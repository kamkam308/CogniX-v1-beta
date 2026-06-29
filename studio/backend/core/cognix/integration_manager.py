# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native integration planning.

The integration manager turns declarative tool manifests into connector status
and activation plans without reading secrets, enabling connectors, or executing
external calls.
"""

from __future__ import annotations

from typing import Any

from core.cognix import tool_registry as cognix_tool_registry


COGNIX_INTEGRATION_MANAGER_VERSION = "cognix_integration_manager_v1"
COGNIX_INTEGRATION_ACTIVATION_CONTRACT_VERSION = "cognix_integration_activation_contract_v1"


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
    permissions.add(cognix_tool_registry.IMPLICIT_AUTHENTICATED_PERMISSION)
    if is_admin:
        permissions.add(cognix_tool_registry.ADMIN_PERMISSION)
        permissions.add(cognix_tool_registry.DEVELOPER_MODE_PERMISSION)
    if has_developer_mode:
        permissions.add(cognix_tool_registry.DEVELOPER_MODE_PERMISSION)
    return permissions


def _risk_rank(risk_level: str) -> int:
    return cognix_tool_registry.RISK_ORDER.get(str(risk_level or "").lower(), 0)


def _max_risk(actions: list[dict[str, Any]]) -> str:
    ranked = sorted(
        (str(action.get("riskLevel") or "low") for action in actions),
        key = _risk_rank,
        reverse = True,
    )
    return ranked[0] if ranked else "low"


def _required_permissions(actions: list[dict[str, Any]]) -> set[str]:
    required: set[str] = set()
    for action in actions:
        for permission in action.get("permissions") or []:
            normalized = _normalize_permission(str(permission))
            if normalized and normalized != cognix_tool_registry.IMPLICIT_AUTHENTICATED_PERMISSION:
                required.add(normalized)
    return required


def _next_actions(
    *,
    enabled: bool,
    secrets_required: bool,
    missing_permissions: list[str],
    max_risk: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not enabled:
        actions.append(
            {
                "id": "enable_connector",
                "label": "Activer le connecteur",
                "requiresAdmin": True,
                "status": "planned",
            }
        )
    if secrets_required:
        actions.append(
            {
                "id": "configure_server_secret",
                "label": "Configurer le secret cote serveur",
                "requiresAdmin": True,
                "status": "planned",
            }
        )
    if missing_permissions:
        actions.append(
            {
                "id": "request_permissions",
                "label": "Demander les permissions manquantes",
                "requiresAdmin": False,
                "status": "planned",
                "permissions": missing_permissions,
            }
        )
    if _risk_rank(max_risk) >= _risk_rank("high"):
        actions.append(
            {
                "id": "review_risk_policy",
                "label": "Revoir la politique de risque",
                "requiresAdmin": True,
                "status": "planned",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "ready_for_guarded_planning",
                "label": "Pret pour planification controlee",
                "requiresAdmin": False,
                "status": "ready",
            }
        )
    return actions


def _activation_contract(
    *,
    integration: dict[str, Any] | None,
    username: str,
    status_side_effects: dict[str, Any],
) -> dict[str, Any]:
    if integration is None:
        return {
            "contractVersion": COGNIX_INTEGRATION_ACTIVATION_CONTRACT_VERSION,
            "mode": "activation_contract_dry_run",
            "username": username,
            "toolId": None,
            "connector": None,
            "allowedToPrepareActivation": False,
            "readyForActivation": False,
            "automaticActivationAllowed": False,
            "frontendDirectActivationAllowed": False,
            "nextRequiredGate": "unknown_integration",
            "preconditions": {
                "manifestPresent": False,
                "connectorDeclared": False,
                "permissionsResolved": False,
                "serverSecretConfigured": False,
                "riskReviewed": False,
                "humanApprovalRequired": True,
                "auditRequired": True,
            },
            "blockedWhen": ["unknown_integration"],
            "blockedActions": [
                "connector_activation",
                "secret_read",
                "network_tool_call",
                "external_write",
                "permission_write",
                "frontend_direct_activation",
            ],
            "sideEffects": status_side_effects,
        }

    missing_permissions = list(integration.get("missingPermissions") or [])
    secrets_required = bool(integration.get("secretsRequired"))
    enabled = bool(integration.get("enabled"))
    high_risk = _risk_rank(str(integration.get("maxRiskLevel") or "low")) >= _risk_rank("high")
    blocked_when: list[str] = []
    if not enabled:
        blocked_when.append("connector_disabled")
    if missing_permissions:
        blocked_when.append("missing_permissions")
    if secrets_required:
        blocked_when.append("server_secret_required")
    if high_risk:
        blocked_when.append("risk_review_required")
    if not blocked_when:
        blocked_when.append("human_approval_required")
    ready_for_activation = enabled and not missing_permissions and not secrets_required and not high_risk
    return {
        "contractVersion": COGNIX_INTEGRATION_ACTIVATION_CONTRACT_VERSION,
        "mode": "activation_contract_dry_run",
        "username": username,
        "toolId": integration.get("id"),
        "connector": integration.get("connector"),
        "allowedToPrepareActivation": bool(integration.get("id")),
        "readyForActivation": False,
        "automaticActivationAllowed": False,
        "frontendDirectActivationAllowed": False,
        "nextRequiredGate": blocked_when[0],
        "preconditions": {
            "manifestPresent": True,
            "connectorDeclared": bool(integration.get("connector")),
            "connectorEnabled": enabled,
            "permissionsResolved": not missing_permissions,
            "missingPermissions": missing_permissions,
            "serverSecretConfigured": not secrets_required,
            "secretsRequired": secrets_required,
            "riskReviewed": not high_risk,
            "maxRiskLevel": integration.get("maxRiskLevel"),
            "humanApprovalRequired": True,
            "auditRequired": True,
            "wouldBeActivationReadyAfterApproval": ready_for_activation,
        },
        "activationExecutor": "cognix_integration_executor:activate_connector",
        "allowedActions": [
            "record_activation_plan",
            "request_missing_permissions",
            "configure_server_secret_reference",
            "request_human_approval",
            "enable_connector_after_approval",
        ],
        "blockedWhen": blocked_when,
        "blockedActions": [
            "connector_activation",
            "secret_read",
            "network_tool_call",
            "external_write",
            "permission_write",
            "frontend_direct_activation",
        ],
        "dataBoundary": {
            "dataIsolation": integration.get("dataIsolation"),
            "secretsStayServerSide": True,
            "rawSecretLoggingAllowed": False,
        },
        "sideEffects": status_side_effects,
    }


def _integration_record(tool: dict[str, Any], permissions: set[str]) -> dict[str, Any]:
    actions = [action for action in tool.get("actions") or [] if isinstance(action, dict)]
    enabled = bool(tool.get("enabled"))
    required = _required_permissions(actions)
    missing = sorted(permission for permission in required if permission not in permissions)
    secrets_required = any(bool(action.get("secretsRequired")) for action in actions)
    max_risk = _max_risk(actions)
    allowed_action_count = 0
    for action in actions:
        action_permissions = {
            _normalize_permission(str(item))
            for item in action.get("permissions") or []
            if item
        }
        if enabled and action_permissions.issubset(permissions):
            allowed_action_count += 1

    status = "enabled_ready"
    if not enabled:
        status = "declared_disabled"
    elif missing:
        status = "enabled_needs_permissions"

    return {
        "id": tool.get("id"),
        "name": tool.get("name"),
        "category": tool.get("category"),
        "connector": tool.get("connector"),
        "enabled": enabled,
        "status": status,
        "dataIsolation": tool.get("dataIsolation"),
        "actionCount": len(actions),
        "allowedActionCount": allowed_action_count,
        "maxRiskLevel": max_risk,
        "secretsRequired": secrets_required,
        "secretState": "required_unverified" if secrets_required else "not_required",
        "missingPermissions": missing,
        "nextActions": _next_actions(
            enabled = enabled,
            secrets_required = secrets_required,
            missing_permissions = missing,
            max_risk = max_risk,
        ),
    }


def build_integration_status(
    *,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    permissions = _permission_set(
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    registry = cognix_tool_registry.build_tool_registry()
    integrations = [
        _integration_record(tool, permissions)
        for tool in registry.get("tools") or []
        if isinstance(tool, dict)
    ]
    return {
        "username": username,
        "integrationManagerVersion": COGNIX_INTEGRATION_MANAGER_VERSION,
        "mode": "dry_run",
        "integrations": integrations,
        "summary": {
            "integrationCount": len(integrations),
            "enabledCount": sum(1 for item in integrations if item.get("enabled")),
            "disabledCount": sum(1 for item in integrations if not item.get("enabled")),
            "secretsRequiredCount": sum(1 for item in integrations if item.get("secretsRequired")),
            "highRiskIntegrationCount": sum(
                1 for item in integrations if _risk_rank(str(item.get("maxRiskLevel"))) >= _risk_rank("high")
            ),
            "directFrontendExecutionAllowed": False,
            "activationContractRequired": True,
        },
        "policies": {
            "secretsStayServerSide": True,
            "humanConfirmationForWrites": True,
            "auditRequired": True,
            "rateLimitsRequired": True,
            "toolExecutionRequiresSeparateExecutor": True,
            "activationRequiresSeparateExecutor": True,
        },
        "sideEffects": {
            "integrationActivation": False,
            "secretRead": False,
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
        },
    }


def build_integration_plan(
    *,
    tool_id: str,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    status = build_integration_status(
        username = username,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    integration = next(
        (item for item in status["integrations"] if item.get("id") == tool_id),
        None,
    )
    if integration is None:
        return {
            "username": username,
            "integrationManagerVersion": COGNIX_INTEGRATION_MANAGER_VERSION,
            "mode": "dry_run",
            "toolId": tool_id,
            "status": "unknown_integration",
            "allowedToActivate": False,
            "humanApprovalRequired": True,
            "activationContract": _activation_contract(
                integration = None,
                username = username,
                status_side_effects = status["sideEffects"],
            ),
            "steps": [
                {
                    "id": "verify_manifest",
                    "status": "blocked",
                    "detail": "Integration absente du registre CogniX.",
                }
            ],
            "sideEffects": status["sideEffects"],
        }

    next_actions = integration.get("nextActions") or []
    max_risk = str(integration.get("maxRiskLevel") or "low")
    allowed_to_activate = bool(
        integration.get("enabled")
        and not integration.get("missingPermissions")
        and not integration.get("secretsRequired")
    )
    return {
        "username": username,
        "integrationManagerVersion": COGNIX_INTEGRATION_MANAGER_VERSION,
        "activationContractVersion": COGNIX_INTEGRATION_ACTIVATION_CONTRACT_VERSION,
        "mode": "dry_run",
        "toolId": integration.get("id"),
        "connector": integration.get("connector"),
        "status": integration.get("status"),
        "allowedToActivate": allowed_to_activate,
        "humanApprovalRequired": True if next_actions else _risk_rank(max_risk) >= _risk_rank("medium"),
        "integration": integration,
        "activationContract": _activation_contract(
            integration = integration,
            username = username,
            status_side_effects = status["sideEffects"],
        ),
        "steps": [
            {
                "id": "verify_manifest",
                "status": "complete",
                "detail": "Manifest declaratif charge depuis le Tool Registry.",
            },
            {
                "id": "verify_server_secret",
                "status": "planned" if integration.get("secretsRequired") else "skipped",
                "detail": "Aucun secret lu; configuration serveur a faire hors plan dry-run.",
            },
            {
                "id": "verify_permissions",
                "status": "planned" if integration.get("missingPermissions") else "complete",
                "detail": "Permissions utilisateur comparees aux actions declarees.",
            },
            {
                "id": "enable_guarded_connector",
                "status": "planned" if not integration.get("enabled") else "complete",
                "detail": "Activation separee, auditee, reservee aux garde-fous CogniX.",
            },
            {
                "id": "dry_run_guard",
                "status": "complete",
                "detail": "Aucun appel reseau, secret ou action outil pendant ce plan.",
            },
        ],
        "nextActions": next_actions,
        "sideEffects": status["sideEffects"],
    }
