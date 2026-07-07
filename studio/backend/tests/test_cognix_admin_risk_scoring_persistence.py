from __future__ import annotations

import asyncio
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage as auth_storage
from core.cognix import admin_security as cognix_admin_security
from core.cognix import module_registry as cognix_module_registry
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(tmp_path / "project_workspaces"))
    monkeypatch.setattr(auth_storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth_storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(auth_storage, "_bootstrap_password", None)
    monkeypatch.setattr(auth_storage, "_api_key_pbkdf2_salt_cache", None)
    monkeypatch.setattr(cognix_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False


def run_async(coro):
    return asyncio.run(coro)


def seed_accounts() -> None:
    auth_storage.create_initial_user(
        username = auth_storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    auth_storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )


def test_risk_scoring_schema_and_module_contract_declares_full_pipeline():
    risk = cognix_admin_security.build_risk_scoring(
        security_events = [],
        audit_logs = [],
        bans = [],
        reports = [],
    )
    assert risk["featureExtractorVersion"] == "cognix_risk_feature_extractor_v1"
    assert risk["recommendationServiceVersion"] == "cognix_risk_recommendation_service_v1"
    assert risk["services"] == ["RiskScoringService", "RiskFeatureExtractor", "RiskRecommendationService"]
    assert {"risk_scores", "risk_events", "risk_recommendations"}.issubset(set(risk["tables"]))

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_global_roadmap_tables(conn)
        cognix_db._ensure_admin_risk_scoring_columns(conn)
        score_columns = {row[1] for row in conn.execute("PRAGMA table_info(risk_scores)").fetchall()}
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(risk_events)").fetchall()}
        rec_columns = {row[1] for row in conn.execute("PRAGMA table_info(risk_recommendations)").fetchall()}
        assert {"entity_type", "entity_id", "score", "level", "features_json", "recommended_action"}.issubset(
            score_columns
        )
        assert {"event_type", "severity", "feature_json", "source_json"}.issubset(event_columns)
        assert {"risk_level", "recommendation", "updated_by"}.issubset(rec_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    security = modules["cognix-admin-security-center"]
    assert "risk_score_persistence" in security["capabilities"]
    assert "/api/cognix/admin/risk-scores/aggregate" in security["routes"]


def test_risk_scoring_aggregate_persists_scores_events_and_recommendations():
    seed_accounts()
    cognix_db.record_security_event(
        username = "alice",
        client_key = "127.0.0.1",
        category = "sql_injection",
        severity = "critical",
        pattern_label = "SQL injection",
        method = "POST",
        path = "/api/auth/login",
        excerpt = "or 1=1",
        create_temporary_ban = True,
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_risk_scores_aggregate(current_subject = "alice"))
    assert user_read.value.status_code == 403

    aggregated = run_async(
        cognix_routes.admin_risk_scores_aggregate(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME)
    )
    assert aggregated["sideEffects"]["riskScoreWrite"] is True
    assert aggregated["sideEffects"]["riskEventWrite"] is True
    assert aggregated["sideEffects"]["riskRecommendationWrite"] is True
    assert aggregated["persistedRiskScores"][0]["entityId"] == "alice"
    assert aggregated["riskRecommendations"][0]["recommendation"]

    scores = run_async(cognix_routes.admin_risk_scores(current_subject = auth_storage.DEFAULT_ADMIN_USERNAME))
    assert scores["persistedRiskScores"][0]["entityId"] == "alice"
    assert scores["riskEvents"][0]["eventType"] == "score_aggregated"
    assert scores["riskRecommendations"][0]["entityId"] == "alice"
