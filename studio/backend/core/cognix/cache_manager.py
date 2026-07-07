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
MODEL_CACHE_MANAGER_VERSION = "model_cache_manager_v1"
MODEL_CACHE_PRESSURE_PLAN_VERSION = "model_cache_pressure_plan_v1"


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


def _memory_guard(
    hardware: dict[str, Any],
    policy: dict[str, Any],
    *,
    estimated_ram_gb: float | None,
) -> dict[str, Any]:
    memory = hardware.get("memory") if isinstance(hardware, dict) else {}
    if not isinstance(memory, dict):
        memory = {}
    available_gb = _as_float(memory.get("availableGb"))
    tier = str(policy.get("tier") or "balanced_local")
    reserve_gb = 1.5 if tier == "small_local" else 2.0 if tier == "balanced_local" else 4.0
    if estimated_ram_gb is None:
        return {
            "status": "unknown_estimate",
            "availableGb": available_gb,
            "estimatedTargetRamGb": None,
            "reserveGb": reserve_gb,
            "estimatedAfterLoadGb": None,
            "requiresEvictionForMemory": False,
            "reason": "Estimation RAM cible absente: appliquer seulement les limites LRU/cache.",
        }
    if available_gb is None:
        return {
            "status": "unknown_available_memory",
            "availableGb": None,
            "estimatedTargetRamGb": estimated_ram_gb,
            "reserveGb": reserve_gb,
            "estimatedAfterLoadGb": None,
            "requiresEvictionForMemory": False,
            "reason": "Memoire disponible inconnue: appliquer les limites LRU/cache avant execution.",
        }
    after = available_gb - estimated_ram_gb
    ok = after >= reserve_gb
    return {
        "status": "safe" if ok else "needs_eviction",
        "availableGb": available_gb,
        "estimatedTargetRamGb": estimated_ram_gb,
        "reserveGb": reserve_gb,
        "estimatedAfterLoadGb": round(after, 2),
        "requiresEvictionForMemory": not ok,
        "reason": (
            "Memoire suffisante pour charger le modele cible en conservant une reserve."
            if ok
            else "Memoire disponible insuffisante: decharger un modele resident avant chargement."
        ),
    }


