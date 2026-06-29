# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX semantic cache planning.

The semantic cache planner prepares privacy-safe lookup/write contracts for
future response reuse. It never embeds text, reads a vector index, writes cache
entries, or returns raw hidden context.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_SEMANTIC_CACHE_VERSION = "cognix_semantic_cache_v1"
COGNIX_SEMANTIC_CACHE_POLICY_VERSION = "cognix_semantic_cache_policy_v1"
COGNIX_SEMANTIC_REUSE_CONTRACT_VERSION = "cognix_semantic_reuse_contract_v1"

SENSITIVE_TERMS = {
    "api_key",
    "apikey",
    "bearer",
    "client_secret",
    "credential",
    "jwt",
    "mot de passe",
    "password",
    "private_key",
    "secret",
    "token",
}

CACHEABLE_TASK_TERMS = {
    "explain",
    "explique",
    "resume",
    "résume",
    "summarize",
    "definition",
    "définition",
    "compare",
    "qcm",
    "revision",
    "révision",
    "template",
    "boilerplate",
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split())


def _keywords(text: str) -> set[str]:
    return {
        item.casefold()
        for item in re.findall(r"[a-zA-Z0-9_+-]{3,}", text or "")
        if item.casefold() not in {"avec", "dans", "pour", "that", "this", "from", "have", "will"}
    }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sensitivity(prompt: str, sensitivity_level: str | None) -> dict[str, Any]:
    normalized_level = str(sensitivity_level or "").strip().casefold()
    prompt_lower = prompt.casefold()
    matched_terms = sorted(term for term in SENSITIVE_TERMS if term in prompt_lower)
    if normalized_level in {"restricted", "secret", "highly_confidential"} or matched_terms:
        level = "restricted"
    elif normalized_level in {"confidential", "private", "sensitive"}:
        level = "confidential"
    elif normalized_level in {"public", "low"}:
        level = "public"
    else:
        level = "standard"
    return {
        "level": level,
        "matchedSensitiveTermIds": matched_terms[:12],
        "cacheLookupAllowed": level not in {"restricted"},
        "cacheWriteEligible": level in {"public", "standard"},
    }


def _scope(username: str, project_id: str | None, project_type: str | None, sensitivity: dict[str, Any]) -> dict[str, Any]:
    if sensitivity["level"] in {"confidential", "restricted"}:
        scope_type = "user_private"
    elif project_id:
        scope_type = "project_private"
    else:
        scope_type = "user_private"
    namespace_source = f"{scope_type}:{username}:{project_id or 'general'}:{project_type or 'general'}"
    return {
        "scopeType": scope_type,
        "namespaceHash": _hash_text(namespace_source)[:24],
        "usernameBound": True,
        "projectBound": bool(project_id),
        "organizationSharingAllowed": False,
        "crossUserReuseAllowed": False,
    }


def _cacheability(prompt: str, task_type: str | None, requires_sources: bool, sensitivity: dict[str, Any]) -> dict[str, Any]:
    terms = _keywords(prompt)
    matched_task_terms = sorted(terms & CACHEABLE_TASK_TERMS)
    token_count = max(1, len(re.findall(r"\S+", prompt)))
    if not sensitivity["cacheLookupAllowed"]:
        status = "blocked_sensitive"
        score = 0.0
    else:
        base = 0.34
        base += min(0.28, len(matched_task_terms) * 0.07)
        base += 0.16 if requires_sources else 0.0
        base += 0.12 if str(task_type or "").casefold() in {"education", "research", "rag", "general"} else 0.0
        base += 0.1 if 8 <= token_count <= 240 else 0.0
        score = round(min(base, 0.92), 3)
        status = "eligible" if score >= 0.58 else "lookup_only"
    return {
        "status": status,
        "score": score,
        "tokenCount": token_count,
        "matchedTaskTerms": matched_task_terms,
        "requiresSources": requires_sources,
    }


def build_semantic_cache_plan(
    *,
    username: str,
    prompt: str,
    project_id: str | None = None,
    project_type: str | None = None,
    task_type: str | None = None,
    model_id: str | None = None,
    sensitivity_level: str | None = None,
    requires_sources: bool = False,
    context_hashes: list[str] | None = None,
) -> dict[str, Any]:
    normalized_prompt = _normalize(prompt)
    prompt_hash = _hash_text(normalized_prompt)
    sensitivity = _sensitivity(normalized_prompt, sensitivity_level)
    scope = _scope(username, project_id, project_type, sensitivity)
    cacheability = _cacheability(normalized_prompt, task_type, requires_sources, sensitivity)
    context_hashes_clean = [
        str(item).strip()
        for item in (context_hashes or [])
        if str(item or "").strip()
    ][:20]
    cache_key_source = ":".join(
        [
            scope["namespaceHash"],
            prompt_hash,
            str(model_id or "any-model"),
            str(project_type or "general"),
            *context_hashes_clean,
        ]
    )
    cache_key_hash = _hash_text(cache_key_source)
    ready_for_lookup = bool(sensitivity["cacheLookupAllowed"] and normalized_prompt)
    write_eligible_after_validation = bool(
        ready_for_lookup
        and sensitivity["cacheWriteEligible"]
        and cacheability["status"] == "eligible"
    )
    return {
        "semanticCacheVersion": COGNIX_SEMANTIC_CACHE_VERSION,
        "policyVersion": COGNIX_SEMANTIC_CACHE_POLICY_VERSION,
        "reuseContractVersion": COGNIX_SEMANTIC_REUSE_CONTRACT_VERSION,
        "mode": "semantic_cache_plan_dry_run",
        "username": username,
        "projectId": project_id,
        "projectType": project_type,
        "requestSignature": prompt_hash[:24],
        "cacheKeyPlan": {
            "namespaceHash": scope["namespaceHash"],
            "cacheKeyHash": cache_key_hash,
            "promptHash": prompt_hash,
            "modelId": model_id,
            "contextHashCount": len(context_hashes_clean),
            "rawPromptStoredInKey": False,
        },
        "scope": scope,
        "sensitivity": sensitivity,
        "cacheability": cacheability,
        "lookupPlan": {
            "readyForLookup": ready_for_lookup,
            "willLookupNow": False,
            "requiresEmbeddingIndex": True,
            "embeddingGenerationAllowedHere": False,
            "minimumSimilarity": 0.88 if requires_sources else 0.84,
            "maxCandidateCount": 5,
            "allowedCandidateSources": ["same_user", "same_project"] if project_id else ["same_user"],
        },
        "writePlan": {
            "writeEligibleAfterValidation": write_eligible_after_validation,
            "willWriteNow": False,
            "requiresResponseReflection": True,
            "requiresBenchmarkEvidence": True,
            "requiresPermissionSnapshot": True,
            "ttlSeconds": 7 * 24 * 60 * 60 if sensitivity["level"] == "public" else 24 * 60 * 60,
        },
        "reuseContract": {
            "contractVersion": COGNIX_SEMANTIC_REUSE_CONTRACT_VERSION,
            "readyForReuse": False,
            "automaticReuseAllowed": False,
            "frontendDirectReuseAllowed": False,
            "requiresSameUser": True,
            "requiresProjectScopeMatch": bool(project_id),
            "requiresModelCompatibility": True,
            "requiresSourceRevalidation": bool(requires_sources),
            "requiresHumanReviewForHighImpact": True,
            "blockedActions": [
                "cache_lookup",
                "cache_write",
                "response_reuse",
                "embedding_generation",
                "cross_user_read",
                "raw_prompt_storage",
            ],
            "nextRequiredGate": (
                "sensitivity_review"
                if not sensitivity["cacheLookupAllowed"]
                else "semantic_index_executor"
            ),
        },
        "invalidationPolicy": {
            "invalidateOnModelChange": True,
            "invalidateOnPromptPolicyChange": True,
            "invalidateOnProjectPermissionChange": True,
            "invalidateOnSourceDocumentChange": bool(requires_sources),
            "invalidateOnMemoryScopeChange": True,
        },
        "sideEffects": {
            "cacheLookup": False,
            "cacheWrite": False,
            "embeddingGeneration": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "promptMutation": False,
            "rawPromptStorage": False,
            "crossUserRead": False,
        },
    }
