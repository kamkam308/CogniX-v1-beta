# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Declarative CogniX tool registry.

The registry is intentionally execution-free. It tells the orchestrator which
tool actions exist, what they are allowed to do, and what guardrails must be in
place before a later executor can run them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TOOL_REGISTRY_VERSION = "cognix_tool_registry_v1"

RISK_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

IMPLICIT_AUTHENTICATED_PERMISSION = "authenticated"
DEVELOPER_MODE_PERMISSION = "developer_mode"
ADMIN_PERMISSION = "admin"

DEFAULT_RATE_LIMIT_POLICY = {
    "windowSeconds": 60,
    "maxEvents": 60,
}

RATE_LIMIT_POLICIES: dict[str, dict[str, int]] = {
    "github:read": {"windowSeconds": 60, "maxEvents": 120},
    "github:write": {"windowSeconds": 60, "maxEvents": 20},
    "github:merge": {"windowSeconds": 300, "maxEvents": 3},
    "drive:read": {"windowSeconds": 60, "maxEvents": 120},
    "drive:delete": {"windowSeconds": 300, "maxEvents": 3},
    "gmail:read": {"windowSeconds": 60, "maxEvents": 120},
    "gmail:draft": {"windowSeconds": 60, "maxEvents": 30},
    "gmail:send": {"windowSeconds": 300, "maxEvents": 5},
    "notion:read": {"windowSeconds": 60, "maxEvents": 120},
    "notion:write": {"windowSeconds": 60, "maxEvents": 30},
    "rag:index": {"windowSeconds": 300, "maxEvents": 12},
    "codex:plan": {"windowSeconds": 60, "maxEvents": 120},
    "codex:write": {"windowSeconds": 300, "maxEvents": 20},
    "codex:merge": {"windowSeconds": 600, "maxEvents": 2},
    "security:scan": {"windowSeconds": 600, "maxEvents": 5},
    "security:active": {"windowSeconds": 1800, "maxEvents": 1},
}


