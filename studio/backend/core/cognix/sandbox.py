# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX AI Sandbox planning.

The sandbox manager prepares isolated experiment plans for risky changes. It
never starts an isolated runtime, copies production secrets, runs tools, edits
files, promotes changes, or rolls back production state from the planner.
"""

from __future__ import annotations

from typing import Any


COGNIX_SANDBOX_MANAGER_VERSION = "cognix_sandbox_manager_v1"
COGNIX_ISOLATED_RUNTIME_VERSION = "cognix_isolated_runtime_v1"
COGNIX_EXPERIMENT_RUNNER_VERSION = "cognix_experiment_runner_v1"
COGNIX_ROLLBACK_SERVICE_VERSION = "cognix_rollback_service_v1"

SANDBOX_TARGET_TYPES: tuple[str, ...] = ("feature", "model", "tool", "code_change", "config_change")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_sandbox_target_type(value: str | None) -> str:
    target = _normalize(value).lower().replace(" ", "_").replace("-", "_") or "feature"
    aliases = {
        "fonctionnalite": "feature",
        "functionality": "feature",
        "modele": "model",
        "llm": "model",
        "outil": "tool",
        "plugin": "tool",
        "code": "code_change",
        "patch": "code_change",
        "modification": "code_change",
        "settings": "config_change",
        "configuration": "config_change",
    }
    target = aliases.get(target, target)
    return target if target in SANDBOX_TARGET_TYPES else "feature"


def build_sandbox_blueprint() -> dict[str, Any]:
    return {
        "sandboxManagerVersion": COGNIX_SANDBOX_MANAGER_VERSION,
        "isolatedRuntimeVersion": COGNIX_ISOLATED_RUNTIME_VERSION,
        "experimentRunnerVersion": COGNIX_EXPERIMENT_RUNNER_VERSION,
        "rollbackServiceVersion": COGNIX_ROLLBACK_SERVICE_VERSION,
        "mode": "ai_sandbox_contract",
        "services": ["SandboxManager", "IsolatedRuntime", "ExperimentRunner", "RollbackService"],
        "targetTypes": list(SANDBOX_TARGET_TYPES),
        "badge": {
            "label": "Mode sandbox actif",
            "visibleWhenActive": True,
            "designSystemReuseRequired": True,
        },
        "pipeline": [
            "create_isolated_environment",
            "copy_minimal_config",
            "test_modification",
            "collect_results",
            "delete_or_promote",
        ],
        "tables": ["cognix_sandboxes", "cognix_sandbox_runs", "cognix_sandbox_reports"],
        "security": {
            "productionSecretsAccessible": False,
            "productionDatabaseWritable": False,
            "productionConfigWritable": False,
            "networkDefaultAllowed": False,
            "autoPromotionAllowed": False,
            "rollbackTouchesProductionFromPlanner": False,
        },
        "sideEffects": {
            "sandboxWrite": False,
            "sandboxRunWrite": False,
            "sandboxReportWrite": False,
            "isolatedRuntimeStart": False,
            "minimalConfigCopy": False,
            "experimentRun": False,
            "productionSecretRead": False,
            "productionWrite": False,
            "networkCall": False,
            "fileWrite": False,
            "rollbackExecute": False,
            "promotion": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
        },
    }


def _risk_flags(text: str, requested_checks: list[str], target_type: str) -> dict[str, bool]:
    combined = f"{text} {' '.join(requested_checks)}".lower()
    return {
        "touchesSecrets": any(token in combined for token in ("secret", "token", "credential", "api key", "apikey", "password")),
        "touchesProduction": any(token in combined for token in ("production", "prod", "live", "deploy", "database", "auth")),
        "networkNeeded": any(token in combined for token in ("network", "http", "api", "webhook", "external", "internet")),
        "toolOrCode": target_type in {"tool", "code_change"},
        "modelRisk": target_type == "model",
    }


def _risk_level(flags: dict[str, bool]) -> str:
    if flags["touchesSecrets"] or flags["touchesProduction"]:
        return "high"
    if flags["toolOrCode"] or flags["networkNeeded"]:
        return "medium"
    return "low"


def _checks(target_type: str, requested_checks: list[str], flags: dict[str, bool]) -> list[dict[str, Any]]:
    defaults = [
        {"id": "smoke_test", "label": "Smoke test", "required": True},
        {"id": "permission_scan", "label": "Scan permissions", "required": True},
        {"id": "secret_redaction_check", "label": "Verifier absence de secrets prod", "required": True},
        {"id": "rollback_plan_check", "label": "Verifier plan de rollback", "required": True},
    ]
    if target_type == "model":
        defaults.append({"id": "model_load_dry_run", "label": "Plan de chargement modele", "required": True})
    if flags["networkNeeded"]:
        defaults.append({"id": "network_policy_review", "label": "Revue reseau", "required": True})
    requested = [
        {"id": f"custom_{index + 1}", "label": item[:160], "required": False}
        for index, item in enumerate(requested_checks[:12])
    ]
    return defaults + requested


def build_sandbox_plan(
    *,
    username: str,
    target_type: str | None,
    objective: str,
    change_summary: str,
    project_id: str | None = None,
    project_type: str | None = None,
    requested_checks: list[str] | None = None,
    duration_minutes: int = 30,
) -> dict[str, Any]:
    target = normalize_sandbox_target_type(target_type)
    clean_objective = _normalize(objective)[:4000] or "Tester en sandbox"
    clean_change = _normalize(change_summary)[:4000] or clean_objective
    clean_checks = [_normalize(item)[:240] for item in requested_checks or [] if _normalize(item)]
    try:
        duration = max(1, min(1440, int(duration_minutes)))
    except (TypeError, ValueError):
        duration = 30
    flags = _risk_flags(f"{clean_objective} {clean_change}", clean_checks, target)
    risk_level = _risk_level(flags)
    checks = _checks(target, clean_checks, flags)
    requires_human_approval = risk_level in {"medium", "high"} or flags["networkNeeded"]

    pipeline = [
        {
            "id": "create_isolated_environment",
            "service": "SandboxManager",
            "status": "planned",
            "willExecuteNow": False,
            "detail": "Creer un environnement ephemere separe de CogniX production.",
        },
        {
            "id": "copy_minimal_config",
            "service": "IsolatedRuntime",
            "status": "planned",
            "willExecuteNow": False,
            "detail": "Copier uniquement la configuration minimale redigee, sans secrets.",
        },
        {
            "id": "test_modification",
            "service": "ExperimentRunner",
            "status": "planned",
            "willExecuteNow": False,
            "detail": "Executer les checks dans l'environnement isole seulement apres confirmation.",
        },
        {
            "id": "collect_results",
            "service": "ExperimentRunner",
            "status": "planned",
            "willExecuteNow": False,
            "detail": "Collecter logs, erreurs et rapport agrege sans donnees brutes sensibles.",
        },
        {
            "id": "delete_or_promote",
            "service": "RollbackService",
            "status": "approval_required" if requires_human_approval else "planned",
            "willExecuteNow": False,
            "detail": "Supprimer la sandbox par defaut; promotion seulement apres revue.",
        },
    ]

    report = {
        "title": f"Sandbox {target}",
        "status": "planned_no_execution",
        "riskLevel": risk_level,
        "badge": "Mode sandbox actif",
        "summary": {
            "checkCount": len(checks),
            "requiresHumanApproval": requires_human_approval,
            "productionSecretsAccessible": False,
            "autoPromotionAllowed": False,
        },
        "risks": [
            {
                "id": key,
                "severity": "high" if key in {"touchesSecrets", "touchesProduction"} else "medium",
                "active": value,
            }
            for key, value in flags.items()
            if value
        ],
        "recommendations": [
            "Supprimer la sandbox si un check echoue.",
            "Promouvoir uniquement apres revue humaine et audit.",
            "Ne jamais injecter de secrets production dans l'environnement isole.",
        ],
    }
    if not report["risks"]:
        report["risks"].append({"id": "low_risk", "severity": "low", "active": True})

    return {
        "sandboxManagerVersion": COGNIX_SANDBOX_MANAGER_VERSION,
        "isolatedRuntimeVersion": COGNIX_ISOLATED_RUNTIME_VERSION,
        "experimentRunnerVersion": COGNIX_EXPERIMENT_RUNNER_VERSION,
        "rollbackServiceVersion": COGNIX_ROLLBACK_SERVICE_VERSION,
        "mode": "sandbox_plan",
        "username": username,
        "projectId": project_id,
        "projectType": project_type,
        "target": {
            "type": target,
            "objective": clean_objective,
            "changeSummary": clean_change,
            "durationMinutes": duration,
        },
        "isolation": {
            "ephemeral": True,
            "minimalConfigOnly": True,
            "minimalConfigKeys": ["runtime_adapter", "model_metadata", "project_settings", "permission_policy"],
            "productionSecretsAccessible": False,
            "productionDatabaseWritable": False,
            "networkAllowedByDefault": False,
            "rawDatasetCopyAllowed": False,
        },
        "checks": checks,
        "pipeline": pipeline,
        "rollbackPlan": {
            "defaultAction": "delete_sandbox",
            "deleteSandboxOnFailure": True,
            "promotionRequiresApproval": True,
            "productionRollbackWillExecuteNow": False,
        },
        "report": report,
        "queuePlan": {
            "queueRequired": True,
            "queueId": "local_probe",
            "jobType": "sandbox_experiment",
            "willEnqueueNow": False,
            "reason": "sandbox_experiments_must_be_isolated",
        },
        "sideEffects": build_sandbox_blueprint()["sideEffects"],
    }
