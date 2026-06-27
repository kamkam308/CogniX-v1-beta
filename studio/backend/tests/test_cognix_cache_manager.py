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
from core.cognix import cache_manager
from core.cognix import hardware as cognix_hardware
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
    cache_manager.reset_cache_state()
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()
    yield
    cache_manager.reset_cache_state()
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


def _cpu_hardware(available_gb: float = 6.0, total_gb: float = 8.0) -> dict:
    return {
        "deviceBackend": "cpu",
        "cpuCount": 8,
        "memory": {"totalGb": total_gb, "availableGb": available_gb},
        "gpu": {"available": False, "devices": []},
    }


def test_small_local_policy_keeps_one_resident_model():
    state = cache_manager.build_cache_state(
        _cpu_hardware(),
        active_model = "qwen:4b",
        loaded_models = ["qwen:4b", "code:3b"],
        runtime_type = "ollama",
        now = 1000.0,
    )

    assert state["policy"]["tier"] == "small_local"
    assert state["policy"]["maxResidentModels"] == 1
    assert state["policy"]["evictionStrategy"] == "lru"
    assert any(action["type"] == "would_unload_lru" for action in state["actions"])
    assert all(action["automatic"] is False for action in state["actions"])


def test_project_scope_uses_longer_idle_timeout_and_tracks_last_use():
    cache_manager.mark_model_used(
        "qwen:4b",
        runtime_type = "ollama",
        project_id = "project-code",
        now = 1000.0,
    )

    state = cache_manager.build_cache_state(
        _cpu_hardware(),
        active_model = "qwen:4b",
        loaded_models = ["qwen:4b"],
        runtime_type = "ollama",
        project_id = "project-code",
        now = 1300.0,
    )

    assert state["policy"]["idleTimeoutSeconds"] == 900
    resident = state["residentModels"][0]
    assert resident["projectId"] == "project-code"
    assert resident["idleForSeconds"] == 300
    assert resident["secondsUntilIdle"] == 600


def test_cache_endpoint_returns_authenticated_runtime_policy(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware())
    monkeypatch.setattr(
        cognix_routes,
        "_current_model_cache_runtime",
        lambda: {
            "runtimeType": "ollama",
            "activeModel": "qwen:4b",
            "loadedModels": ["qwen:4b"],
            "loadingModels": [],
        },
    )

    response = client.get(
        "/api/cognix/models/cache?project_id=project-code",
        headers = headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    cache = body["cache"]
    assert cache["managerVersion"] == "model_cache_manager_v1"
    assert cache["mode"] == "observe_only"
    assert cache["policy"]["idleTimeoutSeconds"] == 900
    assert cache["runtime"]["activeModel"] == "qwen:4b"
