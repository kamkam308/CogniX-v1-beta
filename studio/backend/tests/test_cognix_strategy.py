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
from core.cognix import hardware as cognix_hardware
from core.cognix import registry as cognix_registry
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


def login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json = {"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _cpu_hardware(available_gb: float = 6.0) -> dict:
    return {
        "deviceBackend": "cpu",
        "cpuCount": 8,
        "memory": {"totalGb": 7.94, "availableGb": available_gb},
        "gpu": {"available": False, "devices": []},
    }


def _benchmark_payload() -> dict:
    return {
        "benchmarkVersion": "cognix_benchmark_v1",
        "mode": "quick",
        "hardware": _cpu_hardware(available_gb = 6.0),
        "measurements": {
            "cpu": {"status": "complete", "score": 68.0},
            "memory": {"status": "complete", "score": 52.0},
            "disk": {"status": "skipped", "score": None},
            "gpu": {"status": "observed", "score": 0.0},
            "network": {"status": "skipped"},
        },
        "overallScore": 55.0,
        "estimatedTokensPerSecond": 14.5,
        "modelFitness": [
            {
                "modelId": "cognix-code-4b-q4",
                "label": "CogniX Code 4B Q4",
                "status": "recommended",
                "stars": 4,
                "estimatedTokensPerSecond": 14.5,
            },
            {
                "modelId": "glm-700b",
                "label": "GLM 700B",
                "status": "blocked",
                "stars": 0,
                "estimatedTokensPerSecond": 0.0,
            },
        ],
        "optimizationPlan": {
            "expectedLocalSpeed": "balanced",
            "quantization": "Q4_or_Q5",
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "gpuStressTest": False,
            "temporaryDiskWrite": False,
        },
    }


def test_strategy_recommends_default_ollama_qwen(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware())
    monkeypatch.setattr(
        cognix_registry,
        "_ollama_models",
        lambda _base_url: (True, [cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID]),
    )

    response = client.get("/api/cognix/strategy", headers = headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["phase"] == "mvp_core_local"
    assert body["recommendation"]["readiness"] == "ready"
    assert body["recommendation"]["executionMode"] == "local"
    assert body["recommendation"]["providerType"] == "ollama"
    assert body["recommendation"]["providerId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_PROVIDER_ID
    assert body["recommendation"]["modelId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
    assert body["providers"]["ollama"]["reachable"] is True
    assert body["providers"]["ollama"]["hasDefaultModel"] is True


def test_strategy_uses_latest_benchmark_run_for_recommendation(client, monkeypatch):
    seed_accounts()
    benchmark_run = cognix_db.create_benchmark_run("alice", _benchmark_payload())
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware())
    monkeypatch.setattr(
        cognix_registry,
        "_ollama_models",
        lambda _base_url: (True, [cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID]),
    )

    response = client.get("/api/cognix/strategy", headers = headers)

    assert response.status_code == 200
    body = response.json()
    assert body["latestBenchmark"]["id"] == benchmark_run["id"]
    assert body["recommendation"]["benchmark"]["available"] is True
    assert body["recommendation"]["benchmark"]["runId"] == benchmark_run["id"]
    assert body["recommendation"]["benchmark"]["bestLocalModel"]["modelId"] == "cognix-code-4b-q4"
    assert body["recommendation"]["confidence"] >= 0.87


def test_strategy_keeps_qwen_available_when_memory_is_tight(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware(available_gb = 3.3))
    monkeypatch.setattr(
        cognix_registry,
        "_ollama_models",
        lambda _base_url: (True, [cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID]),
    )

    response = client.get("/api/cognix/strategy", headers = headers)

    assert response.status_code == 200
    recommendation = response.json()["recommendation"]
    assert recommendation["readiness"] == "ready_with_caution"
    assert recommendation["modelId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
    assert recommendation["memoryFit"]["level"] == "tight"
    assert any("RAM disponible serree" in warning for warning in recommendation["warnings"])


def test_strategy_reports_ollama_service_unreachable(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware())
    monkeypatch.setattr(cognix_registry, "_ollama_models", lambda _base_url: (False, []))

    response = client.get("/api/cognix/strategy", headers = headers)

    assert response.status_code == 200
    recommendation = response.json()["recommendation"]
    assert recommendation["readiness"] == "service_unreachable"
    assert recommendation["providerType"] == "ollama"
    assert recommendation["modelId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
    assert any("Ollama non joignable" in warning for warning in recommendation["warnings"])


def test_hardware_profile_endpoint_returns_authenticated_profile(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware(available_gb = 5.5))

    response = client.get("/api/cognix/hardware/profile", headers = headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["hardware"]["deviceBackend"] == "cpu"
    assert body["hardware"]["memory"]["availableGb"] == 5.5
    assert body["hardware"]["gpu"]["available"] is False


def test_model_recommendation_endpoint_returns_recommender_output(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware(available_gb = 5.5))
    monkeypatch.setattr(
        cognix_registry,
        "_ollama_models",
        lambda _base_url: (True, [cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID]),
    )

    response = client.get("/api/cognix/models/recommendation", headers = headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["hardware"]["memory"]["availableGb"] == 5.5
    assert body["recommendation"]["readiness"] == "ready"
    assert body["recommendation"]["modelId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
    assert body["providers"]["ollama"]["hasDefaultModel"] is True


def test_model_recommendation_uses_latest_benchmark_run(client, monkeypatch):
    seed_accounts()
    benchmark_run = cognix_db.create_benchmark_run("alice", _benchmark_payload())
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(cognix_hardware, "get_hardware_profile", lambda: _cpu_hardware(available_gb = 5.5))
    monkeypatch.setattr(
        cognix_registry,
        "_ollama_models",
        lambda _base_url: (True, [cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID]),
    )

    response = client.get("/api/cognix/models/recommendation", headers = headers)

    assert response.status_code == 200
    body = response.json()
    assert body["latestBenchmark"]["id"] == benchmark_run["id"]
    assert body["recommendation"]["benchmark"]["available"] is True
    assert body["recommendation"]["benchmark"]["runId"] == benchmark_run["id"]
    assert body["recommendation"]["benchmark"]["overallScore"] == 55.0
    assert body["recommendation"]["benchmark"]["bestLocalModel"]["modelId"] == "cognix-code-4b-q4"


def test_model_registry_endpoint_returns_native_registry(client, monkeypatch):
    seed_accounts()
    headers = login_headers(client, "alice", "alice-password-123")
    monkeypatch.setattr(
        cognix_registry,
        "_ollama_models",
        lambda _base_url: (True, [cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID]),
    )

    response = client.get("/api/cognix/models/registry", headers = headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    registry = body["registry"]
    assert registry["registryVersion"] == "local_model_registry_v1"
    assert registry["defaultModelId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
    assert registry["recommendedModelId"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
    assert registry["ollama"]["hasDefaultModel"] is True
    assert registry["models"][0]["id"] == cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID
