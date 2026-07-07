# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI debate planning.

The debate orchestrator prepares visible debate roles and bounded rounds. It
never calls a model, exposes raw chain-of-thought, or creates a final answer on
its own.
"""

from __future__ import annotations

from typing import Any


COGNIX_DEBATE_ORCHESTRATOR_VERSION = "cognix_debate_orchestrator_v1"
COGNIX_DEBATE_ROLE_REGISTRY_VERSION = "cognix_debate_role_registry_v1"

ROLE_PROFILES: list[dict[str, Any]] = [
    {
        "id": "advocate",
        "label": "Agent A",
        "displayRole": "Argument principal",
        "purpose": "Proposer une solution forte et utile.",
        "visibility": "public_summary_only",
    },
    {
        "id": "critic",
        "label": "Agent B",
        "displayRole": "Contre-argument",
        "purpose": "Identifier limites, risques, angles morts et hypotheses faibles.",
        "visibility": "public_summary_only",
    },
    {
        "id": "synthesizer",
        "label": "Arbitre CogniX",
        "displayRole": "Synthese finale",
        "purpose": "Comparer les arguments visibles et produire une synthese actionnable.",
        "visibility": "final_summary_visible",
    },
    {
        "id": "domain_expert",
        "label": "Expert domaine",
        "displayRole": "Validation specialisee",
        "purpose": "Verifier les contraintes du domaine quand la demande est technique.",
        "visibility": "public_summary_only",
    },
]

ALIASES = {
    "agent_a": "advocate",
    "a": "advocate",
    "pro": "advocate",
    "agent_b": "critic",
    "b": "critic",
    "contra": "critic",
    "critique": "critic",
    "judge": "synthesizer",
    "juge": "synthesizer",
    "arbitre": "synthesizer",
    "expert": "domain_expert",
}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _role_lookup() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in ROLE_PROFILES}


def _normalized_role_id(value: Any) -> str:
    role_id = _normalize(value)
    return ALIASES.get(role_id, role_id)


def _default_roles(task_type: str, prompt: str) -> list[str]:
    text = f"{task_type} {prompt}".lower()
    if any(marker in text for marker in ("architecture", "code", "modele", "model", "scientifique", "science")):
        return ["advocate", "critic", "domain_expert", "synthesizer"]
    return ["advocate", "critic", "synthesizer"]


def _objective_excerpt(prompt: str) -> str:
    return " ".join(str(prompt or "").split())[:500]


def build_debate_role_registry() -> dict[str, Any]:
    return {
        "debateRoleRegistryVersion": COGNIX_DEBATE_ROLE_REGISTRY_VERSION,
        "mode": "declarative",
        "roles": ROLE_PROFILES,
        "summary": {
            "roleCount": len(ROLE_PROFILES),
            "defaultRoleIds": ["advocate", "critic", "synthesizer"],
            "frontendDirectModelCallAllowed": False,
        },
        "policies": {
            "backendOrchestratorRequired": True,
            "rawChainOfThoughtAllowed": False,
            "publicArgumentsOnly": True,
            "finalAnswerSingleVisible": True,
            "roundLimitRequired": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "debateSessionWrite": False,
            "toolExecution": False,
        },
    }


def _selected_roles(requested_roles: list[str] | None, *, task_type: str, prompt: str) -> list[dict[str, Any]]:
    lookup = _role_lookup()
    requested = [
        _normalized_role_id(item)
        for item in (requested_roles or _default_roles(task_type, prompt))
    ]
    selected_ids = [
        item
        for item in dict.fromkeys(requested)
        if item in lookup
    ]
    if "advocate" not in selected_ids:
        selected_ids.insert(0, "advocate")
    if "critic" not in selected_ids:
        selected_ids.insert(1, "critic")
    if "synthesizer" not in selected_ids:
        selected_ids.append("synthesizer")
    return [lookup[item] for item in selected_ids]


def build_debate_plan(
    *,
    prompt: str,
    requested_roles: list[str] | None = None,
    max_rounds: int = 3,
    task_type: str | None = None,
    message_id: str | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    task = task_type or "general"
    roles = _selected_roles(requested_roles, task_type = task, prompt = prompt)
    round_limit = max(2, min(int(max_rounds or 3), 5))
    role_ids = [str(role["id"]) for role in roles]
    rounds: list[dict[str, Any]] = [
        {
            "id": "round_opening",
            "roundIndex": 1,
            "roleId": "advocate",
            "label": "Argument principal",
            "purpose": "Proposer une reponse candidate claire.",
            "publicPrompt": "Resume l'argument principal sans raisonnement cache.",
            "status": "planned",
            "requiresBackendGeneration": True,
            "willGenerateNow": False,
        },
        {
            "id": "round_critique",
            "roundIndex": 2,
            "roleId": "critic",
            "label": "Contre-argument",
            "purpose": "Lister risques, limites et corrections possibles.",
            "publicPrompt": "Expose uniquement les critiques utiles et verifiables.",
            "status": "planned",
            "requiresBackendGeneration": True,
            "willGenerateNow": False,
        },
    ]
    if "domain_expert" in role_ids and round_limit >= 4:
        rounds.append(
            {
                "id": "round_domain_review",
                "roundIndex": 3,
                "roleId": "domain_expert",
                "label": "Validation specialisee",
                "purpose": "Verifier contraintes et exactitude du domaine.",
                "publicPrompt": "Donne une verification specialisee sans details internes.",
                "status": "planned",
                "requiresBackendGeneration": True,
                "willGenerateNow": False,
            }
        )
    if round_limit >= 3:
        rounds.append(
            {
                "id": "round_reply",
                "roundIndex": len(rounds) + 1,
                "roleId": "advocate",
                "label": "Reponse aux critiques",
                "purpose": "Ameliorer la proposition avec les critiques utiles.",
                "publicPrompt": "Reponds aux critiques sous forme de synthese visible.",
                "status": "planned",
                "requiresBackendGeneration": True,
                "willGenerateNow": False,
            }
        )
    rounds.append(
        {
            "id": "round_synthesis",
            "roundIndex": len(rounds) + 1,
            "roleId": "synthesizer",
            "label": "Synthese finale",
            "purpose": "Produire la reponse finale concise et actionnable.",
            "publicPrompt": "Fais une synthese finale visible, sans chain-of-thought brute.",
            "status": "planned",
            "requiresBackendGeneration": True,
            "willGenerateNow": False,
        }
    )
    return {
        "debateOrchestratorVersion": COGNIX_DEBATE_ORCHESTRATOR_VERSION,
        "debateRoleRegistryVersion": COGNIX_DEBATE_ROLE_REGISTRY_VERSION,
        "mode": "dry_run",
        "messageId": message_id,
        "projectId": project_id,
        "modelId": model_id,
        "taskType": task,
        "objectiveExcerpt": _objective_excerpt(prompt),
        "roles": roles,
        "rounds": rounds,
        "summary": {
            "roleCount": len(roles),
            "plannedRoundCount": len(rounds),
            "maxRounds": round_limit,
            "finalRoundId": "round_synthesis",
        },
        "displayContract": {
            "finalAnswerVisibleByDefault": True,
            "debatePanelCollapsible": True,
            "publicArgumentsVisible": True,
            "rawChainOfThoughtVisible": False,
            "showOneCleanThread": True,
        },
        "policies": {
            "backendOrchestratorRequired": True,
            "frontendDirectModelCallAllowed": False,
            "roundLimitEnforced": True,
            "rawChainOfThoughtAllowed": False,
            "judgeSynthesisRequired": True,
            "storeOnlyPublicSummaries": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "debateSessionWrite": False,
            "debateOutputWrite": False,
            "toolExecution": False,
            "uiMutation": False,
        },
    }
