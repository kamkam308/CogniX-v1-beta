# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI Evolution Engine planning.

The evolution engine turns research ideas into cautious experiment proposals.
It does not integrate techniques into production, mutate UX, run benchmarks, or
modify code without the sandbox/report/human approval pipeline.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_EVOLUTION_ENGINE_VERSION = "cognix_evolution_engine_v1"
COGNIX_PROTOTYPE_GENERATOR_VERSION = "cognix_prototype_generator_v1"
COGNIX_EVOLUTION_SECURITY_REVIEW_VERSION = "cognix_evolution_security_review_v1"
COGNIX_INTEGRATION_PROPOSAL_VERSION = "cognix_integration_proposal_v1"


CATEGORY_RULES: list[dict[str, Any]] = [
    {
        "id": "inference_optimization",
        "signals": ["latency", "speed", "vitesse", "kv cache", "speculative", "decoding", "batching"],
        "targetModules": ["cognix-runtime-adapter", "cognix-optimization-engine"],
    },
    {
        "id": "fine_tuning_method",
        "signals": ["lora", "qlora", "fine tuning", "adapter", "distillation", "training"],
        "targetModules": ["cognix-fine-tuning", "cognix-worker-queue"],
    },
    {
        "id": "rag_method",
        "signals": ["rag", "retrieval", "rerank", "embedding", "citation", "chunk"],
        "targetModules": ["cognix-rag", "cognix-memory-manager"],
    },
    {
        "id": "security_method",
        "signals": ["security", "securite", "jailbreak", "guardrail", "permission", "audit"],
        "targetModules": ["cognix-security-policy", "cognix-governance-manager"],
    },
    {
        "id": "evaluation_method",
        "signals": ["eval", "benchmark", "judge", "score", "quality", "mesure"],
        "targetModules": ["cognix-benchmark", "cognix-response-reflection"],
    },
]


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _lower(value: Any) -> str:
    return _normalize(value).lower()


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9_+-]{3,}", value.lower())


def _category(text: str, requested: str | None = None) -> dict[str, Any]:
    requested_clean = _lower(requested)
    for rule in CATEGORY_RULES:
        if requested_clean == rule["id"]:
            return {**rule, "matchedSignals": [requested_clean]}
    best = CATEGORY_RULES[-1]
    best_matches: list[str] = []
    for rule in CATEGORY_RULES:
        matches = [signal for signal in rule["signals"] if signal in text]
        if len(matches) > len(best_matches):
            best = rule
            best_matches = matches
    return {**best, "matchedSignals": best_matches[:8]}


def _risk_level(text: str, risk_tolerance: str | None) -> str:
    if any(token in text for token in ("auth", "token", "secret", "permission", "jailbreak", "production", "database")):
        return "high"
    if any(token in text for token in ("network", "cloud", "runtime", "plugin", "tool", "training")):
        return "medium"
    if _lower(risk_tolerance) == "low":
        return "medium"
    return "low"


def build_evolution_blueprint() -> dict[str, Any]:
    return {
        "evolutionEngineVersion": COGNIX_EVOLUTION_ENGINE_VERSION,
        "prototypeGeneratorVersion": COGNIX_PROTOTYPE_GENERATOR_VERSION,
        "securityReviewVersion": COGNIX_EVOLUTION_SECURITY_REVIEW_VERSION,
        "integrationProposalVersion": COGNIX_INTEGRATION_PROPOSAL_VERSION,
        "mode": "cautious_ai_evolution_contract",
        "services": [
            "EvolutionEngine",
            "ResearchWatcher",
            "PrototypeGenerator",
            "SandboxManager",
            "BenchmarkService",
            "SecurityReviewService",
        ],
        "pipeline": [
            "research_watcher",
            "technique_classifier",
            "prototype_plan",
            "sandbox_implementation",
            "benchmark",
            "security_review",
            "report",
            "human_approval",
        ],
        "uiContract": {
            "tab": "Evolution Lab",
            "components": ["cards", "badges", "progress_indicators", "reports", "approval_modals"],
        },
        "rules": {
            "automaticProductionIntegrationAllowed": False,
            "automaticUxModificationAllowed": False,
            "sandboxRequired": True,
            "benchmarkRequired": True,
            "securityReviewRequired": True,
            "humanApprovalRequired": True,
        },
        "sideEffects": {
            "evolutionItemWrite": False,
            "experimentWrite": False,
            "benchmarkResultWrite": False,
            "proposalWrite": False,
            "sandboxRun": False,
            "benchmarkRun": False,
            "codeModification": False,
            "productionIntegration": False,
            "uxModification": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "toolExecution": False,
        },
    }


