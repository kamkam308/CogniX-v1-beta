# SPDX-License-Identifier: AGPL-3.0-only

"""CogniX native banned/suspended user administration and reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


COGNIX_BAN_SERVICE_VERSION = "cognix_ban_service_v1"
COGNIX_BAN_REPORT_GENERATOR_VERSION = "cognix_ban_report_generator_v1"
COGNIX_USER_RISK_SERVICE_VERSION = "cognix_user_risk_service_v1"

RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _key(value: Any, fallback: str = "") -> str:
    return _norm(value, fallback).lower()


def _risk(value: Any, fallback: str = "medium") -> str:
    risk = _key(value, fallback)
    return risk if risk in RISK_RANK else fallback


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_label(created_at: Any, temporary_until: Any) -> str:
    until = _parse_time(temporary_until)
    if until is not None:
        if until.tzinfo is None:
            until = until.replace(tzinfo = timezone.utc)
        remaining = int((until - datetime.now(timezone.utc)).total_seconds() // 3600)
        return f"{max(0, remaining)}h remaining"
    created = _parse_time(created_at)
    if created is None:
        return "unknown"
    if created.tzinfo is None:
        created = created.replace(tzinfo = timezone.utc)
    hours = int((datetime.now(timezone.utc) - created).total_seconds() // 3600)
    return f"{max(0, hours)}h elapsed"


def build_banned_blueprint() -> dict[str, Any]:
    return {
        "banServiceVersion": COGNIX_BAN_SERVICE_VERSION,
        "banReportGeneratorVersion": COGNIX_BAN_REPORT_GENERATOR_VERSION,
        "userRiskServiceVersion": COGNIX_USER_RISK_SERVICE_VERSION,
        "mode": "native_banned_users_with_reports",
        "services": ["BanService", "BanReportGenerator", "UserRiskService"],
        "tables": [
            "banned_users",
            "ban_reports",
            "ban_evidence_logs",
            "cognix_bans",
            "cognix_ban_reports",
            "cognix_ban_evidence_logs",
            "cognix_security_events",
            "cognix_reports",
        ],
        "fields": [
            "user",
            "reason",
            "date",
            "responsible_admin",
            "duration",
            "evidence_logs",
            "ai_report",
            "reactivation",
        ],
        "sideEffects": {
            "banWrite": False,
            "reportWrite": False,
            "evidenceWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def _events_for_ban(ban: dict[str, Any], security_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ban_id = _norm(ban.get("id"))
    username = _key(ban.get("username"))
    client_key = _key(ban.get("client_key") or ban.get("clientKey"))
    matches: list[dict[str, Any]] = []
    for event in security_events:
        if _norm(event.get("ban_id") or event.get("banId")) == ban_id:
            matches.append(event)
            continue
        if username and _key(event.get("username")) == username:
            matches.append(event)
            continue
        if client_key and _key(event.get("client_key") or event.get("clientKey")) == client_key:
            matches.append(event)
    return matches


def _reports_for_user(ban: dict[str, Any], reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    username = _key(ban.get("username"))
    if not username:
        return []
    return [report for report in reports if _key(report.get("username")) == username]


def _risk_from_evidence(ban: dict[str, Any], events: list[dict[str, Any]], reports: list[dict[str, Any]]) -> str:
    status = _key(ban.get("status"))
    if status == "permanent":
        return "critical"
    risk = "medium"
    for event in events:
        event_risk = _risk(event.get("severity"), "medium")
        if RISK_RANK[event_risk] > RISK_RANK[risk]:
            risk = event_risk
    if len(reports) >= 3 and RISK_RANK[risk] < RISK_RANK["high"]:
        risk = "high"
    return risk


def build_ban_ai_report(
    *,
    ban: dict[str, Any],
    security_events: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    risk = _risk_from_evidence(ban, security_events, reports)
    behaviors = sorted({_norm(item.get("pattern_label") or item.get("patternLabel") or item.get("category")) for item in security_events if item})
    rules = []
    if security_events:
        rules.append("security_policy")
    if reports:
        rules.append("community_reports")
    if _key(ban.get("status")) == "permanent":
        rules.append("permanent_ban_policy")
    recommendation = {
        "critical": "maintain_ban_and_require_admin_review",
        "high": "keep_suspended_until_evidence_reviewed",
        "medium": "review_and_consider_temporary_reactivation",
        "low": "reactivate_if_no_recent_evidence",
    }[risk]
    summary = _norm(ban.get("reason"), "Incident requires admin review.")
    return {
        "summary": summary,
        "detectedBehavior": ", ".join(item for item in behaviors if item) or "manual_admin_flag",
        "violatedRules": rules or ["manual_review"],
        "riskLevel": risk,
        "recommendation": recommendation,
        "reactivation": {
            "possible": _key(ban.get("status")) not in {"cleared", "permanent"} and risk in {"low", "medium"},
            "recommendedStatus": "cleared" if risk in {"low", "medium"} else "active",
        },
        "evidenceCount": len(security_events),
        "reportCount": len(reports),
        "generatorVersion": COGNIX_BAN_REPORT_GENERATOR_VERSION,
        "sideEffects": build_banned_blueprint()["sideEffects"],
    }


def _persisted_report_by_ban(ban_reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_norm(item.get("ban_id") or item.get("banId")): item for item in ban_reports}


def _manual_evidence_by_ban(evidence_logs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence_logs:
        grouped.setdefault(_norm(item.get("ban_id") or item.get("banId")), []).append(item)
    return grouped


def build_banned_dashboard(
    *,
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    security_events: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    ban_reports: list[dict[str, Any]] | None = None,
    evidence_logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    persisted_reports = _persisted_report_by_ban(ban_reports or [])
    manual_evidence = _manual_evidence_by_ban(evidence_logs or [])
    rows: list[dict[str, Any]] = []
    summary = {"total": len(bans), "active": 0, "pending": 0, "permanent": 0, "cleared": 0, "reactivationPossible": 0}

    for ban in bans:
        status = _key(ban.get("status"), "pending_admin_review")
        if status == "pending_admin_review":
            summary["pending"] += 1
        elif status in summary:
            summary[status] += 1
        events = _events_for_ban(ban, security_events)
        user_reports = _reports_for_user(ban, reports)
        generated_report = build_ban_ai_report(ban = ban, security_events = events, reports = user_reports)
        ban_id = _norm(ban.get("id"))
        persisted = persisted_reports.get(ban_id)
        ai_report = persisted.get("report") if persisted else generated_report
        reactivation = generated_report["reactivation"]
        if reactivation["possible"]:
            summary["reactivationPossible"] += 1
        related_audits = [
            item
            for item in audit_logs
            if _norm(item.get("resource_id") or item.get("resourceId")) == ban_id
            or (_norm(ban.get("username")) and _norm(item.get("username")) == _norm(ban.get("username")))
        ][:10]
        rows.append(
            {
                "banId": ban_id,
                "user": _norm(ban.get("username")) or None,
                "clientKey": _norm(ban.get("client_key") or ban.get("clientKey")) or None,
                "reason": _norm(ban.get("reason")),
                "status": status,
                "date": ban.get("created_at") or ban.get("createdAt"),
                "responsibleAdmin": ban.get("decided_by") or ban.get("decidedBy"),
                "duration": _duration_label(ban.get("created_at") or ban.get("createdAt"), ban.get("temporary_until") or ban.get("temporaryUntil")),
                "temporaryUntil": ban.get("temporary_until") or ban.get("temporaryUntil"),
                "evidence": {
                    "securityEvents": events,
                    "manualLogs": manual_evidence.get(ban_id, []),
                    "reports": user_reports,
                    "auditLogs": related_audits,
                },
                "aiReport": ai_report,
                "persistedReport": persisted,
                "reactivation": reactivation,
            }
        )

    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key = lambda item: (item["status"] == "cleared", risk_order.get(_risk(item["aiReport"].get("riskLevel")), 9), item["date"] or ""))
    return {
        "banServiceVersion": COGNIX_BAN_SERVICE_VERSION,
        "banReportGeneratorVersion": COGNIX_BAN_REPORT_GENERATOR_VERSION,
        "userRiskServiceVersion": COGNIX_USER_RISK_SERVICE_VERSION,
        "summary": summary,
        "bannedUsers": rows,
        "sideEffects": build_banned_blueprint()["sideEffects"],
    }
