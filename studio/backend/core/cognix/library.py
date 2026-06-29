# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Library asset planning, search, and metadata contracts."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any


COGNIX_LIBRARY_VERSION = "cognix_library_v1"
COGNIX_LIBRARY_METADATA_VERSION = "cognix_library_metadata_extractor_v1"
COGNIX_LIBRARY_SEARCH_VERSION = "cognix_library_search_v1"

LIBRARY_ASSET_TYPES: tuple[str, ...] = (
    "document",
    "dataset",
    "model",
    "lora_adapter",
    "image",
    "prompt",
    "persona",
    "workflow",
    "report",
    "app",
    "plugin",
    "skill",
    "directive",
    "file",
    "video",
    "other",
)

RAG_ELIGIBLE_TYPES = {"document", "dataset", "report", "prompt", "skill", "directive", "file"}
TEXTUAL_TYPES = {"document", "dataset", "prompt", "persona", "workflow", "report", "skill", "directive", "file"}


def _normalize(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _tags(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("tags")
    if isinstance(raw, list):
        return [_normalize(item, limit = 60) for item in raw if _normalize(item, limit = 60)][:16]
    if isinstance(raw, str):
        return [_normalize(item, limit = 60) for item in raw.split(",") if _normalize(item, limit = 60)][:16]
    return []


def _extension(name: str, uri: str | None = None) -> str | None:
    candidate = uri or name
    suffix = PurePosixPath(str(candidate or "")).suffix.lower().lstrip(".")
    return suffix or None


def _asset_family(kind: str) -> str:
    if kind in {"document", "dataset", "report", "file"}:
        return "knowledge"
    if kind in {"model", "lora_adapter"}:
        return "modeling"
    if kind in {"prompt", "persona", "skill", "directive", "workflow"}:
        return "behavior"
    if kind in {"image", "video"}:
        return "media"
    if kind in {"app", "plugin"}:
        return "integration"
    return "general"


def _safe_kind(kind: Any) -> str:
    normalized = _normalize(kind, limit = 80)
    return normalized if normalized in LIBRARY_ASSET_TYPES else "other"


def build_library_blueprint() -> dict[str, Any]:
    return {
        "libraryVersion": COGNIX_LIBRARY_VERSION,
        "metadataExtractorVersion": COGNIX_LIBRARY_METADATA_VERSION,
        "searchVersion": COGNIX_LIBRARY_SEARCH_VERSION,
        "mode": "local_asset_library_contract",
        "services": [
            "LibraryService",
            "LibraryAssetService",
            "AssetMetadataExtractor",
            "AssetPermissionService",
            "LibrarySearchService",
        ],
        "assetTypes": list(LIBRARY_ASSET_TYPES),
        "permissions": ["library:read", "library:write", "library:share", "library:delete", "library:admin"],
        "searchContract": {
            "query": True,
            "kindFilter": True,
            "sourceFilter": True,
            "facets": ["kind", "source", "assetFamily", "ragCandidate"],
            "crossUserSearchAllowed": False,
        },
        "indexingPolicy": {
            "ragEligibleTypes": sorted(RAG_ELIGIBLE_TYPES),
            "autoIndexNow": False,
            "queueRequired": True,
            "permissionCheckRequired": True,
        },
        "displayContract": {
            "cards": True,
            "tableView": True,
            "filters": True,
            "searchBar": True,
            "modelHubCompatible": True,
            "designSystemOnly": True,
        },
        "sideEffects": {
            "assetWrite": False,
            "metadataWrite": False,
            "indexWrite": False,
            "ragIndexWrite": False,
            "permissionWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
            "crossUserRead": False,
        },
    }


def normalize_library_asset(item: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(item.get("metadata") or item.get("metadata_json") or item.get("metadataJson"))
    kind = _safe_kind(item.get("kind"))
    name = _normalize(item.get("name"), limit = 240) or "Asset CogniX"
    source = _normalize(item.get("source"), limit = 80) or "manual"
    uri = _normalize(item.get("uri"), limit = 2000) or None
    extension = _extension(name, uri)
    tags = _tags(metadata)
    family = _asset_family(kind)
    return {
        "id": _normalize(item.get("id"), limit = 180),
        "kind": kind,
        "name": name,
        "source": source,
        "sizeBytes": item.get("size_bytes") if item.get("size_bytes") is not None else item.get("sizeBytes"),
        "uri": uri,
        "createdAt": item.get("created_at") or item.get("createdAt"),
        "updatedAt": item.get("updated_at") or item.get("updatedAt"),
        "metadata": metadata,
        "tags": tags,
        "classification": {
            "assetFamily": family,
            "extension": extension,
            "textual": kind in TEXTUAL_TYPES,
            "ragCandidate": kind in RAG_ELIGIBLE_TYPES,
            "datasetCandidate": kind in {"document", "dataset", "report", "file"},
        },
        "permissionScope": metadata.get("permissionScope") or "user_private",
        "projectId": metadata.get("projectId") or metadata.get("project_id"),
        "searchText": " ".join(
            [
                name.lower(),
                kind.lower(),
                source.lower(),
                family.lower(),
                " ".join(tag.lower() for tag in tags),
            ]
        ).strip(),
    }


def summarize_library(items: list[dict[str, Any]]) -> dict[str, Any]:
    assets = [normalize_library_asset(item) for item in items]
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_family: dict[str, int] = {}
    rag_candidates = 0
    total_size = 0
    for asset in assets:
        by_kind[asset["kind"]] = by_kind.get(asset["kind"], 0) + 1
        by_source[asset["source"]] = by_source.get(asset["source"], 0) + 1
        family = asset["classification"]["assetFamily"]
        by_family[family] = by_family.get(family, 0) + 1
        if asset["classification"]["ragCandidate"]:
            rag_candidates += 1
        try:
            total_size += int(asset.get("sizeBytes") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "libraryVersion": COGNIX_LIBRARY_VERSION,
        "assetCount": len(assets),
        "ragCandidateCount": rag_candidates,
        "totalSizeBytes": total_size,
        "byKind": by_kind,
        "bySource": by_source,
        "byFamily": by_family,
        "sideEffects": build_library_blueprint()["sideEffects"],
    }


def search_library_assets(
    *,
    items: list[dict[str, Any]],
    query: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    safe_query = _normalize(query, limit = 240).lower()
    safe_kind = _safe_kind(kind) if kind else None
    safe_source = _normalize(source, limit = 80).lower() if source else None
    assets = [normalize_library_asset(item) for item in items]
    matches = []
    for asset in assets:
        if safe_kind and asset["kind"] != safe_kind:
            continue
        if safe_source and asset["source"].lower() != safe_source:
            continue
        if safe_query and safe_query not in asset["searchText"]:
            continue
        score = 1.0
        if safe_query and asset["name"].lower().startswith(safe_query):
            score = 1.25
        elif safe_query and safe_query in asset["name"].lower():
            score = 1.1
        match = dict(asset)
        match["relevanceScore"] = round(score, 3)
        matches.append(match)
    matches.sort(key = lambda item: (item["relevanceScore"], str(item.get("createdAt") or "")), reverse = True)
    safe_limit = max(1, min(int(limit or 80), 200))
    return {
        "libraryVersion": COGNIX_LIBRARY_VERSION,
        "searchVersion": COGNIX_LIBRARY_SEARCH_VERSION,
        "query": query or "",
        "filters": {"kind": safe_kind, "source": source},
        "summary": summarize_library(items),
        "matches": matches[:safe_limit],
        "totalMatches": len(matches),
        "sideEffects": build_library_blueprint()["sideEffects"],
    }


def build_library_asset_plan(
    *,
    username: str,
    kind: str,
    name: str,
    source: str = "manual",
    size_bytes: int | None = None,
    uri: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_kind = _safe_kind(kind)
    safe_name = _normalize(name, limit = 240) or "Asset CogniX"
    safe_source = _normalize(source, limit = 80) or "manual"
    clean_metadata = _metadata(metadata)
    extension = _extension(safe_name, uri)
    family = _asset_family(safe_kind)
    tags = _tags(clean_metadata)
    rag_candidate = safe_kind in RAG_ELIGIBLE_TYPES
    return {
        "libraryVersion": COGNIX_LIBRARY_VERSION,
        "metadataExtractorVersion": COGNIX_LIBRARY_METADATA_VERSION,
        "mode": "asset_write_plan",
        "username": username,
        "asset": {
            "kind": safe_kind,
            "name": safe_name,
            "source": safe_source,
            "sizeBytes": size_bytes,
            "uri": uri,
            "metadata": {
                **clean_metadata,
                "assetFamily": family,
                "extension": extension,
                "tags": tags,
                "ragCandidate": rag_candidate,
                "datasetCandidate": safe_kind in {"document", "dataset", "report", "file"},
            },
        },
        "classification": {
            "assetFamily": family,
            "extension": extension,
            "textual": safe_kind in TEXTUAL_TYPES,
            "ragCandidate": rag_candidate,
            "datasetCandidate": safe_kind in {"document", "dataset", "report", "file"},
        },
        "indexingPlan": {
            "eligible": rag_candidate,
            "queueRequired": rag_candidate,
            "indexNow": False,
            "target": "rag" if rag_candidate else "library_metadata",
        },
        "permissionPlan": {
            "ownerUsername": username,
            "scope": clean_metadata.get("permissionScope") or "user_private",
            "shareNow": False,
            "adminReviewRequired": False,
        },
        "sideEffects": build_library_blueprint()["sideEffects"],
    }
