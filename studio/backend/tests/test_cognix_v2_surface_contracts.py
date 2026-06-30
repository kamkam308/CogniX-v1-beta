from __future__ import annotations

import sqlite3

from core.cognix import api_surface as cognix_api_surface
from core.cognix import database_blueprint as cognix_database_blueprint
from storage import cognix_db


def test_v2_global_roadmap_tables_are_bootstrapped_with_common_contract_columns():
    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_global_roadmap_tables(conn)
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
        table_names = {row[0] for row in rows}

        assert set(cognix_db.GLOBAL_ROADMAP_TABLE_NAMES).issubset(table_names)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(enterprise_chats)").fetchall()}
        assert {"id", "organization_id", "username", "project_id", "status", "payload_json", "metadata_json"}.issubset(
            columns
        )
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(enterprise_chats)").fetchall()}
        assert "idx_enterprise_chats_org_status" in indexes
        assert "idx_enterprise_chats_scope" in indexes
    finally:
        conn.close()


def test_database_blueprint_reports_v2_global_table_coverage_without_changing_legacy_contract():
    studio_tables = {
        "chat_projects",
        "chat_threads",
        "chat_messages",
        "cognix_audit_logs",
        *cognix_database_blueprint.GLOBAL_ROADMAP_TABLE_NAMES,
    }

    blueprint = cognix_database_blueprint.build_database_blueprint(
        auth_tables = {"auth_user"},
        studio_tables = studio_tables,
        rag_tables = {"documents", "chunks"},
    )

    assert blueprint["databaseBlueprintVersion"] == "cognix_database_blueprint_v1"
    assert blueprint["sourceOfTruth"] == "roadmap_section_27"
    assert blueprint["summary"]["roadmapTableCount"] == 25
    assert blueprint["summary"]["globalRoadmapTableCount"] == len(cognix_database_blueprint.GLOBAL_ROADMAP_TABLE_NAMES)
    assert blueprint["summary"]["plannedGlobalRoadmapTableCount"] == 0
    assert blueprint["globalCoverage"]["sourceOfTruth"] == "v2_sections_42_global_tables"
    assert blueprint["globalCoverage"]["readyForV2GlobalSchema"] is True
    assert "enterprise_chats" in blueprint["globalCoverage"]["availableTables"]
    assert "notifications" in blueprint["globalCoverage"]["availableTables"]
    table_records = {item["tableName"]: item for item in blueprint["globalRoadmapTables"]}
    assert table_records["project_directives"]["schemaManagedByBootstrap"] is True
    assert table_records["project_directives"]["destructiveChangeAllowed"] is False
    assert blueprint["sideEffects"]["databaseWrite"] is False
    assert blueprint["sideEffects"]["tableCreate"] is False


def test_api_surface_reports_v2_product_navigation_routes():
    registered_routes = [
        {"path": "/api/cognix/pulse", "methods": ["GET"]},
        {"path": "/api/cognix/library", "methods": ["GET"]},
        {"path": "/api/cognix/admin/users", "methods": ["GET"]},
        {"path": "/api/cognix/admin/usage", "methods": ["GET"]},
        {"path": "/api/inference/chat/completions", "methods": ["POST"]},
        {"path": "/api/cognix/chat-project-bridge/links", "methods": ["POST"]},
        {"path": "/api/cognix/skills/marketplace", "methods": ["GET"]},
        {"path": "/api/cognix/admin/approvals", "methods": ["GET"]},
    ]

    contract = cognix_api_surface.build_api_surface_contract(registered_routes)
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}

    assert contract["summary"]["productRouteCount"] == len(cognix_api_surface.PRODUCT_NAVIGATION_ROUTES)
    assert contract["productNavigationContract"]["sourceOfTruth"] == "v2_section_41_recommended_routes"
    assert routes["/pulse"]["status"] == "equivalent"
    assert routes["/pulse"]["matchedRoute"] == "/api/cognix/pulse"
    assert routes["/chat"]["matchedRoute"] == "/api/inference/chat/completions"
    assert routes["/projects/:id/skills"]["status"] == "equivalent"
    assert routes["/projects/:id/directives"]["status"] == "planned"
    assert routes["/projects/:id/directives"]["frontendDirectModelCallAllowed"] is False
    assert contract["productNavigationContract"]["coverage"]["readyForV2Navigation"] is False
    assert contract["sideEffects"]["routeRegistration"] is False
    assert contract["sideEffects"]["apiMutation"] is False
