# SPDX-License-Identifier: AGPL-3.0-only

"""CogniX native admin limits, quotas, usage, and enforcement planning."""

from __future__ import annotations

from typing import Any


COGNIX_LIMIT_SERVICE_VERSION = "cognix_limit_service_v2"
COGNIX_QUOTA_MANAGER_VERSION = "cognix_quota_manager_v1"
COGNIX_USAGE_ENFORCER_VERSION = "cognix_usage_enforcer_v1"

DEFAULT_QUOTAS: list[dict[str, Any]] = [
    {"quotaKey": "tokens_daily", "defaultValue": 100000, "unit": "tokens", "period": "day", "category": "tokens"},
    {"quotaKey": "tokens_monthly", "defaultValue": 2500000, "unit": "tokens", "period": "month", "category": "tokens"},
    {"quotaKey": "messages_daily", "defaultValue": 500, "unit": "messages", "period": "day", "category": "chat"},
    {"quotaKey": "models_installable", "defaultValue": 12, "unit": "models", "period": "total", "category": "models"},
    {"quotaKey": "cloud_model_access", "defaultValue": 0, "unit": "boolean", "period": "always", "category": "models"},
    {"quotaKey": "tools_access", "defaultValue": 1, "unit": "boolean", "period": "always", "category": "tools"},
    {"quotaKey": "images_generation", "defaultValue": 50, "unit": "images", "period": "day", "category": "images"},
    {"quotaKey": "codex_access", "defaultValue": 0, "unit": "boolean", "period": "always", "category": "codex"},
    {"quotaKey": "cowork_access", "defaultValue": 0, "unit": "boolean", "period": "always", "category": "cowork"},
    {"quotaKey": "scheduled_tasks", "defaultValue": 20, "unit": "tasks", "period": "total", "category": "automation"},
]


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _quota_key(row: dict[str, Any]) -> str:
    return _norm(row.get("quota_key") or row.get("quotaKey") or row.get("limit_key") or row.get("limitKey"))


def _quota_value(row: dict[str, Any]) -> float:
    return _as_float(row.get("quota_value") or row.get("quotaValue") or row.get("limit_value") or row.get("limitValue"))


def _username(row: dict[str, Any]) -> str:
    return _norm(row.get("username"))


def _role(row: dict[str, Any]) -> str:
    return _norm(row.get("role") or row.get("role_key") or row.get("roleKey"), "user").lower()


def _status(row: dict[str, Any]) -> str:
    value = _norm(row.get("status"), "active").lower()
    return value if value in {"active", "disabled"} else "active"


def _unit(row: dict[str, Any], fallback: str = "") -> str:
    return _norm(row.get("unit"), fallback)


def _period(row: dict[str, Any], fallback: str = "custom") -> str:
    return _norm(row.get("period"), fallback)


def _source_record(
    *,
    source: str,
    quota_key: str,
    value: float,
    unit: str,
    period: str,
    updated_by: Any = None,
    updated_at: Any = None,
    reason: Any = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "quotaKey": quota_key,
        "quotaValue": value,
        "unit": unit,
        "period": period,
        "updatedBy": updated_by,
        "updatedAt": updated_at,
        "reason": reason,
    }


