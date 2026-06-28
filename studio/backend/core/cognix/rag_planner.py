# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native RAG planning.

The planner decides how CogniX should use documents and sources before any
retrieval, embedding, indexing, or model call happens.
"""

from __future__ import annotations

from typing import Any


COGNIX_RAG_PLANNER_VERSION = "cognix_rag_planner_v1"

SUPPORTED_SOURCE_TYPES = {"pdf", "docx", "txt", "md", "csv", "html", "url", "knowledge_base"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _source_checks(sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not sources:
        return {
            "status": "missing",
            "ready": False,
            "sourceCount": 0,
            "indexedSourceCount": 0,
            "estimatedChunkCount": 0,
            "checks": [
                {
                    "id": "sources_present",
                    "status": "missing",
                    "severity": "error",
                    "detail": "No RAG source metadata supplied.",
                }
            ],
            "warnings": ["Aucune source RAG declaree."],
        }

    checks: list[dict[str, Any]] = []
    indexed_count = 0
    estimated_chunks = 0
    warnings: list[str] = []

    for index, source in enumerate(sources):
        source_id = str(source.get("id") or source.get("name") or f"source-{index + 1}")
        source_type = str(source.get("type") or source.get("kind") or "unknown").strip().lower()
        indexed = bool(source.get("indexed") or source.get("isIndexed"))
        chunk_count = _as_int(source.get("chunkCount") or source.get("numChunks"))
        estimated_chunks += chunk_count
        if indexed:
            indexed_count += 1

        if source_type not in SUPPORTED_SOURCE_TYPES:
            checks.append(
                {
                    "id": "source_type_supported",
                    "sourceId": source_id,
                    "status": "warning",
                    "severity": "warning",
                    "detail": source_type,
                }
            )
            warnings.append(f"Type source non confirme: {source_type or 'unknown'}")
        if not indexed:
            checks.append(
                {
                    "id": "source_indexed",
                    "sourceId": source_id,
                    "status": "planned",
                    "severity": "warning",
                    "detail": "Source pas encore indexee.",
                }
            )
        if bool(source.get("containsSensitiveData")):
            checks.append(
                {
                    "id": "sensitive_source",
                    "sourceId": source_id,
                    "status": "warning",
                    "severity": "warning",
                    "detail": "Source marquee sensible.",
                }
            )
            warnings.append("Source sensible: appliquer permissions et citations strictes.")

    ready = indexed_count > 0
    if indexed_count == 0:
        warnings.append("Aucune source indexee: planifier l'indexation avant retrieval.")
    return {
        "status": "ready" if ready and not warnings else "ready_with_warnings" if ready else "needs_indexing",
        "ready": ready,
        "sourceCount": len(sources),
        "indexedSourceCount": indexed_count,
        "estimatedChunkCount": estimated_chunks,
        "checks": checks,
        "warnings": warnings,
    }


def _context_budget(task_strategy: dict[str, Any], recommendation: dict[str, Any]) -> dict[str, Any]:
    memory_fit = _as_dict(recommendation.get("memoryFit"))
    level = str(memory_fit.get("level") or "unknown")
    if level == "tight":
        max_context_tokens = 1800
        chunk_budget = 4
    elif task_strategy.get("path") == "rag_first":
        max_context_tokens = 3200
        chunk_budget = 8
    else:
        max_context_tokens = 2200
        chunk_budget = 5
    return {
        "maxContextTokens": max_context_tokens,
        "maxChunks": chunk_budget,
        "compression": "summarize_then_cite" if chunk_budget <= 5 else "rank_then_compress",
        "rawHistoryAllowed": False,
    }


def _recommended_path(task_strategy: dict[str, Any]) -> str:
    if task_strategy.get("path") == "rag_first":
        return "rag_first"
    if _as_dict(task_strategy.get("uses")).get("rag"):
        return "rag_first"
    return "no_rag_needed"


def build_rag_plan(
    *,
    objective: str,
    project_id: str | None,
    classification: dict[str, Any],
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    sources: list[dict[str, Any]] | None = None,
    rag_available: bool | None = None,
) -> dict[str, Any]:
    normalized_sources = [
        item for item in _as_list(sources) if isinstance(item, dict)
    ]
    source_result = _source_checks(normalized_sources)
    path = _recommended_path(task_strategy)
    budget = _context_budget(task_strategy, recommendation)
    rag_ready = bool(source_result["ready"]) and (rag_available is not False)

    blocked_actions = [
        {
            "id": "rag_indexing",
            "reason": "Aucune indexation n'est lancee pendant la planification CogniX.",
        },
        {
            "id": "embedding_generation",
            "reason": "Aucun embedding n'est calcule dans ce plan dry-run.",
        },
        {
            "id": "retrieval_query",
            "reason": "Aucune recherche dense/hybride n'est executee pendant la planification.",
        },
    ]
    if rag_available is False:
        blocked_actions.append(
            {
                "id": "rag_runtime",
                "reason": "RAG indisponible: sqlite-vec ou store RAG non disponible.",
            }
        )

    warnings: list[str] = list(source_result.get("warnings") or [])
    if path == "rag_first" and not rag_ready:
        warnings.append("RAG recommande mais sources pas encore pretes.")
    if path == "no_rag_needed":
        warnings.append("Aucun signal documentaire dominant: RAG reste optionnel.")
    if rag_available is False:
        warnings.append("RAG backend indisponible sur cette installation.")

    retrieval_strategy = "hybrid"
    if source_result["estimatedChunkCount"] and source_result["estimatedChunkCount"] < 10:
        retrieval_strategy = "lexical"
    if classification.get("needsClarification"):
        retrieval_strategy = "defer_until_clarified"

    return {
        "plannerVersion": COGNIX_RAG_PLANNER_VERSION,
        "mode": "dry_run",
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "projectId": project_id,
        "recommendedPath": path,
        "ragAvailable": rag_available,
        "readyForRetrieval": rag_ready and path == "rag_first",
        "targetDomain": classification.get("selectedDomain") or "general",
        "sourceReadiness": source_result,
        "retrieval": {
            "strategy": retrieval_strategy,
            "topK": budget["maxChunks"],
            "minScore": 0.18 if retrieval_strategy == "hybrid" else 0.0,
            "includeCitations": True,
            "deduplicateSources": True,
            "rerank": source_result["estimatedChunkCount"] >= 20,
        },
        "contextBudget": budget,
        "blockedActions": blocked_actions,
        "warnings": warnings,
        "reason": (
            "RAG recommande: preparer sources, retrieval hybride, compression et citations."
            if path == "rag_first"
            else "RAG optionnel: la demande ne depend pas principalement de documents."
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "ragIndexing": False,
            "embeddingGeneration": False,
            "retrievalQuery": False,
            "sourceMutation": False,
        },
    }
