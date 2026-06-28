# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX research watch and innovation gatekeeping.

CogniX can learn from modern AI research, but new techniques must pass through
source, compatibility, security, benchmark, and rollback gates before they can
become executable product behavior. This planner is deliberately dry-run only.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


COGNIX_RESEARCH_WATCH_VERSION = "cognix_research_watch_v1"


RESEARCH_SOURCES: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "priority": "high",
        "sourceTypes": ["official_blog", "paper", "reference_repo", "model_card"],
        "watchedFor": ["model_architecture", "inference_optimization", "distillation"],
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "priority": "high",
        "sourceTypes": ["official_blog", "paper", "safety_report"],
        "watchedFor": ["security_method", "evaluation_method", "model_behavior"],
    },
    {
        "id": "google-deepmind",
        "label": "Google / Google DeepMind",
        "priority": "high",
        "sourceTypes": ["paper", "official_blog", "reference_repo"],
        "watchedFor": ["model_architecture", "evaluation_method", "inference_optimization"],
    },
    {
        "id": "sakana-ai",
        "label": "Sakana AI",
        "priority": "high",
        "sourceTypes": ["paper", "official_blog", "reference_repo"],
        "watchedFor": ["agentic_research", "model_composition", "evaluation_method"],
    },
    {
        "id": "zhipu-glm",
        "label": "Zhipu AI / GLM",
        "priority": "high",
        "sourceTypes": ["paper", "model_card", "reference_repo"],
        "watchedFor": ["model_architecture", "local_model_pack", "multilingual_reasoning"],
    },
    {
        "id": "meta-ai",
        "label": "Meta AI",
        "priority": "high",
        "sourceTypes": ["paper", "model_card", "reference_repo"],
        "watchedFor": ["model_architecture", "fine_tuning_method", "evaluation_method"],
    },
    {
        "id": "alibaba-qwen",
        "label": "Alibaba / Qwen",
        "priority": "high",
        "sourceTypes": ["paper", "model_card", "reference_repo"],
        "watchedFor": ["local_model_pack", "model_architecture", "multimodal_support"],
    },
    {
        "id": "mistral-ai",
        "label": "Mistral AI",
        "priority": "high",
        "sourceTypes": ["paper", "official_blog", "model_card"],
        "watchedFor": ["local_model_pack", "model_architecture", "inference_optimization"],
    },
    {
        "id": "nvidia",
        "label": "NVIDIA",
        "priority": "high",
        "sourceTypes": ["official_docs", "reference_repo", "benchmark_report"],
        "watchedFor": ["runtime_adapter", "tensor_rt_llm", "gpu_scheduler"],
    },
    {
        "id": "microsoft-research",
        "label": "Microsoft Research",
        "priority": "medium",
        "sourceTypes": ["paper", "reference_repo", "official_blog"],
        "watchedFor": ["evaluation_method", "agent_workflow", "security_method"],
    },
    {
        "id": "hugging-face",
        "label": "Hugging Face",
        "priority": "medium",
        "sourceTypes": ["model_card", "dataset_card", "paper_page", "reference_repo"],
        "watchedFor": ["model_pack", "dataset", "evaluation_method", "fine_tuning_method"],
    },
]


