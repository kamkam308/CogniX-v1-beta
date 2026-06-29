# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native command palette.

The palette exposes commands through CogniX Core with permission-aware filtering
and dry-run execution plans. It never calls models, tools, or frontend-only APIs
directly.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_COMMAND_PALETTE_VERSION = "cognix_command_palette_v1"
COGNIX_COMMAND_REGISTRY_VERSION = "cognix_command_registry_v1"
COGNIX_PERMISSION_AWARE_COMMAND_FILTER_VERSION = "cognix_permission_aware_command_filter_v1"

BASE_COMMANDS: list[dict[str, Any]] = [
    {
        "id": "new_chat",
        "label": "New Chat",
        "description": "Start a fresh CogniX chat.",
        "category": "chat",
        "route": "/",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["chat", "conversation", "nouveau"],
        "riskLevel": "low",
        "priority": 10,
    },
    {
        "id": "create_project",
        "label": "Create Project",
        "description": "Open the native CogniX project creation flow.",
        "category": "projects",
        "route": "/projects/new",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["project", "projet", "create", "new"],
        "riskLevel": "low",
        "priority": 20,
    },
    {
        "id": "open_library",
        "label": "Open Library",
        "description": "Open the central CogniX Library.",
        "category": "library",
        "route": "/library",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["library", "bibliotheque", "document", "file"],
        "riskLevel": "low",
        "priority": 30,
    },
    {
        "id": "search_documents",
        "label": "Search Documents",
        "description": "Search Library assets with CogniX permission filters.",
        "category": "library",
        "route": "/library?focus=search",
        "actionType": "open_search",
        "requiredPermissions": ["library:read"],
        "keywords": ["search", "chercher", "document", "library", "rag"],
        "riskLevel": "low",
        "priority": 35,
    },
    {
        "id": "create_scheduled_task",
        "label": "Create Scheduled Task",
        "description": "Open the Scheduled task composer.",
        "category": "automation",
        "route": "/scheduled/new",
        "actionType": "navigate",
        "requiredPermissions": ["scheduled:create"],
        "keywords": ["scheduled", "schedule", "cron", "task", "automation", "tache"],
        "riskLevel": "medium",
        "priority": 40,
    },
    {
        "id": "open_pulse",
        "label": "Open Pulse",
        "description": "Open CogniX Pulse activity and recommendations.",
        "category": "pulse",
        "route": "/pulse",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["pulse", "activity", "resume", "dashboard"],
        "riskLevel": "low",
        "priority": 45,
    },
    {
        "id": "open_apps",
        "label": "Open Apps",
        "description": "Open connected CogniX apps and integrations.",
        "category": "apps",
        "route": "/apps",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["apps", "integration", "connecteur"],
        "riskLevel": "low",
        "priority": 50,
    },
    {
        "id": "open_gpts",
        "label": "Open GPTs",
        "description": "Open CogniX custom assistant configurations.",
        "category": "gpts",
        "route": "/gpts",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["gpt", "assistant", "custom", "persona"],
        "riskLevel": "low",
        "priority": 55,
    },
    {
        "id": "open_images",
        "label": "Open Images",
        "description": "Open image generation, editing, analysis, and Library linking.",
        "category": "images",
        "route": "/images",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["image", "generate", "edit", "visual"],
        "riskLevel": "low",
        "priority": 60,
    },
    {
        "id": "open_model_hub",
        "label": "Open Model Hub",
        "description": "Open model registry, favorites, and quick switching.",
        "category": "models",
        "route": "/hub",
        "actionType": "navigate",
        "requiredPermissions": ["authenticated"],
        "keywords": ["model", "hub", "favorite", "pin", "quick switcher"],
        "riskLevel": "low",
        "priority": 65,
    },
    {
        "id": "launch_codex",
        "label": "Launch Codex",
        "description": "Open the secure Codex planning surface.",
        "category": "codex",
        "route": "/codex",
        "actionType": "navigate",
        "requiredPermissions": ["developer_mode"],
        "keywords": ["codex", "code", "repo", "tests", "develop"],
        "riskLevel": "high",
        "priority": 70,
    },
    {
        "id": "activate_cowork",
        "label": "Activate Cowork",
        "description": "Open the visible, permission-gated Cowork control panel.",
        "category": "cowork",
        "route": "/cowork",
        "actionType": "navigate",
        "requiredPermissions": ["cowork:control"],
        "keywords": ["cowork", "remote", "assist", "control", "ordinateur"],
        "riskLevel": "high",
        "priority": 75,
    },
    {
        "id": "view_approvals",
        "label": "View Approvals",
        "description": "Open admin approval queue.",
        "category": "admin",
        "route": "/admin/approvals",
        "actionType": "navigate",
        "requiredPermissions": ["admin"],
        "keywords": ["approval", "approbation", "admin", "request"],
        "riskLevel": "medium",
        "priority": 80,
    },
]


