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


def build_api_surface_contract(registered_routes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    registered = _registered_route_keys(registered_routes)
    endpoints = [_endpoint_record(endpoint, registered) for endpoint in RECOMMENDED_ENDPOINTS]
    exact = [item["path"] for item in endpoints if item["status"] == "exact"]
    equivalent = [item["path"] for item in endpoints if item["status"] == "equivalent"]
    planned = [item["path"] for item in endpoints if item["status"] == "planned"]
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
        },
        "coverage": {
            "exactEndpoints": exact,
            "equivalentEndpoints": equivalent,
            "plannedEndpoints": planned,
            "missingEndpoints": planned,
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
