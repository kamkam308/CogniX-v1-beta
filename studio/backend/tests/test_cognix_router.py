import asyncio
import inspect
import secrets
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage
from auth.authentication import get_current_jwt_subject
from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import context_manager as cognix_context_manager
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import tool_registry as cognix_tool_registry
from core.cognix.router import classify_objective
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(tmp_path / "project_workspaces"))
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(storage, "_bootstrap_password", None)
    monkeypatch.setattr(storage, "_api_key_pbkdf2_salt_cache", None)
    monkeypatch.setattr(cognix_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    cognix_cache_manager.reset_cache_state()
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False
    cognix_cache_manager.reset_cache_state()
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()


def seed_accounts() -> None:
    storage.create_initial_user(
        username = storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )


def run_async(coro):
    return asyncio.run(coro)


def stub_hardware_profile() -> dict[str, object]:
    return {
        "deviceBackend": "cpu",
        "cpuCount": 8,
        "memory": {
            "totalGb": 16.0,
            "availableGb": 10.0,
        },
        "gpu": {
            "available": False,
            "devices": [],
        },
    }


def stub_recommendation(
    hardware: dict[str, object],
    *,
    latest_benchmark_run: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "providers": {
            "configured": [
                {
                    "id": "ollama-local",
                    "type": "ollama",
                    "name": "Ollama Local",
                    "baseUrl": "http://127.0.0.1:11434/v1",
                    "enabled": True,
                }
            ],
            "ollama": {
                "configured": True,
                "reachable": True,
                "hasDefaultModel": True,
            },
        },
        "recommendation": {
            "readiness": "ready",
            "executionMode": "local",
            "providerId": "ollama-local",
            "providerType": "ollama",
            "providerName": "Ollama Local",
            "baseUrl": "http://127.0.0.1:11434/v1",
            "modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "modelLabel": "Qwen 4B local via Ollama",
            "memoryFit": {
                "level": "ok",
                "estimatedRamGb": 4.4,
                "label": "Compatible avec la memoire actuellement disponible",
            },
            "benchmark": {
                "available": latest_benchmark_run is not None,
                "status": "measured" if latest_benchmark_run is not None else "missing",
            },
            "confidence": 0.82,
            "warnings": [],
            "reason": "Machine test compatible avec un petit modele Ollama local.",
        },
    }


def test_router_selects_code_for_python_bug():
    classification = classify_objective("Corrige ce bug Python dans mon backend API")

    assert classification["selectedDomain"] == "code"
    assert classification["recommendedModelLabel"] == "CogniX Code 4B"
    assert classification["confidence"] >= 0.75
    assert classification["needsClarification"] is False


def test_router_flags_close_math_physics_domains():
    classification = classify_objective("Explique cette equation de mecanique avec energie et derivee")

    assert classification["selectedDomain"] in {"maths", "physique"}
    assert classification["needsClarification"] is True
    assert classification["scores"]["maths"] > 0.4
    assert classification["scores"]["physique"] > 0.4


def test_decision_engine_prefers_rag_before_fine_tuning_for_documents():
    classification = classify_objective("Je veux entrainer CogniX pour repondre a partir de mes PDF de cours")
    strategy = cognix_decision_engine.build_task_strategy(
        "Je veux entrainer CogniX pour repondre a partir de mes PDF de cours",
        classification = classification,
    )

    assert strategy["decisionEngineVersion"] == "cognix_decision_engine_v1"
    assert strategy["path"] == "rag_first"
    assert strategy["primaryCapability"] == "rag"
    assert strategy["uses"]["rag"] is True
    assert strategy["uses"]["fineTuning"] is False
    assert strategy["contextPlan"]["includeRagChunks"] is True
    assert strategy["sideEffects"]["ragIndexing"] is False
    assert any("Fine-tuning differe" in item for item in strategy["deferred"])


def test_orchestrator_builds_dry_run_plan_without_loading(monkeypatch):
    monkeypatch.setattr(
        cognix_orchestrator.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_orchestrator.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )

    plan = cognix_orchestrator.build_execution_plan(
        "Corrige ce bug Python dans mon backend API",
        current_subject = "alice",
        project_type = "code",
        runtime_snapshot = {
            "runtimeType": "ollama",
            "activeModel": None,
            "loadedModels": [],
            "loadingModels": [],
        },
    )

    assert plan["mode"] == "dry_run"
    assert plan["classification"]["selectedDomain"] == "code"
    assert plan["executionStrategy"]["selectedModelLabel"] == "Qwen 4B local via Ollama"
    assert plan["executionStrategy"]["domainModelLabel"] == "CogniX Code 4B"
    assert plan["taskStrategy"]["decisionEngineVersion"] == "cognix_decision_engine_v1"
    assert plan["taskStrategy"]["path"] == "codex_guarded_pipeline"
    assert plan["executionStrategy"]["recommendedPath"] == "codex_guarded_pipeline"
    assert plan["executionStrategy"]["primaryCapability"] == "codex_secure_agent"
    assert plan["preloadPlan"]["plannerVersion"] == "cognix_preload_planner_v1"
    assert plan["preloadPlan"]["target"]["domain"] == "code"
    assert plan["preloadPlan"]["sideEffects"]["modelLoad"] is False
    assert plan["executionStrategy"]["preloadAction"] == "would_preload"
    assert any(step["id"] == "plan_preload" for step in plan["steps"])
    assert plan["executionStrategy"]["automaticExecutionAllowed"] is False
    assert plan["executionStrategy"]["securityRiskLevel"] == "high"
    assert plan["executionPolicy"]["policyVersion"] == "cognix_security_policy_v1"
    assert plan["executionPolicy"]["automaticExecutionAllowed"] is False
    assert plan["executionPolicy"]["requiresHumanConfirmation"] is True
    assert plan["executionPolicy"]["guardrails"]["frontendDirectModelCallAllowed"] is False
    assert plan["executionPolicy"]["guardrails"]["sandboxRequired"] is True
    assert plan["executionPolicy"]["deniedSideEffects"]["codeModification"] is True
    assert plan["executionStrategy"]["willLoadModel"] is False
    assert plan["executionStrategy"]["willGenerate"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["codeModification"] is False
    assert any(step["id"] == "apply_execution_policy" for step in plan["steps"])
    assert any(step["id"] == "dry_run_guard" for step in plan["steps"])
    assert any(step["id"] == "choose_task_strategy" for step in plan["steps"])


def test_orchestrator_policy_blocks_tool_execution(monkeypatch):
    monkeypatch.setattr(
        cognix_orchestrator.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_orchestrator.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )

    plan = cognix_orchestrator.build_execution_plan(
        "Prepare un brouillon Gmail pour mon equipe",
        current_subject = "alice",
        project_type = "business",
        runtime_snapshot = {
            "runtimeType": "ollama",
            "activeModel": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "loadedModels": ["huihui_ai/qwen3-vl-abliterated:4b-instruct"],
            "loadingModels": [],
        },
    )

    blocked_ids = {item["id"] for item in plan["executionPolicy"]["blockedActions"]}
    assert plan["taskStrategy"]["path"] == "tool_plan"
    assert plan["executionPolicy"]["riskLevel"] == "medium"
    assert plan["executionPolicy"]["requiresRateLimit"] is True
    assert plan["executionPolicy"]["guardrails"]["frontendDirectToolExecutionAllowed"] is False
    assert plan["executionPolicy"]["deniedSideEffects"]["toolExecution"] is True
    assert "tool_execution" in blocked_ids
    assert plan["executionStrategy"]["requiresModelLoad"] is False
    assert plan["executionStrategy"]["willGenerate"] is False


def test_context_manager_builds_bounded_context_packet():
    packet = cognix_context_manager.build_context_packet(
        current_subject = "alice",
        user_memory = {"content": "Reponds en francais et garde un style concis."},
        project = {
            "id": "project-code",
            "name": "Backend API",
            "instructions": "Priorite a la securite et aux tests.",
        },
        project_id = "project-code",
        objective = "Corrige cette route API",
    )

    assert packet["contextManagerVersion"] == "cognix_context_manager_v1"
    assert packet["mode"] == "minimal"
    assert packet["includedSectionIds"] == ["user_memory", "project_instructions"]
    assert "<cognix_context>" in packet["systemInstruction"]
    assert "<user_memory>" in packet["systemInstruction"]
    assert "<project_instructions>" in packet["systemInstruction"]
    assert packet["sideEffects"]["modelLoad"] is False
    assert packet["sideEffects"]["generation"] is False
    assert packet["sideEffects"]["networkModelCall"] is False


def test_context_pack_endpoint_combines_user_memory_and_project_instructions():
    seed_accounts()
    now_ms = int(time.time() * 1000)
    studio_db_storage.upsert_chat_project(
        {
            "id": "project-code",
            "name": "Backend API",
            "instructions": "Priorite a la securite et aux tests.",
            "archived": False,
            "createdAt": now_ms,
            "updatedAt": now_ms,
        },
        owner_username = "alice",
    )
    cognix_db.update_context_memory(
        "alice",
        "Reponds en francais et garde un style concis.",
        "alice",
    )

    body = run_async(
        cognix_routes.build_context_pack(
            cognix_routes.ContextPackRequest(
                objective = "Corrige cette route API",
                project_id = "project-code",
            ),
            current_subject = "alice",
        )
    )

    assert body["username"] == "alice"
    assert body["projectId"] == "project-code"
    assert body["includedSectionIds"] == ["user_memory", "project_instructions"]
    assert "Reponds en francais" in body["systemInstruction"]
    assert "Priorite a la securite" in body["systemInstruction"]
    assert body["sideEffects"]["networkModelCall"] is False


def test_context_pack_writes_sanitized_audit_log():
    seed_accounts()
    cognix_db.update_context_memory(
        "alice",
        "Preference sensible a ne pas recopier dans les logs.",
        "alice",
    )

    body = run_async(
        cognix_routes.build_context_pack(
            cognix_routes.ContextPackRequest(
                objective = "Corrige cette route API sans fuite de contexte",
                project_id = None,
            ),
            current_subject = "alice",
        )
    )

    assert body["auditLogId"].startswith("aud_")
    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_audit_logs(current_subject = "alice"))
    assert user_read.value.status_code == 403

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    logs = admin_read["logs"]
    assert len(logs) == 1
    log = logs[0]
    assert log["id"] == body["auditLogId"]
    assert log["username"] == "alice"
    assert log["action"] == "context_pack_built"
    assert log["resourceType"] == "cognix_context"
    assert log["metadata"]["sectionIds"] == ["user_memory"]
    assert log["metadata"]["sideEffects"]["networkModelCall"] is False
    assert "Preference sensible" not in log["metadataJson"]


def test_audit_log_retention_prunes_old_entries():
    seed_accounts()
    created_ids: list[str] = []
    for index in range(5):
        log = cognix_db.create_audit_log(
            username = "alice",
            actor_username = "alice",
            action = "retention_test",
            resource_type = "test",
            resource_id = str(index),
            metadata = {"index": index},
        )
        created_ids.append(log["id"])

    deleted = cognix_db.prune_audit_logs(max_entries = 3)
    logs = cognix_db.list_audit_logs(limit = 10)
    kept_ids = {log["id"] for log in logs}

    assert deleted == 2
    assert len(logs) == 3
    assert set(created_ids[-3:]) == kept_ids
    assert set(created_ids[:2]).isdisjoint(kept_ids)


def test_tool_registry_declares_permissions_and_guardrails():
    registry = cognix_tool_registry.build_tool_registry()

    assert registry["registryVersion"] == "cognix_tool_registry_v1"
    assert registry["mode"] == "declarative_guarded"
    assert registry["summary"]["executionEnabled"] is False
    assert registry["globalPolicies"]["frontendDirectExecutionAllowed"] is False
    assert registry["globalPolicies"]["rateLimitsEnabled"] is True
    assert registry["sideEffects"]["toolExecution"] is False

    tools = {tool["id"]: tool for tool in registry["tools"]}
    assert {"github", "google-drive", "gmail", "codex-secure-agent", "kali-isolated"}.issubset(
        tools
    )
    gmail_actions = {action["id"]: action for action in tools["gmail"]["actions"]}
    send_mail = gmail_actions["send_mail"]
    assert send_mail["riskLevel"] == "high"
    assert send_mail["requiresConfirmation"] is True
    assert send_mail["auditRequired"] is True
    assert cognix_tool_registry.rate_limit_policy_for_key(send_mail["rateLimitKey"]) == {
        "windowSeconds": 300,
        "maxEvents": 5,
    }

    kali_actions = {action["id"]: action for action in tools["kali-isolated"]["actions"]}
    assert kali_actions["active_test"]["sandboxRequired"] is True
    assert "admin" in kali_actions["active_test"]["permissions"]


def test_tool_plan_endpoint_allows_safe_declared_action_and_logs_audit():
    seed_accounts()

    body = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "codex-secure-agent",
                action_id = "plan_feature",
            ),
            current_subject = "alice",
        )
    )

    assert body["allowed"] is True
    assert body["status"] == "allowed"
    assert body["requiresConfirmation"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["networkToolCall"] is False
    assert body["rateLimit"]["allowed"] is True
    assert body["rateLimit"]["rateLimitKey"] == "codex:plan"
    assert body["auditLogId"].startswith("aud_")

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    logs = admin_read["logs"]
    assert len(logs) == 1
    log = logs[0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "tool_action_planned"
    assert log["resourceType"] == "cognix_tool_action"
    assert log["metadata"]["toolId"] == "codex-secure-agent"
    assert log["metadata"]["actionId"] == "plan_feature"
    assert log["metadata"]["rateLimit"]["allowed"] is True
    assert log["metadata"]["sideEffects"]["toolExecution"] is False


def test_tool_rate_limit_storage_blocks_after_capacity():
    seed_accounts()

    first = cognix_db.check_rate_limit(
        username = "alice",
        rate_limit_key = "codex:plan",
        action = "unit_test",
        window_seconds = 60,
        max_events = 2,
    )
    second = cognix_db.check_rate_limit(
        username = "alice",
        rate_limit_key = "codex:plan",
        action = "unit_test",
        window_seconds = 60,
        max_events = 2,
    )
    third = cognix_db.check_rate_limit(
        username = "alice",
        rate_limit_key = "codex:plan",
        action = "unit_test",
        window_seconds = 60,
        max_events = 2,
    )

    assert first["allowed"] is True
    assert first["remaining"] == 1
    assert second["allowed"] is True
    assert second["remaining"] == 0
    assert third["allowed"] is False
    assert third["remaining"] == 0
    assert third["consumed"] is False


def test_tool_plan_applies_rate_limit_guard(monkeypatch):
    seed_accounts()
    monkeypatch.setitem(
        cognix_tool_registry.RATE_LIMIT_POLICIES,
        "codex:plan",
        {"windowSeconds": 60, "maxEvents": 1},
    )

    first = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "codex-secure-agent",
                action_id = "plan_feature",
            ),
            current_subject = "alice",
        )
    )
    second = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "codex-secure-agent",
                action_id = "plan_feature",
            ),
            current_subject = "alice",
        )
    )

    assert first["allowed"] is True
    assert first["rateLimit"]["allowed"] is True
    assert second["allowed"] is False
    assert second["status"] == "rate_limited"
    assert second["rateLimit"]["allowed"] is False
    assert second["sideEffects"]["toolExecution"] is False


