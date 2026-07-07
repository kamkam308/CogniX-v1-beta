from __future__ import annotations

import asyncio
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage as auth_storage
from core.cognix import api_surface as cognix_api_surface
from core.cognix import edition_billing as cognix_edition_billing
from core.cognix import module_registry as cognix_module_registry
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(tmp_path / "project_workspaces"))
    monkeypatch.setattr(auth_storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth_storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(auth_storage, "_bootstrap_password", None)
    monkeypatch.setattr(auth_storage, "_api_key_pbkdf2_salt_cache", None)
    monkeypatch.setattr(cognix_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()


def run_async(coro):
    return asyncio.run(coro)


def seed_accounts() -> None:
    auth_storage.create_initial_user(
        username = auth_storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    auth_storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )


def test_edition_billing_blueprint_schema_registry_and_surface_contract():
    blueprint = cognix_edition_billing.build_edition_billing_blueprint()
    assert blueprint["planCatalogVersion"] == "cognix_plan_catalog_v1"
    assert blueprint["entitlementPolicyEngineVersion"] == "cognix_entitlement_policy_engine_v1"
    assert blueprint["billingEventLedgerVersion"] == "cognix_billing_event_ledger_v1"
    assert blueprint["services"] == [
        "PlanCatalogService",
        "EntitlementPolicyEngine",
        "BillingEventLedger",
        "WorkspaceProvisioningPlanner",
        "BillingApprovalGate",
    ]
    assert {
        "cognix_workspaces",
        "cognix_organizations",
        "cognix_plans",
        "cognix_billing_events",
    }.issubset(set(blueprint["tables"]))
    assert blueprint["security"]["billingMutationRequiresApproval"] is True
    assert blueprint["sideEffects"]["paymentProcessorCall"] is False
    assert blueprint["sideEffects"]["billingMutation"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_edition_billing_columns(conn)
        plan_columns = {row[1] for row in conn.execute("PRAGMA table_info(cognix_plans)").fetchall()}
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(cognix_billing_events)").fetchall()}
        workspace_columns = {row[1] for row in conn.execute("PRAGMA table_info(cognix_workspaces)").fetchall()}
        organization_columns = {row[1] for row in conn.execute("PRAGMA table_info(cognix_organizations)").fetchall()}
        assert {"plan_key", "allowed_modules_json", "limits_json", "cloud_allowed"}.issubset(plan_columns)
        assert {"event_type", "approval_required", "event_json", "status"}.issubset(event_columns)
        assert {"organization_id", "owner_username", "plan_key"}.issubset(workspace_columns)
        assert {"organization_type", "owner_username", "plan_key"}.issubset(organization_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    edition = modules["cognix-edition-billing-policy"]
    assert "plan_catalog_service" in edition["capabilities"]
    assert "billing_mutation_approval_required" in edition["capabilities"]
    assert "/api/cognix/admin/billing/events/plan" in edition["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/editions/plans", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/editions"]["status"] == "equivalent"
    assert routes["/editions"]["matchedRoute"] == "/api/cognix/editions/plans"


def test_edition_routes_sync_entitlements_workspace_and_billing_guardrails():
    seed_accounts()
    admin = auth_storage.DEFAULT_ADMIN_USERNAME

    plans_response = run_async(cognix_routes.edition_plans(current_subject = "alice"))
    plan_keys = {item["planKey"] for item in plans_response["planCatalog"]["plans"]}
    assert {"free", "developer", "business", "university", "enterprise", "CEO"}.issubset(plan_keys)
    assert plans_response["sideEffects"]["planWrite"] is True

    allowed = run_async(
        cognix_routes.edition_entitlement_decision(
            cognix_routes.EntitlementDecisionRequest(
                planKey = "developer",
                role = "owner",
                moduleId = "cognix-codex-secure-agent",
                action = "read",
            ),
            current_subject = "alice",
        )
    )
    assert allowed["entitlementDecision"]["allowed"] is True
    assert allowed["entitlementDecision"]["sideEffects"]["billingMutation"] is False

    blocked = run_async(
        cognix_routes.edition_entitlement_decision(
            cognix_routes.EntitlementDecisionRequest(
                planKey = "free",
                role = "user",
                moduleId = "cognix-enterprise-secure-model-registry",
                action = "cloud_generation",
            ),
            current_subject = "alice",
        )
    )
    assert blocked["entitlementDecision"]["allowed"] is False
    assert "module_not_in_plan" in blocked["entitlementDecision"]["blockedReasons"]
    assert "cloud_not_allowed_by_plan" in blocked["entitlementDecision"]["blockedReasons"]

    with pytest.raises(HTTPException) as non_admin_billing:
        run_async(
            cognix_routes.admin_billing_event_plan(
                cognix_routes.BillingEventPlanRequest(eventType = "plan_change", planKey = "business"),
                current_subject = "alice",
            )
        )
    assert non_admin_billing.value.status_code == 403

    workspace_response = run_async(
        cognix_routes.admin_workspace_provision_plan(
            cognix_routes.WorkspaceProvisioningPlanRequest(
                organizationName = "EBK University",
                workspaceName = "Physics Department",
                organizationType = "university",
                planKey = "university",
            ),
            current_subject = admin,
        )
    )
    assert workspace_response["sideEffects"]["workspaceWrite"] is True
    assert workspace_response["sideEffects"]["organizationWrite"] is True
    assert workspace_response["workspaceProvisioningPlan"]["entitlements"]["allowed"] is True
    assert workspace_response["stored"]["organization"]["planKey"] == "university"

    billing_response = run_async(
        cognix_routes.admin_billing_event_plan(
            cognix_routes.BillingEventPlanRequest(
                eventType = "plan_change",
                planKey = "business",
                amountCents = 4900,
                reason = "Upgrade requested by admin",
            ),
            current_subject = admin,
        )
    )
    assert billing_response["requiresApproval"] is True
    assert billing_response["billingEventPlan"]["event"]["willMutateBillingNow"] is False
    assert billing_response["sideEffects"]["paymentProcessorCall"] is False
    assert billing_response["billingEvent"]["status"] == "planned_no_payment_mutation"

    events = run_async(cognix_routes.admin_billing_events(current_subject = admin))
    assert len(events["billingEvents"]) == 1
    assert events["billingEvents"][0]["approvalRequired"] is True

    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert "workspace_provisioning_planned" in audit_actions
    assert "billing_event_planned" in audit_actions
