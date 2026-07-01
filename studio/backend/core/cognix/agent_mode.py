# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native Agent Mode planning.

Agent Mode is interactive and project-scoped. This module plans sessions,
steps, tool calls, memory updates, progress streaming, and outputs without
executing tools, loading models, or mutating user files directly.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_AGENT_MODE_SERVICE_VERSION = "cognix_agent_mode_service_v1"
COGNIX_TASK_PLANNER_VERSION = "cognix_task_planner_v1"
COGNIX_TOOL_EXECUTION_SERVICE_VERSION = "cognix_tool_execution_service_v1"
COGNIX_AGENT_MEMORY_VERSION = "cognix_agent_memory_v1"
COGNIX_AGENT_PROGRESS_STREAMER_VERSION = "cognix_agent_progress_streamer_v1"

AGENT_MODE_SERVICES = [
    "AgentModeService",
    "TaskPlanner",
    "ToolExecutionService",
    "AgentMemory",
    "AgentProgressStreamer",
]

AGENT_MODE_TABLES = [
    "agent_sessions",
    "agent_steps",
    "agent_tool_calls",
    "agent_outputs",
]

AGENT_MODES = {"agent", "research", "automation", "repo", "course", "dataset", "documents"}
STEP_STATUSES = {"planned", "waiting_approval", "running", "blocked", "complete", "failed", "skipped"}
SENSITIVE_TOOL_KEYWORDS = {
    "write",
    "delete",
    "remove",
    "shell",
    "terminal",
    "exec",
    "email",
    "send",
    "deploy",
    "payment",
    "secret",
    "token",
    "system",
}


def _text(value: Any, limit: int = 240, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).replace("\r\n", "\n").strip()
    return " ".join(text.split())[:limit].strip()


def _multiline(value: Any, limit: int = 6000) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:limit].strip()


def _key(value: Any, fallback: str = "agent") -> str:
    text = _text(value, 180, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return cleaned.strip("-")[:160] or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:14]}"


def _normalize_mode(mode: str | None, goal: str) -> str:
    requested = _key(mode, "agent")
    if requested in AGENT_MODES:
        return requested
    lower = goal.lower()
    if any(word in lower for word in ("repo", "repository", "codebase", "bug", "tests")):
        return "repo"
    if any(word in lower for word in ("cours", "course", "lesson", "teach", "devoir")):
        return "course"
    if any(word in lower for word in ("dataset", "donnees", "data set", "csv", "jsonl")):
        return "dataset"
    if any(word in lower for word in ("document", "documents", "organise", "classer", "pdf")):
        return "documents"
    if any(word in lower for word in ("research", "recherche", "sources", "veille")):
        return "research"
    return "agent"


def _step(
    step_id: str,
    title: str,
    description: str,
    *,
    tool_candidates: list[str] | None = None,
    risk_level: str = "low",
    requires_approval: bool = False,
    memory_write: bool = False,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "description": description,
        "status": "waiting_approval" if requires_approval else "planned",
        "progressPercent": 0,
        "riskLevel": risk_level,
        "toolCandidates": tool_candidates or [],
        "requiresApproval": requires_approval,
        "memoryWritePlanned": memory_write,
        "result": "",
    }


