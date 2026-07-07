# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX hardware profiling helpers."""

from __future__ import annotations

from typing import Any


def get_hardware_profile() -> dict[str, Any]:
    total_gb: float | None = None
    available_gb: float | None = None
    cpu_count: int | None = None
    try:
        import psutil

        memory = psutil.virtual_memory()
        total_gb = round(memory.total / 1e9, 2)
        available_gb = round(memory.available / 1e9, 2)
        cpu_count = psutil.cpu_count()
    except Exception:
        pass

    gpu_available = False
    gpu_devices: list[dict[str, Any]] = []
    device_backend = "unknown"
    try:
        from utils.hardware import get_backend_visible_gpu_info, get_device
        from utils.hardware.hardware import _backend_label

        visibility = get_backend_visible_gpu_info()
        gpu_available = bool(visibility.get("available"))
        gpu_devices = [
            {
                "name": item.get("name"),
                "vramTotalGb": item.get("memory_total_gb"),
            }
            for item in visibility.get("devices", [])
        ]
        device_backend = _backend_label(get_device())
    except Exception:
        pass

    if device_backend == "unknown":
        device_backend = "gpu" if gpu_available else "cpu"

    return {
        "deviceBackend": device_backend,
        "cpuCount": cpu_count,
        "memory": {
            "totalGb": total_gb,
            "availableGb": available_gb,
        },
        "gpu": {
            "available": gpu_available,
            "devices": gpu_devices,
        },
    }
