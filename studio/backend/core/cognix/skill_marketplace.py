# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX internal skill marketplace contracts.

The internal marketplace shares organization-approved skills. It plans,
validates, versions, and gates usage; it never executes arbitrary code, reads
secrets, calls models, or activates a skill without storage/admin state.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION = "cognix_skill_marketplace_service_v1"
COGNIX_SKILL_APPROVAL_SERVICE_VERSION = "cognix_skill_approval_service_v1"
COGNIX_SKILL_VERSION_MANAGER_VERSION = "cognix_skill_version_manager_v1"

SKILL_CATEGORIES = ["hr", "support", "legal", "education", "code", "operations", "research"]
SKILL_STATUSES = {"draft", "pending_approval", "approved", "denied", "disabled"}
SKILL_ACTIONS = {"view", "use", "share", "version", "disable"}
DEFAULT_ORGANIZATION_ID = "local"

BUILTIN_INTERNAL_SKILLS: list[dict[str, Any]] = [
    {
        "skillKey": "hr-policy-helper",
        "displayName": "Skill RH",
        "category": "hr",
        "description": "Prepare des reponses RH a partir de politiques internes validees.",
        "version": "1.0.0",
        "publisher": "CogniX Internal",
        "allowedRoles": ["admin", "ceo", "hr"],
        "instructions": "Verifier la politique interne avant toute reponse RH.",
    },
    {
        "skillKey": "support-client-playbook",
        "displayName": "Skill support client",
        "category": "support",
        "description": "Structure les reponses support avec diagnostic, solution et escalade.",
        "version": "1.0.0",
        "publisher": "CogniX Internal",
        "allowedRoles": ["admin", "support", "ceo"],
        "instructions": "Toujours separer faits verifies, hypothese et prochaine action.",
    },
    {
        "skillKey": "legal-review-assistant",
        "displayName": "Skill juridique interne",
        "category": "legal",
        "description": "Aide a preparer une revue juridique sans donner d'avis legal final.",
        "version": "1.0.0",
        "publisher": "CogniX Internal",
        "allowedRoles": ["admin", "legal", "ceo"],
        "instructions": "Identifier clauses, risques et questions a valider par un juriste.",
    },
    {
        "skillKey": "exam-correction-rubric",
        "displayName": "Skill correction examens",
        "category": "education",
        "description": "Applique une grille de correction et signale les points ambigus.",
        "version": "1.0.0",
        "publisher": "CogniX Internal",
        "allowedRoles": ["admin", "teacher", "ceo"],
        "instructions": "Corriger selon bareme explicite et conserver la justification.",
    },
    {
        "skillKey": "code-audit-review",
        "displayName": "Skill audit code",
        "category": "code",
        "description": "Priorise bugs, regressions, securite et tests manquants.",
        "version": "1.0.0",
        "publisher": "CogniX Internal",
        "allowedRoles": ["admin", "developer", "ceo"],
        "instructions": "Presenter d'abord les risques avec references fichier/ligne.",
    },
]


def _safe_key(value: Any, fallback: str = "internal-skill") -> str:
    text = str(value or fallback).strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return cleaned[:120].strip("-") or fallback


def _safe_text(value: Any, limit: int, fallback: str = "") -> str:
    return " ".join(str(value or fallback).replace("\r\n", "\n").split()).strip()[:limit]


def _normalize_roles(roles: Any) -> list[str]:
    if not isinstance(roles, list):
        return ["admin"]
    normalized = [_safe_key(role, "user") for role in roles if str(role or "").strip()]
    return list(dict.fromkeys(normalized))[:20] or ["admin"]


def _normalize_category(value: Any) -> str:
    category = _safe_key(value, "operations")
    return category if category in SKILL_CATEGORIES else "operations"


