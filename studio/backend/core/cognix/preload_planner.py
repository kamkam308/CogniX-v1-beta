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

DOMAIN_MODEL_ROLES = {
    "general": {"role": "generalist", "fallbackLabel": "CogniX General 3B"},
    "maths": {"role": "math_expert", "fallbackLabel": "CogniX Maths 3B"},
    "physique": {"role": "physics_expert", "fallbackLabel": "CogniX Physique 3B"},
    "code": {"role": "code_expert", "fallbackLabel": "CogniX Code 4B"},
    "business": {"role": "business_expert", "fallbackLabel": "CogniX Business 3B"},
    "research": {"role": "research_expert", "fallbackLabel": "CogniX Research 3B"},
    "education": {"role": "education_expert", "fallbackLabel": "CogniX Education 3B"},
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
    target["priority"] = priority
    target["state"] = action["type"]
    target["reason"] = action["reason"]

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
            }
        ],
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
            "cacheMutation": False,
        },
    }
