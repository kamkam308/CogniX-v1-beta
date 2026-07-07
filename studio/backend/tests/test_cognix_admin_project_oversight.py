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
from core.cognix import admin_project_oversight as cognix_admin_project_oversight
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


def seed_project() -> dict:
    now = int(time.time() * 1000)
    project = studio_db_storage.upsert_chat_project(
        {
            "id": "project-alice-1",
            "name": "Alice Research",
            "instructions": "Use local-first models.",
            "archived": False,
            "createdAt": now - 1000,
            "updatedAt": now,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-alice-1",
            "title": "Qwen test",
            "modelType": "local",
            "modelId": "qwen-test:4b",
            "projectId": project["id"],
            "archived": False,
            "createdAt": now,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_message(
        {
            "id": "msg-alice-1",
            "threadId": "thread-alice-1",
            "role": "user",
            "content": [{"type": "text", "text": "hello"}],
            "createdAt": now,
        }
    )
    cognix_db.create_token_usage_event(
        "alice",
        project_id = project["id"],
        model_id = "qwen-test:4b",
        provider = "openrouter",
        input_tokens = 70_000,
        output_tokens = 40_000,
        estimated_cost_usd = 0.42,
    )
    cognix_db.upsert_project_permission(
        project["id"],
        subject_type = "user",
        subject_id = "alice",
        permission_key = "models:cloud",
        allowed = False,
        updated_by = auth_storage.DEFAULT_ADMIN_USERNAME,
    )
    return project


def test_admin_project_oversight_blueprint_schema_and_surface_contract():
    blueprint = cognix_admin_project_oversight.build_admin_project_blueprint()
    assert blueprint["adminProjectServiceVersion"] == "cognix_admin_project_service_v1"
    assert blueprint["services"] == ["AdminProjectService", "ProjectRiskAnalyzer", "ProjectUsageAggregator"]
    assert "admin_project_events" in blueprint["tables"]
    assert "project_admin_reports" in blueprint["tables"]
    assert blueprint["security"]["sensitiveActionsRequireApproval"] is True
    assert blueprint["sideEffects"]["projectMutation"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_admin_project_oversight_columns(conn)
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_project_events)").fetchall()}
        report_columns = {row[1] for row in conn.execute("PRAGMA table_info(project_admin_reports)").fetchall()}
        assert {"actor_username", "action", "event_json", "approval_required"}.issubset(event_columns)
        assert {"generated_by", "report_type", "report_json", "risk_level"}.issubset(report_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    assert "cognix-admin-project-oversight" in modules
    assert "/api/cognix/admin/projects" in modules["cognix-admin-project-oversight"]["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/projects", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/projects"]["status"] == "equivalent"
    assert routes["/admin/projects"]["matchedRoute"] == "/api/cognix/admin/projects"


def test_admin_project_oversight_routes_plan_action_and_persist_report():
    seed_accounts()
    project = seed_project()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_projects_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_projects_blueprint(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert blueprint["adminProjectsBlueprint"]["mode"] == "native_admin_project_oversight"

    overview = run_async(cognix_routes.admin_projects(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert overview["adminProjectOversight"]["summary"]["projectCount"] == 1
    item = overview["adminProjectOversight"]["projects"][0]
    assert item["projectId"] == project["id"]
    assert item["usage"]["tokenTotal"] == 110_000
    assert item["risk"]["riskLevel"] in {"medium", "high", "critical"}
    assert overview["sideEffects"]["projectMutation"] is False

    action = run_async(
        cognix_routes.admin_project_action_plan(
            project["id"],
            cognix_routes.AdminProjectActionPlanRequest(
                action = "restrict_models",
                reason = "Lock project to approved local models",
                modelIds = ["qwen-test:4b"],
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert action["actionPlan"]["readyForApproval"] is True
    assert action["actionPlan"]["permissionRequired"] == "admin:projects:models"
    assert action["sideEffects"]["adminProjectEventWrite"] is True
    assert action["sideEffects"]["projectMutation"] is False
    assert cognix_db.list_admin_project_events(project_id = project["id"])[0]["action"] == "restrict_models"

    report = run_async(
        cognix_routes.admin_project_report(
            project["id"],
            cognix_routes.AdminProjectReportRequest(reportType = "full", outputFormat = "json", reason = "audit"),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert report["sideEffects"]["reportWrite"] is True
    assert report["sideEffects"]["modelLoad"] is False
    stored_reports = cognix_db.list_project_admin_reports(project_id = project["id"])
    assert stored_reports[0]["reportType"] == "full"
    assert stored_reports[0]["report"]["projectId"] == project["id"]

    detail = run_async(
        cognix_routes.admin_project_detail(project["id"], current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    assert detail["project"]["adminReports"][0]["reportType"] == "full"
    assert detail["project"]["adminEvents"][0]["action"] == "restrict_models"
