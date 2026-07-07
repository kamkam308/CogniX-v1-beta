# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native image orchestration contracts."""

from __future__ import annotations

import re
from typing import Any


COGNIX_IMAGES_VERSION = "cognix_images_v1"
COGNIX_IMAGE_ORCHESTRATOR_VERSION = "cognix_image_orchestrator_v1"
COGNIX_IMAGE_SAFETY_VERSION = "cognix_image_safety_v1"
COGNIX_IMAGE_ASSET_MANAGER_VERSION = "cognix_image_asset_manager_v1"

IMAGE_ACTIONS: list[dict[str, Any]] = [
    {
        "id": "generate",
        "label": "Text-to-image",
        "keywords": ["genere", "génère", "cree", "crée", "image", "illustration", "dessine"],
        "requiredPermissions": [],
        "output": "image_asset",
    },
    {
        "id": "edit",
        "label": "Image edit",
        "keywords": ["modifie", "edit", "édition", "retouche", "remplace", "supprime"],
        "requiredPermissions": ["images:edit"],
        "output": "image_edit",
    },
    {
        "id": "analyze",
        "label": "Image analysis",
        "keywords": ["analyse", "decris", "décris", "inspecte", "ocr", "vision"],
        "requiredPermissions": ["images:analyze"],
        "output": "image_analysis",
    },
    {
        "id": "variants",
        "label": "Image variants",
        "keywords": ["variante", "variantes", "versions", "declinaisons", "déclinaisons"],
        "requiredPermissions": [],
        "output": "image_variants",
    },
]

SENSITIVE_SIGNALS: tuple[tuple[str, str], ...] = (
    ("credential", "secret"),
    ("api key", "secret"),
    ("password", "secret"),
    ("mot de passe", "secret"),
    ("token", "secret"),
    ("carte bancaire", "financial"),
    ("credit card", "financial"),
    ("document officiel", "identity"),
    ("passeport", "identity"),
)

SAFETY_REVIEW_SIGNALS: tuple[tuple[str, str], ...] = (
    ("sang", "graphic_content"),
    ("blood", "graphic_content"),
    ("arme", "weapon"),
    ("weapon", "weapon"),
    ("nu", "adult_content"),
    ("nude", "adult_content"),
)