TECHNIQUE_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "inference_optimization",
        "label": "Optimisation d'inference",
        "signals": ["speculative", "decoding", "kv-cache", "prompt cache", "latency", "latence", "batching", "warmup"],
        "techniques": ["speculative_decoding", "kv_cache_optimization", "prompt_caching", "model_warmup"],
        "targetModules": ["cognix-runtime-adapter", "cognix-optimization-planner", "cognix-worker-queue"],
        "requiredProof": ["before_after_latency", "runtime_support", "fallback_path"],
    },
    {
        "id": "model_architecture",
        "label": "Architecture de modele",
        "signals": ["moe", "mixture", "architecture", "expert", "deepseek", "transformer"],
        "targetModules": ["cognix-model-lifecycle", "cognix-runtime-adapter"],
        "requiredProof": ["model_metadata_support", "engine_support", "hardware_fit"],
    },
    {
        "id": "fine_tuning_method",
        "label": "Methode de fine-tuning",
        "signals": ["lora", "qlora", "distillation", "adapter", "fine-tuning", "training"],
        "targetModules": ["cognix-fine-tuning", "cognix-worker-queue"],
        "requiredProof": ["dataset_validation", "training_budget", "quality_eval"],
    },
    {
        "id": "rag_method",
        "label": "Methode RAG",
        "signals": ["rag", "retrieval", "chunk", "citation", "rerank", "embedding"],
        "targetModules": ["cognix-rag", "cognix-memory-manager", "cognix-context-manager"],
        "requiredProof": ["retrieval_eval", "citation_accuracy", "privacy_review"],
    },
    {
        "id": "compression_method",
        "label": "Compression",
        "signals": ["compression", "quantization", "quantisation", "q4", "q5", "q8", "cache eviction", "summarization"],
        "targetModules": ["cognix-optimization-planner", "cognix-memory-manager"],
        "requiredProof": ["quality_regression_check", "memory_delta", "rollback_path"],
    },
    {
        "id": "security_method",
        "label": "Methode de securite",
        "signals": ["security", "safety", "guardrail", "jailbreak", "permission", "audit", "securite"],
        "targetModules": ["cognix-security-policy", "cognix-governance-manager", "cognix-tool-registry"],
        "requiredProof": ["threat_model", "abuse_cases", "audit_log_policy"],
    },
    {
        "id": "evaluation_method",
        "label": "Methode d'evaluation",
        "signals": ["eval", "benchmark", "score", "test", "judge", "measurement", "mesure"],
        "targetModules": ["cognix-benchmark", "cognix-orchestrator"],
        "requiredProof": ["metric_definition", "baseline", "repeatability"],
    },
]


MEASURABLE_GAIN_TYPES = ["speed", "memory", "cost", "quality", "security", "stability"]


INTEGRATION_GATES: list[dict[str, Any]] = [
    {
        "id": "official_source_review",
        "label": "Source officielle ou reference",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "technique_summary",
        "label": "Resume technique",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "category_classification",
        "label": "Classification CogniX",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "compatibility_review",
        "label": "Compatibilite modele/runtime/materiel",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "security_review",
        "label": "Analyse securite",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "benchmark_before_after",
        "label": "Benchmark avant/apres",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "fallback_plan",
        "label": "Fallback propre",
        "required": True,
        "blocksWithoutEvidence": True,
    },
    {
        "id": "risk_documentation",
        "label": "Risques, limites et prerequis",
        "required": True,
        "blocksWithoutEvidence": True,
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize_text(value).casefold()).strip("_")


def _excerpt(value: Any, limit: int = 500) -> str:
    return _normalize_text(value)[:limit]


def _source_for(source_name: str | None) -> dict[str, Any]:
    key = _normalize_key(source_name)
    if not key:
        return {
            "id": "unknown",
            "label": "Source non precisee",
            "recognized": False,
            "trusted": False,
            "priority": "unknown",
            "sourceTypes": [],
            "watchedFor": [],
        }
    for source in RESEARCH_SOURCES:
        aliases = {
            _normalize_key(source["id"]),
            _normalize_key(source["label"]),
            _normalize_key(source["label"].split("/")[0]),
        }
        if key in aliases or any(part and part in key for part in aliases):
            record = deepcopy(source)
            record["recognized"] = True
            record["trusted"] = True
            return record
    evidence_words = {"paper", "official", "reference_repo", "repo", "github", "arxiv", "model_card", "docs"}
    return {
        "id": key[:80],
        "label": _normalize_text(source_name),
        "recognized": False,
        "trusted": any(word in key for word in evidence_words),
        "priority": "needs_review",
        "sourceTypes": [],
        "watchedFor": [],
    }


def _category_for(category: str | None, text: str) -> dict[str, Any]:
    requested = _normalize_key(category)
    for item in TECHNIQUE_CATEGORIES:
        if requested == _normalize_key(item["id"]) or requested == _normalize_key(item["label"]):
            return deepcopy(item)

    lowered = text.casefold()
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in TECHNIQUE_CATEGORIES:
        score = sum(1 for signal in item["signals"] if signal.casefold() in lowered)
        scored.append((score, item))
    score, selected = max(scored, key = lambda pair: pair[0])
    if score <= 0:
        selected = next(item for item in TECHNIQUE_CATEGORIES if item["id"] == "evaluation_method")
    return deepcopy(selected)


def _hardware_tier(hardware: dict[str, Any] | None) -> str:
    hardware = _as_dict(hardware)
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb")) or 0.0
    available_gb = _as_float(memory.get("availableGb")) or 0.0
    gpu = _as_dict(hardware.get("gpu"))
    devices = [item for item in _as_list(gpu.get("devices")) if isinstance(item, dict)]
    max_vram = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices),
        default = 0.0,
    )
    if bool(gpu.get("available")) and (max_vram >= 16 or total_gb >= 32):
        return "powerful_local"
    if total_gb <= 12 or available_gb < 5:
        return "small_local"
    return "balanced_local"


