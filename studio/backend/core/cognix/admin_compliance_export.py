# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX admin compliance export service."""

from __future__ import annotations

import csv
import io
import json
from hashlib import sha256
from typing import Any


COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION = "cognix_compliance_export_service_v1"
COGNIX_REPORT_BUILDER_VERSION = "cognix_compliance_report_builder_v1"
COGNIX_EXPORT_JOB_SERVICE_VERSION = "cognix_export_job_service_v1"

COMPLIANCE_EXPORT_SERVICES = [
    "ComplianceExportService",
    "ReportBuilder",
    "ExportJobService",
]

COMPLIANCE_EXPORT_TABLES = [
    "compliance_exports",
    "export_jobs",
    "token_usage_events",
    "user_activity_events",
    "security_threats",
    "banned_users",
    "approval_requests",
    "admin_chat_access_logs",
    "audit_logs",
]

SUPPORTED_EXPORT_FORMATS = ["json", "markdown", "csv", "pdf"]
SUPPORTED_REPORT_TYPES = [
    "full",
    "usage_tokens",
    "user_activity",
    "security_threats",
    "banned_users",
    "approvals",
    "models_used",
    "tools_used",
    "document_access",
    "admin_chat_access",
]


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _token_total(row: dict[str, Any]) -> int:
    total = _as_int(row.get("total_tokens") or row.get("totalTokens"))
    if total:
        return total
    return _as_int(row.get("input_tokens") or row.get("inputTokens")) + _as_int(
        row.get("output_tokens") or row.get("outputTokens")
    )


def _checksum(payload: dict[str, Any], rendered_content: str) -> str:
    encoded = json.dumps(payload, sort_keys = True, ensure_ascii = False).encode("utf-8")
    return sha256(encoded + rendered_content.encode("utf-8")).hexdigest()


