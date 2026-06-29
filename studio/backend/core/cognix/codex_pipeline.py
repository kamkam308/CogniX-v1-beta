# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Codex secure pipeline planning.

This module plans code-change work as a guarded pipeline. It does not edit
files, create branches, run tests, commit, push, merge, or deploy.
"""

from __future__ import annotations

import re
from typing import Any


COGNIX_CODEX_PIPELINE_VERSION = "cognix_codex_pipeline_v1"
COGNIX_CODEX_RUN_CONTRACT_VERSION = "cognix_codex_run_contract_v1"
COGNIX_CODEX_PREVIEW_CONTRACT_VERSION = "cognix_codex_preview_contract_v1"

CODEX_PIPELINE_STEPS: list[dict[str, Any]] = [
    {
        "id": "triage_feature_request",
        "label": "Analyser la demande",
        "gate": "objective_required",
        "required": True,
    },
    {
        "id": "create_git_branch",
        "label": "Creer une branche Git dediee",
        "gate": "clean_worktree_or_isolated_changes",
        "required": True,
    },
    {
        "id": "modify_native_source",
        "label": "Modifier le code source natif",
        "gate": "scoped_patch_review",
        "required": True,
    },
    {
        "id": "run_tests",
        "label": "Lancer les tests automatiques",
        "gate": "tests_pass",
        "required": True,
    },
    {
        "id": "run_build",
        "label": "Lancer le build",
        "gate": "build_passes",
        "required": True,
    },
    {
        "id": "security_review",
        "label": "Revue securite",
        "gate": "no_secret_leak_or_unsafe_executor",
        "required": True,
    },
    {
        "id": "preview_runtime",
        "label": "Verifier la preview/runtime",
        "gate": "runtime_health_check",
        "required": True,
    },
    {
        "id": "human_approval",
        "label": "Validation humaine",
        "gate": "explicit_approval_before_merge",
        "required": True,
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _objective_excerpt(objective: str | None) -> str:
    return re.sub(r"\s+", " ", objective or "").strip()[:500]


def _branch_slug(objective: str | None, project_id: str | None) -> str:
    source = project_id or objective or "feature"
    slug = re.sub(r"[^a-z0-9]+", "-", source.casefold()).strip("-")
    slug = slug[:48].strip("-") or "feature"
    return f"cognix/{slug}"


def _risk_level(task_strategy: dict[str, Any], execution_policy: dict[str, Any] | None) -> str:
    policy_risk = str(_as_dict(execution_policy).get("riskLevel") or "")
    if policy_risk:
        return policy_risk
    if task_strategy.get("path") == "codex_guarded_pipeline":
        return "high"
    return "low"


def _planned_steps(path: str) -> list[dict[str, Any]]:
    if path != "codex_guarded_pipeline":
        return [
            {
                "id": "not_applicable",
                "label": "Pipeline Codex non requis",
                "status": "skipped",
                "gate": "path_not_codex",
                "required": False,
            }
        ]
    return [
        {
            **step,
            "status": "planned",
            "sideEffectBlocked": step["id"] in {
                "create_git_branch",
                "modify_native_source",
                "run_tests",
                "run_build",
                "preview_runtime",
                "human_approval",
            },
        }
        for step in CODEX_PIPELINE_STEPS
    ]


def _status_passed(report: dict[str, Any], *, zero_fields: tuple[str, ...] = ()) -> bool:
    status = str(report.get("status") or report.get("state") or report.get("result") or "").casefold()
    explicit_pass = report.get("passed") is True or status in {
        "ok",
        "pass",
        "passed",
        "success",
        "succeeded",
        "green",
        "clean",
    }
    if not explicit_pass:
        return False
    for field in zero_fields:
        try:
            if int(report.get(field) or 0) > 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _preview_gate(gate_id: str, label: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "id": gate_id,
        "label": label,
        "required": True,
        "passed": passed,
        "status": "passed" if passed else "blocked",
        "evidence": evidence,
    }


def build_codex_preview_contract(
    *,
    username: str,
    feature_request: dict[str, Any] | None = None,
    pipeline_plan: dict[str, Any] | None = None,
    branch_name: str | None = None,
    test_results: dict[str, Any] | None = None,
    build_result: dict[str, Any] | None = None,
    security_scan: dict[str, Any] | None = None,
    preview_target: str | None = None,
) -> dict[str, Any]:
    feature_request = _as_dict(feature_request)
    pipeline_plan = _as_dict(pipeline_plan)
    test_results = _as_dict(test_results)
    build_result = _as_dict(build_result)
    security_scan = _as_dict(security_scan)
    branch = (
        branch_name
        or _as_dict(pipeline_plan.get("branch")).get("recommendedName")
        or pipeline_plan.get("targetBranch")
        or ""
    )
    feature_declared = bool(
        feature_request.get("id")
        or feature_request.get("title")
        or feature_request.get("summary")
        or feature_request.get("type")
    )
    branch_declared = bool(str(branch).strip())
    tests_passed = _status_passed(test_results, zero_fields = ("failed", "failures", "errors"))
    build_passed = _status_passed(build_result, zero_fields = ("failed", "failures", "errors"))
    security_passed = _status_passed(security_scan, zero_fields = ("critical", "high", "errors"))
    gates = [
        _preview_gate(
            "feature_request_declared",
            "Feature request declaree",
            feature_declared,
            "feature_request_metadata_present",
        ),
        _preview_gate(
            "branch_declared",
            "Branche Git declaree",
            branch_declared,
            "branch_name_present",
        ),
        _preview_gate(
            "tests_passed",
            "Tests automatiques valides",
            tests_passed,
            "test_report_status_passed",
        ),
        _preview_gate(
            "build_passed",
            "Build valide",
            build_passed,
            "build_report_status_passed",
        ),
        _preview_gate(
            "security_scan_passed",
            "Scan securite valide",
            security_passed,
            "security_scan_has_no_critical_or_high_findings",
        ),
        {
            "id": "human_approval_required",
            "label": "Validation humaine obligatoire",
            "required": True,
            "passed": True,
            "status": "required",
            "evidence": "approval_must_happen_outside_this_contract",
        },
    ]
    blocked_gate_ids = [
        gate["id"] for gate in gates if gate.get("required") and gate.get("status") == "blocked"
    ]
    ready_for_review = not blocked_gate_ids
    return {
        "contractVersion": COGNIX_CODEX_PREVIEW_CONTRACT_VERSION,
        "mode": "codex_preview_contract_dry_run",
        "username": username,
        "status": "ready_for_preview_review" if ready_for_review else "blocked_missing_gate",
        "readyForPreviewReview": ready_for_review,
        "readyForPreviewStart": False,
        "readyForMerge": False,
        "blockedGateIds": blocked_gate_ids,
        "featureRequest": {
            "declared": feature_declared,
            "metadataKeys": sorted(feature_request.keys())[:12],
        },
        "branch": {
            "name": str(branch).strip() or None,
            "declared": branch_declared,
            "willCreate": False,
        },
        "qualityReports": {
            "tests": {"declared": bool(test_results), "passed": tests_passed},
            "build": {"declared": bool(build_result), "passed": build_passed},
            "security": {"declared": bool(security_scan), "passed": security_passed},
        },
        "previewPlan": {
            "target": preview_target or "local_preview",
            "readyForManualReview": ready_for_review,
            "willStartPreview": False,
            "previewUrlGenerated": False,
            "requiresHumanApprovalBeforeMerge": True,
        },
        "mergePolicy": {
            "automaticMergeAllowed": False,
            "humanApprovalRequired": True,
            "mainBranchWriteAllowed": False,
            "mergeAllowedWithoutApproval": False,
            "readyForHumanMergeApproval": ready_for_review,
        },
        "gates": gates,
        "blockedActions": [
            "branch_create",
            "code_write",
            "test_run",
            "build_run",
            "security_scan_run",
            "preview_start",
            "merge",
            "git_push",
            "network_call",
            "file_write",
            "tool_execution",
        ],
        "sideEffects": {
            "branchCreate": False,
            "codeWrite": False,
            "testRun": False,
            "buildRun": False,
            "securityScanRun": False,
            "previewStart": False,
            "merge": False,
            "gitPush": False,
            "networkCall": False,
            "fileWrite": False,
            "toolExecution": False,
        },
    }


def _run_contract(*, applicable: bool, branch_name: str, risk_level: str) -> dict[str, Any]:
    requires_security_review = risk_level in {"high", "critical"}
    command_plan = [
        {
            "id": "inspect_worktree",
            "command": "git status --short",
            "required": True,
            "willRunHere": False,
            "evidence": "worktree_status_captured",
        },
        {
            "id": "compile_backend",
            "command": "PYTHONPATH=studio/backend python -m py_compile <changed-python-files>",
            "required": True,
            "willRunHere": False,
            "evidence": "python_compile_passed",
        },
        {
            "id": "targeted_tests",
            "command": "PYTHONPATH=studio/backend python -m pytest -q <targeted-tests>",
            "required": True,
            "willRunHere": False,
            "evidence": "targeted_tests_passed",
        },
        {
            "id": "native_guard",
            "command": "npm run cognix:check",
            "required": True,
            "willRunHere": False,
            "evidence": "native_guard_passed",
        },
        {
            "id": "runtime_smoke",
            "command": "curl -ksS https://cognix.local:4321/<changed-endpoint>",
            "required": True,
            "willRunHere": False,
            "evidence": "runtime_endpoint_verified",
        },
    ]
    evidence_requirements = [
        "changed_files_scoped",
        "tests_passed",
        "native_guard_passed",
        "runtime_verified_when_api_changes",
        "git_commit_created",
        "github_push_completed",
    ]
    if requires_security_review:
        evidence_requirements.append("security_review_notes")
    return {
        "contractVersion": COGNIX_CODEX_RUN_CONTRACT_VERSION,
        "mode": "codex_run_contract_dry_run",
        "applicable": applicable,
        "targetBranch": branch_name,
        "branchCreateAllowedHere": False,
        "codeModificationAllowedHere": False,
        "testExecutionAllowedHere": False,
        "buildExecutionAllowedHere": False,
        "commitAllowedHere": False,
        "pushAllowedHere": False,
        "mergeAllowedHere": False,
        "deploymentAllowedHere": False,
        "commandPlan": command_plan if applicable else [],
        "evidenceRequirements": evidence_requirements if applicable else [],
        "mergeGate": {
            "humanApprovalRequired": True,
            "requiresPassingTests": True,
            "requiresBuildOrNativeGuard": True,
            "requiresSecurityReview": requires_security_review,
            "mergeAllowedWithoutApproval": False,
        },
        "blockedActions": [
            "branch_create",
            "file_write",
            "test_execution",
            "build_execution",
            "commit",
            "push",
            "merge",
            "deployment",
        ],
        "sideEffects": {
            "branchCreate": False,
            "fileWrite": False,
            "testExecution": False,
            "buildExecution": False,
            "commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
    }


def build_codex_pipeline_plan(
    *,
    objective: str,
    current_subject: str,
    project_id: str | None = None,
    classification: dict[str, Any] | None = None,
    task_strategy: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_strategy = _as_dict(task_strategy)
    classification = _as_dict(classification)
    path = str(task_strategy.get("path") or "expert_chat")
    applicable = path == "codex_guarded_pipeline"
    risk_level = _risk_level(task_strategy, execution_policy)
    branch_name = _branch_slug(objective, project_id)

    warnings: list[str] = []
    if applicable:
        warnings.append("Pipeline Codex planifie: modification code bloquee sans executor audite.")
    if classification.get("needsClarification"):
        warnings.append("Clarification requise avant modification de code.")

    return {
        "plannerVersion": COGNIX_CODEX_PIPELINE_VERSION,
        "mode": "dry_run",
        "username": current_subject,
        "projectId": project_id,
        "objectiveExcerpt": _objective_excerpt(objective),
        "applicable": applicable,
        "recommendedPath": "codex_guarded_pipeline" if applicable else "not_needed",
        "targetDomain": classification.get("selectedDomain") or "general",
        "riskLevel": risk_level,
        "branch": {
            "recommendedName": branch_name,
            "willCreate": False,
            "reason": "La branche est planifiee mais jamais creee par ce planner.",
        },
        "qualityGates": {
            "testsRequired": applicable,
            "buildRequired": applicable,
            "securityReviewRequired": applicable,
            "previewRequired": applicable,
            "humanApprovalRequired": applicable,
            "mergeAllowedWithoutApproval": False,
        },
        "runContract": _run_contract(
            applicable=applicable,
            branch_name=branch_name,
            risk_level=risk_level,
        ),
        "steps": _planned_steps(path),
        "blockedActions": [
            {
                "id": "git_branch_create",
                "reason": "Creation de branche reservee au runner Codex audite.",
            },
            {
                "id": "file_write",
                "reason": "Modification de fichiers reservee au pipeline de travail courant, pas a cette API.",
            },
            {
                "id": "test_execution",
                "reason": "Tests planifies mais non lances par le planner.",
            },
            {
                "id": "commit_push_merge",
                "reason": "Commit, push et merge exigent validation humaine et etapes separees.",
            },
            {
                "id": "deployment",
                "reason": "Aucun deploiement production depuis le planner Codex.",
            },
        ],
        "warnings": warnings,
        "reason": (
            "Demande code detectee: preparer branche, changements natifs, tests, build, preview et validation."
            if applicable
            else "Pipeline Codex optionnel: la demande ne cible pas une modification de code."
        ),
        "sideEffects": {
            "branchCreate": False,
            "fileWrite": False,
            "testExecution": False,
            "buildExecution": False,
            "commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
            "codeModification": False,
        },
    }