def _benchmark_available(latest_benchmark_run: dict[str, Any] | None) -> bool:
    if not isinstance(latest_benchmark_run, dict):
        return False
    return bool(latest_benchmark_run.get("benchmark") or latest_benchmark_run.get("benchmark_json") or latest_benchmark_run.get("id"))


def _measurable_gains(text: str) -> list[str]:
    lowered = text.casefold()
    aliases = {
        "speed": ["speed", "latency", "latence", "vitesse", "throughput"],
        "memory": ["memory", "memoire", "ram", "vram", "cache"],
        "cost": ["cost", "cout", "coût", "prix"],
        "quality": ["quality", "qualite", "qualité", "accuracy", "precision"],
        "security": ["security", "securite", "sécurité", "safety", "guardrail"],
        "stability": ["stability", "stabilite", "stabilité", "reliability"],
    }
    gains = [
        gain_id
        for gain_id, words in aliases.items()
        if any(word in lowered for word in words)
    ]
    return gains


def _blocked_claims(text: str) -> list[dict[str, Any]]:
    lowered = text.casefold()
    blocked: list[dict[str, Any]] = []
    if "moe" in lowered and any(phrase in lowered for phrase in ("any model", "n'importe quel", "magique", "magically", "ajouter a tous", "ajouter à tous")):
        blocked.append(
            {
                "id": "architecture_magic_moe",
                "reason": "MoE est lie a l'architecture du modele; CogniX doit detecter le support au lieu de le promettre partout.",
            }
        )
    if "deepseek" in lowered and "moe" in lowered and "support" not in lowered and "compatible" not in lowered:
        blocked.append(
            {
                "id": "deepseek_moe_requires_model_support",
                "reason": "DeepSeek-style MoE exige un modele et un runtime compatibles.",
            }
        )
    if any(phrase in lowered for phrase in ("sans benchmark", "no benchmark", "pas besoin de benchmark")):
        blocked.append(
            {
                "id": "benchmark_bypass",
                "reason": "Les optimisations CogniX exigent une mesure avant/apres.",
            }
        )
    return blocked


def _runtime_type(recommendation: dict[str, Any] | None) -> str:
    recommendation = _as_dict(recommendation)
    return str(
        recommendation.get("providerType")
        or recommendation.get("runtimeType")
        or recommendation.get("provider_type")
        or "unknown"
    )


def _compatibility_status(
    *,
    category: dict[str, Any],
    technique_name: str | None,
    target_module: str | None,
    recommendation: dict[str, Any] | None,
    hardware: dict[str, Any] | None,
) -> dict[str, Any]:
    text = f"{technique_name or ''} {target_module or ''}".casefold()
    runtime_type = _runtime_type(recommendation)
    hardware_tier = _hardware_tier(hardware)
    category_id = str(category.get("id") or "unknown")
    target_modules = _as_list(category.get("targetModules"))
    selected_module = target_module or (str(target_modules[0]) if target_modules else "cognix-core")

    if category_id == "model_architecture" and "moe" in text:
        return {
            "status": "architecture_bound",
            "directIntegrationAllowed": False,
            "targetModule": selected_module,
            "runtimeType": runtime_type,
            "hardwareTier": hardware_tier,
            "reason": "Technique dependante du modele: selectionner seulement un modele MoE compatible et un runtime adapte.",
        }
    if "speculative" in text and runtime_type not in {"llama.cpp", "llama-cpp", "vllm", "unknown"}:
        return {
            "status": "runtime_support_unknown",
            "directIntegrationAllowed": False,
            "targetModule": selected_module,
            "runtimeType": runtime_type,
            "hardwareTier": hardware_tier,
            "reason": "Speculative decoding necessite un runtime declare compatible et un petit modele draft mesure.",
        }
    if category_id == "inference_optimization" and hardware_tier == "small_local":
        return {
            "status": "candidate_memory_guarded",
            "directIntegrationAllowed": True,
            "targetModule": selected_module,
            "runtimeType": runtime_type,
            "hardwareTier": hardware_tier,
            "reason": "Candidat possible, mais avec garde memoire stricte sur petite machine.",
        }
    return {
        "status": "candidate",
        "directIntegrationAllowed": True,
        "targetModule": selected_module,
        "runtimeType": runtime_type,
        "hardwareTier": hardware_tier,
        "reason": "Technique compatible en principe, sous reserve de preuve officielle et benchmark interne.",
    }


