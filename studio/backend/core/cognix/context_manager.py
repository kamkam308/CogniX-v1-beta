# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Minimal CogniX context packet builder."""

from __future__ import annotations

import re
from typing import Any

CONTEXT_MANAGER_VERSION = "cognix_context_manager_v1"
CONTEXT_BOUNDARY_CONTRACT_VERSION = "cognix_context_boundary_contract_v1"
MAX_SECTION_CHARS = 4000
MAX_SYSTEM_INSTRUCTION_CHARS = 10000


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _as_non_negative_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _render_project_dna(project_dna: dict[str, Any] | None) -> str:
    dna = _as_dict(project_dna)
    plan = _as_dict(dna.get("dna"))
    profile = _as_dict(plan.get("profile"))
    if not profile and dna:
        profile = {
            "objective": dna.get("objective"),
            "context": dna.get("context"),
            "responseStyle": dna.get("response_style"),
            "preferredModels": dna.get("preferredModels"),
            "allowedTools": dna.get("allowedTools"),
            "constraints": [item.get("label") for item in _as_list(dna.get("constraints")) if isinstance(item, dict)],
            "decisions": dna.get("decisions"),
        }
    if not profile:
        return ""

    lines: list[str] = []
    objective = _normalize_text(profile.get("objective"))
    context = _normalize_text(profile.get("context"))
    style = _normalize_text(profile.get("responseStyle"))
    if objective:
        lines.append(f"Objectif: {objective}")
    if context:
        lines.append(f"Contexte: {context}")
    if style:
        lines.append(f"Style de reponse: {style}")
    constraints = [str(item) for item in _as_list(profile.get("constraints")) if str(item).strip()]
    if constraints:
        lines.append("Contraintes: " + "; ".join(constraints[:8]))
    decisions = _as_list(profile.get("decisions"))
    decision_titles: list[str] = []
    for item in decisions[:8]:
        if isinstance(item, dict):
            title = _clip_text(_normalize_text(item.get("title")), 240)[0]
        else:
            title = _clip_text(_normalize_text(str(item)), 240)[0]
        if title:
            decision_titles.append(title)
    if decision_titles:
        lines.append("Decisions: " + "; ".join(decision_titles))
    return _clip_text("\n".join(lines), MAX_SECTION_CHARS)[0]


def _rag_packet_context(rag_retrieval_packet: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    packet = _as_dict(rag_retrieval_packet)
    context_block = _normalize_text(packet.get("contextBlock"))
    chunks = [item for item in _as_list(packet.get("chunks")) if isinstance(item, dict)]
    citations = [item for item in _as_list(packet.get("citations")) if isinstance(item, dict)]
    ready = bool(packet.get("readyForInjection")) and bool(context_block)
    if not context_block and chunks:
        lines: list[str] = []
        for index, chunk in enumerate(chunks, start = 1):
            citation_id = str(chunk.get("citationId") or f"S{index}")
            content = _normalize_text(chunk.get("content"))
            if content:
                lines.append(f"[{citation_id}] {content}")
        context_block = "\n\n".join(lines)
        ready = bool(context_block)
    return context_block, {
        "retrievalPacketVersion": packet.get("retrievalPacketVersion"),
        "plannerVersion": packet.get("plannerVersion"),
        "readyForInjection": ready,
        "selectedChunkCount": len(chunks),
        "citationCount": len(citations),
        "sourceCount": _as_dict(packet.get("summary")).get("sourceCount"),
    }


def _rag_plan_from_packet(rag_retrieval_packet: dict[str, Any] | None) -> dict[str, Any]:
    packet = _as_dict(rag_retrieval_packet)
    context_block, meta = _rag_packet_context(packet)
    ready = bool(meta.get("readyForInjection")) and bool(context_block)
    if not packet:
        return {}
    return {
        "recommendedPath": "rag_first" if ready else "no_rag_needed",
        "readyForRetrieval": ready,
        "sourceReadiness": packet.get("sourceReadiness", {}),
        "retrieval": packet.get("retrieval", {}),
        "contextBudget": {
            "maxContextTokens": 3200 if ready else 0,
            "maxChunks": _as_non_negative_int(_as_dict(packet.get("retrieval")).get("topK"), 0),
        },
        "sideEffects": {
            "ragRetrieval": False,
            "embeddingGeneration": False,
            "networkModelCall": False,
        },
    }


def _channel(
    *,
    channel_id: str,
    label: str,
    source: str,
    priority: int,
    status: str,
    max_tokens: int,
    included: bool,
    required: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "id": channel_id,
        "label": label,
        "source": source,
        "priority": priority,
        "status": status,
        "included": included,
        "required": required,
        "maxTokens": max_tokens,
        "reason": reason,
    }


def _context_budget(
    *,
    task_strategy: dict[str, Any],
    recommendation: dict[str, Any],
    rag_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    rag_budget = _as_dict(_as_dict(rag_plan).get("contextBudget"))
    rag_max = _as_non_negative_int(rag_budget.get("maxContextTokens"), 0)
    memory_fit = _as_dict(recommendation.get("memoryFit"))
    memory_level = str(memory_fit.get("level") or "unknown")
    path = str(task_strategy.get("path") or "expert_chat")

    if rag_max:
        max_context_tokens = rag_max
    elif memory_level == "tight":
        max_context_tokens = 1800
    elif path == "rag_first":
        max_context_tokens = 3200
    else:
        max_context_tokens = 2400

    recent_message_limit = 4 if memory_level == "tight" else 6 if path == "rag_first" else 8
    rag_token_reserve = 0
    if path == "rag_first" or _as_dict(rag_plan).get("recommendedPath") == "rag_first":
        rag_token_reserve = min(max(700, max_context_tokens // 2), 1800)

    return {
        "maxContextTokens": max_context_tokens,
        "recentMessageLimit": recent_message_limit,
        "ragTokenReserve": rag_token_reserve,
        "memoryTokenReserve": min(360, max_context_tokens // 6),
        "projectTokenReserve": min(500, max_context_tokens // 5),
        "summaryTokenReserve": min(420, max_context_tokens // 5),
        "rawHistoryAllowed": False,
    }


def _context_boundary_contract(context_plan: dict[str, Any]) -> dict[str, Any]:
    token_budget = _as_dict(context_plan.get("tokenBudget"))
    channels = [item for item in _as_list(context_plan.get("channels")) if isinstance(item, dict)]
    included_channel_ids = [
        str(item.get("id"))
        for item in channels
        if item.get("included") and item.get("id")
    ]
    required_channel_ids = [
        str(item.get("id"))
        for item in channels
        if item.get("required") and item.get("id")
    ]
    return {
        "contractVersion": CONTEXT_BOUNDARY_CONTRACT_VERSION,
        "mode": "context_boundary_dry_run",
        "contextManagerVersion": context_plan.get("contextManagerVersion"),
        "assemblyStrategy": context_plan.get("assemblyStrategy"),
        "maxContextTokens": token_budget.get("maxContextTokens"),
        "recentMessageLimit": token_budget.get("recentMessageLimit"),
        "includedChannelIds": included_channel_ids,
        "requiredChannelIds": required_channel_ids,
        "channelStates": [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "included": bool(item.get("included")),
                "required": bool(item.get("required")),
                "maxTokens": item.get("maxTokens"),
                "source": item.get("source"),
            }
            for item in channels
        ],
        "inputPolicy": {
            "rawHistoryAllowed": bool(token_budget.get("rawHistoryAllowed")),
            "fullConversationHistoryAllowed": False,
            "uncitedRagContentAllowed": False,
            "secretValuesAllowed": False,
            "unboundedProjectFilesAllowed": False,
            "recentMessagesMustBeCapped": True,
        },
        "allowedInputs": [
            "system_instruction",
            "user_memory_summary",
            "project_dna",
            "project_memory_summary",
            "conversation_summary",
            "rag_cited_chunks",
            "recent_messages_capped",
            "current_request",
        ],
        "blockedInputs": [
            "full_raw_history",
            "uncited_rag_content",
            "secret_values",
            "unbounded_project_files",
            "frontend_assembled_prompt_override",
        ],
        "executionGate": {
            "backendContextManagerRequired": True,
            "frontendRawHistoryUploadAllowed": False,
            "memoryWriteAllowedNow": False,
            "ragRetrievalAllowedNow": False,
            "generationAllowedHere": False,
            "networkModelCallAllowed": False,
            "contextMutationAllowed": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "memoryWrite": False,
            "ragRetrieval": False,
            "contextMutation": False,
        },
    }


def build_context_plan(
    *,
    current_subject: str,
    objective: str | None = None,
    project_id: str | None = None,
    classification: dict[str, Any] | None = None,
    task_strategy: dict[str, Any] | None = None,
    recommendation: dict[str, Any] | None = None,
    rag_plan: dict[str, Any] | None = None,
    user_memory: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    project_dna: dict[str, Any] | None = None,
    conversation_summary: str | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Plan context assembly without reading extra data or calling a model."""

    task_strategy = _as_dict(task_strategy)
    recommendation = _as_dict(recommendation)
    rag_plan = _as_dict(rag_plan)
    classification = _as_dict(classification)
    budget = _context_budget(
        task_strategy = task_strategy,
        recommendation = recommendation,
        rag_plan = rag_plan,
    )

    memory_content = _normalize_text(_as_dict(user_memory).get("content"))
    project_dna_content = _render_project_dna(project_dna)
    project_instructions = _normalize_text(_as_dict(project).get("instructions"))
    project_name = _normalize_text(_as_dict(project).get("name"))
    summary_content = _normalize_text(conversation_summary)
    recent = [item for item in _as_list(recent_messages) if isinstance(item, dict)]
    objective_excerpt = _clip_text(_normalize_text(objective)[:500], 500)[0]

    path = str(task_strategy.get("path") or "expert_chat")
    rag_recommended = path == "rag_first" or rag_plan.get("recommendedPath") == "rag_first"
    rag_ready = bool(rag_plan.get("readyForRetrieval"))
    needs_summary = len(recent) > int(budget["recentMessageLimit"])

    channels = [
        _channel(
            channel_id = "user_memory",
            label = "Memoire utilisateur",
            source = "cognix_context_memory",
            priority = 10,
            status = "ready" if memory_content else "missing_optional",
            max_tokens = int(budget["memoryTokenReserve"]),
            included = bool(memory_content),
            reason = "Preferences stables utilisateur." if memory_content else "Aucune memoire utilisateur utile fournie.",
        ),
        _channel(
            channel_id = "project_dna",
            label = "Project DNA",
            source = "cognix_project_dna",
            priority = 15,
            status = "ready" if project_dna_content else "missing_optional",
            max_tokens = 700,
            included = bool(project_dna_content),
            reason = "Identite structuree du projet." if project_dna_content else "Aucun Project DNA actif.",
        ),
        _channel(
            channel_id = "project_memory",
            label = "Memoire projet",
            source = "chat_project",
            priority = 20,
            status = "ready" if project_instructions or project_name else "missing_optional",
            max_tokens = int(budget["projectTokenReserve"]),
            included = bool(project_instructions or project_name),
            reason = "Instructions projet disponibles." if project_instructions or project_name else "Aucun contexte projet disponible.",
        ),
        _channel(
            channel_id = "conversation_summary",
            label = "Resume conversation",
            source = "conversation_summary",
            priority = 30,
            status = "ready" if summary_content else "recommended" if needs_summary else "optional",
            max_tokens = int(budget["summaryTokenReserve"]),
            included = bool(summary_content),
            required = needs_summary,
            reason = "Resume compact des anciens messages." if summary_content else "Resumer les anciens tours avant injection brute.",
        ),
        _channel(
            channel_id = "rag_chunks",
            label = "Passages RAG cites",
            source = "rag_engine",
            priority = 40,
            status = "ready" if rag_ready else "blocked" if rag_recommended else "not_needed",
            max_tokens = int(budget["ragTokenReserve"]),
            included = rag_ready,
            required = rag_recommended,
            reason = "Passages documentaires prets avec citations." if rag_ready else "Retrieval non execute en planification dry-run.",
        ),
        _channel(
            channel_id = "recent_messages",
            label = "Messages recents",
            source = "conversation",
            priority = 50,
            status = "capped" if len(recent) > int(budget["recentMessageLimit"]) else "ready" if recent else "optional",
            max_tokens = max(240, int(budget["maxContextTokens"]) - int(budget["ragTokenReserve"]) - int(budget["summaryTokenReserve"])),
            included = bool(recent),
            reason = f"Limiter a {budget['recentMessageLimit']} messages recents, jamais toute l'histoire brute.",
        ),
        _channel(
            channel_id = "current_request",
            label = "Demande courante",
            source = "user_input",
            priority = 60,
            status = "ready" if objective_excerpt else "missing",
            max_tokens = 420,
            included = bool(objective_excerpt),
            required = True,
            reason = "La demande courante reste prioritaire sur tout contexte plus ancien.",
        ),
    ]

    plan_warnings = list(warnings or [])
    if rag_recommended and not rag_ready:
        plan_warnings.append("RAG requis mais aucun passage pret: ne pas halluciner de source.")
    if needs_summary and not summary_content:
        plan_warnings.append("Conversation longue: resume requis avant injection au modele.")
    if not memory_content and not project_dna_content and not project_instructions and not rag_ready:
        plan_warnings.append("Contexte minimal: reponse basee surtout sur la demande courante.")

    compression = ["never_send_raw_history"]
    if needs_summary:
        compression.append("summarize_old_turns")
    if rag_ready:
        compression.append("compress_rag_chunks_with_citations")
    if classification.get("needsClarification"):
        compression.append("defer_context_until_clarified")

    context_plan = {
        "username": current_subject,
        "contextManagerVersion": CONTEXT_MANAGER_VERSION,
        "mode": "dry_run",
        "projectId": project_id,
        "objectiveExcerpt": objective_excerpt,
        "targetDomain": classification.get("selectedDomain") or "general",
        "assemblyStrategy": "rag_augmented_context" if rag_ready else "memory_project_recent",
        "tokenBudget": budget,
        "channels": channels,
        "includedChannelIds": [
            channel["id"] for channel in channels if channel.get("included")
        ],
        "requiredChannelIds": [
            channel["id"] for channel in channels if channel.get("required")
        ],
        "compression": compression,
        "warnings": plan_warnings,
        "reason": (
            "Construire un contexte compact avec passages RAG cites et memoire utile."
            if rag_ready
            else "Construire un contexte minimal: memoire, projet, resume et demande courante."
        ),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "memoryWrite": False,
            "ragRetrieval": False,
            "contextMutation": False,
        },
    }
    context_plan["contextBoundaryContract"] = _context_boundary_contract(context_plan)
    return context_plan


def build_context_packet(
    *,
    current_subject: str,
    user_memory: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    project_dna: dict[str, Any] | None = None,
    compressed_context: dict[str, Any] | None = None,
    rag_retrieval_packet: dict[str, Any] | None = None,
    conversation_summary: str | None = None,
    project_id: str | None = None,
    objective: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    memory_content = _normalize_text((user_memory or {}).get("content"))
    project_dna_content = _render_project_dna(project_dna)
    project_instructions = _normalize_text((project or {}).get("instructions"))
    project_name = _normalize_text((project or {}).get("name"))
    compressed_context = _as_dict(compressed_context)
    summary_content = _normalize_text(
        conversation_summary
        or compressed_context.get("compressedContext")
        or compressed_context.get("compressed_context")
    )
    objective_excerpt = _clip_text(_normalize_text(objective)[:500], 500)[0]
    rag_context, rag_packet_meta = _rag_packet_context(rag_retrieval_packet)

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
    if project_dna_content:
        sections.append(
            _section(
                section_id = "project_dna",
                label = "Project DNA",
                source = "cognix_project_dna",
                content = project_dna_content,
                priority = 15,
            )
        )
    if summary_content:
        sections.append(
            _section(
                section_id = "conversation_summary",
                label = "Conversation summary",
                source = "cognix_compressed_context",
                content = summary_content,
                priority = 30,
            )
        )
    if rag_context:
        sections.append(
            _section(
                section_id = "rag_chunks",
                label = "RAG cited chunks",
                source = "cognix_rag_retrieval_packet",
                content = rag_context,
                priority = 35,
            )
        )

    context_plan = build_context_plan(
        current_subject = current_subject,
        user_memory = user_memory,
        project = project,
        project_dna = project_dna,
        conversation_summary = summary_content,
        rag_plan = _rag_plan_from_packet(rag_retrieval_packet),
        project_id = project_id,
        objective = objective,
        warnings = warnings,
    )

    compressed_context_meta: dict[str, Any] | None = None
    if compressed_context:
        compressed_context_meta = {
            "id": compressed_context.get("id"),
            "projectId": compressed_context.get("project_id") or compressed_context.get("projectId"),
            "originalTokenCount": compressed_context.get("original_token_count")
            or compressed_context.get("originalTokenCount"),
            "compressedTokenCount": compressed_context.get("compressed_token_count")
            or compressed_context.get("compressedTokenCount"),
            "reductionRatio": compressed_context.get("reduction_ratio") or compressed_context.get("reductionRatio"),
        }

    return {
        "username": current_subject,
        "contextManagerVersion": CONTEXT_MANAGER_VERSION,
        "contextBoundaryContract": context_plan.get("contextBoundaryContract"),
        "mode": "minimal",
        "projectId": project_id,
        "objectiveExcerpt": objective_excerpt,
        "compressedContext": compressed_context_meta,
        "ragPacket": rag_packet_meta if rag_retrieval_packet else None,
        "sections": sections,
        "systemInstruction": _render_instruction(sections),
        "contextPlan": context_plan,
        "includedSectionIds": [
            section["id"] for section in sections if section.get("included")
        ],
        "warnings": warnings or [],
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "memoryWrite": False,
            "ragRetrieval": False,
            "contextMutation": False,
        },
    }
