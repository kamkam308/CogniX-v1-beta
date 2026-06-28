# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX organization, RBAC, SSO, and education governance planning.

The governance manager turns the Business, University, and Enterprise parts of
the CogniX roadmap into a native backend contract. It plans organizations,
roles, permissions, SSO, class spaces, and audit policies without creating
users, granting permissions, touching SSO secrets, syncing directories, or
mutating the database beyond the route-level audit log.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


COGNIX_GOVERNANCE_MANAGER_VERSION = "cognix_governance_manager_v1"

ROLE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "owner",
        "label": "Owner",
        "scope": "organization",
        "defaultFor": ["business", "enterprise"],
        "permissions": [
            "organization:manage",
            "users:invite",
            "roles:assign",
            "sso:configure",
            "audit:read",
            "deployment:approve",
        ],
        "riskLevel": "critical",
    },
    {
        "id": "admin",
        "label": "Admin",
        "scope": "organization",
        "defaultFor": ["business", "enterprise", "university"],
        "permissions": [
            "users:invite",
            "roles:assign",
            "projects:manage",
            "connectors:plan",
            "audit:read",
        ],
        "riskLevel": "high",
    },
    {
        "id": "security_admin",
        "label": "Security admin",
        "scope": "organization",
        "defaultFor": ["enterprise"],
        "permissions": [
            "security:manage",
            "sso:configure",
            "audit:export",
            "permissions:review",
        ],
        "riskLevel": "critical",
    },
    {
        "id": "teacher",
        "label": "Teacher",
        "scope": "education",
        "defaultFor": ["university"],
        "permissions": [
            "classes:manage",
            "course_documents:manage",
            "assignments:review",
            "student_progress:read",
        ],
        "riskLevel": "medium",
    },
    {
        "id": "student",
        "label": "Student",
        "scope": "education",
        "defaultFor": ["university"],
        "permissions": [
            "classes:read",
            "course_documents:read",
            "assignments:submit",
        ],
        "riskLevel": "low",
    },
    {
        "id": "member",
        "label": "Member",
        "scope": "workspace",
        "defaultFor": ["business", "enterprise"],
        "permissions": [
            "chat:use",
            "projects:create",
            "documents:read",
            "models:request",
        ],
        "riskLevel": "low",
    },
    {
        "id": "viewer",
        "label": "Viewer",
        "scope": "workspace",
        "defaultFor": ["business", "enterprise", "university"],
        "permissions": [
            "chat:use",
            "projects:read",
            "documents:read",
        ],
        "riskLevel": "low",
    },
]

SSO_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "local_password",
        "label": "Local password",
        "protocol": "local",
        "supportsDirectorySync": False,
        "requiresSecrets": False,
    },
    {
        "id": "microsoft_entra_id",
        "label": "Microsoft Entra ID",
        "protocol": "oidc",
        "supportsDirectorySync": True,
        "requiresSecrets": True,
    },
    {
        "id": "google_workspace",
        "label": "Google Workspace",
        "protocol": "oidc",
        "supportsDirectorySync": True,
        "requiresSecrets": True,
    },
    {
        "id": "saml_generic",
        "label": "Generic SAML 2.0",
        "protocol": "saml",
        "supportsDirectorySync": False,
        "requiresSecrets": True,
    },
]

EDITION_POLICIES: dict[str, dict[str, Any]] = {
    "free": {
        "maxUsers": 1,
        "requiresSso": False,
        "advancedAudit": False,
        "educationSpaces": False,
        "deploymentApproval": False,
    },
    "developer": {
        "maxUsers": 3,
        "requiresSso": False,
        "advancedAudit": False,
        "educationSpaces": False,
        "deploymentApproval": False,
    },
    "business": {
        "maxUsers": 250,
        "requiresSso": True,
        "advancedAudit": True,
        "educationSpaces": False,
        "deploymentApproval": True,
    },
    "university": {
        "maxUsers": 10000,
        "requiresSso": True,
        "advancedAudit": True,
        "educationSpaces": True,
        "deploymentApproval": True,
    },
    "enterprise": {
        "maxUsers": 100000,
        "requiresSso": True,
        "advancedAudit": True,
        "educationSpaces": True,
        "deploymentApproval": True,
    },
}


