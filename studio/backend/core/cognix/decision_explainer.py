# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX explainable decision layer.

This module turns already-recorded router/orchestrator decisions into safe,
human-readable explanations. It never calls a model and never exposes hidden
reasoning; only explicit reason codes and selected public signals are returned.
"""

from __future__ import annotations

from typing import Any


COGNIX_DECISION_LOG_SERVICE_VERSION = "cognix_decision_log_service_v1"
COGNIX_EXPLANATION_GENERATOR_VERSION = "cognix_explanation_generator_v1"
COGNIX_ROUTER_DECISION_EXPLAINER_VERSION = "cognix_router_decision_explainer_v1"


PATH_LABELS = {
    "rag_first": "RAG avant fine-tuning",
    "guided_fine_tuning": "fine-tuning guide",
    "tool_plan": "action outil controlee",
    "codex_guarded_pipeline": "pipeline Codex securise",
    "expert_chat": "chat avec expert adapte",
}


DOMAIN_LABELS = {
    "code": "code",
    "math": "mathematiques",
    "physics": "physique",
    "research": "recherche",
    "general": "general",
    "rag": "documents",
    "tool": "outils",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or fallback).strip()
    return text[:2000]


def _reason(
    code: str,
    label: str,
    detail: str,
    *,
    confidence: float | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "detail": detail,
        "confidence": confidence,
        "evidence": evidence or {},
    }


def build_decision_explainer_blueprint() -> dict[str, Any]:
    return {
        "decisionLogServiceVersion": COGNIX_DECISION_LOG_SERVICE_VERSION,
        "explanationGeneratorVersion": COGNIX_EXPLANATION_GENERATOR_VERSION,
        "routerDecisionExplainerVersion": COGNIX_ROUTER_DECISION_EXPLAINER_VERSION,
        "services": ["DecisionLogService", "ExplanationGenerator", "RouterDecisionExplainer"],
        "sourceTypes": ["orchestrator_log", "router_log", "manual"],
        "reasonCodeFamilies": [
            "domain_match",
            "strategy_selection",
            "model_provider_fit",
            "readiness_status",
            "safety_guardrail",
            "human_confirmation",
            "warnings_considered",
        ],
        "uiContract": {
            "entryPoint": "Pourquoi cette decision ?",
            "surface": "tooltip_or_side_panel",
            "rawReasoningVisible": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
            "rawReasoningExposure": False,
            "decisionWrite": False,
            "reasonWrite": False,
        },
    }


def _strategy_reason(path: str, decision: dict[str, Any]) -> dict[str, Any]:
    if path == "rag_first":
        return _reason(
            "strategy_rag_first",
            "RAG prioritaire",
            "CogniX privilegie les documents et sources internes avant un entrainement, car la demande depend du contexte disponible.",
            evidence = {"recommendedPath": path, "uses": decision.get("uses")},
        )
    if path == "guided_fine_tuning":
        return _reason(
            "strategy_fine_tuning",
            "Fine-tuning guide",
            "CogniX oriente vers un plan d'entrainement quand l'objectif parle de dataset, style, comportement ou specialisation durable.",
            evidence = {"recommendedPath": path, "uses": decision.get("uses")},
        )
    if path == "tool_plan":
        return _reason(
            "strategy_tool_plan",
            "Action outil controlee",
            "CogniX prepare une action via connecteur parce que la demande implique un outil externe, avec permissions et confirmation.",
            evidence = {"recommendedPath": path, "primaryCapability": decision.get("primaryCapability")},
        )
    if path == "codex_guarded_pipeline":
        return _reason(
            "strategy_codex_pipeline",
            "Pipeline code securise",
            "CogniX passe par le pipeline Codex car la demande touche au code source, aux tests ou a Git, sans modification directe depuis le chat.",
            evidence = {"recommendedPath": path, "primaryCapability": decision.get("primaryCapability")},
        )
    return _reason(
        "strategy_expert_chat",
        "Expert adapte",
        "CogniX garde une strategie de chat expert quand aucun workflow specialise n'est plus pertinent que la reponse directe.",
        evidence = {"recommendedPath": path or "expert_chat"},
    )


def _question_hint(question: str, decision: dict[str, Any]) -> str:
    normalized = question.casefold()
    provider_type = _clean(decision.get("providerType") or decision.get("provider_type"))
    path = _clean(decision.get("recommendedPath") or decision.get("recommended_path"))
    if "modele" in normalized or "model" in normalized:
        model = _clean(decision.get("modelId") or decision.get("model_id") or decision.get("modelLabel"))
        if model:
            return f"Le modele `{model}` est explique par le domaine detecte, la disponibilite runtime et les garde-fous actifs."
    if "cloud" in normalized or "local" in normalized:
        if provider_type:
            return f"Le choix local/cloud vient du provider `{provider_type}` et de l'etat d'execution autorise."
    if "rag" in normalized or "fine" in normalized or "entrain" in normalized:
        if path:
            return f"La strategie `{path}` indique pourquoi CogniX prefere RAG, fine-tuning ou une autre voie."
    if "document" in normalized or "source" in normalized:
        return "Les documents sont utilises uniquement quand la strategie et les sources declarees rendent le contexte utile."
    return ""


def build_decision_explanation(
    *,
    decision: dict[str, Any],
    source_type: str = "manual",
    source_id: str | None = None,
    question: str | None = None,
    objective_excerpt: str | None = None,
) -> dict[str, Any]:
    decision = _as_dict(decision)
    selected_domain = _clean(
        decision.get("selectedDomain")
        or decision.get("selected_domain")
        or decision.get("domain")
        or "general"
    )
    path = _clean(
        decision.get("recommendedPath")
        or decision.get("recommended_path")
        or decision.get("path")
        or "expert_chat"
    )
    provider_type = _clean(decision.get("providerType") or decision.get("provider_type"))
    model_id = _clean(decision.get("modelId") or decision.get("model_id") or decision.get("modelLabel"))
    status = _clean(decision.get("status") or "unknown")
    confidence = decision.get("confidence")
    side_effects = _as_dict(decision.get("sideEffects"))
    warnings = [str(item)[:500] for item in _as_list(decision.get("warnings")) if item]
    question = _clean(question)

    reasons: list[dict[str, Any]] = [
        _reason(
            "domain_match",
            "Domaine detecte",
            f"La demande est routee vers le domaine {DOMAIN_LABELS.get(selected_domain, selected_domain)}.",
            confidence = float(confidence) if isinstance(confidence, int | float) else None,
            evidence = {"selectedDomain": selected_domain, "objectiveExcerpt": objective_excerpt},
        ),
        _strategy_reason(path, decision),
    ]

    if provider_type or model_id:
        reasons.append(
            _reason(
                "model_provider_fit",
                "Modele et provider compatibles",
                "Le provider et le modele retenus correspondent au domaine, au runtime declare et aux contraintes locales/cloud.",
                evidence = {"providerType": provider_type, "modelId": model_id},
            )
        )
    if status:
        reasons.append(
            _reason(
                "readiness_status",
                "Etat d'execution",
                f"Le statut `{status}` indique si CogniX peut executer, doit configurer quelque chose, ou reste bloque.",
                evidence = {"status": status},
            )
        )
    if decision.get("requiresHumanConfirmation"):
        reasons.append(
            _reason(
                "human_confirmation",
                "Confirmation humaine requise",
                "La decision touche une action sensible; CogniX exige validation humaine avant execution.",
                evidence = {"requiresHumanConfirmation": True},
            )
        )
    if side_effects:
        reasons.append(
            _reason(
                "safety_guardrail",
                "Garde-fous actifs",
                "La decision est expliquee en mode planification: aucun chargement modele, generation ou appel outil n'est declenche ici.",
                evidence = {
                    key: side_effects.get(key)
                    for key in ("modelLoad", "generation", "networkModelCall", "toolExecution")
                    if key in side_effects
                },
            )
        )
    if warnings:
        reasons.append(
            _reason(
                "warnings_considered",
                "Avertissements pris en compte",
                "CogniX conserve les avertissements dans l'explication pour rendre la decision revisable.",
                evidence = {"warnings": warnings[:5]},
            )
        )

    path_label = PATH_LABELS.get(path, path or "strategie CogniX")
    model_part = f" avec `{model_id}`" if model_id else ""
    summary = f"CogniX a choisi {path_label}{model_part} pour une demande de type {DOMAIN_LABELS.get(selected_domain, selected_domain)}."
    hint = _question_hint(question, decision) if question else ""
    answer = f"{summary} " + " ".join(reason["detail"] for reason in reasons[:4])
    if hint:
        answer = f"{answer} {hint}"

    return {
        "decisionLogServiceVersion": COGNIX_DECISION_LOG_SERVICE_VERSION,
        "explanationGeneratorVersion": COGNIX_EXPLANATION_GENERATOR_VERSION,
        "routerDecisionExplainerVersion": COGNIX_ROUTER_DECISION_EXPLAINER_VERSION,
        "sourceType": source_type,
        "sourceId": source_id,
        "decisionType": "router_orchestrator_decision",
        "title": "Pourquoi cette decision ?",
        "summary": summary,
        "answer": answer[:4000],
        "question": question or None,
        "reasonCodes": reasons,
        "display": {
            "entryPoint": "Pourquoi cette decision ?",
            "panelTitle": "Explication de decision",
            "safeForTooltip": True,
            "rawReasoningVisible": False,
        },
        "trace": {
            "selectedDomain": selected_domain,
            "recommendedPath": path,
            "primaryCapability": decision.get("primaryCapability") or decision.get("primary_capability"),
            "providerType": provider_type or None,
            "modelId": model_id or None,
            "status": status,
        },
        "sideEffects": build_decision_explainer_blueprint()["sideEffects"],
    }
