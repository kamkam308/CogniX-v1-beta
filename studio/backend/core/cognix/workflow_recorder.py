# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI workflow recording and replay planning.

The recorder captures reusable workflow structure. The runner only builds a
dry-run replay plan here; it never calls tools, models, exporters, or cloud
services by itself.
"""

from __future__ import annotations

from typing import Any


COGNIX_WORKFLOW_RECORDER_VERSION = "cognix_workflow_recorder_v1"
COGNIX_WORKFLOW_RUNNER_VERSION = "cognix_workflow_runner_v1"
COGNIX_WORKFLOW_TEMPLATE_MANAGER_VERSION = "cognix_workflow_template_manager_v1"

WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "rag_workflow",
        "workflowType": "rag",
        "label": "Workflow RAG",
        "steps": [
            {"stepType": "user_action", "label": "Importer les documents"},
            {"stepType": "tool_call", "label": "Indexer les sources"},
            {"stepType": "model_call", "label": "Repondre avec citations"},
            {"stepType": "export", "label": "Exporter le resultat"},
        ],
    },
    {
        "id": "fine_tuning_workflow",
        "workflowType": "fine_tuning",
        "label": "Workflow fine-tuning",
        "steps": [
            {"stepType": "user_action", "label": "Importer le dataset"},
            {"stepType": "tool_call", "label": "Valider le format"},
            {"stepType": "model_call", "label": "Planifier LoRA ou QLoRA"},
            {"stepType": "export", "label": "Exporter le plan d'entrainement"},
        ],
    },
    {
        "id": "code_workflow",
        "workflowType": "code",
        "label": "Workflow code",
        "steps": [
            {"stepType": "user_action", "label": "Decrire la modification"},
            {"stepType": "tool_call", "label": "Lire les fichiers utiles"},
            {"stepType": "model_call", "label": "Generer le patch"},
            {"stepType": "tool_call", "label": "Lancer les tests"},
        ],
    },
    {
        "id": "document_workflow",
        "workflowType": "document",
        "label": "Workflow document",
        "steps": [
            {"stepType": "user_action", "label": "Importer le document"},
            {"stepType": "model_call", "label": "Resumer"},
            {"stepType": "model_call", "label": "Extraire les QCM"},
            {"stepType": "export", "label": "Generer la fiche"},
        ],
    },
]

SAFE_STEP_TYPES = {"user_action", "tool_call", "model_call", "parameters", "output", "export", "approval"}


def _text(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _workflow_type(value: str | None) -> str:
    normalized = _text(value, "custom").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "rag": "rag",
        "retrieval": "rag",
        "fine_tuning": "fine_tuning",
        "finetuning": "fine_tuning",
        "training": "fine_tuning",
        "code": "code",
        "coding": "code",
        "document": "document",
        "docs": "document",
    }
    return aliases.get(normalized, normalized or "custom")


def _template_for_type(workflow_type: str) -> dict[str, Any] | None:
    return next((item for item in WORKFLOW_TEMPLATES if item["workflowType"] == workflow_type), None)


def _normalize_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    step_type = _text(step.get("stepType") or step.get("step_type"), "user_action").lower()
    if step_type not in SAFE_STEP_TYPES:
        step_type = "user_action"
    label = _text(step.get("label") or step.get("title"), f"Step {index + 1}")
    return {
        "stepIndex": index,
        "stepType": step_type,
        "label": label[:240],
        "toolName": _text(step.get("toolName") or step.get("tool_name"))[:160] or None,
        "modelId": _text(step.get("modelId") or step.get("model_id"))[:240] or None,
        "parameters": step.get("parameters") if isinstance(step.get("parameters"), dict) else {},
        "outputSummary": _text(step.get("outputSummary") or step.get("output") or step.get("summary"))[:2000],
        "requiresApproval": bool(step.get("requiresApproval", step_type in {"tool_call", "model_call", "export"})),
        "willExecuteNow": False,
    }


def build_workflow_blueprint() -> dict[str, Any]:
    return {
        "workflowRecorderVersion": COGNIX_WORKFLOW_RECORDER_VERSION,
        "workflowRunnerVersion": COGNIX_WORKFLOW_RUNNER_VERSION,
        "workflowTemplateManagerVersion": COGNIX_WORKFLOW_TEMPLATE_MANAGER_VERSION,
        "mode": "declarative_workflow_contract",
        "services": ["WorkflowRecorder", "WorkflowRunner", "WorkflowTemplateManager"],
        "userControls": {
            "record": True,
            "replay": True,
            "edit": True,
            "share": True,
            "export": True,
            "delete": True,
            "requireConfirmationBeforeReplay": True,
        },
        "stepTypes": sorted(SAFE_STEP_TYPES),
        "runnerPolicy": {
            "dryRunByDefault": True,
            "executeWithoutUserConfirmation": False,
            "frontendDirectToolExecutionAllowed": False,
            "frontendDirectModelCallAllowed": False,
            "rawSecretCaptureAllowed": False,
        },
        "sideEffects": {
            "workflowWrite": False,
            "workflowRunWrite": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
            "exportWrite": False,
            "networkCall": False,
        },
    }


def build_workflow_template_registry() -> dict[str, Any]:
    return {
        "workflowTemplateManagerVersion": COGNIX_WORKFLOW_TEMPLATE_MANAGER_VERSION,
        "mode": "template_registry",
        "templates": WORKFLOW_TEMPLATES,
        "summary": {
            "templateCount": len(WORKFLOW_TEMPLATES),
            "workflowTypes": [item["workflowType"] for item in WORKFLOW_TEMPLATES],
        },
        "sideEffects": build_workflow_blueprint()["sideEffects"],
    }


def build_workflow_recording_plan(
    *,
    username: str,
    title: str | None,
    objective: str | None = None,
    workflow_type: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = _workflow_type(workflow_type)
    template = _template_for_type(normalized_type)
    source_steps = steps if steps else list((template or {}).get("steps") or [])
    normalized_steps = [_normalize_step(step, index) for index, step in enumerate(source_steps)]
    return {
        "workflowRecorderVersion": COGNIX_WORKFLOW_RECORDER_VERSION,
        "workflowTemplateManagerVersion": COGNIX_WORKFLOW_TEMPLATE_MANAGER_VERSION,
        "mode": "workflow_recording_plan",
        "username": username,
        "workflow": {
            "title": _text(title, (template or {}).get("label") or "Workflow CogniX")[:240],
            "objective": _text(objective)[:4000],
            "workflowType": normalized_type,
            "projectId": project_id,
            "status": "active",
            "shareStatus": "private",
            "metadata": metadata or {},
        },
        "steps": normalized_steps,
        "summary": {
            "stepCount": len(normalized_steps),
            "requiresApprovalCount": len([item for item in normalized_steps if item["requiresApproval"]]),
            "templateId": (template or {}).get("id"),
        },
        "sideEffects": build_workflow_blueprint()["sideEffects"],
    }


def build_workflow_run_plan(
    *,
    username: str,
    workflow: dict[str, Any],
    steps: list[dict[str, Any]],
    run_mode: str = "dry_run",
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered_steps = sorted(steps, key = lambda item: int(item.get("step_index", item.get("stepIndex", 0)) or 0))
    planned_steps = []
    for step in ordered_steps:
        planned_steps.append(
            {
                "stepId": step.get("id"),
                "stepIndex": int(step.get("step_index", step.get("stepIndex", 0)) or 0),
                "stepType": step.get("step_type") or step.get("stepType"),
                "label": step.get("label"),
                "requiresApproval": True,
                "willExecuteNow": False,
                "blockedSideEffects": ["toolExecution", "modelLoad", "generation", "exportWrite", "networkCall"],
            }
        )
    return {
        "workflowRunnerVersion": COGNIX_WORKFLOW_RUNNER_VERSION,
        "mode": "workflow_replay_dry_run",
        "username": username,
        "workflowId": workflow.get("id"),
        "runMode": "dry_run" if run_mode != "simulation" else "simulation",
        "inputs": inputs or {},
        "orderedSteps": planned_steps,
        "summary": {
            "stepCount": len(planned_steps),
            "willExecuteNow": False,
            "requiresUserConfirmation": True,
        },
        "sideEffects": build_workflow_blueprint()["sideEffects"],
    }
