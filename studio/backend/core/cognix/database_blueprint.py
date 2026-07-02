# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX roadmap database blueprint.

The blueprint maps the Section 27 target tables to the current SQLite files.
It is intentionally read-only: it inspects schema metadata and never creates,
migrates, drops, or backfills tables.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.cognix import module_registry as cognix_module_registry
from utils.paths import auth_db_path, rag_db_path, studio_db_path


COGNIX_DATABASE_BLUEPRINT_VERSION = "cognix_database_blueprint_v1"
GLOBAL_ROADMAP_TABLE_SOURCE = "v2_sections_42_global_tables"
GLOBAL_ROADMAP_TABLE_NAMES: tuple[str, ...] = (
    "pulse_events",
    "pulse_summaries",
    "pulse_user_preferences",
    "pulse_notifications",
    "library_assets",
    "library_collections",
    "library_permissions",
    "library_asset_versions",
    "library_asset_links",
    "rag_sources",
    "rag_retrieval_packets",
    "codex_tasks",
    "codex_reports",
    "codex_security_reviews",
    "codex_branches",
    "codex_changes",
    "codex_test_runs",
    "scheduled_tasks",
    "scheduled_task_runs",
    "image_assets",
    "image_generations",
    "apps",
    "installed_apps",
    "app_permissions",
    "plugins",
    "plugin_installations",
    "plugin_permissions",
    "plugin_reviews",
    "gpts",
    "gpt_versions",
    "gpt_tools",
    "gpt_permissions",
    "worker_jobs",
    "worker_job_events",
    "worker_dead_letters",
    "tool_execution_logs",
    "admin_chat_access_logs",
    "approval_requests",
    "approval_decisions",
    "banned_users",
    "ban_reports",
    "security_threats",
    "security_reports",
    "token_usage_events",
    "daily_user_token_usage",
    "daily_model_usage",
    "organization_usage_summary",
    "enterprise_chats",
    "enterprise_chat_members",
    "encrypted_messages",
    "chat_key_metadata",
    "chat_policies",
    "project_members",
    "project_roles",
    "project_activity_events",
    "presence_sessions",
    "project_comments",
    "collaboration_events",
    "agent_sessions",
    "agent_steps",
    "agent_tool_calls",
    "agent_outputs",
    "favorite_models",
    "user_model_defaults",
    "project_model_defaults",
    "cowork_sessions",
    "cowork_actions",
    "cowork_permissions",
    "cowork_approvals",
    "skills",
    "skill_versions",
    "project_skills",
    "model_skills",
    "directives",
    "project_directives",
    "model_directives",
    "organization_policies",
    "risk_scores",
    "audit_logs",
    "sensitive_action_logs",
    "notifications",
    "notification_preferences",
    "admin_alerts",
    "deployment_plans",
    "gpu_scheduler_contracts",
    "education_spaces",
    "education_classes",
    "education_members",
    "education_courses",
    "education_assignments",
    "education_exam_policies",
)

