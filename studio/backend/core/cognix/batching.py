# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX multi-user batching planning.

Batching is useful for enterprise or school deployments with concurrent users.
This planner prepares a micro-batch and throughput experiment contract without
starting servers, changing runtime flags, enqueueing jobs, loading models, or
issuing model requests.
"""

from __future__ import annotations

import json
from typing import Any

from core.cognix.benchmark import COGNIX_BENCHMARK_VERSION


COGNIX_BATCHING_PLAN_VERSION = "cognix_batching_plan_v1"
COGNIX_MICRO_BATCH_POLICY_VERSION = "cognix_micro_batch_policy_v1"
COGNIX_THROUGHPUT_EXPERIMENT_CONTRACT_VERSION = "cognix_throughput_experiment_contract_v1"

DIRECT_BATCH_RUNTIME_TYPES = {"vllm", "cloud", "cloud_api"}
QUEUE_MEDIATED_RUNTIME_TYPES = {"transformers"}
UNSUPPORTED_BATCH_RUNTIME_TYPES = {"ollama", "llama.cpp", "llama-cpp"}
REQUIRED_BENCHMARK_METRICS = ("overallScore", "estimatedTokensPerSecond")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _deployment_target(runtime_adapter: dict[str, Any] | None, explicit_target: str | None) -> str:
    adapter = _as_dict(runtime_adapter)
    selected = _as_dict(adapter.get("selectedAdapter"))
    return str(
        explicit_target
        or adapter.get("deploymentTarget")
        or selected.get("deploymentTarget")
        or ""
    ).strip().casefold()


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


def _workload(
    *,
    concurrent_users: int | None,
    request_rate_per_minute: float | None,
    average_prompt_tokens: int | None,
    average_completion_tokens: int | None,
    target_latency_ms: int | None,
) -> dict[str, Any]:
    users = max(1, _as_int(concurrent_users, 1))
    rpm = max(0.0, _as_float(request_rate_per_minute, float(users * 6)))
    prompt_tokens = max(1, _as_int(average_prompt_tokens, 512))
    completion_tokens = max(1, _as_int(average_completion_tokens, 256))
    latency = max(250, _as_int(target_latency_ms, 2500))
    tokens_per_request = prompt_tokens + completion_tokens
    target_tokens_per_second = round((rpm * tokens_per_request) / 60.0, 2)
    return {
        "concurrentUsers": users,
        "requestRatePerMinute": round(rpm, 2),
        "averagePromptTokens": prompt_tokens,
        "averageCompletionTokens": completion_tokens,
        "tokensPerRequest": tokens_per_request,
        "targetLatencyMs": latency,
        "targetTokensPerSecond": target_tokens_per_second,
        "multiUser": users >= 2 or rpm >= 12,
    }


def _hardware_capacity(hardware: dict[str, Any] | None) -> dict[str, Any]:
    item = _as_dict(hardware)
    gpu = _as_dict(item.get("gpu"))
    devices = [device for device in gpu.get("devices", []) if isinstance(device, dict)]
    max_vram = max((_as_float(device.get("vramTotalGb")) for device in devices), default = 0.0)
    memory = _as_dict(item.get("memory"))
    total_ram = _as_float(memory.get("totalGb"))
    if bool(gpu.get("available")) and max_vram >= 24:
        tier = "enterprise_gpu_ready"
    elif bool(gpu.get("available")) and max_vram >= 12:
        tier = "single_gpu_experiment"
    elif total_ram >= 64:
        tier = "cpu_or_server_queue_only"
    else:
        tier = "not_batching_ready"
    return {
        "tier": tier,
        "gpuAvailable": bool(gpu.get("available")),
        "gpuCount": len(devices),
        "maxVramGb": round(max_vram, 2),
        "totalRamGb": round(total_ram, 2),
    }


def _micro_batch_policy(workload: dict[str, Any], runtime: str, hardware: dict[str, Any]) -> dict[str, Any]:
    users = int(workload["concurrentUsers"])
    latency = int(workload["targetLatencyMs"])
    runtime_direct = runtime in DIRECT_BATCH_RUNTIME_TYPES
    if not runtime_direct:
        max_batch_size = 1
        max_wait_ms = 0
    else:
        base = 8 if hardware["tier"] == "enterprise_gpu_ready" else 4
        max_batch_size = max(2, min(32, base + users // 4))
        max_wait_ms = max(8, min(80, int(latency * 0.035)))
    return {
        "microBatchPolicyVersion": COGNIX_MICRO_BATCH_POLICY_VERSION,
        "strategy": "continuous_batching" if runtime_direct else "queue_serialized_fallback",
        "maxBatchSize": max_batch_size,
        "maxWaitMs": max_wait_ms,
        "priorityMode": "latency_slo_first",
        "perUserFairnessRequired": True,
        "streamingBackpressureRequired": True,
        "rawPromptBatchStorageAllowed": False,
        "automaticRuntimeEnableAllowed": False,
    }


def build_batching_plan(
    *,
    username: str,
    objective: str,
    runtime_adapter: dict[str, Any] | None = None,
    hardware: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    project_id: str | None = None,
    deployment_target: str | None = None,
    concurrent_users: int | None = None,
    request_rate_per_minute: float | None = None,
    average_prompt_tokens: int | None = None,
    average_completion_tokens: int | None = None,
    target_latency_ms: int | None = None,
) -> dict[str, Any]:
    runtime = _runtime_type(runtime_adapter)
    target = _deployment_target(runtime_adapter, deployment_target)
    workload = _workload(
        concurrent_users = concurrent_users,
        request_rate_per_minute = request_rate_per_minute,
        average_prompt_tokens = average_prompt_tokens,
        average_completion_tokens = average_completion_tokens,
        target_latency_ms = target_latency_ms,
    )
    hardware_capacity = _hardware_capacity(hardware)
    benchmark = _benchmark_contract(latest_benchmark_run)
    runtime_direct = runtime in DIRECT_BATCH_RUNTIME_TYPES
    runtime_queue = runtime in QUEUE_MEDIATED_RUNTIME_TYPES
    runtime_supported = runtime_direct or runtime_queue
    enterprise_target = target in {"server_gpu", "enterprise_server", "cloud", "cloud_gpu", "on_prem_gpu"}
    policy = _micro_batch_policy(workload, runtime, hardware_capacity)
    gates = [
        {
            "id": "runtime_declared",
            "status": "pass" if bool(runtime) else "blocked",
            "requiredBefore": "experiment",
        },
        {
            "id": "runtime_supports_batching",
            "status": "pass" if runtime_direct else "warning" if runtime_queue else "blocked",
            "requiredBefore": "experiment",
            "runtimeType": runtime or "unknown",
        },
        {
            "id": "multi_user_load_declared",
            "status": "pass" if workload["multiUser"] else "blocked",
            "requiredBefore": "experiment",
        },
        {
            "id": "enterprise_or_server_target",
            "status": "pass" if enterprise_target else "warning",
            "requiredBefore": "enablement",
            "deploymentTarget": target or "unknown",
        },
        {
            "id": "hardware_capacity_ready",
            "status": "pass" if hardware_capacity["tier"] in {"enterprise_gpu_ready", "single_gpu_experiment"} or target in {"cloud", "cloud_gpu"} else "warning",
            "requiredBefore": "experiment",
            "hardwareTier": hardware_capacity["tier"],
        },
        {
            "id": "benchmark_baseline_ready",
            "status": "pass" if benchmark["ready"] else "blocked",
            "requiredBefore": "experiment",
            "benchmarkStatus": benchmark["status"],
        },
    ]
    blocked_gate_ids = [str(item["id"]) for item in gates if item.get("status") == "blocked"]
    warning_gate_ids = [str(item["id"]) for item in gates if item.get("status") == "warning"]
    ready_for_experiment = runtime_supported and workload["multiUser"] and benchmark["ready"]
    recommended_queue = {
        "queueId": "enterprise_throughput",
        "jobType": "batching_experiment",
        "willEnqueueNow": False,
        "requiresHumanConfirmation": True,
    } if ready_for_experiment else {
        "queueId": None,
        "jobType": None,
        "willEnqueueNow": False,
        "requiresHumanConfirmation": True,
    }
    return {
        "batchingPlanVersion": COGNIX_BATCHING_PLAN_VERSION,
        "microBatchPolicyVersion": COGNIX_MICRO_BATCH_POLICY_VERSION,
        "throughputExperimentContractVersion": COGNIX_THROUGHPUT_EXPERIMENT_CONTRACT_VERSION,
        "mode": "batching_plan_dry_run",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "status": "ready_for_experiment" if ready_for_experiment else "blocked_by_gates",
        "readyForExperiment": ready_for_experiment,
        "readyForActivation": False,
        "runtime": {
            "runtimeType": runtime or "unknown",
            "deploymentTarget": target or "unknown",
            "directBatchingSupported": runtime_direct,
            "queueMediatedBatchingOnly": runtime_queue,
            "unsupportedRuntime": runtime in UNSUPPORTED_BATCH_RUNTIME_TYPES,
        },
        "hardwareCapacity": hardware_capacity,
        "workload": workload,
        "microBatchPolicy": policy,
        "queuePlan": recommended_queue,
        "experimentContract": {
            "contractVersion": COGNIX_THROUGHPUT_EXPERIMENT_CONTRACT_VERSION,
            "benchmarkBeforeAfterRequired": True,
            "perUserLatencySloRequired": True,
            "qualityRegressionCheckRequired": True,
            "rollbackRequired": True,
            "automaticRuntimeEnableAllowed": False,
            "frontendDirectBatchingAllowed": False,
            "blockedActions": [
                "runtime_server_start",
                "runtime_flag_write",
                "batch_scheduler_enable",
                "job_enqueue",
                "model_load",
                "generation",
                "network_model_call",
            ],
        },
        "benchmarkEvidence": benchmark,
        "gates": gates,
        "summary": {
            "blockedGateIds": blocked_gate_ids,
            "warningGateIds": warning_gate_ids,
            "recommendedQueueId": recommended_queue["queueId"],
            "recommendedJobType": recommended_queue["jobType"],
            "targetTokensPerSecond": workload["targetTokensPerSecond"],
            "expectedBenefit": "throughput" if workload["multiUser"] else "none_single_user",
        },
        "sideEffects": {
            "runtimeServerStart": False,
            "runtimeConfigWrite": False,
            "runtimeFlagWrite": False,
            "batchSchedulerEnable": False,
            "jobEnqueue": False,
            "workerStart": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "benchmarkRun": False,
        },
    }
