# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX optimization planner.

This planner decides which runtime optimizations are safe to prepare for a
request. It never changes engine flags, cache state, or model files.
"""

from __future__ import annotations

from typing import Any


COGNIX_OPTIMIZATION_PLANNER_VERSION = "cognix_optimization_planner_v1"
COGNIX_OPTIMIZATION_CAPABILITY_REGISTRY_VERSION = "cognix_optimization_capability_registry_v1"
COGNIX_OPTIMIZATION_EXPERIMENT_PLAN_VERSION = "cognix_optimization_experiment_plan_v1"

OPTIMIZATION_CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "quantization",
        "label": "Quantization strategies",
        "category": "memory",
        "requiredSignals": ["model_metadata", "runtime_adapter", "memory_fit"],
        "dependencies": ["cognix-model-lifecycle", "cognix-runtime-adapter"],
        "estimatedBenefit": {"memory": "high", "latency": "medium", "qualityRisk": "medium"},
        "risk": "medium",
        "runtimeSupport": ["llama.cpp", "ollama", "vllm", "transformers"],
        "hardwareSupport": ["small_local", "balanced_local", "powerful_local"],
        "experimental": False,
    },
    {
        "id": "flash_attention",
        "label": "FlashAttention",
        "category": "latency",
        "requiredSignals": ["gpu_backend", "model_architecture", "torch_runtime"],
        "dependencies": ["cognix-runtime-adapter", "cognix-worker-queue"],
        "estimatedBenefit": {"latency": "high", "memory": "medium", "qualityRisk": "low"},
        "risk": "medium",
        "runtimeSupport": ["transformers", "vllm"],
        "hardwareSupport": ["powerful_local"],
        "experimental": True,
    },
    {
        "id": "kv_cache_eviction",
        "label": "KV-cache eviction",
        "category": "memory_latency",
        "requiredSignals": ["context_budget", "runtime_adapter", "conversation_length"],
        "dependencies": ["cognix-memory-manager", "cognix-runtime-adapter"],
        "estimatedBenefit": {"memory": "medium", "latency": "medium", "qualityRisk": "low"},
        "risk": "low",
        "runtimeSupport": ["llama.cpp", "ollama", "vllm", "transformers"],
        "hardwareSupport": ["small_local", "balanced_local", "powerful_local"],
        "experimental": False,
    },
    {
        "id": "semantic_cache",
        "label": "Semantic cache",
        "category": "latency_cost",
        "requiredSignals": ["embedding_model", "cache_policy", "privacy_policy"],
        "dependencies": ["cognix-memory-manager", "cognix-cache-manager"],
        "estimatedBenefit": {"latency": "medium", "cost": "medium", "qualityRisk": "medium"},
        "risk": "medium",
        "runtimeSupport": ["llama.cpp", "ollama", "vllm", "transformers", "dry_run"],
        "hardwareSupport": ["small_local", "balanced_local", "powerful_local"],
        "experimental": True,
    },
    {
        "id": "prompt_compression",
        "label": "Prompt compression",
        "category": "context",
        "requiredSignals": ["context_budget", "message_importance", "quality_eval"],
        "dependencies": ["cognix-memory-manager"],
        "estimatedBenefit": {"memory": "medium", "latency": "medium", "qualityRisk": "medium"},
        "risk": "medium",
        "runtimeSupport": ["llama.cpp", "ollama", "vllm", "transformers", "dry_run"],
        "hardwareSupport": ["small_local", "balanced_local", "powerful_local"],
        "experimental": False,
    },
    {
        "id": "rag_compression",
        "label": "RAG compression",
        "category": "rag",
        "requiredSignals": ["retrieval_plan", "citation_policy", "quality_eval"],
        "dependencies": ["cognix-rag", "cognix-memory-manager"],
        "estimatedBenefit": {"latency": "medium", "context": "high", "qualityRisk": "medium"},
        "risk": "medium",
        "runtimeSupport": ["llama.cpp", "ollama", "vllm", "transformers", "dry_run"],
        "hardwareSupport": ["small_local", "balanced_local", "powerful_local"],
        "experimental": False,
    },
    {
        "id": "speculative_decoding",
        "label": "Speculative decoding",
        "category": "latency",
        "requiredSignals": ["draft_model", "runtime_support", "acceptance_rate"],
        "dependencies": ["cognix-model-lifecycle", "cognix-runtime-adapter"],
        "estimatedBenefit": {"latency": "high", "memory": "low", "qualityRisk": "medium"},
        "risk": "high",
        "runtimeSupport": ["llama.cpp", "vllm"],
        "hardwareSupport": ["powerful_local"],
        "experimental": True,
    },
    {
        "id": "batching",
        "label": "Batching",
        "category": "throughput",
        "requiredSignals": ["worker_queue", "multi_user_load", "latency_slo"],
        "dependencies": ["cognix-worker-queue", "cognix-deployment-manager"],
        "estimatedBenefit": {"throughput": "high", "latencyRisk": "medium", "qualityRisk": "low"},
        "risk": "medium",
        "runtimeSupport": ["vllm", "transformers", "dry_run"],
        "hardwareSupport": ["powerful_local"],
        "experimental": True,
    },
    {
        "id": "lora_qlora",
        "label": "LoRA/QLoRA adapters",
        "category": "training",
        "requiredSignals": ["dataset_quality", "training_budget", "eval_baseline"],
        "dependencies": ["cognix-fine-tuning", "cognix-worker-queue"],
        "estimatedBenefit": {"specialization": "high", "qualityRisk": "high"},
        "risk": "high",
        "runtimeSupport": ["transformers", "dry_run"],
        "hardwareSupport": ["balanced_local", "powerful_local"],
        "experimental": False,
    },
]

OPTIMIZATION_ALIASES = {
    "quantization_profile": "quantization",
    "prompt_cache": "semantic_cache",
    "kv_cache_policy": "kv_cache_eviction",
}


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


def _benchmark_available(latest_benchmark_run: dict[str, Any] | None) -> bool:
    if not isinstance(latest_benchmark_run, dict):
        return False
    return bool(
        latest_benchmark_run.get("benchmark")
        or latest_benchmark_run.get("benchmark_json")
        or latest_benchmark_run.get("id")
    )


def _normalized_capability_id(value: str) -> str:
    capability_id = str(value or "").strip().lower().replace("-", "_")
    return OPTIMIZATION_ALIASES.get(capability_id, capability_id)


def _capability_lookup() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in OPTIMIZATION_CAPABILITIES}


def _capability_compatible(
    capability: dict[str, Any],
    *,
    hardware_tier: str,
    runtime_type: str,
) -> tuple[bool, str]:
    hardware_support = {str(item) for item in capability.get("hardwareSupport") or []}
    runtime_support = {str(item) for item in capability.get("runtimeSupport") or []}
    if hardware_tier not in hardware_support:
        return False, f"Hardware tier {hardware_tier} non supporte pour cette optimisation."
    if runtime_type not in runtime_support and "dry_run" not in runtime_support:
        return False, f"Runtime {runtime_type} non supporte ou non confirme."
    return True, "Compatible avec le profil courant avant benchmark."


def _capability_record(
    capability: dict[str, Any],
    *,
    hardware_tier: str,
    runtime_type: str,
    benchmark_ready: bool,
) -> dict[str, Any]:
    compatible, reason = _capability_compatible(
        capability,
        hardware_tier = hardware_tier,
        runtime_type = runtime_type,
    )
    experimental = bool(capability.get("experimental"))
    status = "blocked_incompatible"
    if compatible and experimental:
        status = "experimental"
    elif compatible:
        status = "available"
    return {
        "id": capability["id"],
        "label": capability["label"],
        "category": capability["category"],
        "status": status,
        "compatible": compatible,
        "experimental": experimental,
        "hardwareFit": {
            "tier": hardware_tier,
            "compatible": compatible,
            "reason": reason,
        },
        "runtimeFit": {
            "runtimeType": runtime_type,
            "supportedRuntimeTypes": capability.get("runtimeSupport", []),
        },
        "requiredSignals": capability.get("requiredSignals", []),
        "dependencies": capability.get("dependencies", []),
        "estimatedBenefit": capability.get("estimatedBenefit", {}),
        "risk": capability.get("risk", "medium"),
        "benchmarkRequired": True,
        "benchmarkGate": {
            "requiredBeforeEnable": True,
            "latestBenchmarkAvailable": benchmark_ready,
            "status": "satisfied" if benchmark_ready else "required",
        },
        "activationPolicy": {
            "automaticEnableAllowed": False,
            "requiresRollbackPlan": True,
            "requiresHumanConfirmation": True,
            "experimentalModuleRequired": experimental,
        },
        "sideEffects": {
            "runtimeConfigWrite": False,
            "benchmarkRun": False,
            "modelLoad": False,
            "cacheMutation": False,
            "networkCall": False,
            "codeModification": False,
        },
    }


def build_optimization_capability_registry(
    *,
    hardware: dict[str, Any],
    recommendation: dict[str, Any],
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hardware_tier = _hardware_tier(hardware)
    runtime_type = str(recommendation.get("providerType") or "dry_run")
    benchmark_ready = _benchmark_available(latest_benchmark_run)
    capabilities = [
        _capability_record(
            item,
            hardware_tier = hardware_tier,
            runtime_type = runtime_type,
            benchmark_ready = benchmark_ready,
        )
        for item in OPTIMIZATION_CAPABILITIES
    ]
    recommended = [
        item["id"]
        for item in capabilities
        if item["compatible"] and item["status"] in {"available", "experimental"}
    ]
    return {
        "plannerVersion": COGNIX_OPTIMIZATION_PLANNER_VERSION,
        "registryVersion": COGNIX_OPTIMIZATION_CAPABILITY_REGISTRY_VERSION,
        "mode": "dry_run",
        "hardwareTier": hardware_tier,
        "runtimeType": runtime_type,
        "benchmarkReady": benchmark_ready,
        "summary": {
            "capabilityCount": len(capabilities),
            "compatibleCount": sum(1 for item in capabilities if item["compatible"]),
            "experimentalCount": sum(1 for item in capabilities if item["experimental"]),
            "benchmarkRequiredBeforeEnable": True,
        },
        "policies": {
            "benchmarkRequiredBeforeEnable": True,
            "modelMetadataRequired": True,
            "frontendDirectOptimizationMutationAllowed": False,
            "experimentalModulesRequireManifest": True,
            "rollbackPlanRequired": True,
        },
        "recommendedCapabilityIds": recommended,
        "capabilities": capabilities,
        "sideEffects": {
            "runtimeConfigWrite": False,
            "benchmarkRun": False,
            "modelLoad": False,
            "cacheMutation": False,
            "networkCall": False,
            "codeModification": False,
        },
    }


def _experiment_gates(
    capability: dict[str, Any],
    *,
    benchmark_ready: bool,
    compatible: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "model_metadata",
            "status": "required",
            "requiredBefore": "experiment",
        },
        {
            "id": "hardware_fit",
            "status": "pass" if compatible else "blocked",
            "requiredBefore": "experiment",
        },
        {
            "id": "benchmark_baseline",
            "status": "pass" if benchmark_ready else "blocked",
            "requiredBefore": "enablement",
        },
        {
            "id": "rollback_plan",
            "status": "planned",
            "requiredBefore": "enablement",
        },
        {
            "id": "experimental_manifest",
            "status": "required" if capability.get("experimental") else "not_required",
            "requiredBefore": "enablement",
        },
    ]


def build_optimization_experiment_plan(
    *,
    objective: str,
    hardware: dict[str, Any],
    recommendation: dict[str, Any],
    latest_benchmark_run: dict[str, Any] | None = None,
    requested_optimizations: list[str] | None = None,
) -> dict[str, Any]:
    registry = build_optimization_capability_registry(
        hardware = hardware,
        recommendation = recommendation,
        latest_benchmark_run = latest_benchmark_run,
    )
    lookup = {item["id"]: item for item in registry["capabilities"]}
    requested = [
        _normalized_capability_id(item)
        for item in (requested_optimizations or registry["recommendedCapabilityIds"])
    ]
    selected_ids = [
        item
        for item in dict.fromkeys(requested)
        if item in lookup
    ]
    benchmark_ready = bool(registry["benchmarkReady"])
    tickets: list[dict[str, Any]] = []
    for capability_id in selected_ids:
        capability = lookup[capability_id]
        compatible = bool(capability.get("compatible"))
        gates = _experiment_gates(
            capability,
            benchmark_ready = benchmark_ready,
            compatible = compatible,
        )
        blocked_gate_ids = [
            str(gate["id"])
            for gate in gates
            if gate["status"] == "blocked"
        ]
        status = "ready_for_experiment" if compatible and benchmark_ready else "blocked_by_gates"
        tickets.append(
            {
                "id": f"experiment_{capability_id}",
                "capabilityId": capability_id,
                "label": capability["label"],
                "status": status,
                "blockedGateIds": blocked_gate_ids,
                "gates": gates,
                "measurableMetrics": [
                    "latency_ms",
                    "tokens_per_second",
                    "memory_peak_gb",
                    "quality_regression_score",
                ],
                "rollbackPlan": {
                    "required": True,
                    "strategy": "feature_flag_disable_and_restore_previous_runtime_profile",
                    "testedBeforeEnable": False,
                },
                "willEnableRuntime": False,
                "willRunBenchmark": False,
                "willModifyCache": False,
            }
        )

    blocked_gate_ids = sorted(
        {
            gate_id
            for ticket in tickets
            for gate_id in ticket.get("blockedGateIds", [])
        }
    )
    return {
        "plannerVersion": COGNIX_OPTIMIZATION_PLANNER_VERSION,
        "experimentPlanVersion": COGNIX_OPTIMIZATION_EXPERIMENT_PLAN_VERSION,
        "registryVersion": registry["registryVersion"],
        "mode": "dry_run",
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "hardwareTier": registry["hardwareTier"],
        "runtimeType": registry["runtimeType"],
        "benchmarkReady": benchmark_ready,
        "requestedOptimizationIds": requested,
        "selectedOptimizationIds": selected_ids,
        "tickets": tickets,
        "summary": {
            "ticketCount": len(tickets),
            "readyTicketCount": sum(1 for item in tickets if item["status"] == "ready_for_experiment"),
            "blockedTicketCount": sum(1 for item in tickets if item["status"] != "ready_for_experiment"),
            "blockedGateIds": blocked_gate_ids,
        },
        "policies": registry["policies"],
        "sideEffects": {
            "runtimeConfigWrite": False,
            "benchmarkRun": False,
            "modelLoad": False,
            "cacheMutation": False,
            "networkCall": False,
            "codeModification": False,
            "generation": False,
        },
    }


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