def _gate(gate_id: str, status: str, reason: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    template = next((item for item in INTEGRATION_GATES if item["id"] == gate_id), {"id": gate_id, "label": gate_id, "required": True})
    return {
        "id": gate_id,
        "label": template.get("label"),
        "required": bool(template.get("required")),
        "status": status,
        "reason": reason,
        "evidence": evidence or {},
    }


def build_research_watch_registry() -> dict[str, Any]:
    return {
        "researchWatchVersion": COGNIX_RESEARCH_WATCH_VERSION,
        "mode": "declarative_dry_run",
        "sources": deepcopy(RESEARCH_SOURCES),
        "categories": deepcopy(TECHNIQUE_CATEGORIES),
        "integrationGates": deepcopy(INTEGRATION_GATES),
        "measurableGainTypes": list(MEASURABLE_GAIN_TYPES),
        "policies": {
            "officialSourceRequired": True,
            "referenceImplementationPreferred": True,
            "benchmarkBeforeAfterRequired": True,
            "securityReviewRequired": True,
            "hardwarePrerequisitesMustBeDocumented": True,
            "fallbackRequired": True,
            "hypeOnlyAdoptionAllowed": False,
            "architectureClaimsMustMatchModelMetadata": True,
            "experimentalModulesNeedIsolation": True,
        },
        "summary": {
            "sourceCount": len(RESEARCH_SOURCES),
            "categoryCount": len(TECHNIQUE_CATEGORIES),
            "gateCount": len(INTEGRATION_GATES),
            "watchedLabs": [source["label"] for source in RESEARCH_SOURCES],
            "frontendDirectIntegrationAllowed": False,
        },
        "sideEffects": {
            "networkResearch": False,
            "modelDownload": False,
            "modelLoad": False,
            "benchmarkRun": False,
            "codeModification": False,
            "settingsWrite": False,
            "deployment": False,
        },
    }


def build_research_integration_plan(
    *,
    objective: str,
    technique_name: str | None = None,
    source_name: str | None = None,
    category: str | None = None,
    claimed_benefit: str | None = None,
    target_module: str | None = None,
    risk_tolerance: str | None = None,
    hardware: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combined_text = _normalize_text(" ".join([
        objective or "",
        technique_name or "",
        source_name or "",
        category or "",
        claimed_benefit or "",
        target_module or "",
    ]))
    source = _source_for(source_name)
    selected_category = _category_for(category, combined_text)
    gains = _measurable_gains(f"{objective or ''} {claimed_benefit or ''} {technique_name or ''}")
    blocked_claims = _blocked_claims(combined_text)
    compatibility = _compatibility_status(
        category = selected_category,
        technique_name = technique_name,
        target_module = target_module,
        recommendation = recommendation,
        hardware = hardware,
    )
    benchmark_ready = _benchmark_available(latest_benchmark_run)
    source_ready = bool(source.get("trusted"))
    summary_ready = bool(_normalize_text(objective) or _normalize_text(technique_name))
    category_ready = bool(selected_category.get("id"))
    direct_allowed = bool(compatibility.get("directIntegrationAllowed"))
    risk = _normalize_key(risk_tolerance or "normal")

    gates = [
        _gate(
            "official_source_review",
            "ready" if source_ready else "blocked",
            "Source reconnue ou preuve officielle fournie." if source_ready else "Ajouter article officiel, paper, depot reference ou model card.",
            {"sourceId": source.get("id"), "recognized": source.get("recognized"), "trusted": source.get("trusted")},
        ),
        _gate(
            "technique_summary",
            "ready" if summary_ready else "blocked",
            "Objectif ou nom de technique suffisant pour preparer un resume." if summary_ready else "Nommer la technique et son objectif.",
            {"objectiveExcerpt": _excerpt(objective), "techniqueName": technique_name},
        ),
        _gate(
            "category_classification",
            "ready" if category_ready else "blocked",
            "Technique classee dans la taxonomie CogniX.",
            {"categoryId": selected_category.get("id")},
        ),
        _gate(
            "compatibility_review",
            "ready" if direct_allowed else "blocked",
            str(compatibility.get("reason") or ""),
            compatibility,
        ),
        _gate(
            "security_review",
            "pending",
            "Analyse securite obligatoire avant module experimental.",
            {"requiredForCategory": selected_category.get("id")},
        ),
        _gate(
            "benchmark_before_after",
            "ready_for_comparison" if benchmark_ready else "blocked",
            "Baseline locale disponible; comparer avant/apres l'experience." if benchmark_ready else "Lancer un benchmark interne avant toute integration.",
            {"latestBenchmarkAvailable": benchmark_ready},
        ),
        _gate(
            "fallback_plan",
            "pending",
            "Prevoir retour au comportement actuel si le gain n'est pas confirme.",
            {"fallbackRequired": True},
        ),
        _gate(
            "risk_documentation",
            "pending",
            "Documenter limites, prerequis materiels et risques de regression.",
            {"riskTolerance": risk},
        ),
    ]

    blocked_gate_ids = [gate["id"] for gate in gates if gate["status"] == "blocked"]
    warnings: list[str] = []
    if not gains:
        warnings.append("Aucun gain mesurable explicite: vitesse, memoire, cout, qualite, securite ou stabilite requis.")
    if blocked_claims:
        warnings.append("Revendication bloquee: CogniX refuse les promesses incompatibles avec l'architecture du modele.")
    if not benchmark_ready:
        warnings.append("Benchmark absent: integration limitee a une veille ou un prototype non applique.")
    if not source_ready:
        warnings.append("Source non validee: ajouter paper officiel, depot reference, model card ou documentation officielle.")

    if blocked_claims:
        recommended_action = "reject_claim"
        integration_phase = "blocked"
    elif not source_ready:
        recommended_action = "needs_official_source"
        integration_phase = "watchlist"
    elif not benchmark_ready:
        recommended_action = "benchmark_required"
        integration_phase = "watchlist"
    elif not direct_allowed:
        recommended_action = "observe_only"
        integration_phase = "watchlist"
    elif risk in {"low", "faible", "strict"}:
        recommended_action = "prototype_experiment"
        integration_phase = "isolated_experimental_module"
    else:
        recommended_action = "prototype_experiment"
        integration_phase = "isolated_experimental_module"

    return {
        "researchWatchVersion": COGNIX_RESEARCH_WATCH_VERSION,
        "mode": "dry_run",
        "request": {
            "objectiveExcerpt": _excerpt(objective),
            "techniqueName": _normalize_text(technique_name),
            "sourceName": _normalize_text(source_name),
            "claimedBenefit": _excerpt(claimed_benefit, limit = 300),
            "targetModule": target_module or compatibility.get("targetModule"),
            "riskTolerance": risk,
        },
        "source": source,
        "category": selected_category,
        "measurableGains": gains,
        "compatibility": compatibility,
        "gates": gates,
        "blockedGateIds": blocked_gate_ids,
        "hypeFilter": {
            "hypeOnlyAdoptionAllowed": False,
            "blockedClaims": blocked_claims,
            "requiresMeasuredGain": True,
        },
        "recommendedAction": recommended_action,
        "integrationPhase": integration_phase,
        "experimentalModulePolicy": {
            "isolationRequired": True,
            "featureFlagRequired": True,
            "rollbackRequired": True,
            "auditRequired": True,
            "directProductionActivationAllowed": False,
        },
        "benchmarkPolicy": {
            "latestBenchmarkAvailable": benchmark_ready,
            "beforeAfterComparisonRequired": True,
            "acceptedGainTypes": list(MEASURABLE_GAIN_TYPES),
            "benchmarkRunWillStart": False,
        },
        "warnings": warnings,
        "sideEffects": {
            "networkResearch": False,
            "modelDownload": False,
            "modelLoad": False,
            "benchmarkRun": False,
            "codeModification": False,
            "settingsWrite": False,
            "deployment": False,
        },
    }
