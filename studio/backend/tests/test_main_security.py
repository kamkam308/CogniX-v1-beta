# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved.

"""Security checks for app-level endpoints."""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _shutdown_client(subject: str, monkeypatch) -> TestClient:
    import main
    from auth.authentication import get_current_jwt_subject

    monkeypatch.setattr(main.storage, "is_admin", lambda candidate: candidate == "admin")

    app = FastAPI()
    app.state.trigger_shutdown = lambda: None
    app.add_api_route("/api/shutdown", main.shutdown_server, methods = ["POST"])
    app.dependency_overrides[get_current_jwt_subject] = lambda: subject
    return TestClient(app)


def test_shutdown_rejects_non_admin_user(monkeypatch):
    client = _shutdown_client("user", monkeypatch)

    response = client.post("/api/shutdown")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin privileges required"


def test_shutdown_allows_admin(monkeypatch):
    client = _shutdown_client("admin", monkeypatch)

    response = client.post("/api/shutdown")

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}


def test_cors_defaults_do_not_allow_wildcard_with_credentials():
    import main

    assert "*" not in main._cors_origins
    assert main._cors_origin_regex is None


def test_cors_extra_origins_ignore_wildcard(monkeypatch):
    import main

    monkeypatch.setenv(
        "UNSLOTH_STUDIO_CORS_ORIGINS",
        "*, https://cognix.example, https://cognix.example",
    )

    origins = main._configured_cors_origins(["http://localhost"])

    assert origins == ["http://localhost", "https://cognix.example"]
