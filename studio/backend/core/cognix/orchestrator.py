# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native orchestration planning.

The MVP orchestrator is deliberately dry-run only: it explains how CogniX would
route a request, which local runtime it would prefer, and what cache policy
applies, without loading a model or generating tokens.
"""

from __future__ import annotations

import re
from typing import Any

from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import context_manager as cognix_context_manager
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import fine_tuning_planner as cognix_fine_tuning_planner
from core.cognix import hardware as cognix_hardware
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import preload_planner as cognix_preload_planner
from core.cognix import project_experts as cognix_project_experts
from core.cognix import rag_planner as cognix_rag_planner
from core.cognix import recommender as cognix_recommender
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import security_policy as cognix_security_policy
from core.cognix import worker_queue as cognix_worker_queue
from core.cognix.router import classify_objective


def _objective_excerpt(objective: str) -> str:
    return re.sub(r"\s+", " ", objective or "").strip()[:500]


def _runtime_snapshot_value(
    runtime_snapshot: dict[str, Any] | None,
    key: str,
    default: Any,
) -> Any:
    if not isinstance(runtime_snapshot, dict):
        return default
    value = runtime_snapshot.get(key)
    return default if value is None else value


def _execution_status(
    *,
    classification: dict[str, Any],
    recommendation: dict[str, Any],
) -> str:
    readiness = str(recommendation.get("readiness") or "unknown")
    if classification.get("needsClarification"):
        return "needs_clarification"
    if readiness in {"ready", "ready_with_caution"}:
        return "ready"
    if readiness in {"setup_required", "service_unreachable", "model_missing"}:
        return "needs_setup"
    return "blocked"


def _execution_reason(
    *,
    status: str,
    classification: dict[str, Any],
    recommendation: dict[str, Any],
) -> str:
    if status == "needs_clarification":
        return "CogniX a detecte plusieurs domaines proches et gardera la main sur la clarification."
    if status == "ready":
        return "CogniX peut preparer cette demande sur le runtime local recommande, sans auto-load en dry-run."
    if status == "needs_setup":
        return str(
            recommendation.get("reason")
            or "CogniX doit terminer la configuration du provider ou du modele local avant execution."
        )
    return str(
        recommendation.get("reason")
        or "CogniX ne peut pas executer cette demande localement avec l'etat actuel."
    )


def _warnings(
    *,
    classification: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any],
    task_strategy: dict[str, Any],
    codex_pipeline_plan: dict[str, Any],
    rag_plan: dict[str, Any],
    context_plan: dict[str, Any],
    optimization_plan: dict[str, Any],
    runtime_adapter_plan: dict[str, Any],
    preload_plan: dict[str, Any],
    project_expert_plan: dict[str, Any],
    fine_tuning_plan: dict[str, Any],
    worker_queue_plan: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if classification.get("needsClarification"):
        warnings.append("Domaine ambigu: clarification conseillee avant execution automatique.")
    for item in recommendation.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    next_action = cache.get("nextAction") if isinstance(cache, dict) else None
    if isinstance(next_action, dict) and str(next_action.get("type") or "").startswith("would_unload"):
        warnings.append(str(next_action.get("reason") or "Le cache local proposera une eviction."))
    for item in task_strategy.get("risks") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in codex_pipeline_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in rag_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in context_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in optimization_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in runtime_adapter_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in preload_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in project_expert_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in fine_tuning_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)
    for item in worker_queue_plan.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in warnings:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _steps(
    *,
    classification: dict[str, Any],
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any],
    codex_pipeline_plan: dict[str, Any],
    rag_plan: dict[str, Any],
    context_plan: dict[str, Any],
    optimization_plan: dict[str, Any],
    runtime_adapter_plan: dict[str, Any],
    preload_plan: dict[str, Any],
    project_expert_plan: dict[str, Any],
    fine_tuning_plan: dict[str, Any],
    worker_queue_plan: dict[str, Any],
    execution_policy: dict[str, Any],
    status: str,
) -> list[dict[str, Any]]:
    cache_policy = cache.get("policy") if isinstance(cache, dict) else {}
    return [
        {
            "id": "classify_objective",
            "label": "Classer l'objectif",
            "status": "complete",
            "detail": (
                f"Domaine {classification.get('label', 'General')} "
                f"via {classification.get('routingMode', 'unknown')}."
            ),
        },
        {
            "id": "choose_task_strategy",
            "label": "Choisir la strategie IA",
            "status": "complete",
            "detail": (
                f"{task_strategy.get('label', 'Strategie CogniX')} "
                f"via {task_strategy.get('primaryCapability', 'orchestrator')}."
            ),
        },
        {
            "id": "select_runtime",
            "label": "Choisir le runtime",
            "status": "complete",
            "detail": (
                f"{recommendation.get('providerName') or 'Provider local'} / "
                f"{recommendation.get('modelLabel') or recommendation.get('modelId') or 'modele local'}."
            ),
        },
        {
            "id": "select_runtime_adapter",
            "label": "Choisir l'adapter runtime",
            "status": "complete",
            "detail": str(
                runtime_adapter_plan.get("reason")
                or "Adapter runtime selectionne sans mutation de serveur."
            ),
        },
        {
            "id": "plan_codex_pipeline",
            "label": "Planifier pipeline Codex",
            "status": "complete",
            "detail": str(
                codex_pipeline_plan.get("reason")
                or "Pipeline Codex observe uniquement: aucune modification code."
            ),
        },
        {
            "id": "check_cache",
            "label": "Verifier le cache modele",
            "status": "complete",
            "detail": str(
                cache_policy.get("reason")
                or "Cache observe en mode lecture: aucune eviction automatique."
            ),
        },
        {
            "id": "plan_rag",
            "label": "Planifier RAG",
            "status": "complete",
            "detail": str(
                rag_plan.get("reason")
                or "RAG observe uniquement: aucune indexation ni recherche."
            ),
        },
        {
            "id": "plan_context",
            "label": "Construire le contexte",
            "status": "complete",
            "detail": str(
                context_plan.get("reason")
                or "Contexte observe uniquement: aucune memoire ecrite ni retrieval execute."
            ),
        },
        {
            "id": "plan_optimizations",
            "label": "Planifier optimisations",
            "status": "complete",
            "detail": str(
                optimization_plan.get("reason")
                or "Optimisations observees uniquement: aucune reconfiguration runtime."
            ),
        },
        {
            "id": "plan_preload",
            "label": "Planifier le prechargement",
            "status": "complete",
            "detail": str(
                preload_plan.get("reason")
                or "Prechargement observe uniquement: aucun modele charge."
            ),
        },
        {
            "id": "plan_project_expert",
            "label": "Planifier l'expert projet",
            "status": "complete",
            "detail": str(
                project_expert_plan.get("reason")
                or "Expert projet observe uniquement: aucun modele charge."
            ),
        },
        {
            "id": "plan_fine_tuning",
            "label": "Evaluer fine-tuning",
            "status": "complete",
            "detail": str(
                fine_tuning_plan.get("reason")
                or "Fine-tuning observe uniquement: aucun job lance."
            ),
        },
        {
            "id": "plan_worker_queue",
            "label": "Planifier workers",
            "status": "complete",
            "detail": str(
                worker_queue_plan.get("reason")
                or "Workers observes uniquement: aucun job enfile ni demarre."
            ),
        },
        {
            "id": "apply_execution_policy",
            "label": "Appliquer les garde-fous",
            "status": "complete",
            "detail": str(
                execution_policy.get("reason")
                or "Politique CogniX active en mode planification securisee."
            ),
        },
        {
            "id": "dry_run_guard",
            "label": "Bloquer le lancement automatique",
            "status": "complete",
            "detail": "Dry-run actif: aucun modele charge, aucun token genere.",
        },
        {
            "id": "execution_ready",
            "label": "Etat d'execution",
            "status": status,
            "detail": _execution_reason(
                status = status,
                classification = classification,
                recommendation = recommendation,
            ),
        },
    ]


def build_execution_plan(
    objective: str,
    *,
    current_subject: str,
    project_type: str | None = None,
    project_id: str | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    rag_sources: list[dict[str, Any]] | None = None,
    rag_available: bool | None = None,
    fine_tuning_dataset: dict[str, Any] | None = None,
    user_plan: str | None = None,
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark_run,
    )
    recommendation = recommendation_payload["recommendation"]
    classification = classify_objective(objective, project_type = project_type)
    task_strategy = cognix_decision_engine.build_task_strategy(
        objective,
        classification = classification,
        project_type = project_type,
    )
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = _runtime_snapshot_value(runtime_snapshot, "activeModel", None),
        loaded_models = _runtime_snapshot_value(runtime_snapshot, "loadedModels", []),
        loading_models = _runtime_snapshot_value(runtime_snapshot, "loadingModels", []),
        runtime_type = str(_runtime_snapshot_value(runtime_snapshot, "runtimeType", "unknown")),
        project_id = project_id,
    )
    rag_plan = cognix_rag_planner.build_rag_plan(
        objective = objective,
        project_id = project_id,
        classification = classification,
        task_strategy = task_strategy,
        recommendation = recommendation,
        sources = rag_sources,
        rag_available = rag_available,
    )
    context_plan = cognix_context_manager.build_context_plan(
        current_subject = current_subject,
        objective = objective,
        project_id = project_id,
        classification = classification,
        task_strategy = task_strategy,
        recommendation = recommendation,
        rag_plan = rag_plan,
    )
    optimization_plan = cognix_optimization_planner.build_optimization_plan(
        hardware = hardware,
        recommendation = recommendation,
        cache = cache,
        context_plan = context_plan,
        rag_plan = rag_plan,
        task_strategy = task_strategy,
        latest_benchmark_run = latest_benchmark_run,
    )
    fine_tuning_plan = cognix_fine_tuning_planner.build_fine_tuning_plan(
        objective = objective,
        classification = classification,
        task_strategy = task_strategy,
        recommendation = recommendation,
        hardware = hardware,
        dataset = fine_tuning_dataset,
        latest_benchmark_run = latest_benchmark_run,
        user_plan = user_plan,
    )
    runtime_adapter_plan = cognix_runtime_adapter.build_runtime_adapter_plan(
        recommendation = recommendation,
        hardware = hardware,
        task_strategy = task_strategy,
        rag_plan = rag_plan,
        fine_tuning_plan = fine_tuning_plan,
        optimization_plan = optimization_plan,
    )
    preload_plan = cognix_preload_planner.build_preload_plan(
        objective = objective,
        project_type = project_type,
        project_id = project_id,
        classification = classification,
        task_strategy = task_strategy,
        recommendation = recommendation,
        cache = cache,
        latest_benchmark_run = latest_benchmark_run,
    )
    project_expert_plan = cognix_project_experts.build_project_expert_plan(
        objective = objective,
        project_id = project_id,
        project_type = project_type,
        project_default_model = None,
        classification = classification,
        recommendation = recommendation,
        preload_plan = preload_plan,
        rag_plan = rag_plan,
        context_plan = context_plan,
    )
    status = _execution_status(
        classification = classification,
        recommendation = recommendation,
    )
    execution_policy = cognix_security_policy.build_execution_policy(
        task_strategy = task_strategy,
        recommendation = recommendation,
        cache = cache,
        classification = classification,
    )
    codex_pipeline_plan = cognix_codex_pipeline.build_codex_pipeline_plan(
        objective = objective,
        current_subject = current_subject,
        project_id = project_id,
        classification = classification,
        task_strategy = task_strategy,
        execution_policy = execution_policy,
    )
    worker_queue_plan = cognix_worker_queue.build_worker_queue_plan(
        objective = objective,
        project_id = project_id,
        task_strategy = task_strategy,
        rag_plan = rag_plan,
        fine_tuning_plan = fine_tuning_plan,
        preload_plan = preload_plan,
        codex_pipeline_plan = codex_pipeline_plan,
        optimization_plan = optimization_plan,
        latest_benchmark_run = latest_benchmark_run,
    )

    execution_strategy = {
        "status": status,
        "executionMode": recommendation.get("executionMode"),
        "providerId": recommendation.get("providerId"),
        "providerType": recommendation.get("providerType"),
        "providerName": recommendation.get("providerName"),
        "baseUrl": recommendation.get("baseUrl"),
        "selectedModelId": recommendation.get("modelId"),
        "selectedModelLabel": recommendation.get("modelLabel"),
        "domainModelLabel": classification.get("recommendedModelLabel"),
        "recommendedPath": task_strategy.get("path"),
        "primaryCapability": task_strategy.get("primaryCapability"),
        "requiresHumanConfirmation": task_strategy.get("requiresHumanConfirmation"),
        "automaticExecutionAllowed": execution_policy.get("automaticExecutionAllowed"),
        "securityRiskLevel": execution_policy.get("riskLevel"),
        "preloadAction": (preload_plan.get("actions") or [{}])[0].get("type"),
        "preloadTargetModelId": preload_plan.get("target", {}).get("modelId"),
        "projectExpertId": project_expert_plan.get("primaryExpert", {}).get("expertId"),
        "projectExpertDomain": project_expert_plan.get("primaryExpert", {}).get("domain"),
        "projectExpertModelId": project_expert_plan.get("primaryExpert", {}).get("selectedModel", {}).get("modelId"),
        "secondaryExpertIds": [
            item.get("expertId")
            for item in project_expert_plan.get("secondaryExperts", [])
            if isinstance(item, dict)
        ],
        "generalistVerifierEnabled": project_expert_plan.get("generalistVerifier", {}).get("enabled"),
        "ragReadyForRetrieval": rag_plan.get("readyForRetrieval"),
        "ragStrategy": rag_plan.get("retrieval", {}).get("strategy"),
        "contextAssemblyStrategy": context_plan.get("assemblyStrategy"),
        "maxContextTokens": context_plan.get("tokenBudget", {}).get("maxContextTokens"),
        "rawHistoryAllowed": context_plan.get("tokenBudget", {}).get("rawHistoryAllowed"),
        "optimizationProfile": optimization_plan.get("optimizationProfile"),
        "optimizationHardwareTier": optimization_plan.get("hardwareTier"),
        "runtimeAdapterId": runtime_adapter_plan.get("selectedAdapter", {}).get("adapterId"),
        "runtimeAdapterType": runtime_adapter_plan.get("selectedAdapter", {}).get("runtimeType"),
        "codexPipelineApplicable": codex_pipeline_plan.get("applicable"),
        "codexBranchName": codex_pipeline_plan.get("branch", {}).get("recommendedName"),
        "workerQueueRecommended": bool(worker_queue_plan.get("jobs")),
        "workerQueueId": worker_queue_plan.get("recommendedQueue", {}).get("id"),
        "plannedWorkerJobCount": worker_queue_plan.get("summary", {}).get("plannedJobCount"),
        "fineTuningMethod": fine_tuning_plan.get("method", {}).get("type"),
        "fineTuningReadyToRequestApproval": fine_tuning_plan.get("approval", {}).get("readyToRequest"),
        "uses": task_strategy.get("uses"),
        "requiresModelLoad": not bool(cache.get("runtime", {}).get("activeModel")),
        "willLoadModel": False,
        "willGenerate": False,
        "reason": _execution_reason(
            status = status,
            classification = classification,
            recommendation = recommendation,
        ),
    }

    return {
        "username": current_subject,
        "orchestratorVersion": "cognix_orchestrator_v1",
        "mode": "dry_run",
        "objectiveExcerpt": _objective_excerpt(objective),
        "classification": classification,
        "hardware": hardware,
        "latestBenchmark": latest_benchmark_run,
        "providers": recommendation_payload["providers"],
        "recommendation": recommendation,
        "cache": cache,
        "codexPipelinePlan": codex_pipeline_plan,
        "ragPlan": rag_plan,
        "contextPlan": context_plan,
        "optimizationPlan": optimization_plan,
        "runtimeAdapterPlan": runtime_adapter_plan,
        "preloadPlan": preload_plan,
        "projectExpertPlan": project_expert_plan,
        "fineTuningPlan": fine_tuning_plan,
        "workerQueuePlan": worker_queue_plan,
        "taskStrategy": task_strategy,
        "executionPolicy": execution_policy,
        "executionStrategy": execution_strategy,
        "steps": _steps(
            classification = classification,
            task_strategy = task_strategy,
            recommendation = recommendation,
            cache = cache,
            codex_pipeline_plan = codex_pipeline_plan,
            rag_plan = rag_plan,
            context_plan = context_plan,
            optimization_plan = optimization_plan,
            runtime_adapter_plan = runtime_adapter_plan,
            preload_plan = preload_plan,
            project_expert_plan = project_expert_plan,
            fine_tuning_plan = fine_tuning_plan,
            worker_queue_plan = worker_queue_plan,
            execution_policy = execution_policy,
            status = status,
        ),
        "warnings": _warnings(
            classification = classification,
            recommendation = recommendation,
            cache = cache,
            task_strategy = task_strategy,
            codex_pipeline_plan = codex_pipeline_plan,
            rag_plan = rag_plan,
            context_plan = context_plan,
            optimization_plan = optimization_plan,
            runtime_adapter_plan = runtime_adapter_plan,
            preload_plan = preload_plan,
            project_expert_plan = project_expert_plan,
            fine_tuning_plan = fine_tuning_plan,
            worker_queue_plan = worker_queue_plan,
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
            "ragIndexing": False,
            "ragRetrieval": False,
            "memoryWrite": False,
            "contextMutation": False,
            "modelReconfiguration": False,
            "runtimeMutation": False,
            "serverStart": False,
            "benchmarkRun": False,
            "projectMutation": False,
            "defaultModelWrite": False,
            "fineTuningJob": False,
            "jobEnqueue": False,
            "workerStart": False,
            "codeModification": False,
            "branchCreate": False,
            "commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
            "cacheMode": "observe_only",
        },
    }
