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
from core.cognix import api_surface as cognix_api_surface
from core.cognix import module_registry as cognix_module_registry
from core.cognix import shared_knowledge_base as cognix_shared_knowledge_base
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
    auth_storage.create_user(
        username = "bob",
        email = "bob@example.com",
        password = "bob-password-123",
    )


def test_shared_knowledge_blueprint_schema_module_registry_and_surface_contract():
    blueprint = cognix_shared_knowledge_base.build_shared_knowledge_blueprint()
    assert blueprint["sharedKnowledgeBaseVersion"] == "cognix_shared_knowledge_base_v1"
    assert blueprint["organizationRagServiceVersion"] == "cognix_organization_rag_service_v1"
    assert blueprint["documentPermissionFilterVersion"] == "cognix_document_permission_filter_v1"
    assert blueprint["services"] == [
        "SharedKnowledgeBaseService",
        "OrganizationRAGService",
        "DocumentPermissionFilter",
    ]
    assert {"knowledge_bases", "knowledge_documents", "knowledge_chunks", "knowledge_permissions"}.issubset(
        set(blueprint["tables"])
    )
    assert blueprint["security"]["permissionFilteredRetrieval"] is True
    assert blueprint["sideEffects"]["embeddingCall"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_shared_knowledge_columns(conn)
        base_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_bases)").fetchall()}
        document_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_documents)").fetchall()}
        chunk_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()}
        permission_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_permissions)").fetchall()}
        assert {"name", "description", "owner_username", "visibility"}.issubset(base_columns)
        assert {"knowledge_base_id", "title", "content_text", "created_by"}.issubset(document_columns)
        assert {"document_id", "chunk_index", "text", "embedding_status"}.issubset(chunk_columns)
        assert {"subject_type", "subject_id", "permission", "granted_by"}.issubset(permission_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    shared = modules["cognix-shared-knowledge-base"]
    assert "shared_knowledge_base_service" in shared["capabilities"]
    assert "permission_filtered_retrieval" in shared["capabilities"]
    assert "/api/cognix/knowledge/shared/bases/{knowledge_base_id}/query" in shared["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/knowledge/shared/bases", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/library"]["status"] == "equivalent"
    assert routes["/library"]["matchedRoute"] == "/api/cognix/knowledge/shared/bases"


def test_shared_knowledge_routes_index_permissions_and_filtered_retrieval():
    seed_accounts()

    with pytest.raises(HTTPException) as user_create:
        run_async(
            cognix_routes.create_shared_knowledge_base(
                cognix_routes.SharedKnowledgeBaseRequest(name = "Physics KB"),
                current_subject = "alice",
            )
        )
    assert user_create.value.status_code == 403

    created = run_async(
        cognix_routes.create_shared_knowledge_base(
            cognix_routes.SharedKnowledgeBaseRequest(
                name = "Physics KB",
                description = "Organization physics sources",
                visibility = "organization",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    kb_id = created["knowledgeBase"]["id"]
    assert created["sideEffects"]["knowledgeBaseWrite"] is True

    document = run_async(
        cognix_routes.add_shared_knowledge_document(
            kb_id,
            cognix_routes.SharedKnowledgeDocumentRequest(
                title = "Quantum notes",
                content = "Quantum mechanics uses wave functions. Alpha beta gamma sources explain operators.",
                chunkSize = 20,
                overlap = 0,
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert document["sideEffects"]["documentWrite"] is True
    assert document["sideEffects"]["chunkWrite"] is True
    assert document["sideEffects"]["embeddingCall"] is False
    assert document["chunks"][0]["embeddingStatus"] == "planned"

    permission = run_async(
        cognix_routes.grant_shared_knowledge_permission(
            kb_id,
            cognix_routes.SharedKnowledgePermissionRequest(
                subjectType = "user",
                subjectId = "alice",
                permission = "read",
            ),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert permission["sideEffects"]["permissionWrite"] is True

    alice = run_async(
        cognix_routes.query_shared_knowledge_base(
            kb_id,
            cognix_routes.SharedKnowledgeQueryRequest(query = "wave operators", limit = 5),
            current_subject = "alice",
        )
    )
    assert alice["retrieval"]["summary"]["returnedChunkCount"] == 1
    assert alice["retrieval"]["sources"][0]["title"] == "Quantum notes"
    assert alice["retrieval"]["summary"]["filteredChunkCount"] == 0

    bob = run_async(
        cognix_routes.query_shared_knowledge_base(
            kb_id,
            cognix_routes.SharedKnowledgeQueryRequest(query = "wave operators", limit = 5),
            current_subject = "bob",
        )
    )
    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert bob["retrieval"]["summary"]["returnedChunkCount"] == 0
    assert bob["retrieval"]["summary"]["filteredChunkCount"] >= 1
    assert "shared_knowledge_permission_granted" in audit_actions