def _normalize(value: Any, *, limit: int = 240) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()[:limit]


def _normalize_key(value: Any) -> str:
    text = _normalize(value, limit = 160).casefold()
    return re.sub(r"[^a-z0-9:_-]+", "_", text).strip("_")


def _permission_status(
    required_permissions: list[str],
    *,
    granted_permissions: set[str] | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    granted = {str(item).strip().casefold() for item in granted_permissions or set() if str(item).strip()}
    missing: list[str] = []
    for permission in required_permissions:
        key = str(permission).strip().casefold()
        if not key or key == "authenticated":
            continue
        if is_admin and (key == "admin" or key.startswith("admin:")):
            continue
        if key not in granted:
            missing.append(key)
    return {
        "allowed": not missing,
        "missingPermissions": missing,
        "requiredPermissions": required_permissions,
    }


def _command_search_text(command: dict[str, Any]) -> str:
    parts = [
        command.get("id"),
        command.get("label"),
        command.get("description"),
        command.get("category"),
        " ".join(str(item) for item in command.get("keywords", []) if item),
    ]
    return " ".join(str(item or "") for item in parts).casefold()


def _score(command: dict[str, Any], query: str) -> int:
    if not query:
        return max(1, 100 - int(command.get("priority") or 100))
    needle = query.casefold()
    text = _command_search_text(command)
    score = 0
    if needle in str(command.get("label") or "").casefold():
        score += 80
    if needle in str(command.get("id") or "").casefold():
        score += 60
    if needle in text:
        score += 35
    for token in [item for item in re.split(r"\s+", needle) if item]:
        if token in text:
            score += 10
    return score


def _decorate_command(
    command: dict[str, Any],
    *,
    granted_permissions: set[str] | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    out = dict(command)
    permissions = _permission_status(
        [str(item) for item in command.get("requiredPermissions", []) if item],
        granted_permissions = granted_permissions,
        is_admin = is_admin,
    )
    out["permissionFilterVersion"] = COGNIX_PERMISSION_AWARE_COMMAND_FILTER_VERSION
    out["available"] = bool(permissions["allowed"])
    out["status"] = "available" if out["available"] else "missing_permissions"
    out["missingPermissions"] = permissions["missingPermissions"]
    out["navigationOnly"] = out.get("actionType") == "navigate"
    out["directExecutionAllowed"] = False
    return out


def build_command_palette_blueprint() -> dict[str, Any]:
    return {
        "commandPaletteVersion": COGNIX_COMMAND_PALETTE_VERSION,
        "commandRegistryVersion": COGNIX_COMMAND_REGISTRY_VERSION,
        "permissionFilterVersion": COGNIX_PERMISSION_AWARE_COMMAND_FILTER_VERSION,
        "mode": "permission_aware_native_command_registry",
        "services": ["CommandPaletteService", "CommandRegistry", "PermissionAwareCommandFilter"],
        "shortcuts": ["Ctrl+K", "Cmd+K"],
        "policies": {
            "frontendDirectModelCallAllowed": False,
            "frontendDirectToolExecutionAllowed": False,
            "sensitiveCommandsRequirePermission": True,
            "blockedCommandsStayVisibleOnlyWhenRequested": True,
            "commandPlansAreDryRun": True,
        },
        "commandCount": len(BASE_COMMANDS),
        "sideEffects": {
            "commandUsageLogWrite": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "filesystemWrite": False,
            "permissionGrant": False,
        },
    }


def list_commands(
    *,
    query: str | None = None,
    granted_permissions: set[str] | None = None,
    is_admin: bool = False,
    project_id: str | None = None,
    limit: int = 20,
    include_disabled: bool = False,
) -> dict[str, Any]:
    safe_query = _normalize(query, limit = 240)
    safe_project_id = _normalize(project_id, limit = 160) or None
    decorated: list[dict[str, Any]] = []
    for command in BASE_COMMANDS:
        score = _score(command, safe_query)
        if safe_query and score <= 0:
            continue
        item = _decorate_command(command, granted_permissions = granted_permissions, is_admin = is_admin)
        item["score"] = score
        item["projectId"] = safe_project_id
        if item["available"] or include_disabled:
            decorated.append(item)
    decorated.sort(key = lambda item: (-int(item.get("score") or 0), int(item.get("priority") or 999), item["label"]))
    safe_limit = min(max(int(limit or 20), 1), 80)
    commands = decorated[:safe_limit]
    return {
        "commandPaletteVersion": COGNIX_COMMAND_PALETTE_VERSION,
        "commandRegistryVersion": COGNIX_COMMAND_REGISTRY_VERSION,
        "permissionFilterVersion": COGNIX_PERMISSION_AWARE_COMMAND_FILTER_VERSION,
        "mode": "command_search",
        "query": safe_query,
        "projectId": safe_project_id,
        "commands": commands,
        "summary": {
            "returned": len(commands),
            "available": sum(1 for item in commands if item.get("available")),
            "blocked": sum(1 for item in commands if not item.get("available")),
        },
        "sideEffects": build_command_palette_blueprint()["sideEffects"],
    }


def build_command_plan(
    *,
    command_id: str,
    query: str | None = None,
    project_id: str | None = None,
    parameters: dict[str, Any] | None = None,
    granted_permissions: set[str] | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    safe_command_id = _normalize_key(command_id)
    command = next((item for item in BASE_COMMANDS if item["id"] == safe_command_id), None)
    if command is None:
        return {
            "commandPaletteVersion": COGNIX_COMMAND_PALETTE_VERSION,
            "mode": "command_plan",
            "status": "unknown_command",
            "commandId": safe_command_id,
            "allowedToRun": False,
            "missingPermissions": [],
            "blockedActions": [{"id": "unknown_command", "reason": "Command is not registered in CogniX Core."}],
            "sideEffects": build_command_palette_blueprint()["sideEffects"],
        }
    decorated = _decorate_command(command, granted_permissions = granted_permissions, is_admin = is_admin)
    safe_parameters = {
        _normalize_key(key): _normalize(value, limit = 500)
        for key, value in (parameters or {}).items()
        if _normalize_key(key)
    }
    status = "ready" if decorated["available"] else "missing_permissions"
    blocked_actions = []
    if not decorated["available"]:
        blocked_actions.append(
            {
                "id": "permission_gate",
                "reason": "Command requires permissions that are not currently granted.",
                "missingPermissions": decorated["missingPermissions"],
            }
        )
    return {
        "commandPaletteVersion": COGNIX_COMMAND_PALETTE_VERSION,
        "commandRegistryVersion": COGNIX_COMMAND_REGISTRY_VERSION,
        "permissionFilterVersion": COGNIX_PERMISSION_AWARE_COMMAND_FILTER_VERSION,
        "mode": "command_plan",
        "status": status,
        "allowedToRun": decorated["available"],
        "command": decorated,
        "commandId": safe_command_id,
        "query": _normalize(query, limit = 240),
        "projectId": _normalize(project_id, limit = 160) or None,
        "parameters": safe_parameters,
        "executionPlan": {
            "actionType": decorated["actionType"],
            "route": decorated["route"],
            "frontendMayNavigate": decorated["available"] and decorated["actionType"] == "navigate",
            "requiresConfirmation": decorated["riskLevel"] in {"medium", "high"},
            "runsToolNow": False,
            "loadsModelNow": False,
            "generatesNow": False,
        },
        "blockedActions": blocked_actions,
        "sideEffects": build_command_palette_blueprint()["sideEffects"],
    }
