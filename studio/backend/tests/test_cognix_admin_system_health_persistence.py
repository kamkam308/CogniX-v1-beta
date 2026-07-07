from __future__ import annotations

import asyncio
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage as auth_storage
from core.cognix import admin_security as cognix_admin_security
from core.cognix import api_surface as cognix_api_surface
from core.cognix import module_registry as cognix_module_registry
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(tmp_path / "project_workspaces"))
    monkeypatch.setattr(auth_storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth_storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(auth_storage, "_bootstrap_password", None)
    monkeypatch.setattr(auth_storage, "_api_key_pbkdf2_salt_cache", None)
    monkeypatch.setattr(cognix_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False


def run_async(coro):
    return asyncio.run(coro)


def seed_accounts() -> None:
    auth_storage.create_initial_user(
        username = auth_storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    auth_storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )


def test_system_health_blueprint_schema_and_module_contract_declares_full_pipeline():
    blueprint = cognix_admin_security.build_system_health_blueprint()
    assert blueprint["healthVersion"] == "cognix_system_health_v1"
    assert blueprint["workerMonitorVersion"] == "cognix_worker_monitor_v1"
    assert blueprint["runtimeHealthCheckerVersion"] == "cognix_runtime_health_checker_v1"
    assert blueprint["services"] == ["SystemHealthService", "WorkerMonitor", "RuntimeHealthChecker"]
    assert {"system_health_snapshots", "service_health_events"}.issubset(set(blueprint["tables"]))
    assert {"queue_jobs", "average_latency", "model_errors", "worker_status", "storage"}.issubset(
        set(blueprint["metrics"])
    )
    assert blueprint["sideEffects"]["snapshotWrite"] is False
    assert blueprint["sideEffects"]["serviceEventWrite"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_admin_system_health_columns(conn)
        snapshot_columns = {row[1] for row in conn.execute("PRAGMA table_info(system_health_snapshots)").fetchall()}
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(service_health_events)").fetchall()}
        assert {"overall_status", "queue_json", "latency_json", "storage_json", "health_json"}.issubset(
            snapshot_columns
        )
        assert {"service_id", "event_type", "severity", "message", "event_json"}.issubset(event_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    security = modules["cognix-admin-security-center"]
    assert "system_health_service" in security["capabilities"]
    assert "worker_monitor" in security["capabilities"]
    assert "runtime_health_checker" in security["capabilities"]
    assert "system_health_snapshots" in security["capabilities"]
    assert "/api/cognix/admin/system-health/snapshot" in security["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/system-health/snapshots", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/system-health"]["status"] == "equivalent"
    assert routes["/admin/system-health"]["matchedRoute"] == "/api/cognix/admin/system-health/snapshots"


def test_system_health_snapshot_persists_history_and_service_events():
    seed_accounts()
    cognix_db.record_security_event(
        username = "alice",
        client_key = "127.0.0.1",
        category = "sql_injection",
        severity = "critical",
        pattern_label = "SQL injection",
        method = "POST",
        path = "/api/auth/login",
        excerpt = "or 1=1",
        create_temporary_ban = True,
    )
    cognix_db.create_token_usage_event(
        username = "alice",
        model_id = "qwen-test:4b",
        provider = "ollama",
        input_tokens = 12,
        output_tokens = 8,
        latency_ms = 6200,
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_system_health_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    health_response = run_async(
        cognix_routes.admin_system_health(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    health = health_response["systemHealth"]
    assert health["healthVersion"] == "cognix_system_health_v1"
    assert {"queue", "latency", "storage", "vram", "activeServices"}.issubset(set(health["metrics"]))
    assert health["metrics"]["latency"]["averageLatencyMs"] == 6200
    assert health["sideEffects"]["snapshotWrite"] is False

    snapshot_response = run_async(
        cognix_routes.admin_system_health_snapshot(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    assert snapshot_response["snapshot"]["overallStatus"] in {"yellow", "red"}
    assert snapshot_response["snapshot"]["health"]["healthVersion"] == "cognix_system_health_v1"
    assert snapshot_response["snapshot"]["latency"]["averageLatencyMs"] == 6200
    assert snapshot_response["serviceHealthEvents"]
    assert snapshot_response["sideEffects"]["snapshotWrite"] is True
    assert snapshot_response["sideEffects"]["serviceEventWrite"] is True
    assert snapshot_response["sideEffects"]["auditWrite"] is True

    history = run_async(
        cognix_routes.admin_system_health_snapshots(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    events = run_async(
        cognix_routes.admin_system_health_service_events(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert history["snapshots"][0]["id"] == snapshot_response["snapshot"]["id"]
    assert events["serviceHealthEvents"][0]["eventType"] == "snapshot"
    assert "admin_system_health_snapshot_created" in audit_actions
