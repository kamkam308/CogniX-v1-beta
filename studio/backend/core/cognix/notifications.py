# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX notifications and approval alert contracts."""

from __future__ import annotations

from typing import Any


COGNIX_NOTIFICATION_SERVICE_VERSION = "cognix_notification_service_v1"
COGNIX_ADMIN_ALERT_SERVICE_VERSION = "cognix_admin_alert_service_v1"
COGNIX_USER_NOTIFICATION_PREFERENCES_VERSION = "cognix_user_notification_preferences_v1"

NOTIFICATION_SERVICES = [
    "NotificationService",
    "AdminAlertService",
    "UserNotificationPreferences",
]

NOTIFICATION_TABLES = [
    "notifications",
    "notification_preferences",
    "admin_alerts",
]

NOTIFICATION_TYPES: list[dict[str, Any]] = [
    {"id": "approval_requested", "audience": ["user", "admin"], "priority": "high"},
    {"id": "approval_approved", "audience": ["user", "admin"], "priority": "normal"},
    {"id": "approval_denied", "audience": ["user", "admin"], "priority": "high"},
    {"id": "quota_near_limit", "audience": ["user", "admin"], "priority": "high"},
    {"id": "critical_security", "audience": ["admin"], "priority": "critical"},
    {"id": "scheduled_task_completed", "audience": ["user"], "priority": "normal"},
    {"id": "codex_report_available", "audience": ["user", "admin"], "priority": "normal"},
    {"id": "project_shared", "audience": ["user"], "priority": "normal"},
    {"id": "chat_mention", "audience": ["user"], "priority": "normal"},
]


def _norm(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_notification_type(notification_type: str) -> str:
    normalized = _norm(notification_type).lower().replace(" ", "_").replace("-", "_")
    known = {item["id"] for item in NOTIFICATION_TYPES}
    return normalized if normalized in known else "codex_report_available"


def notification_priority(notification_type: str, fallback: str = "normal") -> str:
    normalized = normalize_notification_type(notification_type)
    for item in NOTIFICATION_TYPES:
        if item["id"] == normalized:
            return str(item.get("priority") or fallback)
    return fallback


def build_notification_blueprint(
    *,
    notifications: list[dict[str, Any]] | None = None,
    admin_alerts: list[dict[str, Any]] | None = None,
    preferences: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    unread = sum(1 for item in notifications or [] if not item.get("readAt") and not item.get("read_at"))
    open_alerts = sum(1 for item in admin_alerts or [] if str(item.get("status") or "") in {"open", "active"})
    return {
        "notificationServiceVersion": COGNIX_NOTIFICATION_SERVICE_VERSION,
        "adminAlertServiceVersion": COGNIX_ADMIN_ALERT_SERVICE_VERSION,
        "userNotificationPreferencesVersion": COGNIX_USER_NOTIFICATION_PREFERENCES_VERSION,
        "mode": "native_notification_alert_pipeline",
        "services": NOTIFICATION_SERVICES,
        "tables": NOTIFICATION_TABLES,
        "notificationTypes": NOTIFICATION_TYPES,
        "summary": {
            "notificationCount": len(notifications or []),
            "unreadNotificationCount": unread,
            "adminAlertCount": len(admin_alerts or []),
            "openAdminAlertCount": open_alerts,
            "preferenceCount": len(preferences or []),
        },
        "deliveryPolicy": {
            "inAppCenter": True,
            "adminAlertCenter": True,
            "preferenceAware": True,
            "externalPushSendAllowed": False,
            "emailSendAllowedHere": False,
        },
        "sideEffects": {
            "notificationWrite": False,
            "adminAlertWrite": False,
            "preferenceWrite": False,
            "auditWrite": False,
            "externalSend": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_approval_notification_payload(
    *,
    request: dict[str, Any],
    event: str,
    actor_username: str | None = None,
) -> dict[str, Any]:
    notification_type = normalize_notification_type(event)
    request_type = _norm(request.get("request_type") or request.get("requestType") or "approval")
    title = _norm(request.get("title") or request_type or "Approval")
    username = _norm(request.get("username"))
    status = _norm(request.get("status") or "pending")
    actor = _norm(actor_username)
    if notification_type == "approval_requested":
        message = f"Approval requested: {title}."
    elif notification_type == "approval_approved":
        message = f"Approval accepted for {title}."
    elif notification_type == "approval_denied":
        message = f"Approval refused for {title}."
    else:
        message = f"Approval update for {title}: {status}."
    return {
        "notificationType": notification_type,
        "title": title,
        "message": message,
        "priority": notification_priority(notification_type),
        "sourceType": "cognix_approval_request",
        "sourceId": str(request.get("id") or ""),
        "username": username,
        "actorUsername": actor,
        "status": status,
        "requestType": request_type,
    }
