# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX speculative decoding planning.

This module builds a compatibility and experiment contract for speculative
decoding. It never mutates runtime flags, starts a server, loads a draft model,
or generates tokens.
"""

from __future__ import annotations

import json
from typing import Any

from core.cognix.benchmark import COGNIX_BENCHMARK_VERSION


COGNIX_SPECULATIVE_DECODING_CONTRACT_VERSION = "cognix_speculative_decoding_contract_v1"
COGNIX_SPECULATIVE_DECODING_PREFLIGHT_VERSION = "cognix_speculative_decoding_preflight_v1"

SUPPORTED_RUNTIME_TYPES = {"llama.cpp", "llama-cpp", "vllm"}
SPECULATIVE_BENCHMARK_METRICS = (
    "overallScore",
    "estimatedTokensPerSecond",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _model_id(model: dict[str, Any]) -> str:
    return str(model.get("modelId") or model.get("id") or model.get("name") or "").strip()[:240]


def _model_family(model: dict[str, Any]) -> str:
    return str(
        model.get("family")
        or model.get("modelFamily")
        or model.get("architecture")
        or model.get("baseFamily")
        or ""
    ).strip().casefold()


def _tokenizer_ref(model: dict[str, Any]) -> str:
    return str(
        model.get("tokenizerHash")
        or model.get("tokenizer")
        or model.get("tokenizerId")
        or model.get("tokenizerName")
        or ""
    ).strip().casefold()


def _model_size_b(model: dict[str, Any]) -> float | None:
    for key in ("parameterCountB", "paramsB", "sizeB", "billionParameters"):
        parsed = _as_float(model.get(key))
        if parsed is not None:
            return parsed
    parameter_count = _as_float(model.get("parameterCount") or model.get("params"))
    if parameter_count is not None:
        return round(parameter_count / 1_000_000_000, 3) if parameter_count > 1000 else parameter_count
    return None


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
    ).strip().lower()


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


def _benchmark_gate(latest_benchmark_run: dict[str, Any] | None) -> dict[str, Any]:
    run_present = isinstance(latest_benchmark_run, dict)
    payload = _benchmark_payload(latest_benchmark_run)
    benchmark_version = str(payload.get("benchmarkVersion") or "")
    observed_metrics = [
        metric
        for metric in SPECULATIVE_BENCHMARK_METRICS
        if _as_float(payload.get(metric)) is not None
    ]
    missing_metrics = [
        metric
        for metric in SPECULATIVE_BENCHMARK_METRICS
        if metric not in observed_metrics
    ]
    if not run_present:
        status = "missing"
    elif not payload:
        status = "incomplete_payload"
    elif benchmark_version != COGNIX_BENCHMARK_VERSION:
        status = "unsupported_version"
    elif missing_metrics:
        status = "insufficient_metrics"
    else:
        status = "ready"
    return {
        "status": status,
        "ready": status == "ready",
        "runId": latest_benchmark_run.get("id") if isinstance(latest_benchmark_run, dict) else None,
        "benchmarkVersion": benchmark_version or None,
        "expectedBenchmarkVersion": COGNIX_BENCHMARK_VERSION,
        "requiredMetricIds": list(SPECULATIVE_BENCHMARK_METRICS),
        "observedMetricIds": observed_metrics,
        "missingMetricIds": missing_metrics,
        "sideEffects": {
            "benchmarkRun": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def _gate(gate_id: str, passed: bool, *, required_before: str, reason: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": "pass" if passed else "blocked",
        "requiredBefore": required_before,
        "reason": reason,
        **(metadata or {}),
    }


def build_speculative_decoding_plan(
    *,
    username: str,
    objective: str,
    runtime_adapter: dict[str, Any] | None = None,
    target_model: dict[str, Any] | None = None,
    draft_model: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    project_id: str | None = None,
    max_quality_delta: float = 0.02,
) -> dict[str, Any]:
    runtime = _runtime_type(runtime_adapter)
    target = _as_dict(target_model)
    draft = _as_dict(draft_model)
    target_id = _model_id(target)
    draft_id = _model_id(draft)
    target_size_b = _model_size_b(target)
    draft_size_b = _model_size_b(draft)
    target_family = _model_family(target)
    draft_family = _model_family(draft)
    target_tokenizer = _tokenizer_ref(target)
    draft_tokenizer = _tokenizer_ref(draft)
    max_delta = min(max(_as_float(max_quality_delta, 0.02) or 0.02, 0.0), 0.2)
    benchmark = _benchmark_gate(latest_benchmark_run)

    runtime_supported = runtime in SUPPORTED_RUNTIME_TYPES
    target_present = bool(target_id)
    draft_present = bool(draft_id)
    distinct_models = bool(target_id and draft_id and target_id != draft_id)
    size_known = target_size_b is not None and draft_size_b is not None
    draft_smaller = bool(size_known and draft_size_b < target_size_b and draft_size_b <= max(target_size_b * 0.6, 0.1))
    tokenizer_compatible = bool(target_tokenizer and target_tokenizer == draft_tokenizer)
    family_compatible = bool(target_family and draft_family and target_family == draft_family)
    compatibility_known = tokenizer_compatible or family_compatible

    gates = [
        _gate(
            "runtime_supports_speculative_decoding",
            runtime_supported,
            required_before = "experiment",
            reason = "Speculative decoding is supported only by llama.cpp or vLLM runtime contracts.",
            metadata = {"runtimeType": runtime or "unknown", "supportedRuntimeTypes": sorted(SUPPORTED_RUNTIME_TYPES)},
        ),
        _gate(
            "target_model_declared",
            target_present,
            required_before = "experiment",
            reason = "A target model must be declared before pairing a draft model.",
        ),
        _gate(
            "draft_model_declared",
            draft_present,
            required_before = "experiment",
            reason = "A smaller draft model must be declared before speculative decoding can be tested.",
        ),
        _gate(
            "target_and_draft_are_distinct",
            distinct_models,
            required_before = "experiment",
            reason = "Draft and target model must be different models.",
        ),
        _gate(
            "draft_model_smaller",
            draft_smaller,
            required_before = "experiment",
            reason = "Draft model should be materially smaller than the target model.",
            metadata = {"targetSizeB": target_size_b, "draftSizeB": draft_size_b},
        ),
        _gate(
            "tokenizer_or_family_compatible",
            compatibility_known,
            required_before = "experiment",
            reason = "Draft and target should share tokenizer metadata or at least the same model family.",
            metadata = {
                "tokenizerCompatible": tokenizer_compatible,
                "familyCompatible": family_compatible,
            },
        ),
        _gate(
            "benchmark_baseline_ready",
            bool(benchmark.get("ready")),
            required_before = "experiment",
            reason = "A CogniX benchmark baseline is required before measuring speculative decoding.",
            metadata = {
                "benchmarkStatus": benchmark.get("status"),
                "benchmarkRunId": benchmark.get("runId"),
            },
        ),
    ]
    blocked_gate_ids = [
        str(gate["id"])
        for gate in gates
        if gate.get("status") == "blocked"
    ]
    ready_for_experiment = not blocked_gate_ids
    status = "ready_for_experiment" if ready_for_experiment else "blocked_by_gates"
    side_effects = {
        "runtimeConfigWrite": False,
        "runtimeFlagWrite": False,
        "serverStart": False,
        "modelLoad": False,
        "draftModelLoad": False,
        "targetModelLoad": False,
        "benchmarkRun": False,
        "generation": False,
        "networkModelCall": False,
        "cacheMutation": False,
        "auditWrite": False,
    }
    return {
        "contractVersion": COGNIX_SPECULATIVE_DECODING_CONTRACT_VERSION,
        "preflightVersion": COGNIX_SPECULATIVE_DECODING_PREFLIGHT_VERSION,
        "mode": "speculative_decoding_preflight_dry_run",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "status": status,
        "readyForExperiment": ready_for_experiment,
        "readyForActivation": False,
        "runtime": {
            "runtimeType": runtime or "unknown",
            "supported": runtime_supported,
            "supportedRuntimeTypes": sorted(SUPPORTED_RUNTIME_TYPES),
        },
        "modelPair": {
            "targetModelId": target_id or None,
            "draftModelId": draft_id or None,
            "targetSizeB": target_size_b,
            "draftSizeB": draft_size_b,
            "draftToTargetSizeRatio": round(draft_size_b / target_size_b, 3) if target_size_b and draft_size_b is not None else None,
            "tokenizerCompatible": tokenizer_compatible,
            "familyCompatible": family_compatible,
        },
        "qualityPolicy": {
            "maxAllowedQualityDelta": max_delta,
            "qualityRegressionAllowedWithoutReview": False,
            "requiresSideBySideEval": True,
            "requiresRollbackPlan": True,
        },
        "benchmarkEvidence": benchmark,
        "gates": gates,
        "summary": {
            "blockedGateIds": blocked_gate_ids,
            "blockedGateCount": len(blocked_gate_ids),
            "passGateCount": len(gates) - len(blocked_gate_ids),
            "readyForExperiment": ready_for_experiment,
        },
        "activationContract": {
            "automaticActivationAllowed": False,
            "runtimeMutationAllowed": False,
            "runtimeFlagWriteAllowed": False,
            "humanApprovalRequired": True,
            "benchmarkBeforeAfterRequired": True,
            "rollbackPlanRequired": True,
            "canaryRolloutRequired": True,
        },
        "experimentPlan": {
            "willRunBenchmarkNow": False,
            "willLoadDraftModelNow": False,
            "willGenerateNow": False,
            "metrics": [
                "tokens_per_second_delta",
                "first_token_latency_delta",
                "acceptance_rate",
                "quality_regression_score",
                "memory_peak_delta",
            ],
            "minimumEvidenceBeforeActivation": [
                "baseline_benchmark",
                "speculative_benchmark",
                "quality_regression_eval",
                "rollback_test",
            ],
        },
        "warnings": [
            "Speculative decoding reste experimental: activation interdite sans benchmark avant/apres."
        ] if ready_for_experiment else [
            "Speculative decoding bloque tant que les gates de compatibilite ou benchmark ne sont pas resolues."
        ],
        "sideEffects": side_effects,
    }
