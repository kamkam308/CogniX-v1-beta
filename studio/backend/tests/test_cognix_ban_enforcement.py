import secrets
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage
from auth.authentication import create_access_token
from storage import cognix_db


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
    yield
    cognix_db._schema_ready = False


@pytest.fixture
def client():
    import main

    app = FastAPI()
    app.add_middleware(main.CognixBanMiddleware)
    app.add_middleware(main.CognixSecurityScanMiddleware, scan_prefixes = ("/api/cognix",))

    @app.get("/api/cognix/ping")
    async def ping():
        return {"ok": True}

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


def bearer(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(username)}"}


def record_ban(username: str) -> None:
    cognix_db.record_security_event(
        username = username,
        client_key = None,
        category = "sql_injection",
        severity = "critical",
        pattern_label = "SQL injection",
        method = "GET",
        path = "/api/cognix/ping",
        excerpt = "or 1=1",
        create_temporary_ban = True,
    )


def latest_ban() -> dict:
    bans = cognix_db.list_bans()
    assert bans
    return bans[0]


def expire_ban(ban_id: str) -> None:
    expired_at = (datetime.now(timezone.utc) - timedelta(hours = 1)).isoformat()
    conn = cognix_db.get_connection()
    try:
        conn.execute(
            "UPDATE cognix_bans SET temporary_until = ? WHERE id = ?",
            (expired_at, ban_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_active_ban_blocks_authenticated_api_reads(client):
    seed_accounts()
    record_ban("alice")

    response = client.get("/api/cognix/ping", headers = bearer("alice"))

    assert response.status_code == 403
    assert "administrator" in response.json()["detail"]


def test_pending_admin_review_ban_waits_for_admin_decision_even_after_temporary_time(client):
    seed_accounts()
    record_ban("alice")
    expire_ban(latest_ban()["id"])

    response = client.get("/api/cognix/ping", headers = bearer("alice"))

    assert response.status_code == 403
    assert "administrator" in response.json()["detail"]


def test_permanent_admin_ban_does_not_expire_with_temporary_time(client):
    seed_accounts()
    record_ban("alice")
    ban = latest_ban()
    updated = cognix_db.update_ban_status(
        ban["id"],
        "permanent",
        decided_by = storage.DEFAULT_ADMIN_USERNAME,
        admin_decision = "Confirmed malicious activity.",
    )

    assert updated is not None
    assert updated["status"] == "permanent"
    assert updated["temporary_until"] is None
    response = client.get("/api/cognix/ping", headers = bearer("alice"))
    assert response.status_code == 403


def test_cleared_admin_ban_unblocks_user(client):
    seed_accounts()
    record_ban("alice")
    ban = latest_ban()
    updated = cognix_db.update_ban_status(
        ban["id"],
        "cleared",
        decided_by = storage.DEFAULT_ADMIN_USERNAME,
        admin_decision = "False positive.",
    )

    assert updated is not None
    assert updated["status"] == "cleared"
    assert updated["temporary_until"] is None
    response = client.get("/api/cognix/ping", headers = bearer("alice"))
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_admin_can_still_access_api_when_ban_record_exists(client):
    seed_accounts()
    record_ban(storage.DEFAULT_ADMIN_USERNAME)

    response = client.get("/api/cognix/ping", headers = bearer(storage.DEFAULT_ADMIN_USERNAME))

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_encoded_query_attack_creates_ban_and_blocks_followup(client):
    response = client.get("/api/cognix/ping?q=or%201%3D1--")

    assert response.status_code == 403
    assert "Security threat detected" in response.json()["detail"]
    events = cognix_db.list_security_events()
    assert events
    assert events[0]["category"] == "sql_injection"

    followup = client.get("/api/cognix/ping")

    assert followup.status_code == 403
    assert "administrator" in followup.json()["detail"]


def test_admin_query_is_not_banned_by_security_scan(client):
    seed_accounts()

    response = client.get(
        "/api/cognix/ping?q=or%201%3D1--",
        headers = bearer(storage.DEFAULT_ADMIN_USERNAME),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert cognix_db.list_security_events() == []


def test_forged_admin_token_does_not_bypass_security_scan(client):
    seed_accounts()
    forged_token = jwt.encode(
        {"sub": storage.DEFAULT_ADMIN_USERNAME},
        "wrong-secret-that-is-long-enough-for-hs256",
        algorithm = "HS256",
    )

    response = client.get(
        "/api/cognix/ping?q=or%201%3D1--",
        headers = {"Authorization": f"Bearer {forged_token}"},
    )

    assert response.status_code == 403
    assert "Security threat detected" in response.json()["detail"]
