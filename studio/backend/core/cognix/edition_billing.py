# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native edition, entitlement, workspace, and billing policy.

This module formalizes product editions and billing-related guardrails without
calling a payment processor or changing real subscriptions. Mutating billing
actions are planned, audited, and require explicit approval.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_PLAN_CATALOG_VERSION = "cognix_plan_catalog_v1"
COGNIX_ENTITLEMENT_POLICY_ENGINE_VERSION = "cognix_entitlement_policy_engine_v1"
COGNIX_BILLING_EVENT_LEDGER_VERSION = "cognix_billing_event_ledger_v1"
COGNIX_WORKSPACE_PROVISIONING_PLANNER_VERSION = "cognix_workspace_provisioning_planner_v1"
COGNIX_BILLING_APPROVAL_GATE_VERSION = "cognix_billing_approval_gate_v1"

EDITION_BILLING_SERVICES = [
    "PlanCatalogService",
    "EntitlementPolicyEngine",
    "BillingEventLedger",
    "WorkspaceProvisioningPlanner",
    "BillingApprovalGate",
]

EDITION_BILLING_TABLES = [
    "cognix_workspaces",
    "cognix_organizations",
    "cognix_plans",
    "cognix_billing_events",
]

BILLING_MUTATION_EVENTS = {
    "plan_change",
    "payment_method_change",
    "invoice_charge",
    "refund",
    "cancel_subscription",
    "reactivate_subscription",
}

PLAN_CATALOG: list[dict[str, Any]] = [
    {
        "planKey": "free",
        "displayName": "CogniX Free",
        "editionTarget": "free",
        "monthlyPriceCents": 0,
        "allowedModules": [
            "cognix-local-core",
            "cognix-pulse",
            "cognix-library",
            "cognix-apps",
            "cognix-command-palette",
        ],
        "limits": {"dailyTokens": 20000, "projects": 3, "cloudRequests": 0, "coworkSessions": 0},
        "features": ["local_chat", "model_hub_basic", "basic_projects", "local_rag"],
        "cloudAllowed": False,
        "enterpriseControls": False,
    },
    {
        "planKey": "local",
        "displayName": "CogniX Local",
        "editionTarget": "local",
        "monthlyPriceCents": 0,
        "allowedModules": [
            "cognix-local-core",
            "cognix-pulse",
            "cognix-library",
            "cognix-apps",
            "cognix-command-palette",
            "cognix-fine-tuning",
            "cognix-shared-knowledge-base",
        ],
        "limits": {"dailyTokens": 50000, "projects": 10, "cloudRequests": 0, "coworkSessions": 1},
        "features": ["offline_first", "local_models", "guided_training", "project_memory"],
        "cloudAllowed": False,
        "enterpriseControls": False,
    },
    {
        "planKey": "developer",
        "displayName": "CogniX Developer Pro",
        "editionTarget": "developer",
        "monthlyPriceCents": 1900,
        "allowedModules": [
            "cognix-local-core",
            "cognix-model-lifecycle",
            "cognix-fine-tuning",
            "cognix-codex-secure-agent",
            "cognix-agent-mode",
            "cognix-cowork-mode",
            "cognix-ai-evolution-engine",
            "cognix-plugin-marketplace",
        ],
        "limits": {"dailyTokens": 200000, "projects": 50, "cloudRequests": 1000, "coworkSessions": 10},
        "features": ["developer_tools", "codex_pipeline", "benchmarks", "plugin_system"],
        "cloudAllowed": True,
        "enterpriseControls": False,
    },
    {
        "planKey": "business",
        "displayName": "CogniX Business",
        "editionTarget": "business",
        "monthlyPriceCents": 4900,
        "allowedModules": [
            "cognix-local-core",
            "cognix-admin-operations",
            "cognix-admin-security-center",
            "cognix-admin-organization-settings",
            "cognix-shared-knowledge-base",
            "cognix-chat-project-bridge",
            "cognix-enterprise-encrypted-chat",
        ],
        "limits": {"dailyTokens": 1000000, "projects": 250, "cloudRequests": 10000, "coworkSessions": 25},
        "features": ["organizations", "rbac", "audit_logs", "business_connectors"],
        "cloudAllowed": True,
        "enterpriseControls": True,
    },
    {
        "planKey": "university",
        "displayName": "CogniX University",
        "editionTarget": "university",
        "monthlyPriceCents": 3900,
        "allowedModules": [
            "cognix-local-core",
            "cognix-education-spaces",
            "cognix-shared-knowledge-base",
            "cognix-admin-operations",
            "cognix-admin-data-retention-privacy",
            "cognix-enterprise-encrypted-chat",
        ],
        "limits": {"dailyTokens": 1500000, "projects": 500, "cloudRequests": 15000, "coworkSessions": 25},
        "features": ["classes", "courses", "exam_guard", "teacher_student_permissions"],
        "cloudAllowed": True,
        "enterpriseControls": True,
    },
    {
        "planKey": "enterprise",
        "displayName": "CogniX Enterprise",
        "editionTarget": "enterprise",
        "monthlyPriceCents": 0,
        "allowedModules": ["*"],
        "limits": {"dailyTokens": -1, "projects": -1, "cloudRequests": -1, "coworkSessions": -1},
        "features": ["on_premise", "multi_server", "sso", "secure_model_registry", "local_only_mode"],
        "cloudAllowed": True,
        "enterpriseControls": True,
    },
    {
        "planKey": "CEO",
        "displayName": "CogniX CEO",
        "editionTarget": "enterprise",
        "monthlyPriceCents": 0,
        "allowedModules": ["*"],
        "limits": {"dailyTokens": -1, "projects": -1, "cloudRequests": -1, "coworkSessions": -1},
        "features": ["all_modules", "cloud_training_unlocked", "owner_override", "full_development_mode"],
        "cloudAllowed": True,
        "enterpriseControls": True,
    },
]


