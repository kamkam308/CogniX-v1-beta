# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX advanced native roadmap readiness contract.

This maps the "30 fonctionnalites avancees natives" roadmap to native modules,
registered API routes, and database blueprint storage records. It is diagnostic
only: it never activates modules, registers routes, migrates data, loads models,
starts jobs, or mutates the UI.
"""

from __future__ import annotations

from typing import Any, Iterable

from core.cognix import module_registry


COGNIX_ADVANCED_ROADMAP_READINESS_VERSION = "cognix_advanced_roadmap_readiness_v1"

ADVANCED_FEATURES: list[dict[str, Any]] = [
    {
        "id": "ai_self_reflection",
        "number": 1,
        "title": "AI Self Reflection",
        "moduleId": "cognix-response-reflection",
        "requiredCapabilities": ["response_quality_evaluation", "reflection_logs"],
    },
    {
        "id": "multi_draft_generation",
        "number": 2,
        "title": "Multi-Draft Generation",
        "moduleId": "cognix-multi-draft-generation",
        "requiredCapabilities": ["multi_draft_planning", "response_variant_store"],
    },
    {
        "id": "ai_debate_mode",
        "number": 3,
        "title": "AI Debate Mode",
        "moduleId": "cognix-ai-debate",
        "requiredCapabilities": ["bounded_debate_planning", "judge_synthesis_planning"],
    },
    {
        "id": "automatic_tool_discovery",
        "number": 4,
        "title": "Automatic Tool Discovery",
        "moduleId": "cognix-tool-discovery",
        "requiredCapabilities": ["project_tool_need_detection", "tool_capability_registry"],
    },
    {
        "id": "live_context_graph",
        "number": 5,
        "title": "Live Context Graph",
        "moduleId": "cognix-context-graph",
        "requiredCapabilities": ["context_graph_snapshot", "graph_store"],
    },
    {
        "id": "long_term_skill_memory",
        "number": 6,
        "title": "Long Term Skill Memory",
        "moduleId": "cognix-long-term-skill-memory",
        "requiredCapabilities": ["skill_memory_candidates", "memory_approval_flow"],
    },
    {
        "id": "ai_workflow_recorder",
        "number": 7,
        "title": "AI Workflow Recorder",
        "moduleId": "cognix-ai-workflow-recorder",
        "requiredCapabilities": ["workflow_recording", "workflow_replay_planning"],
    },
    {
        "id": "prompt_compression",
        "number": 8,
        "title": "Prompt Compression",
        "moduleId": "cognix-prompt-compression",
        "requiredCapabilities": ["prompt_compression", "compressed_context_store"],
    },
    {
        "id": "intent_prediction",
        "number": 9,
        "title": "Intent Prediction",
        "moduleId": "cognix-intent-prediction",
        "requiredCapabilities": ["intent_prediction", "preload_planning"],
    },
    {
        "id": "dynamic_ui",
        "number": 10,
        "title": "Dynamic UI",
        "moduleId": "cognix-dynamic-ui",
        "requiredCapabilities": ["ui_layout_profiles", "adaptive_panels"],
    },
    {
        "id": "autonomous_background_agents",
        "number": 11,
        "title": "Autonomous Background Agents",
        "moduleId": "cognix-background-agents",
        "requiredCapabilities": ["background_job_planning", "agent_queue_contract"],
    },
    {
        "id": "ai_timeline",
        "number": 12,
        "title": "AI Timeline",
        "moduleId": "cognix-ai-timeline",
        "requiredCapabilities": ["project_timeline_events", "timeline_search"],
    },
    {
        "id": "live_memory_editing",
        "number": 13,
        "title": "Live Memory Editing",
        "moduleId": "cognix-live-memory-editing",
        "requiredCapabilities": ["live_memory_editor", "memory_versioning"],
    },
    {
        "id": "ai_simulation",
        "number": 14,
        "title": "AI Simulation",
        "moduleId": "cognix-ai-simulation",
        "requiredCapabilities": ["simulation_engine", "risk_report"],
    },
    {
        "id": "ai_sandbox",
        "number": 15,
        "title": "AI Sandbox",
        "moduleId": "cognix-ai-sandbox",
        "requiredCapabilities": ["sandbox_manager", "isolated_runtime"],
    },
    {
        "id": "adaptive_quantization",
        "number": 16,
        "title": "Adaptive Quantization",
        "moduleId": "cognix-optimization-engine",
        "requiredCapabilities": ["adaptive_quantization", "quantization_advisor"],
    },
    {
        "id": "ai_cost_optimizer",
        "number": 17,
        "title": "AI Cost Optimizer",
        "moduleId": "cognix-optimization-engine",
        "requiredCapabilities": ["cost_optimizer", "execution_cost_planning"],
    },
    {
        "id": "context_heatmap",
        "number": 18,
        "title": "Context Heatmap",
        "moduleId": "cognix-context-heatmap",
        "requiredCapabilities": ["context_heatmap", "utility_scoring"],
    },
    {
        "id": "automatic_dataset_builder",
        "number": 19,
        "title": "Automatic Dataset Builder",
        "moduleId": "cognix-dataset-builder",
        "requiredCapabilities": ["dataset_builder", "dataset_quality_filter"],
    },
    {
        "id": "ai_persona_builder",
        "number": 20,
        "title": "AI Persona Builder",
        "moduleId": "cognix-persona-builder",
        "requiredCapabilities": ["persona_manager", "persona_template_engine"],
    },
    {
        "id": "universal_model_translator",
        "number": 21,
        "title": "Universal Model Translator",
        "moduleId": "cognix-model-translator",
        "requiredCapabilities": ["model_conversion_planning", "compatibility_checking"],
    },
    {
        "id": "ai_plugin_marketplace",
        "number": 22,
        "title": "AI Plugin Marketplace",
        "moduleId": "cognix-plugin-marketplace",
        "requiredCapabilities": ["plugin_catalog", "plugin_install_planning"],
    },
    {
        "id": "project_dna",
        "number": 23,
        "title": "Project DNA",
        "moduleId": "cognix-projects",
        "requiredCapabilities": ["project_dna", "project_dna_context_injection"],
    },
    {
        "id": "live_performance_monitor",
        "number": 24,
        "title": "Live Performance Monitor",
        "moduleId": "cognix-performance-monitor",
        "requiredCapabilities": ["runtime_metrics", "metrics_streaming"],
    },
    {
        "id": "ai_explain_decisions",
        "number": 25,
        "title": "AI Explain Decisions",
        "moduleId": "cognix-explain-decisions",
        "requiredCapabilities": ["decision_logs", "why_this_model"],
    },
    {
        "id": "automatic_research_assistant",
        "number": 26,
        "title": "Automatic Research Assistant",
        "moduleId": "cognix-research-watch",
        "requiredCapabilities": ["technology_watch", "research_triage"],
    },
    {
        "id": "ai_memory_garbage_collector",
        "number": 27,
        "title": "AI Memory Garbage Collector",
        "moduleId": "cognix-context-heatmap",
        "requiredCapabilities": ["memory_garbage_collection_planning", "rollback_safe_cleanup"],
    },
    {
        "id": "personal_ai_twin",
        "number": 28,
        "title": "Personal AI Twin",
        "moduleId": "cognix-personal-ai-twin",
        "requiredCapabilities": ["personal_ai_profile", "safe_personalization_injection"],
    },
    {
        "id": "live_model_comparison",
        "number": 29,
        "title": "Live Model Comparison",
        "moduleId": "cognix-live-model-comparison",
        "requiredCapabilities": ["side_by_side_model_comparison", "user_best_response_selection"],
    },
    {
        "id": "ai_evolution_engine",
        "number": 30,
        "title": "AI Evolution Engine",
        "moduleId": "cognix-ai-evolution-engine",
        "requiredCapabilities": ["evolution_lab", "integration_proposals"],
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _module_records(modules: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if modules is not None:
        return [item for item in modules if isinstance(item, dict)]
    return module_registry.build_module_registry()["modules"]


def _module_index(modules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in modules
        if isinstance(item, dict) and item.get("id")
    }


def _module_storage_index(database_blueprint: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    blueprint = _as_dict(database_blueprint)
    return {
        str(item.get("moduleId")): item
        for item in _as_list(blueprint.get("moduleStorageTables"))
        if isinstance(item, dict) and item.get("moduleId")
    }


def _registered_route_paths(registered_routes: Iterable[Any] | None) -> set[str] | None:
    if registered_routes is None:
        return None
    paths: set[str] = set()
    for route in registered_routes:
        if isinstance(route, dict):
            path = route.get("path")
        else:
            path = getattr(route, "path", None)
        if isinstance(path, str) and path.strip():
            paths.add(path.strip())
    return paths


def _route_record(module: dict[str, Any], registered_paths: set[str] | None) -> dict[str, Any]:
    declared = [str(route) for route in _as_list(module.get("routes")) if str(route).strip()]
    if registered_paths is None:
        return {
            "status": "declared" if declared else "missing",
            "coverageChecked": False,
            "declaredRouteCount": len(declared),
            "matchedRouteCount": 0,
            "declaredRoutes": declared,
            "matchedRoutes": [],
            "missingDeclaredRoutes": [],
        }
    matched = [route for route in declared if route in registered_paths]
    missing = [route for route in declared if route not in registered_paths]
    if matched:
        status = "ready" if not missing else "partial"
    elif declared:
        status = "declared_unregistered"
    else:
        status = "missing"
    return {
        "status": status,
        "coverageChecked": True,
        "declaredRouteCount": len(declared),
        "matchedRouteCount": len(matched),
        "declaredRoutes": declared,
        "matchedRoutes": matched,
        "missingDeclaredRoutes": missing,
    }


def _capability_record(module: dict[str, Any], required: list[str]) -> dict[str, Any]:
    capabilities = {str(item) for item in _as_list(module.get("capabilities")) if str(item).strip()}
    present = [item for item in required if item in capabilities]
    missing = [item for item in required if item not in capabilities]
    return {
        "status": "ready" if not missing else "partial" if present else "missing",
        "requiredCapabilities": required,
        "presentCapabilities": present,
        "missingCapabilities": missing,
    }


def _storage_record(module_id: str, storage_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    record = _as_dict(storage_index.get(module_id))
    status = str(record.get("status") or "missing")
    return {
        "status": status,
        "declaredTableCount": int(record.get("declaredTableCount") or 0),
        "presentTableCount": int(record.get("presentTableCount") or 0),
        "plannedTableCount": int(record.get("plannedTableCount") or 0),
        "storageTables": _as_list(record.get("storageTables")),
        "presentStorageTables": _as_list(record.get("presentStorageTables")),
        "plannedStorageTables": _as_list(record.get("plannedStorageTables")),
    }


def _feature_status(
    *,
    module: dict[str, Any] | None,
    routes: dict[str, Any],
    capabilities: dict[str, Any],
    storage: dict[str, Any],
) -> str:
    if not module:
        return "missing"
    module_status = str(module.get("status") or "")
    activation_state = str(module.get("activationState") or "")
    if module_status != "enabled" or activation_state != "ready":
        return "planned"
    if capabilities.get("status") == "missing":
        return "missing"
    if routes.get("status") in {"missing", "declared_unregistered"}:
        return "partial"
    if storage.get("status") == "available" and capabilities.get("status") == "ready":
        return "ready"
    if storage.get("status") in {"partial", "planned", "missing_declaration", "missing"}:
        return "partial"
    return "partial"


def _feature_record(
    definition: dict[str, Any],
    *,
    modules: dict[str, dict[str, Any]],
    storage_index: dict[str, dict[str, Any]],
    registered_paths: set[str] | None,
) -> dict[str, Any]:
    module_id = str(definition["moduleId"])
    module = modules.get(module_id)
    module_dict = _as_dict(module)
    routes = _route_record(module_dict, registered_paths) if module else {
        "status": "missing",
        "coverageChecked": registered_paths is not None,
        "declaredRouteCount": 0,
        "matchedRouteCount": 0,
        "declaredRoutes": [],
        "matchedRoutes": [],
        "missingDeclaredRoutes": [],
    }
    capabilities = _capability_record(module_dict, list(definition["requiredCapabilities"])) if module else {
        "status": "missing",
        "requiredCapabilities": list(definition["requiredCapabilities"]),
        "presentCapabilities": [],
        "missingCapabilities": list(definition["requiredCapabilities"]),
    }
    storage = _storage_record(module_id, storage_index)
    status = _feature_status(
        module = module,
        routes = routes,
        capabilities = capabilities,
        storage = storage,
    )
    return {
        "id": definition["id"],
        "number": definition["number"],
        "title": definition["title"],
        "status": status,
        "moduleId": module_id,
        "moduleDisplayName": module_dict.get("displayName") or module_dict.get("name") or module_id,
        "moduleStatus": module_dict.get("status") if module else "missing",
        "activationState": module_dict.get("activationState") if module else "missing",
        "readyForNativeIteration": status in {"ready", "partial"},
        "capabilityCoverage": capabilities,
        "routeCoverage": routes,
        "storageCoverage": storage,
    }


def build_advanced_roadmap_readiness_contract(
    *,
    modules: Iterable[dict[str, Any]] | None = None,
    registered_routes: Iterable[Any] | None = None,
    database_blueprint: dict[str, Any] | None = None,
    service_topology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_records = _module_records(modules)
    module_by_id = _module_index(module_records)
    storage_index = _module_storage_index(database_blueprint)
    registered_paths = _registered_route_paths(registered_routes)
    features = [
        _feature_record(
            feature,
            modules = module_by_id,
            storage_index = storage_index,
            registered_paths = registered_paths,
        )
        for feature in ADVANCED_FEATURES
    ]
    ready = [item for item in features if item["status"] == "ready"]
    partial = [item for item in features if item["status"] == "partial"]
    planned = [item for item in features if item["status"] == "planned"]
    missing = [item for item in features if item["status"] == "missing"]
    storage_blocked = [
        item["id"]
        for item in features
        if item["storageCoverage"]["status"] in {"planned", "partial", "missing", "missing_declaration"}
    ]
    route_blocked = [
        item["id"]
        for item in features
        if item["routeCoverage"]["status"] in {"missing", "declared_unregistered"}
    ]
    return {
        "advancedRoadmapReadinessVersion": COGNIX_ADVANCED_ROADMAP_READINESS_VERSION,
        "mode": "advanced_roadmap_readiness_read_only",
        "sourceOfTruth": "cognix_30_advanced_native_features",
        "summary": {
            "featureCount": len(features),
            "readyFeatureCount": len(ready),
            "partialFeatureCount": len(partial),
            "plannedFeatureCount": len(planned),
            "missingFeatureCount": len(missing),
            "nativeModuleCoverageReady": not missing,
            "allStorageReady": not storage_blocked,
            "routeCoverageChecked": registered_paths is not None,
            "routeCoverageBlockedFeatureIds": route_blocked,
            "storageBlockedFeatureIds": storage_blocked,
            "readyForAdvancedIteration": not missing,
        },
        "inputContracts": {
            "moduleRegistryVersion": module_registry.COGNIX_MODULE_REGISTRY_VERSION,
            "databaseBlueprintVersion": _as_dict(database_blueprint).get("databaseBlueprintVersion"),
            "serviceTopologyVersion": _as_dict(service_topology).get("serviceTopologyVersion"),
        },
        "features": features,
        "policies": {
            "roadmapAdvancedFeatureSetRequired": True,
            "frontendMutationAllowedHere": False,
            "moduleActivationAllowedHere": False,
            "routeRegistrationAllowedHere": False,
            "databaseMigrationAllowedHere": False,
            "jobEnqueueAllowedHere": False,
            "modelLoadAllowedHere": False,
            "toolExecutionAllowedHere": False,
            "codeModificationAllowedHere": False,
        },
        "sideEffects": {
            "moduleActivation": False,
            "routeRegistration": False,
            "apiMutation": False,
            "databaseWrite": False,
            "migrationRun": False,
            "jobEnqueue": False,
            "workerStart": False,
            "modelLoad": False,
            "toolExecution": False,
            "networkCall": False,
            "uiMutation": False,
            "codeModification": False,
            "auditWrite": False,
        },
    }