def _normalize(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")


def _clean_label(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    return text[:160] or fallback


def _slug(value: Any, fallback: str) -> str:
    text = _normalize(value)
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return (text or fallback)[:80]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize(value)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _edition(value: str | None, organization_type: str, user_count: int) -> str:
    normalized = _normalize(value)
    if normalized in EDITION_POLICIES:
        return normalized
    if organization_type in {"school", "university", "education"}:
        return "university"
    if user_count >= 250:
        return "enterprise"
    if user_count > 1:
        return "business"
    return "developer"


def _organization_type(value: str | None, edition: str) -> str:
    normalized = _normalize(value)
    if normalized in {"business", "company", "enterprise", "university", "school", "education", "personal"}:
        return normalized
    if edition == "university":
        return "university"
    if edition == "enterprise":
        return "enterprise"
    if edition == "business":
        return "business"
    return "personal"


def _provider(value: str | None, edition: str) -> dict[str, Any]:
    requested = _normalize(value)
    providers = {str(item.get("id")): item for item in SSO_PROVIDERS}
    if requested in providers:
        return deepcopy(providers[requested])
    if requested in {"microsoft", "azure_ad", "entra", "office_365"}:
        return deepcopy(providers["microsoft_entra_id"])
    if requested in {"google", "google_sso", "workspace"}:
        return deepcopy(providers["google_workspace"])
    if requested in {"saml", "saml2"}:
        return deepcopy(providers["saml_generic"])
    if EDITION_POLICIES.get(edition, {}).get("requiresSso"):
        return deepcopy(providers["microsoft_entra_id"])
    return deepcopy(providers["local_password"])


def _role_map() -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): deepcopy(item) for item in ROLE_CATALOG}


def _default_role_ids(edition: str, organization_type: str, requested_roles: list[str]) -> list[str]:
    role_ids: list[str] = []
    for role in ROLE_CATALOG:
        defaults = role.get("defaultFor") or []
        if edition in defaults:
            role_ids.append(str(role.get("id")))
    if organization_type in {"school", "university", "education"}:
        role_ids.extend(["teacher", "student"])
    if edition in {"business", "enterprise"}:
        role_ids.extend(["owner", "admin", "member", "viewer"])
    role_ids.extend(requested_roles)
    return _dedupe(role_ids)


def _selected_roles(edition: str, organization_type: str, requested_roles: list[str]) -> list[dict[str, Any]]:
    catalog = _role_map()
    roles = []
    for role_id in _default_role_ids(edition, organization_type, requested_roles):
        if role_id in catalog:
            roles.append(catalog[role_id])
    return roles


def _required_capabilities(
    *,
    edition: str,
    organization_type: str,
    user_count: int,
    data_sensitivity: str,
    requested_features: list[str],
) -> list[str]:
    capabilities = ["organizations", "rbac", "audit_logs", "admin_console"]
    if EDITION_POLICIES.get(edition, {}).get("requiresSso") or user_count >= 10:
        capabilities.append("sso")
    if user_count >= 50 or "directory_sync" in requested_features:
        capabilities.append("directory_sync")
    if organization_type in {"school", "university", "education"} or "classes" in requested_features:
        capabilities.extend(["education_spaces", "class_permissions"])
    if "exam_mode" in requested_features or organization_type in {"school", "university", "education"}:
        capabilities.append("exam_mode")
    if edition == "enterprise" or data_sensitivity in {"restricted", "confidential", "education_records"}:
        capabilities.extend(["advanced_audit", "data_residency", "security_review"])
    if edition in {"business", "enterprise", "university"}:
        capabilities.append("deployment_approval")
    return _dedupe(capabilities)


