# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX model cache manager MVP.

This module is deliberately non-destructive: it observes loaded models, tracks
last use, and computes the idle/LRU action CogniX should take. Automatic unload
can be enabled later from this native state instead of a frontend overlay.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable


CHAT_IDLE_TIMEOUT_SECONDS = 10 * 60
PROJECT_IDLE_TIMEOUT_SECONDS = 15 * 60


@dataclass
class ModelCacheEntry:
    model_id: str
    runtime_type: str
    loaded_at: float
    last_used_at: float
    project_id: str | None = None
    hits: int = 0


_CACHE_ENTRIES: dict[str, ModelCacheEntry] = {}


def _now() -> float:
    return time.time()


def _clean_model_id(model_id: str | None) -> str | None:
    if not isinstance(model_id, str):
        return None
    value = model_id.strip()
    return value or None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _unique_models(models: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for model in models:
        clean = _clean_model_id(model)
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def reset_cache_state() -> None:
    """Clear process-local cache observations. Intended for tests."""

    _CACHE_ENTRIES.clear()


def mark_model_loaded(
    model_id: str | None,
    *,
    runtime_type: str = "unknown",
    project_id: str | None = None,
    now: float | None = None,
) -> None:
    model = _clean_model_id(model_id)
    if not model:
        return
    timestamp = _now() if now is None else now
    entry = _CACHE_ENTRIES.get(model)
    if entry is None:
        _CACHE_ENTRIES[model] = ModelCacheEntry(
            model_id = model,
            runtime_type = runtime_type or "unknown",
            loaded_at = timestamp,
            last_used_at = timestamp,
            project_id = project_id,
            hits = 0,
        )
        return
    entry.runtime_type = runtime_type or entry.runtime_type
    entry.project_id = project_id or entry.project_id


def mark_model_used(
    model_id: str | None,
    *,
    runtime_type: str = "unknown",
    project_id: str | None = None,
    now: float | None = None,
) -> None:
    model = _clean_model_id(model_id)
    if not model:
        return
    timestamp = _now() if now is None else now
    if model not in _CACHE_ENTRIES:
        mark_model_loaded(
            model,
            runtime_type = runtime_type,
            project_id = project_id,
            now = timestamp,
        )
    entry = _CACHE_ENTRIES[model]
    entry.last_used_at = timestamp
    entry.runtime_type = runtime_type or entry.runtime_type
    entry.project_id = project_id or entry.project_id
    entry.hits += 1


def mark_model_unloaded(model_id: str | None) -> None:
    model = _clean_model_id(model_id)
    if not model:
        return
    _CACHE_ENTRIES.pop(model, None)


def _policy_for_hardware(
    hardware: dict[str, Any],
    *,
    project_scoped: bool,
) -> dict[str, Any]:
    memory = hardware.get("memory") if isinstance(hardware, dict) else {}
    if not isinstance(memory, dict):
        memory = {}
    total_gb = _as_float(memory.get("totalGb"))
    available_gb = _as_float(memory.get("availableGb"))
    gpu = hardware.get("gpu") if isinstance(hardware, dict) else {}
    if not isinstance(gpu, dict):
        gpu = {}
    gpu_available = bool(gpu.get("available"))
    devices = gpu.get("devices") if isinstance(gpu.get("devices"), list) else []
    max_vram_gb = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices if isinstance(item, dict)),
        default = 0.0,
    )

    if (not gpu_available and (total_gb is None or total_gb <= 12)) or (
        available_gb is not None and available_gb < 5
    ):
        tier = "small_local"
        max_resident_models = 1
        reason = "Petit profil local: CogniX garde un seul modele resident."
    elif gpu_available and (max_vram_gb >= 16 or (total_gb is not None and total_gb >= 32)):
        tier = "powerful_local"
        max_resident_models = 4
        reason = "Profil puissant: CogniX peut garder plusieurs modeles chauds."
    else:
        tier = "balanced_local"
        max_resident_models = 2
        reason = "Profil local moyen: CogniX garde un modele principal et un expert."

    return {
        "tier": tier,
        "idleTimeoutSeconds": (
            PROJECT_IDLE_TIMEOUT_SECONDS if project_scoped else CHAT_IDLE_TIMEOUT_SECONDS
        ),
        "maxResidentModels": max_resident_models,
        "evictionStrategy": "lru",
        "preloadEnabled": tier != "small_local",
        "automaticEvictionEnabled": False,
        "reason": reason,
    }


