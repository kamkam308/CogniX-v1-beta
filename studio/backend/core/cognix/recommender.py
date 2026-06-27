# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX local model recommendation helpers."""

from __future__ import annotations

import re
from typing import Any

from core.cognix import registry as cognix_registry


COGNIX_DEFAULT_OLLAMA_PROVIDER_ID = cognix_registry.COGNIX_DEFAULT_OLLAMA_PROVIDER_ID
COGNIX_DEFAULT_OLLAMA_MODEL_ID = cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID


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


def build_model_recommendation(hardware: dict[str, Any]) -> dict[str, Any]:
    registry = cognix_registry.build_model_registry()
    ollama = registry["ollama"]
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
        "registry": registry,
        "providers": {
            "configured": registry["providers"],
            "ollama": registry["ollama"],
        },
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
    }