def _space_plan(
    *,
    organization_type: str,
    edition: str,
    classroom_count: int,
) -> list[dict[str, Any]]:
    spaces = [
        {
            "id": "organization_workspace",
            "label": "Organization workspace",
            "roleAccess": ["owner", "admin", "security_admin", "member", "viewer"],
            "status": "planned",
            "willCreate": False,
        }
    ]
    if edition in {"business", "enterprise"}:
        spaces.append(
            {
                "id": "department_workspaces",
                "label": "Department workspaces",
                "roleAccess": ["owner", "admin", "member"],
                "status": "planned",
                "willCreate": False,
            }
        )
    if organization_type in {"school", "university", "education"} or edition == "university":
        spaces.extend(
            [
                {
                    "id": "teacher_workspace",
                    "label": "Teacher workspace",
                    "roleAccess": ["admin", "teacher"],
                    "status": "planned",
                    "willCreate": False,
                },
                {
                    "id": "student_workspace",
                    "label": "Student workspace",
                    "roleAccess": ["student", "teacher"],
                    "status": "planned",
                    "willCreate": False,
                },
                {
                    "id": "class_spaces",
                    "label": "Class spaces",
                    "plannedCount": max(1, min(classroom_count, 500)),
                    "roleAccess": ["teacher", "student"],
                    "status": "planned",
                    "willCreate": False,
                },
                {
                    "id": "exam_mode",
                    "label": "Exam mode",
                    "roleAccess": ["admin", "teacher"],
                    "status": "planned",
                    "willCreate": False,
                },
            ]
        )
    return spaces


def build_governance_blueprint() -> dict[str, Any]:
    return {
        "governanceManagerVersion": COGNIX_GOVERNANCE_MANAGER_VERSION,
        "mode": "declarative_dry_run",
        "editions": deepcopy(EDITION_POLICIES),
        "roleCatalog": deepcopy(ROLE_CATALOG),
        "ssoProviders": deepcopy(SSO_PROVIDERS),
        "globalPolicies": {
            "leastPrivilegeRequired": True,
            "roleChangesRequireAudit": True,
            "ssoSecretsStayServerSide": True,
            "frontendCannotGrantRoles": True,
            "directorySyncRequiresApproval": True,
            "educationRecordsRequireScopedAccess": True,
        },
        "sideEffects": {
            "organizationWrite": False,
            "userInvite": False,
            "roleGrant": False,
            "permissionWrite": False,
            "ssoMutation": False,
            "secretRead": False,
            "secretWrite": False,
            "directorySync": False,
            "networkCall": False,
            "classroomWrite": False,
            "policyActivation": False,
        },
    }


