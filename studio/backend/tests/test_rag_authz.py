# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Authorization checks for RAG resources tied to chat owners."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("sqlite_vec")

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth.authentication import get_current_jwt_subject
from routes import rag
from storage import rag_db, studio_db
from core.rag import store


def _app_for_subject(subject: str) -> TestClient:
    app = FastAPI()
    app.include_router(rag.router, prefix = "/api/rag")
    app.dependency_overrides[get_current_jwt_subject] = lambda: subject
    return TestClient(app)


def _reset_studio_state(rag_home, monkeypatch) -> None:
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(rag_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(rag_home / "Projects"))
    monkeypatch.setattr(studio_db, "_schema_ready", False)


def _seed_thread_document(thread_owner: str = "alice") -> str:
    studio_db.upsert_chat_thread(
        {
            "id": "thread-owned",
            "title": "Private thread",
            "modelType": "base",
            "modelId": "model-a",
            "pairId": None,
            "archived": False,
            "createdAt": 1_700_000_000_000,
        },
        owner_username = thread_owner,
    )
    conn = rag_db.get_connection()
    try:
        return store.create_document(
            conn,
            scope = store.thread_scope("thread-owned"),
            filename = "private.txt",
            sha256 = "hash-private",
            thread_id = "thread-owned",
            status = "completed",
        )
    finally:
        conn.close()


def test_thread_documents_are_owner_scoped(rag_home, monkeypatch):
    _reset_studio_state(rag_home, monkeypatch)
    monkeypatch.setattr(rag.auth_storage, "is_admin", lambda subject: subject == "admin")
    document_id = _seed_thread_document()

    bob = _app_for_subject("bob")
    alice = _app_for_subject("alice")
    admin = _app_for_subject("admin")

    assert bob.get("/api/rag/threads/thread-owned/documents").status_code == 404
    assert bob.delete(f"/api/rag/documents/{document_id}").status_code == 404

    alice_docs = alice.get("/api/rag/threads/thread-owned/documents")
    assert alice_docs.status_code == 200
    assert alice_docs.json()["documents"][0]["id"] == document_id

    admin_docs = admin.get("/api/rag/threads/thread-owned/documents")
    assert admin_docs.status_code == 200
    assert admin_docs.json()["documents"][0]["id"] == document_id


def test_knowledge_bases_are_owner_scoped(rag_home, monkeypatch):
    _reset_studio_state(rag_home, monkeypatch)
    monkeypatch.setattr(rag.auth_storage, "is_admin", lambda subject: subject == "admin")

    alice = _app_for_subject("alice")
    bob = _app_for_subject("bob")
    admin = _app_for_subject("admin")

    created = alice.post("/api/rag/knowledge-bases", json = {"name": "Alice KB"})
    assert created.status_code == 200
    kb_id = created.json()["id"]

    bob_list = bob.get("/api/rag/knowledge-bases")
    assert bob_list.status_code == 200
    assert bob_list.json()["knowledgeBases"] == []

    admin_list = admin.get("/api/rag/knowledge-bases")
    assert admin_list.status_code == 200
    assert admin_list.json()["knowledgeBases"][0]["id"] == kb_id

    assert bob.get(f"/api/rag/knowledge-bases/{kb_id}/documents").status_code == 404
    assert bob.patch(f"/api/rag/knowledge-bases/{kb_id}", json = {"name": "Bob KB"}).status_code == 404
    assert bob.delete(f"/api/rag/knowledge-bases/{kb_id}").status_code == 404
    assert bob.post("/api/rag/search", json = {"kb_id": kb_id, "query": "secret"}).status_code == 404
