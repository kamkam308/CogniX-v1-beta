# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Declarative CogniX module registry.

Modules describe optional product capabilities without mutating routes, UI, or
permissions. Activation remains a separate guarded workflow.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_MODULE_REGISTRY_VERSION = "cognix_module_registry_v1"
COGNIX_MODULE_MANIFEST_SCHEMA_VERSION = "cognix_module_manifest_schema_v1"
COGNIX_MODULE_MANIFEST_BUNDLE_VERSION = "cognix_module_manifest_bundle_v1"

MANIFEST_REQUIRED_FIELDS = (
    "id",
    "displayName",
    "editionTargets",
    "status",
    "capabilities",
    "routes",
    "permissions",
    "tools",
    "defaultModels",
    "uiPanels",
    "dependencies",
)
MANIFEST_LIST_FIELDS = (
    "editionTargets",
    "capabilities",
    "routes",
    "permissions",
    "tools",
    "defaultModels",
    "uiPanels",
    "dependencies",
)
MANIFEST_STATUS_VALUES = {"enabled", "planned"}


MODULE_MANIFESTS: list[dict[str, Any]] = [
    {
        "id": "cognix-local-core",
        "displayName": "CogniX Local Core",
        "editionTargets": ["free", "local", "developer"],
        "status": "enabled",
        "capabilities": [
            "chat_local",
            "model_registry",
            "module_registry",
            "module_manifest_registry",
            "hardware_profiler",
            "model_recommender",
            "model_pack_registry",
        ],
        "routes": [
            "/api/cognix/models/registry",
            "/api/cognix/models/packs",
            "/api/cognix/hardware/profile",
            "/api/cognix/modules/registry",
            "/api/cognix/modules/manifests",
            "/api/cognix/modules/plan",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["chat", "model-selector"],
        "dependencies": [],
    },
    {
        "id": "cognix-model-lifecycle",
        "displayName": "CogniX Model Lifecycle",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": ["model_packs", "install_planning", "load_unload_planning", "cache_load_planning", "hardware_fit", "cache_policy"],
        "routes": ["/api/cognix/models/packs", "/api/cognix/models/lifecycle-plan", "/api/cognix/models/cache/load-plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-3b-q4", "ollama-qwen-4b-local"],
        "uiPanels": ["model-selector", "settings-models"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-optimization-engine",
        "displayName": "CogniX Optimization Engine",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "optimization_capability_registry",
            "benchmark_gated_experiments",
            "adaptive_quantization",
            "quantization_advisor",
            "model_variant_registry",
            "performance_predictor",
            "cost_optimizer",
            "provider_pricing_store",
            "execution_cost_planning",
            "privacy_aware_provider_selection",
            "semantic_cache_planning",
            "kv_cache_eviction_planning",
            "prompt_compression_planning",
            "rag_compression_planning",
            "speculative_decoding_planning",
        ],
        "routes": [
            "/api/cognix/optimizations/capabilities",
            "/api/cognix/optimizations/plan",
            "/api/cognix/optimizations/experiment-plan",
            "/api/cognix/quantization/variants",
            "/api/cognix/quantization/plan",
            "/api/cognix/quantization/profiles",
            "/api/cognix/costs/providers",
            "/api/cognix/costs/plan",
            "/api/cognix/costs/logs",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["developer-workflow", "settings-models"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-worker-queue"],
    },
    {
        "id": "cognix-prompt-compression",
        "displayName": "CogniX Prompt Compression",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "prompt_compression",
            "importance_ranking",
            "compressed_context_store",
            "compression_evaluation",
            "context_optimized_badge",
        ],
        "routes": [
            "/api/cognix/prompt-compression/blueprint",
            "/api/cognix/prompt-compression/plan",
            "/api/cognix/prompt-compression/contexts",
            "/api/cognix/prompt-compression/contexts/{context_id}",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat", "settings-memory"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager"],
    },
    {
        "id": "cognix-intent-prediction",
        "displayName": "CogniX Intent Prediction",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "intent_prediction",
            "domain_probability",
            "preload_planning",
            "single_useful_suggestion",
            "abrupt_domain_change_detection",
        ],
        "routes": [
            "/api/cognix/intent/blueprint",
            "/api/cognix/intent/predict",
            "/api/cognix/intent/predictions",
            "/api/cognix/intent/preload-events",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-worker-queue"],
    },
    {
        "id": "cognix-dynamic-ui",
        "displayName": "CogniX Dynamic UI",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "ui_layout_profiles",
            "adaptive_panels",
            "project_type_layout_mapping",
            "theme_safe_layout_planning",
            "mobile_desktop_layout_planning",
        ],
        "routes": [
            "/api/cognix/dynamic-ui/blueprint",
            "/api/cognix/dynamic-ui/profile",
            "/api/cognix/dynamic-ui/profiles",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["project-settings", "chat"],
        "dependencies": ["cognix-local-core", "cognix-projects"],
    },
    {
        "id": "cognix-background-agents",
        "displayName": "CogniX Autonomous Background Agents",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "background_job_planning",
            "agent_queue_contract",
            "progress_tracking",
            "notification_planning",
            "night_mode_respect",
        ],
        "routes": [
            "/api/cognix/background-agents/blueprint",
            "/api/cognix/background-agents/job-plan",
            "/api/cognix/background-agents/jobs",
            "/api/cognix/background-agents/jobs/{job_id}",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["activity-center", "developer-workflow"],
        "dependencies": ["cognix-local-core", "cognix-worker-queue", "cognix-integrations"],
    },
    {
        "id": "cognix-ai-timeline",
        "displayName": "CogniX AI Timeline",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "project_timeline_events",
            "timeline_event_classification",
            "project_history_store",
            "timeline_filtering",
            "timeline_search",
        ],
        "routes": [
            "/api/cognix/timeline/blueprint",
            "/api/cognix/timeline/events",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["project-timeline", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-projects"],
    },
    {
        "id": "cognix-thinking-status",
        "displayName": "CogniX Thinking Status",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": ["visible_thinking_timeline", "technical_redaction", "progress_status"],
        "routes": ["/api/cognix/thinking/plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle"],
    },
    {
        "id": "cognix-response-reflection",
        "displayName": "CogniX Response Reflection",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "response_quality_evaluation",
            "confidence_scoring",
            "verification_recommendation",
            "reflection_logs",
            "raw_reasoning_redaction",
        ],
        "routes": [
            "/api/cognix/reflection/evaluate",
            "/api/cognix/reflection/evaluations",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat"],
        "dependencies": ["cognix-local-core", "cognix-thinking-status"],
    },
    {
        "id": "cognix-multi-draft-generation",
        "displayName": "CogniX Multi-Draft Generation",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "style_profile_registry",
            "multi_draft_planning",
            "response_variant_store",
            "post_generation_ranking_plan",
            "on_demand_variant_generation",
        ],
        "routes": [
            "/api/cognix/drafts/styles",
            "/api/cognix/drafts/plan",
            "/api/cognix/drafts/variants",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat"],
        "dependencies": ["cognix-local-core", "cognix-response-reflection"],
    },
    {
        "id": "cognix-ai-debate",
        "displayName": "CogniX AI Debate",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "debate_role_registry",
            "bounded_debate_planning",
            "judge_synthesis_planning",
            "debate_round_store",
            "public_argument_summaries",
        ],
        "routes": [
            "/api/cognix/debate/roles",
            "/api/cognix/debate/plan",
            "/api/cognix/debate/sessions",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat"],
        "dependencies": ["cognix-local-core", "cognix-response-reflection", "cognix-multi-draft-generation"],
    },
    {
        "id": "cognix-tool-discovery",
        "displayName": "CogniX Automatic Tool Discovery",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "project_tool_need_detection",
            "tool_capability_registry",
            "tool_recommendation_store",
            "installed_tool_snapshot",
            "no_auto_install_guardrail",
        ],
        "routes": [
            "/api/cognix/tools/discovery/capabilities",
            "/api/cognix/tools/discovery/analyze",
            "/api/cognix/tools/recommendations",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat", "project-settings", "command-palette"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
    },
    {
        "id": "cognix-context-graph",
        "displayName": "CogniX Live Context Graph",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "context_graph_snapshot",
            "entity_extraction",
            "relation_builder",
            "graph_store",
            "project_context_map",
        ],
        "routes": [
            "/api/cognix/context/graph/blueprint",
            "/api/cognix/context/graph/build",
            "/api/cognix/context/graph/snapshots",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["project-settings"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager", "cognix-projects"],
    },
    {
        "id": "cognix-memory-manager",
        "displayName": "CogniX Memory Manager",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": ["central_memory_layers", "memory_policy", "conversation_summarization_planning", "document_memory_planning"],
        "routes": ["/api/cognix/memory/blueprint", "/api/cognix/memory/plan", "/api/cognix/context/pack"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-thinking-status"],
    },
    {
        "id": "cognix-long-term-skill-memory",
        "displayName": "CogniX Long Term Skill Memory",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "skill_memory_candidates",
            "preference_extraction",
            "memory_approval_flow",
            "user_memory_controls",
            "context_injection_planning",
        ],
        "routes": [
            "/api/cognix/memory/skills/blueprint",
            "/api/cognix/memory/skills/candidates",
            "/api/cognix/memory/skills",
            "/api/cognix/memory/skills/export",
            "/api/cognix/memory/skills/injection-plan",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["settings-memory", "chat"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager"],
    },
    {
        "id": "cognix-live-memory-editing",
        "displayName": "CogniX Live Memory Editing",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "live_memory_editor",
            "memory_versioning",
            "memory_search",
            "memory_merge",
            "memory_export",
            "sensitive_memory_controls",
        ],
        "routes": [
            "/api/cognix/memory/editor/blueprint",
            "/api/cognix/memory/editor/items",
            "/api/cognix/memory/editor/merge",
            "/api/cognix/memory/editor/export",
            "/api/cognix/memory/editor/audit-logs",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["settings-memory", "chat"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager", "cognix-long-term-skill-memory"],
    },
    {
        "id": "cognix-ai-simulation",
        "displayName": "CogniX AI Simulation",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "simulation_engine",
            "synthetic_user_generation",
            "load_scenario_runner",
            "simulation_metrics",
            "risk_report",
            "bottleneck_detection",
            "queue_safe_simulation",
        ],
        "routes": [
            "/api/cognix/simulations/blueprint",
            "/api/cognix/simulations/runs",
            "/api/cognix/simulations/runs/{run_id}",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["developer-workflow", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-worker-queue", "cognix-projects"],
    },
    {
        "id": "cognix-ai-sandbox",
        "displayName": "CogniX AI Sandbox",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "sandbox_manager",
            "isolated_runtime",
            "experiment_runner",
            "rollback_service",
            "minimal_config_copy",
            "secret_isolation",
            "sandbox_badge",
        ],
        "routes": [
            "/api/cognix/sandbox/blueprint",
            "/api/cognix/sandbox/plans",
            "/api/cognix/sandbox/runs",
            "/api/cognix/sandbox/runs/{run_id}",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["developer-workflow", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-worker-queue", "cognix-codex-secure-agent"],
    },
    {
        "id": "cognix-ai-workflow-recorder",
        "displayName": "CogniX AI Workflow Recorder",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "workflow_recording",
            "workflow_steps_store",
            "workflow_replay_planning",
            "workflow_template_registry",
            "workflow_export",
            "workflow_sharing_controls",
        ],
        "routes": [
            "/api/cognix/workflows/blueprint",
            "/api/cognix/workflows/templates",
            "/api/cognix/workflows/record",
            "/api/cognix/workflows",
            "/api/cognix/workflows/{workflow_id}/export",
            "/api/cognix/workflows/{workflow_id}/run-plan",
            "/api/cognix/workflows/{workflow_id}/runs",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["developer-workflow", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-worker-queue"],
    },
    {
        "id": "cognix-projects",
        "displayName": "CogniX Projects",
        "editionTargets": ["free", "developer", "business", "university"],
        "status": "enabled",
        "capabilities": ["project_memory", "project_default_model", "specialized_projects", "project_expert_routing", "generalist_verifier"],
        "routes": ["/projects", "/api/cognix/project-model-defaults", "/api/cognix/project-experts/registry", "/api/cognix/projects/{project_id}/expert-plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-code-small", "cognix-math-small", "cognix-physics-small"],
        "uiPanels": ["project-sidebar", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-thinking-status", "cognix-memory-manager"],
    },
    {
        "id": "cognix-onboarding",
        "displayName": "CogniX Intelligent Onboarding",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": ["hardware_onboarding", "starter_pack_recommendation", "edition_guidance"],
        "routes": ["/api/cognix/onboarding/plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["onboarding"],
        "dependencies": ["cognix-local-core", "cognix-projects", "cognix-memory-manager"],
    },
    {
        "id": "cognix-rag",
        "displayName": "CogniX RAG",
        "editionTargets": ["free", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "document_memory",
            "rag_source_registry",
            "rag_indexing_planning",
            "source_permission_gates",
            "retrieval_planning",
            "citations",
        ],
        "routes": [
            "/api/cognix/rag/sources",
            "/api/cognix/rag/indexing-plan",
            "/api/cognix/rag/plan",
            "/api/cognix/context/pack",
        ],
        "permissions": ["authenticated", "rag:read", "rag:write"],
        "tools": ["google-drive"],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["project-documents"],
        "dependencies": ["cognix-local-core", "cognix-projects"],
    },
    {
        "id": "cognix-fine-tuning",
        "displayName": "CogniX Fine-tuning",
        "editionTargets": ["developer", "enterprise"],
        "status": "planned",
        "capabilities": [
            "dataset_validation",
            "qlora_planning",
            "cloud_training_targets",
            "cloud_training_handoff",
            "ceo_cloud_training_bypass",
            "adapter_library",
        ],
        "routes": ["/api/cognix/fine-tuning/plan", "/api/cognix/fine-tuning/cloud-handoff-plan"],
        "permissions": ["developer_mode"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["dataset-manager", "lora-manager"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-worker-queue",
        "displayName": "CogniX Worker Queue",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "worker_queue_registry",
            "long_running_job_planning",
            "worker_job_specs",
            "cloud_training_job_specs",
            "rag_indexing_job_specs",
            "benchmark_job_planning",
        ],
        "routes": [
            "/api/cognix/workers/registry",
            "/api/cognix/workers/plan",
            "/api/cognix/workers/job-spec-plan",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["developer-workflow", "settings-models"],
        "dependencies": ["cognix-local-core", "cognix-rag", "cognix-fine-tuning"],
    },
    {
        "id": "cognix-research-watch",
        "displayName": "CogniX Research Watch",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["technology_watch", "research_triage", "hype_filter", "benchmark_gate", "experimental_module_planning"],
        "routes": ["/api/cognix/research/watch-registry", "/api/cognix/research/integration-plan"],
        "permissions": ["authenticated"],
        "tools": ["hugging-face", "github"],
        "defaultModels": ["cognix-research-3b-q4"],
        "uiPanels": ["research-watch", "developer-workflow"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-memory-manager"],
    },
    {
        "id": "cognix-integrations",
        "displayName": "CogniX Integrations",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["tool_registry", "integration_status", "permissions_audit", "tool_permission_matrix"],
        "routes": ["/api/cognix/integrations/status", "/api/cognix/tools/registry", "/api/cognix/tools/permission-matrix"],
        "permissions": ["authenticated"],
        "tools": ["github", "google-drive", "gmail", "notion"],
        "defaultModels": [],
        "uiPanels": ["integrations-settings"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-codex-secure-agent",
        "displayName": "CogniX Codex Secure Agent",
        "editionTargets": ["developer", "enterprise"],
        "status": "planned",
        "capabilities": ["feature_request", "branch_pipeline", "tests_build_preview"],
        "routes": ["/api/cognix/tools/plan"],
        "permissions": ["developer_mode"],
        "tools": ["codex-secure-agent", "github"],
        "defaultModels": ["cognix-code-small"],
        "uiPanels": ["developer-workflow"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
    },
    {
        "id": "cognix-enterprise-foundation",
        "displayName": "CogniX Enterprise Foundation",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["organizations", "rbac", "sso_planning", "education_spaces", "audit_logs", "deployment_targets"],
        "routes": [
            "/api/cognix/admin/audit-logs",
            "/api/cognix/admin/permissions/{username}",
            "/api/cognix/governance/blueprint",
            "/api/cognix/governance/plan",
        ],
        "permissions": ["admin"],
        "tools": ["sharepoint", "microsoft-teams", "google-workspace"],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["admin-security", "organization-settings", "education-admin", "deployment-settings"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
    },
    {
        "id": "cognix-deployment-manager",
        "displayName": "CogniX Deployment Manager",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["deployment_targets", "gpu_scheduler_planning", "monitoring_plan", "autoscaling_plan"],
        "routes": ["/api/cognix/deployments/targets", "/api/cognix/deployments/plan"],
        "permissions": ["admin"],
        "tools": ["github", "cloud-provider", "microsoft-teams"],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["deployment-settings", "admin-security"],
        "dependencies": ["cognix-local-core", "cognix-integrations", "cognix-enterprise-foundation"],
    },
]


def _manifest_ids() -> set[str]:
    return {str(item.get("id")) for item in MODULE_MANIFESTS}


def _dependency_status(module: dict[str, Any]) -> dict[str, Any]:
    manifest_ids = _manifest_ids()
    dependencies = [
        str(item) for item in module.get("dependencies") or [] if item
    ]
    missing = [item for item in dependencies if item not in manifest_ids]
    return {
        "dependencies": dependencies,
        "missingDependencies": missing,
        "ready": not missing,
    }


def _check_record(check_id: str, passed: bool, detail: str, **metadata: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": check_id,
        "status": "pass" if passed else "fail",
        "detail": detail,
    }
    record.update(metadata)
    return record


def _validate_module_manifest(module: dict[str, Any], manifest_ids: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    module_id = str(module.get("id") or "")

    missing_fields = [field for field in MANIFEST_REQUIRED_FIELDS if field not in module]
    if missing_fields:
        errors.append("required_fields_missing")
    checks.append(
        _check_record(
            "required_fields",
            not missing_fields,
            "Tous les champs manifestes obligatoires sont declares.",
            missingFields = missing_fields,
        )
    )

    invalid_list_fields = [field for field in MANIFEST_LIST_FIELDS if field in module and not isinstance(module.get(field), list)]
    if invalid_list_fields:
        errors.append("list_fields_invalid")
    checks.append(
        _check_record(
            "typed_list_fields",
            not invalid_list_fields,
            "Les champs liste du manifeste restent normalises.",
            invalidFields = invalid_list_fields,
        )
    )

    status = str(module.get("status") or "")
    invalid_status = status not in MANIFEST_STATUS_VALUES
    if invalid_status:
        errors.append("status_invalid")
    checks.append(
        _check_record(
            "status_value",
            not invalid_status,
            "Le statut du module fait partie du contrat supporte.",
            allowedStatuses = sorted(MANIFEST_STATUS_VALUES),
        )
    )

    invalid_routes = [
        str(route)
        for route in module.get("routes") or []
        if not str(route).startswith("/")
    ]
    if invalid_routes:
        errors.append("routes_invalid")
    checks.append(
        _check_record(
            "declared_routes",
            bool(module.get("routes")) and not invalid_routes,
            "Les routes backend/UI du module sont declarees sans mutation runtime.",
            invalidRoutes = invalid_routes,
        )
    )

    if not module.get("permissions"):
        errors.append("permissions_missing")
    checks.append(
        _check_record(
            "declared_permissions",
            bool(module.get("permissions")),
            "Les permissions requises sont declarees avant activation.",
        )
    )

    dependencies = [str(item) for item in module.get("dependencies") or [] if item]
    missing_dependencies = [item for item in dependencies if item not in manifest_ids]
    if missing_dependencies:
        errors.append("dependencies_missing")
    checks.append(
        _check_record(
            "dependency_resolution",
            not missing_dependencies,
            "Les dependances module se resolvent dans la registry native.",
            missingDependencies = missing_dependencies,
        )
    )

    if not module_id.startswith("cognix-"):
        warnings.append("module_id_prefix_non_standard")
    checks.append(
        _check_record(
            "stable_module_id",
            bool(module_id) and module_id.startswith("cognix-"),
            "L'identifiant module reste stable et namespace CogniX.",
        )
    )

    return {
        "moduleId": module_id,
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def _module_record(module: dict[str, Any]) -> dict[str, Any]:
    record = deepcopy(module)
    dependency_state = _dependency_status(record)
    record["dependencyState"] = dependency_state
    record["activationState"] = (
        "ready"
        if record.get("status") == "enabled" and dependency_state["ready"]
        else "planned"
        if dependency_state["ready"]
        else "blocked"
    )
    record["riskLevel"] = (
        "high"
        if "admin" in record.get("permissions", [])
        else "medium"
        if "developer_mode" in record.get("permissions", [])
        else "low"
    )
    return record


def build_module_registry() -> dict[str, Any]:
    modules = [_module_record(module) for module in MODULE_MANIFESTS]
    return {
        "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
        "mode": "declarative_dry_run",
        "modules": modules,
        "summary": {
            "moduleCount": len(modules),
            "enabledCount": sum(1 for item in modules if item.get("status") == "enabled"),
            "plannedCount": sum(1 for item in modules if item.get("status") == "planned"),
            "blockedCount": sum(1 for item in modules if item.get("activationState") == "blocked"),
            "uiMutationAllowed": False,
            "routeMutationAllowed": False,
        },
        "globalPolicies": {
            "declarativeManifestRequired": True,
            "manifestSchemaVersion": COGNIX_MODULE_MANIFEST_SCHEMA_VERSION,
            "dependenciesMustResolve": True,
            "permissionsMustBeDeclared": True,
            "activationRequiresAudit": True,
            "frontendCannotSelfRegisterModules": True,
            "runtimeRouteMutationAllowed": False,
        },
        "sideEffects": {
            "moduleActivation": False,
            "routeRegistration": False,
            "uiMutation": False,
            "permissionWrite": False,
            "toolExecution": False,
            "secretRead": False,
        },
    }


def build_module_manifest_bundle(edition: str | None = None) -> dict[str, Any]:
    normalized_edition = str(edition).strip().lower() if edition else None
    manifest_ids = _manifest_ids()
    all_modules = [_module_record(module) for module in MODULE_MANIFESTS]
    modules = [
        module
        for module in all_modules
        if normalized_edition is None or normalized_edition in {str(item).lower() for item in module.get("editionTargets", [])}
    ]
    ids = [str(module.get("id")) for module in modules]
    duplicate_ids = sorted({module_id for module_id in ids if ids.count(module_id) > 1})
    manifests: list[dict[str, Any]] = []
    validation_by_module: dict[str, Any] = {}

    for module in modules:
        manifest = deepcopy(module)
        manifest["kind"] = "cognix.module.manifest"
        manifest["schemaVersion"] = COGNIX_MODULE_MANIFEST_SCHEMA_VERSION
        manifest["manifestVersion"] = f"{manifest.get('id')}@{COGNIX_MODULE_MANIFEST_SCHEMA_VERSION}"
        manifest["declaredBy"] = "backend_source"
        manifest["runtimeMutationAllowed"] = False
        validation = _validate_module_manifest(manifest, manifest_ids)
        manifest["manifestValidation"] = validation
        validation_by_module[str(manifest.get("id"))] = validation
        manifests.append(manifest)

    invalid_ids = [
        module_id
        for module_id, validation in validation_by_module.items()
        if not validation.get("ready")
    ]
    if duplicate_ids:
        invalid_ids.extend(duplicate_ids)

    return {
        "bundleVersion": COGNIX_MODULE_MANIFEST_BUNDLE_VERSION,
        "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
        "schemaVersion": COGNIX_MODULE_MANIFEST_SCHEMA_VERSION,
        "mode": "declarative_dry_run",
        "editionFilter": normalized_edition,
        "contract": {
            "sourceOfTruth": "backend_source_manifest",
            "declarativeManifestRequired": True,
            "dependenciesMustResolve": True,
            "permissionsMustBeDeclared": True,
            "activationRequiresAudit": True,
            "runtimeRouteMutationAllowed": False,
            "frontendSelfRegistrationAllowed": False,
            "directModelExecutionAllowed": False,
            "toolExecutionRequiresPlan": True,
        },
        "summary": {
            "manifestCount": len(manifests),
            "invalidManifestCount": len(set(invalid_ids)),
            "duplicateIdCount": len(duplicate_ids),
            "editionFilterApplied": normalized_edition is not None,
        },
        "moduleIds": [str(item.get("id")) for item in manifests],
        "manifests": manifests,
        "validation": {
            "ready": not invalid_ids,
            "invalidManifestIds": sorted(set(invalid_ids)),
            "duplicateIds": duplicate_ids,
            "modules": validation_by_module,
        },
        "sideEffects": {
            "moduleActivation": False,
            "routeRegistration": False,
            "uiMutation": False,
            "permissionWrite": False,
            "toolExecution": False,
            "secretRead": False,
            "modelLoad": False,
            "trainingRun": False,
        },
    }


def build_module_activation_plan(module_id: str) -> dict[str, Any]:
    registry = build_module_registry()
    module = next(
        (item for item in registry["modules"] if item.get("id") == module_id),
        None,
    )
    if module is None:
        return {
            "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
            "mode": "dry_run",
            "moduleId": module_id,
            "status": "unknown_module",
            "allowedToActivate": False,
            "steps": [
                {
                    "id": "verify_manifest",
                    "status": "blocked",
                    "detail": "Module absent de la registry CogniX.",
                }
            ],
            "sideEffects": registry["sideEffects"],
        }

    dependency_ready = bool(module.get("dependencyState", {}).get("ready"))
    already_enabled = module.get("status") == "enabled"
    allowed_to_activate = dependency_ready and not already_enabled
    return {
        "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
        "mode": "dry_run",
        "moduleId": module.get("id"),
        "displayName": module.get("displayName"),
        "status": module.get("activationState"),
        "allowedToActivate": allowed_to_activate,
        "humanApprovalRequired": True,
        "module": module,
        "steps": [
            {
                "id": "verify_manifest",
                "status": "complete",
                "detail": "Manifest declaratif present.",
            },
            {
                "id": "verify_dependencies",
                "status": "complete" if dependency_ready else "blocked",
                "detail": "Dependances resolues dans la registry locale.",
            },
            {
                "id": "verify_permissions",
                "status": "complete" if module.get("permissions") else "blocked",
                "detail": "Permissions declarees avant activation.",
            },
            {
                "id": "dry_run_guard",
                "status": "complete",
                "detail": "Aucune route, permission ou UI n'est modifiee pendant ce plan.",
            },
        ],
        "sideEffects": registry["sideEffects"],
    }