def build_governance_plan(
    *,
    username: str,
    organization_name: str | None = None,
    organization_type: str | None = None,
    edition: str | None = None,
    user_count: int | None = None,
    roles: list[str] | None = None,
    sso_provider: str | None = None,
    data_sensitivity: str | None = None,
    classroom_count: int | None = None,
    requested_features: list[str] | None = None,
) -> dict[str, Any]:
    requested_roles = _dedupe(roles or [])
    requested = _dedupe(requested_features or [])
    users = max(1, min(int(user_count or 1), 100_000))
    normalized_sensitivity = _normalize(data_sensitivity) or "internal"
    normalized_edition = _edition(edition, _normalize(organization_type), users)
    normalized_type = _organization_type(organization_type, normalized_edition)
    provider = _provider(sso_provider, normalized_edition)
    policy = EDITION_POLICIES[normalized_edition]
    selected_roles = _selected_roles(normalized_edition, normalized_type, requested_roles)
    capability_ids = _required_capabilities(
        edition = normalized_edition,
        organization_type = normalized_type,
        user_count = users,
        data_sensitivity = normalized_sensitivity,
        requested_features = requested,
    )
    class_count = max(0, int(classroom_count or 0))
    warnings: list[str] = []
    if users > int(policy.get("maxUsers") or 1):
        warnings.append("Le nombre d'utilisateurs depasse la politique edition: prevoir upgrade ou shard enterprise.")
    if normalized_sensitivity in {"restricted", "confidential", "education_records"} and provider.get("id") == "local_password":
        warnings.append("Donnees sensibles sans SSO: exiger MFA, rotation et comptes admin separes.")
    if normalized_type in {"school", "university", "education"} and "student" not in {role["id"] for role in selected_roles}:
        warnings.append("Espace education sans role etudiant explicite: verifier les imports de classe.")

    sso_required = bool(policy.get("requiresSso")) or "sso" in capability_ids
    directory_sync_required = bool(provider.get("supportsDirectorySync")) and (
        users >= 50 or "directory_sync" in capability_ids
    )
    approval_required = sso_required or normalized_edition in {"business", "enterprise", "university"}
    organization_id = _slug(organization_name, "cognix_org")

    return {
        "governanceManagerVersion": COGNIX_GOVERNANCE_MANAGER_VERSION,
        "mode": "dry_run",
        "username": username,
        "organization": {
            "id": organization_id,
            "name": _clean_label(organization_name, "CogniX Organization"),
            "type": normalized_type,
            "edition": normalized_edition,
            "plannedUserCount": users,
            "dataSensitivity": normalized_sensitivity,
            "willCreate": False,
        },
        "requiredCapabilities": capability_ids,
        "roles": selected_roles,
        "roleMatrix": [
            {
                "roleId": role.get("id"),
                "scope": role.get("scope"),
                "permissions": role.get("permissions", []),
                "riskLevel": role.get("riskLevel"),
                "willGrant": False,
            }
            for role in selected_roles
        ],
        "spacePlan": _space_plan(
            organization_type = normalized_type,
            edition = normalized_edition,
            classroom_count = class_count,
        ),
        "ssoPlan": {
            "required": sso_required,
            "provider": provider,
            "status": "planned" if sso_required else "optional",
            "directorySyncRequired": directory_sync_required,
            "claimsRequired": ["email", "name", "groups", "role"],
            "mfaRequired": normalized_sensitivity in {"restricted", "confidential", "education_records"}
            or normalized_edition in {"business", "enterprise", "university"},
            "willReadSecrets": False,
            "willWriteSecrets": False,
            "willUpdateProvider": False,
            "willSyncDirectory": False,
        },
        "policyPlan": {
            "leastPrivilegeRequired": True,
            "rbacRequired": True,
            "advancedAuditRequired": bool(policy.get("advancedAudit")),
            "deploymentApprovalRequired": bool(policy.get("deploymentApproval")),
            "educationRecordsScoped": normalized_type in {"school", "university", "education"},
            "dataResidencyRequired": normalized_sensitivity in {"restricted", "confidential", "education_records"},
            "humanApprovalRequired": approval_required,
            "policyActivationAllowed": False,
        },
        "auditPlan": {
            "auditRequired": True,
            "auditEvents": [
                "organization_created",
                "user_invited",
                "role_granted",
                "sso_configured",
                "directory_synced",
                "class_space_created",
                "deployment_approved",
            ],
            "retention": "enterprise_policy" if normalized_edition == "enterprise" else "default_local_policy",
            "willExportAudit": False,
        },
        "readinessChecks": [
            {"id": "role_catalog", "status": "complete", "required": True},
            {"id": "edition_policy", "status": "complete", "required": True},
            {"id": "sso_provider", "status": "planned" if sso_required else "optional", "required": sso_required},
            {"id": "directory_sync", "status": "planned" if directory_sync_required else "optional", "required": directory_sync_required},
            {"id": "human_approval", "status": "blocked", "required": approval_required},
        ],
        "blockedActions": [
            {
                "id": "organization_write",
                "reason": "Le planner ne cree aucune organisation ni workspace.",
            },
            {
                "id": "role_grant",
                "reason": "Aucun role ou permission n'est attribue sans workflow admin dedie.",
            },
            {
                "id": "sso_secret_access",
                "reason": "Aucun secret OIDC/SAML n'est lu ou ecrit dans ce planner.",
            },
            {
                "id": "directory_sync",
                "reason": "Aucune synchronisation Microsoft/Google/LDAP n'est lancee en dry-run.",
            },
            {
                "id": "classroom_write",
                "reason": "Les espaces classe restent planifies jusqu'a validation humaine.",
            },
        ],
        "warnings": warnings,
        "reason": "Plan de gouvernance CogniX prepare sans mutation d'organisation, SSO, roles ou classes.",
        "sideEffects": {
            "organizationWrite": False,
            "userInvite": False,
            "roleGrant": False,
            "permissionWrite": False,
            "ssoMutation": False,
            "secretRead": False,
            "secretWrite": False,
            "directorySync": False,
            "networkCall": False,
            "auditExport": False,
            "classroomWrite": False,
            "policyActivation": False,
        },
    }
