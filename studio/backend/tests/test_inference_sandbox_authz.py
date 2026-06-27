# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved.

"""Authorization checks for inference sandbox file sessions."""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def test_sandbox_denies_known_thread_owned_by_another_user(monkeypatch):
    from routes import inference
    from storage import studio_db

    monkeypatch.setattr(inference.auth_storage, "is_admin", lambda subject: False)

    def fake_get_chat_thread(id, *, owner_username = None, include_all = True):
        if id != "thread-owned-by-bob":
            return None
        if owner_username == "alice" and not include_all:
            return None
        return {"id": id, "ownerUsername": "bob"}

    monkeypatch.setattr(studio_db, "get_chat_thread", fake_get_chat_thread)

    with pytest.raises(HTTPException) as exc:
        inference._ensure_sandbox_session_access("thread-owned-by-bob", "alice")

    assert exc.value.status_code == 404


def test_sandbox_allows_unknown_legacy_session_id(monkeypatch):
    from routes import inference
    from storage import studio_db

    monkeypatch.setattr(inference.auth_storage, "is_admin", lambda subject: False)
    monkeypatch.setattr(studio_db, "get_chat_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr(studio_db, "get_chat_project", lambda *args, **kwargs: None)

    inference._ensure_sandbox_session_access("legacy-session", "alice")


def test_sandbox_allows_admin_for_known_project(monkeypatch):
    from routes import inference
    from storage import studio_db

    monkeypatch.setattr(inference.auth_storage, "is_admin", lambda subject: subject == "admin")

    def fake_get_chat_project(id, *, owner_username = None, include_all = True):
        if id == "project-1" and include_all:
            return {"id": id, "ownerUsername": "bob"}
        return None

    monkeypatch.setattr(studio_db, "get_chat_project", fake_get_chat_project)
    monkeypatch.setattr(studio_db, "get_chat_thread", lambda *args, **kwargs: None)

    inference._ensure_sandbox_session_access("project-project-1", "admin")
