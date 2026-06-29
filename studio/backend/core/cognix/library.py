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
COGNIX_MODEL_LIBRARY_REGISTRATION_VERSION = "cognix_model_library_registration_v1"

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
MODEL_ASSET_TYPES = {"model", "lora_adapter"}
MODEL_EVALUATION_PASS_VALUES = {"passed", "approved", "ready", "ready_for_library", "accepted"}
SENSITIVE_METADATA_MARKERS = (
    "secret",
    "token",
    "password",
    "rawpreview",
    "raw_preview",
    "privatekey",
    "private_key",
    "api_key",
)


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


def _sanitize_metadata(value: Any) -> dict[str, Any]:
    metadata = _metadata(value)
    sanitized: dict[str, Any] = {}
    redacted_keys: list[str] = []
    for key, item in metadata.items():
        key_text = str(key)
        normalized = key_text.replace("-", "_").casefold()
        if any(marker in normalized for marker in SENSITIVE_METADATA_MARKERS):
            redacted_keys.append(key_text[:80])
            continue
        sanitized[key_text] = item
    if redacted_keys:
        sanitized["redactedMetadataKeys"] = redacted_keys[:16]
    return sanitized


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


def _metadata_bool(metadata: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().casefold() in {"true", "yes", "1", "approved", "passed"}:
            return True
    return False


def _metadata_text(metadata: dict[str, Any], *keys: str, limit: int = 240) -> str:
    for key in keys:
        value = _normalize(metadata.get(key), limit = limit)
        if value:
            return value
    return ""


def _registration_gate(
    *,
    gate_id: str,
    status: str,
    severity: str,
    reason: str,
    detail: Any = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": status,
        "severity": severity,
        "reason": reason,
        "detail": detail,
    }


def build_model_library_registration_gate(*, kind: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    safe_kind = _safe_kind(kind)
    clean_metadata = _sanitize_metadata(metadata)
    required = safe_kind in MODEL_ASSET_TYPES
    if not required:
        return {
            "gateVersion": COGNIX_MODEL_LIBRARY_REGISTRATION_VERSION,
            "required": False,
            "status": "not_required",
            "readyForLibraryWrite": True,
            "blockedGateIds": [],
            "warningGateIds": [],
            "gates": [],
            "sideEffects": {
                "evaluationJob": False,
                "modelLoad": False,
                "modelRegistryWrite": False,
                "networkCall": False,
            },
        }

    artifact_ref = _metadata_text(clean_metadata, "artifactId", "adapterRef", "modelId", "uri")
    evaluation_report_ref = _metadata_text(clean_metadata, "evaluationReportRef", "evalReportRef", "evaluation_report_ref")
    evaluation_status = _metadata_text(clean_metadata, "evaluationStatus", "evalStatus", "evaluation_status", limit = 80).casefold()
    evaluation_plan_version = _metadata_text(clean_metadata, "evaluationPlanVersion", "evaluation_plan_version", limit = 160)
    safety_review_passed = _metadata_bool(clean_metadata, "safetyReviewPassed", "safety_review_passed")
    human_approved = _metadata_bool(clean_metadata, "humanApproved", "humanApproval", "human_approved")

    gates = [
        _registration_gate(
            gate_id = "artifact_declared",
            status = "pass" if artifact_ref else "blocked",
            severity = "info" if artifact_ref else "error",
            reason = "Model artifact reference is declared." if artifact_ref else "A model or adapter artifact reference is required.",
            detail = artifact_ref or None,
        ),
        _registration_gate(
            gate_id = "evaluation_report_declared",
            status = "pass" if evaluation_report_ref else "blocked",
            severity = "info" if evaluation_report_ref else "error",
            reason = "Evaluation report reference is declared." if evaluation_report_ref else "A post-training evaluation report is required.",
            detail = evaluation_report_ref or None,
        ),
        _registration_gate(
            gate_id = "evaluation_status_passed",
            status = "pass" if evaluation_status in MODEL_EVALUATION_PASS_VALUES else "blocked",
            severity = "info" if evaluation_status in MODEL_EVALUATION_PASS_VALUES else "error",
            reason = "Evaluation status allows library registration." if evaluation_status in MODEL_EVALUATION_PASS_VALUES else "Evaluation must pass before registration.",
            detail = evaluation_status or None,
        ),
        _registration_gate(
            gate_id = "safety_review_passed",
            status = "pass" if safety_review_passed else "blocked",
            severity = "info" if safety_review_passed else "error",
            reason = "Safety review passed." if safety_review_passed else "Safety review must pass before registration.",
            detail = safety_review_passed,
        ),
        _registration_gate(
            gate_id = "human_approval_recorded",
            status = "pass" if human_approved else "blocked",
            severity = "info" if human_approved else "error",
            reason = "Human approval recorded." if human_approved else "Human approval is required before model library write.",
            detail = human_approved,
        ),
    ]
    if not evaluation_plan_version:
        gates.append(
            _registration_gate(
                gate_id = "evaluation_plan_version_missing",
                status = "warning",
                severity = "warning",
                reason = "Evaluation plan version is recommended for audit traceability.",
            )
        )
    blocked_gate_ids = [str(item["id"]) for item in gates if item.get("severity") == "error"]
    warning_gate_ids = [str(item["id"]) for item in gates if item.get("severity") == "warning"]
    return {
        "gateVersion": COGNIX_MODEL_LIBRARY_REGISTRATION_VERSION,
        "required": True,
        "status": "ready" if not blocked_gate_ids else "blocked",
        "readyForLibraryWrite": not blocked_gate_ids,
        "blockedGateIds": blocked_gate_ids,
        "warningGateIds": warning_gate_ids,
        "artifact": {
            "kind": safe_kind,
            "artifactRef": artifact_ref or None,
        },
        "evaluation": {
            "reportRef": evaluation_report_ref or None,
            "status": evaluation_status or None,
            "evaluationPlanVersion": evaluation_plan_version or None,
        },
        "gates": gates,
        "sideEffects": {
            "evaluationJob": False,
            "modelLoad": False,
            "modelRegistryWrite": False,
            "networkCall": False,
        },
    }


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
            "ModelLibraryRegistrationGate",
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
        "modelRegistrationPolicy": {
            "registrationGateVersion": COGNIX_MODEL_LIBRARY_REGISTRATION_VERSION,
            "modelAssetTypes": sorted(MODEL_ASSET_TYPES),
            "evaluationReportRequired": True,
            "safetyReviewRequired": True,
            "humanApprovalRequired": True,
            "genericModelWriteBypassAllowed": False,
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
            "evaluationJob": False,
            "modelRegistryWrite": False,
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
    clean_metadata = _sanitize_metadata(metadata)
    registration_gate = build_model_library_registration_gate(kind = safe_kind, metadata = clean_metadata)
    extension = _extension(safe_name, uri)
    family = _asset_family(safe_kind)
    tags = _tags(clean_metadata)
    rag_candidate = safe_kind in RAG_ELIGIBLE_TYPES
    asset_metadata = {
        **clean_metadata,
        "assetFamily": family,
        "extension": extension,
        "tags": tags,
        "ragCandidate": rag_candidate,
        "datasetCandidate": safe_kind in {"document", "dataset", "report", "file"},
    }
    if registration_gate.get("required"):
        asset_metadata["modelRegistrationGate"] = registration_gate
    return {
        "libraryVersion": COGNIX_LIBRARY_VERSION,
        "metadataExtractorVersion": COGNIX_LIBRARY_METADATA_VERSION,
        "modelRegistrationGateVersion": COGNIX_MODEL_LIBRARY_REGISTRATION_VERSION,
        "mode": "asset_write_plan",
        "username": username,
        "asset": {
            "kind": safe_kind,
            "name": safe_name,
            "source": safe_source,
            "sizeBytes": size_bytes,
            "uri": uri,
            "metadata": asset_metadata,
        },
        "classification": {
            "assetFamily": family,
            "extension": extension,
            "textual": safe_kind in TEXTUAL_TYPES,
            "ragCandidate": rag_candidate,
            "datasetCandidate": safe_kind in {"document", "dataset", "report", "file"},
        },
        "registrationGate": registration_gate,
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
            "adminReviewRequired": bool(registration_gate.get("required")),
        },
        "sideEffects": build_library_blueprint()["sideEffects"],
    }
