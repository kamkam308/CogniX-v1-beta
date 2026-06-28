# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Project DNA planning.

Project DNA captures a project's stable identity and prepares a context
injection plan without loading models, generating text, or mutating prompts
outside the normal Context Manager flow.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_PROJECT_DNA_SERVICE_VERSION = "cognix_project_dna_service_v1"
COGNIX_PROJECT_PROFILE_BUILDER_VERSION = "cognix_project_profile_builder_v1"
COGNIX_CONTEXT_INJECTOR_VERSION = "cognix_context_injector_v1"

DNA_SECTION_IDS = [
    "objective",
    "context",
    "response_style",
    "preferred_models",
    "allowed_tools",
    "constraints",
    "decisions",
]


def _normalize_text(value: Any, limit: int = 4000) -> str:
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n")).strip()
    return normalized[:limit]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_list(value: Any, limit: int = 20) -> list[str]:
    items: list[str] = []
    for item in _as_list(value)[:limit]:
        if isinstance(item, str):
            text = _normalize_text(item, 600)
        elif isinstance(item, dict):
            text = _normalize_text(item.get("label") or item.get("title") or item.get("value"), 600)
        else:
            text = ""
        if text:
            items.append(text)
    return list(dict.fromkeys(items))


def _model_list(value: Any) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for item in _as_list(value)[:12]:
        if isinstance(item, str):
            model_id = item.strip()
            label = model_id
        elif isinstance(item, dict):
            model_id = str(item.get("modelId") or item.get("id") or "").strip()
            label = str(item.get("label") or item.get("name") or model_id).strip()
        else:
            continue
        if model_id:
            models.append({"modelId": model_id[:240], "label": (label or model_id)[:240]})
    return models


def _tool_list(value: Any) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for item in _as_list(value)[:24]:
        if isinstance(item, str):
            tool_id = item.strip().lower()
            label = tool_id
        elif isinstance(item, dict):
            tool_id = str(item.get("toolId") or item.get("id") or "").strip().lower()
            label = str(item.get("label") or item.get("name") or tool_id).strip()
        else:
            continue
        if tool_id:
            tools.append({"toolId": tool_id[:120], "label": (label or tool_id)[:160]})
    return tools


def _decision_list(value: Any) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for index, item in enumerate(_as_list(value)[:40]):
        if isinstance(item, str):
            title = _normalize_text(item, 240)
            rationale = ""
            status = "active"
        elif isinstance(item, dict):
            title = _normalize_text(item.get("title") or item.get("decision") or item.get("label"), 240)
            rationale = _normalize_text(item.get("rationale") or item.get("reason") or item.get("notes"), 2000)
            status = str(item.get("status") or "active")[:80]
        else:
            continue
        if title:
            decisions.append(
                {
                    "decisionKey": f"decision_{index + 1}",
                    "title": title,
                    "rationale": rationale,
                    "status": status,
                }
            )
    return decisions


