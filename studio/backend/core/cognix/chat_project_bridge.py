# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native chat/project bridge.

The bridge converts chat artifacts into project-scoped records without calling
models, external tools, or frontend-only APIs. Runtime execution remains a
separate, audited action.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_CHAT_PROJECT_BRIDGE_VERSION = "cognix_chat_project_bridge_v1"
COGNIX_MESSAGE_TO_TASK_VERSION = "cognix_message_to_task_service_v1"
COGNIX_PROJECT_MENTION_VERSION = "cognix_project_mention_service_v1"
COGNIX_CHAT_ANSWER_SHARE_VERSION = "cognix_chat_answer_share_v1"
COGNIX_DISCUSSION_PROJECT_VERSION = "cognix_discussion_project_service_v1"

LINK_TYPES = {"conversation", "answer_share", "approval_context"}
TASK_PRIORITIES = {"low", "medium", "high", "critical"}
TASK_STATUSES = {"open", "in_progress", "done", "blocked"}


def _normalize(value: Any, *, limit: int = 240, multiline: bool = False) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if not multiline:
        text = " ".join(text.split())
    else:
        text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit].strip()


def _first_sentence(value: str) -> str:
    text = _normalize(value, limit = 400)
    if not text:
        return ""
    match = re.search(r"(?<=[.!?])\s+", text)
    if match:
        return text[: match.start()].strip()
    return text


def _task_title(source_text: str, requested_title: str | None = None) -> str:
    title = _normalize(requested_title, limit = 160)
    if title:
        return title
    sentence = _first_sentence(source_text)
    if sentence:
        return sentence[:160].strip()
    return "Task from chat"


def _project_summary(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _normalize(project.get("id"), limit = 160),
        "name": _normalize(project.get("name"), limit = 240),
        "archived": bool(project.get("archived")),
        "ownerUsername": _normalize(project.get("ownerUsername") or project.get("owner_username"), limit = 160),
    }


