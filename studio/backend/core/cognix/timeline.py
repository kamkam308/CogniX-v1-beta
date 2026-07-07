# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX project timeline event planning and classification."""

from __future__ import annotations

from typing import Any


COGNIX_TIMELINE_VERSION = "cognix_timeline_v1"
COGNIX_TIMELINE_EVENT_CLASSIFIER_VERSION = "cognix_timeline_event_classifier_v1"

TIMELINE_EVENT_TYPES: list[dict[str, Any]] = [
    {"id": "model_selected", "keywords": ["modele", "model", "qwen", "llama", "selectionne"]},
    {"id": "architecture_decision", "keywords": ["architecture", "validee", "decision", "module", "backend"]},
    {"id": "document_added", "keywords": ["document", "pdf", "fichier", "source", "ajoute"]},
    {"id": "fine_tuning_started", "keywords": ["fine-tuning", "qlora", "lora", "training", "entrainement"]},
    {"id": "critical_error", "keywords": ["erreur", "critique", "crash", "bloque", "failed"]},
    {"id": "business_decision", "keywords": ["business", "client", "prix", "abonnement", "decision"]},
]


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def classify_timeline_event(text: str, requested_type: str | None = None) -> dict[str, Any]:
    if requested_type and any(item["id"] == requested_type for item in TIMELINE_EVENT_TYPES):
        return {"eventType": requested_type, "confidence": 0.95, "matchedSignals": ["requested_type"]}
    lower = _normalize(text).lower()
    best_type = "architecture_decision"
    best_hits: list[str] = []
    for item in TIMELINE_EVENT_TYPES:
        hits = [keyword for keyword in item["keywords"] if keyword in lower]
        if len(hits) > len(best_hits):
            best_type = item["id"]
            best_hits = hits
    confidence = min(0.95, 0.42 + (0.12 * len(best_hits)))
    return {"eventType": best_type, "confidence": round(confidence, 3), "matchedSignals": best_hits[:8]}


def build_timeline_blueprint() -> dict[str, Any]:
    return {
        "timelineVersion": COGNIX_TIMELINE_VERSION,
        "eventClassifierVersion": COGNIX_TIMELINE_EVENT_CLASSIFIER_VERSION,
        "mode": "project_timeline_contract",
        "services": ["TimelineService", "EventClassifier", "ProjectHistoryStore"],
        "eventTypes": TIMELINE_EVENT_TYPES,
        "displayContract": {
            "tabName": "Timeline",
            "elegantHistory": True,
            "rawLogUi": False,
            "clickableEvents": True,
            "sourceLinked": True,
        },
        "sideEffects": {
            "timelineWrite": False,
            "uiMutation": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


def build_timeline_event_plan(
    *,
    username: str,
    title: str,
    summary: str | None = None,
    project_id: str | None = None,
    event_type: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = " ".join([_normalize(title), _normalize(summary)])
    classification = classify_timeline_event(text, requested_type = event_type)
    return {
        "timelineVersion": COGNIX_TIMELINE_VERSION,
        "eventClassifierVersion": COGNIX_TIMELINE_EVENT_CLASSIFIER_VERSION,
        "mode": "timeline_event_plan",
        "username": username,
        "projectId": project_id,
        "event": {
            "eventType": classification["eventType"],
            "title": _normalize(title)[:240],
            "summary": _normalize(summary)[:2000],
            "sourceType": _normalize(source_type)[:80] or None,
            "sourceId": _normalize(source_id)[:160] or None,
            "importance": "high" if classification["confidence"] >= 0.66 else "normal",
            "metadata": metadata or {},
        },
        "classification": classification,
        "sideEffects": build_timeline_blueprint()["sideEffects"],
    }
