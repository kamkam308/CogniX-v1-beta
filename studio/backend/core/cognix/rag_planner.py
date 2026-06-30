# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native RAG planning.

The planner decides how CogniX should use documents and sources before any
retrieval, embedding, indexing, or model call happens.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import tool_registry as cognix_tool_registry


COGNIX_RAG_PLANNER_VERSION = "cognix_rag_planner_v1"
COGNIX_RAG_SOURCE_REGISTRY_VERSION = "cognix_rag_source_registry_v1"
COGNIX_RAG_RETRIEVAL_PACKET_VERSION = "cognix_rag_retrieval_packet_v1"
COGNIX_RAG_CONNECTOR_SYNC_CONTRACT_VERSION = "cognix_rag_connector_sync_contract_v1"

SUPPORTED_SOURCE_TYPES = {"pdf", "docx", "txt", "md", "csv", "html", "url", "knowledge_base"}
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
}

RAG_SOURCE_MANIFESTS: list[dict[str, Any]] = [
    {
        "id": "project_uploads",
        "displayName": "Project uploads",
        "status": "enabled",
        "connector": "local",
        "sourceTypes": ["pdf", "docx", "txt", "md", "csv", "html"],
        "permissions": ["authenticated", "rag:write"],
        "tools": [],
        "requiresSecret": False,
        "requiresNetwork": False,
        "dataBoundary": "project",
        "defaultChunking": {"maxChunkTokens": 900, "overlapTokens": 120},
    },
    {
        "id": "project_memory",
        "displayName": "Project memory",
        "status": "enabled",
        "connector": "internal",
        "sourceTypes": ["knowledge_base", "md", "txt"],
        "permissions": ["authenticated"],
        "tools": [],
        "requiresSecret": False,
        "requiresNetwork": False,
        "dataBoundary": "project",
        "defaultChunking": {"maxChunkTokens": 700, "overlapTokens": 80},
    },
    {
        "id": "google-drive",
        "displayName": "Google Drive",
        "status": "planned",
        "connector": "google-drive",
        "sourceTypes": ["pdf", "docx", "txt", "md", "csv"],
        "permissions": ["authenticated", "drive:read", "rag:write"],
        "tools": ["google-drive"],
        "requiresSecret": True,
        "requiresNetwork": True,
        "dataBoundary": "user_connector",
        "defaultChunking": {"maxChunkTokens": 850, "overlapTokens": 120},
    },
    {
        "id": "notion",
        "displayName": "Notion",
        "status": "planned",
        "connector": "notion",
        "sourceTypes": ["knowledge_base", "md", "html"],
        "permissions": ["authenticated", "notion:read", "rag:write"],
        "tools": ["notion"],
        "requiresSecret": True,
        "requiresNetwork": True,
        "dataBoundary": "user_connector",
        "defaultChunking": {"maxChunkTokens": 800, "overlapTokens": 100},
    },
    {
        "id": "sharepoint",
        "displayName": "SharePoint / Microsoft 365",
        "status": "planned",
        "connector": "sharepoint",
        "sourceTypes": ["pdf", "docx", "txt", "md", "csv", "html"],
        "permissions": ["authenticated", "sharepoint:read", "rag:write"],
        "tools": ["sharepoint", "microsoft-365"],
        "requiresSecret": True,
        "requiresNetwork": True,
        "dataBoundary": "organization_connector",
        "defaultChunking": {"maxChunkTokens": 850, "overlapTokens": 120},
    },
    {
        "id": "moodle",
        "displayName": "Moodle",
        "status": "planned",
        "connector": "moodle",
        "sourceTypes": ["pdf", "docx", "txt", "md", "html", "knowledge_base"],
        "permissions": ["authenticated", "moodle:read", "rag:write"],
        "tools": ["moodle"],
        "requiresSecret": True,
        "requiresNetwork": True,
        "dataBoundary": "organization_connector",
        "defaultChunking": {"maxChunkTokens": 780, "overlapTokens": 100},
    },
    {
        "id": "slack-teams",
        "displayName": "Slack / Teams",
        "status": "planned",
        "connector": "slack-teams",
        "sourceTypes": ["txt", "md", "html", "knowledge_base"],
        "permissions": ["authenticated", "slack:read", "teams:read", "rag:write"],
        "tools": ["slack", "microsoft-teams"],
        "requiresSecret": True,
        "requiresNetwork": True,
        "dataBoundary": "organization_connector",
        "defaultChunking": {"maxChunkTokens": 650, "overlapTokens": 80},
    },
    {
        "id": "web_url",
        "displayName": "Web URL",
        "status": "planned",
        "connector": "web",
        "sourceTypes": ["url", "html"],
        "permissions": ["authenticated", "rag:write"],
        "tools": [],
        "requiresSecret": False,
        "requiresNetwork": True,
        "dataBoundary": "public_web",
        "defaultChunking": {"maxChunkTokens": 750, "overlapTokens": 90},
    },
]

