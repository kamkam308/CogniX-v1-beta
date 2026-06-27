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
      '@router.get("/admin/audit-logs")',
      "context_pack_built",
      '@router.post("/orchestrator/plan")',
      '"runtimeType": "dry_run"',
      '"runtimeError": None',
    ],
  },
  {
    file: "../backend/storage/cognix_db.py",
    includes: [
      "CREATE TABLE IF NOT EXISTS cognix_audit_logs",
      "def create_audit_log",
      "def list_audit_logs",
      "metadata_json",
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
    file: "../backend/core/cognix/orchestrator.py",
    includes: [
      '"orchestratorVersion": "cognix_orchestrator_v1"',
      '"mode": "dry_run"',
      '"willLoadModel": False',
      '"willGenerate": False',
      '"networkModelCall": False',
    ],
  },
  {
    file: "../backend/tests/test_cognix_router.py",
    includes: [
      "test_context_manager_builds_bounded_context_packet",
      "test_context_pack_endpoint_combines_user_memory_and_project_instructions",
      "test_context_pack_writes_sanitized_audit_log",
      "test_orchestrator_builds_dry_run_plan_without_loading",
      "test_orchestrator_plan_endpoint_logs_dry_run_decision",
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