def _reconcile_runtime(
    *,
    loaded_models: list[str],
    runtime_type: str,
    active_model: str | None,
    project_id: str | None,
    now: float,
) -> None:
    loaded_set = set(loaded_models)
    for model_id in list(_CACHE_ENTRIES):
        if model_id not in loaded_set:
            _CACHE_ENTRIES.pop(model_id, None)
    for model_id in loaded_models:
        mark_model_loaded(
            model_id,
            runtime_type = runtime_type,
            project_id = project_id if model_id == active_model else None,
            now = now,
        )


def build_cache_state(
    hardware: dict[str, Any],
    *,
    active_model: str | None = None,
    loaded_models: Iterable[str | None] = (),
    loading_models: Iterable[str | None] = (),
    runtime_type: str = "unknown",
    project_id: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    timestamp = _now() if now is None else now
    active = _clean_model_id(active_model)
    loaded = _unique_models([*loaded_models, active])
    loading = _unique_models(loading_models)
    project_scoped = bool(project_id)
    policy = _policy_for_hardware(hardware, project_scoped = project_scoped)
    _reconcile_runtime(
        loaded_models = loaded,
        runtime_type = runtime_type,
        active_model = active,
        project_id = project_id,
        now = timestamp,
    )

    idle_timeout = int(policy["idleTimeoutSeconds"])
    entries = sorted(_CACHE_ENTRIES.values(), key = lambda item: item.last_used_at)
    over_capacity_count = max(0, len(entries) - int(policy["maxResidentModels"]))
    over_capacity_models = {entry.model_id for entry in entries[:over_capacity_count]}
    resident: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    for entry in entries:
        idle_for = max(0, int(timestamp - entry.last_used_at))
        seconds_until_idle = max(0, idle_timeout - idle_for)
        should_evict_idle = seconds_until_idle == 0
        should_evict_lru = entry.model_id in over_capacity_models
        state = {
            "modelId": entry.model_id,
            "runtimeType": entry.runtime_type,
            "projectId": entry.project_id,
            "loadedAt": entry.loaded_at,
            "lastUsedAt": entry.last_used_at,
            "idleForSeconds": idle_for,
            "secondsUntilIdle": seconds_until_idle,
            "hits": entry.hits,
            "active": entry.model_id == active,
        }
        resident.append(state)
        if should_evict_lru:
            action_type = "would_unload_lru"
            reason = "Depasse la limite de modeles residents pour ce profil."
        elif should_evict_idle:
            action_type = "would_unload_idle"
            reason = "Le delai idle est atteint."
        else:
            action_type = "keep_loaded"
            reason = "Encore dans la fenetre de cache."
        actions.append(
            {
                "type": action_type,
                "modelId": entry.model_id,
                "reason": reason,
                "automatic": False,
            }
        )

    for model_id in loading:
        actions.append(
            {
                "type": "wait_loading",
                "modelId": model_id,
                "reason": "Chargement en cours; aucune eviction pendant cette phase.",
                "automatic": False,
            }
        )

    return {
        "managerVersion": "model_cache_manager_v1",
        "mode": "observe_only",
        "observedAt": timestamp,
        "policy": policy,
        "runtime": {
            "activeModel": active,
            "loadedModels": loaded,
            "loadingModels": loading,
            "residentCount": len(resident),
            "runtimeType": runtime_type,
        },
        "residentModels": resident,
        "actions": actions,
        "nextAction": actions[0] if actions else None,
    }
