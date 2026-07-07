# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Scheduled task planning and permission-aware execution contracts."""

from __future__ import annotations

import re
from typing import Any


COGNIX_SCHEDULED_VERSION = "cognix_scheduled_v1"
COGNIX_CRON_SCHEDULER_VERSION = "cognix_cron_scheduler_v1"
COGNIX_SCHEDULED_PERMISSION_VERSION = "cognix_scheduled_permission_checker_v1"
COGNIX_SCHEDULED_REPORT_VERSION = "cognix_scheduled_report_generator_v1"

SCHEDULED_ACTIONS: list[dict[str, Any]] = [
    {
        "id": "report",
        "label": "Rapport Library",
        "keywords": ["rapport", "resume", "résumé", "synthese", "synthèse", "recap", "compte rendu"],
        "requiredPermissions": [],
        "riskLevel": "low",
        "queueName": "scheduled_reports",
        "outputType": "library_item",
        "networkRequired": False,
        "writes": ["scheduled_task_run", "library_item"],
    },
    {
        "id": "news",
        "label": "Veille actualites",
        "keywords": ["news", "actualite", "actualité", "veille", "surveille", "monitoring"],
        "requiredPermissions": ["scheduled:external_read"],
        "riskLevel": "medium",
        "queueName": "scheduled_watch",
        "outputType": "news",
        "networkRequired": True,
        "writes": ["scheduled_task_run", "news_items"],
    },
    {
        "id": "research",
        "label": "Recherche planifiee",
        "keywords": ["recherche", "research", "analyse", "source", "sources", "rapport de recherche"],
        "requiredPermissions": ["scheduled:external_read", "research:create"],
        "riskLevel": "medium",
        "queueName": "scheduled_research",
        "outputType": "research_report",
        "networkRequired": True,
        "writes": ["scheduled_task_run", "research_report"],
    },
    {
        "id": "agent",
        "label": "Agent planifie",
        "keywords": ["agent", "action", "automatisation", "execute", "exécute", "workflow"],
        "requiredPermissions": ["agent:run"],
        "riskLevel": "medium",
        "queueName": "scheduled_agents",
        "outputType": "agent_run",
        "networkRequired": False,
        "writes": ["scheduled_task_run", "agent_run"],
    },
    {
        "id": "benchmark",
        "label": "Benchmark planifie",
        "keywords": ["benchmark", "performance", "latence", "tokens", "vitesse"],
        "requiredPermissions": ["benchmark:run"],
        "riskLevel": "medium",
        "queueName": "scheduled_benchmarks",
        "outputType": "benchmark_plan",
        "networkRequired": False,
        "writes": ["scheduled_task_run"],
    },
    {
        "id": "index_documents",
        "label": "Indexation documents",
        "keywords": ["indexer", "indexation", "rag", "documents", "pdf", "fichiers"],
        "requiredPermissions": ["rag:write"],
        "riskLevel": "medium",
        "queueName": "scheduled_rag",
        "outputType": "rag_index_plan",
        "networkRequired": False,
        "writes": ["scheduled_task_run"],
    },
    {
        "id": "security_audit",
        "label": "Audit securite",
        "keywords": ["securite", "sécurité", "vulnerabilite", "vulnérabilité", "audit", "scan"],
        "requiredPermissions": ["security:audit"],
        "riskLevel": "high",
        "queueName": "scheduled_security",
        "outputType": "security_audit_plan",
        "networkRequired": False,
        "writes": ["scheduled_task_run", "audit_log"],
    },
]


