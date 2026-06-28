# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX optimization planner.

This planner decides which runtime optimizations are safe to prepare for a
request. It never changes engine flags, cache state, or model files.
"""

from __future__ import annotations

from typing import Any


COGNIX_OPTIMIZATION_PLANNER_VERSION = "cognix_optimization_planner_v1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _hardware_tier(hardware: dict[str, Any]) -> str:
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb"))
    available_gb = _as_float(memory.get("availableGb"))
    gpu = _as_dict(hardware.get("gpu"))
    devices = gpu.get("devices") if isinstance(gpu.get("devices"), list) else []
    max_vram = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices if isinstance(item, dict)),
        default = 0.0,
    )
    if bool(gpu.get("available")) and (max_vram >= 16 or (total_gb or 0) >= 32):
        return "powerful_local"
    if (available_gb is not None and available_gb < 5) or (total_gb is not None and total_gb <= 12):
        return "small_local"
    return "balanced_local"


def _optimization(
    *,
    optimization_id: str,
    label: str,
    status: str,
    reason: str,
    expected_impact: str,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": optimization_id,
        "label": label,
        "status": status,
        "reason": reason,
        "expectedImpact": expected_impact,
        "prerequisites": prerequisites or [],
        "willApplyAutomatically": False,
    }


def build_optimization_plan(
    *,
    hardware: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any] | None = None,
    context_plan: dict[str, Any] | None = None,
    rag_plan: dict[str, Any] | None = None,
    task_strategy: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cache = _as_dict(cache)
    context_plan = _as_dict(context_plan)
    rag_plan = _as_dict(rag_plan)
    task_strategy = _as_dict(task_strategy)
    provider_type = str(recommendation.get("providerType") or "unknown")
    memory_fit = _as_dict(recommendation.get("memoryFit"))
    memory_level = str(memory_fit.get("level") or "unknown")
    tier = _hardware_tier(hardware)
    context_tokens = int(_as_float(_as_dict(context_plan.get("tokenBudget")).get("maxContextTokens")) or 0)
    rag_ready = bool(rag_plan.get("readyForRetrieval"))
    benchmark_available = isinstance(latest_benchmark_run, dict)

    optimizations: list[dict[str, Any]] = []
    optimizations.append(
        _optimization(
            optimization_id = "quantization_profile",
            label = "Profil quantization",
            status = "prefer_q4" if tier == "small_local" or memory_level == "tight" else "prefer_q5_or_q8" if tier == "powerful_local" else "prefer_q4_or_q5",
            reason = "Adapter la quantization au profil RAM/VRAM avant chargement.",
            expected_impact = "memory",
            prerequisites = ["model_metadata", "runtime_adapter"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "prompt_cache",
            label = "Prompt caching",
            status = "recommended" if context_tokens >= 1800 else "optional",
            reason = "Reutiliser les prefixes stables lorsque le contexte devient long.",
            expected_impact = "latency",
            prerequisites = ["stable_system_prompt", "runtime_support"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "kv_cache_policy",
            label = "KV-cache policy",
            status = "compact" if tier == "small_local" else "standard",
            reason = "Garder les tours recents utiles et eviter l'historique brut.",
            expected_impact = "memory_latency",
            prerequisites = ["context_manager"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "rag_compression",
            label = "Compression RAG",
            status = "recommended" if rag_ready else "defer_until_retrieval",
            reason = "Compresser les passages documentaires avant injection quand RAG est pret.",
            expected_impact = "quality_latency",
            prerequisites = ["rag_plan", "citations"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "speculative_decoding",
            label = "Speculative decoding",
            status = "candidate" if tier == "powerful_local" and provider_type in {"llama.cpp", "vllm"} else "unsupported_for_current_runtime",
            reason = "Necessite un runtime compatible et un petit modele draft mesure.",
            expected_impact = "latency",
            prerequisites = ["draft_model", "runtime_support", "benchmark"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "single_resident_model",
            label = "Modele resident unique",
            status = "recommended" if tier == "small_local" else "not_needed",
            reason = "Limiter la RAM sur petit PC local.",
            expected_impact = "stability",
            prerequisites = ["cache_manager"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "batching",
            label = "Batching",
            status = "enterprise_only" if task_strategy.get("path") != "expert_chat" else "not_needed_for_single_user",
            reason = "Utile surtout pour plusieurs utilisateurs ou serveurs GPU.",
            expected_impact = "throughput",
            prerequisites = ["worker_queue", "multi_user_scheduler"],
        )
    )
    optimizations.append(
        _optimization(
            optimization_id = "benchmark_calibration",
            label = "Calibration benchmark",
            status = "measured" if benchmark_available else "recommended",
            reason = "Mesurer avant d'activer une optimisation de runtime.",
            expected_impact = "stability",
            prerequisites = ["local_benchmark"],
        )
    )

    recommended = [item["id"] for item in optimizations if item.get("status") in {"recommended", "prefer_q4", "prefer_q4_or_q5", "prefer_q5_or_q8", "compact", "standard", "candidate"}]
    warnings: list[str] = []
    if not benchmark_available:
        warnings.append("Benchmark absent: mesurer avant d'appliquer les optimisations runtime.")
    if provider_type == "ollama" and any(item["id"] == "speculative_decoding" and item["status"] == "unsupported_for_current_runtime" for item in optimizations):
        warnings.append("Speculative decoding non active: support runtime non confirme pour Ollama.")
    if memory_level == "tight":
        warnings.append("Memoire serree: privilegier contexte court, Q4 et un seul modele resident.")

    return {
        "plannerVersion": COGNIX_OPTIMIZATION_PLANNER_VERSION,
        "mode": "dry_run",
        "hardwareTier": tier,
        "runtimeType": provider_type,
        "optimizationProfile": "memory_saver" if tier == "small_local" or memory_level == "tight" else "throughput_ready" if tier == "powerful_local" else "balanced",
        "recommendedOptimizationIds": recommended,
        "optimizations": optimizations,
        "warnings": warnings,
        "reason": "Optimisations planifiees sans modifier le runtime ni le cache.",
        "sideEffects": {
            "modelReconfiguration": False,
            "cacheMutation": False,
            "benchmarkRun": False,
            "networkModelCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }
