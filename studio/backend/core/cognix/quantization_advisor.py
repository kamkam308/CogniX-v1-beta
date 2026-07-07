# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX adaptive quantization advisor.

The advisor selects a recommended model variant from hardware, model metadata,
and user priority. It is deliberately dry-run only: no model file is converted,
downloaded, loaded, or reconfigured from this module.
"""

from __future__ import annotations

from typing import Any


COGNIX_QUANTIZATION_ADVISOR_VERSION = "cognix_quantization_advisor_v1"
COGNIX_MODEL_VARIANT_REGISTRY_VERSION = "cognix_model_variant_registry_v1"
COGNIX_PERFORMANCE_PREDICTOR_VERSION = "cognix_performance_predictor_v1"

PRIORITY_ALIASES = {
    "quality": "quality",
    "qualite": "quality",
    "speed": "speed",
    "vitesse": "speed",
    "memory": "memory",
    "memoire": "memory",
    "economy": "memory",
    "economie": "memory",
    "balanced": "balanced",
    "balance": "balanced",
    "equilibre": "balanced",
}

VARIANT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "variantId": "iq2_xxs",
        "quantization": "IQ2",
        "label": "IQ2 ultra compact",
        "qualityScore": 42,
        "speedScore": 72,
        "memoryScore": 96,
        "ramFactor": 0.62,
        "vramFactor": 0.58,
        "bestFor": ["memory"],
        "risk": "high_quality_loss",
    },
    {
        "variantId": "q4_k_m",
        "quantization": "Q4",
        "label": "Q4 equilibre compact",
        "qualityScore": 70,
        "speedScore": 82,
        "memoryScore": 86,
        "ramFactor": 1.0,
        "vramFactor": 0.92,
        "bestFor": ["memory", "speed", "balanced"],
        "risk": "low_medium_quality_loss",
    },
    {
        "variantId": "q5_k_m",
        "quantization": "Q5",
        "label": "Q5 qualite locale",
        "qualityScore": 82,
        "speedScore": 74,
        "memoryScore": 74,
        "ramFactor": 1.25,
        "vramFactor": 1.15,
        "bestFor": ["balanced", "quality"],
        "risk": "low_quality_loss",
    },
    {
        "variantId": "q8_0",
        "quantization": "Q8",
        "label": "Q8 haute qualite",
        "qualityScore": 91,
        "speedScore": 56,
        "memoryScore": 48,
        "ramFactor": 1.95,
        "vramFactor": 1.78,
        "bestFor": ["quality"],
        "risk": "memory_pressure",
    },
    {
        "variantId": "fp16",
        "quantization": "FP16",
        "label": "FP16 GPU puissant",
        "qualityScore": 98,
        "speedScore": 46,
        "memoryScore": 24,
        "ramFactor": 3.8,
        "vramFactor": 3.4,
        "bestFor": ["quality"],
        "risk": "requires_powerful_gpu",
    },
)

PRIORITY_WEIGHTS = {
    "quality": {"qualityScore": 0.62, "speedScore": 0.14, "memoryScore": 0.14, "fitScore": 0.10},
    "speed": {"qualityScore": 0.20, "speedScore": 0.50, "memoryScore": 0.18, "fitScore": 0.12},
    "memory": {"qualityScore": 0.14, "speedScore": 0.18, "memoryScore": 0.56, "fitScore": 0.12},
    "balanced": {"qualityScore": 0.34, "speedScore": 0.28, "memoryScore": 0.26, "fitScore": 0.12},
}


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


def normalize_priority(value: str | None) -> str:
    normalized = str(value or "balanced").strip().casefold().replace("-", "_").replace(" ", "_")
    return PRIORITY_ALIASES.get(normalized, "balanced")


def _hardware_summary(hardware: dict[str, Any]) -> dict[str, Any]:
    memory = _as_dict(hardware.get("memory"))
    gpu = _as_dict(hardware.get("gpu"))
    devices = [item for item in gpu.get("devices", []) if isinstance(item, dict)]
    max_vram = max(
        (
            _as_float(item.get("vramFreeGb"))
            or _as_float(item.get("vramTotalGb"))
            or 0.0
            for item in devices
        ),
        default = 0.0,
    )
    total_ram = _as_float(memory.get("totalGb")) or 0.0
    available_ram = _as_float(memory.get("availableGb")) or total_ram
    return {
        "deviceBackend": str(hardware.get("deviceBackend") or "unknown"),
        "totalRamGb": round(total_ram, 2),
        "availableRamGb": round(available_ram, 2),
        "gpuAvailable": bool(gpu.get("available")),
        "gpuCount": len(devices),
        "maxVramGb": round(max_vram, 2),
    }


def _base_model_metadata(model_metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = _as_dict(model_metadata)
    model_id = str(
        metadata.get("modelId")
        or metadata.get("id")
        or metadata.get("model_id")
        or "selected_model"
    )
    label = str(metadata.get("modelLabel") or metadata.get("label") or model_id)
    base_ram = (
        _as_float(metadata.get("estimatedRamGb"))
        or _as_float(_as_dict(metadata.get("memoryFit")).get("requiredRamGb"))
        or _as_float(metadata.get("ramGb"))
        or 4.6
    )
    family = "gguf" if str(metadata.get("format") or metadata.get("providerType") or "").lower() in {"gguf", "local_gguf", "ollama"} else "generic"
    return {
        "modelId": model_id,
        "label": label,
        "providerType": str(metadata.get("providerType") or "local_gguf"),
        "format": str(metadata.get("format") or ("gguf" if family == "gguf" else "unknown")),
        "baseQuantization": str(metadata.get("quantization") or "Q4"),
        "baseEstimatedRamGb": round(base_ram, 2),
        "family": family,
    }


def _fit_score(variant: dict[str, Any], hardware: dict[str, Any], base_ram_gb: float) -> dict[str, Any]:
    estimated_ram = round(max(0.4, base_ram_gb * float(variant["ramFactor"])), 2)
    estimated_vram = round(max(0.4, base_ram_gb * float(variant["vramFactor"])), 2)
    available_ram = float(hardware.get("availableRamGb") or hardware.get("totalRamGb") or 0.0)
    max_vram = float(hardware.get("maxVramGb") or 0.0)
    gpu_ok = bool(hardware.get("gpuAvailable")) and max_vram >= estimated_vram * 1.08
    ram_ok = available_ram >= estimated_ram * 1.18
    total_ram_ok = float(hardware.get("totalRamGb") or 0.0) >= estimated_ram
    if gpu_ok:
        status = "recommended"
        reason = "Compatible GPU avec marge VRAM."
        fit = 100
    elif ram_ok:
        status = "recommended"
        reason = "Compatible RAM locale avec marge."
        fit = 86
    elif total_ram_ok:
        status = "tight"
        reason = "Possible apres liberation de memoire."
        fit = 58
    else:
        status = "blocked"
        reason = "RAM/VRAM insuffisante pour cette variante."
        fit = 18
    return {
        "status": status,
        "fitScore": fit,
        "reason": reason,
        "estimatedRamGb": estimated_ram,
        "estimatedVramGb": estimated_vram,
        "gpuFit": gpu_ok,
        "ramFit": ram_ok,
    }


def _priority_score(variant: dict[str, Any], fit: dict[str, Any], priority: str) -> float:
    weights = PRIORITY_WEIGHTS[priority]
    score = 0.0
    for key, weight in weights.items():
        score += float(variant.get(key) if key != "fitScore" else fit.get(key)) * weight
    if fit["status"] == "blocked":
        score -= 100
    elif fit["status"] == "tight":
        score -= 12
    if priority in set(variant.get("bestFor") or []):
        score += 4
    if priority == "quality" and fit.get("gpuFit") and variant.get("quantization") in {"Q8", "FP16"}:
        score += 8
    return round(score, 2)


def _variant_record(template: dict[str, Any], *, model: dict[str, Any], hardware: dict[str, Any], priority: str) -> dict[str, Any]:
    fit = _fit_score(template, hardware, float(model["baseEstimatedRamGb"]))
    score = _priority_score(template, fit, priority)
    return {
        **template,
        "modelId": model["modelId"],
        "variantKey": f"{model['modelId']}:{template['variantId']}",
        "priorityScore": score,
        "fit": fit,
        "performancePrediction": {
            "predictorVersion": COGNIX_PERFORMANCE_PREDICTOR_VERSION,
            "expectedLatency": "low" if template["speedScore"] >= 78 and fit["status"] != "blocked" else "medium" if template["speedScore"] >= 58 else "high",
            "expectedQuality": "high" if template["qualityScore"] >= 86 else "medium" if template["qualityScore"] >= 68 else "low",
            "memoryPressure": "low" if fit["status"] == "recommended" and template["memoryScore"] >= 74 else "medium" if fit["status"] != "blocked" else "high",
            "benchmarkRequiredForConfidence": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "modelDownload": False,
            "modelConversion": False,
            "modelFileWrite": False,
            "runtimeConfigWrite": False,
            "networkCall": False,
            "benchmarkRun": False,
        },
    }


def build_model_variant_registry(
    *,
    model_metadata: dict[str, Any] | None = None,
    hardware: dict[str, Any] | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    normalized_priority = normalize_priority(priority)
    hw = _hardware_summary(_as_dict(hardware))
    model = _base_model_metadata(model_metadata)
    variants = [
        _variant_record(template, model = model, hardware = hw, priority = normalized_priority)
        for template in VARIANT_TEMPLATES
    ]
    viable = [item for item in variants if item["fit"]["status"] != "blocked"]
    recommended = max(viable or variants, key = lambda item: item["priorityScore"])
    return {
        "advisorVersion": COGNIX_QUANTIZATION_ADVISOR_VERSION,
        "registryVersion": COGNIX_MODEL_VARIANT_REGISTRY_VERSION,
        "mode": "dry_run",
        "priority": normalized_priority,
        "model": model,
        "hardware": hw,
        "badge": {
            "label": "Recommande pour ton PC",
            "variantKey": recommended["variantKey"],
            "quantization": recommended["quantization"],
        },
        "variantCount": len(variants),
        "recommendedVariant": recommended,
        "variants": sorted(variants, key = lambda item: item["priorityScore"], reverse = True),
        "policies": {
            "frontendDirectModelSelectionMutationAllowed": False,
            "benchmarkRecommendedBeforeApply": True,
            "humanConfirmationRequiredBeforeApply": True,
            "modelFileMutationAllowed": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "modelDownload": False,
            "modelConversion": False,
            "modelFileWrite": False,
            "runtimeConfigWrite": False,
            "networkCall": False,
            "benchmarkRun": False,
        },
    }


def build_adaptive_quantization_plan(
    *,
    hardware: dict[str, Any],
    model_metadata: dict[str, Any] | None = None,
    priority: str | None = None,
    latest_benchmark_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = build_model_variant_registry(
        model_metadata = model_metadata,
        hardware = hardware,
        priority = priority,
    )
    selected = registry["recommendedVariant"]
    benchmark_available = isinstance(latest_benchmark_run, dict)
    alternatives = [
        item
        for item in registry["variants"]
        if item["variantKey"] != selected["variantKey"] and item["fit"]["status"] != "blocked"
    ][:3]
    return {
        "advisorVersion": COGNIX_QUANTIZATION_ADVISOR_VERSION,
        "variantRegistryVersion": COGNIX_MODEL_VARIANT_REGISTRY_VERSION,
        "performancePredictorVersion": COGNIX_PERFORMANCE_PREDICTOR_VERSION,
        "mode": "dry_run",
        "priority": registry["priority"],
        "badge": registry["badge"],
        "model": registry["model"],
        "hardware": registry["hardware"],
        "selectedVariant": selected,
        "alternativeVariants": alternatives,
        "variantRegistry": registry,
        "benchmark": {
            "available": benchmark_available,
            "latestRunId": _as_dict(latest_benchmark_run).get("id"),
            "recommendedBeforeApply": not benchmark_available,
            "willRunBenchmark": False,
        },
        "applyPlan": {
            "willApplyAutomatically": False,
            "requiresHumanConfirmation": True,
            "requiresModelReload": True,
            "modelVariantSelectionOnly": True,
            "writesModelFiles": False,
            "writesRuntimeConfig": False,
        },
        "reason": f"{selected['quantization']} choisi pour la priorite {registry['priority']} avec le profil materiel courant.",
        "sideEffects": {
            "modelLoad": False,
            "modelDownload": False,
            "modelConversion": False,
            "modelFileWrite": False,
            "runtimeConfigWrite": False,
            "networkCall": False,
            "benchmarkRun": False,
            "generation": False,
        },
    }
