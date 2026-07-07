# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native RAG chunk compression planning.

The planner ranks already-provided RAG chunks, performs deterministic
extractive compression, and preserves citation metadata. It never retrieves,
indexes, loads a model, or generates text.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_RAG_COMPRESSION_VERSION = "cognix_rag_compression_v1"
COGNIX_RAG_CITATION_RETENTION_VERSION = "cognix_rag_citation_retention_v1"
COGNIX_RAG_EXTRACTIVE_RANKER_VERSION = "cognix_rag_extractive_ranker_v1"

STOPWORDS = {
    "avec",
    "dans",
    "pour",
    "from",
    "that",
    "this",
    "quoi",
    "quel",
    "quelle",
    "mes",
    "mon",
    "the",
    "and",
    "des",
    "les",
    "une",
    "sur",
    "aux",
    "par",
    "est",
    "sont",
}

SIGNAL_TERMS = {
    "citation",
    "citations",
    "source",
    "sources",
    "preuve",
    "evidence",
    "pdf",
    "rag",
    "qcm",
    "document",
    "documents",
    "important",
    "definition",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r\n", "\n")).strip()


def _estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text or "")))


def _terms(value: Any) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[a-zA-Z0-9_+-]{3,}", str(value or ""))
        if item.lower() not in STOPWORDS
    }


