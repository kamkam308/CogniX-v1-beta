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
COGNIX_RISK_FEATURE_EXTRACTOR_VERSION = "cognix_risk_feature_extractor_v1"
COGNIX_RISK_RECOMMENDATION_SERVICE_VERSION = "cognix_risk_recommendation_service_v1"
COGNIX_SYSTEM_HEALTH_VERSION = "cognix_system_health_v1"
COGNIX_WORKER_MONITOR_VERSION = "cognix_worker_monitor_v1"
COGNIX_RUNTIME_HEALTH_CHECKER_VERSION = "cognix_runtime_health_checker_v1"
COGNIX_SECURITY_THREAT_CENTER_VERSION = "cognix_security_threat_center_v1"
COGNIX_VULNERABILITY_SCANNER_ADAPTER_VERSION = "cognix_vulnerability_scanner_adapter_v1"

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_POINTS = {"low": 8, "medium": 18, "high": 34, "critical": 55}
ACTIVE_BAN_STATUSES = {"pending_admin_review", "active", "permanent"}
OPEN_REPORT_STATUSES = {"open", "in_review"}
RESOLVED_STATUSES = {"resolved", "closed", "cleared"}
IGNORED_STATUSES = {"ignored", "false_positive"}
SECURITY_THREAT_STATUSES = ["open", "active", "in_review", "resolved", "ignored"]
SECRET_EXPOSURE_TERMS = (
    "secret",
    "api_key",
    "api key",
    "access_token",
    "refresh_token",
    "hf_token",
    "bearer ",
    ".env",
    "credential",
    "password",
)

SECURITY_THREAT_SERVICES = [
    "SecurityThreatService",
    "VulnerabilityScannerAdapter",
    "CodexSecuritySummarizer",
    "ThreatReportService",
]

SECURITY_THREAT_TABLES = [
    "cognix_security_threats",
    "cognix_security_reports",
    "cognix_vulnerability_findings",
    "cognix_security_remediation_tasks",
    "cognix_security_events",
    "cognix_audit_logs",
]

RISK_SCORING_SERVICES = [
    "RiskScoringService",
    "RiskFeatureExtractor",
    "RiskRecommendationService",
]

RISK_SCORING_TABLES = [
    "risk_scores",
    "risk_events",
    "risk_recommendations",
]

SYSTEM_HEALTH_SERVICES = [
    "SystemHealthService",
    "WorkerMonitor",
    "RuntimeHealthChecker",
]

SYSTEM_HEALTH_TABLES = [
    "system_health_snapshots",
    "service_health_events",
]

SECURITY_THREAT_CATEGORIES = [
    {
        "id": "vulnerabilities_detected",
        "label": "Vulnerabilities detected",
        "description": "Security signatures, risky routes, and vulnerability findings.",
    },
    {
        "id": "risky_dependencies",
        "label": "Risky dependencies",
        "description": "Packages, runtimes, or model dependencies that need review.",
    },
    {
        "id": "permission_errors",
        "label": "Permission errors",
        "description": "Missing, denied, revoked, or conflicting permission decisions.",
    },
    {
        "id": "access_denied",
        "label": "Access denied attempts",
        "description": "Forbidden or blocked access attempts across CogniX.",
    },
    {
        "id": "user_anomalies",
        "label": "User anomalies",
        "description": "Bans, reports, and unusual user behavior that needs admin review.",
    },
    {
        "id": "codex_incidents",
        "label": "Codex incidents",
        "description": "Codex tool, agent, sandbox, or automation incidents.",
    },
    {
        "id": "configuration_issues",
        "label": "Configuration issues",
        "description": "Misconfiguration signals from runtime, auth, HTTPS, and providers.",
    },
    {
        "id": "exposed_secrets",
        "label": "Exposed secrets",
        "description": "Tokens, keys, env files, and credential exposure signals.",
    },
    {
        "id": "cloud_risks",
        "label": "Cloud risks",
        "description": "Colab, Kaggle, provider, and remote execution security risks.",
    },
]


