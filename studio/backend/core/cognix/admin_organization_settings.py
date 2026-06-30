# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX organization policy and admin settings service."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_ORGANIZATION_POLICY_SERVICE_VERSION = "cognix_organization_policy_service_v1"
COGNIX_POLICY_ENFORCER_VERSION = "cognix_policy_enforcer_v1"
COGNIX_ADMIN_SETTINGS_SERVICE_VERSION = "cognix_admin_settings_service_v1"
COGNIX_POLICY_CHANGE_LOG_VERSION = "cognix_policy_change_log_v1"

ORGANIZATION_POLICY_SERVICES = [
    "OrganizationPolicyService",
    "PolicyEnforcer",
    "AdminSettingsService",
]

ORGANIZATION_POLICY_TABLES = [
    "organization_policies",
    "organization_settings",
    "policy_change_logs",
]

DEFAULT_ORGANIZATION_SETTINGS: dict[str, Any] = {
    "cloudAllowed": True,
    "externalModelsAllowed": True,
    "e2eeAllowed": True,
    "adminChatAccessAllowed": False,
    "dataRetentionDays": 90,
    "roleQuotas": {},
    "allowedModels": [],
    "allowedApps": [],
    "defaultPermissions": [],
    "approvalRequired": True,
}

BOOLEAN_SETTING_KEYS = {
    "cloudAllowed",
    "externalModelsAllowed",
    "e2eeAllowed",
    "adminChatAccessAllowed",
    "approvalRequired",
}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "allow", "allowed"}:
            return True
        if normalized in {"0", "false", "no", "off", "deny", "denied"}:
            return False
    return fallback


