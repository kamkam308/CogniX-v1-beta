# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX admin project oversight.

The service builds organization-wide project summaries from existing chat,
usage, permission, and security records. Sensitive project operations are
planned and audited before any destructive mutation is allowed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


COGNIX_ADMIN_PROJECT_SERVICE_VERSION = "cognix_admin_project_service_v1"
COGNIX_PROJECT_RISK_ANALYZER_VERSION = "cognix_project_risk_analyzer_v1"
COGNIX_PROJECT_USAGE_AGGREGATOR_VERSION = "cognix_project_usage_aggregator_v1"
COGNIX_PROJECT_ACTION_PLANNER_VERSION = "cognix_project_action_planner_v1"
COGNIX_PROJECT_REPORT_VERSION = "cognix_project_admin_report_v1"

PROJECT_OVERSIGHT_SERVICES = [
    "AdminProjectService",
    "ProjectRiskAnalyzer",
    "ProjectUsageAggregator",
]

PROJECT_OVERSIGHT_TABLES = [
    "admin_project_events",
    "project_admin_reports",
    "project_members",
    "project_roles",
    "project_activity_events",
    "token_usage_events",
    "daily_model_usage",
    "risk_scores",
    "audit_logs",
]

PROJECT_ACTIONS: dict[str, dict[str, Any]] = {
    "archive": {
        "label": "Archive project",
        "permission": "admin:projects:archive",
        "riskLevel": "high",
        "approvalRequired": True,
        "destructive": True,
    },
    "transfer_ownership": {
        "label": "Transfer ownership",
        "permission": "admin:projects:transfer",
        "riskLevel": "high",
        "approvalRequired": True,
        "destructive": True,
    },
    "remove_member": {
        "label": "Remove member",
        "permission": "admin:projects:members",
        "riskLevel": "medium",
        "approvalRequired": True,
        "destructive": True,
    },
    "add_member": {
        "label": "Add member",
        "permission": "admin:projects:members",
        "riskLevel": "medium",
        "approvalRequired": True,
        "destructive": False,
    },
    "restrict_models": {
        "label": "Restrict models",
        "permission": "admin:projects:models",
        "riskLevel": "high",
        "approvalRequired": True,
        "destructive": False,
    },
    "disable_cloud": {
        "label": "Disable cloud",
        "permission": "admin:projects:cloud",
        "riskLevel": "high",
        "approvalRequired": True,
        "destructive": False,
    },
    "export_report": {
        "label": "Export report",
        "permission": "admin:projects:export",
        "riskLevel": "medium",
        "approvalRequired": False,
        "destructive": False,
    },
}

RISK_POINTS = {
    "archived_project": 8,
    "high_usage": 15,
    "cloud_usage": 15,
    "security_events": 24,
    "sensitive_audit": 18,
    "restricted_permission": 10,
    "open_reports": 16,
}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _project_id(row: dict[str, Any]) -> str:
    return _norm(row.get("projectId") or row.get("project_id") or row.get("id"), "none") or "none"


def _thread_project_id(row: dict[str, Any]) -> str:
    return _norm(row.get("projectId") or row.get("project_id"), "none") or "none"


def _thread_model_id(row: dict[str, Any]) -> str:
    return _norm(row.get("modelId") or row.get("model_id") or row.get("modelType") or row.get("model_type"), "unknown")


def _owner(row: dict[str, Any]) -> str:
    return _norm(row.get("ownerUsername") or row.get("owner_username") or row.get("username"), "unknown") or "unknown"


def _token_total(row: dict[str, Any]) -> int:
    total = _as_int(row.get("total_tokens") or row.get("totalTokens"))
    if total:
        return max(0, total)
    return max(0, _as_int(row.get("input_tokens") or row.get("inputTokens"))) + max(
        0,
        _as_int(row.get("output_tokens") or row.get("outputTokens")),
    )


def _provider(row: dict[str, Any]) -> str:
    return _norm(row.get("provider"), "local").lower() or "local"


def _is_cloud_provider(row: dict[str, Any]) -> bool:
    provider = _provider(row)
    return provider not in {"", "local", "ollama", "llama", "gguf", "cpu", "unsloth"}


