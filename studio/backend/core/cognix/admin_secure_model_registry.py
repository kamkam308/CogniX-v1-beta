# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX enterprise secure model registry."""

from __future__ import annotations

import re
from typing import Any


COGNIX_SECURE_MODEL_REGISTRY_VERSION = "cognix_secure_model_registry_v1"
COGNIX_MODEL_APPROVAL_SERVICE_VERSION = "cognix_model_approval_service_v1"
COGNIX_MODEL_LICENSE_CHECKER_VERSION = "cognix_model_license_checker_v1"
COGNIX_MODEL_CHECKSUM_VERIFIER_VERSION = "cognix_model_checksum_verifier_v1"

SECURE_MODEL_REGISTRY_SERVICES = [
    "SecureModelRegistry",
    "ModelApprovalService",
    "ModelLicenseChecker",
    "ModelChecksumVerifier",
]

SECURE_MODEL_REGISTRY_TABLES = [
    "approved_models",
    "blocked_models",
    "model_security_metadata",
]

LOCAL_PROVIDER_TYPES = {"", "local", "ollama", "llama", "llama.cpp", "llamacpp", "gguf", "local_gguf", "unsloth"}
CHECKSUM_RE = re.compile(r"^(sha256:)?[a-fA-F0-9]{64}$")


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled", "required"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return fallback


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple | set):
        raw = list(value)
    else:
        raw = [value]
    return [item for item in (_norm(entry) for entry in raw) if item]


def _provider_is_local(provider_type: str | None) -> bool:
    return _norm(provider_type, "local").casefold() in LOCAL_PROVIDER_TYPES


def checksum_status(checksum: str | None) -> dict[str, Any]:
    value = _norm(checksum)
    if not value:
        return {"checksum": "", "verified": False, "status": "missing"}
    if CHECKSUM_RE.match(value):
        return {"checksum": value, "verified": True, "status": "format_verified"}
    return {"checksum": value, "verified": False, "status": "invalid_format"}


def build_secure_model_registry_blueprint() -> dict[str, Any]:
    return {
        "secureModelRegistryVersion": COGNIX_SECURE_MODEL_REGISTRY_VERSION,
        "modelApprovalServiceVersion": COGNIX_MODEL_APPROVAL_SERVICE_VERSION,
        "modelLicenseCheckerVersion": COGNIX_MODEL_LICENSE_CHECKER_VERSION,
        "modelChecksumVerifierVersion": COGNIX_MODEL_CHECKSUM_VERIFIER_VERSION,
        "mode": "native_enterprise_secure_model_registry",
        "services": SECURE_MODEL_REGISTRY_SERVICES,
        "tables": SECURE_MODEL_REGISTRY_TABLES,
        "controls": [
            "approve_model",
            "block_model",
            "limit_by_role",
            "require_quantization",
            "require_local_only",
            "license_visibility",
            "source_visibility",
            "checksum_verification",
        ],
        "sideEffects": {
            "databaseWrite": False,
            "approvedModelWrite": False,
            "blockedModelWrite": False,
            "metadataWrite": False,
            "organizationSettingsWrite": False,
            "auditWrite": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "fileWrite": False,
        },
    }


def build_model_security_metadata(
    *,
    model_id: str,
    provider_type: str | None = None,
    license_name: str | None = None,
    source: str | None = None,
    checksum: str | None = None,
) -> dict[str, Any]:
    checksum_info = checksum_status(checksum)
    license_value = _norm(license_name, "unknown")
    source_value = _norm(source, "unknown")
    risk_level = "low"
    warnings: list[str] = []
    if license_value == "unknown":
        risk_level = "medium"
        warnings.append("license_unknown")
    if source_value == "unknown":
        risk_level = "medium"
        warnings.append("source_unknown")
    if not checksum_info["verified"]:
        risk_level = "medium" if risk_level == "low" else risk_level
        warnings.append(f"checksum_{checksum_info['status']}")
    if not _provider_is_local(provider_type):
        warnings.append("external_provider")
    return {
        "modelLicenseCheckerVersion": COGNIX_MODEL_LICENSE_CHECKER_VERSION,
        "modelChecksumVerifierVersion": COGNIX_MODEL_CHECKSUM_VERIFIER_VERSION,
        "modelId": _norm(model_id),
        "providerType": _norm(provider_type, "local"),
        "license": license_value,
        "source": source_value,
        "checksum": checksum_info["checksum"],
        "checksumVerified": bool(checksum_info["verified"]),
        "checksumStatus": checksum_info["status"],
        "riskLevel": risk_level,
        "warnings": warnings,
        "sideEffects": build_secure_model_registry_blueprint()["sideEffects"],
    }


def build_model_access_decision(
    *,
    model_id: str,
    provider_type: str | None,
    role: str | None,
    quantization: str | None,
    local_only_active: bool,
    approved_models: list[dict[str, Any]],
    blocked_models: list[dict[str, Any]],
) -> dict[str, Any]:
    model_value = _norm(model_id)
    provider_value = _norm(provider_type, "local")
    role_value = _norm(role, "user")
    quant_value = _norm(quantization)
    approved_by_id = {str(item.get("modelId") or item.get("model_id") or ""): item for item in approved_models}
    blocked_by_id = {str(item.get("modelId") or item.get("model_id") or ""): item for item in blocked_models}
    reasons: list[str] = []
    approved = approved_by_id.get(model_value)
    blocked = blocked_by_id.get(model_value)
    if blocked:
        reasons.append("model_blocked_by_secure_registry")
    if approved_models and not approved:
        reasons.append("model_not_approved_by_secure_registry")
    if approved:
        allowed_roles = set(_as_list(approved.get("allowedRoles") or approved.get("allowed_roles")))
        if allowed_roles and role_value not in allowed_roles:
            reasons.append("role_not_allowed_for_model")
        required_quant = _norm(approved.get("quantizationRequired") or approved.get("quantization_required"))
        if required_quant and quant_value != required_quant:
            reasons.append("required_quantization_missing")
        local_required = _as_bool(approved.get("localOnlyRequired") or approved.get("local_only_required"), False)
        if local_required and (not local_only_active or not _provider_is_local(provider_value)):
            reasons.append("local_only_required_for_model")
    allowed = not reasons
    return {
        "secureModelRegistryVersion": COGNIX_SECURE_MODEL_REGISTRY_VERSION,
        "modelId": model_value,
        "providerType": provider_value,
        "role": role_value,
        "quantization": quant_value,
        "localOnlyActive": bool(local_only_active),
        "approved": approved is not None,
        "blocked": blocked is not None,
        "allowed": allowed,
        "reasons": reasons,
        "decision": "allow_model" if allowed else "deny_model",
        "sideEffects": build_secure_model_registry_blueprint()["sideEffects"],
    }


def build_secure_registry_bundle(
    *,
    model_registry: dict[str, Any],
    approved_models: list[dict[str, Any]],
    blocked_models: list[dict[str, Any]],
    metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    registry_models = list(model_registry.get("models") or [])
    return {
        "secureModelRegistryVersion": COGNIX_SECURE_MODEL_REGISTRY_VERSION,
        "modelApprovalServiceVersion": COGNIX_MODEL_APPROVAL_SERVICE_VERSION,
        "modelRegistry": model_registry,
        "approvedModels": approved_models,
        "blockedModels": blocked_models,
        "modelSecurityMetadata": metadata,
        "summary": {
            "registeredModelCount": len(registry_models),
            "approvedModelCount": len(approved_models),
            "blockedModelCount": len(blocked_models),
            "metadataCount": len(metadata),
        },
        "sideEffects": build_secure_model_registry_blueprint()["sideEffects"],
    }
