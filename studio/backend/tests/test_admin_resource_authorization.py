# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Admin-only guards for global platform resources."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.authentication import get_current_jwt_subject, get_current_subject
from hub import dependencies as hub_dependencies
from hub.routes import datasets as hub_datasets
from hub.routes import inventory as hub_inventory
from routes import data_recipe, datasets, export, inference, llama, mcp_servers, models, providers, training, training_history
from storage import mcp_servers_db, providers_db


def _client(router, prefix: str, subject: str) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix = prefix)
    app.dependency_overrides[get_current_subject] = lambda: subject
    app.dependency_overrides[get_current_jwt_subject] = lambda: subject
    return TestClient(app)


def test_provider_mutations_are_admin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(tmp_path))
    monkeypatch.setattr(providers_db, "_schema_ready", False)
    monkeypatch.setattr(providers.auth_storage, "is_admin", lambda subject: subject == "admin")

    user = _client(providers.router, "/api/providers", "user")
    admin = _client(providers.router, "/api/providers", "admin")

    payload = {"provider_type": "openai", "display_name": "OpenAI"}
    assert user.get("/api/providers/").status_code == 403
    assert user.post("/api/providers/", json = payload).status_code == 403
    assert user.post("/api/providers/models", json = {"provider_type": "openai"}).status_code == 403

    created = admin.post("/api/providers/", json = payload)
    assert created.status_code == 201
    provider_id = created.json()["id"]

    assert admin.get("/api/providers/").status_code == 200
    assert user.put(f"/api/providers/{provider_id}", json = {"display_name": "Tamper"}).status_code == 403
    assert user.delete(f"/api/providers/{provider_id}").status_code == 403


def test_mcp_server_mutations_are_admin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(tmp_path))
    monkeypatch.setattr(mcp_servers_db, "_schema_ready", False)
    monkeypatch.setattr(mcp_servers.auth_storage, "is_admin", lambda subject: subject == "admin")

    user = _client(mcp_servers.router, "/api/mcp/servers", "user")
    admin = _client(mcp_servers.router, "/api/mcp/servers", "admin")

    payload = {"display_name": "Docs", "url": "https://example.com/mcp"}
    assert user.get("/api/mcp/servers/").status_code == 403
    assert user.post("/api/mcp/servers/", json = payload).status_code == 403
    assert user.post("/api/mcp/servers/test", json = {"url": "https://example.com/mcp"}).status_code == 403

    created = admin.post("/api/mcp/servers/", json = payload)
    assert created.status_code == 201
    server_id = created.json()["id"]

    assert admin.get("/api/mcp/servers/").status_code == 200
    assert user.put(f"/api/mcp/servers/{server_id}", json = {"display_name": "Tamper"}).status_code == 403
    assert user.post(f"/api/mcp/servers/{server_id}/refresh").status_code == 403
    assert user.delete(f"/api/mcp/servers/{server_id}").status_code == 403


def test_model_filesystem_routes_are_admin_only(monkeypatch):
    monkeypatch.setattr(models.auth_storage, "is_admin", lambda subject: subject == "admin")

    user = _client(models.router, "/api/models", "user")

    assert user.get("/api/models/local").status_code == 403
    assert user.get("/api/models/scan-folders").status_code == 403
    assert user.post("/api/models/scan-folders", json = {"path": "C:\\Models"}).status_code == 403
    assert user.delete("/api/models/scan-folders/1").status_code == 403
    assert user.get("/api/models/recommended-folders").status_code == 403
    assert user.get("/api/models/browse-folders").status_code == 403
    assert user.get("/api/models/cached-gguf").status_code == 403
    assert user.get("/api/models/cached-models").status_code == 403
    assert user.request(
        "DELETE",
        "/api/models/delete-finetuned",
        json = {"model_path": "C:\\Models\\x", "source": "training"},
    ).status_code == 403
    assert user.request(
        "DELETE",
        "/api/models/delete-cached",
        json = {"repo_id": "org/model"},
    ).status_code == 403


def test_dataset_and_data_recipe_routes_are_admin_only(monkeypatch):
    monkeypatch.setattr(datasets.auth_storage, "is_admin", lambda subject: subject == "admin")
    monkeypatch.setattr(data_recipe.auth_storage, "is_admin", lambda subject: subject == "admin")

    dataset_user = _client(datasets.router, "/api/datasets", "user")
    assert dataset_user.get("/api/datasets/local").status_code == 403
    assert dataset_user.get("/api/datasets/download-progress?repo_id=org/name").status_code == 403

    recipe_user = _client(data_recipe.router, "/api/data-recipe", "user")
    assert recipe_user.get("/api/data-recipe/jobs/current").status_code == 403
    assert recipe_user.post("/api/data-recipe/validate", json = {}).status_code == 403


def test_hub_routes_are_admin_only(monkeypatch):
    monkeypatch.setattr(hub_dependencies.auth_storage, "is_admin", lambda subject: subject == "admin")

    hub_user = _client(hub_inventory.router, "/api/hub", "user")
    assert hub_user.get("/api/hub/local").status_code == 403
    assert hub_user.get("/api/hub/scan-folders").status_code == 403

    hub_dataset_user = _client(hub_datasets.router, "/api/hub/datasets", "user")
    assert hub_dataset_user.get("/api/hub/datasets/local").status_code == 403
    assert hub_dataset_user.get("/api/hub/datasets/cached").status_code == 403


def test_training_export_and_llama_routes_are_admin_only(monkeypatch):
    for module in (training, export, training_history, llama):
        monkeypatch.setattr(module.auth_storage, "is_admin", lambda subject: subject == "admin")

    training_user = _client(training.router, "/api/training", "user")
    assert training_user.get("/api/training/hardware").status_code == 403
    assert training_user.get("/api/training/status").status_code == 403
    assert training_user.post("/api/training/reset").status_code == 403
    assert training_user.post("/api/training/stop").status_code == 403

    history_user = _client(training_history.router, "/api/training-history", "user")
    assert history_user.get("/api/training-history/runs").status_code == 403
    assert history_user.delete("/api/training-history/runs/run-1").status_code == 403

    export_user = _client(export.router, "/api/export", "user")
    assert export_user.get("/api/export/status").status_code == 403
    assert export_user.get("/api/export/logs").status_code == 403
    assert export_user.post("/api/export/cleanup").status_code == 403
    assert export_user.post("/api/export/cancel").status_code == 403

    llama_user = _client(llama.router, "/api/llama", "user")
    assert llama_user.get("/api/llama/update-status").status_code == 403
    assert llama_user.post("/api/llama/update").status_code == 403


def test_inference_model_management_routes_are_admin_only(monkeypatch):
    monkeypatch.setattr(inference.auth_storage, "is_admin", lambda subject: subject == "admin")

    user = _client(inference.router, "/api/inference", "user")

    assert user.post("/api/inference/load", json = {"model_path": "org/model"}).status_code == 403
    assert user.post("/api/inference/validate", json = {"model_path": "org/model"}).status_code == 403
    assert user.post("/api/inference/unload", json = {"model_path": "org/model"}).status_code == 403
