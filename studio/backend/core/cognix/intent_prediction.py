# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX intent prediction and preload planning.

Predictions are deterministic planning hints. They never preload, unload, or
call a model directly.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_INTENT_PREDICTION_VERSION = "cognix_intent_prediction_v1"
COGNIX_PRELOAD_SCHEDULER_VERSION = "cognix_preload_scheduler_v1"

INTENT_DOMAINS: list[dict[str, Any]] = [
    {
        "id": "code",
        "modelId": "cognix-code-local",
        "keywords": ["code", "python", "javascript", "typescript", "bug", "erreur", "test", "git", "fichier", "api"],
    },
    {
        "id": "maths",
        "modelId": "cognix-maths-local",
        "keywords": ["equation", "integrale", "derivee", "matrice", "theoreme", "preuve", "fonction", "calcul", "math"],
    },
    {
        "id": "physics",
        "modelId": "cognix-physique-local",
        "keywords": ["physique", "quantique", "mecanique", "force", "energie", "onde", "champ", "vitesse"],
    },
    {
        "id": "rag",
        "modelId": "cognix-general-small",
        "keywords": ["pdf", "document", "citation", "indexer", "rag", "source", "retrieval", "chunk"],
    },
    {
        "id": "fine_tuning",
        "modelId": "cognix-general-small",
        "keywords": ["fine-tuning", "finetuning", "qlora", "lora", "dataset", "training", "entrainement"],
    },
    {
        "id": "general",
        "modelId": "cognix-general-small",
        "keywords": ["general", "chat", "question", "aide", "expliquer"],
    },
]


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _text_from_recent(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    return " ".join(
        str(value.get(key) or "")
        for key in ("content", "text", "message", "summary", "title")
        if value.get(key)
    )


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[a-zA-Z0-9_+-]{3,}", text or "")}


def _domain_by_id(domain_id: str) -> dict[str, Any]:
    return next((item for item in INTENT_DOMAINS if item["id"] == domain_id), INTENT_DOMAINS[-1])


def build_intent_prediction_blueprint() -> dict[str, Any]:
    return {
        "intentPredictionVersion": COGNIX_INTENT_PREDICTION_VERSION,
        "preloadSchedulerVersion": COGNIX_PRELOAD_SCHEDULER_VERSION,
        "mode": "deterministic_intent_planning",
        "services": ["IntentPredictionService", "PreloadScheduler", "ModelCacheManager"],
        "domains": [
            {"id": item["id"], "modelId": item["modelId"], "keywordCount": len(item["keywords"])}
            for item in INTENT_DOMAINS
        ],
        "displayPolicy": {
            "mostlyInvisible": True,
            "maxSuggestions": 1,
            "showOnlyUsefulSuggestion": True,
        },
        "preloadPolicy": {
            "silentPreloadPlanningAllowed": True,
            "actualPreloadAllowedHere": False,
            "requiresCacheManager": True,
            "abruptDomainChangeThreshold": 0.18,
        },
        "sideEffects": {
            "predictionWrite": False,
            "preloadEventWrite": False,
            "modelLoad": False,
            "modelUnload": False,
            "generation": False,
            "networkCall": False,
            "uiSuggestion": False,
        },
    }


def build_intent_prediction(
    *,
    username: str,
    project_type: str | None = None,
    draft_text: str | None = None,
    recent_messages: list[Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    project_text = _normalize(project_type).lower()
    draft = _normalize(draft_text).lower()
    recent = _normalize(" ".join(_text_from_recent(item) for item in recent_messages or [])).lower()
    all_tokens = {
        "project": _tokens(project_text),
        "draft": _tokens(draft),
        "recent": _tokens(recent),
    }
    raw_scores: dict[str, float] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for domain in INTENT_DOMAINS:
        keywords = {str(item).lower() for item in domain["keywords"]}
        project_hits = keywords & all_tokens["project"]
        draft_hits = keywords & all_tokens["draft"]
        recent_hits = keywords & all_tokens["recent"]
        score = 0.08 + (0.25 * len(project_hits)) + (0.34 * len(draft_hits)) + (0.16 * len(recent_hits))
        if domain["id"] == "general":
            score += 0.08
        raw_scores[domain["id"]] = score
        evidence[domain["id"]] = {
            "projectSignals": sorted(project_hits),
            "draftSignals": sorted(draft_hits),
            "recentSignals": sorted(recent_hits),
        }
    total = sum(raw_scores.values()) or 1.0
    probabilities = [
        {
            "domain": domain_id,
            "probability": round(score / total, 3),
            "evidence": evidence[domain_id],
        }
        for domain_id, score in sorted(raw_scores.items(), key = lambda item: item[1], reverse = True)
    ]
    selected = probabilities[0] if probabilities else {"domain": "general", "probability": 1.0}
    selected_domain = _domain_by_id(str(selected["domain"]))
    confidence = float(selected["probability"])
    previous_project_domain = project_text if project_text in {item["id"] for item in INTENT_DOMAINS} else None
    abrupt_change = bool(previous_project_domain and previous_project_domain != selected_domain["id"] and confidence >= 0.28)
    should_suggest = confidence >= 0.24 and selected_domain["id"] != "general"
    suggestion = (
        {
            "type": "preload_model",
            "domain": selected_domain["id"],
            "modelId": selected_domain["modelId"],
            "label": f"Preparer {selected_domain['id']}",
            "visible": True,
        }
        if should_suggest
        else None
    )
    preload_plan = {
        "preloadSchedulerVersion": COGNIX_PRELOAD_SCHEDULER_VERSION,
        "targetDomain": selected_domain["id"],
        "targetModelId": selected_domain["modelId"],
        "wouldPreload": should_suggest,
        "willPreloadNow": False,
        "requiresCacheManager": True,
        "reason": "High confidence intent prediction." if should_suggest else "Confidence too low for visible suggestion.",
    }
    return {
        "intentPredictionVersion": COGNIX_INTENT_PREDICTION_VERSION,
        "preloadSchedulerVersion": COGNIX_PRELOAD_SCHEDULER_VERSION,
        "mode": "intent_prediction_dry_run",
        "username": username,
        "projectId": project_id,
        "projectType": project_type,
        "selectedDomain": selected_domain["id"],
        "confidence": round(confidence, 3),
        "domainProbabilities": probabilities,
        "suggestion": suggestion,
        "preloadPlan": preload_plan,
        "summary": {
            "maxSuggestions": 1,
            "suggestionCount": 1 if suggestion else 0,
            "abruptDomainChange": abrupt_change,
            "willPreloadNow": False,
        },
        "sideEffects": build_intent_prediction_blueprint()["sideEffects"],
    }
