# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX prompt/context compression planning.

This module performs deterministic extractive compression. It does not call a
model, mutate prompts in place, or hide the compression plan from the backend.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_PROMPT_COMPRESSION_VERSION = "cognix_prompt_compression_v1"
COGNIX_CONTEXT_RANKER_VERSION = "cognix_context_ranker_v1"
COGNIX_COMPRESSION_EVALUATOR_VERSION = "cognix_compression_evaluator_v1"

SIGNAL_TERMS = {
    "important",
    "objectif",
    "goal",
    "erreur",
    "error",
    "security",
    "securite",
    "test",
    "source",
    "decision",
    "todo",
    "rag",
    "fine-tuning",
    "code",
    "model",
    "modele",
}


def _normalize(value: Any) -> str:
    return "\n".join(line.strip() for line in str(value or "").replace("\r\n", "\n").splitlines() if line.strip())


def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text or "")))


def _keywords(text: str) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[a-zA-Z0-9_+-]{4,}", text or "")
        if item.lower() not in {"avec", "dans", "pour", "that", "this", "from", "have", "will"}
    }


def _sentences(text: str) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    chunks = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _score_sentence(sentence: str, *, objective_terms: set[str], index: int, total: int) -> dict[str, Any]:
    sentence_terms = _keywords(sentence)
    overlap = sentence_terms & objective_terms
    signals = sentence_terms & SIGNAL_TERMS
    position_bonus = 0.08 if index in {0, total - 1} else 0.0
    length = estimate_tokens(sentence)
    length_penalty = 0.04 if length > 90 else 0.0
    score = 0.18 + (0.17 * len(overlap)) + (0.08 * len(signals)) + position_bonus - length_penalty
    return {
        "index": index,
        "score": round(min(max(score, 0.01), 1.0), 3),
        "matchedObjectiveTerms": sorted(overlap)[:12],
        "matchedSignalTerms": sorted(signals)[:12],
        "tokenCount": length,
    }


def build_prompt_compression_blueprint() -> dict[str, Any]:
    return {
        "promptCompressionVersion": COGNIX_PROMPT_COMPRESSION_VERSION,
        "contextRankerVersion": COGNIX_CONTEXT_RANKER_VERSION,
        "compressionEvaluatorVersion": COGNIX_COMPRESSION_EVALUATOR_VERSION,
        "mode": "deterministic_extractive_compression",
        "services": ["PromptCompressionService", "ContextRanker", "CompressionEvaluator"],
        "display": {
            "defaultVisibility": "invisible",
            "badge": "Context optimized",
            "badgeOnly": True,
        },
        "pipeline": [
            "long_context",
            "importance_ranking",
            "compressed_summary",
            "optional_validation",
            "compact_prompt",
        ],
        "policies": {
            "modelGenerationAllowed": False,
            "frontendDirectCompressionWriteAllowed": False,
            "rawSecretExpansionAllowed": False,
            "validationOptional": True,
        },
        "sideEffects": {
            "compressionWrite": False,
            "logWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "promptMutation": False,
        },
    }


def build_compression_evaluation(
    *,
    original_context: str,
    compressed_context: str,
    objective: str | None = None,
) -> dict[str, Any]:
    original_tokens = estimate_tokens(original_context)
    compressed_tokens = estimate_tokens(compressed_context)
    original_terms = _keywords(original_context)
    compressed_terms = _keywords(compressed_context)
    objective_terms = _keywords(objective or "")
    retained_terms = original_terms & compressed_terms
    retained_objective_terms = objective_terms & compressed_terms
    retained_keyword_ratio = round(len(retained_terms) / max(1, len(original_terms)), 3)
    retained_objective_ratio = round(len(retained_objective_terms) / max(1, len(objective_terms)), 3) if objective_terms else 1.0
    reduction_ratio = round(1 - (compressed_tokens / max(1, original_tokens)), 3)
    lost_info_risk = "low" if retained_objective_ratio >= 0.75 else "medium" if retained_objective_ratio >= 0.45 else "high"
    return {
        "compressionEvaluatorVersion": COGNIX_COMPRESSION_EVALUATOR_VERSION,
        "originalTokenCount": original_tokens,
        "compressedTokenCount": compressed_tokens,
        "reductionRatio": reduction_ratio,
        "retainedKeywordRatio": retained_keyword_ratio,
        "retainedObjectiveRatio": retained_objective_ratio,
        "lostInfoRisk": lost_info_risk,
        "qualityGate": {
            "passesObjectiveRetention": retained_objective_ratio >= 0.45,
            "passesMinimumCompression": reduction_ratio >= 0.05,
            "requiresOptionalValidation": lost_info_risk != "low",
        },
        "sideEffects": build_prompt_compression_blueprint()["sideEffects"],
    }


def build_prompt_compression_plan(
    *,
    username: str,
    context: str,
    objective: str | None = None,
    target_tokens: int = 500,
    project_id: str | None = None,
) -> dict[str, Any]:
    normalized_context = _normalize(context)
    sentences = _sentences(normalized_context)
    objective_terms = _keywords(objective or "")
    ranked: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        ranked.append(
            {
                **_score_sentence(sentence, objective_terms = objective_terms, index = index, total = len(sentences)),
                "text": sentence,
            }
        )
    ranked_by_score = sorted(ranked, key = lambda item: (-float(item["score"]), int(item["index"])))
    selected: list[dict[str, Any]] = []
    used_tokens = 0
    safe_target = min(max(int(target_tokens or 500), 64), max(64, estimate_tokens(normalized_context)))
    for item in ranked_by_score:
        next_count = used_tokens + int(item["tokenCount"])
        if selected and next_count > safe_target:
            continue
        selected.append(item)
        used_tokens = next_count
        if used_tokens >= safe_target:
            break
    selected_indexes = {int(item["index"]) for item in selected}
    ordered_selected = [item for item in ranked if int(item["index"]) in selected_indexes]
    compressed_context = "\n".join(item["text"] for item in ordered_selected).strip()
    if not compressed_context and normalized_context:
        compressed_context = normalized_context[:4000]
    evaluation = build_compression_evaluation(
        original_context = normalized_context,
        compressed_context = compressed_context,
        objective = objective,
    )
    context_hash = hashlib.sha256(normalized_context.encode("utf-8")).hexdigest()
    return {
        "promptCompressionVersion": COGNIX_PROMPT_COMPRESSION_VERSION,
        "contextRankerVersion": COGNIX_CONTEXT_RANKER_VERSION,
        "compressionEvaluatorVersion": COGNIX_COMPRESSION_EVALUATOR_VERSION,
        "mode": "compression_plan",
        "username": username,
        "projectId": project_id,
        "objective": objective,
        "targetTokens": safe_target,
        "contextHash": context_hash,
        "ranking": [
            {key: value for key, value in item.items() if key != "text"}
            for item in ranked_by_score
        ],
        "selectedSentenceIndexes": [int(item["index"]) for item in ordered_selected],
        "compressedContext": compressed_context,
        "evaluation": evaluation,
        "summary": {
            "originalTokenCount": evaluation["originalTokenCount"],
            "compressedTokenCount": evaluation["compressedTokenCount"],
            "targetTokenCount": safe_target,
            "reductionRatio": evaluation["reductionRatio"],
            "badge": "Context optimized" if evaluation["reductionRatio"] > 0 else None,
            "lostInfoRisk": evaluation["lostInfoRisk"],
        },
        "sideEffects": build_prompt_compression_blueprint()["sideEffects"],
    }
