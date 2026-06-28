# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX guided fine-tuning planner.

This module implements the roadmap rule "RAG before fine-tuning" and prepares
resource/method estimates for LoRA/QLoRA without starting a training job.
"""

from __future__ import annotations

from typing import Any


COGNIX_FINE_TUNING_PLANNER_VERSION = "cognix_fine_tuning_planner_v1"

SUPPORTED_DATASET_FORMATS = {"jsonl", "csv", "parquet", "hf_dataset", "folder"}
LICENSE_WARNING_VALUES = {"unknown", "unverified", "restricted", "proprietary"}
CLOUD_TRAINING_TARGETS: list[dict[str, Any]] = [
    {
        "id": "google_colab",
        "label": "Google Colab",
        "access": "external_notebook",
        "bestFor": ["quick_prototype", "notebook_export", "single_gpu"],
        "requires": ["notebook_export", "dataset_access_plan", "secret_review"],
        "exportFormat": "ipynb_plan",
        "secretNames": ["HF_TOKEN"],
        "datasetModes": ["google_drive_mount", "manual_upload", "hf_dataset"],
        "artifactOutputs": ["lora_adapter", "training_metrics", "eval_report"],
    },
    {
        "id": "kaggle",
        "label": "Kaggle",
        "access": "external_notebook",
        "bestFor": ["dataset_hosted_training", "reproducible_notebook"],
        "requires": ["notebook_export", "dataset_terms_review", "secret_review"],
        "exportFormat": "kaggle_kernel_plan",
        "secretNames": ["HF_TOKEN", "KAGGLE_USERNAME"],
        "datasetModes": ["kaggle_dataset", "manual_upload", "hf_dataset"],
        "artifactOutputs": ["lora_adapter", "training_metrics", "dataset_card"],
    },
    {
        "id": "cloud_gpu",
        "label": "Cloud GPU",
        "access": "managed_cloud_runner",
        "bestFor": ["larger_jobs", "repeatable_training", "long_running_runs"],
        "requires": ["provider_credentials", "budget_limit", "artifact_sync"],
        "exportFormat": "container_job_plan",
        "secretNames": ["HF_TOKEN", "CLOUD_PROVIDER_TOKEN"],
        "datasetModes": ["object_storage", "hf_dataset", "signed_url"],
        "artifactOutputs": ["lora_adapter", "training_metrics", "eval_report", "model_card"],
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


def _target_by_id(target_id: str | None) -> dict[str, Any] | None:
    normalized = str(target_id or "").strip().lower()
    if not normalized:
        return None
    return next((item for item in CLOUD_TRAINING_TARGETS if item.get("id") == normalized), None)


def _gpu_summary(hardware: dict[str, Any]) -> dict[str, Any]:
    gpu = _as_dict(hardware.get("gpu"))
    devices = [
        item
        for item in gpu.get("devices", [])
        if isinstance(item, dict)
    ]
    max_vram = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices),
        default = 0.0,
    )
    return {
        "available": bool(gpu.get("available")),
        "deviceCount": len(devices),
        "maxVramGb": round(max_vram, 2),
    }


def _is_ceo_plan(user_plan: str | None) -> bool:
    return str(user_plan or "").strip().casefold() == "ceo"


def _hardware_tier(hardware: dict[str, Any], *, user_plan: str | None = None) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb")) or 0.0
    available_gb = _as_float(memory.get("availableGb")) or 0.0
    gpu = _gpu_summary(hardware)
    if gpu["available"] and gpu["maxVramGb"] >= 24 and total_gb >= 48:
        return {
            "tier": "training_ready",
            "method": "lora",
            "reason": "GPU et RAM suffisants pour LoRA local controle.",
        }
    if gpu["available"] and gpu["maxVramGb"] >= 12 and total_gb >= 24:
        return {
            "tier": "qlora_ready",
            "method": "qlora",
            "reason": "VRAM moyenne: QLoRA recommande pour limiter la memoire.",
        }
    if _is_ceo_plan(user_plan):
        return {
            "tier": "cloud_training_ready",
            "method": "cloud_qlora",
            "reason": "Compte CEO: training cloud autorise meme sans GPU local AMD/NVIDIA.",
            "cloudEligible": True,
            "localGpuRequired": False,
        }
    if total_gb >= 32 and available_gb >= 16:
        return {
            "tier": "cpu_experimental",
            "method": "qlora_cpu_experimental",
            "reason": "Pas de GPU visible: entrainement local seulement experimental et lent.",
        }
    return {
        "tier": "not_recommended",
        "method": "none",
        "reason": "Materiel local insuffisant pour fine-tuning; preferer RAG ou cloud.",
    }


def _dataset_checks(dataset: dict[str, Any] | None) -> dict[str, Any]:
    data = _as_dict(dataset)
    if not data:
        return {
            "status": "missing",
            "ready": False,
            "checks": [
                {"id": "dataset_present", "status": "missing", "severity": "error"},
            ],
            "warnings": ["Dataset absent: importer ou decrire un dataset avant entrainement."],
        }

    fmt = str(data.get("format") or "unknown").strip().lower()
    sample_count = _as_int(data.get("sampleCount"))
    estimated_tokens = _as_int(data.get("estimatedTokens"))
    duplicate_ratio = _as_float(data.get("duplicateRatio")) or 0.0
    invalid_rows = _as_int(data.get("invalidRows")) or 0
    average_response_tokens = _as_float(data.get("averageResponseTokens"))
    license_value = str(data.get("license") or "unknown").strip().lower()
    contains_sensitive = bool(data.get("containsSensitiveData"))

    checks: list[dict[str, Any]] = [
        {
            "id": "format_supported",
            "status": "pass" if fmt in SUPPORTED_DATASET_FORMATS else "warning",
            "severity": "warning" if fmt not in SUPPORTED_DATASET_FORMATS else "info",
            "detail": fmt,
        },
        {
            "id": "sample_count",
            "status": "pass" if sample_count and sample_count >= 100 else "warning",
            "severity": "warning",
            "detail": sample_count,
        },
        {
            "id": "token_budget",
            "status": "pass" if estimated_tokens and estimated_tokens >= 50_000 else "warning",
            "severity": "warning",
            "detail": estimated_tokens,
        },
        {
            "id": "duplicates",
            "status": "pass" if duplicate_ratio <= 0.05 else "warning",
            "severity": "warning",
            "detail": duplicate_ratio,
        },
        {
            "id": "invalid_rows",
            "status": "pass" if invalid_rows == 0 else "warning",
            "severity": "warning",
            "detail": invalid_rows,
        },
        {
            "id": "response_length",
            "status": "pass"
            if average_response_tokens is None or average_response_tokens >= 12
            else "warning",
            "severity": "warning",
            "detail": average_response_tokens,
        },
        {
            "id": "license",
            "status": "pass" if license_value not in LICENSE_WARNING_VALUES else "warning",
            "severity": "warning",
            "detail": license_value,
        },
        {
            "id": "sensitive_data",
            "status": "warning" if contains_sensitive else "pass",
            "severity": "warning" if contains_sensitive else "info",
            "detail": contains_sensitive,
        },
    ]
    warnings = [
        str(check["id"])
        for check in checks
        if check.get("status") != "pass"
    ]
    return {
        "status": "ready_with_warnings" if warnings else "ready",
        "ready": not any(check["severity"] == "error" for check in checks),
        "format": fmt,
        "sampleCount": sample_count,
        "estimatedTokens": estimated_tokens,
        "checks": checks,
        "warnings": warnings,
    }


def _dataset_descriptor(dataset: dict[str, Any] | None, dataset_checks: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(dataset)
    return {
        "format": dataset_checks.get("format"),
        "sampleCount": dataset_checks.get("sampleCount"),
        "estimatedTokens": dataset_checks.get("estimatedTokens"),
        "license": str(data.get("license") or "unknown").strip().lower(),
        "containsSensitiveData": bool(data.get("containsSensitiveData")),
        "sourceRef": str(data.get("sourceRef") or data.get("datasetId") or data.get("name") or "provided_metadata")[:160],
        "rawPreviewStored": False,
    }


def _dataset_access_plan(target: dict[str, Any], dataset: dict[str, Any] | None, dataset_checks: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(dataset)
    fmt = str(dataset_checks.get("format") or "unknown")
    target_modes = [str(item) for item in target.get("datasetModes") or []]
    if fmt == "hf_dataset" and "hf_dataset" in target_modes:
        mode = "hf_dataset"
    elif target.get("id") == "google_colab" and "google_drive_mount" in target_modes:
        mode = "google_drive_mount"
    elif target.get("id") == "kaggle" and "kaggle_dataset" in target_modes:
        mode = "kaggle_dataset"
    else:
        mode = target_modes[0] if target_modes else "manual_upload"
    return {
        "mode": mode,
        "requiresDatasetUpload": mode in {"manual_upload", "kaggle_dataset", "object_storage"},
        "requiresSecretReview": bool(target.get("requiresSecret", True) or target.get("secretNames")),
        "datasetDescriptor": _dataset_descriptor(dataset, dataset_checks),
        "allowedModes": target_modes,
        "rawDatasetRead": False,
        "datasetUpload": False,
        "notes": [
            "Le dataset est decrit par metadonnees uniquement pendant ce plan.",
            "Aucun contenu dataset n'est lu ni transfere avant confirmation et executor dedie.",
        ],
    }


def _cloud_handoff_steps(target: dict[str, Any], fine_tuning_plan: dict[str, Any]) -> list[dict[str, Any]]:
    method = str(_as_dict(fine_tuning_plan.get("method")).get("type") or "cloud_qlora")
    base_model = _as_dict(fine_tuning_plan.get("baseModel")).get("modelId") or "selected_model"
    return [
        {
            "id": "create_training_config",
            "label": "Creer la configuration CogniX training",
            "status": "planned",
            "detail": f"Preparer methode {method} pour {base_model}.",
        },
        {
            "id": "prepare_runtime",
            "label": "Preparer le runtime cloud",
            "status": "planned",
            "detail": f"Exporter le format {target.get('exportFormat')}.",
        },
        {
            "id": "attach_dataset",
            "label": "Attacher le dataset",
            "status": "planned",
            "detail": "Verifier acces dataset sans lire ni uploader de contenu dans ce plan.",
        },
        {
            "id": "run_training_after_confirmation",
            "label": "Lancer apres confirmation humaine",
            "status": "blocked",
            "detail": "Le lancement cloud reste bloque hors executor approuve.",
        },
        {
            "id": "collect_artifacts",
            "label": "Collecter adaptateur et rapports",
            "status": "planned",
            "detail": "Synchroniser les artefacts seulement apres job termine et evaluation.",
        },
    ]


def build_cloud_training_handoff_plan(
    *,
    username: str,
    objective: str,
    project_id: str | None,
    target_id: str | None,
    fine_tuning_plan: dict[str, Any],
    dataset: dict[str, Any] | None = None,
    user_plan: str | None = None,
) -> dict[str, Any]:
    target = _target_by_id(target_id) or _target_by_id(
        _as_dict(fine_tuning_plan.get("resourceTargetPlan")).get("recommendedTargetId")
    ) or _target_by_id("google_colab")
    assert target is not None
    dataset_result = _dataset_checks(dataset)
    method = str(_as_dict(fine_tuning_plan.get("method")).get("type") or "none")
    resource_plan = _as_dict(fine_tuning_plan.get("resourceTargetPlan"))
    approval = _as_dict(fine_tuning_plan.get("approval"))
    cloud_allowed = bool(resource_plan.get("cloudTrainingAllowed"))
    dataset_ready = bool(dataset_result.get("ready"))
    target_known = target.get("id") in {item.get("id") for item in CLOUD_TRAINING_TARGETS}
    ready_to_export = target_known and cloud_allowed and dataset_ready and method == "cloud_qlora"

    status = "ready_for_export" if ready_to_export else "blocked_not_cloud_eligible"
    if not dataset_ready:
        status = "blocked_dataset_not_ready"
    if not target_known:
        status = "blocked_unknown_target"

    warnings: list[str] = []
    warnings.extend(str(item) for item in dataset_result.get("warnings", []))
    if not cloud_allowed:
        warnings.append("Le plan fine-tuning courant n'autorise pas encore le training cloud.")
    if method != "cloud_qlora":
        warnings.append("Le handoff cloud exige une methode cloud_qlora.")
    if _as_dict(dataset).get("containsSensitiveData"):
        warnings.append("Dataset sensible: revue permissions, secrets et destination cloud obligatoire.")

    artifact_manifest = [
        {
            "path": "cognix-training-config.json",
            "purpose": "Configuration reproductible du job cloud.",
            "containsSecret": False,
            "writePlanned": True,
        },
        {
            "path": "train_unsloth_lora.py",
            "purpose": "Script training LoRA/QLoRA exportable.",
            "containsSecret": False,
            "writePlanned": True,
        },
        {
            "path": "README_CogniX_training.md",
            "purpose": "Instructions d'execution et d'audit.",
            "containsSecret": False,
            "writePlanned": True,
        },
    ]
    if target.get("exportFormat") in {"ipynb_plan", "kaggle_kernel_plan"}:
        artifact_manifest.append(
            {
                "path": "CogniX_training_notebook.ipynb",
                "purpose": "Notebook cloud planifie pour execution manuelle.",
                "containsSecret": False,
                "writePlanned": True,
            }
        )

    return {
        "plannerVersion": COGNIX_FINE_TUNING_PLANNER_VERSION,
        "mode": "dry_run",
        "handoffVersion": "cognix_cloud_training_handoff_v1",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "status": status,
        "readyToExport": ready_to_export,
        "target": {
            **target,
            "launchUrlGenerated": False,
            "jobSubmitted": False,
        },
        "method": _as_dict(fine_tuning_plan.get("method")),
        "baseModel": _as_dict(fine_tuning_plan.get("baseModel")),
        "dataset": dataset_result,
        "datasetAccessPlan": _dataset_access_plan(target, dataset, dataset_result),
        "notebookPlan": {
            "format": target.get("exportFormat"),
            "steps": _cloud_handoff_steps(target, fine_tuning_plan),
            "parameterCells": [
                "base_model_id",
                "dataset_source",
                "lora_rank",
                "learning_rate",
                "max_steps",
                "output_adapter_name",
            ],
            "secretPlaceholders": [str(item) for item in target.get("secretNames") or []],
            "rawSecretValuesIncluded": False,
        },
        "artifactManifest": artifact_manifest,
        "approval": {
            "required": True,
            "readyToRequest": ready_to_export and bool(approval.get("readyToRequest")),
            "requiredBefore": ["dataset_upload", "cloud_training_job", "artifact_sync", "model_registration"],
        },
        "blockedActions": [
            {
                "id": "notebook_write",
                "reason": "Aucun notebook ou script n'est ecrit pendant ce plan.",
            },
            {
                "id": "dataset_upload",
                "reason": "Aucun dataset n'est transfere vers le cloud pendant ce plan.",
            },
            {
                "id": "cloud_training_job",
                "reason": "Aucun job Colab/Kaggle/Cloud GPU n'est lance sans executor et confirmation.",
            },
            {
                "id": "cloud_secret_read",
                "reason": "Aucune valeur de secret n'est lue; seuls les noms attendus sont declares.",
            },
        ],
        "warnings": warnings,
        "sideEffects": {
            "fileWrite": False,
            "notebookWrite": False,
            "datasetRead": False,
            "datasetUpload": False,
            "cloudCredentialRead": False,
            "cloudTrainingJob": False,
            "networkCall": False,
            "adapterWrite": False,
            "modelRegistration": False,
        },
    }


def _time_estimate_hours(
    *,
    method: str,
    dataset_checks: dict[str, Any],
    hardware_tier: dict[str, Any],
) -> float | None:
    if method == "none":
        return None
    tokens = _as_float(dataset_checks.get("estimatedTokens")) or 75_000.0
    token_factor = max(0.5, tokens / 250_000.0)
    multiplier = {
        "lora": 1.0,
        "qlora": 1.35,
        "qlora_cpu_experimental": 5.5,
        "cloud_qlora": 1.1,
    }.get(method, 2.0)
    if hardware_tier.get("tier") == "training_ready":
        multiplier *= 0.8
    return round(max(0.25, token_factor * multiplier), 2)


def _recommended_path(task_strategy: dict[str, Any]) -> str:
    path = str(task_strategy.get("path") or "expert_chat")
    if path == "rag_first":
        return "rag_before_fine_tuning"
    if path == "guided_fine_tuning":
        return "guided_fine_tuning"
    return "no_fine_tuning_needed"


def build_fine_tuning_plan(
    *,
    objective: str,
    classification: dict[str, Any],
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    hardware: dict[str, Any],
    dataset: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    user_plan: str | None = None,
) -> dict[str, Any]:
    hardware_tier = _hardware_tier(hardware, user_plan = user_plan)
    dataset_result = _dataset_checks(dataset)
    path = _recommended_path(task_strategy)
    method = str(hardware_tier["method"])
    if path != "guided_fine_tuning":
        method = "none"
    estimated_hours = _time_estimate_hours(
        method = method,
        dataset_checks = dataset_result,
        hardware_tier = hardware_tier,
    )
    benchmark = _as_dict(_as_dict(latest_benchmark_run).get("benchmark"))
    optimization = _as_dict(benchmark.get("optimizationPlan"))

    blocked_actions = [
        {
            "id": "fine_tuning_job",
            "reason": "Aucun entrainement n'est lance pendant la planification CogniX.",
        },
        {
            "id": "cloud_training_job",
            "reason": "Aucun job cloud Kaggle/Colab/GPU n'est lance sans executor et confirmation explicites.",
        },
        {
            "id": "dataset_import",
            "reason": "Le dataset doit etre valide par un executor dedie avant import.",
        },
        {
            "id": "model_registration",
            "reason": "Aucun adaptateur LoRA n'est enregistre sans evaluation.",
        },
    ]
    if path == "rag_before_fine_tuning":
        blocked_actions.append(
            {
                "id": "premature_fine_tuning",
                "reason": "La demande parle de documents/sources: RAG est recommande avant fine-tuning.",
            }
        )

    warnings: list[str] = []
    warnings.extend(str(item) for item in dataset_result.get("warnings", []))
    if hardware_tier["tier"] in {"not_recommended", "cpu_experimental"}:
        warnings.append(str(hardware_tier["reason"]))
    if path == "rag_before_fine_tuning":
        warnings.append("RAG recommande avant fine-tuning pour les documents et sources.")
    if optimization.get("quantization"):
        warnings.append(f"Quantization recommandee par benchmark: {optimization['quantization']}")

    ready_to_request_approval = (
        path == "guided_fine_tuning"
        and bool(dataset_result.get("ready"))
        and method in {"lora", "qlora", "qlora_cpu_experimental", "cloud_qlora"}
    )
    cloud_targets = [dict(item) for item in CLOUD_TRAINING_TARGETS]
    recommended_cloud_target = "google_colab" if method == "cloud_qlora" else None

    return {
        "plannerVersion": COGNIX_FINE_TUNING_PLANNER_VERSION,
        "mode": "dry_run",
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "recommendedPath": path,
        "baseModel": {
            "modelId": recommendation.get("modelId"),
            "modelLabel": recommendation.get("modelLabel"),
            "providerId": recommendation.get("providerId"),
            "providerType": recommendation.get("providerType"),
        },
        "targetDomain": classification.get("selectedDomain") or "general",
        "method": {
            "type": method,
            "label": {
                "lora": "LoRA local",
                "qlora": "QLoRA local",
                "qlora_cpu_experimental": "QLoRA CPU experimental",
                "cloud_qlora": "QLoRA cloud",
                "none": "Aucun fine-tuning recommande",
            }.get(method, method),
            "requiresGpu": method in {"lora", "qlora"},
            "requiresLocalGpu": method in {"lora", "qlora"},
            "requiresCloudCompute": method == "cloud_qlora",
            "estimatedHours": estimated_hours,
        },
        "hardwareFit": {
            **hardware_tier,
            "gpu": _gpu_summary(hardware),
            "memory": _as_dict(hardware.get("memory")),
        },
        "resourceTargetPlan": {
            "recommendedTargetId": recommended_cloud_target or "local",
            "cloudTrainingAllowed": method == "cloud_qlora",
            "localGpuBypassAllowed": method == "cloud_qlora",
            "availableTargets": cloud_targets if method == "cloud_qlora" else [],
            "requiresHumanConfirmation": method == "cloud_qlora",
        },
        "dataset": dataset_result,
        "approval": {
            "required": path == "guided_fine_tuning",
            "readyToRequest": ready_to_request_approval,
            "requiredBefore": ["dataset_import", "fine_tuning_job", "cloud_training_job", "model_registration"],
        },
        "blockedActions": blocked_actions,
        "warnings": warnings,
        "reason": (
            "RAG est recommande avant fine-tuning pour ce besoin documentaire."
            if path == "rag_before_fine_tuning"
            else "CogniX peut preparer un fine-tuning guide, mais aucun job n'est lance."
            if path == "guided_fine_tuning"
            else "Aucun signal ne justifie un fine-tuning pour cette demande."
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "datasetImport": False,
            "fineTuningJob": False,
            "cloudTrainingJob": False,
            "cloudCredentialRead": False,
            "adapterWrite": False,
            "modelRegistration": False,
        },
    }
