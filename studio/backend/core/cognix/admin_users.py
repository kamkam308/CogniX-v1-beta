# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native admin user, activity, limits, and usage services."""

from __future__ import annotations

from collections import Counter
from typing import Any


COGNIX_ADMIN_USER_SERVICE_VERSION = "cognix_admin_user_service_v1"
COGNIX_ACTIVITY_MONITORING_VERSION = "cognix_activity_monitoring_v1"
COGNIX_LIMIT_SERVICE_VERSION = "cognix_limit_service_v1"
COGNIX_USAGE_DASHBOARD_VERSION = "cognix_usage_dashboard_v1"

DEFAULT_LIMITS: list[dict[str, Any]] = [
    {"limitKey": "tokens_daily", "defaultValue": 100000, "unit": "tokens", "category": "tokens"},
    {"limitKey": "tokens_monthly", "defaultValue": 2500000, "unit": "tokens", "category": "tokens"},
    {"limitKey": "messages_daily", "defaultValue": 500, "unit": "messages", "category": "chat"},
    {"limitKey": "models_installable", "defaultValue": 12, "unit": "models", "category": "models"},
    {"limitKey": "cloud_model_access", "defaultValue": 0, "unit": "boolean", "category": "models"},
    {"limitKey": "tools_access", "defaultValue": 1, "unit": "boolean", "category": "tools"},
    {"limitKey": "images_generation", "defaultValue": 50, "unit": "images/day", "category": "images"},
    {"limitKey": "codex_access", "defaultValue": 0, "unit": "boolean", "category": "codex"},
    {"limitKey": "cowork_access", "defaultValue": 0, "unit": "boolean", "category": "cowork"},
    {"limitKey": "scheduled_tasks", "defaultValue": 20, "unit": "tasks", "category": "automation"},
]


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _username(row: dict[str, Any]) -> str:
    return str(row.get("username") or row.get("owner_username") or row.get("ownerUsername") or "").strip()


