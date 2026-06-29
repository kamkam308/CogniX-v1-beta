# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Pulse activity collection and daily digest planning.

Pulse stays local-first: it summarizes already-owned CogniX records without
loading models, calling external services, or reading another user's data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


COGNIX_PULSE_VERSION = "cognix_pulse_v1"
COGNIX_PULSE_COLLECTOR_VERSION = "cognix_pulse_event_collector_v1"
COGNIX_PULSE_SUMMARIZER_VERSION = "cognix_pulse_summarizer_v1"
COGNIX_PULSE_PRIORITY_VERSION = "cognix_pulse_priority_ranker_v1"

PULSE_SOURCE_CONTRACTS: list[dict[str, Any]] = [
    {"id": "chat", "label": "Conversations", "privacyScope": "user_owned_threads"},
    {"id": "project", "label": "Projects", "privacyScope": "user_owned_projects"},
    {"id": "library", "label": "Library", "privacyScope": "user_library_assets"},
    {"id": "scheduled", "label": "Scheduled", "privacyScope": "user_scheduled_tasks"},
    {"id": "research", "label": "Research", "privacyScope": "user_research_reports"},
    {"id": "agent", "label": "Agents", "privacyScope": "user_agent_runs"},
    {"id": "image", "label": "Images", "privacyScope": "user_image_history"},
    {"id": "audit", "label": "Audit", "privacyScope": "sanitized_user_audit"},
]


