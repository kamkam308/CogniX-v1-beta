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
from core.cognix import realtime_collaboration
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


def seed_project_with_collaborator(permission: str = "edit") -> None:
    studio_db_storage.upsert_chat_project(
        {
            "id": "project-collab-1",
            "name": "Realtime research",
            "instructions": "Shared project",
            "createdAt": 1,
            "updatedAt": 1,
        },
        owner_username = "alice",
    )
    share = cognix_db.create_project_share("alice", "project-collab-1", permission = permission)
    accepted = cognix_db.accept_project_share(str(share["token"]), "bob")
    assert accepted is not None


def test_realtime_collaboration_blueprint_declares_native_services_and_safety():
    blueprint = realtime_collaboration.build_realtime_collaboration_blueprint()

    assert blueprint["realtimeCollaborationVersion"] == "cognix_realtime_collaboration_v1"
    assert {
        "RealtimeCollaborationService",
        "PresenceService",
        "CommentService",
        "ConflictResolver",
    }.issubset(set(blueprint["services"]))
    assert blueprint["tables"] == ["presence_sessions", "project_comments", "collaboration_events"]
    assert "websocket_ready_contract" not in blueprint["capabilities"]
    assert blueprint["transportContract"]["webSocketReady"] is True
    assert blueprint["transportContract"]["hiddenPresenceAllowed"] is False
    assert blueprint["sideEffects"]["projectFileWrite"] is False
    assert blueprint["sideEffects"]["modelLoad"] is False


def test_realtime_presence_comments_and_events_work_for_project_collaborators(client: TestClient):
    seed_accounts()
    seed_project_with_collaborator(permission = "edit")
    alice_headers = login_headers(client, "alice")
    bob_headers = login_headers(client, "bob")

    presence_response = client.post(
        "/api/cognix/projects/project-collab-1/realtime/presence",
        headers = alice_headers,
        json = {
            "clientId": "browser-a",
            "status": "editing",
            "activity": "Editing notes",
            "cursor": {"resourceType": "note", "resourceId": "intro", "line": 3, "column": 8},
        },
    )
    assert presence_response.status_code == 200
    presence_body = presence_response.json()
    assert presence_body["sideEffects"]["presenceWrite"] is True
    assert presence_body["presence"]["payload"]["presence"]["hiddenPresenceAllowed"] is False

    visible_presence = client.get(
        "/api/cognix/projects/project-collab-1/realtime/presence",
        headers = bob_headers,
    )
    assert visible_presence.status_code == 200
    assert visible_presence.json()["presenceSessions"][0]["username"] == "alice"

    comment_response = client.post(
        "/api/cognix/projects/project-collab-1/comments",
        headers = bob_headers,
        json = {
            "body": "A verifier avant publication.",
            "target": {"type": "note", "id": "intro"},
        },
    )
    assert comment_response.status_code == 200
    comment_body = comment_response.json()
    comment_id = comment_body["projectComment"]["id"]
    assert comment_body["sideEffects"]["commentWrite"] is True
    assert comment_body["projectComment"]["payload"]["comment"]["status"] == "open"

    resolve_response = client.post(
        f"/api/cognix/projects/project-collab-1/comments/{comment_id}/resolve",
        headers = alice_headers,
        json = {"status": "resolved", "note": "Checked."},
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["projectComment"]["status"] == "resolved"

    events_response = client.get(
        "/api/cognix/projects/project-collab-1/collaboration/events",
        headers = bob_headers,
    )
    assert events_response.status_code == 200
    event_types = {item["payload"]["event"]["type"] for item in events_response.json()["collaborationEvents"]}
    assert {"presence_updated", "comment_created", "comment_resolved"}.issubset(event_types)


def test_realtime_collaboration_blocks_non_members_and_requires_edit_for_conflicts(client: TestClient):
    seed_accounts()
    seed_project_with_collaborator(permission = "view")
    bob_headers = login_headers(client, "bob")
    charlie_headers = login_headers(client, "charlie")

    blocked = client.get(
        "/api/cognix/projects/project-collab-1/realtime/blueprint",
        headers = charlie_headers,
    )
    assert blocked.status_code == 404

    forbidden_conflict = client.post(
        "/api/cognix/projects/project-collab-1/collaboration/conflict-plan",
        headers = bob_headers,
        json = {
            "resourceType": "document",
            "resourceId": "doc-1",
            "localRevision": "r2",
            "remoteRevision": "r3",
        },
    )
    assert forbidden_conflict.status_code == 403

    alice_headers = login_headers(client, "alice")
    allowed_conflict = client.post(
        "/api/cognix/projects/project-collab-1/collaboration/conflict-plan",
        headers = alice_headers,
        json = {
            "resourceType": "document",
            "resourceId": "doc-1",
            "baseRevision": "r1",
            "localRevision": "r2",
            "remoteRevision": "r3",
            "strategy": "merge_if_clean",
            "changes": [{"op": "replace", "path": "/title"}],
        },
    )
    assert allowed_conflict.status_code == 200
    plan = allowed_conflict.json()["conflictResolutionPlan"]
    assert plan["resolutionPolicy"]["automaticOverwriteAllowed"] is False
    assert plan["resolutionPolicy"]["projectFileWriteAllowedNow"] is False
    assert plan["conflict"]["revisionMismatchDetected"] is True
