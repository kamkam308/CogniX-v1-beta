# SPDX-License-Identifier: AGPL-3.0-only

"""CogniX native admin approval queue and policy planning."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


COGNIX_APPROVAL_SERVICE_VERSION = "cognix_approval_service_v1"
COGNIX_APPROVAL_QUEUE_VERSION = "cognix_approval_queue_v1"
COGNIX_APPROVAL_POLICY_VERSION = "cognix_approval_policy_engine_v1"

APPROVAL_REQUEST_TYPES: list[dict[str, Any]] = [
    {
        "requestType": "developer_mode",
        "label": "Developer mode",
        "category": "developer",
        "riskLevel": "critical",
        "actionAfterApproval": "grant_developer_mode",
    },
    {
        "requestType": "models:install:heavy",
        "label": "Installer un modele lourd",
        "category": "models",
        "riskLevel": "high",
        "actionAfterApproval": "allow_model_install_plan",
    },
    {
        "requestType": "models:run:cloud",
        "label": "Utiliser un modele cloud",
        "category": "models",
        "riskLevel": "high",
        "actionAfterApproval": "allow_cloud_model_plan",
    },
    {
        "requestType": "limits:tokens:increase",
        "label": "Augmenter limite tokens",
        "category": "limits",
        "riskLevel": "medium",
        "actionAfterApproval": "allow_quota_change",
    },
    {
        "requestType": "apps:connect",
        "label": "Connecter une app",
        "category": "integrations",
        "riskLevel": "medium",
        "actionAfterApproval": "allow_app_connection",
    },
    {
        "requestType": "projects:share",
        "label": "Partager un projet",
        "category": "projects",
        "riskLevel": "medium",
        "actionAfterApproval": "allow_project_share",
    },
    {
        "requestType": "tools:execute:sensitive",
        "label": "Executer un outil sensible",
        "category": "tools",
        "riskLevel": "critical",
        "actionAfterApproval": "allow_sensitive_tool_plan",
    },
    {
        "requestType": "cowork:control",
        "label": "Utiliser Cowork",
        "category": "cowork",
        "riskLevel": "high",
        "actionAfterApproval": "allow_cowork_control",
    },
    {
        "requestType": "codex:run",
        "label": "Utiliser Codex",
        "category": "codex",
        "riskLevel": "critical",
        "actionAfterApproval": "allow_codex_run",
    },
    {
        "requestType": "documents:restricted:read",
        "label": "Acceder a un document restreint",
        "category": "documents",
        "riskLevel": "high",
        "actionAfterApproval": "allow_restricted_document_read",
    },
    {
        "requestType": "scheduled:task:sensitive",
        "label": "Creer une tache planifiee sensible",
        "category": "scheduled",
        "riskLevel": "high",
        "actionAfterApproval": "allow_sensitive_schedule",
    },
]

RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _key(value: Any, fallback: str = "") -> str:
    return _norm(value, fallback).lower()


def _request_type(row: dict[str, Any]) -> str:
    return _key(row.get("request_type") or row.get("requestType"))


def _status(row: dict[str, Any]) -> str:
    status = _key(row.get("status"), "pending")
    return status if status in {"pending", "approved", "denied"} else "pending"


def _risk(row: dict[str, Any], fallback: str = "medium") -> str:
    risk = _key(row.get("risk_level") or row.get("riskLevel"), fallback)
    return risk if risk in RISK_RANK else fallback


def _catalog_map() -> dict[str, dict[str, Any]]:
    return {item["requestType"]: dict(item) for item in APPROVAL_REQUEST_TYPES}


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_minutes(created_at: Any) -> int:
    created = _parse_time(created_at)
    if created is None:
        return 0
    if created.tzinfo is None:
        created = created.replace(tzinfo = timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - created).total_seconds() // 60))


def build_approvals_blueprint() -> dict[str, Any]:
    return {
        "approvalServiceVersion": COGNIX_APPROVAL_SERVICE_VERSION,
        "approvalQueueVersion": COGNIX_APPROVAL_QUEUE_VERSION,
        "approvalPolicyVersion": COGNIX_APPROVAL_POLICY_VERSION,
        "mode": "native_admin_approval_pipeline",
        "services": ["ApprovalService", "ApprovalQueue", "ApprovalPolicyEngine"],
        "tables": [
            "approval_requests",
            "approval_decisions",
            "approval_comments",
            "cognix_approval_requests",
            "cognix_approval_decisions",
            "cognix_approval_comments",
        ],
        "pipeline": [
            "user_request",
            "approval_request_service",
            "admin_queue",
            "approve_or_deny",
            "action_execution_or_refusal",
            "audit_log",
        ],
        "requestTypes": APPROVAL_REQUEST_TYPES,
        "sideEffects": {
            "requestWrite": False,
            "decisionWrite": False,
            "commentWrite": False,
            "legacyPermissionWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def classify_request_type(request_type: str, explicit_risk: str | None = None) -> dict[str, Any]:
    catalog = _catalog_map()
    normalized = _key(request_type)
    item = dict(catalog.get(normalized) or {})
    if not item:
        category = normalized.split(":", 1)[0] if ":" in normalized else "general"
        item = {
            "requestType": normalized,
            "label": normalized or "approval request",
            "category": category,
            "riskLevel": "medium",
            "actionAfterApproval": "manual_review",
        }
    if explicit_risk:
        item["riskLevel"] = _risk({"riskLevel": explicit_risk}, item["riskLevel"])
    return item


def build_policy_decision(
    *,
    request_type: str,
    requester_role: str = "user",
    risk_level: str | None = None,
    has_permission: bool = False,
) -> dict[str, Any]:
    request_meta = classify_request_type(request_type, risk_level)
    risk = request_meta["riskLevel"]
    role = _key(requester_role, "user")
    requires_approval = not has_permission and role != "admin"
    if risk in {"high", "critical"}:
        requires_approval = role != "admin"
    return {
        "approvalPolicyVersion": COGNIX_APPROVAL_POLICY_VERSION,
        "requestType": request_meta["requestType"],
        "category": request_meta["category"],
        "riskLevel": risk,
        "requiresApproval": requires_approval,
        "recommendedQueue": "admin" if requires_approval else "auto_allowed",
        "recommendedAction": "queue_for_admin" if requires_approval else "execute_with_audit",
        "sideEffects": build_approvals_blueprint()["sideEffects"],
    }


def _latest_decisions(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in sorted(decisions, key = lambda row: _norm(row.get("created_at") or row.get("createdAt"))):
        request_id = _norm(item.get("request_id") or item.get("requestId"))
        if request_id:
            latest[request_id] = item
    return latest


def _comments_by_request(comments: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in comments:
        request_id = _norm(item.get("request_id") or item.get("requestId"))
        if request_id:
            grouped.setdefault(request_id, []).append(item)
    return grouped


def build_approval_queue(
    *,
    requests: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    comments: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = _latest_decisions(decisions)
    grouped_comments = _comments_by_request(comments)
    queue_items: list[dict[str, Any]] = []
    summary = {"pending": 0, "approved": 0, "denied": 0, "critical": 0, "high": 0}

    for request in requests:
        request_id = _norm(request.get("id"))
        request_type = _request_type(request)
        meta = classify_request_type(request_type, request.get("risk_level") or request.get("riskLevel"))
        risk = meta["riskLevel"]
        status = _status(request)
        if status in summary:
            summary[status] += 1
        if risk in {"critical", "high"}:
            summary[risk] += 1
        item_comments = grouped_comments.get(request_id, [])
        latest_decision = latest.get(request_id)
        queue_items.append(
            {
                "id": request_id,
                "requester": _norm(request.get("username")),
                "requestType": request_type,
                "typeLabel": _norm(request.get("title"), meta["label"]),
                "category": meta["category"],
                "riskLevel": risk,
                "status": status,
                "date": request.get("created_at") or request.get("createdAt"),
                "ageMinutes": _age_minutes(request.get("created_at") or request.get("createdAt")),
                "justification": _norm(request.get("reason")),
                "resource": {
                    "type": _norm(request.get("resource_type") or request.get("resourceType")),
                    "id": _norm(request.get("resource_id") or request.get("resourceId")),
                },
                "latestDecision": latest_decision,
                "comments": item_comments,
                "commentCount": len(item_comments),
                "actionAfterApproval": meta["actionAfterApproval"],
                "recommendedAction": "review_now" if status == "pending" and risk in {"high", "critical"} else "review",
            }
        )

    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    queue_items.sort(key = lambda item: (item["status"] != "pending", risk_order.get(item["riskLevel"], 9), -item["ageMinutes"]))
    return {
        "approvalServiceVersion": COGNIX_APPROVAL_SERVICE_VERSION,
        "approvalQueueVersion": COGNIX_APPROVAL_QUEUE_VERSION,
        "approvalPolicyVersion": COGNIX_APPROVAL_POLICY_VERSION,
        "summary": {
            **summary,
            "total": len(queue_items),
        },
        "requests": queue_items,
        "sideEffects": build_approvals_blueprint()["sideEffects"],
    }
