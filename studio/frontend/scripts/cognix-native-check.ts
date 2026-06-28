// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..");

type Check = {
  file: string;
  includes?: string[];
  excludes?: string[];
};

type ScopedCheck = Check & {
  start: string;
  end?: string;
};

const checks: Check[] = [
  {
    file: "src/index.css",
    includes: [
      ".cognix-logo-mark",
      "transform: scale(1.04)",
      "html.dark .cognix-logo-mark",
      "invert(1) contrast(1.08)",
    ],
  },
  {
    file: "src/components/app-sidebar.tsx",
    includes: [
      'src="/cognix-logo.png"',
      "h-[31px] w-[31px]",
      "h-[24px] w-[24px]",
      "CogniX",
    ],
  },
  {
    file: "src/features/auth/components/auth-form.tsx",
    includes: [
      "cognix-auth-mode-pill",
      "Identifiant ou email",
      "Nom d'utilisateur",
      "Connexion",
      "Inscription",
    ],
    excludes: [
      "Se connecter a CogniX",
      "Se connecter à CogniX",
      "Log in to CogniX",
      "Setup your account",
      "Configurer votre compte",
    ],
  },
  {
    file: "src/features/chat/api/chat-api.ts",
    includes: [
      "CogniXContextPack",
      "CogniXExecutionPlan",
      "auditLogId",
      'CHAT_HISTORY_UPDATED_EVENT = "cognix-chat-history-updated"',
      'authFetch("/api/cognix/context/pack"',
      'authFetch("/api/cognix/orchestrator/plan"',
    ],
    excludes: [
      "unsloth-chat-history-updated",
    ],
  },
  {
    file: "src/features/chat/api/chat-adapter.ts",
    includes: [
      "buildCogniXContextPack",
      "buildLatestCogniXContextInstruction",
      "planCogniXExecution",
      "planLatestCogniXObjective",
      "willLoadModel",
      "willGenerate",
      "setLatestCogniXRoute",
    ],
    excludes: [
      "await classifyCogniXObjective",
    ],
  },
  {
    file: "src/features/chat/chat-page.tsx",
    includes: [
      "CogniX Auto",
      "latestRoute?.executionStatus",
      "Plan {latestRoute.planMode",
    ],
  },
  {
    file: "../backend/routes/cognix.py",
    includes: [
      '@router.post("/context/pack")',
      '@router.post("/benchmark/run")',
      '@router.get("/benchmark/runs")',
      '@router.get("/admin/audit-logs")',
      '@router.get("/admin/benchmark-runs")',
      '@router.get("/tools/registry")',
      '@router.post("/tools/plan")',
      '@router.get("/admin/permissions/{username}")',
      '@router.post("/admin/permissions/{username}")',
      '@router.delete("/admin/permissions/{username}/{permission_key}")',
      '@router.get("/admin/orchestrator-logs")',
      "context_pack_built",
      "tool_action_planned",
      "permission_granted",
      "permission_revoked",
      "rate_limited",
      "cognix_db.check_rate_limit",
      "cognix_db.create_orchestrator_log",
      '@router.post("/orchestrator/plan")',
      '"orchestratorLogId"',
      '"runtimeType": "dry_run"',
      '"runtimeError": None',
    ],
  },
  {
    file: "../backend/storage/cognix_db.py",
    includes: [
      "CREATE TABLE IF NOT EXISTS cognix_audit_logs",
      "AUDIT_LOG_RETENTION_LIMIT",
      "def create_audit_log",
      "def list_audit_logs",
      "def prune_audit_logs",
      "def grant_user_permission",
      "def revoke_user_permission",
      "def list_user_permissions",
      "CREATE TABLE IF NOT EXISTS cognix_rate_limit_events",
      "def check_rate_limit",
      "CREATE TABLE IF NOT EXISTS cognix_orchestrator_logs",
      "def create_orchestrator_log",
      "def list_orchestrator_logs",
      "CREATE TABLE IF NOT EXISTS cognix_benchmark_runs",
      "def create_benchmark_run",
      "def list_benchmark_runs",
      "metadata_json",
    ],
  },
  {
    file: "../backend/core/cognix/benchmark.py",
    includes: [
      'COGNIX_BENCHMARK_VERSION = "cognix_benchmark_v1"',
      "def run_benchmark",
      '"estimatedTokensPerSecond"',
      '"modelFitness"',
      '"optimizationPlan"',
      '"networkCall": False',
      '"gpuStressTest": False',
    ],
  },
  {
    file: "../backend/core/cognix/decision_engine.py",
    includes: [
      'COGNIX_DECISION_ENGINE_VERSION = "cognix_decision_engine_v1"',
      "def build_task_strategy",
      '"rag_first"',
      '"guided_fine_tuning"',
      '"codex_guarded_pipeline"',
      '"toolExecution": False',
      '"fineTuningJob": False',
    ],
  },
  {
    file: "../backend/core/cognix/context_manager.py",
    includes: [
      'CONTEXT_MANAGER_VERSION = "cognix_context_manager_v1"',
      '"systemInstruction"',
      '"user_memory"',
      '"project_instructions"',
      '"networkModelCall": False',
    ],
  },
  {
    file: "../backend/core/cognix/tool_registry.py",
    includes: [
      'TOOL_REGISTRY_VERSION = "cognix_tool_registry_v1"',
      "frontendDirectExecutionAllowed",
      "RATE_LIMIT_POLICIES",
      "rate_limit_policy_for_key",
      "requiresConfirmation",
      "auditRequired",
      "sandboxRequired",
      '"toolExecution": False',
      "def plan_tool_action",
    ],
  },
  {
    file: "../backend/core/cognix/orchestrator.py",
    includes: [
      '"orchestratorVersion": "cognix_orchestrator_v1"',
      '"mode": "dry_run"',
      "cognix_decision_engine.build_task_strategy",
      '"taskStrategy"',
      '"recommendedPath"',
      '"willLoadModel": False',
      '"willGenerate": False',
      '"networkModelCall": False',
    ],
  },
  {
    file: "../backend/tests/test_cognix_benchmark.py",
    includes: [
      "test_benchmark_estimates_model_fitness_without_model_side_effects",
      "test_benchmark_run_endpoint_persists_user_history_and_admin_view",
      "cognix_benchmark_v1",
      "/api/cognix/benchmark/run",
      "/api/cognix/admin/benchmark-runs",
    ],
  },
  {
    file: "../backend/tests/test_cognix_router.py",
    includes: [
      "test_context_manager_builds_bounded_context_packet",
      "test_context_pack_endpoint_combines_user_memory_and_project_instructions",
      "test_context_pack_writes_sanitized_audit_log",
      "test_audit_log_retention_prunes_old_entries",
      "test_decision_engine_prefers_rag_before_fine_tuning_for_documents",
      "test_tool_registry_declares_permissions_and_guardrails",
      "test_tool_plan_endpoint_allows_safe_declared_action_and_logs_audit",
      "test_tool_rate_limit_storage_blocks_after_capacity",
      "test_tool_plan_applies_rate_limit_guard",
      "test_tool_plan_blocks_disabled_connectors_before_permissions",
      "test_admin_permission_grant_and_revoke_affect_tool_planning",
      "test_orchestrator_builds_dry_run_plan_without_loading",
      "test_orchestrator_plan_endpoint_logs_dry_run_decision",
      "admin_orchestrator_logs",
      "orchestratorLogId",
      "willLoadModel",
      "networkModelCall",
    ],
  },
];

