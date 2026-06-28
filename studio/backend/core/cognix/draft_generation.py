# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX multi-draft response planning.

The planner prepares response variants and style instructions without calling a
model. Actual generation must still go through the backend orchestrator/runtime
adapter, never directly from the frontend.
"""

from __future__ import annotations

from typing import Any


COGNIX_DRAFT_GENERATION_VERSION = "cognix_draft_generation_v1"
COGNIX_STYLE_PROFILE_REGISTRY_VERSION = "cognix_style_profile_registry_v1"

STYLE_PROFILES: list[dict[str, Any]] = [
    {
        "id": "quick",
        "label": "Reponse rapide",
        "tone": "direct",
        "targetLength": "short",
        "bestFor": ["chat", "resume", "triage"],
        "instruction": "Reponds en quelques phrases utiles, sans perdre les points essentiels.",
    },
    {
        "id": "detailed",
        "label": "Reponse detaillee",
        "tone": "structured",
        "targetLength": "long",
        "bestFor": ["science", "strategy", "research", "course"],
        "instruction": "Donne une reponse structuree avec contexte, etapes et limites importantes.",
    },
    {
        "id": "technical",
        "label": "Reponse technique",
        "tone": "precise",
        "targetLength": "medium",
        "bestFor": ["code", "ml", "architecture", "debugging"],
        "instruction": "Priorise les details techniques, contraintes, APIs, hypotheses et risques.",
    },
    {
        "id": "simple",
        "label": "Reponse simple",
        "tone": "plain_language",
        "targetLength": "medium",
        "bestFor": ["education", "onboarding", "support"],
        "instruction": "Explique simplement avec vocabulaire accessible et exemples courts.",
    },
    {
        "id": "business",
        "label": "Reponse business",
        "tone": "executive",
        "targetLength": "medium",
        "bestFor": ["business", "product", "decision"],
        "instruction": "Mets en avant impact, priorites, risques, couts et prochaine decision.",
    },
    {
        "id": "pedagogical",
        "label": "Reponse pedagogique",
        "tone": "teacher",
        "targetLength": "medium",
        "bestFor": ["course", "math", "physics", "education"],
        "instruction": "Explique pas a pas, avec intuition, exemple et mini-recapitulatif.",
    },
    {
        "id": "creative",
        "label": "Reponse creative",
        "tone": "imaginative",
        "targetLength": "medium",
        "bestFor": ["writing", "ideation", "brand"],
        "instruction": "Propose une reponse plus originale, expressive et exploratoire.",
    },
    {
        "id": "professional",
        "label": "Reponse professionnelle",
        "tone": "polished",
        "targetLength": "medium",
        "bestFor": ["email", "report", "work"],
        "instruction": "Formule une version soignee, claire, respectueuse et prete a partager.",
    },
]

ALIASES = {
    "rapide": "quick",
    "court": "quick",
    "detaillee": "detailed",
    "détaillée": "detailed",
    "technique": "technical",
    "simple": "simple",
    "business": "business",
    "pedagogique": "pedagogical",
    "pédagogique": "pedagogical",
    "creatif": "creative",
    "créatif": "creative",
    "pro": "professional",
    "professionnel": "professional",
}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _profile_lookup() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in STYLE_PROFILES}


def _normalized_profile_id(value: Any) -> str:
    profile_id = _normalize(value)
    return ALIASES.get(profile_id, profile_id)


def _task_defaults(task_type: str, prompt: str) -> list[str]:
    text = f"{task_type} {prompt}".lower()
    if any(marker in text for marker in ("code", "debug", "api", "python", "typescript")):
        return ["quick", "technical", "detailed"]
    if any(marker in text for marker in ("email", "mail", "rapport", "business", "client")):
        return ["quick", "professional", "business"]
    if any(marker in text for marker in ("cours", "expliquer", "math", "physique", "pedagog")):
        return ["simple", "pedagogical", "detailed"]
    if any(marker in text for marker in ("idee", "idée", "creative", "creatif", "créatif")):
        return ["quick", "creative", "professional"]
    return ["quick", "detailed", "simple"]


def build_style_profile_registry() -> dict[str, Any]:
    return {
        "styleProfileRegistryVersion": COGNIX_STYLE_PROFILE_REGISTRY_VERSION,
        "mode": "declarative",
        "profiles": STYLE_PROFILES,
        "summary": {
            "profileCount": len(STYLE_PROFILES),
            "defaultProfileIds": ["quick", "detailed", "simple"],
            "frontendDirectModelCallAllowed": False,
        },
        "policies": {
            "backendOrchestratorRequired": True,
            "multipleDraftsOnDemandOnly": True,
            "projectDefaultCanPreselectProfiles": True,
            "rankingMustHideRawReasoning": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "variantWrite": False,
            "toolExecution": False,
        },
    }


def build_draft_generation_plan(
    *,
    prompt: str,
    requested_variants: list[str] | None = None,
    max_variants: int = 3,
    task_type: str | None = None,
    include_ranking: bool = True,
    message_id: str | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    lookup = _profile_lookup()
    requested = [
        _normalized_profile_id(item)
        for item in (requested_variants or _task_defaults(task_type or "", prompt))
    ]
    selected_ids = [
        item
        for item in dict.fromkeys(requested)
        if item in lookup
    ][: max(1, min(int(max_variants or 3), 6))]
    if not selected_ids:
        selected_ids = ["quick"]
    variants = [
        {
            "id": f"draft_{profile_id}",
            "variantType": profile_id,
            "label": lookup[profile_id]["label"],
            "status": "planned",
            "styleProfile": lookup[profile_id],
            "promptInstruction": lookup[profile_id]["instruction"],
            "requiresBackendGeneration": True,
            "willGenerateNow": False,
            "willStoreVariant": False,
        }
        for profile_id in selected_ids
    ]
    return {
        "draftGenerationVersion": COGNIX_DRAFT_GENERATION_VERSION,
        "styleProfileRegistryVersion": COGNIX_STYLE_PROFILE_REGISTRY_VERSION,
        "mode": "dry_run",
        "messageId": message_id,
        "projectId": project_id,
        "modelId": model_id,
        "taskType": task_type or "general",
        "selectedVariantTypes": selected_ids,
        "variants": variants,
        "rankingPlan": {
            "enabled": bool(include_ranking) and len(variants) > 1,
            "method": "post_generation_quality_score",
            "rawReasoningVisible": False,
            "usesResponseReflection": True,
        },
        "costPlan": {
            "estimatedGenerationCount": len(variants),
            "requiresExplicitUserAction": True,
            "defaultSingleDraftStillAllowed": True,
        },
        "policies": {
            "backendOrchestratorRequired": True,
            "frontendDirectModelCallAllowed": False,
            "multipleDraftsOnDemandOnly": True,
            "storeOnlyAfterBackendGeneration": True,
            "humanCanChooseVariant": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "variantWrite": False,
            "toolExecution": False,
            "uiMutation": False,
        },
    }
