# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX live memory editing, versioning, and search planning."""

from __future__ import annotations

from typing import Any


COGNIX_MEMORY_EDITOR_VERSION = "cognix_live_memory_editor_v1"
COGNIX_MEMORY_VERSIONING_VERSION = "cognix_memory_versioning_v1"
COGNIX_MEMORY_SEARCH_VERSION = "cognix_memory_search_v1"

MEMORY_CATEGORIES = ("preference", "project", "skill", "organization", "general")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_category(value: str | None) -> str:
    category = _normalize(value).lower().replace(" ", "_") or "general"
    aliases = {
        "competence": "skill",
        "organisation": "organization",
        "projet": "project",
        "preference": "preference",
    }
    category = aliases.get(category, category)
    return category if category in MEMORY_CATEGORIES else "general"


def build_memory_editor_blueprint() -> dict[str, Any]:
    return {
        "memoryEditorVersion": COGNIX_MEMORY_EDITOR_VERSION,
        "memoryVersioningVersion": COGNIX_MEMORY_VERSIONING_VERSION,
        "memorySearchVersion": COGNIX_MEMORY_SEARCH_VERSION,
        "mode": "live_memory_editing_contract",
        "services": ["MemoryEditorService", "MemoryVersioning", "MemorySearch"],
        "categories": [
            {"id": "preference", "label": "Preference"},
            {"id": "project", "label": "Projet"},
            {"id": "skill", "label": "Competence"},
            {"id": "organization", "label": "Organisation"},
            {"id": "general", "label": "General"},
        ],
        "userControls": {
            "view": True,
            "edit": True,
            "delete": True,
            "merge": True,
            "disable": True,
            "export": True,
        },
        "versioningPolicy": {
            "newVersionOnEdit": True,
            "auditEveryMutation": True,
            "softDeleteKeepsAudit": True,
            "mergeCreatesNewMemory": True,
        },
        "sensitiveMemoryPolicy": {
            "noSensitiveMemoryWithoutControl": True,
            "requiresExplicitConfirmation": True,
            "defaultSensitiveCreationAllowed": False,
        },
        "sideEffects": {
            "memoryWrite": False,
            "versionWrite": False,
            "auditWrite": False,
            "memoryDelete": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_memory_item_plan(
    *,
    username: str,
    title: str,
    content: str,
    category: str | None = None,
    project_id: str | None = None,
    sensitive: bool = False,
    confirmed_sensitive_control: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocked = bool(sensitive and not confirmed_sensitive_control)
    return {
        "memoryEditorVersion": COGNIX_MEMORY_EDITOR_VERSION,
        "memoryVersioningVersion": COGNIX_MEMORY_VERSIONING_VERSION,
        "mode": "memory_item_plan",
        "username": username,
        "projectId": project_id,
        "memory": {
            "title": _normalize(title)[:240],
            "content": _normalize(content)[:120000],
            "category": normalize_category(category),
            "sensitive": bool(sensitive),
            "metadata": metadata or {},
            "status": "active",
        },
        "policy": {
            "blocked": blocked,
            "reason": "Sensitive memory requires explicit user control." if blocked else None,
            "confirmedSensitiveControl": bool(confirmed_sensitive_control),
        },
        "sideEffects": build_memory_editor_blueprint()["sideEffects"],
    }


def build_memory_edit_plan(
    *,
    existing_memory: dict[str, Any],
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
    status: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    current_version = int(existing_memory.get("current_version", existing_memory.get("currentVersion", 1)) or 1)
    changes: list[str] = []
    if title is not None and _normalize(title) != _normalize(existing_memory.get("title")):
        changes.append("title")
    if content is not None and _normalize(content) != _normalize(existing_memory.get("content")):
        changes.append("content")
    if category is not None and normalize_category(category) != _normalize(existing_memory.get("category")):
        changes.append("category")
    if status is not None and _normalize(status).lower() != _normalize(existing_memory.get("status")):
        changes.append("status")
    return {
        "memoryEditorVersion": COGNIX_MEMORY_EDITOR_VERSION,
        "memoryVersioningVersion": COGNIX_MEMORY_VERSIONING_VERSION,
        "mode": "memory_edit_plan",
        "memoryId": existing_memory.get("id"),
        "currentVersion": current_version,
        "nextVersion": current_version + 1 if changes else current_version,
        "changes": changes,
        "reason": _normalize(reason)[:500],
        "sideEffects": build_memory_editor_blueprint()["sideEffects"],
    }


def build_memory_merge_plan(
    *,
    username: str,
    source_memories: list[dict[str, Any]],
    title: str | None = None,
    category: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    titles = [_normalize(item.get("title")) for item in source_memories if item.get("title")]
    contents = [_normalize(item.get("content")) for item in source_memories if item.get("content")]
    merged_title = _normalize(title) or " + ".join(titles[:3]) or "Memoire fusionnee"
    merged_content = "\n\n".join(contents)
    return {
        "memoryEditorVersion": COGNIX_MEMORY_EDITOR_VERSION,
        "memoryVersioningVersion": COGNIX_MEMORY_VERSIONING_VERSION,
        "mode": "memory_merge_plan",
        "username": username,
        "sourceMemoryIds": [str(item.get("id")) for item in source_memories],
        "memory": {
            "title": merged_title[:240],
            "content": merged_content[:120000],
            "category": normalize_category(category or (source_memories[0].get("category") if source_memories else None)),
            "sensitive": any(bool(item.get("sensitive")) for item in source_memories),
            "metadata": {
                "mergedFrom": [str(item.get("id")) for item in source_memories],
                **(metadata or {}),
            },
            "status": "active",
        },
        "summary": {
            "sourceCount": len(source_memories),
            "mergedContentLength": len(merged_content),
        },
        "sideEffects": build_memory_editor_blueprint()["sideEffects"],
    }
