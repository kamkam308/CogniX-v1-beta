# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Project/model skills and directives contracts.

Skills and directives are native CogniX project configuration. This module
prepares prompt/tool bindings only; it never grants permissions, executes
tools, calls models, writes files, or mutates storage directly.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_SKILL_MANAGER_VERSION = "cognix_skill_manager_v1"
COGNIX_SKILL_RUNTIME_BINDER_VERSION = "cognix_skill_runtime_binder_v1"
COGNIX_SKILL_PROMPT_BUILDER_VERSION = "cognix_skill_prompt_builder_v1"
COGNIX_SKILL_PERMISSION_BINDER_VERSION = "cognix_skill_permission_binder_v1"
COGNIX_DIRECTIVE_MANAGER_VERSION = "cognix_directive_manager_v1"
COGNIX_DIRECTIVE_COMPILER_VERSION = "cognix_directive_compiler_v1"
COGNIX_PROMPT_POLICY_ENGINE_VERSION = "cognix_prompt_policy_engine_v1"

SKILL_TABLES = ["skills", "skill_versions", "project_skills", "model_skills", "skill_examples"]
DIRECTIVE_TABLES = ["directives", "project_directives", "model_directives", "directive_priorities"]
DIRECTIVE_TYPES = ("style", "security", "privacy", "format", "tools", "model", "rag", "code", "pedagogy")
SOURCE_LEVEL_RANK = {
    "security": 100,
    "organization": 80,
    "project": 60,
    "user": 40,
    "model_preference": 20,
}
SAFE_BASELINE_TOOLS = {"project_context", "memory_read", "rag_retrieval"}


