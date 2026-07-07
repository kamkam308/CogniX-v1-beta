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
from core.cognix import agent_mode
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


def seed_project(owner_username: str = "alice", project_id: str = "project-agent-1") -> dict:
    return studio_db_storage.upsert_chat_project(
        {
            "id": project_id,
            "name": "CogniX Agent Mode",
            "instructions": "Use guarded native planning.",
            "archived": False,
            "createdAt": 1000,
            "updatedAt": 2000,
        },
        owner_username = owner_username,
    )


def test_agent_mode_blueprint_declares_native_services_and_safety():
    blueprint = agent_mode.build_agent_mode_blueprint()

    assert blueprint["agentModeServiceVersion"] == "cognix_agent_mode_service_v1"
    assert {
        "AgentModeService",
        "TaskPlanner",
        "ToolExecutionService",
        "AgentMemory",
        "AgentProgressStreamer",
    }.issubset(set(blueprint["services"]))
    assert blueprint["tables"] == [
        "agent_sessions",
        "agent_steps",
        "agent_tool_calls",
        "agent_outputs",
    ]
    assert blueprint["securityPolicy"]["directToolExecutionAllowed"] is False
    assert blueprint["sideEffects"]["toolExecution"] is False
    assert blueprint["sideEffects"]["modelLoad"] is False
    assert blueprint["sideEffects"]["generation"] is False
    assert blueprint["sideEffects"]["fileWrite"] is False


def test_agent_mode_session_tracks_steps_tool_plans_and_outputs(client: TestClient):
    seed_accounts()
    seed_project()
    alice_headers = login_headers(client, "alice")

    create_response = client.post(
        "/api/cognix/agent-mode/sessions",
        headers = alice_headers,
        json = {
            "goal": "Analyse ce repo et prepare un correctif teste.",
            "mode": "repo",
            "projectId": "project-agent-1",
            "allowedTools": ["filesystem-read", "terminal"],
            "memoryPolicy": {"enabled": True, "writeAtEnd": True},
            "maxSteps": 6,
        },
    )
    assert create_response.status_code == 200
    body = create_response.json()
    session = body["agentSession"]
    session_id = session["id"]
    step_id = body["plan"]["steps"][0]["id"]

    assert body["plan"]["sideEffects"]["sessionWrite"] is True
    assert body["plan"]["sideEffects"]["stepWrite"] is True
    assert body["plan"]["sideEffects"]["toolExecution"] is False
    assert len(session["steps"]) >= 1

    step_response = client.post(
        f"/api/cognix/agent-mode/sessions/{session_id}/steps/{step_id}",
        headers = alice_headers,
        json = {
            "status": "running",
            "result": "Inspection demarree.",
            "progressPercent": 35,
        },
    )
    assert step_response.status_code == 200
    assert step_response.json()["stepPlan"]["sideEffects"]["stepWrite"] is True

    tool_response = client.post(
        f"/api/cognix/agent-mode/sessions/{session_id}/tool-call-plan",
        headers = alice_headers,
        json = {
            "stepId": step_id,
            "toolId": "terminal",
            "action": "shell_exec",
            "arguments": {"cmd": "pytest"},
        },
    )
    assert tool_response.status_code == 200
    tool_body = tool_response.json()
    assert tool_body["requiresApproval"] is True
    assert tool_body["willExecuteNow"] is False
    assert tool_body["toolCallPlan"]["sideEffects"]["toolExecution"] is False
    assert tool_body["toolCallPlan"]["sideEffects"]["toolCallWrite"] is True

    output_response = client.post(
        f"/api/cognix/agent-mode/sessions/{session_id}/outputs",
        headers = alice_headers,
        json = {
            "content": "Plan final pret, aucune execution directe realisee.",
            "outputType": "final_report",
        },
    )
    assert output_response.status_code == 200
    assert output_response.json()["outputPlan"]["sideEffects"]["outputWrite"] is True
    assert output_response.json()["outputPlan"]["sideEffects"]["memoryWrite"] is False

    detail_response = client.get(
        f"/api/cognix/agent-mode/sessions/{session_id}",
        headers = alice_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()["agentSession"]
    assert len(detail["toolCalls"]) == 1
    assert len(detail["outputs"]) == 1


def test_agent_mode_blocks_non_owner_project_and_legacy_agent_run_uses_native_session(client: TestClient):
    seed_accounts()
    seed_project(owner_username = "alice", project_id = "project-agent-1")
    alice_headers = login_headers(client, "alice")
    bob_headers = login_headers(client, "bob")

    blocked_response = client.post(
        "/api/cognix/agent-mode/sessions",
        headers = bob_headers,
        json = {
            "goal": "Essayer de planifier dans le projet Alice.",
            "mode": "repo",
            "projectId": "project-agent-1",
        },
    )
    assert blocked_response.status_code == 404

    legacy_response = client.post(
        "/api/cognix/agent-runs",
        headers = alice_headers,
        json = {
            "goal": "Prepare une checklist autonome.",
            "mode": "agent",
            "allowedTools": ["terminal"],
        },
    )
    assert legacy_response.status_code == 200
    legacy_body = legacy_response.json()
    session_id = legacy_body["agentSession"]["id"]
    assert legacy_body["run"]["id"] == session_id
    assert legacy_body["plan"]["sideEffects"]["sessionWrite"] is True
    assert legacy_body["plan"]["sideEffects"]["toolExecution"] is False

    runs_response = client.get("/api/cognix/agent-runs", headers = alice_headers)
    assert runs_response.status_code == 200
    assert session_id in {item["id"] for item in runs_response.json()["runs"]}
