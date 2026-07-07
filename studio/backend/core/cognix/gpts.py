# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native GPT manager.

Custom GPTs are persisted assistant configurations bound to the creator's
permissions, tools, documents, memory, project scope, and CogniX orchestrator.
They never grant permissions or call models directly.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_GPT_MANAGER_VERSION = "cognix_gpt_manager_v1"
COGNIX_CUSTOM_ASSISTANT_RUNTIME_VERSION = "cognix_custom_assistant_runtime_v1"
COGNIX_GPT_PERMISSION_BINDER_VERSION = "cognix_gpt_permission_binder_v1"
COGNIX_GPT_TOOL_BINDER_VERSION = "cognix_gpt_tool_binder_v1"
COGNIX_GPT_MEMORY_BINDER_VERSION = "cognix_gpt_memory_binder_v1"

SAFE_BASELINE_TOOLS = {"project_context", "memory_read", "rag_retrieval"}
TOOL_PERMISSION_REQUIREMENTS = {
    "codex": "tools:codex",
    "terminal": "tools:terminal",
    "web_search": "tools:web_search",
    "browser": "tools:browser",
    "github": "tools:github",
    "google_drive": "tools:google_drive",
    "gmail": "tools:gmail",
    "calendar": "tools:calendar",
    "notion": "tools:notion",
    "hugging_face": "tools:hugging_face",
    "kaggle": "tools:kaggle",
    "cloud_training": "tools:cloud_training",
}
PRIVACY_LEVELS = {"private", "project", "organization"}
SHARE_SCOPES = {"private", "project", "organization", "public_readonly"}


