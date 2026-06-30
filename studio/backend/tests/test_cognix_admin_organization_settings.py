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
from core.cognix import admin_organization_settings as cognix_admin_organization_settings
from core.cognix import api_surface as cognix_api_surface
from core.cognix import module_registry as cognix_module_registry
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
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False


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


def test_admin_organization_settings_blueprint_schema_and_surface_contract():
    blueprint = cognix_admin_organization_settings.build_organization_settings_blueprint()
    assert blueprint["organizationPolicyServiceVersion"] == "cognix_organization_policy_service_v1"
    assert blueprint["services"] == ["OrganizationPolicyService", "PolicyEnforcer", "AdminSettingsService"]
    assert "organization_policies" in blueprint["tables"]
    assert "organization_settings" in blueprint["tables"]
    assert "policy_change_logs" in blueprint["tables"]
    assert blueprint["security"]["permissionEngineIntegration"] is True
    assert blueprint["sideEffects"]["policyWrite"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_global_roadmap_tables(conn)
        cognix_db._ensure_admin_organization_settings_columns(conn)
        policy_columns = {row[1] for row in conn.execute("PRAGMA table_info(organization_policies)").fetchall()}
        settings_columns = {row[1] for row in conn.execute("PRAGMA table_info(organization_settings)").fetchall()}
        log_columns = {row[1] for row in conn.execute("PRAGMA table_info(policy_change_logs)").fetchall()}
        assert {"policy_key", "policy_value_json", "permission_key", "allowed", "updated_by"}.issubset(
            policy_columns
        )
        assert {"setting_key", "setting_value_json", "updated_by"}.issubset(settings_columns)
        assert {"changed_by", "changed_keys_json", "before_json", "after_json"}.issubset(log_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    assert "cognix-admin-organization-settings" in modules
    assert "/api/cognix/admin/settings/enforcement-plan" in modules["cognix-admin-organization-settings"]["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/settings", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/settings"]["status"] == "equivalent"
    assert routes["/admin/settings"]["matchedRoute"] == "/api/cognix/admin/settings"


def test_admin_organization_settings_routes_update_policy_enforce_and_feed_permissions():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_settings_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    updated = run_async(
        cognix_routes.admin_update_settings(
            cognix_routes.AdminOrganizationSettingsRequest(
                cloudAllowed = False,
                externalModelsAllowed = False,
                allowedModels = ["local-qwen"],
                allowedApps = ["github"],
                defaultPermissions = ["tools:execute"],
                approvalRequired = True,
                reason = "Local-first policy",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert updated["sideEffects"]["policyWrite"] is True
    assert updated["sideEffects"]["settingsWrite"] is True
    assert updated["organizationSettings"]["settings"]["cloudAllowed"] is False
    assert "tools:execute" in {
        policy.get("permissionKey") for policy in updated["policies"]
    }
    assert updated["policyChangeLog"]["changedKeys"]

    settings = run_async(cognix_routes.admin_settings(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert settings["organizationSettings"]["summary"]["cloudAllowed"] is False
    assert settings["organizationSettings"]["summary"]["defaultPermissionCount"] == 1

    denied = run_async(
        cognix_routes.admin_settings_enforcement_plan(
            cognix_routes.AdminPolicyEnforcementRequest(
                actionType = "model",
                modelId = "gpt-4o",
                provider = "openai",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert denied["enforcementPlan"]["allowed"] is False
    assert "cloud_disabled_by_organization_policy" in denied["enforcementPlan"]["reasons"]
    assert denied["sideEffects"]["modelLoad"] is False

    permission = run_async(
        cognix_routes.admin_permission_decision(
            cognix_routes.AdminPermissionDecisionRequest(
                username = "alice",
                permissionKey = "tools:execute",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert permission["decision"]["allowed"] is True
    assert permission["decision"]["source"] == "organization_policy"

    logs = run_async(cognix_routes.admin_settings_change_logs(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert logs["changeLogs"][0]["changedBy"] == auth_storage.DEFAULT_ADMIN_USERNAME