def _skill_hash(manifest: dict[str, Any]) -> str:
    source = "|".join(
        str(manifest.get(key) or "")
        for key in ("skillKey", "displayName", "version", "publisher", "instructions")
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def normalize_skill_manifest(skill_manifest: dict[str, Any] | None) -> dict[str, Any]:
    manifest = deepcopy(skill_manifest) if isinstance(skill_manifest, dict) else {}
    display_name = _safe_text(manifest.get("displayName") or manifest.get("name"), 160, "Internal Skill")
    skill_key = _safe_key(manifest.get("skillKey") or manifest.get("id") or display_name)
    normalized = {
        "schemaVersion": "cognix_internal_skill_manifest_v1",
        "skillKey": skill_key,
        "displayName": display_name,
        "category": _normalize_category(manifest.get("category")),
        "description": _safe_text(manifest.get("description"), 600),
        "version": _safe_text(manifest.get("version"), 80, "1.0.0"),
        "publisher": _safe_text(manifest.get("publisher"), 160, "CogniX Internal"),
        "allowedRoles": _normalize_roles(manifest.get("allowedRoles")),
        "instructions": _safe_text(manifest.get("instructions") or manifest.get("prompt"), 4000),
        "tags": [
            _safe_key(item, "tag")
            for item in (manifest.get("tags") if isinstance(manifest.get("tags"), list) else [])
            if str(item or "").strip()
        ][:20],
    }
    normalized["manifestHash"] = _skill_hash(normalized)
    return normalized


def validate_skill_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    for field in ("skillKey", "displayName", "category", "version", "allowedRoles", "instructions"):
        value = manifest.get(field)
        if value in (None, "", []):
            missing.append(field)
    valid = not missing
    return {
        "schemaVersion": "cognix_internal_skill_validation_v1",
        "valid": valid,
        "missingFields": missing,
        "requiresAdminApproval": True,
        "blockingReasons": [] if valid else ["missing_required_fields"],
    }


def build_skill_marketplace_blueprint() -> dict[str, Any]:
    return {
        "skillMarketplaceVersion": COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
        "skillApprovalVersion": COGNIX_SKILL_APPROVAL_SERVICE_VERSION,
        "skillVersionManagerVersion": COGNIX_SKILL_VERSION_MANAGER_VERSION,
        "services": [
            "SkillMarketplaceService",
            "SkillApprovalService",
            "SkillVersionManager",
        ],
        "tables": ["shared_skills", "skill_approvals", "skill_usage_logs"],
        "categories": SKILL_CATEGORIES,
        "adminControls": {
            "approveSkill": True,
            "limitToRoles": True,
            "viewUsage": True,
            "disableSkill": True,
            "versionSkill": True,
        },
        "policies": {
            "organizationScoped": True,
            "adminApprovalRequired": True,
            "roleLimitsRequired": True,
            "usageAudited": True,
            "frontendCannotActivateUnapprovedSkill": True,
            "skillInstructionsStayServerSideUntilApproved": True,
        },
        "sideEffects": {
            "skillExecution": False,
            "approvalWrite": False,
            "skillWrite": False,
            "usageLogWrite": False,
            "permissionGrant": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "secretRead": False,
        },
    }


def build_builtin_catalog() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for item in BUILTIN_INTERNAL_SKILLS:
        manifest = normalize_skill_manifest(item)
        skills.append(
            {
                "id": f"builtin_{manifest['skillKey']}",
                "organizationId": DEFAULT_ORGANIZATION_ID,
                "skillKey": manifest["skillKey"],
                "displayName": manifest["displayName"],
                "category": manifest["category"],
                "description": manifest["description"],
                "currentVersion": manifest["version"],
                "status": "approved",
                "allowedRoles": manifest["allowedRoles"],
                "manifestHash": manifest["manifestHash"],
                "source": "builtin",
            }
        )
    return skills


def build_marketplace_catalog(
    *,
    shared_skills: list[dict[str, Any]] | None = None,
    approvals: list[dict[str, Any]] | None = None,
    usage_logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stored = shared_skills or []
    skills = build_builtin_catalog() + stored
    return {
        "skillMarketplaceVersion": COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
        "mode": "internal_skill_catalog",
        "categories": SKILL_CATEGORIES,
        "skills": skills,
        "approvals": approvals or [],
        "usageLogs": usage_logs or [],
        "summary": {
            "skillCount": len(skills),
            "approvedCount": sum(1 for item in skills if item.get("status") == "approved"),
            "pendingApprovalCount": sum(1 for item in skills if item.get("status") == "pending_approval"),
            "disabledCount": sum(1 for item in skills if item.get("status") == "disabled"),
            "usageLogCount": len(usage_logs or []),
        },
        "sideEffects": build_skill_marketplace_blueprint()["sideEffects"],
    }


def build_skill_publish_plan(
    *,
    username: str,
    skill_manifest: dict[str, Any] | None,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    is_admin: bool = False,
) -> dict[str, Any]:
    manifest = normalize_skill_manifest(skill_manifest)
    validation = validate_skill_manifest(manifest)
    status = "approved" if is_admin and validation["valid"] else "pending_approval"
    if not validation["valid"]:
        status = "draft"
    return {
        "skillMarketplaceVersion": COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
        "skillApprovalVersion": COGNIX_SKILL_APPROVAL_SERVICE_VERSION,
        "skillVersionManagerVersion": COGNIX_SKILL_VERSION_MANAGER_VERSION,
        "mode": "internal_skill_publish_plan",
        "username": username,
        "organizationId": _safe_key(organization_id, DEFAULT_ORGANIZATION_ID),
        "status": status,
        "skill": {
            "skillKey": manifest["skillKey"],
            "displayName": manifest["displayName"],
            "category": manifest["category"],
            "currentVersion": manifest["version"],
            "allowedRoles": manifest["allowedRoles"],
            "manifestHash": manifest["manifestHash"],
        },
        "manifest": manifest,
        "validation": validation,
        "approvalPlan": {
            "required": True,
            "autoApprovedByAdmin": bool(is_admin and validation["valid"]),
            "status": "approved" if is_admin and validation["valid"] else "pending",
            "requestType": "internal_skill_approval",
        },
        "versionPlan": {
            "currentVersion": manifest["version"],
            "versionHistoryAppend": True,
            "versionManagerVersion": COGNIX_SKILL_VERSION_MANAGER_VERSION,
        },
        "sideEffects": build_skill_marketplace_blueprint()["sideEffects"],
    }


def build_skill_approval_plan(
    *,
    skill: dict[str, Any],
    reviewer_username: str,
    status: str,
    admin_note: str | None = None,
) -> dict[str, Any]:
    normalized_status = status if status in {"approved", "denied", "disabled"} else "denied"
    return {
        "skillApprovalVersion": COGNIX_SKILL_APPROVAL_SERVICE_VERSION,
        "mode": "internal_skill_approval_decision",
        "skillId": skill.get("id"),
        "skillKey": skill.get("skillKey") or skill.get("skill_key"),
        "reviewerUsername": reviewer_username,
        "status": normalized_status,
        "adminNote": _safe_text(admin_note, 1200),
        "willEnableUsage": normalized_status == "approved",
        "willDisableUsage": normalized_status in {"denied", "disabled"},
        "sideEffects": build_skill_marketplace_blueprint()["sideEffects"],
    }


def build_skill_usage_plan(
    *,
    username: str,
    skill: dict[str, Any],
    action: str,
    user_role: str | None = None,
) -> dict[str, Any]:
    normalized_action = action if action in SKILL_ACTIONS else "use"
    allowed_roles = skill.get("allowedRoles") or skill.get("allowed_roles") or []
    role = _safe_key(user_role or "user", "user")
    status = str(skill.get("status") or "disabled")
    role_allowed = "admin" in allowed_roles or role in allowed_roles or role == "admin"
    allowed = status == "approved" and role_allowed
    return {
        "skillMarketplaceVersion": COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
        "mode": "internal_skill_usage_gate",
        "username": username,
        "skillId": skill.get("id"),
        "skillKey": skill.get("skillKey") or skill.get("skill_key"),
        "action": normalized_action,
        "allowed": allowed,
        "blockedReasons": [
            reason
            for reason, blocked in {
                "skill_not_approved": status != "approved",
                "role_not_allowed": not role_allowed,
            }.items()
            if blocked
        ],
        "usageLogRequired": allowed,
        "sideEffects": build_skill_marketplace_blueprint()["sideEffects"],
    }
