# SPDX-License-Identifier: AGPL-3.0-only

"""Native CogniX admin permission engine and RBAC planning."""

from __future__ import annotations

from typing import Any


COGNIX_PERMISSION_ENGINE_VERSION = "cognix_permission_engine_v1"
COGNIX_ROLE_MANAGER_VERSION = "cognix_role_manager_v1"
COGNIX_PERMISSION_OVERRIDE_VERSION = "cognix_permission_override_service_v1"

DEFAULT_PERMISSION_CATALOG: list[dict[str, Any]] = [
    {
        "permissionKey": "models:install",
        "module": "models",
        "displayName": "Install models",
        "description": "Install or register local models.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "models:run:cloud",
        "module": "models",
        "displayName": "Run cloud models",
        "description": "Use cloud inference providers.",
        "riskLevel": "high",
    },
    {
        "permissionKey": "tools:execute",
        "module": "tools",
        "displayName": "Execute tools",
        "description": "Run native tool actions through CogniX.",
        "riskLevel": "high",
    },
    {
        "permissionKey": "tools:cloud_training",
        "module": "training",
        "displayName": "Cloud training",
        "description": "Prepare Kaggle, Colab, or cloud GPU handoffs without requiring a local AMD/NVIDIA GPU.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "images:generate",
        "module": "images",
        "displayName": "Generate images",
        "description": "Use image generation features.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "codex:run",
        "module": "codex",
        "displayName": "Run Codex",
        "description": "Use code execution and repository automation.",
        "riskLevel": "critical",
    },
    {
        "permissionKey": "cowork:control",
        "module": "cowork",
        "displayName": "Control cowork sessions",
        "description": "Create and steer collaborative agent sessions.",
        "riskLevel": "high",
    },
    {
        "permissionKey": "admin:read",
        "module": "admin",
        "displayName": "Read admin panels",
        "description": "Read administrative surfaces.",
        "riskLevel": "high",
    },
    {
        "permissionKey": "admin:permissions:update",
        "module": "admin",
        "displayName": "Manage permissions",
        "description": "Create roles, grants, denies, and project-scoped permissions.",
        "riskLevel": "critical",
    },
    {
        "permissionKey": "library:share",
        "module": "library",
        "displayName": "Share library assets",
        "description": "Share prompts, documents, models, or datasets.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "projects:collaborate",
        "module": "projects",
        "displayName": "Collaborate on projects",
        "description": "Join and edit shared CogniX projects.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "developer_mode",
        "module": "developer",
        "displayName": "Developer mode",
        "description": "Use legacy developer-mode unlocks.",
        "riskLevel": "critical",
    },
    {
        "permissionKey": "github:read",
        "module": "integrations",
        "displayName": "Read GitHub",
        "description": "Read GitHub repository data through connected tools.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "tools:codex",
        "module": "tools",
        "displayName": "Codex tool",
        "description": "Use Codex-backed tool execution.",
        "riskLevel": "critical",
    },
    {
        "permissionKey": "tools:terminal",
        "module": "tools",
        "displayName": "Terminal tool",
        "description": "Use terminal-backed tool execution.",
        "riskLevel": "critical",
    },
    {
        "permissionKey": "tools:web_search",
        "module": "tools",
        "displayName": "Web search",
        "description": "Use browser or search backed tool execution.",
        "riskLevel": "medium",
    },
    {
        "permissionKey": "tools:kaggle",
        "module": "training",
        "displayName": "Kaggle training",
        "description": "Prepare Kaggle training handoffs.",
        "riskLevel": "medium",
    },
]

CEO_CLOUD_TRAINING_PERMISSIONS = {
    "models:run:cloud",
    "tools:cloud_training",
    "tools:kaggle",
}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _key(value: Any, fallback: str = "") -> str:
    return _norm(value, fallback).lower()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "allow", "allowed"}
    return bool(value)


def _permission_key(row: dict[str, Any]) -> str:
    return _key(row.get("permission_key") or row.get("permissionKey"))


def _role_key(row: dict[str, Any]) -> str:
    role = _key(row.get("role_key") or row.get("roleKey") or row.get("role"), "user") or "user"
    plan = _key(row.get("plan"))
    if role != "admin" and plan == "ceo":
        return "ceo"
    return role


def _username(row: dict[str, Any]) -> str:
    return _norm(row.get("username"))


def _status(row: dict[str, Any]) -> str:
    value = _key(row.get("status"), "active")
    return value if value in {"active", "disabled"} else "active"


