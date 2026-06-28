# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native plugin marketplace planning.

The marketplace is deliberately declarative here: it validates manifests,
scans requested permissions, and prepares installation plans without installing
packages, granting permissions, reading secrets, or activating plugins.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION = "cognix_plugin_marketplace_service_v1"
COGNIX_PLUGIN_INSTALLER_VERSION = "cognix_plugin_installer_v1"
COGNIX_PLUGIN_PERMISSION_SCANNER_VERSION = "cognix_plugin_permission_scanner_v1"

MARKETPLACE_CATEGORIES = [
    "productivity",
    "education",
    "code",
    "research",
    "business",
    "connectors",
    "models",
]

IMPLICIT_AUTHENTICATED_PERMISSION = "authenticated"
DEVELOPER_MODE_PERMISSION = "developer_mode"
ADMIN_PERMISSION = "admin"

PERMISSION_RISK_HINTS = {
    "read": "low",
    "index": "medium",
    "write": "medium",
    "draft": "medium",
    "send": "high",
    "delete": "critical",
    "merge": "critical",
    "admin": "critical",
    "secret": "high",
    "model": "medium",
}

RISK_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

BUILTIN_PLUGIN_MANIFESTS: list[dict[str, Any]] = [
    {
        "id": "github-project-board",
        "displayName": "GitHub Project Board",
        "category": "code",
        "description": "Planifie issues, branches et revues depuis CogniX.",
        "version": "0.1.0",
        "publisher": "CogniX Labs",
        "source": "cognix-curated",
        "signature": {"status": "verified", "issuer": "cognix-curated"},
        "permissions": ["authenticated", "github:read", "github:write"],
        "capabilities": ["issue_planning", "pull_request_summary", "project_board_sync"],
        "routes": [],
        "tools": ["github"],
        "uiPanels": ["developer-workflow", "integrations-settings"],
    },
    {
        "id": "research-brief-builder",
        "displayName": "Research Brief Builder",
        "category": "research",
        "description": "Prepare des briefs de recherche avec sources et citations.",
        "version": "0.1.0",
        "publisher": "CogniX Labs",
        "source": "cognix-curated",
        "signature": {"status": "verified", "issuer": "cognix-curated"},
        "permissions": ["authenticated", "rag:write"],
        "capabilities": ["source_triage", "brief_outline", "citation_pack"],
        "routes": [],
        "tools": ["google-drive"],
        "uiPanels": ["project-documents"],
    },
    {
        "id": "cloud-training-exporter",
        "displayName": "Cloud Training Exporter",
        "category": "models",
        "description": "Prepare des notebooks Colab/Kaggle pour training cloud guide.",
        "version": "0.1.0",
        "publisher": "CogniX Labs",
        "source": "cognix-curated",
        "signature": {"status": "verified", "issuer": "cognix-curated"},
        "permissions": ["authenticated", "developer_mode", "tools:cloud_training"],
        "capabilities": ["cloud_training_handoff", "notebook_export", "artifact_sync_plan"],
        "routes": [],
        "tools": ["cloud-training"],
        "uiPanels": ["dataset-manager", "lora-manager"],
    },
]

REQUIRED_MANIFEST_FIELDS = {
    "id",
    "displayName",
    "category",
    "version",
    "publisher",
    "signature",
    "permissions",
    "capabilities",
}


def _normalize_permission(permission: str) -> str:
    return (permission or "").strip().lower()


def _permission_set(
    *,
    is_admin: bool,
    has_developer_mode: bool,
    granted_permissions: set[str] | None,
) -> set[str]:
    permissions = {
        _normalize_permission(item)
        for item in (granted_permissions or set())
        if item
    }
    permissions.add(IMPLICIT_AUTHENTICATED_PERMISSION)
    if is_admin:
        permissions.add(ADMIN_PERMISSION)
        permissions.add(DEVELOPER_MODE_PERMISSION)
    if has_developer_mode:
        permissions.add(DEVELOPER_MODE_PERMISSION)
    return permissions


def _risk_rank(risk: str) -> int:
    return RISK_ORDER.get(str(risk or "low").lower(), 1)


def _permission_risk(permission: str) -> str:
    normalized = _normalize_permission(permission)
    if normalized == IMPLICIT_AUTHENTICATED_PERMISSION:
        return "low"
    if normalized == ADMIN_PERMISSION:
        return "critical"
    if normalized == DEVELOPER_MODE_PERMISSION:
        return "medium"
    for token, risk in PERMISSION_RISK_HINTS.items():
        if token in normalized:
            return risk
    return "medium"


def _manifest_signature_status(manifest: dict[str, Any]) -> str:
    signature = manifest.get("signature")
    if not isinstance(signature, dict):
        return "missing"
    status = str(signature.get("status") or "").strip().lower()
    issuer = str(signature.get("issuer") or "").strip().lower()
    if status == "verified" and issuer in {"cognix-curated", "cognix-marketplace"}:
        return "verified"
    if status:
        return status
    return "unknown"


