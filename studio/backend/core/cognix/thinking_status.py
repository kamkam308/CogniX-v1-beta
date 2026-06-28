# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX user-visible thinking status planning.

This module translates technical orchestration plans into a clean UI-facing
timeline. It deliberately hides model identifiers, routing scores, cache keys,
runtime internals, and policy details from the visible messages.
"""

from __future__ import annotations

from typing import Any


COGNIX_THINKING_STATUS_VERSION = "cognix_thinking_status_v1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _objective_excerpt(value: Any) -> str:
    return " ".join(str(value or "").split())[:500]


def _visibility_status(
    *,
    classification: dict[str, Any],
    recommendation: dict[str, Any],
    model_lifecycle_plan: dict[str, Any],
) -> str:
    if classification.get("needsClarification"):
        return "needs_clarification"
    fit = _as_dict(_as_dict(model_lifecycle_plan.get("compatibility")).get("fit"))
    if fit.get("status") == "blocked":
        return "blocked"
    readiness = str(recommendation.get("readiness") or "unknown")
    if readiness in {"setup_required", "service_unreachable", "model_missing"}:
        return "needs_setup"
    if _as_dict(model_lifecycle_plan.get("installPlan")).get("required"):
        return "model_preparation_required"
    return "ready"


def _current_message(status: str) -> str:
    return {
        "ready": "Pret a repondre.",
        "model_preparation_required": "Preparation du modele local requise avant reponse.",
        "needs_setup": "Configuration locale a terminer avant reponse.",
        "needs_clarification": "Precision necessaire avant de choisir la meilleure strategie.",
        "blocked": "Execution locale bloquee par le profil actuel.",
    }.get(status, "Analyse en cours.")


def _timeline_status(status: str, step_id: str) -> str:
    if step_id in {"analyze_request", "choose_strategy"}:
        return "attention" if status == "needs_clarification" and step_id == "analyze_request" else "complete"
    if step_id == "prepare_model":
        return "attention" if status in {"needs_setup", "model_preparation_required", "blocked"} else "complete"
    if step_id in {"prepare_context", "check_permissions"}:
        return "waiting" if status in {"needs_setup", "blocked"} else "complete"
    if step_id == "ready_to_answer":
        return "ready" if status == "ready" else "waiting"
    return "waiting"


def _prepare_model_detail(status: str, model_lifecycle_plan: dict[str, Any]) -> str:
    load_action = str(_as_dict(model_lifecycle_plan.get("loadPlan")).get("action") or "")
    if status == "ready":
        return "Modele adapte selectionne."
    if status == "model_preparation_required":
        return "Modele adapte selectionne, preparation requise."
    if status == "needs_setup":
        return "Runtime local a finaliser."
    if status == "blocked":
        return "Profil local insuffisant pour cette execution."
    if load_action.startswith("defer"):
        return "Chargement reporte."
    return "Preparation du modele."


def _progress_for_status(status: str) -> int:
    return {
        "ready": 100,
        "model_preparation_required": 62,
        "needs_setup": 48,
        "needs_clarification": 32,
        "blocked": 20,
    }.get(status, 25)


def _visible_timeline(
    *,
    status: str,
    task_strategy: dict[str, Any],
    model_lifecycle_plan: dict[str, Any],
    rag_plan: dict[str, Any],
    project_expert_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    project_mode = str(project_expert_plan.get("projectMode") or "standard")
    rag_path = str(rag_plan.get("recommendedPath") or "no_rag_needed")
    strategy_label = str(task_strategy.get("label") or "Strategie CogniX")
    return [
        {
            "id": "analyze_request",
            "label": "Analyse de la demande",
            "status": _timeline_status(status, "analyze_request"),
            "detail": "Objectif compris et classe.",
        },
        {
            "id": "choose_strategy",
            "label": "Choix de la strategie",
            "status": _timeline_status(status, "choose_strategy"),
            "detail": strategy_label,
        },
        {
            "id": "prepare_model",
            "label": "Preparation du modele adapte",
            "status": _timeline_status(status, "prepare_model"),
            "detail": _prepare_model_detail(status, model_lifecycle_plan),
        },
        {
            "id": "prepare_context",
            "label": "Preparation du contexte",
            "status": _timeline_status(status, "prepare_context"),
            "detail": "Contexte projet prepare." if project_mode != "standard" else "Contexte recent prepare.",
        },
        {
            "id": "check_permissions",
            "label": "Verification des permissions",
            "status": _timeline_status(status, "check_permissions"),
            "detail": "Garde-fous appliques.",
        },
        {
            "id": "ready_to_answer",
            "label": "Reponse",
            "status": _timeline_status(status, "ready_to_answer"),
            "detail": "Pret avec documents utiles." if rag_path == "rag_first" else _current_message(status),
        },
    ]


def build_thinking_status_plan(
    *,
    objective: str,
    classification: dict[str, Any],
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    model_lifecycle_plan: dict[str, Any],
    context_plan: dict[str, Any],
    rag_plan: dict[str, Any],
    project_expert_plan: dict[str, Any],
    execution_policy: dict[str, Any],
    audience: str | None = None,
) -> dict[str, Any]:
    status = _visibility_status(
        classification = classification,
        recommendation = recommendation,
        model_lifecycle_plan = model_lifecycle_plan,
    )
    timeline = _visible_timeline(
        status = status,
        task_strategy = task_strategy,
        model_lifecycle_plan = model_lifecycle_plan,
        rag_plan = rag_plan,
        project_expert_plan = project_expert_plan,
    )
    hidden_fields = [
        "modelId",
        "selectedModelId",
        "routingScores",
        "cacheResidentModels",
        "providerBaseUrl",
        "rawHistory",
        "policyInternals",
    ]
    return {
        "thinkingStatusVersion": COGNIX_THINKING_STATUS_VERSION,
        "mode": "dry_run",
        "audience": audience or "chat",
        "objectiveExcerpt": _objective_excerpt(objective),
        "status": status,
        "currentMessage": _current_message(status),
        "progress": _progress_for_status(status),
        "visibleTimeline": timeline,
        "visibleSummary": {
            "domain": classification.get("label") or classification.get("selectedDomain") or "General",
            "strategy": task_strategy.get("label") or task_strategy.get("path") or "CogniX",
            "contextReady": bool(context_plan),
            "ragPrepared": str(rag_plan.get("recommendedPath") or "") in {"rag_first", "hybrid"},
            "guarded": True,
        },
        "displayContract": {
            "frontendMayShowOnlyTimeline": True,
            "frontendMustHideRawRoutingScores": True,
            "frontendMustHideModelIdentifiers": True,
            "frontendMustHideCacheInternals": True,
            "technicalDetailsAvailableOnlyInAudit": True,
        },
        "redaction": {
            "hiddenTechnicalFields": hidden_fields,
            "visibleTimelineContainsModelIds": False,
            "visibleTimelineContainsRoutingScores": False,
            "visibleTimelineContainsRawHistory": False,
        },
        "policySummary": {
            "automaticExecutionAllowed": bool(execution_policy.get("automaticExecutionAllowed")),
            "frontendDirectModelCallAllowed": False,
            "requiresBackendOrchestrator": True,
        },
        "warnings": [
            item
            for item in _as_list(model_lifecycle_plan.get("warnings"))
            if isinstance(item, str) and item
        ],
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "cacheMutation": False,
            "memoryWrite": False,
            "ragRetrieval": False,
            "uiMutation": False,
        },
    }
