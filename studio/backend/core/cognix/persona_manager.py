# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI persona builder.

Personas are reusable prompt, tool-permission, memory-scope, and project-binding
plans. They cannot grant permissions: requested tools are intersected with the
user's existing permissions and safe baseline capabilities.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_PERSONA_MANAGER_VERSION = "cognix_persona_manager_v1"
COGNIX_PERSONA_TEMPLATE_ENGINE_VERSION = "cognix_persona_template_engine_v1"
COGNIX_PERSONA_PERMISSION_BINDER_VERSION = "cognix_persona_permission_binder_v1"

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

ROLE_PRESETS = {
    "physics_teacher": {
        "role": "Prof de physique",
        "tone": "pedagogical",
        "level": "intermediate",
        "limits": ["Ne pas inventer de citations.", "Expliquer les etapes de calcul."],
    },
    "code_coach": {
        "role": "Coach code",
        "tone": "technical",
        "level": "advanced",
        "limits": ["Ne pas executer d'outil sans permission.", "Privilegier les tests reproductibles."],
    },
    "business_assistant": {
        "role": "Assistant business",
        "tone": "direct",
        "level": "professional",
        "limits": ["Separer faits, hypotheses et risques.", "Respecter les donnees confidentielles."],
    },
    "internal_legal": {
        "role": "Assistant juridique interne",
        "tone": "precise",
        "level": "professional",
        "limits": ["Ne pas donner de conseil legal final.", "Demander validation humaine."],
    },
    "ai_mentor": {
        "role": "Mentor IA",
        "tone": "supportive",
        "level": "adaptive",
        "limits": ["Adapter le niveau.", "Rendre les compromis explicites."],
    },
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower()).strip("_")
    return normalized or "persona"


def _list_strings(values: list[str] | None, *, max_count: int = 20, max_len: int = 240) -> list[str]:
    result: list[str] = []
    for item in values or []:
        text = _normalize(item)
        if text:
            result.append(text[:max_len])
        if len(result) >= max_count:
            break
    return result


