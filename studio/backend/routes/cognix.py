# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX product/admin API routes."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from auth import storage as auth_storage
from auth.authentication import get_current_jwt_subject
from core.cognix import admin_activity as cognix_admin_activity
from core.cognix import admin_approvals as cognix_admin_approvals
from core.cognix import admin_banned as cognix_admin_banned
from core.cognix import admin_chat as cognix_admin_chat
from core.cognix import admin_limits as cognix_admin_limits
from core.cognix import admin_permissions as cognix_admin_permissions
from core.cognix import admin_security as cognix_admin_security
from core.cognix import admin_usage as cognix_admin_usage
from core.cognix import admin_users as cognix_admin_users
from core.cognix import apps as cognix_apps
from core.cognix import benchmark as cognix_benchmark
from core.cognix import background_agents as cognix_background_agents
from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import command_palette as cognix_command_palette
from core.cognix import context_graph as cognix_context_graph
from core.cognix import context_heatmap as cognix_context_heatmap
from core.cognix import context_manager as cognix_context_manager
from core.cognix import cost_optimizer as cognix_cost_optimizer
from core.cognix import dataset_builder as cognix_dataset_builder
from core.cognix import debate_orchestrator as cognix_debate_orchestrator
from core.cognix import deployment_manager as cognix_deployment_manager
from core.cognix import draft_generation as cognix_draft_generation
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import decision_explainer as cognix_decision_explainer
from core.cognix import dynamic_ui as cognix_dynamic_ui
from core.cognix import evolution_engine as cognix_evolution_engine
from core.cognix import fine_tuning_planner as cognix_fine_tuning_planner
from core.cognix import governance_manager as cognix_governance_manager
from core.cognix import gpts as cognix_gpts
from core.cognix import hardware as cognix_hardware
from core.cognix import images as cognix_images
from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import intent_prediction as cognix_intent_prediction
from core.cognix import library as cognix_library
from core.cognix import memory_manager as cognix_memory_manager
from core.cognix import memory_editor as cognix_memory_editor
from core.cognix import model_comparison as cognix_model_comparison
from core.cognix import model_lifecycle as cognix_model_lifecycle
from core.cognix import model_translator as cognix_model_translator
from core.cognix import module_registry as cognix_module_registry
from core.cognix import onboarding as cognix_onboarding
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import persona_manager as cognix_persona_manager
from core.cognix import personal_twin as cognix_personal_twin
from core.cognix import performance_monitor as cognix_performance_monitor
from core.cognix import plugin_marketplace as cognix_plugin_marketplace
from core.cognix import project_dna as cognix_project_dna
from core.cognix import project_experts as cognix_project_experts
from core.cognix import pulse as cognix_pulse
from core.cognix import prompt_compression as cognix_prompt_compression
from core.cognix import quantization_advisor as cognix_quantization_advisor
from core.cognix import rag_planner as cognix_rag_planner
from core.cognix import registry as cognix_registry
from core.cognix import recommender as cognix_recommender
from core.cognix import research_watch as cognix_research_watch
from core.cognix import response_reflection as cognix_response_reflection
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import sandbox as cognix_sandbox
from core.cognix import scheduled as cognix_scheduled
from core.cognix import skill_memory as cognix_skill_memory
from core.cognix import simulation as cognix_simulation
from core.cognix import thinking_status as cognix_thinking_status
from core.cognix import timeline as cognix_timeline
from core.cognix import tool_discovery as cognix_tool_discovery
from core.cognix import tool_registry as cognix_tool_registry
from core.cognix import workflow_recorder as cognix_workflow_recorder
from core.cognix import worker_queue as cognix_worker_queue
from core.cognix.router import classify_objective
from core.cognix.strategy import build_strategy
from storage import cognix_db
from storage.studio_db import get_chat_project, list_chat_messages_for_threads, list_chat_projects, list_chat_threads


router = APIRouter()


class ApprovalCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    reason: str = Field(..., min_length = 3, max_length = 2000)
    request_type: str | None = Field(None, alias = "requestType", max_length = 160)
    title: str | None = Field(None, max_length = 180)
    risk_level: Literal["low", "medium", "high", "critical"] = Field("medium", alias = "riskLevel")
    resource_type: str | None = Field("", alias = "resourceType", max_length = 120)
    resource_id: str | None = Field("", alias = "resourceId", max_length = 240)
    metadata: dict[str, Any] = Field(default_factory = dict)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    status: Literal["pending", "approved", "denied"]
    admin_note: str | None = Field(None, max_length = 2000)
    policy_snapshot: dict[str, Any] | None = Field(None, alias = "policySnapshot")


class ApprovalCommentRequest(BaseModel):
    comment: str = Field(..., min_length = 1, max_length = 2000)
    visibility: Literal["admin", "requester", "internal"] = "admin"


class ApprovalPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    request_type: str = Field(..., alias = "requestType", min_length = 1, max_length = 160)
    requester_role: str = Field("user", alias = "requesterRole", max_length = 80)
    risk_level: Literal["low", "medium", "high", "critical"] | None = Field(None, alias = "riskLevel")
    has_permission: bool = Field(False, alias = "hasPermission")


class AdminPermissionGrantRequest(BaseModel):
    permission_key: str = Field(..., min_length = 1, max_length = 160)
    expires_at: str | None = Field(None, max_length = 80)


class AdminRoleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    display_name: str = Field("", alias = "displayName", max_length = 160)
    description: str = Field("", max_length = 1000)
    status: Literal["active", "disabled"] = "active"


class AdminRolePermissionRequest(BaseModel):
    allowed: bool = True
    reason: str | None = Field(None, max_length = 1000)


class AdminPermissionOverrideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    effect: Literal["allow", "deny"] = "allow"
    reason: str | None = Field("", max_length = 1000)
    expires_at: str | None = Field(None, alias = "expiresAt", max_length = 80)


class AdminProjectPermissionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    subject_type: Literal["user", "role", "group"] = Field(..., alias = "subjectType")
    subject_id: str = Field(..., alias = "subjectId", min_length = 1, max_length = 160)
    permission_key: str = Field(..., alias = "permissionKey", min_length = 1, max_length = 160)
    allowed: bool = True


class AdminPermissionDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    username: str = Field(..., min_length = 1, max_length = 160)
    permission_key: str = Field(..., alias = "permissionKey", min_length = 1, max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 240)


class AdminUserLimitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    limit_value: float = Field(..., alias = "limitValue", ge = 0)
    unit: str = Field("", max_length = 80)
    scope: str = Field("user", max_length = 80)
    period: str = Field("custom", max_length = 80)
    status: Literal["active", "disabled"] = "active"
    reason: str | None = Field(None, max_length = 500)


class AdminQuotaRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    quota_value: float = Field(..., alias = "quotaValue", ge = 0)
    unit: str = Field("", max_length = 80)
    period: str = Field("custom", max_length = 80)
    status: Literal["active", "disabled"] = "active"
    reason: str | None = Field(None, max_length = 500)


class AdminQuotaUsageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    username: str | None = Field(None, max_length = 160)
    quota_key: str = Field(..., alias = "quotaKey", min_length = 1, max_length = 160)
    used_value: float = Field(..., alias = "usedValue", ge = 0)
    unit: str = Field("", max_length = 80)
    period_key: str | None = Field(None, alias = "periodKey", max_length = 80)
    metadata: dict[str, Any] | None = None


class AdminQuotaOverrideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    target_type: Literal["user", "role", "group"] = Field(..., alias = "targetType")
    target_id: str = Field(..., alias = "targetId", min_length = 1, max_length = 160)
    quota_key: str = Field(..., alias = "quotaKey", min_length = 1, max_length = 160)
    quota_value: float = Field(..., alias = "quotaValue", ge = 0)
    unit: str = Field("", max_length = 80)
    period: str = Field("custom", max_length = 80)
    reason: str = Field("", max_length = 500)
    status: Literal["active", "disabled"] = "active"
    expires_at: str | None = Field(None, alias = "expiresAt", max_length = 80)


class AdminQuotaEnforcementRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    username: str = Field(..., min_length = 1, max_length = 160)
    quota_key: str = Field(..., alias = "quotaKey", min_length = 1, max_length = 160)
    requested_units: float = Field(1, alias = "requestedUnits", ge = 0)


class AdminChatPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    mode: Literal["e2ee_strict", "enterprise_compliance"] = "e2ee_strict"
    admin_chat_access: bool = Field(False, alias = "adminChatAccess")
    require_reason: bool = Field(True, alias = "requireReason")
    retention_days: int = Field(90, alias = "retentionDays", ge = 1, le = 3650)
    policy_scope: str = Field("organization", alias = "policyScope", max_length = 80)
    scope_id: str = Field("default", alias = "scopeId", max_length = 160)


class AdminChatExportPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    reason: str = Field(..., min_length = 3, max_length = 500)
    output_format: Literal["json", "jsonl", "markdown"] = Field("json", alias = "outputFormat")


class ReportCreateRequest(BaseModel):
    category: str = Field("general", min_length = 1, max_length = 80)
    title: str = Field(..., min_length = 3, max_length = 160)
    message: str = Field(..., min_length = 3, max_length = 4000)


class ReportStatusRequest(BaseModel):
    status: Literal["open", "in_review", "resolved", "closed"]


class BanStatusRequest(BaseModel):
    status: Literal["pending_admin_review", "active", "cleared", "permanent"]
    admin_decision: str | None = Field(None, max_length = 2000)


class BanEvidenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    source_type: str = Field("admin_note", alias = "sourceType", min_length = 1, max_length = 80)
    source_id: str | None = Field(None, alias = "sourceId", max_length = 240)
    excerpt: str = Field(..., min_length = 1, max_length = 2000)
    metadata: dict[str, Any] = Field(default_factory = dict)


class BanReportRequest(BaseModel):
    store: bool = True


class ContextMemoryRequest(BaseModel):
    content: str = Field("", max_length = 120000)


class ContextPackRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    rag_retrieval_packet: dict[str, Any] | None = Field(None, alias = "ragRetrievalPacket")


class ContextGraphBuildRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_name: str | None = Field(None, alias = "projectName", max_length = 240)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    messages: list[dict[str, Any]] | None = None
    documents: list[dict[str, Any]] | None = None
    files: list[Any] | None = None
    decisions: list[Any] | None = None
    tasks: list[Any] | None = None
    models: list[Any] | None = None
    tools: list[Any] | None = None
    include_project_threads: bool = Field(True, alias = "includeProjectThreads")
    store_snapshot: bool = Field(True, alias = "storeSnapshot")


class MemoryPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    conversation_summary: str | None = Field(None, alias = "conversationSummary", max_length = 12000)
    recent_message_count: int = Field(0, alias = "recentMessageCount", ge = 0, le = 500)


class SkillMemoryCandidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    observations: list[Any] = Field(default_factory = list)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    store_candidates: bool = Field(True, alias = "storeCandidates")


class SkillMemoryDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    label: str | None = Field(None, max_length = 240)
    value: str | None = Field(None, max_length = 2000)
    category: str | None = Field(None, max_length = 120)


class SkillMemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    label: str | None = Field(None, max_length = 240)
    value: str | None = Field(None, max_length = 2000)
    category: str | None = Field(None, max_length = 120)
    status: Literal["active", "disabled"] | None = None


class SkillMemoryInjectionPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    max_memories: int = Field(5, alias = "maxMemories", ge = 1, le = 20)


class PersonalTwinProfilePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    interactions: list[Any] = Field(default_factory = list, max_length = 200)
    activate: bool = False
    store_profile: bool = Field(True, alias = "storeProfile")


class PersonalTwinStatusRequest(BaseModel):
    status: Literal["active", "disabled", "reset"]


class PersonalTwinInjectionPlanRequest(BaseModel):
    objective: str | None = Field(None, max_length = 4000)


class LiveMemoryCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    title: str = Field(..., min_length = 1, max_length = 240)
    content: str = Field(..., min_length = 1, max_length = 120000)
    category: str = Field("general", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    sensitive: bool = False
    confirmed_sensitive_control: bool = Field(False, alias = "confirmedSensitiveControl")
    metadata: dict[str, Any] | None = None
    store_memory: bool = Field(True, alias = "storeMemory")


class LiveMemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    title: str | None = Field(None, max_length = 240)
    content: str | None = Field(None, max_length = 120000)
    category: str | None = Field(None, max_length = 80)
    reason: str | None = Field(None, max_length = 500)


class LiveMemoryStatusRequest(BaseModel):
    reason: str | None = Field(None, max_length = 500)


class LiveMemoryMergeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    source_ids: list[str] = Field(..., alias = "sourceIds", min_length = 2, max_length = 12)
    title: str | None = Field(None, max_length = 240)
    category: str | None = Field(None, max_length = 80)
    disable_sources: bool = Field(False, alias = "disableSources")
    metadata: dict[str, Any] | None = None


class WorkflowRecordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    title: str | None = Field(None, max_length = 240)
    objective: str | None = Field(None, max_length = 4000)
    workflow_type: str | None = Field(None, alias = "workflowType", max_length = 120)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    steps: list[dict[str, Any]] = Field(default_factory = list)
    metadata: dict[str, Any] | None = None
    store_workflow: bool = Field(True, alias = "storeWorkflow")


class WorkflowUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    title: str | None = Field(None, max_length = 240)
    objective: str | None = Field(None, max_length = 4000)
    status: Literal["active", "disabled", "archived"] | None = None
    share_status: Literal["private", "shared"] | None = Field(None, alias = "shareStatus")


class WorkflowRunPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    run_mode: Literal["dry_run", "simulation"] = Field("dry_run", alias = "runMode")
    inputs: dict[str, Any] | None = None


class PromptCompressionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    context: str = Field(..., min_length = 1, max_length = 240000)
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    target_tokens: int = Field(500, alias = "targetTokens", ge = 64, le = 8000)
    store_context: bool = Field(True, alias = "storeContext")


class ContextHeatmapPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    context_chunks: list[dict[str, Any]] = Field(..., alias = "contextChunks")
    response_usage: list[dict[str, Any]] | None = Field(None, alias = "responseUsage")
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_heatmap: bool = Field(True, alias = "storeHeatmap")


class MemoryCleanupPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    memories: list[dict[str, Any]] = Field(default_factory = list)
    usage_entries: list[dict[str, Any]] | None = Field(None, alias = "usageEntries")
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_suggestions: bool = Field(True, alias = "storeSuggestions")


class IntentPredictionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 120)
    draft_text: str | None = Field(None, alias = "draftText", max_length = 12000)
    recent_messages: list[Any] = Field(default_factory = list, alias = "recentMessages")
    store_prediction: bool = Field(True, alias = "storePrediction")


class DynamicUIProfileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 120)
    viewport: Literal["desktop", "mobile"] = "desktop"
    theme: Literal["dark", "light"] = "dark"
    store_profile: bool = Field(True, alias = "storeProfile")


class BackgroundJobPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    task: str = Field(..., min_length = 1, max_length = 4000)
    job_type: str | None = Field(None, alias = "jobType", max_length = 120)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    priority: Literal["low", "normal", "high"] = "normal"
    night_mode: bool = Field(False, alias = "nightMode")
    enqueue_job: bool = Field(True, alias = "enqueueJob")


class TimelineEventRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    event_type: str | None = Field(None, alias = "eventType", max_length = 120)
    title: str = Field(..., min_length = 1, max_length = 240)
    summary: str | None = Field(None, max_length = 2000)
    source_type: str | None = Field(None, alias = "sourceType", max_length = 80)
    source_id: str | None = Field(None, alias = "sourceId", max_length = 160)
    metadata: dict[str, Any] | None = None
    store_event: bool = Field(True, alias = "storeEvent")


class SimulationRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    simulation_type: str = Field("business", alias = "simulationType", max_length = 80)
    user_count: int = Field(10, alias = "userCount", ge = 1, le = 100000)
    scenario: str = Field(..., min_length = 1, max_length = 4000)
    duration_minutes: int = Field(15, alias = "durationMinutes", ge = 1, le = 10080)
    constraints: list[str] = Field(default_factory = list, max_length = 20)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 120)
    store_run: bool = Field(True, alias = "storeRun")


class SandboxPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    target_type: str = Field("feature", alias = "targetType", max_length = 80)
    objective: str = Field(..., min_length = 1, max_length = 4000)
    change_summary: str = Field(..., alias = "changeSummary", min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 120)
    requested_checks: list[str] = Field(default_factory = list, alias = "requestedChecks", max_length = 20)
    duration_minutes: int = Field(30, alias = "durationMinutes", ge = 1, le = 1440)
    store_run: bool = Field(True, alias = "storeRun")


class ResearchIntegrationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    technique_name: str | None = Field(None, alias = "techniqueName", max_length = 240)
    source_name: str | None = Field(None, alias = "sourceName", max_length = 240)
    category: str | None = Field(None, max_length = 120)
    claimed_benefit: str | None = Field(None, alias = "claimedBenefit", max_length = 1000)
    target_module: str | None = Field(None, alias = "targetModule", max_length = 160)
    risk_tolerance: str | None = Field(None, alias = "riskTolerance", max_length = 80)


class EvolutionItemPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    technique_name: str = Field(..., alias = "techniqueName", min_length = 1, max_length = 240)
    source_name: str | None = Field(None, alias = "sourceName", max_length = 240)
    category: str | None = Field(None, max_length = 120)
    claimed_benefit: str | None = Field(None, alias = "claimedBenefit", max_length = 1000)
    evidence: list[Any] = Field(default_factory = list, max_length = 20)
    risk_tolerance: str | None = Field(None, alias = "riskTolerance", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_item: bool = Field(True, alias = "storeItem")


class EvolutionExperimentPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    item_id: str | None = Field(None, alias = "itemId", max_length = 180)
    item_plan: dict[str, Any] | None = Field(None, alias = "itemPlan")
    expected_gain_percent: float | None = Field(None, alias = "expectedGainPercent", ge = -100, le = 500)
    benchmark_metric: str | None = Field(None, alias = "benchmarkMetric", max_length = 160)
    sandbox_target: str | None = Field(None, alias = "sandboxTarget", max_length = 120)
    store_experiment: bool = Field(True, alias = "storeExperiment")


class LibraryItemRequest(BaseModel):
    kind: Literal[
        "document",
        "dataset",
        "model",
        "lora_adapter",
        "image",
        "prompt",
        "persona",
        "workflow",
        "report",
        "app",
        "plugin",
        "skill",
        "directive",
        "file",
        "video",
        "other",
    ] = "other"
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


class ModelComparisonPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 12000)
    models: list[dict[str, Any]] = Field(..., min_length = 2, max_length = 8)
    outputs: list[dict[str, Any]] | None = None
    evaluator_enabled: bool = Field(True, alias = "evaluatorEnabled")
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_comparison: bool = Field(True, alias = "storeComparison")


class ModelComparisonPreferenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    output_id: str = Field(..., alias = "outputId", min_length = 1, max_length = 180)
    reason: str | None = Field(None, max_length = 1000)


class ModelConversionPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    source_model: dict[str, Any] = Field(..., alias = "sourceModel")
    target_format: str = Field(..., alias = "targetFormat", min_length = 1, max_length = 120)
    conversion_options: dict[str, Any] | None = Field(None, alias = "conversionOptions")
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_conversion: bool = Field(True, alias = "storeConversion")


class PluginInstallPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    plugin_id: str | None = Field(None, alias = "pluginId", max_length = 160)
    plugin_manifest: dict[str, Any] | None = Field(None, alias = "pluginManifest")
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    target_scope: Literal["user", "project", "workspace"] = Field("user", alias = "targetScope")
    store_plan: bool = Field(True, alias = "storePlan")


class ThinkingStatusPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    audience: Literal["chat", "project", "onboarding"] = "chat"


class ResponseReflectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 120000)
    response: str = Field("", max_length = 400000)
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    thread_id: str | None = Field(None, alias = "threadId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    task_type: str | None = Field(None, alias = "taskType", max_length = 80)
    requires_sources: bool = Field(False, alias = "requiresSources")
    response_sources: list[dict[str, Any]] | None = Field(None, alias = "responseSources")


class DraftGenerationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 120000)
    requested_variants: list[str] | None = Field(None, alias = "requestedVariants")
    max_variants: int = Field(3, alias = "maxVariants", ge = 1, le = 6)
    task_type: str | None = Field(None, alias = "taskType", max_length = 80)
    include_ranking: bool = Field(True, alias = "includeRanking")
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    thread_id: str | None = Field(None, alias = "threadId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)


class ResponseVariantRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    variant_type: str = Field(..., alias = "variantType", min_length = 1, max_length = 80)
    title: str = Field(..., min_length = 1, max_length = 160)
    content: str = Field(..., min_length = 1, max_length = 400000)
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    thread_id: str | None = Field(None, alias = "threadId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    ranking_score: float | None = Field(None, alias = "rankingScore", ge = 0.0, le = 1.0)
    metadata: dict[str, Any] | None = None


class DebatePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 120000)
    requested_roles: list[str] | None = Field(None, alias = "requestedRoles")
    max_rounds: int = Field(3, alias = "maxRounds", ge = 2, le = 5)
    task_type: str | None = Field(None, alias = "taskType", max_length = 80)
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    thread_id: str | None = Field(None, alias = "threadId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    create_session: bool = Field(True, alias = "createSession")


class DebateOutputRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    role_id: str = Field(..., alias = "roleId", min_length = 1, max_length = 80)
    output_type: Literal["argument", "critique", "reply", "synthesis", "note"] = Field("argument", alias = "outputType")
    public_summary: str = Field(..., alias = "publicSummary", min_length = 1, max_length = 20000)
    content: str = Field("", max_length = 400000)
    round_id: str | None = Field(None, alias = "roundId", max_length = 160)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    metadata: dict[str, Any] | None = None


class ToolDiscoveryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    project_name: str | None = Field(None, alias = "projectName", max_length = 240)
    file_names: list[str] | None = Field(None, alias = "fileNames")
    documents: list[dict[str, Any]] | None = None
    tags: list[str] | None = None
    installed_tool_ids: list[str] | None = Field(None, alias = "installedToolIds")
    store_recommendations: bool = Field(True, alias = "storeRecommendations")
    record_installed_snapshot: bool = Field(False, alias = "recordInstalledSnapshot")


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


class ProjectDNARequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    context: str | None = Field(None, max_length = 12000)
    response_style: str | None = Field(None, alias = "responseStyle", max_length = 4000)
    preferred_models: list[Any] | None = Field(None, alias = "preferredModels")
    allowed_tools: list[Any] | None = Field(None, alias = "allowedTools")
    constraints: list[Any] | None = None
    decisions: list[Any] | None = None
    store_dna: bool = Field(True, alias = "storeDna")


class ProjectShareCreateRequest(BaseModel):
    project_id: str = Field(..., min_length = 1, max_length = 160)
    permission: Literal["view", "edit"] = "view"


class ImageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 4000)
    model: str | None = Field(None, max_length = 160)
    mode: Literal["generate", "edit", "analyze", "variants"] = "generate"
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    source_image_id: str | None = Field(None, alias = "sourceImageId", max_length = 180)
    variant_count: int | None = Field(None, alias = "variantCount", ge = 1, le = 8)


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length = 2, max_length = 500)


class ResearchTopicPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    topic: str = Field(..., min_length = 2, max_length = 500)
    sources: list[Any] | None = None
    frequency: str | None = Field(None, max_length = 80)
    output_format: str | None = Field(None, alias = "outputFormat", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_topic: bool = Field(True, alias = "storeTopic")


class ResearchReportPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    topic_id: str | None = Field(None, alias = "topicId", max_length = 160)
    topic: str | None = Field(None, max_length = 500)
    items: list[dict[str, Any]] | None = None
    sources: list[Any] | None = None
    output_format: str | None = Field(None, alias = "outputFormat", max_length = 80)
    store_items: bool = Field(True, alias = "storeItems")
    store_report: bool = Field(True, alias = "storeReport")


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


class CommandPaletteSearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    query: str | None = Field(None, max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    limit: int = Field(20, ge = 1, le = 80)
    include_disabled: bool = Field(False, alias = "includeDisabled")


class CommandPalettePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    command_id: str = Field(..., alias = "commandId", min_length = 1, max_length = 160)
    query: str | None = Field(None, max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    parameters: dict[str, Any] | None = None
    log_usage: bool = Field(True, alias = "logUsage")


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


class DatasetBuilderPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    documents: list[dict[str, Any]]
    objective: str | None = Field(None, max_length = 4000)
    output_format: str | None = Field("jsonl", alias = "outputFormat", max_length = 80)
    max_examples: int = Field(50, alias = "maxExamples", ge = 1, le = 500)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_dataset: bool = Field(True, alias = "storeDataset")


class PersonaPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    name: str | None = Field(None, max_length = 180)
    role: str | None = Field(None, max_length = 180)
    tone: str | None = Field(None, max_length = 80)
    level: str | None = Field(None, max_length = 80)
    limits: list[str] | None = None
    allowed_tools: list[str] | None = Field(None, alias = "allowedTools")
    preferred_model: str | None = Field(None, alias = "preferredModel", max_length = 240)
    memory_ids: list[str] | None = Field(None, alias = "memoryIds")
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_persona: bool = Field(True, alias = "storePersona")


class GPTPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    name: str = Field(..., min_length = 1, max_length = 180)
    description: str | None = Field(None, max_length = 1000)
    instructions: str | None = Field(None, max_length = 12000)
    preferred_model: str | None = Field(None, alias = "preferredModel", max_length = 240)
    allowed_tools: list[Any] | None = Field(None, alias = "allowedTools")
    document_ids: list[Any] | None = Field(None, alias = "documentIds")
    memory_ids: list[Any] | None = Field(None, alias = "memoryIds")
    skills: list[Any] | None = None
    directives: list[Any] | None = None
    privacy_level: Literal["private", "project", "organization"] = Field("private", alias = "privacyLevel")
    icon: str | None = Field(None, max_length = 80)
    share_scope: Literal["private", "project", "organization", "public_readonly"] = Field("private", alias = "shareScope")
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_gpt: bool = Field(True, alias = "storeGpt")


class GPTRuntimePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    store_usage_log: bool = Field(True, alias = "storeUsageLog")


class RagPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None


class RagRetrievalPacketRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    sources: list[dict[str, Any]] | None = None
    top_k: int = Field(6, alias = "topK", ge = 1, le = 12)


class RagIndexingPlanRequest(BaseModel):
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None


class OptimizationPlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class OptimizationExperimentPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    requested_optimizations: list[str] | None = Field(None, alias = "requestedOptimizations")


class QuantizationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    priority: str = Field("balanced", max_length = 80)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    model_metadata: dict[str, Any] | None = Field(None, alias = "modelMetadata")
    store_profile: bool = Field(True, alias = "storeProfile")


class CostOptimizationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    priority: str = Field("balanced", max_length = 80)
    sensitivity_level: str | None = Field(None, alias = "sensitivityLevel", max_length = 80)
    constraints: list[str] | None = None
    expected_input_tokens: int | None = Field(None, alias = "expectedInputTokens")
    expected_output_tokens: int | None = Field(None, alias = "expectedOutputTokens")
    message_count: int | None = Field(None, alias = "messageCount")
    budget_usd: float | None = Field(None, alias = "budgetUsd")
    allow_cloud_when_sensitive: bool = Field(False, alias = "allowCloudWhenSensitive")
    provider_profiles: list[dict[str, Any]] | None = Field(None, alias = "providerProfiles")
    store_log: bool = Field(True, alias = "storeLog")


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


class PerformanceSnapshotRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    runtime_snapshot: dict[str, Any] | None = Field(None, alias = "runtimeSnapshot")
    inference_stats: dict[str, Any] | None = Field(None, alias = "inferenceStats")
    store_metric: bool = Field(True, alias = "storeMetric")


class DecisionExplainRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    source_type: Literal["orchestrator_log", "router_log", "manual"] = Field("manual", alias = "sourceType")
    source_id: str | None = Field(None, alias = "sourceId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    question: str | None = Field(None, max_length = 500)
    decision: dict[str, Any] | None = None
    store_decision: bool = Field(True, alias = "storeDecision")


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


def _effective_training_plan(current_subject: str, profile: dict[str, Any] | None = None) -> str:
    profile = profile or auth_storage.get_user_profile(current_subject) or {}
    if auth_storage.has_ceo_training_entitlement(current_subject, profile):
        return "CEO"
    return str(profile.get("plan") or "")


def _build_admin_security_bundle() -> dict[str, Any]:
    security_events = cognix_db.list_security_events(limit = 500)
    audit_logs = cognix_db.list_audit_logs(limit = 500)
    bans = cognix_db.list_bans()
    reports = cognix_db.list_reports()
    security_threats = cognix_db.list_security_threats(limit = 500)
    security_reports = cognix_db.list_security_reports(limit = 500)
    vulnerability_findings = cognix_db.list_vulnerability_findings(limit = 500)
    remediation_tasks = cognix_db.list_security_remediation_tasks(limit = 500)
    threat_report = cognix_admin_security.build_security_threat_report(
        security_events = security_events,
        audit_logs = audit_logs,
        bans = bans,
        reports = reports,
    )
    risk_scoring = cognix_admin_security.build_risk_scoring(
        security_events = security_events,
        audit_logs = audit_logs,
        bans = bans,
        reports = reports,
    )
    system_health = cognix_admin_security.build_system_health(
        hardware = cognix_hardware.get_hardware_profile(),
        security_report = threat_report,
        risk_scoring = risk_scoring,
        audit_logs = audit_logs,
    )
    security_threat_center = cognix_admin_security.build_security_threat_center(
        security_events = security_events,
        audit_logs = audit_logs,
        bans = bans,
        reports = reports,
        security_threats = security_threats,
        security_reports = security_reports,
        vulnerability_findings = vulnerability_findings,
        remediation_tasks = remediation_tasks,
    )
    return {
        "securityEvents": security_events,
        "auditLogs": audit_logs,
        "bans": bans,
        "reports": reports,
        "securityThreats": security_threats,
        "securityReports": security_reports,
        "vulnerabilityFindings": vulnerability_findings,
        "remediationTasks": remediation_tasks,
        "threatReport": threat_report,
        "securityThreatCenter": security_threat_center,
        "riskScoring": risk_scoring,
        "systemHealth": system_health,
    }


def _build_admin_banned_bundle() -> dict[str, Any]:
    bans = cognix_db.list_bans()
    reports = cognix_db.list_reports()
    security_events = cognix_db.list_security_events(limit = 1000)
    audit_logs = cognix_db.list_audit_logs(limit = 1000)
    ban_reports = cognix_db.list_ban_reports()
    evidence_logs = cognix_db.list_ban_evidence_logs()
    dashboard = cognix_admin_banned.build_banned_dashboard(
        bans = bans,
        reports = reports,
        security_events = security_events,
        audit_logs = audit_logs,
        ban_reports = ban_reports,
        evidence_logs = evidence_logs,
    )
    return {
        "bans": bans,
        "reports": reports,
        "securityEvents": security_events,
        "auditLogs": audit_logs,
        "banReports": ban_reports,
        "evidenceLogs": evidence_logs,
        "dashboard": dashboard,
    }


def _build_admin_user_bundle() -> dict[str, Any]:
    users = auth_storage.list_user_profiles()
    permissions = [
        permission
        for user in users
        for permission in cognix_db.list_user_permissions(str(user.get("username") or ""))
    ]
    threads = list_chat_threads(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    projects = list_chat_projects(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    audit_logs = cognix_db.list_audit_logs(limit = 500)
    activity_events = cognix_db.list_user_activity_events(limit = 1000)
    token_events = cognix_db.list_token_usage_events(limit = 5000)
    limits = cognix_db.list_user_limits()
    bans = cognix_db.list_bans()
    reports = cognix_db.list_reports()
    persisted_user_daily = cognix_db.list_daily_user_token_usage(limit = 1000)
    persisted_model_daily = cognix_db.list_daily_model_usage(limit = 1000)
    persisted_org_summary = cognix_db.list_organization_usage_summary(limit = 365)
    directory = cognix_admin_users.build_admin_user_directory(
        users = users,
        permissions = permissions,
        limits = limits,
        audit_logs = audit_logs,
        activity_events = activity_events,
        token_events = token_events,
        projects = projects,
        threads = threads,
        bans = bans,
        reports = reports,
    )
    usage = cognix_admin_usage.build_usage_dashboard(
        token_events = token_events,
        persisted_user_daily = persisted_user_daily,
        persisted_model_daily = persisted_model_daily,
        persisted_org_summary = persisted_org_summary,
    )
    return {
        "users": users,
        "permissions": permissions,
        "threads": threads,
        "projects": projects,
        "auditLogs": audit_logs,
        "activityEvents": activity_events,
        "tokenEvents": token_events,
        "limits": limits,
        "bans": bans,
        "reports": reports,
        "persistedUserDaily": persisted_user_daily,
        "persistedModelDaily": persisted_model_daily,
        "persistedOrgSummary": persisted_org_summary,
        "directory": directory,
        "usage": usage,
    }


def _build_admin_limits_bundle() -> dict[str, Any]:
    users = auth_storage.list_user_profiles()
    user_quotas = cognix_db.list_user_quotas()
    role_quotas = cognix_db.list_role_quotas()
    quota_overrides = cognix_db.list_quota_overrides()
    quota_usage = cognix_db.list_quota_usage(limit = 5000)
    legacy_limits = cognix_db.list_user_limits()
    matrix = cognix_admin_limits.build_quota_matrix(
        users = users,
        user_quotas = user_quotas,
        role_quotas = role_quotas,
        quota_overrides = quota_overrides,
        quota_usage = quota_usage,
        legacy_limits = legacy_limits,
    )
    return {
        "users": users,
        "userQuotas": user_quotas,
        "roleQuotas": role_quotas,
        "quotaOverrides": quota_overrides,
        "quotaUsage": quota_usage,
        "legacyLimits": legacy_limits,
        "matrix": matrix,
    }


def _build_admin_permissions_bundle() -> dict[str, Any]:
    users = auth_storage.list_user_profiles()
    legacy_permissions = [
        permission
        for user in users
        for permission in cognix_db.list_user_permissions(str(user.get("username") or ""))
    ]
    roles = cognix_db.list_roles()
    permission_definitions = cognix_db.list_permission_definitions()
    role_permissions = cognix_db.list_role_permissions()
    user_overrides = cognix_db.list_user_permission_overrides()
    project_permissions = cognix_db.list_project_permissions()
    matrix = cognix_admin_permissions.build_permission_matrix(
        users = users,
        roles = roles,
        permissions = permission_definitions,
        role_permissions = role_permissions,
        user_overrides = user_overrides,
        project_permissions = project_permissions,
        legacy_user_permissions = legacy_permissions,
        organization_policy = [],
    )
    return {
        "users": users,
        "roles": roles,
        "permissionDefinitions": permission_definitions,
        "rolePermissions": role_permissions,
        "userOverrides": user_overrides,
        "projectPermissions": project_permissions,
        "legacyPermissions": legacy_permissions,
        "matrix": matrix,
    }


def _build_admin_approvals_bundle() -> dict[str, Any]:
    requests = cognix_db.list_approval_requests()
    decisions = cognix_db.list_approval_decisions()
    comments = cognix_db.list_approval_comments()
    queue = cognix_admin_approvals.build_approval_queue(
        requests = requests,
        decisions = decisions,
        comments = comments,
    )
    return {
        "requests": requests,
        "decisions": decisions,
        "comments": comments,
        "queue": queue,
    }


def _refresh_conversation_audit_metadata(
    threads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    token_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    for record in cognix_admin_chat.build_conversation_audit_metadata_records(
        threads = threads,
        messages = messages,
        token_events = token_events,
    ):
        stored.append(
            cognix_db.upsert_conversation_audit_metadata(
                thread_id = str(record.get("threadId") or ""),
                username = str(record.get("username") or ""),
                project_id = record.get("projectId"),
                model_id = str(record.get("modelId") or "unknown"),
                risk_level = str(record.get("riskLevel") or "low"),
                message_count = int(record.get("messageCount") or 0),
                token_total = int(record.get("tokenTotal") or 0),
                tool_call_count = int(record.get("toolCallCount") or 0),
                document_access_count = int(record.get("documentAccessCount") or 0),
                metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
            )
        )
    return stored


def _build_admin_chat_bundle(
    *,
    refresh_metadata: bool = False,
) -> dict[str, Any]:
    threads = list_chat_threads(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    projects = list_chat_projects(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    messages = list_chat_messages_for_threads([str(thread.get("id")) for thread in threads if thread.get("id")])
    token_events = cognix_db.list_token_usage_events(limit = 5000)
    audit_metadata = (
        _refresh_conversation_audit_metadata(threads, messages, token_events)
        if refresh_metadata
        else cognix_db.list_conversation_audit_metadata()
    )
    return {
        "threads": threads,
        "projects": projects,
        "messages": messages,
        "tokenEvents": token_events,
        "auditMetadata": audit_metadata,
        "policy": cognix_db.get_chat_access_policy(),
    }


def _persist_activity_rollups(rollups: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    user_daily = [
        cognix_db.upsert_user_activity_daily(record)
        for record in rollups.get("userDaily", [])
    ]
    organization_daily = [
        cognix_db.upsert_organization_activity_daily(record)
        for record in rollups.get("organizationDaily", [])
    ]
    return {
        "userDaily": user_daily,
        "organizationDaily": organization_daily,
    }


def _build_admin_activity_bundle(*, refresh_rollups: bool = False) -> dict[str, Any]:
    users = auth_storage.list_user_profiles()
    threads = list_chat_threads(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    projects = list_chat_projects(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    messages = list_chat_messages_for_threads([str(thread.get("id")) for thread in threads if thread.get("id")])
    token_events = cognix_db.list_token_usage_events(limit = 5000)
    conversation_metadata = _refresh_conversation_audit_metadata(threads, messages, token_events)
    activity_events = cognix_db.list_user_activity_events(limit = 1000)
    audit_logs = cognix_db.list_audit_logs(limit = 500)
    rollups = cognix_admin_activity.build_activity_rollups(
        users = users,
        activity_events = activity_events,
        token_events = token_events,
        threads = threads,
        messages = messages,
        audit_logs = audit_logs,
        conversation_metadata = conversation_metadata,
    )
    persisted = (
        _persist_activity_rollups(rollups)
        if refresh_rollups
        else {
            "userDaily": cognix_db.list_user_activity_daily(limit = 1000),
            "organizationDaily": cognix_db.list_organization_activity_daily(limit = 365),
        }
    )
    return {
        "users": users,
        "threads": threads,
        "projects": projects,
        "messages": messages,
        "tokenEvents": token_events,
        "conversationMetadata": conversation_metadata,
        "activityEvents": activity_events,
        "auditLogs": audit_logs,
        "rollups": rollups,
        "persisted": persisted,
    }


def _row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a frontend-friendly copy while keeping raw fields available."""

    out = dict(row)
    alias_map = {
        "request_type": "requestType",
        "request_id": "requestId",
        "permission_key": "permissionKey",
        "admin_note": "adminNote",
        "policy_snapshot_json": "policySnapshotJson",
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
        "violated_rules_json": "violatedRulesJson",
        "detected_behavior": "detectedBehavior",
        "role_key": "roleKey",
        "module_key": "moduleKey",
        "effect": "effect",
        "allowed": "allowed",
        "subject_type": "subjectType",
        "subject_id": "subjectId",
        "updated_by": "updatedBy",
        "size_bytes": "sizeBytes",
        "metadata_json": "metadataJson",
        "evidence_json": "evidenceJson",
        "files_json": "filesJson",
        "recommended_solution": "recommendedSolution",
        "installed_version": "installedVersion",
        "fixed_version": "fixedVersion",
        "package_name": "packageName",
        "source_name": "sourceName",
        "schedule_text": "scheduleText",
        "display_name": "displayName",
        "app_id": "appId",
        "app_name": "appName",
        "resource_type": "resourceType",
        "resource_id": "resourceId",
        "model_id": "modelId",
        "provider_type": "providerType",
        "provider_id": "providerId",
        "prompt_hash": "promptHash",
        "prompt_excerpt": "promptExcerpt",
        "selected_output_id": "selectedOutputId",
        "comparison_json": "comparisonJson",
        "comparison_id": "comparisonId",
        "model_label": "modelLabel",
        "output_text": "outputText",
        "evaluation_json": "evaluationJson",
        "preference_type": "preferenceType",
        "output_id": "outputId",
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
        "report_json": "reportJson",
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
        "runtime_type": "runtimeType",
        "source_type": "sourceType",
        "source_id": "sourceId",
        "decision_type": "decisionType",
        "explanation_json": "explanationJson",
        "reason_code": "reasonCode",
        "evidence_json": "evidenceJson",
        "topic_id": "topicId",
        "topic_key": "topicKey",
        "output_format": "outputFormat",
        "item_type": "itemType",
        "item_json": "itemJson",
        "relevance_score": "relevanceScore",
        "suggestion_json": "suggestionJson",
        "conflict_json": "conflictJson",
        "memory_ids_json": "memoryIdsJson",
        "conflict_type": "conflictType",
        "ram_used_percent": "ramUsedPercent",
        "cpu_used_percent": "cpuUsedPercent",
        "gpu_available": "gpuAvailable",
        "tokens_per_second": "tokensPerSecond",
        "latency_ms": "latencyMs",
        "load_time_ms": "loadTimeMs",
        "estimated_cost_usd": "estimatedCostUsd",
        "metrics_json": "metricsJson",
        "needs_clarification": "needsClarification",
        "routing_mode": "routingMode",
        "simulation_type": "simulationType",
        "user_count": "userCount",
        "duration_minutes": "durationMinutes",
        "metric_key": "metricKey",
        "metric_value": "metricValue",
        "target_type": "targetType",
        "change_summary": "changeSummary",
        "sandbox_id": "sandboxId",
        "badge_label": "badgeLabel",
        "risk_level": "riskLevel",
        "variant_id": "variantId",
        "selected_variant_id": "selectedVariantId",
        "quantization": "quantization",
        "provider_id": "providerId",
        "display_name": "displayName",
        "execution_target": "executionTarget",
        "selected_provider_id": "selectedProviderId",
        "selected_execution_target": "selectedExecutionTarget",
        "estimated_cost_usd": "estimatedCostUsd",
        "estimated_latency_ms": "estimatedLatencyMs",
        "sensitivity_level": "sensitivityLevel",
        "decision_json": "decisionJson",
        "source_model_id": "sourceModelId",
        "source_format": "sourceFormat",
        "target_format": "targetFormat",
        "compatibility_status": "compatibilityStatus",
        "plan_json": "planJson",
        "conversion_id": "conversionId",
        "plugin_id": "pluginId",
        "target_scope": "targetScope",
        "install_plan_json": "installPlanJson",
        "signature_status": "signatureStatus",
        "review_type": "reviewType",
        "response_style": "responseStyle",
        "preferred_models_json": "preferredModelsJson",
        "allowed_tools_json": "allowedToolsJson",
        "allowed_tools": "allowedTools",
        "dna_json": "dnaJson",
        "dna_hash": "dnaHash",
        "constraint_type": "constraintType",
        "decision_key": "decisionKey",
        "decided_at": "decidedAt",
        "scores_json": "scoresJson",
        "message_id": "messageId",
        "thread_id": "threadId",
        "confidence_score": "confidenceScore",
        "confidence_label": "confidenceLabel",
        "verification_required": "verificationRequired",
        "recommended_action": "recommendedAction",
        "issues_json": "issuesJson",
        "evaluation_json": "evaluationJson",
        "variant_type": "variantType",
        "ranking_score": "rankingScore",
        "prompt_excerpt": "promptExcerpt",
        "max_rounds": "maxRounds",
        "roles_json": "rolesJson",
        "round_index": "roundIndex",
        "role_id": "roleId",
        "public_prompt": "publicPrompt",
        "output_type": "outputType",
        "public_summary": "publicSummary",
        "tool_id": "toolId",
        "tool_name": "toolName",
        "need_id": "needId",
        "recommendation_json": "recommendationJson",
        "command_id": "commandId",
        "command_label": "commandLabel",
        "result_status": "resultStatus",
        "limit_key": "limitKey",
        "limit_value": "limitValue",
        "quota_key": "quotaKey",
        "quota_value": "quotaValue",
        "role_key": "roleKey",
        "period_key": "periodKey",
        "used_value": "usedValue",
        "target_type": "targetType",
        "target_id": "targetId",
        "updated_by": "updatedBy",
        "event_type": "eventType",
        "organization_id": "organizationId",
        "input_tokens": "inputTokens",
        "output_tokens": "outputTokens",
        "total_tokens": "totalTokens",
        "average_latency_ms": "averageLatencyMs",
        "local_tokens": "localTokens",
        "cloud_tokens": "cloudTokens",
        "providers_json": "providersJson",
        "users_json": "usersJson",
        "period_type": "periodType",
        "target_username": "targetUsername",
        "viewed_by": "viewedBy",
        "view_reason": "viewReason",
        "policy_scope": "policyScope",
        "scope_id": "scopeId",
        "admin_chat_access": "adminChatAccess",
        "require_reason": "requireReason",
        "retention_days": "retentionDays",
        "admin_username": "adminUsername",
        "access_mode": "accessMode",
        "content_visible": "contentVisible",
        "message_count": "messageCount",
        "model_count": "modelCount",
        "token_total": "tokenTotal",
        "tool_call_count": "toolCallCount",
        "document_access_count": "documentAccessCount",
        "active_project_count": "activeProjectCount",
        "error_count": "errorCount",
        "sensitive_action_count": "sensitiveActionCount",
        "active_minutes": "activeMinutes",
        "activity_score": "activityScore",
        "models_json": "modelsJson",
        "projects_json": "projectsJson",
        "actions_json": "actionsJson",
        "active_user_count": "activeUserCount",
        "top_users_json": "topUsersJson",
        "gpt_id": "gptId",
        "runtime_plan_json": "runtimePlanJson",
        "privacy_level": "privacyLevel",
        "share_scope": "shareScope",
        "runtime_instructions": "runtimeInstructions",
        "tool_binding_json": "toolBindingJson",
        "document_binding_json": "documentBindingJson",
        "memory_binding_json": "memoryBindingJson",
        "permission_binding_json": "permissionBindingJson",
        "manager_version": "managerVersion",
        "snapshot_id": "snapshotId",
        "graph_json": "graphJson",
        "node_count": "nodeCount",
        "edge_count": "edgeCount",
        "node_key": "nodeKey",
        "node_type": "nodeType",
        "source_node_key": "sourceNodeKey",
        "target_node_key": "targetNodeKey",
        "edge_type": "edgeType",
        "candidate_key": "candidateKey",
        "candidate_type": "candidateType",
        "candidate_json": "candidateJson",
        "evidence_excerpt": "evidenceExcerpt",
        "source_candidate_id": "sourceCandidateId",
        "memory_id": "memoryId",
        "current_version": "currentVersion",
        "version_number": "versionNumber",
        "change_reason": "changeReason",
        "preference_key": "preferenceKey",
        "workflow_type": "workflowType",
        "share_status": "shareStatus",
        "step_index": "stepIndex",
        "step_type": "stepType",
        "tool_name": "toolName",
        "output_summary": "outputSummary",
        "parameters_json": "parametersJson",
        "step_json": "stepJson",
        "workflow_id": "workflowId",
        "run_mode": "runMode",
        "run_plan_json": "runPlanJson",
        "step_id": "stepId",
        "context_hash": "contextHash",
        "objective_excerpt": "objectiveExcerpt",
        "original_token_count": "originalTokenCount",
        "compressed_token_count": "compressedTokenCount",
        "reduction_ratio": "reductionRatio",
        "compressed_context": "compressedContext",
        "ranking_json": "rankingJson",
        "event_type": "eventType",
        "compressed_context_id": "compressedContextId",
        "chunk_id": "chunkId",
        "source_id": "sourceId",
        "source_type": "sourceType",
        "usage_count": "usageCount",
        "response_count": "responseCount",
        "citation_count": "citationCount",
        "utility_score": "utilityScore",
        "recommended_action": "recommendedAction",
        "theme_token": "themeToken",
        "entry_json": "entryJson",
        "output_format": "outputFormat",
        "example_count": "exampleCount",
        "ready_example_count": "readyExampleCount",
        "review_example_count": "reviewExampleCount",
        "quality_summary_json": "qualitySummaryJson",
        "data_sources_json": "dataSourcesJson",
        "export_plan_json": "exportPlanJson",
        "dataset_id": "datasetId",
        "quality_score": "qualityScore",
        "quality_label": "qualityLabel",
        "signals_json": "signalsJson",
        "preferred_model": "preferredModel",
        "config_json": "configJson",
        "system_prompt": "systemPrompt",
        "tool_permissions_json": "toolPermissionsJson",
        "memory_scope_json": "memoryScopeJson",
        "persona_id": "personaId",
        "version_number": "versionNumber",
        "template_version": "templateVersion",
        "binding_json": "bindingJson",
        "selected_domain": "selectedDomain",
        "probabilities_json": "probabilitiesJson",
        "suggestion_json": "suggestionJson",
        "preload_plan_json": "preloadPlanJson",
        "prediction_id": "predictionId",
        "target_model_id": "targetModelId",
        "technique_name": "techniqueName",
        "source_name": "sourceName",
        "item_json": "itemJson",
        "risk_level": "riskLevel",
        "item_id": "itemId",
        "sandbox_id": "sandboxId",
        "experiment_json": "experimentJson",
        "experiment_id": "experimentId",
        "gain_percent": "gainPercent",
        "result_json": "resultJson",
        "proposal_json": "proposalJson",
        "profile_key": "profileKey",
        "profile_json": "profileJson",
        "value_json": "valueJson",
        "profile_id": "profileId",
        "profile_json": "profileJson",
        "controls_json": "controlsJson",
        "style_key": "styleKey",
        "style_value": "styleValue",
        "evidence_json": "evidenceJson",
        "rule_key": "ruleKey",
        "rule_type": "ruleType",
        "rule_text": "ruleText",
        "job_type": "jobType",
        "progress_percent": "progressPercent",
        "job_plan_json": "jobPlanJson",
        "job_id": "jobId",
        "runner_type": "runnerType",
        "event_type": "eventType",
        "source_type": "sourceType",
        "source_id": "sourceId",
    }
    for source, target in alias_map.items():
        if source in out:
            out[target] = out[source]
    if "needsClarification" in out:
        out["needsClarification"] = bool(out["needsClarification"])
    if "verificationRequired" in out:
        out["verificationRequired"] = bool(out["verificationRequired"])
    if "ignored" in out:
        out["ignored"] = bool(out["ignored"])
    if "gpuAvailable" in out:
        out["gpuAvailable"] = bool(out["gpuAvailable"])
    for bool_key in ("adminChatAccess", "requireReason", "contentVisible"):
        if bool_key in out:
            out[bool_key] = bool(out[bool_key])
    if isinstance(out.get("steps"), list):
        out["steps"] = [_row(item) if isinstance(item, dict) else item for item in out["steps"]]
    if isinstance(out.get("runs"), list):
        out["runs"] = [_row(item) if isinstance(item, dict) else item for item in out["runs"]]
    if isinstance(out.get("logs"), list):
        out["logs"] = [_row(item) if isinstance(item, dict) else item for item in out["logs"]]
    if isinstance(out.get("metrics"), list):
        out["metrics"] = [_row(item) if isinstance(item, dict) else item for item in out["metrics"]]
    if isinstance(out.get("reasons"), list):
        out["reasons"] = [_row(item) if isinstance(item, dict) else item for item in out["reasons"]]
    if isinstance(out.get("permissions"), list):
        out["permissions"] = [_row(item) if isinstance(item, dict) else item for item in out["permissions"]]
    if isinstance(out.get("reviews"), list):
        out["reviews"] = [_row(item) if isinstance(item, dict) else item for item in out["reviews"]]
    if isinstance(out.get("constraints"), list):
        out["constraints"] = [_row(item) if isinstance(item, dict) else item for item in out["constraints"]]
    if isinstance(out.get("decisions"), list):
        out["decisions"] = [_row(item) if isinstance(item, dict) else item for item in out["decisions"]]
    if isinstance(out.get("plugin"), dict):
        out["plugin"] = _row(out["plugin"])
    if isinstance(out.get("sandbox"), dict):
        out["sandbox"] = _row(out["sandbox"])
    if isinstance(out.get("reportRecord"), dict):
        out["reportRecord"] = _row(out["reportRecord"])
    if isinstance(out.get("versions"), list):
        out["versions"] = [_row(item) if isinstance(item, dict) else item for item in out["versions"]]
    if isinstance(out.get("projectBindings"), list):
        out["projectBindings"] = [_row(item) if isinstance(item, dict) else item for item in out["projectBindings"]]
    if isinstance(out.get("usageLogs"), list):
        out["usageLogs"] = [_row(item) if isinstance(item, dict) else item for item in out["usageLogs"]]
    if isinstance(out.get("auditLogs"), list):
        out["auditLogs"] = [_row(item) if isinstance(item, dict) else item for item in out["auditLogs"]]
    if isinstance(out.get("styleProfiles"), list):
        out["styleProfiles"] = [_row(item) if isinstance(item, dict) else item for item in out["styleProfiles"]]
    if isinstance(out.get("personalizationRules"), list):
        out["personalizationRules"] = [_row(item) if isinstance(item, dict) else item for item in out["personalizationRules"]]
    if isinstance(out.get("outputs"), list):
        out["outputs"] = [_row(item) if isinstance(item, dict) else item for item in out["outputs"]]
    if isinstance(out.get("benchmarkResults"), list):
        out["benchmarkResults"] = [_row(item) if isinstance(item, dict) else item for item in out["benchmarkResults"]]
    if isinstance(out.get("proposals"), list):
        out["proposals"] = [_row(item) if isinstance(item, dict) else item for item in out["proposals"]]
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
    return str(cognix_scheduled.classify_scheduled_action(prompt).get("id") or "report")


def _build_scheduled_task_plan(
    current_subject: str,
    *,
    title: str,
    prompt: str,
    schedule_text: str,
    existing_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return cognix_scheduled.build_scheduled_task_plan(
        username = current_subject,
        title = title,
        prompt = prompt,
        schedule_text = schedule_text,
        granted_permissions = _granted_permission_keys(current_subject),
        admin = auth_storage.is_admin(current_subject),
        existing_task = existing_task,
    )


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
    elif action_type in {"benchmark", "index_documents", "security_audit"}:
        stub = cognix_scheduled.build_run_result_stub(action_type, prompt or str(task.get("title") or ""))
        artifact_type = str(stub.get("artifactType") or "") or None
        result = str(stub.get("result") or "Execution planifiee.")
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


def _build_pulse_plan(current_subject: str, *, hours: int = 24) -> dict[str, Any]:
    threads = list_chat_threads(
        include_archived = True,
        owner_username = current_subject,
        include_all = False,
    )
    projects = list_chat_projects(
        include_archived = True,
        owner_username = current_subject,
        include_all = False,
    )
    events = cognix_pulse.collect_pulse_events(
        username = current_subject,
        threads = threads,
        projects = projects,
        library_items = cognix_db.list_library_items(current_subject),
        scheduled_tasks = cognix_db.list_scheduled_tasks(current_subject),
        scheduled_runs = cognix_db.list_scheduled_task_runs(current_subject),
        news_items = cognix_db.list_news_items(current_subject),
        research_reports = cognix_db.list_research_reports(current_subject),
        agent_runs = cognix_db.list_agent_runs(current_subject),
        image_history = cognix_db.list_image_history(current_subject),
        audit_logs = cognix_db.list_audit_logs(username = current_subject, limit = 80),
    )
    return cognix_pulse.build_pulse_plan(
        username = current_subject,
        events = events,
        hours = hours,
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


@router.get("/performance/blueprint")
async def performance_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_performance_monitor.build_performance_monitor_blueprint()
    return {
        "username": current_subject,
        "performanceBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_performance_monitor.COGNIX_PERFORMANCE_MONITOR_VERSION,
    }


@router.post("/performance/snapshot")
async def performance_snapshot(
    payload: PerformanceSnapshotRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    runtime = payload.runtime_snapshot or _current_model_cache_runtime()
    metrics = cognix_performance_monitor.collect_runtime_metrics(
        username = current_subject,
        hardware = cognix_hardware.get_hardware_profile(),
        runtime_snapshot = runtime,
        inference_stats = payload.inference_stats,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        project_id = payload.project_id,
        model_id = payload.model_id,
    )
    stored_metric = (
        cognix_db.create_runtime_metric(
            current_subject,
            metrics = metrics,
            project_id = payload.project_id,
        )
        if payload.store_metric
        else None
    )
    side_effects = {
        **metrics.get("sideEffects", {}),
        "metricsWrite": stored_metric is not None,
        "performanceLogWrite": stored_metric is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "performance_snapshot_collected",
        resource_type = "cognix_performance_monitor",
        resource_id = str((stored_metric or {}).get("id") or metrics.get("modelId") or "runtime"),
        severity = "notice",
        metadata = {
            "performanceMonitorVersion": metrics.get("performanceMonitorVersion"),
            "runtimeMetricsCollectorVersion": metrics.get("runtimeMetricsCollectorVersion"),
            "metricsStreamerVersion": metrics.get("metricsStreamerVersion"),
            "modelId": metrics.get("modelId"),
            "runtimeType": metrics.get("runtime", {}).get("runtimeType"),
            "tokensPerSecond": metrics.get("inference", {}).get("tokensPerSecond"),
            "latencyMs": metrics.get("inference", {}).get("latencyMs"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "runtimeMetrics": metrics,
        "storedMetric": _row(stored_metric) if stored_metric else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_performance_monitor.COGNIX_PERFORMANCE_MONITOR_VERSION,
    }


@router.get("/performance/stream-plan")
async def performance_stream_plan(
    project_id: str | None = None,
    developer_mode: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    plan = cognix_performance_monitor.build_metrics_stream_plan(
        project_id = project_id,
        developer_mode = developer_mode,
    )
    return {
        "username": current_subject,
        "metricsStreamPlan": plan,
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_performance_monitor.COGNIX_METRICS_STREAMER_VERSION,
    }


@router.get("/performance/metrics")
async def performance_metrics(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    metrics = cognix_db.list_runtime_metrics(current_subject, project_id = project_id, limit = limit)
    return {"username": current_subject, "metrics": _rows(metrics), "count": len(metrics)}


@router.get("/performance/logs")
async def performance_logs(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    logs = cognix_db.list_model_performance_logs(current_subject, project_id = project_id, limit = limit)
    return {"username": current_subject, "logs": _rows(logs), "count": len(logs)}


def _router_log_decision(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "selectedDomain": log.get("selected_domain") or log.get("selectedDomain"),
        "modelLabel": log.get("model_label") or log.get("modelLabel"),
        "confidence": log.get("confidence"),
        "routingMode": log.get("routing_mode") or log.get("routingMode"),
        "needsClarification": bool(log.get("needs_clarification") or log.get("needsClarification")),
        "scores": log.get("scores") or log.get("scores_json") or log.get("scoresJson"),
        "recommendedPath": "expert_chat",
        "primaryCapability": "model_router",
        "status": "ready",
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
        },
    }


def _source_decision_for_explanation(
    *,
    payload: DecisionExplainRequest,
    current_subject: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, str, str | None, str | None]:
    if payload.decision:
        return payload.decision, None, payload.source_type, payload.source_id, None
    if not payload.source_id:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = "decision or sourceId is required",
        )

    if payload.source_type == "orchestrator_log":
        for log in cognix_db.list_orchestrator_logs(current_subject, limit = 500):
            if log.get("id") == payload.source_id:
                return (
                    log.get("decision") if isinstance(log.get("decision"), dict) else {},
                    log,
                    "orchestrator_log",
                    payload.source_id,
                    log.get("objective_excerpt") or log.get("objectiveExcerpt"),
                )
    elif payload.source_type == "router_log":
        for log in cognix_db.list_router_logs(current_subject, limit = 500):
            if log.get("id") == payload.source_id:
                return _router_log_decision(log), log, "router_log", payload.source_id, log.get("objective_excerpt")

    raise HTTPException(
        status_code = status.HTTP_404_NOT_FOUND,
        detail = "Decision source not found",
    )


@router.get("/decisions/blueprint")
async def decision_explainer_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_decision_explainer.build_decision_explainer_blueprint()
    return {
        "username": current_subject,
        "decisionExplainerBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_decision_explainer.COGNIX_EXPLANATION_GENERATOR_VERSION,
    }


@router.post("/decisions/explain")
async def explain_decision(
    payload: DecisionExplainRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    decision, source_log, source_type, source_id, objective_excerpt = _source_decision_for_explanation(
        payload = payload,
        current_subject = current_subject,
    )
    explanation = cognix_decision_explainer.build_decision_explanation(
        decision = decision,
        source_type = source_type,
        source_id = source_id,
        question = payload.question,
        objective_excerpt = objective_excerpt,
    )
    stored_decision = (
        cognix_db.create_system_decision(
            current_subject,
            explanation = explanation,
            decision = decision,
            source_type = source_type,
            source_id = source_id,
            project_id = payload.project_id or (source_log or {}).get("project_id"),
        )
        if payload.store_decision
        else None
    )
    side_effects = {
        **explanation.get("sideEffects", {}),
        "decisionWrite": stored_decision is not None,
        "reasonWrite": stored_decision is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "decision_explanation_built",
        resource_type = "cognix_system_decision",
        resource_id = str((stored_decision or {}).get("id") or source_id or "manual"),
        severity = "notice",
        metadata = {
            "sourceType": source_type,
            "sourceId": source_id,
            "decisionType": explanation.get("decisionType"),
            "reasonCodeCount": len(explanation.get("reasonCodes") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "decisionExplanation": explanation,
        "storedDecision": _row(stored_decision) if stored_decision else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_decision_explainer.COGNIX_EXPLANATION_GENERATOR_VERSION,
    }


@router.get("/decisions")
async def list_decisions(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    decisions = cognix_db.list_system_decisions(current_subject, project_id = project_id, limit = limit)
    return {"username": current_subject, "decisions": _rows(decisions), "count": len(decisions)}


@router.get("/decisions/{decision_id}")
async def get_decision(
    decision_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    decision = cognix_db.get_system_decision(current_subject, decision_id)
    if not decision:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Decision not found")
    return {"username": current_subject, "decision": _row(decision)}


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


@router.get("/models/comparison/blueprint")
async def model_comparison_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_model_comparison.build_model_comparison_blueprint()
    return {
        "username": current_subject,
        "modelComparisonBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_model_comparison.COGNIX_MODEL_COMPARISON_SERVICE_VERSION,
    }


@router.post("/models/comparison/plan")
async def model_comparison_plan(
    payload: ModelComparisonPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_model_comparison.build_model_comparison_plan(
        prompt = payload.prompt,
        models = payload.models,
        outputs = payload.outputs,
        evaluator_enabled = payload.evaluator_enabled,
        project_id = payload.project_id,
    )
    stored = (
        cognix_db.create_model_comparison(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_comparison
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "comparisonWrite": stored is not None,
        "outputWrite": bool((stored or {}).get("outputs")),
        "preferenceWrite": False,
        "parallelModelCall": False,
        "modelLoad": False,
        "generation": False,
        "networkModelCall": False,
        "toolExecution": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_comparison_plan_built",
        resource_type = "cognix_model_comparison",
        resource_id = str((stored or {}).get("id") or plan.get("promptHash") or current_subject),
        severity = "notice",
        metadata = {
            "modelComparisonServiceVersion": plan.get("modelComparisonServiceVersion"),
            "modelCount": plan.get("summary", {}).get("modelCount"),
            "collectedOutputCount": plan.get("summary", {}).get("collectedOutputCount"),
            "awaitingGenerationCount": plan.get("summary", {}).get("awaitingGenerationCount"),
            "recommendedModelId": plan.get("evaluator", {}).get("recommendedModelId"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "modelComparisonPlan": plan,
        "comparison": _row(stored) if stored else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_model_comparison.COGNIX_MODEL_COMPARISON_SERVICE_VERSION,
    }


@router.get("/models/comparisons")
async def model_comparisons(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    comparisons = cognix_db.list_model_comparisons(current_subject, project_id = project_id, limit = limit)
    return {
        "username": current_subject,
        "comparisons": _rows(comparisons),
        "count": len(comparisons),
        "sideEffects": {
            "comparisonWrite": False,
            "outputWrite": False,
            "preferenceWrite": False,
            "parallelModelCall": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
        },
    }


@router.get("/models/comparisons/{comparison_id}")
async def model_comparison_detail(
    comparison_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    comparison = cognix_db.get_model_comparison(current_subject, comparison_id)
    if comparison is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Model comparison not found")
    return {
        "username": current_subject,
        "comparison": _row(comparison),
        "sideEffects": {
            "comparisonWrite": False,
            "outputWrite": False,
            "preferenceWrite": False,
            "parallelModelCall": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
        },
    }


@router.post("/models/comparisons/{comparison_id}/preference")
async def model_comparison_preference(
    comparison_id: str,
    payload: ModelComparisonPreferenceRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    result = cognix_db.choose_model_comparison_output(
        current_subject,
        comparison_id,
        payload.output_id,
        reason = payload.reason,
    )
    if result is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Comparison output not found")
    side_effects = {
        "comparisonWrite": True,
        "outputWrite": False,
        "preferenceWrite": True,
        "parallelModelCall": False,
        "modelLoad": False,
        "generation": False,
        "networkModelCall": False,
        "toolExecution": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_comparison_preference_recorded",
        resource_type = "cognix_model_comparison",
        resource_id = comparison_id,
        severity = "notice",
        metadata = {
            "outputId": payload.output_id,
            "modelId": (result.get("output") or {}).get("model_id"),
            "preferenceId": (result.get("preference") or {}).get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "comparison": _row(result.get("comparison") or {}),
        "output": _row(result.get("output") or {}),
        "preference": _row(result.get("preference") or {}),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_model_comparison.COGNIX_MODEL_COMPARISON_SERVICE_VERSION,
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


@router.get("/models/translator/blueprint")
async def model_translator_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_model_translator.build_model_translator_blueprint()
    return {
        "username": current_subject,
        "modelTranslatorBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_model_translator.COGNIX_MODEL_CONVERSION_SERVICE_VERSION,
    }


@router.post("/models/translator/plan")
async def model_conversion_plan(
    payload: ModelConversionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_model_translator.build_model_conversion_plan(
        source_model = payload.source_model,
        target_format = payload.target_format,
        conversion_options = payload.conversion_options,
        project_id = payload.project_id,
    )
    stored_conversion = (
        cognix_db.create_model_conversion(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_conversion
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "conversionPlanWrite": stored_conversion is not None,
        "conversionLogWrite": stored_conversion is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_conversion_plan_built",
        resource_type = "cognix_model_conversion",
        resource_id = str((stored_conversion or {}).get("id") or plan.get("conversionId") or "conversion_plan"),
        severity = "warning" if not plan.get("compatibility", {}).get("compatible") else "notice",
        metadata = {
            "conversionServiceVersion": plan.get("conversionServiceVersion"),
            "compatibilityCheckerVersion": plan.get("compatibilityCheckerVersion"),
            "exportManagerVersion": plan.get("exportManagerVersion"),
            "sourceFormat": plan.get("sourceModel", {}).get("sourceFormat"),
            "targetFormat": plan.get("targetFormat"),
            "compatible": plan.get("compatibility", {}).get("compatible"),
            "compatibilityStatus": plan.get("compatibility", {}).get("status"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "modelConversionPlan": plan,
        "modelConversion": _row(stored_conversion) if stored_conversion else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_model_translator.COGNIX_MODEL_CONVERSION_SERVICE_VERSION,
    }


@router.get("/models/conversions")
async def model_conversions(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "conversions": _rows(cognix_db.list_model_conversions(current_subject, project_id = project_id)),
        "sideEffects": {
            "modelFileRead": False,
            "modelFileWrite": False,
            "conversionJobEnqueue": False,
            "registryUpdate": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
        "plannerVersion": cognix_model_translator.COGNIX_MODEL_CONVERSION_SERVICE_VERSION,
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


@router.post("/reflection/evaluate")
async def response_reflection_evaluate(
    payload: ResponseReflectionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    evaluation = cognix_response_reflection.build_response_reflection_evaluation(
        prompt = payload.prompt,
        response = payload.response,
        response_sources = payload.response_sources,
        requires_sources = payload.requires_sources,
        task_type = payload.task_type,
        model_id = payload.model_id,
    )
    record = cognix_db.create_response_evaluation(
        current_subject,
        evaluation = evaluation,
        message_id = payload.message_id,
        thread_id = payload.thread_id,
        project_id = payload.project_id,
        model_id = payload.model_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "response_reflection_evaluated",
        resource_type = "cognix_response_evaluation",
        resource_id = record.get("id"),
        severity = "warning" if evaluation.get("confidence", {}).get("verificationRequired") else "notice",
        metadata = {
            "responseReflectionVersion": evaluation.get("reflectionVersion"),
            "confidenceScore": evaluation.get("confidence", {}).get("score"),
            "confidenceLabel": evaluation.get("confidence", {}).get("label"),
            "verificationRequired": evaluation.get("confidence", {}).get("verificationRequired"),
            "recommendedAction": evaluation.get("confidence", {}).get("recommendedAction"),
            "issueIds": [str(item.get("id")) for item in evaluation.get("issues", []) if isinstance(item, dict)],
            "messageId": payload.message_id,
            "threadId": payload.thread_id,
            "projectId": payload.project_id,
            "sideEffects": evaluation.get("sideEffects", {}),
            "storageSideEffects": {"evaluationWrite": True, "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "responseReflection": evaluation,
        "record": _row(record),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            **evaluation.get("sideEffects", {}),
            "evaluationWrite": True,
            "auditWrite": True,
        },
        "plannerVersion": cognix_response_reflection.COGNIX_RESPONSE_REFLECTION_VERSION,
    }


@router.get("/reflection/evaluations")
async def response_reflection_evaluations(
    message_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    evaluations = cognix_db.list_response_evaluations(
        current_subject,
        message_id = message_id,
    )
    return {
        "username": current_subject,
        "evaluations": _rows(evaluations),
    }


@router.get("/drafts/styles")
async def draft_style_profiles(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_draft_generation.build_style_profile_registry()
    return {
        "username": current_subject,
        "styleProfileRegistry": registry,
        "sideEffects": registry.get("sideEffects", {}),
    }


@router.post("/drafts/plan")
async def draft_generation_plan(
    payload: DraftGenerationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_draft_generation.build_draft_generation_plan(
        prompt = payload.prompt,
        requested_variants = payload.requested_variants,
        max_variants = payload.max_variants,
        task_type = payload.task_type,
        include_ranking = payload.include_ranking,
        message_id = payload.message_id,
        project_id = payload.project_id,
        model_id = payload.model_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "draft_generation_plan_built",
        resource_type = "cognix_draft_generation_plan",
        resource_id = str(payload.message_id or payload.thread_id or payload.project_id or "general"),
        severity = "notice",
        metadata = {
            "draftGenerationVersion": plan.get("draftGenerationVersion"),
            "selectedVariantTypes": plan.get("selectedVariantTypes", []),
            "estimatedGenerationCount": plan.get("costPlan", {}).get("estimatedGenerationCount"),
            "messageId": payload.message_id,
            "threadId": payload.thread_id,
            "projectId": payload.project_id,
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "draftGenerationPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_draft_generation.COGNIX_DRAFT_GENERATION_VERSION,
    }


@router.get("/drafts/variants")
async def response_variants(
    message_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    variants = cognix_db.list_response_variants(current_subject, message_id = message_id)
    return {
        "username": current_subject,
        "variants": _rows(variants),
    }


@router.post("/drafts/variants")
async def create_response_variant(
    payload: ResponseVariantRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    variant = cognix_db.create_response_variant(
        current_subject,
        variant_type = payload.variant_type,
        title = payload.title,
        content = payload.content,
        message_id = payload.message_id,
        thread_id = payload.thread_id,
        project_id = payload.project_id,
        model_id = payload.model_id,
        ranking_score = payload.ranking_score,
        metadata = payload.metadata,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "response_variant_stored",
        resource_type = "cognix_response_variant",
        resource_id = variant.get("id"),
        severity = "notice",
        metadata = {
            "variantType": variant.get("variant_type"),
            "messageId": payload.message_id,
            "threadId": payload.thread_id,
            "projectId": payload.project_id,
            "modelId": payload.model_id,
            "storageSideEffects": {"variantWrite": True, "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "variant": _row(variant),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "variantWrite": True,
            "auditWrite": True,
        },
    }


def _debate_session_response(session: dict[str, Any]) -> dict[str, Any]:
    out = _row(session)
    out["rounds"] = _rows(session.get("rounds", []))
    out["outputs"] = _rows(session.get("outputs", []))
    return out


@router.get("/debate/roles")
async def debate_roles(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_debate_orchestrator.build_debate_role_registry()
    return {
        "username": current_subject,
        "debateRoleRegistry": registry,
        "sideEffects": registry.get("sideEffects", {}),
    }


@router.post("/debate/plan")
async def debate_plan(
    payload: DebatePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_debate_orchestrator.build_debate_plan(
        prompt = payload.prompt,
        requested_roles = payload.requested_roles,
        max_rounds = payload.max_rounds,
        task_type = payload.task_type,
        message_id = payload.message_id,
        project_id = payload.project_id,
        model_id = payload.model_id,
    )
    session: dict[str, Any] | None = None
    if payload.create_session:
        session = cognix_db.create_debate_session(
            current_subject,
            plan = plan,
            prompt = payload.prompt,
            message_id = payload.message_id,
            thread_id = payload.thread_id,
            project_id = payload.project_id,
        )
    side_effects = {
        **plan.get("sideEffects", {}),
        "debateSessionWrite": bool(session),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "debate_plan_built",
        resource_type = "cognix_debate_session" if session else "cognix_debate_plan",
        resource_id = str((session or {}).get("id") or payload.message_id or "general"),
        severity = "notice",
        metadata = {
            "debateOrchestratorVersion": plan.get("debateOrchestratorVersion"),
            "plannedRoundCount": plan.get("summary", {}).get("plannedRoundCount"),
            "roleIds": [str(item.get("id")) for item in plan.get("roles", []) if isinstance(item, dict)],
            "messageId": payload.message_id,
            "threadId": payload.thread_id,
            "projectId": payload.project_id,
            "sessionCreated": bool(session),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "debatePlan": plan,
        "session": _debate_session_response(session) if session else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_debate_orchestrator.COGNIX_DEBATE_ORCHESTRATOR_VERSION,
    }


@router.get("/debate/sessions")
async def debate_sessions(
    message_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    sessions = cognix_db.list_debate_sessions(current_subject, message_id = message_id)
    return {
        "username": current_subject,
        "sessions": [_debate_session_response(session) for session in sessions],
    }


@router.post("/debate/sessions/{session_id}/outputs")
async def create_debate_output(
    session_id: str,
    payload: DebateOutputRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        output = cognix_db.create_debate_output(
            current_subject,
            session_id = session_id,
            role_id = payload.role_id,
            output_type = payload.output_type,
            public_summary = payload.public_summary,
            content = payload.content,
            round_id = payload.round_id,
            model_id = payload.model_id,
            metadata = payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 404, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "debate_output_stored",
        resource_type = "cognix_debate_output",
        resource_id = output.get("id"),
        severity = "notice",
        metadata = {
            "sessionId": session_id,
            "roleId": payload.role_id,
            "outputType": payload.output_type,
            "roundId": payload.round_id,
            "storageSideEffects": {"debateOutputWrite": True, "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "output": _row(output),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "debateOutputWrite": True,
            "auditWrite": True,
        },
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
    user_plan = _effective_training_plan(current_subject, user_profile)
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


@router.get("/command-palette/blueprint")
async def command_palette_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_command_palette.build_command_palette_blueprint()
    return {
        "username": current_subject,
        "commandPaletteBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_command_palette.COGNIX_COMMAND_PALETTE_VERSION,
    }


@router.post("/command-palette/search")
async def command_palette_search(
    payload: CommandPaletteSearchRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    result = cognix_command_palette.list_commands(
        query = payload.query,
        granted_permissions = _granted_permission_keys(current_subject),
        is_admin = auth_storage.is_admin(current_subject),
        project_id = payload.project_id,
        limit = payload.limit,
        include_disabled = payload.include_disabled,
    )
    return {
        "username": current_subject,
        "commandPalette": result,
        "sideEffects": result.get("sideEffects", {}),
        "plannerVersion": cognix_command_palette.COGNIX_COMMAND_PALETTE_VERSION,
    }


@router.post("/command-palette/plan")
async def command_palette_plan(
    payload: CommandPalettePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_command_palette.build_command_plan(
        command_id = payload.command_id,
        query = payload.query,
        project_id = payload.project_id,
        parameters = payload.parameters,
        granted_permissions = _granted_permission_keys(current_subject),
        is_admin = auth_storage.is_admin(current_subject),
    )
    usage_log = (
        cognix_db.create_command_usage_log(current_subject, command_plan = plan)
        if payload.log_usage
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "commandUsageLogWrite": usage_log is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "command_palette_plan_built",
        resource_type = "cognix_command_palette",
        resource_id = str(plan.get("commandId") or payload.command_id),
        severity = "warning" if plan.get("status") != "ready" else "notice",
        metadata = {
            "commandPaletteVersion": plan.get("commandPaletteVersion"),
            "commandRegistryVersion": plan.get("commandRegistryVersion"),
            "commandId": plan.get("commandId"),
            "status": plan.get("status"),
            "allowedToRun": plan.get("allowedToRun"),
            "missingPermissions": plan.get("command", {}).get("missingPermissions", []),
            "route": plan.get("executionPlan", {}).get("route"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "commandPlan": plan,
        "usageLog": _row(usage_log) if usage_log else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_command_palette.COGNIX_COMMAND_PALETTE_VERSION,
    }


@router.get("/command-palette/usage")
async def command_palette_usage(
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "username": current_subject,
        "usageLogs": _rows(cognix_db.list_command_usage_logs(current_subject, limit = limit)),
        "sideEffects": cognix_command_palette.build_command_palette_blueprint()["sideEffects"],
        "plannerVersion": cognix_command_palette.COGNIX_COMMAND_PALETTE_VERSION,
    }


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


@router.get("/tools/discovery/capabilities")
async def tool_discovery_capabilities(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_tool_discovery.build_tool_capability_registry()
    return {
        "username": current_subject,
        "capabilityRegistry": registry,
        "sideEffects": registry.get("sideEffects", {}),
    }


@router.post("/tools/discovery/analyze")
async def analyze_tool_discovery(
    payload: ToolDiscoveryRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project: dict[str, Any] | None = None
    if payload.project_id:
        project = _require_owned_project(payload.project_id, current_subject)
    capability_lookup = {
        str(item.get("toolId")): item
        for item in cognix_tool_discovery.build_tool_capability_registry().get("capabilities", [])
        if item.get("toolId")
    }
    installed_writes: list[dict[str, Any]] = []
    if payload.record_installed_snapshot:
        for tool_id in payload.installed_tool_ids or []:
            normalized_tool_id = str(tool_id or "").strip().lower()
            if not normalized_tool_id:
                continue
            capability = capability_lookup.get(normalized_tool_id, {})
            installed_writes.append(
                cognix_db.upsert_installed_tool(
                    current_subject,
                    tool_id = normalized_tool_id,
                    tool_name = str(capability.get("name") or normalized_tool_id),
                    status = "installed",
                    source = "client_snapshot",
                    metadata = {
                        "toolDiscoveryVersion": cognix_tool_discovery.COGNIX_TOOL_DISCOVERY_VERSION,
                        "recordedFromAnalyzeRequest": True,
                    },
                )
            )
    installed_records = cognix_db.list_installed_tools(current_subject)
    project_name = payload.project_name
    project_type = payload.project_type
    if project:
        project_name = project_name or str(project.get("title") or project.get("name") or "")
        project_type = project_type or str(project.get("project_type") or project.get("projectType") or "")
    plan = cognix_tool_discovery.build_tool_discovery_plan(
        username = current_subject,
        objective = payload.objective,
        project_type = project_type,
        project_name = project_name,
        project_id = payload.project_id,
        file_names = payload.file_names,
        documents = payload.documents,
        tags = payload.tags,
        installed_tool_ids = payload.installed_tool_ids,
        installed_records = installed_records,
    )
    stored_recommendations = (
        cognix_db.create_tool_recommendations(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_recommendations
        else []
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "recommendationWrite": bool(stored_recommendations),
        "installedToolWrite": bool(installed_writes),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_discovery_analyzed",
        resource_type = "cognix_tool_discovery_plan",
        resource_id = payload.project_id or "general",
        severity = "notice",
        metadata = {
            "toolDiscoveryVersion": plan.get("toolDiscoveryVersion"),
            "projectId": payload.project_id,
            "needCount": plan.get("summary", {}).get("needCount"),
            "recommendationCount": plan.get("summary", {}).get("recommendationCount"),
            "storedRecommendationCount": len(stored_recommendations),
            "installedSnapshotCount": len(installed_writes),
            "automaticInstallAllowed": plan.get("summary", {}).get("automaticInstallAllowed"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "toolDiscoveryPlan": plan,
        "storedRecommendations": _rows(stored_recommendations),
        "installedTools": _rows(installed_records),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.get("/tools/recommendations")
async def tool_recommendations(
    project_id: str | None = None,
    include_ignored: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    recommendations = cognix_db.list_tool_recommendations(
        current_subject,
        project_id = project_id,
        include_ignored = include_ignored,
    )
    return {
        "username": current_subject,
        "recommendations": _rows(recommendations),
        "sideEffects": {
            "toolExecution": False,
            "installation": False,
            "recommendationWrite": False,
            "secretRead": False,
        },
    }


@router.post("/tools/recommendations/{recommendation_id}/ignore")
async def ignore_tool_recommendation(
    recommendation_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    recommendation = cognix_db.ignore_tool_recommendation(current_subject, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code = 404, detail = "Recommendation not found")
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_recommendation_ignored",
        resource_type = "cognix_tool_recommendation",
        resource_id = recommendation_id,
        severity = "notice",
        metadata = {
            "toolId": recommendation.get("tool_id"),
            "needId": recommendation.get("need_id"),
            "sideEffects": {
                "recommendationWrite": True,
                "installation": False,
                "toolExecution": False,
            },
        },
    )
    return {
        "username": current_subject,
        "recommendation": _row(recommendation),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "recommendationWrite": True,
            "installation": False,
            "toolExecution": False,
            "secretRead": False,
        },
    }


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


@router.get("/plugins/marketplace/blueprint")
async def plugin_marketplace_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_plugin_marketplace.build_plugin_marketplace_blueprint()
    return {
        "username": current_subject,
        "pluginMarketplaceBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_plugin_marketplace.COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION,
    }


@router.get("/plugins/marketplace")
async def plugin_marketplace_catalog(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    catalog = cognix_plugin_marketplace.build_marketplace_catalog()
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "plugin_marketplace_catalog_built",
        resource_type = "cognix_plugin_marketplace",
        resource_id = str(catalog.get("marketplaceServiceVersion")),
        severity = "notice",
        metadata = {
            "marketplaceServiceVersion": catalog.get("marketplaceServiceVersion"),
            "pluginCount": catalog.get("summary", {}).get("pluginCount"),
            "installableCount": catalog.get("summary", {}).get("installableCount"),
            "sideEffects": catalog.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "marketplaceCatalog": catalog,
        "auditLogId": audit.get("id"),
        "sideEffects": catalog.get("sideEffects", {}),
        "plannerVersion": cognix_plugin_marketplace.COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION,
    }


@router.post("/plugins/install-plan")
async def plugin_install_plan(
    payload: PluginInstallPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_plugin_marketplace.build_plugin_install_plan(
        username = current_subject,
        plugin_id = payload.plugin_id,
        plugin_manifest = payload.plugin_manifest,
        project_id = payload.project_id,
        target_scope = payload.target_scope,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    stored_installation = (
        cognix_db.create_plugin_install_plan(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_plan
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "pluginPlanWrite": stored_installation is not None,
        "permissionScanWrite": stored_installation is not None,
        "reviewWrite": stored_installation is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "plugin_install_plan_built",
        resource_type = "cognix_plugin_installation",
        resource_id = str((stored_installation or {}).get("id") or plan.get("installationPlanId") or "plugin_plan"),
        severity = "warning" if plan.get("status") != "ready_for_confirmation" else "notice",
        metadata = {
            "marketplaceServiceVersion": plan.get("marketplaceServiceVersion"),
            "installerVersion": plan.get("installerVersion"),
            "permissionScannerVersion": plan.get("permissionScannerVersion"),
            "pluginId": plan.get("plugin", {}).get("id"),
            "status": plan.get("status"),
            "signatureStatus": plan.get("validation", {}).get("signatureStatus"),
            "missingPermissions": plan.get("permissionScan", {}).get("missingPermissions", []),
            "maxRiskLevel": plan.get("permissionScan", {}).get("maxRiskLevel"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "pluginInstallPlan": plan,
        "installedPlugin": _row(stored_installation) if stored_installation else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_plugin_marketplace.COGNIX_PLUGIN_MARKETPLACE_SERVICE_VERSION,
    }


@router.get("/plugins/installations")
async def plugin_installations(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    installations = cognix_db.list_installed_plugins(
        current_subject,
        project_id = project_id,
        limit = limit,
    )
    return {
        "username": current_subject,
        "installations": [_row(item) for item in installations],
        "count": len(installations),
    }


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
        plan = cognix_tool_registry.apply_rate_limit_result(plan, rate_limit)
        tool_rate_limited_status = "rate_limited"
        if isinstance(rate_limit, dict) and plan.get("status") == tool_rate_limited_status:
            rate_limit["status"] = tool_rate_limited_status

    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_action_planned",
        resource_type = "cognix_tool_action",
        resource_id = f"{payload.tool_id}:{payload.action_id}",
        severity = "notice" if plan.get("allowed") else "warning",
        metadata = {
            "toolRegistryVersion": plan.get("registryVersion"),
            "executionContractVersion": plan.get("executionContractVersion"),
            "toolId": plan.get("toolId"),
            "actionId": plan.get("actionId"),
            "status": plan.get("status"),
            "riskLevel": plan.get("riskLevel"),
            "requiresConfirmation": plan.get("requiresConfirmation"),
            "guardrails": plan.get("guardrails", {}),
            "contract": {
                "allowedToPrepare": plan.get("executionContract", {}).get("allowedToPrepare"),
                "readyForExecution": plan.get("executionContract", {}).get("readyForExecution"),
                "nextRequiredGate": plan.get("executionContract", {}).get("nextRequiredGate"),
                "blockedWhen": plan.get("executionContract", {}).get("blockedWhen", []),
            },
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
            "decisionScore": preload_plan.get("target", {}).get("decisionScore"),
            "executionContractVersion": preload_plan.get("executionContract", {}).get("contractVersion"),
            "recommendedWindowSeconds": preload_plan.get("schedule", {}).get("recommendedWindowSeconds"),
            "requiredEvictionCount": preload_plan.get("cachePreflight", {}).get("requiredEvictionCount"),
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
    user_plan = _effective_training_plan(current_subject, user_profile)
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        fine_tuning_dataset = payload.dataset,
        user_plan = user_plan,
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
    user_plan = _effective_training_plan(current_subject, user_profile)
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        fine_tuning_dataset = payload.dataset,
        user_plan = user_plan,
    )
    tuning_plan = plan["fineTuningPlan"]
    handoff = cognix_fine_tuning_planner.build_cloud_training_handoff_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        target_id = payload.target_id,
        fine_tuning_plan = tuning_plan,
        dataset = payload.dataset,
        user_plan = user_plan,
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


@router.get("/datasets/blueprint")
async def dataset_builder_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_dataset_builder.build_dataset_builder_blueprint()
    return {
        "username": current_subject,
        "datasetBuilderBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_dataset_builder.COGNIX_DATASET_BUILDER_VERSION,
    }


@router.post("/datasets/plan")
async def dataset_builder_plan(
    payload: DatasetBuilderPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_dataset_builder.build_dataset_plan(
        username = current_subject,
        documents = payload.documents,
        objective = payload.objective,
        output_format = payload.output_format,
        max_examples = payload.max_examples,
        project_id = payload.project_id,
    )
    stored_dataset = (
        cognix_db.create_generated_dataset(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_dataset
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "datasetWrite": stored_dataset is not None,
        "exampleWrite": stored_dataset is not None,
        "qualityScoreWrite": stored_dataset is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "dataset_builder_plan_built",
        resource_type = "cognix_generated_dataset",
        resource_id = str((stored_dataset or {}).get("id") or plan.get("dataset", {}).get("datasetId") or current_subject),
        severity = "warning" if plan.get("dataset", {}).get("status") == "review_required" else "notice",
        metadata = {
            "datasetBuilderVersion": plan.get("datasetBuilderVersion"),
            "syntheticExampleGeneratorVersion": plan.get("syntheticExampleGeneratorVersion"),
            "qualityFilterVersion": plan.get("qualityFilterVersion"),
            "exportServiceVersion": plan.get("exportServiceVersion"),
            "datasetId": plan.get("dataset", {}).get("datasetId"),
            "exampleCount": plan.get("dataset", {}).get("exampleCount"),
            "reviewExampleCount": plan.get("dataset", {}).get("reviewExampleCount"),
            "sensitiveSourceCount": plan.get("qualitySummary", {}).get("sensitiveSourceCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "datasetBuilderPlan": plan,
        "generatedDataset": _row(stored_dataset) if stored_dataset else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_dataset_builder.COGNIX_DATASET_BUILDER_VERSION,
    }


@router.get("/datasets")
async def generated_datasets(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "datasets": _rows(cognix_db.list_generated_datasets(current_subject, project_id = project_id)),
        "sideEffects": {
            "datasetWrite": False,
            "exampleWrite": False,
            "qualityScoreWrite": False,
            "fileWrite": False,
            "datasetExport": False,
            "datasetUpload": False,
            "trainingJob": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
        "plannerVersion": cognix_dataset_builder.COGNIX_DATASET_BUILDER_VERSION,
    }


@router.get("/personas/blueprint")
async def persona_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_persona_manager.build_persona_blueprint()
    return {
        "username": current_subject,
        "personaBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_persona_manager.COGNIX_PERSONA_MANAGER_VERSION,
    }


@router.post("/personas/plan")
async def persona_plan(
    payload: PersonaPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_persona_manager.build_persona_plan(
        username = current_subject,
        name = payload.name,
        role = payload.role,
        tone = payload.tone,
        level = payload.level,
        limits = payload.limits,
        allowed_tools = payload.allowed_tools,
        preferred_model = payload.preferred_model,
        memory_ids = payload.memory_ids,
        project_id = payload.project_id,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    stored_persona = (
        cognix_db.create_persona(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_persona
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "personaWrite": stored_persona is not None,
        "personaVersionWrite": stored_persona is not None,
        "projectBindingWrite": bool(stored_persona and payload.project_id),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "persona_plan_built",
        resource_type = "cognix_persona",
        resource_id = str((stored_persona or {}).get("id") or plan.get("personaId") or current_subject),
        severity = "warning" if plan.get("security", {}).get("blockedToolCount") else "notice",
        metadata = {
            "personaManagerVersion": plan.get("personaManagerVersion"),
            "templateEngineVersion": plan.get("templateEngineVersion"),
            "permissionBinderVersion": plan.get("permissionBinderVersion"),
            "personaId": plan.get("personaId"),
            "blockedToolCount": plan.get("security", {}).get("blockedToolCount"),
            "allowedToolIds": plan.get("toolPermissions", {}).get("allowedToolIds", []),
            "blockedToolIds": plan.get("toolPermissions", {}).get("blockedToolIds", []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "personaPlan": plan,
        "persona": _row(stored_persona) if stored_persona else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_persona_manager.COGNIX_PERSONA_MANAGER_VERSION,
    }


@router.get("/personas")
async def personas(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "personas": _rows(cognix_db.list_personas(current_subject, project_id = project_id)),
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
        "plannerVersion": cognix_persona_manager.COGNIX_PERSONA_MANAGER_VERSION,
    }


@router.get("/personas/{persona_id}")
async def persona_detail(
    persona_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    persona = cognix_db.get_persona(current_subject, persona_id)
    if persona is None:
        raise HTTPException(status_code = 404, detail = "Persona not found")
    return {
        "persona": _row(persona),
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
        "plannerVersion": cognix_persona_manager.COGNIX_PERSONA_MANAGER_VERSION,
    }


@router.get("/gpts/blueprint")
async def gpts_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_gpts.build_gpts_blueprint()
    return {
        "username": current_subject,
        "gptsBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_gpts.COGNIX_GPT_MANAGER_VERSION,
    }


@router.post("/gpts/plan")
async def gpt_plan(
    payload: GPTPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_gpts.build_gpt_plan(
        username = current_subject,
        name = payload.name,
        description = payload.description,
        instructions = payload.instructions,
        preferred_model = payload.preferred_model,
        allowed_tools = payload.allowed_tools,
        document_ids = payload.document_ids,
        memory_ids = payload.memory_ids,
        skills = payload.skills,
        directives = payload.directives,
        privacy_level = payload.privacy_level,
        icon = payload.icon,
        share_scope = payload.share_scope,
        project_id = payload.project_id,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    stored_gpt = (
        cognix_db.create_gpt(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_gpt
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "gptWrite": stored_gpt is not None,
        "gptVersionWrite": stored_gpt is not None,
        "projectBindingWrite": bool(stored_gpt and payload.project_id),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "gpt_plan_built",
        resource_type = "cognix_gpt",
        resource_id = str((stored_gpt or {}).get("id") or plan.get("gptId") or current_subject),
        severity = "warning" if plan.get("security", {}).get("blockedToolCount") else "notice",
        metadata = {
            "gptManagerVersion": plan.get("gptManagerVersion"),
            "customAssistantRuntimeVersion": plan.get("customAssistantRuntimeVersion"),
            "permissionBinderVersion": plan.get("permissionBinderVersion"),
            "gptId": plan.get("gptId"),
            "blockedToolCount": plan.get("security", {}).get("blockedToolCount"),
            "allowedToolIds": plan.get("toolBinding", {}).get("allowedToolIds", []),
            "blockedToolIds": plan.get("toolBinding", {}).get("blockedToolIds", []),
            "privacyLevel": plan.get("security", {}).get("privacyLevel"),
            "shareScope": plan.get("security", {}).get("shareScope"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "gptPlan": plan,
        "gpt": _row(stored_gpt) if stored_gpt else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_gpts.COGNIX_GPT_MANAGER_VERSION,
    }


@router.get("/gpts")
async def gpts(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "gpts": _rows(cognix_db.list_gpts(current_subject, project_id = project_id)),
        "sideEffects": cognix_gpts.build_gpts_blueprint()["sideEffects"],
        "plannerVersion": cognix_gpts.COGNIX_GPT_MANAGER_VERSION,
    }


@router.get("/gpts/{gpt_id}")
async def gpt_detail(
    gpt_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    gpt = cognix_db.get_gpt(current_subject, gpt_id)
    if gpt is None:
        raise HTTPException(status_code = 404, detail = "GPT not found")
    return {
        "gpt": _row(gpt),
        "sideEffects": cognix_gpts.build_gpts_blueprint()["sideEffects"],
        "plannerVersion": cognix_gpts.COGNIX_GPT_MANAGER_VERSION,
    }


@router.post("/gpts/{gpt_id}/runtime-plan")
async def gpt_runtime_plan(
    gpt_id: str,
    payload: GPTRuntimePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    gpt = cognix_db.get_gpt(current_subject, gpt_id)
    if gpt is None:
        raise HTTPException(status_code = 404, detail = "GPT not found")
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_gpts.build_gpt_runtime_plan(
        username = current_subject,
        gpt = gpt,
        objective = payload.objective,
        project_id = payload.project_id,
    )
    usage_log = (
        cognix_db.create_gpt_usage_log(
            current_subject,
            gpt_id = gpt_id,
            runtime_plan = plan,
        )
        if payload.store_usage_log
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "usageLogWrite": usage_log is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "gpt_runtime_plan_built",
        resource_type = "cognix_gpt",
        resource_id = gpt_id,
        severity = "notice",
        metadata = {
            "gptManagerVersion": plan.get("gptManagerVersion"),
            "customAssistantRuntimeVersion": plan.get("customAssistantRuntimeVersion"),
            "allowedToolIds": plan.get("orchestratorRequest", {}).get("allowedToolIds", []),
            "blockedToolIds": plan.get("orchestratorRequest", {}).get("blockedToolIds", []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "gpt": _row(gpt),
        "gptRuntimePlan": plan,
        "usageLog": _row(usage_log) if usage_log else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_gpts.COGNIX_CUSTOM_ASSISTANT_RUNTIME_VERSION,
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


@router.post("/rag/retrieval-packet")
async def rag_retrieval_packet(
    payload: RagRetrievalPacketRequest,
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
    packet = cognix_rag_planner.build_rag_retrieval_packet(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        sources = payload.sources or [],
        rag_plan = plan["ragPlan"],
        top_k = payload.top_k,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "rag_retrieval_packet_built",
        resource_type = "cognix_rag_retrieval_packet",
        resource_id = str(payload.project_id or plan["ragPlan"].get("targetDomain") or "general"),
        severity = "notice" if packet.get("readyForInjection") else "warning",
        metadata = {
            "retrievalPacketVersion": packet.get("retrievalPacketVersion"),
            "plannerVersion": packet.get("plannerVersion"),
            "readyForInjection": packet.get("readyForInjection"),
            "sourceCount": packet.get("summary", {}).get("sourceCount"),
            "candidateChunkCount": packet.get("summary", {}).get("candidateChunkCount"),
            "selectedChunkCount": packet.get("summary", {}).get("selectedChunkCount"),
            "citationCount": packet.get("summary", {}).get("citationCount"),
            "sideEffects": packet.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "ragPlan": plan["ragPlan"],
        "retrievalPacket": packet,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": packet.get("sideEffects", {}),
    }


@router.get("/optimizations/capabilities")
async def optimization_capabilities(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    registry = cognix_optimization_planner.build_optimization_capability_registry(
        hardware = hardware,
        recommendation = recommendation_payload["recommendation"],
        latest_benchmark_run = latest_benchmark,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "optimization_capability_registry_built",
        resource_type = "cognix_optimization_capability_registry",
        resource_id = str(registry.get("registryVersion")),
        severity = "notice",
        metadata = {
            "registryVersion": registry.get("registryVersion"),
            "plannerVersion": registry.get("plannerVersion"),
            "hardwareTier": registry.get("hardwareTier"),
            "runtimeType": registry.get("runtimeType"),
            "compatibleCount": registry.get("summary", {}).get("compatibleCount"),
            "benchmarkReady": registry.get("benchmarkReady"),
            "sideEffects": registry.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "registry": registry,
        "auditLogId": audit.get("id"),
        "sideEffects": registry.get("sideEffects", {}),
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


@router.post("/optimizations/experiment-plan")
async def optimization_experiment_plan(
    payload: OptimizationExperimentPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    plan = cognix_optimization_planner.build_optimization_experiment_plan(
        objective = payload.objective,
        hardware = hardware,
        recommendation = recommendation_payload["recommendation"],
        latest_benchmark_run = latest_benchmark,
        requested_optimizations = payload.requested_optimizations,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "optimization_experiment_plan_built",
        resource_type = "cognix_optimization_experiment_plan",
        resource_id = str(payload.project_id or plan.get("experimentPlanVersion") or "general"),
        severity = "warning" if plan.get("summary", {}).get("blockedTicketCount") else "notice",
        metadata = {
            "experimentPlanVersion": plan.get("experimentPlanVersion"),
            "registryVersion": plan.get("registryVersion"),
            "hardwareTier": plan.get("hardwareTier"),
            "runtimeType": plan.get("runtimeType"),
            "ticketCount": plan.get("summary", {}).get("ticketCount"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds"),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "optimizationExperimentPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_optimization_planner.COGNIX_OPTIMIZATION_PLANNER_VERSION,
    }


@router.get("/quantization/variants")
async def quantization_variants(
    priority: str = "balanced",
    model_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    recommendation = dict(recommendation_payload.get("recommendation") or {})
    if model_id:
        recommendation["modelId"] = model_id
    registry = cognix_quantization_advisor.build_model_variant_registry(
        model_metadata = recommendation,
        hardware = hardware,
        priority = priority,
    )
    stored_variants = cognix_db.upsert_model_variants(registry.get("variants", []))
    side_effects = {
        **registry.get("sideEffects", {}),
        "modelVariantWrite": bool(stored_variants),
        "profileWrite": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_variant_registry_built",
        resource_type = "cognix_model_variant_registry",
        resource_id = str(registry.get("model", {}).get("modelId") or "selected_model"),
        severity = "notice",
        metadata = {
            "advisorVersion": registry.get("advisorVersion"),
            "registryVersion": registry.get("registryVersion"),
            "priority": registry.get("priority"),
            "selectedQuantization": registry.get("recommendedVariant", {}).get("quantization"),
            "badgeLabel": registry.get("badge", {}).get("label"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "variantRegistry": registry,
        "storedVariants": _rows(stored_variants),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_quantization_advisor.COGNIX_QUANTIZATION_ADVISOR_VERSION,
    }


@router.post("/quantization/plan")
async def adaptive_quantization_plan(
    payload: QuantizationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    model_metadata = dict(payload.model_metadata or recommendation_payload.get("recommendation") or {})
    if payload.model_id:
        model_metadata["modelId"] = payload.model_id
    plan = cognix_quantization_advisor.build_adaptive_quantization_plan(
        hardware = hardware,
        model_metadata = model_metadata,
        priority = payload.priority,
        latest_benchmark_run = latest_benchmark,
    )
    plan["projectId"] = payload.project_id
    plan["projectType"] = payload.project_type
    cognix_db.upsert_model_variants(plan.get("variantRegistry", {}).get("variants", []))
    profile = (
        cognix_db.create_quantization_profile(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_profile
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "modelVariantWrite": True,
        "profileWrite": profile is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "adaptive_quantization_plan_built",
        resource_type = "cognix_quantization_profile",
        resource_id = str((profile or {}).get("id") or payload.project_id or plan.get("model", {}).get("modelId") or "selected_model"),
        severity = "warning" if plan.get("selectedVariant", {}).get("fit", {}).get("status") == "tight" else "notice",
        metadata = {
            "advisorVersion": plan.get("advisorVersion"),
            "variantRegistryVersion": plan.get("variantRegistryVersion"),
            "performancePredictorVersion": plan.get("performancePredictorVersion"),
            "priority": plan.get("priority"),
            "modelId": plan.get("model", {}).get("modelId"),
            "selectedVariantId": plan.get("selectedVariant", {}).get("variantId"),
            "selectedQuantization": plan.get("selectedVariant", {}).get("quantization"),
            "badgeLabel": plan.get("badge", {}).get("label"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "quantizationPlan": plan,
        "profile": _row(profile) if profile else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_quantization_advisor.COGNIX_QUANTIZATION_ADVISOR_VERSION,
    }


@router.get("/quantization/profiles")
async def quantization_profiles(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "profiles": _rows(
            cognix_db.list_quantization_profiles(
                current_subject,
                project_id = project_id,
            )
        ),
        "sideEffects": {
            "modelLoad": False,
            "modelDownload": False,
            "modelConversion": False,
            "modelFileWrite": False,
            "runtimeConfigWrite": False,
            "networkCall": False,
            "benchmarkRun": False,
            "generation": False,
            "profileWrite": False,
        },
        "plannerVersion": cognix_quantization_advisor.COGNIX_QUANTIZATION_ADVISOR_VERSION,
    }


@router.get("/costs/providers")
async def cost_provider_profiles(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    store = cognix_cost_optimizer.build_provider_pricing_store(
        hardware = cognix_hardware.get_hardware_profile(),
    )
    stored_profiles = cognix_db.upsert_provider_profiles(store.get("profiles", []))
    side_effects = {
        **store.get("sideEffects", {}),
        "providerProfileWrite": bool(stored_profiles),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "provider_pricing_store_built",
        resource_type = "cognix_provider_pricing_store",
        resource_id = str(store.get("pricingStoreVersion")),
        severity = "notice",
        metadata = {
            "pricingStoreVersion": store.get("pricingStoreVersion"),
            "providerCount": store.get("providerCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "providerPricingStore": store,
        "storedProviderProfiles": _rows(stored_profiles),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_cost_optimizer.COGNIX_COST_OPTIMIZER_VERSION,
    }


@router.post("/costs/plan")
async def cost_optimization_plan(
    payload: CostOptimizationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_cost_optimizer.build_cost_optimization_plan(
        objective = payload.objective,
        hardware = cognix_hardware.get_hardware_profile(),
        project_type = payload.project_type,
        project_id = payload.project_id,
        priority = payload.priority,
        sensitivity_level = payload.sensitivity_level,
        constraints = payload.constraints,
        expected_input_tokens = payload.expected_input_tokens,
        expected_output_tokens = payload.expected_output_tokens,
        message_count = payload.message_count,
        budget_usd = payload.budget_usd,
        allow_cloud_when_sensitive = payload.allow_cloud_when_sensitive,
        provider_profiles = payload.provider_profiles,
    )
    stored_profiles = cognix_db.upsert_provider_profiles(
        plan.get("providerPricingStore", {}).get("profiles", [])
    )
    cost_log = (
        cognix_db.create_execution_cost_log(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_log
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "providerProfileWrite": bool(stored_profiles),
        "executionCostLogWrite": cost_log is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "cost_optimization_plan_built",
        resource_type = "cognix_execution_cost_log",
        resource_id = str((cost_log or {}).get("id") or payload.project_id or plan.get("decision", {}).get("selectedProviderId") or "cost_plan"),
        severity = "warning" if plan.get("policy", {}).get("cloudBlockedBecauseSensitive") else "notice",
        metadata = {
            "optimizerVersion": plan.get("optimizerVersion"),
            "pricingStoreVersion": plan.get("pricingStoreVersion"),
            "executionPlannerVersion": plan.get("executionPlannerVersion"),
            "privacyPolicyVersion": plan.get("privacyPolicyVersion"),
            "priority": plan.get("priority"),
            "selectedProviderId": plan.get("decision", {}).get("selectedProviderId"),
            "selectedExecutionTarget": plan.get("decision", {}).get("selectedExecutionTarget"),
            "estimatedCostUsd": plan.get("decision", {}).get("estimatedCostUsd"),
            "cloudBlockedBecauseSensitive": plan.get("policy", {}).get("cloudBlockedBecauseSensitive"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "costOptimizationPlan": plan,
        "costLog": _row(cost_log) if cost_log else None,
        "storedProviderProfiles": _rows(stored_profiles),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_cost_optimizer.COGNIX_COST_OPTIMIZER_VERSION,
    }


@router.get("/costs/logs")
async def execution_cost_logs(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "logs": _rows(
            cognix_db.list_execution_cost_logs(
                current_subject,
                project_id = project_id,
            )
        ),
        "sideEffects": {
            "networkCall": False,
            "providerCall": False,
            "billingMutation": False,
            "modelLoad": False,
            "generation": False,
            "runtimeConfigWrite": False,
            "executionCostLogWrite": False,
        },
        "plannerVersion": cognix_cost_optimizer.COGNIX_COST_OPTIMIZER_VERSION,
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
        title = payload.title or "Developer mode",
        risk_level = "critical",
        resource_type = "permission",
        resource_id = cognix_db.DEVELOPER_MODE_PERMISSION,
        metadata = {"approvalPolicy": "developer_mode_requires_admin"},
    )
    return {"request": _row(request)}


@router.post("/approvals")
async def create_approval_request(
    payload: ApprovalCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    request_type = payload.request_type or cognix_db.DEVELOPER_MODE_PERMISSION
    policy = cognix_admin_approvals.build_policy_decision(
        request_type = request_type,
        requester_role = (auth_storage.get_user_profile(current_subject) or {}).get("role") or "user",
        risk_level = payload.risk_level,
        has_permission = False,
    )
    request = cognix_db.create_approval_request(
        current_subject,
        request_type,
        payload.reason,
        title = payload.title or policy.get("requestType") or request_type,
        risk_level = str(policy.get("riskLevel") or payload.risk_level),
        resource_type = payload.resource_type or "",
        resource_id = payload.resource_id or "",
        metadata = {
            **(payload.metadata or {}),
            "policyDecision": policy,
        },
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "approval_requested",
        resource_type = "cognix_approval_request",
        resource_id = request.get("id"),
        severity = "warning" if policy.get("riskLevel") in {"high", "critical"} else "notice",
        metadata = {
            "requestType": request_type,
            "riskLevel": policy.get("riskLevel"),
            "requiresApproval": policy.get("requiresApproval"),
        },
    )
    return {
        "request": _row(request),
        "policy": policy,
        "auditLogId": audit.get("id"),
        "sideEffects": {"requestWrite": True, "auditWrite": True},
    }


@router.get("/approvals/me")
async def my_approval_requests(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    requests = cognix_db.list_approval_requests(username = current_subject)
    request_ids = {str(item.get("id") or "") for item in requests}
    decisions = [
        decision
        for decision in cognix_db.list_approval_decisions()
        if str(decision.get("request_id") or "") in request_ids
    ]
    comments = [
        comment
        for comment in cognix_db.list_approval_comments()
        if str(comment.get("request_id") or "") in request_ids
    ]
    return {
        "requests": _rows(requests),
        "queue": cognix_admin_approvals.build_approval_queue(
            requests = requests,
            decisions = decisions,
            comments = comments,
        ),
    }


@router.get("/approvals/blueprint")
async def approvals_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "approvalsBlueprint": cognix_admin_approvals.build_approvals_blueprint(),
    }


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


@router.get("/memory/skills/blueprint")
async def skill_memory_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_skill_memory.build_skill_memory_blueprint()
    return {
        "username": current_subject,
        "skillMemoryBlueprint": blueprint,
        "plannerVersion": cognix_skill_memory.COGNIX_SKILL_MEMORY_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.post("/memory/skills/candidates")
async def skill_memory_candidates(
    payload: SkillMemoryCandidateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    existing_memories = cognix_db.list_skill_memories(current_subject, include_disabled = True)
    plan = cognix_skill_memory.build_candidate_memory_plan(
        username = current_subject,
        observations = payload.observations,
        project_id = payload.project_id,
        project_type = payload.project_type,
        existing_memories = existing_memories,
    )
    stored_candidates = (
        cognix_db.create_memory_candidates(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_candidates
        else []
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "memoryCandidateWrite": bool(stored_candidates),
        "auditWrite": True,
        "skillMemoryWrite": False,
        "preferenceWrite": False,
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_candidates_built",
        resource_type = "cognix_skill_memory",
        resource_id = str(payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "skillMemoryVersion": plan.get("skillMemoryVersion"),
            "preferenceExtractorVersion": plan.get("preferenceExtractorVersion"),
            "candidateCount": plan.get("summary", {}).get("candidateCount", 0),
            "storedCandidateCount": len(stored_candidates),
            "requiresUserApproval": True,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "candidateMemoryPlan": plan,
        "storedCandidates": _rows(stored_candidates),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_SKILL_MEMORY_VERSION,
    }


@router.get("/memory/skills/candidates")
async def list_skill_memory_candidates(
    status: str | None = None,
    include_decided: bool = True,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "username": current_subject,
        "candidates": _rows(
            cognix_db.list_memory_candidates(
                current_subject,
                status = status,
                include_decided = include_decided,
            )
        ),
        "sideEffects": {
            "memoryCandidateWrite": False,
            "skillMemoryWrite": False,
            "preferenceWrite": False,
            "contextInjection": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.post("/memory/skills/candidates/{candidate_id}/approve")
async def approve_skill_memory_candidate(
    candidate_id: str,
    payload: SkillMemoryDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    result = cognix_db.approve_memory_candidate(
        current_subject,
        candidate_id,
        label = payload.label,
        value = payload.value,
        category = payload.category,
    )
    if result is None:
        raise HTTPException(status_code = 404, detail = "Memory candidate not found")
    preferences = result.get("preferences") or []
    side_effects = {
        "memoryCandidateWrite": True,
        "skillMemoryWrite": True,
        "preferenceWrite": bool(preferences),
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_candidate_approved",
        resource_type = "cognix_skill_memory",
        resource_id = str(result.get("memory", {}).get("id") or candidate_id),
        severity = "notice",
        metadata = {
            "candidateId": candidate_id,
            "candidateType": result.get("candidate", {}).get("candidate_type"),
            "category": result.get("memory", {}).get("category"),
            "sideEffects": side_effects,
        },
    )
    return {
        "candidate": _row(result.get("candidate") or {}),
        "memory": _row(result.get("memory") or {}),
        "preferences": _rows(preferences),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_MEMORY_APPROVAL_VERSION,
    }


@router.post("/memory/skills/candidates/{candidate_id}/reject")
async def reject_skill_memory_candidate(
    candidate_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    candidate = cognix_db.reject_memory_candidate(current_subject, candidate_id)
    if candidate is None:
        raise HTTPException(status_code = 404, detail = "Memory candidate not found")
    side_effects = {
        "memoryCandidateWrite": True,
        "skillMemoryWrite": False,
        "preferenceWrite": False,
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_candidate_rejected",
        resource_type = "cognix_skill_memory_candidate",
        resource_id = candidate_id,
        severity = "notice",
        metadata = {
            "candidateId": candidate_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "candidate": _row(candidate),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_MEMORY_APPROVAL_VERSION,
    }


@router.get("/memory/skills")
async def list_skill_memories(
    include_disabled: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "username": current_subject,
        "skillMemories": _rows(cognix_db.list_skill_memories(current_subject, include_disabled = include_disabled)),
        "preferences": _rows(cognix_db.list_user_preferences(current_subject, include_disabled = include_disabled)),
        "sideEffects": {
            "skillMemoryWrite": False,
            "preferenceWrite": False,
            "contextInjection": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/memory/skills/export")
async def export_skill_memories(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    bundle = cognix_db.export_skill_memory_bundle(current_subject)
    side_effects = {
        "exportRead": True,
        "memoryCandidateWrite": False,
        "skillMemoryWrite": False,
        "preferenceWrite": False,
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_exported",
        resource_type = "cognix_skill_memory",
        resource_id = current_subject,
        severity = "notice",
        metadata = {
            "skillMemoryCount": len(bundle.get("skillMemories") or []),
            "preferenceCount": len(bundle.get("preferences") or []),
            "candidateCount": len(bundle.get("candidates") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "memoryExport": {
            **bundle,
            "skillMemories": _rows(bundle.get("skillMemories") or []),
            "preferences": _rows(bundle.get("preferences") or []),
            "candidates": _rows(bundle.get("candidates") or []),
        },
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_SKILL_MEMORY_VERSION,
    }


@router.patch("/memory/skills/{memory_id}")
async def update_skill_memory(
    memory_id: str,
    payload: SkillMemoryUpdateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        memory = cognix_db.update_skill_memory(
            current_subject,
            memory_id,
            label = payload.label,
            value = payload.value,
            category = payload.category,
            status = payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code = 404, detail = "Skill memory not found")
    side_effects = {
        "skillMemoryWrite": True,
        "preferenceWrite": True,
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_updated",
        resource_type = "cognix_skill_memory",
        resource_id = memory_id,
        severity = "notice",
        metadata = {
            "status": memory.get("status"),
            "category": memory.get("category"),
            "sideEffects": side_effects,
        },
    )
    return {
        "memory": _row(memory),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_MEMORY_APPROVAL_VERSION,
    }


@router.delete("/memory/skills/{memory_id}")
async def delete_skill_memory(
    memory_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    deleted = cognix_db.delete_skill_memory(current_subject, memory_id)
    if not deleted:
        raise HTTPException(status_code = 404, detail = "Skill memory not found")
    side_effects = {
        "skillMemoryWrite": True,
        "preferenceWrite": True,
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_deleted",
        resource_type = "cognix_skill_memory",
        resource_id = memory_id,
        severity = "notice",
        metadata = {
            "memoryId": memory_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "deleted": True,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_MEMORY_APPROVAL_VERSION,
    }


@router.post("/memory/skills/injection-plan")
async def skill_memory_injection_plan(
    payload: SkillMemoryInjectionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    active_memories = cognix_db.list_skill_memories(current_subject)
    plan = cognix_skill_memory.build_context_injection_plan(
        username = current_subject,
        objective = payload.objective,
        active_memories = active_memories,
        max_memories = payload.max_memories,
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "memoryCandidateWrite": False,
        "skillMemoryWrite": False,
        "preferenceWrite": False,
        "contextInjection": False,
        "modelLoad": False,
        "generation": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_memory_injection_plan_built",
        resource_type = "cognix_skill_memory",
        resource_id = current_subject,
        severity = "notice",
        metadata = {
            "contextInjectorVersion": plan.get("contextInjectorVersion"),
            "selectedMemoryCount": plan.get("summary", {}).get("selectedMemoryCount", 0),
            "sideEffects": side_effects,
        },
    )
    return {
        "injectionPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_memory.COGNIX_CONTEXT_INJECTOR_VERSION,
    }


@router.get("/personal-twin/blueprint")
async def personal_twin_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_personal_twin.build_personal_twin_blueprint()
    return {
        "username": current_subject,
        "personalTwinBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_personal_twin.COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
    }


@router.post("/personal-twin/profile/plan")
async def personal_twin_profile_plan(
    payload: PersonalTwinProfilePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    existing_profile = cognix_db.get_personal_ai_profile(current_subject)
    plan = cognix_personal_twin.build_personal_twin_profile_plan(
        username = current_subject,
        interactions = payload.interactions,
        existing_profile = existing_profile,
        activate = payload.activate,
    )
    stored_profile = (
        cognix_db.upsert_personal_ai_profile(
            current_subject,
            plan = plan,
            activate = payload.activate,
        )
        if payload.store_profile
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "profileWrite": stored_profile is not None,
        "styleProfileWrite": bool((stored_profile or {}).get("styleProfiles")),
        "ruleWrite": bool((stored_profile or {}).get("personalizationRules")),
        "contextInjection": False,
        "autonomousAction": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "networkCall": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "personal_twin_profile_planned",
        resource_type = "cognix_personal_ai_profile",
        resource_id = str((stored_profile or {}).get("id") or current_subject),
        severity = "notice",
        metadata = {
            "personalTwinServiceVersion": plan.get("personalTwinServiceVersion"),
            "profileConfidence": plan.get("summary", {}).get("profileConfidence"),
            "ruleCount": plan.get("summary", {}).get("ruleCount"),
            "styleSignalCount": plan.get("summary", {}).get("styleSignalCount"),
            "stored": stored_profile is not None,
            "activated": payload.activate,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "personalTwinPlan": plan,
        "profile": _row(stored_profile) if stored_profile else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_personal_twin.COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
    }


@router.get("/personal-twin/profile")
async def personal_twin_profile(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    profile = cognix_db.get_personal_ai_profile(current_subject)
    return {
        "username": current_subject,
        "profile": _row(profile) if profile else None,
        "sideEffects": {
            "profileWrite": False,
            "styleProfileWrite": False,
            "ruleWrite": False,
            "contextInjection": False,
            "autonomousAction": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
        "plannerVersion": cognix_personal_twin.COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
    }


@router.patch("/personal-twin/profile/status")
async def personal_twin_profile_status(
    payload: PersonalTwinStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    profile = cognix_db.set_personal_ai_profile_status(current_subject, payload.status)
    if profile is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Personal AI profile not found")
    side_effects = {
        "profileWrite": True,
        "styleProfileWrite": payload.status == "reset",
        "ruleWrite": True,
        "contextInjection": False,
        "autonomousAction": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "networkCall": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "personal_twin_status_updated",
        resource_type = "cognix_personal_ai_profile",
        resource_id = str(profile.get("id") or current_subject),
        severity = "warning" if payload.status == "reset" else "notice",
        metadata = {
            "status": payload.status,
            "styleProfileCount": len(profile.get("styleProfiles") or []),
            "ruleCount": len(profile.get("personalizationRules") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "profile": _row(profile),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_personal_twin.COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
    }


@router.get("/personal-twin/export")
async def personal_twin_export(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    export = cognix_db.export_personal_ai_profile(current_subject)
    if export is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Personal AI profile not found")
    side_effects = {
        "exportRead": True,
        "profileWrite": False,
        "styleProfileWrite": False,
        "ruleWrite": False,
        "contextInjection": False,
        "autonomousAction": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "networkCall": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "personal_twin_exported",
        resource_type = "cognix_personal_ai_profile",
        resource_id = str((export.get("profile") or {}).get("id") or current_subject),
        severity = "notice",
        metadata = {
            "schemaVersion": export.get("schemaVersion"),
            "styleProfileCount": len((export.get("profile") or {}).get("styleProfiles") or []),
            "ruleCount": len((export.get("profile") or {}).get("personalizationRules") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "profileExport": {
            **export,
            "profile": _row(export.get("profile") or {}),
        },
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_personal_twin.COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
    }


@router.post("/personal-twin/injection-plan")
async def personal_twin_injection_plan(
    payload: PersonalTwinInjectionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    profile = cognix_db.get_personal_ai_profile(current_subject)
    plan = cognix_personal_twin.build_personalization_injection_plan(
        username = current_subject,
        profile = profile,
        objective = payload.objective,
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "personal_twin_injection_plan_built",
        resource_type = "cognix_personal_ai_profile",
        resource_id = str((profile or {}).get("id") or current_subject),
        severity = "notice",
        metadata = {
            "personalizationEngineVersion": plan.get("personalizationEngineVersion"),
            "profileStatus": plan.get("profileStatus"),
            "selectedRuleCount": plan.get("profileSummary", {}).get("selectedRuleCount"),
            "willInjectNow": plan.get("willInjectNow"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "injectionPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_personal_twin.COGNIX_PERSONALIZATION_ENGINE_VERSION,
    }


@router.get("/memory/editor/blueprint")
async def live_memory_editor_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_memory_editor.build_memory_editor_blueprint()
    return {
        "username": current_subject,
        "memoryEditorBlueprint": blueprint,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_EDITOR_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.post("/memory/editor/items")
async def create_live_memory_item(
    payload: LiveMemoryCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_memory_editor.build_memory_item_plan(
        username = current_subject,
        title = payload.title,
        content = payload.content,
        category = payload.category,
        project_id = payload.project_id,
        sensitive = payload.sensitive,
        confirmed_sensitive_control = payload.confirmed_sensitive_control,
        metadata = payload.metadata,
    )
    if plan.get("policy", {}).get("blocked"):
        raise HTTPException(status_code = 400, detail = plan.get("policy", {}).get("reason") or "Memory blocked")
    stored_memory = (
        cognix_db.create_live_memory(current_subject, plan = plan, actor_username = current_subject)
        if payload.store_memory
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "memoryWrite": bool(stored_memory),
        "versionWrite": bool(stored_memory),
        "auditWrite": True,
        "memoryDelete": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "live_memory_created",
        resource_type = "cognix_live_memory",
        resource_id = str(stored_memory.get("id") if stored_memory else current_subject),
        severity = "notice",
        metadata = {
            "memoryEditorVersion": plan.get("memoryEditorVersion"),
            "category": plan.get("memory", {}).get("category"),
            "sensitive": plan.get("memory", {}).get("sensitive"),
            "stored": bool(stored_memory),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "memoryItemPlan": plan,
        "memory": _row(stored_memory) if stored_memory else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_EDITOR_VERSION,
    }


@router.get("/memory/editor/items")
async def list_live_memory_items(
    category: str | None = None,
    query: str | None = None,
    include_disabled: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "username": current_subject,
        "items": _rows(
            cognix_db.list_live_memories(
                current_subject,
                category = cognix_memory_editor.normalize_category(category) if category else None,
                query = query,
                include_disabled = include_disabled,
            )
        ),
        "sideEffects": {
            "memoryWrite": False,
            "versionWrite": False,
            "auditWrite": False,
            "memoryDelete": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/memory/editor/items/{memory_id}")
async def get_live_memory_item(
    memory_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    memory = cognix_db.get_live_memory(current_subject, memory_id)
    if memory is None:
        raise HTTPException(status_code = 404, detail = "Live memory not found")
    return {
        "username": current_subject,
        "memory": _row(memory),
        "sideEffects": {
            "memoryWrite": False,
            "versionWrite": False,
            "auditWrite": False,
            "memoryDelete": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.patch("/memory/editor/items/{memory_id}")
async def update_live_memory_item(
    memory_id: str,
    payload: LiveMemoryUpdateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    existing = cognix_db.get_live_memory(current_subject, memory_id)
    if existing is None:
        raise HTTPException(status_code = 404, detail = "Live memory not found")
    plan = cognix_memory_editor.build_memory_edit_plan(
        existing_memory = existing,
        title = payload.title,
        content = payload.content,
        category = payload.category,
        reason = payload.reason,
    )
    try:
        memory = cognix_db.update_live_memory(
            current_subject,
            memory_id,
            actor_username = current_subject,
            title = payload.title,
            content = payload.content,
            category = cognix_memory_editor.normalize_category(payload.category) if payload.category else None,
            reason = payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code = 404, detail = "Live memory not found")
    side_effects = {
        **plan.get("sideEffects", {}),
        "memoryWrite": True,
        "versionWrite": True,
        "auditWrite": True,
        "memoryDelete": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "live_memory_updated",
        resource_type = "cognix_live_memory",
        resource_id = memory_id,
        severity = "notice",
        metadata = {
            "changes": plan.get("changes", []),
            "nextVersion": memory.get("current_version"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "memoryEditPlan": plan,
        "memory": _row(memory),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_VERSIONING_VERSION,
    }


@router.post("/memory/editor/items/{memory_id}/disable")
async def disable_live_memory_item(
    memory_id: str,
    payload: LiveMemoryStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    memory = cognix_db.set_live_memory_status(
        current_subject,
        memory_id,
        status = "disabled",
        actor_username = current_subject,
        reason = payload.reason or "memory_disabled",
    )
    if memory is None:
        raise HTTPException(status_code = 404, detail = "Live memory not found")
    side_effects = {
        "memoryWrite": True,
        "versionWrite": True,
        "auditWrite": True,
        "memoryDelete": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "live_memory_disabled",
        resource_type = "cognix_live_memory",
        resource_id = memory_id,
        severity = "notice",
        metadata = {
            "status": memory.get("status"),
            "sideEffects": side_effects,
        },
    )
    return {
        "memory": _row(memory),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_VERSIONING_VERSION,
    }


@router.delete("/memory/editor/items/{memory_id}")
async def delete_live_memory_item(
    memory_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    memory = cognix_db.set_live_memory_status(
        current_subject,
        memory_id,
        status = "deleted",
        actor_username = current_subject,
        reason = "memory_deleted",
    )
    if memory is None:
        raise HTTPException(status_code = 404, detail = "Live memory not found")
    side_effects = {
        "memoryWrite": True,
        "versionWrite": True,
        "auditWrite": True,
        "memoryDelete": True,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "live_memory_deleted",
        resource_type = "cognix_live_memory",
        resource_id = memory_id,
        severity = "notice",
        metadata = {
            "softDelete": True,
            "sideEffects": side_effects,
        },
    )
    return {
        "deleted": True,
        "memory": _row(memory),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_VERSIONING_VERSION,
    }


@router.post("/memory/editor/merge")
async def merge_live_memory_items(
    payload: LiveMemoryMergeRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    source_ids = list(dict.fromkeys(str(item) for item in payload.source_ids if str(item).strip()))
    if len(source_ids) < 2:
        raise HTTPException(status_code = 400, detail = "At least two distinct memories are required")
    source_memories: list[dict[str, Any]] = []
    for memory_id in source_ids:
        memory = cognix_db.get_live_memory(current_subject, memory_id)
        if memory is None or memory.get("status") == "deleted":
            raise HTTPException(status_code = 404, detail = f"Live memory not found: {memory_id}")
        source_memories.append(memory)
    plan = cognix_memory_editor.build_memory_merge_plan(
        username = current_subject,
        source_memories = source_memories,
        title = payload.title,
        category = payload.category,
        metadata = payload.metadata,
    )
    memory = cognix_db.merge_live_memories(
        current_subject,
        plan = plan,
        actor_username = current_subject,
        disable_sources = payload.disable_sources,
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "memoryWrite": True,
        "versionWrite": True,
        "auditWrite": True,
        "memoryDelete": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "live_memory_merged",
        resource_type = "cognix_live_memory",
        resource_id = str(memory.get("id")),
        severity = "notice",
        metadata = {
            "sourceMemoryIds": source_ids,
            "disableSources": payload.disable_sources,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "memoryMergePlan": plan,
        "memory": _row(memory),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_VERSIONING_VERSION,
    }


@router.get("/memory/editor/export")
async def export_live_memory_items(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    bundle = cognix_db.export_live_memory_bundle(current_subject)
    side_effects = {
        "exportRead": True,
        "memoryWrite": False,
        "versionWrite": False,
        "auditWrite": True,
        "memoryDelete": False,
        "modelLoad": False,
        "generation": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "live_memory_exported",
        resource_type = "cognix_live_memory",
        resource_id = current_subject,
        severity = "notice",
        metadata = {
            "memoryCount": len(bundle.get("memories") or []),
            "versionCount": len(bundle.get("versions") or []),
            "auditLogCount": len(bundle.get("auditLogs") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "memoryExport": {
            **bundle,
            "memories": _rows(bundle.get("memories") or []),
            "versions": _rows(bundle.get("versions") or []),
            "auditLogs": _rows(bundle.get("auditLogs") or []),
        },
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_memory_editor.COGNIX_MEMORY_SEARCH_VERSION,
    }


@router.get("/memory/editor/audit-logs")
async def list_live_memory_audit_logs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "username": current_subject,
        "auditLogs": _rows(cognix_db.list_live_memory_audit_logs(current_subject)),
        "sideEffects": {
            "memoryWrite": False,
            "versionWrite": False,
            "auditWrite": False,
            "memoryDelete": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/workflows/blueprint")
async def workflow_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_workflow_recorder.build_workflow_blueprint()
    return {
        "username": current_subject,
        "workflowBlueprint": blueprint,
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_RECORDER_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/workflows/templates")
async def workflow_templates(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_workflow_recorder.build_workflow_template_registry()
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "workflow_template_registry_built",
        resource_type = "cognix_workflow",
        resource_id = current_subject,
        severity = "notice",
        metadata = {
            "workflowTemplateManagerVersion": registry.get("workflowTemplateManagerVersion"),
            "templateCount": registry.get("summary", {}).get("templateCount", 0),
            "sideEffects": registry.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "templateRegistry": registry,
        "auditLogId": audit.get("id"),
        "sideEffects": registry.get("sideEffects", {}),
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_TEMPLATE_MANAGER_VERSION,
    }


@router.post("/workflows/record")
async def record_workflow(
    payload: WorkflowRecordRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_workflow_recorder.build_workflow_recording_plan(
        username = current_subject,
        title = payload.title,
        objective = payload.objective,
        workflow_type = payload.workflow_type,
        steps = payload.steps,
        project_id = payload.project_id,
        metadata = payload.metadata,
    )
    workflow = (
        cognix_db.create_workflow_from_plan(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_workflow
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "workflowWrite": workflow is not None,
        "workflowRunWrite": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "exportWrite": False,
        "networkCall": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "workflow_recording_built",
        resource_type = "cognix_workflow",
        resource_id = str((workflow or {}).get("id") or payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "workflowRecorderVersion": plan.get("workflowRecorderVersion"),
            "workflowType": plan.get("workflow", {}).get("workflowType"),
            "stepCount": plan.get("summary", {}).get("stepCount", 0),
            "stored": workflow is not None,
            "sideEffects": side_effects,
        },
    )
    return {
        "recordingPlan": plan,
        "workflow": _row(workflow) if workflow else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_RECORDER_VERSION,
    }


@router.get("/workflows")
async def list_workflows(
    include_disabled: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "username": current_subject,
        "workflows": _rows(cognix_db.list_workflows(current_subject, include_disabled = include_disabled)),
        "sideEffects": {
            "workflowWrite": False,
            "workflowRunWrite": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    workflow = cognix_db.get_workflow(current_subject, workflow_id)
    if workflow is None:
        raise HTTPException(status_code = 404, detail = "Workflow not found")
    return {
        "workflow": _row(workflow),
        "sideEffects": {
            "workflowWrite": False,
            "workflowRunWrite": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.patch("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        workflow = cognix_db.update_workflow(
            current_subject,
            workflow_id,
            title = payload.title,
            objective = payload.objective,
            status = payload.status,
            share_status = payload.share_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if workflow is None:
        raise HTTPException(status_code = 404, detail = "Workflow not found")
    side_effects = {
        "workflowWrite": True,
        "workflowRunWrite": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "exportWrite": False,
        "networkCall": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "workflow_updated",
        resource_type = "cognix_workflow",
        resource_id = workflow_id,
        severity = "notice",
        metadata = {
            "status": workflow.get("status"),
            "shareStatus": workflow.get("share_status"),
            "sideEffects": side_effects,
        },
    )
    return {
        "workflow": _row(workflow),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_RECORDER_VERSION,
    }


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    deleted = cognix_db.delete_workflow(current_subject, workflow_id)
    if not deleted:
        raise HTTPException(status_code = 404, detail = "Workflow not found")
    side_effects = {
        "workflowWrite": True,
        "workflowRunWrite": True,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "exportWrite": False,
        "networkCall": False,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "workflow_deleted",
        resource_type = "cognix_workflow",
        resource_id = workflow_id,
        severity = "notice",
        metadata = {"workflowId": workflow_id, "sideEffects": side_effects},
    )
    return {
        "deleted": True,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_RECORDER_VERSION,
    }


@router.get("/workflows/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    bundle = cognix_db.export_workflow_bundle(current_subject, workflow_id)
    if bundle is None:
        raise HTTPException(status_code = 404, detail = "Workflow not found")
    side_effects = {
        "workflowWrite": False,
        "workflowRunWrite": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "exportWrite": False,
        "networkCall": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "workflow_exported",
        resource_type = "cognix_workflow",
        resource_id = workflow_id,
        severity = "notice",
        metadata = {
            "workflowId": workflow_id,
            "runCount": len(bundle.get("runs") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "workflowExport": {
            **bundle,
            "workflow": _row(bundle.get("workflow") or {}),
            "runs": _rows(bundle.get("runs") or []),
        },
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_RECORDER_VERSION,
    }


@router.post("/workflows/{workflow_id}/run-plan")
async def workflow_run_plan(
    workflow_id: str,
    payload: WorkflowRunPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    workflow = cognix_db.get_workflow(current_subject, workflow_id)
    if workflow is None:
        raise HTTPException(status_code = 404, detail = "Workflow not found")
    plan = cognix_workflow_recorder.build_workflow_run_plan(
        username = current_subject,
        workflow = workflow,
        steps = workflow.get("steps") or [],
        run_mode = payload.run_mode,
        inputs = payload.inputs,
    )
    run = cognix_db.create_workflow_run_plan_record(
        current_subject,
        workflow_id = workflow_id,
        plan = plan,
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "workflowWrite": False,
        "workflowRunWrite": True,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "exportWrite": False,
        "networkCall": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "workflow_run_plan_built",
        resource_type = "cognix_workflow_run",
        resource_id = str(run.get("id") or workflow_id),
        severity = "notice",
        metadata = {
            "workflowId": workflow_id,
            "workflowRunnerVersion": plan.get("workflowRunnerVersion"),
            "stepCount": plan.get("summary", {}).get("stepCount", 0),
            "sideEffects": side_effects,
        },
    )
    return {
        "runPlan": plan,
        "run": _row(run),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_workflow_recorder.COGNIX_WORKFLOW_RUNNER_VERSION,
    }


@router.get("/workflows/{workflow_id}/runs")
async def workflow_runs(
    workflow_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if cognix_db.get_workflow(current_subject, workflow_id) is None:
        raise HTTPException(status_code = 404, detail = "Workflow not found")
    return {
        "runs": _rows(cognix_db.list_workflow_runs(current_subject, workflow_id)),
        "sideEffects": {
            "workflowWrite": False,
            "workflowRunWrite": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/prompt-compression/blueprint")
async def prompt_compression_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_prompt_compression.build_prompt_compression_blueprint()
    return {
        "username": current_subject,
        "promptCompressionBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_prompt_compression.COGNIX_PROMPT_COMPRESSION_VERSION,
    }


@router.post("/prompt-compression/plan")
async def prompt_compression_plan(
    payload: PromptCompressionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_prompt_compression.build_prompt_compression_plan(
        username = current_subject,
        context = payload.context,
        objective = payload.objective,
        target_tokens = payload.target_tokens,
        project_id = payload.project_id,
    )
    stored_context = (
        cognix_db.create_compressed_context(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_context
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "compressionWrite": stored_context is not None,
        "logWrite": stored_context is not None,
        "modelLoad": False,
        "generation": False,
        "networkCall": False,
        "promptMutation": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "prompt_compression_plan_built",
        resource_type = "cognix_prompt_compression",
        resource_id = str((stored_context or {}).get("id") or payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "promptCompressionVersion": plan.get("promptCompressionVersion"),
            "contextRankerVersion": plan.get("contextRankerVersion"),
            "compressionEvaluatorVersion": plan.get("compressionEvaluatorVersion"),
            "originalTokenCount": plan.get("summary", {}).get("originalTokenCount"),
            "compressedTokenCount": plan.get("summary", {}).get("compressedTokenCount"),
            "reductionRatio": plan.get("summary", {}).get("reductionRatio"),
            "lostInfoRisk": plan.get("summary", {}).get("lostInfoRisk"),
            "sideEffects": side_effects,
        },
    )
    return {
        "compressionPlan": plan,
        "compressedContext": _row(stored_context) if stored_context else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_prompt_compression.COGNIX_PROMPT_COMPRESSION_VERSION,
    }


@router.get("/context/heatmap/blueprint")
async def context_heatmap_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_context_heatmap.build_context_heatmap_blueprint()
    return {
        "username": current_subject,
        "contextHeatmapBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_context_heatmap.COGNIX_CONTEXT_HEATMAP_GENERATOR_VERSION,
    }


@router.post("/context/heatmap/plan")
async def context_heatmap_plan(
    payload: ContextHeatmapPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_context_heatmap.build_context_heatmap_plan(
        username = current_subject,
        context_chunks = payload.context_chunks,
        response_usage = payload.response_usage,
        objective = payload.objective,
        project_id = payload.project_id,
    )
    stored = (
        cognix_db.create_context_heatmap_entries(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_heatmap
        else {"entries": [], "usageStats": []}
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "usageStatsWrite": payload.store_heatmap,
        "heatmapEntryWrite": payload.store_heatmap,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "context_heatmap_plan_built",
        resource_type = "cognix_context_heatmap",
        resource_id = str(payload.project_id or current_subject),
        severity = "warning" if plan.get("summary", {}).get("archiveCandidateCount") else "notice",
        metadata = {
            "usageTrackerVersion": plan.get("usageTrackerVersion"),
            "heatmapGeneratorVersion": plan.get("heatmapGeneratorVersion"),
            "memoryGarbageCollectorVersion": plan.get("memoryGarbageCollectorVersion"),
            "chunkCount": plan.get("summary", {}).get("chunkCount"),
            "bucketCounts": plan.get("summary", {}).get("bucketCounts"),
            "archiveCandidateCount": plan.get("summary", {}).get("archiveCandidateCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "contextHeatmapPlan": plan,
        "storedHeatmapEntries": _rows(stored.get("entries", [])),
        "storedUsageStats": _rows(stored.get("usageStats", [])),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_context_heatmap.COGNIX_CONTEXT_HEATMAP_GENERATOR_VERSION,
    }


@router.get("/context/heatmap/entries")
async def context_heatmap_entries(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "entries": _rows(cognix_db.list_context_heatmap_entries(current_subject, project_id = project_id)),
        "usageStats": _rows(cognix_db.list_context_usage_stats(current_subject, project_id = project_id)),
        "sideEffects": {
            "usageStatsWrite": False,
            "heatmapEntryWrite": False,
            "memoryArchive": False,
            "memoryDelete": False,
            "contextMutation": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
        "plannerVersion": cognix_context_heatmap.COGNIX_CONTEXT_HEATMAP_GENERATOR_VERSION,
    }


@router.get("/memory/cleanup/blueprint")
async def memory_cleanup_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_context_heatmap.build_memory_cleanup_blueprint()
    return {
        "username": current_subject,
        "memoryCleanupBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_context_heatmap.COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION,
    }


@router.post("/memory/cleanup/plan")
async def memory_cleanup_plan(
    payload: MemoryCleanupPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_context_heatmap.build_memory_cleanup_plan(
        username = current_subject,
        memories = payload.memories,
        usage_entries = payload.usage_entries,
        project_id = payload.project_id,
    )
    stored = (
        cognix_db.create_memory_cleanup_plan_records(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_suggestions
        else {"suggestions": [], "conflicts": []}
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "suggestionWrite": bool(stored.get("suggestions")),
        "conflictWrite": bool(stored.get("conflicts")),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "memory_cleanup_plan_built",
        resource_type = "cognix_memory_cleanup",
        resource_id = current_subject,
        severity = "warning" if plan.get("summary", {}).get("suggestionCount") else "notice",
        metadata = {
            "memoryGarbageCollectorVersion": plan.get("memoryGarbageCollectorVersion"),
            "memoryConflictResolverVersion": plan.get("memoryConflictResolverVersion"),
            "suggestionCount": plan.get("summary", {}).get("suggestionCount"),
            "conflictCount": plan.get("summary", {}).get("conflictCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "memoryCleanupPlan": plan,
        "storedSuggestions": _rows(stored.get("suggestions") or []),
        "storedConflicts": _rows(stored.get("conflicts") or []),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_context_heatmap.COGNIX_MEMORY_GARBAGE_COLLECTOR_VERSION,
    }


@router.get("/memory/cleanup/suggestions")
async def memory_cleanup_suggestions(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    suggestions = cognix_db.list_memory_cleanup_suggestions(current_subject, project_id = project_id, limit = limit)
    return {"username": current_subject, "suggestions": _rows(suggestions), "count": len(suggestions)}


@router.get("/memory/cleanup/conflicts")
async def memory_conflicts(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    conflicts = cognix_db.list_memory_conflicts(current_subject, project_id = project_id, limit = limit)
    return {"username": current_subject, "conflicts": _rows(conflicts), "count": len(conflicts)}


@router.get("/prompt-compression/contexts")
async def list_compressed_contexts(
    include_deleted: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "contexts": _rows(cognix_db.list_compressed_contexts(current_subject, include_deleted = include_deleted)),
        "sideEffects": {
            "compressionWrite": False,
            "logWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "promptMutation": False,
        },
    }


@router.get("/prompt-compression/contexts/{context_id}")
async def get_compressed_context(
    context_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    context = cognix_db.get_compressed_context(current_subject, context_id)
    if context is None:
        raise HTTPException(status_code = 404, detail = "Compressed context not found")
    return {
        "compressedContext": _row(context),
        "sideEffects": {
            "compressionWrite": False,
            "logWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "promptMutation": False,
        },
    }


@router.delete("/prompt-compression/contexts/{context_id}")
async def delete_compressed_context(
    context_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    deleted = cognix_db.delete_compressed_context(current_subject, context_id)
    if not deleted:
        raise HTTPException(status_code = 404, detail = "Compressed context not found")
    side_effects = {
        "compressionWrite": True,
        "logWrite": False,
        "modelLoad": False,
        "generation": False,
        "networkCall": False,
        "promptMutation": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "prompt_compression_context_deleted",
        resource_type = "cognix_prompt_compression",
        resource_id = context_id,
        severity = "notice",
        metadata = {"contextId": context_id, "sideEffects": side_effects},
    )
    return {
        "deleted": True,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_prompt_compression.COGNIX_PROMPT_COMPRESSION_VERSION,
    }


@router.get("/intent/blueprint")
async def intent_prediction_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_intent_prediction.build_intent_prediction_blueprint()
    return {
        "username": current_subject,
        "intentPredictionBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_intent_prediction.COGNIX_INTENT_PREDICTION_VERSION,
    }


@router.post("/intent/predict")
async def intent_predict(
    payload: IntentPredictionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    prediction = cognix_intent_prediction.build_intent_prediction(
        username = current_subject,
        project_type = payload.project_type,
        draft_text = payload.draft_text,
        recent_messages = payload.recent_messages,
        project_id = payload.project_id,
    )
    input_excerpt = " ".join(
        item
        for item in [payload.project_type or "", payload.draft_text or ""]
        if item
    )[:1000]
    stored_prediction = (
        cognix_db.create_intent_prediction(
            current_subject,
            prediction = prediction,
            project_id = payload.project_id,
            input_excerpt = input_excerpt,
        )
        if payload.store_prediction
        else None
    )
    side_effects = {
        **prediction.get("sideEffects", {}),
        "predictionWrite": stored_prediction is not None,
        "preloadEventWrite": bool((stored_prediction or {}).get("preloadEvents")),
        "modelLoad": False,
        "modelUnload": False,
        "generation": False,
        "networkCall": False,
        "uiSuggestion": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "intent_prediction_built",
        resource_type = "cognix_intent_prediction",
        resource_id = str((stored_prediction or {}).get("id") or payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "intentPredictionVersion": prediction.get("intentPredictionVersion"),
            "preloadSchedulerVersion": prediction.get("preloadSchedulerVersion"),
            "selectedDomain": prediction.get("selectedDomain"),
            "confidence": prediction.get("confidence"),
            "suggestionCount": prediction.get("summary", {}).get("suggestionCount"),
            "abruptDomainChange": prediction.get("summary", {}).get("abruptDomainChange"),
            "sideEffects": side_effects,
        },
    )
    return {
        "intentPrediction": prediction,
        "storedPrediction": _row(stored_prediction) if stored_prediction else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_intent_prediction.COGNIX_INTENT_PREDICTION_VERSION,
    }


@router.get("/intent/predictions")
async def intent_predictions(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "predictions": _rows(cognix_db.list_intent_predictions(current_subject)),
        "sideEffects": {
            "predictionWrite": False,
            "preloadEventWrite": False,
            "modelLoad": False,
            "modelUnload": False,
            "generation": False,
            "networkCall": False,
            "uiSuggestion": False,
        },
    }


@router.get("/intent/preload-events")
async def intent_preload_events(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "events": _rows(cognix_db.list_preload_events(current_subject)),
        "sideEffects": {
            "predictionWrite": False,
            "preloadEventWrite": False,
            "modelLoad": False,
            "modelUnload": False,
            "generation": False,
            "networkCall": False,
            "uiSuggestion": False,
        },
    }


@router.get("/dynamic-ui/blueprint")
async def dynamic_ui_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_dynamic_ui.build_dynamic_ui_blueprint()
    return {
        "username": current_subject,
        "dynamicUiBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_dynamic_ui.COGNIX_DYNAMIC_UI_VERSION,
    }


@router.post("/dynamic-ui/profile")
async def dynamic_ui_profile(
    payload: DynamicUIProfileRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    profile = cognix_dynamic_ui.build_project_ui_profile(
        username = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        viewport = payload.viewport,
        theme = payload.theme,
    )
    stored_profile = (
        cognix_db.create_project_ui_profile(
            current_subject,
            profile = profile,
            project_id = payload.project_id,
        )
        if payload.store_profile
        else None
    )
    side_effects = {
        **profile.get("sideEffects", {}),
        "profileWrite": stored_profile is not None,
        "uiMutation": False,
        "routeMutation": False,
        "themeMutation": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "dynamic_ui_profile_built",
        resource_type = "cognix_dynamic_ui",
        resource_id = str((stored_profile or {}).get("id") or payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "dynamicUiVersion": profile.get("dynamicUiVersion"),
            "layoutProfileVersion": profile.get("layoutProfileVersion"),
            "projectType": profile.get("projectType"),
            "viewport": profile.get("viewport"),
            "theme": profile.get("theme"),
            "sideEffects": side_effects,
        },
    )
    return {
        "uiProfile": profile,
        "storedProfile": _row(stored_profile) if stored_profile else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_dynamic_ui.COGNIX_DYNAMIC_UI_VERSION,
    }


@router.get("/dynamic-ui/profiles")
async def dynamic_ui_profiles(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "profiles": _rows(cognix_db.list_project_ui_profiles(current_subject)),
        "sideEffects": {
            "profileWrite": False,
            "uiMutation": False,
            "routeMutation": False,
            "themeMutation": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/background-agents/blueprint")
async def background_agents_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_background_agents.build_background_agent_blueprint()
    return {
        "username": current_subject,
        "backgroundAgentBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_background_agents.COGNIX_BACKGROUND_AGENT_VERSION,
    }


@router.post("/background-agents/job-plan")
async def background_agent_job_plan(
    payload: BackgroundJobPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_background_agents.build_background_agent_job_plan(
        username = current_subject,
        task = payload.task,
        job_type = payload.job_type,
        project_id = payload.project_id,
        priority = payload.priority,
        night_mode = payload.night_mode,
    )
    job = (
        cognix_db.create_background_job_from_plan(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.enqueue_job
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "jobEnqueue": job is not None,
        "agentRunWrite": job is not None,
        "progressLogWrite": job is not None,
        "workerStart": False,
        "toolExecution": False,
        "modelLoad": False,
        "generation": False,
        "notificationSend": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "background_agent_job_planned",
        resource_type = "cognix_background_agent",
        resource_id = str((job or {}).get("id") or payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "backgroundAgentVersion": plan.get("backgroundAgentVersion"),
            "jobType": plan.get("jobType"),
            "priority": plan.get("priority"),
            "nightMode": plan.get("nightMode"),
            "sideEffects": side_effects,
        },
    )
    return {
        "jobPlan": plan,
        "job": _row(job) if job else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_background_agents.COGNIX_BACKGROUND_AGENT_VERSION,
    }


@router.get("/background-agents/jobs")
async def background_agent_jobs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "jobs": _rows(cognix_db.list_background_jobs(current_subject)),
        "sideEffects": {
            "jobEnqueue": False,
            "agentRunWrite": False,
            "progressLogWrite": False,
            "workerStart": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "notificationSend": False,
        },
    }


@router.get("/background-agents/jobs/{job_id}")
async def background_agent_job(
    job_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    job = cognix_db.get_background_job(current_subject, job_id)
    if job is None:
        raise HTTPException(status_code = 404, detail = "Background job not found")
    return {
        "job": _row(job),
        "sideEffects": {
            "jobEnqueue": False,
            "agentRunWrite": False,
            "progressLogWrite": False,
            "workerStart": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "notificationSend": False,
        },
    }


@router.get("/timeline/blueprint")
async def timeline_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_timeline.build_timeline_blueprint()
    return {
        "username": current_subject,
        "timelineBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_timeline.COGNIX_TIMELINE_VERSION,
    }


@router.post("/timeline/events")
async def create_timeline_event(
    payload: TimelineEventRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_timeline.build_timeline_event_plan(
        username = current_subject,
        title = payload.title,
        summary = payload.summary,
        project_id = payload.project_id,
        event_type = payload.event_type,
        source_type = payload.source_type,
        source_id = payload.source_id,
        metadata = payload.metadata,
    )
    event = (
        cognix_db.create_timeline_event(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_event
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "timelineWrite": event is not None,
        "uiMutation": False,
        "modelLoad": False,
        "generation": False,
        "toolExecution": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "timeline_event_planned",
        resource_type = "cognix_timeline",
        resource_id = str((event or {}).get("id") or payload.project_id or current_subject),
        severity = "notice",
        metadata = {
            "timelineVersion": plan.get("timelineVersion"),
            "eventClassifierVersion": plan.get("eventClassifierVersion"),
            "eventType": plan.get("event", {}).get("eventType"),
            "confidence": plan.get("classification", {}).get("confidence"),
            "sideEffects": side_effects,
        },
    )
    return {
        "timelineEventPlan": plan,
        "event": _row(event) if event else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_timeline.COGNIX_TIMELINE_VERSION,
    }


@router.get("/timeline/events")
async def timeline_events(
    project_id: str | None = None,
    event_type: str | None = None,
    query: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "events": _rows(
            cognix_db.list_timeline_events(
                current_subject,
                project_id = project_id,
                event_type = event_type,
                query = query,
            )
        ),
        "sideEffects": {
            "timelineWrite": False,
            "uiMutation": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


@router.get("/simulations/blueprint")
async def simulation_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_simulation.build_simulation_blueprint()
    return {
        "username": current_subject,
        "simulationBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_simulation.COGNIX_SIMULATION_ENGINE_VERSION,
    }


@router.post("/simulations/runs")
async def create_simulation_run(
    payload: SimulationRunRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_simulation.build_simulation_plan(
        username = current_subject,
        simulation_type = payload.simulation_type,
        user_count = payload.user_count,
        scenario = payload.scenario,
        duration_minutes = payload.duration_minutes,
        constraints = payload.constraints,
        project_id = payload.project_id,
        project_type = payload.project_type,
    )
    run = (
        cognix_db.create_simulation_run(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_run
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "simulationRunWrite": run is not None,
        "metricsWrite": run is not None,
        "queueEnqueue": False,
        "syntheticAgentRun": False,
        "loadExecution": False,
        "reportWrite": run is not None,
        "modelLoad": False,
        "generation": False,
        "toolExecution": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "simulation_run_planned",
        resource_type = "cognix_simulation",
        resource_id = str((run or {}).get("id") or payload.project_id or current_subject),
        severity = "warning" if plan.get("queuePlan", {}).get("queueRequired") else "notice",
        metadata = {
            "simulationEngineVersion": plan.get("simulationEngineVersion"),
            "simulationType": plan.get("scenario", {}).get("simulationType"),
            "userCount": plan.get("scenario", {}).get("userCount"),
            "durationMinutes": plan.get("scenario", {}).get("durationMinutes"),
            "queueRequired": plan.get("queuePlan", {}).get("queueRequired"),
            "highestMetricSeverity": plan.get("report", {}).get("summary", {}).get("highestMetricSeverity"),
            "sideEffects": side_effects,
        },
    )
    return {
        "simulationPlan": plan,
        "run": _row(run) if run else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_simulation.COGNIX_SIMULATION_ENGINE_VERSION,
    }


@router.get("/simulations/runs")
async def simulation_runs(
    project_id: str | None = None,
    simulation_type: str | None = None,
    query: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "runs": _rows(
            cognix_db.list_simulation_runs(
                current_subject,
                project_id = project_id,
                simulation_type = cognix_simulation.normalize_simulation_type(simulation_type) if simulation_type else None,
                query = query,
            )
        ),
        "sideEffects": {
            "simulationRunWrite": False,
            "metricsWrite": False,
            "queueEnqueue": False,
            "syntheticAgentRun": False,
            "loadExecution": False,
            "reportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


@router.get("/simulations/runs/{run_id}")
async def simulation_run(
    run_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    run = cognix_db.get_simulation_run(current_subject, run_id)
    if run is None:
        raise HTTPException(status_code = 404, detail = "Simulation run not found")
    return {
        "run": _row(run),
        "sideEffects": {
            "simulationRunWrite": False,
            "metricsWrite": False,
            "queueEnqueue": False,
            "syntheticAgentRun": False,
            "loadExecution": False,
            "reportWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


@router.get("/sandbox/blueprint")
async def sandbox_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_sandbox.build_sandbox_blueprint()
    return {
        "username": current_subject,
        "sandboxBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_sandbox.COGNIX_SANDBOX_MANAGER_VERSION,
    }


@router.post("/sandbox/plans")
async def create_sandbox_plan(
    payload: SandboxPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_sandbox.build_sandbox_plan(
        username = current_subject,
        target_type = payload.target_type,
        objective = payload.objective,
        change_summary = payload.change_summary,
        project_id = payload.project_id,
        project_type = payload.project_type,
        requested_checks = payload.requested_checks,
        duration_minutes = payload.duration_minutes,
    )
    run = (
        cognix_db.create_sandbox_run(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_run
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "sandboxWrite": run is not None,
        "sandboxRunWrite": run is not None,
        "sandboxReportWrite": run is not None,
        "isolatedRuntimeStart": False,
        "minimalConfigCopy": False,
        "experimentRun": False,
        "productionSecretRead": False,
        "productionWrite": False,
        "networkCall": False,
        "fileWrite": False,
        "rollbackExecute": False,
        "promotion": False,
        "modelLoad": False,
        "generation": False,
        "toolExecution": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "sandbox_plan_built",
        resource_type = "cognix_sandbox",
        resource_id = str((run or {}).get("sandbox_id") or payload.project_id or current_subject),
        severity = "warning" if plan.get("report", {}).get("riskLevel") in {"medium", "high"} else "notice",
        metadata = {
            "sandboxManagerVersion": plan.get("sandboxManagerVersion"),
            "targetType": plan.get("target", {}).get("type"),
            "riskLevel": plan.get("report", {}).get("riskLevel"),
            "requiresHumanApproval": plan.get("report", {}).get("summary", {}).get("requiresHumanApproval"),
            "productionSecretsAccessible": plan.get("isolation", {}).get("productionSecretsAccessible"),
            "queueRequired": plan.get("queuePlan", {}).get("queueRequired"),
            "sideEffects": side_effects,
        },
    )
    return {
        "sandboxPlan": plan,
        "run": _row(run) if run else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_sandbox.COGNIX_SANDBOX_MANAGER_VERSION,
    }


@router.get("/sandbox/runs")
async def sandbox_runs(
    project_id: str | None = None,
    target_type: str | None = None,
    query: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    return {
        "runs": _rows(
            cognix_db.list_sandbox_runs(
                current_subject,
                project_id = project_id,
                target_type = cognix_sandbox.normalize_sandbox_target_type(target_type) if target_type else None,
                query = query,
            )
        ),
        "sideEffects": {
            "sandboxWrite": False,
            "sandboxRunWrite": False,
            "sandboxReportWrite": False,
            "isolatedRuntimeStart": False,
            "minimalConfigCopy": False,
            "experimentRun": False,
            "productionSecretRead": False,
            "productionWrite": False,
            "networkCall": False,
            "fileWrite": False,
            "rollbackExecute": False,
            "promotion": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


@router.get("/sandbox/runs/{run_id}")
async def sandbox_run(
    run_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    run = cognix_db.get_sandbox_run(current_subject, run_id)
    if run is None:
        raise HTTPException(status_code = 404, detail = "Sandbox run not found")
    return {
        "run": _row(run),
        "sideEffects": {
            "sandboxWrite": False,
            "sandboxRunWrite": False,
            "sandboxReportWrite": False,
            "isolatedRuntimeStart": False,
            "minimalConfigCopy": False,
            "experimentRun": False,
            "productionSecretRead": False,
            "productionWrite": False,
            "networkCall": False,
            "fileWrite": False,
            "rollbackExecute": False,
            "promotion": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
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


@router.get("/evolution/blueprint")
async def evolution_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_evolution_engine.build_evolution_blueprint()
    return {
        "username": current_subject,
        "evolutionBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_evolution_engine.COGNIX_EVOLUTION_ENGINE_VERSION,
    }


@router.post("/evolution/items/plan")
async def evolution_item_plan(
    payload: EvolutionItemPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_evolution_engine.build_evolution_item_plan(
        technique_name = payload.technique_name,
        source_name = payload.source_name,
        category = payload.category,
        claimed_benefit = payload.claimed_benefit,
        evidence = payload.evidence,
        risk_tolerance = payload.risk_tolerance,
        project_id = payload.project_id,
    )
    item_record = (
        cognix_db.create_evolution_item(current_subject, item_plan = plan, project_id = payload.project_id)
        if payload.store_item
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "evolutionItemWrite": item_record is not None,
        "experimentWrite": False,
        "benchmarkResultWrite": False,
        "proposalWrite": False,
        "productionIntegration": False,
        "codeModification": False,
        "uxModification": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "evolution_item_planned",
        resource_type = "cognix_evolution_item",
        resource_id = str((item_record or {}).get("id") or plan.get("technique", {}).get("name") or "evolution-item"),
        severity = "warning" if plan.get("risk", {}).get("level") == "high" else "notice",
        metadata = {
            "evolutionEngineVersion": plan.get("evolutionEngineVersion"),
            "techniqueName": plan.get("technique", {}).get("name"),
            "category": plan.get("technique", {}).get("category"),
            "riskLevel": plan.get("risk", {}).get("level"),
            "status": plan.get("status"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "evolutionItemPlan": plan,
        "item": _row(item_record) if item_record else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_evolution_engine.COGNIX_EVOLUTION_ENGINE_VERSION,
    }


@router.get("/evolution/items")
async def evolution_items(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    items = cognix_db.list_evolution_items(current_subject, project_id = project_id, limit = limit)
    return {
        "username": current_subject,
        "items": _rows(items),
        "count": len(items),
        "sideEffects": {
            "evolutionItemWrite": False,
            "experimentWrite": False,
            "benchmarkResultWrite": False,
            "proposalWrite": False,
            "productionIntegration": False,
            "codeModification": False,
            "uxModification": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.post("/evolution/experiments/plan")
async def evolution_experiment_plan(
    payload: EvolutionExperimentPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    stored_item = cognix_db.get_evolution_item(current_subject, payload.item_id) if payload.item_id else None
    if payload.item_id and stored_item is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evolution item not found")
    item_plan = payload.item_plan or (stored_item or {}).get("item")
    if not isinstance(item_plan, dict) or not item_plan:
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = "Evolution item plan is required")
    plan = cognix_evolution_engine.build_evolution_experiment_plan(
        item_plan = item_plan,
        expected_gain_percent = payload.expected_gain_percent,
        benchmark_metric = payload.benchmark_metric,
        sandbox_target = payload.sandbox_target,
    )
    stored = (
        cognix_db.create_evolution_experiment(
            current_subject,
            item_id = payload.item_id or "dry-run-item",
            experiment_plan = plan,
        )
        if payload.store_experiment and payload.item_id
        else {"experiment": None, "benchmarkResults": [], "proposals": []}
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "evolutionItemWrite": False,
        "experimentWrite": bool(stored.get("experiment")),
        "benchmarkResultWrite": bool(stored.get("benchmarkResults")),
        "proposalWrite": bool(stored.get("proposals")),
        "productionIntegration": False,
        "codeModification": False,
        "uxModification": False,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "evolution_experiment_planned",
        resource_type = "cognix_evolution_experiment",
        resource_id = str((stored.get("experiment") or {}).get("id") or payload.item_id or "evolution-experiment"),
        severity = "warning" if plan.get("securityReview", {}).get("riskLevel") in {"medium", "high"} else "notice",
        metadata = {
            "evolutionEngineVersion": plan.get("evolutionEngineVersion"),
            "recommendation": plan.get("integrationProposal", {}).get("recommendation"),
            "riskLevel": plan.get("securityReview", {}).get("riskLevel"),
            "expectedGainPercent": plan.get("benchmarkPlan", {}).get("expectedGainPercent"),
            "humanApprovalRequired": True,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "evolutionExperimentPlan": plan,
        "experiment": _row(stored.get("experiment") or {}) if stored.get("experiment") else None,
        "benchmarkResults": _rows(stored.get("benchmarkResults") or []),
        "proposals": _rows(stored.get("proposals") or []),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_evolution_engine.COGNIX_EVOLUTION_ENGINE_VERSION,
    }


@router.get("/evolution/proposals")
async def evolution_proposals(
    item_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    proposals = cognix_db.list_integration_proposals(current_subject, item_id = item_id, limit = limit)
    return {
        "username": current_subject,
        "proposals": _rows(proposals),
        "count": len(proposals),
        "sideEffects": {
            "proposalWrite": False,
            "productionIntegration": False,
            "codeModification": False,
            "uxModification": False,
            "modelLoad": False,
            "generation": False,
        },
    }


@router.get("/research/assistant/blueprint")
async def research_assistant_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_research_watch.build_research_assistant_blueprint()
    return {
        "username": current_subject,
        "researchAssistantBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_research_watch.COGNIX_RESEARCH_ASSISTANT_VERSION,
    }


@router.post("/research/assistant/topics")
async def plan_research_topic(
    payload: ResearchTopicPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_research_watch.build_research_topic_plan(
        topic = payload.topic,
        sources = payload.sources,
        frequency = payload.frequency,
        output_format = payload.output_format,
        project_id = payload.project_id,
    )
    topic_record = (
        cognix_db.create_research_topic(current_subject, topic_plan = plan)
        if payload.store_topic
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "topicWrite": topic_record is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "research_topic_planned",
        resource_type = "cognix_research_topic",
        resource_id = str((topic_record or {}).get("id") or plan.get("topic", {}).get("topicKey") or "research-topic"),
        severity = "notice",
        metadata = {
            "researchAssistantVersion": plan.get("researchAssistantVersion"),
            "topicKey": plan.get("topic", {}).get("topicKey"),
            "sourceCount": plan.get("collectionPlan", {}).get("sourceCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "researchTopicPlan": plan,
        "topic": _row(topic_record) if topic_record else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_research_watch.COGNIX_RESEARCH_ASSISTANT_VERSION,
    }


@router.get("/research/assistant/topics")
async def research_topics(
    project_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    topics = cognix_db.list_research_topics(current_subject, project_id = project_id, limit = limit)
    return {"username": current_subject, "topics": _rows(topics), "count": len(topics)}


@router.post("/research/assistant/reports/plan")
async def plan_research_report(
    payload: ResearchReportPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    topic_record = cognix_db.get_research_topic(current_subject, payload.topic_id) if payload.topic_id else None
    if payload.topic_id and topic_record is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Research topic not found")
    topic_name = payload.topic or (topic_record or {}).get("topic") or "Veille CogniX"
    sources = payload.sources if payload.sources is not None else (topic_record or {}).get("sources")
    plan = cognix_research_watch.build_research_report_plan(
        topic = topic_name,
        items = payload.items,
        output_format = payload.output_format or (topic_record or {}).get("output_format"),
        sources = sources,
    )
    stored_items = (
        cognix_db.create_research_items(
            current_subject,
            topic_id = payload.topic_id,
            items = plan.get("items") or [],
        )
        if payload.store_items
        else []
    )
    report_record = (
        cognix_db.create_research_report(
            current_subject,
            topic_name,
            plan.get("report", {}).get("title") or f"Veille CogniX: {topic_name[:90]}",
            plan.get("report", {}).get("summary") or "",
            [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "publishedAt": item.get("publishedAt"),
                    "topicId": payload.topic_id,
                }
                for item in plan.get("items") or []
            ],
        )
        if payload.store_report
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "itemWrite": bool(stored_items),
        "reportWrite": report_record is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "research_report_plan_built",
        resource_type = "cognix_research_report",
        resource_id = str((report_record or {}).get("id") or payload.topic_id or "research-report"),
        severity = "notice",
        metadata = {
            "researchAssistantVersion": plan.get("researchAssistantVersion"),
            "topicId": payload.topic_id,
            "itemCount": len(plan.get("items") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "researchReportPlan": plan,
        "items": _rows(stored_items),
        "report": _row(report_record) if report_record else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_research_watch.COGNIX_RESEARCH_ASSISTANT_VERSION,
    }


@router.post("/context/pack")
async def build_context_pack(
    payload: ContextPackRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    warnings: list[str] = []
    project: dict[str, Any] | None = None
    project_dna: dict[str, Any] | None = None
    if payload.project_id:
        project = get_chat_project(
            payload.project_id,
            owner_username = current_subject,
            include_all = False,
        )
        if project is None or project.get("archived"):
            project = None
            warnings.append("Project context unavailable for this user.")
        else:
            project_dna = cognix_db.get_project_dna(current_subject, payload.project_id)
    compressed_context = cognix_db.get_latest_compressed_context(
        current_subject,
        project_id = payload.project_id if project is not None else None,
    )

    packet = cognix_context_manager.build_context_packet(
        current_subject = current_subject,
        user_memory = cognix_db.get_context_memory(current_subject),
        project = project,
        project_dna = project_dna,
        compressed_context = compressed_context,
        rag_retrieval_packet = payload.rag_retrieval_packet,
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
            "compressedContextId": (packet.get("compressedContext") or {}).get("id"),
            "hasConversationSummary": "conversation_summary" in packet.get("includedSectionIds", []),
            "hasRagPacket": bool(packet.get("ragPacket", {}).get("readyForInjection"))
            if packet.get("ragPacket")
            else False,
            "ragCitationCount": (packet.get("ragPacket") or {}).get("citationCount"),
            "ragSelectedChunkCount": (packet.get("ragPacket") or {}).get("selectedChunkCount"),
            "warnings": warnings,
            "sideEffects": packet.get("sideEffects", {}),
        },
    )
    packet["auditLogId"] = audit.get("id")
    return packet


@router.get("/context/graph/blueprint")
async def context_graph_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_context_graph.build_context_graph_blueprint()
    return {
        "username": current_subject,
        "contextGraphBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.post("/context/graph/build")
async def build_context_graph(
    payload: ContextGraphBuildRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project: dict[str, Any] | None = None
    warnings: list[str] = []
    messages = list(payload.messages or [])
    if payload.project_id:
        project = _require_owned_project(payload.project_id, current_subject)
        if payload.include_project_threads:
            threads = list_chat_threads(
                project_id = payload.project_id,
                include_archived = False,
                owner_username = current_subject,
                include_all = False,
            )[:20]
            thread_messages = list_chat_messages_for_threads([str(thread.get("id")) for thread in threads if thread.get("id")])
            messages.extend(thread_messages[-120:])
    project_name = payload.project_name
    project_type = payload.project_type
    if project:
        project_name = project_name or str(project.get("name") or project.get("title") or "")
        project_type = project_type or str(project.get("type") or project.get("project_type") or project.get("projectType") or "")
    graph = cognix_context_graph.build_context_graph_snapshot(
        username = current_subject,
        project_id = payload.project_id,
        project_name = project_name,
        project_type = project_type,
        messages = messages,
        documents = payload.documents,
        files = payload.files,
        decisions = payload.decisions,
        tasks = payload.tasks,
        models = payload.models,
        tools = payload.tools,
    )
    stored_snapshot = (
        cognix_db.create_context_graph_snapshot(
            current_subject,
            graph = graph,
            project_id = payload.project_id,
            title = project_name,
        )
        if payload.store_snapshot
        else None
    )
    side_effects = {
        **graph.get("sideEffects", {}),
        "snapshotWrite": bool(stored_snapshot),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "context_graph_built",
        resource_type = "cognix_context_graph_snapshot" if stored_snapshot else "cognix_context_graph_plan",
        resource_id = str((stored_snapshot or {}).get("id") or payload.project_id or "general"),
        severity = "notice",
        metadata = {
            "contextGraphVersion": graph.get("contextGraphVersion"),
            "projectId": payload.project_id,
            "nodeCount": graph.get("summary", {}).get("nodeCount"),
            "edgeCount": graph.get("summary", {}).get("edgeCount"),
            "storedSnapshot": bool(stored_snapshot),
            "warnings": warnings,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "contextGraph": graph,
        "snapshot": _row(stored_snapshot) if stored_snapshot else None,
        "auditLogId": audit.get("id"),
        "warnings": warnings,
        "sideEffects": side_effects,
    }


@router.get("/context/graph/snapshots")
async def context_graph_snapshots(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    snapshots = cognix_db.list_context_graph_snapshots(
        current_subject,
        project_id = project_id,
    )
    return {
        "username": current_subject,
        "snapshots": _rows(snapshots),
        "sideEffects": {
            "snapshotWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


@router.get("/library")
async def my_library(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    items = _rows(cognix_db.list_library_items(current_subject))
    return {
        "items": items,
        "summary": cognix_library.summarize_library(items),
        "blueprint": cognix_library.build_library_blueprint(),
    }


@router.get("/library/blueprint")
async def library_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_library.build_library_blueprint()
    return {
        "username": current_subject,
        "blueprint": blueprint,
        "sideEffects": blueprint["sideEffects"],
    }


@router.get("/library/search")
async def search_library(
    query: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    limit: int = 80,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    result = cognix_library.search_library_assets(
        items = _rows(cognix_db.list_library_items(current_subject)),
        query = query,
        kind = kind,
        source = source,
        limit = limit,
    )
    return {
        "username": current_subject,
        "librarySearch": result,
        "sideEffects": result["sideEffects"],
    }


@router.post("/library")
async def create_library_item(
    payload: LibraryItemRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    asset_plan = cognix_library.build_library_asset_plan(
        username = current_subject,
        kind = payload.kind,
        name = payload.name,
        source = payload.source,
        size_bytes = payload.size_bytes,
        uri = payload.uri,
        metadata = payload.metadata,
    )
    planned_asset = asset_plan["asset"]
    item = cognix_db.create_library_item(
        current_subject,
        kind = planned_asset["kind"],
        name = planned_asset["name"],
        source = planned_asset["source"],
        size_bytes = planned_asset["sizeBytes"],
        uri = planned_asset["uri"],
        metadata = planned_asset["metadata"],
    )
    side_effects = {
        **asset_plan["sideEffects"],
        "assetWrite": True,
        "metadataWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "library_item_created",
        resource_type = "cognix_library_item",
        resource_id = str(item.get("id") or ""),
        severity = "notice",
        metadata = {
            "libraryVersion": asset_plan.get("libraryVersion"),
            "kind": planned_asset["kind"],
            "source": planned_asset["source"],
            "classification": asset_plan["classification"],
            "indexingPlan": asset_plan["indexingPlan"],
            "permissionScope": asset_plan["permissionPlan"]["scope"],
            "sideEffects": side_effects,
        },
    )
    return {
        "item": _row(item),
        "assetPlan": asset_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.get("/scheduled-tasks")
async def my_scheduled_tasks(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    tasks = _rows(cognix_db.list_scheduled_tasks(current_subject))
    runs = _rows(cognix_db.list_scheduled_task_runs(current_subject))
    return {
        "tasks": tasks,
        "runs": runs,
        "blueprint": cognix_scheduled.build_scheduled_blueprint(),
    }


@router.get("/scheduled-tasks/blueprint")
async def scheduled_tasks_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_scheduled.build_scheduled_blueprint()
    return {
        "username": current_subject,
        "blueprint": blueprint,
        "sideEffects": blueprint["sideEffects"],
    }


@router.post("/scheduled-tasks/plan")
async def plan_scheduled_task(
    payload: ScheduledTaskCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = _build_scheduled_task_plan(
        current_subject,
        title = payload.title,
        prompt = payload.prompt,
        schedule_text = payload.schedule_text,
    )
    return {
        "username": current_subject,
        "scheduledTaskPlan": plan,
        "sideEffects": plan["sideEffects"],
    }


@router.post("/scheduled-tasks")
async def create_scheduled_task(
    payload: ScheduledTaskCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = _build_scheduled_task_plan(
        current_subject,
        title = payload.title,
        prompt = payload.prompt,
        schedule_text = payload.schedule_text,
    )
    task = cognix_db.create_scheduled_task(
        current_subject,
        plan["title"],
        plan["prompt"],
        plan["scheduleText"],
    )
    stored_plan = _build_scheduled_task_plan(
        current_subject,
        title = str(task.get("title") or payload.title),
        prompt = str(task.get("prompt") or payload.prompt),
        schedule_text = str(task.get("schedule_text") or payload.schedule_text),
        existing_task = task,
    )
    side_effects = {
        **stored_plan["sideEffects"],
        "taskWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "scheduled_task_created",
        resource_type = "cognix_scheduled_task",
        resource_id = str(task.get("id") or ""),
        severity = "warning" if stored_plan["permissionPlan"]["missingPermissions"] else "notice",
        metadata = {
            "scheduledVersion": stored_plan.get("scheduledVersion"),
            "actionType": stored_plan["action"]["actionType"],
            "riskLevel": stored_plan["action"]["riskLevel"],
            "missingPermissions": stored_plan["permissionPlan"]["missingPermissions"],
            "queuePlan": stored_plan["queuePlan"],
            "sideEffects": side_effects,
        },
    )
    return {
        "task": _row(task),
        "scheduledTaskPlan": stored_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


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
    side_effects = {
        **cognix_scheduled.build_scheduled_blueprint()["sideEffects"],
        "taskWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "scheduled_task_status_updated",
        resource_type = "cognix_scheduled_task",
        resource_id = task_id,
        severity = "notice",
        metadata = {
            "status": payload.status,
            "sideEffects": side_effects,
        },
    )
    return {"task": _row(task), "auditLogId": audit.get("id"), "sideEffects": side_effects}


@router.get("/scheduled-tasks/{task_id}/run-plan")
async def scheduled_task_run_plan(
    task_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    task = cognix_db.get_scheduled_task(current_subject, task_id)
    if not task:
        raise HTTPException(status_code = 404, detail = "Scheduled task not found")
    plan = _build_scheduled_task_plan(
        current_subject,
        title = str(task.get("title") or ""),
        prompt = str(task.get("prompt") or ""),
        schedule_text = str(task.get("schedule_text") or ""),
        existing_task = task,
    )
    return {
        "username": current_subject,
        "task": _row(task),
        "scheduledTaskPlan": plan,
        "sideEffects": plan["sideEffects"],
    }


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
    plan = _build_scheduled_task_plan(
        current_subject,
        title = str(task.get("title") or ""),
        prompt = str(task.get("prompt") or ""),
        schedule_text = str(task.get("schedule_text") or ""),
        existing_task = task,
    )
    if plan["permissionPlan"]["missingPermissions"]:
        run = cognix_db.create_scheduled_task_run(
            current_subject,
            task_id,
            plan["action"]["actionType"],
            "Execution bloquee: permissions manquantes "
            + ", ".join(plan["permissionPlan"]["missingPermissions"]),
            status = "failed",
        )
        side_effects = {
            **plan["sideEffects"],
            "taskRunWrite": True,
            "auditWrite": True,
        }
        audit = cognix_db.create_audit_log(
            username = current_subject,
            actor_username = current_subject,
            action = "scheduled_task_run_blocked",
            resource_type = "cognix_scheduled_task",
            resource_id = task_id,
            severity = "warning",
            metadata = {
                "scheduledVersion": plan.get("scheduledVersion"),
                "actionType": plan["action"]["actionType"],
                "missingPermissions": plan["permissionPlan"]["missingPermissions"],
                "sideEffects": side_effects,
            },
        )
        return {
            "run": _row(run),
            "scheduledTaskPlan": plan,
            "auditLogId": audit.get("id"),
            "sideEffects": side_effects,
        }
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
    side_effects = {
        **plan["sideEffects"],
        "taskRunWrite": True,
        "auditWrite": True,
        "networkCall": bool(plan["action"]["networkRequired"]),
        "libraryWrite": plan["action"]["outputType"] == "library_item",
        "newsWrite": plan["action"]["outputType"] == "news",
        "researchWrite": plan["action"]["outputType"] == "research_report",
        "agentRunWrite": plan["action"]["outputType"] == "agent_run",
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "scheduled_task_run_completed" if run.get("status") == "complete" else "scheduled_task_run_failed",
        resource_type = "cognix_scheduled_task",
        resource_id = task_id,
        severity = "notice" if run.get("status") == "complete" else "warning",
        metadata = {
            "scheduledVersion": plan.get("scheduledVersion"),
            "actionType": plan["action"]["actionType"],
            "runStatus": run.get("status"),
            "artifactType": run.get("artifact_type"),
            "artifactId": run.get("artifact_id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "run": _row(run),
        "scheduledTaskPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.get("/apps")
async def my_apps(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    connections = _rows(cognix_db.list_app_connections(current_subject))
    return {
        "catalog": APP_CATALOG,
        "connections": connections,
        "appRegistry": cognix_apps.build_app_registry(
            catalog = APP_CATALOG,
            connections = connections,
        ),
        "blueprint": cognix_apps.build_apps_blueprint(),
    }


@router.get("/apps/blueprint")
async def apps_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_apps.build_apps_blueprint()
    return {
        "username": current_subject,
        "blueprint": blueprint,
        "sideEffects": blueprint["sideEffects"],
    }


@router.get("/apps/registry")
async def apps_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    registry = cognix_apps.build_app_registry(
        catalog = APP_CATALOG,
        connections = _rows(cognix_db.list_app_connections(current_subject)),
    )
    return {
        "username": current_subject,
        "appRegistry": registry,
        "sideEffects": registry["sideEffects"],
    }


@router.post("/apps/plan")
async def plan_app_connection(
    payload: AppConnectionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_apps.build_app_connection_plan(
        app_id = payload.app_id,
        requested_status = payload.status,
        catalog = APP_CATALOG,
        granted_permissions = _granted_permission_keys(current_subject),
        admin = auth_storage.is_admin(current_subject),
    )
    return {
        "username": current_subject,
        "appConnectionPlan": plan,
        "sideEffects": plan["sideEffects"],
    }


@router.post("/apps/connections")
async def set_app_connection(
    payload: AppConnectionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_apps.build_app_connection_plan(
        app_id = payload.app_id,
        requested_status = payload.status,
        catalog = APP_CATALOG,
        granted_permissions = _granted_permission_keys(current_subject),
        admin = auth_storage.is_admin(current_subject),
    )
    if not plan["allowed"]:
        side_effects = {
            **plan["sideEffects"],
            "auditWrite": True,
        }
        audit = cognix_db.create_audit_log(
            username = current_subject,
            actor_username = current_subject,
            action = "app_connection_blocked",
            resource_type = "cognix_app",
            resource_id = payload.app_id,
            severity = "warning",
            metadata = {
                "appsVersion": plan.get("appsVersion"),
                "status": plan.get("status"),
                "riskLevel": plan.get("securityReview", {}).get("riskLevel"),
                "missingRequiredPermissions": plan.get("securityReview", {}).get("missingRequiredPermissions", []),
                "sideEffects": side_effects,
            },
        )
        raise HTTPException(
            status_code = 403,
            detail = {
                "message": "Missing app permissions",
                "missingPermissions": plan.get("securityReview", {}).get("missingRequiredPermissions", []),
                "auditLogId": audit.get("id"),
            },
        )
    app = plan["app"] or {}
    app_name = app.get("name") or payload.app_name
    try:
        connection = cognix_db.set_app_connection(
            current_subject,
            str(app.get("id") or payload.app_id),
            str(app_name),
            payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **plan["sideEffects"],
        "connectionWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "app_connection_updated",
        resource_type = "cognix_app",
        resource_id = str(app.get("id") or payload.app_id),
        severity = "warning" if plan.get("securityReview", {}).get("riskLevel") == "high" else "notice",
        metadata = {
            "appsVersion": plan.get("appsVersion"),
            "requestedStatus": payload.status,
            "riskLevel": plan.get("securityReview", {}).get("riskLevel"),
            "permissionScan": plan.get("permissionScan"),
            "runtimeAdapter": plan.get("connectionPlan", {}).get("runtimeAdapter"),
            "sideEffects": side_effects,
        },
    )
    return {
        "connection": _row(connection),
        "appConnectionPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


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


@router.get("/projects/{project_id}/dna/blueprint")
async def project_dna_blueprint(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    blueprint = cognix_project_dna.build_project_dna_blueprint()
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectDnaBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_project_dna.COGNIX_PROJECT_DNA_SERVICE_VERSION,
    }


@router.get("/projects/{project_id}/dna")
async def get_project_dna(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    dna = cognix_db.get_project_dna(current_subject, project_id)
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectDna": _row(dna) if dna else None,
    }


@router.put("/projects/{project_id}/dna")
async def upsert_project_dna(
    project_id: str,
    payload: ProjectDNARequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project = _require_owned_project(project_id, current_subject)
    plan = cognix_project_dna.build_project_dna_plan(
        username = current_subject,
        project_id = project_id,
        project = project,
        objective = payload.objective,
        context = payload.context,
        response_style = payload.response_style,
        preferred_models = payload.preferred_models,
        allowed_tools = payload.allowed_tools,
        constraints = payload.constraints,
        decisions = payload.decisions,
    )
    stored_dna = (
        cognix_db.upsert_project_dna(
            current_subject,
            project_id,
            plan = plan,
        )
        if payload.store_dna
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "projectDnaWrite": stored_dna is not None,
        "constraintWrite": stored_dna is not None,
        "decisionWrite": stored_dna is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_dna_upserted",
        resource_type = "cognix_project_dna",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "projectDnaServiceVersion": plan.get("projectDnaServiceVersion"),
            "profileBuilderVersion": plan.get("profileBuilderVersion"),
            "contextInjectorVersion": plan.get("contextInjectorVersion"),
            "status": plan.get("status"),
            "readySectionIds": plan.get("profile", {}).get("completion", {}).get("readySectionIds", []),
            "dnaHash": plan.get("profile", {}).get("dnaHash"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "project": _row(project),
        "projectDnaPlan": plan,
        "projectDna": _row(stored_dna) if stored_dna else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_project_dna.COGNIX_PROJECT_DNA_SERVICE_VERSION,
    }


@router.post("/projects/{project_id}/dna/injection-plan")
async def project_dna_injection_plan(
    project_id: str,
    payload: ProjectDNARequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project = _require_owned_project(project_id, current_subject)
    stored_dna = cognix_db.get_project_dna(current_subject, project_id)
    if stored_dna and not any(
        [
            payload.objective,
            payload.context,
            payload.response_style,
            payload.preferred_models,
            payload.allowed_tools,
            payload.constraints,
            payload.decisions,
        ]
    ):
        plan = stored_dna.get("dna") if isinstance(stored_dna.get("dna"), dict) else {}
    else:
        plan = cognix_project_dna.build_project_dna_plan(
            username = current_subject,
            project_id = project_id,
            project = project,
            objective = payload.objective,
            context = payload.context,
            response_style = payload.response_style,
            preferred_models = payload.preferred_models,
            allowed_tools = payload.allowed_tools,
            constraints = payload.constraints,
            decisions = payload.decisions,
        )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_dna_injection_plan_built",
        resource_type = "cognix_project_dna",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "projectDnaServiceVersion": plan.get("projectDnaServiceVersion"),
            "status": plan.get("status"),
            "includedSectionIds": plan.get("contextInjectionPlan", {}).get("includedSectionIds", []),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "project": _row(project),
        "projectDnaPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_project_dna.COGNIX_PROJECT_DNA_SERVICE_VERSION,
    }


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
    return {
        "reports": _rows(cognix_db.list_pulse_reports(current_subject)),
        "blueprint": cognix_pulse.build_pulse_blueprint(),
    }


@router.get("/pulse/blueprint")
async def pulse_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_pulse.build_pulse_blueprint()
    return {
        "username": current_subject,
        "blueprint": blueprint,
        "sideEffects": blueprint["sideEffects"],
    }


@router.get("/pulse/preview")
async def preview_pulse(
    hours: int = 24,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = _build_pulse_plan(current_subject, hours = hours)
    return {
        "username": current_subject,
        "pulsePlan": plan,
        "sideEffects": plan["sideEffects"],
    }


@router.post("/pulse/generate")
async def generate_pulse(
    hours: int = 24,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = _build_pulse_plan(current_subject, hours = hours)
    report_payload = plan["reportPayload"]
    report = cognix_db.create_pulse_report(
        current_subject,
        report_payload["title"],
        report_payload["summary"],
        report_payload["topics"],
        report_payload["sourceThreadIds"],
    )
    side_effects = {
        **plan["sideEffects"],
        "pulseReportWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "pulse_report_generated",
        resource_type = "cognix_pulse",
        resource_id = str(report.get("id") or ""),
        severity = "notice" if plan["summary"]["criticalCount"] == 0 else "warning",
        metadata = {
            "pulseVersion": plan.get("pulseVersion"),
            "eventCount": plan["summary"]["eventCount"],
            "criticalCount": plan["summary"]["criticalCount"],
            "sourceCounts": plan["summary"]["sourceCounts"],
            "sideEffects": side_effects,
        },
    )
    return {
        "report": _row(report),
        "pulsePlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.get("/images")
async def my_images(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    images = _rows(cognix_db.list_image_history(current_subject))
    return {
        "images": images,
        "summary": cognix_images.summarize_image_history(images),
        "blueprint": cognix_images.build_images_blueprint(),
    }


@router.get("/images/blueprint")
async def images_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_images.build_images_blueprint()
    return {
        "username": current_subject,
        "blueprint": blueprint,
        "sideEffects": blueprint["sideEffects"],
    }


@router.post("/images/plan")
async def plan_image(
    payload: ImageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_images.build_image_plan(
        username = current_subject,
        prompt = payload.prompt,
        model = payload.model,
        mode = payload.mode,
        project_id = payload.project_id,
        source_image_id = payload.source_image_id,
        variant_count = payload.variant_count,
        granted_permissions = _granted_permission_keys(current_subject),
        admin = auth_storage.is_admin(current_subject),
    )
    return {
        "username": current_subject,
        "imagePlan": plan,
        "sideEffects": plan["sideEffects"],
    }


@router.post("/images")
async def create_image(
    payload: ImageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_images.build_image_plan(
        username = current_subject,
        prompt = payload.prompt,
        model = payload.model,
        mode = payload.mode,
        project_id = payload.project_id,
        source_image_id = payload.source_image_id,
        variant_count = payload.variant_count,
        granted_permissions = _granted_permission_keys(current_subject),
        admin = auth_storage.is_admin(current_subject),
    )
    if plan["permissionPlan"]["missingPermissions"]:
        raise HTTPException(
            status_code = 403,
            detail = "Missing image permissions: " + ", ".join(plan["permissionPlan"]["missingPermissions"]),
        )
    image = cognix_db.create_image_request(
        current_subject,
        plan["prompt"],
        plan["modelPlan"]["selectedModel"],
    )
    asset = plan["libraryAsset"]
    metadata = {
        **asset["metadata"],
        "imageRequestId": image.get("id"),
        "status": image.get("status"),
    }
    library_item = cognix_db.create_library_item(
        current_subject,
        kind = asset["kind"],
        name = asset["name"],
        source = asset["source"],
        metadata = metadata,
    )
    side_effects = {
        **plan["sideEffects"],
        "imageRequestWrite": True,
        "libraryWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "image_request_created",
        resource_type = "cognix_image",
        resource_id = str(image.get("id") or ""),
        severity = "warning" if plan["safety"]["status"] == "needs_review" else "notice",
        metadata = {
            "imagesVersion": plan.get("imagesVersion"),
            "actionType": plan["action"]["actionType"],
            "selectedModel": plan["modelPlan"]["selectedModel"],
            "variantCount": plan["variantPlan"]["count"],
            "safetyStatus": plan["safety"]["status"],
            "libraryItemId": library_item.get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "image": _row(image),
        "libraryItem": _row(library_item),
        "imagePlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.get("/admin/users/blueprint")
async def admin_users_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_users.build_admin_users_blueprint()
    return {
        "username": current_subject,
        "adminUsersBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_users.COGNIX_ADMIN_USER_SERVICE_VERSION,
    }


@router.get("/admin/users")
async def admin_users(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_user_bundle()
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_users_directory_viewed",
        resource_type = "cognix_admin_users",
        resource_id = "directory",
        severity = "notice",
        metadata = {
            "adminUserServiceVersion": bundle["directory"].get("adminUserServiceVersion"),
            "userCount": bundle["directory"].get("summary", {}).get("userCount"),
            "sideEffects": {**bundle["directory"].get("sideEffects", {}), "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "directory": bundle["directory"],
        "auditLogId": audit.get("id"),
        "sideEffects": {**bundle["directory"].get("sideEffects", {}), "auditWrite": True},
        "plannerVersion": cognix_admin_users.COGNIX_ADMIN_USER_SERVICE_VERSION,
    }


@router.get("/admin/users/{username}")
async def admin_user_detail(
    username: str,
    reason: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_user_bundle()
    detail_preview = cognix_admin_users.build_admin_user_detail(
        username,
        bundle["directory"],
        cognix_db.list_admin_user_views(username, limit = 50),
    )
    if not detail_preview.get("found"):
        raise HTTPException(status_code = 404, detail = "User not found")
    view = cognix_db.record_admin_user_view(
        target_username = username,
        viewed_by = current_subject,
        reason = reason or "admin_user_detail",
    )
    cognix_db.create_user_activity_event(
        username,
        event_type = "admin_user_profile_viewed",
        resource_type = "cognix_admin_user",
        resource_id = username,
        metadata = {"viewedBy": current_subject, "viewId": view.get("id")},
    )
    detail = cognix_admin_users.build_admin_user_detail(
        username,
        _build_admin_user_bundle()["directory"],
        cognix_db.list_admin_user_views(username, limit = 50),
    )
    side_effects = {
        **detail.get("sideEffects", {}),
        "adminViewLogWrite": True,
        "activityEventWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_user_detail_viewed",
        resource_type = "cognix_admin_user",
        resource_id = username,
        severity = "notice",
        metadata = {
            "adminUserServiceVersion": detail.get("adminUserServiceVersion"),
            "viewId": view.get("id"),
            "reason": reason or "admin_user_detail",
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "userDetail": detail,
        "adminView": _row(view),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_users.COGNIX_ADMIN_USER_SERVICE_VERSION,
    }


@router.get("/admin/users/{username}/limits")
async def admin_user_limits(
    username: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if auth_storage.get_user_profile(username) is None:
        raise HTTPException(status_code = 404, detail = "User not found")
    bundle = _build_admin_user_bundle()
    detail = cognix_admin_users.build_admin_user_detail(
        username,
        bundle["directory"],
        cognix_db.list_admin_user_views(username, limit = 50),
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "limits": detail.get("user", {}).get("limits", {}),
        "sideEffects": cognix_admin_users.build_admin_users_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_users.COGNIX_LIMIT_SERVICE_VERSION,
    }


@router.get("/admin/limits/blueprint")
async def admin_limits_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_limits.build_limits_blueprint()
    return {
        "username": current_subject,
        "limitsBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/admin/limits")
async def admin_limits(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_limits_bundle()
    return {
        "username": current_subject,
        "quotaMatrix": bundle["matrix"],
        "userQuotas": _rows(bundle["userQuotas"]),
        "roleQuotas": _rows(bundle["roleQuotas"]),
        "quotaOverrides": _rows(bundle["quotaOverrides"]),
        "quotaUsage": _rows(bundle["quotaUsage"]),
        "legacyLimits": _rows(bundle["legacyLimits"]),
        "sideEffects": bundle["matrix"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_limits.COGNIX_LIMIT_SERVICE_VERSION,
    }


@router.put("/admin/limits/users/{username}/{quota_key}")
async def admin_update_user_quota(
    username: str,
    quota_key: str,
    payload: AdminQuotaRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if auth_storage.get_user_profile(username) is None:
        raise HTTPException(status_code = 404, detail = "User not found")
    try:
        quota = cognix_db.upsert_user_quota(
            username,
            quota_key = quota_key,
            quota_value = payload.quota_value,
            unit = payload.unit,
            period = payload.period,
            status = payload.status,
            updated_by = current_subject,
        )
        legacy_limit = cognix_db.upsert_user_limit(
            username,
            limit_key = quota_key,
            limit_value = payload.quota_value,
            unit = payload.unit,
            scope = "user",
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **cognix_admin_limits.build_limits_blueprint()["sideEffects"],
        "userQuotaWrite": True,
        "legacyLimitWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_user_quota_updated",
        resource_type = "cognix_user_quota",
        resource_id = str(quota.get("quota_key") or quota_key),
        severity = "notice",
        metadata = {
            "limitServiceVersion": cognix_admin_limits.COGNIX_LIMIT_SERVICE_VERSION,
            "quotaManagerVersion": cognix_admin_limits.COGNIX_QUOTA_MANAGER_VERSION,
            "quotaKey": quota.get("quota_key"),
            "quotaValue": quota.get("quota_value"),
            "unit": quota.get("unit"),
            "period": quota.get("period"),
            "reason": payload.reason,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "quota": _row(quota),
        "legacyLimit": _row(legacy_limit),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_limits.COGNIX_QUOTA_MANAGER_VERSION,
    }


@router.delete("/admin/limits/users/{username}/{quota_key}")
async def admin_reset_user_quota(
    username: str,
    quota_key: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if auth_storage.get_user_profile(username) is None:
        raise HTTPException(status_code = 404, detail = "User not found")
    try:
        quota_deleted = cognix_db.delete_user_quota(username, quota_key)
        legacy_deleted = cognix_db.delete_user_limit(username, quota_key)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **cognix_admin_limits.build_limits_blueprint()["sideEffects"],
        "userQuotaWrite": quota_deleted,
        "legacyLimitWrite": legacy_deleted,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_user_quota_reset",
        resource_type = "cognix_user_quota",
        resource_id = quota_key,
        severity = "notice",
        metadata = {
            "quotaDeleted": quota_deleted,
            "legacyDeleted": legacy_deleted,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "quotaKey": quota_key,
        "quotaDeleted": quota_deleted,
        "legacyDeleted": legacy_deleted,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_limits.COGNIX_QUOTA_MANAGER_VERSION,
    }


@router.put("/admin/limits/roles/{role_key}/{quota_key}")
async def admin_update_role_quota(
    role_key: str,
    quota_key: str,
    payload: AdminQuotaRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        quota = cognix_db.upsert_role_quota(
            role_key,
            quota_key = quota_key,
            quota_value = payload.quota_value,
            unit = payload.unit,
            period = payload.period,
            status = payload.status,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **cognix_admin_limits.build_limits_blueprint()["sideEffects"],
        "roleQuotaWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_role_quota_updated",
        resource_type = "cognix_role_quota",
        resource_id = str(quota.get("quota_key") or quota_key),
        severity = "notice",
        metadata = {
            "roleKey": quota.get("role_key"),
            "quotaKey": quota.get("quota_key"),
            "quotaValue": quota.get("quota_value"),
            "reason": payload.reason,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "roleKey": role_key,
        "quota": _row(quota),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_limits.COGNIX_QUOTA_MANAGER_VERSION,
    }


@router.post("/admin/limits/usage")
async def admin_record_quota_usage(
    payload: AdminQuotaUsageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if not payload.username:
        raise HTTPException(status_code = 400, detail = "Username is required")
    return await admin_record_user_quota_usage(
        payload.username,
        payload,
        current_subject = current_subject,
    )


@router.post("/admin/limits/users/{username}/usage")
async def admin_record_user_quota_usage(
    username: str,
    payload: AdminQuotaUsageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if auth_storage.get_user_profile(username) is None:
        raise HTTPException(status_code = 404, detail = "User not found")
    try:
        usage = cognix_db.record_quota_usage(
            username,
            quota_key = payload.quota_key,
            used_value = payload.used_value,
            unit = payload.unit,
            period_key = payload.period_key,
            metadata = payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **cognix_admin_limits.build_limits_blueprint()["sideEffects"],
        "quotaUsageWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_quota_usage_recorded",
        resource_type = "cognix_quota_usage",
        resource_id = str(usage.get("quota_key") or payload.quota_key),
        severity = "notice",
        metadata = {
            "quotaKey": usage.get("quota_key"),
            "usedValue": usage.get("used_value"),
            "periodKey": usage.get("period_key"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "usage": _row(usage),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_limits.COGNIX_QUOTA_MANAGER_VERSION,
    }


@router.post("/admin/limits/overrides")
async def admin_create_quota_override(
    payload: AdminQuotaOverrideRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        override = cognix_db.create_quota_override(
            target_type = payload.target_type,
            target_id = payload.target_id,
            quota_key = payload.quota_key,
            quota_value = payload.quota_value,
            unit = payload.unit,
            period = payload.period,
            reason = payload.reason,
            status = payload.status,
            expires_at = payload.expires_at,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **cognix_admin_limits.build_limits_blueprint()["sideEffects"],
        "quotaOverrideWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = payload.target_id if payload.target_type == "user" else None,
        actor_username = current_subject,
        action = "admin_quota_override_created",
        resource_type = "cognix_quota_override",
        resource_id = str(override.get("id") or ""),
        severity = "notice",
        metadata = {
            "targetType": override.get("target_type"),
            "targetId": override.get("target_id"),
            "quotaKey": override.get("quota_key"),
            "quotaValue": override.get("quota_value"),
            "reason": override.get("reason"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "override": _row(override),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_limits.COGNIX_QUOTA_MANAGER_VERSION,
    }


@router.post("/admin/limits/enforcement-plan")
async def admin_quota_enforcement_plan(
    payload: AdminQuotaEnforcementRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if auth_storage.get_user_profile(payload.username) is None:
        raise HTTPException(status_code = 404, detail = "User not found")
    bundle = _build_admin_limits_bundle()
    plan = cognix_admin_limits.build_usage_enforcement_plan(
        username = payload.username,
        quota_key = payload.quota_key,
        requested_units = payload.requested_units,
        quota_matrix = bundle["matrix"],
    )
    return {
        "username": current_subject,
        "enforcementPlan": plan,
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_admin_limits.COGNIX_USAGE_ENFORCER_VERSION,
    }


@router.put("/admin/users/{username}/limits/{limit_key}")
async def admin_update_user_limit(
    username: str,
    limit_key: str,
    payload: AdminUserLimitRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if auth_storage.get_user_profile(username) is None:
        raise HTTPException(status_code = 404, detail = "User not found")
    try:
        limit = cognix_db.upsert_user_limit(
            username,
            limit_key = limit_key,
            limit_value = payload.limit_value,
            unit = payload.unit,
            scope = payload.scope,
            updated_by = current_subject,
        )
        quota = cognix_db.upsert_user_quota(
            username,
            quota_key = limit_key,
            quota_value = payload.limit_value,
            unit = payload.unit,
            period = payload.period,
            status = payload.status,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    activity = cognix_db.create_user_activity_event(
        username,
        event_type = "admin_user_limit_updated",
        resource_type = "cognix_user_limit",
        resource_id = str(limit.get("limit_key") or limit_key),
        metadata = {
            "updatedBy": current_subject,
            "limitValue": limit.get("limit_value"),
            "unit": limit.get("unit"),
            "reason": payload.reason,
        },
    )
    side_effects = {
        **cognix_admin_users.build_admin_users_blueprint()["sideEffects"],
        "limitWrite": True,
        "userQuotaWrite": True,
        "activityEventWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_user_limit_updated",
        resource_type = "cognix_user_limit",
        resource_id = str(limit.get("limit_key") or limit_key),
        severity = "notice",
        metadata = {
            "limitServiceVersion": cognix_admin_users.COGNIX_LIMIT_SERVICE_VERSION,
            "limitKey": limit.get("limit_key"),
            "limitValue": limit.get("limit_value"),
            "unit": limit.get("unit"),
            "scope": limit.get("scope"),
            "quotaId": quota.get("id"),
            "quotaPeriod": quota.get("period"),
            "reason": payload.reason,
            "activityEventId": activity.get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "limit": _row(limit),
        "quota": _row(quota),
        "activityEvent": _row(activity),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_users.COGNIX_LIMIT_SERVICE_VERSION,
    }


@router.get("/admin/activity")
async def admin_activity(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_user_bundle()
    activity_bundle = _build_admin_activity_bundle(refresh_rollups = True)
    side_effects = {
        **cognix_admin_activity.build_activity_monitoring_blueprint()["sideEffects"],
        "userDailyWrite": True,
        "organizationDailyWrite": True,
    }
    return {
        "username": current_subject,
        "activityEvents": _rows(bundle["activityEvents"]),
        "activityDashboard": activity_bundle["rollups"],
        "userDaily": _rows(activity_bundle["persisted"]["userDaily"]),
        "organizationDaily": _rows(activity_bundle["persisted"]["organizationDaily"]),
        "directorySummary": bundle["directory"].get("summary", {}),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_activity.COGNIX_ACTIVITY_MONITORING_VERSION,
    }


@router.get("/admin/activity/blueprint")
async def admin_activity_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_activity.build_activity_monitoring_blueprint()
    return {
        "username": current_subject,
        "activityMonitoringBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.post("/admin/activity/aggregate")
async def admin_activity_aggregate(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    activity_bundle = _build_admin_activity_bundle(refresh_rollups = True)
    side_effects = {
        **activity_bundle["rollups"].get("sideEffects", {}),
        "userDailyWrite": True,
        "organizationDailyWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_activity_aggregated",
        resource_type = "cognix_activity_rollups",
        resource_id = None,
        severity = "notice",
        metadata = {
            "activityMonitoringVersion": cognix_admin_activity.COGNIX_ACTIVITY_MONITORING_VERSION,
            "activityAggregatorVersion": cognix_admin_activity.COGNIX_ACTIVITY_AGGREGATOR_VERSION,
            "userDailyRows": len(activity_bundle["persisted"]["userDaily"]),
            "organizationDailyRows": len(activity_bundle["persisted"]["organizationDaily"]),
            "summary": activity_bundle["rollups"].get("summary", {}),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "activityDashboard": activity_bundle["rollups"],
        "userDaily": _rows(activity_bundle["persisted"]["userDaily"]),
        "organizationDaily": _rows(activity_bundle["persisted"]["organizationDaily"]),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_activity.COGNIX_ACTIVITY_AGGREGATOR_VERSION,
    }


def _persist_usage_rollups(usage_dashboard: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rollups = usage_dashboard.get("rollups") if isinstance(usage_dashboard.get("rollups"), dict) else {}
    user_daily = [
        cognix_db.upsert_daily_user_token_usage(record)
        for record in rollups.get("dailyUserTokenUsage", [])
        if isinstance(record, dict)
    ]
    model_daily = [
        cognix_db.upsert_daily_model_usage(record)
        for record in rollups.get("dailyModelUsage", [])
        if isinstance(record, dict)
    ]
    organization_summary = [
        cognix_db.upsert_organization_usage_summary(record)
        for record in rollups.get("organizationUsageSummary", [])
        if isinstance(record, dict)
    ]
    return {
        "dailyUserTokenUsage": user_daily,
        "dailyModelUsage": model_daily,
        "organizationUsageSummary": organization_summary,
    }


@router.get("/admin/usage/blueprint")
async def admin_usage_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "username": current_subject,
        "usageBlueprint": cognix_admin_usage.build_usage_blueprint(),
    }


@router.get("/admin/usage")
async def admin_usage(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_user_bundle()
    return {
        "username": current_subject,
        "usageDashboard": bundle["usage"],
        "sideEffects": bundle["usage"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_usage.COGNIX_USAGE_DASHBOARD_VERSION,
    }


@router.post("/admin/usage/aggregate")
async def admin_usage_aggregate(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_user_bundle()
    persisted = _persist_usage_rollups(bundle["usage"])
    side_effects = {
        **bundle["usage"].get("sideEffects", {}),
        "rollupWrite": True,
        "databaseWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "admin_usage_rollups_aggregated",
        resource_type = "cognix_admin_usage",
        resource_id = "token_model_usage",
        severity = "notice",
        metadata = {
            "usageDashboardVersion": bundle["usage"].get("usageDashboardVersion"),
            "dailyUserRows": len(persisted["dailyUserTokenUsage"]),
            "dailyModelRows": len(persisted["dailyModelUsage"]),
            "organizationSummaryRows": len(persisted["organizationUsageSummary"]),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "usageDashboard": bundle["usage"],
        "persisted": {
            "dailyUserTokenUsage": _rows(persisted["dailyUserTokenUsage"]),
            "dailyModelUsage": _rows(persisted["dailyModelUsage"]),
            "organizationUsageSummary": _rows(persisted["organizationUsageSummary"]),
        },
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_usage.COGNIX_USAGE_DASHBOARD_VERSION,
    }


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
    audit_logs = cognix_db.list_audit_logs(limit = 500)
    threat_report = cognix_admin_security.build_security_threat_report(
        security_events = threats,
        audit_logs = audit_logs,
        bans = bans,
        reports = reports,
    )
    risk_scoring = cognix_admin_security.build_risk_scoring(
        security_events = threats,
        audit_logs = audit_logs,
        bans = bans,
        reports = reports,
    )
    system_health = cognix_admin_security.build_system_health(
        hardware = cognix_hardware.get_hardware_profile(),
        security_report = threat_report,
        risk_scoring = risk_scoring,
        audit_logs = audit_logs,
    )
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
            "riskEntities": risk_scoring["summary"]["entities"],
            "maxRiskScore": risk_scoring["summary"]["maxScore"],
            "systemHealth": system_health["overallStatus"],
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
        "threatReport": threat_report,
        "riskScoring": risk_scoring,
        "systemHealth": system_health,
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


@router.get("/admin/chats/blueprint")
async def admin_chats_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_chat.build_admin_chat_blueprint()
    return {
        "username": current_subject,
        "adminChatBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/admin/chats/policy")
async def admin_chat_policy(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    stored_policy = cognix_db.get_chat_access_policy()
    policy = cognix_admin_chat.normalize_chat_access_policy(stored_policy)
    return {
        "username": current_subject,
        "policy": policy,
        "storedPolicy": _row(stored_policy) if stored_policy else None,
        "sideEffects": cognix_admin_chat.build_admin_chat_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_chat.COGNIX_CHAT_ACCESS_POLICY_VERSION,
    }


@router.put("/admin/chats/policy")
async def admin_update_chat_policy(
    payload: AdminChatPolicyRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        policy = cognix_db.upsert_chat_access_policy(
            policy_scope = payload.policy_scope,
            scope_id = payload.scope_id,
            mode = payload.mode,
            admin_chat_access = payload.admin_chat_access,
            require_reason = payload.require_reason,
            retention_days = payload.retention_days,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    normalized_policy = cognix_admin_chat.normalize_chat_access_policy(policy)
    side_effects = {
        **cognix_admin_chat.build_admin_chat_blueprint()["sideEffects"],
        "policyWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_chat_policy_updated",
        resource_type = "cognix_chat_access_policy",
        resource_id = str(policy.get("id") or ""),
        severity = "notice",
        metadata = {
            "policyVersion": cognix_admin_chat.COGNIX_CHAT_ACCESS_POLICY_VERSION,
            "mode": normalized_policy["mode"],
            "contentVisible": normalized_policy["contentVisible"],
            "adminChatAccess": normalized_policy["adminChatAccess"],
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "policy": normalized_policy,
        "storedPolicy": _row(policy),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_chat.COGNIX_CHAT_ACCESS_POLICY_VERSION,
    }


@router.get("/admin/chats")
async def admin_chats(
    username: str | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
    risk_level: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_chat_bundle(refresh_metadata = True)
    directory = cognix_admin_chat.build_admin_chat_directory(
        threads = bundle["threads"],
        messages = bundle["messages"],
        projects = bundle["projects"],
        token_events = bundle["tokenEvents"],
        audit_metadata = bundle["auditMetadata"],
        policy = bundle["policy"],
        filters = {
            "username": username,
            "projectId": project_id,
            "modelId": model_id,
            "riskLevel": risk_level,
        },
    )
    side_effects = {
        **directory.get("sideEffects", {}),
        "auditMetadataWrite": True,
    }
    return {
        "username": current_subject,
        "directory": directory,
        "conversationAuditMetadata": _rows(bundle["auditMetadata"]),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_chat.COGNIX_ADMIN_CHAT_SERVICE_VERSION,
    }


@router.get("/admin/chats/{thread_id}")
async def admin_chat_detail(
    thread_id: str,
    reason: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_chat_bundle(refresh_metadata = True)
    thread = next((item for item in bundle["threads"] if str(item.get("id") or "") == thread_id), None)
    if thread is None:
        raise HTTPException(status_code = 404, detail = "Conversation not found")
    audit_metadata = cognix_db.get_conversation_audit_metadata(thread_id) or {}
    try:
        detail = cognix_admin_chat.build_admin_chat_detail(
            thread = thread,
            messages = bundle["messages"],
            policy = bundle["policy"],
            reason = reason,
            audit_metadata = audit_metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc

    content_visible = bool(detail.get("policy", {}).get("contentVisible"))
    access_mode = "content_visible" if content_visible else "metadata_only"
    target_username = str(detail.get("thread", {}).get("ownerUsername") or "")
    try:
        access_log = cognix_db.record_admin_chat_access(
            admin_username = current_subject,
            target_username = target_username,
            thread_id = thread_id,
            access_mode = access_mode,
            content_visible = content_visible,
            reason = str(detail.get("access", {}).get("reason") or reason or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **detail.get("sideEffects", {}),
        "adminAccessLogWrite": True,
        "auditMetadataWrite": True,
        "auditWrite": True,
        "contentRead": content_visible,
    }
    audit = cognix_db.create_audit_log(
        username = target_username,
        actor_username = current_subject,
        action = "admin_chat_detail_viewed",
        resource_type = "chat_thread",
        resource_id = thread_id,
        severity = "notice",
        metadata = {
            "adminChatServiceVersion": cognix_admin_chat.COGNIX_ADMIN_CHAT_SERVICE_VERSION,
            "policyMode": detail.get("policy", {}).get("mode"),
            "contentVisible": content_visible,
            "accessMode": access_mode,
            "accessLogId": access_log.get("id"),
            "reason": detail.get("access", {}).get("reason"),
            "messageCount": len(detail.get("messages") or []),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "detail": detail,
        "accessLog": _row(access_log),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_chat.COGNIX_CHAT_AUDIT_VIEWER_VERSION,
    }


@router.post("/admin/chats/{thread_id}/export-plan")
async def admin_chat_export_plan(
    thread_id: str,
    payload: AdminChatExportPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_chat_bundle(refresh_metadata = True)
    thread = next((item for item in bundle["threads"] if str(item.get("id") or "") == thread_id), None)
    if thread is None:
        raise HTTPException(status_code = 404, detail = "Conversation not found")
    try:
        plan = cognix_admin_chat.build_conversation_export_plan(
            thread = thread,
            messages = bundle["messages"],
            policy = bundle["policy"],
            reason = payload.reason,
            output_format = payload.output_format,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    side_effects = {
        **plan.get("sideEffects", {}),
        "auditMetadataWrite": True,
        "auditWrite": True,
        "exportWrite": False,
    }
    audit = cognix_db.create_audit_log(
        username = str(plan.get("targetUsername") or ""),
        actor_username = current_subject,
        action = "admin_chat_export_planned",
        resource_type = "chat_thread",
        resource_id = thread_id,
        severity = "notice",
        metadata = {
            "conversationExportVersion": cognix_admin_chat.COGNIX_CONVERSATION_EXPORT_VERSION,
            "outputFormat": plan.get("outputFormat"),
            "contentIncluded": plan.get("contentIncluded"),
            "dryRun": plan.get("dryRun"),
            "reason": plan.get("reason"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "exportPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_chat.COGNIX_CONVERSATION_EXPORT_VERSION,
    }


@router.get("/admin/approvals")
async def admin_approvals(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_approvals_bundle()
    return {
        "requests": _rows(bundle["requests"]),
        "decisions": _rows(bundle["decisions"]),
        "comments": _rows(bundle["comments"]),
        "approvalQueue": bundle["queue"],
        "sideEffects": bundle["queue"].get("sideEffects", {}),
        "approvalServiceVersion": cognix_admin_approvals.COGNIX_APPROVAL_SERVICE_VERSION,
    }


@router.get("/admin/approvals/blueprint")
async def admin_approvals_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "approvalsBlueprint": cognix_admin_approvals.build_approvals_blueprint(),
    }


@router.post("/admin/approvals/policy")
async def admin_approval_policy(
    payload: ApprovalPolicyRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "policy": cognix_admin_approvals.build_policy_decision(
            request_type = payload.request_type,
            requester_role = payload.requester_role,
            risk_level = payload.risk_level,
            has_permission = payload.has_permission,
        )
    }


@router.get("/admin/approvals/{request_id}")
async def admin_approval_detail(
    request_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    request = cognix_db.get_approval_request(request_id)
    if request is None:
        raise HTTPException(status_code = 404, detail = "Approval request not found")
    decisions = cognix_db.list_approval_decisions(request_id)
    comments = cognix_db.list_approval_comments(request_id)
    queue = cognix_admin_approvals.build_approval_queue(
        requests = [request],
        decisions = decisions,
        comments = comments,
    )
    return {
        "request": _row(request),
        "decisions": _rows(decisions),
        "comments": _rows(comments),
        "approvalQueueItem": queue["requests"][0] if queue["requests"] else None,
    }


@router.post("/admin/approvals/{request_id}/comments")
async def admin_add_approval_comment(
    request_id: str,
    payload: ApprovalCommentRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if cognix_db.get_approval_request(request_id) is None:
        raise HTTPException(status_code = 404, detail = "Approval request not found")
    try:
        comment = cognix_db.add_approval_comment(
            request_id,
            username = current_subject,
            comment = payload.comment,
            visibility = payload.visibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "approval_comment_added",
        resource_type = "cognix_approval_request",
        resource_id = request_id,
        severity = "notice",
        metadata = {
            "visibility": payload.visibility,
        },
    )
    return {
        "comment": _row(comment),
        "auditLogId": audit.get("id"),
        "sideEffects": {"commentWrite": True, "auditWrite": True},
    }


@router.patch("/admin/approvals/{request_id}")
async def admin_decide_approval(
    request_id: str,
    payload: ApprovalDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    current_request = cognix_db.get_approval_request(request_id)
    if current_request is None:
        raise HTTPException(status_code = 404, detail = "Approval request not found")
    policy_snapshot = payload.policy_snapshot or cognix_admin_approvals.build_policy_decision(
        request_type = str(current_request.get("request_type") or ""),
        requester_role = "user",
        risk_level = str(current_request.get("risk_level") or "medium"),
        has_permission = False,
    )
    try:
        request = cognix_db.set_approval_status(
            request_id,
            payload.status,
            decided_by = current_subject,
            admin_note = payload.admin_note,
            policy_snapshot = policy_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if request is None:
        raise HTTPException(status_code = 404, detail = "Approval request not found")
    audit = cognix_db.create_audit_log(
        username = str(request.get("username") or ""),
        actor_username = current_subject,
        action = "approval_decided",
        resource_type = "cognix_approval_request",
        resource_id = request_id,
        severity = "notice" if payload.status == "approved" else "warning",
        metadata = {
            "status": payload.status,
            "requestType": request.get("request_type"),
            "riskLevel": request.get("risk_level"),
            "policySnapshot": policy_snapshot,
        },
    )
    return {
        "request": _row(request),
        "decisions": _rows(cognix_db.list_approval_decisions(request_id)),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "decisionWrite": True,
            "legacyPermissionWrite": request.get("request_type") == cognix_db.DEVELOPER_MODE_PERMISSION,
            "auditWrite": True,
        },
    }


@router.get("/admin/permissions/blueprint")
async def admin_permissions_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "permissionsBlueprint": cognix_admin_permissions.build_permissions_blueprint(),
    }


@router.get("/admin/permissions/matrix")
async def admin_permissions_matrix(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_permissions_bundle()
    return {
        **bundle,
        "roles": _rows(bundle["roles"]),
        "permissionDefinitions": _rows(bundle["permissionDefinitions"]),
        "rolePermissions": _rows(bundle["rolePermissions"]),
        "userOverrides": _rows(bundle["userOverrides"]),
        "projectPermissions": _rows(bundle["projectPermissions"]),
        "legacyPermissions": _rows(bundle["legacyPermissions"]),
        "auditLogs": _rows(cognix_db.list_audit_logs(limit = 200)),
    }


@router.put("/admin/permissions/roles/{role_key}")
async def admin_upsert_role(
    role_key: str,
    payload: AdminRoleRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        role = cognix_db.upsert_role(
            role_key,
            display_name = payload.display_name,
            description = payload.description,
            status = payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = role.get("role_key") or role_key,
        actor_username = current_subject,
        action = "permission_role_upserted",
        resource_type = "cognix_role",
        resource_id = role.get("role_key") or role_key,
        severity = "notice",
        metadata = {
            "roleKey": role.get("role_key") or role_key,
            "status": role.get("status"),
        },
    )
    return {
        "role": _row(role),
        "auditLogId": audit.get("id"),
        "sideEffects": {"roleWrite": True, "auditWrite": True},
    }


@router.put("/admin/permissions/roles/{role_key}/{permission_key}")
async def admin_upsert_role_permission(
    role_key: str,
    permission_key: str,
    payload: AdminRolePermissionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        module_key = permission_key.split(":", 1)[0] if ":" in permission_key else "general"
        permission_definition = cognix_db.upsert_permission_definition(
            permission_key,
            module_key = module_key,
            display_name = permission_key,
            risk_level = "high" if payload.allowed else "medium",
        )
        role_permission = cognix_db.upsert_role_permission(
            role_key,
            permission_key,
            allowed = payload.allowed,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = role_key,
        actor_username = current_subject,
        action = "role_permission_updated",
        resource_type = "cognix_role_permission",
        resource_id = f"{role_key}:{permission_key}",
        severity = "notice",
        metadata = {
            "roleKey": role_key,
            "permissionKey": permission_key,
            "allowed": payload.allowed,
            "reason": payload.reason,
        },
    )
    return {
        "permissionDefinition": _row(permission_definition),
        "rolePermission": _row(role_permission),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "permissionCatalogWrite": True,
            "rolePermissionWrite": True,
            "auditWrite": True,
        },
    }


@router.put("/admin/permissions/users/{username}/{permission_key}/override")
async def admin_upsert_user_permission_override(
    username: str,
    permission_key: str,
    payload: AdminPermissionOverrideRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        module_key = permission_key.split(":", 1)[0] if ":" in permission_key else "general"
        permission_definition = cognix_db.upsert_permission_definition(
            permission_key,
            module_key = module_key,
            display_name = permission_key,
        )
        override = cognix_db.upsert_user_permission_override(
            username,
            permission_key,
            effect = payload.effect,
            reason = payload.reason or "",
            expires_at = payload.expires_at,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "user_permission_override_updated",
        resource_type = "cognix_user_permission_override",
        resource_id = f"{username}:{permission_key}",
        severity = "notice" if payload.effect == "allow" else "warning",
        metadata = {
            "permissionKey": permission_key,
            "effect": payload.effect,
            "reason": payload.reason,
            "expiresAt": payload.expires_at,
        },
    )
    return {
        "permissionDefinition": _row(permission_definition),
        "override": _row(override),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "permissionCatalogWrite": True,
            "userOverrideWrite": True,
            "auditWrite": True,
        },
    }


@router.delete("/admin/permissions/users/{username}/{permission_key}/override")
async def admin_delete_user_permission_override(
    username: str,
    permission_key: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        deleted = cognix_db.delete_user_permission_override(username, permission_key)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "user_permission_override_deleted",
        resource_type = "cognix_user_permission_override",
        resource_id = f"{username}:{permission_key}",
        severity = "notice" if deleted else "warning",
        metadata = {
            "permissionKey": permission_key,
            "deleted": deleted,
        },
    )
    return {
        "deleted": deleted,
        "auditLogId": audit.get("id"),
        "sideEffects": {"userOverrideWrite": True, "auditWrite": True},
    }


@router.put("/admin/permissions/projects/{project_id}")
async def admin_upsert_project_permission(
    project_id: str,
    payload: AdminProjectPermissionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        module_key = payload.permission_key.split(":", 1)[0] if ":" in payload.permission_key else "general"
        permission_definition = cognix_db.upsert_permission_definition(
            payload.permission_key,
            module_key = module_key,
            display_name = payload.permission_key,
        )
        project_permission = cognix_db.upsert_project_permission(
            project_id,
            subject_type = payload.subject_type,
            subject_id = payload.subject_id,
            permission_key = payload.permission_key,
            allowed = payload.allowed,
            updated_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    audit = cognix_db.create_audit_log(
        username = payload.subject_id,
        actor_username = current_subject,
        action = "project_permission_updated",
        resource_type = "cognix_project_permission",
        resource_id = f"{project_id}:{payload.subject_type}:{payload.subject_id}:{payload.permission_key}",
        severity = "notice",
        metadata = {
            "projectId": project_id,
            "subjectType": payload.subject_type,
            "subjectId": payload.subject_id,
            "permissionKey": payload.permission_key,
            "allowed": payload.allowed,
        },
    )
    return {
        "permissionDefinition": _row(permission_definition),
        "projectPermission": _row(project_permission),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "permissionCatalogWrite": True,
            "projectPermissionWrite": True,
            "auditWrite": True,
        },
    }


@router.post("/admin/permissions/decision")
async def admin_permission_decision(
    payload: AdminPermissionDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_permissions_bundle()
    decision = cognix_admin_permissions.build_permission_decision(
        username = payload.username,
        permission_key = payload.permission_key,
        project_id = payload.project_id,
        matrix = bundle["matrix"],
    )
    return {
        "decision": decision,
        "permissionEngineVersion": cognix_admin_permissions.COGNIX_PERMISSION_ENGINE_VERSION,
    }


@router.get("/admin/permissions/{username}")
async def admin_user_permissions(
    username: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_permissions_bundle()
    effective_user = next(
        (
            user
            for user in bundle["matrix"].get("users", [])
            if str(user.get("username") or "").casefold() == username.casefold()
        ),
        None,
    )
    return {
        "username": username,
        "permissions": _rows(cognix_db.list_user_permissions(username)),
        "overrides": _rows(cognix_db.list_user_permission_overrides(username)),
        "effectivePermissions": effective_user,
    }


@router.post("/admin/permissions/{username}")
async def admin_grant_permission(
    username: str,
    payload: AdminPermissionGrantRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        module_key = payload.permission_key.split(":", 1)[0] if ":" in payload.permission_key else "general"
        permission_definition = cognix_db.upsert_permission_definition(
            payload.permission_key,
            module_key = module_key,
            display_name = payload.permission_key,
        )
        permission = cognix_db.grant_user_permission(
            username,
            payload.permission_key,
            granted_by = current_subject,
            expires_at = payload.expires_at,
        )
        override = cognix_db.upsert_user_permission_override(
            username,
            payload.permission_key,
            effect = "allow",
            reason = "Legacy admin grant synchronized with native RBAC.",
            expires_at = payload.expires_at,
            updated_by = current_subject,
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
        "permissionDefinition": _row(permission_definition),
        "permission": _row(permission),
        "override": _row(override),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "permissionCatalogWrite": True,
            "legacyPermissionWrite": True,
            "userOverrideWrite": True,
            "auditWrite": True,
        },
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
        override = cognix_db.upsert_user_permission_override(
            username,
            permission_key,
            effect = "deny",
            reason = "Legacy admin revoke synchronized with native RBAC.",
            updated_by = current_subject,
        )
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
        "override": _row(override),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "legacyPermissionWrite": True,
            "userOverrideWrite": True,
            "auditWrite": True,
        },
    }


@router.get("/admin/banned/blueprint")
async def admin_banned_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "bannedBlueprint": cognix_admin_banned.build_banned_blueprint(),
    }


@router.get("/admin/banned")
async def admin_banned(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_banned_bundle()
    return {
        "bannedDashboard": bundle["dashboard"],
        "bans": _rows(bundle["bans"]),
        "reports": _rows(bundle["reports"]),
        "banReports": _rows(bundle["banReports"]),
        "evidenceLogs": _rows(bundle["evidenceLogs"]),
        "sideEffects": bundle["dashboard"].get("sideEffects", {}),
    }


@router.post("/admin/banned/{ban_id}/evidence")
async def admin_add_ban_evidence(
    ban_id: str,
    payload: BanEvidenceRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    if not any(str(item.get("id") or "") == ban_id for item in cognix_db.list_bans()):
        raise HTTPException(status_code = 404, detail = "Ban not found")
    evidence = cognix_db.create_ban_evidence_log(
        ban_id,
        source_type = payload.source_type,
        source_id = payload.source_id,
        excerpt = payload.excerpt,
        metadata = payload.metadata,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "ban_evidence_added",
        resource_type = "cognix_ban",
        resource_id = ban_id,
        severity = "notice",
        metadata = {
            "sourceType": payload.source_type,
            "sourceId": payload.source_id,
        },
    )
    return {
        "evidence": _row(evidence),
        "auditLogId": audit.get("id"),
        "sideEffects": {"evidenceWrite": True, "auditWrite": True},
    }


@router.post("/admin/banned/{ban_id}/report")
async def admin_generate_ban_report(
    ban_id: str,
    payload: BanReportRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_banned_bundle()
    row = next((item for item in bundle["dashboard"]["bannedUsers"] if item["banId"] == ban_id), None)
    if row is None:
        raise HTTPException(status_code = 404, detail = "Ban not found")
    report = row["aiReport"]
    stored = None
    if payload.store:
        stored = cognix_db.upsert_ban_report(
            ban_id,
            username = row.get("user"),
            risk_level = report.get("riskLevel") or "medium",
            summary = report.get("summary") or "",
            detected_behavior = report.get("detectedBehavior") or "",
            violated_rules = report.get("violatedRules") if isinstance(report.get("violatedRules"), list) else [],
            recommendation = report.get("recommendation") or "",
            report = report,
        )
    audit = cognix_db.create_audit_log(
        username = row.get("user") or current_subject,
        actor_username = current_subject,
        action = "ban_report_generated",
        resource_type = "cognix_ban",
        resource_id = ban_id,
        severity = "warning" if report.get("riskLevel") in {"high", "critical"} else "notice",
        metadata = {
            "riskLevel": report.get("riskLevel"),
            "stored": bool(stored),
            "recommendation": report.get("recommendation"),
        },
    )
    return {
        "banId": ban_id,
        "report": report,
        "storedReport": _row(stored) if stored else None,
        "auditLogId": audit.get("id"),
        "sideEffects": {"reportWrite": bool(stored), "auditWrite": True},
    }


@router.patch("/admin/banned/{ban_id}")
async def admin_update_banned(
    ban_id: str,
    payload: BanStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return await admin_update_ban(ban_id, payload, current_subject)


@router.get("/admin/bans")
async def admin_bans(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_banned_bundle()
    return {
        "bans": _rows(bundle["bans"]),
        "bannedDashboard": bundle["dashboard"],
    }


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
    audit = cognix_db.create_audit_log(
        username = str(ban.get("username") or current_subject),
        actor_username = current_subject,
        action = "ban_status_updated",
        resource_type = "cognix_ban",
        resource_id = ban_id,
        severity = "warning" if payload.status in {"active", "permanent"} else "notice",
        metadata = {
            "status": payload.status,
            "adminDecision": payload.admin_decision,
            "reactivation": payload.status == "cleared",
        },
    )
    return {
        "ban": _row(ban),
        "auditLogId": audit.get("id"),
        "sideEffects": {"banWrite": True, "auditWrite": True},
    }


@router.get("/admin/security-threats/blueprint")
async def admin_security_threats_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return cognix_admin_security.build_security_threats_blueprint()


@router.get("/admin/security-threats")
async def admin_security_threats(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_security_bundle()
    return {
        "threats": _rows(bundle["securityEvents"]),
        "securityThreats": _rows(bundle["securityThreats"]),
        "securityReports": _rows(bundle["securityReports"]),
        "vulnerabilityFindings": _rows(bundle["vulnerabilityFindings"]),
        "remediationTasks": _rows(bundle["remediationTasks"]),
        "threatReport": bundle["threatReport"],
        "securityThreatCenter": bundle["securityThreatCenter"],
        "incidentCategories": bundle["securityThreatCenter"]["incidentCategories"],
        "codexSummaries": bundle["securityThreatCenter"]["codexSummaries"],
        "riskScoring": bundle["riskScoring"],
        "knownAttacks": [
            {
                "id": item["id"],
                "label": item["label"],
                "severity": item["severity"],
            }
            for item in cognix_db.KNOWN_ATTACK_SIGNATURES
        ],
        "blueprint": cognix_admin_security.build_security_threats_blueprint(),
        "sideEffects": bundle["securityThreatCenter"]["sideEffects"],
    }


@router.get("/admin/risk-scores")
async def admin_risk_scores(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_security_bundle()
    return {
        "riskScoring": bundle["riskScoring"],
        "threatSummary": bundle["threatReport"]["summary"],
        "sideEffects": bundle["riskScoring"]["sideEffects"],
    }


@router.get("/admin/system-health")
async def admin_system_health(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_security_bundle()
    return {
        "systemHealth": bundle["systemHealth"],
        "threatSummary": bundle["threatReport"]["summary"],
        "riskSummary": bundle["riskScoring"]["summary"],
        "sideEffects": bundle["systemHealth"]["sideEffects"],
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