TOOL_MANIFESTS: list[dict[str, Any]] = [
    {
        "id": "github",
        "name": "GitHub",
        "category": "code",
        "description": "Depots, issues, pull requests et workflow de developpement.",
        "connector": "github",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "read_repository",
                "label": "Lire un depot",
                "description": "Lire les fichiers, issues et pull requests accessibles.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "github:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "github:read",
                "secretsRequired": True,
            },
            {
                "id": "create_issue",
                "label": "Creer une issue",
                "description": "Creer une issue ou un brouillon de suivi dans un depot.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "github:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "github:write",
                "secretsRequired": True,
            },
            {
                "id": "merge_pull_request",
                "label": "Fusionner une pull request",
                "description": "Action critique reservee aux admins ou validations humaines.",
                "mode": "write",
                "permissions": [ADMIN_PERMISSION, "github:merge"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "github:merge",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "category": "files",
        "description": "Lecture, indexation et organisation de documents utilisateur.",
        "connector": "google-drive",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "read_document",
                "label": "Lire un document",
                "description": "Lire un document accessible pour alimenter RAG ou contexte.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "drive:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "drive:read",
                "secretsRequired": True,
            },
            {
                "id": "index_document",
                "label": "Indexer un document",
                "description": "Importer un document dans la memoire documentaire CogniX.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "rag:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "rag:index",
                "secretsRequired": True,
            },
            {
                "id": "delete_file",
                "label": "Supprimer un fichier",
                "description": "Suppression distante; interdite sans role admin et confirmation.",
                "mode": "delete",
                "permissions": [ADMIN_PERMISSION, "drive:delete"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "drive:delete",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "gmail",
        "name": "Gmail",
        "category": "communication",
        "description": "Recherche mail, brouillons et envoi controle.",
        "connector": "gmail",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "search_mail",
                "label": "Chercher des emails",
                "description": "Lire les emails accessibles pour resumer ou preparer une reponse.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "gmail:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "gmail:read",
                "secretsRequired": True,
            },
            {
                "id": "create_draft",
                "label": "Creer un brouillon",
                "description": "Creer un brouillon sans envoyer de message.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "gmail:draft"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "gmail:draft",
                "secretsRequired": True,
            },
            {
                "id": "send_mail",
                "label": "Envoyer un email",
                "description": "Envoi reel; confirmation humaine obligatoire.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "gmail:send"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "gmail:send",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "notion",
        "name": "Notion",
        "category": "productivity",
        "description": "Lecture et creation de pages de travail.",
        "connector": "notion",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "read_page",
                "label": "Lire une page",
                "description": "Lire une page ou base Notion accessible.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "notion:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "notion:read",
                "secretsRequired": True,
            },
            {
                "id": "create_page",
                "label": "Creer une page",
                "description": "Creer une page ou note structuree.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "notion:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "notion:write",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "codex-secure-agent",
        "name": "Codex Secure Agent",
        "category": "development",
        "description": "Pipeline interne branche Git, tests, build et validation humaine.",
        "connector": "local-codex",
        "enabled": True,
        "dataIsolation": "workspace",
        "actions": [
            {
                "id": "plan_feature",
                "label": "Planifier une feature",
                "description": "Analyser une demande et produire un plan sans modifier le code.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "codex:plan",
                "secretsRequired": False,
            },
            {
                "id": "modify_code",
                "label": "Modifier le code",
                "description": "Modifier le code sur branche avec tests et build obligatoires.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "codex:write",
                "secretsRequired": False,
            },
            {
                "id": "merge_to_main",
                "label": "Fusionner vers main",
                "description": "Merge final; reserve aux admins apres validation humaine.",
                "mode": "write",
                "permissions": [ADMIN_PERMISSION],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "codex:merge",
                "secretsRequired": False,
            },
        ],
    },
    {
        "id": "kali-isolated",
        "name": "Kali Isolated Toolkit",
        "category": "security",
        "description": "Boite a outils cyber uniquement en VM/container isole.",
        "connector": "isolated-container",
        "enabled": False,
        "dataIsolation": "ephemeral_container",
        "actions": [
            {
                "id": "passive_scan",
                "label": "Scan passif",
                "description": "Analyse passive autorisee uniquement sur cible validee.",
                "mode": "execute",
                "permissions": [DEVELOPER_MODE_PERMISSION, "security:passive_scan"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "security:scan",
                "secretsRequired": False,
            },
            {
                "id": "active_test",
                "label": "Test actif",
                "description": "Action critique exigeant isolation, admin et autorisation explicite.",
                "mode": "execute",
                "permissions": [ADMIN_PERMISSION, "security:active_test"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "security:active",
                "secretsRequired": False,
            },
        ],
    },
]


def _normalize_permission(permission: str) -> str:
    return permission.strip().lower()


def _risk_at_least(risk: str, threshold: str) -> bool:
    return RISK_ORDER.get(risk, 0) >= RISK_ORDER.get(threshold, 0)


def _permission_context(
    *,
    username: str,
    is_admin: bool,
    has_developer_mode: bool,
    granted_permissions: set[str] | None,
) -> dict[str, Any]:
    explicit_permissions = sorted(
        {
            _normalize_permission(str(item))
            for item in (granted_permissions or set())
            if str(item or "").strip()
        }
    )
    effective_permissions = set(explicit_permissions)
    effective_permissions.add(IMPLICIT_AUTHENTICATED_PERMISSION)
    if is_admin:
        effective_permissions.add(ADMIN_PERMISSION)
        effective_permissions.add(DEVELOPER_MODE_PERMISSION)
    if has_developer_mode:
        effective_permissions.add(DEVELOPER_MODE_PERMISSION)
    return {
        "username": username,
        "isAdmin": bool(is_admin),
        "developerMode": bool(is_admin or has_developer_mode),
        "explicitPermissions": explicit_permissions,
        "effectivePermissions": sorted(effective_permissions),
        "derivedPermissions": sorted(
            permission
            for permission in effective_permissions
            if permission not in set(explicit_permissions)
        ),
        "sideEffects": {
            "permissionWrite": False,
            "secretRead": False,
            "toolExecution": False,
        },
    }


def _permission_set_from_context(context: dict[str, Any]) -> set[str]:
    return {
        _normalize_permission(str(item))
        for item in context.get("effectivePermissions", [])
        if str(item or "").strip()
    }


def _action_decision(
    *,
    tool: dict[str, Any],
    action: dict[str, Any],
    permission_set: set[str],
) -> dict[str, Any]:
    required_permissions = [
        _normalize_permission(str(item))
        for item in action.get("permissions", [])
        if str(item or "").strip()
    ]
    missing = [
        permission for permission in required_permissions if permission not in permission_set
    ]
    enabled = bool(tool.get("enabled"))
    risk_level = str(action.get("riskLevel") or "medium").lower()
    mode = str(action.get("mode") or "read")
    rate_limit_key = action.get("rateLimitKey")
    requires_confirmation = bool(action.get("requiresConfirmation")) or _risk_at_least(risk_level, "medium")
    admin_required = ADMIN_PERMISSION in required_permissions or _risk_at_least(risk_level, "critical")
    allowed = enabled and not missing
    status = "allowed" if allowed else ("connector_disabled" if not enabled else "missing_permission")
    blockers: list[dict[str, Any]] = []
    if not enabled:
        blockers.append(
            {
                "id": "connector_disabled",
                "reason": "Connector is declared in CogniX but not enabled.",
            }
        )
    if missing:
        blockers.append(
            {
                "id": "missing_permissions",
                "reason": "User is missing required tool permissions.",
                "permissions": missing,
            }
        )
    return {
        "allowed": allowed,
        "status": status,
        "reason": (
            "Action allowed by CogniX guardrails."
            if allowed
            else (
                "Connector is declared but not enabled yet."
                if not enabled
                else "User is missing required tool permissions."
            )
        ),
        "mode": mode,
        "riskLevel": risk_level,
        "requiredPermissions": required_permissions,
        "missingPermissions": missing,
        "requiresConfirmation": requires_confirmation,
        "auditRequired": bool(action.get("auditRequired", True)),
        "sandboxRequired": bool(action.get("sandboxRequired")),
        "rateLimitKey": rate_limit_key,
        "rateLimitPolicy": rate_limit_policy_for_key(
            str(rate_limit_key) if rate_limit_key else None
        ),
        "secretsRequired": bool(action.get("secretsRequired")),
        "dataIsolation": tool.get("dataIsolation"),
        "adminRequired": admin_required,
        "guardrails": {
            "humanConfirmationRequired": requires_confirmation,
            "auditRequired": bool(action.get("auditRequired", True)),
            "rateLimitRequired": bool(rate_limit_key),
            "sandboxRequired": bool(action.get("sandboxRequired")),
            "secretsStayServerSide": bool(action.get("secretsRequired")),
            "adminRequired": admin_required,
            "frontendDirectExecutionAllowed": False,
        },
        "blockers": blockers,
        "sideEffects": {
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
            "secretRead": False,
            "permissionWrite": False,
        },
    }


def build_tool_registry() -> dict[str, Any]:
    tools = deepcopy(TOOL_MANIFESTS)
    action_count = sum(len(tool.get("actions") or []) for tool in tools)
    high_risk_count = sum(
        1
        for tool in tools
        for action in tool.get("actions") or []
        if _risk_at_least(str(action.get("riskLevel") or ""), "high")
    )
    return {
        "registryVersion": TOOL_REGISTRY_VERSION,
        "mode": "declarative_guarded",
        "tools": tools,
        "summary": {
            "toolCount": len(tools),
            "actionCount": action_count,
            "highRiskActionCount": high_risk_count,
            "executionEnabled": False,
            "auditRequiredByDefault": True,
        },
        "globalPolicies": {
            "humanConfirmationForRiskAtLeast": "medium",
            "adminOnlyForRiskAtLeast": "critical",
            "auditRequired": True,
            "rateLimitsEnabled": True,
            "secretsMustStayServerSide": True,
            "permissionMatrixAvailable": True,
            "frontendDirectExecutionAllowed": False,
        },
        "sideEffects": {
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
        },
    }


def build_tool_permission_matrix(
    *,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    context = _permission_context(
        username = username,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    permission_set = _permission_set_from_context(context)
    tools: list[dict[str, Any]] = []
    allowed_count = 0
    confirmation_count = 0
    blocked_count = 0
    high_risk_count = 0
    for tool in TOOL_MANIFESTS:
        actions: list[dict[str, Any]] = []
        for action in tool.get("actions") or []:
            decision = _action_decision(
                tool = tool,
                action = action,
                permission_set = permission_set,
            )
            if decision["allowed"]:
                allowed_count += 1
            else:
                blocked_count += 1
            if decision["requiresConfirmation"]:
                confirmation_count += 1
            if _risk_at_least(str(decision["riskLevel"]), "high"):
                high_risk_count += 1
            actions.append(
                {
                    "id": action.get("id"),
                    "label": action.get("label"),
                    "connector": tool.get("connector"),
                    **decision,
                }
            )
        tools.append(
            {
                "id": tool.get("id"),
                "name": tool.get("name"),
                "category": tool.get("category"),
                "enabled": bool(tool.get("enabled")),
                "dataIsolation": tool.get("dataIsolation"),
                "actions": actions,
            }
        )
    return {
        "registryVersion": TOOL_REGISTRY_VERSION,
        "mode": "permission_matrix_dry_run",
        "username": username,
        "permissionContext": context,
        "tools": tools,
        "summary": {
            "toolCount": len(tools),
            "actionCount": allowed_count + blocked_count,
            "allowedActionCount": allowed_count,
            "blockedActionCount": blocked_count,
            "confirmationRequiredCount": confirmation_count,
            "highRiskActionCount": high_risk_count,
            "executionEnabled": False,
        },
        "policies": {
            "permissionSource": "cognix_user_permissions_plus_role",
            "humanConfirmationForRiskAtLeast": "medium",
            "adminOnlyForRiskAtLeast": "critical",
            "auditRequired": True,
            "rateLimitsEnabled": True,
            "secretsMustStayServerSide": True,
            "frontendDirectExecutionAllowed": False,
        },
        "sideEffects": {
            "permissionWrite": False,
            "secretRead": False,
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
        },
    }


def rate_limit_policy_for_key(rate_limit_key: str | None) -> dict[str, int] | None:
    if not rate_limit_key:
        return None
    policy = RATE_LIMIT_POLICIES.get(rate_limit_key.strip().lower())
    return deepcopy(policy or DEFAULT_RATE_LIMIT_POLICY)


def find_tool_action(tool_id: str, action_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    normalized_tool_id = tool_id.strip()
    normalized_action_id = action_id.strip()
    for tool in TOOL_MANIFESTS:
        if tool["id"] != normalized_tool_id:
            continue
        for action in tool.get("actions") or []:
            if action["id"] == normalized_action_id:
                return deepcopy(tool), deepcopy(action)
    return None


def plan_tool_action(
    *,
    tool_id: str,
    action_id: str,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    found = find_tool_action(tool_id, action_id)
    if found is None:
        return {
            "registryVersion": TOOL_REGISTRY_VERSION,
            "username": username,
            "toolId": tool_id,
            "actionId": action_id,
            "allowed": False,
            "status": "unknown_action",
            "reason": "Tool action is not registered in CogniX.",
            "missingPermissions": [],
            "requiresConfirmation": True,
            "riskLevel": "unknown",
            "sideEffects": {
                "toolExecution": False,
                "networkToolCall": False,
                "externalWrite": False,
                "secretRead": False,
                "permissionWrite": False,
            },
        }

    tool, action = found
    permission_context = _permission_context(
        username = username,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    decision = _action_decision(
        tool = tool,
        action = action,
        permission_set = _permission_set_from_context(permission_context),
    )
    return {
        "registryVersion": TOOL_REGISTRY_VERSION,
        "username": username,
        "toolId": tool["id"],
        "toolName": tool["name"],
        "actionId": action["id"],
        "actionLabel": action["label"],
        "permissionContext": permission_context,
        **decision,
    }
