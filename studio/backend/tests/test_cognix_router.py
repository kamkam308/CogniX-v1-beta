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
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import context_manager as cognix_context_manager
from core.cognix import deployment_manager as cognix_deployment_manager
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import governance_manager as cognix_governance_manager
from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import model_lifecycle as cognix_model_lifecycle
from core.cognix import module_registry as cognix_module_registry
from core.cognix import onboarding as cognix_onboarding
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import project_experts as cognix_project_experts
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import tool_registry as cognix_tool_registry
from core.cognix import worker_queue as cognix_worker_queue
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


def stub_gpu_hardware_profile() -> dict[str, object]:
    return {
        "deviceBackend": "cuda",
        "cpuCount": 12,
        "memory": {
            "totalGb": 32.0,
            "availableGb": 22.0,
        },
        "gpu": {
            "available": True,
            "devices": [
                {
                    "name": "Test GPU",
                    "vramTotalGb": 16.0,
                    "vramFreeGb": 13.0,
                }
            ],
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
    assert plan["projectExpertPlan"]["projectExpertsVersion"] == "cognix_project_experts_v1"
    assert plan["projectExpertPlan"]["primaryExpert"]["expertId"] == "cognix-code"
    assert plan["projectExpertPlan"]["primaryExpert"]["selectedModel"]["source"] == "expert_profile"
    assert plan["projectExpertPlan"]["generalistVerifier"]["enabled"] is True
    assert plan["projectExpertPlan"]["executionContract"]["frontendDirectModelCallAllowed"] is False
    assert plan["projectExpertPlan"]["sideEffects"]["modelLoad"] is False
    assert plan["projectExpertPlan"]["sideEffects"]["projectMutation"] is False
    assert plan["executionStrategy"]["projectExpertId"] == "cognix-code"
    assert plan["executionStrategy"]["projectExpertDomain"] == "code"
    assert plan["ragPlan"]["plannerVersion"] == "cognix_rag_planner_v1"
    assert plan["ragPlan"]["recommendedPath"] == "no_rag_needed"
    assert plan["ragPlan"]["sideEffects"]["ragIndexing"] is False
    assert plan["executionStrategy"]["ragReadyForRetrieval"] is False
    assert plan["contextPlan"]["contextManagerVersion"] == "cognix_context_manager_v1"
    assert plan["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
    assert plan["contextPlan"]["sideEffects"]["memoryWrite"] is False
    assert plan["executionStrategy"]["contextAssemblyStrategy"] == "memory_project_recent"
    assert plan["executionStrategy"]["rawHistoryAllowed"] is False
    assert plan["optimizationPlan"]["plannerVersion"] == "cognix_optimization_planner_v1"
    assert plan["optimizationPlan"]["optimizationProfile"] == "balanced"
    assert plan["optimizationPlan"]["sideEffects"]["modelReconfiguration"] is False
    assert plan["executionStrategy"]["optimizationProfile"] == "balanced"
    assert plan["runtimeAdapterPlan"]["runtimeAdapterVersion"] == "cognix_runtime_adapter_v1"
    assert plan["runtimeAdapterPlan"]["selectedAdapter"]["adapterId"] == "ollama"
    assert plan["runtimeAdapterPlan"]["sideEffects"]["runtimeMutation"] is False
    assert plan["executionStrategy"]["runtimeAdapterId"] == "ollama"
    assert plan["codexPipelinePlan"]["plannerVersion"] == "cognix_codex_pipeline_v1"
    assert plan["codexPipelinePlan"]["applicable"] is True
    assert plan["codexPipelinePlan"]["sideEffects"]["codeModification"] is False
    assert plan["executionStrategy"]["codexPipelineApplicable"] is True
    assert plan["executionStrategy"]["codexBranchName"].startswith("cognix/")
    assert plan["workerQueuePlan"]["workerQueueVersion"] == "cognix_worker_queue_v1"
    assert plan["workerQueuePlan"]["summary"]["plannedJobCount"] >= 1
    assert plan["workerQueuePlan"]["sideEffects"]["jobEnqueue"] is False
    assert plan["executionStrategy"]["workerQueueRecommended"] is True
    assert plan["executionStrategy"]["plannedWorkerJobCount"] >= 1
    assert plan["executionStrategy"]["preloadAction"] == "would_preload"
    assert any(step["id"] == "select_runtime_adapter" for step in plan["steps"])
    assert any(step["id"] == "plan_codex_pipeline" for step in plan["steps"])
    assert any(step["id"] == "plan_rag" for step in plan["steps"])
    assert any(step["id"] == "plan_context" for step in plan["steps"])
    assert any(step["id"] == "plan_optimizations" for step in plan["steps"])
    assert any(step["id"] == "plan_preload" for step in plan["steps"])
    assert plan["fineTuningPlan"]["plannerVersion"] == "cognix_fine_tuning_planner_v1"
    assert plan["fineTuningPlan"]["recommendedPath"] == "no_fine_tuning_needed"
    assert plan["fineTuningPlan"]["sideEffects"]["fineTuningJob"] is False
    assert plan["executionStrategy"]["fineTuningMethod"] == "none"
    assert any(step["id"] == "plan_fine_tuning" for step in plan["steps"])
    assert any(step["id"] == "plan_worker_queue" for step in plan["steps"])
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
    assert plan["sideEffects"]["jobEnqueue"] is False
    assert plan["sideEffects"]["workerStart"] is False
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


def test_fine_tuning_plan_endpoint_prepares_qlora_without_training(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_orchestrator.cognix_hardware,
        "get_hardware_profile",
        stub_gpu_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_orchestrator.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )

    body = run_async(
        cognix_routes.fine_tuning_plan(
            cognix_routes.FineTuningPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style de reponse",
                project_type = "education",
                project_id = "project-training",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1500,
                    "estimatedTokens": 650000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 48,
                    "license": "mit",
                    "containsSensitiveData": False,
                },
            ),
            current_subject = "alice",
        )
    )

    plan = body["fineTuningPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert plan["plannerVersion"] == "cognix_fine_tuning_planner_v1"
    assert plan["recommendedPath"] == "guided_fine_tuning"
    assert plan["method"]["type"] == "qlora"
    assert plan["dataset"]["status"] == "ready"
    assert plan["approval"]["required"] is True
    assert plan["approval"]["readyToRequest"] is True
    assert plan["sideEffects"]["datasetImport"] is False
    assert plan["sideEffects"]["fineTuningJob"] is False
    assert plan["sideEffects"]["adapterWrite"] is False
    assert body["executionPolicy"]["automaticExecutionAllowed"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "fine_tuning_plan_built"
    assert log["metadata"]["plannerVersion"] == "cognix_fine_tuning_planner_v1"
    assert log["metadata"]["method"] == "qlora"
    assert log["metadata"]["sideEffects"]["fineTuningJob"] is False


def test_rag_plan_endpoint_prepares_hybrid_retrieval_without_indexing(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(cognix_routes, "_rag_available", lambda: True)
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
        cognix_routes.rag_plan(
            cognix_routes.RagPlanRequest(
                objective = "Reponds a partir de mes PDF de cours avec sources",
                project_type = "education",
                project_id = "project-rag",
                sources = [
                    {
                        "id": "doc-1",
                        "type": "pdf",
                        "indexed": True,
                        "chunkCount": 42,
                    }
                ],
            ),
            current_subject = "alice",
        )
    )

    rag = body["ragPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert rag["plannerVersion"] == "cognix_rag_planner_v1"
    assert rag["recommendedPath"] == "rag_first"
    assert rag["readyForRetrieval"] is True
    assert rag["retrieval"]["strategy"] == "hybrid"
    assert rag["retrieval"]["includeCitations"] is True
    assert rag["contextBudget"]["rawHistoryAllowed"] is False
    assert rag["sourceReadiness"]["indexedSourceCount"] == 1
    assert rag["sideEffects"]["ragIndexing"] is False
    assert rag["sideEffects"]["embeddingGeneration"] is False
    assert rag["sideEffects"]["retrievalQuery"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "rag_plan_built"
    assert log["metadata"]["plannerVersion"] == "cognix_rag_planner_v1"
    assert log["metadata"]["readyForRetrieval"] is True
    assert log["metadata"]["sideEffects"]["ragIndexing"] is False


def test_rag_plan_blocks_retrieval_when_sources_are_missing(monkeypatch):
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
        "Reponds a partir de mes documents de cours",
        current_subject = "alice",
        project_type = "education",
        runtime_snapshot = {
            "runtimeType": "ollama",
            "activeModel": None,
            "loadedModels": [],
            "loadingModels": [],
        },
        rag_sources = [],
        rag_available = True,
    )

    assert plan["taskStrategy"]["path"] == "rag_first"
    assert plan["ragPlan"]["recommendedPath"] == "rag_first"
    assert plan["ragPlan"]["readyForRetrieval"] is False
    assert plan["ragPlan"]["sourceReadiness"]["status"] == "missing"
    assert any(
        item["id"] == "retrieval_query"
        for item in plan["ragPlan"]["blockedActions"]
    )
    assert plan["ragPlan"]["sideEffects"]["retrievalQuery"] is False


def test_fine_tuning_plan_defers_to_rag_for_document_objective(monkeypatch):
    monkeypatch.setattr(
        cognix_orchestrator.cognix_hardware,
        "get_hardware_profile",
        stub_gpu_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_orchestrator.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )

    plan = cognix_orchestrator.build_execution_plan(
        "Je veux entrainer CogniX pour repondre a partir de mes PDF de cours",
        current_subject = "alice",
        project_type = "education",
        runtime_snapshot = {
            "runtimeType": "ollama",
            "activeModel": None,
            "loadedModels": [],
            "loadingModels": [],
        },
        fine_tuning_dataset = {
            "format": "jsonl",
            "sampleCount": 400,
            "estimatedTokens": 120000,
            "license": "mit",
        },
    )

    assert plan["taskStrategy"]["path"] == "rag_first"
    assert plan["fineTuningPlan"]["recommendedPath"] == "rag_before_fine_tuning"
    assert plan["fineTuningPlan"]["method"]["type"] == "none"
    assert any(
        item["id"] == "premature_fine_tuning"
        for item in plan["fineTuningPlan"]["blockedActions"]
    )
    assert plan["fineTuningPlan"]["sideEffects"]["fineTuningJob"] is False


def test_context_plan_reserves_rag_and_caps_history():
    plan = cognix_context_manager.build_context_plan(
        current_subject = "alice",
        objective = "Reponds a partir du document avec citations",
        project_id = "project-rag",
        classification = {"selectedDomain": "education"},
        task_strategy = {"path": "rag_first"},
        recommendation = {"memoryFit": {"level": "ok"}},
        rag_plan = {
            "recommendedPath": "rag_first",
            "readyForRetrieval": True,
            "contextBudget": {"maxContextTokens": 3200},
        },
        user_memory = {"content": "Reponds en francais."},
        project = {"name": "Cours", "instructions": "Toujours citer les sources."},
        recent_messages = [{"role": "user", "content": str(index)} for index in range(10)],
    )

    assert plan["contextManagerVersion"] == "cognix_context_manager_v1"
    assert plan["assemblyStrategy"] == "rag_augmented_context"
    assert plan["tokenBudget"]["rawHistoryAllowed"] is False
    assert plan["tokenBudget"]["recentMessageLimit"] == 6
    assert "rag_chunks" in plan["includedChannelIds"]
    assert "conversation_summary" in plan["requiredChannelIds"]
    assert "never_send_raw_history" in plan["compression"]
    assert "compress_rag_chunks_with_citations" in plan["compression"]
    assert plan["sideEffects"]["ragRetrieval"] is False
    assert plan["sideEffects"]["memoryWrite"] is False


def test_optimization_planner_recommends_memory_safe_profile_without_reconfiguration():
    plan = cognix_optimization_planner.build_optimization_plan(
        hardware = {
            "deviceBackend": "cpu",
            "memory": {"totalGb": 8.0, "availableGb": 3.5},
            "gpu": {"available": False, "devices": []},
        },
        recommendation = {
            "providerType": "ollama",
            "memoryFit": {"level": "tight"},
        },
        cache = {"policy": {"tier": "small_local"}},
        context_plan = {"tokenBudget": {"maxContextTokens": 1800}},
        rag_plan = {"readyForRetrieval": False},
        task_strategy = {"path": "expert_chat"},
    )

    assert plan["plannerVersion"] == "cognix_optimization_planner_v1"
    assert plan["hardwareTier"] == "small_local"
    assert plan["optimizationProfile"] == "memory_saver"
    assert "quantization_profile" in plan["recommendedOptimizationIds"]
    assert any(item["id"] == "single_resident_model" and item["status"] == "recommended" for item in plan["optimizations"])
    assert plan["sideEffects"]["modelReconfiguration"] is False
    assert plan["sideEffects"]["cacheMutation"] is False
    assert plan["sideEffects"]["benchmarkRun"] is False


def test_optimization_plan_endpoint_logs_dry_run_decision(monkeypatch):
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
        cognix_routes.optimization_plan(
            cognix_routes.OptimizationPlanRequest(
                objective = "Optimise CogniX pour repondre vite sans consommer trop de RAM",
                project_type = "general",
            ),
            current_subject = "alice",
        )
    )

    optimization = body["optimizationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_optimization_planner_v1"
    assert optimization["optimizationProfile"] == "balanced"
    assert optimization["sideEffects"]["modelLoad"] is False
    assert optimization["sideEffects"]["modelReconfiguration"] is False
    assert optimization["sideEffects"]["networkModelCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_plan_built"
    assert log["metadata"]["optimizationPlannerVersion"] == "cognix_optimization_planner_v1"
    assert log["metadata"]["sideEffects"]["modelReconfiguration"] is False


def test_runtime_adapter_registry_and_plan_select_ollama_without_side_effects():
    registry = cognix_runtime_adapter.build_runtime_adapter_registry()

    assert registry["runtimeAdapterVersion"] == "cognix_runtime_adapter_v1"
    assert registry["summary"]["directFrontendModelCallAllowed"] is False
    assert registry["globalPolicies"]["frontendMustUseBackend"] is True
    assert registry["sideEffects"]["runtimeMutation"] is False

    plan = cognix_runtime_adapter.build_runtime_adapter_plan(
        recommendation = {"providerType": "ollama"},
        hardware = stub_hardware_profile(),
        task_strategy = {"path": "expert_chat"},
        rag_plan = {"readyForRetrieval": False},
        fine_tuning_plan = {"recommendedPath": "no_fine_tuning_needed"},
        optimization_plan = {"recommendedOptimizationIds": ["prompt_cache"]},
    )

    assert plan["runtimeAdapterVersion"] == "cognix_runtime_adapter_v1"
    assert plan["selectedAdapter"]["adapterId"] == "ollama"
    assert "promptCaching" in plan["selectedAdapter"]["missingCapabilities"]
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["serverStart"] is False
    assert plan["sideEffects"]["networkModelCall"] is False


def test_runtime_adapter_plan_endpoint_logs_audited_dry_run(monkeypatch):
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
        cognix_routes.runtime_plan(
            cognix_routes.RuntimePlanRequest(
                objective = "Choisis le meilleur runtime local pour cette demande",
                project_type = "general",
            ),
            current_subject = "alice",
        )
    )

    adapter_plan = body["runtimeAdapterPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_runtime_adapter_v1"
    assert adapter_plan["selectedAdapter"]["adapterId"] == "ollama"
    assert adapter_plan["sideEffects"]["runtimeMutation"] is False
    assert adapter_plan["sideEffects"]["serverStart"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "runtime_adapter_plan_built"
    assert log["metadata"]["runtimeAdapterVersion"] == "cognix_runtime_adapter_v1"
    assert log["metadata"]["sideEffects"]["runtimeMutation"] is False


def test_onboarding_planner_recommends_small_local_pack_without_side_effects():
    plan = cognix_onboarding.build_onboarding_plan(
        username = "alice",
        hardware = stub_hardware_profile(),
        recommendation = stub_recommendation(stub_hardware_profile())["recommendation"],
        purpose = "developpement",
        level = "intermediaire",
        execution_target = "local",
        priorities = ["confidentialite", "faible consommation"],
        project_type = None,
        latest_benchmark_run = None,
    )

    model_ids = {item["id"] for item in plan["recommendedPack"]["models"]}
    assert plan["onboardingVersion"] == "cognix_onboarding_v1"
    assert plan["profile"]["purpose"] == "development"
    assert plan["recommendedEdition"] == "developer"
    assert plan["hardwareSummary"]["tier"] == "balanced_local"
    assert "cognix-general-3b-q4" in model_ids
    assert "cognix-code-4b-q4" in model_ids
    assert "cognix-onboarding" in plan["recommendedPack"]["modules"]
    assert "cognix-codex-secure-agent" in plan["recommendedPack"]["modules"]
    assert any(item["id"] == "glm-700b" for item in plan["recommendedPack"]["blockedModels"])
    assert any(item["id"] == "run_local_benchmark" for item in plan["firstSteps"])
    assert plan["benchmark"]["recommendedBeforeExecution"] is True
    assert plan["sideEffects"]["profileWrite"] is False
    assert plan["sideEffects"]["modelDownload"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False


def test_onboarding_plan_endpoint_logs_audited_dry_run(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_routes.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )

    body = run_async(
        cognix_routes.onboarding_plan(
            cognix_routes.OnboardingPlanRequest(
                purpose = "education",
                level = "debutant",
                executionTarget = "local",
                priorities = ["hors_ligne", "qualite"],
            ),
            current_subject = "alice",
        )
    )

    plan = body["onboardingPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_onboarding_v1"
    assert plan["profile"]["purpose"] == "education"
    assert plan["recommendedEdition"] == "university"
    assert "cognix-rag" in plan["recommendedPack"]["modules"]
    assert plan["sideEffects"]["settingsWrite"] is False
    assert plan["sideEffects"]["benchmarkRun"] is False
    assert plan["sideEffects"]["ragIndexing"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "onboarding_plan_built"
    assert log["metadata"]["onboardingVersion"] == "cognix_onboarding_v1"
    assert log["metadata"]["purpose"] == "education"
    assert log["metadata"]["sideEffects"]["modelDownload"] is False


def test_deployment_manager_plans_enterprise_target_without_provisioning():
    registry = cognix_deployment_manager.build_deployment_target_registry()
    assert registry["deploymentManagerVersion"] == "cognix_deployment_manager_v1"
    assert registry["globalPolicies"]["productionDeploymentFromPlannerAllowed"] is False
    assert registry["sideEffects"]["deployment"] is False

    plan = cognix_deployment_manager.build_deployment_plan(
        username = "alice",
        objective = "Deployer CogniX pour une equipe entreprise avec audit et SSO",
        hardware = stub_gpu_hardware_profile(),
        recommendation = stub_recommendation(stub_gpu_hardware_profile())["recommendation"],
        target_type = "on_premise",
        edition = "enterprise",
        expected_users = 80,
        data_sensitivity = "confidential",
        requested_features = ["autoscaling", "moe"],
        latest_benchmark_run = {"id": "bench-1", "benchmark": {"benchmarkVersion": "cognix_benchmark_v1"}},
    )

    assert plan["deploymentManagerVersion"] == "cognix_deployment_manager_v1"
    assert plan["mode"] == "dry_run"
    assert plan["recommendedTarget"]["targetId"] in {"on_prem_multi_gpu", "cloud_managed"}
    assert "autoscaling" in plan["requiredCapabilities"]
    assert "moeServing" in plan["requiredCapabilities"]
    assert plan["schedulerPlan"]["workerQueueRequired"] is True
    assert plan["securityPlan"]["rbacRequired"] is True
    assert plan["securityPlan"]["ssoRequired"] is True
    assert plan["securityPlan"]["productionMergeAllowed"] is False
    assert any(item["id"] == "production_deployment" for item in plan["blockedActions"])
    assert plan["sideEffects"]["deployment"] is False
    assert plan["sideEffects"]["infrastructureProvisioning"] is False
    assert plan["sideEffects"]["serverStart"] is False
    assert plan["sideEffects"]["secretWrite"] is False
    assert plan["sideEffects"]["networkExposure"] is False


def test_deployment_plan_endpoint_logs_audited_dry_run(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_hardware,
        "get_hardware_profile",
        stub_gpu_hardware_profile,
    )
    monkeypatch.setattr(
        cognix_routes.cognix_recommender,
        "build_model_recommendation",
        stub_recommendation,
    )

    body = run_async(
        cognix_routes.deployment_plan(
            cognix_routes.DeploymentPlanRequest(
                objective = "Planifie un deploiement CogniX Business pour 12 utilisateurs",
                targetType = "on_premise",
                edition = "business",
                expectedUsers = 12,
                dataSensitivity = "restricted",
                requestedFeatures = ["sso"],
            ),
            current_subject = "alice",
        )
    )

    plan = body["deploymentPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_deployment_manager_v1"
    assert plan["request"]["expectedUsers"] == 12
    assert plan["securityPlan"]["humanApprovalRequired"] is True
    assert plan["sideEffects"]["deployment"] is False
    assert plan["sideEffects"]["containerStart"] is False
    assert plan["sideEffects"]["networkModelCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "deployment_plan_built"
    assert log["metadata"]["deploymentManagerVersion"] == "cognix_deployment_manager_v1"
    assert log["metadata"]["expectedUsers"] == 12
    assert log["metadata"]["sideEffects"]["deployment"] is False


def test_governance_manager_plans_university_rbac_sso_without_mutation():
    blueprint = cognix_governance_manager.build_governance_blueprint()
    assert blueprint["governanceManagerVersion"] == "cognix_governance_manager_v1"
    assert blueprint["globalPolicies"]["frontendCannotGrantRoles"] is True
    assert blueprint["sideEffects"]["roleGrant"] is False
    assert blueprint["sideEffects"]["ssoMutation"] is False

    plan = cognix_governance_manager.build_governance_plan(
        username = "admin",
        organization_name = "CogniX Universite",
        organization_type = "university",
        edition = "university",
        user_count = 420,
        roles = ["teacher", "student", "security_admin"],
        sso_provider = "google_workspace",
        data_sensitivity = "education_records",
        classroom_count = 18,
        requested_features = ["exam_mode", "directory_sync"],
    )

    assert plan["governanceManagerVersion"] == "cognix_governance_manager_v1"
    assert plan["mode"] == "dry_run"
    assert plan["organization"]["type"] == "university"
    assert plan["organization"]["edition"] == "university"
    assert "sso" in plan["requiredCapabilities"]
    assert "education_spaces" in plan["requiredCapabilities"]
    assert "class_permissions" in plan["requiredCapabilities"]
    assert "advanced_audit" in plan["requiredCapabilities"]
    assert {role["id"] for role in plan["roles"]}.issuperset({"admin", "teacher", "student"})
    assert plan["ssoPlan"]["provider"]["id"] == "google_workspace"
    assert plan["ssoPlan"]["directorySyncRequired"] is True
    assert plan["ssoPlan"]["willSyncDirectory"] is False
    assert any(space["id"] == "class_spaces" and space["plannedCount"] == 18 for space in plan["spacePlan"])
    assert plan["policyPlan"]["educationRecordsScoped"] is True
    assert plan["policyPlan"]["policyActivationAllowed"] is False
    assert any(item["id"] == "role_grant" for item in plan["blockedActions"])
    assert plan["sideEffects"]["organizationWrite"] is False
    assert plan["sideEffects"]["roleGrant"] is False
    assert plan["sideEffects"]["permissionWrite"] is False
    assert plan["sideEffects"]["secretRead"] is False
    assert plan["sideEffects"]["secretWrite"] is False
    assert plan["sideEffects"]["directorySync"] is False
    assert plan["sideEffects"]["classroomWrite"] is False


def test_governance_plan_endpoint_requires_admin_and_logs_audited_dry_run():
    seed_accounts()

    with pytest.raises(HTTPException) as user_call:
        run_async(
            cognix_routes.governance_plan(
                cognix_routes.GovernancePlanRequest(
                    organizationName = "CogniX Business",
                    organizationType = "business",
                    edition = "business",
                    userCount = 25,
                    ssoProvider = "microsoft_entra_id",
                    dataSensitivity = "confidential",
                ),
                current_subject = "alice",
            )
        )
    assert user_call.value.status_code == 403

    body = run_async(
        cognix_routes.governance_plan(
            cognix_routes.GovernancePlanRequest(
                organizationName = "CogniX Business",
                organizationType = "business",
                edition = "business",
                userCount = 25,
                roles = ["owner", "admin", "member"],
                ssoProvider = "microsoft_entra_id",
                dataSensitivity = "confidential",
                requestedFeatures = ["directory_sync"],
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    plan = body["governancePlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_governance_manager_v1"
    assert plan["organization"]["id"] == "cognix_business"
    assert plan["ssoPlan"]["provider"]["id"] == "microsoft_entra_id"
    assert plan["policyPlan"]["humanApprovalRequired"] is True
    assert plan["sideEffects"]["organizationWrite"] is False
    assert plan["sideEffects"]["ssoMutation"] is False
    assert plan["sideEffects"]["networkCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "governance_plan_built"
    assert log["resourceType"] == "cognix_governance"
    assert log["metadata"]["governanceManagerVersion"] == "cognix_governance_manager_v1"
    assert log["metadata"]["edition"] == "business"
    assert log["metadata"]["ssoProviderId"] == "microsoft_entra_id"
    assert log["metadata"]["sideEffects"]["organizationWrite"] is False


def test_project_experts_plan_specialized_project_without_loading():
    registry = cognix_project_experts.build_project_expert_registry()
    assert registry["projectExpertsVersion"] == "cognix_project_experts_v1"
    assert registry["globalPolicies"]["specializedProjectsPreferPrimaryExpert"] is True
    assert registry["globalPolicies"]["fallbackToGeneralist"] is True
    assert registry["sideEffects"]["modelLoad"] is False

    plan = cognix_project_experts.build_project_expert_plan(
        objective = "Corrige ce bug TypeScript dans mon API",
        project_id = "project-code",
        project_type = "code",
        project_default_model = {
            "model_id": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "label": "Qwen 4B local via Ollama",
            "provider_type": "ollama",
            "provider_id": "ollama-local",
        },
        classification = {"selectedDomain": "code", "scores": {"code": 0.91}, "needsClarification": False},
        recommendation = stub_recommendation(stub_hardware_profile())["recommendation"],
        preload_plan = {
            "target": {"modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct", "priority": 85},
            "actions": [{"type": "would_preload", "reason": "Projet code actif."}],
        },
        rag_plan = {"recommendedPath": "no_rag_needed", "retrieval": {"strategy": "none"}},
        context_plan = {
            "assemblyStrategy": "memory_project_recent",
            "tokenBudget": {"maxContextTokens": 4096, "rawHistoryAllowed": False},
        },
    )

    assert plan["projectExpertsVersion"] == "cognix_project_experts_v1"
    assert plan["projectMode"] == "specialized_project"
    assert plan["selectionSource"] == "project_type"
    assert plan["primaryExpert"]["expertId"] == "cognix-code"
    assert plan["primaryExpert"]["selectedModel"]["source"] == "project_default_model"
    assert plan["primaryExpert"]["selectedModel"]["modelId"] == "huihui_ai/qwen3-vl-abliterated:4b-instruct"
    assert plan["generalistVerifier"]["enabled"] is True
    assert any(item["expertId"] == "cognix-general" for item in plan["secondaryExperts"])
    assert plan["projectMemoryPlan"]["projectMemoryRequired"] is True
    assert plan["projectMemoryPlan"]["rawHistoryAllowed"] is False
    assert plan["preloadIntent"]["willPreload"] is False
    assert plan["executionContract"]["routingMode"] == "direct_expert_for_specialized_project"
    assert plan["executionContract"]["willLoadModel"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["defaultModelWrite"] is False
    assert plan["sideEffects"]["projectMutation"] is False


def test_project_expert_plan_endpoint_uses_project_default_and_logs_audit(monkeypatch):
    seed_accounts()
    now_ms = int(time.time() * 1000)
    studio_db_storage.upsert_chat_project(
        {
            "id": "project-code",
            "name": "Code API",
            "instructions": "Utilise les tests et garde les changements natifs.",
            "archived": False,
            "createdAt": now_ms,
            "updatedAt": now_ms,
        },
        owner_username = "alice",
    )
    cognix_db.set_project_model_default(
        "alice",
        "project-code",
        "huihui_ai/qwen3-vl-abliterated:4b-instruct",
        "Qwen 4B local via Ollama",
        provider_type = "ollama",
        provider_id = "ollama-local",
    )
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
    monkeypatch.setattr(
        cognix_routes,
        "_current_model_cache_runtime",
        lambda: {"runtimeType": "dry_run", "activeModel": None, "loadedModels": [], "loadingModels": []},
    )

    body = run_async(
        cognix_routes.project_expert_plan(
            "project-code",
            cognix_routes.ProjectExpertPlanRequest(
                objective = "Corrige ce bug Python dans mon backend",
                projectType = "code",
            ),
            current_subject = "alice",
        )
    )

    expert_plan = body["projectExpertPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_project_experts_v1"
    assert body["defaultModel"]["modelId"] == "huihui_ai/qwen3-vl-abliterated:4b-instruct"
    assert expert_plan["primaryExpert"]["expertId"] == "cognix-code"
    assert expert_plan["primaryExpert"]["selectedModel"]["source"] == "project_default_model"
    assert expert_plan["sideEffects"]["modelLoad"] is False
    assert expert_plan["sideEffects"]["projectMutation"] is False
    assert expert_plan["sideEffects"]["cacheMutation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "project_expert_plan_built"
    assert log["resourceType"] == "cognix_project_expert"
    assert log["metadata"]["projectExpertsVersion"] == "cognix_project_experts_v1"
    assert log["metadata"]["primaryExpertId"] == "cognix-code"
    assert log["metadata"]["selectedModelId"] == "huihui_ai/qwen3-vl-abliterated:4b-instruct"
    assert log["metadata"]["sideEffects"]["modelLoad"] is False


def test_model_lifecycle_plans_expert_pack_without_loading():
    hardware = stub_hardware_profile()
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = None,
        loaded_models = [],
        loading_models = [],
        runtime_type = "ollama",
    )
    registry = {
        "models": [
            {
                "id": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
                "providerId": "ollama-local",
                "providerType": "ollama",
                "source": "ollama",
                "available": True,
            }
        ]
    }

    plan = cognix_model_lifecycle.build_model_lifecycle_plan(
        objective = "Corrige ce bug Python dans mon backend",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        cache = cache,
        classification = {"selectedDomain": "code", "scores": {"code": 0.91}},
        project_expert_plan = {
            "primaryExpert": {
                "domain": "code",
                "selectedModel": {"modelId": "cognix-code-4b-q4"},
            }
        },
        runtime_adapter_plan = {"selectedAdapter": {"adapterId": "llama-cpp"}},
        model_registry = registry,
        project_id = "project-code",
        project_type = "code",
        quality_priority = "balanced",
    )

    assert plan["modelLifecycleVersion"] == "cognix_model_lifecycle_v1"
    assert plan["mode"] == "dry_run"
    assert plan["request"]["targetDomain"] == "code"
    assert plan["selectedPack"]["packId"] == "cognix-code-local"
    assert plan["installPlan"]["required"] is True
    assert plan["loadPlan"]["action"] == "defer_load_until_install"
    assert any(item["modelId"] == "glm-700b" for item in plan["blockedModels"])
    assert plan["policies"]["frontendCannotLoadModelsDirectly"] is True
    assert plan["sideEffects"]["modelDownload"] is False
    assert plan["sideEffects"]["modelInstall"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["modelUnload"] is False
    assert plan["sideEffects"]["runtimeMutation"] is False


def test_model_lifecycle_endpoint_logs_audited_dry_run(monkeypatch):
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
    monkeypatch.setattr(
        cognix_routes,
        "_current_model_cache_runtime",
        lambda: {"runtimeType": "ollama", "activeModel": None, "loadedModels": [], "loadingModels": []},
    )
    monkeypatch.setattr(
        cognix_routes.cognix_registry,
        "build_model_registry",
        lambda: {
            "registryVersion": "local_model_registry_v1",
            "providers": [],
            "models": [
                {
                    "id": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
                    "providerId": "ollama-local",
                    "providerType": "ollama",
                    "source": "ollama",
                    "available": True,
                }
            ],
            "defaultModelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "recommendedModelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "ollama": {
                "configured": True,
                "reachable": True,
                "hasDefaultModel": True,
                "recommendedModel": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            },
        },
    )

    body = run_async(
        cognix_routes.model_lifecycle_plan(
            cognix_routes.ModelLifecyclePlanRequest(
                objective = "Teste Qwen 4B en local sans lancer le modele",
                modelId = "huihui_ai/qwen3-vl-abliterated:4b-instruct",
                projectType = "code",
                offlineRequired = True,
            ),
            current_subject = "alice",
        )
    )

    lifecycle = body["modelLifecyclePlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_model_lifecycle_v1"
    assert lifecycle["selectedPack"]["packId"] == "ollama-qwen-4b-local"
    assert lifecycle["selectedPack"]["availability"]["installed"] is True
    assert lifecycle["installPlan"]["required"] is False
    assert lifecycle["loadPlan"]["willLoad"] is False
    assert lifecycle["sideEffects"]["modelDownload"] is False
    assert lifecycle["sideEffects"]["modelLoad"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "model_lifecycle_plan_built"
    assert log["resourceType"] == "cognix_model_lifecycle"
    assert log["metadata"]["modelLifecycleVersion"] == "cognix_model_lifecycle_v1"
    assert log["metadata"]["selectedPackId"] == "ollama-qwen-4b-local"
    assert log["metadata"]["sideEffects"]["modelLoad"] is False


def test_codex_pipeline_plans_required_gates_without_modifying_code():
    plan = cognix_codex_pipeline.build_codex_pipeline_plan(
        objective = "Ajoute un module CogniX Chemistry dans le code source",
        current_subject = "alice",
        project_id = "project-code",
        classification = {"selectedDomain": "code"},
        task_strategy = {"path": "codex_guarded_pipeline"},
        execution_policy = {"riskLevel": "high"},
    )

    assert plan["plannerVersion"] == "cognix_codex_pipeline_v1"
    assert plan["applicable"] is True
    assert plan["recommendedPath"] == "codex_guarded_pipeline"
    assert plan["branch"]["recommendedName"] == "cognix/project-code"
    assert plan["branch"]["willCreate"] is False
    assert plan["qualityGates"]["testsRequired"] is True
    assert plan["qualityGates"]["buildRequired"] is True
    assert plan["qualityGates"]["humanApprovalRequired"] is True
    assert any(step["id"] == "human_approval" for step in plan["steps"])
    assert any(item["id"] == "commit_push_merge" for item in plan["blockedActions"])
    assert plan["sideEffects"]["fileWrite"] is False
    assert plan["sideEffects"]["codeModification"] is False
    assert plan["sideEffects"]["merge"] is False


def test_codex_pipeline_endpoint_logs_audited_dry_run(monkeypatch):
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
        cognix_routes.codex_pipeline_plan(
            cognix_routes.CodexPipelinePlanRequest(
                objective = "Corrige ce bug Python dans mon backend API",
                project_type = "code",
                project_id = "project-code",
            ),
            current_subject = "alice",
        )
    )

    pipeline = body["codexPipelinePlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_codex_pipeline_v1"
    assert pipeline["applicable"] is True
    assert pipeline["sideEffects"]["branchCreate"] is False
    assert pipeline["sideEffects"]["testExecution"] is False
    assert pipeline["sideEffects"]["codeModification"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "codex_pipeline_plan_built"
    assert log["metadata"]["codexPipelineVersion"] == "cognix_codex_pipeline_v1"
    assert log["metadata"]["sideEffects"]["codeModification"] is False


def test_worker_queue_plans_long_running_jobs_without_enqueueing():
    plan = cognix_worker_queue.build_worker_queue_plan(
        objective = "Corrige ce bug Python et prepare mes PDF pour RAG",
        project_id = "project-code",
        task_strategy = {"path": "codex_guarded_pipeline"},
        rag_plan = {
            "recommendedPath": "rag_first",
            "readyForRetrieval": False,
        },
        fine_tuning_plan = {"recommendedPath": "no_fine_tuning_needed"},
        preload_plan = {
            "actions": [
                {
                    "type": "would_preload",
                    "priority": 72,
                    "reason": "Modele cible pret.",
                }
            ]
        },
        codex_pipeline_plan = {"applicable": True},
        optimization_plan = {
            "optimizations": [
                {"id": "benchmark_calibration", "status": "recommended"},
            ]
        },
        latest_benchmark_run = None,
    )

    job_ids = {job["id"] for job in plan["jobs"]}
    assert plan["workerQueueVersion"] == "cognix_worker_queue_v1"
    assert {"codex_pipeline", "model_preload", "benchmark_run"}.issubset(job_ids)
    assert plan["summary"]["safeToAutoEnqueue"] is False
    assert plan["resourceGuards"]["frontendDirectQueueMutationAllowed"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False
    assert plan["sideEffects"]["workerStart"] is False
    assert plan["sideEffects"]["benchmarkRun"] is False


def test_worker_queue_endpoint_logs_audited_dry_run(monkeypatch):
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
        cognix_routes.worker_queue_plan(
            cognix_routes.WorkerQueuePlanRequest(
                objective = "Corrige ce bug Python dans mon backend API",
                project_type = "code",
                project_id = "project-code",
            ),
            current_subject = "alice",
        )
    )

    queue_plan = body["workerQueuePlan"]
    job_ids = {job["id"] for job in queue_plan["jobs"]}
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_worker_queue_v1"
    assert "codex_pipeline" in job_ids
    assert queue_plan["summary"]["plannedJobCount"] >= 1
    assert queue_plan["sideEffects"]["jobEnqueue"] is False
    assert queue_plan["sideEffects"]["codeModification"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "worker_queue_plan_built"
    assert log["metadata"]["workerQueueVersion"] == "cognix_worker_queue_v1"
    assert "codex_pipeline" in log["metadata"]["plannedJobIds"]
    assert log["metadata"]["sideEffects"]["jobEnqueue"] is False


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
    assert packet["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
    assert packet["sideEffects"]["modelLoad"] is False
    assert packet["sideEffects"]["generation"] is False
    assert packet["sideEffects"]["networkModelCall"] is False
    assert packet["sideEffects"]["memoryWrite"] is False


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
    assert body["contextPlan"]["assemblyStrategy"] == "memory_project_recent"
    assert body["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
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
    assert log["metadata"]["rawHistoryAllowed"] is False
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


def test_module_registry_declares_modular_cognix_capabilities():
    registry = cognix_module_registry.build_module_registry()

    assert registry["moduleRegistryVersion"] == "cognix_module_registry_v1"
    assert registry["mode"] == "declarative_dry_run"
    assert registry["summary"]["uiMutationAllowed"] is False
    assert registry["summary"]["routeMutationAllowed"] is False
    assert registry["sideEffects"]["moduleActivation"] is False
    assert registry["sideEffects"]["uiMutation"] is False

    modules = {item["id"]: item for item in registry["modules"]}
    assert {"cognix-local-core", "cognix-model-lifecycle", "cognix-onboarding", "cognix-rag", "cognix-integrations", "cognix-codex-secure-agent", "cognix-enterprise-foundation", "cognix-deployment-manager"}.issubset(
        modules
    )
    assert modules["cognix-local-core"]["activationState"] == "ready"
    assert modules["cognix-model-lifecycle"]["activationState"] == "ready"
    assert "load_unload_planning" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "/api/cognix/models/lifecycle-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert modules["cognix-onboarding"]["activationState"] == "ready"
    assert modules["cognix-rag"]["dependencyState"]["ready"] is True
    assert "sso_planning" in modules["cognix-enterprise-foundation"]["capabilities"]
    assert "/api/cognix/governance/plan" in modules["cognix-enterprise-foundation"]["routes"]
    assert modules["cognix-deployment-manager"]["dependencyState"]["ready"] is True
    assert "cognix-integrations" in modules["cognix-codex-secure-agent"]["dependencyState"]["dependencies"]


def test_module_plan_endpoint_writes_sanitized_audit_log():
    seed_accounts()

    body = run_async(
        cognix_routes.plan_module_activation(
            cognix_routes.ModulePlanRequest(module_id = "cognix-rag"),
            current_subject = "alice",
        )
    )

    assert body["auditLogId"].startswith("aud_")
    assert body["moduleRegistryVersion"] == "cognix_module_registry_v1"
    assert body["moduleId"] == "cognix-rag"
    assert body["allowedToActivate"] is True
    assert body["sideEffects"]["moduleActivation"] is False
    assert body["sideEffects"]["routeRegistration"] is False
    assert body["sideEffects"]["permissionWrite"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "module_plan_built"
    assert log["resourceType"] == "cognix_module"
    assert log["metadata"]["moduleRegistryVersion"] == "cognix_module_registry_v1"
    assert log["metadata"]["sideEffects"]["moduleActivation"] is False


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


def test_integration_manager_summarizes_connectors_without_secret_access():
    status = cognix_integration_manager.build_integration_status(
        username = "alice",
        is_admin = False,
        has_developer_mode = True,
        granted_permissions = {"github:read"},
    )

    assert status["integrationManagerVersion"] == "cognix_integration_manager_v1"
    assert status["mode"] == "dry_run"
    assert status["summary"]["directFrontendExecutionAllowed"] is False
    assert status["policies"]["secretsStayServerSide"] is True
    assert status["sideEffects"]["secretRead"] is False
    assert status["sideEffects"]["toolExecution"] is False

    integrations = {item["id"]: item for item in status["integrations"]}
    assert integrations["github"]["status"] == "declared_disabled"
    assert integrations["github"]["secretState"] == "required_unverified"
    assert any(item["id"] == "configure_server_secret" for item in integrations["github"]["nextActions"])
    assert integrations["codex-secure-agent"]["enabled"] is True


def test_integration_plan_endpoint_writes_sanitized_audit_log():
    seed_accounts()

    body = run_async(
        cognix_routes.plan_integration(
            cognix_routes.IntegrationPlanRequest(tool_id = "github"),
            current_subject = "alice",
        )
    )

    assert body["auditLogId"].startswith("aud_")
    assert body["integrationManagerVersion"] == "cognix_integration_manager_v1"
    assert body["status"] == "declared_disabled"
    assert body["allowedToActivate"] is False
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["networkToolCall"] is False
    assert any(item["id"] == "enable_connector" for item in body["nextActions"])

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "integration_plan_built"
    assert log["resourceType"] == "cognix_integration"
    assert log["metadata"]["integrationManagerVersion"] == "cognix_integration_manager_v1"
    assert log["metadata"]["sideEffects"]["secretRead"] is False
    assert "access_token" not in log["metadataJson"].lower()
    assert "secret_value" not in log["metadataJson"].lower()


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