const scopedChecks: ScopedCheck[] = [
  {
    file: "../backend/routes/cognix.py",
    start: '@router.post("/orchestrator/plan")',
    end: "\n@router.",
    includes: [
      '"runtimeType": "dry_run"',
      "cognix_orchestrator.build_execution_plan",
      "cognix_db.create_orchestrator_log",
      '"runtimeError": None',
    ],
    excludes: [
      "_current_model_cache_runtime()",
      "get_inference_backend",
      "get_llama_cpp_backend",
    ],
  },
];

const failures: string[] = [];

for (const check of checks) {
  const absolute = resolve(ROOT, check.file);
  const content = readFileSync(absolute, "utf8");

  for (const expected of check.includes ?? []) {
    if (!content.includes(expected)) {
      failures.push(`${check.file}: missing ${JSON.stringify(expected)}`);
    }
  }

  for (const forbidden of check.excludes ?? []) {
    if (content.includes(forbidden)) {
      failures.push(`${check.file}: forbidden ${JSON.stringify(forbidden)}`);
    }
  }
}

for (const check of scopedChecks) {
  const absolute = resolve(ROOT, check.file);
  const content = readFileSync(absolute, "utf8");
  const startIndex = content.indexOf(check.start);

  if (startIndex === -1) {
    failures.push(`${check.file}: missing scoped start ${JSON.stringify(check.start)}`);
    continue;
  }

  const endIndex = check.end ? content.indexOf(check.end, startIndex + check.start.length) : -1;
  const scopedContent = content.slice(startIndex, endIndex === -1 ? undefined : endIndex);

  for (const expected of check.includes ?? []) {
    if (!scopedContent.includes(expected)) {
      failures.push(`${check.file}: scoped block missing ${JSON.stringify(expected)}`);
    }
  }

  for (const forbidden of check.excludes ?? []) {
    if (scopedContent.includes(forbidden)) {
      failures.push(`${check.file}: scoped block contains forbidden ${JSON.stringify(forbidden)}`);
    }
  }
}

if (failures.length > 0) {
  console.error("CogniX native guard failed:");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("CogniX native guard passed.");
