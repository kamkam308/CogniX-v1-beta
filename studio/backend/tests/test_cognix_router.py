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
from core.cognix import background_agents as cognix_background_agents
from core.cognix import cache_manager as cognix_cache_manager
from core.cognix import codex_pipeline as cognix_codex_pipeline
from core.cognix import context_graph as cognix_context_graph
from core.cognix import context_manager as cognix_context_manager
from core.cognix import debate_orchestrator as cognix_debate_orchestrator
from core.cognix import deployment_manager as cognix_deployment_manager
from core.cognix import draft_generation as cognix_draft_generation
from core.cognix import decision_engine as cognix_decision_engine
from core.cognix import dynamic_ui as cognix_dynamic_ui
from core.cognix import governance_manager as cognix_governance_manager
from core.cognix import integration_manager as cognix_integration_manager
from core.cognix import intent_prediction as cognix_intent_prediction
from core.cognix import memory_manager as cognix_memory_manager
from core.cognix import model_lifecycle as cognix_model_lifecycle
from core.cognix import module_registry as cognix_module_registry
from core.cognix import onboarding as cognix_onboarding
from core.cognix import optimization_planner as cognix_optimization_planner
from core.cognix import orchestrator as cognix_orchestrator
from core.cognix import project_experts as cognix_project_experts
from core.cognix import prompt_compression as cognix_prompt_compression
from core.cognix import rag_planner as cognix_rag_planner
from core.cognix import research_watch as cognix_research_watch
from core.cognix import response_reflection as cognix_response_reflection
from core.cognix import runtime_adapter as cognix_runtime_adapter
from core.cognix import skill_memory as cognix_skill_memory
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
    assert registry["policies"]["frontendDirectOptimizationMutationAllowed"] is False
    assert registry["sideEffects"]["runtimeConfigWrite"] is False
    assert registry["sideEffects"]["benchmarkRun"] is False
    assert registry["sideEffects"]["cacheMutation"] is False

    capabilities = {item["id"]: item for item in registry["capabilities"]}
    assert "semantic_cache" in capabilities
    assert "kv_cache_eviction" in capabilities
    assert "flash_attention" in capabilities
    assert capabilities["semantic_cache"]["benchmarkGate"]["status"] == "required"
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
    assert plan["selectedOptimizationIds"] == ["semantic_cache", "kv_cache_eviction"]
    assert "benchmark_baseline" in plan["summary"]["blockedGateIds"]
    assert all(ticket["status"] == "blocked_by_gates" for ticket in plan["tickets"])
    assert all(ticket["willEnableRuntime"] is False for ticket in plan["tickets"])
    assert all(ticket["willRunBenchmark"] is False for ticket in plan["tickets"])
    assert plan["sideEffects"]["runtimeConfigWrite"] is False
    assert plan["sideEffects"]["cacheMutation"] is False
    assert plan["sideEffects"]["generation"] is False


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
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert body["sideEffects"]["benchmarkRun"] is False
    assert body["sideEffects"]["cacheMutation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_capability_registry_built"
    assert log["metadata"]["registryVersion"] == "cognix_optimization_capability_registry_v1"
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
    assert plan["selectedOptimizationIds"] == ["semantic_cache", "kv_cache_eviction"]
    assert "benchmark_baseline" in plan["summary"]["blockedGateIds"]
    assert body["sideEffects"]["runtimeConfigWrite"] is False
    assert body["sideEffects"]["cacheMutation"] is False
    assert body["sideEffects"]["generation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "optimization_experiment_plan_built"
    assert log["metadata"]["experimentPlanVersion"] == "cognix_optimization_experiment_plan_v1"
    assert "benchmark_baseline" in log["metadata"]["blockedGateIds"]


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


def test_thinking_status_redacts_technical_model_details():
    lifecycle = {
        "installPlan": {"required": False},
        "loadPlan": {"action": "would_load_on_demand"},
        "compatibility": {"fit": {"status": "ok"}},
        "warnings": [],
    }

    plan = cognix_thinking_status.build_thinking_status_plan(
        objective = "Explique ce bug avec huihui_ai/qwen3-vl-abliterated:4b-instruct",
        classification = {"selectedDomain": "code", "label": "Code", "needsClarification": False},
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
    assert plan["thinkingStatusVersion"] == "cognix_thinking_status_v1"
    assert plan["status"] == "ready"
    assert plan["progress"] == 100
    assert plan["displayContract"]["frontendMustHideModelIdentifiers"] is True
    assert plan["redaction"]["visibleTimelineContainsModelIds"] is False
    assert "qwen" not in visible_text
    assert "cognix-code-4b-q4" not in visible_text
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
    assert thinking["redaction"]["visibleTimelineContainsRoutingScores"] is False
    assert thinking["sideEffects"]["generation"] is False
    assert thinking["sideEffects"]["uiMutation"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["id"] == body["auditLogId"]
    assert log["action"] == "thinking_status_plan_built"
    assert log["resourceType"] == "cognix_thinking_status"
    assert log["metadata"]["thinkingStatusVersion"] == "cognix_thinking_status_v1"
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
    assert {"latex-renderer", "python-runtime", "pytorch", "ollama", "google-drive"}.issubset(tools)
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
    assert {"latex-renderer", "rag-indexer"}.issubset(tool_ids)
    assert {"latex-renderer", "rag-indexer"}.issubset(stored_ids)
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
    assert "cloud_training" in queues
    assert "cloud_training_job" in queues["cloud_training"]["acceptedJobTypes"]
    assert queues["cloud_training"]["requiresHumanConfirmation"] is True


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
    assert registry["sideEffects"]["toolExecution"] is False
    assert registry["sideEffects"]["secretRead"] is False

    modules = {item["id"]: item for item in registry["modules"]}
    assert {
        "cognix-local-core",
        "cognix-model-lifecycle",
        "cognix-optimization-engine",
        "cognix-prompt-compression",
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
        "cognix-ai-workflow-recorder",
        "cognix-onboarding",
        "cognix-rag",
        "cognix-fine-tuning",
        "cognix-worker-queue",
        "cognix-research-watch",
        "cognix-integrations",
        "cognix-codex-secure-agent",
        "cognix-enterprise-foundation",
        "cognix-deployment-manager",
    }.issubset(modules)
    assert modules["cognix-local-core"]["activationState"] == "ready"
    assert "module_manifest_registry" in modules["cognix-local-core"]["capabilities"]
    assert "/api/cognix/modules/manifests" in modules["cognix-local-core"]["routes"]
    assert modules["cognix-model-lifecycle"]["activationState"] == "ready"
    assert "load_unload_planning" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "cache_load_planning" in modules["cognix-model-lifecycle"]["capabilities"]
    assert "/api/cognix/models/lifecycle-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert "/api/cognix/models/cache/load-plan" in modules["cognix-model-lifecycle"]["routes"]
    assert modules["cognix-optimization-engine"]["dependencyState"]["ready"] is True
    assert "optimization_capability_registry" in modules["cognix-optimization-engine"]["capabilities"]
    assert "benchmark_gated_experiments" in modules["cognix-optimization-engine"]["capabilities"]
    assert "/api/cognix/optimizations/capabilities" in modules["cognix-optimization-engine"]["routes"]
    assert "/api/cognix/optimizations/experiment-plan" in modules["cognix-optimization-engine"]["routes"]
    assert modules["cognix-prompt-compression"]["dependencyState"]["ready"] is True
    assert "prompt_compression" in modules["cognix-prompt-compression"]["capabilities"]
    assert "importance_ranking" in modules["cognix-prompt-compression"]["capabilities"]
    assert "compression_evaluation" in modules["cognix-prompt-compression"]["capabilities"]
    assert "/api/cognix/prompt-compression/plan" in modules["cognix-prompt-compression"]["routes"]
    assert "/api/cognix/prompt-compression/contexts" in modules["cognix-prompt-compression"]["routes"]
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
    assert modules["cognix-response-reflection"]["dependencyState"]["ready"] is True
    assert "response_quality_evaluation" in modules["cognix-response-reflection"]["capabilities"]
    assert "raw_reasoning_redaction" in modules["cognix-response-reflection"]["capabilities"]
    assert "/api/cognix/reflection/evaluate" in modules["cognix-response-reflection"]["routes"]
    assert "/api/cognix/reflection/evaluations" in modules["cognix-response-reflection"]["routes"]
    assert modules["cognix-multi-draft-generation"]["dependencyState"]["ready"] is True
    assert "style_profile_registry" in modules["cognix-multi-draft-generation"]["capabilities"]
    assert "response_variant_store" in modules["cognix-multi-draft-generation"]["capabilities"]
    assert "/api/cognix/drafts/styles" in modules["cognix-multi-draft-generation"]["routes"]
    assert "/api/cognix/drafts/plan" in modules["cognix-multi-draft-generation"]["routes"]
    assert "/api/cognix/drafts/variants" in modules["cognix-multi-draft-generation"]["routes"]
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
    assert "/api/cognix/memory/plan" in modules["cognix-memory-manager"]["routes"]
    assert modules["cognix-long-term-skill-memory"]["dependencyState"]["ready"] is True
    assert "skill_memory_candidates" in modules["cognix-long-term-skill-memory"]["capabilities"]
    assert "memory_approval_flow" in modules["cognix-long-term-skill-memory"]["capabilities"]
    assert "context_injection_planning" in modules["cognix-long-term-skill-memory"]["capabilities"]
    assert "/api/cognix/memory/skills/candidates" in modules["cognix-long-term-skill-memory"]["routes"]
    assert "/api/cognix/memory/skills/export" in modules["cognix-long-term-skill-memory"]["routes"]
    assert "/api/cognix/memory/skills/injection-plan" in modules["cognix-long-term-skill-memory"]["routes"]
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
    assert "/api/cognix/rag/sources" in modules["cognix-rag"]["routes"]
    assert "/api/cognix/rag/indexing-plan" in modules["cognix-rag"]["routes"]
    assert "cloud_training_targets" in modules["cognix-fine-tuning"]["capabilities"]
    assert "cloud_training_handoff" in modules["cognix-fine-tuning"]["capabilities"]
    assert "/api/cognix/fine-tuning/cloud-handoff-plan" in modules["cognix-fine-tuning"]["routes"]
    assert "worker_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "cloud_training_job_specs" in modules["cognix-worker-queue"]["capabilities"]
    assert "/api/cognix/workers/registry" in modules["cognix-worker-queue"]["routes"]
    assert "/api/cognix/workers/job-spec-plan" in modules["cognix-worker-queue"]["routes"]
    assert "technology_watch" in modules["cognix-research-watch"]["capabilities"]
    assert "benchmark_gate" in modules["cognix-research-watch"]["capabilities"]
    assert "/api/cognix/research/integration-plan" in modules["cognix-research-watch"]["routes"]
    assert "tool_permission_matrix" in modules["cognix-integrations"]["capabilities"]
    assert "/api/cognix/tools/permission-matrix" in modules["cognix-integrations"]["routes"]
    assert "sso_planning" in modules["cognix-enterprise-foundation"]["capabilities"]
    assert "/api/cognix/governance/plan" in modules["cognix-enterprise-foundation"]["routes"]
    assert modules["cognix-deployment-manager"]["dependencyState"]["ready"] is True
    assert "cognix-integrations" in modules["cognix-codex-secure-agent"]["dependencyState"]["dependencies"]


def test_module_manifest_bundle_exports_declarative_contract_without_mutation():
    bundle = cognix_module_registry.build_module_manifest_bundle()

    assert bundle["bundleVersion"] == "cognix_module_manifest_bundle_v1"
    assert bundle["moduleRegistryVersion"] == "cognix_module_registry_v1"
    assert bundle["schemaVersion"] == "cognix_module_manifest_schema_v1"
    assert bundle["mode"] == "declarative_dry_run"
    assert bundle["contract"]["sourceOfTruth"] == "backend_source_manifest"
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
    assert "/api/cognix/modules/manifests" in manifests["cognix-local-core"]["routes"]
    assert manifests["cognix-local-core"]["manifestValidation"]["ready"] is True
    assert "developer_mode" in manifests["cognix-codex-secure-agent"]["permissions"]
    assert "github" in manifests["cognix-codex-secure-agent"]["tools"]

    developer_bundle = cognix_module_registry.build_module_manifest_bundle(edition = "developer")
    assert developer_bundle["editionFilter"] == "developer"
    assert developer_bundle["validation"]["ready"] is True
    assert all("developer" in item["editionTargets"] for item in developer_bundle["manifests"])


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
    assert registry["globalPolicies"]["permissionMatrixAvailable"] is True
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
    assert body["sideEffects"]["secretRead"] is False
    assert body["sideEffects"]["toolExecution"] is False

    admin_read = run_async(cognix_routes.admin_audit_logs(current_subject = storage.DEFAULT_ADMIN_USERNAME))
    log = admin_read["logs"][0]
    assert log["action"] == "tool_action_planned"
    assert log["metadata"]["missingPermissions"] == []
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
