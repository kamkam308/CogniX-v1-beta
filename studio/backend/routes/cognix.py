# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX product/admin API routes."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from auth import storage as auth_storage
from auth.authentication import get_current_jwt_subject
from core.cognix import benchmark as cognix_benchmark
from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import context_manager as cognix_context_manager
from core.cognix import deployment_manager as cognix_deployment_manager
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import fine_tuning_planner as cognix_fine_tuning_planner
from core.cognix import governance_manager as cognix_governance_manager
from core.cognix import hardware as cognix_hardware
from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import memory_manager as cognix_memory_manager
from core.cognix import model_lifecycle as cognix_model_lifecycle
from core.cognix import module_registry as cognix_module_registry
from core.cognix import onboarding as cognix_onboarding
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import project_experts as cognix_project_experts
from core.cognix import rag_planner as cognix_rag_planner
from core.cognix import registry as cognix_registry
from core.cognix import recommender as cognix_recommender
from core.cognix import research_watch as cognix_research_watch
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import thinking_status as cognix_thinking_status
from core.cognix import tool_registry as cognix_tool_registry
from core.cognix import worker_queue as cognix_worker_queue
from core.cognix.router import classify_objective
from core.cognix.strategy import build_strategy
from storage import cognix_db
from storage.studio_db import get_chat_project, list_chat_messages_for_threads, list_chat_projects, list_chat_threads


router = APIRouter()


class ApprovalCreateRequest(BaseModel):
    reason: str = Field(..., min_length = 3, max_length = 2000)


class ApprovalDecisionRequest(BaseModel):
    status: Literal["pending", "approved", "denied"]
    admin_note: str | None = Field(None, max_length = 2000)


class AdminPermissionGrantRequest(BaseModel):
    permission_key: str = Field(..., min_length = 1, max_length = 160)
    expires_at: str | None = Field(None, max_length = 80)


class ReportCreateRequest(BaseModel):
    category: str = Field("general", min_length = 1, max_length = 80)
    title: str = Field(..., min_length = 3, max_length = 160)
    message: str = Field(..., min_length = 3, max_length = 4000)


class ReportStatusRequest(BaseModel):
    status: Literal["open", "in_review", "resolved", "closed"]


class BanStatusRequest(BaseModel):
    status: Literal["pending_admin_review", "active", "cleared", "permanent"]
    admin_decision: str | None = Field(None, max_length = 2000)


class ContextMemoryRequest(BaseModel):
    content: str = Field("", max_length = 120000)


class ContextPackRequest(BaseModel):
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, max_length = 160)


class MemoryPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    conversation_summary: str | None = Field(None, alias = "conversationSummary", max_length = 12000)
    recent_message_count: int = Field(0, alias = "recentMessageCount", ge = 0, le = 500)


class ResearchIntegrationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    technique_name: str | None = Field(None, alias = "techniqueName", max_length = 240)
    source_name: str | None = Field(None, alias = "sourceName", max_length = 240)
    category: str | None = Field(None, max_length = 120)
    claimed_benefit: str | None = Field(None, alias = "claimedBenefit", max_length = 1000)
    target_module: str | None = Field(None, alias = "targetModule", max_length = 160)
    risk_tolerance: str | None = Field(None, alias = "riskTolerance", max_length = 80)


class LibraryItemRequest(BaseModel):
    kind: Literal["file", "image", "video", "document", "dataset", "other"] = "other"
    name: str = Field(..., min_length = 1, max_length = 240)
    source: str = Field("manual", max_length = 80)
    size_bytes: int | None = Field(None, ge = 0)
    uri: str | None = Field(None, max_length = 2000)
    metadata: dict[str, Any] | None = None


class ScheduledTaskCreateRequest(BaseModel):
    title: str = Field(..., min_length = 1, max_length = 160)
    prompt: str = Field(..., min_length = 1, max_length = 4000)
    schedule_text: str = Field(..., min_length = 1, max_length = 160)


class ScheduledTaskStatusRequest(BaseModel):
    status: Literal["active", "paused", "done", "cancelled"]


class AppConnectionRequest(BaseModel):
    app_id: str = Field(..., min_length = 1, max_length = 80)
    app_name: str = Field(..., min_length = 1, max_length = 120)
    status: Literal["connected", "disabled"] = "connected"


class SocialMessageRequest(BaseModel):
    content: str = Field(..., min_length = 1, max_length = 2000)


class SocialAgentRequest(BaseModel):
    prompt: str | None = Field(None, max_length = 1000)


class ModelPinRequest(BaseModel):
    model_id: str = Field(..., min_length = 1, max_length = 240)
    label: str = Field(..., min_length = 1, max_length = 240)


class ModelLifecyclePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    execution_target: str | None = Field(None, alias = "executionTarget", max_length = 120)
    quality_priority: str | None = Field(None, alias = "qualityPriority", max_length = 80)
    offline_required: bool = Field(False, alias = "offlineRequired")


class ThinkingStatusPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    audience: Literal["chat", "project", "onboarding"] = "chat"


class ProjectDefaultModelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    label: str = Field(..., min_length = 1, max_length = 240)
    provider_type: str | None = Field(None, alias = "providerType", max_length = 80)
    provider_id: str | None = Field(None, alias = "providerId", max_length = 160)


class ProjectExpertPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)


class ProjectShareCreateRequest(BaseModel):
    project_id: str = Field(..., min_length = 1, max_length = 160)
    permission: Literal["view", "edit"] = "view"


class ImageRequest(BaseModel):
    prompt: str = Field(..., min_length = 1, max_length = 4000)
    model: str | None = Field(None, max_length = 160)


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length = 2, max_length = 500)


class AgentRunRequest(BaseModel):
    goal: str = Field(..., min_length = 2, max_length = 2000)
    mode: Literal["agent", "research", "automation"] = "agent"


class RouterClassifyRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)


class OnboardingPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    purpose: str | None = Field(None, max_length = 120)
    level: str | None = Field(None, max_length = 80)
    execution_target: str | None = Field(None, alias = "executionTarget", max_length = 120)
    priorities: list[str] | None = None
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)


class OrchestratorPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class PreloadPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class ModelCacheLoadPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    runtime_type: str | None = Field(None, alias = "runtimeType", max_length = 80)
    estimated_ram_gb: float | None = Field(None, alias = "estimatedRamGb", ge = 0)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)


class FineTuningPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    dataset: dict[str, Any] | None = None


class FineTuningCloudHandoffPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    target_id: str | None = Field(None, alias = "targetId", max_length = 120)
    dataset: dict[str, Any] | None = None


class RagPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None


class RagIndexingPlanRequest(BaseModel):
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None


class OptimizationPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class RuntimePlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class CodexPipelinePlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class WorkerQueuePlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None
    dataset: dict[str, Any] | None = None


class WorkerJobSpecPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None
    dataset: dict[str, Any] | None = None
    target_id: str | None = Field(None, alias = "targetId", max_length = 120)


class DeploymentPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    target_type: str | None = Field(None, alias = "targetType", max_length = 120)
    edition: str | None = Field(None, max_length = 80)
    expected_users: int | None = Field(None, alias = "expectedUsers", ge = 1, le = 100000)
    data_sensitivity: str | None = Field(None, alias = "dataSensitivity", max_length = 120)
    requested_features: list[str] | None = Field(None, alias = "requestedFeatures")


class GovernancePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    organization_name: str | None = Field(None, alias = "organizationName", max_length = 160)
    organization_type: str | None = Field(None, alias = "organizationType", max_length = 120)
    edition: str | None = Field(None, max_length = 80)
    user_count: int | None = Field(None, alias = "userCount", ge = 1, le = 100000)
    roles: list[str] | None = None
    sso_provider: str | None = Field(None, alias = "ssoProvider", max_length = 120)
    data_sensitivity: str | None = Field(None, alias = "dataSensitivity", max_length = 120)
    classroom_count: int | None = Field(None, alias = "classroomCount", ge = 0, le = 10000)
    requested_features: list[str] | None = Field(None, alias = "requestedFeatures")


class ToolActionPlanRequest(BaseModel):
    tool_id: str = Field(..., min_length = 1, max_length = 120)
    action_id: str = Field(..., min_length = 1, max_length = 120)


class IntegrationPlanRequest(BaseModel):
    tool_id: str = Field(..., min_length = 1, max_length = 120)


class ModulePlanRequest(BaseModel):
    module_id: str = Field(..., min_length = 1, max_length = 160)


class BenchmarkRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    mode: Literal["quick", "extended"] = "quick"
    include_disk: bool = Field(True, alias = "includeDisk")


class NewsRefreshRequest(BaseModel):
    topic: str = Field("intelligence artificielle", min_length = 1, max_length = 120)


class GameCreateRequest(BaseModel):
    game_type: Literal["chess", "quiz", "code_duel"] = "chess"
    opponent_type: Literal["ai", "user"] = "ai"
    opponent_username: str | None = Field(None, max_length = 120)


class GameMoveRequest(BaseModel):
    from_square: str = Field(..., min_length = 2, max_length = 2)
    to_square: str = Field(..., min_length = 2, max_length = 2)


APP_CATALOG = [
    {"id": "canva", "name": "Canva", "category": "Design", "description": "Creer des designs et supports."},
    {"id": "google-drive", "name": "Google Drive", "category": "Files", "description": "Importer et organiser les fichiers."},
    {"id": "github", "name": "GitHub", "category": "Code", "description": "Depots, issues et pull requests."},
    {"id": "hugging-face", "name": "Hugging Face", "category": "AI", "description": "Modeles, datasets et jobs GPU."},
    {"id": "notion", "name": "Notion", "category": "Productivity", "description": "Docs, bases et suivi projet."},
    {"id": "gmail", "name": "Gmail", "category": "Communication", "description": "Lecture et redaction assistee."},
]


NEWS_FEEDS = [
    ("Google News", "https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr"),
    ("Hacker News", "https://hnrss.org/newest?q={query}"),
]


def _require_admin(current_subject: str) -> None:
    if not auth_storage.is_admin(current_subject):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail = "Admin access required",
        )


