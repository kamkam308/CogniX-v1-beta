# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX specialized project expert planning.

Specialized projects are the native contract behind Phase 2 of the roadmap:
Maths, Physics, Code, Business, Research, and Education projects should prefer
their expert model, optionally keep a generalist verifier, reserve project
memory/RAG, and prepare preload/cache actions without mutating project settings
or loading models.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_PROJECT_EXPERTS_VERSION = "cognix_project_experts_v1"
COGNIX_PROJECT_SESSION_CONTRACT_VERSION = "cognix_project_session_contract_v1"

EXPERT_PROFILES: dict[str, dict[str, Any]] = {
    "general": {
        "id": "cognix-general",
        "label": "CogniX General",
        "domain": "general",
        "modelId": "cognix-general-3b-q4",
        "modelLabel": "CogniX General 3B Q4",
        "role": "generalist",
        "supports": ["chat", "synthesis", "verification"],
        "defaultProjectTypes": ["general"],
        "secondaryExpertIds": [],
    },
    "maths": {
        "id": "cognix-maths",
        "label": "CogniX Maths",
        "domain": "maths",
        "modelId": "cognix-maths-3b-q4",
        "modelLabel": "CogniX Maths 3B Q4",
        "role": "math_expert",
        "supports": ["equations", "proofs", "step_by_step"],
        "defaultProjectTypes": ["maths", "math", "mathematiques"],
        "secondaryExpertIds": ["cognix-general"],
    },
    "physique": {
        "id": "cognix-physique",
        "label": "CogniX Physique",
        "domain": "physique",
        "modelId": "cognix-physique-3b-q4",
        "modelLabel": "CogniX Physique 3B Q4",
        "role": "physics_expert",
        "supports": ["mechanics", "energy", "scientific_explanations"],
        "defaultProjectTypes": ["physique", "physics", "science"],
        "secondaryExpertIds": ["cognix-maths", "cognix-general"],
    },
    "code": {
        "id": "cognix-code",
        "label": "CogniX Code",
        "domain": "code",
        "modelId": "cognix-code-4b-q4",
        "modelLabel": "CogniX Code 4B Q4",
        "role": "code_expert",
        "supports": ["debugging", "architecture", "tests"],
        "defaultProjectTypes": ["code", "dev", "developer", "software"],
        "secondaryExpertIds": ["cognix-general"],
    },
    "business": {
        "id": "cognix-business",
        "label": "CogniX Business",
        "domain": "business",
        "modelId": "cognix-business-3b-q4",
        "modelLabel": "CogniX Business 3B Q4",
        "role": "business_expert",
        "supports": ["strategy", "marketing", "analytics"],
        "defaultProjectTypes": ["business", "crm", "sales"],
        "secondaryExpertIds": ["cognix-general"],
    },
    "research": {
        "id": "cognix-research",
        "label": "CogniX Research",
        "domain": "research",
        "modelId": "cognix-research-3b-q4",
        "modelLabel": "CogniX Research 3B Q4",
        "role": "research_expert",
        "supports": ["source_review", "summaries", "comparison"],
        "defaultProjectTypes": ["research", "recherche", "veille"],
        "secondaryExpertIds": ["cognix-general"],
    },
    "education": {
        "id": "cognix-education",
        "label": "CogniX Education",
        "domain": "education",
        "modelId": "cognix-education-3b-q4",
        "modelLabel": "CogniX Education 3B Q4",
        "role": "education_expert",
        "supports": ["lesson_planning", "quizzes", "guided_feedback"],
        "defaultProjectTypes": ["education", "school", "university", "cours"],
        "secondaryExpertIds": ["cognix-general"],
    },
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")


def _objective_excerpt(value: Any) -> str:
    return " ".join(str(value or "").split())[:500]


def _expert_by_id(expert_id: str | None) -> dict[str, Any] | None:
    if not expert_id:
        return None
    normalized = _normalize(expert_id)
    for expert in EXPERT_PROFILES.values():
        if normalized in {_normalize(expert.get("id")), _normalize(expert.get("domain"))}:
            return deepcopy(expert)
    return None


def _domain_from_project_type(project_type: str | None) -> str | None:
    normalized = _normalize(project_type)
    if not normalized:
        return None
    for domain, expert in EXPERT_PROFILES.items():
        aliases = {_normalize(item) for item in expert.get("defaultProjectTypes", [])}
        aliases.add(_normalize(domain))
        if normalized in aliases:
            return domain
    return None


def _classification_domain(classification: dict[str, Any]) -> str:
    domain = _normalize(classification.get("selectedDomain"))
    return domain if domain in EXPERT_PROFILES else "general"


def _select_primary_expert(
    *,
    project_type: str | None,
    classification: dict[str, Any],
    project_default_model: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    project_domain = _domain_from_project_type(project_type)
    if project_domain:
        return deepcopy(EXPERT_PROFILES[project_domain]), "project_type"

    default_model = _as_dict(project_default_model)
    default_label = str(default_model.get("label") or default_model.get("model_id") or default_model.get("modelId") or "")
    default_text = _normalize(default_label)
    for domain, expert in EXPERT_PROFILES.items():
        if domain != "general" and _normalize(domain) in default_text:
            return deepcopy(expert), "project_default_model"

    classified_domain = _classification_domain(classification)
    return deepcopy(EXPERT_PROFILES[classified_domain]), "classification"


def _model_override(expert: dict[str, Any], project_default_model: dict[str, Any] | None) -> dict[str, Any]:
    default_model = _as_dict(project_default_model)
    model_id = default_model.get("model_id") or default_model.get("modelId")
    if not model_id:
        return {
            "modelId": expert.get("modelId"),
            "modelLabel": expert.get("modelLabel"),
            "providerType": None,
            "providerId": None,
            "source": "expert_profile",
            "willWriteDefault": False,
        }
    return {
        "modelId": model_id,
        "modelLabel": default_model.get("label") or expert.get("modelLabel"),
        "providerType": default_model.get("provider_type") or default_model.get("providerType"),
        "providerId": default_model.get("provider_id") or default_model.get("providerId"),
        "source": "project_default_model",
        "willWriteDefault": False,
    }


def _secondary_experts(primary: dict[str, Any], classification: dict[str, Any]) -> list[dict[str, Any]]:
    secondary_ids = [str(item) for item in primary.get("secondaryExpertIds", [])]
    scores = _as_dict(classification.get("scores"))
    primary_domain = _normalize(primary.get("domain"))
    scored_domains = sorted(
        (
            (domain, float(score))
            for domain, score in scores.items()
            if domain in EXPERT_PROFILES and domain not in {primary_domain, "general"}
        ),
        key = lambda item: item[1],
        reverse = True,
    )
    for domain, score in scored_domains[:2]:
        if score >= 0.38:
            secondary_ids.append(str(EXPERT_PROFILES[domain]["id"]))
    if classification.get("needsClarification"):
        secondary_ids.append("cognix-general")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for expert_id in secondary_ids:
        expert = _expert_by_id(expert_id)
        if not expert:
            continue
        normalized = str(expert.get("id"))
        if normalized == primary.get("id") or normalized in seen:
            continue
        seen.add(normalized)
        result.append(
            {
                "expertId": expert.get("id"),
                "label": expert.get("label"),
                "domain": expert.get("domain"),
                "role": expert.get("role"),
                "modelId": expert.get("modelId"),
                "modelLabel": expert.get("modelLabel"),
                "willLoad": False,
            }
        )
    return result


def _preload_intent(preload_plan: dict[str, Any], selected_model: dict[str, Any]) -> dict[str, Any]:
    first_action = (_as_list(preload_plan.get("actions")) or [{}])[0]
    target = _as_dict(preload_plan.get("target"))
    return {
        "actionType": first_action.get("type") or "defer_preload",
        "targetModelId": selected_model.get("modelId") or target.get("modelId"),
        "targetModelLabel": selected_model.get("modelLabel") or target.get("modelLabel"),
        "priority": target.get("priority"),
        "willPreload": False,
        "cacheMutation": False,
        "reason": first_action.get("reason") or preload_plan.get("reason"),
    }


def _project_session_contract(
    *,
    project_id: str | None,
    project_type: str | None,
    project_mode: str,
    primary: dict[str, Any],
    selected_model: dict[str, Any],
    secondary: list[dict[str, Any]],
    use_generalist_verifier: bool,
    classification: dict[str, Any],
    preload_plan: dict[str, Any],
    rag_plan: dict[str, Any],
    context_plan: dict[str, Any],
) -> dict[str, Any]:
    token_budget = _as_dict(context_plan.get("tokenBudget"))
    preload_queue = _as_dict(preload_plan.get("preloadQueueContract"))
    preload_gate = _as_dict(preload_queue.get("executionGate"))
    preload_action = (_as_list(preload_plan.get("actions")) or [{}])[0]
    session_mode = (
        "direct_project_expert"
        if (project_id or project_type) and primary.get("domain") != "general"
        else "router_guided_project"
    )
    startup_sequence = [
        {
            "id": "resolve_project_scope",
            "status": "ready" if project_id or project_type else "optional",
            "sideEffects": {"projectMutation": False},
        },
        {
            "id": "select_primary_expert",
            "status": "ready",
            "expertId": primary.get("id"),
            "modelId": selected_model.get("modelId"),
            "sideEffects": {"modelLoad": False},
        },
        {
            "id": "assemble_project_context",
            "status": "ready",
            "assemblyStrategy": context_plan.get("assemblyStrategy"),
            "rawHistoryAllowed": bool(token_budget.get("rawHistoryAllowed")),
            "sideEffects": {"memoryWrite": False, "ragRetrieval": False},
        },
        {
            "id": "plan_project_preload",
            "status": preload_queue.get("status") or preload_action.get("type") or "deferred",
            "preloadQueueContractVersion": preload_queue.get("contractVersion"),
            "willLoadNow": bool(preload_gate.get("willLoadNow")),
            "sideEffects": {"modelLoad": False, "cacheMutation": False},
        },
    ]
    if use_generalist_verifier:
        startup_sequence.append(
            {
                "id": "attach_generalist_verifier",
                "status": "ready",
                "expertId": "cognix-general",
                "sideEffects": {"modelLoad": False, "generation": False},
            }
        )

    return {
        "contractVersion": COGNIX_PROJECT_SESSION_CONTRACT_VERSION,
        "mode": "project_session_dry_run",
        "sessionMode": session_mode,
        "projectId": project_id,
        "projectType": project_type,
        "projectMode": project_mode,
        "primaryExpertId": primary.get("id"),
        "primaryDomain": primary.get("domain"),
        "primaryModelId": selected_model.get("modelId"),
        "secondaryExpertIds": [item.get("expertId") for item in secondary if isinstance(item, dict)],
        "startupSequence": startup_sequence,
        "routingPolicy": {
            "directPrimaryExpertPreferred": session_mode == "direct_project_expert",
            "lightweightRouterFallbackOnly": True,
            "secondaryExpertAllowed": bool(secondary),
            "generalistVerifierEnabled": use_generalist_verifier,
            "backendOrchestratorRequired": True,
            "frontendDirectModelCallAllowed": False,
            "automaticModelLoadAllowed": False,
        },
        "contextBoundary": {
            "contextManagerVersion": context_plan.get("contextManagerVersion"),
            "assemblyStrategy": context_plan.get("assemblyStrategy"),
            "includedChannelIds": context_plan.get("includedChannelIds", []),
            "maxContextTokens": token_budget.get("maxContextTokens"),
            "rawHistoryAllowed": bool(token_budget.get("rawHistoryAllowed")),
            "projectMemoryRequired": bool(project_id),
            "ragRecommendedPath": rag_plan.get("recommendedPath"),
            "ragStrategy": _as_dict(rag_plan.get("retrieval")).get("strategy"),
            "memoryWriteAllowedNow": False,
            "ragRetrievalAllowedNow": False,
        },
        "preloadBoundary": {
            "preloadAction": preload_action.get("type") or "defer_preload",
            "preloadQueueContractVersion": preload_queue.get("contractVersion"),
            "preloadQueueStatus": preload_queue.get("status"),
            "willLoadNow": bool(preload_gate.get("willLoadNow")),
            "automaticPreloadAllowed": bool(preload_gate.get("automaticPreloadAllowed")),
            "frontendDirectModelLoadAllowed": False,
        },
        "clarification": {
            "required": bool(classification.get("needsClarification")) and not project_type,
            "reason": classification.get("reason"),
        },
        "approvalGates": [
            "project_context_ready",
            "model_residency_policy",
            "user_message_submitted",
        ],
        "blockedActions": [
            "model_load",
            "model_unload",
            "runtime_mutation",
            "cache_mutation",
            "generation",
            "network_model_call",
            "memory_write",
            "rag_retrieval",
            "frontend_direct_model_call",
        ],
        "sideEffects": {
            "modelLoad": False,
            "modelUnload": False,
            "generation": False,
            "networkModelCall": False,
            "projectMutation": False,
            "defaultModelWrite": False,
            "cacheMutation": False,
            "ragRetrieval": False,
            "memoryWrite": False,
        },
    }


def build_project_expert_registry() -> dict[str, Any]:
    experts = []
    for expert in EXPERT_PROFILES.values():
        record = deepcopy(expert)
        record["willLoad"] = False
        experts.append(record)
    return {
        "projectExpertsVersion": COGNIX_PROJECT_EXPERTS_VERSION,
        "mode": "declarative_dry_run",
        "experts": experts,
        "summary": {
            "expertCount": len(experts),
            "specializedExpertCount": len([item for item in experts if item.get("domain") != "general"]),
            "projectDirectRoutingSupported": True,
            "generalistVerifierSupported": True,
            "secondaryExpertsSupported": True,
        },
        "globalPolicies": {
            "specializedProjectsPreferPrimaryExpert": True,
            "directProjectSessionContract": True,
            "fallbackToGeneralist": True,
            "projectMemoryRequired": True,
            "frontendCannotLoadExpertDirectly": True,
            "expertSwitchRequiresBackendOrchestrator": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "projectMutation": False,
            "defaultModelWrite": False,
            "cacheMutation": False,
            "ragRetrieval": False,
            "memoryWrite": False,
        },
    }


def build_project_expert_plan(
    *,
    objective: str,
    project_id: str | None,
    project_type: str | None,
    project_default_model: dict[str, Any] | None,
    classification: dict[str, Any],
    recommendation: dict[str, Any],
    preload_plan: dict[str, Any],
    rag_plan: dict[str, Any],
    context_plan: dict[str, Any],
) -> dict[str, Any]:
    primary, selection_source = _select_primary_expert(
        project_type = project_type,
        classification = classification,
        project_default_model = project_default_model,
    )
    selected_model = _model_override(primary, project_default_model)
    secondary = _secondary_experts(primary, classification)
    project_mode = "specialized_project" if primary.get("domain") != "general" else "general_project"
    use_generalist_verifier = primary.get("domain") != "general"
    rag_required = bool(rag_plan.get("recommendedPath") == "rag_first" or project_id)

    warnings: list[str] = []
    if classification.get("needsClarification") and not project_type:
        warnings.append("Domaine ambigu: utiliser le type de projet ou une clarification avant chargement expert.")
    if selected_model["source"] == "project_default_model" and selected_model.get("modelId") != primary.get("modelId"):
        warnings.append("Modele par defaut projet prioritaire sur le profil expert CogniX.")
    if recommendation.get("readiness") not in {"ready", "ready_with_caution", "model_missing"}:
        warnings.append("Runtime local pas pret: l'expert projet reste en planification.")
    project_session_contract = _project_session_contract(
        project_id = project_id,
        project_type = project_type,
        project_mode = project_mode,
        primary = primary,
        selected_model = selected_model,
        secondary = secondary,
        use_generalist_verifier = use_generalist_verifier,
        classification = classification,
        preload_plan = preload_plan,
        rag_plan = rag_plan,
        context_plan = context_plan,
    )

    return {
        "projectExpertsVersion": COGNIX_PROJECT_EXPERTS_VERSION,
        "mode": "dry_run",
        "objectiveExcerpt": _objective_excerpt(objective),
        "projectId": project_id,
        "projectType": project_type,
        "projectMode": project_mode,
        "selectionSource": selection_source,
        "primaryExpert": {
            "expertId": primary.get("id"),
            "label": primary.get("label"),
            "domain": primary.get("domain"),
            "role": primary.get("role"),
            "supports": primary.get("supports", []),
            "profileModelId": primary.get("modelId"),
            "profileModelLabel": primary.get("modelLabel"),
            "selectedModel": selected_model,
            "willLoad": False,
        },
        "secondaryExperts": secondary,
        "generalistVerifier": {
            "enabled": use_generalist_verifier,
            "expertId": "cognix-general" if use_generalist_verifier else None,
            "purpose": "reformulate_verify_explain" if use_generalist_verifier else "not_needed",
            "willLoad": False,
        },
        "projectMemoryPlan": {
            "projectMemoryRequired": bool(project_id),
            "contextAssemblyStrategy": context_plan.get("assemblyStrategy"),
            "maxContextTokens": _as_dict(context_plan.get("tokenBudget")).get("maxContextTokens"),
            "ragReserved": rag_required,
            "ragStrategy": _as_dict(rag_plan.get("retrieval")).get("strategy"),
            "rawHistoryAllowed": _as_dict(context_plan.get("tokenBudget")).get("rawHistoryAllowed"),
            "willWriteMemory": False,
            "willRetrieveRag": False,
        },
        "preloadIntent": _preload_intent(preload_plan, selected_model),
        "projectSessionContract": project_session_contract,
        "executionContract": {
            "routingMode": "direct_expert_for_specialized_project" if project_id or project_type else "router_guided_expert",
            "projectSessionContractVersion": project_session_contract.get("contractVersion"),
            "projectSessionMode": project_session_contract.get("sessionMode"),
            "frontendDirectModelCallAllowed": False,
            "backendOrchestratorRequired": True,
            "fallbackExpertId": "cognix-general",
            "willLoadModel": False,
            "willGenerate": False,
        },
        "warnings": warnings,
        "reason": "Projet specialise planifie avec expert principal, fallback generaliste et memoire projet.",
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "projectMutation": False,
            "defaultModelWrite": False,
            "cacheMutation": False,
            "ragRetrieval": False,
            "memoryWrite": False,
        },
    }
