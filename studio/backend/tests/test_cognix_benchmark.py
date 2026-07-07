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
from core.cognix import benchmark as cognix_benchmark
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


def _cpu_hardware() -> dict:
    return {
        "deviceBackend": "cpu",
        "cpuCount": 8,
        "memory": {"totalGb": 8.0, "availableGb": 5.5},
        "gpu": {"available": False, "devices": []},
    }


def _stub_benchmark() -> dict:
    return {
        "benchmarkVersion": "cognix_benchmark_v1",
        "mode": "quick",
        "hardware": _cpu_hardware(),
        "measurements": {
            "cpu": {"status": "complete", "score": 70.0},
            "memory": {"status": "complete", "score": 39.5},
            "disk": {"status": "skipped", "score": None},
            "gpu": {"status": "observed", "score": 0.0},
            "network": {"status": "skipped"},
        },
        "overallScore": 44.3,
        "estimatedTokensPerSecond": 11.2,
        "modelFitness": [],
        "optimizationPlan": {"quantization": "Q4"},
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "gpuStressTest": False,
            "temporaryDiskWrite": False,
        },
    }


def test_benchmark_estimates_model_fitness_without_model_side_effects(monkeypatch):
    monkeypatch.setattr(
        cognix_benchmark,
        "_run_cpu_probe",
        lambda _iterations = 120_000: {
            "status": "complete",
            "iterations": 60_000,
            "opsPerSecond": 2_400_000,
            "score": 57.1,
            "checksum": 123,
            "durationMs": 25.0,
        },
    )

    benchmark = cognix_benchmark.run_benchmark(
        hardware = _cpu_hardware(),
        include_disk = False,
    )

    assert benchmark["benchmarkVersion"] == "cognix_benchmark_v1"
    assert benchmark["measurements"]["network"]["status"] == "skipped"
    assert benchmark["sideEffects"]["modelLoad"] is False
    assert benchmark["sideEffects"]["generation"] is False
    assert benchmark["sideEffects"]["networkCall"] is False
    assert benchmark["sideEffects"]["gpuStressTest"] is False
    assert benchmark["optimizationPlan"]["quantization"] == "Q4"

    fitness = {item["modelId"]: item for item in benchmark["modelFitness"]}
    assert fitness["cognix-general-3b-q4"]["stars"] >= 3
    assert fitness["glm-700b"]["status"] == "blocked"
    assert benchmark["estimatedTokensPerSecond"] > 1


def test_benchmark_run_endpoint_persists_user_history_and_admin_view(client, monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_benchmark,
        "run_benchmark",
        lambda **_kwargs: _stub_benchmark(),
    )
    headers = login_headers(client, "alice", "alice-password-123")

    response = client.post(
        "/api/cognix/benchmark/run",
        headers = headers,
        json = {"mode": "quick", "includeDisk": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["runId"].startswith("bnc_")
    assert body["benchmark"]["sideEffects"]["modelLoad"] is False

    history = client.get("/api/cognix/benchmark/runs", headers = headers)
    assert history.status_code == 200
    run = history.json()["runs"][0]
    assert run["id"] == body["runId"]
    assert run["overallScore"] == 44.3
    assert run["benchmark"]["benchmarkVersion"] == "cognix_benchmark_v1"

    forbidden = client.get("/api/cognix/admin/benchmark-runs", headers = headers)
    assert forbidden.status_code == 403

    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")
    admin_history = client.get("/api/cognix/admin/benchmark-runs", headers = admin_headers)
    assert admin_history.status_code == 200
    assert admin_history.json()["runs"][0]["id"] == body["runId"]
