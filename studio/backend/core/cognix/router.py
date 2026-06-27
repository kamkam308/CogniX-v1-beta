# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Lightweight CogniX domain router.

This MVP router does not call an LLM. It gives CogniX a deterministic first
routing signal that can later be replaced or enriched by model-based routing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen = True)
class DomainProfile:
    domain: str
    label: str
    model_label: str
    keywords: tuple[tuple[str, float], ...]


DOMAIN_PROFILES: tuple[DomainProfile, ...] = (
    DomainProfile(
        domain = "maths",
        label = "Maths",
        model_label = "CogniX Maths 3B",
        keywords = (
            ("equation", 1.0),
            ("derivee", 1.0),
            ("integrale", 1.0),
            ("probabilite", 0.9),
            ("matrice", 0.9),
            ("algebre", 0.9),
            ("geometrie", 0.8),
            ("theoreme", 0.8),
            ("fonction", 0.5),
            ("calcul", 0.5),
        ),
    ),
    DomainProfile(
        domain = "physique",
        label = "Physique",
        model_label = "CogniX Physique 3B",
        keywords = (
            ("mecanique", 1.1),
            ("force", 1.0),
            ("vitesse", 0.9),
            ("acceleration", 0.9),
            ("energie", 0.9),
            ("newton", 0.9),
            ("quantique", 0.8),
            ("thermodynamique", 0.8),
            ("onde", 0.7),
            ("circuit", 0.7),
        ),
    ),
    DomainProfile(
        domain = "code",
        label = "Code",
        model_label = "CogniX Code 4B",
        keywords = (
            ("python", 1.2),
            ("javascript", 1.1),
            ("typescript", 1.1),
            ("react", 1.0),
            ("backend", 0.9),
            ("frontend", 0.9),
            ("api", 0.8),
            ("bug", 0.8),
            ("erreur", 0.7),
            ("git", 0.7),
            ("code", 0.7),
        ),
    ),
    DomainProfile(
        domain = "business",
        label = "Business",
        model_label = "CogniX Business 3B",
        keywords = (
            ("business", 1.0),
            ("vente", 0.9),
            ("marketing", 0.9),
            ("client", 0.8),
            ("revenu", 0.8),
            ("strategie", 0.8),
            ("prix", 0.7),
            ("kpi", 0.7),
            ("crm", 0.7),
        ),
    ),
    DomainProfile(
        domain = "research",
        label = "Research",
        model_label = "CogniX Research 3B",
        keywords = (
            ("recherche", 1.0),
            ("source", 0.9),
            ("article", 0.9),
            ("etude", 0.8),
            ("veille", 0.8),
            ("rapport", 0.8),
            ("analyse", 0.7),
            ("compare", 0.7),
            ("resume", 0.6),
        ),
    ),
    DomainProfile(
        domain = "education",
        label = "Education",
        model_label = "CogniX Education 3B",
        keywords = (
            ("cours", 1.0),
            ("professeur", 0.9),
            ("etudiant", 0.9),
            ("exercice", 0.8),
            ("corriger", 0.7),
            ("pedagogique", 0.7),
            ("apprendre", 0.6),
            ("expliquer", 0.5),
        ),
    ),
)

GENERAL_PROFILE = DomainProfile(
    domain = "general",
    label = "General",
    model_label = "CogniX General 3B",
    keywords = (),
)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_accents.casefold()


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_+#.-]+", _normalize_text(value)))


def _score_profile(profile: DomainProfile, tokens: set[str], text: str) -> float:
    score = 0.0
    for keyword, weight in profile.keywords:
        normalized_keyword = _normalize_text(keyword)
        if " " in normalized_keyword:
            if normalized_keyword in text:
                score += weight
        elif normalized_keyword in tokens:
            score += weight
    return score


def _confidence(raw_score: float, second_score: float) -> float:
    if raw_score <= 0:
        return 0.42
    separation = max(0.0, raw_score - second_score)
    return round(min(0.94, 0.5 + raw_score * 0.14 + separation * 0.08), 2)


def classify_objective(objective: str, *, project_type: str | None = None) -> dict[str, Any]:
    text = _normalize_text(objective)
    tokens = _tokenize(objective)
    project_hint = _normalize_text(project_type or "").strip()

    raw_scores: dict[str, float] = {}
    for profile in DOMAIN_PROFILES:
        score = _score_profile(profile, tokens, text)
        if project_hint and project_hint in {profile.domain, _normalize_text(profile.label)}:
            score += 1.3
        raw_scores[profile.domain] = round(score, 3)

    ranked = sorted(raw_scores.items(), key = lambda item: item[1], reverse = True)
    top_domain, top_score = ranked[0] if ranked else (GENERAL_PROFILE.domain, 0.0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score <= 0:
        selected_profile = GENERAL_PROFILE
        top_domain = GENERAL_PROFILE.domain
        second_score = 0.0
    else:
        selected_profile = next(profile for profile in DOMAIN_PROFILES if profile.domain == top_domain)

    scores = {
        domain: round(min(0.97, 0.18 + raw_score * 0.18), 2)
        for domain, raw_score in raw_scores.items()
    }
    scores[GENERAL_PROFILE.domain] = 0.42 if top_score <= 0 else 0.24
    needs_clarification = bool(top_score > 0 and second_score > 0 and (top_score - second_score) < 0.55)

    return {
        "selectedDomain": selected_profile.domain,
        "label": selected_profile.label,
        "recommendedModelLabel": selected_profile.model_label,
        "confidence": _confidence(top_score, second_score),
        "needsClarification": needs_clarification,
        "scores": scores,
        "routingMode": "local_keyword_router_v1",
        "reason": (
            "Domaine ambigu: CogniX demandera une precision avant routage automatique."
            if needs_clarification
            else "Domaine choisi par signaux locaux simples, sans appel modele."
        ),
    }
