# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX long-term skill and preference memory.

This module proposes candidate memories from observations. It never writes
storage, injects context, calls a model, or auto-approves a memory by itself.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_SKILL_MEMORY_VERSION = "cognix_skill_memory_v1"
COGNIX_PREFERENCE_EXTRACTOR_VERSION = "cognix_preference_extractor_v1"
COGNIX_MEMORY_APPROVAL_VERSION = "cognix_memory_approval_v1"
COGNIX_CONTEXT_INJECTOR_VERSION = "cognix_context_injector_v1"

KEYWORD_RULES: list[dict[str, Any]] = [
    {
        "id": "python_prototyping",
        "candidateType": "preference",
        "category": "tooling",
        "label": "Prefere Python pour prototyper",
        "value": "L'utilisateur prefere Python pour les prototypes rapides.",
        "keywords": ["python", "prototype", "prototyper", "script"],
    },
    {
        "id": "local_first",
        "candidateType": "preference",
        "category": "runtime",
        "label": "Prefere les solutions locales",
        "value": "L'utilisateur privilegie les solutions locales quand c'est possible.",
        "keywords": ["local", "offline", "ollama", "llama.cpp", "gguf"],
    },
    {
        "id": "structured_answers",
        "candidateType": "preference",
        "category": "communication",
        "label": "Prefere les reponses structurees",
        "value": "L'utilisateur prefere les reponses structurees pour les projets complexes.",
        "keywords": ["structure", "structured", "plan", "architecture", "complexe"],
    },
    {
        "id": "modular_architecture",
        "candidateType": "skill",
        "category": "engineering",
        "label": "Aime les architectures modulaires",
        "value": "L'utilisateur apprecie les architectures modulaires et maintenables.",
        "keywords": ["modulaire", "modular", "architecture", "module", "source natif"],
    },
    {
        "id": "ai_engineering_goal",
        "candidateType": "goal",
        "category": "career",
        "label": "Objectif ingenieur IA",
        "value": "L'utilisateur veut progresser vers l'ingenierie IA.",
        "keywords": ["ingenieur ia", "engineer ai", "ia", "ai", "machine learning", "ml"],
    },
    {
        "id": "security_first",
        "candidateType": "preference",
        "category": "security",
        "label": "Priorise la securite",
        "value": "L'utilisateur veut que la securite reste prioritaire pendant les changements.",
        "keywords": ["securite", "security", "permission", "audit", "ne casse pas"],
    },
]


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _lower(value: Any) -> str:
    return _normalize(value).lower()


def _text_from_observation(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    return " ".join(
        str(value.get(key) or "")
        for key in ("text", "content", "message", "summary", "observation", "value", "title")
        if value.get(key)
    )


def _excerpt(value: str, limit: int = 360) -> str:
    text = _normalize(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _existing_keys(existing_memories: list[dict[str, Any]] | None) -> set[str]:
    keys: set[str] = set()
    for item in existing_memories or []:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        key = metadata.get("candidateRuleId") or item.get("memory_key") or item.get("memoryKey")
        if key:
            keys.add(str(key))
    return keys


def _rule_matches(rule: dict[str, Any], text: str) -> tuple[bool, list[str]]:
    matched = [
        str(keyword)
        for keyword in rule.get("keywords") or []
        if str(keyword).lower() in text
    ]
    return bool(matched), matched


def build_skill_memory_blueprint() -> dict[str, Any]:
    return {
        "skillMemoryVersion": COGNIX_SKILL_MEMORY_VERSION,
        "preferenceExtractorVersion": COGNIX_PREFERENCE_EXTRACTOR_VERSION,
        "memoryApprovalVersion": COGNIX_MEMORY_APPROVAL_VERSION,
        "contextInjectorVersion": COGNIX_CONTEXT_INJECTOR_VERSION,
        "mode": "declarative_memory_contract",
        "memoryTypes": [
            {"id": "preference", "label": "Preference", "examples": ["style", "tools", "runtime"]},
            {"id": "skill", "label": "Skill", "examples": ["coding", "architecture", "domain"]},
            {"id": "goal", "label": "Goal", "examples": ["learning", "career", "project"]},
            {"id": "habit", "label": "Habit", "examples": ["workflow", "format", "review"]},
        ],
        "userControls": {
            "view": True,
            "edit": True,
            "delete": True,
            "disable": True,
            "export": True,
            "approveBeforeActivation": True,
        },
        "injectionPolicy": {
            "contextInjectionOnlyWhenRelevant": True,
            "activeMemoriesOnly": True,
            "rawObservationInjectionAllowed": False,
            "userCanDisableInjection": True,
        },
        "privacyPolicy": {
            "userScoped": True,
            "projectScopedCandidatesAllowed": True,
            "automaticApprovalAllowed": False,
            "sensitiveMemoryRequiresExplicitApproval": True,
            "auditRequired": True,
        },
        "sideEffects": {
            "memoryCandidateWrite": False,
            "skillMemoryWrite": False,
            "preferenceWrite": False,
            "contextInjection": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_candidate_memory_plan(
    *,
    username: str,
    observations: list[Any],
    project_id: str | None = None,
    project_type: str | None = None,
    existing_memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text_items = [_text_from_observation(item) for item in observations]
    text = _lower(" ".join(text_items))
    existing = _existing_keys(existing_memories)
    candidates: list[dict[str, Any]] = []
    for rule in KEYWORD_RULES:
        matched, matched_keywords = _rule_matches(rule, text)
        if not matched or rule["id"] in existing:
            continue
        confidence = min(0.95, 0.42 + (0.11 * len(matched_keywords)))
        candidates.append(
            {
                "candidateKey": rule["id"],
                "candidateType": rule["candidateType"],
                "category": rule["category"],
                "label": rule["label"],
                "value": rule["value"],
                "confidence": round(confidence, 3),
                "evidenceExcerpt": _excerpt(" ".join(text_items)),
                "matchedSignals": matched_keywords[:8],
                "projectId": project_id,
                "projectType": project_type,
                "status": "pending_validation",
                "requiresUserApproval": True,
                "canAutoApprove": False,
                "contextInjection": {
                    "allowedWhenRelevant": True,
                    "willInjectNow": False,
                    "activeMemoryRequired": True,
                },
            }
        )
    return {
        "skillMemoryVersion": COGNIX_SKILL_MEMORY_VERSION,
        "preferenceExtractorVersion": COGNIX_PREFERENCE_EXTRACTOR_VERSION,
        "memoryApprovalVersion": COGNIX_MEMORY_APPROVAL_VERSION,
        "contextInjectorVersion": COGNIX_CONTEXT_INJECTOR_VERSION,
        "mode": "candidate_memory_dry_run",
        "username": username,
        "projectId": project_id,
        "projectType": project_type,
        "candidates": candidates,
        "summary": {
            "observationCount": len(observations),
            "candidateCount": len(candidates),
            "requiresUserApprovalCount": len([item for item in candidates if item["requiresUserApproval"]]),
            "automaticApprovalCount": 0,
        },
        "userControls": build_skill_memory_blueprint()["userControls"],
        "sideEffects": {
            "memoryCandidateWrite": False,
            "skillMemoryWrite": False,
            "preferenceWrite": False,
            "contextInjection": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_context_injection_plan(
    *,
    username: str,
    objective: str | None = None,
    active_memories: list[dict[str, Any]] | None = None,
    max_memories: int = 5,
) -> dict[str, Any]:
    objective_text = _lower(objective)
    selected: list[dict[str, Any]] = []
    for item in active_memories or []:
        if str(item.get("status") or "active") != "active":
            continue
        haystack = _lower(" ".join([str(item.get("category") or ""), str(item.get("label") or ""), str(item.get("value") or "")]))
        relevant = not objective_text or any(token in objective_text for token in re.findall(r"[a-z0-9_+-]{4,}", haystack))
        if relevant:
            selected.append(item)
        if len(selected) >= max_memories:
            break
    return {
        "contextInjectorVersion": COGNIX_CONTEXT_INJECTOR_VERSION,
        "mode": "injection_plan_dry_run",
        "username": username,
        "selectedMemoryIds": [str(item.get("id")) for item in selected],
        "selectedMemories": [
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "label": item.get("label"),
                "value": item.get("value"),
            }
            for item in selected
        ],
        "summary": {
            "availableMemoryCount": len(active_memories or []),
            "selectedMemoryCount": len(selected),
            "willInjectNow": False,
        },
        "sideEffects": {
            "contextInjection": False,
            "memoryRead": False,
            "modelLoad": False,
            "generation": False,
        },
    }
