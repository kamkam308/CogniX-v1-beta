# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX Codex secure pipeline planning.

This module plans code-change work as a guarded pipeline. It does not edit
files, create branches, run tests, commit, push, merge, or deploy.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


COGNIX_CODEX_PIPELINE_VERSION = "cognix_codex_pipeline_v1"
COGNIX_CODEX_RUN_CONTRACT_VERSION = "cognix_codex_run_contract_v1"
COGNIX_CODEX_PREVIEW_CONTRACT_VERSION = "cognix_codex_preview_contract_v1"
COGNIX_CODEX_APPROVAL_GATE_VERSION = "cognix_codex_approval_gate_v1"
COGNIX_CODEX_NIGHT_MODE_CONTRACT_VERSION = "cognix_codex_night_mode_contract_v1"

NIGHT_MODE_ALIASES = {"night", "sleep", "mode_nuit", "nuit", "sommeil"}
NIGHT_MODE_ALLOWED_CATEGORIES = [
    "security",
    "performance_optimization",
    "memory_optimization",
    "tests",
    "technical_documentation",
    "static_analysis",
    "logs_observability",
    "permissions_hardening",
    "non_destructive_cleanup",
]
NIGHT_MODE_BLOCKED_CATEGORIES = [
    "visible_ux_change",
    "new_visible_feature",
    "navigation_change",
    "auth_behavior_change",
    "billing_or_payment_change",
    "risky_database_migration",
    "chat_behavior_change",
    "production_deployment",
    "main_branch_merge",
]

ALLOWED_NIGHT_SIGNALS: list[tuple[str, tuple[str, ...]]] = [
    ("security", ("security", "securite", "secure", "secret", "vulnerability", "vulnerabilite", "audit", "redaction", "sanitize", "durcir", "durcissement")),
    ("permissions_hardening", ("permission", "permissions", "rbac", "role", "roles", "admin", "policy", "policies", "guardrail", "garde fou")),
    ("performance_optimization", ("performance", "optimisation", "optimization", "speed", "vitesse", "latency", "latence", "cache")),
    ("memory_optimization", ("memory", "memoire", "ram", "gpu memory", "kv cache", "compression")),
    ("tests", ("test", "tests", "pytest", "coverage", "verification", "smoke")),
    ("technical_documentation", ("documentation", "docs", "readme", "rapport technique", "technical doc")),
    ("static_analysis", ("static analysis", "analyse statique", "lint", "type check", "mypy", "bug detection", "detecter bug")),
    ("logs_observability", ("log", "logs", "observability", "monitoring", "metrics", "trace", "telemetry")),
    ("non_destructive_cleanup", ("cleanup", "nettoyage", "refactor", "dette", "debt", "non destructive")),
]

VISIBLE_CHANGE_SIGNALS = (
    "ux",
    "ui",
    "design",
    "navigation",
    "interface",
    "frontend visible",
    "new feature",
    "feature visible",
    "nouvelle fonctionnalite",
    "fonctionnalite visible",
    "module visible",
    "connecteur",
    "connector",
    "login",
    "inscription",
    "auth",
    "authentication",
    "mot de passe",
    "password",
    "billing",
    "payment",
    "paiement",
    "pricing",
    "migration",
    "database migration",
    "comportement du chat",
    "chat behavior",
    "merge",
    "deploy",
    "deployment",
    "deploiement",
    "production",
)

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


def _normalized_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").casefold()
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text).strip()


def _matched_signals(text: str, signals: tuple[str, ...]) -> list[str]:
    return [signal for signal in signals if signal in text]


def _night_mode_classification(objective: str | None) -> dict[str, Any]:
    text = _normalized_text(objective)
    matched_allowed: list[str] = []
    selected_category = "unclassified"
    for category, signals in ALLOWED_NIGHT_SIGNALS:
        matched = _matched_signals(text, signals)
        if matched:
            selected_category = category
            matched_allowed = matched
            break
    visible_signals = _matched_signals(text, VISIBLE_CHANGE_SIGNALS)
    return {
        "selectedCategory": selected_category,
        "matchedAllowedSignals": matched_allowed[:12],
        "matchedBlockedSignals": visible_signals[:12],
        "visibleProductChangeRequested": bool(visible_signals),
    }


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


