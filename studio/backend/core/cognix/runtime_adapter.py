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

    return {
        "runtimeAdapterVersion": COGNIX_RUNTIME_ADAPTER_VERSION,
        "mode": "dry_run",
        "requestedRuntimeType": requested_runtime,
        "selectedAdapter": selected,
        "selectedCapabilities": _as_dict(selected_adapter.get("supports")),
        "requiredCapabilities": sorted(required),
        "candidateAdapters": candidates,
        "adapterPolicies": registry["globalPolicies"],
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
