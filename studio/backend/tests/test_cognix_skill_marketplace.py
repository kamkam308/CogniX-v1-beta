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
from core.cognix import skill_marketplace
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


def test_skill_marketplace_blueprint_declares_services_and_tables():
    blueprint = skill_marketplace.build_skill_marketplace_blueprint()

    assert blueprint["skillMarketplaceVersion"] == "cognix_skill_marketplace_service_v1"
    assert {
        "SkillMarketplaceService",
        "SkillApprovalService",
        "SkillVersionManager",
    }.issubset(blueprint["services"])
    assert blueprint["tables"] == ["shared_skills", "skill_approvals", "skill_usage_logs"]
    assert blueprint["sideEffects"]["skillExecution"] is False
    assert blueprint["sideEffects"]["secretRead"] is False


def test_skill_marketplace_publish_approve_and_usage_flow(client: TestClient):
    seed_accounts()
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")

    publish_response = client.post(
        "/api/cognix/skills/marketplace/skills",
        json = {
            "displayName": "Skill audit code",
            "category": "code",
            "instructions": "Priorise bugs, regressions, securite et tests.",
            "allowedRoles": ["admin", "ceo"],
        },
        headers = admin_headers,
    )
    assert publish_response.status_code == 200
    body = publish_response.json()
    skill_id = body["sharedSkill"]["id"]
    assert body["sharedSkill"]["status"] == "approved"
    assert body["sideEffects"]["skillWrite"] is True
    assert body["sideEffects"]["approvalWrite"] is True

    usage_response = client.post(
        "/api/cognix/skills/marketplace/usage",
        json = {"skillId": skill_id, "action": "use"},
        headers = admin_headers,
    )
    assert usage_response.status_code == 200
    usage_body = usage_response.json()
    assert usage_body["skillUsagePlan"]["allowed"] is True
    assert usage_body["usageLog"]["skillId"] == skill_id
    assert usage_body["sideEffects"]["usageLogWrite"] is True

    catalog_response = client.get("/api/cognix/skills/marketplace", headers = admin_headers)
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()["skillMarketplaceCatalog"]
    assert catalog["summary"]["skillCount"] >= 6
    assert catalog["summary"]["approvedCount"] >= 6
    assert any(item["id"] == skill_id for item in catalog["skills"])

    assert len(cognix_db.list_skill_approvals()) == 1
    assert len(cognix_db.list_skill_usage_logs(skill_id = skill_id)) == 1


def test_skill_marketplace_blocks_non_admin_approval_and_unapproved_usage(client: TestClient):
    seed_accounts()
    alice_headers = login_headers(client, "alice", "alice-password-123")
    admin_headers = login_headers(client, storage.DEFAULT_ADMIN_USERNAME, "admin-password-123")

    publish_response = client.post(
        "/api/cognix/skills/marketplace/skills",
        json = {
            "displayName": "Skill support client",
            "category": "support",
            "instructions": "Diagnostiquer, proposer une solution, escalader si besoin.",
            "allowedRoles": ["user"],
        },
        headers = alice_headers,
    )
    assert publish_response.status_code == 200
    skill_id = publish_response.json()["sharedSkill"]["id"]
    assert publish_response.json()["sharedSkill"]["status"] == "pending_approval"

    blocked_usage = client.post(
        "/api/cognix/skills/marketplace/usage",
        json = {"skillId": skill_id, "action": "use"},
        headers = alice_headers,
    )
    assert blocked_usage.status_code == 403
    assert "skill_not_approved" in blocked_usage.json()["detail"]["blockedReasons"]

    denied_approval = client.patch(
        f"/api/cognix/skills/marketplace/skills/{skill_id}/approval",
        json = {"status": "approved"},
        headers = alice_headers,
    )
    assert denied_approval.status_code == 403

    approve_response = client.patch(
        f"/api/cognix/skills/marketplace/skills/{skill_id}/approval",
        json = {"status": "approved"},
        headers = admin_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["sharedSkill"]["status"] == "approved"

    allowed_usage = client.post(
        "/api/cognix/skills/marketplace/usage",
        json = {"skillId": skill_id, "action": "use"},
        headers = alice_headers,
    )
    assert allowed_usage.status_code == 200
    assert allowed_usage.json()["skillUsagePlan"]["allowed"] is True