def _text(value: Any, limit: int = 240, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).replace("\r\n", "\n").strip()
    return " ".join(text.split())[:limit].strip()


def _key(value: Any, fallback: str = "") -> str:
    text = _text(value, 160, fallback)
    if text == "CEO":
        return "CEO"
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in text.lower())
    return cleaned.strip("_")[:120] or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:14]}"


def _plan_by_key() -> dict[str, dict[str, Any]]:
    return {str(item["planKey"]): dict(item) for item in PLAN_CATALOG}


def _normalize_plan_key(plan_key: str | None) -> str:
    key = _key(plan_key, "free")
    return key if key in _plan_by_key() else "free"


def build_edition_billing_blueprint() -> dict[str, Any]:
    return {
        "planCatalogVersion": COGNIX_PLAN_CATALOG_VERSION,
        "entitlementPolicyEngineVersion": COGNIX_ENTITLEMENT_POLICY_ENGINE_VERSION,
        "billingEventLedgerVersion": COGNIX_BILLING_EVENT_LEDGER_VERSION,
        "workspaceProvisioningPlannerVersion": COGNIX_WORKSPACE_PROVISIONING_PLANNER_VERSION,
        "billingApprovalGateVersion": COGNIX_BILLING_APPROVAL_GATE_VERSION,
        "mode": "native_edition_billing_policy_contract",
        "services": EDITION_BILLING_SERVICES,
        "tables": EDITION_BILLING_TABLES,
        "plans": [item["planKey"] for item in PLAN_CATALOG],
        "security": {
            "billingMutationRequiresApproval": True,
            "paymentProcessorCallsForbiddenHere": True,
            "entitlementsResolvedServerSide": True,
            "auditEveryBillingEvent": True,
            "frontendPlanOverrideAllowed": False,
        },
        "sideEffects": {
            "databaseWrite": False,
            "planWrite": False,
            "workspaceWrite": False,
            "organizationWrite": False,
            "billingEventWrite": False,
            "auditWrite": False,
            "billingMutation": False,
            "paymentProcessorCall": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_plan_catalog() -> dict[str, Any]:
    return {
        "planCatalogVersion": COGNIX_PLAN_CATALOG_VERSION,
        "mode": "native_plan_catalog",
        "plans": [dict(item) for item in PLAN_CATALOG],
        "summary": {
            "planCount": len(PLAN_CATALOG),
            "paidPlanCount": sum(1 for item in PLAN_CATALOG if int(item.get("monthlyPriceCents") or 0) > 0),
            "enterprisePlanKeys": [
                item["planKey"]
                for item in PLAN_CATALOG
                if item.get("enterpriseControls")
            ],
        },
        "sideEffects": build_edition_billing_blueprint()["sideEffects"],
    }


def build_entitlement_decision(
    *,
    plan_key: str | None,
    role: str = "user",
    module_id: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    normalized_plan = _normalize_plan_key(plan_key)
    plan = _plan_by_key()[normalized_plan]
    module = _text(module_id, 160)
    allowed_modules = set(plan.get("allowedModules") or [])
    module_allowed = not module or "*" in allowed_modules or module in allowed_modules
    role_key = _key(role, "user")
    action_key = _key(action, "read")
    blocked_reasons: list[str] = []
    if module and not module_allowed:
        blocked_reasons.append("module_not_in_plan")
    if action_key in {"admin", "billing", "security_admin"} and role_key not in {"admin", "owner", "ceo"}:
        blocked_reasons.append("role_does_not_allow_admin_action")
    if action_key in {"cloud_generation", "cloud_training"} and not plan.get("cloudAllowed"):
        blocked_reasons.append("cloud_not_allowed_by_plan")
    return {
        "entitlementPolicyEngineVersion": COGNIX_ENTITLEMENT_POLICY_ENGINE_VERSION,
        "mode": "native_entitlement_decision",
        "plan": plan,
        "role": role_key,
        "moduleId": module or None,
        "action": action_key,
        "allowed": not blocked_reasons,
        "blockedReasons": blocked_reasons,
        "limits": plan.get("limits") or {},
        "features": plan.get("features") or [],
        "sideEffects": build_edition_billing_blueprint()["sideEffects"],
    }


def build_billing_event_plan(
    *,
    actor_username: str,
    event_type: str,
    plan_key: str | None = None,
    amount_cents: int | None = None,
    currency: str = "USD",
    reason: str | None = None,
    approval_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = _key(event_type, "usage_metered")
    plan = _normalize_plan_key(plan_key)
    mutating = event in BILLING_MUTATION_EVENTS
    approval = _text(approval_id, 160)
    amount = max(0, int(amount_cents or 0))
    risk_level = "high" if mutating or amount > 0 else "low"
    blocked_reasons = []
    approval_reasons = []
    if mutating and not approval:
        approval_reasons.append("billing_mutation_requires_human_approval")
    return {
        "billingEventLedgerVersion": COGNIX_BILLING_EVENT_LEDGER_VERSION,
        "billingApprovalGateVersion": COGNIX_BILLING_APPROVAL_GATE_VERSION,
        "mode": "native_billing_event_plan",
        "billingEventPlanId": _stable_id("billplan", actor_username, event, plan, amount, reason),
        "event": {
            "actorUsername": _text(actor_username, 160),
            "eventType": event,
            "planKey": plan,
            "amountCents": amount,
            "currency": _text(currency, 12, "USD").upper(),
            "reason": _text(reason, 1000),
            "approvalId": approval or None,
            "metadata": _as_dict(metadata),
            "riskLevel": risk_level,
            "requiresApproval": bool(approval_reasons),
            "blockedReasons": blocked_reasons,
            "approvalReasons": approval_reasons,
            "willMutateBillingNow": False,
        },
        "sideEffects": build_edition_billing_blueprint()["sideEffects"],
    }


def build_workspace_provisioning_plan(
    *,
    organization_name: str,
    workspace_name: str,
    plan_key: str | None,
    owner_username: str,
    organization_type: str = "business",
) -> dict[str, Any]:
    plan = _normalize_plan_key(plan_key)
    entitlement = build_entitlement_decision(plan_key = plan, role = "owner")
    return {
        "workspaceProvisioningPlannerVersion": COGNIX_WORKSPACE_PROVISIONING_PLANNER_VERSION,
        "entitlementPolicyEngineVersion": COGNIX_ENTITLEMENT_POLICY_ENGINE_VERSION,
        "mode": "native_workspace_provisioning_plan",
        "provisioningPlanId": _stable_id("workspace_plan", organization_name, workspace_name, plan, owner_username),
        "organization": {
            "name": _text(organization_name, 240, "CogniX Organization"),
            "organizationType": _key(organization_type, "business"),
            "ownerUsername": _text(owner_username, 160),
            "planKey": plan,
        },
        "workspace": {
            "name": _text(workspace_name, 240, "Main Workspace"),
            "ownerUsername": _text(owner_username, 160),
            "planKey": plan,
        },
        "entitlements": entitlement,
        "sideEffects": build_edition_billing_blueprint()["sideEffects"],
    }