SOURCE_CONNECTOR_ALIASES = {
    "drive": "google-drive",
    "google_drive": "google-drive",
    "google-drive": "google-drive",
    "gdrive": "google-drive",
    "local": "project_uploads",
    "file": "project_uploads",
    "upload": "project_uploads",
    "uploads": "project_uploads",
    "project": "project_uploads",
    "memory": "project_memory",
    "knowledge_base": "project_memory",
    "kb": "project_memory",
    "notion": "notion",
    "microsoft365": "sharepoint",
    "microsoft-365": "sharepoint",
    "office365": "sharepoint",
    "sharepoint": "sharepoint",
    "moodle": "moodle",
    "slack": "slack-teams",
    "teams": "slack-teams",
    "microsoft-teams": "slack-teams",
    "slack-teams": "slack-teams",
    "url": "web_url",
    "web": "web_url",
    "html": "web_url",
}


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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r\n", "\n")).strip()


def _terms(value: Any) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[a-zA-Z0-9_+-]{3,}", str(value or ""))
        if item.lower() not in STOPWORDS
    }


def _normalize_permission(permission: str) -> str:
    return (permission or "").strip().lower()


def _permission_set(
    *,
    is_admin: bool,
    has_developer_mode: bool,
    granted_permissions: set[str] | None,
) -> set[str]:
    permissions = {
        _normalize_permission(item)
        for item in (granted_permissions or set())
        if item
    }
    permissions.add(cognix_tool_registry.IMPLICIT_AUTHENTICATED_PERMISSION)
    if is_admin:
        permissions.add(cognix_tool_registry.ADMIN_PERMISSION)
        permissions.add(cognix_tool_registry.DEVELOPER_MODE_PERMISSION)
    if has_developer_mode:
        permissions.add(cognix_tool_registry.DEVELOPER_MODE_PERMISSION)
    return permissions


def _connector_by_id() -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in RAG_SOURCE_MANIFESTS}


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _missing_permissions(required: list[str], permissions: set[str]) -> list[str]:
    missing: list[str] = []
    for item in required:
        permission = _normalize_permission(str(item))
        if permission and permission not in permissions:
            missing.append(permission)
    return sorted(set(missing))


def _connector_id_for_source(source: dict[str, Any]) -> str:
    explicit = (
        source.get("sourceConnectorId")
        or source.get("connectorId")
        or source.get("connector")
        or source.get("source")
        or source.get("provider")
    )
    if explicit:
        normalized = _normalize_text(explicit).replace(" ", "_")
        return SOURCE_CONNECTOR_ALIASES.get(normalized, normalized)
    source_type = _normalize_text(source.get("type") or source.get("kind"))
    if source_type in {"url", "html"}:
        return "web_url"
    if source_type == "knowledge_base":
        return "project_memory"
    return "project_uploads"


def _source_type(source: dict[str, Any]) -> str:
    return _normalize_text(source.get("type") or source.get("kind") or "unknown")


