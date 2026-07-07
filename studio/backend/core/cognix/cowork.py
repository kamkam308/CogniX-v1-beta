# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native Cowork Mode planning.

Cowork Mode gives CogniX a visible, project-scoped control contract. This
module only plans sessions and actions: it never executes shell commands, reads
secrets, modifies files, starts servers, or hides activity from the user.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_COWORK_SERVICE_VERSION = "cognix_cowork_service_v1"
COGNIX_REMOTE_CONTROL_POLICY_ENGINE_VERSION = "cognix_remote_control_policy_engine_v1"
COGNIX_COMMAND_ALLOWLIST_VERSION = "cognix_command_allowlist_v1"
COGNIX_ACTION_RECORDER_VERSION = "cognix_action_recorder_v1"
COGNIX_HUMAN_APPROVAL_GATE_VERSION = "cognix_human_approval_gate_v1"

COWORK_SERVICES = [
    "CoworkService",
    "RemoteControlPolicyEngine",
    "CommandAllowlist",
    "ActionRecorder",
    "HumanApprovalGate",
]

COWORK_TABLES = [
    "cowork_sessions",
    "cowork_actions",
    "cowork_permissions",
    "cowork_approvals",
]

COWORK_LEVELS = {
    "read_only",
    "suggest_only",
    "edit_project_files",
    "run_dev_commands",
    "full_dev_project",
}

COWORK_STATUSES = {"active", "paused", "stopped", "pending_approval"}
COWORK_ACTION_TYPES = {"read_file", "suggest_change", "edit_file", "run_command", "pause", "stop"}

DANGEROUS_COMMAND_FRAGMENTS = {
    "rm -rf",
    "sudo ",
    "su ",
    "chmod ",
    "chown ",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "systemctl",
    "service ",
    "passwd",
    "curl ",
    "wget ",
}

HIGH_RISK_FRAGMENTS = {
    "deploy",
    "production",
    "prod",
    "payment",
    "stripe",
    "paypal",
    "email",
    "mail",
    "secret",
    "token",
    "password",
    "api_key",
    "private_key",
    ".env",
}

DEV_COMMAND_ALLOWLIST = {
    "pytest",
    "python -m pytest",
    "npm test",
    "npm run test",
    "npm run typecheck",
    "npm run build",
    "pnpm test",
    "pnpm run test",
    "pnpm run typecheck",
    "pnpm run build",
    "yarn test",
    "yarn build",
    "ruff check",
    "mypy",
    "tsc",
    "git status",
    "git diff",
}

LEVEL_CAPABILITIES = {
    "read_only": ["view_project_files", "inspect_errors", "summarize_state"],
    "suggest_only": ["view_project_files", "inspect_errors", "suggest_changes", "summarize_state"],
    "edit_project_files": [
        "view_project_files",
        "inspect_errors",
        "suggest_changes",
        "plan_project_file_edits",
        "record_file_edit_intent",
    ],
    "run_dev_commands": [
        "view_project_files",
        "inspect_errors",
        "suggest_changes",
        "plan_dev_commands",
        "record_command_intent",
    ],
    "full_dev_project": [
        "view_project_files",
        "inspect_errors",
        "suggest_changes",
        "plan_project_file_edits",
        "plan_dev_commands",
        "record_file_edit_intent",
        "record_command_intent",
    ],
}


def _text(value: Any, limit: int = 240, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).replace("\r\n", "\n").strip()
    return " ".join(text.split())[:limit].strip()


def _multiline(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:limit].strip()


def _key(value: Any, fallback: str = "") -> str:
    text = _text(value, 160, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in text)
    return cleaned.strip("_")[:120] or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:14]}"


def _normalize_level(level: str | None) -> str:
    normalized = _key(level, "suggest_only")
    return normalized if normalized in COWORK_LEVELS else "suggest_only"


