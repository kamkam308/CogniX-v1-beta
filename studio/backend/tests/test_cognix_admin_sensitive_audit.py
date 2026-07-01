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
from core.cognix import module_registry as cognix_module_registry
from core.cognix import sensitive_audit as cognix_sensitive_audit
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


def test_sensitive_audit_blueprint_schema_registry_and_surface_contract():
    blueprint = cognix_sensitive_audit.build_sensitive_audit_blueprint()
    assert blueprint["sensitiveAuditVersion"] == "cognix_sensitive_audit_v1"
    assert blueprint["services"] == ["AuditLogService", "SensitiveActionLogger", "AuditSearchService"]
    assert blueprint["tables"] == ["audit_logs", "sensitive_action_logs"]
    assert blueprint["immutabilityPolicy"]["standardAdminMutationAllowed"] is False
    assert {"admin_chat_read", "permissions_modified", "codex_code_modification"}.issubset(
        {item["id"] for item in blueprint["sensitiveActions"]}
    )

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_global_roadmap_tables(conn)
        cognix_db._ensure_sensitive_action_log_columns(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sensitive_action_logs)").fetchall()}
        assert {"audit_log_id", "sensitive_category", "actor_username", "search_text"}.issubset(columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    security = modules["cognix-admin-security-center"]
    operations = modules["cognix-admin-operations"]
    for module in (security, operations):
        assert "audit_log_service" in module["capabilities"]
        assert "sensitive_action_logger" in module["capabilities"]
        assert "audit_search_service" in module["capabilities"]
        assert "sensitive_action_logs" in module["capabilities"]
        assert "/api/cognix/admin/sensitive-action-logs" in module["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/sensitive-action-logs", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/audit"]["status"] == "equivalent"
    assert routes["/admin/audit"]["matchedRoute"] == "/api/cognix/admin/sensitive-action-logs"


def test_sensitive_actions_auto_persist_append_only_logs():
    seed_accounts()

    ordinary = cognix_db.create_audit_log(
        username = "alice",
        actor_username = auth_storage.DEFAULT_ADMIN_USERNAME,
        action = "profile_viewed",
        resource_type = "profile",
        resource_id = "alice",
        severity = "notice",
        metadata = {"reason": "support"},
    )
    assert ordinary["sensitiveAudit"]["sensitive"] is False
    assert cognix_db.list_sensitive_action_logs(limit = 10) == []

    expected = {
        "admin_chat_read",
        "permissions_modified",
        "user_ban",
        "project_deletion",
        "cloud_activation",
        "app_connection",
        "tool_execution",
        "cowork_control",
        "codex_code_modification",
        "scheduled_sensitive_task",
    }
    for action in [
        "admin_chat_thread_viewed",
        "project_permission_updated",
        "user_ban_applied",
        "project_deleted",
        "cloud_activation_enabled",
        "app_connection_created",
        "tool_execution_completed",
        "cowork_control_taken",
        "codex_code_modification_applied",
        "scheduled_sensitive_task_run",
    ]:
        audit = cognix_db.create_audit_log(
            username = "alice",
            actor_username = auth_storage.DEFAULT_ADMIN_USERNAME,
            action = action,
            resource_type = action,
            resource_id = "resource-1",
            severity = "warning",
            metadata = {"password": "secret-password", "actionCategory": action},
        )
        assert audit["sensitiveAudit"]["sensitive"] is True
        assert audit["sensitiveAudit"]["sensitiveActionLogId"]

    logs = cognix_db.list_sensitive_action_logs(limit = 50)
    categories = {item["sensitiveCategory"] for item in logs}
    assert expected.issubset(categories)
    assert all(item["immutableByStandardAdmin"] is True for item in logs)
    assert all("password" not in item["redactedMetadata"] for item in logs)
    assert all(item["redactedMetadata"].get("redactedSensitiveFieldCount") == 1 for item in logs)
    assert not hasattr(cognix_db, "delete_sensitive_action_log")
    assert not hasattr(cognix_routes, "admin_delete_sensitive_action_log")

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_sensitive_action_logs(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(
        cognix_routes.admin_sensitive_audit_blueprint(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    search = run_async(
        cognix_routes.admin_sensitive_action_logs(
            query = "codex",
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert blueprint["sensitiveAuditBlueprint"]["summary"]["sensitiveActionLogCount"] == len(logs)
    assert search["summary"]["sensitiveActionLogCount"] == 1
    assert search["sensitiveActionLogs"][0]["sensitiveCategory"] == "codex_code_modification"