def _as_int(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def build_organization_settings_blueprint() -> dict[str, Any]:
    return {
        "organizationPolicyServiceVersion": COGNIX_ORGANIZATION_POLICY_SERVICE_VERSION,
        "policyEnforcerVersion": COGNIX_POLICY_ENFORCER_VERSION,
        "adminSettingsServiceVersion": COGNIX_ADMIN_SETTINGS_SERVICE_VERSION,
        "policyChangeLogVersion": COGNIX_POLICY_CHANGE_LOG_VERSION,
        "mode": "native_admin_organization_settings",
        "services": ORGANIZATION_POLICY_SERVICES,
        "tables": ORGANIZATION_POLICY_TABLES,
        "settings": list(DEFAULT_ORGANIZATION_SETTINGS.keys()),
        "policyScopes": [
            "cloud",
            "external_models",
            "e2ee",
            "admin_chat_access",
            "data_retention",
            "role_quotas",
            "allowed_models",
            "allowed_apps",
            "default_permissions",
            "approval_required",
        ],
        "security": {
            "adminOnly": True,
            "organizationScoped": True,
            "policyChangesAudited": True,
            "permissionEngineIntegration": True,
            "frontendDirectModelCallAllowed": False,
        },
        "sideEffects": {
            "databaseWrite": False,
            "policyWrite": False,
            "settingsWrite": False,
            "changeLogWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def normalize_organization_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = deepcopy(DEFAULT_ORGANIZATION_SETTINGS)
    incoming = settings if isinstance(settings, dict) else {}
    for key in BOOLEAN_SETTING_KEYS:
        if key in incoming:
            normalized[key] = _as_bool(incoming.get(key), bool(normalized[key]))
    if "dataRetentionDays" in incoming:
        normalized["dataRetentionDays"] = max(1, min(_as_int(incoming.get("dataRetentionDays"), 90), 3650))
    for key in ("allowedModels", "allowedApps", "defaultPermissions"):
        if key in incoming:
            normalized[key] = [item for item in _as_list(incoming.get(key)) if _norm(item)]
    if isinstance(incoming.get("roleQuotas"), dict):
        normalized["roleQuotas"] = dict(incoming["roleQuotas"])
    return normalized


def policy_records_from_settings(
    *,
    settings: dict[str, Any],
    organization_id: str = "default",
    updated_by: str = "",
) -> list[dict[str, Any]]:
    normalized = normalize_organization_settings(settings)
    records: list[dict[str, Any]] = []
    for key, value in normalized.items():
        policy_key = {
            "cloudAllowed": "cloud:allowed",
            "externalModelsAllowed": "models:external",
            "e2eeAllowed": "chat:e2ee",
            "adminChatAccessAllowed": "admin:chats:read",
            "dataRetentionDays": "data:retention_days",
            "roleQuotas": "quotas:roles",
            "allowedModels": "models:allowed",
            "allowedApps": "apps:allowed",
            "defaultPermissions": "permissions:defaults",
            "approvalRequired": "approvals:required",
        }[key]
        records.append(
            {
                "organizationId": organization_id,
                "policyKey": policy_key,
                "settingKey": key,
                "policyType": "permission" if ":" in policy_key else "setting",
                "policyValue": value,
                "allowed": _as_bool(value, True) if key in BOOLEAN_SETTING_KEYS else True,
                "enforced": True,
                "updatedBy": updated_by,
            }
        )
    for permission in normalized.get("defaultPermissions", []):
        permission_key = _norm(permission)
        if not permission_key:
            continue
        records.append(
            {
                "organizationId": organization_id,
                "policyKey": permission_key,
                "settingKey": "defaultPermissions",
                "policyType": "permission",
                "policyValue": {"permissionKey": permission_key, "allowed": True},
                "permissionKey": permission_key,
                "allowed": True,
                "enforced": True,
                "updatedBy": updated_by,
            }
        )
    return records


def build_policy_bundle(
    *,
    settings: dict[str, Any] | None = None,
    policies: list[dict[str, Any]] | None = None,
    change_logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_organization_settings(settings)
    policy_records = list(policies or policy_records_from_settings(settings = normalized))
    return {
        "organizationPolicyServiceVersion": COGNIX_ORGANIZATION_POLICY_SERVICE_VERSION,
        "adminSettingsServiceVersion": COGNIX_ADMIN_SETTINGS_SERVICE_VERSION,
        "settings": normalized,
        "policies": policy_records,
        "changeLogs": list(change_logs or []),
        "summary": {
            "policyCount": len(policy_records),
            "changeLogCount": len(change_logs or []),
            "cloudAllowed": normalized["cloudAllowed"],
            "externalModelsAllowed": normalized["externalModelsAllowed"],
            "approvalRequired": normalized["approvalRequired"],
            "defaultPermissionCount": len(normalized["defaultPermissions"]),
            "allowedModelCount": len(normalized["allowedModels"]),
            "allowedAppCount": len(normalized["allowedApps"]),
        },
        "sideEffects": build_organization_settings_blueprint()["sideEffects"],
    }


def build_policy_enforcement_plan(
    *,
    settings: dict[str, Any],
    action_type: str,
    model_id: str | None = None,
    provider: str | None = None,
    app_id: str | None = None,
    permission_key: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_organization_settings(settings)
    action = _norm(action_type, "general").lower()
    allowed = True
    reasons: list[str] = []
    if action in {"cloud", "model", "generation"}:
        provider_value = _norm(provider, "local").lower()
        is_cloud = provider_value not in {"", "local", "ollama", "llama", "gguf", "cpu", "unsloth"}
        if is_cloud and not normalized["cloudAllowed"]:
            allowed = False
            reasons.append("cloud_disabled_by_organization_policy")
        model_value = _norm(model_id)
        allowed_models = {str(item) for item in normalized.get("allowedModels", [])}
        if model_value and allowed_models and model_value not in allowed_models:
            allowed = False
            reasons.append("model_not_in_allowed_models")
        if is_cloud and not normalized["externalModelsAllowed"]:
            allowed = False
            reasons.append("external_models_disabled_by_organization_policy")
    if action == "app":
        app_value = _norm(app_id)
        allowed_apps = {str(item) for item in normalized.get("allowedApps", [])}
        if app_value and allowed_apps and app_value not in allowed_apps:
            allowed = False
            reasons.append("app_not_in_allowed_apps")
    if action == "permission":
        permission_value = _norm(permission_key)
        defaults = {str(item) for item in normalized.get("defaultPermissions", [])}
        if permission_value and defaults and permission_value not in defaults:
            allowed = False
            reasons.append("permission_not_in_default_permissions")
    if action == "admin_chat_access" and not normalized["adminChatAccessAllowed"]:
        allowed = False
        reasons.append("admin_chat_access_disabled_by_organization_policy")
    return {
        "policyEnforcerVersion": COGNIX_POLICY_ENFORCER_VERSION,
        "actionType": action,
        "allowed": allowed,
        "reasons": reasons,
        "approvalRequired": bool(normalized["approvalRequired"]) and not allowed,
        "settingsSnapshot": normalized,
        "sideEffects": {
            "databaseWrite": False,
            "policyWrite": False,
            "settingsWrite": False,
            "changeLogWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_policy_change_record(
    *,
    before: dict[str, Any] | None,
    after: dict[str, Any],
    changed_by: str,
    reason: str = "",
) -> dict[str, Any]:
    before_settings = normalize_organization_settings(before)
    after_settings = normalize_organization_settings(after)
    changed_keys = [
        key for key in sorted(after_settings)
        if before_settings.get(key) != after_settings.get(key)
    ]
    return {
        "policyChangeLogVersion": COGNIX_POLICY_CHANGE_LOG_VERSION,
        "changedBy": _norm(changed_by),
        "reason": _norm(reason),
        "changedKeys": changed_keys,
        "before": before_settings,
        "after": after_settings,
        "sideEffects": {
            "databaseWrite": False,
            "policyWrite": False,
            "settingsWrite": False,
            "changeLogWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }
