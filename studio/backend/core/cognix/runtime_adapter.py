# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX model runtime adapter planning.

The adapter planner chooses a compatible runtime path from declarative
capabilities. It never starts a server, checks external network state, changes
runtime flags, loads a model, or generates tokens.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_RUNTIME_ADAPTER_VERSION = "cognix_runtime_adapter_v1"
COGNIX_RUNTIME_OPTIMIZATION_CONTRACT_VERSION = "cognix_runtime_optimization_contract_v1"


OPTIMIZATION_CAPABILITY_MAP: dict[str, dict[str, Any]] = {
    "prompt_cache": {
        "capability": "promptCaching",
        "label": "Prompt caching",
        "benchmarkMetric": "first_token_latency_and_prompt_eval_ms",
    },
    "kv_cache_policy": {
        "capability": "kvCacheTuning",
        "label": "KV-cache policy",
        "benchmarkMetric": "long_context_latency_and_memory",
    },
    "speculative_decoding": {
        "capability": "speculativeDecoding",
        "label": "Speculative decoding",
        "benchmarkMetric": "tokens_per_second_and_quality_delta",
    },
    "batching": {
        "capability": "multiUserBatching",
        "label": "Multi-user batching",
        "benchmarkMetric": "throughput_under_concurrent_load",
    },
}


