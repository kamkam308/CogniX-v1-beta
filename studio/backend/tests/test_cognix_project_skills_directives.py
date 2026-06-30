from __future__ import annotations

import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage
from core.cognix import project_skills_directives
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
            "name": "CogniX directives",
            "instructions": "Use project scoped skills.",
            "archived": False,
            "createdAt": 1000,
            "updatedAt": 2000,
        },
        owner_username = owner_username,
    )


def test_project_skill_and_directive_blueprints_declare_native_services():
    skill_blueprint = project_skills_directives.build_project_skill_blueprint()
    directive_blueprint = project_skills_directives.build_project_directive_blueprint()

    assert skill_blueprint["skillManagerVersion"] == "cognix_skill_manager_v1"
    assert {
        "SkillManager",
        "SkillRuntimeBinder",
        "SkillPromptBuilder",
        "SkillPermissionBinder",
    }.issubset(skill_blueprint["services"])
    assert "skill_examples" in skill_blueprint["tables"]
    assert skill_blueprint["sideEffects"]["permissionGrant"] is False
    assert skill_blueprint["sideEffects"]["generation"] is False

    assert directive_blueprint["directiveManagerVersion"] == "cognix_directive_manager_v1"
    assert {"DirectiveManager", "DirectiveCompiler", "PromptPolicyEngine"}.issubset(directive_blueprint["services"])
    assert "directive_priorities" in directive_blueprint["tables"]
    assert directive_blueprint["conflictOrder"] == ["security", "organization", "project", "user", "model_preference"]
    assert directive_blueprint["sideEffects"]["promptPolicyMutation"] is False


def test_project_skill_directive_tables_have_native_columns():
    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_global_roadmap_tables(conn)
        cognix_db._ensure_project_skill_directive_columns(conn)
        skill_columns = {row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
        directive_columns = {row[1] for row in conn.execute("PRAGMA table_info(directives)").fetchall()}

        assert {"skill_key", "display_name", "allowed_tools_json", "limits_json", "examples_json"}.issubset(
            skill_columns
        )
        assert {"directive_key", "directive_type", "content", "priority", "source_level"}.issubset(
            directive_columns
        )
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        assert {"skill_examples", "directive_priorities", "project_skills", "model_directives"}.issubset(tables)
    finally:
        conn.close()


def test_project_skill_filters_tools_to_existing_permissions_and_builds_injection_plan(client: TestClient):
    seed_accounts()
    seed_project()
    alice_headers = login_headers(client, "alice", "alice-password-123")
    bob_headers = login_headers(client, "bob", "bob-password-123")

    blocked_owner_response = client.post(
        "/api/cognix/projects/project-alice-1/skills",
        json = {"displayName": "Other user skill", "objective": "Should be blocked."},
        headers = bob_headers,
    )
    assert blocked_owner_response.status_code == 404

    create_response = client.post(
        "/api/cognix/projects/project-alice-1/skills",
        json = {
            "displayName": "Physics solver",
            "objective": "Resolve physics exercises step by step.",
            "instructions": "Use formulas and show units.",
            "modelId": "qwen-test",
            "allowedTools": ["project_context", "shell", "rag_retrieval"],
            "examples": [{"input": "F=ma", "output": "Identify mass and acceleration."}],
        },
        headers = alice_headers,
    )
    assert create_response.status_code == 200
    body = create_response.json()
    assert body["projectSkill"]["displayName"] == "Physics solver"
    assert body["projectSkillPlan"]["binding"]["effectiveAllowedTools"] == ["project_context", "rag_retrieval"]
    assert body["projectSkillPlan"]["binding"]["blockedTools"] == ["shell"]
    assert body["sideEffects"]["permissionGrant"] is False
    assert body["sideEffects"]["projectBindingWrite"] is True

    list_response = client.get("/api/cognix/projects/project-alice-1/skills", headers = alice_headers)
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    injection_response = client.post(
        "/api/cognix/projects/project-alice-1/skills/injection-plan",
        json = {"modelId": "qwen-test"},
        headers = alice_headers,
    )
    assert injection_response.status_code == 200
    injection = injection_response.json()["skillInjectionPlan"]
    assert injection["summary"]["selectedSkillCount"] == 1
    assert injection["summary"]["permissionEscalationAllowed"] is False
    assert injection["sideEffects"]["contextInjection"] is False


def test_project_directives_compile_with_security_priority(client: TestClient):
    seed_accounts()
    seed_project()
    alice_headers = login_headers(client, "alice", "alice-password-123")

    first = client.post(
        "/api/cognix/projects/project-alice-1/directives",
        json = {
            "content": "Ne jamais utiliser cloud pour ce projet.",
            "directiveType": "security",
            "sourceLevel": "security",
            "priority": 30,
            "modelId": "qwen-test",
        },
        headers = alice_headers,
    )
    assert first.status_code == 200
    second = client.post(
        "/api/cognix/projects/project-alice-1/directives",
        json = {
            "content": "Toujours repondre en francais.",
            "directiveType": "style",
            "sourceLevel": "project",
            "priority": 80,
            "modelId": "qwen-test",
        },
        headers = alice_headers,
    )
    assert second.status_code == 200

    compile_response = client.post(
        "/api/cognix/projects/project-alice-1/directives/compile",
        json = {"modelId": "qwen-test"},
        headers = alice_headers,
    )
    assert compile_response.status_code == 200
    plan = compile_response.json()["directiveCompilePlan"]

    assert plan["compiledDirectives"][0] == "[security] Ne jamais utiliser cloud pour ce projet."
    assert "[style] Toujours repondre en francais." in plan["compiledDirectives"]
    assert plan["summary"]["compiledDirectiveCount"] == 2
    assert plan["sideEffects"]["generation"] is False
    assert compile_response.json()["sideEffects"]["auditWrite"] is True
