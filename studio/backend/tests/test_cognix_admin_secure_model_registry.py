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
from core.cognix import admin_secure_model_registry as cognix_admin_secure_model_registry
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


def test_secure_model_registry_blueprint_schema_module_registry_and_surface_contract():
    blueprint = cognix_admin_secure_model_registry.build_secure_model_registry_blueprint()
    assert blueprint["secureModelRegistryVersion"] == "cognix_secure_model_registry_v1"
    assert blueprint["modelApprovalServiceVersion"] == "cognix_model_approval_service_v1"
    assert blueprint["modelLicenseCheckerVersion"] == "cognix_model_license_checker_v1"
    assert blueprint["modelChecksumVerifierVersion"] == "cognix_model_checksum_verifier_v1"
    assert blueprint["services"] == [
        "SecureModelRegistry",
        "ModelApprovalService",
        "ModelLicenseChecker",
        "ModelChecksumVerifier",
    ]
    assert {"approved_models", "blocked_models", "model_security_metadata"}.issubset(set(blueprint["tables"]))
    assert blueprint["sideEffects"]["networkCall"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_admin_secure_model_registry_columns(conn)
        approved_columns = {row[1] for row in conn.execute("PRAGMA table_info(approved_models)").fetchall()}
        blocked_columns = {row[1] for row in conn.execute("PRAGMA table_info(blocked_models)").fetchall()}
        metadata_columns = {row[1] for row in conn.execute("PRAGMA table_info(model_security_metadata)").fetchall()}
        assert {"model_id", "allowed_roles_json", "quantization_required", "local_only_required"}.issubset(
            approved_columns
        )
        assert {"model_id", "provider_type", "reason", "blocked_by"}.issubset(blocked_columns)
        assert {"model_id", "license", "source", "checksum", "checksum_verified", "risk_level"}.issubset(
            metadata_columns
        )
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    secure_registry = modules["cognix-enterprise-secure-model-registry"]
    assert "secure_model_registry" in secure_registry["capabilities"]
    assert "model_checksum_verifier" in secure_registry["capabilities"]
    assert "/api/cognix/admin/models/secure-registry/access-decision" in secure_registry["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/admin/models/secure-registry", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/admin/settings"]["status"] == "equivalent"
    assert routes["/admin/settings"]["matchedRoute"] == "/api/cognix/admin/models/secure-registry"


def test_secure_model_registry_routes_approve_block_and_decide_access():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_secure_model_registry_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    checksum = "sha256:" + ("a" * 64)
    approved = run_async(
        cognix_routes.admin_approve_secure_model(
            cognix_routes.AdminSecureModelApprovalRequest(
                modelId = "qwen-test:4b",
                displayName = "Qwen test 4B",
                providerType = "ollama",
                allowedRoles = ["CEO", "admin"],
                quantizationRequired = "Q4_K_M",
                localOnlyRequired = True,
                license = "Apache-2.0",
                source = "ollama",
                checksum = checksum,
                reason = "Approved local test model",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert approved["approvedModel"]["modelId"] == "qwen-test:4b"
    assert approved["modelSecurityMetadata"]["checksumVerified"] is True
    assert approved["sideEffects"]["approvedModelWrite"] is True
    assert approved["sideEffects"]["organizationSettingsWrite"] is True
    assert "qwen-test:4b" in approved["allowedModels"]

    settings = run_async(cognix_routes.admin_settings(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert "qwen-test:4b" in settings["settings"]["allowedModels"]

    allowed = run_async(
        cognix_routes.admin_secure_model_access_decision(
            cognix_routes.AdminSecureModelDecisionRequest(
                modelId = "qwen-test:4b",
                providerType = "ollama",
                role = "CEO",
                quantization = "Q4_K_M",
                localOnlyActive = True,
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert allowed["decision"]["allowed"] is True

    denied_role = run_async(
        cognix_routes.admin_secure_model_access_decision(
            cognix_routes.AdminSecureModelDecisionRequest(
                modelId = "qwen-test:4b",
                providerType = "ollama",
                role = "student",
                quantization = "Q4_K_M",
                localOnlyActive = True,
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert denied_role["decision"]["allowed"] is False
    assert "role_not_allowed_for_model" in denied_role["decision"]["reasons"]

    blocked = run_async(
        cognix_routes.admin_block_secure_model(
            cognix_routes.AdminSecureModelBlockRequest(
                modelId = "gpt-4o",
                providerType = "openai",
                reason = "External model blocked by enterprise registry",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert blocked["blockedModel"]["modelId"] == "gpt-4o"
    assert blocked["sideEffects"]["blockedModelWrite"] is True
    assert "gpt-4o" not in blocked["allowedModels"]

    denied_block = run_async(
        cognix_routes.admin_secure_model_access_decision(
            cognix_routes.AdminSecureModelDecisionRequest(
                modelId = "gpt-4o",
                providerType = "openai",
                role = "CEO",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert denied_block["decision"]["allowed"] is False
    assert "model_blocked_by_secure_registry" in denied_block["decision"]["reasons"]
    assert "admin_secure_model_blocked" in audit_actions
