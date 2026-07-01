import asyncio
import inspect
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage
from auth.authentication import get_current_jwt_subject
from core.cognix import admin_activity as cognix_admin_activity
from core.cognix import admin_approvals as cognix_admin_approvals
from core.cognix import admin_banned as cognix_admin_banned
from core.cognix import admin_chat as cognix_admin_chat
from core.cognix import admin_limits as cognix_admin_limits
from core.cognix import admin_permissions as cognix_admin_permissions
from core.cognix import admin_users as cognix_admin_users
from core.cognix import api_surface as cognix_api_surface
from core.cognix import apps as cognix_apps
from core.cognix import background_agents as cognix_background_agents
from core.cognix import batching as cognix_batching
from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import command_palette as cognix_command_palette
from core.cognix import context_graph as cognix_context_graph
from core.cognix import context_heatmap as cognix_context_heatmap
from core.cognix import context_manager as cognix_context_manager
from core.cognix import cost_optimizer as cognix_cost_optimizer
from core.cognix import database_blueprint as cognix_database_blueprint
from core.cognix import dataset_builder as cognix_dataset_builder
from core.cognix import debate_orchestrator as cognix_debate_orchestrator
from core.cognix import deployment_manager as cognix_deployment_manager
from core.cognix import distillation_planner as cognix_distillation_planner
from core.cognix import draft_generation as cognix_draft_generation
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import decision_explainer as cognix_decision_explainer
from core.cognix import dynamic_ui as cognix_dynamic_ui
from core.cognix import evolution_engine as cognix_evolution_engine
from core.cognix import fine_tuning_planner as cognix_fine_tuning_planner
from core.cognix import governance_manager as cognix_governance_manager
from core.cognix import gpts as cognix_gpts
from core.cognix import images as cognix_images
from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import intent_prediction as cognix_intent_prediction
from core.cognix import kv_cache as cognix_kv_cache
from core.cognix import library as cognix_library
from core.cognix import memory_editor as cognix_memory_editor
from core.cognix import memory_manager as cognix_memory_manager
from core.cognix import model_lifecycle as cognix_model_lifecycle
from core.cognix import model_comparison as cognix_model_comparison
from core.cognix import model_translator as cognix_model_translator
from core.cognix import module_registry as cognix_module_registry
from core.cognix import mvp_readiness as cognix_mvp_readiness
from core.cognix import native_tools as cognix_native_tools
from core.cognix import onboarding as cognix_onboarding
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import persona_manager as cognix_persona_manager
from core.cognix import personal_twin as cognix_personal_twin
from core.cognix import performance_monitor as cognix_performance_monitor
from core.cognix import plugin_marketplace as cognix_plugin_marketplace
from core.cognix import preload_planner as cognix_preload_planner
from core.cognix import project_dna as cognix_project_dna
from core.cognix import project_experts as cognix_project_experts
from core.cognix import pulse as cognix_pulse
from core.cognix import prompt_cache as cognix_prompt_cache
from core.cognix import prompt_compression as cognix_prompt_compression
from core.cognix import quantization_advisor as cognix_quantization_advisor
from core.cognix import rag_compression as cognix_rag_compression
from core.cognix import rag_planner as cognix_rag_planner
from core.cognix import research_watch as cognix_research_watch
from core.cognix import response_reflection as cognix_response_reflection
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import sandbox as cognix_sandbox
from core.cognix import scheduled as cognix_scheduled
from core.cognix import security_policy as cognix_security_policy
from core.cognix import semantic_cache as cognix_semantic_cache
from core.cognix import skill_memory as cognix_skill_memory
from core.cognix import simulation as cognix_simulation
from core.cognix import speculative_decoding as cognix_speculative_decoding
from core.cognix import thinking_status as cognix_thinking_status
from core.cognix import timeline as cognix_timeline
from core.cognix import tool_discovery as cognix_tool_discovery
from core.cognix import tool_registry as cognix_tool_registry
from core.cognix import workflow_recorder as cognix_workflow_recorder
from core.cognix import worker_queue as cognix_worker_queue
from core.cognix.router import classify_objective
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage
from utils.paths import studio_db_path


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

    assert classification["routerVersion"] == "cognix_model_router_v2"
    assert classification["selectedDomain"] == "code"
    assert classification["recommendedModelLabel"] == "CogniX Code 4B"
    assert classification["recommendedModelId"] == "cognix-code-4b-q4"
    assert classification["recommendedExpertId"] == "cognix-code"
    assert classification["confidence"] >= 0.75
    assert classification["needsClarification"] is False
    external_moe = classification["externalMoePlan"]
    assert external_moe["routerVersion"] == "cognix_external_moe_router_v1"
    assert external_moe["strategy"] == "direct_primary_expert"
    assert external_moe["primaryExpert"]["expertId"] == "cognix-code"
    assert external_moe["primaryExpert"]["willLoad"] is False
    assert "cognix-general" in {item["expertId"] for item in external_moe["secondaryExperts"]}
    assert external_moe["executionBoundary"]["backendOrchestratorRequired"] is True
    assert external_moe["executionBoundary"]["frontendDirectModelCallAllowed"] is False
    assert external_moe["sideEffects"]["modelLoad"] is False


def test_router_flags_close_math_physics_domains():
    classification = classify_objective("Explique cette equation de mecanique avec energie et derivee")

    assert classification["selectedDomain"] in {"maths", "physique"}
    assert classification["needsClarification"] is True
    assert classification["scores"]["maths"] > 0.4
    assert classification["scores"]["physique"] > 0.4
    external_moe = classification["externalMoePlan"]
    assert external_moe["strategy"] == "clarify_before_expert_load"
    assert external_moe["clarification"]["required"] is True
    assert {
        external_moe["primaryExpert"]["expertId"],
        *(item["expertId"] for item in external_moe["secondaryExperts"]),
    }.issuperset({"cognix-maths", "cognix-physique"})
    assert external_moe["sideEffects"]["generation"] is False


def test_decision_engine_prefers_rag_before_fine_tuning_for_documents():
    classification = classify_objective("Je veux entrainer CogniX pour repondre a partir de mes PDF de cours")
    strategy = cognix_decision_engine.build_task_strategy(
        "Je veux entrainer CogniX pour repondre a partir de mes PDF de cours",
        classification = classification,
    )

    assert strategy["decisionEngineVersion"] == "cognix_decision_engine_v1"
    assert strategy["path"] == "rag_first"
    assert strategy["primaryCapability"] == "rag"
    assert strategy["knowledgeStrategyContract"]["contractVersion"] == "cognix_knowledge_strategy_contract_v1"
    assert strategy["knowledgeStrategyContract"]["selectedStrategy"] == "rag_first"
    assert strategy["knowledgeStrategyContract"]["ragBeforeFineTuning"] is True
    assert strategy["knowledgeStrategyContract"]["fineTuningDeferred"] is True
    assert strategy["knowledgeStrategyContract"]["sideEffects"]["fineTuningJob"] is False
    assert "fine_tuning_job" in strategy["knowledgeStrategyContract"]["blockedActions"]
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
    assert plan["architectureDecision"]["architectureDecisionVersion"] == "cognix_architecture_decision_v1"
    assert plan["architectureDecision"]["primaryPath"] == "codex_guarded_pipeline"
    assert plan["architectureDecision"]["primaryCapability"] == "codex_secure_agent"
    assert plan["architectureDecision"]["selectedModel"]["modelLabel"] == "Qwen 4B local via Ollama"
    assert plan["architectureDecision"]["runtime"]["adapterId"] == "ollama"
    assert plan["architectureDecision"]["routing"]["externalMoeRouterVersion"] == "cognix_external_moe_router_v1"
    assert plan["architectureDecision"]["routing"]["externalMoeStrategy"] == "direct_primary_expert"
    assert plan["architectureDecision"]["routing"]["primaryExpertId"] == "cognix-code"
    assert plan["architectureDecision"]["routing"]["frontendDirectModelCallAllowed"] is False
    assert plan["architectureDecision"]["context"]["rawHistoryAllowed"] is False
    assert plan["architectureDecision"]["cache"]["cacheMutationAllowed"] is False
    assert plan["architectureDecision"]["rag"]["knowledgeStrategyContractVersion"] == "cognix_knowledge_strategy_contract_v1"
    assert plan["architectureDecision"]["rag"]["selectedKnowledgeStrategy"] == "no_knowledge_workflow_needed"
    assert plan["architectureDecision"]["preload"]["loadPredictionStatus"] == "predicted"
    assert plan["architectureDecision"]["preload"]["warmupContractVersion"] == "cognix_model_warmup_contract_v1"
    assert plan["architectureDecision"]["preload"]["willWarmupNow"] is False
    assert plan["architectureDecision"]["preload"]["preloadQueueContractVersion"] == "cognix_preload_queue_contract_v1"
    assert plan["architectureDecision"]["preload"]["preloadQueueStatus"] == "queue_ready"
    assert plan["architectureDecision"]["preload"]["willLoadNow"] is False
    assert plan["architectureDecision"]["security"]["frontendDirectModelCallAllowed"] is False
    assert plan["architectureDecision"]["sideEffects"]["modelLoad"] is False
    assert plan["architectureDecision"]["sideEffects"]["generation"] is False
    assert plan["executionStrategy"]["selectedModelLabel"] == "Qwen 4B local via Ollama"
    assert plan["executionStrategy"]["domainModelLabel"] == "CogniX Code 4B"
    assert plan["executionStrategy"]["domainModelId"] == "cognix-code-4b-q4"
    assert plan["executionStrategy"]["recommendedExpertId"] == "cognix-code"
    assert plan["executionStrategy"]["externalMoeRouterVersion"] == "cognix_external_moe_router_v1"
    assert plan["executionStrategy"]["externalMoePrimaryExpertId"] == "cognix-code"
    assert plan["executionStrategy"]["externalMoeClarificationRequired"] is False
    assert plan["taskStrategy"]["decisionEngineVersion"] == "cognix_decision_engine_v1"
    assert plan["taskStrategy"]["path"] == "codex_guarded_pipeline"
    assert plan["executionStrategy"]["recommendedPath"] == "codex_guarded_pipeline"
    assert plan["executionStrategy"]["primaryCapability"] == "codex_secure_agent"
    assert plan["executionStrategy"]["knowledgeStrategyContractVersion"] == "cognix_knowledge_strategy_contract_v1"
    assert plan["executionStrategy"]["selectedKnowledgeStrategy"] == "no_knowledge_workflow_needed"
    assert plan["executionStrategy"]["preloadQueueStatus"] == "queue_ready"
    assert plan["executionStrategy"]["preloadQueueWillLoadNow"] is False
    assert plan["preloadPlan"]["plannerVersion"] == "cognix_preload_planner_v1"
    assert plan["preloadPlan"]["target"]["domain"] == "code"
    assert plan["preloadPlan"]["loadPrediction"]["predictionVersion"] == "cognix_load_prediction_v1"
    assert plan["preloadPlan"]["warmupContract"]["contractVersion"] == "cognix_model_warmup_contract_v1"
    assert plan["preloadPlan"]["preloadQueueContract"]["contractVersion"] == "cognix_preload_queue_contract_v1"
    assert plan["preloadPlan"]["preloadQueueContract"]["selectedCandidate"]["expertId"] == "cognix-code"
    assert plan["preloadPlan"]["preloadQueueContract"]["selectedCandidate"]["modelId"] == plan["preloadPlan"]["target"]["modelId"]
    assert plan["preloadPlan"]["preloadQueueContract"]["executionGate"]["willLoadNow"] is False
    assert plan["preloadPlan"]["sideEffects"]["modelLoad"] is False
    assert plan["projectExpertPlan"]["projectExpertsVersion"] == "cognix_project_experts_v1"
    assert plan["projectExpertPlan"]["primaryExpert"]["expertId"] == "cognix-code"
    assert plan["projectExpertPlan"]["primaryExpert"]["selectedModel"]["source"] == "expert_profile"
    assert plan["projectExpertPlan"]["generalistVerifier"]["enabled"] is True
    assert plan["projectExpertPlan"]["executionContract"]["frontendDirectModelCallAllowed"] is False
    assert plan["projectExpertPlan"]["projectSessionContract"]["contractVersion"] == "cognix_project_session_contract_v1"
    assert plan["projectExpertPlan"]["projectSessionContract"]["sessionMode"] == "direct_project_expert"
    assert plan["projectExpertPlan"]["projectSessionContract"]["routingPolicy"]["automaticModelLoadAllowed"] is False
    assert plan["projectExpertPlan"]["projectSessionContract"]["preloadBoundary"]["willLoadNow"] is False
    assert plan["projectExpertPlan"]["sideEffects"]["modelLoad"] is False
    assert plan["projectExpertPlan"]["sideEffects"]["projectMutation"] is False
    assert plan["executionStrategy"]["projectExpertId"] == "cognix-code"
    assert plan["executionStrategy"]["projectExpertDomain"] == "code"
    assert plan["executionStrategy"]["projectSessionContractVersion"] == "cognix_project_session_contract_v1"
    assert plan["executionStrategy"]["projectSessionMode"] == "direct_project_expert"
    assert plan["executionStrategy"]["projectSessionWillLoadModel"] is False
    assert plan["ragPlan"]["plannerVersion"] == "cognix_rag_planner_v1"
    assert plan["ragPlan"]["recommendedPath"] == "no_rag_needed"
    assert plan["ragPlan"]["sideEffects"]["ragIndexing"] is False
    assert plan["executionStrategy"]["ragReadyForRetrieval"] is False
    assert plan["contextPlan"]["contextManagerVersion"] == "cognix_context_manager_v1"
    assert plan["contextPlan"]["contextBoundaryContract"]["contractVersion"] == "cognix_context_boundary_contract_v1"
    assert plan["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
    assert plan["contextPlan"]["sideEffects"]["memoryWrite"] is False
    assert plan["executionStrategy"]["contextAssemblyStrategy"] == "memory_project_recent"
    assert plan["executionStrategy"]["contextBoundaryContractVersion"] == "cognix_context_boundary_contract_v1"
    assert plan["executionStrategy"]["rawHistoryAllowed"] is False
    assert plan["executionStrategy"]["frontendRawHistoryUploadAllowed"] is False
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


def test_preload_planner_builds_auditable_lru_contract_without_loading():
    hardware = stub_hardware_profile()
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = "cognix-maths-3b-q4",
        loaded_models = ["cognix-general-3b-q4", "cognix-maths-3b-q4"],
        loading_models = [],
        runtime_type = "ollama",
        project_id = "project-code",
        now = 1000,
    )
    classification = classify_objective("Corrige ce bug Python dans mon backend API", project_type = "code")
    task_strategy = cognix_decision_engine.build_task_strategy(
        "Corrige ce bug Python dans mon backend API",
        classification = classification,
        project_type = "code",
    )

    plan = cognix_preload_planner.build_preload_plan(
        objective = "Corrige ce bug Python dans mon backend API",
        project_type = "code",
        project_id = "project-code",
        classification = classification,
        task_strategy = task_strategy,
        recommendation = stub_recommendation(hardware)["recommendation"],
        cache = cache,
    )

    signal_ids = {item["id"] for item in plan["triggerSignals"]}
    assert plan["plannerVersion"] == "cognix_preload_planner_v1"
    assert plan["target"]["domain"] == "code"
    assert plan["target"]["decisionScore"] > 0.5
    assert plan["actions"][0]["type"] == "would_preload_after_lru"
    assert plan["actions"][0]["requiresExecutor"] is True
    assert plan["cachePreflight"]["requiredEvictionCount"] == 1
    assert plan["cachePreflight"]["proposedEvictions"][0]["modelId"] == "cognix-general-3b-q4"
    assert plan["schedule"]["earliestAfter"] == "project_open_idle"
    assert plan["executionContract"]["contractVersion"] == "cognix_preload_execution_contract_v1"
    assert plan["loadPrediction"]["predictionVersion"] == "cognix_load_prediction_v1"
    assert plan["loadPrediction"]["status"] == "predicted"
    assert plan["loadPrediction"]["predictedNextModelId"] == plan["target"]["modelId"]
    assert plan["loadPrediction"]["policies"]["predictionMayTriggerDirectLoad"] is False
    assert plan["warmupContract"]["contractVersion"] == "cognix_model_warmup_contract_v1"
    assert plan["warmupContract"]["predictionVersion"] == "cognix_load_prediction_v1"
    assert plan["warmupContract"]["allowedToPrepareWarmup"] is True
    assert plan["warmupContract"]["readyForWarmup"] is False
    assert plan["warmupContract"]["willWarmupNow"] is False
    assert plan["warmupContract"]["automaticWarmupAllowed"] is False
    assert plan["warmupContract"]["preconditions"]["evictionsPlanned"] == 1
    assert plan["warmupContract"]["sideEffects"]["modelLoad"] is False
    assert "model_load" in plan["warmupContract"]["blockedActions"]
    queue_contract = plan["preloadQueueContract"]
    assert queue_contract["contractVersion"] == "cognix_preload_queue_contract_v1"
    assert queue_contract["status"] == "approval_required"
    assert queue_contract["selectedCandidate"]["expertId"] == "cognix-code"
    assert queue_contract["selectedCandidate"]["modelId"] == plan["target"]["modelId"]
    assert queue_contract["selectedCandidate"]["requiresHumanConfirmation"] is True
    assert queue_contract["executionGate"]["willLoadNow"] is False
    assert queue_contract["executionGate"]["automaticPreloadAllowed"] is False
    assert queue_contract["executionGate"]["frontendDirectModelLoadAllowed"] is False
    assert queue_contract["sideEffects"]["modelLoad"] is False
    assert "model_load" in queue_contract["blockedActions"]
    assert plan["executionContract"]["observeOnly"] is True
    assert plan["executionContract"]["automaticExecutionAllowed"] is False
    assert plan["executionContract"]["requiresHumanConfirmation"] is True
    assert "model_load" in plan["executionContract"]["blockedActions"]
    assert "project_scope" in signal_ids
    assert "cache_capacity" in signal_ids
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["modelUnload"] is False
    assert plan["sideEffects"]["cacheMutation"] is False


def test_model_preload_plan_endpoint_logs_execution_contract_without_loading(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes,
        "_current_model_cache_runtime",
        lambda: {
            "runtimeType": "ollama",
            "activeModel": None,
            "loadedModels": [],
            "loadingModels": [],
        },
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

    body = run_async(
        cognix_routes.model_preload_plan(
            cognix_routes.PreloadPlanRequest(
                objective = "Corrige ce bug Python dans mon backend API",
                project_type = "code",
                project_id = "project-code",
            ),
            current_subject = "alice",
        )
    )

    plan = body["preloadPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert plan["executionContract"]["contractVersion"] == "cognix_preload_execution_contract_v1"
    assert plan["executionContract"]["observeOnly"] is True
    assert plan["executionContract"]["automaticExecutionAllowed"] is False
    assert plan["loadPrediction"]["predictionVersion"] == "cognix_load_prediction_v1"
    assert plan["loadPrediction"]["status"] == "predicted"
    assert plan["warmupContract"]["contractVersion"] == "cognix_model_warmup_contract_v1"
    assert plan["warmupContract"]["willWarmupNow"] is False
    assert plan["warmupContract"]["sideEffects"]["jobEnqueue"] is False
    assert plan["preloadQueueContract"]["contractVersion"] == "cognix_preload_queue_contract_v1"
    assert plan["preloadQueueContract"]["status"] == "queue_ready"
    assert plan["preloadQueueContract"]["executionGate"]["willLoadNow"] is False
    assert plan["preloadQueueContract"]["sideEffects"]["jobEnqueue"] is False
    assert plan["actions"][0]["type"] == "would_preload"
    assert plan["actions"][0]["requiresExecutor"] is True
    assert plan["actions"][0]["warmupContractVersion"] == "cognix_model_warmup_contract_v1"
    assert plan["actions"][0]["preloadQueueContractVersion"] == "cognix_preload_queue_contract_v1"
    assert plan["cachePreflight"]["requiredEvictionCount"] == 0
    assert plan["schedule"]["runOnlyWhenIdle"] is True
    assert body["sideEffects"]["modelLoad"] is False
    assert body["sideEffects"]["cacheMutation"] is False
    assert body["sideEffects"]["preloadEventWrite"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "preload_plan_built"
    assert log["metadata"]["executionContractVersion"] == "cognix_preload_execution_contract_v1"
    assert log["metadata"]["loadPredictionVersion"] == "cognix_load_prediction_v1"
    assert log["metadata"]["loadPredictionStatus"] == "predicted"
    assert log["metadata"]["warmupContractVersion"] == "cognix_model_warmup_contract_v1"
    assert log["metadata"]["preloadQueueContractVersion"] == "cognix_preload_queue_contract_v1"
    assert log["metadata"]["preloadQueueStatus"] == "queue_ready"
    assert log["metadata"]["preloadQueueWillLoadNow"] is False
    assert log["metadata"]["decisionScore"] == plan["target"]["decisionScore"]
    assert log["metadata"]["recommendedWindowSeconds"] == plan["schedule"]["recommendedWindowSeconds"]
    assert log["metadata"]["requiredEvictionCount"] == 0
    assert log["metadata"]["sideEffects"]["modelLoad"] is False


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


def test_frontend_boundary_contract_blocks_direct_model_runtime_urls():
    contract = cognix_security_policy.build_frontend_boundary_contract(
        endpoint = "http://localhost:11434/api/chat",
        provider_type = "ollama",
        model_id = "qwen-secret-model",
        request_intent = "chat_generation",
    )

    assert contract["contractVersion"] == "cognix_frontend_boundary_contract_v1"
    assert contract["status"] == "blocked_frontend_direct_model_call"
    assert contract["allowedForFrontend"] is False
    assert contract["frontendDirectModelCallAllowed"] is False
    assert contract["backendProxyRequired"] is True
    assert contract["orchestratorPlanRequired"] is True
    assert contract["endpoint"]["hostIsDirectModelRuntime"] is True
    assert contract["sideEffects"]["networkModelCall"] is False
    assert contract["sideEffects"]["generation"] is False


def test_frontend_boundary_contract_allows_backend_generation_proxy_without_generation():
    contract = cognix_security_policy.build_frontend_boundary_contract(
        endpoint = "/api/inference/chat/completions",
        provider_type = "ollama",
        model_id = "qwen-local",
        request_intent = "chat_generation",
    )

    assert contract["status"] == "allowed_backend_boundary"
    assert contract["allowedForFrontend"] is True
    assert contract["endpoint"]["category"] == "backend_inference_proxy"
    assert contract["frontendDirectModelCallAllowed"] is False
    assert contract["secretPolicy"]["rawProviderSecretsInBrowserStorageAllowed"] is False
    assert contract["sideEffects"]["modelLoad"] is False
    assert contract["sideEffects"]["generation"] is False


def test_frontend_boundary_endpoint_logs_sanitized_dry_run():
    seed_accounts()
    body = run_async(
        cognix_routes.frontend_boundary_contract(
            cognix_routes.FrontendBoundaryContractRequest(
                endpoint = "/v1/chat/completions",
                provider_type = "openai",
                model_id = "secret-model-id-should-not-be-logged",
                request_intent = "chat_generation",
            ),
            current_subject = "alice",
        )
    )

    contract = body["frontendBoundaryContract"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_frontend_boundary_contract_v1"
    assert contract["allowedForFrontend"] is True
    assert contract["sideEffects"]["auditWrite"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "frontend_boundary_contract_built"
    assert log["metadata"]["frontendBoundaryVersion"] == "cognix_frontend_boundary_contract_v1"
    assert log["metadata"]["allowedForFrontend"] is True
    assert log["metadata"]["frontendDirectModelCallAllowed"] is False
    assert "secret-model-id-should-not-be-logged" not in log["metadataJson"]


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


def test_fine_tuning_dataset_validation_plan_blocks_bad_metadata_without_reading():
    plan = cognix_fine_tuning_planner.build_dataset_validation_plan(
        username = "alice",
        objective = "Specialiser CogniX sur mon style",
        project_id = "project-training",
        dataset = {
            "format": "txt",
            "sampleCount": 42,
            "estimatedTokens": 9000,
            "duplicateRatio": 0.31,
            "invalidRows": 4,
            "averageResponseTokens": 8,
            "license": "proprietary",
            "containsSensitiveData": True,
            "sourceRef": "dataset-v1",
            "rawPreview": "secret training sample should never be logged",
        },
    )

    blocked = set(plan["summary"]["blockedGateIds"])
    warnings = set(plan["summary"]["warningGateIds"])
    assert plan["validationPlanVersion"] == "cognix_dataset_validation_plan_v1"
    assert plan["status"] == "blocked"
    assert {"format_supported", "duplicates", "invalid_rows", "license"}.issubset(blocked)
    assert {"sample_count", "token_budget", "response_length", "sensitive_data"}.issubset(warnings)
    assert plan["quality"]["readyForFineTuning"] is False
    assert plan["summary"]["requiresHumanReview"] is True
    assert plan["policies"]["rawDatasetLoggingAllowed"] is False
    assert plan["policies"]["datasetContentReadAllowed"] is False
    assert any(item["id"] == "fine_tuning_job" for item in plan["blockedActions"])
    assert plan["sideEffects"]["datasetRead"] is False
    assert plan["sideEffects"]["datasetImport"] is False
    assert plan["sideEffects"]["fineTuningJob"] is False


def test_fine_tuning_dataset_validation_endpoint_audits_without_raw_dataset_leak():
    seed_accounts()

    body = run_async(
        cognix_routes.fine_tuning_dataset_validation(
            cognix_routes.FineTuningDatasetValidationRequest(
                objective = "Specialiser CogniX sur mon style",
                project_id = "project-training",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 900,
                    "estimatedTokens": 180000,
                    "duplicateRatio": 0.02,
                    "invalidRows": 0,
                    "averageResponseTokens": 44,
                    "license": "mit",
                    "containsSensitiveData": False,
                    "sourceRef": "style-dataset-v1",
                    "rawPreview": "private training sentence should stay out of audit",
                },
            ),
            current_subject = "alice",
        )
    )

    validation = body["datasetValidationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert validation["status"] == "ready"
    assert validation["summary"]["readyForFineTuning"] is True
    assert validation["summary"]["blockedGateIds"] == []
    assert validation["sideEffects"]["datasetRead"] is False
    assert validation["sideEffects"]["datasetUpload"] is False
    assert validation["sideEffects"]["fineTuningJob"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "fine_tuning_dataset_validated"
    assert log["metadata"]["validationPlanVersion"] == "cognix_dataset_validation_plan_v1"
    assert log["metadata"]["readyForFineTuning"] is True
    assert log["metadata"]["sideEffects"]["datasetRead"] is False
    assert "private training sentence" not in log["metadataJson"]


def test_fine_tuning_evaluation_plan_blocks_missing_artifact_without_jobs():
    plan = cognix_fine_tuning_planner.build_fine_tuning_evaluation_plan(
        username = "alice",
        objective = "Evaluer un LoRA avant ajout bibliotheque",
        fine_tuning_plan = {
            "recommendedPath": "guided_fine_tuning",
            "method": {"type": "qlora"},
            "baseModel": {"modelId": "qwen-test-4b", "providerType": "ollama"},
            "sideEffects": {"fineTuningJob": False, "cloudTrainingJob": False},
        },
        dataset_validation_plan = {
            "status": "ready",
            "quality": {"label": "ready", "readyForFineTuning": True},
            "summary": {"readyForFineTuning": True},
        },
        training_artifact = None,
        baseline_model = {"modelId": "qwen-test-4b", "providerType": "ollama"},
    )

    assert plan["evaluationPlanVersion"] == "cognix_fine_tuning_evaluation_plan_v1"
    assert plan["status"] == "blocked_missing_gate"
    assert "training_artifact_declared" in plan["summary"]["blockedGateIds"]
    assert plan["readyForEvaluationReview"] is False
    assert plan["readyForEvaluationJob"] is False
    assert plan["libraryRegistrationPlan"]["readyForLibraryRegistration"] is False
    assert plan["sideEffects"]["evaluationJob"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["libraryWrite"] is False
    assert plan["sideEffects"]["modelRegistryWrite"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False


def test_fine_tuning_evaluation_plan_prepares_quality_review_without_generation():
    plan = cognix_fine_tuning_planner.build_fine_tuning_evaluation_plan(
        username = storage.DEFAULT_ADMIN_USERNAME,
        objective = "Comparer le LoRA CogniX style au modele de base",
        fine_tuning_plan = {
            "recommendedPath": "guided_fine_tuning",
            "method": {"type": "cloud_qlora"},
            "baseModel": {"modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct", "providerType": "ollama"},
            "sideEffects": {"fineTuningJob": False, "cloudTrainingJob": False},
        },
        dataset_validation_plan = {
            "status": "ready",
            "quality": {"label": "ready", "readyForFineTuning": True},
            "summary": {"readyForFineTuning": True},
        },
        training_artifact = {
            "artifactId": "lora_style_v1",
            "adapterRef": "artifact://lora/style-v1",
            "trainingRunId": "run_style_v1",
            "rawPreview": "secret row should not appear",
        },
        baseline_model = {
            "modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct",
            "providerType": "ollama",
        },
        requested_metrics = ["Instruction Following", "baseline-quality-delta"],
    )

    assert plan["status"] == "ready_for_evaluation_review"
    assert plan["readyForEvaluationReview"] is True
    assert plan["evaluationPlan"]["willRunEvaluation"] is False
    assert plan["evaluationPlan"]["willLoadModel"] is False
    assert plan["evaluationPlan"]["willGenerate"] is False
    assert plan["evaluationPlan"]["comparison"]["baselineModelId"] == "huihui_ai/qwen3-vl-abliterated:4b-instruct"
    assert "instruction_following" in plan["summary"]["metricIds"]
    assert "baseline_quality_delta" in plan["summary"]["metricIds"]
    assert plan["libraryRegistrationPlan"]["willRegisterModel"] is False
    assert plan["libraryRegistrationPlan"]["requiresEvaluationReport"] is True
    assert plan["policies"]["evaluationRequiredBeforeLibraryRegistration"] is True
    assert plan["sideEffects"]["evaluationJob"] is False
    assert plan["sideEffects"]["generation"] is False
    assert "secret row" not in str(plan)


def test_fine_tuning_evaluation_endpoint_logs_sanitized_plan_without_library_write(monkeypatch):
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
        cognix_routes.fine_tuning_evaluation_plan(
            cognix_routes.FineTuningEvaluationPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                project_type = "education",
                project_id = "project-training",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 900,
                    "estimatedTokens": 220000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 52,
                    "license": "mit",
                    "containsSensitiveData": False,
                    "sourceRef": "style-dataset-v1",
                    "rawPreview": "private eval row should stay out of audit",
                },
                training_artifact = {
                    "artifactId": "lora_style_v1",
                    "adapterRef": "artifact://lora/style-v1",
                    "trainingRunId": "run_style_v1",
                    "secretValue": "secret_value",
                },
                baseline_model = {"modelId": "qwen-test-4b", "providerType": "ollama"},
                requested_metrics = ["instruction_following", "baseline_quality_delta"],
            ),
            current_subject = "alice",
        )
    )

    evaluation = body["fineTuningEvaluationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert evaluation["evaluationPlanVersion"] == "cognix_fine_tuning_evaluation_plan_v1"
    assert evaluation["status"] == "ready_for_evaluation_review"
    assert evaluation["readyForEvaluationJob"] is False
    assert evaluation["trainingArtifact"]["rawPreviewIncluded"] is False
    assert evaluation["trainingArtifact"]["secretValuesIncluded"] is False
    assert evaluation["libraryRegistrationPlan"]["readyForLibraryRegistration"] is False
    assert evaluation["sideEffects"]["evaluationJob"] is False
    assert evaluation["sideEffects"]["libraryWrite"] is False
    assert evaluation["sideEffects"]["modelRegistryWrite"] is False
    assert body["executionPolicy"]["automaticExecutionAllowed"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "fine_tuning_evaluation_plan_built"
    assert log["metadata"]["evaluationPlanVersion"] == "cognix_fine_tuning_evaluation_plan_v1"
    assert log["metadata"]["readyForLibraryRegistration"] is False
    assert log["metadata"]["sideEffects"]["libraryWrite"] is False
    assert "private eval row" not in log["metadataJson"]
    assert "secret_value" not in log["metadataJson"]


def test_fine_tuning_plan_allows_ceo_cloud_training_without_local_gpu(monkeypatch):
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
        cognix_routes.fine_tuning_plan(
            cognix_routes.FineTuningPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                project_type = "education",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 500000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 42,
                    "license": "mit",
                    "containsSensitiveData": False,
                },
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    plan = body["fineTuningPlan"]
    assert plan["recommendedPath"] == "guided_fine_tuning"
    assert plan["method"]["type"] == "cloud_qlora"
    assert plan["method"]["requiresLocalGpu"] is False
    assert plan["method"]["requiresCloudCompute"] is True
    assert plan["hardwareFit"]["tier"] == "cloud_training_ready"
    assert plan["resourceTargetPlan"]["recommendedTargetId"] == "google_colab"
    assert plan["resourceTargetPlan"]["localGpuBypassAllowed"] is True
    assert {"google_colab", "kaggle", "cloud_gpu"}.issubset(
        {item["id"] for item in plan["resourceTargetPlan"]["availableTargets"]}
    )
    assert plan["approval"]["readyToRequest"] is True
    assert plan["sideEffects"]["cloudTrainingJob"] is False
    assert plan["sideEffects"]["cloudCredentialRead"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["metadata"]["method"] == "cloud_qlora"
    assert log["metadata"]["resourceTarget"] == "google_colab"
    assert log["metadata"]["sideEffects"]["cloudTrainingJob"] is False


def test_fine_tuning_plan_keeps_admin_cloud_training_when_plan_is_restored_free(monkeypatch):
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
    real_get_user_profile = storage.get_user_profile

    def restored_profile(username: str) -> dict[str, object] | None:
        profile = real_get_user_profile(username)
        if profile and username == storage.DEFAULT_ADMIN_USERNAME:
            return {**profile, "role": "admin", "plan": "free"}
        return profile

    monkeypatch.setattr(cognix_routes.auth_storage, "get_user_profile", restored_profile)

    body = run_async(
        cognix_routes.fine_tuning_plan(
            cognix_routes.FineTuningPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                project_type = "education",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 500000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 42,
                    "license": "mit",
                    "containsSensitiveData": False,
                },
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    plan = body["fineTuningPlan"]
    assert plan["method"]["type"] == "cloud_qlora"
    assert plan["hardwareFit"]["tier"] == "cloud_training_ready"
    assert plan["resourceTargetPlan"]["localGpuBypassAllowed"] is True
    assert plan["resourceTargetPlan"]["recommendedTargetId"] == "google_colab"


def test_fine_tuning_cloud_handoff_prepares_kaggle_package_without_launch(monkeypatch):
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
        cognix_routes.fine_tuning_cloud_handoff_plan(
            cognix_routes.FineTuningCloudHandoffPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                project_type = "education",
                target_id = "kaggle",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 500000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 42,
                    "license": "mit",
                    "containsSensitiveData": False,
                    "sourceRef": "training-dataset-v1",
                },
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    handoff = body["cloudHandoffPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert handoff["handoffVersion"] == "cognix_cloud_training_handoff_v1"
    assert handoff["status"] == "ready_for_export"
    assert handoff["readyToExport"] is True
    assert handoff["target"]["id"] == "kaggle"
    assert handoff["target"]["exportFormat"] == "kaggle_kernel_plan"
    assert handoff["method"]["type"] == "cloud_qlora"
    assert handoff["datasetAccessPlan"]["datasetDescriptor"]["sourceRef"] == "training-dataset-v1"
    assert handoff["datasetAccessPlan"]["rawDatasetRead"] is False
    assert handoff["notebookPlan"]["rawSecretValuesIncluded"] is False
    assert "HF_TOKEN" in handoff["notebookPlan"]["secretPlaceholders"]
    assert any(item["path"] == "CogniX_training_notebook.ipynb" for item in handoff["artifactManifest"])
    assert any(item["id"] == "cloud_training_job" for item in handoff["blockedActions"])
    assert handoff["sideEffects"]["fileWrite"] is False
    assert handoff["sideEffects"]["notebookWrite"] is False
    assert handoff["sideEffects"]["datasetUpload"] is False
    assert handoff["sideEffects"]["cloudCredentialRead"] is False
    assert handoff["sideEffects"]["cloudTrainingJob"] is False
    assert body["executionPolicy"]["automaticExecutionAllowed"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "fine_tuning_cloud_handoff_plan_built"
    assert log["metadata"]["targetId"] == "kaggle"
    assert log["metadata"]["readyToExport"] is True
    assert log["metadata"]["sideEffects"]["cloudTrainingJob"] is False
    assert "secret_value" not in log["metadataJson"].lower()


def test_distillation_plan_allows_ceo_cloud_training_without_local_gpu():
    plan = cognix_distillation_planner.build_distillation_plan(
        username = storage.DEFAULT_ADMIN_USERNAME,
        objective = "Distiller CogniX Code 7B vers petit expert code 1B",
        teacher_model = {
            "modelId": "teacher-code-7b",
            "parameterCountB": 7,
            "family": "qwen",
            "tokenizerHash": "tok-qwen",
        },
        student_model = {
            "modelId": "student-code-1b",
            "parameterCountB": 1.5,
            "family": "qwen",
            "tokenizerHash": "tok-qwen",
        },
        dataset = {
            "format": "jsonl",
            "sampleCount": 1200,
            "estimatedTokens": 400000,
            "duplicateRatio": 0.01,
            "invalidRows": 0,
            "license": "mit",
            "containsSensitiveData": False,
            "sourceRef": "code-distill-v1",
            "rawPreview": "this raw row must not appear in the plan",
        },
        hardware = stub_hardware_profile(),
        user_plan = "CEO",
        target_id = "kaggle",
    )

    assert plan["plannerVersion"] == "cognix_distillation_planner_v1"
    assert plan["teacherStudentContractVersion"] == "cognix_teacher_student_contract_v1"
    assert plan["evaluationContractVersion"] == "cognix_distillation_eval_contract_v1"
    assert plan["status"] == "ready_for_approval"
    assert plan["readyForApproval"] is True
    assert plan["readyForJob"] is False
    assert plan["teacherStudentContract"]["method"] == "logit_distillation"
    assert plan["teacherStudentContract"]["studentSmallerThanTeacher"] is True
    assert plan["dataset"]["status"] == "ready"
    assert plan["dataset"]["rawPreviewIncluded"] is False
    assert "this raw row" not in str(plan)
    assert plan["resourceTargetPlan"]["status"] == "cloud_ready"
    assert plan["resourceTargetPlan"]["recommendedTargetId"] == "kaggle"
    assert plan["resourceTargetPlan"]["localGpuBypassAllowed"] is True
    assert plan["queuePlan"]["queueId"] == "cloud_training"
    assert plan["queuePlan"]["jobType"] == "cloud_distillation_job"
    assert plan["queuePlan"]["willEnqueueNow"] is False
    assert plan["sideEffects"]["teacherModelCall"] is False
    assert plan["sideEffects"]["distillationJob"] is False
    assert plan["sideEffects"]["cloudDistillationJob"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False
    assert plan["sideEffects"]["cloudCredentialRead"] is False


def test_distillation_plan_blocks_unsafe_student_and_dataset_without_training():
    plan = cognix_distillation_planner.build_distillation_plan(
        username = "alice",
        objective = "Distiller un modele trop petit avec donnees insuffisantes",
        teacher_model = {
            "modelId": "teacher-code-1b",
            "parameterCountB": 1,
            "family": "qwen",
        },
        student_model = {
            "modelId": "student-code-2b",
            "parameterCountB": 2,
            "family": "qwen",
        },
        dataset = {
            "format": "txt",
            "sampleCount": 50,
            "invalidRows": 3,
            "duplicateRatio": 0.2,
            "license": "restricted",
            "containsSensitiveData": True,
            "rawPreview": "secret distillation row",
        },
        hardware = stub_hardware_profile(),
        user_plan = "free",
    )

    blocked = set(plan["summary"]["blockedGateIds"])
    warnings = set(plan["summary"]["warningGateIds"])
    assert plan["status"] == "blocked_by_gates"
    assert plan["readyForApproval"] is False
    assert "student_smaller_than_teacher" in blocked
    assert "dataset_ready" in blocked
    assert "resource_target_ready" in blocked
    assert {"duplicate_ratio", "license_review", "sensitive_data_review"}.issubset(warnings)
    assert plan["resourceTargetPlan"]["status"] == "blocked_no_training_target"
    assert "secret distillation row" not in str(plan)
    assert plan["sideEffects"]["teacherModelCall"] is False
    assert plan["sideEffects"]["datasetRead"] is False
    assert plan["sideEffects"]["distillationJob"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False


def test_distillation_plan_endpoint_audits_without_raw_dataset_leak(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )

    body = run_async(
        cognix_routes.fine_tuning_distillation_plan(
            cognix_routes.FineTuningDistillationPlanRequest(
                objective = "Distiller CogniX Code 7B vers expert 1B",
                target_id = "kaggle",
                teacher_model = {
                    "modelId": "teacher-code-7b",
                    "parameterCountB": 7,
                    "family": "qwen",
                    "tokenizerHash": "tok-qwen",
                },
                student_model = {
                    "modelId": "student-code-1b",
                    "parameterCountB": 1,
                    "family": "qwen",
                    "tokenizerHash": "tok-qwen",
                },
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 400000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "license": "mit",
                    "containsSensitiveData": False,
                    "sourceRef": "code-distill-v1",
                    "rawPreview": "private teacher output should not be logged",
                },
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    plan = body["distillationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_distillation_planner_v1"
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["jobEnqueue"] is False
    assert plan["status"] == "ready_for_approval"
    assert plan["resourceTargetPlan"]["recommendedTargetId"] == "kaggle"
    assert plan["sideEffects"]["cloudDistillationJob"] is False
    assert "private teacher output" not in str(plan)

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "fine_tuning_distillation_plan_built"
    assert log["metadata"]["plannerVersion"] == "cognix_distillation_planner_v1"
    assert log["metadata"]["recommendedTargetId"] == "kaggle"
    assert log["metadata"]["sideEffects"]["cloudDistillationJob"] is False
    assert "private teacher output" not in log["metadataJson"]


def test_fine_tuning_cloud_handoff_blocks_non_ceo_cpu_without_launch(monkeypatch):
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
        cognix_routes.fine_tuning_cloud_handoff_plan(
            cognix_routes.FineTuningCloudHandoffPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                target_id = "google_colab",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 500000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 42,
                    "license": "mit",
                    "containsSensitiveData": False,
                },
            ),
            current_subject = "alice",
        )
    )

    handoff = body["cloudHandoffPlan"]
    assert handoff["status"] == "blocked_not_cloud_eligible"
    assert handoff["readyToExport"] is False
    assert handoff["target"]["id"] == "google_colab"
    assert handoff["sideEffects"]["cloudTrainingJob"] is False
    assert handoff["sideEffects"]["datasetUpload"] is False
    assert handoff["sideEffects"]["cloudCredentialRead"] is False
    assert any("training cloud" in item for item in handoff["warnings"])


def test_dataset_builder_creates_reviewable_examples_without_generation():
    plan = cognix_dataset_builder.build_dataset_plan(
        username = "alice",
        objective = "cours RAG citations securite",
        output_format = "jsonl",
        max_examples = 4,
        documents = [
            {
                "sourceId": "cours-rag",
                "sourceType": "document",
                "title": "Cours RAG",
                "text": (
                    "Le RAG utilise des documents indexes pour fournir des citations fiables. "
                    "La securite impose de verifier les sources avant reponse."
                ),
            },
            {
                "sourceId": "secret-note",
                "sourceType": "chat",
                "title": "Note sensible",
                "text": "Le token prive ne doit jamais etre exporte dans un dataset brut.",
            },
        ],
    )

    assert plan["datasetBuilderVersion"] == "cognix_dataset_builder_v1"
    assert plan["syntheticExampleGeneratorVersion"] == "cognix_synthetic_example_generator_v1"
    assert plan["qualityFilterVersion"] == "cognix_dataset_quality_filter_v1"
    assert plan["exportServiceVersion"] == "cognix_dataset_export_service_v1"
    assert plan["dataset"]["format"] == "jsonl"
    assert plan["dataset"]["exampleCount"] >= 2
    assert plan["qualitySummary"]["sensitiveSourceCount"] == 1
    assert "quality_score" in plan["exportPlan"]["previewJsonl"]
    assert plan["exportPlan"]["willWriteFile"] is False
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["datasetExport"] is False
    assert plan["sideEffects"]["trainingJob"] is False


def test_dataset_builder_endpoint_stores_dataset_examples_and_audits():
    seed_accounts()
    body = run_async(
        cognix_routes.dataset_builder_plan(
            cognix_routes.DatasetBuilderPlanRequest(
                documents = [
                    {
                        "sourceId": "cours-rag",
                        "sourceType": "document",
                        "title": "Cours RAG",
                        "text": (
                            "Le RAG utilise les documents pour repondre avec citations. "
                            "La qualite du dataset depend de sources claires."
                        ),
                    }
                ],
                objective = "RAG citations dataset",
                outputFormat = "jsonl",
                maxExamples = 5,
                storeDataset = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["datasetBuilderPlan"]
    dataset = body["generatedDataset"]
    assert body["auditLogId"].startswith("aud_")
    assert dataset["id"] == plan["dataset"]["datasetId"]
    assert dataset["examples"][0]["id"].startswith("ex_")
    assert dataset["qualityScores"][0]["id"].startswith("dq_")
    assert body["sideEffects"]["datasetWrite"] is True
    assert body["sideEffects"]["fileWrite"] is False
    assert body["sideEffects"]["trainingJob"] is False
    assert body["sideEffects"]["generation"] is False

    listed = run_async(cognix_routes.generated_datasets(current_subject = "alice"))
    assert listed["datasets"][0]["id"] == dataset["id"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "dataset_builder_plan_built"
    assert log["metadata"]["datasetBuilderVersion"] == "cognix_dataset_builder_v1"


def test_persona_builder_binds_tools_to_existing_permissions_only():
    plan = cognix_persona_manager.build_persona_plan(
        username = "alice",
        name = "Coach Python",
        role = "Coach code",
        tone = "technical",
        level = "advanced",
        limits = ["Ne jamais executer un outil sans permission."],
        allowed_tools = ["memory_read", "github", "terminal"],
        preferred_model = "qwen-local",
        memory_ids = ["mem_style"],
        granted_permissions = {"tools:github"},
    )
    tools = {item["toolId"]: item for item in plan["toolPermissions"]["tools"]}

    assert plan["personaManagerVersion"] == "cognix_persona_manager_v1"
    assert plan["templateEngineVersion"] == "cognix_persona_template_engine_v1"
    assert plan["permissionBinderVersion"] == "cognix_persona_permission_binder_v1"
    assert tools["memory_read"]["status"] == "allowed"
    assert tools["github"]["status"] == "allowed"
    assert tools["terminal"]["status"] == "blocked_missing_user_permission"
    assert "terminal" in plan["toolPermissions"]["blockedToolIds"]
    assert plan["memoryScope"]["scopeType"] == "selected_memories"
    assert "ne peut jamais ignorer" in plan["systemPromptTemplate"]["content"]
    assert plan["security"]["cannotBypassUserPermissions"] is True
    assert plan["sideEffects"]["permissionGrant"] is False
    assert plan["sideEffects"]["toolExecution"] is False
    assert plan["sideEffects"]["generation"] is False


def test_persona_endpoint_stores_versions_lists_detail_and_audits():
    seed_accounts()
    body = run_async(
        cognix_routes.persona_plan(
            cognix_routes.PersonaPlanRequest(
                name = "Assistant business EBK",
                role = "Assistant business",
                tone = "direct",
                level = "professional",
                limits = ["Separer faits et hypotheses."],
                allowedTools = ["memory_read", "github"],
                preferredModel = "qwen-local",
                memoryIds = ["mem_business"],
                storePersona = True,
            ),
            current_subject = "alice",
        )
    )

    persona = body["persona"]
    assert body["auditLogId"].startswith("aud_")
    assert persona["id"].startswith("pers_")
    assert persona["versions"][0]["id"].startswith("pver_")
    assert persona["toolPermissions"]["blockedToolIds"] == ["github"]
    assert body["sideEffects"]["personaWrite"] is True
    assert body["sideEffects"]["personaVersionWrite"] is True
    assert body["sideEffects"]["permissionGrant"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["generation"] is False

    listed = run_async(cognix_routes.personas(current_subject = "alice"))
    detail = run_async(cognix_routes.persona_detail(persona["id"], current_subject = "alice"))
    assert listed["personas"][0]["id"] == persona["id"]
    assert detail["persona"]["id"] == persona["id"]
    assert detail["persona"]["versions"][0]["templateVersion"] == "cognix_persona_template_engine_v1"
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "persona_plan_built"
    assert log["metadata"]["blockedToolIds"] == ["github"]


def test_gpts_native_manager_binds_tools_memory_documents_and_runtime():
    plan = cognix_gpts.build_gpt_plan(
        username = "alice",
        name = "Prof physique",
        description = "Assistant pedagogique pour la mecanique",
        instructions = "Explique etape par etape.",
        preferred_model = "qwen-local",
        allowed_tools = ["memory_read", "github", "terminal", "rag_retrieval"],
        document_ids = ["lib_course"],
        memory_ids = ["mem_style"],
        skills = ["pedagogie"],
        directives = ["Ne jamais inventer une citation."],
        privacy_level = "private",
        share_scope = "organization",
        granted_permissions = {"tools:github"},
    )
    tools = {item["toolId"]: item for item in plan["toolBinding"]["tools"]}

    assert plan["gptManagerVersion"] == "cognix_gpt_manager_v1"
    assert plan["customAssistantRuntimeVersion"] == "cognix_custom_assistant_runtime_v1"
    assert plan["permissionBinderVersion"] == "cognix_gpt_permission_binder_v1"
    assert tools["memory_read"]["status"] == "allowed"
    assert tools["github"]["status"] == "allowed"
    assert tools["terminal"]["status"] == "blocked_missing_creator_permission"
    assert tools["rag_retrieval"]["status"] == "allowed"
    assert plan["permissionBinding"]["shareScope"] == "private"
    assert plan["permissionBinding"]["requestedShareScope"] == "organization"
    assert plan["documentBinding"]["rawDocumentReadNow"] is False
    assert plan["memoryBinding"]["rawMemoryReadNow"] is False
    assert plan["runtimePolicy"]["routeThroughOrchestrator"] is True
    assert plan["runtimePolicy"]["generationNow"] is False
    assert plan["security"]["cannotExceedCreatorPermissions"] is True
    assert plan["sideEffects"]["permissionGrant"] is False
    assert plan["sideEffects"]["toolExecution"] is False
    assert plan["sideEffects"]["generation"] is False


def test_gpts_endpoint_stores_lists_runtime_plan_and_audits():
    seed_accounts()
    body = run_async(
        cognix_routes.gpt_plan(
            cognix_routes.GPTPlanRequest(
                name = "Prof physique",
                description = "Aide mecanique",
                instructions = "Explique etape par etape.",
                preferredModel = "qwen-local",
                allowedTools = ["memory_read", "github", "terminal"],
                documentIds = ["lib_course"],
                memoryIds = ["mem_style"],
                skills = ["pedagogie"],
                directives = ["Pas de citations inventees."],
                privacyLevel = "private",
                shareScope = "organization",
                storeGpt = True,
            ),
            current_subject = "alice",
        )
    )

    gpt = body["gpt"]
    assert body["auditLogId"].startswith("aud_")
    assert gpt["id"].startswith("gpt_")
    assert gpt["gptId"] == gpt["id"]
    assert gpt["versions"][0]["id"].startswith("gver_")
    assert gpt["versions"][0]["managerVersion"] == "cognix_gpt_manager_v1"
    assert gpt["toolBinding"]["blockedToolIds"] == ["github", "terminal"]
    assert gpt["documentBinding"]["documentIds"] == ["lib_course"]
    assert gpt["memoryBinding"]["memoryIds"] == ["mem_style"]
    assert gpt["permissionBinding"]["shareScope"] == "private"
    assert body["sideEffects"]["gptWrite"] is True
    assert body["sideEffects"]["gptVersionWrite"] is True
    assert body["sideEffects"]["permissionGrant"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["generation"] is False

    listed = run_async(cognix_routes.gpts(current_subject = "alice"))
    detail = run_async(cognix_routes.gpt_detail(gpt["id"], current_subject = "alice"))
    runtime = run_async(
        cognix_routes.gpt_runtime_plan(
            gpt["id"],
            cognix_routes.GPTRuntimePlanRequest(objective = "Explique Newton"),
            current_subject = "alice",
        )
    )
    assert listed["gpts"][0]["id"] == gpt["id"]
    assert detail["gpt"]["id"] == gpt["id"]
    assert runtime["gptRuntimePlan"]["runtimeGuards"]["generationNow"] is False
    assert runtime["gptRuntimePlan"]["runtimeGuards"]["toolExecutionNow"] is False
    assert runtime["usageLog"]["id"].startswith("guse_")
    assert runtime["usageLog"]["runtimePlan"]["gptId"] == gpt["id"]

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    actions = [item["action"] for item in admin_read["logs"][:2]]
    assert "gpt_runtime_plan_built" in actions
    assert "gpt_plan_built" in actions


def test_command_palette_filters_commands_by_permissions_and_admin_role():
    blueprint = cognix_command_palette.build_command_palette_blueprint()
    search = cognix_command_palette.list_commands(
        query = "codex",
        granted_permissions = set(),
        include_disabled = True,
    )
    commands = {item["id"]: item for item in search["commands"]}
    admin_search = cognix_command_palette.list_commands(
        query = "approval",
        granted_permissions = set(),
        is_admin = True,
        include_disabled = True,
    )
    admin_commands = {item["id"]: item for item in admin_search["commands"]}
    plan = cognix_command_palette.build_command_plan(
        command_id = "launch_codex",
        granted_permissions = set(),
    )

    assert blueprint["commandPaletteVersion"] == "cognix_command_palette_v1"
    assert blueprint["policies"]["commandPlansAreDryRun"] is True
    assert blueprint["sideEffects"]["toolExecution"] is False
    assert commands["launch_codex"]["status"] == "missing_permissions"
    assert commands["launch_codex"]["missingPermissions"] == ["developer_mode"]
    assert admin_commands["view_approvals"]["available"] is True
    assert plan["status"] == "missing_permissions"
    assert plan["allowedToRun"] is False
    assert plan["executionPlan"]["runsToolNow"] is False
    assert plan["executionPlan"]["loadsModelNow"] is False


def test_command_palette_endpoint_searches_plans_logs_and_audits():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "library:read",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    search = run_async(
        cognix_routes.command_palette_search(
            cognix_routes.CommandPaletteSearchRequest(
                query = "document",
                includeDisabled = True,
            ),
            current_subject = "alice",
        )
    )
    commands = {item["id"]: item for item in search["commandPalette"]["commands"]}
    assert commands["search_documents"]["available"] is True

    body = run_async(
        cognix_routes.command_palette_plan(
            cognix_routes.CommandPalettePlanRequest(
                commandId = "search_documents",
                query = "document",
                parameters = {"q": "cours physique"},
                logUsage = True,
            ),
            current_subject = "alice",
        )
    )
    assert body["auditLogId"].startswith("aud_")
    assert body["commandPlan"]["status"] == "ready"
    assert body["commandPlan"]["executionPlan"]["route"] == "/library?focus=search"
    assert body["commandPlan"]["executionPlan"]["runsToolNow"] is False
    assert body["sideEffects"]["commandUsageLogWrite"] is True
    assert body["sideEffects"]["toolExecution"] is False
    assert body["usageLog"]["id"].startswith("cmdlog_")
    assert body["usageLog"]["commandId"] == "search_documents"
    assert body["usageLog"]["metadata"]["allowedToRun"] is True

    blocked = run_async(
        cognix_routes.command_palette_plan(
            cognix_routes.CommandPalettePlanRequest(commandId = "launch_codex"),
            current_subject = "alice",
        )
    )
    assert blocked["commandPlan"]["status"] == "missing_permissions"
    assert blocked["commandPlan"]["command"]["missingPermissions"] == ["developer_mode"]

    usage = run_async(cognix_routes.command_palette_usage(current_subject = "alice"))
    assert [item["commandId"] for item in usage["usageLogs"][:2]] == ["launch_codex", "search_documents"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert admin_read["logs"][0]["action"] == "command_palette_plan_built"


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


def test_rag_retrieval_packet_endpoint_ranks_chunks_with_citations_without_model(monkeypatch):
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
        cognix_routes.rag_retrieval_packet(
            cognix_routes.RagRetrievalPacketRequest(
                objective = "Explique le RAG avec citations fiables",
                project_id = "project-rag",
                sources = [
                    {
                        "id": "cours-rag",
                        "type": "pdf",
                        "indexed": True,
                        "title": "Cours RAG",
                        "chunks": [
                            {
                                "id": "chunk-noise",
                                "content": "La couleur du theme est sombre.",
                            },
                            {
                                "id": "chunk-rag",
                                "page": 4,
                                "content": (
                                    "Le RAG utilise des documents indexes pour fournir des citations "
                                    "fiables et reduire les hallucinations."
                                ),
                            },
                        ],
                    }
                ],
                top_k = 2,
            ),
            current_subject = "alice",
        )
    )

    packet = body["retrievalPacket"]
    assert body["auditLogId"].startswith("aud_")
    assert packet["retrievalPacketVersion"] == "cognix_rag_retrieval_packet_v1"
    assert packet["plannerVersion"] == "cognix_rag_planner_v1"
    assert packet["readyForInjection"] is True
    assert packet["retrieval"]["strategy"] == "lexical"
    assert packet["retrieval"]["includeCitations"] is True
    assert packet["retrieval"]["embeddingRequired"] is False
    assert packet["retrieval"]["vectorStoreRequired"] is False
    assert packet["chunks"][0]["chunkId"] == "chunk-rag"
    assert packet["chunks"][0]["citationId"] == "S1"
    assert packet["citations"][0]["sourceId"] == "cours-rag"
    assert "[S1]" in packet["contextBlock"]
    assert packet["sideEffects"]["networkModelCall"] is False
    assert packet["sideEffects"]["embeddingGeneration"] is False
    assert packet["sideEffects"]["vectorSearch"] is False
    assert packet["sideEffects"]["retrievalQuery"] is True

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "rag_retrieval_packet_built"
    assert log["metadata"]["retrievalPacketVersion"] == "cognix_rag_retrieval_packet_v1"
    assert log["metadata"]["selectedChunkCount"] == 1
    assert log["metadata"]["citationCount"] == 1
    assert "reduire les hallucinations" not in str(log["metadata"])


def test_rag_compression_plan_preserves_citations_without_generation():
    plan = cognix_rag_compression.build_rag_compression_plan(
        username = "alice",
        objective = "RAG PDF QCM citations securite",
        project_id = "project-rag",
        chunks = [
            {
                "chunkId": "c-noise",
                "sourceId": "doc-noise",
                "sourceName": "notes.txt",
                "text": "Theme sombre et couleur du bouton principal.",
                "score": 0.1,
            },
            {
                "chunkId": "c-rag",
                "sourceId": "cours-rag",
                "sourceName": "Cours RAG.pdf",
                "page": 7,
                "text": (
                    "Le RAG PDF doit garder les citations pour repondre aux QCM. "
                    "Chaque reponse sourcee doit conserver le chunk et la page."
                ),
                "score": 0.8,
            },
        ],
        target_tokens = 70,
        max_chunks = 2,
        require_citations = True,
    )

    assert plan["ragCompressionVersion"] == "cognix_rag_compression_v1"
    assert plan["citationRetentionVersion"] == "cognix_rag_citation_retention_v1"
    assert plan["readyForInjection"] is True
    assert plan["compressedChunks"][0]["chunkId"] == "c-rag"
    assert plan["compressedChunks"][0]["citation"]["sourceId"] == "cours-rag"
    assert plan["compressedChunks"][0]["citation"]["page"] == 7
    assert "[S1]" in plan["contextBlock"]
    assert plan["citationContract"]["citationRetentionRequired"] is True
    assert plan["citationContract"]["noUncitedClaims"] is True
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["ragRetrieval"] is False
    assert plan["sideEffects"]["ragIndexing"] is False


def test_rag_compression_plan_blocks_strict_mode_when_citations_are_missing():
    plan = cognix_rag_compression.build_rag_compression_plan(
        username = "alice",
        objective = "RAG citations",
        chunks = [
            {
                "chunkId": "c-missing",
                "text": "Le RAG avec citations est important mais cette ligne n'a pas de source.",
            }
        ],
        require_citations = True,
    )

    assert plan["status"] == "blocked_missing_citations"
    assert plan["readyForInjection"] is False
    assert plan["compressedChunks"] == []
    assert plan["citationContract"]["missingCitationCount"] == 1
    assert plan["sideEffects"]["generation"] is False


def test_rag_compression_plan_endpoint_logs_sanitized_metadata():
    seed_accounts()

    body = run_async(
        cognix_routes.rag_compression_plan(
            cognix_routes.RagCompressionPlanRequest(
                objective = "RAG PDF citations QCM",
                chunks = [
                    {
                        "chunkId": "c-private",
                        "sourceId": "cours-rag",
                        "sourceName": "Cours RAG.pdf",
                        "page": 2,
                        "text": "Phrase privee de source RAG qui ne doit pas entrer dans audit.",
                    }
                ],
                target_tokens = 80,
                max_chunks = 1,
                require_citations = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["ragCompressionPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert plan["readyForInjection"] is True
    assert plan["compressedChunks"][0]["chunkId"] == "c-private"
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["ragRetrieval"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "rag_compression_plan_built"
    assert log["metadata"]["ragCompressionVersion"] == "cognix_rag_compression_v1"
    assert log["metadata"]["selectedChunkIds"] == ["c-private"]
    assert log["metadata"]["sideEffects"]["generation"] is False
    assert "Phrase privee de source RAG" not in log["metadataJson"]


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


def test_rag_source_registry_declares_connectors_without_secret_or_network_access():
    registry = cognix_rag_planner.build_rag_source_registry(
        username = "alice",
        granted_permissions = {"rag:write", "drive:read"},
    )

    assert registry["registryVersion"] == "cognix_rag_source_registry_v1"
    assert registry["plannerVersion"] == "cognix_rag_planner_v1"
    assert registry["mode"] == "declarative_dry_run"
    assert registry["policies"]["sourceManifestsRequired"] is True
    assert registry["policies"]["rawContentLoggingAllowed"] is False
    assert registry["policies"]["frontendDirectIndexingAllowed"] is False
    assert registry["sideEffects"]["fileRead"] is False
    assert registry["sideEffects"]["networkRead"] is False
    assert registry["sideEffects"]["secretRead"] is False
    assert registry["sideEffects"]["ragIndexing"] is False

    connectors = {item["id"]: item for item in registry["sourceConnectors"]}
    assert connectors["project_uploads"]["allowedForIndexing"] is True
    assert connectors["project_uploads"]["requiresSecret"] is False
    assert "pdf" in connectors["project_uploads"]["sourceTypes"]
    assert connectors["google-drive"]["status"] == "planned"
    assert connectors["google-drive"]["requiresSecret"] is True
    assert connectors["google-drive"]["requiresNetwork"] is True
    assert connectors["google-drive"]["allowedForIndexing"] is False
    assert "google-drive" in connectors["google-drive"]["tools"]


def test_rag_source_registry_endpoint_logs_audited_dry_run():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "rag:write",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    body = run_async(cognix_routes.rag_source_registry(current_subject = "alice"))

    assert body["auditLogId"].startswith("aud_")
    assert body["registry"]["registryVersion"] == "cognix_rag_source_registry_v1"
    assert body["registry"]["summary"]["connectorCount"] >= 4
    assert body["sideEffects"]["fileRead"] is False
    assert body["sideEffects"]["secretRead"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "rag_source_registry_built"
    assert log["resourceType"] == "cognix_rag_source_registry"
    assert log["metadata"]["registryVersion"] == "cognix_rag_source_registry_v1"
    assert log["metadata"]["sideEffects"]["ragIndexing"] is False


def test_rag_indexing_plan_prepares_local_sources_without_indexing(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(cognix_routes, "_rag_available", lambda: True)
    cognix_db.grant_user_permission(
        "alice",
        "rag:write",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    body = run_async(
        cognix_routes.rag_indexing_plan(
            cognix_routes.RagIndexingPlanRequest(
                objective = "Indexer mes PDF de cours avec citations",
                project_id = "project-rag",
                sources = [
                    {
                        "id": "course-pdf",
                        "name": "Cours physique.pdf",
                        "type": "pdf",
                        "connector": "local",
                        "estimatedSizeMb": 8,
                    }
                ],
            ),
            current_subject = "alice",
        )
    )

    plan = body["indexingPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert plan["sourceRegistryVersion"] == "cognix_rag_source_registry_v1"
    assert plan["status"] == "ready"
    assert plan["readyToIndexCount"] == 1
    assert plan["summary"]["sourceCount"] == 1
    assert plan["sourcePlans"][0]["status"] == "ready_to_index"
    assert plan["sourcePlans"][0]["missingPermissions"] == []
    assert plan["sourcePlans"][0]["readyToIndex"] is True
    assert any(item["id"] == "vector_write" for item in plan["blockedActions"])
    assert plan["sideEffects"]["fileRead"] is False
    assert plan["sideEffects"]["embeddingGeneration"] is False
    assert plan["sideEffects"]["ragIndexing"] is False
    assert plan["sideEffects"]["vectorWrite"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "rag_indexing_plan_built"
    assert log["metadata"]["status"] == "ready"
    assert log["metadata"]["sideEffects"]["vectorWrite"] is False


def test_rag_indexing_plan_blocks_sensitive_sources_without_explicit_permission(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(cognix_routes, "_rag_available", lambda: True)
    cognix_db.grant_user_permission(
        "alice",
        "rag:write",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    body = run_async(
        cognix_routes.rag_indexing_plan(
            cognix_routes.RagIndexingPlanRequest(
                project_id = "project-sensitive",
                sources = [
                    {
                        "id": "hr-policy",
                        "type": "pdf",
                        "connector": "local",
                        "containsSensitiveData": True,
                    }
                ],
            ),
            current_subject = "alice",
        )
    )

    plan = body["indexingPlan"]
    assert plan["status"] == "planned"
    assert plan["readyToIndexCount"] == 0
    assert plan["summary"]["sensitiveSourceCount"] == 1
    assert "rag:sensitive" in plan["sourcePlans"][0]["missingPermissions"]
    assert plan["sourcePlans"][0]["requiresHumanConfirmation"] is True
    assert plan["sideEffects"]["fileRead"] is False
    assert plan["sideEffects"]["secretRead"] is False
    assert plan["sideEffects"]["ragIndexing"] is False


def test_rag_connector_sync_plan_prepares_drive_handoff_without_network_or_secrets():
    plan = cognix_rag_planner.build_rag_connector_sync_plan(
        username = "alice",
        connector_id = "google-drive",
        project_id = "project-rag",
        objective = "Synchroniser Drive vers le RAG CogniX",
        source_filters = {"folderId": "private-folder", "mimeTypes": ["pdf"]},
        max_documents = 25,
        has_developer_mode = True,
        granted_permissions = {"drive:read", "rag:write"},
    )

    assert plan["connectorSyncContractVersion"] == "cognix_rag_connector_sync_contract_v1"
    assert plan["mode"] == "rag_connector_sync_contract_dry_run"
    assert plan["connectorId"] == "google-drive"
    assert plan["readyForSyncRequest"] is True
    assert plan["readyForIndexing"] is False
    assert plan["syncScope"]["sourceFilterKeys"] == ["folderId", "mimeTypes"]
    assert plan["syncScope"]["rawFilterValuesIncluded"] is False
    assert plan["workerHandoff"]["plannedJobType"] == "rag_connector_sync"
    assert plan["workerHandoff"]["plannedQueue"] == "io_bound"
    assert plan["workerHandoff"]["plannedWorkload"] == "rag_indexing"
    assert plan["workerHandoff"]["jobEnqueueAllowedHere"] is False
    assert plan["integrationPreflight"][0]["actualSecretValuesIncluded"] is False
    assert "secret_read" in plan["blockedActions"]
    assert "document_download" in plan["blockedActions"]
    assert plan["sideEffects"]["networkRead"] is False
    assert plan["sideEffects"]["secretRead"] is False
    assert plan["sideEffects"]["documentDownload"] is False
    assert plan["sideEffects"]["ragIndexing"] is False
    assert plan["sideEffects"]["vectorWrite"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False


def test_rag_connector_sync_plan_blocks_unknown_connector_without_side_effects():
    plan = cognix_rag_planner.build_rag_connector_sync_plan(
        username = "alice",
        connector_id = "unknown-drive",
        project_id = "project-rag",
        granted_permissions = {"rag:write"},
    )

    assert plan["status"] == "unknown_connector"
    assert plan["readyForSyncRequest"] is False
    assert plan["readyForIndexing"] is False
    assert plan["gates"][0]["id"] == "source_manifest_declared"
    assert plan["gates"][0]["status"] == "blocked"
    assert "network_read" in plan["blockedActions"]
    assert "secret_read" in plan["blockedActions"]
    assert plan["sideEffects"]["networkRead"] is False
    assert plan["sideEffects"]["secretRead"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False


def test_rag_connector_sync_endpoint_logs_sanitized_contract():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "drive:read",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )
    cognix_db.grant_user_permission(
        "alice",
        "rag:write",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    body = run_async(
        cognix_routes.rag_connector_sync_plan(
            cognix_routes.RagConnectorSyncPlanRequest(
                connectorId = "google-drive",
                projectId = "project-rag",
                objective = "Synchroniser Drive vers RAG",
                sourceFilters = {"folderId": "private-folder", "mimeTypes": ["pdf"]},
                maxDocuments = 25,
            ),
            current_subject = "alice",
        )
    )

    plan = body["connectorSyncPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_rag_planner_v1"
    assert body["connectorSyncContractVersion"] == "cognix_rag_connector_sync_contract_v1"
    assert plan["connectorId"] == "google-drive"
    assert plan["syncScope"]["sourceFilterKeys"] == ["folderId", "mimeTypes"]
    assert plan["syncScope"]["rawFilterValuesIncluded"] is False
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["networkRead"] is False
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["jobEnqueue"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "rag_connector_sync_plan_built"
    assert log["resourceType"] == "cognix_rag_connector_sync_plan"
    assert log["metadata"]["sourceFilterKeys"] == ["folderId", "mimeTypes"]
    assert "private-folder" not in str(log["metadata"])
    assert log["metadata"]["sideEffects"]["networkRead"] is False
    assert log["metadata"]["sideEffects"]["secretRead"] is False
    assert log["metadata"]["sideEffects"]["auditWrite"] is True


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
    assert plan["benchmarkEvidence"]["contractVersion"] == "cognix_benchmark_evidence_contract_v1"
    assert plan["benchmarkEvidence"]["status"] == "missing"
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
    assert optimization["benchmarkEvidence"]["status"] == "missing"
    assert optimization["sideEffects"]["modelLoad"] is False
    assert optimization["sideEffects"]["modelReconfiguration"] is False
    assert optimization["sideEffects"]["networkModelCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_plan_built"
    assert log["metadata"]["optimizationPlannerVersion"] == "cognix_optimization_planner_v1"
    assert log["metadata"]["benchmarkEvidenceStatus"] == "missing"
    assert log["metadata"]["sideEffects"]["modelReconfiguration"] is False


def test_optimization_capability_registry_declares_benchmark_gated_features_without_mutation():
    hardware = stub_hardware_profile()
    registry = cognix_optimization_planner.build_optimization_capability_registry(
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        latest_benchmark_run = None,
    )

    assert registry["registryVersion"] == "cognix_optimization_capability_registry_v1"
    assert registry["mode"] == "dry_run"
    assert registry["policies"]["benchmarkRequiredBeforeEnable"] is True
    assert registry["policies"]["benchmarkEvidenceContractRequired"] is True
    assert registry["benchmarkEvidence"]["contractVersion"] == "cognix_benchmark_evidence_contract_v1"
    assert registry["benchmarkEvidence"]["status"] == "missing"
    assert registry["policies"]["frontendDirectOptimizationMutationAllowed"] is False
    assert registry["sideEffects"]["runtimeConfigWrite"] is False
    assert registry["sideEffects"]["benchmarkRun"] is False
    assert registry["sideEffects"]["cacheMutation"] is False

    capabilities = {item["id"]: item for item in registry["capabilities"]}
    assert "semantic_cache" in capabilities
    assert "kv_cache_eviction" in capabilities
    assert "flash_attention" in capabilities
    assert capabilities["semantic_cache"]["benchmarkGate"]["status"] == "required"
    assert capabilities["semantic_cache"]["benchmarkGate"]["evidenceStatus"] == "missing"
    assert capabilities["semantic_cache"]["activationPolicy"]["automaticEnableAllowed"] is False
    assert capabilities["kv_cache_eviction"]["sideEffects"]["cacheMutation"] is False


def test_optimization_experiment_plan_requires_benchmark_before_enablement():
    hardware = stub_hardware_profile()
    plan = cognix_optimization_planner.build_optimization_experiment_plan(
        objective = "Tester semantic cache et kv cache eviction",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        latest_benchmark_run = None,
        requested_optimizations = ["semantic_cache", "kv_cache_policy"],
    )

    assert plan["experimentPlanVersion"] == "cognix_optimization_experiment_plan_v1"
    assert plan["mode"] == "dry_run"
    assert plan["benchmarkEvidence"]["status"] == "missing"
    assert plan["selectedOptimizationIds"] == ["semantic_cache", "kv_cache_eviction"]
    assert "benchmark_baseline" in plan["summary"]["blockedGateIds"]
    assert "benchmark_evidence" in plan["summary"]["blockedGateIds"]
    assert all(ticket["status"] == "blocked_by_gates" for ticket in plan["tickets"])
    assert all(ticket["willEnableRuntime"] is False for ticket in plan["tickets"])
    assert all(ticket["willRunBenchmark"] is False for ticket in plan["tickets"])
    assert plan["sideEffects"]["runtimeConfigWrite"] is False
    assert plan["sideEffects"]["cacheMutation"] is False
    assert plan["sideEffects"]["generation"] is False


def test_optimization_experiment_plan_accepts_complete_benchmark_evidence_without_enabling_runtime():
    hardware = stub_hardware_profile()
    plan = cognix_optimization_planner.build_optimization_experiment_plan(
        objective = "Tester KV-cache eviction apres benchmark local",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        latest_benchmark_run = {
            "id": "bench-ready",
            "created_at": "2026-06-29T00:00:00+00:00",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 70.0,
                "estimatedTokensPerSecond": 18.5,
            },
        },
        requested_optimizations = ["kv_cache_policy"],
    )

    ticket = plan["tickets"][0]
    assert plan["benchmarkEvidence"]["status"] == "ready"
    assert plan["benchmarkEvidence"]["readyForExperiment"] is True
    assert "benchmark_baseline" not in plan["summary"]["blockedGateIds"]
    assert "benchmark_evidence" not in plan["summary"]["blockedGateIds"]
    assert ticket["status"] == "ready_for_experiment"
    assert ticket["willEnableRuntime"] is False
    assert ticket["willRunBenchmark"] is False
    assert ticket["rollbackPlan"]["required"] is True


def test_optimization_application_contract_blocks_without_benchmark_or_runtime_mutation():
    hardware = stub_hardware_profile()
    experiment = cognix_optimization_planner.build_optimization_experiment_plan(
        objective = "Preparer application semantic cache",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        latest_benchmark_run = None,
        requested_optimizations = ["semantic_cache"],
    )

    contract = cognix_optimization_planner.build_optimization_application_contract(
        objective = "Preparer application semantic cache",
        experiment_plan = experiment,
        confirmation_id = "conf_apply_semantic_cache",
        rollback_plan_id = "rollback_semantic_cache",
        request_id = "req_apply_semantic_cache",
        project_id = "project-optimization",
    )

    assert contract["applicationContractVersion"] == "cognix_optimization_application_contract_v1"
    assert contract["status"] == "blocked_missing_gate"
    assert contract["readyForExecutorReview"] is False
    assert contract["readyForRuntimeMutation"] is False
    assert contract["applyAllowedHere"] is False
    assert "benchmark_evidence_ready" in contract["blockedGateIds"]
    assert "experiment_tickets_ready" in contract["blockedGateIds"]
    assert contract["policies"]["benchmarkRequiredBeforeApply"] is True
    assert contract["policies"]["runtimeMutationAllowedHere"] is False
    assert contract["executionHandoff"]["willEnqueue"] is False
    assert contract["runtimeChangeSet"]["willWriteRuntimeConfig"] is False
    assert contract["sideEffects"]["runtimeConfigWrite"] is False
    assert contract["sideEffects"]["cacheMutation"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False


def test_optimization_application_contract_ready_for_executor_review_without_apply():
    hardware = stub_hardware_profile()
    benchmark = {
        "id": "bench-ready",
        "created_at": "2026-06-29T00:00:00+00:00",
        "benchmark": {
            "benchmarkVersion": "cognix_benchmark_v1",
            "overallScore": 70.0,
            "estimatedTokensPerSecond": 18.5,
        },
    }
    recommendation = stub_recommendation(hardware)["recommendation"]
    optimization = cognix_optimization_planner.build_optimization_plan(
        hardware = hardware,
        recommendation = recommendation,
        latest_benchmark_run = benchmark,
    )
    experiment = cognix_optimization_planner.build_optimization_experiment_plan(
        objective = "Preparer application KV-cache apres benchmark",
        hardware = hardware,
        recommendation = recommendation,
        latest_benchmark_run = benchmark,
        requested_optimizations = ["kv_cache_policy"],
    )

    contract = cognix_optimization_planner.build_optimization_application_contract(
        objective = "Preparer application KV-cache apres benchmark",
        experiment_plan = experiment,
        optimization_plan = optimization,
        confirmation_id = "conf_apply_kv_cache",
        rollback_plan_id = "rollback_kv_cache",
        request_id = "req_apply_kv_cache",
        project_id = "project-optimization",
    )

    assert contract["status"] == "ready_for_executor_review"
    assert contract["readyForExecutorReview"] is True
    assert contract["readyForRuntimeMutation"] is False
    assert contract["blockedGateIds"] == []
    assert contract["readyOptimizationIds"] == ["kv_cache_eviction"]
    assert contract["runtimeChangeSet"]["wouldApplyOptimizationIds"] == ["kv_cache_eviction"]
    assert contract["runtimeChangeSet"]["willWriteRuntimeConfig"] is False
    assert contract["executionHandoff"]["willStartWorker"] is False
    assert contract["sideEffects"]["runtimeConfigWrite"] is False
    assert contract["sideEffects"]["modelReconfiguration"] is False
    assert contract["sideEffects"]["workerStart"] is False


def test_optimization_capability_registry_endpoint_logs_audit_without_mutation(monkeypatch):
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

    body = run_async(cognix_routes.optimization_capabilities(current_subject = "alice"))

    registry = body["registry"]
    assert body["auditLogId"].startswith("aud_")
    assert registry["registryVersion"] == "cognix_optimization_capability_registry_v1"
    assert registry["benchmarkEvidence"]["status"] == "missing"
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert body["sideEffects"]["benchmarkRun"] is False
    assert body["sideEffects"]["cacheMutation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_capability_registry_built"
    assert log["metadata"]["registryVersion"] == "cognix_optimization_capability_registry_v1"
    assert log["metadata"]["benchmarkEvidenceStatus"] == "missing"
    assert log["metadata"]["sideEffects"]["runtimeConfigWrite"] is False


def test_optimization_experiment_plan_endpoint_blocks_enablement_until_benchmark(monkeypatch):
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
        cognix_routes.optimization_experiment_plan(
            cognix_routes.OptimizationExperimentPlanRequest(
                objective = "Valider semantic cache et policy KV avant activation",
                requested_optimizations = ["semantic_cache", "kv_cache_policy"],
            ),
            current_subject = "alice",
        )
    )

    plan = body["optimizationExperimentPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert plan["experimentPlanVersion"] == "cognix_optimization_experiment_plan_v1"
    assert plan["benchmarkEvidence"]["contractVersion"] == "cognix_benchmark_evidence_contract_v1"
    assert plan["selectedOptimizationIds"] == ["semantic_cache", "kv_cache_eviction"]
    assert "benchmark_baseline" in plan["summary"]["blockedGateIds"]
    assert "benchmark_evidence" in plan["summary"]["blockedGateIds"]
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert body["sideEffects"]["cacheMutation"] is False
    assert body["sideEffects"]["generation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_experiment_plan_built"
    assert log["metadata"]["experimentPlanVersion"] == "cognix_optimization_experiment_plan_v1"
    assert log["metadata"]["benchmarkEvidenceStatus"] == "missing"
    assert "benchmark_baseline" in log["metadata"]["blockedGateIds"]


def test_optimization_application_contract_endpoint_logs_executor_gate(monkeypatch):
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
        cognix_routes.optimization_application_contract(
            cognix_routes.OptimizationApplicationContractRequest(
                objective = "Preparer application semantic cache sans mutation runtime",
                requestedOptimizations = ["semantic_cache"],
                confirmationId = "conf_apply_semantic_cache",
                rollbackPlanId = "rollback_semantic_cache",
                requestId = "req_apply_semantic_cache",
            ),
            current_subject = "alice",
        )
    )

    contract = body["optimizationApplicationContract"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_optimization_application_contract_v1"
    assert contract["status"] == "blocked_missing_gate"
    assert contract["readyForRuntimeMutation"] is False
    assert "benchmark_evidence_ready" in contract["blockedGateIds"]
    assert contract["sideEffects"]["runtimeConfigWrite"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False
    assert contract["sideEffects"]["workerStart"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_application_contract_built"
    assert log["resourceType"] == "cognix_optimization_application_contract"
    assert log["metadata"]["applicationContractVersion"] == "cognix_optimization_application_contract_v1"
    assert log["metadata"]["readyForRuntimeMutation"] is False
    assert "benchmark_evidence_ready" in log["metadata"]["blockedGateIds"]
    assert log["metadata"]["sideEffects"]["runtimeConfigWrite"] is False


def test_speculative_decoding_plan_allows_llama_cpp_experiment_without_activation():
    plan = cognix_speculative_decoding.build_speculative_decoding_plan(
        username = "alice",
        objective = "Evaluer speculative decoding pour accelerer CogniX Code",
        runtime_adapter = {"selectedAdapter": {"runtimeType": "llama.cpp"}},
        target_model = {
            "modelId": "cognix-code-7b-q4",
            "parameterCountB": 7.0,
            "family": "qwen",
            "tokenizerHash": "tok-qwen",
        },
        draft_model = {
            "modelId": "cognix-code-1b-draft",
            "parameterCountB": 1.5,
            "family": "qwen",
            "tokenizerHash": "tok-qwen",
        },
        latest_benchmark_run = {
            "id": "bench-ready",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 72.0,
                "estimatedTokensPerSecond": 22.4,
            },
        },
    )

    assert plan["contractVersion"] == "cognix_speculative_decoding_contract_v1"
    assert plan["preflightVersion"] == "cognix_speculative_decoding_preflight_v1"
    assert plan["status"] == "ready_for_experiment"
    assert plan["readyForExperiment"] is True
    assert plan["readyForActivation"] is False
    assert plan["runtime"]["runtimeType"] == "llama.cpp"
    assert plan["modelPair"]["draftToTargetSizeRatio"] < 0.6
    assert plan["benchmarkEvidence"]["status"] == "ready"
    assert plan["activationContract"]["runtimeFlagWriteAllowed"] is False
    assert plan["activationContract"]["benchmarkBeforeAfterRequired"] is True
    assert plan["sideEffects"]["runtimeConfigWrite"] is False
    assert plan["sideEffects"]["draftModelLoad"] is False
    assert plan["sideEffects"]["generation"] is False


def test_speculative_decoding_plan_blocks_ollama_and_bad_draft_without_mutation():
    plan = cognix_speculative_decoding.build_speculative_decoding_plan(
        username = "alice",
        objective = "Tester speculative decoding",
        runtime_adapter = {"selectedAdapter": {"runtimeType": "ollama"}},
        target_model = {
            "modelId": "cognix-general-4b",
            "parameterCountB": 4.0,
            "family": "qwen",
        },
        draft_model = {
            "modelId": "cognix-general-4b-copy",
            "parameterCountB": 4.0,
            "family": "mistral",
        },
        latest_benchmark_run = None,
    )

    assert plan["status"] == "blocked_by_gates"
    assert plan["readyForExperiment"] is False
    assert {
        "runtime_supports_speculative_decoding",
        "draft_model_smaller",
        "tokenizer_or_family_compatible",
        "benchmark_baseline_ready",
    }.issubset(set(plan["summary"]["blockedGateIds"]))
    assert plan["activationContract"]["runtimeMutationAllowed"] is False
    assert plan["sideEffects"]["runtimeFlagWrite"] is False
    assert plan["sideEffects"]["modelLoad"] is False


def test_speculative_decoding_plan_endpoint_logs_sanitized_contract(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_db,
        "get_latest_benchmark_run",
        lambda username: {
            "id": f"bench-{username}",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 72.0,
                "estimatedTokensPerSecond": 22.4,
            },
        },
    )

    body = run_async(
        cognix_routes.speculative_decoding_plan(
            cognix_routes.SpeculativeDecodingPlanRequest(
                objective = "Evaluer speculative decoding pour reduire la latence sans degradation.",
                runtimeAdapter = {"selectedAdapter": {"runtimeType": "vllm"}},
                targetModel = {
                    "modelId": "target-secret-safe",
                    "parameterCountB": 14.0,
                    "family": "qwen",
                    "tokenizerHash": "tok-qwen",
                },
                draftModel = {
                    "modelId": "draft-safe",
                    "parameterCountB": 3.0,
                    "family": "qwen",
                    "tokenizerHash": "tok-qwen",
                },
            ),
            current_subject = "alice",
        )
    )

    plan = body["speculativeDecodingPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert plan["status"] == "ready_for_experiment"
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert body["sideEffects"]["generation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "speculative_decoding_plan_built"
    assert log["metadata"]["contractVersion"] == "cognix_speculative_decoding_contract_v1"
    assert log["metadata"]["runtimeType"] == "vllm"
    assert log["metadata"]["targetModelId"] == "target-secret-safe"
    assert log["metadata"]["draftModelId"] == "draft-safe"
    assert log["metadata"]["blockedGateIds"] == []
    assert log["metadata"]["sideEffects"]["runtimeFlagWrite"] is False
    assert "reduire la latence sans degradation" not in log["metadataJson"]


def test_kv_cache_eviction_plan_prepares_direct_runtime_policy_without_mutation():
    plan = cognix_kv_cache.build_kv_cache_eviction_plan(
        username = "alice",
        objective = "Garder le contexte utile et supprimer le bruit KV",
        runtime_adapter = {"selectedAdapter": {"runtimeType": "llama.cpp"}},
        model = {"modelId": "cognix-code-7b-q4", "contextLength": 4096},
        target_token_budget = 4096,
        latest_benchmark_run = {
            "id": "bench-ready",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 72.0,
                "estimatedTokensPerSecond": 22.4,
            },
        },
        context_blocks = [
            {"id": "sys", "type": "system", "tokenCount": 300, "content": "hidden system text"},
            {"id": "project", "type": "project_summary", "tokenCount": 800, "importance": 0.9},
            {"id": "recent", "type": "user_message", "tokenCount": 700, "importance": 0.8},
            {"id": "trace", "type": "terminal_output", "tokenCount": 2400, "importance": 0.2, "content": "secret terminal trace"},
            {"id": "rag", "type": "rag_chunk", "tokenCount": 900, "hasCitation": True},
        ],
    )

    actions = {item["blockId"]: item["action"] for item in plan["retentionPlan"]["decisions"]}
    assert plan["kvCacheEvictionPlanVersion"] == "cognix_kv_cache_eviction_plan_v1"
    assert plan["policyContractVersion"] == "cognix_kv_cache_policy_contract_v1"
    assert plan["contextRetentionPolicyVersion"] == "cognix_context_retention_policy_v1"
    assert plan["status"] == "ready_for_activation"
    assert plan["readyForPolicyReview"] is True
    assert plan["readyForActivation"] is True
    assert plan["runtime"]["directKvControlSupported"] is True
    assert plan["policyMode"] == "direct_kv_eviction_contract"
    assert actions["sys"] == "pin"
    assert actions["trace"] == "evict_from_kv"
    assert plan["retentionPlan"]["summary"]["evictCount"] >= 1
    assert plan["summary"]["estimatedTokenReduction"] > 0
    assert "secret terminal trace" not in str(plan)
    assert "hidden system text" not in str(plan)
    assert plan["policyContract"]["runtimeFlagWriteAllowed"] is False
    assert plan["policyContract"]["frontendDirectKvMutationAllowed"] is False
    assert plan["sideEffects"]["kvCacheEviction"] is False
    assert plan["sideEffects"]["runtimeFlagWrite"] is False
    assert plan["sideEffects"]["contextSummarization"] is False
    assert plan["sideEffects"]["generation"] is False


def test_kv_cache_eviction_plan_falls_back_for_ollama_and_requires_benchmark():
    plan = cognix_kv_cache.build_kv_cache_eviction_plan(
        username = "alice",
        objective = "Optimiser long chat sur Ollama",
        runtime_adapter = {"selectedAdapter": {"runtimeType": "ollama"}},
        model = {"modelId": "qwen-local", "contextLength": 2048},
        latest_benchmark_run = None,
        context_blocks = [
            {"id": "recent", "type": "user_message", "tokenCount": 500},
            {"id": "logs", "type": "debug_log", "tokenCount": 1200},
        ],
    )

    assert plan["status"] == "ready_for_policy_review"
    assert plan["readyForPolicyReview"] is True
    assert plan["readyForActivation"] is False
    assert plan["runtime"]["directKvControlSupported"] is False
    assert plan["runtime"]["fallbackToContextRetention"] is True
    assert plan["policyMode"] == "context_level_retention_contract"
    assert "benchmark_baseline_ready" in plan["summary"]["blockedGateIds"]
    assert "runtime_direct_kv_supported" in plan["summary"]["warningGateIds"]
    assert plan["benchmarkEvidence"]["status"] == "missing"
    assert plan["sideEffects"]["kvCacheRead"] is False
    assert plan["sideEffects"]["kvCacheWrite"] is False


def test_kv_cache_eviction_endpoint_logs_sanitized_contract(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_db,
        "get_latest_benchmark_run",
        lambda username: {
            "id": f"bench-{username}",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 70.0,
                "estimatedTokensPerSecond": 18.5,
            },
        },
    )

    body = run_async(
        cognix_routes.kv_cache_eviction_plan(
            cognix_routes.KvCacheEvictionPlanRequest(
                objective = "Planifier eviction KV sans exposer le contexte brut",
                runtimeAdapter = {"selectedAdapter": {"runtimeType": "vllm"}},
                model = {"modelId": "cognix-general-4b", "contextLength": 4096},
                contextBlocks = [
                    {"id": "sys", "type": "system", "tokenCount": 240, "content": "raw system secret"},
                    {"id": "old", "type": "raw_history", "tokenCount": 1800, "content": "private chat sentence"},
                    {"id": "recent", "type": "user_message", "tokenCount": 600, "importance": 0.8},
                ],
            ),
            current_subject = "alice",
        )
    )

    plan = body["kvCacheEvictionPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_kv_cache_eviction_plan_v1"
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["kvCacheEviction"] is False
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert plan["readyForPolicyReview"] is True
    assert plan["runtime"]["runtimeType"] == "vllm"
    assert "raw system secret" not in str(plan)
    assert "private chat sentence" not in str(plan)

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "kv_cache_eviction_plan_built"
    assert log["metadata"]["kvCacheEvictionPlanVersion"] == "cognix_kv_cache_eviction_plan_v1"
    assert log["metadata"]["policyContractVersion"] == "cognix_kv_cache_policy_contract_v1"
    assert log["metadata"]["runtimeType"] == "vllm"
    assert log["metadata"]["sideEffects"]["kvCacheEviction"] is False
    assert "raw system secret" not in log["metadataJson"]
    assert "private chat sentence" not in log["metadataJson"]


def test_batching_plan_prepares_vllm_throughput_experiment_without_activation():
    plan = cognix_batching.build_batching_plan(
        username = "alice",
        objective = "Preparer batching multi-utilisateur enterprise pour CogniX",
        runtime_adapter = {
            "selectedAdapter": {
                "runtimeType": "vllm",
                "deploymentTarget": "server_gpu",
            }
        },
        hardware = {
            "memory": {"totalGb": 128, "availableGb": 96},
            "gpu": {
                "available": True,
                "devices": [{"name": "A6000", "vramTotalGb": 48}],
            },
        },
        latest_benchmark_run = {
            "id": "bench-ready",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 88.0,
                "estimatedTokensPerSecond": 140.0,
            },
        },
        concurrent_users = 24,
        request_rate_per_minute = 360,
        average_prompt_tokens = 700,
        average_completion_tokens = 300,
        target_latency_ms = 1800,
    )

    assert plan["batchingPlanVersion"] == "cognix_batching_plan_v1"
    assert plan["microBatchPolicyVersion"] == "cognix_micro_batch_policy_v1"
    assert plan["throughputExperimentContractVersion"] == "cognix_throughput_experiment_contract_v1"
    assert plan["status"] == "ready_for_experiment"
    assert plan["readyForExperiment"] is True
    assert plan["readyForActivation"] is False
    assert plan["runtime"]["directBatchingSupported"] is True
    assert plan["microBatchPolicy"]["strategy"] == "continuous_batching"
    assert plan["microBatchPolicy"]["maxBatchSize"] >= 8
    assert plan["queuePlan"]["queueId"] == "enterprise_throughput"
    assert plan["queuePlan"]["jobType"] == "batching_experiment"
    assert plan["queuePlan"]["willEnqueueNow"] is False
    assert plan["experimentContract"]["automaticRuntimeEnableAllowed"] is False
    assert plan["experimentContract"]["frontendDirectBatchingAllowed"] is False
    assert plan["sideEffects"]["runtimeServerStart"] is False
    assert plan["sideEffects"]["runtimeFlagWrite"] is False
    assert plan["sideEffects"]["batchSchedulerEnable"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False
    assert plan["sideEffects"]["generation"] is False


def test_batching_plan_blocks_ollama_single_user_without_queue_mutation():
    plan = cognix_batching.build_batching_plan(
        username = "alice",
        objective = "Tester batching local single user",
        runtime_adapter = {"selectedAdapter": {"runtimeType": "ollama", "deploymentTarget": "local"}},
        hardware = stub_hardware_profile(),
        latest_benchmark_run = None,
        concurrent_users = 1,
        request_rate_per_minute = 4,
    )

    blocked = set(plan["summary"]["blockedGateIds"])
    warnings = set(plan["summary"]["warningGateIds"])
    assert plan["status"] == "blocked_by_gates"
    assert plan["readyForExperiment"] is False
    assert plan["runtime"]["unsupportedRuntime"] is True
    assert {"runtime_supports_batching", "multi_user_load_declared", "benchmark_baseline_ready"}.issubset(blocked)
    assert {"enterprise_or_server_target", "hardware_capacity_ready"}.issubset(warnings)
    assert plan["queuePlan"]["willEnqueueNow"] is False
    assert plan["sideEffects"]["runtimeServerStart"] is False
    assert plan["sideEffects"]["jobEnqueue"] is False


def test_batching_plan_endpoint_logs_sanitized_contract(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_hardware,
        "get_hardware_profile",
        lambda: {
            "memory": {"totalGb": 128, "availableGb": 96},
            "gpu": {
                "available": True,
                "devices": [{"name": "A6000", "vramTotalGb": 48}],
            },
        },
    )
    monkeypatch.setattr(
        cognix_routes.cognix_db,
        "get_latest_benchmark_run",
        lambda username: {
            "id": f"bench-{username}",
            "benchmark": {
                "benchmarkVersion": "cognix_benchmark_v1",
                "overallScore": 88.0,
                "estimatedTokensPerSecond": 140.0,
            },
        },
    )

    body = run_async(
        cognix_routes.batching_plan(
            cognix_routes.BatchingPlanRequest(
                objective = "Preparer batching secret enterprise prompt should not leak",
                runtimeAdapter = {
                    "selectedAdapter": {
                        "runtimeType": "vllm",
                        "deploymentTarget": "server_gpu",
                    }
                },
                concurrentUsers = 18,
                requestRatePerMinute = 240,
                averagePromptTokens = 600,
                averageCompletionTokens = 220,
                targetLatencyMs = 2000,
            ),
            current_subject = "alice",
        )
    )

    plan = body["batchingPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_batching_plan_v1"
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["batchSchedulerEnable"] is False
    assert plan["status"] == "ready_for_experiment"
    assert plan["queuePlan"]["queueId"] == "enterprise_throughput"

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "batching_plan_built"
    assert log["metadata"]["batchingPlanVersion"] == "cognix_batching_plan_v1"
    assert log["metadata"]["microBatchPolicyVersion"] == "cognix_micro_batch_policy_v1"
    assert log["metadata"]["recommendedQueueId"] == "enterprise_throughput"
    assert log["metadata"]["sideEffects"]["batchSchedulerEnable"] is False
    assert "secret enterprise prompt" not in log["metadataJson"]


def test_performance_monitor_collects_snapshot_without_execution_side_effects():
    metrics = cognix_performance_monitor.collect_runtime_metrics(
        username = "alice",
        hardware = stub_gpu_hardware_profile(),
        runtime_snapshot = {
            "runtimeType": "ollama",
            "activeModel": "qwen-4b",
            "loadedModels": ["qwen-4b"],
            "loadingModels": [],
        },
        inference_stats = {
            "tokensPerSecond": 23.5,
            "latencyMs": 180,
            "loadTimeMs": 1200,
            "estimatedCostUsd": 0,
        },
        latest_benchmark_run = {"id": "bench-1", "benchmark": {"estimatedTokensPerSecond": 19.0}},
        project_id = "project-code",
    )

    assert metrics["performanceMonitorVersion"] == "cognix_performance_monitor_v1"
    assert metrics["runtimeMetricsCollectorVersion"] == "cognix_runtime_metrics_collector_v1"
    assert metrics["metricsStreamerVersion"] == "cognix_metrics_streamer_v1"
    assert metrics["hardware"]["ram"]["totalGb"] == 32.0
    assert metrics["hardware"]["gpu"]["available"] is True
    assert metrics["inference"]["tokensPerSecond"] == 23.5
    assert metrics["streamPlan"]["willOpenStreamNow"] is False
    assert metrics["sideEffects"]["generation"] is False
    assert metrics["sideEffects"]["benchmarkRun"] is False
    assert metrics["sideEffects"]["gpuStressTest"] is False


def test_performance_snapshot_endpoint_stores_metrics_and_logs_audit(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(cognix_routes.cognix_hardware, "get_hardware_profile", stub_gpu_hardware_profile)
    monkeypatch.setattr(
        cognix_routes,
        "_current_model_cache_runtime",
        lambda: {
            "runtimeType": "ollama",
            "activeModel": "qwen-4b",
            "loadedModels": ["qwen-4b"],
            "loadingModels": [],
        },
    )
    cognix_db.create_benchmark_run(
        "alice",
        {
            "mode": "quick",
            "overallScore": 71.0,
            "estimatedTokensPerSecond": 19.0,
            "hardware": stub_gpu_hardware_profile(),
        },
    )

    body = run_async(
        cognix_routes.performance_snapshot(
            cognix_routes.PerformanceSnapshotRequest(
                modelId = "qwen-4b",
                inferenceStats = {
                    "tokensPerSecond": 24.0,
                    "latencyMs": 165,
                    "loadTimeMs": 900,
                    "estimatedCostUsd": 0,
                },
                storeMetric = True,
            ),
            current_subject = "alice",
        )
    )

    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_performance_monitor_v1"
    assert body["storedMetric"]["modelId"] == "qwen-4b"
    assert body["storedMetric"]["tokensPerSecond"] == 24.0
    assert body["sideEffects"]["metricsWrite"] is True
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["benchmarkRun"] is False

    metrics = run_async(cognix_routes.performance_metrics(current_subject = "alice"))
    logs = run_async(cognix_routes.performance_logs(current_subject = "alice"))
    assert metrics["metrics"][0]["id"] == body["storedMetric"]["id"]
    assert logs["logs"][0]["eventType"] == "runtime_metric_snapshot"

    stream = run_async(cognix_routes.performance_stream_plan(developer_mode = True, current_subject = "alice"))
    assert stream["metricsStreamPlan"]["displayMode"] == "developer_overlay"
    assert stream["metricsStreamPlan"]["willOpenStreamNow"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "performance_snapshot_collected"
    assert log["metadata"]["sideEffects"]["metricsWrite"] is True
    assert log["metadata"]["sideEffects"]["gpuStressTest"] is False


def test_decision_explainer_builds_reason_codes_without_generation():
    explanation = cognix_decision_explainer.build_decision_explanation(
        decision = {
            "selectedDomain": "rag",
            "recommendedPath": "rag_first",
            "providerType": "ollama",
            "modelId": "qwen-4b",
            "status": "ready",
            "confidence": 0.84,
            "sideEffects": {
                "modelLoad": False,
                "generation": False,
                "networkModelCall": False,
                "toolExecution": False,
            },
            "knowledgeStrategyContract": {
                "contractVersion": "cognix_knowledge_strategy_contract_v1",
                "selectedStrategy": "rag_first",
                "ragBeforeFineTuning": True,
                "fineTuningDeferred": True,
                "explanation": "RAG est prioritaire pour repondre depuis un PDF.",
            },
        },
        source_type = "orchestrator_log",
        source_id = "orl-test",
        question = "Pourquoi RAG plutot que fine-tuning ?",
        objective_excerpt = "Repondre a partir de ce PDF.",
    )

    assert explanation["explanationGeneratorVersion"] == "cognix_explanation_generator_v1"
    assert explanation["routerDecisionExplainerVersion"] == "cognix_router_decision_explainer_v1"
    assert explanation["trace"]["recommendedPath"] == "rag_first"
    assert any(reason["code"] == "strategy_rag_first" for reason in explanation["reasonCodes"])
    assert any(reason["code"] == "knowledge_strategy_contract" for reason in explanation["reasonCodes"])
    assert explanation["display"]["rawReasoningVisible"] is False
    assert explanation["sideEffects"]["generation"] is False
    assert explanation["sideEffects"]["rawReasoningExposure"] is False


def test_decision_explanation_endpoint_stores_reasons_and_audit(monkeypatch):
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
    plan = run_async(
        cognix_routes.orchestrator_plan(
            cognix_routes.OrchestratorPlanRequest(
                objective = "Reponds a partir de ce PDF de cours avec sources",
                project_type = "research",
            ),
            current_subject = "alice",
        )
    )

    body = run_async(
        cognix_routes.explain_decision(
            cognix_routes.DecisionExplainRequest(
                sourceType = "orchestrator_log",
                sourceId = plan["orchestratorLogId"],
                question = "Pourquoi RAG plutot que fine-tuning ?",
                storeDecision = True,
            ),
            current_subject = "alice",
        )
    )

    explanation = body["decisionExplanation"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_explanation_generator_v1"
    assert explanation["trace"]["recommendedPath"] == "rag_first"
    assert explanation["display"]["rawReasoningVisible"] is False
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["decisionWrite"] is True
    assert body["sideEffects"]["reasonWrite"] is True
    assert body["storedDecision"]["id"].startswith("sdec_")
    assert any(reason["reasonCode"] == "strategy_rag_first" for reason in body["storedDecision"]["reasons"])

    listed = run_async(cognix_routes.list_decisions(current_subject = "alice"))
    read_back = run_async(
        cognix_routes.get_decision(body["storedDecision"]["id"], current_subject = "alice")
    )
    assert listed["count"] == 1
    assert listed["decisions"][0]["id"] == body["storedDecision"]["id"]
    assert read_back["decision"]["explanation"]["summary"] == explanation["summary"]
    assert read_back["decision"]["reasons"][0]["reasonCode"]

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "decision_explanation_built"
    assert log["metadata"]["sourceType"] == "orchestrator_log"
    assert log["metadata"]["sideEffects"]["rawReasoningExposure"] is False


def test_adaptive_quantization_recommends_memory_safe_variant_without_model_mutation():
    registry = cognix_quantization_advisor.build_model_variant_registry(
        hardware = {
            "deviceBackend": "cpu",
            "memory": {"totalGb": 8.0, "availableGb": 4.2},
            "gpu": {"available": False, "devices": []},
        },
        model_metadata = {
            "modelId": "qwen-4b-local",
            "modelLabel": "Qwen 4B local",
            "providerType": "ollama",
            "estimatedRamGb": 4.6,
        },
        priority = "memory",
    )

    assert registry["registryVersion"] == "cognix_model_variant_registry_v1"
    assert registry["mode"] == "dry_run"
    assert registry["badge"]["label"] == "Recommande pour ton PC"
    assert registry["recommendedVariant"]["quantization"] in {"IQ2", "Q4"}
    assert registry["recommendedVariant"]["fit"]["status"] != "blocked"
    assert registry["policies"]["frontendDirectModelSelectionMutationAllowed"] is False
    assert registry["sideEffects"]["modelLoad"] is False
    assert registry["sideEffects"]["modelConversion"] is False
    assert registry["sideEffects"]["runtimeConfigWrite"] is False


def test_adaptive_quantization_plan_prefers_quality_on_powerful_gpu_without_apply():
    plan = cognix_quantization_advisor.build_adaptive_quantization_plan(
        hardware = stub_gpu_hardware_profile(),
        model_metadata = {
            "modelId": "qwen-4b-local",
            "modelLabel": "Qwen 4B local",
            "providerType": "ollama",
            "estimatedRamGb": 4.6,
        },
        priority = "quality",
        latest_benchmark_run = {"id": "bench-ok", "benchmark": {"benchmarkVersion": "cognix_benchmark_v1"}},
    )

    assert plan["advisorVersion"] == "cognix_quantization_advisor_v1"
    assert plan["performancePredictorVersion"] == "cognix_performance_predictor_v1"
    assert plan["selectedVariant"]["quantization"] in {"Q8", "FP16"}
    assert plan["applyPlan"]["willApplyAutomatically"] is False
    assert plan["applyPlan"]["writesModelFiles"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["modelFileWrite"] is False
    assert plan["sideEffects"]["generation"] is False


def test_adaptive_quantization_endpoint_stores_profile_and_logs_audit(monkeypatch):
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
        cognix_routes.adaptive_quantization_plan(
            cognix_routes.QuantizationPlanRequest(
                priority = "balanced",
                model_id = "huihui_ai/qwen3-vl-abliterated:4b-instruct",
                store_profile = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["quantizationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["profile"]["id"].startswith("qprof_")
    assert plan["badge"]["label"] == "Recommande pour ton PC"
    assert plan["selectedVariant"]["quantization"] in {"Q4", "Q5"}
    assert body["sideEffects"]["modelLoad"] is False
    assert body["sideEffects"]["modelConversion"] is False
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert body["sideEffects"]["profileWrite"] is True

    profiles = run_async(cognix_routes.quantization_profiles(current_subject = "alice"))
    assert profiles["profiles"][0]["id"] == body["profile"]["id"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "adaptive_quantization_plan_built"
    assert log["metadata"]["selectedQuantization"] == plan["selectedVariant"]["quantization"]
    assert log["metadata"]["sideEffects"]["modelLoad"] is False


def test_cost_optimizer_blocks_generic_cloud_for_sensitive_data_without_provider_calls():
    plan = cognix_cost_optimizer.build_cost_optimization_plan(
        objective = "Analyser une base de donnees client avec token prive et logs production.",
        hardware = stub_hardware_profile(),
        project_type = "business",
        priority = "privacy",
        sensitivity_level = "confidential",
        expected_input_tokens = 8000,
        expected_output_tokens = 4000,
    )
    candidates = {item["providerId"]: item for item in plan["candidates"]}

    assert plan["optimizerVersion"] == "cognix_cost_optimizer_v1"
    assert plan["pricingStoreVersion"] == "cognix_provider_pricing_store_v1"
    assert plan["executionPlannerVersion"] == "cognix_execution_planner_v1"
    assert plan["privacyPolicyVersion"] == "cognix_privacy_policy_v1"
    assert plan["policy"]["cloudBlockedBecauseSensitive"] is True
    assert candidates["cloud-fast-api"]["status"] == "blocked"
    assert "sensitive_cloud_requires_explicit_validation" in candidates["cloud-fast-api"]["blockedReasons"]
    assert plan["decision"]["selectedExecutionTarget"] in {"enterprise_server", "local", "personal_server"}
    assert plan["sideEffects"]["providerCall"] is False
    assert plan["sideEffects"]["billingMutation"] is False
    assert plan["sideEffects"]["generation"] is False


def test_cost_optimizer_prefers_cloud_for_speed_when_data_is_not_sensitive_without_execution():
    plan = cognix_cost_optimizer.build_cost_optimization_plan(
        objective = "Repondre vite a une question publique de demonstration.",
        hardware = stub_hardware_profile(),
        project_type = "demo",
        priority = "speed",
        sensitivity_level = "public",
        expected_input_tokens = 8000,
        expected_output_tokens = 4000,
        message_count = 3,
    )

    assert plan["decision"]["selectedProviderId"] == "cloud-fast-api"
    assert plan["decision"]["selectedExecutionTarget"] == "cloud_api"
    assert plan["decision"]["estimatedCostUsd"] == 0.02
    assert plan["policy"]["cloudBlockedBecauseSensitive"] is False
    assert any(item["providerId"] == "cloud-fast-api" and item["status"] == "candidate" for item in plan["displayOptions"])
    assert plan["sideEffects"]["networkCall"] is False
    assert plan["sideEffects"]["providerCall"] is False
    assert plan["sideEffects"]["runtimeConfigWrite"] is False


def test_execution_budget_guard_blocks_cloud_without_quota_and_falls_back_without_provider_call():
    plan = cognix_cost_optimizer.build_cost_optimization_plan(
        objective = "Repondre vite a une question publique de demonstration.",
        hardware = stub_hardware_profile(),
        project_type = "demo",
        priority = "speed",
        sensitivity_level = "public",
        expected_input_tokens = 8000,
        expected_output_tokens = 4000,
        message_count = 3,
    )
    quota_matrix = cognix_admin_limits.build_quota_matrix(
        users = [{"username": "alice", "role": "user"}],
        user_quotas = [],
        role_quotas = [],
        quota_overrides = [],
        quota_usage = [],
        legacy_limits = [],
    )
    guard = cognix_cost_optimizer.build_execution_budget_guard(
        username = "alice",
        cost_plan = plan,
        quota_matrix = quota_matrix,
    )

    assert plan["decision"]["selectedProviderId"] == "cloud-fast-api"
    assert guard["budgetGuardVersion"] == "cognix_execution_budget_guard_v1"
    assert guard["mode"] == "quota_guard_dry_run"
    assert guard["allowedToExecute"] is True
    assert guard["cloudQuota"]["allowed"] is False
    assert guard["guardedDecision"]["selectedProviderId"] != "cloud-fast-api"
    assert guard["guardedDecision"]["selectedExecutionTarget"] != "cloud_api"
    assert guard["guardedDecision"]["selectedExecutionTargetChanged"] is True
    cloud_candidate = next(item for item in guard["guardedCandidates"] if item["providerId"] == "cloud-fast-api")
    assert "cloud_model_access_quota_blocked" in cloud_candidate["blockedReasons"]
    assert guard["policy"]["providerCallAllowedHere"] is False
    assert guard["sideEffects"]["quotaUsageWrite"] is False
    assert guard["sideEffects"]["providerCall"] is False
    assert guard["sideEffects"]["billingMutation"] is False


def test_execution_budget_guard_blocks_all_targets_when_daily_token_quota_is_exceeded():
    plan = cognix_cost_optimizer.build_cost_optimization_plan(
        objective = "Analyser un gros dossier de recherche.",
        hardware = stub_hardware_profile(),
        project_type = "research",
        priority = "balanced",
        sensitivity_level = "public",
        expected_input_tokens = 100,
        expected_output_tokens = 40,
    )
    quota_matrix = cognix_admin_limits.build_quota_matrix(
        users = [{"username": "alice", "role": "user"}],
        user_quotas = [
            {
                "username": "alice",
                "quota_key": "tokens_daily",
                "quota_value": 100,
                "unit": "tokens",
                "period": "day",
                "status": "active",
            }
        ],
        role_quotas = [],
        quota_overrides = [],
        quota_usage = [{"username": "alice", "quota_key": "tokens_daily", "used_value": 80}],
        legacy_limits = [],
    )

    guard = cognix_cost_optimizer.build_execution_budget_guard(
        username = "alice",
        cost_plan = plan,
        quota_matrix = quota_matrix,
    )

    assert guard["allowedToExecute"] is False
    assert guard["status"] == "blocked_by_quota"
    assert guard["tokenQuota"]["remainingBefore"] == 20
    assert guard["tokenQuota"]["remainingAfter"] == -120
    assert "tokens_daily_quota_exceeded" in guard["blockingReasons"]
    assert all("tokens_daily_quota_exceeded" in item["blockedReasons"] for item in guard["guardedCandidates"])
    assert guard["sideEffects"]["generation"] is False
    assert guard["sideEffects"]["quotaUsageWrite"] is False


def test_cost_optimization_endpoint_stores_execution_cost_log_and_logs_audit(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )

    body = run_async(
        cognix_routes.cost_optimization_plan(
            cognix_routes.CostOptimizationPlanRequest(
                objective = "Comparer local, cloud et serveur entreprise pour une base client confidentielle.",
                project_type = "business",
                priority = "privacy",
                sensitivity_level = "confidential",
                expected_input_tokens = 8000,
                expected_output_tokens = 4000,
                store_log = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["costOptimizationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["costLog"]["id"].startswith("cost_")
    assert body["costLog"]["selectedExecutionTarget"] == plan["decision"]["selectedExecutionTarget"]
    assert plan["services"] == ["CostOptimizer", "ProviderPricingStore", "ExecutionPlanner"]
    assert plan["policy"]["cloudBlockedBecauseSensitive"] is True
    assert body["sideEffects"]["providerCall"] is False
    assert body["sideEffects"]["billingMutation"] is False
    assert body["sideEffects"]["executionCostLogWrite"] is True

    logs = run_async(cognix_routes.execution_cost_logs(current_subject = "alice"))
    assert logs["logs"][0]["id"] == body["costLog"]["id"]
    assert logs["logs"][0]["decision"]["decision"]["selectedProviderId"] == plan["decision"]["selectedProviderId"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "cost_optimization_plan_built"
    assert log["metadata"]["selectedProviderId"] == plan["decision"]["selectedProviderId"]
    assert log["metadata"]["sideEffects"]["providerCall"] is False


def test_cost_optimization_endpoint_applies_native_quota_guard_before_cloud_execution(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(
        cognix_routes.cognix_hardware,
        "get_hardware_profile",
        stub_hardware_profile,
    )

    body = run_async(
        cognix_routes.cost_optimization_plan(
            cognix_routes.CostOptimizationPlanRequest(
                objective = "Repondre vite a une question publique de demonstration.",
                project_type = "demo",
                priority = "speed",
                sensitivity_level = "public",
                expected_input_tokens = 8000,
                expected_output_tokens = 4000,
                store_log = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["costOptimizationPlan"]
    assert plan["decision"]["selectedProviderId"] == "cloud-fast-api"
    assert plan["budgetGuard"]["cloudQuota"]["allowed"] is False
    assert plan["budgetGuard"]["guardedDecision"]["selectedExecutionTarget"] != "cloud_api"
    assert plan["guardedDecision"] == plan["budgetGuard"]["guardedDecision"]
    assert body["costLog"]["decision"]["budgetGuard"]["budgetGuardVersion"] == "cognix_execution_budget_guard_v1"
    assert body["sideEffects"]["quotaUsageWrite"] is False
    assert body["sideEffects"]["providerCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["metadata"]["budgetGuardStatus"] == "allowed"
    assert log["metadata"]["guardedSelectedExecutionTarget"] != "cloud_api"


def test_runtime_adapter_registry_and_plan_select_ollama_without_side_effects():
    registry = cognix_runtime_adapter.build_runtime_adapter_registry()

    assert registry["runtimeAdapterVersion"] == "cognix_runtime_adapter_v1"
    assert registry["summary"]["directFrontendModelCallAllowed"] is False
    assert registry["globalPolicies"]["frontendMustUseBackend"] is True
    assert registry["globalPolicies"]["optimizationCompatibilityContractRequired"] is True
    assert registry["globalPolicies"]["optimizationContractVersion"] == "cognix_runtime_optimization_contract_v1"
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
    assert plan["optimizationContract"]["contractVersion"] == "cognix_runtime_optimization_contract_v1"
    assert plan["optimizationContract"]["blockedOptimizationIds"] == ["prompt_cache"]
    assert plan["optimizationContract"]["activationContract"]["runtimeMutationAllowed"] is False
    assert plan["optimizationContract"]["sideEffects"]["runtimeFlagWrite"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["serverStart"] is False
    assert plan["sideEffects"]["networkModelCall"] is False


def test_runtime_adapter_optimization_contract_allows_llama_cpp_after_benchmark_only():
    plan = cognix_runtime_adapter.build_runtime_adapter_plan(
        recommendation = {"providerType": "llama.cpp"},
        hardware = stub_hardware_profile(),
        task_strategy = {"path": "expert_chat"},
        rag_plan = {"readyForRetrieval": False},
        fine_tuning_plan = {"recommendedPath": "no_fine_tuning_needed"},
        optimization_plan = {"recommendedOptimizationIds": ["prompt_cache", "kv_cache_policy", "speculative_decoding"]},
    )

    contract = plan["optimizationContract"]
    assert plan["selectedAdapter"]["adapterId"] == "llama-cpp"
    assert contract["contractVersion"] == "cognix_runtime_optimization_contract_v1"
    assert contract["compatibleOptimizationIds"] == ["prompt_cache", "kv_cache_policy", "speculative_decoding"]
    assert contract["blockedOptimizationIds"] == []
    assert contract["activationContract"]["benchmarkRequiredBeforeActivation"] is True
    assert contract["activationContract"]["runtimeFlagWriteAllowed"] is False
    assert all(item["status"] == "compatible_requires_benchmark" for item in contract["checks"])
    assert contract["sideEffects"]["runtimeMutation"] is False
    assert contract["sideEffects"]["benchmarkRun"] is False


def test_runtime_adapter_registry_declares_tensorrt_llm_without_side_effects():
    registry = cognix_runtime_adapter.build_runtime_adapter_registry()
    adapters = {item["id"]: item for item in registry["adapters"]}

    tensorrt = adapters["tensorrt-llm"]
    assert tensorrt["label"] == "TensorRT-LLM"
    assert tensorrt["deploymentTarget"] == "server_gpu"
    assert "nvidia_gpu" in tensorrt["requires"]
    assert "engine_build" in tensorrt["requires"]
    assert tensorrt["supports"]["toolCalling"] is True
    assert tensorrt["supports"]["speculativeDecoding"] is True
    assert tensorrt["supports"]["multiUserBatching"] is True
    assert registry["globalPolicies"]["fallbackChainContractRequired"] is True
    assert registry["globalPolicies"]["fallbackContractVersion"] == "cognix_runtime_fallback_contract_v1"
    assert registry["sideEffects"]["networkModelCall"] is False
    assert registry["sideEffects"]["runtimeMutation"] is False


def test_runtime_fallback_plan_builds_ordered_chain_without_runtime_mutation():
    adapter_plan = cognix_runtime_adapter.build_runtime_adapter_plan(
        recommendation = {"providerType": "tensorrt-llm"},
        hardware = stub_hardware_profile(),
        task_strategy = {"path": "tool_plan"},
        rag_plan = {"readyForRetrieval": True},
        fine_tuning_plan = {"recommendedPath": "no_fine_tuning_needed"},
        optimization_plan = {"recommendedOptimizationIds": ["batching", "speculative_decoding"]},
    )

    fallback = cognix_runtime_adapter.build_runtime_fallback_plan(
        runtime_adapter_plan = adapter_plan,
        hardware = stub_hardware_profile(),
        required_capabilities = ["streaming", "toolCalling", "ragContextInjection", "multiUserBatching"],
        requested_optimization_ids = ["batching", "speculative_decoding"],
        allow_cloud_fallback = False,
        data_sensitivity = "confidential",
    )

    chain = fallback["fallbackChain"]
    assert fallback["contractVersion"] == "cognix_runtime_fallback_contract_v1"
    assert fallback["status"] == "ready_for_review"
    assert fallback["primaryAdapterId"] == "tensorrt-llm"
    assert chain[0]["adapterId"] == "tensorrt-llm"
    assert chain[0]["activationAllowedHere"] is False
    assert chain[0]["hardwareCompatible"] is False
    assert any(item["adapterId"] == "vllm" for item in chain)
    assert any(item["adapterId"] == "cloud-openai-compatible" for item in chain)
    assert any(item["adapterId"] == "llama-cpp" for item in chain)
    cloud = next(item for item in chain if item["adapterId"] == "cloud-openai-compatible")
    assert cloud["status"].startswith("blocked_")
    assert cloud["cloudFallbackAllowed"] is False
    assert fallback["policies"]["automaticFailoverAllowed"] is False
    assert fallback["policies"]["tensorrtEngineBuildAllowedHere"] is False
    assert fallback["sideEffects"]["modelLoad"] is False
    assert fallback["sideEffects"]["serverStart"] is False
    assert fallback["sideEffects"]["networkModelCall"] is False
    assert fallback["sideEffects"]["runtimeMutation"] is False
    assert fallback["sideEffects"]["engineBuild"] is False


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
    assert adapter_plan["optimizationContract"]["contractVersion"] == "cognix_runtime_optimization_contract_v1"
    assert adapter_plan["sideEffects"]["runtimeMutation"] is False
    assert adapter_plan["sideEffects"]["serverStart"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "runtime_adapter_plan_built"
    assert log["metadata"]["runtimeAdapterVersion"] == "cognix_runtime_adapter_v1"
    assert log["metadata"]["optimizationContractVersion"] == "cognix_runtime_optimization_contract_v1"
    assert log["metadata"]["sideEffects"]["runtimeMutation"] is False


def test_runtime_fallback_plan_endpoint_logs_sanitized_dry_run(monkeypatch):
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
        cognix_routes.runtime_fallback_plan(
            cognix_routes.RuntimeFallbackPlanRequest(
                objective = "Planifier un fallback runtime confidentiel sans fuite dans l'audit",
                project_type = "enterprise",
                required_capabilities = ["streaming", "ragContextInjection", "multiUserBatching"],
                requested_optimization_ids = ["batching"],
                allow_cloud_fallback = False,
                data_sensitivity = "confidential",
            ),
            current_subject = "alice",
        )
    )

    fallback = body["runtimeFallbackPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_runtime_fallback_contract_v1"
    assert fallback["contractVersion"] == "cognix_runtime_fallback_contract_v1"
    assert fallback["policies"]["frontendDirectCallAllowed"] is False
    assert fallback["sideEffects"]["runtimeMutation"] is False
    assert fallback["sideEffects"]["networkModelCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "runtime_fallback_plan_built"
    assert log["resourceType"] == "cognix_runtime_fallback_plan"
    assert log["metadata"]["runtimeFallbackContractVersion"] == "cognix_runtime_fallback_contract_v1"
    assert log["metadata"]["sideEffects"]["serverStart"] is False
    metadata_json = str(log["metadata"])
    assert "Planifier un fallback runtime confidentiel" not in metadata_json


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


def test_gpu_scheduler_contract_admits_enterprise_workloads_without_enqueueing():
    hardware = stub_gpu_hardware_profile()
    deployment = cognix_deployment_manager.build_deployment_plan(
        username = "alice",
        objective = "Planifier un scheduler GPU enterprise",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        target_type = "on_premise",
        edition = "enterprise",
        expected_users = 40,
        data_sensitivity = "confidential",
        requested_features = ["autoscaling"],
        latest_benchmark_run = {"id": "bench-1"},
    )
    contract = cognix_deployment_manager.build_gpu_scheduler_contract(
        username = "alice",
        hardware = hardware,
        deployment_plan = deployment,
        gpu_nodes = [
            {"nodeId": "gpu-a", "name": "A6000", "backend": "vllm", "vramTotalGb": 48, "vramReservedGb": 8},
            {"nodeId": "gpu-b", "name": "A6000", "backend": "vllm", "vramTotalGb": 48, "vramReservedGb": 4},
        ],
        workloads = [
            {"workloadType": "chat", "count": 4, "requiredVramGb": 10},
            {"workloadType": "batch", "count": 2, "requiredVramGb": 16},
        ],
        expected_users = 40,
        tenant_policy = {"isolationMode": "tenant_queues", "maxConcurrentPerTenant": 3},
    )

    assert contract["schedulerContractVersion"] == "cognix_gpu_scheduler_contract_v1"
    assert contract["status"] == "ready_for_admin_review"
    assert contract["readyForAdminReview"] is True
    assert contract["readyForSchedulerActivation"] is False
    assert contract["gpuPool"]["availableNodeCount"] == 2
    assert contract["admissionPlan"]["totalRequested"] == 6
    assert contract["admissionPlan"]["totalAdmitted"] >= 2
    assert contract["queuePlan"]["workerStartAllowed"] is False
    assert contract["tenantIsolation"]["crossTenantMemorySharingAllowed"] is False
    assert contract["tenantIsolation"]["perTenantAuditRequired"] is True
    assert any(item["id"] == "job_enqueue" for item in contract["blockedActions"])
    assert contract["sideEffects"]["schedulerActivation"] is False
    assert contract["sideEffects"]["gpuReservation"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False
    assert contract["sideEffects"]["workerStart"] is False


def test_gpu_scheduler_contract_blocks_without_gpu_capacity():
    contract = cognix_deployment_manager.build_gpu_scheduler_contract(
        username = "alice",
        hardware = stub_hardware_profile(),
        deployment_plan = {},
        gpu_nodes = [],
        workloads = [{"workloadType": "fine_tuning", "count": 1, "requiredVramGb": 24}],
        expected_users = 5,
    )

    assert contract["status"] == "blocked_capacity"
    assert "gpu_nodes_available" in contract["summary"]["blockedGateIds"]
    assert "capacity_for_workloads" in contract["summary"]["blockedGateIds"]
    assert contract["readyForSchedulerActivation"] is False
    assert contract["admissionPlan"]["willEnqueueNow"] is False
    assert contract["sideEffects"]["serverStart"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False


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


def test_gpu_scheduler_contract_endpoint_logs_audited_dry_run(monkeypatch):
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
        cognix_routes.gpu_scheduler_contract(
            cognix_routes.GpuSchedulerContractRequest(
                objective = "Planifie un scheduler GPU Business pour plusieurs utilisateurs",
                targetType = "on_premise",
                edition = "business",
                expectedUsers = 16,
                dataSensitivity = "confidential",
                gpuNodes = [
                    {"nodeId": "gpu-a", "name": "RTX 4090", "backend": "vllm", "vramTotalGb": 24, "vramReservedGb": 4},
                ],
                workloads = [
                    {"workloadType": "chat", "count": 2, "requiredVramGb": 8},
                    {"workloadType": "rag", "count": 1, "requiredVramGb": 4},
                ],
                tenantPolicy = {"isolationMode": "tenant_queues"},
            ),
            current_subject = "alice",
        )
    )

    contract = body["gpuSchedulerContract"]
    assert body["auditLogId"].startswith("aud_")
    assert contract["schedulerContractVersion"] == "cognix_gpu_scheduler_contract_v1"
    assert contract["mode"] == "gpu_scheduler_contract_dry_run"
    assert contract["readyForSchedulerActivation"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False
    assert contract["sideEffects"]["workerStart"] is False
    assert contract["sideEffects"]["gpuReservation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "gpu_scheduler_contract_built"
    assert log["metadata"]["schedulerContractVersion"] == "cognix_gpu_scheduler_contract_v1"
    assert log["metadata"]["sideEffects"]["jobEnqueue"] is False
    assert log["metadata"]["sideEffects"]["workerStart"] is False


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
    assert plan["executionContract"]["projectSessionContractVersion"] == "cognix_project_session_contract_v1"
    session = plan["projectSessionContract"]
    assert session["contractVersion"] == "cognix_project_session_contract_v1"
    assert session["sessionMode"] == "direct_project_expert"
    assert session["routingPolicy"]["directPrimaryExpertPreferred"] is True
    assert session["routingPolicy"]["frontendDirectModelCallAllowed"] is False
    assert session["routingPolicy"]["automaticModelLoadAllowed"] is False
    assert session["contextBoundary"]["projectMemoryRequired"] is True
    assert session["contextBoundary"]["rawHistoryAllowed"] is False
    assert session["preloadBoundary"]["willLoadNow"] is False
    assert "model_load" in session["blockedActions"]
    assert plan["executionContract"]["willLoadModel"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["defaultModelWrite"] is False
    assert plan["sideEffects"]["projectMutation"] is False


def test_project_dna_builds_profile_and_context_injection_plan():
    plan = cognix_project_dna.build_project_dna_plan(
        username = "alice",
        project_id = "project-code",
        project = {"name": "Backend API", "instructions": "Priorite securite."},
        objective = "Construire CogniX V1 beta",
        response_style = "Repondre en francais, clair et direct.",
        preferred_models = [{"modelId": "qwen-4b", "label": "Qwen 4B"}],
        allowed_tools = ["github", "terminal"],
        constraints = ["Changements natifs uniquement", "Ne pas lancer le modele sans demande"],
        decisions = [{"title": "Utiliser Ollama pour les tests locaux", "rationale": "Rapide et reproductible"}],
    )

    assert plan["projectDnaServiceVersion"] == "cognix_project_dna_service_v1"
    assert plan["profileBuilderVersion"] == "cognix_project_profile_builder_v1"
    assert plan["contextInjectorVersion"] == "cognix_context_injector_v1"
    assert plan["status"] == "ready_for_context"
    assert plan["profile"]["completion"]["readySectionCount"] >= 6
    assert plan["contextInjectionPlan"]["channelId"] == "project_dna"
    assert plan["contextInjectionPlan"]["contextManagerCompatible"] is True
    assert plan["contextInjectionPlan"]["willInjectNow"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["contextMutation"] is False


def test_project_dna_endpoint_stores_and_context_pack_includes_dna():
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

    body = run_async(
        cognix_routes.upsert_project_dna(
            "project-code",
            cognix_routes.ProjectDNARequest(
                objective = "Construire CogniX comme interface ChatGPT locale",
                responseStyle = "Francais, direct, sans surcouche.",
                preferredModels = [{"modelId": "qwen-4b", "label": "Qwen 4B"}],
                allowedTools = ["github", "terminal"],
                constraints = ["Tous les changements doivent etre natifs"],
                decisions = [{"title": "Garder cognix.local en HTTPS"}],
                storeDna = True,
            ),
            current_subject = "alice",
        )
    )

    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_project_dna_service_v1"
    assert body["projectDna"]["projectId"] == "project-code"
    assert body["projectDna"]["dna"]["contextInjectionPlan"]["channelId"] == "project_dna"
    assert body["sideEffects"]["projectDnaWrite"] is True
    assert body["sideEffects"]["modelLoad"] is False

    packet = run_async(
        cognix_routes.build_context_pack(
            cognix_routes.ContextPackRequest(
                objective = "Continue la mission",
                projectId = "project-code",
            ),
            current_subject = "alice",
        )
    )
    assert "project_dna" in packet["includedSectionIds"]
    assert "project_dna" in packet["contextPlan"]["includedChannelIds"]
    assert "Construire CogniX" in packet["systemInstruction"]
    assert packet["sideEffects"]["networkModelCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][1]
    assert log["action"] == "project_dna_upserted"
    assert log["metadata"]["sideEffects"]["projectDnaWrite"] is True


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
    assert expert_plan["projectSessionContract"]["contractVersion"] == "cognix_project_session_contract_v1"
    assert expert_plan["projectSessionContract"]["sessionMode"] == "direct_project_expert"
    assert expert_plan["projectSessionContract"]["routingPolicy"]["frontendDirectModelCallAllowed"] is False
    assert expert_plan["projectSessionContract"]["routingPolicy"]["automaticModelLoadAllowed"] is False
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
    assert log["metadata"]["projectSessionContractVersion"] == "cognix_project_session_contract_v1"
    assert log["metadata"]["projectSessionMode"] == "direct_project_expert"
    assert log["metadata"]["projectSessionWillLoadModel"] is False
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


def test_model_install_contract_prepares_huggingface_download_without_network_or_files():
    hardware = stub_hardware_profile()
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = None,
        loaded_models = [],
        loading_models = [],
        runtime_type = "transformers",
    )
    lifecycle = cognix_model_lifecycle.build_model_lifecycle_plan(
        objective = "Prepare Hugging Face model install",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        cache = cache,
        classification = {"selectedDomain": "general", "scores": {"general": 0.91}},
        model_registry = {"models": []},
        requested_model_id = "Qwen/Qwen2.5-3B-Instruct",
        project_type = "research",
    )

    contract = cognix_model_lifecycle.build_model_install_contract(
        objective = "Prepare Hugging Face model install",
        lifecycle_plan = lifecycle,
        external_model = {
            "modelId": "Qwen/Qwen2.5-3B-Instruct",
            "providerType": "hf_transformers",
            "source": "huggingface_hub",
            "estimatedStorageGb": 6.2,
            "estimatedRamGb": 8.0,
        },
        revision = "main",
        license_id = "apache-2.0",
        license_accepted = True,
        allow_network = True,
        confirmation_id = "conf_hf_install",
        request_id = "req_hf_install",
        project_id = "project-hf",
    )

    assert contract["installContractVersion"] == "cognix_model_install_contract_v1"
    assert contract["status"] == "ready_for_download_review"
    assert contract["readyForDownloadReview"] is True
    assert contract["readyForWorkerEnqueue"] is False
    assert contract["downloadAllowedHere"] is False
    assert contract["targetModel"]["modelId"] == "Qwen/Qwen2.5-3B-Instruct"
    assert contract["sourcePolicy"]["sourceId"] == "huggingface_hub"
    assert contract["sourcePolicy"]["revisionPinRequired"] is True
    assert contract["sourcePolicy"]["rawSecretReadAllowed"] is False
    assert contract["workerHandoff"]["jobType"] == "model_download"
    assert contract["workerHandoff"]["queueId"] == "local_runtime"
    assert contract["workerHandoff"]["willEnqueue"] is False
    assert contract["storagePlan"]["willWriteFiles"] is False
    assert contract["policies"]["downloadsMustUseWorkerQueue"] is True
    assert contract["sideEffects"]["networkCall"] is False
    assert contract["sideEffects"]["fileWrite"] is False
    assert contract["sideEffects"]["modelDownload"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False


def test_model_residency_contract_blocks_load_until_install_without_mutation():
    hardware = stub_hardware_profile()
    cache = cognix_cache_manager.build_cache_state(
        hardware,
        active_model = None,
        loaded_models = [],
        loading_models = [],
        runtime_type = "llama-cpp",
    )
    lifecycle = cognix_model_lifecycle.build_model_lifecycle_plan(
        objective = "Prepare code model residency",
        hardware = hardware,
        recommendation = stub_recommendation(hardware)["recommendation"],
        cache = cache,
        classification = {"selectedDomain": "code", "scores": {"code": 0.91}},
        model_registry = {"models": []},
        requested_model_id = "cognix-code-4b-q4",
        project_type = "code",
    )

    contract = cognix_model_lifecycle.build_model_residency_contract(
        objective = "Prepare code model residency",
        lifecycle_plan = lifecycle,
        cache = cache,
        runtime_snapshot = {"runtimeType": "llama-cpp", "activeModel": None, "loadedModels": [], "loadingModels": []},
        confirmation_id = "conf_load_code",
        request_id = "req_load_code",
        project_id = "project-code",
    )

    assert contract["residencyContractVersion"] == "cognix_model_residency_contract_v1"
    assert contract["status"] == "blocked_missing_gate"
    assert contract["readyForRuntimeMutation"] is False
    assert contract["loadAllowedHere"] is False
    assert contract["unloadAllowedHere"] is False
    assert "installed_before_load" in contract["blockedWhen"]
    assert contract["targetModel"]["modelId"] == "cognix-code-4b-q4"
    assert contract["transition"]["loadRequired"] is False
    assert contract["transition"]["willLoad"] is False
    assert contract["transition"]["willUnload"] is False
    assert contract["policies"]["backendExecutorRequired"] is True
    assert contract["policies"]["runtimeMutationAllowedHere"] is False
    assert contract["sideEffects"]["modelLoad"] is False
    assert contract["sideEffects"]["modelUnload"] is False
    assert contract["sideEffects"]["runtimeMutation"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False


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


def test_model_install_contract_endpoint_logs_sanitized_hf_plan_without_download(monkeypatch):
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
        lambda: {"runtimeType": "transformers", "activeModel": None, "loadedModels": [], "loadingModels": []},
    )
    monkeypatch.setattr(
        cognix_routes.cognix_registry,
        "build_model_registry",
        lambda: {
            "registryVersion": "local_model_registry_v1",
            "providers": [],
            "models": [],
            "defaultModelId": None,
            "recommendedModelId": None,
        },
    )

    body = run_async(
        cognix_routes.model_install_contract(
            cognix_routes.ModelInstallContractRequest(
                objective = "Prepare HF install without exposing secrets",
                modelId = "Qwen/Qwen2.5-3B-Instruct",
                providerType = "hf_transformers",
                source = "huggingface_hub",
                revision = "main",
                licenseId = "apache-2.0",
                licenseAccepted = True,
                allowNetwork = True,
                confirmationId = "conf_hf_install",
                requestId = "req_hf_install",
                estimatedStorageGb = 6.2,
                estimatedRamGb = 8.0,
            ),
            current_subject = "alice",
        )
    )

    contract = body["modelInstallContract"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_model_install_contract_v1"
    assert contract["readyForDownloadReview"] is True
    assert contract["readyForWorkerEnqueue"] is False
    assert contract["sourcePolicy"]["sourceId"] == "huggingface_hub"
    assert contract["sideEffects"]["networkCall"] is False
    assert contract["sideEffects"]["fileWrite"] is False
    assert contract["sideEffects"]["modelDownload"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "model_install_contract_built"
    assert log["resourceType"] == "cognix_model_install_contract"
    assert log["metadata"]["installContractVersion"] == "cognix_model_install_contract_v1"
    assert log["metadata"]["sourceId"] == "huggingface_hub"
    assert log["metadata"]["readyForWorkerEnqueue"] is False
    assert log["metadata"]["sideEffects"]["modelDownload"] is False
    assert "access_token" not in log["metadataJson"].lower()
    assert "hf_token" not in log["metadataJson"].lower()
    assert "secret_value" not in log["metadataJson"].lower()


def test_model_residency_contract_endpoint_logs_review_without_runtime_mutation(monkeypatch):
    seed_accounts()
    qwen_model_id = "huihui_ai/qwen3-vl-abliterated:4b-instruct"
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
        lambda: {
            "runtimeType": "ollama",
            "activeModel": "cognix-general-3b-q4",
            "loadedModels": ["cognix-general-3b-q4"],
            "loadingModels": [],
        },
    )
    monkeypatch.setattr(
        cognix_routes.cognix_registry,
        "build_model_registry",
        lambda: {
            "registryVersion": "local_model_registry_v1",
            "providers": [],
            "models": [
                {
                    "id": qwen_model_id,
                    "providerId": "ollama-local",
                    "providerType": "ollama",
                    "source": "ollama",
                    "available": True,
                }
            ],
            "defaultModelId": qwen_model_id,
            "recommendedModelId": qwen_model_id,
            "ollama": {
                "configured": True,
                "reachable": True,
                "hasDefaultModel": True,
                "recommendedModel": qwen_model_id,
            },
        },
    )

    body = run_async(
        cognix_routes.model_residency_contract(
            cognix_routes.ModelResidencyContractRequest(
                objective = "Prepare Qwen native residency without loading it",
                modelId = qwen_model_id,
                projectType = "code",
                confirmationId = "conf_qwen_residency",
                requestId = "req_qwen_residency",
            ),
            current_subject = "alice",
        )
    )

    contract = body["modelResidencyContract"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_model_residency_contract_v1"
    assert contract["status"] == "ready_for_residency_review"
    assert contract["targetModel"]["modelId"] == qwen_model_id
    assert contract["targetModel"]["installed"] is True
    assert contract["transition"]["fromActiveModel"] == "cognix-general-3b-q4"
    assert contract["transition"]["toModel"] == qwen_model_id
    assert contract["transition"]["loadRequired"] is True
    assert contract["transition"]["willLoad"] is False
    assert contract["transition"]["willUnload"] is False
    assert contract["readyForRuntimeMutation"] is False
    assert contract["sideEffects"]["modelLoad"] is False
    assert contract["sideEffects"]["modelUnload"] is False
    assert contract["sideEffects"]["runtimeMutation"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "model_residency_contract_built"
    assert log["resourceType"] == "cognix_model_residency_contract"
    assert log["metadata"]["residencyContractVersion"] == "cognix_model_residency_contract_v1"
    assert log["metadata"]["targetModelId"] == qwen_model_id
    assert log["metadata"]["readyForRuntimeMutation"] is False
    assert log["metadata"]["loadRequired"] is True
    assert log["metadata"]["sideEffects"]["modelLoad"] is False


def test_model_comparison_plan_compares_outputs_without_generation():
    plan = cognix_model_comparison.build_model_comparison_plan(
        prompt = "Explique comment tester un petit modele local et un expert code.",
        models = [
            {"modelId": "cognix-general-small", "label": "General Small", "providerType": "local", "role": "general"},
            {"modelId": "cognix-code-4b-q4", "label": "Code Expert", "providerType": "local", "role": "code"},
            {"modelId": "cloud-reasoner", "label": "Cloud Reasoner", "providerType": "cloud", "role": "general"},
        ],
        outputs = [
            {
                "modelId": "cognix-general-small",
                "outputText": "Tester le modele avec un prompt simple, mesurer la latence et comparer la clarte.",
            },
            {
                "modelId": "cognix-code-4b-q4",
                "outputText": "Utilise un script Python, lance pytest, puis compare les erreurs et les temps de reponse.",
            },
        ],
    )
    models = {item["modelId"]: item for item in plan["models"]}

    assert plan["modelComparisonServiceVersion"] == "cognix_model_comparison_service_v1"
    assert plan["parallelInferenceRunnerVersion"] == "cognix_parallel_inference_runner_v1"
    assert plan["responseEvaluatorVersion"] == "cognix_response_evaluator_v1"
    assert plan["summary"]["modelCount"] == 3
    assert plan["summary"]["collectedOutputCount"] == 2
    assert plan["summary"]["awaitingGenerationCount"] == 1
    assert models["cloud-reasoner"]["requiresBackendGeneration"] is True
    assert models["cloud-reasoner"]["willGenerateNow"] is False
    assert models["cognix-code-4b-q4"]["evaluation"]["score"] > 0
    assert plan["parallelCallPlan"]["willCallModelsNow"] is False
    assert plan["sideEffects"]["parallelModelCall"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["networkModelCall"] is False


def test_model_comparison_endpoint_stores_outputs_and_user_preference():
    seed_accounts()

    body = run_async(
        cognix_routes.model_comparison_plan(
            cognix_routes.ModelComparisonPlanRequest(
                prompt = "Compare un petit modele local, un modele cloud et un expert code.",
                models = [
                    {"modelId": "local-small", "label": "Local Small", "providerType": "local", "role": "general"},
                    {"modelId": "cloud-qwen", "label": "Cloud Qwen", "providerType": "cloud", "role": "general"},
                    {"modelId": "code-expert", "label": "Code Expert", "providerType": "local", "role": "code"},
                ],
                outputs = [
                    {"modelId": "local-small", "outputText": "Reponse courte mais utile pour comparer rapidement."},
                    {"modelId": "cloud-qwen", "outputText": "Reponse plus detaillee, structuree, avec avantages et limites."},
                    {
                        "modelId": "code-expert",
                        "outputText": "Pour le code, lance ```pytest``` et inspecte les logs avant de choisir.",
                    },
                ],
                storeComparison = True,
            ),
            current_subject = "alice",
        )
    )
    comparison = body["comparison"]
    output_id = next(item["id"] for item in comparison["outputs"] if item["modelId"] == "code-expert")
    detail = run_async(cognix_routes.model_comparison_detail(comparison["id"], current_subject = "alice"))
    preference = run_async(
        cognix_routes.model_comparison_preference(
            comparison["id"],
            cognix_routes.ModelComparisonPreferenceRequest(outputId = output_id, reason = "Meilleur format code."),
            current_subject = "alice",
        )
    )
    listed = run_async(cognix_routes.model_comparisons(current_subject = "alice"))
    bob_listed = run_async(cognix_routes.model_comparisons(current_subject = "bob"))

    assert body["auditLogId"].startswith("aud_")
    assert body["sideEffects"]["comparisonWrite"] is True
    assert body["sideEffects"]["outputWrite"] is True
    assert body["sideEffects"]["parallelModelCall"] is False
    assert body["sideEffects"]["generation"] is False
    assert comparison["id"].startswith("mcmp_")
    assert len(comparison["outputs"]) == 3
    assert detail["comparison"]["id"] == comparison["id"]
    assert preference["comparison"]["selectedOutputId"] == output_id
    assert preference["preference"]["modelId"] == "code-expert"
    assert preference["sideEffects"]["preferenceWrite"] is True
    assert preference["sideEffects"]["generation"] is False
    assert [item["id"] for item in listed["comparisons"]] == [comparison["id"]]
    assert bob_listed["comparisons"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {"model_comparison_plan_built", "model_comparison_preference_recorded"}.issubset(actions)


def test_model_translator_plans_gguf_to_ollama_without_conversion_job():
    plan = cognix_model_translator.build_model_conversion_plan(
        source_model = {
            "modelId": "qwen-4b-q4.gguf",
            "format": "gguf",
            "architecture": "qwen",
            "license": "apache-2.0",
        },
        target_format = "ollama_modelfile",
        conversion_options = {"template": "chatml"},
    )

    assert plan["conversionServiceVersion"] == "cognix_model_conversion_service_v1"
    assert plan["compatibilityCheckerVersion"] == "cognix_compatibility_checker_v1"
    assert plan["exportManagerVersion"] == "cognix_model_export_manager_v1"
    assert plan["compatibility"]["compatible"] is True
    assert plan["targetFormat"] == "ollama_modelfile"
    assert plan["conversionPlan"]["jobQueueRequired"] is True
    assert plan["conversionPlan"]["willEnqueueNow"] is False
    assert plan["exportPlan"]["willWriteArtifact"] is False
    assert plan["registryUpdatePlan"]["willUpdateRegistryNow"] is False
    assert plan["sideEffects"]["modelFileWrite"] is False
    assert plan["sideEffects"]["conversionJobEnqueue"] is False
    assert plan["sideEffects"]["modelLoad"] is False


def test_model_translator_blocks_unknown_or_impossible_conversion_without_promise():
    plan = cognix_model_translator.build_model_conversion_plan(
        source_model = {"modelId": "qwen-4b-q4.gguf", "format": "gguf"},
        target_format = "transformers",
    )

    assert plan["status"] == "blocked"
    assert plan["compatibility"]["compatible"] is False
    assert plan["compatibility"]["status"] == "blocked_impossible_or_unknown"
    assert any("conversion universelle" in item["message"] for item in plan["risks"])
    assert plan["conversionPlan"]["willEnqueueNow"] is False
    assert plan["sideEffects"]["modelFileRead"] is False
    assert plan["sideEffects"]["modelFileWrite"] is False


def test_model_conversion_endpoint_stores_plan_and_logs_audit():
    seed_accounts()
    body = run_async(
        cognix_routes.model_conversion_plan(
            cognix_routes.ModelConversionPlanRequest(
                sourceModel = {
                    "modelId": "qwen-4b-q4.gguf",
                    "format": "gguf",
                    "architecture": "qwen",
                },
                targetFormat = "ollama_modelfile",
                conversionOptions = {"template": "chatml"},
                storeConversion = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["modelConversionPlan"]
    conversion = body["modelConversion"]
    assert body["auditLogId"].startswith("aud_")
    assert conversion["id"] == plan["conversionId"]
    assert conversion["logs"][0]["eventType"] == "conversion_plan_stored"
    assert body["sideEffects"]["conversionPlanWrite"] is True
    assert body["sideEffects"]["conversionJobEnqueue"] is False
    assert body["sideEffects"]["registryUpdate"] is False
    assert body["sideEffects"]["modelLoad"] is False

    listed = run_async(cognix_routes.model_conversions(current_subject = "alice"))
    assert listed["conversions"][0]["id"] == conversion["id"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "model_conversion_plan_built"
    assert log["metadata"]["compatible"] is True
    assert log["metadata"]["sideEffects"]["conversionJobEnqueue"] is False


def test_plugin_marketplace_catalog_requires_permission_manifests():
    catalog = cognix_plugin_marketplace.build_marketplace_catalog()

    assert catalog["marketplaceServiceVersion"] == "cognix_plugin_marketplace_service_v1"
    assert {"productivity", "education", "code", "research", "business", "connectors", "models"}.issubset(
        set(catalog["categories"])
    )
    assert catalog["summary"]["pluginCount"] >= 3
    assert all(plugin["permissionCount"] > 0 for plugin in catalog["plugins"])
    assert all(plugin["signatureStatus"] == "verified" for plugin in catalog["plugins"])
    assert catalog["sideEffects"]["pluginInstall"] is False
    assert catalog["sideEffects"]["networkCall"] is False


def test_plugin_install_plan_blocks_manifest_without_permissions():
    plan = cognix_plugin_marketplace.build_plugin_install_plan(
        username = "alice",
        plugin_manifest = {
            "id": "unsafe-plugin",
            "displayName": "Unsafe Plugin",
            "category": "code",
            "version": "1.0.0",
            "publisher": "unknown",
            "signature": {"status": "verified", "issuer": "cognix-marketplace"},
            "capabilities": ["write_code"],
        },
        is_admin = False,
        has_developer_mode = False,
        granted_permissions = set(),
    )

    assert plan["status"] == "blocked_missing_permission_manifest"
    assert plan["validation"]["permissionManifestPresent"] is False
    assert "missing_permission_manifest" in plan["validation"]["blockingReasons"]
    assert plan["installationPlan"]["readyToInstall"] is False
    assert plan["sideEffects"]["pluginInstall"] is False
    assert plan["sideEffects"]["permissionGrant"] is False


def test_plugin_install_plan_endpoint_stores_permissions_and_audit():
    seed_accounts()
    body = run_async(
        cognix_routes.plugin_install_plan(
            cognix_routes.PluginInstallPlanRequest(
                pluginId = "github-project-board",
                targetScope = "user",
                storePlan = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["pluginInstallPlan"]
    installed = body["installedPlugin"]
    assert plan["status"] == "blocked_missing_permissions"
    assert plan["validation"]["signatureStatus"] == "verified"
    assert "github:read" in plan["permissionScan"]["missingPermissions"]
    assert installed["id"] == plan["installationPlanId"]
    assert installed["pluginId"] == "github-project-board"
    assert installed["reviews"][0]["reviewType"] == "security_scan"
    assert any(item["permissionKey"] == "github:write" for item in installed["permissions"])
    assert body["sideEffects"]["pluginPlanWrite"] is True
    assert body["sideEffects"]["pluginInstall"] is False
    assert body["sideEffects"]["pluginActivation"] is False
    assert body["sideEffects"]["networkCall"] is False

    listed = run_async(cognix_routes.plugin_installations(current_subject = "alice"))
    assert listed["installations"][0]["id"] == installed["id"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "plugin_install_plan_built"
    assert log["metadata"]["pluginId"] == "github-project-board"
    assert log["metadata"]["sideEffects"]["pluginInstall"] is False


def test_thinking_status_redacts_technical_model_details():
    lifecycle = {
        "installPlan": {"required": False},
        "loadPlan": {"action": "would_load_on_demand"},
        "compatibility": {"fit": {"status": "ok"}},
        "warnings": [],
    }

    plan = cognix_thinking_status.build_thinking_status_plan(
        objective = "Explique ce bug avec huihui_ai/qwen3-vl-abliterated:4b-instruct",
        classification = {
            "selectedDomain": "code",
            "label": "Code",
            "recommendedModelId": "cognix-code-4b-q4",
            "needsClarification": False,
            "externalMoePlan": {
                "routerVersion": "cognix_external_moe_router_v1",
                "primaryExpert": {
                    "expertId": "cognix-code",
                    "label": "CogniX Code",
                    "modelId": "cognix-code-4b-q4",
                },
                "secondaryExperts": [],
            },
        },
        task_strategy = {"label": "Assistant code", "path": "codex_guarded_pipeline"},
        recommendation = {"readiness": "ready", "modelId": "huihui_ai/qwen3-vl-abliterated:4b-instruct"},
        model_lifecycle_plan = lifecycle,
        context_plan = {"assemblyStrategy": "memory_project_recent"},
        rag_plan = {"recommendedPath": "no_rag_needed"},
        project_expert_plan = {
            "projectMode": "specialized_project",
            "primaryExpert": {"selectedModel": {"modelId": "cognix-code-4b-q4"}},
        },
        execution_policy = {"automaticExecutionAllowed": False},
    )

    visible_text = str(plan["visibleTimeline"]).casefold()
    visible_events = str(plan["visibleStatusEvents"]).casefold()
    assert plan["thinkingStatusVersion"] == "cognix_thinking_status_v1"
    assert plan["visibleTimelineVersion"] == "cognix_visible_thinking_timeline_v1"
    assert plan["status"] == "ready"
    assert plan["progress"] == 100
    assert any(item["id"] == "select_expert" for item in plan["visibleTimeline"])
    assert any(item["id"] == "expert_selection" for item in plan["visibleStatusEvents"])
    assert plan["displayContract"]["frontendMustHideModelIdentifiers"] is True
    assert plan["redaction"]["redactionContractVersion"] == "cognix_thinking_redaction_contract_v1"
    assert plan["redaction"]["visibleTimelineContainsModelIds"] is False
    assert plan["redaction"]["visibleTimelineContainsRoutingScores"] is False
    assert plan["redaction"]["verifiedNoTechnicalLeak"] is True
    assert "qwen" not in visible_text
    assert "qwen" not in visible_events
    assert "cognix-code-4b-q4" not in visible_text
    assert "cognix-code-4b-q4" not in visible_events
    assert "0." not in visible_text
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["uiMutation"] is False


def test_thinking_status_endpoint_logs_audited_visible_plan(monkeypatch):
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
        cognix_routes.thinking_status_plan(
            cognix_routes.ThinkingStatusPlanRequest(
                objective = "Teste une reponse visible propre pour Qwen",
                modelId = "huihui_ai/qwen3-vl-abliterated:4b-instruct",
                projectType = "code",
                audience = "chat",
            ),
            current_subject = "alice",
        )
    )

    thinking = body["thinkingStatusPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_thinking_status_v1"
    assert thinking["displayContract"]["frontendMayShowOnlyTimeline"] is True
    assert thinking["visibleTimelineVersion"] == "cognix_visible_thinking_timeline_v1"
    assert any(item["id"] == "expert_selection" for item in thinking["visibleStatusEvents"])
    assert thinking["redaction"]["visibleTimelineContainsRoutingScores"] is False
    assert thinking["redaction"]["verifiedNoTechnicalLeak"] is True
    assert thinking["sideEffects"]["generation"] is False
    assert thinking["sideEffects"]["uiMutation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "thinking_status_plan_built"
    assert log["resourceType"] == "cognix_thinking_status"
    assert log["metadata"]["thinkingStatusVersion"] == "cognix_thinking_status_v1"
    assert log["metadata"]["visibleTimelineVersion"] == "cognix_visible_thinking_timeline_v1"
    assert log["metadata"]["redactionContractVersion"] == "cognix_thinking_redaction_contract_v1"
    assert log["metadata"]["verifiedNoTechnicalLeak"] is True
    assert "modelId" in log["metadata"]["hiddenTechnicalFields"]
    assert log["metadata"]["sideEffects"]["uiMutation"] is False


def test_response_reflection_scores_reliable_answer_without_model_calls():
    evaluation = cognix_response_reflection.build_response_reflection_evaluation(
        prompt = "Explique pourquoi le RAG est preferable au fine-tuning pour un document de cours.",
        response = (
            "Le RAG est preferable quand l'objectif est d'utiliser des informations presentes "
            "dans un document sans modifier le comportement du modele. Il garde les sources "
            "separees, permet de citer les passages utiles et evite un entrainement inutile."
        ),
        response_sources = [{"id": "src_1", "title": "Cours IA"}],
        requires_sources = True,
        task_type = "rag",
        model_id = "cognix-general",
    )

    assert evaluation["reflectionVersion"] == "cognix_response_reflection_v1"
    assert evaluation["confidence"]["label"] == "high"
    assert evaluation["confidence"]["verificationRequired"] is False
    assert evaluation["confidence"]["recommendedAction"] == "accept"
    assert evaluation["qualitySignals"]["sourceCount"] == 1
    assert evaluation["policies"]["rawChainOfThoughtAllowed"] is False
    assert evaluation["policies"]["frontendMustNotShowHiddenReasoning"] is True
    assert evaluation["sideEffects"]["modelLoad"] is False
    assert evaluation["sideEffects"]["generation"] is False
    assert evaluation["sideEffects"]["networkModelCall"] is False
    assert evaluation["sideEffects"]["rawReasoningExposure"] is False


def test_response_reflection_flags_missing_sources_and_incomplete_answer():
    evaluation = cognix_response_reflection.build_response_reflection_evaluation(
        prompt = "Donne une reponse detaillee avec sources sur la securite des outils connectes.",
        response = "C'est probablement securise.",
        response_sources = [],
        requires_sources = True,
        task_type = "security",
    )

    issue_ids = {item["id"] for item in evaluation["issues"]}
    assert evaluation["confidence"]["verificationRequired"] is True
    assert evaluation["confidence"]["recommendedAction"] in {"verify_with_sources", "second_pass_recommended"}
    assert "missing_sources" in issue_ids
    assert "incomplete_response" in issue_ids
    assert evaluation["userVisibleMetadata"]["showExpandableDetails"] is True
    assert evaluation["sideEffects"]["toolExecution"] is False
    assert evaluation["sideEffects"]["memoryWrite"] is False


def test_expert_generalist_quality_gate_recommends_review_without_second_model_call():
    gate = cognix_response_reflection.build_expert_generalist_quality_gate(
        prompt = "Explique avec sources pourquoi le RAG est meilleur que le fine-tuning pour ce PDF. token=sk-1234567890abcdef",
        expert_response = "C'est probablement mieux.",
        expert_model_id = "cognix-research",
        generalist_model_id = "cognix-general",
        response_sources = [],
        requires_sources = True,
        task_type = "research",
        domain = "rag",
    )

    assert gate["qualityGateVersion"] == "cognix_expert_generalist_quality_gate_v1"
    assert gate["mode"] == "expert_generalist_quality_gate"
    assert gate["summary"]["secondPassRecommended"] is True
    assert gate["generalist"]["modelId"] == "cognix-general"
    assert "source_verification" in gate["generalist"]["allowedReviewModes"]
    assert gate["handoffContract"]["backendOrchestratorRequired"] is True
    assert gate["handoffContract"]["automaticSecondModelCallAllowed"] is False
    assert gate["handoffContract"]["frontendDirectSecondPassAllowed"] is False
    assert gate["handoffContract"]["rawPromptIncluded"] is False
    assert gate["handoffContract"]["rawExpertResponseIncluded"] is False
    assert "sk-1234567890abcdef" not in str(gate)
    assert gate["sideEffects"]["generation"] is False
    assert gate["sideEffects"]["secondModelCall"] is False
    assert gate["sideEffects"]["networkModelCall"] is False


def test_response_reflection_endpoint_stores_evaluation_and_logs_audit():
    seed_accounts()

    body = run_async(
        cognix_routes.response_reflection_evaluate(
            cognix_routes.ResponseReflectionRequest(
                prompt = "Resume ce document avec les sources principales.",
                response = "Resume trop court.",
                message_id = "msg_1",
                thread_id = "thread_1",
                project_id = None,
                model_id = "cognix-general",
                requires_sources = True,
                response_sources = [],
            ),
            current_subject = "alice",
        )
    )

    reflection = body["responseReflection"]
    record = body["record"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_response_reflection_v1"
    assert reflection["confidence"]["verificationRequired"] is True
    assert record["id"].startswith("rfl_")
    assert record["messageId"] == "msg_1"
    assert record["verificationRequired"] is True
    assert body["sideEffects"]["modelLoad"] is False
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["networkModelCall"] is False
    assert body["sideEffects"]["evaluationWrite"] is True

    evaluations = cognix_db.list_response_evaluations("alice", message_id = "msg_1")
    assert len(evaluations) == 1
    assert evaluations[0]["id"] == record["id"]
    assert evaluations[0]["evaluation"]["reflectionVersion"] == "cognix_response_reflection_v1"

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "response_reflection_evaluated"
    assert log["metadata"]["responseReflectionVersion"] == "cognix_response_reflection_v1"
    assert log["metadata"]["verificationRequired"] is True
    assert log["metadata"]["sideEffects"]["generation"] is False
    assert log["metadata"]["storageSideEffects"]["evaluationWrite"] is True


def test_expert_generalist_quality_gate_endpoint_stores_metadata_and_audits():
    seed_accounts()

    body = run_async(
        cognix_routes.response_reflection_expert_generalist_gate(
            cognix_routes.ExpertGeneralistQualityGateRequest(
                prompt = "Explique avec sources les limites du fine-tuning pour des documents internes.",
                expertResponse = "Il faut faire attention.",
                messageId = "msg_gate",
                threadId = "thread_gate",
                expertModelId = "cognix-research",
                generalistModelId = "cognix-general",
                requiresSources = True,
                responseSources = [],
                taskType = "research",
                domain = "rag",
            ),
            current_subject = "alice",
        )
    )

    gate = body["expertGeneralistGate"]
    record = body["record"]
    assert body["plannerVersion"] == "cognix_expert_generalist_quality_gate_v1"
    assert body["auditLogId"].startswith("aud_")
    assert gate["summary"]["secondPassRecommended"] is True
    assert gate["handoffContract"]["rawPromptIncluded"] is False
    assert gate["handoffContract"]["rawExpertResponseIncluded"] is False
    assert record["id"].startswith("rfl_")
    assert record["messageId"] == "msg_gate"
    assert record["evaluation"]["qualityGateVersion"] == "cognix_expert_generalist_quality_gate_v1"
    assert record["verificationRequired"] is True
    assert body["sideEffects"]["secondModelCall"] is False
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["evaluationWrite"] is True

    log = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"][0]
    assert log["action"] == "expert_generalist_quality_gate_built"
    assert log["metadata"]["qualityGateVersion"] == "cognix_expert_generalist_quality_gate_v1"
    assert log["metadata"]["secondPassRecommended"] is True
    assert log["metadata"]["rawPromptIncluded"] is False
    assert log["metadata"]["rawExpertResponseIncluded"] is False
    assert log["metadata"]["sideEffects"]["secondModelCall"] is False


def test_response_reflection_list_endpoint_is_user_scoped():
    seed_accounts()
    alice_eval = cognix_response_reflection.build_response_reflection_evaluation(
        prompt = "Explique CogniX.",
        response = "CogniX orchestre les modeles, outils et memoire.",
    )
    bob_eval = cognix_response_reflection.build_response_reflection_evaluation(
        prompt = "Explique CogniX.",
        response = "CogniX est une plateforme IA modulaire.",
    )
    cognix_db.create_response_evaluation("alice", evaluation = alice_eval, message_id = "msg_alice")
    cognix_db.create_response_evaluation("bob", evaluation = bob_eval, message_id = "msg_bob")

    body = run_async(cognix_routes.response_reflection_evaluations(current_subject = "alice"))

    assert body["username"] == "alice"
    assert len(body["evaluations"]) == 1
    assert body["evaluations"][0]["messageId"] == "msg_alice"


def test_draft_style_registry_declares_profiles_without_generation():
    registry = cognix_draft_generation.build_style_profile_registry()
    profile_ids = {item["id"] for item in registry["profiles"]}

    assert registry["styleProfileRegistryVersion"] == "cognix_style_profile_registry_v1"
    assert {"quick", "detailed", "technical", "simple", "business", "pedagogical"}.issubset(profile_ids)
    assert registry["policies"]["backendOrchestratorRequired"] is True
    assert registry["policies"]["multipleDraftsOnDemandOnly"] is True
    assert registry["summary"]["frontendDirectModelCallAllowed"] is False
    assert registry["sideEffects"]["generation"] is False
    assert registry["sideEffects"]["networkModelCall"] is False
    assert registry["sideEffects"]["variantWrite"] is False


def test_draft_generation_plan_prepares_variants_without_model_call():
    plan = cognix_draft_generation.build_draft_generation_plan(
        prompt = "Explique ce bug Python avec une version courte et une version technique.",
        requested_variants = ["quick", "technical", "detailed"],
        max_variants = 3,
        task_type = "code",
        message_id = "msg_draft",
        model_id = "cognix-code",
    )

    assert plan["draftGenerationVersion"] == "cognix_draft_generation_v1"
    assert plan["mode"] == "dry_run"
    assert plan["selectedVariantTypes"] == ["quick", "technical", "detailed"]
    assert plan["costPlan"]["estimatedGenerationCount"] == 3
    assert plan["costPlan"]["requiresExplicitUserAction"] is True
    assert plan["rankingPlan"]["usesResponseReflection"] is True
    assert plan["rankingPlan"]["rawReasoningVisible"] is False
    assert all(item["requiresBackendGeneration"] is True for item in plan["variants"])
    assert all(item["willGenerateNow"] is False for item in plan["variants"])
    assert plan["policies"]["frontendDirectModelCallAllowed"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["variantWrite"] is False


def test_draft_generation_plan_endpoint_logs_audit_without_generation():
    seed_accounts()

    body = run_async(
        cognix_routes.draft_generation_plan(
            cognix_routes.DraftGenerationPlanRequest(
                prompt = "Prepare plusieurs styles pour expliquer une notion de physique.",
                requested_variants = ["simple", "pedagogical", "detailed"],
                max_variants = 3,
                task_type = "education",
                message_id = "msg_multi",
            ),
            current_subject = "alice",
        )
    )

    plan = body["draftGenerationPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_draft_generation_v1"
    assert plan["selectedVariantTypes"] == ["simple", "pedagogical", "detailed"]
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["networkModelCall"] is False
    assert body["sideEffects"]["variantWrite"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "draft_generation_plan_built"
    assert log["metadata"]["draftGenerationVersion"] == "cognix_draft_generation_v1"
    assert log["metadata"]["selectedVariantTypes"] == ["simple", "pedagogical", "detailed"]
    assert log["metadata"]["sideEffects"]["generation"] is False


def test_response_variant_store_and_list_are_user_scoped():
    seed_accounts()
    variant = run_async(
        cognix_routes.create_response_variant(
            cognix_routes.ResponseVariantRequest(
                variant_type = "technical",
                title = "Version technique",
                content = "Analyse technique stockee apres generation backend.",
                message_id = "msg_variant",
                thread_id = "thread_variant",
                model_id = "cognix-code",
                ranking_score = 0.82,
                metadata = {"source": "test"},
            ),
            current_subject = "alice",
        )
    )
    cognix_db.create_response_variant(
        "bob",
        variant_type = "quick",
        title = "Bob",
        content = "Variante autre utilisateur.",
        message_id = "msg_variant",
    )

    listed = run_async(
        cognix_routes.response_variants(
            message_id = "msg_variant",
            current_subject = "alice",
        )
    )

    assert variant["variant"]["id"].startswith("var_")
    assert variant["variant"]["variantType"] == "technical"
    assert variant["variant"]["rankingScore"] == 0.82
    assert variant["sideEffects"]["generation"] is False
    assert variant["sideEffects"]["variantWrite"] is True
    assert len(listed["variants"]) == 1
    assert listed["variants"][0]["title"] == "Version technique"

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == variant["auditLogId"]
    assert log["action"] == "response_variant_stored"
    assert log["metadata"]["storageSideEffects"]["variantWrite"] is True


def test_debate_role_registry_declares_public_roles_without_generation():
    registry = cognix_debate_orchestrator.build_debate_role_registry()
    role_ids = {item["id"] for item in registry["roles"]}

    assert registry["debateRoleRegistryVersion"] == "cognix_debate_role_registry_v1"
    assert {"advocate", "critic", "synthesizer"}.issubset(role_ids)
    assert registry["policies"]["backendOrchestratorRequired"] is True
    assert registry["policies"]["rawChainOfThoughtAllowed"] is False
    assert registry["policies"]["publicArgumentsOnly"] is True
    assert registry["summary"]["frontendDirectModelCallAllowed"] is False
    assert registry["sideEffects"]["generation"] is False
    assert registry["sideEffects"]["networkModelCall"] is False
    assert registry["sideEffects"]["debateSessionWrite"] is False


def test_debate_plan_prepares_bounded_rounds_without_model_call():
    plan = cognix_debate_orchestrator.build_debate_plan(
        prompt = "Fais debattre deux agents sur l'architecture CogniX pour le RAG.",
        requested_roles = ["advocate", "critic", "domain_expert", "synthesizer"],
        max_rounds = 4,
        task_type = "architecture",
        message_id = "msg_debate",
        model_id = "cognix-general",
    )

    role_ids = [item["id"] for item in plan["roles"]]
    round_ids = [item["id"] for item in plan["rounds"]]
    assert plan["debateOrchestratorVersion"] == "cognix_debate_orchestrator_v1"
    assert plan["mode"] == "dry_run"
    assert role_ids == ["advocate", "critic", "domain_expert", "synthesizer"]
    assert "round_synthesis" in round_ids
    assert plan["summary"]["maxRounds"] == 4
    assert plan["displayContract"]["rawChainOfThoughtVisible"] is False
    assert plan["displayContract"]["showOneCleanThread"] is True
    assert plan["policies"]["judgeSynthesisRequired"] is True
    assert all(item["willGenerateNow"] is False for item in plan["rounds"])
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["debateSessionWrite"] is False


def test_debate_plan_endpoint_creates_session_rounds_and_logs_audit():
    seed_accounts()

    body = run_async(
        cognix_routes.debate_plan(
            cognix_routes.DebatePlanRequest(
                prompt = "Debats sur le choix entre RAG et fine-tuning pour un cours.",
                requested_roles = ["advocate", "critic", "synthesizer"],
                max_rounds = 3,
                task_type = "strategy",
                message_id = "msg_debate_endpoint",
                thread_id = "thread_debate",
                create_session = True,
            ),
            current_subject = "alice",
        )
    )

    session = body["session"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_debate_orchestrator_v1"
    assert body["debatePlan"]["displayContract"]["rawChainOfThoughtVisible"] is False
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["debateSessionWrite"] is True
    assert session["id"].startswith("deb_")
    assert session["messageId"] == "msg_debate_endpoint"
    assert len(session["rounds"]) >= 3
    assert any(round_item["roleId"] == "synthesizer" for round_item in session["rounds"])

    sessions = cognix_db.list_debate_sessions("alice", message_id = "msg_debate_endpoint")
    assert len(sessions) == 1
    assert sessions[0]["id"] == session["id"]
    assert sessions[0]["plan"]["debateOrchestratorVersion"] == "cognix_debate_orchestrator_v1"

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "debate_plan_built"
    assert log["metadata"]["debateOrchestratorVersion"] == "cognix_debate_orchestrator_v1"
    assert log["metadata"]["sessionCreated"] is True
    assert log["metadata"]["sideEffects"]["generation"] is False


def test_debate_output_store_is_user_scoped_and_public_summary_only():
    seed_accounts()
    plan = cognix_debate_orchestrator.build_debate_plan(
        prompt = "Debat sur architecture CogniX.",
        requested_roles = ["advocate", "critic", "synthesizer"],
        max_rounds = 3,
    )
    session = cognix_db.create_debate_session(
        "alice",
        plan = plan,
        prompt = "Debat sur architecture CogniX.",
        message_id = "msg_debate_store",
    )
    bob_session = cognix_db.create_debate_session(
        "bob",
        plan = plan,
        prompt = "Autre debat.",
        message_id = "msg_debate_store",
    )

    body = run_async(
        cognix_routes.create_debate_output(
            session["id"],
            cognix_routes.DebateOutputRequest(
                role_id = "synthesizer",
                output_type = "synthesis",
                public_summary = "Synthese publique sans raisonnement interne.",
                content = "Contenu public final.",
                model_id = "cognix-general",
                metadata = {"source": "test"},
            ),
            current_subject = "alice",
        )
    )
    run_async(
        cognix_routes.create_debate_output(
            bob_session["id"],
            cognix_routes.DebateOutputRequest(
                roleId = "synthesizer",
                outputType = "synthesis",
                publicSummary = "Bob only.",
            ),
            current_subject = "bob",
        )
    )
    listed = run_async(cognix_routes.debate_sessions(message_id = "msg_debate_store", current_subject = "alice"))

    assert body["output"]["id"].startswith("dbo_")
    assert body["output"]["roleId"] == "synthesizer"
    assert body["output"]["publicSummary"] == "Synthese publique sans raisonnement interne."
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["debateOutputWrite"] is True
    assert len(listed["sessions"]) == 1
    assert listed["sessions"][0]["id"] == session["id"]
    assert len(listed["sessions"][0]["outputs"]) == 1

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = next(item for item in admin_read["logs"] if item["id"] == body["auditLogId"])
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "debate_output_stored"
    assert log["metadata"]["storageSideEffects"]["debateOutputWrite"] is True


def test_tool_discovery_capability_registry_blocks_auto_installation():
    registry = cognix_tool_discovery.build_tool_capability_registry()
    tools = {item["toolId"]: item for item in registry["capabilities"]}

    assert registry["capabilityRegistryVersion"] == "cognix_tool_capability_registry_v1"
    assert registry["toolDiscoveryVersion"] == "cognix_tool_discovery_v1"
    assert {
        "calculator",
        "physics-solver",
        "latex-renderer",
        "python-runtime",
        "pytorch",
        "ollama",
        "google-drive",
    }.issubset(tools)
    assert tools["calculator"]["enabledByDefault"] is True
    assert tools["calculator"]["connectorBacked"] is False
    assert tools["physics-solver"]["enabledByDefault"] is True
    assert tools["physics-solver"]["connectorBacked"] is False
    assert tools["latex-renderer"]["enabledByDefault"] is True
    assert tools["latex-renderer"]["connectorBacked"] is False
    assert registry["summary"]["automaticInstallAllowed"] is False
    assert registry["policies"]["automaticInstallationAllowed"] is False
    assert registry["policies"]["frontendDirectInstallationAllowed"] is False
    assert registry["sideEffects"]["installation"] is False
    assert registry["sideEffects"]["toolExecution"] is False
    assert registry["sideEffects"]["secretRead"] is False


def test_tool_discovery_plan_recommends_project_tools_without_installing():
    plan = cognix_tool_discovery.build_tool_discovery_plan(
        username = "alice",
        objective = "Projet Python ML avec Qwen GGUF, training local et requirements.",
        project_type = "ml",
        file_names = ["train.py", "model.gguf", "requirements.txt"],
        installed_tool_ids = ["ollama"],
    )
    recommendations = {item["toolId"]: item for item in plan["recommendations"]}

    assert plan["toolDiscoveryVersion"] == "cognix_tool_discovery_v1"
    assert plan["mode"] == "recommendation_dry_run"
    assert {"python-runtime", "python-venv", "pytorch", "ollama", "llama-cpp"}.issubset(recommendations)
    assert recommendations["ollama"]["status"] == "installed"
    assert recommendations["python-runtime"]["actions"]["automaticInstallAllowed"] is False
    assert recommendations["llama-cpp"]["guardrails"]["noAutomaticInstallation"] is True
    assert plan["summary"]["automaticInstallAllowed"] is False
    assert plan["sideEffects"]["installation"] is False
    assert plan["sideEffects"]["toolExecution"] is False
    assert plan["sideEffects"]["networkToolCall"] is False


def test_tool_discovery_endpoint_stores_recommendations_and_ignore_is_user_scoped():
    seed_accounts()

    body = run_async(
        cognix_routes.analyze_tool_discovery(
            cognix_routes.ToolDiscoveryRequest(
                objective = "Cours de physique avec formules LaTeX, notes PDF et documents sources.",
                projectType = "maths",
                fileNames = ["cours.tex", "notes.pdf"],
                installedToolIds = ["python-runtime"],
                recordInstalledSnapshot = True,
                storeRecommendations = True,
            ),
            current_subject = "alice",
        )
    )

    tool_ids = {item["toolId"] for item in body["toolDiscoveryPlan"]["recommendations"]}
    stored_ids = {item["toolId"] for item in body["storedRecommendations"]}
    assert body["auditLogId"].startswith("aud_")
    assert {"calculator", "physics-solver", "latex-renderer", "rag-indexer"}.issubset(tool_ids)
    assert {"calculator", "physics-solver", "latex-renderer", "rag-indexer"}.issubset(stored_ids)
    assert body["sideEffects"]["recommendationWrite"] is True
    assert body["sideEffects"]["installedToolWrite"] is True
    assert body["sideEffects"]["installation"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert any(item["toolId"] == "python-runtime" for item in body["installedTools"])

    listed = run_async(cognix_routes.tool_recommendations(current_subject = "alice"))
    bob_listed = run_async(cognix_routes.tool_recommendations(current_subject = "bob"))
    assert len(listed["recommendations"]) == len(body["storedRecommendations"])
    assert bob_listed["recommendations"] == []

    recommendation_id = listed["recommendations"][0]["id"]
    ignored = run_async(
        cognix_routes.ignore_tool_recommendation(
            recommendation_id,
            current_subject = "alice",
        )
    )
    after_ignore = run_async(cognix_routes.tool_recommendations(current_subject = "alice"))
    include_ignored = run_async(
        cognix_routes.tool_recommendations(include_ignored = True, current_subject = "alice")
    )

    assert ignored["recommendation"]["id"] == recommendation_id
    assert ignored["recommendation"]["ignored"] is True
    assert all(item["id"] != recommendation_id for item in after_ignore["recommendations"])
    assert any(item["id"] == recommendation_id and item["ignored"] for item in include_ignored["recommendations"])

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    analyze_log = next(item for item in admin_read["logs"] if item["id"] == body["auditLogId"])
    ignore_log = next(item for item in admin_read["logs"] if item["id"] == ignored["auditLogId"])
    assert analyze_log["action"] == "tool_discovery_analyzed"
    assert analyze_log["metadata"]["sideEffects"]["installation"] is False
    assert ignore_log["action"] == "tool_recommendation_ignored"
    assert ignore_log["metadata"]["sideEffects"]["toolExecution"] is False


def test_context_graph_blueprint_declares_theme_safe_graph_contract():
    blueprint = cognix_context_graph.build_context_graph_blueprint()
    node_types = {item["id"]: item for item in blueprint["nodeTypes"]}

    assert blueprint["contextGraphVersion"] == "cognix_context_graph_v1"
    assert blueprint["entityExtractorVersion"] == "cognix_entity_extractor_v1"
    assert blueprint["relationBuilderVersion"] == "cognix_relation_builder_v1"
    assert {"project", "document", "chat", "concept", "model", "tool"}.issubset(node_types)
    assert blueprint["displayContract"]["themeAwareTokensOnly"] is True
    assert blueprint["displayContract"]["customVisualizationLibraryRequired"] is False
    assert blueprint["policies"]["rawMessageContentStoredInGraph"] is False
    assert blueprint["policies"]["modelGenerationAllowed"] is False
    assert blueprint["sideEffects"]["generation"] is False
    assert blueprint["sideEffects"]["snapshotWrite"] is False
    assert blueprint["sideEffects"]["uiMutation"] is False


def test_context_graph_snapshot_builds_nodes_edges_without_model_call():
    graph = cognix_context_graph.build_context_graph_snapshot(
        username = "alice",
        project_id = "project-physics",
        project_name = "Physique",
        project_type = "physics",
        messages = [
            {
                "id": "msg_1",
                "role": "user",
                "content": "Construire un RAG pour mecanique quantique avec PDF et equations LaTeX.",
            }
        ],
        documents = [{"id": "doc_1", "name": "cours.pdf", "summary": "Mecanique quantique et equations."}],
        files = ["notes.tex", "experiences.md"],
        decisions = ["Utiliser RAG avant fine-tuning pour ce cours."],
        tasks = ["Indexer le PDF de physique."],
        models = ["qwen-local"],
        tools = ["rag-indexer"],
    )
    node_types = {item["type"] for item in graph["nodes"]}
    edge_types = {item["type"] for item in graph["edges"]}
    chat_nodes = [item for item in graph["nodes"] if item["type"] == "chat"]

    assert graph["contextGraphVersion"] == "cognix_context_graph_v1"
    assert {"project", "document", "chat", "concept", "file", "decision", "task", "model", "tool"}.issubset(node_types)
    assert {"contains", "mentions", "uses_model", "uses_tool", "tracks_task", "references_file"}.issubset(edge_types)
    assert graph["summary"]["conceptCount"] >= 1
    assert graph["displayContract"]["rawConversationContentVisibleByDefault"] is False
    assert all("mecanique quantique" not in item["label"].lower() for item in chat_nodes)
    assert graph["sideEffects"]["modelLoad"] is False
    assert graph["sideEffects"]["generation"] is False
    assert graph["sideEffects"]["snapshotWrite"] is False


def test_context_graph_endpoint_stores_project_snapshot_and_audit():
    seed_accounts()
    now_ms = int(time.time() * 1000)
    studio_db_storage.upsert_chat_project(
        {
            "id": "project-graph",
            "name": "Graph Projet",
            "instructions": "Relier documents, decisions et outils.",
            "archived": False,
            "createdAt": now_ms,
            "updatedAt": now_ms,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-graph",
            "title": "Discussion graph",
            "modelType": "local",
            "modelId": "qwen-local",
            "projectId": "project-graph",
            "archived": False,
            "createdAt": now_ms,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_message(
        {
            "id": "msg-graph-1",
            "threadId": "thread-graph",
            "role": "user",
            "content": [{"type": "text", "text": "Creer un graph de contexte pour PDF, RAG et decisions."}],
            "createdAt": now_ms,
        }
    )

    body = run_async(
        cognix_routes.build_context_graph(
            cognix_routes.ContextGraphBuildRequest(
                projectId = "project-graph",
                documents = [{"id": "doc_1", "name": "roadmap.pdf", "summary": "RAG, tools et decisions"}],
                files = ["roadmap.md"],
                decisions = ["Garder le graph dans le code source natif."],
                tasks = ["Afficher le graph dans un onglet projet plus tard."],
                models = ["qwen-local"],
                tools = ["rag-indexer"],
                includeProjectThreads = True,
                storeSnapshot = True,
            ),
            current_subject = "alice",
        )
    )
    snapshot = body["snapshot"]
    stored = cognix_db.get_context_graph_snapshot("alice", snapshot["id"])
    listed = run_async(cognix_routes.context_graph_snapshots(project_id = "project-graph", current_subject = "alice"))
    bob_listed = run_async(cognix_routes.context_graph_snapshots(current_subject = "bob"))

    assert body["auditLogId"].startswith("aud_")
    assert body["contextGraph"]["summary"]["nodeCount"] == snapshot["nodeCount"]
    assert body["contextGraph"]["summary"]["edgeCount"] == snapshot["edgeCount"]
    assert body["sideEffects"]["snapshotWrite"] is True
    assert body["sideEffects"]["generation"] is False
    assert stored is not None
    assert stored["node_count"] == snapshot["nodeCount"]
    assert len(stored["nodes"]) == snapshot["nodeCount"]
    assert len(stored["edges"]) == snapshot["edgeCount"]
    assert len(listed["snapshots"]) == 1
    assert bob_listed["snapshots"] == []

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "context_graph_built"
    assert log["metadata"]["contextGraphVersion"] == "cognix_context_graph_v1"
    assert log["metadata"]["sideEffects"]["generation"] is False
    assert log["metadata"]["sideEffects"]["snapshotWrite"] is True


def test_skill_memory_blueprint_declares_user_control_and_no_auto_approval():
    blueprint = cognix_skill_memory.build_skill_memory_blueprint()

    assert blueprint["skillMemoryVersion"] == "cognix_skill_memory_v1"
    assert blueprint["preferenceExtractorVersion"] == "cognix_preference_extractor_v1"
    assert blueprint["memoryApprovalVersion"] == "cognix_memory_approval_v1"
    assert blueprint["contextInjectorVersion"] == "cognix_context_injector_v1"
    assert blueprint["userControls"]["view"] is True
    assert blueprint["userControls"]["edit"] is True
    assert blueprint["userControls"]["delete"] is True
    assert blueprint["userControls"]["disable"] is True
    assert blueprint["userControls"]["export"] is True
    assert blueprint["userControls"]["approveBeforeActivation"] is True
    assert blueprint["privacyPolicy"]["automaticApprovalAllowed"] is False
    assert blueprint["sideEffects"]["memoryCandidateWrite"] is False
    assert blueprint["sideEffects"]["skillMemoryWrite"] is False
    assert blueprint["sideEffects"]["preferenceWrite"] is False
    assert blueprint["sideEffects"]["contextInjection"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_skill_memory_candidate_plan_extracts_preferences_without_writes():
    plan = cognix_skill_memory.build_candidate_memory_plan(
        username = "alice",
        observations = [
            (
                "Kamil prefere Python pour prototyper, solutions locales, "
                "architectures modulaires, securite, et veut devenir ingenieur IA."
            )
        ],
        project_type = "ai",
    )
    candidates = {item["candidateKey"]: item for item in plan["candidates"]}

    assert plan["mode"] == "candidate_memory_dry_run"
    assert {"python_prototyping", "local_first", "modular_architecture", "ai_engineering_goal", "security_first"}.issubset(
        candidates
    )
    assert candidates["python_prototyping"]["candidateType"] == "preference"
    assert candidates["python_prototyping"]["requiresUserApproval"] is True
    assert candidates["python_prototyping"]["canAutoApprove"] is False
    assert plan["summary"]["automaticApprovalCount"] == 0
    assert plan["sideEffects"]["memoryCandidateWrite"] is False
    assert plan["sideEffects"]["skillMemoryWrite"] is False
    assert plan["sideEffects"]["contextInjection"] is False
    assert plan["sideEffects"]["generation"] is False


def test_skill_memory_candidate_endpoint_approves_updates_exports_and_deletes():
    seed_accounts()

    body = run_async(
        cognix_routes.skill_memory_candidates(
            cognix_routes.SkillMemoryCandidateRequest(
                observations = [
                    (
                        "Je prefere Python pour prototyper et les solutions locales. "
                        "Je veux aussi une architecture modulaire et securisee."
                    )
                ],
                storeCandidates = True,
            ),
            current_subject = "alice",
        )
    )
    stored = body["storedCandidates"]
    python_candidate = next(item for item in stored if item["candidateKey"] == "python_prototyping")
    bob_candidates = run_async(cognix_routes.list_skill_memory_candidates(current_subject = "bob"))

    assert body["auditLogId"].startswith("aud_")
    assert body["sideEffects"]["memoryCandidateWrite"] is True
    assert body["sideEffects"]["generation"] is False
    assert bob_candidates["candidates"] == []

    approved = run_async(
        cognix_routes.approve_skill_memory_candidate(
            python_candidate["id"],
            cognix_routes.SkillMemoryDecisionRequest(value = "Kamil prefere Python pour les prototypes rapides."),
            current_subject = "alice",
        )
    )
    memory_id = approved["memory"]["id"]

    assert memory_id.startswith("smem_")
    assert approved["memory"]["status"] == "active"
    assert approved["sideEffects"]["skillMemoryWrite"] is True
    assert approved["sideEffects"]["preferenceWrite"] is True
    assert any(item["preferenceKey"] == "python_prototyping" for item in approved["preferences"])

    listed = run_async(cognix_routes.list_skill_memories(current_subject = "alice"))
    assert [item["id"] for item in listed["skillMemories"]] == [memory_id]

    updated = run_async(
        cognix_routes.update_skill_memory(
            memory_id,
            cognix_routes.SkillMemoryUpdateRequest(
                status = "disabled",
                value = "Kamil prefere Python, mais la memoire est desactivee pour ce test.",
            ),
            current_subject = "alice",
        )
    )
    active_after_disable = run_async(cognix_routes.list_skill_memories(current_subject = "alice"))
    export = run_async(cognix_routes.export_skill_memories(current_subject = "alice"))
    deleted = run_async(cognix_routes.delete_skill_memory(memory_id, current_subject = "alice"))
    after_delete = run_async(cognix_routes.list_skill_memories(include_disabled = True, current_subject = "alice"))

    assert updated["memory"]["status"] == "disabled"
    assert active_after_disable["skillMemories"] == []
    assert any(item["id"] == memory_id for item in export["memoryExport"]["skillMemories"])
    assert deleted["deleted"] is True
    assert deleted["sideEffects"]["generation"] is False
    assert after_delete["skillMemories"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {
        "skill_memory_candidates_built",
        "skill_memory_candidate_approved",
        "skill_memory_updated",
        "skill_memory_exported",
        "skill_memory_deleted",
    }.issubset(actions)


def test_skill_memory_injection_plan_selects_active_relevant_memories_without_injecting():
    seed_accounts()
    body = run_async(
        cognix_routes.skill_memory_candidates(
            cognix_routes.SkillMemoryCandidateRequest(
                observations = ["Kamil prefere Python pour prototyper des outils IA locaux."],
                storeCandidates = True,
            ),
            current_subject = "alice",
        )
    )
    candidate_id = next(item["id"] for item in body["storedCandidates"] if item["candidateKey"] == "python_prototyping")
    approved = run_async(
        cognix_routes.approve_skill_memory_candidate(
            candidate_id,
            cognix_routes.SkillMemoryDecisionRequest(),
            current_subject = "alice",
        )
    )
    plan_body = run_async(
        cognix_routes.skill_memory_injection_plan(
            cognix_routes.SkillMemoryInjectionPlanRequest(objective = "Construire un prototype Python local"),
            current_subject = "alice",
        )
    )
    plan = plan_body["injectionPlan"]

    assert approved["memory"]["id"] in plan["selectedMemoryIds"]
    assert plan["summary"]["willInjectNow"] is False
    assert plan_body["sideEffects"]["contextInjection"] is False
    assert plan_body["sideEffects"]["generation"] is False
    assert plan_body["auditLogId"].startswith("aud_")

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "skill_memory_injection_plan_built"


def test_personal_twin_builds_user_controlled_profile_without_autonomy():
    plan = cognix_personal_twin.build_personal_twin_profile_plan(
        username = "alice",
        interactions = [
            (
                "Reponds en francais, continue de maniere autonome, et fais les changements "
                "dans le code source natif. Je veux que CogniX garde la securite et Github."
            ),
            {"message": "Ne fais pas une surcouche, les modifications doivent etre permanentes."},
        ],
        activate = True,
    )
    blueprint = cognix_personal_twin.build_personal_twin_blueprint()
    style_values = {item["styleKey"]: item["styleValue"] for item in plan["profile"]["styleProfiles"]}
    rule_keys = {item["ruleKey"] for item in plan["profile"]["preferenceRules"]}

    assert blueprint["services"] == [
        "PersonalTwinService",
        "StyleProfiler",
        "PreferenceModel",
        "PersonalizationEngine",
    ]
    assert blueprint["userControls"]["activate"] is True
    assert blueprint["userControls"]["deactivate"] is True
    assert blueprint["userControls"]["export"] is True
    assert blueprint["userControls"]["reset"] is True
    assert blueprint["safetyPolicy"]["autonomousCloneAllowed"] is False
    assert style_values["language_preference"] == "fr"
    assert style_values["work_method"] == "autonomous_native_execution"
    assert style_values["coding_style"] in {"native_source_changes", "security_first_native_changes"}
    assert {"reply_language_fr", "autonomous_native_work", "native_source_only", "security_first", "git_preservation"}.issubset(
        rule_keys
    )
    assert plan["personalizationLayer"]["requiresUserActivation"] is True
    assert plan["personalizationLayer"]["willInjectNow"] is False
    assert plan["sideEffects"]["autonomousAction"] is False
    assert plan["sideEffects"]["toolExecution"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["generation"] is False


def test_personal_twin_endpoint_stores_activates_exports_and_resets():
    seed_accounts()

    body = run_async(
        cognix_routes.personal_twin_profile_plan(
            cognix_routes.PersonalTwinProfilePlanRequest(
                interactions = [
                    "Je veux CogniX en francais, autonome, natif dans le code source, avec securite.",
                    {"content": "Github doit servir de checkpoint permanent."},
                ],
                activate = True,
                storeProfile = True,
            ),
            current_subject = "alice",
        )
    )
    profile = body["profile"]
    listed = run_async(cognix_routes.personal_twin_profile(current_subject = "alice"))
    injection = run_async(
        cognix_routes.personal_twin_injection_plan(
            cognix_routes.PersonalTwinInjectionPlanRequest(objective = "Modifier le code source CogniX"),
            current_subject = "alice",
        )
    )
    exported = run_async(cognix_routes.personal_twin_export(current_subject = "alice"))
    disabled = run_async(
        cognix_routes.personal_twin_profile_status(
            cognix_routes.PersonalTwinStatusRequest(status = "disabled"),
            current_subject = "alice",
        )
    )
    reset = run_async(
        cognix_routes.personal_twin_profile_status(
            cognix_routes.PersonalTwinStatusRequest(status = "reset"),
            current_subject = "alice",
        )
    )
    bob_profile = run_async(cognix_routes.personal_twin_profile(current_subject = "bob"))

    assert body["auditLogId"].startswith("aud_")
    assert profile["id"].startswith("ptwin_")
    assert profile["status"] == "active"
    assert body["sideEffects"]["profileWrite"] is True
    assert body["sideEffects"]["styleProfileWrite"] is True
    assert body["sideEffects"]["ruleWrite"] is True
    assert body["sideEffects"]["autonomousAction"] is False
    assert body["sideEffects"]["generation"] is False
    assert listed["profile"]["id"] == profile["id"]
    assert listed["profile"]["status"] == "active"
    assert injection["injectionPlan"]["safeToInject"] is True
    assert injection["injectionPlan"]["willInjectNow"] is False
    assert injection["sideEffects"]["contextInjection"] is False
    assert injection["sideEffects"]["modelLoad"] is False
    assert exported["profileExport"]["schemaVersion"] == "cognix_personal_ai_profile_export_v1"
    assert exported["profileExport"]["profile"]["id"] == profile["id"]
    assert disabled["profile"]["status"] == "disabled"
    assert all(item["status"] == "disabled" for item in disabled["profile"]["personalizationRules"])
    assert reset["profile"]["status"] == "reset"
    assert reset["profile"]["styleProfiles"] == []
    assert reset["profile"]["personalizationRules"] == []
    assert bob_profile["profile"] is None

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {
        "personal_twin_profile_planned",
        "personal_twin_injection_plan_built",
        "personal_twin_exported",
        "personal_twin_status_updated",
    }.issubset(actions)


def test_live_memory_editor_blueprint_declares_versioned_user_controls():
    blueprint = cognix_memory_editor.build_memory_editor_blueprint()

    assert blueprint["memoryEditorVersion"] == "cognix_live_memory_editor_v1"
    assert blueprint["memoryVersioningVersion"] == "cognix_memory_versioning_v1"
    assert blueprint["memorySearchVersion"] == "cognix_memory_search_v1"
    assert blueprint["services"] == ["MemoryEditorService", "MemoryVersioning", "MemorySearch"]
    assert blueprint["userControls"]["view"] is True
    assert blueprint["userControls"]["edit"] is True
    assert blueprint["userControls"]["delete"] is True
    assert blueprint["userControls"]["merge"] is True
    assert blueprint["userControls"]["disable"] is True
    assert blueprint["userControls"]["export"] is True
    assert blueprint["versioningPolicy"]["newVersionOnEdit"] is True
    assert blueprint["versioningPolicy"]["auditEveryMutation"] is True
    assert blueprint["versioningPolicy"]["softDeleteKeepsAudit"] is True
    assert blueprint["sensitiveMemoryPolicy"]["noSensitiveMemoryWithoutControl"] is True
    assert blueprint["sideEffects"]["memoryWrite"] is False
    assert blueprint["sideEffects"]["versionWrite"] is False
    assert blueprint["sideEffects"]["auditWrite"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_live_memory_item_plan_blocks_sensitive_memory_without_control():
    blocked = cognix_memory_editor.build_memory_item_plan(
        username = "alice",
        title = "Secret",
        content = "Memoire sensible",
        category = "competence",
        sensitive = True,
        confirmed_sensitive_control = False,
    )
    allowed = cognix_memory_editor.build_memory_item_plan(
        username = "alice",
        title = "Secret",
        content = "Memoire sensible",
        category = "competence",
        sensitive = True,
        confirmed_sensitive_control = True,
    )

    assert blocked["policy"]["blocked"] is True
    assert blocked["memory"]["category"] == "skill"
    assert allowed["policy"]["blocked"] is False
    assert allowed["memory"]["sensitive"] is True


def test_live_memory_editor_endpoint_versions_searches_exports_and_deletes():
    seed_accounts()

    with pytest.raises(HTTPException) as sensitive_error:
        run_async(
            cognix_routes.create_live_memory_item(
                cognix_routes.LiveMemoryCreateRequest(
                    title = "Token prive",
                    content = "Ne pas enregistrer sans controle explicite.",
                    sensitive = True,
                ),
                current_subject = "alice",
            )
        )
    assert sensitive_error.value.status_code == 400

    created = run_async(
        cognix_routes.create_live_memory_item(
            cognix_routes.LiveMemoryCreateRequest(
                title = "Style de travail",
                content = "Kamil prefere des changements natifs et permanents dans CogniX.",
                category = "preference",
                metadata = {"tag": "native"},
            ),
            current_subject = "alice",
        )
    )
    memory_id = created["memory"]["id"]
    bob_list = run_async(cognix_routes.list_live_memory_items(current_subject = "bob"))

    assert memory_id.startswith("mem_")
    assert created["memory"]["currentVersion"] == 1
    assert created["memory"]["versions"][0]["versionNumber"] == 1
    assert created["sideEffects"]["memoryWrite"] is True
    assert created["sideEffects"]["versionWrite"] is True
    assert created["sideEffects"]["generation"] is False
    assert bob_list["items"] == []

    updated = run_async(
        cognix_routes.update_live_memory_item(
            memory_id,
            cognix_routes.LiveMemoryUpdateRequest(
                content = "Kamil prefere des changements natifs, permanents, audites et testables.",
                category = "organization",
                reason = "precision utilisateur",
            ),
            current_subject = "alice",
        )
    )
    listed = run_async(
        cognix_routes.list_live_memory_items(
            query = "audites",
            category = "organization",
            current_subject = "alice",
        )
    )
    disabled = run_async(
        cognix_routes.disable_live_memory_item(
            memory_id,
            cognix_routes.LiveMemoryStatusRequest(reason = "test disable"),
            current_subject = "alice",
        )
    )
    active_after_disable = run_async(cognix_routes.list_live_memory_items(current_subject = "alice"))
    disabled_list = run_async(
        cognix_routes.list_live_memory_items(include_disabled = True, current_subject = "alice")
    )
    exported = run_async(cognix_routes.export_live_memory_items(current_subject = "alice"))
    audit_logs = run_async(cognix_routes.list_live_memory_audit_logs(current_subject = "alice"))
    deleted = run_async(cognix_routes.delete_live_memory_item(memory_id, current_subject = "alice"))
    after_delete = run_async(
        cognix_routes.list_live_memory_items(include_disabled = True, current_subject = "alice")
    )

    assert updated["memory"]["currentVersion"] == 2
    assert updated["memory"]["versions"][0]["versionNumber"] == 2
    assert updated["memoryEditPlan"]["changes"] == ["content", "category"]
    assert [item["id"] for item in listed["items"]] == [memory_id]
    assert disabled["memory"]["status"] == "disabled"
    assert disabled["memory"]["currentVersion"] == 3
    assert active_after_disable["items"] == []
    assert [item["id"] for item in disabled_list["items"]] == [memory_id]
    assert any(item["id"] == memory_id for item in exported["memoryExport"]["memories"])
    assert any(item["memoryId"] == memory_id for item in exported["memoryExport"]["versions"])
    assert any(item["memoryId"] == memory_id for item in exported["memoryExport"]["auditLogs"])
    assert any(item["action"] == "memory_disabled" for item in audit_logs["auditLogs"])
    assert deleted["deleted"] is True
    assert deleted["memory"]["status"] == "deleted"
    assert after_delete["items"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {
        "live_memory_created",
        "live_memory_updated",
        "live_memory_disabled",
        "live_memory_exported",
        "live_memory_deleted",
    }.issubset(actions)


def test_live_memory_merge_creates_new_memory_and_can_disable_sources():
    seed_accounts()
    first = run_async(
        cognix_routes.create_live_memory_item(
            cognix_routes.LiveMemoryCreateRequest(
                title = "Preference code",
                content = "Kamil veut des modules natifs.",
                category = "preference",
            ),
            current_subject = "alice",
        )
    )
    second = run_async(
        cognix_routes.create_live_memory_item(
            cognix_routes.LiveMemoryCreateRequest(
                title = "Preference test",
                content = "Kamil veut des tests avant de pousser.",
                category = "preference",
            ),
            current_subject = "alice",
        )
    )
    source_ids = [first["memory"]["id"], second["memory"]["id"]]
    merged = run_async(
        cognix_routes.merge_live_memory_items(
            cognix_routes.LiveMemoryMergeRequest(
                sourceIds = source_ids,
                title = "Preferences CogniX",
                disableSources = True,
            ),
            current_subject = "alice",
        )
    )
    all_items = run_async(
        cognix_routes.list_live_memory_items(include_disabled = True, current_subject = "alice")
    )
    by_id = {item["id"]: item for item in all_items["items"]}

    assert merged["memory"]["id"].startswith("mem_")
    assert merged["memory"]["content"] == "Kamil veut des modules natifs.\n\nKamil veut des tests avant de pousser."
    assert merged["memory"]["metadata"]["mergedFrom"] == source_ids
    assert merged["memoryMergePlan"]["summary"]["sourceCount"] == 2
    assert merged["sideEffects"]["generation"] is False
    assert by_id[source_ids[0]]["status"] == "disabled"
    assert by_id[source_ids[1]]["status"] == "disabled"

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert "live_memory_merged" in {item["action"] for item in logs}


def test_workflow_recorder_blueprint_declares_no_execution_contract():
    blueprint = cognix_workflow_recorder.build_workflow_blueprint()

    assert blueprint["workflowRecorderVersion"] == "cognix_workflow_recorder_v1"
    assert blueprint["workflowRunnerVersion"] == "cognix_workflow_runner_v1"
    assert blueprint["workflowTemplateManagerVersion"] == "cognix_workflow_template_manager_v1"
    assert blueprint["userControls"]["record"] is True
    assert blueprint["userControls"]["replay"] is True
    assert blueprint["userControls"]["edit"] is True
    assert blueprint["userControls"]["share"] is True
    assert blueprint["userControls"]["export"] is True
    assert blueprint["runnerPolicy"]["dryRunByDefault"] is True
    assert blueprint["runnerPolicy"]["executeWithoutUserConfirmation"] is False
    assert blueprint["runnerPolicy"]["frontendDirectToolExecutionAllowed"] is False
    assert blueprint["runnerPolicy"]["frontendDirectModelCallAllowed"] is False
    assert blueprint["sideEffects"]["workflowWrite"] is False
    assert blueprint["sideEffects"]["workflowRunWrite"] is False
    assert blueprint["sideEffects"]["toolExecution"] is False
    assert blueprint["sideEffects"]["modelLoad"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_workflow_templates_cover_rag_fine_tuning_code_and_document():
    registry = cognix_workflow_recorder.build_workflow_template_registry()
    templates = {item["workflowType"]: item for item in registry["templates"]}

    assert registry["workflowTemplateManagerVersion"] == "cognix_workflow_template_manager_v1"
    assert {"rag", "fine_tuning", "code", "document"}.issubset(templates)
    assert any(step["stepType"] == "tool_call" for step in templates["rag"]["steps"])
    assert any(step["stepType"] == "model_call" for step in templates["fine_tuning"]["steps"])
    assert any(step["stepType"] == "tool_call" for step in templates["code"]["steps"])
    assert any(step["stepType"] == "export" for step in templates["document"]["steps"])
    assert registry["sideEffects"]["toolExecution"] is False
    assert registry["sideEffects"]["generation"] is False


def test_workflow_record_endpoint_stores_steps_and_run_plan_without_execution():
    seed_accounts()

    body = run_async(
        cognix_routes.record_workflow(
            cognix_routes.WorkflowRecordRequest(
                title = "Pipeline PDF vers fiche",
                objective = "Importer PDF, indexer, resumer, extraire QCM et exporter.",
                workflowType = "rag",
                steps = [
                    {"stepType": "user_action", "label": "Importer PDF", "parameters": {"kind": "pdf"}},
                    {"stepType": "tool_call", "label": "Indexer", "toolName": "rag-indexer"},
                    {"stepType": "model_call", "label": "Resumer", "modelId": "cognix-general-small"},
                    {"stepType": "export", "label": "Exporter fiche"},
                ],
                storeWorkflow = True,
            ),
            current_subject = "alice",
        )
    )
    workflow = body["workflow"]
    workflow_id = workflow["id"]
    bob_workflows = run_async(cognix_routes.list_workflows(current_subject = "bob"))
    fetched = run_async(cognix_routes.get_workflow(workflow_id, current_subject = "alice"))["workflow"]
    run_body = run_async(
        cognix_routes.workflow_run_plan(
            workflow_id,
            cognix_routes.WorkflowRunPlanRequest(runMode = "dry_run", inputs = {"document": "cours.pdf"}),
            current_subject = "alice",
        )
    )
    runs = run_async(cognix_routes.workflow_runs(workflow_id, current_subject = "alice"))

    assert body["auditLogId"].startswith("aud_")
    assert body["sideEffects"]["workflowWrite"] is True
    assert body["sideEffects"]["toolExecution"] is False
    assert workflow["workflowType"] == "rag"
    assert fetched["stepCount"] == 4
    assert fetched["steps"][1]["toolName"] == "rag-indexer"
    assert bob_workflows["workflows"] == []
    assert run_body["run"]["id"].startswith("wrun_")
    assert run_body["runPlan"]["summary"]["willExecuteNow"] is False
    assert run_body["runPlan"]["orderedSteps"][1]["willExecuteNow"] is False
    assert run_body["sideEffects"]["workflowRunWrite"] is True
    assert run_body["sideEffects"]["toolExecution"] is False
    assert run_body["sideEffects"]["generation"] is False
    assert len(run_body["run"]["logs"]) == 4
    assert len(runs["runs"]) == 1

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert "workflow_run_plan_built" in actions


def test_workflow_update_export_and_delete_are_user_scoped_and_audited():
    seed_accounts()
    created = run_async(
        cognix_routes.record_workflow(
            cognix_routes.WorkflowRecordRequest(
                title = "Workflow code",
                workflowType = "code",
                storeWorkflow = True,
            ),
            current_subject = "alice",
        )
    )
    workflow_id = created["workflow"]["id"]

    updated = run_async(
        cognix_routes.update_workflow(
            workflow_id,
            cognix_routes.WorkflowUpdateRequest(title = "Workflow code partage", shareStatus = "shared"),
            current_subject = "alice",
        )
    )
    export = run_async(cognix_routes.export_workflow(workflow_id, current_subject = "alice"))
    deleted = run_async(cognix_routes.delete_workflow(workflow_id, current_subject = "alice"))
    after_delete = run_async(cognix_routes.list_workflows(include_disabled = True, current_subject = "alice"))

    assert updated["workflow"]["title"] == "Workflow code partage"
    assert updated["workflow"]["shareStatus"] == "shared"
    assert export["workflowExport"]["workflow"]["id"] == workflow_id
    assert export["sideEffects"]["toolExecution"] is False
    assert deleted["deleted"] is True
    assert deleted["sideEffects"]["generation"] is False
    assert after_delete["workflows"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {
        "workflow_recording_built",
        "workflow_updated",
        "workflow_exported",
        "workflow_deleted",
    }.issubset(actions)


def test_prompt_compression_blueprint_declares_badge_and_no_generation():
    blueprint = cognix_prompt_compression.build_prompt_compression_blueprint()

    assert blueprint["promptCompressionVersion"] == "cognix_prompt_compression_v1"
    assert blueprint["contextRankerVersion"] == "cognix_context_ranker_v1"
    assert blueprint["compressionEvaluatorVersion"] == "cognix_compression_evaluator_v1"
    assert blueprint["display"]["badge"] == "Context optimized"
    assert blueprint["display"]["badgeOnly"] is True
    assert blueprint["policies"]["modelGenerationAllowed"] is False
    assert blueprint["policies"]["frontendDirectCompressionWriteAllowed"] is False
    assert blueprint["sideEffects"]["compressionWrite"] is False
    assert blueprint["sideEffects"]["logWrite"] is False
    assert blueprint["sideEffects"]["modelLoad"] is False
    assert blueprint["sideEffects"]["generation"] is False
    assert blueprint["sideEffects"]["promptMutation"] is False


def test_prompt_compression_plan_reduces_tokens_and_preserves_objective_terms():
    context = " ".join(
        [
            "Le projet RAG PDF doit indexer les documents et garder les citations.",
            "Il faut extraire des QCM et une fiche de revision claire.",
            "Phrase de bruit sur une preference visuelle sans lien direct.",
            "Autre detail peu important sur la couleur de fond.",
        ]
        * 25
    )
    plan = cognix_prompt_compression.build_prompt_compression_plan(
        username = "alice",
        context = context,
        objective = "RAG PDF QCM citations",
        target_tokens = 90,
    )

    assert plan["promptCompressionVersion"] == "cognix_prompt_compression_v1"
    assert plan["summary"]["compressedTokenCount"] < plan["summary"]["originalTokenCount"]
    assert plan["summary"]["reductionRatio"] > 0
    assert plan["summary"]["badge"] == "Context optimized"
    assert plan["evaluation"]["retainedObjectiveRatio"] >= 0.45
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["promptMutation"] is False


def test_conversation_summary_plan_caps_recent_messages_and_redacts_secrets_without_generation():
    messages = [
        {"role": "user", "content": "Objectif important: construire un RAG PDF cite avec QCM."},
        {"role": "assistant", "content": "Decision: garder les citations et ne jamais inventer de source."},
        {"role": "user", "content": "token=sk-1234567890abcdef ne doit jamais etre reutilise."},
        {"role": "assistant", "content": "Todo: ajouter des tests backend pour le Context Manager."},
        {"role": "user", "content": "Detail secondaire sur la couleur sans importance."},
        {"role": "assistant", "content": "Le contexte projet doit rester concis."},
        {"role": "user", "content": "Derniere question: comment lancer le plan ?"},
        {"role": "assistant", "content": "Reponse recente a garder comme extrait seulement."},
    ]
    plan = cognix_prompt_compression.build_conversation_summary_plan(
        username = "alice",
        messages = messages,
        objective = "RAG PDF citations QCM tests",
        target_tokens = 90,
        recent_message_limit = 2,
        project_id = "project-rag",
    )

    assert plan["conversationSummaryContractVersion"] == "cognix_conversation_summary_contract_v1"
    assert plan["mode"] == "conversation_summary_plan"
    assert plan["summary"]["messageCount"] == 8
    assert plan["summary"]["summarizedMessageCount"] == 6
    assert plan["summary"]["retainedRecentMessageCount"] == 2
    assert plan["summary"]["rawHistoryIncluded"] is False
    assert plan["conversationSummary"]["readyForContextInjection"] is True
    assert plan["boundaryContract"]["rawHistoryAllowed"] is False
    assert plan["boundaryContract"]["fullConversationHistoryAllowed"] is False
    assert plan["boundaryContract"]["recentMessagesCapped"] is True
    assert "secret_value" in plan["conversationSummary"]["redactionMarkers"]
    assert "sk-1234567890abcdef" not in plan["compressedContext"]
    assert all(item["rawContentIncluded"] is False for item in plan["recentMessages"])
    assert plan["sideEffects"]["generation"] is False
    assert plan["sideEffects"]["promptMutation"] is False
    assert plan["sideEffects"]["networkCall"] is False


def test_prompt_compression_endpoint_stores_lists_deletes_and_audits():
    seed_accounts()
    context = " ".join(
        [
            "Objectif important: compresser un contexte RAG PDF avec citations et QCM.",
            "Decision: garder les sources, les tests et les contraintes de securite.",
            "Bruit: phrase secondaire sans impact sur la reponse finale.",
        ]
        * 30
    )
    body = run_async(
        cognix_routes.prompt_compression_plan(
            cognix_routes.PromptCompressionRequest(
                context = context,
                objective = "RAG PDF citations QCM securite",
                targetTokens = 120,
                storeContext = True,
            ),
            current_subject = "alice",
        )
    )
    context_id = body["compressedContext"]["id"]
    listed = run_async(cognix_routes.list_compressed_contexts(current_subject = "alice"))
    bob_listed = run_async(cognix_routes.list_compressed_contexts(current_subject = "bob"))
    fetched = run_async(cognix_routes.get_compressed_context(context_id, current_subject = "alice"))
    deleted = run_async(cognix_routes.delete_compressed_context(context_id, current_subject = "alice"))
    after_delete = run_async(cognix_routes.list_compressed_contexts(current_subject = "alice"))

    assert body["auditLogId"].startswith("aud_")
    assert body["sideEffects"]["compressionWrite"] is True
    assert body["sideEffects"]["generation"] is False
    assert context_id.startswith("cctx_")
    assert listed["contexts"][0]["id"] == context_id
    assert bob_listed["contexts"] == []
    assert fetched["compressedContext"]["logs"][0]["eventType"] == "compression_plan_stored"
    assert deleted["deleted"] is True
    assert deleted["sideEffects"]["promptMutation"] is False
    assert after_delete["contexts"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {"prompt_compression_plan_built", "prompt_compression_context_deleted"}.issubset(actions)


def test_conversation_summary_endpoint_stores_redacted_summary_and_audits():
    seed_accounts()
    messages = [
        {"role": "user", "content": "Objectif: indexer mes PDF et garder les citations."},
        {"role": "assistant", "content": "Decision: RAG avant fine-tuning."},
        {"role": "user", "content": "api_key=sk-1234567890abcdef doit rester secret."},
        {"role": "assistant", "content": "Todo: ajouter evaluation avant bibliotheque."},
        {"role": "user", "content": "Message recent 1."},
        {"role": "assistant", "content": "Message recent 2."},
    ]

    body = run_async(
        cognix_routes.conversation_summary_plan(
            cognix_routes.ConversationSummaryPlanRequest(
                messages = messages,
                objective = "PDF citations RAG evaluation",
                targetTokens = 80,
                recentMessageLimit = 2,
                storeContext = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["conversationSummaryPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_conversation_summary_contract_v1"
    assert body["compressedContext"]["id"].startswith("cctx_")
    assert body["compressedContext"]["compressed_context"] == plan["compressedContext"]
    assert "sk-1234567890abcdef" not in body["compressedContext"]["compressed_context"]
    assert plan["summary"]["rawHistoryIncluded"] is False
    assert body["sideEffects"]["compressionWrite"] is True
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["promptMutation"] is False

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    log = logs[0]
    assert log["action"] == "conversation_summary_plan_built"
    assert log["metadata"]["rawHistoryIncluded"] is False
    assert log["metadata"]["redactionCount"] >= 1


def test_semantic_cache_plan_builds_privacy_safe_lookup_contract_without_cache_io():
    plan = cognix_semantic_cache.build_semantic_cache_plan(
        username = "alice",
        prompt = "Explique le RAG PDF avec citations et une fiche de revision QCM.",
        project_id = "project-rag",
        project_type = "education",
        task_type = "education",
        model_id = "cognix-education-3b-q4",
        requires_sources = True,
        context_hashes = ["ctx_a", "ctx_b"],
    )

    assert plan["semanticCacheVersion"] == "cognix_semantic_cache_v1"
    assert plan["policyVersion"] == "cognix_semantic_cache_policy_v1"
    assert plan["reuseContract"]["contractVersion"] == "cognix_semantic_reuse_contract_v1"
    assert plan["scope"]["crossUserReuseAllowed"] is False
    assert plan["cacheKeyPlan"]["rawPromptStoredInKey"] is False
    assert plan["cacheKeyPlan"]["contextHashCount"] == 2
    assert plan["lookupPlan"]["readyForLookup"] is True
    assert plan["lookupPlan"]["willLookupNow"] is False
    assert plan["lookupPlan"]["embeddingGenerationAllowedHere"] is False
    assert plan["writePlan"]["writeEligibleAfterValidation"] is True
    assert plan["writePlan"]["willWriteNow"] is False
    assert plan["reuseContract"]["automaticReuseAllowed"] is False
    assert plan["reuseContract"]["requiresSourceRevalidation"] is True
    assert plan["sideEffects"]["cacheLookup"] is False
    assert plan["sideEffects"]["cacheWrite"] is False
    assert plan["sideEffects"]["embeddingGeneration"] is False
    assert plan["sideEffects"]["rawPromptStorage"] is False


def test_semantic_cache_plan_blocks_sensitive_prompts_without_raw_prompt_storage():
    plan = cognix_semantic_cache.build_semantic_cache_plan(
        username = "alice",
        prompt = "Resume ce token secret et mon mot de passe admin.",
        sensitivity_level = "confidential",
    )

    assert plan["sensitivity"]["level"] == "restricted"
    assert "secret" in plan["sensitivity"]["matchedSensitiveTermIds"]
    assert plan["lookupPlan"]["readyForLookup"] is False
    assert plan["writePlan"]["writeEligibleAfterValidation"] is False
    assert plan["reuseContract"]["nextRequiredGate"] == "sensitivity_review"
    assert "raw_prompt_storage" in plan["reuseContract"]["blockedActions"]
    assert plan["sideEffects"]["rawPromptStorage"] is False
    assert plan["sideEffects"]["crossUserRead"] is False


def test_semantic_cache_plan_endpoint_logs_sanitized_audit_without_cache_io():
    seed_accounts()

    body = run_async(
        cognix_routes.semantic_cache_plan(
            cognix_routes.SemanticCachePlanRequest(
                prompt = "Explique le RAG PDF avec citations et QCM.",
                projectType = "education",
                taskType = "education",
                modelId = "cognix-education-3b-q4",
                requiresSources = True,
                contextHashes = ["ctx_a"],
            ),
            current_subject = "alice",
        )
    )

    plan = body["semanticCachePlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_semantic_cache_v1"
    assert plan["lookupPlan"]["readyForLookup"] is True
    assert body["sideEffects"]["cacheLookup"] is False
    assert body["sideEffects"]["cacheWrite"] is False
    assert body["sideEffects"]["embeddingGeneration"] is False

    log = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "semantic_cache_plan_built"
    assert log["metadata"]["semanticCacheVersion"] == "cognix_semantic_cache_v1"
    assert log["metadata"]["requestSignature"] == plan["requestSignature"]
    assert log["metadata"]["sideEffects"]["cacheWrite"] is False
    assert "Explique le RAG" not in log["metadataJson"]
    assert "citations et QCM" not in log["metadataJson"]


def test_prompt_cache_plan_prepares_stable_prefix_without_runtime_mutation():
    plan = cognix_prompt_cache.build_prompt_cache_plan(
        username = "alice",
        objective = "Repondre avec le contexte projet deja stable.",
        runtime_adapter = {
            "runtimeType": "llama.cpp",
            "capabilities": {"promptCaching": True},
        },
        model = {"modelId": "cognix-code-4b"},
        prompt_segments = [
            {
                "id": "system",
                "type": "system",
                "content": "Regles CogniX stables et consignes projet. " * 50,
            },
            {
                "id": "project",
                "type": "project_summary",
                "content": "Resume projet stable avec decisions techniques. " * 45,
            },
            {
                "id": "request",
                "type": "user_message",
                "content": "Question actuelle qui ne doit pas etre mise en cache prefixe.",
            },
        ],
        expected_reuse_count = 4,
    )

    assert plan["promptCachePlanVersion"] == "cognix_prompt_cache_plan_v1"
    assert plan["policyVersion"] == "cognix_prompt_cache_policy_v1"
    assert plan["runtimeContract"]["contractVersion"] == "cognix_prompt_cache_runtime_contract_v1"
    assert plan["readyForExperiment"] is True
    assert plan["readyForActivation"] is False
    assert plan["runtime"]["promptCachingSupported"] is True
    assert plan["prefixPlan"]["stablePrefixTokens"] >= plan["policy"]["minStablePrefixTokens"]
    assert plan["prefixPlan"]["rawPrefixStoredInKey"] is False
    assert plan["policy"]["rawContentStored"] is False
    assert all(item["containsRawContent"] is False for item in plan["segments"])
    assert plan["segments"][0]["cacheAction"] == "cache_prefix"
    assert plan["segments"][-1]["cacheAction"] == "exclude_from_prompt_cache"
    assert plan["runtimeContract"]["runtimeFlagWriteAllowed"] is False
    assert plan["runtimeContract"]["cacheWriteAllowedHere"] is False
    assert plan["sideEffects"]["promptCacheWrite"] is False
    assert plan["sideEffects"]["runtimeConfigWrite"] is False
    assert plan["sideEffects"]["rawPromptStorage"] is False


def test_prompt_cache_plan_blocks_sensitive_prefix_without_raw_prompt_storage():
    plan = cognix_prompt_cache.build_prompt_cache_plan(
        username = "alice",
        objective = "Optimiser un prompt contenant un secret.",
        runtime_adapter = {
            "runtimeType": "vllm",
            "capabilities": {"promptCaching": True},
        },
        prompt_segments = [
            {
                "id": "system",
                "type": "system",
                "content": "api_key secret token " * 120,
            },
            {
                "id": "request",
                "type": "user_message",
                "content": "Question actuelle.",
            },
        ],
    )

    assert plan["sensitivity"]["level"] == "restricted"
    assert "secret" in plan["sensitivity"]["matchedSensitiveTermIds"]
    assert plan["readyForExperiment"] is False
    assert "privacy_scope_allows_prompt_cache" in plan["summary"]["blockedGateIds"]
    assert plan["runtimeContract"]["nextRequiredGate"] == "privacy_scope_allows_prompt_cache"
    assert "raw_prompt_storage" in plan["runtimeContract"]["blockedActions"]
    assert plan["policy"]["rawPromptStorageAllowed"] is False
    assert plan["sideEffects"]["rawPromptStorage"] is False


def test_prompt_cache_plan_endpoint_logs_sanitized_contract_without_cache_io():
    seed_accounts()

    body = run_async(
        cognix_routes.prompt_cache_plan(
            cognix_routes.PromptCachePlanRequest(
                objective = "Preparer un prefixe cacheable pour un projet Code.",
                runtimeAdapter = {
                    "runtimeType": "llama.cpp",
                    "capabilities": {"promptCaching": True},
                },
                promptSegments = [
                    {
                        "id": "system",
                        "type": "system",
                        "content": "Instructions stables CogniX pour le projet Code. " * 50,
                    },
                    {
                        "id": "project",
                        "type": "project_summary",
                        "content": "Decisions projet persistantes et contexte architecture. " * 45,
                    },
                    {
                        "id": "request",
                        "type": "user_message",
                        "content": "Nouvelle question non stockee dans le cache.",
                    },
                ],
                expectedReuseCount = 3,
            ),
            current_subject = "alice",
        )
    )

    plan = body["promptCachePlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_prompt_cache_plan_v1"
    assert plan["readyForExperiment"] is True
    assert body["sideEffects"]["promptCacheLookup"] is False
    assert body["sideEffects"]["promptCacheWrite"] is False
    assert body["sideEffects"]["runtimeConfigWrite"] is False

    log = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "prompt_cache_plan_built"
    assert log["metadata"]["promptCachePlanVersion"] == "cognix_prompt_cache_plan_v1"
    assert log["metadata"]["stablePrefixTokens"] == plan["prefixPlan"]["stablePrefixTokens"]
    assert log["metadata"]["sideEffects"]["promptCacheWrite"] is False
    assert "Instructions stables CogniX" not in log["metadataJson"]
    assert "Nouvelle question" not in log["metadataJson"]


def test_context_heatmap_scores_used_and_archive_candidates_without_generation():
    plan = cognix_context_heatmap.build_context_heatmap_plan(
        username = "alice",
        objective = "RAG PDF citations securite projet",
        context_chunks = [
            {
                "chunkId": "doc-a",
                "sourceType": "document",
                "sourceId": "doc-a.pdf",
                "title": "Document A",
                "text": "RAG PDF avec citations, securite et objectif projet.",
                "ageDays": 2,
            },
            {
                "chunkId": "old-chat",
                "sourceType": "old_message",
                "title": "Ancien message",
                "text": "Ancienne note visuelle sans rapport utile.",
                "ageDays": 90,
            },
            {
                "chunkId": "memory-project",
                "sourceType": "project_memory",
                "title": "Memoire projet",
                "text": "Memoire importante: garder les decisions RAG et les citations.",
                "ageDays": 8,
            },
        ],
        response_usage = [
            {"chunkId": "doc-a", "usageCount": 4, "responseCount": 3, "citationCount": 2},
            {"chunkId": "memory-project", "usageCount": 2, "responseCount": 2, "copiedTermCount": 3},
        ],
    )
    entries = {item["chunkId"]: item for item in plan["entries"]}

    assert plan["usageTrackerVersion"] == "cognix_context_usage_tracker_v1"
    assert plan["heatmapGeneratorVersion"] == "cognix_context_heatmap_generator_v1"
    assert plan["memoryGarbageCollectorVersion"] == "cognix_memory_garbage_collector_v1"
    assert entries["doc-a"]["bucket"] == "very_useful"
    assert entries["doc-a"]["label"] == "Contexte tres utile"
    assert entries["old-chat"]["bucket"] == "archive_candidate"
    assert entries["old-chat"]["recommendedAction"] == "archive"
    assert entries["memory-project"]["bucket"] in {"very_useful", "low_usage"}
    assert plan["garbageCollectorPlan"]["automaticArchiveAllowed"] is False
    assert plan["sideEffects"]["memoryArchive"] is False
    assert plan["sideEffects"]["memoryDelete"] is False
    assert plan["sideEffects"]["generation"] is False


def test_context_heatmap_endpoint_stores_entries_and_logs_audit():
    seed_accounts()
    body = run_async(
        cognix_routes.context_heatmap_plan(
            cognix_routes.ContextHeatmapPlanRequest(
                contextChunks = [
                    {
                        "chunkId": "doc-a",
                        "sourceType": "document",
                        "sourceId": "doc-a.pdf",
                        "title": "Document A",
                        "text": "Document tres utilise pour RAG, citations et securite.",
                        "ageDays": 1,
                    },
                    {
                        "chunkId": "old-chat",
                        "sourceType": "old_message",
                        "title": "Ancien message",
                        "text": "Message ancien sans usage recent.",
                        "ageDays": 120,
                    },
                ],
                responseUsage = [{"chunkId": "doc-a", "usageCount": 5, "responseCount": 4, "citationCount": 2}],
                objective = "RAG citations securite",
                storeHeatmap = True,
            ),
            current_subject = "alice",
        )
    )

    plan = body["contextHeatmapPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["sideEffects"]["usageStatsWrite"] is True
    assert body["sideEffects"]["heatmapEntryWrite"] is True
    assert body["sideEffects"]["memoryArchive"] is False
    assert body["sideEffects"]["generation"] is False
    assert plan["summary"]["chunkCount"] == 2
    assert body["storedHeatmapEntries"][0]["id"].startswith("ctxheat_")

    listed = run_async(cognix_routes.context_heatmap_entries(current_subject = "alice"))
    assert listed["entries"][0]["chunkId"] == "doc-a"
    assert listed["entries"][0]["bucket"] == "very_useful"
    assert listed["usageStats"][0]["usageCount"] == 5
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "context_heatmap_plan_built"
    assert log["metadata"]["heatmapGeneratorVersion"] == "cognix_context_heatmap_generator_v1"


def test_memory_cleanup_detects_duplicates_stale_and_conflicts_without_delete():
    plan = cognix_context_heatmap.build_memory_cleanup_plan(
        username = "alice",
        memories = [
            {
                "id": "mem-a",
                "title": "Reponse en francais",
                "content": "Toujours repondre en francais.",
                "preferenceKey": "language",
                "ageDays": 3,
                "usageCount": 5,
            },
            {
                "id": "mem-b",
                "title": "Reponse en francais copie",
                "content": "Toujours repondre en francais.",
                "preferenceKey": "language-copy",
                "ageDays": 2,
            },
            {
                "id": "mem-old",
                "title": "Ancien style",
                "content": "Ancienne preference jamais reutilisee.",
                "preferenceKey": "old-style",
                "ageDays": 140,
            },
            {
                "id": "mem-conflict",
                "title": "Langue",
                "content": "Toujours repondre en anglais.",
                "preferenceKey": "language",
                "ageDays": 1,
            },
        ],
    )
    reason_codes = {item["reasonCode"] for item in plan["suggestions"]}

    assert plan["memoryGarbageCollectorVersion"] == "cognix_memory_garbage_collector_v1"
    assert plan["memoryConflictResolverVersion"] == "cognix_memory_conflict_resolver_v1"
    assert "duplicate_memory" in reason_codes
    assert "stale_unused_memory" in reason_codes
    assert "conflicting_memory" in reason_codes
    assert plan["summary"]["conflictCount"] == 1
    assert plan["reviewPolicy"]["reviewBeforeDelete"] is True
    assert plan["reviewPolicy"]["permanentDeleteAllowedHere"] is False
    assert plan["sideEffects"]["memoryDelete"] is False
    assert plan["sideEffects"]["permanentDelete"] is False
    assert plan["sideEffects"]["generation"] is False


def test_memory_cleanup_endpoint_stores_suggestions_conflicts_and_audit():
    seed_accounts()
    body = run_async(
        cognix_routes.memory_cleanup_plan(
            cognix_routes.MemoryCleanupPlanRequest(
                memories = [
                    {
                        "id": "mem-a",
                        "title": "Ton",
                        "content": "Utiliser un ton concis.",
                        "preferenceKey": "tone",
                        "usageCount": 4,
                    },
                    {
                        "id": "mem-b",
                        "title": "Ton contradictoire",
                        "content": "Utiliser un ton tres detaille.",
                        "preferenceKey": "tone",
                    },
                    {
                        "id": "mem-old",
                        "title": "Ancienne note",
                        "content": "Note obsolete sans usage.",
                        "preferenceKey": "obsolete",
                        "ageDays": 180,
                    },
                ],
                storeSuggestions = True,
            ),
            current_subject = "alice",
        )
    )

    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_memory_garbage_collector_v1"
    assert body["sideEffects"]["suggestionWrite"] is True
    assert body["sideEffects"]["conflictWrite"] is True
    assert body["sideEffects"]["memoryDelete"] is False
    assert body["sideEffects"]["permanentDelete"] is False
    assert body["memoryCleanupPlan"]["summary"]["automaticCleanupWillRun"] is False
    assert body["storedSuggestions"][0]["id"].startswith("mcln_")
    assert body["storedConflicts"][0]["id"].startswith("mconf_")

    suggestions = run_async(cognix_routes.memory_cleanup_suggestions(current_subject = "alice"))
    conflicts = run_async(cognix_routes.memory_conflicts(current_subject = "alice"))
    assert suggestions["count"] >= 2
    assert conflicts["count"] == 1
    assert conflicts["conflicts"][0]["memoryIds"]

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "memory_cleanup_plan_built"
    assert log["metadata"]["sideEffects"]["memoryDelete"] is False
    assert log["metadata"]["sideEffects"]["permanentDelete"] is False


def test_intent_prediction_blueprint_declares_single_suggestion_and_no_preload():
    blueprint = cognix_intent_prediction.build_intent_prediction_blueprint()

    assert blueprint["intentPredictionVersion"] == "cognix_intent_prediction_v1"
    assert blueprint["preloadSchedulerVersion"] == "cognix_preload_scheduler_v1"
    assert blueprint["displayPolicy"]["mostlyInvisible"] is True
    assert blueprint["displayPolicy"]["maxSuggestions"] == 1
    assert blueprint["preloadPolicy"]["actualPreloadAllowedHere"] is False
    assert blueprint["sideEffects"]["predictionWrite"] is False
    assert blueprint["sideEffects"]["preloadEventWrite"] is False
    assert blueprint["sideEffects"]["modelLoad"] is False
    assert blueprint["sideEffects"]["modelUnload"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_intent_prediction_detects_code_maths_general_and_abrupt_domain_change():
    code = cognix_intent_prediction.build_intent_prediction(
        username = "alice",
        project_type = "code",
        draft_text = "corrige ce bug python et lance les tests",
    )
    maths = cognix_intent_prediction.build_intent_prediction(
        username = "alice",
        draft_text = "resous cette equation avec une integrale et une matrice",
    )
    general = cognix_intent_prediction.build_intent_prediction(
        username = "alice",
        draft_text = "bonjour peux-tu m'aider a organiser mes idees",
    )
    abrupt = cognix_intent_prediction.build_intent_prediction(
        username = "alice",
        project_type = "code",
        draft_text = "calcule cette derivee et resous cette equation matricielle",
    )

    assert code["selectedDomain"] == "code"
    assert code["suggestion"]["modelId"] == "cognix-code-local"
    assert code["preloadPlan"]["willPreloadNow"] is False
    assert maths["selectedDomain"] == "maths"
    assert general["summary"]["suggestionCount"] <= 1
    assert abrupt["selectedDomain"] == "maths"
    assert abrupt["summary"]["abruptDomainChange"] is True
    assert abrupt["sideEffects"]["modelLoad"] is False
    assert abrupt["sideEffects"]["generation"] is False


def test_intent_prediction_endpoint_stores_preload_event_without_loading():
    seed_accounts()
    body = run_async(
        cognix_routes.intent_predict(
            cognix_routes.IntentPredictionRequest(
                projectType = "code",
                draftText = "ajoute une route FastAPI et des tests python",
                storePrediction = True,
            ),
            current_subject = "alice",
        )
    )
    prediction_id = body["storedPrediction"]["id"]
    listed = run_async(cognix_routes.intent_predictions(current_subject = "alice"))
    events = run_async(cognix_routes.intent_preload_events(current_subject = "alice"))
    bob_listed = run_async(cognix_routes.intent_predictions(current_subject = "bob"))

    assert prediction_id.startswith("ipred_")
    assert body["intentPrediction"]["selectedDomain"] == "code"
    assert body["sideEffects"]["predictionWrite"] is True
    assert body["sideEffects"]["preloadEventWrite"] is True
    assert body["sideEffects"]["modelLoad"] is False
    assert body["sideEffects"]["generation"] is False
    assert listed["predictions"][0]["id"] == prediction_id
    assert events["events"][0]["status"] == "planned_no_execution"
    assert events["events"][0]["targetModelId"] == "cognix-code-local"
    assert bob_listed["predictions"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "intent_prediction_built"


def test_dynamic_ui_blueprint_preserves_design_system_without_mutation():
    blueprint = cognix_dynamic_ui.build_dynamic_ui_blueprint()

    assert blueprint["dynamicUiVersion"] == "cognix_dynamic_ui_v1"
    assert blueprint["layoutProfileVersion"] == "cognix_ui_layout_profile_v1"
    assert blueprint["designContract"]["sameDesignSystem"] is True
    assert blueprint["designContract"]["sameTypography"] is True
    assert blueprint["designContract"]["sameNavigationLogic"] is True
    assert blueprint["designContract"]["noVisualRupture"] is True
    assert blueprint["sideEffects"]["profileWrite"] is False
    assert blueprint["sideEffects"]["uiMutation"] is False
    assert blueprint["sideEffects"]["routeMutation"] is False
    assert blueprint["sideEffects"]["themeMutation"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_dynamic_ui_profiles_cover_project_types_mobile_desktop_and_themes():
    code = cognix_dynamic_ui.build_project_ui_profile(
        username = "alice",
        project_type = "code",
        viewport = "desktop",
        theme = "dark",
    )
    physics_mobile = cognix_dynamic_ui.build_project_ui_profile(
        username = "alice",
        project_type = "physique",
        viewport = "mobile",
        theme = "light",
    )

    assert code["projectType"] == "code"
    assert {"files", "editor", "terminal"}.issubset(set(code["activePanels"]))
    assert code["summary"]["darkModeCompatible"] is True
    assert physics_mobile["projectType"] == "physics"
    assert physics_mobile["viewport"] == "mobile"
    assert "overflow-menu" in physics_mobile["activePanels"]
    assert physics_mobile["summary"]["mobileOptimized"] is True
    assert physics_mobile["designContract"]["sameDesignSystem"] is True
    assert physics_mobile["sideEffects"]["uiMutation"] is False


def test_dynamic_ui_profile_endpoint_stores_profile_without_changing_ui():
    seed_accounts()
    body = run_async(
        cognix_routes.dynamic_ui_profile(
            cognix_routes.DynamicUIProfileRequest(
                projectType = "business",
                viewport = "desktop",
                theme = "dark",
                storeProfile = True,
            ),
            current_subject = "alice",
        )
    )
    profile_id = body["storedProfile"]["id"]
    listed = run_async(cognix_routes.dynamic_ui_profiles(current_subject = "alice"))
    bob_listed = run_async(cognix_routes.dynamic_ui_profiles(current_subject = "bob"))

    assert profile_id.startswith("uiprof_")
    assert body["uiProfile"]["projectType"] == "business"
    assert body["sideEffects"]["profileWrite"] is True
    assert body["sideEffects"]["uiMutation"] is False
    assert body["sideEffects"]["themeMutation"] is False
    assert listed["profiles"][0]["id"] == profile_id
    assert bob_listed["profiles"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "dynamic_ui_profile_built"


def test_background_agent_blueprint_requires_queue_without_worker_start():
    blueprint = cognix_background_agents.build_background_agent_blueprint()

    assert blueprint["backgroundAgentVersion"] == "cognix_background_agent_v1"
    assert blueprint["progressTrackerVersion"] == "cognix_progress_tracker_v1"
    assert blueprint["notificationPlanVersion"] == "cognix_notification_plan_v1"
    assert blueprint["securityPolicy"]["queueRequired"] is True
    assert blueprint["securityPolicy"]["permissionsRequired"] is True
    assert blueprint["securityPolicy"]["nightModeRespected"] is True
    assert blueprint["securityPolicy"]["directToolExecutionAllowed"] is False
    assert blueprint["sideEffects"]["jobEnqueue"] is False
    assert blueprint["sideEffects"]["workerStart"] is False
    assert blueprint["sideEffects"]["toolExecution"] is False
    assert blueprint["sideEffects"]["generation"] is False
    assert blueprint["sideEffects"]["notificationSend"] is False


def test_background_agent_plan_selects_job_type_and_respects_night_mode():
    indexing = cognix_background_agents.build_background_agent_job_plan(
        username = "alice",
        task = "Indexer 200 PDF pour le RAG",
        night_mode = True,
    )
    audit = cognix_background_agents.build_background_agent_job_plan(
        username = "alice",
        task = "Auditer un repo GitHub pour la securite",
        priority = "high",
    )

    assert indexing["jobType"] == "index_documents"
    assert indexing["summary"]["nightModeRespected"] is True
    assert indexing["queuePlan"]["willEnqueueNow"] is False
    assert audit["jobType"] == "audit_repo"
    assert audit["priority"] == "high"
    assert audit["sideEffects"]["workerStart"] is False
    assert audit["sideEffects"]["toolExecution"] is False


def test_background_agent_endpoint_queues_planned_job_without_starting_worker():
    seed_accounts()
    body = run_async(
        cognix_routes.background_agent_job_plan(
            cognix_routes.BackgroundJobPlanRequest(
                task = "Comparer plusieurs modeles sur la latence et la qualite",
                priority = "high",
                nightMode = True,
                enqueueJob = True,
            ),
            current_subject = "alice",
        )
    )
    job_id = body["job"]["id"]
    listed = run_async(cognix_routes.background_agent_jobs(current_subject = "alice"))
    fetched = run_async(cognix_routes.background_agent_job(job_id, current_subject = "alice"))
    bob_listed = run_async(cognix_routes.background_agent_jobs(current_subject = "bob"))

    assert job_id.startswith("bjob_")
    assert body["jobPlan"]["jobType"] == "compare_models"
    assert body["sideEffects"]["jobEnqueue"] is True
    assert body["sideEffects"]["workerStart"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["generation"] is False
    assert listed["jobs"][0]["id"] == job_id
    assert fetched["job"]["runs"][0]["status"] == "planned"
    assert fetched["job"]["logs"][0]["progressPercent"] == 0
    assert bob_listed["jobs"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "background_agent_job_planned"


def test_timeline_blueprint_declares_elegant_history_without_ui_mutation():
    blueprint = cognix_timeline.build_timeline_blueprint()

    assert blueprint["timelineVersion"] == "cognix_timeline_v1"
    assert blueprint["eventClassifierVersion"] == "cognix_timeline_event_classifier_v1"
    assert blueprint["displayContract"]["tabName"] == "Timeline"
    assert blueprint["displayContract"]["elegantHistory"] is True
    assert blueprint["displayContract"]["rawLogUi"] is False
    assert blueprint["sideEffects"]["timelineWrite"] is False
    assert blueprint["sideEffects"]["uiMutation"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_timeline_event_classifier_detects_core_event_types():
    model = cognix_timeline.build_timeline_event_plan(
        username = "alice",
        title = "Modele Qwen choisi pour le projet",
    )
    error = cognix_timeline.build_timeline_event_plan(
        username = "alice",
        title = "Erreur critique pendant l'indexation",
    )
    training = cognix_timeline.build_timeline_event_plan(
        username = "alice",
        title = "Fine-tuning QLoRA lance",
    )

    assert model["event"]["eventType"] == "model_selected"
    assert error["event"]["eventType"] == "critical_error"
    assert training["event"]["eventType"] == "fine_tuning_started"
    assert training["sideEffects"]["modelLoad"] is False


def test_timeline_endpoint_stores_filters_searches_and_is_user_scoped():
    seed_accounts()
    body = run_async(
        cognix_routes.create_timeline_event(
            cognix_routes.TimelineEventRequest(
                title = "Architecture backend validee",
                summary = "Decision importante: routes natives et stockage SQLite.",
                storeEvent = True,
            ),
            current_subject = "alice",
        )
    )
    event_id = body["event"]["id"]
    filtered = run_async(cognix_routes.timeline_events(event_type = "architecture_decision", current_subject = "alice"))
    searched = run_async(cognix_routes.timeline_events(query = "sqlite", current_subject = "alice"))
    bob_events = run_async(cognix_routes.timeline_events(current_subject = "bob"))

    assert event_id.startswith("tl_")
    assert body["sideEffects"]["timelineWrite"] is True
    assert body["sideEffects"]["uiMutation"] is False
    assert filtered["events"][0]["id"] == event_id
    assert searched["events"][0]["id"] == event_id
    assert bob_events["events"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "timeline_event_planned"


def test_simulation_blueprint_declares_dashboard_contract_without_execution():
    blueprint = cognix_simulation.build_simulation_blueprint()

    assert blueprint["simulationEngineVersion"] == "cognix_simulation_engine_v1"
    assert blueprint["syntheticUserGeneratorVersion"] == "cognix_synthetic_user_generator_v1"
    assert blueprint["loadScenarioRunnerVersion"] == "cognix_load_scenario_runner_v1"
    assert blueprint["reportGeneratorVersion"] == "cognix_simulation_report_generator_v1"
    assert blueprint["services"] == ["SimulationEngine", "SyntheticUserGenerator", "LoadScenarioRunner", "ReportGenerator"]
    assert {"business", "user", "server", "database", "workflow"}.issubset(set(blueprint["simulationTypes"]))
    assert blueprint["reportContract"]["risks"] is True
    assert blueprint["reportContract"]["estimatedLatency"] is True
    assert blueprint["reportContract"]["estimatedCosts"] is True
    assert blueprint["reportContract"]["bottlenecks"] is True
    assert blueprint["reportContract"]["dashboardSimple"] is True
    assert blueprint["queuePolicy"]["directLoadTestAllowedFromPlanner"] is False
    assert blueprint["sideEffects"]["simulationRunWrite"] is False
    assert blueprint["sideEffects"]["queueEnqueue"] is False
    assert blueprint["sideEffects"]["syntheticAgentRun"] is False
    assert blueprint["sideEffects"]["loadExecution"] is False
    assert blueprint["sideEffects"]["generation"] is False


def test_simulation_plan_estimates_10_and_100_user_loads_without_execution():
    small = cognix_simulation.build_simulation_plan(
        username = "alice",
        simulation_type = "server",
        user_count = 10,
        scenario = "Simule un serveur local CogniX pour une classe.",
        duration_minutes = 15,
        constraints = ["local only"],
        project_type = "school",
    )
    large = cognix_simulation.build_simulation_plan(
        username = "alice",
        simulation_type = "business",
        user_count = 100,
        scenario = "Simule 100 utilisateurs utilisant CogniX Business avec SQLite.",
        duration_minutes = 45,
        constraints = ["database", "privacy"],
        project_type = "business",
    )
    small_metrics = {item["id"]: item for item in small["metrics"]}
    large_metrics = {item["id"]: item for item in large["metrics"]}

    assert small["scenario"]["simulationType"] == "server"
    assert small["scenario"]["userCount"] == 10
    assert small["queuePlan"]["queueRequired"] is False
    assert small["report"]["summary"]["estimatedCostUsd"] == 0.0
    assert small["sideEffects"]["loadExecution"] is False
    assert small["sideEffects"]["generation"] is False
    assert large["scenario"]["simulationType"] == "business"
    assert large["scenario"]["userCount"] == 100
    assert large["queuePlan"]["queueRequired"] is True
    assert large["queuePlan"]["jobType"] == "simulation_run"
    assert large["syntheticAgents"]["plannedCount"] == 25
    assert large_metrics["estimated_latency_ms"]["value"] > small_metrics["estimated_latency_ms"]["value"]
    assert any(item["id"] == "high_concurrency" for item in large["report"]["risks"])
    assert any(item["id"] == "database_pressure" for item in large["report"]["bottlenecks"])


def test_simulation_endpoint_stores_metrics_and_is_user_scoped():
    seed_accounts()
    body = run_async(
        cognix_routes.create_simulation_run(
            cognix_routes.SimulationRunRequest(
                simulationType = "business",
                userCount = 100,
                scenario = "Simule 100 utilisateurs utilisant CogniX Business avec SQLite.",
                durationMinutes = 45,
                constraints = ["database", "privacy"],
                storeRun = True,
            ),
            current_subject = "alice",
        )
    )
    run_id = body["run"]["id"]
    detail = run_async(cognix_routes.simulation_run(run_id, current_subject = "alice"))
    listed = run_async(cognix_routes.simulation_runs(simulation_type = "business", query = "sqlite", current_subject = "alice"))
    bob_runs = run_async(cognix_routes.simulation_runs(current_subject = "bob"))

    assert run_id.startswith("sim_")
    assert body["simulationPlan"]["queuePlan"]["queueRequired"] is True
    assert body["simulationPlan"]["report"]["dashboardSimple"] is True
    assert body["sideEffects"]["simulationRunWrite"] is True
    assert body["sideEffects"]["metricsWrite"] is True
    assert body["sideEffects"]["queueEnqueue"] is False
    assert body["sideEffects"]["loadExecution"] is False
    assert body["sideEffects"]["generation"] is False
    assert detail["run"]["id"] == run_id
    assert detail["run"]["simulationType"] == "business"
    assert detail["run"]["userCount"] == 100
    assert len(detail["run"]["metrics"]) >= 6
    assert any(item["metricKey"] == "estimated_latency_ms" for item in detail["run"]["metrics"])
    assert listed["runs"][0]["id"] == run_id
    assert bob_runs["runs"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "simulation_run_planned"
    assert logs[0]["metadata"]["queueRequired"] is True


def test_sandbox_blueprint_declares_isolation_without_execution():
    blueprint = cognix_sandbox.build_sandbox_blueprint()

    assert blueprint["sandboxManagerVersion"] == "cognix_sandbox_manager_v1"
    assert blueprint["isolatedRuntimeVersion"] == "cognix_isolated_runtime_v1"
    assert blueprint["experimentRunnerVersion"] == "cognix_experiment_runner_v1"
    assert blueprint["rollbackServiceVersion"] == "cognix_rollback_service_v1"
    assert blueprint["services"] == ["SandboxManager", "IsolatedRuntime", "ExperimentRunner", "RollbackService"]
    assert "feature" in blueprint["targetTypes"]
    assert "tool" in blueprint["targetTypes"]
    assert blueprint["badge"]["label"] == "Mode sandbox actif"
    assert blueprint["security"]["productionSecretsAccessible"] is False
    assert blueprint["security"]["autoPromotionAllowed"] is False
    assert blueprint["sideEffects"]["isolatedRuntimeStart"] is False
    assert blueprint["sideEffects"]["experimentRun"] is False
    assert blueprint["sideEffects"]["productionSecretRead"] is False
    assert blueprint["sideEffects"]["promotion"] is False
    assert blueprint["sideEffects"]["toolExecution"] is False


def test_sandbox_plan_blocks_prod_secrets_and_prepares_rollback():
    plan = cognix_sandbox.build_sandbox_plan(
        username = "alice",
        target_type = "tool",
        objective = "Tester un nouvel outil API avant de l'activer dans CogniX.",
        change_summary = "Le test touche un token secret et une base production.",
        requested_checks = ["network policy", "rollback"],
        duration_minutes = 45,
        project_type = "developer",
    )

    assert plan["target"]["type"] == "tool"
    assert plan["report"]["riskLevel"] == "high"
    assert plan["report"]["summary"]["requiresHumanApproval"] is True
    assert plan["isolation"]["productionSecretsAccessible"] is False
    assert plan["isolation"]["productionDatabaseWritable"] is False
    assert plan["rollbackPlan"]["deleteSandboxOnFailure"] is True
    assert plan["rollbackPlan"]["productionRollbackWillExecuteNow"] is False
    assert plan["queuePlan"]["jobType"] == "sandbox_experiment"
    assert plan["queuePlan"]["willEnqueueNow"] is False
    assert any(step["id"] == "copy_minimal_config" for step in plan["pipeline"])
    assert any(item["id"] == "touchesSecrets" for item in plan["report"]["risks"])
    assert plan["sideEffects"]["minimalConfigCopy"] is False
    assert plan["sideEffects"]["experimentRun"] is False
    assert plan["sideEffects"]["productionSecretRead"] is False
    assert plan["sideEffects"]["networkCall"] is False
    assert plan["sideEffects"]["fileWrite"] is False


def test_sandbox_endpoint_stores_report_and_is_user_scoped():
    seed_accounts()
    body = run_async(
        cognix_routes.create_sandbox_plan(
            cognix_routes.SandboxPlanRequest(
                targetType = "code_change",
                objective = "Tester une modification backend CogniX sans casser l'app.",
                changeSummary = "Patch sur route auth avec rollback obligatoire.",
                requestedChecks = ["smoke", "security"],
                storeRun = True,
            ),
            current_subject = "alice",
        )
    )
    run_id = body["run"]["id"]
    detail = run_async(cognix_routes.sandbox_run(run_id, current_subject = "alice"))
    listed = run_async(cognix_routes.sandbox_runs(target_type = "code_change", query = "rollback", current_subject = "alice"))
    bob_runs = run_async(cognix_routes.sandbox_runs(current_subject = "bob"))

    assert run_id.startswith("srun_")
    assert body["run"]["sandboxId"].startswith("sbx_")
    assert body["sandboxPlan"]["report"]["badge"] == "Mode sandbox actif"
    assert body["sideEffects"]["sandboxWrite"] is True
    assert body["sideEffects"]["sandboxRunWrite"] is True
    assert body["sideEffects"]["sandboxReportWrite"] is True
    assert body["sideEffects"]["isolatedRuntimeStart"] is False
    assert body["sideEffects"]["productionSecretRead"] is False
    assert body["sideEffects"]["promotion"] is False
    assert detail["run"]["id"] == run_id
    assert detail["run"]["targetType"] == "code_change"
    assert detail["run"]["sandbox"]["badgeLabel"] == "Mode sandbox actif"
    assert detail["run"]["reportRecord"]["riskLevel"] in {"medium", "high"}
    assert listed["runs"][0]["id"] == run_id
    assert bob_runs["runs"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    assert logs[0]["action"] == "sandbox_plan_built"
    assert logs[0]["metadata"]["productionSecretsAccessible"] is False
    assert logs[0]["metadata"]["sideEffects"]["experimentRun"] is False


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
    assert plan["nightModeContractVersion"] == "cognix_codex_night_mode_contract_v1"
    assert plan["supervisionMode"] == "supervised"
    assert plan["nightModeActive"] is False
    assert plan["applicable"] is True
    assert plan["recommendedPath"] == "codex_guarded_pipeline"
    assert plan["branch"]["recommendedName"] == "cognix/project-code"
    assert plan["branch"]["willCreate"] is False
    assert plan["runContract"]["contractVersion"] == "cognix_codex_run_contract_v1"
    assert plan["runContract"]["targetBranch"] == "cognix/project-code"
    assert plan["runContract"]["mergeAllowedHere"] is False
    assert plan["runContract"]["mergeGate"]["humanApprovalRequired"] is True
    assert plan["runContract"]["mergeGate"]["requiresSecurityReview"] is True
    assert "native_guard_passed" in plan["runContract"]["evidenceRequirements"]
    assert any(item["id"] == "native_guard" for item in plan["runContract"]["commandPlan"])
    assert plan["qualityGates"]["testsRequired"] is True
    assert plan["qualityGates"]["buildRequired"] is True
    assert plan["qualityGates"]["humanApprovalRequired"] is True
    assert plan["qualityGates"]["nightModePolicyRequired"] is False
    assert plan["supervisionModeContract"]["runMode"] == "supervised"
    assert plan["supervisionModeContract"]["visibleUxChangeAllowed"] is True
    assert any(step["id"] == "human_approval" for step in plan["steps"])
    assert any(item["id"] == "commit_push_merge" for item in plan["blockedActions"])
    assert "merge" in plan["runContract"]["blockedActions"]
    assert plan["sideEffects"]["fileWrite"] is False
    assert plan["sideEffects"]["codeModification"] is False
    assert plan["sideEffects"]["merge"] is False
    assert plan["runContract"]["sideEffects"]["testExecution"] is False


def test_codex_night_mode_contract_allows_security_optimization_only():
    plan = cognix_codex_pipeline.build_codex_pipeline_plan(
        objective = "Durcir la securite backend, redaction des secrets et logs audit.",
        current_subject = "alice",
        project_id = "security-hardening",
        classification = {"selectedDomain": "code"},
        task_strategy = {"path": "codex_guarded_pipeline"},
        execution_policy = {"riskLevel": "high"},
        run_mode = "night",
    )

    contract = plan["supervisionModeContract"]
    assert contract["contractVersion"] == "cognix_codex_night_mode_contract_v1"
    assert contract["runMode"] == "night"
    assert contract["nightModeActive"] is True
    assert contract["selectedCategory"] == "security"
    assert contract["visibleProductChangeRequested"] is False
    assert contract["autonomousNightWorkAllowed"] is True
    assert contract["blockedByNightMode"] is False
    assert contract["nativeSourcePatchAllowed"] is True
    assert contract["visibleUxChangeAllowed"] is False
    assert "files_modified" in contract["requiredReportSections"]
    assert "recommendations_for_human_validation" in contract["requiredReportSections"]
    assert plan["qualityGates"]["nightModePolicyRequired"] is True
    assert plan["qualityGates"]["nightModeAllowsAutonomousWork"] is True
    assert plan["sideEffects"]["codeModification"] is False


def test_codex_night_mode_contract_blocks_visible_feature_work():
    plan = cognix_codex_pipeline.build_codex_pipeline_plan(
        objective = "Ajoute un nouveau module visible CogniX Chemistry avec navigation et UI.",
        current_subject = "alice",
        project_id = "chemistry-ui",
        classification = {"selectedDomain": "code"},
        task_strategy = {"path": "codex_guarded_pipeline"},
        execution_policy = {"riskLevel": "high"},
        run_mode = "night",
    )

    contract = plan["supervisionModeContract"]
    assert contract["runMode"] == "night"
    assert contract["nightModeActive"] is True
    assert contract["visibleProductChangeRequested"] is True
    assert contract["autonomousNightWorkAllowed"] is False
    assert contract["blockedByNightMode"] is True
    assert contract["nativeSourcePatchAllowed"] is False
    assert "visible_ux_change" in contract["blockedActions"]
    assert any(item["id"] == "night_mode_visible_change" for item in plan["blockedActions"])
    assert plan["qualityGates"]["nightModeAllowsAutonomousWork"] is False
    assert any("Mode nuit bloque" in warning for warning in plan["warnings"])


def test_codex_night_report_contract_requires_sections_without_writes():
    contract = cognix_codex_pipeline.build_codex_night_report_contract(
        objective = "Durcir la securite backend et optimiser les logs audit.",
        run_mode = "night",
        files_modified = ["studio/backend/core/cognix/security_policy.py"],
        tests_run = [{"command": "pytest -q studio/backend/tests/test_cognix_router.py", "status": "passed"}],
        results = {"summary": "Security policy tests passed."},
        risks_detected = [],
        recommendations_for_human_validation = ["Review the security policy diff before merge."],
    )

    assert contract["contractVersion"] == "cognix_codex_night_report_contract_v1"
    assert contract["nightModeContractVersion"] == "cognix_codex_night_mode_contract_v1"
    assert contract["runMode"] == "night"
    assert contract["nightModeActive"] is True
    assert contract["readyForHumanValidation"] is True
    assert contract["missingRequiredSections"] == []
    assert contract["mergePolicy"]["automaticMergeAllowed"] is False
    assert contract["mergePolicy"]["productionDeploymentAllowed"] is False
    assert contract["sideEffects"]["fileWrite"] is False
    assert contract["sideEffects"]["codeModification"] is False
    assert contract["sideEffects"]["testExecution"] is False
    assert contract["sideEffects"]["auditWrite"] is False


def test_codex_night_report_contract_blocks_incomplete_or_visible_work():
    missing_report = cognix_codex_pipeline.build_codex_night_report_contract(
        objective = "Durcir la securite backend.",
        run_mode = "night",
        files_modified = ["studio/backend/routes/cognix.py"],
        tests_run = [{"command": "pytest", "status": "passed"}],
        results = {"summary": "ok"},
    )
    visible_report = cognix_codex_pipeline.build_codex_night_report_contract(
        objective = "Ajoute une nouvelle interface visible avec navigation.",
        run_mode = "night",
        files_modified = ["studio/frontend/src/App.tsx"],
        tests_run = [{"command": "npm test", "status": "passed"}],
        results = {"summary": "ok"},
        risks_detected = [],
        recommendations_for_human_validation = ["Wait for human validation."],
    )

    assert missing_report["readyForHumanValidation"] is False
    assert "recommendations_for_human_validation" in missing_report["missingRequiredSections"]
    assert visible_report["blockedByNightMode"] is True
    assert visible_report["readyForHumanValidation"] is False
    assert visible_report["sideEffects"]["reportWrite"] is False


def test_codex_night_report_endpoint_returns_dry_run_contract():
    body = run_async(
        cognix_routes.codex_night_report_contract(
            cognix_routes.CodexNightReportContractRequest(
                objective = "Durcir la securite CogniX pendant la nuit.",
                nightMode = True,
                filesModified = ["studio/backend/core/cognix/codex_pipeline.py"],
                testsRun = [{"command": "pytest -q", "status": "passed"}],
                results = {"summary": "ok"},
                risksDetected = [],
                recommendationsForHumanValidation = ["Review before merge."],
            ),
            current_subject = "alice",
        )
    )

    contract = body["codexNightReportContract"]
    assert body["plannerVersion"] == "cognix_codex_night_report_contract_v1"
    assert body["username"] == "alice"
    assert contract["readyForHumanValidation"] is True
    assert body["sideEffects"]["fileWrite"] is False
    assert body["sideEffects"]["reportWrite"] is False
    assert body["sideEffects"]["merge"] is False


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
    assert pipeline["runContract"]["contractVersion"] == "cognix_codex_run_contract_v1"
    assert pipeline["supervisionModeContract"]["runMode"] == "supervised"
    assert pipeline["sideEffects"]["branchCreate"] is False
    assert pipeline["sideEffects"]["testExecution"] is False
    assert pipeline["sideEffects"]["codeModification"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "codex_pipeline_plan_built"
    assert log["metadata"]["codexPipelineVersion"] == "cognix_codex_pipeline_v1"
    assert log["metadata"]["runContractVersion"] == "cognix_codex_run_contract_v1"
    assert log["metadata"]["nightModeContractVersion"] == "cognix_codex_night_mode_contract_v1"
    assert log["metadata"]["supervisionMode"] == "supervised"
    assert log["metadata"]["nightModeActive"] is False
    assert "native_guard_passed" in log["metadata"]["evidenceRequirements"]
    assert log["metadata"]["sideEffects"]["codeModification"] is False


def test_codex_pipeline_endpoint_respects_night_mode_policy(monkeypatch):
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
                objective = "Durcir la securite backend CogniX et les logs audit.",
                project_type = "code",
                project_id = "security-hardening",
                nightMode = True,
            ),
            current_subject = "alice",
        )
    )

    pipeline = body["codexPipelinePlan"]
    contract = pipeline["supervisionModeContract"]
    assert pipeline["nightModeActive"] is True
    assert contract["runMode"] == "night"
    assert contract["selectedCategory"] == "security"
    assert contract["autonomousNightWorkAllowed"] is True
    assert contract["visibleProductChangeRequested"] is False
    assert pipeline["qualityGates"]["nightModeAllowsAutonomousWork"] is True

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["metadata"]["nightModeActive"] is True
    assert log["metadata"]["supervisionModeContract"]["runMode"] == "night"
    assert log["metadata"]["supervisionModeContract"]["selectedCategory"] == "security"
    assert log["metadata"]["supervisionModeContract"]["autonomousNightWorkAllowed"] is True


def test_codex_preview_contract_blocks_merge_without_test_build_security_gates():
    contract = cognix_codex_pipeline.build_codex_preview_contract(
        username = "alice",
        feature_request = {"title": "CogniX Chemistry"},
        pipeline_plan = {"branch": {"recommendedName": "cognix/chemistry"}},
        test_results = {"status": "failed", "failed": 1},
        build_result = {"status": "passed", "failed": 0},
        security_scan = {"status": "failed", "critical": 1, "high": 0},
        preview_target = "local_preview",
    )

    assert contract["contractVersion"] == "cognix_codex_preview_contract_v1"
    assert contract["status"] == "blocked_missing_gate"
    assert contract["readyForPreviewReview"] is False
    assert contract["readyForPreviewStart"] is False
    assert contract["readyForMerge"] is False
    assert {"tests_passed", "security_scan_passed"}.issubset(contract["blockedGateIds"])
    assert contract["mergePolicy"]["automaticMergeAllowed"] is False
    assert contract["mergePolicy"]["humanApprovalRequired"] is True
    assert contract["sideEffects"]["previewStart"] is False
    assert contract["sideEffects"]["merge"] is False
    assert contract["sideEffects"]["codeWrite"] is False


def test_codex_preview_contract_prepares_preview_without_starting_or_merging():
    contract = cognix_codex_pipeline.build_codex_preview_contract(
        username = "alice",
        feature_request = {"id": "feat-chemistry", "title": "CogniX Chemistry"},
        branch_name = "feature/cognix-chemistry",
        test_results = {"status": "passed", "passed": True, "failed": 0, "errors": 0},
        build_result = {"status": "success", "failed": 0, "errors": 0},
        security_scan = {"status": "clean", "critical": 0, "high": 0, "errors": 0},
        preview_target = "https://cognix.local:4321",
    )

    assert contract["status"] == "ready_for_preview_review"
    assert contract["readyForPreviewReview"] is True
    assert contract["previewPlan"]["readyForManualReview"] is True
    assert contract["previewPlan"]["willStartPreview"] is False
    assert contract["previewPlan"]["previewUrlGenerated"] is False
    assert contract["mergePolicy"]["readyForHumanMergeApproval"] is True
    assert contract["mergePolicy"]["mainBranchWriteAllowed"] is False
    assert contract["blockedGateIds"] == []
    assert all(value is False for value in contract["sideEffects"].values())


def test_codex_preview_contract_endpoint_logs_sanitized_dry_run(monkeypatch):
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
        cognix_routes.codex_preview_contract(
            cognix_routes.CodexPreviewContractRequest(
                objective = "Ajoute un module CogniX Chemistry dans mon backend",
                project_type = "code",
                project_id = "project-code",
                branch_name = "feature/cognix-chemistry",
                feature_request = {
                    "title": "CogniX Chemistry",
                    "description": "secret codex idea should never be logged",
                },
                test_results = {"status": "passed", "passed": True, "failed": 0, "errors": 0},
                build_result = {"status": "passed", "failed": 0, "errors": 0},
                security_scan = {"status": "passed", "critical": 0, "high": 0, "errors": 0},
                preview_target = "local_preview",
            ),
            current_subject = "alice",
        )
    )

    contract = body["codexPreviewContract"]
    assert body["auditLogId"].startswith("aud_")
    assert body["contractVersion"] == "cognix_codex_preview_contract_v1"
    assert contract["readyForPreviewReview"] is True
    assert contract["readyForPreviewStart"] is False
    assert contract["readyForMerge"] is False
    assert contract["sideEffects"]["toolExecution"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "codex_preview_contract_built"
    assert log["metadata"]["previewContractVersion"] == "cognix_codex_preview_contract_v1"
    assert log["metadata"]["readyForPreviewReview"] is True
    assert log["metadata"]["readyForPreviewStart"] is False
    assert log["metadata"]["readyForMerge"] is False
    assert log["metadata"]["sideEffects"]["previewStart"] is False
    assert "secret codex idea" not in log["metadataJson"]


def test_codex_approval_gate_blocks_merge_without_branch_scoped_approval():
    preview = cognix_codex_pipeline.build_codex_preview_contract(
        username = "alice",
        feature_request = {"title": "CogniX Chemistry"},
        branch_name = "feature/cognix-chemistry",
        test_results = {"status": "passed", "passed": True, "failed": 0},
        build_result = {"status": "passed", "failed": 0},
        security_scan = {"status": "passed", "critical": 0, "high": 0},
    )
    gate = cognix_codex_pipeline.build_codex_approval_gate_contract(
        username = "alice",
        preview_contract = preview,
        approval_request = {
            "id": "apr_1",
            "username": "alice",
            "request_type": "codex:run",
            "status": "approved",
            "risk_level": "critical",
            "metadata": {"branchName": "feature/other"},
        },
        approval_decisions = [{"status": "approved", "decided_by": "admin"}],
        branch_name = "feature/cognix-chemistry",
    )

    assert gate["contractVersion"] == "cognix_codex_approval_gate_v1"
    assert gate["status"] == "blocked_missing_approval_gate"
    assert gate["readyForMergeReview"] is False
    assert gate["readyForMerge"] is False
    assert "approval_branch_matches_preview" in gate["blockedGateIds"]
    assert gate["mergePolicy"]["automaticMergeAllowed"] is False
    assert gate["sideEffects"]["approvalWrite"] is False
    assert gate["sideEffects"]["merge"] is False


def test_codex_approval_gate_prepares_human_merge_review_without_merging():
    preview = cognix_codex_pipeline.build_codex_preview_contract(
        username = "alice",
        feature_request = {"title": "CogniX Chemistry"},
        branch_name = "feature/cognix-chemistry",
        test_results = {"status": "passed", "passed": True, "failed": 0},
        build_result = {"status": "passed", "failed": 0},
        security_scan = {"status": "passed", "critical": 0, "high": 0},
    )
    gate = cognix_codex_pipeline.build_codex_approval_gate_contract(
        username = "alice",
        preview_contract = preview,
        approval_request = {
            "id": "apr_1",
            "username": "alice",
            "request_type": "codex:run",
            "status": "approved",
            "risk_level": "critical",
            "metadata": {"branchName": "feature/cognix-chemistry"},
        },
        approval_decisions = [{"status": "approved", "decided_by": "admin"}],
        branch_name = "feature/cognix-chemistry",
    )

    assert gate["status"] == "ready_for_human_merge_review"
    assert gate["readyForMergeReview"] is True
    assert gate["readyForMerge"] is False
    assert gate["mergeAllowedHere"] is False
    assert gate["mergePolicy"]["readyForHumanMergeReview"] is True
    assert gate["mergePolicy"]["mainBranchWriteAllowed"] is False
    assert gate["blockedGateIds"] == []
    assert all(value is False for value in gate["sideEffects"].values())


def test_codex_approval_gate_endpoint_logs_sanitized_dry_run(monkeypatch):
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
    request = cognix_db.create_approval_request(
        "alice",
        "codex:run",
        "Approve Codex branch",
        title = "Codex branch approval",
        risk_level = "critical",
        resource_type = "codex",
        resource_id = "feature/cognix-chemistry",
        metadata = {
            "branchName": "feature/cognix-chemistry",
            "secretNote": "branch secret should never be logged",
        },
    )
    request = cognix_db.set_approval_status(
        str(request["id"]),
        "approved",
        decided_by = storage.DEFAULT_ADMIN_USERNAME,
        admin_note = "Approved",
    )

    body = run_async(
        cognix_routes.codex_approval_gate(
            cognix_routes.CodexApprovalGateRequest(
                objective = "Ajoute un module CogniX Chemistry dans mon backend",
                project_type = "code",
                project_id = "project-code",
                approval_request_id = str(request["id"]),
                branch_name = "feature/cognix-chemistry",
                feature_request = {"title": "CogniX Chemistry"},
                test_results = {"status": "passed", "passed": True, "failed": 0, "errors": 0},
                build_result = {"status": "passed", "failed": 0, "errors": 0},
                security_scan = {"status": "passed", "critical": 0, "high": 0, "errors": 0},
                preview_target = "local_preview",
            ),
            current_subject = "alice",
        )
    )

    gate = body["codexApprovalGate"]
    assert body["auditLogId"].startswith("aud_")
    assert body["contractVersion"] == "cognix_codex_approval_gate_v1"
    assert gate["readyForMergeReview"] is True
    assert gate["readyForMerge"] is False
    assert gate["sideEffects"]["decisionWrite"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "codex_approval_gate_built"
    assert log["metadata"]["approvalGateVersion"] == "cognix_codex_approval_gate_v1"
    assert log["metadata"]["readyForMergeReview"] is True
    assert log["metadata"]["readyForMerge"] is False
    assert log["metadata"]["sideEffects"]["merge"] is False
    assert "branch secret should never be logged" not in log["metadataJson"]


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


def test_worker_queue_registry_declares_cloud_training_without_execution():
    registry = cognix_worker_queue.build_worker_queue_registry()

    assert registry["workerQueueVersion"] == "cognix_worker_queue_v1"
    assert registry["mode"] == "declarative_dry_run"
    assert registry["globalPolicies"]["frontendDirectQueueMutationAllowed"] is False
    assert registry["globalPolicies"]["jobSpecsRequireApproval"] is True
    assert registry["globalPolicies"]["idempotencyKeyRequired"] is True
    assert registry["sideEffects"]["jobEnqueue"] is False
    assert registry["sideEffects"]["workerStart"] is False
    assert registry["sideEffects"]["cloudTrainingJob"] is False

    queues = {item["id"]: item for item in registry["queues"]}
    assert "simulation_run" in queues["local_probe"]["acceptedJobTypes"]
    assert "sandbox_experiment" in queues["local_probe"]["acceptedJobTypes"]
    assert "rag_connector_sync" in queues["io_bound"]["acceptedJobTypes"]
    assert "tool_execution" in queues
    assert "tool_execution" in queues["tool_execution"]["acceptedJobTypes"]
    assert queues["tool_execution"]["requiresHumanConfirmation"] is True
    assert "distillation_job" in queues["gpu_long_running"]["acceptedJobTypes"]
    assert "cloud_training" in queues
    assert "cloud_training_job" in queues["cloud_training"]["acceptedJobTypes"]
    assert "cloud_distillation_job" in queues["cloud_training"]["acceptedJobTypes"]
    assert queues["cloud_training"]["requiresHumanConfirmation"] is True
    assert "enterprise_throughput" in queues
    assert "batching_experiment" in queues["enterprise_throughput"]["acceptedJobTypes"]
    assert "throughput_benchmark" in queues["enterprise_throughput"]["acceptedJobTypes"]
    assert queues["enterprise_throughput"]["requiresHumanConfirmation"] is True


def test_worker_job_spec_plan_materializes_cloud_and_rag_jobs_without_enqueueing():
    queue_plan = cognix_worker_queue.build_worker_queue_plan(
        objective = "Prepare RAG indexing and cloud training",
        project_id = "project-ai",
        task_strategy = {"path": "rag_first"},
        rag_plan = {
            "recommendedPath": "rag_first",
            "readyForRetrieval": False,
        },
        fine_tuning_plan = {
            "recommendedPath": "guided_fine_tuning",
            "method": {"type": "cloud_qlora"},
            "resourceTargetPlan": {"cloudTrainingAllowed": True},
            "approval": {"readyToRequest": True},
        },
        preload_plan = {},
        codex_pipeline_plan = {},
        optimization_plan = {},
        latest_benchmark_run = {"id": "bench-ok", "benchmark": {}},
    )

    spec_plan = cognix_worker_queue.build_worker_job_spec_plan(
        objective = "Prepare RAG indexing and cloud training",
        project_id = "project-ai",
        worker_queue_plan = queue_plan,
        rag_indexing_plan = {
            "status": "ready",
            "readyToIndexCount": 1,
            "summary": {"sourceCount": 1, "estimatedChunkCount": 24},
        },
        cloud_handoff_plan = {
            "status": "ready_for_export",
            "readyToExport": True,
            "target": {"id": "kaggle", "exportFormat": "kaggle_kernel_plan"},
            "artifactManifest": [{"path": "CogniX_training_notebook.ipynb"}],
        },
        preload_plan = {},
    )

    assert spec_plan["jobSpecVersion"] == "cognix_worker_job_spec_v1"
    assert spec_plan["summary"]["safeToEnqueueAutomatically"] is False
    assert spec_plan["policies"]["rawPayloadStorageAllowed"] is False
    assert spec_plan["sideEffects"]["jobEnqueue"] is False
    assert spec_plan["sideEffects"]["cloudTrainingJob"] is False
    assert spec_plan["sideEffects"]["ragIndexing"] is False

    specs = {item["jobType"]: item for item in spec_plan["jobSpecs"]}
    assert {"rag_indexing", "cloud_training_job"}.issubset(specs)
    assert specs["cloud_training_job"]["queueId"] == "cloud_training"
    assert specs["cloud_training_job"]["payloadSummary"]["targetId"] == "kaggle"
    assert specs["cloud_training_job"]["payloadSummary"]["rawSecretsIncluded"] is False
    assert specs["rag_indexing"]["payloadSummary"]["rawSourceContentIncluded"] is False
    assert all(spec["idempotencyKey"].startswith("cognix:project-ai:") for spec in spec_plan["jobSpecs"])


def test_worker_job_spec_plan_materializes_connector_sync_without_network_or_enqueueing():
    connector_plan = cognix_rag_planner.build_rag_connector_sync_plan(
        username = "alice",
        connector_id = "google-drive",
        project_id = "project-rag",
        objective = "Synchroniser Drive vers RAG",
        source_filters = {"folderId": "private-folder", "mimeTypes": ["pdf"]},
        max_documents = 12,
        has_developer_mode = True,
        granted_permissions = {"drive:read", "rag:write"},
    )

    spec_plan = cognix_worker_queue.build_worker_job_spec_plan(
        objective = "Synchroniser Drive vers RAG",
        project_id = "project-rag",
        worker_queue_plan = {},
        rag_connector_sync_plan = connector_plan,
    )

    assert spec_plan["jobSpecVersion"] == "cognix_worker_job_spec_v1"
    assert spec_plan["summary"]["safeToEnqueueAutomatically"] is False
    assert spec_plan["sideEffects"]["jobEnqueue"] is False
    assert spec_plan["sideEffects"]["connectorSync"] is False
    assert spec_plan["sideEffects"]["documentDownload"] is False
    assert spec_plan["sideEffects"]["networkToolCall"] is False
    assert spec_plan["sideEffects"]["secretRead"] is False

    specs = {item["jobType"]: item for item in spec_plan["jobSpecs"]}
    assert "rag_connector_sync" in specs
    sync = specs["rag_connector_sync"]
    assert sync["queueId"] == "io_bound"
    assert sync["sourcePlanStatus"] == "connector_activation_required"
    assert sync["requiresHumanConfirmation"] is True
    assert sync["willEnqueue"] is False
    assert sync["willExecute"] is False
    assert sync["payloadSummary"]["connectorId"] == "google-drive"
    assert sync["payloadSummary"]["sourceFilterKeys"] == ["folderId", "mimeTypes"]
    assert sync["payloadSummary"]["rawFilterValuesIncluded"] is False
    assert sync["payloadSummary"]["rawDocumentContentIncluded"] is False
    assert sync["payloadSummary"]["rawSecretsIncluded"] is False
    assert "private-folder" not in str(sync["payloadSummary"])

    enqueue_contract = cognix_worker_queue.build_worker_enqueue_contract(
        job_spec_plan = spec_plan,
        confirmation_id = "conf_rag_sync",
        request_id = "req_rag_sync",
    )
    job_contracts = {item["jobType"]: item for item in enqueue_contract["jobContracts"]}
    assert enqueue_contract["readyForQueueReview"] is True
    assert enqueue_contract["readyForJobEnqueue"] is False
    assert enqueue_contract["sideEffects"]["jobEnqueue"] is False
    assert enqueue_contract["sideEffects"]["connectorSync"] is False
    assert job_contracts["rag_connector_sync"]["readyForQueueReview"] is True
    assert all(gate["passed"] for gate in job_contracts["rag_connector_sync"]["gates"])
    assert job_contracts["rag_connector_sync"]["payloadBoundary"]["secretValuesIncluded"] is False


def test_worker_job_spec_plan_materializes_tool_execution_handoff_without_enqueuing_or_payload_storage():
    tool_plan = cognix_tool_registry.plan_tool_action(
        tool_id = "codex-secure-agent",
        action_id = "plan_feature",
        username = "alice",
        has_developer_mode = True,
        granted_permissions = set(),
    )
    tool_plan = cognix_tool_registry.apply_rate_limit_result(
        tool_plan,
        {
            "allowed": True,
            "remaining": 19,
            "resetAt": "2026-06-29T00:00:00Z",
        },
    )
    handoff = cognix_tool_registry.build_tool_execution_handoff(
        plan = tool_plan,
        request_id = "req_tool_worker",
    )

    spec_plan = cognix_worker_queue.build_worker_job_spec_plan(
        objective = "Planifier une action outil via worker",
        project_id = "project-tools",
        worker_queue_plan = {},
        tool_execution_handoff = handoff,
    )

    assert handoff["readyForExecutorReview"] is True
    assert spec_plan["jobSpecVersion"] == "cognix_worker_job_spec_v1"
    assert spec_plan["summary"]["safeToEnqueueAutomatically"] is False
    assert spec_plan["sideEffects"]["jobEnqueue"] is False
    assert spec_plan["sideEffects"]["toolExecution"] is False
    assert spec_plan["sideEffects"]["externalWrite"] is False
    assert spec_plan["sideEffects"]["networkToolCall"] is False
    assert spec_plan["sideEffects"]["secretRead"] is False

    specs = {item["jobType"]: item for item in spec_plan["jobSpecs"]}
    assert "tool_execution" in specs
    tool_spec = specs["tool_execution"]
    assert tool_spec["queueId"] == "tool_execution"
    assert tool_spec["sourcePlanStatus"] == "ready_for_executor_review"
    assert tool_spec["requiresHumanConfirmation"] is True
    assert tool_spec["willEnqueue"] is False
    assert tool_spec["willExecute"] is False
    assert tool_spec["payloadSummary"]["handoffId"] == handoff["handoffId"]
    assert tool_spec["payloadSummary"]["toolId"] == "codex-secure-agent"
    assert tool_spec["payloadSummary"]["actionId"] == "plan_feature"
    assert tool_spec["payloadSummary"]["readyForExecutorReview"] is True
    assert tool_spec["payloadSummary"]["readyForJobEnqueue"] is False
    assert tool_spec["payloadSummary"]["rawPayloadIncluded"] is False
    assert tool_spec["payloadSummary"]["rawToolPayloadIncluded"] is False
    assert tool_spec["payloadSummary"]["secretValuesIncluded"] is False
    assert tool_spec["payloadSummary"]["rawSecretsIncluded"] is False
    assert "access_token" not in str(tool_spec["payloadSummary"]).lower()

    enqueue_contract = cognix_worker_queue.build_worker_enqueue_contract(
        job_spec_plan = spec_plan,
        confirmation_id = "conf_tool_worker",
        request_id = "req_tool_worker",
    )
    job_contracts = {item["jobType"]: item for item in enqueue_contract["jobContracts"]}
    assert enqueue_contract["readyForQueueReview"] is True
    assert enqueue_contract["readyForJobEnqueue"] is False
    assert enqueue_contract["sideEffects"]["jobEnqueue"] is False
    assert enqueue_contract["sideEffects"]["toolExecution"] is False
    assert job_contracts["tool_execution"]["readyForQueueReview"] is True
    assert all(gate["passed"] for gate in job_contracts["tool_execution"]["gates"])
    assert job_contracts["tool_execution"]["payloadBoundary"]["rawPayloadIncluded"] is False
    assert job_contracts["tool_execution"]["payloadBoundary"]["secretValuesIncluded"] is False


def test_worker_enqueue_contract_adds_retry_dead_letter_and_idempotency_without_enqueueing():
    queue_plan = cognix_worker_queue.build_worker_queue_plan(
        objective = "Prepare RAG indexing and cloud training",
        project_id = "project-ai",
        task_strategy = {"path": "rag_first"},
        rag_plan = {
            "recommendedPath": "rag_first",
            "readyForRetrieval": False,
        },
        fine_tuning_plan = {
            "recommendedPath": "guided_fine_tuning",
            "method": {"type": "cloud_qlora"},
            "resourceTargetPlan": {"cloudTrainingAllowed": True},
            "approval": {"readyToRequest": True},
        },
        preload_plan = {},
        codex_pipeline_plan = {},
        optimization_plan = {},
        latest_benchmark_run = {"id": "bench-ok", "benchmark": {}},
    )
    spec_plan = cognix_worker_queue.build_worker_job_spec_plan(
        objective = "Prepare RAG indexing and cloud training",
        project_id = "project-ai",
        worker_queue_plan = queue_plan,
        rag_indexing_plan = {
            "status": "ready",
            "readyToIndexCount": 1,
            "summary": {"sourceCount": 1, "estimatedChunkCount": 24},
        },
        cloud_handoff_plan = {
            "status": "ready_for_export",
            "readyToExport": True,
            "target": {"id": "kaggle", "exportFormat": "kaggle_kernel_plan"},
            "artifactManifest": [{"path": "CogniX_training_notebook.ipynb"}],
        },
        preload_plan = {},
    )

    contract = cognix_worker_queue.build_worker_enqueue_contract(
        job_spec_plan = spec_plan,
        confirmation_id = "conf_worker_123",
        request_id = "req_worker_123",
    )

    assert contract["enqueueContractVersion"] == "cognix_worker_enqueue_contract_v1"
    assert contract["status"] == "ready_for_queue_review"
    assert contract["readyForQueueReview"] is True
    assert contract["readyForJobEnqueue"] is False
    assert contract["policies"]["idempotencyKeyRequired"] is True
    assert contract["policies"]["deadLetterQueueRequired"] is True
    assert contract["policies"]["retryBudgetRequired"] is True
    assert contract["sideEffects"]["jobEnqueue"] is False
    assert contract["sideEffects"]["workerStart"] is False
    assert contract["sideEffects"]["cloudTrainingJob"] is False

    job_contracts = {item["jobType"]: item for item in contract["jobContracts"]}
    assert {"rag_indexing", "cloud_training_job"}.issubset(job_contracts)
    cloud = job_contracts["cloud_training_job"]
    assert cloud["readyForQueueReview"] is True
    assert cloud["readyForJobEnqueue"] is False
    assert cloud["retryPolicy"]["maxAttempts"] == 3
    assert cloud["deadLetterPolicy"]["enabled"] is True
    assert cloud["payloadBoundary"]["rawPayloadIncluded"] is False
    assert cloud["payloadBoundary"]["secretValuesIncluded"] is False
    assert all(gate["passed"] for gate in cloud["gates"])
    assert all(item.startswith("cognix:project-ai:") for item in contract["summary"]["idempotencyKeys"])


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


def test_worker_registry_endpoint_logs_audited_dry_run():
    seed_accounts()

    body = run_async(cognix_routes.worker_queue_registry(current_subject = "alice"))

    assert body["auditLogId"].startswith("aud_")
    assert body["registry"]["workerQueueVersion"] == "cognix_worker_queue_v1"
    assert body["registry"]["sideEffects"]["jobEnqueue"] is False
    assert any(item["id"] == "cloud_training" for item in body["registry"]["queues"])

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "worker_queue_registry_built"
    assert log["resourceType"] == "cognix_worker_queue_registry"
    assert log["metadata"]["sideEffects"]["workerStart"] is False


def test_worker_job_spec_endpoint_builds_cloud_specs_without_enqueueing(monkeypatch):
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
        cognix_routes.worker_job_spec_plan(
            cognix_routes.WorkerJobSpecPlanRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                project_type = "education",
                project_id = "project-training",
                target_id = "kaggle",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 500000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 42,
                    "license": "mit",
                    "containsSensitiveData": False,
                },
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    spec_plan = body["workerJobSpecPlan"]
    specs = {item["jobType"]: item for item in spec_plan["jobSpecs"]}
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_worker_queue_v1"
    assert spec_plan["jobSpecVersion"] == "cognix_worker_job_spec_v1"
    assert "cloud_training_job" in specs
    assert specs["cloud_training_job"]["queueId"] == "cloud_training"
    assert specs["cloud_training_job"]["payloadSummary"]["targetId"] == "kaggle"
    assert specs["cloud_training_job"]["payloadSummary"]["rawSecretsIncluded"] is False
    assert spec_plan["sideEffects"]["jobEnqueue"] is False
    assert spec_plan["sideEffects"]["cloudTrainingJob"] is False
    assert spec_plan["sideEffects"]["workerStart"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "worker_job_spec_plan_built"
    assert "cloud_training_job" in log["metadata"]["jobTypes"]
    assert log["metadata"]["sideEffects"]["jobEnqueue"] is False


def test_worker_job_spec_endpoint_accepts_connector_sync_plan_without_raw_filters(monkeypatch):
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
    connector_plan = cognix_rag_planner.build_rag_connector_sync_plan(
        username = "alice",
        connector_id = "google-drive",
        project_id = "project-rag",
        objective = "Synchroniser Drive vers RAG",
        source_filters = {"folderId": "private-folder", "mimeTypes": ["pdf"]},
        max_documents = 12,
        has_developer_mode = True,
        granted_permissions = {"drive:read", "rag:write"},
    )

    body = run_async(
        cognix_routes.worker_job_spec_plan(
            cognix_routes.WorkerJobSpecPlanRequest(
                objective = "Synchroniser Drive vers RAG",
                project_id = "project-rag",
                ragConnectorSyncPlan = connector_plan,
            ),
            current_subject = "alice",
        )
    )

    specs = {item["jobType"]: item for item in body["workerJobSpecPlan"]["jobSpecs"]}
    assert body["auditLogId"].startswith("aud_")
    assert "rag_connector_sync" in specs
    assert specs["rag_connector_sync"]["queueId"] == "io_bound"
    assert specs["rag_connector_sync"]["payloadSummary"]["rawFilterValuesIncluded"] is False
    assert "private-folder" not in str(specs["rag_connector_sync"]["payloadSummary"])
    assert body["sideEffects"]["jobEnqueue"] is False
    assert body["sideEffects"]["connectorSync"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "worker_job_spec_plan_built"
    assert "rag_connector_sync" in log["metadata"]["jobTypes"]
    assert "private-folder" not in log["metadataJson"]


def test_worker_job_spec_endpoint_accepts_tool_execution_handoff_without_raw_payload(monkeypatch):
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
    tool_plan = cognix_tool_registry.plan_tool_action(
        tool_id = "codex-secure-agent",
        action_id = "plan_feature",
        username = "alice",
        has_developer_mode = True,
        granted_permissions = set(),
    )
    tool_plan = cognix_tool_registry.apply_rate_limit_result(
        tool_plan,
        {
            "allowed": True,
            "remaining": 19,
            "resetAt": "2026-06-29T00:00:00Z",
        },
    )
    handoff = cognix_tool_registry.build_tool_execution_handoff(
        plan = tool_plan,
        request_id = "req_tool_worker_endpoint",
    )

    body = run_async(
        cognix_routes.worker_job_spec_plan(
            cognix_routes.WorkerJobSpecPlanRequest(
                objective = "Planifier une action outil via worker",
                project_id = "project-tools",
                toolExecutionHandoff = handoff,
            ),
            current_subject = "alice",
        )
    )

    specs = {item["jobType"]: item for item in body["workerJobSpecPlan"]["jobSpecs"]}
    assert body["auditLogId"].startswith("aud_")
    assert "tool_execution" in specs
    assert specs["tool_execution"]["queueId"] == "tool_execution"
    assert specs["tool_execution"]["payloadSummary"]["toolId"] == "codex-secure-agent"
    assert specs["tool_execution"]["payloadSummary"]["rawPayloadIncluded"] is False
    assert specs["tool_execution"]["payloadSummary"]["rawToolPayloadIncluded"] is False
    assert specs["tool_execution"]["payloadSummary"]["secretValuesIncluded"] is False
    assert body["sideEffects"]["jobEnqueue"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["secretRead"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "worker_job_spec_plan_built"
    assert "tool_execution" in log["metadata"]["jobTypes"]
    assert "access_token" not in log["metadataJson"].lower()
    assert "secret_value" not in log["metadataJson"].lower()


def test_worker_enqueue_contract_endpoint_logs_retry_policy_without_enqueueing(monkeypatch):
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
        cognix_routes.worker_enqueue_contract(
            cognix_routes.WorkerEnqueueContractRequest(
                objective = "Je veux fine-tuning LoRA pour specialiser CogniX sur mon style",
                project_type = "education",
                project_id = "project-training",
                target_id = "kaggle",
                confirmation_id = "conf_cloud_training",
                request_id = "req_cloud_training",
                dataset = {
                    "format": "jsonl",
                    "sampleCount": 1200,
                    "estimatedTokens": 500000,
                    "duplicateRatio": 0.01,
                    "invalidRows": 0,
                    "averageResponseTokens": 42,
                    "license": "mit",
                    "containsSensitiveData": False,
                },
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    contract = body["workerEnqueueContract"]
    job_contracts = {item["jobType"]: item for item in contract["jobContracts"]}
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_worker_enqueue_contract_v1"
    assert contract["enqueueContractVersion"] == "cognix_worker_enqueue_contract_v1"
    assert contract["readyForQueueReview"] is True
    assert contract["readyForJobEnqueue"] is False
    assert "cloud_training_job" in job_contracts
    assert job_contracts["cloud_training_job"]["retryPolicy"]["backoff"] == "exponential_jitter"
    assert job_contracts["cloud_training_job"]["deadLetterPolicy"]["storeSanitizedPayloadOnly"] is True
    assert job_contracts["cloud_training_job"]["payloadBoundary"]["secretValuesIncluded"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["cloudTrainingJob"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "worker_enqueue_contract_built"
    assert log["resourceType"] == "cognix_worker_enqueue_contract"
    assert log["metadata"]["enqueueContractVersion"] == "cognix_worker_enqueue_contract_v1"
    assert log["metadata"]["readyForJobEnqueue"] is False
    assert log["metadata"]["sideEffects"]["jobEnqueue"] is False
    assert "secret_value" not in log["metadataJson"].lower()
    assert "raw_payload" not in log["metadataJson"].lower()


def test_memory_manager_plans_central_layers_without_writes():
    context_plan = cognix_context_manager.build_context_plan(
        current_subject = "alice",
        objective = "Resume mes documents de cours",
        user_memory = {"content": "Reponds en francais et sois pedagogique."},
        project = {"id": "project-cours", "name": "Cours", "instructions": "Cite les sources."},
        project_id = "project-cours",
        task_strategy = {"path": "rag_first"},
        recommendation = {"memoryFit": {"level": "ok"}},
    )
    plan = cognix_memory_manager.build_memory_plan(
        username = "alice",
        objective = "Resume mes documents de cours",
        project_id = "project-cours",
        project_type = "education",
        user_memory = {"content": "Reponds en francais et sois pedagogique."},
        project = {"id": "project-cours", "name": "Cours", "instructions": "Cite les sources."},
        conversation_summary = "",
        recent_message_count = 12,
        library_items = [{"id": "lib_1", "kind": "document", "name": "cours.pdf"}],
        hardware = stub_hardware_profile(),
        latest_benchmark_run = {"id": "bench_1", "benchmark": {"benchmarkVersion": "cognix_benchmark_v1"}},
        classification = {"selectedDomain": "education", "needsClarification": False},
        task_strategy = {"path": "rag_first"},
        context_plan = context_plan,
    )

    assert plan["memoryManagerVersion"] == "cognix_memory_manager_v1"
    assert plan["mode"] == "dry_run"
    assert plan["targetDomain"] == "education"
    assert {"user_memory", "project_memory", "document_memory", "technical_memory"}.issubset(
        set(plan["readyLayerIds"])
    )
    assert "conversation_summary" in plan["requiredLayerIds"]
    assert plan["privacyPlan"]["rawHistoryAllowed"] is False
    assert plan["privacyPlan"]["memoryScopesIsolated"] is True
    assert any(item["id"] == "summarize_conversation" and item["recommended"] for item in plan["capturePlan"])
    assert plan["sideEffects"]["memoryWrite"] is False
    assert plan["sideEffects"]["summaryWrite"] is False
    assert plan["sideEffects"]["documentRetrieval"] is False
    assert plan["sideEffects"]["modelLoad"] is False


def test_memory_plan_endpoint_logs_audited_dry_run(monkeypatch):
    seed_accounts()
    now_ms = int(time.time() * 1000)
    studio_db_storage.upsert_chat_project(
        {
            "id": "project-memory",
            "name": "Cours IA",
            "instructions": "Garde les citations et separe les hypotheses.",
            "archived": False,
            "createdAt": now_ms,
            "updatedAt": now_ms,
        },
        owner_username = "alice",
    )
    cognix_db.update_context_memory(
        "alice",
        "Prefere les explications courtes avec exemples.",
        "alice",
    )
    cognix_db.create_library_item(
        "alice",
        kind = "document",
        name = "cours.pdf",
        source = "upload",
        metadata = {"subject": "ia"},
    )
    monkeypatch.setattr(cognix_routes.cognix_hardware, "get_hardware_profile", stub_hardware_profile)
    monkeypatch.setattr(cognix_routes.cognix_recommender, "build_model_recommendation", stub_recommendation)

    body = run_async(
        cognix_routes.memory_plan(
            cognix_routes.MemoryPlanRequest(
                objective = "Je veux repondre a partir de mes PDF de cours",
                projectId = "project-memory",
                projectType = "education",
                recentMessageCount = 14,
            ),
            current_subject = "alice",
        )
    )

    plan = body["memoryPlan"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_memory_manager_v1"
    assert "user_memory" in plan["readyLayerIds"]
    assert "project_memory" in plan["readyLayerIds"]
    assert plan["contextBridge"]["rawHistoryAllowed"] is False
    assert plan["sideEffects"]["memoryWrite"] is False
    assert plan["sideEffects"]["documentRetrieval"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "memory_plan_built"
    assert log["resourceType"] == "cognix_memory"
    assert log["metadata"]["memoryManagerVersion"] == "cognix_memory_manager_v1"
    assert "technical_memory" in log["metadata"]["requiredLayerIds"]
    assert log["metadata"]["sideEffects"]["memoryWrite"] is False


def test_research_watch_registry_and_plan_require_benchmark_evidence():
    registry = cognix_research_watch.build_research_watch_registry()
    plan = cognix_research_watch.build_research_integration_plan(
        objective = "Evaluer speculative decoding pour reduire la latence CogniX",
        technique_name = "Speculative decoding",
        source_name = "DeepSeek",
        category = "inference_optimization",
        claimed_benefit = "latence plus faible et vitesse plus haute",
        target_module = "cognix-runtime-adapter",
        risk_tolerance = "low",
        hardware = stub_hardware_profile(),
        latest_benchmark_run = None,
        recommendation = {"providerType": "ollama"},
    )

    assert registry["researchWatchVersion"] == "cognix_research_watch_v1"
    assert "DeepSeek" in registry["summary"]["watchedLabs"]
    assert registry["policies"]["hypeOnlyAdoptionAllowed"] is False
    assert registry["sideEffects"]["networkResearch"] is False
    assert plan["researchWatchVersion"] == "cognix_research_watch_v1"
    assert plan["mode"] == "dry_run"
    assert plan["source"]["id"] == "deepseek"
    assert plan["category"]["id"] == "inference_optimization"
    assert plan["recommendedAction"] == "benchmark_required"
    assert "benchmark_before_after" in plan["blockedGateIds"]
    assert "speed" in plan["measurableGains"]
    assert plan["benchmarkPolicy"]["benchmarkRunWillStart"] is False
    assert plan["hypeFilter"]["hypeOnlyAdoptionAllowed"] is False
    assert plan["sideEffects"]["benchmarkRun"] is False
    assert plan["sideEffects"]["modelLoad"] is False


def test_research_assistant_plans_topic_and_report_without_network_or_generation():
    blueprint = cognix_research_watch.build_research_assistant_blueprint()
    topic_plan = cognix_research_watch.build_research_topic_plan(
        topic = "optimisations RAG open-weight",
        sources = ["arxiv", "hugging-face-papers", "official-blogs"],
        frequency = "weekly",
        output_format = "technical",
    )
    report_plan = cognix_research_watch.build_research_report_plan(
        topic = "optimisations RAG open-weight",
        items = [
            {
                "title": "New RAG reranker benchmark",
                "summary": "A benchmark compares rerankers for citation accuracy.",
                "source": "arxiv",
                "relevanceScore": 0.91,
            },
            {
                "title": "Open-weight embedding model update",
                "summary": "A model card describes retrieval improvements.",
                "source": "hugging-face-papers",
                "relevanceScore": 0.82,
            },
        ],
        output_format = "technical",
    )

    assert blueprint["researchAssistantVersion"] == "cognix_research_assistant_v1"
    assert "ResearchAssistantService" in blueprint["services"]
    assert topic_plan["collectionPlan"]["sourceCount"] == 3
    assert topic_plan["collectionPlan"]["willFetchNow"] is False
    assert topic_plan["collectionPlan"]["willEnqueueNow"] is False
    assert topic_plan["reportPlan"]["style"] == "cognix_document"
    assert topic_plan["sideEffects"]["networkResearch"] is False
    assert topic_plan["sideEffects"]["jobEnqueue"] is False
    assert report_plan["report"]["sections"][0]["id"] == "key_findings"
    assert report_plan["report"]["comparison"][0]["title"] == "New RAG reranker benchmark"
    assert report_plan["sideEffects"]["generation"] is False
    assert report_plan["sideEffects"]["reportWrite"] is False


def test_research_assistant_endpoints_store_topic_items_report_and_audit():
    seed_accounts()
    topic_body = run_async(
        cognix_routes.plan_research_topic(
            cognix_routes.ResearchTopicPlanRequest(
                topic = "Suis les techniques RAG avec citations",
                sources = ["arxiv", "hugging-face-papers"],
                frequency = "weekly",
                outputFormat = "brief",
                storeTopic = True,
            ),
            current_subject = "alice",
        )
    )

    topic_id = topic_body["topic"]["id"]
    assert topic_id.startswith("rtop_")
    assert topic_body["plannerVersion"] == "cognix_research_assistant_v1"
    assert topic_body["researchTopicPlan"]["collectionPlan"]["willFetchNow"] is False
    assert topic_body["sideEffects"]["networkResearch"] is False
    assert topic_body["sideEffects"]["topicWrite"] is True

    report_body = run_async(
        cognix_routes.plan_research_report(
            cognix_routes.ResearchReportPlanRequest(
                topicId = topic_id,
                items = [
                    {
                        "title": "Citation-aware RAG evaluation",
                        "summary": "Paper compares citation fidelity for retrieval systems.",
                        "source": "arxiv",
                        "relevanceScore": 0.93,
                    },
                    {
                        "title": "Hybrid retrieval model card",
                        "summary": "Model card reports better recall on technical documents.",
                        "source": "hugging-face-papers",
                        "relevanceScore": 0.86,
                    },
                ],
                storeItems = True,
                storeReport = True,
            ),
            current_subject = "alice",
        )
    )

    topics = run_async(cognix_routes.research_topics(current_subject = "alice"))
    reports = run_async(cognix_routes.my_research(current_subject = "alice"))
    stored_items = cognix_db.list_research_items("alice", topic_id = topic_id)
    assert topics["count"] == 1
    assert report_body["report"]["id"].startswith("res_")
    assert len(report_body["items"]) == 2
    assert len(stored_items) == 2
    assert reports["reports"][0]["id"] == report_body["report"]["id"]
    assert report_body["sideEffects"]["itemWrite"] is True
    assert report_body["sideEffects"]["reportWrite"] is True
    assert report_body["sideEffects"]["generation"] is False
    assert report_body["sideEffects"]["networkResearch"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    actions = {item["action"]: item for item in admin_read["logs"]}
    assert "research_topic_planned" in actions
    assert "research_report_plan_built" in actions
    assert actions["research_report_plan_built"]["metadata"]["sideEffects"]["networkResearch"] is False
    assert actions["research_report_plan_built"]["metadata"]["itemCount"] == 2


def test_research_integration_endpoint_logs_audited_dry_run(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(cognix_routes.cognix_hardware, "get_hardware_profile", stub_hardware_profile)
    monkeypatch.setattr(cognix_routes.cognix_recommender, "build_model_recommendation", stub_recommendation)

    body = run_async(
        cognix_routes.research_integration_plan(
            cognix_routes.ResearchIntegrationPlanRequest(
                objective = "Tester prompt caching pour eviter de recalculer le meme contexte",
                techniqueName = "Prompt caching",
                sourceName = "Google DeepMind",
                category = "inference_optimization",
                claimedBenefit = "moins de latence et plus de stabilite",
                targetModule = "cognix-optimization-planner",
                riskTolerance = "low",
            ),
            current_subject = "alice",
        )
    )

    plan = body["researchIntegrationPlan"]
    assert body["plannerVersion"] == "cognix_research_watch_v1"
    assert body["auditLogId"].startswith("aud_")
    assert plan["recommendedAction"] == "benchmark_required"
    assert plan["experimentalModulePolicy"]["directProductionActivationAllowed"] is False
    assert plan["sideEffects"]["networkResearch"] is False
    assert plan["sideEffects"]["codeModification"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "research_integration_plan_built"
    assert log["resourceType"] == "cognix_research_watch"
    assert log["metadata"]["researchWatchVersion"] == "cognix_research_watch_v1"
    assert log["metadata"]["recommendedAction"] == "benchmark_required"
    assert log["metadata"]["sideEffects"]["networkResearch"] is False


def test_evolution_engine_blueprint_and_experiment_require_human_approval():
    blueprint = cognix_evolution_engine.build_evolution_blueprint()
    item_plan = cognix_evolution_engine.build_evolution_item_plan(
        technique_name = "Speculative decoding KV cache",
        source_name = "DeepSeek research",
        claimed_benefit = "+31% vitesse sur prompts longs",
        evidence = ["benchmark public", "reference repo"],
        risk_tolerance = "balanced",
    )
    experiment_plan = cognix_evolution_engine.build_evolution_experiment_plan(
        item_plan = item_plan,
        expected_gain_percent = 31,
        benchmark_metric = "tokens_per_second",
        sandbox_target = "runtime_adapter",
    )

    assert blueprint["evolutionEngineVersion"] == "cognix_evolution_engine_v1"
    assert blueprint["rules"]["automaticProductionIntegrationAllowed"] is False
    assert blueprint["rules"]["automaticUxModificationAllowed"] is False
    assert blueprint["rules"]["sandboxRequired"] is True
    assert blueprint["rules"]["humanApprovalRequired"] is True
    assert "EvolutionEngine" in blueprint["services"]
    assert item_plan["technique"]["category"] == "inference_optimization"
    assert item_plan["gates"]["sandboxRequired"] is True
    assert item_plan["sideEffects"]["productionIntegration"] is False
    assert experiment_plan["prototypePlan"]["willModifyCodeNow"] is False
    assert experiment_plan["sandboxPlan"]["willRunNow"] is False
    assert experiment_plan["benchmarkPlan"]["willRunNow"] is False
    assert experiment_plan["integrationProposal"]["status"] == "requires_human_approval"
    assert experiment_plan["integrationProposal"]["automaticProductionIntegrationAllowed"] is False
    assert experiment_plan["sideEffects"]["codeModification"] is False
    assert experiment_plan["sideEffects"]["productionIntegration"] is False


def test_evolution_endpoints_store_item_experiment_proposal_without_integration():
    seed_accounts()

    item_body = run_async(
        cognix_routes.evolution_item_plan(
            cognix_routes.EvolutionItemPlanRequest(
                techniqueName = "Speculative decoding KV cache",
                sourceName = "DeepSeek research",
                claimedBenefit = "+31% vitesse sur prompts longs",
                evidence = ["benchmark public", "reference repo"],
                riskTolerance = "balanced",
                storeItem = True,
            ),
            current_subject = "alice",
        )
    )
    item_id = item_body["item"]["id"]
    experiment_body = run_async(
        cognix_routes.evolution_experiment_plan(
            cognix_routes.EvolutionExperimentPlanRequest(
                itemId = item_id,
                expectedGainPercent = 31,
                benchmarkMetric = "tokens_per_second",
                sandboxTarget = "runtime_adapter",
                storeExperiment = True,
            ),
            current_subject = "alice",
        )
    )
    listed = run_async(cognix_routes.evolution_items(current_subject = "alice"))
    proposals = run_async(cognix_routes.evolution_proposals(current_subject = "alice"))
    bob_items = run_async(cognix_routes.evolution_items(current_subject = "bob"))

    assert item_id.startswith("evo_")
    assert item_body["sideEffects"]["evolutionItemWrite"] is True
    assert item_body["sideEffects"]["productionIntegration"] is False
    assert item_body["sideEffects"]["codeModification"] is False
    assert experiment_body["experiment"]["id"].startswith("evexp_")
    assert len(experiment_body["benchmarkResults"]) == 1
    assert len(experiment_body["proposals"]) == 1
    assert experiment_body["proposals"][0]["status"] == "requires_human_approval"
    assert experiment_body["sideEffects"]["experimentWrite"] is True
    assert experiment_body["sideEffects"]["benchmarkResultWrite"] is True
    assert experiment_body["sideEffects"]["proposalWrite"] is True
    assert experiment_body["sideEffects"]["productionIntegration"] is False
    assert experiment_body["sideEffects"]["uxModification"] is False
    assert listed["items"][0]["id"] == item_id
    assert proposals["proposals"][0]["itemId"] == item_id
    assert bob_items["items"] == []

    logs = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"]
    actions = {item["action"] for item in logs}
    assert {"evolution_item_planned", "evolution_experiment_planned"}.issubset(actions)


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
    assert packet["contextBoundaryContract"]["contractVersion"] == "cognix_context_boundary_contract_v1"
    assert packet["contextBoundaryContract"]["inputPolicy"]["rawHistoryAllowed"] is False
    assert packet["contextBoundaryContract"]["executionGate"]["frontendRawHistoryUploadAllowed"] is False
    assert packet["contextBoundaryContract"]["executionGate"]["memoryWriteAllowedNow"] is False
    assert packet["mode"] == "minimal"
    assert packet["includedSectionIds"] == ["user_memory", "project_instructions"]
    assert "<cognix_context>" in packet["systemInstruction"]
    assert "<user_memory>" in packet["systemInstruction"]
    assert "<project_instructions>" in packet["systemInstruction"]
    assert packet["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
    assert packet["contextPlan"]["contextBoundaryContract"]["contractVersion"] == "cognix_context_boundary_contract_v1"
    assert packet["sideEffects"]["modelLoad"] is False
    assert packet["sideEffects"]["generation"] is False
    assert packet["sideEffects"]["networkModelCall"] is False
    assert packet["sideEffects"]["memoryWrite"] is False


def test_context_manager_injects_rag_retrieval_packet_with_citations_without_retrieval():
    rag_packet = cognix_rag_planner.build_rag_retrieval_packet(
        username = "alice",
        objective = "Explique le RAG avec citations fiables",
        project_id = "project-rag",
        sources = [
            {
                "id": "cours-rag",
                "type": "pdf",
                "indexed": True,
                "title": "Cours RAG",
                "chunks": [
                    {
                        "id": "chunk-rag",
                        "page": 4,
                        "content": "Le RAG injecte des passages cites pour ancrer la reponse.",
                    }
                ],
            }
        ],
        top_k = 1,
    )

    packet = cognix_context_manager.build_context_packet(
        current_subject = "alice",
        rag_retrieval_packet = rag_packet,
        project_id = "project-rag",
        objective = "Explique le RAG",
    )

    assert packet["ragPacket"]["retrievalPacketVersion"] == "cognix_rag_retrieval_packet_v1"
    assert packet["ragPacket"]["readyForInjection"] is True
    assert packet["ragPacket"]["citationCount"] == 1
    assert "rag_chunks" in packet["includedSectionIds"]
    assert "rag_chunks" in packet["contextPlan"]["includedChannelIds"]
    assert packet["contextPlan"]["assemblyStrategy"] == "rag_augmented_context"
    assert packet["contextBoundaryContract"]["contractVersion"] == "cognix_context_boundary_contract_v1"
    assert packet["contextBoundaryContract"]["executionGate"]["ragRetrievalAllowedNow"] is False
    assert "[S1]" in packet["systemInstruction"]
    assert "<rag_chunks>" in packet["systemInstruction"]
    assert packet["contextPlan"]["sideEffects"]["ragRetrieval"] is False
    assert packet["sideEffects"]["ragRetrieval"] is False
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
    assert body["contextPlan"]["assemblyStrategy"] == "memory_project_recent"
    assert body["contextBoundaryContract"]["contractVersion"] == "cognix_context_boundary_contract_v1"
    assert body["contextBoundaryContract"]["executionGate"]["frontendRawHistoryUploadAllowed"] is False
    assert body["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
    assert "Reponds en francais" in body["systemInstruction"]
    assert "Priorite a la securite" in body["systemInstruction"]
    assert body["sideEffects"]["networkModelCall"] is False


def test_context_pack_endpoint_injects_rag_packet_without_audit_leak():
    seed_accounts()
    rag_packet = cognix_rag_planner.build_rag_retrieval_packet(
        username = "alice",
        objective = "Explique le RAG avec citations fiables",
        project_id = "project-rag",
        sources = [
            {
                "id": "cours-rag",
                "type": "pdf",
                "indexed": True,
                "title": "Cours RAG",
                "chunks": [
                    {
                        "id": "chunk-rag",
                        "page": 4,
                        "content": "Le RAG injecte des passages cites pour ancrer la reponse.",
                    }
                ],
            }
        ],
        top_k = 1,
    )

    body = run_async(
        cognix_routes.build_context_pack(
            cognix_routes.ContextPackRequest(
                objective = "Explique le RAG",
                project_id = "project-rag",
                rag_retrieval_packet = rag_packet,
            ),
            current_subject = "alice",
        )
    )

    assert body["ragPacket"]["readyForInjection"] is True
    assert "rag_chunks" in body["includedSectionIds"]
    assert "[S1]" in body["systemInstruction"]
    assert body["contextPlan"]["assemblyStrategy"] == "rag_augmented_context"
    assert body["sideEffects"]["ragRetrieval"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = next(item for item in admin_read["logs"] if item["id"] == body["auditLogId"])
    assert log["metadata"]["hasRagPacket"] is True
    assert log["metadata"]["contextBoundaryContractVersion"] == "cognix_context_boundary_contract_v1"
    assert log["metadata"]["frontendRawHistoryUploadAllowed"] is False
    assert log["metadata"]["ragCitationCount"] == 1
    assert log["metadata"]["ragSelectedChunkCount"] == 1
    assert "passages cites" not in log["metadataJson"]


def test_context_pack_endpoint_injects_project_compressed_context_without_audit_leak():
    seed_accounts()
    now_ms = int(time.time() * 1000)
    studio_db_storage.upsert_chat_project(
        {
            "id": "project-context",
            "name": "Projet Context",
            "instructions": "Toujours garder les decisions de contexte.",
            "archived": False,
            "createdAt": now_ms,
            "updatedAt": now_ms,
        },
        owner_username = "alice",
    )
    global_plan = cognix_prompt_compression.build_prompt_compression_plan(
        username = "alice",
        context = "Global summary should not override the project summary.",
        objective = "context",
        target_tokens = 80,
    )
    cognix_db.create_compressed_context("alice", plan = global_plan)
    project_plan = cognix_prompt_compression.build_prompt_compression_plan(
        username = "alice",
        project_id = "project-context",
        context = "Decision importante: utiliser le resume compresse du projet pour reduire les tokens.",
        objective = "resume compresse projet",
        target_tokens = 80,
    )
    stored_project_context = cognix_db.create_compressed_context(
        "alice",
        plan = project_plan,
        project_id = "project-context",
    )

    body = run_async(
        cognix_routes.build_context_pack(
            cognix_routes.ContextPackRequest(
                objective = "Continue le projet avec le bon contexte",
                project_id = "project-context",
            ),
            current_subject = "alice",
        )
    )

    assert body["compressedContext"]["id"] == stored_project_context["id"]
    assert "conversation_summary" in body["includedSectionIds"]
    assert "conversation_summary" in body["contextPlan"]["includedChannelIds"]
    assert body["contextPlan"]["tokenBudget"]["rawHistoryAllowed"] is False
    assert "resume compresse du projet" in body["systemInstruction"]
    assert "Global summary" not in body["systemInstruction"]
    assert body["sideEffects"]["networkModelCall"] is False
    assert body["sideEffects"]["contextMutation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = next(item for item in admin_read["logs"] if item["id"] == body["auditLogId"])
    assert log["metadata"]["compressedContextId"] == stored_project_context["id"]
    assert log["metadata"]["hasConversationSummary"] is True
    assert "resume compresse du projet" not in log["metadataJson"]


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


def test_audit_governance_contract_hashes_redacted_logs_without_mutation():
    seed_accounts()
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = "alice",
        action = "audit_governance_test",
        resource_type = "test",
        resource_id = "secret-resource",
        severity = "warning",
        metadata = {
            "apiKey": "sk-secret-should-not-survive",
            "url": "https://user:password@example.test/path?token=secret-token",
            "safe": "visible",
        },
    )
    logs = cognix_db.list_audit_logs(limit = 10)

    contract = cognix_db.build_audit_governance_contract(logs, max_entries = 3)

    assert contract["contractVersion"] == "cognix_audit_governance_contract_v1"
    assert contract["mode"] == "audit_integrity_retention_dry_run"
    assert contract["retentionPolicy"]["maxEntries"] == 3
    assert contract["retentionPolicy"]["willPruneNow"] is False
    assert contract["redactionPolicy"]["redactionEnabled"] is True
    assert contract["redactionPolicy"]["rawSecretValuesAllowed"] is False
    assert contract["redactionPolicy"]["metadataJsonReturnedInContract"] is False
    assert contract["integrity"]["algorithm"] == "sha256_previous_hash_chain"
    assert len(contract["integrity"]["chainHead"]) == 64
    assert contract["integrity"]["checkpointCount"] >= 1
    assert contract["sideEffects"]["auditWrite"] is False
    assert contract["sideEffects"]["auditPrune"] is False
    assert "sk-secret-should-not-survive" not in str(logs)
    assert "secret-token" not in str(logs)
    assert "sk-secret-should-not-survive" not in str(contract)
    assert "secret-token" not in str(contract)


def test_audit_governance_contract_endpoint_is_admin_only_and_read_only():
    seed_accounts()
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = "alice",
        action = "audit_governance_endpoint_test",
        resource_type = "test",
        metadata = {"secretValue": "secret_value"},
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_audit_governance_contract(current_subject = "alice"))
    assert user_read.value.status_code == 403

    body = run_async(
        cognix_routes.admin_audit_governance_contract(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    contract = body["auditGovernanceContract"]
    assert body["plannerVersion"] == "cognix_audit_governance_contract_v1"
    assert contract["integrity"]["logCount"] >= 1
    assert contract["auditReadPolicy"]["adminOnly"] is True
    assert body["sideEffects"]["auditWrite"] is False
    assert body["sideEffects"]["auditPrune"] is False
    assert "secret_value" not in str(contract)


def test_database_blueprint_maps_roadmap_tables_without_schema_mutation():
    blueprint = cognix_database_blueprint.build_database_blueprint(
        auth_tables = {"auth_user", "refresh_tokens"},
        studio_tables = {
            "chat_projects",
            "chat_threads",
            "chat_messages",
            "cognix_audit_logs",
            "cognix_router_logs",
            "cognix_token_usage_events",
            "cognix_model_performance_logs",
            "cognix_context_memory",
            "cognix_generated_datasets",
        },
        rag_tables = {"documents", "chunks"},
    )

    assert blueprint["databaseBlueprintVersion"] == "cognix_database_blueprint_v1"
    assert blueprint["mode"] == "database_blueprint_read_only"
    assert blueprint["summary"]["roadmapTableCount"] == 25
    assert blueprint["summary"]["migrationExecutionAllowed"] is False
    assert blueprint["summary"]["destructiveChangeAllowed"] is False
    assert blueprint["coverage"]["readyForMvpSchema"] is True
    assert {"users", "projects", "chats", "messages", "documents", "document_chunks", "audit_logs"}.issubset(
        set(blueprint["coverage"]["availableLogicalTables"])
    )
    assert "datasets" in blueprint["coverage"]["partialLogicalTables"]
    assert "workspaces" in blueprint["coverage"]["plannedLogicalTables"]
    tables = {item["logicalName"]: item for item in blueprint["logicalTables"]}
    assert tables["users"]["presentCanonicalTables"] == ["auth_user"]
    assert tables["documents"]["presentCanonicalTables"] == ["documents"]
    assert tables["document_chunks"]["presentCanonicalTables"] == ["chunks"]
    assert tables["billing_events"]["runtimeMigrationAllowed"] is False
    assert blueprint["dataIsolationPolicy"]["authDatabaseSeparated"] is True
    assert blueprint["dataIsolationPolicy"]["ragDatabaseSeparated"] is True
    assert blueprint["migrationPolicy"]["destructiveMigrationAllowed"] is False
    assert blueprint["sideEffects"]["schemaRead"] is True
    assert blueprint["sideEffects"]["databaseWrite"] is False
    assert blueprint["sideEffects"]["migrationRun"] is False
    assert blueprint["sideEffects"]["tableCreate"] is False
    assert blueprint["sideEffects"]["auditWrite"] is False


def test_database_blueprint_endpoint_is_admin_only_and_read_only():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_database_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    body = run_async(cognix_routes.admin_database_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))

    blueprint = body["databaseBlueprint"]
    assert body["plannerVersion"] == "cognix_database_blueprint_v1"
    assert blueprint["sourceOfTruth"] == "roadmap_section_27"
    assert "users" in blueprint["coverage"]["requiredLogicalTables"]
    assert "audit_logs" in blueprint["coverage"]["requiredLogicalTables"]
    assert blueprint["schemaSources"]["rawCreateSqlReturned"] is False
    assert body["sideEffects"]["databaseWrite"] is False
    assert body["sideEffects"]["migrationRun"] is False
    assert body["sideEffects"]["tableDrop"] is False
    assert body["sideEffects"]["auditWrite"] is False


def test_api_surface_contract_maps_roadmap_endpoints_without_route_mutation():
    registered_routes = [
        {"path": "/api/inference/chat/completions", "methods": ["POST"]},
        {"path": "/api/inference/generate/stream", "methods": ["POST"]},
        {"path": "/api/cognix/router/classify", "methods": ["POST"]},
        {"path": "/api/cognix/models/install-contract", "methods": ["POST"]},
        {"path": "/api/inference/load", "methods": ["POST"]},
        {"path": "/api/inference/unload", "methods": ["POST"]},
        {"path": "/api/models/list", "methods": ["GET"]},
        {"path": "/api/cognix/models/favorites", "methods": ["GET"]},
        {"path": "/api/cognix/models/default", "methods": ["GET"]},
        {"path": "/api/cognix/models/quick-switcher", "methods": ["GET"]},
        {"path": "/api/cognix/hardware/profile", "methods": ["GET"]},
        {"path": "/api/cognix/benchmark/run", "methods": ["POST"]},
        {"path": "/api/cognix/rag/indexing-plan", "methods": ["POST"]},
        {"path": "/api/train/start", "methods": ["POST"]},
        {"path": "/api/train/runs", "methods": ["GET"]},
        {"path": "/api/cognix/tools/execution-handoff", "methods": ["POST"]},
        {"path": "/api/cognix/admin/audit-logs", "methods": ["GET"]},
        {"path": "/api/cognix/codex/pipeline-plan", "methods": ["POST"]},
    ]

    contract = cognix_api_surface.build_api_surface_contract(registered_routes)

    assert contract["apiSurfaceContractVersion"] == "cognix_api_surface_contract_v1"
    assert contract["mode"] == "api_surface_contract_read_only"
    assert contract["sourceOfTruth"] == "roadmap_section_28"
    assert contract["summary"]["recommendedEndpointCount"] == len(cognix_api_surface.RECOMMENDED_ENDPOINTS)
    assert contract["summary"]["plannedEndpointCount"] == 0
    assert contract["summary"]["readyForMvpApi"] is True
    endpoints = {item["path"]: item for item in contract["endpoints"]}
    assert endpoints["/api/chat"]["status"] == "equivalent"
    assert endpoints["/api/chat"]["matchedRoute"] == "POST /api/inference/chat/completions"
    assert endpoints["/api/router/classify"]["matchedRoute"] == "POST /api/cognix/router/classify"
    assert endpoints["/api/tools/execute"]["frontendDirectModelCallAllowed"] is False
    assert contract["policies"]["orchestratorRequiredForGeneration"] is True
    assert contract["policies"]["routeRegistrationAllowedHere"] is False
    assert contract["sideEffects"]["routeRegistration"] is False
    assert contract["sideEffects"]["modelLoad"] is False
    assert contract["sideEffects"]["generation"] is False
    assert contract["sideEffects"]["toolExecution"] is False


def test_registered_api_routes_traverses_included_routers_with_prefixes():
    request = SimpleNamespace(
        app = SimpleNamespace(
            routes = [
                SimpleNamespace(
                    original_router = SimpleNamespace(
                        routes = [
                            SimpleNamespace(path = "/router/classify", methods = {"POST"}),
                            SimpleNamespace(
                                original_router = SimpleNamespace(
                                    routes = [SimpleNamespace(path = "/indexing-plan", methods = {"POST"})]
                                ),
                                include_context = SimpleNamespace(prefix = "/rag"),
                            ),
                        ]
                    ),
                    include_context = SimpleNamespace(prefix = "/api/cognix"),
                )
            ]
        )
    )

    records = cognix_routes._registered_api_routes(request)

    assert {"path": "/api/cognix/router/classify", "methods": ["POST"]} in records
    assert {"path": "/api/cognix/rag/indexing-plan", "methods": ["POST"]} in records


def test_api_surface_contract_endpoint_is_admin_only_and_read_only():
    seed_accounts()
    fake_routes = [
        SimpleNamespace(path = path, methods = {method})
        for method, path in [
            ("POST", "/api/inference/chat/completions"),
            ("POST", "/api/inference/generate/stream"),
            ("POST", "/api/cognix/router/classify"),
            ("POST", "/api/cognix/models/install-contract"),
            ("POST", "/api/inference/load"),
                ("POST", "/api/inference/unload"),
                ("GET", "/api/models/list"),
                ("GET", "/api/cognix/models/favorites"),
                ("GET", "/api/cognix/models/default"),
                ("GET", "/api/cognix/models/quick-switcher"),
                ("GET", "/api/cognix/hardware/profile"),
            ("POST", "/api/cognix/benchmark/run"),
            ("POST", "/api/cognix/rag/indexing-plan"),
            ("POST", "/api/train/start"),
            ("GET", "/api/train/runs"),
            ("POST", "/api/cognix/tools/execution-handoff"),
            ("GET", "/api/cognix/admin/audit-logs"),
            ("POST", "/api/cognix/codex/pipeline-plan"),
        ]
    ]
    request = SimpleNamespace(app = SimpleNamespace(routes = fake_routes))

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_api_surface_contract(request, current_subject = "alice"))
    assert user_read.value.status_code == 403

    body = run_async(
        cognix_routes.admin_api_surface_contract(
            request,
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    contract = body["apiSurfaceContract"]
    assert body["plannerVersion"] == "cognix_api_surface_contract_v1"
    assert contract["summary"]["recommendedEndpointCount"] == len(cognix_api_surface.RECOMMENDED_ENDPOINTS)
    assert contract["coverage"]["missingEndpoints"] == []
    assert body["sideEffects"]["routeRegistration"] is False
    assert body["sideEffects"]["apiMutation"] is False
    assert body["sideEffects"]["generation"] is False
    assert body["sideEffects"]["auditWrite"] is False


def test_mvp_readiness_contract_maps_roadmap_phases_without_mutation():
    registered_routes = [
        {"path": "/api/inference/chat/completions", "methods": ["POST"]},
        {"path": "/api/inference/generate/stream", "methods": ["POST"]},
        {"path": "/api/cognix/router/classify", "methods": ["POST"]},
        {"path": "/api/cognix/models/install-contract", "methods": ["POST"]},
        {"path": "/api/inference/load", "methods": ["POST"]},
        {"path": "/api/inference/unload", "methods": ["POST"]},
        {"path": "/api/models/list", "methods": ["GET"]},
        {"path": "/api/cognix/hardware/profile", "methods": ["GET"]},
        {"path": "/api/cognix/benchmark/run", "methods": ["POST"]},
        {"path": "/api/cognix/rag/indexing-plan", "methods": ["POST"]},
        {"path": "/api/train/start", "methods": ["POST"]},
        {"path": "/api/train/runs", "methods": ["GET"]},
        {"path": "/api/cognix/tools/execution-handoff", "methods": ["POST"]},
        {"path": "/api/cognix/admin/audit-logs", "methods": ["GET"]},
        {"path": "/api/cognix/codex/pipeline-plan", "methods": ["POST"]},
    ]
    api_contract = cognix_api_surface.build_api_surface_contract(registered_routes)
    database_blueprint = cognix_database_blueprint.build_database_blueprint(
        auth_tables = {"auth_user"},
        studio_tables = {
            "chat_projects",
            "chat_threads",
            "chat_messages",
            "cognix_models",
            "cognix_installed_models",
            "cognix_memories",
            "cognix_router_logs",
            "cognix_tool_integrations",
            "cognix_tool_permissions",
            "cognix_audit_logs",
            "cognix_fine_tuning_jobs",
            "cognix_datasets",
            "cognix_lora_adapters",
            "cognix_organizations",
            "cognix_deployment_targets",
        },
        rag_tables = {"documents", "chunks"},
    )
    service_topology = cognix_module_registry.build_module_service_topology()

    contract = cognix_mvp_readiness.build_mvp_readiness_contract(
        api_surface_contract = api_contract,
        database_blueprint = database_blueprint,
        service_topology = service_topology,
    )

    assert contract["mvpReadinessVersion"] == "cognix_mvp_readiness_v1"
    assert contract["mode"] == "mvp_readiness_read_only"
    assert contract["sourceOfTruth"] == "roadmap_section_31"
    assert contract["summary"]["phaseCount"] == 9
    assert contract["summary"]["coreMvpBlocked"] is False
    phases = {item["id"]: item for item in contract["phases"]}
    assert phases["phase_1_core_local"]["status"] == "ready"
    assert phases["phase_3_orchestrator"]["status"] == "partial"
    assert phases["phase_9_native_codex_secure"]["status"] == "partial"
    assert phases["phase_1_core_local"]["missingRequirements"] == []
    assert contract["policies"]["moduleActivationAllowedHere"] is False
    assert contract["policies"]["databaseMigrationAllowedHere"] is False
    assert contract["sideEffects"]["routeRegistration"] is False
    assert contract["sideEffects"]["databaseWrite"] is False
    assert contract["sideEffects"]["jobEnqueue"] is False
    assert contract["sideEffects"]["modelLoad"] is False
    assert contract["sideEffects"]["codeModification"] is False


def test_mvp_readiness_endpoint_is_admin_only_and_read_only():
    seed_accounts()
    request = SimpleNamespace(
        app = SimpleNamespace(
            routes = [
                SimpleNamespace(
                    original_router = SimpleNamespace(
                        routes = [
                            SimpleNamespace(path = "/chat/completions", methods = {"POST"}),
                            SimpleNamespace(path = "/generate/stream", methods = {"POST"}),
                            SimpleNamespace(path = "/load", methods = {"POST"}),
                            SimpleNamespace(path = "/unload", methods = {"POST"}),
                        ]
                    ),
                    include_context = SimpleNamespace(prefix = "/api/inference"),
                ),
                SimpleNamespace(
                    original_router = SimpleNamespace(
                        routes = [
                            SimpleNamespace(path = "/router/classify", methods = {"POST"}),
                            SimpleNamespace(path = "/models/install-contract", methods = {"POST"}),
                            SimpleNamespace(path = "/hardware/profile", methods = {"GET"}),
                            SimpleNamespace(path = "/benchmark/run", methods = {"POST"}),
                            SimpleNamespace(path = "/rag/indexing-plan", methods = {"POST"}),
                            SimpleNamespace(path = "/tools/execution-handoff", methods = {"POST"}),
                            SimpleNamespace(path = "/admin/audit-logs", methods = {"GET"}),
                            SimpleNamespace(path = "/codex/pipeline-plan", methods = {"POST"}),
                        ]
                    ),
                    include_context = SimpleNamespace(prefix = "/api/cognix"),
                ),
                SimpleNamespace(
                    original_router = SimpleNamespace(routes = [SimpleNamespace(path = "/list", methods = {"GET"})]),
                    include_context = SimpleNamespace(prefix = "/api/models"),
                ),
                SimpleNamespace(
                    original_router = SimpleNamespace(
                        routes = [
                            SimpleNamespace(path = "/start", methods = {"POST"}),
                            SimpleNamespace(path = "/runs", methods = {"GET"}),
                        ]
                    ),
                    include_context = SimpleNamespace(prefix = "/api/train"),
                ),
            ]
        )
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_mvp_readiness(request, current_subject = "alice"))
    assert user_read.value.status_code == 403

    body = run_async(
        cognix_routes.admin_mvp_readiness(
            request,
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )

    contract = body["mvpReadiness"]
    assert body["plannerVersion"] == "cognix_mvp_readiness_v1"
    assert contract["summary"]["phaseCount"] == 9
    assert contract["inputContracts"]["apiSurfaceContractVersion"] == "cognix_api_surface_contract_v1"
    assert contract["inputContracts"]["serviceTopologyVersion"] == "cognix_module_service_topology_v1"
    assert body["sideEffects"]["databaseWrite"] is False
    assert body["sideEffects"]["migrationRun"] is False
    assert body["sideEffects"]["jobEnqueue"] is False
    assert body["sideEffects"]["modelLoad"] is False
    assert body["sideEffects"]["codeModification"] is False


def test_audit_log_redacts_sensitive_metadata_before_storage():
    seed_accounts()

    log = cognix_db.create_audit_log(
        username = "alice",
        actor_username = "alice",
        action = "secret_redaction_test",
        resource_type = "test",
        metadata = {
            "access_token": "tok_live_secret_value",
            "apiKey": "sk-testabcdefghijklmnop",
            "s3": {
                "accessKeyId": "AKIA1234567890ABCDEF",
                "secretAccessKey": "aws-secret-access-key",
            },
            "safeLabel": "kept",
            "nested": {
                "password": "plain-password",
                "note": (
                    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
                    "Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ=="
                ),
                "signedUrl": "https://example.test/callback?access_token=tok_query_secret&safe=1",
                "credentialUrl": "https://user:plainpass@example.test/private",
                "assignment": (
                    "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz "
                    "AWS_SECRET_ACCESS_KEY=awssecretfromstring"
                ),
            },
        },
    )

    stored = cognix_db.list_audit_logs(action = "secret_redaction_test", limit = 1)[0]
    metadata_json = stored["metadata_json"].lower()
    assert stored["id"] == log["id"]
    assert stored["metadata"]["safeLabel"] == "kept"
    assert stored["metadata"]["redactedSensitiveFieldCount"] == 2
    assert stored["metadata"]["s3"]["redactedSensitiveFieldCount"] == 2
    assert stored["metadata"]["nested"]["redactedSensitiveFieldCount"] == 1
    assert "tok_live_secret_value" not in metadata_json
    assert "tok_query_secret" not in metadata_json
    assert "sk-test" not in metadata_json
    assert "sk-proj" not in metadata_json
    assert "akia1234567890abcdef" not in metadata_json
    assert "aws-secret-access-key" not in metadata_json
    assert "awssecretfromstring" not in metadata_json
    assert "qwxszzrpbgjpbgvcgvuihnlc2ftzq" not in metadata_json
    assert "plainpass" not in metadata_json
    assert "plain-password" not in metadata_json
    assert "access_token" not in metadata_json
    assert "apikey" not in metadata_json
    assert "password" not in metadata_json
    assert "<redacted token>" in metadata_json


def test_module_registry_declares_modular_cognix_capabilities():
    registry = cognix_module_registry.build_module_registry()

    assert registry["moduleRegistryVersion"] == "cognix_module_registry_v1"
    assert registry["mode"] == "declarative_dry_run"
    assert registry["summary"]["uiMutationAllowed"] is False
    assert registry["summary"]["routeMutationAllowed"] is False
    assert registry["summary"]["serviceCount"] == 10
    assert registry["summary"]["coveredServiceCount"] == 10
    assert registry["globalPolicies"]["serviceTopologyVersion"] == "cognix_module_service_topology_v1"
    assert registry["globalPolicies"]["serviceTopologyAvailable"] is True
    assert registry["sideEffects"]["moduleActivation"] is False
    assert registry["sideEffects"]["uiMutation"] is False
    assert registry["sideEffects"]["toolExecution"] is False
    assert registry["sideEffects"]["secretRead"] is False

    modules = {item["id"]: item for item in registry["modules"]}
    assert {
        "cognix-local-core",
        "cognix-pulse",
        "cognix-library",
        "cognix-scheduled",
        "cognix-images",
        "cognix-apps",
        "cognix-command-palette",
        "cognix-model-lifecycle",
        "cognix-live-model-comparison",
        "cognix-model-translator",
        "cognix-optimization-engine",
        "cognix-performance-monitor",
        "cognix-explain-decisions",
        "cognix-prompt-compression",
        "cognix-context-heatmap",
        "cognix-intent-prediction",
        "cognix-dynamic-ui",
        "cognix-background-agents",
        "cognix-ai-timeline",
        "cognix-thinking-status",
        "cognix-response-reflection",
        "cognix-multi-draft-generation",
        "cognix-ai-debate",
        "cognix-tool-discovery",
        "cognix-context-graph",
        "cognix-memory-manager",
        "cognix-long-term-skill-memory",
        "cognix-personal-ai-twin",
        "cognix-ai-workflow-recorder",
        "cognix-onboarding",
        "cognix-rag",
        "cognix-dataset-builder",
        "cognix-persona-builder",
        "cognix-fine-tuning",
        "cognix-worker-queue",
        "cognix-research-watch",
        "cognix-ai-evolution-engine",
        "cognix-integrations",
        "cognix-plugin-marketplace",
        "cognix-codex-secure-agent",
        "cognix-enterprise-foundation",
        "cognix-admin-operations",
        "cognix-admin-chat-access",
        "cognix-admin-security-center",
        "cognix-deployment-manager",
    }.issubset(modules)
    assert modules["cognix-pulse"]["status"] == "enabled"
    assert "daily_digest" in modules["cognix-pulse"]["capabilities"]
    assert "local_privacy_preserving_summary" in modules["cognix-pulse"]["capabilities"]
    assert "/api/cognix/pulse/preview" in modules["cognix-pulse"]["routes"]
    assert "/api/cognix/pulse/generate" in modules["cognix-pulse"]["routes"]
    assert modules["cognix-library"]["status"] == "enabled"
    assert "library_search" in modules["cognix-library"]["capabilities"]
    assert "asset_permission_scope" in modules["cognix-library"]["capabilities"]
    assert "model_registration_gate" in modules["cognix-library"]["capabilities"]
    assert "lora_adapter_registration_gate" in modules["cognix-library"]["capabilities"]
    assert "/api/cognix/library/search" in modules["cognix-library"]["routes"]
    assert modules["cognix-scheduled"]["status"] == "enabled"
    assert "queue_first_execution" in modules["cognix-scheduled"]["capabilities"]
    assert "creator_permission_ceiling" in modules["cognix-scheduled"]["capabilities"]
    assert "/api/cognix/scheduled-tasks/plan" in modules["cognix-scheduled"]["routes"]
    assert "/api/cognix/scheduled-tasks/{task_id}/run-plan" in modules["cognix-scheduled"]["routes"]
    assert modules["cognix-images"]["status"] == "enabled"
    assert "image_safety_check" in modules["cognix-images"]["capabilities"]
    assert "image_asset_library_link" in modules["cognix-images"]["capabilities"]
    assert "/api/cognix/images/plan" in modules["cognix-images"]["routes"]
    assert modules["cognix-apps"]["status"] == "enabled"
    assert "app_permission_scanning" in modules["cognix-apps"]["capabilities"]
    assert "token_safe_registry" in modules["cognix-apps"]["capabilities"]
    assert "/api/cognix/apps/plan" in modules["cognix-apps"]["routes"]
    assert modules["cognix-command-palette"]["status"] == "enabled"
    assert modules["cognix-command-palette"]["dependencyState"]["ready"] is True
    assert "permission_aware_command_filter" in modules["cognix-command-palette"]["capabilities"]
    assert "command_usage_logging" in modules["cognix-command-palette"]["capabilities"]
    assert "/api/cognix/command-palette/search" in modules["cognix-command-palette"]["routes"]
    assert "/api/cognix/command-palette/plan" in modules["cognix-command-palette"]["routes"]
    assert modules["cognix-local-core"]["activationState"] == "ready"
    assert "module_manifest_registry" in modules["cognix-local-core"]["capabilities"]
    assert "module_service_topology" in modules["cognix-local-core"]["capabilities"]
    assert "external_moe_model_router" in modules["cognix-local-core"]["capabilities"]
    assert "multi_expert_routing_contract" in modules["cognix-local-core"]["capabilities"]
    assert "secondary_expert_planning" in modules["cognix-local-core"]["capabilities"]
    assert "router_fallback_chain" in modules["cognix-local-core"]["capabilities"]
    assert "architecture_decision_contract" in modules["cognix-local-core"]["capabilities"]
    assert "orchestrator_runtime_plan" in modules["cognix-local-core"]["capabilities"]
    assert "runtime_optimization_contract" in modules["cognix-local-core"]["capabilities"]
    assert "runtime_fallback_chain" in modules["cognix-local-core"]["capabilities"]
    assert "runtime_failover_contract" in modules["cognix-local-core"]["capabilities"]
    assert "tensorrt_llm_adapter" in modules["cognix-local-core"]["capabilities"]
    assert "frontend_inference_boundary_contract" in modules["cognix-local-core"]["capabilities"]
    assert "orchestrator_required_generation_boundary" in modules["cognix-local-core"]["capabilities"]
    assert "/api/cognix/orchestrator/plan" in modules["cognix-local-core"]["routes"]
    assert "/api/cognix/runtime/plan" in modules["cognix-local-core"]["routes"]
    assert "/api/cognix/runtime/fallback-plan" in modules["cognix-local-core"]["routes"]
    assert "/api/cognix/runtime/frontend-boundary-contract" in modules["cognix-local-core"]["routes"]
    assert "/api/cognix/modules/manifests" in modules["cognix-local-core"]["routes"]
    assert "/api/cognix/modules/service-topology" in modules["cognix-local-core"]["routes"]
    assert "project_dna" in modules["cognix-projects"]["capabilities"]
    assert "project_dna_context_injection" in modules["cognix-projects"]["capabilities"]
    assert "project_constraints" in modules["cognix-projects"]["capabilities"]
    assert "project_decisions" in modules["cognix-projects"]["capabilities"]
    assert "project_session_contract" in modules["cognix-projects"]["capabilities"]
    assert "direct_project_expert_session" in modules["cognix-projects"]["capabilities"]
    assert "/api/cognix/projects/{project_id}/dna" in modules["cognix-projects"]["routes"]
    assert "/api/cognix/projects/{project_id}/dna/injection-plan" in modules["cognix-projects"]["routes"]
    assert modules["cognix-model-lifecycle"]["activationState"] == "ready"
    assert "load_unload_planning" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "cache_load_planning" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "cache_pressure_planning" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "model_residency_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "resident_model_inventory" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "load_unload_execution_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "preload_execution_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "load_prediction" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "model_warmup_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "external_moe_preload_queue" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "intelligent_preload_queue_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "model_install_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "hugging_face_install_contract" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "download_worker_handoff" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "/api/cognix/models/lifecycle-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert "/api/cognix/models/install-contract" in modules["cognix-model-lifecycle"]["routes"]
    assert "/api/cognix/models/residency-contract" in modules["cognix-model-lifecycle"]["routes"]
    assert "/api/cognix/models/cache/load-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert "/api/cognix/models/cache/pressure-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert "/api/cognix/models/preload-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert modules["cognix-live-model-comparison"]["dependencyState"]["ready"] is True
    assert "side_by_side_model_comparison" in modules["cognix-live-model-comparison"]["capabilities"]
    assert "parallel_inference_planning" in modules["cognix-live-model-comparison"]["capabilities"]
    assert "response_collection" in modules["cognix-live-model-comparison"]["capabilities"]
    assert "user_best_response_selection" in modules["cognix-live-model-comparison"]["capabilities"]
    assert "/api/cognix/models/comparison/plan" in modules["cognix-live-model-comparison"]["routes"]
    assert "/api/cognix/models/comparisons/{comparison_id}/preference" in modules["cognix-live-model-comparison"]["routes"]
    assert modules["cognix-model-translator"]["dependencyState"]["ready"] is True
    assert "model_conversion_planning" in modules["cognix-model-translator"]["capabilities"]
    assert "compatibility_checking" in modules["cognix-model-translator"]["capabilities"]
    assert "model_export_planning" in modules["cognix-model-translator"]["capabilities"]
    assert "/api/cognix/models/translator/plan" in modules["cognix-model-translator"]["routes"]
    assert "/api/cognix/models/conversions" in modules["cognix-model-translator"]["routes"]
    assert modules["cognix-optimization-engine"]["status"] == "enabled"
    assert modules["cognix-optimization-engine"]["activationState"] == "ready"
    assert modules["cognix-optimization-engine"]["dependencyState"]["ready"] is True
    assert "optimization_capability_registry" in modules["cognix-optimization-engine"]["capabilities"]
    assert "benchmark_gated_experiments" in modules["cognix-optimization-engine"]["capabilities"]
    assert "benchmark_evidence_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "optimization_application_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "runtime_optimization_executor_gate" in modules["cognix-optimization-engine"]["capabilities"]
    assert "prompt_cache_planning" in modules["cognix-optimization-engine"]["capabilities"]
    assert "prompt_cache_runtime_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "stable_prefix_cache_policy" in modules["cognix-optimization-engine"]["capabilities"]
    assert "semantic_cache_planning" in modules["cognix-optimization-engine"]["capabilities"]
    assert "semantic_reuse_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "privacy_safe_cache_keys" in modules["cognix-optimization-engine"]["capabilities"]
    assert "kv_cache_eviction_planning" in modules["cognix-optimization-engine"]["capabilities"]
    assert "kv_cache_policy_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "context_retention_policy" in modules["cognix-optimization-engine"]["capabilities"]
    assert "speculative_decoding_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "multi_user_batching_planning" in modules["cognix-optimization-engine"]["capabilities"]
    assert "micro_batch_policy_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "throughput_experiment_contract" in modules["cognix-optimization-engine"]["capabilities"]
    assert "/api/cognix/semantic-cache/plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/capabilities" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/experiment-plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/application-contract" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/speculative-decoding-plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/kv-cache-plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/prompt-cache-plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/batching-plan" in modules["cognix-optimization-engine"]["routes"]
    assert modules["cognix-performance-monitor"]["status"] == "enabled"
    assert modules["cognix-performance-monitor"]["activationState"] == "ready"
    assert modules["cognix-performance-monitor"]["dependencyState"]["ready"] is True
    assert "runtime_metrics" in modules["cognix-performance-monitor"]["capabilities"]
    assert "metrics_streaming" in modules["cognix-performance-monitor"]["capabilities"]
    assert "model_performance_logs" in modules["cognix-performance-monitor"]["capabilities"]
    assert "/api/cognix/performance/snapshot" in modules["cognix-performance-monitor"]["routes"]
    assert "/api/cognix/performance/logs" in modules["cognix-performance-monitor"]["routes"]
    assert modules["cognix-explain-decisions"]["status"] == "enabled"
    assert modules["cognix-explain-decisions"]["activationState"] == "ready"
    assert modules["cognix-explain-decisions"]["dependencyState"]["ready"] is True
    assert "decision_logs" in modules["cognix-explain-decisions"]["capabilities"]
    assert "reason_codes" in modules["cognix-explain-decisions"]["capabilities"]
    assert "router_decision_explanations" in modules["cognix-explain-decisions"]["capabilities"]
    assert "knowledge_strategy_contract" in modules["cognix-explain-decisions"]["capabilities"]
    assert "/api/cognix/decisions/explain" in modules["cognix-explain-decisions"]["routes"]
    assert "/api/cognix/decisions/{decision_id}" in modules["cognix-explain-decisions"]["routes"]
    assert modules["cognix-prompt-compression"]["status"] == "enabled"
    assert modules["cognix-prompt-compression"]["activationState"] == "ready"
    assert modules["cognix-prompt-compression"]["dependencyState"]["ready"] is True
    assert "prompt_compression" in modules["cognix-prompt-compression"]["capabilities"]
    assert "importance_ranking" in modules["cognix-prompt-compression"]["capabilities"]
    assert "compression_evaluation" in modules["cognix-prompt-compression"]["capabilities"]
    assert "compressed_context_injection" in modules["cognix-prompt-compression"]["capabilities"]
    assert "conversation_summary_contract" in modules["cognix-prompt-compression"]["capabilities"]
    assert "secret_redacted_summary" in modules["cognix-prompt-compression"]["capabilities"]
    assert "/api/cognix/prompt-compression/plan" in modules["cognix-prompt-compression"]["routes"]
    assert "/api/cognix/prompt-compression/conversation-summary-plan" in modules["cognix-prompt-compression"]["routes"]
    assert "/api/cognix/prompt-compression/contexts" in modules["cognix-prompt-compression"]["routes"]
    assert modules["cognix-context-heatmap"]["status"] == "enabled"
    assert modules["cognix-context-heatmap"]["activationState"] == "ready"
    assert modules["cognix-context-heatmap"]["dependencyState"]["ready"] is True
    assert "context_usage_tracking" in modules["cognix-context-heatmap"]["capabilities"]
    assert "context_heatmap" in modules["cognix-context-heatmap"]["capabilities"]
    assert "memory_garbage_collection_planning" in modules["cognix-context-heatmap"]["capabilities"]
    assert "memory_cleanup_suggestions" in modules["cognix-context-heatmap"]["capabilities"]
    assert "memory_conflict_resolution" in modules["cognix-context-heatmap"]["capabilities"]
    assert "/api/cognix/context/heatmap/plan" in modules["cognix-context-heatmap"]["routes"]
    assert "/api/cognix/context/heatmap/entries" in modules["cognix-context-heatmap"]["routes"]
    assert "/api/cognix/memory/cleanup/plan" in modules["cognix-context-heatmap"]["routes"]
    assert "/api/cognix/memory/cleanup/conflicts" in modules["cognix-context-heatmap"]["routes"]
    assert modules["cognix-intent-prediction"]["dependencyState"]["ready"] is True
    assert "intent_prediction" in modules["cognix-intent-prediction"]["capabilities"]
    assert "preload_planning" in modules["cognix-intent-prediction"]["capabilities"]
    assert "single_useful_suggestion" in modules["cognix-intent-prediction"]["capabilities"]
    assert "/api/cognix/intent/predict" in modules["cognix-intent-prediction"]["routes"]
    assert "/api/cognix/intent/preload-events" in modules["cognix-intent-prediction"]["routes"]
    assert modules["cognix-dynamic-ui"]["dependencyState"]["ready"] is True
    assert "ui_layout_profiles" in modules["cognix-dynamic-ui"]["capabilities"]
    assert "adaptive_panels" in modules["cognix-dynamic-ui"]["capabilities"]
    assert "theme_safe_layout_planning" in modules["cognix-dynamic-ui"]["capabilities"]
    assert "/api/cognix/dynamic-ui/profile" in modules["cognix-dynamic-ui"]["routes"]
    assert modules["cognix-background-agents"]["dependencyState"]["ready"] is True
    assert "background_job_planning" in modules["cognix-background-agents"]["capabilities"]
    assert "agent_queue_contract" in modules["cognix-background-agents"]["capabilities"]
    assert "progress_tracking" in modules["cognix-background-agents"]["capabilities"]
    assert "/api/cognix/background-agents/job-plan" in modules["cognix-background-agents"]["routes"]
    assert modules["cognix-ai-timeline"]["dependencyState"]["ready"] is True
    assert "project_timeline_events" in modules["cognix-ai-timeline"]["capabilities"]
    assert "timeline_event_classification" in modules["cognix-ai-timeline"]["capabilities"]
    assert "timeline_search" in modules["cognix-ai-timeline"]["capabilities"]
    assert "/api/cognix/timeline/events" in modules["cognix-ai-timeline"]["routes"]
    assert modules["cognix-thinking-status"]["activationState"] == "ready"
    assert "technical_redaction" in modules["cognix-thinking-status"]["capabilities"]
    assert "/api/cognix/thinking/plan" in modules["cognix-thinking-status"]["routes"]
    assert modules["cognix-response-reflection"]["status"] == "enabled"
    assert modules["cognix-response-reflection"]["activationState"] == "ready"
    assert modules["cognix-response-reflection"]["dependencyState"]["ready"] is True
    assert "response_quality_evaluation" in modules["cognix-response-reflection"]["capabilities"]
    assert "expert_generalist_quality_gate" in modules["cognix-response-reflection"]["capabilities"]
    assert "raw_reasoning_redaction" in modules["cognix-response-reflection"]["capabilities"]
    assert "/api/cognix/reflection/evaluate" in modules["cognix-response-reflection"]["routes"]
    assert "/api/cognix/reflection/evaluations" in modules["cognix-response-reflection"]["routes"]
    assert "/api/cognix/reflection/expert-generalist-gate" in modules["cognix-response-reflection"]["routes"]
    assert modules["cognix-multi-draft-generation"]["status"] == "enabled"
    assert modules["cognix-multi-draft-generation"]["activationState"] == "ready"
    assert modules["cognix-multi-draft-generation"]["dependencyState"]["ready"] is True
    assert "style_profile_registry" in modules["cognix-multi-draft-generation"]["capabilities"]
    assert "response_variant_store" in modules["cognix-multi-draft-generation"]["capabilities"]
    assert "/api/cognix/drafts/styles" in modules["cognix-multi-draft-generation"]["routes"]
    assert "/api/cognix/drafts/plan" in modules["cognix-multi-draft-generation"]["routes"]
    assert "/api/cognix/drafts/variants" in modules["cognix-multi-draft-generation"]["routes"]
    assert modules["cognix-ai-debate"]["status"] == "enabled"
    assert modules["cognix-ai-debate"]["activationState"] == "ready"
    assert modules["cognix-ai-debate"]["dependencyState"]["ready"] is True
    assert "debate_role_registry" in modules["cognix-ai-debate"]["capabilities"]
    assert "judge_synthesis_planning" in modules["cognix-ai-debate"]["capabilities"]
    assert "public_argument_summaries" in modules["cognix-ai-debate"]["capabilities"]
    assert "/api/cognix/debate/roles" in modules["cognix-ai-debate"]["routes"]
    assert "/api/cognix/debate/plan" in modules["cognix-ai-debate"]["routes"]
    assert "/api/cognix/debate/sessions" in modules["cognix-ai-debate"]["routes"]
    assert modules["cognix-tool-discovery"]["dependencyState"]["ready"] is True
    assert "project_tool_need_detection" in modules["cognix-tool-discovery"]["capabilities"]
    assert "tool_recommendation_store" in modules["cognix-tool-discovery"]["capabilities"]
    assert "no_auto_install_guardrail" in modules["cognix-tool-discovery"]["capabilities"]
    assert "/api/cognix/tools/discovery/capabilities" in modules["cognix-tool-discovery"]["routes"]
    assert "/api/cognix/tools/discovery/analyze" in modules["cognix-tool-discovery"]["routes"]
    assert "/api/cognix/tools/recommendations" in modules["cognix-tool-discovery"]["routes"]
    assert modules["cognix-context-graph"]["status"] == "enabled"
    assert modules["cognix-context-graph"]["activationState"] == "ready"
    assert modules["cognix-context-graph"]["dependencyState"]["ready"] is True
    assert "context_graph_snapshot" in modules["cognix-context-graph"]["capabilities"]
    assert "entity_extraction" in modules["cognix-context-graph"]["capabilities"]
    assert "relation_builder" in modules["cognix-context-graph"]["capabilities"]
    assert "graph_store" in modules["cognix-context-graph"]["capabilities"]
    assert "/api/cognix/context/graph/blueprint" in modules["cognix-context-graph"]["routes"]
    assert "/api/cognix/context/graph/build" in modules["cognix-context-graph"]["routes"]
    assert "/api/cognix/context/graph/snapshots" in modules["cognix-context-graph"]["routes"]
    assert modules["cognix-memory-manager"]["activationState"] == "ready"
    assert "central_memory_layers" in modules["cognix-memory-manager"]["capabilities"]
    assert "compressed_context_injection" in modules["cognix-memory-manager"]["capabilities"]
    assert "context_boundary_contract" in modules["cognix-memory-manager"]["capabilities"]
    assert "raw_history_boundary" in modules["cognix-memory-manager"]["capabilities"]
    assert "/api/cognix/memory/plan" in modules["cognix-memory-manager"]["routes"]
    assert modules["cognix-long-term-skill-memory"]["status"] == "enabled"
    assert modules["cognix-long-term-skill-memory"]["activationState"] == "ready"
    assert modules["cognix-long-term-skill-memory"]["dependencyState"]["ready"] is True
    assert "skill_memory_candidates" in modules["cognix-long-term-skill-memory"]["capabilities"]
    assert "memory_approval_flow" in modules["cognix-long-term-skill-memory"]["capabilities"]
    assert "context_injection_planning" in modules["cognix-long-term-skill-memory"]["capabilities"]
    assert "/api/cognix/memory/skills/candidates" in modules["cognix-long-term-skill-memory"]["routes"]
    assert "/api/cognix/memory/skills/export" in modules["cognix-long-term-skill-memory"]["routes"]
    assert "/api/cognix/memory/skills/injection-plan" in modules["cognix-long-term-skill-memory"]["routes"]
    assert modules["cognix-personal-ai-twin"]["status"] == "enabled"
    assert modules["cognix-personal-ai-twin"]["activationState"] == "ready"
    assert modules["cognix-personal-ai-twin"]["dependencyState"]["ready"] is True
    assert "personal_ai_profile" in modules["cognix-personal-ai-twin"]["capabilities"]
    assert "style_profiler" in modules["cognix-personal-ai-twin"]["capabilities"]
    assert "preference_model" in modules["cognix-personal-ai-twin"]["capabilities"]
    assert "personalization_rules" in modules["cognix-personal-ai-twin"]["capabilities"]
    assert "profile_export_reset" in modules["cognix-personal-ai-twin"]["capabilities"]
    assert "/api/cognix/personal-twin/profile/plan" in modules["cognix-personal-ai-twin"]["routes"]
    assert "/api/cognix/personal-twin/export" in modules["cognix-personal-ai-twin"]["routes"]
    assert "/api/cognix/personal-twin/injection-plan" in modules["cognix-personal-ai-twin"]["routes"]
    assert modules["cognix-live-memory-editing"]["status"] == "enabled"
    assert modules["cognix-live-memory-editing"]["activationState"] == "ready"
    assert modules["cognix-live-memory-editing"]["dependencyState"]["ready"] is True
    assert "live_memory_editor" in modules["cognix-live-memory-editing"]["capabilities"]
    assert "memory_versioning" in modules["cognix-live-memory-editing"]["capabilities"]
    assert "memory_search" in modules["cognix-live-memory-editing"]["capabilities"]
    assert "memory_merge" in modules["cognix-live-memory-editing"]["capabilities"]
    assert "sensitive_memory_controls" in modules["cognix-live-memory-editing"]["capabilities"]
    assert "/api/cognix/memory/editor/blueprint" in modules["cognix-live-memory-editing"]["routes"]
    assert "/api/cognix/memory/editor/items" in modules["cognix-live-memory-editing"]["routes"]
    assert "/api/cognix/memory/editor/merge" in modules["cognix-live-memory-editing"]["routes"]
    assert "/api/cognix/memory/editor/export" in modules["cognix-live-memory-editing"]["routes"]
    assert modules["cognix-ai-simulation"]["dependencyState"]["ready"] is True
    assert "simulation_engine" in modules["cognix-ai-simulation"]["capabilities"]
    assert "synthetic_user_generation" in modules["cognix-ai-simulation"]["capabilities"]
    assert "load_scenario_runner" in modules["cognix-ai-simulation"]["capabilities"]
    assert "simulation_metrics" in modules["cognix-ai-simulation"]["capabilities"]
    assert "risk_report" in modules["cognix-ai-simulation"]["capabilities"]
    assert "queue_safe_simulation" in modules["cognix-ai-simulation"]["capabilities"]
    assert "/api/cognix/simulations/blueprint" in modules["cognix-ai-simulation"]["routes"]
    assert "/api/cognix/simulations/runs" in modules["cognix-ai-simulation"]["routes"]
    assert "/api/cognix/simulations/runs/{run_id}" in modules["cognix-ai-simulation"]["routes"]
    assert modules["cognix-ai-sandbox"]["dependencyState"]["ready"] is True
    assert "sandbox_manager" in modules["cognix-ai-sandbox"]["capabilities"]
    assert "isolated_runtime" in modules["cognix-ai-sandbox"]["capabilities"]
    assert "experiment_runner" in modules["cognix-ai-sandbox"]["capabilities"]
    assert "rollback_service" in modules["cognix-ai-sandbox"]["capabilities"]
    assert "secret_isolation" in modules["cognix-ai-sandbox"]["capabilities"]
    assert "/api/cognix/sandbox/blueprint" in modules["cognix-ai-sandbox"]["routes"]
    assert "/api/cognix/sandbox/plans" in modules["cognix-ai-sandbox"]["routes"]
    assert "/api/cognix/sandbox/runs" in modules["cognix-ai-sandbox"]["routes"]
    assert "/api/cognix/sandbox/runs/{run_id}" in modules["cognix-ai-sandbox"]["routes"]
    assert modules["cognix-ai-workflow-recorder"]["dependencyState"]["ready"] is True
    assert "workflow_recording" in modules["cognix-ai-workflow-recorder"]["capabilities"]
    assert "workflow_replay_planning" in modules["cognix-ai-workflow-recorder"]["capabilities"]
    assert "workflow_template_registry" in modules["cognix-ai-workflow-recorder"]["capabilities"]
    assert "/api/cognix/workflows/record" in modules["cognix-ai-workflow-recorder"]["routes"]
    assert "/api/cognix/workflows/{workflow_id}/run-plan" in modules["cognix-ai-workflow-recorder"]["routes"]
    assert modules["cognix-onboarding"]["activationState"] == "ready"
    assert modules["cognix-rag"]["dependencyState"]["ready"] is True
    assert "rag_source_registry" in modules["cognix-rag"]["capabilities"]
    assert "rag_indexing_planning" in modules["cognix-rag"]["capabilities"]
    assert "rag_connector_sync_contract" in modules["cognix-rag"]["capabilities"]
    assert "connector_source_sync_planning" in modules["cognix-rag"]["capabilities"]
    assert "rag_retrieval_packet" in modules["cognix-rag"]["capabilities"]
    assert "rag_compression_contract" in modules["cognix-rag"]["capabilities"]
    assert "citation_retention_contract" in modules["cognix-rag"]["capabilities"]
    assert "/api/cognix/rag/sources" in modules["cognix-rag"]["routes"]
    assert "/api/cognix/rag/connector-sync-plan" in modules["cognix-rag"]["routes"]
    assert "/api/cognix/rag/indexing-plan" in modules["cognix-rag"]["routes"]
    assert "/api/cognix/rag/compression-plan" in modules["cognix-rag"]["routes"]
    assert "/api/cognix/rag/retrieval-packet" in modules["cognix-rag"]["routes"]
    assert "cognix-integrations" in modules["cognix-rag"]["dependencies"]
    assert "cloud_training_targets" in modules["cognix-fine-tuning"]["capabilities"]
    assert "cloud_training_handoff" in modules["cognix-fine-tuning"]["capabilities"]
    assert "dataset_validation_plan" in modules["cognix-fine-tuning"]["capabilities"]
    assert "distillation_planning" in modules["cognix-fine-tuning"]["capabilities"]
    assert "teacher_student_contract" in modules["cognix-fine-tuning"]["capabilities"]
    assert "fine_tuning_evaluation_plan" in modules["cognix-fine-tuning"]["capabilities"]
    assert "post_training_quality_review" in modules["cognix-fine-tuning"]["capabilities"]
    assert "model_library_registration_gate" in modules["cognix-fine-tuning"]["capabilities"]
    assert "/api/cognix/fine-tuning/dataset/validate" in modules["cognix-fine-tuning"]["routes"]
    assert "/api/cognix/fine-tuning/evaluation-plan" in modules["cognix-fine-tuning"]["routes"]
    assert "/api/cognix/fine-tuning/cloud-handoff-plan" in modules["cognix-fine-tuning"]["routes"]
    assert "/api/cognix/fine-tuning/distillation-plan" in modules["cognix-fine-tuning"]["routes"]
    assert modules["cognix-dataset-builder"]["dependencyState"]["ready"] is True
    assert "dataset_builder" in modules["cognix-dataset-builder"]["capabilities"]
    assert "synthetic_example_generation" in modules["cognix-dataset-builder"]["capabilities"]
    assert "dataset_quality_filter" in modules["cognix-dataset-builder"]["capabilities"]
    assert "/api/cognix/datasets/plan" in modules["cognix-dataset-builder"]["routes"]
    assert "/api/cognix/datasets" in modules["cognix-dataset-builder"]["routes"]
    assert modules["cognix-persona-builder"]["dependencyState"]["ready"] is True
    assert "persona_manager" in modules["cognix-persona-builder"]["capabilities"]
    assert "persona_template_engine" in modules["cognix-persona-builder"]["capabilities"]
    assert "persona_permission_binder" in modules["cognix-persona-builder"]["capabilities"]
    assert "/api/cognix/personas/plan" in modules["cognix-persona-builder"]["routes"]
    assert "/api/cognix/personas/{persona_id}" in modules["cognix-persona-builder"]["routes"]
    assert modules["cognix-gpts"]["dependencyState"]["ready"] is True
    assert "custom_gpt_manager" in modules["cognix-gpts"]["capabilities"]
    assert "custom_assistant_runtime" in modules["cognix-gpts"]["capabilities"]
    assert "creator_permission_ceiling" in modules["cognix-gpts"]["capabilities"]
    assert "/api/cognix/gpts/plan" in modules["cognix-gpts"]["routes"]
    assert "/api/cognix/gpts/{gpt_id}/runtime-plan" in modules["cognix-gpts"]["routes"]
    assert "worker_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "worker_enqueue_contract" in modules["cognix-worker-queue"]["capabilities"]
    assert "worker_retry_policy" in modules["cognix-worker-queue"]["capabilities"]
    assert "worker_dead_letter_policy" in modules["cognix-worker-queue"]["capabilities"]
    assert "cloud_training_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "rag_indexing_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "connector_sync_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "tool_execution_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "batching_experiment_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "enterprise_throughput_queue" in modules["cognix-worker-queue"]["capabilities"]
    assert "/api/cognix/workers/registry" in modules["cognix-worker-queue"]["routes"]
    assert "/api/cognix/workers/job-spec-plan" in modules["cognix-worker-queue"]["routes"]
    assert "/api/cognix/workers/enqueue-contract" in modules["cognix-worker-queue"]["routes"]
    assert "adaptive_quantization" in modules["cognix-optimization-engine"]["capabilities"]
    assert "quantization_advisor" in modules["cognix-optimization-engine"]["capabilities"]
    assert "model_variant_registry" in modules["cognix-optimization-engine"]["capabilities"]
    assert "cost_optimizer" in modules["cognix-optimization-engine"]["capabilities"]
    assert "provider_pricing_store" in modules["cognix-optimization-engine"]["capabilities"]
    assert "execution_budget_guard" in modules["cognix-optimization-engine"]["capabilities"]
    assert "cloud_quota_guard" in modules["cognix-optimization-engine"]["capabilities"]
    assert "token_quota_guard" in modules["cognix-optimization-engine"]["capabilities"]
    assert "privacy_aware_provider_selection" in modules["cognix-optimization-engine"]["capabilities"]
    assert "/api/cognix/quantization/plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/quantization/variants" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/costs/plan" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/costs/providers" in modules["cognix-optimization-engine"]["routes"]
    assert "technology_watch" in modules["cognix-research-watch"]["capabilities"]
    assert "benchmark_gate" in modules["cognix-research-watch"]["capabilities"]
    assert "research_topics" in modules["cognix-research-watch"]["capabilities"]
    assert "research_report_generation" in modules["cognix-research-watch"]["capabilities"]
    assert "/api/cognix/research/integration-plan" in modules["cognix-research-watch"]["routes"]
    assert "/api/cognix/research/assistant/topics" in modules["cognix-research-watch"]["routes"]
    assert "/api/cognix/research/assistant/reports/plan" in modules["cognix-research-watch"]["routes"]
    assert modules["cognix-ai-evolution-engine"]["dependencyState"]["ready"] is True
    assert "evolution_lab" in modules["cognix-ai-evolution-engine"]["capabilities"]
    assert "technique_classifier" in modules["cognix-ai-evolution-engine"]["capabilities"]
    assert "sandbox_experiment_planning" in modules["cognix-ai-evolution-engine"]["capabilities"]
    assert "benchmark_review" in modules["cognix-ai-evolution-engine"]["capabilities"]
    assert "human_approval_gate" in modules["cognix-ai-evolution-engine"]["capabilities"]
    assert "/api/cognix/evolution/items/plan" in modules["cognix-ai-evolution-engine"]["routes"]
    assert "/api/cognix/evolution/experiments/plan" in modules["cognix-ai-evolution-engine"]["routes"]
    assert "/api/cognix/evolution/proposals" in modules["cognix-ai-evolution-engine"]["routes"]
    assert "tool_permission_matrix" in modules["cognix-integrations"]["capabilities"]
    assert "tool_execution_contract" in modules["cognix-integrations"]["capabilities"]
    assert "tool_execution_boundary_contract" in modules["cognix-integrations"]["capabilities"]
    assert "tool_execution_handoff" in modules["cognix-integrations"]["capabilities"]
    assert "tool_executor_queue_gate" in modules["cognix-integrations"]["capabilities"]
    assert "tool_secret_policy" in modules["cognix-integrations"]["capabilities"]
    assert "native_calculator_tool" in modules["cognix-integrations"]["capabilities"]
    assert "safe_math_evaluation" in modules["cognix-integrations"]["capabilities"]
    assert "native_physics_solver_tool" in modules["cognix-integrations"]["capabilities"]
    assert "safe_physics_formula_solving" in modules["cognix-integrations"]["capabilities"]
    assert "native_latex_renderer_tool" in modules["cognix-integrations"]["capabilities"]
    assert "safe_latex_render_packets" in modules["cognix-integrations"]["capabilities"]
    assert "connector_preflight_contract" in modules["cognix-integrations"]["capabilities"]
    assert "integration_activation_contract" in modules["cognix-integrations"]["capabilities"]
    assert "connector_secret_rotation_contract" in modules["cognix-integrations"]["capabilities"]
    assert "server_side_secret_rotation" in modules["cognix-integrations"]["capabilities"]
    assert "enterprise_connector_manifests" in modules["cognix-integrations"]["capabilities"]
    assert "education_connector_manifests" in modules["cognix-integrations"]["capabilities"]
    assert "business_system_connector_manifests" in modules["cognix-integrations"]["capabilities"]
    assert "connector_roadmap_readiness" in modules["cognix-integrations"]["capabilities"]
    assert "mvp_connector_phase_mapping" in modules["cognix-integrations"]["capabilities"]
    assert {"calculator", "physics-solver", "latex-renderer", "sharepoint", "microsoft-teams", "slack", "moodle", "crm", "erp"}.issubset(
        set(modules["cognix-integrations"]["tools"])
    )
    assert "/api/cognix/integrations/plan" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/integrations/preflight-contract" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/integrations/activation-contract" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/integrations/secret-rotation-contract" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/integrations/roadmap-readiness" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/tools/permission-matrix" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/tools/latex/render" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/tools/plan" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/tools/calculator/evaluate" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/tools/physics/solve" in modules["cognix-integrations"]["routes"]
    assert "/api/cognix/tools/execution-handoff" in modules["cognix-integrations"]["routes"]
    assert modules["cognix-plugin-marketplace"]["dependencyState"]["ready"] is True
    assert "plugin_manifest_validation" in modules["cognix-plugin-marketplace"]["capabilities"]
    assert "plugin_permission_scanning" in modules["cognix-plugin-marketplace"]["capabilities"]
    assert "plugin_install_planning" in modules["cognix-plugin-marketplace"]["capabilities"]
    assert "/api/cognix/plugins/marketplace" in modules["cognix-plugin-marketplace"]["routes"]
    assert "/api/cognix/plugins/install-plan" in modules["cognix-plugin-marketplace"]["routes"]
    assert "sso_planning" in modules["cognix-enterprise-foundation"]["capabilities"]
    assert "/api/cognix/governance/plan" in modules["cognix-enterprise-foundation"]["routes"]
    assert modules["cognix-admin-operations"]["status"] == "enabled"
    assert modules["cognix-admin-operations"]["dependencyState"]["ready"] is True
    assert "admin_user_service" in modules["cognix-admin-operations"]["capabilities"]
    assert "activity_daily_rollups" in modules["cognix-admin-operations"]["capabilities"]
    assert "organization_activity_daily" in modules["cognix-admin-operations"]["capabilities"]
    assert "quota_manager" in modules["cognix-admin-operations"]["capabilities"]
    assert "usage_enforcer" in modules["cognix-admin-operations"]["capabilities"]
    assert "role_quota_management" in modules["cognix-admin-operations"]["capabilities"]
    assert "token_usage_dashboard" in modules["cognix-admin-operations"]["capabilities"]
    assert "token_usage_service" in modules["cognix-admin-operations"]["capabilities"]
    assert "model_usage_aggregator" in modules["cognix-admin-operations"]["capabilities"]
    assert "cost_estimator" in modules["cognix-admin-operations"]["capabilities"]
    assert "daily_user_token_rollups" in modules["cognix-admin-operations"]["capabilities"]
    assert "organization_usage_summary" in modules["cognix-admin-operations"]["capabilities"]
    assert "permission_engine" in modules["cognix-admin-operations"]["capabilities"]
    assert "role_permission_management" in modules["cognix-admin-operations"]["capabilities"]
    assert "user_permission_overrides" in modules["cognix-admin-operations"]["capabilities"]
    assert "project_permission_scopes" in modules["cognix-admin-operations"]["capabilities"]
    assert "ceo_cloud_training_permissions" in modules["cognix-admin-operations"]["capabilities"]
    assert "approval_service" in modules["cognix-admin-operations"]["capabilities"]
    assert "approval_queue" in modules["cognix-admin-operations"]["capabilities"]
    assert "approval_policy_engine" in modules["cognix-admin-operations"]["capabilities"]
    assert "audit_governance_contract" in modules["cognix-admin-operations"]["capabilities"]
    assert "database_blueprint_contract" in modules["cognix-admin-operations"]["capabilities"]
    assert "roadmap_schema_mapping" in modules["cognix-admin-operations"]["capabilities"]
    assert "read_only_schema_inspection" in modules["cognix-admin-operations"]["capabilities"]
    assert "api_surface_contract" in modules["cognix-admin-operations"]["capabilities"]
    assert "roadmap_endpoint_mapping" in modules["cognix-admin-operations"]["capabilities"]
    assert "ban_service" in modules["cognix-admin-operations"]["capabilities"]
    assert "ban_report_generator" in modules["cognix-admin-operations"]["capabilities"]
    assert "user_reactivation" in modules["cognix-admin-operations"]["capabilities"]
    assert "/api/cognix/admin/users" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/limits" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/limits/enforcement-plan" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/permissions/matrix" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/permissions/decision" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/approvals" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/approvals/blueprint" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/audit-governance-contract" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/database-blueprint" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/api-surface-contract" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/banned" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/usage/blueprint" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/usage/aggregate" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/banned/blueprint" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/activity/aggregate" in modules["cognix-admin-operations"]["routes"]
    assert "/api/cognix/admin/usage" in modules["cognix-admin-operations"]["routes"]
    assert modules["cognix-admin-chat-access"]["status"] == "enabled"
    assert modules["cognix-admin-chat-access"]["dependencyState"]["ready"] is True
    assert "e2ee_metadata_only_mode" in modules["cognix-admin-chat-access"]["capabilities"]
    assert "admin_chat_access_audit" in modules["cognix-admin-chat-access"]["capabilities"]
    assert "/api/cognix/admin/chats" in modules["cognix-admin-chat-access"]["routes"]
    assert "/api/cognix/admin/chats/{thread_id}/export-plan" in modules["cognix-admin-chat-access"]["routes"]
    assert modules["cognix-admin-security-center"]["status"] == "enabled"
    assert modules["cognix-admin-security-center"]["activationState"] == "ready"
    assert modules["cognix-admin-security-center"]["dependencyState"]["ready"] is True
    assert "security_threat_service" in modules["cognix-admin-security-center"]["capabilities"]
    assert "vulnerability_scanner_adapter" in modules["cognix-admin-security-center"]["capabilities"]
    assert "vulnerability_scanner_contract" in modules["cognix-admin-security-center"]["capabilities"]
    assert "codex_security_summarizer" in modules["cognix-admin-security-center"]["capabilities"]
    assert "permission_error_detection" in modules["cognix-admin-security-center"]["capabilities"]
    assert "secret_exposure_detection" in modules["cognix-admin-security-center"]["capabilities"]
    assert "cloud_risk_detection" in modules["cognix-admin-security-center"]["capabilities"]
    assert "ai_risk_scoring" in modules["cognix-admin-security-center"]["capabilities"]
    assert "live_system_health" in modules["cognix-admin-security-center"]["capabilities"]
    assert "/api/cognix/admin/security-threats/blueprint" in modules["cognix-admin-security-center"]["routes"]
    assert "/api/cognix/admin/vulnerability-scanner-contract" in modules["cognix-admin-security-center"]["routes"]
    assert "/api/cognix/admin/risk-scores" in modules["cognix-admin-security-center"]["routes"]
    assert "/api/cognix/admin/system-health" in modules["cognix-admin-security-center"]["routes"]
    assert "codex_run_contract" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "codex_night_mode_contract" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "codex_night_report_contract" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "codex_preview_contract" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "branch_test_build_preview_gate" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "codex_human_approval_gate" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "codex_merge_gate_contract" in modules["cognix-codex-secure-agent"]["capabilities"]
    assert "/api/cognix/codex/pipeline-plan" in modules["cognix-codex-secure-agent"]["routes"]
    assert "/api/cognix/codex/night-report-contract" in modules["cognix-codex-secure-agent"]["routes"]
    assert "/api/cognix/codex/preview-contract" in modules["cognix-codex-secure-agent"]["routes"]
    assert "/api/cognix/codex/approval-gate" in modules["cognix-codex-secure-agent"]["routes"]
    assert modules["cognix-deployment-manager"]["dependencyState"]["ready"] is True
    assert "gpu_scheduler_contract" in modules["cognix-deployment-manager"]["capabilities"]
    assert "gpu_pool_admission_control" in modules["cognix-deployment-manager"]["capabilities"]
    assert "/api/cognix/deployments/gpu-scheduler-contract" in modules["cognix-deployment-manager"]["routes"]
    assert "cognix-integrations" in modules["cognix-codex-secure-agent"]["dependencyState"]["dependencies"]


def test_module_manifest_bundle_exports_declarative_contract_without_mutation():
    bundle = cognix_module_registry.build_module_manifest_bundle()

    assert bundle["bundleVersion"] == "cognix_module_manifest_bundle_v1"
    assert bundle["moduleRegistryVersion"] == "cognix_module_registry_v1"
    assert bundle["schemaVersion"] == "cognix_module_manifest_schema_v1"
    assert bundle["mode"] == "declarative_dry_run"
    assert bundle["contract"]["sourceOfTruth"] == "backend_source_manifest"
    assert bundle["contract"]["serviceTopologyVersion"] == "cognix_module_service_topology_v1"
    assert bundle["contract"]["runtimeRouteMutationAllowed"] is False
    assert bundle["contract"]["frontendSelfRegistrationAllowed"] is False
    assert bundle["validation"]["ready"] is True
    assert bundle["summary"]["invalidManifestCount"] == 0
    assert bundle["sideEffects"]["moduleActivation"] is False
    assert bundle["sideEffects"]["routeRegistration"] is False
    assert bundle["sideEffects"]["uiMutation"] is False
    assert bundle["sideEffects"]["permissionWrite"] is False
    assert bundle["sideEffects"]["toolExecution"] is False
    assert bundle["sideEffects"]["secretRead"] is False
    assert bundle["sideEffects"]["modelLoad"] is False
    assert bundle["sideEffects"]["trainingRun"] is False

    manifests = {item["id"]: item for item in bundle["manifests"]}
    assert "cognix-local-core" in manifests
    assert "cognix-codex-secure-agent" in manifests
    assert manifests["cognix-local-core"]["kind"] == "cognix.module.manifest"
    assert manifests["cognix-local-core"]["runtimeMutationAllowed"] is False
    assert "module_manifest_registry" in manifests["cognix-local-core"]["capabilities"]
    assert "module_service_topology" in manifests["cognix-local-core"]["capabilities"]
    assert "/api/cognix/modules/manifests" in manifests["cognix-local-core"]["routes"]
    assert "/api/cognix/modules/service-topology" in manifests["cognix-local-core"]["routes"]
    assert {"backend-api", "frontend", "orchestrator-service"}.issubset(
        set(manifests["cognix-local-core"]["serviceIds"])
    )
    assert manifests["cognix-local-core"]["manifestValidation"]["ready"] is True
    assert "developer_mode" in manifests["cognix-codex-secure-agent"]["permissions"]
    assert "github" in manifests["cognix-codex-secure-agent"]["tools"]

    developer_bundle = cognix_module_registry.build_module_manifest_bundle(edition = "developer")
    assert developer_bundle["editionFilter"] == "developer"
    assert developer_bundle["validation"]["ready"] is True
    assert all("developer" in item["editionTargets"] for item in developer_bundle["manifests"])


def test_module_service_topology_maps_roadmap_services_without_mutation():
    topology = cognix_module_registry.build_module_service_topology()

    assert topology["serviceTopologyVersion"] == "cognix_module_service_topology_v1"
    assert topology["mode"] == "declarative_service_topology_dry_run"
    assert topology["coverage"]["ready"] is True
    assert topology["coverage"]["missingServiceIds"] == []
    assert {
        "frontend",
        "backend-api",
        "orchestrator-service",
        "model-runtime-adapter",
        "memory-service",
        "rag-service",
        "fine-tuning-service",
        "tool-service",
        "codex-agent-service",
        "worker-queue",
    } == set(topology["coverage"]["requiredServiceIds"])

    services = {item["id"]: item for item in topology["services"]}
    assert "cognix-rag" in services["rag-service"]["moduleIds"]
    assert "cognix-fine-tuning" in services["fine-tuning-service"]["moduleIds"]
    assert "cognix-tool-discovery" in services["tool-service"]["moduleIds"]
    assert "cognix-codex-secure-agent" in services["codex-agent-service"]["moduleIds"]
    assert "cognix-worker-queue" in services["worker-queue"]["moduleIds"]
    assert topology["contract"]["matchesRoadmapInternalServices"] is True
    assert topology["sideEffects"]["moduleActivation"] is False
    assert topology["sideEffects"]["routeRegistration"] is False
    assert topology["sideEffects"]["serviceStart"] is False
    assert topology["sideEffects"]["toolExecution"] is False


def test_module_manifest_endpoint_writes_sanitized_audit_log():
    seed_accounts()

    body = run_async(cognix_routes.module_manifests(edition = "developer", current_subject = "alice"))

    assert body["auditLogId"].startswith("aud_")
    assert body["manifestBundle"]["bundleVersion"] == "cognix_module_manifest_bundle_v1"
    assert body["manifestBundle"]["schemaVersion"] == "cognix_module_manifest_schema_v1"
    assert body["manifestBundle"]["editionFilter"] == "developer"
    assert body["manifestBundle"]["validation"]["ready"] is True
    assert body["sideEffects"]["moduleActivation"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["secretRead"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "module_manifest_bundle_built"
    assert log["resourceType"] == "cognix_module_manifest_bundle"
    assert log["metadata"]["bundleVersion"] == "cognix_module_manifest_bundle_v1"
    assert log["metadata"]["schemaVersion"] == "cognix_module_manifest_schema_v1"
    assert log["metadata"]["editionFilter"] == "developer"
    assert log["metadata"]["validationReady"] is True
    assert log["metadata"]["sideEffects"]["moduleActivation"] is False
    assert log["metadata"]["sideEffects"]["secretRead"] is False


def test_module_service_topology_endpoint_writes_sanitized_audit_log():
    seed_accounts()

    body = run_async(cognix_routes.module_service_topology(edition = "developer", current_subject = "alice"))

    topology = body["serviceTopology"]
    assert body["auditLogId"].startswith("aud_")
    assert topology["serviceTopologyVersion"] == "cognix_module_service_topology_v1"
    assert topology["editionFilter"] == "developer"
    assert topology["coverage"]["ready"] is True
    assert topology["coverage"]["missingServiceIds"] == []
    assert body["sideEffects"]["serviceStart"] is False
    assert body["sideEffects"]["moduleActivation"] is False
    assert body["sideEffects"]["toolExecution"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "module_service_topology_built"
    assert log["resourceType"] == "cognix_module_service_topology"
    assert log["metadata"]["serviceTopologyVersion"] == "cognix_module_service_topology_v1"
    assert log["metadata"]["editionFilter"] == "developer"
    assert log["metadata"]["coverageReady"] is True
    assert log["metadata"]["missingServiceIds"] == []
    assert log["metadata"]["sideEffects"]["serviceStart"] is False
    assert log["metadata"]["sideEffects"]["routeRegistration"] is False


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


def test_pulse_preview_and_generate_use_native_isolated_activity_feed():
    seed_accounts()
    now_ms = int(time.time() * 1000)
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-alice",
            "title": "Projet physique CogniX",
            "modelType": "local",
            "modelId": "qwen-test",
            "createdAt": now_ms,
            "archived": False,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-bob",
            "title": "Conversation Bob secrete",
            "modelType": "local",
            "modelId": "private",
            "createdAt": now_ms,
            "archived": False,
        },
        owner_username = "bob",
    )
    cognix_db.create_library_item(
        "alice",
        kind = "document",
        name = "Cours mecanique.pdf",
        source = "manual",
    )
    task = cognix_db.create_scheduled_task(
        "alice",
        "Resume quotidien",
        "resumer les nouveaux documents",
        "tous les jours a 08:00",
    )
    cognix_db.create_scheduled_task_run(
        "alice",
        task["id"],
        "report",
        "Erreur de test recuperee",
        status = "failed",
    )
    cognix_db.create_research_report(
        "alice",
        "Qwen local",
        "Recherche Qwen",
        "Notes sur le modele local.",
        [{"title": "Qwen", "url": "https://example.test/qwen", "source": "test"}],
    )
    cognix_db.create_agent_run(
        "alice",
        "Analyser les options cloud training",
        "research",
        ["collecter", "verifier"],
        "Plan prepare.",
        status = "complete",
    )
    cognix_db.create_image_request("alice", "schema architecture CogniX", "local-placeholder")
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = "alice",
        action = "scheduled_task_failed",
        resource_type = "cognix_scheduled_task",
        resource_id = task["id"],
        severity = "warning",
        metadata = {"safe": True},
    )

    blueprint = run_async(cognix_routes.pulse_blueprint(current_subject = "alice"))
    assert blueprint["blueprint"]["pulseVersion"] == "cognix_pulse_v1"
    assert blueprint["sideEffects"]["pulseReportWrite"] is False
    assert blueprint["blueprint"]["privacyPolicy"]["crossAccountAggregationAllowed"] is False

    preview = run_async(cognix_routes.preview_pulse(current_subject = "alice"))
    plan = preview["pulsePlan"]
    assert plan["pulseVersion"] == cognix_pulse.COGNIX_PULSE_VERSION
    assert plan["summary"]["eventCount"] >= 6
    assert plan["summary"]["criticalCount"] >= 1
    assert plan["privacy"]["crossAccountAggregation"] is False
    assert plan["sideEffects"]["modelLoad"] is False
    assert plan["sideEffects"]["networkCall"] is False
    source_ids = {event["sourceId"] for event in plan["digest"]["recentEvents"]}
    titles = {event["title"] for event in plan["digest"]["recentEvents"]}
    assert "thread-alice" in source_ids
    assert "thread-bob" not in source_ids
    assert "Conversation Bob secrete" not in titles

    generated = run_async(cognix_routes.generate_pulse(current_subject = "alice"))
    assert generated["report"]["id"].startswith("pul_")
    assert generated["report"]["sourceThreadIds"] == ["thread-alice"]
    assert "Projet physique CogniX" in generated["report"]["topics"]
    assert generated["sideEffects"]["pulseReportWrite"] is True
    assert generated["sideEffects"]["auditWrite"] is True
    assert generated["sideEffects"]["modelLoad"] is False
    assert generated["sideEffects"]["crossUserRead"] is False

    reports = run_async(cognix_routes.my_pulse(current_subject = "alice"))
    assert reports["blueprint"]["pulseVersion"] == "cognix_pulse_v1"
    assert reports["reports"][0]["id"] == generated["report"]["id"]
    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert admin_read["logs"][0]["action"] == "pulse_report_generated"
    assert admin_read["logs"][0]["metadata"]["sideEffects"]["pulseReportWrite"] is True


def test_library_native_blueprint_search_and_audited_asset_creation():
    seed_accounts()
    cognix_db.create_library_item(
        "bob",
        kind = "document",
        name = "Document prive Bob",
        source = "manual",
        metadata = {"tags": ["private"]},
    )

    blueprint = run_async(cognix_routes.library_blueprint(current_subject = "alice"))
    assert blueprint["blueprint"]["libraryVersion"] == cognix_library.COGNIX_LIBRARY_VERSION
    assert "directive" in blueprint["blueprint"]["assetTypes"]
    assert blueprint["blueprint"]["searchContract"]["crossUserSearchAllowed"] is False
    assert blueprint["blueprint"]["modelRegistrationPolicy"]["evaluationReportRequired"] is True
    assert blueprint["blueprint"]["modelRegistrationPolicy"]["genericModelWriteBypassAllowed"] is False
    assert blueprint["sideEffects"]["assetWrite"] is False
    assert blueprint["sideEffects"]["modelRegistryWrite"] is False

    created = run_async(
        cognix_routes.create_library_item(
            cognix_routes.LibraryItemRequest(
                kind = "directive",
                name = "Directive securite projet",
                source = "manual",
                metadata = {"tags": ["securite", "projet"], "projectId": "project-sec"},
            ),
            current_subject = "alice",
        )
    )
    assert created["item"]["kind"] == "directive"
    assert created["assetPlan"]["classification"]["assetFamily"] == "behavior"
    assert created["assetPlan"]["classification"]["ragCandidate"] is True
    assert created["sideEffects"]["assetWrite"] is True
    assert created["sideEffects"]["auditWrite"] is True
    assert created["sideEffects"]["ragIndexWrite"] is False
    assert created["sideEffects"]["modelLoad"] is False

    search = run_async(cognix_routes.search_library(query = "securite", current_subject = "alice"))
    results = search["librarySearch"]
    assert results["libraryVersion"] == cognix_library.COGNIX_LIBRARY_VERSION
    assert results["totalMatches"] == 1
    assert results["matches"][0]["name"] == "Directive securite projet"
    assert results["matches"][0]["projectId"] == "project-sec"
    assert results["matches"][0]["classification"]["ragCandidate"] is True
    assert "Document prive Bob" not in {item["name"] for item in results["matches"]}
    assert search["sideEffects"]["crossUserRead"] is False

    library = run_async(cognix_routes.my_library(current_subject = "alice"))
    assert library["summary"]["assetCount"] == 1
    assert library["summary"]["byKind"]["directive"] == 1
    assert library["summary"]["ragCandidateCount"] == 1
    assert library["blueprint"]["libraryVersion"] == "cognix_library_v1"

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert admin_read["logs"][0]["action"] == "library_item_created"
    assert admin_read["logs"][0]["metadata"]["classification"]["assetFamily"] == "behavior"
    assert admin_read["logs"][0]["metadata"]["sideEffects"]["assetWrite"] is True


def test_library_blocks_model_assets_without_evaluation_gate():
    seed_accounts()
    plan = cognix_library.build_library_asset_plan(
        username = "alice",
        kind = "lora_adapter",
        name = "CogniX Style LoRA",
        source = "fine_tuning",
        metadata = {
            "artifactId": "lora_style_v1",
            "secretValue": "must not be stored",
        },
    )

    gate = plan["registrationGate"]
    assert gate["gateVersion"] == "cognix_model_library_registration_v1"
    assert gate["required"] is True
    assert gate["status"] == "blocked"
    assert "evaluation_report_declared" in gate["blockedGateIds"]
    assert "evaluation_status_passed" in gate["blockedGateIds"]
    assert plan["sideEffects"]["assetWrite"] is False
    assert plan["sideEffects"]["modelRegistryWrite"] is False
    assert "secretValue" not in plan["asset"]["metadata"]
    assert plan["asset"]["metadata"]["redactedMetadataKeys"] == ["secretValue"]

    with pytest.raises(HTTPException) as exc:
        run_async(
            cognix_routes.create_library_item(
                cognix_routes.LibraryItemRequest(
                    kind = "lora_adapter",
                    name = "CogniX Style LoRA",
                    source = "fine_tuning",
                    metadata = {
                        "artifactId": "lora_style_v1",
                        "secretValue": "must not be stored",
                    },
                ),
                current_subject = "alice",
            )
        )

    assert exc.value.status_code == 403
    assert "evaluation_report_declared" in exc.value.detail["blockedGateIds"]
    assert exc.value.detail["auditLogId"].startswith("aud_")
    assert cognix_db.list_library_items("alice") == []

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["action"] == "library_model_registration_blocked"
    assert log["metadata"]["sideEffects"]["assetWrite"] is False
    assert "must not be stored" not in log["metadataJson"]


def test_library_allows_evaluated_lora_registration_with_audit():
    seed_accounts()
    created = run_async(
        cognix_routes.create_library_item(
            cognix_routes.LibraryItemRequest(
                kind = "lora_adapter",
                name = "CogniX Style LoRA",
                source = "fine_tuning",
                metadata = {
                    "artifactId": "lora_style_v1",
                    "adapterRef": "artifact://lora/style-v1",
                    "evaluationReportRef": "eval://reports/lora-style-v1",
                    "evaluationStatus": "passed",
                    "evaluationPlanVersion": "cognix_fine_tuning_evaluation_plan_v1",
                    "safetyReviewPassed": True,
                    "humanApproved": True,
                    "projectId": "project-training",
                },
            ),
            current_subject = "alice",
        )
    )

    gate = created["assetPlan"]["registrationGate"]
    assert created["item"]["kind"] == "lora_adapter"
    assert created["item"]["metadata"]["modelRegistrationGate"]["status"] == "ready"
    assert gate["status"] == "ready"
    assert gate["readyForLibraryWrite"] is True
    assert gate["blockedGateIds"] == []
    assert created["sideEffects"]["assetWrite"] is True
    assert created["sideEffects"]["modelRegistryWrite"] is False
    assert created["sideEffects"]["evaluationJob"] is False

    search = run_async(cognix_routes.search_library(kind = "lora_adapter", current_subject = "alice"))
    assert search["librarySearch"]["totalMatches"] == 1
    assert search["librarySearch"]["matches"][0]["classification"]["assetFamily"] == "modeling"

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["action"] == "library_item_created"
    assert log["metadata"]["registrationGate"]["status"] == "ready"
    assert log["metadata"]["sideEffects"]["assetWrite"] is True
    assert log["metadata"]["sideEffects"]["modelRegistryWrite"] is False


def test_scheduled_native_plan_permission_ceiling_and_audited_runs():
    seed_accounts()

    blueprint = run_async(cognix_routes.scheduled_tasks_blueprint(current_subject = "alice"))
    assert blueprint["blueprint"]["scheduledVersion"] == cognix_scheduled.COGNIX_SCHEDULED_VERSION
    assert blueprint["blueprint"]["securityPolicy"]["creatorPermissionCeiling"] is True
    assert blueprint["sideEffects"]["taskWrite"] is False

    plan = run_async(
        cognix_routes.plan_scheduled_task(
            cognix_routes.ScheduledTaskCreateRequest(
                title = "Audit securite nocturne",
                prompt = "verifier les vulnerabilites chaque nuit",
                schedule_text = "tous les jours a 02:30",
            ),
            current_subject = "alice",
        )
    )
    security_plan = plan["scheduledTaskPlan"]
    assert security_plan["action"]["actionType"] == "security_audit"
    assert security_plan["schedule"]["cadence"] == "daily"
    assert security_plan["schedule"]["hour"] == 2
    assert security_plan["permissionPlan"]["missingPermissions"] == ["security:audit"]
    assert security_plan["executionPlan"]["canRunNow"] is False
    assert security_plan["sideEffects"]["securityScan"] is False

    created_security = run_async(
        cognix_routes.create_scheduled_task(
            cognix_routes.ScheduledTaskCreateRequest(
                title = "Audit securite nocturne",
                prompt = "verifier les vulnerabilites chaque nuit",
                schedule_text = "tous les jours a 02:30",
            ),
            current_subject = "alice",
        )
    )
    assert created_security["task"]["id"].startswith("tsk_")
    assert created_security["scheduledTaskPlan"]["permissionPlan"]["missingPermissions"] == ["security:audit"]
    assert created_security["sideEffects"]["taskWrite"] is True
    assert created_security["sideEffects"]["auditWrite"] is True

    blocked = run_async(
        cognix_routes.run_scheduled_task(
            created_security["task"]["id"],
            current_subject = "alice",
        )
    )
    assert blocked["run"]["status"] == "failed"
    assert blocked["scheduledTaskPlan"]["action"]["actionType"] == "security_audit"
    assert blocked["sideEffects"]["taskRunWrite"] is True
    assert blocked["sideEffects"]["securityScan"] is False
    assert "security:audit" in blocked["run"]["result"]

    created_report = run_async(
        cognix_routes.create_scheduled_task(
            cognix_routes.ScheduledTaskCreateRequest(
                title = "Resume quotidien",
                prompt = "resume les nouveaux documents du projet",
                schedule_text = "tous les jours a 08:00",
            ),
            current_subject = "alice",
        )
    )
    assert created_report["scheduledTaskPlan"]["action"]["actionType"] == "report"
    assert created_report["scheduledTaskPlan"]["permissionPlan"]["missingPermissions"] == []

    report_run_plan = run_async(
        cognix_routes.scheduled_task_run_plan(
            created_report["task"]["id"],
            current_subject = "alice",
        )
    )
    assert report_run_plan["scheduledTaskPlan"]["executionPlan"]["canRunNow"] is True
    assert report_run_plan["scheduledTaskPlan"]["queuePlan"]["queueName"] == "scheduled_reports"

    report_run = run_async(
        cognix_routes.run_scheduled_task(
            created_report["task"]["id"],
            current_subject = "alice",
        )
    )
    assert report_run["run"]["status"] == "complete"
    assert report_run["run"]["artifactType"] == "library_item"
    assert report_run["sideEffects"]["libraryWrite"] is True
    assert report_run["sideEffects"]["networkCall"] is False
    assert report_run["sideEffects"]["modelLoad"] is False

    listing = run_async(cognix_routes.my_scheduled_tasks(current_subject = "alice"))
    assert listing["blueprint"]["scheduledVersion"] == "cognix_scheduled_v1"
    assert len(listing["tasks"]) == 2
    assert len(listing["runs"]) == 2

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    actions = [log["action"] for log in admin_read["logs"][:6]]
    assert "scheduled_task_run_completed" in actions
    assert "scheduled_task_run_blocked" in actions
    assert any(log["metadata"].get("scheduledVersion") == "cognix_scheduled_v1" for log in admin_read["logs"])


def test_images_native_plan_safety_library_link_and_permission_ceiling():
    seed_accounts()
    cognix_db.create_image_request("bob", "image privee bob", "private-model")

    blueprint = run_async(cognix_routes.images_blueprint(current_subject = "alice"))
    assert blueprint["blueprint"]["imagesVersion"] == cognix_images.COGNIX_IMAGES_VERSION
    assert blueprint["blueprint"]["runtimePolicy"]["frontendDirectModelCallAllowed"] is False
    assert blueprint["sideEffects"]["generation"] is False

    plan = run_async(
        cognix_routes.plan_image(
            cognix_routes.ImageRequest(
                prompt = "cree 3 variantes du logo CogniX blanc",
                model = "local-image-test",
                variantCount = 3,
                projectId = "project-logo",
            ),
            current_subject = "alice",
        )
    )
    image_plan = plan["imagePlan"]
    assert image_plan["action"]["actionType"] == "variants"
    assert image_plan["variantPlan"]["count"] == 3
    assert image_plan["modelPlan"]["selectedModel"] == "local-image-test"
    assert image_plan["safety"]["status"] == "clear"
    assert image_plan["permissionPlan"]["missingPermissions"] == []
    assert image_plan["sideEffects"]["modelLoad"] is False

    created = run_async(
        cognix_routes.create_image(
            cognix_routes.ImageRequest(
                prompt = "cree 3 variantes du logo CogniX blanc",
                model = "local-image-test",
                variantCount = 3,
                projectId = "project-logo",
            ),
            current_subject = "alice",
        )
    )
    assert created["image"]["id"].startswith("img_")
    assert created["image"]["status"] == "queued"
    assert created["imagePlan"]["variantPlan"]["count"] == 3
    assert created["libraryItem"]["kind"] == "image"
    assert created["libraryItem"]["metadata"]["imageRequestId"] == created["image"]["id"]
    assert created["libraryItem"]["metadata"]["projectId"] == "project-logo"
    assert created["sideEffects"]["imageRequestWrite"] is True
    assert created["sideEffects"]["libraryWrite"] is True
    assert created["sideEffects"]["generation"] is False
    assert created["sideEffects"]["modelLoad"] is False

    with pytest.raises(HTTPException) as blocked_edit:
        run_async(
            cognix_routes.create_image(
                cognix_routes.ImageRequest(
                    prompt = "modifie cette image",
                    mode = "edit",
                    sourceImageId = created["image"]["id"],
                ),
                current_subject = "alice",
            )
        )
    assert blocked_edit.value.status_code == 403

    sensitive = run_async(
        cognix_routes.plan_image(
            cognix_routes.ImageRequest(prompt = "illustration avec mot de passe visible"),
            current_subject = "alice",
        )
    )
    assert sensitive["imagePlan"]["safety"]["status"] == "needs_review"
    assert sensitive["imagePlan"]["warnings"][0]["id"] == "image_safety_review"

    listing = run_async(cognix_routes.my_images(current_subject = "alice"))
    assert listing["blueprint"]["imagesVersion"] == "cognix_images_v1"
    assert listing["summary"]["requestCount"] == 1
    assert "image privee bob" not in {item["prompt"] for item in listing["images"]}

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert admin_read["logs"][0]["action"] == "image_request_created"
    assert admin_read["logs"][0]["metadata"]["imagesVersion"] == "cognix_images_v1"
    assert admin_read["logs"][0]["metadata"]["sideEffects"]["generation"] is False


def test_apps_native_registry_permission_scan_and_audited_connection():
    seed_accounts()

    blueprint = run_async(cognix_routes.apps_blueprint(current_subject = "alice"))
    assert blueprint["blueprint"]["appsVersion"] == cognix_apps.COGNIX_APPS_VERSION
    assert blueprint["blueprint"]["securityPolicy"]["manifestRequired"] is True
    assert blueprint["blueprint"]["securityPolicy"]["tokenReadAllowedInRegistry"] is False
    assert blueprint["sideEffects"]["tokenRead"] is False

    registry = run_async(cognix_routes.apps_registry(current_subject = "alice"))
    app_registry = registry["appRegistry"]
    apps = {item["id"]: item for item in app_registry["apps"]}
    assert app_registry["summary"]["appCount"] >= 6
    assert apps["github"]["permissionScan"]["maxRiskLevel"] == "high"
    assert apps["github"]["permissionScan"]["missingRequiredPermissions"] == ["github:read"]
    assert registry["sideEffects"]["tokenRead"] is False

    plan = run_async(
        cognix_routes.plan_app_connection(
            cognix_routes.AppConnectionRequest(
                app_id = "github",
                app_name = "GitHub",
                status = "connected",
            ),
            current_subject = "alice",
        )
    )
    github_plan = plan["appConnectionPlan"]
    assert github_plan["allowed"] is False
    assert github_plan["status"] == "missing_permissions"
    assert github_plan["securityReview"]["missingRequiredPermissions"] == ["github:read"]
    assert github_plan["sideEffects"]["connectionWrite"] is False

    with pytest.raises(HTTPException) as blocked:
        run_async(
            cognix_routes.set_app_connection(
                cognix_routes.AppConnectionRequest(
                    app_id = "github",
                    app_name = "GitHub",
                    status = "connected",
                ),
                current_subject = "alice",
            )
        )
    assert blocked.value.status_code == 403
    assert cognix_db.list_app_connections("alice") == []

    cognix_db.grant_user_permission(
        "alice",
        "github:read",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )
    connected = run_async(
        cognix_routes.set_app_connection(
            cognix_routes.AppConnectionRequest(
                app_id = "github",
                app_name = "GitHub",
                status = "connected",
            ),
            current_subject = "alice",
        )
    )
    assert connected["connection"]["appId"] == "github"
    assert connected["connection"]["status"] == "connected"
    assert connected["appConnectionPlan"]["allowed"] is True
    assert connected["appConnectionPlan"]["permissionScan"]["missingRequiredPermissions"] == []
    assert connected["sideEffects"]["connectionWrite"] is True
    assert connected["sideEffects"]["tokenRead"] is False
    assert connected["sideEffects"]["tokenWrite"] is False
    assert connected["sideEffects"]["toolExecution"] is False

    apps_read = run_async(cognix_routes.my_apps(current_subject = "alice"))
    assert apps_read["blueprint"]["appsVersion"] == "cognix_apps_v1"
    assert apps_read["appRegistry"]["summary"]["connectedCount"] == 1
    github = next(item for item in apps_read["appRegistry"]["apps"] if item["id"] == "github")
    assert github["connection"]["connected"] is True

    disabled = run_async(
        cognix_routes.set_app_connection(
            cognix_routes.AppConnectionRequest(
                app_id = "github",
                app_name = "GitHub",
                status = "disabled",
            ),
            current_subject = "alice",
        )
    )
    assert disabled["connection"]["status"] == "disabled"
    assert disabled["appConnectionPlan"]["connectionPlan"]["revocation"] is True

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    actions = [log["action"] for log in admin_read["logs"][:5]]
    assert "app_connection_updated" in actions
    assert "app_connection_blocked" in [log["action"] for log in admin_read["logs"]]
    assert any(log["metadata"].get("appsVersion") == "cognix_apps_v1" for log in admin_read["logs"])


def test_tool_registry_declares_permissions_and_guardrails():
    registry = cognix_tool_registry.build_tool_registry()

    assert registry["registryVersion"] == "cognix_tool_registry_v1"
    assert registry["mode"] == "declarative_guarded"
    assert registry["summary"]["executionEnabled"] is False
    assert registry["globalPolicies"]["frontendDirectExecutionAllowed"] is False
    assert registry["globalPolicies"]["rateLimitsEnabled"] is True
    assert registry["globalPolicies"]["permissionMatrixAvailable"] is True
    assert registry["globalPolicies"]["executionContractRequired"] is True
    assert registry["globalPolicies"]["executionBoundaryContractRequired"] is True
    assert registry["globalPolicies"]["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert registry["globalPolicies"]["secretPolicyRequired"] is True
    assert registry["globalPolicies"]["secretPolicyVersion"] == "cognix_tool_secret_policy_v1"
    assert registry["sideEffects"]["toolExecution"] is False

    tools = {tool["id"]: tool for tool in registry["tools"]}
    assert {
        "calculator",
        "physics-solver",
        "latex-renderer",
        "github",
        "google-drive",
        "gmail",
        "notion",
        "microsoft-365",
        "google-workspace",
        "sharepoint",
        "microsoft-teams",
        "slack",
        "moodle",
        "crm",
        "erp",
        "internal-tools",
        "codex-secure-agent",
        "kali-isolated",
    }.issubset(tools)
    calculator_actions = {action["id"]: action for action in tools["calculator"]["actions"]}
    evaluate = calculator_actions["evaluate_expression"]
    assert tools["calculator"]["enabled"] is True
    assert evaluate["riskLevel"] == "low"
    assert evaluate["requiresConfirmation"] is False
    assert evaluate["secretPolicy"]["requiresSecret"] is False
    assert evaluate["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert cognix_tool_registry.rate_limit_policy_for_key(evaluate["rateLimitKey"]) == {
        "windowSeconds": 60,
        "maxEvents": 240,
    }
    physics_actions = {action["id"]: action for action in tools["physics-solver"]["actions"]}
    solve_formula = physics_actions["solve_formula"]
    assert tools["physics-solver"]["enabled"] is True
    assert solve_formula["riskLevel"] == "low"
    assert solve_formula["requiresConfirmation"] is False
    assert solve_formula["secretPolicy"]["requiresSecret"] is False
    assert solve_formula["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert cognix_tool_registry.rate_limit_policy_for_key(solve_formula["rateLimitKey"]) == {
        "windowSeconds": 60,
        "maxEvents": 180,
    }
    latex_actions = {action["id"]: action for action in tools["latex-renderer"]["actions"]}
    render_math = latex_actions["render_math"]
    assert tools["latex-renderer"]["enabled"] is True
    assert render_math["riskLevel"] == "low"
    assert render_math["requiresConfirmation"] is False
    assert render_math["secretPolicy"]["requiresSecret"] is False
    assert render_math["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert cognix_tool_registry.rate_limit_policy_for_key(render_math["rateLimitKey"]) == {
        "windowSeconds": 60,
        "maxEvents": 240,
    }
    gmail_actions = {action["id"]: action for action in tools["gmail"]["actions"]}
    send_mail = gmail_actions["send_mail"]
    assert send_mail["riskLevel"] == "high"
    assert send_mail["requiresConfirmation"] is True
    assert send_mail["auditRequired"] is True
    assert send_mail["secretPolicy"]["policyVersion"] == "cognix_tool_secret_policy_v1"
    assert send_mail["secretPolicy"]["requiresSecret"] is True
    assert send_mail["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert send_mail["secretPolicy"]["auditSecretValueAllowed"] is False
    assert cognix_tool_registry.rate_limit_policy_for_key(send_mail["rateLimitKey"]) == {
        "windowSeconds": 300,
        "maxEvents": 5,
    }

    kali_actions = {action["id"]: action for action in tools["kali-isolated"]["actions"]}
    assert kali_actions["active_test"]["sandboxRequired"] is True
    assert "admin" in kali_actions["active_test"]["permissions"]

    sharepoint_actions = {action["id"]: action for action in tools["sharepoint"]["actions"]}
    assert sharepoint_actions["delete_site_file"]["riskLevel"] == "critical"
    assert sharepoint_actions["delete_site_file"]["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert cognix_tool_registry.rate_limit_policy_for_key("sharepoint:delete") == {
        "windowSeconds": 300,
        "maxEvents": 2,
    }

    moodle_actions = {action["id"]: action for action in tools["moodle"]["actions"]}
    assert moodle_actions["publish_grade"]["riskLevel"] == "critical"
    assert moodle_actions["publish_grade"]["requiresConfirmation"] is True
    assert "admin" in moodle_actions["publish_grade"]["permissions"]

    crm_actions = {action["id"]: action for action in tools["crm"]["actions"]}
    assert crm_actions["export_customer_data"]["sandboxRequired"] is True
    assert crm_actions["export_customer_data"]["secretPolicy"]["serverSideResolutionRequired"] is True

    erp_actions = {action["id"]: action for action in tools["erp"]["actions"]}
    assert erp_actions["approve_payment"]["riskLevel"] == "critical"

    internal_actions = {action["id"]: action for action in tools["internal-tools"]["actions"]}
    assert internal_actions["run_internal_job"]["sandboxRequired"] is True


def test_native_calculator_evaluates_expression_without_model_or_network():
    result = cognix_native_tools.evaluate_calculator_expression("sqrt(81) + 2 * pi", precision = 10)

    assert result["calculatorVersion"] == "cognix_native_calculator_v1"
    assert result["status"] == "evaluated"
    assert result["resultText"].startswith("15.28318")
    assert result["safety"]["allowedFunctions"]
    assert result["sideEffects"]["calculatorEvaluation"] is True
    assert result["sideEffects"]["modelLoad"] is False
    assert result["sideEffects"]["generation"] is False
    assert result["sideEffects"]["networkToolCall"] is False


def test_native_calculator_blocks_unsafe_ast_without_execution_side_effects():
    with pytest.raises(cognix_native_tools.CalculatorValidationError):
        cognix_native_tools.evaluate_calculator_expression("__import__('os').system('id')")


def test_native_physics_solver_solves_missing_force_without_model_or_network():
    result = cognix_native_tools.solve_physics_formula(
        formula_id = "force",
        variables = {"mass": 12, "acceleration": 2.5},
        precision = 12,
    )

    assert result["physicsSolverVersion"] == "cognix_native_physics_solver_v1"
    assert result["status"] == "solved"
    assert result["targetVariable"] == "force"
    assert result["targetUnit"] == "N"
    assert result["resultText"] == "30"
    assert result["sideEffects"]["physicsSolve"] is True
    assert result["sideEffects"]["modelLoad"] is False
    assert result["sideEffects"]["generation"] is False
    assert result["sideEffects"]["networkToolCall"] is False


def test_native_physics_solver_blocks_ambiguous_formula_without_execution_side_effects():
    with pytest.raises(cognix_native_tools.PhysicsSolverValidationError):
        cognix_native_tools.solve_physics_formula(
            formula_id = "speed",
            variables = {"speed": 10, "distance": 100, "time": 10},
        )


def test_native_latex_renderer_builds_katex_packet_without_model_or_files():
    result = cognix_native_tools.render_latex_expression(
        source = r"\frac{a}{b} = c^2",
        display_mode = True,
        context = "physics",
    )

    assert result["latexRendererVersion"] == "cognix_native_latex_renderer_v1"
    assert result["status"] == "render_packet_ready"
    assert result["renderTarget"] == "streamdown_katex"
    assert result["context"] == "physics"
    assert result["markdown"].startswith("$$")
    assert result["sourceHash"]
    assert "frac" in result["commands"]
    assert result["sideEffects"]["latexRenderPacket"] is True
    assert result["sideEffects"]["fileRead"] is False
    assert result["sideEffects"]["fileWrite"] is False
    assert result["sideEffects"]["networkToolCall"] is False
    assert result["sideEffects"]["modelLoad"] is False


def test_native_latex_renderer_blocks_file_commands_without_side_effects():
    with pytest.raises(cognix_native_tools.LatexRendererValidationError):
        cognix_native_tools.render_latex_expression(source = r"\input{/etc/passwd}")


def test_tool_action_plan_builds_execution_contract_without_execution():
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "codex-secure-agent",
        action_id = "modify_code",
        username = "alice",
        has_developer_mode = True,
        granted_permissions = set(),
    )

    contract = plan["executionContract"]
    assert plan["executionContractVersion"] == "cognix_tool_execution_contract_v1"
    assert plan["secretPolicy"]["policyVersion"] == "cognix_tool_secret_policy_v1"
    assert plan["secretPolicy"]["requiresSecret"] is False
    assert plan["allowed"] is True
    assert contract["contractVersion"] == "cognix_tool_execution_contract_v1"
    assert contract["boundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert contract["mode"] == "guarded_plan_only"
    assert contract["allowedToPrepare"] is True
    assert contract["readyForExecution"] is False
    assert contract["automaticExecutionAllowed"] is False
    assert contract["frontendDirectExecutionAllowed"] is False
    assert contract["executorRequired"] is True
    assert contract["preconditions"]["humanConfirmationRequired"] is True
    assert contract["preconditions"]["sandboxRequired"] is True
    assert contract["preconditions"]["rateLimitRequired"] is True
    assert contract["preconditions"]["secretPolicyVersion"] == "cognix_tool_secret_policy_v1"
    assert contract["dataBoundary"]["rawSecretExposureAllowed"] is False
    assert contract["secretPolicy"]["clientSecretTransmitAllowed"] is False
    assert "human_confirmation_required" in contract["blockedWhen"]
    assert "sandbox_required" in contract["blockedWhen"]
    assert "rate_limit_check_required" in contract["blockedWhen"]
    assert "tool_execution" in contract["blockedActions"]
    assert contract["sideEffects"]["toolExecution"] is False
    assert plan["sideEffects"]["toolExecution"] is False


def test_tool_action_plan_builds_execution_boundary_contract_without_execution():
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "codex-secure-agent",
        action_id = "modify_code",
        username = "alice",
        has_developer_mode = True,
        granted_permissions = set(),
    )

    boundary = plan["executionBoundaryContract"]
    assert plan["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert boundary["contractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert boundary["mode"] == "pre_executor_boundary"
    assert boundary["status"] == "closed_until_executor_review"
    assert boundary["manifest"]["declared"] is True
    assert boundary["manifest"]["toolEnabled"] is True
    assert boundary["manifest"]["riskLevel"] == "high"
    assert boundary["rbac"]["allowedByRbac"] is True
    assert boundary["requestBoundary"]["toolExecutionAllowedHere"] is False
    assert boundary["requestBoundary"]["frontendDirectExecutionAllowed"] is False
    assert boundary["requestBoundary"]["rawPayloadAuditAllowed"] is False
    assert boundary["executorBoundary"]["executorRequired"] is True
    assert boundary["executorBoundary"]["plannedExecutorQueue"] == "cognix_worker_queue:tool_execution"
    assert boundary["executorBoundary"]["jobEnqueueAllowedHere"] is False
    assert boundary["secretBoundary"]["secretReadAllowedHere"] is False
    assert boundary["networkBoundary"]["networkToolCallAllowedHere"] is False
    assert boundary["auditBoundary"]["auditLogRawPayloadAllowed"] is False
    assert "job_enqueue" in boundary["blockedActions"]
    assert "executor_boundary_required" in boundary["blockedWhen"]
    assert boundary["sideEffects"]["toolExecution"] is False
    assert boundary["sideEffects"]["jobEnqueue"] is False


def test_tool_execution_handoff_prepares_executor_packet_without_enqueuing():
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "codex-secure-agent",
        action_id = "modify_code",
        username = "alice",
        has_developer_mode = True,
        granted_permissions = set(),
    )
    plan = cognix_tool_registry.apply_rate_limit_result(
        plan,
        {
            "allowed": True,
            "remaining": 19,
            "resetAt": "2026-06-29T00:00:00Z",
        },
    )

    handoff = cognix_tool_registry.build_tool_execution_handoff(
        plan = plan,
        confirmation_id = "conf_123",
        sandbox_run_id = "sbx_123",
        request_id = "req_123",
    )

    assert handoff["handoffVersion"] == "cognix_tool_execution_handoff_v1"
    assert handoff["executionContractVersion"] == "cognix_tool_execution_contract_v1"
    assert handoff["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert handoff["executionBoundary"]["toolExecutionAllowedHere"] is False
    assert handoff["executionBoundary"]["jobEnqueueAllowedHere"] is False
    assert handoff["executionBoundary"]["executorMustRecheckBoundary"] is True
    assert handoff["status"] == "ready_for_executor_review"
    assert handoff["readyForExecutorReview"] is True
    assert handoff["readyForJobEnqueue"] is False
    assert handoff["executionAllowedHere"] is False
    assert handoff["executorInput"]["confirmationId"] == "conf_123"
    assert handoff["executorInput"]["sandboxRunId"] == "sbx_123"
    assert handoff["executorInput"]["secretValuesIncluded"] is False
    assert handoff["dataBoundary"]["rawPayloadIncluded"] is False
    assert handoff["policies"]["jobEnqueueAllowedHere"] is False
    assert "executor_approval_required" in handoff["blockedWhen"]
    assert all(gate["passed"] for gate in handoff["gates"])
    assert handoff["sideEffects"]["jobEnqueue"] is False
    assert handoff["sideEffects"]["toolExecution"] is False
    assert handoff["sideEffects"]["secretRead"] is False


def test_tool_permission_matrix_summarizes_effective_permissions_without_execution():
    matrix = cognix_tool_registry.build_tool_permission_matrix(
        username = "alice",
        is_admin = False,
        has_developer_mode = True,
        granted_permissions = {"github:read"},
    )

    assert matrix["registryVersion"] == "cognix_tool_registry_v1"
    assert matrix["mode"] == "permission_matrix_dry_run"
    assert matrix["summary"]["executionEnabled"] is False
    assert matrix["policies"]["permissionSource"] == "cognix_user_permissions_plus_role"
    assert matrix["policies"]["executionBoundaryContractRequired"] is True
    assert matrix["policies"]["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert matrix["sideEffects"]["permissionWrite"] is False
    assert matrix["sideEffects"]["secretRead"] is False
    assert matrix["sideEffects"]["toolExecution"] is False
    assert "authenticated" in matrix["permissionContext"]["effectivePermissions"]
    assert "developer_mode" in matrix["permissionContext"]["effectivePermissions"]
    assert "github:read" in matrix["permissionContext"]["effectivePermissions"]

    tools = {tool["id"]: tool for tool in matrix["tools"]}
    codex_actions = {action["id"]: action for action in tools["codex-secure-agent"]["actions"]}
    assert codex_actions["plan_feature"]["allowed"] is True
    assert codex_actions["plan_feature"]["guardrails"]["frontendDirectExecutionAllowed"] is False
    assert codex_actions["modify_code"]["allowed"] is True
    assert codex_actions["modify_code"]["guardrails"]["sandboxRequired"] is True

    github_actions = {action["id"]: action for action in tools["github"]["actions"]}
    assert github_actions["read_repository"]["allowed"] is False
    assert github_actions["read_repository"]["status"] == "connector_disabled"
    assert github_actions["read_repository"]["missingPermissions"] == []
    assert github_actions["merge_pull_request"]["guardrails"]["adminRequired"] is True
    assert "admin" in github_actions["merge_pull_request"]["missingPermissions"]


def test_tool_permission_matrix_endpoint_uses_database_permissions():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "github:read",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    matrix = run_async(
        cognix_routes.tool_permission_matrix(current_subject = "alice")
    )

    assert matrix["username"] == "alice"
    assert matrix["mode"] == "permission_matrix_dry_run"
    assert "github:read" in matrix["permissionContext"]["explicitPermissions"]
    tools = {tool["id"]: tool for tool in matrix["tools"]}
    github_actions = {action["id"]: action for action in tools["github"]["actions"]}
    assert github_actions["read_repository"]["status"] == "connector_disabled"
    assert github_actions["read_repository"]["missingPermissions"] == []
    assert github_actions["read_repository"]["sideEffects"]["toolExecution"] is False


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
    assert status["summary"]["activationContractRequired"] is True
    assert status["policies"]["secretsStayServerSide"] is True
    assert status["policies"]["activationRequiresSeparateExecutor"] is True
    assert status["sideEffects"]["secretRead"] is False
    assert status["sideEffects"]["toolExecution"] is False

    integrations = {item["id"]: item for item in status["integrations"]}
    assert integrations["github"]["status"] == "declared_disabled"
    assert integrations["github"]["secretState"] == "required_unverified"
    assert any(item["id"] == "configure_server_secret" for item in integrations["github"]["nextActions"])
    assert integrations["codex-secure-agent"]["enabled"] is True
    assert integrations["sharepoint"]["dataIsolation"] == "organization"
    assert integrations["sharepoint"]["maxRiskLevel"] == "critical"
    assert integrations["moodle"]["secretState"] == "required_unverified"
    assert integrations["erp"]["maxRiskLevel"] == "critical"


def test_connector_roadmap_readiness_maps_mvp_connectors_without_execution():
    readiness = cognix_integration_manager.build_connector_roadmap_readiness(
        username = "alice",
        is_admin = False,
        has_developer_mode = True,
        granted_permissions = {"github:read", "drive:read", "notion:read", "moodle:read", "slack:read", "teams:read"},
    )

    assert readiness["connectorRoadmapReadinessVersion"] == "cognix_connector_roadmap_readiness_v1"
    assert readiness["mode"] == "connector_roadmap_readiness_dry_run"
    assert readiness["sourceOfTruth"] == "roadmap_phase_7_connectors"
    assert readiness["summary"]["roadmapConnectorCount"] == 6
    assert readiness["summary"]["declaredConnectorCount"] == 6
    assert readiness["summary"]["readyForMvpConnectorLayer"] is True
    assert readiness["summary"]["readyForExternalExecution"] is False
    connectors = {item["id"]: item for item in readiness["connectors"]}
    assert set(connectors) == {"github", "google-drive", "microsoft-365", "notion", "moodle", "slack-teams"}
    assert connectors["github"]["status"] == "manifest_ready_activation_pending"
    assert connectors["github"]["readyForMvpConnectorLayer"] is True
    assert connectors["github"]["readyForExecution"] is False
    assert "github" in connectors["github"]["declaredToolIds"]
    assert "server_secret_unverified" in connectors["github"]["activationBlockers"]
    assert connectors["microsoft-365"]["declaredToolIds"] == ["microsoft-365", "sharepoint"]
    assert connectors["slack-teams"]["declaredToolIds"] == ["slack", "microsoft-teams"]
    assert connectors["slack-teams"]["writeActionCount"] >= 2
    assert connectors["moodle"]["maxRiskLevel"] in {"high", "critical"}
    assert all(item["securityContract"]["auditRequiredForAllActions"] for item in connectors.values())
    assert all(item["securityContract"]["rateLimitsDeclaredForAllActions"] for item in connectors.values())
    assert all(item["securityContract"]["humanConfirmationForWrites"] for item in connectors.values())
    assert readiness["policies"]["frontendDirectToolCallAllowed"] is False
    assert readiness["policies"]["networkToolCallAllowedHere"] is False
    assert readiness["policies"]["toolExecutionAllowedHere"] is False
    assert readiness["sideEffects"]["secretRead"] is False
    assert readiness["sideEffects"]["toolExecution"] is False
    assert readiness["sideEffects"]["networkToolCall"] is False


def test_connector_roadmap_readiness_endpoint_is_user_scoped_and_read_only():
    seed_accounts()
    for permission_key in (
        "github:read",
        "drive:read",
        "notion:read",
        "moodle:read",
        "slack:read",
        "teams:read",
    ):
        cognix_db.grant_user_permission(
            "alice",
            permission_key,
            granted_by = storage.DEFAULT_ADMIN_USERNAME,
        )

    body = run_async(cognix_routes.integrations_roadmap_readiness(current_subject = "alice"))

    readiness = body["connectorRoadmapReadiness"]
    assert body["plannerVersion"] == "cognix_connector_roadmap_readiness_v1"
    assert body["username"] == "alice"
    assert readiness["username"] == "alice"
    assert readiness["summary"]["roadmapConnectorCount"] == 6
    assert readiness["summary"]["missingManifestCount"] == 0
    assert readiness["summary"]["readyForMvpConnectorLayer"] is True
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["secretWrite"] is False
    assert body["sideEffects"]["toolExecution"] is False
    assert body["sideEffects"]["networkToolCall"] is False
    assert body["sideEffects"]["auditWrite"] is False


def test_secret_rotation_contract_recommends_high_risk_rotation_without_secret_io():
    contract = cognix_integration_manager.build_secret_rotation_contract(
        tool_id = "github",
        username = "alice",
        rotation_reason = "admin_requested",
        current_secret_age_days = 120,
        has_developer_mode = True,
        granted_permissions = {"github:read"},
    )

    assert contract["secretRotationContractVersion"] == "cognix_secret_rotation_contract_v1"
    assert contract["mode"] == "secret_rotation_contract_dry_run"
    assert contract["toolId"] == "github"
    assert contract["connector"] == "github"
    assert contract["rotationRecommended"] is True
    assert contract["readyForRotationRequest"] is True
    assert contract["readyForSecretRotation"] is False
    assert contract["rotationPolicy"]["requiresServerSideSecretManager"] is True
    assert contract["rotationPolicy"]["ageExceeded"] is True
    assert contract["executorContract"]["plannedExecutor"] == "cognix_secret_manager:rotate_connector_secret"
    assert contract["executorContract"]["secretReadAllowedHere"] is False
    assert contract["executorContract"]["secretWriteAllowedHere"] is False
    assert contract["secretSources"][0]["currentValueIncluded"] is False
    assert contract["secretSources"][0]["newValueIncluded"] is False
    assert contract["sideEffects"]["secretRead"] is False
    assert contract["sideEffects"]["secretWrite"] is False
    assert contract["sideEffects"]["secretRotation"] is False
    assert "secret_rotation" in contract["blockedActions"]


def test_secret_rotation_contract_blocks_unknown_integration_without_secret_io():
    contract = cognix_integration_manager.build_secret_rotation_contract(
        tool_id = "unknown-connector",
        username = "alice",
        rotation_reason = "suspected_leak",
    )

    assert contract["status"] == "unknown_integration"
    assert contract["readyForRotationRequest"] is False
    assert contract["readyForSecretRotation"] is False
    assert contract["summary"]["secretSourceCount"] == 0
    assert "connector_preflight_ready" in contract["summary"]["blockedGateIds"]
    assert "secret_sources_declared" in contract["summary"]["blockedGateIds"]
    assert contract["executorContract"]["plannedExecutor"] is None
    assert contract["sideEffects"]["secretRead"] is False
    assert contract["sideEffects"]["secretWrite"] is False


def test_secret_rotation_contract_endpoint_logs_sanitized_contract():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "github:read",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    body = run_async(
        cognix_routes.integration_secret_rotation_contract(
            cognix_routes.IntegrationSecretRotationContractRequest(
                toolId = "github",
                rotationReason = "admin_requested",
                currentSecretAgeDays = 120,
            ),
            current_subject = "alice",
        )
    )

    contract = body["secretRotationContract"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_secret_rotation_contract_v1"
    assert contract["rotationRecommended"] is True
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["secretWrite"] is False
    assert body["sideEffects"]["secretRotation"] is False

    log = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "integration_secret_rotation_contract_built"
    assert log["metadata"]["secretRotationContractVersion"] == "cognix_secret_rotation_contract_v1"
    assert log["metadata"]["secretSourceCount"] == contract["summary"]["secretSourceCount"]
    assert log["metadata"]["sideEffects"]["secretRead"] is False
    assert "secretSources" not in log["metadataJson"]
    assert "currentValue" not in log["metadataJson"]


def test_enterprise_tool_action_plan_blocks_critical_exports_without_execution():
    plan = cognix_tool_registry.plan_tool_action(
        tool_id = "crm",
        action_id = "export_customer_data",
        username = "alice",
        has_developer_mode = True,
        granted_permissions = {"crm:read", "crm:export"},
    )

    assert plan["allowed"] is False
    assert plan["status"] == "connector_disabled"
    assert plan["riskLevel"] == "critical"
    assert plan["guardrails"]["adminRequired"] is True
    assert plan["guardrails"]["sandboxRequired"] is True
    assert "admin" in plan["missingPermissions"]
    assert plan["secretPolicy"]["allowedSecretSources"] == [
        "connector_oauth_token",
        "encrypted_user_token",
        "crm_api_token",
    ]
    assert plan["executionContract"]["allowedToPrepare"] is False
    assert plan["executionContract"]["readyForExecution"] is False
    assert "connector_disabled" in plan["executionContract"]["blockedWhen"]
    assert "sandbox_required" in plan["executionContract"]["blockedWhen"]
    assert plan["executionContract"]["dataBoundary"]["clientSecretTransmitAllowed"] is False
    assert plan["executionBoundaryContract"]["manifest"]["riskLevel"] == "critical"
    assert plan["executionBoundaryContract"]["rbac"]["adminRequired"] is True
    assert plan["executionBoundaryContract"]["requestBoundary"]["toolExecutionAllowedHere"] is False
    assert plan["executionBoundaryContract"]["auditBoundary"]["auditLogRawPayloadAllowed"] is False
    assert plan["sideEffects"]["toolExecution"] is False
    assert plan["sideEffects"]["externalWrite"] is False
    assert plan["sideEffects"]["secretRead"] is False


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
    assert body["activationContractVersion"] == "cognix_integration_activation_contract_v1"
    assert body["activationContract"]["contractVersion"] == "cognix_integration_activation_contract_v1"
    assert body["activationContract"]["readyForActivation"] is False
    assert body["activationContract"]["automaticActivationAllowed"] is False
    assert body["activationContract"]["frontendDirectActivationAllowed"] is False
    assert body["activationContract"]["preconditions"]["serverSecretConfigured"] is False
    assert "connector_disabled" in body["activationContract"]["blockedWhen"]
    assert "server_secret_required" in body["activationContract"]["blockedWhen"]
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["networkToolCall"] is False
    assert any(item["id"] == "enable_connector" for item in body["nextActions"])

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "integration_plan_built"
    assert log["resourceType"] == "cognix_integration"
    assert log["metadata"]["integrationManagerVersion"] == "cognix_integration_manager_v1"
    assert log["metadata"]["activationContractVersion"] == "cognix_integration_activation_contract_v1"
    assert log["metadata"]["activationContract"]["readyForActivation"] is False
    assert log["metadata"]["sideEffects"]["secretRead"] is False
    assert "access_token" not in log["metadataJson"].lower()
    assert "secret_value" not in log["metadataJson"].lower()


def test_integration_activation_contract_endpoint_blocks_activation_without_secret_read():
    seed_accounts()

    body = run_async(
        cognix_routes.integration_activation_contract(
            cognix_routes.IntegrationActivationContractRequest(tool_id = "github"),
            current_subject = "alice",
        )
    )

    contract = body["activationContract"]
    assert body["auditLogId"].startswith("aud_")
    assert contract["contractVersion"] == "cognix_integration_activation_contract_v1"
    assert contract["allowedToPrepareActivation"] is True
    assert contract["readyForActivation"] is False
    assert contract["preconditions"]["manifestPresent"] is True
    assert contract["preconditions"]["serverSecretConfigured"] is False
    assert contract["dataBoundary"]["secretsStayServerSide"] is True
    assert contract["dataBoundary"]["rawSecretLoggingAllowed"] is False
    assert "secret_read" in contract["blockedActions"]
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["integrationActivation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "integration_activation_contract_built"
    assert log["metadata"]["activationContractVersion"] == "cognix_integration_activation_contract_v1"
    assert log["metadata"]["readyForActivation"] is False
    assert "server_secret_required" in log["metadata"]["blockedWhen"]
    assert "secret_value" not in log["metadataJson"].lower()


def test_connector_preflight_contract_summarizes_provider_without_secret_or_network_access():
    contract = cognix_integration_manager.build_connector_preflight_contract(
        tool_id = "github",
        username = "alice",
        is_admin = False,
        has_developer_mode = True,
        granted_permissions = {"github:read"},
    )

    assert contract["contractVersion"] == "cognix_connector_preflight_contract_v1"
    assert contract["mode"] == "connector_preflight_dry_run"
    assert contract["toolId"] == "github"
    assert contract["connector"] == "github"
    assert contract["status"] == "ready_for_admin_review"
    assert contract["readyForActivationRequest"] is True
    assert contract["readyForConnectorActivation"] is False
    assert contract["authProfile"]["authMode"] == "oauth_user_token"
    assert contract["authProfile"]["actualSecretValuesIncluded"] is False
    assert contract["secretContract"]["secretSourceNames"] == [
        "connector_oauth_token",
        "encrypted_user_token",
    ]
    assert contract["secretContract"]["actualSecretValuesIncluded"] is False
    assert "github:write" in contract["permissionContract"]["missingPermissions"]
    assert "admin" in contract["permissionContract"]["missingPermissions"]
    assert contract["riskContract"]["maxRiskLevel"] == "critical"
    assert "merge_pull_request" in contract["riskContract"]["criticalActionIds"]
    assert contract["dataBoundary"]["networkCallPlanned"] is False
    assert contract["sideEffects"]["secretRead"] is False
    assert contract["sideEffects"]["networkToolCall"] is False
    assert contract["sideEffects"]["integrationActivation"] is False


def test_connector_preflight_unknown_integration_blocks_everything_without_execution():
    contract = cognix_integration_manager.build_connector_preflight_contract(
        tool_id = "unknown-connector",
        username = "alice",
    )

    assert contract["contractVersion"] == "cognix_connector_preflight_contract_v1"
    assert contract["status"] == "unknown_integration"
    assert contract["readyForActivationRequest"] is False
    assert contract["nextRequiredGate"] == "manifest_missing"
    assert "network_tool_call" in contract["blockedActions"]
    assert contract["sideEffects"]["secretRead"] is False
    assert contract["sideEffects"]["toolExecution"] is False


def test_integration_preflight_endpoint_logs_sanitized_contract():
    seed_accounts()

    body = run_async(
        cognix_routes.integration_preflight_contract(
            cognix_routes.IntegrationPreflightContractRequest(tool_id = "github"),
            current_subject = "alice",
        )
    )

    contract = body["preflightContract"]
    assert body["auditLogId"].startswith("aud_")
    assert contract["contractVersion"] == "cognix_connector_preflight_contract_v1"
    assert contract["readyForConnectorActivation"] is False
    assert contract["secretContract"]["actualSecretValuesIncluded"] is False
    assert contract["sideEffects"]["secretRead"] is False
    assert contract["sideEffects"]["networkToolCall"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "integration_preflight_contract_built"
    assert log["metadata"]["preflightContractVersion"] == "cognix_connector_preflight_contract_v1"
    assert log["metadata"]["secretContract"]["actualSecretValuesIncluded"] is False
    assert log["metadata"]["sideEffects"]["secretRead"] is False
    assert "secret_value" not in log["metadataJson"].lower()
    assert "access_token" not in log["metadataJson"].lower()


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


def test_tool_execution_handoff_endpoint_logs_sanitized_packet_without_job_enqueue():
    seed_accounts()

    body = run_async(
        cognix_routes.tool_execution_handoff(
            cognix_routes.ToolExecutionHandoffRequest(
                tool_id = "codex-secure-agent",
                action_id = "plan_feature",
                request_id = "req_safe_plan",
            ),
            current_subject = "alice",
        )
    )

    handoff = body["executionHandoff"]
    assert body["auditLogId"].startswith("aud_")
    assert body["plannerVersion"] == "cognix_tool_execution_handoff_v1"
    assert body["toolPlan"]["executionContract"]["preconditions"]["rateLimitChecked"] is True
    assert body["toolPlan"]["executionBoundaryContract"]["rateLimitBoundary"]["rateLimitChecked"] is True
    assert handoff["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert handoff["executionBoundary"]["jobEnqueueAllowedHere"] is False
    assert handoff["status"] == "ready_for_executor_review"
    assert handoff["readyForExecutorReview"] is True
    assert handoff["readyForJobEnqueue"] is False
    assert handoff["executorInput"]["secretValuesIncluded"] is False
    assert handoff["sideEffects"]["jobEnqueue"] is False
    assert body["sideEffects"]["auditWrite"] is True
    assert body["sideEffects"]["toolExecution"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "tool_execution_handoff_built"
    assert log["resourceType"] == "cognix_tool_execution_handoff"
    assert log["metadata"]["handoffVersion"] == "cognix_tool_execution_handoff_v1"
    assert log["metadata"]["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert log["metadata"]["executionBoundary"]["jobEnqueueAllowedHere"] is False
    assert log["metadata"]["executionBoundary"]["rawPayloadAuditAllowed"] is False
    assert log["metadata"]["readyForJobEnqueue"] is False
    assert log["metadata"]["secretValuesIncluded"] is False
    assert log["metadata"]["rawPayloadIncluded"] is False
    assert log["metadata"]["sideEffects"]["jobEnqueue"] is False
    assert "access_token" not in log["metadataJson"].lower()
    assert "secret_value" not in log["metadataJson"].lower()


def test_tool_calculator_endpoint_evaluates_and_logs_sanitized_expression():
    seed_accounts()

    body = run_async(
        cognix_routes.tool_calculator_evaluate(
            cognix_routes.ToolCalculatorEvaluateRequest(
                expression = "sqrt(144) + 3 * 7",
                precision = 12,
            ),
            current_subject = "alice",
        )
    )

    result = body["calculatorResult"]
    assert body["auditLogId"].startswith("aud_")
    assert body["status"] == "evaluated"
    assert body["plannerVersion"] == "cognix_native_calculator_v1"
    assert result["resultText"] == "33"
    assert body["toolPlan"]["toolId"] == "calculator"
    assert body["toolPlan"]["rateLimit"]["allowed"] is True
    assert body["sideEffects"]["calculatorEvaluation"] is True
    assert body["sideEffects"]["networkToolCall"] is False
    assert body["sideEffects"]["generation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "tool_calculator_evaluated"
    assert log["resourceType"] == "cognix_native_calculator"
    assert log["metadata"]["calculatorVersion"] == "cognix_native_calculator_v1"
    assert log["metadata"]["status"] == "evaluated"
    assert log["metadata"]["expressionLength"] == len("sqrt(144) + 3 * 7")
    assert log["metadata"]["sideEffects"]["calculatorEvaluation"] is True
    assert "sqrt(144)" not in log["metadataJson"]


def test_tool_physics_solver_endpoint_solves_and_logs_sanitized_values():
    seed_accounts()

    body = run_async(
        cognix_routes.tool_physics_solve(
            cognix_routes.ToolPhysicsSolveRequest(
                formula_id = "ohm_law",
                variables = {"current": 2, "resistance": 5},
                precision = 12,
            ),
            current_subject = "alice",
        )
    )

    result = body["physicsResult"]
    assert body["auditLogId"].startswith("aud_")
    assert body["status"] == "solved"
    assert body["plannerVersion"] == "cognix_native_physics_solver_v1"
    assert result["formulaId"] == "ohm_law"
    assert result["targetVariable"] == "voltage"
    assert result["resultText"] == "10"
    assert body["toolPlan"]["toolId"] == "physics-solver"
    assert body["toolPlan"]["rateLimit"]["allowed"] is True
    assert body["sideEffects"]["physicsSolve"] is True
    assert body["sideEffects"]["networkToolCall"] is False
    assert body["sideEffects"]["generation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "tool_physics_solver_solved"
    assert log["resourceType"] == "cognix_native_physics_solver"
    assert log["metadata"]["physicsSolverVersion"] == "cognix_native_physics_solver_v1"
    assert log["metadata"]["formulaId"] == "ohm_law"
    assert log["metadata"]["targetVariable"] == "voltage"
    assert log["metadata"]["providedVariableIds"] == ["current", "resistance"]
    assert "variables" not in log["metadata"]
    assert log["metadata"]["sideEffects"]["physicsSolve"] is True
    assert "current" in log["metadataJson"]
    assert '"variables"' not in log["metadataJson"]


def test_tool_latex_renderer_endpoint_returns_sanitized_render_packet():
    seed_accounts()

    body = run_async(
        cognix_routes.tool_latex_render(
            cognix_routes.ToolLatexRenderRequest(
                source = r"\frac{F}{m}=a",
                display_mode = True,
                context = "physics",
            ),
            current_subject = "alice",
        )
    )

    result = body["latexResult"]
    assert body["auditLogId"].startswith("aud_")
    assert body["status"] == "render_packet_ready"
    assert body["plannerVersion"] == "cognix_native_latex_renderer_v1"
    assert result["renderTarget"] == "streamdown_katex"
    assert result["markdown"].startswith("$$")
    assert body["toolPlan"]["toolId"] == "latex-renderer"
    assert body["toolPlan"]["rateLimit"]["allowed"] is True
    assert body["sideEffects"]["latexRenderPacket"] is True
    assert body["sideEffects"]["fileRead"] is False
    assert body["sideEffects"]["networkToolCall"] is False
    assert body["sideEffects"]["generation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "tool_latex_rendered"
    assert log["resourceType"] == "cognix_native_latex_renderer"
    assert log["metadata"]["latexRendererVersion"] == "cognix_native_latex_renderer_v1"
    assert log["metadata"]["sourceHash"] == result["sourceHash"]
    assert log["metadata"]["commandCount"] == result["commandCount"]
    assert log["metadata"]["sideEffects"]["latexRenderPacket"] is True
    assert "source" not in log["metadata"]
    assert r"\frac{F}{m}=a" not in log["metadataJson"]


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
    assert first["executionContract"]["preconditions"]["rateLimitChecked"] is True
    assert first["executionContract"]["preconditions"]["rateLimitAllowed"] is True
    assert first["executionBoundaryContract"]["rateLimitBoundary"]["rateLimitChecked"] is True
    assert first["executionBoundaryContract"]["rateLimitBoundary"]["rateLimitAllowed"] is True
    assert first["executionContract"]["readyForExecution"] is False
    assert second["allowed"] is False
    assert second["status"] == "rate_limited"
    assert second["rateLimit"]["allowed"] is False
    assert second["executionContract"]["nextRequiredGate"] == "rate_limited"
    assert "rate_limited" in second["executionContract"]["blockedWhen"]
    assert second["executionContract"]["allowedToPrepare"] is False
    assert second["executionBoundaryContract"]["status"] == "blocked_rate_limited"
    assert "rate_limited" in second["executionBoundaryContract"]["blockedWhen"]
    assert second["executionBoundaryContract"]["executorBoundary"]["executorRequired"] is False
    assert second["executionBoundaryContract"]["executorBoundary"]["plannedExecutorQueue"] is None
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
    assert body["executionContract"]["allowedToPrepare"] is False
    assert body["executionContract"]["readyForExecution"] is False
    assert body["executionContract"]["preconditions"]["connectorEnabled"] is False
    assert "connector_disabled" in body["executionContract"]["blockedWhen"]
    assert body["sideEffects"]["externalWrite"] is False
    assert "developer_mode" in body["missingPermissions"]


def test_tool_plan_uses_database_permissions_for_connector_actions():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "github:read",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )

    body = run_async(
        cognix_routes.plan_tool_action(
            cognix_routes.ToolActionPlanRequest(
                tool_id = "github",
                action_id = "read_repository",
            ),
            current_subject = "alice",
        )
    )

    assert body["allowed"] is False
    assert body["status"] == "connector_disabled"
    assert body["missingPermissions"] == []
    assert "github:read" in body["permissionContext"]["explicitPermissions"]
    assert body["guardrails"]["auditRequired"] is True
    assert body["guardrails"]["frontendDirectExecutionAllowed"] is False
    assert body["guardrails"]["secretPolicyRequired"] is True
    assert body["secretPolicy"]["policyVersion"] == "cognix_tool_secret_policy_v1"
    assert body["secretPolicy"]["requiresSecret"] is True
    assert body["secretPolicy"]["secretReadAllowedHere"] is False
    assert body["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert body["executionContract"]["contractVersion"] == "cognix_tool_execution_contract_v1"
    assert body["executionBoundaryContract"]["contractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert body["executionBoundaryContract"]["requestBoundary"]["toolExecutionAllowedHere"] is False
    assert body["executionBoundaryContract"]["secretBoundary"]["secretReadAllowedHere"] is False
    assert body["executionContract"]["preconditions"]["secretsRequired"] is True
    assert body["executionContract"]["preconditions"]["secretPolicyVersion"] == "cognix_tool_secret_policy_v1"
    assert body["executionContract"]["dataBoundary"]["secretsStayServerSide"] is True
    assert body["executionContract"]["dataBoundary"]["clientSecretTransmitAllowed"] is False
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["toolExecution"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["action"] == "tool_action_planned"
    assert log["metadata"]["missingPermissions"] == []
    assert log["metadata"]["executionContractVersion"] == "cognix_tool_execution_contract_v1"
    assert log["metadata"]["executionBoundaryContractVersion"] == "cognix_tool_execution_boundary_contract_v1"
    assert log["metadata"]["executionBoundary"]["toolExecutionAllowedHere"] is False
    assert log["metadata"]["executionBoundary"]["rawPayloadAuditAllowed"] is False
    assert log["metadata"]["secretPolicyVersion"] == "cognix_tool_secret_policy_v1"
    assert log["metadata"]["secretPolicy"]["rawSecretExposureAllowed"] is False
    assert log["metadata"]["contract"]["readyForExecution"] is False
    assert "connector_disabled" in log["metadata"]["contract"]["blockedWhen"]
    assert log["metadata"]["guardrails"]["frontendDirectExecutionAllowed"] is False


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


def test_admin_approvals_core_builds_queue_policy_and_blueprint():
    blueprint = cognix_admin_approvals.build_approvals_blueprint()
    assert blueprint["services"] == ["ApprovalService", "ApprovalQueue", "ApprovalPolicyEngine"]
    assert "cognix_approval_decisions" in blueprint["tables"]
    assert blueprint["sideEffects"]["toolExecution"] is False

    policy = cognix_admin_approvals.build_policy_decision(
        request_type = "codex:run",
        requester_role = "user",
        risk_level = "critical",
        has_permission = False,
    )
    assert policy["requiresApproval"] is True
    assert policy["recommendedQueue"] == "admin"

    admin_policy = cognix_admin_approvals.build_policy_decision(
        request_type = "codex:run",
        requester_role = "admin",
        risk_level = "critical",
        has_permission = True,
    )
    assert admin_policy["requiresApproval"] is False
    assert admin_policy["recommendedAction"] == "execute_with_audit"

    queue = cognix_admin_approvals.build_approval_queue(
        requests = [
            {
                "id": "apr_low",
                "username": "alice",
                "request_type": "apps:connect",
                "reason": "connect app",
                "risk_level": "medium",
                "status": "pending",
                "created_at": "2026-06-29T00:00:00+00:00",
            },
            {
                "id": "apr_high",
                "username": "bob",
                "request_type": "codex:run",
                "reason": "run codex",
                "risk_level": "critical",
                "status": "pending",
                "created_at": "2026-06-29T00:01:00+00:00",
            },
        ],
        decisions = [{"request_id": "apr_low", "status": "approved", "decided_by": "admin"}],
        comments = [{"request_id": "apr_high", "comment": "Needs review", "username": "admin"}],
    )
    assert queue["summary"]["pending"] == 2
    assert queue["summary"]["critical"] == 1
    assert queue["requests"][0]["id"] == "apr_high"
    assert queue["requests"][0]["commentCount"] == 1


def test_admin_approvals_schema_migrates_legacy_request_table():
    db_path = studio_db_path()
    db_path.parent.mkdir(parents = True, exist_ok = True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE cognix_approval_requests (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                request_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    cognix_db._schema_ready = False
    conn = cognix_db.get_connection()
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(cognix_approval_requests)")}
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(cognix_approval_requests)")}
    finally:
        conn.close()

    assert {"title", "risk_level", "resource_type", "resource_id", "metadata_json"}.issubset(columns)
    assert "idx_cognix_approval_risk" in indexes


def test_admin_approvals_routes_manage_queue_comments_decisions_and_developer_sync():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_approvals(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(
        cognix_routes.admin_approvals_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    assert blueprint["approvalsBlueprint"]["approvalQueueVersion"] == "cognix_approval_queue_v1"

    created = run_async(
        cognix_routes.create_approval_request(
            cognix_routes.ApprovalCreateRequest(
                requestType = "codex:run",
                reason = "Need Codex for a protected repo change",
                riskLevel = "critical",
                resourceType = "tool",
                resourceId = "codex",
            ),
            current_subject = "alice",
        )
    )
    request_id = created["request"]["id"]
    assert created["request"]["requestType"] == "codex:run"
    assert created["request"]["riskLevel"] == "critical"
    assert created["policy"]["requiresApproval"] is True

    admin_queue = run_async(cognix_routes.admin_approvals(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert admin_queue["approvalQueue"]["summary"]["pending"] == 1
    assert admin_queue["approvalQueue"]["requests"][0]["id"] == request_id
    assert admin_queue["sideEffects"]["decisionWrite"] is False

    comment = run_async(
        cognix_routes.admin_add_approval_comment(
            request_id,
            cognix_routes.ApprovalCommentRequest(comment = "Reviewing scope", visibility = "admin"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert comment["comment"]["requestId"] == request_id
    assert comment["sideEffects"]["commentWrite"] is True

    denied = run_async(
        cognix_routes.admin_decide_approval(
            request_id,
            cognix_routes.ApprovalDecisionRequest(status = "denied", admin_note = "Too risky"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert denied["request"]["status"] == "denied"
    assert denied["decisions"][0]["status"] == "denied"
    assert denied["sideEffects"]["decisionWrite"] is True

    detail = run_async(
        cognix_routes.admin_approval_detail(request_id, current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    assert detail["comments"][0]["comment"] == "Reviewing scope"
    assert detail["approvalQueueItem"]["status"] == "denied"

    dev_request = run_async(
        cognix_routes.request_developer_mode(
            cognix_routes.ApprovalCreateRequest(reason = "Need developer mode"),
            current_subject = "alice",
        )
    )
    dev_request_id = dev_request["request"]["id"]
    approved = run_async(
        cognix_routes.admin_decide_approval(
            dev_request_id,
            cognix_routes.ApprovalDecisionRequest(status = "approved", admin_note = "Approved"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert approved["request"]["status"] == "approved"
    assert cognix_db.user_has_permission("alice", cognix_db.DEVELOPER_MODE_PERMISSION) is True
    overrides = cognix_db.list_user_permission_overrides("alice")
    assert any(
        item["permission_key"] == cognix_db.DEVELOPER_MODE_PERMISSION and item["effect"] == "allow"
        for item in overrides
    )

    actions = [log["action"] for log in cognix_db.list_audit_logs(limit = 20)]
    assert "approval_requested" in actions
    assert "approval_comment_added" in actions
    assert "approval_decided" in actions


def test_admin_users_service_aggregates_permissions_limits_activity_and_usage():
    seed_accounts()
    cognix_db.grant_user_permission(
        "alice",
        "codex:run",
        granted_by = storage.DEFAULT_ADMIN_USERNAME,
    )
    cognix_db.upsert_user_limit(
        "alice",
        limit_key = "tokens_daily",
        limit_value = 42000,
        unit = "tokens",
        updated_by = storage.DEFAULT_ADMIN_USERNAME,
    )
    cognix_db.create_user_activity_event(
        "alice",
        event_type = "message_sent",
        resource_type = "chat",
        resource_id = "thread-1",
    )
    cognix_db.create_token_usage_event(
        "alice",
        model_id = "qwen-local",
        provider = "ollama",
        input_tokens = 120,
        output_tokens = 80,
        estimated_cost_usd = 0,
    )
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = "alice",
        action = "chat_message_created",
        resource_type = "chat",
        severity = "notice",
    )

    directory = cognix_admin_users.build_admin_user_directory(
        users = storage.list_user_profiles(),
        permissions = cognix_db.list_user_permissions("alice"),
        limits = cognix_db.list_user_limits(),
        audit_logs = cognix_db.list_audit_logs(limit = 50),
        activity_events = cognix_db.list_user_activity_events(limit = 50),
        token_events = cognix_db.list_token_usage_events(limit = 50),
        projects = [],
        threads = [],
        bans = [],
        reports = [],
    )
    alice = next(item for item in directory["users"] if item["username"] == "alice")

    assert directory["adminUserServiceVersion"] == "cognix_admin_user_service_v1"
    assert alice["permissions"]["permissionKeys"] == ["codex:run"]
    assert alice["permissions"]["sensitivePermissionCount"] == 1
    assert alice["limits"]["tokens_daily"]["value"] == 42000
    assert alice["limits"]["tokens_daily"]["overridden"] is True
    assert alice["usage"]["totalTokens"] == 200
    assert alice["usage"]["topModels"] == [{"modelId": "qwen-local", "count": 1}]
    assert alice["activity"]["auditEvents"] == 1
    assert alice["activity"]["activityEvents"] == 1
    assert directory["sideEffects"]["permissionGrant"] is False
    assert directory["sideEffects"]["generation"] is False


def test_admin_activity_rollups_combine_events_usage_chats_and_audits():
    users = [{"username": "alice"}, {"username": "kamil"}]
    thread = {
        "id": "thread-activity-core",
        "title": "Activity",
        "modelType": "ollama",
        "modelId": "qwen-local",
        "projectId": "project-1",
        "ownerUsername": "alice",
        "createdAt": 1782700000000,
    }
    messages = [
        {
            "id": "msg-activity-1",
            "threadId": "thread-activity-core",
            "role": "user",
            "content": [{"type": "text", "text": "hello"}],
            "createdAt": 1782700001000,
        },
        {
            "id": "msg-activity-2",
            "threadId": "thread-activity-core",
            "role": "assistant",
            "content": [{"type": "text", "text": "hi"}],
            "createdAt": 1782700002000,
        },
    ]
    rollups = cognix_admin_activity.build_activity_rollups(
        users = users,
        activity_events = [
            {
                "username": "alice",
                "event_type": "tool_error",
                "resource_type": "tool",
                "created_at": "2026-06-29T10:00:00+00:00",
            }
        ],
        token_events = [
            {
                "username": "alice",
                "model_id": "qwen-local",
                "total_tokens": 42,
                "created_at": "2026-06-29T10:01:00+00:00",
            }
        ],
        threads = [thread],
        messages = messages,
        audit_logs = [
            {
                "username": "alice",
                "actor_username": "kamil",
                "action": "permission_granted",
                "severity": "warning",
                "created_at": "2026-06-29T10:02:00+00:00",
            }
        ],
        conversation_metadata = [
            {
                "username": "alice",
                "thread_id": "thread-activity-core",
                "project_id": "project-1",
                "model_id": "qwen-local",
                "tool_call_count": 2,
                "document_access_count": 3,
                "updated_at": "2026-06-29T10:03:00+00:00",
            }
        ],
    )
    alice = next(item for item in rollups["userDaily"] if item["username"] == "alice")

    assert rollups["activityMonitoringVersion"] == "cognix_activity_monitoring_v2"
    assert alice["messageCount"] == 2
    assert alice["tokenTotal"] == 42
    assert alice["toolCallCount"] == 2
    assert alice["documentAccessCount"] == 3
    assert alice["activeProjectCount"] == 1
    assert alice["errorCount"] >= 2
    assert alice["sensitiveActionCount"] >= 1
    assert alice["activityScore"] > 0
    assert rollups["organizationDaily"][0]["activeUserCount"] == 1
    assert rollups["sideEffects"]["modelLoad"] is False
    assert rollups["sideEffects"]["toolExecution"] is False


def test_admin_activity_monitoring_routes_are_admin_only_and_persist_rollups():
    seed_accounts()
    now = int(time.time())
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-activity-1",
            "title": "Activity route",
            "modelType": "ollama",
            "modelId": "qwen-local",
            "createdAt": now,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_message(
        {
            "id": "msg-activity-route-1",
            "threadId": "thread-activity-1",
            "role": "user",
            "content": [{"type": "text", "text": "route activity"}],
            "metadata": {"toolCalls": [{"name": "library_search"}], "documents": ["doc-1"]},
            "createdAt": now + 1,
        }
    )
    cognix_db.create_user_activity_event(
        "alice",
        event_type = "document_consulted",
        resource_type = "library",
        resource_id = "doc-1",
    )
    cognix_db.create_token_usage_event(
        "alice",
        model_id = "qwen-local",
        provider = "ollama",
        input_tokens = 30,
        output_tokens = 12,
    )
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = storage.DEFAULT_ADMIN_USERNAME,
        action = "permission_granted",
        resource_type = "permission",
        severity = "warning",
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_activity_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_activity_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert blueprint["activityMonitoringBlueprint"]["tables"] == [
        "cognix_user_activity_events",
        "cognix_user_activity_daily",
        "cognix_organization_activity_daily",
    ]

    aggregate = run_async(cognix_routes.admin_activity_aggregate(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert aggregate["activityDashboard"]["summary"]["messageCount"] >= 1
    assert aggregate["activityDashboard"]["summary"]["tokenTotal"] == 42
    assert aggregate["userDaily"]
    assert aggregate["organizationDaily"]
    assert aggregate["sideEffects"]["userDailyWrite"] is True
    assert aggregate["sideEffects"]["organizationDailyWrite"] is True
    assert cognix_db.list_user_activity_daily("alice")
    assert cognix_db.list_organization_activity_daily()

    activity = run_async(cognix_routes.admin_activity(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert activity["activityDashboard"]["summary"]["messageCount"] >= 1
    assert activity["userDaily"]
    assert activity["organizationDaily"]
    assert activity["plannerVersion"] == "cognix_activity_monitoring_v2"

    actions = [log["action"] for log in cognix_db.list_audit_logs(limit = 20)]
    assert "admin_activity_aggregated" in actions


def test_admin_limits_core_builds_effective_quota_matrix_and_enforcement():
    users = [{"username": "alice", "role": "user"}]
    matrix = cognix_admin_limits.build_quota_matrix(
        users = users,
        user_quotas = [
            {
                "username": "alice",
                "quota_key": "tokens_daily",
                "quota_value": 80,
                "unit": "tokens",
                "period": "day",
                "status": "active",
            }
        ],
        role_quotas = [
            {
                "role_key": "user",
                "quota_key": "tokens_daily",
                "quota_value": 100,
                "unit": "tokens",
                "period": "day",
                "status": "active",
            }
        ],
        quota_overrides = [],
        quota_usage = [
            {
                "username": "alice",
                "quota_key": "tokens_daily",
                "used_value": 70,
            }
        ],
        legacy_limits = [],
    )
    quota = matrix["users"][0]["quotas"]["tokens_daily"]
    blocked = cognix_admin_limits.build_usage_enforcement_plan(
        username = "alice",
        quota_key = "tokens_daily",
        requested_units = 15,
        quota_matrix = matrix,
    )

    assert matrix["limitServiceVersion"] == "cognix_limit_service_v2"
    assert quota["source"] == "user_quota"
    assert quota["quotaValue"] == 80
    assert quota["usedValue"] == 70
    assert blocked["allowed"] is False
    assert blocked["status"] == "quota_exceeded"
    assert blocked["sideEffects"]["modelLoad"] is False
    assert blocked["sideEffects"]["toolExecution"] is False

    override_matrix = cognix_admin_limits.build_quota_matrix(
        users = users,
        user_quotas = [],
        role_quotas = [],
        quota_overrides = [
            {
                "target_type": "user",
                "target_id": "alice",
                "quota_key": "tokens_daily",
                "quota_value": 120,
                "unit": "tokens",
                "period": "day",
                "status": "active",
            }
        ],
        quota_usage = [{"username": "alice", "quota_key": "tokens_daily", "used_value": 70}],
        legacy_limits = [],
    )
    allowed = cognix_admin_limits.build_usage_enforcement_plan(
        username = "alice",
        quota_key = "tokens_daily",
        requested_units = 15,
        quota_matrix = override_matrix,
    )
    assert override_matrix["users"][0]["quotas"]["tokens_daily"]["source"] == "user_override"
    assert allowed["allowed"] is True


def test_admin_permissions_core_builds_rbac_overrides_project_scopes_and_ceo_cloud_training():
    matrix = cognix_admin_permissions.build_permission_matrix(
        users = [
            {"username": "alice", "role": "user", "plan": "free"},
            {"username": "ceo_user", "role": "user", "plan": "CEO"},
        ],
        roles = [],
        permissions = [],
        role_permissions = [
            {
                "role_key": "user",
                "permission_key": "tools:execute",
                "allowed": 1,
                "updated_by": "admin",
            }
        ],
        user_overrides = [
            {
                "username": "alice",
                "permission_key": "tools:execute",
                "effect": "deny",
                "reason": "pause tools",
            }
        ],
        project_permissions = [
            {
                "project_id": "proj_1",
                "subject_type": "user",
                "subject_id": "alice",
                "permission_key": "projects:collaborate",
                "allowed": 1,
                "updated_by": "admin",
            }
        ],
        legacy_user_permissions = [
            {
                "username": "alice",
                "permission_key": "github:read",
                "granted_by": "admin",
            }
        ],
        organization_policy = [],
    )

    alice_tools = cognix_admin_permissions.build_permission_decision(
        username = "alice",
        permission_key = "tools:execute",
        matrix = matrix,
    )
    assert alice_tools["allowed"] is False
    assert alice_tools["source"] == "user_override"
    assert alice_tools["sideEffects"]["networkCall"] is False

    alice_github = cognix_admin_permissions.build_permission_decision(
        username = "alice",
        permission_key = "github:read",
        matrix = matrix,
    )
    assert alice_github["allowed"] is True
    assert alice_github["source"] == "legacy_user_permission"

    alice_project = cognix_admin_permissions.build_permission_decision(
        username = "alice",
        permission_key = "projects:collaborate",
        project_id = "proj_1",
        matrix = matrix,
    )
    assert alice_project["allowed"] is True
    assert alice_project["source"] == "project_permission"

    ceo_training = cognix_admin_permissions.build_permission_decision(
        username = "ceo_user",
        permission_key = "tools:cloud_training",
        matrix = matrix,
    )
    assert ceo_training["allowed"] is True
    assert ceo_training["source"] == "builtin_ceo_cloud_training"


def test_admin_permissions_routes_manage_roles_overrides_project_permissions_and_legacy_sync():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_permissions_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(
        cognix_routes.admin_permissions_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    assert blueprint["permissionsBlueprint"]["services"] == [
        "PermissionEngine",
        "RoleManager",
        "PermissionOverrideService",
    ]
    assert "cognix_user_permission_overrides" in blueprint["permissionsBlueprint"]["tables"]

    role = run_async(
        cognix_routes.admin_upsert_role(
            "user",
            cognix_routes.AdminRoleRequest(displayName = "User", description = "Base users"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert role["role"]["roleKey"] == "user"
    assert role["sideEffects"]["roleWrite"] is True

    role_permission = run_async(
        cognix_routes.admin_upsert_role_permission(
            "user",
            "tools:execute",
            cognix_routes.AdminRolePermissionRequest(allowed = True, reason = "tools enabled"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert role_permission["rolePermission"]["permissionKey"] == "tools:execute"
    assert role_permission["rolePermission"]["allowed"] == 1

    allowed = run_async(
        cognix_routes.admin_permission_decision(
            cognix_routes.AdminPermissionDecisionRequest(
                username = "alice",
                permissionKey = "tools:execute",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert allowed["decision"]["allowed"] is True
    assert allowed["decision"]["source"] == "role_permission"

    denied = run_async(
        cognix_routes.admin_upsert_user_permission_override(
            "alice",
            "tools:execute",
            cognix_routes.AdminPermissionOverrideRequest(effect = "deny", reason = "temporary"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert denied["override"]["effect"] == "deny"
    assert denied["sideEffects"]["userOverrideWrite"] is True

    denied_decision = run_async(
        cognix_routes.admin_permission_decision(
            cognix_routes.AdminPermissionDecisionRequest(
                username = "alice",
                permissionKey = "tools:execute",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert denied_decision["decision"]["allowed"] is False
    assert denied_decision["decision"]["source"] == "user_override"

    project_permission = run_async(
        cognix_routes.admin_upsert_project_permission(
            "proj_1",
            cognix_routes.AdminProjectPermissionRequest(
                subjectType = "user",
                subjectId = "alice",
                permissionKey = "projects:collaborate",
                allowed = True,
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert project_permission["projectPermission"]["projectId"] == "proj_1"
    assert project_permission["projectPermission"]["subjectType"] == "user"

    project_decision = run_async(
        cognix_routes.admin_permission_decision(
            cognix_routes.AdminPermissionDecisionRequest(
                username = "alice",
                permissionKey = "projects:collaborate",
                projectId = "proj_1",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert project_decision["decision"]["allowed"] is True
    assert project_decision["decision"]["source"] == "project_permission"

    granted = run_async(
        cognix_routes.admin_grant_permission(
            "alice",
            cognix_routes.AdminPermissionGrantRequest(permission_key = "developer_mode"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert granted["override"]["effect"] == "allow"
    assert granted["sideEffects"]["legacyPermissionWrite"] is True

    grant_decision = run_async(
        cognix_routes.admin_permission_decision(
            cognix_routes.AdminPermissionDecisionRequest(
                username = "alice",
                permissionKey = "developer_mode",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert grant_decision["decision"]["allowed"] is True

    revoked = run_async(
        cognix_routes.admin_revoke_permission(
            "alice",
            "developer_mode",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert revoked["override"]["effect"] == "deny"

    revoke_decision = run_async(
        cognix_routes.admin_permission_decision(
            cognix_routes.AdminPermissionDecisionRequest(
                username = "alice",
                permissionKey = "developer_mode",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert revoke_decision["decision"]["allowed"] is False
    assert revoke_decision["decision"]["source"] == "user_override"


def test_ceo_cloud_training_access_does_not_require_local_amd_or_nvidia_gpu():
    profile = {"username": "ceo_user", "role": "user", "plan": "CEO"}
    assert storage.has_ceo_training_entitlement("ceo_user", profile) is True

    base_kwargs = dict(
        objective = "Fine tune a Qwen model in the cloud",
        classification = {"selectedDomain": "general"},
        task_strategy = {"path": "guided_fine_tuning"},
        recommendation = {"modelId": "qwen-test", "modelLabel": "Qwen test", "providerId": "local"},
        hardware = {
            "gpu": {"available": False, "devices": []},
            "memory": {"totalGb": 8, "availableGb": 4},
        },
        dataset = {
            "format": "sharegpt",
            "sampleCount": 250,
            "estimatedTokens": 75000,
            "duplicateRatio": 0.0,
            "invalidRows": 0,
            "license": "mit",
            "containsSensitiveData": False,
        },
    )
    plan = cognix_fine_tuning_planner.build_fine_tuning_plan(
        **base_kwargs,
        user_plan = "CEO",
    )
    cloud_alias_plan = cognix_fine_tuning_planner.build_fine_tuning_plan(
        **base_kwargs,
        user_plan = "cloud_ceo",
    )

    assert plan["method"]["type"] == "cloud_qlora"
    assert plan["method"]["requiresLocalGpu"] is False
    assert plan["resourceTargetPlan"]["cloudTrainingAllowed"] is True
    assert plan["resourceTargetPlan"]["localGpuBypassAllowed"] is True
    assert plan["resourceTargetPlan"]["recommendedTargetId"] == "google_colab"
    assert {"google_colab", "kaggle", "cloud_gpu"}.issubset(
        {item["id"] for item in plan["resourceTargetPlan"]["availableTargets"]}
    )
    assert cloud_alias_plan["method"]["type"] == "cloud_qlora"
    assert cloud_alias_plan["resourceTargetPlan"]["localGpuBypassAllowed"] is True


def test_admin_limits_routes_manage_user_role_usage_overrides_and_reset():
    seed_accounts()

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_limits_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_limits_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert blueprint["limitsBlueprint"]["services"] == [
        "LimitService",
        "QuotaManager",
        "UsageEnforcer",
    ]
    assert "cognix_user_quotas" in blueprint["limitsBlueprint"]["tables"]

    role_quota = run_async(
        cognix_routes.admin_update_role_quota(
            "user",
            "tokens_daily",
            cognix_routes.AdminQuotaRequest(quotaValue = 100, unit = "tokens", period = "day", reason = "role cap"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert role_quota["quota"]["roleKey"] == "user"
    assert role_quota["sideEffects"]["roleQuotaWrite"] is True

    user_quota = run_async(
        cognix_routes.admin_update_user_quota(
            "alice",
            "tokens_daily",
            cognix_routes.AdminQuotaRequest(quotaValue = 50, unit = "tokens", period = "day", reason = "temporary cap"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert user_quota["quota"]["quotaKey"] == "tokens_daily"
    assert user_quota["quota"]["quotaValue"] == 50
    assert user_quota["legacyLimit"]["limitKey"] == "tokens_daily"
    assert user_quota["sideEffects"]["userQuotaWrite"] is True

    usage = run_async(
        cognix_routes.admin_record_user_quota_usage(
            "alice",
            cognix_routes.AdminQuotaUsageRequest(
                quotaKey = "tokens_daily",
                usedValue = 45,
                unit = "tokens",
                periodKey = "2026-06-29",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert usage["usage"]["usedValue"] == 45
    assert usage["sideEffects"]["quotaUsageWrite"] is True

    blocked = run_async(
        cognix_routes.admin_quota_enforcement_plan(
            cognix_routes.AdminQuotaEnforcementRequest(
                username = "alice",
                quotaKey = "tokens_daily",
                requestedUnits = 10,
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert blocked["enforcementPlan"]["allowed"] is False

    override = run_async(
        cognix_routes.admin_create_quota_override(
            cognix_routes.AdminQuotaOverrideRequest(
                targetType = "user",
                targetId = "alice",
                quotaKey = "tokens_daily",
                quotaValue = 80,
                unit = "tokens",
                period = "day",
                reason = "support exception",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert override["override"]["targetType"] == "user"
    assert override["sideEffects"]["quotaOverrideWrite"] is True

    matrix = run_async(cognix_routes.admin_limits(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    alice = next(item for item in matrix["quotaMatrix"]["users"] if item["username"] == "alice")
    assert alice["quotas"]["tokens_daily"]["source"] == "user_override"

    allowed = run_async(
        cognix_routes.admin_quota_enforcement_plan(
            cognix_routes.AdminQuotaEnforcementRequest(
                username = "alice",
                quotaKey = "tokens_daily",
                requestedUnits = 10,
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert allowed["enforcementPlan"]["allowed"] is True

    legacy = run_async(
        cognix_routes.admin_update_user_limit(
            "alice",
            "messages_daily",
            cognix_routes.AdminUserLimitRequest(limitValue = 25, unit = "messages", period = "day", reason = "legacy sync"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert legacy["quota"]["quotaKey"] == "messages_daily"
    assert cognix_db.list_user_quotas("alice")

    reset = run_async(
        cognix_routes.admin_reset_user_quota(
            "alice",
            "tokens_daily",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert reset["quotaDeleted"] is True
    assert reset["legacyDeleted"] is True

    actions = [log["action"] for log in cognix_db.list_audit_logs(limit = 40)]
    assert "admin_role_quota_updated" in actions
    assert "admin_user_quota_updated" in actions
    assert "admin_quota_usage_recorded" in actions
    assert "admin_quota_override_created" in actions
    assert "admin_user_quota_reset" in actions


def test_admin_users_endpoints_are_admin_only_audited_and_persist_limits():
    seed_accounts()
    cognix_db.create_token_usage_event(
        "alice",
        model_id = "qwen-local",
        provider = "ollama",
        input_tokens = 10,
        output_tokens = 15,
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_users(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_users_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert blueprint["adminUsersBlueprint"]["services"] == [
        "AdminUserService",
        "UserActivityService",
        "UserLimitService",
        "UserPermissionService",
        "ActivityMonitoringService",
        "TokenUsageService",
        "ModelUsageAggregator",
    ]

    directory = run_async(cognix_routes.admin_users(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert directory["auditLogId"].startswith("aud_")
    assert directory["directory"]["summary"]["userCount"] == 2
    alice = next(item for item in directory["directory"]["users"] if item["username"] == "alice")
    assert alice["usage"]["totalTokens"] == 25

    detail = run_async(
        cognix_routes.admin_user_detail(
            "alice",
            reason = "support",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert detail["adminView"]["targetUsername"] == "alice"
    assert detail["adminView"]["viewedBy"] == storage.DEFAULT_ADMIN_USERNAME
    assert detail["sideEffects"]["adminViewLogWrite"] is True
    assert detail["sideEffects"]["activityEventWrite"] is True

    updated = run_async(
        cognix_routes.admin_update_user_limit(
            "alice",
            "tokens_daily",
            cognix_routes.AdminUserLimitRequest(limitValue = 25000, unit = "tokens", reason = "reduce daily spend"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert updated["limit"]["limitKey"] == "tokens_daily"
    assert updated["limit"]["limitValue"] == 25000
    assert updated["sideEffects"]["limitWrite"] is True

    limits = run_async(cognix_routes.admin_user_limits("alice", current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert limits["limits"]["tokens_daily"]["value"] == 25000
    activity = run_async(cognix_routes.admin_activity(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert any(item["eventType"] == "admin_user_limit_updated" for item in activity["activityEvents"])
    usage = run_async(cognix_routes.admin_usage(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert usage["usageDashboard"]["summary"]["totalTokens"] == 25

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    actions = [log["action"] for log in admin_read["logs"]]
    assert "admin_users_directory_viewed" in actions
    assert "admin_user_detail_viewed" in actions


def test_admin_token_usage_dashboard_builds_charts_rollups_and_persists_aggregates():
    seed_accounts()
    cognix_db.create_token_usage_event(
        "alice",
        organization_id = "org-ebk",
        project_id = "project-a",
        model_id = "qwen-local",
        provider = "ollama",
        input_tokens = 100,
        output_tokens = 50,
        message_count = 2,
        latency_ms = 120,
    )
    cognix_db.create_token_usage_event(
        storage.DEFAULT_ADMIN_USERNAME,
        organization_id = "org-ebk",
        project_id = "project-b",
        model_id = "gpt-cloud",
        provider = "openai",
        input_tokens = 200,
        output_tokens = 100,
        message_count = 1,
        latency_ms = 500,
        estimated_cost_usd = 0.003,
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_usage_blueprint(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_usage_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert blueprint["usageBlueprint"]["services"] == [
        "TokenUsageService",
        "ModelUsageAggregator",
        "CostEstimator",
        "UsageDashboardService",
    ]
    assert "cognix_daily_user_token_usage" in blueprint["usageBlueprint"]["tables"]
    assert "usage_by_model" in blueprint["usageBlueprint"]["charts"]
    assert "organization_id" in blueprint["usageBlueprint"]["loggingRule"]["requiredFields"]

    usage = run_async(cognix_routes.admin_usage(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    dashboard = usage["usageDashboard"]
    assert dashboard["summary"]["totalTokens"] == 450
    assert dashboard["summary"]["messageCount"] == 3
    assert dashboard["summary"]["localTokens"] == 150
    assert dashboard["summary"]["cloudTokens"] == 300
    assert dashboard["summary"]["averageLatencyMs"] == 310
    assert dashboard["organization"]["organizationId"] == "org-ebk"
    assert dashboard["organization"]["peakDay"]
    assert any(item["projectId"] == "project-a" for item in dashboard["byProject"])
    assert any(item["modelId"] == "qwen-local" for item in dashboard["charts"]["usageByModel"])
    assert {item["scope"] for item in dashboard["charts"]["localVsCloud"]} == {"cloud", "local"}
    assert dashboard["rollups"]["dailyUserTokenUsage"]
    assert dashboard["rollups"]["dailyModelUsage"]
    assert dashboard["sideEffects"]["rollupWrite"] is False

    aggregate = run_async(cognix_routes.admin_usage_aggregate(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert aggregate["auditLogId"].startswith("aud_")
    assert aggregate["sideEffects"]["rollupWrite"] is True
    assert len(aggregate["persisted"]["dailyUserTokenUsage"]) == 2
    assert len(aggregate["persisted"]["dailyModelUsage"]) == 2
    assert aggregate["persisted"]["organizationUsageSummary"][0]["totalTokens"] == 450

    user_daily = cognix_db.list_daily_user_token_usage(organization_id = "org-ebk")
    model_daily = cognix_db.list_daily_model_usage(organization_id = "org-ebk")
    org_summary = cognix_db.list_organization_usage_summary(organization_id = "org-ebk")
    assert len(user_daily) == 2
    assert len(model_daily) == 2
    assert org_summary[0]["total_tokens"] == 450

    actions = [log["action"] for log in cognix_db.list_audit_logs(limit = 20)]
    assert "admin_usage_rollups_aggregated" in actions


def test_admin_chat_core_redacts_e2ee_and_allows_compliance_content():
    thread = {
        "id": "thread-admin-chat-core",
        "title": "Support",
        "modelType": "ollama",
        "modelId": "qwen-local",
        "createdAt": 100,
        "ownerUsername": "alice",
    }
    messages = [
        {
            "id": "msg-secret",
            "threadId": "thread-admin-chat-core",
            "role": "user",
            "content": [{"type": "text", "text": "secret physics note"}],
            "createdAt": 101,
        }
    ]

    strict_detail = cognix_admin_chat.build_admin_chat_detail(
        thread = thread,
        messages = messages,
        policy = None,
        reason = "security review",
    )
    assert strict_detail["policy"]["mode"] == "e2ee_strict"
    assert strict_detail["policy"]["contentVisible"] is False
    assert strict_detail["messages"][0]["content"] is None
    assert strict_detail["messages"][0]["contentRedacted"] is True
    assert strict_detail["sideEffects"]["generation"] is False
    assert strict_detail["sideEffects"]["toolExecution"] is False

    compliance_detail = cognix_admin_chat.build_admin_chat_detail(
        thread = thread,
        messages = messages,
        policy = {
            "mode": "enterprise_compliance",
            "admin_chat_access": 1,
            "require_reason": 1,
        },
        reason = "legal review",
    )
    assert compliance_detail["policy"]["contentVisible"] is True
    assert compliance_detail["messages"][0]["content"][0]["text"] == "secret physics note"
    assert compliance_detail["sideEffects"]["contentRead"] is True

    with pytest.raises(ValueError):
        cognix_admin_chat.build_admin_chat_detail(
            thread = thread,
            messages = messages,
            policy = None,
            reason = "",
        )


def test_admin_chat_access_routes_are_policy_gated_audited_and_persistent():
    seed_accounts()
    now = int(time.time())
    studio_db_storage.upsert_chat_thread(
        {
            "id": "thread-admin-chat-1",
            "title": "Private research",
            "modelType": "ollama",
            "modelId": "qwen-local",
            "createdAt": now,
        },
        owner_username = "alice",
    )
    studio_db_storage.upsert_chat_message(
        {
            "id": "msg-admin-chat-1",
            "threadId": "thread-admin-chat-1",
            "role": "user",
            "content": [{"type": "text", "text": "secret physics note"}],
            "metadata": {"toolCalls": [{"name": "library_search"}], "documents": ["doc-1"]},
            "createdAt": now + 1,
        }
    )
    cognix_db.create_token_usage_event(
        "alice",
        model_id = "qwen-local",
        provider = "ollama",
        input_tokens = 12,
        output_tokens = 8,
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_chats(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_chats_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert "AdminChatService" in blueprint["adminChatBlueprint"]["services"]
    assert blueprint["adminChatBlueprint"]["policies"]["strictE2eeDefault"] is True

    directory = run_async(cognix_routes.admin_chats(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    row = next(item for item in directory["directory"]["threads"] if item["threadId"] == "thread-admin-chat-1")
    assert row["ownerUsername"] == "alice"
    assert row["messageCount"] == 1
    assert row["contentAvailable"] is False
    assert row["metadataOnly"] is True
    assert row["toolCallCount"] == 1
    assert row["documentAccessCount"] == 1
    assert directory["sideEffects"]["auditMetadataWrite"] is True
    assert cognix_db.get_conversation_audit_metadata("thread-admin-chat-1") is not None

    with pytest.raises(HTTPException) as missing_reason:
        run_async(
            cognix_routes.admin_chat_detail(
                "thread-admin-chat-1",
                current_subject = storage.DEFAULT_ADMIN_USERNAME,
            )
        )
    assert missing_reason.value.status_code == 400

    strict_detail = run_async(
        cognix_routes.admin_chat_detail(
            "thread-admin-chat-1",
            reason = "support review",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert strict_detail["detail"]["policy"]["contentVisible"] is False
    assert strict_detail["detail"]["messages"][0]["content"] is None
    assert "secret physics note" not in str(strict_detail["detail"]["messages"])
    assert strict_detail["accessLog"]["targetUsername"] == "alice"
    assert strict_detail["accessLog"]["contentVisible"] is False
    assert strict_detail["sideEffects"]["adminAccessLogWrite"] is True
    assert strict_detail["sideEffects"]["contentRead"] is False

    updated_policy = run_async(
        cognix_routes.admin_update_chat_policy(
            cognix_routes.AdminChatPolicyRequest(
                mode = "enterprise_compliance",
                admin_chat_access = True,
                require_reason = True,
                retention_days = 365,
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert updated_policy["policy"]["mode"] == "enterprise_compliance"
    assert updated_policy["policy"]["contentVisible"] is True
    assert updated_policy["storedPolicy"]["adminChatAccess"] is True
    assert cognix_db.get_chat_access_policy()["mode"] == "enterprise_compliance"

    compliance_detail = run_async(
        cognix_routes.admin_chat_detail(
            "thread-admin-chat-1",
            reason = "compliance review",
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert compliance_detail["detail"]["policy"]["contentVisible"] is True
    assert compliance_detail["detail"]["messages"][0]["content"][0]["text"] == "secret physics note"
    assert compliance_detail["accessLog"]["contentVisible"] is True
    assert compliance_detail["sideEffects"]["contentRead"] is True

    export = run_async(
        cognix_routes.admin_chat_export_plan(
            "thread-admin-chat-1",
            cognix_routes.AdminChatExportPlanRequest(
                reason = "legal export",
                output_format = "json",
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert export["exportPlan"]["dryRun"] is True
    assert export["exportPlan"]["contentIncluded"] is True
    assert export["sideEffects"]["exportWrite"] is False

    logs = cognix_db.list_admin_chat_access_logs(target_username = "alice")
    assert len(logs) == 2
    assert [item["content_visible"] for item in logs] == [True, False]
    actions = [log["action"] for log in cognix_db.list_audit_logs(limit = 20)]
    assert "admin_chat_policy_updated" in actions
    assert "admin_chat_detail_viewed" in actions
    assert "admin_chat_export_planned" in actions


def test_admin_banned_core_builds_reports_evidence_and_reactivation_plan():
    blueprint = cognix_admin_banned.build_banned_blueprint()
    assert blueprint["services"] == ["BanService", "BanReportGenerator", "UserRiskService"]
    assert "cognix_ban_reports" in blueprint["tables"]
    assert blueprint["sideEffects"]["generation"] is False

    dashboard = cognix_admin_banned.build_banned_dashboard(
        bans = [
            {
                "id": "ban_1",
                "username": "alice",
                "client_key": "client-a",
                "reason": "SQL injection detected",
                "status": "pending_admin_review",
                "created_at": "2026-06-29T00:00:00+00:00",
                "temporary_until": "2026-06-30T00:00:00+00:00",
            }
        ],
        reports = [
            {
                "id": "rep_1",
                "username": "alice",
                "category": "security",
                "title": "Suspicious behavior",
                "message": "Repeated malicious prompts.",
                "status": "open",
            }
        ],
        security_events = [
            {
                "id": "sec_1",
                "username": "alice",
                "client_key": "client-a",
                "category": "sql_injection",
                "severity": "critical",
                "pattern_label": "SQL injection",
                "ban_id": "ban_1",
            }
        ],
        audit_logs = [],
        ban_reports = [],
        evidence_logs = [{"ban_id": "ban_1", "source_type": "admin_note", "excerpt": "manual evidence"}],
    )

    row = dashboard["bannedUsers"][0]
    assert dashboard["summary"]["pending"] == 1
    assert row["aiReport"]["riskLevel"] == "critical"
    assert row["aiReport"]["recommendation"] == "maintain_ban_and_require_admin_review"
    assert row["evidence"]["securityEvents"][0]["id"] == "sec_1"
    assert row["evidence"]["manualLogs"][0]["excerpt"] == "manual evidence"
    assert row["reactivation"]["possible"] is False


def test_admin_banned_routes_manage_reports_evidence_reactivation_and_audit():
    seed_accounts()
    event = cognix_db.record_security_event(
        username = "alice",
        client_key = "client-a",
        category = "sql_injection",
        severity = "critical",
        pattern_label = "SQL injection",
        method = "POST",
        path = "/api/auth/login",
        excerpt = "admin' OR 1=1 --",
        create_temporary_ban = True,
    )
    ban_id = event["ban_id"]
    cognix_db.create_report(
        "alice",
        "security",
        "Suspicious behavior",
        "Repeated malicious prompts.",
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_banned(current_subject = "alice"))
    assert user_read.value.status_code == 403

    blueprint = run_async(cognix_routes.admin_banned_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert blueprint["bannedBlueprint"]["banServiceVersion"] == "cognix_ban_service_v1"

    dashboard = run_async(cognix_routes.admin_banned(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert dashboard["bannedDashboard"]["summary"]["pending"] == 1
    assert dashboard["bannedDashboard"]["bannedUsers"][0]["banId"] == ban_id
    assert dashboard["bannedDashboard"]["bannedUsers"][0]["aiReport"]["riskLevel"] == "critical"

    evidence = run_async(
        cognix_routes.admin_add_ban_evidence(
            ban_id,
            cognix_routes.BanEvidenceRequest(
                sourceType = "admin_note",
                excerpt = "Manual admin evidence",
                metadata = {"ticket": "INC-1"},
            ),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert evidence["evidence"]["banId"] == ban_id
    assert evidence["sideEffects"]["evidenceWrite"] is True

    report = run_async(
        cognix_routes.admin_generate_ban_report(
            ban_id,
            cognix_routes.BanReportRequest(store = True),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert report["report"]["riskLevel"] == "critical"
    assert report["storedReport"]["banId"] == ban_id
    assert report["sideEffects"]["reportWrite"] is True

    cleared = run_async(
        cognix_routes.admin_update_banned(
            ban_id,
            cognix_routes.BanStatusRequest(status = "cleared", admin_decision = "Reviewed and cleared"),
            current_subject = storage.DEFAULT_ADMIN_USERNAME,
        )
    )
    assert cleared["ban"]["status"] == "cleared"
    assert cleared["sideEffects"]["banWrite"] is True

    actions = [log["action"] for log in cognix_db.list_audit_logs(limit = 20)]
    assert "ban_evidence_added" in actions
    assert "ban_report_generated" in actions
    assert "ban_status_updated" in actions


def test_admin_security_center_builds_threat_risk_and_health(monkeypatch):
    seed_accounts()
    monkeypatch.setattr(cognix_routes.cognix_hardware, "get_hardware_profile", stub_hardware_profile)

    event = cognix_db.record_security_event(
        username = "alice",
        client_key = "client-a",
        category = "sql_injection",
        severity = "critical",
        pattern_label = "SQL injection",
        method = "POST",
        path = "/api/auth/login",
        excerpt = "admin' OR 1=1 --",
        create_temporary_ban = True,
    )
    cognix_db.create_report(
        "alice",
        "security",
        "Cloud risk",
        "Project uses cloud with sensitive data.",
    )
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = storage.DEFAULT_ADMIN_USERNAME,
        action = "permission_granted",
        resource_type = "permission",
        resource_id = "developer_mode",
        severity = "warning",
        metadata = {"permissionKey": "developer_mode"},
    )
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = storage.DEFAULT_ADMIN_USERNAME,
        action = "permission_denied",
        resource_type = "permission",
        resource_id = "codex:run",
        severity = "warning",
        metadata = {"missingPermission": "codex:run"},
    )
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = "codex",
        action = "codex_run_denied",
        resource_type = "codex",
        resource_id = "cloud-training",
        severity = "warning",
        metadata = {"target": "google_colab", "reason": "permission denied"},
    )
    cognix_db.create_audit_log(
        username = "alice",
        actor_username = "system",
        action = "secret_exposure_detected",
        resource_type = "configuration",
        resource_id = ".env",
        severity = "critical",
        metadata = {"file": ".env", "token": "redacted"},
    )
    cognix_db.create_security_threat(
        title = "HTTPS configuration drift",
        category = "configuration_issues",
        severity = "medium",
        summary = "cognix.local HTTPS configuration needs review.",
        evidence = {"host": "cognix.local"},
        files = ["studio/backend/run.py"],
        recommended_solution = "Verify HTTPS proxy and certificate configuration.",
    )
    finding = cognix_db.create_vulnerability_finding(
        package_name = "llama-cpp-python",
        source_name = "pip",
        installed_version = "0.0.1",
        fixed_version = "0.0.2",
        severity = "high",
        description = "Runtime dependency needs upgrade.",
        evidence = {"file": "requirements.txt"},
    )
    cognix_db.create_security_report(
        title = "Dependency risk summary",
        summary = "Risky dependency queued for review.",
        impact = "Runtime surface could be exposed.",
        severity = "high",
        report = {"findingId": finding["id"]},
    )
    cognix_db.create_security_remediation_task(
        title = "Upgrade llama-cpp-python",
        priority = "high",
        recommended_solution = "Upgrade dependency before enabling remote training workers.",
        finding_id = finding["id"],
        assignee = storage.DEFAULT_ADMIN_USERNAME,
    )

    with pytest.raises(HTTPException) as user_read:
        run_async(cognix_routes.admin_security_threats(current_subject = "alice"))
    assert user_read.value.status_code == 403

    with pytest.raises(HTTPException) as user_blueprint:
        run_async(cognix_routes.admin_security_threats_blueprint(current_subject = "alice"))
    assert user_blueprint.value.status_code == 403

    blueprint = run_async(
        cognix_routes.admin_security_threats_blueprint(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    assert blueprint["blueprintVersion"] == "cognix_security_threat_center_v1"
    assert "SecurityThreatService" in blueprint["services"]
    assert "VulnerabilityScannerAdapter" in blueprint["services"]
    assert "cognix_vulnerability_findings" in blueprint["tables"]
    assert "filesAffected" in blueprint["codexSummaryFields"]
    assert blueprint["sideEffects"]["externalScan"] is False

    with pytest.raises(HTTPException) as user_scanner_contract:
        run_async(cognix_routes.admin_vulnerability_scanner_contract(current_subject = "alice"))
    assert user_scanner_contract.value.status_code == 403

    scanner_contract_body = run_async(
        cognix_routes.admin_vulnerability_scanner_contract(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )
    scanner_contract = scanner_contract_body["vulnerabilityScannerContract"]
    assert scanner_contract_body["plannerVersion"] == "cognix_vulnerability_scanner_adapter_v1"
    assert scanner_contract["contractVersion"] == "cognix_vulnerability_scanner_adapter_v1"
    assert scanner_contract["mode"] == "vulnerability_scanner_adapter_read_only"
    assert any(item["id"] == "python_dependencies" for item in scanner_contract["supportedSources"])
    assert any(item["id"] == "cloud_training_dependencies" for item in scanner_contract["supportedSources"])
    assert scanner_contract["scanPolicy"]["externalScannerExecutionAllowedHere"] is False
    assert scanner_contract["scanPolicy"]["networkVulnerabilityLookupAllowedHere"] is False
    assert scanner_contract["scanPolicy"]["rawManifestContentReturned"] is False
    assert scanner_contract["redactionPolicy"]["rawSecretsReturned"] is False
    assert scanner_contract_body["sideEffects"]["externalScan"] is False
    assert scanner_contract_body["sideEffects"]["databaseWrite"] is False
    assert scanner_contract_body["sideEffects"]["subprocess"] is False

    security = run_async(
        cognix_routes.admin_security_threats(current_subject = storage.DEFAULT_ADMIN_USERNAME)
    )

    assert security["threatReport"]["reportVersion"] == "cognix_admin_security_v1"
    assert security["securityThreatCenter"]["centerVersion"] == "cognix_security_threat_center_v1"
    assert security["securityThreatCenter"]["scannerAdapterVersion"] == "cognix_vulnerability_scanner_adapter_v1"
    assert security["securityThreatCenter"]["summary"]["cloudRisks"] >= 1
    assert security["securityThreatCenter"]["summary"]["codexIncidents"] >= 1
    assert security["securityThreatCenter"]["summary"]["permissionErrors"] >= 1
    assert security["securityThreatCenter"]["summary"]["exposedSecrets"] >= 1
    categories = {item["id"]: item for item in security["incidentCategories"]}
    assert categories["risky_dependencies"]["count"] >= 1
    assert categories["configuration_issues"]["count"] >= 1
    assert any(item["title"] == "llama-cpp-python" for item in categories["risky_dependencies"]["items"])
    assert any(item["recommendedSolution"] for item in security["codexSummaries"])
    assert security["threatReport"]["summary"]["critical"] >= 1
    assert security["threatReport"]["summary"]["activeBans"] == 1
    assert security["sideEffects"]["databaseWrite"] is False
    assert security["sideEffects"]["generation"] is False
    assert security["vulnerabilityFindings"][0]["packageName"] == "llama-cpp-python"
    assert security["remediationTasks"][0]["recommendedSolution"]
    threat = next(item for item in security["threatReport"]["threats"] if item["sourceEventId"] == event["id"])
    assert threat["title"] == "SQL injection"
    assert threat["severity"] == "critical"
    assert "POST /api/auth/login" in threat["evidence"]
    assert threat["recommendedSolution"]

    risk = run_async(cognix_routes.admin_risk_scores(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert risk["riskScoring"]["scoringVersion"] == "cognix_risk_scoring_v1"
    assert risk["riskScoring"]["summary"]["maxLevel"] == "critical"
    alice_score = next(item for item in risk["riskScoring"]["scores"] if item["entityId"] == "alice")
    assert alice_score["features"]["criticalEvents"] == 1
    assert alice_score["features"]["activeBans"] == 1
    assert alice_score["recommendedAction"]
    assert risk["sideEffects"]["permissionMutation"] is False

    health = run_async(cognix_routes.admin_system_health(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    assert health["systemHealth"]["healthVersion"] == "cognix_system_health_v1"
    assert health["systemHealth"]["overallStatus"] == "red"
    assert any(item["id"] == "security-monitor" for item in health["systemHealth"]["services"])
    assert health["sideEffects"]["workerMutation"] is False


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
    assert classification["externalMoePlan"]["primaryExpert"]["expertId"] == "cognix-code"
    assert classification["externalMoePlan"]["executionBoundary"]["backendOrchestratorRequired"] is True


def test_router_fallback_chain_handles_ambiguous_experts_without_loading_models():
    classification = classify_objective(
        "Calcul equation force vitesse.",
    )

    chain = classification["routerFallbackChain"]
    assert classification["needsClarification"] is True
    assert chain["fallbackChainVersion"] == "cognix_router_fallback_chain_v1"
    assert chain["status"] == "clarification_required"
    assert "ambiguous_domain" in chain["triggerConditions"]
    assert any(step["id"] == "clarify_ambiguous_domain" for step in chain["steps"])
    assert any(step["id"].startswith("secondary_") for step in chain["steps"])
    assert any(step["id"] == "generalist_fallback" for step in chain["steps"])
    assert chain["summary"]["hasSecondaryExpert"] is True
    assert chain["summary"]["hasGeneralistFallback"] is True
    assert chain["executionBoundary"]["backendOrchestratorRequired"] is True
    assert chain["executionBoundary"]["frontendDirectModelCallAllowed"] is False
    assert chain["executionBoundary"]["automaticFallbackExecutionAllowed"] is False
    assert chain["sideEffects"]["modelLoad"] is False
    assert chain["sideEffects"]["generation"] is False
    assert chain["sideEffects"]["fallbackExecution"] is False


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
    assert body["architectureDecision"]["architectureDecisionVersion"] == "cognix_architecture_decision_v1"
    assert body["architectureDecision"]["runtime"]["adapterId"] == "ollama"
    assert body["architectureDecision"]["routing"]["externalMoeRouterVersion"] == "cognix_external_moe_router_v1"
    assert body["architectureDecision"]["routing"]["routerFallbackChainVersion"] == "cognix_router_fallback_chain_v1"
    assert body["architectureDecision"]["routing"]["primaryExpertId"] == "cognix-code"
    assert body["architectureDecision"]["routing"]["hasGeneralistFallback"] is True
    assert body["architectureDecision"]["routing"]["automaticFallbackExecutionAllowed"] is False
    assert body["architectureDecision"]["security"]["automaticExecutionAllowed"] is False
    assert body["architectureDecision"]["sideEffects"]["codeModification"] is False
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
    assert decision_log["decision"]["architectureDecisionVersion"] == "cognix_architecture_decision_v1"
    assert decision_log["decision"]["architectureDecision"]["runtime"]["adapterId"] == "ollama"
    assert decision_log["decision"]["architectureDecision"]["routing"]["externalMoeRouterVersion"] == "cognix_external_moe_router_v1"
    assert decision_log["decision"]["architectureDecision"]["security"]["frontendDirectModelCallAllowed"] is False


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
