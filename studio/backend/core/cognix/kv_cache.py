# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX KV-cache eviction planning.

The planner turns context blocks, runtime capability signals, and benchmark
evidence into an auditable KV-cache policy contract. It never reads a live
KV-cache, mutates runtime flags, evicts tokens, summarizes text, loads a model,
or generates tokens.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.cognix.benchmark import COGNIX_BENCHMARK_VERSION


COGNIX_KV_CACHE_EVICTION_PLAN_VERSION = "cognix_kv_cache_eviction_plan_v1"
COGNIX_KV_CACHE_POLICY_CONTRACT_VERSION = "cognix_kv_cache_policy_contract_v1"
COGNIX_CONTEXT_RETENTION_POLICY_VERSION = "cognix_context_retention_policy_v1"

DIRECT_KV_RUNTIME_TYPES = {"llama.cpp", "llama-cpp", "vllm", "transformers"}
OPAQUE_KV_RUNTIME_TYPES = {"ollama", "cloud_api", "openai", "anthropic"}
PROTECTED_BLOCK_TYPES = {"system", "policy", "developer", "safety", "project_summary"}
RECENT_BLOCK_TYPES = {"user_message", "assistant_message", "tool_result"}
NOISY_BLOCK_TYPES = {"debug_log", "terminal_output", "stack_trace", "raw_history", "scratchpad"}
REQUIRED_BENCHMARK_METRICS = ("overallScore", "estimatedTokensPerSecond")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _as_int(value: Any, default: int = 0) -> int:
    return int(_as_float(value, float(default)))


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runtime_type(runtime_adapter: dict[str, Any] | None) -> str:
    adapter = _as_dict(runtime_adapter)
    selected = _as_dict(adapter.get("selectedAdapter"))
    return str(
        adapter.get("runtimeType")
        or adapter.get("selectedRuntimeType")
        or selected.get("runtimeType")
        or selected.get("adapterId")
        or adapter.get("adapterId")
        or ""
    ).strip().casefold()


def _model_id(model: dict[str, Any] | None) -> str:
    item = _as_dict(model)
    return str(item.get("modelId") or item.get("id") or item.get("name") or "").strip()[:240]


