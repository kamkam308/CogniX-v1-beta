from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage
from core.cognix import cowork
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(storage, "_bootstrap_password", None)
    monkeypatch.setattr(storage, "_api_key_pbkdf2_salt_cache", None)
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


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auth_routes.router, prefix = "/api/auth")
    app.include_router(cognix_routes.router, prefix = "/api/cognix")
    return TestClient(app)


def seed_accounts() -> None:
    storage.create_initial_user(
        username = storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    for username in ("alice", "bob"):
        storage.create_user(
            username = username,
            email = f"{username}@example.com",
            password = f"{username}-password-123",
        )


def login_headers(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json = {"username": username, "password": f"{username}-password-123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_project(owner_username: str = "alice", project_id: str = "project-cowork-1") -> dict:
    return studio_db_storage.upsert_chat_project(
        {
            "id": project_id,
            "name": "CogniX Cowork",
            "instructions": "Visible project-scoped Cowork session.",
            "archived": False,
            "createdAt": 1000,
            "updatedAt": 2000,
        },
        owner_username = owner_username,
    )


def test_cowork_blueprint_declares_native_services_and_no_execution():
    blueprint = cowork.build_cowork_blueprint()

    assert blueprint["coworkServiceVersion"] == "cognix_cowork_service_v1"
    assert {
        "CoworkService",
        "RemoteControlPolicyEngine",
        "CommandAllowlist",
        "ActionRecorder",
        "HumanApprovalGate",
    }.issubset(set(blueprint["services"]))
    assert blueprint["tables"] == [
        "cowork_sessions",
        "cowork_actions",
        "cowork_permissions",
        "cowork_approvals",
    ]
    assert blueprint["securityPolicy"]["neverStealth"] is True
    assert blueprint["securityPolicy"]["directExecutionAllowed"] is False
    assert blueprint["sideEffects"]["commandExecution"] is False
    assert blueprint["sideEffects"]["fileWrite"] is False
    assert blueprint["sideEffects"]["secretRead"] is False

    session_plan = cowork.build_cowork_session_plan(
        username = "alice",
        level = "full_dev_project",
        project_id = "project-cowork-1",
        objective = "Aide-moi a corriger le projet.",
    )
    assert session_plan["cowork"]["status"] == "pending_approval"
    assert session_plan["cowork"]["approvalRequired"] is True
    assert session_plan["cowork"]["neverStealth"] is True

    action_plan = cowork.build_cowork_action_plan(
        username = "alice",
        session = {"id": "cwk_1", "status": "active", "payload": session_plan},
        action_type = "run_command",
        command = "rm -rf /",
    )
    assert action_plan["action"]["allowed"] is False
    assert action_plan["action"]["requiresApproval"] is True
    assert action_plan["action"]["willExecuteNow"] is False
    assert action_plan["sideEffects"]["commandExecution"] is False


def test_cowork_session_actions_status_and_user_scope(client: TestClient):
    seed_accounts()
    seed_project()
    alice_headers = login_headers(client, "alice")
    bob_headers = login_headers(client, "bob")

    create_response = client.post(
        "/api/cognix/cowork/sessions",
        headers = alice_headers,
        json = {
            "level": "run_dev_commands",
            "projectId": "project-cowork-1",
            "objective": "Lancer les tests autorises de maniere visible.",
        },
    )
    assert create_response.status_code == 200
    body = create_response.json()
    session = body["coworkSession"]
    session_id = session["id"]

    assert body["requiresApproval"] is True
    assert body["plan"]["sideEffects"]["sessionWrite"] is True
    assert body["plan"]["sideEffects"]["commandExecution"] is False
    assert len(session["permissions"]) >= 1
    assert len(session["approvals"]) == 1

    action_response = client.post(
        f"/api/cognix/cowork/sessions/{session_id}/actions",
        headers = alice_headers,
        json = {
            "actionType": "run_command",
            "command": "pytest",
            "description": "Planifier les tests, sans execution directe.",
        },
    )
    assert action_response.status_code == 200
    action_body = action_response.json()
    assert action_body["requiresApproval"] is True
    assert action_body["willExecuteNow"] is False
    assert action_body["actionPlan"]["sideEffects"]["commandExecution"] is False

    pause_response = client.patch(
        f"/api/cognix/cowork/sessions/{session_id}/status",
        headers = alice_headers,
        json = {"status": "paused"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["coworkSession"]["status"] == "paused"

    actions_response = client.get(
        f"/api/cognix/cowork/sessions/{session_id}/actions",
        headers = alice_headers,
    )
    assert actions_response.status_code == 200
    assert len(actions_response.json()["actions"]) == 1

    bob_detail = client.get(f"/api/cognix/cowork/sessions/{session_id}", headers = bob_headers)
    assert bob_detail.status_code == 404


def test_cowork_blocks_non_owner_project_and_audits_actions(client: TestClient):
    seed_accounts()
    seed_project(owner_username = "alice", project_id = "project-cowork-1")
    alice_headers = login_headers(client, "alice")
    bob_headers = login_headers(client, "bob")

    blocked_response = client.post(
        "/api/cognix/cowork/sessions",
        headers = bob_headers,
        json = {
            "level": "suggest_only",
            "projectId": "project-cowork-1",
            "objective": "Entrer dans le projet Alice.",
        },
    )
    assert blocked_response.status_code == 404

    create_response = client.post(
        "/api/cognix/cowork/sessions",
        headers = alice_headers,
        json = {
            "level": "edit_project_files",
            "projectId": "project-cowork-1",
            "objective": "Proposer une modification de fichier.",
        },
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["coworkSession"]["id"]

    risky_response = client.post(
        f"/api/cognix/cowork/sessions/{session_id}/actions",
        headers = alice_headers,
        json = {
            "actionType": "edit_file",
            "path": "/etc/passwd",
            "description": "Tentative hors projet.",
        },
    )
    assert risky_response.status_code == 200
    risky = risky_response.json()
    assert risky["allowed"] is False
    assert risky["requiresApproval"] is True
    assert "system_path" in risky["actionPlan"]["action"]["blockedReasons"]

    logs = cognix_db.list_audit_logs(username = "alice", action = "cowork_action_planned")
    assert logs
    assert logs[0]["metadata"]["willExecuteNow"] is False
    assert logs[0]["metadata"]["neverStealth"] is True
