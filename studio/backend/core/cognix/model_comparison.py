# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX live model comparison planning.

This module prepares a side-by-side comparison contract. It can evaluate
provided outputs deterministically and record a user choice through the API,
but it does not call models or start parallel inference by itself.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


COGNIX_MODEL_COMPARISON_SERVICE_VERSION = "cognix_model_comparison_service_v1"
COGNIX_PARALLEL_INFERENCE_RUNNER_VERSION = "cognix_parallel_inference_runner_v1"
COGNIX_RESPONSE_EVALUATOR_VERSION = "cognix_response_evaluator_v1"


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _words(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_+-]{3,}", value.lower())


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(_normalize(prompt).encode("utf-8")).hexdigest()[:24]


def _model_id(model: dict[str, Any], index: int) -> str:
    return str(model.get("modelId") or model.get("id") or f"model_{index + 1}")[:180]


def _model_label(model: dict[str, Any], index: int) -> str:
    return str(model.get("label") or model.get("modelLabel") or _model_id(model, index))[:240]


def _output_for_model(outputs: list[dict[str, Any]], model_id: str) -> dict[str, Any] | None:
    for output in outputs:
        if str(output.get("modelId") or output.get("id") or "") == model_id:
            return output
    return None


def build_model_comparison_blueprint() -> dict[str, Any]:
    return {
        "modelComparisonServiceVersion": COGNIX_MODEL_COMPARISON_SERVICE_VERSION,
        "parallelInferenceRunnerVersion": COGNIX_PARALLEL_INFERENCE_RUNNER_VERSION,
        "responseEvaluatorVersion": COGNIX_RESPONSE_EVALUATOR_VERSION,
        "mode": "side_by_side_model_comparison_contract",
        "services": [
            "ModelComparisonService",
            "ParallelInferenceRunner",
            "ResponseEvaluator",
        ],
        "pipeline": [
            "prompt",
            "parallel_model_calls",
            "response_collection",
            "optional_evaluator",
            "side_by_side_ui",
            "user_selection",
        ],
        "uiContract": {
            "layout": "responsive_split_view",
            "buttonLabel": "Comparer avec d'autres modeles",
            "userCanChooseBestResponse": True,
            "rawReasoningVisible": False,
        },
        "policies": {
            "backendOrchestratorRequired": True,
            "frontendDirectModelCallAllowed": False,
            "parallelExecutionRequiresExplicitAction": True,
            "userPreferenceIsStoredOnlyAfterChoice": True,
            "cloudModelAllowedByPolicy": True,
        },
        "sideEffects": {
            "comparisonWrite": False,
            "outputWrite": False,
            "preferenceWrite": False,
            "parallelModelCall": False,
            "modelLoad": False,
            "generation": False,
            "networkModelCall": False,
            "toolExecution": False,
        },
    }


def _evaluate_output(prompt: str, output_text: str, model: dict[str, Any]) -> dict[str, Any]:
    prompt_words = set(_words(prompt))
    output_words = _words(output_text)
    output_word_set = set(output_words)
    overlap = len(prompt_words & output_word_set)
    relevance = 0.0 if not prompt_words else min(1.0, overlap / max(3, len(prompt_words)))
    length_score = 0.35
    if 30 <= len(output_words) <= 260:
        length_score = 0.9
    elif 12 <= len(output_words) < 30 or 260 < len(output_words) <= 520:
        length_score = 0.62
    role = str(model.get("role") or model.get("domain") or "").lower()
    specialty_score = 0.5
    if role and any(token in prompt_words for token in _words(role)):
        specialty_score = 0.86
    if any(token in prompt_words for token in ("code", "python", "typescript", "debug")) and any(
        marker in output_text for marker in ("```", "def ", "const ", "function ")
    ):
        specialty_score = max(specialty_score, 0.82)
    score = round((relevance * 0.48) + (length_score * 0.32) + (specialty_score * 0.20), 3)
    return {
        "score": score,
        "relevanceScore": round(relevance, 3),
        "lengthScore": round(length_score, 3),
        "specialtyScore": round(specialty_score, 3),
        "wordCount": len(output_words),
        "signals": {
            "promptOverlap": overlap,
            "modelRole": role or None,
            "hasCodeShape": "```" in output_text,
        },
    }


def build_model_comparison_plan(
    *,
    prompt: str,
    models: list[dict[str, Any]],
    outputs: list[dict[str, Any]] | None = None,
    evaluator_enabled: bool = True,
    project_id: str | None = None,
    comparison_id: str | None = None,
) -> dict[str, Any]:
    normalized_prompt = _normalize(prompt)
    provided_outputs = [item for item in (outputs or []) if isinstance(item, dict)]
    candidates: list[dict[str, Any]] = []
    for index, model in enumerate([item for item in models if isinstance(item, dict)]):
        model_id = _model_id(model, index)
        output = _output_for_model(provided_outputs, model_id)
        output_text = _normalize((output or {}).get("outputText") or (output or {}).get("content") or "")
        evaluation = _evaluate_output(normalized_prompt, output_text, model) if output_text and evaluator_enabled else {}
        candidates.append(
            {
                "modelId": model_id,
                "modelLabel": _model_label(model, index),
                "providerType": str(model.get("providerType") or model.get("provider") or "local")[:80],
                "role": model.get("role") or model.get("domain") or "general",
                "status": "response_collected" if output_text else "awaiting_generation",
                "outputText": output_text,
                "evaluation": evaluation,
                "requiresBackendGeneration": not bool(output_text),
                "willGenerateNow": False,
            }
        )
    ranked = sorted(
        [item for item in candidates if item.get("evaluation")],
        key = lambda item: float(item.get("evaluation", {}).get("score") or 0.0),
        reverse = True,
    )
    return {
        "modelComparisonServiceVersion": COGNIX_MODEL_COMPARISON_SERVICE_VERSION,
        "parallelInferenceRunnerVersion": COGNIX_PARALLEL_INFERENCE_RUNNER_VERSION,
        "responseEvaluatorVersion": COGNIX_RESPONSE_EVALUATOR_VERSION,
        "mode": "comparison_plan_dry_run",
        "comparisonId": comparison_id,
        "projectId": project_id,
        "promptHash": _prompt_hash(normalized_prompt),
        "promptExcerpt": normalized_prompt[:600],
        "models": candidates,
        "parallelCallPlan": {
            "enabled": True,
            "plannedCallCount": len(candidates),
            "readyForParallelCalls": len(candidates) >= 2,
            "willCallModelsNow": False,
            "runnerVersion": COGNIX_PARALLEL_INFERENCE_RUNNER_VERSION,
        },
        "evaluator": {
            "enabled": bool(evaluator_enabled),
            "method": "deterministic_quality_signals",
            "rawReasoningVisible": False,
            "rankedModelIds": [item["modelId"] for item in ranked],
            "recommendedModelId": ranked[0]["modelId"] if ranked else None,
        },
        "userChoice": {
            "canSelectBestResponse": True,
            "selectedOutputId": None,
            "preferenceWriteRequiresExplicitChoice": True,
        },
        "summary": {
            "modelCount": len(candidates),
            "collectedOutputCount": len([item for item in candidates if item["status"] == "response_collected"]),
            "awaitingGenerationCount": len([item for item in candidates if item["status"] == "awaiting_generation"]),
            "readyForSideBySideUi": len(candidates) >= 2,
        },
        "sideEffects": build_model_comparison_blueprint()["sideEffects"],
    }
