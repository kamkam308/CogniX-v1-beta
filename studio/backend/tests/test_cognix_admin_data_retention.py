from __future__ import annotations

import asyncio
import secrets
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage as auth_storage
from core.cognix import admin_data_retention as cognix_admin_data_retention
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


def seed_old_chat_project() -> None:
    now = int(time.time() * 1000)
    old_project_time = now - (400 * 86_400_000)
    old_thread_time = now - (120 * 86_400_000)
    project = studio_db_storage.upsert_chat_project(
        {
            "id": "project-alice-retention",
            "name": "Alice Retention Project",
            "instructions": "Local-first private project.",
            "archived": False,
            "createdAt": old_project_time,
            "updatedAt": old_project_time,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-alice-retention",
            "title": "Old private chat",
            "modelType": "local",
            "modelId": "qwen-test:4b",
            "projectId": project["id"],
            "archived": False,
            "createdAt": old_thread_time,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_message(
        {
            "id": "msg-alice-retention",
            "threadId": "thread-alice-retention",
            "role": "user",
            "content": [{"type": "text", "text": "my password and sk-test-secret must stay private"}],
            "createdAt": old_thread_time + 1000,
        }
    )


def test_data_retention_blueprint_schema_module_registry_and_surface_contract():
    blueprint = cognix_admin_data_retention.build_data_retention_blueprint()
    assert blueprint["dataRetentionServiceVersion"] == "cognix_data_retention_service_v1"
    assert blueprint["privacyPolicyServiceVersion"] == "cognix_privacy_policy_service_v1"
    assert blueprint["dataDeletionServiceVersion"] == "cognix_data_deletion_service_v1"
    assert blueprint["services"] == ["DataRetentionService", "PrivacyPolicyService", "DataDeletionService"]
    assert {"retention_policies", "deletion_jobs", "privacy_events"}.issubset(set(blueprint["tables"]))
    assert blueprint["e2eeLimits"]["strictModeServerContentReadable"] is False
    assert blueprint["sideEffects"]["contentDelete"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_admin_data_retention_columns(conn)
        policy_columns = {row[1] for row in conn.execute("PRAGMA table_info(retention_policies)").fetchall()}
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(deletion_jobs)").fetchall()}
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(privacy_events)").fetchall()}
        assert {"policy_key", "chat_retention_days", "sensitive_prompt_mode", "policy_json"}.issubset(
            policy_columns
        )
        assert {"target_type", "target_id", "approval_required", "job_json"}.issubset(job_columns)
        assert {"actor_username", "target_username", "privacy_mode", "event_json"}.issubset(event_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    data_retention = modules["cognix-admin-data-retention-privacy"]
    assert "data_retention_service" in data_retention["capabilities"]
    assert "privacy_policy_service" in data_retention["capabilities"]
    assert "/api/cognix/admin/data-retention/privacy-decision" in data_retention["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/data-retention", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/settings"]["status"] == "equivalent"
    assert routes["/admin/settings"]["matchedRoute"] == "/api/cognix/admin/data-retention"


def test_data_retention_routes_policy_privacy_export_and_deletion_jobs():
    seed_accounts()
    seed_old_chat_project()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_data_retention_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    updated = run_async(
        cognix_routes.admin_update_data_retention_policy(
            cognix_routes.AdminDataRetentionPolicyRequest(
                chatRetentionDays = 30,
                projectArchiveMonths = 6,
                sensitivePromptMode = "metadata_only",
                contentLogsEnabled = False,
                metadataOnlyMode = True,
                userExportEnabled = True,
                e2eeStrict = True,
                reason = "Privacy-first retention policy",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert updated["policy"]["chatRetentionDays"] == 30
    assert updated["policy"]["metadataOnlyMode"] is True
    assert updated["sideEffects"]["retentionPolicyWrite"] is True
    assert updated["privacyEvent"]["eventType"] == "retention_policy_updated"

    plan = run_async(cognix_routes.admin_data_retention_plan(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert plan["retentionPlan"]["summary"]["chatDeletionCandidateCount"] == 1
    assert plan["retentionPlan"]["summary"]["projectArchiveCandidateCount"] == 1
    assert plan["retentionPlan"]["sideEffects"]["contentDelete"] is False

    decision = run_async(
        cognix_routes.admin_privacy_decision(
            cognix_routes.AdminPrivacyDecisionRequest(
                targetUsername = "alice",
                e2eeStrict = True,
                content = "this contains sk-test-secret and password",
                metadata = {"source": "pytest"},
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert decision["decision"]["storageMode"] == "metadata_only"
    assert decision["decision"]["contentReadableByServer"] is False
    assert decision["sideEffects"]["privacyEventWrite"] is True
    assert decision["sideEffects"]["contentStore"] is False

    export = run_async(
        cognix_routes.admin_user_export_plan(
            "alice",
            cognix_routes.AdminUserDataRequest(
                reason = "User requested export",
                includeContent = True,
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert export["exportPlan"]["contentIncluded"] is False
    assert export["exportPlan"]["metadataOnly"] is True
    assert export["exportPlan"]["summary"]["messageCount"] == 1
    assert export["exportPlan"]["payload"]["messages"][0]["content"] is None

    deletion = run_async(
        cognix_routes.admin_user_deletion_plan(
            "alice",
            cognix_routes.AdminUserDataRequest(reason = "User requested deletion"),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert deletion["deletionPlan"]["status"] == "requires_approval"
    assert deletion["deletionJob"]["status"] == "requires_approval"
    assert deletion["sideEffects"]["deletionJobWrite"] is True
    assert deletion["sideEffects"]["contentDelete"] is False

    jobs = run_async(cognix_routes.admin_deletion_jobs(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    events = run_async(cognix_routes.admin_privacy_events(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert jobs["deletionJobs"][0]["targetId"] == "alice"
    assert "admin_user_deletion_planned" in audit_actions
    assert {event["eventType"] for event in events["privacyEvents"]}.issuperset(
        {"retention_policy_updated", "privacy_decision_logged"}
    )