def _estimated_chunks(source: dict[str, Any], connector: dict[str, Any] | None) -> int:
    explicit = _as_int(source.get("chunkCount") or source.get("numChunks"))
    if explicit:
        return explicit
    estimated_tokens = _as_int(source.get("estimatedTokens"))
    if estimated_tokens:
        return max(1, (estimated_tokens + 599) // 600)
    estimated_size_mb = _as_int(source.get("estimatedSizeMb") or source.get("sizeMb"))
    if estimated_size_mb:
        chunk_tokens = _as_int(_as_dict((connector or {}).get("defaultChunking")).get("maxChunkTokens"), 800)
        return max(1, (estimated_size_mb * 320 + chunk_tokens - 1) // max(1, chunk_tokens))
    return 0


def _source_registry_record(manifest: dict[str, Any], permissions: set[str]) -> dict[str, Any]:
    record = dict(manifest)
    required = [str(item) for item in record.get("permissions") or []]
    missing = _missing_permissions(required, permissions)
    enabled = record.get("status") == "enabled"
    record["missingPermissions"] = missing
    record["allowedForPlanning"] = True
    record["allowedForIndexing"] = enabled and not missing
    record["requiresHumanConfirmation"] = bool(record.get("requiresNetwork") or record.get("requiresSecret"))
    record["secretState"] = "required_unverified" if record.get("requiresSecret") else "not_required"
    record["runtimeState"] = "ready" if record["allowedForIndexing"] else "planned" if not missing else "needs_permissions"
    return record


def build_rag_source_registry(
    *,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    permissions = _permission_set(
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    connectors = [_source_registry_record(item, permissions) for item in RAG_SOURCE_MANIFESTS]
    return {
        "registryVersion": COGNIX_RAG_SOURCE_REGISTRY_VERSION,
        "plannerVersion": COGNIX_RAG_PLANNER_VERSION,
        "mode": "declarative_dry_run",
        "username": username,
        "summary": {
            "connectorCount": len(connectors),
            "enabledCount": sum(1 for item in connectors if item.get("status") == "enabled"),
            "plannedCount": sum(1 for item in connectors if item.get("status") == "planned"),
            "readyForIndexingCount": sum(1 for item in connectors if item.get("allowedForIndexing")),
        },
        "policies": {
            "sourceManifestsRequired": True,
            "citationsRequired": True,
            "rawContentLoggingAllowed": False,
            "secretsStayServerSide": True,
            "frontendDirectIndexingAllowed": False,
            "sensitiveSourcesRequireExplicitPermission": True,
        },
        "sourceConnectors": connectors,
        "sideEffects": {
            "fileRead": False,
            "networkRead": False,
            "secretRead": False,
            "embeddingGeneration": False,
            "ragIndexing": False,
            "vectorWrite": False,
            "sourceMutation": False,
            "modelLoad": False,
        },
    }


def build_rag_indexing_plan(
    *,
    username: str,
    project_id: str | None,
    sources: list[dict[str, Any]] | None,
    objective: str | None = None,
    rag_available: bool | None = None,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    registry = build_rag_source_registry(
        username = username,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    permissions = _permission_set(
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    connector_map = _connector_by_id()
    normalized_sources = [item for item in _as_list(sources) if isinstance(item, dict)]
    source_plans: list[dict[str, Any]] = []
    warnings: list[str] = []
    ready_count = 0
    blocked_count = 0
    sensitive_count = 0
    estimated_chunks = 0

    for index, source in enumerate(normalized_sources):
        source_id = str(source.get("id") or source.get("name") or f"source-{index + 1}")[:160]
        source_name = str(source.get("name") or source_id)[:240]
        source_type = _source_type(source)
        connector_id = _connector_id_for_source(source)
        connector = connector_map.get(connector_id)
        source_sensitive = bool(source.get("containsSensitiveData") or source.get("sensitive"))
        if source_sensitive:
            sensitive_count += 1

        unsupported_type = source_type not in SUPPORTED_SOURCE_TYPES
        connector_missing = connector is None
        connector_supports_type = False if connector_missing else source_type in set(connector.get("sourceTypes") or [])
        required_permissions = [str(item) for item in (connector or {}).get("permissions") or ["authenticated"]]
        missing = _missing_permissions(required_permissions, permissions)
        if source_sensitive and not is_admin and "rag:sensitive" not in permissions:
            missing = sorted(set(missing + ["rag:sensitive"]))

        chunks = _estimated_chunks(source, connector)
        estimated_chunks += chunks
        if connector_missing:
            status = "blocked_unknown_connector"
        elif unsupported_type or not connector_supports_type:
            status = "blocked_unsupported_source"
        elif rag_available is False:
            status = "blocked_rag_unavailable"
        elif source.get("indexed") or source.get("isIndexed"):
            status = "already_indexed"
        elif missing:
            status = "needs_permissions"
        elif connector.get("status") != "enabled":
            status = "planned_connector"
        else:
            status = "ready_to_index"

        if status == "ready_to_index":
            ready_count += 1
        if status.startswith("blocked"):
            blocked_count += 1

        if missing:
            warnings.append(f"Permissions manquantes pour {source_id}: {', '.join(missing)}")
        if source_sensitive:
            warnings.append(f"Source sensible declaree: {source_id}")
        if status == "planned_connector":
            warnings.append(f"Connecteur pas encore active pour {source_id}: {connector_id}")

        source_plans.append(
            {
                "sourceId": source_id,
                "sourceName": source_name,
                "sourceType": source_type,
                "connectorId": connector_id,
                "status": status,
                "readyToIndex": status == "ready_to_index",
                "alreadyIndexed": bool(source.get("indexed") or source.get("isIndexed")),
                "containsSensitiveData": source_sensitive,
                "estimatedChunks": chunks,
                "missingPermissions": missing,
                "requiresHumanConfirmation": bool(
                    source_sensitive or (connector or {}).get("requiresNetwork") or (connector or {}).get("requiresSecret")
                ),
                "chunking": _as_dict((connector or {}).get("defaultChunking")),
                "checks": [
                    {
                        "id": "source_type_supported",
                        "status": "blocked" if unsupported_type or not connector_supports_type else "complete",
                    },
                    {
                        "id": "permissions_resolved",
                        "status": "blocked" if missing else "complete",
                    },
                    {
                        "id": "connector_ready",
                        "status": "complete" if connector and connector.get("status") == "enabled" else "planned",
                    },
                    {
                        "id": "dry_run_guard",
                        "status": "complete",
                    },
                ],
            }
        )

    if not normalized_sources:
        warnings.append("Aucune source fournie pour le plan d'indexation RAG.")
    if rag_available is False:
        warnings.append("RAG backend indisponible: indexation impossible tant que le runtime RAG manque.")

    status = "ready"
    if not normalized_sources:
        status = "missing_sources"
    elif blocked_count:
        status = "blocked"
    elif ready_count == 0:
        status = "planned"

    return {
        "plannerVersion": COGNIX_RAG_PLANNER_VERSION,
        "sourceRegistryVersion": COGNIX_RAG_SOURCE_REGISTRY_VERSION,
        "mode": "dry_run",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "ragAvailable": rag_available,
        "status": status,
        "readyToIndexCount": ready_count,
        "requiresHumanConfirmation": sensitive_count > 0 or any(item.get("requiresHumanConfirmation") for item in source_plans),
        "sourcePlans": source_plans,
        "summary": {
            "sourceCount": len(normalized_sources),
            "readyToIndexCount": ready_count,
            "blockedSourceCount": blocked_count,
            "sensitiveSourceCount": sensitive_count,
            "estimatedChunkCount": estimated_chunks,
            "missingPermissionCount": sum(len(item.get("missingPermissions") or []) for item in source_plans),
        },
        "policies": registry["policies"],
        "registry": registry,
        "blockedActions": [
            {
                "id": "file_read",
                "reason": "Aucun contenu source n'est lu pendant le plan d'indexation.",
            },
            {
                "id": "embedding_generation",
                "reason": "Aucun embedding n'est calcule pendant le plan d'indexation.",
            },
            {
                "id": "vector_write",
                "reason": "Aucun index vectoriel n'est modifie en dry-run.",
            },
        ],
        "warnings": warnings,
        "sideEffects": {
            "fileRead": False,
            "networkRead": False,
            "secretRead": False,
            "embeddingGeneration": False,
            "ragIndexing": False,
            "vectorWrite": False,
            "sourceMutation": False,
            "modelLoad": False,
        },
    }


def _tool_ids_for_connector(manifest: dict[str, Any]) -> list[str]:
    return [
        str(item).strip()
        for item in manifest.get("tools") or []
        if str(item or "").strip()
    ]


def _connector_sync_manifest(connector_id: str) -> dict[str, Any] | None:
    connector_map = _connector_by_id()
    normalized = SOURCE_CONNECTOR_ALIASES.get(_normalize_text(connector_id).replace(" ", "_"), connector_id)
    return connector_map.get(normalized)


def build_rag_connector_sync_plan(
    *,
    username: str,
    connector_id: str,
    project_id: str | None = None,
    objective: str | None = None,
    source_filters: dict[str, Any] | None = None,
    max_documents: int | None = None,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    permissions = _permission_set(
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    manifest = _connector_sync_manifest(connector_id)
    side_effects = {
        "networkRead": False,
        "secretRead": False,
        "fileRead": False,
        "documentDownload": False,
        "ragIndexing": False,
        "embeddingGeneration": False,
        "vectorWrite": False,
        "sourceMutation": False,
        "toolExecution": False,
        "jobEnqueue": False,
        "modelLoad": False,
    }
    if manifest is None:
        return {
            "connectorSyncContractVersion": COGNIX_RAG_CONNECTOR_SYNC_CONTRACT_VERSION,
            "plannerVersion": COGNIX_RAG_PLANNER_VERSION,
            "sourceRegistryVersion": COGNIX_RAG_SOURCE_REGISTRY_VERSION,
            "mode": "rag_connector_sync_contract_dry_run",
            "username": username,
            "projectId": project_id,
            "connectorId": connector_id,
            "status": "unknown_connector",
            "readyForSyncRequest": False,
            "readyForIndexing": False,
            "nextRequiredGate": "source_manifest_missing",
            "gates": [
                {
                    "id": "source_manifest_declared",
                    "status": "blocked",
                    "severity": "error",
                    "reason": "RAG source connector manifest is missing.",
                }
            ],
            "blockedActions": [
                "network_read",
                "secret_read",
                "document_download",
                "rag_indexing",
                "embedding_generation",
                "vector_write",
                "job_enqueue",
            ],
            "sideEffects": side_effects,
        }

    required_permissions = [str(item) for item in manifest.get("permissions") or []]
    missing_permissions = _missing_permissions(required_permissions, permissions)
    safe_filters = _as_dict(source_filters)
    requested_filter_keys = sorted(str(key)[:80] for key in safe_filters.keys())
    limit = max(1, min(_as_int(max_documents, 50), 500))
    tool_ids = _tool_ids_for_connector(manifest)
    preflight_contracts = [
        cognix_integration_manager.build_connector_preflight_contract(
            tool_id = tool_id,
            username = username,
            is_admin = is_admin,
            has_developer_mode = has_developer_mode,
            granted_permissions = permissions,
        )
        for tool_id in tool_ids
    ]
    preflight_blocked = [
        item
        for item in preflight_contracts
        if item.get("status") == "unknown_integration"
        or bool(item.get("summary", {}).get("blockedGateIds"))
    ]
    source_type_candidates = list(manifest.get("sourceTypes") or [])
    enabled = manifest.get("status") == "enabled"
    connector_ready = enabled and not preflight_blocked and not missing_permissions
    ready_for_sync_request = bool(tool_ids and not preflight_blocked and not missing_permissions)
    ready_for_indexing = bool(connector_ready)
    gates = [
        {
            "id": "source_manifest_declared",
            "status": "pass",
            "severity": "info",
            "reason": "RAG source connector manifest is declared.",
            "detail": manifest.get("id"),
        },
        {
            "id": "integration_preflight_ready",
            "status": "pass" if not preflight_blocked else "blocked",
            "severity": "info" if not preflight_blocked else "error",
            "reason": "Connector preflight must be available before sync.",
            "detail": [item.get("toolId") for item in preflight_blocked],
        },
        {
            "id": "permissions_resolved",
            "status": "pass" if not missing_permissions else "blocked",
            "severity": "info" if not missing_permissions else "error",
            "reason": "RAG connector sync requires both connector read and rag write permissions.",
            "detail": missing_permissions,
        },
        {
            "id": "connector_enabled",
            "status": "pass" if enabled else "planned",
            "severity": "info" if enabled else "warning",
            "reason": "Connector activation remains a separate guarded workflow.",
        },
        {
            "id": "secret_server_side",
            "status": "planned" if manifest.get("requiresSecret") else "pass",
            "severity": "warning" if manifest.get("requiresSecret") else "info",
            "reason": "Secret resolution is server-side only and not performed by this plan.",
        },
    ]
    blocked_gate_ids = [str(item["id"]) for item in gates if item.get("severity") == "error"]
    warning_gate_ids = [str(item["id"]) for item in gates if item.get("severity") == "warning"]
    if blocked_gate_ids:
        status = "blocked"
    elif not enabled:
        status = "connector_activation_required"
    else:
        status = "ready_for_sync_handoff"
    sync_namespace = ":".join(
        [
            username,
            project_id or "general",
            str(manifest.get("id")),
            ",".join(requested_filter_keys),
        ]
    )
    return {
        "connectorSyncContractVersion": COGNIX_RAG_CONNECTOR_SYNC_CONTRACT_VERSION,
        "plannerVersion": COGNIX_RAG_PLANNER_VERSION,
        "sourceRegistryVersion": COGNIX_RAG_SOURCE_REGISTRY_VERSION,
        "mode": "rag_connector_sync_contract_dry_run",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "connectorId": manifest.get("id"),
        "connector": manifest.get("connector"),
        "status": status,
        "readyForSyncRequest": ready_for_sync_request,
        "readyForIndexing": ready_for_indexing,
        "nextRequiredGate": blocked_gate_ids[0] if blocked_gate_ids else "connector_activation" if not enabled else "worker_handoff_review",
        "syncScope": {
            "scopeHash": _stable_hash(sync_namespace)[:24],
            "projectBound": bool(project_id),
            "dataBoundary": manifest.get("dataBoundary"),
            "sourceFilterKeys": requested_filter_keys,
            "maxDocuments": limit,
            "rawFilterValuesIncluded": False,
            "crossUserSyncAllowed": False,
        },
        "sourceContract": {
            "supportedSourceTypes": source_type_candidates,
            "defaultChunking": _as_dict(manifest.get("defaultChunking")),
            "citationsRequired": True,
            "deduplicateByExternalSourceId": True,
            "rawDocumentContentLogged": False,
            "sourceMetadataOnly": True,
        },
        "integrationPreflight": [
            {
                "toolId": item.get("toolId"),
                "connector": item.get("connector"),
                "status": item.get("status"),
                "readyForActivationRequest": item.get("readyForActivationRequest"),
                "secretRequired": item.get("secretContract", {}).get("required"),
                "actualSecretValuesIncluded": item.get("secretContract", {}).get("actualSecretValuesIncluded"),
                "blockedGateIds": item.get("summary", {}).get("blockedGateIds", []),
                "warningGateIds": item.get("summary", {}).get("warningGateIds", []),
            }
            for item in preflight_contracts
        ],
        "permissionContract": {
            "requiredPermissions": required_permissions,
            "missingPermissions": missing_permissions,
            "effectivePermissionCount": len(permissions),
            "permissionWritePlanned": False,
        },
        "workerHandoff": {
            "plannedJobType": "rag_connector_sync",
            "plannedQueue": "rag_indexing",
            "readyForWorkerHandoff": False,
            "readyForSyncExecutor": False,
            "requiresHumanConfirmation": bool(manifest.get("requiresNetwork") or manifest.get("requiresSecret")),
            "requiresConnectorPreflight": True,
            "requiresPostSyncIndexingPlan": True,
            "jobEnqueueAllowedHere": False,
        },
        "gates": gates,
        "summary": {
            "toolCount": len(tool_ids),
            "preflightBlockedCount": len(preflight_blocked),
            "missingPermissionCount": len(missing_permissions),
            "blockedGateIds": blocked_gate_ids,
            "warningGateIds": warning_gate_ids,
            "supportedSourceTypeCount": len(source_type_candidates),
        },
        "blockedActions": [
            "network_read",
            "secret_read",
            "document_download",
            "rag_indexing",
            "embedding_generation",
            "vector_write",
            "job_enqueue",
            "tool_execution",
            "raw_document_logging",
        ],
        "sideEffects": side_effects,
    }


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


def _source_chunks(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for source_index, source in enumerate(sources):
        source_id = str(source.get("id") or source.get("sourceId") or f"source-{source_index + 1}")[:160]
        source_title = str(source.get("title") or source.get("name") or source_id)[:240]
        source_type = _source_type(source)
        raw_chunks = (
            source.get("chunks")
            or source.get("documentChunks")
            or source.get("chunkList")
            or []
        )
        if not isinstance(raw_chunks, list):
            raw_chunks = []
        if not raw_chunks and (source.get("content") or source.get("text") or source.get("excerpt")):
            raw_chunks = [
                {
                    "id": source.get("chunkId") or f"{source_id}:1",
                    "content": source.get("content") or source.get("text") or source.get("excerpt"),
                    "page": source.get("page"),
                }
            ]
        for chunk_index, chunk in enumerate(raw_chunks):
            if not isinstance(chunk, dict):
                continue
            content = _clean_text(chunk.get("content") or chunk.get("text") or chunk.get("excerpt"))
            if not content:
                continue
            chunks.append(
                {
                    "sourceId": str(chunk.get("sourceId") or source_id)[:160],
                    "sourceTitle": str(chunk.get("sourceTitle") or chunk.get("title") or source_title)[:240],
                    "sourceType": source_type,
                    "chunkId": str(chunk.get("id") or chunk.get("chunkId") or f"{source_id}:{chunk_index + 1}")[:180],
                    "page": chunk.get("page") or chunk.get("pageNumber"),
                    "content": content[:6000],
                    "originalIndex": len(chunks),
                }
            )
    return chunks


def _rank_chunk(chunk: dict[str, Any], objective_terms: set[str]) -> dict[str, Any]:
    chunk_terms = _terms(chunk.get("content"))
    matched_terms = sorted(chunk_terms & objective_terms)
    content = str(chunk.get("content") or "")
    if objective_terms and not matched_terms:
        return {
            **chunk,
            "score": 0.0,
            "matchedTerms": [],
        }
    exact_bonus = 0.18 if any(term in content.lower() for term in objective_terms) else 0.0
    density = len(matched_terms) / max(1, len(objective_terms))
    score = round(min(1.0, (density * 0.74) + exact_bonus + min(0.08, len(chunk_terms) / 1200)), 3)
    return {
        **chunk,
        "score": score,
        "matchedTerms": matched_terms[:16],
    }


def build_rag_retrieval_packet(
    *,
    username: str,
    objective: str,
    project_id: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    rag_plan: dict[str, Any] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    normalized_sources = [item for item in _as_list(sources) if isinstance(item, dict)]
    source_result = _source_checks(normalized_sources)
    rag_plan = _as_dict(rag_plan)
    objective_excerpt = " ".join((objective or "").split())[:500]
    objective_terms = _terms(objective)
    chunk_budget = _as_int(top_k, 0) or _as_int(_as_dict(rag_plan.get("retrieval")).get("topK"), 6) or 6
    safe_top_k = min(max(chunk_budget, 1), 12)
    candidates = [_rank_chunk(chunk, objective_terms) for chunk in _source_chunks(normalized_sources)]
    candidates.sort(
        key = lambda item: (
            float(item.get("score") or 0.0),
            len(item.get("matchedTerms") or []),
            -int(item.get("originalIndex") or 0),
        ),
        reverse = True,
    )
    selected = [item for item in candidates if float(item.get("score") or 0.0) > 0][:safe_top_k]
    if not selected and candidates:
        selected = candidates[: min(2, safe_top_k)]

    citations: list[dict[str, Any]] = []
    context_lines: list[str] = []
    packet_chunks: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start = 1):
        citation_id = f"S{index}"
        citation = {
            "id": citation_id,
            "sourceId": item.get("sourceId"),
            "chunkId": item.get("chunkId"),
            "title": item.get("sourceTitle"),
            "page": item.get("page"),
        }
        citations.append(citation)
        content = str(item.get("content") or "")
        clipped_content = content[:1800].rstrip()
        context_lines.append(f"[{citation_id}] {clipped_content}")
        packet_chunks.append(
            {
                "citationId": citation_id,
                "sourceId": item.get("sourceId"),
                "sourceTitle": item.get("sourceTitle"),
                "sourceType": item.get("sourceType"),
                "chunkId": item.get("chunkId"),
                "page": item.get("page"),
                "score": item.get("score"),
                "matchedTerms": item.get("matchedTerms"),
                "content": clipped_content,
                "charCount": len(content),
            }
        )

    warnings: list[str] = []
    if not normalized_sources:
        warnings.append("Aucune source RAG fournie pour construire le paquet de retrieval.")
    if not candidates and normalized_sources:
        warnings.append("Aucun chunk textuel exploitable trouve dans les sources RAG.")
    if candidates and not selected:
        warnings.append("Aucun chunk ne correspond suffisamment a l'objectif.")

    context_block = "\n\n".join(context_lines)
    return {
        "retrievalPacketVersion": COGNIX_RAG_RETRIEVAL_PACKET_VERSION,
        "plannerVersion": COGNIX_RAG_PLANNER_VERSION,
        "mode": "deterministic_lexical_retrieval",
        "username": username,
        "projectId": project_id,
        "objectiveExcerpt": objective_excerpt,
        "readyForInjection": bool(packet_chunks),
        "retrieval": {
            "strategy": "lexical",
            "topK": safe_top_k,
            "includeCitations": True,
            "embeddingRequired": False,
            "vectorStoreRequired": False,
        },
        "sourceReadiness": source_result,
        "summary": {
            "sourceCount": len(normalized_sources),
            "candidateChunkCount": len(candidates),
            "selectedChunkCount": len(packet_chunks),
            "citationCount": len(citations),
        },
        "chunks": packet_chunks,
        "citations": citations,
        "contextBlock": context_block,
        "injection": {
            "channelId": "rag_chunks",
            "format": "citation_block",
            "systemInstruction": "Use only cited RAG chunks for source-grounded claims. Cite sources with [S#].",
        },
        "warnings": warnings,
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "fileRead": False,
            "networkRead": False,
            "secretRead": False,
            "embeddingGeneration": False,
            "vectorSearch": False,
            "ragIndexing": False,
            "retrievalQuery": True,
            "sourceMutation": False,
        },
    }


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
