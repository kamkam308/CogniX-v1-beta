# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX data retention and privacy controls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


COGNIX_DATA_RETENTION_SERVICE_VERSION = "cognix_data_retention_service_v1"
COGNIX_PRIVACY_POLICY_SERVICE_VERSION = "cognix_privacy_policy_service_v1"
COGNIX_DATA_DELETION_SERVICE_VERSION = "cognix_data_deletion_service_v1"

DATA_RETENTION_SERVICES = [
    "DataRetentionService",
    "PrivacyPolicyService",
    "DataDeletionService",
]

DATA_RETENTION_TABLES = [
    "retention_policies",
    "deletion_jobs",
    "privacy_events",
]

SENSITIVE_TERMS = (
    "api_key",
    "api key",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "private key",
    "bearer ",
    "hf_",
    "sk-",
    ".env",
)

DEFAULT_RETENTION_POLICY: dict[str, Any] = {
    "chatRetentionDays": 90,
    "projectArchiveMonths": 12,
    "sensitivePromptMode": "metadata_only",
    "contentLogsEnabled": False,
    "metadataOnlyMode": True,
    "userExportEnabled": True,
    "userDeletionRequiresApproval": True,
    "e2eeStrict": False,
}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return fallback


def _as_int(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _timestamp_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    raw = _norm(value)
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return 0


def _age_days(value: Any, *, now_ms: int) -> float:
    timestamp = _timestamp_ms(value)
    if timestamp <= 0:
        return 0.0
    return max(0.0, (now_ms - timestamp) / 86_400_000)


def _text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return str(value)


def _is_sensitive(value: Any) -> bool:
    text = _text_blob(value).lower()
    return any(term in text for term in SENSITIVE_TERMS)


def normalize_retention_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = policy if isinstance(policy, dict) else {}
    normalized = dict(DEFAULT_RETENTION_POLICY)
    if "chatRetentionDays" in incoming:
        normalized["chatRetentionDays"] = max(1, min(_as_int(incoming.get("chatRetentionDays"), 90), 3650))
    if "projectArchiveMonths" in incoming:
        normalized["projectArchiveMonths"] = max(1, min(_as_int(incoming.get("projectArchiveMonths"), 12), 240))
    mode = _norm(incoming.get("sensitivePromptMode"), normalized["sensitivePromptMode"]).lower()
    if mode in {"store", "redact", "metadata_only", "disabled"}:
        normalized["sensitivePromptMode"] = mode
    for key in ("contentLogsEnabled", "metadataOnlyMode", "userExportEnabled", "userDeletionRequiresApproval", "e2eeStrict"):
        if key in incoming:
            normalized[key] = _as_bool(incoming.get(key), bool(normalized[key]))
    if normalized["metadataOnlyMode"]:
        normalized["contentLogsEnabled"] = False
    return normalized


def build_data_retention_blueprint() -> dict[str, Any]:
    return {
        "dataRetentionServiceVersion": COGNIX_DATA_RETENTION_SERVICE_VERSION,
        "privacyPolicyServiceVersion": COGNIX_PRIVACY_POLICY_SERVICE_VERSION,
        "dataDeletionServiceVersion": COGNIX_DATA_DELETION_SERVICE_VERSION,
        "mode": "native_admin_data_retention_privacy_controls",
        "services": DATA_RETENTION_SERVICES,
        "tables": DATA_RETENTION_TABLES,
        "controls": [
            "delete_chats_after_days",
            "archive_projects_after_months",
            "sensitive_prompt_storage_policy",
            "content_log_disable",
            "metadata_only_mode",
            "user_export",
            "user_deletion",
        ],
        "e2eeLimits": {
            "strictModeServerContentReadable": False,
            "metadataExportAllowed": True,
            "contentDeletionCanBeScheduled": True,
        },
        "sideEffects": {
            "databaseWrite": False,
            "retentionPolicyWrite": False,
            "deletionJobWrite": False,
            "privacyEventWrite": False,
            "auditWrite": False,
            "contentDelete": False,
            "projectArchive": False,
            "fileWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_privacy_decision(
    *,
    policy: dict[str, Any],
    content: Any = None,
    e2ee_strict: bool | None = None,
) -> dict[str, Any]:
    normalized = normalize_retention_policy(policy)
    strict = normalized["e2eeStrict"] if e2ee_strict is None else bool(e2ee_strict)
    sensitive = _is_sensitive(content)
    content_readable = not strict
    content_stored = bool(normalized["contentLogsEnabled"] and not normalized["metadataOnlyMode"] and content_readable)
    storage_mode = "content"
    if strict or normalized["metadataOnlyMode"]:
        storage_mode = "metadata_only"
        content_stored = False
    if sensitive:
        mode = normalized["sensitivePromptMode"]
        if mode in {"metadata_only", "disabled"}:
            storage_mode = "metadata_only"
            content_stored = False
        elif mode == "redact":
            storage_mode = "redacted_content"
            content_stored = bool(content_readable and normalized["contentLogsEnabled"])
        else:
            storage_mode = "content"
    return {
        "privacyPolicyServiceVersion": COGNIX_PRIVACY_POLICY_SERVICE_VERSION,
        "e2eeStrict": strict,
        "contentReadableByServer": content_readable,
        "sensitivePromptDetected": sensitive,
        "storageMode": storage_mode,
        "contentStorageAllowed": content_stored,
        "contentLoggingAllowed": bool(normalized["contentLogsEnabled"] and content_readable),
        "metadataOnly": storage_mode == "metadata_only",
        "serverContentExportAllowed": bool(content_readable and content_stored),
        "reason": (
            "e2ee_strict_content_unreadable"
            if strict
            else "sensitive_prompt_policy"
            if sensitive
            else "organization_privacy_policy"
        ),
        "sideEffects": build_data_retention_blueprint()["sideEffects"],
    }


def build_retention_plan(
    *,
    policy: dict[str, Any],
    threads: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    now_ms: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_retention_policy(policy)
    current_ms = int(now_ms or datetime.now(timezone.utc).timestamp() * 1000)
    chat_limit = normalized["chatRetentionDays"]
    project_limit_days = normalized["projectArchiveMonths"] * 30
    chat_candidates = []
    for thread in threads:
        age = _age_days(thread.get("createdAt") or thread.get("created_at"), now_ms = current_ms)
        if age >= chat_limit:
            chat_candidates.append(
                {
                    "threadId": thread.get("id"),
                    "ownerUsername": thread.get("ownerUsername") or thread.get("owner_username"),
                    "ageDays": round(age, 2),
                    "recommendedAction": "queue_chat_deletion",
                }
            )
    project_candidates = []
    for project in projects:
        age = _age_days(project.get("updatedAt") or project.get("updated_at"), now_ms = current_ms)
        if age >= project_limit_days and not bool(project.get("archived")):
            project_candidates.append(
                {
                    "projectId": project.get("id"),
                    "ownerUsername": project.get("ownerUsername") or project.get("owner_username"),
                    "ageDays": round(age, 2),
                    "recommendedAction": "queue_project_archive",
                }
            )
    return {
        "dataRetentionServiceVersion": COGNIX_DATA_RETENTION_SERVICE_VERSION,
        "policy": normalized,
        "summary": {
            "threadCount": len(threads),
            "projectCount": len(projects),
            "chatDeletionCandidateCount": len(chat_candidates),
            "projectArchiveCandidateCount": len(project_candidates),
        },
        "chatDeletionCandidates": chat_candidates,
        "projectArchiveCandidates": project_candidates,
        "sideEffects": build_data_retention_blueprint()["sideEffects"],
    }


def build_user_export_plan(
    *,
    username: str,
    policy: dict[str, Any],
    threads: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    include_content: bool = False,
) -> dict[str, Any]:
    normalized = normalize_retention_policy(policy)
    privacy = build_privacy_decision(policy = normalized, content = None)
    content_allowed = bool(include_content and privacy["serverContentExportAllowed"] and not normalized["e2eeStrict"])
    user_threads = [thread for thread in threads if _norm(thread.get("ownerUsername") or thread.get("owner_username")) == username]
    thread_ids = {str(thread.get("id")) for thread in user_threads}
    user_messages = [message for message in messages if str(message.get("threadId") or message.get("thread_id")) in thread_ids]
    payload = {
        "username": username,
        "projects": [
            {
                "id": project.get("id"),
                "name": project.get("name"),
                "archived": bool(project.get("archived")),
            }
            for project in projects
            if _norm(project.get("ownerUsername") or project.get("owner_username")) == username
        ],
        "threads": [
            {
                "id": thread.get("id"),
                "title": thread.get("title"),
                "projectId": thread.get("projectId") or thread.get("project_id"),
                "modelId": thread.get("modelId") or thread.get("model_id"),
                "createdAt": thread.get("createdAt") or thread.get("created_at"),
            }
            for thread in user_threads
        ],
        "messages": [
            {
                "id": message.get("id"),
                "threadId": message.get("threadId") or message.get("thread_id"),
                "role": message.get("role"),
                "content": message.get("content") if content_allowed else None,
                "metadataOnly": not content_allowed,
            }
            for message in user_messages
        ],
        "auditLogs": [
            {
                "id": log.get("id"),
                "action": log.get("action"),
                "resourceType": log.get("resource_type") or log.get("resourceType"),
                "createdAt": log.get("created_at") or log.get("createdAt"),
            }
            for log in audit_logs
            if _norm(log.get("username")) == username or _norm(log.get("actor_username") or log.get("actorUsername")) == username
        ],
    }
    return {
        "dataRetentionServiceVersion": COGNIX_DATA_RETENTION_SERVICE_VERSION,
        "privacyPolicyServiceVersion": COGNIX_PRIVACY_POLICY_SERVICE_VERSION,
        "exportEnabled": bool(normalized["userExportEnabled"]),
        "contentIncluded": content_allowed,
        "metadataOnly": not content_allowed,
        "e2eeStrict": bool(normalized["e2eeStrict"]),
        "payload": payload,
        "summary": {
            "projectCount": len(payload["projects"]),
            "threadCount": len(payload["threads"]),
            "messageCount": len(payload["messages"]),
            "auditLogCount": len(payload["auditLogs"]),
        },
        "sideEffects": build_data_retention_blueprint()["sideEffects"],
    }


def build_user_deletion_plan(
    *,
    username: str,
    policy: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    normalized = normalize_retention_policy(policy)
    requires_approval = bool(normalized["userDeletionRequiresApproval"])
    return {
        "dataDeletionServiceVersion": COGNIX_DATA_DELETION_SERVICE_VERSION,
        "targetType": "user",
        "targetId": username,
        "reason": _norm(reason),
        "requiresApproval": requires_approval,
        "status": "requires_approval" if requires_approval else "queued",
        "steps": [
            "revoke_sessions",
            "queue_chat_deletion",
            "queue_project_archive_or_transfer",
            "remove_memories",
            "write_privacy_event",
            "write_audit_log",
        ],
        "e2eeStrictNotice": "server_cannot_read_encrypted_content" if normalized["e2eeStrict"] else "",
        "sideEffects": build_data_retention_blueprint()["sideEffects"],
    }
