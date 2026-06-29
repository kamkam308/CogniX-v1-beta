# SPDX-License-Identifier: AGPL-3.0-only

"""Native CogniX admin token/model usage aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


COGNIX_USAGE_DASHBOARD_VERSION = "cognix_usage_dashboard_v1"
COGNIX_TOKEN_USAGE_SERVICE_VERSION = "cognix_token_usage_service_v1"
COGNIX_MODEL_USAGE_AGGREGATOR_VERSION = "cognix_model_usage_aggregator_v1"
COGNIX_COST_ESTIMATOR_VERSION = "cognix_cost_estimator_v1"
COGNIX_USAGE_DASHBOARD_SERVICE_VERSION = "cognix_usage_dashboard_service_v1"

LOCAL_PROVIDER_HINTS = {"local", "ollama", "llama", "gguf", "unsloth", "mlx", "vllm-local", "cpu"}
CLOUD_PROVIDER_HINTS = {
    "openai",
    "anthropic",
    "google",
    "gemini",
    "openrouter",
    "mistral",
    "groq",
    "together",
    "fireworks",
    "kaggle",
    "colab",
    "cloud",
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
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _username(row: dict[str, Any]) -> str:
    return _norm(row.get("username") or row.get("owner_username") or row.get("ownerUsername"), "unknown") or "unknown"


def _model_id(row: dict[str, Any]) -> str:
    return _norm(row.get("model_id") or row.get("modelId"), "unknown") or "unknown"


def _project_id(row: dict[str, Any]) -> str:
    return _norm(row.get("project_id") or row.get("projectId"), "none") or "none"


def _organization_id(row: dict[str, Any]) -> str:
    return _norm(row.get("organization_id") or row.get("organizationId"), "default") or "default"


def _provider(row: dict[str, Any]) -> str:
    return _norm(row.get("provider"), "local").lower() or "local"


def provider_scope(provider: str) -> str:
    normalized = _norm(provider, "local").casefold()
    if any(hint in normalized for hint in CLOUD_PROVIDER_HINTS):
        return "cloud"
    if any(hint in normalized for hint in LOCAL_PROVIDER_HINTS):
        return "local"
    return "cloud" if normalized not in {"", "local"} else "local"


def _input_tokens(row: dict[str, Any]) -> int:
    return max(0, _as_int(row.get("input_tokens") or row.get("inputTokens")))


def _output_tokens(row: dict[str, Any]) -> int:
    return max(0, _as_int(row.get("output_tokens") or row.get("outputTokens")))


def _total_tokens(row: dict[str, Any]) -> int:
    total = max(0, _as_int(row.get("total_tokens") or row.get("totalTokens")))
    return total or _input_tokens(row) + _output_tokens(row)


def _message_count(row: dict[str, Any]) -> int:
    return max(1, _as_int(row.get("message_count") or row.get("messageCount") or 1))


def _latency_ms(row: dict[str, Any]) -> float:
    return max(0.0, _as_float(row.get("latency_ms") or row.get("latencyMs")))


def _cost_usd(row: dict[str, Any]) -> float:
    return max(0.0, _as_float(row.get("estimated_cost_usd") or row.get("estimatedCostUsd")))


def _created_at(row: dict[str, Any]) -> datetime:
    raw = _norm(row.get("created_at") or row.get("createdAt"))
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _day_key(row: dict[str, Any]) -> str:
    return _created_at(row).date().isoformat()


def _week_key(row: dict[str, Any]) -> str:
    dt = _created_at(row).date()
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _month_key(row: dict[str, Any]) -> str:
    dt = _created_at(row).date()
    return f"{dt.year:04d}-{dt.month:02d}"


def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = sum(_input_tokens(item) for item in events)
    output_tokens = sum(_output_tokens(item) for item in events)
    total_tokens = sum(_total_tokens(item) for item in events) or input_tokens + output_tokens
    message_count = sum(_message_count(item) for item in events)
    cost = sum(_cost_usd(item) for item in events)
    latency_values = [_latency_ms(item) for item in events if _latency_ms(item) > 0]
    local_tokens = sum(_total_tokens(item) for item in events if provider_scope(_provider(item)) == "local")
    cloud_tokens = sum(_total_tokens(item) for item in events if provider_scope(_provider(item)) == "cloud")
    providers = Counter(_provider(item) for item in events)
    models = {_model_id(item) for item in events}
    users = {_username(item) for item in events}
    projects = {_project_id(item) for item in events if _project_id(item) != "none"}
    return {
        "eventCount": len(events),
        "messageCount": message_count,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "modelsUsed": len(models),
        "userCount": len(users),
        "projectCount": len(projects),
        "estimatedCostUsd": round(cost, 6),
        "averageLatencyMs": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0,
        "localTokens": local_tokens,
        "cloudTokens": cloud_tokens,
        "providerSplit": [
            {"provider": key, "scope": provider_scope(key), "count": count}
            for key, count in providers.most_common()
        ],
    }


def _group_by(events: list[dict[str, Any]], key_fn) -> dict[str, list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[key_fn(event)].append(event)
    return dict(grouped)


def _ranked(grouped: dict[str, list[dict[str, Any]]], *, key_name: str, limit: int | None = None) -> list[dict[str, Any]]:
    rows = [{key_name: key, **_summarize(items)} for key, items in grouped.items()]
    rows.sort(key = lambda item: (-_as_int(item.get("totalTokens")), str(item.get(key_name) or "")))
    return rows[:limit] if limit else rows


def build_usage_blueprint() -> dict[str, Any]:
    return {
        "usageDashboardVersion": COGNIX_USAGE_DASHBOARD_VERSION,
        "tokenUsageServiceVersion": COGNIX_TOKEN_USAGE_SERVICE_VERSION,
        "modelUsageAggregatorVersion": COGNIX_MODEL_USAGE_AGGREGATOR_VERSION,
        "costEstimatorVersion": COGNIX_COST_ESTIMATOR_VERSION,
        "usageDashboardServiceVersion": COGNIX_USAGE_DASHBOARD_SERVICE_VERSION,
        "mode": "native_token_model_usage_dashboard",
        "services": ["TokenUsageService", "ModelUsageAggregator", "CostEstimator", "UsageDashboardService"],
        "tables": [
            "cognix_token_usage_events",
            "cognix_daily_user_token_usage",
            "cognix_daily_model_usage",
            "cognix_organization_usage_summary",
        ],
        "charts": ["usage_by_day", "usage_by_model", "usage_by_user", "local_vs_cloud", "cost_estimate"],
        "loggingRule": {
            "requiredFields": [
                "user_id",
                "organization_id",
                "project_id",
                "model_id",
                "provider",
                "input_tokens",
                "output_tokens",
                "latency",
                "cost_estimate",
                "timestamp",
            ],
            "nativeTable": "cognix_token_usage_events",
        },
        "sideEffects": {
            "tokenUsageWrite": False,
            "rollupWrite": False,
            "databaseWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_usage_dashboard(
    *,
    token_events: list[dict[str, Any]],
    persisted_user_daily: list[dict[str, Any]] | None = None,
    persisted_model_daily: list[dict[str, Any]] | None = None,
    persisted_org_summary: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = list(token_events or [])
    by_user = _group_by(events, _username)
    by_model = _group_by(events, _model_id)
    by_project = _group_by(events, _project_id)
    by_day = _group_by(events, _day_key)
    by_week = _group_by(events, _week_key)
    by_month = _group_by(events, _month_key)
    by_scope = _group_by(events, lambda item: provider_scope(_provider(item)))
    by_org = _group_by(events, _organization_id)

    day_rows = _ranked(by_day, key_name = "day")
    day_rows.sort(key = lambda item: item["day"])
    model_rows = _ranked(by_model, key_name = "modelId")
    user_rows = _ranked(by_user, key_name = "username")
    project_rows = _ranked(by_project, key_name = "projectId")
    scope_rows = _ranked(by_scope, key_name = "scope")

    org_id = next(iter(by_org.keys()), "default")
    org_events = by_org.get(org_id, events)
    top_users = _ranked(_group_by(org_events, _username), key_name = "username", limit = 5)
    top_models = _ranked(_group_by(org_events, _model_id), key_name = "modelId", limit = 5)
    peak_day = max(day_rows, key = lambda item: _as_int(item.get("totalTokens")), default = None)

    daily_user_rollups = []
    for day, day_events in by_day.items():
        for username, user_events in _group_by(day_events, _username).items():
            models = _ranked(_group_by(user_events, _model_id), key_name = "modelId", limit = 8)
            summary = _summarize(user_events)
            daily_user_rollups.append(
                {
                    "organizationId": _organization_id(user_events[0]) if user_events else "default",
                    "username": username,
                    "day": day,
                    **summary,
                    "modelCount": summary["modelsUsed"],
                    "models": [{"modelId": item["modelId"], "totalTokens": item["totalTokens"]} for item in models],
                }
            )

    daily_model_rollups = []
    for day, day_events in by_day.items():
        for model_id, model_events in _group_by(day_events, _model_id).items():
            providers = Counter(_provider(item) for item in model_events)
            users = _ranked(_group_by(model_events, _username), key_name = "username", limit = 8)
            summary = _summarize(model_events)
            daily_model_rollups.append(
                {
                    "organizationId": _organization_id(model_events[0]) if model_events else "default",
                    "modelId": model_id,
                    "day": day,
                    **summary,
                    "providers": [{"provider": key, "count": count} for key, count in providers.most_common()],
                    "users": [{"username": item["username"], "totalTokens": item["totalTokens"]} for item in users],
                }
            )

    organization_summary = {
        "organizationId": org_id,
        "periodType": "all_time",
        "periodKey": "all_time",
        **_summarize(org_events),
        "topUsers": [{"username": item["username"], "totalTokens": item["totalTokens"]} for item in top_users],
        "topModels": [{"modelId": item["modelId"], "totalTokens": item["totalTokens"]} for item in top_models],
        "peakDay": peak_day["day"] if peak_day else None,
        "localCloudSplit": scope_rows,
    }

    blueprint = build_usage_blueprint()
    return {
        "usageDashboardVersion": COGNIX_USAGE_DASHBOARD_VERSION,
        "tokenUsageServiceVersion": COGNIX_TOKEN_USAGE_SERVICE_VERSION,
        "modelUsageAggregatorVersion": COGNIX_MODEL_USAGE_AGGREGATOR_VERSION,
        "costEstimatorVersion": COGNIX_COST_ESTIMATOR_VERSION,
        "usageDashboardServiceVersion": COGNIX_USAGE_DASHBOARD_SERVICE_VERSION,
        "mode": "admin_token_model_usage_dashboard",
        "summary": _summarize(events),
        "byUser": sorted(user_rows, key = lambda item: str(item["username"])),
        "byModel": sorted(model_rows, key = lambda item: str(item["modelId"])),
        "byProject": sorted(project_rows, key = lambda item: str(item["projectId"])),
        "byDay": day_rows,
        "byWeek": sorted(_ranked(by_week, key_name = "week"), key = lambda item: item["week"]),
        "byMonth": sorted(_ranked(by_month, key_name = "month"), key = lambda item: item["month"]),
        "byProviderScope": sorted(scope_rows, key = lambda item: str(item["scope"])),
        "organization": organization_summary,
        "charts": {
            "usageByDay": day_rows,
            "usageByModel": model_rows[:12],
            "usageByUser": user_rows[:12],
            "localVsCloud": sorted(scope_rows, key = lambda item: str(item["scope"])),
            "costEstimate": [
                {
                    "day": item["day"],
                    "estimatedCostUsd": item["estimatedCostUsd"],
                    "totalTokens": item["totalTokens"],
                }
                for item in day_rows
            ],
        },
        "rollups": {
            "dailyUserTokenUsage": sorted(daily_user_rollups, key = lambda item: (item["day"], item["username"])),
            "dailyModelUsage": sorted(daily_model_rollups, key = lambda item: (item["day"], item["modelId"])),
            "organizationUsageSummary": [organization_summary],
            "persistedDailyUserTokenUsage": persisted_user_daily or [],
            "persistedDailyModelUsage": persisted_model_daily or [],
            "persistedOrganizationUsageSummary": persisted_org_summary or [],
        },
        "loggingRule": blueprint["loggingRule"],
        "sideEffects": blueprint["sideEffects"],
    }