def _catalog_item(row: dict[str, Any]) -> dict[str, Any]:
    permission_key = _permission_key(row)
    module = _key(row.get("module_key") or row.get("moduleKey") or row.get("module"), "general")
    return {
        "permissionKey": permission_key,
        "module": module,
        "displayName": _norm(row.get("display_name") or row.get("displayName"), permission_key),
        "description": _norm(row.get("description")),
        "riskLevel": _key(row.get("risk_level") or row.get("riskLevel"), "medium"),
        "status": _status(row),
    }


def _catalog_map(permission_definitions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    catalog = {_permission_key(item): _catalog_item(item) for item in DEFAULT_PERMISSION_CATALOG}
    for item in permission_definitions:
        if _status(item) != "active":
            continue
        permission_key = _permission_key(item)
        if permission_key:
            catalog[permission_key] = _catalog_item(item)
    return catalog


def _source_record(
    *,
    source: str,
    permission_key: str,
    allowed: bool,
    updated_by: Any = None,
    updated_at: Any = None,
    reason: Any = None,
    project_id: Any = None,
) -> dict[str, Any]:
    record = {
        "source": source,
        "permissionKey": permission_key,
        "allowed": bool(allowed),
        "updatedBy": updated_by,
        "updatedAt": updated_at,
        "reason": reason,
    }
    if project_id is not None:
        record["projectId"] = project_id
    return record


def build_permissions_blueprint() -> dict[str, Any]:
    return {
        "permissionEngineVersion": COGNIX_PERMISSION_ENGINE_VERSION,
        "roleManagerVersion": COGNIX_ROLE_MANAGER_VERSION,
        "permissionOverrideVersion": COGNIX_PERMISSION_OVERRIDE_VERSION,
        "mode": "native_rbac_permissions",
        "services": ["PermissionEngine", "RoleManager", "PermissionOverrideService"],
        "tables": [
            "roles",
            "permissions",
            "role_permissions",
            "user_permission_overrides",
            "project_permissions",
            "cognix_roles",
            "cognix_permissions",
            "cognix_role_permissions",
            "cognix_user_permission_overrides",
            "cognix_project_permissions",
            "cognix_user_permissions",
        ],
        "composition": [
            "role permissions",
            "legacy user grants",
            "user overrides",
            "project permissions",
            "organization policy",
        ],
        "actions": [
            "create_role",
            "update_role_permission",
            "grant_permission",
            "deny_permission",
            "remove_override",
            "scope_project_permission",
        ],
        "catalog": DEFAULT_PERMISSION_CATALOG,
        "sideEffects": {
            "roleWrite": False,
            "permissionCatalogWrite": False,
            "rolePermissionWrite": False,
            "userOverrideWrite": False,
            "projectPermissionWrite": False,
            "legacyPermissionWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _roles_by_key(users: list[dict[str, Any]], roles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for role in roles:
        if _status(role) != "active":
            continue
        role_key = _role_key(role)
        mapped[role_key] = {
            "roleKey": role_key,
            "displayName": _norm(role.get("display_name") or role.get("displayName"), role_key),
            "description": _norm(role.get("description")),
            "status": "active",
        }
    for user in users:
        role_key = _role_key(user)
        mapped.setdefault(
            role_key,
            {
                "roleKey": role_key,
                "displayName": role_key.upper() if role_key == "ceo" else role_key.title(),
                "description": "Derived from user profiles.",
                "status": "active",
            },
        )
    mapped.setdefault(
        "user",
        {"roleKey": "user", "displayName": "User", "description": "Default CogniX user role.", "status": "active"},
    )
    mapped.setdefault(
        "admin",
        {"roleKey": "admin", "displayName": "Admin", "description": "CogniX administrator role.", "status": "active"},
    )
    return mapped


def _role_permissions_by_role(
    role_permissions: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    mapped: dict[str, dict[str, dict[str, Any]]] = {}
    for permission_key in catalog:
        mapped.setdefault("admin", {})[permission_key] = {
            "role_key": "admin",
            "permission_key": permission_key,
            "allowed": 1,
            "source": "builtin_admin_role",
        }
    for permission_key in CEO_CLOUD_TRAINING_PERMISSIONS:
        if permission_key in catalog:
            mapped.setdefault("ceo", {})[permission_key] = {
                "role_key": "ceo",
                "permission_key": permission_key,
                "allowed": 1,
                "source": "builtin_ceo_cloud_training",
            }
    for item in role_permissions:
        role_key = _role_key(item)
        permission_key = _permission_key(item)
        if not role_key or not permission_key:
            continue
        mapped.setdefault(role_key, {})[permission_key] = item
    return mapped


def _legacy_by_user(legacy_user_permissions: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    mapped: dict[str, dict[str, dict[str, Any]]] = {}
    for item in legacy_user_permissions:
        username = _key(item.get("username"))
        permission_key = _permission_key(item)
        if username and permission_key:
            mapped.setdefault(username, {})[permission_key] = item
    return mapped


def _overrides_by_user(user_overrides: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    mapped: dict[str, dict[str, dict[str, Any]]] = {}
    for item in user_overrides:
        username = _key(item.get("username"))
        permission_key = _permission_key(item)
        if username and permission_key:
            mapped.setdefault(username, {})[permission_key] = item
    return mapped


def _policy_by_permission(organization_policy: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for item in organization_policy or []:
        permission_key = _permission_key(item)
        if permission_key:
            mapped[permission_key] = item
    return mapped


def _project_scopes_for_user(
    *,
    username: str,
    role: str,
    permission_key: str,
    project_permissions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    username_key = username.lower()
    role_key = role.lower()
    for item in project_permissions:
        if _permission_key(item) != permission_key:
            continue
        subject_type = _key(item.get("subject_type") or item.get("subjectType"))
        subject_id = _key(item.get("subject_id") or item.get("subjectId"))
        if subject_type == "user" and subject_id != username_key:
            continue
        if subject_type == "role" and subject_id != role_key:
            continue
        if subject_type == "group" and subject_id not in {"all", "everyone", "*"}:
            continue
        scopes.append(
            {
                "projectId": _norm(item.get("project_id") or item.get("projectId")),
                "subjectType": subject_type,
                "subjectId": _norm(item.get("subject_id") or item.get("subjectId")),
                "allowed": _bool(item.get("allowed")),
                "source": "project_permission",
                "updatedBy": item.get("updated_by") or item.get("updatedBy"),
                "updatedAt": item.get("updated_at") or item.get("updatedAt"),
            }
        )
    return scopes


def _permission_groups(permissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for permission in permissions:
        grouped.setdefault(permission["module"], []).append(permission)
    return [
        {"module": module, "permissions": sorted(items, key = lambda item: item["permissionKey"])}
        for module, items in sorted(grouped.items())
    ]


def build_permission_matrix(
    *,
    users: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    role_permissions: list[dict[str, Any]],
    user_overrides: list[dict[str, Any]],
    project_permissions: list[dict[str, Any]],
    legacy_user_permissions: list[dict[str, Any]],
    organization_policy: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = _catalog_map(permissions)
    for item in role_permissions + user_overrides + project_permissions + legacy_user_permissions:
        permission_key = _permission_key(item)
        if permission_key:
            catalog.setdefault(
                permission_key,
                {
                    "permissionKey": permission_key,
                    "module": permission_key.split(":", 1)[0] if ":" in permission_key else "general",
                    "displayName": permission_key,
                    "description": "",
                    "riskLevel": "medium",
                    "status": "active",
                },
            )
    roles_map = _roles_by_key(users, roles)
    role_perm_map = _role_permissions_by_role(role_permissions, catalog)
    legacy_map = _legacy_by_user(legacy_user_permissions)
    override_map = _overrides_by_user(user_overrides)
    policy_map = _policy_by_permission(organization_policy)
    matrix_users: list[dict[str, Any]] = []

    for user in users:
        username = _username(user)
        role = _role_key(user)
        username_key = username.lower()
        permission_rows: list[dict[str, Any]] = []
        for permission_key, definition in sorted(catalog.items()):
            allowed = False
            source = "default_deny"
            source_chain = [
                _source_record(source = "default_deny", permission_key = permission_key, allowed = False)
            ]

            role_permission = role_perm_map.get(role, {}).get(permission_key)
            if role_permission:
                allowed = _bool(role_permission.get("allowed"))
                source = _norm(role_permission.get("source"), "role_permission")
                source_chain.append(
                    _source_record(
                        source = source,
                        permission_key = permission_key,
                        allowed = allowed,
                        updated_by = role_permission.get("updated_by") or role_permission.get("updatedBy"),
                        updated_at = role_permission.get("updated_at") or role_permission.get("updatedAt"),
                    )
                )

            legacy = legacy_map.get(username_key, {}).get(permission_key)
            if legacy:
                allowed = True
                source = "legacy_user_permission"
                source_chain.append(
                    _source_record(
                        source = source,
                        permission_key = permission_key,
                        allowed = True,
                        updated_by = legacy.get("granted_by") or legacy.get("grantedBy"),
                        updated_at = legacy.get("granted_at") or legacy.get("grantedAt"),
                    )
                )

            override = override_map.get(username_key, {}).get(permission_key)
            if override:
                effect = _key(override.get("effect"), "allow")
                allowed = effect == "allow"
                source = "user_override"
                source_chain.append(
                    _source_record(
                        source = source,
                        permission_key = permission_key,
                        allowed = allowed,
                        updated_by = override.get("updated_by") or override.get("updatedBy"),
                        updated_at = override.get("updated_at") or override.get("updatedAt"),
                        reason = override.get("reason"),
                    )
                )

            project_scopes = _project_scopes_for_user(
                username = username,
                role = role,
                permission_key = permission_key,
                project_permissions = project_permissions,
            )

            policy = policy_map.get(permission_key)
            if policy:
                policy_allowed = _bool(policy.get("allowed"))
                allowed = policy_allowed
                source = "organization_policy"
                source_chain.append(
                    _source_record(
                        source = source,
                        permission_key = permission_key,
                        allowed = policy_allowed,
                        updated_by = policy.get("updated_by") or policy.get("updatedBy"),
                        updated_at = policy.get("updated_at") or policy.get("updatedAt"),
                        reason = policy.get("reason"),
                    )
                )

            permission_rows.append(
                {
                    "permissionKey": permission_key,
                    "module": definition["module"],
                    "displayName": definition["displayName"],
                    "description": definition.get("description", ""),
                    "riskLevel": definition.get("riskLevel", "medium"),
                    "allowed": allowed,
                    "source": source,
                    "sourceChain": source_chain,
                    "projectScopes": project_scopes,
                    "toggle": {
                        "state": "on" if allowed else "off",
                        "canOverride": source != "organization_policy",
                    },
                }
            )
        matrix_users.append(
            {
                "username": username,
                "role": role,
                "plan": _norm(user.get("plan")),
                "permissions": permission_rows,
                "permissionGroups": _permission_groups(permission_rows),
            }
        )

    return {
        "permissionEngineVersion": COGNIX_PERMISSION_ENGINE_VERSION,
        "roleManagerVersion": COGNIX_ROLE_MANAGER_VERSION,
        "permissionOverrideVersion": COGNIX_PERMISSION_OVERRIDE_VERSION,
        "roles": sorted(roles_map.values(), key = lambda item: item["roleKey"]),
        "catalog": sorted(catalog.values(), key = lambda item: (item["module"], item["permissionKey"])),
        "users": matrix_users,
        "policies": {
            "permissionSource": "role_permissions_plus_legacy_plus_overrides_plus_project_plus_org",
            "projectScopedPermissions": True,
            "organizationPolicySupported": True,
        },
        "sideEffects": build_permissions_blueprint()["sideEffects"],
    }


def build_permission_decision(
    *,
    username: str,
    permission_key: str,
    matrix: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    normalized_username = username.strip()
    normalized_permission = permission_key.strip().lower()
    for user in matrix.get("users", []):
        if _key(user.get("username")) != normalized_username.lower():
            continue
        for permission in user.get("permissions", []):
            if _key(permission.get("permissionKey")) != normalized_permission:
                continue
            source = permission.get("source")
            allowed = bool(permission.get("allowed"))
            project_scope = None
            if project_id:
                for scope in permission.get("projectScopes", []):
                    if _norm(scope.get("projectId")) == project_id:
                        project_scope = scope
                        allowed = bool(scope.get("allowed"))
                        source = "project_permission"
                        break
            return {
                "username": normalized_username,
                "permissionKey": normalized_permission,
                "projectId": project_id,
                "allowed": allowed,
                "source": source,
                "sourceChain": permission.get("sourceChain", []),
                "projectScope": project_scope,
                "riskLevel": permission.get("riskLevel", "medium"),
                "decisionVersion": COGNIX_PERMISSION_ENGINE_VERSION,
                "sideEffects": {
                    "modelLoad": False,
                    "generation": False,
                    "toolExecution": False,
                    "networkCall": False,
                    "databaseWrite": False,
                },
            }
    return {
        "username": normalized_username,
        "permissionKey": normalized_permission,
        "projectId": project_id,
        "allowed": False,
        "source": "unknown_user_or_permission",
        "sourceChain": [],
        "projectScope": None,
        "riskLevel": "medium",
        "decisionVersion": COGNIX_PERMISSION_ENGINE_VERSION,
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
            "databaseWrite": False,
        },
    }
