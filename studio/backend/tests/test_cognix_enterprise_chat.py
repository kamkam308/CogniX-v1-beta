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
from core.cognix import enterprise_chat
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
    for username in ("alice", "bob", "charlie"):
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


def test_enterprise_chat_blueprint_declares_e2ee_and_compliance_modes():
    blueprint = enterprise_chat.build_enterprise_chat_blueprint()

    assert blueprint["enterpriseChatServiceVersion"] == "cognix_enterprise_chat_service_v1"
    assert {
        "EnterpriseChatService",
        "E2EEKeyManager",
        "MessageEncryptionService",
        "ChatPolicyService",
    }.issubset(set(blueprint["services"]))
    assert blueprint["tables"] == [
        "enterprise_chats",
        "enterprise_chat_members",
        "encrypted_messages",
        "chat_key_metadata",
        "chat_policies",
    ]
    assert {item["id"] for item in blueprint["modes"]} == {"compliance", "e2ee"}
    assert blueprint["sideEffects"]["plaintextRead"] is False
    assert blueprint["sideEffects"]["serverDecryption"] is False


def test_enterprise_e2ee_chat_stores_metadata_and_encrypted_messages_only(client: TestClient):
    seed_accounts()
    alice_headers = login_headers(client, "alice")
    bob_headers = login_headers(client, "bob")

    create_response = client.post(
        "/api/cognix/chat/enterprise/chats",
        headers = alice_headers,
        json = {
            "title": "Legal review",
            "chatMode": "e2ee",
            "participants": [{"username": "bob", "role": "member"}],
        },
    )
    assert create_response.status_code == 200
    body = create_response.json()
    chat = body["enterpriseChat"]
    chat_id = chat["id"]

    assert body["sideEffects"]["chatWrite"] is True
    assert chat["payload"]["policy"]["serverContentReadable"] is False
    assert chat["payload"]["policy"]["serverIndexingAllowed"] is False
    assert chat["payload"]["keyPlan"]["serverStoresKeyMaterial"] is False
    assert len(chat["members"]) == 2

    message_response = client.post(
        f"/api/cognix/chat/enterprise/chats/{chat_id}/messages",
        headers = alice_headers,
        json = {
            "encryptedPayload": {
                "ciphertext": "sealed:abc123",
                "nonce": "nonce-1",
                "keyId": "client-key-1",
                "algorithm": "xchacha20-poly1305",
            },
            "metadata": {"pinned": True},
        },
    )
    assert message_response.status_code == 200
    message_body = message_response.json()
    assert message_body["sideEffects"]["encryptedMessageWrite"] is True
    assert message_body["encryptedMessagePlan"]["message"]["plaintextStored"] is False
    assert message_body["encryptedMessagePlan"]["message"]["serverCanDecrypt"] is False
    assert "abc123" not in message_body["auditLogId"]

    bob_detail = client.get(f"/api/cognix/chat/enterprise/chats/{chat_id}", headers = bob_headers)
    assert bob_detail.status_code == 200
    assert bob_detail.json()["encryptedMessages"][0]["payload"]["message"]["plaintextStored"] is False

    rotation = client.post(
        f"/api/cognix/chat/enterprise/chats/{chat_id}/key-rotation-plan",
        headers = bob_headers,
        json = {"reason": "member device changed", "revokedMember": "bob"},
    )
    assert rotation.status_code == 200
    assert rotation.json()["keyRotationPlan"]["serverGeneratesKeys"] is False
    assert rotation.json()["keyRotationPlan"]["serverStoresKeyMaterial"] is False


def test_enterprise_chat_blocks_non_members_and_missing_encrypted_payload(client: TestClient):
    seed_accounts()
    alice_headers = login_headers(client, "alice")
    charlie_headers = login_headers(client, "charlie")

    create_response = client.post(
        "/api/cognix/chat/enterprise/chats",
        headers = alice_headers,
        json = {
            "title": "Private chat",
            "chatMode": "e2ee",
            "participants": [{"username": "bob", "role": "member"}],
        },
    )
    assert create_response.status_code == 200
    chat_id = create_response.json()["enterpriseChat"]["id"]

    forbidden_detail = client.get(f"/api/cognix/chat/enterprise/chats/{chat_id}", headers = charlie_headers)
    assert forbidden_detail.status_code == 404

    invalid_message = client.post(
        f"/api/cognix/chat/enterprise/chats/{chat_id}/messages",
        headers = alice_headers,
        json = {"encryptedPayload": {"ciphertext": "sealed-without-key"}},
    )
    assert invalid_message.status_code == 400
    assert "Encrypted payload" in invalid_message.json()["detail"]