def _normalize(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\r\n", "\n").split()).strip()
    return text[:limit]


def _safe_variant_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 1
    return max(1, min(count, 8))


def _infer_variant_count(prompt: str, explicit_count: int | None = None) -> int:
    if explicit_count:
        return _safe_variant_count(explicit_count)
    match = re.search(r"\b([2-8])\s+(?:variantes|versions|declinaisons|déclinaisons)\b", prompt.lower())
    if match:
        return _safe_variant_count(match.group(1))
    return 1


def classify_image_action(prompt: str, requested_mode: str | None = None) -> dict[str, Any]:
    if requested_mode:
        for action in IMAGE_ACTIONS:
            if action["id"] == requested_mode:
                return {**action, "confidence": 0.96, "matchedSignals": ["requested_mode"]}
    lower = _normalize(prompt, limit = 4000).lower()
    best = IMAGE_ACTIONS[0]
    best_hits: list[str] = []
    for action in IMAGE_ACTIONS:
        hits = [keyword for keyword in action["keywords"] if keyword in lower]
        if len(hits) > len(best_hits):
            best = action
            best_hits = hits
    confidence = min(0.95, 0.48 + (0.14 * len(best_hits)))
    return {**best, "confidence": round(confidence, 3), "matchedSignals": best_hits[:8]}


def build_image_safety_check(prompt: str) -> dict[str, Any]:
    lower = _normalize(prompt, limit = 4000).lower()
    flags: list[dict[str, str]] = []
    for signal, category in SENSITIVE_SIGNALS:
        if signal in lower:
            flags.append({"category": category, "signal": signal, "severity": "high"})
    for signal, category in SAFETY_REVIEW_SIGNALS:
        if signal in lower:
            flags.append({"category": category, "signal": signal, "severity": "medium"})
    max_severity = "high" if any(item["severity"] == "high" for item in flags) else "medium" if flags else "low"
    return {
        "safetyVersion": COGNIX_IMAGE_SAFETY_VERSION,
        "status": "needs_review" if flags else "clear",
        "maxSeverity": max_severity,
        "flags": flags,
        "policy": {
            "manualReviewRequired": bool(flags),
            "secretsBlockedFromMetadata": True,
            "rawPromptStored": True,
        },
    }


def build_images_blueprint() -> dict[str, Any]:
    return {
        "imagesVersion": COGNIX_IMAGES_VERSION,
        "orchestratorVersion": COGNIX_IMAGE_ORCHESTRATOR_VERSION,
        "safetyVersion": COGNIX_IMAGE_SAFETY_VERSION,
        "assetManagerVersion": COGNIX_IMAGE_ASSET_MANAGER_VERSION,
        "mode": "queue_first_image_orchestration_contract",
        "services": [
            "ImageOrchestrator",
            "ImageGenerationService",
            "ImageEditingService",
            "ImageAnalysisService",
            "ImageAssetManager",
            "ImageSafetyService",
        ],
        "actions": IMAGE_ACTIONS,
        "permissions": ["images:generate", "images:edit", "images:analyze", "images:share", "images:admin"],
        "storagePolicy": {
            "libraryWriteRequired": True,
            "variantMetadataStored": True,
            "projectLinkSupported": True,
            "artifactUriOptionalUntilRuntimeCompletes": True,
        },
        "runtimePolicy": {
            "frontendDirectModelCallAllowed": False,
            "backendOrchestratorRequired": True,
            "queueRequired": True,
            "actualGenerationEnabled": False,
        },
        "sideEffects": {
            "imageRequestWrite": False,
            "libraryWrite": False,
            "auditWrite": False,
            "queueEnqueue": False,
            "generation": False,
            "imageEdit": False,
            "imageAnalysis": False,
            "modelLoad": False,
            "networkCall": False,
            "toolExecution": False,
        },
    }


def build_permission_plan(
    *,
    action: dict[str, Any],
    granted_permissions: set[str] | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    granted = {permission.lower() for permission in (granted_permissions or set())}
    required = [str(permission).lower() for permission in action.get("requiredPermissions", [])]
    missing = [] if admin else [permission for permission in required if permission not in granted]
    return {
        "requiredPermissions": required,
        "grantedPermissions": sorted(granted),
        "missingPermissions": missing,
        "allowedByRole": bool(admin),
        "allowed": not missing,
        "executionCeiling": "admin" if admin else "creator_permissions",
    }


def build_image_plan(
    *,
    username: str,
    prompt: str,
    model: str | None = None,
    mode: str | None = None,
    project_id: str | None = None,
    source_image_id: str | None = None,
    variant_count: int | None = None,
    granted_permissions: set[str] | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    clean_prompt = _normalize(prompt, limit = 4000)
    variants = _infer_variant_count(clean_prompt, variant_count)
    requested_mode = mode
    if (not requested_mode or requested_mode == "generate") and variants > 1:
        requested_mode = "variants"
    action = classify_image_action(clean_prompt, requested_mode = requested_mode)
    safety = build_image_safety_check(clean_prompt)
    permissions = build_permission_plan(
        action = action,
        granted_permissions = granted_permissions,
        admin = admin,
    )
    selected_model = _normalize(model, limit = 160) or "cognix-image-default"
    side_effects = build_images_blueprint()["sideEffects"]
    return {
        "imagesVersion": COGNIX_IMAGES_VERSION,
        "orchestratorVersion": COGNIX_IMAGE_ORCHESTRATOR_VERSION,
        "safetyVersion": COGNIX_IMAGE_SAFETY_VERSION,
        "assetManagerVersion": COGNIX_IMAGE_ASSET_MANAGER_VERSION,
        "mode": "image_request_plan",
        "username": username,
        "prompt": clean_prompt,
        "projectId": _normalize(project_id, limit = 160) or None,
        "sourceImageId": _normalize(source_image_id, limit = 180) or None,
        "action": {
            "actionType": action["id"],
            "label": action["label"],
            "confidence": action["confidence"],
            "matchedSignals": action["matchedSignals"],
            "output": action["output"],
        },
        "modelPlan": {
            "requestedModel": model,
            "selectedModel": selected_model,
            "selectionSource": "user_request" if model else "default_image_runtime",
            "loadNow": False,
        },
        "variantPlan": {
            "count": variants,
            "storeVariants": variants > 1,
            "variantGridReady": variants > 1,
        },
        "safety": safety,
        "permissionPlan": permissions,
        "queuePlan": {
            "queueRequired": True,
            "queueName": "images",
            "willEnqueueNow": False,
            "workerStart": False,
        },
        "libraryAsset": {
            "kind": "image",
            "name": clean_prompt[:80] or "Image CogniX",
            "source": "image_generation",
            "metadata": {
                "imagePlanVersion": COGNIX_IMAGES_VERSION,
                "actionType": action["id"],
                "selectedModel": selected_model,
                "projectId": _normalize(project_id, limit = 160) or None,
                "sourceImageId": _normalize(source_image_id, limit = 180) or None,
                "variantCount": variants,
                "safetyStatus": safety["status"],
            },
        },
        "warnings": [
            {
                "id": "image_safety_review",
                "message": "La demande image contient des signaux qui necessitent une revue.",
                "flags": safety["flags"],
            }
        ]
        if safety["flags"]
        else [],
        "sideEffects": side_effects,
    }


def summarize_image_history(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_model: dict[str, int] = {}
    for item in items:
        status = _normalize(item.get("status"), limit = 80) or "unknown"
        model = _normalize(item.get("model"), limit = 160) or "default"
        by_status[status] = by_status.get(status, 0) + 1
        by_model[model] = by_model.get(model, 0) + 1
    return {
        "imagesVersion": COGNIX_IMAGES_VERSION,
        "requestCount": len(items),
        "byStatus": by_status,
        "byModel": by_model,
        "sideEffects": build_images_blueprint()["sideEffects"],
    }
