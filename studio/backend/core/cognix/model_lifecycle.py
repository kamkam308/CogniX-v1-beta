# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native model lifecycle planning.

The lifecycle planner is the stable backend contract for model packs, installs,
loads, unloads, runtime choice, and cache residency. It does not download,
install, load, unload, start a server, or generate tokens; it only returns the
auditable plan that a future guarded executor can follow.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.cognix import registry as cognix_registry


COGNIX_MODEL_LIFECYCLE_VERSION = "cognix_model_lifecycle_v1"
COGNIX_MODEL_INSTALL_CONTRACT_VERSION = "cognix_model_install_contract_v1"
COGNIX_MODEL_RESIDENCY_CONTRACT_VERSION = "cognix_model_residency_contract_v1"


MODEL_PACKS: list[dict[str, Any]] = [
    {
        "packId": "cognix-general-local",
        "modelId": "cognix-general-3b-q4",
        "label": "CogniX General 3B Q4",
        "domain": "general",
        "role": "generalist",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 3.6,
        "estimatedStorageGb": 2.4,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_general_3b_q4",
        "loadActionId": "load_cognix_general_3b_q4",
        "priorityDomains": ["general", "education", "research"],
        "tags": ["local", "small", "generalist"],
    },
    {
        "packId": "cognix-code-local",
        "modelId": "cognix-code-4b-q4",
        "label": "CogniX Code 4B Q4",
        "domain": "code",
        "role": "code_expert",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 4.4,
        "estimatedStorageGb": 3.2,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_code_4b_q4",
        "loadActionId": "load_cognix_code_4b_q4",
        "priorityDomains": ["code", "developer"],
        "tags": ["local", "small", "code"],
    },
    {
        "packId": "cognix-maths-local",
        "modelId": "cognix-maths-3b-q4",
        "label": "CogniX Maths 3B Q4",
        "domain": "maths",
        "role": "math_expert",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 3.8,
        "estimatedStorageGb": 2.6,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_maths_3b_q4",
        "loadActionId": "load_cognix_maths_3b_q4",
        "priorityDomains": ["maths", "math", "mathematiques"],
        "tags": ["local", "small", "maths"],
    },
    {
        "packId": "cognix-physique-local",
        "modelId": "cognix-physique-3b-q4",
        "label": "CogniX Physique 3B Q4",
        "domain": "physique",
        "role": "physics_expert",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 3.8,
        "estimatedStorageGb": 2.7,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_physique_3b_q4",
        "loadActionId": "load_cognix_physique_3b_q4",
        "priorityDomains": ["physique", "physics", "science"],
        "tags": ["local", "small", "science"],
    },
    {
        "packId": "cognix-business-local",
        "modelId": "cognix-business-3b-q4",
        "label": "CogniX Business 3B Q4",
        "domain": "business",
        "role": "business_expert",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 3.7,
        "estimatedStorageGb": 2.5,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_business_3b_q4",
        "loadActionId": "load_cognix_business_3b_q4",
        "priorityDomains": ["business", "crm", "sales"],
        "tags": ["local", "small", "business"],
    },
    {
        "packId": "cognix-research-local",
        "modelId": "cognix-research-3b-q4",
        "label": "CogniX Research 3B Q4",
        "domain": "research",
        "role": "research_expert",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 3.9,
        "estimatedStorageGb": 2.8,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_research_3b_q4",
        "loadActionId": "load_cognix_research_3b_q4",
        "priorityDomains": ["research", "recherche", "veille"],
        "tags": ["local", "small", "research"],
    },
    {
        "packId": "cognix-education-local",
        "modelId": "cognix-education-3b-q4",
        "label": "CogniX Education 3B Q4",
        "domain": "education",
        "role": "education_expert",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 3.6,
        "estimatedStorageGb": 2.4,
        "installSource": "cognix_pack_catalog",
        "installActionId": "install_cognix_education_3b_q4",
        "loadActionId": "load_cognix_education_3b_q4",
        "priorityDomains": ["education", "school", "university", "cours"],
        "tags": ["local", "small", "education"],
    },
    {
        "packId": "ollama-qwen-4b-local",
        "modelId": cognix_registry.COGNIX_DEFAULT_OLLAMA_MODEL_ID,
        "label": "Qwen 4B local via Ollama",
        "domain": "general",
        "role": "local_generalist",
        "runtimeAdapterId": "ollama",
        "providerType": "ollama",
        "format": "ollama_manifest",
        "quantization": "Q4/Q5 managed by Ollama",
        "estimatedRamGb": 4.6,
        "estimatedStorageGb": 3.5,
        "installSource": "ollama_catalog",
        "installActionId": "ollama_pull_qwen_4b",
        "loadActionId": "select_ollama_qwen_4b",
        "priorityDomains": ["general", "code", "education", "research"],
        "tags": ["local", "ollama", "qwen", "small"],
    },
    {
        "packId": "qwen-14b-local",
        "modelId": "qwen-14b-q4",
        "label": "Qwen 14B Q4",
        "domain": "general",
        "role": "larger_generalist",
        "runtimeAdapterId": "llama-cpp",
        "providerType": "local_gguf",
        "format": "gguf",
        "quantization": "Q4",
        "estimatedRamGb": 12.4,
        "estimatedStorageGb": 9.4,
        "installSource": "advanced_pack_catalog",
        "installActionId": "install_qwen_14b_q4",
        "loadActionId": "load_qwen_14b_q4",
        "priorityDomains": ["general", "research", "business"],
        "tags": ["local", "advanced", "qwen"],
    },
    {
        "packId": "glm-70b-reference",
        "modelId": "glm-70b-q4",
        "label": "GLM 70B Q4",
        "domain": "general",
        "role": "enterprise_reference",
        "runtimeAdapterId": "vllm",
        "providerType": "server_gpu",
        "format": "safetensors_or_gguf",
        "quantization": "Q4",
        "estimatedRamGb": 58.0,
        "estimatedStorageGb": 42.0,
        "installSource": "enterprise_reference",
        "installActionId": "install_glm_70b_q4",
        "loadActionId": "load_glm_70b_q4",
        "priorityDomains": ["enterprise", "research"],
        "referenceOnly": True,
        "tags": ["server", "large", "reference"],
    },
    {
        "packId": "glm-700b-reference",
        "modelId": "glm-700b",
        "label": "GLM 700B",
        "domain": "general",
        "role": "cluster_reference",
        "runtimeAdapterId": "vllm",
        "providerType": "cluster",
        "format": "safetensors",
        "quantization": "mixed",
        "estimatedRamGb": 520.0,
        "estimatedStorageGb": 700.0,
        "installSource": "enterprise_reference",
        "installActionId": "install_glm_700b",
        "loadActionId": "load_glm_700b",
        "priorityDomains": ["enterprise"],
        "referenceOnly": True,
        "tags": ["cluster", "huge", "reference"],
    },
]


DOMAIN_ALIASES: dict[str, str] = {
    "general": "general",
    "chat": "general",
    "code": "code",
    "dev": "code",
    "developer": "code",
    "software": "code",
    "math": "maths",
    "maths": "maths",
    "mathematiques": "maths",
    "physics": "physique",
    "physique": "physique",
    "science": "physique",
    "business": "business",
    "crm": "business",
    "sales": "business",
    "research": "research",
    "recherche": "research",
    "veille": "research",
    "education": "education",
    "school": "education",
    "university": "education",
    "cours": "education",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _objective_excerpt(value: Any) -> str:
    return " ".join(str(value or "").split())[:500]


def _stable_key(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:18]


def _hardware_tier(hardware: dict[str, Any]) -> str:
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb")) or 0.0
    available_gb = _as_float(memory.get("availableGb")) or 0.0
    gpu = _as_dict(hardware.get("gpu"))
    devices = [item for item in _as_list(gpu.get("devices")) if isinstance(item, dict)]
    max_vram = max(
        (_as_float(item.get("vramTotalGb")) or 0.0 for item in devices),
        default = 0.0,
    )
    if bool(gpu.get("available")) and (max_vram >= 16 or total_gb >= 32):
        return "powerful_local"
    if total_gb <= 12 or available_gb < 5:
        return "small_local"
    return "balanced_local"


def _availability_index(model_registry: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    models = _as_list(_as_dict(model_registry).get("models"))
    return {
        str(item.get("id")): item
        for item in models
        if isinstance(item, dict) and item.get("id")
    }


def _with_availability(pack: dict[str, Any], model_registry: dict[str, Any] | None) -> dict[str, Any]:
    record = deepcopy(pack)
    indexed = _availability_index(model_registry)
    model = indexed.get(str(record.get("modelId")))
    installed = bool(_as_dict(model).get("available"))
    source = _as_dict(model).get("source") or record.get("installSource")
    record["availability"] = {
        "installed": installed,
        "availableInRuntimeRegistry": bool(model),
        "providerId": _as_dict(model).get("providerId"),
        "providerType": _as_dict(model).get("providerType") or record.get("providerType"),
        "source": source,
        "status": "installed" if installed else "known_not_installed" if model else "catalog_planned",
    }
    record["willDownload"] = False
    record["willInstall"] = False
    record["willLoad"] = False
    return record


def _fit_for_pack(pack: dict[str, Any], hardware: dict[str, Any]) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    total_gb = _as_float(memory.get("totalGb"))
    available_gb = _as_float(memory.get("availableGb"))
    required = _as_float(pack.get("estimatedRamGb")) or 0.0
    if bool(pack.get("referenceOnly")):
        return {
            "status": "blocked",
            "estimatedRamGb": required,
            "reason": "Pack reference: reserve a une infrastructure serveur ou cluster.",
        }
    if total_gb is None or total_gb <= 0:
        return {
            "status": "unknown",
            "estimatedRamGb": required,
            "reason": "Memoire locale inconnue: validation materielle requise avant chargement.",
        }
    if total_gb < required:
        return {
            "status": "blocked",
            "estimatedRamGb": required,
            "reason": "RAM totale insuffisante pour ce pack modele.",
        }
    if available_gb is not None and available_gb < required:
        return {
            "status": "tight",
            "estimatedRamGb": required,
            "reason": "Compatible seulement apres liberation de memoire.",
        }
    return {
        "status": "ok",
        "estimatedRamGb": required,
        "reason": "Compatible avec le profil local actuel.",
    }


def _benchmark_fitness(latest_benchmark_run: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    benchmark = _as_dict(_as_dict(latest_benchmark_run).get("benchmark"))
    return {
        str(item.get("modelId")): item
        for item in _as_list(benchmark.get("modelFitness"))
        if isinstance(item, dict) and item.get("modelId")
    }


def _project_domain(project_type: str | None, classification: dict[str, Any], project_expert_plan: dict[str, Any]) -> str:
    direct = DOMAIN_ALIASES.get(_normalize(project_type))
    if direct:
        return direct
    expert_domain = DOMAIN_ALIASES.get(
        _normalize(_as_dict(project_expert_plan.get("primaryExpert")).get("domain"))
    )
    if expert_domain:
        return expert_domain
    return DOMAIN_ALIASES.get(_normalize(classification.get("selectedDomain")), "general")


def _requested_model(requested_model_id: str | None, project_expert_plan: dict[str, Any]) -> str | None:
    requested = str(requested_model_id or "").strip()
    if requested:
        return requested
    expert_model = _as_dict(_as_dict(project_expert_plan.get("primaryExpert")).get("selectedModel"))
    model_id = expert_model.get("modelId")
    return str(model_id) if model_id else None


def build_model_pack_registry(
    *,
    model_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observed_registry = model_registry if isinstance(model_registry, dict) else {}
    packs = [_with_availability(pack, observed_registry) for pack in MODEL_PACKS]
    return {
        "modelLifecycleVersion": COGNIX_MODEL_LIFECYCLE_VERSION,
        "mode": "declarative_dry_run",
        "packs": packs,
        "summary": {
            "packCount": len(packs),
            "installedCount": sum(1 for item in packs if item.get("availability", {}).get("installed")),
            "localPackCount": sum(1 for item in packs if item.get("providerType") in {"local_gguf", "ollama"}),
            "referenceOnlyCount": sum(1 for item in packs if item.get("referenceOnly")),
            "backendExecutorRequired": True,
        },
        "globalPolicies": {
            "frontendCannotDownloadModels": True,
            "frontendCannotLoadModelsDirectly": True,
            "installRequiresBackendAudit": True,
            "installContractRequired": True,
            "installContractVersion": COGNIX_MODEL_INSTALL_CONTRACT_VERSION,
            "residencyContractRequired": True,
            "residencyContractVersion": COGNIX_MODEL_RESIDENCY_CONTRACT_VERSION,
            "huggingFaceDownloadsRequireRevisionPin": True,
            "downloadsMustUseWorkerQueue": True,
            "loadRequiresLifecyclePlan": True,
            "cacheEvictionRequiresLifecyclePlan": True,
        },
        "sideEffects": {
            "modelDownload": False,
            "modelInstall": False,
            "modelLoad": False,
            "modelUnload": False,
            "runtimeMutation": False,
            "cacheMutation": False,
            "networkCall": False,
            "generation": False,
            "settingsWrite": False,
            "fileWrite": False,
        },
    }


def _is_hugging_face_source(source: str, provider_type: str, model_id: str) -> bool:
    normalized = _normalize(source)
    provider = _normalize(provider_type)
    return normalized in {"hf", "huggingface", "hugging_face", "huggingface_hub"} or provider in {
        "hf",
        "huggingface",
        "hugging_face",
        "hf_transformers",
        "transformers",
    } or "/" in model_id and provider not in {"ollama", "local_gguf"}


def _install_source_policy(
    *,
    source: str,
    provider_type: str,
    model_id: str,
    gated_model: bool,
) -> dict[str, Any]:
    if _is_hugging_face_source(source, provider_type, model_id):
        return {
            "sourceId": "huggingface_hub",
            "connector": "hugging-face",
            "networkRequired": True,
            "revisionPinRequired": True,
            "licenseReviewRequired": True,
            "checksumPolicyRequired": True,
            "gatedModelRequiresToken": gated_model,
            "allowedSecretRefs": ["hf_token"] if gated_model else [],
            "rawSecretReadAllowed": False,
            "termsMustBeAcceptedOutsidePlanner": True,
        }
    if _normalize(provider_type) == "ollama" or _normalize(source) == "ollama_catalog":
        return {
            "sourceId": "ollama_catalog",
            "connector": "ollama",
            "networkRequired": True,
            "revisionPinRequired": False,
            "licenseReviewRequired": False,
            "checksumPolicyRequired": True,
            "gatedModelRequiresToken": False,
            "allowedSecretRefs": [],
            "rawSecretReadAllowed": False,
            "termsMustBeAcceptedOutsidePlanner": False,
        }
    return {
        "sourceId": source or "cognix_pack_catalog",
        "connector": "cognix-model-pack",
        "networkRequired": True,
        "revisionPinRequired": False,
        "licenseReviewRequired": True,
        "checksumPolicyRequired": True,
        "gatedModelRequiresToken": gated_model,
        "allowedSecretRefs": [],
        "rawSecretReadAllowed": False,
        "termsMustBeAcceptedOutsidePlanner": True,
    }


def _contract_gate(
    gate_id: str,
    *,
    required: bool,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "required": required,
        "status": "pass" if passed else ("blocked" if required else "not_required"),
        "passed": passed,
        "reason": reason,
    }


def _target_from_lifecycle_or_external(
    *,
    lifecycle_plan: dict[str, Any],
    external_model: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(external_model, dict) and external_model.get("modelId"):
        return {
            "packId": external_model.get("packId") or f"external_{_stable_key(external_model.get('modelId'))}",
            "modelId": external_model.get("modelId"),
            "label": external_model.get("label") or external_model.get("modelId"),
            "providerType": external_model.get("providerType") or "hf_transformers",
            "format": external_model.get("format") or "hf_transformers",
            "installSource": external_model.get("source") or "huggingface_hub",
            "runtimeAdapterId": external_model.get("runtimeAdapterId") or "transformers",
            "estimatedRamGb": external_model.get("estimatedRamGb"),
            "estimatedStorageGb": external_model.get("estimatedStorageGb"),
            "availability": {"installed": False, "status": "external_contract_planned"},
            "fit": {"status": "unknown", "reason": "External model requires executor-side metadata validation."},
        }
    return deepcopy(_as_dict(lifecycle_plan.get("selectedPack")))


def build_model_install_contract(
    *,
    objective: str,
    lifecycle_plan: dict[str, Any],
    hardware: dict[str, Any] | None = None,
    external_model: dict[str, Any] | None = None,
    revision: str | None = None,
    license_id: str | None = None,
    license_accepted: bool = False,
    allow_network: bool = False,
    offline_required: bool = False,
    gated_model: bool = False,
    confirmation_id: str | None = None,
    request_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    target = _target_from_lifecycle_or_external(
        lifecycle_plan = lifecycle_plan,
        external_model = external_model,
    )
    model_id = str(target.get("modelId") or "")
    provider_type = str(target.get("providerType") or "")
    source = str(target.get("installSource") or target.get("source") or "")
    source_policy = _install_source_policy(
        source = source,
        provider_type = provider_type,
        model_id = model_id,
        gated_model = gated_model,
    )
    installed = bool(_as_dict(target.get("availability")).get("installed"))
    estimated_storage = _as_float(target.get("estimatedStorageGb"))
    estimated_ram = _as_float(target.get("estimatedRamGb"))
    network_required = bool(source_policy.get("networkRequired")) and not installed
    revision_required = bool(source_policy.get("revisionPinRequired"))
    license_required = bool(source_policy.get("licenseReviewRequired"))
    confirmation_required = network_required or license_required or gated_model
    gates = [
        _contract_gate(
            "target_model_declared",
            required = True,
            passed = bool(model_id),
            reason = "A model id must be selected before an install contract can be reviewed.",
        ),
        _contract_gate(
            "source_policy_declared",
            required = True,
            passed = bool(source_policy.get("sourceId")),
            reason = "Every install source must map to a CogniX source policy.",
        ),
        _contract_gate(
            "storage_estimate_present",
            required = True,
            passed = estimated_storage is not None and estimated_storage > 0,
            reason = "Disk reservation must be estimated before download.",
        ),
        _contract_gate(
            "hardware_fit_reviewed",
            required = True,
            passed = _as_dict(target.get("fit")).get("status") != "blocked",
            reason = "Hardware fit must not be blocked before install planning.",
        ),
        _contract_gate(
            "revision_pinned",
            required = revision_required,
            passed = (not revision_required) or bool(str(revision or "").strip()),
            reason = "Hugging Face downloads require a pinned revision for reproducibility.",
        ),
        _contract_gate(
            "license_reviewed",
            required = license_required,
            passed = (not license_required) or bool(license_accepted and str(license_id or "").strip()),
            reason = "Model license and usage terms must be reviewed before download.",
        ),
        _contract_gate(
            "network_allowed",
            required = network_required,
            passed = (not network_required) or bool(allow_network and not offline_required),
            reason = "Network downloads require explicit backend approval and cannot run in offline mode.",
        ),
        _contract_gate(
            "human_confirmation",
            required = confirmation_required,
            passed = (not confirmation_required) or bool(str(confirmation_id or "").strip()),
            reason = "Human confirmation is required before model download handoff.",
        ),
        _contract_gate(
            "checksum_policy_declared",
            required = True,
            passed = bool(source_policy.get("checksumPolicyRequired")),
            reason = "Executor must verify checksums or content hashes before marking an install complete.",
        ),
    ]
    blocked_gates = [gate["id"] for gate in gates if gate["required"] and not gate["passed"]]
    ready_for_download_review = not blocked_gates
    idempotency_key = f"cognix:{project_id or 'global'}:model_download:{_stable_key(model_id, revision, request_id)}"
    return {
        "installContractVersion": COGNIX_MODEL_INSTALL_CONTRACT_VERSION,
        "modelLifecycleVersion": lifecycle_plan.get("modelLifecycleVersion") or COGNIX_MODEL_LIFECYCLE_VERSION,
        "mode": "model_install_contract_dry_run",
        "contractId": f"model_install_{_stable_key(model_id, revision, request_id)}",
        "requestId": request_id,
        "objectiveExcerpt": _objective_excerpt(objective),
        "projectId": project_id,
        "targetModel": {
            "packId": target.get("packId"),
            "modelId": model_id,
            "label": target.get("label"),
            "providerType": provider_type,
            "format": target.get("format"),
            "runtimeAdapterId": target.get("runtimeAdapterId"),
            "revision": revision,
            "licenseId": license_id,
            "estimatedRamGb": estimated_ram,
            "estimatedStorageGb": estimated_storage,
            "installed": installed,
        },
        "sourcePolicy": source_policy,
        "status": "ready_for_download_review" if ready_for_download_review else "blocked_missing_gate",
        "readyForDownloadReview": ready_for_download_review,
        "readyForWorkerEnqueue": False,
        "downloadAllowedHere": False,
        "installAllowedHere": False,
        "gates": gates,
        "blockedWhen": sorted(set(blocked_gates + ["worker_enqueue_contract_required"])),
        "workerHandoff": {
            "jobType": "model_download" if network_required else "model_register",
            "queueId": "local_runtime",
            "idempotencyKey": idempotency_key,
            "requiresWorkerEnqueueContract": True,
            "willEnqueue": False,
            "willStartWorker": False,
        },
        "storagePlan": {
            "estimatedStorageGb": estimated_storage,
            "willReserveDisk": False,
            "willWriteFiles": False,
            "checksumVerificationRequired": True,
        },
        "policies": {
            "frontendCannotDownloadModels": True,
            "backendExecutorRequired": True,
            "humanApprovalRequiredBeforeDownload": True,
            "downloadsMustUseWorkerQueue": True,
            "idempotencyKeyRequired": True,
            "rawSecretReadAllowed": False,
            "rawPayloadStorageAllowed": False,
            "networkCallAllowedHere": False,
            "fileWriteAllowedHere": False,
        },
        "sideEffects": {
            "modelDownload": False,
            "modelInstall": False,
            "modelLoad": False,
            "networkCall": False,
            "fileWrite": False,
            "settingsWrite": False,
            "secretRead": False,
            "jobEnqueue": False,
            "workerStart": False,
        },
    }


def _unique_runtime_models(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        model_id = str(value or "").strip()
        if model_id and model_id not in seen:
            seen.add(model_id)
            out.append(model_id)
    return out


def _runtime_inventory(
    *,
    cache: dict[str, Any],
    runtime_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    cache_runtime = _as_dict(cache.get("runtime"))
    runtime = _as_dict(runtime_snapshot)
    active_model = str(runtime.get("activeModel") or cache_runtime.get("activeModel") or "").strip()
    loaded_models = _unique_runtime_models(
        [
            *_as_list(runtime.get("loadedModels")),
            *_as_list(cache_runtime.get("loadedModels")),
            active_model,
        ]
    )
    loading_models = _unique_runtime_models(
        [
            *_as_list(runtime.get("loadingModels")),
            *_as_list(cache_runtime.get("loadingModels")),
        ]
    )
    return {
        "activeModel": active_model or None,
        "loadedModels": loaded_models,
        "loadingModels": loading_models,
        "residentCount": len(loaded_models),
        "runtimeType": runtime.get("runtimeType") or cache_runtime.get("runtimeType") or "unknown",
        "runtimeError": runtime.get("error") or cache_runtime.get("error"),
    }


def _unload_candidates_for_residency(
    *,
    lifecycle_plan: dict[str, Any],
    cache: dict[str, Any],
    target_model_id: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    source_actions = [
        *_as_list(_as_dict(lifecycle_plan.get("unloadPlan")).get("actions")),
        *_as_list(cache.get("actions")),
        *_as_list(lifecycle_plan.get("selectedEvictions")),
        *_as_list(cache.get("selectedEvictions")),
    ]
    seen: set[str] = set()
    for item in source_actions:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or "")
        model_id = str(item.get("modelId") or "").strip()
        if not model_id or model_id == target_model_id or model_id in seen:
            continue
        if not (action_type.startswith("would_unload") or action_type in {"evict", "unload"}):
            continue
        seen.add(model_id)
        candidates.append(
            {
                "modelId": model_id,
                "type": action_type,
                "reason": item.get("reason"),
                "reasonCode": item.get("reasonCode"),
                "willUnload": False,
                "automatic": False,
            }
        )
    return candidates


def build_model_residency_contract(
    *,
    objective: str,
    lifecycle_plan: dict[str, Any],
    cache: dict[str, Any],
    runtime_snapshot: dict[str, Any] | None = None,
    confirmation_id: str | None = None,
    request_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    target = deepcopy(_as_dict(lifecycle_plan.get("selectedPack")))
    runtime_plan = _as_dict(lifecycle_plan.get("runtimePlan"))
    load_plan = _as_dict(lifecycle_plan.get("loadPlan"))
    compatibility = _as_dict(lifecycle_plan.get("compatibility"))
    cache_policy = _as_dict(cache.get("policy")) or _as_dict(_as_dict(lifecycle_plan.get("unloadPlan")).get("policy"))
    inventory = _runtime_inventory(cache = cache, runtime_snapshot = runtime_snapshot)

    model_id = str(target.get("modelId") or load_plan.get("modelId") or "").strip()
    runtime_adapter_id = str(
        target.get("runtimeAdapterId")
        or load_plan.get("runtimeAdapterId")
        or runtime_plan.get("adapterId")
        or ""
    ).strip()
    installed = bool(_as_dict(target.get("availability")).get("installed"))
    fit = _as_dict(target.get("fit")) or _as_dict(compatibility.get("fit"))
    fit_status = str(fit.get("status") or "unknown")
    loaded_models = set(str(item) for item in _as_list(inventory.get("loadedModels")))
    loading_models = set(str(item) for item in _as_list(inventory.get("loadingModels")))
    already_loaded = bool(model_id and model_id in loaded_models)
    currently_loading = bool(model_id and model_id in loading_models)
    load_required = bool(model_id and not already_loaded and not currently_loading and installed and fit_status != "blocked")
    unload_candidates = _unload_candidates_for_residency(
        lifecycle_plan = lifecycle_plan,
        cache = cache,
        target_model_id = model_id,
    )
    confirmation_required = load_required or bool(unload_candidates)
    gates = [
        _contract_gate(
            "target_model_selected",
            required = True,
            passed = bool(model_id),
            reason = "A target model must be selected before residency can be reviewed.",
        ),
        _contract_gate(
            "installed_before_load",
            required = not already_loaded,
            passed = already_loaded or installed,
            reason = "A model must be installed before it can become resident.",
        ),
        _contract_gate(
            "hardware_fit_allows_load",
            required = True,
            passed = fit_status != "blocked",
            reason = "Hardware fit cannot be blocked before runtime residency.",
        ),
        _contract_gate(
            "runtime_adapter_selected",
            required = True,
            passed = bool(runtime_adapter_id),
            reason = "Runtime adapter selection is required before load handoff.",
        ),
        _contract_gate(
            "cache_policy_available",
            required = True,
            passed = bool(cache_policy),
            reason = "Cache policy must be observed before load or unload planning.",
        ),
        _contract_gate(
            "human_confirmation",
            required = confirmation_required,
            passed = (not confirmation_required) or bool(str(confirmation_id or "").strip()),
            reason = "Human confirmation is required before any model residency mutation.",
        ),
        _contract_gate(
            "backend_executor_required",
            required = True,
            passed = True,
            reason = "Only a guarded backend executor may load or unload runtime models.",
        ),
    ]
    blocked_gates = [gate["id"] for gate in gates if gate["required"] and not gate["passed"]]
    if blocked_gates:
        status = "blocked_missing_gate"
    elif already_loaded:
        status = "already_resident"
    else:
        status = "ready_for_residency_review"

    idempotency_key = f"cognix:{project_id or 'global'}:model_residency:{_stable_key(model_id, request_id)}"
    return {
        "residencyContractVersion": COGNIX_MODEL_RESIDENCY_CONTRACT_VERSION,
        "modelLifecycleVersion": lifecycle_plan.get("modelLifecycleVersion") or COGNIX_MODEL_LIFECYCLE_VERSION,
        "mode": "model_residency_contract_dry_run",
        "contractId": f"model_residency_{_stable_key(model_id, request_id)}",
        "requestId": request_id,
        "objectiveExcerpt": _objective_excerpt(objective),
        "projectId": project_id,
        "targetModel": {
            "packId": target.get("packId"),
            "modelId": model_id,
            "label": target.get("label"),
            "providerType": target.get("providerType"),
            "format": target.get("format"),
            "runtimeAdapterId": runtime_adapter_id,
            "estimatedRamGb": _as_float(target.get("estimatedRamGb")),
            "installed": installed,
            "fitStatus": fit_status,
        },
        "status": status,
        "readyForResidencyReview": not blocked_gates,
        "readyForRuntimeMutation": False,
        "loadAllowedHere": False,
        "unloadAllowedHere": False,
        "gates": gates,
        "blockedWhen": sorted(set(blocked_gates)),
        "nextRequiredGate": "runtime_executor_handoff",
        "inventory": {
            "activeModel": inventory.get("activeModel"),
            "loadedModels": inventory.get("loadedModels", []),
            "loadingModels": inventory.get("loadingModels", []),
            "residentCount": inventory.get("residentCount", 0),
            "runtimeType": inventory.get("runtimeType"),
            "runtimeError": inventory.get("runtimeError"),
            "selectedModelInstalled": installed,
        },
        "transition": {
            "fromActiveModel": inventory.get("activeModel"),
            "toModel": model_id,
            "alreadyLoaded": already_loaded,
            "currentlyLoading": currently_loading,
            "loadRequired": load_required,
            "willLoad": False,
            "willUnload": False,
            "unloadCandidates": unload_candidates,
            "idempotencyKey": idempotency_key,
        },
        "executorHandoff": {
            "jobType": "model_residency_transition",
            "queueId": "local_runtime",
            "idempotencyKey": idempotency_key,
            "requiresExecutorContract": True,
            "willEnqueue": False,
            "willStartWorker": False,
        },
        "policies": {
            "frontendCannotLoadModelsDirectly": True,
            "backendExecutorRequired": True,
            "loadRequiresLifecyclePlan": True,
            "unloadRequiresCachePlan": True,
            "humanApprovalRequiredBeforeRuntimeMutation": True,
            "runtimeMutationAllowedHere": False,
            "auditRequiredBeforeExecution": True,
        },
        "sideEffects": {
            "modelDownload": False,
            "modelInstall": False,
            "modelLoad": False,
            "modelUnload": False,
            "runtimeMutation": False,
            "cacheMutation": False,
            "networkCall": False,
            "generation": False,
            "settingsWrite": False,
            "fileWrite": False,
            "jobEnqueue": False,
            "workerStart": False,
        },
    }


def _score_pack(
    *,
    pack: dict[str, Any],
    requested_model_id: str | None,
    target_domain: str,
    quality_priority: str,
    recommendation: dict[str, Any],
    fit: dict[str, Any],
    benchmark: dict[str, dict[str, Any]],
    offline_required: bool,
) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    model_id = str(pack.get("modelId") or "")
    pack_id = str(pack.get("packId") or "")
    if requested_model_id and _normalize(requested_model_id) in {_normalize(model_id), _normalize(pack_id)}:
        score += 120
        signals.append("requested_model")
    if pack.get("domain") == target_domain:
        score += 42
        signals.append("domain_match")
    elif target_domain in _as_list(pack.get("priorityDomains")):
        score += 28
        signals.append("priority_domain")
    elif pack.get("domain") == "general":
        score += 12
        signals.append("general_fallback")

    if model_id == recommendation.get("modelId"):
        score += 34
        signals.append("runtime_recommendation")
    if _as_dict(pack.get("availability")).get("installed"):
        score += 26
        signals.append("already_installed")

    fitness = benchmark.get(model_id)
    if fitness:
        score += int(fitness.get("stars") or 0) * 6
        signals.append("benchmark_fit")

    fit_status = fit.get("status")
    if fit_status == "ok":
        score += 24
        signals.append("memory_ok")
    elif fit_status == "tight":
        score += 8
        signals.append("memory_tight")
    elif fit_status == "blocked":
        score -= 140
        signals.append("memory_blocked")

    estimated_ram = _as_float(pack.get("estimatedRamGb")) or 0.0
    if quality_priority in {"speed", "fast", "rapide"}:
        score += max(0, int(14 - estimated_ram))
        signals.append("speed_priority")
    elif quality_priority in {"quality", "qualite", "deep"}:
        score += min(18, int(estimated_ram))
        signals.append("quality_priority")
    else:
        score += 10 if 3.0 <= estimated_ram <= 5.0 else 2
        signals.append("balanced_priority")

    if offline_required and not _as_dict(pack.get("availability")).get("installed"):
        score -= 24
        signals.append("offline_not_installed")
    return score, signals


def _candidate_record(
    *,
    pack: dict[str, Any],
    score: int,
    signals: list[str],
    fit: dict[str, Any],
) -> dict[str, Any]:
    return {
        "packId": pack.get("packId"),
        "modelId": pack.get("modelId"),
        "label": pack.get("label"),
        "domain": pack.get("domain"),
        "role": pack.get("role"),
        "runtimeAdapterId": pack.get("runtimeAdapterId"),
        "providerType": pack.get("providerType"),
        "format": pack.get("format"),
        "quantization": pack.get("quantization"),
        "estimatedRamGb": pack.get("estimatedRamGb"),
        "estimatedStorageGb": pack.get("estimatedStorageGb"),
        "availability": pack.get("availability"),
        "fit": fit,
        "score": score,
        "selectionSignals": signals,
        "referenceOnly": bool(pack.get("referenceOnly")),
        "willDownload": False,
        "willInstall": False,
        "willLoad": False,
    }


def _install_plan(
    *,
    selected: dict[str, Any],
    offline_required: bool,
) -> dict[str, Any]:
    installed = bool(_as_dict(selected.get("availability")).get("installed"))
    fit_blocked = _as_dict(selected.get("fit")).get("status") == "blocked"
    network_required = not installed and selected.get("installSource") in {
        "ollama_catalog",
        "cognix_pack_catalog",
        "advanced_pack_catalog",
    }
    required = not installed and not fit_blocked
    return {
        "required": required,
        "installActionId": selected.get("installActionId"),
        "source": selected.get("installSource"),
        "networkRequired": bool(network_required),
        "blockedByOfflineRequirement": bool(offline_required and network_required),
        "steps": [
            {
                "id": "verify_runtime_adapter",
                "runtimeAdapterId": selected.get("runtimeAdapterId"),
                "willExecute": False,
                "automatic": False,
            },
            {
                "id": selected.get("installActionId"),
                "type": "model_download" if network_required else "model_register",
                "willDownload": False,
                "willInstall": False,
                "willWriteFiles": False,
                "automatic": False,
            },
        ] if required else [],
        "willDownload": False,
        "willInstall": False,
        "willWriteFiles": False,
    }


def _load_plan(
    *,
    selected: dict[str, Any],
    cache: dict[str, Any],
) -> dict[str, Any]:
    runtime = _as_dict(cache.get("runtime"))
    loaded_models = set(str(item) for item in _as_list(runtime.get("loadedModels")))
    model_id = str(selected.get("modelId") or "")
    fit_status = _as_dict(selected.get("fit")).get("status")
    installed = bool(_as_dict(selected.get("availability")).get("installed"))
    if model_id in loaded_models:
        action = "keep_loaded"
        reason = "Le modele selectionne est deja resident."
    elif fit_status == "blocked":
        action = "defer_load_hardware_blocked"
        reason = "Le pack est bloque par le profil materiel."
    elif not installed:
        action = "defer_load_until_install"
        reason = "Le pack doit etre installe avant chargement."
    elif _as_dict(cache.get("policy")).get("preloadEnabled"):
        action = "would_load_after_selection"
        reason = "Le cache autorise un chargement controle plus tard."
    else:
        action = "would_load_on_demand"
        reason = "Petit profil local: chargement uniquement a la demande."
    return {
        "required": action not in {"keep_loaded", "defer_load_hardware_blocked"},
        "action": action,
        "loadActionId": selected.get("loadActionId"),
        "modelId": selected.get("modelId"),
        "runtimeAdapterId": selected.get("runtimeAdapterId"),
        "reason": reason,
        "willLoad": False,
        "willGenerate": False,
        "automatic": False,
    }


def _unload_plan(cache: dict[str, Any]) -> dict[str, Any]:
    actions = []
    for item in _as_list(cache.get("actions")):
        if isinstance(item, dict):
            actions.append(
                {
                    "type": item.get("type"),
                    "modelId": item.get("modelId"),
                    "reason": item.get("reason"),
                    "automatic": False,
                    "willUnload": False,
                }
            )
    return {
        "policy": _as_dict(cache.get("policy")),
        "actions": actions,
        "willUnload": False,
        "cacheMutation": False,
    }


def build_model_lifecycle_plan(
    *,
    objective: str,
    hardware: dict[str, Any],
    recommendation: dict[str, Any],
    cache: dict[str, Any],
    classification: dict[str, Any],
    project_expert_plan: dict[str, Any] | None = None,
    runtime_adapter_plan: dict[str, Any] | None = None,
    model_registry: dict[str, Any] | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
    project_id: str | None = None,
    project_type: str | None = None,
    requested_model_id: str | None = None,
    execution_target: str | None = None,
    quality_priority: str | None = None,
    offline_required: bool = False,
) -> dict[str, Any]:
    expert_plan = _as_dict(project_expert_plan)
    adapter_plan = _as_dict(runtime_adapter_plan)
    registry = build_model_pack_registry(model_registry = model_registry)
    target_domain = _project_domain(project_type, classification, expert_plan)
    requested = _requested_model(requested_model_id, expert_plan)
    priority = _normalize(quality_priority) or "balanced"
    benchmark = _benchmark_fitness(latest_benchmark_run)

    candidates: list[dict[str, Any]] = []
    unknown_requested = bool(requested)
    for pack in registry["packs"]:
        if requested and _normalize(requested) in {
            _normalize(pack.get("modelId")),
            _normalize(pack.get("packId")),
        }:
            unknown_requested = False
        fit = _fit_for_pack(pack, hardware)
        score, signals = _score_pack(
            pack = pack,
            requested_model_id = requested,
            target_domain = target_domain,
            quality_priority = priority,
            recommendation = recommendation,
            fit = fit,
            benchmark = benchmark,
            offline_required = offline_required,
        )
        candidate = _candidate_record(pack = pack, score = score, signals = signals, fit = fit)
        candidate["installSource"] = pack.get("installSource")
        candidate["installActionId"] = pack.get("installActionId")
        candidate["loadActionId"] = pack.get("loadActionId")
        candidates.append(candidate)

    candidates.sort(
        key = lambda item: (
            _as_dict(item.get("fit")).get("status") != "blocked",
            int(item.get("score") or 0),
        ),
        reverse = True,
    )
    selected = candidates[0] if candidates else {}
    selected = deepcopy(selected)
    install_plan = _install_plan(selected = selected, offline_required = offline_required)
    load_plan = _load_plan(selected = selected, cache = cache)
    unload_plan = _unload_plan(cache)

    blocked_models = [
        {
            "packId": item.get("packId"),
            "modelId": item.get("modelId"),
            "label": item.get("label"),
            "reason": _as_dict(item.get("fit")).get("reason"),
        }
        for item in candidates
        if _as_dict(item.get("fit")).get("status") == "blocked"
    ]
    warnings: list[str] = []
    if unknown_requested:
        warnings.append("Modele demande absent du catalogue CogniX local: fallback sur le meilleur pack connu.")
    if install_plan["blockedByOfflineRequirement"]:
        warnings.append("Mode hors-ligne demande: installation reseau reportee.")
    if _as_dict(selected.get("fit")).get("status") == "tight":
        warnings.append("Memoire disponible serree: fermer les applications lourdes avant chargement.")
    if recommendation.get("readiness") in {"setup_required", "service_unreachable"}:
        warnings.append("Runtime local pas totalement pret: planifier la configuration avant execution.")

    return {
        "modelLifecycleVersion": COGNIX_MODEL_LIFECYCLE_VERSION,
        "mode": "dry_run",
        "objectiveExcerpt": _objective_excerpt(objective),
        "request": {
            "projectId": project_id,
            "projectType": project_type,
            "targetDomain": target_domain,
            "requestedModelId": requested_model_id,
            "effectiveRequestedModelId": requested,
            "executionTarget": execution_target or "local",
            "qualityPriority": priority,
            "offlineRequired": bool(offline_required),
        },
        "selectedPack": selected,
        "candidatePacks": candidates[:8],
        "blockedModels": blocked_models,
        "installPlan": install_plan,
        "loadPlan": load_plan,
        "unloadPlan": unload_plan,
        "runtimePlan": {
            "adapterId": selected.get("runtimeAdapterId"),
            "providerType": selected.get("providerType"),
            "format": selected.get("format"),
            "selectedAdapter": adapter_plan.get("selectedAdapter", {}),
            "serverStart": False,
            "runtimeMutation": False,
            "networkModelCall": False,
        },
        "storagePlan": {
            "estimatedStorageGb": selected.get("estimatedStorageGb"),
            "cachePolicy": _as_dict(cache.get("policy")).get("evictionStrategy"),
            "maxResidentModels": _as_dict(cache.get("policy")).get("maxResidentModels"),
            "willReserveDisk": False,
            "willWriteCache": False,
        },
        "compatibility": {
            "hardwareTier": _hardware_tier(hardware),
            "readiness": recommendation.get("readiness"),
            "fit": selected.get("fit"),
            "benchmarkKnown": bool(benchmark),
        },
        "policies": {
            "frontendCannotDownloadModels": True,
            "frontendCannotLoadModelsDirectly": True,
            "backendExecutorRequired": True,
            "auditRequiredBeforeExecution": True,
        },
        "warnings": warnings,
        "reason": "Pack modele selectionne par projet, expertise, hardware, cache et registry local, sans mutation runtime.",
        "sideEffects": {
            "modelDownload": False,
            "modelInstall": False,
            "modelLoad": False,
            "modelUnload": False,
            "runtimeMutation": False,
            "cacheMutation": False,
            "networkCall": False,
            "generation": False,
            "settingsWrite": False,
            "fileWrite": False,
        },
    }
