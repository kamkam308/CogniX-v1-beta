# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX local benchmark helpers.

The MVP benchmark is intentionally lightweight: it measures enough local signal
to improve recommendations without loading a model, touching the network, or
running a GPU stress test.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any

from core.cognix import hardware as cognix_hardware


COGNIX_BENCHMARK_VERSION = "cognix_benchmark_v1"

MODEL_FIT_TARGETS: tuple[dict[str, Any], ...] = (
    {"id": "cognix-general-3b-q4", "label": "CogniX General 3B Q4", "ramGb": 3.6, "storageGb": 2.4},
    {"id": "cognix-code-4b-q4", "label": "CogniX Code 4B Q4", "ramGb": 4.4, "storageGb": 3.2},
    {"id": "cognix-maths-7b-q4", "label": "CogniX Maths 7B Q4", "ramGb": 6.8, "storageGb": 5.1},
    {"id": "qwen-14b-q4", "label": "Qwen 14B Q4", "ramGb": 12.4, "storageGb": 9.4},
    {"id": "glm-700b", "label": "GLM 700B", "ramGb": 520.0, "storageGb": 700.0},
)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _max_vram_gb(hardware: dict[str, Any]) -> float:
    gpu = hardware.get("gpu") if isinstance(hardware, dict) else {}
    if not isinstance(gpu, dict):
        return 0.0
    devices = gpu.get("devices") if isinstance(gpu.get("devices"), list) else []
    return max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices if isinstance(item, dict)),
        default = 0.0,
    )


def _run_cpu_probe(iterations: int = 120_000) -> dict[str, Any]:
    start = time.perf_counter()
    total = 0
    for index in range(max(10_000, iterations)):
        total = (total + (index * index) % 9973) % 1_000_000_007
    elapsed = max(time.perf_counter() - start, 0.000001)
    ops_per_second = int(iterations / elapsed)
    score = round(min(100.0, max(1.0, ops_per_second / 42_000)), 1)
    return {
        "status": "complete",
        "iterations": iterations,
        "opsPerSecond": ops_per_second,
        "score": score,
        "checksum": total,
        "durationMs": round(elapsed * 1000, 2),
    }


def _run_disk_probe(sample_bytes: int = 512 * 1024) -> dict[str, Any]:
    payload = os.urandom(max(4096, sample_bytes))
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix = "cognix-bench-", delete = False) as handle:
            path = handle.name
            write_start = time.perf_counter()
            handle.write(payload)
            handle.flush()
            write_elapsed = max(time.perf_counter() - write_start, 0.000001)

        read_start = time.perf_counter()
        with open(path, "rb") as handle:
            read_size = len(handle.read())
        read_elapsed = max(time.perf_counter() - read_start, 0.000001)

        mib = sample_bytes / (1024 * 1024)
        write_mibs = round(mib / write_elapsed, 2)
        read_mibs = round((read_size / (1024 * 1024)) / read_elapsed, 2)
        score = round(min(100.0, max(1.0, min(write_mibs, read_mibs) / 12)), 1)
        return {
            "status": "complete",
            "sampleBytes": sample_bytes,
            "writeMiBps": write_mibs,
            "readMiBps": read_mibs,
            "score": score,
            "durationMs": round((write_elapsed + read_elapsed) * 1000, 2),
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "sampleBytes": sample_bytes,
            "writeMiBps": None,
            "readMiBps": None,
            "score": 0.0,
            "reason": str(exc)[:240],
        }
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _memory_score(hardware: dict[str, Any]) -> float:
    memory = hardware.get("memory") if isinstance(hardware, dict) else {}
    if not isinstance(memory, dict):
        return 20.0
    total = _as_float(memory.get("totalGb")) or 0.0
    available = _as_float(memory.get("availableGb")) or 0.0
    return round(min(100.0, total * 2.6 + available * 3.4), 1)


def _gpu_score(hardware: dict[str, Any]) -> float:
    gpu = hardware.get("gpu") if isinstance(hardware, dict) else {}
    if not isinstance(gpu, dict) or not gpu.get("available"):
        return 0.0
    return round(min(100.0, 35.0 + _max_vram_gb(hardware) * 3.8), 1)


def _estimated_tokens_per_second(
    *,
    cpu_score: float,
    memory_score: float,
    gpu_score: float,
    hardware: dict[str, Any],
) -> float:
    cpu_count = _as_float(hardware.get("cpuCount")) or 4.0
    base = 2.0 + cpu_score * 0.11 + memory_score * 0.035 + min(cpu_count, 16.0) * 0.22
    if gpu_score > 0:
        base += gpu_score * 0.22
    return round(max(1.0, min(base, 120.0)), 1)


