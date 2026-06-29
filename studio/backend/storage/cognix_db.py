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
            title TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL,
            risk_level TEXT NOT NULL DEFAULT 'medium',
            resource_type TEXT NOT NULL DEFAULT '',
            resource_id TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
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

        CREATE TABLE IF NOT EXISTS cognix_approval_decisions (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            status TEXT NOT NULL,
            decided_by TEXT NOT NULL,
            admin_note TEXT NOT NULL DEFAULT '',
            policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_approval_decisions_request
            ON cognix_approval_decisions(request_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_approval_comments (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            username TEXT NOT NULL,
            comment TEXT NOT NULL,
            visibility TEXT NOT NULL DEFAULT 'admin',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_approval_comments_request
            ON cognix_approval_comments(request_id, created_at ASC);

        CREATE TABLE IF NOT EXISTS cognix_user_permissions (
            username TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            expires_at TEXT,
            PRIMARY KEY(username, permission_key)
        );

        CREATE TABLE IF NOT EXISTS cognix_user_limits (
            username TEXT NOT NULL,
            limit_key TEXT NOT NULL,
            limit_value REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT 'user',
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(username, limit_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_limits_username
            ON cognix_user_limits(username, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_quotas (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            quota_key TEXT NOT NULL,
            quota_value REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL DEFAULT 'custom',
            status TEXT NOT NULL DEFAULT 'active',
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, quota_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_quotas_username
            ON cognix_user_quotas(username, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_role_quotas (
            id TEXT PRIMARY KEY,
            role_key TEXT NOT NULL,
            quota_key TEXT NOT NULL,
            quota_value REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL DEFAULT 'custom',
            status TEXT NOT NULL DEFAULT 'active',
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(role_key, quota_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_role_quotas_role
            ON cognix_role_quotas(role_key, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_roles (
            id TEXT PRIMARY KEY,
            role_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_roles_status
            ON cognix_roles(status, role_key);

        CREATE TABLE IF NOT EXISTS cognix_permissions (
            id TEXT PRIMARY KEY,
            permission_key TEXT NOT NULL UNIQUE,
            module_key TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            risk_level TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_permissions_module
            ON cognix_permissions(module_key, risk_level);

        CREATE TABLE IF NOT EXISTS cognix_role_permissions (
            id TEXT PRIMARY KEY,
            role_key TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(role_key, permission_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_role_permissions_role
            ON cognix_role_permissions(role_key, permission_key);

        CREATE TABLE IF NOT EXISTS cognix_user_permission_overrides (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            effect TEXT NOT NULL DEFAULT 'allow',
            reason TEXT NOT NULL DEFAULT '',
            expires_at TEXT,
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, permission_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_permission_overrides_user
            ON cognix_user_permission_overrides(username, permission_key);

        CREATE TABLE IF NOT EXISTS cognix_project_permissions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, subject_type, subject_id, permission_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_permissions_subject
            ON cognix_project_permissions(project_id, subject_type, subject_id);

        CREATE TABLE IF NOT EXISTS cognix_quota_usage (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            quota_key TEXT NOT NULL,
            period_key TEXT NOT NULL,
            used_value REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, quota_key, period_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_quota_usage_username
            ON cognix_quota_usage(username, quota_key, period_key);

        CREATE TABLE IF NOT EXISTS cognix_quota_overrides (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            quota_key TEXT NOT NULL,
            quota_value REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL DEFAULT 'custom',
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            expires_at TEXT,
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_quota_overrides_target
            ON cognix_quota_overrides(target_type, target_id, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_activity_events (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            event_type TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_activity_events_username_created
            ON cognix_user_activity_events(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_activity_daily (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            day TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            model_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            document_access_count INTEGER NOT NULL DEFAULT 0,
            active_project_count INTEGER NOT NULL DEFAULT 0,
            token_total INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            sensitive_action_count INTEGER NOT NULL DEFAULT 0,
            active_minutes INTEGER NOT NULL DEFAULT 0,
            activity_score REAL NOT NULL DEFAULT 0,
            models_json TEXT NOT NULL DEFAULT '[]',
            projects_json TEXT NOT NULL DEFAULT '[]',
            actions_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            UNIQUE(username, day)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_activity_daily_username_day
            ON cognix_user_activity_daily(username, day DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_user_activity_daily_day
            ON cognix_user_activity_daily(day DESC);

        CREATE TABLE IF NOT EXISTS cognix_organization_activity_daily (
            id TEXT PRIMARY KEY,
            day TEXT NOT NULL UNIQUE,
            active_user_count INTEGER NOT NULL DEFAULT 0,
            message_count INTEGER NOT NULL DEFAULT 0,
            token_total INTEGER NOT NULL DEFAULT 0,
            model_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            document_access_count INTEGER NOT NULL DEFAULT 0,
            active_project_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            sensitive_action_count INTEGER NOT NULL DEFAULT 0,
            active_minutes INTEGER NOT NULL DEFAULT 0,
            top_users_json TEXT NOT NULL DEFAULT '[]',
            models_json TEXT NOT NULL DEFAULT '[]',
            projects_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_organization_activity_daily_day
            ON cognix_organization_activity_daily(day DESC);

        CREATE TABLE IF NOT EXISTS cognix_token_usage_events (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            model_id TEXT NOT NULL DEFAULT 'unknown',
            provider TEXT NOT NULL DEFAULT 'local',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            latency_ms REAL NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_token_usage_events_username_created
            ON cognix_token_usage_events(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_token_usage_events_model_created
            ON cognix_token_usage_events(model_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_admin_user_views (
            id TEXT PRIMARY KEY,
            target_username TEXT NOT NULL,
            viewed_by TEXT NOT NULL,
            view_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_admin_user_views_target_created
            ON cognix_admin_user_views(target_username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_chat_access_policies (
            id TEXT PRIMARY KEY,
            policy_scope TEXT NOT NULL DEFAULT 'organization',
            scope_id TEXT NOT NULL DEFAULT 'default',
            mode TEXT NOT NULL DEFAULT 'e2ee_strict',
            admin_chat_access INTEGER NOT NULL DEFAULT 0,
            require_reason INTEGER NOT NULL DEFAULT 1,
            retention_days INTEGER NOT NULL DEFAULT 90,
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(policy_scope, scope_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_chat_access_policies_scope
            ON cognix_chat_access_policies(policy_scope, scope_id);

        CREATE TABLE IF NOT EXISTS cognix_admin_chat_access_logs (
            id TEXT PRIMARY KEY,
            admin_username TEXT NOT NULL,
            target_username TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            access_mode TEXT NOT NULL DEFAULT 'metadata_only',
            content_visible INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_admin_chat_access_logs_target
            ON cognix_admin_chat_access_logs(target_username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_admin_chat_access_logs_admin
            ON cognix_admin_chat_access_logs(admin_username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_admin_chat_access_logs_thread
            ON cognix_admin_chat_access_logs(thread_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_conversation_audit_metadata (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            project_id TEXT,
            model_id TEXT NOT NULL DEFAULT 'unknown',
            risk_level TEXT NOT NULL DEFAULT 'low',
            message_count INTEGER NOT NULL DEFAULT 0,
            token_total INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            document_access_count INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_conversation_audit_username
            ON cognix_conversation_audit_metadata(username, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_conversation_audit_project
            ON cognix_conversation_audit_metadata(project_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_conversation_audit_risk
            ON cognix_conversation_audit_metadata(risk_level, updated_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_security_threats (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_id TEXT,
            category TEXT NOT NULL DEFAULT 'vulnerabilities_detected',
            title TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            summary TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            files_json TEXT NOT NULL DEFAULT '[]',
            recommended_solution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_security_threats_status
            ON cognix_security_threats(status, severity, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_security_threats_source
            ON cognix_security_threats(source_type, source_id);

        CREATE TABLE IF NOT EXISTS cognix_security_reports (
            id TEXT PRIMARY KEY,
            threat_id TEXT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            impact TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_security_reports_status
            ON cognix_security_reports(status, severity, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_security_reports_threat
            ON cognix_security_reports(threat_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_vulnerability_findings (
            id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL DEFAULT '',
            package_name TEXT NOT NULL DEFAULT '',
            installed_version TEXT NOT NULL DEFAULT '',
            fixed_version TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            description TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_vulnerability_findings_status
            ON cognix_vulnerability_findings(status, severity, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_vulnerability_findings_package
            ON cognix_vulnerability_findings(package_name, source_name);

        CREATE TABLE IF NOT EXISTS cognix_security_remediation_tasks (
            id TEXT PRIMARY KEY,
            threat_id TEXT,
            finding_id TEXT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            priority TEXT NOT NULL DEFAULT 'medium',
            recommended_solution TEXT NOT NULL DEFAULT '',
            assignee TEXT NOT NULL DEFAULT '',
            due_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_security_remediation_status
            ON cognix_security_remediation_tasks(status, priority, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_security_remediation_refs
            ON cognix_security_remediation_tasks(threat_id, finding_id);

        CREATE TABLE IF NOT EXISTS cognix_ban_reports (
            id TEXT PRIMARY KEY,
            ban_id TEXT NOT NULL,
            username TEXT,
            risk_level TEXT NOT NULL DEFAULT 'medium',
            summary TEXT NOT NULL DEFAULT '',
            detected_behavior TEXT NOT NULL DEFAULT '',
            violated_rules_json TEXT NOT NULL DEFAULT '[]',
            recommendation TEXT NOT NULL DEFAULT '',
            report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(ban_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_ban_reports_ban
            ON cognix_ban_reports(ban_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_ban_evidence_logs (
            id TEXT PRIMARY KEY,
            ban_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            excerpt TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_ban_evidence_ban
            ON cognix_ban_evidence_logs(ban_id, created_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_system_decisions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            project_id TEXT,
            decision_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            explanation_json TEXT NOT NULL DEFAULT '{}',
            decision_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_system_decisions_username_created
            ON cognix_system_decisions(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_system_decisions_source
            ON cognix_system_decisions(username, source_type, source_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_system_decisions_project
            ON cognix_system_decisions(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_decision_reasons (
            id TEXT PRIMARY KEY,
            decision_id TEXT NOT NULL,
            username TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            label TEXT NOT NULL,
            detail TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_decision_reasons_decision
            ON cognix_decision_reasons(decision_id, created_at ASC);
        CREATE INDEX IF NOT EXISTS idx_cognix_decision_reasons_username_code
            ON cognix_decision_reasons(username, reason_code, created_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_runtime_metrics (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            model_id TEXT,
            runtime_type TEXT NOT NULL DEFAULT 'unknown',
            ram_used_percent REAL,
            cpu_used_percent REAL,
            gpu_available INTEGER NOT NULL DEFAULT 0,
            tokens_per_second REAL,
            latency_ms REAL,
            load_time_ms REAL,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_runtime_metrics_username_created
            ON cognix_runtime_metrics(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_runtime_metrics_project
            ON cognix_runtime_metrics(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_model_performance_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            model_id TEXT,
            project_id TEXT,
            event_type TEXT NOT NULL,
            tokens_per_second REAL,
            latency_ms REAL,
            load_time_ms REAL,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_model_performance_logs_username_created
            ON cognix_model_performance_logs(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_model_variants (
            id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            variant_id TEXT NOT NULL,
            quantization TEXT NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(model_id, variant_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_model_variants_model
            ON cognix_model_variants(model_id, quantization);

        CREATE TABLE IF NOT EXISTS cognix_quantization_profiles (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            priority TEXT NOT NULL,
            model_id TEXT NOT NULL,
            selected_variant_id TEXT NOT NULL,
            quantization TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned_no_execution',
            plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_quantization_profiles_username_created
            ON cognix_quantization_profiles(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_quantization_profiles_project
            ON cognix_quantization_profiles(username, project_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_provider_profiles (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            execution_target TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            pricing_json TEXT NOT NULL DEFAULT '{}',
            policy_json TEXT NOT NULL DEFAULT '{}',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_provider_profiles_target
            ON cognix_provider_profiles(execution_target, status);

        CREATE TABLE IF NOT EXISTS cognix_execution_cost_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            objective_excerpt TEXT NOT NULL,
            selected_provider_id TEXT NOT NULL,
            selected_execution_target TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned_no_execution',
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            estimated_latency_ms INTEGER NOT NULL DEFAULT 0,
            sensitivity_level TEXT NOT NULL DEFAULT 'low',
            decision_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_execution_cost_logs_username_created
            ON cognix_execution_cost_logs(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_execution_cost_logs_project
            ON cognix_execution_cost_logs(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_model_conversions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            source_model_id TEXT NOT NULL,
            source_format TEXT NOT NULL,
            target_format TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned_no_execution',
            compatibility_status TEXT NOT NULL DEFAULT 'unknown',
            plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_model_conversions_username_created
            ON cognix_model_conversions(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_model_conversions_project
            ON cognix_model_conversions(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_conversion_logs (
            id TEXT PRIMARY KEY,
            conversion_id TEXT NOT NULL,
            username TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_conversion_logs_conversion
            ON cognix_conversion_logs(username, conversion_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_plugins (
            id TEXT PRIMARY KEY,
            plugin_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL,
            publisher TEXT NOT NULL,
            version TEXT NOT NULL,
            signature_status TEXT NOT NULL DEFAULT 'unknown',
            status TEXT NOT NULL DEFAULT 'planned',
            manifest_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_plugins_category
            ON cognix_plugins(category, display_name COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS cognix_installed_plugins (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            plugin_id TEXT NOT NULL,
            project_id TEXT,
            target_scope TEXT NOT NULL DEFAULT 'user',
            status TEXT NOT NULL DEFAULT 'planned_no_install',
            install_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_installed_plugins_username
            ON cognix_installed_plugins(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_installed_plugins_project
            ON cognix_installed_plugins(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_plugin_permissions (
            id TEXT PRIMARY KEY,
            installation_id TEXT NOT NULL,
            username TEXT NOT NULL,
            plugin_id TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            risk_level TEXT NOT NULL DEFAULT 'medium',
            granted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_plugin_permissions_installation
            ON cognix_plugin_permissions(username, installation_id);

        CREATE TABLE IF NOT EXISTS cognix_plugin_reviews (
            id TEXT PRIMARY KEY,
            installation_id TEXT NOT NULL,
            username TEXT NOT NULL,
            plugin_id TEXT NOT NULL,
            review_type TEXT NOT NULL,
            status TEXT NOT NULL,
            risk_level TEXT NOT NULL DEFAULT 'medium',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_plugin_reviews_installation
            ON cognix_plugin_reviews(username, installation_id, created_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_memory_candidates (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            candidate_key TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            category TEXT NOT NULL,
            label TEXT NOT NULL,
            value TEXT NOT NULL,
            evidence_excerpt TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending_validation',
            candidate_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_memory_candidates_username_status
            ON cognix_memory_candidates(username, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_memory_candidates_project
            ON cognix_memory_candidates(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_skill_memories (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            category TEXT NOT NULL,
            label TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            source_candidate_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_skill_memories_username_status
            ON cognix_user_skill_memories(username, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_preferences (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            category TEXT NOT NULL,
            value TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            source_candidate_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, preference_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_preferences_username_status
            ON cognix_user_preferences(username, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_personal_ai_profiles (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'disabled',
            profile_json TEXT NOT NULL DEFAULT '{}',
            controls_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_personal_ai_profiles_status
            ON cognix_personal_ai_profiles(username, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_style_profiles (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            style_key TEXT NOT NULL,
            style_value TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE(username, profile_id, style_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_style_profiles_profile
            ON cognix_style_profiles(username, profile_id, style_key);

        CREATE TABLE IF NOT EXISTS cognix_personalization_rules (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            rule_key TEXT NOT NULL,
            rule_type TEXT NOT NULL,
            rule_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            confidence REAL NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, profile_id, rule_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_personalization_rules_profile
            ON cognix_personalization_rules(username, profile_id, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_memories (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            category TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            sensitive INTEGER NOT NULL DEFAULT 0,
            current_version INTEGER NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_memories_username_status
            ON cognix_memories(username, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_memories_category
            ON cognix_memories(username, category, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_memory_versions (
            id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            username TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            change_reason TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_memory_versions_memory
            ON cognix_memory_versions(username, memory_id, version_number DESC);

        CREATE TABLE IF NOT EXISTS cognix_memory_audit_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            memory_id TEXT,
            action TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_memory_audit_username_created
            ON cognix_memory_audit_logs(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_workflows (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            title TEXT NOT NULL,
            objective TEXT NOT NULL DEFAULT '',
            workflow_type TEXT NOT NULL DEFAULT 'custom',
            status TEXT NOT NULL DEFAULT 'active',
            share_status TEXT NOT NULL DEFAULT 'private',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_workflows_username_status
            ON cognix_workflows(username, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_workflows_project
            ON cognix_workflows(username, project_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_workflow_steps (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            username TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            step_type TEXT NOT NULL,
            label TEXT NOT NULL,
            tool_name TEXT,
            model_id TEXT,
            parameters_json TEXT NOT NULL DEFAULT '{}',
            output_summary TEXT NOT NULL DEFAULT '',
            step_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_workflow_steps_workflow
            ON cognix_workflow_steps(username, workflow_id, step_index);

        CREATE TABLE IF NOT EXISTS cognix_workflow_runs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            run_mode TEXT NOT NULL DEFAULT 'dry_run',
            run_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_workflow_runs_workflow
            ON cognix_workflow_runs(username, workflow_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_workflow_run_logs (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            username TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            step_id TEXT,
            level TEXT NOT NULL DEFAULT 'info',
            message TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_workflow_run_logs_run
            ON cognix_workflow_run_logs(username, run_id, created_at);

        CREATE TABLE IF NOT EXISTS cognix_compressed_contexts (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            context_hash TEXT NOT NULL,
            objective_excerpt TEXT NOT NULL DEFAULT '',
            original_token_count INTEGER NOT NULL DEFAULT 0,
            compressed_token_count INTEGER NOT NULL DEFAULT 0,
            reduction_ratio REAL NOT NULL DEFAULT 0,
            compressed_context TEXT NOT NULL DEFAULT '',
            ranking_json TEXT NOT NULL DEFAULT '[]',
            evaluation_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_compressed_contexts_username_created
            ON cognix_compressed_contexts(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_compressed_contexts_project
            ON cognix_compressed_contexts(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_compression_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            compressed_context_id TEXT,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_compression_logs_context
            ON cognix_compression_logs(username, compressed_context_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_context_usage_stats (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            chunk_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            usage_count INTEGER NOT NULL DEFAULT 0,
            response_count INTEGER NOT NULL DEFAULT 0,
            citation_count INTEGER NOT NULL DEFAULT 0,
            utility_score REAL NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, project_id, chunk_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_context_usage_stats_username_project
            ON cognix_context_usage_stats(username, project_id, utility_score DESC);

        CREATE TABLE IF NOT EXISTS cognix_context_heatmap_entries (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            chunk_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            utility_score REAL NOT NULL DEFAULT 0,
            bucket TEXT NOT NULL DEFAULT 'low_usage',
            recommended_action TEXT NOT NULL DEFAULT 'review',
            theme_token TEXT NOT NULL DEFAULT 'warning',
            entry_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, project_id, chunk_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_context_heatmap_entries_project
            ON cognix_context_heatmap_entries(username, project_id, bucket, utility_score DESC);

        CREATE TABLE IF NOT EXISTS cognix_memory_cleanup_suggestions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            memory_id TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending_review',
            suggestion_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_memory_cleanup_suggestions_user
            ON cognix_memory_cleanup_suggestions(username, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_memory_cleanup_suggestions_project
            ON cognix_memory_cleanup_suggestions(username, project_id, status, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_memory_conflicts (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            conflict_type TEXT NOT NULL,
            memory_ids_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending_review',
            conflict_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_memory_conflicts_user
            ON cognix_memory_conflicts(username, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_memory_conflicts_project
            ON cognix_memory_conflicts(username, project_id, status, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_generated_datasets (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            objective_excerpt TEXT NOT NULL DEFAULT '',
            output_format TEXT NOT NULL DEFAULT 'jsonl',
            status TEXT NOT NULL DEFAULT 'review_required',
            example_count INTEGER NOT NULL DEFAULT 0,
            ready_example_count INTEGER NOT NULL DEFAULT 0,
            review_example_count INTEGER NOT NULL DEFAULT 0,
            quality_summary_json TEXT NOT NULL DEFAULT '{}',
            data_sources_json TEXT NOT NULL DEFAULT '[]',
            export_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_generated_datasets_username_created
            ON cognix_generated_datasets(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_generated_datasets_project
            ON cognix_generated_datasets(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_dataset_examples (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            username TEXT NOT NULL,
            instruction TEXT NOT NULL DEFAULT '',
            input TEXT NOT NULL DEFAULT '',
            output TEXT NOT NULL DEFAULT '',
            quality_score REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'review',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_dataset_examples_dataset
            ON cognix_dataset_examples(username, dataset_id, quality_score DESC);

        CREATE TABLE IF NOT EXISTS cognix_dataset_quality_scores (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            example_id TEXT,
            username TEXT NOT NULL,
            quality_score REAL NOT NULL DEFAULT 0,
            quality_label TEXT NOT NULL DEFAULT 'review',
            signals_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_dataset_quality_scores_dataset
            ON cognix_dataset_quality_scores(username, dataset_id, quality_score DESC);

        CREATE TABLE IF NOT EXISTS cognix_personas (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            tone TEXT NOT NULL,
            level TEXT NOT NULL,
            preferred_model TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            config_json TEXT NOT NULL DEFAULT '{}',
            system_prompt TEXT NOT NULL DEFAULT '',
            tool_permissions_json TEXT NOT NULL DEFAULT '{}',
            memory_scope_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_personas_username_created
            ON cognix_personas(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_persona_versions (
            id TEXT PRIMARY KEY,
            persona_id TEXT NOT NULL,
            username TEXT NOT NULL,
            version_number INTEGER NOT NULL DEFAULT 1,
            template_version TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            system_prompt TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_persona_versions_persona
            ON cognix_persona_versions(username, persona_id, version_number DESC);

        CREATE TABLE IF NOT EXISTS cognix_persona_project_bindings (
            id TEXT PRIMARY KEY,
            persona_id TEXT NOT NULL,
            username TEXT NOT NULL,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            binding_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, persona_id, project_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_persona_project_bindings_project
            ON cognix_persona_project_bindings(username, project_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_gpts (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            preferred_model TEXT,
            privacy_level TEXT NOT NULL DEFAULT 'private',
            share_scope TEXT NOT NULL DEFAULT 'private',
            icon TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            config_json TEXT NOT NULL DEFAULT '{}',
            instructions TEXT NOT NULL DEFAULT '',
            runtime_instructions TEXT NOT NULL DEFAULT '',
            tool_binding_json TEXT NOT NULL DEFAULT '{}',
            document_binding_json TEXT NOT NULL DEFAULT '{}',
            memory_binding_json TEXT NOT NULL DEFAULT '{}',
            permission_binding_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_gpts_username_created
            ON cognix_gpts(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_gpt_versions (
            id TEXT PRIMARY KEY,
            gpt_id TEXT NOT NULL,
            username TEXT NOT NULL,
            version_number INTEGER NOT NULL DEFAULT 1,
            manager_version TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            runtime_instructions TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_gpt_versions_gpt
            ON cognix_gpt_versions(username, gpt_id, version_number DESC);

        CREATE TABLE IF NOT EXISTS cognix_gpt_project_bindings (
            id TEXT PRIMARY KEY,
            gpt_id TEXT NOT NULL,
            username TEXT NOT NULL,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            binding_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, gpt_id, project_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_gpt_project_bindings_project
            ON cognix_gpt_project_bindings(username, project_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_gpt_usage_logs (
            id TEXT PRIMARY KEY,
            gpt_id TEXT NOT NULL,
            username TEXT NOT NULL,
            project_id TEXT,
            objective_excerpt TEXT NOT NULL DEFAULT '',
            runtime_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_gpt_usage_logs_gpt
            ON cognix_gpt_usage_logs(username, gpt_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_command_usage_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            command_id TEXT NOT NULL,
            command_label TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            query TEXT NOT NULL DEFAULT '',
            result_status TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_command_usage_logs_username_created
            ON cognix_command_usage_logs(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_intent_predictions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            project_type TEXT,
            selected_domain TEXT NOT NULL,
            confidence_score REAL NOT NULL DEFAULT 0,
            input_excerpt TEXT NOT NULL DEFAULT '',
            probabilities_json TEXT NOT NULL DEFAULT '[]',
            suggestion_json TEXT NOT NULL DEFAULT '{}',
            preload_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_intent_predictions_username_created
            ON cognix_intent_predictions(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_intent_predictions_project
            ON cognix_intent_predictions(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_preload_events (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            prediction_id TEXT,
            project_id TEXT,
            event_type TEXT NOT NULL,
            target_model_id TEXT,
            status TEXT NOT NULL DEFAULT 'planned_no_execution',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_preload_events_username_created
            ON cognix_preload_events(username, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_project_ui_profiles (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            project_type TEXT NOT NULL,
            profile_key TEXT NOT NULL,
            viewport TEXT NOT NULL DEFAULT 'desktop',
            theme TEXT NOT NULL DEFAULT 'dark',
            profile_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_ui_profiles_username_created
            ON cognix_project_ui_profiles(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_project_ui_profiles_project
            ON cognix_project_ui_profiles(username, project_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_user_layout_preferences (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            value_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, preference_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_layout_preferences_username
            ON cognix_user_layout_preferences(username, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_background_jobs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            job_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority TEXT NOT NULL DEFAULT 'normal',
            progress_percent INTEGER NOT NULL DEFAULT 0,
            job_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_background_jobs_username_status
            ON cognix_background_jobs(username, status, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_background_agent_runs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            runner_type TEXT NOT NULL DEFAULT 'AgentRunner',
            run_plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_background_agent_runs_job
            ON cognix_background_agent_runs(username, job_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_background_job_logs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            job_id TEXT NOT NULL,
            run_id TEXT,
            level TEXT NOT NULL DEFAULT 'info',
            message TEXT NOT NULL,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_background_job_logs_job
            ON cognix_background_job_logs(username, job_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_project_timeline_events (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            source_type TEXT,
            source_id TEXT,
            importance TEXT NOT NULL DEFAULT 'normal',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_timeline_username_project
            ON cognix_project_timeline_events(username, project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_project_timeline_type
            ON cognix_project_timeline_events(username, event_type, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_simulation_runs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            project_type TEXT,
            simulation_type TEXT NOT NULL,
            scenario TEXT NOT NULL,
            user_count INTEGER NOT NULL DEFAULT 1,
            duration_minutes INTEGER NOT NULL DEFAULT 15,
            status TEXT NOT NULL DEFAULT 'planned',
            plan_json TEXT NOT NULL DEFAULT '{}',
            report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_simulation_runs_username_created
            ON cognix_simulation_runs(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_simulation_runs_project
            ON cognix_simulation_runs(username, project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_simulation_runs_type
            ON cognix_simulation_runs(username, simulation_type, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_simulation_metrics (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            run_id TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            metric_value REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'low',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_simulation_metrics_run
            ON cognix_simulation_metrics(username, run_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_sandboxes (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            target_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            badge_label TEXT NOT NULL DEFAULT 'Mode sandbox actif',
            isolation_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_sandboxes_username_created
            ON cognix_sandboxes(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_sandboxes_project
            ON cognix_sandboxes(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_sandbox_runs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            sandbox_id TEXT NOT NULL,
            project_id TEXT,
            target_type TEXT NOT NULL,
            objective TEXT NOT NULL,
            change_summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planned_no_execution',
            plan_json TEXT NOT NULL DEFAULT '{}',
            pipeline_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_sandbox_runs_username_created
            ON cognix_sandbox_runs(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_sandbox_runs_project
            ON cognix_sandbox_runs(username, project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_sandbox_runs_type
            ON cognix_sandbox_runs(username, target_type, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_sandbox_reports (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            sandbox_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            risk_level TEXT NOT NULL DEFAULT 'low',
            report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_sandbox_reports_run
            ON cognix_sandbox_reports(username, run_id, created_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_response_evaluations (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            message_id TEXT,
            thread_id TEXT,
            project_id TEXT,
            model_id TEXT,
            confidence_score REAL NOT NULL,
            confidence_label TEXT NOT NULL,
            verification_required INTEGER NOT NULL DEFAULT 0,
            recommended_action TEXT NOT NULL,
            issues_json TEXT NOT NULL DEFAULT '[]',
            evaluation_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_response_eval_username_created
            ON cognix_response_evaluations(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_response_eval_message
            ON cognix_response_evaluations(username, message_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_response_variants (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            message_id TEXT,
            thread_id TEXT,
            project_id TEXT,
            variant_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            model_id TEXT,
            ranking_score REAL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_response_variants_username_created
            ON cognix_response_variants(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_response_variants_message
            ON cognix_response_variants(username, message_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_debate_sessions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            message_id TEXT,
            thread_id TEXT,
            project_id TEXT,
            prompt_excerpt TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planned',
            max_rounds INTEGER NOT NULL DEFAULT 3,
            roles_json TEXT NOT NULL DEFAULT '[]',
            plan_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_debate_sessions_username_created
            ON cognix_debate_sessions(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_debate_sessions_message
            ON cognix_debate_sessions(username, message_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_debate_rounds (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            username TEXT NOT NULL,
            round_index INTEGER NOT NULL,
            role_id TEXT NOT NULL,
            label TEXT NOT NULL,
            purpose TEXT NOT NULL,
            public_prompt TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_debate_rounds_session
            ON cognix_debate_rounds(session_id, round_index);

        CREATE TABLE IF NOT EXISTS cognix_debate_outputs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            round_id TEXT,
            username TEXT NOT NULL,
            role_id TEXT NOT NULL,
            output_type TEXT NOT NULL,
            public_summary TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            model_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_debate_outputs_session
            ON cognix_debate_outputs(session_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_tool_capabilities (
            id TEXT PRIMARY KEY,
            tool_id TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            label TEXT NOT NULL,
            category TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tool_id, capability_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_tool_capabilities_tool
            ON cognix_tool_capabilities(tool_id, category);

        CREATE TABLE IF NOT EXISTS cognix_installed_tools (
            username TEXT NOT NULL,
            tool_id TEXT NOT NULL,
            tool_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'installed',
            source TEXT NOT NULL DEFAULT 'manual',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(username, tool_id)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_installed_tools_username_status
            ON cognix_installed_tools(username, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_tool_recommendations (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            need_id TEXT NOT NULL,
            tool_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            category TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            recommendation_json TEXT NOT NULL DEFAULT '{}',
            ignored INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_tool_recommendations_username_created
            ON cognix_tool_recommendations(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_tool_recommendations_project
            ON cognix_tool_recommendations(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_context_graph_snapshots (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            title TEXT NOT NULL,
            graph_json TEXT NOT NULL DEFAULT '{}',
            node_count INTEGER NOT NULL DEFAULT 0,
            edge_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_context_graph_snapshots_username_created
            ON cognix_context_graph_snapshots(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_context_graph_snapshots_project
            ON cognix_context_graph_snapshots(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_context_nodes (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            username TEXT NOT NULL,
            project_id TEXT,
            node_key TEXT NOT NULL,
            node_type TEXT NOT NULL,
            label TEXT NOT NULL,
            source TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_context_nodes_snapshot
            ON cognix_context_nodes(snapshot_id, node_type);
        CREATE INDEX IF NOT EXISTS idx_cognix_context_nodes_project
            ON cognix_context_nodes(username, project_id, node_type);

        CREATE TABLE IF NOT EXISTS cognix_context_edges (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            username TEXT NOT NULL,
            project_id TEXT,
            source_node_key TEXT NOT NULL,
            target_node_key TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            label TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_context_edges_snapshot
            ON cognix_context_edges(snapshot_id, edge_type);
        CREATE INDEX IF NOT EXISTS idx_cognix_context_edges_project
            ON cognix_context_edges(username, project_id, edge_type);

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

        CREATE TABLE IF NOT EXISTS cognix_model_comparisons (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            prompt_excerpt TEXT NOT NULL DEFAULT '',
            prompt_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            selected_output_id TEXT,
            comparison_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_model_comparisons_username_created
            ON cognix_model_comparisons(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_model_comparisons_project
            ON cognix_model_comparisons(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_comparison_outputs (
            id TEXT PRIMARY KEY,
            comparison_id TEXT NOT NULL,
            username TEXT NOT NULL,
            model_id TEXT NOT NULL,
            model_label TEXT NOT NULL,
            provider_type TEXT NOT NULL DEFAULT 'local',
            output_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'awaiting_generation',
            evaluation_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_comparison_outputs_comparison
            ON cognix_comparison_outputs(username, comparison_id, model_id);

        CREATE TABLE IF NOT EXISTS cognix_user_model_preferences (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            model_id TEXT NOT NULL,
            preference_type TEXT NOT NULL DEFAULT 'chosen_best_response',
            comparison_id TEXT,
            output_id TEXT,
            reason TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, model_id, preference_type)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_user_model_preferences_username
            ON cognix_user_model_preferences(username, preference_type, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_project_dna (
            project_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            objective TEXT NOT NULL DEFAULT '',
            context TEXT NOT NULL DEFAULT '',
            response_style TEXT NOT NULL DEFAULT '',
            preferred_models_json TEXT NOT NULL DEFAULT '[]',
            allowed_tools_json TEXT NOT NULL DEFAULT '[]',
            dna_json TEXT NOT NULL DEFAULT '{}',
            dna_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_dna_username
            ON cognix_project_dna(username, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_project_constraints (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT NOT NULL,
            constraint_type TEXT NOT NULL DEFAULT 'general',
            label TEXT NOT NULL,
            value TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 50,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_constraints_project
            ON cognix_project_constraints(username, project_id, status, priority);

        CREATE TABLE IF NOT EXISTS cognix_project_decisions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT NOT NULL,
            decision_key TEXT NOT NULL,
            title TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            decided_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, project_id, decision_key)
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_project_decisions_project
            ON cognix_project_decisions(username, project_id, status, updated_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_research_topics (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            topic TEXT NOT NULL,
            topic_key TEXT NOT NULL,
            project_id TEXT,
            frequency TEXT NOT NULL DEFAULT 'weekly',
            output_format TEXT NOT NULL DEFAULT 'brief',
            sources_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_research_topics_username_created
            ON cognix_research_topics(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_research_topics_project
            ON cognix_research_topics(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_research_items (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            topic_id TEXT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            source TEXT NOT NULL,
            item_type TEXT NOT NULL DEFAULT 'research_item',
            url TEXT,
            published_at TEXT,
            relevance_score REAL NOT NULL DEFAULT 0,
            item_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_research_items_topic
            ON cognix_research_items(username, topic_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_research_items_source
            ON cognix_research_items(username, source, created_at DESC);

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

        CREATE TABLE IF NOT EXISTS cognix_evolution_items (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            project_id TEXT,
            technique_name TEXT NOT NULL,
            source_name TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready_for_sandbox_plan',
            risk_level TEXT NOT NULL DEFAULT 'medium',
            item_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_evolution_items_username_created
            ON cognix_evolution_items(username, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cognix_evolution_items_project
            ON cognix_evolution_items(username, project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_evolution_experiments (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            item_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            sandbox_id TEXT,
            experiment_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_evolution_experiments_item
            ON cognix_evolution_experiments(username, item_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_evolution_benchmark_results (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            item_id TEXT NOT NULL,
            experiment_id TEXT NOT NULL,
            metric TEXT NOT NULL,
            gain_percent REAL NOT NULL DEFAULT 0,
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_evolution_benchmark_results_experiment
            ON cognix_evolution_benchmark_results(username, experiment_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cognix_integration_proposals (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            item_id TEXT NOT NULL,
            experiment_id TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'requires_human_approval',
            proposal_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cognix_integration_proposals_username
            ON cognix_integration_proposals(username, status, created_at DESC);

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
    _ensure_approval_request_columns(conn)


def _ensure_approval_request_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cognix_approval_requests)").fetchall()}
    additions = {
        "title": "ALTER TABLE cognix_approval_requests ADD COLUMN title TEXT NOT NULL DEFAULT ''",
        "risk_level": "ALTER TABLE cognix_approval_requests ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'medium'",
        "resource_type": "ALTER TABLE cognix_approval_requests ADD COLUMN resource_type TEXT NOT NULL DEFAULT ''",
        "resource_id": "ALTER TABLE cognix_approval_requests ADD COLUMN resource_id TEXT NOT NULL DEFAULT ''",
        "metadata_json": "ALTER TABLE cognix_approval_requests ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
    }
    for column, sql in additions.items():
        if column not in columns:
            conn.execute(sql)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cognix_approval_risk
            ON cognix_approval_requests(risk_level, status, created_at DESC)
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


def create_approval_request(
    username: str,
    request_type: str,
    reason: str,
    *,
    title: str = "",
    risk_level: str = "medium",
    resource_type: str = "",
    resource_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _now()
    request_id = _new_id("apr")
    normalized_risk = _normalize_approval_risk(risk_level)
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
                (
                    id, username, request_type, title, reason, risk_level,
                    resource_type, resource_id, metadata_json, status, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                request_id,
                username,
                request_type.strip().lower(),
                str(title or "")[:180],
                reason.strip(),
                normalized_risk,
                str(resource_type or "")[:120],
                str(resource_id or "")[:240],
                json.dumps(metadata or {}, ensure_ascii = False),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        return get_approval_request(request_id) or {}
    finally:
        conn.close()


def get_approval_request(request_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        item = row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_approval_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        )
        if item:
            item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return item
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
        items = _rows_to_dicts(rows)
        for item in items:
            item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return items
    finally:
        conn.close()


def _normalize_approval_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in {"pending", "approved", "denied"}:
        raise ValueError("Unsupported approval status")
    return normalized


def _normalize_approval_risk(risk_level: str | None) -> str:
    normalized = (risk_level or "medium").strip().lower()
    if normalized not in {"low", "medium", "high", "critical"}:
        raise ValueError("Unsupported approval risk level")
    return normalized


def set_approval_status(
    request_id: str,
    status: str,
    *,
    decided_by: str,
    admin_note: str | None = None,
    policy_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    status = _normalize_approval_status(status)
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
        conn.execute(
            """
            INSERT INTO cognix_approval_decisions
                (id, request_id, status, decided_by, admin_note, policy_snapshot_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("apd"),
                request_id,
                status,
                decided_by,
                str(admin_note or "")[:2000],
                json.dumps(policy_snapshot or {}, ensure_ascii = False),
                updated_at,
            ),
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
                conn.execute(
                    """
                    INSERT INTO cognix_user_permission_overrides
                        (id, username, permission_key, effect, reason, expires_at, updated_by, created_at, updated_at)
                    VALUES (?, ?, ?, 'allow', ?, NULL, ?, ?, ?)
                    ON CONFLICT(username, permission_key) DO UPDATE SET
                        effect = excluded.effect,
                        reason = excluded.reason,
                        expires_at = excluded.expires_at,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        _new_id("uper"),
                        row["username"],
                        DEVELOPER_MODE_PERMISSION,
                        "Approval accepted by admin.",
                        decided_by,
                        updated_at,
                        updated_at,
                    ),
                )
            elif status == "denied":
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
                    conn.execute(
                        """
                        INSERT INTO cognix_user_permission_overrides
                            (id, username, permission_key, effect, reason, expires_at, updated_by, created_at, updated_at)
                        VALUES (?, ?, ?, 'deny', ?, NULL, ?, ?, ?)
                        ON CONFLICT(username, permission_key) DO UPDATE SET
                            effect = excluded.effect,
                            reason = excluded.reason,
                            expires_at = excluded.expires_at,
                            updated_by = excluded.updated_by,
                            updated_at = excluded.updated_at
                        """,
                        (
                            _new_id("uper"),
                            row["username"],
                            DEVELOPER_MODE_PERMISSION,
                            "Approval denied by admin.",
                            decided_by,
                            updated_at,
                            updated_at,
                        ),
                    )
        conn.commit()
        updated = row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_approval_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        )
        if updated:
            updated["metadata"] = _json_or_default(updated.get("metadata_json"), {})
        return updated
    finally:
        conn.close()


def list_approval_decisions(request_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if request_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_approval_decisions
                WHERE request_id = ?
                ORDER BY created_at DESC
                """,
                (request_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_approval_decisions ORDER BY created_at DESC"
            ).fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["policySnapshot"] = _json_or_default(item.get("policy_snapshot_json"), {})
        return items
    finally:
        conn.close()


def add_approval_comment(
    request_id: str,
    *,
    username: str,
    comment: str,
    visibility: str = "admin",
) -> dict[str, Any]:
    normalized_visibility = (visibility or "admin").strip().lower()
    if normalized_visibility not in {"admin", "requester", "internal"}:
        raise ValueError("Unsupported approval comment visibility")
    created_at = _now()
    comment_id = _new_id("apc")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_approval_comments
                (id, request_id, username, comment, visibility, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                comment_id,
                request_id,
                username,
                comment.strip()[:2000],
                normalized_visibility,
                created_at,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_approval_comments WHERE id = ?",
                (comment_id,),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_approval_comments(request_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if request_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_approval_comments
                WHERE request_id = ?
                ORDER BY created_at ASC
                """,
                (request_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_approval_comments ORDER BY created_at ASC"
            ).fetchall()
        return _rows_to_dicts(rows)
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


def _normalize_admin_key(value: str, *, label: str) -> str:
    normalized = (value or "").strip().lower()
    if not RATE_LIMIT_KEY_PATTERN.fullmatch(normalized):
        raise ValueError(f"Invalid {label}")
    return normalized


def _normalize_permission_effect(effect: str) -> str:
    normalized = (effect or "").strip().lower()
    if normalized not in {"allow", "deny"}:
        raise ValueError("Invalid permission effect")
    return normalized


def _normalize_permission_subject_type(subject_type: str) -> str:
    normalized = (subject_type or "").strip().lower()
    if normalized not in {"user", "role", "group"}:
        raise ValueError("Invalid permission subject type")
    return normalized


def upsert_role(
    role_key: str,
    *,
    display_name: str = "",
    description: str = "",
    status: str = "active",
) -> dict[str, Any]:
    normalized_role = _normalize_admin_key(role_key or "user", label = "role key")
    normalized_status = _normalize_quota_status(status)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_roles
                (id, role_key, display_name, description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role_key) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("role"),
                normalized_role,
                str(display_name or normalized_role)[:160],
                str(description or "")[:1000],
                normalized_status,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute("SELECT * FROM cognix_roles WHERE role_key = ?", (normalized_role,)).fetchone()
        ) or {}
    finally:
        conn.close()


def list_roles() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM cognix_roles ORDER BY role_key ASC").fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def upsert_permission_definition(
    permission_key: str,
    *,
    module_key: str = "",
    display_name: str = "",
    description: str = "",
    risk_level: str = "medium",
    status: str = "active",
) -> dict[str, Any]:
    normalized_permission = _normalize_permission_key(permission_key)
    normalized_module = _normalize_admin_key(module_key or "general", label = "module key")
    normalized_risk = _normalize_admin_key(risk_level or "medium", label = "risk level")
    normalized_status = _normalize_quota_status(status)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_permissions
                (id, permission_key, module_key, display_name, description, risk_level, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(permission_key) DO UPDATE SET
                module_key = excluded.module_key,
                display_name = excluded.display_name,
                description = excluded.description,
                risk_level = excluded.risk_level,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("perm"),
                normalized_permission,
                normalized_module,
                str(display_name or normalized_permission)[:180],
                str(description or "")[:1000],
                normalized_risk,
                normalized_status,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_permissions WHERE permission_key = ?",
                (normalized_permission,),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_permission_definitions() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cognix_permissions ORDER BY module_key ASC, permission_key ASC"
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def upsert_role_permission(
    role_key: str,
    permission_key: str,
    *,
    allowed: bool = True,
    updated_by: str,
) -> dict[str, Any]:
    normalized_role = _normalize_admin_key(role_key or "user", label = "role key")
    normalized_permission = _normalize_permission_key(permission_key)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_role_permissions
                (id, role_key, permission_key, allowed, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role_key, permission_key) DO UPDATE SET
                allowed = excluded.allowed,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("rper"),
                normalized_role,
                normalized_permission,
                1 if allowed else 0,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_role_permissions WHERE role_key = ? AND permission_key = ?",
                (normalized_role, normalized_permission),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_role_permissions(role_key: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if role_key:
            rows = conn.execute(
                """
                SELECT * FROM cognix_role_permissions
                WHERE role_key = ?
                ORDER BY permission_key ASC
                """,
                (_normalize_admin_key(role_key, label = "role key"),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_role_permissions ORDER BY role_key ASC, permission_key ASC"
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def upsert_user_permission_override(
    username: str,
    permission_key: str,
    *,
    effect: str = "allow",
    reason: str = "",
    expires_at: str | None = None,
    updated_by: str,
) -> dict[str, Any]:
    normalized_permission = _normalize_permission_key(permission_key)
    normalized_effect = _normalize_permission_effect(effect)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_user_permission_overrides
                (id, username, permission_key, effect, reason, expires_at, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, permission_key) DO UPDATE SET
                effect = excluded.effect,
                reason = excluded.reason,
                expires_at = excluded.expires_at,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("uper"),
                username,
                normalized_permission,
                normalized_effect,
                str(reason or "")[:1000],
                expires_at,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                """
                SELECT * FROM cognix_user_permission_overrides
                WHERE username = ? AND permission_key = ?
                """,
                (username, normalized_permission),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_user_permission_overrides(username: str | None = None) -> list[dict[str, Any]]:
    now = _now()
    conn = get_connection()
    try:
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_permission_overrides
                WHERE username = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY permission_key ASC
                """,
                (username, now),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_permission_overrides
                WHERE expires_at IS NULL OR expires_at > ?
                ORDER BY username ASC, permission_key ASC
                """,
                (now,),
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def delete_user_permission_override(username: str, permission_key: str) -> bool:
    normalized_permission = _normalize_permission_key(permission_key)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            DELETE FROM cognix_user_permission_overrides
            WHERE username = ? AND permission_key = ?
            """,
            (username, normalized_permission),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def upsert_project_permission(
    project_id: str,
    *,
    subject_type: str,
    subject_id: str,
    permission_key: str,
    allowed: bool = True,
    updated_by: str,
) -> dict[str, Any]:
    normalized_project = str(project_id or "").strip()
    if not normalized_project:
        raise ValueError("Invalid project id")
    normalized_subject_type = _normalize_permission_subject_type(subject_type)
    normalized_subject = str(subject_id or "").strip()
    if not normalized_subject:
        raise ValueError("Invalid permission subject")
    normalized_permission = _normalize_permission_key(permission_key)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_permissions
                (id, project_id, subject_type, subject_id, permission_key, allowed, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, subject_type, subject_id, permission_key) DO UPDATE SET
                allowed = excluded.allowed,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("pper"),
                normalized_project,
                normalized_subject_type,
                normalized_subject,
                normalized_permission,
                1 if allowed else 0,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                """
                SELECT * FROM cognix_project_permissions
                WHERE project_id = ? AND subject_type = ? AND subject_id = ? AND permission_key = ?
                """,
                (normalized_project, normalized_subject_type, normalized_subject, normalized_permission),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_project_permissions(project_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_project_permissions
                WHERE project_id = ?
                ORDER BY subject_type ASC, subject_id ASC, permission_key ASC
                """,
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_project_permissions
                ORDER BY project_id ASC, subject_type ASC, subject_id ASC, permission_key ASC
                """
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def upsert_user_limit(
    username: str,
    *,
    limit_key: str,
    limit_value: float,
    unit: str = "",
    scope: str = "user",
    updated_by: str,
) -> dict[str, Any]:
    normalized_key = _normalize_admin_key(limit_key, label = "limit key")
    normalized_scope = _normalize_admin_key(scope or "user", label = "limit scope")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_user_limits
                (username, limit_key, limit_value, unit, scope, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, limit_key) DO UPDATE SET
                limit_value = excluded.limit_value,
                unit = excluded.unit,
                scope = excluded.scope,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                username,
                normalized_key,
                float(limit_value),
                str(unit or "")[:80],
                normalized_scope,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_user_limits WHERE username = ? AND limit_key = ?",
                (username, normalized_key),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_user_limits(username: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_limits
                WHERE username = ?
                ORDER BY limit_key ASC
                """,
                (username,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_user_limits ORDER BY username ASC, limit_key ASC"
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def delete_user_limit(username: str, limit_key: str) -> bool:
    normalized_key = _normalize_admin_key(limit_key, label = "limit key")
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM cognix_user_limits WHERE username = ? AND limit_key = ?",
            (username, normalized_key),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def _normalize_quota_status(status: str | None) -> str:
    normalized = (status or "active").strip().lower()
    if normalized not in {"active", "disabled"}:
        raise ValueError("Unsupported quota status")
    return normalized


def upsert_user_quota(
    username: str,
    *,
    quota_key: str,
    quota_value: float,
    unit: str = "",
    period: str = "custom",
    status: str = "active",
    updated_by: str,
) -> dict[str, Any]:
    normalized_key = _normalize_admin_key(quota_key, label = "quota key")
    normalized_period = _normalize_admin_key(period or "custom", label = "quota period")
    normalized_status = _normalize_quota_status(status)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_user_quotas
                (id, username, quota_key, quota_value, unit, period, status, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, quota_key) DO UPDATE SET
                quota_value = excluded.quota_value,
                unit = excluded.unit,
                period = excluded.period,
                status = excluded.status,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("uquo"),
                username,
                normalized_key,
                float(quota_value),
                str(unit or "")[:80],
                normalized_period,
                normalized_status,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_user_quotas WHERE username = ? AND quota_key = ?",
                (username, normalized_key),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_user_quotas(username: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_quotas
                WHERE username = ?
                ORDER BY quota_key ASC
                """,
                (username,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_user_quotas ORDER BY username ASC, quota_key ASC"
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def delete_user_quota(username: str, quota_key: str) -> bool:
    normalized_key = _normalize_admin_key(quota_key, label = "quota key")
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM cognix_user_quotas WHERE username = ? AND quota_key = ?",
            (username, normalized_key),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def upsert_role_quota(
    role_key: str,
    *,
    quota_key: str,
    quota_value: float,
    unit: str = "",
    period: str = "custom",
    status: str = "active",
    updated_by: str,
) -> dict[str, Any]:
    normalized_role = _normalize_admin_key(role_key or "user", label = "role key")
    normalized_key = _normalize_admin_key(quota_key, label = "quota key")
    normalized_period = _normalize_admin_key(period or "custom", label = "quota period")
    normalized_status = _normalize_quota_status(status)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_role_quotas
                (id, role_key, quota_key, quota_value, unit, period, status, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role_key, quota_key) DO UPDATE SET
                quota_value = excluded.quota_value,
                unit = excluded.unit,
                period = excluded.period,
                status = excluded.status,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("rquo"),
                normalized_role,
                normalized_key,
                float(quota_value),
                str(unit or "")[:80],
                normalized_period,
                normalized_status,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                "SELECT * FROM cognix_role_quotas WHERE role_key = ? AND quota_key = ?",
                (normalized_role, normalized_key),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_role_quotas(role_key: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if role_key:
            rows = conn.execute(
                """
                SELECT * FROM cognix_role_quotas
                WHERE role_key = ?
                ORDER BY quota_key ASC
                """,
                (_normalize_admin_key(role_key, label = "role key"),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_role_quotas ORDER BY role_key ASC, quota_key ASC"
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def record_quota_usage(
    username: str,
    *,
    quota_key: str,
    used_value: float,
    unit: str = "",
    period_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_key = _normalize_admin_key(quota_key, label = "quota key")
    normalized_period_key = str(period_key or datetime.now(timezone.utc).date().isoformat())[:80]
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_quota_usage
                (id, username, quota_key, period_key, used_value, unit, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, quota_key, period_key) DO UPDATE SET
                used_value = cognix_quota_usage.used_value + excluded.used_value,
                unit = excluded.unit,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("qusage"),
                username,
                normalized_key,
                normalized_period_key,
                max(0.0, float(used_value or 0)),
                str(unit or "")[:80],
                json.dumps(metadata or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute(
                """
                SELECT * FROM cognix_quota_usage
                WHERE username = ? AND quota_key = ? AND period_key = ?
                """,
                (username, normalized_key, normalized_period_key),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_quota_usage(username: str | None = None, *, limit: int = 1000) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 1000), 5000))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_quota_usage
                WHERE username = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_quota_usage
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return items
    finally:
        conn.close()


def create_quota_override(
    *,
    target_type: str,
    target_id: str,
    quota_key: str,
    quota_value: float,
    unit: str = "",
    period: str = "custom",
    reason: str = "",
    status: str = "active",
    expires_at: str | None = None,
    updated_by: str,
) -> dict[str, Any]:
    normalized_target_type = _normalize_admin_key(target_type, label = "quota override target type")
    if normalized_target_type not in {"user", "role", "group"}:
        raise ValueError("Unsupported quota override target type")
    normalized_key = _normalize_admin_key(quota_key, label = "quota key")
    normalized_period = _normalize_admin_key(period or "custom", label = "quota period")
    normalized_status = _normalize_quota_status(status)
    override_id = _new_id("qover")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_quota_overrides
                (
                    id, target_type, target_id, quota_key, quota_value, unit, period,
                    reason, status, expires_at, updated_by, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                override_id,
                normalized_target_type,
                str(target_id or "")[:160],
                normalized_key,
                float(quota_value),
                str(unit or "")[:80],
                normalized_period,
                str(reason or "")[:500],
                normalized_status,
                expires_at,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()
        return row_to_dict(
            conn.execute("SELECT * FROM cognix_quota_overrides WHERE id = ?", (override_id,)).fetchone()
        ) or {}
    finally:
        conn.close()


def list_quota_overrides(
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    include_disabled: bool = False,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if target_type:
        clauses.append("target_type = ?")
        values.append(_normalize_admin_key(target_type, label = "quota override target type"))
    if target_id:
        clauses.append("target_id = ?")
        values.append(str(target_id)[:160])
    if not include_disabled:
        clauses.append("status = 'active'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 1000), 5000))
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_quota_overrides
            {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (*values, safe_limit),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def create_user_activity_event(
    username: str,
    *,
    event_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = _new_id("act")
    created_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_user_activity_events
                (id, username, event_type, resource_type, resource_id, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                username,
                _normalize_admin_key(event_type, label = "activity event type"),
                str(resource_type or "")[:120] or None,
                str(resource_id or "")[:160] or None,
                json.dumps(metadata or {}, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_user_activity_events WHERE id = ?", (event_id,)).fetchone()
        item = row_to_dict(row) or {}
        item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return item
    finally:
        conn.close()


def list_user_activity_events(username: str | None = None, *, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 200), 1000))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_activity_events
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_activity_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return items
    finally:
        conn.close()


def _hydrate_user_activity_daily(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["models"] = _json_or_default(item.get("models_json"), [])
    item["projects"] = _json_or_default(item.get("projects_json"), [])
    item["actions"] = _json_or_default(item.get("actions_json"), [])
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def upsert_user_activity_daily(record: dict[str, Any]) -> dict[str, Any]:
    username = str(record.get("username") or "").strip()
    day = str(record.get("day") or "").strip()
    if not username or not day:
        raise ValueError("User activity daily rollup requires username and day")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_user_activity_daily
                (
                    id,
                    username,
                    day,
                    message_count,
                    model_count,
                    tool_call_count,
                    document_access_count,
                    active_project_count,
                    token_total,
                    error_count,
                    sensitive_action_count,
                    active_minutes,
                    activity_score,
                    models_json,
                    projects_json,
                    actions_json,
                    metadata_json,
                    updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, day) DO UPDATE SET
                message_count = excluded.message_count,
                model_count = excluded.model_count,
                tool_call_count = excluded.tool_call_count,
                document_access_count = excluded.document_access_count,
                active_project_count = excluded.active_project_count,
                token_total = excluded.token_total,
                error_count = excluded.error_count,
                sensitive_action_count = excluded.sensitive_action_count,
                active_minutes = excluded.active_minutes,
                activity_score = excluded.activity_score,
                models_json = excluded.models_json,
                projects_json = excluded.projects_json,
                actions_json = excluded.actions_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("uactd"),
                username[:160],
                day[:20],
                max(0, int(record.get("messageCount") or record.get("message_count") or 0)),
                max(0, int(record.get("modelCount") or record.get("model_count") or 0)),
                max(0, int(record.get("toolCallCount") or record.get("tool_call_count") or 0)),
                max(0, int(record.get("documentAccessCount") or record.get("document_access_count") or 0)),
                max(0, int(record.get("activeProjectCount") or record.get("active_project_count") or 0)),
                max(0, int(record.get("tokenTotal") or record.get("token_total") or 0)),
                max(0, int(record.get("errorCount") or record.get("error_count") or 0)),
                max(0, int(record.get("sensitiveActionCount") or record.get("sensitive_action_count") or 0)),
                max(0, int(record.get("activeMinutes") or record.get("active_minutes") or 0)),
                max(0.0, float(record.get("activityScore") or record.get("activity_score") or 0)),
                json.dumps(record.get("models") or [], ensure_ascii = False),
                json.dumps(record.get("projects") or [], ensure_ascii = False),
                json.dumps(record.get("actions") or [], ensure_ascii = False),
                json.dumps(record.get("metadata") or {}, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
        return _hydrate_user_activity_daily(
            conn.execute(
                "SELECT * FROM cognix_user_activity_daily WHERE username = ? AND day = ?",
                (username[:160], day[:20]),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_user_activity_daily(username: str | None = None, *, limit: int = 365) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 365), 1000))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_activity_daily
                WHERE username = ?
                ORDER BY day DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_activity_daily
                ORDER BY day DESC, username ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            item
            for item in (_hydrate_user_activity_daily(row) for row in rows)
            if item is not None
        ]
    finally:
        conn.close()


def _hydrate_organization_activity_daily(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["topUsers"] = _json_or_default(item.get("top_users_json"), [])
    item["models"] = _json_or_default(item.get("models_json"), [])
    item["projects"] = _json_or_default(item.get("projects_json"), [])
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def upsert_organization_activity_daily(record: dict[str, Any]) -> dict[str, Any]:
    day = str(record.get("day") or "").strip()
    if not day:
        raise ValueError("Organization activity daily rollup requires day")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_organization_activity_daily
                (
                    id,
                    day,
                    active_user_count,
                    message_count,
                    token_total,
                    model_count,
                    tool_call_count,
                    document_access_count,
                    active_project_count,
                    error_count,
                    sensitive_action_count,
                    active_minutes,
                    top_users_json,
                    models_json,
                    projects_json,
                    metadata_json,
                    updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                active_user_count = excluded.active_user_count,
                message_count = excluded.message_count,
                token_total = excluded.token_total,
                model_count = excluded.model_count,
                tool_call_count = excluded.tool_call_count,
                document_access_count = excluded.document_access_count,
                active_project_count = excluded.active_project_count,
                error_count = excluded.error_count,
                sensitive_action_count = excluded.sensitive_action_count,
                active_minutes = excluded.active_minutes,
                top_users_json = excluded.top_users_json,
                models_json = excluded.models_json,
                projects_json = excluded.projects_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("oactd"),
                day[:20],
                max(0, int(record.get("activeUserCount") or record.get("active_user_count") or 0)),
                max(0, int(record.get("messageCount") or record.get("message_count") or 0)),
                max(0, int(record.get("tokenTotal") or record.get("token_total") or 0)),
                max(0, int(record.get("modelCount") or record.get("model_count") or 0)),
                max(0, int(record.get("toolCallCount") or record.get("tool_call_count") or 0)),
                max(0, int(record.get("documentAccessCount") or record.get("document_access_count") or 0)),
                max(0, int(record.get("activeProjectCount") or record.get("active_project_count") or 0)),
                max(0, int(record.get("errorCount") or record.get("error_count") or 0)),
                max(0, int(record.get("sensitiveActionCount") or record.get("sensitive_action_count") or 0)),
                max(0, int(record.get("activeMinutes") or record.get("active_minutes") or 0)),
                json.dumps(record.get("topUsers") or record.get("top_users") or [], ensure_ascii = False),
                json.dumps(record.get("models") or [], ensure_ascii = False),
                json.dumps(record.get("projects") or [], ensure_ascii = False),
                json.dumps(record.get("metadata") or {}, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
        return _hydrate_organization_activity_daily(
            conn.execute(
                "SELECT * FROM cognix_organization_activity_daily WHERE day = ?",
                (day[:20],),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def list_organization_activity_daily(*, limit: int = 365) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 365), 1000))
        rows = conn.execute(
            """
            SELECT * FROM cognix_organization_activity_daily
            ORDER BY day DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [
            item
            for item in (_hydrate_organization_activity_daily(row) for row in rows)
            if item is not None
        ]
    finally:
        conn.close()


def create_token_usage_event(
    username: str,
    *,
    project_id: str | None = None,
    model_id: str = "unknown",
    provider: str = "local",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: float = 0,
    estimated_cost_usd: float = 0,
) -> dict[str, Any]:
    event_id = _new_id("tok")
    created_at = _now()
    safe_input = max(0, int(input_tokens or 0))
    safe_output = max(0, int(output_tokens or 0))
    total_tokens = safe_input + safe_output
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_token_usage_events
                (
                    id, username, project_id, model_id, provider, input_tokens,
                    output_tokens, total_tokens, latency_ms, estimated_cost_usd, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                username,
                str(project_id)[:160] if project_id else None,
                str(model_id or "unknown")[:240],
                str(provider or "local")[:120],
                safe_input,
                safe_output,
                total_tokens,
                max(0.0, float(latency_ms or 0)),
                max(0.0, float(estimated_cost_usd or 0)),
                created_at,
            ),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_token_usage_events WHERE id = ?", (event_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_token_usage_events(username: str | None = None, *, limit: int = 1000) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 1000), 5000))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_token_usage_events
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_token_usage_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


CHAT_ACCESS_POLICY_MODES = {"e2ee_strict", "enterprise_compliance"}
CHAT_RISK_LEVELS = {"low", "medium", "high", "critical"}


def _normalize_chat_policy_mode(mode: str) -> str:
    normalized = (mode or "e2ee_strict").strip().lower()
    if normalized not in CHAT_ACCESS_POLICY_MODES:
        raise ValueError("Unsupported chat access policy mode")
    return normalized


def _normalize_chat_risk_level(risk_level: str) -> str:
    normalized = (risk_level or "low").strip().lower()
    return normalized if normalized in CHAT_RISK_LEVELS else "low"


def _hydrate_chat_access_policy(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["admin_chat_access"] = bool(item.get("admin_chat_access"))
    item["require_reason"] = bool(item.get("require_reason"))
    return item


def upsert_chat_access_policy(
    *,
    policy_scope: str = "organization",
    scope_id: str = "default",
    mode: str = "e2ee_strict",
    admin_chat_access: bool = False,
    require_reason: bool = True,
    retention_days: int = 90,
    updated_by: str,
) -> dict[str, Any]:
    normalized_scope = _normalize_admin_key(policy_scope or "organization", label = "chat policy scope")
    normalized_scope_id = str(scope_id or "default").strip()[:160] or "default"
    normalized_mode = _normalize_chat_policy_mode(mode)
    safe_retention = max(1, min(int(retention_days or 90), 3650))
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_chat_access_policies
                (
                    id,
                    policy_scope,
                    scope_id,
                    mode,
                    admin_chat_access,
                    require_reason,
                    retention_days,
                    updated_by,
                    created_at,
                    updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(policy_scope, scope_id) DO UPDATE SET
                mode = excluded.mode,
                admin_chat_access = excluded.admin_chat_access,
                require_reason = excluded.require_reason,
                retention_days = excluded.retention_days,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("capol"),
                normalized_scope,
                normalized_scope_id,
                normalized_mode,
                1 if admin_chat_access else 0,
                1 if require_reason else 0,
                safe_retention,
                str(updated_by or "")[:160],
                now,
                now,
            ),
        )
        conn.commit()
        return _hydrate_chat_access_policy(
            conn.execute(
                """
                SELECT * FROM cognix_chat_access_policies
                WHERE policy_scope = ? AND scope_id = ?
                """,
                (normalized_scope, normalized_scope_id),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def get_chat_access_policy(
    policy_scope: str = "organization",
    scope_id: str = "default",
) -> dict[str, Any] | None:
    normalized_scope = _normalize_admin_key(policy_scope or "organization", label = "chat policy scope")
    normalized_scope_id = str(scope_id or "default").strip()[:160] or "default"
    conn = get_connection()
    try:
        return _hydrate_chat_access_policy(
            conn.execute(
                """
                SELECT * FROM cognix_chat_access_policies
                WHERE policy_scope = ? AND scope_id = ?
                """,
                (normalized_scope, normalized_scope_id),
            ).fetchone()
        )
    finally:
        conn.close()


def list_chat_access_policies() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_chat_access_policies
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [item for item in (_hydrate_chat_access_policy(row) for row in rows) if item is not None]
    finally:
        conn.close()


def record_admin_chat_access(
    *,
    admin_username: str,
    target_username: str,
    thread_id: str,
    access_mode: str,
    content_visible: bool,
    reason: str,
) -> dict[str, Any]:
    clean_reason = (reason or "").strip()
    if len(clean_reason) < 3:
        raise ValueError("Admin chat access reason is required")
    access_id = _new_id("chatacc")
    created_at = _now()
    normalized_access_mode = _normalize_admin_key(access_mode or "metadata_only", label = "chat access mode")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_admin_chat_access_logs
                (
                    id,
                    admin_username,
                    target_username,
                    thread_id,
                    access_mode,
                    content_visible,
                    reason,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                access_id,
                str(admin_username or "")[:160],
                str(target_username or "")[:160],
                str(thread_id or "")[:180],
                normalized_access_mode,
                1 if content_visible else 0,
                clean_reason[:500],
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_admin_chat_access_logs WHERE id = ?",
            (access_id,),
        ).fetchone()
        item = row_to_dict(row) or {}
        item["content_visible"] = bool(item.get("content_visible"))
        return item
    finally:
        conn.close()


def list_admin_chat_access_logs(
    *,
    target_username: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 200), 500))
        if target_username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_admin_chat_access_logs
                WHERE target_username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (target_username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_admin_chat_access_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["content_visible"] = bool(item.get("content_visible"))
        return items
    finally:
        conn.close()


def _hydrate_conversation_audit_metadata(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["message_count"] = int(item.get("message_count") or 0)
    item["token_total"] = int(item.get("token_total") or 0)
    item["tool_call_count"] = int(item.get("tool_call_count") or 0)
    item["document_access_count"] = int(item.get("document_access_count") or 0)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def upsert_conversation_audit_metadata(
    *,
    thread_id: str,
    username: str,
    project_id: str | None = None,
    model_id: str = "unknown",
    risk_level: str = "low",
    message_count: int = 0,
    token_total: int = 0,
    tool_call_count: int = 0,
    document_access_count: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_thread_id = str(thread_id or "").strip()
    if not clean_thread_id:
        raise ValueError("Conversation audit metadata requires a thread id")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_conversation_audit_metadata
                (
                    id,
                    thread_id,
                    username,
                    project_id,
                    model_id,
                    risk_level,
                    message_count,
                    token_total,
                    tool_call_count,
                    document_access_count,
                    metadata_json,
                    updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                username = excluded.username,
                project_id = excluded.project_id,
                model_id = excluded.model_id,
                risk_level = excluded.risk_level,
                message_count = excluded.message_count,
                token_total = excluded.token_total,
                tool_call_count = excluded.tool_call_count,
                document_access_count = excluded.document_access_count,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("caud"),
                clean_thread_id[:180],
                str(username or "")[:160],
                str(project_id)[:160] if project_id else None,
                str(model_id or "unknown")[:240],
                _normalize_chat_risk_level(risk_level),
                max(0, int(message_count or 0)),
                max(0, int(token_total or 0)),
                max(0, int(tool_call_count or 0)),
                max(0, int(document_access_count or 0)),
                json.dumps(metadata or {}, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
        return _hydrate_conversation_audit_metadata(
            conn.execute(
                "SELECT * FROM cognix_conversation_audit_metadata WHERE thread_id = ?",
                (clean_thread_id[:180],),
            ).fetchone()
        ) or {}
    finally:
        conn.close()


def get_conversation_audit_metadata(thread_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        return _hydrate_conversation_audit_metadata(
            conn.execute(
                "SELECT * FROM cognix_conversation_audit_metadata WHERE thread_id = ?",
                (str(thread_id or "").strip()[:180],),
            ).fetchone()
        )
    finally:
        conn.close()


def list_conversation_audit_metadata(
    *,
    username: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 5000), 5000))
        if username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_conversation_audit_metadata
                WHERE username = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_conversation_audit_metadata
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            item
            for item in (_hydrate_conversation_audit_metadata(row) for row in rows)
            if item is not None
        ]
    finally:
        conn.close()


def record_admin_user_view(
    *,
    target_username: str,
    viewed_by: str,
    reason: str | None = None,
) -> dict[str, Any]:
    view_id = _new_id("uview")
    created_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_admin_user_views
                (id, target_username, viewed_by, view_reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (view_id, target_username, viewed_by, str(reason or "")[:500], created_at),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM cognix_admin_user_views WHERE id = ?", (view_id,)).fetchone()) or {}
    finally:
        conn.close()


def list_admin_user_views(target_username: str | None = None, *, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit or 200), 1000))
        if target_username:
            rows = conn.execute(
                """
                SELECT * FROM cognix_admin_user_views
                WHERE target_username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (target_username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_admin_user_views
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
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


def _normalize_security_severity(severity: str) -> str:
    normalized = (severity or "medium").strip().lower()
    return normalized if normalized in {"critical", "high", "medium", "low"} else "medium"


def _normalize_security_status(status: str) -> str:
    normalized = (status or "open").strip().lower()
    return normalized if normalized in {"open", "active", "in_review", "resolved", "ignored"} else "open"


def _inflate_security_threat(row: dict[str, Any]) -> dict[str, Any]:
    row["evidence"] = _json_or_default(row.get("evidence_json"), {})
    row["files"] = _json_or_default(row.get("files_json"), [])
    return row


def create_security_threat(
    *,
    title: str,
    category: str = "vulnerabilities_detected",
    severity: str = "medium",
    status: str = "open",
    summary: str = "",
    evidence: dict[str, Any] | None = None,
    files: list[str] | None = None,
    recommended_solution: str = "",
    source_type: str = "manual",
    source_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    threat_id = _new_id("sth")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_security_threats
                (
                    id, source_type, source_id, category, title, severity, status,
                    summary, evidence_json, files_json, recommended_solution, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                threat_id,
                source_type.strip()[:120] or "manual",
                source_id,
                category.strip()[:120] or "vulnerabilities_detected",
                title.strip()[:240],
                _normalize_security_severity(severity),
                _normalize_security_status(status),
                summary.strip(),
                json.dumps(evidence or {}, ensure_ascii = False),
                json.dumps(files or [], ensure_ascii = False),
                recommended_solution.strip(),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM cognix_security_threats WHERE id = ?", (threat_id,)).fetchone()) or {}
        return _inflate_security_threat(row)
    finally:
        conn.close()


def list_security_threats(limit: int = 500) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_security_threats
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [_inflate_security_threat(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _inflate_security_report(row: dict[str, Any]) -> dict[str, Any]:
    row["report"] = _json_or_default(row.get("report_json"), {})
    return row


def create_security_report(
    *,
    title: str,
    summary: str = "",
    impact: str = "",
    severity: str = "medium",
    status: str = "open",
    report: dict[str, Any] | None = None,
    threat_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    report_id = _new_id("srep")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_security_reports
                (id, threat_id, title, summary, impact, severity, status, report_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                threat_id,
                title.strip()[:240],
                summary.strip(),
                impact.strip(),
                _normalize_security_severity(severity),
                _normalize_security_status(status),
                json.dumps(report or {}, ensure_ascii = False),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM cognix_security_reports WHERE id = ?", (report_id,)).fetchone()) or {}
        return _inflate_security_report(row)
    finally:
        conn.close()


def list_security_reports(limit: int = 500) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_security_reports
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [_inflate_security_report(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _inflate_vulnerability_finding(row: dict[str, Any]) -> dict[str, Any]:
    row["evidence"] = _json_or_default(row.get("evidence_json"), {})
    return row


def create_vulnerability_finding(
    *,
    package_name: str,
    source_name: str = "",
    installed_version: str = "",
    fixed_version: str = "",
    severity: str = "medium",
    status: str = "open",
    description: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _now()
    finding_id = _new_id("vuln")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_vulnerability_findings
                (
                    id, source_name, package_name, installed_version, fixed_version,
                    severity, status, description, evidence_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                source_name.strip()[:160],
                package_name.strip()[:160],
                installed_version.strip()[:80],
                fixed_version.strip()[:80],
                _normalize_security_severity(severity),
                _normalize_security_status(status),
                description.strip(),
                json.dumps(evidence or {}, ensure_ascii = False),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = row_to_dict(
            conn.execute("SELECT * FROM cognix_vulnerability_findings WHERE id = ?", (finding_id,)).fetchone()
        ) or {}
        return _inflate_vulnerability_finding(row)
    finally:
        conn.close()


def list_vulnerability_findings(limit: int = 500) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_vulnerability_findings
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [_inflate_vulnerability_finding(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _inflate_security_remediation_task(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_security_remediation_task(
    *,
    title: str,
    priority: str = "medium",
    status: str = "open",
    recommended_solution: str = "",
    threat_id: str | None = None,
    finding_id: str | None = None,
    assignee: str = "",
    due_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _now()
    task_id = _new_id("srt")
    normalized_priority = _normalize_security_severity(priority)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_security_remediation_tasks
                (
                    id, threat_id, finding_id, title, status, priority,
                    recommended_solution, assignee, due_at, metadata_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                threat_id,
                finding_id,
                title.strip()[:240],
                _normalize_security_status(status),
                normalized_priority,
                recommended_solution.strip(),
                assignee.strip()[:160],
                due_at,
                json.dumps(metadata or {}, ensure_ascii = False),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = row_to_dict(
            conn.execute("SELECT * FROM cognix_security_remediation_tasks WHERE id = ?", (task_id,)).fetchone()
        ) or {}
        return _inflate_security_remediation_task(row)
    finally:
        conn.close()


def list_security_remediation_tasks(limit: int = 500) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_security_remediation_tasks
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [_inflate_security_remediation_task(row) for row in _rows_to_dicts(rows)]
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


def _hydrate_decision_reason(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["evidence"] = _json_or_default(item.get("evidence_json"), {})
    return item


def _hydrate_system_decision(row: dict[str, Any], reasons: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    item = dict(row)
    item["explanation"] = _json_or_default(item.get("explanation_json"), {})
    item["decision"] = _json_or_default(item.get("decision_json"), {})
    item["reasons"] = reasons or []
    return item


def _decision_reasons_for_ids(conn: sqlite3.Connection, decision_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not decision_ids:
        return {}
    placeholders = ", ".join("?" for _ in decision_ids)
    rows = conn.execute(
        f"""
        SELECT * FROM cognix_decision_reasons
        WHERE decision_id IN ({placeholders})
        ORDER BY created_at ASC
        """,
        decision_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {decision_id: [] for decision_id in decision_ids}
    for row in rows:
        item = _hydrate_decision_reason(row_to_dict(row) or {})
        grouped.setdefault(str(item.get("decision_id") or ""), []).append(item)
    return grouped


def create_system_decision(
    username: str,
    *,
    explanation: dict[str, Any],
    decision: dict[str, Any] | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    decision_id = _new_id("sdec")
    reasons = [
        item for item in explanation.get("reasonCodes", [])
        if isinstance(item, dict)
    ]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_system_decisions
                (
                    id, username, source_type, source_id, project_id,
                    decision_type, title, summary,
                    explanation_json, decision_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                username,
                str(source_type or explanation.get("sourceType") or "manual")[:80],
                str(source_id or explanation.get("sourceId") or "")[:160] or None,
                project_id,
                str(explanation.get("decisionType") or "router_orchestrator_decision")[:160],
                str(explanation.get("title") or "Pourquoi cette decision ?")[:240],
                str(explanation.get("summary") or "")[:2000],
                json.dumps(explanation, ensure_ascii = False),
                json.dumps(decision or {}, ensure_ascii = False),
                created_at,
            ),
        )
        for reason in reasons:
            conn.execute(
                """
                INSERT INTO cognix_decision_reasons
                    (
                        id, decision_id, username, reason_code,
                        label, detail, evidence_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("drea"),
                    decision_id,
                    username,
                    str(reason.get("code") or "unspecified")[:160],
                    str(reason.get("label") or reason.get("code") or "Decision reason")[:240],
                    str(reason.get("detail") or "")[:4000],
                    json.dumps(reason.get("evidence") or {}, ensure_ascii = False),
                    created_at,
                ),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_system_decisions WHERE id = ?", (decision_id,)).fetchone()
        reason_map = _decision_reasons_for_ids(conn, [decision_id])
        return _hydrate_system_decision(row_to_dict(row) or {}, reason_map.get(decision_id, []))
    finally:
        conn.close()


def list_system_decisions(
    username: str,
    *,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_system_decisions
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_system_decisions
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        items = _rows_to_dicts(rows)
        reason_map = _decision_reasons_for_ids(conn, [str(item.get("id")) for item in items])
        return [
            _hydrate_system_decision(item, reason_map.get(str(item.get("id")), []))
            for item in items
        ]
    finally:
        conn.close()


def get_system_decision(username: str, decision_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM cognix_system_decisions
            WHERE username = ? AND id = ?
            """,
            (username, decision_id),
        ).fetchone()
        if row is None:
            return None
        reason_map = _decision_reasons_for_ids(conn, [decision_id])
        return _hydrate_system_decision(row_to_dict(row) or {}, reason_map.get(decision_id, []))
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


def get_latest_benchmark_run(username: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM cognix_benchmark_runs
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        if row is None:
            return None
        return _benchmark_row(dict(row))
    finally:
        conn.close()


def _hydrate_runtime_metric(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metrics"] = _json_or_default(item.get("metrics_json"), {})
    return item


def _hydrate_model_performance_log(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def create_runtime_metric(username: str, *, metrics: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    created_at = _now()
    metric_id = _new_id("rtm")
    runtime = metrics.get("runtime") if isinstance(metrics.get("runtime"), dict) else {}
    hardware = metrics.get("hardware") if isinstance(metrics.get("hardware"), dict) else {}
    ram = hardware.get("ram") if isinstance(hardware.get("ram"), dict) else {}
    cpu = hardware.get("cpu") if isinstance(hardware.get("cpu"), dict) else {}
    gpu = hardware.get("gpu") if isinstance(hardware.get("gpu"), dict) else {}
    inference = metrics.get("inference") if isinstance(metrics.get("inference"), dict) else {}
    model_id = metrics.get("modelId")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_runtime_metrics
                (
                    id, username, project_id, model_id, runtime_type,
                    ram_used_percent, cpu_used_percent, gpu_available,
                    tokens_per_second, latency_ms, load_time_ms,
                    estimated_cost_usd, metrics_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric_id,
                username,
                project_id or metrics.get("projectId"),
                str(model_id)[:240] if model_id else None,
                str(runtime.get("runtimeType") or "unknown")[:80],
                ram.get("usedPercent"),
                cpu.get("usagePercent"),
                1 if gpu.get("available") else 0,
                inference.get("tokensPerSecond"),
                inference.get("latencyMs"),
                inference.get("loadTimeMs"),
                float(inference.get("estimatedCostUsd") or 0.0),
                json.dumps(metrics, ensure_ascii = False),
                created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_model_performance_logs
                (
                    id, username, model_id, project_id, event_type,
                    tokens_per_second, latency_ms, load_time_ms,
                    estimated_cost_usd, metadata_json, created_at
                )
            VALUES (?, ?, ?, ?, 'runtime_metric_snapshot', ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("mplog"),
                username,
                str(model_id)[:240] if model_id else None,
                project_id or metrics.get("projectId"),
                inference.get("tokensPerSecond"),
                inference.get("latencyMs"),
                inference.get("loadTimeMs"),
                float(inference.get("estimatedCostUsd") or 0.0),
                json.dumps(
                    {
                        "performanceMonitorVersion": metrics.get("performanceMonitorVersion"),
                        "runtimeType": runtime.get("runtimeType"),
                        "sideEffects": metrics.get("sideEffects", {}),
                    },
                    ensure_ascii = False,
                ),
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_runtime_metrics WHERE id = ?", (metric_id,)).fetchone()
        return _hydrate_runtime_metric(row_to_dict(row) or {})
    finally:
        conn.close()


def list_runtime_metrics(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_runtime_metrics
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_runtime_metrics
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_runtime_metric(row_to_dict(row) or {}) for row in rows]
    finally:
        conn.close()


def list_model_performance_logs(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_model_performance_logs
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_model_performance_logs
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_model_performance_log(row_to_dict(row) or {}) for row in rows]
    finally:
        conn.close()


def _hydrate_model_variant(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def upsert_model_variants(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not variants:
        return []
    now = _now()
    conn = get_connection()
    try:
        for variant in variants:
            model_id = str(variant.get("modelId") or "selected_model")[:240]
            variant_id = str(variant.get("variantId") or variant.get("variantKey") or "unknown")[:160]
            conn.execute(
                """
                INSERT INTO cognix_model_variants
                    (id, model_id, variant_id, quantization, label, status, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'planned', ?, ?, ?)
                ON CONFLICT(model_id, variant_id) DO UPDATE SET
                    quantization = excluded.quantization,
                    label = excluded.label,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("mvar"),
                    model_id,
                    variant_id,
                    str(variant.get("quantization") or "")[:80],
                    str(variant.get("label") or variant_id)[:240],
                    json.dumps(variant, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.commit()
        model_ids = sorted({str(item.get("modelId") or "selected_model")[:240] for item in variants})
        placeholders = ",".join("?" for _ in model_ids)
        rows = conn.execute(
            f"SELECT * FROM cognix_model_variants WHERE model_id IN ({placeholders}) ORDER BY model_id, variant_id",
            tuple(model_ids),
        ).fetchall()
        return [_hydrate_model_variant(dict(row)) for row in rows]
    finally:
        conn.close()


def _hydrate_quantization_profile(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["plan"] = _json_or_default(item.get("plan_json"), {})
    return item


def create_quantization_profile(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    profile_id = _new_id("qprof")
    model = plan.get("model") if isinstance(plan.get("model"), dict) else {}
    selected = plan.get("selectedVariant") if isinstance(plan.get("selectedVariant"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_quantization_profiles
                (
                    id,
                    username,
                    project_id,
                    priority,
                    model_id,
                    selected_variant_id,
                    quantization,
                    status,
                    plan_json,
                    created_at,
                    updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'planned_no_execution', ?, ?, ?)
            """,
            (
                profile_id,
                username,
                project_id or plan.get("projectId"),
                str(plan.get("priority") or "balanced")[:80],
                str(model.get("modelId") or "selected_model")[:240],
                str(selected.get("variantId") or selected.get("variantKey") or "unknown")[:160],
                str(selected.get("quantization") or "")[:80],
                json.dumps(plan, ensure_ascii = False),
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_quantization_profiles WHERE id = ? AND username = ?",
            (profile_id, username),
        ).fetchone()
        return _hydrate_quantization_profile(dict(row)) if row else {}
    finally:
        conn.close()


def list_quantization_profiles(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 200))
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_quantization_profiles
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, normalized_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_quantization_profiles
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, normalized_limit),
            ).fetchall()
        return [_hydrate_quantization_profile(dict(row)) for row in rows]
    finally:
        conn.close()


def _hydrate_provider_profile(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["pricing"] = _json_or_default(item.get("pricing_json"), {})
    item["policy"] = _json_or_default(item.get("policy_json"), {})
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def upsert_provider_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not profiles:
        return []
    now = _now()
    conn = get_connection()
    try:
        for profile in profiles:
            provider_id = str(profile.get("providerId") or profile.get("provider_id") or "unknown")[:160]
            metadata = {
                key: value
                for key, value in profile.items()
                if key not in {"pricing", "policy"}
            }
            conn.execute(
                """
                INSERT INTO cognix_provider_profiles
                    (
                        id,
                        provider_id,
                        display_name,
                        execution_target,
                        status,
                        pricing_json,
                        policy_json,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    execution_target = excluded.execution_target,
                    status = excluded.status,
                    pricing_json = excluded.pricing_json,
                    policy_json = excluded.policy_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("prov"),
                    provider_id,
                    str(profile.get("displayName") or profile.get("label") or provider_id)[:240],
                    str(profile.get("executionTarget") or "unknown")[:120],
                    str(profile.get("status") or "available")[:80],
                    json.dumps(profile.get("pricing") or {}, ensure_ascii = False),
                    json.dumps(profile.get("policy") or {}, ensure_ascii = False),
                    json.dumps(metadata, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.commit()
        provider_ids = sorted({str(item.get("providerId") or item.get("provider_id") or "unknown")[:160] for item in profiles})
        placeholders = ",".join("?" for _ in provider_ids)
        rows = conn.execute(
            f"SELECT * FROM cognix_provider_profiles WHERE provider_id IN ({placeholders}) ORDER BY provider_id",
            tuple(provider_ids),
        ).fetchall()
        return [_hydrate_provider_profile(dict(row)) for row in rows]
    finally:
        conn.close()


def list_provider_profiles(limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 200))
        rows = conn.execute(
            """
            SELECT * FROM cognix_provider_profiles
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()
        return [_hydrate_provider_profile(dict(row)) for row in rows]
    finally:
        conn.close()


def _hydrate_execution_cost_log(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["decision"] = _json_or_default(item.get("decision_json"), {})
    return item


def create_execution_cost_log(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    log_id = _new_id("cost")
    task = plan.get("task") if isinstance(plan.get("task"), dict) else {}
    decision = plan.get("decision") if isinstance(plan.get("decision"), dict) else {}
    sensitivity = plan.get("sensitivity") if isinstance(plan.get("sensitivity"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_execution_cost_logs
                (
                    id,
                    username,
                    project_id,
                    objective_excerpt,
                    selected_provider_id,
                    selected_execution_target,
                    status,
                    estimated_cost_usd,
                    estimated_latency_ms,
                    sensitivity_level,
                    decision_json,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, 'planned_no_execution', ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                username,
                project_id or task.get("projectId"),
                str(task.get("objectiveExcerpt") or "")[:240],
                str(decision.get("selectedProviderId") or "unknown")[:160],
                str(decision.get("selectedExecutionTarget") or "unknown")[:120],
                float(decision.get("estimatedCostUsd") or 0.0),
                int(decision.get("estimatedLatencyMs") or 0),
                str(sensitivity.get("level") or "low")[:80],
                json.dumps(plan, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_execution_cost_logs WHERE id = ? AND username = ?",
            (log_id, username),
        ).fetchone()
        return _hydrate_execution_cost_log(dict(row)) if row else {}
    finally:
        conn.close()


def list_execution_cost_logs(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        normalized_limit = max(1, min(int(limit), 200))
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_execution_cost_logs
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, normalized_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_execution_cost_logs
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, normalized_limit),
            ).fetchall()
        return [_hydrate_execution_cost_log(dict(row)) for row in rows]
    finally:
        conn.close()


def _hydrate_model_conversion(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["plan"] = _json_or_default(item.get("plan_json"), {})
    return item


def _hydrate_conversion_log(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def create_model_conversion(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    conversion_id = str(plan.get("conversionId") or _new_id("mconv"))[:160]
    source = plan.get("sourceModel") if isinstance(plan.get("sourceModel"), dict) else {}
    compatibility = plan.get("compatibility") if isinstance(plan.get("compatibility"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_model_conversions
                (
                    id, username, project_id, source_model_id, source_format,
                    target_format, status, compatibility_status, plan_json,
                    created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversion_id,
                username,
                project_id or plan.get("projectId"),
                str(source.get("modelId") or "selected_model")[:240],
                str(source.get("sourceFormat") or "unknown")[:80],
                str(plan.get("targetFormat") or "unknown")[:80],
                str(plan.get("status") or "planned_no_execution")[:80],
                str(compatibility.get("status") or "unknown")[:120],
                json.dumps(plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_conversion_logs
                (id, conversion_id, username, event_type, message, metadata_json, created_at)
            VALUES (?, ?, ?, 'conversion_plan_stored', ?, ?, ?)
            """,
            (
                _new_id("clog"),
                conversion_id,
                username,
                "Model conversion plan stored without enqueueing a conversion job.",
                json.dumps(
                    {
                        "conversionServiceVersion": plan.get("conversionServiceVersion"),
                        "compatible": compatibility.get("compatible"),
                        "targetFormat": plan.get("targetFormat"),
                    },
                    ensure_ascii = False,
                ),
                now,
            ),
        )
        conn.commit()
        return get_model_conversion(username, conversion_id) or {}
    finally:
        conn.close()


def list_model_conversions(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = max(1, min(int(limit), 200))
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_model_conversions
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_model_conversions
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_model_conversion(dict(row)) for row in rows]
    finally:
        conn.close()


def get_model_conversion(username: str, conversion_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_model_conversions WHERE id = ? AND username = ?",
            (conversion_id, username),
        ).fetchone()
        if row is None:
            return None
        conversion = _hydrate_model_conversion(dict(row))
        log_rows = conn.execute(
            """
            SELECT * FROM cognix_conversion_logs
            WHERE username = ? AND conversion_id = ?
            ORDER BY created_at DESC
            """,
            (username, conversion_id),
        ).fetchall()
        conversion["logs"] = [_hydrate_conversion_log(dict(item)) for item in log_rows]
        return conversion
    finally:
        conn.close()


def _hydrate_plugin(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["manifest"] = _json_or_default(item.get("manifest_json"), {})
    return item


def _hydrate_installed_plugin(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["installPlan"] = _json_or_default(item.get("install_plan_json"), {})
    return item


def _hydrate_plugin_review(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def create_plugin_install_plan(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    plugin = plan.get("plugin") if isinstance(plan.get("plugin"), dict) else {}
    manifest = plan.get("manifest") if isinstance(plan.get("manifest"), dict) else {}
    validation = plan.get("validation") if isinstance(plan.get("validation"), dict) else {}
    permission_scan = plan.get("permissionScan") if isinstance(plan.get("permissionScan"), dict) else {}
    plugin_id = str(plugin.get("id") or manifest.get("id") or "unknown-plugin")[:160]
    installation_id = str(plan.get("installationPlanId") or _new_id("plugplan"))[:160]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_plugins
                (
                    id, plugin_id, display_name, category, publisher, version,
                    signature_status, status, manifest_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                publisher = excluded.publisher,
                version = excluded.version,
                signature_status = excluded.signature_status,
                manifest_json = excluded.manifest_json,
                updated_at = excluded.updated_at
            """,
            (
                plugin_id,
                plugin_id,
                str(plugin.get("displayName") or manifest.get("displayName") or plugin_id)[:160],
                str(plugin.get("category") or manifest.get("category") or "productivity")[:80],
                str(plugin.get("publisher") or manifest.get("publisher") or "unknown")[:160],
                str(plugin.get("version") or manifest.get("version") or "0.0.0")[:80],
                str(validation.get("signatureStatus") or "unknown")[:80],
                json.dumps(manifest, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_installed_plugins
                (
                    id, username, plugin_id, project_id, target_scope, status,
                    install_plan_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                installation_id,
                username,
                plugin_id,
                project_id or plan.get("projectId"),
                str(plan.get("targetScope") or "user")[:80],
                str(plan.get("status") or "planned_no_install")[:80],
                json.dumps(plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        for permission in permission_scan.get("requestedPermissions") or []:
            if not isinstance(permission, dict):
                continue
            conn.execute(
                """
                INSERT INTO cognix_plugin_permissions
                    (
                        id, installation_id, username, plugin_id, permission_key,
                        risk_level, granted, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("pperm"),
                    installation_id,
                    username,
                    plugin_id,
                    str(permission.get("permission") or "")[:160],
                    str(permission.get("riskLevel") or "medium")[:40],
                    1 if permission.get("granted") else 0,
                    now,
                ),
            )
        conn.execute(
            """
            INSERT INTO cognix_plugin_reviews
                (
                    id, installation_id, username, plugin_id, review_type,
                    status, risk_level, metadata_json, created_at
                )
            VALUES (?, ?, ?, ?, 'security_scan', ?, ?, ?, ?)
            """,
            (
                _new_id("prev"),
                installation_id,
                username,
                plugin_id,
                "passed" if validation.get("valid") else "blocked",
                str(permission_scan.get("maxRiskLevel") or "medium")[:40],
                json.dumps(
                    {
                        "validation": validation,
                        "permissionScan": permission_scan,
                        "sideEffects": plan.get("sideEffects", {}),
                    },
                    ensure_ascii = False,
                ),
                now,
            ),
        )
        conn.commit()
        return get_installed_plugin(username, installation_id) or {}
    finally:
        conn.close()


def list_installed_plugins(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_installed_plugins
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_installed_plugins
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_installed_plugin(dict(row)) for row in rows]
    finally:
        conn.close()


def get_installed_plugin(username: str, installation_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_installed_plugins WHERE id = ? AND username = ?",
            (installation_id, username),
        ).fetchone()
        if row is None:
            return None
        installation = _hydrate_installed_plugin(dict(row))
        plugin_row = conn.execute(
            "SELECT * FROM cognix_plugins WHERE id = ?",
            (installation.get("plugin_id"),),
        ).fetchone()
        permission_rows = conn.execute(
            """
            SELECT * FROM cognix_plugin_permissions
            WHERE username = ? AND installation_id = ?
            ORDER BY risk_level DESC, permission_key
            """,
            (username, installation_id),
        ).fetchall()
        review_rows = conn.execute(
            """
            SELECT * FROM cognix_plugin_reviews
            WHERE username = ? AND installation_id = ?
            ORDER BY created_at DESC
            """,
            (username, installation_id),
        ).fetchall()
        installation["plugin"] = _hydrate_plugin(dict(plugin_row)) if plugin_row else None
        installation["permissions"] = _rows_to_dicts(permission_rows)
        installation["reviews"] = [_hydrate_plugin_review(dict(row)) for row in review_rows]
        return installation
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


def _hydrate_ban_report(row: dict[str, Any]) -> dict[str, Any]:
    row["violatedRules"] = _json_or_default(row.get("violated_rules_json"), [])
    row["report"] = _json_or_default(row.get("report_json"), {})
    return row


def upsert_ban_report(
    ban_id: str,
    *,
    username: str | None = None,
    risk_level: str = "medium",
    summary: str = "",
    detected_behavior: str = "",
    violated_rules: list[str] | None = None,
    recommendation: str = "",
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_risk = _normalize_approval_risk(risk_level)
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_ban_reports
                (
                    id, ban_id, username, risk_level, summary, detected_behavior,
                    violated_rules_json, recommendation, report_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ban_id) DO UPDATE SET
                username = excluded.username,
                risk_level = excluded.risk_level,
                summary = excluded.summary,
                detected_behavior = excluded.detected_behavior,
                violated_rules_json = excluded.violated_rules_json,
                recommendation = excluded.recommendation,
                report_json = excluded.report_json,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("brp"),
                ban_id,
                username,
                normalized_risk,
                summary[:2000],
                detected_behavior[:2000],
                json.dumps(violated_rules or [], ensure_ascii = False),
                recommendation[:1000],
                json.dumps(report or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM cognix_ban_reports WHERE ban_id = ?", (ban_id,)).fetchone())
        return _hydrate_ban_report(row or {})
    finally:
        conn.close()


def list_ban_reports(ban_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if ban_id:
            rows = conn.execute(
                "SELECT * FROM cognix_ban_reports WHERE ban_id = ? ORDER BY updated_at DESC",
                (ban_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM cognix_ban_reports ORDER BY updated_at DESC").fetchall()
        return [_hydrate_ban_report(dict(row)) for row in rows]
    finally:
        conn.close()


def create_ban_evidence_log(
    ban_id: str,
    *,
    source_type: str,
    source_id: str | None = None,
    excerpt: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _now()
    evidence_id = _new_id("bev")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_ban_evidence_logs
                (id, ban_id, source_type, source_id, excerpt, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                ban_id,
                source_type.strip().lower()[:80],
                (source_id or "")[:240],
                excerpt[:2000],
                json.dumps(metadata or {}, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        item = row_to_dict(
            conn.execute("SELECT * FROM cognix_ban_evidence_logs WHERE id = ?", (evidence_id,)).fetchone()
        ) or {}
        item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return item
    finally:
        conn.close()


def list_ban_evidence_logs(ban_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if ban_id:
            rows = conn.execute(
                "SELECT * FROM cognix_ban_evidence_logs WHERE ban_id = ? ORDER BY created_at DESC",
                (ban_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM cognix_ban_evidence_logs ORDER BY created_at DESC").fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["metadata"] = _json_or_default(item.get("metadata_json"), {})
        return items
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


def _hydrate_memory_candidate(row: dict[str, Any]) -> dict[str, Any]:
    row["candidate"] = _json_or_default(row.get("candidate_json"), {})
    return row


def create_memory_candidates(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    candidates = [item for item in (plan.get("candidates") or []) if isinstance(item, dict)]
    if not candidates:
        return []
    now = _now()
    stored: list[dict[str, Any]] = []
    conn = get_connection()
    try:
        for candidate in candidates:
            candidate_id = _new_id("mcand")
            conn.execute(
                """
                INSERT INTO cognix_memory_candidates
                    (
                        id, username, project_id, candidate_key, candidate_type,
                        category, label, value, evidence_excerpt, confidence,
                        status, candidate_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_validation', ?, ?, ?)
                """,
                (
                    candidate_id,
                    username,
                    project_id,
                    str(candidate.get("candidateKey") or "")[:160],
                    str(candidate.get("candidateType") or "preference")[:80],
                    str(candidate.get("category") or "general")[:120],
                    str(candidate.get("label") or "")[:240],
                    str(candidate.get("value") or "")[:2000],
                    str(candidate.get("evidenceExcerpt") or "")[:2000],
                    float(candidate.get("confidence") or 0.0),
                    json.dumps(candidate, ensure_ascii = False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM cognix_memory_candidates WHERE id = ?", (candidate_id,)).fetchone()
            stored.append(_hydrate_memory_candidate(row_to_dict(row) or {}))
        conn.commit()
        return stored
    finally:
        conn.close()


def list_memory_candidates(
    username: str,
    *,
    status: str | None = None,
    include_decided: bool = True,
    limit: int = 80,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 80), 1), 200)
    conn = get_connection()
    try:
        clauses = ["username = ?"]
        params: list[Any] = [username]
        if status:
            clauses.append("status = ?")
            params.append(status)
        elif not include_decided:
            clauses.append("status = 'pending_validation'")
        params.append(safe_limit)
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_memory_candidates
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_memory_candidate(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_skill_memory(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _hydrate_user_preference(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def list_skill_memories(
    username: str,
    *,
    include_disabled: bool = False,
    limit: int = 120,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 120), 1), 300)
    conn = get_connection()
    try:
        if include_disabled:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_skill_memories
                WHERE username = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_user_skill_memories
                WHERE username = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_skill_memory(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def list_user_preferences(username: str, *, include_disabled: bool = False) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if include_disabled:
            rows = conn.execute(
                "SELECT * FROM cognix_user_preferences WHERE username = ? ORDER BY updated_at DESC",
                (username,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognix_user_preferences WHERE username = ? AND status = 'active' ORDER BY updated_at DESC",
                (username,),
            ).fetchall()
        return [_hydrate_user_preference(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_personal_ai_profile(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["profile"] = _json_or_default(item.get("profile_json"), {})
    item["controls"] = _json_or_default(item.get("controls_json"), {})
    return item


def _hydrate_style_profile(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["evidence"] = _json_or_default(item.get("evidence_json"), [])
    return item


def _hydrate_personalization_rule(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def _attach_personal_twin_children(conn: sqlite3.Connection, profile: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(profile.get("id") or "")
    username = str(profile.get("username") or "")
    style_rows = conn.execute(
        """
        SELECT * FROM cognix_style_profiles
        WHERE username = ? AND profile_id = ?
        ORDER BY style_key ASC
        """,
        (username, profile_id),
    ).fetchall()
    rule_rows = conn.execute(
        """
        SELECT * FROM cognix_personalization_rules
        WHERE username = ? AND profile_id = ?
        ORDER BY confidence DESC, updated_at DESC
        """,
        (username, profile_id),
    ).fetchall()
    profile["styleProfiles"] = [_hydrate_style_profile(row) for row in _rows_to_dicts(style_rows)]
    profile["personalizationRules"] = [_hydrate_personalization_rule(row) for row in _rows_to_dicts(rule_rows)]
    return profile


def get_personal_ai_profile(username: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_personal_ai_profiles WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return _attach_personal_twin_children(conn, _hydrate_personal_ai_profile(row_to_dict(row) or {}))
    finally:
        conn.close()


def upsert_personal_ai_profile(
    username: str,
    *,
    plan: dict[str, Any],
    activate: bool = False,
) -> dict[str, Any]:
    now = _now()
    profile_payload = plan.get("profile") if isinstance(plan.get("profile"), dict) else {}
    display_name = str(profile_payload.get("displayName") or f"{username} Personal AI Twin")[:240]
    controls = plan.get("controls") if isinstance(plan.get("controls"), dict) else {}
    styles = [item for item in profile_payload.get("styleProfiles", []) if isinstance(item, dict)]
    rules = [item for item in profile_payload.get("preferenceRules", []) if isinstance(item, dict)]
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM cognix_personal_ai_profiles WHERE username = ?",
            (username,),
        ).fetchone()
        profile_id = str((row_to_dict(existing) or {}).get("id") or _new_id("ptwin"))
        status = "active" if activate else str((row_to_dict(existing) or {}).get("status") or "disabled")
        profile_payload = {**profile_payload, "status": status}
        conn.execute(
            """
            INSERT INTO cognix_personal_ai_profiles
                (id, username, display_name, status, profile_json, controls_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                display_name = excluded.display_name,
                status = excluded.status,
                profile_json = excluded.profile_json,
                controls_json = excluded.controls_json,
                updated_at = excluded.updated_at
            """,
            (
                profile_id,
                username,
                display_name,
                status,
                json.dumps(profile_payload, ensure_ascii = False),
                json.dumps(controls, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            "DELETE FROM cognix_style_profiles WHERE username = ? AND profile_id = ?",
            (username, profile_id),
        )
        for style in styles:
            conn.execute(
                """
                INSERT INTO cognix_style_profiles
                    (id, username, profile_id, style_key, style_value, confidence, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("sty"),
                    username,
                    profile_id,
                    str(style.get("styleKey") or "")[:160],
                    str(style.get("styleValue") or "")[:240],
                    float(style.get("confidence") or 0.0),
                    json.dumps(style.get("evidence") or [], ensure_ascii = False),
                    now,
                ),
            )
        conn.execute(
            "DELETE FROM cognix_personalization_rules WHERE username = ? AND profile_id = ?",
            (username, profile_id),
        )
        rule_status = "active" if status == "active" else "disabled"
        for rule in rules:
            metadata = {
                "editable": bool(rule.get("editable", True)),
                "requiresUserActivation": bool(rule.get("requiresUserActivation", True)),
                "evidence": rule.get("evidence") or [],
            }
            conn.execute(
                """
                INSERT INTO cognix_personalization_rules
                    (
                        id, username, profile_id, rule_key, rule_type,
                        rule_text, status, confidence, metadata_json,
                        created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("prule"),
                    username,
                    profile_id,
                    str(rule.get("ruleKey") or "")[:160],
                    str(rule.get("ruleType") or "preference")[:120],
                    str(rule.get("ruleText") or "")[:3000],
                    rule_status,
                    float(rule.get("confidence") or 0.0),
                    json.dumps(metadata, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_personal_ai_profiles WHERE username = ?",
            (username,),
        ).fetchone()
        return _attach_personal_twin_children(conn, _hydrate_personal_ai_profile(row_to_dict(row) or {}))
    finally:
        conn.close()


def set_personal_ai_profile_status(username: str, status: str) -> dict[str, Any] | None:
    normalized_status = status if status in {"active", "disabled", "reset"} else "disabled"
    now = _now()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_personal_ai_profiles WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        profile = row_to_dict(row) or {}
        profile_id = str(profile.get("id") or "")
        if normalized_status == "reset":
            conn.execute(
                """
                UPDATE cognix_personal_ai_profiles
                SET status = 'reset', profile_json = '{}', controls_json = '{}', updated_at = ?
                WHERE username = ?
                """,
                (now, username),
            )
            conn.execute("DELETE FROM cognix_style_profiles WHERE username = ? AND profile_id = ?", (username, profile_id))
            conn.execute("DELETE FROM cognix_personalization_rules WHERE username = ? AND profile_id = ?", (username, profile_id))
        else:
            rule_status = "active" if normalized_status == "active" else "disabled"
            conn.execute(
                """
                UPDATE cognix_personal_ai_profiles
                SET status = ?, updated_at = ?
                WHERE username = ?
                """,
                (normalized_status, now, username),
            )
            conn.execute(
                """
                UPDATE cognix_personalization_rules
                SET status = ?, updated_at = ?
                WHERE username = ? AND profile_id = ?
                """,
                (rule_status, now, username, profile_id),
            )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM cognix_personal_ai_profiles WHERE username = ?",
            (username,),
        ).fetchone()
        return _attach_personal_twin_children(conn, _hydrate_personal_ai_profile(row_to_dict(updated) or {}))
    finally:
        conn.close()


def export_personal_ai_profile(username: str) -> dict[str, Any] | None:
    profile = get_personal_ai_profile(username)
    if profile is None:
        return None
    return {
        "schemaVersion": "cognix_personal_ai_profile_export_v1",
        "username": username,
        "exportedAt": _now(),
        "profile": profile,
        "userControls": {
            "canModify": True,
            "canDeactivate": True,
            "canReset": True,
            "canDeleteExport": True,
        },
    }


def approve_memory_candidate(
    username: str,
    candidate_id: str,
    *,
    label: str | None = None,
    value: str | None = None,
    category: str | None = None,
) -> dict[str, Any] | None:
    now = _now()
    memory_id = _new_id("smem")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_memory_candidates WHERE id = ? AND username = ?",
            (candidate_id, username),
        ).fetchone()
        if row is None:
            return None
        candidate = row_to_dict(row) or {}
        candidate_json = _json_or_default(candidate.get("candidate_json"), {})
        final_label = (label or candidate.get("label") or "").strip()[:240]
        final_value = (value or candidate.get("value") or "").strip()[:2000]
        final_category = (category or candidate.get("category") or "general").strip()[:120]
        metadata = {
            "candidateRuleId": candidate.get("candidate_key"),
            "candidateType": candidate.get("candidate_type"),
            "projectId": candidate.get("project_id"),
            "approvedFromCandidate": True,
        }
        conn.execute(
            """
            INSERT INTO cognix_user_skill_memories
                (
                    id, username, category, label, value, confidence, status,
                    source_candidate_id, metadata_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                memory_id,
                username,
                final_category,
                final_label,
                final_value,
                float(candidate.get("confidence") or 0.0),
                candidate_id,
                json.dumps(metadata, ensure_ascii = False),
                now,
                now,
            ),
        )
        if str(candidate.get("candidate_type") or "") == "preference":
            preference_key = str(candidate.get("candidate_key") or memory_id)[:160]
            conn.execute(
                """
                INSERT INTO cognix_user_preferences
                    (
                        id, username, preference_key, category, value, status,
                        source_candidate_id, metadata_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                ON CONFLICT(username, preference_key) DO UPDATE SET
                    category = excluded.category,
                    value = excluded.value,
                    status = 'active',
                    source_candidate_id = excluded.source_candidate_id,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("pref"),
                    username,
                    preference_key,
                    final_category,
                    final_value,
                    candidate_id,
                    json.dumps({"sourceMemoryId": memory_id, **metadata}, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.execute(
            """
            UPDATE cognix_memory_candidates
            SET status = 'approved', updated_at = ?, decided_at = ?, candidate_json = ?
            WHERE id = ? AND username = ?
            """,
            (
                now,
                now,
                json.dumps({**candidate_json, "approvedMemoryId": memory_id}, ensure_ascii = False),
                candidate_id,
                username,
            ),
        )
        conn.commit()
        memory = _hydrate_skill_memory(
            row_to_dict(conn.execute("SELECT * FROM cognix_user_skill_memories WHERE id = ?", (memory_id,)).fetchone()) or {}
        )
        candidate_row = _hydrate_memory_candidate(
            row_to_dict(conn.execute("SELECT * FROM cognix_memory_candidates WHERE id = ?", (candidate_id,)).fetchone()) or {}
        )
        preferences = list_user_preferences(username, include_disabled = True)
        return {"candidate": candidate_row, "memory": memory, "preferences": preferences}
    finally:
        conn.close()


def reject_memory_candidate(username: str, candidate_id: str) -> dict[str, Any] | None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE cognix_memory_candidates
            SET status = 'rejected', updated_at = ?, decided_at = ?
            WHERE id = ? AND username = ?
            """,
            (now, now, candidate_id, username),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_memory_candidates WHERE id = ? AND username = ?",
            (candidate_id, username),
        ).fetchone()
        if row is None:
            return None
        return _hydrate_memory_candidate(row_to_dict(row) or {})
    finally:
        conn.close()


def update_skill_memory(
    username: str,
    memory_id: str,
    *,
    label: str | None = None,
    value: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    updates: list[str] = []
    params: list[Any] = []
    if label is not None:
        updates.append("label = ?")
        params.append(label.strip()[:240])
    if value is not None:
        updates.append("value = ?")
        params.append(value.strip()[:2000])
    if category is not None:
        updates.append("category = ?")
        params.append(category.strip()[:120])
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"active", "disabled"}:
            raise ValueError("Unsupported memory status")
        updates.append("status = ?")
        params.append(normalized_status)
    if not updates:
        return None
    updated_at = _now()
    updates.append("updated_at = ?")
    params.append(updated_at)
    params.extend([memory_id, username])
    conn = get_connection()
    try:
        conn.execute(
            f"""
            UPDATE cognix_user_skill_memories
            SET {', '.join(updates)}
            WHERE id = ? AND username = ?
            """,
            tuple(params),
        )
        row = conn.execute(
            "SELECT * FROM cognix_user_skill_memories WHERE id = ? AND username = ?",
            (memory_id, username),
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        memory = _hydrate_skill_memory(row_to_dict(row) or {})
        source_candidate_id = memory.get("source_candidate_id")
        if source_candidate_id:
            preference_updates: list[str] = []
            preference_params: list[Any] = []
            if value is not None:
                preference_updates.append("value = ?")
                preference_params.append(str(memory.get("value") or "")[:2000])
            if category is not None:
                preference_updates.append("category = ?")
                preference_params.append(str(memory.get("category") or "")[:120])
            if status is not None:
                preference_updates.append("status = ?")
                preference_params.append(str(memory.get("status") or "active"))
            if preference_updates:
                preference_updates.append("updated_at = ?")
                preference_params.extend([updated_at, username, source_candidate_id])
                conn.execute(
                    f"""
                    UPDATE cognix_user_preferences
                    SET {', '.join(preference_updates)}
                    WHERE username = ? AND source_candidate_id = ?
                    """,
                    tuple(preference_params),
                )
        conn.commit()
        return memory
    finally:
        conn.close()


def delete_skill_memory(username: str, memory_id: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT source_candidate_id FROM cognix_user_skill_memories WHERE id = ? AND username = ?",
            (memory_id, username),
        ).fetchone()
        source_candidate_id = row["source_candidate_id"] if row is not None else None
        cur = conn.execute(
            "DELETE FROM cognix_user_skill_memories WHERE id = ? AND username = ?",
            (memory_id, username),
        )
        if source_candidate_id:
            conn.execute(
                "UPDATE cognix_user_preferences SET status = 'disabled', updated_at = ? WHERE username = ? AND source_candidate_id = ?",
                (_now(), username, source_candidate_id),
            )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def export_skill_memory_bundle(username: str) -> dict[str, Any]:
    return {
        "username": username,
        "skillMemories": list_skill_memories(username, include_disabled = True),
        "preferences": list_user_preferences(username, include_disabled = True),
        "candidates": list_memory_candidates(username, include_decided = True, limit = 300),
        "exportedAt": _now(),
    }


def _hydrate_live_memory(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    row["sensitive"] = bool(row.get("sensitive"))
    return row


def _hydrate_live_memory_version(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _hydrate_memory_audit_log(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _insert_memory_version(
    conn: sqlite3.Connection,
    *,
    memory_id: str,
    username: str,
    version_number: int,
    category: str,
    title: str,
    content: str,
    change_reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO cognix_memory_versions
            (
                id, memory_id, username, version_number, category, title,
                content, change_reason, metadata_json, created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id("mver"),
            memory_id,
            username,
            version_number,
            category,
            title,
            content,
            change_reason,
            json.dumps(metadata or {}, ensure_ascii = False),
            _now(),
        ),
    )


def _insert_memory_audit(
    conn: sqlite3.Connection,
    *,
    username: str,
    memory_id: str | None,
    action: str,
    actor_username: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO cognix_memory_audit_logs
            (id, username, memory_id, action, actor_username, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id("maud"),
            username,
            memory_id,
            action,
            actor_username,
            json.dumps(metadata or {}, ensure_ascii = False),
            _now(),
        ),
    )


def create_live_memory(username: str, *, plan: dict[str, Any], actor_username: str | None = None) -> dict[str, Any]:
    memory = plan.get("memory") if isinstance(plan.get("memory"), dict) else {}
    memory_id = _new_id("mem")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_memories
                (
                    id, username, project_id, category, title, content, status,
                    sensitive, current_version, metadata_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 1, ?, ?, ?)
            """,
            (
                memory_id,
                username,
                plan.get("projectId"),
                str(memory.get("category") or "general")[:80],
                str(memory.get("title") or "Memoire")[:240],
                str(memory.get("content") or "")[:120000],
                1 if memory.get("sensitive") else 0,
                json.dumps(memory.get("metadata") or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        _insert_memory_version(
            conn,
            memory_id = memory_id,
            username = username,
            version_number = 1,
            category = str(memory.get("category") or "general")[:80],
            title = str(memory.get("title") or "Memoire")[:240],
            content = str(memory.get("content") or "")[:120000],
            change_reason = "initial_create",
            metadata = memory.get("metadata") or {},
        )
        _insert_memory_audit(
            conn,
            username = username,
            memory_id = memory_id,
            action = "memory_created",
            actor_username = actor_username or username,
            metadata = {"memoryEditorVersion": plan.get("memoryEditorVersion")},
        )
        conn.commit()
    finally:
        conn.close()
    return get_live_memory(username, memory_id) or {}


def list_live_memories(
    username: str,
    *,
    category: str | None = None,
    query: str | None = None,
    include_disabled: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    clauses = ["username = ?"]
    params: list[Any] = [username]
    if not include_disabled:
        clauses.append("status = 'active'")
    else:
        clauses.append("status != 'deleted'")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if query:
        needle = f"%{query.lower()}%"
        clauses.append("(LOWER(title) LIKE ? OR LOWER(content) LIKE ?)")
        params.extend([needle, needle])
    params.append(safe_limit)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_memories
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_live_memory(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_live_memory(username: str, memory_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_memories WHERE id = ? AND username = ?",
            (memory_id, username),
        ).fetchone()
        if row is None:
            return None
        memory = _hydrate_live_memory(row_to_dict(row) or {})
        version_rows = conn.execute(
            """
            SELECT * FROM cognix_memory_versions
            WHERE username = ? AND memory_id = ?
            ORDER BY version_number DESC
            """,
            (username, memory_id),
        ).fetchall()
        audit_rows = conn.execute(
            """
            SELECT * FROM cognix_memory_audit_logs
            WHERE username = ? AND memory_id = ?
            ORDER BY created_at DESC
            """,
            (username, memory_id),
        ).fetchall()
        memory["versions"] = [_hydrate_live_memory_version(item) for item in _rows_to_dicts(version_rows)]
        memory["auditLogs"] = [_hydrate_memory_audit_log(item) for item in _rows_to_dicts(audit_rows)]
        return memory
    finally:
        conn.close()


def update_live_memory(
    username: str,
    memory_id: str,
    *,
    actor_username: str | None = None,
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
    status: str | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    existing = get_live_memory(username, memory_id)
    if existing is None:
        return None
    final_title = title.strip()[:240] if title is not None else str(existing.get("title") or "")
    final_content = content.strip()[:120000] if content is not None else str(existing.get("content") or "")
    final_category = category.strip()[:80] if category is not None else str(existing.get("category") or "general")
    final_status = status.strip().lower() if status is not None else str(existing.get("status") or "active")
    if final_status not in {"active", "disabled", "deleted"}:
        raise ValueError("Unsupported memory status")
    next_version = int(existing.get("current_version") or 1) + 1
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE cognix_memories
            SET title = ?, content = ?, category = ?, status = ?, current_version = ?, updated_at = ?
            WHERE id = ? AND username = ?
            """,
            (final_title, final_content, final_category, final_status, next_version, _now(), memory_id, username),
        )
        _insert_memory_version(
            conn,
            memory_id = memory_id,
            username = username,
            version_number = next_version,
            category = final_category,
            title = final_title,
            content = final_content,
            change_reason = (reason or "memory_updated")[:500],
            metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {},
        )
        _insert_memory_audit(
            conn,
            username = username,
            memory_id = memory_id,
            action = "memory_updated" if final_status == "active" else f"memory_{final_status}",
            actor_username = actor_username or username,
            metadata = {"nextVersion": next_version, "reason": reason},
        )
        conn.commit()
    finally:
        conn.close()
    return get_live_memory(username, memory_id)


def set_live_memory_status(
    username: str,
    memory_id: str,
    *,
    status: str,
    actor_username: str | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    return update_live_memory(
        username,
        memory_id,
        actor_username = actor_username,
        status = status,
        reason = reason or f"memory_{status}",
    )


def merge_live_memories(
    username: str,
    *,
    plan: dict[str, Any],
    actor_username: str | None = None,
    disable_sources: bool = False,
) -> dict[str, Any]:
    created = create_live_memory(username, plan = plan, actor_username = actor_username)
    source_ids = [str(item) for item in plan.get("sourceMemoryIds") or []]
    conn = get_connection()
    try:
        _insert_memory_audit(
            conn,
            username = username,
            memory_id = created.get("id"),
            action = "memory_merged",
            actor_username = actor_username or username,
            metadata = {"sourceMemoryIds": source_ids},
        )
        if disable_sources:
            now = _now()
            for source_id in source_ids:
                source_row = conn.execute(
                    "SELECT * FROM cognix_memories WHERE id = ? AND username = ?",
                    (source_id, username),
                ).fetchone()
                if source_row is None:
                    continue
                source_memory = row_to_dict(source_row) or {}
                next_version = int(source_memory.get("current_version") or 1) + 1
                conn.execute(
                    """
                    UPDATE cognix_memories
                    SET status = 'disabled', current_version = ?, updated_at = ?
                    WHERE id = ? AND username = ?
                    """,
                    (next_version, now, source_id, username),
                )
                _insert_memory_version(
                    conn,
                    memory_id = source_id,
                    username = username,
                    version_number = next_version,
                    category = str(source_memory.get("category") or "general")[:80],
                    title = str(source_memory.get("title") or "Memoire")[:240],
                    content = str(source_memory.get("content") or "")[:120000],
                    change_reason = "memory_disabled_after_merge",
                    metadata = _json_or_default(source_memory.get("metadata_json"), {}),
                )
                _insert_memory_audit(
                    conn,
                    username = username,
                    memory_id = source_id,
                    action = "memory_disabled_after_merge",
                    actor_username = actor_username or username,
                    metadata = {"mergedInto": created.get("id")},
                )
        conn.commit()
    finally:
        conn.close()
    return get_live_memory(username, str(created.get("id"))) or created


def export_live_memory_bundle(username: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        versions = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_memory_versions WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
        audits = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM cognix_memory_audit_logs WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        )
        return {
            "username": username,
            "memories": list_live_memories(username, include_disabled = True, limit = 300),
            "versions": [_hydrate_live_memory_version(item) for item in versions],
            "auditLogs": [_hydrate_memory_audit_log(item) for item in audits],
            "exportedAt": _now(),
        }
    finally:
        conn.close()


def list_live_memory_audit_logs(username: str, *, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_memory_audit_logs
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, safe_limit),
        ).fetchall()
        return [_hydrate_memory_audit_log(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_workflow(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _hydrate_workflow_step(row: dict[str, Any]) -> dict[str, Any]:
    row["parameters"] = _json_or_default(row.get("parameters_json"), {})
    row["step"] = _json_or_default(row.get("step_json"), {})
    return row


def _hydrate_workflow_run(row: dict[str, Any]) -> dict[str, Any]:
    row["runPlan"] = _json_or_default(row.get("run_plan_json"), {})
    return row


def _hydrate_workflow_run_log(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_workflow_from_plan(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    workflow = plan.get("workflow") if isinstance(plan.get("workflow"), dict) else {}
    steps = [item for item in (plan.get("steps") or []) if isinstance(item, dict)]
    workflow_id = _new_id("wf")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_workflows
                (
                    id, username, project_id, title, objective, workflow_type,
                    status, share_status, metadata_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                workflow_id,
                username,
                project_id or workflow.get("projectId"),
                str(workflow.get("title") or "Workflow CogniX")[:240],
                str(workflow.get("objective") or "")[:4000],
                str(workflow.get("workflowType") or "custom")[:120],
                str(workflow.get("shareStatus") or "private")[:40],
                json.dumps(workflow.get("metadata") or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        for index, step in enumerate(steps):
            step_id = _new_id("wstep")
            conn.execute(
                """
                INSERT INTO cognix_workflow_steps
                    (
                        id, workflow_id, username, step_index, step_type, label,
                        tool_name, model_id, parameters_json, output_summary,
                        step_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    workflow_id,
                    username,
                    int(step.get("stepIndex", index)),
                    str(step.get("stepType") or "user_action")[:80],
                    str(step.get("label") or f"Step {index + 1}")[:240],
                    step.get("toolName"),
                    step.get("modelId"),
                    json.dumps(step.get("parameters") or {}, ensure_ascii = False),
                    str(step.get("outputSummary") or "")[:2000],
                    json.dumps(step, ensure_ascii = False),
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return get_workflow(username, workflow_id) or {}


def list_workflows(
    username: str,
    *,
    include_disabled: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        clauses = ["username = ?"]
        params: list[Any] = [username]
        if not include_disabled:
            clauses.append("status = 'active'")
        params.append(safe_limit)
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_workflows
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        workflows = [_hydrate_workflow(row) for row in _rows_to_dicts(rows)]
        for workflow in workflows:
            count_row = conn.execute(
                "SELECT COUNT(*) AS count FROM cognix_workflow_steps WHERE username = ? AND workflow_id = ?",
                (username, workflow.get("id")),
            ).fetchone()
            workflow["stepCount"] = int(count_row["count"] if count_row is not None else 0)
        return workflows
    finally:
        conn.close()


def get_workflow(username: str, workflow_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        workflow_row = conn.execute(
            "SELECT * FROM cognix_workflows WHERE id = ? AND username = ?",
            (workflow_id, username),
        ).fetchone()
        if workflow_row is None:
            return None
        workflow = _hydrate_workflow(row_to_dict(workflow_row) or {})
        step_rows = conn.execute(
            """
            SELECT * FROM cognix_workflow_steps
            WHERE workflow_id = ? AND username = ?
            ORDER BY step_index ASC
            """,
            (workflow_id, username),
        ).fetchall()
        workflow["steps"] = [_hydrate_workflow_step(row) for row in _rows_to_dicts(step_rows)]
        workflow["stepCount"] = len(workflow["steps"])
        return workflow
    finally:
        conn.close()


def update_workflow(
    username: str,
    workflow_id: str,
    *,
    title: str | None = None,
    objective: str | None = None,
    status: str | None = None,
    share_status: str | None = None,
) -> dict[str, Any] | None:
    updates: list[str] = []
    params: list[Any] = []
    if title is not None:
        updates.append("title = ?")
        params.append(title.strip()[:240])
    if objective is not None:
        updates.append("objective = ?")
        params.append(objective.strip()[:4000])
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"active", "disabled", "archived"}:
            raise ValueError("Unsupported workflow status")
        updates.append("status = ?")
        params.append(normalized_status)
    if share_status is not None:
        normalized_share = share_status.strip().lower()
        if normalized_share not in {"private", "shared"}:
            raise ValueError("Unsupported workflow share status")
        updates.append("share_status = ?")
        params.append(normalized_share)
    if not updates:
        return None
    updates.append("updated_at = ?")
    params.append(_now())
    params.extend([workflow_id, username])
    conn = get_connection()
    try:
        conn.execute(
            f"""
            UPDATE cognix_workflows
            SET {', '.join(updates)}
            WHERE id = ? AND username = ?
            """,
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()
    return get_workflow(username, workflow_id)


def delete_workflow(username: str, workflow_id: str) -> bool:
    conn = get_connection()
    try:
        run_rows = conn.execute(
            "SELECT id FROM cognix_workflow_runs WHERE workflow_id = ? AND username = ?",
            (workflow_id, username),
        ).fetchall()
        run_ids = [row["id"] for row in run_rows]
        for run_id in run_ids:
            conn.execute(
                "DELETE FROM cognix_workflow_run_logs WHERE run_id = ? AND username = ?",
                (run_id, username),
            )
        conn.execute(
            "DELETE FROM cognix_workflow_runs WHERE workflow_id = ? AND username = ?",
            (workflow_id, username),
        )
        conn.execute(
            "DELETE FROM cognix_workflow_steps WHERE workflow_id = ? AND username = ?",
            (workflow_id, username),
        )
        cur = conn.execute(
            "DELETE FROM cognix_workflows WHERE id = ? AND username = ?",
            (workflow_id, username),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def create_workflow_run_plan_record(
    username: str,
    *,
    workflow_id: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    run_id = _new_id("wrun")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_workflow_runs
                (id, username, workflow_id, status, run_mode, run_plan_json, created_at, updated_at)
            VALUES (?, ?, ?, 'planned', ?, ?, ?, ?)
            """,
            (
                run_id,
                username,
                workflow_id,
                str(plan.get("runMode") or "dry_run")[:80],
                json.dumps(plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        for planned_step in plan.get("orderedSteps") or []:
            conn.execute(
                """
                INSERT INTO cognix_workflow_run_logs
                    (id, run_id, username, workflow_id, step_id, level, message, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, 'info', ?, ?, ?)
                """,
                (
                    _new_id("wlog"),
                    run_id,
                    username,
                    workflow_id,
                    planned_step.get("stepId"),
                    "Replay planned only; execution is blocked until explicit confirmation.",
                    json.dumps(planned_step, ensure_ascii = False),
                    now,
                ),
            )
        conn.commit()
        run_row = conn.execute(
            "SELECT * FROM cognix_workflow_runs WHERE id = ? AND username = ?",
            (run_id, username),
        ).fetchone()
        log_rows = conn.execute(
            """
            SELECT * FROM cognix_workflow_run_logs
            WHERE run_id = ? AND username = ?
            ORDER BY created_at ASC
            """,
            (run_id, username),
        ).fetchall()
        run = _hydrate_workflow_run(row_to_dict(run_row) or {})
        run["logs"] = [_hydrate_workflow_run_log(row) for row in _rows_to_dicts(log_rows)]
        return run
    finally:
        conn.close()


def list_workflow_runs(username: str, workflow_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 50), 1), 200)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_workflow_runs
            WHERE username = ? AND workflow_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, workflow_id, safe_limit),
        ).fetchall()
        return [_hydrate_workflow_run(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def export_workflow_bundle(username: str, workflow_id: str) -> dict[str, Any] | None:
    workflow = get_workflow(username, workflow_id)
    if workflow is None:
        return None
    return {
        "username": username,
        "workflow": workflow,
        "runs": list_workflow_runs(username, workflow_id, limit = 100),
        "exportedAt": _now(),
    }


def _hydrate_compressed_context(row: dict[str, Any]) -> dict[str, Any]:
    row["ranking"] = _json_or_default(row.get("ranking_json"), [])
    row["evaluation"] = _json_or_default(row.get("evaluation_json"), {})
    return row


def _hydrate_compression_log(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_compressed_context(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    context_id = _new_id("cctx")
    now = _now()
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    evaluation = plan.get("evaluation") if isinstance(plan.get("evaluation"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_compressed_contexts
                (
                    id, username, project_id, context_hash, objective_excerpt,
                    original_token_count, compressed_token_count, reduction_ratio,
                    compressed_context, ranking_json, evaluation_json, status,
                    created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                context_id,
                username,
                project_id or plan.get("projectId"),
                str(plan.get("contextHash") or "")[:128],
                str(plan.get("objective") or "")[:500],
                int(summary.get("originalTokenCount") or evaluation.get("originalTokenCount") or 0),
                int(summary.get("compressedTokenCount") or evaluation.get("compressedTokenCount") or 0),
                float(summary.get("reductionRatio") or evaluation.get("reductionRatio") or 0.0),
                str(plan.get("compressedContext") or ""),
                json.dumps(plan.get("ranking") or [], ensure_ascii = False),
                json.dumps(evaluation, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_compression_logs
                (id, username, compressed_context_id, event_type, message, metadata_json, created_at)
            VALUES (?, ?, ?, 'compression_plan_stored', ?, ?, ?)
            """,
            (
                _new_id("clog"),
                username,
                context_id,
                "Compressed context stored from deterministic prompt compression plan.",
                json.dumps(
                    {
                        "promptCompressionVersion": plan.get("promptCompressionVersion"),
                        "reductionRatio": summary.get("reductionRatio"),
                        "lostInfoRisk": summary.get("lostInfoRisk"),
                    },
                    ensure_ascii = False,
                ),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_compressed_context(username, context_id) or {}


def list_compressed_contexts(
    username: str,
    *,
    include_deleted: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        clauses = ["username = ?"]
        params: list[Any] = [username]
        if not include_deleted:
            clauses.append("status = 'active'")
        params.append(safe_limit)
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_compressed_contexts
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_compressed_context(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_compressed_context(username: str, context_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_compressed_contexts WHERE id = ? AND username = ?",
            (context_id, username),
        ).fetchone()
        if row is None:
            return None
        context = _hydrate_compressed_context(row_to_dict(row) or {})
        log_rows = conn.execute(
            """
            SELECT * FROM cognix_compression_logs
            WHERE username = ? AND compressed_context_id = ?
            ORDER BY created_at DESC
            """,
            (username, context_id),
        ).fetchall()
        context["logs"] = [_hydrate_compression_log(item) for item in _rows_to_dicts(log_rows)]
        return context
    finally:
        conn.close()


def delete_compressed_context(username: str, context_id: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE cognix_compressed_contexts SET status = 'deleted', updated_at = ? WHERE id = ? AND username = ?",
            (_now(), context_id, username),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def _hydrate_context_usage_stat(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _hydrate_context_heatmap_entry(row: dict[str, Any]) -> dict[str, Any]:
    row["entry"] = _json_or_default(row.get("entry_json"), {})
    return row


def create_context_heatmap_entries(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    normalized_project_id = project_id or plan.get("projectId")
    entries = [entry for entry in plan.get("entries", []) if isinstance(entry, dict)]
    conn = get_connection()
    try:
        for entry in entries:
            chunk_id = str(entry.get("chunkId") or "unknown")[:180]
            source_type = str(entry.get("sourceType") or "context")[:80]
            source_id = str(entry.get("sourceId") or chunk_id)[:180]
            conn.execute(
                """
                INSERT INTO cognix_context_usage_stats
                    (
                        id, username, project_id, chunk_id, source_type, source_id,
                        usage_count, response_count, citation_count, utility_score,
                        metadata_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username, project_id, chunk_id) DO UPDATE SET
                    source_type = excluded.source_type,
                    source_id = excluded.source_id,
                    usage_count = excluded.usage_count,
                    response_count = excluded.response_count,
                    citation_count = excluded.citation_count,
                    utility_score = excluded.utility_score,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("ctxstat"),
                    username,
                    normalized_project_id,
                    chunk_id,
                    source_type,
                    source_id,
                    int(entry.get("usageCount") or 0),
                    int(entry.get("responseCount") or 0),
                    int(entry.get("citationCount") or 0),
                    float(entry.get("utilityScore") or 0.0),
                    json.dumps(
                        {
                            "signals": entry.get("signals") or {},
                            "matchedObjectiveTerms": entry.get("matchedObjectiveTerms") or [],
                            "usageTrackerVersion": plan.get("usageTrackerVersion"),
                        },
                        ensure_ascii = False,
                    ),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO cognix_context_heatmap_entries
                    (
                        id, username, project_id, chunk_id, source_type, source_id, title,
                        utility_score, bucket, recommended_action, theme_token,
                        entry_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username, project_id, chunk_id) DO UPDATE SET
                    source_type = excluded.source_type,
                    source_id = excluded.source_id,
                    title = excluded.title,
                    utility_score = excluded.utility_score,
                    bucket = excluded.bucket,
                    recommended_action = excluded.recommended_action,
                    theme_token = excluded.theme_token,
                    entry_json = excluded.entry_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("ctxheat"),
                    username,
                    normalized_project_id,
                    chunk_id,
                    source_type,
                    source_id,
                    str(entry.get("title") or "")[:240],
                    float(entry.get("utilityScore") or 0.0),
                    str(entry.get("bucket") or "low_usage")[:80],
                    str(entry.get("recommendedAction") or "review")[:80],
                    str(entry.get("themeToken") or "warning")[:80],
                    json.dumps(entry, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "entries": list_context_heatmap_entries(username, project_id = normalized_project_id, limit = 300),
        "usageStats": list_context_usage_stats(username, project_id = normalized_project_id, limit = 300),
    }


def list_context_usage_stats(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = min(max(int(limit or 100), 1), 500)
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_context_usage_stats
                WHERE username = ? AND project_id = ?
                ORDER BY utility_score DESC, updated_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_context_usage_stats
                WHERE username = ?
                ORDER BY utility_score DESC, updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_context_usage_stat(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def list_context_heatmap_entries(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = min(max(int(limit or 100), 1), 500)
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_context_heatmap_entries
                WHERE username = ? AND project_id = ?
                ORDER BY utility_score DESC, updated_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_context_heatmap_entries
                WHERE username = ?
                ORDER BY utility_score DESC, updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_context_heatmap_entry(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_memory_cleanup_suggestion(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["suggestion"] = _json_or_default(item.get("suggestion_json"), {})
    return item


def _hydrate_memory_conflict(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["memoryIds"] = _json_or_default(item.get("memory_ids_json"), [])
    item["conflict"] = _json_or_default(item.get("conflict_json"), {})
    return item


def create_memory_cleanup_plan_records(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    normalized_project_id = project_id or plan.get("projectId")
    suggestions = [item for item in plan.get("suggestions", []) if isinstance(item, dict)]
    conflicts = [item for item in plan.get("conflicts", []) if isinstance(item, dict)]
    conn = get_connection()
    try:
        for suggestion in suggestions:
            conn.execute(
                """
                INSERT INTO cognix_memory_cleanup_suggestions
                    (
                        id, username, project_id, memory_id, reason_code,
                        recommended_action, confidence, status,
                        suggestion_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)
                """,
                (
                    _new_id("mcln"),
                    username,
                    normalized_project_id,
                    str(suggestion.get("memoryId") or "unknown")[:180],
                    str(suggestion.get("reasonCode") or "review")[:160],
                    str(suggestion.get("recommendedAction") or "review")[:80],
                    float(suggestion.get("confidence") or 0.0),
                    json.dumps(suggestion, ensure_ascii = False),
                    created_at,
                ),
            )
        for conflict in conflicts:
            conn.execute(
                """
                INSERT INTO cognix_memory_conflicts
                    (
                        id, username, project_id, conflict_type,
                        memory_ids_json, summary, status,
                        conflict_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)
                """,
                (
                    _new_id("mconf"),
                    username,
                    normalized_project_id,
                    str(conflict.get("conflictType") or "memory_conflict")[:160],
                    json.dumps(conflict.get("memoryIds") or [], ensure_ascii = False),
                    str(conflict.get("summary") or "")[:2000],
                    json.dumps(conflict, ensure_ascii = False),
                    created_at,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "suggestions": list_memory_cleanup_suggestions(username, project_id = normalized_project_id, limit = 300),
        "conflicts": list_memory_conflicts(username, project_id = normalized_project_id, limit = 300),
    }


def list_memory_cleanup_suggestions(
    username: str,
    *,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 500)
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_memory_cleanup_suggestions
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_memory_cleanup_suggestions
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_memory_cleanup_suggestion(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def list_memory_conflicts(
    username: str,
    *,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 500)
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_memory_conflicts
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_memory_conflicts
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_memory_conflict(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_generated_dataset(row: dict[str, Any]) -> dict[str, Any]:
    row["qualitySummary"] = _json_or_default(row.get("quality_summary_json"), {})
    row["dataSources"] = _json_or_default(row.get("data_sources_json"), [])
    row["exportPlan"] = _json_or_default(row.get("export_plan_json"), {})
    return row


def _hydrate_dataset_example(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _hydrate_dataset_quality_score(row: dict[str, Any]) -> dict[str, Any]:
    row["signals"] = _json_or_default(row.get("signals_json"), {})
    return row


def create_generated_dataset(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    dataset = plan.get("dataset") if isinstance(plan.get("dataset"), dict) else {}
    dataset_id = str(dataset.get("datasetId") or _new_id("ds"))[:160]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_generated_datasets
                (
                    id, username, project_id, objective_excerpt, output_format, status,
                    example_count, ready_example_count, review_example_count,
                    quality_summary_json, data_sources_json, export_plan_json,
                    created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                username,
                project_id or plan.get("projectId"),
                str(dataset.get("objective") or plan.get("objective") or "")[:500],
                str(dataset.get("format") or "jsonl")[:80],
                str(dataset.get("status") or "review_required")[:80],
                int(dataset.get("exampleCount") or 0),
                int(dataset.get("readyExampleCount") or 0),
                int(dataset.get("reviewExampleCount") or 0),
                json.dumps(plan.get("qualitySummary") or {}, ensure_ascii = False),
                json.dumps(plan.get("dataSources") or [], ensure_ascii = False),
                json.dumps(plan.get("exportPlan") or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        for example in [item for item in plan.get("examples", []) if isinstance(item, dict)]:
            example_id = str(example.get("id") or _new_id("ex"))[:180]
            conn.execute(
                """
                INSERT INTO cognix_dataset_examples
                    (
                        id, dataset_id, username, instruction, input, output,
                        quality_score, status, metadata_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    example_id,
                    dataset_id,
                    username,
                    str(example.get("instruction") or ""),
                    str(example.get("input") or ""),
                    str(example.get("output") or ""),
                    float(example.get("qualityScore") or 0.0),
                    str(example.get("status") or "review")[:80],
                    json.dumps(example.get("metadata") or {}, ensure_ascii = False),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO cognix_dataset_quality_scores
                    (
                        id, dataset_id, example_id, username, quality_score,
                        quality_label, signals_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("dq"),
                    dataset_id,
                    example_id,
                    username,
                    float(example.get("qualityScore") or 0.0),
                    str(example.get("qualityLabel") or example.get("status") or "review")[:80],
                    json.dumps(
                        {
                            "matchedObjectiveTerms": example.get("matchedObjectiveTerms") or [],
                            "sensitiveTerms": example.get("sensitiveTerms") or [],
                            "tokenCount": example.get("tokenCount"),
                        },
                        ensure_ascii = False,
                    ),
                    now,
                ),
            )
        conn.commit()
        return get_generated_dataset(username, dataset_id) or {}
    finally:
        conn.close()


def list_generated_datasets(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = min(max(int(limit or 100), 1), 300)
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_generated_datasets
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_generated_datasets
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_generated_dataset(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_generated_dataset(username: str, dataset_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_generated_datasets WHERE id = ? AND username = ?",
            (dataset_id, username),
        ).fetchone()
        if row is None:
            return None
        dataset = _hydrate_generated_dataset(row_to_dict(row) or {})
        example_rows = conn.execute(
            """
            SELECT * FROM cognix_dataset_examples
            WHERE username = ? AND dataset_id = ?
            ORDER BY quality_score DESC, created_at DESC
            """,
            (username, dataset_id),
        ).fetchall()
        quality_rows = conn.execute(
            """
            SELECT * FROM cognix_dataset_quality_scores
            WHERE username = ? AND dataset_id = ?
            ORDER BY quality_score DESC, created_at DESC
            """,
            (username, dataset_id),
        ).fetchall()
        dataset["examples"] = [_hydrate_dataset_example(item) for item in _rows_to_dicts(example_rows)]
        dataset["qualityScores"] = [_hydrate_dataset_quality_score(item) for item in _rows_to_dicts(quality_rows)]
        return dataset
    finally:
        conn.close()


def _hydrate_persona(row: dict[str, Any]) -> dict[str, Any]:
    row["config"] = _json_or_default(row.get("config_json"), {})
    row["toolPermissions"] = _json_or_default(row.get("tool_permissions_json"), {})
    row["memoryScope"] = _json_or_default(row.get("memory_scope_json"), {})
    return row


def _hydrate_persona_version(row: dict[str, Any]) -> dict[str, Any]:
    row["config"] = _json_or_default(row.get("config_json"), {})
    return row


def _hydrate_persona_project_binding(row: dict[str, Any]) -> dict[str, Any]:
    row["binding"] = _json_or_default(row.get("binding_json"), {})
    return row


def create_persona(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    persona_id = str(plan.get("personaId") or _new_id("pers"))[:160]
    config = plan.get("config") if isinstance(plan.get("config"), dict) else {}
    prompt_template = plan.get("systemPromptTemplate") if isinstance(plan.get("systemPromptTemplate"), dict) else {}
    tool_permissions = plan.get("toolPermissions") if isinstance(plan.get("toolPermissions"), dict) else {}
    memory_scope = plan.get("memoryScope") if isinstance(plan.get("memoryScope"), dict) else {}
    binding_project_id = project_id or plan.get("projectBinding", {}).get("projectId") if isinstance(plan.get("projectBinding"), dict) else project_id
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(version_number) AS version_number FROM cognix_persona_versions WHERE username = ? AND persona_id = ?",
            (username, persona_id),
        ).fetchone()
        version_number = int((row["version_number"] if row else 0) or 0) + 1
        conn.execute(
            """
            INSERT INTO cognix_personas
                (
                    id, username, name, role, tone, level, preferred_model, status,
                    config_json, system_prompt, tool_permissions_json,
                    memory_scope_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                role = excluded.role,
                tone = excluded.tone,
                level = excluded.level,
                preferred_model = excluded.preferred_model,
                config_json = excluded.config_json,
                system_prompt = excluded.system_prompt,
                tool_permissions_json = excluded.tool_permissions_json,
                memory_scope_json = excluded.memory_scope_json,
                updated_at = excluded.updated_at
            """,
            (
                persona_id,
                username,
                str(config.get("name") or "Persona CogniX")[:180],
                str(config.get("role") or "Assistant CogniX")[:180],
                str(config.get("tone") or "clear")[:80],
                str(config.get("level") or "adaptive")[:80],
                (str(config.get("preferredModel"))[:240] if config.get("preferredModel") else None),
                json.dumps(config, ensure_ascii = False),
                str(prompt_template.get("content") or ""),
                json.dumps(tool_permissions, ensure_ascii = False),
                json.dumps(memory_scope, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_persona_versions
                (
                    id, persona_id, username, version_number, template_version,
                    config_json, system_prompt, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("pver"),
                persona_id,
                username,
                version_number,
                str(plan.get("templateEngineVersion") or "")[:120],
                json.dumps(config, ensure_ascii = False),
                str(prompt_template.get("content") or ""),
                now,
            ),
        )
        if binding_project_id:
            binding = plan.get("projectBinding") if isinstance(plan.get("projectBinding"), dict) else {}
            conn.execute(
                """
                INSERT INTO cognix_persona_project_bindings
                    (
                        id, persona_id, username, project_id, status,
                        binding_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                ON CONFLICT(username, persona_id, project_id) DO UPDATE SET
                    status = 'active',
                    binding_json = excluded.binding_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("pbind"),
                    persona_id,
                    username,
                    str(binding_project_id)[:160],
                    json.dumps(binding, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.commit()
        return get_persona(username, persona_id) or {}
    finally:
        conn.close()


def list_personas(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = min(max(int(limit or 100), 1), 300)
        if project_id:
            rows = conn.execute(
                """
                SELECT p.*
                FROM cognix_personas p
                INNER JOIN cognix_persona_project_bindings b
                    ON b.persona_id = p.id AND b.username = p.username
                WHERE p.username = ? AND b.project_id = ? AND p.status = 'active'
                ORDER BY p.updated_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_personas
                WHERE username = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_persona(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_persona(username: str, persona_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_personas WHERE id = ? AND username = ? AND status = 'active'",
            (persona_id, username),
        ).fetchone()
        if row is None:
            return None
        persona = _hydrate_persona(row_to_dict(row) or {})
        version_rows = conn.execute(
            """
            SELECT * FROM cognix_persona_versions
            WHERE username = ? AND persona_id = ?
            ORDER BY version_number DESC
            """,
            (username, persona_id),
        ).fetchall()
        binding_rows = conn.execute(
            """
            SELECT * FROM cognix_persona_project_bindings
            WHERE username = ? AND persona_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            """,
            (username, persona_id),
        ).fetchall()
        persona["versions"] = [_hydrate_persona_version(item) for item in _rows_to_dicts(version_rows)]
        persona["projectBindings"] = [_hydrate_persona_project_binding(item) for item in _rows_to_dicts(binding_rows)]
        return persona
    finally:
        conn.close()


def _hydrate_gpt(row: dict[str, Any]) -> dict[str, Any]:
    row["gptId"] = row.get("id")
    row["config"] = _json_or_default(row.get("config_json"), {})
    row["toolBinding"] = _json_or_default(row.get("tool_binding_json"), {})
    row["documentBinding"] = _json_or_default(row.get("document_binding_json"), {})
    row["memoryBinding"] = _json_or_default(row.get("memory_binding_json"), {})
    row["permissionBinding"] = _json_or_default(row.get("permission_binding_json"), {})
    return row


def _hydrate_gpt_version(row: dict[str, Any]) -> dict[str, Any]:
    row["config"] = _json_or_default(row.get("config_json"), {})
    return row


def _hydrate_gpt_project_binding(row: dict[str, Any]) -> dict[str, Any]:
    row["binding"] = _json_or_default(row.get("binding_json"), {})
    return row


def _hydrate_gpt_usage_log(row: dict[str, Any]) -> dict[str, Any]:
    row["gptId"] = row.get("gpt_id")
    row["runtimePlan"] = _json_or_default(row.get("runtime_plan_json"), {})
    return row


def create_gpt(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    gpt_id = str(plan.get("gptId") or _new_id("gpt"))[:160]
    config = plan.get("config") if isinstance(plan.get("config"), dict) else {}
    runtime = plan.get("runtimeInstructions") if isinstance(plan.get("runtimeInstructions"), dict) else {}
    tool_binding = plan.get("toolBinding") if isinstance(plan.get("toolBinding"), dict) else {}
    document_binding = plan.get("documentBinding") if isinstance(plan.get("documentBinding"), dict) else {}
    memory_binding = plan.get("memoryBinding") if isinstance(plan.get("memoryBinding"), dict) else {}
    permission_binding = plan.get("permissionBinding") if isinstance(plan.get("permissionBinding"), dict) else {}
    project_binding = plan.get("projectBinding") if isinstance(plan.get("projectBinding"), dict) else {}
    binding_project_id = project_id or project_binding.get("projectId")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(version_number) AS version_number FROM cognix_gpt_versions WHERE username = ? AND gpt_id = ?",
            (username, gpt_id),
        ).fetchone()
        version_number = int((row["version_number"] if row else 0) or 0) + 1
        conn.execute(
            """
            INSERT INTO cognix_gpts
                (
                    id, username, name, description, preferred_model, privacy_level,
                    share_scope, icon, status, config_json, instructions,
                    runtime_instructions, tool_binding_json, document_binding_json,
                    memory_binding_json, permission_binding_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                preferred_model = excluded.preferred_model,
                privacy_level = excluded.privacy_level,
                share_scope = excluded.share_scope,
                icon = excluded.icon,
                config_json = excluded.config_json,
                instructions = excluded.instructions,
                runtime_instructions = excluded.runtime_instructions,
                tool_binding_json = excluded.tool_binding_json,
                document_binding_json = excluded.document_binding_json,
                memory_binding_json = excluded.memory_binding_json,
                permission_binding_json = excluded.permission_binding_json,
                updated_at = excluded.updated_at
            """,
            (
                gpt_id,
                username,
                str(config.get("name") or "GPT CogniX")[:180],
                str(config.get("description") or "")[:1000],
                (str(config.get("preferredModel"))[:240] if config.get("preferredModel") else None),
                str(config.get("privacyLevel") or "private")[:80],
                str(config.get("shareScope") or "private")[:80],
                str(config.get("icon") or "sparkles")[:80],
                json.dumps(config, ensure_ascii = False),
                str(config.get("instructions") or ""),
                str(runtime.get("content") or ""),
                json.dumps(tool_binding, ensure_ascii = False),
                json.dumps(document_binding, ensure_ascii = False),
                json.dumps(memory_binding, ensure_ascii = False),
                json.dumps(permission_binding, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_gpt_versions
                (
                    id, gpt_id, username, version_number, manager_version,
                    config_json, runtime_instructions, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("gver"),
                gpt_id,
                username,
                version_number,
                str(plan.get("gptManagerVersion") or "")[:120],
                json.dumps(config, ensure_ascii = False),
                str(runtime.get("content") or ""),
                now,
            ),
        )
        if binding_project_id:
            conn.execute(
                """
                INSERT INTO cognix_gpt_project_bindings
                    (
                        id, gpt_id, username, project_id, status,
                        binding_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                ON CONFLICT(username, gpt_id, project_id) DO UPDATE SET
                    status = 'active',
                    binding_json = excluded.binding_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _new_id("gbind"),
                    gpt_id,
                    username,
                    str(binding_project_id)[:160],
                    json.dumps(project_binding, ensure_ascii = False),
                    now,
                    now,
                ),
            )
        conn.commit()
        return get_gpt(username, gpt_id) or {}
    finally:
        conn.close()


def list_gpts(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = min(max(int(limit or 100), 1), 300)
        if project_id:
            rows = conn.execute(
                """
                SELECT g.*
                FROM cognix_gpts g
                INNER JOIN cognix_gpt_project_bindings b
                    ON b.gpt_id = g.id AND b.username = g.username
                WHERE g.username = ? AND b.project_id = ? AND g.status = 'active'
                ORDER BY g.updated_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_gpts
                WHERE username = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_gpt(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_gpt(username: str, gpt_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_gpts WHERE id = ? AND username = ? AND status = 'active'",
            (gpt_id, username),
        ).fetchone()
        if row is None:
            return None
        gpt = _hydrate_gpt(row_to_dict(row) or {})
        version_rows = conn.execute(
            """
            SELECT * FROM cognix_gpt_versions
            WHERE username = ? AND gpt_id = ?
            ORDER BY version_number DESC
            """,
            (username, gpt_id),
        ).fetchall()
        binding_rows = conn.execute(
            """
            SELECT * FROM cognix_gpt_project_bindings
            WHERE username = ? AND gpt_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            """,
            (username, gpt_id),
        ).fetchall()
        usage_rows = conn.execute(
            """
            SELECT * FROM cognix_gpt_usage_logs
            WHERE username = ? AND gpt_id = ?
            ORDER BY created_at DESC
            LIMIT 40
            """,
            (username, gpt_id),
        ).fetchall()
        gpt["versions"] = [_hydrate_gpt_version(item) for item in _rows_to_dicts(version_rows)]
        gpt["projectBindings"] = [_hydrate_gpt_project_binding(item) for item in _rows_to_dicts(binding_rows)]
        gpt["usageLogs"] = [_hydrate_gpt_usage_log(item) for item in _rows_to_dicts(usage_rows)]
        return gpt
    finally:
        conn.close()


def create_gpt_usage_log(username: str, *, gpt_id: str, runtime_plan: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    log_id = _new_id("guse")
    project_id = runtime_plan.get("projectId")
    objective = str(runtime_plan.get("objective") or "")[:500]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_gpt_usage_logs
                (id, gpt_id, username, project_id, objective_excerpt, runtime_plan_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                gpt_id,
                username,
                str(project_id)[:160] if project_id else None,
                objective,
                json.dumps(runtime_plan, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_gpt_usage_logs WHERE id = ?", (log_id,)).fetchone()
        return _hydrate_gpt_usage_log(row_to_dict(row) or {})
    finally:
        conn.close()


def _hydrate_command_usage_log(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_command_usage_log(username: str, *, command_plan: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    log_id = _new_id("cmdlog")
    command = command_plan.get("command") if isinstance(command_plan.get("command"), dict) else {}
    command_id = str(command_plan.get("commandId") or command.get("id") or "unknown_command")[:160]
    command_label = str(command.get("label") or command_id)[:240]
    project_id = command_plan.get("projectId")
    query = str(command_plan.get("query") or "")[:240]
    status = str(command_plan.get("status") or "unknown")[:80]
    metadata = {
        "commandPaletteVersion": command_plan.get("commandPaletteVersion"),
        "commandRegistryVersion": command_plan.get("commandRegistryVersion"),
        "permissionFilterVersion": command_plan.get("permissionFilterVersion"),
        "allowedToRun": command_plan.get("allowedToRun"),
        "missingPermissions": command.get("missingPermissions", []),
        "route": command_plan.get("executionPlan", {}).get("route"),
        "actionType": command_plan.get("executionPlan", {}).get("actionType"),
        "sideEffects": command_plan.get("sideEffects", {}),
    }
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_command_usage_logs
                (id, username, command_id, command_label, project_id, query, result_status, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                username,
                command_id,
                command_label,
                str(project_id)[:160] if project_id else None,
                query,
                status,
                json.dumps(metadata, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_command_usage_logs WHERE id = ?", (log_id,)).fetchone()
        return _hydrate_command_usage_log(row_to_dict(row) or {})
    finally:
        conn.close()


def list_command_usage_logs(username: str, *, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        safe_limit = min(max(int(limit or 100), 1), 300)
        rows = conn.execute(
            """
            SELECT * FROM cognix_command_usage_logs
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, safe_limit),
        ).fetchall()
        return [_hydrate_command_usage_log(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_intent_prediction(row: dict[str, Any]) -> dict[str, Any]:
    row["domainProbabilities"] = _json_or_default(row.get("probabilities_json"), [])
    row["suggestion"] = _json_or_default(row.get("suggestion_json"), {})
    row["preloadPlan"] = _json_or_default(row.get("preload_plan_json"), {})
    return row


def _hydrate_preload_event(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_intent_prediction(
    username: str,
    *,
    prediction: dict[str, Any],
    project_id: str | None = None,
    input_excerpt: str | None = None,
) -> dict[str, Any]:
    prediction_id = _new_id("ipred")
    now = _now()
    suggestion = prediction.get("suggestion") if isinstance(prediction.get("suggestion"), dict) else {}
    preload_plan = prediction.get("preloadPlan") if isinstance(prediction.get("preloadPlan"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_intent_predictions
                (
                    id, username, project_id, project_type, selected_domain,
                    confidence_score, input_excerpt, probabilities_json,
                    suggestion_json, preload_plan_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction_id,
                username,
                project_id or prediction.get("projectId"),
                prediction.get("projectType"),
                str(prediction.get("selectedDomain") or "general")[:80],
                float(prediction.get("confidence") or 0.0),
                str(input_excerpt or "")[:1000],
                json.dumps(prediction.get("domainProbabilities") or [], ensure_ascii = False),
                json.dumps(suggestion, ensure_ascii = False),
                json.dumps(preload_plan, ensure_ascii = False),
                now,
            ),
        )
        if preload_plan:
            conn.execute(
                """
                INSERT INTO cognix_preload_events
                    (
                        id, username, prediction_id, project_id, event_type,
                        target_model_id, status, metadata_json, created_at
                    )
                VALUES (?, ?, ?, ?, 'preload_plan_created', ?, 'planned_no_execution', ?, ?)
                """,
                (
                    _new_id("pload"),
                    username,
                    prediction_id,
                    project_id or prediction.get("projectId"),
                    preload_plan.get("targetModelId"),
                    json.dumps(preload_plan, ensure_ascii = False),
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return get_intent_prediction(username, prediction_id) or {}


def get_intent_prediction(username: str, prediction_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_intent_predictions WHERE id = ? AND username = ?",
            (prediction_id, username),
        ).fetchone()
        if row is None:
            return None
        prediction = _hydrate_intent_prediction(row_to_dict(row) or {})
        event_rows = conn.execute(
            """
            SELECT * FROM cognix_preload_events
            WHERE username = ? AND prediction_id = ?
            ORDER BY created_at DESC
            """,
            (username, prediction_id),
        ).fetchall()
        prediction["preloadEvents"] = [_hydrate_preload_event(item) for item in _rows_to_dicts(event_rows)]
        return prediction
    finally:
        conn.close()


def list_intent_predictions(username: str, *, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_intent_predictions
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, safe_limit),
        ).fetchall()
        return [_hydrate_intent_prediction(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def list_preload_events(username: str, *, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_preload_events
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, safe_limit),
        ).fetchall()
        return [_hydrate_preload_event(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_project_ui_profile(row: dict[str, Any]) -> dict[str, Any]:
    row["profile"] = _json_or_default(row.get("profile_json"), {})
    return row


def create_project_ui_profile(
    username: str,
    *,
    profile: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    profile_id = _new_id("uiprof")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_ui_profiles
                (
                    id, username, project_id, project_type, profile_key, viewport,
                    theme, profile_json, status, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                profile_id,
                username,
                project_id or profile.get("projectId"),
                str(profile.get("projectType") or "general")[:120],
                str(profile.get("profileKey") or "general")[:120],
                str(profile.get("viewport") or "desktop")[:40],
                str(profile.get("theme") or "dark")[:40],
                json.dumps(profile, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_project_ui_profile(username, profile_id) or {}


def get_project_ui_profile(username: str, profile_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_project_ui_profiles WHERE id = ? AND username = ?",
            (profile_id, username),
        ).fetchone()
        if row is None:
            return None
        return _hydrate_project_ui_profile(row_to_dict(row) or {})
    finally:
        conn.close()


def list_project_ui_profiles(username: str, *, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_project_ui_profiles
            WHERE username = ? AND status = 'active'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, safe_limit),
        ).fetchall()
        return [_hydrate_project_ui_profile(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_background_job(row: dict[str, Any]) -> dict[str, Any]:
    row["jobPlan"] = _json_or_default(row.get("job_plan_json"), {})
    return row


def _hydrate_agent_run(row: dict[str, Any]) -> dict[str, Any]:
    row["runPlan"] = _json_or_default(row.get("run_plan_json"), {})
    return row


def _hydrate_job_log(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_background_job_from_plan(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    job_id = _new_id("bjob")
    run_id = _new_id("arun")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_background_jobs
                (
                    id, username, project_id, job_type, title, status, priority,
                    progress_percent, job_plan_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, 'queued', ?, 0, ?, ?, ?)
            """,
            (
                job_id,
                username,
                project_id or plan.get("projectId"),
                str(plan.get("jobType") or "prepare_report")[:120],
                str(plan.get("title") or "Background job")[:180],
                str(plan.get("priority") or "normal")[:40],
                json.dumps(plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_background_agent_runs
                (id, username, job_id, status, runner_type, run_plan_json, created_at, updated_at)
            VALUES (?, ?, ?, 'planned', 'AgentRunner', ?, ?, ?)
            """,
            (
                run_id,
                username,
                job_id,
                json.dumps(plan.get("agentRunPlan") or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_background_job_logs
                (id, username, job_id, run_id, level, message, progress_percent, metadata_json, created_at)
            VALUES (?, ?, ?, ?, 'info', ?, 0, ?, ?)
            """,
            (
                _new_id("jlog"),
                username,
                job_id,
                run_id,
                "Background job planned and queued; worker execution has not started.",
                json.dumps({"sideEffects": plan.get("sideEffects", {})}, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_background_job(username, job_id) or {}


def get_background_job(username: str, job_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_background_jobs WHERE id = ? AND username = ?",
            (job_id, username),
        ).fetchone()
        if row is None:
            return None
        job = _hydrate_background_job(row_to_dict(row) or {})
        run_rows = conn.execute(
            "SELECT * FROM cognix_background_agent_runs WHERE username = ? AND job_id = ? ORDER BY created_at DESC",
            (username, job_id),
        ).fetchall()
        log_rows = conn.execute(
            "SELECT * FROM cognix_background_job_logs WHERE username = ? AND job_id = ? ORDER BY created_at DESC",
            (username, job_id),
        ).fetchall()
        job["runs"] = [_hydrate_agent_run(item) for item in _rows_to_dicts(run_rows)]
        job["logs"] = [_hydrate_job_log(item) for item in _rows_to_dicts(log_rows)]
        return job
    finally:
        conn.close()


def list_background_jobs(username: str, *, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_background_jobs
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (username, safe_limit),
        ).fetchall()
        return [_hydrate_background_job(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_timeline_event(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_timeline_event(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    event = plan.get("event") if isinstance(plan.get("event"), dict) else {}
    event_id = _new_id("tl")
    created_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_timeline_events
                (
                    id, username, project_id, event_type, title, summary,
                    source_type, source_id, importance, metadata_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                username,
                project_id or plan.get("projectId"),
                str(event.get("eventType") or "architecture_decision")[:120],
                str(event.get("title") or "Timeline event")[:240],
                str(event.get("summary") or "")[:2000],
                event.get("sourceType"),
                event.get("sourceId"),
                str(event.get("importance") or "normal")[:40],
                json.dumps(event.get("metadata") or {}, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_project_timeline_events WHERE id = ? AND username = ?",
            (event_id, username),
        ).fetchone()
        return _hydrate_timeline_event(row_to_dict(row) or {})
    finally:
        conn.close()


def list_timeline_events(
    username: str,
    *,
    project_id: str | None = None,
    event_type: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    clauses = ["username = ?"]
    params: list[Any] = [username]
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if query:
        clauses.append("(LOWER(title) LIKE ? OR LOWER(summary) LIKE ?)")
        needle = f"%{query.lower()}%"
        params.extend([needle, needle])
    params.append(safe_limit)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_project_timeline_events
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_timeline_event(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_simulation_run(row: dict[str, Any]) -> dict[str, Any]:
    row["plan"] = _json_or_default(row.get("plan_json"), {})
    row["report"] = _json_or_default(row.get("report_json"), {})
    return row


def _hydrate_simulation_metric(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def create_simulation_run(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    scenario = plan.get("scenario") if isinstance(plan.get("scenario"), dict) else {}
    report = plan.get("report") if isinstance(plan.get("report"), dict) else {}
    metrics = plan.get("metrics") if isinstance(plan.get("metrics"), list) else []
    run_id = _new_id("sim")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_simulation_runs
                (
                    id, username, project_id, project_type, simulation_type, scenario,
                    user_count, duration_minutes, status, plan_json, report_json,
                    created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?)
            """,
            (
                run_id,
                username,
                project_id or plan.get("projectId"),
                plan.get("projectType"),
                str(scenario.get("simulationType") or "business")[:80],
                str(scenario.get("description") or "")[:4000],
                int(scenario.get("userCount") or 1),
                int(scenario.get("durationMinutes") or 15),
                json.dumps(plan, ensure_ascii = False),
                json.dumps(report, ensure_ascii = False),
                now,
                now,
            ),
        )
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            conn.execute(
                """
                INSERT INTO cognix_simulation_metrics
                    (id, username, run_id, metric_key, metric_value, unit, severity, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("smet"),
                    username,
                    run_id,
                    str(metric.get("id") or metric.get("metricKey") or "metric")[:120],
                    float(metric.get("value") or 0),
                    str(metric.get("unit") or "")[:40],
                    str(metric.get("severity") or "low")[:40],
                    json.dumps(metric, ensure_ascii = False),
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return get_simulation_run(username, run_id) or {}


def get_simulation_run(username: str, run_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_simulation_runs WHERE id = ? AND username = ?",
            (run_id, username),
        ).fetchone()
        if row is None:
            return None
        run = _hydrate_simulation_run(row_to_dict(row) or {})
        metric_rows = conn.execute(
            """
            SELECT * FROM cognix_simulation_metrics
            WHERE username = ? AND run_id = ?
            ORDER BY created_at ASC
            """,
            (username, run_id),
        ).fetchall()
        run["metrics"] = [_hydrate_simulation_metric(item) for item in _rows_to_dicts(metric_rows)]
        return run
    finally:
        conn.close()


def list_simulation_runs(
    username: str,
    *,
    project_id: str | None = None,
    simulation_type: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    clauses = ["username = ?"]
    params: list[Any] = [username]
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if simulation_type:
        clauses.append("simulation_type = ?")
        params.append(simulation_type)
    if query:
        clauses.append("(LOWER(scenario) LIKE ? OR LOWER(report_json) LIKE ?)")
        needle = f"%{query.lower()}%"
        params.extend([needle, needle])
    params.append(safe_limit)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_simulation_runs
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_simulation_run(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_sandbox(row: dict[str, Any]) -> dict[str, Any]:
    row["isolation"] = _json_or_default(row.get("isolation_json"), {})
    return row


def _hydrate_sandbox_run(row: dict[str, Any]) -> dict[str, Any]:
    row["plan"] = _json_or_default(row.get("plan_json"), {})
    row["pipeline"] = _json_or_default(row.get("pipeline_json"), [])
    return row


def _hydrate_sandbox_report(row: dict[str, Any]) -> dict[str, Any]:
    row["report"] = _json_or_default(row.get("report_json"), {})
    return row


def create_sandbox_run(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    target = plan.get("target") if isinstance(plan.get("target"), dict) else {}
    isolation = plan.get("isolation") if isinstance(plan.get("isolation"), dict) else {}
    report = plan.get("report") if isinstance(plan.get("report"), dict) else {}
    pipeline = plan.get("pipeline") if isinstance(plan.get("pipeline"), list) else []
    sandbox_id = _new_id("sbx")
    run_id = _new_id("srun")
    report_id = _new_id("srep")
    now = _now()
    resolved_project_id = project_id or plan.get("projectId")
    target_type = str(target.get("type") or "feature")[:80]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_sandboxes
                (id, username, project_id, target_type, status, badge_label, isolation_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'planned', 'Mode sandbox actif', ?, ?, ?)
            """,
            (
                sandbox_id,
                username,
                resolved_project_id,
                target_type,
                json.dumps(isolation, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_sandbox_runs
                (
                    id, username, sandbox_id, project_id, target_type, objective,
                    change_summary, status, plan_json, pipeline_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'planned_no_execution', ?, ?, ?, ?)
            """,
            (
                run_id,
                username,
                sandbox_id,
                resolved_project_id,
                target_type,
                str(target.get("objective") or "")[:4000],
                str(target.get("changeSummary") or "")[:4000],
                json.dumps(plan, ensure_ascii = False),
                json.dumps(pipeline, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_sandbox_reports
                (id, username, sandbox_id, run_id, risk_level, report_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                username,
                sandbox_id,
                run_id,
                str(report.get("riskLevel") or "low")[:40],
                json.dumps(report, ensure_ascii = False),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_sandbox_run(username, run_id) or {}


def get_sandbox_run(username: str, run_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_sandbox_runs WHERE id = ? AND username = ?",
            (run_id, username),
        ).fetchone()
        if row is None:
            return None
        run = _hydrate_sandbox_run(row_to_dict(row) or {})
        sandbox_row = conn.execute(
            "SELECT * FROM cognix_sandboxes WHERE id = ? AND username = ?",
            (run.get("sandbox_id"), username),
        ).fetchone()
        report_row = conn.execute(
            """
            SELECT * FROM cognix_sandbox_reports
            WHERE username = ? AND run_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (username, run_id),
        ).fetchone()
        run["sandbox"] = _hydrate_sandbox(row_to_dict(sandbox_row) or {}) if sandbox_row else None
        run["reportRecord"] = _hydrate_sandbox_report(row_to_dict(report_row) or {}) if report_row else None
        return run
    finally:
        conn.close()


def list_sandbox_runs(
    username: str,
    *,
    project_id: str | None = None,
    target_type: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    clauses = ["username = ?"]
    params: list[Any] = [username]
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if target_type:
        clauses.append("target_type = ?")
        params.append(target_type)
    if query:
        clauses.append("(LOWER(objective) LIKE ? OR LOWER(change_summary) LIKE ? OR LOWER(plan_json) LIKE ?)")
        needle = f"%{query.lower()}%"
        params.extend([needle, needle, needle])
    params.append(safe_limit)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_sandbox_runs
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_sandbox_run(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def _hydrate_response_evaluation(row: dict[str, Any]) -> dict[str, Any]:
    row["issues"] = _json_or_default(row.get("issues_json"), [])
    row["evaluation"] = _json_or_default(row.get("evaluation_json"), {})
    row["verification_required"] = bool(row.get("verification_required"))
    return row


def list_response_evaluations(
    username: str,
    *,
    message_id: str | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 80), 1), 200)
    conn = get_connection()
    try:
        if message_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_response_evaluations
                WHERE username = ? AND message_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, message_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_response_evaluations
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_response_evaluation(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def create_response_evaluation(
    username: str,
    *,
    evaluation: dict[str, Any],
    message_id: str | None = None,
    thread_id: str | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    evaluation_id = _new_id("rfl")
    confidence = evaluation.get("confidence") if isinstance(evaluation.get("confidence"), dict) else {}
    issues = evaluation.get("issues") if isinstance(evaluation.get("issues"), list) else []
    score = float(confidence.get("score") or 0.0)
    label = str(confidence.get("label") or "unknown")
    verification_required = 1 if confidence.get("verificationRequired") else 0
    recommended_action = str(confidence.get("recommendedAction") or "unknown")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_response_evaluations
                (
                    id, username, message_id, thread_id, project_id, model_id,
                    confidence_score, confidence_label, verification_required,
                    recommended_action, issues_json, evaluation_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                username,
                message_id,
                thread_id,
                project_id,
                model_id,
                score,
                label,
                verification_required,
                recommended_action,
                json.dumps(issues, ensure_ascii = False),
                json.dumps(evaluation, ensure_ascii = False),
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_response_evaluations WHERE id = ?",
            (evaluation_id,),
        ).fetchone()
        stored = row_to_dict(row) or {}
        return _hydrate_response_evaluation(stored)
    finally:
        conn.close()


def _hydrate_response_variant(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def list_response_variants(
    username: str,
    *,
    message_id: str | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 80), 1), 200)
    conn = get_connection()
    try:
        if message_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_response_variants
                WHERE username = ? AND message_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, message_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_response_variants
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_response_variant(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def create_response_variant(
    username: str,
    *,
    variant_type: str,
    title: str,
    content: str,
    message_id: str | None = None,
    thread_id: str | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
    ranking_score: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    variant_id = _new_id("var")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_response_variants
                (
                    id, username, message_id, thread_id, project_id, variant_type,
                    title, content, model_id, ranking_score, metadata_json,
                    created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                variant_id,
                username,
                message_id,
                thread_id,
                project_id,
                variant_type.strip(),
                title.strip(),
                content,
                model_id,
                ranking_score,
                json.dumps(metadata or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_response_variants WHERE id = ?",
            (variant_id,),
        ).fetchone()
        stored = row_to_dict(row) or {}
        return _hydrate_response_variant(stored)
    finally:
        conn.close()


def _hydrate_debate_session(row: dict[str, Any]) -> dict[str, Any]:
    row["roles"] = _json_or_default(row.get("roles_json"), [])
    row["plan"] = _json_or_default(row.get("plan_json"), {})
    return row


def _hydrate_debate_output(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def _list_debate_rounds_for_session(conn: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    return _rows_to_dicts(
        conn.execute(
            """
            SELECT * FROM cognix_debate_rounds
            WHERE session_id = ?
            ORDER BY round_index ASC
            """,
            (session_id,),
        ).fetchall()
    )


def _list_debate_outputs_for_session(conn: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    outputs = _rows_to_dicts(
        conn.execute(
            """
            SELECT * FROM cognix_debate_outputs
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    )
    return [_hydrate_debate_output(output) for output in outputs]


def list_debate_sessions(
    username: str,
    *,
    message_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 50), 1), 200)
    conn = get_connection()
    try:
        if message_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_debate_sessions
                WHERE username = ? AND message_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, message_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_debate_sessions
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        sessions = [_hydrate_debate_session(row) for row in _rows_to_dicts(rows)]
        for session in sessions:
            session["rounds"] = _list_debate_rounds_for_session(conn, str(session.get("id")))
            session["outputs"] = _list_debate_outputs_for_session(conn, str(session.get("id")))
        return sessions
    finally:
        conn.close()


def get_debate_session(username: str, session_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_debate_sessions WHERE id = ? AND username = ?",
            (session_id, username),
        ).fetchone()
        if row is None:
            return None
        session = _hydrate_debate_session(row_to_dict(row) or {})
        session["rounds"] = _list_debate_rounds_for_session(conn, session_id)
        session["outputs"] = _list_debate_outputs_for_session(conn, session_id)
        return session
    finally:
        conn.close()


def create_debate_session(
    username: str,
    *,
    plan: dict[str, Any],
    prompt: str,
    message_id: str | None = None,
    thread_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    session_id = _new_id("deb")
    roles = plan.get("roles") if isinstance(plan.get("roles"), list) else []
    rounds = plan.get("rounds") if isinstance(plan.get("rounds"), list) else []
    max_rounds = int(plan.get("summary", {}).get("maxRounds") or len(rounds) or 3)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_debate_sessions
                (
                    id, username, message_id, thread_id, project_id, prompt_excerpt,
                    status, max_rounds, roles_json, plan_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                username,
                message_id,
                thread_id,
                project_id,
                " ".join(str(prompt or "").split())[:500],
                max_rounds,
                json.dumps(roles, ensure_ascii = False),
                json.dumps(plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        for item in rounds:
            if not isinstance(item, dict):
                continue
            conn.execute(
                """
                INSERT INTO cognix_debate_rounds
                    (
                        id, session_id, username, round_index, role_id, label,
                        purpose, public_prompt, status, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
                """,
                (
                    _new_id("rnd"),
                    session_id,
                    username,
                    int(item.get("roundIndex") or 0),
                    str(item.get("roleId") or "unknown"),
                    str(item.get("label") or ""),
                    str(item.get("purpose") or ""),
                    str(item.get("publicPrompt") or ""),
                    now,
                    now,
                ),
            )
        conn.commit()
        return get_debate_session(username, session_id) or {}
    finally:
        conn.close()


def create_debate_output(
    username: str,
    *,
    session_id: str,
    role_id: str,
    output_type: str,
    public_summary: str,
    content: str = "",
    round_id: str | None = None,
    model_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    output_id = _new_id("dbo")
    conn = get_connection()
    try:
        session = conn.execute(
            "SELECT * FROM cognix_debate_sessions WHERE id = ? AND username = ?",
            (session_id, username),
        ).fetchone()
        if session is None:
            raise ValueError("Debate session not found")
        if round_id:
            round_row = conn.execute(
                "SELECT * FROM cognix_debate_rounds WHERE id = ? AND session_id = ? AND username = ?",
                (round_id, session_id, username),
            ).fetchone()
            if round_row is None:
                raise ValueError("Debate round not found")
        conn.execute(
            """
            INSERT INTO cognix_debate_outputs
                (
                    id, session_id, round_id, username, role_id, output_type,
                    public_summary, content, model_id, metadata_json, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                output_id,
                session_id,
                round_id,
                username,
                role_id.strip(),
                output_type.strip(),
                public_summary.strip(),
                content,
                model_id,
                json.dumps(metadata or {}, ensure_ascii = False),
                now,
            ),
        )
        conn.execute(
            "UPDATE cognix_debate_sessions SET status = 'in_progress', updated_at = ? WHERE id = ? AND username = ?",
            (now, session_id, username),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_debate_outputs WHERE id = ?",
            (output_id,),
        ).fetchone()
        stored = row_to_dict(row) or {}
        return _hydrate_debate_output(stored)
    finally:
        conn.close()


def _hydrate_installed_tool(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = _json_or_default(row.get("metadata_json"), {})
    return row


def list_installed_tools(username: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM cognix_installed_tools
            WHERE username = ?
            ORDER BY updated_at DESC
            """,
            (username,),
        ).fetchall()
        return [_hydrate_installed_tool(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def upsert_installed_tool(
    username: str,
    *,
    tool_id: str,
    tool_name: str = "",
    status: str = "installed",
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    normalized_tool_id = tool_id.strip().lower()
    if not normalized_tool_id:
        raise ValueError("tool_id is required")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_installed_tools
                (username, tool_id, tool_name, status, source, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, tool_id) DO UPDATE SET
                tool_name = excluded.tool_name,
                status = excluded.status,
                source = excluded.source,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                username,
                normalized_tool_id,
                tool_name.strip()[:240],
                status.strip().lower()[:80] or "installed",
                source.strip().lower()[:80] or "manual",
                json.dumps(metadata or {}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_installed_tools WHERE username = ? AND tool_id = ?",
            (username, normalized_tool_id),
        ).fetchone()
        return _hydrate_installed_tool(row_to_dict(row) or {})
    finally:
        conn.close()


def _hydrate_tool_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    row["recommendation"] = _json_or_default(row.get("recommendation_json"), {})
    row["ignored"] = bool(row.get("ignored"))
    return row


def create_tool_recommendations(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    recommendations = [
        item
        for item in (plan.get("recommendations") or [])
        if isinstance(item, dict)
    ]
    if not recommendations:
        return []
    now = _now()
    rows_to_return: list[dict[str, Any]] = []
    conn = get_connection()
    try:
        for recommendation in recommendations:
            rec_id = _new_id("trec")
            conn.execute(
                """
                INSERT INTO cognix_tool_recommendations
                    (
                        id, username, project_id, need_id, tool_id, tool_name,
                        category, reason, status, confidence, recommendation_json,
                        ignored, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    rec_id,
                    username,
                    project_id,
                    str(recommendation.get("needId") or "general")[:160],
                    str(recommendation.get("toolId") or "")[:160],
                    str(recommendation.get("toolName") or "")[:240],
                    str(recommendation.get("category") or "other")[:120],
                    str(recommendation.get("reason") or "")[:2000],
                    str(recommendation.get("status") or "recommended")[:80],
                    float(recommendation.get("confidence") or 0.0),
                    json.dumps(recommendation, ensure_ascii = False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM cognix_tool_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
            rows_to_return.append(_hydrate_tool_recommendation(row_to_dict(row) or {}))
        conn.commit()
        return rows_to_return
    finally:
        conn.close()


def list_tool_recommendations(
    username: str,
    *,
    project_id: str | None = None,
    include_ignored: bool = False,
    limit: int = 80,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 80), 1), 200)
    conn = get_connection()
    try:
        clauses = ["username = ?"]
        params: list[Any] = [username]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if not include_ignored:
            clauses.append("ignored = 0")
        params.append(safe_limit)
        rows = conn.execute(
            f"""
            SELECT * FROM cognix_tool_recommendations
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_hydrate_tool_recommendation(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def ignore_tool_recommendation(username: str, recommendation_id: str) -> dict[str, Any] | None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE cognix_tool_recommendations
            SET ignored = 1, status = 'ignored', updated_at = ?
            WHERE id = ? AND username = ?
            """,
            (now, recommendation_id, username),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_tool_recommendations WHERE id = ? AND username = ?",
            (recommendation_id, username),
        ).fetchone()
        if row is None:
            return None
        return _hydrate_tool_recommendation(row_to_dict(row) or {})
    finally:
        conn.close()


def _hydrate_context_graph_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    row["graph"] = _json_or_default(row.get("graph_json"), {})
    return row


def create_context_graph_snapshot(
    username: str,
    *,
    graph: dict[str, Any],
    project_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    now = _now()
    snapshot_id = _new_id("cgraph")
    nodes = [
        item
        for item in (graph.get("nodes") or [])
        if isinstance(item, dict)
    ]
    edges = [
        item
        for item in (graph.get("edges") or [])
        if isinstance(item, dict)
    ]
    snapshot_title = (title or graph.get("projectName") or project_id or "Context Graph").strip()[:240]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_context_graph_snapshots
                (id, username, project_id, title, graph_json, node_count, edge_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                username,
                project_id,
                snapshot_title,
                json.dumps(graph, ensure_ascii = False),
                len(nodes),
                len(edges),
                now,
            ),
        )
        for node in nodes:
            conn.execute(
                """
                INSERT INTO cognix_context_nodes
                    (
                        id, snapshot_id, username, project_id, node_key, node_type,
                        label, source, weight, metadata_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("cnode"),
                    snapshot_id,
                    username,
                    project_id,
                    str(node.get("id") or "")[:180],
                    str(node.get("type") or "unknown")[:80],
                    str(node.get("label") or "")[:240],
                    str(node.get("source") or "unknown")[:120],
                    float(node.get("weight") or 0.0),
                    json.dumps(node.get("metadata") or {}, ensure_ascii = False),
                    now,
                ),
            )
        for edge in edges:
            conn.execute(
                """
                INSERT INTO cognix_context_edges
                    (
                        id, snapshot_id, username, project_id, source_node_key,
                        target_node_key, edge_type, label, weight, metadata_json,
                        created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("cedge"),
                    snapshot_id,
                    username,
                    project_id,
                    str(edge.get("source") or "")[:180],
                    str(edge.get("target") or "")[:180],
                    str(edge.get("type") or "related_to")[:80],
                    str(edge.get("label") or "")[:240],
                    float(edge.get("weight") or 0.0),
                    json.dumps(edge.get("metadata") or {}, ensure_ascii = False),
                    now,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_context_graph_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        return _hydrate_context_graph_snapshot(row_to_dict(row) or {})
    finally:
        conn.close()


def list_context_graph_snapshots(
    username: str,
    *,
    project_id: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 40), 1), 120)
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_context_graph_snapshots
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_context_graph_snapshots
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_context_graph_snapshot(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_context_graph_snapshot(username: str, snapshot_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_context_graph_snapshots WHERE id = ? AND username = ?",
            (snapshot_id, username),
        ).fetchone()
        if row is None:
            return None
        snapshot = _hydrate_context_graph_snapshot(row_to_dict(row) or {})
        snapshot["nodes"] = _rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM cognix_context_nodes
                WHERE snapshot_id = ? AND username = ?
                ORDER BY node_type ASC, label ASC
                """,
                (snapshot_id, username),
            ).fetchall()
        )
        snapshot["edges"] = _rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM cognix_context_edges
                WHERE snapshot_id = ? AND username = ?
                ORDER BY edge_type ASC, label ASC
                """,
                (snapshot_id, username),
            ).fetchall()
        )
        return snapshot
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


def _hydrate_model_comparison(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["comparison"] = _json_or_default(item.get("comparison_json"), {})
    return item


def _hydrate_comparison_output(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["evaluation"] = _json_or_default(item.get("evaluation_json"), {})
    return item


def _hydrate_user_model_preference(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_or_default(item.get("metadata_json"), {})
    return item


def _attach_comparison_outputs(conn: sqlite3.Connection, comparison: dict[str, Any]) -> dict[str, Any]:
    comparison_id = str(comparison.get("id") or "")
    username = str(comparison.get("username") or "")
    rows = conn.execute(
        """
        SELECT * FROM cognix_comparison_outputs
        WHERE username = ? AND comparison_id = ?
        ORDER BY created_at ASC
        """,
        (username, comparison_id),
    ).fetchall()
    comparison["outputs"] = [_hydrate_comparison_output(row) for row in _rows_to_dicts(rows)]
    return comparison


def create_model_comparison(
    username: str,
    *,
    plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    comparison_id = _new_id("mcmp")
    models = [item for item in plan.get("models", []) if isinstance(item, dict)]
    status_value = "ready_for_choice" if any(item.get("outputText") for item in models) else "planned"
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_model_comparisons
                (
                    id, username, project_id, prompt_excerpt, prompt_hash,
                    status, selected_output_id, comparison_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                comparison_id,
                username,
                project_id or plan.get("projectId"),
                str(plan.get("promptExcerpt") or "")[:1000],
                str(plan.get("promptHash") or "")[:80],
                status_value,
                json.dumps({**plan, "comparisonId": comparison_id}, ensure_ascii = False),
                now,
                now,
            ),
        )
        for model in models:
            conn.execute(
                """
                INSERT INTO cognix_comparison_outputs
                    (
                        id, comparison_id, username, model_id, model_label,
                        provider_type, output_text, status, evaluation_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("cout"),
                    comparison_id,
                    username,
                    str(model.get("modelId") or "")[:180],
                    str(model.get("modelLabel") or model.get("modelId") or "")[:240],
                    str(model.get("providerType") or "local")[:80],
                    str(model.get("outputText") or ""),
                    str(model.get("status") or "awaiting_generation")[:80],
                    json.dumps(model.get("evaluation") or {}, ensure_ascii = False),
                    now,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM cognix_model_comparisons WHERE id = ? AND username = ?",
            (comparison_id, username),
        ).fetchone()
        return _attach_comparison_outputs(conn, _hydrate_model_comparison(row_to_dict(row) or {}))
    finally:
        conn.close()


def list_model_comparisons(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_model_comparisons
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_model_comparisons
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_model_comparison(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_model_comparison(username: str, comparison_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_model_comparisons WHERE username = ? AND id = ?",
            (username, comparison_id),
        ).fetchone()
        if row is None:
            return None
        return _attach_comparison_outputs(conn, _hydrate_model_comparison(row_to_dict(row) or {}))
    finally:
        conn.close()


def choose_model_comparison_output(
    username: str,
    comparison_id: str,
    output_id: str,
    *,
    reason: str | None = None,
) -> dict[str, Any] | None:
    now = _now()
    conn = get_connection()
    try:
        output_row = conn.execute(
            """
            SELECT * FROM cognix_comparison_outputs
            WHERE username = ? AND comparison_id = ? AND id = ?
            """,
            (username, comparison_id, output_id),
        ).fetchone()
        if output_row is None:
            return None
        output = row_to_dict(output_row) or {}
        model_id = str(output.get("model_id") or "")
        conn.execute(
            """
            UPDATE cognix_model_comparisons
            SET selected_output_id = ?, status = 'choice_recorded', updated_at = ?
            WHERE username = ? AND id = ?
            """,
            (output_id, now, username, comparison_id),
        )
        conn.execute(
            """
            INSERT INTO cognix_user_model_preferences
                (
                    id, username, model_id, preference_type, comparison_id,
                    output_id, reason, metadata_json, created_at, updated_at
                )
            VALUES (?, ?, ?, 'chosen_best_response', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, model_id, preference_type) DO UPDATE SET
                comparison_id = excluded.comparison_id,
                output_id = excluded.output_id,
                reason = excluded.reason,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                _new_id("mpref"),
                username,
                model_id,
                comparison_id,
                output_id,
                str(reason or "")[:1000],
                json.dumps(
                    {
                        "modelLabel": output.get("model_label"),
                        "providerType": output.get("provider_type"),
                        "evaluation": _json_or_default(output.get("evaluation_json"), {}),
                    },
                    ensure_ascii = False,
                ),
                now,
                now,
            ),
        )
        conn.commit()
        comparison = get_model_comparison(username, comparison_id)
        preference_row = conn.execute(
            """
            SELECT * FROM cognix_user_model_preferences
            WHERE username = ? AND model_id = ? AND preference_type = 'chosen_best_response'
            """,
            (username, model_id),
        ).fetchone()
        return {
            "comparison": comparison,
            "output": _hydrate_comparison_output(output),
            "preference": _hydrate_user_model_preference(row_to_dict(preference_row) or {}),
        }
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


def _hydrate_project_dna(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["preferredModels"] = _json_or_default(item.get("preferred_models_json"), [])
    item["allowedTools"] = _json_or_default(item.get("allowed_tools_json"), [])
    item["dna"] = _json_or_default(item.get("dna_json"), {})
    return item


def _hydrate_project_decision(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def upsert_project_dna(
    username: str,
    project_id: str,
    *,
    plan: dict[str, Any],
) -> dict[str, Any]:
    profile = plan.get("profile") if isinstance(plan.get("profile"), dict) else {}
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_project_dna
                (
                    project_id, username, objective, context, response_style,
                    preferred_models_json, allowed_tools_json, dna_json,
                    dna_hash, status, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                username = excluded.username,
                objective = excluded.objective,
                context = excluded.context,
                response_style = excluded.response_style,
                preferred_models_json = excluded.preferred_models_json,
                allowed_tools_json = excluded.allowed_tools_json,
                dna_json = excluded.dna_json,
                dna_hash = excluded.dna_hash,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                username,
                str(profile.get("objective") or "")[:4000],
                str(profile.get("context") or "")[:8000],
                str(profile.get("responseStyle") or "")[:4000],
                json.dumps(profile.get("preferredModels") or [], ensure_ascii = False),
                json.dumps(profile.get("allowedTools") or [], ensure_ascii = False),
                json.dumps(plan, ensure_ascii = False),
                str(profile.get("dnaHash") or "")[:80],
                str(plan.get("status") or "draft")[:80],
                now,
                now,
            ),
        )
        conn.execute(
            "DELETE FROM cognix_project_constraints WHERE username = ? AND project_id = ?",
            (username, project_id),
        )
        for index, constraint in enumerate(profile.get("constraints") or []):
            label = str(constraint)[:240]
            if not label:
                continue
            conn.execute(
                """
                INSERT INTO cognix_project_constraints
                    (
                        id, username, project_id, constraint_type, label, value,
                        priority, status, created_at, updated_at
                    )
                VALUES (?, ?, ?, 'general', ?, ?, ?, 'active', ?, ?)
                """,
                (
                    _new_id("pcon"),
                    username,
                    project_id,
                    label,
                    label,
                    50 + index,
                    now,
                    now,
                ),
            )
        conn.execute(
            "DELETE FROM cognix_project_decisions WHERE username = ? AND project_id = ?",
            (username, project_id),
        )
        for decision in profile.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            title = str(decision.get("title") or "")[:240]
            if not title:
                continue
            conn.execute(
                """
                INSERT INTO cognix_project_decisions
                    (
                        id, username, project_id, decision_key, title,
                        rationale, status, decided_at, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("pdec"),
                    username,
                    project_id,
                    str(decision.get("decisionKey") or _new_id("decision"))[:160],
                    title,
                    str(decision.get("rationale") or "")[:4000],
                    str(decision.get("status") or "active")[:80],
                    decision.get("decidedAt"),
                    now,
                    now,
                ),
            )
        conn.commit()
        return get_project_dna(username, project_id) or {}
    finally:
        conn.close()


def get_project_dna(username: str, project_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_project_dna WHERE username = ? AND project_id = ?",
            (username, project_id),
        ).fetchone()
        if row is None:
            return None
        dna = _hydrate_project_dna(row_to_dict(row) or {})
        constraint_rows = conn.execute(
            """
            SELECT * FROM cognix_project_constraints
            WHERE username = ? AND project_id = ? AND status = 'active'
            ORDER BY priority ASC, created_at ASC
            """,
            (username, project_id),
        ).fetchall()
        decision_rows = conn.execute(
            """
            SELECT * FROM cognix_project_decisions
            WHERE username = ? AND project_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            """,
            (username, project_id),
        ).fetchall()
        dna["constraints"] = _rows_to_dicts(constraint_rows)
        dna["decisions"] = [_hydrate_project_decision(row) for row in _rows_to_dicts(decision_rows)]
        return dna
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


def _hydrate_research_topic(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["sources"] = _json_or_default(item.get("sources_json"), [])
    return item


def _hydrate_research_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["item"] = _json_or_default(item.get("item_json"), {})
    return item


def create_research_topic(
    username: str,
    *,
    topic_plan: dict[str, Any],
) -> dict[str, Any]:
    now = _now()
    topic_id = _new_id("rtop")
    topic = topic_plan.get("topic") if isinstance(topic_plan.get("topic"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_research_topics
                (
                    id, username, topic, topic_key, project_id,
                    frequency, output_format, sources_json,
                    status, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                topic_id,
                username,
                str(topic.get("name") or "")[:240],
                str(topic.get("topicKey") or topic_id)[:160],
                topic.get("projectId"),
                str(topic.get("frequency") or "weekly")[:80],
                str(topic.get("outputFormat") or "brief")[:80],
                json.dumps(topic_plan.get("sources") or [], ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_research_topics WHERE id = ?", (topic_id,)).fetchone()
        return _hydrate_research_topic(row_to_dict(row) or {})
    finally:
        conn.close()


def list_research_topics(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_research_topics
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_research_topics
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_research_topic(row_to_dict(row) or {}) for row in rows]
    finally:
        conn.close()


def get_research_topic(username: str, topic_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM cognix_research_topics
            WHERE username = ? AND id = ?
            """,
            (username, topic_id),
        ).fetchone()
        return _hydrate_research_topic(row_to_dict(row) or {}) if row else None
    finally:
        conn.close()


def create_research_items(
    username: str,
    *,
    topic_id: str | None,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    created_at = _now()
    conn = get_connection()
    created_ids: list[str] = []
    try:
        for item in items:
            item_id = _new_id("ritm")
            created_ids.append(item_id)
            conn.execute(
                """
                INSERT INTO cognix_research_items
                    (
                        id, username, topic_id, title, summary, source,
                        item_type, url, published_at, relevance_score,
                        item_json, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    username,
                    topic_id,
                    str(item.get("title") or "")[:240],
                    str(item.get("summary") or "")[:4000],
                    str(item.get("source") or "provided")[:160],
                    str(item.get("itemType") or "research_item")[:80],
                    str(item.get("url") or "")[:1000] or None,
                    item.get("publishedAt"),
                    float(item.get("relevanceScore") or 0.0),
                    json.dumps(item, ensure_ascii = False),
                    created_at,
                ),
            )
        conn.commit()
        if not created_ids:
            return []
        placeholders = ", ".join("?" for _ in created_ids)
        rows = conn.execute(
            f"SELECT * FROM cognix_research_items WHERE id IN ({placeholders}) ORDER BY created_at DESC",
            created_ids,
        ).fetchall()
        return [_hydrate_research_item(row_to_dict(row) or {}) for row in rows]
    finally:
        conn.close()


def list_research_items(
    username: str,
    *,
    topic_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    conn = get_connection()
    try:
        if topic_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_research_items
                WHERE username = ? AND topic_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, topic_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_research_items
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_research_item(row_to_dict(row) or {}) for row in rows]
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


def _hydrate_evolution_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["item"] = _json_or_default(item.get("item_json"), {})
    return item


def _hydrate_evolution_experiment(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["experiment"] = _json_or_default(item.get("experiment_json"), {})
    return item


def _hydrate_evolution_benchmark_result(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["result"] = _json_or_default(item.get("result_json"), {})
    return item


def _hydrate_integration_proposal(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["proposal"] = _json_or_default(item.get("proposal_json"), {})
    return item


def create_evolution_item(
    username: str,
    *,
    item_plan: dict[str, Any],
    project_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    item_id = _new_id("evo")
    technique = item_plan.get("technique") if isinstance(item_plan.get("technique"), dict) else {}
    risk = item_plan.get("risk") if isinstance(item_plan.get("risk"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_evolution_items
                (
                    id, username, project_id, technique_name, source_name,
                    category, status, risk_level, item_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                username,
                project_id or item_plan.get("projectId"),
                str(technique.get("name") or "")[:240],
                str(technique.get("sourceName") or "")[:240],
                str(technique.get("category") or "evaluation_method")[:120],
                str(item_plan.get("status") or "ready_for_sandbox_plan")[:120],
                str(risk.get("level") or "medium")[:80],
                json.dumps(item_plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cognix_evolution_items WHERE id = ?", (item_id,)).fetchone()
        return _hydrate_evolution_item(row_to_dict(row) or {})
    finally:
        conn.close()


def list_evolution_items(username: str, *, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_evolution_items
                WHERE username = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, project_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_evolution_items
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_evolution_item(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_evolution_item(username: str, item_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_evolution_items WHERE username = ? AND id = ?",
            (username, item_id),
        ).fetchone()
        return _hydrate_evolution_item(row_to_dict(row) or {}) if row else None
    finally:
        conn.close()


def create_evolution_experiment(
    username: str,
    *,
    item_id: str,
    experiment_plan: dict[str, Any],
) -> dict[str, Any]:
    now = _now()
    experiment_id = _new_id("evexp")
    benchmark = experiment_plan.get("benchmarkPlan") if isinstance(experiment_plan.get("benchmarkPlan"), dict) else {}
    proposal = experiment_plan.get("integrationProposal") if isinstance(experiment_plan.get("integrationProposal"), dict) else {}
    report = experiment_plan.get("report") if isinstance(experiment_plan.get("report"), dict) else {}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cognix_evolution_experiments
                (id, username, item_id, status, sandbox_id, experiment_json, created_at, updated_at)
            VALUES (?, ?, ?, 'planned', NULL, ?, ?, ?)
            """,
            (
                experiment_id,
                username,
                item_id,
                json.dumps(experiment_plan, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_evolution_benchmark_results
                (id, username, item_id, experiment_id, metric, gain_percent, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("evbench"),
                username,
                item_id,
                experiment_id,
                str(benchmark.get("metric") or "quality_speed_cost")[:160],
                float(benchmark.get("expectedGainPercent") or 0.0),
                json.dumps({"benchmarkPlan": benchmark, "report": report}, ensure_ascii = False),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO cognix_integration_proposals
                (
                    id, username, item_id, experiment_id, recommendation,
                    status, proposal_json, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, 'requires_human_approval', ?, ?, ?)
            """,
            (
                _new_id("evprop"),
                username,
                item_id,
                experiment_id,
                str(proposal.get("recommendation") or report.get("recommendation") or "watch_and_retest")[:160],
                json.dumps({"proposal": proposal, "report": report}, ensure_ascii = False),
                now,
                now,
            ),
        )
        conn.commit()
        experiment = get_evolution_experiment(username, experiment_id)
        benchmarks = list_evolution_benchmark_results(username, experiment_id = experiment_id)
        proposals = list_integration_proposals(username, item_id = item_id)
        return {
            "experiment": experiment,
            "benchmarkResults": benchmarks,
            "proposals": proposals,
        }
    finally:
        conn.close()


def get_evolution_experiment(username: str, experiment_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cognix_evolution_experiments WHERE username = ? AND id = ?",
            (username, experiment_id),
        ).fetchone()
        return _hydrate_evolution_experiment(row_to_dict(row) or {}) if row else None
    finally:
        conn.close()


def list_evolution_benchmark_results(
    username: str,
    *,
    experiment_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        if experiment_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_evolution_benchmark_results
                WHERE username = ? AND experiment_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, experiment_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_evolution_benchmark_results
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_evolution_benchmark_result(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def list_integration_proposals(
    username: str,
    *,
    item_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 100), 1), 300)
    conn = get_connection()
    try:
        if item_id:
            rows = conn.execute(
                """
                SELECT * FROM cognix_integration_proposals
                WHERE username = ? AND item_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, item_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognix_integration_proposals
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (username, safe_limit),
            ).fetchall()
        return [_hydrate_integration_proposal(row) for row in _rows_to_dicts(rows)]
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
