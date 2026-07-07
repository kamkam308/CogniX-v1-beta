# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX prompt cache planning.

Prompt caching is useful only when a stable prefix can be reused safely by a
runtime that supports it. This planner builds that contract without writing
cache entries, changing runtime flags, storing raw prompt text, or generating.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.cognix.benchmark import COGNIX_BENCHMARK_VERSION


COGNIX_PROMPT_CACHE_PLAN_VERSION = "cognix_prompt_cache_plan_v1"
COGNIX_PROMPT_CACHE_POLICY_VERSION = "cognix_prompt_cache_policy_v1"
COGNIX_PROMPT_CACHE_RUNTIME_CONTRACT_VERSION = "cognix_prompt_cache_runtime_contract_v1"

PROMPT_CACHE_RUNTIME_TYPES = {"llama.cpp", "llama-cpp", "vllm", "transformers", "cloud_api", "openai", "anthropic"}
STABLE_SEGMENT_TYPES = {
    "developer",
    "memory_summary",
    "policy",
    "project_summary",
    "rag_header",
    "system",
    "tool_schema",
}
VOLATILE_SEGMENT_TYPES = {
    "assistant_message",
    "raw_history",
    "scratchpad",
    "tool_result",
    "user_message",
}
SENSITIVE_TERMS = {
    "api_key",
    "apikey",
    "bearer",
    "client_secret",
    "credential",
    "jwt",
    "mot de passe",
    "password",
    "private_key",
    "secret",
    "token",
}
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


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split())


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runtime_type(runtime_adapter: dict[str, Any] | None, model: dict[str, Any] | None) -> str:
    adapter = _as_dict(runtime_adapter)
    selected = _as_dict(adapter.get("selectedAdapter"))
    model_data = _as_dict(model)
    return str(
        adapter.get("runtimeType")
        or adapter.get("selectedRuntimeType")
        or selected.get("runtimeType")
        or selected.get("adapterId")
        or adapter.get("adapterId")
        or model_data.get("runtimeType")
        or model_data.get("runtime")
        or ""
    ).strip().casefold()