def test_tool_plan_blocks_disabled_connectors_before_permissions():
    seed_accounts()

    body = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "github",
                action_id = "create_issue",
            ),
            current_subject = "alice",
        )
    )

    assert body["allowed"] is False
    assert body["status"] == "connector_disabled"
    assert body["requiresConfirmation"] is True
    assert body["riskLevel"] == "medium"
    assert body["sideEffects"]["externalWrite"] is False
    assert "developer_mode" in body["missingPermissions"]


def test_admin_permission_grant_and_revoke_affect_tool_planning():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_user_permissions("alice", current_subject = "alice"))
    assert user_read.value.status_code == 403

    granted = run_async(
        cognix_routes.admin_grant_permission(
            "alice",
            cognix_routes.AdminPermissionGrantRequest(permission_key = "developer_mode"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    assert granted["permission"]["permissionKey"] == "developer_mode"
    assert granted["permission"]["grantedBy"] == storage.DEFAULT_ADMIN_USERNAME
    assert granted["auditLogId"].startswith("aud_")

    listed = run_async(
        cognix_routes.admin_user_permissions(
            "alice",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert [item["permissionKey"] for item in listed["permissions"]] == ["developer_mode"]

    allowed = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "codex-secure-agent",
                action_id = "modify_code",
            ),
            current_subject = "alice",
        )
    )
    assert allowed["allowed"] is True
    assert allowed["requiresConfirmation"] is True
    assert allowed["sandboxRequired"] is True

    revoked = run_async(
        cognix_routes.admin_revoke_permission(
            "alice",
            "developer_mode",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert revoked["revoked"] is True

    blocked = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "codex-secure-agent",
                action_id = "modify_code",
            ),
            current_subject = "alice",
        )
    )
    assert blocked["allowed"] is False
    assert blocked["status"] == "missing_permission"
    assert blocked["missingPermissions"] == ["developer_mode"]

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    actions = [log["action"] for log in admin_read["logs"]]
    assert "permission_granted" in actions
    assert "permission_revoked" in actions


def test_router_endpoint_declares_jwt_dependency():
    current_subject = inspect.signature(cognix_routes.classify_route).parameters["current_subject"]

    assert current_subject.default.dependency is get_current_jwt_subject


def test_router_endpoint_uses_project_hint():
    seed_accounts()

    body = run_async(
        cognix_routes.classify_route(
            cognix_routes.RouterClassifyRequest(
                objective = "Explique ce probleme simplement",
                project_type = "code",
            ),
            current_subject = "alice",
        )
    )

    assert body["username"] == "alice"
    assert body["logId"].startswith("rtl_")
    classification = body["classification"]
    assert classification["routingMode"] == "local_keyword_router_v1"
    assert classification["selectedDomain"] == "code"
    assert classification["recommendedModelLabel"] == "CogniX Code 4B"


def test_orchestrator_plan_endpoint_logs_dry_run_decision(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_orchestrator.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_orchestrator.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )
    body = run_async(
        cognix_routes.orchestrator_plan(
            cognix_routes.OrchestratorPlanRequest(
                objective = "Corrige ce bug Python dans mon backend API",
                project_type = "code",
                project_id = "project-local",
            ),
            current_subject = "alice",
        )
    )

    assert body["username"] == "alice"
    assert body["logId"].startswith("rtl_")
    assert body["orchestratorLogId"].startswith("orl_")
    assert body["mode"] == "dry_run"
    assert body["classification"]["selectedDomain"] == "code"
    assert body["taskStrategy"]["path"] == "codex_guarded_pipeline"
    assert body["taskStrategy"]["sideEffects"]["codeModification"] is False
    assert body["preloadPlan"]["plannerVersion"] == "cognix_preload_planner_v1"
    assert body["preloadPlan"]["sideEffects"]["modelLoad"] is False
    assert body["executionStrategy"]["willLoadModel"] is False
    assert body["sideEffects"]["networkModelCall"] is False

    admin_read = run_async(cognix_routes.admin_router_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    logs = admin_read["logs"]
    assert len(logs) == 1
    assert logs[0]["id"] == body["logId"]
    assert logs[0]["selectedDomain"] == "code"

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_orchestrator_logs(current_subject = "alice"))
    assert user_read.value.status_code == 403

    admin_orchestrator_read = run_async(
        cognix_routes.admin_orchestrator_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    orchestrator_logs = admin_orchestrator_read["logs"]
    assert len(orchestrator_logs) == 1
    decision_log = orchestrator_logs[0]
    assert decision_log["id"] == body["orchestratorLogId"]
    assert decision_log["selectedDomain"] == "code"
    assert decision_log["recommendedPath"] == "codex_guarded_pipeline"
    assert decision_log["primaryCapability"] == "codex_secure_agent"
    assert decision_log["decision"]["sideEffects"]["generation"] is False


def test_router_decisions_are_logged_for_admin_review():
    seed_accounts()
    created = run_async(
        cognix_routes.classify_route(
            cognix_routes.RouterClassifyRequest(
                objective = "Corrige ce bug Python dans mon backend API",
                project_type = "code",
            ),
            current_subject = "alice",
        )
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_router_logs(current_subject = "alice"))
    assert user_read.value.status_code == 403

    admin_read = run_async(cognix_routes.admin_router_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    logs = admin_read["logs"]
    assert len(logs) == 1
    log = logs[0]
    assert log["id"] == created["logId"]
    assert log["username"] == "alice"
    assert log["selectedDomain"] == "code"
    assert log["modelLabel"] == "CogniX Code 4B"
    assert log["routingMode"] == "local_keyword_router_v1"
    assert log["needsClarification"] is False
    assert "Python" in log["objectiveExcerpt"]