def _benchmark_payload(latest_benchmark_run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(latest_benchmark_run, dict):
        return {}
    raw = latest_benchmark_run.get("benchmark")
    if raw is None:
        raw = latest_benchmark_run.get("benchmark_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _benchmark_contract(latest_benchmark_run: dict[str, Any] | None) -> dict[str, Any]:
    run_present = isinstance(latest_benchmark_run, dict)
    payload = _benchmark_payload(latest_benchmark_run)
    benchmark_version = str(payload.get("benchmarkVersion") or "")
    observed = [
        metric
        for metric in REQUIRED_BENCHMARK_METRICS
        if _as_float(payload.get(metric), -1.0) >= 0
    ]
    missing = [metric for metric in REQUIRED_BENCHMARK_METRICS if metric not in observed]
    if not run_present:
        status = "missing"
    elif not payload:
        status = "incomplete_payload"
    elif benchmark_version != COGNIX_BENCHMARK_VERSION:
        status = "unsupported_version"
    elif missing:
        status = "insufficient_metrics"
    else:
        status = "ready"
    return {
        "status": status,
        "ready": status == "ready",
        "runId": latest_benchmark_run.get("id") if isinstance(latest_benchmark_run, dict) else None,
        "benchmarkVersion": benchmark_version or None,
        "expectedBenchmarkVersion": COGNIX_BENCHMARK_VERSION,
        "requiredMetricIds": list(REQUIRED_BENCHMARK_METRICS),
        "observedMetricIds": observed,
        "missingMetricIds": missing,
        "sideEffects": {
            "benchmarkRun": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def _context_limits(context_plan: dict[str, Any] | None, model: dict[str, Any] | None, target_token_budget: int | None) -> dict[str, int]:
    context = _as_dict(context_plan)
    token_budget = _as_dict(context.get("tokenBudget"))
    model_data = _as_dict(model)
    max_context = (
        _as_int(target_token_budget)
        or _as_int(token_budget.get("maxContextTokens"))
        or _as_int(model_data.get("contextLength"))
        or _as_int(model_data.get("maxContextTokens"))
        or 4096
    )
    reserve = max(256, min(2048, int(max_context * 0.18)))
    retain_budget = max(256, max_context - reserve)
    soft_limit = int(retain_budget * 0.86)
    return {
        "maxContextTokens": max_context,
        "generationReserveTokens": reserve,
        "retentionBudgetTokens": retain_budget,
        "softRetentionLimitTokens": soft_limit,
    }


def _block_id(block: dict[str, Any], index: int) -> str:
    raw_id = str(block.get("id") or block.get("blockId") or "").strip()
    if raw_id:
        return raw_id[:120]
    seed = "|".join(
        [
            str(block.get("type") or "context"),
            str(block.get("source") or ""),
            str(block.get("contentHash") or block.get("hash") or ""),
            str(index),
        ]
    )
    return "ctx_" + _stable_hash(seed)[:14]


def _block_token_count(block: dict[str, Any]) -> int:
    if "tokenCount" in block:
        return _as_int(block.get("tokenCount"), 0)
    if "tokens" in block:
        return _as_int(block.get("tokens"), 0)
    text = str(block.get("content") or block.get("text") or "")
    return max(1, len(text.split())) if text else 0


def _block_priority(block: dict[str, Any], index: int, total: int) -> float:
    block_type = str(block.get("type") or block.get("kind") or "context").strip().casefold()
    explicit = _as_float(block.get("importance"), -1.0)
    if explicit >= 0:
        base = min(explicit, 1.0)
    elif block_type in PROTECTED_BLOCK_TYPES:
        base = 0.94
    elif block_type in {"user_memory", "project_memory", "rag_chunk"}:
        base = 0.72
    elif block_type in RECENT_BLOCK_TYPES:
        base = 0.62
    elif block_type in NOISY_BLOCK_TYPES:
        base = 0.22
    else:
        base = 0.5
    recency_boost = 0.16 * ((index + 1) / max(total, 1))
    if bool(block.get("pinned") or block.get("protected")):
        base += 0.18
    if bool(block.get("hasCitation") or block.get("requiresCitation")):
        base += 0.08
    if bool(block.get("sensitive")):
        base -= 0.08
    if block_type in NOISY_BLOCK_TYPES:
        base -= 0.12
    return round(max(0.0, min(1.0, base + recency_boost)), 3)


def _retention_action(block: dict[str, Any], priority: float, running_tokens: int, limits: dict[str, int]) -> str:
    block_type = str(block.get("blockType") or block.get("type") or block.get("kind") or "context").strip().casefold()
    tokens = _block_token_count(block)
    if block_type in PROTECTED_BLOCK_TYPES or bool(block.get("pinned") or block.get("protected")):
        return "pin"
    if block_type in NOISY_BLOCK_TYPES and priority < 0.45:
        return "evict_from_kv"
    if running_tokens + tokens <= limits["softRetentionLimitTokens"] and priority >= 0.48:
        return "retain"
    if priority >= 0.58:
        return "summarize_then_retain"
    return "evict_from_kv"


def _rank_context_blocks(context_blocks: list[dict[str, Any]], limits: dict[str, int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total = len(context_blocks)
    analyzed: list[dict[str, Any]] = []
    for index, raw_block in enumerate(context_blocks):
        block = _as_dict(raw_block)
        block_type = str(block.get("type") or block.get("kind") or "context").strip().casefold() or "context"
        token_count = _block_token_count(block)
        content_hash = str(block.get("contentHash") or block.get("hash") or "").strip()
        if not content_hash:
            raw_content = str(block.get("content") or block.get("text") or "")
            content_hash = _stable_hash(raw_content) if raw_content else _stable_hash(f"{block_type}:{index}:{token_count}")
        analyzed.append(
            {
                "blockId": _block_id(block, index),
                "blockType": block_type,
                "tokenCount": token_count,
                "contentHash": content_hash[:64],
                "sourceRef": str(block.get("sourceRef") or block.get("source") or "").strip()[:160] or None,
                "priorityScore": _block_priority(block, index, total),
                "pinned": bool(block.get("pinned") or block.get("protected")),
                "containsRawContent": False,
            }
        )
    analyzed.sort(key = lambda item: (item["pinned"], item["priorityScore"], -item["tokenCount"]), reverse = True)
    running = 0
    decisions: list[dict[str, Any]] = []
    for item in analyzed:
        action = _retention_action(item, item["priorityScore"], running, limits)
        retained_tokens = item["tokenCount"] if action in {"pin", "retain"} else int(item["tokenCount"] * 0.35) if action == "summarize_then_retain" else 0
        running += retained_tokens
        decisions.append(
            {
                **item,
                "action": action,
                "estimatedRetainedTokens": retained_tokens,
                "willMutateNow": False,
            }
        )
    summary = {
        "blockCount": len(decisions),
        "inputTokenCount": sum(item["tokenCount"] for item in decisions),
        "estimatedRetainedTokens": sum(item["estimatedRetainedTokens"] for item in decisions),
        "pinCount": sum(1 for item in decisions if item["action"] == "pin"),
        "retainCount": sum(1 for item in decisions if item["action"] == "retain"),
        "summarizeCount": sum(1 for item in decisions if item["action"] == "summarize_then_retain"),
        "evictCount": sum(1 for item in decisions if item["action"] == "evict_from_kv"),
    }
    return decisions, summary


def build_kv_cache_eviction_plan(
    *,
    username: str,
    objective: str,
    context_blocks: list[dict[str, Any]] | None = None,
    context_plan: dict[str, Any] | None = None,
    runtime_adapter: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    project_id: str | None = None,
    target_token_budget: int | None = None,
) -> dict[str, Any]:
    runtime = _runtime_type(runtime_adapter)
    runtime_known = bool(runtime)
    direct_kv_supported = runtime in DIRECT_KV_RUNTIME_TYPES
    opaque_runtime = runtime in OPAQUE_KV_RUNTIME_TYPES
    model_ref = _model_id(model)
    limits = _context_limits(context_plan, model, target_token_budget)
    blocks = [_as_dict(item) for item in _as_list(context_blocks) if isinstance(item, dict)]
    decisions, retention_summary = _rank_context_blocks(blocks, limits)
    benchmark = _benchmark_contract(latest_benchmark_run)
    needs_eviction = retention_summary["inputTokenCount"] > limits["softRetentionLimitTokens"] or retention_summary["evictCount"] > 0
    policy_mode = (
        "direct_kv_eviction_contract"
        if direct_kv_supported
        else "context_level_retention_contract"
        if opaque_runtime or runtime_known
        else "runtime_unknown_context_retention_contract"
    )
    gates = [
        {
            "id": "runtime_declared",
            "status": "pass" if runtime_known else "blocked",
            "requiredBefore": "activation",
        },
        {
            "id": "context_blocks_present",
            "status": "pass" if bool(decisions) else "blocked",
            "requiredBefore": "activation",
        },
        {
            "id": "context_budget_declared",
            "status": "pass" if limits["maxContextTokens"] > 0 else "blocked",
            "requiredBefore": "activation",
        },
        {
            "id": "benchmark_baseline_ready",
            "status": "pass" if benchmark["ready"] else "blocked",
            "requiredBefore": "enablement",
            "benchmarkStatus": benchmark["status"],
        },
        {
            "id": "runtime_direct_kv_supported",
            "status": "pass" if direct_kv_supported else "warning" if runtime_known else "blocked",
            "requiredBefore": "direct_kv_eviction",
            "runtimeType": runtime or "unknown",
        },
    ]
    blocked_gate_ids = [str(item["id"]) for item in gates if item.get("status") == "blocked"]
    warning_gate_ids = [str(item["id"]) for item in gates if item.get("status") == "warning"]
    ready_for_policy_review = bool(decisions) and runtime_known and limits["maxContextTokens"] > 0
    ready_for_activation = ready_for_policy_review and benchmark["ready"] and direct_kv_supported
    return {
        "kvCacheEvictionPlanVersion": COGNIX_KV_CACHE_EVICTION_PLAN_VERSION,
        "policyContractVersion": COGNIX_KV_CACHE_POLICY_CONTRACT_VERSION,
        "contextRetentionPolicyVersion": COGNIX_CONTEXT_RETENTION_POLICY_VERSION,
        "mode": "kv_cache_eviction_plan_dry_run",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "status": "ready_for_activation" if ready_for_activation else "ready_for_policy_review" if ready_for_policy_review else "blocked_by_gates",
        "readyForPolicyReview": ready_for_policy_review,
        "readyForActivation": ready_for_activation,
        "policyMode": policy_mode,
        "runtime": {
            "runtimeType": runtime or "unknown",
            "directKvControlSupported": direct_kv_supported,
            "opaqueKvRuntime": opaque_runtime,
            "fallbackToContextRetention": not direct_kv_supported,
        },
        "model": {
            "modelId": model_ref or None,
            "contextLength": limits["maxContextTokens"],
        },
        "tokenBudget": limits,
        "retentionPlan": {
            "needsEviction": needs_eviction,
            "strategy": "priority_recency_pinning",
            "rawContentStored": False,
            "decisions": decisions,
            "summary": retention_summary,
        },
        "policyContract": {
            "contractVersion": COGNIX_KV_CACHE_POLICY_CONTRACT_VERSION,
            "automaticEvictionAllowed": False,
            "frontendDirectKvMutationAllowed": False,
            "runtimeFlagWriteAllowed": False,
            "contextSummaryRequiredBeforeEvicting": retention_summary["summarizeCount"] > 0,
            "benchmarkBeforeActivationRequired": True,
            "blockedActions": [
                "kv_cache_read",
                "kv_cache_write",
                "kv_cache_eviction",
                "runtime_flag_write",
                "context_summarization",
                "model_load",
                "generation",
            ],
        },
        "benchmarkEvidence": benchmark,
        "gates": gates,
        "summary": {
            "blockedGateIds": blocked_gate_ids,
            "warningGateIds": warning_gate_ids,
            "needsEviction": needs_eviction,
            "estimatedTokenReduction": max(0, retention_summary["inputTokenCount"] - retention_summary["estimatedRetainedTokens"]),
            "recommendedRuntimeAction": "direct_kv_policy_after_benchmark" if direct_kv_supported else "context_manager_retention_policy",
        },
        "sideEffects": {
            "kvCacheRead": False,
            "kvCacheWrite": False,
            "kvCacheEviction": False,
            "runtimeConfigWrite": False,
            "runtimeFlagWrite": False,
            "contextSummarization": False,
            "memoryWrite": False,
            "modelLoad": False,
            "generation": False,
            "benchmarkRun": False,
        },
    }