def _sentences(text: str) -> list[str]:
    normalized = _clean_text(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [part.strip() for part in parts if part.strip()]


def _word_clip(text: str, token_budget: int) -> str:
    words = re.findall(r"\S+", text or "")
    safe_budget = max(1, token_budget)
    if len(words) <= safe_budget:
        return " ".join(words).strip()
    return (" ".join(words[:safe_budget]).rstrip() + " ...").strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunk_text(chunk: dict[str, Any]) -> str:
    return _clean_text(
        chunk.get("compressedText")
        or chunk.get("content")
        or chunk.get("text")
        or chunk.get("excerpt")
    )


def _normalize_chunk(chunk: dict[str, Any], index: int) -> dict[str, Any] | None:
    text = _chunk_text(chunk)
    if not text:
        return None
    citation = _as_dict(chunk.get("citation"))
    source_id = str(
        chunk.get("sourceId")
        or chunk.get("source_id")
        or citation.get("sourceId")
        or citation.get("source_id")
        or ""
    ).strip()
    chunk_id = str(
        chunk.get("chunkId")
        or chunk.get("id")
        or citation.get("chunkId")
        or citation.get("chunk_id")
        or f"chunk-{index + 1}"
    ).strip()[:180]
    source_name = str(
        chunk.get("sourceName")
        or chunk.get("sourceTitle")
        or chunk.get("title")
        or citation.get("sourceName")
        or citation.get("title")
        or source_id
        or "unknown"
    ).strip()[:240]
    page = chunk.get("page") or chunk.get("pageNumber") or citation.get("page") or citation.get("pageNumber")
    valid_citation = bool(source_id and chunk_id)
    return {
        "sourceId": source_id[:160],
        "sourceName": source_name,
        "sourceType": str(chunk.get("sourceType") or chunk.get("type") or "unknown").strip().lower()[:80],
        "chunkId": chunk_id,
        "page": page,
        "url": chunk.get("url") or citation.get("url"),
        "content": text[:12000],
        "contentHash": _content_hash(text),
        "inputScore": _as_float(chunk.get("score"), 0.0),
        "inputIndex": index,
        "citationValid": valid_citation,
    }


def _score_chunk(chunk: dict[str, Any], objective_terms: set[str]) -> dict[str, Any]:
    content = str(chunk.get("content") or "")
    chunk_terms = _terms(content)
    matched_terms = sorted(chunk_terms & objective_terms)
    signal_terms = sorted(chunk_terms & SIGNAL_TERMS)
    objective_density = len(matched_terms) / max(1, len(objective_terms)) if objective_terms else 0.0
    exact_bonus = 0.12 if objective_terms and any(term in content.lower() for term in objective_terms) else 0.0
    citation_bonus = 0.08 if chunk.get("citationValid") else 0.0
    input_bonus = min(0.16, _as_float(chunk.get("inputScore"), 0.0) * 0.16)
    signal_bonus = min(0.12, len(signal_terms) * 0.03)
    score = round(min(1.0, 0.12 + objective_density * 0.52 + exact_bonus + citation_bonus + input_bonus + signal_bonus), 3)
    if objective_terms and not matched_terms and not signal_terms:
        score = round(min(score, 0.14 + input_bonus + citation_bonus), 3)
    return {
        **chunk,
        "score": score,
        "matchedObjectiveTerms": matched_terms[:16],
        "matchedSignalTerms": signal_terms[:12],
        "tokenCount": _estimate_tokens(content),
    }


def _compress_text(text: str, *, objective_terms: set[str], token_budget: int) -> str:
    safe_budget = max(24, token_budget)
    sentence_items: list[dict[str, Any]] = []
    for index, sentence in enumerate(_sentences(text)):
        sentence_terms = _terms(sentence)
        overlap = sentence_terms & objective_terms
        signals = sentence_terms & SIGNAL_TERMS
        score = (len(overlap) * 0.22) + (len(signals) * 0.1)
        if index == 0:
            score += 0.05
        sentence_items.append(
            {
                "index": index,
                "text": sentence,
                "score": score,
                "tokenCount": _estimate_tokens(sentence),
            }
        )
    if not sentence_items:
        return _word_clip(text, safe_budget)
    ranked = sorted(sentence_items, key = lambda item: (-float(item["score"]), int(item["index"])))
    selected: list[dict[str, Any]] = []
    used_tokens = 0
    for item in ranked:
        next_count = used_tokens + int(item["tokenCount"])
        if selected and next_count > safe_budget:
            continue
        selected.append(item)
        used_tokens = next_count
        if used_tokens >= safe_budget:
            break
    if not selected:
        selected = [ranked[0]]
    ordered = sorted(selected, key = lambda item: int(item["index"]))
    excerpt = " ".join(str(item["text"]) for item in ordered).strip()
    return _word_clip(excerpt, safe_budget)


def _citation_for_chunk(chunk: dict[str, Any], citation_id: str) -> dict[str, Any]:
    return {
        "id": citation_id,
        "sourceId": chunk.get("sourceId"),
        "chunkId": chunk.get("chunkId"),
        "sourceName": chunk.get("sourceName"),
        "sourceType": chunk.get("sourceType"),
        "page": chunk.get("page"),
        "url": chunk.get("url"),
        "valid": bool(chunk.get("citationValid")),
    }


def build_rag_compression_plan(
    *,
    username: str,
    objective: str,
    chunks: list[dict[str, Any]] | None,
    project_id: str | None = None,
    target_tokens: int = 900,
    max_chunks: int = 6,
    require_citations: bool = True,
) -> dict[str, Any]:
    normalized_chunks = [
        normalized
        for index, chunk in enumerate(chunks or [])
        if isinstance(chunk, dict)
        for normalized in [_normalize_chunk(chunk, index)]
        if normalized is not None
    ]
    objective_terms = _terms(objective)
    safe_target_tokens = min(max(_as_int(target_tokens, 900), 64), 12000)
    safe_max_chunks = min(max(_as_int(max_chunks, 6), 1), 20)
    ranked = [_score_chunk(chunk, objective_terms) for chunk in normalized_chunks]
    ranked.sort(
        key = lambda item: (
            float(item.get("score") or 0.0),
            len(item.get("matchedObjectiveTerms") or []),
            bool(item.get("citationValid")),
            -int(item.get("inputIndex") or 0),
        ),
        reverse = True,
    )
    missing_citation_chunks = [item for item in ranked if not item.get("citationValid")]
    eligible = [item for item in ranked if item.get("citationValid")] if require_citations else ranked

    compressed_chunks: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    context_lines: list[str] = []
    used_tokens = 0
    for candidate in eligible:
        if len(compressed_chunks) >= safe_max_chunks:
            break
        remaining_chunks = max(1, safe_max_chunks - len(compressed_chunks))
        remaining_tokens = max(24, safe_target_tokens - used_tokens)
        chunk_budget = min(360, max(48, remaining_tokens // remaining_chunks))
        compressed_text = _compress_text(
            str(candidate.get("content") or ""),
            objective_terms = objective_terms,
            token_budget = chunk_budget,
        )
        compressed_tokens = _estimate_tokens(compressed_text)
        if compressed_chunks and used_tokens + compressed_tokens > safe_target_tokens:
            continue
        citation_id = f"S{len(compressed_chunks) + 1}"
        citation = _citation_for_chunk(candidate, citation_id)
        citations.append(citation)
        compressed_chunks.append(
            {
                "citationId": citation_id,
                "sourceId": candidate.get("sourceId"),
                "sourceName": candidate.get("sourceName"),
                "sourceType": candidate.get("sourceType"),
                "chunkId": candidate.get("chunkId"),
                "page": candidate.get("page"),
                "score": candidate.get("score"),
                "matchedObjectiveTerms": candidate.get("matchedObjectiveTerms"),
                "matchedSignalTerms": candidate.get("matchedSignalTerms"),
                "contentHash": candidate.get("contentHash"),
                "originalTokenCount": candidate.get("tokenCount"),
                "compressedTokenCount": compressed_tokens,
                "compressionMode": "extractive_sentence_selection",
                "compressedText": compressed_text,
                "citation": citation,
            }
        )
        context_lines.append(f"[{citation_id}] {compressed_text}")
        used_tokens += compressed_tokens

    warnings: list[str] = []
    if not normalized_chunks:
        warnings.append("Aucun chunk RAG fourni pour compression.")
    if missing_citation_chunks:
        warnings.append("Certains chunks RAG n'ont pas de citation source/chunk exploitable.")
    if not compressed_chunks and normalized_chunks:
        warnings.append("Aucun chunk compressible eligible apres application des contraintes de citation.")

    if not normalized_chunks:
        status = "missing_chunks"
    elif require_citations and not eligible:
        status = "blocked_missing_citations"
    elif not compressed_chunks:
        status = "no_relevant_chunks"
    elif missing_citation_chunks and require_citations:
        status = "ready_with_warnings"
    else:
        status = "ready"

    original_token_count = sum(int(item.get("tokenCount") or 0) for item in ranked)
    compressed_token_count = sum(int(item.get("compressedTokenCount") or 0) for item in compressed_chunks)
    reduction_ratio = round(1 - (compressed_token_count / max(1, original_token_count)), 3)
    ready_for_injection = bool(compressed_chunks) and status not in {"missing_chunks", "blocked_missing_citations", "no_relevant_chunks"}
    side_effects = {
        "ragRetrieval": False,
        "ragIndexing": False,
        "vectorSearch": False,
        "embeddingGeneration": False,
        "modelLoad": False,
        "generation": False,
        "networkModelCall": False,
        "sourceMutation": False,
        "cacheWrite": False,
        "compressionWrite": False,
        "auditWrite": False,
    }
    return {
        "ragCompressionVersion": COGNIX_RAG_COMPRESSION_VERSION,
        "citationRetentionVersion": COGNIX_RAG_CITATION_RETENTION_VERSION,
        "extractiveRankerVersion": COGNIX_RAG_EXTRACTIVE_RANKER_VERSION,
        "mode": "deterministic_extractive_rag_compression",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "status": status,
        "readyForInjection": ready_for_injection,
        "targetTokens": safe_target_tokens,
        "maxChunks": safe_max_chunks,
        "ranking": [
            {
                "sourceId": item.get("sourceId"),
                "chunkId": item.get("chunkId"),
                "sourceName": item.get("sourceName"),
                "page": item.get("page"),
                "score": item.get("score"),
                "citationValid": item.get("citationValid"),
                "matchedObjectiveTerms": item.get("matchedObjectiveTerms"),
                "matchedSignalTerms": item.get("matchedSignalTerms"),
                "tokenCount": item.get("tokenCount"),
                "contentHash": item.get("contentHash"),
            }
            for item in ranked
        ],
        "selectedChunkIds": [str(item.get("chunkId")) for item in compressed_chunks],
        "compressedChunks": compressed_chunks,
        "citations": citations,
        "contextBlock": "\n\n".join(context_lines),
        "citationContract": {
            "citationRetentionRequired": True,
            "requireCitations": require_citations,
            "requiresSourceId": True,
            "requiresChunkId": True,
            "pageRecommended": True,
            "noUncitedClaims": True,
            "validCitationCount": sum(1 for item in citations if item.get("valid")),
            "missingCitationCount": len(missing_citation_chunks),
            "missingCitationChunkIds": [str(item.get("chunkId")) for item in missing_citation_chunks[:20]],
            "answerInstruction": "Use compressed chunks only for source-grounded claims and cite them with [S#].",
        },
        "summary": {
            "inputChunkCount": len(normalized_chunks),
            "rankedChunkCount": len(ranked),
            "selectedChunkCount": len(compressed_chunks),
            "citationCount": len(citations),
            "originalTokenCount": original_token_count,
            "compressedTokenCount": compressed_token_count,
            "targetTokenCount": safe_target_tokens,
            "reductionRatio": reduction_ratio,
            "status": status,
        },
        "warnings": warnings,
        "sideEffects": side_effects,
    }
