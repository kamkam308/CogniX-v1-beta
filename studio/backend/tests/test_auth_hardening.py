import secrets
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import hashing, storage
from routes import auth as auth_routes


@pytest.fixture(autouse = True)
def isolated_auth_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(storage, "_bootstrap_password", None)
    monkeypatch.setattr(storage, "_api_key_pbkdf2_salt_cache", None)
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()
    yield
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auth_routes.router, prefix = "/api/auth")
    return TestClient(app)


def seed_admin() -> None:
    storage.create_initial_user(
        username = storage.DEFAULT_ADMIN_USERNAME,
        password = "human-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )


def seed_user(username = "alice", password = "correct-password-123") -> None:
    storage.create_user(
        username = username,
        email = f"{username}@example.com",
        password = password,
    )


def test_auth_status_exposes_cognix_admin_before_initialization(client):
    response = client.get("/api/auth/status")

    assert response.status_code == 200
    body = response.json()
    assert body["initialized"] is False
    assert body["default_username"] == "kamil"


def test_default_admin_bootstrap_uses_cognix_username():
    created = storage.ensure_default_admin()

    assert created is True
    assert storage.DEFAULT_ADMIN_USERNAME == "kamil"
    assert storage.get_user_and_secret("kamil") is not None
    assert storage.get_user_and_secret("unsloth") is None


def test_ceo_plan_is_training_operator_without_admin_role():
    storage.create_user(
        username = "ceo_user",
        email = "ceo@example.com",
        password = "human-password-123",
        plan = storage.CEO_PLAN,
    )

    profile = storage.get_user_profile("ceo_user")

    assert profile is not None
    assert profile["role"] == "user"
    assert profile["plan"] == storage.CEO_PLAN
    assert storage.is_admin("ceo_user") is False
    assert storage.has_ceo_training_entitlement("ceo_user", profile) is True
    assert storage.is_training_operator("ceo_user") is True


def test_ceo_role_and_account_alias_are_training_operators_without_admin_role():
    storage.create_user(
        username = "cloud_lead",
        email = "cloud-lead@example.com",
        password = "human-password-123",
        role = "ceo",
    )
    storage.create_user(
        username = "CEO",
        email = "ceo-account@example.com",
        password = "human-password-123",
    )

    role_profile = storage.get_user_profile("cloud_lead")
    alias_profile = storage.get_user_profile("CEO")

    assert role_profile is not None
    assert role_profile["role"] == "ceo"
    assert storage.is_admin("cloud_lead") is False
    assert storage.is_training_operator("cloud_lead") is True

    assert alias_profile is not None
    assert alias_profile["role"] == "user"
    assert storage.is_admin("CEO") is False
    assert storage.has_ceo_training_entitlement("CEO", alias_profile) is True
    assert storage.is_training_operator("CEO") is True


def test_free_user_is_not_training_operator():
    seed_user("freeuser")

    assert storage.has_ceo_training_entitlement("freeuser") is False
    assert storage.is_training_operator("freeuser") is False


def test_auth_status_does_not_disclose_admin_username_after_initialization(client):
    seed_admin()

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    body = response.json()
    assert body["initialized"] is True
    assert body["default_username"] == ""


def expire_login_lockout(username: str) -> None:
    conn = storage.get_connection()
    try:
        conn.execute(
            "UPDATE auth_user SET login_lockout_until = ? WHERE username = ?",
            (datetime(2000, 1, 1, tzinfo = timezone.utc).isoformat(), username),
        )
        conn.commit()
    finally:
        conn.close()


def test_login_identifier_sql_injection_does_not_bypass_password(client):
    seed_admin()

    response = client.post(
        "/api/auth/login",
        json = {
            "username": "unsloth' OR 1=1 --",
            "password": "human-password-123",
        },
    )

    assert response.status_code == 401


def test_register_rejects_sqlish_username(client):
    response = client.post(
        "/api/auth/register",
        json = {
            "username": "bad' OR 1=1 --",
            "email": "bad@example.com",
            "password": "human-password-123",
        },
    )

    assert response.status_code == 400
    assert "letters, numbers" in response.json()["detail"]


def test_register_rejects_weak_password(client):
    response = client.post(
        "/api/auth/register",
        json = {
            "username": "weakpass",
            "email": "weakpass@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 400
    assert "common password" in response.json()["detail"]


def test_register_rejects_password_based_on_identifier(client):
    response = client.post(
        "/api/auth/register",
        json = {
            "username": "alice",
            "email": "alice@example.com",
            "password": "Alice2026!",
        },
    )

    assert response.status_code == 400
    assert "username or email" in response.json()["detail"]


def test_register_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "_REGISTER_IP_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_routes, "_REGISTER_WINDOW_SECONDS", 60.0)

    for idx in range(2):
        response = client.post(
            "/api/auth/register",
            json = {
                "username": f"user{idx}",
                "email": f"user{idx}@example.com",
                "password": "human-password-123",
            },
        )
        assert response.status_code == 200

    blocked = client.post(
        "/api/auth/register",
        json = {
            "username": "user3",
            "email": "user3@example.com",
            "password": "human-password-123",
        },
    )

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_legacy_password_hash_is_rehashed_after_successful_login(client):
    seed_user()
    legacy_salt = "legacy-salt"
    legacy_digest = hashlib.pbkdf2_hmac(
        "sha256",
        b"correct-password-123",
        legacy_salt.encode("utf-8"),
        hashing.LEGACY_PBKDF2_ITERATIONS,
    ).hex()
    conn = storage.get_connection()
    try:
        conn.execute(
            """
            UPDATE auth_user
            SET password_salt = ?, password_hash = ?
            WHERE username = ?
            """,
            (legacy_salt, legacy_digest, "alice"),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "correct-password-123"},
    )
    assert response.status_code == 200

    stored = storage.get_user_and_secret("alice")
    assert stored is not None
    _salt, upgraded_hash, _jwt_secret, _must_change = stored
    assert upgraded_hash != legacy_digest
    assert upgraded_hash.startswith(f"{hashing.HASH_ALGORITHM}${hashing.PBKDF2_ITERATIONS}$")
    assert hashing.needs_rehash(upgraded_hash) is False


def test_login_sets_http_only_refresh_cookie_and_refresh_uses_cookie(client):
    seed_admin()

    login = client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )

    assert login.status_code == 200
    set_cookie = login.headers["set-cookie"].lower()
    assert "cognix_refresh_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    refreshed = client.post("/api/auth/refresh", json = {})

    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert "cognix_refresh_token=" in refreshed.headers["set-cookie"].lower()


def test_refresh_rejects_oversized_token_before_storage_lookup(client):
    response = client.post("/api/auth/refresh", json = {"refresh_token": "x" * 4096})

    assert response.status_code == 422


def test_desktop_login_rejects_oversized_secret(client):
    response = client.post("/api/auth/desktop-login", json = {"secret": "x" * 4096})

    assert response.status_code == 422


def test_api_key_payload_limits_are_enforced(client):
    seed_admin()
    login = client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    long_name = client.post(
        "/api/auth/api-keys",
        json = {"name": "x" * 81},
        headers = headers,
    )
    bad_expiry = client.post(
        "/api/auth/api-keys",
        json = {"name": "valid", "expires_in_days": -1},
        headers = headers,
    )

    assert long_name.status_code == 422
    assert bad_expiry.status_code == 422


def test_api_key_cannot_access_web_session_routes(client):
    seed_admin()
    login = client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )
    token = login.json()["access_token"]
    jwt_headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/auth/api-keys",
        json = {"name": "cli"},
        headers = jwt_headers,
    )
    api_key = created.json()["key"]
    api_headers = {"Authorization": f"Bearer {api_key}"}

    me = client.get("/api/auth/me", headers = api_headers)
    list_keys = client.get("/api/auth/api-keys", headers = api_headers)

    assert me.status_code == 403
    assert me.json()["detail"] == "Web session required"
    assert list_keys.status_code == 403
    assert list_keys.json()["detail"] == "Web session required"


def test_regular_user_cannot_access_admin_routes(client):
    seed_admin()
    seed_user()
    login = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "correct-password-123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    users = client.get("/api/auth/admin/users", headers = headers)
    unlock = client.post("/api/auth/admin/users/alice/unlock", headers = headers)

    assert users.status_code == 403
    assert users.json()["detail"] == "Admin access required"
    assert unlock.status_code == 403
    assert unlock.json()["detail"] == "Admin access required"


def test_admin_api_key_cannot_access_admin_routes(client):
    seed_admin()
    login = client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )
    jwt_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post(
        "/api/auth/api-keys",
        json = {"name": "cli"},
        headers = jwt_headers,
    )
    api_headers = {"Authorization": f"Bearer {created.json()['key']}"}

    users = client.get("/api/auth/admin/users", headers = api_headers)
    unlock = client.post("/api/auth/admin/users/alice/unlock", headers = api_headers)

    assert users.status_code == 403
    assert users.json()["detail"] == "Web session required"
    assert unlock.status_code == 403
    assert unlock.json()["detail"] == "Web session required"


def test_api_key_cannot_access_studio_inference_monitor():
    from routes import inference_router, inference_studio_router

    seed_admin()
    app = FastAPI()
    app.include_router(auth_routes.router, prefix = "/api/auth")
    app.include_router(inference_router, prefix = "/api/inference")
    app.include_router(inference_studio_router, prefix = "/api/inference")
    local_client = TestClient(app)
    login = local_client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )
    token = login.json()["access_token"]
    jwt_headers = {"Authorization": f"Bearer {token}"}
    created = local_client.post(
        "/api/auth/api-keys",
        json = {"name": "cli"},
        headers = jwt_headers,
    )
    api_key = created.json()["key"]

    monitor = local_client.get(
        "/api/inference/monitor",
        headers = {"Authorization": f"Bearer {api_key}"},
    )
    status = local_client.get(
        "/api/inference/status",
        headers = {"Authorization": f"Bearer {api_key}"},
    )

    assert monitor.status_code == 403
    assert monitor.json()["detail"] == "Web session required"
    assert status.status_code == 403
    assert status.json()["detail"] == "Web session required"


