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

from utils.paths import auth_db_path, rag_db_path, studio_db_path


COGNIX_DATABASE_BLUEPRINT_VERSION = "cognix_database_blueprint_v1"

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
        "supportingTables": ["cognix_model_pins", "cognix_project_model_defaults"],
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
    available = [item["logicalName"] for item in records if item["status"] == "available"]
    partial = [item["logicalName"] for item in records if item["status"] == "partial"]
    planned = [item["logicalName"] for item in records if item["status"] == "planned"]
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
        "schemaSources": {
            "auth": sorted(schemas["auth"]),
            "studio": sorted(schemas["studio"]),
            "rag": sorted(schemas["rag"]),
            "rawCreateSqlReturned": False,
        },
        "logicalTables": records,
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
