# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX MVP readiness contract.

This maps roadmap Section 31 phases to native modules, API coverage, database
blueprint records, and internal services. It is diagnostic only: it does not
activate modules, register routes, migrate data, enqueue jobs, or start models.
"""

from __future__ import annotations

from typing import Any, Iterable

from core.cognix import module_registry


COGNIX_MVP_READINESS_VERSION = "cognix_mvp_readiness_v1"

MVP_PHASES: list[dict[str, Any]] = [
    {
        "id": "phase_1_core_local",
        "phase": 1,
        "title": "Core local solide",
        "requirements": [
            ("capability", "chat_local"),
            ("capability", "model_registry"),
            ("capability", "hugging_face_install_contract"),
            ("capability", "hardware_profiler"),
            ("capability", "model_recommender"),
            ("capability", "install_planning"),
            ("capability", "external_moe_model_router"),
            ("apiPurpose", "non_streaming_chat"),
            ("apiPurpose", "streaming_chat"),
            ("apiPurpose", "model_install_planning"),
            ("apiPurpose", "model_load"),
            ("apiPurpose", "model_unload"),
            ("apiPurpose", "installed_model_inventory"),
            ("apiPurpose", "hardware_profile"),
            ("logicalTable", "users"),
            ("logicalTable", "projects"),
            ("logicalTable", "chats"),
            ("logicalTable", "messages"),
            ("logicalTable", "models"),
            ("logicalTable", "installed_models"),
            ("service", "backend-api"),
            ("service", "model-runtime-adapter"),
            ("service", "orchestrator-service"),
            ("service", "frontend"),
        ],
    },
    {
        "id": "phase_2_specialized_projects",
        "phase": 2,
        "title": "Projets specialises",
        "requirements": [
            ("capability", "project_memory"),
            ("capability", "project_default_model"),
            ("capability", "project_dna"),
            ("capability", "project_profile_builder"),
            ("capability", "central_memory_layers"),
            ("logicalTable", "projects"),
            ("logicalTable", "memories"),
            ("service", "backend-api"),
            ("service", "memory-service"),
            ("service", "orchestrator-service"),
        ],
    },
    {
        "id": "phase_3_orchestrator",
        "phase": 3,
        "title": "Orchestrateur",
        "requirements": [
            ("capability", "external_moe_model_router"),
            ("capability", "architecture_decision_contract"),
            ("capability", "orchestrator_runtime_plan"),
            ("capability", "runtime_fallback_chain"),
            ("capability", "decision_logs"),
            ("apiPurpose", "domain_classification"),
            ("logicalTable", "router_logs"),
            ("service", "orchestrator-service"),
            ("service", "backend-api"),
        ],
    },
    {
        "id": "phase_4_model_cache_manager",
        "phase": 4,
        "title": "Model Cache Manager",
        "requirements": [
            ("capability", "cache_load_planning"),
            ("capability", "preload_execution_contract"),
            ("capability", "cache_policy"),
            ("capability", "intelligent_preload_queue_contract"),
            ("capability", "worker_queue_registry"),
            ("service", "model-runtime-adapter"),
            ("service", "worker-queue"),
        ],
    },
    {
        "id": "phase_5_rag",
        "phase": 5,
        "title": "RAG",
        "requirements": [
            ("capability", "document_memory"),
            ("capability", "rag_source_registry"),
            ("capability", "rag_indexing_planning"),
            ("capability", "rag_retrieval_packet"),
            ("apiPurpose", "rag_indexing"),
            ("logicalTable", "documents"),
            ("logicalTable", "document_chunks"),
            ("service", "rag-service"),
            ("service", "memory-service"),
        ],
    },
    {
        "id": "phase_6_guided_fine_tuning",
        "phase": 6,
        "title": "Fine-tuning guide",
        "requirements": [
            ("capability", "dataset_validation"),
            ("capability", "dataset_validation_plan"),
            ("capability", "qlora_planning"),
            ("capability", "cloud_training_targets"),
            ("capability", "cloud_training_handoff"),
            ("capability", "worker_enqueue_contract"),
            ("apiPurpose", "fine_tuning_start"),
            ("apiPurpose", "fine_tuning_jobs"),
            ("logicalTable", "fine_tuning_jobs"),
            ("logicalTable", "datasets"),
            ("logicalTable", "lora_adapters"),
            ("service", "fine-tuning-service"),
            ("service", "worker-queue"),
        ],
    },
    {
        "id": "phase_7_connectors",
        "phase": 7,
        "title": "Connecteurs",
        "requirements": [
            ("capability", "tool_registry"),
            ("capability", "integration_status"),
            ("capability", "permissions_audit"),
            ("capability", "tool_permission_matrix"),
            ("capability", "app_manifest_registry"),
            ("capability", "oauth_connection_planning"),
            ("apiPurpose", "guarded_tool_execution"),
            ("logicalTable", "tool_integrations"),
            ("logicalTable", "tool_permissions"),
            ("service", "tool-service"),
        ],
    },
    {
        "id": "phase_8_enterprise",
        "phase": 8,
        "title": "Enterprise",
        "requirements": [
            ("capability", "organizations"),
            ("capability", "rbac"),
            ("capability", "sso_planning"),
            ("capability", "gpu_scheduler_contract"),
            ("capability", "deployment_targets"),
            ("capability", "admin_user_service"),
            ("capability", "audit_governance_contract"),
            ("apiPurpose", "admin_audit_log_read"),
            ("logicalTable", "organizations"),
            ("logicalTable", "audit_logs"),
            ("logicalTable", "deployment_targets"),
            ("service", "backend-api"),
            ("service", "worker-queue"),
        ],
    },
    {
        "id": "phase_9_native_codex_secure",
        "phase": 9,
        "title": "Codex natif securise",
        "requirements": [
            ("capability", "feature_request"),
            ("capability", "branch_pipeline"),
            ("capability", "tests_build_preview"),
            ("capability", "codex_run_contract"),
            ("capability", "codex_preview_contract"),
            ("capability", "codex_human_approval_gate"),
            ("capability", "codex_merge_gate_contract"),
            ("apiPurpose", "codex_feature_pipeline"),
            ("logicalTable", "audit_logs"),
            ("service", "codex-agent-service"),
            ("service", "worker-queue"),
            ("service", "tool-service"),
        ],
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


def _capability_index(modules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for module in modules:
        module_id = str(module.get("id") or "")
        status = str(module.get("status") or "planned")
        for capability in _as_list(module.get("capabilities")):
            key = str(capability or "").strip()
            if not key:
                continue
            index.setdefault(key, []).append({"moduleId": module_id, "moduleStatus": status})
    return index


def _api_index(api_surface_contract: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    contract = _as_dict(api_surface_contract)
    return {
        str(item.get("purpose")): item
        for item in _as_list(contract.get("endpoints"))
        if isinstance(item, dict) and item.get("purpose")
    }


def _table_index(database_blueprint: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    blueprint = _as_dict(database_blueprint)
    return {
        str(item.get("logicalName")): item
        for item in _as_list(blueprint.get("logicalTables"))
        if isinstance(item, dict) and item.get("logicalName")
    }


def _service_index(service_topology: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    topology = _as_dict(service_topology)
    return {
        str(item.get("id")): item
        for item in _as_list(topology.get("services"))
        if isinstance(item, dict) and item.get("id")
    }


def _capability_requirement(key: str, capabilities: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    modules = capabilities.get(key, [])
    enabled = [item for item in modules if item.get("moduleStatus") == "enabled"]
    if enabled:
        status = "ready"
    elif modules:
        status = "planned"
    else:
        status = "missing"
    return {
        "kind": "capability",
        "id": key,
        "status": status,
        "declared": bool(modules),
        "moduleIds": [str(item.get("moduleId")) for item in modules],
        "enabledModuleIds": [str(item.get("moduleId")) for item in enabled],
    }


def _api_requirement(key: str, endpoints: dict[str, dict[str, Any]]) -> dict[str, Any]:
    endpoint = endpoints.get(key)
    endpoint_status = str(_as_dict(endpoint).get("status") or "")
    if endpoint_status in {"exact", "equivalent"}:
        status = "ready"
    elif endpoint_status == "planned":
        status = "planned"
    else:
        status = "missing"
    return {
        "kind": "apiPurpose",
        "id": key,
        "status": status,
        "endpointStatus": endpoint_status or "missing",
        "path": _as_dict(endpoint).get("path"),
        "matchedRoute": _as_dict(endpoint).get("matchedRoute"),
    }


def _table_requirement(key: str, tables: dict[str, dict[str, Any]]) -> dict[str, Any]:
    table = tables.get(key)
    table_status = str(_as_dict(table).get("status") or "")
    if table_status == "available":
        status = "ready"
    elif table_status == "partial":
        status = "partial"
    elif table_status == "planned":
        status = "planned"
    else:
        status = "missing"
    return {
        "kind": "logicalTable",
        "id": key,
        "status": status,
        "tableStatus": table_status or "missing",
        "presentCanonicalTables": _as_dict(table).get("presentCanonicalTables", []),
        "presentSupportingTables": _as_dict(table).get("presentSupportingTables", []),
    }


def _service_requirement(key: str, services: dict[str, dict[str, Any]]) -> dict[str, Any]:
    service = services.get(key)
    covered = bool(_as_dict(service).get("covered"))
    return {
        "kind": "service",
        "id": key,
        "status": "ready" if covered else "planned" if service else "missing",
        "covered": covered,
        "moduleIds": _as_dict(service).get("moduleIds", []),
    }


def _requirement_record(
    kind: str,
    key: str,
    *,
    capabilities: dict[str, list[dict[str, Any]]],
    endpoints: dict[str, dict[str, Any]],
    tables: dict[str, dict[str, Any]],
    services: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if kind == "capability":
        return _capability_requirement(key, capabilities)
    if kind == "apiPurpose":
        return _api_requirement(key, endpoints)
    if kind == "logicalTable":
        return _table_requirement(key, tables)
    if kind == "service":
        return _service_requirement(key, services)
    return {"kind": kind, "id": key, "status": "missing"}


def _phase_status(requirements: list[dict[str, Any]]) -> str:
    statuses = [str(item.get("status")) for item in requirements]
    if any(status == "missing" for status in statuses):
        return "blocked"
    if all(status == "ready" for status in statuses):
        return "ready"
    if any(status in {"ready", "partial"} for status in statuses):
        return "partial"
    return "planned"


def _phase_record(
    definition: dict[str, Any],
    *,
    capabilities: dict[str, list[dict[str, Any]]],
    endpoints: dict[str, dict[str, Any]],
    tables: dict[str, dict[str, Any]],
    services: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    requirements = [
        _requirement_record(
            str(kind),
            str(key),
            capabilities = capabilities,
            endpoints = endpoints,
            tables = tables,
            services = services,
        )
        for kind, key in definition.get("requirements", [])
    ]
    missing = [item["id"] for item in requirements if item.get("status") == "missing"]
    not_ready = [
        item["id"]
        for item in requirements
        if item.get("status") in {"partial", "planned", "missing"}
    ]
    status = _phase_status(requirements)
    return {
        "id": definition["id"],
        "phase": definition["phase"],
        "title": definition["title"],
        "status": status,
        "readyForImplementationFocus": status in {"ready", "partial"},
        "requirementCount": len(requirements),
        "readyRequirementCount": sum(1 for item in requirements if item.get("status") == "ready"),
        "partialRequirementCount": sum(1 for item in requirements if item.get("status") == "partial"),
        "plannedRequirementCount": sum(1 for item in requirements if item.get("status") == "planned"),
        "missingRequirementCount": len(missing),
        "missingRequirements": missing,
        "nextRequirements": not_ready[:8],
        "requirements": requirements,
    }


def build_mvp_readiness_contract(
    *,
    modules: Iterable[dict[str, Any]] | None = None,
    api_surface_contract: dict[str, Any] | None = None,
    database_blueprint: dict[str, Any] | None = None,
    service_topology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_records = _module_records(modules)
    capabilities = _capability_index(module_records)
    endpoints = _api_index(api_surface_contract)
    tables = _table_index(database_blueprint)
    services = _service_index(service_topology)
    phases = [
        _phase_record(
            phase,
            capabilities = capabilities,
            endpoints = endpoints,
            tables = tables,
            services = services,
        )
        for phase in MVP_PHASES
    ]
    blocked = [item for item in phases if item["status"] == "blocked"]
    ready = [item for item in phases if item["status"] == "ready"]
    partial = [item for item in phases if item["status"] == "partial"]
    planned = [item for item in phases if item["status"] == "planned"]
    core_phase_ids = {"phase_1_core_local", "phase_2_specialized_projects", "phase_3_orchestrator"}
    core_blocked = [item["id"] for item in blocked if item["id"] in core_phase_ids]
    return {
        "mvpReadinessVersion": COGNIX_MVP_READINESS_VERSION,
        "mode": "mvp_readiness_read_only",
        "sourceOfTruth": "roadmap_section_31",
        "summary": {
            "phaseCount": len(phases),
            "readyPhaseCount": len(ready),
            "partialPhaseCount": len(partial),
            "plannedPhaseCount": len(planned),
            "blockedPhaseCount": len(blocked),
            "coreMvpBlocked": bool(core_blocked),
            "coreMvpBlockedPhaseIds": core_blocked,
            "readyForMvpIteration": not core_blocked,
        },
        "inputContracts": {
            "moduleRegistryVersion": module_registry.COGNIX_MODULE_REGISTRY_VERSION,
            "apiSurfaceContractVersion": _as_dict(api_surface_contract).get("apiSurfaceContractVersion"),
            "databaseBlueprintVersion": _as_dict(database_blueprint).get("databaseBlueprintVersion"),
            "serviceTopologyVersion": _as_dict(service_topology).get("serviceTopologyVersion"),
        },
        "phases": phases,
        "policies": {
            "roadmapSection31Required": True,
            "frontendFeatureToggleMutationAllowed": False,
            "moduleActivationAllowedHere": False,
            "routeRegistrationAllowedHere": False,
            "databaseMigrationAllowedHere": False,
            "jobEnqueueAllowedHere": False,
            "modelLoadAllowedHere": False,
            "codeModificationAllowedHere": False,
        },
        "sideEffects": {
            "moduleActivation": False,
            "routeRegistration": False,
            "databaseWrite": False,
            "migrationRun": False,
            "jobEnqueue": False,
            "workerStart": False,
            "modelLoad": False,
            "toolExecution": False,
            "codeModification": False,
            "auditWrite": False,
        },
    }
