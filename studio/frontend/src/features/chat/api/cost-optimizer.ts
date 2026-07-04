// SPDX-License-Identifier: AGPL-3.0-only

import { authFetch } from "@/features/auth";
import { formatFastApiDetail } from "@/lib/format-fastapi-error";

export type CostPriority = "balanced" | "cost" | "speed" | "privacy";

export interface CostEstimate {
  estimatedCostUsd: number;
  free: boolean;
  billingRequired: boolean;
  inputPer1kUsd?: number;
  outputPer1kUsd?: number;
}

export interface LatencyEstimate {
  estimatedLatencyMs: number;
  speedRank?: number;
}

export interface PrivacyFit {
  score: number;
  tier: string;
  sensitiveDataAllowed: boolean;
  dataLeavesDevice: boolean;
  cloudBlockedBecauseSensitive: boolean;
}

export interface CostCandidate {
  providerId: string;
  displayName: string;
  executionTarget: string;
  label: string;
  status: string;
  blockedReasons: string[];
  costEstimate: CostEstimate;
  latencyEstimate: LatencyEstimate;
  privacyFit: PrivacyFit;
  projectFit: number;
  decisionScore: number;
  quotaGuardStatus?: string | null;
}

export interface CostDecision {
  selectedProviderId: string;
  selectedExecutionTarget: string;
  providerLabel: string;
  estimatedCostUsd: number;
  estimatedLatencyMs: number;
  decisionScore: number;
  reason: string;
  requiresExplicitUserAction: boolean;
  cloudBlockedBecauseSensitive: boolean;
}

export interface BudgetGuardDecision {
  selectedProviderId?: string | null;
  selectedExecutionTarget?: string | null;
  providerLabel?: string | null;
  estimatedCostUsd?: number | null;
  estimatedLatencyMs?: number | null;
  decisionScore?: number | null;
  quotaGuardStatus?: string | null;
  blockedReasons?: string[];
  selectedExecutionTargetChanged?: boolean;
}

export interface BudgetGuard {
  status?: string | null;
  allowedToExecute?: boolean;
  blockingReasons?: string[];
  guardedDecision?: BudgetGuardDecision;
}

export interface CostOptimizationPlan {
  optimizerVersion?: string;
  pricingStoreVersion?: string;
  executionPlannerVersion?: string;
  privacyPolicyVersion?: string;
  mode?: string;
  services: string[];
  task: {
    objectiveExcerpt?: string;
    projectId?: string | null;
    projectType?: string | null;
    expectedInputTokens?: number;
    expectedOutputTokens?: number;
    estimatedTotalTokens?: number;
    messageCount?: number;
  };
  priority: CostPriority;
  budget: {
    budgetUsd?: number | null;
    hardLimitApplied?: boolean;
  };
  sensitivity: {
    level?: string;
    sensitive?: boolean;
    signals?: string[];
    reason?: string;
    allowCloudWhenSensitive?: boolean;
    cloudAllowed?: boolean;
  };
  decision: CostDecision;
  guardedDecision?: BudgetGuardDecision | null;
  candidates: CostCandidate[];
  displayOptions: Array<{
    providerId: string;
    label: string;
    estimatedCostUsd: number;
    estimatedLatencyMs: number;
    status: string;
  }>;
  budgetGuard?: BudgetGuard | null;
  policy: {
    displayOnlyWhenUseful?: boolean;
    requiresExplicitCloudValidation?: boolean;
    cloudBlockedBecauseSensitive?: boolean;
    humanConfirmationRequiredBeforePaidCloud?: boolean;
    frontendDirectProviderCallAllowed?: boolean;
    sensitiveCloudDefaultAllowed?: boolean;
    quotaGuardApplied?: boolean;
  };
  sideEffects?: Record<string, unknown>;
}