def _session_payload(session: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(session.get("payload"))
    if payload:
        return payload
    return session


def _session_level(session: dict[str, Any]) -> str:
    payload = _session_payload(session)
    cowork = _as_dict(payload.get("cowork"))
    return _normalize_level(cowork.get("level") or payload.get("level") or session.get("level"))


def _session_status(session: dict[str, Any]) -> str:
    payload = _session_payload(session)
    cowork = _as_dict(payload.get("cowork"))
    status = _key(cowork.get("status") or payload.get("status") or session.get("status"), "active")
    return status if status in COWORK_STATUSES else "active"


def _capabilities_for_level(level: str) -> list[str]:
    return list(LEVEL_CAPABILITIES.get(_normalize_level(level), LEVEL_CAPABILITIES["suggest_only"]))


def _action_allowed_for_level(level: str, action_type: str) -> bool:
    level = _normalize_level(level)
    action_type = _key(action_type, "")
    if action_type in {"pause", "stop"}:
        return True
    if action_type == "read_file":
        return True
    if action_type == "suggest_change":
        return level in {"suggest_only", "edit_project_files", "run_dev_commands", "full_dev_project"}
    if action_type == "edit_file":
        return level in {"edit_project_files", "full_dev_project"}
    if action_type == "run_command":
        return level in {"run_dev_commands", "full_dev_project"}
    return False


def _path_policy(path: str | None) -> dict[str, Any]:
    normalized = _text(path, 800)
    lowered = normalized.replace("\\", "/").lower()
    reasons: list[str] = []
    if not normalized:
        return {"path": "", "riskLevel": "low", "requiresApproval": False, "blockedReasons": []}
    if lowered.startswith("../") or "/../" in lowered or lowered in {"..", "."}:
        reasons.append("path_traversal")
    if lowered.startswith("~") or lowered.startswith("/etc") or lowered.startswith("/var") or lowered.startswith("/usr") or lowered.startswith("/boot"):
        reasons.append("system_path")
    if lowered.startswith("/") and "/bureau/ebk/" not in lowered and "/cognix" not in lowered:
        reasons.append("outside_project_path")
    if any(fragment in lowered for fragment in HIGH_RISK_FRAGMENTS):
        reasons.append("sensitive_path")
    return {
        "path": normalized,
        "riskLevel": "high" if reasons else "low",
        "requiresApproval": bool(reasons),
        "blockedReasons": reasons,
    }


def _command_policy(command: str | None) -> dict[str, Any]:
    normalized = _text(command, 1200)
    lowered = normalized.lower()
    blocked_reasons: list[str] = []
    approval_reasons: list[str] = []
    if not normalized:
        return {
            "command": "",
            "riskLevel": "low",
            "allowlistMatch": False,
            "requiresApproval": False,
            "blockedReasons": ["command_required"],
        }
    for fragment in DANGEROUS_COMMAND_FRAGMENTS:
        if fragment in lowered:
            blocked_reasons.append(f"dangerous_command:{fragment.strip()}")
    for fragment in HIGH_RISK_FRAGMENTS:
        if fragment in lowered:
            approval_reasons.append(f"high_risk_context:{fragment}")
    allowlist_match = any(lowered == item or lowered.startswith(item + " ") for item in DEV_COMMAND_ALLOWLIST)
    if not allowlist_match:
        approval_reasons.append("not_in_command_allowlist")
    risk = "critical" if blocked_reasons else ("high" if approval_reasons else "low")
    return {
        "command": normalized,
        "riskLevel": risk,
        "allowlistMatch": allowlist_match,
        "requiresApproval": bool(approval_reasons or blocked_reasons),
        "blockedReasons": blocked_reasons,
        "approvalReasons": approval_reasons,
    }


def build_cowork_blueprint() -> dict[str, Any]:
    return {
        "coworkServiceVersion": COGNIX_COWORK_SERVICE_VERSION,
        "remoteControlPolicyEngineVersion": COGNIX_REMOTE_CONTROL_POLICY_ENGINE_VERSION,
        "commandAllowlistVersion": COGNIX_COMMAND_ALLOWLIST_VERSION,
        "actionRecorderVersion": COGNIX_ACTION_RECORDER_VERSION,
        "humanApprovalGateVersion": COGNIX_HUMAN_APPROVAL_GATE_VERSION,
        "mode": "native_cowork_contract",
        "services": COWORK_SERVICES,
        "tables": COWORK_TABLES,
        "levels": sorted(COWORK_LEVELS),
        "actions": sorted(COWORK_ACTION_TYPES),
        "commandAllowlist": sorted(DEV_COMMAND_ALLOWLIST),
        "visibleControls": [
            "active_mode_indicator",
            "pause_button",
            "stop_button",
            "action_history",
            "current_action",
            "last_modified_file",
            "last_command",
        ],
        "securityPolicy": {
            "neverStealth": True,
            "projectBoundaryRequired": True,
            "humanApprovalForHighRiskActions": True,
            "commandAllowlistRequired": True,
            "secretsAccessForbidden": True,
            "paymentEmailDeploySystemActionsForbiddenWithoutApproval": True,
            "directExecutionAllowed": False,
            "frontendDirectToolExecutionAllowed": False,
        },
        "sideEffects": {
            "sessionWrite": False,
            "actionWrite": False,
            "permissionWrite": False,
            "approvalWrite": False,
            "auditWrite": False,
            "commandExecution": False,
            "fileWrite": False,
            "secretRead": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_cowork_session_plan(
    *,
    username: str,
    level: str | None = None,
    project_id: str | None = None,
    objective: str | None = None,
    approval_id: str | None = None,
) -> dict[str, Any]:
    normalized_level = _normalize_level(level)
    normalized_objective = _multiline(objective, 2000)
    needs_approval = normalized_level in {"run_dev_commands", "full_dev_project"} and not _text(approval_id, 160)
    status = "pending_approval" if needs_approval else "active"
    session_id = _stable_id("cwk_plan", username, project_id, normalized_level, normalized_objective)
    return {
        "coworkServiceVersion": COGNIX_COWORK_SERVICE_VERSION,
        "remoteControlPolicyEngineVersion": COGNIX_REMOTE_CONTROL_POLICY_ENGINE_VERSION,
        "humanApprovalGateVersion": COGNIX_HUMAN_APPROVAL_GATE_VERSION,
        "mode": "native_cowork_session_plan",
        "valid": True,
        "username": _text(username, 160),
        "projectId": _text(project_id, 160) or None,
        "sessionPlanId": session_id,
        "cowork": {
            "level": normalized_level,
            "status": status,
            "objective": normalized_objective,
            "capabilities": _capabilities_for_level(normalized_level),
            "visibleToUser": True,
            "neverStealth": True,
            "approvalRequired": needs_approval,
            "approvalId": _text(approval_id, 160) or None,
        },
        "controls": {
            "pause": True,
            "stop": True,
            "history": True,
            "currentAction": True,
            "lastModifiedFile": True,
            "lastCommand": True,
        },
        "approval": {
            "required": needs_approval,
            "reason": "run_dev_commands_and_full_dev_project_require_human_approval" if needs_approval else "",
            "requestType": "cowork:control",
        },
        "sideEffects": {
            "sessionWrite": False,
            "permissionWrite": False,
            "approvalWrite": False,
            "auditWrite": False,
            "commandExecution": False,
            "fileWrite": False,
            "secretRead": False,
            "networkCall": False,
        },
    }


def build_cowork_status_update_plan(
    *,
    username: str,
    session: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    normalized = _key(status, "paused")
    if normalized not in {"active", "paused", "stopped"}:
        normalized = "paused"
    return {
        "coworkServiceVersion": COGNIX_COWORK_SERVICE_VERSION,
        "mode": "native_cowork_status_update_plan",
        "username": _text(username, 160),
        "sessionId": str(session.get("id") or session.get("scope_id") or ""),
        "previousStatus": _session_status(session),
        "status": normalized,
        "visibleToUser": True,
        "neverStealth": True,
        "sideEffects": {
            "sessionWrite": False,
            "auditWrite": False,
            "commandExecution": False,
            "fileWrite": False,
            "secretRead": False,
        },
    }


def build_cowork_action_plan(
    *,
    username: str,
    session: dict[str, Any],
    action_type: str,
    command: str | None = None,
    path: str | None = None,
    description: str | None = None,
    approval_id: str | None = None,
) -> dict[str, Any]:
    normalized_action = _key(action_type, "read_file")
    if normalized_action not in COWORK_ACTION_TYPES:
        normalized_action = "read_file"
    level = _session_level(session)
    status = _session_status(session)
    allowed_by_level = _action_allowed_for_level(level, normalized_action)
    path_guard = _path_policy(path)
    command_guard = _command_policy(command) if normalized_action == "run_command" else {
        "command": _text(command, 1200),
        "riskLevel": "low",
        "allowlistMatch": False,
        "requiresApproval": False,
        "blockedReasons": [],
        "approvalReasons": [],
    }
    blocked_reasons: list[str] = []
    approval_reasons: list[str] = []
    if status == "stopped":
        blocked_reasons.append("session_stopped")
    if status == "paused" and normalized_action not in {"pause", "stop"}:
        blocked_reasons.append("session_paused")
    if not allowed_by_level:
        blocked_reasons.append("level_does_not_allow_action")
    blocked_reasons.extend(command_guard.get("blockedReasons") or [])
    blocked_reasons.extend(path_guard.get("blockedReasons") or [])
    approval_reasons.extend(command_guard.get("approvalReasons") or [])
    if command_guard.get("requiresApproval") and not command_guard.get("blockedReasons"):
        approval_reasons.append("command_requires_approval")
    if path_guard.get("requiresApproval") and not path_guard.get("blockedReasons"):
        approval_reasons.append("path_requires_approval")
    if normalized_action in {"edit_file", "run_command"} and not _text(approval_id, 160):
        approval_reasons.append("human_approval_required_for_mutating_action")
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    risk_level = max(
        [str(command_guard.get("riskLevel") or "low"), str(path_guard.get("riskLevel") or "low")],
        key = lambda item: risk_order.get(item, 0),
    )
    requires_approval = bool(approval_reasons or blocked_reasons)
    allowed = not blocked_reasons and not (approval_reasons and not _text(approval_id, 160))
    decision = "blocked" if blocked_reasons else ("approval_required" if requires_approval and not approval_id else "planned")
    return {
        "coworkServiceVersion": COGNIX_COWORK_SERVICE_VERSION,
        "remoteControlPolicyEngineVersion": COGNIX_REMOTE_CONTROL_POLICY_ENGINE_VERSION,
        "commandAllowlistVersion": COGNIX_COMMAND_ALLOWLIST_VERSION,
        "actionRecorderVersion": COGNIX_ACTION_RECORDER_VERSION,
        "humanApprovalGateVersion": COGNIX_HUMAN_APPROVAL_GATE_VERSION,
        "mode": "native_cowork_action_plan",
        "username": _text(username, 160),
        "sessionId": str(session.get("id") or session.get("scope_id") or ""),
        "projectId": session.get("project_id") or _session_payload(session).get("projectId"),
        "action": {
            "id": _stable_id("cwka", username, session.get("id"), normalized_action, command, path, description),
            "type": normalized_action,
            "description": _multiline(description, 1200),
            "path": path_guard["path"],
            "command": command_guard["command"],
            "level": level,
            "status": decision,
            "riskLevel": risk_level,
            "allowed": allowed,
            "requiresApproval": requires_approval,
            "approvalId": _text(approval_id, 160) or None,
            "blockedReasons": blocked_reasons,
            "approvalReasons": sorted(set(approval_reasons)),
            "allowlistMatch": bool(command_guard.get("allowlistMatch")),
            "visibleToUser": True,
            "neverStealth": True,
            "willExecuteNow": False,
        },
        "policy": {
            "allowedByLevel": allowed_by_level,
            "directExecutionAllowed": False,
            "projectBoundaryRequired": True,
            "secretReadAllowed": False,
        },
        "sideEffects": {
            "actionWrite": False,
            "auditWrite": False,
            "commandExecution": False,
            "fileWrite": False,
            "secretRead": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
        },
    }