def _model_fit(
    *,
    target: dict[str, Any],
    total_ram_gb: float,
    available_ram_gb: float,
    estimated_tokens_per_second: float,
    gpu_available: bool,
) -> dict[str, Any]:
    required_ram = float(target["ramGb"])
    if total_ram_gb < required_ram:
        stars = 0
        status = "blocked"
        reason = "RAM totale insuffisante pour ce modele en local."
    elif available_ram_gb < required_ram:
        stars = 2 if required_ram <= 8 else 1
        status = "tight"
        reason = "Possible uniquement apres liberation de memoire."
    else:
        headroom = available_ram_gb - required_ram
        stars = 5 if headroom >= 6 else 4 if headroom >= 3 else 3
        status = "recommended" if stars >= 4 else "possible"
        reason = "Compatible avec le profil local actuel."
    if gpu_available and stars > 0:
        stars = min(5, stars + 1)
    return {
        "modelId": target["id"],
        "label": target["label"],
        "status": status,
        "stars": stars,
        "estimatedRamGb": required_ram,
        "estimatedStorageGb": float(target["storageGb"]),
        "estimatedFirstTokenSeconds": (
            None if stars == 0 else round(max(1.2, required_ram * 0.38), 1)
        ),
        "estimatedTokensPerSecond": 0.0 if stars == 0 else estimated_tokens_per_second,
        "reason": reason,
    }


def _optimization_plan(
    *,
    hardware: dict[str, Any],
    estimated_tokens_per_second: float,
) -> dict[str, Any]:
    memory = hardware.get("memory") if isinstance(hardware, dict) else {}
    if not isinstance(memory, dict):
        memory = {}
    total_ram = _as_float(memory.get("totalGb")) or 0.0
    available_ram = _as_float(memory.get("availableGb")) or 0.0
    gpu_available = bool((hardware.get("gpu") or {}).get("available")) if isinstance(hardware, dict) else False
    if total_ram < 12 or available_ram < 5:
        quantization = "Q4"
        cache_policy = "single_resident_model"
    elif gpu_available or total_ram >= 32:
        quantization = "Q5_or_Q8_when_quality_matters"
        cache_policy = "multi_model_lru"
    else:
        quantization = "Q4_or_Q5"
        cache_policy = "general_plus_one_expert"
    return {
        "quantization": quantization,
        "cachePolicy": cache_policy,
        "preload": "disabled_on_small_profile" if cache_policy == "single_resident_model" else "enabled_for_project_expert",
        "expectedLocalSpeed": "slow" if estimated_tokens_per_second < 7 else "balanced" if estimated_tokens_per_second < 20 else "fast",
        "networkBenchmark": "skipped_local_only",
        "gpuStressTest": "skipped_safe_mvp",
    }


def run_benchmark(
    *,
    hardware: dict[str, Any] | None = None,
    mode: str = "quick",
    include_disk: bool = True,
) -> dict[str, Any]:
    observed_hardware = hardware if isinstance(hardware, dict) else cognix_hardware.get_hardware_profile()
    cpu = _run_cpu_probe(60_000 if mode == "quick" else 180_000)
    disk = (
        _run_disk_probe(256 * 1024 if mode == "quick" else 1024 * 1024)
        if include_disk
        else {"status": "skipped", "score": None, "reason": "Disk benchmark disabled."}
    )
    memory_score = _memory_score(observed_hardware)
    gpu_score = _gpu_score(observed_hardware)
    cpu_score = float(cpu.get("score") or 0.0)
    disk_score = float(disk.get("score") or 0.0) if isinstance(disk.get("score"), (int, float)) else 0.0
    overall_score = round(cpu_score * 0.36 + memory_score * 0.32 + disk_score * 0.16 + gpu_score * 0.16, 1)
    estimated_tps = _estimated_tokens_per_second(
        cpu_score = cpu_score,
        memory_score = memory_score,
        gpu_score = gpu_score,
        hardware = observed_hardware,
    )
    memory = observed_hardware.get("memory") if isinstance(observed_hardware, dict) else {}
    if not isinstance(memory, dict):
        memory = {}
    total_ram = _as_float(memory.get("totalGb")) or 0.0
    available_ram = _as_float(memory.get("availableGb")) or 0.0
    gpu_available = bool((observed_hardware.get("gpu") or {}).get("available")) if isinstance(observed_hardware, dict) else False
    model_fitness = [
        _model_fit(
            target = target,
            total_ram_gb = total_ram,
            available_ram_gb = available_ram,
            estimated_tokens_per_second = estimated_tps,
            gpu_available = gpu_available,
        )
        for target in MODEL_FIT_TARGETS
    ]
    return {
        "benchmarkVersion": COGNIX_BENCHMARK_VERSION,
        "mode": "quick" if mode != "extended" else "extended",
        "hardware": observed_hardware,
        "measurements": {
            "cpu": cpu,
            "memory": {
                "status": "complete",
                "score": memory_score,
                "totalGb": total_ram or None,
                "availableGb": available_ram or None,
            },
            "disk": disk,
            "gpu": {
                "status": "observed",
                "score": gpu_score,
                "available": gpu_available,
                "maxVramGb": _max_vram_gb(observed_hardware),
                "stressTest": "skipped",
            },
            "network": {
                "status": "skipped",
                "reason": "Benchmark local: no external network probe.",
            },
        },
        "overallScore": overall_score,
        "estimatedTokensPerSecond": estimated_tps,
        "modelFitness": model_fitness,
        "optimizationPlan": _optimization_plan(
            hardware = observed_hardware,
            estimated_tokens_per_second = estimated_tps,
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "gpuStressTest": False,
            "temporaryDiskWrite": bool(include_disk),
        },
    }
