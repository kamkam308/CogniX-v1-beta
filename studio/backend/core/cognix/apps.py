# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native app registry, permission scanning, and connection planning."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_APPS_VERSION = "cognix_apps_v1"
COGNIX_APP_REGISTRY_VERSION = "cognix_app_registry_v1"
COGNIX_APP_PERMISSION_SCANNER_VERSION = "cognix_app_permission_scanner_v1"
COGNIX_APP_RUNTIME_ADAPTER_VERSION = "cognix_app_runtime_adapter_v1"

APP_PERMISSION_PROFILES: dict[str, dict[str, Any]] = {
    "canva": {
        "authType": "oauth",
        "riskLevel": "low",
        "permissions": [{"permission": "canva:design:create", "riskLevel": "low", "required": False}],
        "tools": ["canva"],
        "runtimeAdapter": "design_asset_adapter",
    },
    "google-drive": {
        "authType": "oauth",
        "riskLevel": "medium",
        "permissions": [
            {"permission": "google-drive:read", "riskLevel": "medium", "required": True},
            {"permission": "google-drive:write", "riskLevel": "high", "required": False},
        ],
        "tools": ["google-drive"],
        "runtimeAdapter": "file_provider_adapter",
    },
    "github": {
        "authType": "oauth",
        "riskLevel": "medium",
        "permissions": [
            {"permission": "github:read", "riskLevel": "medium", "required": True},
            {"permission": "github:write", "riskLevel": "high", "required": False},
        ],
        "tools": ["github"],
        "runtimeAdapter": "code_repository_adapter",
    },
    "hugging-face": {
        "authType": "token_or_oauth",
        "riskLevel": "medium",
        "permissions": [
            {"permission": "hugging-face:read", "riskLevel": "medium", "required": False},
            {"permission": "hugging-face:jobs", "riskLevel": "high", "required": False},
        ],
        "tools": ["hugging-face"],
        "runtimeAdapter": "model_hub_adapter",
    },
    "notion": {
        "authType": "oauth",
        "riskLevel": "medium",
        "permissions": [
            {"permission": "notion:read", "riskLevel": "medium", "required": True},
            {"permission": "notion:write", "riskLevel": "high", "required": False},
        ],
        "tools": ["notion"],
        "runtimeAdapter": "workspace_docs_adapter",
    },
    "gmail": {
        "authType": "oauth",
        "riskLevel": "high",
        "permissions": [
            {"permission": "gmail:read", "riskLevel": "high", "required": True},
            {"permission": "gmail:send", "riskLevel": "critical", "required": False},
        ],
        "tools": ["gmail"],
        "runtimeAdapter": "communication_adapter",
    },
}

RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _normalize(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _risk_max(values: list[str]) -> str:
    if not values:
        return "low"
    return max(values, key = lambda item: RISK_ORDER.get(item, 1))


def normalize_app_manifest(app: dict[str, Any]) -> dict[str, Any]:
    app_id = _normalize(app.get("id"), limit = 80)
    profile = deepcopy(APP_PERMISSION_PROFILES.get(app_id, {}))
    permissions = profile.get("permissions") or []
    risk_level = str(profile.get("riskLevel") or _risk_max([str(item.get("riskLevel") or "low") for item in permissions]))
    return {
        "id": app_id,
        "name": _normalize(app.get("name"), limit = 120) or app_id,
        "category": _normalize(app.get("category"), limit = 80) or "Integration",
        "description": _normalize(app.get("description"), limit = 500),
        "manifestVersion": COGNIX_APPS_VERSION,
        "authType": profile.get("authType") or "manual",
        "riskLevel": risk_level,
        "requestedPermissions": permissions,
        "tools": profile.get("tools") or [],
        "runtimeAdapter": profile.get("runtimeAdapter") or "generic_app_adapter",
        "revocationSupported": True,
        "logsRequired": True,
    }


def build_apps_blueprint() -> dict[str, Any]:
    return {
        "appsVersion": COGNIX_APPS_VERSION,
        "registryVersion": COGNIX_APP_REGISTRY_VERSION,
        "permissionScannerVersion": COGNIX_APP_PERMISSION_SCANNER_VERSION,
        "runtimeAdapterVersion": COGNIX_APP_RUNTIME_ADAPTER_VERSION,
        "mode": "manifest_first_app_integration_contract",
        "services": ["AppRegistry", "AppInstaller", "OAuthManager", "AppPermissionScanner", "AppRuntimeAdapter"],
        "securityPolicy": {
            "manifestRequired": True,
            "permissionsDeclared": True,
            "permissionScanRequired": True,
            "activationRequiresAudit": True,
            "revocationSupported": True,
            "tokenReadAllowedInRegistry": False,
            "frontendDirectToolCallAllowed": False,
        },
        "displayContract": {
            "catalog": True,
            "connectionStatus": True,
            "permissionBadges": True,
            "riskBadges": True,
            "logsPanel": True,
            "designSystemOnly": True,
        },
        "sideEffects": {
            "connectionWrite": False,
            "permissionWrite": False,
            "auditWrite": False,
            "tokenRead": False,
            "tokenWrite": False,
            "oauthStart": False,
            "toolExecution": False,
            "networkCall": False,
            "modelLoad": False,
        },
    }


def scan_app_permissions(
    app_manifest: dict[str, Any],
    *,
    granted_permissions: set[str] | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    granted = {permission.lower() for permission in (granted_permissions or set())}
    requested = []
    missing_required = []
    risk_levels: list[str] = []
    for item in app_manifest.get("requestedPermissions") or []:
        permission = str(item.get("permission") or "").lower()
        risk = str(item.get("riskLevel") or "low").lower()
        required = bool(item.get("required"))
        granted_here = admin or not required or permission in granted
        risk_levels.append(risk)
        record = {
            "permission": permission,
            "riskLevel": risk,
            "required": required,
            "granted": granted_here,
        }
        requested.append(record)
        if required and not granted_here:
            missing_required.append(permission)
    return {
        "permissionScannerVersion": COGNIX_APP_PERMISSION_SCANNER_VERSION,
        "appId": app_manifest.get("id"),
        "requestedPermissions": requested,
        "missingRequiredPermissions": missing_required,
        "maxRiskLevel": _risk_max(risk_levels or [str(app_manifest.get("riskLevel") or "low")]),
        "sensitiveScopes": [
            item["permission"]
            for item in requested
            if RISK_ORDER.get(item["riskLevel"], 1) >= RISK_ORDER["high"]
        ],
        "allowed": not missing_required,
        "allowedByRole": bool(admin),
    }


def build_app_registry(
    *,
    catalog: list[dict[str, Any]],
    connections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    connection_by_app = {str(item.get("app_id") or item.get("appId")): item for item in connections or []}
    manifests = []
    for app in catalog:
        manifest = normalize_app_manifest(app)
        connection = connection_by_app.get(manifest["id"])
        manifest["connection"] = {
            "status": connection.get("status") if connection else "available",
            "connected": bool(connection and connection.get("status") == "connected"),
            "updatedAt": connection.get("updated_at") or connection.get("updatedAt") if connection else None,
        }
        manifest["permissionScan"] = scan_app_permissions(manifest)
        manifests.append(manifest)
    by_risk: dict[str, int] = {}
    for manifest in manifests:
        by_risk[manifest["riskLevel"]] = by_risk.get(manifest["riskLevel"], 0) + 1
    return {
        "appsVersion": COGNIX_APPS_VERSION,
        "registryVersion": COGNIX_APP_REGISTRY_VERSION,
        "summary": {
            "appCount": len(manifests),
            "connectedCount": sum(1 for item in manifests if item["connection"]["connected"]),
            "byRisk": by_risk,
        },
        "apps": manifests,
        "sideEffects": build_apps_blueprint()["sideEffects"],
    }


def _find_manifest(catalog: list[dict[str, Any]], app_id: str) -> dict[str, Any] | None:
    normalized = _normalize(app_id, limit = 80)
    for app in catalog:
        if _normalize(app.get("id"), limit = 80) == normalized:
            return normalize_app_manifest(app)
    return None


def build_app_connection_plan(
    *,
    app_id: str,
    requested_status: str,
    catalog: list[dict[str, Any]],
    granted_permissions: set[str] | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    manifest = _find_manifest(catalog, app_id)
    side_effects = build_apps_blueprint()["sideEffects"]
    if manifest is None:
        return {
            "appsVersion": COGNIX_APPS_VERSION,
            "registryVersion": COGNIX_APP_REGISTRY_VERSION,
            "mode": "app_connection_plan",
            "status": "unknown_app",
            "allowed": False,
            "app": None,
            "permissionScan": None,
            "connectionPlan": {
                "requestedStatus": requested_status,
                "willWriteConnection": False,
                "oauthStart": False,
                "revocation": False,
            },
            "sideEffects": side_effects,
        }
    permission_scan = scan_app_permissions(
        manifest,
        granted_permissions = granted_permissions,
        admin = admin,
    )
    normalized_status = _normalize(requested_status, limit = 80) or "connected"
    disabling = normalized_status == "disabled"
    allowed = disabling or permission_scan["allowed"]
    return {
        "appsVersion": COGNIX_APPS_VERSION,
        "registryVersion": COGNIX_APP_REGISTRY_VERSION,
        "permissionScannerVersion": COGNIX_APP_PERMISSION_SCANNER_VERSION,
        "runtimeAdapterVersion": COGNIX_APP_RUNTIME_ADAPTER_VERSION,
        "mode": "app_connection_plan",
        "status": "ready" if allowed else "missing_permissions",
        "allowed": allowed,
        "app": manifest,
        "permissionScan": permission_scan,
        "connectionPlan": {
            "requestedStatus": normalized_status,
            "willWriteConnection": allowed,
            "oauthStart": False,
            "revocation": disabling,
            "runtimeAdapter": manifest["runtimeAdapter"],
            "toolRegistrationMutation": False,
        },
        "securityReview": {
            "riskLevel": manifest["riskLevel"],
            "auditRequired": True,
            "tokenWrite": False,
            "tokenRead": False,
            "missingRequiredPermissions": permission_scan["missingRequiredPermissions"],
        },
        "sideEffects": side_effects,
    }