def _dna_hash(project_id: str | None, profile: dict[str, Any]) -> str:
    seed = "|".join(
        [
            project_id or "",
            profile.get("objective", ""),
            profile.get("responseStyle", ""),
            ",".join(profile.get("constraints", [])),
            ",".join(item.get("title", "") for item in profile.get("decisions", [])),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _section_state(value: Any) -> str:
    if isinstance(value, str):
        return "ready" if value.strip() else "missing_optional"
    if isinstance(value, list):
        return "ready" if value else "missing_optional"
    return "missing_optional"


def build_project_dna_blueprint() -> dict[str, Any]:
    return {
        "projectDnaServiceVersion": COGNIX_PROJECT_DNA_SERVICE_VERSION,
        "profileBuilderVersion": COGNIX_PROJECT_PROFILE_BUILDER_VERSION,
        "contextInjectorVersion": COGNIX_CONTEXT_INJECTOR_VERSION,
        "services": [
            "ProjectDNAService",
            "ProjectProfileBuilder",
            "ContextInjector",
        ],
        "sections": DNA_SECTION_IDS,
        "contextManagerIntegration": {
            "channelId": "project_dna",
            "injectedBy": "ContextBuilder",
            "priority": 15,
            "rawHistoryAllowed": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "contextMutation": False,
            "projectMutation": False,
            "memoryWrite": False,
        },
    }


def build_project_profile(
    *,
    username: str,
    project_id: str,
    project: dict[str, Any] | None = None,
    objective: str | None = None,
    context: str | None = None,
    response_style: str | None = None,
    preferred_models: list[Any] | None = None,
    allowed_tools: list[Any] | None = None,
    constraints: list[Any] | None = None,
    decisions: list[Any] | None = None,
) -> dict[str, Any]:
    project = project if isinstance(project, dict) else {}
    project_name = _normalize_text(project.get("name"), 240)
    project_instructions = _normalize_text(project.get("instructions"), 4000)
    resolved_context = _normalize_text(context, 6000) or project_instructions
    profile = {
        "username": username,
        "projectId": project_id,
        "projectName": project_name,
        "objective": _normalize_text(objective, 2000),
        "context": resolved_context,
        "responseStyle": _normalize_text(response_style, 1600),
        "preferredModels": _model_list(preferred_models),
        "allowedTools": _tool_list(allowed_tools),
        "constraints": _text_list(constraints),
        "decisions": _decision_list(decisions),
    }
    ready_sections = [
        section
        for section, value in {
            "objective": profile["objective"],
            "context": profile["context"],
            "response_style": profile["responseStyle"],
            "preferred_models": profile["preferredModels"],
            "allowed_tools": profile["allowedTools"],
            "constraints": profile["constraints"],
            "decisions": profile["decisions"],
        }.items()
        if _section_state(value) == "ready"
    ]
    profile["sectionStates"] = {
        "objective": _section_state(profile["objective"]),
        "context": _section_state(profile["context"]),
        "response_style": _section_state(profile["responseStyle"]),
        "preferred_models": _section_state(profile["preferredModels"]),
        "allowed_tools": _section_state(profile["allowedTools"]),
        "constraints": _section_state(profile["constraints"]),
        "decisions": _section_state(profile["decisions"]),
    }
    profile["completion"] = {
        "readySectionCount": len(ready_sections),
        "totalSectionCount": len(DNA_SECTION_IDS),
        "readySectionIds": ready_sections,
        "score": round(len(ready_sections) / len(DNA_SECTION_IDS), 3),
    }
    profile["dnaHash"] = _dna_hash(project_id, profile)
    return profile


def build_context_injection_plan(profile: dict[str, Any]) -> dict[str, Any]:
    ready_sections = profile.get("completion", {}).get("readySectionIds", [])
    included = bool(ready_sections)
    return {
        "contextInjectorVersion": COGNIX_CONTEXT_INJECTOR_VERSION,
        "channelId": "project_dna",
        "status": "ready" if included else "missing_optional",
        "includedSectionIds": ready_sections,
        "priority": 15,
        "maxTokens": 700,
        "willInjectNow": False,
        "contextManagerCompatible": True,
        "rawHistoryAllowed": False,
        "reason": (
            "Project DNA pret pour injection compacte dans le ContextBuilder."
            if included
            else "Project DNA incomplet; aucune injection obligatoire."
        ),
    }


def build_project_dna_plan(
    *,
    username: str,
    project_id: str,
    project: dict[str, Any] | None = None,
    objective: str | None = None,
    context: str | None = None,
    response_style: str | None = None,
    preferred_models: list[Any] | None = None,
    allowed_tools: list[Any] | None = None,
    constraints: list[Any] | None = None,
    decisions: list[Any] | None = None,
) -> dict[str, Any]:
    profile = build_project_profile(
        username = username,
        project_id = project_id,
        project = project,
        objective = objective,
        context = context,
        response_style = response_style,
        preferred_models = preferred_models,
        allowed_tools = allowed_tools,
        constraints = constraints,
        decisions = decisions,
    )
    injection = build_context_injection_plan(profile)
    return {
        "projectDnaServiceVersion": COGNIX_PROJECT_DNA_SERVICE_VERSION,
        "profileBuilderVersion": COGNIX_PROJECT_PROFILE_BUILDER_VERSION,
        "contextInjectorVersion": COGNIX_CONTEXT_INJECTOR_VERSION,
        "mode": "dry_run_project_dna",
        "projectId": project_id,
        "status": "ready_for_context" if injection["status"] == "ready" else "draft",
        "profile": profile,
        "contextInjectionPlan": injection,
        "sideEffects": build_project_dna_blueprint()["sideEffects"],
    }