def _runtime_supports_prompt_cache(runtime_adapter: dict[str, Any] | None, model: dict[str, Any] | None) -> bool:
    adapter = _as_dict(runtime_adapter)
    selected = _as_dict(adapter.get("selectedAdapter"))
    capabilities = _as_dict(adapter.get("capabilities")) or _as_dict(selected.get("capabilities"))
    if "promptCaching" in capabilities:
        return bool(capabilities.get("promptCaching"))
    optimization_contract = _as_dict(adapter.get("optimizationContract"))
    if "prompt_cache" in _as_list(optimization_contract.get("compatibleOptimizationIds")):
        return True
    runtime = _runtime_type(runtime_adapter, model)
    return runtime in PROMPT_CACHE_RUNTIME_TYPES


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
    version = str(payload.get("benchmarkVersion") or "")
    observed = [metric for metric in REQUIRED_BENCHMARK_METRICS if _as_float(payload.get(metric), -1.0) >= 0]
    missing = [metric for metric in REQUIRED_BENCHMARK_METRICS if metric not in observed]
    if not run_present:
        status = "missing"
    elif not payload:
        status = "incomplete_payload"
    elif version != COGNIX_BENCHMARK_VERSION:
        status = "unsupported_version"
    elif missing:
        status = "insufficient_metrics"
    else:
        status = "ready"
    return {
        "status": status,
        "ready": status == "ready",
        "runId": latest_benchmark_run.get("id") if isinstance(latest_benchmark_run, dict) else None,
        "benchmarkVersion": version or None,
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


def _sensitivity(text: str, sensitivity_level: str | None) -> dict[str, Any]:
    normalized_level = str(sensitivity_level or "").strip().casefold()
    lower = text.casefold()
    matched_terms = sorted(term for term in SENSITIVE_TERMS if term in lower)
    if normalized_level in {"restricted", "secret", "highly_confidential"} or matched_terms:
        level = "restricted"
    elif normalized_level in {"confidential", "private", "sensitive"}:
        level = "confidential"
    elif normalized_level in {"public", "low"}:
        level = "public"
    else:
        level = "standard"
    return {
        "level": level,
        "matchedSensitiveTermIds": matched_terms[:12],
        "promptCacheAllowed": level in {"public", "standard"},
        "rawPromptStorageAllowed": False,
    }


def _section_segments_from_context(context_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    context = _as_dict(context_plan)
    sections = _as_list(context.get("sections")) or _as_list(context.get("contextSections"))
    segments: list[dict[str, Any]] = []
    for section in sections[:80]:
        item = _as_dict(section)
        segment_type = str(item.get("type") or item.get("sectionType") or item.get("kind") or "context").strip()
        content_hash = str(item.get("contentHash") or item.get("hash") or "").strip()
        content = str(item.get("content") or item.get("text") or "")
        segments.append(
            {
                "id": item.get("id") or item.get("sectionId"),
                "type": segment_type,
                "tokenCount": item.get("tokenCount") or item.get("tokens"),
                "contentHash": content_hash or (_stable_hash(content) if content else ""),
                "content": content,
                "stable": item.get("stable"),
            }
        )
    return segments


def _segment_id(segment: dict[str, Any], index: int) -> str:
    raw_id = str(segment.get("id") or segment.get("segmentId") or "").strip()
    if raw_id:
        return raw_id[:120]
    seed = f"{segment.get('type') or segment.get('kind') or 'segment'}:{index}:{segment.get('contentHash') or ''}"
    return "prompt_seg_" + _stable_hash(seed)[:14]


def _segment_token_count(segment: dict[str, Any]) -> int:
    if "tokenCount" in segment:
        return _as_int(segment.get("tokenCount"), 0)
    if "tokens" in segment:
        return _as_int(segment.get("tokens"), 0)
    text = str(segment.get("content") or segment.get("text") or "")
    return max(1, len(re.findall(r"\S+", text))) if text else 0


def _segment_stability(segment: dict[str, Any]) -> bool:
    explicit = segment.get("stable")
    if explicit is not None:
        return bool(explicit)
    segment_type = str(segment.get("type") or segment.get("kind") or "context").strip().casefold()
    if segment_type in VOLATILE_SEGMENT_TYPES:
        return False
    return segment_type in STABLE_SEGMENT_TYPES


def _analyze_segments(
    *,
    prompt_segments: list[dict[str, Any]] | None,
    context_plan: dict[str, Any] | None,
    objective: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_segments = [_as_dict(item) for item in _as_list(prompt_segments)]
    if not raw_segments:
        raw_segments = _section_segments_from_context(context_plan)
    if not raw_segments and objective:
        raw_segments = [{"id": "current_request", "type": "user_message", "content": objective, "stable": False}]

    analyzed: list[dict[str, Any]] = []
    stable_prefix_open = True
    stable_prefix_tokens = 0
    for index, segment in enumerate(raw_segments[:120]):
        segment_type = str(segment.get("type") or segment.get("kind") or "context").strip().casefold() or "context"
        token_count = _segment_token_count(segment)
        raw_content = str(segment.get("content") or segment.get("text") or "")
        content_hash = str(segment.get("contentHash") or segment.get("hash") or "").strip()
        if not content_hash:
            content_hash = _stable_hash(raw_content) if raw_content else _stable_hash(f"{segment_type}:{index}:{token_count}")
        stable = _segment_stability(segment)
        in_prefix = stable_prefix_open and stable
        if not stable:
            stable_prefix_open = False
        if in_prefix:
            stable_prefix_tokens += token_count
        if in_prefix and token_count > 0:
            action = "cache_prefix"
        elif stable and token_count > 0:
            action = "include_without_prefix_cache"
        else:
            action = "exclude_from_prompt_cache"
        analyzed.append(
            {
                "segmentId": _segment_id(segment, index),
                "segmentType": segment_type,
                "tokenCount": token_count,
                "contentHash": content_hash[:64],
                "stable": stable,
                "inStablePrefix": in_prefix,
                "cacheAction": action,
                "containsRawContent": False,
            }
        )
    summary = {
        "segmentCount": len(analyzed),
        "totalTokenCount": sum(item["tokenCount"] for item in analyzed),
        "stablePrefixSegmentCount": sum(1 for item in analyzed if item["inStablePrefix"]),
        "stablePrefixTokens": stable_prefix_tokens,
        "cacheCandidateCount": sum(1 for item in analyzed if item["cacheAction"] == "cache_prefix"),
    }
    return analyzed, summary


def _scope(username: str, project_id: str | None, sensitivity: dict[str, Any]) -> dict[str, Any]:
    scope_type = "project_private" if project_id and sensitivity["level"] in {"public", "standard"} else "user_private"
    source = f"{scope_type}:{username}:{project_id or 'general'}"
    return {
        "scopeType": scope_type,
        "namespaceHash": _stable_hash(source)[:24],
        "usernameBound": True,
        "projectBound": bool(project_id),
        "crossUserPrefixReuseAllowed": False,
        "organizationPrefixReuseAllowed": False,
    }


def _gate(gate_id: str, passed: bool, required: bool, reason: str, detail: Any = None) -> dict[str, Any]:
    if passed:
        status = "pass"
    elif required:
        status = "blocked"
    else:
        status = "warning"
    return {
        "id": gate_id,
        "status": status,
        "required": required,
        "passed": passed,
        "severity": "info" if passed else "error" if required else "warning",
        "reason": reason,
        "detail": detail,
    }


def build_prompt_cache_plan(
    *,
    username: str,
    objective: str,
    project_id: str | None = None,
    runtime_adapter: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    context_plan: dict[str, Any] | None = None,
    prompt_segments: list[dict[str, Any]] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    sensitivity_level: str | None = None,
    expected_reuse_count: int | None = None,
) -> dict[str, Any]:
    clean_objective = _normalize(objective)[:4000]
    segments, segment_summary = _analyze_segments(
        prompt_segments = prompt_segments,
        context_plan = context_plan,
        objective = clean_objective,
    )
    sensitivity_text = " ".join(
        [
            clean_objective,
            *[
                str(_as_dict(item).get("content") or _as_dict(item).get("text") or "")
                for item in _as_list(prompt_segments)[:120]
            ],
        ]
    )
    sensitivity = _sensitivity(sensitivity_text, sensitivity_level)
    scope = _scope(username, project_id, sensitivity)
    runtime = {
        "runtimeType": _runtime_type(runtime_adapter, model) or "unknown",
        "promptCachingSupported": _runtime_supports_prompt_cache(runtime_adapter, model),
        "directRuntimeFlagControl": _runtime_type(runtime_adapter, model) in {"llama.cpp", "llama-cpp", "vllm", "transformers"},
    }
    benchmark = _benchmark_contract(latest_benchmark_run)
    min_prefix_tokens = 256
    reuse_count = max(1, _as_int(expected_reuse_count, 1))
    stable_prefix_ready = segment_summary["stablePrefixTokens"] >= min_prefix_tokens
    privacy_ready = bool(sensitivity["promptCacheAllowed"])
    runtime_ready = bool(runtime["promptCachingSupported"])
    ready_for_experiment = bool(runtime_ready and stable_prefix_ready and privacy_ready)
    ready_for_activation = bool(ready_for_experiment and benchmark["ready"])
    gates = [
        _gate(
            "runtime_supports_prompt_cache",
            runtime_ready,
            True,
            "The selected runtime must expose prompt caching support.",
            runtime["runtimeType"],
        ),
        _gate(
            "stable_prefix_ready",
            stable_prefix_ready,
            True,
            "A reusable stable prefix must be large enough to justify prompt caching.",
            {"stablePrefixTokens": segment_summary["stablePrefixTokens"], "minimumTokens": min_prefix_tokens},
        ),
        _gate(
            "privacy_scope_allows_prompt_cache",
            privacy_ready,
            True,
            "Restricted or confidential prompts cannot be stored in a prompt cache.",
            sensitivity["level"],
        ),
        _gate(
            "benchmark_before_activation",
            bool(benchmark["ready"]),
            False,
            "A before/after benchmark is required before runtime activation.",
            benchmark["status"],
        ),
    ]
    blocked_gate_ids = [item["id"] for item in gates if item["status"] == "blocked"]
    warning_gate_ids = [item["id"] for item in gates if item["status"] == "warning"]
    if ready_for_activation:
        status = "ready_for_activation_review"
    elif ready_for_experiment:
        status = "ready_for_experiment"
    else:
        status = "blocked"

    prefix_hash = _stable_hash(":".join(item["contentHash"] for item in segments if item["inStablePrefix"]))
    estimated_saved_tokens = max(0, (reuse_count - 1) * segment_summary["stablePrefixTokens"])
    return {
        "promptCachePlanVersion": COGNIX_PROMPT_CACHE_PLAN_VERSION,
        "policyVersion": COGNIX_PROMPT_CACHE_POLICY_VERSION,
        "runtimeContractVersion": COGNIX_PROMPT_CACHE_RUNTIME_CONTRACT_VERSION,
        "mode": "prompt_cache_plan_dry_run",
        "username": username,
        "projectId": project_id,
        "status": status,
        "readyForExperiment": ready_for_experiment,
        "readyForActivation": False,
        "requestSignature": _stable_hash(clean_objective)[:24],
        "runtime": runtime,
        "scope": scope,
        "sensitivity": sensitivity,
        "policy": {
            "policyVersion": COGNIX_PROMPT_CACHE_POLICY_VERSION,
            "minStablePrefixTokens": min_prefix_tokens,
            "expectedReuseCount": reuse_count,
            "rawPromptStorageAllowed": False,
            "rawContentStored": False,
            "crossUserPrefixReuseAllowed": False,
            "ttlSeconds": 3600 if scope["scopeType"] == "user_private" else 6 * 3600,
            "invalidateOnModelChange": True,
            "invalidateOnSystemPromptChange": True,
            "invalidateOnProjectPermissionChange": True,
            "invalidateOnMemoryScopeChange": True,
        },
        "prefixPlan": {
            "prefixHash": prefix_hash,
            "stablePrefixTokens": segment_summary["stablePrefixTokens"],
            "stablePrefixSegmentCount": segment_summary["stablePrefixSegmentCount"],
            "cacheKeyHash": _stable_hash(f"{scope['namespaceHash']}:{runtime['runtimeType']}:{prefix_hash}"),
            "rawPrefixStoredInKey": False,
            "estimatedSavedTokensAcrossReuse": estimated_saved_tokens,
        },
        "segments": segments,
        "summary": {
            **segment_summary,
            "blockedGateIds": blocked_gate_ids,
            "warningGateIds": warning_gate_ids,
            "estimatedSavedTokensAcrossReuse": estimated_saved_tokens,
        },
        "gates": gates,
        "benchmarkEvidence": benchmark,
        "runtimeContract": {
            "contractVersion": COGNIX_PROMPT_CACHE_RUNTIME_CONTRACT_VERSION,
            "readyForExperiment": ready_for_experiment,
            "readyForActivation": False,
            "automaticRuntimeEnableAllowed": False,
            "frontendDirectPromptCacheAllowed": False,
            "runtimeFlagWriteAllowed": False,
            "cacheWriteAllowedHere": False,
            "cacheLookupAllowedHere": False,
            "benchmarkBeforeActivationRequired": True,
            "plannedExecutor": "cognix_worker_queue:prompt_cache_experiment" if ready_for_experiment else None,
            "nextRequiredGate": blocked_gate_ids[0] if blocked_gate_ids else "benchmark_before_activation",
            "blockedActions": [
                "prompt_cache_lookup",
                "prompt_cache_write",
                "runtime_config_write",
                "automatic_prompt_cache_reuse",
                "raw_prompt_storage",
                "cross_user_prefix_reuse",
            ],
        },
        "sideEffects": {
            "promptCacheLookup": False,
            "promptCacheWrite": False,
            "runtimeConfigWrite": False,
            "modelLoad": False,
            "benchmarkRun": False,
            "generation": False,
            "networkCall": False,
            "rawPromptStorage": False,
            "crossUserRead": False,
        },
    }