def _safe_plugin_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip().lower())
    return cleaned[:120] or "unknown-plugin"


def _plugin_hash(manifest: dict[str, Any]) -> str:
    source = "|".join(
        str(manifest.get(key) or "")
        for key in ("id", "displayName", "version", "publisher")
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _builtin_manifest(plugin_id: str | None) -> dict[str, Any] | None:
    if not plugin_id:
        return None
    wanted = _safe_plugin_id(plugin_id)
    for manifest in BUILTIN_PLUGIN_MANIFESTS:
        if _safe_plugin_id(str(manifest.get("id") or "")) == wanted:
            return deepcopy(manifest)
    return None


def _normalize_manifest(plugin_manifest: dict[str, Any] | None, plugin_id: str | None = None) -> dict[str, Any]:
    manifest = _builtin_manifest(plugin_id)
    if manifest is None and isinstance(plugin_manifest, dict):
        manifest = deepcopy(plugin_manifest)
    if manifest is None:
        manifest = {"id": plugin_id or "unknown-plugin"}

    manifest["id"] = _safe_plugin_id(str(manifest.get("id") or plugin_id or "unknown-plugin"))
    manifest["displayName"] = str(manifest.get("displayName") or manifest.get("name") or manifest["id"])[:160]
    manifest["category"] = str(manifest.get("category") or "productivity").strip().lower()
    if manifest["category"] not in MARKETPLACE_CATEGORIES:
        manifest["category"] = "productivity"
    manifest["version"] = str(manifest.get("version") or "0.0.0")[:80]
    manifest["publisher"] = str(manifest.get("publisher") or "unknown")[:160]
    for key in ("permissions", "capabilities", "routes", "tools", "uiPanels"):
        value = manifest.get(key)
        manifest[key] = [str(item) for item in value if item] if isinstance(value, list) else []
    return manifest


def validate_plugin_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing_fields = sorted(field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest)
    permissions = manifest.get("permissions") if isinstance(manifest.get("permissions"), list) else []
    signature_status = _manifest_signature_status(manifest)
    permission_manifest_present = bool(permissions)
    valid = not missing_fields and permission_manifest_present and signature_status == "verified"

    blocking_reasons: list[str] = []
    if missing_fields:
        blocking_reasons.append("missing_required_fields")
    if not permission_manifest_present:
        blocking_reasons.append("missing_permission_manifest")
    if signature_status != "verified":
        blocking_reasons.append("signature_not_verified")

    return {
        "schemaVersion": "cognix_plugin_manifest_schema_v1",
        "valid": valid,
        "missingFields": missing_fields,
        "signatureStatus": signature_status,
        "permissionManifestPresent": permission_manifest_present,
        "blockingReasons": blocking_reasons,
    }


def scan_plugin_permissions(
    manifest: dict[str, Any],
    *,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    available_permissions = _permission_set(
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    requested = [
        _normalize_permission(str(permission))
        for permission in manifest.get("permissions", [])
        if str(permission).strip()
    ]
    requested = list(dict.fromkeys(requested))
    permission_items: list[dict[str, Any]] = []
    for permission in requested:
        risk = _permission_risk(permission)
        permission_items.append(
            {
                "permission": permission,
                "riskLevel": risk,
                "granted": permission in available_permissions,
                "requiresAdmin": risk == "critical" or permission == ADMIN_PERMISSION,
            }
        )
    missing = [item["permission"] for item in permission_items if not item["granted"]]
    max_risk = "low"
    if permission_items:
        max_risk = sorted(
            (item["riskLevel"] for item in permission_items),
            key = _risk_rank,
            reverse = True,
        )[0]
    return {
        "scannerVersion": COGNIX_PLUGIN_PERMISSION_SCANNER_VERSION,
        "requestedPermissions": permission_items,
        "missingPermissions": missing,
        "maxRiskLevel": max_risk,
        "requiresAdminReview": any(item["requiresAdmin"] for item in permission_items),
        "permissionGrantRequired": bool(missing),
    }


def build_plugin_marketplace_blueprint() -> dict[str, Any]:
    return {
        "marketplaceServiceVersion": COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION,
        "installerVersion": COGNIX_PLUGIN_INSTALLER_VERSION,
        "permissionScannerVersion": COGNIX_PLUGIN_PERMISSION_SCANNER_VERSION,
        "services": [
            "PluginMarketplaceService",
            "PluginInstaller",
            "PluginPermissionScanner",
        ],
        "categories": MARKETPLACE_CATEGORIES,
        "pipeline": [
            "plugin_manifest",
            "signature_validation",
            "permission_scan",
            "installation_plan",
            "activation_plan",
        ],
        "policies": {
            "permissionManifestRequired": True,
            "verifiedSignatureRequired": True,
            "humanConfirmationForInstall": True,
            "humanConfirmationForActivation": True,
            "secretsStayServerSide": True,
            "frontendCannotSelfInstallPlugins": True,
        },
        "sideEffects": {
            "pluginInstall": False,
            "pluginActivation": False,
            "permissionGrant": False,
            "networkCall": False,
            "fileWrite": False,
            "secretRead": False,
            "toolExecution": False,
        },
    }


def build_marketplace_catalog() -> dict[str, Any]:
    plugins: list[dict[str, Any]] = []
    for manifest in BUILTIN_PLUGIN_MANIFESTS:
        normalized = _normalize_manifest(manifest)
        validation = validate_plugin_manifest(normalized)
        permission_scan = scan_plugin_permissions(normalized)
        plugins.append(
            {
                "id": normalized["id"],
                "displayName": normalized["displayName"],
                "category": normalized["category"],
                "description": normalized.get("description", ""),
                "version": normalized["version"],
                "publisher": normalized["publisher"],
                "signatureStatus": validation["signatureStatus"],
                "permissionCount": len(normalized.get("permissions", [])),
                "maxRiskLevel": permission_scan["maxRiskLevel"],
                "installable": validation["valid"],
                "manifestHash": _plugin_hash(normalized),
            }
        )
    return {
        "marketplaceServiceVersion": COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION,
        "mode": "curated_catalog",
        "categories": MARKETPLACE_CATEGORIES,
        "plugins": plugins,
        "summary": {
            "pluginCount": len(plugins),
            "installableCount": sum(1 for plugin in plugins if plugin.get("installable")),
        },
        "sideEffects": build_plugin_marketplace_blueprint()["sideEffects"],
    }


def build_plugin_install_plan(
    *,
    username: str,
    plugin_id: str | None = None,
    plugin_manifest: dict[str, Any] | None = None,
    project_id: str | None = None,
    target_scope: str = "user",
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    manifest = _normalize_manifest(plugin_manifest, plugin_id)
    validation = validate_plugin_manifest(manifest)
    permission_scan = scan_plugin_permissions(
        manifest,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    install_ready = bool(validation["valid"]) and not permission_scan["missingPermissions"]
    plan_id_seed = f"{username}|{project_id or ''}|{manifest['id']}|{manifest['version']}|{target_scope}"
    installation_plan_id = f"plugplan_{hashlib.sha256(plan_id_seed.encode('utf-8')).hexdigest()[:18]}"
    status = "ready_for_confirmation" if install_ready else "blocked"
    if validation["valid"] and permission_scan["missingPermissions"]:
        status = "blocked_missing_permissions"
    if "missing_permission_manifest" in validation["blockingReasons"]:
        status = "blocked_missing_permission_manifest"
    elif "signature_not_verified" in validation["blockingReasons"]:
        status = "blocked_signature_not_verified"

    return {
        "marketplaceServiceVersion": COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION,
        "installerVersion": COGNIX_PLUGIN_INSTALLER_VERSION,
        "permissionScannerVersion": COGNIX_PLUGIN_PERMISSION_SCANNER_VERSION,
        "mode": "dry_run_plugin_install",
        "installationPlanId": installation_plan_id,
        "username": username,
        "projectId": project_id,
        "targetScope": target_scope if target_scope in {"user", "project", "workspace"} else "user",
        "status": status,
        "plugin": {
            "id": manifest["id"],
            "displayName": manifest["displayName"],
            "category": manifest["category"],
            "version": manifest["version"],
            "publisher": manifest["publisher"],
            "manifestHash": _plugin_hash(manifest),
            "source": manifest.get("source") or "external_manifest",
        },
        "manifest": manifest,
        "validation": validation,
        "permissionScan": permission_scan,
        "installationPlan": {
            "steps": [
                {"id": "validate_manifest", "status": "passed" if validation["valid"] else "blocked", "willRunNow": False},
                {"id": "scan_permissions", "status": "passed", "willRunNow": False},
                {
                    "id": "request_missing_permissions",
                    "status": "planned" if permission_scan["missingPermissions"] else "not_required",
                    "willRunNow": False,
                },
                {
                    "id": "install_plugin_package",
                    "status": "planned_after_confirmation" if install_ready else "blocked",
                    "willRunNow": False,
                },
                {
                    "id": "activate_plugin",
                    "status": "planned_after_confirmation" if install_ready else "blocked",
                    "willRunNow": False,
                },
            ],
            "readyToInstall": install_ready,
            "requiresHumanConfirmation": True,
        },
        "activationPlan": {
            "readyToActivate": install_ready,
            "willActivateNow": False,
            "activationRequiresConfirmation": True,
        },
        "sideEffects": build_plugin_marketplace_blueprint()["sideEffects"],
    }