ROADMAP_TABLES: list[dict[str, Any]] = [
    {
        "logicalName": "users",
        "domain": "identity",
        "ownerService": "Backend API",
        "canonicalTables": ["auth_user"],
        "supportingTables": ["refresh_tokens", "api_keys"],
        "dataClass": "identity_sensitive",
    },
    {
        "logicalName": "workspaces",
        "domain": "identity",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_workspaces"],
        "supportingTables": [],
        "dataClass": "tenant_metadata",
    },
    {
        "logicalName": "organizations",
        "domain": "governance",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_organizations"],
        "supportingTables": ["cognix_organization_activity_daily", "cognix_organization_usage_summary"],
        "dataClass": "tenant_metadata",
    },
    {
        "logicalName": "plans",
        "domain": "billing",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_plans"],
        "supportingTables": ["cognix_user_limits", "cognix_user_quotas", "cognix_role_quotas"],
        "dataClass": "billing_metadata",
    },
    {
        "logicalName": "modules",
        "domain": "module_system",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_modules"],
        "supportingTables": ["cognix_plugins", "cognix_installed_plugins"],
        "dataClass": "configuration",
    },
    {
        "logicalName": "projects",
        "domain": "projects",
        "ownerService": "Backend API",
        "canonicalTables": ["chat_projects"],
        "supportingTables": ["cognix_project_dna", "cognix_project_collaborators"],
        "dataClass": "user_content_metadata",
    },
    {
        "logicalName": "chats",
        "domain": "chat",
        "ownerService": "Backend API",
        "canonicalTables": ["chat_threads"],
        "supportingTables": ["cognix_conversation_audit_metadata"],
        "dataClass": "conversation_metadata",
    },
    {
        "logicalName": "messages",
        "domain": "chat",
        "ownerService": "Backend API",
        "canonicalTables": ["chat_messages"],
        "supportingTables": [],
        "dataClass": "user_content",
    },
    {
        "logicalName": "memories",
        "domain": "memory",
        "ownerService": "Memory Service",
        "canonicalTables": ["cognix_memories"],
        "supportingTables": ["cognix_context_memory", "cognix_memory_versions", "cognix_user_preferences"],
        "dataClass": "personalization_sensitive",
    },
    {
        "logicalName": "documents",
        "domain": "rag",
        "ownerService": "RAG Service",
        "canonicalTables": ["documents"],
        "supportingTables": ["cognix_library_items"],
        "dataClass": "user_content",
    },
    {
        "logicalName": "document_chunks",
        "domain": "rag",
        "ownerService": "RAG Service",
        "canonicalTables": ["chunks", "document_chunks"],
        "supportingTables": ["embedding_metadata"],
        "dataClass": "derived_user_content",
    },
    {
        "logicalName": "models",
        "domain": "models",
        "ownerService": "Model Runtime Adapter",
        "canonicalTables": ["cognix_models"],
        "supportingTables": ["cognix_model_variants", "cognix_provider_profiles"],
        "dataClass": "configuration",
    },
    {
        "logicalName": "installed_models",
        "domain": "models",
        "ownerService": "Model Runtime Adapter",
        "canonicalTables": ["cognix_installed_models"],
        "supportingTables": [
            "cognix_model_pins",
            "cognix_project_model_defaults",
            "favorite_models",
            "user_model_defaults",
            "project_model_defaults",
        ],
        "dataClass": "configuration",
    },
    {
        "logicalName": "model_packs",
        "domain": "models",
        "ownerService": "Model Runtime Adapter",
        "canonicalTables": ["cognix_model_packs"],
        "supportingTables": ["cognix_library_items"],
        "dataClass": "configuration",
    },
    {
        "logicalName": "model_usage_logs",
        "domain": "observability",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_model_performance_logs", "cognix_token_usage_events"],
        "supportingTables": ["cognix_daily_model_usage", "cognix_runtime_metrics"],
        "dataClass": "usage_metrics",
    },
    {
        "logicalName": "hardware_profiles",
        "domain": "hardware",
        "ownerService": "Orchestrator Service",
        "canonicalTables": ["cognix_hardware_profiles"],
        "supportingTables": ["cognix_benchmark_runs", "cognix_runtime_metrics"],
        "dataClass": "device_fingerprint",
    },
    {
        "logicalName": "router_logs",
        "domain": "orchestration",
        "ownerService": "Orchestrator Service",
        "canonicalTables": ["cognix_router_logs"],
        "supportingTables": ["cognix_orchestrator_logs", "cognix_system_decisions"],
        "dataClass": "decision_logs",
    },
    {
        "logicalName": "tool_integrations",
        "domain": "tools",
        "ownerService": "Tool Service",
        "canonicalTables": ["cognix_tool_integrations"],
        "supportingTables": ["cognix_installed_tools", "cognix_app_connections"],
        "dataClass": "integration_metadata",
    },
    {
        "logicalName": "tool_permissions",
        "domain": "tools",
        "ownerService": "Tool Service",
        "canonicalTables": ["cognix_tool_permissions"],
        "supportingTables": ["cognix_plugin_permissions", "cognix_user_permissions", "cognix_role_permissions"],
        "dataClass": "authorization",
    },
    {
        "logicalName": "audit_logs",
        "domain": "audit",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_audit_logs"],
        "supportingTables": ["cognix_security_events", "cognix_admin_user_views"],
        "dataClass": "security_audit",
    },
    {
        "logicalName": "fine_tuning_jobs",
        "domain": "fine_tuning",
        "ownerService": "Fine-tuning Service",
        "canonicalTables": ["cognix_fine_tuning_jobs"],
        "supportingTables": ["cognix_background_jobs", "cognix_approval_requests"],
        "dataClass": "job_metadata",
    },
    {
        "logicalName": "datasets",
        "domain": "fine_tuning",
        "ownerService": "Fine-tuning Service",
        "canonicalTables": ["cognix_datasets"],
        "supportingTables": ["cognix_generated_datasets", "cognix_dataset_examples", "cognix_dataset_quality_scores"],
        "dataClass": "dataset_metadata",
    },
    {
        "logicalName": "lora_adapters",
        "domain": "fine_tuning",
        "ownerService": "Fine-tuning Service",
        "canonicalTables": ["cognix_lora_adapters"],
        "supportingTables": ["cognix_library_items"],
        "dataClass": "model_artifact_metadata",
    },
    {
        "logicalName": "deployment_targets",
        "domain": "deployment",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_deployment_targets"],
        "supportingTables": ["cognix_provider_profiles", "cognix_sandboxes"],
        "dataClass": "infrastructure_metadata",
    },
    {
        "logicalName": "billing_events",
        "domain": "billing",
        "ownerService": "Backend API",
        "canonicalTables": ["cognix_billing_events"],
        "supportingTables": ["cognix_execution_cost_logs", "cognix_organization_usage_summary"],
        "dataClass": "billing_sensitive",
    },
]


