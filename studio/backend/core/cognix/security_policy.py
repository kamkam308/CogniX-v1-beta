# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native execution security policy.

The policy layer is intentionally declarative. It does not execute tools, load
models, index documents, or modify code; it gives the orchestrator a stable
contract for what remains blocked until a dedicated guarded executor exists.
"""

from __future__ import annotations

from typing import Any


COGNIX_SECURITY_POLICY_VERSION = "cognix_security_policy_v1"


PATH_RISK_LEVELS = {
    "expert_chat": "low",
    "rag_first": "medium",
    "tool_plan": "medium",
    "guided_fine_tuning": "high",
    "codex_guarded_pipeline": "high",
}

SENSITIVE_PATHS = {
    "tool_plan",
    "guided_fine_tuning",
    "codex_guarded_pipeline",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _path(task_strategy: dict[str, Any]) -> str:
    candidate = str(task_strategy.get("path") or "expert_chat")
    return candidate if candidate in PATH_RISK_LEVELS else "expert_chat"


def _allowed_actions(path: str) -> list[str]:
    actions = [
        "classify_objective",
        "recommend_model",
        "build_context_plan",
        "write_audit_log",
    ]
    if path == "rag_first":
        actions.append("plan_rag_retrieval")
    elif path == "tool_plan":
        actions.append("plan_tool_action")
    elif path == "guided_fine_tuning":
        actions.append("estimate_training")
    elif path == "codex_guarded_pipeline":
        actions.append("plan_codex_pipeline")
    return actions


def _blocked_actions(path: str, readiness: str) -> list[dict[str, str]]:
    blocked = [
        {
            "id": "model_load",
            "reason": "Dry-run actif: le chargement modele reste bloque par l'orchestrateur.",
        },
        {
            "id": "generation",
            "reason": "Aucun token n'est genere pendant la phase de planification.",
        },
        {
            "id": "frontend_direct_model_call",
            "reason": "Le frontend doit passer par le backend et l'orchestrateur CogniX.",
        },
    ]
    if readiness not in {"ready", "ready_with_caution"}:
        blocked.append(
            {
                "id": "runtime_execution",
                "reason": "Le provider ou le modele recommande n'est pas pret pour execution.",
            }
        )
    if path == "rag_first":
        blocked.append(
            {
                "id": "rag_indexing",
                "reason": "L'indexation RAG necessite un executor dedie et audite.",
            }
        )
    elif path == "tool_plan":
        blocked.append(
            {
                "id": "tool_execution",
                "reason": "Les outils restent en planification jusqu'aux permissions et confirmations.",
            }
        )
    elif path == "guided_fine_tuning":
        blocked.append(
            {
                "id": "fine_tuning_job",
                "reason": "Les jobs d'entrainement exigent validation dataset, ressources et confirmation.",
            }
        )
    elif path == "codex_guarded_pipeline":
        blocked.append(
            {
                "id": "code_modification",
                "reason": "Les modifications code passent par le pipeline Codex securise.",
            }
        )
    return blocked


def build_execution_policy(
    *,
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    path = _path(task_strategy)
    uses = _as_dict(task_strategy.get("uses"))
    readiness = str(recommendation.get("readiness") or "unknown")
    risk_level = PATH_RISK_LEVELS[path]
    requires_confirmation = bool(task_strategy.get("requiresHumanConfirmation")) or path in SENSITIVE_PATHS
    requires_rate_limit = path in SENSITIVE_PATHS or bool(uses.get("tools"))
    sandbox_required = path in {"guided_fine_tuning", "codex_guarded_pipeline"} or bool(uses.get("tools"))
    needs_clarification = bool(classification.get("needsClarification"))

    blocked_actions = _blocked_actions(path, readiness)
    if needs_clarification:
        blocked_actions.append(
            {
                "id": "automatic_routing",
                "reason": "Domaine ambigu: CogniX garde l'execution automatique bloquee.",
            }
        )

    return {
        "policyVersion": COGNIX_SECURITY_POLICY_VERSION,
        "mode": "dry_run_guarded",
        "riskLevel": risk_level,
        "planningAllowed": True,
        "automaticExecutionAllowed": False,
        "requiresHumanConfirmation": requires_confirmation,
        "requiresAudit": True,
        "requiresRateLimit": requires_rate_limit,
        "guardrails": {
            "frontendDirectModelCallAllowed": False,
            "frontendDirectToolExecutionAllowed": False,
            "secretsStayServerSide": True,
            "auditRequired": True,
            "rateLimitRequired": requires_rate_limit,
            "sandboxRequired": sandbox_required,
            "cacheEvictionObserveOnly": str(_as_dict(cache.get("policy")).get("mode") or "") != "execute",
        },
        "allowedActions": _allowed_actions(path),
        "blockedActions": blocked_actions,
        "deniedSideEffects": {
            "modelLoad": True,
            "generation": True,
            "networkModelCall": True,
            "toolExecution": True,
            "ragIndexing": True,
            "fineTuningJob": True,
            "codeModification": True,
        },
        "reason": (
            "CogniX autorise uniquement la planification auditee; toute execution reste bloquee."
            if requires_confirmation or needs_clarification
            else "CogniX conserve un mode planification auditee avant le runtime d'execution."
        ),
    }
