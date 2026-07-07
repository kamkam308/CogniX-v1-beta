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


COGNIX_MODEL_ROUTER_VERSION = "cognix_model_router_v2"
COGNIX_EXTERNAL_MOE_ROUTER_VERSION = "cognix_external_moe_router_v1"
COGNIX_ROUTER_FALLBACK_CHAIN_VERSION = "cognix_router_fallback_chain_v1"
SECONDARY_EXPERT_SCORE_THRESHOLD = 0.38
AMBIGUOUS_DOMAIN_MARGIN = 0.55


@dataclass(frozen = True)
class DomainProfile:
    domain: str
    label: str
    model_label: str
    expert_id: str
    model_id: str
    role: str
    preload_priority: str
    keywords: tuple[tuple[str, float], ...]


DOMAIN_PROFILES: tuple[DomainProfile, ...] = (
    DomainProfile(
        domain = "maths",
        label = "Maths",
        model_label = "CogniX Maths 3B",
        expert_id = "cognix-maths",
        model_id = "cognix-maths-3b-q4",
        role = "math_expert",
        preload_priority = "high",
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
        expert_id = "cognix-physique",
        model_id = "cognix-physique-3b-q4",
        role = "physics_expert",
        preload_priority = "high",
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
        expert_id = "cognix-code",
        model_id = "cognix-code-4b-q4",
        role = "code_expert",
        preload_priority = "high",
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
        expert_id = "cognix-business",
        model_id = "cognix-business-3b-q4",
        role = "business_expert",
        preload_priority = "normal",
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
        expert_id = "cognix-research",
        model_id = "cognix-research-3b-q4",
        role = "research_expert",
        preload_priority = "normal",
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
        expert_id = "cognix-education",
        model_id = "cognix-education-3b-q4",
        role = "education_expert",
        preload_priority = "normal",
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
    expert_id = "cognix-general",
    model_id = "cognix-general-3b-q4",
    role = "generalist",
    preload_priority = "low",
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


def _profile_for_domain(domain: str) -> DomainProfile:
    if domain == GENERAL_PROFILE.domain:
        return GENERAL_PROFILE
    return next((profile for profile in DOMAIN_PROFILES if profile.domain == domain), GENERAL_PROFILE)


def _expert_packet(profile: DomainProfile, score: float, *, rank: int, primary: bool) -> dict[str, Any]:
    return {
        "rank": rank,
        "expertId": profile.expert_id,
        "domain": profile.domain,
        "label": profile.label,
        "role": profile.role,
        "modelId": profile.model_id,
        "modelLabel": profile.model_label,
        "score": round(score, 2),
        "primary": primary,
        "willLoad": False,
        "willGenerate": False,
    }


def _fallback_step(
    step_id: str,
    action: str,
    reason: str,
    *,
    expert: dict[str, Any] | None = None,
    gate: str = "backend_orchestrator",
    terminal: bool = False,
) -> dict[str, Any]:
    payload = {
        "id": step_id,
        "action": action,
        "reason": reason,
        "gate": gate,
        "willLoad": False,
        "willGenerate": False,
        "terminal": terminal,
    }
    if expert:
        payload["expert"] = {
            "expertId": expert.get("expertId"),
            "domain": expert.get("domain"),
            "modelId": expert.get("modelId"),
            "score": expert.get("score"),
        }
    return payload


def _router_fallback_chain(
    *,
    primary: dict[str, Any],
    secondary: list[dict[str, Any]],
    needs_clarification: bool,
    selected_profile: DomainProfile,
    confidence: float,
) -> dict[str, Any]:
    triggers = ["primary_expert_unavailable", "runtime_model_missing", "quality_gate_requests_review"]
    steps: list[dict[str, Any]] = []
    if needs_clarification:
        triggers.append("ambiguous_domain")
        steps.append(
            _fallback_step(
                "clarify_ambiguous_domain",
                "request_clarification_before_model_load",
                "Deux domaines sont proches; CogniX doit clarifier avant de charger un expert.",
                gate = "user_or_orchestrator_clarification",
            )
        )
    if confidence < 0.62:
        triggers.append("low_router_confidence")
    steps.append(
        _fallback_step(
            "primary_expert_attempt",
            "try_primary_expert_when_available",
            "Utiliser l'expert principal seulement si le backend confirme que le modele est disponible.",
            expert = primary,
        )
    )
    for item in secondary:
        if item.get("expertId") == GENERAL_PROFILE.expert_id:
            continue
        steps.append(
            _fallback_step(
                f"secondary_{item.get('domain') or item.get('expertId')}",
                "try_secondary_expert_if_primary_blocked",
                "Expert secondaire autorise si le primaire est indisponible ou si le domaine reste mixte.",
                expert = item,
            )
        )
    if selected_profile.domain != GENERAL_PROFILE.domain:
        generalist = _expert_packet(
            GENERAL_PROFILE,
            0.42,
            rank = len(steps) + 1,
            primary = False,
        )
        steps.append(
            _fallback_step(
                "generalist_fallback",
                "fallback_to_generalist_model",
                "Revenir au generaliste CogniX pour eviter un blocage utilisateur si aucun expert n'est disponible.",
                expert = generalist,
                terminal = True,
            )
        )
    return {
        "fallbackChainVersion": COGNIX_ROUTER_FALLBACK_CHAIN_VERSION,
        "mode": "router_fallback_chain_dry_run",
        "status": "clarification_required" if needs_clarification else "fallback_ready",
        "triggerConditions": sorted(set(triggers)),
        "steps": steps,
        "summary": {
            "stepCount": len(steps),
            "hasSecondaryExpert": any(step.get("id", "").startswith("secondary_") for step in steps),
            "hasGeneralistFallback": any(step.get("id") == "generalist_fallback" for step in steps),
            "confidence": confidence,
        },
        "executionBoundary": {
            "backendOrchestratorRequired": True,
            "frontendDirectModelCallAllowed": False,
            "automaticExpertLoadAllowed": False,
            "automaticFallbackExecutionAllowed": False,
            "requiresRuntimeAvailabilityCheck": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "cacheMutation": False,
            "fallbackExecution": False,
        },
    }


def _external_moe_plan(
    *,
    selected_profile: DomainProfile,
    ranked_scores: list[tuple[str, float]],
    normalized_scores: dict[str, float],
    needs_clarification: bool,
    project_hint: str,
    confidence: float,
) -> dict[str, Any]:
    primary_score = normalized_scores.get(selected_profile.domain, 0.42)
    primary = _expert_packet(
        selected_profile,
        primary_score,
        rank = 1,
        primary = True,
    )
    secondary: list[dict[str, Any]] = []
    for domain, _raw_score in ranked_scores:
        if domain == selected_profile.domain or domain == GENERAL_PROFILE.domain:
            continue
        normalized_score = normalized_scores.get(domain, 0.0)
        if normalized_score < SECONDARY_EXPERT_SCORE_THRESHOLD and not needs_clarification:
            continue
        secondary.append(
            _expert_packet(
                _profile_for_domain(domain),
                normalized_score,
                rank = len(secondary) + 2,
                primary = False,
            )
        )
        if len(secondary) >= 2:
            break
    if selected_profile.domain != GENERAL_PROFILE.domain and all(
        item.get("expertId") != GENERAL_PROFILE.expert_id for item in secondary
    ):
        secondary.append(
            _expert_packet(
                GENERAL_PROFILE,
                normalized_scores.get(GENERAL_PROFILE.domain, 0.24),
                rank = len(secondary) + 2,
                primary = False,
            )
        )
    fallback_chain = _router_fallback_chain(
        primary = primary,
        secondary = secondary,
        needs_clarification = needs_clarification,
        selected_profile = selected_profile,
        confidence = confidence,
    )
    return {
        "routerVersion": COGNIX_EXTERNAL_MOE_ROUTER_VERSION,
        "mode": "external_moe_dry_run",
        "strategy": (
            "clarify_before_expert_load"
            if needs_clarification
            else "direct_primary_expert"
        ),
        "primaryExpert": primary,
        "secondaryExperts": secondary,
        "generalistFallback": {
            "expertId": GENERAL_PROFILE.expert_id,
            "modelId": GENERAL_PROFILE.model_id,
            "enabled": selected_profile.domain != GENERAL_PROFILE.domain,
            "willLoad": False,
        },
        "fallbackChain": fallback_chain,
        "cacheIntent": {
            "preferredCachePolicy": "project_lru" if project_hint else "chat_lru",
            "keepPrimaryWarmSeconds": 15 * 60 if project_hint else 10 * 60,
            "preloadPriority": selected_profile.preload_priority,
            "willMutateCache": False,
        },
        "clarification": {
            "required": needs_clarification,
            "reason": (
                "Deux domaines CogniX sont proches; demander une precision avant de charger un expert."
                if needs_clarification
                else "Le domaine principal domine assez pour choisir l'expert sans question."
            ),
        },
        "executionBoundary": {
            "backendOrchestratorRequired": True,
            "frontendDirectModelCallAllowed": False,
            "automaticExpertLoadAllowed": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "cacheMutation": False,
        },
    }


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
    ranked_with_general = ranked + [(GENERAL_PROFILE.domain, 0.0)]
    needs_clarification = bool(
        top_score > 0
        and second_score > 0
        and (top_score - second_score) < AMBIGUOUS_DOMAIN_MARGIN
    )
    confidence = _confidence(top_score, second_score)
    external_moe_plan = _external_moe_plan(
        selected_profile = selected_profile,
        ranked_scores = ranked_with_general,
        normalized_scores = scores,
        needs_clarification = needs_clarification,
        project_hint = project_hint,
        confidence = confidence,
    )

    return {
        "routerVersion": COGNIX_MODEL_ROUTER_VERSION,
        "selectedDomain": selected_profile.domain,
        "label": selected_profile.label,
        "recommendedModelLabel": selected_profile.model_label,
        "recommendedModelId": selected_profile.model_id,
        "recommendedExpertId": selected_profile.expert_id,
        "confidence": confidence,
        "needsClarification": needs_clarification,
        "scores": scores,
        "routingMode": "local_keyword_router_v1",
        "externalMoePlan": external_moe_plan,
        "routerFallbackChain": external_moe_plan["fallbackChain"],
        "reason": (
            "Domaine ambigu: CogniX demandera une precision avant routage automatique."
            if needs_clarification
            else "Domaine choisi par signaux locaux simples, sans appel modele."
        ),
    }
