# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX product/admin API routes."""

from __future__ import annotations

import re
import shutil
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from auth import storage as auth_storage
from auth.authentication import get_current_jwt_subject
from core.cognix import admin_activity as cognix_admin_activity
from core.cognix import admin_compliance_export as cognix_admin_compliance_export
from core.cognix import admin_data_retention as cognix_admin_data_retention
from core.cognix import admin_approvals as cognix_admin_approvals
from core.cognix import admin_banned as cognix_admin_banned
from core.cognix import admin_chat as cognix_admin_chat
from core.cognix import admin_limits as cognix_admin_limits
from core.cognix import admin_local_only as cognix_admin_local_only
from core.cognix import admin_organization_settings as cognix_admin_organization_settings
from core.cognix import admin_permissions as cognix_admin_permissions
from core.cognix import admin_project_oversight as cognix_admin_project_oversight
from core.cognix import admin_security as cognix_admin_security
from core.cognix import admin_secure_model_registry as cognix_admin_secure_model_registry
from core.cognix import admin_usage as cognix_admin_usage
from core.cognix import admin_users as cognix_admin_users
from core.cognix import api_surface as cognix_api_surface
from core.cognix import apps as cognix_apps
from core.cognix import benchmark as cognix_benchmark
from core.cognix import batching as cognix_batching
from core.cognix import background_agents as cognix_background_agents
from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import chat_project_bridge as cognix_chat_project_bridge
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import command_palette as cognix_command_palette
from core.cognix import context_graph as cognix_context_graph
from core.cognix import context_heatmap as cognix_context_heatmap
from core.cognix import context_manager as cognix_context_manager
from core.cognix import cost_optimizer as cognix_cost_optimizer
from core.cognix import database_blueprint as cognix_database_blueprint
from core.cognix import dataset_builder as cognix_dataset_builder
from core.cognix import debate_orchestrator as cognix_debate_orchestrator
from core.cognix import deployment_manager as cognix_deployment_manager
from core.cognix import distillation_planner as cognix_distillation_planner
from core.cognix import draft_generation as cognix_draft_generation
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import decision_explainer as cognix_decision_explainer
from core.cognix import dynamic_ui as cognix_dynamic_ui
from core.cognix import enterprise_chat as cognix_enterprise_chat
from core.cognix import evolution_engine as cognix_evolution_engine
from core.cognix import favorite_models as cognix_favorite_models
from core.cognix import fine_tuning_planner as cognix_fine_tuning_planner
from core.cognix import governance_manager as cognix_governance_manager
from core.cognix import gpts as cognix_gpts
from core.cognix import hardware as cognix_hardware
from core.cognix import images as cognix_images
from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import intent_prediction as cognix_intent_prediction
from core.cognix import kv_cache as cognix_kv_cache
from core.cognix import library as cognix_library
from core.cognix import memory_manager as cognix_memory_manager
from core.cognix import memory_editor as cognix_memory_editor
from core.cognix import model_comparison as cognix_model_comparison
from core.cognix import model_lifecycle as cognix_model_lifecycle
from core.cognix import model_translator as cognix_model_translator
from core.cognix import module_registry as cognix_module_registry
from core.cognix import mvp_readiness as cognix_mvp_readiness
from core.cognix import native_tools as cognix_native_tools
from core.cognix import onboarding as cognix_onboarding
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import notifications as cognix_notifications
from core.cognix import persona_manager as cognix_persona_manager
from core.cognix import personal_twin as cognix_personal_twin
from core.cognix import performance_monitor as cognix_performance_monitor
from core.cognix import plugin_marketplace as cognix_plugin_marketplace
from core.cognix import project_skills_directives as cognix_project_skills_directives
from core.cognix import project_dna as cognix_project_dna
from core.cognix import project_experts as cognix_project_experts
from core.cognix import prompt_cache as cognix_prompt_cache
from core.cognix import pulse as cognix_pulse
from core.cognix import prompt_compression as cognix_prompt_compression
from core.cognix import quantization_advisor as cognix_quantization_advisor
from core.cognix import rag_compression as cognix_rag_compression
from core.cognix import rag_planner as cognix_rag_planner
from core.cognix import registry as cognix_registry
from core.cognix import recommender as cognix_recommender
from core.cognix import realtime_collaboration as cognix_realtime_collaboration
from core.cognix import research_watch as cognix_research_watch
from core.cognix import response_reflection as cognix_response_reflection
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import sandbox as cognix_sandbox
from core.cognix import scheduled as cognix_scheduled
from core.cognix import security_policy as cognix_security_policy
from core.cognix import semantic_cache as cognix_semantic_cache
from core.cognix import sensitive_audit as cognix_sensitive_audit
from core.cognix import shared_knowledge_base as cognix_shared_knowledge_base
from core.cognix import skill_memory as cognix_skill_memory
from core.cognix import skill_marketplace as cognix_skill_marketplace
from core.cognix import simulation as cognix_simulation
from core.cognix import speculative_decoding as cognix_speculative_decoding
from core.cognix import thinking_status as cognix_thinking_status
from core.cognix import timeline as cognix_timeline
from core.cognix import tool_discovery as cognix_tool_discovery
from core.cognix import tool_registry as cognix_tool_registry
from core.cognix import workflow_recorder as cognix_workflow_recorder
from core.cognix import worker_queue as cognix_worker_queue
from core.cognix.router import classify_objective
from core.cognix.strategy import build_strategy
from storage import cognix_db
from storage.studio_db import (
    get_chat_message,
    get_chat_project,
    get_chat_thread,
    list_chat_messages_for_threads,
    list_chat_projects,
    list_chat_threads,
    upsert_chat_message,
    upsert_chat_project,
)


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


class NotificationPreferenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    enabled: bool = True
    channels: list[str] | None = None
    quiet_hours: dict[str, Any] | None = Field(None, alias = "quietHours")


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


class AdminProjectActionPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    action: Literal[
        "archive",
        "transfer_ownership",
        "remove_member",
        "add_member",
        "restrict_models",
        "disable_cloud",
        "export_report",
    ]
    reason: str = Field(..., min_length = 3, max_length = 1000)
    target_username: str | None = Field(None, alias = "targetUsername", max_length = 160)
    target_role: str | None = Field(None, alias = "targetRole", max_length = 80)
    model_ids: list[str] = Field(default_factory = list, alias = "modelIds")
    cloud_allowed: bool | None = Field(None, alias = "cloudAllowed")


class AdminProjectReportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    report_type: Literal["summary", "security", "usage", "full"] = Field("summary", alias = "reportType")
    output_format: Literal["json", "markdown"] = Field("json", alias = "outputFormat")
    reason: str | None = Field("", max_length = 1000)


class AdminOrganizationSettingsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    cloud_allowed: bool | None = Field(None, alias = "cloudAllowed")
    external_models_allowed: bool | None = Field(None, alias = "externalModelsAllowed")
    e2ee_allowed: bool | None = Field(None, alias = "e2eeAllowed")
    admin_chat_access_allowed: bool | None = Field(None, alias = "adminChatAccessAllowed")
    data_retention_days: int | None = Field(None, alias = "dataRetentionDays", ge = 1, le = 3650)
    role_quotas: dict[str, Any] | None = Field(None, alias = "roleQuotas")
    allowed_models: list[str] | None = Field(None, alias = "allowedModels")
    allowed_apps: list[str] | None = Field(None, alias = "allowedApps")
    default_permissions: list[str] | None = Field(None, alias = "defaultPermissions")
    approval_required: bool | None = Field(None, alias = "approvalRequired")
    reason: str | None = Field("", max_length = 1000)


class AdminLocalOnlyPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    enabled: bool | None = None
    allowed_hosts: list[str] | None = Field(None, alias = "allowedHosts")
    allowed_providers: list[str] | None = Field(None, alias = "allowedProviders")
    block_cloud_providers: bool | None = Field(None, alias = "blockCloudProviders")
    block_external_models: bool | None = Field(None, alias = "blockExternalModels")
    block_telemetry: bool | None = Field(None, alias = "blockTelemetry")
    block_document_egress: bool | None = Field(None, alias = "blockDocumentEgress")
    internal_logs_only: bool | None = Field(None, alias = "internalLogsOnly")
    reason: str | None = Field("", max_length = 1000)


class AdminLocalOnlyDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    provider: str | None = Field(None, max_length = 120)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    url: str | None = Field(None, max_length = 1000)
    action_type: Literal["model", "provider", "generation", "tool", "telemetry", "document", "document_egress", "network"] = Field(
        "network",
        alias = "actionType",
    )
    document_transfer: bool = Field(False, alias = "documentTransfer")
    metadata: dict[str, Any] = Field(default_factory = dict)


class AdminSecureModelApprovalRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    display_name: str | None = Field(None, alias = "displayName", max_length = 240)
    provider_type: str = Field("local", alias = "providerType", max_length = 80)
    allowed_roles: list[str] = Field(default_factory = list, alias = "allowedRoles")
    quantization_required: str | None = Field("", alias = "quantizationRequired", max_length = 80)
    local_only_required: bool = Field(False, alias = "localOnlyRequired")
    license_name: str | None = Field("unknown", alias = "license", max_length = 160)
    source: str | None = Field("unknown", max_length = 500)
    checksum: str | None = Field("", max_length = 160)
    reason: str | None = Field("", max_length = 1000)


class AdminSecureModelBlockRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    provider_type: str | None = Field("", alias = "providerType", max_length = 80)
    reason: str = Field(..., min_length = 3, max_length = 1000)


class AdminSecureModelDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    provider_type: str | None = Field("local", alias = "providerType", max_length = 80)
    role: str | None = Field("user", max_length = 80)
    quantization: str | None = Field("", max_length = 80)
    local_only_active: bool = Field(False, alias = "localOnlyActive")


class SharedKnowledgeBaseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    name: str = Field(..., min_length = 1, max_length = 240)
    description: str | None = Field("", max_length = 1000)
    visibility: Literal["restricted", "organization", "project"] = "restricted"
    project_id: str | None = Field(None, alias = "projectId", max_length = 240)


class SharedKnowledgeDocumentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    title: str = Field(..., min_length = 1, max_length = 240)
    content: str = Field(..., min_length = 1, max_length = 300000)
    source_type: str = Field("text", alias = "sourceType", max_length = 80)
    source_uri: str | None = Field("", alias = "sourceUri", max_length = 1000)
    chunk_size: int = Field(120, alias = "chunkSize", ge = 20, le = 500)
    overlap: int = Field(20, ge = 0, le = 100)


class SharedKnowledgePermissionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    subject_type: Literal["user", "role", "everyone"] = Field(..., alias = "subjectType")
    subject_id: str = Field("", alias = "subjectId", max_length = 160)
    permission: Literal["read", "write", "admin"] = "read"
    document_id: str | None = Field("", alias = "documentId", max_length = 240)


class SharedKnowledgeQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    query: str = Field(..., min_length = 1, max_length = 4000)
    role: str = Field("user", max_length = 80)
    limit: int = Field(5, ge = 1, le = 20)


class AdminPolicyEnforcementRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    action_type: Literal["cloud", "model", "generation", "app", "permission", "admin_chat_access"] = Field(
        "model",
        alias = "actionType",
    )
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    provider: str | None = Field(None, max_length = 120)
    app_id: str | None = Field(None, alias = "appId", max_length = 160)
    permission_key: str | None = Field(None, alias = "permissionKey", max_length = 160)


class AdminComplianceExportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    report_type: Literal[
        "full",
        "usage_tokens",
        "user_activity",
        "security_threats",
        "banned_users",
        "approvals",
        "models_used",
        "tools_used",
        "document_access",
        "admin_chat_access",
    ] = Field("full", alias = "reportType")
    output_format: Literal["json", "markdown", "csv", "pdf"] = Field("json", alias = "outputFormat")
    reason: str | None = Field("", max_length = 1000)


class AdminDataRetentionPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    chat_retention_days: int | None = Field(None, alias = "chatRetentionDays", ge = 1, le = 3650)
    project_archive_months: int | None = Field(None, alias = "projectArchiveMonths", ge = 1, le = 240)
    sensitive_prompt_mode: Literal["store", "redact", "metadata_only", "disabled"] | None = Field(
        None,
        alias = "sensitivePromptMode",
    )
    content_logs_enabled: bool | None = Field(None, alias = "contentLogsEnabled")
    metadata_only_mode: bool | None = Field(None, alias = "metadataOnlyMode")
    user_export_enabled: bool | None = Field(None, alias = "userExportEnabled")
    user_deletion_requires_approval: bool | None = Field(None, alias = "userDeletionRequiresApproval")
    e2ee_strict: bool | None = Field(None, alias = "e2eeStrict")
    reason: str | None = Field("", max_length = 1000)


class AdminPrivacyDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    content: Any | None = None
    target_username: str | None = Field(None, alias = "targetUsername", max_length = 160)
    e2ee_strict: bool | None = Field(None, alias = "e2eeStrict")
    metadata: dict[str, Any] = Field(default_factory = dict)


class AdminUserDataRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    reason: str = Field(..., min_length = 3, max_length = 1000)
    include_content: bool = Field(False, alias = "includeContent")
    output_format: Literal["json", "markdown"] = Field("json", alias = "outputFormat")


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


class ConversationSummaryPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    messages: list[dict[str, Any]] = Field(default_factory = list, max_length = 500)
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    target_tokens: int = Field(420, alias = "targetTokens", ge = 64, le = 8000)
    recent_message_limit: int = Field(6, alias = "recentMessageLimit", ge = 1, le = 20)
    store_context: bool = Field(True, alias = "storeContext")


class SemanticCachePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 240000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    task_type: str | None = Field(None, alias = "taskType", max_length = 80)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    sensitivity_level: str | None = Field(None, alias = "sensitivityLevel", max_length = 80)
    requires_sources: bool = Field(False, alias = "requiresSources")
    context_hashes: list[str] | None = Field(None, alias = "contextHashes")


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


class ChatProjectLinkRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str = Field(..., alias = "projectId", min_length = 1, max_length = 160)
    thread_id: str = Field(..., alias = "threadId", min_length = 1, max_length = 160)
    link_type: Literal["conversation", "answer_share", "approval_context"] = Field("conversation", alias = "linkType")
    source: Literal["chat", "project", "manual"] = "chat"
    metadata: dict[str, Any] | None = None
    store_link: bool = Field(True, alias = "storeLink")


class MessageTaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str = Field(..., alias = "projectId", min_length = 1, max_length = 160)
    thread_id: str | None = Field(None, alias = "threadId", max_length = 160)
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    title: str | None = Field(None, max_length = 180)
    source_text: str = Field(..., alias = "sourceText", min_length = 1, max_length = 12000)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["open", "in_progress", "done", "blocked"] = "open"
    require_approval: bool = Field(False, alias = "requireApproval")
    metadata: dict[str, Any] | None = None
    store_task: bool = Field(True, alias = "storeTask")


class AnswerShareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    project_id: str = Field(..., alias = "projectId", min_length = 1, max_length = 160)
    thread_id: str = Field(..., alias = "threadId", min_length = 1, max_length = 160)
    answer_text: str = Field(..., alias = "answerText", min_length = 1, max_length = 12000)
    title: str | None = Field(None, max_length = 180)
    parent_message_id: str | None = Field(None, alias = "parentMessageId", max_length = 160)
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    metadata: dict[str, Any] | None = None
    store_share: bool = Field(True, alias = "storeShare")


class DiscussionProjectCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    thread_id: str = Field(..., alias = "threadId", min_length = 1, max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_name: str = Field(..., alias = "projectName", min_length = 1, max_length = 240)
    discussion_summary: str = Field(..., alias = "discussionSummary", min_length = 1, max_length = 4000)
    instructions: str | None = Field(None, max_length = 4000)
    metadata: dict[str, Any] | None = None
    store_project: bool = Field(True, alias = "storeProject")


class ProjectMentionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    text: str = Field(..., min_length = 1, max_length = 12000)
    limit: int = Field(8, ge = 1, le = 40)


class AppConnectionRequest(BaseModel):
    app_id: str = Field(..., min_length = 1, max_length = 80)
    app_name: str = Field(..., min_length = 1, max_length = 120)
    status: Literal["connected", "disabled"] = "connected"


class SocialMessageRequest(BaseModel):
    content: str = Field(..., min_length = 1, max_length = 2000)


class SocialAgentRequest(BaseModel):
    prompt: str | None = Field(None, max_length = 1000)


class ModelPinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    label: str = Field(..., min_length = 1, max_length = 240)
    provider_type: str | None = Field(None, alias = "providerType", max_length = 80)
    provider_id: str | None = Field(None, alias = "providerId", max_length = 160)
    source: str | None = Field(None, max_length = 80)
    project_ids: list[Any] | None = Field(None, alias = "projectIds")
    quick_switcher: bool = Field(True, alias = "quickSwitcher")
    sort_order: int = Field(0, alias = "sortOrder", ge = -10000, le = 10000)
    metadata: dict[str, Any] | None = None


class UserDefaultModelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str = Field(..., alias = "modelId", min_length = 1, max_length = 240)
    label: str = Field(..., min_length = 1, max_length = 240)
    provider_type: str | None = Field(None, alias = "providerType", max_length = 80)
    provider_id: str | None = Field(None, alias = "providerId", max_length = 160)
    source: str | None = Field(None, max_length = 80)
    metadata: dict[str, Any] | None = None


class ModelLifecyclePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    execution_target: str | None = Field(None, alias = "executionTarget", max_length = 120)
    quality_priority: str | None = Field(None, alias = "qualityPriority", max_length = 80)
    offline_required: bool = Field(False, alias = "offlineRequired")


class ModelInstallContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    provider_type: str | None = Field(None, alias = "providerType", max_length = 80)
    source: str | None = Field(None, max_length = 120)
    revision: str | None = Field(None, max_length = 160)
    license_id: str | None = Field(None, alias = "licenseId", max_length = 160)
    license_accepted: bool = Field(False, alias = "licenseAccepted")
    allow_network: bool = Field(False, alias = "allowNetwork")
    offline_required: bool = Field(False, alias = "offlineRequired")
    gated_model: bool = Field(False, alias = "gatedModel")
    confirmation_id: str | None = Field(None, alias = "confirmationId", max_length = 180)
    request_id: str | None = Field(None, alias = "requestId", max_length = 180)
    estimated_storage_gb: float | None = Field(None, alias = "estimatedStorageGb", ge = 0)
    estimated_ram_gb: float | None = Field(None, alias = "estimatedRamGb", ge = 0)


class ModelResidencyContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    execution_target: str | None = Field(None, alias = "executionTarget", max_length = 120)
    quality_priority: str | None = Field(None, alias = "qualityPriority", max_length = 80)
    offline_required: bool = Field(False, alias = "offlineRequired")
    confirmation_id: str | None = Field(None, alias = "confirmationId", max_length = 180)
    request_id: str | None = Field(None, alias = "requestId", max_length = 180)


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


class ExpertGeneralistQualityGateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    prompt: str = Field(..., min_length = 1, max_length = 120000)
    expert_response: str = Field("", alias = "expertResponse", max_length = 400000)
    message_id: str | None = Field(None, alias = "messageId", max_length = 160)
    thread_id: str | None = Field(None, alias = "threadId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    expert_model_id: str | None = Field(None, alias = "expertModelId", max_length = 240)
    generalist_model_id: str | None = Field(None, alias = "generalistModelId", max_length = 240)
    task_type: str | None = Field(None, alias = "taskType", max_length = 80)
    domain: str | None = Field(None, max_length = 80)
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


class SkillMarketplacePublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    skill_manifest: dict[str, Any] | None = Field(None, alias = "skillManifest")
    display_name: str | None = Field(None, alias = "displayName", max_length = 160)
    description: str | None = Field(None, max_length = 600)
    category: str | None = Field(None, max_length = 120)
    version: str | None = Field(None, max_length = 80)
    instructions: str | None = Field(None, max_length = 4000)
    allowed_roles: list[str] | None = Field(None, alias = "allowedRoles")
    organization_id: str = Field("local", alias = "organizationId", max_length = 120)
    store_skill: bool = Field(True, alias = "storeSkill")


class SkillMarketplaceApprovalRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    status: Literal["approved", "denied", "disabled"]
    admin_note: str | None = Field(None, alias = "adminNote", max_length = 1200)


class SkillMarketplaceUsageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    skill_id: str = Field(..., alias = "skillId", min_length = 1, max_length = 160)
    action: Literal["view", "use", "share", "version", "disable"] = "use"
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    metadata: dict[str, Any] | None = None


class ProjectSkillRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    skill_config: dict[str, Any] | None = Field(None, alias = "skillConfig")
    display_name: str | None = Field(None, alias = "displayName", max_length = 180)
    description: str | None = Field(None, max_length = 1000)
    objective: str | None = Field(None, max_length = 1200)
    instructions: str | None = Field(None, max_length = 6000)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    allowed_tools: list[str] | None = Field(None, alias = "allowedTools")
    limits: dict[str, Any] | None = None
    examples: list[Any] | None = None
    store_skill: bool = Field(True, alias = "storeSkill")


class ProjectSkillInjectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str | None = Field(None, alias = "modelId", max_length = 240)


class ProjectDirectiveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    directive_config: dict[str, Any] | None = Field(None, alias = "directiveConfig")
    content: str | None = Field(None, max_length = 3000)
    directive_type: str | None = Field(None, alias = "directiveType", max_length = 80)
    priority: int = Field(50, ge = 0, le = 100)
    scope: str = Field("project", max_length = 80)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    source_level: str | None = Field(None, alias = "sourceLevel", max_length = 80)
    store_directive: bool = Field(True, alias = "storeDirective")


class ProjectDirectiveCompileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    model_id: str | None = Field(None, alias = "modelId", max_length = 240)


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


class EnterpriseChatCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    title: str | None = Field(None, max_length = 180)
    organization_id: str = Field("local", alias = "organizationId", max_length = 160)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    chat_mode: Literal["compliance", "e2ee"] = Field("e2ee", alias = "chatMode")
    participants: list[Any] | None = None
    policy: dict[str, Any] | None = None
    store_chat: bool = Field(True, alias = "storeChat")


class EnterpriseEncryptedMessageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    encrypted_payload: dict[str, Any] | None = Field(None, alias = "encryptedPayload")
    metadata: dict[str, Any] | None = None
    store_message: bool = Field(True, alias = "storeMessage")


class EnterpriseKeyRotationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    reason: str | None = Field(None, max_length = 500)
    revoked_member: str | None = Field(None, alias = "revokedMember", max_length = 160)


class RealtimePresenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    client_id: str = Field("browser", alias = "clientId", max_length = 160)
    status: Literal["online", "idle", "editing", "viewing", "offline"] = "online"
    cursor: dict[str, Any] | None = None
    activity: str | None = Field(None, max_length = 180)
    ttl_seconds: int = Field(90, alias = "ttlSeconds", ge = 15, le = 600)
    metadata: dict[str, Any] | None = None


class ProjectCommentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    body: str = Field(..., min_length = 1, max_length = 3000)
    target: dict[str, Any] | None = None
    parent_comment_id: str | None = Field(None, alias = "parentCommentId", max_length = 160)
    metadata: dict[str, Any] | None = None
    store_comment: bool = Field(True, alias = "storeComment")


class ProjectCommentResolutionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    status: Literal["resolved", "open", "archived"] = "resolved"
    note: str | None = Field(None, max_length = 1000)


class CollaborationEventRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    event_type: str = Field(..., alias = "eventType", min_length = 1, max_length = 120)
    resource_type: str = Field("project", alias = "resourceType", max_length = 120)
    resource_id: str | None = Field(None, alias = "resourceId", max_length = 200)
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    store_event: bool = Field(True, alias = "storeEvent")


class ConflictResolutionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    resource_type: str = Field("document", alias = "resourceType", max_length = 120)
    resource_id: str = Field(..., alias = "resourceId", min_length = 1, max_length = 200)
    base_revision: str | None = Field(None, alias = "baseRevision", max_length = 120)
    local_revision: str | None = Field(None, alias = "localRevision", max_length = 120)
    remote_revision: str | None = Field(None, alias = "remoteRevision", max_length = 120)
    strategy: Literal["manual_review", "latest_wins", "owner_wins", "merge_if_clean"] = "manual_review"
    changes: list[Any] | None = None


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


class ModelCachePressurePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

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


class FineTuningDatasetValidationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    dataset: dict[str, Any] | None = None


class FineTuningCloudHandoffPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    target_id: str | None = Field(None, alias = "targetId", max_length = 120)
    dataset: dict[str, Any] | None = None


class FineTuningEvaluationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    dataset: dict[str, Any] | None = None
    training_artifact: dict[str, Any] | None = Field(None, alias = "trainingArtifact")
    baseline_model: dict[str, Any] | None = Field(None, alias = "baselineModel")
    requested_metrics: list[str] | None = Field(None, alias = "requestedMetrics")


class FineTuningDistillationPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    teacher_model: dict[str, Any] | None = Field(None, alias = "teacherModel")
    student_model: dict[str, Any] | None = Field(None, alias = "studentModel")
    dataset: dict[str, Any] | None = None
    target_id: str | None = Field(None, alias = "targetId", max_length = 120)


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


class RagCompressionPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    chunks: list[dict[str, Any]] = Field(..., min_length = 1, max_length = 80)
    target_tokens: int = Field(900, alias = "targetTokens", ge = 64, le = 12000)
    max_chunks: int = Field(6, alias = "maxChunks", ge = 1, le = 20)
    require_citations: bool = Field(True, alias = "requireCitations")


class RagIndexingPlanRequest(BaseModel):
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None


class RagConnectorSyncPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    connector_id: str = Field(..., alias = "connectorId", min_length = 1, max_length = 120)
    objective: str | None = Field(None, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    source_filters: dict[str, Any] | None = Field(None, alias = "sourceFilters")
    max_documents: int | None = Field(None, alias = "maxDocuments", ge = 1, le = 500)


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


class OptimizationApplicationContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    requested_optimizations: list[str] | None = Field(None, alias = "requestedOptimizations")
    confirmation_id: str | None = Field(None, alias = "confirmationId", max_length = 180)
    rollback_plan_id: str | None = Field(None, alias = "rollbackPlanId", max_length = 180)
    request_id: str | None = Field(None, alias = "requestId", max_length = 180)


class SpeculativeDecodingPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    runtime_adapter: dict[str, Any] | None = Field(None, alias = "runtimeAdapter")
    target_model: dict[str, Any] | None = Field(None, alias = "targetModel")
    draft_model: dict[str, Any] | None = Field(None, alias = "draftModel")
    max_quality_delta: float = Field(0.02, alias = "maxQualityDelta", ge = 0.0, le = 0.2)


class KvCacheEvictionPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    runtime_adapter: dict[str, Any] | None = Field(None, alias = "runtimeAdapter")
    model: dict[str, Any] | None = None
    context_plan: dict[str, Any] | None = Field(None, alias = "contextPlan")
    context_blocks: list[dict[str, Any]] | None = Field(None, alias = "contextBlocks", max_length = 120)
    target_token_budget: int | None = Field(None, alias = "targetTokenBudget", ge = 256, le = 262144)


class PromptCachePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    runtime_adapter: dict[str, Any] | None = Field(None, alias = "runtimeAdapter")
    model: dict[str, Any] | None = None
    context_plan: dict[str, Any] | None = Field(None, alias = "contextPlan")
    prompt_segments: list[dict[str, Any]] | None = Field(None, alias = "promptSegments", max_length = 120)
    sensitivity_level: str | None = Field(None, alias = "sensitivityLevel", max_length = 80)
    expected_reuse_count: int | None = Field(None, alias = "expectedReuseCount", ge = 1, le = 100000)


class BatchingPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    runtime_adapter: dict[str, Any] | None = Field(None, alias = "runtimeAdapter")
    deployment_target: str | None = Field(None, alias = "deploymentTarget", max_length = 120)
    concurrent_users: int | None = Field(None, alias = "concurrentUsers", ge = 1, le = 100000)
    request_rate_per_minute: float | None = Field(None, alias = "requestRatePerMinute", ge = 0, le = 10_000_000)
    average_prompt_tokens: int | None = Field(None, alias = "averagePromptTokens", ge = 1, le = 1_000_000)
    average_completion_tokens: int | None = Field(None, alias = "averageCompletionTokens", ge = 1, le = 1_000_000)
    target_latency_ms: int | None = Field(None, alias = "targetLatencyMs", ge = 250, le = 600_000)


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
    enforce_quotas: bool = Field(True, alias = "enforceQuotas")
    store_log: bool = Field(True, alias = "storeLog")


class RuntimePlanRequest(BaseModel):
    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)


class RuntimeFallbackPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, alias = "projectType", max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    runtime_adapter: dict[str, Any] | None = Field(None, alias = "runtimeAdapter")
    required_capabilities: list[str] | None = Field(None, alias = "requiredCapabilities")
    requested_optimization_ids: list[str] | None = Field(None, alias = "requestedOptimizationIds")
    allow_cloud_fallback: bool = Field(False, alias = "allowCloudFallback")
    data_sensitivity: str | None = Field(None, alias = "dataSensitivity", max_length = 80)


class FrontendBoundaryContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    endpoint: str = Field(..., min_length = 1, max_length = 500)
    provider_type: str | None = Field(None, alias = "providerType", max_length = 80)
    model_id: str | None = Field(None, alias = "modelId", max_length = 240)
    request_intent: str | None = Field(None, alias = "requestIntent", max_length = 120)


class CodexPipelinePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    run_mode: str | None = Field(None, alias = "runMode", max_length = 40)
    night_mode: bool | None = Field(None, alias = "nightMode")


class CodexPreviewContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    branch_name: str | None = Field(None, alias = "branchName", max_length = 180)
    feature_request: dict[str, Any] | None = Field(None, alias = "featureRequest")
    test_results: dict[str, Any] | None = Field(None, alias = "testResults")
    build_result: dict[str, Any] | None = Field(None, alias = "buildResult")
    security_scan: dict[str, Any] | None = Field(None, alias = "securityScan")
    preview_target: str | None = Field(None, alias = "previewTarget", max_length = 120)


class CodexNightReportContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    run_mode: str | None = Field(None, alias = "runMode", max_length = 40)
    night_mode: bool | None = Field(None, alias = "nightMode")
    files_modified: list[Any] | None = Field(None, alias = "filesModified")
    tests_run: list[Any] | None = Field(None, alias = "testsRun")
    results: dict[str, Any] | str | None = None
    risks_detected: list[Any] | None = Field(None, alias = "risksDetected")
    recommendations_for_human_validation: list[Any] | None = Field(
        None,
        alias = "recommendationsForHumanValidation",
    )


class CodexApprovalGateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, alias = "projectId", max_length = 160)
    approval_request_id: str | None = Field(None, alias = "approvalRequestId", max_length = 120)
    branch_name: str | None = Field(None, alias = "branchName", max_length = 180)
    feature_request: dict[str, Any] | None = Field(None, alias = "featureRequest")
    test_results: dict[str, Any] | None = Field(None, alias = "testResults")
    build_result: dict[str, Any] | None = Field(None, alias = "buildResult")
    security_scan: dict[str, Any] | None = Field(None, alias = "securityScan")
    preview_target: str | None = Field(None, alias = "previewTarget", max_length = 120)


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
    rag_connector_sync_plan: dict[str, Any] | None = Field(None, alias = "ragConnectorSyncPlan")
    tool_execution_handoff: dict[str, Any] | None = Field(None, alias = "toolExecutionHandoff")
    dataset: dict[str, Any] | None = None
    target_id: str | None = Field(None, alias = "targetId", max_length = 120)


class WorkerEnqueueContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    project_type: str | None = Field(None, max_length = 80)
    project_id: str | None = Field(None, max_length = 160)
    sources: list[dict[str, Any]] | None = None
    rag_connector_sync_plan: dict[str, Any] | None = Field(None, alias = "ragConnectorSyncPlan")
    tool_execution_handoff: dict[str, Any] | None = Field(None, alias = "toolExecutionHandoff")
    dataset: dict[str, Any] | None = None
    target_id: str | None = Field(None, alias = "targetId", max_length = 120)
    confirmation_id: str | None = Field(None, alias = "confirmationId", max_length = 180)
    confirmation_ids: dict[str, str] | None = Field(None, alias = "confirmationIds")
    request_id: str | None = Field(None, alias = "requestId", max_length = 180)


class DeploymentPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    target_type: str | None = Field(None, alias = "targetType", max_length = 120)
    edition: str | None = Field(None, max_length = 80)
    expected_users: int | None = Field(None, alias = "expectedUsers", ge = 1, le = 100000)
    data_sensitivity: str | None = Field(None, alias = "dataSensitivity", max_length = 120)
    requested_features: list[str] | None = Field(None, alias = "requestedFeatures")


class GpuSchedulerContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    objective: str = Field(..., min_length = 1, max_length = 4000)
    target_type: str | None = Field(None, alias = "targetType", max_length = 120)
    edition: str | None = Field(None, max_length = 80)
    expected_users: int | None = Field(None, alias = "expectedUsers", ge = 1, le = 100000)
    data_sensitivity: str | None = Field(None, alias = "dataSensitivity", max_length = 120)
    requested_features: list[str] | None = Field(None, alias = "requestedFeatures")
    gpu_nodes: list[dict[str, Any]] | None = Field(None, alias = "gpuNodes")
    workloads: list[dict[str, Any]] | None = None
    tenant_policy: dict[str, Any] | None = Field(None, alias = "tenantPolicy")


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


class ToolCalculatorEvaluateRequest(BaseModel):
    expression: str = Field(..., min_length = 1, max_length = 300)
    precision: int = Field(12, ge = 1, le = 16)


class ToolPhysicsSolveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    formula_id: str = Field(..., alias = "formulaId", min_length = 1, max_length = 120)
    variables: dict[str, Any] = Field(default_factory = dict)
    precision: int = Field(12, ge = 1, le = 16)


class ToolLatexRenderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    source: str = Field(..., min_length = 1, max_length = 2000)
    display_mode: bool = Field(True, alias = "displayMode")
    context: Literal["math", "physics", "general"] = "math"


class ToolExecutionHandoffRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    tool_id: str = Field(..., alias = "toolId", min_length = 1, max_length = 120)
    action_id: str = Field(..., alias = "actionId", min_length = 1, max_length = 120)
    confirmation_id: str | None = Field(None, alias = "confirmationId", max_length = 180)
    sandbox_run_id: str | None = Field(None, alias = "sandboxRunId", max_length = 180)
    request_id: str | None = Field(None, alias = "requestId", max_length = 180)


class IntegrationPlanRequest(BaseModel):
    tool_id: str = Field(..., min_length = 1, max_length = 120)


class IntegrationActivationContractRequest(BaseModel):
    tool_id: str = Field(..., min_length = 1, max_length = 120)


class IntegrationPreflightContractRequest(BaseModel):
    tool_id: str = Field(..., min_length = 1, max_length = 120)


class IntegrationSecretRotationContractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name = True)

    tool_id: str = Field(..., alias = "toolId", min_length = 1, max_length = 120)
    rotation_reason: str | None = Field(None, alias = "rotationReason", max_length = 120)
    current_secret_age_days: int | None = Field(None, alias = "currentSecretAgeDays", ge = 0, le = 10000)
    last_rotation_at: str | None = Field(None, alias = "lastRotationAt", max_length = 120)


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


def _admin_storage_metrics() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    total_gb = round(usage.total / (1024**3), 2)
    free_gb = round(usage.free / (1024**3), 2)
    used_percent = round(((usage.total - usage.free) / usage.total) * 100, 2) if usage.total else 0.0
    return {
        "path": "/",
        "totalGb": total_gb,
        "freeGb": free_gb,
        "usedPercent": used_percent,
    }


def _admin_background_jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for profile in auth_storage.list_user_profiles():
        username = str(profile.get("username") or "")
        if not username:
            continue
        jobs.extend(cognix_db.list_background_jobs(username, limit = 100))
    return jobs


def _build_admin_security_bundle() -> dict[str, Any]:
    security_events = cognix_db.list_security_events(limit = 500)
    audit_logs = cognix_db.list_audit_logs(limit = 500)
    bans = cognix_db.list_bans()
    reports = cognix_db.list_reports()
    security_threats = cognix_db.list_security_threats(limit = 500)
    security_reports = cognix_db.list_security_reports(limit = 500)
    vulnerability_findings = cognix_db.list_vulnerability_findings(limit = 500)
    remediation_tasks = cognix_db.list_security_remediation_tasks(limit = 500)
    token_events = cognix_db.list_token_usage_events(limit = 1000)
    router_logs = cognix_db.list_router_logs(limit = 500)
    orchestrator_logs = cognix_db.list_orchestrator_logs(limit = 500)
    background_jobs = _admin_background_jobs()
    service_health_events = cognix_db.list_service_health_events(limit = 200)
    system_health_snapshots = cognix_db.list_system_health_snapshots(limit = 100)
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
        background_jobs = background_jobs,
        token_events = token_events,
        router_logs = router_logs,
        orchestrator_logs = orchestrator_logs,
        service_events = service_health_events,
        storage = _admin_storage_metrics(),
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
        "tokenEvents": token_events,
        "routerLogs": router_logs,
        "orchestratorLogs": orchestrator_logs,
        "backgroundJobs": background_jobs,
        "serviceHealthEvents": service_health_events,
        "systemHealthSnapshots": system_health_snapshots,
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
    organization_policy = cognix_db.list_organization_policies()
    matrix = cognix_admin_permissions.build_permission_matrix(
        users = users,
        roles = roles,
        permissions = permission_definitions,
        role_permissions = role_permissions,
        user_overrides = user_overrides,
        project_permissions = project_permissions,
        legacy_user_permissions = legacy_permissions,
        organization_policy = organization_policy,
    )
    return {
        "users": users,
        "roles": roles,
        "permissionDefinitions": permission_definitions,
        "rolePermissions": role_permissions,
        "userOverrides": user_overrides,
        "projectPermissions": project_permissions,
        "organizationPolicy": organization_policy,
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


def _emit_approval_notifications(
    request: dict[str, Any],
    *,
    event: str,
    actor_username: str | None = None,
) -> dict[str, Any]:
    payload = cognix_notifications.build_approval_notification_payload(
        request = request,
        event = event,
        actor_username = actor_username,
    )
    notification = cognix_db.create_notification(
        username = str(request.get("username") or payload.get("username") or ""),
        notification_type = str(payload.get("notificationType") or event),
        title = str(payload.get("title") or "Approval"),
        message = str(payload.get("message") or ""),
        priority = str(payload.get("priority") or "normal"),
        source_type = str(payload.get("sourceType") or "cognix_approval_request"),
        source_id = str(payload.get("sourceId") or request.get("id") or ""),
        metadata = payload,
    )
    alert = cognix_db.create_admin_alert(
        alert_type = str(payload.get("notificationType") or event),
        title = str(payload.get("title") or "Approval"),
        message = str(payload.get("message") or ""),
        severity = "critical"
        if request.get("risk_level") == "critical"
        else "warning"
        if str(payload.get("priority") or "") in {"high", "critical"}
        else "notice",
        source_type = str(payload.get("sourceType") or "cognix_approval_request"),
        source_id = str(payload.get("sourceId") or request.get("id") or ""),
        metadata = payload,
    )
    return {"notification": notification, "adminAlert": alert, "payload": payload}


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


def _build_admin_project_oversight_bundle() -> dict[str, Any]:
    projects = list_chat_projects(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    threads = list_chat_threads(
        include_archived = True,
        owner_username = "",
        include_all = True,
    )
    messages = list_chat_messages_for_threads([str(thread.get("id")) for thread in threads if thread.get("id")])
    token_events = cognix_db.list_token_usage_events(limit = 5000)
    project_permissions = cognix_db.list_project_permissions()
    security_events = cognix_db.list_security_events(limit = 1000)
    audit_logs = cognix_db.list_audit_logs(limit = 1000)
    reports = cognix_db.list_reports()
    admin_project_events = cognix_db.list_admin_project_events(limit = 1000)
    project_admin_reports = cognix_db.list_project_admin_reports(limit = 1000)
    oversight = cognix_admin_project_oversight.build_admin_project_oversight(
        projects = projects,
        threads = threads,
        messages = messages,
        token_events = token_events,
        project_permissions = project_permissions,
        security_events = security_events,
        audit_logs = audit_logs,
        reports = reports,
        admin_project_events = admin_project_events,
        project_admin_reports = project_admin_reports,
    )
    return {
        "projects": projects,
        "threads": threads,
        "messages": messages,
        "tokenEvents": token_events,
        "projectPermissions": project_permissions,
        "securityEvents": security_events,
        "auditLogs": audit_logs,
        "reports": reports,
        "adminProjectEvents": admin_project_events,
        "projectAdminReports": project_admin_reports,
        "oversight": oversight,
    }


def _settings_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    settings = dict(cognix_admin_organization_settings.DEFAULT_ORGANIZATION_SETTINGS)
    for record in records:
        key = str(record.get("settingKey") or record.get("setting_key") or "")
        if not key:
            continue
        settings[key] = record.get("settingValue")
    return cognix_admin_organization_settings.normalize_organization_settings(settings)


def _settings_payload_to_dict(payload: AdminOrganizationSettingsRequest) -> dict[str, Any]:
    values: dict[str, Any] = {}
    mapping = {
        "cloudAllowed": payload.cloud_allowed,
        "externalModelsAllowed": payload.external_models_allowed,
        "e2eeAllowed": payload.e2ee_allowed,
        "adminChatAccessAllowed": payload.admin_chat_access_allowed,
        "dataRetentionDays": payload.data_retention_days,
        "roleQuotas": payload.role_quotas,
        "allowedModels": payload.allowed_models,
        "allowedApps": payload.allowed_apps,
        "defaultPermissions": payload.default_permissions,
        "approvalRequired": payload.approval_required,
    }
    for key, value in mapping.items():
        if value is not None:
            values[key] = value
    return values


def _build_admin_organization_settings_bundle() -> dict[str, Any]:
    setting_records = cognix_db.list_organization_settings()
    policies = cognix_db.list_organization_policies()
    change_logs = cognix_db.list_policy_change_logs(limit = 200)
    settings = _settings_from_records(setting_records)
    bundle = cognix_admin_organization_settings.build_policy_bundle(
        settings = settings,
        policies = policies,
        change_logs = change_logs,
    )
    return {
        "settings": settings,
        "settingRecords": setting_records,
        "policies": policies,
        "changeLogs": change_logs,
        "bundle": bundle,
    }


def _local_only_policy_from_record(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return cognix_admin_local_only.normalize_local_only_policy(
            cognix_admin_local_only.DEFAULT_LOCAL_ONLY_POLICY
        )
    stored_policy = record.get("policy") if isinstance(record.get("policy"), dict) else {}
    if not stored_policy:
        stored_policy = {
            "enabled": record.get("enabled"),
            "allowedHosts": record.get("allowedHosts") or record.get("allowed_hosts"),
            "allowedProviders": record.get("allowedProviders") or record.get("allowed_providers"),
            "blockCloudProviders": record.get("blockCloudProviders") or record.get("block_cloud_providers"),
            "blockExternalModels": record.get("blockExternalModels") or record.get("block_external_models"),
            "blockTelemetry": record.get("blockTelemetry") or record.get("block_telemetry"),
            "blockDocumentEgress": record.get("blockDocumentEgress") or record.get("block_document_egress"),
            "internalLogsOnly": record.get("internalLogsOnly") or record.get("internal_logs_only"),
        }
    return cognix_admin_local_only.normalize_local_only_policy(stored_policy)


def _local_only_payload_to_dict(payload: AdminLocalOnlyPolicyRequest) -> dict[str, Any]:
    values: dict[str, Any] = {}
    mapping = {
        "enabled": payload.enabled,
        "allowedHosts": payload.allowed_hosts,
        "allowedProviders": payload.allowed_providers,
        "blockCloudProviders": payload.block_cloud_providers,
        "blockExternalModels": payload.block_external_models,
        "blockTelemetry": payload.block_telemetry,
        "blockDocumentEgress": payload.block_document_egress,
        "internalLogsOnly": payload.internal_logs_only,
    }
    for key, value in mapping.items():
        if value is not None:
            values[key] = value
    return values


def _current_local_only_policy_record() -> dict[str, Any] | None:
    return cognix_db.get_local_only_policy()


def _current_local_only_policy() -> dict[str, Any]:
    return _local_only_policy_from_record(_current_local_only_policy_record())


def _build_admin_local_only_bundle() -> dict[str, Any]:
    policy_record = _current_local_only_policy_record()
    policy = _local_only_policy_from_record(policy_record)
    blocked_calls = cognix_db.list_blocked_external_calls(limit = 500)
    enforcement_plan = cognix_admin_local_only.build_enforcement_plan(
        policy = policy,
        blocked_calls = blocked_calls,
    )
    return {
        "policyRecord": policy_record,
        "policy": policy,
        "blockedCalls": blocked_calls,
        "enforcementPlan": enforcement_plan,
    }


def _build_admin_secure_model_registry_bundle() -> dict[str, Any]:
    model_registry_payload = cognix_registry.build_model_registry()
    approved_models = cognix_db.list_approved_models()
    blocked_models = cognix_db.list_blocked_models()
    security_metadata = cognix_db.list_model_security_metadata()
    secure_registry = cognix_admin_secure_model_registry.build_secure_registry_bundle(
        model_registry = model_registry_payload,
        approved_models = approved_models,
        blocked_models = blocked_models,
        metadata = security_metadata,
    )
    return {
        "modelRegistry": model_registry_payload,
        "approvedModels": approved_models,
        "blockedModels": blocked_models,
        "modelSecurityMetadata": security_metadata,
        "secureRegistry": secure_registry,
    }


def _sync_allowed_models_setting(
    *,
    model_id: str,
    current_subject: str,
    reason: str = "",
    remove: bool = False,
) -> dict[str, Any]:
    settings_bundle = _build_admin_organization_settings_bundle()
    allowed = {str(item) for item in settings_bundle["settings"].get("allowedModels", []) if str(item)}
    if remove:
        allowed.discard(model_id)
    else:
        allowed.add(model_id)
    allowed_models = sorted(allowed)
    setting = cognix_db.upsert_organization_setting(
        setting_key = "allowedModels",
        setting_value = allowed_models,
        setting_type = "secure_model_registry",
        updated_by = current_subject,
    )
    policy = cognix_db.upsert_organization_policy(
        policy_key = "models:allowed",
        policy_value = allowed_models,
        policy_type = "permission",
        permission_key = "models:allowed",
        allowed = True,
        enforced = True,
        updated_by = current_subject,
        reason = reason,
    )
    change_log = cognix_db.create_policy_change_log(
        changed_by = current_subject,
        change_type = "secure_model_registry_update",
        changed_keys = ["allowedModels"],
        before = settings_bundle["settings"],
        after = {**settings_bundle["settings"], "allowedModels": allowed_models},
        reason = reason,
    )
    return {
        "allowedModels": allowed_models,
        "setting": setting,
        "policy": policy,
        "changeLog": change_log,
    }


def _build_shared_knowledge_bundle(knowledge_base_id: str | None = None) -> dict[str, Any]:
    bases = cognix_db.list_knowledge_bases()
    documents = cognix_db.list_knowledge_documents(knowledge_base_id = knowledge_base_id) if knowledge_base_id else []
    chunks = cognix_db.list_knowledge_chunks(knowledge_base_id = knowledge_base_id) if knowledge_base_id else []
    permissions = (
        cognix_db.list_knowledge_permissions(knowledge_base_id = knowledge_base_id)
        if knowledge_base_id
        else []
    )
    return {
        "knowledgeBases": bases,
        "documents": documents,
        "chunks": chunks,
        "permissions": permissions,
    }


def _build_admin_compliance_export_bundle() -> dict[str, Any]:
    return {
        "tokenEvents": cognix_db.list_token_usage_events(limit = 5000),
        "activityEvents": cognix_db.list_user_activity_events(limit = 5000),
        "securityEvents": cognix_db.list_security_events(limit = 1000),
        "bans": cognix_db.list_bans(),
        "approvals": cognix_db.list_approval_requests(),
        "adminChatAccessLogs": cognix_db.list_admin_chat_access_logs(limit = 1000),
        "auditLogs": cognix_db.list_audit_logs(limit = 1000),
        "exports": cognix_db.list_compliance_exports(limit = 500),
        "exportJobs": cognix_db.list_export_jobs(limit = 500),
    }


def _retention_policy_from_record(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return cognix_admin_data_retention.normalize_retention_policy(
            cognix_admin_data_retention.DEFAULT_RETENTION_POLICY
        )
    stored_policy = record.get("policy") if isinstance(record.get("policy"), dict) else {}
    if not stored_policy:
        stored_policy = {
            "chatRetentionDays": record.get("chatRetentionDays") or record.get("chat_retention_days"),
            "projectArchiveMonths": record.get("projectArchiveMonths") or record.get("project_archive_months"),
            "sensitivePromptMode": record.get("sensitivePromptMode") or record.get("sensitive_prompt_mode"),
            "contentLogsEnabled": record.get("contentLogsEnabled") or record.get("content_logs_enabled"),
            "metadataOnlyMode": record.get("metadataOnlyMode") or record.get("metadata_only_mode"),
            "userExportEnabled": record.get("userExportEnabled") or record.get("user_export_enabled"),
            "userDeletionRequiresApproval": record.get("userDeletionRequiresApproval")
            or record.get("user_deletion_requires_approval"),
            "e2eeStrict": record.get("e2eeStrict") or record.get("e2ee_strict"),
        }
    return cognix_admin_data_retention.normalize_retention_policy(stored_policy)


def _retention_policy_payload_to_dict(payload: AdminDataRetentionPolicyRequest) -> dict[str, Any]:
    values: dict[str, Any] = {}
    mapping = {
        "chatRetentionDays": payload.chat_retention_days,
        "projectArchiveMonths": payload.project_archive_months,
        "sensitivePromptMode": payload.sensitive_prompt_mode,
        "contentLogsEnabled": payload.content_logs_enabled,
        "metadataOnlyMode": payload.metadata_only_mode,
        "userExportEnabled": payload.user_export_enabled,
        "userDeletionRequiresApproval": payload.user_deletion_requires_approval,
        "e2eeStrict": payload.e2ee_strict,
    }
    for key, value in mapping.items():
        if value is not None:
            values[key] = value
    return values


def _current_retention_policy_record() -> dict[str, Any] | None:
    return cognix_db.get_retention_policy()


def _current_retention_policy() -> dict[str, Any]:
    return _retention_policy_from_record(_current_retention_policy_record())


def _build_admin_data_retention_bundle() -> dict[str, Any]:
    policy_record = _current_retention_policy_record()
    policy = _retention_policy_from_record(policy_record)
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
    thread_ids = [str(thread.get("id")) for thread in threads if thread.get("id")]
    messages = list_chat_messages_for_threads(thread_ids)
    audit_logs = cognix_db.list_audit_logs(limit = 1000)
    deletion_jobs = cognix_db.list_deletion_jobs(limit = 500)
    privacy_events = cognix_db.list_privacy_events(limit = 500)
    retention_plan = cognix_admin_data_retention.build_retention_plan(
        policy = policy,
        threads = threads,
        projects = projects,
    )
    return {
        "policyRecord": policy_record,
        "policy": policy,
        "threads": threads,
        "projects": projects,
        "messages": messages,
        "auditLogs": audit_logs,
        "deletionJobs": deletion_jobs,
        "privacyEvents": privacy_events,
        "retentionPlan": retention_plan,
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
        "payload_json": "payloadJson",
        "scope_type": "scopeType",
        "scope_id": "scopeId",
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
        "link_type": "linkType",
        "source_text": "sourceText",
        "approval_request_id": "approvalRequestId",
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
        "organization_id": "organizationId",
        "skill_key": "skillKey",
        "current_version": "currentVersion",
        "allowed_roles_json": "allowedRolesJson",
        "version_history_json": "versionHistoryJson",
        "created_by": "createdBy",
        "approved_by": "approvedBy",
        "approved_at": "approvedAt",
        "skill_id": "skillId",
        "requester_username": "requesterUsername",
        "reviewer_username": "reviewerUsername",
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


def _join_registered_route_path(prefix: str, path: str) -> str:
    base = str(prefix or "").strip().rstrip("/")
    suffix = str(path or "").strip()
    if not suffix:
        return base
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"
    if suffix == "/":
        return base or "/"
    return f"{base}{suffix}" if base else suffix


def _iter_registered_api_routes(routes: Any, prefix: str = ""):
    for route in routes or []:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            include_context = getattr(route, "include_context", None)
            include_prefix = getattr(include_context, "prefix", "") if include_context is not None else ""
            yield from _iter_registered_api_routes(
                getattr(original_router, "routes", []),
                _join_registered_route_path(prefix, include_prefix),
            )
            continue

        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        nested_routes = getattr(route, "routes", None)
        if nested_routes and path:
            yield from _iter_registered_api_routes(
                nested_routes,
                _join_registered_route_path(prefix, str(path)),
            )
        if not path or not methods:
            continue
        yield (
            {
                "path": _join_registered_route_path(prefix, str(path)),
                "methods": sorted(str(method).upper() for method in methods),
            }
        )


def _registered_api_routes(request: Request) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in _iter_registered_api_routes(getattr(request.app, "routes", [])):
        records.append(record)
    return records


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


def _require_project_collaboration_access(
    project_id: str,
    username: str,
    *,
    require_edit: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    project = get_chat_project(project_id, include_all = True)
    if project is None:
        raise HTTPException(status_code = 404, detail = "Project not found")
    owner_username = str(project.get("ownerUsername") or "")
    if owner_username == username:
        return project, {
            "role": "owner",
            "permission": "owner",
            "canRead": True,
            "canComment": True,
            "canEdit": True,
        }
    collaborator = cognix_db.get_project_collaborator(project_id, username)
    if collaborator is None:
        raise HTTPException(status_code = 404, detail = "Project not found")
    permission = str(collaborator.get("permission") or "view")
    can_edit = permission == "edit"
    if require_edit and not can_edit:
        raise HTTPException(status_code = 403, detail = "Project edit permission required")
    return project, {
        "role": "collaborator",
        "permission": permission,
        "canRead": True,
        "canComment": True,
        "canEdit": can_edit,
        "shareId": collaborator.get("share_id"),
    }


def _require_owned_thread(thread_id: str, owner_username: str) -> dict[str, Any]:
    thread = get_chat_thread(
        thread_id,
        owner_username = owner_username,
        include_all = False,
    )
    if thread is None:
        raise HTTPException(status_code = 404, detail = "Thread not found")
    return thread


def _get_owned_message(thread_id: str | None, message_id: str | None, owner_username: str) -> dict[str, Any] | None:
    if not thread_id or not message_id:
        return None
    _require_owned_thread(thread_id, owner_username)
    message = get_chat_message(thread_id, message_id)
    if message is None:
        raise HTTPException(status_code = 404, detail = "Message not found")
    return message


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


@router.post("/models/install-contract")
async def model_install_contract(
    payload: ModelInstallContractRequest,
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
        execution_target = "local",
        quality_priority = None,
        offline_required = payload.offline_required,
    )
    model_id = str(payload.model_id or "")
    provider_type = str(payload.provider_type or "")
    source = str(payload.source or "")
    source_key = source.strip().lower().replace("-", "_")
    provider_key = provider_type.strip().lower().replace("-", "_")
    external_model = None
    if model_id and (
        source_key in {"hf", "huggingface", "hugging_face", "huggingface_hub"}
        or provider_key in {"hf", "huggingface", "hugging_face", "hf_transformers", "transformers"}
        or "/" in model_id and provider_key not in {"ollama", "local_gguf"}
    ):
        external_model = {
            "modelId": model_id,
            "providerType": provider_type or "hf_transformers",
            "format": "hf_transformers",
            "source": source or "huggingface_hub",
            "estimatedStorageGb": payload.estimated_storage_gb,
            "estimatedRamGb": payload.estimated_ram_gb,
            "runtimeAdapterId": "transformers",
        }
    install_contract = cognix_model_lifecycle.build_model_install_contract(
        objective = payload.objective,
        lifecycle_plan = lifecycle,
        hardware = plan["hardware"],
        external_model = external_model,
        revision = payload.revision,
        license_id = payload.license_id,
        license_accepted = payload.license_accepted,
        allow_network = payload.allow_network,
        offline_required = payload.offline_required,
        gated_model = payload.gated_model,
        confirmation_id = payload.confirmation_id,
        request_id = payload.request_id,
        project_id = payload.project_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_install_contract_built",
        resource_type = "cognix_model_install_contract",
        resource_id = str(install_contract.get("targetModel", {}).get("modelId") or "none"),
        severity = "notice" if install_contract.get("readyForDownloadReview") else "warning",
        metadata = {
            "modelLifecycleVersion": install_contract.get("modelLifecycleVersion"),
            "installContractVersion": install_contract.get("installContractVersion"),
            "contractId": install_contract.get("contractId"),
            "targetModelId": install_contract.get("targetModel", {}).get("modelId"),
            "providerType": install_contract.get("targetModel", {}).get("providerType"),
            "sourceId": install_contract.get("sourcePolicy", {}).get("sourceId"),
            "readyForDownloadReview": install_contract.get("readyForDownloadReview"),
            "readyForWorkerEnqueue": install_contract.get("readyForWorkerEnqueue"),
            "blockedWhen": install_contract.get("blockedWhen", []),
            "workerJobType": install_contract.get("workerHandoff", {}).get("jobType"),
            "sideEffects": install_contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "latestBenchmark": latest_benchmark,
        "modelRegistry": model_registry_payload,
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "modelLifecyclePlan": lifecycle,
        "modelInstallContract": install_contract,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": install_contract.get("sideEffects", {}),
        "plannerVersion": cognix_model_lifecycle.COGNIX_MODEL_INSTALL_CONTRACT_VERSION,
    }


@router.post("/models/residency-contract")
async def model_residency_contract(
    payload: ModelResidencyContractRequest,
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
        execution_target = payload.execution_target or "local",
        quality_priority = payload.quality_priority,
        offline_required = payload.offline_required,
    )
    residency_contract = cognix_model_lifecycle.build_model_residency_contract(
        objective = payload.objective,
        lifecycle_plan = lifecycle,
        cache = plan["cache"],
        runtime_snapshot = runtime,
        confirmation_id = payload.confirmation_id,
        request_id = payload.request_id,
        project_id = payload.project_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "model_residency_contract_built",
        resource_type = "cognix_model_residency_contract",
        resource_id = str(residency_contract.get("targetModel", {}).get("modelId") or "none"),
        severity = "warning" if residency_contract.get("blockedWhen") else "notice",
        metadata = {
            "modelLifecycleVersion": residency_contract.get("modelLifecycleVersion"),
            "residencyContractVersion": residency_contract.get("residencyContractVersion"),
            "contractId": residency_contract.get("contractId"),
            "targetModelId": residency_contract.get("targetModel", {}).get("modelId"),
            "status": residency_contract.get("status"),
            "readyForRuntimeMutation": residency_contract.get("readyForRuntimeMutation"),
            "loadRequired": residency_contract.get("transition", {}).get("loadRequired"),
            "unloadCandidateCount": len(residency_contract.get("transition", {}).get("unloadCandidates", [])),
            "blockedWhen": residency_contract.get("blockedWhen", []),
            "sideEffects": residency_contract.get("sideEffects", {}),
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
        "modelResidencyContract": residency_contract,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": residency_contract.get("sideEffects", {}),
        "plannerVersion": cognix_model_lifecycle.COGNIX_MODEL_RESIDENCY_CONTRACT_VERSION,
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
            "visibleTimelineVersion": thinking.get("visibleTimelineVersion"),
            "status": thinking.get("status"),
            "audience": thinking.get("audience"),
            "progress": thinking.get("progress"),
            "hiddenTechnicalFields": thinking.get("redaction", {}).get("hiddenTechnicalFields", []),
            "redactionContractVersion": thinking.get("redaction", {}).get("redactionContractVersion"),
            "verifiedNoTechnicalLeak": thinking.get("redaction", {}).get("verifiedNoTechnicalLeak"),
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


@router.post("/reflection/expert-generalist-gate")
async def response_reflection_expert_generalist_gate(
    payload: ExpertGeneralistQualityGateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    gate = cognix_response_reflection.build_expert_generalist_quality_gate(
        prompt = payload.prompt,
        expert_response = payload.expert_response,
        expert_model_id = payload.expert_model_id,
        generalist_model_id = payload.generalist_model_id,
        response_sources = payload.response_sources,
        requires_sources = payload.requires_sources,
        task_type = payload.task_type,
        domain = payload.domain,
    )
    record = cognix_db.create_response_evaluation(
        current_subject,
        evaluation = gate,
        message_id = payload.message_id,
        thread_id = payload.thread_id,
        project_id = payload.project_id,
        model_id = payload.expert_model_id,
    )
    side_effects = {
        **gate.get("sideEffects", {}),
        "evaluationWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "expert_generalist_quality_gate_built",
        resource_type = "cognix_expert_generalist_quality_gate",
        resource_id = record.get("id"),
        severity = "warning" if gate.get("summary", {}).get("secondPassRecommended") else "notice",
        metadata = {
            "qualityGateVersion": gate.get("qualityGateVersion"),
            "reflectionVersion": gate.get("reflectionVersion"),
            "status": gate.get("status"),
            "secondPassRecommended": gate.get("summary", {}).get("secondPassRecommended"),
            "recommendedAction": gate.get("summary", {}).get("recommendedAction"),
            "confidenceLabel": gate.get("summary", {}).get("confidenceLabel"),
            "expertModelId": payload.expert_model_id,
            "generalistModelId": gate.get("generalist", {}).get("modelId"),
            "messageId": payload.message_id,
            "threadId": payload.thread_id,
            "projectId": payload.project_id,
            "rawPromptIncluded": gate.get("handoffContract", {}).get("rawPromptIncluded"),
            "rawExpertResponseIncluded": gate.get("handoffContract", {}).get("rawExpertResponseIncluded"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "expertGeneralistGate": gate,
        "record": _row(record),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_response_reflection.COGNIX_EXPERT_GENERALIST_QUALITY_GATE_VERSION,
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


@router.post("/deployments/gpu-scheduler-contract")
async def gpu_scheduler_contract(
    payload: GpuSchedulerContractRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    deployment = cognix_deployment_manager.build_deployment_plan(
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
    contract = cognix_deployment_manager.build_gpu_scheduler_contract(
        username = current_subject,
        hardware = hardware,
        deployment_plan = deployment,
        gpu_nodes = payload.gpu_nodes,
        workloads = payload.workloads,
        expected_users = payload.expected_users,
        tenant_policy = payload.tenant_policy,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "gpu_scheduler_contract_built",
        resource_type = "cognix_gpu_scheduler_contract",
        resource_id = str(contract.get("target", {}).get("targetId") or "unknown"),
        severity = "notice" if contract.get("readyForAdminReview") else "warning",
        metadata = {
            "deploymentManagerVersion": contract.get("deploymentManagerVersion"),
            "schedulerContractVersion": contract.get("schedulerContractVersion"),
            "status": contract.get("status"),
            "targetId": contract.get("target", {}).get("targetId"),
            "nodeCount": contract.get("gpuPool", {}).get("nodeCount"),
            "availableNodeCount": contract.get("gpuPool", {}).get("availableNodeCount"),
            "totalRequested": contract.get("admissionPlan", {}).get("totalRequested"),
            "totalAdmitted": contract.get("admissionPlan", {}).get("totalAdmitted"),
            "blockedGateIds": contract.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": contract.get("summary", {}).get("warningGateIds", []),
            "sideEffects": contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "deploymentPlan": deployment,
        "gpuSchedulerContract": contract,
        "auditLogId": audit.get("id"),
        "sideEffects": contract.get("sideEffects", {}),
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
            "optimizationContractVersion": adapter_plan.get("optimizationContract", {}).get("contractVersion"),
            "requestedRuntimeType": adapter_plan.get("requestedRuntimeType"),
            "selectedAdapter": adapter_plan.get("selectedAdapter", {}),
            "requiredCapabilities": adapter_plan.get("requiredCapabilities", []),
            "compatibleOptimizationIds": adapter_plan.get("optimizationContract", {}).get("compatibleOptimizationIds", []),
            "blockedOptimizationIds": adapter_plan.get("optimizationContract", {}).get("blockedOptimizationIds", []),
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


@router.post("/runtime/fallback-plan")
async def runtime_fallback_plan(
    payload: RuntimeFallbackPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    plan: dict[str, Any] = {}
    if payload.runtime_adapter:
        adapter_plan = payload.runtime_adapter
    else:
        plan = cognix_orchestrator.build_execution_plan(
            payload.objective,
            current_subject = current_subject,
            project_type = payload.project_type,
            project_id = payload.project_id,
            runtime_snapshot = runtime,
            latest_benchmark_run = latest_benchmark,
            rag_available = _rag_available(),
        )
        adapter_plan = plan["runtimeAdapterPlan"]
    fallback_plan = cognix_runtime_adapter.build_runtime_fallback_plan(
        runtime_adapter_plan = adapter_plan,
        hardware = hardware,
        task_strategy = plan.get("taskStrategy"),
        rag_plan = plan.get("ragPlan"),
        fine_tuning_plan = plan.get("fineTuningPlan"),
        optimization_plan = plan.get("optimizationPlan"),
        required_capabilities = payload.required_capabilities,
        requested_optimization_ids = payload.requested_optimization_ids,
        allow_cloud_fallback = payload.allow_cloud_fallback,
        data_sensitivity = payload.data_sensitivity,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "runtime_fallback_plan_built",
        resource_type = "cognix_runtime_fallback_plan",
        resource_id = str(fallback_plan.get("primaryAdapterId") or "none"),
        severity = "warning" if fallback_plan.get("warnings") else "notice",
        metadata = {
            "runtimeFallbackContractVersion": fallback_plan.get("contractVersion"),
            "runtimeAdapterVersion": fallback_plan.get("runtimeAdapterVersion"),
            "primaryAdapterId": fallback_plan.get("primaryAdapterId"),
            "primaryRuntimeType": fallback_plan.get("primaryRuntimeType"),
            "fallbackAdapterIds": [
                item.get("adapterId") for item in fallback_plan.get("fallbackChain", []) if isinstance(item, dict)
            ],
            "requiredCapabilities": fallback_plan.get("requiredCapabilities", []),
            "requestedOptimizationIds": fallback_plan.get("requestedOptimizationIds", []),
            "allowCloudFallback": payload.allow_cloud_fallback,
            "dataSensitivity": str(payload.data_sensitivity or "internal").strip().lower(),
            "sideEffects": fallback_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "runtimeFallbackPlan": fallback_plan,
        "runtimeAdapterPlan": adapter_plan,
        "executionPolicy": plan.get("executionPolicy"),
        "auditLogId": audit.get("id"),
        "sideEffects": fallback_plan.get("sideEffects", {}),
        "plannerVersion": cognix_runtime_adapter.COGNIX_RUNTIME_FALLBACK_CONTRACT_VERSION,
    }


@router.post("/runtime/frontend-boundary-contract")
async def frontend_boundary_contract(
    payload: FrontendBoundaryContractRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    contract = cognix_security_policy.build_frontend_boundary_contract(
        endpoint = payload.endpoint,
        provider_type = payload.provider_type,
        model_id = payload.model_id,
        request_intent = payload.request_intent,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "frontend_boundary_contract_built",
        resource_type = "cognix_frontend_boundary_contract",
        resource_id = str(contract.get("endpoint", {}).get("category") or "unknown"),
        severity = "notice" if contract.get("allowedForFrontend") else "warning",
        metadata = {
            "frontendBoundaryVersion": contract.get("contractVersion"),
            "status": contract.get("status"),
            "endpoint": contract.get("endpoint", {}),
            "requestIntent": contract.get("requestIntent"),
            "providerType": contract.get("providerType"),
            "modelIdDeclared": contract.get("modelIdDeclared"),
            "allowedForFrontend": contract.get("allowedForFrontend"),
            "backendProxyRequired": contract.get("backendProxyRequired"),
            "orchestratorPlanRequired": contract.get("orchestratorPlanRequired"),
            "frontendDirectModelCallAllowed": contract.get("frontendDirectModelCallAllowed"),
            "sideEffects": contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "frontendBoundaryContract": contract,
        "auditLogId": audit.get("id"),
        "sideEffects": contract.get("sideEffects", {}),
        "plannerVersion": cognix_security_policy.COGNIX_FRONTEND_BOUNDARY_CONTRACT_VERSION,
    }


@router.post("/codex/pipeline-plan")
async def codex_pipeline_plan(
    payload: CodexPipelinePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    runtime = _current_model_cache_runtime()
    codex_run_mode = "night" if payload.night_mode is True else payload.run_mode
    plan = cognix_orchestrator.build_execution_plan(
        payload.objective,
        current_subject = current_subject,
        project_type = payload.project_type,
        project_id = payload.project_id,
        runtime_snapshot = runtime,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        codex_run_mode = codex_run_mode,
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
            "runContractVersion": pipeline.get("runContract", {}).get("contractVersion"),
            "nightModeContractVersion": pipeline.get("nightModeContractVersion"),
            "supervisionMode": pipeline.get("supervisionMode"),
            "nightModeActive": pipeline.get("nightModeActive"),
            "applicable": pipeline.get("applicable"),
            "recommendedPath": pipeline.get("recommendedPath"),
            "branchName": pipeline.get("branch", {}).get("recommendedName"),
            "qualityGates": pipeline.get("qualityGates", {}),
            "supervisionModeContract": {
                "runMode": pipeline.get("supervisionModeContract", {}).get("runMode"),
                "selectedCategory": pipeline.get("supervisionModeContract", {}).get("selectedCategory"),
                "blockedByNightMode": pipeline.get("supervisionModeContract", {}).get("blockedByNightMode"),
                "visibleProductChangeRequested": pipeline.get("supervisionModeContract", {}).get("visibleProductChangeRequested"),
                "autonomousNightWorkAllowed": pipeline.get("supervisionModeContract", {}).get("autonomousNightWorkAllowed"),
            },
            "evidenceRequirements": pipeline.get("runContract", {}).get("evidenceRequirements", []),
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


@router.post("/codex/preview-contract")
async def codex_preview_contract(
    payload: CodexPreviewContractRequest,
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
    contract = cognix_codex_pipeline.build_codex_preview_contract(
        username = current_subject,
        feature_request = payload.feature_request,
        pipeline_plan = pipeline,
        branch_name = payload.branch_name,
        test_results = payload.test_results,
        build_result = payload.build_result,
        security_scan = payload.security_scan,
        preview_target = payload.preview_target,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "codex_preview_contract_built",
        resource_type = "cognix_codex_preview_contract",
        resource_id = str(payload.project_id or contract.get("branch", {}).get("name") or "none"),
        severity = "notice" if contract.get("readyForPreviewReview") else "warning",
        metadata = {
            "codexPipelineVersion": pipeline.get("plannerVersion"),
            "previewContractVersion": contract.get("contractVersion"),
            "status": contract.get("status"),
            "readyForPreviewReview": contract.get("readyForPreviewReview"),
            "readyForPreviewStart": contract.get("readyForPreviewStart"),
            "readyForMerge": contract.get("readyForMerge"),
            "blockedGateIds": contract.get("blockedGateIds", []),
            "featureRequestKeys": contract.get("featureRequest", {}).get("metadataKeys", []),
            "qualityReports": contract.get("qualityReports", {}),
            "mergePolicy": contract.get("mergePolicy", {}),
            "sideEffects": contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "codexPipelinePlan": pipeline,
        "codexPreviewContract": contract,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": contract.get("sideEffects", {}),
        "plannerVersion": cognix_codex_pipeline.COGNIX_CODEX_PIPELINE_VERSION,
        "contractVersion": cognix_codex_pipeline.COGNIX_CODEX_PREVIEW_CONTRACT_VERSION,
    }


@router.post("/codex/night-report-contract")
async def codex_night_report_contract(
    payload: CodexNightReportContractRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    codex_run_mode = "night" if payload.night_mode is True else payload.run_mode
    contract = cognix_codex_pipeline.build_codex_night_report_contract(
        objective = payload.objective,
        run_mode = codex_run_mode,
        files_modified = payload.files_modified,
        tests_run = payload.tests_run,
        results = payload.results,
        risks_detected = payload.risks_detected,
        recommendations_for_human_validation = payload.recommendations_for_human_validation,
    )
    return {
        "username": current_subject,
        "codexNightReportContract": contract,
        "sideEffects": contract.get("sideEffects", {}),
        "plannerVersion": cognix_codex_pipeline.COGNIX_CODEX_NIGHT_REPORT_CONTRACT_VERSION,
    }


@router.post("/codex/approval-gate")
async def codex_approval_gate(
    payload: CodexApprovalGateRequest,
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
    preview_contract = cognix_codex_pipeline.build_codex_preview_contract(
        username = current_subject,
        feature_request = payload.feature_request,
        pipeline_plan = pipeline,
        branch_name = payload.branch_name,
        test_results = payload.test_results,
        build_result = payload.build_result,
        security_scan = payload.security_scan,
        preview_target = payload.preview_target,
    )
    approval_request = (
        cognix_db.get_approval_request(payload.approval_request_id)
        if payload.approval_request_id
        else None
    )
    approval_decisions = (
        cognix_db.list_approval_decisions(payload.approval_request_id)
        if payload.approval_request_id
        else []
    )
    approval_gate = cognix_codex_pipeline.build_codex_approval_gate_contract(
        username = current_subject,
        preview_contract = preview_contract,
        approval_request = approval_request,
        approval_decisions = approval_decisions,
        branch_name = payload.branch_name,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "codex_approval_gate_built",
        resource_type = "cognix_codex_approval_gate",
        resource_id = str(payload.approval_request_id or payload.project_id or "none"),
        severity = "notice" if approval_gate.get("readyForMergeReview") else "warning",
        metadata = {
            "previewContractVersion": preview_contract.get("contractVersion"),
            "approvalGateVersion": approval_gate.get("contractVersion"),
            "status": approval_gate.get("status"),
            "readyForMergeReview": approval_gate.get("readyForMergeReview"),
            "readyForMerge": approval_gate.get("readyForMerge"),
            "blockedGateIds": approval_gate.get("blockedGateIds", []),
            "approvalRequest": approval_gate.get("approvalRequest", {}),
            "approvalDecision": approval_gate.get("approvalDecision", {}),
            "branch": approval_gate.get("branch", {}),
            "mergePolicy": approval_gate.get("mergePolicy", {}),
            "sideEffects": approval_gate.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "codexPipelinePlan": pipeline,
        "codexPreviewContract": preview_contract,
        "codexApprovalGate": approval_gate,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": approval_gate.get("sideEffects", {}),
        "plannerVersion": cognix_codex_pipeline.COGNIX_CODEX_PIPELINE_VERSION,
        "contractVersion": cognix_codex_pipeline.COGNIX_CODEX_APPROVAL_GATE_VERSION,
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
        rag_connector_sync_plan = payload.rag_connector_sync_plan,
        rag_indexing_plan = rag_indexing_plan,
        cloud_handoff_plan = cloud_handoff_plan,
        tool_execution_handoff = payload.tool_execution_handoff,
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
        "ragConnectorSyncPlan": payload.rag_connector_sync_plan or {},
        "toolExecutionHandoff": payload.tool_execution_handoff or {},
        "ragIndexingPlan": rag_indexing_plan,
        "cloudHandoffPlan": cloud_handoff_plan,
        "workerJobSpecPlan": spec_plan,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": spec_plan.get("sideEffects", {}),
        "plannerVersion": cognix_worker_queue.COGNIX_WORKER_QUEUE_VERSION,
    }


@router.post("/workers/enqueue-contract")
async def worker_enqueue_contract(
    payload: WorkerEnqueueContractRequest,
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
        rag_connector_sync_plan = payload.rag_connector_sync_plan,
        rag_indexing_plan = rag_indexing_plan,
        cloud_handoff_plan = cloud_handoff_plan,
        tool_execution_handoff = payload.tool_execution_handoff,
        preload_plan = plan["preloadPlan"],
    )
    enqueue_contract = cognix_worker_queue.build_worker_enqueue_contract(
        job_spec_plan = spec_plan,
        confirmation_id = payload.confirmation_id,
        confirmation_ids = payload.confirmation_ids,
        request_id = payload.request_id,
    )
    audit_side_effects = {
        **enqueue_contract.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "worker_enqueue_contract_built",
        resource_type = "cognix_worker_enqueue_contract",
        resource_id = str(enqueue_contract.get("contractId") or payload.project_id or "worker_enqueue_contract"),
        severity = "notice" if enqueue_contract.get("readyForQueueReview") else "warning",
        metadata = {
            "workerQueueVersion": enqueue_contract.get("workerQueueVersion"),
            "jobSpecVersion": enqueue_contract.get("jobSpecVersion"),
            "enqueueContractVersion": enqueue_contract.get("enqueueContractVersion"),
            "contractId": enqueue_contract.get("contractId"),
            "status": enqueue_contract.get("status"),
            "readyForQueueReview": enqueue_contract.get("readyForQueueReview"),
            "readyForJobEnqueue": enqueue_contract.get("readyForJobEnqueue"),
            "jobCount": enqueue_contract.get("summary", {}).get("jobCount"),
            "queueIds": enqueue_contract.get("summary", {}).get("queueIds", []),
            "blockedWhen": enqueue_contract.get("blockedWhen", []),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "workerQueuePlan": plan["workerQueuePlan"],
        "ragConnectorSyncPlan": payload.rag_connector_sync_plan or {},
        "toolExecutionHandoff": payload.tool_execution_handoff or {},
        "ragIndexingPlan": rag_indexing_plan,
        "cloudHandoffPlan": cloud_handoff_plan,
        "workerJobSpecPlan": spec_plan,
        "workerEnqueueContract": enqueue_contract,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "sideEffects": audit_side_effects,
        "plannerVersion": cognix_worker_queue.COGNIX_WORKER_ENQUEUE_CONTRACT_VERSION,
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


@router.get("/modules/service-topology")
async def module_service_topology(
    edition: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    topology = cognix_module_registry.build_module_service_topology(edition = edition)
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "module_service_topology_built",
        resource_type = "cognix_module_service_topology",
        resource_id = str(topology.get("serviceTopologyVersion")),
        severity = "notice" if topology.get("coverage", {}).get("ready") else "warning",
        metadata = {
            "serviceTopologyVersion": topology.get("serviceTopologyVersion"),
            "moduleRegistryVersion": topology.get("moduleRegistryVersion"),
            "manifestBundleVersion": topology.get("manifestBundleVersion"),
            "editionFilter": topology.get("editionFilter"),
            "serviceCount": topology.get("summary", {}).get("serviceCount"),
            "coveredServiceCount": topology.get("summary", {}).get("coveredServiceCount"),
            "missingServiceIds": topology.get("coverage", {}).get("missingServiceIds", []),
            "coverageReady": topology.get("coverage", {}).get("ready"),
            "sideEffects": topology.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "serviceTopology": topology,
        "auditLogId": audit.get("id"),
        "sideEffects": topology.get("sideEffects", {}),
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


@router.get("/integrations/roadmap-readiness")
async def integrations_roadmap_readiness(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    readiness = cognix_integration_manager.build_connector_roadmap_readiness(
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    return {
        "username": current_subject,
        "connectorRoadmapReadiness": readiness,
        "sideEffects": readiness.get("sideEffects", {}),
        "plannerVersion": cognix_integration_manager.COGNIX_CONNECTOR_ROADMAP_READINESS_VERSION,
    }


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
            "activationContractVersion": plan.get("activationContractVersion"),
            "toolId": plan.get("toolId"),
            "connector": plan.get("connector"),
            "status": plan.get("status"),
            "allowedToActivate": plan.get("allowedToActivate"),
            "humanApprovalRequired": plan.get("humanApprovalRequired"),
            "activationContract": {
                "readyForActivation": plan.get("activationContract", {}).get("readyForActivation"),
                "nextRequiredGate": plan.get("activationContract", {}).get("nextRequiredGate"),
                "blockedWhen": plan.get("activationContract", {}).get("blockedWhen", []),
            },
            "missingPermissions": plan.get("integration", {}).get("missingPermissions", []),
            "nextActionIds": [
                item.get("id") for item in plan.get("nextActions", []) if isinstance(item, dict)
            ],
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    plan["auditLogId"] = audit.get("id")
    return plan


@router.post("/integrations/preflight-contract")
async def integration_preflight_contract(
    payload: IntegrationPreflightContractRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    contract = cognix_integration_manager.build_connector_preflight_contract(
        tool_id = payload.tool_id,
        username = current_subject,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "integration_preflight_contract_built",
        resource_type = "cognix_connector_preflight_contract",
        resource_id = str(payload.tool_id),
        severity = "notice" if contract.get("readyForActivationRequest") else "warning",
        metadata = {
            "integrationManagerVersion": cognix_integration_manager.COGNIX_INTEGRATION_MANAGER_VERSION,
            "preflightContractVersion": contract.get("contractVersion"),
            "toolId": contract.get("toolId"),
            "connector": contract.get("connector"),
            "status": contract.get("status"),
            "readyForActivationRequest": contract.get("readyForActivationRequest"),
            "readyForConnectorActivation": contract.get("readyForConnectorActivation"),
            "nextRequiredGate": contract.get("nextRequiredGate"),
            "secretContract": {
                "required": contract.get("secretContract", {}).get("required"),
                "secretSourceNames": contract.get("secretContract", {}).get("secretSourceNames", []),
                "actualSecretValuesIncluded": contract.get("secretContract", {}).get("actualSecretValuesIncluded"),
            },
            "blockedGateIds": contract.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": contract.get("summary", {}).get("warningGateIds", []),
            "sideEffects": contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "preflightContract": contract,
        "auditLogId": audit.get("id"),
        "sideEffects": contract.get("sideEffects", {}),
    }


@router.post("/integrations/secret-rotation-contract")
async def integration_secret_rotation_contract(
    payload: IntegrationSecretRotationContractRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    contract = cognix_integration_manager.build_secret_rotation_contract(
        tool_id = payload.tool_id,
        username = current_subject,
        rotation_reason = payload.rotation_reason,
        current_secret_age_days = payload.current_secret_age_days,
        last_rotation_at = payload.last_rotation_at,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    audit_side_effects = {
        **contract.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "integration_secret_rotation_contract_built",
        resource_type = "cognix_secret_rotation_contract",
        resource_id = str(payload.tool_id),
        severity = "warning" if contract.get("rotationRecommended") else "notice",
        metadata = {
            "secretRotationContractVersion": contract.get("secretRotationContractVersion"),
            "integrationManagerVersion": contract.get("integrationManagerVersion"),
            "preflightContractVersion": contract.get("preflightContractVersion"),
            "toolId": contract.get("toolId"),
            "connector": contract.get("connector"),
            "status": contract.get("status"),
            "readyForRotationRequest": contract.get("readyForRotationRequest"),
            "readyForSecretRotation": contract.get("readyForSecretRotation"),
            "rotationRecommended": contract.get("rotationRecommended"),
            "secretSourceCount": contract.get("summary", {}).get("secretSourceCount"),
            "blockedGateIds": contract.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": contract.get("summary", {}).get("warningGateIds", []),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "secretRotationContract": contract,
        "auditLogId": audit.get("id"),
        "sideEffects": audit_side_effects,
        "plannerVersion": cognix_integration_manager.COGNIX_SECRET_ROTATION_CONTRACT_VERSION,
    }


@router.post("/integrations/activation-contract")
async def integration_activation_contract(
    payload: IntegrationActivationContractRequest,
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
    contract = plan.get("activationContract", {})
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "integration_activation_contract_built",
        resource_type = "cognix_integration_activation_contract",
        resource_id = str(payload.tool_id),
        severity = "notice" if contract.get("allowedToPrepareActivation") else "warning",
        metadata = {
            "integrationManagerVersion": plan.get("integrationManagerVersion"),
            "activationContractVersion": contract.get("contractVersion"),
            "toolId": plan.get("toolId"),
            "connector": plan.get("connector"),
            "status": plan.get("status"),
            "readyForActivation": contract.get("readyForActivation"),
            "nextRequiredGate": contract.get("nextRequiredGate"),
            "blockedWhen": contract.get("blockedWhen", []),
            "sideEffects": contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "integrationPlan": plan,
        "activationContract": contract,
        "auditLogId": audit.get("id"),
        "sideEffects": contract.get("sideEffects", {}),
    }


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


def _skill_marketplace_manifest_from_payload(payload: SkillMarketplacePublishRequest) -> dict[str, Any]:
    manifest = dict(payload.skill_manifest or {})
    if payload.display_name is not None:
        manifest["displayName"] = payload.display_name
    if payload.description is not None:
        manifest["description"] = payload.description
    if payload.category is not None:
        manifest["category"] = payload.category
    if payload.version is not None:
        manifest["version"] = payload.version
    if payload.instructions is not None:
        manifest["instructions"] = payload.instructions
    if payload.allowed_roles is not None:
        manifest["allowedRoles"] = payload.allowed_roles
    return manifest


def _builtin_shared_skill(skill_id: str) -> dict[str, Any] | None:
    for skill in cognix_skill_marketplace.build_builtin_catalog():
        if str(skill.get("id") or "") == skill_id:
            return skill
    return None


@router.get("/skills/marketplace/blueprint")
async def skill_marketplace_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_skill_marketplace.build_skill_marketplace_blueprint()
    return {
        "username": current_subject,
        "skillMarketplaceBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_skill_marketplace.COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
    }


@router.get("/skills/marketplace")
async def skill_marketplace_catalog(
    organization_id: str = "local",
    include_disabled: bool = False,
    limit: int = 120,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    shared_skills = cognix_db.list_shared_skills(
        organization_id = organization_id,
        include_disabled = include_disabled and is_admin,
        limit = limit,
    )
    approvals = cognix_db.list_skill_approvals(limit = 200) if is_admin else []
    usage_logs = (
        cognix_db.list_skill_usage_logs(limit = 200)
        if is_admin
        else cognix_db.list_skill_usage_logs(username = current_subject, limit = 80)
    )
    catalog = cognix_skill_marketplace.build_marketplace_catalog(
        shared_skills = [_row(item) for item in shared_skills],
        approvals = [_row(item) for item in approvals],
        usage_logs = [_row(item) for item in usage_logs],
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "skill_marketplace_catalog_built",
        resource_type = "cognix_skill_marketplace",
        resource_id = organization_id,
        severity = "notice",
        metadata = {
            "skillMarketplaceVersion": catalog.get("skillMarketplaceVersion"),
            "skillCount": catalog.get("summary", {}).get("skillCount"),
            "pendingApprovalCount": catalog.get("summary", {}).get("pendingApprovalCount"),
            "sideEffects": catalog.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "skillMarketplaceCatalog": catalog,
        "auditLogId": audit.get("id"),
        "sideEffects": catalog.get("sideEffects", {}),
        "plannerVersion": cognix_skill_marketplace.COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
    }


@router.post("/skills/marketplace/skills")
async def publish_shared_skill(
    payload: SkillMarketplacePublishRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    plan = cognix_skill_marketplace.build_skill_publish_plan(
        username = current_subject,
        skill_manifest = _skill_marketplace_manifest_from_payload(payload),
        organization_id = payload.organization_id,
        is_admin = is_admin,
    )
    stored_skill = (
        cognix_db.create_shared_skill(
            current_subject,
            plan = plan,
            organization_id = payload.organization_id,
        )
        if payload.store_skill
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "skillWrite": stored_skill is not None,
        "approvalWrite": stored_skill is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "shared_skill_publish_planned",
        resource_type = "shared_skill",
        resource_id = str((stored_skill or {}).get("id") or plan.get("skill", {}).get("skillKey") or "skill"),
        severity = "warning" if plan.get("status") != "approved" else "notice",
        metadata = {
            "skillMarketplaceVersion": plan.get("skillMarketplaceVersion"),
            "skillKey": plan.get("skill", {}).get("skillKey"),
            "status": plan.get("status"),
            "autoApprovedByAdmin": plan.get("approvalPlan", {}).get("autoApprovedByAdmin"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "skillPublishPlan": plan,
        "sharedSkill": _row(stored_skill) if stored_skill else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_skill_marketplace.COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
    }


@router.patch("/skills/marketplace/skills/{skill_id}/approval")
async def decide_shared_skill_approval(
    skill_id: str,
    payload: SkillMarketplaceApprovalRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if not auth_storage.is_admin(current_subject):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required.")
    skill = cognix_db.get_shared_skill(skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shared skill not found.")
    plan = cognix_skill_marketplace.build_skill_approval_plan(
        skill = _row(skill),
        reviewer_username = current_subject,
        status = payload.status,
        admin_note = payload.admin_note,
    )
    updated = cognix_db.decide_shared_skill(
        skill_id,
        reviewer_username = current_subject,
        status = payload.status,
        admin_note = payload.admin_note,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "shared_skill_approval_decided",
        resource_type = "shared_skill",
        resource_id = skill_id,
        severity = "notice" if payload.status == "approved" else "warning",
        metadata = {
            "skillApprovalVersion": plan.get("skillApprovalVersion"),
            "status": payload.status,
            "sideEffects": {**plan.get("sideEffects", {}), "approvalWrite": True, "skillWrite": True, "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "skillApprovalPlan": plan,
        "sharedSkill": _row(updated) if updated else None,
        "auditLogId": audit.get("id"),
        "sideEffects": {**plan.get("sideEffects", {}), "approvalWrite": True, "skillWrite": True, "auditWrite": True},
        "plannerVersion": cognix_skill_marketplace.COGNIX_SKILL_APPROVAL_SERVICE_VERSION,
    }


@router.post("/skills/marketplace/usage")
async def record_shared_skill_usage(
    payload: SkillMarketplaceUsageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    skill = cognix_db.get_shared_skill(payload.skill_id) or _builtin_shared_skill(payload.skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shared skill not found.")
    profile = auth_storage.get_user_profile(current_subject) or {}
    user_role = str(profile.get("role") or "user")
    usage_plan = cognix_skill_marketplace.build_skill_usage_plan(
        username = current_subject,
        skill = _row(skill),
        action = payload.action,
        user_role = user_role,
    )
    if not usage_plan.get("allowed"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "message": "Shared skill usage blocked.",
                "blockedReasons": usage_plan.get("blockedReasons", []),
            },
        )
    usage_log = cognix_db.record_skill_usage(
        current_subject,
        skill_id = payload.skill_id,
        action = payload.action,
        project_id = payload.project_id,
        version = str(skill.get("currentVersion") or skill.get("current_version") or ""),
        metadata = {"usagePlan": usage_plan, **(payload.metadata or {})},
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "shared_skill_usage_logged",
        resource_type = "shared_skill",
        resource_id = payload.skill_id,
        severity = "notice",
        metadata = {
            "skillMarketplaceVersion": usage_plan.get("skillMarketplaceVersion"),
            "action": payload.action,
            "projectId": payload.project_id,
            "sideEffects": {**usage_plan.get("sideEffects", {}), "usageLogWrite": True, "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "skillUsagePlan": usage_plan,
        "usageLog": _row(usage_log),
        "auditLogId": audit.get("id"),
        "sideEffects": {**usage_plan.get("sideEffects", {}), "usageLogWrite": True, "auditWrite": True},
        "plannerVersion": cognix_skill_marketplace.COGNIX_SKILL_MARKETPLACE_SERVICE_VERSION,
    }


def _project_skill_config_from_payload(payload: ProjectSkillRequest) -> dict[str, Any]:
    config = dict(payload.skill_config or {})
    if payload.display_name is not None:
        config["displayName"] = payload.display_name
    if payload.description is not None:
        config["description"] = payload.description
    if payload.objective is not None:
        config["objective"] = payload.objective
    if payload.instructions is not None:
        config["instructions"] = payload.instructions
    if payload.model_id is not None:
        config["modelId"] = payload.model_id
    if payload.allowed_tools is not None:
        config["allowedTools"] = payload.allowed_tools
    if payload.limits is not None:
        config["limits"] = payload.limits
    if payload.examples is not None:
        config["examples"] = payload.examples
    return config


def _project_directive_config_from_payload(payload: ProjectDirectiveRequest) -> dict[str, Any]:
    config = dict(payload.directive_config or {})
    if payload.content is not None:
        config["content"] = payload.content
    if payload.directive_type is not None:
        config["directiveType"] = payload.directive_type
    config["priority"] = payload.priority
    config["scope"] = payload.scope
    if payload.model_id is not None:
        config["modelId"] = payload.model_id
    if payload.source_level is not None:
        config["sourceLevel"] = payload.source_level
    return config


@router.get("/projects/{project_id}/skills/blueprint")
async def project_skills_blueprint(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    blueprint = cognix_project_skills_directives.build_project_skill_blueprint()
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectSkillBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_project_skills_directives.COGNIX_SKILL_MANAGER_VERSION,
    }


@router.get("/projects/{project_id}/skills")
async def list_project_skills(
    project_id: str,
    include_disabled: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    skills = cognix_db.list_project_skills(
        current_subject,
        project_id = project_id,
        include_disabled = include_disabled,
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "skills": [_row(item) for item in skills],
        "count": len(skills),
    }


@router.post("/projects/{project_id}/skills")
async def create_project_skill(
    project_id: str,
    payload: ProjectSkillRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    plan = cognix_project_skills_directives.build_project_skill_plan(
        username = current_subject,
        project_id = project_id,
        skill_config = _project_skill_config_from_payload(payload),
        granted_permissions = _granted_permission_keys(current_subject),
        model_id = payload.model_id,
    )
    if not plan.get("validation", {}).get("valid"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Invalid project skill.", "missingFields": plan.get("validation", {}).get("missingFields", [])},
        )
    stored_skill = (
        cognix_db.create_project_skill(
            current_subject,
            project_id = project_id,
            plan = plan,
            model_id = payload.model_id,
        )
        if payload.store_skill
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "skillWrite": stored_skill is not None,
        "versionWrite": stored_skill is not None,
        "projectBindingWrite": stored_skill is not None,
        "modelBindingWrite": stored_skill is not None and bool((plan.get("skill") or {}).get("modelId")),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_skill_binding_planned",
        resource_type = "project_skill",
        resource_id = project_id,
        severity = "warning" if plan.get("binding", {}).get("blockedTools") else "notice",
        metadata = {
            "skillManagerVersion": plan.get("skillManagerVersion"),
            "projectId": project_id,
            "skillKey": plan.get("skill", {}).get("skillKey"),
            "blockedTools": plan.get("binding", {}).get("blockedTools"),
            "permissionEscalationAllowed": False,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectSkillPlan": plan,
        "projectSkill": _row(stored_skill) if stored_skill else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_project_skills_directives.COGNIX_SKILL_MANAGER_VERSION,
    }


@router.post("/projects/{project_id}/skills/injection-plan")
async def project_skill_injection_plan(
    project_id: str,
    payload: ProjectSkillInjectionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    skills = cognix_db.list_project_skills(current_subject, project_id = project_id)
    plan = cognix_project_skills_directives.build_skill_injection_plan(
        username = current_subject,
        project_id = project_id,
        skills = [_row(item) for item in skills],
        model_id = payload.model_id,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_skill_injection_plan_built",
        resource_type = "project_skill",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "runtimeBinderVersion": plan.get("runtimeBinderVersion"),
            "selectedSkillCount": plan.get("summary", {}).get("selectedSkillCount"),
            "permissionEscalationAllowed": False,
            "sideEffects": {**plan.get("sideEffects", {}), "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "skillInjectionPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": {**plan.get("sideEffects", {}), "auditWrite": True},
        "plannerVersion": cognix_project_skills_directives.COGNIX_SKILL_RUNTIME_BINDER_VERSION,
    }


@router.get("/projects/{project_id}/directives/blueprint")
async def project_directives_blueprint(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    blueprint = cognix_project_skills_directives.build_project_directive_blueprint()
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectDirectiveBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_project_skills_directives.COGNIX_DIRECTIVE_MANAGER_VERSION,
    }


@router.get("/projects/{project_id}/directives")
async def list_project_directives(
    project_id: str,
    include_disabled: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    directives = cognix_db.list_project_directives(
        current_subject,
        project_id = project_id,
        include_disabled = include_disabled,
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "directives": [_row(item) for item in directives],
        "count": len(directives),
    }


@router.post("/projects/{project_id}/directives")
async def create_project_directive(
    project_id: str,
    payload: ProjectDirectiveRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    plan = cognix_project_skills_directives.build_project_directive_plan(
        username = current_subject,
        project_id = project_id,
        directive_config = _project_directive_config_from_payload(payload),
        model_id = payload.model_id,
    )
    if not plan.get("validation", {}).get("valid"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Invalid project directive.", "missingFields": plan.get("validation", {}).get("missingFields", [])},
        )
    stored_directive = (
        cognix_db.create_project_directive(
            current_subject,
            project_id = project_id,
            plan = plan,
            model_id = payload.model_id,
        )
        if payload.store_directive
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "directiveWrite": stored_directive is not None,
        "projectBindingWrite": stored_directive is not None,
        "modelBindingWrite": stored_directive is not None and bool((plan.get("directive") or {}).get("modelId")),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_directive_planned",
        resource_type = "project_directive",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "directiveManagerVersion": plan.get("directiveManagerVersion"),
            "projectId": project_id,
            "directiveType": plan.get("directive", {}).get("directiveType"),
            "sourceLevel": plan.get("directive", {}).get("sourceLevel"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectDirectivePlan": plan,
        "projectDirective": _row(stored_directive) if stored_directive else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_project_skills_directives.COGNIX_DIRECTIVE_MANAGER_VERSION,
    }


@router.post("/projects/{project_id}/directives/compile")
async def compile_project_directives(
    project_id: str,
    payload: ProjectDirectiveCompileRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    directives = cognix_db.list_project_directives(current_subject, project_id = project_id)
    plan = cognix_project_skills_directives.compile_project_directives(
        username = current_subject,
        project_id = project_id,
        directives = [_row(item) for item in directives],
        model_id = payload.model_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_directives_compiled",
        resource_type = "project_directive",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "directiveCompilerVersion": plan.get("directiveCompilerVersion"),
            "compiledDirectiveCount": plan.get("summary", {}).get("compiledDirectiveCount"),
            "sideEffects": {**plan.get("sideEffects", {}), "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "directiveCompilePlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": {**plan.get("sideEffects", {}), "auditWrite": True},
        "plannerVersion": cognix_project_skills_directives.COGNIX_DIRECTIVE_COMPILER_VERSION,
    }


@router.get("/projects/{project_id}/realtime/blueprint")
async def project_realtime_blueprint(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    blueprint = cognix_realtime_collaboration.build_realtime_collaboration_blueprint()
    return {
        "username": current_subject,
        "projectId": project_id,
        "project": _row(project),
        "access": access,
        "realtimeCollaborationBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_realtime_collaboration.COGNIX_REALTIME_COLLABORATION_VERSION,
    }


@router.post("/projects/{project_id}/realtime/presence")
async def update_project_presence(
    project_id: str,
    payload: RealtimePresenceRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    plan = cognix_realtime_collaboration.build_presence_plan(
        username = current_subject,
        project = project,
        client_id = payload.client_id,
        status = payload.status,
        cursor = payload.cursor,
        activity = payload.activity,
        ttl_seconds = payload.ttl_seconds,
        metadata = payload.metadata,
    )
    presence = cognix_db.upsert_project_presence(current_subject, project_id = project_id, plan = plan)
    event_plan = cognix_realtime_collaboration.build_collaboration_event_plan(
        username = current_subject,
        project = project,
        event_type = "presence_updated",
        resource_type = "project",
        resource_id = project_id,
        payload = {"clientId": plan.get("presence", {}).get("clientId"), "status": plan.get("presence", {}).get("status")},
    )
    event = cognix_db.create_collaboration_event(current_subject, project_id = project_id, plan = event_plan)
    side_effects = {**plan.get("sideEffects", {}), "presenceWrite": True, "eventWrite": True, "auditWrite": True}
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_presence_updated",
        resource_type = "presence_session",
        resource_id = str(presence.get("id") or project_id),
        severity = "notice",
        metadata = {
            "presenceServiceVersion": plan.get("presenceServiceVersion"),
            "projectId": project_id,
            "access": access,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "presencePlan": plan,
        "presence": _row(presence),
        "collaborationEvent": _row(event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_realtime_collaboration.COGNIX_PRESENCE_SERVICE_VERSION,
    }


@router.get("/projects/{project_id}/realtime/presence")
async def list_project_presence(
    project_id: str,
    active_only: bool = True,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    sessions = cognix_db.list_project_presence_sessions(project_id, active_only = active_only, limit = limit)
    return {
        "username": current_subject,
        "projectId": project_id,
        "project": _row(project),
        "access": access,
        "presenceSessions": _rows(sessions),
        "count": len(sessions),
        "sideEffects": {"presenceWrite": False, "eventWrite": False, "modelLoad": False, "generation": False},
        "plannerVersion": cognix_realtime_collaboration.COGNIX_PRESENCE_SERVICE_VERSION,
    }


@router.post("/projects/{project_id}/comments")
async def create_project_comment(
    project_id: str,
    payload: ProjectCommentRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    plan = cognix_realtime_collaboration.build_comment_plan(
        username = current_subject,
        project = project,
        body = payload.body,
        target = payload.target,
        parent_comment_id = payload.parent_comment_id,
        metadata = payload.metadata,
    )
    if not plan.get("valid"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Comment body is required.")
    comment = (
        cognix_db.create_project_comment(current_subject, project_id = project_id, plan = plan)
        if payload.store_comment
        else None
    )
    event_plan = cognix_realtime_collaboration.build_collaboration_event_plan(
        username = current_subject,
        project = project,
        event_type = "comment_created",
        resource_type = "project_comment",
        resource_id = str((comment or {}).get("id") or project_id),
        payload = {"commentId": (comment or {}).get("id"), "target": plan.get("comment", {}).get("target")},
    )
    event = cognix_db.create_collaboration_event(current_subject, project_id = project_id, plan = event_plan)
    side_effects = {**plan.get("sideEffects", {}), "commentWrite": comment is not None, "eventWrite": True, "auditWrite": True}
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_comment_created",
        resource_type = "project_comment",
        resource_id = str((comment or {}).get("id") or project_id),
        severity = "notice",
        metadata = {
            "commentServiceVersion": plan.get("commentServiceVersion"),
            "projectId": project_id,
            "access": access,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "projectCommentPlan": plan,
        "projectComment": _row(comment) if comment else None,
        "collaborationEvent": _row(event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_realtime_collaboration.COGNIX_COMMENT_SERVICE_VERSION,
    }


@router.get("/projects/{project_id}/comments")
async def list_project_comments(
    project_id: str,
    status_filter: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    comments = cognix_db.list_project_comments(project_id, status = status_filter, limit = limit)
    return {
        "username": current_subject,
        "projectId": project_id,
        "project": _row(project),
        "access": access,
        "projectComments": _rows(comments),
        "count": len(comments),
        "sideEffects": {"commentWrite": False, "eventWrite": False, "modelLoad": False, "generation": False},
        "plannerVersion": cognix_realtime_collaboration.COGNIX_COMMENT_SERVICE_VERSION,
    }


@router.post("/projects/{project_id}/comments/{comment_id}/resolve")
async def resolve_project_comment(
    project_id: str,
    comment_id: str,
    payload: ProjectCommentResolutionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    comment = cognix_db.get_project_comment(comment_id, project_id = project_id)
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project comment not found.")
    if not access.get("canEdit") and comment.get("username") != current_subject:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Comment owner or project edit permission required.")
    plan = cognix_realtime_collaboration.build_comment_resolution_plan(
        username = current_subject,
        project = project,
        comment = comment,
        status = payload.status,
        note = payload.note,
    )
    updated = cognix_db.resolve_project_comment(
        current_subject,
        project_id = project_id,
        comment_id = comment_id,
        plan = plan,
    )
    event_plan = cognix_realtime_collaboration.build_collaboration_event_plan(
        username = current_subject,
        project = project,
        event_type = "comment_resolved" if payload.status == "resolved" else "comment_updated",
        resource_type = "project_comment",
        resource_id = comment_id,
        payload = {"commentId": comment_id, "status": payload.status},
    )
    event = cognix_db.create_collaboration_event(current_subject, project_id = project_id, plan = event_plan)
    side_effects = {**plan.get("sideEffects", {}), "commentStatusWrite": updated is not None, "eventWrite": True, "auditWrite": True}
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_comment_resolution_planned",
        resource_type = "project_comment",
        resource_id = comment_id,
        severity = "notice",
        metadata = {
            "commentServiceVersion": plan.get("commentServiceVersion"),
            "projectId": project_id,
            "nextStatus": payload.status,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "commentResolutionPlan": plan,
        "projectComment": _row(updated) if updated else None,
        "collaborationEvent": _row(event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_realtime_collaboration.COGNIX_COMMENT_SERVICE_VERSION,
    }


@router.post("/projects/{project_id}/collaboration/events")
async def create_project_collaboration_event(
    project_id: str,
    payload: CollaborationEventRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    plan = cognix_realtime_collaboration.build_collaboration_event_plan(
        username = current_subject,
        project = project,
        event_type = payload.event_type,
        resource_type = payload.resource_type,
        resource_id = payload.resource_id,
        payload = payload.payload,
        metadata = payload.metadata,
    )
    event = (
        cognix_db.create_collaboration_event(current_subject, project_id = project_id, plan = plan)
        if payload.store_event
        else None
    )
    side_effects = {**plan.get("sideEffects", {}), "eventWrite": event is not None, "auditWrite": True}
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_collaboration_event_planned",
        resource_type = "collaboration_event",
        resource_id = str((event or {}).get("id") or project_id),
        severity = "notice",
        metadata = {
            "realtimeCollaborationVersion": plan.get("realtimeCollaborationVersion"),
            "projectId": project_id,
            "eventType": plan.get("event", {}).get("type"),
            "access": access,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "collaborationEventPlan": plan,
        "collaborationEvent": _row(event) if event else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_realtime_collaboration.COGNIX_REALTIME_COLLABORATION_VERSION,
    }


@router.get("/projects/{project_id}/collaboration/events")
async def list_project_collaboration_events(
    project_id: str,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject)
    events = cognix_db.list_collaboration_events(project_id, limit = limit)
    return {
        "username": current_subject,
        "projectId": project_id,
        "project": _row(project),
        "access": access,
        "collaborationEvents": _rows(events),
        "count": len(events),
        "sideEffects": {"eventWrite": False, "modelLoad": False, "generation": False},
        "plannerVersion": cognix_realtime_collaboration.COGNIX_REALTIME_COLLABORATION_VERSION,
    }


@router.post("/projects/{project_id}/collaboration/conflict-plan")
async def project_collaboration_conflict_plan(
    project_id: str,
    payload: ConflictResolutionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project, access = _require_project_collaboration_access(project_id, current_subject, require_edit = True)
    plan = cognix_realtime_collaboration.build_conflict_resolution_plan(
        username = current_subject,
        project = project,
        resource_type = payload.resource_type,
        resource_id = payload.resource_id,
        base_revision = payload.base_revision,
        local_revision = payload.local_revision,
        remote_revision = payload.remote_revision,
        strategy = payload.strategy,
        changes = payload.changes,
    )
    event_plan = cognix_realtime_collaboration.build_collaboration_event_plan(
        username = current_subject,
        project = project,
        event_type = "conflict_detected",
        resource_type = payload.resource_type,
        resource_id = payload.resource_id,
        payload = {"conflict": plan.get("conflict"), "resolutionPolicy": plan.get("resolutionPolicy")},
    )
    event = cognix_db.create_collaboration_event(current_subject, project_id = project_id, plan = event_plan)
    side_effects = {**plan.get("sideEffects", {}), "eventWrite": True, "auditWrite": True}
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_conflict_resolution_planned",
        resource_type = payload.resource_type,
        resource_id = payload.resource_id,
        severity = "warning" if plan.get("resolutionPolicy", {}).get("requiresHumanReview") else "notice",
        metadata = {
            "conflictResolverVersion": plan.get("conflictResolverVersion"),
            "projectId": project_id,
            "access": access,
            "automaticOverwriteAllowed": False,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "projectId": project_id,
        "conflictResolutionPlan": plan,
        "collaborationEvent": _row(event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_realtime_collaboration.COGNIX_CONFLICT_RESOLVER_VERSION,
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

    execution_boundary_contract = plan.get("executionBoundaryContract")
    if not isinstance(execution_boundary_contract, dict):
        execution_boundary_contract = {}
    request_boundary = execution_boundary_contract.get("requestBoundary")
    if not isinstance(request_boundary, dict):
        request_boundary = {}
    executor_boundary = execution_boundary_contract.get("executorBoundary")
    if not isinstance(executor_boundary, dict):
        executor_boundary = {}
    audit_boundary = execution_boundary_contract.get("auditBoundary")
    if not isinstance(audit_boundary, dict):
        audit_boundary = {}
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
            "executionBoundaryContractVersion": plan.get("executionBoundaryContractVersion"),
            "toolId": plan.get("toolId"),
            "actionId": plan.get("actionId"),
            "status": plan.get("status"),
            "riskLevel": plan.get("riskLevel"),
            "requiresConfirmation": plan.get("requiresConfirmation"),
            "guardrails": plan.get("guardrails", {}),
            "secretPolicyVersion": plan.get("secretPolicy", {}).get("policyVersion"),
            "secretPolicy": {
                "requiresSecret": plan.get("secretPolicy", {}).get("requiresSecret"),
                "secretReadAllowedHere": plan.get("secretPolicy", {}).get("secretReadAllowedHere"),
                "rawSecretExposureAllowed": plan.get("secretPolicy", {}).get("rawSecretExposureAllowed"),
                "auditSecretValueAllowed": plan.get("secretPolicy", {}).get("auditSecretValueAllowed"),
            },
            "contract": {
                "allowedToPrepare": plan.get("executionContract", {}).get("allowedToPrepare"),
                "readyForExecution": plan.get("executionContract", {}).get("readyForExecution"),
                "nextRequiredGate": plan.get("executionContract", {}).get("nextRequiredGate"),
                "blockedWhen": plan.get("executionContract", {}).get("blockedWhen", []),
            },
            "executionBoundary": {
                "status": execution_boundary_contract.get("status"),
                "contractVersion": execution_boundary_contract.get("contractVersion"),
                "toolExecutionAllowedHere": request_boundary.get("toolExecutionAllowedHere"),
                "jobEnqueueAllowedHere": executor_boundary.get("jobEnqueueAllowedHere"),
                "rawPayloadAuditAllowed": audit_boundary.get("auditLogRawPayloadAllowed"),
            },
            "missingPermissions": plan.get("missingPermissions", []),
            "rateLimit": rate_limit,
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    plan["auditLogId"] = audit.get("id")
    return plan


@router.post("/tools/calculator/evaluate")
async def tool_calculator_evaluate(
    payload: ToolCalculatorEvaluateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "calculator",
        action_id = "evaluate_expression",
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
                action = "tool_calculator_evaluated",
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

    result: dict[str, Any] | None = None
    error: str | None = None
    if plan.get("allowed") and (rate_limit is None or rate_limit.get("allowed")):
        try:
            result = cognix_native_tools.evaluate_calculator_expression(
                payload.expression,
                precision = payload.precision,
            )
        except (ValueError, ArithmeticError, OverflowError) as exc:
            error = str(exc)
    side_effects = {
        "calculatorEvaluation": result is not None,
        "modelLoad": False,
        "generation": False,
        "networkToolCall": False,
        "externalWrite": False,
        "secretRead": False,
        "secretWrite": False,
        "auditWrite": True,
    }
    status = "evaluated" if result is not None else ("blocked_invalid_expression" if error else "blocked_by_tool_guard")
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_calculator_evaluated",
        resource_type = "cognix_native_calculator",
        resource_id = str(result.get("expressionHash") if result else "blocked"),
        severity = "notice" if result is not None else "warning",
        metadata = {
            "calculatorVersion": (
                result.get("calculatorVersion")
                if result
                else cognix_native_tools.COGNIX_NATIVE_CALCULATOR_VERSION
            ),
            "toolRegistryVersion": plan.get("registryVersion"),
            "toolId": plan.get("toolId"),
            "actionId": plan.get("actionId"),
            "status": status,
            "expressionHash": result.get("expressionHash") if result else None,
            "expressionLength": len(payload.expression),
            "precision": payload.precision,
            "rateLimit": rate_limit,
            "errorType": type(error).__name__ if error else None,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "status": status,
        "toolPlan": plan,
        "calculatorResult": result,
        "error": error,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_native_tools.COGNIX_NATIVE_CALCULATOR_VERSION,
    }


@router.post("/tools/physics/solve")
async def tool_physics_solve(
    payload: ToolPhysicsSolveRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "physics-solver",
        action_id = "solve_formula",
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
                action = "tool_physics_solver_solved",
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

    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    if plan.get("allowed") and (rate_limit is None or rate_limit.get("allowed")):
        try:
            result = cognix_native_tools.solve_physics_formula(
                formula_id = payload.formula_id,
                variables = payload.variables,
                precision = payload.precision,
            )
        except (ValueError, ArithmeticError, OverflowError) as exc:
            error = str(exc)
            error_type = type(exc).__name__
    side_effects = {
        "physicsSolve": result is not None,
        "modelLoad": False,
        "generation": False,
        "networkToolCall": False,
        "externalWrite": False,
        "secretRead": False,
        "secretWrite": False,
        "auditWrite": True,
    }
    status_value = "solved" if result is not None else ("blocked_invalid_formula" if error else "blocked_by_tool_guard")
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_physics_solver_solved",
        resource_type = "cognix_native_physics_solver",
        resource_id = str(result.get("formulaHash") if result else "blocked"),
        severity = "notice" if result is not None else "warning",
        metadata = {
            "physicsSolverVersion": (
                result.get("physicsSolverVersion")
                if result
                else cognix_native_tools.COGNIX_NATIVE_PHYSICS_SOLVER_VERSION
            ),
            "toolRegistryVersion": plan.get("registryVersion"),
            "toolId": plan.get("toolId"),
            "actionId": plan.get("actionId"),
            "status": status_value,
            "formulaId": result.get("formulaId") if result else payload.formula_id,
            "targetVariable": result.get("targetVariable") if result else None,
            "providedVariableIds": result.get("providedVariableIds") if result else sorted(payload.variables),
            "formulaHash": result.get("formulaHash") if result else None,
            "precision": payload.precision,
            "rateLimit": rate_limit,
            "errorType": error_type,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "status": status_value,
        "toolPlan": plan,
        "physicsResult": result,
        "error": error,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_native_tools.COGNIX_NATIVE_PHYSICS_SOLVER_VERSION,
    }


@router.post("/tools/latex/render")
async def tool_latex_render(
    payload: ToolLatexRenderRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "latex-renderer",
        action_id = "render_math",
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
                action = "tool_latex_rendered",
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

    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    if plan.get("allowed") and (rate_limit is None or rate_limit.get("allowed")):
        try:
            result = cognix_native_tools.render_latex_expression(
                source = payload.source,
                display_mode = payload.display_mode,
                context = payload.context,
            )
        except ValueError as exc:
            error = str(exc)
            error_type = type(exc).__name__
    side_effects = {
        "latexRenderPacket": result is not None,
        "modelLoad": False,
        "generation": False,
        "networkToolCall": False,
        "fileRead": False,
        "fileWrite": False,
        "externalWrite": False,
        "secretRead": False,
        "secretWrite": False,
        "auditWrite": True,
    }
    status_value = "render_packet_ready" if result is not None else ("blocked_invalid_latex" if error else "blocked_by_tool_guard")
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_latex_rendered",
        resource_type = "cognix_native_latex_renderer",
        resource_id = str(result.get("sourceHash") if result else "blocked"),
        severity = "notice" if result is not None else "warning",
        metadata = {
            "latexRendererVersion": (
                result.get("latexRendererVersion")
                if result
                else cognix_native_tools.COGNIX_NATIVE_LATEX_RENDERER_VERSION
            ),
            "toolRegistryVersion": plan.get("registryVersion"),
            "toolId": plan.get("toolId"),
            "actionId": plan.get("actionId"),
            "status": status_value,
            "sourceHash": result.get("sourceHash") if result else None,
            "sourceLength": result.get("sourceLength") if result else len(payload.source),
            "commandCount": result.get("commandCount") if result else None,
            "commands": result.get("commands") if result else [],
            "environments": result.get("environments") if result else [],
            "displayMode": payload.display_mode,
            "context": payload.context,
            "renderTarget": result.get("renderTarget") if result else None,
            "rateLimit": rate_limit,
            "errorType": error_type,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "status": status_value,
        "toolPlan": plan,
        "latexResult": result,
        "error": error,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_native_tools.COGNIX_NATIVE_LATEX_RENDERER_VERSION,
    }


@router.post("/tools/execution-handoff")
async def tool_execution_handoff(
    payload: ToolExecutionHandoffRequest,
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
                action = "tool_execution_handoff_built",
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
    handoff = cognix_tool_registry.build_tool_execution_handoff(
        plan = plan,
        confirmation_id = payload.confirmation_id,
        sandbox_run_id = payload.sandbox_run_id,
        request_id = payload.request_id,
    )
    audit_side_effects = {
        **handoff.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "tool_execution_handoff_built",
        resource_type = "cognix_tool_execution_handoff",
        resource_id = str(handoff.get("handoffId") or f"{payload.tool_id}:{payload.action_id}"),
        severity = "notice" if handoff.get("readyForExecutorReview") else "warning",
        metadata = {
            "toolRegistryVersion": plan.get("registryVersion"),
            "executionContractVersion": handoff.get("executionContractVersion"),
            "executionBoundaryContractVersion": handoff.get("executionBoundaryContractVersion"),
            "handoffVersion": handoff.get("handoffVersion"),
            "handoffId": handoff.get("handoffId"),
            "toolId": handoff.get("toolId"),
            "actionId": handoff.get("actionId"),
            "connector": handoff.get("connector"),
            "status": handoff.get("status"),
            "readyForExecutorReview": handoff.get("readyForExecutorReview"),
            "readyForJobEnqueue": handoff.get("readyForJobEnqueue"),
            "executionBoundary": handoff.get("executionBoundary", {}),
            "blockedWhen": handoff.get("blockedWhen", []),
            "gateIds": [
                item.get("id") for item in handoff.get("gates", []) if isinstance(item, dict)
            ],
            "secretValuesIncluded": handoff.get("executorInput", {}).get("secretValuesIncluded"),
            "rawPayloadIncluded": handoff.get("dataBoundary", {}).get("rawPayloadIncluded"),
            "rateLimit": rate_limit,
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "toolPlan": plan,
        "executionHandoff": handoff,
        "auditLogId": audit.get("id"),
        "sideEffects": audit_side_effects,
        "plannerVersion": cognix_tool_registry.TOOL_EXECUTION_HANDOFF_VERSION,
    }


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


@router.post("/models/cache/pressure-plan")
async def model_cache_pressure_plan(
    payload: ModelCachePressurePlanRequest,
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
    pressure_plan = cognix_cache_manager.build_cache_pressure_plan(
        hardware,
        cache_state = cache,
        project_id = payload.project_id,
    )
    proposed_evictions = [
        item.get("modelId")
        for item in pressure_plan.get("proposedEvictions", [])
        if isinstance(item, dict)
    ]
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "cache_pressure_plan_built",
        resource_type = "cognix_cache_pressure_plan",
        resource_id = str(payload.project_id or current_subject),
        severity = "warning" if pressure_plan.get("status") != "healthy" else "notice",
        metadata = {
            "managerVersion": pressure_plan.get("managerVersion"),
            "pressurePlanVersion": pressure_plan.get("pressurePlanVersion"),
            "status": pressure_plan.get("status"),
            "proposedEvictionCount": len(proposed_evictions),
            "proposedEvictions": proposed_evictions,
            "memoryPressureStatus": pressure_plan.get("memoryPressure", {}).get("status"),
            "overCapacityCount": pressure_plan.get("capacityPressure", {}).get("overCapacityCount"),
            "idleCandidateCount": pressure_plan.get("idlePressure", {}).get("idleCandidateCount"),
            "sideEffects": pressure_plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "hardware": hardware,
        "runtimeError": runtime.get("error"),
        "cache": cache,
        "pressurePlan": pressure_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": pressure_plan.get("sideEffects", {}),
        "plannerVersion": pressure_plan.get("pressurePlanVersion"),
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
    preload_queue_contract = preload_plan.get("preloadQueueContract", {})
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
            "loadPredictionVersion": preload_plan.get("loadPrediction", {}).get("predictionVersion"),
            "loadPredictionStatus": preload_plan.get("loadPrediction", {}).get("status"),
            "warmupContractVersion": preload_plan.get("warmupContract", {}).get("contractVersion"),
            "warmupNextRequiredGate": preload_plan.get("warmupContract", {}).get("nextRequiredGate"),
            "preloadQueueContractVersion": preload_queue_contract.get("contractVersion"),
            "preloadQueueStatus": preload_queue_contract.get("status"),
            "preloadQueueCandidateCount": preload_queue_contract.get("candidateCount"),
            "preloadQueueDepth": preload_queue_contract.get("queueDepth"),
            "preloadQueueWillLoadNow": preload_queue_contract.get("executionGate", {}).get("willLoadNow"),
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


@router.post("/fine-tuning/dataset/validate")
async def fine_tuning_dataset_validation(
    payload: FineTuningDatasetValidationRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    validation = cognix_fine_tuning_planner.build_dataset_validation_plan(
        username = current_subject,
        dataset = payload.dataset,
        objective = payload.objective,
        project_id = payload.project_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "fine_tuning_dataset_validated",
        resource_type = "cognix_dataset_validation_plan",
        resource_id = str(validation.get("dataset", {}).get("sourceRef") or payload.project_id or current_subject),
        severity = "warning" if validation.get("status") != "ready" else "notice",
        metadata = {
            "plannerVersion": validation.get("plannerVersion"),
            "validationPlanVersion": validation.get("validationPlanVersion"),
            "status": validation.get("status"),
            "qualityScore": validation.get("quality", {}).get("score"),
            "qualityLabel": validation.get("quality", {}).get("label"),
            "blockedGateIds": validation.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": validation.get("summary", {}).get("warningGateIds", []),
            "readyForFineTuning": validation.get("summary", {}).get("readyForFineTuning"),
            "requiresHumanReview": validation.get("summary", {}).get("requiresHumanReview"),
            "sideEffects": validation.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "datasetValidationPlan": validation,
        "auditLogId": audit.get("id"),
        "sideEffects": validation.get("sideEffects", {}),
    }


@router.post("/fine-tuning/evaluation-plan")
async def fine_tuning_evaluation_plan(
    payload: FineTuningEvaluationPlanRequest,
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
    dataset_validation = cognix_fine_tuning_planner.build_dataset_validation_plan(
        username = current_subject,
        dataset = payload.dataset,
        objective = payload.objective,
        project_id = payload.project_id,
    )
    evaluation = cognix_fine_tuning_planner.build_fine_tuning_evaluation_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        fine_tuning_plan = tuning_plan,
        dataset_validation_plan = dataset_validation,
        training_artifact = payload.training_artifact,
        baseline_model = payload.baseline_model,
        requested_metrics = payload.requested_metrics,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "fine_tuning_evaluation_plan_built",
        resource_type = "cognix_fine_tuning_evaluation_plan",
        resource_id = str(
            evaluation.get("trainingArtifact", {}).get("artifactId")
            or evaluation.get("baseline", {}).get("modelId")
            or payload.project_id
            or current_subject
        ),
        severity = "notice" if evaluation.get("readyForEvaluationReview") else "warning",
        metadata = {
            "plannerVersion": evaluation.get("plannerVersion"),
            "evaluationPlanVersion": evaluation.get("evaluationPlanVersion"),
            "status": evaluation.get("status"),
            "readyForEvaluationReview": evaluation.get("readyForEvaluationReview"),
            "readyForLibraryRegistration": evaluation.get("libraryRegistrationPlan", {}).get("readyForLibraryRegistration"),
            "artifactId": evaluation.get("trainingArtifact", {}).get("artifactId"),
            "adapterRef": evaluation.get("trainingArtifact", {}).get("adapterRef"),
            "baselineModelId": evaluation.get("baseline", {}).get("modelId"),
            "metricIds": evaluation.get("summary", {}).get("metricIds", []),
            "blockedGateIds": evaluation.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": evaluation.get("summary", {}).get("warningGateIds", []),
            "sideEffects": evaluation.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "runtimeError": runtime.get("error"),
        "classification": plan["classification"],
        "taskStrategy": plan["taskStrategy"],
        "fineTuningPlan": tuning_plan,
        "datasetValidationPlan": dataset_validation,
        "fineTuningEvaluationPlan": evaluation,
        "executionPolicy": plan["executionPolicy"],
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_fine_tuning_planner.COGNIX_FINE_TUNING_PLANNER_VERSION,
        "sideEffects": evaluation.get("sideEffects", {}),
    }


@router.post("/fine-tuning/distillation-plan")
async def fine_tuning_distillation_plan(
    payload: FineTuningDistillationPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    user_profile = auth_storage.get_user_profile(current_subject) or {}
    user_plan = _effective_training_plan(current_subject, user_profile)
    plan = cognix_distillation_planner.build_distillation_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        teacher_model = payload.teacher_model,
        student_model = payload.student_model,
        dataset = payload.dataset,
        hardware = cognix_hardware.get_hardware_profile(),
        user_plan = user_plan,
        target_id = payload.target_id,
    )
    audit_side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "fine_tuning_distillation_plan_built",
        resource_type = "cognix_distillation_plan",
        resource_id = str(plan.get("planId") or payload.project_id or current_subject),
        severity = "notice" if plan.get("readyForApproval") else "warning",
        metadata = {
            "plannerVersion": plan.get("plannerVersion"),
            "teacherStudentContractVersion": plan.get("teacherStudentContractVersion"),
            "evaluationContractVersion": plan.get("evaluationContractVersion"),
            "status": plan.get("status"),
            "readyForApproval": plan.get("readyForApproval"),
            "teacherModelId": plan.get("teacher", {}).get("modelId"),
            "studentModelId": plan.get("student", {}).get("modelId"),
            "datasetStatus": plan.get("dataset", {}).get("status"),
            "recommendedMethod": plan.get("summary", {}).get("recommendedMethod"),
            "recommendedTargetId": plan.get("summary", {}).get("recommendedTargetId"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": plan.get("summary", {}).get("warningGateIds", []),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "distillationPlan": plan,
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_distillation_planner.COGNIX_DISTILLATION_PLANNER_VERSION,
        "sideEffects": audit_side_effects,
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


@router.post("/rag/connector-sync-plan")
async def rag_connector_sync_plan(
    payload: RagConnectorSyncPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    is_admin = auth_storage.is_admin(current_subject)
    has_developer_mode = cognix_db.user_has_permission(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
    )
    plan = cognix_rag_planner.build_rag_connector_sync_plan(
        username = current_subject,
        connector_id = payload.connector_id,
        project_id = payload.project_id,
        objective = payload.objective,
        source_filters = payload.source_filters or {},
        max_documents = payload.max_documents,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = _granted_permission_keys(current_subject),
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "rag_connector_sync_plan_built",
        resource_type = "cognix_rag_connector_sync_plan",
        resource_id = str(payload.project_id or plan.get("connectorId") or payload.connector_id),
        severity = "notice" if plan.get("readyForSyncRequest") else "warning",
        metadata = {
            "connectorSyncContractVersion": plan.get("connectorSyncContractVersion"),
            "plannerVersion": plan.get("plannerVersion"),
            "sourceRegistryVersion": plan.get("sourceRegistryVersion"),
            "connectorId": plan.get("connectorId"),
            "status": plan.get("status"),
            "readyForSyncRequest": plan.get("readyForSyncRequest"),
            "readyForIndexing": plan.get("readyForIndexing"),
            "sourceFilterKeys": plan.get("syncScope", {}).get("sourceFilterKeys", []),
            "maxDocuments": plan.get("syncScope", {}).get("maxDocuments"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": plan.get("summary", {}).get("warningGateIds", []),
            "missingPermissionCount": plan.get("summary", {}).get("missingPermissionCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "connectorSyncPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": plan.get("plannerVersion"),
        "connectorSyncContractVersion": plan.get("connectorSyncContractVersion"),
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


@router.post("/rag/compression-plan")
async def rag_compression_plan(
    payload: RagCompressionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_rag_compression.build_rag_compression_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        chunks = payload.chunks,
        target_tokens = payload.target_tokens,
        max_chunks = payload.max_chunks,
        require_citations = payload.require_citations,
    )
    audit_side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "rag_compression_plan_built",
        resource_type = "cognix_rag_compression_plan",
        resource_id = str(payload.project_id or plan.get("summary", {}).get("status") or "general"),
        severity = "notice" if plan.get("readyForInjection") else "warning",
        metadata = {
            "ragCompressionVersion": plan.get("ragCompressionVersion"),
            "citationRetentionVersion": plan.get("citationRetentionVersion"),
            "extractiveRankerVersion": plan.get("extractiveRankerVersion"),
            "status": plan.get("status"),
            "readyForInjection": plan.get("readyForInjection"),
            "inputChunkCount": plan.get("summary", {}).get("inputChunkCount"),
            "selectedChunkCount": plan.get("summary", {}).get("selectedChunkCount"),
            "citationCount": plan.get("summary", {}).get("citationCount"),
            "missingCitationCount": plan.get("citationContract", {}).get("missingCitationCount"),
            "reductionRatio": plan.get("summary", {}).get("reductionRatio"),
            "selectedChunkIds": plan.get("selectedChunkIds"),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "ragCompressionPlan": plan,
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_rag_compression.COGNIX_RAG_COMPRESSION_VERSION,
        "sideEffects": audit_side_effects,
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
            "benchmarkEvidenceVersion": registry.get("benchmarkEvidence", {}).get("contractVersion"),
            "benchmarkEvidenceStatus": registry.get("benchmarkEvidence", {}).get("status"),
            "benchmarkEvidenceReady": registry.get("benchmarkEvidence", {}).get("readyForExperiment"),
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
            "benchmarkEvidenceVersion": optimization.get("benchmarkEvidence", {}).get("contractVersion"),
            "benchmarkEvidenceStatus": optimization.get("benchmarkEvidence", {}).get("status"),
            "benchmarkEvidenceReady": optimization.get("benchmarkEvidence", {}).get("readyForExperiment"),
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
            "benchmarkEvidenceVersion": plan.get("benchmarkEvidence", {}).get("contractVersion"),
            "benchmarkEvidenceStatus": plan.get("benchmarkEvidence", {}).get("status"),
            "benchmarkEvidenceReady": plan.get("benchmarkEvidence", {}).get("readyForExperiment"),
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


@router.post("/optimizations/application-contract")
async def optimization_application_contract(
    payload: OptimizationApplicationContractRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    recommendation_payload = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )
    recommendation = recommendation_payload["recommendation"]
    optimization = cognix_optimization_planner.build_optimization_plan(
        hardware = hardware,
        recommendation = recommendation,
        latest_benchmark_run = latest_benchmark,
    )
    experiment = cognix_optimization_planner.build_optimization_experiment_plan(
        objective = payload.objective,
        hardware = hardware,
        recommendation = recommendation,
        latest_benchmark_run = latest_benchmark,
        requested_optimizations = payload.requested_optimizations,
    )
    contract = cognix_optimization_planner.build_optimization_application_contract(
        objective = payload.objective,
        experiment_plan = experiment,
        optimization_plan = optimization,
        confirmation_id = payload.confirmation_id,
        rollback_plan_id = payload.rollback_plan_id,
        request_id = payload.request_id,
        project_id = payload.project_id,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "optimization_application_contract_built",
        resource_type = "cognix_optimization_application_contract",
        resource_id = str(payload.project_id or contract.get("contractId") or "general"),
        severity = "warning" if contract.get("blockedGateIds") else "notice",
        metadata = {
            "applicationContractVersion": contract.get("applicationContractVersion"),
            "experimentPlanVersion": contract.get("experimentPlanVersion"),
            "contractId": contract.get("contractId"),
            "status": contract.get("status"),
            "readyForExecutorReview": contract.get("readyForExecutorReview"),
            "readyForRuntimeMutation": contract.get("readyForRuntimeMutation"),
            "selectedOptimizationIds": contract.get("selectedOptimizationIds", []),
            "readyOptimizationIds": contract.get("readyOptimizationIds", []),
            "blockedGateIds": contract.get("blockedGateIds", []),
            "benchmarkEvidenceStatus": contract.get("benchmarkEvidence", {}).get("status"),
            "sideEffects": contract.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "optimizationPlan": optimization,
        "optimizationExperimentPlan": experiment,
        "optimizationApplicationContract": contract,
        "auditLogId": audit.get("id"),
        "sideEffects": contract.get("sideEffects", {}),
        "plannerVersion": cognix_optimization_planner.COGNIX_OPTIMIZATION_APPLICATION_CONTRACT_VERSION,
    }


@router.post("/optimizations/speculative-decoding-plan")
async def speculative_decoding_plan(
    payload: SpeculativeDecodingPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_speculative_decoding.build_speculative_decoding_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        runtime_adapter = payload.runtime_adapter,
        target_model = payload.target_model,
        draft_model = payload.draft_model,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        max_quality_delta = payload.max_quality_delta,
    )
    audit_side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "speculative_decoding_plan_built",
        resource_type = "cognix_speculative_decoding_plan",
        resource_id = str(plan.get("modelPair", {}).get("targetModelId") or payload.project_id or "general"),
        severity = "notice" if plan.get("readyForExperiment") else "warning",
        metadata = {
            "contractVersion": plan.get("contractVersion"),
            "preflightVersion": plan.get("preflightVersion"),
            "status": plan.get("status"),
            "readyForExperiment": plan.get("readyForExperiment"),
            "readyForActivation": plan.get("readyForActivation"),
            "runtimeType": plan.get("runtime", {}).get("runtimeType"),
            "targetModelId": plan.get("modelPair", {}).get("targetModelId"),
            "draftModelId": plan.get("modelPair", {}).get("draftModelId"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds"),
            "benchmarkStatus": plan.get("benchmarkEvidence", {}).get("status"),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "speculativeDecodingPlan": plan,
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_speculative_decoding.COGNIX_SPECULATIVE_DECODING_CONTRACT_VERSION,
        "sideEffects": audit_side_effects,
    }


@router.post("/optimizations/kv-cache-plan")
async def kv_cache_eviction_plan(
    payload: KvCacheEvictionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_kv_cache.build_kv_cache_eviction_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        context_blocks = payload.context_blocks,
        context_plan = payload.context_plan,
        runtime_adapter = payload.runtime_adapter,
        model = payload.model,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        target_token_budget = payload.target_token_budget,
    )
    audit_side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "kv_cache_eviction_plan_built",
        resource_type = "cognix_kv_cache_eviction_plan",
        resource_id = str(payload.project_id or plan.get("runtime", {}).get("runtimeType") or "general"),
        severity = "notice" if plan.get("readyForPolicyReview") else "warning",
        metadata = {
            "kvCacheEvictionPlanVersion": plan.get("kvCacheEvictionPlanVersion"),
            "policyContractVersion": plan.get("policyContractVersion"),
            "contextRetentionPolicyVersion": plan.get("contextRetentionPolicyVersion"),
            "status": plan.get("status"),
            "readyForPolicyReview": plan.get("readyForPolicyReview"),
            "readyForActivation": plan.get("readyForActivation"),
            "policyMode": plan.get("policyMode"),
            "runtimeType": plan.get("runtime", {}).get("runtimeType"),
            "directKvControlSupported": plan.get("runtime", {}).get("directKvControlSupported"),
            "blockCount": plan.get("retentionPlan", {}).get("summary", {}).get("blockCount"),
            "estimatedTokenReduction": plan.get("summary", {}).get("estimatedTokenReduction"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": plan.get("summary", {}).get("warningGateIds", []),
            "benchmarkStatus": plan.get("benchmarkEvidence", {}).get("status"),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "kvCacheEvictionPlan": plan,
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_kv_cache.COGNIX_KV_CACHE_EVICTION_PLAN_VERSION,
        "sideEffects": audit_side_effects,
    }


@router.post("/optimizations/prompt-cache-plan")
async def prompt_cache_plan(
    payload: PromptCachePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_prompt_cache.build_prompt_cache_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        runtime_adapter = payload.runtime_adapter,
        model = payload.model,
        context_plan = payload.context_plan,
        prompt_segments = payload.prompt_segments,
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        sensitivity_level = payload.sensitivity_level,
        expected_reuse_count = payload.expected_reuse_count,
    )
    audit_side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "prompt_cache_plan_built",
        resource_type = "cognix_prompt_cache_plan",
        resource_id = str(plan.get("prefixPlan", {}).get("cacheKeyHash") or payload.project_id or "general"),
        severity = "notice" if plan.get("readyForExperiment") else "warning",
        metadata = {
            "promptCachePlanVersion": plan.get("promptCachePlanVersion"),
            "policyVersion": plan.get("policyVersion"),
            "runtimeContractVersion": plan.get("runtimeContractVersion"),
            "status": plan.get("status"),
            "readyForExperiment": plan.get("readyForExperiment"),
            "readyForActivation": plan.get("readyForActivation"),
            "runtimeType": plan.get("runtime", {}).get("runtimeType"),
            "promptCachingSupported": plan.get("runtime", {}).get("promptCachingSupported"),
            "stablePrefixTokens": plan.get("prefixPlan", {}).get("stablePrefixTokens"),
            "sensitivityLevel": plan.get("sensitivity", {}).get("level"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": plan.get("summary", {}).get("warningGateIds", []),
            "benchmarkStatus": plan.get("benchmarkEvidence", {}).get("status"),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "promptCachePlan": plan,
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_prompt_cache.COGNIX_PROMPT_CACHE_PLAN_VERSION,
        "sideEffects": audit_side_effects,
    }


@router.post("/optimizations/batching-plan")
async def batching_plan(
    payload: BatchingPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_batching.build_batching_plan(
        username = current_subject,
        objective = payload.objective,
        project_id = payload.project_id,
        runtime_adapter = payload.runtime_adapter,
        deployment_target = payload.deployment_target,
        hardware = cognix_hardware.get_hardware_profile(),
        latest_benchmark_run = cognix_db.get_latest_benchmark_run(current_subject),
        concurrent_users = payload.concurrent_users,
        request_rate_per_minute = payload.request_rate_per_minute,
        average_prompt_tokens = payload.average_prompt_tokens,
        average_completion_tokens = payload.average_completion_tokens,
        target_latency_ms = payload.target_latency_ms,
    )
    audit_side_effects = {
        **plan.get("sideEffects", {}),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "batching_plan_built",
        resource_type = "cognix_batching_plan",
        resource_id = str(payload.project_id or plan.get("runtime", {}).get("runtimeType") or "general"),
        severity = "notice" if plan.get("readyForExperiment") else "warning",
        metadata = {
            "batchingPlanVersion": plan.get("batchingPlanVersion"),
            "microBatchPolicyVersion": plan.get("microBatchPolicyVersion"),
            "throughputExperimentContractVersion": plan.get("throughputExperimentContractVersion"),
            "status": plan.get("status"),
            "readyForExperiment": plan.get("readyForExperiment"),
            "readyForActivation": plan.get("readyForActivation"),
            "runtimeType": plan.get("runtime", {}).get("runtimeType"),
            "deploymentTarget": plan.get("runtime", {}).get("deploymentTarget"),
            "directBatchingSupported": plan.get("runtime", {}).get("directBatchingSupported"),
            "concurrentUsers": plan.get("workload", {}).get("concurrentUsers"),
            "targetTokensPerSecond": plan.get("workload", {}).get("targetTokensPerSecond"),
            "recommendedQueueId": plan.get("summary", {}).get("recommendedQueueId"),
            "recommendedJobType": plan.get("summary", {}).get("recommendedJobType"),
            "blockedGateIds": plan.get("summary", {}).get("blockedGateIds", []),
            "warningGateIds": plan.get("summary", {}).get("warningGateIds", []),
            "benchmarkStatus": plan.get("benchmarkEvidence", {}).get("status"),
            "sideEffects": audit_side_effects,
        },
    )
    return {
        "username": current_subject,
        "batchingPlan": plan,
        "auditLogId": audit.get("id"),
        "plannerVersion": cognix_batching.COGNIX_BATCHING_PLAN_VERSION,
        "sideEffects": audit_side_effects,
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
    budget_guard = (
        cognix_cost_optimizer.build_execution_budget_guard(
            username = current_subject,
            cost_plan = plan,
            quota_matrix = _build_admin_limits_bundle()["matrix"],
        )
        if payload.enforce_quotas
        else None
    )
    if budget_guard is not None:
        plan = {
            **plan,
            "budgetGuard": budget_guard,
            "guardedDecision": budget_guard.get("guardedDecision"),
            "policy": {
                **plan.get("policy", {}),
                "quotaGuardApplied": True,
                "quotaUsageRecordedHere": False,
            },
            "sideEffects": {
                **plan.get("sideEffects", {}),
                "quotaUsageWrite": False,
            },
        }
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
        "quotaUsageWrite": False,
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
            "guardedSelectedProviderId": plan.get("guardedDecision", {}).get("selectedProviderId"),
            "guardedSelectedExecutionTarget": plan.get("guardedDecision", {}).get("selectedExecutionTarget"),
            "budgetGuardStatus": (budget_guard or {}).get("status"),
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


@router.get("/notifications/blueprint")
async def notifications_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    notifications = cognix_db.list_notifications(current_subject, limit = 200)
    preferences = cognix_db.list_notification_preferences(current_subject)
    blueprint = cognix_notifications.build_notification_blueprint(
        notifications = notifications,
        preferences = preferences,
    )
    return {
        "notificationsBlueprint": blueprint,
        "plannerVersion": cognix_notifications.COGNIX_NOTIFICATION_SERVICE_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/notifications")
async def my_notifications(
    unread_only: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    notifications = cognix_db.list_notifications(current_subject, unread_only = unread_only, limit = 200)
    preferences = cognix_db.list_notification_preferences(current_subject)
    blueprint = cognix_notifications.build_notification_blueprint(
        notifications = notifications,
        preferences = preferences,
    )
    return {
        "notifications": _rows(notifications),
        "preferences": _rows(preferences),
        "summary": blueprint["summary"],
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_notifications.COGNIX_NOTIFICATION_SERVICE_VERSION,
    }


@router.patch("/notifications/{notification_id}/read")
async def mark_my_notification_read(
    notification_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    notification = cognix_db.mark_notification_read(notification_id, username = current_subject)
    if notification is None:
        raise HTTPException(status_code = 404, detail = "Notification not found")
    return {
        "notification": _row(notification),
        "sideEffects": {"notificationWrite": True},
        "plannerVersion": cognix_notifications.COGNIX_NOTIFICATION_SERVICE_VERSION,
    }


@router.get("/notifications/preferences")
async def my_notification_preferences(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    preferences = cognix_db.list_notification_preferences(current_subject)
    return {
        "preferences": _rows(preferences),
        "plannerVersion": cognix_notifications.COGNIX_USER_NOTIFICATION_PREFERENCES_VERSION,
    }


@router.put("/notifications/preferences/{notification_type}")
async def update_my_notification_preference(
    notification_type: str,
    payload: NotificationPreferenceRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    preference = cognix_db.upsert_notification_preference(
        username = current_subject,
        notification_type = notification_type,
        enabled = payload.enabled,
        channels = payload.channels,
        quiet_hours = payload.quiet_hours,
        updated_by = current_subject,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "notification_preference_updated",
        resource_type = "notification_preference",
        resource_id = str(preference.get("id") or notification_type),
        severity = "notice",
        metadata = {
            "notificationType": preference.get("notificationType"),
            "enabled": preference.get("enabled"),
            "channels": preference.get("channels"),
        },
    )
    return {
        "preference": _row(preference),
        "auditLogId": audit.get("id"),
        "sideEffects": {"preferenceWrite": True, "auditWrite": True},
        "plannerVersion": cognix_notifications.COGNIX_USER_NOTIFICATION_PREFERENCES_VERSION,
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
    emitted = _emit_approval_notifications(request, event = "approval_requested", actor_username = current_subject)
    return {
        "request": _row(request),
        "notification": _row(emitted["notification"]),
        "adminAlert": _row(emitted["adminAlert"]),
        "sideEffects": {"requestWrite": True, "notificationWrite": True, "adminAlertWrite": True},
    }


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
    emitted = _emit_approval_notifications(request, event = "approval_requested", actor_username = current_subject)
    return {
        "request": _row(request),
        "policy": policy,
        "notification": _row(emitted["notification"]),
        "adminAlert": _row(emitted["adminAlert"]),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "requestWrite": True,
            "notificationWrite": True,
            "adminAlertWrite": True,
            "auditWrite": True,
        },
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


@router.post("/prompt-compression/conversation-summary-plan")
async def conversation_summary_plan(
    payload: ConversationSummaryPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_prompt_compression.build_conversation_summary_plan(
        username = current_subject,
        messages = payload.messages,
        objective = payload.objective,
        target_tokens = payload.target_tokens,
        recent_message_limit = payload.recent_message_limit,
        project_id = payload.project_id,
    )
    stored_context = (
        cognix_db.create_compressed_context(
            current_subject,
            plan = plan,
            project_id = payload.project_id,
        )
        if payload.store_context and plan.get("compressedContext")
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
        action = "conversation_summary_plan_built",
        resource_type = "cognix_conversation_summary_plan",
        resource_id = str((stored_context or {}).get("id") or payload.project_id or current_subject),
        severity = "warning" if plan.get("summary", {}).get("redactionCount") else "notice",
        metadata = {
            "conversationSummaryContractVersion": plan.get("conversationSummaryContractVersion"),
            "messageCount": plan.get("summary", {}).get("messageCount"),
            "summarizedMessageCount": plan.get("summary", {}).get("summarizedMessageCount"),
            "retainedRecentMessageCount": plan.get("summary", {}).get("retainedRecentMessageCount"),
            "rawHistoryIncluded": plan.get("summary", {}).get("rawHistoryIncluded"),
            "redactionCount": plan.get("summary", {}).get("redactionCount"),
            "sideEffects": side_effects,
        },
    )
    return {
        "conversationSummaryPlan": plan,
        "compressedContext": _row(stored_context) if stored_context else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_prompt_compression.COGNIX_CONVERSATION_SUMMARY_CONTRACT_VERSION,
    }


@router.post("/semantic-cache/plan")
async def semantic_cache_plan(
    payload: SemanticCachePlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_semantic_cache.build_semantic_cache_plan(
        username = current_subject,
        prompt = payload.prompt,
        project_id = payload.project_id,
        project_type = payload.project_type,
        task_type = payload.task_type,
        model_id = payload.model_id,
        sensitivity_level = payload.sensitivity_level,
        requires_sources = payload.requires_sources,
        context_hashes = payload.context_hashes,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "semantic_cache_plan_built",
        resource_type = "cognix_semantic_cache_plan",
        resource_id = str(plan.get("cacheKeyPlan", {}).get("cacheKeyHash") or plan.get("requestSignature")),
        severity = "warning" if plan.get("sensitivity", {}).get("level") == "restricted" else "notice",
        metadata = {
            "semanticCacheVersion": plan.get("semanticCacheVersion"),
            "policyVersion": plan.get("policyVersion"),
            "reuseContractVersion": plan.get("reuseContractVersion"),
            "requestSignature": plan.get("requestSignature"),
            "scopeType": plan.get("scope", {}).get("scopeType"),
            "sensitivityLevel": plan.get("sensitivity", {}).get("level"),
            "cacheabilityStatus": plan.get("cacheability", {}).get("status"),
            "readyForLookup": plan.get("lookupPlan", {}).get("readyForLookup"),
            "writeEligibleAfterValidation": plan.get("writePlan", {}).get("writeEligibleAfterValidation"),
            "sideEffects": plan.get("sideEffects", {}),
        },
    )
    return {
        "username": current_subject,
        "semanticCachePlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_semantic_cache.COGNIX_SEMANTIC_CACHE_VERSION,
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
    context_boundary = packet.get("contextBoundaryContract", {})
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
            "contextBoundaryContractVersion": context_boundary.get("contractVersion"),
            "assemblyStrategy": packet.get("contextPlan", {}).get("assemblyStrategy"),
            "rawHistoryAllowed": packet.get("contextPlan", {}).get("tokenBudget", {}).get("rawHistoryAllowed"),
            "frontendRawHistoryUploadAllowed": context_boundary.get("executionGate", {}).get("frontendRawHistoryUploadAllowed"),
            "memoryWriteAllowedNow": context_boundary.get("executionGate", {}).get("memoryWriteAllowedNow"),
            "ragRetrievalAllowedNow": context_boundary.get("executionGate", {}).get("ragRetrievalAllowedNow"),
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


@router.get("/chat/enterprise/blueprint")
async def enterprise_chat_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_enterprise_chat.build_enterprise_chat_blueprint()
    return {
        "username": current_subject,
        "enterpriseChatBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_enterprise_chat.COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION,
    }


@router.post("/chat/enterprise/chats")
async def create_enterprise_chat(
    payload: EnterpriseChatCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if payload.project_id:
        _require_owned_project(payload.project_id, current_subject)
    plan = cognix_enterprise_chat.build_enterprise_chat_creation_plan(
        username = current_subject,
        title = payload.title,
        organization_id = payload.organization_id,
        project_id = payload.project_id,
        chat_mode = payload.chat_mode,
        participants = payload.participants,
        policy = payload.policy,
    )
    stored_chat = cognix_db.create_enterprise_chat(current_subject, plan = plan) if payload.store_chat else None
    side_effects = {
        **plan.get("sideEffects", {}),
        "chatWrite": stored_chat is not None,
        "memberWrite": stored_chat is not None,
        "keyMetadataWrite": stored_chat is not None,
        "policyWrite": stored_chat is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "enterprise_chat_creation_planned",
        resource_type = "enterprise_chat",
        resource_id = str((stored_chat or {}).get("id") or plan.get("chat", {}).get("title") or "enterprise_chat"),
        severity = "notice" if plan.get("chat", {}).get("groupReady") else "warning",
        metadata = {
            "enterpriseChatServiceVersion": plan.get("enterpriseChatServiceVersion"),
            "chatMode": plan.get("chat", {}).get("mode"),
            "participantCount": plan.get("chat", {}).get("participantCount"),
            "storedChat": stored_chat is not None,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "enterpriseChatPlan": plan,
        "enterpriseChat": _row(stored_chat) if stored_chat else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_enterprise_chat.COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION,
    }


@router.get("/chat/enterprise/chats")
async def list_enterprise_chats(
    organization_id: str | None = None,
    limit: int = 100,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    chats = cognix_db.list_enterprise_chats(current_subject, organization_id = organization_id, limit = limit)
    return {
        "username": current_subject,
        "enterpriseChats": _rows([item for item in chats if item]),
        "count": len([item for item in chats if item]),
        "sideEffects": {
            "chatWrite": False,
            "memberWrite": False,
            "encryptedMessageWrite": False,
            "keyMetadataWrite": False,
            "policyWrite": False,
            "plaintextRead": False,
            "serverDecryption": False,
            "serverIndexing": False,
        },
        "plannerVersion": cognix_enterprise_chat.COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION,
    }


@router.get("/chat/enterprise/chats/{chat_id}")
async def get_enterprise_chat(
    chat_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    chat = cognix_db.get_enterprise_chat(chat_id, username = current_subject)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enterprise chat not found.")
    messages = cognix_db.list_enterprise_encrypted_messages(chat_id, username = current_subject, limit = 200)
    return {
        "username": current_subject,
        "enterpriseChat": _row(chat),
        "encryptedMessages": _rows(messages),
        "sideEffects": {
            "chatWrite": False,
            "memberWrite": False,
            "encryptedMessageWrite": False,
            "keyMetadataWrite": False,
            "policyWrite": False,
            "plaintextRead": False,
            "serverDecryption": False,
            "serverIndexing": False,
        },
        "plannerVersion": cognix_enterprise_chat.COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION,
    }


@router.post("/chat/enterprise/chats/{chat_id}/messages")
async def create_enterprise_encrypted_message(
    chat_id: str,
    payload: EnterpriseEncryptedMessageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    chat = cognix_db.get_enterprise_chat(chat_id, username = current_subject)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enterprise chat not found.")
    plan = cognix_enterprise_chat.build_encrypted_message_plan(
        username = current_subject,
        chat = chat,
        encrypted_payload = payload.encrypted_payload,
        metadata = payload.metadata,
    )
    if not plan.get("valid"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Encrypted payload, nonce and keyId are required.")
    stored_message = (
        cognix_db.create_enterprise_encrypted_message(current_subject, chat_id = chat_id, plan = plan)
        if payload.store_message
        else None
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "encryptedMessageWrite": stored_message is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "enterprise_encrypted_message_planned",
        resource_type = "encrypted_message",
        resource_id = str((stored_message or {}).get("id") or chat_id),
        severity = "notice",
        metadata = {
            "messageEncryptionServiceVersion": plan.get("messageEncryptionServiceVersion"),
            "chatId": chat_id,
            "ciphertextFingerprint": plan.get("message", {}).get("ciphertextFingerprint"),
            "storedMessage": stored_message is not None,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "encryptedMessagePlan": plan,
        "encryptedMessage": _row(stored_message) if stored_message else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_enterprise_chat.COGNIX_MESSAGE_ENCRYPTION_SERVICE_VERSION,
    }


@router.post("/chat/enterprise/chats/{chat_id}/key-rotation-plan")
async def enterprise_chat_key_rotation_plan(
    chat_id: str,
    payload: EnterpriseKeyRotationRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    chat = cognix_db.get_enterprise_chat(chat_id, username = current_subject)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enterprise chat not found.")
    plan = cognix_enterprise_chat.build_key_rotation_plan(
        username = current_subject,
        chat = chat,
        reason = payload.reason,
        revoked_member = payload.revoked_member,
    )
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "enterprise_chat_key_rotation_planned",
        resource_type = "chat_key_metadata",
        resource_id = chat_id,
        severity = "warning" if payload.revoked_member else "notice",
        metadata = {
            "e2eeKeyManagerVersion": plan.get("e2eeKeyManagerVersion"),
            "chatId": chat_id,
            "clientActionRequired": plan.get("clientActionRequired"),
            "serverStoresKeyMaterial": plan.get("serverStoresKeyMaterial"),
            "sideEffects": {**plan.get("sideEffects", {}), "auditWrite": True},
        },
    )
    return {
        "username": current_subject,
        "keyRotationPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": {**plan.get("sideEffects", {}), "auditWrite": True},
        "plannerVersion": cognix_enterprise_chat.COGNIX_E2EE_KEY_MANAGER_VERSION,
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
    registration_gate = asset_plan.get("registrationGate", {})
    if registration_gate.get("required") and not registration_gate.get("readyForLibraryWrite"):
        audit = cognix_db.create_audit_log(
            username = current_subject,
            actor_username = current_subject,
            action = "library_model_registration_blocked",
            resource_type = "cognix_library_item",
            resource_id = planned_asset["name"],
            severity = "warning",
            metadata = {
                "libraryVersion": asset_plan.get("libraryVersion"),
                "modelRegistrationGateVersion": registration_gate.get("gateVersion"),
                "kind": planned_asset["kind"],
                "source": planned_asset["source"],
                "blockedGateIds": registration_gate.get("blockedGateIds", []),
                "warningGateIds": registration_gate.get("warningGateIds", []),
                "sideEffects": asset_plan.get("sideEffects", {}),
            },
        )
        raise HTTPException(
            status_code = 403,
            detail = {
                "message": "Model library registration blocked until evaluation, safety review, and human approval pass.",
                "blockedGateIds": registration_gate.get("blockedGateIds", []),
                "auditLogId": audit.get("id"),
            },
        )
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
            "registrationGate": registration_gate,
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


@router.get("/chat-project-bridge")
async def chat_project_bridge(
    project_id: str | None = None,
    thread_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    if thread_id:
        _require_owned_thread(thread_id, current_subject)
    links = _rows(
        cognix_db.list_chat_project_links(
            current_subject,
            project_id = project_id,
            thread_id = thread_id,
        )
    )
    tasks = _rows(
        cognix_db.list_message_tasks(
            current_subject,
            project_id = project_id,
            thread_id = thread_id,
        )
    )
    return {
        "links": links,
        "tasks": tasks,
        "summary": {
            "linkCount": len(links),
            "taskCount": len(tasks),
            "openTaskCount": sum(1 for task in tasks if task.get("status") in {"open", "in_progress", "blocked"}),
        },
        "blueprint": cognix_chat_project_bridge.build_chat_project_bridge_blueprint(),
    }


@router.get("/chat-project-bridge/blueprint")
async def chat_project_bridge_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_chat_project_bridge.build_chat_project_bridge_blueprint()
    return {
        "username": current_subject,
        "blueprint": blueprint,
        "sideEffects": blueprint["sideEffects"],
    }


@router.post("/chat-project-bridge/mentions")
async def detect_chat_project_mentions(
    payload: ProjectMentionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    projects = list_chat_projects(
        include_archived = False,
        owner_username = current_subject,
        include_all = False,
    )
    mention_plan = cognix_chat_project_bridge.extract_project_mentions(payload.text, projects, limit = payload.limit)
    return {
        "username": current_subject,
        "mentionPlan": mention_plan,
        "mentions": mention_plan["mentions"],
        "sideEffects": mention_plan["sideEffects"],
    }


@router.post("/chat-project-bridge/links")
async def create_chat_project_link(
    payload: ChatProjectLinkRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project = _require_owned_project(payload.project_id, current_subject)
    thread = _require_owned_thread(payload.thread_id, current_subject)
    plan = cognix_chat_project_bridge.build_thread_link_plan(
        username = current_subject,
        project = project,
        thread = thread,
        link_type = payload.link_type,
        source = payload.source,
        metadata = payload.metadata,
    )
    if not payload.store_link:
        return {
            "link": None,
            "chatProjectLinkPlan": plan,
            "sideEffects": plan["sideEffects"],
        }
    link = cognix_db.create_chat_project_link(
        current_subject,
        project_id = plan["link"]["projectId"],
        thread_id = plan["link"]["threadId"],
        link_type = plan["link"]["linkType"],
        source = plan["link"]["source"],
        metadata = {
            **(payload.metadata or {}),
            "chatProjectBridgeVersion": plan["chatProjectBridgeVersion"],
        },
    )
    side_effects = {
        **plan["sideEffects"],
        "chatProjectLinkWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "chat_project_link_created",
        resource_type = "chat_project_link",
        resource_id = str(link.get("id") or ""),
        severity = "notice",
        metadata = {
            "projectId": payload.project_id,
            "threadId": payload.thread_id,
            "linkType": payload.link_type,
            "sideEffects": side_effects,
        },
    )
    return {
        "link": _row(link),
        "chatProjectLinkPlan": {**plan, "sideEffects": side_effects},
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.post("/chat-project-bridge/message-tasks")
async def create_message_task(
    payload: MessageTaskCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project = _require_owned_project(payload.project_id, current_subject)
    thread = _require_owned_thread(payload.thread_id, current_subject) if payload.thread_id else None
    if payload.message_id and not payload.thread_id:
        raise HTTPException(status_code = 400, detail = "threadId is required when messageId is provided")
    message = _get_owned_message(payload.thread_id, payload.message_id, current_subject)
    plan = cognix_chat_project_bridge.build_message_task_plan(
        username = current_subject,
        project = project,
        thread = thread,
        message = message,
        source_text = payload.source_text,
        task_title = payload.title,
        status = payload.status,
        priority = payload.priority,
        require_approval = payload.require_approval,
        metadata = payload.metadata,
    )
    if not payload.store_task:
        return {
            "task": None,
            "messageTaskPlan": plan,
            "approvalRequest": None,
            "sideEffects": plan["sideEffects"],
        }
    approval = None
    if payload.require_approval:
        approval = cognix_db.create_approval_request(
            current_subject,
            "chat_message_task_approval",
            f"Review chat-derived task: {plan['task']['title']}",
            title = plan["task"]["title"],
            risk_level = "medium",
            resource_type = "message_task",
            resource_id = payload.message_id or payload.thread_id or payload.project_id,
            metadata = {
                "projectId": payload.project_id,
                "threadId": payload.thread_id,
                "messageId": payload.message_id,
                "chatProjectBridgeVersion": plan["chatProjectBridgeVersion"],
            },
        )
    task = cognix_db.create_message_task(
        current_subject,
        project_id = plan["task"]["projectId"],
        thread_id = plan["task"]["threadId"],
        message_id = plan["task"]["messageId"],
        title = plan["task"]["title"],
        source_text = plan["task"]["sourceText"],
        status = plan["task"]["status"],
        priority = plan["task"]["priority"],
        approval_request_id = str((approval or {}).get("id") or "") or None,
        metadata = {
            **(payload.metadata or {}),
            "chatProjectBridgeVersion": plan["chatProjectBridgeVersion"],
            "messageToTaskVersion": plan["messageToTaskVersion"],
        },
    )
    side_effects = {
        **plan["sideEffects"],
        "messageTaskWrite": True,
        "approvalRequestWrite": approval is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "message_task_created",
        resource_type = "message_task",
        resource_id = str(task.get("id") or ""),
        severity = "warning" if approval is not None else "notice",
        metadata = {
            "projectId": payload.project_id,
            "threadId": payload.thread_id,
            "messageId": payload.message_id,
            "priority": payload.priority,
            "approvalRequestId": (approval or {}).get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "task": _row(task),
        "messageTaskPlan": {**plan, "sideEffects": side_effects},
        "approvalRequest": _row(approval) if approval else None,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.post("/chat-project-bridge/answer-shares")
async def share_cognix_answer_to_chat(
    payload: AnswerShareRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    project = _require_owned_project(payload.project_id, current_subject)
    thread = _require_owned_thread(payload.thread_id, current_subject)
    if payload.parent_message_id:
        _get_owned_message(payload.thread_id, payload.parent_message_id, current_subject)
    plan = cognix_chat_project_bridge.build_answer_share_plan(
        username = current_subject,
        project = project,
        thread = thread,
        answer_text = payload.answer_text,
        title = payload.title,
        parent_message_id = payload.parent_message_id,
        metadata = payload.metadata,
    )
    if not payload.store_share:
        return {
            "message": None,
            "link": None,
            "answerSharePlan": plan,
            "sideEffects": plan["sideEffects"],
        }
    message_id = payload.message_id or f"ans_{uuid.uuid4().hex}"
    message = upsert_chat_message(
        {
            "id": message_id,
            "threadId": payload.thread_id,
            "parentId": payload.parent_message_id,
            "role": "assistant",
            "content": [{"type": "text", "text": plan["answer"]["text"]}],
            "metadata": {
                **(payload.metadata or {}),
                "sharedFromProjectId": payload.project_id,
                "chatProjectBridgeVersion": plan["chatProjectBridgeVersion"],
                "answerShareVersion": plan["answerShareVersion"],
                "title": plan["answer"]["title"],
            },
            "createdAt": int(time.time() * 1000),
        }
    )
    link = cognix_db.create_chat_project_link(
        current_subject,
        project_id = payload.project_id,
        thread_id = payload.thread_id,
        link_type = "answer_share",
        source = "project",
        metadata = {
            **(payload.metadata or {}),
            "messageId": message_id,
            "answerShareVersion": plan["answerShareVersion"],
            "chatProjectBridgeVersion": plan["chatProjectBridgeVersion"],
        },
    )
    side_effects = {
        **plan["sideEffects"],
        "chatMessageWrite": True,
        "chatProjectLinkWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "cognix_answer_shared_to_chat",
        resource_type = "chat_message",
        resource_id = message_id,
        severity = "notice",
        metadata = {
            "projectId": payload.project_id,
            "threadId": payload.thread_id,
            "messageId": message_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "message": _row(message),
        "link": _row(link),
        "answerSharePlan": {**plan, "sideEffects": side_effects},
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.post("/chat-project-bridge/projects-from-discussion")
async def create_project_from_discussion(
    payload: DiscussionProjectCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    thread = _require_owned_thread(payload.thread_id, current_subject)
    base_slug = re.sub(r"[^a-z0-9]+", "-", payload.project_name.lower()).strip("-")[:48] or "discussion"
    project_id = payload.project_id or f"project-{base_slug}-{uuid.uuid4().hex[:8]}"
    existing_project = get_chat_project(project_id)
    if existing_project is not None and payload.store_project:
        raise HTTPException(status_code = 409, detail = "Project already exists")
    plan = cognix_chat_project_bridge.build_discussion_project_plan(
        username = current_subject,
        thread = thread,
        project_id = project_id,
        project_name = payload.project_name,
        discussion_summary = payload.discussion_summary,
        instructions = payload.instructions,
        metadata = payload.metadata,
    )
    if not payload.store_project:
        return {
            "project": None,
            "link": None,
            "discussionProjectPlan": plan,
            "sideEffects": plan["sideEffects"],
        }
    now_ms = int(time.time() * 1000)
    project = upsert_chat_project(
        {
            "id": project_id,
            "name": plan["project"]["name"],
            "instructions": plan["project"]["instructions"],
            "archived": False,
            "createdAt": now_ms,
            "updatedAt": now_ms,
        },
        owner_username = current_subject,
    )
    link = cognix_db.create_chat_project_link(
        current_subject,
        project_id = project_id,
        thread_id = payload.thread_id,
        link_type = "conversation",
        source = "discussion",
        metadata = {
            **(payload.metadata or {}),
            "discussionSummary": plan["project"]["discussionSummary"],
            "discussionProjectVersion": plan["discussionProjectVersion"],
            "chatProjectBridgeVersion": plan["chatProjectBridgeVersion"],
        },
    )
    side_effects = {
        **plan["sideEffects"],
        "projectWrite": True,
        "chatProjectLinkWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_created_from_discussion",
        resource_type = "chat_project",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "projectId": project_id,
            "threadId": payload.thread_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "project": _row(project),
        "link": _row(link),
        "discussionProjectPlan": {**plan, "sideEffects": side_effects},
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


@router.get("/models/favorites/blueprint")
async def favorite_models_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_favorite_models.build_favorite_models_blueprint()
    return {
        "username": current_subject,
        "favoriteModelsBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_favorite_models.COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
    }


@router.get("/models/favorites")
async def list_favorite_models(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    favorites = cognix_db.list_favorite_models(current_subject)
    user_default = cognix_db.get_user_model_default(current_subject)
    project_defaults = cognix_db.list_project_model_defaults(current_subject)
    snapshot = cognix_favorite_models.build_quick_switcher_snapshot(
        username = current_subject,
        favorites = favorites,
        user_default = user_default,
        project_defaults = project_defaults,
    )
    return {
        "username": current_subject,
        "favoriteModels": _rows(favorites),
        "userDefaultModel": _row(user_default) if user_default else None,
        "projectDefaults": _rows(project_defaults),
        "quickSwitcher": snapshot,
        "count": len(favorites),
        "sideEffects": snapshot.get("sideEffects", {}),
        "plannerVersion": cognix_favorite_models.COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
    }


@router.post("/model-pins")
async def pin_model(
    payload: ModelPinRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return await favorite_model_upsert(payload, current_subject)


@router.post("/models/favorites")
async def favorite_model_upsert(
    payload: ModelPinRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_favorite_models.build_favorite_model_plan(
        username = current_subject,
        model_id = payload.model_id,
        label = payload.label,
        provider_type = payload.provider_type,
        provider_id = payload.provider_id,
        source = payload.source,
        project_ids = payload.project_ids,
        quick_switcher = payload.quick_switcher,
        sort_order = payload.sort_order,
        metadata = payload.metadata,
    )
    if not plan.get("valid"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Model id is required.")
    favorite = cognix_db.upsert_favorite_model(current_subject, plan = plan)
    pin = cognix_db.set_model_pin(
        current_subject,
        payload.model_id,
        payload.label,
        provider_type = payload.provider_type,
        provider_id = payload.provider_id,
        source = payload.source,
        quick_switcher = payload.quick_switcher,
        sort_order = payload.sort_order,
        metadata = payload.metadata,
    )
    side_effects = {
        **plan.get("sideEffects", {}),
        "favoriteWrite": True,
        "quickSwitcherWrite": payload.quick_switcher,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "favorite_model_upserted",
        resource_type = "favorite_model",
        resource_id = payload.model_id,
        severity = "notice",
        metadata = {
            "favoriteModelServiceVersion": plan.get("favoriteModelServiceVersion"),
            "modelQuickSwitcherVersion": plan.get("modelQuickSwitcherVersion"),
            "quickSwitcher": payload.quick_switcher,
            "sideEffects": side_effects,
        },
    )
    return {
        "pin": _row(pin),
        "favoriteModel": _row(favorite),
        "favoriteModelPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_favorite_models.COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
    }


@router.delete("/model-pins/{model_id}")
async def unpin_model(
    model_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return await delete_favorite_model(model_id, current_subject)


@router.delete("/models/favorites/{model_id:path}")
async def delete_favorite_model(
    model_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    removed = cognix_db.delete_favorite_model(current_subject, model_id)
    side_effects = {
        **cognix_favorite_models.build_favorite_models_blueprint().get("sideEffects", {}),
        "favoriteDelete": removed,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "favorite_model_deleted",
        resource_type = "favorite_model",
        resource_id = model_id,
        severity = "notice" if removed else "warning",
        metadata = {
            "favoriteModelServiceVersion": cognix_favorite_models.COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
            "removed": removed,
            "sideEffects": side_effects,
        },
    )
    return {"ok": True, "removed": removed, "auditLogId": audit.get("id"), "sideEffects": side_effects}


@router.get("/models/default")
async def get_user_default_model(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    default_model = cognix_db.get_user_model_default(current_subject)
    return {
        "username": current_subject,
        "defaultModel": _row(default_model) if default_model else None,
        "sideEffects": {"userDefaultWrite": False, "modelLoad": False, "generation": False},
        "plannerVersion": cognix_favorite_models.COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION,
    }


@router.put("/models/default")
async def set_user_default_model(
    payload: UserDefaultModelRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    plan = cognix_favorite_models.build_user_default_model_plan(
        username = current_subject,
        model_id = payload.model_id,
        label = payload.label,
        provider_type = payload.provider_type,
        provider_id = payload.provider_id,
        source = payload.source,
        metadata = payload.metadata,
    )
    if not plan.get("valid"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Model id is required.")
    default_model = cognix_db.set_user_model_default(current_subject, plan = plan)
    favorite_plan = cognix_favorite_models.build_favorite_model_plan(
        username = current_subject,
        model_id = payload.model_id,
        label = payload.label,
        provider_type = payload.provider_type,
        provider_id = payload.provider_id,
        source = payload.source or "user_default",
        quick_switcher = True,
        metadata = payload.metadata,
    )
    favorite = cognix_db.upsert_favorite_model(current_subject, plan = favorite_plan)
    side_effects = {
        **plan.get("sideEffects", {}),
        "userDefaultWrite": True,
        "favoriteWrite": True,
        "quickSwitcherWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "user_default_model_set",
        resource_type = "user_model_default",
        resource_id = payload.model_id,
        severity = "notice",
        metadata = {
            "userModelPreferenceServiceVersion": plan.get("userModelPreferenceServiceVersion"),
            "modelId": payload.model_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "defaultModel": _row(default_model),
        "favoriteModel": _row(favorite),
        "userDefaultModelPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_favorite_models.COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION,
    }


@router.delete("/models/default")
async def delete_user_default_model(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    removed = cognix_db.delete_user_model_default(current_subject)
    side_effects = {
        **cognix_favorite_models.build_favorite_models_blueprint().get("sideEffects", {}),
        "userDefaultWrite": removed,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "user_default_model_deleted",
        resource_type = "user_model_default",
        resource_id = current_subject,
        severity = "notice" if removed else "warning",
        metadata = {
            "userModelPreferenceServiceVersion": cognix_favorite_models.COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION,
            "removed": removed,
            "sideEffects": side_effects,
        },
    )
    return {"ok": True, "removed": removed, "auditLogId": audit.get("id"), "sideEffects": side_effects}


@router.get("/models/quick-switcher")
async def model_quick_switcher(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if project_id:
        _require_owned_project(project_id, current_subject)
    favorites = cognix_db.list_favorite_models(current_subject)
    user_default = cognix_db.get_user_model_default(current_subject)
    project_defaults = cognix_db.list_project_model_defaults(current_subject)
    snapshot = cognix_favorite_models.build_quick_switcher_snapshot(
        username = current_subject,
        favorites = favorites,
        user_default = user_default,
        project_defaults = project_defaults,
        active_project_id = project_id,
    )
    return {
        "username": current_subject,
        "quickSwitcher": snapshot,
        "sideEffects": snapshot.get("sideEffects", {}),
        "plannerVersion": cognix_favorite_models.COGNIX_MODEL_QUICK_SWITCHER_VERSION,
    }


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
    plan = cognix_favorite_models.build_project_default_model_plan(
        username = current_subject,
        project_id = project_id,
        model_id = payload.model_id,
        label = payload.label,
        provider_type = payload.provider_type,
        provider_id = payload.provider_id,
        source = "project_default",
    )
    if not plan.get("valid"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project id and model id are required.")
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
    favorite_plan = cognix_favorite_models.build_favorite_model_plan(
        username = current_subject,
        model_id = payload.model_id,
        label = payload.label,
        provider_type = payload.provider_type,
        provider_id = payload.provider_id,
        source = "project_default",
        project_ids = [project_id],
        quick_switcher = True,
    )
    favorite = cognix_db.upsert_favorite_model(current_subject, plan = favorite_plan)
    side_effects = {
        **plan.get("sideEffects", {}),
        "projectDefaultWrite": True,
        "favoriteWrite": True,
        "quickSwitcherWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_default_model_set",
        resource_type = "project_model_default",
        resource_id = project_id,
        severity = "notice",
        metadata = {
            "favoriteModelServiceVersion": plan.get("favoriteModelServiceVersion"),
            "userModelPreferenceServiceVersion": plan.get("userModelPreferenceServiceVersion"),
            "projectId": project_id,
            "modelId": payload.model_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "defaultModel": _row(default_model),
        "favoriteModel": _row(favorite),
        "projectDefaultModelPlan": plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.delete("/projects/{project_id}/default-model")
async def delete_project_default_model(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_owned_project(project_id, current_subject)
    removed = cognix_db.delete_project_model_default(current_subject, project_id)
    side_effects = {
        **cognix_favorite_models.build_favorite_models_blueprint().get("sideEffects", {}),
        "projectDefaultWrite": removed,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = current_subject,
        actor_username = current_subject,
        action = "project_default_model_deleted",
        resource_type = "project_model_default",
        resource_id = project_id,
        severity = "notice" if removed else "warning",
        metadata = {
            "favoriteModelServiceVersion": cognix_favorite_models.COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
            "projectId": project_id,
            "removed": removed,
            "sideEffects": side_effects,
        },
    )
    return {"ok": True, "removed": removed, "auditLogId": audit.get("id"), "sideEffects": side_effects}


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
    project_session_contract = expert_plan.get("projectSessionContract", {})
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
            "projectSessionContractVersion": project_session_contract.get("contractVersion"),
            "projectSessionMode": project_session_contract.get("sessionMode"),
            "projectSessionWillLoadModel": False,
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


@router.get("/admin/projects/blueprint")
async def admin_projects_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_project_oversight.build_admin_project_blueprint()
    return {
        "username": current_subject,
        "adminProjectsBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_project_oversight.COGNIX_ADMIN_PROJECT_SERVICE_VERSION,
    }


@router.get("/admin/projects")
async def admin_projects(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_project_oversight_bundle()
    return {
        "username": current_subject,
        "adminProjectOversight": bundle["oversight"],
        "projects": _rows(bundle["projects"]),
        "adminProjectEvents": _rows(bundle["adminProjectEvents"]),
        "projectAdminReports": _rows(bundle["projectAdminReports"]),
        "sideEffects": bundle["oversight"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_project_oversight.COGNIX_ADMIN_PROJECT_SERVICE_VERSION,
    }


@router.get("/admin/projects/{project_id}")
async def admin_project_detail(
    project_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_project_oversight_bundle()
    project_item = next(
        (item for item in bundle["oversight"]["projects"] if str(item.get("projectId") or "") == project_id),
        None,
    )
    if project_item is None:
        raise HTTPException(status_code = 404, detail = "Project not found")
    return {
        "username": current_subject,
        "project": project_item,
        "sideEffects": bundle["oversight"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_project_oversight.COGNIX_ADMIN_PROJECT_SERVICE_VERSION,
    }


@router.post("/admin/projects/{project_id}/action-plan")
async def admin_project_action_plan(
    project_id: str,
    payload: AdminProjectActionPlanRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    project = get_chat_project(project_id, include_all = True)
    if project is None:
        raise HTTPException(status_code = 404, detail = "Project not found")
    try:
        action_plan = cognix_admin_project_oversight.build_project_action_plan(
            project = project,
            action = payload.action,
            actor_username = current_subject,
            reason = payload.reason,
            target_username = payload.target_username,
            target_role = payload.target_role,
            model_ids = payload.model_ids,
            cloud_allowed = payload.cloud_allowed,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    event = cognix_db.create_admin_project_event(
        project_id = project_id,
        owner_username = str(project.get("ownerUsername") or ""),
        actor_username = current_subject,
        target_username = payload.target_username,
        action = payload.action,
        reason = payload.reason,
        risk_level = str(action_plan.get("action", {}).get("riskLevel") or "medium"),
        approval_required = bool(action_plan.get("approvalRequired")),
        event = action_plan,
        metadata = {
            "projectActionPlannerVersion": cognix_admin_project_oversight.COGNIX_PROJECT_ACTION_PLANNER_VERSION,
            "permissionRequired": action_plan.get("permissionRequired"),
        },
    )
    side_effects = {
        **action_plan.get("sideEffects", {}),
        "databaseWrite": True,
        "adminProjectEventWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = str(project.get("ownerUsername") or ""),
        actor_username = current_subject,
        action = "admin_project_action_planned",
        resource_type = "chat_project",
        resource_id = project_id,
        severity = "warning" if action_plan.get("confirmationRequired") else "notice",
        metadata = {
            "projectId": project_id,
            "action": payload.action,
            "approvalRequired": action_plan.get("approvalRequired"),
            "permissionRequired": action_plan.get("permissionRequired"),
            "eventId": event.get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "actionPlan": action_plan,
        "adminProjectEvent": _row(event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_project_oversight.COGNIX_PROJECT_ACTION_PLANNER_VERSION,
    }


@router.post("/admin/projects/{project_id}/report")
async def admin_project_report(
    project_id: str,
    payload: AdminProjectReportRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_project_oversight_bundle()
    project = next((item for item in bundle["projects"] if str(item.get("id") or "") == project_id), None)
    oversight_item = next(
        (item for item in bundle["oversight"]["projects"] if str(item.get("projectId") or "") == project_id),
        None,
    )
    if project is None or oversight_item is None:
        raise HTTPException(status_code = 404, detail = "Project not found")
    report_plan = cognix_admin_project_oversight.build_project_admin_report(
        project = project,
        oversight_item = oversight_item,
        generated_by = current_subject,
        report_type = payload.report_type,
        output_format = payload.output_format,
    )
    report = cognix_db.create_project_admin_report(
        project_id = project_id,
        owner_username = str(project.get("ownerUsername") or ""),
        generated_by = current_subject,
        report = report_plan,
        report_type = payload.report_type,
        output_format = payload.output_format,
    )
    side_effects = {
        **report_plan.get("sideEffects", {}),
        "databaseWrite": True,
        "reportWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = str(project.get("ownerUsername") or ""),
        actor_username = current_subject,
        action = "admin_project_report_generated",
        resource_type = "project_admin_report",
        resource_id = str(report.get("id") or ""),
        severity = "notice",
        metadata = {
            "projectId": project_id,
            "reportType": payload.report_type,
            "outputFormat": payload.output_format,
            "reason": payload.reason,
            "riskLevel": report_plan.get("riskLevel"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "reportPlan": report_plan,
        "projectAdminReport": _row(report),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_project_oversight.COGNIX_PROJECT_REPORT_VERSION,
    }


@router.get("/admin/settings/blueprint")
async def admin_settings_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_organization_settings.build_organization_settings_blueprint()
    return {
        "username": current_subject,
        "organizationSettingsBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_organization_settings.COGNIX_ADMIN_SETTINGS_SERVICE_VERSION,
    }


@router.get("/admin/settings")
async def admin_settings(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_organization_settings_bundle()
    return {
        "username": current_subject,
        "organizationSettings": bundle["bundle"],
        "settings": bundle["settings"],
        "settingRecords": _rows(bundle["settingRecords"]),
        "policies": _rows(bundle["policies"]),
        "changeLogs": _rows(bundle["changeLogs"]),
        "sideEffects": bundle["bundle"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_organization_settings.COGNIX_ADMIN_SETTINGS_SERVICE_VERSION,
    }


@router.put("/admin/settings")
async def admin_update_settings(
    payload: AdminOrganizationSettingsRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    before_bundle = _build_admin_organization_settings_bundle()
    incoming = _settings_payload_to_dict(payload)
    after = dict(before_bundle["settings"])
    after.update(incoming)
    normalized_after = cognix_admin_organization_settings.normalize_organization_settings(after)
    change_record = cognix_admin_organization_settings.build_policy_change_record(
        before = before_bundle["settings"],
        after = normalized_after,
        changed_by = current_subject,
        reason = payload.reason or "",
    )
    setting_records = [
        cognix_db.upsert_organization_setting(
            setting_key = key,
            setting_value = value,
            setting_type = "policy",
            updated_by = current_subject,
        )
        for key, value in normalized_after.items()
    ]
    policy_records = [
        cognix_db.upsert_organization_policy(
            policy_key = str(record.get("policyKey") or ""),
            policy_value = record.get("policyValue"),
            policy_type = str(record.get("policyType") or "setting"),
            permission_key = record.get("permissionKey") or record.get("policyKey"),
            allowed = bool(record.get("allowed")),
            enforced = bool(record.get("enforced", True)),
            updated_by = current_subject,
            reason = payload.reason or "",
        )
        for record in cognix_admin_organization_settings.policy_records_from_settings(
            settings = normalized_after,
            updated_by = current_subject,
        )
    ]
    change_log = cognix_db.create_policy_change_log(
        changed_by = current_subject,
        changed_keys = change_record["changedKeys"],
        before = change_record["before"],
        after = change_record["after"],
        reason = payload.reason or "",
    )
    updated_bundle = cognix_admin_organization_settings.build_policy_bundle(
        settings = normalized_after,
        policies = policy_records,
        change_logs = [change_log, *before_bundle["changeLogs"]],
    )
    side_effects = {
        **updated_bundle.get("sideEffects", {}),
        "databaseWrite": True,
        "policyWrite": True,
        "settingsWrite": True,
        "changeLogWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_organization_settings_updated",
        resource_type = "organization_settings",
        resource_id = "default",
        severity = "warning" if change_record["changedKeys"] else "notice",
        metadata = {
            "changedKeys": change_record["changedKeys"],
            "reason": payload.reason,
            "policyChangeLogId": change_log.get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "organizationSettings": updated_bundle,
        "settingRecords": _rows(setting_records),
        "policies": _rows(policy_records),
        "policyChangeLog": _row(change_log),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_organization_settings.COGNIX_ADMIN_SETTINGS_SERVICE_VERSION,
    }


@router.post("/admin/settings/enforcement-plan")
async def admin_settings_enforcement_plan(
    payload: AdminPolicyEnforcementRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_organization_settings_bundle()
    plan = cognix_admin_organization_settings.build_policy_enforcement_plan(
        settings = bundle["settings"],
        action_type = payload.action_type,
        model_id = payload.model_id,
        provider = payload.provider,
        app_id = payload.app_id,
        permission_key = payload.permission_key,
    )
    return {
        "username": current_subject,
        "enforcementPlan": plan,
        "sideEffects": plan.get("sideEffects", {}),
        "plannerVersion": cognix_admin_organization_settings.COGNIX_POLICY_ENFORCER_VERSION,
    }


@router.get("/admin/settings/change-logs")
async def admin_settings_change_logs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    logs = cognix_db.list_policy_change_logs(limit = 500)
    return {
        "username": current_subject,
        "changeLogs": _rows(logs),
        "sideEffects": {
            "databaseWrite": False,
            "policyWrite": False,
            "settingsWrite": False,
            "changeLogWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
        "plannerVersion": cognix_admin_organization_settings.COGNIX_POLICY_CHANGE_LOG_VERSION,
    }


@router.get("/admin/local-only/blueprint")
async def admin_local_only_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_local_only.build_local_only_blueprint()
    return {
        "username": current_subject,
        "localOnlyBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_local_only.COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION,
    }


@router.get("/admin/local-only")
async def admin_local_only(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_local_only_bundle()
    return {
        "username": current_subject,
        "policy": bundle["policy"],
        "policyRecord": _row(bundle["policyRecord"]) if bundle["policyRecord"] else None,
        "badge": bundle["enforcementPlan"]["badge"],
        "enforcementPlan": bundle["enforcementPlan"],
        "blockedExternalCalls": _rows(bundle["blockedCalls"]),
        "sideEffects": bundle["enforcementPlan"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_local_only.COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION,
    }


@router.put("/admin/local-only/policy")
async def admin_update_local_only_policy(
    payload: AdminLocalOnlyPolicyRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    before_policy = _current_local_only_policy()
    after_policy = dict(before_policy)
    after_policy.update(_local_only_payload_to_dict(payload))
    normalized_policy = cognix_admin_local_only.normalize_local_only_policy(after_policy)
    policy_record = cognix_db.upsert_local_only_policy(
        policy = normalized_policy,
        updated_by = current_subject,
        reason = payload.reason or "",
    )
    setting_records: list[dict[str, Any]] = []
    policy_records: list[dict[str, Any]] = []
    change_log = None
    if normalized_policy["enabled"]:
        before_settings = _build_admin_organization_settings_bundle()["settings"]
        setting_records = [
            cognix_db.upsert_organization_setting(
                setting_key = "cloudAllowed",
                setting_value = False,
                setting_type = "local_only_policy",
                updated_by = current_subject,
            ),
            cognix_db.upsert_organization_setting(
                setting_key = "externalModelsAllowed",
                setting_value = False,
                setting_type = "local_only_policy",
                updated_by = current_subject,
            ),
        ]
        policy_records = [
            cognix_db.upsert_organization_policy(
                policy_key = "cloud:allowed",
                policy_value = False,
                policy_type = "permission",
                permission_key = "cloud:allowed",
                allowed = False,
                enforced = True,
                updated_by = current_subject,
                reason = payload.reason or "Enterprise local-only mode",
            ),
            cognix_db.upsert_organization_policy(
                policy_key = "models:external",
                policy_value = False,
                policy_type = "permission",
                permission_key = "models:external",
                allowed = False,
                enforced = True,
                updated_by = current_subject,
                reason = payload.reason or "Enterprise local-only mode",
            ),
        ]
        after_settings = dict(before_settings)
        after_settings.update({"cloudAllowed": False, "externalModelsAllowed": False})
        change_log = cognix_db.create_policy_change_log(
            changed_by = current_subject,
            change_type = "local_only_policy_update",
            changed_keys = ["localOnlyMode", "cloudAllowed", "externalModelsAllowed"],
            before = before_settings,
            after = after_settings,
            reason = payload.reason or "",
        )
    enforcement_plan = cognix_admin_local_only.build_enforcement_plan(
        policy = normalized_policy,
        blocked_calls = cognix_db.list_blocked_external_calls(limit = 500),
    )
    side_effects = {
        **enforcement_plan.get("sideEffects", {}),
        "databaseWrite": True,
        "policyWrite": True,
        "organizationSettingsWrite": bool(setting_records),
        "changeLogWrite": change_log is not None,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_local_only_policy_updated",
        resource_type = "local_only_policy",
        resource_id = str(policy_record.get("id") or "default"),
        severity = "warning" if normalized_policy["enabled"] else "notice",
        metadata = {
            "enabled": normalized_policy["enabled"],
            "policyRecordId": policy_record.get("id"),
            "changeLogId": change_log.get("id") if change_log else None,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "policy": normalized_policy,
        "policyRecord": _row(policy_record),
        "settingRecords": _rows(setting_records),
        "policies": _rows(policy_records),
        "policyChangeLog": _row(change_log) if change_log else None,
        "enforcementPlan": enforcement_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_local_only.COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION,
    }


@router.post("/admin/local-only/enforcement-plan")
async def admin_local_only_enforcement_plan(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_local_only_bundle()
    return {
        "username": current_subject,
        "enforcementPlan": bundle["enforcementPlan"],
        "policy": bundle["policy"],
        "sideEffects": bundle["enforcementPlan"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_local_only.COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION,
    }


@router.post("/admin/local-only/egress-decision")
async def admin_local_only_egress_decision(
    payload: AdminLocalOnlyDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    policy = _current_local_only_policy()
    decision = cognix_admin_local_only.build_egress_decision(
        policy = policy,
        provider = payload.provider,
        url = payload.url,
        action_type = payload.action_type,
        model_id = payload.model_id,
        document_transfer = payload.document_transfer,
    )
    blocked_call = None
    audit = None
    side_effects = dict(decision.get("sideEffects", {}))
    if not decision["allowed"]:
        blocked_call = cognix_db.create_blocked_external_call(
            actor_username = current_subject,
            provider = str(decision.get("provider") or ""),
            model_id = str(decision.get("modelId") or ""),
            url = str(decision.get("url") or ""),
            action_type = str(decision.get("actionType") or "network"),
            reason = ", ".join(decision.get("reasons") or []),
            decision = {
                "decision": decision,
                "metadata": payload.metadata,
            },
        )
        side_effects.update(
            {
                "databaseWrite": True,
                "blockedCallWrite": True,
                "auditWrite": True,
                "networkCall": False,
            }
        )
        audit = cognix_db.create_audit_log(
            username = None,
            actor_username = current_subject,
            action = "admin_local_only_external_call_blocked",
            resource_type = "blocked_external_call",
            resource_id = str(blocked_call.get("id") or ""),
            severity = "warning",
            metadata = {
                "provider": decision.get("provider"),
                "modelId": decision.get("modelId"),
                "url": decision.get("url"),
                "reasons": decision.get("reasons"),
                "sideEffects": side_effects,
            },
        )
    return {
        "username": current_subject,
        "decision": decision,
        "blockedExternalCall": _row(blocked_call) if blocked_call else None,
        "auditLogId": audit.get("id") if audit else None,
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_local_only.COGNIX_NETWORK_EGRESS_GUARD_VERSION,
    }


@router.get("/admin/local-only/blocked-calls")
async def admin_local_only_blocked_calls(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blocked_calls = cognix_db.list_blocked_external_calls(limit = 500)
    return {
        "username": current_subject,
        "blockedExternalCalls": _rows(blocked_calls),
        "sideEffects": cognix_admin_local_only.build_local_only_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_local_only.COGNIX_PROVIDER_BLOCKER_VERSION,
    }


@router.get("/admin/models/secure-registry/blueprint")
async def admin_secure_model_registry_blueprint(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_secure_model_registry.build_secure_model_registry_blueprint()
    return {
        "username": current_subject,
        "secureModelRegistryBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_secure_model_registry.COGNIX_SECURE_MODEL_REGISTRY_VERSION,
    }


@router.get("/admin/models/secure-registry")
async def admin_secure_model_registry(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_secure_model_registry_bundle()
    return {
        "username": current_subject,
        "secureModelRegistry": bundle["secureRegistry"],
        "approvedModels": _rows(bundle["approvedModels"]),
        "blockedModels": _rows(bundle["blockedModels"]),
        "modelSecurityMetadata": _rows(bundle["modelSecurityMetadata"]),
        "sideEffects": bundle["secureRegistry"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_secure_model_registry.COGNIX_SECURE_MODEL_REGISTRY_VERSION,
    }


@router.post("/admin/models/secure-registry/approve")
async def admin_approve_secure_model(
    payload: AdminSecureModelApprovalRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    security_metadata = cognix_admin_secure_model_registry.build_model_security_metadata(
        model_id = payload.model_id,
        provider_type = payload.provider_type,
        license_name = payload.license_name,
        source = payload.source,
        checksum = payload.checksum,
    )
    approved = cognix_db.approve_model(
        model_id = payload.model_id,
        display_name = payload.display_name or payload.model_id,
        provider_type = payload.provider_type,
        allowed_roles = payload.allowed_roles,
        quantization_required = payload.quantization_required or "",
        local_only_required = payload.local_only_required,
        license_name = payload.license_name or "unknown",
        source = payload.source or "unknown",
        checksum = payload.checksum or "",
        approved_by = current_subject,
        reason = payload.reason or "",
    )
    metadata_record = cognix_db.upsert_model_security_metadata(
        metadata = security_metadata,
        updated_by = current_subject,
    )
    allowed_sync = _sync_allowed_models_setting(
        model_id = payload.model_id,
        current_subject = current_subject,
        reason = payload.reason or "Secure model approval",
    )
    side_effects = {
        **security_metadata.get("sideEffects", {}),
        "databaseWrite": True,
        "approvedModelWrite": True,
        "metadataWrite": True,
        "organizationSettingsWrite": True,
        "changeLogWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_secure_model_approved",
        resource_type = "approved_model",
        resource_id = str(approved.get("id") or payload.model_id),
        severity = "notice" if security_metadata.get("riskLevel") == "low" else "warning",
        metadata = {
            "modelId": payload.model_id,
            "providerType": payload.provider_type,
            "checksumVerified": security_metadata.get("checksumVerified"),
            "riskLevel": security_metadata.get("riskLevel"),
            "allowedModels": allowed_sync["allowedModels"],
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "approvedModel": _row(approved),
        "modelSecurityMetadata": _row(metadata_record),
        "allowedModels": allowed_sync["allowedModels"],
        "policyChangeLog": _row(allowed_sync["changeLog"]),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_secure_model_registry.COGNIX_MODEL_APPROVAL_SERVICE_VERSION,
    }


@router.post("/admin/models/secure-registry/block")
async def admin_block_secure_model(
    payload: AdminSecureModelBlockRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    blocked = cognix_db.block_model(
        model_id = payload.model_id,
        provider_type = payload.provider_type or "",
        reason = payload.reason,
        blocked_by = current_subject,
    )
    allowed_sync = _sync_allowed_models_setting(
        model_id = payload.model_id,
        current_subject = current_subject,
        reason = payload.reason,
        remove = True,
    )
    side_effects = {
        **cognix_admin_secure_model_registry.build_secure_model_registry_blueprint()["sideEffects"],
        "databaseWrite": True,
        "blockedModelWrite": True,
        "organizationSettingsWrite": True,
        "changeLogWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_secure_model_blocked",
        resource_type = "blocked_model",
        resource_id = str(blocked.get("id") or payload.model_id),
        severity = "warning",
        metadata = {
            "modelId": payload.model_id,
            "providerType": payload.provider_type,
            "reason": payload.reason,
            "allowedModels": allowed_sync["allowedModels"],
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "blockedModel": _row(blocked),
        "allowedModels": allowed_sync["allowedModels"],
        "policyChangeLog": _row(allowed_sync["changeLog"]),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_secure_model_registry.COGNIX_MODEL_APPROVAL_SERVICE_VERSION,
    }


@router.post("/admin/models/secure-registry/access-decision")
async def admin_secure_model_access_decision(
    payload: AdminSecureModelDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_secure_model_registry_bundle()
    decision = cognix_admin_secure_model_registry.build_model_access_decision(
        model_id = payload.model_id,
        provider_type = payload.provider_type,
        role = payload.role,
        quantization = payload.quantization,
        local_only_active = payload.local_only_active,
        approved_models = bundle["approvedModels"],
        blocked_models = bundle["blockedModels"],
    )
    return {
        "username": current_subject,
        "decision": decision,
        "sideEffects": decision.get("sideEffects", {}),
        "plannerVersion": cognix_admin_secure_model_registry.COGNIX_SECURE_MODEL_REGISTRY_VERSION,
    }


@router.get("/admin/models/secure-registry/security-metadata")
async def admin_secure_model_security_metadata(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    metadata = cognix_db.list_model_security_metadata()
    return {
        "username": current_subject,
        "modelSecurityMetadata": _rows(metadata),
        "sideEffects": cognix_admin_secure_model_registry.build_secure_model_registry_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_secure_model_registry.COGNIX_MODEL_LICENSE_CHECKER_VERSION,
    }


@router.get("/knowledge/shared/blueprint")
async def shared_knowledge_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    blueprint = cognix_shared_knowledge_base.build_shared_knowledge_blueprint()
    return {
        "username": current_subject,
        "sharedKnowledgeBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_SHARED_KNOWLEDGE_BASE_VERSION,
    }


@router.get("/knowledge/shared/bases")
async def shared_knowledge_bases(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    bundle = _build_shared_knowledge_bundle()
    return {
        "username": current_subject,
        "knowledgeBases": _rows(bundle["knowledgeBases"]),
        "sideEffects": cognix_shared_knowledge_base.build_shared_knowledge_blueprint()["sideEffects"],
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_SHARED_KNOWLEDGE_BASE_VERSION,
    }


@router.post("/knowledge/shared/bases")
async def create_shared_knowledge_base(
    payload: SharedKnowledgeBaseRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    knowledge_base = cognix_db.create_knowledge_base(
        name = payload.name,
        description = payload.description or "",
        owner_username = current_subject,
        visibility = payload.visibility,
        project_id = payload.project_id,
    )
    side_effects = {
        **cognix_shared_knowledge_base.build_shared_knowledge_blueprint()["sideEffects"],
        "databaseWrite": True,
        "knowledgeBaseWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "shared_knowledge_base_created",
        resource_type = "knowledge_base",
        resource_id = str(knowledge_base.get("id") or ""),
        severity = "notice",
        metadata = {
            "name": payload.name,
            "visibility": payload.visibility,
            "projectId": payload.project_id,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "knowledgeBase": _row(knowledge_base),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_SHARED_KNOWLEDGE_BASE_VERSION,
    }


@router.get("/knowledge/shared/bases/{knowledge_base_id}/documents")
async def shared_knowledge_documents(
    knowledge_base_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    knowledge_base = cognix_db.get_knowledge_base(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code = 404, detail = "Knowledge base not found")
    bundle = _build_shared_knowledge_bundle(knowledge_base_id)
    return {
        "username": current_subject,
        "knowledgeBase": _row(knowledge_base),
        "documents": _rows(bundle["documents"]),
        "chunks": _rows(bundle["chunks"]),
        "permissions": _rows(bundle["permissions"]),
        "sideEffects": cognix_shared_knowledge_base.build_shared_knowledge_blueprint()["sideEffects"],
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_SHARED_KNOWLEDGE_BASE_VERSION,
    }


@router.post("/knowledge/shared/bases/{knowledge_base_id}/documents")
async def add_shared_knowledge_document(
    knowledge_base_id: str,
    payload: SharedKnowledgeDocumentRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    knowledge_base = cognix_db.get_knowledge_base(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code = 404, detail = "Knowledge base not found")
    document = cognix_db.create_knowledge_document(
        knowledge_base_id = knowledge_base_id,
        title = payload.title,
        content_text = payload.content,
        source_type = payload.source_type,
        source_uri = payload.source_uri or "",
        created_by = current_subject,
    )
    index_plan = cognix_shared_knowledge_base.build_document_index_plan(
        knowledge_base_id = knowledge_base_id,
        document_id = str(document.get("id") or ""),
        title = payload.title,
        content = payload.content,
        chunk_size = payload.chunk_size,
        overlap = payload.overlap,
    )
    chunks = cognix_db.replace_knowledge_chunks(
        knowledge_base_id = knowledge_base_id,
        document_id = str(document.get("id") or ""),
        chunks = index_plan["chunks"],
    )
    side_effects = {
        **index_plan.get("sideEffects", {}),
        "databaseWrite": True,
        "documentWrite": True,
        "chunkWrite": True,
        "auditWrite": True,
        "embeddingCall": False,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "shared_knowledge_document_indexed",
        resource_type = "knowledge_document",
        resource_id = str(document.get("id") or ""),
        severity = "notice",
        metadata = {
            "knowledgeBaseId": knowledge_base_id,
            "chunkCount": len(chunks),
            "embeddingCall": False,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "knowledgeBase": _row(knowledge_base),
        "document": _row(document),
        "indexPlan": index_plan,
        "chunks": _rows(chunks),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_ORGANIZATION_RAG_SERVICE_VERSION,
    }


@router.post("/knowledge/shared/bases/{knowledge_base_id}/permissions")
async def grant_shared_knowledge_permission(
    knowledge_base_id: str,
    payload: SharedKnowledgePermissionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    knowledge_base = cognix_db.get_knowledge_base(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code = 404, detail = "Knowledge base not found")
    permission = cognix_db.grant_knowledge_permission(
        knowledge_base_id = knowledge_base_id,
        document_id = payload.document_id or "",
        subject_type = payload.subject_type,
        subject_id = payload.subject_id,
        permission = payload.permission,
        granted_by = current_subject,
    )
    side_effects = {
        **cognix_shared_knowledge_base.build_shared_knowledge_blueprint()["sideEffects"],
        "databaseWrite": True,
        "permissionWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = payload.subject_id if payload.subject_type == "user" else None,
        actor_username = current_subject,
        action = "shared_knowledge_permission_granted",
        resource_type = "knowledge_permission",
        resource_id = str(permission.get("id") or ""),
        severity = "notice",
        metadata = {
            "knowledgeBaseId": knowledge_base_id,
            "subjectType": payload.subject_type,
            "subjectId": payload.subject_id,
            "permission": payload.permission,
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "permission": _row(permission),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_DOCUMENT_PERMISSION_FILTER_VERSION,
    }


@router.post("/knowledge/shared/bases/{knowledge_base_id}/query")
async def query_shared_knowledge_base(
    knowledge_base_id: str,
    payload: SharedKnowledgeQueryRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    knowledge_base = cognix_db.get_knowledge_base(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code = 404, detail = "Knowledge base not found")
    bundle = _build_shared_knowledge_bundle(knowledge_base_id)
    role = "admin" if auth_storage.is_admin(current_subject) else payload.role
    result = cognix_shared_knowledge_base.build_retrieval_result(
        query = payload.query,
        chunks = bundle["chunks"],
        documents = bundle["documents"],
        permissions = bundle["permissions"],
        username = current_subject,
        role = role,
        limit = payload.limit,
    )
    return {
        "username": current_subject,
        "knowledgeBase": _row(knowledge_base),
        "retrieval": result,
        "sideEffects": result.get("sideEffects", {}),
        "plannerVersion": cognix_shared_knowledge_base.COGNIX_ORGANIZATION_RAG_SERVICE_VERSION,
    }


@router.get("/admin/data-retention/blueprint")
async def admin_data_retention_blueprint(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_data_retention.build_data_retention_blueprint()
    return {
        "username": current_subject,
        "dataRetentionBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_RETENTION_SERVICE_VERSION,
    }


@router.get("/admin/data-retention")
async def admin_data_retention(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_data_retention_bundle()
    return {
        "username": current_subject,
        "policy": bundle["policy"],
        "policyRecord": _row(bundle["policyRecord"]) if bundle["policyRecord"] else None,
        "retentionPlan": bundle["retentionPlan"],
        "deletionJobs": _rows(bundle["deletionJobs"]),
        "privacyEvents": _rows(bundle["privacyEvents"]),
        "sideEffects": bundle["retentionPlan"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_RETENTION_SERVICE_VERSION,
    }


@router.put("/admin/data-retention/policy")
async def admin_update_data_retention_policy(
    payload: AdminDataRetentionPolicyRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    before_policy = _current_retention_policy()
    after_policy = dict(before_policy)
    after_policy.update(_retention_policy_payload_to_dict(payload))
    normalized_policy = cognix_admin_data_retention.normalize_retention_policy(after_policy)
    policy_record = cognix_db.upsert_retention_policy(
        policy = normalized_policy,
        updated_by = current_subject,
        reason = payload.reason or "",
    )
    side_effects = {
        **cognix_admin_data_retention.build_data_retention_blueprint()["sideEffects"],
        "databaseWrite": True,
        "retentionPolicyWrite": True,
        "privacyEventWrite": True,
        "auditWrite": True,
    }
    privacy_event = cognix_db.create_privacy_event(
        actor_username = current_subject,
        target_username = "",
        event_type = "retention_policy_updated",
        privacy_mode = str(normalized_policy.get("sensitivePromptMode") or "metadata_only"),
        content_readable = False,
        content_stored = False,
        metadata_only = True,
        event = {
            "before": before_policy,
            "after": normalized_policy,
            "reason": payload.reason or "",
            "sideEffects": side_effects,
        },
    )
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_data_retention_policy_updated",
        resource_type = "retention_policy",
        resource_id = str(policy_record.get("id") or "default"),
        severity = "warning",
        metadata = {
            "policyEventId": privacy_event.get("id"),
            "reason": payload.reason or "",
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "policy": normalized_policy,
        "policyRecord": _row(policy_record),
        "privacyEvent": _row(privacy_event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_RETENTION_SERVICE_VERSION,
    }


@router.post("/admin/data-retention/plan")
async def admin_data_retention_plan(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_data_retention_bundle()
    return {
        "username": current_subject,
        "retentionPlan": bundle["retentionPlan"],
        "policy": bundle["policy"],
        "sideEffects": bundle["retentionPlan"].get("sideEffects", {}),
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_RETENTION_SERVICE_VERSION,
    }


@router.post("/admin/data-retention/privacy-decision")
async def admin_privacy_decision(
    payload: AdminPrivacyDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    policy = _current_retention_policy()
    decision = cognix_admin_data_retention.build_privacy_decision(
        policy = policy,
        content = payload.content,
        e2ee_strict = payload.e2ee_strict,
    )
    side_effects = {
        **decision.get("sideEffects", {}),
        "databaseWrite": True,
        "privacyEventWrite": True,
        "auditWrite": True,
        "contentStore": False,
        "contentDelete": False,
    }
    privacy_event = cognix_db.create_privacy_event(
        actor_username = current_subject,
        target_username = payload.target_username or "",
        event_type = "privacy_decision_logged",
        privacy_mode = str(decision.get("storageMode") or "metadata_only"),
        content_readable = bool(decision.get("contentReadableByServer")),
        content_stored = bool(decision.get("contentStorageAllowed")),
        metadata_only = bool(decision.get("metadataOnly")),
        event = {
            "decision": decision,
            "targetUsername": payload.target_username or "",
            "metadata": payload.metadata,
            "contentLength": len(str(payload.content or "")),
            "sideEffects": side_effects,
        },
    )
    audit = cognix_db.create_audit_log(
        username = payload.target_username,
        actor_username = current_subject,
        action = "admin_privacy_decision_logged",
        resource_type = "privacy_event",
        resource_id = str(privacy_event.get("id") or ""),
        severity = "notice",
        metadata = {
            "privacyMode": decision.get("storageMode"),
            "contentReadableByServer": decision.get("contentReadableByServer"),
            "contentStorageAllowed": decision.get("contentStorageAllowed"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "decision": decision,
        "privacyEvent": _row(privacy_event),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_data_retention.COGNIX_PRIVACY_POLICY_SERVICE_VERSION,
    }


@router.post("/admin/data-retention/users/{username}/export-plan")
async def admin_user_export_plan(
    username: str,
    payload: AdminUserDataRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_data_retention_bundle()
    export_plan = cognix_admin_data_retention.build_user_export_plan(
        username = username,
        policy = bundle["policy"],
        threads = bundle["threads"],
        projects = bundle["projects"],
        messages = bundle["messages"],
        audit_logs = bundle["auditLogs"],
        include_content = payload.include_content,
    )
    side_effects = {
        **export_plan.get("sideEffects", {}),
        "auditWrite": True,
        "fileWrite": False,
        "contentStore": False,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_user_export_planned",
        resource_type = "user_data_export",
        resource_id = username,
        severity = "notice",
        metadata = {
            "reason": payload.reason,
            "outputFormat": payload.output_format,
            "contentIncluded": export_plan.get("contentIncluded"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "exportPlan": export_plan,
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_RETENTION_SERVICE_VERSION,
    }


@router.post("/admin/data-retention/users/{username}/deletion-plan")
async def admin_user_deletion_plan(
    username: str,
    payload: AdminUserDataRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    policy = _current_retention_policy()
    deletion_plan = cognix_admin_data_retention.build_user_deletion_plan(
        username = username,
        policy = policy,
        reason = payload.reason,
    )
    deletion_job = cognix_db.create_deletion_job(
        target_type = "user",
        target_id = username,
        requested_by = current_subject,
        job_type = "user_deletion",
        reason = payload.reason,
        approval_required = bool(deletion_plan.get("requiresApproval")),
        status = str(deletion_plan.get("status") or "requires_approval"),
        job = deletion_plan,
    )
    side_effects = {
        **deletion_plan.get("sideEffects", {}),
        "databaseWrite": True,
        "deletionJobWrite": True,
        "auditWrite": True,
        "contentDelete": False,
    }
    audit = cognix_db.create_audit_log(
        username = username,
        actor_username = current_subject,
        action = "admin_user_deletion_planned",
        resource_type = "deletion_job",
        resource_id = str(deletion_job.get("id") or ""),
        severity = "warning",
        metadata = {
            "reason": payload.reason,
            "jobStatus": deletion_job.get("status"),
            "requiresApproval": deletion_plan.get("requiresApproval"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "targetUsername": username,
        "deletionPlan": deletion_plan,
        "deletionJob": _row(deletion_job),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_DELETION_SERVICE_VERSION,
    }


@router.get("/admin/data-retention/deletion-jobs")
async def admin_deletion_jobs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    jobs = cognix_db.list_deletion_jobs(limit = 500)
    return {
        "username": current_subject,
        "deletionJobs": _rows(jobs),
        "sideEffects": cognix_admin_data_retention.build_data_retention_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_data_retention.COGNIX_DATA_DELETION_SERVICE_VERSION,
    }


@router.get("/admin/data-retention/privacy-events")
async def admin_privacy_events(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    events = cognix_db.list_privacy_events(limit = 500)
    return {
        "username": current_subject,
        "privacyEvents": _rows(events),
        "sideEffects": cognix_admin_data_retention.build_data_retention_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_data_retention.COGNIX_PRIVACY_POLICY_SERVICE_VERSION,
    }


@router.get("/admin/compliance/exports/blueprint")
async def admin_compliance_exports_blueprint(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_compliance_export.build_compliance_export_blueprint()
    return {
        "username": current_subject,
        "complianceExportBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_compliance_export.COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION,
    }


@router.get("/admin/compliance/exports")
async def admin_compliance_exports(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_compliance_export_bundle()
    return {
        "username": current_subject,
        "exports": _rows(bundle["exports"]),
        "exportJobs": _rows(bundle["exportJobs"]),
        "sideEffects": cognix_admin_compliance_export.build_compliance_export_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_compliance_export.COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION,
    }


@router.post("/admin/compliance/exports/plan")
async def admin_compliance_export_plan(
    payload: AdminComplianceExportRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_compliance_export_bundle()
    try:
        report = cognix_admin_compliance_export.build_compliance_report(
            report_type = payload.report_type,
            output_format = payload.output_format,
            generated_by = current_subject,
            token_events = bundle["tokenEvents"],
            activity_events = bundle["activityEvents"],
            security_events = bundle["securityEvents"],
            bans = bundle["bans"],
            approvals = bundle["approvals"],
            admin_chat_access_logs = bundle["adminChatAccessLogs"],
            audit_logs = bundle["auditLogs"],
        )
        job_plan = cognix_admin_compliance_export.build_export_job_plan(
            report = report,
            queued_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    return {
        "username": current_subject,
        "report": report,
        "exportJobPlan": job_plan,
        "sideEffects": report.get("sideEffects", {}),
        "plannerVersion": cognix_admin_compliance_export.COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION,
    }


@router.post("/admin/compliance/exports")
async def admin_create_compliance_export(
    payload: AdminComplianceExportRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_compliance_export_bundle()
    try:
        report = cognix_admin_compliance_export.build_compliance_report(
            report_type = payload.report_type,
            output_format = payload.output_format,
            generated_by = current_subject,
            token_events = bundle["tokenEvents"],
            activity_events = bundle["activityEvents"],
            security_events = bundle["securityEvents"],
            bans = bundle["bans"],
            approvals = bundle["approvals"],
            admin_chat_access_logs = bundle["adminChatAccessLogs"],
            audit_logs = bundle["auditLogs"],
        )
        job_plan = cognix_admin_compliance_export.build_export_job_plan(
            report = report,
            queued_by = current_subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    export = cognix_db.create_compliance_export(
        generated_by = current_subject,
        report = report,
    )
    job = cognix_db.create_export_job(
        export_id = str(export.get("id") or ""),
        queued_by = current_subject,
        job = job_plan,
    )
    side_effects = {
        **report.get("sideEffects", {}),
        "databaseWrite": True,
        "exportWrite": True,
        "exportJobWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_compliance_export_created",
        resource_type = "compliance_export",
        resource_id = str(export.get("id") or ""),
        severity = "notice",
        metadata = {
            "reportType": payload.report_type,
            "outputFormat": payload.output_format,
            "reason": payload.reason,
            "checksum": export.get("checksum"),
            "jobId": job.get("id"),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "export": _row(export),
        "exportJob": _row(job),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_compliance_export.COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION,
    }


@router.get("/admin/compliance/exports/{export_id}")
async def admin_compliance_export_detail(
    export_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    export = cognix_db.get_compliance_export(export_id)
    if export is None:
        raise HTTPException(status_code = 404, detail = "Compliance export not found")
    jobs = cognix_db.list_export_jobs(export_id = export_id)
    return {
        "username": current_subject,
        "export": _row(export),
        "exportJobs": _rows(jobs),
        "sideEffects": cognix_admin_compliance_export.build_compliance_export_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_compliance_export.COGNIX_COMPLIANCE_EXPORT_SERVICE_VERSION,
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


@router.get("/admin/notifications/blueprint")
async def admin_notifications_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    alerts = cognix_db.list_admin_alerts(limit = 200)
    notifications = cognix_db.list_notifications(limit = 200)
    blueprint = cognix_notifications.build_notification_blueprint(
        notifications = notifications,
        admin_alerts = alerts,
    )
    return {
        "notificationsBlueprint": blueprint,
        "plannerVersion": cognix_notifications.COGNIX_ADMIN_ALERT_SERVICE_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/admin/alerts")
async def admin_alerts(
    status_filter: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    alerts = cognix_db.list_admin_alerts(status = status_filter, limit = 500)
    blueprint = cognix_notifications.build_notification_blueprint(admin_alerts = alerts)
    return {
        "alerts": _rows(alerts),
        "summary": blueprint["summary"],
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_notifications.COGNIX_ADMIN_ALERT_SERVICE_VERSION,
    }


@router.patch("/admin/alerts/{alert_id}/acknowledge")
async def admin_acknowledge_alert(
    alert_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    alert = cognix_db.acknowledge_admin_alert(alert_id, acknowledged_by = current_subject)
    if alert is None:
        raise HTTPException(status_code = 404, detail = "Admin alert not found")
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_alert_acknowledged",
        resource_type = "admin_alert",
        resource_id = alert_id,
        severity = "notice",
        metadata = {"alertType": alert.get("alertType"), "sourceId": alert.get("sourceId")},
    )
    return {
        "alert": _row(alert),
        "auditLogId": audit.get("id"),
        "sideEffects": {"adminAlertWrite": True, "auditWrite": True},
        "plannerVersion": cognix_notifications.COGNIX_ADMIN_ALERT_SERVICE_VERSION,
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
    emitted = _emit_approval_notifications(
        request,
        event = "approval_approved" if payload.status == "approved" else "approval_denied",
        actor_username = current_subject,
    )
    return {
        "request": _row(request),
        "decisions": _rows(cognix_db.list_approval_decisions(request_id)),
        "notification": _row(emitted["notification"]),
        "adminAlert": _row(emitted["adminAlert"]),
        "auditLogId": audit.get("id"),
        "sideEffects": {
            "decisionWrite": True,
            "legacyPermissionWrite": request.get("request_type") == cognix_db.DEVELOPER_MODE_PERMISSION,
            "notificationWrite": True,
            "adminAlertWrite": True,
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


@router.get("/admin/vulnerability-scanner-contract")
async def admin_vulnerability_scanner_contract(
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    contract = cognix_admin_security.build_vulnerability_scanner_adapter_contract()
    return {
        "vulnerabilityScannerContract": contract,
        "plannerVersion": cognix_admin_security.COGNIX_VULNERABILITY_SCANNER_ADAPTER_VERSION,
        "sideEffects": contract.get("sideEffects", {}),
    }


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
        "persistedRiskScores": _rows(cognix_db.list_risk_scores(limit = 500)),
        "riskEvents": _rows(cognix_db.list_risk_events(limit = 500)),
        "riskRecommendations": _rows(cognix_db.list_risk_recommendations(limit = 500)),
        "threatSummary": bundle["threatReport"]["summary"],
        "sideEffects": bundle["riskScoring"]["sideEffects"],
    }


@router.post("/admin/risk-scores/aggregate")
async def admin_risk_scores_aggregate(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_security_bundle()
    persisted = cognix_db.persist_risk_scoring(
        bundle["riskScoring"],
        updated_by = current_subject,
    )
    side_effects = {
        **bundle["riskScoring"].get("sideEffects", {}),
        "databaseWrite": True,
        "riskScoreWrite": True,
        "riskEventWrite": True,
        "riskRecommendationWrite": True,
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_risk_scores_aggregated",
        resource_type = "risk_scores",
        resource_id = "latest",
        severity = "notice",
        metadata = {
            "riskScoringVersion": bundle["riskScoring"].get("scoringVersion"),
            "scoreCount": len(persisted["scores"]),
            "eventCount": len(persisted["events"]),
            "recommendationCount": len(persisted["recommendations"]),
            "sideEffects": side_effects,
        },
    )
    return {
        "riskScoring": bundle["riskScoring"],
        "persistedRiskScores": _rows(persisted["scores"]),
        "riskEvents": _rows(persisted["events"]),
        "riskRecommendations": _rows(persisted["recommendations"]),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
    }


@router.get("/admin/system-health/blueprint")
async def admin_system_health_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_admin_security.build_system_health_blueprint()
    return {
        "username": current_subject,
        "systemHealthBlueprint": blueprint,
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_admin_security.COGNIX_SYSTEM_HEALTH_VERSION,
    }


@router.get("/admin/system-health")
async def admin_system_health(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_security_bundle()
    return {
        "systemHealth": bundle["systemHealth"],
        "threatSummary": bundle["threatReport"]["summary"],
        "riskSummary": bundle["riskScoring"]["summary"],
        "snapshots": _rows(bundle["systemHealthSnapshots"]),
        "serviceHealthEvents": _rows(bundle["serviceHealthEvents"]),
        "sideEffects": bundle["systemHealth"]["sideEffects"],
    }


@router.post("/admin/system-health/snapshot")
async def admin_system_health_snapshot(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    bundle = _build_admin_security_bundle()
    health = bundle["systemHealth"]
    snapshot = cognix_db.create_system_health_snapshot(
        health = health,
        recorded_by = current_subject,
    )
    service_events = [
        cognix_db.create_service_health_event(
            service_id = str(service.get("id") or ""),
            service_label = str(service.get("label") or service.get("id") or ""),
            status = str(service.get("status") or "green"),
            event_type = "snapshot",
            severity = "critical" if service.get("status") == "red" else "warning" if service.get("status") == "yellow" else "notice",
            message = str(service.get("detail") or ""),
            event = service,
            recorded_by = current_subject,
        )
        for service in health.get("services", [])
        if service.get("status") in {"red", "yellow"}
    ]
    side_effects = {
        **health.get("sideEffects", {}),
        "databaseWrite": True,
        "snapshotWrite": True,
        "serviceEventWrite": bool(service_events),
        "auditWrite": True,
    }
    audit = cognix_db.create_audit_log(
        username = None,
        actor_username = current_subject,
        action = "admin_system_health_snapshot_created",
        resource_type = "system_health_snapshot",
        resource_id = str(snapshot.get("id") or ""),
        severity = "warning" if health.get("overallStatus") != "green" else "notice",
        metadata = {
            "overallStatus": health.get("overallStatus"),
            "alertCount": len(health.get("alerts") or []),
            "serviceEventCount": len(service_events),
            "sideEffects": side_effects,
        },
    )
    return {
        "username": current_subject,
        "systemHealth": health,
        "snapshot": _row(snapshot),
        "serviceHealthEvents": _rows(service_events),
        "auditLogId": audit.get("id"),
        "sideEffects": side_effects,
        "plannerVersion": cognix_admin_security.COGNIX_SYSTEM_HEALTH_VERSION,
    }


@router.get("/admin/system-health/snapshots")
async def admin_system_health_snapshots(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    snapshots = cognix_db.list_system_health_snapshots(limit = 500)
    return {
        "username": current_subject,
        "snapshots": _rows(snapshots),
        "sideEffects": cognix_admin_security.build_system_health_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_security.COGNIX_SYSTEM_HEALTH_VERSION,
    }


@router.get("/admin/system-health/service-events")
async def admin_system_health_service_events(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    events = cognix_db.list_service_health_events(limit = 500)
    return {
        "username": current_subject,
        "serviceHealthEvents": _rows(events),
        "sideEffects": cognix_admin_security.build_system_health_blueprint()["sideEffects"],
        "plannerVersion": cognix_admin_security.COGNIX_RUNTIME_HEALTH_CHECKER_VERSION,
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


@router.get("/admin/sensitive-audit/blueprint")
async def admin_sensitive_audit_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    logs = cognix_db.list_audit_logs(limit = 500)
    sensitive_logs = cognix_db.list_sensitive_action_logs(limit = 500)
    blueprint = cognix_sensitive_audit.build_sensitive_audit_blueprint(
        audit_logs = logs,
        sensitive_action_logs = sensitive_logs,
    )
    return {
        "sensitiveAuditBlueprint": blueprint,
        "plannerVersion": cognix_sensitive_audit.COGNIX_SENSITIVE_AUDIT_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/admin/sensitive-action-logs")
async def admin_sensitive_action_logs(
    username: str | None = None,
    actor_username: str | None = None,
    sensitive_category: str | None = None,
    query: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    logs = cognix_db.list_sensitive_action_logs(
        username = username,
        actor_username = actor_username,
        sensitive_category = sensitive_category,
        query = query,
        limit = 500,
    )
    blueprint = cognix_sensitive_audit.build_sensitive_audit_blueprint(sensitive_action_logs = logs)
    return {
        "sensitiveActionLogs": _rows(logs),
        "summary": blueprint["summary"],
        "immutabilityPolicy": blueprint["immutabilityPolicy"],
        "sideEffects": blueprint.get("sideEffects", {}),
        "plannerVersion": cognix_sensitive_audit.COGNIX_AUDIT_SEARCH_SERVICE_VERSION,
    }


@router.get("/admin/audit-governance-contract")
async def admin_audit_governance_contract(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    logs = cognix_db.list_audit_logs(limit = 500)
    contract = cognix_db.build_audit_governance_contract(logs)
    return {
        "auditGovernanceContract": contract,
        "plannerVersion": cognix_db.AUDIT_GOVERNANCE_CONTRACT_VERSION,
        "sideEffects": contract.get("sideEffects", {}),
    }


@router.get("/admin/database-blueprint")
async def admin_database_blueprint(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    blueprint = cognix_database_blueprint.build_database_blueprint()
    return {
        "databaseBlueprint": blueprint,
        "plannerVersion": cognix_database_blueprint.COGNIX_DATABASE_BLUEPRINT_VERSION,
        "sideEffects": blueprint.get("sideEffects", {}),
    }


@router.get("/admin/api-surface-contract")
async def admin_api_surface_contract(
    request: Request,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    contract = cognix_api_surface.build_api_surface_contract(_registered_api_routes(request))
    return {
        "apiSurfaceContract": contract,
        "plannerVersion": cognix_api_surface.COGNIX_API_SURFACE_CONTRACT_VERSION,
        "sideEffects": contract.get("sideEffects", {}),
    }


@router.get("/admin/mvp-readiness")
async def admin_mvp_readiness(
    request: Request,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    api_surface_contract = cognix_api_surface.build_api_surface_contract(_registered_api_routes(request))
    database_blueprint = cognix_database_blueprint.build_database_blueprint()
    service_topology = cognix_module_registry.build_module_service_topology()
    contract = cognix_mvp_readiness.build_mvp_readiness_contract(
        api_surface_contract = api_surface_contract,
        database_blueprint = database_blueprint,
        service_topology = service_topology,
    )
    return {
        "mvpReadiness": contract,
        "plannerVersion": cognix_mvp_readiness.COGNIX_MVP_READINESS_VERSION,
        "sideEffects": contract.get("sideEffects", {}),
    }


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
