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
