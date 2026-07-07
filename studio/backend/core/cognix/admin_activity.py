# SPDX-License-Identifier: AGPL-3.0-only

"""CogniX native admin activity monitoring and daily aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


COGNIX_ACTIVITY_MONITORING_VERSION = "cognix_activity_monitoring_v2"
COGNIX_ACTIVITY_AGGREGATOR_VERSION = "cognix_activity_aggregator_v1"
COGNIX_ADMIN_ACTIVITY_DASHBOARD_VERSION = "cognix_admin_activity_dashboard_v1"

SENSITIVE_ACTION_KEYWORDS = (
    "admin",
    "permission",
    "policy",
    "approval",
    "ban",
    "export",
    "secret",
    "token",
    "limit",
    "cloud",
    "tool",
    "codex",
)
ERROR_KEYWORDS = ("error", "failed", "denied", "blocked", "critical", "warning")


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _day(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if abs(timestamp) > 100_000_000_000:
            timestamp = timestamp / 1000
        try:
            return datetime.fromtimestamp(timestamp, tz = timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return datetime.now(timezone.utc).date().isoformat()
    text = _norm(value)
    if not text:
        return datetime.now(timezone.utc).date().isoformat()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        try:
            timestamp = float(text)
            if abs(timestamp) > 100_000_000_000:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp, tz = timezone.utc).date().isoformat()
        except (OverflowError, OSError, TypeError, ValueError):
            return datetime.now(timezone.utc).date().isoformat()


def _username(row: dict[str, Any]) -> str:
    return _norm(row.get("username") or row.get("owner_username") or row.get("ownerUsername"), "unknown")


def _created_at(row: dict[str, Any]) -> Any:
    return _first(row, "created_at", "createdAt", default = None)


def _project_id(row: dict[str, Any]) -> str:
    return _norm(row.get("project_id") or row.get("projectId"))


def _model_id(row: dict[str, Any]) -> str:
    return _norm(row.get("model_id") or row.get("modelId") or row.get("modelType") or row.get("model_type"), "unknown")


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("metadata")
    return value if isinstance(value, dict) else {}


def _is_sensitive_action(action: str) -> bool:
    lowered = action.lower()
    return any(keyword in lowered for keyword in SENSITIVE_ACTION_KEYWORDS)


def _is_error_signal(*values: Any) -> bool:
    text = " ".join(_norm(value).lower() for value in values)
    return any(keyword in text for keyword in ERROR_KEYWORDS)


def build_activity_monitoring_blueprint() -> dict[str, Any]:
    return {
        "activityMonitoringVersion": COGNIX_ACTIVITY_MONITORING_VERSION,
        "activityAggregatorVersion": COGNIX_ACTIVITY_AGGREGATOR_VERSION,
        "adminActivityDashboardVersion": COGNIX_ADMIN_ACTIVITY_DASHBOARD_VERSION,
        "mode": "native_activity_monitoring_rollups",
        "services": [
            "ActivityMonitoringService",
            "ActivityAggregator",
            "AdminActivityDashboard",
        ],
        "tables": [
            "cognix_user_activity_events",
            "cognix_user_activity_daily",
            "cognix_organization_activity_daily",
        ],
        "signals": [
            "messages",
            "models",
            "tools",
            "documents",
            "projects",
            "tokens",
            "errors",
            "sensitive_actions",
            "estimated_active_minutes",
        ],
        "sideEffects": {
            "activityEventWrite": False,
            "userDailyWrite": False,
            "organizationDailyWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _empty_user_bucket(username: str, day: str) -> dict[str, Any]:
    return {
        "username": username,
        "day": day,
        "messageCount": 0,
        "tokenTotal": 0,
        "toolCallCount": 0,
        "documentAccessCount": 0,
        "errorCount": 0,
        "sensitiveActionCount": 0,
        "activeMinutes": 0,
        "activityScore": 0,
        "models": Counter(),
        "projects": Counter(),
        "actions": Counter(),
        "signalTimestamps": set(),
    }


def _touch(bucket: dict[str, Any], created_at: Any) -> None:
    bucket["signalTimestamps"].add(_norm(created_at) or f"{bucket['day']}:unknown")


def _finalize_user_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    models = bucket["models"]
    projects = bucket["projects"]
    actions = bucket["actions"]
    active_minutes = min(720, max(bucket["activeMinutes"], len(bucket["signalTimestamps"]) * 5))
    score = (
        bucket["messageCount"] * 2
        + bucket["tokenTotal"] / 250
        + bucket["toolCallCount"] * 3
        + bucket["documentAccessCount"] * 2
        + bucket["sensitiveActionCount"] * 5
        + active_minutes / 10
    )
    return {
        "username": bucket["username"],
        "day": bucket["day"],
        "messageCount": int(bucket["messageCount"]),
        "modelCount": len(models),
        "toolCallCount": int(bucket["toolCallCount"]),
        "documentAccessCount": int(bucket["documentAccessCount"]),
        "activeProjectCount": len(projects),
        "tokenTotal": int(bucket["tokenTotal"]),
        "errorCount": int(bucket["errorCount"]),
        "sensitiveActionCount": int(bucket["sensitiveActionCount"]),
        "activeMinutes": int(active_minutes),
        "activityScore": round(score, 2),
        "models": [{"modelId": key, "count": value} for key, value in models.most_common()],
        "projects": [{"projectId": key, "count": value} for key, value in projects.most_common() if key],
        "actions": [{"action": key, "count": value} for key, value in actions.most_common()],
        "metadata": {
            "signalCount": len(bucket["signalTimestamps"]),
            "activityAggregatorVersion": COGNIX_ACTIVITY_AGGREGATOR_VERSION,
        },
    }


def _organization_from_users(day: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    model_counter: Counter[str] = Counter()
    project_counter: Counter[str] = Counter()
    for row in rows:
        for item in row["models"]:
            model_counter[str(item["modelId"])] += _as_int(item.get("count"))
        for item in row["projects"]:
            project_counter[str(item["projectId"])] += _as_int(item.get("count"))
    return {
        "day": day,
        "activeUserCount": len({row["username"] for row in rows}),
        "messageCount": sum(_as_int(row["messageCount"]) for row in rows),
        "tokenTotal": sum(_as_int(row["tokenTotal"]) for row in rows),
        "modelCount": len(model_counter),
        "toolCallCount": sum(_as_int(row["toolCallCount"]) for row in rows),
        "documentAccessCount": sum(_as_int(row["documentAccessCount"]) for row in rows),
        "activeProjectCount": len(project_counter),
        "errorCount": sum(_as_int(row["errorCount"]) for row in rows),
        "sensitiveActionCount": sum(_as_int(row["sensitiveActionCount"]) for row in rows),
        "activeMinutes": sum(_as_int(row["activeMinutes"]) for row in rows),
        "topUsers": [
            {
                "username": row["username"],
                "activityScore": row["activityScore"],
                "messageCount": row["messageCount"],
                "tokenTotal": row["tokenTotal"],
            }
            for row in sorted(rows, key = lambda item: item["activityScore"], reverse = True)[:10]
        ],
        "models": [{"modelId": key, "count": value} for key, value in model_counter.most_common()],
        "projects": [{"projectId": key, "count": value} for key, value in project_counter.most_common() if key],
        "metadata": {
            "activityAggregatorVersion": COGNIX_ACTIVITY_AGGREGATOR_VERSION,
        },
    }


def build_activity_rollups(
    *,
    users: list[dict[str, Any]],
    activity_events: list[dict[str, Any]],
    token_events: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    conversation_metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    known_users = {_norm(user.get("username")) for user in users if _norm(user.get("username"))}
    buckets: dict[tuple[str, str], dict[str, Any]] = {}

    def bucket(username: str, day: str) -> dict[str, Any]:
        clean_username = username if username in known_users or username != "unknown" else username
        key = (clean_username, day)
        if key not in buckets:
            buckets[key] = _empty_user_bucket(clean_username, day)
        return buckets[key]

    thread_index = {_norm(thread.get("id")): thread for thread in threads}
    for message in messages:
        thread = thread_index.get(_norm(message.get("threadId") or message.get("thread_id")), {})
        username = _username(thread)
        day = _day(_created_at(message) or _created_at(thread))
        item = bucket(username, day)
        item["messageCount"] += 1
        item["models"][_model_id(thread)] += 1
        project_id = _project_id(thread)
        if project_id:
            item["projects"][project_id] += 1
        item["actions"][f"message:{_norm(message.get('role'), 'unknown')}"] += 1
        _touch(item, _created_at(message))

    for event in activity_events:
        username = _username(event)
        day = _day(_created_at(event))
        item = bucket(username, day)
        action = _norm(event.get("event_type") or event.get("eventType"), "activity")
        item["actions"][action] += 1
        if _is_sensitive_action(action):
            item["sensitiveActionCount"] += 1
        if _is_error_signal(action, event.get("resource_type") or event.get("resourceType"), _metadata(event)):
            item["errorCount"] += 1
        _touch(item, _created_at(event))

    for event in token_events:
        username = _username(event)
        day = _day(_created_at(event))
        item = bucket(username, day)
        item["tokenTotal"] += _as_int(event.get("total_tokens") or event.get("totalTokens"))
        item["models"][_model_id(event)] += 1
        project_id = _project_id(event)
        if project_id:
            item["projects"][project_id] += 1
        item["actions"]["token_usage"] += 1
        _touch(item, _created_at(event))

    for log in audit_logs:
        username = _norm(log.get("username") or log.get("actor_username") or log.get("actorUsername"), "system")
        day = _day(_created_at(log))
        item = bucket(username, day)
        action = _norm(log.get("action"), "audit")
        item["actions"][f"audit:{action}"] += 1
        if _is_sensitive_action(action):
            item["sensitiveActionCount"] += 1
        if _is_error_signal(action, log.get("severity")):
            item["errorCount"] += 1
        _touch(item, _created_at(log))

    for record in conversation_metadata:
        username = _username(record)
        day = _day(record.get("updated_at") or record.get("updatedAt"))
        item = bucket(username, day)
        item["toolCallCount"] += _as_int(record.get("tool_call_count") or record.get("toolCallCount"))
        item["documentAccessCount"] += _as_int(record.get("document_access_count") or record.get("documentAccessCount"))
        item["models"][_model_id(record)] += 1
        project_id = _project_id(record)
        if project_id:
            item["projects"][project_id] += 1
        _touch(item, record.get("updated_at") or record.get("updatedAt"))

    user_daily = [_finalize_user_bucket(item) for item in buckets.values()]
    user_daily.sort(key = lambda item: (item["day"], item["username"]), reverse = True)
    by_day: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in user_daily:
        by_day[row["day"]].append(row)
    organization_daily = [_organization_from_users(day, rows) for day, rows in by_day.items()]
    organization_daily.sort(key = lambda item: item["day"], reverse = True)

    return {
        "activityMonitoringVersion": COGNIX_ACTIVITY_MONITORING_VERSION,
        "activityAggregatorVersion": COGNIX_ACTIVITY_AGGREGATOR_VERSION,
        "adminActivityDashboardVersion": COGNIX_ADMIN_ACTIVITY_DASHBOARD_VERSION,
        "mode": "admin_activity_rollups",
        "summary": {
            "activeUserCount": len({row["username"] for row in user_daily}),
            "dayCount": len(organization_daily),
            "messageCount": sum(_as_int(row["messageCount"]) for row in user_daily),
            "tokenTotal": sum(_as_int(row["tokenTotal"]) for row in user_daily),
            "toolCallCount": sum(_as_int(row["toolCallCount"]) for row in user_daily),
            "documentAccessCount": sum(_as_int(row["documentAccessCount"]) for row in user_daily),
            "errorCount": sum(_as_int(row["errorCount"]) for row in user_daily),
            "sensitiveActionCount": sum(_as_int(row["sensitiveActionCount"]) for row in user_daily),
        },
        "userDaily": user_daily,
        "organizationDaily": organization_daily,
        "sideEffects": build_activity_monitoring_blueprint()["sideEffects"],
    }