def build_limits_blueprint() -> dict[str, Any]:
    return {
        "limitServiceVersion": COGNIX_LIMIT_SERVICE_VERSION,
        "quotaManagerVersion": COGNIX_QUOTA_MANAGER_VERSION,
        "usageEnforcerVersion": COGNIX_USAGE_ENFORCER_VERSION,
        "mode": "native_quota_management",
        "services": [
            "LimitService",
            "QuotaManager",
            "UsageEnforcer",
        ],
        "tables": [
            "cognix_user_quotas",
            "cognix_role_quotas",
            "cognix_quota_usage",
            "cognix_quota_overrides",
        ],
        "actions": [
            "increase_limit",
            "reduce_limit",
            "reset_limit",
            "create_custom_limit",
            "apply_limit_to_group",
            "apply_limit_to_role",
        ],
        "sideEffects": {
            "userQuotaWrite": False,
            "roleQuotaWrite": False,
            "quotaUsageWrite": False,
            "quotaOverrideWrite": False,
            "legacyLimitWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _default_quota_map() -> dict[str, dict[str, Any]]:
    return {item["quotaKey"]: item for item in DEFAULT_QUOTAS}


def _usage_key(username: str, quota_key: str) -> tuple[str, str]:
    return (username, quota_key)


def _usage_totals(quota_usage: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], float] = {}
    for item in quota_usage:
        key = _usage_key(_username(item), _quota_key(item))
        totals[key] = totals.get(key, 0.0) + _as_float(item.get("used_value") or item.get("usedValue"))
    return totals


def _active_override_for_user(
    *,
    username: str,
    role: str,
    quota_key: str,
    quota_overrides: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in quota_overrides:
        if _status(item) != "active" or _quota_key(item) != quota_key:
            continue
        target_type = _norm(item.get("target_type") or item.get("targetType")).lower()
        target_id = _norm(item.get("target_id") or item.get("targetId")).lower()
        if target_type == "user" and target_id == username.lower():
            candidates.append(item)
        elif target_type == "role" and target_id == role.lower():
            candidates.append(item)
        elif target_type == "group" and target_id in {"all", "everyone", "*"}:
            candidates.append(item)
    return candidates[-1] if candidates else None


def _rows_by_key(rows: list[dict[str, Any]], key_name: str) -> dict[tuple[str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows:
        if _status(item) != "active":
            continue
        owner = _norm(item.get(key_name) or item.get("username") or item.get("role_key") or item.get("roleKey")).lower()
        quota_key = _quota_key(item)
        if owner and quota_key:
            mapped[(owner, quota_key)] = item
    return mapped


def build_quota_matrix(
    *,
    users: list[dict[str, Any]],
    user_quotas: list[dict[str, Any]],
    role_quotas: list[dict[str, Any]],
    quota_overrides: list[dict[str, Any]],
    quota_usage: list[dict[str, Any]],
    legacy_limits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    defaults = _default_quota_map()
    user_quota_map = _rows_by_key(user_quotas, "username")
    role_quota_map = _rows_by_key(role_quotas, "role_key")
    legacy_map = _rows_by_key(legacy_limits or [], "username")
    usage_totals = _usage_totals(quota_usage)
    rows: list[dict[str, Any]] = []

    for user in users:
        username = _norm(user.get("username"))
        role = _role(user)
        quotas: dict[str, dict[str, Any]] = {}
        for quota_key, default in defaults.items():
            unit = default["unit"]
            period = default["period"]
            source_chain = [
                _source_record(
                    source = "default",
                    quota_key = quota_key,
                    value = _as_float(default["defaultValue"]),
                    unit = unit,
                    period = period,
                )
            ]
            effective = source_chain[-1]

            role_quota = role_quota_map.get((role, quota_key))
            if role_quota:
                effective = _source_record(
                    source = "role_quota",
                    quota_key = quota_key,
                    value = _quota_value(role_quota),
                    unit = _unit(role_quota, unit),
                    period = _period(role_quota, period),
                    updated_by = role_quota.get("updated_by") or role_quota.get("updatedBy"),
                    updated_at = role_quota.get("updated_at") or role_quota.get("updatedAt"),
                )
                source_chain.append(effective)

            legacy = legacy_map.get((username.lower(), quota_key))
            if legacy:
                effective = _source_record(
                    source = "legacy_user_limit",
                    quota_key = quota_key,
                    value = _quota_value(legacy),
                    unit = _unit(legacy, unit),
                    period = _period(legacy, period),
                    updated_by = legacy.get("updated_by") or legacy.get("updatedBy"),
                    updated_at = legacy.get("updated_at") or legacy.get("updatedAt"),
                )
                source_chain.append(effective)

            user_quota = user_quota_map.get((username.lower(), quota_key))
            if user_quota:
                effective = _source_record(
                    source = "user_quota",
                    quota_key = quota_key,
                    value = _quota_value(user_quota),
                    unit = _unit(user_quota, unit),
                    period = _period(user_quota, period),
                    updated_by = user_quota.get("updated_by") or user_quota.get("updatedBy"),
                    updated_at = user_quota.get("updated_at") or user_quota.get("updatedAt"),
                )
                source_chain.append(effective)

            override = _active_override_for_user(
                username = username,
                role = role,
                quota_key = quota_key,
                quota_overrides = quota_overrides,
            )
            if override:
                effective = _source_record(
                    source = f"{_norm(override.get('target_type') or override.get('targetType'), 'target')}_override",
                    quota_key = quota_key,
                    value = _quota_value(override),
                    unit = _unit(override, unit),
                    period = _period(override, period),
                    updated_by = override.get("updated_by") or override.get("updatedBy"),
                    updated_at = override.get("updated_at") or override.get("updatedAt"),
                    reason = override.get("reason"),
                )
                source_chain.append(effective)

            used = usage_totals.get(_usage_key(username, quota_key), 0.0)
            value = _as_float(effective["quotaValue"])
            remaining = value - used
            if effective["unit"] == "boolean":
                status = "allowed" if value >= 1 else "blocked"
            elif remaining < 0:
                status = "exceeded"
            elif value > 0 and remaining <= value * 0.1:
                status = "warning"
            else:
                status = "ok"
            quotas[quota_key] = {
                **effective,
                "category": default["category"],
                "usedValue": used,
                "remainingValue": remaining,
                "status": status,
                "sourceChain": source_chain,
            }
        rows.append(
            {
                "username": username,
                "role": role,
                "quotas": quotas,
            }
        )

    exceeded = sum(1 for row in rows for quota in row["quotas"].values() if quota["status"] == "exceeded")
    blocked = sum(1 for row in rows for quota in row["quotas"].values() if quota["status"] == "blocked")
    warnings = sum(1 for row in rows for quota in row["quotas"].values() if quota["status"] == "warning")
    return {
        "limitServiceVersion": COGNIX_LIMIT_SERVICE_VERSION,
        "quotaManagerVersion": COGNIX_QUOTA_MANAGER_VERSION,
        "usageEnforcerVersion": COGNIX_USAGE_ENFORCER_VERSION,
        "mode": "effective_quota_matrix",
        "defaults": DEFAULT_QUOTAS,
        "users": rows,
        "summary": {
            "userCount": len(rows),
            "quotaCount": len(rows) * len(defaults),
            "exceededCount": exceeded,
            "blockedCount": blocked,
            "warningCount": warnings,
            "overrideCount": len([item for item in quota_overrides if _status(item) == "active"]),
        },
        "sideEffects": build_limits_blueprint()["sideEffects"],
    }


def build_usage_enforcement_plan(
    *,
    username: str,
    quota_key: str,
    requested_units: float,
    quota_matrix: dict[str, Any],
) -> dict[str, Any]:
    target = next((item for item in quota_matrix.get("users", []) if item.get("username") == username), None)
    quota = (target or {}).get("quotas", {}).get(quota_key)
    if not quota:
        return {
            "usageEnforcerVersion": COGNIX_USAGE_ENFORCER_VERSION,
            "allowed": False,
            "status": "quota_not_found",
            "reason": "Quota unavailable for this user.",
            "sideEffects": build_limits_blueprint()["sideEffects"],
        }
    requested = max(0.0, _as_float(requested_units))
    value = _as_float(quota.get("quotaValue"))
    used = _as_float(quota.get("usedValue"))
    remaining_after = value - used - requested
    if quota.get("unit") == "boolean":
        allowed = value >= 1
        status = "allowed" if allowed else "blocked"
    else:
        allowed = remaining_after >= 0
        status = "allowed" if allowed else "quota_exceeded"
    return {
        "usageEnforcerVersion": COGNIX_USAGE_ENFORCER_VERSION,
        "allowed": allowed,
        "status": status,
        "username": username,
        "quotaKey": quota_key,
        "requestedUnits": requested,
        "quotaValue": value,
        "usedValue": used,
        "remainingBefore": value - used,
        "remainingAfter": remaining_after,
        "source": quota.get("source"),
        "recommendedAction": "proceed" if allowed else "request_admin_approval_or_reduce_usage",
        "sideEffects": build_limits_blueprint()["sideEffects"],
    }
