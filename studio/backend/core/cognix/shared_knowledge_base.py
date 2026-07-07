# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX shared knowledge base services."""

from __future__ import annotations

import re
from typing import Any


COGNIX_SHARED_KNOWLEDGE_BASE_VERSION = "cognix_shared_knowledge_base_v1"
COGNIX_ORGANIZATION_RAG_SERVICE_VERSION = "cognix_organization_rag_service_v1"
COGNIX_DOCUMENT_PERMISSION_FILTER_VERSION = "cognix_document_permission_filter_v1"

SHARED_KNOWLEDGE_SERVICES = [
    "SharedKnowledgeBaseService",
    "OrganizationRAGService",
    "DocumentPermissionFilter",
]

SHARED_KNOWLEDGE_TABLES = [
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_permissions",
]


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w-]{3,}", value or "")}


def build_shared_knowledge_blueprint() -> dict[str, Any]:
    return {
        "sharedKnowledgeBaseVersion": COGNIX_SHARED_KNOWLEDGE_BASE_VERSION,
        "organizationRagServiceVersion": COGNIX_ORGANIZATION_RAG_SERVICE_VERSION,
        "documentPermissionFilterVersion": COGNIX_DOCUMENT_PERMISSION_FILTER_VERSION,
        "mode": "native_shared_knowledge_base",
        "services": SHARED_KNOWLEDGE_SERVICES,
        "tables": SHARED_KNOWLEDGE_TABLES,
        "pipeline": ["Documents", "Chunking", "Embeddings", "Permissions", "Retrieval"],
        "security": {
            "permissionFilteredRetrieval": True,
            "denyByDefault": True,
            "chunkVisibilityRequiresPermission": True,
            "frontendDirectVectorAccess": False,
        },
        "sideEffects": {
            "databaseWrite": False,
            "knowledgeBaseWrite": False,
            "documentWrite": False,
            "chunkWrite": False,
            "permissionWrite": False,
            "auditWrite": False,
            "embeddingCall": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "fileWrite": False,
        },
    }


def chunk_document_text(text: str, *, chunk_size: int = 120, overlap: int = 20) -> list[dict[str, Any]]:
    words = [word for word in re.split(r"\s+", text.strip()) if word]
    if not words:
        return []
    size = max(20, min(int(chunk_size or 120), 500))
    step = max(1, size - max(0, min(int(overlap or 0), size - 1)))
    chunks: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(words), step)):
        segment = words[start : start + size]
        if not segment:
            continue
        chunks.append(
            {
                "chunkIndex": index,
                "text": " ".join(segment),
                "tokenCountEstimate": len(segment),
                "embeddingStatus": "planned",
            }
        )
        if start + size >= len(words):
            break
    return chunks


def build_document_index_plan(
    *,
    knowledge_base_id: str,
    document_id: str,
    title: str,
    content: str,
    chunk_size: int = 120,
    overlap: int = 20,
) -> dict[str, Any]:
    chunks = chunk_document_text(content, chunk_size = chunk_size, overlap = overlap)
    return {
        "organizationRagServiceVersion": COGNIX_ORGANIZATION_RAG_SERVICE_VERSION,
        "knowledgeBaseId": knowledge_base_id,
        "documentId": document_id,
        "title": title,
        "chunkCount": len(chunks),
        "chunks": chunks,
        "embeddingPlan": {
            "status": "planned",
            "embeddingCall": False,
            "reason": "native_index_plan_without_external_embedding_call",
        },
        "sideEffects": build_shared_knowledge_blueprint()["sideEffects"],
    }


def _permission_allows(record: dict[str, Any], *, username: str, role: str, permission: str) -> bool:
    subject_type = _norm(record.get("subjectType") or record.get("subject_type")).casefold()
    subject_id = _norm(record.get("subjectId") or record.get("subject_id"))
    permission_value = _norm(record.get("permission"), "read").casefold()
    if permission_value not in {permission.casefold(), "admin", "write"}:
        return False
    if subject_type == "everyone":
        return True
    if subject_type == "user" and subject_id == username:
        return True
    if subject_type == "role" and subject_id.casefold() == role.casefold():
        return True
    return False


def filter_chunks_for_user(
    *,
    chunks: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    username: str,
    role: str = "user",
    permission: str = "read",
) -> dict[str, Any]:
    if role in {"admin", "CEO"}:
        return {
            "documentPermissionFilterVersion": COGNIX_DOCUMENT_PERMISSION_FILTER_VERSION,
            "visibleChunks": chunks,
            "filteredChunkCount": 0,
            "allowedDocumentIds": sorted({str(chunk.get("documentId") or chunk.get("document_id") or "") for chunk in chunks}),
        }
    allowed_scopes = {
        str(record.get("scopeId") or record.get("scope_id") or "")
        for record in permissions
        if _permission_allows(record, username = username, role = role, permission = permission)
    }
    visible = [
        chunk
        for chunk in chunks
        if str(chunk.get("knowledgeBaseId") or chunk.get("knowledge_base_id") or "") in allowed_scopes
        or str(chunk.get("documentId") or chunk.get("document_id") or "") in allowed_scopes
    ]
    return {
        "documentPermissionFilterVersion": COGNIX_DOCUMENT_PERMISSION_FILTER_VERSION,
        "visibleChunks": visible,
        "filteredChunkCount": max(0, len(chunks) - len(visible)),
        "allowedDocumentIds": sorted({str(chunk.get("documentId") or chunk.get("document_id") or "") for chunk in visible}),
    }


def build_retrieval_result(
    *,
    query: str,
    chunks: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    username: str,
    role: str = "user",
    limit: int = 5,
) -> dict[str, Any]:
    filtered = filter_chunks_for_user(
        chunks = chunks,
        permissions = permissions,
        username = username,
        role = role,
        permission = "read",
    )
    query_tokens = _tokens(query)
    scored = []
    for chunk in filtered["visibleChunks"]:
        chunk_text = _norm(chunk.get("text"))
        overlap = len(query_tokens & _tokens(chunk_text))
        if overlap <= 0 and query_tokens:
            continue
        scored.append((overlap, chunk))
    scored.sort(key = lambda item: (item[0], str(item[1].get("createdAt") or item[1].get("created_at") or "")), reverse = True)
    selected = [chunk for _, chunk in scored[: max(1, min(int(limit or 5), 20))]]
    documents_by_id = {str(item.get("id") or item.get("documentId") or ""): item for item in documents}
    sources = [
        {
            "documentId": chunk.get("documentId") or chunk.get("document_id"),
            "title": documents_by_id.get(str(chunk.get("documentId") or chunk.get("document_id") or ""), {}).get("title"),
            "chunkId": chunk.get("id"),
            "chunkIndex": chunk.get("chunkIndex") or chunk.get("chunk_index"),
        }
        for chunk in selected
    ]
    return {
        "organizationRagServiceVersion": COGNIX_ORGANIZATION_RAG_SERVICE_VERSION,
        "documentPermissionFilterVersion": COGNIX_DOCUMENT_PERMISSION_FILTER_VERSION,
        "query": query,
        "chunks": selected,
        "sources": sources,
        "summary": {
            "visibleChunkCount": len(filtered["visibleChunks"]),
            "returnedChunkCount": len(selected),
            "filteredChunkCount": filtered["filteredChunkCount"],
        },
        "sideEffects": build_shared_knowledge_blueprint()["sideEffects"],
    }
