# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX internal API surface contract.

This maps the roadmap Section 28 endpoints to the currently registered FastAPI
routes. It is a read-only compatibility contract; it does not register routes
or execute any endpoint.
"""

from __future__ import annotations

from typing import Any, Iterable


COGNIX_API_SURFACE_CONTRACT_VERSION = "cognix_api_surface_contract_v1"
PRODUCT_NAVIGATION_ROUTE_SOURCE = "v2_section_41_recommended_routes"

RECOMMENDED_ENDPOINTS: list[dict[str, Any]] = [
    {
        "method": "POST",
        "path": "/api/chat",
        "ownerService": "Backend API",
        "purpose": "non_streaming_chat",
        "equivalentRoutes": ["/api/inference/chat/completions", "/v1/chat/completions"],
    },
    {
        "method": "POST",
        "path": "/api/chat/stream",
        "ownerService": "Backend API",
        "purpose": "streaming_chat",
        "equivalentRoutes": ["/api/inference/generate/stream", "/api/inference/chat/completions", "/v1/chat/completions"],
    },
    {
        "method": "POST",
        "path": "/api/router/classify",
        "ownerService": "Orchestrator Service",
        "purpose": "domain_classification",
        "equivalentRoutes": ["/api/cognix/router/classify"],
    },
    {
        "method": "POST",
        "path": "/api/models/install",
        "ownerService": "Model Runtime Adapter",
        "purpose": "model_install_planning",
        "equivalentRoutes": ["/api/cognix/models/install-contract"],
    },
    {
        "method": "POST",
        "path": "/api/models/load",
        "ownerService": "Model Runtime Adapter",
        "purpose": "model_load",
        "equivalentRoutes": ["/api/inference/load"],
    },
    {
        "method": "POST",
        "path": "/api/models/unload",
        "ownerService": "Model Runtime Adapter",
        "purpose": "model_unload",
        "equivalentRoutes": ["/api/inference/unload"],
    },
    {
        "method": "GET",
        "path": "/api/models/installed",
        "ownerService": "Model Runtime Adapter",
        "purpose": "installed_model_inventory",
        "equivalentRoutes": ["/api/models/list", "/api/models/local", "/api/cognix/models/registry"],
    },
    {
        "method": "GET",
        "path": "/api/hardware/profile",
        "ownerService": "Orchestrator Service",
        "purpose": "hardware_profile",
        "equivalentRoutes": ["/api/cognix/hardware/profile", "/api/system/hardware"],
    },
    {
        "method": "POST",
        "path": "/api/benchmark/run",
        "ownerService": "Orchestrator Service",
        "purpose": "benchmark_run",
        "equivalentRoutes": ["/api/cognix/benchmark/run"],
    },
    {
        "method": "POST",
        "path": "/api/rag/index",
        "ownerService": "RAG Service",
        "purpose": "rag_indexing",
        "equivalentRoutes": ["/api/cognix/rag/indexing-plan", "/api/rag/knowledge-bases/{kb_id}/documents", "/api/rag/projects/{project_id}/documents"],
    },
    {
        "method": "POST",
        "path": "/api/fine-tune/start",
        "ownerService": "Fine-tuning Service",
        "purpose": "fine_tuning_start",
        "equivalentRoutes": ["/api/train/start", "/api/cognix/fine-tuning/plan", "/api/cognix/fine-tuning/cloud-handoff-plan"],
    },
    {
        "method": "GET",
        "path": "/api/fine-tune/jobs",
        "ownerService": "Fine-tuning Service",
        "purpose": "fine_tuning_jobs",
        "equivalentRoutes": ["/api/train/runs", "/api/train/status"],
    },
    {
        "method": "POST",
        "path": "/api/tools/execute",
        "ownerService": "Tool Service",
        "purpose": "guarded_tool_execution",
        "equivalentRoutes": ["/api/cognix/tools/execution-handoff", "/api/cognix/tools/plan"],
    },
    {
        "method": "GET",
        "path": "/api/audit/logs",
        "ownerService": "Backend API",
        "purpose": "admin_audit_log_read",
        "equivalentRoutes": ["/api/cognix/admin/audit-logs"],
    },
    {
        "method": "POST",
        "path": "/api/codex/feature-request",
        "ownerService": "Codex Agent Service",
        "purpose": "codex_feature_pipeline",
        "equivalentRoutes": ["/api/cognix/codex/pipeline-plan", "/api/cognix/codex/preview-contract", "/api/cognix/codex/approval-gate"],
    },
]

PRODUCT_NAVIGATION_ROUTES: list[dict[str, Any]] = [
    {"path": "/pulse", "equivalentRoutes": ["/api/cognix/pulse"]},
    {"path": "/library", "equivalentRoutes": ["/api/cognix/library"]},
    {"path": "/codex", "equivalentRoutes": ["/api/cognix/codex/pipeline-plan"]},
    {"path": "/scheduled", "equivalentRoutes": ["/api/cognix/scheduled-tasks"]},
    {"path": "/images", "equivalentRoutes": ["/api/cognix/images"]},
    {"path": "/apps", "equivalentRoutes": ["/api/cognix/apps"]},
    {"path": "/gpts", "equivalentRoutes": ["/api/cognix/gpts"]},
    {"path": "/admin", "equivalentRoutes": ["/api/cognix/admin/dashboard"]},
    {"path": "/admin/users", "equivalentRoutes": ["/api/cognix/admin/users"]},
    {"path": "/admin/chats", "equivalentRoutes": ["/api/cognix/admin/chats"]},
    {"path": "/admin/activity", "equivalentRoutes": ["/api/cognix/admin/activity"]},
    {"path": "/admin/limits", "equivalentRoutes": ["/api/cognix/admin/limits"]},
    {"path": "/admin/permissions", "equivalentRoutes": ["/api/cognix/admin/permissions/matrix"]},
    {"path": "/admin/approvals", "equivalentRoutes": ["/api/cognix/admin/approvals"]},
    {"path": "/admin/banned", "equivalentRoutes": ["/api/cognix/admin/banned", "/api/cognix/admin/bans"]},
    {"path": "/admin/security-threats", "equivalentRoutes": ["/api/cognix/admin/security-threats"]},
    {"path": "/admin/token-usage", "equivalentRoutes": ["/api/cognix/admin/usage"]},
    {"path": "/admin/model-usage", "equivalentRoutes": ["/api/cognix/admin/usage"]},
    {"path": "/admin/projects", "equivalentRoutes": ["/api/projects", "/api/cognix/admin/database-blueprint"]},
    {"path": "/admin/settings", "equivalentRoutes": ["/api/cognix/admin/api-surface-contract"]},
    {"path": "/admin/system-health", "equivalentRoutes": ["/api/cognix/admin/system-health"]},
    {"path": "/chat", "equivalentRoutes": ["/api/inference/chat/completions", "/v1/chat/completions"]},
    {"path": "/chat/enterprise", "equivalentRoutes": ["/api/cognix/admin/chats/policy", "/api/cognix/admin/chats"]},
    {"path": "/projects/:id/collaboration", "equivalentRoutes": ["/api/cognix/chat-project-bridge/links", "/api/projects/{project_id}"]},
    {"path": "/projects/:id/skills", "equivalentRoutes": ["/api/cognix/projects/{project_id}/skills", "/api/cognix/skills/marketplace", "/api/cognix/memory/skills"]},
    {"path": "/projects/:id/directives", "equivalentRoutes": ["/api/cognix/projects/{project_id}/directives"]},
    {"path": "/cowork", "equivalentRoutes": ["/api/cognix/admin/approvals", "/api/cognix/command-palette/plan"]},
]


def _normalize_method(value: Any) -> str:
    return str(value or "").strip().upper()


def _route_key(method: Any, path: Any) -> str:
    return f"{_normalize_method(method)} {str(path or '').strip()}"


def _registered_route_keys(registered_routes: Iterable[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for route in registered_routes:
        path = str(route.get("path") or "").strip()
        methods = route.get("methods") or []
        for method in methods:
            normalized = _normalize_method(method)
            if normalized in {"HEAD", "OPTIONS"}:
                continue
            keys.add(_route_key(normalized, path))
    return keys


def _registered_paths(registered_routes: Iterable[dict[str, Any]]) -> set[str]:
    return {str(route.get("path") or "").strip() for route in registered_routes if str(route.get("path") or "").strip()}


def _endpoint_record(endpoint: dict[str, Any], registered: set[str]) -> dict[str, Any]:
    method = str(endpoint["method"])
    expected_key = _route_key(method, endpoint["path"])
    equivalent_keys = [_route_key(method, path) for path in endpoint.get("equivalentRoutes") or []]
    matched_exact = expected_key in registered
    matched_equivalent = [key for key in equivalent_keys if key in registered]
    status = "exact" if matched_exact else "equivalent" if matched_equivalent else "planned"
    return {
        "method": method,
        "path": endpoint["path"],
        "purpose": endpoint["purpose"],
        "ownerService": endpoint["ownerService"],
        "status": status,
        "matchedRoute": expected_key if matched_exact else matched_equivalent[0] if matched_equivalent else None,
        "equivalentRoutes": equivalent_keys,
        "frontendDirectModelCallAllowed": False,
        "routeRegistrationAllowedHere": False,
    }


def _product_route_record(route: dict[str, Any], registered_paths: set[str]) -> dict[str, Any]:
    path = str(route["path"])
    equivalent_routes = [str(item) for item in route.get("equivalentRoutes") or []]
    matched_exact = path in registered_paths
    matched_equivalent = [item for item in equivalent_routes if item in registered_paths]
    status = "exact" if matched_exact else "equivalent" if matched_equivalent else "planned"
    return {
        "path": path,
        "status": status,
        "matchedRoute": path if matched_exact else matched_equivalent[0] if matched_equivalent else None,
        "equivalentRoutes": equivalent_routes,
        "sourceOfTruth": PRODUCT_NAVIGATION_ROUTE_SOURCE,
        "frontendDirectModelCallAllowed": False,
        "routeRegistrationAllowedHere": False,
    }


def build_api_surface_contract(registered_routes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    registered_routes = list(registered_routes)
    registered = _registered_route_keys(registered_routes)
    registered_paths = _registered_paths(registered_routes)
    endpoints = [_endpoint_record(endpoint, registered) for endpoint in RECOMMENDED_ENDPOINTS]
    product_routes = [_product_route_record(route, registered_paths) for route in PRODUCT_NAVIGATION_ROUTES]
    exact = [item["path"] for item in endpoints if item["status"] == "exact"]
    equivalent = [item["path"] for item in endpoints if item["status"] == "equivalent"]
    planned = [item["path"] for item in endpoints if item["status"] == "planned"]
    product_exact = [item["path"] for item in product_routes if item["status"] == "exact"]
    product_equivalent = [item["path"] for item in product_routes if item["status"] == "equivalent"]
    product_planned = [item["path"] for item in product_routes if item["status"] == "planned"]
    return {
        "apiSurfaceContractVersion": COGNIX_API_SURFACE_CONTRACT_VERSION,
        "mode": "api_surface_contract_read_only",
        "sourceOfTruth": "roadmap_section_28",
        "summary": {
            "recommendedEndpointCount": len(endpoints),
            "exactEndpointCount": len(exact),
            "equivalentEndpointCount": len(equivalent),
            "plannedEndpointCount": len(planned),
            "registeredRouteCount": len(registered),
            "readyForMvpApi": not planned,
            "productRouteCount": len(product_routes),
            "coveredProductRouteCount": len(product_exact) + len(product_equivalent),
            "plannedProductRouteCount": len(product_planned),
        },
        "coverage": {
            "exactEndpoints": exact,
            "equivalentEndpoints": equivalent,
            "plannedEndpoints": planned,
            "missingEndpoints": planned,
        },
        "productNavigationContract": {
            "sourceOfTruth": PRODUCT_NAVIGATION_ROUTE_SOURCE,
            "routes": product_routes,
            "coverage": {
                "exactRoutes": product_exact,
                "equivalentRoutes": product_equivalent,
                "plannedRoutes": product_planned,
                "missingRoutes": product_planned,
                "readyForV2Navigation": not product_planned,
            },
        },
        "endpoints": endpoints,
        "policies": {
            "frontendDirectModelCallAllowed": False,
            "orchestratorRequiredForGeneration": True,
            "routeRegistrationAllowedHere": False,
            "compatibilityAliasesAllowed": True,
            "destructiveToolExecuteRequiresHandoff": True,
        },
        "sideEffects": {
            "routeRegistration": False,
            "apiMutation": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "trainingJob": False,
            "auditWrite": False,
        },
    }