def _steps_for_goal(goal: str, mode: str, allowed_tools: list[Any]) -> list[dict[str, Any]]:
    tool_ids = [_key(item, "") for item in allowed_tools if _key(item, "")]
    if mode == "repo":
        return [
            _step("clarify", "Clarifier l'objectif", "Identifier le repo, les criteres de reussite et les limites."),
            _step("inspect", "Inspecter le projet", "Lister les fichiers utiles et etablir une carte de travail.", tool_candidates = ["filesystem-read", "git-status"]),
            _step("plan", "Construire le plan", "Transformer l'objectif en etapes petites, verifiables et reversibles."),
            _step("execute", "Executer sous controle", "Preparer les actions de code et tests via outils autorises.", tool_candidates = tool_ids or ["codex", "terminal"], risk_level = "high", requires_approval = True),
            _step("verify", "Verifier", "Lancer ou planifier les tests pertinents et produire un compte rendu."),
        ]
    if mode == "course":
        return [
            _step("scope", "Cadrer le cours", "Identifier niveau, sujet, duree et objectifs pedagogiques."),
            _step("outline", "Structurer", "Creer le plan du cours avec progression logique."),
            _step("examples", "Preparer exemples", "Ajouter exercices, analogies et corrections."),
            _step("review", "Verifier pedagogiquement", "Controler clarte, prerequis et coherence."),
            _step("output", "Produire la sortie", "Generer le support final ou le plan d'export.", memory_write = True),
        ]
    if mode == "dataset":
        return [
            _step("define_schema", "Definir le schema", "Fixer colonnes, labels, format et criteres qualite."),
            _step("collect_sources", "Identifier les sources", "Lister documents, chats ou fichiers admissibles.", tool_candidates = ["library", "rag-indexer"]),
            _step("build_examples", "Construire exemples", "Planifier extraction, nettoyage et validation.", risk_level = "medium", requires_approval = True),
            _step("quality_gate", "Evaluer la qualite", "Detecter doublons, donnees sensibles et biais."),
            _step("export_plan", "Preparer export", "Produire un plan d'export sans ecrire de fichier directement.", memory_write = True),
        ]
    if mode == "documents":
        return [
            _step("inventory", "Inventorier", "Identifier documents, types, tailles et priorites.", tool_candidates = ["library", "filesystem-read"]),
            _step("classify", "Classer", "Proposer collections, tags et rattachements projet."),
            _step("rag_plan", "Preparer RAG", "Planifier indexation et citations sans lancer d'indexation ici.", tool_candidates = ["rag-indexer"], risk_level = "medium", requires_approval = True),
            _step("cleanup", "Nettoyer", "Detecter doublons et elements obsoletes."),
            _step("report", "Compte rendu", "Resumer les decisions et prochaines actions."),
        ]
    if mode == "research":
        return [
            _step("question", "Formuler la question", "Transformer l'objectif en questions verifiables."),
            _step("sources", "Planifier les sources", "Identifier sources internes/externes et limites.", tool_candidates = ["web-search", "library"], risk_level = "medium", requires_approval = True),
            _step("compare", "Comparer les informations", "Distinguer faits, hypotheses et inconnues."),
            _step("synthesize", "Synthese", "Produire une synthese structuree et sourcer les points critiques."),
        ]
    return [
        _step("clarify", "Clarifier l'objectif", "Identifier les criteres de reussite et les contraintes."),
        _step("plan", "Decomposer", "Transformer l'objectif en etapes actionnables."),
        _step("prepare_tools", "Preparer les outils", "Selectionner les outils autorises avant execution.", tool_candidates = tool_ids),
        _step("execute_guarded", "Executer sous garde", "Executer seulement apres permission si une action est sensible.", risk_level = "medium", requires_approval = bool(tool_ids)),
        _step("final_report", "Compte rendu", "Verifier le resultat et produire une conclusion utile.", memory_write = True),
    ]


def _is_sensitive_tool(tool_id: str, action: str, arguments: dict[str, Any] | None) -> bool:
    haystack = " ".join([tool_id, action, " ".join(str(key) for key in _as_dict(arguments).keys())]).lower()
    return any(keyword in haystack for keyword in SENSITIVE_TOOL_KEYWORDS)


def build_agent_mode_blueprint() -> dict[str, Any]:
    return {
        "agentModeServiceVersion": COGNIX_AGENT_MODE_SERVICE_VERSION,
        "taskPlannerVersion": COGNIX_TASK_PLANNER_VERSION,
        "toolExecutionServiceVersion": COGNIX_TOOL_EXECUTION_SERVICE_VERSION,
        "agentMemoryVersion": COGNIX_AGENT_MEMORY_VERSION,
        "agentProgressStreamerVersion": COGNIX_AGENT_PROGRESS_STREAMER_VERSION,
        "mode": "native_agent_mode_contract",
        "services": AGENT_MODE_SERVICES,
        "tables": AGENT_MODE_TABLES,
        "capabilities": [
            "task_decomposition",
            "agent_step_tracking",
            "guarded_tool_call_planning",
            "agent_memory_update_plan",
            "progress_streaming_contract",
            "final_report_output",
        ],
        "securityPolicy": {
            "humanConfirmationForSensitiveTools": True,
            "permissionGateRequired": True,
            "directToolExecutionAllowed": False,
            "frontendDirectModelCallAllowed": False,
            "projectBoundaryRequired": True,
            "memoryWriteRequiresPlan": True,
        },
        "sideEffects": {
            "sessionWrite": False,
            "stepWrite": False,
            "toolCallWrite": False,
            "outputWrite": False,
            "memoryWrite": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "fileWrite": False,
            "secretRead": False,
            "auditWrite": False,
        },
    }


