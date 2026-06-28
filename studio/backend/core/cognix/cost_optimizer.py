# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI cost optimizer.

This module chooses a dry-run execution target from local, cloud, personal
server, and enterprise server options. It estimates cost, latency, and privacy
fit without calling providers, loading models, launching jobs, or mutating
runtime configuration.
"""

from __future__ import annotations

import math
from typing import Any


COGNIX_COST_OPTIMIZER_VERSION = "cognix_cost_optimizer_v1"
COGNIX_PROVIDER_PRICING_STORE_VERSION = "cognix_provider_pricing_store_v1"
COGNIX_EXECUTION_PLANNER_VERSION = "cognix_execution_planner_v1"
COGNIX_PRIVACY_POLICY_VERSION = "cognix_privacy_policy_v1"

PRIORITY_ALIASES = {
    "balanced": "balanced",
    "balance": "balanced",
    "equilibre": "balanced",
    "cost": "cost",
    "budget": "cost",
    "cheap": "cost",
    "prix": "cost",
    "cout": "cost",
    "speed": "speed",
    "fast": "speed",
    "vitesse": "speed",
    "privacy": "privacy",
    "confidentialite": "privacy",
    "private": "privacy",
}

SENSITIVE_LEVELS = {"internal", "medium", "confidential", "high", "critical", "secret"}
SENSITIVE_SIGNALS = (
    "secret",
    "token",
    "password",
    "mot de passe",
    "api key",
    "cle api",
    "private key",
    "jwt",
    "client",
    "customer",
    "rgpd",
    "gdpr",
    "database",
    "base de donnees",
    "medical",
    "finance",
    "confidentiel",
    "production",
)

DEFAULT_PROVIDER_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "providerId": "local-ollama",
        "displayName": "Local",
        "executionTarget": "local",
        "label": "Local : gratuit mais lent",
        "status": "available",
        "pricing": {
            "inputPer1kUsd": 0.0,
            "outputPer1kUsd": 0.0,
            "fixedSessionUsd": 0.0,
            "minimumRequestUsd": 0.0,
        },
        "latency": {"baseMs": 1800, "per1kTokensMs": 420, "speedRank": 2},
        "privacy": {
            "tier": "device_only",
            "score": 100,
            "sensitiveDataAllowed": True,
            "dataLeavesDevice": False,
            "requiresExplicitCloudValidation": False,
        },
        "policy": {"networkRequired": False, "billingRequired": False, "ownedBoundary": True},
    },
    {
        "providerId": "cloud-fast-api",
        "displayName": "Cloud",
        "executionTarget": "cloud_api",
        "label": "Cloud : rapide mais payant",
        "status": "available",
        "pricing": {
            "inputPer1kUsd": 0.001,
            "outputPer1kUsd": 0.003,
            "fixedSessionUsd": 0.0,
            "minimumRequestUsd": 0.002,
        },
        "latency": {"baseMs": 420, "per1kTokensMs": 85, "speedRank": 5},
        "privacy": {
            "tier": "third_party_cloud",
            "score": 54,
            "sensitiveDataAllowed": False,
            "dataLeavesDevice": True,
            "requiresExplicitCloudValidation": True,
        },
        "policy": {"networkRequired": True, "billingRequired": True, "ownedBoundary": False},
    },
    {
        "providerId": "personal-server",
        "displayName": "Serveur personnel",
        "executionTarget": "personal_server",
        "label": "Serveur personnel : controle garde, cout faible",
        "status": "available",
        "pricing": {
            "inputPer1kUsd": 0.0004,
            "outputPer1kUsd": 0.0009,
            "fixedSessionUsd": 0.001,
            "minimumRequestUsd": 0.001,
        },
        "latency": {"baseMs": 820, "per1kTokensMs": 190, "speedRank": 4},
        "privacy": {
            "tier": "self_hosted",
            "score": 86,
            "sensitiveDataAllowed": True,
            "dataLeavesDevice": True,
            "requiresExplicitCloudValidation": False,
        },
        "policy": {"networkRequired": True, "billingRequired": False, "ownedBoundary": True},
    },
    {
        "providerId": "enterprise-server",
        "displayName": "Serveur entreprise",
        "executionTarget": "enterprise_server",
        "label": "Serveur entreprise : recommande",
        "status": "available",
        "pricing": {
            "inputPer1kUsd": 0.0015,
            "outputPer1kUsd": 0.0025,
            "fixedSessionUsd": 0.003,
            "minimumRequestUsd": 0.004,
        },
        "latency": {"baseMs": 620, "per1kTokensMs": 130, "speedRank": 4},
        "privacy": {
            "tier": "enterprise_controlled",
            "score": 94,
            "sensitiveDataAllowed": True,
            "dataLeavesDevice": True,
            "requiresExplicitCloudValidation": False,
        },
        "policy": {"networkRequired": True, "billingRequired": True, "ownedBoundary": True},
    },
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or parsed < 0:
        return default
    return parsed


def _as_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_priority(value: str | None) -> str:
    key = _normalize(value).casefold().replace("-", "_").replace(" ", "_") or "balanced"
    return PRIORITY_ALIASES.get(key, "balanced")


def _normalized_sensitivity(level: str | None, text: str, constraints: list[str]) -> dict[str, Any]:
    normalized_level = _normalize(level).casefold().replace("-", "_").replace(" ", "_")
    if normalized_level in {"public", "low", "none", "normal"}:
        effective_level = "low"
    elif normalized_level in SENSITIVE_LEVELS:
        effective_level = normalized_level
    else:
        effective_level = "low"
    haystack = " ".join([text, *constraints]).casefold()
    signals = [signal for signal in SENSITIVE_SIGNALS if signal in haystack]
    if signals and effective_level == "low":
        effective_level = "confidential"
    sensitive = effective_level in SENSITIVE_LEVELS
    return {
        "level": effective_level,
        "sensitive": sensitive,
        "signals": signals[:8],
        "reason": "Signaux sensibles detectes." if signals else "Niveau explicite ou faible sensibilite.",
    }


def _token_plan(
    *,
    objective: str,
    expected_input_tokens: int | None,
    expected_output_tokens: int | None,
    message_count: int | None,
) -> dict[str, int]:
    input_tokens = _as_int(expected_input_tokens, 0, minimum = 0, maximum = 2_000_000)
    if input_tokens == 0:
        input_tokens = max(400, min(24_000, int(len(objective) / 3.6) + 900))
    output_tokens = _as_int(expected_output_tokens, 0, minimum = 0, maximum = 2_000_000)
    if output_tokens == 0:
        output_tokens = max(300, min(16_000, int(input_tokens * 0.38)))
    messages = _as_int(message_count, 1, minimum = 1, maximum = 10_000)
    return {
        "expectedInputTokens": input_tokens,
        "expectedOutputTokens": output_tokens,
        "estimatedTotalTokens": input_tokens + output_tokens,
        "messageCount": messages,
    }


def _hardware_latency_adjustment(hardware: dict[str, Any] | None) -> float:
    hw = _as_dict(hardware)
    gpu = _as_dict(hw.get("gpu"))
    memory = _as_dict(hw.get("memory"))
    devices = [item for item in gpu.get("devices", []) if isinstance(item, dict)]
    max_vram = max((_as_float(item.get("vramTotalGb")) for item in devices), default = 0.0)
    total_ram = _as_float(memory.get("totalGb"), 0.0)
    if bool(gpu.get("available")) and max_vram >= 16:
        return 0.42
    if bool(gpu.get("available")) and max_vram >= 8:
        return 0.62
    if total_ram >= 32:
        return 0.76
    if total_ram <= 12:
        return 1.18
    return 1.0


def _profile_record(profile: dict[str, Any], *, hardware: dict[str, Any] | None) -> dict[str, Any]:
    record = dict(profile)
    if record.get("executionTarget") == "local":
        latency = dict(record.get("latency") or {})
        adjustment = _hardware_latency_adjustment(hardware)
        latency["baseMs"] = round(_as_float(latency.get("baseMs"), 1800.0) * adjustment, 2)
        latency["per1kTokensMs"] = round(_as_float(latency.get("per1kTokensMs"), 420.0) * adjustment, 2)
        record["latency"] = latency
    return record


def build_provider_pricing_store(
    *,
    hardware: dict[str, Any] | None = None,
    provider_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profiles = [
        _profile_record(dict(item), hardware = hardware)
        for item in (provider_profiles if provider_profiles else DEFAULT_PROVIDER_PROFILES)
        if isinstance(item, dict)
    ]
    return {
        "pricingStoreVersion": COGNIX_PROVIDER_PRICING_STORE_VERSION,
        "mode": "dry_run",
        "services": ["ProviderPricingStore"],
        "providerCount": len(profiles),
        "profiles": profiles,
        "policies": {
            "providerCallsAllowed": False,
            "billingMutationAllowed": False,
            "pricingRefreshUsesNetwork": False,
            "frontendDirectProviderCallAllowed": False,
        },
        "sideEffects": {
            "networkCall": False,
            "providerCall": False,
            "billingMutation": False,
            "runtimeConfigWrite": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def _cost_estimate(profile: dict[str, Any], tokens: dict[str, int]) -> float:
    pricing = _as_dict(profile.get("pricing"))
    cost = (
        (tokens["expectedInputTokens"] / 1000.0) * _as_float(pricing.get("inputPer1kUsd"))
        + (tokens["expectedOutputTokens"] / 1000.0) * _as_float(pricing.get("outputPer1kUsd"))
        + _as_float(pricing.get("fixedSessionUsd"))
    )
    minimum = _as_float(pricing.get("minimumRequestUsd"))
    if cost > 0:
        cost = max(cost, minimum)
    return round(cost, 4)


def _latency_estimate(profile: dict[str, Any], tokens: dict[str, int]) -> int:
    latency = _as_dict(profile.get("latency"))
    token_units = max(1.0, tokens["estimatedTotalTokens"] / 1000.0)
    base = _as_float(latency.get("baseMs"), 1000.0)
    per_1k = _as_float(latency.get("per1kTokensMs"), 250.0)
    message_penalty = max(0, tokens["messageCount"] - 1) * 18
    return int(round(base + (per_1k * token_units) + message_penalty))


def _project_fit(profile: dict[str, Any], project_type: str | None, constraints: list[str]) -> int:
    target = str(profile.get("executionTarget") or "")
    project = _normalize(project_type).casefold()
    text = " ".join(constraints).casefold()
    if "local" in text and target == "local":
        return 100
    if project in {"business", "enterprise", "company", "university", "school"} and target == "enterprise_server":
        return 96
    if "personal" in project and target == "personal_server":
        return 92
    if target == "cloud_api":
        return 76
    if target == "local":
        return 72
    return 80


def _candidate_record(
    profile: dict[str, Any],
    *,
    tokens: dict[str, int],
    sensitivity: dict[str, Any],
    explicit_cloud_override: bool,
    budget_usd: float | None,
    project_type: str | None,
    constraints: list[str],
) -> dict[str, Any]:
    target = str(profile.get("executionTarget") or "unknown")
    pricing = _as_dict(profile.get("pricing"))
    privacy = _as_dict(profile.get("privacy"))
    policy = _as_dict(profile.get("policy"))
    estimated_cost = _cost_estimate(profile, tokens)
    estimated_latency = _latency_estimate(profile, tokens)
    cloud_blocked = (
        target == "cloud_api"
        and bool(sensitivity.get("sensitive"))
        and not explicit_cloud_override
        and bool(privacy.get("requiresExplicitCloudValidation"))
    )
    blocked_reasons: list[str] = []
    if cloud_blocked:
        blocked_reasons.append("sensitive_cloud_requires_explicit_validation")
    if budget_usd is not None and estimated_cost > budget_usd and bool(policy.get("billingRequired")):
        blocked_reasons.append("over_budget")
    status = "blocked" if blocked_reasons else "candidate"
    privacy_score = int(_as_float(privacy.get("score"), 60.0))
    if bool(sensitivity.get("sensitive")) and not bool(privacy.get("sensitiveDataAllowed")):
        privacy_score = min(privacy_score, 24)
    return {
        "providerId": str(profile.get("providerId") or target),
        "displayName": str(profile.get("displayName") or target),
        "executionTarget": target,
        "label": str(profile.get("label") or target),
        "status": status,
        "blockedReasons": blocked_reasons,
        "costEstimate": {
            "estimatedCostUsd": estimated_cost,
            "free": estimated_cost == 0.0,
            "billingRequired": bool(policy.get("billingRequired")),
            "inputPer1kUsd": _as_float(pricing.get("inputPer1kUsd")),
            "outputPer1kUsd": _as_float(pricing.get("outputPer1kUsd")),
        },
        "latencyEstimate": {
            "estimatedLatencyMs": estimated_latency,
            "speedRank": _as_int(_as_dict(profile.get("latency")).get("speedRank"), 3, minimum = 1, maximum = 5),
        },
        "privacyFit": {
            "score": privacy_score,
            "tier": str(privacy.get("tier") or "unknown"),
            "sensitiveDataAllowed": bool(privacy.get("sensitiveDataAllowed")),
            "dataLeavesDevice": bool(privacy.get("dataLeavesDevice")),
            "cloudBlockedBecauseSensitive": cloud_blocked,
        },
        "projectFit": _project_fit(profile, project_type, constraints),
    }


def _score_candidate(candidate: dict[str, Any], *, priority: str, max_cost: float, max_latency: int) -> float:
    cost = _as_float(_as_dict(candidate.get("costEstimate")).get("estimatedCostUsd"))
    latency = _as_float(_as_dict(candidate.get("latencyEstimate")).get("estimatedLatencyMs"))
    privacy = _as_float(_as_dict(candidate.get("privacyFit")).get("score"), 50.0)
    project_fit = _as_float(candidate.get("projectFit"), 80.0)
    cost_score = 100.0 if max_cost <= 0 else max(0.0, 100.0 - ((cost / max_cost) * 92.0))
    speed_score = 100.0 if max_latency <= 0 else max(0.0, 100.0 - ((latency / max_latency) * 82.0))
    weights = {
        "balanced": {"cost": 0.30, "speed": 0.30, "privacy": 0.30, "project": 0.10},
        "cost": {"cost": 0.58, "speed": 0.18, "privacy": 0.18, "project": 0.06},
        "speed": {"cost": 0.14, "speed": 0.58, "privacy": 0.20, "project": 0.08},
        "privacy": {"cost": 0.18, "speed": 0.12, "privacy": 0.62, "project": 0.08},
    }[priority]
    score = (
        cost_score * weights["cost"]
        + speed_score * weights["speed"]
        + privacy * weights["privacy"]
        + project_fit * weights["project"]
    )
    if candidate.get("status") == "blocked":
        score -= 300
    if priority == "speed" and candidate.get("executionTarget") == "cloud_api":
        score += 12
    if priority == "privacy" and candidate.get("executionTarget") in {"enterprise_server", "local"}:
        score += 8
    if priority == "privacy" and candidate.get("executionTarget") == "enterprise_server" and project_fit >= 90:
        score += 18
    return round(score, 2)


def build_cost_optimization_plan(
    *,
    objective: str,
    hardware: dict[str, Any] | None = None,
    project_type: str | None = None,
    project_id: str | None = None,
    priority: str | None = None,
    sensitivity_level: str | None = None,
    constraints: list[str] | None = None,
    expected_input_tokens: int | None = None,
    expected_output_tokens: int | None = None,
    message_count: int | None = None,
    budget_usd: float | None = None,
    allow_cloud_when_sensitive: bool = False,
    provider_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_priority = normalize_priority(priority)
    clean_objective = _normalize(objective)[:4000] or "CogniX task"
    clean_constraints = [_normalize(item)[:240] for item in constraints or [] if _normalize(item)]
    tokens = _token_plan(
        objective = clean_objective,
        expected_input_tokens = expected_input_tokens,
        expected_output_tokens = expected_output_tokens,
        message_count = message_count,
    )
    sensitivity = _normalized_sensitivity(sensitivity_level, clean_objective, clean_constraints)
    pricing_store = build_provider_pricing_store(hardware = hardware, provider_profiles = provider_profiles)
    budget = _as_float(budget_usd, -1.0)
    normalized_budget = budget if budget >= 0 else None
    candidates = [
        _candidate_record(
            profile,
            tokens = tokens,
            sensitivity = sensitivity,
            explicit_cloud_override = allow_cloud_when_sensitive,
            budget_usd = normalized_budget,
            project_type = project_type,
            constraints = clean_constraints,
        )
        for profile in pricing_store["profiles"]
    ]
    max_cost = max((_as_float(_as_dict(item.get("costEstimate")).get("estimatedCostUsd")) for item in candidates), default = 0.0)
    max_latency = max((int(_as_float(_as_dict(item.get("latencyEstimate")).get("estimatedLatencyMs"))) for item in candidates), default = 0)
    scored_candidates = [
        {
            **item,
            "decisionScore": _score_candidate(
                item,
                priority = normalized_priority,
                max_cost = max_cost,
                max_latency = max_latency,
            ),
        }
        for item in candidates
    ]
    viable = [item for item in scored_candidates if item["status"] != "blocked"]
    selected = max(viable or scored_candidates, key = lambda item: item["decisionScore"])
    cloud_blocked = any(
        _as_dict(item.get("privacyFit")).get("cloudBlockedBecauseSensitive")
        for item in scored_candidates
    )
    display_options = [
        {
            "providerId": item["providerId"],
            "label": item["label"],
            "estimatedCostUsd": item["costEstimate"]["estimatedCostUsd"],
            "estimatedLatencyMs": item["latencyEstimate"]["estimatedLatencyMs"],
            "status": item["status"],
        }
        for item in sorted(scored_candidates, key = lambda candidate: candidate["decisionScore"], reverse = True)
    ]
    decision = {
        "selectedProviderId": selected["providerId"],
        "selectedExecutionTarget": selected["executionTarget"],
        "providerLabel": selected["displayName"],
        "estimatedCostUsd": selected["costEstimate"]["estimatedCostUsd"],
        "estimatedLatencyMs": selected["latencyEstimate"]["estimatedLatencyMs"],
        "decisionScore": selected["decisionScore"],
        "reason": f"{selected['displayName']} choisi pour priorite {normalized_priority}.",
        "requiresExplicitUserAction": bool(selected["costEstimate"]["billingRequired"]) or cloud_blocked,
        "cloudBlockedBecauseSensitive": cloud_blocked,
    }
    return {
        "optimizerVersion": COGNIX_COST_OPTIMIZER_VERSION,
        "pricingStoreVersion": COGNIX_PROVIDER_PRICING_STORE_VERSION,
        "executionPlannerVersion": COGNIX_EXECUTION_PLANNER_VERSION,
        "privacyPolicyVersion": COGNIX_PRIVACY_POLICY_VERSION,
        "mode": "dry_run",
        "services": ["CostOptimizer", "ProviderPricingStore", "ExecutionPlanner"],
        "task": {
            "objectiveExcerpt": clean_objective[:240],
            "projectId": project_id,
            "projectType": project_type,
            **tokens,
        },
        "priority": normalized_priority,
        "budget": {
            "budgetUsd": normalized_budget,
            "hardLimitApplied": normalized_budget is not None,
        },
        "sensitivity": {
            **sensitivity,
            "allowCloudWhenSensitive": allow_cloud_when_sensitive,
            "cloudAllowed": not cloud_blocked,
        },
        "decision": decision,
        "candidates": sorted(scored_candidates, key = lambda candidate: candidate["decisionScore"], reverse = True),
        "displayOptions": display_options,
        "providerPricingStore": pricing_store,
        "policy": {
            "displayOnlyWhenUseful": True,
            "requiresExplicitCloudValidation": cloud_blocked,
            "cloudBlockedBecauseSensitive": cloud_blocked,
            "humanConfirmationRequiredBeforePaidCloud": True,
            "frontendDirectProviderCallAllowed": False,
            "sensitiveCloudDefaultAllowed": False,
        },
        "sideEffects": {
            "networkCall": False,
            "providerCall": False,
            "billingMutation": False,
            "modelLoad": False,
            "generation": False,
            "trainingJob": False,
            "cloudJob": False,
            "runtimeConfigWrite": False,
            "providerProfileWrite": False,
            "executionCostLogWrite": False,
        },
    }