def _risk_level(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _bounded_score(value: int | float) -> int:
    return int(max(0, min(100, round(float(value)))))


def _project_metadata(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "projectId": _project_id(project),
        "name": _norm(project.get("name"), "Untitled project"),
        "ownerUsername": _owner(project),
        "archived": bool(project.get("archived")),
        "createdAt": project.get("createdAt") or project.get("created_at"),
        "updatedAt": project.get("updatedAt") or project.get("updated_at"),
    }


def build_admin_project_blueprint() -> dict[str, Any]:
    return {
        "adminProjectServiceVersion": COGNIX_ADMIN_PROJECT_SERVICE_VERSION,
        "projectRiskAnalyzerVersion": COGNIX_PROJECT_RISK_ANALYZER_VERSION,
        "projectUsageAggregatorVersion": COGNIX_PROJECT_USAGE_AGGREGATOR_VERSION,
        "projectActionPlannerVersion": COGNIX_PROJECT_ACTION_PLANNER_VERSION,
        "projectReportVersion": COGNIX_PROJECT_REPORT_VERSION,
        "mode": "native_admin_project_oversight",
        "services": PROJECT_OVERSIGHT_SERVICES,
        "tables": PROJECT_OVERSIGHT_TABLES,
        "adminVisibleFields": [
            "projects",
            "owner",
            "members",
            "models",
            "documents",
            "activity",
            "risks",
            "cost",
            "tokens",
            "permissions",
        ],
        "actions": [
            {"id": action_id, **definition}
            for action_id, definition in PROJECT_ACTIONS.items()
        ],
        "security": {
            "adminOnly": True,
            "organizationScoped": True,
            "sensitiveActionsRequireApproval": True,
            "destructiveActionsDefaultToPlanOnly": True,
            "frontendDirectModelCallAllowed": False,
        },
        "sideEffects": {
            "databaseWrite": False,
            "projectMutation": False,
            "auditWrite": False,
            "reportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_project_usage_aggregation(
    *,
    projects: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    token_events: list[dict[str, Any]],
) -> dict[str, Any]:
    thread_by_id = {str(thread.get("id") or ""): thread for thread in threads}
    threads_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    messages_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    tokens_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for thread in threads:
        threads_by_project[_thread_project_id(thread)].append(thread)
    for message in messages:
        thread = thread_by_id.get(str(message.get("threadId") or message.get("thread_id") or ""))
        if thread:
            messages_by_project[_thread_project_id(thread)].append(message)
    for event in token_events:
        tokens_by_project[_project_id(event)].append(event)

    project_rows: list[dict[str, Any]] = []
    total_tokens = 0
    total_cost = 0.0
    for project in projects:
        project_id = _project_id(project)
        project_threads = threads_by_project.get(project_id, [])
        project_messages = messages_by_project.get(project_id, [])
        project_tokens = tokens_by_project.get(project_id, [])
        token_total = sum(_token_total(event) for event in project_tokens)
        estimated_cost = round(sum(_as_float(event.get("estimated_cost_usd") or event.get("estimatedCostUsd")) for event in project_tokens), 6)
        total_tokens += token_total
        total_cost += estimated_cost
        models = Counter(_thread_model_id(thread) for thread in project_threads)
        cloud_events = [event for event in project_tokens if _is_cloud_provider(event)]
        project_rows.append(
            {
                "projectId": project_id,
                "conversationCount": len(project_threads),
                "messageCount": len(project_messages),
                "tokenTotal": token_total,
                "estimatedCostUsd": estimated_cost,
                "cloudTokenTotal": sum(_token_total(event) for event in cloud_events),
                "models": [
                    {"modelId": model_id, "conversationCount": count}
                    for model_id, count in models.most_common()
                    if model_id
                ],
            }
        )
    return {
        "usageAggregatorVersion": COGNIX_PROJECT_USAGE_AGGREGATOR_VERSION,
        "summary": {
            "projectCount": len(projects),
            "conversationCount": len(threads),
            "messageCount": len(messages),
            "tokenTotal": total_tokens,
            "estimatedCostUsd": round(total_cost, 6),
        },
        "projects": project_rows,
        "sideEffects": {
            "databaseWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def build_project_risk_analysis(
    *,
    projects: list[dict[str, Any]],
    usage_by_project: dict[str, dict[str, Any]],
    project_permissions: list[dict[str, Any]],
    security_events: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    permissions_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    security_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    audit_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    reports_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for permission in project_permissions:
        permissions_by_project[_project_id(permission)].append(permission)
    for event in security_events:
        security_by_project[_project_id(event)].append(event)
    for log in audit_logs:
        metadata = log.get("metadata") if isinstance(log.get("metadata"), dict) else {}
        project_id = _norm(log.get("project_id") or metadata.get("projectId") or log.get("resource_id"))
        if project_id:
            audit_by_project[project_id].append(log)
    for report in reports:
        metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        project_id = _norm(report.get("project_id") or metadata.get("projectId") or report.get("resource_id"))
        if project_id:
            reports_by_project[project_id].append(report)

    risk_rows: list[dict[str, Any]] = []
    for project in projects:
        project_id = _project_id(project)
        usage = usage_by_project.get(project_id, {})
        reasons: list[dict[str, Any]] = []
        score = 0
        if project.get("archived"):
            score += RISK_POINTS["archived_project"]
            reasons.append({"id": "archived_project", "label": "Project is archived", "points": RISK_POINTS["archived_project"]})
        if _as_int(usage.get("tokenTotal")) >= 100_000:
            score += RISK_POINTS["high_usage"]
            reasons.append({"id": "high_usage", "label": "High token usage", "points": RISK_POINTS["high_usage"]})
        if _as_int(usage.get("cloudTokenTotal")) > 0:
            score += RISK_POINTS["cloud_usage"]
            reasons.append({"id": "cloud_usage", "label": "Cloud model usage detected", "points": RISK_POINTS["cloud_usage"]})
        project_security = security_by_project.get(project_id, [])
        if project_security:
            score += min(40, len(project_security) * RISK_POINTS["security_events"])
            reasons.append({"id": "security_events", "label": "Security events linked to project", "count": len(project_security)})
        project_audit = audit_by_project.get(project_id, [])
        sensitive_audit = [
            log for log in project_audit
            if _norm(log.get("severity")).lower() in {"warning", "critical"}
        ]
        if sensitive_audit:
            score += min(36, len(sensitive_audit) * RISK_POINTS["sensitive_audit"])
            reasons.append({"id": "sensitive_audit", "label": "Sensitive audit entries", "count": len(sensitive_audit)})
        denied_permissions = [
            permission for permission in permissions_by_project.get(project_id, [])
            if _as_int(permission.get("allowed")) == 0 or permission.get("allowed") is False
        ]
        if denied_permissions:
            score += min(30, len(denied_permissions) * RISK_POINTS["restricted_permission"])
            reasons.append({"id": "restricted_permission", "label": "Restricted permissions", "count": len(denied_permissions)})
        open_reports = [
            report for report in reports_by_project.get(project_id, [])
            if _norm(report.get("status"), "open").lower() in {"open", "in_review", "pending"}
        ]
        if open_reports:
            score += min(32, len(open_reports) * RISK_POINTS["open_reports"])
            reasons.append({"id": "open_reports", "label": "Open reports", "count": len(open_reports)})
        bounded = _bounded_score(score)
        risk_rows.append(
            {
                "projectId": project_id,
                "riskScore": bounded,
                "riskLevel": _risk_level(bounded),
                "reasons": reasons,
                "securityEventCount": len(project_security),
                "sensitiveAuditCount": len(sensitive_audit),
                "restrictedPermissionCount": len(denied_permissions),
                "openReportCount": len(open_reports),
            }
        )
    return {
        "riskAnalyzerVersion": COGNIX_PROJECT_RISK_ANALYZER_VERSION,
        "summary": {
            "projectCount": len(projects),
            "maxScore": max((item["riskScore"] for item in risk_rows), default = 0),
            "highOrCriticalCount": sum(1 for item in risk_rows if item["riskLevel"] in {"high", "critical"}),
        },
        "projects": risk_rows,
        "sideEffects": {
            "databaseWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def build_admin_project_oversight(
    *,
    projects: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    token_events: list[dict[str, Any]],
    project_permissions: list[dict[str, Any]],
    security_events: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    admin_project_events: list[dict[str, Any]],
    project_admin_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    usage = build_project_usage_aggregation(
        projects = projects,
        threads = threads,
        messages = messages,
        token_events = token_events,
    )
    usage_by_project = {item["projectId"]: item for item in usage["projects"]}
    risk = build_project_risk_analysis(
        projects = projects,
        usage_by_project = usage_by_project,
        project_permissions = project_permissions,
        security_events = security_events,
        audit_logs = audit_logs,
        reports = reports,
    )
    risk_by_project = {item["projectId"]: item for item in risk["projects"]}
    permissions_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for permission in project_permissions:
        permissions_by_project[_project_id(permission)].append(permission)
    admin_events_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in admin_project_events:
        admin_events_by_project[_project_id(event)].append(event)
    admin_reports_by_project: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in project_admin_reports:
        admin_reports_by_project[_project_id(report)].append(report)

    project_rows = []
    for project in projects:
        project_id = _project_id(project)
        project_usage = usage_by_project.get(project_id, {})
        project_risk = risk_by_project.get(project_id, {})
        project_rows.append(
            {
                **_project_metadata(project),
                "usage": project_usage,
                "risk": project_risk,
                "permissions": permissions_by_project.get(project_id, []),
                "adminEvents": admin_events_by_project.get(project_id, [])[:20],
                "adminReports": admin_reports_by_project.get(project_id, [])[:20],
                "availableActions": [
                    {"id": action_id, **definition}
                    for action_id, definition in PROJECT_ACTIONS.items()
                ],
            }
        )
    return {
        "adminProjectServiceVersion": COGNIX_ADMIN_PROJECT_SERVICE_VERSION,
        "usageAggregatorVersion": COGNIX_PROJECT_USAGE_AGGREGATOR_VERSION,
        "riskAnalyzerVersion": COGNIX_PROJECT_RISK_ANALYZER_VERSION,
        "summary": {
            "projectCount": len(project_rows),
            "archivedProjectCount": sum(1 for item in project_rows if item["archived"]),
            "highOrCriticalRiskCount": risk["summary"]["highOrCriticalCount"],
            "tokenTotal": usage["summary"]["tokenTotal"],
            "estimatedCostUsd": usage["summary"]["estimatedCostUsd"],
            "adminEventCount": len(admin_project_events),
            "adminReportCount": len(project_admin_reports),
        },
        "projects": project_rows,
        "usage": usage,
        "risk": risk,
        "sideEffects": {
            "databaseWrite": False,
            "projectMutation": False,
            "auditWrite": False,
            "reportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_project_action_plan(
    *,
    project: dict[str, Any],
    action: str,
    actor_username: str,
    reason: str,
    target_username: str | None = None,
    target_role: str | None = None,
    model_ids: list[str] | None = None,
    cloud_allowed: bool | None = None,
) -> dict[str, Any]:
    action_id = _norm(action).lower().replace("-", "_")
    if action_id not in PROJECT_ACTIONS:
        raise ValueError("Unsupported admin project action")
    definition = PROJECT_ACTIONS[action_id]
    project_info = _project_metadata(project)
    missing_fields: list[str] = []
    if action_id in {"transfer_ownership", "add_member", "remove_member"} and not _norm(target_username):
        missing_fields.append("targetUsername")
    if action_id == "add_member" and not _norm(target_role):
        missing_fields.append("targetRole")
    if action_id == "restrict_models" and not (model_ids or []):
        missing_fields.append("modelIds")
    if action_id == "disable_cloud" and cloud_allowed is None:
        cloud_allowed = False

    ready = not missing_fields and bool(_norm(reason))
    return {
        "projectActionPlannerVersion": COGNIX_PROJECT_ACTION_PLANNER_VERSION,
        "projectId": project_info["projectId"],
        "project": project_info,
        "action": {"id": action_id, **definition},
        "actorUsername": _norm(actor_username),
        "reason": _norm(reason),
        "target": {
            "targetUsername": _norm(target_username),
            "targetRole": _norm(target_role),
            "modelIds": list(model_ids or []),
            "cloudAllowed": bool(cloud_allowed) if cloud_allowed is not None else None,
        },
        "readyForApproval": ready,
        "missingFields": missing_fields if _norm(reason) else [*missing_fields, "reason"],
        "approvalRequired": bool(definition["approvalRequired"]),
        "confirmationRequired": bool(definition["approvalRequired"] or definition["destructive"]),
        "permissionRequired": definition["permission"],
        "executionMode": "plan_only_until_approval",
        "sideEffects": {
            "databaseWrite": False,
            "projectMutation": False,
            "approvalWrite": False,
            "auditWrite": False,
            "reportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_project_admin_report(
    *,
    project: dict[str, Any],
    oversight_item: dict[str, Any],
    generated_by: str,
    report_type: str = "summary",
    output_format: str = "json",
) -> dict[str, Any]:
    project_info = _project_metadata(project)
    usage = oversight_item.get("usage") if isinstance(oversight_item.get("usage"), dict) else {}
    risk = oversight_item.get("risk") if isinstance(oversight_item.get("risk"), dict) else {}
    summary = (
        f"{project_info['name']} has {usage.get('conversationCount', 0)} conversation(s), "
        f"{usage.get('tokenTotal', 0)} token(s), and {risk.get('riskLevel', 'low')} risk."
    )
    return {
        "projectReportVersion": COGNIX_PROJECT_REPORT_VERSION,
        "projectId": project_info["projectId"],
        "project": project_info,
        "generatedBy": _norm(generated_by),
        "reportType": _norm(report_type, "summary") or "summary",
        "outputFormat": _norm(output_format, "json") or "json",
        "title": f"Project oversight report - {project_info['name']}",
        "summary": summary,
        "riskLevel": _norm(risk.get("riskLevel"), "low") or "low",
        "payload": {
            "project": project_info,
            "usage": usage,
            "risk": risk,
            "permissions": oversight_item.get("permissions") or [],
            "adminEvents": oversight_item.get("adminEvents") or [],
        },
        "sideEffects": {
            "databaseWrite": False,
            "reportWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }
