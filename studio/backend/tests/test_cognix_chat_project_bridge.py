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
from core.cognix import chat_project_bridge
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
    storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )
    storage.create_user(
        username = "bob",
        email = "bob@example.com",
        password = "bob-password-123",
    )


def login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json = {"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_project(owner_username: str = "alice", project_id: str = "project-alice-1") -> dict:
    return studio_db_storage.upsert_chat_project(
        {
            "id": project_id,
            "name": "CogniX bridge",
            "instructions": "Track chat tasks.",
            "archived": False,
            "createdAt": 1000,
            "updatedAt": 2000,
        },
        owner_username = owner_username,
    )


def seed_thread(
    owner_username: str = "alice",
    thread_id: str = "thread-alice-1",
    project_id: str | None = "project-alice-1",
) -> dict:
    return studio_db_storage.upsert_chat_thread(
        {
            "id": thread_id,
            "title": "Bridge kickoff",
            "modelType": "base",
            "modelId": "qwen-test",
            "projectId": project_id,
            "archived": False,
            "createdAt": 3000,
        },
        owner_username = owner_username,
    )


def seed_message(thread_id: str = "thread-alice-1", message_id: str = "msg-alice-1") -> dict:
    return studio_db_storage.upsert_chat_message(
        {
            "id": message_id,
            "threadId": thread_id,
            "parentId": None,
            "role": "user",
            "content": [{"type": "text", "text": "Turn this bridge decision into a tracked task."}],
            "createdAt": 3100,
        }
    )


def test_chat_project_bridge_blueprint_declares_native_services():
    blueprint = chat_project_bridge.build_chat_project_bridge_blueprint()

    assert blueprint["chatProjectBridgeVersion"] == "cognix_chat_project_bridge_v1"
    assert {"ChatProjectBridge", "MessageToTaskService", "ProjectMentionService"}.issubset(
        blueprint["services"]
    )
    assert blueprint["tables"] == ["chat_project_links", "message_tasks"]
    assert blueprint["sideEffects"]["modelCall"] is False
    assert blueprint["sideEffects"]["networkCall"] is False


def test_chat_project_bridge_endpoint_creates_link_task_and_approval(client: TestClient):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    seed_project()
    seed_thread()
    seed_message()

    link_response = client.post(
        "/api/cognix/chat-project-bridge/links",
        json = {"projectId": "project-alice-1", "threadId": "thread-alice-1"},
        headers = headers,
    )
    assert link_response.status_code == 200
    link_body = link_response.json()
    assert link_body["link"]["projectId"] == "project-alice-1"
    assert link_body["link"]["threadId"] == "thread-alice-1"
    assert link_body["sideEffects"]["chatProjectLinkWrite"] is True

    task_response = client.post(
        "/api/cognix/chat-project-bridge/message-tasks",
        json = {
            "projectId": "project-alice-1",
            "threadId": "thread-alice-1",
            "messageId": "msg-alice-1",
            "sourceText": "Ship the enterprise chat/project bridge.",
            "priority": "high",
            "requireApproval": True,
        },
        headers = headers,
    )
    assert task_response.status_code == 200
    task_body = task_response.json()
    assert task_body["task"]["projectId"] == "project-alice-1"
    assert task_body["task"]["messageId"] == "msg-alice-1"
    assert task_body["task"]["priority"] == "high"
    assert task_body["task"]["approvalRequestId"]
    assert task_body["sideEffects"]["messageTaskWrite"] is True
    assert task_body["sideEffects"]["approvalRequestWrite"] is True

    bridge_response = client.get("/api/cognix/chat-project-bridge", headers = headers)
    assert bridge_response.status_code == 200
    bridge_body = bridge_response.json()
    assert bridge_body["summary"]["linkCount"] == 1
    assert bridge_body["summary"]["taskCount"] == 1


def test_chat_project_bridge_rejects_cross_user_thread(client: TestClient):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    seed_project(owner_username = "alice", project_id = "project-alice-1")
    seed_thread(owner_username = "bob", thread_id = "thread-bob-1", project_id = None)

    response = client.post(
        "/api/cognix/chat-project-bridge/links",
        json = {"projectId": "project-alice-1", "threadId": "thread-bob-1"},
        headers = headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"
