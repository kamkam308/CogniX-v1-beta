# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native task decision engine.

This module chooses the high-level AI architecture for a user objective before
any model, tool, RAG index, or fine-tuning job can run.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


COGNIX_DECISION_ENGINE_VERSION = "cognix_decision_engine_v1"


KEYWORD_WEIGHTS: dict[str, tuple[tuple[str, float], ...]] = {
    "rag": (
        ("pdf", 1.3),
        ("document", 1.2),
        ("documents", 1.2),
        ("fichier", 1.0),
        ("fichiers", 1.0),
        ("source", 0.9),
        ("sources", 0.9),
        ("cours", 0.9),
        ("contexte", 0.8),
        ("drive", 0.8),
        ("sharepoint", 0.8),
        ("indexer", 1.1),
        ("retrouver", 0.7),
        ("repondre a partir", 1.4),
    ),
    "fine_tuning": (
        ("fine tuning", 1.4),
        ("fine-tuning", 1.4),
        ("finetuning", 1.4),
        ("entrainer", 1.2),
        ("lora", 1.2),
        ("qlora", 1.2),
        ("dataset", 1.0),
        ("jeu de donnees", 1.0),
        ("style", 0.8),
        ("format", 0.8),
        ("comportement", 0.9),
        ("specialiser", 0.9),
    ),
    "tool": (
        ("email", 1.0),
        ("mail", 0.9),
        ("gmail", 1.2),
        ("github", 1.2),
        ("issue", 0.8),
        ("pull request", 0.9),
        ("drive", 1.0),
        ("notion", 1.0),
        ("slack", 1.0),
        ("teams", 1.0),
        ("moodle", 1.0),
        ("connecteur", 0.9),
        ("outil", 0.7),
    ),
    "codex": (
        ("codex", 1.2),
        ("code source", 1.1),
        ("branche", 0.9),
        ("commit", 0.9),
        ("github", 0.7),
        ("ajoute une fonctionnalite", 1.2),
        ("ajouter une fonctionnalite", 1.2),
        ("corrige ce bug", 1.1),
        ("modifie le code", 1.2),
        ("refactor", 1.0),
        ("test automatique", 0.9),
    ),
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


def _score_keywords(text: str, keywords: tuple[tuple[str, float], ...]) -> float:
    score = 0.0
    for keyword, weight in keywords:
        normalized_keyword = _normalize_text(keyword)
        if " " in normalized_keyword:
            if normalized_keyword in text:
                score += weight
        elif re.search(rf"(?<![a-z0-9_]){re.escape(normalized_keyword)}(?![a-z0-9_])", text):
            score += weight
    return round(score, 3)


def _scores(objective: str) -> dict[str, float]:
    text = _normalize_text(objective)
    return {
        key: _score_keywords(text, keywords)
        for key, keywords in KEYWORD_WEIGHTS.items()
    }


def _confidence(top_score: float, second_score: float) -> float:
    if top_score <= 0:
        return 0.52
    separation = max(0.0, top_score - second_score)
    return round(min(0.93, 0.58 + top_score * 0.08 + separation * 0.05), 2)


def _visible_status(path: str) -> list[str]:
    if path == "rag_first":
        return [
            "Analyse de la demande",
            "Selection du contexte documentaire",
            "Preparation de la reponse avec sources internes",
        ]
    if path == "guided_fine_tuning":
        return [
            "Analyse de l'objectif d'entrainement",
            "Verification du dataset",
            "Estimation ressources et methode LoRA/QLoRA",
        ]
    if path == "tool_plan":
        return [
            "Identification de l'outil",
            "Verification des permissions",
            "Preparation d'une action controlee",
        ]
    if path == "codex_guarded_pipeline":
        return [
            "Analyse de la fonctionnalite",
            "Preparation branche, tests et revue securite",
            "Planification sans modification directe",
        ]
    return [
        "Analyse de la demande",
        "Choix du modele adapte",
        "Preparation de la reponse",
    ]


def _build_steps(path: str) -> list[dict[str, str]]:
    if path == "rag_first":
        return [
            {"id": "collect_documents", "label": "Identifier les documents utiles", "status": "planned"},
            {"id": "retrieve_context", "label": "Rechercher les passages pertinents", "status": "planned"},
            {"id": "inject_sources", "label": "Injecter le contexte avec sources", "status": "planned"},
        ]
    if path == "guided_fine_tuning":
        return [
            {"id": "validate_dataset", "label": "Verifier le dataset", "status": "planned"},
            {"id": "estimate_training", "label": "Estimer RAM, VRAM et duree", "status": "planned"},
            {"id": "choose_adapter", "label": "Choisir LoRA, QLoRA ou full tuning", "status": "planned"},
        ]
    if path == "tool_plan":
        return [
            {"id": "select_tool", "label": "Choisir le connecteur", "status": "planned"},
            {"id": "check_permissions", "label": "Verifier permissions et confirmation", "status": "planned"},
            {"id": "prepare_tool_action", "label": "Preparer l'action sans execution directe", "status": "planned"},
        ]
    if path == "codex_guarded_pipeline":
        return [
            {"id": "create_branch", "label": "Travailler sur une branche Git", "status": "planned"},
            {"id": "apply_changes", "label": "Modifier le code source natif", "status": "planned"},
            {"id": "verify_pipeline", "label": "Lancer tests, build et controle securite", "status": "planned"},
        ]
    return [
        {"id": "route_domain", "label": "Router vers l'expert adapte", "status": "planned"},
        {"id": "build_context", "label": "Construire le contexte minimal", "status": "planned"},
        {"id": "answer", "label": "Generer la reponse", "status": "planned"},
    ]


def _tool_candidates(objective: str) -> list[str]:
    text = _normalize_text(objective)
    candidates: list[str] = []
    for keyword, tool_id in (
        ("github", "github"),
        ("git", "github"),
        ("gmail", "gmail"),
        ("email", "gmail"),
        ("mail", "gmail"),
        ("drive", "google-drive"),
        ("document", "google-drive"),
        ("notion", "notion"),
        ("slack", "slack"),
        ("teams", "microsoft-teams"),
        ("moodle", "moodle"),
        ("sharepoint", "sharepoint"),
    ):
        if keyword in text and tool_id not in candidates:
            candidates.append(tool_id)
    return candidates


def build_task_strategy(
    objective: str,
    *,
    classification: dict[str, Any] | None = None,
    project_type: str | None = None,
) -> dict[str, Any]:
    score_map = _scores(objective)
    ranked = sorted(score_map.items(), key = lambda item: item[1], reverse = True)
    top_key, top_score = ranked[0] if ranked else ("chat", 0.0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # Roadmap rule: document-grounded answers use RAG before fine-tuning.
    if score_map["rag"] > 0 and score_map["rag"] >= score_map["fine_tuning"] - 0.2:
        path = "rag_first"
    elif top_key == "fine_tuning" and top_score > 0:
        path = "guided_fine_tuning"
    elif top_key == "codex" and top_score > 0:
        path = "codex_guarded_pipeline"
    elif top_key == "tool" and top_score > 0:
        path = "tool_plan"
    else:
        path = "expert_chat"

    selected_domain = str((classification or {}).get("selectedDomain") or project_type or "general")
    confidence = _confidence(top_score, second_score)
    uses = {
        "rag": path == "rag_first",
        "fineTuning": path == "guided_fine_tuning",
        "tools": path == "tool_plan",
        "codex": path == "codex_guarded_pipeline",
    }
    deferred: list[str] = []
    risks: list[str] = []
    if path == "rag_first" and score_map["fine_tuning"] > 0:
        deferred.append("Fine-tuning differe: RAG recommande d'abord pour les documents.")
    if path in {"tool_plan", "codex_guarded_pipeline", "guided_fine_tuning"}:
        risks.append("Action potentiellement sensible: rester en planification jusqu'aux garde-fous.")

    labels = {
        "rag_first": "RAG avant fine-tuning",
        "guided_fine_tuning": "Fine-tuning guide",
        "tool_plan": "Plan d'outil controle",
        "codex_guarded_pipeline": "Pipeline Codex securise",
        "expert_chat": "Chat expert local",
    }
    primary_capabilities = {
        "rag_first": "rag",
        "guided_fine_tuning": "fine_tuning",
        "tool_plan": "tool_registry",
        "codex_guarded_pipeline": "codex_secure_agent",
        "expert_chat": "model_router",
    }

    return {
        "decisionEngineVersion": COGNIX_DECISION_ENGINE_VERSION,
        "path": path,
        "label": labels[path],
        "primaryCapability": primary_capabilities[path],
        "confidence": confidence,
        "scores": score_map,
        "selectedDomain": selected_domain,
        "preferredModelRole": (
            "document_grounded"
            if path == "rag_first"
            else "specialized_expert"
            if selected_domain != "general"
            else "generalist"
        ),
        "requiresHumanConfirmation": path in {
            "tool_plan",
            "codex_guarded_pipeline",
            "guided_fine_tuning",
        },
        "uses": uses,
        "toolCandidates": _tool_candidates(objective),
        "contextPlan": {
            "includeUserMemory": True,
            "includeProjectMemory": True,
            "includeRagChunks": path == "rag_first",
            "includeRecentMessages": True,
            "rawHistoryAllowed": False,
        },
        "steps": _build_steps(path),
        "deferred": deferred,
        "risks": risks,
        "visibleStatus": _visible_status(path),
        "reason": (
            "Les documents et sources dominent: CogniX recommande RAG avant fine-tuning."
            if path == "rag_first"
            else "L'objectif vise un comportement ou dataset: CogniX recommande un fine-tuning guide."
            if path == "guided_fine_tuning"
            else "Un connecteur est implique: CogniX planifie l'outil avec permissions et audit."
            if path == "tool_plan"
            else "La demande touche au code source: CogniX passe par le pipeline Codex garde."
            if path == "codex_guarded_pipeline"
            else "Aucun workflow specialise n'est dominant: CogniX utilise le routeur d'expert."
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "ragIndexing": False,
            "fineTuningJob": False,
            "codeModification": False,
        },
    }
