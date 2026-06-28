# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX autonomous background agent planning.

This module prepares queue-safe background jobs. It does not start workers,
run agents, execute tools, or send notifications directly.
"""

from __future__ import annotations

from typing import Any


COGNIX_BACKGROUND_AGENT_VERSION = "cognix_background_agent_v1"
COGNIX_PROGRESS_TRACKER_VERSION = "cognix_progress_tracker_v1"
COGNIX_NOTIFICATION_PLAN_VERSION = "cognix_notification_plan_v1"

BACKGROUND_JOB_TYPES: list[dict[str, Any]] = [
    {
        "id": "index_documents",
        "label": "Indexer des documents",
        "keywords": ["indexer", "pdf", "documents", "rag", "source"],
        "steps": ["prepare_sources", "queue_indexing", "track_progress", "notify_done"],
    },
    {
        "id": "clean_knowledge_base",
        "label": "Nettoyer une base de connaissances",
        "keywords": ["nettoyer", "base", "knowledge", "doublons", "rag"],
        "steps": ["scan_items", "detect_duplicates", "propose_cleanup", "notify_done"],
    },
    {
        "id": "compare_models",
        "label": "Comparer plusieurs modeles",
        "keywords": ["comparer", "benchmark", "modeles", "latence", "qualite"],
        "steps": ["prepare_benchmark", "queue_runs", "collect_metrics", "notify_done"],
    },
    {
        "id": "prepare_report",
        "label": "Preparer un rapport",
        "keywords": ["rapport", "report", "synthese", "resume"],
        "steps": ["collect_context", "draft_report", "review_summary", "notify_done"],
    },
    {
        "id": "audit_repo",
        "label": "Auditer un repo",
        "keywords": ["audit", "repo", "code", "github", "securite"],
        "steps": ["scan_repo", "queue_static_checks", "summarize_findings", "notify_done"],
    },
]


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _select_job_type(task: str, requested: str | None = None) -> dict[str, Any]:
    if requested:
        for item in BACKGROUND_JOB_TYPES:
            if item["id"] == requested:
                return item
    lower = task.lower()
    scored = []
    for item in BACKGROUND_JOB_TYPES:
        hits = [keyword for keyword in item["keywords"] if keyword in lower]
        scored.append((len(hits), item))
    scored.sort(key = lambda item: item[0], reverse = True)
    return scored[0][1] if scored and scored[0][0] > 0 else BACKGROUND_JOB_TYPES[3]


def build_background_agent_blueprint() -> dict[str, Any]:
    return {
        "backgroundAgentVersion": COGNIX_BACKGROUND_AGENT_VERSION,
        "progressTrackerVersion": COGNIX_PROGRESS_TRACKER_VERSION,
        "notificationPlanVersion": COGNIX_NOTIFICATION_PLAN_VERSION,
        "mode": "queue_first_background_agent_contract",
        "services": ["BackgroundAgentService", "JobQueue", "ProgressTracker", "NotificationService"],
        "jobTypes": BACKGROUND_JOB_TYPES,
        "userSurface": {
            "toast": True,
            "jobDrawer": True,
            "progressBar": True,
            "activityCenter": True,
        },
        "securityPolicy": {
            "queueRequired": True,
            "permissionsRequired": True,
            "nightModeRespected": True,
            "agentRunnerRequiresWorker": True,
            "directToolExecutionAllowed": False,
        },
        "sideEffects": {
            "jobEnqueue": False,
            "agentRunWrite": False,
            "progressLogWrite": False,
            "workerStart": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "notificationSend": False,
        },
    }


def build_background_agent_job_plan(
    *,
    username: str,
    task: str,
    job_type: str | None = None,
    project_id: str | None = None,
    priority: str = "normal",
    night_mode: bool = False,
) -> dict[str, Any]:
    clean_task = _normalize(task)
    selected = _select_job_type(clean_task, requested = job_type)
    safe_priority = priority if priority in {"low", "normal", "high"} else "normal"
    return {
        "backgroundAgentVersion": COGNIX_BACKGROUND_AGENT_VERSION,
        "progressTrackerVersion": COGNIX_PROGRESS_TRACKER_VERSION,
        "notificationPlanVersion": COGNIX_NOTIFICATION_PLAN_VERSION,
        "mode": "background_job_plan",
        "username": username,
        "projectId": project_id,
        "jobType": selected["id"],
        "title": clean_task[:180] or selected["label"],
        "priority": safe_priority,
        "nightMode": bool(night_mode),
        "queuePlan": {
            "queueRequired": True,
            "queueName": "background_agents",
            "willEnqueueNow": False,
            "workerStart": False,
        },
        "agentRunPlan": {
            "runner": "AgentRunner",
            "steps": selected["steps"],
            "initialProgressPercent": 0,
            "willRunNow": False,
        },
        "notificationPlan": {
            "toast": True,
            "activityCenter": True,
            "sendNow": False,
            "message": f"{selected['label']} planifie en arriere-plan.",
        },
        "summary": {
            "jobType": selected["id"],
            "stepCount": len(selected["steps"]),
            "progressPercent": 0,
            "nightModeRespected": bool(night_mode),
        },
        "sideEffects": build_background_agent_blueprint()["sideEffects"],
    }
