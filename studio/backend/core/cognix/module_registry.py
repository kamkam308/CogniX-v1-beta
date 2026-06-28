# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Declarative CogniX module registry.

Modules describe optional product capabilities without mutating routes, UI, or
permissions. Activation remains a separate guarded workflow.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_MODULE_REGISTRY_VERSION = "cognix_module_registry_v1"


MODULE_MANIFESTS: list[dict[str, Any]] = [
    {
        "id": "cognix-local-core",
        "displayName": "CogniX Local Core",
        "editionTargets": ["free", "local", "developer"],
        "status": "enabled",
        "capabilities": ["chat_local", "model_registry", "hardware_profiler", "model_recommender", "model_pack_registry"],
        "routes": ["/api/cognix/models/registry", "/api/cognix/models/packs", "/api/cognix/hardware/profile"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["chat", "model-selector"],
        "dependencies": [],
    },
    {
        "id": "cognix-model-lifecycle",
        "displayName": "CogniX Model Lifecycle",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": ["model_packs", "install_planning", "load_unload_planning", "hardware_fit", "cache_policy"],
        "routes": ["/api/cognix/models/packs", "/api/cognix/models/lifecycle-plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-3b-q4", "ollama-qwen-4b-local"],
        "uiPanels": ["model-selector", "settings-models"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-projects",
        "displayName": "CogniX Projects",
        "editionTargets": ["free", "developer", "business", "university"],
        "status": "enabled",
        "capabilities": ["project_memory", "project_default_model", "specialized_projects", "project_expert_routing", "generalist_verifier"],
        "routes": ["/projects", "/api/cognix/project-model-defaults", "/api/cognix/project-experts/registry", "/api/cognix/projects/{project_id}/expert-plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-code-small", "cognix-math-small", "cognix-physics-small"],
        "uiPanels": ["project-sidebar", "project-settings"],
        "dependencies": ["cognix-local-core", "cognix-model-lifecycle"],
    },
    {
        "id": "cognix-onboarding",
        "displayName": "CogniX Intelligent Onboarding",
        "editionTargets": ["free", "local", "developer", "business", "university", "enterprise"],
        "status": "enabled",
        "capabilities": ["hardware_onboarding", "starter_pack_recommendation", "edition_guidance"],
        "routes": ["/api/cognix/onboarding/plan"],
        "permissions": ["authenticated"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["onboarding"],
        "dependencies": ["cognix-local-core", "cognix-projects"],
    },
    {
        "id": "cognix-rag",
        "displayName": "CogniX RAG",
        "editionTargets": ["free", "developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["document_memory", "retrieval_planning", "citations"],
        "routes": ["/api/cognix/rag/plan", "/api/cognix/context/pack"],
        "permissions": ["authenticated", "rag:read"],
        "tools": ["google-drive"],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["project-documents"],
        "dependencies": ["cognix-local-core", "cognix-projects"],
    },
    {
        "id": "cognix-fine-tuning",
        "displayName": "CogniX Fine-tuning",
        "editionTargets": ["developer", "enterprise"],
        "status": "planned",
        "capabilities": ["dataset_validation", "qlora_planning", "adapter_library"],
        "routes": ["/api/cognix/fine-tuning/plan"],
        "permissions": ["developer_mode"],
        "tools": [],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["dataset-manager", "lora-manager"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-integrations",
        "displayName": "CogniX Integrations",
        "editionTargets": ["developer", "business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["tool_registry", "integration_status", "permissions_audit"],
        "routes": ["/api/cognix/integrations/status", "/api/cognix/tools/registry"],
        "permissions": ["authenticated"],
        "tools": ["github", "google-drive", "gmail", "notion"],
        "defaultModels": [],
        "uiPanels": ["integrations-settings"],
        "dependencies": ["cognix-local-core"],
    },
    {
        "id": "cognix-codex-secure-agent",
        "displayName": "CogniX Codex Secure Agent",
        "editionTargets": ["developer", "enterprise"],
        "status": "planned",
        "capabilities": ["feature_request", "branch_pipeline", "tests_build_preview"],
        "routes": ["/api/cognix/tools/plan"],
        "permissions": ["developer_mode"],
        "tools": ["codex-secure-agent", "github"],
        "defaultModels": ["cognix-code-small"],
        "uiPanels": ["developer-workflow"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
    },
    {
        "id": "cognix-enterprise-foundation",
        "displayName": "CogniX Enterprise Foundation",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["organizations", "rbac", "sso_planning", "education_spaces", "audit_logs", "deployment_targets"],
        "routes": [
            "/api/cognix/admin/audit-logs",
            "/api/cognix/admin/permissions/{username}",
            "/api/cognix/governance/blueprint",
            "/api/cognix/governance/plan",
        ],
        "permissions": ["admin"],
        "tools": ["sharepoint", "microsoft-teams", "google-workspace"],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["admin-security", "organization-settings", "education-admin", "deployment-settings"],
        "dependencies": ["cognix-local-core", "cognix-integrations"],
    },
    {
        "id": "cognix-deployment-manager",
        "displayName": "CogniX Deployment Manager",
        "editionTargets": ["business", "university", "enterprise"],
        "status": "planned",
        "capabilities": ["deployment_targets", "gpu_scheduler_planning", "monitoring_plan", "autoscaling_plan"],
        "routes": ["/api/cognix/deployments/targets", "/api/cognix/deployments/plan"],
        "permissions": ["admin"],
        "tools": ["github", "cloud-provider", "microsoft-teams"],
        "defaultModels": ["cognix-general-small"],
        "uiPanels": ["deployment-settings", "admin-security"],
        "dependencies": ["cognix-local-core", "cognix-integrations", "cognix-enterprise-foundation"],
    },
]


def _manifest_ids() -> set[str]:
    return {str(item.get("id")) for item in MODULE_MANIFESTS}


def _dependency_status(module: dict[str, Any]) -> dict[str, Any]:
    manifest_ids = _manifest_ids()
    dependencies = [
        str(item) for item in module.get("dependencies") or [] if item
    ]
    missing = [item for item in dependencies if item not in manifest_ids]
    return {
        "dependencies": dependencies,
        "missingDependencies": missing,
        "ready": not missing,
    }


def _module_record(module: dict[str, Any]) -> dict[str, Any]:
    record = deepcopy(module)
    dependency_state = _dependency_status(record)
    record["dependencyState"] = dependency_state
    record["activationState"] = (
        "ready"
        if record.get("status") == "enabled" and dependency_state["ready"]
        else "planned"
        if dependency_state["ready"]
        else "blocked"
    )
    record["riskLevel"] = (
        "high"
        if "admin" in record.get("permissions", [])
        else "medium"
        if "developer_mode" in record.get("permissions", [])
        else "low"
    )
    return record


def build_module_registry() -> dict[str, Any]:
    modules = [_module_record(module) for module in MODULE_MANIFESTS]
    return {
        "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
        "mode": "declarative_dry_run",
        "modules": modules,
        "summary": {
            "moduleCount": len(modules),
            "enabledCount": sum(1 for item in modules if item.get("status") == "enabled"),
            "plannedCount": sum(1 for item in modules if item.get("status") == "planned"),
            "blockedCount": sum(1 for item in modules if item.get("activationState") == "blocked"),
            "uiMutationAllowed": False,
            "routeMutationAllowed": False,
        },
        "globalPolicies": {
            "declarativeManifestRequired": True,
            "dependenciesMustResolve": True,
            "permissionsMustBeDeclared": True,
            "activationRequiresAudit": True,
            "frontendCannotSelfRegisterModules": True,
        },
        "sideEffects": {
            "moduleActivation": False,
            "routeRegistration": False,
            "uiMutation": False,
            "permissionWrite": False,
        },
    }


def build_module_activation_plan(module_id: str) -> dict[str, Any]:
    registry = build_module_registry()
    module = next(
        (item for item in registry["modules"] if item.get("id") == module_id),
        None,
    )
    if module is None:
        return {
            "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
            "mode": "dry_run",
            "moduleId": module_id,
            "status": "unknown_module",
            "allowedToActivate": False,
            "steps": [
                {
                    "id": "verify_manifest",
                    "status": "blocked",
                    "detail": "Module absent de la registry CogniX.",
                }
            ],
            "sideEffects": registry["sideEffects"],
        }

    dependency_ready = bool(module.get("dependencyState", {}).get("ready"))
    already_enabled = module.get("status") == "enabled"
    allowed_to_activate = dependency_ready and not already_enabled
    return {
        "moduleRegistryVersion": COGNIX_MODULE_REGISTRY_VERSION,
        "mode": "dry_run",
        "moduleId": module.get("id"),
        "displayName": module.get("displayName"),
        "status": module.get("activationState"),
        "allowedToActivate": allowed_to_activate,
        "humanApprovalRequired": True,
        "module": module,
        "steps": [
            {
                "id": "verify_manifest",
                "status": "complete",
                "detail": "Manifest declaratif present.",
            },
            {
                "id": "verify_dependencies",
                "status": "complete" if dependency_ready else "blocked",
                "detail": "Dependances resolues dans la registry locale.",
            },
            {
                "id": "verify_permissions",
                "status": "complete" if module.get("permissions") else "blocked",
                "detail": "Permissions declarees avant activation.",
            },
            {
                "id": "dry_run_guard",
                "status": "complete",
                "detail": "Aucune route, permission ou UI n'est modifiee pendant ce plan.",
            },
        ],
        "sideEffects": registry["sideEffects"],
    }