def _thread_summary(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    if not thread:
        return None
    return {
        "id": _normalize(thread.get("id"), limit = 160),
        "title": _normalize(thread.get("title"), limit = 240) or "New Chat",
        "projectId": _normalize(thread.get("projectId") or thread.get("project_id"), limit = 160) or None,
        "archived": bool(thread.get("archived")),
    }


def build_chat_project_bridge_blueprint() -> dict[str, Any]:
    return {
        "chatProjectBridgeVersion": COGNIX_CHAT_PROJECT_BRIDGE_VERSION,
        "messageToTaskVersion": COGNIX_MESSAGE_TO_TASK_VERSION,
        "projectMentionVersion": COGNIX_PROJECT_MENTION_VERSION,
        "mode": "native_chat_project_bridge_contract",
        "services": ["ChatProjectBridge", "MessageToTaskService", "ProjectMentionService"],
        "tables": ["chat_project_links", "message_tasks"],
        "capabilities": [
            "transform_message_to_task",
            "link_conversation_to_project",
            "share_cognix_answer_to_chat",
            "create_project_from_discussion",
            "request_approval_from_chat",
            "detect_project_mentions",
        ],
        "securityPolicy": {
            "authenticatedUserRequired": True,
            "projectOwnershipRequired": True,
            "threadOwnershipRequired": True,
            "approvalRequestAudited": True,
            "modelCallAllowed": False,
            "networkCallAllowed": False,
            "frontendOnlyOverlay": False,
        },
        "sideEffects": {
            "chatProjectLinkWrite": False,
            "messageTaskWrite": False,
            "chatMessageWrite": False,
            "projectWrite": False,
            "approvalRequestWrite": False,
            "auditWrite": False,
            "modelCall": False,
            "networkCall": False,
            "toolExecution": False,
        },
    }


def build_answer_share_plan(
    *,
    username: str,
    project: dict[str, Any],
    thread: dict[str, Any],
    answer_text: str,
    title: str | None = None,
    parent_message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_answer = _normalize(answer_text, limit = 12000, multiline = True)
    return {
        "chatProjectBridgeVersion": COGNIX_CHAT_PROJECT_BRIDGE_VERSION,
        "answerShareVersion": COGNIX_CHAT_ANSWER_SHARE_VERSION,
        "mode": "native_cognix_answer_share_plan",
        "service": "ChatProjectBridge",
        "username": _normalize(username, limit = 160),
        "project": _project_summary(project),
        "thread": _thread_summary(thread),
        "answer": {
            "title": _normalize(title, limit = 180) or "CogniX answer",
            "text": normalized_answer,
            "parentMessageId": _normalize(parent_message_id, limit = 160) or None,
            "metadata": metadata or {},
        },
        "link": {
            "projectId": _normalize(project.get("id"), limit = 160),
            "threadId": _normalize(thread.get("id"), limit = 160),
            "linkType": "answer_share",
            "source": "project",
            "status": "active",
        },
        "permissionPlan": {
            "requiredPermissions": ["authenticated"],
            "projectOwnershipRequired": True,
            "threadOwnershipRequired": True,
            "approvalRequired": False,
        },
        "sideEffects": {
            **build_chat_project_bridge_blueprint()["sideEffects"],
            "chatMessageWrite": False,
            "chatProjectLinkWrite": False,
        },
    }


def build_discussion_project_plan(
    *,
    username: str,
    thread: dict[str, Any],
    project_id: str,
    project_name: str,
    discussion_summary: str,
    instructions: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "chatProjectBridgeVersion": COGNIX_CHAT_PROJECT_BRIDGE_VERSION,
        "discussionProjectVersion": COGNIX_DISCUSSION_PROJECT_VERSION,
        "mode": "native_project_from_discussion_plan",
        "service": "ChatProjectBridge",
        "username": _normalize(username, limit = 160),
        "thread": _thread_summary(thread),
        "project": {
            "id": _normalize(project_id, limit = 160),
            "name": _normalize(project_name, limit = 240) or "Project from discussion",
            "instructions": _normalize(instructions or discussion_summary, limit = 4000, multiline = True),
            "discussionSummary": _normalize(discussion_summary, limit = 4000, multiline = True),
            "metadata": metadata or {},
        },
        "link": {
            "projectId": _normalize(project_id, limit = 160),
            "threadId": _normalize(thread.get("id"), limit = 160),
            "linkType": "conversation",
            "source": "discussion",
            "status": "active",
        },
        "permissionPlan": {
            "requiredPermissions": ["authenticated"],
            "threadOwnershipRequired": True,
            "projectOwnershipRequired": False,
            "approvalRequired": False,
        },
        "sideEffects": {
            **build_chat_project_bridge_blueprint()["sideEffects"],
            "projectWrite": False,
            "chatProjectLinkWrite": False,
        },
    }


def build_thread_link_plan(
    *,
    username: str,
    project: dict[str, Any],
    thread: dict[str, Any],
    link_type: str = "conversation",
    source: str = "chat",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_link_type = link_type if link_type in LINK_TYPES else "conversation"
    return {
        "chatProjectBridgeVersion": COGNIX_CHAT_PROJECT_BRIDGE_VERSION,
        "mode": "native_chat_project_link_plan",
        "service": "ChatProjectBridge",
        "username": _normalize(username, limit = 160),
        "project": _project_summary(project),
        "thread": _thread_summary(thread),
        "link": {
            "projectId": _normalize(project.get("id"), limit = 160),
            "threadId": _normalize(thread.get("id"), limit = 160),
            "linkType": normalized_link_type,
            "source": _normalize(source, limit = 80) or "chat",
            "status": "active",
            "metadata": metadata or {},
        },
        "permissionPlan": {
            "requiredPermissions": ["authenticated"],
            "projectOwnershipRequired": True,
            "threadOwnershipRequired": True,
            "approvalRequired": False,
        },
        "sideEffects": {
            **build_chat_project_bridge_blueprint()["sideEffects"],
            "chatProjectLinkWrite": False,
        },
    }


def build_message_task_plan(
    *,
    username: str,
    project: dict[str, Any],
    source_text: str,
    thread: dict[str, Any] | None = None,
    message: dict[str, Any] | None = None,
    task_title: str | None = None,
    status: str = "open",
    priority: str = "medium",
    require_approval: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_text = _normalize(source_text, limit = 12000, multiline = True)
    normalized_status = status if status in TASK_STATUSES else "open"
    normalized_priority = priority if priority in TASK_PRIORITIES else "medium"
    thread_record = _thread_summary(thread)
    message_id = _normalize((message or {}).get("id"), limit = 160) or None
    task = {
        "projectId": _normalize(project.get("id"), limit = 160),
        "threadId": thread_record["id"] if thread_record else None,
        "messageId": message_id,
        "title": _task_title(normalized_text, task_title),
        "sourceText": normalized_text,
        "status": normalized_status,
        "priority": normalized_priority,
        "metadata": metadata or {},
    }
    return {
        "chatProjectBridgeVersion": COGNIX_CHAT_PROJECT_BRIDGE_VERSION,
        "messageToTaskVersion": COGNIX_MESSAGE_TO_TASK_VERSION,
        "mode": "native_message_to_task_plan",
        "service": "MessageToTaskService",
        "username": _normalize(username, limit = 160),
        "project": _project_summary(project),
        "thread": thread_record,
        "message": {
            "id": message_id,
            "role": _normalize((message or {}).get("role"), limit = 80) or None,
        },
        "task": task,
        "approvalPlan": {
            "required": bool(require_approval),
            "requestType": "chat_message_task_approval",
            "riskLevel": "medium" if require_approval else "low",
            "resourceType": "message_task",
        },
        "permissionPlan": {
            "requiredPermissions": ["authenticated"],
            "projectOwnershipRequired": True,
            "threadOwnershipRequired": bool(thread_record),
            "approvalRequired": bool(require_approval),
        },
        "sideEffects": {
            **build_chat_project_bridge_blueprint()["sideEffects"],
            "messageTaskWrite": False,
            "approvalRequestWrite": False,
        },
    }


def extract_project_mentions(text: str, projects: list[dict[str, Any]], *, limit: int = 8) -> dict[str, Any]:
    normalized_text = _normalize(text, limit = 12000, multiline = True).lower()
    mentions: list[dict[str, Any]] = []
    for project in projects:
        project_name = _normalize(project.get("name"), limit = 240)
        project_id = _normalize(project.get("id"), limit = 160)
        if not project_name and not project_id:
            continue
        signals = []
        if project_name and project_name.lower() in normalized_text:
            signals.append("name")
        if project_id and project_id.lower() in normalized_text:
            signals.append("id")
        slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-")
        if slug and f"#{slug}" in normalized_text:
            signals.append("hashtag")
        if signals:
            mentions.append(
                {
                    "projectId": project_id,
                    "projectName": project_name,
                    "signals": signals,
                    "confidence": min(0.98, 0.55 + 0.18 * len(signals)),
                }
            )
        if len(mentions) >= limit:
            break
    return {
        "projectMentionVersion": COGNIX_PROJECT_MENTION_VERSION,
        "mode": "native_project_mention_detection",
        "mentions": mentions,
        "sideEffects": build_chat_project_bridge_blueprint()["sideEffects"],
    }