RUNTIME_ADAPTERS: list[dict[str, Any]] = [
    {
        "id": "ollama",
        "label": "Ollama",
        "runtimeType": "ollama",
        "deploymentTarget": "local",
        "modelFormats": ["gguf", "ollama_manifest"],
        "strengths": ["simple_local_setup", "openai_compatible_chat", "cpu_friendly"],
        "supports": {
            "streaming": True,
            "toolCalling": False,
            "ragContextInjection": True,
            "promptCaching": False,
            "kvCacheTuning": False,
            "speculativeDecoding": False,
            "multiUserBatching": False,
            "fineTuning": False,
        },
        "riskLevel": "low",
    },
    {
        "id": "llama-cpp",
        "label": "llama.cpp server",
        "runtimeType": "llama.cpp",
        "deploymentTarget": "local",
        "modelFormats": ["gguf"],
        "strengths": ["fine_grained_runtime_flags", "cpu_gpu_split", "kv_cache_control"],
        "supports": {
            "streaming": True,
            "toolCalling": False,
            "ragContextInjection": True,
            "promptCaching": True,
            "kvCacheTuning": True,
            "speculativeDecoding": True,
            "multiUserBatching": False,
            "fineTuning": False,
        },
        "riskLevel": "medium",
    },
    {
        "id": "vllm",
        "label": "vLLM",
        "runtimeType": "vllm",
        "deploymentTarget": "server_gpu",
        "modelFormats": ["safetensors", "hf_transformers"],
        "strengths": ["high_throughput", "paged_attention", "multi_user_serving"],
        "supports": {
            "streaming": True,
            "toolCalling": True,
            "ragContextInjection": True,
            "promptCaching": True,
            "kvCacheTuning": True,
            "speculativeDecoding": True,
            "multiUserBatching": True,
            "fineTuning": False,
        },
        "riskLevel": "medium",
    },
    {
        "id": "transformers",
        "label": "Transformers local",
        "runtimeType": "transformers",
        "deploymentTarget": "local_or_server",
        "modelFormats": ["safetensors", "hf_transformers"],
        "strengths": ["research_flexibility", "fine_tuning_bridge", "custom_pipelines"],
        "supports": {
            "streaming": True,
            "toolCalling": False,
            "ragContextInjection": True,
            "promptCaching": False,
            "kvCacheTuning": False,
            "speculativeDecoding": False,
            "multiUserBatching": False,
            "fineTuning": True,
        },
        "riskLevel": "medium",
    },
    {
        "id": "cloud-openai-compatible",
        "label": "Cloud OpenAI-compatible",
        "runtimeType": "cloud",
        "deploymentTarget": "cloud",
        "modelFormats": ["provider_api"],
        "strengths": ["fallback_quality", "large_models", "managed_scaling"],
        "supports": {
            "streaming": True,
            "toolCalling": True,
            "ragContextInjection": True,
            "promptCaching": True,
            "kvCacheTuning": False,
            "speculativeDecoding": False,
            "multiUserBatching": True,
            "fineTuning": False,
        },
        "riskLevel": "high",
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _capability_score(adapter: dict[str, Any], required: set[str]) -> int:
    supports = _as_dict(adapter.get("supports"))
    return sum(1 for capability in required if bool(supports.get(capability)))


def _required_capabilities(
    *,
    task_strategy: dict[str, Any],
    rag_plan: dict[str, Any],
    fine_tuning_plan: dict[str, Any],
    optimization_plan: dict[str, Any],
) -> set[str]:
    required = {"streaming", "ragContextInjection"}
    if task_strategy.get("path") == "tool_plan":
        required.add("toolCalling")
    if bool(rag_plan.get("readyForRetrieval")):
        required.add("ragContextInjection")
    if str(fine_tuning_plan.get("recommendedPath") or "") in {"fine_tune", "guided_fine_tuning"}:
        required.add("fineTuning")
    for optimization_id in optimization_plan.get("recommendedOptimizationIds") or []:
        if optimization_id == "prompt_cache":
            required.add("promptCaching")
        elif optimization_id == "kv_cache_policy":
            required.add("kvCacheTuning")
        elif optimization_id == "speculative_decoding":
            required.add("speculativeDecoding")
        elif optimization_id == "batching":
            required.add("multiUserBatching")
    return required


def _requested_optimizations(optimization_plan: dict[str, Any]) -> list[str]:
    requested: list[str] = []
    for key in ("recommendedOptimizationIds", "requestedOptimizationIds", "enabledOptimizationIds"):
        for item in optimization_plan.get(key) or []:
            optimization_id = str(item or "").strip()
            if optimization_id and optimization_id not in requested:
                requested.append(optimization_id)
    return requested


def _optimization_contract(
    *,
    selected_adapter: dict[str, Any],
    selected_candidate: dict[str, Any],
    optimization_plan: dict[str, Any],
) -> dict[str, Any]:
    requested = _requested_optimizations(optimization_plan)
    supports = _as_dict(selected_adapter.get("supports"))
    checks: list[dict[str, Any]] = []
    compatible: list[str] = []
    blocked: list[str] = []
    unknown: list[str] = []
    for optimization_id in requested:
        definition = OPTIMIZATION_CAPABILITY_MAP.get(optimization_id)
        if not definition:
            unknown.append(optimization_id)
            checks.append(
                {
                    "id": optimization_id,
                    "status": "unknown_optimization",
                    "activationAllowedHere": False,
                    "reason": "Optimization is not declared in the native CogniX runtime contract.",
                }
            )
            continue
        capability = str(definition["capability"])
        is_supported = bool(supports.get(capability))
        if is_supported:
            compatible.append(optimization_id)
        else:
            blocked.append(optimization_id)
        checks.append(
            {
                "id": optimization_id,
                "label": definition["label"],
                "capability": capability,
                "status": "compatible_requires_benchmark" if is_supported else "blocked_missing_runtime_capability",
                "activationAllowedHere": False,
                "runtimeFlagMutationAllowed": False,
                "benchmarkRequired": is_supported,
                "benchmarkMetric": definition["benchmarkMetric"],
                "reason": (
                    "Runtime declares the required capability; benchmark and rollback review are still required."
                    if is_supported
                    else "Selected runtime adapter does not declare the capability required for this optimization."
                ),
            }
        )
    return {
        "contractVersion": COGNIX_RUNTIME_OPTIMIZATION_CONTRACT_VERSION,
        "mode": "runtime_optimization_compatibility_dry_run",
        "selectedAdapterId": selected_candidate.get("adapterId"),
        "selectedRuntimeType": selected_candidate.get("runtimeType"),
        "requestedOptimizationIds": requested,
        "compatibleOptimizationIds": compatible,
        "blockedOptimizationIds": blocked,
        "unknownOptimizationIds": unknown,
        "checks": checks,
        "activationContract": {
            "automaticActivationAllowed": False,
            "runtimeMutationAllowed": False,
            "runtimeFlagWriteAllowed": False,
            "modelReloadAllowed": False,
            "benchmarkRequiredBeforeActivation": bool(compatible),
            "rollbackPlanRequired": bool(compatible),
            "humanApprovalRequired": bool(compatible or blocked or unknown),
        },
        "evidenceRequirements": [
            "runtime_adapter_selected",
            "compatibility_check_recorded",
            "benchmark_before_after_required",
            "rollback_plan_required",
            "no_runtime_mutation_during_planning",
        ],
        "sideEffects": {
            "runtimeMutation": False,
            "runtimeFlagWrite": False,
            "modelReload": False,
            "benchmarkRun": False,
            "generation": False,
        },
    }


def build_runtime_adapter_registry() -> dict[str, Any]:
    adapters = deepcopy(RUNTIME_ADAPTERS)
    return {
        "runtimeAdapterVersion": COGNIX_RUNTIME_ADAPTER_VERSION,
        "mode": "declarative",
        "adapters": adapters,
        "summary": {
            "adapterCount": len(adapters),
            "localAdapterCount": sum(1 for item in adapters if str(item.get("deploymentTarget")).startswith("local")),
            "serverAdapterCount": sum(1 for item in adapters if item.get("deploymentTarget") == "server_gpu"),
            "cloudAdapterCount": sum(1 for item in adapters if item.get("deploymentTarget") == "cloud"),
            "directFrontendModelCallAllowed": False,
        },
        "globalPolicies": {
            "frontendMustUseBackend": True,
            "adapterSelectionAudited": True,
            "runtimeFlagsRequireCompatibilityCheck": True,
            "optimizationCompatibilityContractRequired": True,
            "optimizationContractVersion": COGNIX_RUNTIME_OPTIMIZATION_CONTRACT_VERSION,
            "networkReachabilityCheckedElsewhere": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "runtimeMutation": False,
        },
    }


def build_runtime_adapter_plan(
    *,
    recommendation: dict[str, Any],
    hardware: dict[str, Any],
    task_strategy: dict[str, Any] | None = None,
    rag_plan: dict[str, Any] | None = None,
    fine_tuning_plan: dict[str, Any] | None = None,
    optimization_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_strategy = _as_dict(task_strategy)
    rag_plan = _as_dict(rag_plan)
    fine_tuning_plan = _as_dict(fine_tuning_plan)
    optimization_plan = _as_dict(optimization_plan)
    requested_runtime = str(recommendation.get("providerType") or "unknown").strip().lower()
    hardware_gpu = bool(_as_dict(hardware.get("gpu")).get("available"))
    required = _required_capabilities(
        task_strategy = task_strategy,
        rag_plan = rag_plan,
        fine_tuning_plan = fine_tuning_plan,
        optimization_plan = optimization_plan,
    )

    registry = build_runtime_adapter_registry()
    candidates: list[dict[str, Any]] = []
    for adapter in registry["adapters"]:
        supports = _as_dict(adapter.get("supports"))
        missing = sorted(capability for capability in required if not bool(supports.get(capability)))
        runtime_match = requested_runtime in {str(adapter.get("runtimeType")).lower(), str(adapter.get("id")).lower()}
        local_penalty = 1 if adapter.get("deploymentTarget") == "server_gpu" and not hardware_gpu else 0
        score = _capability_score(adapter, required) + (3 if runtime_match else 0) - local_penalty
        candidates.append(
            {
                "adapterId": adapter.get("id"),
                "label": adapter.get("label"),
                "runtimeType": adapter.get("runtimeType"),
                "deploymentTarget": adapter.get("deploymentTarget"),
                "score": score,
                "runtimeMatch": runtime_match,
                "missingCapabilities": missing,
                "supportedCapabilities": sorted(
                    capability for capability in required if bool(supports.get(capability))
                ),
                "riskLevel": adapter.get("riskLevel"),
            }
        )

    candidates.sort(key = lambda item: (int(item.get("score") or 0), bool(item.get("runtimeMatch"))), reverse = True)
    selected = candidates[0] if candidates else {}
    selected_adapter = next(
        (adapter for adapter in registry["adapters"] if adapter.get("id") == selected.get("adapterId")),
        {},
    )
    warnings: list[str] = []
    if selected.get("missingCapabilities"):
        warnings.append("Adapter selectionne avec capacites manquantes: garder les fonctions avancees desactivees.")
    if requested_runtime == "ollama" and "speculativeDecoding" in required:
        warnings.append("Ollama ne confirme pas speculative decoding: fallback sans cette optimisation.")
    if selected.get("deploymentTarget") == "server_gpu" and not hardware_gpu:
        warnings.append("Adapter serveur GPU non adapte au materiel local actuel.")
    optimization_contract = _optimization_contract(
        selected_adapter = selected_adapter,
        selected_candidate = selected,
        optimization_plan = optimization_plan,
    )
    if optimization_contract["blockedOptimizationIds"]:
        warnings.append("Optimisations bloquees par compatibilite runtime: conserver le fallback.")

    return {
        "runtimeAdapterVersion": COGNIX_RUNTIME_ADAPTER_VERSION,
        "mode": "dry_run",
        "requestedRuntimeType": requested_runtime,
        "selectedAdapter": selected,
        "selectedCapabilities": _as_dict(selected_adapter.get("supports")),
        "requiredCapabilities": sorted(required),
        "candidateAdapters": candidates,
        "adapterPolicies": registry["globalPolicies"],
        "optimizationContract": optimization_contract,
        "warnings": warnings,
        "reason": "Adapter runtime choisi par compatibilite declarative, sans appel modele.",
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "runtimeMutation": False,
            "serverStart": False,
        },
    }
