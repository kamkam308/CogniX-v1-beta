# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX product/admin state stored in the Studio SQLite database."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.paths import studio_db_path

_schema_lock = threading.Lock()
_schema_ready = False

DEVELOPER_MODE_PERMISSION = "developer_mode"
AUDIT_LOG_RETENTION_LIMIT = 5000
PERMISSION_KEY_PATTERN = re.compile(r"^[a-z0-9:_-]{1,160}$")
RATE_LIMIT_KEY_PATTERN = re.compile(r"^[a-z0-9:_-]{1,160}$")
RATE_LIMIT_EVENT_RETENTION_DAYS = 7

KNOWN_ATTACK_SIGNATURES: list[dict[str, str]] = [
    {
        "id": "sql_injection",
        "label": "SQL injection",
        "severity": "critical",
        "pattern": r"(?i)(\bunion\b\s+\bselect\b|or\s+1\s*=\s*1|--\s|/\*|\bdrop\s+table\b|\binformation_schema\b)",
    },
    {
        "id": "auth_bypass",
        "label": "Password or auth bypass",
        "severity": "critical",
        "pattern": r"(?i)(admin'\s*--|'?\s+or\s+'?1'?\s*=\s*'?1|password\s*=\s*password|jwt\s*none)",
    },
    {
        "id": "xss",
        "label": "Cross-site scripting",
        "severity": "high",
        "pattern": r"(?i)(<script\b|javascript:|onerror\s*=|onload\s*=|document\.cookie)",
    },
    {
        "id": "path_traversal",
        "label": "Path traversal",
        "severity": "high",
        "pattern": r"(?i)(\.\./|\.\.\\|%2e%2e%2f|%252e%252e|/etc/passwd|boot\.ini)",
    },
    {
        "id": "command_injection",
        "label": "Command injection",
        "severity": "critical",
        "pattern": r"(?i)(;\s*(cat|curl|wget|powershell|cmd|bash)\b|\|\s*(cat|curl|wget|powershell|cmd|bash)\b|`[^`]+`|\$\([^)]+\))",
    },
    {
        "id": "ssrf",
        "label": "SSRF attempt",
        "severity": "high",
        "pattern": r"(?i)(169\.254\.169\.254|metadata\.google\.internal|localhost:\d+|127\.0\.0\.1:\d+)",
    },
    {
        "id": "template_injection",
        "label": "Template injection",
        "severity": "high",
        "pattern": r"(?i)(\{\{.*\}\}|\$\{.*\}|<%.*%>)",
    },
    {
        "id": "scanner_probe",
        "label": "Automated scanner probe",
        "severity": "medium",
        "pattern": r"(?i)(/wp-admin|/phpmyadmin|/\.env|/cgi-bin|nikto|sqlmap|acunetix|nessus)",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def get_connection() -> sqlite3.Connection:
    ensure_schema()
    conn = sqlite3.connect(studio_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _bootstrap_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cognix_approval_requests (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            request_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            admin_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_approval_status_created
            ON cognix_approval_requests(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_approval_username
            ON cognix_approval_requests(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_permissions (
            username TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            expires_at TEXT,
            PRIMARY KEY(username, permission_key)
        );

        CREATE TABLE IF NOT EXISTS cognix_bans (
            id TEXT PRIMARY KEY,
            username TEXT,
            client_key TEXT,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_admin_review',
            temporary_until TEXT,
            admin_decision TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_bans_status_until
            ON cognix_bans(status, temporary_until);
        CREATE INDEX IF NOT EXISTS idx_cognix_bans_username
            ON cognix_bans(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_bans_client
            ON cognix_bans(client_key, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_security_events (
            id TEXT PRIMARY KEY,
            username TEXT,
            client_key TEXT,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            pattern_label TEXT NOT NULL,
            method TEXT,
            path TEXT,
            excerpt TEXT,
            ban_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_security_created
            ON cognix_security_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_security_username
            ON cognix_security_events(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_audit_logs (
            id TEXT PRIMARY KEY,
            username TEXT,
            actor_username TEXT,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_audit_created
            ON cognix_audit_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_audit_username
            ON cognix_audit_logs(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_audit_action
            ON cognix_audit_logs(action, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_rate_limit_events (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            rate_limit_key TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_rate_limit_user_key_created
            ON cognix_rate_limit_events(username, rate_limit_key, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_rate_limit_created
            ON cognix_rate_limit_events(created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_router_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            objective_excerpt TEXT NOT NULL,
            project_type TEXT,
            selected_domain TEXT NOT NULL,
            model_label TEXT NOT NULL,
            confidence REAL NOT NULL,
            needs_clarification INTEGER NOT NULL DEFAULT 0,
            routing_mode TEXT NOT NULL,
            scores_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_router_logs_created
            ON cognix_router_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_router_logs_username
            ON cognix_router_logs(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_orchestrator_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            objective_excerpt TEXT NOT NULL,
            project_type TEXT,
            project_id TEXT,
            selected_domain TEXT NOT NULL,
            recommended_path TEXT NOT NULL,
            primary_capability TEXT NOT NULL,
            provider_type TEXT,
            model_id TEXT,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            decision_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_orchestrator_logs_created
            ON cognix_orchestrator_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_orchestrator_logs_username
            ON cognix_orchestrator_logs(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_orchestrator_logs_path
            ON cognix_orchestrator_logs(recommended_path, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_benchmark_runs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            mode TEXT NOT NULL,
            overall_score REAL NOT NULL,
            estimated_tokens_per_second REAL NOT NULL,
            hardware_json TEXT NOT NULL DEFAULT '{}',
            benchmark_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_benchmark_runs_username_created
            ON cognix_benchmark_runs(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_benchmark_runs_created
            ON cognix_benchmark_runs(created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_reports (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_reports_status_created
            ON cognix_reports(status, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_context_memory (
            username TEXT PRIMARY KEY,
            content TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cognix_library_items (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            size_bytes INTEGER,
            uri TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_library_username_created
            ON cognix_library_items(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_scheduled_tasks (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            schedule_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_tasks_username_status
            ON cognix_scheduled_tasks(username, status, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_scheduled_task_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            username TEXT NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'complete',
            result TEXT NOT NULL DEFAULT '',
            artifact_type TEXT,
            artifact_id TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_task_runs_task_created
            ON cognix_scheduled_task_runs(task_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_task_runs_username_created
            ON cognix_scheduled_task_runs(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_app_connections (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            app_id TEXT NOT NULL,
            app_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'connected',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, app_id)
        );

        CREATE TABLE IF NOT EXISTS cognix_social_messages (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_social_created
            ON cognix_social_messages(created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_model_pins (
            username TEXT NOT NULL,
            model_id TEXT NOT NULL,
            label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(username, model_id)
        );

        CREATE TABLE IF NOT EXISTS cognix_project_model_defaults (
            project_id TEXT PRIMARY KEY,
            owner_username TEXT NOT NULL,
            model_id TEXT NOT NULL,
            label TEXT NOT NULL,
            provider_type TEXT,
            provider_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_model_defaults_owner
            ON cognix_project_model_defaults(owner_username, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_project_shares (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            permission TEXT NOT NULL DEFAULT 'view',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            revoked_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_shares_project
            ON cognix_project_shares(project_id, revoked_at);

        CREATE TABLE IF NOT EXISTS cognix_project_collaborators (
            id TEXT PRIMARY KEY,
            share_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            collaborator_username TEXT NOT NULL,
            permission TEXT NOT NULL DEFAULT 'view',
            status TEXT NOT NULL DEFAULT 'accepted',
            created_at TEXT NOT NULL,
            UNIQUE(share_id, collaborator_username)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_collaborators_user
            ON cognix_project_collaborators(collaborator_username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_pulse_reports (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            topics_json TEXT NOT NULL DEFAULT '[]',
            source_thread_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_pulse_username_created
            ON cognix_pulse_reports(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_image_history (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            prompt TEXT NOT NULL,
            model TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            artifact_uri TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_image_username_created
            ON cognix_image_history(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_research_reports (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            query TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'complete',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_research_username_created
            ON cognix_research_reports(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_agent_runs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            goal TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'agent',
            status TEXT NOT NULL DEFAULT 'planned',
            plan_json TEXT NOT NULL DEFAULT '[]',
            result TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_agent_username_created
            ON cognix_agent_runs(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_news_items (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            published_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_news_username_created
            ON cognix_news_items(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_game_sessions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            game_type TEXT NOT NULL,
            opponent_type TEXT NOT NULL DEFAULT 'ai',
            opponent_username TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_games_username_created
            ON cognix_game_sessions(username, created_at DESC);
        """
    )


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn = sqlite3.connect(studio_db_path())
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            _bootstrap_schema(conn)
            conn.commit()
            _schema_ready = True
        finally:
            conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def create_approval_request(username: str, request_type: str, reason: str) -> dict[str, Any]:
    created_at = _now()
    request_id = _new_id("apr")
    conn = get_connection()
    try:
        existing = conn.execute(
            """
            SELECT * FROM cognix_approval_requests
            WHERE username = ? AND request_type = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (username, request_type),
        ).fetchone()
        if existing is not None:
            return row_to_dict(existing) or {}

        conn.execute(
            """
            INSERT INTO cognix_approval_requests
                (id, username, request_type, reason, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (request_id, username, request_type, reason.strip(), created_at, created_at),
        )
        conn.commit()
        return get_approval_request(request_id) or {}
    finally:
        conn.close()


def get_approval_request(request_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_approval_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        )
    finally:
        conn.close()


def list_approval_requests(username: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_approval_requests
                WHERE username = ?
                ORDER BY created_at DESC
                """,
                (username,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_approval_requests ORDER BY created_at DESC"
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def set_approval_status(
    request_id: str,
    status: str,
    *,
    decided_by: str,
    admin_note: str | None = None,
) -> dict[str, Any] | None:
    status = status.strip().lower()
    if status not in {"pending", "approved", "denied"}:
        raise ValueError("Unsupported approval status")
    updated_at = _now()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_approval_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE cognix_approval_requests
            SET status = ?, admin_note = ?, updated_at = ?, decided_at = ?, decided_by = ?
            WHERE id = ?
            """,
            (status, admin_note, updated_at, updated_at, decided_by, request_id),
        )
        if row["request_type"] == DEVELOPER_MODE_PERMISSION:
            if status == "approved":
                conn.execute(
                    """
                    INSERT INTO cognix_user_permissions
                        (username, permission_key, granted_by, granted_at, expires_at)
                    VALUES (?, ?, ?, ?, NULL)
                    ON CONFLICT(username, permission_key) DO UPDATE SET
                        granted_by = excluded.granted_by,
                        granted_at = excluded.granted_at,
                        expires_at = excluded.expires_at
                    """,
                    (row["username"], DEVELOPER_MODE_PERMISSION, decided_by, updated_at),
                )
            else:
                remaining_approval = conn.execute(
                    """
                    SELECT 1 FROM cognix_approval_requests
                    WHERE username = ?
                      AND request_type = ?
                      AND status = 'approved'
                    LIMIT 1
                    """,
                    (row["username"], DEVELOPER_MODE_PERMISSION),
                ).fetchone()
                if remaining_approval is None:
                    conn.execute(
                        """
                        DELETE FROM cognix_user_permissions
                        WHERE username = ? AND permission_key = ?
                        """,
                        (row["username"], DEVELOPER_MODE_PERMISSION),
                    )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_approval_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        )
    finally:
        conn.close()


def _normalize_permission_key(permission_key: str) -> str:
    normalized = (permission_key or "").strip().lower()
    if not PERMISSION_KEY_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid permission key")
    return normalized


def user_has_permission(username: str, permission_key: str) -> bool:
    try:
        normalized_permission = _normalize_permission_key(permission_key)
    except ValueError:
        return False
    now = _now()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM cognix_user_permissions
            WHERE username = ? AND permission_key = ?
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (username, normalized_permission, now),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def grant_user_permission(
    username: str,
    permission_key: str,
    *,
    granted_by: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    normalized_permission = _normalize_permission_key(permission_key)
    granted_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_user_permissions
                (username, permission_key, granted_by, granted_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, permission_key) DO UPDATE SET
                granted_by = excluded.granted_by,
                granted_at = excluded.granted_at,
                expires_at = excluded.expires_at
            """,
            (username, normalized_permission, granted_by, granted_at, expires_at),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                """
                SELECT * FROM cognix_user_permissions
                WHERE username = ? AND permission_key = ?
                """,
                (username, normalized_permission),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def revoke_user_permission(username: str, permission_key: str) -> bool:
    normalized_permission = _normalize_permission_key(permission_key)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            DELETE FROM cognix_user_permissions
            WHERE username = ? AND permission_key = ?
            """,
            (username, normalized_permission),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def list_user_permissions(username: str) -> list[dict[str, Any]]:
    now = _now()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_user_permissions
            WHERE username = ?
              AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY permission_key ASC
            """,
            (username, now),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_security_events(limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_security_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def _normalize_rate_limit_key(rate_limit_key: str) -> str:
    normalized = (rate_limit_key or "").strip().lower()
    if not RATE_LIMIT_KEY_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid rate limit key")
    return normalized


def _prune_rate_limit_events(conn: sqlite3.Connection) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days = RATE_LIMIT_EVENT_RETENTION_DAYS)).isoformat()
    conn.execute(
        "DELETE FROM cognix_rate_limit_events WHERE created_at < ?",
        (cutoff,),
    )


def check_rate_limit(
    *,
    username: str,
    rate_limit_key: str,
    action: str,
    window_seconds: int,
    max_events: int,
    consume: bool = True,
) -> dict[str, Any]:
    normalized_key = _normalize_rate_limit_key(rate_limit_key)
    normalized_window = max(1, int(window_seconds))
    normalized_max = max(1, int(max_events))
    now_dt = datetime.now(timezone.utc)
    created_at = now_dt.isoformat()
    window_start = (now_dt - timedelta(seconds = normalized_window)).isoformat()
    conn = get_connection()
    try:
        _prune_rate_limit_events(conn)
        used = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM cognix_rate_limit_events
                WHERE username = ?
                  AND rate_limit_key = ?
                  AND created_at >= ?
                """,
                (username, normalized_key, window_start),
            ).fetchone()[0]
        )
        allowed = used < normalized_max
        consumed = False
        if allowed and consume:
            event_id = _new_id("rl")
            conn.execute(
                """
                INSERT INTO cognix_rate_limit_events
                    (id, username, rate_limit_key, action, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, username, normalized_key, action.strip()[:160], created_at),
            )
            used += 1
            consumed = True

        oldest = conn.execute(
            """
            SELECT created_at FROM cognix_rate_limit_events
            WHERE username = ?
              AND rate_limit_key = ?
              AND created_at >= ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (username, normalized_key, window_start),
        ).fetchone()
        if oldest is not None:
            try:
                resets_at = (
                    datetime.fromisoformat(str(oldest["created_at"]))
                    + timedelta(seconds = normalized_window)
                ).isoformat()
            except ValueError:
                resets_at = (now_dt + timedelta(seconds = normalized_window)).isoformat()
        else:
            resets_at = (now_dt + timedelta(seconds = normalized_window)).isoformat()

        conn.commit()
        return {
            "allowed": allowed,
            "rateLimitKey": normalized_key,
            "windowSeconds": normalized_window,
            "maxEvents": normalized_max,
            "used": used,
            "remaining": max(0, normalized_max - used),
            "consumed": consumed,
            "resetsAt": resets_at,
        }
    finally:
        conn.close()


def _prune_audit_logs(conn: sqlite3.Connection, max_entries: int) -> int:
    normalized_limit = max(1, int(max_entries))
    cur = conn.execute(
        """
        DELETE FROM cognix_audit_logs
        WHERE id NOT IN (
            SELECT id FROM cognix_audit_logs
            ORDER BY created_at DESC
            LIMIT ?
        )
        """,
        (normalized_limit,),
    )
    return int(cur.rowcount or 0)


def prune_audit_logs(max_entries: int = AUDIT_LOG_RETENTION_LIMIT) -> int:
    conn = get_connection()
    try:
        deleted = _prune_audit_logs(conn, max_entries)
        conn.commit()
        return deleted
    finally:
        conn.close()


def create_audit_log(
    *,
    username: str | None,
    actor_username: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _now()
    audit_id = _new_id("aud")
    normalized_severity = severity.strip().lower() or "info"
    if normalized_severity not in {"info", "notice", "warning", "critical"}:
        normalized_severity = "info"
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_audit_logs
                (
                    id,
                    username,
                    actor_username,
                    action,
                    resource_type,
                    resource_id,
                    severity,
                    metadata_json,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                username,
                actor_username,
                action.strip()[:160],
                resource_type.strip()[:120],
                (resource_id or None),
                normalized_severity,
                json.dumps(metadata or {}, ensure_ascii = False),
                created_at,
            ),
        )
        _prune_audit_logs(conn, AUDIT_LOG_RETENTION_LIMIT)
        conn.commit()
        return row_to_dict(
            conn.execute("SELECT * FROM cognix_audit_logs WHERE id = ?", (audit_id,)).fetchone()
        ) or {}
    finally:
        conn.close()


def list_audit_logs(
    *,
    username: str | None = None,
    action: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        values: list[Any] = []
        if username:
            clauses.append("username = ?")
            values.append(username)
        if action:
            clauses.append("action = ?")
            values.append(action)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_audit_logs
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*values, normalized_limit),
        ).fetchall()
        logs = _rows_to_dicts(rows)
        for log in logs:
            log["metadata"] = _json_or_default(log.get("metadata_json"), {})
        return logs
    finally:
        conn.close()


def create_router_log(
    username: str,
    objective: str,
    *,
    project_type: str | None,
    classification: dict[str, Any],
) -> dict[str, Any]:
    created_at = _now()
    log_id = _new_id("rtl")
    objective_excerpt = re.sub(r"\s+", " ", objective or "").strip()[:500]
    scores = classification.get("scores")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_router_logs
                (
                    id,
                    username,
                    objective_excerpt,
                    project_type,
                    selected_domain,
                    model_label,
                    confidence,
                    needs_clarification,
                    routing_mode,
                    scores_json,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                username,
                objective_excerpt,
                (project_type or "").strip() or None,
                str(classification.get("selectedDomain") or "general"),
                str(classification.get("recommendedModelLabel") or "CogniX General 3B"),
                float(classification.get("confidence") or 0.0),
                1 if classification.get("needsClarification") else 0,
                str(classification.get("routingMode") or "unknown"),
                json.dumps(scores if isinstance(scores, dict) else {}, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute("SELECT * FROM cognix_router_logs WHERE id = ?", (log_id,)).fetchone()
        ) or {}
    finally:
        conn.close()


def list_router_logs(username: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 500))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_router_logs
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, normalized_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_router_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (normalized_limit,),
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def create_orchestrator_log(
    username: str,
    objective: str,
    *,
    project_type: str | None,
    project_id: str | None,
    plan: dict[str, Any],
) -> dict[str, Any]:
    created_at = _now()
    log_id = _new_id("orl")
    objective_excerpt = re.sub(r"\s+", " ", objective or "").strip()[:500]
    classification = plan.get("classification") if isinstance(plan.get("classification"), dict) else {}
    task_strategy = plan.get("taskStrategy") if isinstance(plan.get("taskStrategy"), dict) else {}
    execution_strategy = (
        plan.get("executionStrategy")
        if isinstance(plan.get("executionStrategy"), dict)
        else {}
    )
    recommendation = (
        plan.get("recommendation")
        if isinstance(plan.get("recommendation"), dict)
        else {}
    )
    decision = {
        "orchestratorVersion": plan.get("orchestratorVersion"),
        "decisionEngineVersion": task_strategy.get("decisionEngineVersion"),
        "mode": plan.get("mode"),
        "selectedDomain": classification.get("selectedDomain"),
        "recommendedPath": task_strategy.get("path"),
        "primaryCapability": task_strategy.get("primaryCapability"),
        "requiresHumanConfirmation": task_strategy.get("requiresHumanConfirmation"),
        "uses": task_strategy.get("uses"),
        "status": execution_strategy.get("status"),
        "sideEffects": plan.get("sideEffects"),
        "warnings": plan.get("warnings") or [],
    }
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_orchestrator_logs
                (
                    id,
                    username,
                    objective_excerpt,
                    project_type,
                    project_id,
                    selected_domain,
                    recommended_path,
                    primary_capability,
                    provider_type,
                    model_id,
                    status,
                    confidence,
                    decision_json,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                username,
                objective_excerpt,
                (project_type or "").strip() or None,
                (project_id or "").strip() or None,
                str(classification.get("selectedDomain") or "general"),
                str(task_strategy.get("path") or "expert_chat"),
                str(task_strategy.get("primaryCapability") or "model_router"),
                recommendation.get("providerType"),
                recommendation.get("modelId"),
                str(execution_strategy.get("status") or "unknown"),
                float(task_strategy.get("confidence") or 0.0),
                json.dumps(decision, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_orchestrator_logs WHERE id = ?",
                (log_id,),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_orchestrator_logs(username: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 500))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_orchestrator_logs
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, normalized_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_orchestrator_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (normalized_limit,),
            ).fetchall()
        logs = _rows_to_dicts(rows)
        for log in logs:
            log["decision"] = _json_or_default(log.get("decision_json"), {})
        return logs
    finally:
        conn.close()


def create_benchmark_run(username: str, benchmark: dict[str, Any]) -> dict[str, Any]:
    created_at = _now()
    run_id = _new_id("bnc")
    hardware = benchmark.get("hardware") if isinstance(benchmark.get("hardware"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_benchmark_runs
                (
                    id,
                    username,
                    mode,
                    overall_score,
                    estimated_tokens_per_second,
                    hardware_json,
                    benchmark_json,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                username,
                str(benchmark.get("mode") or "quick"),
                float(benchmark.get("overallScore") or 0.0),
                float(benchmark.get("estimatedTokensPerSecond") or 0.0),
                json.dumps(hardware, ensure_ascii = False),
                json.dumps(benchmark, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_benchmark_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return _benchmark_row(row_to_dict(row) or {})
    finally:
        conn.close()


def _benchmark_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["hardware"] = _json_or_default(item.get("hardware_json"), {})
    item["benchmark"] = _json_or_default(item.get("benchmark_json"), {})
    return item


def list_benchmark_runs(username: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 200))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_benchmark_runs
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, normalized_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_benchmark_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (normalized_limit,),
            ).fetchall()
        return [_benchmark_row(dict(row)) for row in rows]
    finally:
        conn.close()


def list_bans() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM cognix_bans ORDER BY created_at DESC").fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def update_ban_status(
    ban_id: str,
    status: str,
    *,
    decided_by: str,
    admin_decision: str | None = None,
) -> dict[str, Any] | None:
    status = status.strip().lower()
    if status not in {"pending_admin_review", "active", "cleared", "permanent"}:
        raise ValueError("Unsupported ban status")
    updated_at = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE cognix_bans
            SET status = ?,
                admin_decision = ?,
                temporary_until = CASE
                    WHEN ? IN ('cleared', 'permanent') THEN NULL
                    ELSE temporary_until
                END,
                updated_at = ?,
                decided_at = ?,
                decided_by = ?
            WHERE id = ?
            """,
            (status, admin_decision, status, updated_at, updated_at, decided_by, ban_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return row_to_dict(conn.execute("SELECT * FROM cognix_bans WHERE id = ?", (ban_id,)).fetchone())
    finally:
        conn.close()


def create_report(username: str, category: str, title: str, message: str) -> dict[str, Any]:
    created_at = _now()
    report_id = _new_id("rep")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_reports
                (id, username, category, title, message, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (report_id, username, category.strip(), title.strip(), message.strip(), created_at, created_at),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_reports WHERE id = ?", (report_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_reports(username: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if username:
            rows = conn.execute(
                "SELECT * FROM cognix_reports WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM cognix_reports ORDER BY created_at DESC").fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def update_report_status(report_id: str, status: str) -> dict[str, Any] | None:
    status = status.strip().lower()
    if status not in {"open", "in_review", "resolved", "closed"}:
        raise ValueError("Unsupported report status")
    updated_at = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE cognix_reports SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, report_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return row_to_dict(conn.execute("SELECT * FROM cognix_reports WHERE id = ?", (report_id,)).fetchone())
    finally:
        conn.close()


def get_context_memory(username: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_context_memory WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return {"username": username, "content": "", "updated_at": None, "updated_by": None}
        return dict(row)
    finally:
        conn.close()


def update_context_memory(username: str, content: str, updated_by: str) -> dict[str, Any]:
    updated_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_context_memory (username, content, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (username, content, updated_at, updated_by),
        )
        conn.commit()
        return get_context_memory(username)
    finally:
        conn.close()


def _json_or_default(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def list_library_items(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cognix_library_items WHERE username = ? ORDER BY created_at DESC",
            (username,),
        ).fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return items
    finally:
        conn.close()


def create_library_item(
    username: str,
    *,
    kind: str,
    name: str,
    source: str = "manual",
    size_bytes: int | None = None,
    uri: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _now()
    item_id = _new_id("lib")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_library_items
                (id, username, kind, name, source, size_bytes, uri, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                username,
                kind,
                name.strip(),
                source,
                size_bytes,
                uri,
                json.dumps(metadata or {}, ensure_ascii = False),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_library_items WHERE id = ?", (item_id,)).fetchone()
        item = row_to_dict(row) or {}
        item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return item
    finally:
        conn.close()


def list_scheduled_tasks(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        return _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_scheduled_tasks WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
    finally:
        conn.close()


def get_scheduled_task(username: str, task_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_scheduled_tasks WHERE id = ? AND username = ?",
                (task_id, username),
            ).fetchone()
        )
    finally:
        conn.close()


def create_scheduled_task(username: str, title: str, prompt: str, schedule_text: str) -> dict[str, Any]:
    created_at = _now()
    task_id = _new_id("tsk")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_scheduled_tasks
                (id, username, title, prompt, schedule_text, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (task_id, username, title.strip(), prompt.strip(), schedule_text.strip(), created_at, created_at),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_scheduled_tasks WHERE id = ?", (task_id,)).fetchone()) or {}
    finally:
        conn.close()


def update_scheduled_task_status(username: str, task_id: str, status: str) -> dict[str, Any] | None:
    if status not in {"active", "paused", "done", "cancelled"}:
        raise ValueError("Unsupported task status")
    updated_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cognix_scheduled_tasks SET status = ?, updated_at = ? WHERE id = ? AND username = ?",
            (status, updated_at, task_id, username),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_scheduled_tasks WHERE id = ? AND username = ?",
                (task_id, username),
            ).fetchone()
        )
    finally:
        conn.close()


def list_scheduled_task_runs(username: str, task_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if task_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_scheduled_task_runs
                WHERE username = ? AND task_id = ?
                ORDER BY created_at DESC
                LIMIT 80
                """,
                (username, task_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_scheduled_task_runs
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT 120
                """,
                (username,),
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def create_scheduled_task_run(
    username: str,
    task_id: str,
    action_type: str,
    result: str,
    artifact_type: str | None = None,
    artifact_id: str | None = None,
    status: str = "complete",
) -> dict[str, Any]:
    if status not in {"complete", "failed"}:
        raise ValueError("Unsupported task run status")
    now = _now()
    run_id = _new_id("run")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_scheduled_task_runs
                (id, task_id, username, action_type, status, result, artifact_type, artifact_id, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task_id,
                username,
                action_type,
                status,
                result.strip(),
                artifact_type,
                artifact_id,
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE cognix_scheduled_tasks SET updated_at = ? WHERE id = ? AND username = ?",
            (now, task_id, username),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_scheduled_task_runs WHERE id = ?", (run_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_app_connections(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        return _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_app_connections WHERE username = ? ORDER BY updated_at DESC",
                (username,),
            ).fetchall()
        )
    finally:
        conn.close()


def set_app_connection(username: str, app_id: str, app_name: str, status: str) -> dict[str, Any]:
    if status not in {"connected", "disabled"}:
        raise ValueError("Unsupported app connection status")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_app_connections (id, username, app_id, app_name, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, app_id) DO UPDATE SET
                app_name = excluded.app_name,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (_new_id("app"), username, app_id, app_name, status, now, now),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_app_connections WHERE username = ? AND app_id = ?",
                (username, app_id),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_social_messages(limit: int = 80) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cognix_social_messages ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
        return list(reversed(_rows_to_dicts(rows)))
    finally:
        conn.close()


def create_social_message(username: str, display_name: str, role: str, content: str) -> dict[str, Any]:
    created_at = _now()
    message_id = _new_id("soc")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_social_messages (id, username, display_name, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, username, display_name or username, role or "user", content.strip(), created_at),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_social_messages WHERE id = ?", (message_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_model_pins(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        return _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_model_pins WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
    finally:
        conn.close()


def set_model_pin(username: str, model_id: str, label: str) -> dict[str, Any]:
    created_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_model_pins (username, model_id, label, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, model_id) DO UPDATE SET
                label = excluded.label
            """,
            (username, model_id, label or model_id, created_at),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_model_pins WHERE username = ? AND model_id = ?",
                (username, model_id),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def delete_model_pin(username: str, model_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM cognix_model_pins WHERE username = ? AND model_id = ?",
            (username, model_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_project_model_defaults(owner_username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_project_model_defaults
            WHERE owner_username = ?
            ORDER BY updated_at DESC
            """,
            (owner_username,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_project_model_default(project_id: str, owner_username: str | None = None) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        if owner_username:
            row = conn.execute(
                """
                SELECT * FROM cognix_project_model_defaults
                WHERE project_id = ? AND owner_username = ?
                """,
                (project_id, owner_username),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM cognix_project_model_defaults WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def set_project_model_default(
    owner_username: str,
    project_id: str,
    model_id: str,
    label: str,
    *,
    provider_type: str | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    normalized_project_id = project_id.strip()
    normalized_model_id = model_id.strip()
    normalized_label = (label or normalized_model_id).strip() or normalized_model_id
    if not normalized_project_id:
        raise ValueError("Project id is required")
    if not normalized_model_id:
        raise ValueError("Model id is required")

    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_model_defaults
                (
                    project_id,
                    owner_username,
                    model_id,
                    label,
                    provider_type,
                    provider_id,
                    created_at,
                    updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                owner_username = excluded.owner_username,
                model_id = excluded.model_id,
                label = excluded.label,
                provider_type = excluded.provider_type,
                provider_id = excluded.provider_id,
                updated_at = excluded.updated_at
            """,
            (
                normalized_project_id,
                owner_username,
                normalized_model_id,
                normalized_label,
                (provider_type or "").strip() or None,
                (provider_id or "").strip() or None,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_project_model_defaults WHERE project_id = ?",
                (normalized_project_id,),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def delete_project_model_default(owner_username: str, project_id: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            DELETE FROM cognix_project_model_defaults
            WHERE project_id = ? AND owner_username = ?
            """,
            (project_id, owner_username),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def create_project_share(owner_username: str, project_id: str, permission: str = "view") -> dict[str, Any]:
    if permission not in {"view", "edit"}:
        raise ValueError("Unsupported share permission")
    now = _now()
    share_id = _new_id("shr")
    token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_shares
                (id, project_id, owner_username, token, permission, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (share_id, project_id, owner_username, token, permission, now, now),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_project_shares WHERE id = ?", (share_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_project_shares(owner_username: str, project_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_project_shares
                WHERE owner_username = ? AND project_id = ?
                ORDER BY created_at DESC
                """,
                (owner_username, project_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_project_shares
                WHERE owner_username = ?
                ORDER BY created_at DESC
                """,
                (owner_username,),
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_project_share_by_token(token: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        return row_to_dict(
            conn.execute(
                """
                SELECT * FROM cognix_project_shares
                WHERE token = ?
                LIMIT 1
                """,
                (token,),
            ).fetchone()
        )
    finally:
        conn.close()


def list_project_collaborators(owner_username: str | None = None, collaborator_username: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if owner_username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_project_collaborators
                WHERE owner_username = ?
                ORDER BY created_at DESC
                """,
                (owner_username,),
            ).fetchall()
        elif collaborator_username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_project_collaborators
                WHERE collaborator_username = ?
                ORDER BY created_at DESC
                """,
                (collaborator_username,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_project_collaborators ORDER BY created_at DESC"
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def accept_project_share(token: str, collaborator_username: str) -> dict[str, Any] | None:
    share = get_project_share_by_token(token)
    if not share or share.get("revoked_at"):
        return None
    now = _now()
    collab_id = _new_id("col")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_collaborators
                (id, share_id, project_id, owner_username, collaborator_username, permission, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'accepted', ?)
            ON CONFLICT(share_id, collaborator_username) DO UPDATE SET
                permission = excluded.permission,
                status = 'accepted'
            """,
            (
                collab_id,
                share["id"],
                share["project_id"],
                share["owner_username"],
                collaborator_username,
                share["permission"],
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                """
                SELECT * FROM cognix_project_collaborators
                WHERE share_id = ? AND collaborator_username = ?
                """,
                (share["id"], collaborator_username),
            ).fetchone()
        )
    finally:
        conn.close()


def revoke_project_share(owner_username: str, share_id: str) -> dict[str, Any] | None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cognix_project_shares SET revoked_at = ?, updated_at = ? WHERE id = ? AND owner_username = ?",
            (now, now, share_id, owner_username),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_project_shares WHERE id = ? AND owner_username = ?",
                (share_id, owner_username),
            ).fetchone()
        )
    finally:
        conn.close()


def list_pulse_reports(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        reports = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_pulse_reports WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
        for report in reports:
            report["topics"] = _json_or_default(report.get("topics_json"), [])
            report["sourceThreadIds"] = _json_or_default(report.get("source_thread_ids_json"), [])
        return reports
    finally:
        conn.close()


def create_pulse_report(
    username: str,
    title: str,
    summary: str,
    topics: list[str],
    source_thread_ids: list[str],
) -> dict[str, Any]:
    created_at = _now()
    report_id = _new_id("pul")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_pulse_reports
                (id, username, title, summary, topics_json, source_thread_ids_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                username,
                title.strip(),
                summary.strip(),
                json.dumps(topics, ensure_ascii = False),
                json.dumps(source_thread_ids, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        reports = list_pulse_reports(username)
        for report in reports:
            if report.get("id") == report_id:
                return report
        return {}
    finally:
        conn.close()


def list_image_history(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        return _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_image_history WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
    finally:
        conn.close()


def create_image_request(username: str, prompt: str, model: str | None = None) -> dict[str, Any]:
    now = _now()
    request_id = _new_id("img")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_image_history
                (id, username, prompt, model, status, artifact_uri, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'queued', NULL, ?, ?)
            """,
            (request_id, username, prompt.strip(), model, now, now),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_image_history WHERE id = ?", (request_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_research_reports(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        reports = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_research_reports WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
        for report in reports:
            report["sources"] = _json_or_default(report.get("sources_json"), [])
        return reports
    finally:
        conn.close()


def create_research_report(
    username: str,
    query: str,
    title: str,
    summary: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    created_at = _now()
    report_id = _new_id("res")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_research_reports
                (id, username, query, title, summary, sources_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'complete', ?)
            """,
            (
                report_id,
                username,
                query.strip(),
                title.strip(),
                summary.strip(),
                json.dumps(sources, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        reports = list_research_reports(username)
        for report in reports:
            if report.get("id") == report_id:
                return report
        return {}
    finally:
        conn.close()


def list_agent_runs(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        runs = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_agent_runs WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
        for run in runs:
            run["plan"] = _json_or_default(run.get("plan_json"), [])
        return runs
    finally:
        conn.close()


def create_agent_run(
    username: str,
    goal: str,
    mode: str,
    plan: list[str],
    result: str,
    status: str = "planned",
) -> dict[str, Any]:
    if status not in {"planned", "running", "complete", "failed"}:
        raise ValueError("Unsupported agent status")
    now = _now()
    run_id = _new_id("agt")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_agent_runs
                (id, username, goal, mode, status, plan_json, result, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                username,
                goal.strip(),
                mode.strip() or "agent",
                status,
                json.dumps(plan, ensure_ascii = False),
                result.strip(),
                now,
                now,
            ),
        )
        conn.commit()
        runs = list_agent_runs(username)
        for run in runs:
            if run.get("id") == run_id:
                return run
        return {}
    finally:
        conn.close()


def list_news_items(username: str, topic: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if topic:
            rows = conn.execute(
                """
                SELECT * FROM cognix_news_items
                WHERE username = ? AND topic = ?
                ORDER BY COALESCE(published_at, created_at) DESC
                LIMIT 80
                """,
                (username, topic),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_news_items
                WHERE username = ?
                ORDER BY COALESCE(published_at, created_at) DESC
                LIMIT 80
                """,
                (username,),
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def create_news_item(
    username: str,
    topic: str,
    title: str,
    summary: str,
    url: str,
    source: str,
    published_at: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    item_id = _new_id("new")
    conn = get_connection()
    try:
        existing = conn.execute(
            """
            SELECT * FROM cognix_news_items
            WHERE username = ? AND url = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (username, url),
        ).fetchone()
        if existing:
            item = row_to_dict(existing) or {}
            return item
        conn.execute(
            """
            INSERT INTO cognix_news_items
                (id, username, topic, title, summary, url, source, published_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                username,
                topic.strip() or "ai",
                title.strip(),
                summary.strip(),
                url.strip(),
                source.strip(),
                published_at,
                created_at,
            ),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_news_items WHERE id = ?", (item_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_game_sessions(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        games = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_game_sessions WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
        for game in games:
            game["state"] = _json_or_default(game.get("state_json"), {})
        return games
    finally:
        conn.close()


def get_game_session(username: str, game_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        game = row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_game_sessions WHERE id = ? AND username = ?",
                (game_id, username),
            ).fetchone()
        )
        if game:
            game["state"] = _json_or_default(game.get("state_json"), {})
        return game
    finally:
        conn.close()


def create_game_session(
    username: str,
    game_type: str,
    opponent_type: str,
    opponent_username: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if game_type not in {"chess", "quiz", "code_duel"}:
        raise ValueError("Unsupported game type")
    if opponent_type not in {"ai", "user"}:
        raise ValueError("Unsupported opponent type")
    now = _now()
    game_id = _new_id("gam")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_game_sessions
                (id, username, game_type, opponent_type, opponent_username, status, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                username,
                game_type,
                opponent_type,
                opponent_username,
                "active" if opponent_type == "ai" else "pending",
                json.dumps(state or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        games = list_game_sessions(username)
        for game in games:
            if game.get("id") == game_id:
                return game
        return {}
    finally:
        conn.close()


def update_game_session(
    username: str,
    game_id: str,
    *,
    status: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    if status not in {"pending", "active", "complete", "cancelled"}:
        raise ValueError("Unsupported game status")
    updated_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE cognix_game_sessions
            SET status = ?, state_json = ?, updated_at = ?
            WHERE id = ? AND username = ?
            """,
            (status, json.dumps(state, ensure_ascii = False), updated_at, game_id, username),
        )
        conn.commit()
        return get_game_session(username, game_id)
    finally:
        conn.close()


def detect_known_attack(value: str) -> dict[str, str] | None:
    if not value:
        return None
    sample = value[:12000]
    for signature in KNOWN_ATTACK_SIGNATURES:
        if re.search(signature["pattern"], sample):
            return {
                "category": signature["id"],
                "severity": signature["severity"],
                "pattern_label": signature["label"],
            }
    return None


def record_security_event(
    *,
    username: str | None,
    client_key: str | None,
    category: str,
    severity: str,
    pattern_label: str,
    method: str | None,
    path: str | None,
    excerpt: str | None,
    create_temporary_ban: bool = False,
) -> dict[str, Any]:
    created_at = _now()
    event_id = _new_id("sec")
    ban_id = None
    conn = get_connection()
    try:
        if create_temporary_ban:
            ban_id = _new_id("ban")
            temporary_until = (datetime.now(timezone.utc) + timedelta(hours = 24)).isoformat()
            conn.execute(
                """
                INSERT INTO cognix_bans
                    (id, username, client_key, reason, status, temporary_until, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending_admin_review', ?, ?, ?)
                """,
                (
                    ban_id,
                    username,
                    client_key,
                    f"{pattern_label} detected",
                    temporary_until,
                    created_at,
                    created_at,
                ),
            )
        conn.execute(
            """
            INSERT INTO cognix_security_events
                (id, username, client_key, category, severity, pattern_label, method, path, excerpt, ban_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                username,
                client_key,
                category,
                severity,
                pattern_label,
                method,
                path,
                (excerpt or "")[:1000],
                ban_id,
                created_at,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute("SELECT * FROM cognix_security_events WHERE id = ?", (event_id,)).fetchone()
        ) or {}
    finally:
        conn.close()


def active_ban_for(username: str | None, client_key: str | None) -> dict[str, Any] | None:
    now = _now()
    clauses = []
    values: list[Any] = []
    if username:
        clauses.append("username = ?")
        values.append(username)
    if client_key:
        clauses.append("client_key = ?")
        values.append(client_key)
    if not clauses:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            f"""
            SELECT * FROM cognix_bans
            WHERE ({' OR '.join(clauses)})
              AND (
                status IN ('pending_admin_review', 'permanent')
                OR (
                    status = 'active'
                    AND (temporary_until IS NULL OR temporary_until > ?)
                )
              )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (*values, now),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def summarize_compute_usage(threads: list[dict[str, Any]], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_thread = {str(thread.get("id")): thread for thread in threads}
    summary: dict[tuple[str, str], dict[str, Any]] = {}

    def _new_usage_item(owner: str, model: str) -> dict[str, Any]:
        return {
            "username": owner,
            "ownerUsername": owner,
            "model": model,
            "modelId": model,
            "conversations": 0,
            "messages": 0,
            "estimatedTokens": 0,
            "approxTokens": 0,
            "lastUsedAt": None,
        }

    def _touch(item: dict[str, Any], timestamp: Any) -> None:
        if timestamp is None:
            return
        try:
            value = int(timestamp)
        except (TypeError, ValueError):
            return
        current = item.get("lastUsedAt")
        if current is None or value > int(current):
            item["lastUsedAt"] = value

    for thread in threads:
        owner = str(thread.get("ownerUsername") or "unknown")
        model = str(thread.get("modelId") or thread.get("modelType") or "unknown")
        key = (owner, model)
        item = summary.setdefault(key, _new_usage_item(owner, model))
        item["conversations"] += 1
        _touch(item, thread.get("updatedAt") or thread.get("createdAt"))
    for message in messages:
        thread = by_thread.get(str(message.get("threadId")))
        if not thread:
            continue
        owner = str(thread.get("ownerUsername") or "unknown")
        model = str(thread.get("modelId") or thread.get("modelType") or "unknown")
        key = (owner, model)
        item = summary.setdefault(key, _new_usage_item(owner, model))
        item["messages"] += 1
        text = json.dumps(message.get("content") or "", ensure_ascii = False)
        estimated = max(1, len(text) // 4)
        item["estimatedTokens"] += estimated
        item["approxTokens"] += estimated
        _touch(item, message.get("createdAt"))
    return sorted(summary.values(), key = lambda item: (item["username"], item["model"]))
