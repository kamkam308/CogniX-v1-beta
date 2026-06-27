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
from core.cognix import hardware as cognix_hardware
from core.cognix import recommender as cognix_recommender
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
    recommendation: dict[str, Any],
    cache: dict[str, Any],
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
            "id": "select_runtime",
            "label": "Choisir le runtime",
            "status": "complete",
            "detail": (
                f"{recommendation.get('providerName') or 'Provider local'} / "
                f"{recommendation.get('modelLabel') or recommendation.get('modelId') or 'modele local'}."
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
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    recommendation_payload = cognix_recommender.build_model_recommendation(hardware)
    recommendation = recommendation_payload["recommendation"]
    classification = classify_objective(objective, project_type = project_type)
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = _runtime_snapshot_value(runtime_snapshot, "activeModel", None),
        loaded_models = _runtime_snapshot_value(runtime_snapshot, "loadedModels", []),
        loading_models = _runtime_snapshot_value(runtime_snapshot, "loadingModels", []),
        runtime_type = str(_runtime_snapshot_value(runtime_snapshot, "runtimeType", "unknown")),
        project_id = project_id,
    )
    status = _execution_status(
        classification = classification,
        recommendation = recommendation,
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
        "providers": recommendation_payload["providers"],
        "recommendation": recommendation,
        "cache": cache,
        "executionStrategy": execution_strategy,
        "steps": _steps(
            classification = classification,
            recommendation = recommendation,
            cache = cache,
            status = status,
        ),
        "warnings": _warnings(
            classification = classification,
            recommendation = recommendation,
            cache = cache,
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "cacheMode": "observe_only",
        },
    }
