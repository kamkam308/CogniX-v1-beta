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
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db, providers_db
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
    monkeypatch.setattr(providers_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()
    yield
    cognix_db._schema_ready = False
    providers_db._schema_ready = False
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
            "name": "CogniX benchmark",
            "instructions": "Prefer local Qwen for early MVP tests.",
            "archived": False,
            "createdAt": 1000,
            "updatedAt": 2000,
        },
        owner_username = owner_username,
    )


def test_project_default_model_can_be_set_listed_read_and_deleted(client):
    seed_accounts()
    seed_project()
    headers = login_headers(client, "alice", "alice-password-123")

    response = client.put(
        "/api/cognix/projects/project-alice-1/default-model",
        headers = headers,
        json = {
            "modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "label": "Ollama Qwen 4B",
            "providerType": "ollama",
            "providerId": "b6878df754d543b1",
        },
    )

    assert response.status_code == 200
    default_model = response.json()["defaultModel"]
    assert default_model["projectId"] == "project-alice-1"
    assert default_model["ownerUsername"] == "alice"
    assert default_model["modelId"] == "huihui_ai/qwen3-vl-abliterated:4b-instruct"
    assert default_model["label"] == "Ollama Qwen 4B"
    assert default_model["providerType"] == "ollama"
    assert default_model["providerId"] == "b6878df754d543b1"

    read_response = client.get(
        "/api/cognix/projects/project-alice-1/default-model",
        headers = headers,
    )
    assert read_response.status_code == 200
    assert read_response.json()["defaultModel"]["modelId"] == default_model["modelId"]

    list_response = client.get("/api/cognix/project-model-defaults", headers = headers)
    assert list_response.status_code == 200
    assert [item["projectId"] for item in list_response.json()["defaults"]] == ["project-alice-1"]

    delete_response = client.delete(
        "/api/cognix/projects/project-alice-1/default-model",
        headers = headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    empty_response = client.get(
        "/api/cognix/projects/project-alice-1/default-model",
        headers = headers,
    )
    assert empty_response.status_code == 200
    assert empty_response.json()["defaultModel"] is None


def test_project_default_model_is_limited_to_project_owner(client):
    seed_accounts()
    seed_project(owner_username = "alice")
    bob_headers = login_headers(client, "bob", "bob-password-123")

    response = client.put(
        "/api/cognix/projects/project-alice-1/default-model",
        headers = bob_headers,
        json = {
            "modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "label": "Ollama Qwen 4B",
        },
    )

    assert response.status_code == 404
    assert cognix_db.get_project_model_default("project-alice-1") is None


def test_project_default_model_requires_authentication(client):
    response = client.get("/api/cognix/project-model-defaults")

    assert response.status_code in {401, 403}