def _normalize(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _timestamp_ms(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        raw = int(value)
        return raw if raw > 10_000_000_000 else raw * 1000
    text = str(value).strip()
    if not text:
        return 0
    if text.isdigit():
        return _timestamp_ms(int(text))
    normalized = text.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError:
        return 0


def _created_at(item: dict[str, Any]) -> Any:
    return (
        item.get("createdAt")
        or item.get("created_at")
        or item.get("updatedAt")
        or item.get("updated_at")
        or item.get("publishedAt")
        or item.get("published_at")
        or item.get("finishedAt")
        or item.get("finished_at")
    )


def _event(
    *,
    source_type: str,
    source_id: Any,
    title: Any,
    summary: Any,
    category: str,
    priority: str = "normal",
    created_at: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_priority = priority if priority in {"critical", "high", "normal", "low"} else "normal"
    safe_source_id = _normalize(source_id, limit = 180) or f"{source_type}-unknown"
    return {
        "id": f"{source_type}:{safe_source_id}",
        "sourceType": source_type,
        "sourceId": safe_source_id,
        "title": _normalize(title) or "Activite CogniX",
        "summary": _normalize(summary, limit = 900),
        "category": category,
        "priority": safe_priority,
        "createdAt": created_at,
        "timestampMs": _timestamp_ms(created_at),
        "metadata": metadata or {},
    }


def build_pulse_blueprint() -> dict[str, Any]:
    return {
        "pulseVersion": COGNIX_PULSE_VERSION,
        "collectorVersion": COGNIX_PULSE_COLLECTOR_VERSION,
        "summarizerVersion": COGNIX_PULSE_SUMMARIZER_VERSION,
        "priorityRankerVersion": COGNIX_PULSE_PRIORITY_VERSION,
        "mode": "local_activity_digest_contract",
        "services": [
            "PulseService",
            "PulseEventCollector",
            "PulseSummarizer",
            "PulsePriorityRanker",
            "PulseNotificationService",
        ],
        "sources": PULSE_SOURCE_CONTRACTS,
        "permissions": ["pulse:read", "pulse:configure", "pulse:admin_read"],
        "privacyPolicy": {
            "userIsolationRequired": True,
            "rawMessageBodiesIncluded": False,
            "crossAccountAggregationAllowed": False,
            "externalNetworkAllowed": False,
            "modelGenerationAllowed": False,
        },
        "displayContract": {
            "summaryCard": True,
            "timeline": True,
            "badges": True,
            "filters": True,
            "emptyState": True,
            "designSystemOnly": True,
        },
        "sideEffects": {
            "pulseReportWrite": False,
            "auditWrite": False,
            "notificationSend": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
            "crossUserRead": False,
        },
    }


def collect_pulse_events(
    *,
    username: str,
    threads: list[dict[str, Any]] | None = None,
    projects: list[dict[str, Any]] | None = None,
    library_items: list[dict[str, Any]] | None = None,
    scheduled_tasks: list[dict[str, Any]] | None = None,
    scheduled_runs: list[dict[str, Any]] | None = None,
    news_items: list[dict[str, Any]] | None = None,
    research_reports: list[dict[str, Any]] | None = None,
    agent_runs: list[dict[str, Any]] | None = None,
    image_history: list[dict[str, Any]] | None = None,
    audit_logs: list[dict[str, Any]] | None = None,
    limit: int = 120,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for thread in threads or []:
        events.append(
            _event(
                source_type = "chat",
                source_id = thread.get("id"),
                title = thread.get("title") or "Conversation CogniX",
                summary = "Conversation recente disponible dans le chat.",
                category = "conversation",
                created_at = _created_at(thread),
                metadata = {
                    "projectId": thread.get("projectId") or thread.get("project_id"),
                    "modelType": thread.get("modelType") or thread.get("model_type"),
                },
            )
        )

    for project in projects or []:
        events.append(
            _event(
                source_type = "project",
                source_id = project.get("id"),
                title = project.get("name") or "Projet CogniX",
                summary = "Projet actif dans l'espace CogniX.",
                category = "project",
                priority = "high",
                created_at = _created_at(project),
                metadata = {"archived": bool(project.get("archived"))},
            )
        )

    for item in library_items or []:
        kind = _normalize(item.get("kind"), limit = 80) or "asset"
        events.append(
            _event(
                source_type = "library",
                source_id = item.get("id"),
                title = item.get("name") or "Element Library",
                summary = f"Element {kind} ajoute depuis {item.get('source') or 'manual'}.",
                category = "library",
                created_at = _created_at(item),
                metadata = {"kind": kind, "source": item.get("source"), "sizeBytes": item.get("size_bytes")},
            )
        )

    for task in scheduled_tasks or []:
        status = _normalize(task.get("status"), limit = 80) or "active"
        priority = "high" if status == "active" else "normal"
        events.append(
            _event(
                source_type = "scheduled_task",
                source_id = task.get("id"),
                title = task.get("title") or "Tache planifiee",
                summary = f"Planification: {task.get('schedule_text') or task.get('scheduleText') or 'non precisee'}.",
                category = "scheduled",
                priority = priority,
                created_at = _created_at(task),
                metadata = {"status": status},
            )
        )

    for run in scheduled_runs or []:
        status = _normalize(run.get("status"), limit = 80) or "complete"
        events.append(
            _event(
                source_type = "scheduled_run",
                source_id = run.get("id"),
                title = f"Scheduled {run.get('action_type') or run.get('actionType') or 'run'}",
                summary = run.get("result") or "Execution planifiee terminee.",
                category = "scheduled",
                priority = "critical" if status == "failed" else "normal",
                created_at = _created_at(run),
                metadata = {
                    "status": status,
                    "taskId": run.get("task_id") or run.get("taskId"),
                    "artifactType": run.get("artifact_type") or run.get("artifactType"),
                },
            )
        )

    for item in news_items or []:
        events.append(
            _event(
                source_type = "news",
                source_id = item.get("id"),
                title = item.get("title") or "Veille CogniX",
                summary = item.get("summary") or "Element de veille ajoute.",
                category = "watch",
                created_at = _created_at(item),
                metadata = {"topic": item.get("topic"), "source": item.get("source")},
            )
        )

    for report in research_reports or []:
        events.append(
            _event(
                source_type = "research",
                source_id = report.get("id"),
                title = report.get("title") or "Rapport de recherche",
                summary = report.get("summary") or report.get("query") or "Rapport de recherche disponible.",
                category = "research",
                priority = "high",
                created_at = _created_at(report),
                metadata = {"status": report.get("status"), "sourceCount": len(report.get("sources") or [])},
            )
        )

    for run in agent_runs or []:
        status = _normalize(run.get("status"), limit = 80) or "planned"
        priority = "critical" if status == "failed" else "high" if status in {"running", "complete"} else "normal"
        events.append(
            _event(
                source_type = "agent",
                source_id = run.get("id"),
                title = run.get("goal") or "Agent CogniX",
                summary = run.get("result") or "Agent planifie dans CogniX.",
                category = "agent",
                priority = priority,
                created_at = _created_at(run),
                metadata = {"status": status, "mode": run.get("mode"), "stepCount": len(run.get("plan") or [])},
            )
        )

    for image in image_history or []:
        status = _normalize(image.get("status"), limit = 80) or "requested"
        events.append(
            _event(
                source_type = "image",
                source_id = image.get("id"),
                title = image.get("prompt") or "Image CogniX",
                summary = f"Demande image {status}.",
                category = "image",
                created_at = _created_at(image),
                metadata = {"status": status, "model": image.get("model")},
            )
        )

    for log in audit_logs or []:
        severity = _normalize(log.get("severity"), limit = 80) or "info"
        if severity not in {"warning", "critical"}:
            continue
        events.append(
            _event(
                source_type = "audit",
                source_id = log.get("id"),
                title = log.get("action") or "Action auditee",
                summary = f"Action sensible detectee sur {log.get('resource_type') or log.get('resourceType') or 'ressource'}.",
                category = "security",
                priority = "critical" if severity == "critical" else "high",
                created_at = _created_at(log),
                metadata = {"severity": severity, "resourceType": log.get("resource_type") or log.get("resourceType")},
            )
        )

    events.sort(key = lambda item: (_number(item.get("timestampMs")), item["priority"]), reverse = True)
    return events[: max(1, min(int(limit or 120), 240))]


def _priority_rank(priority: str) -> int:
    return {"critical": 4, "high": 3, "normal": 2, "low": 1}.get(priority, 2)


def _top_events(events: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(
        events,
        key = lambda item: (_priority_rank(str(item.get("priority"))), _number(item.get("timestampMs"))),
        reverse = True,
    )
    return ranked[:limit]


def _source_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        source = str(event.get("sourceType") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _topic_from_event(event: dict[str, Any]) -> str:
    title = _normalize(event.get("title"), limit = 80)
    if title:
        return title
    return _normalize(event.get("category"), limit = 80) or "CogniX"


def build_pulse_plan(
    *,
    username: str,
    events: list[dict[str, Any]],
    hours: int = 24,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_hours = max(1, min(int(hours or 24), 168))
    cutoff_ms = int(((now or datetime.now(timezone.utc)).timestamp() * 1000) - (safe_hours * 60 * 60 * 1000))
    recent_events = [
        event for event in events if not event.get("timestampMs") or _number(event.get("timestampMs")) >= cutoff_ms
    ]
    source_events = recent_events if recent_events else events[:12]
    important = _top_events(source_events, limit = 8)
    failed = [event for event in source_events if event.get("priority") == "critical"]
    high = [event for event in source_events if event.get("priority") == "high"]
    counts = _source_counts(source_events)
    topics = []
    for event in important:
        topic = _topic_from_event(event)
        if topic and topic not in topics:
            topics.append(topic)
    if not topics:
        topics = ["Activite CogniX", "Suivi personnel", "Idees a reprendre"]

    if source_events:
        summary = (
            f"Pulse a analyse {len(source_events)} activites CogniX sur les {safe_hours} dernieres heures. "
            f"Points forts: {', '.join(topics[:4])}."
        )
    else:
        summary = (
            "Pulse n'a pas encore trouve d'activite recente. "
            "Demarrez un chat, ajoutez un element Library ou creez une tache Scheduled pour alimenter ce fil."
        )

    recommendations: list[dict[str, Any]] = []
    if counts.get("library", 0) and not counts.get("scheduled_task", 0):
        recommendations.append(
            {
                "id": "schedule_library_digest",
                "title": "Planifier un resume Library",
                "reason": "Des elements Library existent sans tache Scheduled associee.",
                "action": "create_scheduled_digest",
                "priority": "normal",
            }
        )
    if counts.get("scheduled_run", 0) and failed:
        recommendations.append(
            {
                "id": "review_failed_scheduled_runs",
                "title": "Verifier les taches planifiees en echec",
                "reason": "Pulse a detecte au moins une execution critique.",
                "action": "open_scheduled_runs",
                "priority": "high",
            }
        )
    if counts.get("research", 0) and not counts.get("library", 0):
        recommendations.append(
            {
                "id": "save_research_to_library",
                "title": "Classer la recherche dans Library",
                "reason": "Les rapports de recherche gagnent a etre relies a la bibliotheque.",
                "action": "create_library_link",
                "priority": "normal",
            }
        )

    source_thread_ids = [
        event["sourceId"]
        for event in source_events
        if event.get("sourceType") == "chat" and event.get("sourceId")
    ][:24]

    side_effects = build_pulse_blueprint()["sideEffects"]
    return {
        "pulseVersion": COGNIX_PULSE_VERSION,
        "collectorVersion": COGNIX_PULSE_COLLECTOR_VERSION,
        "summarizerVersion": COGNIX_PULSE_SUMMARIZER_VERSION,
        "priorityRankerVersion": COGNIX_PULSE_PRIORITY_VERSION,
        "mode": "daily_pulse_plan",
        "username": username,
        "windowHours": safe_hours,
        "summary": {
            "eventCount": len(source_events),
            "importantCount": len(important),
            "criticalCount": len(failed),
            "highPriorityCount": len(high),
            "sourceCounts": counts,
            "topics": topics[:12],
        },
        "digest": {
            "title": f"Pulse des dernieres {safe_hours}h",
            "summary": summary,
            "topics": topics[:12],
            "importantEvents": important,
            "recentEvents": source_events[:40],
            "recommendations": recommendations,
            "problemsDetected": failed[:8],
        },
        "reportPayload": {
            "title": f"Pulse des dernieres {safe_hours}h",
            "summary": summary,
            "topics": topics[:12],
            "sourceThreadIds": source_thread_ids,
        },
        "privacy": {
            "rawMessageBodiesIncluded": False,
            "crossAccountAggregation": False,
            "ownerUsername": username,
        },
        "sideEffects": side_effects,
    }
