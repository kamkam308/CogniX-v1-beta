# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX sensitive action audit contracts."""

from __future__ import annotations

from typing import Any


COGNIX_SENSITIVE_AUDIT_VERSION = "cognix_sensitive_audit_v1"
COGNIX_AUDIT_LOG_SERVICE_VERSION = "cognix_audit_log_service_v1"
COGNIX_SENSITIVE_ACTION_LOGGER_VERSION = "cognix_sensitive_action_logger_v1"
COGNIX_AUDIT_SEARCH_SERVICE_VERSION = "cognix_audit_search_service_v1"

SENSITIVE_AUDIT_SERVICES = [
    "AuditLogService",
    "SensitiveActionLogger",
    "AuditSearchService",
]

SENSITIVE_AUDIT_TABLES = [
    "audit_logs",
    "sensitive_action_logs",
]

SENSITIVE_ACTION_CATALOG: list[dict[str, Any]] = [
    {
        "id": "admin_chat_read",
        "label": "Admin chat read",
        "keywords": ["admin_chat", "chat_access", "chat_thread_viewed", "conversation_read"],
        "severity": "warning",
    },
    {
        "id": "permissions_modified",
        "label": "Permission modification",
        "keywords": ["permission", "role_permission", "override"],
        "severity": "warning",
    },
    {
        "id": "user_ban",
        "label": "User ban or reactivation",
        "keywords": ["ban", "banned", "reactivation"],
        "severity": "warning",
    },
    {
        "id": "project_deletion",
        "label": "Project deletion",
        "keywords": ["project_deleted", "delete_project", "project_delete"],
        "severity": "critical",
    },
    {
        "id": "cloud_activation",
        "label": "Cloud activation",
        "keywords": ["cloud_activation", "cloud_provider", "remote_training", "colab", "kaggle"],
        "severity": "warning",
    },
    {
        "id": "app_connection",
        "label": "App connection",
        "keywords": ["app_connection", "installed_app", "connector", "integration"],
        "severity": "warning",
    },
    {
        "id": "tool_execution",
        "label": "Tool execution",
        "keywords": ["tool_execution", "tool_execute", "tools_execute", "tool_plan"],
        "severity": "warning",
    },
    {
        "id": "cowork_control",
        "label": "Cowork control",
        "keywords": ["cowork"],
        "severity": "critical",
    },
    {
        "id": "codex_code_modification",
        "label": "Codex code modification",
        "keywords": ["codex", "code_modification", "code_patch", "file_edit", "github_push"],
        "severity": "critical",
    },
    {
        "id": "scheduled_sensitive_task",
        "label": "Scheduled sensitive task",
        "keywords": ["scheduled_sensitive", "scheduled_task", "scheduled_run"],
        "severity": "warning",
    },
]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def classify_sensitive_action(
    action: str,
    *,
    resource_type: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    haystack = " ".join(
        [
            _norm(action),
            _norm(resource_type),
            " ".join(_norm(key) for key in (metadata or {}).keys()),
            _norm((metadata or {}).get("sensitiveAction")),
            _norm((metadata or {}).get("actionCategory")),
        ]
    )
    matches: list[dict[str, Any]] = []
    for category in SENSITIVE_ACTION_CATALOG:
        keywords = [str(item) for item in category.get("keywords", [])]
        matched_keywords = [keyword for keyword in keywords if keyword in haystack]
        if matched_keywords:
            matches.append(
                {
                    "id": category["id"],
                    "label": category["label"],
                    "severity": category["severity"],
                    "matchedKeywords": matched_keywords,
                }
            )
    if not matches:
        return {
            "sensitive": False,
            "category": None,
            "severity": "info",
            "matchedKeywords": [],
            "immutableByStandardAdmin": True,
            "requiredTables": SENSITIVE_AUDIT_TABLES,
        }
    selected = sorted(matches, key = lambda item: item["severity"] == "critical", reverse = True)[0]
    return {
        "sensitive": True,
        "category": selected["id"],
        "categoryLabel": selected["label"],
        "severity": selected["severity"],
        "matchedKeywords": selected["matchedKeywords"],
        "immutableByStandardAdmin": True,
        "requiredTables": SENSITIVE_AUDIT_TABLES,
    }


def build_sensitive_audit_blueprint(
    *,
    audit_logs: list[dict[str, Any]] | None = None,
    sensitive_action_logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    audit_count = len(audit_logs or [])
    sensitive_count = len(sensitive_action_logs or [])
    categories = sorted(
        {
            str(item.get("sensitiveCategory") or item.get("sensitive_category") or "")
            for item in sensitive_action_logs or []
            if item.get("sensitiveCategory") or item.get("sensitive_category")
        }
    )
    return {
        "sensitiveAuditVersion": COGNIX_SENSITIVE_AUDIT_VERSION,
        "auditLogServiceVersion": COGNIX_AUDIT_LOG_SERVICE_VERSION,
        "sensitiveActionLoggerVersion": COGNIX_SENSITIVE_ACTION_LOGGER_VERSION,
        "auditSearchServiceVersion": COGNIX_AUDIT_SEARCH_SERVICE_VERSION,
        "mode": "native_sensitive_action_audit",
        "services": SENSITIVE_AUDIT_SERVICES,
        "tables": SENSITIVE_AUDIT_TABLES,
        "sensitiveActions": SENSITIVE_ACTION_CATALOG,
        "summary": {
            "auditLogCount": audit_count,
            "sensitiveActionLogCount": sensitive_count,
            "sensitiveCategoryCount": len(categories),
            "categoriesObserved": categories,
        },
        "immutabilityPolicy": {
            "standardAdminMutationAllowed": False,
            "appendOnly": True,
            "deleteRouteExposed": False,
            "metadataRedactionRequired": True,
        },
        "sideEffects": {
            "auditWrite": False,
            "sensitiveActionWrite": False,
            "auditMutation": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }
