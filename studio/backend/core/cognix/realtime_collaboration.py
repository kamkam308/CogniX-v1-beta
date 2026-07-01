# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native real-time collaboration contracts.

The module defines the backend contract for project presence, comments, live
activity events, and conflict resolution without opening sockets or mutating
project files directly. A future WebSocket transport can use the same plans and
tables without becoming a separate overlay.
"""

from __future__ import annotations

from typing import Any


COGNIX_REALTIME_COLLABORATION_VERSION = "cognix_realtime_collaboration_v1"
COGNIX_PRESENCE_SERVICE_VERSION = "cognix_presence_service_v1"
COGNIX_COMMENT_SERVICE_VERSION = "cognix_comment_service_v1"
COGNIX_CONFLICT_RESOLVER_VERSION = "cognix_conflict_resolver_v1"

REALTIME_COLLABORATION_SERVICES = [
    "RealtimeCollaborationService",
    "PresenceService",
    "CommentService",
    "ConflictResolver",
]

REALTIME_COLLABORATION_TABLES = [
    "presence_sessions",
    "project_comments",
    "collaboration_events",
]

PRESENCE_STATUSES = {"online", "idle", "editing", "viewing", "offline"}
COMMENT_STATUSES = {"open", "resolved", "archived"}
COMMENT_TARGET_TYPES = {"project", "document", "note", "message", "task", "asset"}
EVENT_TYPES = {
    "presence_updated",
    "comment_created",
    "comment_updated",
    "comment_resolved",
    "document_edit_proposed",
    "note_edit_proposed",
    "cursor_updated",
    "conflict_detected",
    "conflict_resolved",
}
CONFLICT_STRATEGIES = {"manual_review", "latest_wins", "owner_wins", "merge_if_clean"}


def _text(value: Any, limit: int = 240, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).replace("\r\n", "\n").strip()
    return " ".join(text.split())[:limit].strip()


def _multiline(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:limit].strip()


def _key(value: Any, fallback: str = "project") -> str:
    text = _text(value, 180, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return cleaned.strip("-")[:160] or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _project_summary(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(project.get("id"), 160),
        "name": _text(project.get("name"), 240),
        "ownerUsername": _text(project.get("ownerUsername") or project.get("owner_username"), 160),
        "archived": bool(project.get("archived")),
    }


def build_realtime_collaboration_blueprint() -> dict[str, Any]:
    return {
        "realtimeCollaborationVersion": COGNIX_REALTIME_COLLABORATION_VERSION,
        "presenceServiceVersion": COGNIX_PRESENCE_SERVICE_VERSION,
        "commentServiceVersion": COGNIX_COMMENT_SERVICE_VERSION,
        "conflictResolverVersion": COGNIX_CONFLICT_RESOLVER_VERSION,
        "mode": "native_realtime_collaboration_contract",
        "services": REALTIME_COLLABORATION_SERVICES,
        "tables": REALTIME_COLLABORATION_TABLES,
        "capabilities": [
            "project_presence",
            "cursor_metadata",
            "project_comments",
            "comment_resolution",
            "live_activity_events",
            "conflict_resolution_plan",
        ],
        "permissions": {
            "presenceRead": ["project:read"],
            "presenceWrite": ["project:read"],
            "commentWrite": ["project:comment"],
            "commentResolve": ["project:edit", "comment:owner"],
            "eventWrite": ["project:read"],
            "conflictResolve": ["project:edit"],
        },
        "transportContract": {
            "webSocketReady": True,
            "restFallbackReady": True,
            "presenceTtlSecondsDefault": 90,
            "hiddenPresenceAllowed": False,
            "frontendDirectModelCallAllowed": False,
        },
        "sideEffects": {
            "presenceWrite": False,
            "commentWrite": False,
            "commentStatusWrite": False,
            "eventWrite": False,
            "projectFileWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "secretRead": False,
        },
    }


def build_presence_plan(
    *,
    username: str,
    project: dict[str, Any],
    client_id: str,
    status: str = "online",
    cursor: dict[str, Any] | None = None,
    activity: str | None = None,
    ttl_seconds: int = 90,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = _key(status, "online")
    if normalized_status not in PRESENCE_STATUSES:
        normalized_status = "online"
    ttl = max(15, min(int(ttl_seconds or 90), 600))
    normalized_cursor = _dict(cursor)
    return {
        "realtimeCollaborationVersion": COGNIX_REALTIME_COLLABORATION_VERSION,
        "presenceServiceVersion": COGNIX_PRESENCE_SERVICE_VERSION,
        "mode": "native_presence_update_plan",
        "service": "PresenceService",
        "username": _text(username, 160),
        "project": _project_summary(project),
        "presence": {
            "clientId": _key(client_id, "browser"),
            "status": normalized_status,
            "activity": _text(activity, 180) or None,
            "cursor": {
                "resourceType": _key(normalized_cursor.get("resourceType"), "project"),
                "resourceId": _text(normalized_cursor.get("resourceId"), 200) or None,
                "line": normalized_cursor.get("line") if isinstance(normalized_cursor.get("line"), int) else None,
                "column": normalized_cursor.get("column") if isinstance(normalized_cursor.get("column"), int) else None,
            },
            "ttlSeconds": ttl,
            "visibleToProjectMembers": True,
            "hiddenPresenceAllowed": False,
        },
        "metadata": _dict(metadata),
        "sideEffects": build_realtime_collaboration_blueprint()["sideEffects"],
    }


def build_comment_plan(
    *,
    username: str,
    project: dict[str, Any],
    body: str,
    target: dict[str, Any] | None = None,
    parent_comment_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_body = _multiline(body, 3000)
    normalized_target = _dict(target)
    target_type = _key(normalized_target.get("type") or normalized_target.get("targetType"), "project")
    if target_type not in COMMENT_TARGET_TYPES:
        target_type = "project"
    return {
        "realtimeCollaborationVersion": COGNIX_REALTIME_COLLABORATION_VERSION,
        "commentServiceVersion": COGNIX_COMMENT_SERVICE_VERSION,
        "mode": "native_project_comment_plan",
        "service": "CommentService",
        "username": _text(username, 160),
        "project": _project_summary(project),
        "valid": bool(normalized_body),
        "comment": {
            "body": normalized_body,
            "status": "open",
            "target": {
                "type": target_type,
                "id": _text(normalized_target.get("id") or normalized_target.get("targetId"), 200)
                or _text(project.get("id"), 160),
                "range": _dict(normalized_target.get("range")),
            },
            "parentCommentId": _text(parent_comment_id, 160) or None,
        },
        "metadata": _dict(metadata),
        "sideEffects": build_realtime_collaboration_blueprint()["sideEffects"],
    }


def build_comment_resolution_plan(
    *,
    username: str,
    project: dict[str, Any],
    comment: dict[str, Any],
    status: str = "resolved",
    note: str | None = None,
) -> dict[str, Any]:
    normalized_status = _key(status, "resolved")
    if normalized_status not in COMMENT_STATUSES:
        normalized_status = "resolved"
    return {
        "realtimeCollaborationVersion": COGNIX_REALTIME_COLLABORATION_VERSION,
        "commentServiceVersion": COGNIX_COMMENT_SERVICE_VERSION,
        "mode": "native_comment_resolution_plan",
        "service": "CommentService",
        "username": _text(username, 160),
        "project": _project_summary(project),
        "comment": {
            "id": _text(comment.get("id"), 160),
            "previousStatus": _text(comment.get("status"), 80),
            "nextStatus": normalized_status,
            "resolverNote": _multiline(note, 1000) or None,
        },
        "sideEffects": build_realtime_collaboration_blueprint()["sideEffects"],
    }


def build_collaboration_event_plan(
    *,
    username: str,
    project: dict[str, Any],
    event_type: str,
    resource_type: str = "project",
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_event_type = _key(event_type, "presence_updated")
    if normalized_event_type not in EVENT_TYPES:
        normalized_event_type = "presence_updated"
    return {
        "realtimeCollaborationVersion": COGNIX_REALTIME_COLLABORATION_VERSION,
        "mode": "native_collaboration_event_plan",
        "service": "RealtimeCollaborationService",
        "username": _text(username, 160),
        "project": _project_summary(project),
        "event": {
            "type": normalized_event_type,
            "resourceType": _key(resource_type, "project"),
            "resourceId": _text(resource_id, 200) or _text(project.get("id"), 160),
            "payload": _dict(payload),
            "visibleToProjectMembers": True,
        },
        "metadata": _dict(metadata),
        "sideEffects": build_realtime_collaboration_blueprint()["sideEffects"],
    }


def build_conflict_resolution_plan(
    *,
    username: str,
    project: dict[str, Any],
    resource_type: str,
    resource_id: str,
    base_revision: str | None = None,
    local_revision: str | None = None,
    remote_revision: str | None = None,
    strategy: str = "manual_review",
    changes: list[Any] | None = None,
) -> dict[str, Any]:
    normalized_strategy = _key(strategy, "manual_review")
    if normalized_strategy not in CONFLICT_STRATEGIES:
        normalized_strategy = "manual_review"
    normalized_changes = _list(changes)
    has_revision_mismatch = bool(local_revision and remote_revision and local_revision != remote_revision)
    requires_human_review = normalized_strategy == "manual_review" or has_revision_mismatch
    return {
        "realtimeCollaborationVersion": COGNIX_REALTIME_COLLABORATION_VERSION,
        "conflictResolverVersion": COGNIX_CONFLICT_RESOLVER_VERSION,
        "mode": "native_conflict_resolution_plan",
        "service": "ConflictResolver",
        "username": _text(username, 160),
        "project": _project_summary(project),
        "conflict": {
            "resourceType": _key(resource_type, "document"),
            "resourceId": _text(resource_id, 200),
            "baseRevision": _text(base_revision, 120) or None,
            "localRevision": _text(local_revision, 120) or None,
            "remoteRevision": _text(remote_revision, 120) or None,
            "changeCount": len(normalized_changes),
            "revisionMismatchDetected": has_revision_mismatch,
        },
        "resolutionPolicy": {
            "strategy": normalized_strategy,
            "automaticOverwriteAllowed": False,
            "requiresHumanReview": requires_human_review,
            "auditRequired": True,
            "projectFileWriteAllowedNow": False,
        },
        "proposedChanges": normalized_changes[:80],
        "sideEffects": build_realtime_collaboration_blueprint()["sideEffects"],
    }
