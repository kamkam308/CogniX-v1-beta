# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX intelligent onboarding planner.

The onboarding planner translates a user's goal, level, execution preference,
priorities, hardware, benchmark, and runtime recommendation into a simple
starter pack. It never downloads models, writes settings, starts workers, or
changes projects.
"""

from __future__ import annotations

from typing import Any


COGNIX_ONBOARDING_VERSION = "cognix_onboarding_v1"

PURPOSE_DOMAINS: dict[str, list[str]] = {
    "studies": ["education", "maths", "research"],
    "education": ["education", "research", "maths"],
    "development": ["code", "general"],
    "code": ["code", "general"],
    "math": ["maths", "general"],
    "mathematics": ["maths", "general"],
    "physics": ["physique", "maths", "general"],
    "business": ["business", "research", "general"],
    "research": ["research", "education", "general"],
    "enterprise": ["business", "research", "code"],
    "content": ["general", "business"],
}

DOMAIN_MODELS: dict[str, dict[str, str]] = {
    "general": {
        "id": "cognix-general-3b-q4",
        "label": "CogniX General 3B Q4",
        "role": "generalist",
    },
    "code": {
        "id": "cognix-code-4b-q4",
        "label": "CogniX Code 4B Q4",
        "role": "code_expert",
    },
    "maths": {
        "id": "cognix-maths-3b-q4",
        "label": "CogniX Maths 3B Q4",
        "role": "math_expert",
    },
    "physique": {
        "id": "cognix-physique-3b-q4",
        "label": "CogniX Physique 3B Q4",
        "role": "physics_expert",
    },
    "business": {
        "id": "cognix-business-3b-q4",
        "label": "CogniX Business 3B Q4",
        "role": "business_expert",
    },
    "research": {
        "id": "cognix-research-3b-q4",
        "label": "CogniX Research 3B Q4",
        "role": "research_expert",
    },
    "education": {
        "id": "cognix-education-3b-q4",
        "label": "CogniX Education 3B Q4",
        "role": "education_expert",
    },
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")


def _normalize_many(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = _normalize(value)
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _hardware_tier(hardware: dict[str, Any]) -> str:
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb")) or 0.0
    available_gb = _as_float(memory.get("availableGb")) or 0.0
    gpu = _as_dict(hardware.get("gpu"))
    devices = [
        item
        for item in gpu.get("devices", [])
        if isinstance(item, dict)
    ]
    max_vram = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices),
        default = 0.0,
    )
    if bool(gpu.get("available")) and (max_vram >= 16 or total_gb >= 32):
        return "powerful_local"
    if total_gb <= 12 or available_gb < 5:
        return "small_local"
    return "balanced_local"


def _canonical_purpose(purpose: str | None, project_type: str | None) -> str:
    candidate = _normalize(project_type) or _normalize(purpose)
    aliases = {
        "etudes": "studies",
        "study": "studies",
        "studies": "studies",
        "developpement": "development",
        "development": "development",
        "dev": "development",
        "maths": "math",
        "mathematiques": "math",
        "mathematics": "mathematics",
        "physique": "physics",
        "physics": "physics",
        "business": "business",
        "entreprise": "enterprise",
        "enterprise": "enterprise",
        "education": "education",
        "recherche": "research",
        "research": "research",
        "creation_de_contenu": "content",
        "content": "content",
        "code": "code",
    }
    return aliases.get(candidate, candidate or "studies")


def _domains_for_purpose(purpose: str) -> list[str]:
    domains = PURPOSE_DOMAINS.get(purpose)
    if domains:
        return domains
    return ["general"]


def _recommended_edition(
    *,
    purpose: str,
    execution_target: str,
    priorities: list[str],
) -> str:
    if execution_target in {"enterprise_server", "server_entreprise"} or purpose == "enterprise":
        return "enterprise"
    if purpose == "business":
        return "business"
    if purpose == "education":
        return "university"
    if purpose == "studies":
        return "university" if "classes" in priorities or "mode_examen" in priorities else "free_local"
    if purpose in {"development", "code"}:
        return "developer"
    return "free_local"


def _model_record(domain: str, *, required: bool, tier: str) -> dict[str, Any]:
    model = DOMAIN_MODELS.get(domain, DOMAIN_MODELS["general"])
    return {
        **model,
        "domain": domain,
        "required": required,
        "recommendedQuantization": "Q4" if tier == "small_local" else "Q4/Q5",
        "loadPolicy": "on_demand" if tier == "small_local" else "warm_project_model",
        "willDownload": False,
        "willLoad": False,
    }


def _recommended_models(domains: list[str], tier: str) -> list[dict[str, Any]]:
    ordered = ["general"]
    for domain in domains:
        if domain not in ordered:
            ordered.append(domain)
    max_models = 2 if tier == "small_local" else 4 if tier == "balanced_local" else 6
    selected = ordered[:max_models]
    return [
        _model_record(domain, required = index == 0 or domain in domains[:1], tier = tier)
        for index, domain in enumerate(selected)
    ]


def _blocked_models(tier: str) -> list[dict[str, Any]]:
    blocked = [
        {
            "id": "glm-700b",
            "label": "GLM 700B",
            "reason": "Modele impossible en local standard; reserver a un cluster enterprise.",
        }
    ]
    if tier == "small_local":
        blocked.extend(
            [
                {
                    "id": "qwen-14b-q4",
                    "label": "Qwen 14B Q4",
                    "reason": "Trop lourd pour un petit profil local sans pression RAM.",
                },
                {
                    "id": "local-32b-unquantized",
                    "label": "32B non quantifie",
                    "reason": "RAM locale insuffisante: preferer 3B/4B quantifie.",
                },
            ]
        )
    return blocked


def _module_ids(purpose: str, priorities: list[str]) -> list[str]:
    modules = ["cognix-local-core", "cognix-projects", "cognix-onboarding"]
    if purpose in {"studies", "education", "research", "business", "enterprise"}:
        modules.append("cognix-rag")
    if purpose in {"development", "code"}:
        modules.append("cognix-codex-secure-agent")
    if purpose in {"development", "code", "enterprise"}:
        modules.append("cognix-fine-tuning")
    if purpose in {"business", "enterprise"} or "connecteurs" in priorities:
        modules.append("cognix-integrations")
    if purpose in {"business", "enterprise"}:
        modules.append("cognix-enterprise-foundation")
    return modules


def _first_steps(
    *,
    purpose: str,
    execution_target: str,
    recommendation: dict[str, Any],
    latest_benchmark_run: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if not isinstance(latest_benchmark_run, dict):
        steps.append(
            {
                "id": "run_local_benchmark",
                "label": "Calibrer la machine",
                "status": "recommended",
                "reason": "Le benchmark permet d'ajuster modeles, cache et optimisations.",
                "willRun": False,
            }
        )
    readiness = str(recommendation.get("readiness") or "unknown")
    if readiness in {"setup_required", "service_unreachable", "model_missing"}:
        steps.append(
            {
                "id": "configure_local_runtime",
                "label": "Configurer le runtime local",
                "status": "required",
                "reason": str(recommendation.get("reason") or "Provider ou modele local pas encore pret."),
                "willConfigure": False,
            }
        )
    if purpose in {"studies", "education", "research", "business", "enterprise"}:
        steps.append(
            {
                "id": "prepare_document_memory",
                "label": "Preparer la memoire documentaire",
                "status": "recommended",
                "reason": "RAG avant fine-tuning pour les cours, PDF et documents internes.",
                "willIndex": False,
            }
        )
    if purpose in {"development", "code"}:
        steps.append(
            {
                "id": "create_code_project",
                "label": "Creer un projet Code",
                "status": "recommended",
                "reason": "Un projet specialise charge CogniX Code par defaut et garde le contexte technique.",
                "willCreateProject": False,
            }
        )
    if execution_target in {"cloud", "enterprise_server", "server_entreprise"}:
        steps.append(
            {
                "id": "review_cloud_policy",
                "label": "Verifier la politique cloud",
                "status": "required",
                "reason": "Les providers externes exigent secrets serveur, permissions et audit.",
                "willReadSecrets": False,
            }
        )
    return steps


def build_onboarding_plan(
    *,
    username: str,
    hardware: dict[str, Any],
    recommendation: dict[str, Any],
    purpose: str | None = None,
    level: str | None = None,
    execution_target: str | None = None,
    priorities: list[str] | None = None,
    project_type: str | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_priorities = _normalize_many(priorities)
    normalized_purpose = _canonical_purpose(purpose, project_type)
    normalized_level = _normalize(level) or "intermediate"
    normalized_execution = _normalize(execution_target) or "local"
    domains = _domains_for_purpose(normalized_purpose)
    tier = _hardware_tier(hardware)
    edition = _recommended_edition(
        purpose = normalized_purpose,
        execution_target = normalized_execution,
        priorities = normalized_priorities,
    )
    recommended_models = _recommended_models(domains, tier)
    first_steps = _first_steps(
        purpose = normalized_purpose,
        execution_target = normalized_execution,
        recommendation = recommendation,
        latest_benchmark_run = latest_benchmark_run,
    )

    warnings: list[str] = []
    if tier == "small_local":
        warnings.append("Petit profil local: garder un seul modele resident et preferer Q4.")
    if "confidentialite" in normalized_priorities or "privacy" in normalized_priorities or "hors_ligne" in normalized_priorities:
        warnings.append("Priorite confidentialite: privilegier local/offline et eviter providers externes par defaut.")
    for item in recommendation.get("warnings") or []:
        if isinstance(item, str) and item:
            warnings.append(item)

    return {
        "onboardingVersion": COGNIX_ONBOARDING_VERSION,
        "mode": "dry_run",
        "username": username,
        "profile": {
            "purpose": normalized_purpose,
            "level": normalized_level,
            "executionTarget": normalized_execution,
            "priorities": normalized_priorities,
            "primaryDomains": domains,
        },
        "hardwareSummary": {
            "tier": tier,
            "deviceBackend": hardware.get("deviceBackend"),
            "cpuCount": hardware.get("cpuCount"),
            "memory": _as_dict(hardware.get("memory")),
            "gpu": _as_dict(hardware.get("gpu")),
        },
        "recommendedEdition": edition,
        "recommendedPack": {
            "id": f"{edition}-{tier}-{normalized_purpose}",
            "label": "Pack CogniX recommande",
            "models": recommended_models,
            "blockedModels": _blocked_models(tier),
            "modules": _module_ids(normalized_purpose, normalized_priorities),
            "defaultProjectType": domains[0] if domains else "general",
            "cachePolicy": "single_resident_model" if tier == "small_local" else "project_expert_warm",
            "runtime": {
                "providerId": recommendation.get("providerId"),
                "providerType": recommendation.get("providerType"),
                "providerName": recommendation.get("providerName"),
                "modelId": recommendation.get("modelId"),
                "readiness": recommendation.get("readiness"),
                "willConfigure": False,
            },
        },
        "firstSteps": first_steps,
        "benchmark": {
            "available": isinstance(latest_benchmark_run, dict),
            "latestRunId": _as_dict(latest_benchmark_run).get("id"),
            "recommendedBeforeExecution": not isinstance(latest_benchmark_run, dict),
        },
        "warnings": warnings,
        "reason": "Onboarding CogniX prepare: pack, modules, runtime et prochaines etapes sans mutation.",
        "sideEffects": {
            "profileWrite": False,
            "settingsWrite": False,
            "projectCreate": False,
            "modelDownload": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "benchmarkRun": False,
            "ragIndexing": False,
            "toolExecution": False,
        },
    }
