# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI simulation planning.

This module prepares synthetic load and workflow simulation reports. It does
not start agents, hit servers, run load tests, enqueue jobs, or call models.
"""

from __future__ import annotations

import math
from typing import Any


COGNIX_SIMULATION_ENGINE_VERSION = "cognix_simulation_engine_v1"
COGNIX_SYNTHETIC_USER_GENERATOR_VERSION = "cognix_synthetic_user_generator_v1"
COGNIX_LOAD_SCENARIO_RUNNER_VERSION = "cognix_load_scenario_runner_v1"
COGNIX_SIMULATION_REPORT_GENERATOR_VERSION = "cognix_simulation_report_generator_v1"

SIMULATION_TYPES: tuple[str, ...] = ("business", "user", "server", "database", "workflow")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _clamp_int(value: int | None, *, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_simulation_type(value: str | None) -> str:
    kind = _normalize(value).lower().replace(" ", "_") or "business"
    aliases = {
        "enterprise": "business",
        "company": "business",
        "organisation": "business",
        "organization": "business",
        "utilisateur": "user",
        "serveur": "server",
        "db": "database",
        "base_de_donnees": "database",
        "base_de_donnees_sql": "database",
        "workflow_test": "workflow",
    }
    kind = aliases.get(kind, kind)
    return kind if kind in SIMULATION_TYPES else "business"


def build_simulation_blueprint() -> dict[str, Any]:
    return {
        "simulationEngineVersion": COGNIX_SIMULATION_ENGINE_VERSION,
        "syntheticUserGeneratorVersion": COGNIX_SYNTHETIC_USER_GENERATOR_VERSION,
        "loadScenarioRunnerVersion": COGNIX_LOAD_SCENARIO_RUNNER_VERSION,
        "reportGeneratorVersion": COGNIX_SIMULATION_REPORT_GENERATOR_VERSION,
        "mode": "ai_simulation_contract",
        "services": ["SimulationEngine", "SyntheticUserGenerator", "LoadScenarioRunner", "ReportGenerator"],
        "simulationTypes": list(SIMULATION_TYPES),
        "inputContract": {
            "simulationType": True,
            "userCount": True,
            "scenario": True,
            "durationMinutes": True,
            "constraints": True,
        },
        "reportContract": {
            "risks": True,
            "estimatedLatency": True,
            "estimatedCosts": True,
            "bottlenecks": True,
            "dashboardSimple": True,
        },
        "queuePolicy": {
            "queueRequiredAboveUsers": 50,
            "queueRequiredAboveMinutes": 60,
            "directLoadTestAllowedFromPlanner": False,
            "syntheticAgentsRunInPlanner": False,
        },
        "sideEffects": {
            "simulationRunWrite": False,
            "metricsWrite": False,
            "queueEnqueue": False,
            "syntheticAgentRun": False,
            "loadExecution": False,
            "reportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


def _severity(value: float, *, medium: float, high: float) -> str:
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def _type_multiplier(simulation_type: str) -> float:
    return {
        "business": 1.2,
        "user": 0.45,
        "server": 1.0,
        "database": 0.9,
        "workflow": 0.7,
    }.get(simulation_type, 1.0)


def _project_multiplier(project_type: str | None) -> float:
    value = _normalize(project_type).lower()
    if value in {"school", "education", "university", "ecole"}:
        return 0.85
    if value in {"business", "enterprise", "company"}:
        return 1.3
    return 1.0


def _constraint_flags(constraints: list[str]) -> dict[str, bool]:
    text = " ".join(constraints).lower()
    return {
        "localOnly": any(token in text for token in ("local", "offline", "on-prem", "on_prem")),
        "lowCost": any(token in text for token in ("budget", "cheap", "cost", "gratuit", "econom")),
        "privacy": any(token in text for token in ("privacy", "confidential", "private", "rgpd", "secret")),
        "databaseHeavy": any(token in text for token in ("database", "sqlite", "postgres", "sql", "db")),
    }


def _metric(metric_id: str, label: str, value: float, unit: str, severity: str) -> dict[str, Any]:
    rounded = round(value, 4) if unit == "usd" else round(value, 2)
    return {
        "id": metric_id,
        "label": label,
        "value": rounded,
        "unit": unit,
        "severity": severity,
    }


def build_simulation_plan(
    *,
    username: str,
    simulation_type: str | None,
    user_count: int,
    scenario: str,
    duration_minutes: int,
    constraints: list[str] | None = None,
    project_id: str | None = None,
    project_type: str | None = None,
) -> dict[str, Any]:
    kind = normalize_simulation_type(simulation_type)
    users = _clamp_int(user_count, minimum = 1, maximum = 100000, default = 10)
    duration = _clamp_int(duration_minutes, minimum = 1, maximum = 10080, default = 15)
    clean_constraints = [_normalize(item)[:240] for item in constraints or [] if _normalize(item)]
    scenario_text = _normalize(scenario)[:4000] or "Simulation CogniX"
    multiplier = _type_multiplier(kind) * _project_multiplier(project_type)
    flags = _constraint_flags(clean_constraints + [scenario_text])

    concurrent_users = max(1, min(users, int(math.ceil(users * 0.18))))
    requests_per_minute = max(1.0, round((users * multiplier) / max(1.0, min(duration, 60) / 10.0), 2))
    estimated_latency_ms = 95 + (math.sqrt(users) * 42 * multiplier) + (concurrent_users * 5.5)
    cpu_pressure = min(100.0, 14 + (concurrent_users * 0.92 * multiplier) + (requests_per_minute * 0.08))
    memory_pressure = min(100.0, 10 + (users * 0.11 * multiplier) + (duration * 0.035))
    database_heavy = kind == "database" or flags["databaseHeavy"]
    database_pressure = min(
        100.0,
        8
        + (users * (0.45 if database_heavy else 0.08))
        + (requests_per_minute * (0.15 if database_heavy else 0.05)),
    )
    cost_estimate_usd = 0.0 if flags["localOnly"] else ((requests_per_minute * duration) / 1000.0) * 0.0025
    if flags["lowCost"]:
        cost_estimate_usd *= 0.65

    metrics = [
        _metric("estimated_latency_ms", "Latence estimee", estimated_latency_ms, "ms", _severity(estimated_latency_ms, medium = 650, high = 1200)),
        _metric("requests_per_minute", "Requetes estimees par minute", requests_per_minute, "rpm", _severity(requests_per_minute, medium = 120, high = 500)),
        _metric("cpu_pressure", "Pression CPU estimee", cpu_pressure, "percent", _severity(cpu_pressure, medium = 60, high = 82)),
        _metric("memory_pressure", "Pression memoire estimee", memory_pressure, "percent", _severity(memory_pressure, medium = 62, high = 84)),
        _metric("database_pressure", "Pression base de donnees estimee", database_pressure, "percent", _severity(database_pressure, medium = 58, high = 78)),
        _metric("cost_estimate_usd", "Cout estime", cost_estimate_usd, "usd", _severity(cost_estimate_usd, medium = 0.1, high = 1.0)),
    ]

    bottlenecks: list[dict[str, Any]] = []
    if cpu_pressure >= 60:
        bottlenecks.append({"id": "cpu_pressure", "label": "CPU", "severity": _severity(cpu_pressure, medium = 60, high = 82)})
    if memory_pressure >= 62:
        bottlenecks.append({"id": "memory_pressure", "label": "Memoire", "severity": _severity(memory_pressure, medium = 62, high = 84)})
    if database_pressure >= 58:
        bottlenecks.append({"id": "database_pressure", "label": "Base de donnees", "severity": _severity(database_pressure, medium = 58, high = 78)})
    if estimated_latency_ms >= 650:
        bottlenecks.append({"id": "latency", "label": "Latence", "severity": _severity(estimated_latency_ms, medium = 650, high = 1200)})

    risks: list[dict[str, Any]] = []
    if users >= 100:
        risks.append({"id": "high_concurrency", "severity": "high", "message": "Charge multi-utilisateur elevee; passer par une queue et limiter la concurrence."})
    elif users >= 50:
        risks.append({"id": "medium_concurrency", "severity": "medium", "message": "Charge notable; valider la concurrence avant execution."})
    if flags["privacy"]:
        risks.append({"id": "privacy_constraints", "severity": "medium", "message": "Scenario sensible; eviter l'export de donnees brutes dans le rapport."})
    if database_pressure >= 58:
        risks.append({"id": "database_hotspot", "severity": _severity(database_pressure, medium = 58, high = 78), "message": "La base de donnees peut devenir le goulot principal."})
    if not risks:
        risks.append({"id": "low_risk", "severity": "low", "message": "Aucun risque critique estime pour ce scenario."})

    recommendations = [
        "Limiter les tests reels a une queue controlee.",
        "Mesurer un benchmark court avant toute simulation longue.",
        "Conserver les rapports sous forme agregee, sans secrets ni donnees brutes.",
    ]
    if any(item["id"] == "database_pressure" for item in bottlenecks):
        recommendations.append("Ajouter indexes, pagination et cache avant un test de charge base de donnees.")
    if flags["localOnly"]:
        recommendations.append("Rester local-only: cout cloud estime a zero, mais surveiller CPU et RAM.")

    queue_required = users > 50 or duration > 60
    synthetic_agent_count = min(users, 25)
    return {
        "simulationEngineVersion": COGNIX_SIMULATION_ENGINE_VERSION,
        "syntheticUserGeneratorVersion": COGNIX_SYNTHETIC_USER_GENERATOR_VERSION,
        "loadScenarioRunnerVersion": COGNIX_LOAD_SCENARIO_RUNNER_VERSION,
        "reportGeneratorVersion": COGNIX_SIMULATION_REPORT_GENERATOR_VERSION,
        "mode": "simulation_plan",
        "username": username,
        "projectId": project_id,
        "projectType": project_type,
        "scenario": {
            "simulationType": kind,
            "userCount": users,
            "durationMinutes": duration,
            "description": scenario_text,
            "constraints": clean_constraints,
        },
        "syntheticAgents": {
            "plannedCount": synthetic_agent_count,
            "profiles": ["new_user", "regular_user", "power_user", "admin_operator"][: min(4, max(1, synthetic_agent_count))],
            "willRunNow": False,
        },
        "queuePlan": {
            "queueRequired": queue_required,
            "queueId": "local_probe",
            "jobType": "simulation_run",
            "willEnqueueNow": False,
            "reason": "large_simulation" if queue_required else "planner_only",
        },
        "metrics": metrics,
        "report": {
            "title": f"Simulation {kind} - {users} utilisateurs",
            "dashboardSimple": True,
            "risks": risks,
            "bottlenecks": bottlenecks,
            "recommendations": recommendations,
            "summary": {
                "estimatedLatencyMs": round(estimated_latency_ms, 2),
                "estimatedCostUsd": round(cost_estimate_usd, 4),
                "highestMetricSeverity": "high" if any(item["severity"] == "high" for item in metrics) else ("medium" if any(item["severity"] == "medium" for item in metrics) else "low"),
                "queueRequired": queue_required,
            },
        },
        "sideEffects": build_simulation_blueprint()["sideEffects"],
    }
