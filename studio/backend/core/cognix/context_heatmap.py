# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX context heatmap planning.

The heatmap scores context chunks from deterministic usage signals. It never
deletes memories, archives data, calls models, or rewrites project context.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_CONTEXT_USAGE_TRACKER_VERSION = "cognix_context_usage_tracker_v1"
COGNIX_CONTEXT_HEATMAP_GENERATOR_VERSION = "cognix_context_heatmap_generator_v1"
COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION = "cognix_memory_garbage_collector_v1"
COGNIX_MEMORY_CONFLICT_RESOLVER_VERSION = "cognix_memory_conflict_resolver_v1"

SOURCE_IMPORTANCE_BONUS = {
    "project_memory": 0.16,
    "memory": 0.14,
    "document": 0.09,
    "code": 0.08,
    "chat": 0.02,
    "old_message": -0.08,
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, parsed)


def _as_int(value: Any, default: int = 0, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _keywords(text: str) -> set[str]:
    return {
        item.casefold()
        for item in re.findall(r"[a-zA-Z0-9_+-]{4,}", text or "")
        if item.casefold() not in {"avec", "dans", "pour", "that", "this", "from", "have", "will", "context"}
    }


def _chunk_id(chunk: dict[str, Any], index: int) -> str:
    return str(chunk.get("chunkId") or chunk.get("id") or chunk.get("sourceId") or f"chunk_{index}")[:180]


def _memory_id(memory: dict[str, Any], index: int) -> str:
    return str(memory.get("memoryId") or memory.get("id") or memory.get("sourceId") or f"memory_{index}")[:180]


def _memory_text(memory: dict[str, Any]) -> str:
    return _normalize(
        memory.get("content")
        or memory.get("text")
        or memory.get("summary")
        or memory.get("value")
        or ""
    )


def _usage_lookup(response_usage: list[dict[str, Any]] | None) -> dict[str, dict[str, int]]:
    lookup: dict[str, dict[str, int]] = {}
    for usage in response_usage or []:
        if not isinstance(usage, dict):
            continue
        chunk_id = str(usage.get("chunkId") or usage.get("id") or usage.get("sourceId") or "").strip()
        if not chunk_id:
            continue
        current = lookup.setdefault(
            chunk_id,
            {"usageCount": 0, "responseCount": 0, "citationCount": 0, "copiedTermCount": 0},
        )
        current["usageCount"] += _as_int(usage.get("usageCount"), 1, minimum = 0)
        current["responseCount"] += _as_int(usage.get("responseCount"), 1, minimum = 0)
        current["citationCount"] += _as_int(usage.get("citationCount"), 0, minimum = 0)
        current["copiedTermCount"] += _as_int(usage.get("copiedTermCount"), 0, minimum = 0)
    return lookup


def build_memory_cleanup_blueprint() -> dict[str, Any]:
    return {
        "memoryGarbageCollectorVersion": COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION,
        "memoryConflictResolverVersion": COGNIX_MEMORY_CONFLICT_RESOLVER_VERSION,
        "usageTrackerVersion": COGNIX_CONTEXT_USAGE_TRACKER_VERSION,
        "mode": "dry_run_memory_cleanup",
        "services": ["MemoryGarbageCollector", "MemoryConflictResolver", "MemoryUsageTracker"],
        "pipeline": ["memory_scan", "duplicate_detection", "staleness_score", "conflict_detection", "cleanup_proposal"],
        "proposalTypes": ["archive", "merge", "deprioritize", "review_conflict", "keep"],
        "reviewPolicy": {
            "reviewBeforeDelete": True,
            "rollbackRequired": True,
            "permanentDeleteAllowedHere": False,
            "automaticCleanupStartsNow": False,
        },
        "sideEffects": {
            "memoryScan": False,
            "suggestionWrite": False,
            "conflictWrite": False,
            "memoryArchive": False,
            "memoryDelete": False,
            "permanentDelete": False,
            "memoryMerge": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_context_heatmap_blueprint() -> dict[str, Any]:
    return {
        "usageTrackerVersion": COGNIX_CONTEXT_USAGE_TRACKER_VERSION,
        "heatmapGeneratorVersion": COGNIX_CONTEXT_HEATMAP_GENERATOR_VERSION,
        "memoryGarbageCollectorVersion": COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION,
        "mode": "dry_run_context_heatmap",
        "services": ["ContextUsageTracker", "HeatmapGenerator", "MemoryGarbageCollector"],
        "pipeline": ["context_chunks", "response_usage", "utility_score", "heatmap"],
        "buckets": [
            {"id": "very_useful", "label": "Contexte tres utile", "themeToken": "success"},
            {"id": "low_usage", "label": "Contexte peu utilise", "themeToken": "warning"},
            {"id": "archive_candidate", "label": "Contexte a archiver", "themeToken": "muted"},
        ],
        "policies": {
            "automaticArchiveAllowed": False,
            "automaticDeleteAllowed": False,
            "frontendDirectMemoryMutationAllowed": False,
            "themeAwareTokensOnly": True,
        },
        "sideEffects": {
            "usageStatsWrite": False,
            "heatmapEntryWrite": False,
            "memoryArchive": False,
            "memoryDelete": False,
            "contextMutation": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def _memory_usage_for(memory: dict[str, Any], usage_lookup: dict[str, dict[str, int]], memory_id: str) -> dict[str, int]:
    usage = usage_lookup.get(memory_id, {})
    return {
        "usageCount": _as_int(memory.get("usageCount"), 0, minimum = 0) + usage.get("usageCount", 0),
        "responseCount": _as_int(memory.get("responseCount"), 0, minimum = 0) + usage.get("responseCount", 0),
        "citationCount": _as_int(memory.get("citationCount"), 0, minimum = 0) + usage.get("citationCount", 0),
    }


def _cleanup_suggestion(
    *,
    memory_id: str,
    title: str,
    category: str,
    reason_code: str,
    recommended_action: str,
    confidence: float,
    detail: str,
    duplicate_of: str | None = None,
    conflict_id: str | None = None,
) -> dict[str, Any]:
    return {
        "memoryId": memory_id,
        "title": title[:180],
        "category": category[:80],
        "reasonCode": reason_code,
        "recommendedAction": recommended_action,
        "confidence": round(max(0.0, min(confidence, 0.99)), 2),
        "detail": detail[:1000],
        "duplicateOf": duplicate_of,
        "conflictId": conflict_id,
        "requiresReview": True,
        "rollbackPlan": {
            "snapshotBeforeChange": True,
            "restoreAction": "reactivate_previous_memory_version",
            "permanentDeleteAllowed": False,
        },
    }


def build_memory_cleanup_plan(
    *,
    username: str,
    memories: list[dict[str, Any]],
    usage_entries: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    usage_lookup = _usage_lookup(usage_entries)
    normalized_memories: list[dict[str, Any]] = []
    for index, memory in enumerate(memories or []):
        if not isinstance(memory, dict):
            continue
        memory_id = _memory_id(memory, index)
        text = _memory_text(memory)
        title = _normalize(memory.get("title") or memory.get("label") or memory_id)[:180]
        category = _normalize(memory.get("category") or memory.get("scope") or "general").casefold().replace(" ", "_")
        normalized_memories.append(
            {
                "memoryId": memory_id,
                "title": title,
                "category": category,
                "text": text,
                "keywords": _keywords(text + " " + title),
                "ageDays": _as_int(memory.get("ageDays"), 0, minimum = 0, maximum = 3650),
                "status": _normalize(memory.get("status") or "active"),
                "preferenceKey": _normalize(memory.get("preferenceKey") or memory.get("key") or title).casefold(),
                "usage": _memory_usage_for(memory, usage_lookup, memory_id),
            }
        )

    suggestions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_text: dict[str, str] = {}
    by_preference: dict[str, list[dict[str, Any]]] = {}

    for memory in normalized_memories:
        text_key = re.sub(r"[^a-z0-9]+", "", memory["text"].casefold())[:400]
        if text_key and text_key in seen_text:
            suggestions.append(
                _cleanup_suggestion(
                    memory_id = memory["memoryId"],
                    title = memory["title"],
                    category = memory["category"],
                    reason_code = "duplicate_memory",
                    recommended_action = "merge",
                    confidence = 0.91,
                    detail = "Memoire quasi identique a une entree existante; proposer une fusion avec revue.",
                    duplicate_of = seen_text[text_key],
                )
            )
        elif text_key:
            seen_text[text_key] = memory["memoryId"]

        usage_count = memory["usage"]["usageCount"] + memory["usage"]["responseCount"] + memory["usage"]["citationCount"]
        if memory["ageDays"] >= 90 and usage_count == 0:
            suggestions.append(
                _cleanup_suggestion(
                    memory_id = memory["memoryId"],
                    title = memory["title"],
                    category = memory["category"],
                    reason_code = "stale_unused_memory",
                    recommended_action = "archive",
                    confidence = 0.78,
                    detail = "Memoire ancienne sans usage recent; archiver apres validation humaine.",
                )
            )
        elif memory["ageDays"] >= 45 and usage_count <= 1:
            suggestions.append(
                _cleanup_suggestion(
                    memory_id = memory["memoryId"],
                    title = memory["title"],
                    category = memory["category"],
                    reason_code = "low_usage_memory",
                    recommended_action = "deprioritize",
                    confidence = 0.64,
                    detail = "Memoire peu utilisee; reduire son poids plutot que supprimer.",
                )
            )

        by_preference.setdefault(memory["preferenceKey"], []).append(memory)

    for key, group in by_preference.items():
        active_group = [item for item in group if item["status"] != "deleted"]
        text_values = {item["text"].casefold() for item in active_group if item["text"]}
        if len(active_group) > 1 and len(text_values) > 1:
            conflict_id = f"conflict_{abs(hash((username, key))) % 1_000_000_000}"
            conflicts.append(
                {
                    "conflictId": conflict_id,
                    "memoryIds": [item["memoryId"] for item in active_group],
                    "conflictType": "contradictory_preference",
                    "preferenceKey": key,
                    "summary": "Plusieurs memoires actives semblent decrire la meme preference avec un contenu different.",
                    "requiresReview": True,
                    "rollbackRequired": True,
                }
            )
            for item in active_group:
                suggestions.append(
                    _cleanup_suggestion(
                        memory_id = item["memoryId"],
                        title = item["title"],
                        category = item["category"],
                        reason_code = "conflicting_memory",
                        recommended_action = "review_conflict",
                        confidence = 0.82,
                        detail = "Memoire en conflit avec une autre entree active; choisir la version fiable avant nettoyage.",
                        conflict_id = conflict_id,
                    )
                )

    deduped: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for suggestion in suggestions:
        key = (suggestion["memoryId"], suggestion["reasonCode"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        deduped.append(suggestion)

    archive_count = sum(1 for item in deduped if item["recommendedAction"] == "archive")
    merge_count = sum(1 for item in deduped if item["recommendedAction"] == "merge")
    conflict_count = len(conflicts)
    return {
        "memoryGarbageCollectorVersion": COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION,
        "memoryConflictResolverVersion": COGNIX_MEMORY_CONFLICT_RESOLVER_VERSION,
        "usageTrackerVersion": COGNIX_CONTEXT_USAGE_TRACKER_VERSION,
        "mode": "dry_run_memory_cleanup",
        "username": username,
        "projectId": project_id,
        "suggestions": deduped,
        "conflicts": conflicts,
        "summary": {
            "memoryCount": len(normalized_memories),
            "suggestionCount": len(deduped),
            "archiveCandidateCount": archive_count,
            "mergeCandidateCount": merge_count,
            "conflictCount": conflict_count,
            "reviewMessage": f"J'ai trouve {len(deduped)} memoires a revoir. Nettoyer ?",
            "automaticCleanupWillRun": False,
        },
        "reviewPolicy": build_memory_cleanup_blueprint()["reviewPolicy"],
        "sideEffects": build_memory_cleanup_blueprint()["sideEffects"],
    }


def _entry_bucket(score: float, *, age_days: int, source_type: str) -> dict[str, str]:
    if score >= 0.70:
        return {
            "bucket": "very_useful",
            "label": "Contexte tres utile",
            "recommendedAction": "keep",
            "themeToken": "success",
        }
    if score >= 0.38:
        return {
            "bucket": "low_usage",
            "label": "Contexte peu utilise",
            "recommendedAction": "review",
            "themeToken": "warning",
        }
    archive = age_days >= 30 or source_type == "old_message"
    return {
        "bucket": "archive_candidate",
        "label": "Contexte a archiver",
        "recommendedAction": "archive" if archive else "deprioritize",
        "themeToken": "muted",
    }


def _score_chunk(
    chunk: dict[str, Any],
    *,
    usage: dict[str, int],
    objective_terms: set[str],
) -> dict[str, Any]:
    text = _normalize(chunk.get("text") or chunk.get("content") or chunk.get("summary") or "")
    title = _normalize(chunk.get("title") or chunk.get("label") or chunk.get("sourceId") or "Context chunk")[:160]
    source_type = _normalize(chunk.get("sourceType") or chunk.get("type") or "context").casefold().replace(" ", "_")
    source_id = _normalize(chunk.get("sourceId") or chunk.get("id") or title)[:180]
    age_days = _as_int(chunk.get("ageDays"), 0, minimum = 0, maximum = 3650)
    usage_count = _as_int(chunk.get("usageCount"), 0, minimum = 0) + usage.get("usageCount", 0)
    response_count = _as_int(chunk.get("responseCount"), 0, minimum = 0) + usage.get("responseCount", 0)
    citation_count = _as_int(chunk.get("citationCount"), 0, minimum = 0) + usage.get("citationCount", 0)
    copied_term_count = _as_int(chunk.get("copiedTermCount"), 0, minimum = 0) + usage.get("copiedTermCount", 0)
    overlap = sorted((_keywords(text) | _keywords(title)) & objective_terms)[:12]
    recency_score = max(0.0, 1.0 - (age_days / 120.0))
    source_bonus = SOURCE_IMPORTANCE_BONUS.get(source_type, 0.0)
    base = 0.08 if usage_count == 0 and response_count == 0 else 0.18
    score = (
        base
        + min(0.28, usage_count * 0.07)
        + min(0.20, response_count * 0.05)
        + min(0.14, citation_count * 0.07)
        + min(0.12, copied_term_count * 0.03)
        + min(0.16, len(overlap) * 0.04)
        + (recency_score * 0.10)
        + source_bonus
    )
    score = round(min(max(score, 0.0), 1.0), 3)
    bucket = _entry_bucket(score, age_days = age_days, source_type = source_type)
    return {
        "chunkId": "",
        "sourceType": source_type,
        "sourceId": source_id,
        "title": title,
        "utilityScore": score,
        "usageCount": usage_count,
        "responseCount": response_count,
        "citationCount": citation_count,
        "copiedTermCount": copied_term_count,
        "ageDays": age_days,
        "matchedObjectiveTerms": overlap,
        **bucket,
        "signals": {
            "recencyScore": round(recency_score, 3),
            "sourceImportanceBonus": round(source_bonus, 3),
            "objectiveOverlapCount": len(overlap),
        },
        "sideEffects": build_context_heatmap_blueprint()["sideEffects"],
    }


def build_context_heatmap_plan(
    *,
    username: str,
    context_chunks: list[dict[str, Any]],
    response_usage: list[dict[str, Any]] | None = None,
    objective: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    objective_terms = _keywords(objective or "")
    usage = _usage_lookup(response_usage)
    entries: list[dict[str, Any]] = []
    for index, chunk in enumerate(context_chunks or []):
        if not isinstance(chunk, dict):
            continue
        chunk_id = _chunk_id(chunk, index)
        entry = _score_chunk(chunk, usage = usage.get(chunk_id, {}), objective_terms = objective_terms)
        entry["chunkId"] = chunk_id
        entries.append(entry)
    entries.sort(key = lambda item: (-float(item["utilityScore"]), item["bucket"], item["title"]))
    bucket_counts = {
        "very_useful": sum(1 for item in entries if item["bucket"] == "very_useful"),
        "low_usage": sum(1 for item in entries if item["bucket"] == "low_usage"),
        "archive_candidate": sum(1 for item in entries if item["bucket"] == "archive_candidate"),
    }
    archive_candidates = [item for item in entries if item["bucket"] == "archive_candidate"]
    return {
        "usageTrackerVersion": COGNIX_CONTEXT_USAGE_TRACKER_VERSION,
        "heatmapGeneratorVersion": COGNIX_CONTEXT_HEATMAP_GENERATOR_VERSION,
        "memoryGarbageCollectorVersion": COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION,
        "mode": "dry_run_context_heatmap",
        "username": username,
        "projectId": project_id,
        "objective": objective,
        "entries": entries,
        "summary": {
            "chunkCount": len(entries),
            "bucketCounts": bucket_counts,
            "averageUtilityScore": round(sum(float(item["utilityScore"]) for item in entries) / max(1, len(entries)), 3),
            "archiveCandidateCount": len(archive_candidates),
            "automaticArchiveWillRun": False,
        },
        "garbageCollectorPlan": {
            "candidateChunkIds": [item["chunkId"] for item in archive_candidates],
            "recommendedAction": "review_before_archive" if archive_candidates else "none",
            "automaticArchiveAllowed": False,
            "automaticDeleteAllowed": False,
            "requiresHumanConfirmation": bool(archive_candidates),
        },
        "display": {
            "showOnlyWhenUseful": True,
            "themeAwareTokensOnly": True,
            "legend": build_context_heatmap_blueprint()["buckets"],
        },
        "sideEffects": build_context_heatmap_blueprint()["sideEffects"],
    }
