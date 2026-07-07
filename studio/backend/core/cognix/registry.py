# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX model registry helpers."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from storage import providers_db


COGNIX_DEFAULT_OLLAMA_PROVIDER_ID = "b6878df754d543b1"
COGNIX_DEFAULT_OLLAMA_MODEL_ID = "huihui_ai/qwen3-vl-abliterated:4b-instruct"
COGNIX_DEFAULT_OLLAMA_PROVIDER_NAME = "Ollama Qwen 4B"
COGNIX_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"


def _ollama_models(base_url: str, timeout: float = 1.25) -> tuple[bool, list[str]]:
    endpoint = base_url.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(endpoint, timeout = timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors = "replace"))
    except Exception:
        return False, []
    data = payload.get("data")
    if not isinstance(data, list):
        return True, []
    models = sorted(
        str(item.get("id"))
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")
    )
    return True, models


def _configured_providers() -> list[dict[str, Any]]:
    rows = providers_db.list_providers()
    return [
        {
            "id": row.get("id"),
            "type": row.get("provider_type"),
            "name": row.get("display_name"),
            "baseUrl": row.get("base_url"),
            "enabled": bool(row.get("is_enabled")),
        }
        for row in rows
    ]


def _default_ollama_provider(configured: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    enabled_ollama = [
        provider
        for provider in configured
        if provider.get("type") == "ollama" and provider.get("enabled")
    ]
    default_provider = next(
        (
            provider
            for provider in enabled_ollama
            if provider.get("id") == COGNIX_DEFAULT_OLLAMA_PROVIDER_ID
        ),
        None,
    )
    if default_provider is None and enabled_ollama:
        default_provider = enabled_ollama[0]
    if default_provider is not None:
        return default_provider, True
    return {
        "id": COGNIX_DEFAULT_OLLAMA_PROVIDER_ID,
        "type": "ollama",
        "name": COGNIX_DEFAULT_OLLAMA_PROVIDER_NAME,
        "baseUrl": COGNIX_DEFAULT_OLLAMA_BASE_URL,
        "enabled": False,
    }, False


def build_model_registry() -> dict[str, Any]:
    configured = _configured_providers()
    default_provider, has_enabled_ollama = _default_ollama_provider(configured)
    base_url = str(default_provider.get("baseUrl") or COGNIX_DEFAULT_OLLAMA_BASE_URL)
    reachable, models = _ollama_models(base_url)
    has_default_model = COGNIX_DEFAULT_OLLAMA_MODEL_ID in models
    recommended_model = (
        COGNIX_DEFAULT_OLLAMA_MODEL_ID
        if has_default_model
        else (models[0] if models else COGNIX_DEFAULT_OLLAMA_MODEL_ID)
    )
    registered_models = [
        {
            "id": model_id,
            "label": model_id,
            "providerId": default_provider.get("id"),
            "providerType": "ollama",
            "source": "ollama",
            "available": True,
            "default": model_id == COGNIX_DEFAULT_OLLAMA_MODEL_ID,
        }
        for model_id in models
    ]
    if not has_default_model:
        registered_models.append(
            {
                "id": COGNIX_DEFAULT_OLLAMA_MODEL_ID,
                "label": "Qwen 4B local via Ollama",
                "providerId": default_provider.get("id"),
                "providerType": "ollama",
                "source": "cognix_default",
                "available": False,
                "default": True,
            }
        )

    return {
        "registryVersion": "local_model_registry_v1",
        "providers": configured,
        "models": registered_models,
        "defaultModelId": COGNIX_DEFAULT_OLLAMA_MODEL_ID,
        "recommendedModelId": recommended_model,
        "ollama": {
            "configured": has_enabled_ollama,
            "reachable": reachable,
            "provider": default_provider,
            "models": models,
            "hasDefaultModel": has_default_model,
            "recommendedModel": recommended_model,
        },
    }