def _sqlite_tables(path: Path) -> set[str]:
    if not path.exists():
        return set()
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri = True)
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return {str(row[0]) for row in rows}
    finally:
        conn.close()


def _schema_snapshot(
    *,
    auth_tables: set[str] | None,
    studio_tables: set[str] | None,
    rag_tables: set[str] | None,
) -> dict[str, set[str]]:
    schemas = {
        "auth": set(auth_tables) if auth_tables is not None else _sqlite_tables(auth_db_path()),
        "studio": set(studio_tables) if studio_tables is not None else _sqlite_tables(studio_db_path()),
        "rag": set(rag_tables) if rag_tables is not None else _sqlite_tables(rag_db_path()),
    }
    schemas["all"] = set().union(*schemas.values())
    return schemas


def _table_record(definition: dict[str, Any], all_tables: set[str]) -> dict[str, Any]:
    canonical = [str(item) for item in definition.get("canonicalTables") or []]
    supporting = [str(item) for item in definition.get("supportingTables") or []]
    present_canonical = sorted(item for item in canonical if item in all_tables)
    present_supporting = sorted(item for item in supporting if item in all_tables)
    if present_canonical:
        status = "available"
    elif present_supporting:
        status = "partial"
    else:
        status = "planned"
    return {
        "logicalName": definition["logicalName"],
        "domain": definition["domain"],
        "ownerService": definition["ownerService"],
        "dataClass": definition["dataClass"],
        "status": status,
        "canonicalTables": canonical,
        "supportingTables": supporting,
        "presentCanonicalTables": present_canonical,
        "presentSupportingTables": present_supporting,
        "runtimeMigrationAllowed": False,
    }


def _global_table_domain(table_name: str) -> str:
    if table_name.startswith("admin_") or table_name in {"approval_requests", "approval_decisions", "banned_users"}:
        return "admin"
    if table_name.startswith("project_") or table_name in {"presence_sessions", "project_members", "project_roles"}:
        return "projects"
    if table_name.startswith("enterprise_") or table_name.startswith("encrypted_") or table_name.startswith("chat_"):
        return "enterprise_chat"
    if table_name.startswith("skill") or table_name.endswith("_skills"):
        return "skills"
    if table_name.startswith("directive") or table_name.endswith("_directives"):
        return "directives"
    return table_name.split("_", 1)[0]


def _global_table_record(table_name: str, all_tables: set[str]) -> dict[str, Any]:
    available = table_name in all_tables
    return {
        "tableName": table_name,
        "domain": _global_table_domain(table_name),
        "status": "available" if available else "planned",
        "present": available,
        "sourceOfTruth": GLOBAL_ROADMAP_TABLE_SOURCE,
        "schemaManagedByBootstrap": True,
        "destructiveChangeAllowed": False,
    }


def _module_storage_record(module: dict[str, Any], all_tables: set[str]) -> dict[str, Any]:
    storage_tables = sorted({str(item) for item in module.get("storageTables") or [] if str(item).strip()})
    present_tables = sorted(table for table in storage_tables if table in all_tables)
    planned_tables = sorted(table for table in storage_tables if table not in all_tables)
    if not storage_tables:
        status = "missing_declaration"
    elif not planned_tables:
        status = "available"
    elif present_tables:
        status = "partial"
    else:
        status = "planned"
    return {
        "moduleId": str(module.get("id") or ""),
        "displayName": str(module.get("displayName") or module.get("name") or module.get("id") or ""),
        "status": status,
        "activationState": module.get("activationState"),
        "storageTables": storage_tables,
        "presentStorageTables": present_tables,
        "plannedStorageTables": planned_tables,
        "declaredTableCount": len(storage_tables),
        "presentTableCount": len(present_tables),
        "plannedTableCount": len(planned_tables),
        "eventTypeCount": len(module.get("eventTypes") or []),
        "auditActionCount": len(module.get("auditActions") or []),
        "runtimeMigrationAllowed": False,
    }


