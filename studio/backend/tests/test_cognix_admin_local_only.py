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
from core.cognix import admin_local_only as cognix_admin_local_only
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


def test_local_only_blueprint_schema_module_registry_and_surface_contract():
    blueprint = cognix_admin_local_only.build_local_only_blueprint()
    assert blueprint["localOnlyPolicyEngineVersion"] == "cognix_local_only_policy_engine_v1"
    assert blueprint["networkEgressGuardVersion"] == "cognix_network_egress_guard_v1"
    assert blueprint["providerBlockerVersion"] == "cognix_provider_blocker_v1"
    assert blueprint["services"] == ["LocalOnlyPolicyEngine", "NetworkEgressGuard", "ProviderBlocker"]
    assert {"local_only_policies", "blocked_external_calls"}.issubset(set(blueprint["tables"]))
    assert "no_cloud_calls" in blueprint["rules"]
    assert blueprint["sideEffects"]["networkCall"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_admin_local_only_columns(conn)
        policy_columns = {row[1] for row in conn.execute("PRAGMA table_info(local_only_policies)").fetchall()}
        blocked_columns = {row[1] for row in conn.execute("PRAGMA table_info(blocked_external_calls)").fetchall()}
        assert {"policy_key", "enabled", "allowed_hosts_json", "allowed_providers_json", "policy_json"}.issubset(
            policy_columns
        )
        assert {"actor_username", "provider", "model_id", "url", "reason", "decision_json"}.issubset(
            blocked_columns
        )
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    local_only = modules["cognix-enterprise-local-only-mode"]
    assert "local_only_policy_engine" in local_only["capabilities"]
    assert "network_egress_guard" in local_only["capabilities"]
    assert "/api/cognix/admin/local-only/egress-decision" in local_only["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/local-only", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/settings"]["status"] == "equivalent"
    assert routes["/admin/settings"]["matchedRoute"] == "/api/cognix/admin/local-only"


def test_local_only_routes_policy_settings_blocking_and_allowed_localhost():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_local_only_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    updated = run_async(
        cognix_routes.admin_update_local_only_policy(
            cognix_routes.AdminLocalOnlyPolicyRequest(
                enabled = True,
                allowedHosts = ["127.0.0.1", "localhost", "cognix.local"],
                allowedProviders = ["local", "ollama", "local_gguf"],
                reason = "Enterprise on-premise policy",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert updated["policy"]["enabled"] is True
    assert updated["enforcementPlan"]["badge"]["active"] is True
    assert updated["sideEffects"]["policyWrite"] is True
    assert updated["sideEffects"]["organizationSettingsWrite"] is True

    settings = run_async(cognix_routes.admin_settings(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert settings["settings"]["cloudAllowed"] is False
    assert settings["settings"]["externalModelsAllowed"] is False

    blocked = run_async(
        cognix_routes.admin_local_only_egress_decision(
            cognix_routes.AdminLocalOnlyDecisionRequest(
                provider = "openai",
                modelId = "gpt-4o",
                url = "https://api.openai.com/v1/chat/completions",
                actionType = "model",
                metadata = {"source": "pytest"},
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert blocked["decision"]["allowed"] is False
    assert "cloud_provider_blocked_by_local_only_policy" in blocked["decision"]["reasons"]
    assert "external_network_egress_blocked_by_local_only_policy" in blocked["decision"]["reasons"]
    assert blocked["sideEffects"]["blockedCallWrite"] is True
    assert blocked["sideEffects"]["networkCall"] is False

    allowed = run_async(
        cognix_routes.admin_local_only_egress_decision(
            cognix_routes.AdminLocalOnlyDecisionRequest(
                provider = "ollama",
                modelId = "qwen-test:4b",
                url = "http://127.0.0.1:11434/api/chat",
                actionType = "model",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert allowed["decision"]["allowed"] is True
    assert allowed["blockedExternalCall"] is None
    assert allowed["sideEffects"]["blockedCallWrite"] is False

    blocked_calls = run_async(cognix_routes.admin_local_only_blocked_calls(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert blocked_calls["blockedExternalCalls"][0]["provider"] == "openai"
    assert "admin_local_only_external_call_blocked" in audit_actions