def build_admin_users_blueprint() -> dict[str, Any]:
    return {
        "adminUserServiceVersion": COGNIX_ADMIN_USER_SERVICE_VERSION,
        "activityMonitoringVersion": COGNIX_ACTIVITY_MONITORING_VERSION,
        "limitServiceVersion": COGNIX_LIMIT_SERVICE_VERSION,
        "usageDashboardVersion": COGNIX_USAGE_DASHBOARD_VERSION,
        "mode": "admin_essential_native_services",
        "services": [
            "AdminUserService",
            "UserActivityService",
            "UserLimitService",
            "UserPermissionService",
            "ActivityMonitoringService",
            "TokenUsageService",
            "ModelUsageAggregator",
        ],
        "tables": [
            "cognix_admin_user_views",
            "cognix_user_limits",
            "cognix_user_activity_events",
            "cognix_token_usage_events",
        ],
        "permissions": [
            "admin:users:read",
            "admin:users:update",
            "admin:permissions:update",
            "admin:limits:update",
        ],
        "sideEffects": {
            "adminViewLogWrite": False,
            "limitWrite": False,
            "activityEventWrite": False,
            "tokenUsageWrite": False,
            "permissionGrant": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _limits_for_user(username: str, limits: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    custom = {str(item.get("limit_key") or item.get("limitKey")): item for item in limits if _username(item) == username}
    merged: dict[str, dict[str, Any]] = {}
    for default in DEFAULT_LIMITS:
        key = default["limitKey"]
        override = custom.get(key, {})
        merged[key] = {
            **default,
            "value": _as_float(override.get("limit_value") or override.get("limitValue") or default["defaultValue"]),
            "unit": override.get("unit") or default["unit"],
            "scope": override.get("scope") or "user",
            "updatedBy": override.get("updated_by") or override.get("updatedBy"),
            "updatedAt": override.get("updated_at") or override.get("updatedAt"),
            "overridden": bool(override),
        }
    return merged


def _usage_for_user(username: str, token_events: list[dict[str, Any]]) -> dict[str, Any]:
    events = [item for item in token_events if _username(item) == username]
    model_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cost = 0.0
    for item in events:
        input_tokens += _as_int(item.get("input_tokens") or item.get("inputTokens"))
        output_tokens += _as_int(item.get("output_tokens") or item.get("outputTokens"))
        total_tokens += _as_int(item.get("total_tokens") or item.get("totalTokens"))
        cost += _as_float(item.get("estimated_cost_usd") or item.get("estimatedCostUsd"))
        model = str(item.get("model_id") or item.get("modelId") or "unknown")
        provider = str(item.get("provider") or "local")
        model_counts[model] += 1
        provider_counts[provider] += 1
    return {
        "eventCount": len(events),
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens or input_tokens + output_tokens,
        "estimatedCostUsd": round(cost, 6),
        "topModels": [{"modelId": key, "count": count} for key, count in model_counts.most_common(5)],
        "providers": [{"provider": key, "count": count} for key, count in provider_counts.most_common(5)],
    }


def _activity_for_user(
    username: str,
    *,
    audit_logs: list[dict[str, Any]],
    activity_events: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    user_audits = [item for item in audit_logs if _username(item) == username]
    user_events = [item for item in activity_events if _username(item) == username]
    user_projects = [item for item in projects if _username(item) == username]
    user_threads = [item for item in threads if _username(item) == username]
    user_bans = [item for item in bans if _username(item) == username]
    user_reports = [item for item in reports if _username(item) == username]
    action_counts = Counter(str(item.get("action") or item.get("event_type") or item.get("eventType") or "unknown") for item in [*user_audits, *user_events])
    active_ban = any(str(item.get("status") or "") in {"pending_admin_review", "active", "permanent"} for item in user_bans)
    risk_level = "critical" if active_ban else "medium" if user_reports or len(user_audits) >= 10 else "low"
    return {
        "auditEvents": len(user_audits),
        "activityEvents": len(user_events),
        "projects": len(user_projects),
        "threads": len(user_threads),
        "reports": len(user_reports),
        "activeBan": active_ban,
        "riskLevel": risk_level,
        "recentActions": [{"action": key, "count": count} for key, count in action_counts.most_common(8)],
        "lastActivityAt": max(
            [
                str(item.get("created_at") or item.get("createdAt") or "")
                for item in [*user_audits, *user_events, *user_threads, *user_projects]
            ],
            default = None,
        ),
    }


def _permission_summary(username: str, permissions: list[dict[str, Any]]) -> dict[str, Any]:
    user_permissions = [item for item in permissions if _username(item) == username]
    keys = [str(item.get("permission_key") or item.get("permissionKey") or "") for item in user_permissions]
    sensitive = [
        key
        for key in keys
        if key.startswith("admin") or "cloud" in key or "codex" in key or "cowork" in key or "terminal" in key
    ]
    return {
        "permissionCount": len(keys),
        "permissionKeys": sorted(key for key in keys if key),
        "sensitivePermissionCount": len(sensitive),
    }


def build_admin_user_directory(
    *,
    users: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    limits: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    activity_events: list[dict[str, Any]],
    token_events: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for user in users:
        username = str(user.get("username") or "")
        activity = _activity_for_user(
            username,
            audit_logs = audit_logs,
            activity_events = activity_events,
            projects = projects,
            threads = threads,
            bans = bans,
            reports = reports,
        )
        usage = _usage_for_user(username, token_events)
        row = {
            "username": username,
            "email": user.get("email"),
            "displayName": user.get("displayName") or username,
            "role": user.get("role") or "user",
            "plan": user.get("plan") or "free",
            "status": "locked" if user.get("loginLocked") else "active",
            "lastLoginAt": user.get("lastLoginAt"),
            "createdAt": user.get("createdAt"),
            "activity": activity,
            "usage": usage,
            "permissions": _permission_summary(username, permissions),
            "limits": _limits_for_user(username, limits),
        }
        rows.append(row)
    risk_counts = Counter(str(item["activity"]["riskLevel"]) for item in rows)
    return {
        "adminUserServiceVersion": COGNIX_ADMIN_USER_SERVICE_VERSION,
        "activityMonitoringVersion": COGNIX_ACTIVITY_MONITORING_VERSION,
        "limitServiceVersion": COGNIX_LIMIT_SERVICE_VERSION,
        "usageDashboardVersion": COGNIX_USAGE_DASHBOARD_VERSION,
        "mode": "admin_user_directory",
        "users": rows,
        "summary": {
            "userCount": len(rows),
            "activeUsers": sum(1 for item in rows if item["status"] == "active"),
            "lockedUsers": sum(1 for item in rows if item["status"] == "locked"),
            "totalTokens": sum(_as_int(item["usage"]["totalTokens"]) for item in rows),
            "estimatedCostUsd": round(sum(_as_float(item["usage"]["estimatedCostUsd"]) for item in rows), 6),
            "riskCounts": dict(risk_counts),
        },
        "sideEffects": build_admin_users_blueprint()["sideEffects"],
    }


def build_admin_user_detail(username: str, directory: dict[str, Any], admin_views: list[dict[str, Any]]) -> dict[str, Any]:
    user = next((item for item in directory.get("users", []) if item.get("username") == username), None)
    return {
        "adminUserServiceVersion": COGNIX_ADMIN_USER_SERVICE_VERSION,
        "mode": "admin_user_detail",
        "username": username,
        "user": user,
        "found": user is not None,
        "adminViews": [item for item in admin_views if str(item.get("target_username") or item.get("targetUsername")) == username][:50],
        "sideEffects": build_admin_users_blueprint()["sideEffects"],
    }


def build_usage_dashboard(*, token_events: list[dict[str, Any]]) -> dict[str, Any]:
    from core.cognix import admin_usage as cognix_admin_usage

    return cognix_admin_usage.build_usage_dashboard(token_events = token_events)
