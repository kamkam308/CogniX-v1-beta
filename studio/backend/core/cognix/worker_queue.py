# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX worker queue planning.

This module plans long-running background work without enqueueing jobs,
starting workers, downloading models, indexing documents, training adapters,
running benchmarks, or changing code.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_WORKER_QUEUE_VERSION = "cognix_worker_queue_v1"
COGNIX_WORKER_JOB_SPEC_VERSION = "cognix_worker_job_spec_v1"

QUEUE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "local_probe",
        "label": "Local probe",
        "acceptedJobTypes": ["benchmark_run", "health_check"],
        "maxConcurrentJobs": 1,
        "requiresAudit": True,
        "requiresHumanConfirmation": False,
    },
    {
        "id": "local_runtime",
        "label": "Local runtime",
        "acceptedJobTypes": ["model_preload", "cache_warmup", "model_download"],
        "maxConcurrentJobs": 1,
        "requiresAudit": True,
        "requiresHumanConfirmation": True,
    },
    {
        "id": "io_bound",
        "label": "IO bound",
        "acceptedJobTypes": ["rag_indexing", "document_ingest"],
        "maxConcurrentJobs": 1,
        "requiresAudit": True,
        "requiresHumanConfirmation": True,
    },
    {
        "id": "gpu_long_running",
        "label": "GPU long running",
        "acceptedJobTypes": ["fine_tuning_job"],
        "maxConcurrentJobs": 1,
        "requiresAudit": True,
        "requiresHumanConfirmation": True,
    },
    {
        "id": "cloud_training",
        "label": "Cloud training",
        "acceptedJobTypes": ["cloud_training_job"],
        "maxConcurrentJobs": 1,
        "requiresAudit": True,
        "requiresHumanConfirmation": True,
    },
    {
        "id": "codex_guarded",
        "label": "Codex guarded",
        "acceptedJobTypes": ["codex_pipeline"],
        "maxConcurrentJobs": 1,
        "requiresAudit": True,
        "requiresHumanConfirmation": True,
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _objective_excerpt(objective: str | None) -> str:
    return " ".join((objective or "").split())[:500]


def _stable_key(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:18]


def _queue(queue_id: str) -> dict[str, Any]:
    for queue in QUEUE_DEFINITIONS:
        if queue["id"] == queue_id:
            return dict(queue)
    return {
        "id": "none",
        "label": "No worker queue",
        "acceptedJobTypes": [],
        "maxConcurrentJobs": 0,
        "requiresAudit": True,
        "requiresHumanConfirmation": False,
    }


def _job(
    *,
    job_id: str,
    job_type: str,
    queue_id: str,
    label: str,
    reason: str,
    priority: int,
    required_gates: list[str],
    source_plan: str,
    requires_human_confirmation: bool,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "type": job_type,
        "queueId": queue_id,
        "label": label,
        "status": "planned",
        "priority": max(0, min(priority, 100)),
        "reason": reason,
        "sourcePlan": source_plan,
        "requiredGates": required_gates,
        "requiresAudit": True,
        "requiresRateLimit": True,
        "requiresHumanConfirmation": requires_human_confirmation,
        "willEnqueue": False,
        "willStartWorker": False,
    }


def _needs_benchmark_job(
    *,
    optimization_plan: dict[str, Any],
    latest_benchmark_run: dict[str, Any] | None,
) -> bool:
    if not isinstance(latest_benchmark_run, dict):
        return True
    for item in _as_list(optimization_plan.get("optimizations")):
        if (
            isinstance(item, dict)
            and item.get("id") == "benchmark_calibration"
            and item.get("status") == "recommended"
        ):
            return True
    return False


def build_worker_queue_registry() -> dict[str, Any]:
    return {
        "workerQueueVersion": COGNIX_WORKER_QUEUE_VERSION,
        "mode": "declarative_dry_run",
        "queues": [dict(queue) for queue in QUEUE_DEFINITIONS],
        "globalPolicies": {
            "frontendDirectQueueMutationAllowed": False,
            "backgroundExecutionAllowedFromPlanner": False,
            "jobSpecsRequireApproval": True,
            "idempotencyKeyRequired": True,
            "maxConcurrentLocalJobs": 1,
            "auditRequired": True,
            "rateLimitsEnabled": True,
        },
        "sideEffects": {
            "jobEnqueue": False,
            "workerStart": False,
            "modelDownload": False,
            "modelLoad": False,
            "ragIndexing": False,
            "cloudTrainingJob": False,
            "fineTuningJob": False,
            "benchmarkRun": False,
            "codeModification": False,
            "deployment": False,
        },
    }


def build_worker_queue_plan(
    *,
    objective: str,
    project_id: str | None = None,
    task_strategy: dict[str, Any] | None = None,
    rag_plan: dict[str, Any] | None = None,
    fine_tuning_plan: dict[str, Any] | None = None,
    preload_plan: dict[str, Any] | None = None,
    codex_pipeline_plan: dict[str, Any] | None = None,
    optimization_plan: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_strategy = _as_dict(task_strategy)
    rag_plan = _as_dict(rag_plan)
    fine_tuning_plan = _as_dict(fine_tuning_plan)
    preload_plan = _as_dict(preload_plan)
    codex_pipeline_plan = _as_dict(codex_pipeline_plan)
    optimization_plan = _as_dict(optimization_plan)

    jobs: list[dict[str, Any]] = []
    if (
        task_strategy.get("path") == "rag_first"
        and rag_plan.get("recommendedPath") == "rag_first"
        and not bool(rag_plan.get("readyForRetrieval"))
    ):
        jobs.append(
            _job(
                job_id = "rag_indexing",
                job_type = "rag_indexing",
                queue_id = "io_bound",
                label = "Indexer les sources RAG",
                reason = "RAG recommande mais les sources ne sont pas pretes pour retrieval.",
                priority = 86,
                required_gates = ["sources_present", "permissions_checked", "embedding_runtime_ready"],
                source_plan = "ragPlan",
                requires_human_confirmation = True,
            )
        )

    if fine_tuning_plan.get("recommendedPath") == "guided_fine_tuning":
        ready = bool(_as_dict(fine_tuning_plan.get("approval")).get("readyToRequest"))
        method = _as_dict(fine_tuning_plan.get("method"))
        resource_target = _as_dict(fine_tuning_plan.get("resourceTargetPlan"))
        cloud_training = bool(resource_target.get("cloudTrainingAllowed")) or method.get("type") == "cloud_qlora"
        jobs.append(
            _job(
                job_id = "cloud_training_job" if cloud_training else "fine_tuning_job",
                job_type = "cloud_training_job" if cloud_training else "fine_tuning_job",
                queue_id = "cloud_training" if cloud_training else "gpu_long_running",
                label = "Preparer un training cloud guide" if cloud_training else "Preparer un fine-tuning guide",
                reason = (
                    "Dataset, methode et cible cloud prets pour demande d'approbation."
                    if ready and cloud_training
                    else "Dataset et methode prets pour demande d'approbation."
                    if ready
                    else "Fine-tuning detecte mais validation dataset ou materiel encore incomplete."
                ),
                priority = 82 if ready else 68,
                required_gates = (
                    ["dataset_validation", "cloud_handoff_export", "secret_review", "budget_limit", "human_approval"]
                    if cloud_training
                    else ["dataset_validation", "resource_estimate", "human_approval"]
                ),
                source_plan = "fineTuningPlan",
                requires_human_confirmation = True,
            )
        )

    if bool(codex_pipeline_plan.get("applicable")):
        jobs.append(
            _job(
                job_id = "codex_pipeline",
                job_type = "codex_pipeline",
                queue_id = "codex_guarded",
                label = "Executer pipeline Codex securise",
                reason = "Demande code detectee: isoler branche, tests, build et revue avant toute fusion.",
                priority = 90,
                required_gates = ["clean_worktree", "scoped_changes", "tests_pass", "build_passes"],
                source_plan = "codexPipelinePlan",
                requires_human_confirmation = True,
            )
        )

    preload_action = (_as_list(preload_plan.get("actions")) or [{}])[0]
    if isinstance(preload_action, dict) and preload_action.get("type") in {"would_preload", "would_preload_after_lru"}:
        jobs.append(
            _job(
                job_id = "model_preload",
                job_type = "model_preload",
                queue_id = "local_runtime",
                label = "Precharger le modele cible",
                reason = str(preload_action.get("reason") or "Modele candidat pret pour prechargement controle."),
                priority = int(preload_action.get("priority") or 64),
                required_gates = ["runtime_adapter_ready", "memory_guard", "cache_policy"],
                source_plan = "preloadPlan",
                requires_human_confirmation = True,
            )
        )

    if _needs_benchmark_job(
        optimization_plan = optimization_plan,
        latest_benchmark_run = latest_benchmark_run,
    ):
        jobs.append(
            _job(
                job_id = "benchmark_run",
                job_type = "benchmark_run",
                queue_id = "local_probe",
                label = "Mesurer benchmark local",
                reason = "Calibration benchmark absente ou recommandee avant optimisation runtime.",
                priority = 58,
                required_gates = ["idle_machine", "thermal_guard", "no_model_generation"],
                source_plan = "optimizationPlan",
                requires_human_confirmation = False,
            )
        )

    jobs = sorted(jobs, key = lambda item: int(item.get("priority") or 0), reverse = True)
    recommended_queue_id = str(jobs[0]["queueId"]) if jobs else "none"
    requires_human_confirmation = any(bool(job.get("requiresHumanConfirmation")) for job in jobs)
    warnings: list[str] = []
    if requires_human_confirmation:
        warnings.append("Jobs longs planifies: confirmation humaine requise avant enqueue.")
    if len(jobs) > 1:
        warnings.append("Plusieurs jobs candidats: executer sequentiellement sur machine locale.")
    if not jobs:
        warnings.append("Aucun job background requis pour cette demande.")

    return {
        "workerQueueVersion": COGNIX_WORKER_QUEUE_VERSION,
        "mode": "dry_run",
        "objectiveExcerpt": _objective_excerpt(objective),
        "projectId": project_id,
        "recommendedQueue": _queue(recommended_queue_id),
        "jobs": jobs,
        "summary": {
            "plannedJobCount": len(jobs),
            "plannedJobIds": [str(job["id"]) for job in jobs],
            "requiresHumanConfirmation": requires_human_confirmation,
            "requiresAudit": True,
            "safeToAutoEnqueue": False,
        },
        "concurrencyPolicy": {
            "maxConcurrentLocalJobs": 1,
            "queueOrder": [str(job["queueId"]) for job in jobs],
            "runSequentially": True,
            "backgroundExecutionAllowed": False,
        },
        "resourceGuards": {
            "frontendDirectQueueMutationAllowed": False,
            "requiresAudit": True,
            "requiresRateLimit": bool(jobs),
            "requiresHumanConfirmation": requires_human_confirmation,
            "modelGenerationBlockedDuringPlanning": True,
            "codeMutationBlockedDuringPlanning": True,
        },
        "blockedActions": [
            {
                "id": "job_enqueue",
                "reason": "Le planner ne place aucun job dans une file d'execution.",
            },
            {
                "id": "worker_start",
                "reason": "Aucun worker n'est demarre par ce planner.",
            },
            {
                "id": "long_running_side_effects",
                "reason": "Downloads, indexation, fine-tuning, benchmark et code restent bloques en dry-run.",
            },
        ],
        "warnings": warnings,
        "reason": (
            "Files de workers planifiees sans execution ni mutation."
            if jobs
            else "Aucune file de workers necessaire pour cette demande."
        ),
        "sideEffects": {
            "jobEnqueue": False,
            "workerStart": False,
            "modelDownload": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "ragIndexing": False,
            "embeddingGeneration": False,
            "cloudTrainingJob": False,
            "fineTuningJob": False,
            "benchmarkRun": False,
            "codeModification": False,
            "branchCreate": False,
            "commit": False,
            "push": False,
            "deployment": False,
        },
    }


def _payload_summary_for_job(
    *,
    job: dict[str, Any],
    rag_indexing_plan: dict[str, Any],
    cloud_handoff_plan: dict[str, Any],
    preload_plan: dict[str, Any],
) -> dict[str, Any]:
    job_type = str(job.get("type") or "")
    if job_type == "rag_indexing":
        return {
            "sourcePlan": "ragIndexingPlan",
            "sourceCount": _as_dict(rag_indexing_plan.get("summary")).get("sourceCount"),
            "readyToIndexCount": rag_indexing_plan.get("readyToIndexCount"),
            "estimatedChunkCount": _as_dict(rag_indexing_plan.get("summary")).get("estimatedChunkCount"),
            "rawSourceContentIncluded": False,
        }
    if job_type == "cloud_training_job":
        target = _as_dict(cloud_handoff_plan.get("target"))
        return {
            "sourcePlan": "cloudHandoffPlan",
            "targetId": target.get("id"),
            "exportFormat": target.get("exportFormat"),
            "readyToExport": cloud_handoff_plan.get("readyToExport"),
            "artifactCount": len(_as_list(cloud_handoff_plan.get("artifactManifest"))),
            "rawSecretsIncluded": False,
            "datasetUploadPlannedOnly": True,
        }
    if job_type == "model_preload":
        target = _as_dict(preload_plan.get("target"))
        return {
            "sourcePlan": "preloadPlan",
            "targetModelId": target.get("modelId"),
            "modelRole": target.get("modelRole"),
            "willLoadModel": False,
        }
    return {
        "sourcePlan": job.get("sourcePlan"),
        "rawPayloadIncluded": False,
    }


def _spec_for_job(
    *,
    job: dict[str, Any],
    project_id: str | None,
    rag_indexing_plan: dict[str, Any],
    cloud_handoff_plan: dict[str, Any],
    preload_plan: dict[str, Any],
) -> dict[str, Any]:
    queue = _queue(str(job.get("queueId") or "none"))
    job_id = str(job.get("id") or "job")
    job_type = str(job.get("type") or job_id)
    idempotency_key = f"cognix:{project_id or 'global'}:{job_type}:{_stable_key(job_id, project_id, job.get('sourcePlan'))}"
    required_gates = [str(item) for item in _as_list(job.get("requiredGates")) if item]
    source_plan_status = "planned"
    if job_type == "rag_indexing":
        source_plan_status = str(rag_indexing_plan.get("status") or "planned")
    elif job_type == "cloud_training_job":
        source_plan_status = str(cloud_handoff_plan.get("status") or "planned")

    return {
        "specVersion": COGNIX_WORKER_JOB_SPEC_VERSION,
        "jobId": job_id,
        "jobType": job_type,
        "queueId": queue.get("id"),
        "queueLabel": queue.get("label"),
        "idempotencyKey": idempotency_key,
        "status": "spec_ready",
        "priority": int(job.get("priority") or 0),
        "sourcePlan": job.get("sourcePlan"),
        "sourcePlanStatus": source_plan_status,
        "requiredGates": required_gates,
        "requiresAudit": True,
        "requiresRateLimit": True,
        "requiresHumanConfirmation": bool(job.get("requiresHumanConfirmation") or queue.get("requiresHumanConfirmation")),
        "payloadSummary": _payload_summary_for_job(
            job = job,
            rag_indexing_plan = rag_indexing_plan,
            cloud_handoff_plan = cloud_handoff_plan,
            preload_plan = preload_plan,
        ),
        "willEnqueue": False,
        "willStartWorker": False,
        "willExecute": False,
    }


def build_worker_job_spec_plan(
    *,
    objective: str,
    project_id: str | None = None,
    worker_queue_plan: dict[str, Any] | None = None,
    rag_indexing_plan: dict[str, Any] | None = None,
    cloud_handoff_plan: dict[str, Any] | None = None,
    preload_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    worker_queue_plan = _as_dict(worker_queue_plan)
    rag_indexing_plan = _as_dict(rag_indexing_plan)
    cloud_handoff_plan = _as_dict(cloud_handoff_plan)
    preload_plan = _as_dict(preload_plan)
    jobs = [item for item in _as_list(worker_queue_plan.get("jobs")) if isinstance(item, dict)]
    existing_job_ids = {str(job.get("id") or "") for job in jobs}

    if rag_indexing_plan and "rag_indexing" not in existing_job_ids:
        jobs.append(
            _job(
                job_id = "rag_indexing",
                job_type = "rag_indexing",
                queue_id = "io_bound",
                label = "Indexer les sources RAG",
                reason = "Plan d'indexation RAG fourni au handoff worker.",
                priority = 86,
                required_gates = ["sources_present", "permissions_checked", "embedding_runtime_ready", "human_approval"],
                source_plan = "ragIndexingPlan",
                requires_human_confirmation = True,
            )
        )
    if cloud_handoff_plan and cloud_handoff_plan.get("readyToExport") and "cloud_training_job" not in existing_job_ids:
        jobs.append(
            _job(
                job_id = "cloud_training_job",
                job_type = "cloud_training_job",
                queue_id = "cloud_training",
                label = "Preparer un training cloud guide",
                reason = "Plan de handoff cloud fourni au handoff worker.",
                priority = 84 if cloud_handoff_plan.get("readyToExport") else 66,
                required_gates = ["dataset_validation", "cloud_handoff_export", "secret_review", "budget_limit", "human_approval"],
                source_plan = "cloudHandoffPlan",
                requires_human_confirmation = True,
            )
        )

    jobs = sorted(jobs, key = lambda item: int(item.get("priority") or 0), reverse = True)
    specs = [
        _spec_for_job(
            job = job,
            project_id = project_id,
            rag_indexing_plan = rag_indexing_plan,
            cloud_handoff_plan = cloud_handoff_plan,
            preload_plan = preload_plan,
        )
        for job in jobs
    ]
    return {
        "workerQueueVersion": COGNIX_WORKER_QUEUE_VERSION,
        "jobSpecVersion": COGNIX_WORKER_JOB_SPEC_VERSION,
        "mode": "dry_run",
        "objectiveExcerpt": _objective_excerpt(objective),
        "projectId": project_id,
        "jobSpecs": specs,
        "summary": {
            "jobSpecCount": len(specs),
            "jobTypes": [str(spec.get("jobType")) for spec in specs],
            "requiresHumanConfirmation": any(bool(spec.get("requiresHumanConfirmation")) for spec in specs),
            "safeToEnqueueAutomatically": False,
            "idempotencyKeys": [str(spec.get("idempotencyKey")) for spec in specs],
        },
        "policies": {
            "frontendDirectQueueMutationAllowed": False,
            "jobSpecsRequireApproval": True,
            "idempotencyKeyRequired": True,
            "rawPayloadStorageAllowed": False,
            "secretValuesAllowed": False,
            "backgroundExecutionAllowedFromPlanner": False,
        },
        "blockedActions": [
            {
                "id": "job_enqueue",
                "reason": "Les specs sont preparees sans enqueue.",
            },
            {
                "id": "worker_start",
                "reason": "Aucun worker n'est demarre par le handoff.",
            },
            {
                "id": "side_effect_execution",
                "reason": "Indexation, training, preload, benchmark et code restent bloques.",
            },
        ],
        "sideEffects": {
            "jobEnqueue": False,
            "workerStart": False,
            "jobPersist": False,
            "modelDownload": False,
            "modelLoad": False,
            "ragIndexing": False,
            "embeddingGeneration": False,
            "cloudTrainingJob": False,
            "fineTuningJob": False,
            "benchmarkRun": False,
            "codeModification": False,
            "deployment": False,
        },
    }