def _normalize(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _cron_hint(schedule_text: str) -> dict[str, Any]:
    text = _normalize(schedule_text, limit = 200).lower()
    time_match = re.search(r"(\d{1,2})[:h](\d{2})", text)
    hour = None
    minute = None
    if time_match:
        hour = max(0, min(int(time_match.group(1)), 23))
        minute = max(0, min(int(time_match.group(2)), 59))
    if any(word in text for word in ("jour", "daily", "every day", "quotidien")):
        cadence = "daily"
    elif any(word in text for word in ("semaine", "weekly", "hebdo")):
        cadence = "weekly"
    elif any(word in text for word in ("mois", "monthly", "mensuel")):
        cadence = "monthly"
    elif any(word in text for word in ("heure", "hourly")):
        cadence = "hourly"
    else:
        cadence = "manual_or_custom"
    return {
        "cadence": cadence,
        "hour": hour,
        "minute": minute,
        "timezoneAware": True,
        "raw": _normalize(schedule_text, limit = 200),
    }


def classify_scheduled_action(prompt: str, requested_action: str | None = None) -> dict[str, Any]:
    if requested_action:
        for action in SCHEDULED_ACTIONS:
            if action["id"] == requested_action:
                return {**action, "confidence": 0.96, "matchedSignals": ["requested_action"]}
    text = _normalize(prompt, limit = 4000).lower()
    best_action = SCHEDULED_ACTIONS[0]
    best_hits: list[str] = []
    for action in SCHEDULED_ACTIONS:
        hits = [keyword for keyword in action["keywords"] if keyword in text]
        if len(hits) > len(best_hits):
            best_action = action
            best_hits = hits
    confidence = min(0.95, 0.48 + (0.13 * len(best_hits)))
    return {**best_action, "confidence": round(confidence, 3), "matchedSignals": best_hits[:8]}


def build_scheduled_blueprint() -> dict[str, Any]:
    return {
        "scheduledVersion": COGNIX_SCHEDULED_VERSION,
        "cronSchedulerVersion": COGNIX_CRON_SCHEDULER_VERSION,
        "permissionCheckerVersion": COGNIX_SCHEDULED_PERMISSION_VERSION,
        "reportGeneratorVersion": COGNIX_SCHEDULED_REPORT_VERSION,
        "mode": "queue_first_scheduled_contract",
        "services": [
            "ScheduledTaskService",
            "CronScheduler",
            "JobQueue",
            "ScheduledReportGenerator",
            "TaskPermissionChecker",
        ],
        "actions": SCHEDULED_ACTIONS,
        "permissions": [
            "scheduled:read",
            "scheduled:create",
            "scheduled:update",
            "scheduled:delete",
            "scheduled:admin",
        ],
        "securityPolicy": {
            "creatorPermissionCeiling": True,
            "queueRequiredForHeavyTasks": True,
            "auditRequired": True,
            "externalNetworkRequiresPermission": True,
            "frontendDirectExecutionAllowed": False,
        },
        "sideEffects": {
            "taskWrite": False,
            "taskRunWrite": False,
            "queueEnqueue": False,
            "auditWrite": False,
            "libraryWrite": False,
            "newsWrite": False,
            "researchWrite": False,
            "agentRunWrite": False,
            "ragIndexWrite": False,
            "benchmarkRun": False,
            "securityScan": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


def build_permission_plan(
    *,
    action: dict[str, Any],
    granted_permissions: set[str] | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    granted = {permission.lower() for permission in (granted_permissions or set())}
    required = [str(permission).lower() for permission in action.get("requiredPermissions", [])]
    missing = [] if admin else [permission for permission in required if permission not in granted]
    return {
        "permissionCheckerVersion": COGNIX_SCHEDULED_PERMISSION_VERSION,
        "requiredPermissions": required,
        "grantedPermissions": sorted(granted),
        "missingPermissions": missing,
        "allowedByRole": bool(admin),
        "allowed": not missing,
        "executionCeiling": "admin" if admin else "creator_permissions",
    }


def build_scheduled_task_plan(
    *,
    username: str,
    title: str,
    prompt: str,
    schedule_text: str,
    granted_permissions: set[str] | None = None,
    admin: bool = False,
    existing_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_title = _normalize(title, limit = 160) or "Tache planifiee CogniX"
    clean_prompt = _normalize(prompt, limit = 4000)
    action = classify_scheduled_action(f"{clean_title} {clean_prompt}")
    permission_plan = build_permission_plan(
        action = action,
        granted_permissions = granted_permissions,
        admin = admin,
    )
    cron = _cron_hint(schedule_text)
    heavy = action["id"] in {"research", "agent", "benchmark", "index_documents", "security_audit"}
    side_effects = build_scheduled_blueprint()["sideEffects"]
    return {
        "scheduledVersion": COGNIX_SCHEDULED_VERSION,
        "cronSchedulerVersion": COGNIX_CRON_SCHEDULER_VERSION,
        "permissionCheckerVersion": COGNIX_SCHEDULED_PERMISSION_VERSION,
        "reportGeneratorVersion": COGNIX_SCHEDULED_REPORT_VERSION,
        "mode": "scheduled_task_plan",
        "username": username,
        "taskId": existing_task.get("id") if existing_task else None,
        "title": clean_title,
        "prompt": clean_prompt,
        "scheduleText": _normalize(schedule_text, limit = 160),
        "action": {
            "actionType": action["id"],
            "label": action["label"],
            "confidence": action["confidence"],
            "matchedSignals": action["matchedSignals"],
            "riskLevel": action["riskLevel"],
            "outputType": action["outputType"],
            "networkRequired": bool(action["networkRequired"]),
        },
        "schedule": cron,
        "queuePlan": {
            "queueRequired": bool(heavy or action["networkRequired"]),
            "queueName": action["queueName"],
            "willEnqueueNow": False,
            "workerStart": False,
        },
        "permissionPlan": permission_plan,
        "executionPlan": {
            "canRunNow": permission_plan["allowed"],
            "directFrontendExecutionAllowed": False,
            "writes": action["writes"],
            "reportOutputType": action["outputType"],
            "recoverableErrors": True,
        },
        "warnings": [
            {
                "id": "missing_permissions",
                "message": "Cette tache depasse les permissions actuelles du createur.",
                "missingPermissions": permission_plan["missingPermissions"],
            }
        ]
        if permission_plan["missingPermissions"]
        else [],
        "sideEffects": side_effects,
    }


def build_run_result_stub(action_type: str, prompt: str) -> dict[str, str | None]:
    clean_prompt = _normalize(prompt, limit = 240)
    if action_type == "benchmark":
        return {
            "artifactType": "benchmark_plan",
            "result": f"Benchmark planifie pour '{clean_prompt}'. Le worker dedie devra executer la mesure.",
        }
    if action_type == "index_documents":
        return {
            "artifactType": "rag_index_plan",
            "result": f"Indexation RAG planifiee pour '{clean_prompt}'. Aucun index n'a ete modifie directement.",
        }
    if action_type == "security_audit":
        return {
            "artifactType": "security_audit_plan",
            "result": f"Audit securite planifie pour '{clean_prompt}'. Execution reservee au worker securise.",
        }
    return {"artifactType": None, "result": None}