def build_evolution_item_plan(
    *,
    technique_name: str,
    source_name: str | None = None,
    category: str | None = None,
    claimed_benefit: str | None = None,
    evidence: list[Any] | None = None,
    risk_tolerance: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    clean_name = _normalize(technique_name)[:240] or "New AI technique"
    clean_source = _normalize(source_name)[:240] or "manual"
    text = _lower(" ".join([clean_name, clean_source, _normalize(claimed_benefit), " ".join(map(str, evidence or []))]))
    category_payload = _category(text, category)
    risk = _risk_level(text, risk_tolerance)
    readiness = "ready_for_sandbox_plan" if category_payload["matchedSignals"] else "needs_research_review"
    return {
        "evolutionEngineVersion": COGNIX_EVOLUTION_ENGINE_VERSION,
        "mode": "evolution_item_plan",
        "projectId": project_id,
        "technique": {
            "name": clean_name,
            "sourceName": clean_source,
            "category": category_payload["id"],
            "claimedBenefit": _normalize(claimed_benefit)[:1000],
            "matchedSignals": category_payload["matchedSignals"],
            "targetModules": category_payload["targetModules"],
        },
        "risk": {
            "level": risk,
            "requiresSecurityReview": True,
            "riskTolerance": risk_tolerance or "balanced",
        },
        "progress": [
            {"id": "detected", "label": "Nouvelle technique detectee", "status": "complete"},
            {"id": "classified", "label": "Technique classifiee", "status": "complete"},
            {"id": "prototype", "label": "Prototype cree", "status": "planned"},
            {"id": "benchmark", "label": "Benchmark termine", "status": "planned"},
            {"id": "security_review", "label": "Risque evalue", "status": "planned"},
            {"id": "approval", "label": "Validation humaine", "status": "blocked_until_review"},
        ],
        "gates": {
            "researchReviewRequired": readiness == "needs_research_review",
            "sandboxRequired": True,
            "benchmarkRequired": True,
            "securityReviewRequired": True,
            "humanApprovalRequired": True,
        },
        "status": readiness,
        "sideEffects": build_evolution_blueprint()["sideEffects"],
    }


def build_evolution_experiment_plan(
    *,
    item_plan: dict[str, Any],
    expected_gain_percent: float | None = None,
    benchmark_metric: str | None = None,
    sandbox_target: str | None = None,
) -> dict[str, Any]:
    technique = item_plan.get("technique") if isinstance(item_plan.get("technique"), dict) else {}
    risk = item_plan.get("risk") if isinstance(item_plan.get("risk"), dict) else {}
    try:
        gain = float(expected_gain_percent if expected_gain_percent is not None else 0.0)
    except (TypeError, ValueError):
        gain = 0.0
    gain = round(max(-100.0, min(gain, 500.0)), 2)
    risk_level = str(risk.get("level") or "medium")
    recommendation = "reject_for_now"
    if gain >= 25 and risk_level == "low":
        recommendation = "integrate_experimental_after_approval"
    elif gain >= 10 and risk_level in {"low", "medium"}:
        recommendation = "continue_experiment"
    elif gain > 0:
        recommendation = "watch_and_retest"
    return {
        "evolutionEngineVersion": COGNIX_EVOLUTION_ENGINE_VERSION,
        "prototypeGeneratorVersion": COGNIX_PROTOTYPE_GENERATOR_VERSION,
        "securityReviewVersion": COGNIX_EVOLUTION_SECURITY_REVIEW_VERSION,
        "integrationProposalVersion": COGNIX_INTEGRATION_PROPOSAL_VERSION,
        "mode": "evolution_experiment_plan",
        "technique": technique,
        "prototypePlan": {
            "service": "PrototypeGenerator",
            "target": sandbox_target or technique.get("category") or "feature",
            "status": "planned",
            "willModifyCodeNow": False,
        },
        "sandboxPlan": {
            "service": "SandboxManager",
            "required": True,
            "willRunNow": False,
            "productionSecretsAccessible": False,
            "productionWriteAllowed": False,
        },
        "benchmarkPlan": {
            "service": "BenchmarkService",
            "metric": benchmark_metric or "quality_speed_cost",
            "expectedGainPercent": gain,
            "willRunNow": False,
        },
        "securityReview": {
            "service": "SecurityReviewService",
            "riskLevel": risk_level,
            "required": True,
            "blocksProduction": True,
        },
        "report": {
            "gainLabel": f"+{gain:g} % vitesse" if gain > 0 else "gain non prouve",
            "riskLabel": risk_level,
            "recommendation": recommendation,
            "humanReadableSummary": (
                f"{technique.get('name', 'Technique')} -> gain {gain:g} %, risque {risk_level}, "
                f"recommandation: {recommendation}."
            ),
        },
        "integrationProposal": {
            "status": "requires_human_approval",
            "recommendation": recommendation,
            "automaticProductionIntegrationAllowed": False,
            "automaticUxModificationAllowed": False,
        },
        "sideEffects": build_evolution_blueprint()["sideEffects"],
    }