def _row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a frontend-friendly copy while keeping raw fields available."""

    out = dict(row)
    alias_map = {
        "request_type": "requestType",
        "permission_key": "permissionKey",
        "admin_note": "adminNote",
        "granted_at": "grantedAt",
        "granted_by": "grantedBy",
        "expires_at": "expiresAt",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
        "decided_at": "decidedAt",
        "decided_by": "decidedBy",
        "actor_username": "actorUsername",
        "temporary_until": "temporaryUntil",
        "admin_decision": "adminDecision",
        "client_key": "clientKey",
        "pattern_label": "patternLabel",
        "ban_id": "banId",
        "updated_by": "updatedBy",
        "size_bytes": "sizeBytes",
        "metadata_json": "metadataJson",
        "schedule_text": "scheduleText",
        "display_name": "displayName",
        "app_id": "appId",
        "app_name": "appName",
        "resource_type": "resourceType",
        "resource_id": "resourceId",
        "model_id": "modelId",
        "provider_type": "providerType",
        "provider_id": "providerId",
        "project_id": "projectId",
        "owner_username": "ownerUsername",
        "collaborator_username": "collaboratorUsername",
        "share_id": "shareId",
        "revoked_at": "revokedAt",
        "topics_json": "topicsJson",
        "source_thread_ids_json": "sourceThreadIdsJson",
        "artifact_uri": "artifactUri",
        "task_id": "taskId",
        "action_type": "actionType",
        "artifact_type": "artifactType",
        "artifact_id": "artifactId",
        "finished_at": "finishedAt",
        "sources_json": "sourcesJson",
        "plan_json": "planJson",
        "published_at": "publishedAt",
        "game_type": "gameType",
        "opponent_type": "opponentType",
        "opponent_username": "opponentUsername",
        "state_json": "stateJson",
        "objective_excerpt": "objectiveExcerpt",
        "project_type": "projectType",
        "selected_domain": "selectedDomain",
        "model_label": "modelLabel",
        "recommended_path": "recommendedPath",
        "primary_capability": "primaryCapability",
        "decision_json": "decisionJson",
        "overall_score": "overallScore",
        "estimated_tokens_per_second": "estimatedTokensPerSecond",
        "hardware_json": "hardwareJson",
        "benchmark_json": "benchmarkJson",
        "needs_clarification": "needsClarification",
        "routing_mode": "routingMode",
        "scores_json": "scoresJson",
    }
    for source, target in alias_map.items():
        if source in out:
            out[target] = out[source]
    if "needsClarification" in out:
        out["needsClarification"] = bool(out["needsClarification"])
    return out


def _current_model_cache_runtime() -> dict[str, Any]:
    try:
        from core.inference import get_inference_backend
        from routes.inference import get_llama_cpp_backend

        llama_backend = get_llama_cpp_backend()
        if llama_backend.is_loaded:
            model_id = (
                getattr(llama_backend, "_native_display_label", None)
                or getattr(llama_backend, "model_identifier", None)
            )
            loaded_models = [model_id] if model_id else []
            return {
                "runtimeType": "gguf",
                "activeModel": model_id,
                "loadedModels": loaded_models,
                "loadingModels": [],
            }

        backend = get_inference_backend()
        return {
            "runtimeType": "unsloth",
            "activeModel": getattr(backend, "active_model_name", None),
            "loadedModels": list(getattr(backend, "models", {}).keys()),
            "loadingModels": list(getattr(backend, "loading_models", set())),
        }
    except Exception as exc:
        return {
            "runtimeType": "unknown",
            "activeModel": None,
            "loadedModels": [],
            "loadingModels": [],
            "error": str(exc),
        }


def _rag_available() -> bool | None:
    try:
        from storage import rag_db

        return bool(getattr(rag_db, "RAG_AVAILABLE", False))
    except Exception:
        return None


def _granted_permission_keys(username: str) -> set[str]:
    permissions: set[str] = set()
    for item in cognix_db.list_user_permissions(username):
        key = item.get("permission_key") or item.get("permissionKey")
        if isinstance(key, str) and key.strip():
            permissions.add(key.strip().lower())
    return permissions


def _rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_row(row) for row in rows]


def _require_owned_project(project_id: str, owner_username: str) -> dict[str, Any]:
    project = get_chat_project(
        project_id,
        owner_username = owner_username,
        include_all = False,
    )
    if project is None:
        raise HTTPException(status_code = 404, detail = "Project not found")
    return project


def _dashboard_password_status(user: dict[str, Any]) -> dict[str, Any]:
    locked = bool(user.get("loginLocked"))
    permanent = bool(user.get("loginPermanentlyLocked"))
    must_change = bool(user.get("mustChangePassword"))
    failed = int(user.get("failedLoginCount") or 0)
    if permanent:
        label = "Compte verrouille"
    elif locked:
        label = "Verrouillage temporaire"
    elif must_change:
        label = "Changement requis"
    elif failed:
        label = f"{failed} echec(s) recent(s)"
    else:
        label = "Configure"
    return {
        "configured": True,
        "label": label,
        "mustChangePassword": must_change,
        "locked": locked,
        "permanentlyLocked": permanent,
        "failedAttempts": failed,
        "lockoutLevel": int(user.get("loginLockoutLevel") or 0),
        "lockoutUntil": user.get("loginLockoutUntil"),
        "secretExposed": False,
    }


def _dashboard_quota(plan: str, used_tokens: int) -> dict[str, Any]:
    normalized_plan = (plan or "free").strip() or "free"
    is_unlimited = normalized_plan.casefold() == "ceo"
    return {
        "plan": normalized_plan,
        "usedTokens": int(used_tokens or 0),
        "limitTokens": None,
        "remainingTokens": None,
        "unlimited": is_unlimited,
        "label": "Illimite" if is_unlimited else "Quota non configure",
    }


def _dashboard_model_name(thread: dict[str, Any]) -> str:
    return str(thread.get("modelId") or thread.get("modelType") or "Modele inconnu")


def _build_dashboard_user_details(
    users: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    usage: list[dict[str, Any]],
    security_events: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    collaborators: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    threads_by_user: dict[str, list[dict[str, Any]]] = {}
    projects_by_user: dict[str, list[dict[str, Any]]] = {}
    usage_by_user: dict[str, list[dict[str, Any]]] = {}
    collaborators_by_owner: dict[str, list[dict[str, Any]]] = {}
    collaborators_by_user: dict[str, list[dict[str, Any]]] = {}
    security_by_user: dict[str, list[dict[str, Any]]] = {}
    bans_by_user: dict[str, list[dict[str, Any]]] = {}
    reports_by_user: dict[str, list[dict[str, Any]]] = {}

    for thread in threads:
        owner = str(thread.get("ownerUsername") or "unknown")
        threads_by_user.setdefault(owner, []).append(thread)
    for project in projects:
        owner = str(project.get("ownerUsername") or "unknown")
        projects_by_user.setdefault(owner, []).append(project)
    for item in usage:
        owner = str(item.get("username") or item.get("ownerUsername") or "unknown")
        usage_by_user.setdefault(owner, []).append(item)
    for item in collaborators:
        owner = str(item.get("owner_username") or item.get("ownerUsername") or "unknown")
        collaborator = str(item.get("collaborator_username") or item.get("collaboratorUsername") or "unknown")
        collaborators_by_owner.setdefault(owner, []).append(item)
        collaborators_by_user.setdefault(collaborator, []).append(item)
    for item in security_events:
        owner = str(item.get("username") or "unknown")
        security_by_user.setdefault(owner, []).append(item)
    for item in bans:
        owner = str(item.get("username") or "unknown")
        bans_by_user.setdefault(owner, []).append(item)
    for item in reports:
        owner = str(item.get("username") or "unknown")
        reports_by_user.setdefault(owner, []).append(item)

    details: dict[str, dict[str, Any]] = {}
    for user in users:
        username = str(user.get("username") or "unknown")
        user_threads = threads_by_user.get(username, [])
        user_projects = projects_by_user.get(username, [])
        user_usage = usage_by_user.get(username, [])
        used_tokens = sum(int(item.get("approxTokens") or item.get("estimatedTokens") or 0) for item in user_usage)
        model_usage = sorted(
            user_usage,
            key = lambda item: int(item.get("approxTokens") or item.get("estimatedTokens") or 0),
            reverse = True,
        )
        recent_chats = [
            {
                "id": thread.get("id"),
                "title": thread.get("title") or "Conversation",
                "modelId": _dashboard_model_name(thread),
                "createdAt": thread.get("createdAt"),
                "projectId": thread.get("projectId"),
            }
            for thread in user_threads[:8]
        ]
        project_collaborator_counts: dict[str, int] = {}
        for collab in collaborators_by_owner.get(username, []):
            project_id = str(collab.get("project_id") or collab.get("projectId") or "")
            if project_id:
                project_collaborator_counts[project_id] = project_collaborator_counts.get(project_id, 0) + 1
        project_items = [
            {
                "id": project.get("id"),
                "name": project.get("name") or "Projet",
                "archived": bool(project.get("archived")),
                "updatedAt": project.get("updatedAt"),
                "collaborators": project_collaborator_counts.get(str(project.get("id") or ""), 0),
            }
            for project in user_projects
        ]
        details[username] = {
            "username": username,
            "displayName": user.get("displayName") or username,
            "plan": user.get("plan") or "free",
            "role": user.get("role") or "user",
            "chatCount": len(user_threads),
            "projectCount": len(user_projects),
            "models": model_usage,
            "quota": _dashboard_quota(str(user.get("plan") or "free"), used_tokens),
            "passwordStatus": _dashboard_password_status(user),
            "network": {
                "lastLoginIp": user.get("lastLoginIp"),
                "lastLoginAt": user.get("lastLoginAt"),
            },
            "recentChats": recent_chats,
            "projects": project_items,
            "collaborations": collaborators_by_user.get(username, []),
            "securityEvents": len(security_by_user.get(username, [])),
            "activeBans": sum(
                1
                for item in bans_by_user.get(username, [])
                if item.get("status") in {"pending_admin_review", "active", "permanent"}
            ),
            "openReports": sum(
                1
                for item in reports_by_user.get(username, [])
                if item.get("status") in {"open", "in_review"}
            ),
        }
    return details


def _strip_html(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _short_summary(*parts: str, limit: int = 360) -> str:
    text = _strip_html(" ".join(part for part in parts if part))
    if not text:
        return "Resume indisponible pour le moment."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentences[:2]).strip()
    if len(summary) > limit:
        summary = summary[: limit - 1].rstrip() + "..."
    return summary


def _xml_text(node: ET.Element | None, tag: str) -> str:
    if node is None:
        return ""
    child = node.find(tag)
    if child is None:
        child = node.find(f"{{*}}{tag}")
    return _strip_html(child.text if child is not None else "")


def _xml_link(node: ET.Element | None) -> str:
    if node is None:
        return ""
    link = _xml_text(node, "link")
    if link:
        return link
    for child in node.findall("{*}link"):
        href = child.attrib.get("href")
        if href:
            return href
    return ""


def _parse_published(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return value[:80]


def _fetch_feed_items(topic: str, limit: int = 10) -> list[dict[str, Any]]:
    query = urllib.parse.quote_plus(topic or "intelligence artificielle")
    items: list[dict[str, Any]] = []
    for source, template in NEWS_FEEDS:
        if len(items) >= limit:
            break
        url = template.format(query = query)
        request = urllib.request.Request(
            url,
            headers = {"User-Agent": "CogniX/0.9 (+local studio)"},
        )
        try:
            with urllib.request.urlopen(request, timeout = 5) as response:
                raw = response.read(750_000)
            root = ET.fromstring(raw)
        except Exception:
            continue

        feed_items = root.findall(".//item") or root.findall(".//{*}entry")
        for item in feed_items:
            title = _xml_text(item, "title")
            item_url = _xml_link(item)
            description = _xml_text(item, "description") or _xml_text(item, "summary")
            published = (
                _xml_text(item, "pubDate")
                or _xml_text(item, "published")
                or _xml_text(item, "updated")
            )
            if not title or not item_url:
                continue
            items.append(
                {
                    "topic": topic,
                    "title": title[:240],
                    "summary": _short_summary(title, description),
                    "url": item_url,
                    "source": source,
                    "published_at": _parse_published(published),
                }
            )
            if len(items) >= limit:
                break
    return items


def _research_summary(query: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return (
            "CogniX a cree une fiche de recherche pour ce sujet. "
            "Aucune source externe n'a repondu assez vite; relancez la recherche plus tard ou precisez le sujet."
        )
    titles = [str(source.get("title") or "").strip() for source in sources[:5] if source.get("title")]
    return (
        f"Recherche approfondie sur '{query}'. "
        "Les sources recentes convergent autour de: "
        + "; ".join(titles)
        + ". CogniX garde ces sources pour produire un rapport plus long ensuite."
    )


def _agent_plan(goal: str, mode: str) -> list[str]:
    base = [
        "Clarifier l'objectif et les criteres de reussite.",
        "Identifier les donnees, outils et permissions necessaires.",
        "Executer les etapes a faible risque en premier.",
        "Verifier le resultat et preparer un compte rendu.",
    ]
    if mode == "research":
        base.insert(1, "Collecter des sources et distinguer faits, hypotheses et inconnues.")
    elif mode == "automation":
        base.insert(2, "Planifier les actions dans le temps avec points de controle.")
    return base


def _scheduled_action_type(prompt: str) -> str:
    text = prompt.lower()
    if any(word in text for word in ("news", "actualite", "actualité", "veille", "surveille")):
        return "news"
    if any(word in text for word in ("recherche", "research", "analyse", "rapport", "source")):
        return "research"
    if any(word in text for word in ("agent", "action", "automatisation", "execute", "exécute")):
        return "agent"
    return "report"


def _execute_scheduled_task(username: str, task: dict[str, Any]) -> dict[str, Any]:
    prompt = str(task.get("prompt") or task.get("title") or "").strip()
    action_type = _scheduled_action_type(prompt)
    artifact_type = None
    artifact_id = None

    if action_type == "news":
        topic = prompt or "intelligence artificielle"
        items = _fetch_feed_items(topic, limit = 8)
        for item in items:
            cognix_db.create_news_item(
                username,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
        result = f"Veille terminee: {len(items)} actualites ajoutees pour '{topic[:80]}'."
        artifact_type = "news"
    elif action_type == "research":
        query = prompt or "Recherche CogniX"
        sources = _fetch_feed_items(query, limit = 6)
        report = cognix_db.create_research_report(
            username,
            query,
            "Recherche planifiee: " + query[:90],
            _research_summary(query, sources),
            [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "publishedAt": item.get("published_at"),
                }
                for item in sources
            ],
        )
        artifact_type = "research"
        artifact_id = str(report.get("id") or "")
        result = f"Recherche planifiee terminee avec {len(sources)} sources."
    elif action_type == "agent":
        plan = _agent_plan(prompt or "Action planifiee", "automation")
        run = cognix_db.create_agent_run(
            username,
            prompt or "Action planifiee",
            "automation",
            plan,
            "Run cree depuis une tache planifiee.",
        )
        artifact_type = "agent_run"
        artifact_id = str(run.get("id") or "")
        result = f"Agent planifie avec {len(plan)} etapes."
    else:
        item = cognix_db.create_library_item(
            username,
            kind = "document",
            name = "Compte rendu planifie: " + (task.get("title") or "Tache")[:80],
            source = "scheduled_task",
            metadata = {"taskId": task.get("id"), "prompt": prompt},
        )
        artifact_type = "library_item"
        artifact_id = str(item.get("id") or "")
        result = "Compte rendu de tache cree dans la bibliotheque."

    return cognix_db.create_scheduled_task_run(
        username,
        str(task.get("id")),
        action_type,
        result,
        artifact_type = artifact_type,
        artifact_id = artifact_id,
    )


def _game_initial_state(game_type: str) -> dict[str, Any]:
    if game_type == "chess":
        return {"board": _chess_initial_board(), "turn": "white", "moves": [], "winner": None, "message": "A vous de jouer."}
    if game_type == "quiz":
        return {"round": 1, "score": {"user": 0, "opponent": 0}, "topic": "general"}
    return {"round": 1, "challenge": "En attente", "score": {"user": 0, "opponent": 0}}


def _chess_initial_board() -> dict[str, str]:
    board: dict[str, str] = {}
    order = ["R", "N", "B", "Q", "K", "B", "N", "R"]
    for index, piece in enumerate(order):
        file_name = chr(ord("a") + index)
        board[f"{file_name}1"] = "w" + piece
        board[f"{file_name}2"] = "wP"
        board[f"{file_name}7"] = "bP"
        board[f"{file_name}8"] = "b" + piece
    return board


def _normalize_chess_state(state: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(state or {})
    board = normalized.get("board")
    if not isinstance(board, dict):
        board = _chess_initial_board()
    normalized["board"] = dict(board)
    normalized["turn"] = normalized.get("turn") if normalized.get("turn") in {"white", "black"} else "white"
    normalized["moves"] = normalized.get("moves") if isinstance(normalized.get("moves"), list) else []
    normalized["winner"] = normalized.get("winner")
    normalized["message"] = normalized.get("message") or "A vous de jouer."
    return normalized


def _square_xy(square: str) -> tuple[int, int]:
    if not re.fullmatch(r"[a-h][1-8]", square or ""):
        raise ValueError("Square invalide")
    return ord(square[0]) - ord("a"), int(square[1]) - 1


def _xy_square(x: int, y: int) -> str:
    return f"{chr(ord('a') + x)}{y + 1}"


def _piece_color(piece: str | None) -> str | None:
    if not piece:
        return None
    return "white" if piece[0] == "w" else "black"


def _path_clear(board: dict[str, str], from_square: str, to_square: str) -> bool:
    fx, fy = _square_xy(from_square)
    tx, ty = _square_xy(to_square)
    step_x = 0 if tx == fx else (1 if tx > fx else -1)
    step_y = 0 if ty == fy else (1 if ty > fy else -1)
    x = fx + step_x
    y = fy + step_y
    while (x, y) != (tx, ty):
        if board.get(_xy_square(x, y)):
            return False
        x += step_x
        y += step_y
    return True


def _is_chess_move_legal(board: dict[str, str], from_square: str, to_square: str, turn: str) -> tuple[bool, str]:
    if from_square == to_square:
        return False, "Choisissez deux cases differentes."
    try:
        fx, fy = _square_xy(from_square)
        tx, ty = _square_xy(to_square)
    except ValueError as exc:
        return False, str(exc)

    piece = board.get(from_square)
    if not piece:
        return False, "Aucune piece sur cette case."
    if _piece_color(piece) != turn:
        return False, "Ce n'est pas le tour de cette couleur."
    target = board.get(to_square)
    if target and _piece_color(target) == turn:
        return False, "Une piece alliee occupe deja cette case."

    dx = tx - fx
    dy = ty - fy
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    kind = piece[1]
    direction = 1 if turn == "white" else -1
    start_rank = 1 if turn == "white" else 6

    if kind == "P":
        if dx == 0 and dy == direction and not target:
            return True, ""
        if dx == 0 and dy == 2 * direction and fy == start_rank and not target and not board.get(_xy_square(fx, fy + direction)):
            return True, ""
        if abs_dx == 1 and dy == direction and target and _piece_color(target) != turn:
            return True, ""
        return False, "Deplacement de pion invalide."
    if kind == "N":
        return ((abs_dx, abs_dy) in {(1, 2), (2, 1)}, "Deplacement de cavalier invalide.")
    if kind == "B":
        return (abs_dx == abs_dy and _path_clear(board, from_square, to_square), "Diagonale bloquee ou invalide.")
    if kind == "R":
        return ((dx == 0 or dy == 0) and _path_clear(board, from_square, to_square), "Ligne bloquee ou invalide.")
    if kind == "Q":
        return (((dx == 0 or dy == 0) or abs_dx == abs_dy) and _path_clear(board, from_square, to_square), "Deplacement de dame invalide.")
    if kind == "K":
        return (max(abs_dx, abs_dy) == 1, "Deplacement de roi invalide.")
    return False, "Piece inconnue."


def _apply_chess_move(state: dict[str, Any], from_square: str, to_square: str, actor: str) -> dict[str, Any]:
    board = dict(state["board"])
    turn = state["turn"]
    legal, reason = _is_chess_move_legal(board, from_square, to_square, turn)
    if not legal:
        raise ValueError(reason)

    piece = board.pop(from_square)
    captured = board.get(to_square)
    if piece[1] == "P" and to_square[1] in {"1", "8"}:
        piece = piece[0] + "Q"
    board[to_square] = piece
    winner = "white" if captured == "bK" else "black" if captured == "wK" else None
    next_turn = "black" if turn == "white" else "white"
    move = {
        "from": from_square,
        "to": to_square,
        "piece": piece,
        "captured": captured,
        "actor": actor,
        "turn": turn,
    }
    moves = list(state.get("moves") or [])
    moves.append(move)
    state.update(
        {
            "board": board,
            "turn": next_turn,
            "moves": moves,
            "winner": winner,
            "message": "Partie terminee." if winner else ("Tour des noirs." if next_turn == "black" else "A vous de jouer."),
        }
    )
    return state


def _legal_chess_moves(board: dict[str, str], turn: str) -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    for from_square, piece in board.items():
        if _piece_color(piece) != turn:
            continue
        for x in range(8):
            for y in range(8):
                to_square = _xy_square(x, y)
                legal, _ = _is_chess_move_legal(board, from_square, to_square, turn)
                if legal:
                    moves.append((from_square, to_square))
    return moves


def _apply_ai_chess_reply(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("winner") or state.get("turn") != "black":
        return state
    board = dict(state["board"])
    moves = _legal_chess_moves(board, "black")
    if not moves:
        state["winner"] = "white"
        state["message"] = "Les noirs n'ont plus de coup disponible."
        return state
    captures = [move for move in moves if board.get(move[1])]
    from_square, to_square = (captures or moves)[0]
    return _apply_chess_move(state, from_square, to_square, "cognix-ai")


@router.get("/strategy")
async def my_strategy(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return build_strategy(current_subject)


@router.get("/hardware/profile")
async def hardware_profile(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "hardware": cognix_hardware.get_hardware_profile(),
    }


@router.post("/benchmark/run")
async def run_benchmark(
    payload: BenchmarkRunRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    benchmark = cognix_benchmark.run_benchmark(
        mode = payload.mode,
        include_disk = payload.include_disk,
    )
    run = cognix_db.create_benchmark_run(current_subject, benchmark)
    return {
        "username": current_subject,
        "runId": run.get("id"),
        "benchmark": benchmark,
    }


@router.get("/benchmark/runs")
async def benchmark_runs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "runs": _rows(cognix_db.list_benchmark_runs(username = current_subject, limit = 50)),
    }


@router.get("/models/recommendation")
async def model_recommendation(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "latestBenchmark": latest_benchmark,
        **recommendation,
    }


@router.post("/onboarding/plan")
async def onboarding_plan(
    payload: OnboardingPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    plan = cognix_onboarding.build_onboarding_plan(
        username = current_subject,
        hardware = hardware,
        recommendation = recommendation_payload["recommendation"],
        purpose = payload.purpose,
        level = payload.level,
        execution_target = payload.execution_target,
        priorities = payload.priorities,
        project_type = payload.project_type,
        latest_benchmark_run = latest_benchmark,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "onboarding_plan_built",
        resource_type = "cognix_onboarding",
        resource_id = str(plan.get("recommendedPack", {}).get("id") or "starter-pack"),
        severity = "warning" if plan.get("warnings") else "notice",
        metadata = {
            "onboardingVersion": plan.get("onboardingVersion"),
            "purpose": plan.get("profile", {}).get("purpose"),
            "executionTarget": plan.get("profile", {}).get("executionTarget"),
            "hardwareTier": plan.get("hardwareSummary", {}).get("tier"),
            "recommendedEdition": plan.get("recommendedEdition"),
            "modelIds": [
                item.get("id")
                for item in plan.get("recommendedPack", {}).get("models", [])
                if isinstance(item, dict)
            ],
            "moduleIds": plan.get("recommendedPack", {}).get("modules", []),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "latestBenchmark": latest_benchmark,
        "recommendation": recommendation_payload["recommendation"],
        "onboardingPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_onboarding.COGNIX_ONBOARDING_VERSION,
    }


@router.get("/models/registry")
async def model_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_registry.build_model_registry(),
    }


@router.get("/models/packs")
async def model_packs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_registry.build_model_registry()
    return {
        "username": current_subject,
        "modelRegistry": registry,
        "registry": cognix_model_lifecycle.build_model_pack_registry(model_registry = registry),
        "plannerVersion": cognix_model_lifecycle.COGNIX_MODEL_LIFECYCLE_VERSION,
    }


@router.post("/models/lifecycle-plan")
async def model_lifecycle_plan(
    payload: ModelLifecyclePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    runtime = _current_model_cache_runtime()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    model_registry_payload = cognix_registry.build_model_registry()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = latest_benchmark,
        rag_available = _rag_available(),
    )
    default_model = (
        cognix_db.get_project_model_default(payload.project_id, current_subject)
        if payload.project_id
        else None
    )
    project_expert_plan = plan["projectExpertPlan"]
    if default_model:
        project_expert_plan = cognix_project_experts.build_project_expert_plan(
            objective = payload.objective,
            project_id = payload.project_id,
            project_type = payload.project_type,
            project_default_model = default_model,
            classification = plan["classification"],
            recommendation = plan["recommendation"],
            preload_plan = plan["preloadPlan"],
            rag_plan = plan["ragPlan"],
            context_plan = plan["contextPlan"],
        )
    lifecycle = cognix_model_lifecycle.build_model_lifecycle_plan(
        objective = payload.objective,
        hardware = plan["hardware"],
        recommendation = plan["recommendation"],
        cache = plan["cache"],
        classification = plan["classification"],
        project_expert_plan = project_expert_plan,
        runtime_adapter_plan = plan["runtimeAdapterPlan"],
        model_registry = model_registry_payload,
        latest_benchmark_run = latest_benchmark,
        project_id = payload.project_id,
        project_type = payload.project_type,
        requested_model_id = payload.model_id,
        execution_target = payload.execution_target,
        quality_priority = payload.quality_priority,
        offline_required = payload.offline_required,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_lifecycle_plan_built",
        resource_type = "cognix_model_lifecycle",
        resource_id = str(lifecycle.get("selectedPack", {}).get("modelId") or "none"),
        severity = "warning" if lifecycle.get("warnings") else "notice",
        metadata = {
            "modelLifecycleVersion": lifecycle.get("modelLifecycleVersion"),
            "selectedPackId": lifecycle.get("selectedPack", {}).get("packId"),
            "selectedModelId": lifecycle.get("selectedPack", {}).get("modelId"),
            "targetDomain": lifecycle.get("request", {}).get("targetDomain"),
            "installRequired": lifecycle.get("installPlan", {}).get("required"),
            "loadAction": lifecycle.get("loadPlan", {}).get("action"),
            "sideEffects": lifecycle.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "latestBenchmark": latest_benchmark,
        "modelRegistry": model_registry_payload,
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "projectExpertPlan": project_expert_plan,
        "modelLifecyclePlan": lifecycle,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": lifecycle.get("sideEffects", {}),
        "plannerVersion": cognix_model_lifecycle.COGNIX_MODEL_LIFECYCLE_VERSION,
    }


@router.post("/thinking/plan")
async def thinking_status_plan(
    payload: ThinkingStatusPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    runtime = _current_model_cache_runtime()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    model_registry_payload = cognix_registry.build_model_registry()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = latest_benchmark,
        rag_available = _rag_available(),
    )
    lifecycle = cognix_model_lifecycle.build_model_lifecycle_plan(
        objective = payload.objective,
        hardware = plan["hardware"],
        recommendation = plan["recommendation"],
        cache = plan["cache"],
        classification = plan["classification"],
        project_expert_plan = plan["projectExpertPlan"],
        runtime_adapter_plan = plan["runtimeAdapterPlan"],
        model_registry = model_registry_payload,
        latest_benchmark_run = latest_benchmark,
        project_id = payload.project_id,
        project_type = payload.project_type,
        requested_model_id = payload.model_id,
    )
    thinking = cognix_thinking_status.build_thinking_status_plan(
        objective = payload.objective,
        classification = plan["classification"],
        task_strategy = plan["taskStrategy"],
        recommendation = plan["recommendation"],
        model_lifecycle_plan = lifecycle,
        context_plan = plan["contextPlan"],
        rag_plan = plan["ragPlan"],
        project_expert_plan = plan["projectExpertPlan"],
        execution_policy = plan["executionPolicy"],
        audience = payload.audience,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "thinking_status_plan_built",
        resource_type = "cognix_thinking_status",
        resource_id = str(payload.project_id or payload.audience),
        severity = "warning" if thinking.get("status") != "ready" else "notice",
        metadata = {
            "thinkingStatusVersion": thinking.get("thinkingStatusVersion"),
            "status": thinking.get("status"),
            "audience": thinking.get("audience"),
            "progress": thinking.get("progress"),
            "hiddenTechnicalFields": thinking.get("redaction", {}).get("hiddenTechnicalFields", []),
            "sideEffects": thinking.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "thinkingStatusPlan": thinking,
        "modelLifecyclePlan": lifecycle,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": thinking.get("sideEffects", {}),
        "plannerVersion": cognix_thinking_status.COGNIX_THINKING_STATUS_VERSION,
    }


@router.get("/runtime/adapters")
async def runtime_adapters(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_runtime_adapter.build_runtime_adapter_registry(),
    }


@router.get("/deployments/targets")
async def deployment_targets(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_deployment_manager.build_deployment_target_registry(),
    }


@router.post("/deployments/plan")
async def deployment_plan(
    payload: DeploymentPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    plan = cognix_deployment_manager.build_deployment_plan(
        username = current_subject,
        objective = payload.objective,
        hardware = hardware,
        recommendation = recommendation_payload["recommendation"],
        target_type = payload.target_type,
        edition = payload.edition,
        expected_users = payload.expected_users,
        data_sensitivity = payload.data_sensitivity,
        requested_features = payload.requested_features,
        latest_benchmark_run = latest_benchmark,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "deployment_plan_built",
        resource_type = "cognix_deployment",
        resource_id = str(plan.get("recommendedTarget", {}).get("targetId") or "none"),
        severity = "warning" if plan.get("securityPlan", {}).get("humanApprovalRequired") else "notice",
        metadata = {
            "deploymentManagerVersion": plan.get("deploymentManagerVersion"),
            "targetType": plan.get("request", {}).get("targetType"),
            "edition": plan.get("request", {}).get("edition"),
            "expectedUsers": plan.get("request", {}).get("expectedUsers"),
            "recommendedTargetId": plan.get("recommendedTarget", {}).get("targetId"),
            "riskLevel": plan.get("securityPlan", {}).get("riskLevel"),
            "requiredCapabilities": plan.get("requiredCapabilities", []),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "latestBenchmark": latest_benchmark,
        "recommendation": recommendation_payload["recommendation"],
        "deploymentPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_deployment_manager.COGNIX_DEPLOYMENT_MANAGER_VERSION,
    }


@router.get("/governance/blueprint")
async def governance_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "username": current_subject,
        "blueprint": cognix_governance_manager.build_governance_blueprint(),
    }


@router.post("/governance/plan")
async def governance_plan(
    payload: GovernancePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    plan = cognix_governance_manager.build_governance_plan(
        username = current_subject,
        organization_name = payload.organization_name,
        organization_type = payload.organization_type,
        edition = payload.edition,
        user_count = payload.user_count,
        roles = payload.roles,
        sso_provider = payload.sso_provider,
        data_sensitivity = payload.data_sensitivity,
        classroom_count = payload.classroom_count,
        requested_features = payload.requested_features,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "governance_plan_built",
        resource_type = "cognix_governance",
        resource_id = str(plan.get("organization", {}).get("id") or "organization"),
        severity = "warning" if plan.get("policyPlan", {}).get("humanApprovalRequired") else "notice",
        metadata = {
            "governanceManagerVersion": plan.get("governanceManagerVersion"),
            "organizationId": plan.get("organization", {}).get("id"),
            "organizationType": plan.get("organization", {}).get("type"),
            "edition": plan.get("organization", {}).get("edition"),
            "plannedUserCount": plan.get("organization", {}).get("plannedUserCount"),
            "requiredCapabilities": plan.get("requiredCapabilities", []),
            "ssoProviderId": plan.get("ssoPlan", {}).get("provider", {}).get("id"),
            "roleIds": [
                item.get("roleId") for item in plan.get("roleMatrix", []) if isinstance(item, dict)
            ],
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "governancePlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_governance_manager.COGNIX_GOVERNANCE_MANAGER_VERSION,
    }


@router.post("/runtime/plan")
async def runtime_plan(
    payload: RuntimePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        rag_available = _rag_available(),
    )
    adapter_plan = plan["runtimeAdapterPlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "runtime_adapter_plan_built",
        resource_type = "cognix_runtime_adapter",
        resource_id = str(adapter_plan.get("selectedAdapter", {}).get("adapterId") or "none"),
        severity = "warning" if adapter_plan.get("warnings") else "notice",
        metadata = {
            "runtimeAdapterVersion": adapter_plan.get("runtimeAdapterVersion"),
            "requestedRuntimeType": adapter_plan.get("requestedRuntimeType"),
            "selectedAdapter": adapter_plan.get("selectedAdapter", {}),
            "requiredCapabilities": adapter_plan.get("requiredCapabilities", []),
            "sideEffects": adapter_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "runtimeAdapterPlan": adapter_plan,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": adapter_plan.get("sideEffects", {}),
        "plannerVersion": cognix_runtime_adapter.COGNIX_RUNTIME_ADAPTER_VERSION,
    }


@router.post("/codex/pipeline-plan")
async def codex_pipeline_plan(
    payload: CodexPipelinePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
    )
    pipeline = plan["codexPipelinePlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "codex_pipeline_plan_built",
        resource_type = "cognix_codex_pipeline",
        resource_id = str(payload.project_id or pipeline.get("branch", {}).get("recommendedName") or "none"),
        severity = "warning" if pipeline.get("applicable") else "notice",
        metadata = {
            "codexPipelineVersion": pipeline.get("plannerVersion"),
            "applicable": pipeline.get("applicable"),
            "recommendedPath": pipeline.get("recommendedPath"),
            "branchName": pipeline.get("branch", {}).get("recommendedName"),
            "qualityGates": pipeline.get("qualityGates", {}),
            "blockedActionIds": [
                item.get("id") for item in pipeline.get("blockedActions", []) if isinstance(item, dict)
            ],
            "sideEffects": pipeline.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "codexPipelinePlan": pipeline,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": pipeline.get("sideEffects", {}),
        "plannerVersion": cognix_codex_pipeline.COGNIX_CODEX_PIPELINE_VERSION,
    }


@router.get("/workers/registry")
async def worker_queue_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_worker_queue.build_worker_queue_registry()
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "worker_queue_registry_built",
        resource_type = "cognix_worker_queue_registry",
        resource_id = str(registry.get("workerQueueVersion")),
        severity = "notice",
        metadata = {
            "workerQueueVersion": registry.get("workerQueueVersion"),
            "queueCount": len(registry.get("queues", [])),
            "sideEffects": registry.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "registry": registry,
        "auditLogId": audit.get("id"),
        "sideEffects": registry.get("sideEffects", {}),
    }


@router.post("/workers/plan")
async def worker_queue_plan(
    payload: WorkerQueuePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = latest_benchmark,
        rag_sources = payload.sources or [],
        rag_available = _rag_available(),
        fine_tuning_dataset = payload.dataset,
    )
    queue_plan = plan["workerQueuePlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "worker_queue_plan_built",
        resource_type = "cognix_worker_queue",
        resource_id = str(payload.project_id or queue_plan.get("recommendedQueue", {}).get("id") or "none"),
        severity = "warning" if queue_plan.get("summary", {}).get("requiresHumanConfirmation") else "notice",
        metadata = {
            "workerQueueVersion": queue_plan.get("workerQueueVersion"),
            "recommendedQueueId": queue_plan.get("recommendedQueue", {}).get("id"),
            "plannedJobCount": queue_plan.get("summary", {}).get("plannedJobCount"),
            "plannedJobIds": queue_plan.get("summary", {}).get("plannedJobIds", []),
            "requiresHumanConfirmation": queue_plan.get("summary", {}).get("requiresHumanConfirmation"),
            "sideEffects": queue_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "workerQueuePlan": queue_plan,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": queue_plan.get("sideEffects", {}),
        "plannerVersion": cognix_worker_queue.COGNIX_WORKER_QUEUE_VERSION,
    }


@router.post("/workers/job-spec-plan")
async def worker_job_spec_plan(
    payload: WorkerJobSpecPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    user_profile = auth_storage.get_user_profile(current_subject) or {}
    user_plan = str(user_profile.get("plan") or "")
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = latest_benchmark,
        rag_sources = payload.sources or [],
        rag_available = _rag_available(),
        fine_tuning_dataset = payload.dataset,
        user_plan = user_plan,
    )
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    rag_indexing_plan: dict[str, Any] = {}
    if payload.sources:
        rag_indexing_plan = cognix_rag_planner.build_rag_indexing_plan(
            username = current_subject,
            project_id = payload.project_id,
            sources = payload.sources or [],
            objective = payload.objective,
            rag_available = _rag_available(),
            is_admin = is_admin,
            has_developer_mode = has_developer_mode,
            granted_permissions = _granted_permission_keys(current_subject),
        )
    cloud_handoff_plan: dict[str, Any] = {}
    if payload.dataset or plan.get("fineTuningPlan", {}).get("recommendedPath") == "guided_fine_tuning":
        cloud_handoff_plan = cognix_fine_tuning_planner.build_cloud_training_handoff_plan(
            username = current_subject,
            objective = payload.objective,
            project_id = payload.project_id,
            target_id = payload.target_id,
            fine_tuning_plan = plan["fineTuningPlan"],
            dataset = payload.dataset,
            user_plan = user_plan,
        )
    spec_plan = cognix_worker_queue.build_worker_job_spec_plan(
        objective = payload.objective,
        project_id = payload.project_id,
        worker_queue_plan = plan["workerQueuePlan"],
        rag_indexing_plan = rag_indexing_plan,
        cloud_handoff_plan = cloud_handoff_plan,
        preload_plan = plan["preloadPlan"],
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "worker_job_spec_plan_built",
        resource_type = "cognix_worker_job_spec_plan",
        resource_id = str(payload.project_id or spec_plan.get("jobSpecVersion")),
        severity = "warning" if spec_plan.get("summary", {}).get("requiresHumanConfirmation") else "notice",
        metadata = {
            "workerQueueVersion": spec_plan.get("workerQueueVersion"),
            "jobSpecVersion": spec_plan.get("jobSpecVersion"),
            "jobSpecCount": spec_plan.get("summary", {}).get("jobSpecCount"),
            "jobTypes": spec_plan.get("summary", {}).get("jobTypes", []),
            "requiresHumanConfirmation": spec_plan.get("summary", {}).get("requiresHumanConfirmation"),
            "sideEffects": spec_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "workerQueuePlan": plan["workerQueuePlan"],
        "ragIndexingPlan": rag_indexing_plan,
        "cloudHandoffPlan": cloud_handoff_plan,
        "workerJobSpecPlan": spec_plan,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": spec_plan.get("sideEffects", {}),
        "plannerVersion": cognix_worker_queue.COGNIX_WORKER_QUEUE_VERSION,
    }


@router.get("/modules/registry")
async def module_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_module_registry.build_module_registry(),
    }


@router.get("/modules/manifests")
async def module_manifests(
    edition: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    bundle = cognix_module_registry.build_module_manifest_bundle(edition = edition)
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "module_manifest_bundle_built",
        resource_type = "cognix_module_manifest_bundle",
        resource_id = str(bundle.get("schemaVersion")),
        severity = "notice",
        metadata = {
            "bundleVersion": bundle.get("bundleVersion"),
            "moduleRegistryVersion": bundle.get("moduleRegistryVersion"),
            "schemaVersion": bundle.get("schemaVersion"),
            "editionFilter": bundle.get("editionFilter"),
            "manifestCount": bundle.get("summary", {}).get("manifestCount"),
            "invalidManifestCount": bundle.get("summary", {}).get("invalidManifestCount"),
            "validationReady": bundle.get("validation", {}).get("ready"),
            "sideEffects": bundle.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "manifestBundle": bundle,
        "auditLogId": audit.get("id"),
        "sideEffects": bundle.get("sideEffects", {}),
    }


@router.post("/modules/plan")
async def plan_module_activation(
    payload: ModulePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_module_registry.build_module_activation_plan(payload.module_id)
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "module_plan_built",
        resource_type = "cognix_module",
        resource_id = str(payload.module_id),
        severity = "warning" if plan.get("humanApprovalRequired") else "notice",
        metadata = {
            "moduleRegistryVersion": plan.get("moduleRegistryVersion"),
            "moduleId": plan.get("moduleId"),
            "status": plan.get("status"),
            "allowedToActivate": plan.get("allowedToActivate"),
            "humanApprovalRequired": plan.get("humanApprovalRequired"),
            "riskLevel": plan.get("module", {}).get("riskLevel"),
            "dependencies": plan.get("module", {}).get("dependencyState", {}).get("dependencies", []),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    plan["auditLogId"] = audit.get("id")
    return plan


@router.get("/tools/registry")
async def tool_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_tool_registry.build_tool_registry(),
    }


@router.get("/tools/permission-matrix")
async def tool_permission_matrix(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    return cognix_tool_registry.build_tool_permission_matrix(
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )


@router.get("/integrations/status")
async def integrations_status(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    return cognix_integration_manager.build_integration_status(
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )


@router.post("/integrations/plan")
async def plan_integration(
    payload: IntegrationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_integration_manager.build_integration_plan(
        tool_id = payload.tool_id,
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "integration_plan_built",
        resource_type = "cognix_integration",
        resource_id = str(payload.tool_id),
        severity = "warning" if plan.get("humanApprovalRequired") else "notice",
        metadata = {
            "integrationManagerVersion": plan.get("integrationManagerVersion"),
            "toolId": plan.get("toolId"),
            "connector": plan.get("connector"),
            "status": plan.get("status"),
            "allowedToActivate": plan.get("allowedToActivate"),
            "humanApprovalRequired": plan.get("humanApprovalRequired"),
            "missingPermissions": plan.get("integration", {}).get("missingPermissions", []),
            "nextActionIds": [
                item.get("id") for item in plan.get("nextActions", []) if isinstance(item, dict)
            ],
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    plan["auditLogId"] = audit.get("id")
    return plan


@router.post("/tools/plan")
async def plan_tool_action(
    payload: ToolActionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = payload.tool_id,
        action_id = payload.action_id,
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    rate_limit = None
    rate_limit_policy = plan.get("rateLimitPolicy")
    rate_limit_key = plan.get("rateLimitKey")
    if isinstance(rate_limit_policy, dict) and rate_limit_key:
        try:
            rate_limit = cognix_db.check_rate_limit(
                username = current_subject,
                rate_limit_key = str(rate_limit_key),
                action = "tool_action_planned",
                window_seconds = int(rate_limit_policy.get("windowSeconds") or 60),
                max_events = int(rate_limit_policy.get("maxEvents") or 60),
                consume = True,
            )
        except ValueError:
            rate_limit = {
                "allowed": False,
                "rateLimitKey": rate_limit_key,
                "reason": "Invalid rate limit key",
            }
        plan["rateLimit"] = rate_limit
        if not rate_limit.get("allowed"):
            plan["allowed"] = False
            plan["status"] = "rate_limited"
            plan["reason"] = "Tool action rate limit reached."

    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_action_planned",
        resource_type = "cognix_tool_action",
        resource_id = f"{payload.tool_id}:{payload.action_id}",
        severity = "notice" if plan.get("allowed") else "warning",
        metadata = {
            "toolRegistryVersion": plan.get("registryVersion"),
            "toolId": plan.get("toolId"),
            "actionId": plan.get("actionId"),
            "status": plan.get("status"),
            "riskLevel": plan.get("riskLevel"),
            "requiresConfirmation": plan.get("requiresConfirmation"),
            "guardrails": plan.get("guardrails", {}),
            "missingPermissions": plan.get("missingPermissions", []),
            "rateLimit": rate_limit,
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    plan["auditLogId"] = audit.get("id")
    return plan


@router.get("/models/cache")
async def model_cache_state(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    runtime = _current_model_cache_runtime()
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = runtime.get("activeModel"),
        loaded_models = runtime.get("loadedModels") or [],
        loading_models = runtime.get("loadingModels") or [],
        runtime_type = str(runtime.get("runtimeType") or "unknown"),
        project_id = project_id,
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "runtimeError": runtime.get("error"),
        "cache": cache,
    }


@router.post("/models/cache/load-plan")
async def model_cache_load_plan(
    payload: ModelCacheLoadPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    runtime = _current_model_cache_runtime()
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = runtime.get("activeModel"),
        loaded_models = runtime.get("loadedModels") or [],
        loading_models = runtime.get("loadingModels") or [],
        runtime_type = str(runtime.get("runtimeType") or "unknown"),
        project_id = payload.project_id,
    )
    load_plan = cognix_cache_manager.build_cache_load_plan(
        hardware,
        cache_state = cache,
        target_model_id = payload.model_id,
        target_runtime_type = payload.runtime_type,
        estimated_ram_gb = payload.estimated_ram_gb,
        project_id = payload.project_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "cache_load_plan_built",
        resource_type = "cognix_cache_load_plan",
        resource_id = str(load_plan.get("target", {}).get("modelId") or payload.model_id),
        severity = "warning" if load_plan.get("blockedReasons") else "notice",
        metadata = {
            "managerVersion": load_plan.get("managerVersion"),
            "targetModelId": load_plan.get("target", {}).get("modelId"),
            "runtimeType": load_plan.get("target", {}).get("runtimeType"),
            "allowedToPrepare": load_plan.get("allowedToPrepare"),
            "requiredEvictionCount": load_plan.get("capacity", {}).get("requiredEvictionCount"),
            "selectedEvictions": [
                item.get("modelId")
                for item in load_plan.get("selectedEvictions", [])
                if isinstance(item, dict)
            ],
            "memoryGuardStatus": load_plan.get("memoryGuard", {}).get("status"),
            "sideEffects": load_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "runtimeError": runtime.get("error"),
        "cache": cache,
        "loadPlan": load_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": load_plan.get("sideEffects", {}),
    }


@router.post("/models/preload-plan")
async def model_preload_plan(
    payload: PreloadPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
    )
    preload_plan = plan["preloadPlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "preload_plan_built",
        resource_type = "cognix_preload_plan",
        resource_id = str(preload_plan.get("target", {}).get("modelId") or "none"),
        severity = "notice",
        metadata = {
            "plannerVersion": preload_plan.get("plannerVersion"),
            "domain": preload_plan.get("target", {}).get("domain"),
            "modelRole": preload_plan.get("target", {}).get("modelRole"),
            "actionTypes": [
                item.get("type")
                for item in preload_plan.get("actions", [])
                if isinstance(item, dict)
            ],
            "sideEffects": preload_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "cache": plan["cache"],
        "preloadPlan": preload_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": preload_plan.get("sideEffects", {}),
    }


@router.post("/fine-tuning/plan")
async def fine_tuning_plan(
    payload: FineTuningPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    user_profile = auth_storage.get_user_profile(current_subject) or {}
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        fine_tuning_dataset = payload.dataset,
        user_plan = str(user_profile.get("plan") or ""),
    )
    tuning_plan = plan["fineTuningPlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "fine_tuning_plan_built",
        resource_type = "cognix_fine_tuning_plan",
        resource_id = str(tuning_plan.get("baseModel", {}).get("modelId") or "none"),
        severity = "warning" if tuning_plan.get("approval", {}).get("required") else "notice",
        metadata = {
            "plannerVersion": tuning_plan.get("plannerVersion"),
            "recommendedPath": tuning_plan.get("recommendedPath"),
            "targetDomain": tuning_plan.get("targetDomain"),
            "method": tuning_plan.get("method", {}).get("type"),
            "resourceTarget": tuning_plan.get("resourceTargetPlan", {}).get("recommendedTargetId"),
            "datasetStatus": tuning_plan.get("dataset", {}).get("status"),
            "approval": tuning_plan.get("approval", {}),
            "sideEffects": tuning_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "fineTuningPlan": tuning_plan,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": tuning_plan.get("sideEffects", {}),
    }


@router.get("/rag/sources")
async def rag_source_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    registry = cognix_rag_planner.build_rag_source_registry(
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "rag_source_registry_built",
        resource_type = "cognix_rag_source_registry",
        resource_id = str(registry.get("registryVersion")),
        severity = "notice",
        metadata = {
            "registryVersion": registry.get("registryVersion"),
            "plannerVersion": registry.get("plannerVersion"),
            "connectorCount": registry.get("summary", {}).get("connectorCount"),
            "readyForIndexingCount": registry.get("summary", {}).get("readyForIndexingCount"),
            "sideEffects": registry.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "registry": registry,
        "auditLogId": audit.get("id"),
        "sideEffects": registry.get("sideEffects", {}),
    }


@router.post("/rag/indexing-plan")
async def rag_indexing_plan(
    payload: RagIndexingPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_rag_planner.build_rag_indexing_plan(
        username = current_subject,
        project_id = payload.project_id,
        sources = payload.sources or [],
        objective = payload.objective,
        rag_available = _rag_available(),
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "rag_indexing_plan_built",
        resource_type = "cognix_rag_indexing_plan",
        resource_id = str(payload.project_id or "general"),
        severity = "warning" if plan.get("status") in {"blocked", "missing_sources"} else "notice",
        metadata = {
            "plannerVersion": plan.get("plannerVersion"),
            "sourceRegistryVersion": plan.get("sourceRegistryVersion"),
            "status": plan.get("status"),
            "sourceCount": plan.get("summary", {}).get("sourceCount"),
            "readyToIndexCount": plan.get("summary", {}).get("readyToIndexCount"),
            "blockedSourceCount": plan.get("summary", {}).get("blockedSourceCount"),
            "missingPermissionCount": plan.get("summary", {}).get("missingPermissionCount"),
            "requiresHumanConfirmation": plan.get("requiresHumanConfirmation"),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "indexingPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
    }


@router.post("/fine-tuning/cloud-handoff-plan")
async def fine_tuning_cloud_handoff_plan(
    payload: FineTuningCloudHandoffPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    user_profile = auth_storage.get_user_profile(current_subject) or {}
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        fine_tuning_dataset = payload.dataset,
        user_plan = str(user_profile.get("plan") or ""),
    )
    tuning_plan = plan["fineTuningPlan"]
    handoff = cognix_fine_tuning_planner.build_cloud_training_handoff_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        target_id = payload.target_id,
        fine_tuning_plan = tuning_plan,
        dataset = payload.dataset,
        user_plan = str(user_profile.get("plan") or ""),
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "fine_tuning_cloud_handoff_plan_built",
        resource_type = "cognix_cloud_training_handoff",
        resource_id = str(handoff.get("target", {}).get("id") or "unknown"),
        severity = "notice" if handoff.get("readyToExport") else "warning",
        metadata = {
            "plannerVersion": handoff.get("plannerVersion"),
            "handoffVersion": handoff.get("handoffVersion"),
            "status": handoff.get("status"),
            "targetId": handoff.get("target", {}).get("id"),
            "exportFormat": handoff.get("target", {}).get("exportFormat"),
            "method": handoff.get("method", {}).get("type"),
            "datasetStatus": handoff.get("dataset", {}).get("status"),
            "readyToExport": handoff.get("readyToExport"),
            "approval": handoff.get("approval", {}),
            "sideEffects": handoff.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "fineTuningPlan": tuning_plan,
        "cloudHandoffPlan": handoff,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": handoff.get("sideEffects", {}),
    }


@router.post("/rag/plan")
async def rag_plan(
    payload: RagPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        rag_sources = payload.sources or [],
        rag_available = _rag_available(),
    )
    rag = plan["ragPlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "rag_plan_built",
        resource_type = "cognix_rag_plan",
        resource_id = str(payload.project_id or rag.get("targetDomain") or "general"),
        severity = "warning" if rag.get("recommendedPath") == "rag_first" and not rag.get("readyForRetrieval") else "notice",
        metadata = {
            "plannerVersion": rag.get("plannerVersion"),
            "recommendedPath": rag.get("recommendedPath"),
            "readyForRetrieval": rag.get("readyForRetrieval"),
            "retrievalStrategy": rag.get("retrieval", {}).get("strategy"),
            "sourceCount": rag.get("sourceReadiness", {}).get("sourceCount"),
            "indexedSourceCount": rag.get("sourceReadiness", {}).get("indexedSourceCount"),
            "sideEffects": rag.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "ragPlan": rag,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": rag.get("sideEffects", {}),
    }


@router.post("/optimizations/plan")
async def optimization_plan(
    payload: OptimizationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        rag_available = _rag_available(),
    )
    optimization = plan["optimizationPlan"]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "optimization_plan_built",
        resource_type = "cognix_optimization_plan",
        resource_id = str(payload.project_id or optimization.get("optimizationProfile") or "general"),
        severity = "warning" if optimization.get("warnings") else "notice",
        metadata = {
            "optimizationPlannerVersion": optimization.get("plannerVersion"),
            "optimizationProfile": optimization.get("optimizationProfile"),
            "hardwareTier": optimization.get("hardwareTier"),
            "runtimeType": optimization.get("runtimeType"),
            "recommendedOptimizationIds": optimization.get("recommendedOptimizationIds", []),
            "sideEffects": optimization.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "optimizationPlan": optimization,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": optimization.get("sideEffects", {}),
        "plannerVersion": cognix_optimization_planner.COGNIX_OPTIMIZATION_PLANNER_VERSION,
    }


@router.post("/router/classify")
async def classify_route(
    payload: RouterClassifyRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    classification = classify_objective(
        payload.objective,
        project_type = payload.project_type,
    )
    log = cognix_db.create_router_log(
        current_subject,
        payload.objective,
        project_type = payload.project_type,
        classification = classification,
    )
    return {
        "username": current_subject,
        "classification": classification,
        "logId": log.get("id"),
    }


@router.post("/orchestrator/plan")
async def orchestrator_plan(
    payload: OrchestratorPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = {
        "runtimeType": "dry_run",
        "activeModel": None,
        "loadedModels": [],
        "loadingModels": [],
    }
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
    )
    log = cognix_db.create_router_log(
        current_subject,
        payload.objective,
        project_type = payload.project_type,
        classification = plan["classification"],
    )
    orchestrator_log = cognix_db.create_orchestrator_log(
        current_subject,
        payload.objective,
        project_type = payload.project_type,
        project_id = payload.project_id,
        plan = plan,
    )
    return {
        **plan,
        "runtimeError": None,
        "logId": log.get("id"),
        "orchestratorLogId": orchestrator_log.get("id"),
    }


@router.get("/permissions/me")
async def my_permissions(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    profile = auth_storage.get_user_profile(current_subject)
    is_admin = bool(profile and profile.get("role") == "admin")
    return {
        "username": current_subject,
        "developerMode": is_admin
        or cognix_db.user_has_permission(current_subject, cognix_db.DEVELOPER_MODE_PERMISSION),
        "admin": is_admin,
    }


@router.post("/approvals/developer-mode")
async def request_developer_mode(
    payload: ApprovalCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if auth_storage.is_admin(current_subject):
        return {
            "request": _row(
                {
                    "id": "admin-self-approved",
                    "username": current_subject,
                    "request_type": cognix_db.DEVELOPER_MODE_PERMISSION,
                    "reason": "Admin account",
                    "status": "approved",
                }
            )
        }
    if cognix_db.user_has_permission(current_subject, cognix_db.DEVELOPER_MODE_PERMISSION):
        return {
            "request": _row(
                {
                    "id": "already-approved",
                    "username": current_subject,
                    "request_type": cognix_db.DEVELOPER_MODE_PERMISSION,
                    "reason": "Developer mode permission already granted",
                    "status": "approved",
                }
            )
        }
    request = cognix_db.create_approval_request(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
        payload.reason,
    )
    return {"request": _row(request)}


@router.get("/approvals/me")
async def my_approval_requests(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"requests": _rows(cognix_db.list_approval_requests(username = current_subject))}


@router.post("/reports")
async def create_report(
    payload: ReportCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    report = cognix_db.create_report(
        current_subject,
        payload.category,
        payload.title,
        payload.message,
    )
    return {"report": _row(report)}


@router.get("/reports/me")
async def my_reports(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"reports": _rows(cognix_db.list_reports(username = current_subject))}


@router.get("/context-memory")
async def get_my_context_memory(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"memory": _row(cognix_db.get_context_memory(current_subject))}


@router.put("/context-memory")
async def update_my_context_memory(
    payload: ContextMemoryRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    memory = cognix_db.update_context_memory(current_subject, payload.content, current_subject)
    return {"memory": _row(memory)}


@router.get("/memory/blueprint")
async def memory_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "blueprint": cognix_memory_manager.build_memory_blueprint(),
        "plannerVersion": cognix_memory_manager.COGNIX_MEMORY_MANAGER_VERSION,
    }


@router.post("/memory/plan")
async def memory_plan(
    payload: MemoryPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    warnings: list[str] = []
    project: dict[str, Any] | None = None
    if payload.project_id:
        project = get_chat_project(
            payload.project_id,
            owner_username = current_subject,
            include_all = False,
        )
        if project is None or project.get("archived"):
            raise HTTPException(status_code = 404, detail = "Project not found")

    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    classification = classify_objective(payload.objective or payload.project_type or "general")
    task_strategy = cognix_decision_engine.build_task_strategy(
        payload.objective or payload.project_type or "general",
        classification = classification,
    )
    user_memory = cognix_db.get_context_memory(current_subject)
    library_items = _rows(cognix_db.list_library_items(current_subject))
    context_plan = cognix_context_manager.build_context_plan(
        current_subject = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        classification = classification,
        task_strategy = task_strategy,
        recommendation = recommendation_payload["recommendation"],
        user_memory = user_memory,
        project = project,
        conversation_summary = payload.conversation_summary,
        recent_messages = [{} for _ in range(payload.recent_message_count)],
        warnings = warnings,
    )
    plan = cognix_memory_manager.build_memory_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        project_type = payload.project_type,
        user_memory = user_memory,
        project = project,
        conversation_summary = payload.conversation_summary,
        recent_message_count = payload.recent_message_count,
        library_items = library_items,
        hardware = hardware,
        latest_benchmark_run = latest_benchmark,
        classification = classification,
        task_strategy = task_strategy,
        context_plan = context_plan,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "memory_plan_built",
        resource_type = "cognix_memory",
        resource_id = str(payload.project_id or current_subject),
        severity = "warning" if plan.get("warnings") else "notice",
        metadata = {
            "memoryManagerVersion": plan.get("memoryManagerVersion"),
            "projectId": payload.project_id,
            "projectType": payload.project_type,
            "targetDomain": plan.get("targetDomain"),
            "readyLayerIds": plan.get("readyLayerIds", []),
            "requiredLayerIds": plan.get("requiredLayerIds", []),
            "captureActionIds": [
                item.get("id") for item in plan.get("capturePlan", []) if isinstance(item, dict)
            ],
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "latestBenchmark": latest_benchmark,
        "classification": classification,
        "taskStrategy": task_strategy,
        "contextPlan": context_plan,
        "memoryPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_memory_manager.COGNIX_MEMORY_MANAGER_VERSION,
    }


@router.get("/research/watch-registry")
async def research_watch_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_research_watch.build_research_watch_registry(),
        "plannerVersion": cognix_research_watch.COGNIX_RESEARCH_WATCH_VERSION,
    }


@router.post("/research/integration-plan")
async def research_integration_plan(
    payload: ResearchIntegrationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    plan = cognix_research_watch.build_research_integration_plan(
        objective = payload.objective,
        technique_name = payload.technique_name,
        source_name = payload.source_name,
        category = payload.category,
        claimed_benefit = payload.claimed_benefit,
        target_module = payload.target_module,
        risk_tolerance = payload.risk_tolerance,
        hardware = hardware,
        latest_benchmark_run = latest_benchmark,
        recommendation = recommendation_payload["recommendation"],
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "research_integration_plan_built",
        resource_type = "cognix_research_watch",
        resource_id = str(plan.get("request", {}).get("techniqueName") or plan.get("source", {}).get("id") or "research-watch"),
        severity = "warning" if plan.get("warnings") else "notice",
        metadata = {
            "researchWatchVersion": plan.get("researchWatchVersion"),
            "sourceId": plan.get("source", {}).get("id"),
            "categoryId": plan.get("category", {}).get("id"),
            "recommendedAction": plan.get("recommendedAction"),
            "integrationPhase": plan.get("integrationPhase"),
            "blockedGateIds": plan.get("blockedGateIds", []),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "latestBenchmark": latest_benchmark,
        "recommendation": recommendation_payload["recommendation"],
        "researchIntegrationPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_research_watch.COGNIX_RESEARCH_WATCH_VERSION,
    }


@router.post("/context/pack")
async def build_context_pack(
    payload: ContextPackRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    warnings: list[str] = []
    project: dict[str, Any] | None = None
    if payload.project_id:
        project = get_chat_project(
            payload.project_id,
            owner_username = current_subject,
            include_all = False,
        )
        if project is None or project.get("archived"):
            project = None
            warnings.append("Project context unavailable for this user.")

    packet = cognix_context_manager.build_context_packet(
        current_subject = current_subject,
        user_memory = cognix_db.get_context_memory(current_subject),
        project = project,
        project_id = payload.project_id,
        objective = payload.objective,
        warnings = warnings,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "context_pack_built",
        resource_type = "cognix_context",
        resource_id = payload.project_id,
        metadata = {
            "contextManagerVersion": packet.get("contextManagerVersion"),
            "mode": packet.get("mode"),
            "projectId": payload.project_id,
            "objectiveChars": len(payload.objective or ""),
            "assemblyStrategy": packet.get("contextPlan", {}).get("assemblyStrategy"),
            "rawHistoryAllowed": packet.get("contextPlan", {}).get("tokenBudget", {}).get("rawHistoryAllowed"),
            "sectionIds": packet.get("includedSectionIds", []),
            "channelIds": packet.get("contextPlan", {}).get("includedChannelIds", []),
            "warnings": warnings,
            "sideEffects": packet.get("sideEffects", {}),
        },
    )
    packet["auditLogId"] = audit.get("id")
    return packet


@router.get("/library")
async def my_library(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"items": _rows(cognix_db.list_library_items(current_subject))}


@router.post("/library")
async def create_library_item(
    payload: LibraryItemRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    item = cognix_db.create_library_item(
        current_subject,
        kind = payload.kind,
        name = payload.name,
        source = payload.source,
        size_bytes = payload.size_bytes,
        uri = payload.uri,
        metadata = payload.metadata,
    )
    return {"item": _row(item)}


@router.get("/scheduled-tasks")
async def my_scheduled_tasks(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "tasks": _rows(cognix_db.list_scheduled_tasks(current_subject)),
        "runs": _rows(cognix_db.list_scheduled_task_runs(current_subject)),
    }


@router.post("/scheduled-tasks")
async def create_scheduled_task(
    payload: ScheduledTaskCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    task = cognix_db.create_scheduled_task(
        current_subject,
        payload.title,
        payload.prompt,
        payload.schedule_text,
    )
    return {"task": _row(task)}


@router.patch("/scheduled-tasks/{task_id}")
async def update_scheduled_task(
    task_id: str,
    payload: ScheduledTaskStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        task = cognix_db.update_scheduled_task_status(current_subject, task_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if task is None:
        raise HTTPException(status_code = 404, detail = "Scheduled task not found")
    return {"task": _row(task)}


@router.post("/scheduled-tasks/{task_id}/run")
async def run_scheduled_task(
    task_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    task = cognix_db.get_scheduled_task(current_subject, task_id)
    if not task:
        raise HTTPException(status_code = 404, detail = "Scheduled task not found")
    if task.get("status") not in {"active", "paused"}:
        raise HTTPException(status_code = 400, detail = "Scheduled task cannot run in this state")
    try:
        run = _execute_scheduled_task(current_subject, task)
    except Exception as exc:
        run = cognix_db.create_scheduled_task_run(
            current_subject,
            task_id,
            "error",
            str(exc),
            status = "failed",
        )
    return {"run": _row(run)}


@router.get("/apps")
async def my_apps(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "catalog": APP_CATALOG,
        "connections": _rows(cognix_db.list_app_connections(current_subject)),
    }


@router.post("/apps/connections")
async def set_app_connection(
    payload: AppConnectionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        connection = cognix_db.set_app_connection(
            current_subject,
            payload.app_id,
            payload.app_name,
            payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    return {"connection": _row(connection)}


@router.get("/social/messages")
async def social_messages(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"messages": _rows(cognix_db.list_social_messages())}


@router.post("/social/messages")
async def create_social_message(
    payload: SocialMessageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    profile = auth_storage.get_user_profile(current_subject) or {}
    message = cognix_db.create_social_message(
        current_subject,
        profile.get("displayName") or current_subject,
        profile.get("role") or "user",
        payload.content,
    )
    return {"message": _row(message)}


@router.post("/social/agent-reply")
async def create_social_agent_reply(
    payload: SocialAgentRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    recent_messages = cognix_db.list_social_messages(limit = 12)
    visible = [
        f"{item.get('display_name') or item.get('username')}: {item.get('content')}"
        for item in recent_messages[-6:]
        if item.get("content")
    ]
    prompt = _strip_html(payload.prompt or "")
    if prompt:
        content = f"CogniX Orchestrateur: je prends en compte la demande '{prompt}'. "
    else:
        content = "CogniX Orchestrateur: je rejoins le salon. "
    if visible:
        content += "Derniers sujets detectes: " + "; ".join(visible[-3:])
    else:
        content += "Aucun sujet actif pour le moment."
    message = cognix_db.create_social_message(
        "cognix-orchestrateur",
        "CogniX Orchestrateur",
        "ai",
        content[:2000],
    )
    return {"message": _row(message)}


@router.get("/model-pins")
async def my_model_pins(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"pins": _rows(cognix_db.list_model_pins(current_subject))}


@router.post("/model-pins")
async def pin_model(
    payload: ModelPinRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "pin": _row(
            cognix_db.set_model_pin(
                current_subject,
                payload.model_id,
                payload.label,
            )
        )
    }


@router.delete("/model-pins/{model_id}")
async def unpin_model(
    model_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    cognix_db.delete_model_pin(current_subject, model_id)
    return {"ok": True}


@router.get("/project-model-defaults")
async def my_project_model_defaults(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"defaults": _rows(cognix_db.list_project_model_defaults(current_subject))}


@router.get("/project-experts/registry")
async def project_expert_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "registry": cognix_project_experts.build_project_expert_registry(),
    }


@router.get("/projects/{project_id}/default-model")
async def get_project_default_model(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    default_model = cognix_db.get_project_model_default(project_id, current_subject)
    return {"defaultModel": _row(default_model) if default_model else None}


@router.put("/projects/{project_id}/default-model")
async def set_project_default_model(
    project_id: str,
    payload: ProjectDefaultModelRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    try:
        default_model = cognix_db.set_project_model_default(
            current_subject,
            project_id,
            payload.model_id,
            payload.label,
            provider_type = payload.provider_type,
            provider_id = payload.provider_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    return {"defaultModel": _row(default_model)}


@router.delete("/projects/{project_id}/default-model")
async def delete_project_default_model(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    cognix_db.delete_project_model_default(current_subject, project_id)
    return {"ok": True}


@router.post("/projects/{project_id}/expert-plan")
async def project_expert_plan(
    project_id: str,
    payload: ProjectExpertPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project = _require_owned_project(project_id, current_subject)
    runtime = _current_model_cache_runtime()
    default_model = cognix_db.get_project_model_default(project_id, current_subject)
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        rag_available = _rag_available(),
    )
    expert_plan = cognix_project_experts.build_project_expert_plan(
        objective = payload.objective,
        project_id = project_id,
        project_type = payload.project_type,
        project_default_model = default_model,
        classification = plan["classification"],
        recommendation = plan["recommendation"],
        preload_plan = plan["preloadPlan"],
        rag_plan = plan["ragPlan"],
        context_plan = plan["contextPlan"],
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_expert_plan_built",
        resource_type = "cognix_project_expert",
        resource_id = project_id,
        severity = "warning" if expert_plan.get("warnings") else "notice",
        metadata = {
            "projectExpertsVersion": expert_plan.get("projectExpertsVersion"),
            "projectId": project_id,
            "projectType": expert_plan.get("projectType"),
            "primaryExpertId": expert_plan.get("primaryExpert", {}).get("expertId"),
            "primaryDomain": expert_plan.get("primaryExpert", {}).get("domain"),
            "selectedModelId": expert_plan.get("primaryExpert", {}).get("selectedModel", {}).get("modelId"),
            "selectionSource": expert_plan.get("selectionSource"),
            "secondaryExpertIds": [
                item.get("expertId") for item in expert_plan.get("secondaryExperts", []) if isinstance(item, dict)
            ],
            "sideEffects": expert_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "project": _row(project),
        "defaultModel": _row(default_model) if default_model else None,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "projectExpertPlan": expert_plan,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": expert_plan.get("sideEffects", {}),
        "plannerVersion": cognix_project_experts.COGNIX_PROJECT_EXPERTS_VERSION,
    }


@router.get("/project-shares")
async def my_project_shares(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    shares = _rows(cognix_db.list_project_shares(current_subject, project_id))
    for share in shares:
        share["shareUrl"] = f"/share/project/{share.get('token')}"
    return {
        "shares": shares,
        "collaborators": _rows(cognix_db.list_project_collaborators(owner_username = current_subject)),
        "accepted": _rows(cognix_db.list_project_collaborators(collaborator_username = current_subject)),
    }


@router.get("/project-shares/public/{token}")
async def public_project_share(token: str) -> dict[str, Any]:
    share = cognix_db.get_project_share_by_token(token)
    if not share or share.get("revoked_at"):
        raise HTTPException(status_code = 404, detail = "Project share not found")
    return {
        "share": _row(
            {
                "id": share.get("id"),
                "project_id": share.get("project_id"),
                "owner_username": share.get("owner_username"),
                "permission": share.get("permission"),
                "created_at": share.get("created_at"),
                "revoked_at": share.get("revoked_at"),
            }
        )
    }


@router.post("/project-shares")
async def create_project_share(
    payload: ProjectShareCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        share = _row(
            cognix_db.create_project_share(
                current_subject,
                payload.project_id,
                payload.permission,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    share["shareUrl"] = f"/share/project/{share.get('token')}"
    return {"share": share}


@router.post("/project-shares/public/{token}/accept")
async def accept_public_project_share(
    token: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    collaborator = cognix_db.accept_project_share(token, current_subject)
    if not collaborator:
        raise HTTPException(status_code = 404, detail = "Project share not found")
    return {"collaborator": _row(collaborator)}


@router.delete("/project-shares/{share_id}")
async def revoke_project_share(
    share_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    share = cognix_db.revoke_project_share(current_subject, share_id)
    if share is None:
        raise HTTPException(status_code = 404, detail = "Share not found")
    return {"share": _row(share)}


def _thread_created_at_ms(thread: dict[str, Any]) -> int:
    value = thread.get("createdAt") or thread.get("created_at") or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@router.get("/news")
async def my_news(
    topic: str = "intelligence artificielle",
    refresh: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if refresh:
        for item in _fetch_feed_items(topic, limit = 12):
            cognix_db.create_news_item(
                current_subject,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
    items = cognix_db.list_news_items(current_subject, topic)
    if not items and not refresh:
        for item in _fetch_feed_items(topic, limit = 8):
            cognix_db.create_news_item(
                current_subject,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
        items = cognix_db.list_news_items(current_subject, topic)
    return {"items": _rows(items), "topic": topic}


@router.post("/news/refresh")
async def refresh_news(
    payload: NewsRefreshRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    topic = payload.topic.strip() or "intelligence artificielle"
    created = []
    for item in _fetch_feed_items(topic, limit = 12):
        created.append(
            cognix_db.create_news_item(
                current_subject,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
        )
    return {"items": _rows(cognix_db.list_news_items(current_subject, topic)), "created": len(created)}


@router.get("/research")
async def my_research(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"reports": _rows(cognix_db.list_research_reports(current_subject))}


@router.post("/research")
async def create_research(
    payload: ResearchRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    query = payload.query.strip()
    sources = _fetch_feed_items(query, limit = 6)
    report = cognix_db.create_research_report(
        current_subject,
        query,
        "Recherche approfondie: " + query[:90],
        _research_summary(query, sources),
        [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "source": item.get("source"),
                "publishedAt": item.get("published_at"),
            }
            for item in sources
        ],
    )
    cognix_db.create_library_item(
        current_subject,
        kind = "document",
        name = report.get("title") or ("Recherche " + query[:60]),
        source = "deep_research",
        metadata = {"researchReportId": report.get("id"), "query": query},
    )
    return {"report": _row(report)}


@router.get("/agent-runs")
async def my_agent_runs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"runs": _rows(cognix_db.list_agent_runs(current_subject))}


@router.post("/agent-runs")
async def create_agent_run(
    payload: AgentRunRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    goal = payload.goal.strip()
    plan = _agent_plan(goal, payload.mode)
    result = (
        "Plan prepare. CogniX Orchestrateur peut maintenant suivre les etapes, "
        "demander les permissions necessaires et produire un compte rendu."
    )
    run = cognix_db.create_agent_run(current_subject, goal, payload.mode, plan, result)
    return {"run": _row(run)}


@router.get("/games")
async def my_games(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"games": _rows(cognix_db.list_game_sessions(current_subject))}


@router.post("/games")
async def create_game(
    payload: GameCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        game = cognix_db.create_game_session(
            current_subject,
            payload.game_type,
            payload.opponent_type,
            payload.opponent_username,
            _game_initial_state(payload.game_type),
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    return {"game": _row(game)}


@router.post("/games/{game_id}/move")
async def play_game_move(
    game_id: str,
    payload: GameMoveRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    game = cognix_db.get_game_session(current_subject, game_id)
    if not game:
        raise HTTPException(status_code = 404, detail = "Game not found")
    if game.get("game_type") != "chess":
        raise HTTPException(status_code = 400, detail = "Only chess moves are supported for now")
    if game.get("status") not in {"active", "pending"}:
        raise HTTPException(status_code = 400, detail = "Game is not active")

    state = _normalize_chess_state(game.get("state"))
    try:
        state = _apply_chess_move(state, payload.from_square.lower(), payload.to_square.lower(), "user")
        if game.get("opponent_type") == "ai" and not state.get("winner"):
            state = _apply_ai_chess_reply(state)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc

    status_value = "complete" if state.get("winner") else "active"
    updated = cognix_db.update_game_session(
        current_subject,
        game_id,
        status = status_value,
        state = state,
    )
    return {"game": _row(updated or {})}


@router.get("/pulse")
async def my_pulse(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"reports": _rows(cognix_db.list_pulse_reports(current_subject))}


@router.post("/pulse/generate")
async def generate_pulse(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    threads = list_chat_threads(
        include_archived = True,
        owner_username = current_subject,
    )
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(hours = 24)).timestamp() * 1000)
    recent_threads = [
        thread
        for thread in threads
        if _thread_created_at_ms(thread) >= cutoff_ms
    ]
    source_threads = recent_threads[:12] if recent_threads else threads[:6]
    topics = [
        str(thread.get("title") or "Conversation").strip()[:80]
        for thread in source_threads
        if str(thread.get("title") or "").strip()
    ]
    if not topics:
        topics = ["Activite CogniX", "Suivi personnel", "Idees a reprendre"]
    summary = (
        "Pulse a rassemble les conversations recentes et prepare une base de recherche "
        "sur les sujets suivants: "
        + ", ".join(topics[:6])
        + "."
    )
    report = cognix_db.create_pulse_report(
        current_subject,
        "Pulse des dernieres 24h",
        summary,
        topics[:12],
        [str(thread.get("id")) for thread in source_threads if thread.get("id")],
    )
    return {"report": _row(report)}


@router.get("/images")
async def my_images(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"images": _rows(cognix_db.list_image_history(current_subject))}


@router.post("/images")
async def create_image(
    payload: ImageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    image = cognix_db.create_image_request(current_subject, payload.prompt, payload.model)
    cognix_db.create_library_item(
        current_subject,
        kind = "image",
        name = payload.prompt[:80] or "Image CogniX",
        source = "image_generation",
        metadata = {"imageRequestId": image.get("id"), "status": image.get("status")},
    )
    return {"image": _row(image)}


@router.get("/admin/dashboard")
async def admin_dashboard(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    users = auth_storage.list_user_profiles()
    threads = list_chat_threads(
        include_archived = True,
        owner_username = current_subject,
        include_all = True,
    )
    projects = list_chat_projects(
        include_archived = True,
        owner_username = current_subject,
        include_all = True,
    )
    messages = list_chat_messages_for_threads([thread["id"] for thread in threads])
    usage = cognix_db.summarize_compute_usage(threads, messages)
    approvals = cognix_db.list_approval_requests()
    bans = cognix_db.list_bans()
    threats = cognix_db.list_security_events(limit = 200)
    reports = cognix_db.list_reports()
    collaborators = cognix_db.list_project_collaborators()
    user_details = _build_dashboard_user_details(
        users = users,
        threads = threads,
        projects = projects,
        usage = usage,
        security_events = threats,
        bans = bans,
        reports = reports,
        collaborators = collaborators,
    )
    return {
        "summary": {
            "users": len(users),
            "conversations": len(threads),
            "projects": len(projects),
            "approvalsPending": sum(1 for item in approvals if item.get("status") == "pending"),
            "activeBans": sum(
                1
                for item in bans
                if item.get("status") in {"pending_admin_review", "active", "permanent"}
            ),
            "securityThreats": len(threats),
            "reportsOpen": sum(1 for item in reports if item.get("status") in {"open", "in_review"}),
        },
        "users": [dict(user, dashboard = user_details.get(str(user.get("username") or ""), {})) for user in users],
        "dashboardUsers": user_details,
        "threads": threads,
        "projects": projects,
        "projectCollaborators": _rows(collaborators),
        "computeUsage": usage,
        "approvals": _rows(approvals),
        "bans": _rows(bans),
        "securityThreats": _rows(threats),
        "reports": _rows(reports),
        "knownAttacks": [
            {
                "id": item["id"],
                "label": item["label"],
                "severity": item["severity"],
            }
            for item in cognix_db.KNOWN_ATTACK_SIGNATURES
        ],
    }


@router.get("/admin/approvals")
async def admin_approvals(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"requests": _rows(cognix_db.list_approval_requests())}


@router.patch("/admin/approvals/{request_id}")
async def admin_decide_approval(
    request_id: str,
    payload: ApprovalDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        request = cognix_db.set_approval_status(
            request_id,
            payload.status,
            decided_by = current_subject,
            admin_note = payload.admin_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if request is None:
        raise HTTPException(status_code = 404, detail = "Approval request not found")
    return {"request": _row(request)}


@router.get("/admin/permissions/{username}")
async def admin_user_permissions(
    username: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "username": username,
        "permissions": _rows(cognix_db.list_user_permissions(username)),
    }


@router.post("/admin/permissions/{username}")
async def admin_grant_permission(
    username: str,
    payload: AdminPermissionGrantRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        permission = cognix_db.grant_user_permission(
            username,
            payload.permission_key,
            granted_by = current_subject,
            expires_at = payload.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "permission_granted",
        resource_type = "cognix_user_permission",
        resource_id = permission.get("permission_key"),
        severity = "notice",
        metadata = {
            "permissionKey": permission.get("permission_key"),
            "expiresAt": permission.get("expires_at"),
        },
    )
    return {
        "permission": _row(permission),
        "auditLogId": audit.get("id"),
    }


@router.delete("/admin/permissions/{username}/{permission_key}")
async def admin_revoke_permission(
    username: str,
    permission_key: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        revoked = cognix_db.revoke_user_permission(username, permission_key)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "permission_revoked",
        resource_type = "cognix_user_permission",
        resource_id = permission_key,
        severity = "notice" if revoked else "warning",
        metadata = {
            "permissionKey": permission_key,
            "revoked": revoked,
        },
    )
    return {
        "revoked": revoked,
        "auditLogId": audit.get("id"),
    }


@router.get("/admin/bans")
async def admin_bans(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"bans": _rows(cognix_db.list_bans())}


@router.patch("/admin/bans/{ban_id}")
async def admin_update_ban(
    ban_id: str,
    payload: BanStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        ban = cognix_db.update_ban_status(
            ban_id,
            payload.status,
            decided_by = current_subject,
            admin_decision = payload.admin_decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if ban is None:
        raise HTTPException(status_code = 404, detail = "Ban not found")
    return {"ban": _row(ban)}


@router.get("/admin/security-threats")
async def admin_security_threats(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "threats": _rows(cognix_db.list_security_events(limit = 500)),
        "knownAttacks": [
            {
                "id": item["id"],
                "label": item["label"],
                "severity": item["severity"],
            }
            for item in cognix_db.KNOWN_ATTACK_SIGNATURES
        ],
    }


@router.get("/admin/router-logs")
async def admin_router_logs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"logs": _rows(cognix_db.list_router_logs(limit = 500))}


@router.get("/admin/orchestrator-logs")
async def admin_orchestrator_logs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"logs": _rows(cognix_db.list_orchestrator_logs(limit = 500))}


@router.get("/admin/benchmark-runs")
async def admin_benchmark_runs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"runs": _rows(cognix_db.list_benchmark_runs(limit = 200))}


@router.get("/admin/audit-logs")
async def admin_audit_logs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"logs": _rows(cognix_db.list_audit_logs(limit = 500))}


@router.get("/admin/reports")
async def admin_reports(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"reports": _rows(cognix_db.list_reports())}


@router.patch("/admin/reports/{report_id}")
async def admin_update_report(
    report_id: str,
    payload: ReportStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        report = cognix_db.update_report_status(report_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if report is None:
        raise HTTPException(status_code = 404, detail = "Report not found")
    return {"report": _row(report)}


@router.get("/admin/context-memory/{username}")
async def admin_get_context_memory(
    username: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"memory": _row(cognix_db.get_context_memory(username))}


@router.put("/admin/context-memory/{username}")
async def admin_update_context_memory(
    username: str,
    payload: ContextMemoryRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    memory = cognix_db.update_context_memory(username, payload.content, current_subject)
    return {"memory": _row(memory)}
