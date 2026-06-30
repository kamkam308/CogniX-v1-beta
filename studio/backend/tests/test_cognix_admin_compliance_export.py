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
from core.cognix import admin_compliance_export as cognix_admin_compliance_export
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


def seed_compliance_data() -> None:
    cognix_db.create_token_usage_event(
        "alice",
        project_id = "project-alice-1",
        model_id = "qwen-test:4b",
        provider = "local",
        input_tokens = 120,
        output_tokens = 80,
        estimated_cost_usd = 0,
    )
    cognix_db.create_user_activity_event(
        "alice",
        event_type = "chat_message_sent",
        resource_type = "chat_thread",
        resource_id = "thread-alice-1",
    )
    cognix_db.record_security_event(
        username = "alice",
        client_key = "127.0.0.1",
        category = "scanner_probe",
        severity = "medium",
        pattern_label = "Scanner probe",
        method = "GET",
        path = "/.env",
        excerpt = "scanner",
    )
    cognix_db.create_approval_request(
        "alice",
        "developer_mode",
        "Need developer mode",
        title = "Developer mode",
        risk_level = "medium",
    )
    cognix_db.record_admin_chat_access(
        admin_username = auth_storage.DEFAULT_ADMIN_USERNAME,
        target_username = "alice",
        thread_id = "thread-alice-1",
        access_mode = "metadata_only",
        content_visible = False,
        reason = "compliance test",
    )


def test_compliance_export_blueprint_schema_and_module_registry():
    blueprint = cognix_admin_compliance_export.build_compliance_export_blueprint()
    assert blueprint["complianceExportServiceVersion"] == "cognix_compliance_export_service_v1"
    assert blueprint["services"] == ["ComplianceExportService", "ReportBuilder", "ExportJobService"]
    assert "compliance_exports" in blueprint["tables"]
    assert "export_jobs" in blueprint["tables"]
    assert {"json", "markdown", "csv", "pdf"}.issubset(set(blueprint["formats"]))
    assert blueprint["sideEffects"]["fileWrite"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_admin_compliance_export_columns(conn)
        export_columns = {row[1] for row in conn.execute("PRAGMA table_info(compliance_exports)").fetchall()}
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(export_jobs)").fetchall()}
        assert {"generated_by", "export_type", "output_format", "checksum", "content_json"}.issubset(
            export_columns
        )
        assert {"export_id", "queued_by", "job_type", "progress_percent", "job_json"}.issubset(job_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    assert "cognix-admin-compliance-export" in modules
    assert "/api/cognix/admin/compliance/exports/plan" in modules["cognix-admin-compliance-export"]["routes"]


def test_compliance_export_routes_plan_create_and_fetch_report():
    seed_accounts()
    seed_compliance_data()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_compliance_exports_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    plan = run_async(
        cognix_routes.admin_compliance_export_plan(
            cognix_routes.AdminComplianceExportRequest(reportType = "full", outputFormat = "markdown"),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert plan["report"]["summary"]["tokenEventCount"] == 1
    assert plan["report"]["summary"]["adminChatAccessCount"] == 1
    assert plan["exportJobPlan"]["requiresRenderer"] is False
    assert plan["sideEffects"]["exportWrite"] is False

    created = run_async(
        cognix_routes.admin_create_compliance_export(
            cognix_routes.AdminComplianceExportRequest(
                reportType = "security_threats",
                outputFormat = "pdf",
                reason = "Quarterly compliance",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert created["sideEffects"]["exportWrite"] is True
    assert created["sideEffects"]["exportJobWrite"] is True
    assert created["sideEffects"]["fileWrite"] is False
    assert created["export"]["checksum"]
    assert created["exportJob"]["status"] == "queued"
    assert created["exportJob"]["job"]["requiresRenderer"] is True

    detail = run_async(
        cognix_routes.admin_compliance_export_detail(
            created["export"]["id"],
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert detail["export"]["id"] == created["export"]["id"]
    assert detail["exportJobs"][0]["exportId"] == created["export"]["id"]
