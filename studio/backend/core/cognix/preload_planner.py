# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX intelligent model preload planner.

The planner turns router/cache/benchmark signals into a native, auditable
preload decision. It never loads a model; it only prepares the contract a later
runtime executor can follow safely.
"""

from __future__ import annotations

from typing import Any


COGNIX_PRELOAD_PLANNER_VERSION = "cognix_preload_planner_v1"
COGNIX_LOAD_PREDICTION_VERSION = "cognix_load_prediction_v1"
COGNIX_MODEL_WARMUP_CONTRACT_VERSION = "cognix_model_warmup_contract_v1"
COGNIX_PRELOAD_QUEUE_CONTRACT_VERSION = "cognix_preload_queue_contract_v1"

DOMAIN_MODEL_ROLES = {
    "general": {"role": "generalist", "fallbackLabel": "CogniX General 3B"},
    "maths": {"role": "math_expert", "fallbackLabel": "CogniX Maths 3B"},
    "physique": {"role": "physics_expert", "fallbackLabel": "CogniX Physique 3B"},
    "code": {"role": "code_expert", "fallbackLabel": "CogniX Code 4B"},
    "business": {"role": "business_expert", "fallbackLabel": "CogniX Business 3B"},
    "research": {"role": "research_expert", "fallbackLabel": "CogniX Research 3B"},
    "education": {"role": "education_expert", "fallbackLabel": "CogniX Education 3B"},
}

PRELOAD_PRIORITY_BONUS = {
    "high": 14,
    "normal": 8,
    "low": 2,
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_model_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean or None


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed >= 0 else 0.0


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _confidence(value: Any, default: float = 0.0) -> float:
    parsed = _as_float(value)
    if parsed <= 0:
        parsed = default
    return round(min(parsed, 1.0), 3)


def _benchmark_best_model(latest_benchmark_run: dict[str, Any] | None) -> dict[str, Any] | None:
    benchmark = _as_dict(_as_dict(latest_benchmark_run).get("benchmark"))
    candidates = [
        item
        for item in _as_list(benchmark.get("modelFitness"))
        if isinstance(item, dict)
        and item.get("status") in {"recommended", "possible", "tight"}
        and int(item.get("stars") or 0) > 0
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key = lambda item: (
            int(item.get("stars") or 0),
            _as_float(item.get("estimatedTokensPerSecond")),
        ),
    )


def _target_candidate(
    *,
    classification: dict[str, Any],
    recommendation: dict[str, Any],
    latest_benchmark_run: dict[str, Any] | None,
) -> dict[str, Any]:
    domain = str(classification.get("selectedDomain") or "general")
    role = DOMAIN_MODEL_ROLES.get(domain, DOMAIN_MODEL_ROLES["general"])
    benchmark_model = _benchmark_best_model(latest_benchmark_run)
    benchmark_model_id = _clean_model_id(_as_dict(benchmark_model).get("modelId"))
    recommended_model_id = _clean_model_id(recommendation.get("modelId"))
    model_id = benchmark_model_id or recommended_model_id

    return {
        "domain": domain,
        "modelRole": role["role"],
        "modelId": model_id,
        "modelLabel": (
            _as_dict(benchmark_model).get("label")
            or classification.get("recommendedModelLabel")
            or recommendation.get("modelLabel")
            or role["fallbackLabel"]
        ),
        "providerId": recommendation.get("providerId"),
        "providerType": recommendation.get("providerType"),
        "source": "benchmark" if benchmark_model_id else "recommendation",
    }


def _priority(
    *,
    project_id: str | None,
    project_type: str | None,
    task_strategy: dict[str, Any],
    classification: dict[str, Any],
) -> int:
    value = 60
    if project_id or project_type:
        value += 20
    if task_strategy.get("path") in {"rag_first", "codex_guarded_pipeline", "tool_plan"}:
        value += 8
    if not classification.get("needsClarification"):
        value += 5
    return min(value, 95)


def _trigger_signals(
    *,
    project_id: str | None,
    project_type: str | None,
    classification: dict[str, Any],
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any],
    target: dict[str, Any],
) -> list[dict[str, Any]]:
    cache_policy = _as_dict(cache.get("policy"))
    cache_runtime = _as_dict(cache.get("runtime"))
    max_resident = _as_int(cache_policy.get("maxResidentModels"), 1)
    resident_count = _as_int(cache_runtime.get("residentCount"), 0)
    model_id = _clean_model_id(target.get("modelId"))
    loaded_models = set(_as_list(cache_runtime.get("loadedModels")))
    signals = [
        {
            "id": "classification_confidence",
            "status": "ready" if not classification.get("needsClarification") else "blocked",
            "strength": _confidence(classification.get("confidence"), 0.35),
        },
        {
            "id": "runtime_readiness",
            "status": "ready" if recommendation.get("readiness") in {"ready", "ready_with_caution", "model_missing"} else "blocked",
            "strength": _confidence(recommendation.get("confidence"), 0.45),
        },
        {
            "id": "cache_capacity",
            "status": "ready" if resident_count < max_resident else "requires_lru",
            "strength": round(max(0.1, 1 - (resident_count / max(1, max_resident + 1))), 3),
        },
        {
            "id": "target_not_loaded",
            "status": "ready" if model_id and model_id not in loaded_models else "already_loaded",
            "strength": 0.8 if model_id and model_id not in loaded_models else 0.2,
        },
    ]
    if project_id or project_type:
        signals.append(
            {
                "id": "project_scope",
                "status": "ready",
                "strength": 0.85,
                "detail": project_type or project_id,
            }
        )
    if task_strategy.get("path"):
        signals.append(
            {
                "id": "task_strategy",
                "status": "ready",
                "strength": _confidence(task_strategy.get("confidence"), 0.5),
                "detail": task_strategy.get("path"),
            }
        )
    if target.get("source") == "benchmark":
        signals.append(
            {
                "id": "benchmark_candidate",
                "status": "ready",
                "strength": 0.9,
            }
        )
    return signals


def _preload_score(signals: list[dict[str, Any]], priority: int) -> float:
    if not signals:
        return round(priority / 100, 3)
    signal_score = sum(_confidence(item.get("strength")) for item in signals) / len(signals)
    return round(min(1.0, (signal_score * 0.68) + ((priority / 100) * 0.32)), 3)


def _proposed_evictions(cache: dict[str, Any], target_model_id: str | None, required_count: int) -> list[dict[str, Any]]:
    if required_count <= 0:
        return []
    target = _clean_model_id(target_model_id)
    actions = [
        item
        for item in _as_list(cache.get("actions"))
        if isinstance(item, dict)
        and str(item.get("type") or "").startswith("would_unload")
        and _clean_model_id(item.get("modelId")) != target
    ]
    if actions:
        return [
            {
                "modelId": item.get("modelId"),
                "reason": item.get("reason"),
                "source": "cache_action",
            }
            for item in actions[:required_count]
        ]

    resident = [
        item
        for item in _as_list(cache.get("residentModels"))
        if isinstance(item, dict) and _clean_model_id(item.get("modelId")) != target
    ]
    resident.sort(
        key = lambda item: (
            bool(item.get("active")),
            _as_float(item.get("lastUsedAt")),
            str(item.get("modelId") or ""),
        )
    )
    return [
        {
            "modelId": item.get("modelId"),
            "reason": "Modele resident le moins recemment utilise.",
            "source": "resident_lru",
        }
        for item in resident[:required_count]
    ]


def _cache_preflight(
    *,
    cache: dict[str, Any],
    target: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    policy = _as_dict(cache.get("policy"))
    runtime = _as_dict(cache.get("runtime"))
    loaded_models = set(_as_list(runtime.get("loadedModels")))
    model_id = _clean_model_id(target.get("modelId"))
    max_resident = max(1, _as_int(policy.get("maxResidentModels"), 1))
    resident_count = _as_int(runtime.get("residentCount"), len(loaded_models))
    already_resident = bool(model_id and model_id in loaded_models)
    projected_resident_count = resident_count + (0 if already_resident or not model_id else 1)
    required_eviction_count = max(0, projected_resident_count - max_resident)
    if action.get("type") == "would_preload_after_lru" and required_eviction_count == 0:
        required_eviction_count = 1
    return {
        "policyTier": policy.get("tier"),
        "preloadEnabled": bool(policy.get("preloadEnabled")),
        "evictionStrategy": policy.get("evictionStrategy") or "lru",
        "maxResidentModels": max_resident,
        "residentCount": resident_count,
        "projectedResidentCount": projected_resident_count,
        "alreadyResident": already_resident,
        "requiredEvictionCount": required_eviction_count,
        "proposedEvictions": _proposed_evictions(cache, model_id, required_eviction_count),
    }


def _schedule_window(
    *,
    action: dict[str, Any],
    priority: int,
    project_id: str | None,
    project_type: str | None,
) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    if action_type in {"keep_loaded", "defer_preload"}:
        earliest_after = "none"
        window_seconds = 0
    elif project_id or project_type:
        earliest_after = "project_open_idle"
        window_seconds = 30 if priority >= 80 else 60
    else:
        earliest_after = "after_current_response"
        window_seconds = 90 if priority >= 75 else 180
    return {
        "earliestAfter": earliest_after,
        "recommendedWindowSeconds": window_seconds,
        "expiresInSeconds": 900 if project_id or project_type else 420,
        "cancelIfUserSwitchesDomain": True,
        "runOnlyWhenIdle": True,
    }


def _execution_contract(
    *,
    action: dict[str, Any],
    target: dict[str, Any],
    recommendation: dict[str, Any],
    cache_preflight: dict[str, Any],
) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    can_prepare = action_type in {"would_preload", "would_preload_after_lru"}
    blocked_when: list[str] = []
    if not target.get("modelId"):
        blocked_when.append("missing_model_id")
    if recommendation.get("readiness") not in {"ready", "ready_with_caution", "model_missing"}:
        blocked_when.append("runtime_not_ready")
    if not cache_preflight.get("preloadEnabled") and action_type != "keep_loaded":
        blocked_when.append("preload_disabled_by_cache_policy")
    if cache_preflight.get("requiredEvictionCount") and not cache_preflight.get("proposedEvictions"):
        blocked_when.append("missing_lru_eviction_candidate")
    return {
        "contractVersion": "cognix_preload_execution_contract_v1",
        "observeOnly": True,
        "executorRequired": can_prepare,
        "automaticExecutionAllowed": False,
        "requiresHumanConfirmation": action_type == "would_preload_after_lru",
        "plannedExecutor": "cognix_worker_queue:model_preload" if can_prepare else None,
        "allowedActions": [
            "record_preload_intent",
            "build_cache_load_plan",
            "queue_preload_after_policy",
        ]
        if can_prepare
        else ["record_preload_intent"],
        "blockedActions": [
            "model_load",
            "model_unload",
            "runtime_mutation",
            "generation",
            "network_model_call",
        ],
        "preconditions": {
            "modelIdResolved": bool(target.get("modelId")),
            "runtimeReady": recommendation.get("readiness") in {"ready", "ready_with_caution", "model_missing"},
            "cachePolicyAllowsPreload": bool(cache_preflight.get("preloadEnabled")),
            "alreadyResident": bool(cache_preflight.get("alreadyResident")),
            "evictionsPlanned": len(cache_preflight.get("proposedEvictions") or []),
        },
        "blockedWhen": blocked_when,
    }


def _load_prediction(
    *,
    target: dict[str, Any],
    recommendation: dict[str, Any],
    classification: dict[str, Any],
    signals: list[dict[str, Any]],
    decision_score: float,
) -> dict[str, Any]:
    predicted_model_id = _clean_model_id(target.get("modelId"))
    candidates: list[dict[str, Any]] = []
    if predicted_model_id:
        candidates.append(
            {
                "modelId": predicted_model_id,
                "modelLabel": target.get("modelLabel"),
                "modelRole": target.get("modelRole"),
                "domain": target.get("domain"),
                "source": target.get("source"),
                "confidence": decision_score,
                "reason": "Candidat principal choisi par routage, recommandation et signaux cache.",
            }
        )
    recommended_model_id = _clean_model_id(recommendation.get("modelId"))
    if recommended_model_id and recommended_model_id != predicted_model_id:
        candidates.append(
            {
                "modelId": recommended_model_id,
                "modelLabel": recommendation.get("modelLabel"),
                "modelRole": "runtime_recommendation",
                "domain": classification.get("selectedDomain") or "general",
                "source": "recommendation",
                "confidence": _confidence(recommendation.get("confidence"), 0.45),
                "reason": "Fallback recommande par le Model Recommender.",
            }
        )
    signal_ids = [str(item.get("id")) for item in signals if isinstance(item, dict) and item.get("id")]
    blocked_signal_ids = [
        str(item.get("id"))
        for item in signals
        if isinstance(item, dict) and str(item.get("status") or "").startswith("blocked")
    ]
    status = "predicted" if predicted_model_id and decision_score >= 0.5 and not blocked_signal_ids else "defer_prediction"
    return {
        "predictionVersion": COGNIX_LOAD_PREDICTION_VERSION,
        "mode": "observe_only",
        "status": status,
        "predictedNextModelId": predicted_model_id,
        "confidence": decision_score,
        "candidateCount": len(candidates),
        "candidates": candidates,
        "signalIds": signal_ids,
        "blockedSignalIds": blocked_signal_ids,
        "policies": {
            "singleBestPrediction": True,
            "fallbackCandidateAllowed": True,
            "frontendMayDisplayRawScores": False,
            "predictionMayTriggerDirectLoad": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "cacheMutation": False,
            "runtimeMutation": False,
            "preloadEventWrite": False,
        },
    }


def _warmup_contract(
    *,
    action: dict[str, Any],
    target: dict[str, Any],
    load_prediction: dict[str, Any],
    cache_preflight: dict[str, Any],
    schedule: dict[str, Any],
    execution_contract: dict[str, Any],
) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    can_prepare = action_type in {"would_preload", "would_preload_after_lru"}
    blocked_when = [
        str(item)
        for item in execution_contract.get("blockedWhen", [])
        if str(item or "").strip()
    ]
    if load_prediction.get("status") != "predicted":
        blocked_when.append("load_prediction_not_ready")
    if _as_float(load_prediction.get("confidence")) < 0.55:
        blocked_when.append("prediction_confidence_below_threshold")
    if bool(cache_preflight.get("alreadyResident")):
        blocked_when.append("model_already_resident")
    if not schedule.get("runOnlyWhenIdle"):
        blocked_when.append("idle_window_required")
    blocked_when = sorted(set(blocked_when))
    allowed_to_queue = can_prepare and not blocked_when
    return {
        "contractVersion": COGNIX_MODEL_WARMUP_CONTRACT_VERSION,
        "mode": "warmup_contract_dry_run",
        "targetModelId": target.get("modelId"),
        "targetModelRole": target.get("modelRole"),
        "predictionVersion": load_prediction.get("predictionVersion"),
        "preloadExecutionContractVersion": execution_contract.get("contractVersion"),
        "allowedToPrepareWarmup": can_prepare,
        "readyForWarmup": False,
        "wouldQueueWarmupAfterApproval": allowed_to_queue,
        "willWarmupNow": False,
        "automaticWarmupAllowed": False,
        "frontendDirectWarmupAllowed": False,
        "plannedExecutor": "cognix_worker_queue:model_warmup" if can_prepare else None,
        "nextRequiredGate": blocked_when[0] if blocked_when else "idle_executor_approval",
        "preconditions": {
            "modelIdResolved": bool(target.get("modelId")),
            "loadPredictionReady": load_prediction.get("status") == "predicted",
            "predictionConfidence": load_prediction.get("confidence"),
            "minimumPredictionConfidence": 0.55,
            "cachePolicyAllowsPreload": bool(cache_preflight.get("preloadEnabled")),
            "alreadyResident": bool(cache_preflight.get("alreadyResident")),
            "evictionsPlanned": len(cache_preflight.get("proposedEvictions") or []),
            "idleWindowRequired": True,
            "runOnlyWhenIdle": bool(schedule.get("runOnlyWhenIdle")),
            "humanApprovalRequired": action_type == "would_preload_after_lru",
        },
        "schedule": {
            "earliestAfter": schedule.get("earliestAfter"),
            "recommendedWindowSeconds": schedule.get("recommendedWindowSeconds"),
            "expiresInSeconds": schedule.get("expiresInSeconds"),
            "cancelIfUserSwitchesDomain": bool(schedule.get("cancelIfUserSwitchesDomain")),
        },
        "allowedActions": [
            "record_warmup_intent",
            "verify_cache_preflight",
            "verify_prediction_still_valid",
            "queue_warmup_after_idle_policy",
        ]
        if can_prepare
        else ["record_warmup_intent"],
        "blockedActions": [
            "model_load",
            "model_unload",
            "runtime_mutation",
            "cache_mutation",
            "generation",
            "network_model_call",
            "frontend_direct_warmup",
        ],
        "blockedWhen": blocked_when,
        "sideEffects": {
            "modelLoad": False,
            "modelUnload": False,
            "cacheMutation": False,
            "runtimeMutation": False,
            "generation": False,
            "networkModelCall": False,
            "preloadEventWrite": False,
            "jobEnqueue": False,
        },
    }


def _candidate_priority(
    *,
    base_priority: int,
    cache_intent: dict[str, Any],
    candidate_score: float,
    primary: bool,
) -> int:
    priority_label = str(cache_intent.get("preloadPriority") or "normal")
    priority_bonus = PRELOAD_PRIORITY_BONUS.get(priority_label, PRELOAD_PRIORITY_BONUS["normal"])
    primary_bonus = 14 if primary else 5
    score_bonus = round(candidate_score * 10)
    return min(98, max(1, base_priority + priority_bonus + primary_bonus + score_bonus - 20))


def _external_moe_candidates(
    *,
    classification: dict[str, Any],
    target: dict[str, Any],
    base_priority: int,
) -> list[dict[str, Any]]:
    external_moe = _as_dict(classification.get("externalMoePlan"))
    cache_intent = _as_dict(external_moe.get("cacheIntent"))
    entries: list[tuple[dict[str, Any], bool, str]] = []
    primary_expert = _as_dict(external_moe.get("primaryExpert"))
    if primary_expert:
        entries.append((primary_expert, True, "external_moe_primary"))
    for item in _as_list(external_moe.get("secondaryExperts")):
        if isinstance(item, dict):
            entries.append((item, False, "external_moe_secondary"))
    if not entries:
        entries.append(
            (
                {
                    "rank": 1,
                    "expertId": classification.get("recommendedExpertId"),
                    "domain": target.get("domain") or classification.get("selectedDomain") or "general",
                    "role": target.get("modelRole"),
                    "modelId": classification.get("recommendedModelId") or target.get("modelId"),
                    "modelLabel": classification.get("recommendedModelLabel") or target.get("modelLabel"),
                    "score": classification.get("confidence"),
                },
                True,
                "router_target",
            )
        )

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for entry, primary, source in entries:
        domain = str(entry.get("domain") or target.get("domain") or "general")
        role = str(entry.get("role") or DOMAIN_MODEL_ROLES.get(domain, DOMAIN_MODEL_ROLES["general"])["role"])
        expert_model_id = _clean_model_id(entry.get("modelId"))
        model_id = expert_model_id
        model_label = entry.get("modelLabel")
        if primary:
            model_id = _clean_model_id(target.get("modelId")) or expert_model_id
            model_label = target.get("modelLabel") or model_label
        score = _confidence(entry.get("score"), _confidence(classification.get("confidence"), 0.42))
        expert_id = str(entry.get("expertId") or classification.get("recommendedExpertId") or "cognix-general")
        dedupe_key = (expert_id, model_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "rank": _as_int(entry.get("rank"), len(candidates) + 1),
                "expertId": expert_id,
                "domain": domain,
                "modelRole": role,
                "modelId": model_id,
                "expertModelId": expert_model_id,
                "modelLabel": model_label or DOMAIN_MODEL_ROLES.get(domain, DOMAIN_MODEL_ROLES["general"])["fallbackLabel"],
                "primary": primary,
                "source": source,
                "score": score,
                "priority": _candidate_priority(
                    base_priority = base_priority,
                    cache_intent = cache_intent,
                    candidate_score = score,
                    primary = primary,
                ),
                "willPreloadNow": False,
                "willLoad": False,
                "willGenerate": False,
            }
        )
    candidates.sort(key = lambda item: (not bool(item.get("primary")), int(item.get("rank") or 99)))
    return candidates


def _queue_status(action_type: str, queued: list[dict[str, Any]], classification: dict[str, Any]) -> str:
    if queued:
        return "approval_required" if action_type == "would_preload_after_lru" else "queue_ready"
    if action_type == "keep_loaded":
        return "already_resident"
    if classification.get("needsClarification"):
        return "blocked_clarification"
    return "deferred"


def _defer_candidate(
    candidate: dict[str, Any],
    *,
    reason: str,
    cache_preflight: dict[str, Any],
) -> dict[str, Any]:
    return {
        **candidate,
        "queueState": "deferred",
        "deferReason": reason,
        "cachePreflight": cache_preflight,
        "requiresExecutor": False,
        "automaticPreloadAllowed": False,
        "frontendDirectModelLoadAllowed": False,
        "willLoadNow": False,
    }


def _preload_queue_contract(
    *,
    classification: dict[str, Any],
    target: dict[str, Any],
    action: dict[str, Any],
    cache: dict[str, Any],
    cache_preflight: dict[str, Any],
    schedule: dict[str, Any],
    execution_contract: dict[str, Any],
    priority: int,
) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    candidates = _external_moe_candidates(
        classification = classification,
        target = target,
        base_priority = priority,
    )
    max_queue_depth = min(3, max(1, _as_int(cache_preflight.get("maxResidentModels"), 1)))
    queue_allowed = action_type in {"would_preload", "would_preload_after_lru"}
    queued: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_target = {
            "modelId": candidate.get("modelId"),
            "modelRole": candidate.get("modelRole"),
            "domain": candidate.get("domain"),
        }
        candidate_preflight = _cache_preflight(
            cache = cache,
            target = candidate_target,
            action = action,
        )
        defer_reason = ""
        if not queue_allowed:
            defer_reason = action_type or "preload_not_selected"
        elif not candidate.get("modelId"):
            defer_reason = "missing_model_id"
        elif candidate_preflight.get("alreadyResident"):
            defer_reason = "model_already_resident"
        elif len(queued) >= max_queue_depth:
            defer_reason = "queue_depth_limit"
        elif candidate_preflight.get("requiredEvictionCount") and not candidate_preflight.get("proposedEvictions"):
            defer_reason = "missing_lru_eviction_candidate"

        if defer_reason:
            deferred.append(
                _defer_candidate(
                    candidate,
                    reason = defer_reason,
                    cache_preflight = candidate_preflight,
                )
            )
            continue

        queued.append(
            {
                **candidate,
                "queueState": "planned",
                "cachePreflight": candidate_preflight,
                "schedule": {
                    "earliestAfter": schedule.get("earliestAfter"),
                    "recommendedWindowSeconds": schedule.get("recommendedWindowSeconds"),
                    "expiresInSeconds": schedule.get("expiresInSeconds"),
                    "runOnlyWhenIdle": bool(schedule.get("runOnlyWhenIdle")),
                },
                "requiresExecutor": bool(execution_contract.get("executorRequired")),
                "requiresHumanConfirmation": action_type == "would_preload_after_lru",
                "automaticPreloadAllowed": False,
                "frontendDirectModelLoadAllowed": False,
                "willLoadNow": False,
            }
        )

    selected_candidate = queued[0] if queued else None
    return {
        "contractVersion": COGNIX_PRELOAD_QUEUE_CONTRACT_VERSION,
        "mode": "external_moe_preload_queue_dry_run",
        "status": _queue_status(action_type, queued, classification),
        "externalMoeRouterVersion": _as_dict(classification.get("externalMoePlan")).get("routerVersion"),
        "preloadExecutionContractVersion": execution_contract.get("contractVersion"),
        "actionType": action_type,
        "candidateCount": len(candidates),
        "queueDepth": len(queued),
        "maxQueueDepth": max_queue_depth,
        "selectedCandidate": selected_candidate,
        "queuedCandidates": queued,
        "deferredCandidates": deferred,
        "cacheGuard": {
            "policyTier": cache_preflight.get("policyTier"),
            "preloadEnabled": bool(cache_preflight.get("preloadEnabled")),
            "evictionStrategy": cache_preflight.get("evictionStrategy"),
            "maxResidentModels": cache_preflight.get("maxResidentModels"),
            "residentCount": cache_preflight.get("residentCount"),
            "projectedResidentCount": cache_preflight.get("projectedResidentCount"),
            "requiredEvictionCount": cache_preflight.get("requiredEvictionCount"),
            "proposedEvictions": cache_preflight.get("proposedEvictions", []),
        },
        "executionGate": {
            "backendExecutorRequired": bool(queued),
            "plannedExecutor": "cognix_worker_queue:model_preload" if queued else None,
            "queueAllowedAfterPolicy": bool(queued),
            "automaticPreloadAllowed": False,
            "willLoadNow": False,
            "willMutateCacheNow": False,
            "frontendDirectModelLoadAllowed": False,
            "requiresHumanConfirmation": action_type == "would_preload_after_lru",
            "runOnlyWhenIdle": bool(schedule.get("runOnlyWhenIdle")),
        },
        "policies": {
            "boundedQueue": True,
            "maxPrimaryExperts": 1,
            "secondaryExpertsAllowed": True,
            "frontendMayDisplayRawScores": False,
            "queueMayTriggerDirectLoad": False,
        },
        "blockedActions": [
            "model_load",
            "model_unload",
            "runtime_mutation",
            "cache_mutation",
            "generation",
            "network_model_call",
            "frontend_direct_model_load",
        ],
        "sideEffects": {
            "modelLoad": False,
            "modelUnload": False,
            "cacheMutation": False,
            "runtimeMutation": False,
            "generation": False,
            "networkModelCall": False,
            "jobEnqueue": False,
        },
    }


def _action_for_target(
    *,
    target: dict[str, Any],
    cache: dict[str, Any],
    recommendation: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    model_id = target.get("modelId")
    cache_policy = _as_dict(cache.get("policy"))
    runtime = _as_dict(cache.get("runtime"))
    loaded_models = set(_as_list(runtime.get("loadedModels")))
    resident_count = int(runtime.get("residentCount") or len(loaded_models))
    max_resident = int(cache_policy.get("maxResidentModels") or 1)
    readiness = str(recommendation.get("readiness") or "unknown")

    if not model_id:
        return {
            "type": "defer_preload",
            "reason": "Aucun modele candidat stable pour ce domaine.",
            "automatic": False,
        }
    if classification.get("needsClarification"):
        return {
            "type": "defer_preload",
            "reason": "Domaine ambigu: attendre une clarification avant prechargement.",
            "automatic": False,
        }
    if readiness not in {"ready", "ready_with_caution", "model_missing"}:
        return {
            "type": "defer_preload",
            "reason": "Runtime local pas pret: prechargement reporte.",
            "automatic": False,
        }
    if model_id in loaded_models:
        return {
            "type": "keep_loaded",
            "reason": "Le modele cible est deja resident.",
            "automatic": False,
        }
    if not bool(cache_policy.get("preloadEnabled")):
        return {
            "type": "defer_preload",
            "reason": "Profil petit local: CogniX evite le prechargement silencieux.",
            "automatic": False,
        }
    if resident_count >= max_resident:
        return {
            "type": "would_preload_after_lru",
            "reason": "Prechargement possible apres eviction LRU controlee.",
            "automatic": False,
        }
    return {
        "type": "would_preload",
        "reason": "Profil compatible: CogniX peut precharger ce modele plus tard via executor.",
        "automatic": False,
    }


def build_preload_plan(
    *,
    objective: str,
    project_type: str | None,
    project_id: str | None,
    classification: dict[str, Any],
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any],
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = _target_candidate(
        classification = classification,
        recommendation = recommendation,
        latest_benchmark_run = latest_benchmark_run,
    )
    action = _action_for_target(
        target = target,
        cache = cache,
        recommendation = recommendation,
        classification = classification,
    )
    priority = _priority(
        project_id = project_id,
        project_type = project_type,
        task_strategy = task_strategy,
        classification = classification,
    )
    signals = _trigger_signals(
        project_id = project_id,
        project_type = project_type,
        classification = classification,
        task_strategy = task_strategy,
        recommendation = recommendation,
        cache = cache,
        target = target,
    )
    target["priority"] = priority
    target["state"] = action["type"]
    target["reason"] = action["reason"]
    target["decisionScore"] = _preload_score(signals, priority)
    load_prediction = _load_prediction(
        target = target,
        recommendation = recommendation,
        classification = classification,
        signals = signals,
        decision_score = target["decisionScore"],
    )
    cache_preflight = _cache_preflight(
        cache = cache,
        target = target,
        action = action,
    )
    schedule = _schedule_window(
        action = action,
        priority = priority,
        project_id = project_id,
        project_type = project_type,
    )
    execution_contract = _execution_contract(
        action = action,
        target = target,
        recommendation = recommendation,
        cache_preflight = cache_preflight,
    )
    warmup_contract = _warmup_contract(
        action = action,
        target = target,
        load_prediction = load_prediction,
        cache_preflight = cache_preflight,
        schedule = schedule,
        execution_contract = execution_contract,
    )
    preload_queue_contract = _preload_queue_contract(
        classification = classification,
        target = target,
        action = action,
        cache = cache,
        cache_preflight = cache_preflight,
        schedule = schedule,
        execution_contract = execution_contract,
        priority = priority,
    )

    warnings: list[str] = []
    if action["type"].startswith("defer"):
        warnings.append(str(action["reason"]))
    if _as_dict(cache.get("policy")).get("tier") == "small_local":
        warnings.append("Petit profil local: un seul modele resident recommande.")
    if task_strategy.get("path") == "guided_fine_tuning":
        warnings.append("Fine-tuning detecte: ne pas precharger avant estimation dataset.")

    return {
        "plannerVersion": COGNIX_PRELOAD_PLANNER_VERSION,
        "mode": "observe_only",
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "projectId": project_id,
        "projectType": project_type,
        "trigger": "project" if project_id or project_type else "chat",
        "target": target,
        "actions": [
            {
                **action,
                "modelId": target.get("modelId"),
                "modelRole": target.get("modelRole"),
                "priority": priority,
                "decisionScore": target["decisionScore"],
                "loadPredictionStatus": load_prediction.get("status"),
                "warmupContractVersion": warmup_contract.get("contractVersion"),
                "preloadQueueContractVersion": preload_queue_contract.get("contractVersion"),
                "preloadQueueStatus": preload_queue_contract.get("status"),
                "queuedCandidateCount": preload_queue_contract.get("queueDepth"),
                "schedule": schedule,
                "requiresExecutor": bool(execution_contract.get("executorRequired")),
                "blockedBy": execution_contract.get("blockedWhen", []),
            }
        ],
        "triggerSignals": signals,
        "loadPrediction": load_prediction,
        "cachePreflight": cache_preflight,
        "schedule": schedule,
        "executionContract": execution_contract,
        "warmupContract": warmup_contract,
        "preloadQueueContract": preload_queue_contract,
        "limits": {
            "maxResidentModels": _as_dict(cache.get("policy")).get("maxResidentModels"),
            "residentCount": _as_dict(cache.get("runtime")).get("residentCount"),
            "preloadEnabled": bool(_as_dict(cache.get("policy")).get("preloadEnabled")),
            "evictionStrategy": _as_dict(cache.get("policy")).get("evictionStrategy"),
        },
        "warnings": warnings,
        "reason": str(action["reason"]),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
            "modelUnload": False,
            "cacheMutation": False,
            "runtimeMutation": False,
            "preloadEventWrite": False,
            "jobEnqueue": False,
        },
    }
