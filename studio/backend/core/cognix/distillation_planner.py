# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native distillation planning.

Distillation supports the roadmap goal of small domain experts: a stronger
teacher model guides a smaller student model. This planner only prepares the
contract and gates; it does not call the teacher, read datasets, enqueue jobs,
train, evaluate, or register adapters.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_DISTILLATION_PLANNER_VERSION = "cognix_distillation_planner_v1"
COGNIX_TEACHER_STUDENT_CONTRACT_VERSION = "cognix_teacher_student_contract_v1"
COGNIX_DISTILLATION_EVAL_CONTRACT_VERSION = "cognix_distillation_eval_contract_v1"

SUPPORTED_DATASET_FORMATS = {"jsonl", "csv", "parquet", "hf_dataset", "folder"}
RESTRICTED_LICENSE_VALUES = {"unknown", "unverified", "restricted", "proprietary"}
CEO_CLOUD_TRAINING_TOKENS = {"ceo", "cloud_ceo", "local_plus_cloud_ceo"}
CLOUD_TARGETS = [
    {
        "id": "google_colab",
        "label": "Google Colab",
        "jobType": "cloud_distillation_job",
        "exportFormat": "ipynb_plan",
    },
    {
        "id": "kaggle",
        "label": "Kaggle",
        "jobType": "cloud_distillation_job",
        "exportFormat": "kaggle_kernel_plan",
    },
    {
        "id": "cloud_gpu",
        "label": "Cloud GPU",
        "jobType": "cloud_distillation_job",
        "exportFormat": "container_job_plan",
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _as_int(value: Any) -> int | None:
    parsed = _as_float(value)
    return int(parsed) if parsed is not None else None


def _model_id(model: dict[str, Any]) -> str:
    return str(model.get("modelId") or model.get("id") or model.get("name") or "").strip()[:240]


def _family(model: dict[str, Any]) -> str:
    return str(model.get("family") or model.get("modelFamily") or model.get("architecture") or "").strip().casefold()


def _tokenizer(model: dict[str, Any]) -> str:
    return str(model.get("tokenizerHash") or model.get("tokenizer") or model.get("tokenizerId") or "").strip().casefold()


def _size_b(model: dict[str, Any]) -> float | None:
    for key in ("parameterCountB", "paramsB", "sizeB", "billionParameters"):
        parsed = _as_float(model.get(key))
        if parsed is not None:
            return parsed
    parameter_count = _as_float(model.get("parameterCount") or model.get("params"))
    if parameter_count is None:
        return None
    return round(parameter_count / 1_000_000_000, 3) if parameter_count > 1000 else parameter_count


def _dataset_descriptor(dataset: dict[str, Any] | None) -> dict[str, Any]:
    data = _as_dict(dataset)
    fmt = str(data.get("format") or "unknown").strip().lower()
    sample_count = _as_int(data.get("sampleCount"))
    estimated_tokens = _as_int(data.get("estimatedTokens"))
    invalid_rows = _as_int(data.get("invalidRows")) or 0
    duplicate_ratio = _as_float(data.get("duplicateRatio")) or 0.0
    contains_sensitive = bool(data.get("containsSensitiveData") or data.get("sensitive"))
    license_value = str(data.get("license") or "unknown").strip().lower()
    source_ref = str(data.get("sourceRef") or data.get("datasetName") or data.get("name") or "").strip()[:240]
    checks: list[dict[str, Any]] = [
        {
            "id": "dataset_present",
            "status": "pass" if bool(data) else "blocked",
            "severity": "error" if not data else "info",
        },
        {
            "id": "format_supported",
            "status": "pass" if fmt in SUPPORTED_DATASET_FORMATS else "blocked",
            "severity": "error" if fmt not in SUPPORTED_DATASET_FORMATS else "info",
            "detail": fmt,
        },
        {
            "id": "sample_count_minimum",
            "status": "pass" if sample_count is not None and sample_count >= 200 else "blocked",
            "severity": "error",
            "detail": sample_count,
        },
        {
            "id": "invalid_rows",
            "status": "pass" if invalid_rows == 0 else "blocked",
            "severity": "error" if invalid_rows else "info",
            "detail": invalid_rows,
        },
        {
            "id": "duplicate_ratio",
            "status": "pass" if duplicate_ratio <= 0.08 else "warning",
            "severity": "warning" if duplicate_ratio > 0.08 else "info",
            "detail": round(duplicate_ratio, 4),
        },
        {
            "id": "license_review",
            "status": "warning" if license_value in RESTRICTED_LICENSE_VALUES else "pass",
            "severity": "warning" if license_value in RESTRICTED_LICENSE_VALUES else "info",
            "detail": license_value,
        },
        {
            "id": "sensitive_data_review",
            "status": "warning" if contains_sensitive else "pass",
            "severity": "high" if contains_sensitive else "info",
        },
    ]
    blocked = [item["id"] for item in checks if item.get("status") == "blocked"]
    warnings = [item["id"] for item in checks if item.get("status") == "warning"]
    return {
        "status": "ready" if not blocked else "blocked",
        "ready": not blocked,
        "format": fmt,
        "sourceRef": source_ref or None,
        "sampleCount": sample_count,
        "estimatedTokens": estimated_tokens,
        "containsSensitiveData": contains_sensitive,
        "license": license_value,
        "checks": checks,
        "blockedCheckIds": blocked,
        "warningCheckIds": warnings,
        "rawPreviewIncluded": False,
    }


def _gpu_profile(hardware: dict[str, Any]) -> dict[str, Any]:
    gpu = _as_dict(hardware.get("gpu"))
    devices = [item for item in gpu.get("devices", []) if isinstance(item, dict)]
    max_vram = max((_as_float(item.get("vramTotalGb")) or 0.0 for item in devices), default = 0.0)
    return {
        "available": bool(gpu.get("available")),
        "deviceCount": len(devices),
        "maxVramGb": round(max_vram, 2),
    }


def _is_ceo_plan(user_plan: str | None) -> bool:
    return str(user_plan or "").strip().casefold() in CEO_CLOUD_TRAINING_TOKENS


def _resource_plan(hardware: dict[str, Any], user_plan: str | None, target_id: str | None) -> dict[str, Any]:
    gpu = _gpu_profile(hardware)
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb")) or 0.0
    cloud_allowed = _is_ceo_plan(user_plan)
    requested = str(target_id or "").strip().lower()
    if gpu["available"] and gpu["maxVramGb"] >= 16 and total_gb >= 32:
        return {
            "status": "local_ready",
            "recommendedTargetId": "local_gpu",
            "jobType": "distillation_job",
            "cloudDistillationAllowed": cloud_allowed,
            "localGpuRequired": True,
            "localGpuBypassAllowed": False,
            "availableCloudTargets": CLOUD_TARGETS if cloud_allowed else [],
            "gpu": gpu,
        }
    if cloud_allowed:
        target = next((item for item in CLOUD_TARGETS if item["id"] == requested), CLOUD_TARGETS[0])
        return {
            "status": "cloud_ready",
            "recommendedTargetId": target["id"],
            "jobType": target["jobType"],
            "exportFormat": target["exportFormat"],
            "cloudDistillationAllowed": True,
            "localGpuRequired": False,
            "localGpuBypassAllowed": True,
            "availableCloudTargets": CLOUD_TARGETS,
            "gpu": gpu,
        }
    return {
        "status": "blocked_no_training_target",
        "recommendedTargetId": None,
        "jobType": None,
        "cloudDistillationAllowed": False,
        "localGpuRequired": True,
        "localGpuBypassAllowed": False,
        "availableCloudTargets": [],
        "gpu": gpu,
    }


def _stable_plan_id(username: str, teacher_id: str, student_id: str, objective: str) -> str:
    payload = f"{username}|{teacher_id}|{student_id}|{' '.join((objective or '').split())[:240]}"
    return "distill_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:18]


def build_distillation_plan(
    *,
    username: str,
    objective: str,
    teacher_model: dict[str, Any] | None,
    student_model: dict[str, Any] | None,
    dataset: dict[str, Any] | None,
    hardware: dict[str, Any] | None = None,
    user_plan: str | None = None,
    project_id: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    teacher = _as_dict(teacher_model)
    student = _as_dict(student_model)
    hardware = _as_dict(hardware)
    teacher_id = _model_id(teacher)
    student_id = _model_id(student)
    teacher_size = _size_b(teacher)
    student_size = _size_b(student)
    teacher_family = _family(teacher)
    student_family = _family(student)
    tokenizer_match = bool(_tokenizer(teacher) and _tokenizer(teacher) == _tokenizer(student))
    family_match = bool(teacher_family and teacher_family == student_family)
    student_smaller = bool(
        teacher_size is not None
        and student_size is not None
        and student_size < teacher_size
        and student_size <= max(teacher_size * 0.75, 0.1)
    )
    dataset_plan = _dataset_descriptor(dataset)
    resource = _resource_plan(hardware, user_plan, target_id)
    method = "logit_distillation" if tokenizer_match else "response_distillation"
    gates = [
        {"id": "teacher_model_declared", "status": "pass" if teacher_id else "blocked", "requiredBefore": "plan"},
        {"id": "student_model_declared", "status": "pass" if student_id else "blocked", "requiredBefore": "plan"},
        {"id": "teacher_student_distinct", "status": "pass" if teacher_id and student_id and teacher_id != student_id else "blocked", "requiredBefore": "plan"},
        {"id": "student_smaller_than_teacher", "status": "pass" if student_smaller else "blocked", "requiredBefore": "plan"},
        {"id": "tokenizer_or_family_compatible", "status": "pass" if (tokenizer_match or family_match) else "warning", "requiredBefore": "job"},
        {"id": "dataset_ready", "status": "pass" if dataset_plan["ready"] else "blocked", "requiredBefore": "job", "blockedCheckIds": dataset_plan["blockedCheckIds"]},
        {"id": "resource_target_ready", "status": "pass" if resource["status"] in {"local_ready", "cloud_ready"} else "blocked", "requiredBefore": "job"},
        {"id": "teacher_output_review", "status": "planned", "requiredBefore": "job"},
        {"id": "evaluation_set_ready", "status": "planned", "requiredBefore": "model_registration"},
        {"id": "human_approval", "status": "planned", "requiredBefore": "job"},
    ]
    blocked_gate_ids = [str(item["id"]) for item in gates if item.get("status") == "blocked"]
    warning_gate_ids = [str(item["id"]) for item in gates if item.get("status") == "warning"]
    ready_for_approval = not blocked_gate_ids
    status = "ready_for_approval" if ready_for_approval else "blocked_by_gates"
    side_effects = {
        "teacherModelCall": False,
        "studentModelLoad": False,
        "teacherModelLoad": False,
        "generation": False,
        "datasetRead": False,
        "datasetImport": False,
        "syntheticDataWrite": False,
        "distillationJob": False,
        "cloudDistillationJob": False,
        "adapterWrite": False,
        "modelRegistration": False,
        "jobEnqueue": False,
        "networkModelCall": False,
        "cloudCredentialRead": False,
    }
    return {
        "plannerVersion": COGNIX_DISTILLATION_PLANNER_VERSION,
        "teacherStudentContractVersion": COGNIX_TEACHER_STUDENT_CONTRACT_VERSION,
        "evaluationContractVersion": COGNIX_DISTILLATION_EVAL_CONTRACT_VERSION,
        "mode": "distillation_contract_dry_run",
        "planId": _stable_plan_id(username, teacher_id, student_id, objective),
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "status": status,
        "readyForApproval": ready_for_approval,
        "readyForJob": False,
        "teacher": {
            "modelId": teacher_id or None,
            "family": teacher_family or None,
            "parameterCountB": teacher_size,
            "willLoad": False,
            "willGenerate": False,
        },
        "student": {
            "modelId": student_id or None,
            "family": student_family or None,
            "parameterCountB": student_size,
            "willLoad": False,
            "willTrain": False,
        },
        "teacherStudentContract": {
            "method": method,
            "tokenizerCompatible": tokenizer_match,
            "familyCompatible": family_match,
            "studentSmallerThanTeacher": student_smaller,
            "requiresTeacherOutputReview": True,
            "rawTeacherOutputStorageAllowed": False,
            "qualityRegressionAllowedWithoutReview": False,
        },
        "dataset": dataset_plan,
        "resourceTargetPlan": resource,
        "queuePlan": {
            "queueRequired": ready_for_approval,
            "queueId": "cloud_training" if resource.get("jobType") == "cloud_distillation_job" else "gpu_long_running" if resource.get("jobType") else None,
            "jobType": resource.get("jobType"),
            "willEnqueueNow": False,
            "requiresHumanConfirmation": True,
        },
        "evaluationContract": {
            "requiresBaselineEval": True,
            "requiresTeacherStudentComparison": True,
            "requiresHeldOutSet": True,
            "maxAllowedQualityDelta": 0.03,
            "registerStudentBeforeEvalAllowed": False,
            "sideEffects": {
                "evaluationRun": False,
                "modelRegistration": False,
            },
        },
        "gates": gates,
        "summary": {
            "blockedGateIds": blocked_gate_ids,
            "warningGateIds": warning_gate_ids + list(dataset_plan.get("warningCheckIds") or []),
            "readyForApproval": ready_for_approval,
            "recommendedMethod": method,
            "recommendedTargetId": resource.get("recommendedTargetId"),
        },
        "blockedActions": [
            {"id": "teacher_generation", "reason": "Aucun appel teacher n'est effectue pendant la planification."},
            {"id": "distillation_job", "reason": "Aucun entrainement student n'est lance sans queue et approbation."},
            {"id": "model_registration", "reason": "Aucun modele distille n'est enregistre avant evaluation."},
        ],
        "warnings": [
            "Dataset sensible: revue explicite requise avant distillation."
        ] if dataset_plan.get("containsSensitiveData") else [],
        "sideEffects": side_effects,
    }
