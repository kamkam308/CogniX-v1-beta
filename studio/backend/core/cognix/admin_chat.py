# SPDX-License-Identifier: AGPL-3.0-only

"""CogniX native admin chat access, policy, and audit planning."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


COGNIX_ADMIN_CHAT_SERVICE_VERSION = "cognix_admin_chat_service_v1"
COGNIX_CHAT_ACCESS_POLICY_VERSION = "cognix_chat_access_policy_v1"
COGNIX_CHAT_AUDIT_VIEWER_VERSION = "cognix_chat_audit_viewer_v1"
COGNIX_CONVERSATION_EXPORT_VERSION = "cognix_conversation_export_v1"

POLICY_MODES = {"e2ee_strict", "enterprise_compliance"}
EXPORT_FORMATS = {"json", "jsonl", "markdown"}
RISK_LEVELS = {"low", "medium", "high", "critical"}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _norm(value).lower() in {"1", "true", "yes", "on", "enabled"}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _thread_id(thread: dict[str, Any]) -> str:
    return _norm(thread.get("id") or thread.get("threadId"))


def _thread_owner(thread: dict[str, Any]) -> str:
    return _norm(thread.get("ownerUsername") or thread.get("owner_username"))


def _thread_project_id(thread: dict[str, Any]) -> str:
    return _norm(thread.get("projectId") or thread.get("project_id"))


def _thread_model_id(thread: dict[str, Any]) -> str:
    return _norm(thread.get("modelId") or thread.get("model_id") or thread.get("modelType") or thread.get("model_type"))


def _message_thread_id(message: dict[str, Any]) -> str:
    return _norm(message.get("threadId") or message.get("thread_id"))


def _message_metadata(message: dict[str, Any]) -> dict[str, Any]:
    metadata = message.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _message_content(message: dict[str, Any]) -> Any:
    return message.get("content", [])


def _listish(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _tool_call_count(message: dict[str, Any]) -> int:
    metadata = _message_metadata(message)
    candidates = [
        metadata.get("toolCalls"),
        metadata.get("tool_calls"),
        metadata.get("tools"),
        metadata.get("toolResults"),
        metadata.get("tool_results"),
    ]
    return sum(len(_listish(item)) for item in candidates if item is not None)


def _document_access_count(message: dict[str, Any]) -> int:
    metadata = _message_metadata(message)
    candidates = [
        metadata.get("documents"),
        metadata.get("documentIds"),
        metadata.get("document_ids"),
        metadata.get("retrievedDocuments"),
        metadata.get("retrieved_documents"),
        message.get("attachments"),
    ]
    return sum(len(_listish(item)) for item in candidates if item is not None)


def normalize_chat_access_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    row = policy or {}
    mode = _norm(_first(row, "mode"), "e2ee_strict").lower()
    if mode not in POLICY_MODES:
        mode = "e2ee_strict"
    admin_chat_access = _as_bool(_first(row, "admin_chat_access", "adminChatAccess", default = False))
    require_reason = _as_bool(_first(row, "require_reason", "requireReason", default = True))
    retention_days = max(1, min(_as_int(_first(row, "retention_days", "retentionDays", default = 90)) or 90, 3650))
    content_visible = mode == "enterprise_compliance" and admin_chat_access
    return {
        "policyVersion": COGNIX_CHAT_ACCESS_POLICY_VERSION,
        "mode": mode,
        "adminChatAccess": admin_chat_access,
        "requiresReason": require_reason,
        "reasonRequiredBeforeOpen": True,
        "retentionDays": retention_days,
        "contentVisible": content_visible,
        "adminCanReadContent": content_visible,
        "metadataOnly": not content_visible,
        "strictE2eeActive": not content_visible,
        "policyScope": _norm(_first(row, "policy_scope", "policyScope", default = "organization"), "organization"),
        "scopeId": _norm(_first(row, "scope_id", "scopeId", default = "default"), "default"),
        "updatedBy": _first(row, "updated_by", "updatedBy"),
        "updatedAt": _first(row, "updated_at", "updatedAt"),
    }


def build_admin_chat_blueprint() -> dict[str, Any]:
    return {
        "adminChatServiceVersion": COGNIX_ADMIN_CHAT_SERVICE_VERSION,
        "policyVersion": COGNIX_CHAT_ACCESS_POLICY_VERSION,
        "auditViewerVersion": COGNIX_CHAT_AUDIT_VIEWER_VERSION,
        "conversationExportVersion": COGNIX_CONVERSATION_EXPORT_VERSION,
        "mode": "policy_gated_admin_chat_access",
        "services": [
            "AdminChatService",
            "ChatAccessPolicyService",
            "ChatAuditViewer",
            "ConversationExportService",
        ],
        "tables": [
            "cognix_chat_access_policies",
            "cognix_admin_chat_access_logs",
            "cognix_conversation_audit_metadata",
        ],
        "permissions": [
            "admin:chats:read",
            "admin:chats:policy",
            "admin:chats:export",
        ],
        "policies": {
            "strictE2eeDefault": True,
            "contentReadableOnlyInComplianceMode": True,
            "adminAccessReasonRequired": True,
            "everyOpenIsLogged": True,
            "directoryNeverIncludesMessageContent": True,
            "exportPlanIsDryRunByDefault": True,
        },
        "sideEffects": {
            "adminAccessLogWrite": False,
            "auditMetadataWrite": False,
            "policyWrite": False,
            "auditWrite": False,
            "contentRead": False,
            "exportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _risk_from_counts(message_count: int, tool_count: int, document_count: int, stored_risk: str | None) -> str:
    normalized = _norm(stored_risk).lower()
    if normalized in RISK_LEVELS:
        return normalized
    if tool_count >= 10 or document_count >= 20:
        return "high"
    if tool_count or document_count or message_count >= 40:
        return "medium"
    return "low"


def _last_activity(thread: dict[str, Any], messages: list[dict[str, Any]]) -> Any:
    values = [_first(thread, "createdAt", "created_at")]
    values.extend(_first(message, "createdAt", "created_at") for message in messages)
    clean_values = [value for value in values if value is not None and value != ""]
    return max(clean_values, default = None)


def _project_name(projects_by_id: dict[str, dict[str, Any]], project_id: str) -> str | None:
    project = projects_by_id.get(project_id)
    if not project:
        return None
    return _norm(project.get("name") or project.get("title")) or None


def _token_total_for_thread(thread: dict[str, Any], token_events: list[dict[str, Any]]) -> int:
    owner = _thread_owner(thread)
    model_id = _thread_model_id(thread)
    project_id = _thread_project_id(thread)
    total = 0
    for event in token_events:
        if owner and _norm(event.get("username")) != owner:
            continue
        event_model = _norm(event.get("model_id") or event.get("modelId"))
        if model_id and event_model and event_model != model_id:
            continue
        event_project = _norm(event.get("project_id") or event.get("projectId"))
        if project_id and event_project and event_project != project_id:
            continue
        total += _as_int(event.get("total_tokens") or event.get("totalTokens"))
    return total


def build_conversation_audit_metadata_records(
    *,
    threads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    token_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    messages_by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        messages_by_thread[_message_thread_id(message)].append(message)
    records: list[dict[str, Any]] = []
    for thread in threads:
        thread_id = _thread_id(thread)
        thread_messages = messages_by_thread.get(thread_id, [])
        message_count = len(thread_messages)
        tool_count = sum(_tool_call_count(message) for message in thread_messages)
        document_count = sum(_document_access_count(message) for message in thread_messages)
        token_total = _token_total_for_thread(thread, token_events or [])
        risk_level = _risk_from_counts(message_count, tool_count, document_count, None)
        role_counts = Counter(_norm(message.get("role"), "unknown") for message in thread_messages)
        records.append(
            {
                "threadId": thread_id,
                "username": _thread_owner(thread),
                "projectId": _thread_project_id(thread) or None,
                "modelId": _thread_model_id(thread) or "unknown",
                "riskLevel": risk_level,
                "messageCount": message_count,
                "tokenTotal": token_total,
                "toolCallCount": tool_count,
                "documentAccessCount": document_count,
                "metadata": {
                    "roleCounts": dict(role_counts),
                    "lastActivityAt": _last_activity(thread, thread_messages),
                    "archived": _as_bool(thread.get("archived")),
                },
            }
        )
    return records


def _metadata_by_thread(audit_metadata: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in audit_metadata:
        thread_id = _norm(item.get("thread_id") or item.get("threadId"))
        if thread_id:
            result[thread_id] = item
    return result


def build_admin_chat_directory(
    *,
    threads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    token_events: list[dict[str, Any]] | None = None,
    audit_metadata: list[dict[str, Any]] | None = None,
    policy: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_policy = normalize_chat_access_policy(policy)
    filters = filters or {}
    projects_by_id = {_norm(project.get("id")): project for project in projects}
    messages_by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        messages_by_thread[_message_thread_id(message)].append(message)
    stored_metadata = _metadata_by_thread(audit_metadata or [])

    username_filter = _norm(filters.get("username"))
    project_filter = _norm(filters.get("projectId") or filters.get("project_id"))
    model_filter = _norm(filters.get("modelId") or filters.get("model_id"))
    risk_filter = _norm(filters.get("riskLevel") or filters.get("risk_level")).lower()
    rows: list[dict[str, Any]] = []
    risk_counts: Counter[str] = Counter()

    for thread in threads:
        thread_id = _thread_id(thread)
        owner = _thread_owner(thread)
        project_id = _thread_project_id(thread)
        model_id = _thread_model_id(thread)
        if username_filter and owner != username_filter:
            continue
        if project_filter and project_id != project_filter:
            continue
        if model_filter and model_id != model_filter:
            continue

        thread_messages = messages_by_thread.get(thread_id, [])
        stored = stored_metadata.get(thread_id, {})
        message_count = _as_int(_first(stored, "message_count", "messageCount", default = len(thread_messages)))
        tool_count = _as_int(_first(stored, "tool_call_count", "toolCallCount", default = 0)) or sum(
            _tool_call_count(message) for message in thread_messages
        )
        document_count = _as_int(_first(stored, "document_access_count", "documentAccessCount", default = 0)) or sum(
            _document_access_count(message) for message in thread_messages
        )
        risk_level = _risk_from_counts(message_count, tool_count, document_count, _first(stored, "risk_level", "riskLevel"))
        if risk_filter and risk_level != risk_filter:
            continue
        token_total = _as_int(_first(stored, "token_total", "tokenTotal", default = 0)) or _token_total_for_thread(
            thread,
            token_events or [],
        )
        risk_counts[risk_level] += 1
        rows.append(
            {
                "threadId": thread_id,
                "title": _norm(thread.get("title"), "New Chat"),
                "ownerUsername": owner,
                "projectId": project_id or None,
                "projectName": _project_name(projects_by_id, project_id),
                "modelType": _norm(thread.get("modelType") or thread.get("model_type")),
                "modelId": model_id,
                "archived": _as_bool(thread.get("archived")),
                "createdAt": _first(thread, "createdAt", "created_at"),
                "lastActivityAt": _last_activity(thread, thread_messages),
                "messageCount": message_count,
                "tokenTotal": token_total,
                "toolCallCount": tool_count,
                "documentAccessCount": document_count,
                "riskLevel": risk_level,
                "contentAvailable": active_policy["contentVisible"],
                "metadataOnly": active_policy["metadataOnly"],
            }
        )

    rows.sort(key = lambda item: _norm(item.get("lastActivityAt") or item.get("createdAt")), reverse = True)
    return {
        "adminChatServiceVersion": COGNIX_ADMIN_CHAT_SERVICE_VERSION,
        "auditViewerVersion": COGNIX_CHAT_AUDIT_VIEWER_VERSION,
        "policy": active_policy,
        "filters": {
            "username": username_filter or None,
            "projectId": project_filter or None,
            "modelId": model_filter or None,
            "riskLevel": risk_filter or None,
        },
        "summary": {
            "threadCount": len(rows),
            "contentVisible": active_policy["contentVisible"],
            "metadataOnly": active_policy["metadataOnly"],
            "riskCounts": dict(risk_counts),
        },
        "threads": rows,
        "sideEffects": build_admin_chat_blueprint()["sideEffects"],
    }


def _reason_required(reason: str | None) -> str:
    clean_reason = _norm(reason)
    if len(clean_reason) < 3:
        raise ValueError("A reason is required before opening admin chat access.")
    return clean_reason[:500]


def _public_message(message: dict[str, Any], *, content_visible: bool) -> dict[str, Any]:
    metadata = _message_metadata(message)
    row = {
        "id": _norm(message.get("id")),
        "threadId": _message_thread_id(message),
        "parentId": message.get("parentId") or message.get("parent_id"),
        "role": _norm(message.get("role"), "unknown"),
        "createdAt": message.get("createdAt") or message.get("created_at"),
        "toolCallCount": _tool_call_count(message),
        "documentAccessCount": _document_access_count(message),
    }
    if content_visible:
        row["content"] = _message_content(message)
        row["contentRedacted"] = False
        row["toolCalls"] = metadata.get("toolCalls") or metadata.get("tool_calls") or []
        row["documentsConsulted"] = (
            metadata.get("documents")
            or metadata.get("documentIds")
            or metadata.get("document_ids")
            or metadata.get("retrievedDocuments")
            or []
        )
    else:
        row["content"] = None
        row["contentRedacted"] = True
        row["redactionReason"] = "e2ee_strict_policy"
    return row


def build_admin_chat_detail(
    *,
    thread: dict[str, Any],
    messages: list[dict[str, Any]],
    policy: dict[str, Any] | None,
    reason: str | None,
    audit_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_reason = _reason_required(reason)
    active_policy = normalize_chat_access_policy(policy)
    content_visible = active_policy["contentVisible"]
    thread_id = _thread_id(thread)
    thread_messages = [
        message
        for message in messages
        if _message_thread_id(message) == thread_id
    ]
    thread_messages.sort(key = lambda message: (message.get("createdAt") or message.get("created_at") or 0, _norm(message.get("id"))))
    metadata_records = build_conversation_audit_metadata_records(
        threads = [thread],
        messages = thread_messages,
        token_events = [],
    )
    computed_metadata = metadata_records[0] if metadata_records else {}
    merged_metadata = {**computed_metadata, **(audit_metadata or {})}
    side_effects = {
        **build_admin_chat_blueprint()["sideEffects"],
        "contentRead": content_visible,
    }
    return {
        "adminChatServiceVersion": COGNIX_ADMIN_CHAT_SERVICE_VERSION,
        "auditViewerVersion": COGNIX_CHAT_AUDIT_VIEWER_VERSION,
        "thread": {
            "threadId": thread_id,
            "title": _norm(thread.get("title"), "New Chat"),
            "ownerUsername": _thread_owner(thread),
            "projectId": _thread_project_id(thread) or None,
            "modelType": _norm(thread.get("modelType") or thread.get("model_type")),
            "modelId": _thread_model_id(thread),
            "createdAt": _first(thread, "createdAt", "created_at"),
            "archived": _as_bool(thread.get("archived")),
        },
        "access": {
            "reason": clean_reason,
            "contentVisible": content_visible,
            "metadataOnly": not content_visible,
            "redaction": "none" if content_visible else "e2ee_strict_policy",
        },
        "policy": active_policy,
        "conversationAuditMetadata": merged_metadata,
        "messages": [_public_message(message, content_visible = content_visible) for message in thread_messages],
        "sideEffects": side_effects,
    }


def build_conversation_export_plan(
    *,
    thread: dict[str, Any],
    messages: list[dict[str, Any]],
    policy: dict[str, Any] | None,
    reason: str | None,
    output_format: str = "json",
) -> dict[str, Any]:
    clean_reason = _reason_required(reason)
    safe_format = _norm(output_format, "json").lower()
    if safe_format not in EXPORT_FORMATS:
        safe_format = "json"
    detail = build_admin_chat_detail(
        thread = thread,
        messages = messages,
        policy = policy,
        reason = clean_reason,
    )
    content_visible = detail["policy"]["contentVisible"]
    return {
        "conversationExportVersion": COGNIX_CONVERSATION_EXPORT_VERSION,
        "mode": "dry_run_export_plan",
        "dryRun": True,
        "threadId": detail["thread"]["threadId"],
        "targetUsername": detail["thread"]["ownerUsername"],
        "reason": clean_reason,
        "outputFormat": safe_format,
        "contentIncluded": content_visible,
        "sections": [
            "thread_metadata",
            "conversation_audit_metadata",
            "message_content" if content_visible else "message_metadata_only",
            "admin_access_log_reference",
        ],
        "estimatedMessageCount": len(detail["messages"]),
        "policy": detail["policy"],
        "sideEffects": {
            **build_admin_chat_blueprint()["sideEffects"],
            "contentRead": content_visible,
            "exportWrite": False,
        },
    }