def build_agent_session_plan(
    *,
    username: str,
    goal: str,
    mode: str | None = None,
    project_id: str | None = None,
    allowed_tools: list[Any] | None = None,
    memory_policy: dict[str, Any] | None = None,
    max_steps: int = 8,
) -> dict[str, Any]:
    normalized_goal = _multiline(goal, 4000)
    normalized_mode = _normalize_mode(mode, normalized_goal)
    tools = [_key(item, "") for item in _as_list(allowed_tools) if _key(item, "")]
    steps = _steps_for_goal(normalized_goal, normalized_mode, tools)[: max(1, min(int(max_steps or 8), 20))]
    memory = _as_dict(memory_policy)
    return {
        "agentModeServiceVersion": COGNIX_AGENT_MODE_SERVICE_VERSION,
        "taskPlannerVersion": COGNIX_TASK_PLANNER_VERSION,
        "agentMemoryVersion": COGNIX_AGENT_MEMORY_VERSION,
        "agentProgressStreamerVersion": COGNIX_AGENT_PROGRESS_STREAMER_VERSION,
        "mode": "native_agent_session_plan",
        "username": _text(username, 160),
        "projectId": _text(project_id, 160) or None,
        "valid": bool(normalized_goal),
        "agent": {
            "goal": normalized_goal,
            "mode": normalized_mode,
            "status": "planned",
            "progressPercent": 0,
            "stepCount": len(steps),
            "allowedTools": tools,
        },
        "steps": steps,
        "memoryPlan": {
            "enabled": bool(memory.get("enabled", True)),
            "writeDuringRun": bool(memory.get("writeDuringRun", False)),
            "writeAtEnd": bool(memory.get("writeAtEnd", True)),
            "requiresReview": True,
            "memoryWriteNow": False,
        },
        "progressStream": {
            "streamEvents": ["session_created", "step_updated", "tool_call_planned", "output_created"],
            "transport": "server_events_or_polling",
            "willStreamNow": False,
        },
        "sideEffects": build_agent_mode_blueprint()["sideEffects"],
    }


def build_agent_step_update_plan(
    *,
    username: str,
    session: dict[str, Any],
    step_id: str,
    status: str,
    result: str | None = None,
    progress_percent: int | None = None,
) -> dict[str, Any]:
    normalized_status = _key(status, "planned")
    if normalized_status not in STEP_STATUSES:
        normalized_status = "planned"
    progress = max(0, min(int(progress_percent if progress_percent is not None else 0), 100))
    return {
        "agentModeServiceVersion": COGNIX_AGENT_MODE_SERVICE_VERSION,
        "agentProgressStreamerVersion": COGNIX_AGENT_PROGRESS_STREAMER_VERSION,
        "mode": "native_agent_step_update_plan",
        "username": _text(username, 160),
        "sessionId": _text(session.get("id") or session.get("sessionId"), 160),
        "step": {
            "id": _text(step_id, 160),
            "status": normalized_status,
            "result": _multiline(result, 4000),
            "progressPercent": progress,
        },
        "progressStream": {"event": "step_updated", "willStreamNow": False},
        "sideEffects": build_agent_mode_blueprint()["sideEffects"],
    }


def build_agent_tool_call_plan(
    *,
    username: str,
    session: dict[str, Any],
    tool_id: str,
    action: str,
    arguments: dict[str, Any] | None = None,
    step_id: str | None = None,
    approved: bool = False,
) -> dict[str, Any]:
    normalized_tool = _key(tool_id, "tool")
    normalized_action = _key(action, "plan")
    sensitive = _is_sensitive_tool(normalized_tool, normalized_action, arguments)
    return {
        "agentModeServiceVersion": COGNIX_AGENT_MODE_SERVICE_VERSION,
        "toolExecutionServiceVersion": COGNIX_TOOL_EXECUTION_SERVICE_VERSION,
        "mode": "native_agent_tool_call_plan",
        "username": _text(username, 160),
        "sessionId": _text(session.get("id") or session.get("sessionId"), 160),
        "stepId": _text(step_id, 160) or None,
        "toolCall": {
            "id": _stable_id("tool", session.get("id"), step_id, normalized_tool, normalized_action),
            "toolId": normalized_tool,
            "action": normalized_action,
            "arguments": _as_dict(arguments),
            "riskLevel": "high" if sensitive else "low",
            "requiresApproval": sensitive,
            "approved": bool(approved),
            "willExecuteNow": False,
            "status": "approved_for_executor" if approved and not sensitive else "approval_required" if sensitive else "planned",
        },
        "blockedActions": ["direct_tool_execution", "frontend_tool_execution"]
        + ([] if approved or not sensitive else ["sensitive_tool_without_confirmation"]),
        "sideEffects": build_agent_mode_blueprint()["sideEffects"],
    }


def build_agent_output_plan(
    *,
    username: str,
    session: dict[str, Any],
    content: str,
    output_type: str = "final_report",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_output_type = _key(output_type, "final_report")
    return {
        "agentModeServiceVersion": COGNIX_AGENT_MODE_SERVICE_VERSION,
        "agentMemoryVersion": COGNIX_AGENT_MEMORY_VERSION,
        "mode": "native_agent_output_plan",
        "username": _text(username, 160),
        "sessionId": _text(session.get("id") or session.get("sessionId"), 160),
        "valid": bool(_multiline(content, 12000)),
        "output": {
            "type": normalized_output_type,
            "content": _multiline(content, 12000),
            "metadata": _as_dict(metadata),
            "memoryCandidate": normalized_output_type in {"final_report", "summary", "decision"},
            "memoryWriteNow": False,
        },
        "sideEffects": build_agent_mode_blueprint()["sideEffects"],
    }
