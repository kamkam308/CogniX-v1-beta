# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Personal AI Twin planning.

The twin is a user-controlled personalization profile. It can describe style,
preferences, skills, and safe personalization hints, but it never acts as an
autonomous clone and never writes storage by itself.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


COGNIX_PERSONAL_TWIN_SERVICE_VERSION = "cognix_personal_twin_service_v1"
COGNIX_STYLE_PROFILER_VERSION = "cognix_style_profiler_v1"
COGNIX_PREFERENCE_MODEL_VERSION = "cognix_preference_model_v1"
COGNIX_PERSONALIZATION_ENGINE_VERSION = "cognix_personalization_engine_v1"


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _ascii_lower(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _normalize(value))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _text_from_interaction(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    return " ".join(
        str(value.get(key) or "")
        for key in (
            "text",
            "content",
            "message",
            "summary",
            "objective",
            "instruction",
            "prompt",
            "response",
            "title",
        )
        if value.get(key)
    )


def _excerpt(text: str, limit: int = 420) -> str:
    normalized = _normalize(text)
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _keyword_count(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    matched = [keyword for keyword in keywords if keyword in text]
    return len(matched), matched[:8]


def _style_signal(
    *,
    key: str,
    value: str,
    confidence: float,
    evidence: list[str],
    source: str = "deterministic_keyword_profile",
) -> dict[str, Any]:
    return {
        "styleKey": key,
        "styleValue": value,
        "confidence": round(max(0.0, min(float(confidence), 0.99)), 3),
        "evidence": evidence,
        "source": source,
    }


def _preference_rule(
    *,
    key: str,
    rule_type: str,
    text: str,
    confidence: float,
    evidence: list[str],
    editable: bool = True,
) -> dict[str, Any]:
    return {
        "ruleKey": key,
        "ruleType": rule_type,
        "ruleText": text,
        "confidence": round(max(0.0, min(float(confidence), 0.99)), 3),
        "evidence": evidence,
        "status": "proposed",
        "editable": editable,
        "requiresUserActivation": True,
    }


def build_personal_twin_blueprint() -> dict[str, Any]:
    return {
        "personalTwinServiceVersion": COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
        "styleProfilerVersion": COGNIX_STYLE_PROFILER_VERSION,
        "preferenceModelVersion": COGNIX_PREFERENCE_MODEL_VERSION,
        "personalizationEngineVersion": COGNIX_PERSONALIZATION_ENGINE_VERSION,
        "mode": "controlled_personalization_profile",
        "services": [
            "PersonalTwinService",
            "StyleProfiler",
            "PreferenceModel",
            "PersonalizationEngine",
        ],
        "pipeline": [
            "interactions",
            "style_extraction",
            "preference_model",
            "skill_profile",
            "personalization_layer",
        ],
        "userControls": {
            "activate": True,
            "deactivate": True,
            "modify": True,
            "export": True,
            "reset": True,
            "reviewBeforeUse": True,
        },
        "safetyPolicy": {
            "userControlledOnly": True,
            "autonomousCloneAllowed": False,
            "rawInteractionStorageAllowed": False,
            "userCanDisable": True,
            "exportable": True,
            "resettable": True,
            "modelIndependent": True,
            "profileInjectionRequiresActivation": True,
        },
        "sideEffects": {
            "profileWrite": False,
            "styleProfileWrite": False,
            "ruleWrite": False,
            "memoryWrite": False,
            "contextInjection": False,
            "autonomousAction": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def _language_profile(text: str) -> dict[str, Any]:
    french_count, french = _keyword_count(
        text,
        [
            "francais",
            "reponds en francais",
            "en francais",
            "mot de passe",
            "securite",
            "connexion",
            "corrige",
            "continue",
            "natif",
            "permanent",
        ],
    )
    english_count, english = _keyword_count(
        text,
        ["english", "answer in english", "setup", "login", "password", "training"],
    )
    if french_count > english_count:
        return _style_signal(
            key = "language_preference",
            value = "fr",
            confidence = 0.62 + min(french_count, 5) * 0.06,
            evidence = french,
        )
    if english_count > french_count:
        return _style_signal(
            key = "language_preference",
            value = "en",
            confidence = 0.55 + min(english_count, 5) * 0.06,
            evidence = english,
        )
    return _style_signal(
        key = "language_preference",
        value = "mixed",
        confidence = 0.35,
        evidence = [],
    )


def _response_depth_profile(text: str) -> dict[str, Any]:
    concise_count, concise = _keyword_count(text, ["concis", "court", "simple", "direct", "vite"])
    detailed_count, detailed = _keyword_count(
        text,
        ["detail", "explique", "architecture", "roadmap", "objectif globale", "analyse"],
    )
    if concise_count > detailed_count:
        return _style_signal(
            key = "response_depth",
            value = "concise",
            confidence = 0.58 + min(concise_count, 4) * 0.07,
            evidence = concise,
        )
    if detailed_count > 0:
        return _style_signal(
            key = "response_depth",
            value = "detailed_when_complex",
            confidence = 0.54 + min(detailed_count, 5) * 0.06,
            evidence = detailed,
        )
    return _style_signal(key = "response_depth", value = "balanced", confidence = 0.42, evidence = [])


def _work_method_profile(text: str) -> dict[str, Any]:
    autonomous_count, autonomous = _keyword_count(
        text,
        ["autonome", "ne demande plus", "continue", "termine", "carte blanche", "permanent"],
    )
    step_count, step = _keyword_count(text, ["avant de continuer", "attend", "approuver", "ne modifie rien"])
    if autonomous_count >= max(1, step_count):
        return _style_signal(
            key = "work_method",
            value = "autonomous_native_execution",
            confidence = 0.6 + min(autonomous_count, 5) * 0.06,
            evidence = autonomous,
        )
    if step_count:
        return _style_signal(
            key = "work_method",
            value = "approval_gated_for_product_changes",
            confidence = 0.58 + min(step_count, 5) * 0.06,
            evidence = step,
        )
    return _style_signal(key = "work_method", value = "collaborative", confidence = 0.4, evidence = [])


def _coding_style_profile(text: str) -> dict[str, Any]:
    native_count, native = _keyword_count(
        text,
        ["code source", "natif", "permanent", "pas une surcouche", "github", "tests", "backend"],
    )
    security_count, security = _keyword_count(text, ["securite", "secure", "permission", "https", "audit"])
    value = "native_source_changes"
    confidence = 0.52 + min(native_count, 5) * 0.06
    evidence = native
    if security_count > native_count:
        value = "security_first_native_changes"
        confidence = 0.54 + min(security_count, 5) * 0.06
        evidence = security
    return _style_signal(key = "coding_style", value = value, confidence = confidence, evidence = evidence)


def _learning_style_profile(text: str) -> dict[str, Any]:
    visual_count, visual = _keyword_count(text, ["screen", "capture", "regarde", "interface"])
    practical_count, practical = _keyword_count(text, ["teste", "lance", "verifie", "ça marche", "corrige"])
    if visual_count > practical_count:
        return _style_signal(
            key = "learning_style",
            value = "visual_feedback",
            confidence = 0.52 + min(visual_count, 5) * 0.06,
            evidence = visual,
        )
    if practical_count:
        return _style_signal(
            key = "learning_style",
            value = "practical_iteration",
            confidence = 0.54 + min(practical_count, 5) * 0.06,
            evidence = practical,
        )
    return _style_signal(key = "learning_style", value = "hands_on", confidence = 0.4, evidence = [])


def build_personal_twin_profile_plan(
    *,
    username: str,
    interactions: list[Any],
    existing_profile: dict[str, Any] | None = None,
    activate: bool = False,
) -> dict[str, Any]:
    text_items = [_text_from_interaction(item) for item in interactions]
    joined_text = " ".join(item for item in text_items if item)
    normalized_text = _ascii_lower(joined_text)
    evidence_excerpt = _excerpt(joined_text)
    styles = [
        _language_profile(normalized_text),
        _response_depth_profile(normalized_text),
        _work_method_profile(normalized_text),
        _coding_style_profile(normalized_text),
        _learning_style_profile(normalized_text),
    ]
    style_map = {item["styleKey"]: item["styleValue"] for item in styles}
    rules: list[dict[str, Any]] = []
    if style_map.get("language_preference") == "fr":
        rules.append(
            _preference_rule(
                key = "reply_language_fr",
                rule_type = "communication",
                text = "Prefer French for product and coding collaboration unless the user asks otherwise.",
                confidence = 0.86,
                evidence = styles[0].get("evidence") or [evidence_excerpt],
            )
        )
    if style_map.get("work_method") == "autonomous_native_execution":
        rules.append(
            _preference_rule(
                key = "autonomous_native_work",
                rule_type = "workflow",
                text = "When authorized, complete implementation, verification, sync, and Git preservation without repeated permission prompts.",
                confidence = 0.9,
                evidence = styles[2].get("evidence") or [evidence_excerpt],
            )
        )
    if "native" in str(style_map.get("coding_style")):
        rules.append(
            _preference_rule(
                key = "native_source_only",
                rule_type = "engineering",
                text = "Prefer permanent source-code changes over superficial overlays.",
                confidence = 0.92,
                evidence = styles[3].get("evidence") or [evidence_excerpt],
            )
        )
    if "security" in normalized_text or "securite" in normalized_text:
        rules.append(
            _preference_rule(
                key = "security_first",
                rule_type = "security",
                text = "Treat security and regression protection as default constraints for CogniX changes.",
                confidence = 0.78,
                evidence = ["security" if "security" in normalized_text else "securite"],
            )
        )
    if "github" in normalized_text:
        rules.append(
            _preference_rule(
                key = "git_preservation",
                rule_type = "delivery",
                text = "Preserve stable checkpoints in Git so broken changes can be rolled back safely.",
                confidence = 0.82,
                evidence = ["github"],
            )
        )
    skills = {
        "strengths": [
            "product_iteration",
            "local_ai_runtime_setup",
            "frontend_quality_review",
            "security_awareness",
        ],
        "activeProjects": ["CogniX"],
        "preferredWorkflows": [
            "native_source_modification",
            "test_then_sync_active_build",
            "github_checkpoint_before_risky_changes",
        ],
    }
    confidence = round(
        min(0.96, 0.35 + 0.06 * len([item for item in styles if item["confidence"] >= 0.5]) + 0.04 * len(rules)),
        3,
    )
    profile_status = "active" if activate else str((existing_profile or {}).get("status") or "disabled")
    system_hints = [
        item["ruleText"]
        for item in rules
        if item["confidence"] >= 0.75
    ][:8]
    return {
        "personalTwinServiceVersion": COGNIX_PERSONAL_TWIN_SERVICE_VERSION,
        "styleProfilerVersion": COGNIX_STYLE_PROFILER_VERSION,
        "preferenceModelVersion": COGNIX_PREFERENCE_MODEL_VERSION,
        "personalizationEngineVersion": COGNIX_PERSONALIZATION_ENGINE_VERSION,
        "mode": "controlled_personalization_profile_plan",
        "username": username,
        "profile": {
            "displayName": f"{username} Personal AI Twin",
            "status": profile_status,
            "styleProfiles": styles,
            "preferenceRules": rules,
            "skillProfile": skills,
            "sourceSummary": {
                "interactionCount": len(interactions),
                "evidenceExcerpt": evidence_excerpt,
                "rawInteractionStorageAllowed": False,
            },
        },
        "personalizationLayer": {
            "safeToInject": bool(system_hints),
            "requiresUserActivation": True,
            "willInjectNow": False,
            "systemHints": system_hints,
        },
        "controls": build_personal_twin_blueprint()["userControls"],
        "safetyPolicy": build_personal_twin_blueprint()["safetyPolicy"],
        "summary": {
            "profileConfidence": confidence,
            "ruleCount": len(rules),
            "styleSignalCount": len(styles),
            "readyToActivate": bool(rules),
            "existingProfileStatus": (existing_profile or {}).get("status"),
        },
        "sideEffects": build_personal_twin_blueprint()["sideEffects"],
    }


def build_personalization_injection_plan(
    *,
    username: str,
    profile: dict[str, Any] | None,
    objective: str | None = None,
) -> dict[str, Any]:
    profile = profile or {}
    status = str(profile.get("status") or "disabled")
    profile_payload = profile.get("profile") if isinstance(profile.get("profile"), dict) else {}
    rules = profile.get("personalizationRules") if isinstance(profile.get("personalizationRules"), list) else []
    objective_text = _ascii_lower(objective)
    selected_rules: list[dict[str, Any]] = []
    objective_tokens = set(re.findall(r"[a-z0-9_+-]{4,}", objective_text))
    for rule in rules:
        if not isinstance(rule, dict) or str(rule.get("status") or "active") != "active":
            continue
        haystack = _ascii_lower(
            " ".join(
                [
                    str(rule.get("ruleKey") or rule.get("rule_key") or ""),
                    str(rule.get("ruleType") or rule.get("rule_type") or ""),
                    str(rule.get("ruleText") or rule.get("rule_text") or ""),
                ]
            )
        )
        haystack_tokens = set(re.findall(r"[a-z0-9_+-]{4,}", haystack))
        if (
            not objective_text
            or any(token in objective_text for token in haystack_tokens)
            or any(token in haystack for token in objective_tokens)
        ):
            selected_rules.append(rule)
    active = status == "active"
    hints = [
        str(item.get("ruleText") or item.get("rule_text") or "")
        for item in selected_rules
        if item.get("ruleText") or item.get("rule_text")
    ][:8]
    return {
        "personalizationEngineVersion": COGNIX_PERSONALIZATION_ENGINE_VERSION,
        "mode": "personalization_injection_dry_run",
        "username": username,
        "objective": objective,
        "profileStatus": status,
        "activeProfileRequired": True,
        "willInjectNow": False,
        "safeToInject": active and bool(hints),
        "selectedRuleKeys": [str(item.get("ruleKey") or item.get("rule_key") or "") for item in selected_rules],
        "systemHints": hints if active else [],
        "profileSummary": {
            "displayName": profile.get("displayName") or profile_payload.get("displayName"),
            "styleProfileCount": len(profile.get("styleProfiles") or []),
            "ruleCount": len(rules),
            "selectedRuleCount": len(hints) if active else 0,
        },
        "sideEffects": {
            "contextInjection": False,
            "profileWrite": False,
            "ruleWrite": False,
            "autonomousAction": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }
