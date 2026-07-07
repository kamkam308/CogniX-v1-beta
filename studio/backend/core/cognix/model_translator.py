# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX universal model translator planning.

This planner evaluates whether a model adaptation is possible and prepares a
guarded conversion/export plan. It never reads model files, writes artifacts,
enqueues jobs, updates registries, or promises universal conversion.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_MODEL_CONVERSION_SERVICE_VERSION = "cognix_model_conversion_service_v1"
COGNIX_COMPATIBILITY_CHECKER_VERSION = "cognix_compatibility_checker_v1"
COGNIX_MODEL_EXPORT_MANAGER_VERSION = "cognix_model_export_manager_v1"

FORMAT_ALIASES = {
    "transformers": "transformers",
    "safetensors": "transformers",
    "hf": "transformers",
    "hf_transformers": "transformers",
    "gguf": "gguf",
    "ollama": "ollama_modelfile",
    "ollama_modelfile": "ollama_modelfile",
    "modelfile": "ollama_modelfile",
    "lora": "lora_adapter",
    "qlora": "lora_adapter",
    "lora_adapter": "lora_adapter",
    "merged": "merged_model",
    "merged_model": "merged_model",
    "model_card": "model_card",
    "cognix_metadata": "cognix_metadata",
}

CONVERSION_RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("transformers", "gguf"): {
        "status": "planned",
        "label": "Transformers vers GGUF",
        "risk": "high",
        "requires": ["config.json", "tokenizer", "weights", "llama.cpp converter", "quantization choice"],
        "steps": ["inspect_architecture", "convert_to_gguf", "quantize", "validate_load", "register_variant"],
        "warnings": ["Certaines architectures Transformers ne sont pas supportees par llama.cpp."],
    },
    ("gguf", "ollama_modelfile"): {
        "status": "planned",
        "label": "GGUF vers Ollama Modelfile",
        "risk": "low",
        "requires": ["gguf_path", "prompt_template", "modelfile_metadata"],
        "steps": ["validate_gguf_header", "create_modelfile", "dry_run_ollama_create", "register_runtime_adapter"],
        "warnings": [],
    },
    ("lora_adapter", "merged_model"): {
        "status": "planned",
        "label": "LoRA vers modele merge",
        "risk": "high",
        "requires": ["base_model", "adapter_weights", "license_review", "eval_baseline"],
        "steps": ["validate_base_model", "merge_adapter", "save_merged_model", "run_eval", "register_artifact"],
        "warnings": ["Le merge peut etre irreversible sans sauvegarde de l'adapter et du modele de base."],
    },
    ("model_card", "cognix_metadata"): {
        "status": "planned",
        "label": "Model card vers metadonnees CogniX",
        "risk": "low",
        "requires": ["model_card", "license", "architecture", "context_length"],
        "steps": ["parse_model_card", "map_metadata", "validate_license", "prepare_registry_patch"],
        "warnings": [],
    },
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_format(value: str | None) -> str:
    key = _normalize(value).casefold().replace("-", "_").replace(" ", "_")
    return FORMAT_ALIASES.get(key, key or "unknown")


def build_model_translator_blueprint() -> dict[str, Any]:
    return {
        "conversionServiceVersion": COGNIX_MODEL_CONVERSION_SERVICE_VERSION,
        "compatibilityCheckerVersion": COGNIX_COMPATIBILITY_CHECKER_VERSION,
        "exportManagerVersion": COGNIX_MODEL_EXPORT_MANAGER_VERSION,
        "mode": "dry_run_model_translation",
        "services": ["ModelConversionService", "CompatibilityChecker", "ModelExportManager"],
        "supportedExamples": [
            "Transformers -> GGUF",
            "GGUF -> Ollama Modelfile",
            "LoRA -> merged model",
            "Model card -> CogniX metadata",
        ],
        "policies": {
            "universalConversionPromised": False,
            "conversionRequiresCompatibilityCheck": True,
            "humanConfirmationRequiredBeforeJob": True,
            "registryUpdateRequiresValidation": True,
        },
        "sideEffects": {
            "modelFileRead": False,
            "modelFileWrite": False,
            "conversionJobEnqueue": False,
            "registryUpdate": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def _source_model(source_model: dict[str, Any] | None) -> dict[str, Any]:
    source = source_model if isinstance(source_model, dict) else {}
    model_id = _normalize(source.get("modelId") or source.get("id") or source.get("name") or "selected_model")[:240]
    source_format = normalize_format(str(source.get("sourceFormat") or source.get("format") or source.get("modelFormat") or "unknown"))
    return {
        "modelId": model_id,
        "label": _normalize(source.get("label") or source.get("modelLabel") or model_id)[:240],
        "sourceFormat": source_format,
        "architecture": _normalize(source.get("architecture") or source.get("modelType") or "unknown")[:120],
        "license": _normalize(source.get("license") or "unknown")[:120],
        "localPathKnown": bool(source.get("localPath") or source.get("path")),
    }


def _compatibility(source_format: str, target_format: str) -> dict[str, Any]:
    rule = CONVERSION_RULES.get((source_format, target_format))
    if rule is None:
        return {
            "checkerVersion": COGNIX_COMPATIBILITY_CHECKER_VERSION,
            "status": "blocked_impossible_or_unknown",
            "compatible": False,
            "risk": "unsupported",
            "reason": "Conversion non supportee ou impossible avec les informations actuelles.",
            "requires": [],
            "warnings": ["CogniX ne promet pas de conversion universelle."],
        }
    return {
        "checkerVersion": COGNIX_COMPATIBILITY_CHECKER_VERSION,
        "status": rule["status"],
        "compatible": True,
        "risk": rule["risk"],
        "reason": rule["label"],
        "requires": list(rule["requires"]),
        "warnings": list(rule["warnings"]),
    }


def build_model_conversion_plan(
    *,
    source_model: dict[str, Any],
    target_format: str,
    conversion_options: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    source = _source_model(source_model)
    target = normalize_format(target_format)
    options = conversion_options if isinstance(conversion_options, dict) else {}
    compatibility = _compatibility(source["sourceFormat"], target)
    rule = CONVERSION_RULES.get((source["sourceFormat"], target), {})
    steps = [
        {
            "id": step,
            "status": "planned" if compatibility["compatible"] else "blocked",
            "willRunNow": False,
        }
        for step in rule.get("steps", [])
    ]
    if not steps:
        steps = [{"id": "manual_compatibility_review", "status": "blocked", "willRunNow": False}]
    status = "planned_no_execution" if compatibility["compatible"] else "blocked"
    conversion_seed = f"{source['modelId']}:{source['sourceFormat']}:{target}:{project_id}"
    conversion_id = f"mconv_{hashlib.sha256(conversion_seed.encode('utf-8')).hexdigest()[:18]}"
    return {
        "conversionServiceVersion": COGNIX_MODEL_CONVERSION_SERVICE_VERSION,
        "compatibilityCheckerVersion": COGNIX_COMPATIBILITY_CHECKER_VERSION,
        "exportManagerVersion": COGNIX_MODEL_EXPORT_MANAGER_VERSION,
        "mode": "dry_run_model_translation",
        "conversionId": conversion_id,
        "projectId": project_id,
        "status": status,
        "sourceModel": source,
        "targetFormat": target,
        "conversionOptions": options,
        "compatibility": compatibility,
        "conversionPlan": {
            "steps": steps,
            "jobQueueRequired": compatibility["compatible"],
            "willEnqueueNow": False,
            "requiresHumanConfirmation": compatibility["compatible"],
        },
        "exportPlan": {
            "exportManagerVersion": COGNIX_MODEL_EXPORT_MANAGER_VERSION,
            "artifactType": target,
            "willWriteArtifact": False,
            "willUploadArtifact": False,
            "previewOnly": True,
        },
        "validationPlan": {
            "required": compatibility["compatible"],
            "checks": ["format_header", "metadata", "license", "runtime_adapter"],
            "willLoadModelNow": False,
        },
        "registryUpdatePlan": {
            "requiredAfterValidation": compatibility["compatible"],
            "willUpdateRegistryNow": False,
            "targetRegistry": "cognix_model_registry",
        },
        "risks": [
            {"id": "unsupported_conversion", "severity": "high", "message": warning}
            for warning in compatibility.get("warnings", [])
        ],
        "sideEffects": build_model_translator_blueprint()["sideEffects"],
    }