def _normalize(value: Any, limit: int = 4000, fallback: str = "") -> str:
    text = " ".join(str(value if value is not None else fallback).replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _safe_key(value: Any, fallback: str = "item") -> str:
    text = _normalize(value, 180, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return cleaned.strip("-")[:140] or fallback


def _string_list(value: Any, *, max_items: int = 30, max_len: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = _normalize(item, max_len)
        if text and text not in output:
            output.append(text)
        if len(output) >= max_items:
            break
    return output


def _tool_key(value: Any) -> str:
    return _safe_key(value, "tool")


def _permission_allows_tool(tool_id: str, granted_permissions: set[str]) -> bool:
    if tool_id in SAFE_BASELINE_TOOLS:
        return True
    candidates = {
        tool_id,
        f"tool:{tool_id}",
        f"tools:{tool_id}",
        f"tool:{tool_id}:use",
        f"tools:{tool_id}:use",
    }
    return bool(candidates & granted_permissions)


def _skill_hash(skill: dict[str, Any]) -> str:
    source = "|".join(str(skill.get(key) or "") for key in ("skillKey", "displayName", "objective", "instructions"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def build_project_skill_blueprint() -> dict[str, Any]:
    return {
        "skillManagerVersion": COGNIX_SKILL_MANAGER_VERSION,
        "runtimeBinderVersion": COGNIX_SKILL_RUNTIME_BINDER_VERSION,
        "promptBuilderVersion": COGNIX_SKILL_PROMPT_BUILDER_VERSION,
        "permissionBinderVersion": COGNIX_SKILL_PERMISSION_BINDER_VERSION,
        "services": ["SkillManager", "SkillRuntimeBinder", "SkillPromptBuilder", "SkillPermissionBinder"],
        "tables": SKILL_TABLES,
        "pipeline": ["Skill config", "Project binding", "Model binding", "Context injection", "Tool permission binding"],
        "policies": {
            "projectScoped": True,
            "modelScopedBindings": True,
            "toolPermissionsCannotEscalate": True,
            "contextInjectionPlannedServerSide": True,
            "frontendDirectModelCallAllowed": False,
        },
        "sideEffects": {
            "skillWrite": False,
            "versionWrite": False,
            "projectBindingWrite": False,
            "modelBindingWrite": False,
            "permissionGrant": False,
            "toolExecution": False,
            "contextInjection": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def normalize_skill_config(payload: dict[str, Any] | None, *, project_id: str, username: str) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    display_name = _normalize(source.get("displayName") or source.get("name"), 180, "Project skill")
    objective = _normalize(source.get("objective"), 1200)
    instructions = _normalize(source.get("instructions"), 6000)
    examples = source.get("examples") if isinstance(source.get("examples"), list) else []
    normalized_examples: list[dict[str, str]] = []
    for example in examples[:20]:
        if isinstance(example, dict):
            normalized_examples.append(
                {
                    "input": _normalize(example.get("input") or example.get("prompt"), 1200),
                    "output": _normalize(example.get("output") or example.get("answer"), 1200),
                }
            )
        else:
            normalized_examples.append({"input": _normalize(example, 1200), "output": ""})
    skill = {
        "schemaVersion": "cognix_project_skill_v1",
        "skillKey": _safe_key(source.get("skillKey") or display_name, "project-skill"),
        "displayName": display_name,
        "description": _normalize(source.get("description"), 1000),
        "objective": objective,
        "instructions": instructions,
        "modelId": _normalize(source.get("modelId"), 240) or None,
        "allowedTools": [_tool_key(item) for item in _string_list(source.get("allowedTools"), max_items = 40, max_len = 140)],
        "limits": source.get("limits") if isinstance(source.get("limits"), dict) else {},
        "examples": normalized_examples,
        "projectId": project_id,
        "createdBy": username,
    }
    skill["skillHash"] = _skill_hash(skill)
    return skill


def build_project_skill_plan(
    *,
    username: str,
    project_id: str,
    skill_config: dict[str, Any] | None,
    granted_permissions: set[str] | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    skill = normalize_skill_config(skill_config, project_id = project_id, username = username)
    if model_id:
        skill["modelId"] = _normalize(model_id, 240)
    granted = {str(item).strip().lower() for item in (granted_permissions or set()) if str(item).strip()}
    requested_tools = [_tool_key(item) for item in skill.get("allowedTools") or []]
    effective_tools = [tool for tool in requested_tools if _permission_allows_tool(tool, granted)]
    blocked_tools = [tool for tool in requested_tools if tool not in effective_tools]
    compiled_prompt_lines = [
        f"Skill: {skill['displayName']}",
        f"Objective: {skill['objective'] or 'Project-specific assistance.'}",
        f"Instructions: {skill['instructions'] or 'Follow the project skill objective.'}",
    ]
    if skill["limits"]:
        compiled_prompt_lines.append(f"Limits: {skill['limits']}")
    if effective_tools:
        compiled_prompt_lines.append(f"Allowed tools: {', '.join(effective_tools)}")
    return {
        "skillManagerVersion": COGNIX_SKILL_MANAGER_VERSION,
        "runtimeBinderVersion": COGNIX_SKILL_RUNTIME_BINDER_VERSION,
        "promptBuilderVersion": COGNIX_SKILL_PROMPT_BUILDER_VERSION,
        "permissionBinderVersion": COGNIX_SKILL_PERMISSION_BINDER_VERSION,
        "mode": "project_skill_binding_plan",
        "username": username,
        "projectId": project_id,
        "skill": skill,
        "binding": {
            "projectId": project_id,
            "modelId": skill.get("modelId"),
            "requestedTools": requested_tools,
            "effectiveAllowedTools": effective_tools,
            "blockedTools": blocked_tools,
            "compiledPrompt": "\n".join(compiled_prompt_lines),
            "contextInjectionAllowed": True,
            "permissionEscalationBlocked": bool(blocked_tools),
        },
        "validation": {
            "valid": bool(skill["displayName"] and (skill["objective"] or skill["instructions"])),
            "missingFields": [
                field
                for field, value in (("displayName", skill["displayName"]), ("objectiveOrInstructions", skill["objective"] or skill["instructions"]))
                if not value
            ],
        },
        "sideEffects": build_project_skill_blueprint()["sideEffects"],
    }


def build_skill_injection_plan(
    *,
    username: str,
    project_id: str,
    skills: list[dict[str, Any]],
    model_id: str | None = None,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    granted = {str(item).strip().lower() for item in (granted_permissions or set()) if str(item).strip()}
    selected: list[dict[str, Any]] = []
    blocked_tools: dict[str, list[str]] = {}
    for item in skills:
        if model_id and item.get("modelId") not in (None, "", model_id):
            continue
        requested = [_tool_key(tool) for tool in (item.get("allowedTools") or [])]
        effective = [tool for tool in requested if _permission_allows_tool(tool, granted)]
        blocked = [tool for tool in requested if tool not in effective]
        if blocked:
            blocked_tools[str(item.get("id") or item.get("skillId") or item.get("displayName"))] = blocked
        selected.append(
            {
                "skillId": item.get("skillId") or item.get("id"),
                "displayName": item.get("displayName"),
                "modelId": item.get("modelId"),
                "compiledPrompt": item.get("compiledPrompt") or item.get("instructions") or "",
                "effectiveAllowedTools": effective,
            }
        )
    return {
        "runtimeBinderVersion": COGNIX_SKILL_RUNTIME_BINDER_VERSION,
        "promptBuilderVersion": COGNIX_SKILL_PROMPT_BUILDER_VERSION,
        "permissionBinderVersion": COGNIX_SKILL_PERMISSION_BINDER_VERSION,
        "mode": "project_skill_injection_plan",
        "username": username,
        "projectId": project_id,
        "modelId": model_id,
        "selectedSkills": selected,
        "blockedTools": blocked_tools,
        "summary": {
            "selectedSkillCount": len(selected),
            "blockedToolCount": sum(len(items) for items in blocked_tools.values()),
            "permissionEscalationAllowed": False,
        },
        "sideEffects": build_project_skill_blueprint()["sideEffects"],
    }


def build_project_directive_blueprint() -> dict[str, Any]:
    return {
        "directiveManagerVersion": COGNIX_DIRECTIVE_MANAGER_VERSION,
        "directiveCompilerVersion": COGNIX_DIRECTIVE_COMPILER_VERSION,
        "promptPolicyEngineVersion": COGNIX_PROMPT_POLICY_ENGINE_VERSION,
        "services": ["DirectiveManager", "DirectiveCompiler", "PromptPolicyEngine"],
        "tables": DIRECTIVE_TABLES,
        "directiveTypes": list(DIRECTIVE_TYPES),
        "conflictOrder": ["security", "organization", "project", "user", "model_preference"],
        "policies": {
            "projectScoped": True,
            "modelScopedDirectives": True,
            "securityDirectivesWinConflicts": True,
            "compiledServerSide": True,
            "frontendDirectModelCallAllowed": False,
        },
        "sideEffects": {
            "directiveWrite": False,
            "projectBindingWrite": False,
            "modelBindingWrite": False,
            "promptPolicyMutation": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


def normalize_directive(payload: dict[str, Any] | None, *, project_id: str, username: str) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    directive_type = _safe_key(source.get("directiveType") or source.get("type"), "style")
    if directive_type not in DIRECTIVE_TYPES:
        directive_type = "style"
    source_level = _safe_key(source.get("sourceLevel") or source.get("level"), "project")
    if source_level not in SOURCE_LEVEL_RANK:
        source_level = "project"
    content = _normalize(source.get("content") or source.get("text"), 3000)
    priority = int(source.get("priority") or 50)
    priority = max(0, min(priority, 100))
    directive = {
        "schemaVersion": "cognix_project_directive_v1",
        "directiveKey": _safe_key(source.get("directiveKey") or content[:80] or directive_type, "directive"),
        "directiveType": directive_type,
        "content": content,
        "priority": priority,
        "scope": _safe_key(source.get("scope"), "project"),
        "modelId": _normalize(source.get("modelId"), 240) or None,
        "sourceLevel": source_level,
        "projectId": project_id,
        "createdBy": username,
    }
    return directive


def build_project_directive_plan(
    *,
    username: str,
    project_id: str,
    directive_config: dict[str, Any] | None,
    model_id: str | None = None,
) -> dict[str, Any]:
    directive = normalize_directive(directive_config, project_id = project_id, username = username)
    if model_id:
        directive["modelId"] = _normalize(model_id, 240)
    conflict_rank = SOURCE_LEVEL_RANK.get(str(directive["sourceLevel"]), 30)
    return {
        "directiveManagerVersion": COGNIX_DIRECTIVE_MANAGER_VERSION,
        "directiveCompilerVersion": COGNIX_DIRECTIVE_COMPILER_VERSION,
        "promptPolicyEngineVersion": COGNIX_PROMPT_POLICY_ENGINE_VERSION,
        "mode": "project_directive_plan",
        "username": username,
        "projectId": project_id,
        "directive": directive,
        "validation": {
            "valid": bool(directive["content"]),
            "missingFields": [] if directive["content"] else ["content"],
        },
        "conflictPolicy": {
            "order": ["security", "organization", "project", "user", "model_preference"],
            "sourceLevel": directive["sourceLevel"],
            "conflictRank": conflict_rank,
            "priority": directive["priority"],
        },
        "sideEffects": build_project_directive_blueprint()["sideEffects"],
    }


def compile_project_directives(
    *,
    username: str,
    project_id: str,
    directives: list[dict[str, Any]],
    model_id: str | None = None,
) -> dict[str, Any]:
    applicable = [
        item
        for item in directives
        if not model_id or item.get("modelId") in (None, "", model_id)
    ]
    ordered = sorted(
        applicable,
        key = lambda item: (
            SOURCE_LEVEL_RANK.get(str(item.get("sourceLevel") or "project"), 30),
            int(item.get("priority") or 50),
            str(item.get("updated_at") or item.get("created_at") or ""),
        ),
        reverse = True,
    )
    compiled_lines: list[str] = []
    seen_conflict_types: set[str] = set()
    conflicts: list[dict[str, Any]] = []
    for item in ordered:
        directive_type = str(item.get("directiveType") or item.get("directive_type") or "style")
        content = _normalize(item.get("content"), 3000)
        if not content:
            directive = item.get("directive") if isinstance(item.get("directive"), dict) else {}
            content = _normalize(directive.get("content"), 3000)
        if not content:
            continue
        if directive_type in seen_conflict_types and directive_type in {"security", "privacy", "tools", "model"}:
            conflicts.append({"directiveType": directive_type, "ignoredDirectiveId": item.get("directiveId") or item.get("id")})
            continue
        seen_conflict_types.add(directive_type)
        compiled_lines.append(f"[{directive_type}] {content}")
    return {
        "directiveCompilerVersion": COGNIX_DIRECTIVE_COMPILER_VERSION,
        "promptPolicyEngineVersion": COGNIX_PROMPT_POLICY_ENGINE_VERSION,
        "mode": "project_directive_compile_plan",
        "username": username,
        "projectId": project_id,
        "modelId": model_id,
        "compiledDirectives": compiled_lines,
        "promptPolicy": "\n".join(compiled_lines),
        "conflicts": conflicts,
        "summary": {
            "inputDirectiveCount": len(directives),
            "applicableDirectiveCount": len(applicable),
            "compiledDirectiveCount": len(compiled_lines),
            "conflictCount": len(conflicts),
        },
        "sideEffects": build_project_directive_blueprint()["sideEffects"],
    }
