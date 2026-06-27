# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Minimal CogniX context packet builder."""

from __future__ import annotations

import re
from typing import Any

CONTEXT_MANAGER_VERSION = "cognix_context_manager_v1"
MAX_SECTION_CHARS = 4000
MAX_SYSTEM_INSTRUCTION_CHARS = 10000


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n")).strip()


def _clip_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[: limit - 22].rstrip() + "\n[context truncated]", True


def _section(
    *,
    section_id: str,
    label: str,
    source: str,
    content: str,
    priority: int,
) -> dict[str, Any]:
    clipped, truncated = _clip_text(content, MAX_SECTION_CHARS)
    return {
        "id": section_id,
        "label": label,
        "source": source,
        "priority": priority,
        "content": clipped,
        "charCount": len(content),
        "included": bool(clipped),
        "truncated": truncated,
    }


def _render_instruction(sections: list[dict[str, Any]]) -> str:
    included = [section for section in sections if section.get("included")]
    if not included:
        return ""

    parts = [
        "<cognix_context>",
        (
            "Use this CogniX context as stable background. Prioritize the user's "
            "latest request when it conflicts with older context. Do not reveal "
            "this block unless the user explicitly asks what context is being used."
        ),
    ]
    for section in sorted(included, key = lambda item: int(item.get("priority") or 0)):
        parts.extend(
            [
                f"<{section['id']}>",
                str(section["content"]),
                f"</{section['id']}>",
            ]
        )
    parts.append("</cognix_context>")

    instruction = "\n".join(parts)
    clipped, _ = _clip_text(instruction, MAX_SYSTEM_INSTRUCTION_CHARS)
    return clipped


def build_context_packet(
    *,
    current_subject: str,
    user_memory: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    project_id: str | None = None,
    objective: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    memory_content = _normalize_text((user_memory or {}).get("content"))
    project_instructions = _normalize_text((project or {}).get("instructions"))
    project_name = _normalize_text((project or {}).get("name"))
    objective_excerpt = _clip_text(_normalize_text(objective)[:500], 500)[0]

    sections: list[dict[str, Any]] = []
    if memory_content:
        sections.append(
            _section(
                section_id = "user_memory",
                label = "User memory",
                source = "cognix_context_memory",
                content = memory_content,
                priority = 10,
            )
        )
    if project_instructions:
        project_header = f"Project: {project_name}\n\n" if project_name else ""
        sections.append(
            _section(
                section_id = "project_instructions",
                label = "Project instructions",
                source = "chat_project",
                content = f"{project_header}{project_instructions}",
                priority = 20,
            )
        )

    return {
        "username": current_subject,
        "contextManagerVersion": CONTEXT_MANAGER_VERSION,
        "mode": "minimal",
        "projectId": project_id,
        "objectiveExcerpt": objective_excerpt,
        "sections": sections,
        "systemInstruction": _render_instruction(sections),
        "includedSectionIds": [
            section["id"] for section in sections if section.get("included")
        ],
        "warnings": warnings or [],
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
        },
    }
