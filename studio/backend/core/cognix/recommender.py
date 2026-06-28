# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX local model recommendation helpers."""

from __future__ import annotations

import re
from typing import Any

from core.cognix import registry as cognix_registry


COGNIX_DEFAULT_OLLAMA_PROVIDER_ID = cognix_registry.COGNIX_DEFAULT_OLLAMA_PROVIDER_ID
COGNIX_DEFAULT_OLLAMA_MODEL_ID = cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


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


def _best_benchmark_model(benchmark: dict[str, Any]) -> dict[str, Any] | None:
    fitness = benchmark.get("modelFitness")
    if not isinstance(fitness, list):
        return None
    candidates = [
        item
        for item in fitness
        if isinstance(item, dict)
        and item.get("status") in {"recommended", "possible", "tight"}
        and int(item.get("stars") or 0) > 0
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key = lambda item: (
            int(item.get("stars") or 0),
            _as_float(item.get("estimatedTokensPerSecond")) or 0.0,
        ),
    )


def _benchmark_signal(latest_benchmark_run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(latest_benchmark_run, dict):
        return {
            "available": False,
            "status": "missing",
            "reason": "Aucun benchmark CogniX local n'a encore ete execute.",
        }
    benchmark = latest_benchmark_run.get("benchmark")
    if not isinstance(benchmark, dict):
        return {
            "available": False,
            "status": "invalid",
            "reason": "Dernier benchmark indisponible ou incomplet.",
        }
    best_model = _best_benchmark_model(benchmark)
    optimization = benchmark.get("optimizationPlan")
    return {
        "available": True,
        "status": "measured",
        "runId": latest_benchmark_run.get("id"),
        "createdAt": latest_benchmark_run.get("created_at"),
        "benchmarkVersion": benchmark.get("benchmarkVersion"),
        "overallScore": benchmark.get("overallScore"),
        "estimatedTokensPerSecond": benchmark.get("estimatedTokensPerSecond"),
        "optimizationPlan": optimization if isinstance(optimization, dict) else {},
        "bestLocalModel": best_model,
        "reason": "Dernier benchmark CogniX utilise pour ajuster la recommandation locale.",
    }


def _readiness_confidence(readiness: str) -> float:
    return {
        "ready": 0.82,
        "ready_with_caution": 0.72,
        "model_missing": 0.58,
        "service_unreachable": 0.45,
        "setup_required": 0.35,
        "hardware_blocked": 0.25,
    }[readiness]


def build_model_recommendation(
    hardware: dict[str, Any],
    *,
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    benchmark = _benchmark_signal(latest_benchmark_run)

    warnings: list[str] = []
    if hardware.get("deviceBackend") == "cpu":
        warnings.append("Aucun GPU visible: privilégier les petits modeles quantifies.")
    if not benchmark["available"]:
        warnings.append("Benchmark CogniX absent: lance /api/cognix/benchmark/run pour calibrer la machine.")
    if not ollama["configured"]:
        warnings.append("Provider Ollama par defaut absent de la base locale.")
    if not ollama["reachable"]:
        warnings.append("Service Ollama non joignable sur l'URL configuree.")
    if not ollama["hasDefaultModel"]:
        warnings.append("Modele Qwen 4B par defaut non visible dans le catalogue Ollama.")
    expected_speed = str((benchmark.get("optimizationPlan") or {}).get("expectedLocalSpeed") or "")
    if expected_speed == "slow":
        warnings.append("Benchmark local lent: privilegier Q4, contexte court et un seul modele resident.")
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

    confidence = _readiness_confidence(readiness)
    if benchmark["available"] and readiness in {"ready", "ready_with_caution"}:
        confidence = min(0.92, round(confidence + 0.05, 2))
    elif not benchmark["available"]:
        confidence = max(0.2, round(confidence - 0.04, 2))

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
            "benchmark": benchmark,
            "confidence": confidence,
            "warnings": warnings,
            "reason": (
                "Machine calibree par benchmark local; CogniX recommande un petit modele quantifie via Ollama."
                if benchmark["available"]
                else "Machine detectee en usage local leger; CogniX recommande un petit "
                "modele quantifie via Ollama avant de construire le router avance."
            ),
        },
    }