export interface CostOptimizationResponse {
  username?: string;
  costOptimizationPlan: CostOptimizationPlan;
  costLog?: Record<string, unknown> | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

function parseErrorText(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    const formatted = formatFastApiDetail(detail);
    if (formatted) return formatted;
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return `Request failed (${status})`;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(parseErrorText(response.status, body));
  }
  return body as T;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function maybeString(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function stringValue(value: unknown, fallback = ""): string {
  return maybeString(value) ?? fallback;
}

function numberValue(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function boolValue(value: unknown): boolean {
  return typeof value === "boolean" ? value : false;
}

function normalizePriority(value: unknown): CostPriority {
  const priority = maybeString(value)?.toLowerCase();
  if (
    priority === "balanced" ||
    priority === "cost" ||
    priority === "speed" ||
    priority === "privacy"
  ) {
    return priority;
  }
  return "balanced";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => stringValue(item)).filter(Boolean)
    : [];
}

function normalizeCostEstimate(value: unknown): CostEstimate {
  const raw = asRecord(value);
  return {
    estimatedCostUsd: numberValue(raw.estimatedCostUsd),
    free: boolValue(raw.free),
    billingRequired: boolValue(raw.billingRequired),
    inputPer1kUsd: numberValue(raw.inputPer1kUsd),
    outputPer1kUsd: numberValue(raw.outputPer1kUsd),
  };
}

function normalizeLatencyEstimate(value: unknown): LatencyEstimate {
  const raw = asRecord(value);
  return {
    estimatedLatencyMs: numberValue(raw.estimatedLatencyMs),
    speedRank: numberValue(raw.speedRank),
  };
}

function normalizePrivacyFit(value: unknown): PrivacyFit {
  const raw = asRecord(value);
  return {
    score: numberValue(raw.score),
    tier: stringValue(raw.tier, "unknown"),
    sensitiveDataAllowed: boolValue(raw.sensitiveDataAllowed),
    dataLeavesDevice: boolValue(raw.dataLeavesDevice),
    cloudBlockedBecauseSensitive: boolValue(raw.cloudBlockedBecauseSensitive),
  };
}

function normalizeCandidate(value: unknown): CostCandidate {
  const raw = asRecord(value);
  return {
    providerId: stringValue(raw.providerId, "provider"),
    displayName: stringValue(raw.displayName, "Provider"),
    executionTarget: stringValue(raw.executionTarget, "unknown"),
    label: stringValue(raw.label, stringValue(raw.displayName, "Provider")),
    status: stringValue(raw.status, "candidate"),
    blockedReasons: stringList(raw.blockedReasons),
    costEstimate: normalizeCostEstimate(raw.costEstimate),
    latencyEstimate: normalizeLatencyEstimate(raw.latencyEstimate),
    privacyFit: normalizePrivacyFit(raw.privacyFit),
    projectFit: numberValue(raw.projectFit),
    decisionScore: numberValue(raw.decisionScore),
    quotaGuardStatus: maybeString(raw.quotaGuardStatus),
  };
}

function normalizeDecision(value: unknown): CostDecision {
  const raw = asRecord(value);
  return {
    selectedProviderId: stringValue(raw.selectedProviderId, "provider"),
    selectedExecutionTarget: stringValue(raw.selectedExecutionTarget, "unknown"),
    providerLabel: stringValue(raw.providerLabel, "Provider"),
    estimatedCostUsd: numberValue(raw.estimatedCostUsd),
    estimatedLatencyMs: numberValue(raw.estimatedLatencyMs),
    decisionScore: numberValue(raw.decisionScore),
    reason: stringValue(raw.reason, "Cost optimizer selected this target."),
    requiresExplicitUserAction: boolValue(raw.requiresExplicitUserAction),
    cloudBlockedBecauseSensitive: boolValue(raw.cloudBlockedBecauseSensitive),
  };
}

function normalizeGuardedDecision(value: unknown): BudgetGuardDecision | null {
  const raw = asRecord(value);
  if (Object.keys(raw).length === 0) return null;
  return {
    selectedProviderId: maybeString(raw.selectedProviderId),
    selectedExecutionTarget: maybeString(raw.selectedExecutionTarget),
    providerLabel: maybeString(raw.providerLabel),
    estimatedCostUsd: numberValue(raw.estimatedCostUsd),
    estimatedLatencyMs: numberValue(raw.estimatedLatencyMs),
    decisionScore: numberValue(raw.decisionScore),
    quotaGuardStatus: maybeString(raw.quotaGuardStatus),
    blockedReasons: stringList(raw.blockedReasons),
    selectedExecutionTargetChanged: boolValue(raw.selectedExecutionTargetChanged),
  };
}

function normalizeBudgetGuard(value: unknown): BudgetGuard | null {
  const raw = asRecord(value);
  if (Object.keys(raw).length === 0) return null;
  return {
    status: maybeString(raw.status),
    allowedToExecute: boolValue(raw.allowedToExecute),
    blockingReasons: stringList(raw.blockingReasons),
    guardedDecision: normalizeGuardedDecision(raw.guardedDecision) ?? undefined,
  };
}

function normalizePlan(value: unknown): CostOptimizationPlan {
  const raw = asRecord(value);
  const task = asRecord(raw.task);
  const budget = asRecord(raw.budget);
  const sensitivity = asRecord(raw.sensitivity);
  const policy = asRecord(raw.policy);
  return {
    optimizerVersion: maybeString(raw.optimizerVersion) ?? undefined,
    pricingStoreVersion: maybeString(raw.pricingStoreVersion) ?? undefined,
    executionPlannerVersion:
      maybeString(raw.executionPlannerVersion) ?? undefined,
    privacyPolicyVersion: maybeString(raw.privacyPolicyVersion) ?? undefined,
    mode: maybeString(raw.mode) ?? undefined,
    services: stringList(raw.services),
    task: {
      objectiveExcerpt: maybeString(task.objectiveExcerpt) ?? undefined,
      projectId: maybeString(task.projectId),
      projectType: maybeString(task.projectType),
      expectedInputTokens: numberValue(task.expectedInputTokens),
      expectedOutputTokens: numberValue(task.expectedOutputTokens),
      estimatedTotalTokens: numberValue(task.estimatedTotalTokens),
      messageCount: numberValue(task.messageCount, 1),
    },
    priority: normalizePriority(raw.priority),
    budget: {
      budgetUsd:
        raw.budgetUsd === null || budget.budgetUsd === null
          ? null
          : numberValue(budget.budgetUsd),
      hardLimitApplied: boolValue(budget.hardLimitApplied),
    },
    sensitivity: {
      level: maybeString(sensitivity.level) ?? undefined,
      sensitive: boolValue(sensitivity.sensitive),
      signals: stringList(sensitivity.signals),
      reason: maybeString(sensitivity.reason) ?? undefined,
      allowCloudWhenSensitive: boolValue(sensitivity.allowCloudWhenSensitive),
      cloudAllowed: boolValue(sensitivity.cloudAllowed),
    },
    decision: normalizeDecision(raw.decision),
    guardedDecision: normalizeGuardedDecision(raw.guardedDecision),
    candidates: Array.isArray(raw.candidates)
      ? raw.candidates.map(normalizeCandidate)
      : [],
    displayOptions: Array.isArray(raw.displayOptions)
      ? raw.displayOptions.map((item) => {
          const option = asRecord(item);
          return {
            providerId: stringValue(option.providerId, "provider"),
            label: stringValue(option.label, "Provider"),
            estimatedCostUsd: numberValue(option.estimatedCostUsd),
            estimatedLatencyMs: numberValue(option.estimatedLatencyMs),
            status: stringValue(option.status, "candidate"),
          };
        })
      : [],
    budgetGuard: normalizeBudgetGuard(raw.budgetGuard),
    policy: {
      displayOnlyWhenUseful: boolValue(policy.displayOnlyWhenUseful),
      requiresExplicitCloudValidation: boolValue(
        policy.requiresExplicitCloudValidation,
      ),
      cloudBlockedBecauseSensitive: boolValue(
        policy.cloudBlockedBecauseSensitive,
      ),
      humanConfirmationRequiredBeforePaidCloud: boolValue(
        policy.humanConfirmationRequiredBeforePaidCloud,
      ),
      frontendDirectProviderCallAllowed: boolValue(
        policy.frontendDirectProviderCallAllowed,
      ),
      sensitiveCloudDefaultAllowed: boolValue(
        policy.sensitiveCloudDefaultAllowed,
      ),
      quotaGuardApplied: boolValue(policy.quotaGuardApplied),
    },
    sideEffects: asRecord(raw.sideEffects),
  };
}

export async function createCostOptimizationPlan(payload: {
  objective: string;
  projectId?: string | null;
  projectType?: string | null;
  priority?: CostPriority;
  sensitivityLevel?: string | null;
  constraints?: string[];
  expectedInputTokens?: number | null;
  expectedOutputTokens?: number | null;
  messageCount?: number | null;
  budgetUsd?: number | null;
  allowCloudWhenSensitive?: boolean;
  enforceQuotas?: boolean;
  storeLog?: boolean;
}): Promise<CostOptimizationResponse> {
  const response = await authFetch("/api/cognix/costs/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objective: payload.objective,
      projectId: payload.projectId ?? null,
      projectType: payload.projectType ?? null,
      priority: payload.priority ?? "balanced",
      sensitivityLevel: payload.sensitivityLevel ?? null,
      constraints: payload.constraints ?? [],
      expectedInputTokens: payload.expectedInputTokens ?? null,
      expectedOutputTokens: payload.expectedOutputTokens ?? null,
      messageCount: payload.messageCount ?? null,
      budgetUsd: payload.budgetUsd ?? null,
      allowCloudWhenSensitive: payload.allowCloudWhenSensitive ?? false,
      enforceQuotas: payload.enforceQuotas ?? true,
      storeLog: payload.storeLog ?? false,
    }),
  });
  const body = await parseJsonOrThrow<{
    username?: string;
    costOptimizationPlan?: unknown;
    costLog?: Record<string, unknown> | null;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    username: body.username,
    costOptimizationPlan: normalizePlan(body.costOptimizationPlan),
    costLog: body.costLog ?? null,
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}