def _normalize(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _slug(value: Any) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "gpt"


def _list_strings(values: list[Any] | None, *, max_count: int = 50, max_len: int = 240) -> list[str]:
    result: list[str] = []
    for item in values or []:
        text = _normalize(item, limit = max_len)
        if text:
            result.append(text)
        if len(result) >= max_count:
            break
    return result


def build_gpts_blueprint() -> dict[str, Any]:
    return {
        "gptManagerVersion": COGNIX_GPT_MANAGER_VERSION,
        "customAssistantRuntimeVersion": COGNIX_CUSTOM_ASSISTANT_RUNTIME_VERSION,
        "permissionBinderVersion": COGNIX_GPT_PERMISSION_BINDER_VERSION,
        "toolBinderVersion": COGNIX_GPT_TOOL_BINDER_VERSION,
        "memoryBinderVersion": COGNIX_GPT_MEMORY_BINDER_VERSION,
        "mode": "orchestrator_first_custom_gpt_contract",
        "services": [
            "GPTManager",
            "CustomAssistantRuntime",
            "GPTPermissionBinder",
            "GPTToolBinder",
            "GPTMemoryBinder",
        ],
        "configContract": {
            "name": True,
            "description": True,
            "instructions": True,
            "preferredModel": True,
            "allowedTools": True,
            "documentIds": True,
            "memoryIds": True,
            "skills": True,
            "directives": True,
            "privacyLevel": True,
            "icon": True,
            "shareScope": True,
            "projectId": True,
        },
        "policies": {
            "gptCanGrantPermissions": False,
            "gptCanBypassCreatorPermissions": False,
            "frontendDirectModelCallAllowed": False,
            "runtimeMustUseOrchestrator": True,
            "rawDocumentReadDuringPlanning": False,
            "rawMemoryReadDuringPlanning": False,
        },
        "sideEffects": {
            "gptWrite": False,
            "gptVersionWrite": False,
            "projectBindingWrite": False,
            "usageLogWrite": False,
            "permissionGrant": False,
            "toolExecution": False,
            "documentRead": False,
            "memoryRead": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def _tool_binding(requested_tools: list[Any] | None, granted_permissions: set[str] | None) -> dict[str, Any]:
    granted = {str(item).strip().lower() for item in granted_permissions or set() if str(item).strip()}
    records: list[dict[str, Any]] = []
    allowed: list[str] = []
    blocked: list[str] = []
    for raw_tool in _list_strings(requested_tools, max_count = 40, max_len = 120):
        tool_id = _slug(raw_tool)
        required_permission = TOOL_PERMISSION_REQUIREMENTS.get(tool_id)
        baseline_allowed = tool_id in SAFE_BASELINE_TOOLS
        permission_allowed = bool(required_permission and required_permission in granted)
        status = "allowed" if baseline_allowed or permission_allowed else "blocked_missing_creator_permission"
        if status == "allowed":
            allowed.append(tool_id)
        else:
            blocked.append(tool_id)
        records.append(
            {
                "toolId": tool_id,
                "label": raw_tool,
                "status": status,
                "requiredPermission": required_permission,
                "baselineAllowed": baseline_allowed,
                "grantedByCreatorPermission": permission_allowed,
            }
        )
    return {
        "toolBinderVersion": COGNIX_GPT_TOOL_BINDER_VERSION,
        "permissionBinderVersion": COGNIX_GPT_PERMISSION_BINDER_VERSION,
        "requestedToolCount": len(records),
        "allowedToolIds": allowed,
        "blockedToolIds": blocked,
        "tools": records,
        "policies": {
            "gptCanGrantPermissions": False,
            "blockedToolsStayBlockedUntilCreatorPermission": True,
        },
    }


def _document_binding(document_ids: list[Any] | None, project_id: str | None) -> dict[str, Any]:
    ids = _list_strings(document_ids, max_count = 80, max_len = 180)
    return {
        "documentIds": ids,
        "documentCount": len(ids),
        "projectId": project_id,
        "rawDocumentReadNow": False,
        "ragEligible": bool(ids),
        "requiresLibraryOwnership": True,
    }


def _memory_binding(memory_ids: list[Any] | None, project_id: str | None) -> dict[str, Any]:
    ids = _list_strings(memory_ids, max_count = 80, max_len = 180)
    scope = "selected_memories" if ids else "project_memory" if project_id else "no_attached_memory"
    return {
        "memoryBinderVersion": COGNIX_GPT_MEMORY_BINDER_VERSION,
        "scopeType": scope,
        "memoryIds": ids,
        "projectId": project_id,
        "rawMemoryReadNow": False,
        "requiresUserPermission": True,
    }


def _permission_binding(*, privacy_level: str, share_scope: str, blocked_tools: list[str]) -> dict[str, Any]:
    safe_privacy = privacy_level if privacy_level in PRIVACY_LEVELS else "private"
    safe_share = share_scope if share_scope in SHARE_SCOPES else "private"
    share_allowed = not (safe_privacy == "private" and safe_share != "private")
    return {
        "permissionBinderVersion": COGNIX_GPT_PERMISSION_BINDER_VERSION,
        "privacyLevel": safe_privacy,
        "shareScope": safe_share if share_allowed else "private",
        "requestedShareScope": safe_share,
        "shareAllowed": share_allowed,
        "blockedToolIds": blocked_tools,
        "permissionGrantRequested": False,
        "cannotExceedCreatorPermissions": True,
        "warnings": [
            {
                "id": "private_gpt_share_scope_reduced",
                "message": "Un GPT prive ne peut pas etre partage hors du compte createur.",
            }
        ]
        if not share_allowed
        else [],
    }


def _instructions_template(
    *,
    name: str,
    description: str,
    instructions: str,
    preferred_model: str | None,
    allowed_tools: list[str],
    document_binding: dict[str, Any],
    memory_binding: dict[str, Any],
    directives: list[str],
    skills: list[str],
) -> str:
    tools = ", ".join(allowed_tools) if allowed_tools else "aucun outil externe"
    directives_text = "\n".join(f"- {item}" for item in directives) if directives else "- Respecter les directives du projet."
    skills_text = ", ".join(skills) if skills else "skills par defaut CogniX"
    return (
        f"Tu es {name}, GPT natif CogniX.\n"
        f"Description: {description or 'Assistant specialise CogniX'}.\n"
        f"Modele prefere: {preferred_model or 'selection automatique par CogniX'}.\n"
        f"Outils autorises: {tools}.\n"
        f"Documents lies: {document_binding['documentCount']}.\n"
        f"Memoire: {memory_binding['scopeType']}.\n"
        f"Skills: {skills_text}.\n"
        "Regle de securite: ce GPT ne peut jamais depasser les permissions du createur ou de l'organisation.\n"
        "Instructions utilisateur:\n"
        f"{instructions or 'Aider clairement en restant dans le contexte autorise.'}\n"
        "Directives:\n"
        f"{directives_text}"
    )


def build_gpt_plan(
    *,
    username: str,
    name: str,
    description: str | None = None,
    instructions: str | None = None,
    preferred_model: str | None = None,
    allowed_tools: list[Any] | None = None,
    document_ids: list[Any] | None = None,
    memory_ids: list[Any] | None = None,
    skills: list[Any] | None = None,
    directives: list[Any] | None = None,
    privacy_level: str = "private",
    icon: str | None = None,
    share_scope: str = "private",
    project_id: str | None = None,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    clean_name = _normalize(name, limit = 180) or "GPT CogniX"
    clean_description = _normalize(description, limit = 1000)
    clean_instructions = _normalize(instructions, limit = 12000)
    clean_model = _normalize(preferred_model, limit = 240) or None
    clean_project_id = _normalize(project_id, limit = 160) or None
    clean_skills = _list_strings(skills, max_count = 40, max_len = 160)
    clean_directives = _list_strings(directives, max_count = 40, max_len = 400)
    tool_binding = _tool_binding(allowed_tools, granted_permissions)
    document_binding = _document_binding(document_ids, clean_project_id)
    memory_binding = _memory_binding(memory_ids, clean_project_id)
    permission_binding = _permission_binding(
        privacy_level = _normalize(privacy_level, limit = 80) or "private",
        share_scope = _normalize(share_scope, limit = 80) or "private",
        blocked_tools = tool_binding["blockedToolIds"],
    )
    runtime_instructions = _instructions_template(
        name = clean_name,
        description = clean_description,
        instructions = clean_instructions,
        preferred_model = clean_model,
        allowed_tools = tool_binding["allowedToolIds"],
        document_binding = document_binding,
        memory_binding = memory_binding,
        directives = clean_directives,
        skills = clean_skills,
    )
    seed = f"{username}:{clean_name}:{clean_project_id}:{runtime_instructions}:{permission_binding['privacyLevel']}"
    gpt_id = f"gpt_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"
    config = {
        "name": clean_name,
        "description": clean_description,
        "instructions": clean_instructions,
        "preferredModel": clean_model,
        "allowedTools": tool_binding["allowedToolIds"],
        "blockedTools": tool_binding["blockedToolIds"],
        "documentIds": document_binding["documentIds"],
        "memoryIds": memory_binding["memoryIds"],
        "skills": clean_skills,
        "directives": clean_directives,
        "privacyLevel": permission_binding["privacyLevel"],
        "shareScope": permission_binding["shareScope"],
        "icon": _normalize(icon, limit = 80) or "sparkles",
        "projectId": clean_project_id,
    }
    side_effects = build_gpts_blueprint()["sideEffects"]
    return {
        "gptManagerVersion": COGNIX_GPT_MANAGER_VERSION,
        "customAssistantRuntimeVersion": COGNIX_CUSTOM_ASSISTANT_RUNTIME_VERSION,
        "permissionBinderVersion": COGNIX_GPT_PERMISSION_BINDER_VERSION,
        "toolBinderVersion": COGNIX_GPT_TOOL_BINDER_VERSION,
        "memoryBinderVersion": COGNIX_GPT_MEMORY_BINDER_VERSION,
        "mode": "gpt_config_plan",
        "username": username,
        "gptId": gpt_id,
        "config": config,
        "runtimeInstructions": {
            "content": runtime_instructions,
            "rawReasoningRequested": False,
        },
        "toolBinding": tool_binding,
        "documentBinding": document_binding,
        "memoryBinding": memory_binding,
        "permissionBinding": permission_binding,
        "projectBinding": {
            "projectId": clean_project_id,
            "willBindOnStore": bool(clean_project_id),
            "requiresOwnedProject": bool(clean_project_id),
            "automaticProjectMutation": False,
        },
        "runtimePolicy": {
            "routeThroughOrchestrator": True,
            "frontendDirectModelCallAllowed": False,
            "modelLoadNow": False,
            "generationNow": False,
        },
        "security": {
            "cannotExceedCreatorPermissions": True,
            "blockedToolCount": len(tool_binding["blockedToolIds"]),
            "privacyLevel": permission_binding["privacyLevel"],
            "shareScope": permission_binding["shareScope"],
            "warnings": permission_binding["warnings"],
        },
        "sideEffects": side_effects,
    }


def build_gpt_runtime_plan(
    *,
    username: str,
    gpt: dict[str, Any],
    objective: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    config = gpt.get("config") if isinstance(gpt.get("config"), dict) else {}
    tool_binding = gpt.get("toolBinding") or gpt.get("tool_binding")
    if not isinstance(tool_binding, dict):
        tool_binding = gpt.get("toolPermissions") if isinstance(gpt.get("toolPermissions"), dict) else {}
    memory_binding = gpt.get("memoryBinding") if isinstance(gpt.get("memoryBinding"), dict) else {}
    document_binding = gpt.get("documentBinding") if isinstance(gpt.get("documentBinding"), dict) else {}
    clean_objective = _normalize(objective, limit = 4000)
    side_effects = build_gpts_blueprint()["sideEffects"]
    return {
        "gptManagerVersion": COGNIX_GPT_MANAGER_VERSION,
        "customAssistantRuntimeVersion": COGNIX_CUSTOM_ASSISTANT_RUNTIME_VERSION,
        "mode": "gpt_runtime_plan",
        "username": username,
        "gptId": gpt.get("id") or gpt.get("gptId"),
        "objective": clean_objective,
        "projectId": _normalize(project_id, limit = 160) or config.get("projectId"),
        "orchestratorRequest": {
            "routeThroughOrchestrator": True,
            "preferredModel": config.get("preferredModel") or gpt.get("preferred_model"),
            "allowedToolIds": tool_binding.get("allowedToolIds", []),
            "blockedToolIds": tool_binding.get("blockedToolIds", []),
            "documentIds": document_binding.get("documentIds", config.get("documentIds", [])),
            "memoryIds": memory_binding.get("memoryIds", config.get("memoryIds", [])),
        },
        "runtimeGuards": {
            "frontendDirectModelCallAllowed": False,
            "toolExecutionNow": False,
            "modelLoadNow": False,
            "generationNow": False,
            "rawDocumentReadNow": False,
            "rawMemoryReadNow": False,
        },
        "sideEffects": side_effects,
    }
