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
            "architecture_decision_contract",
            "orchestrator_runtime_plan",
        ],
        "routes": [
            "/api/cognix/models/registry",
            "/api/cognix/models/packs",
            "/api/cognix/hardware/profile",
            "/api/cognix/orchestrator/plan",
            "/api/cognix/runtime/plan",
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
        "id": "cognix-pulse",
        "displayName": "CogniX Pulse",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "activity_feed",
            "daily_digest",
            "event_collection",
            "event_prioritization",
            "pulse_report_generation",
            "local_privacy_preserving_summary",
            "scheduled_activity_summary",
            "admin_activity_signal",
        ],
        "routes": [
            "/api/cognix/pulse",
            "/api/cognix/pulse/blueprint",
            "/api/cognix/pulse/preview",
            "/api/cognix/pulse/generate",
        ],
        "permissions": ["authenticated", "pulse:read", "pulse:configure"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["sidebar", "dashboard", "activity-center"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-library",
        "displayName": "CogniX Library",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "asset_library",
            "asset_metadata_extraction",
            "library_search",
            "asset_type_classification",
            "rag_candidate_detection",
            "dataset_candidate_detection",
            "asset_permission_scope",
            "library_audit_logs",
        ],
        "routes": [
            "/api/cognix/library",
            "/api/cognix/library/blueprint",
            "/api/cognix/library/search",
        ],
        "permissions": ["authenticated", "library:read", "library:write", "library:share", "library:delete"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["library", "project-files", "model-hub"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-scheduled",
        "displayName": "CogniX Scheduled",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "scheduled_tasks",
            "cron_schedule_planning",
            "queue_first_execution",
            "scheduled_permission_checker",
            "scheduled_report_generator",
            "scheduled_run_audit",
            "creator_permission_ceiling",
            "recoverable_scheduled_errors",
        ],
        "routes": [
            "/api/cognix/scheduled-tasks",
            "/api/cognix/scheduled-tasks/blueprint",
            "/api/cognix/scheduled-tasks/plan",
            "/api/cognix/scheduled-tasks/{task_id}/run-plan",
            "/api/cognix/scheduled-tasks/{task_id}/run",
        ],
        "permissions": [
            "authenticated",
            "scheduled:read",
            "scheduled:create",
            "scheduled:update",
            "scheduled:delete",
            "scheduled:admin",
        ],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["scheduled", "activity-center", "project-automation"],
        "dependencies": ["cognix-local-core", "cognix-library", "cognix-worker-queue"],
    },
    {
        "id": "cognix-images",
        "displayName": "CogniX Images",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "text_to_image_planning",
            "image_edit_planning",
            "image_analysis_planning",
            "image_variant_planning",
            "image_safety_check",
            "image_asset_library_link",
            "image_history",
            "queue_first_image_runtime",
        ],
        "routes": [
            "/api/cognix/images",
            "/api/cognix/images/blueprint",
            "/api/cognix/images/plan",
        ],
        "permissions": [
            "authenticated",
            "images:generate",
            "images:edit",
            "images:analyze",
            "images:share",
        ],
        "tools": [],
        "defaultModels": ["cognix-image-default"],
        "uiPanels": ["images", "library", "project-assets"],
        "dependencies": ["cognix-local-core", "cognix-library", "cognix-worker-queue"],
    },
    {
        "id": "cognix-apps",
        "displayName": "CogniX Apps",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "app_manifest_registry",
            "app_permission_scanning",
            "oauth_connection_planning",
            "app_runtime_adapter",
            "app_connection_audit",
            "app_revocation",
            "tool_registry_bridge",
            "token_safe_registry",
        ],
        "routes": [
            "/api/cognix/apps",
            "/api/cognix/apps/blueprint",
            "/api/cognix/apps/registry",
            "/api/cognix/apps/plan",
            "/api/cognix/apps/connections",
        ],
        "permissions": [
            "authenticated",
            "apps:read",
            "apps:connect",
            "apps:disconnect",
            "apps:admin",
        ],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["apps", "settings-integrations", "tool-registry"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
    },
    {
        "id": "cognix-command-palette",
        "displayName": "CogniX Command Palette",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "global_command_palette",
            "command_registry",
            "permission_aware_command_filter",
            "quick_navigation",
            "command_usage_logging",
            "dry_run_command_plans",
        ],
        "routes": [
            "/api/cognix/command-palette/blueprint",
            "/api/cognix/command-palette/search",
            "/api/cognix/command-palette/plan",
            "/api/cognix/command-palette/usage",
        ],
        "permissions": ["authenticated", "command_palette:use", "command_palette:admin"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["command-palette", "global-navigation"],
        "dependencies": ["cognix-local-core", "cognix-tool-discovery"],
    },
    {
        "id": "cognix-model-lifecycle",
        "displayName": "CogniX Model Lifecycle",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "model_packs",
            "install_planning",
            "load_unload_planning",
            "cache_load_planning",
            "preload_execution_contract",
            "hardware_fit",
            "cache_policy",
        ],
        "routes": [
            "/api/cognix/models/packs",
            "/api/cognix/models/lifecycle-plan",
            "/api/cognix/models/cache/load-plan",
            "/api/cognix/models/preload-plan",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-3b-q4", "ollama-qwen-4b-local"],
        "uiPanels": ["model-selector", "settings-models"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-live-model-comparison",
        "displayName": "CogniX Live Model Comparison",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "side_by_side_model_comparison",
            "parallel_inference_planning",
            "response_collection",
            "optional_response_evaluator",
            "user_best_response_selection",
            "user_model_preferences",
            "responsive_split_view_contract",
        ],
        "routes": [
            "/api/cognix/models/comparison/blueprint",
            "/api/cognix/models/comparison/plan",
            "/api/cognix/models/comparisons",
            "/api/cognix/models/comparisons/{comparison_id}",
            "/api/cognix/models/comparisons/{comparison_id}/preference",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat-message-actions", "model-comparison-split-view"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-response-reflection"],
    },
    {
        "id": "cognix-model-translator",
        "displayName": "CogniX Universal Model Translator",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "model_conversion_planning",
            "compatibility_checking",
            "model_export_planning",
            "conversion_validation_planning",
            "registry_update_planning",
        ],
        "routes": [
            "/api/cognix/models/translator/blueprint",
            "/api/cognix/models/translator/plan",
            "/api/cognix/models/conversions",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["model-hub", "settings-models"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-worker-queue"],
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
        "id": "cognix-performance-monitor",
        "displayName": "CogniX Live Performance Monitor",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "runtime_metrics",
            "metrics_streaming",
            "performance_overlay",
            "model_performance_logs",
            "cost_visibility",
            "temperature_tracking",
        ],
        "routes": [
            "/api/cognix/performance/blueprint",
            "/api/cognix/performance/snapshot",
            "/api/cognix/performance/stream-plan",
            "/api/cognix/performance/metrics",
            "/api/cognix/performance/logs",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["performance", "developer-overlay"],
        "dependencies": ["cognix-local-core", "cognix-optimization-engine"],
    },
    {
        "id": "cognix-explain-decisions",
        "displayName": "CogniX Explain Decisions",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "decision_logs",
            "reason_codes",
            "router_decision_explanations",
            "why_this_model",
            "why_rag_or_fine_tuning",
            "human_readable_trace",
        ],
        "routes": [
            "/api/cognix/decisions/blueprint",
            "/api/cognix/decisions/explain",
            "/api/cognix/decisions",
            "/api/cognix/decisions/{decision_id}",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["chat-message-actions", "decision-panel"],
        "dependencies": ["cognix-local-core", "cognix-optimization-engine"],
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
            "compressed_context_injection",
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
        "id": "cognix-context-heatmap",
        "displayName": "CogniX Context Heatmap",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "context_usage_tracking",
            "context_heatmap",
            "utility_scoring",
            "memory_garbage_collection_planning",
            "memory_cleanup_suggestions",
            "memory_conflict_resolution",
            "review_before_delete",
            "rollback_safe_cleanup",
            "theme_aware_heatmap_tokens",
        ],
        "routes": [
            "/api/cognix/context/heatmap/blueprint",
            "/api/cognix/context/heatmap/plan",
            "/api/cognix/context/heatmap/entries",
            "/api/cognix/memory/cleanup/blueprint",
            "/api/cognix/memory/cleanup/plan",
            "/api/cognix/memory/cleanup/suggestions",
            "/api/cognix/memory/cleanup/conflicts",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["project-settings", "settings-memory"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager", "cognix-prompt-compression"],
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
        "capabilities": [
            "central_memory_layers",
            "memory_policy",
            "conversation_summarization_planning",
            "compressed_context_injection",
            "document_memory_planning",
        ],
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
        "id": "cognix-personal-ai-twin",
        "displayName": "CogniX Personal AI Twin",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "personal_ai_profile",
            "style_profiler",
            "preference_model",
            "skill_profile",
            "personalization_rules",
            "user_controlled_twin",
            "profile_export_reset",
            "safe_personalization_injection",
        ],
        "routes": [
            "/api/cognix/personal-twin/blueprint",
            "/api/cognix/personal-twin/profile/plan",
            "/api/cognix/personal-twin/profile",
            "/api/cognix/personal-twin/profile/status",
            "/api/cognix/personal-twin/export",
            "/api/cognix/personal-twin/injection-plan",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["settings-memory", "profile-settings"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager", "cognix-long-term-skill-memory"],
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
        "capabilities": [
            "project_memory",
            "project_default_model",
            "project_dna",
            "project_profile_builder",
            "project_dna_context_injection",
            "project_constraints",
            "project_decisions",
            "specialized_projects",
            "project_expert_routing",
            "generalist_verifier",
        ],
        "routes": [
            "/projects",
            "/api/cognix/project-model-defaults",
            "/api/cognix/project-experts/registry",
            "/api/cognix/projects/{project_id}/dna/blueprint",
            "/api/cognix/projects/{project_id}/dna",
            "/api/cognix/projects/{project_id}/dna/injection-plan",
            "/api/cognix/projects/{project_id}/expert-plan",
        ],
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
            "rag_retrieval_packet",
            "source_permission_gates",
            "retrieval_planning",
            "citations",
        ],
        "routes": [
            "/api/cognix/rag/sources",
            "/api/cognix/rag/indexing-plan",
            "/api/cognix/rag/plan",
            "/api/cognix/rag/retrieval-packet",
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
            "dataset_validation_plan",
            "qlora_planning",
            "cloud_training_targets",
            "cloud_training_handoff",
            "ceo_cloud_training_bypass",
            "adapter_library",
        ],
        "routes": [
            "/api/cognix/fine-tuning/plan",
            "/api/cognix/fine-tuning/dataset/validate",
            "/api/cognix/fine-tuning/cloud-handoff-plan",
        ],
        "permissions": ["developer_mode"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["dataset-manager", "lora-manager"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-dataset-builder",
        "displayName": "CogniX Dataset Builder",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "dataset_builder",
            "synthetic_example_generation",
            "dataset_quality_filter",
            "dataset_export_planning",
            "data_source_transparency",
        ],
        "routes": [
            "/api/cognix/datasets/blueprint",
            "/api/cognix/datasets/plan",
            "/api/cognix/datasets",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["dataset-manager", "project-documents"],
        "dependencies": ["cognix-local-core", "cognix-rag", "cognix-fine-tuning"],
    },
    {
        "id": "cognix-persona-builder",
        "displayName": "CogniX Persona Builder",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "persona_manager",
            "persona_template_engine",
            "persona_permission_binder",
            "memory_scope_binding",
            "project_persona_binding",
        ],
        "routes": [
            "/api/cognix/personas/blueprint",
            "/api/cognix/personas/plan",
            "/api/cognix/personas",
            "/api/cognix/personas/{persona_id}",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["project-settings", "settings-memory"],
        "dependencies": ["cognix-local-core", "cognix-memory-manager", "cognix-integrations"],
    },
    {
        "id": "cognix-gpts",
        "displayName": "CogniX GPTs",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "custom_gpt_manager",
            "custom_assistant_runtime",
            "gpt_permission_binding",
            "gpt_tool_binding",
            "gpt_memory_binding",
            "gpt_document_binding",
            "gpt_project_binding",
            "orchestrator_runtime_plan",
            "creator_permission_ceiling",
            "gpt_versioning",
        ],
        "routes": [
            "/api/cognix/gpts/blueprint",
            "/api/cognix/gpts/plan",
            "/api/cognix/gpts",
            "/api/cognix/gpts/{gpt_id}",
            "/api/cognix/gpts/{gpt_id}/runtime-plan",
        ],
        "permissions": ["authenticated", "gpts:read", "gpts:create", "gpts:share", "gpts:admin"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["gpts", "project-assistants", "chat-model-selector"],
        "dependencies": ["cognix-local-core", "cognix-library", "cognix-memory-manager", "cognix-tool-discovery"],
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
        "capabilities": [
            "technology_watch",
            "research_triage",
            "hype_filter",
            "benchmark_gate",
            "experimental_module_planning",
            "research_topics",
            "source_monitoring_plans",
            "research_item_archive",
            "research_report_generation",
            "cognix_document_reports",
        ],
        "routes": [
            "/api/cognix/research/watch-registry",
            "/api/cognix/research/integration-plan",
            "/api/cognix/research/assistant/blueprint",
            "/api/cognix/research/assistant/topics",
            "/api/cognix/research/assistant/reports/plan",
        ],
        "permissions": ["authenticated"],
        "tools": ["hugging-face", "github"],
        "defaultModels": ["cognix-research-3b-q4"],
        "uiPanels": ["research-watch", "developer-workflow"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle", "cognix-memory-manager"],
    },
    {
        "id": "cognix-ai-evolution-engine",
        "displayName": "CogniX AI Evolution Engine",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "evolution_lab",
            "research_watcher_pipeline",
            "technique_classifier",
            "prototype_planning",
            "sandbox_experiment_planning",
            "benchmark_review",
            "security_review",
            "integration_proposals",
            "human_approval_gate",
        ],
        "routes": [
            "/api/cognix/evolution/blueprint",
            "/api/cognix/evolution/items/plan",
            "/api/cognix/evolution/items",
            "/api/cognix/evolution/experiments/plan",
            "/api/cognix/evolution/proposals",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["evolution-lab", "developer-workflow"],
        "dependencies": ["cognix-local-core", "cognix-research-watch", "cognix-ai-sandbox", "cognix-optimization-engine"],
    },
    {
        "id": "cognix-integrations",
        "displayName": "CogniX Integrations",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "tool_registry",
            "integration_status",
            "permissions_audit",
            "tool_permission_matrix",
            "tool_execution_contract",
        ],
        "routes": [
            "/api/cognix/integrations/status",
            "/api/cognix/tools/registry",
            "/api/cognix/tools/permission-matrix",
            "/api/cognix/tools/plan",
        ],
        "permissions": ["authenticated"],
        "tools": ["github", "google-drive", "gmail", "notion"],
        "defaultModels": [],
        "uiPanels": ["integrations-settings"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-plugin-marketplace",
        "displayName": "CogniX Plugin Marketplace",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "plugin_catalog",
            "plugin_manifest_validation",
            "plugin_signature_validation",
            "plugin_permission_scanning",
            "plugin_install_planning",
            "plugin_activation_planning",
            "plugin_reviews",
        ],
        "routes": [
            "/api/cognix/plugins/marketplace/blueprint",
            "/api/cognix/plugins/marketplace",
            "/api/cognix/plugins/install-plan",
            "/api/cognix/plugins/installations",
        ],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["marketplace", "integrations-settings"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
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
        "id": "cognix-admin-operations",
        "displayName": "CogniX Admin Operations",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "admin_user_service",
            "user_activity_monitoring",
            "activity_daily_rollups",
            "organization_activity_daily",
            "admin_activity_dashboard",
            "user_limit_management",
            "quota_manager",
            "usage_enforcer",
            "role_quota_management",
            "group_quota_overrides",
            "quota_usage_tracking",
            "token_usage_dashboard",
            "model_usage_dashboard",
            "token_usage_service",
            "model_usage_aggregator",
            "cost_estimator",
            "usage_dashboard_service",
            "daily_user_token_rollups",
            "daily_model_usage_rollups",
            "organization_usage_summary",
            "local_cloud_usage_split",
            "model_call_usage_logging",
            "permission_engine",
            "rbac_roles",
            "role_permission_management",
            "user_permission_overrides",
            "project_permission_scopes",
            "permission_decision_planning",
            "ceo_cloud_training_permissions",
            "approval_service",
            "approval_queue",
            "approval_policy_engine",
            "approval_decision_history",
            "approval_admin_comments",
            "ban_service",
            "ban_report_generator",
            "user_risk_service",
            "ban_evidence_logs",
            "user_reactivation",
            "admin_user_view_audit",
        ],
        "routes": [
            "/api/cognix/admin/users/blueprint",
            "/api/cognix/admin/users",
            "/api/cognix/admin/users/{username}",
            "/api/cognix/admin/users/{username}/limits",
            "/api/cognix/admin/users/{username}/limits/{limit_key}",
            "/api/cognix/admin/limits",
            "/api/cognix/admin/limits/blueprint",
            "/api/cognix/admin/limits/users/{username}/{quota_key}",
            "/api/cognix/admin/limits/roles/{role_key}/{quota_key}",
            "/api/cognix/admin/limits/overrides",
            "/api/cognix/admin/limits/enforcement-plan",
            "/api/cognix/admin/permissions/blueprint",
            "/api/cognix/admin/permissions/matrix",
            "/api/cognix/admin/permissions/roles/{role_key}",
            "/api/cognix/admin/permissions/roles/{role_key}/{permission_key}",
            "/api/cognix/admin/permissions/users/{username}/{permission_key}/override",
            "/api/cognix/admin/permissions/projects/{project_id}",
            "/api/cognix/admin/permissions/decision",
            "/api/cognix/admin/permissions/{username}",
            "/api/cognix/admin/approvals",
            "/api/cognix/admin/approvals/blueprint",
            "/api/cognix/admin/approvals/policy",
            "/api/cognix/admin/approvals/{request_id}",
            "/api/cognix/admin/approvals/{request_id}/comments",
            "/api/cognix/admin/banned",
            "/api/cognix/admin/banned/blueprint",
            "/api/cognix/admin/banned/{ban_id}",
            "/api/cognix/admin/banned/{ban_id}/report",
            "/api/cognix/admin/banned/{ban_id}/evidence",
            "/api/cognix/admin/activity",
            "/api/cognix/admin/activity/blueprint",
            "/api/cognix/admin/activity/aggregate",
            "/api/cognix/admin/usage",
            "/api/cognix/admin/usage/blueprint",
            "/api/cognix/admin/usage/aggregate",
        ],
        "permissions": [
            "admin",
            "admin:users:read",
            "admin:users:update",
            "admin:limits:update",
            "admin:permissions:update",
            "admin:approvals:update",
        ],
        "tools": [],
        "defaultModels": [],
        "uiPanels": [
            "admin-dashboard",
            "admin-users",
            "admin-usage",
            "admin-limits",
            "admin-permissions",
            "admin-approvals",
            "admin-banned",
        ],
        "dependencies": ["cognix-enterprise-foundation"],
    },
    {
        "id": "cognix-admin-chat-access",
        "displayName": "CogniX Admin Chat Access",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": [
            "admin_chat_service",
            "chat_access_policy",
            "e2ee_metadata_only_mode",
            "enterprise_compliance_chat_access",
            "admin_chat_access_audit",
            "conversation_audit_metadata",
            "conversation_export_planning",
        ],
        "routes": [
            "/api/cognix/admin/chats/blueprint",
            "/api/cognix/admin/chats/policy",
            "/api/cognix/admin/chats",
            "/api/cognix/admin/chats/{thread_id}",
            "/api/cognix/admin/chats/{thread_id}/export-plan",
        ],
        "permissions": [
            "admin",
            "admin:chats:read",
            "admin:chats:policy",
            "admin:chats:export",
        ],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["admin-dashboard", "admin-chats", "compliance-center"],
        "dependencies": ["cognix-enterprise-foundation", "cognix-admin-operations"],
    },
    {
        "id": "cognix-admin-security-center",
        "displayName": "CogniX Admin Security Center",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "planned",
        "capabilities": [
            "security_threat_reports",
            "security_threat_service",
            "vulnerability_scanner_adapter",
            "codex_security_summarizer",
            "threat_report_service",
            "permission_error_detection",
            "codex_incident_detection",
            "secret_exposure_detection",
            "cloud_risk_detection",
            "ai_risk_scoring",
            "live_system_health",
            "sensitive_action_audit",
            "admin_security_dashboard",
        ],
        "routes": [
            "/api/cognix/admin/security-threats",
            "/api/cognix/admin/security-threats/blueprint",
            "/api/cognix/admin/risk-scores",
            "/api/cognix/admin/system-health",
            "/api/cognix/admin/audit-logs",
        ],
        "permissions": ["admin"],
        "tools": [],
        "defaultModels": [],
        "uiPanels": ["admin-security", "admin-dashboard"],
        "dependencies": ["cognix-enterprise-foundation"],
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