def build_system_health_blueprint() -> dict[str, Any]:
    return {
        "healthVersion": COGNIX_SYSTEM_HEALTH_VERSION,
        "workerMonitorVersion": COGNIX_WORKER_MONITOR_VERSION,
        "runtimeHealthCheckerVersion": COGNIX_RUNTIME_HEALTH_CHECKER_VERSION,
        "mode": "native_admin_live_system_health",
        "services": SYSTEM_HEALTH_SERVICES,
        "tables": SYSTEM_HEALTH_TABLES,
        "metrics": [
            "cpu",
            "ram",
            "gpu",
            "vram",
            "queue_jobs",
            "average_latency",
            "model_errors",
            "worker_status",
            "storage",
            "active_services",
        ],
        "ui": {
            "statuses": ["green", "yellow", "red"],
            "panels": ["admin-dashboard", "admin-system-health"],
            "history": True,
            "alerts": True,
        },
        "sideEffects": {
            "databaseWrite": False,
            "snapshotWrite": False,
            "serviceEventWrite": False,
            "auditWrite": False,
            "networkCall": False,
            "workerMutation": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }

VULNERABILITY_SCANNER_SOURCES = [
    {
        "id": "python_dependencies",
        "label": "Python dependencies",
        "manifestPatterns": ["requirements*.txt", "pyproject.toml", "uv.lock"],
        "findingSource": "pip",
    },
    {
        "id": "node_dependencies",
        "label": "Node dependencies",
        "manifestPatterns": ["package.json", "package-lock.json", "pnpm-lock.yaml"],
        "findingSource": "npm",
    },
    {
        "id": "model_runtime_dependencies",
        "label": "Model runtime dependencies",
        "manifestPatterns": ["llama.cpp", "ollama", "vllm", "transformers"],
        "findingSource": "runtime",
    },
    {
        "id": "cloud_training_dependencies",
        "label": "Cloud training dependencies",
        "manifestPatterns": ["colab", "kaggle", "cloud_gpu"],
        "findingSource": "cloud_training",
    },
]


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


def _text_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            parts.extend(_text_blob(key, item) for key, item in value.items())
            continue
        if isinstance(value, list):
            parts.extend(_text_blob(item) for item in value)
            continue
        parts.append(str(value))
    return " ".join(item for item in parts if item).lower()


def _category_definitions() -> dict[str, dict[str, Any]]:
    return {item["id"]: dict(item) for item in SECURITY_THREAT_CATEGORIES}


def _new_category_state(category: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": category["id"],
        "label": category["label"],
        "description": category["description"],
        "count": 0,
        "severity": "low",
        "status": "clear",
        "items": [],
    }


def _normalize_status(value: Any, fallback: str = "open") -> str:
    normalized = _norm(value, fallback).lower()
    if normalized in IGNORED_STATUSES:
        return "ignored"
    if normalized in RESOLVED_STATUSES:
        return "resolved"
    if normalized in {"pending_admin_review", "pending", "active", "permanent"}:
        return "active"
    if normalized in {"in_review", "review"}:
        return "in_review"
    return normalized if normalized else fallback


def _category_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "clear"
    statuses = {_normalize_status(item.get("status")) for item in items}
    if statuses <= {"ignored"}:
        return "ignored"
    if statuses <= {"resolved"}:
        return "resolved"
    if "active" in statuses:
        return "active"
    if "in_review" in statuses:
        return "in_review"
    return "open"


def _files_from_item(item: dict[str, Any]) -> list[str]:
    files = item.get("filesAffected") or item.get("files") or item.get("files_json") or item.get("filesJson") or []
    if isinstance(files, list):
        return [str(file) for file in files if str(file).strip()]
    if isinstance(files, str) and files.strip() and files.strip() != "[]":
        return [files.strip()]
    return []


def _solution_for_category(category_id: str, severity: str) -> str:
    if category_id == "risky_dependencies":
        return "Pin or upgrade the dependency, verify compatibility, then mark the finding resolved."
    if category_id == "permission_errors":
        return "Review the permission decision, align role overrides, and keep an audit trail."
    if category_id == "access_denied":
        return "Correlate denied attempts with auth logs, rate limits, and active bans."
    if category_id == "user_anomalies":
        return "Review user history, reports, and bans before reactivation or escalation."
    if category_id == "codex_incidents":
        return "Inspect the Codex action, sandbox context, and requested tool permissions."
    if category_id == "configuration_issues":
        return "Fix the configuration drift and verify HTTPS, auth, and provider settings."
    if category_id == "exposed_secrets":
        return "Rotate exposed credentials, remove them from storage, and audit recent access."
    if category_id == "cloud_risks":
        return "Confirm the cloud target, data sensitivity, and provider permissions before execution."
    if severity in {"critical", "high"}:
        return "Review immediately, preserve evidence, and apply the recommended remediation."
    return "Track the finding and close it once evidence confirms the risk is gone."


def _impact_for_category(category_id: str, severity: str) -> str:
    if category_id == "risky_dependencies":
        return "A vulnerable dependency can expose the runtime or training workflow."
    if category_id == "permission_errors":
        return "A permission mismatch can grant or block sensitive CogniX actions incorrectly."
    if category_id == "access_denied":
        return "Repeated denied attempts can indicate credential abuse or route probing."
    if category_id == "user_anomalies":
        return "Unusual user behavior can put projects, chats, or admin workflows at risk."
    if category_id == "codex_incidents":
        return "A Codex incident can affect code execution, tools, or automation safety."
    if category_id == "configuration_issues":
        return "Configuration drift can break authentication, HTTPS, providers, or local safety gates."
    if category_id == "exposed_secrets":
        return "Exposed credentials can allow unauthorized access to local or cloud resources."
    if category_id == "cloud_risks":
        return "Cloud execution can leak data or consume remote resources if policy is wrong."
    if severity == "critical":
        return "Critical security risk that can affect account, data, or runtime integrity."
    return "Security risk that needs admin review and remediation tracking."


def _summarize_signal(signal: dict[str, Any], category: dict[str, Any]) -> dict[str, Any]:
    severity = _severity(signal.get("severity"))
    category_id = _norm(category.get("id"), "vulnerabilities_detected")
    evidence = _norm(signal.get("evidence")) or _norm(signal.get("description")) or "No direct evidence captured."
    return {
        "id": _norm(signal.get("id"), f"{category_id}:summary"),
        "category": category_id,
        "title": _norm(signal.get("title"), category.get("label", "Security threat")),
        "description": _norm(signal.get("description"))
        or f"{category.get('label', 'Security threat')} detected by CogniX security services.",
        "impact": _norm(signal.get("impact")) or _impact_for_category(category_id, severity),
        "severity": severity,
        "filesAffected": _files_from_item(signal),
        "evidence": evidence[:300],
        "recommendedSolution": _norm(signal.get("recommendedSolution"))
        or _norm(signal.get("solution"))
        or _solution_for_category(category_id, severity),
        "status": _normalize_status(signal.get("status")),
        "sourceType": _norm(signal.get("sourceType") or signal.get("source_type"), "security_signal"),
        "sourceId": _norm(signal.get("sourceId") or signal.get("source_id") or signal.get("id")),
        "createdAt": _norm(signal.get("createdAt") or signal.get("created_at")),
    }


def _append_signal(
    categories: dict[str, dict[str, Any]],
    category_id: str,
    signal: dict[str, Any],
) -> None:
    if category_id not in categories:
        category_id = "vulnerabilities_detected"
    category = categories[category_id]
    summary = _summarize_signal(signal, category)
    category["items"].append(summary)
    category["count"] = len(category["items"])
    category["severity"] = _max_severity(category["items"])
    category["status"] = _category_status(category["items"])


def _category_from_security_text(text: str, fallback: str = "vulnerabilities_detected") -> str:
    if any(term in text for term in ("dependency", "package", "pip", "npm", "llama", "runtime")):
        return "risky_dependencies"
    if "permission" in text or "role" in text or "override" in text:
        return "permission_errors"
    if any(term in text for term in ("denied", "forbidden", "unauthorized", "401", "403")):
        return "access_denied"
    if any(term in text for term in ("codex", "sandbox", "agent", "tool")):
        return "codex_incidents"
    if any(term in text for term in ("config", "configuration", "https", "cognix.local", "provider")):
        return "configuration_issues"
    if any(term in text for term in SECRET_EXPOSURE_TERMS):
        return "exposed_secrets"
    if any(term in text for term in ("cloud", "kaggle", "colab", "google colab", "gpu", "provider")):
        return "cloud_risks"
    if any(term in text for term in ("ban", "report", "anomal", "abuse")):
        return "user_anomalies"
    return fallback


def build_security_threats_blueprint() -> dict[str, Any]:
    return {
        "blueprintVersion": COGNIX_SECURITY_THREAT_CENTER_VERSION,
        "mode": "native_read_only",
        "route": "/admin/security-threats",
        "services": SECURITY_THREAT_SERVICES,
        "tables": SECURITY_THREAT_TABLES,
        "categories": SECURITY_THREAT_CATEGORIES,
        "filters": {
            "severity": ["critical", "high", "medium", "low"],
            "status": SECURITY_THREAT_STATUSES,
        },
        "codexSummaryFields": [
            "title",
            "description",
            "impact",
            "severity",
            "filesAffected",
            "evidence",
            "recommendedSolution",
            "status",
        ],
        "sideEffects": {
            "databaseWrite": False,
            "externalScan": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_vulnerability_scanner_adapter_contract() -> dict[str, Any]:
    return {
        "contractVersion": COGNIX_VULNERABILITY_SCANNER_ADAPTER_VERSION,
        "mode": "vulnerability_scanner_adapter_read_only",
        "sourceOfTruth": "security_center_adapter_contract",
        "supportedSources": [dict(item) for item in VULNERABILITY_SCANNER_SOURCES],
        "findingTables": [
            "cognix_vulnerability_findings",
            "cognix_security_reports",
            "cognix_security_remediation_tasks",
            "cognix_audit_logs",
        ],
        "scanPolicy": {
            "externalScannerExecutionAllowedHere": False,
            "networkVulnerabilityLookupAllowedHere": False,
            "manifestReadAllowed": True,
            "rawManifestContentReturned": False,
            "secretValueReturned": False,
            "findingWriteAllowedHere": False,
            "remediationTaskWriteAllowedHere": False,
            "adminReviewRequired": True,
        },
        "redactionPolicy": {
            "rawSecretsReturned": False,
            "tokensRedacted": True,
            "envFileContentReturned": False,
            "evidenceIsSummaryOnly": True,
        },
        "sideEffects": {
            "manifestRead": False,
            "databaseWrite": False,
            "externalScan": False,
            "networkCall": False,
            "subprocess": False,
            "secretRead": False,
            "findingWrite": False,
            "remediationWrite": False,
            "auditWrite": False,
        },
    }


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


def build_security_threat_center(
    *,
    security_events: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    security_threats: list[dict[str, Any]] | None = None,
    security_reports: list[dict[str, Any]] | None = None,
    vulnerability_findings: list[dict[str, Any]] | None = None,
    remediation_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    definitions = _category_definitions()
    categories = {
        category_id: _new_category_state(category)
        for category_id, category in definitions.items()
    }

    for event in security_events:
        event_category = _norm(event.get("category"), "security_event").lower()
        text = _text_blob(event)
        category_id = "vulnerabilities_detected"
        if event_category == "ssrf" or "cloud" in text:
            category_id = "cloud_risks"
        if any(term in text for term in SECRET_EXPOSURE_TERMS):
            _append_signal(
                categories,
                "exposed_secrets",
                {
                    **_threat_from_event(event),
                    "title": "Possible secret exposure",
                    "sourceType": "security_event",
                },
            )
        _append_signal(categories, category_id, _threat_from_event(event))

    for audit in audit_logs:
        action = _norm(audit.get("action")).lower()
        resource_type = _norm(audit.get("resource_type") or audit.get("resourceType")).lower()
        metadata = audit.get("metadata") or audit.get("metadata_json") or audit.get("metadataJson")
        text = _text_blob(action, resource_type, audit.get("resource_id"), audit.get("severity"), metadata)
        category_id = ""
        if "codex" in action or resource_type in {"codex", "agent", "tool"}:
            category_id = "codex_incidents"
        elif "permission" in text and any(term in text for term in ("denied", "missing", "revoked", "failed", "error")):
            category_id = "permission_errors"
        elif any(term in text for term in ("access_denied", "denied", "forbidden", "unauthorized", "401", "403")):
            category_id = "access_denied"
        elif any(term in text for term in SECRET_EXPOSURE_TERMS):
            category_id = "exposed_secrets"
        elif any(term in text for term in ("config", "https", "cognix.local", "provider")):
            category_id = "configuration_issues"
        elif any(term in text for term in ("cloud", "kaggle", "colab", "remote_gpu")):
            category_id = "cloud_risks"

        if category_id:
            severity = "high" if _norm(audit.get("severity")) == "critical" else "medium"
            if category_id in {"exposed_secrets", "codex_incidents"} and _norm(audit.get("severity")) == "warning":
                severity = "high"
            _append_signal(
                categories,
                category_id,
                {
                    "id": _norm(audit.get("id"), "audit"),
                    "title": _norm(audit.get("action"), "Audit security signal").replace("_", " ").title(),
                    "description": f"Audit log signal for {_norm(audit.get('username') or audit.get('actor_username'), 'system')}.",
                    "severity": severity,
                    "evidence": _text_blob(audit.get("action"), audit.get("resource_type"), audit.get("resource_id"))[:300],
                    "status": "open",
                    "sourceType": "audit_log",
                    "sourceId": _norm(audit.get("id")),
                    "createdAt": _norm(audit.get("created_at") or audit.get("createdAt")),
                },
            )

    for ban in bans:
        if _norm(ban.get("status")).lower() in ACTIVE_BAN_STATUSES:
            _append_signal(
                categories,
                "user_anomalies",
                {
                    "id": f"ban:{_norm(ban.get('id'), 'unknown')}",
                    "title": "Active user ban",
                    "description": f"User anomaly under admin review for {_norm(ban.get('username') or ban.get('client_key'), 'unknown')}.",
                    "severity": "critical" if _norm(ban.get("status")) == "permanent" else "high",
                    "evidence": _norm(ban.get("reason"), "ban record"),
                    "status": _normalize_status(ban.get("status")),
                    "sourceType": "ban",
                    "sourceId": _norm(ban.get("id")),
                    "createdAt": _norm(ban.get("created_at") or ban.get("createdAt")),
                },
            )

    for report in reports:
        text = _text_blob(report.get("category"), report.get("title"), report.get("message"), report.get("status"))
        if not any(term in text for term in ("security", "cloud", "secret", "permission", "codex", "config", "abuse", "anomal")):
            continue
        category_id = _category_from_security_text(text, fallback = "user_anomalies")
        _append_signal(
            categories,
            category_id,
            {
                "id": _norm(report.get("id"), "report"),
                "title": _norm(report.get("title"), "Security report"),
                "description": _norm(report.get("message"), "User report requires review."),
                "severity": "high" if category_id in {"exposed_secrets", "cloud_risks"} else "medium",
                "evidence": _norm(report.get("message") or report.get("title"), "report"),
                "status": _normalize_status(report.get("status")),
                "sourceType": "report",
                "sourceId": _norm(report.get("id")),
                "createdAt": _norm(report.get("created_at") or report.get("createdAt")),
            },
        )

    for threat in security_threats or []:
        text = _text_blob(threat)
        category_id = _norm(threat.get("category"))
        if category_id not in definitions:
            category_id = _category_from_security_text(text)
        _append_signal(
            categories,
            category_id,
            {
                "id": _norm(threat.get("id"), "threat"),
                "title": _norm(threat.get("title"), "Security threat"),
                "description": _norm(threat.get("summary") or threat.get("description"), "Persisted security threat."),
                "severity": _severity(threat.get("severity")),
                "filesAffected": _files_from_item(threat),
                "evidence": _norm(threat.get("evidence") or threat.get("evidence_json") or text, "persisted threat"),
                "recommendedSolution": _norm(threat.get("recommended_solution") or threat.get("recommendedSolution")),
                "status": _normalize_status(threat.get("status")),
                "sourceType": _norm(threat.get("source_type") or threat.get("sourceType"), "security_threat"),
                "sourceId": _norm(threat.get("source_id") or threat.get("sourceId") or threat.get("id")),
                "createdAt": _norm(threat.get("created_at") or threat.get("createdAt")),
            },
        )

    for finding in vulnerability_findings or []:
        package_name = _norm(finding.get("package_name") or finding.get("packageName") or finding.get("source_name"))
        version = _norm(finding.get("installed_version") or finding.get("installedVersion"))
        fixed = _norm(finding.get("fixed_version") or finding.get("fixedVersion"))
        evidence = f"{package_name} {version}".strip()
        if fixed:
            evidence = f"{evidence} -> fixed in {fixed}".strip()
        _append_signal(
            categories,
            "risky_dependencies",
            {
                "id": _norm(finding.get("id"), "finding"),
                "title": _norm(finding.get("title"), package_name or "Risky dependency"),
                "description": _norm(finding.get("description"), "Dependency finding from the native scanner adapter."),
                "severity": _severity(finding.get("severity")),
                "evidence": evidence or _norm(finding.get("evidence") or finding.get("evidence_json"), "dependency finding"),
                "status": _normalize_status(finding.get("status")),
                "sourceType": "vulnerability_finding",
                "sourceId": _norm(finding.get("id")),
                "createdAt": _norm(finding.get("created_at") or finding.get("createdAt")),
            },
        )

    incident_categories = list(categories.values())
    codex_summaries = [
        item
        for category in incident_categories
        for item in category["items"]
    ]
    codex_summaries.sort(
        key = lambda item: (
            _severity_rank(item.get("severity")),
            _norm(item.get("createdAt")),
            _norm(item.get("title")),
        ),
        reverse = True,
    )

    severity_counts = {key: 0 for key in ("critical", "high", "medium", "low")}
    status_counts = {key: 0 for key in (*SECURITY_THREAT_STATUSES, "clear")}
    for item in codex_summaries:
        severity_counts[_severity(item.get("severity"))] += 1
        status = _normalize_status(item.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    for category in incident_categories:
        if not category["items"]:
            status_counts["clear"] = status_counts.get("clear", 0) + 1

    overall_status = "green"
    if severity_counts["critical"]:
        overall_status = "red"
    elif severity_counts["high"]:
        overall_status = "yellow"

    return {
        "centerVersion": COGNIX_SECURITY_THREAT_CENTER_VERSION,
        "scannerAdapterVersion": COGNIX_VULNERABILITY_SCANNER_ADAPTER_VERSION,
        "mode": "native_read_only",
        "services": SECURITY_THREAT_SERVICES,
        "tables": SECURITY_THREAT_TABLES,
        "summary": {
            "status": overall_status,
            "totalSignals": len(codex_summaries),
            "categories": len(incident_categories),
            "critical": severity_counts["critical"],
            "high": severity_counts["high"],
            "medium": severity_counts["medium"],
            "low": severity_counts["low"],
            "resolved": status_counts.get("resolved", 0),
            "ignored": status_counts.get("ignored", 0),
            "open": status_counts.get("open", 0) + status_counts.get("active", 0) + status_counts.get("in_review", 0),
            "cloudRisks": categories["cloud_risks"]["count"],
            "codexIncidents": categories["codex_incidents"]["count"],
            "permissionErrors": categories["permission_errors"]["count"],
            "exposedSecrets": categories["exposed_secrets"]["count"],
            "statusCounts": status_counts,
        },
        "incidentCategories": incident_categories,
        "codexSummaries": codex_summaries,
        "securityThreats": security_threats or [],
        "securityReports": security_reports or [],
        "vulnerabilityFindings": vulnerability_findings or [],
        "remediationTasks": remediation_tasks or [],
        "sideEffects": {
            "databaseWrite": False,
            "externalScan": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
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
        "featureExtractorVersion": COGNIX_RISK_FEATURE_EXTRACTOR_VERSION,
        "recommendationServiceVersion": COGNIX_RISK_RECOMMENDATION_SERVICE_VERSION,
        "mode": "native_read_only",
        "services": RISK_SCORING_SERVICES,
        "tables": RISK_SCORING_TABLES,
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


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _status_from_ratio(value: float, *, yellow: float, red: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        return "red" if value >= red else "yellow" if value >= yellow else "green"
    return "red" if value <= red else "yellow" if value <= yellow else "green"


def _worker_monitor(background_jobs: list[dict[str, Any]] | None) -> dict[str, Any]:
    jobs = list(background_jobs or [])
    queued = sum(1 for item in jobs if _norm(item.get("status")).lower() in {"queued", "planned", "pending"})
    running = sum(1 for item in jobs if _norm(item.get("status")).lower() in {"running", "active", "in_progress"})
    failed = sum(1 for item in jobs if _norm(item.get("status")).lower() in {"failed", "error"})
    status = "red" if failed else "yellow" if queued > 10 or running > 5 else "green"
    return {
        "workerMonitorVersion": COGNIX_WORKER_MONITOR_VERSION,
        "status": status,
        "queueJobs": queued,
        "runningJobs": running,
        "failedJobs": failed,
        "totalJobsObserved": len(jobs),
    }


def _latency_metrics(
    token_events: list[dict[str, Any]] | None,
    router_logs: list[dict[str, Any]] | None,
    orchestrator_logs: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    latencies: list[float] = []
    for event in token_events or []:
        latency = event.get("latencyMs") or event.get("latency_ms") or event.get("averageLatencyMs") or event.get("average_latency_ms")
        if isinstance(latency, (int, float)) and float(latency) > 0:
            latencies.append(float(latency))
    router_errors = sum(1 for item in router_logs or [] if _norm(item.get("status")).lower() in {"error", "failed"})
    orchestrator_errors = sum(1 for item in orchestrator_logs or [] if _norm(item.get("status")).lower() in {"error", "failed"})
    average_latency = _avg(latencies)
    status = "red" if average_latency >= 15000 or router_errors + orchestrator_errors >= 5 else "yellow" if average_latency >= 5000 else "green"
    return {
        "averageLatencyMs": average_latency,
        "sampleCount": len(latencies),
        "routerErrors": router_errors,
        "orchestratorErrors": orchestrator_errors,
        "modelErrors": router_errors + orchestrator_errors,
        "status": status,
    }


def _storage_metrics(storage: dict[str, Any] | None) -> dict[str, Any]:
    record = _as_dict(storage)
    total_gb = float(record.get("totalGb") or 0.0)
    free_gb = float(record.get("freeGb") or record.get("availableGb") or 0.0)
    used_percent = float(record.get("usedPercent") or 0.0)
    if total_gb > 0 and used_percent <= 0:
        used_percent = round(((total_gb - free_gb) / total_gb) * 100, 2)
    status = _status_from_ratio(used_percent, yellow = 80, red = 92)
    return {
        "totalGb": total_gb,
        "freeGb": free_gb,
        "usedPercent": used_percent,
        "status": status,
    }


def _vram_metrics(gpu: dict[str, Any]) -> dict[str, Any]:
    devices = gpu.get("devices") or []
    total = 0.0
    free = 0.0
    for device in devices:
        item = _as_dict(device)
        total += float(item.get("totalVramGb") or item.get("vramTotalGb") or item.get("memoryTotalGb") or item.get("totalGb") or 0.0)
        free += float(item.get("freeVramGb") or item.get("vramFreeGb") or item.get("memoryFreeGb") or item.get("freeGb") or 0.0)
    used_percent = round(((total - free) / total) * 100, 2) if total > 0 else 0.0
    return {
        "totalGb": round(total, 2),
        "freeGb": round(free, 2),
        "usedPercent": used_percent,
        "status": _status_from_ratio(used_percent, yellow = 80, red = 92) if total > 0 else "green",
    }


def build_system_health(
    *,
    hardware: dict[str, Any],
    security_report: dict[str, Any],
    risk_scoring: dict[str, Any],
    audit_logs: list[dict[str, Any]],
    background_jobs: list[dict[str, Any]] | None = None,
    token_events: list[dict[str, Any]] | None = None,
    router_logs: list[dict[str, Any]] | None = None,
    orchestrator_logs: list[dict[str, Any]] | None = None,
    service_events: list[dict[str, Any]] | None = None,
    storage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    gpu = _as_dict(hardware.get("gpu"))
    total_gb = float(memory.get("totalGb") or 0.0)
    available_gb = float(memory.get("availableGb") or 0.0)
    used_memory_percent = round(((total_gb - available_gb) / total_gb) * 100, 2) if total_gb > 0 else 0.0
    memory_pressure = "unknown"
    if total_gb > 0:
        ratio = available_gb / total_gb
        memory_pressure = "red" if ratio < 0.10 else "yellow" if ratio < 0.25 else "green"
    worker_monitor = _worker_monitor(background_jobs)
    latency = _latency_metrics(token_events, router_logs, orchestrator_logs)
    storage_metrics = _storage_metrics(storage)
    vram = _vram_metrics(gpu)
    persisted_service_events = list(service_events or [])

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
        {
            "id": "workers",
            "label": "Workers",
            "status": worker_monitor["status"],
            "detail": (
                f"{worker_monitor['runningJobs']} running, "
                f"{worker_monitor['queueJobs']} queued, {worker_monitor['failedJobs']} failed."
            ),
        },
        {
            "id": "runtime-latency",
            "label": "Runtime latency",
            "status": latency["status"],
            "detail": f"{latency['averageLatencyMs']}ms average latency across {latency['sampleCount']} sample(s).",
        },
        {
            "id": "storage",
            "label": "Storage",
            "status": storage_metrics["status"],
            "detail": f"{storage_metrics['freeGb']:.1f}GB free; {storage_metrics['usedPercent']:.1f}% used.",
        },
        {
            "id": "vram",
            "label": "VRAM",
            "status": vram["status"],
            "detail": f"{vram['freeGb']:.1f}GB free / {vram['totalGb']:.1f}GB total.",
        },
    ]
    services.extend(
        {
            "id": str(event.get("serviceId") or event.get("service_id") or event.get("id") or "service"),
            "label": str(event.get("serviceLabel") or event.get("service_label") or event.get("service") or "Service"),
            "status": str(event.get("status") or "green"),
            "detail": str(event.get("message") or event.get("detail") or ""),
        }
        for event in persisted_service_events[:20]
    )

    overall = "green"
    if any(item["status"] == "red" for item in services):
        overall = "red"
    elif any(item["status"] == "yellow" for item in services):
        overall = "yellow"

    return {
        "healthVersion": COGNIX_SYSTEM_HEALTH_VERSION,
        "workerMonitorVersion": COGNIX_WORKER_MONITOR_VERSION,
        "runtimeHealthCheckerVersion": COGNIX_RUNTIME_HEALTH_CHECKER_VERSION,
        "mode": "native_live_system_health",
        "servicesDeclared": SYSTEM_HEALTH_SERVICES,
        "tables": SYSTEM_HEALTH_TABLES,
        "overallStatus": overall,
        "metrics": {
            "cpu": {"count": hardware.get("cpuCount"), "backend": hardware.get("deviceBackend")},
            "memory": {
                "totalGb": total_gb,
                "availableGb": available_gb,
                "usedPercent": used_memory_percent,
                "pressure": memory_pressure,
            },
            "gpu": {
                "available": bool(gpu.get("available")),
                "deviceCount": len(gpu.get("devices") or []),
                "devices": gpu.get("devices") or [],
            },
            "vram": vram,
            "queue": worker_monitor,
            "latency": latency,
            "modelErrors": {"count": latency["modelErrors"]},
            "workers": worker_monitor,
            "storage": storage_metrics,
            "activeServices": {
                "count": len([item for item in services if item["status"] in {"green", "yellow"}]),
                "services": [item["id"] for item in services],
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
            "snapshotWrite": False,
            "serviceEventWrite": False,
            "auditWrite": False,
            "networkCall": False,
            "workerMutation": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }
