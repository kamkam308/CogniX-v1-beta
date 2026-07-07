# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX central memory manager planning.

CogniX memory must be independent from any specialized model. This module
declares the memory layers and plans how memory should be read, summarized,
written, or withheld without mutating storage, retrieving documents, or calling
a model.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_MEMORY_MANAGER_VERSION = "cognix_memory_manager_v1"


MEMORY_LAYERS: list[dict[str, Any]] = [
    {
        "id": "user_memory",
        "label": "Memoire utilisateur",
        "scope": "user",
        "purpose": "preferences_niveau_style_objectifs",
        "source": "cognix_context_memory",
        "retention": "until_user_edits_or_deletes",
        "sensitivity": "personal",
        "defaultPriority": 10,
    },
    {
        "id": "project_memory",
        "label": "Memoire projet",
        "scope": "project",
        "purpose": "instructions_decisions_resume_projet",
        "source": "chat_project",
        "retention": "project_lifetime",
        "sensitivity": "project",
        "defaultPriority": 20,
    },
    {
        "id": "conversation_summary",
        "label": "Resume conversation",
        "scope": "conversation",
        "purpose": "compacter_anciens_messages",
        "source": "conversation_summary",
        "retention": "thread_lifetime",
        "sensitivity": "conversation",
        "defaultPriority": 30,
    },
    {
        "id": "document_memory",
        "label": "Memoire documentaire",
        "scope": "document",
        "purpose": "documents_chunks_citations",
        "source": "library_and_rag",
        "retention": "document_lifetime",
        "sensitivity": "document",
        "defaultPriority": 40,
    },
    {
        "id": "organization_memory",
        "label": "Memoire organisation",
        "scope": "organization",
        "purpose": "regles_roles_permissions",
        "source": "governance_policy",
        "retention": "organization_policy_lifetime",
        "sensitivity": "restricted",
        "defaultPriority": 50,
    },
    {
        "id": "technical_memory",
        "label": "Memoire technique",
        "scope": "technical",
        "purpose": "materiel_modeles_performances_observees",
        "source": "hardware_benchmark_registry",
        "retention": "rolling_observations",
        "sensitivity": "technical",
        "defaultPriority": 60,
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _objective_excerpt(value: Any) -> str:
    return _normalize_text(value)[:500]


def _layer(layer_id: str) -> dict[str, Any]:
    for item in MEMORY_LAYERS:
        if item["id"] == layer_id:
            return item
    return {}


def _memory_chars(value: dict[str, Any] | None) -> int:
    return len(str(_as_dict(value).get("content") or ""))


def _project_has_memory(project: dict[str, Any] | None) -> bool:
    project_data = _as_dict(project)
    return bool(project_data.get("name") or project_data.get("instructions"))


def _document_count(library_items: list[dict[str, Any]] | None) -> int:
    return len([item for item in _as_list(library_items) if isinstance(item, dict)])


def _technical_status(hardware: dict[str, Any] | None, latest_benchmark_run: dict[str, Any] | None) -> str:
    if hardware and latest_benchmark_run:
        return "ready"
    if hardware:
        return "partial"
    return "missing"


def _memory_record(
    *,
    layer_id: str,
    status: str,
    available: bool,
    required: bool,
    evidence: dict[str, Any],
    action: str,
    reason: str,
) -> dict[str, Any]:
    layer = _layer(layer_id)
    return {
        "id": layer_id,
        "label": layer.get("label"),
        "scope": layer.get("scope"),
        "source": layer.get("source"),
        "purpose": layer.get("purpose"),
        "retention": layer.get("retention"),
        "sensitivity": layer.get("sensitivity"),
        "priority": layer.get("defaultPriority"),
        "status": status,
        "available": available,
        "required": required,
        "evidence": evidence,
        "plannedAction": action,
        "reason": reason,
        "willRead": False,
        "willWrite": False,
        "willSummarize": False,
        "willRetrieve": False,
    }


def build_memory_blueprint() -> dict[str, Any]:
    return {
        "memoryManagerVersion": COGNIX_MEMORY_MANAGER_VERSION,
        "mode": "declarative_dry_run",
        "layers": [dict(item) for item in MEMORY_LAYERS],
        "globalPolicies": {
            "memoryIsModelIndependent": True,
            "contextManagerConsumesMemoryPlan": True,
            "rawConversationHistoryDisallowedByDefault": True,
            "userCanEditUserMemory": True,
            "projectMemoryScopedToOwnerOrCollaborator": True,
            "organizationMemoryRequiresRolePolicy": True,
            "documentMemoryRequiresRagPermissions": True,
            "technicalMemoryNeverContainsSecrets": True,
        },
        "summary": {
            "layerCount": len(MEMORY_LAYERS),
            "persistentLayerIds": ["user_memory", "project_memory", "organization_memory", "technical_memory"],
            "ephemeralLayerIds": ["conversation_summary"],
            "retrievalLayerIds": ["document_memory"],
            "frontendDirectMemoryMutationAllowed": False,
        },
        "sideEffects": {
            "memoryWrite": False,
            "summaryWrite": False,
            "documentRetrieval": False,
            "ragIndexing": False,
            "organizationPolicyRead": False,
            "technicalProfileWrite": False,
        },
    }


def build_memory_plan(
    *,
    username: str,
    objective: str | None = None,
    project_id: str | None = None,
    project_type: str | None = None,
    user_memory: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    conversation_summary: str | None = None,
    recent_message_count: int = 0,
    library_items: list[dict[str, Any]] | None = None,
    hardware: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    classification: dict[str, Any] | None = None,
    task_strategy: dict[str, Any] | None = None,
    context_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    classification = _as_dict(classification)
    task_strategy = _as_dict(task_strategy)
    context_plan = _as_dict(context_plan)
    objective_text = _objective_excerpt(objective)
    memory_chars = _memory_chars(user_memory)
    project_ready = _project_has_memory(project)
    summary_ready = bool(_normalize_text(conversation_summary))
    docs_count = _document_count(library_items)
    needs_rag = task_strategy.get("path") == "rag_first"
    long_conversation = recent_message_count > 8
    technical_status = _technical_status(hardware, latest_benchmark_run)

    layers = [
        _memory_record(
            layer_id = "user_memory",
            status = "ready" if memory_chars else "missing_optional",
            available = bool(memory_chars),
            required = False,
            evidence = {"charCount": memory_chars},
            action = "reuse_existing_user_memory" if memory_chars else "offer_user_memory_capture",
            reason = "Preferences utilisateur disponibles." if memory_chars else "Aucune memoire utilisateur stable disponible.",
        ),
        _memory_record(
            layer_id = "project_memory",
            status = "ready" if project_ready else "missing_optional" if project_id else "not_scoped",
            available = project_ready,
            required = bool(project_id or project_type),
            evidence = {
                "projectId": project_id,
                "hasName": bool(_as_dict(project).get("name")),
                "hasInstructions": bool(_as_dict(project).get("instructions")),
            },
            action = "reuse_project_memory" if project_ready else "prepare_project_summary_slot",
            reason = "Memoire projet disponible." if project_ready else "Projet detecte mais contexte projet incomplet.",
        ),
        _memory_record(
            layer_id = "conversation_summary",
            status = "ready" if summary_ready else "recommended" if long_conversation else "optional",
            available = summary_ready,
            required = long_conversation,
            evidence = {"recentMessageCount": recent_message_count, "summaryChars": len(_normalize_text(conversation_summary))},
            action = "reuse_conversation_summary" if summary_ready else "summarize_old_turns" if long_conversation else "keep_recent_messages_capped",
            reason = "Resume conversation disponible." if summary_ready else "Conversation longue a compacter." if long_conversation else "Messages recents suffisants.",
        ),
        _memory_record(
            layer_id = "document_memory",
            status = "ready" if docs_count else "needs_index_or_retrieval" if needs_rag else "optional",
            available = bool(docs_count),
            required = bool(needs_rag),
            evidence = {"libraryItemCount": docs_count, "ragRecommended": bool(needs_rag)},
            action = "prepare_rag_retrieval_plan" if needs_rag else "keep_documents_available",
            reason = "Documents disponibles; retrieval RAG reste planifie." if docs_count else "Aucun document memoire disponible.",
        ),
        _memory_record(
            layer_id = "organization_memory",
            status = "planned_not_loaded",
            available = False,
            required = False,
            evidence = {"organizationScoped": False},
            action = "respect_governance_boundaries",
            reason = "Memoire organisation reservee aux editions gouvernance/education/enterprise.",
        ),
        _memory_record(
            layer_id = "technical_memory",
            status = technical_status,
            available = technical_status in {"ready", "partial"},
            required = True,
            evidence = {
                "hardwareKnown": bool(hardware),
                "benchmarkKnown": bool(latest_benchmark_run),
            },
            action = "reuse_hardware_and_benchmark_observations",
            reason = "Profil technique utilise pour limiter le contexte et les modeles.",
        ),
    ]

    warnings: list[str] = []
    if long_conversation and not summary_ready:
        warnings.append("Conversation longue: resume requis avant injection au modele.")
    if needs_rag and not docs_count:
        warnings.append("RAG recommande mais aucun document memoire n'est disponible.")
    if classification.get("needsClarification"):
        warnings.append("Domaine ambigu: ne pas enrichir la memoire avant clarification.")
    if not memory_chars and not project_ready and not docs_count:
        warnings.append("Memoire minimale: privilegier la demande courante et eviter l'historique brut.")

    return {
        "memoryManagerVersion": COGNIX_MEMORY_MANAGER_VERSION,
        "mode": "dry_run",
        "username": username,
        "objectiveExcerpt": objective_text,
        "projectId": project_id,
        "projectType": project_type,
        "targetDomain": classification.get("selectedDomain") or "general",
        "recommendedPath": task_strategy.get("path") or "expert_chat",
        "layers": layers,
        "readyLayerIds": [item["id"] for item in layers if item.get("status") in {"ready", "partial"}],
        "requiredLayerIds": [item["id"] for item in layers if item.get("required")],
        "contextBridge": {
            "contextManagerVersion": context_plan.get("contextManagerVersion"),
            "assemblyStrategy": context_plan.get("assemblyStrategy"),
            "includedChannelIds": context_plan.get("includedChannelIds", []),
            "rawHistoryAllowed": _as_dict(context_plan.get("tokenBudget")).get("rawHistoryAllowed", False),
        },
        "capturePlan": [
            {
                "id": "capture_user_preference",
                "layerId": "user_memory",
                "recommended": bool(objective_text and not memory_chars),
                "willWrite": False,
                "reason": "Capturer plus tard les preferences stables, jamais pendant le dry-run.",
            },
            {
                "id": "summarize_conversation",
                "layerId": "conversation_summary",
                "recommended": bool(long_conversation and not summary_ready),
                "willSummarize": False,
                "willWrite": False,
                "reason": "Compacter les anciens tours avant tout envoi modele.",
            },
            {
                "id": "prepare_document_memory",
                "layerId": "document_memory",
                "recommended": bool(needs_rag),
                "willRetrieve": False,
                "willIndex": False,
                "reason": "RAG reste planifie jusqu'a execution explicite.",
            },
        ],
        "privacyPlan": {
            "rawHistoryAllowed": False,
            "sendOnlySelectedMemory": True,
            "memoryScopesIsolated": True,
            "organizationMemoryRequiresPolicy": True,
            "documentMemoryRequiresPermission": True,
            "technicalMemorySecretsAllowed": False,
        },
        "warnings": warnings,
        "reason": "Memoire centrale CogniX planifiee par couche, independamment du modele selectionne.",
        "sideEffects": {
            "memoryWrite": False,
            "summaryWrite": False,
            "documentRetrieval": False,
            "ragIndexing": False,
            "organizationPolicyRead": False,
            "technicalProfileWrite": False,
            "modelLoad": False,
            "generation": False,
        },
    }