def build_compliance_export_blueprint() -> dict[str, Any]:
    return {
        "complianceExportServiceVersion": COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION,
        "reportBuilderVersion": COGNIX_REPORT_BUILDER_VERSION,
        "exportJobServiceVersion": COGNIX_EXPORT_JOB_SERVICE_VERSION,
        "mode": "native_admin_compliance_export",
        "services": COMPLIANCE_EXPORT_SERVICES,
        "tables": COMPLIANCE_EXPORT_TABLES,
        "reportTypes": SUPPORTED_REPORT_TYPES,
        "formats": SUPPORTED_EXPORT_FORMATS,
        "security": {
            "adminOnly": True,
            "organizationScoped": True,
            "exportJobsAudited": True,
            "sensitiveValuesRedactedByAuditLayer": True,
            "frontendDirectModelCallAllowed": False,
        },
        "sideEffects": {
            "databaseWrite": False,
            "exportWrite": False,
            "exportJobWrite": False,
            "auditWrite": False,
            "fileWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _section_enabled(report_type: str, section_id: str) -> bool:
    return report_type == "full" or report_type == section_id


def _usage_section(token_events: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, int] = {}
    by_user: dict[str, int] = {}
    total = 0
    for event in token_events:
        tokens = _token_total(event)
        total += tokens
        by_model[_norm(event.get("model_id") or event.get("modelId"), "unknown")] = (
            by_model.get(_norm(event.get("model_id") or event.get("modelId"), "unknown"), 0) + tokens
        )
        by_user[_norm(event.get("username"), "unknown")] = by_user.get(_norm(event.get("username"), "unknown"), 0) + tokens
    return {
        "id": "usage_tokens",
        "title": "Usage tokens",
        "summary": {"eventCount": len(token_events), "tokenTotal": total},
        "rows": [{"modelId": key, "tokenTotal": value} for key, value in sorted(by_model.items())],
        "byUser": [{"username": key, "tokenTotal": value} for key, value in sorted(by_user.items())],
    }


def _activity_section(activity_events: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for event in activity_events:
        event_type = _norm(event.get("event_type") or event.get("eventType"), "unknown")
        by_type[event_type] = by_type.get(event_type, 0) + 1
    return {
        "id": "user_activity",
        "title": "User activity",
        "summary": {"eventCount": len(activity_events), "eventTypeCount": len(by_type)},
        "rows": [{"eventType": key, "count": value} for key, value in sorted(by_type.items())],
    }


def _simple_section(section_id: str, title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "summary": {"rowCount": len(rows)},
        "rows": rows,
    }


def build_compliance_report(
    *,
    report_type: str,
    output_format: str,
    generated_by: str,
    token_events: list[dict[str, Any]],
    activity_events: list[dict[str, Any]],
    security_events: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    admin_chat_access_logs: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_type = _norm(report_type, "full").lower()
    if normalized_type not in SUPPORTED_REPORT_TYPES:
        raise ValueError("Unsupported compliance report type")
    normalized_format = _norm(output_format, "json").lower()
    if normalized_format not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError("Unsupported compliance export format")

    sections: list[dict[str, Any]] = []
    if _section_enabled(normalized_type, "usage_tokens"):
        sections.append(_usage_section(token_events))
    if _section_enabled(normalized_type, "user_activity"):
        sections.append(_activity_section(activity_events))
    if _section_enabled(normalized_type, "security_threats"):
        sections.append(_simple_section("security_threats", "Security threats", security_events))
    if _section_enabled(normalized_type, "banned_users"):
        sections.append(_simple_section("banned_users", "Banned users", bans))
    if _section_enabled(normalized_type, "approvals"):
        sections.append(_simple_section("approvals", "Approvals", approvals))
    if _section_enabled(normalized_type, "models_used"):
        sections.append(_usage_section(token_events) | {"id": "models_used", "title": "Models used"})
    if _section_enabled(normalized_type, "tools_used"):
        tool_logs = [
            log for log in audit_logs
            if "tool" in _norm(log.get("action")).lower() or "tool" in _norm(log.get("resource_type")).lower()
        ]
        sections.append(_simple_section("tools_used", "Tools used", tool_logs))
    if _section_enabled(normalized_type, "document_access"):
        document_logs = [
            log for log in audit_logs
            if "document" in _norm(log.get("action")).lower() or "document" in _norm(log.get("resource_type")).lower()
        ]
        sections.append(_simple_section("document_access", "Document access", document_logs))
    if _section_enabled(normalized_type, "admin_chat_access"):
        sections.append(_simple_section("admin_chat_access", "Admin chat access", admin_chat_access_logs))

    payload = {
        "reportBuilderVersion": COGNIX_REPORT_BUILDER_VERSION,
        "reportType": normalized_type,
        "outputFormat": normalized_format,
        "generatedBy": _norm(generated_by),
        "title": f"CogniX compliance export - {normalized_type.replace('_', ' ')}",
        "sections": sections,
        "summary": {
            "sectionCount": len(sections),
            "tokenEventCount": len(token_events),
            "activityEventCount": len(activity_events),
            "securityEventCount": len(security_events),
            "banCount": len(bans),
            "approvalCount": len(approvals),
            "adminChatAccessCount": len(admin_chat_access_logs),
        },
    }
    rendered = render_export_content(payload, normalized_format)
    payload["checksum"] = _checksum(payload, rendered)
    payload["renderedContent"] = rendered
    payload["sideEffects"] = build_compliance_export_blueprint()["sideEffects"]
    return payload


def render_export_content(report: dict[str, Any], output_format: str) -> str:
    normalized_format = _norm(output_format, "json").lower()
    if normalized_format == "json":
        return json.dumps(report, ensure_ascii = False, indent = 2)
    if normalized_format == "markdown" or normalized_format == "pdf":
        lines = [f"# {report.get('title')}", ""]
        for section in report.get("sections") or []:
            lines.extend([f"## {section.get('title')}", ""])
            summary = section.get("summary") if isinstance(section.get("summary"), dict) else {}
            lines.append(", ".join(f"{key}: {value}" for key, value in summary.items()) or "No summary.")
            lines.append("")
        if normalized_format == "pdf":
            lines.append("_PDF renderer handoff: content is markdown-ready and queued for PDF rendering._")
        return "\n".join(lines)
    if normalized_format == "csv":
        handle = io.StringIO()
        writer = csv.DictWriter(handle, fieldnames = ["section", "key", "value"])
        writer.writeheader()
        for section in report.get("sections") or []:
            summary = section.get("summary") if isinstance(section.get("summary"), dict) else {}
            for key, value in summary.items():
                writer.writerow({"section": section.get("id"), "key": key, "value": value})
        return handle.getvalue()
    raise ValueError("Unsupported compliance export format")


def build_export_job_plan(*, report: dict[str, Any], queued_by: str) -> dict[str, Any]:
    return {
        "exportJobServiceVersion": COGNIX_EXPORT_JOB_SERVICE_VERSION,
        "reportType": report.get("reportType"),
        "outputFormat": report.get("outputFormat"),
        "queuedBy": _norm(queued_by),
        "status": "queued",
        "progressPercent": 0,
        "requiresRenderer": report.get("outputFormat") == "pdf",
        "sideEffects": {
            "databaseWrite": False,
            "exportWrite": False,
            "exportJobWrite": False,
            "auditWrite": False,
            "fileWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }
