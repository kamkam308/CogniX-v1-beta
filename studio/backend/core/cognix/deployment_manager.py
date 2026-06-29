# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX deployment and enterprise planning.

The deployment manager plans local, server, cloud, university, and enterprise
deployment targets. It never provisions infrastructure, starts containers,
opens network ports, writes secrets, changes DNS, deploys production, loads
models, or generates tokens.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COGNIX_DEPLOYMENT_MANAGER_VERSION = "cognix_deployment_manager_v1"
COGNIX_GPU_SCHEDULER_CONTRACT_VERSION = "cognix_gpu_scheduler_contract_v1"

WORKLOAD_PROFILES: dict[str, dict[str, Any]] = {
    "chat": {"queueId": "interactive_inference", "priority": 40, "defaultVramGb": 6.0, "maxConcurrentPerGpu": 2},
    "rag": {"queueId": "rag_indexing", "priority": 35, "defaultVramGb": 4.0, "maxConcurrentPerGpu": 2},
    "batch": {"queueId": "enterprise_throughput", "priority": 25, "defaultVramGb": 8.0, "maxConcurrentPerGpu": 1},
    "fine_tuning": {"queueId": "gpu_long_running", "priority": 15, "defaultVramGb": 12.0, "maxConcurrentPerGpu": 1},
    "cloud_training": {"queueId": "cloud_training", "priority": 10, "defaultVramGb": 0.0, "maxConcurrentPerGpu": 0},
}

DEPLOYMENT_TARGETS: list[dict[str, Any]] = [
    {
        "id": "local_desktop",
        "label": "Local desktop",
        "editions": ["free_local", "developer"],
        "targetType": "local",
        "runtimeAdapters": ["ollama", "llama-cpp", "transformers"],
        "supports": {
            "multiUser": False,
            "gpuScheduler": False,
            "moeServing": False,
            "autoscaling": False,
            "sso": False,
            "auditAdvanced": False,
            "offline": True,
        },
        "riskLevel": "low",
    },
    {
        "id": "personal_server",
        "label": "Personal server",
        "editions": ["developer", "business"],
        "targetType": "server",
        "runtimeAdapters": ["llama-cpp", "transformers"],
        "supports": {
            "multiUser": True,
            "gpuScheduler": False,
            "moeServing": False,
            "autoscaling": False,
            "sso": False,
            "auditAdvanced": True,
            "offline": True,
        },
        "riskLevel": "medium",
    },
    {
        "id": "on_prem_single_gpu",
        "label": "On-prem single GPU",
        "editions": ["business", "enterprise", "university"],
        "targetType": "on_premise",
        "runtimeAdapters": ["vllm", "transformers", "llama-cpp"],
        "supports": {
            "multiUser": True,
            "gpuScheduler": True,
            "moeServing": False,
            "autoscaling": False,
            "sso": True,
            "auditAdvanced": True,
            "offline": True,
        },
        "riskLevel": "high",
    },
    {
        "id": "on_prem_multi_gpu",
        "label": "On-prem multi GPU",
        "editions": ["enterprise", "university"],
        "targetType": "on_premise",
        "runtimeAdapters": ["vllm", "transformers"],
        "supports": {
            "multiUser": True,
            "gpuScheduler": True,
            "moeServing": True,
            "autoscaling": True,
            "sso": True,
            "auditAdvanced": True,
            "offline": True,
        },
        "riskLevel": "high",
    },
    {
        "id": "cloud_managed",
        "label": "Managed cloud",
        "editions": ["business", "enterprise"],
        "targetType": "cloud",
        "runtimeAdapters": ["cloud-openai-compatible", "vllm"],
        "supports": {
            "multiUser": True,
            "gpuScheduler": True,
            "moeServing": True,
            "autoscaling": True,
            "sso": True,
            "auditAdvanced": True,
            "offline": False,
        },
        "riskLevel": "high",
    },
    {
        "id": "university_lab",
        "label": "University lab",
        "editions": ["university", "enterprise"],
        "targetType": "education",
        "runtimeAdapters": ["vllm", "transformers", "llama-cpp"],
        "supports": {
            "multiUser": True,
            "gpuScheduler": True,
            "moeServing": False,
            "autoscaling": False,
            "sso": True,
            "auditAdvanced": True,
            "offline": True,
        },
        "riskLevel": "high",
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")


def _as_int(value: Any) -> int | None:
    parsed = _as_float(value)
    return int(parsed) if parsed is not None else None


def _gpu_devices_from_hardware(hardware: dict[str, Any]) -> list[dict[str, Any]]:
    gpu = _as_dict(hardware.get("gpu"))
    devices = [
        item for item in gpu.get("devices", []) if isinstance(item, dict)
    ]
    normalized: list[dict[str, Any]] = []
    for index, device in enumerate(devices):
        vram = _as_float(device.get("vramTotalGb") or device.get("memoryGb")) or 0.0
        name = str(device.get("name") or device.get("model") or f"GPU {index + 1}").strip()
        normalized.append(
            {
                "nodeId": f"local_gpu_{index + 1}",
                "name": name,
                "backend": gpu.get("backend") or hardware.get("deviceBackend") or "local",
                "vramTotalGb": round(vram, 2),
                "vramReservedGb": 0.0,
                "status": "available" if bool(gpu.get("available")) and vram > 0 else "unavailable",
                "source": "hardware_profile",
            }
        )
    return normalized


def _normalize_scheduler_nodes(
    *,
    hardware: dict[str, Any],
    gpu_nodes: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    raw_nodes = gpu_nodes if isinstance(gpu_nodes, list) and gpu_nodes else _gpu_devices_from_hardware(hardware)
    nodes: list[dict[str, Any]] = []
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            continue
        total = _as_float(node.get("vramTotalGb") or node.get("vramGb") or node.get("memoryGb")) or 0.0
        reserved = _as_float(node.get("vramReservedGb") or node.get("reservedGb")) or 0.0
        available = max(0.0, total - reserved)
        node_id = str(node.get("nodeId") or node.get("id") or f"gpu_node_{index + 1}").strip()[:160]
        nodes.append(
            {
                "nodeId": node_id,
                "name": str(node.get("name") or node_id).strip()[:160],
                "backend": str(node.get("backend") or node.get("runtimeBackend") or "unknown").strip()[:80],
                "status": str(node.get("status") or "available").strip().lower(),
                "vramTotalGb": round(total, 2),
                "vramReservedGb": round(min(reserved, total), 2),
                "vramAvailableGb": round(available, 2),
                "tenantId": str(node.get("tenantId") or "shared").strip()[:120],
                "source": str(node.get("source") or "provided").strip()[:80],
            }
        )
    return nodes


def _normalize_scheduler_workloads(workloads: list[dict[str, Any]] | None, expected_users: int) -> list[dict[str, Any]]:
    if not isinstance(workloads, list) or not workloads:
        workloads = [
            {"workloadType": "chat", "count": max(1, min(expected_users, 8))},
            {"workloadType": "rag", "count": 1 if expected_users >= 2 else 0},
        ]
    normalized: list[dict[str, Any]] = []
    for index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            continue
        workload_type = _normalize(workload.get("workloadType") or workload.get("type") or "chat")
        profile = WORKLOAD_PROFILES.get(workload_type, WORKLOAD_PROFILES["chat"])
        count = max(0, min(_as_int(workload.get("count")) or 1, 100_000))
        if count == 0:
            continue
        required_vram = _as_float(workload.get("requiredVramGb")) or float(profile["defaultVramGb"])
        normalized.append(
            {
                "workloadId": str(workload.get("workloadId") or workload.get("id") or f"workload_{index + 1}").strip()[:160],
                "workloadType": workload_type,
                "count": count,
                "requiredVramGb": round(required_vram, 2),
                "priority": _as_int(workload.get("priority")) or int(profile["priority"]),
                "queueId": str(workload.get("queueId") or profile["queueId"]).strip()[:120],
                "maxConcurrentPerGpu": int(profile["maxConcurrentPerGpu"]),
            }
        )
    return sorted(normalized, key = lambda item: int(item.get("priority") or 0), reverse = True)


def _admission_for_workload(workload: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    required_vram = _as_float(workload.get("requiredVramGb")) or 0.0
    available_nodes = [
        node
        for node in nodes
        if node.get("status") == "available" and (_as_float(node.get("vramAvailableGb")) or 0.0) >= required_vram
    ]
    max_per_gpu = max(0, int(workload.get("maxConcurrentPerGpu") or 0))
    admitted_capacity = len(available_nodes) * max_per_gpu
    requested = int(workload.get("count") or 0)
    admitted = min(requested, admitted_capacity) if max_per_gpu else 0
    overflow = max(0, requested - admitted)
    return {
        "workloadId": workload.get("workloadId"),
        "workloadType": workload.get("workloadType"),
        "queueId": workload.get("queueId"),
        "requestedCount": requested,
        "admittedCount": admitted,
        "overflowCount": overflow,
        "eligibleNodeIds": [node["nodeId"] for node in available_nodes],
        "status": "admitted" if overflow == 0 and admitted > 0 else "partial" if admitted > 0 else "blocked_capacity",
        "willEnqueueNow": False,
        "willReserveGpuNow": False,
    }


def _hardware_summary(hardware: dict[str, Any]) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb")) or 0.0
    available_gb = _as_float(memory.get("availableGb")) or 0.0
    gpu = _as_dict(hardware.get("gpu"))
    devices = [
        item for item in gpu.get("devices", []) if isinstance(item, dict)
    ]
    max_vram = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices),
        default = 0.0,
    )
    if bool(gpu.get("available")) and (len(devices) >= 2 or max_vram >= 24):
        tier = "enterprise_gpu_candidate"
    elif bool(gpu.get("available")) and max_vram >= 12:
        tier = "single_gpu_candidate"
    elif total_gb >= 32 and available_gb >= 12:
        tier = "cpu_server_candidate"
    elif total_gb <= 12 or available_gb < 5:
        tier = "small_local"
    else:
        tier = "local_only"
    return {
        "tier": tier,
        "deviceBackend": hardware.get("deviceBackend"),
        "cpuCount": hardware.get("cpuCount"),
        "memory": memory,
        "gpu": gpu,
        "gpuDeviceCount": len(devices),
        "maxVramGb": round(max_vram, 2),
    }


def _required_capabilities(
    *,
    edition: str,
    expected_users: int,
    target_type: str,
    data_sensitivity: str,
    requested_features: list[str],
) -> set[str]:
    required: set[str] = set()
    if expected_users > 1 or edition in {"business", "enterprise", "university"}:
        required.add("multiUser")
        required.add("auditAdvanced")
    if expected_users >= 10 or target_type in {"on_premise", "cloud", "education"}:
        required.add("gpuScheduler")
    if expected_users >= 50 or "autoscaling" in requested_features:
        required.add("autoscaling")
    if edition in {"business", "enterprise", "university"}:
        required.add("sso")
    if "moe" in requested_features or "moe_serving" in requested_features:
        required.add("moeServing")
    if data_sensitivity in {"restricted", "confidential", "education_records"} and target_type != "cloud":
        required.add("offline")
    return required


def _target_score(
    target: dict[str, Any],
    *,
    edition: str,
    target_type: str,
    expected_users: int,
    hardware: dict[str, Any],
    required: set[str],
) -> int:
    supports = _as_dict(target.get("supports"))
    score = sum(3 for capability in required if bool(supports.get(capability)))
    score -= sum(4 for capability in required if not bool(supports.get(capability)))
    if edition in target.get("editions", []):
        score += 8
    if target_type and target_type == target.get("targetType"):
        score += 8
    if target.get("id") == "local_desktop" and expected_users <= 1:
        score += 3
    if target.get("id") in {"on_prem_single_gpu", "on_prem_multi_gpu", "university_lab"}:
        gpu = _as_dict(hardware.get("gpu"))
        if bool(gpu.get("available")):
            score += 4
        else:
            score -= 4
    if target.get("id") == "cloud_managed" and target_type != "cloud":
        score -= 2
    return score


def _candidate_targets(
    *,
    edition: str,
    target_type: str,
    expected_users: int,
    hardware: dict[str, Any],
    required: set[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for target in DEPLOYMENT_TARGETS:
        supports = _as_dict(target.get("supports"))
        missing = sorted(capability for capability in required if not bool(supports.get(capability)))
        candidates.append(
            {
                "targetId": target.get("id"),
                "label": target.get("label"),
                "targetType": target.get("targetType"),
                "riskLevel": target.get("riskLevel"),
                "runtimeAdapters": target.get("runtimeAdapters", []),
                "supportedCapabilities": sorted(
                    capability for capability in required if bool(supports.get(capability))
                ),
                "missingCapabilities": missing,
                "score": _target_score(
                    target,
                    edition = edition,
                    target_type = target_type,
                    expected_users = expected_users,
                    hardware = hardware,
                    required = required,
                ),
                "willProvision": False,
            }
        )
    return sorted(candidates, key = lambda item: int(item.get("score") or 0), reverse = True)


def _scheduler_plan(selected: dict[str, Any], expected_users: int) -> dict[str, Any]:
    target_id = str(selected.get("targetId") or "none")
    scheduler = "single_local_queue"
    if target_id in {"on_prem_single_gpu", "university_lab"}:
        scheduler = "single_gpu_guarded_queue"
    elif target_id in {"on_prem_multi_gpu", "cloud_managed"}:
        scheduler = "gpu_pool_scheduler"
    return {
        "scheduler": scheduler,
        "maxConcurrentGenerations": 1 if expected_users <= 1 else 2 if expected_users < 10 else 4,
        "queueRequired": expected_users > 1,
        "workerQueueRequired": expected_users > 1 or target_id != "local_desktop",
        "gpuIsolationRequired": target_id in {"on_prem_single_gpu", "on_prem_multi_gpu", "university_lab"},
        "willStartWorkers": False,
    }


def _security_plan(
    *,
    selected: dict[str, Any],
    edition: str,
    data_sensitivity: str,
) -> dict[str, Any]:
    risk = str(selected.get("riskLevel") or "low")
    enterprise = edition in {"business", "enterprise", "university"} or risk == "high"
    return {
        "riskLevel": risk,
        "rbacRequired": enterprise,
        "ssoRequired": enterprise,
        "auditRequired": True,
        "advancedAuditRequired": enterprise,
        "secretsManagerRequired": enterprise,
        "networkIsolationRequired": data_sensitivity in {"restricted", "confidential", "education_records"},
        "humanApprovalRequired": True,
        "productionMergeAllowed": False,
    }


def build_deployment_target_registry() -> dict[str, Any]:
    targets = deepcopy(DEPLOYMENT_TARGETS)
    return {
        "deploymentManagerVersion": COGNIX_DEPLOYMENT_MANAGER_VERSION,
        "mode": "declarative_dry_run",
        "targets": targets,
        "summary": {
            "targetCount": len(targets),
            "localTargetCount": sum(1 for item in targets if item.get("targetType") == "local"),
            "serverTargetCount": sum(1 for item in targets if item.get("targetType") in {"server", "on_premise"}),
            "cloudTargetCount": sum(1 for item in targets if item.get("targetType") == "cloud"),
            "enterpriseTargetCount": sum(1 for item in targets if "enterprise" in item.get("editions", [])),
        },
        "globalPolicies": {
            "deploymentRequiresHumanApproval": True,
            "productionDeploymentFromPlannerAllowed": False,
            "secretsStayServerSide": True,
            "frontendCannotProvisionInfrastructure": True,
            "auditRequired": True,
        },
        "sideEffects": {
            "deployment": False,
            "infrastructureProvisioning": False,
            "serverStart": False,
            "containerStart": False,
            "dnsChange": False,
            "secretWrite": False,
            "networkExposure": False,
        },
    }


def build_gpu_scheduler_contract(
    *,
    username: str,
    hardware: dict[str, Any],
    deployment_plan: dict[str, Any] | None = None,
    gpu_nodes: list[dict[str, Any]] | None = None,
    workloads: list[dict[str, Any]] | None = None,
    expected_users: int | None = None,
    tenant_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = _as_dict(deployment_plan)
    request = _as_dict(plan.get("request"))
    user_count = max(1, min(int(expected_users or request.get("expectedUsers") or 1), 100_000))
    nodes = _normalize_scheduler_nodes(hardware = hardware, gpu_nodes = gpu_nodes)
    normalized_workloads = _normalize_scheduler_workloads(workloads, user_count)
    admissions = [_admission_for_workload(workload, nodes) for workload in normalized_workloads]
    available_nodes = [node for node in nodes if node.get("status") == "available"]
    total_vram = round(sum(_as_float(node.get("vramTotalGb")) or 0.0 for node in nodes), 2)
    available_vram = round(sum(_as_float(node.get("vramAvailableGb")) or 0.0 for node in available_nodes), 2)
    tenant = _as_dict(tenant_policy)
    isolation_mode = str(tenant.get("isolationMode") or "shared_queue").strip()[:80]
    per_tenant_limit = max(1, min(_as_int(tenant.get("maxConcurrentPerTenant")) or 2, 10_000))
    scheduler_plan = _as_dict(plan.get("schedulerPlan"))
    selected_target = _as_dict(plan.get("recommendedTarget"))
    target_id = str(selected_target.get("targetId") or "unknown")
    scheduler_declared = bool(scheduler_plan.get("gpuIsolationRequired") or scheduler_plan.get("scheduler") in {"gpu_pool_scheduler", "single_gpu_guarded_queue"})
    capacity_ready = bool(available_nodes and any(item.get("admittedCount", 0) for item in admissions))
    gates = [
        {
            "id": "deployment_plan_declared",
            "status": "pass" if plan else "warning",
            "severity": "info" if plan else "warning",
            "reason": "Deployment plan supplied." if plan else "Scheduler can plan from hardware only, but deployment plan is recommended.",
        },
        {
            "id": "gpu_nodes_available",
            "status": "pass" if available_nodes else "blocked",
            "severity": "info" if available_nodes else "error",
            "reason": "At least one GPU node is available." if available_nodes else "No available GPU node declared.",
            "detail": [node["nodeId"] for node in available_nodes],
        },
        {
            "id": "capacity_for_workloads",
            "status": "pass" if capacity_ready else "blocked",
            "severity": "info" if capacity_ready else "error",
            "reason": "GPU capacity can admit at least one workload." if capacity_ready else "GPU capacity is insufficient for declared workloads.",
        },
        {
            "id": "scheduler_declared",
            "status": "pass" if scheduler_declared else "warning",
            "severity": "info" if scheduler_declared else "warning",
            "reason": "Deployment plan declares a GPU scheduler." if scheduler_declared else "Deployment plan does not yet require a GPU scheduler.",
            "detail": scheduler_plan.get("scheduler"),
        },
        {
            "id": "tenant_isolation_declared",
            "status": "pass",
            "severity": "info",
            "reason": "Tenant isolation policy is declared for scheduler planning.",
            "detail": isolation_mode,
        },
        {
            "id": "human_approval_required",
            "status": "warning",
            "severity": "warning",
            "reason": "GPU scheduler activation requires human approval and a guarded executor.",
        },
    ]
    blocked_gate_ids = [str(item["id"]) for item in gates if item.get("severity") == "error"]
    warning_gate_ids = [str(item["id"]) for item in gates if item.get("severity") == "warning"]
    ready_for_admin_review = not blocked_gate_ids
    return {
        "deploymentManagerVersion": COGNIX_DEPLOYMENT_MANAGER_VERSION,
        "schedulerContractVersion": COGNIX_GPU_SCHEDULER_CONTRACT_VERSION,
        "mode": "gpu_scheduler_contract_dry_run",
        "username": username,
        "status": "ready_for_admin_review" if ready_for_admin_review else "blocked_capacity",
        "readyForAdminReview": ready_for_admin_review,
        "readyForSchedulerActivation": False,
        "target": {
            "targetId": target_id,
            "scheduler": scheduler_plan.get("scheduler") or "gpu_pool_scheduler",
            "expectedUsers": user_count,
        },
        "gpuPool": {
            "nodeCount": len(nodes),
            "availableNodeCount": len(available_nodes),
            "totalVramGb": total_vram,
            "availableVramGb": available_vram,
            "nodes": nodes,
        },
        "workloads": normalized_workloads,
        "admissionPlan": {
            "admissions": admissions,
            "totalRequested": sum(int(item.get("requestedCount") or 0) for item in admissions),
            "totalAdmitted": sum(int(item.get("admittedCount") or 0) for item in admissions),
            "totalOverflow": sum(int(item.get("overflowCount") or 0) for item in admissions),
            "willReserveGpuNow": False,
            "willEnqueueNow": False,
        },
        "queuePlan": {
            "queueIds": sorted({str(item.get("queueId")) for item in normalized_workloads if item.get("queueId")}),
            "workerQueueRequired": True,
            "workerStartAllowed": False,
            "schedulerActivationAllowed": False,
        },
        "tenantIsolation": {
            "mode": isolation_mode,
            "maxConcurrentPerTenant": per_tenant_limit,
            "crossTenantMemorySharingAllowed": False,
            "crossUserReadAllowed": False,
            "perTenantAuditRequired": True,
        },
        "gates": gates,
        "summary": {
            "blockedGateIds": blocked_gate_ids,
            "warningGateIds": warning_gate_ids,
            "targetId": target_id,
            "capacityReady": capacity_ready,
        },
        "blockedActions": [
            {
                "id": "scheduler_activation",
                "reason": "This contract does not start or enable the GPU scheduler.",
            },
            {
                "id": "gpu_reservation",
                "reason": "No GPU memory is reserved during dry-run planning.",
            },
            {
                "id": "job_enqueue",
                "reason": "No inference, RAG, or training jobs are enqueued by this contract.",
            },
            {
                "id": "worker_start",
                "reason": "No worker process is started by this contract.",
            },
        ],
        "sideEffects": {
            "schedulerActivation": False,
            "gpuReservation": False,
            "jobEnqueue": False,
            "workerStart": False,
            "serverStart": False,
            "containerStart": False,
            "modelLoad": False,
            "generation": False,
            "secretRead": False,
            "networkCall": False,
            "auditWrite": False,
        },
    }


def build_deployment_plan(
    *,
    username: str,
    objective: str,
    hardware: dict[str, Any],
    recommendation: dict[str, Any],
    target_type: str | None = None,
    edition: str | None = None,
    expected_users: int | None = None,
    data_sensitivity: str | None = None,
    requested_features: list[str] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_target_type = _normalize(target_type) or "local"
    normalized_edition = _normalize(edition) or "developer"
    normalized_sensitivity = _normalize(data_sensitivity) or "internal"
    features = [_normalize(item) for item in requested_features or [] if _normalize(item)]
    user_count = max(1, min(int(expected_users or 1), 100_000))
    required = _required_capabilities(
        edition = normalized_edition,
        expected_users = user_count,
        target_type = normalized_target_type,
        data_sensitivity = normalized_sensitivity,
        requested_features = features,
    )
    candidates = _candidate_targets(
        edition = normalized_edition,
        target_type = normalized_target_type,
        expected_users = user_count,
        hardware = hardware,
        required = required,
    )
    selected = candidates[0] if candidates else {}
    hardware_summary = _hardware_summary(hardware)
    security = _security_plan(
        selected = selected,
        edition = normalized_edition,
        data_sensitivity = normalized_sensitivity,
    )
    scheduler = _scheduler_plan(selected, user_count)
    warnings: list[str] = []
    if selected.get("missingCapabilities"):
        warnings.append("Cible recommandee avec capacites manquantes: garder un plan pilote avant production.")
    if normalized_target_type in {"on_premise", "cloud"} and not bool(_as_dict(hardware.get("gpu")).get("available")):
        warnings.append("Aucun GPU local visible: valider le serveur cible avant d'activer vLLM ou MoE.")
    if not isinstance(latest_benchmark_run, dict):
        warnings.append("Benchmark absent: mesurer la machine ou le serveur cible avant dimensionnement.")
    if normalized_sensitivity in {"restricted", "confidential", "education_records"} and selected.get("targetType") == "cloud":
        warnings.append("Donnees sensibles avec cible cloud: verifier DPA, region, chiffrement et SSO.")
    if str(recommendation.get("readiness") or "") not in {"ready", "ready_with_caution"}:
        warnings.append("Runtime local pas encore pret: le plan de deploiement reste preparatoire.")

    return {
        "deploymentManagerVersion": COGNIX_DEPLOYMENT_MANAGER_VERSION,
        "mode": "dry_run",
        "username": username,
        "objectiveExcerpt": " ".join((objective or "").split())[:500],
        "request": {
            "targetType": normalized_target_type,
            "edition": normalized_edition,
            "expectedUsers": user_count,
            "dataSensitivity": normalized_sensitivity,
            "requestedFeatures": features,
        },
        "hardwareSummary": hardware_summary,
        "recommendedTarget": selected,
        "candidateTargets": candidates,
        "requiredCapabilities": sorted(required),
        "runtimePlan": {
            "providerType": recommendation.get("providerType"),
            "providerName": recommendation.get("providerName"),
            "modelId": recommendation.get("modelId"),
            "readiness": recommendation.get("readiness"),
            "compatibleAdapterIds": selected.get("runtimeAdapters", []),
            "willStartRuntime": False,
        },
        "schedulerPlan": scheduler,
        "securityPlan": security,
        "monitoringPlan": {
            "healthChecksRequired": True,
            "auditLogStreamingRequired": security["advancedAuditRequired"],
            "hardwareTelemetryRequired": selected.get("targetId") != "local_desktop",
            "costTrackingRequired": selected.get("targetType") == "cloud",
            "willStartMonitoring": False,
        },
        "readinessChecks": [
            {"id": "hardware_profile", "status": "complete", "required": True},
            {
                "id": "benchmark",
                "status": "complete" if isinstance(latest_benchmark_run, dict) else "recommended",
                "required": selected.get("targetId") != "local_desktop",
            },
            {"id": "rbac_policy", "status": "planned", "required": security["rbacRequired"]},
            {"id": "secrets_manager", "status": "planned", "required": security["secretsManagerRequired"]},
            {"id": "deployment_approval", "status": "blocked", "required": True},
        ],
        "blockedActions": [
            {
                "id": "infrastructure_provisioning",
                "reason": "Le planner ne cree aucun serveur, VM, container ou ressource cloud.",
            },
            {
                "id": "network_exposure",
                "reason": "Aucun port public, DNS ou tunnel n'est ouvert par ce planner.",
            },
            {
                "id": "production_deployment",
                "reason": "Le deploiement production exige validation humaine et executor separe.",
            },
            {
                "id": "secret_write",
                "reason": "Aucun secret SSO/cloud/provider n'est lu ni ecrit ici.",
            },
        ],
        "warnings": warnings,
        "reason": "Plan de deploiement CogniX prepare sans provisionnement ni execution.",
        "sideEffects": {
            "deployment": False,
            "infrastructureProvisioning": False,
            "serverStart": False,
            "containerStart": False,
            "dnsChange": False,
            "secretRead": False,
            "secretWrite": False,
            "networkExposure": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "workerStart": False,
        },
    }
