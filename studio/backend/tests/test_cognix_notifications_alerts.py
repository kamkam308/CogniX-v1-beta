from __future__ import annotations

import asyncio
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage as auth_storage
from core.cognix import api_surface as cognix_api_surface
from core.cognix import module_registry as cognix_module_registry
from core.cognix import notifications as cognix_notifications
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(tmp_path / "project_workspaces"))
    monkeypatch.setattr(auth_storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth_storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(auth_storage, "_bootstrap_password", None)
    monkeypatch.setattr(auth_storage, "_api_key_pbkdf2_salt_cache", None)
    monkeypatch.setattr(cognix_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False


def run_async(coro):
    return asyncio.run(coro)


def seed_accounts() -> None:
    auth_storage.create_initial_user(
        username = auth_storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    auth_storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )


def test_notifications_blueprint_schema_registry_and_surface_contract():
    blueprint = cognix_notifications.build_notification_blueprint()
    assert blueprint["notificationServiceVersion"] == "cognix_notification_service_v1"
    assert blueprint["adminAlertServiceVersion"] == "cognix_admin_alert_service_v1"
    assert blueprint["userNotificationPreferencesVersion"] == "cognix_user_notification_preferences_v1"
    assert blueprint["services"] == ["NotificationService", "AdminAlertService", "UserNotificationPreferences"]
    assert blueprint["tables"] == ["notifications", "notification_preferences", "admin_alerts"]
    assert {"approval_requested", "approval_approved", "critical_security", "chat_mention"}.issubset(
        {item["id"] for item in blueprint["notificationTypes"]}
    )
    assert blueprint["deliveryPolicy"]["externalPushSendAllowed"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_global_roadmap_tables(conn)
        cognix_db._ensure_notification_columns(conn)
        notification_columns = {row[1] for row in conn.execute("PRAGMA table_info(notifications)").fetchall()}
        preference_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(notification_preferences)").fetchall()
        }
        alert_columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_alerts)").fetchall()}
        assert {"notification_type", "title", "message", "read_at"}.issubset(notification_columns)
        assert {"notification_type", "enabled", "channels_json"}.issubset(preference_columns)
        assert {"alert_type", "severity", "acknowledged_by", "acknowledged_at"}.issubset(alert_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    background = modules["cognix-background-agents"]
    operations = modules["cognix-admin-operations"]
    assert "notification_service" in background["capabilities"]
    assert "user_notification_preferences" in background["capabilities"]
    assert "admin_alert_service" in operations["capabilities"]
    assert "approval_alert_notifications" in operations["capabilities"]
    assert "/api/cognix/notifications" in background["routes"]
    assert "/api/cognix/admin/alerts" in operations["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/notifications", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/notifications"]["status"] == "equivalent"
    assert routes["/notifications"]["matchedRoute"] == "/api/cognix/notifications"


def test_approval_notifications_alerts_preferences_and_read_state():
    seed_accounts()

    with pytest.raises(HTTPException) as user_admin_alerts:
        run_async(cognix_routes.admin_alerts(current_subject = "alice"))
    assert user_admin_alerts.value.status_code == 403

    created = run_async(
        cognix_routes.create_approval_request(
            cognix_routes.ApprovalCreateRequest(
                requestType = "cloud_training",
                title = "Use Colab",
                reason = "Need an online resource for a small experiment.",
                riskLevel = "high",
                resourceType = "training",
                resourceId = "colab",
            ),
            current_subject = "alice",
        )
    )
    assert created["sideEffects"]["notificationWrite"] is True
    assert created["sideEffects"]["adminAlertWrite"] is True
    assert created["notification"]["notificationType"] == "approval_requested"
    assert created["adminAlert"]["alertType"] == "approval_requested"

    user_notifications = run_async(cognix_routes.my_notifications(current_subject = "alice"))
    admin_alerts = run_async(cognix_routes.admin_alerts(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert user_notifications["summary"]["unreadNotificationCount"] == 1
    assert user_notifications["notifications"][0]["notificationType"] == "approval_requested"
    assert admin_alerts["summary"]["openAdminAlertCount"] == 1

    preference = run_async(
        cognix_routes.update_my_notification_preference(
            "approval_requested",
            cognix_routes.NotificationPreferenceRequest(enabled = False, channels = ["in_app"]),
            current_subject = "alice",
        )
    )
    assert preference["preference"]["notificationType"] == "approval_requested"
    assert preference["preference"]["enabled"] is False
    assert preference["sideEffects"]["preferenceWrite"] is True

    decided = run_async(
        cognix_routes.admin_decide_approval(
            created["request"]["id"],
            cognix_routes.ApprovalDecisionRequest(status = "approved", admin_note = "Approved for online test."),
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert decided["notification"]["notificationType"] == "approval_approved"
    assert decided["adminAlert"]["alertType"] == "approval_approved"

    refreshed = run_async(cognix_routes.my_notifications(current_subject = "alice"))
    notification_types = {item["notificationType"] for item in refreshed["notifications"]}
    assert {"approval_requested", "approval_approved"}.issubset(notification_types)

    read = run_async(
        cognix_routes.mark_my_notification_read(
            refreshed["notifications"][0]["id"],
            current_subject = "alice",
        )
    )
    acknowledged = run_async(
        cognix_routes.admin_acknowledge_alert(
            admin_alerts["alerts"][0]["id"],
            current_subject = auth_storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert read["notification"]["readAt"]
    assert acknowledged["alert"]["status"] == "acknowledged"
    assert acknowledged["sideEffects"]["adminAlertWrite"] is True