def build_persona_blueprint() -> dict[str, Any]:
    return {
        "personaManagerVersion": COGNIX_PERSONA_MANAGER_VERSION,
        "templateEngineVersion": COGNIX_PERSONA_TEMPLATE_ENGINE_VERSION,
        "permissionBinderVersion": COGNIX_PERSONA_PERMISSION_BINDER_VERSION,
        "mode": "dry_run_persona_builder",
        "services": ["PersonaManager", "PersonaTemplateEngine", "PersonaPermissionBinder"],
        "pipeline": ["persona_config", "system_prompt_template", "tool_permissions", "memory_scope", "project_binding"],
        "configContract": {
            "role": True,
            "tone": True,
            "level": True,
            "limits": True,
            "allowedTools": True,
            "preferredModel": True,
            "memoryIds": True,
        },
        "rolePresets": ROLE_PRESETS,
        "policies": {
            "personaCanGrantPermissions": False,
            "personaCanBypassUserPermissions": False,
            "toolExecutionAllowedFromBuilder": False,
            "memoryContentReadAllowedFromBuilder": False,
            "projectBindingRequiresOwnership": True,
        },
        "sideEffects": {
            "personaWrite": False,
            "personaVersionWrite": False,
            "projectBindingWrite": False,
            "permissionGrant": False,
            "toolExecution": False,
            "memoryRead": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def _apply_preset(role: str | None, tone: str | None, level: str | None, limits: list[str] | None) -> dict[str, Any]:
    key = _slug(role or "")
    preset = ROLE_PRESETS.get(key, {})
    return {
        "role": _normalize(role) or preset.get("role") or "Assistant CogniX",
        "tone": _normalize(tone) or preset.get("tone") or "clear",
        "level": _normalize(level) or preset.get("level") or "adaptive",
        "limits": _list_strings(limits) or list(preset.get("limits") or []),
    }


def _tool_binding(requested_tools: list[str] | None, granted_permissions: set[str] | None) -> dict[str, Any]:
    granted = {str(item).strip().lower() for item in granted_permissions or set() if str(item).strip()}
    tool_records: list[dict[str, Any]] = []
    allowed_ids: list[str] = []
    blocked_ids: list[str] = []
    for raw_tool in _list_strings(requested_tools, max_count = 30, max_len = 120):
        tool_id = _slug(raw_tool)
        required_permission = TOOL_PERMISSION_REQUIREMENTS.get(tool_id)
        baseline_allowed = tool_id in SAFE_BASELINE_TOOLS
        permission_allowed = bool(required_permission and required_permission in granted)
        allowed = baseline_allowed or permission_allowed
        if allowed:
            allowed_ids.append(tool_id)
        else:
            blocked_ids.append(tool_id)
        tool_records.append(
            {
                "toolId": tool_id,
                "label": raw_tool,
                "status": "allowed" if allowed else "blocked_missing_user_permission",
                "requiredPermission": required_permission,
                "baselineAllowed": baseline_allowed,
                "grantedByUserPermission": permission_allowed,
                "reason": "Permission utilisateur presente ou outil de contexte local."
                if allowed
                else "La persona ne peut pas contourner les permissions utilisateur.",
            }
        )
    return {
        "permissionBinderVersion": COGNIX_PERSONA_PERMISSION_BINDER_VERSION,
        "permissionSource": "cognix_user_permissions_plus_safe_baseline",
        "requestedToolCount": len(tool_records),
        "allowedToolIds": allowed_ids,
        "blockedToolIds": blocked_ids,
        "tools": tool_records,
        "policies": {
            "personaCanGrantPermissions": False,
            "blockedToolsStayBlockedUntilUserPermission": True,
        },
    }


def _memory_scope(memory_ids: list[str] | None, project_id: str | None) -> dict[str, Any]:
    clean_memory_ids = _list_strings(memory_ids, max_count = 50, max_len = 180)
    if clean_memory_ids:
        scope_type = "selected_memories"
    elif project_id:
        scope_type = "project_memory"
    else:
        scope_type = "no_attached_memory"
    return {
        "scopeType": scope_type,
        "projectId": project_id,
        "memoryIds": clean_memory_ids,
        "memoryContentReadNow": False,
        "requiresUserPermission": True,
    }


def _system_prompt_template(
    *,
    name: str,
    role: str,
    tone: str,
    level: str,
    limits: list[str],
    preferred_model: str | None,
    allowed_tool_ids: list[str],
    memory_scope: dict[str, Any],
) -> str:
    limit_lines = "\n".join(f"- {item}" for item in limits) if limits else "- Respecter les limites du projet."
    tools_line = ", ".join(allowed_tool_ids) if allowed_tool_ids else "aucun outil externe"
    preferred = preferred_model or "modele selectionne par CogniX"
    return (
        f"Tu es {name}, persona CogniX.\n"
        f"Role: {role}.\n"
        f"Ton: {tone}.\n"
        f"Niveau: {level}.\n"
        f"Modele prefere: {preferred}.\n"
        f"Outils autorises par permissions utilisateur: {tools_line}.\n"
        f"Memoire associee: {memory_scope['scopeType']}.\n"
        "Regle de securite: cette persona ne peut jamais ignorer, creer ou contourner les permissions utilisateur.\n"
        "Limites:\n"
        f"{limit_lines}"
    )


def build_persona_plan(
    *,
    username: str,
    name: str | None = None,
    role: str | None = None,
    tone: str | None = None,
    level: str | None = None,
    limits: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    preferred_model: str | None = None,
    memory_ids: list[str] | None = None,
    project_id: str | None = None,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    preset = _apply_preset(role, tone, level, limits)
    persona_name = _normalize(name) or preset["role"]
    tool_permissions = _tool_binding(allowed_tools, granted_permissions)
    memory_scope = _memory_scope(memory_ids, project_id)
    clean_preferred_model = _normalize(preferred_model)[:240] or None
    system_prompt = _system_prompt_template(
        name = persona_name,
        role = preset["role"],
        tone = preset["tone"],
        level = preset["level"],
        limits = preset["limits"],
        preferred_model = clean_preferred_model,
        allowed_tool_ids = tool_permissions["allowedToolIds"],
        memory_scope = memory_scope,
    )
    config = {
        "name": persona_name,
        "role": preset["role"],
        "tone": preset["tone"],
        "level": preset["level"],
        "limits": preset["limits"],
        "allowedTools": tool_permissions["allowedToolIds"],
        "blockedTools": tool_permissions["blockedToolIds"],
        "preferredModel": clean_preferred_model,
        "memoryScope": memory_scope,
        "projectId": project_id,
    }
    persona_seed = f"{username}:{persona_name}:{preset['role']}:{project_id}:{system_prompt}"
    persona_id = f"pers_{hashlib.sha256(persona_seed.encode('utf-8')).hexdigest()[:24]}"
    return {
        "personaManagerVersion": COGNIX_PERSONA_MANAGER_VERSION,
        "templateEngineVersion": COGNIX_PERSONA_TEMPLATE_ENGINE_VERSION,
        "permissionBinderVersion": COGNIX_PERSONA_PERMISSION_BINDER_VERSION,
        "mode": "dry_run_persona_builder",
        "username": username,
        "personaId": persona_id,
        "config": config,
        "systemPromptTemplate": {
            "templateEngineVersion": COGNIX_PERSONA_TEMPLATE_ENGINE_VERSION,
            "content": system_prompt,
            "rawReasoningRequested": False,
        },
        "toolPermissions": tool_permissions,
        "memoryScope": memory_scope,
        "projectBinding": {
            "projectId": project_id,
            "willBindOnStore": bool(project_id),
            "requiresOwnedProject": bool(project_id),
            "automaticProjectMutation": False,
        },
        "security": {
            "cannotBypassUserPermissions": True,
            "permissionGrantRequested": False,
            "blockedToolCount": len(tool_permissions["blockedToolIds"]),
        },
        "sideEffects": build_persona_blueprint()["sideEffects"],
    }