def build_codex_night_mode_contract(
    *,
    objective: str,
    run_mode: str | None = None,
    task_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_mode = _normalized_text(run_mode or "supervised").replace(" ", "_")
    night_mode_active = normalized_mode in NIGHT_MODE_ALIASES
    classification = _night_mode_classification(objective)
    selected_category = str(classification["selectedCategory"])
    visible_change_requested = bool(classification["visibleProductChangeRequested"])
    category_allowed = selected_category in NIGHT_MODE_ALLOWED_CATEGORIES
    autonomous_night_work_allowed = (
        not night_mode_active
        or (category_allowed and not visible_change_requested)
    )
    blocked_by_night_mode = night_mode_active and not autonomous_night_work_allowed
    return {
        "contractVersion": COGNIX_CODEX_NIGHT_MODE_CONTRACT_VERSION,
        "mode": "codex_supervision_mode_contract",
        "runMode": "night" if night_mode_active else "supervised",
        "nightModeActive": night_mode_active,
        "taskPath": _as_dict(task_strategy).get("path"),
        "objectiveExcerpt": _objective_excerpt(objective),
        "selectedCategory": selected_category,
        "matchedAllowedSignals": classification["matchedAllowedSignals"],
        "matchedBlockedSignals": classification["matchedBlockedSignals"],
        "visibleProductChangeRequested": visible_change_requested,
        "categoryAllowedInNightMode": category_allowed,
        "autonomousNightWorkAllowed": autonomous_night_work_allowed,
        "blockedByNightMode": blocked_by_night_mode,
        "nativeSourcePatchAllowed": autonomous_night_work_allowed,
        "visibleUxChangeAllowed": not night_mode_active,
        "mainBranchMergeAllowed": False,
        "productionDeploymentAllowed": False,
        "allowedNightWorkCategories": NIGHT_MODE_ALLOWED_CATEGORIES,
        "blockedNightWorkCategories": NIGHT_MODE_BLOCKED_CATEGORIES,
        "requiredReportSections": [
            "files_modified",
            "tests_run",
            "results",
            "risks_detected",
            "recommendations_for_human_validation",
        ]
        if night_mode_active
        else [
            "files_modified",
            "tests_run",
            "summary_for_user_validation",
        ],
        "policy": {
            "supervisedModeAllowsVisibleProductWorkWithValidation": True,
            "nightModeAllowsSecurityOptimizationTestsDocsOnly": True,
            "nightModeBlocksVisibleUxNavigationAuthBillingChatBehavior": True,
            "mergeRequiresHumanApproval": True,
            "deploymentRequiresHumanApproval": True,
        },
        "blockedActions": [
            "main_branch_merge",
            "production_deployment",
            "approval_bypass",
            "payment_change",
            "auth_behavior_change_without_validation",
            "database_migration_without_validation",
        ]
        + (
            [
                "visible_ux_change",
                "new_visible_feature",
                "navigation_change",
                "chat_behavior_change",
            ]
            if night_mode_active
            else []
        ),
        "sideEffects": {
            "fileWrite": False,
            "codeModification": False,
            "testExecution": False,
            "buildExecution": False,
            "merge": False,
            "deployment": False,
            "approvalWrite": False,
        },
    }


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


def _latest_approval_decision(decisions: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not decisions:
        return {}
    return _as_dict(decisions[0])


def _approval_metadata(request: dict[str, Any]) -> dict[str, Any]:
    metadata = request.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return {}


def _approval_branch(request: dict[str, Any]) -> str:
    metadata = _approval_metadata(request)
    return str(
        metadata.get("branchName")
        or metadata.get("codexBranchName")
        or metadata.get("targetBranch")
        or request.get("resource_id")
        or request.get("resourceId")
        or ""
    ).strip()


def build_codex_approval_gate_contract(
    *,
    username: str,
    preview_contract: dict[str, Any] | None = None,
    approval_request: dict[str, Any] | None = None,
    approval_decisions: list[dict[str, Any]] | None = None,
    branch_name: str | None = None,
) -> dict[str, Any]:
    preview_contract = _as_dict(preview_contract)
    approval_request = _as_dict(approval_request)
    latest_decision = _latest_approval_decision(approval_decisions)
    preview_branch = str(
        branch_name
        or _as_dict(preview_contract.get("branch")).get("name")
        or ""
    ).strip()
    request_type = str(
        approval_request.get("request_type") or approval_request.get("requestType") or ""
    ).strip().lower()
    requester = str(approval_request.get("username") or approval_request.get("requester") or "").strip()
    request_status = str(approval_request.get("status") or "").strip().lower()
    decision_status = str(latest_decision.get("status") or "").strip().lower()
    decision_actor = str(
        latest_decision.get("decided_by")
        or latest_decision.get("decidedBy")
        or approval_request.get("decided_by")
        or approval_request.get("decidedBy")
        or ""
    ).strip()
    approval_branch = _approval_branch(approval_request)

    preview_ready = preview_contract.get("readyForPreviewReview") is True
    request_present = bool(approval_request)
    type_matches = request_type == "codex:run"
    requester_matches = requester == username
    branch_matches = bool(preview_branch and approval_branch and preview_branch == approval_branch)
    approved = request_status == "approved" and decision_status == "approved"
    decision_recorded = bool(decision_actor)
    gates = [
        _preview_gate(
            "preview_contract_ready",
            "Contrat preview pret",
            preview_ready,
            "codex_preview_contract_ready_for_review",
        ),
        _preview_gate(
            "approval_request_present",
            "Demande approval presente",
            request_present,
            "approval_request_loaded",
        ),
        _preview_gate(
            "approval_request_type_codex_run",
            "Approval cible Codex",
            type_matches,
            "approval_request_type_codex_run",
        ),
        _preview_gate(
            "approval_requester_matches_user",
            "Approval rattache au demandeur",
            requester_matches,
            "approval_username_matches_current_subject",
        ),
        _preview_gate(
            "approval_branch_matches_preview",
            "Approval rattache a la branche preview",
            branch_matches,
            "approval_branch_matches_preview_branch",
        ),
        _preview_gate(
            "approval_status_approved",
            "Approval admin approuvee",
            approved,
            "latest_approval_decision_status_approved",
        ),
        _preview_gate(
            "admin_decision_recorded",
            "Decision admin tracee",
            decision_recorded,
            "approval_decision_has_actor",
        ),
        {
            "id": "human_merge_execution_required",
            "label": "Merge manuel obligatoire",
            "required": True,
            "passed": True,
            "status": "required",
            "evidence": "merge_execution_must_happen_outside_this_contract",
        },
    ]
    blocked_gate_ids = [
        gate["id"] for gate in gates if gate.get("required") and gate.get("status") == "blocked"
    ]
    ready_for_merge_review = not blocked_gate_ids
    return {
        "contractVersion": COGNIX_CODEX_APPROVAL_GATE_VERSION,
        "mode": "codex_approval_gate_dry_run",
        "username": username,
        "status": "ready_for_human_merge_review" if ready_for_merge_review else "blocked_missing_approval_gate",
        "readyForMergeReview": ready_for_merge_review,
        "readyForMerge": False,
        "mergeAllowedHere": False,
        "blockedGateIds": blocked_gate_ids,
        "approvalRequest": {
            "id": approval_request.get("id"),
            "present": request_present,
            "requestType": request_type or None,
            "status": request_status or None,
            "riskLevel": approval_request.get("risk_level") or approval_request.get("riskLevel"),
            "metadataKeys": sorted(_approval_metadata(approval_request).keys())[:12],
        },
        "approvalDecision": {
            "present": bool(latest_decision),
            "status": decision_status or None,
            "decidedByPresent": bool(decision_actor),
        },
        "branch": {
            "previewBranch": preview_branch or None,
            "approvalBranch": approval_branch or None,
            "matches": branch_matches,
        },
        "mergePolicy": {
            "automaticMergeAllowed": False,
            "humanApprovalRequired": True,
            "approvedRequestRequired": True,
            "branchScopedApprovalRequired": True,
            "mainBranchWriteAllowed": False,
            "mergeAllowedWithoutApproval": False,
            "readyForHumanMergeReview": ready_for_merge_review,
        },
        "gates": gates,
        "blockedActions": [
            "merge",
            "main_branch_write",
            "git_push",
            "deployment",
            "file_write",
            "tool_execution",
            "network_call",
        ],
        "sideEffects": {
            "merge": False,
            "mainBranchWrite": False,
            "gitPush": False,
            "deployment": False,
            "fileWrite": False,
            "toolExecution": False,
            "networkCall": False,
            "approvalWrite": False,
            "decisionWrite": False,
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
    run_mode: str | None = None,
) -> dict[str, Any]:
    task_strategy = _as_dict(task_strategy)
    classification = _as_dict(classification)
    path = str(task_strategy.get("path") or "expert_chat")
    applicable = path == "codex_guarded_pipeline"
    risk_level = _risk_level(task_strategy, execution_policy)
    branch_name = _branch_slug(objective, project_id)
    supervision_contract = build_codex_night_mode_contract(
        objective = objective,
        run_mode = run_mode,
        task_strategy = task_strategy,
    )

    warnings: list[str] = []
    if applicable:
        warnings.append("Pipeline Codex planifie: modification code bloquee sans executor audite.")
    if classification.get("needsClarification"):
        warnings.append("Clarification requise avant modification de code.")
    if supervision_contract["nightModeActive"]:
        warnings.append("Mode nuit actif: seuls securite, optimisation, tests, docs, logs et nettoyage non destructif sont autorises.")
    if supervision_contract["blockedByNightMode"]:
        warnings.append("Mode nuit bloque cette demande car elle implique un changement produit visible ou non classe.")

    return {
        "plannerVersion": COGNIX_CODEX_PIPELINE_VERSION,
        "nightModeContractVersion": COGNIX_CODEX_NIGHT_MODE_CONTRACT_VERSION,
        "mode": "dry_run",
        "supervisionMode": supervision_contract["runMode"],
        "nightModeActive": supervision_contract["nightModeActive"],
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
            "nightModePolicyRequired": supervision_contract["nightModeActive"],
            "nightModeAllowsAutonomousWork": supervision_contract["autonomousNightWorkAllowed"],
        },
        "runContract": _run_contract(
            applicable=applicable,
            branch_name=branch_name,
            risk_level=risk_level,
        ),
        "supervisionModeContract": supervision_contract,
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
            *(
                [
                    {
                        "id": "night_mode_visible_change",
                        "reason": "Mode nuit: changement visible, navigation, auth, paiement, chat, merge et prod sont bloques.",
                    }
                ]
                if supervision_contract["blockedByNightMode"]
                else []
            ),
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
