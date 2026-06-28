# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX live performance monitor planning."""

from __future__ import annotations

import time
from typing import Any


COGNIX_PERFORMANCE_MONITOR_VERSION = "cognix_performance_monitor_v1"
COGNIX_RUNTIME_METRICS_COLLECTOR_VERSION = "cognix_runtime_metrics_collector_v1"
COGNIX_METRICS_STREAMER_VERSION = "cognix_metrics_streamer_v1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cpu_percent() -> float | None:
    try:
        import psutil

        return round(float(psutil.cpu_percent(interval = 0.0)), 2)
    except Exception:
        return None


def _ram_metrics(hardware: dict[str, Any]) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    total = _as_float(memory.get("totalGb"))
    available = _as_float(memory.get("availableGb"))
    used = round(total - available, 2) if total is not None and available is not None else None
    percent = round((used / total) * 100, 2) if total and used is not None else None
    return {
        "totalGb": total,
        "availableGb": available,
        "usedGb": used,
        "usedPercent": percent,
    }


def _gpu_metrics(hardware: dict[str, Any]) -> dict[str, Any]:
    gpu = _as_dict(hardware.get("gpu"))
    devices = [item for item in gpu.get("devices", []) if isinstance(item, dict)]
    normalized_devices: list[dict[str, Any]] = []
    for item in devices:
        total = _as_float(item.get("vramTotalGb"))
        free = _as_float(item.get("vramFreeGb"))
        used = round(total - free, 2) if total is not None and free is not None else None
        normalized_devices.append(
            {
                "name": item.get("name"),
                "vramTotalGb": total,
                "vramFreeGb": free,
                "vramUsedGb": used,
                "temperatureC": _as_float(item.get("temperatureC")),
            }
        )
    return {
        "available": bool(gpu.get("available")),
        "deviceCount": len(normalized_devices),
        "devices": normalized_devices,
    }


def build_performance_monitor_blueprint() -> dict[str, Any]:
    return {
        "performanceMonitorVersion": COGNIX_PERFORMANCE_MONITOR_VERSION,
        "runtimeMetricsCollectorVersion": COGNIX_RUNTIME_METRICS_COLLECTOR_VERSION,
        "metricsStreamerVersion": COGNIX_METRICS_STREAMER_VERSION,
        "services": ["PerformanceMonitor", "RuntimeMetricsCollector", "MetricsStreamer"],
        "metrics": [
            "ram",
            "cpu",
            "gpu",
            "vram",
            "tokens_per_second",
            "load_time_ms",
            "latency_ms",
            "temperature_c",
            "estimated_cost_usd",
        ],
        "displayModes": ["discreet_panel", "developer_overlay"],
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "benchmarkRun": False,
            "gpuStressTest": False,
            "networkCall": False,
            "metricsWrite": False,
        },
    }


def collect_runtime_metrics(
    *,
    username: str,
    hardware: dict[str, Any],
    runtime_snapshot: dict[str, Any] | None = None,
    inference_stats: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    runtime_snapshot = _as_dict(runtime_snapshot)
    inference_stats = _as_dict(inference_stats)
    benchmark = _as_dict(_as_dict(latest_benchmark_run).get("benchmark"))
    tokens_per_second = _as_float(inference_stats.get("tokensPerSecond"))
    if tokens_per_second is None:
        tokens_per_second = _as_float(benchmark.get("estimatedTokensPerSecond"))
    latency_ms = _as_float(inference_stats.get("latencyMs"))
    load_time_ms = _as_float(inference_stats.get("loadTimeMs"))
    estimated_cost_usd = _as_float(inference_stats.get("estimatedCostUsd")) or 0.0

    return {
        "performanceMonitorVersion": COGNIX_PERFORMANCE_MONITOR_VERSION,
        "runtimeMetricsCollectorVersion": COGNIX_RUNTIME_METRICS_COLLECTOR_VERSION,
        "metricsStreamerVersion": COGNIX_METRICS_STREAMER_VERSION,
        "mode": "snapshot",
        "username": username,
        "projectId": project_id,
        "modelId": model_id or runtime_snapshot.get("activeModel"),
        "timestampMs": int(time.time() * 1000),
        "runtime": {
            "runtimeType": runtime_snapshot.get("runtimeType") or "unknown",
            "activeModel": runtime_snapshot.get("activeModel"),
            "loadedModelCount": len(runtime_snapshot.get("loadedModels") or []),
            "loadingModelCount": len(runtime_snapshot.get("loadingModels") or []),
        },
        "hardware": {
            "deviceBackend": hardware.get("deviceBackend"),
            "cpuCount": hardware.get("cpuCount"),
            "ram": _ram_metrics(hardware),
            "cpu": {"usagePercent": _cpu_percent()},
            "gpu": _gpu_metrics(hardware),
        },
        "inference": {
            "tokensPerSecond": tokens_per_second,
            "latencyMs": latency_ms,
            "loadTimeMs": load_time_ms,
            "estimatedCostUsd": estimated_cost_usd,
        },
        "streamPlan": {
            "streamId": "performance",
            "intervalMs": 2000,
            "mode": "server_poll",
            "willOpenStreamNow": False,
            "developerOverlayAvailable": True,
        },
        "source": {
            "runtimeSnapshotProvided": bool(runtime_snapshot),
            "inferenceStatsProvided": bool(inference_stats),
            "benchmarkRunId": _as_dict(latest_benchmark_run).get("id"),
        },
        "sideEffects": build_performance_monitor_blueprint()["sideEffects"],
    }


def build_metrics_stream_plan(*, project_id: str | None = None, developer_mode: bool = False) -> dict[str, Any]:
    return {
        "metricsStreamerVersion": COGNIX_METRICS_STREAMER_VERSION,
        "mode": "dry_run_metrics_stream",
        "projectId": project_id,
        "transport": "server_sent_events_or_polling",
        "intervalMs": 1000 if developer_mode else 3000,
        "displayMode": "developer_overlay" if developer_mode else "discreet_panel",
        "willOpenStreamNow": False,
        "retention": {
            "runtimeMetricSamples": 300,
            "performanceLogs": 200,
        },
        "sideEffects": build_performance_monitor_blueprint()["sideEffects"],
    }
