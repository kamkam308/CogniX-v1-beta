# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX enterprise local-only policy controls."""

from __future__ import annotations

import urllib.parse
from typing import Any


COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION = "cognix_local_only_policy_engine_v1"
COGNIX_NETWORK_EGRESS_GUARD_VERSION = "cognix_network_egress_guard_v1"
COGNIX_PROVIDER_BLOCKER_VERSION = "cognix_provider_blocker_v1"

LOCAL_ONLY_SERVICES = [
    "LocalOnlyPolicyEngine",
    "NetworkEgressGuard",
    "ProviderBlocker",
]

LOCAL_ONLY_TABLES = [
    "local_only_policies",
    "blocked_external_calls",
]

LOCAL_PROVIDER_TYPES = {
    "",
    "local",
    "ollama",
    "llama",
    "llama.cpp",
    "llamacpp",
    "gguf",
    "local_gguf",
    "cpu",
    "unsloth",
    "vllm_local",
}

DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "::1", "localhost", "cognix.local"]
DEFAULT_ALLOWED_PROVIDERS = ["local", "ollama", "llama.cpp", "local_gguf", "unsloth"]

DEFAULT_LOCAL_ONLY_POLICY: dict[str, Any] = {
    "enabled": False,
    "allowedHosts": DEFAULT_ALLOWED_HOSTS,
    "allowedProviders": DEFAULT_ALLOWED_PROVIDERS,
    "blockCloudProviders": True,
    "blockExternalModels": True,
    "blockTelemetry": True,
    "blockDocumentEgress": True,
    "internalLogsOnly": True,
}


def _norm(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled", "allow", "allowed"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled", "deny", "denied"}:
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


def _host_from_url(url: str | None) -> str:
    raw = _norm(url)
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.hostname:
        return parsed.hostname.strip().lower()
    if "://" not in raw and "/" not in raw:
        return raw.strip().lower()
    return ""


def normalize_local_only_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = policy if isinstance(policy, dict) else {}
    normalized = dict(DEFAULT_LOCAL_ONLY_POLICY)
    for key in (
        "enabled",
        "blockCloudProviders",
        "blockExternalModels",
        "blockTelemetry",
        "blockDocumentEgress",
        "internalLogsOnly",
    ):
        if key in incoming:
            normalized[key] = _as_bool(incoming.get(key), bool(normalized[key]))
    if "allowedHosts" in incoming:
        hosts = _as_list(incoming.get("allowedHosts"))
        normalized["allowedHosts"] = hosts or list(DEFAULT_ALLOWED_HOSTS)
    if "allowedProviders" in incoming:
        providers = [item.casefold() for item in _as_list(incoming.get("allowedProviders"))]
        normalized["allowedProviders"] = providers or list(DEFAULT_ALLOWED_PROVIDERS)
    if normalized["enabled"]:
        normalized["blockCloudProviders"] = True
        normalized["blockExternalModels"] = True
        normalized["blockTelemetry"] = True
        normalized["blockDocumentEgress"] = True
        normalized["internalLogsOnly"] = True
    return normalized


def build_local_only_blueprint() -> dict[str, Any]:
    return {
        "localOnlyPolicyEngineVersion": COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION,
        "networkEgressGuardVersion": COGNIX_NETWORK_EGRESS_GUARD_VERSION,
        "providerBlockerVersion": COGNIX_PROVIDER_BLOCKER_VERSION,
        "mode": "native_enterprise_local_only",
        "services": LOCAL_ONLY_SERVICES,
        "tables": LOCAL_ONLY_TABLES,
        "rules": [
            "no_cloud_calls",
            "no_external_models",
            "no_external_telemetry",
            "no_document_egress",
            "local_models_only",
            "internal_logs_only",
        ],
        "ui": {
            "badge": "Local-only mode active",
            "visibleWhenEnabled": True,
        },
        "sideEffects": {
            "databaseWrite": False,
            "policyWrite": False,
            "organizationSettingsWrite": False,
            "blockedCallWrite": False,
            "auditWrite": False,
            "networkCall": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "fileWrite": False,
        },
    }


def provider_is_local(provider: str | None, allowed_providers: list[str] | None = None) -> bool:
    normalized = _norm(provider, "local").casefold()
    allowed = {item.casefold() for item in (allowed_providers or DEFAULT_ALLOWED_PROVIDERS)}
    return normalized in LOCAL_PROVIDER_TYPES or normalized in allowed


def host_is_local(url: str | None, allowed_hosts: list[str] | None = None) -> bool:
    host = _host_from_url(url)
    if not host:
        return True
    allowed = {item.casefold() for item in (allowed_hosts or DEFAULT_ALLOWED_HOSTS)}
    return host in allowed


def build_local_only_badge(policy: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_local_only_policy(policy)
    return {
        "label": "Local-only mode active",
        "active": bool(normalized["enabled"]),
        "tone": "secure" if normalized["enabled"] else "neutral",
        "description": "Cloud, external models, telemetry and document egress are blocked."
        if normalized["enabled"]
        else "Local-only mode is available but inactive.",
    }


def build_egress_decision(
    *,
    policy: dict[str, Any],
    provider: str | None = None,
    url: str | None = None,
    action_type: str | None = None,
    model_id: str | None = None,
    document_transfer: bool = False,
) -> dict[str, Any]:
    normalized = normalize_local_only_policy(policy)
    action = _norm(action_type, "network").casefold()
    provider_value = _norm(provider, "local")
    url_value = _norm(url)
    reasons: list[str] = []
    if normalized["enabled"]:
        if normalized["blockCloudProviders"] and not provider_is_local(provider_value, normalized["allowedProviders"]):
            reasons.append("cloud_provider_blocked_by_local_only_policy")
        if normalized["blockExternalModels"] and not provider_is_local(provider_value, normalized["allowedProviders"]):
            reasons.append("external_model_blocked_by_local_only_policy")
        if url_value and not host_is_local(url_value, normalized["allowedHosts"]):
            reasons.append("external_network_egress_blocked_by_local_only_policy")
        if normalized["blockTelemetry"] and action in {"telemetry", "analytics", "metrics"}:
            reasons.append("telemetry_blocked_by_local_only_policy")
        if normalized["blockDocumentEgress"] and (document_transfer or action in {"document", "document_egress"}):
            reasons.append("document_egress_blocked_by_local_only_policy")
    allowed = not reasons
    return {
        "networkEgressGuardVersion": COGNIX_NETWORK_EGRESS_GUARD_VERSION,
        "providerBlockerVersion": COGNIX_PROVIDER_BLOCKER_VERSION,
        "enabled": bool(normalized["enabled"]),
        "allowed": allowed,
        "provider": provider_value,
        "modelId": _norm(model_id),
        "url": url_value,
        "host": _host_from_url(url_value),
        "actionType": action,
        "documentTransfer": bool(document_transfer),
        "reasons": reasons,
        "decision": "allow_local" if allowed else "block_external",
        "sideEffects": build_local_only_blueprint()["sideEffects"],
    }


def build_enforcement_plan(
    *,
    policy: dict[str, Any],
    blocked_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_local_only_policy(policy)
    calls = list(blocked_calls or [])
    return {
        "localOnlyPolicyEngineVersion": COGNIX_LOCAL_ONLY_POLICY_ENGINE_VERSION,
        "policy": normalized,
        "badge": build_local_only_badge(normalized),
        "enforcedSettings": {
            "cloudAllowed": False if normalized["enabled"] else None,
            "externalModelsAllowed": False if normalized["enabled"] else None,
            "telemetryExternalAllowed": False if normalized["enabled"] else None,
            "documentEgressAllowed": False if normalized["enabled"] else None,
        },
        "summary": {
            "enabled": bool(normalized["enabled"]),
            "blockedCallCount": len(calls),
            "allowedProviderCount": len(normalized["allowedProviders"]),
            "allowedHostCount": len(normalized["allowedHosts"]),
        },
        "checks": [
            "provider_is_local",
            "host_is_local",
            "telemetry_disabled",
            "document_egress_disabled",
            "internal_logs_only",
        ],
        "sideEffects": build_local_only_blueprint()["sideEffects"],
    }