def test_change_password_wrong_current_password_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "_LOGIN_MAX_FAILS", 2)
    seed_admin()
    login = client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(2):
        response = client.post(
            "/api/auth/change-password",
            headers = headers,
            json = {
                "current_password": "wrong-password",
                "new_password": "new-human-password-123",
            },
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/auth/change-password",
        headers = headers,
        json = {
            "current_password": "wrong-password",
            "new_password": "new-human-password-123",
        },
    )

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_regular_user_password_failures_escalate_and_admin_can_unlock(client):
    seed_admin()
    seed_user()

    for _ in range(storage.LOGIN_FAILURES_BEFORE_LOCK - 1):
        response = client.post(
            "/api/auth/login",
            json = {"username": "alice", "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect password. To reset it, contact your administrator."

    first_lock = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "wrong-password"},
    )
    assert first_lock.status_code == 429
    assert int(first_lock.headers["Retry-After"]) >= 3590
    assert storage.get_login_lockout_state("alice")["loginLockoutLevel"] == 1

    expire_login_lockout("alice")
    second_lock = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "wrong-password"},
    )
    assert second_lock.status_code == 429
    assert int(second_lock.headers["Retry-After"]) >= 7190
    assert storage.get_login_lockout_state("alice")["loginLockoutLevel"] == 2

    expire_login_lockout("alice")
    permanent_lock = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "wrong-password"},
    )
    assert permanent_lock.status_code == 423
    assert permanent_lock.json()["detail"] == "Contact your administrator to unlock your account."

    still_locked = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "correct-password-123"},
    )
    assert still_locked.status_code == 423

    admin_login = client.post(
        "/api/auth/login",
        json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "human-password-123"},
    )
    token = admin_login.json()["access_token"]
    unlock = client.post(
        "/api/auth/admin/users/alice/unlock",
        headers = {"Authorization": f"Bearer {token}"},
    )
    assert unlock.status_code == 200
    assert unlock.json()["loginLocked"] is False

    success = client.post(
        "/api/auth/login",
        json = {"username": "alice", "password": "correct-password-123"},
    )
    assert success.status_code == 200


def test_admin_wrong_password_does_not_persistently_lock_account(client):
    seed_admin()

    for _ in range(storage.LOGIN_FAILURES_BEFORE_LOCK):
        response = client.post(
            "/api/auth/login",
            json = {"username": storage.DEFAULT_ADMIN_USERNAME, "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect password. To reset it, contact your administrator."

    state = storage.get_login_lockout_state(storage.DEFAULT_ADMIN_USERNAME)
    assert state["loginLocked"] is False
    assert state["loginLockoutLevel"] == 0
