# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native enterprise chat and E2EE planning.

This module models enterprise chat without decrypting content or exposing key
material. In strict E2EE mode every payload must already be encrypted on the
client side; the backend stores only metadata and sealed message envelopes.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION = "cognix_enterprise_chat_service_v1"
COGNIX_E2EE_KEY_MANAGER_VERSION = "cognix_e2ee_key_manager_v1"
COGNIX_MESSAGE_ENCRYPTION_SERVICE_VERSION = "cognix_message_encryption_service_v1"
COGNIX_CHAT_POLICY_SERVICE_VERSION = "cognix_chat_policy_service_v1"

ENTERPRISE_CHAT_SERVICES = [
    "EnterpriseChatService",
    "E2EEKeyManager",
    "MessageEncryptionService",
    "ChatPolicyService",
]

ENTERPRISE_CHAT_TABLES = [
    "enterprise_chats",
    "enterprise_chat_members",
    "encrypted_messages",
    "chat_key_metadata",
    "chat_policies",
]

CHAT_MODES = {"compliance", "e2ee"}
MEMBER_ROLES = {"owner", "admin", "member", "viewer"}
DEFAULT_ORGANIZATION_ID = "local"


def _safe_text(value: Any, limit: int, fallback: str = "") -> str:
    return " ".join(str(value if value is not None else fallback).replace("\r\n", "\n").split()).strip()[:limit]


def _safe_key(value: Any, fallback: str = "local") -> str:
    text = _safe_text(value, 180, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return cleaned.strip("-")[:160] or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled", "allow"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled", "deny"}:
            return False
    return fallback


def _chat_mode(value: Any) -> str:
    mode = _safe_key(value, "e2ee")
    return mode if mode in CHAT_MODES else "e2ee"


def _fingerprint(value: Any) -> str:
    text = _safe_text(value, 4000, "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _participant_record(value: Any, fallback_username: str, *, owner: bool = False) -> dict[str, Any]:
    raw = _as_dict(value)
    username = _safe_key(raw.get("username") or raw.get("user") or value or fallback_username, fallback_username)
    requested_role = _safe_key(raw.get("role") or ("owner" if owner else "member"), "member")
    role = requested_role if requested_role in MEMBER_ROLES else "member"
    if owner:
        role = "owner"
    return {
        "username": username,
        "role": role,
        "status": "active",
        "canReadMetadata": True,
        "serverCanReadContent": False,
    }


def normalize_chat_policy(policy: dict[str, Any] | None = None, *, chat_mode: str = "e2ee") -> dict[str, Any]:
    incoming = _as_dict(policy)
    mode = _chat_mode(chat_mode)
    normalized = {
        "mode": mode,
        "encryptionAtRestRequired": True,
        "encryptionInTransitRequired": True,
        "adminContentReadAllowed": _as_bool(incoming.get("adminContentReadAllowed"), mode == "compliance"),
        "serverContentReadable": _as_bool(incoming.get("serverContentReadable"), mode == "compliance"),
        "serverIndexingAllowed": _as_bool(incoming.get("serverIndexingAllowed"), mode == "compliance"),
        "clientSideKeysRequired": _as_bool(incoming.get("clientSideKeysRequired"), mode == "e2ee"),
        "localSearchOnly": _as_bool(incoming.get("localSearchOnly"), mode == "e2ee"),
        "memberRevocationRequired": True,
        "keyRotationRequired": True,
        "recoveryPolicy": _safe_key(incoming.get("recoveryPolicy"), "metadata_only_recovery"),
        "auditMetadataRequired": True,
    }
    if mode == "e2ee":
        normalized.update(
            {
                "adminContentReadAllowed": False,
                "serverContentReadable": False,
                "serverIndexingAllowed": False,
                "clientSideKeysRequired": True,
                "localSearchOnly": True,
                "recoveryPolicy": "metadata_only_recovery",
            }
        )
    return normalized


def build_enterprise_chat_blueprint() -> dict[str, Any]:
    return {
        "enterpriseChatServiceVersion": COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION,
        "e2eeKeyManagerVersion": COGNIX_E2EE_KEY_MANAGER_VERSION,
        "messageEncryptionServiceVersion": COGNIX_MESSAGE_ENCRYPTION_SERVICE_VERSION,
        "chatPolicyServiceVersion": COGNIX_CHAT_POLICY_SERVICE_VERSION,
        "services": ENTERPRISE_CHAT_SERVICES,
        "tables": ENTERPRISE_CHAT_TABLES,
        "modes": [
            {
                "id": "compliance",
                "label": "Enterprise Compliance Chat",
                "adminCanReadContentWhenPolicyAllows": True,
                "serverIndexingAllowedWhenPolicyAllows": True,
            },
            {
                "id": "e2ee",
                "label": "True E2EE Chat",
                "adminCanReadContentWhenPolicyAllows": False,
                "serverIndexingAllowedWhenPolicyAllows": False,
            },
        ],
        "policyDefaults": {
            "strictE2eeDefault": True,
            "metadataOnlyAuditForE2ee": True,
            "clientKeyGenerationRequiredForE2ee": True,
            "memberRevocationRequiresKeyRotation": True,
            "plaintextPersistenceAllowed": False,
        },
        "sideEffects": {
            "chatWrite": False,
            "memberWrite": False,
            "encryptedMessageWrite": False,
            "keyMetadataWrite": False,
            "policyWrite": False,
            "plaintextRead": False,
            "serverDecryption": False,
            "serverIndexing": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "secretRead": False,
        },
    }


def build_enterprise_chat_creation_plan(
    *,
    username: str,
    title: str | None = None,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    project_id: str | None = None,
    chat_mode: str = "e2ee",
    participants: list[Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = _chat_mode(chat_mode)
    normalized_policy = normalize_chat_policy(policy, chat_mode = mode)
    owner = _participant_record({"username": username, "role": "owner"}, username, owner = True)
    normalized_participants = [owner]
    seen = {owner["username"]}
    for item in _as_list(participants):
        record = _participant_record(item, username)
        if record["username"] in seen:
            continue
        record["serverCanReadContent"] = normalized_policy["serverContentReadable"]
        normalized_participants.append(record)
        seen.add(record["username"])
    group_ready = len(normalized_participants) >= 2
    return {
        "enterpriseChatServiceVersion": COGNIX_ENTERPRISE_CHAT_SERVICE_VERSION,
        "e2eeKeyManagerVersion": COGNIX_E2EE_KEY_MANAGER_VERSION,
        "messageEncryptionServiceVersion": COGNIX_MESSAGE_ENCRYPTION_SERVICE_VERSION,
        "chatPolicyServiceVersion": COGNIX_CHAT_POLICY_SERVICE_VERSION,
        "mode": "enterprise_chat_creation_plan",
        "organizationId": _safe_key(organization_id, DEFAULT_ORGANIZATION_ID),
        "projectId": _safe_text(project_id, 160) or None,
        "chat": {
            "title": _safe_text(title, 180, "Enterprise chat"),
            "mode": mode,
            "status": "ready" if group_ready else "needs_participant",
            "participantCount": len(normalized_participants),
            "groupReady": group_ready,
        },
        "participants": normalized_participants,
        "policy": normalized_policy,
        "keyPlan": {
            "clientSideGenerationRequired": normalized_policy["clientSideKeysRequired"],
            "serverStoresKeyMaterial": False,
            "serverStoresPublicKeyMetadata": True,
            "rotationRequiredOnMemberChange": True,
            "revocationSupported": True,
            "recoveryPolicy": normalized_policy["recoveryPolicy"],
        },
        "messagePlan": {
            "plaintextAcceptedByBackend": False,
            "encryptedPayloadRequired": True,
            "serverCanDecrypt": False,
            "serverCanIndexContent": normalized_policy["serverIndexingAllowed"],
            "localSearchOnly": normalized_policy["localSearchOnly"],
        },
        "sideEffects": build_enterprise_chat_blueprint()["sideEffects"],
    }


def build_encrypted_message_plan(
    *,
    username: str,
    chat: dict[str, Any],
    encrypted_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chat_payload = _as_dict(chat.get("payload") or chat)
    chat_record = _as_dict(chat_payload.get("chat"))
    policy = normalize_chat_policy(chat_payload.get("policy"), chat_mode = chat_record.get("mode") or "e2ee")
    envelope = deepcopy(_as_dict(encrypted_payload))
    ciphertext = _safe_text(envelope.get("ciphertext") or envelope.get("sealedPayload"), 20000)
    nonce = _safe_text(envelope.get("nonce"), 300)
    key_id = _safe_text(envelope.get("keyId") or envelope.get("key_id"), 180)
    has_encrypted_payload = bool(ciphertext and nonce and key_id)
    return {
        "messageEncryptionServiceVersion": COGNIX_MESSAGE_ENCRYPTION_SERVICE_VERSION,
        "e2eeKeyManagerVersion": COGNIX_E2EE_KEY_MANAGER_VERSION,
        "mode": "encrypted_message_store_plan",
        "chatId": chat.get("id") or chat_payload.get("chatId"),
        "organizationId": chat.get("organization_id") or chat.get("organizationId") or chat_payload.get("organizationId"),
        "senderUsername": _safe_key(username, "user"),
        "valid": has_encrypted_payload,
        "blockedReasons": [] if has_encrypted_payload else ["encrypted_payload_required"],
        "message": {
            "ciphertextFingerprint": _fingerprint(ciphertext),
            "nonceFingerprint": _fingerprint(nonce),
            "keyId": key_id,
            "algorithm": _safe_text(envelope.get("algorithm"), 120, "xchacha20-poly1305"),
            "payloadBytesApprox": len(ciphertext.encode("utf-8")) if ciphertext else 0,
            "plaintextStored": False,
            "serverCanDecrypt": False,
            "serverCanIndexContent": policy["serverIndexingAllowed"],
            "metadataOnlyForAdmin": not policy["adminContentReadAllowed"],
        },
        "encryptedEnvelope": {
            "ciphertext": ciphertext,
            "nonce": nonce,
            "keyId": key_id,
            "algorithm": _safe_text(envelope.get("algorithm"), 120, "xchacha20-poly1305"),
        },
        "metadata": deepcopy(_as_dict(metadata)),
        "sideEffects": build_enterprise_chat_blueprint()["sideEffects"],
    }


def build_key_rotation_plan(
    *,
    username: str,
    chat: dict[str, Any],
    reason: str | None = None,
    revoked_member: str | None = None,
) -> dict[str, Any]:
    chat_payload = _as_dict(chat.get("payload") or chat)
    chat_record = _as_dict(chat_payload.get("chat"))
    policy = normalize_chat_policy(chat_payload.get("policy"), chat_mode = chat_record.get("mode") or "e2ee")
    return {
        "e2eeKeyManagerVersion": COGNIX_E2EE_KEY_MANAGER_VERSION,
        "mode": "key_rotation_plan",
        "chatId": chat.get("id") or chat_payload.get("chatId"),
        "requestedBy": _safe_key(username, "user"),
        "reason": _safe_text(reason, 500, "manual_rotation"),
        "revokedMember": _safe_key(revoked_member, "") or None,
        "clientActionRequired": policy["clientSideKeysRequired"],
        "serverGeneratesKeys": False,
        "serverStoresKeyMaterial": False,
        "metadataUpdateRequired": True,
        "memberRevocationRequiresRotation": True,
        "sideEffects": build_enterprise_chat_blueprint()["sideEffects"],
    }
