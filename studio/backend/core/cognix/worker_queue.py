# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX worker queue planning.

This module plans long-running background work without enqueueing jobs,
starting workers, downloading models, indexing documents, training adapters,
running benchmarks, or changing code.
"""

from __future__ import annotations

from typing import Any


COGNIX_WORKER_QUEUE_VERSION = "cognix_worker_queue_v1"

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
        jobs.append(
            _job(
                job_id = "fine_tuning_job",
                job_type = "fine_tuning_job",
                queue_id = "gpu_long_running",
                label = "Preparer un fine-tuning guide",
                reason = (
                    "Dataset et methode prets pour demande d'approbation."
                    if ready
                    else "Fine-tuning detecte mais validation dataset ou materiel encore incomplete."
                ),
                priority = 82 if ready else 68,
                required_gates = ["dataset_validation", "resource_estimate", "human_approval"],
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
            "fineTuningJob": False,
            "benchmarkRun": False,
            "codeModification": False,
            "branchCreate": False,
            "commit": False,
            "push": False,
            "deployment": False,
        },
    }