def _cache_memory_pressure(hardware: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    memory = hardware.get("memory") if isinstance(hardware, dict) else {}
    if not isinstance(memory, dict):
        memory = {}
    available_gb = _as_float(memory.get("availableGb"))
    tier = str(policy.get("tier") or "balanced_local")
    reserve_gb = 1.5 if tier == "small_local" else 2.0 if tier == "balanced_local" else 4.0
    if available_gb is None:
        return {
            "status": "unknown_available_memory",
            "availableGb": None,
            "reserveGb": reserve_gb,
            "requiresEvictionForMemory": False,
            "reason": "Memoire disponible inconnue: appliquer les garde-fous LRU/idle uniquement.",
        }
    pressure = available_gb <= reserve_gb
    return {
        "status": "pressure" if pressure else "healthy",
        "availableGb": available_gb,
        "reserveGb": reserve_gb,
        "requiresEvictionForMemory": pressure,
        "reason": (
            "Reserve RAM atteinte: proposer une eviction avant nouveau chargement."
            if pressure
            else "Reserve RAM suffisante: aucune eviction memoire immediate."
        ),
    }


def _eviction_candidates(cache_state: dict[str, Any], *, target_model_id: str | None) -> list[dict[str, Any]]:
    policy = cache_state.get("policy") if isinstance(cache_state, dict) else {}
    if not isinstance(policy, dict):
        policy = {}
    idle_timeout = int(policy.get("idleTimeoutSeconds") or CHAT_IDLE_TIMEOUT_SECONDS)
    resident = cache_state.get("residentModels") if isinstance(cache_state, dict) else []
    if not isinstance(resident, list):
        resident = []
    records = [item for item in resident if isinstance(item, dict)]
    records.sort(
        key = lambda item: (
            bool(item.get("active")),
            float(item.get("lastUsedAt") or 0),
            str(item.get("modelId") or ""),
        )
    )
    candidates: list[dict[str, Any]] = []
    for rank, item in enumerate(records, start = 1):
        model_id = _clean_model_id(str(item.get("modelId") or ""))
        if not model_id or model_id == target_model_id:
            continue
        idle_for = int(_as_float(item.get("idleForSeconds")) or 0)
        reason_code = "idle_timeout" if idle_for >= idle_timeout else "least_recently_used"
        if item.get("active"):
            reason_code = "active_last_resort"
        candidates.append(
            {
                "rank": rank,
                "modelId": model_id,
                "active": bool(item.get("active")),
                "projectId": item.get("projectId"),
                "idleForSeconds": idle_for,
                "hits": int(_as_float(item.get("hits")) or 0),
                "reasonCode": reason_code,
                "reason": (
                    "Modele idle: candidat prioritaire a l'eviction."
                    if reason_code == "idle_timeout"
                    else (
                        "Modele actif: eviction uniquement en dernier recours."
                        if reason_code == "active_last_resort"
                        else "Modele le moins recemment utilise."
                    )
                ),
            }
        )
    return candidates


def _select_pressure_evictions(
    candidates: list[dict[str, Any]],
    *,
    required_count: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        model_id = _clean_model_id(str(item.get("modelId") or ""))
        if not model_id or model_id in seen:
            return
        selected.append(item)
        seen.add(model_id)

    for item in candidates:
        if item.get("reasonCode") == "idle_timeout":
            add(item)

    for item in candidates:
        if len(selected) >= required_count:
            break
        if item.get("reasonCode") == "least_recently_used":
            add(item)

    for item in candidates:
        if len(selected) >= required_count:
            break
        if item.get("reasonCode") == "active_last_resort":
            add(item)

    return selected


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
        "managerVersion": MODEL_CACHE_MANAGER_VERSION,
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


def build_cache_load_plan(
    hardware: dict[str, Any],
    *,
    cache_state: dict[str, Any],
    target_model_id: str,
    target_runtime_type: str | None = None,
    estimated_ram_gb: float | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    target = _clean_model_id(target_model_id)
    policy = cache_state.get("policy") if isinstance(cache_state, dict) else {}
    if not isinstance(policy, dict):
        policy = {}
    runtime = cache_state.get("runtime") if isinstance(cache_state, dict) else {}
    if not isinstance(runtime, dict):
        runtime = {}
    loaded = set(_unique_models(runtime.get("loadedModels") if isinstance(runtime.get("loadedModels"), list) else []))
    loading = set(_unique_models(runtime.get("loadingModels") if isinstance(runtime.get("loadingModels"), list) else []))
    resident_count = int(_as_float(runtime.get("residentCount")) or len(loaded))
    max_resident = max(1, int(_as_float(policy.get("maxResidentModels")) or 1))
    already_resident = bool(target and target in loaded)
    currently_loading = bool(target and target in loading)
    projected_resident_count = resident_count + (0 if already_resident or currently_loading else 1)
    capacity_eviction_count = max(0, projected_resident_count - max_resident)
    normalized_estimate = _as_float(estimated_ram_gb)
    memory = _memory_guard(
        hardware,
        policy,
        estimated_ram_gb = normalized_estimate,
    )
    candidates = _eviction_candidates(cache_state, target_model_id = target)
    required_count = capacity_eviction_count
    if memory["requiresEvictionForMemory"] and required_count == 0 and not already_resident:
        required_count = 1
    selected = candidates[:required_count]
    blockers: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    if not target:
        blockers.append({"id": "missing_target_model", "reason": "Aucun modele cible valide."})
    if currently_loading:
        actions.append(
            {
                "type": "wait_existing_load",
                "modelId": target,
                "reason": "Le modele cible est deja en cours de chargement.",
                "automatic": False,
            }
        )
    elif already_resident:
        actions.append(
            {
                "type": "keep_loaded",
                "modelId": target,
                "reason": "Le modele cible est deja resident.",
                "automatic": False,
            }
        )
    elif required_count > len(selected):
        blockers.append(
            {
                "id": "insufficient_eviction_candidates",
                "reason": "Pas assez de modeles residents a decharger pour respecter les limites cache/RAM.",
            }
        )

    for item in selected:
        actions.append(
            {
                "type": "would_unload_before_load",
                "modelId": item["modelId"],
                "reason": item["reason"],
                "reasonCode": item["reasonCode"],
                "automatic": False,
            }
        )

    if target and not already_resident and not currently_loading and not blockers:
        actions.append(
            {
                "type": "would_load_model",
                "modelId": target,
                "runtimeType": target_runtime_type or runtime.get("runtimeType") or "unknown",
                "reason": "Cache et garde memoire prepares pour un chargement controle.",
                "automatic": False,
            }
        )

    allowed_to_prepare = bool(target) and not blockers
    return {
        "managerVersion": MODEL_CACHE_MANAGER_VERSION,
        "mode": "dry_run",
        "target": {
            "modelId": target,
            "runtimeType": target_runtime_type or runtime.get("runtimeType") or "unknown",
            "projectId": project_id,
            "estimatedRamGb": normalized_estimate,
            "alreadyResident": already_resident,
            "currentlyLoading": currently_loading,
        },
        "policy": {
            "tier": policy.get("tier"),
            "maxResidentModels": max_resident,
            "idleTimeoutSeconds": policy.get("idleTimeoutSeconds"),
            "evictionStrategy": policy.get("evictionStrategy") or "lru",
            "automaticEvictionEnabled": bool(policy.get("automaticEvictionEnabled")),
        },
        "memoryGuard": memory,
        "capacity": {
            "residentCount": resident_count,
            "projectedResidentCount": projected_resident_count,
            "requiredEvictionCount": required_count,
            "capacityEvictionCount": capacity_eviction_count,
        },
        "evictionCandidates": candidates,
        "selectedEvictions": selected,
        "actions": actions,
        "allowedToPrepare": allowed_to_prepare,
        "blockedReasons": blockers,
        "reason": (
            "Plan cache pret pour chargement controle."
            if allowed_to_prepare
            else "Chargement differe par les garde-fous cache/memoire."
        ),
        "sideEffects": {
            "modelLoad": False,
            "modelUnload": False,
            "cacheMutation": False,
            "runtimeMutation": False,
            "networkModelCall": False,
            "generation": False,
        },
    }


def build_cache_pressure_plan(
    hardware: dict[str, Any],
    *,
    cache_state: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    policy = cache_state.get("policy") if isinstance(cache_state, dict) else {}
    if not isinstance(policy, dict):
        policy = {}
    runtime = cache_state.get("runtime") if isinstance(cache_state, dict) else {}
    if not isinstance(runtime, dict):
        runtime = {}
    resident = cache_state.get("residentModels") if isinstance(cache_state, dict) else []
    resident_count = len(resident) if isinstance(resident, list) else 0
    max_resident = max(1, int(_as_float(policy.get("maxResidentModels")) or 1))
    over_capacity_count = max(0, resident_count - max_resident)
    memory_pressure = _cache_memory_pressure(hardware, policy)
    candidates = _eviction_candidates(cache_state, target_model_id = None)
    idle_candidates = [
        item for item in candidates if item.get("reasonCode") == "idle_timeout"
    ]
    required_count = max(
        over_capacity_count,
        1 if memory_pressure["requiresEvictionForMemory"] else 0,
        len(idle_candidates),
    )
    proposed = _select_pressure_evictions(candidates, required_count = required_count)
    actions: list[dict[str, Any]] = []
    for item in proposed:
        reason_code = str(item.get("reasonCode") or "")
        if reason_code == "idle_timeout":
            action_type = "would_unload_for_idle"
        elif memory_pressure["requiresEvictionForMemory"]:
            action_type = "would_unload_for_memory_pressure"
        else:
            action_type = "would_unload_for_lru"
        actions.append(
            {
                "type": action_type,
                "modelId": item.get("modelId"),
                "reason": item.get("reason"),
                "reasonCode": reason_code,
                "automatic": False,
            }
        )

    pressure_detected = bool(
        proposed
        or over_capacity_count > 0
        or memory_pressure["requiresEvictionForMemory"]
        or idle_candidates
    )
    return {
        "managerVersion": MODEL_CACHE_MANAGER_VERSION,
        "pressurePlanVersion": MODEL_CACHE_PRESSURE_PLAN_VERSION,
        "mode": "cache_pressure_dry_run",
        "status": "pressure_detected" if pressure_detected else "healthy",
        "projectId": project_id,
        "policy": {
            "tier": policy.get("tier"),
            "maxResidentModels": max_resident,
            "idleTimeoutSeconds": policy.get("idleTimeoutSeconds"),
            "evictionStrategy": policy.get("evictionStrategy") or "lru",
            "automaticEvictionEnabled": bool(policy.get("automaticEvictionEnabled")),
        },
        "runtime": {
            "activeModel": runtime.get("activeModel"),
            "runtimeType": runtime.get("runtimeType") or "unknown",
            "residentCount": resident_count,
            "loadedModels": runtime.get("loadedModels") or [],
            "loadingModels": runtime.get("loadingModels") or [],
        },
        "memoryPressure": memory_pressure,
        "capacityPressure": {
            "residentCount": resident_count,
            "maxResidentModels": max_resident,
            "overCapacityCount": over_capacity_count,
            "requiresEvictionForCapacity": over_capacity_count > 0,
        },
        "idlePressure": {
            "idleCandidateCount": len(idle_candidates),
            "idleCandidateModelIds": [item.get("modelId") for item in idle_candidates],
        },
        "evictionCandidates": candidates,
        "proposedEvictions": proposed,
        "actions": actions,
        "executionBoundary": {
            "backendOrchestratorRequired": True,
            "frontendDirectUnloadAllowed": False,
            "automaticUnloadAllowed": False,
            "requiresFreshRuntimeSnapshot": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "modelUnload": False,
            "cacheMutation": False,
            "runtimeMutation": False,
            "networkModelCall": False,
            "generation": False,
        },
    }
