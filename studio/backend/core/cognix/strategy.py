# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX strategy and local model recommendation helpers."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from storage import providers_db


COGNIX_DEFAULT_OLLAMA_PROVIDER_ID = "b6878df754d543b1"
COGNIX_DEFAULT_OLLAMA_MODEL_ID = "huihui_ai/qwen3-vl-abliterated:4b-instruct"
COGNIX_DEFAULT_OLLAMA_PROVIDER_NAME = "Ollama Qwen 4B"
COGNIX_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"


def _parse_model_size_b(model_id: str) -> float | None:
    match = re.search(r"(?i)(\d+(?:\.\d+)?)\s*b\b", model_id)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _estimate_quantized_model_ram_gb(model_id: str) -> float | None:
    size_b = _parse_model_size_b(model_id)
    if size_b is None:
        return None
    # Conservative local estimate for Q4-ish Ollama/GGUF models plus runtime overhead.
    return round(max(2.0, size_b * 0.8 + 1.2), 1)


def _memory_fit(
    *,
    model_id: str,
    available_gb: float | None,
    total_gb: float | None,
) -> dict[str, Any]:
    estimated_gb = _estimate_quantized_model_ram_gb(model_id)
    if estimated_gb is None:
        return {
            "level": "unknown",
            "estimatedRamGb": None,
            "label": "Taille modele inconnue",
        }
    if total_gb is not None and total_gb < estimated_gb:
        return {
            "level": "blocked",
            "estimatedRamGb": estimated_gb,
            "label": "RAM totale insuffisante pour ce modele en local",
        }
    if available_gb is not None and available_gb < estimated_gb:
        return {
            "level": "tight",
            "estimatedRamGb": estimated_gb,
            "label": "Possible, mais ferme les apps lourdes avant generation",
        }
    return {
        "level": "ok",
        "estimatedRamGb": estimated_gb,
        "label": "Compatible avec la memoire actuellement disponible",
    }


def _hardware_profile() -> dict[str, Any]:
    total_gb: float | None = None
    available_gb: float | None = None
    cpu_count: int | None = None
    try:
        import psutil

        memory = psutil.virtual_memory()
        total_gb = round(memory.total / 1e9, 2)
        available_gb = round(memory.available / 1e9, 2)
        cpu_count = psutil.cpu_count()
    except Exception:
        pass

    gpu_available = False
    gpu_devices: list[dict[str, Any]] = []
    device_backend = "unknown"
    try:
        from utils.hardware import get_backend_visible_gpu_info, get_device
        from utils.hardware.hardware import _backend_label

        visibility = get_backend_visible_gpu_info()
        gpu_available = bool(visibility.get("available"))
        gpu_devices = [
            {
                "name": item.get("name"),
                "vramTotalGb": item.get("memory_total_gb"),
            }
            for item in visibility.get("devices", [])
        ]
        device_backend = _backend_label(get_device())
    except Exception:
        pass

    if device_backend == "unknown":
        device_backend = "gpu" if gpu_available else "cpu"

    return {
        "deviceBackend": device_backend,
        "cpuCount": cpu_count,
        "memory": {
            "totalGb": total_gb,
            "availableGb": available_gb,
        },
        "gpu": {
            "available": gpu_available,
            "devices": gpu_devices,
        },
    }


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


def _provider_summary() -> dict[str, Any]:
    rows = providers_db.list_providers()
    configured = [
        {
            "id": row.get("id"),
            "type": row.get("provider_type"),
            "name": row.get("display_name"),
            "baseUrl": row.get("base_url"),
            "enabled": bool(row.get("is_enabled")),
        }
        for row in rows
    ]
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
    if default_provider is None:
        default_provider = {
            "id": COGNIX_DEFAULT_OLLAMA_PROVIDER_ID,
            "type": "ollama",
            "name": COGNIX_DEFAULT_OLLAMA_PROVIDER_NAME,
            "baseUrl": COGNIX_DEFAULT_OLLAMA_BASE_URL,
            "enabled": False,
        }

    base_url = str(default_provider.get("baseUrl") or COGNIX_DEFAULT_OLLAMA_BASE_URL)
    reachable, models = _ollama_models(base_url)
    has_default_model = COGNIX_DEFAULT_OLLAMA_MODEL_ID in models
    recommended_model = (
        COGNIX_DEFAULT_OLLAMA_MODEL_ID
        if has_default_model
        else (models[0] if models else COGNIX_DEFAULT_OLLAMA_MODEL_ID)
    )
    return {
        "configured": configured,
        "ollama": {
            "configured": bool(enabled_ollama),
            "reachable": reachable,
            "provider": default_provider,
            "models": models,
            "hasDefaultModel": has_default_model,
            "recommendedModel": recommended_model,
        },
    }


def build_strategy(current_subject: str) -> dict[str, Any]:
    hardware = _hardware_profile()
    providers = _provider_summary()
    ollama = providers["ollama"]
    recommended_model = str(ollama["recommendedModel"])
    memory = hardware.get("memory") or {}
    fit = _memory_fit(
        model_id = recommended_model,
        available_gb = memory.get("availableGb"),
        total_gb = memory.get("totalGb"),
    )
    provider = ollama["provider"]

    warnings: list[str] = []
    if hardware.get("deviceBackend") == "cpu":
        warnings.append("Aucun GPU visible: privilégier les petits modeles quantifies.")
    if not ollama["configured"]:
        warnings.append("Provider Ollama par defaut absent de la base locale.")
    if not ollama["reachable"]:
        warnings.append("Service Ollama non joignable sur l'URL configuree.")
    if not ollama["hasDefaultModel"]:
        warnings.append("Modele Qwen 4B par defaut non visible dans le catalogue Ollama.")
    if fit["level"] == "tight":
        warnings.append("RAM disponible serree: eviter le multitache pendant les generations.")
    elif fit["level"] == "blocked":
        warnings.append("RAM locale insuffisante: utiliser un modele plus petit ou un provider cloud.")

    readiness = "ready"
    if not ollama["configured"]:
        readiness = "setup_required"
    elif not ollama["reachable"]:
        readiness = "service_unreachable"
    elif fit["level"] == "blocked":
        readiness = "hardware_blocked"
    elif not ollama["hasDefaultModel"]:
        readiness = "model_missing"
    elif fit["level"] == "tight":
        readiness = "ready_with_caution"

    confidence = {
        "ready": 0.82,
        "ready_with_caution": 0.72,
        "model_missing": 0.58,
        "service_unreachable": 0.45,
        "setup_required": 0.35,
        "hardware_blocked": 0.25,
    }[readiness]

    return {
        "username": current_subject,
        "phase": "mvp_core_local",
        "roadmapPhase": "Phase 1 - Core local solide",
        "hardware": hardware,
        "providers": providers,
        "recommendation": {
            "readiness": readiness,
            "executionMode": "local",
            "providerId": provider.get("id"),
            "providerType": provider.get("type"),
            "providerName": provider.get("name"),
            "baseUrl": provider.get("baseUrl"),
            "modelId": recommended_model,
            "modelLabel": "Qwen 4B local via Ollama",
            "memoryFit": fit,
            "confidence": confidence,
            "warnings": warnings,
            "reason": (
                "Machine detectee en usage local leger; CogniX recommande un petit "
                "modele quantifie via Ollama avant de construire le router avance."
            ),
        },
        "nextSteps": [
            "brancher cette strategie au futur Model Router",
            "ajouter un Hardware Profiler visible",
            "journaliser les decisions de routage",
            "preparer le Model Cache Manager sans changer le chat actuel",
        ],
    }
