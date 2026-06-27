import secrets
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage
from storage.studio_db import sync_chat_messages, upsert_chat_project, upsert_chat_thread


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


def login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json = {"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_developer_mode_request_is_deduplicated_and_admin_approved(client):
    seed_accounts()
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")
    user_headers = login_headers(client, "alice", "alice-password-123")

    before = client.get("/api/cognix/permissions/me", headers = user_headers)
    assert before.status_code == 200
    assert before.json()["developerMode"] is False

    first = client.post(
        "/api/cognix/approvals/developer-mode",
        headers = user_headers,
        json = {"reason": "Need developer tools for a training recipe."},
    )
    second = client.post(
        "/api/cognix/approvals/developer-mode",
        headers = user_headers,
        json = {"reason": "Clicked twice by mistake."},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_request = first.json()["request"]
    second_request = second.json()["request"]
    assert first_request["id"] == second_request["id"]
    assert first_request["status"] == "pending"

    dashboard = client.get("/api/cognix/admin/dashboard", headers = admin_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["summary"]["approvalsPending"] == 1

    decision = client.patch(
        f"/api/cognix/admin/approvals/{first_request['id']}",
        headers = admin_headers,
        json = {"status": "approved"},
    )
    assert decision.status_code == 200

    after = client.get("/api/cognix/permissions/me", headers = user_headers)
    assert after.status_code == 200
    assert after.json()["developerMode"] is True

    already_approved = client.post(
        "/api/cognix/approvals/developer-mode",
        headers = user_headers,
        json = {"reason": "Should not create a fresh pending request."},
    )
    assert already_approved.status_code == 200
    assert already_approved.json()["request"]["status"] == "approved"

    final_dashboard = client.get("/api/cognix/admin/dashboard", headers = admin_headers)
    assert final_dashboard.status_code == 200
    assert final_dashboard.json()["summary"]["approvalsPending"] == 0


def test_admin_denial_revokes_developer_mode_permission(client):
    seed_accounts()
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")
    user_headers = login_headers(client, "alice", "alice-password-123")

    created = client.post(
        "/api/cognix/approvals/developer-mode",
        headers = user_headers,
        json = {"reason": "Need temporary access for debugging."},
    )
    assert created.status_code == 200
    request_id = created.json()["request"]["id"]

    approved = client.patch(
        f"/api/cognix/admin/approvals/{request_id}",
        headers = admin_headers,
        json = {"status": "approved"},
    )
    assert approved.status_code == 200
    assert client.get("/api/cognix/permissions/me", headers = user_headers).json()["developerMode"] is True

    denied = client.patch(
        f"/api/cognix/admin/approvals/{request_id}",
        headers = admin_headers,
        json = {"status": "denied", "admin_note": "Temporary access finished."},
    )

    assert denied.status_code == 200
    assert denied.json()["request"]["status"] == "denied"
    permissions = client.get("/api/cognix/permissions/me", headers = user_headers)
    assert permissions.status_code == 200
    assert permissions.json()["developerMode"] is False


def test_non_admin_cannot_read_admin_dashboard(client):
    seed_accounts()
    user_headers = login_headers(client, "alice", "alice-password-123")

    response = client.get("/api/cognix/admin/dashboard", headers = user_headers)

    assert response.status_code == 403


def test_user_report_is_visible_to_admin(client):
    seed_accounts()
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")
    user_headers = login_headers(client, "alice", "alice-password-123")

    created = client.post(
        "/api/cognix/reports",
        headers = user_headers,
        json = {
            "category": "bug",
            "title": "Chat visual issue",
            "message": "The composer overlaps the profile menu.",
        },
    )
    assert created.status_code == 200
    report = created.json()["report"]
    assert report["status"] == "open"

    reports = client.get("/api/cognix/admin/reports", headers = admin_headers)

    assert reports.status_code == 200
    body = reports.json()
    assert any(item["id"] == report["id"] for item in body["reports"])


def test_admin_dashboard_exposes_conversation_model_time_and_usage(client, monkeypatch):
    seed_accounts()
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")
    monkeypatch.setenv("UNSLOTH_STUDIO_TRUST_FORWARDED", "1")
    alice_login = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "alice-password-123"},
        headers = {"X-Forwarded-For": "203.0.113.42"},
    )
    assert alice_login.status_code == 200
    base_time = 1_787_000_000_000
    upsert_chat_project(
        {
            "id": "project-alice-1",
            "name": "CogniX benchmark",
            "instructions": "Suivre les performances.",
            "archived": False,
            "createdAt": base_time - 30_000,
            "updatedAt": base_time + 30_000,
        },
        owner_username = "alice",
    )
    upsert_chat_thread(
        {
            "id": "thread-alice-1",
            "title": "Model performance check",
            "modelType": "base",
            "modelId": "CogniX High",
            "projectId": "project-alice-1",
            "archived": False,
            "createdAt": base_time,
        },
        owner_username = "alice",
    )
    sync_chat_messages(
        "thread-alice-1",
        [
            {
                "id": "msg-user-1",
                "threadId": "thread-alice-1",
                "role": "user",
                "content": [{"type": "text", "text": "Bonjour CogniX"}],
                "createdAt": base_time + 60_000,
            },
            {
                "id": "msg-assistant-1",
                "threadId": "thread-alice-1",
                "role": "assistant",
                "content": [{"type": "text", "text": "Bonjour, je suis pret."}],
                "createdAt": base_time + 120_000,
            },
        ],
    )

    response = client.get("/api/cognix/admin/dashboard", headers = admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["projects"] == 1
    alice = next(item for item in body["users"] if item["username"] == "alice")
    dashboard = alice["dashboard"]
    assert dashboard["chatCount"] == 1
    assert dashboard["projectCount"] == 1
    assert dashboard["network"]["lastLoginIp"] == "203.0.113.42"
    assert dashboard["passwordStatus"]["label"] == "Configure"
    assert dashboard["passwordStatus"]["secretExposed"] is False
    assert "passwordHash" not in dashboard["passwordStatus"]
    assert dashboard["quota"]["usedTokens"] > 0
    assert dashboard["quota"]["label"] == "Quota non configure"
    assert dashboard["projects"][0]["name"] == "CogniX benchmark"
    thread = next(item for item in body["threads"] if item["id"] == "thread-alice-1")
    assert thread["ownerUsername"] == "alice"
    assert thread["modelId"] == "CogniX High"
    assert thread["projectId"] == "project-alice-1"
    assert thread["createdAt"] == base_time
    usage = next(
        item
        for item in body["computeUsage"]
        if item["username"] == "alice" and item["modelId"] == "CogniX High"
    )
    assert usage["conversations"] == 1
    assert usage["messages"] == 2
    assert usage["approxTokens"] == usage["estimatedTokens"]
    assert usage["approxTokens"] > 0
    assert usage["lastUsedAt"] == base_time + 120_000


def test_admin_dashboard_never_exposes_password_or_token_secrets(client):
    seed_accounts()
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")

    response = client.get("/api/cognix/admin/dashboard", headers = admin_headers)

    assert response.status_code == 200
    body = response.json()

    forbidden_keys = {
        "password_salt",
        "passwordSalt",
        "password_hash",
        "passwordHash",
        "jwt_secret",
        "jwtSecret",
        "refresh_token_hash",
        "refreshTokenHash",
        "api_key_hash",
        "apiKeyHash",
    }
    seen_keys: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            seen_keys.update(str(key) for key in value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(body)

    assert forbidden_keys.isdisjoint(seen_keys)
    for user in body["users"]:
        password_status = user["dashboard"]["passwordStatus"]
        assert password_status["configured"] is True
        assert password_status["secretExposed"] is False
