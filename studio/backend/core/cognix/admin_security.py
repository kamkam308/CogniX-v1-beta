# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX admin security, risk scoring, and health summaries.

The service consumes existing CogniX audit/security/runtime tables and returns
admin-ready summaries without mutating state or launching external scanners.
"""

from __future__ import annotations

from typing import Any


COGNIX_ADMIN_SECURITY_VERSION = "cognix_admin_security_v1"
COGNIX_RISK_SCORING_VERSION = "cognix_risk_scoring_v1"
COGNIX_SYSTEM_HEALTH_VERSION = "cognix_system_health_v1"

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_POINTS = {"low": 8, "medium": 18, "high": 34, "critical": 55}
ACTIVE_BAN_STATUSES = {"pending_admin_review", "active", "permanent"}
OPEN_REPORT_STATUSES = {"open", "in_review"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _severity(value: Any) -> str:
    normalized = _norm(value, "low").lower()
    return normalized if normalized in SEVERITY_ORDER else "low"


def _severity_rank(value: Any) -> int:
    return SEVERITY_ORDER.get(_severity(value), 1)


def _max_severity(items: list[dict[str, Any]], key: str = "severity") -> str:
    severity = "low"
    for item in items:
        candidate = _severity(item.get(key))
        if _severity_rank(candidate) > _severity_rank(severity):
            severity = candidate
    return severity


def _risk_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _bounded_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _event_title(event: dict[str, Any]) -> str:
    label = _norm(event.get("pattern_label") or event.get("patternLabel"))
    if label:
        return label
    category = _norm(event.get("category"), "security_event").replace("_", " ")
    return category.title()


def _event_subject(event: dict[str, Any]) -> str:
    username = _norm(event.get("username"))
    if username:
        return username
    client_key = _norm(event.get("client_key") or event.get("clientKey"))
    return client_key or "anonymous"


def _threat_from_event(event: dict[str, Any]) -> dict[str, Any]:
    severity = _severity(event.get("severity"))
    title = _event_title(event)
    subject = _event_subject(event)
    path = _norm(event.get("path"), "unknown path")
    method = _norm(event.get("method"), "UNKNOWN").upper()
    excerpt = _norm(event.get("excerpt"))
    ban_id = _norm(event.get("ban_id") or event.get("banId"))
    created_at = _norm(event.get("created_at") or event.get("createdAt"))
    evidence = f"{method} {path}"
    if excerpt:
        evidence = f"{evidence} :: {excerpt[:180]}"
    return {
        "id": _norm(event.get("id"), "security-event"),
        "title": title,
        "description": f"{title} detecte pour {subject} sur {method} {path}.",
        "impact": {
            "critical": "Risque de compromission ou d'execution non autorisee.",
            "high": "Risque eleve sur les donnees, l'authentification ou l'exposition reseau.",
            "medium": "Signal suspect necessitant verification admin.",
            "low": "Signal faible a conserver pour correlation.",
        }[severity],
        "severity": severity,
        "filesAffected": [],
        "evidence": evidence,
        "recommendedSolution": {
            "critical": "Examiner immediatement, conserver les preuves et maintenir le blocage temporaire si present.",
            "high": "Verifier l'utilisateur, la route touchee et les permissions associees.",
            "medium": "Surveiller les repetitions et comparer avec les logs d'audit.",
            "low": "Conserver dans l'historique de securite.",
        }[severity],
        "status": "active" if ban_id else "open",
        "subject": subject,
        "sourceType": "security_event",
        "sourceEventId": _norm(event.get("id")),
        "banId": ban_id or None,
        "createdAt": created_at,
    }


def build_security_threat_report(
    *,
    security_events: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    threats = [_threat_from_event(event) for event in security_events]
    active_bans = [item for item in bans if _norm(item.get("status")).lower() in ACTIVE_BAN_STATUSES]
    open_reports = [item for item in reports if _norm(item.get("status")).lower() in OPEN_REPORT_STATUSES]
    critical_audits = [
        item for item in audit_logs
        if _severity(item.get("severity")) == "critical" or "permission" in _norm(item.get("action")).lower()
    ]

    for ban in active_bans:
        threats.append(
            {
                "id": f"ban:{_norm(ban.get('id'), 'unknown')}",
                "title": "Blocage utilisateur actif",
                "description": f"Ban actif ou en revue pour {_norm(ban.get('username') or ban.get('client_key'), 'unknown')}.",
                "impact": "Acces limite pour proteger CogniX pendant la revue admin.",
                "severity": "high" if _norm(ban.get("status")) != "permanent" else "critical",
                "filesAffected": [],
                "evidence": _norm(ban.get("reason"), "ban record"),
                "recommendedSolution": "Revoir le ban, documenter la decision et cloturer si le risque est leve.",
                "status": _norm(ban.get("status"), "active"),
                "subject": _norm(ban.get("username") or ban.get("client_key"), "unknown"),
                "sourceType": "ban",
                "sourceEventId": _norm(ban.get("id")),
                "createdAt": _norm(ban.get("created_at") or ban.get("createdAt")),
            }
        )

    severity_counts = {key: 0 for key in ("critical", "high", "medium", "low")}
    status_counts: dict[str, int] = {}
    for threat in threats:
        severity_counts[_severity(threat.get("severity"))] += 1
        status_key = _norm(threat.get("status"), "open")
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

    summary_status = "green"
    if severity_counts["critical"]:
        summary_status = "red"
    elif severity_counts["high"] or len(open_reports) >= 3 or len(critical_audits) >= 3:
        summary_status = "yellow"

    return {
        "reportVersion": COGNIX_ADMIN_SECURITY_VERSION,
        "mode": "native_read_only",
        "summary": {
            "status": summary_status,
            "total": len(threats),
            "critical": severity_counts["critical"],
            "high": severity_counts["high"],
            "medium": severity_counts["medium"],
            "low": severity_counts["low"],
            "activeBans": len(active_bans),
            "openReports": len(open_reports),
            "permissionAuditSignals": len(critical_audits),
            "statusCounts": status_counts,
        },
        "threats": threats,
        "sideEffects": {
            "databaseWrite": False,
            "externalScan": False,
            "networkCall": False,
            "banMutation": False,
        },
    }


def build_risk_scoring(
    *,
    security_events: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    features: dict[str, dict[str, Any]] = {}

    def bucket(entity_type: str, entity_id: str) -> dict[str, Any]:
        key = f"{entity_type}:{entity_id}"
        if key not in features:
            features[key] = {
                "entityType": entity_type,
                "entityId": entity_id,
                "securityEvents": 0,
                "criticalEvents": 0,
                "highEvents": 0,
                "permissionChanges": 0,
                "cloudActions": 0,
                "activeBans": 0,
                "openReports": 0,
                "auditWarnings": 0,
            }
        return features[key]

    for event in security_events:
        item = bucket("user", _event_subject(event))
        severity = _severity(event.get("severity"))
        item["securityEvents"] += 1
        if severity == "critical":
            item["criticalEvents"] += 1
        if severity == "high":
            item["highEvents"] += 1

    for ban in bans:
        if _norm(ban.get("status")).lower() in ACTIVE_BAN_STATUSES:
            bucket("user", _norm(ban.get("username") or ban.get("client_key"), "unknown"))["activeBans"] += 1

    for report in reports:
        if _norm(report.get("status")).lower() in OPEN_REPORT_STATUSES:
            bucket("user", _norm(report.get("username"), "unknown"))["openReports"] += 1

    for log in audit_logs:
        action = _norm(log.get("action")).lower()
        username = _norm(log.get("username") or log.get("actor_username") or log.get("actorUsername"), "system")
        item = bucket("user", username)
        if "permission" in action:
            item["permissionChanges"] += 1
        if "cloud" in action:
            item["cloudActions"] += 1
        if _severity(log.get("severity")) in {"high", "critical"} or _norm(log.get("severity")) == "warning":
            item["auditWarnings"] += 1

    scores: list[dict[str, Any]] = []
    for item in features.values():
        score = (
            item["criticalEvents"] * 42
            + item["highEvents"] * 22
            + max(0, item["securityEvents"] - item["criticalEvents"] - item["highEvents"]) * 7
            + item["activeBans"] * 25
            + item["permissionChanges"] * 8
            + item["cloudActions"] * 10
            + item["openReports"] * 6
            + item["auditWarnings"] * 4
        )
        bounded = _bounded_score(score)
        level = _risk_level(bounded)
        recommendation = {
            "critical": "Limiter l'acces, examiner les evenements et documenter une decision admin.",
            "high": "Verifier les permissions, les bans et les actions cloud recentes.",
            "medium": "Surveiller les repetitions et demander une revue si le score augmente.",
            "low": "Aucune action urgente; conserver le suivi.",
        }[level]
        scores.append(
            {
                "entityType": item["entityType"],
                "entityId": item["entityId"],
                "score": bounded,
                "level": level,
                "features": item,
                "explanation": (
                    f"{item['securityEvents']} evenement(s) securite, "
                    f"{item['permissionChanges']} changement(s) permission, "
                    f"{item['cloudActions']} action(s) cloud."
                ),
                "recommendedAction": recommendation,
            }
        )

    scores.sort(key = lambda row: (row["score"], row["entityId"]), reverse = True)
    max_score = scores[0]["score"] if scores else 0
    return {
        "scoringVersion": COGNIX_RISK_SCORING_VERSION,
        "mode": "native_read_only",
        "summary": {
            "entities": len(scores),
            "maxScore": max_score,
            "maxLevel": _risk_level(max_score),
            "highOrCritical": sum(1 for item in scores if item["level"] in {"high", "critical"}),
        },
        "scores": scores,
        "sideEffects": {
            "databaseWrite": False,
            "permissionMutation": False,
            "cloudAction": False,
        },
    }


def build_system_health(
    *,
    hardware: dict[str, Any],
    security_report: dict[str, Any],
    risk_scoring: dict[str, Any],
    audit_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    gpu = _as_dict(hardware.get("gpu"))
    total_gb = float(memory.get("totalGb") or 0.0)
    available_gb = float(memory.get("availableGb") or 0.0)
    memory_pressure = "unknown"
    if total_gb > 0:
        ratio = available_gb / total_gb
        memory_pressure = "red" if ratio < 0.10 else "yellow" if ratio < 0.25 else "green"

    services = [
        {
            "id": "backend",
            "label": "CogniX backend",
            "status": "green",
            "detail": "API backend responsive; snapshot generated in-process.",
        },
        {
            "id": "security-monitor",
            "label": "Security monitor",
            "status": _as_dict(security_report.get("summary")).get("status", "green"),
            "detail": f"{_as_dict(security_report.get('summary')).get('total', 0)} menace(s) suivie(s).",
        },
        {
            "id": "risk-scoring",
            "label": "AI risk scoring",
            "status": "red"
            if _as_dict(risk_scoring.get("summary")).get("maxLevel") == "critical"
            else "yellow"
            if _as_dict(risk_scoring.get("summary")).get("maxLevel") == "high"
            else "green",
            "detail": f"{_as_dict(risk_scoring.get('summary')).get('entities', 0)} entite(s) scoree(s).",
        },
        {
            "id": "memory",
            "label": "Memory",
            "status": memory_pressure,
            "detail": f"{available_gb:.1f}GB available / {total_gb:.1f}GB total.",
        },
    ]

    overall = "green"
    if any(item["status"] == "red" for item in services):
        overall = "red"
    elif any(item["status"] == "yellow" for item in services):
        overall = "yellow"

    return {
        "healthVersion": COGNIX_SYSTEM_HEALTH_VERSION,
        "mode": "native_read_only",
        "overallStatus": overall,
        "metrics": {
            "cpu": {"count": hardware.get("cpuCount"), "backend": hardware.get("deviceBackend")},
            "memory": {"totalGb": total_gb, "availableGb": available_gb, "pressure": memory_pressure},
            "gpu": {
                "available": bool(gpu.get("available")),
                "deviceCount": len(gpu.get("devices") or []),
                "devices": gpu.get("devices") or [],
            },
            "audit": {"recentEntries": len(audit_logs)},
            "security": _as_dict(security_report.get("summary")),
            "risk": _as_dict(risk_scoring.get("summary")),
        },
        "services": services,
        "alerts": [
            {
                "id": item["id"],
                "severity": "critical" if item["status"] == "red" else "medium",
                "message": item["detail"],
            }
            for item in services
            if item["status"] in {"red", "yellow"}
        ],
        "sideEffects": {
            "databaseWrite": False,
            "networkCall": False,
            "workerMutation": False,
        },
    }