def build_database_blueprint(
    *,
    auth_tables: set[str] | None = None,
    studio_tables: set[str] | None = None,
    rag_tables: set[str] | None = None,
) -> dict[str, Any]:
    schemas = _schema_snapshot(
        auth_tables = auth_tables,
        studio_tables = studio_tables,
        rag_tables = rag_tables,
    )
    records = [_table_record(definition, schemas["all"]) for definition in ROADMAP_TABLES]
    global_records = [_global_table_record(table_name, schemas["all"]) for table_name in GLOBAL_ROADMAP_TABLE_NAMES]
    module_registry = cognix_module_registry.build_module_registry()
    module_storage_records = [
        _module_storage_record(module, schemas["all"])
        for module in module_registry.get("modules", [])
        if isinstance(module, dict)
    ]
    available = [item["logicalName"] for item in records if item["status"] == "available"]
    partial = [item["logicalName"] for item in records if item["status"] == "partial"]
    planned = [item["logicalName"] for item in records if item["status"] == "planned"]
    available_global = [item["tableName"] for item in global_records if item["status"] == "available"]
    planned_global = [item["tableName"] for item in global_records if item["status"] == "planned"]
    available_module_storage = [item["moduleId"] for item in module_storage_records if item["status"] == "available"]
    partial_module_storage = [item["moduleId"] for item in module_storage_records if item["status"] == "partial"]
    planned_module_storage = [item["moduleId"] for item in module_storage_records if item["status"] == "planned"]
    missing_module_storage = [
        item["moduleId"] for item in module_storage_records if item["status"] == "missing_declaration"
    ]
    sensitive = [
        item["logicalName"]
        for item in records
        if item["dataClass"] in {"identity_sensitive", "personalization_sensitive", "security_audit", "billing_sensitive"}
    ]
    return {
        "databaseBlueprintVersion": COGNIX_DATABASE_BLUEPRINT_VERSION,
        "mode": "database_blueprint_read_only",
        "sourceOfTruth": "roadmap_section_27",
        "summary": {
            "roadmapTableCount": len(records),
            "availableLogicalTableCount": len(available),
            "partialLogicalTableCount": len(partial),
            "plannedLogicalTableCount": len(planned),
            "physicalTableCount": len(schemas["all"]),
            "globalRoadmapTableCount": len(global_records),
            "availableGlobalRoadmapTableCount": len(available_global),
            "plannedGlobalRoadmapTableCount": len(planned_global),
            "moduleStorageContractCount": len(module_storage_records),
            "availableModuleStorageContractCount": len(available_module_storage),
            "partialModuleStorageContractCount": len(partial_module_storage),
            "plannedModuleStorageContractCount": len(planned_module_storage),
            "missingModuleStorageDeclarationCount": len(missing_module_storage),
            "migrationExecutionAllowed": False,
            "destructiveChangeAllowed": False,
        },
        "coverage": {
            "requiredLogicalTables": [item["logicalName"] for item in records],
            "availableLogicalTables": available,
            "partialLogicalTables": partial,
            "plannedLogicalTables": planned,
            "readyForMvpSchema": all(name in available for name in ("users", "projects", "chats", "messages", "audit_logs")),
        },
        "globalCoverage": {
            "sourceOfTruth": GLOBAL_ROADMAP_TABLE_SOURCE,
            "requiredTables": list(GLOBAL_ROADMAP_TABLE_NAMES),
            "availableTables": available_global,
            "plannedTables": planned_global,
            "readyForV2GlobalSchema": not planned_global,
        },
        "moduleStorageCoverage": {
            "sourceOfTruth": "module_registry_governance_metadata",
            "governanceVersion": module_registry.get("globalPolicies", {}).get("governanceVersion"),
            "requiredModuleIds": [item["moduleId"] for item in module_storage_records],
            "availableModuleIds": available_module_storage,
            "partialModuleIds": partial_module_storage,
            "plannedModuleIds": planned_module_storage,
            "missingDeclarationModuleIds": missing_module_storage,
            "readyForDeclaredModuleStorage": (
                not partial_module_storage and not planned_module_storage and not missing_module_storage
            ),
            "runtimeMigrationAllowed": False,
        },
        "schemaSources": {
            "auth": sorted(schemas["auth"]),
            "studio": sorted(schemas["studio"]),
            "rag": sorted(schemas["rag"]),
            "rawCreateSqlReturned": False,
        },
        "logicalTables": records,
        "globalRoadmapTables": global_records,
        "moduleStorageTables": module_storage_records,
        "migrationPolicy": {
            "schemaChangesAllowedHere": False,
            "requiresReviewedMigration": True,
            "requiresBackup": True,
            "requiresRollbackPlan": True,
            "requiresDataRetentionReview": True,
            "destructiveMigrationAllowed": False,
        },
        "dataIsolationPolicy": {
            "authDatabaseSeparated": "auth_user" in schemas["auth"],
            "ragDatabaseSeparated": bool({"documents", "chunks"} & schemas["rag"]),
            "rawSecretsInBusinessTablesAllowed": False,
            "auditForSensitiveTablesRequired": True,
            "sensitiveLogicalTables": sensitive,
        },
        "sideEffects": {
            "schemaRead": True,
            "databaseWrite": False,
            "migrationRun": False,
            "tableCreate": False,
            "tableAlter": False,
            "tableDrop": False,
            "dataBackfill": False,
            "auditWrite": False,
        },
    }
