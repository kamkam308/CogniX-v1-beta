# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX response self-reflection.

This module evaluates a completed assistant answer without calling another
model, exposing chain-of-thought, mutating memory, or executing tools.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_RESPONSE_REFLECTION_VERSION = "cognix_response_reflection_v1"

UNCERTAINTY_MARKERS = (
    "je ne suis pas sur",
    "je ne suis pas sûr",
    "pas certain",
    "peut-etre",
    "peut-être",
    "a verifier",
    "à vérifier",
    "not sure",
    "uncertain",
    "maybe",
)

SOURCE_MARKERS = (
    "source",
    "citation",
    "selon",
    "d'apres",
    "d'après",
    "http://",
    "https://",
)

CODE_KEYWORDS = ("code", "script", "fonction", "bug", "erreur", "python", "javascript", "typescript")
MATH_KEYWORDS = ("calcule", "calcul", "equation", "équation", "derivee", "dérivée", "integrale", "intégrale")


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\r\n", "\n").split()).strip()


def _words(value: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ'-]+", value.lower())


def _word_count(value: str) -> int:
    return len(_words(value))


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _has_citation(response: str, response_sources: list[dict[str, Any]]) -> bool:
    if response_sources:
        return True
    if re.search(r"\[[0-9]{1,3}\]", response):
        return True
    return _contains_any(response, SOURCE_MARKERS)


def _needs_code(prompt: str) -> bool:
    return _contains_any(prompt, CODE_KEYWORDS)


def _needs_math(prompt: str) -> bool:
    if _contains_any(prompt, MATH_KEYWORDS):
        return True
    return bool(re.search(r"\d+\s*[-+*/=]\s*\d+", prompt))


def _has_code_shape(response: str) -> bool:
    return "```" in response or bool(re.search(r"\b(def|class|function|const|let|var|import)\b", response))


def _has_math_shape(response: str) -> bool:
    return bool(re.search(r"\d|=|\\frac|\\int|\\sum", response))


def _issue(issue_id: str, severity: str, label: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": issue_id,
        "severity": severity,
        "label": label,
        "detail": detail,
        "evidence": evidence or {},
    }


def _quality_issues(
    *,
    prompt: str,
    response: str,
    response_sources: list[dict[str, Any]],
    requires_sources: bool,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    prompt_words = _word_count(prompt)
    response_words = _word_count(response)

    if not response_words:
        issues.append(
            _issue(
                "empty_response",
                "critical",
                "Reponse vide",
                "Aucune reponse exploitable n'a ete fournie.",
            )
        )
        return issues

    if prompt_words >= 12 and response_words < 24:
        issues.append(
            _issue(
                "incomplete_response",
                "high",
                "Reponse probablement incomplete",
                "La reponse est courte par rapport a la demande.",
                {"promptWords": prompt_words, "responseWords": response_words},
            )
        )

    if _contains_any(response, UNCERTAINTY_MARKERS):
        issues.append(
            _issue(
                "uncertainty_detected",
                "medium",
                "Incertitude explicite",
                "La reponse contient des marqueurs d'incertitude.",
            )
        )

    if requires_sources and not _has_citation(response, response_sources):
        issues.append(
            _issue(
                "missing_sources",
                "high",
                "Sources manquantes",
                "La demande exige des sources mais la reponse ne fournit pas de citation exploitable.",
            )
        )

    if _needs_code(prompt) and not _has_code_shape(response):
        issues.append(
            _issue(
                "missing_code_shape",
                "medium",
                "Structure code absente",
                "La demande semble demander du code mais la reponse ne contient pas de bloc ou forme de code.",
            )
        )

    if _needs_math(prompt) and not _has_math_shape(response):
        issues.append(
            _issue(
                "missing_math_trace",
                "medium",
                "Trace mathematique faible",
                "La demande semble mathematique mais la reponse ne contient pas de calcul visible.",
            )
        )

    if response_words > 900 and not response_sources and requires_sources:
        issues.append(
            _issue(
                "long_unsourced_answer",
                "medium",
                "Longue reponse non sourcee",
                "Une longue reponse demandant verification devrait etre reliee a des sources.",
                {"responseWords": response_words},
            )
        )

    return issues


def _confidence_score(issues: list[dict[str, Any]], *, has_sources: bool) -> float:
    score = 0.9
    penalties = {
        "critical": 0.48,
        "high": 0.22,
        "medium": 0.12,
        "low": 0.06,
    }
    for issue in issues:
        score -= penalties.get(str(issue.get("severity") or "medium"), 0.12)
    if has_sources:
        score += 0.04
    return round(min(max(score, 0.05), 0.98), 2)


def _confidence_label(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _recommended_action(label: str, issues: list[dict[str, Any]]) -> str:
    issue_ids = {str(issue.get("id")) for issue in issues}
    severities = {str(issue.get("severity")) for issue in issues}
    if "empty_response" in issue_ids:
        return "regenerate_response"
    if "missing_sources" in issue_ids or "long_unsourced_answer" in issue_ids:
        return "verify_with_sources"
    if label == "low" or "critical" in severities or "high" in severities:
        return "second_pass_recommended"
    if label == "medium":
        return "light_review_recommended"
    return "accept"


def build_response_reflection_evaluation(
    *,
    prompt: str,
    response: str,
    response_sources: list[dict[str, Any]] | None = None,
    requires_sources: bool = False,
    task_type: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate an assistant response without generating or exposing reasoning."""

    normalized_prompt = _normalize_text(prompt)
    normalized_response = _normalize_text(response)
    sources = [item for item in (response_sources or []) if isinstance(item, dict)]
    has_sources = _has_citation(normalized_response, sources)
    issues = _quality_issues(
        prompt = normalized_prompt,
        response = normalized_response,
        response_sources = sources,
        requires_sources = requires_sources,
    )
    score = _confidence_score(issues, has_sources = has_sources)
    label = _confidence_label(score)
    action = _recommended_action(label, issues)
    verification_required = action != "accept"
    return {
        "reflectionVersion": COGNIX_RESPONSE_REFLECTION_VERSION,
        "mode": "post_response_evaluation",
        "taskType": task_type or "general",
        "modelId": model_id,
        "confidence": {
            "score": score,
            "label": label,
            "verificationRequired": verification_required,
            "recommendedAction": action,
        },
        "qualitySignals": {
            "promptWords": _word_count(normalized_prompt),
            "responseWords": _word_count(normalized_response),
            "sourceCount": len(sources),
            "hasCitationMarkers": has_sources,
            "requiresSources": bool(requires_sources),
            "issueCount": len(issues),
        },
        "issues": issues,
        "userVisibleMetadata": {
            "badgeLabel": {
                "high": "Fiabilite estimee elevee",
                "medium": "Verification legere conseillee",
                "low": "Verification recommandee",
            }[label],
            "tooltip": (
                "Evaluation heuristique CogniX post-reponse. "
                "Aucun raisonnement interne brut n'est expose."
            ),
            "showExpandableDetails": bool(issues),
        },
        "policies": {
            "rawChainOfThoughtAllowed": False,
            "frontendMayShowBadge": True,
            "frontendMustNotShowHiddenReasoning": True,
            "secondModelCallAutomatic": False,
            "humanVerificationForLowConfidence": label == "low",
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
            "memoryWrite": False,
            "rawReasoningExposure": False,
        },
    }
