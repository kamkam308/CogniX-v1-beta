// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { authFetch } from "@/features/auth";
import { consumeNativePathToken } from "@/features/native-intents/api";
import { formatFastApiDetail } from "@/lib/format-fastapi-error";
import type {
  MessageRecord,
  ModelType,
  ProjectRecord,
  ThreadRecord,
} from "../types";
import type {
  ApiMonitorEntry,
  ApiMonitorResponse,
  AudioGenerationResponse,
  GgufVariantsResponse,
  InferenceStatusResponse,
  ListLorasResponse,
  ListModelsResponse,
  LoadModelRequest,
  LoadModelResponse,
  OpenAIChatChunk,
  OpenAIChatCompletionsRequest,
  UnloadModelRequest,
  ValidateModelResponse,
} from "../types/api";

export const CHAT_HISTORY_UPDATED_EVENT = "cognix-chat-history-updated";

export function notifyChatHistoryUpdated(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CHAT_HISTORY_UPDATED_EVENT));
  }
}

function parseErrorText(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const providerError = parseProviderErrorText(body);
    if (providerError) return providerError;
    const detail = (body as { detail?: unknown }).detail;
    const formatted = formatFastApiDetail(detail);
    if (formatted) return formatted;
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return `Request failed (${status})`;
}

function parseProviderErrorText(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return parseProviderErrorText(JSON.parse(trimmed)) ?? trimmed;
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }
  if (!value || typeof value !== "object") return null;
  const record = value as {
    detail?: unknown;
    error?: unknown;
    message?: unknown;
  };
  return (
    parseProviderErrorText(record.message) ??
    parseProviderErrorText(record.error) ??
    parseProviderErrorText(record.detail)
  );
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(parseErrorText(response.status, body));
  }
  return body as T;
}

export async function listModels(): Promise<ListModelsResponse> {
  const response = await authFetch("/api/models/list");
  return parseJsonOrThrow<ListModelsResponse>(response);
}

export async function listLoras(
  outputsDir?: string,
): Promise<ListLorasResponse> {
  const query = outputsDir
    ? `?${new URLSearchParams({ outputs_dir: outputsDir }).toString()}`
    : "";
  const response = await authFetch(`/api/models/loras${query}`);
  return parseJsonOrThrow<ListLorasResponse>(response);
}

export async function getInferenceStatus(): Promise<InferenceStatusResponse> {
  const response = await authFetch("/api/inference/status");
  return parseJsonOrThrow<InferenceStatusResponse>(response);
}

export async function getApiMonitor(): Promise<ApiMonitorResponse> {
  const response = await authFetch("/api/inference/monitor");
  return parseJsonOrThrow<ApiMonitorResponse>(response);
}

export async function getApiMonitorEntry(id: string): Promise<ApiMonitorEntry> {
  const response = await authFetch(
    `/api/inference/monitor/${encodeURIComponent(id)}`,
  );
  return parseJsonOrThrow<ApiMonitorEntry>(response);
}

export interface CogniXRouterClassification {
  selectedDomain: string;
  label: string;
  recommendedModelLabel: string;
  confidence: number;
  needsClarification: boolean;
  scores: Record<string, number>;
  routingMode: string;
  reason: string;
}

export interface CogniXExecutionStep {
  id: string;
  label: string;
  status: string;
  detail: string;
}

export interface CogniXExecutionStrategy {
  status: string;
  executionMode?: string | null;
  providerId?: string | null;
  providerType?: string | null;
  providerName?: string | null;
  baseUrl?: string | null;
  selectedModelId?: string | null;
  selectedModelLabel?: string | null;
  domainModelLabel?: string | null;
  requiresModelLoad: boolean;
  willLoadModel: boolean;
  willGenerate: boolean;
  reason: string;
}

export interface CogniXExecutionPlan {
  username: string;
  orchestratorVersion: string;
  mode: "dry_run" | string;
  objectiveExcerpt: string;
  classification: CogniXRouterClassification;
  executionStrategy: CogniXExecutionStrategy;
  steps: CogniXExecutionStep[];
  warnings: string[];
  sideEffects: {
    modelLoad: boolean;
    generation: boolean;
    networkModelCall: boolean;
    cacheMode: string;
  };
  logId: string | number | null;
  orchestratorLogId?: string | number | null;
}

export interface CogniXDecisionReason {
  code?: string;
  label?: string;
  detail?: string;
  confidence?: number | null;
  evidence?: Record<string, unknown>;
}

export interface CogniXDecisionExplanation {
  title?: string;
  summary?: string;
  answer?: string;
  question?: string | null;
  sourceType?: string;
  sourceId?: string | null;
  decisionType?: string;
  reasonCodes?: CogniXDecisionReason[];
  trace?: Record<string, unknown>;
  display?: Record<string, unknown>;
}

export interface CogniXDecisionExplainResult {
  username: string;
  decisionExplanation: CogniXDecisionExplanation;
  storedDecision?: Record<string, unknown> | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface CogniXContextSection {
  id: string;
  label: string;
  source: string;
  priority: number;
  content: string;
  charCount: number;
  included: boolean;
  truncated: boolean;
}

export interface CogniXContextPack {
  username: string;
  contextManagerVersion: string;
  mode: string;
  projectId: string | null;
  objectiveExcerpt: string;
  sections: CogniXContextSection[];
  systemInstruction: string;
  includedSectionIds: string[];
  warnings: string[];
  auditLogId?: string | null;
  sideEffects: {
    modelLoad: boolean;
    generation: boolean;
    networkModelCall: boolean;
  };
}

export async function classifyCogniXObjective(payload: {
  objective: string;
  projectType?: string | null;
}): Promise<{
  username: string;
  classification: CogniXRouterClassification;
  logId: string | number | null;
}> {
  const response = await authFetch("/api/cognix/router/classify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objective: payload.objective,
      project_type: payload.projectType ?? null,
    }),
  });
  return parseJsonOrThrow(response);
}

export async function buildCogniXContextPack(payload: {
  objective?: string | null;
  projectId?: string | null;
}): Promise<CogniXContextPack> {
  const response = await authFetch("/api/cognix/context/pack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objective: payload.objective ?? null,
      project_id: payload.projectId ?? null,
    }),
  });
  return parseJsonOrThrow(response);
}

export interface ContextGraphVisualToken {
  colorToken?: string;
  icon?: string;
}

export interface ContextGraphNode {
  id: string;
  type: string;
  label: string;
  source?: string;
  weight?: number;
  visual?: ContextGraphVisualToken;
  metadata?: Record<string, unknown>;
}

export interface ContextGraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label?: string;
  weight?: number;
  metadata?: Record<string, unknown>;
}

export interface ContextGraphSnapshot {
  contextGraphVersion?: string;
  entityExtractorVersion?: string;
  relationBuilderVersion?: string;
  mode?: string;
  projectId?: string | null;
  projectName?: string | null;
  projectType?: string | null;
  nodes?: ContextGraphNode[];
  edges?: ContextGraphEdge[];
  summary?: {
    nodeCount?: number;
    edgeCount?: number;
    conceptCount?: number;
    documentCount?: number;
    chatCount?: number;
    fileCount?: number;
    modelCount?: number;
    toolCount?: number;
  };
  displayContract?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface StoredContextGraphSnapshot {
  id: string;
  projectId?: string | null;
  title?: string | null;
  graph?: ContextGraphSnapshot;
  nodeCount?: number | null;
  edgeCount?: number | null;
  createdAt?: string | null;
}

export interface ContextGraphBuildResult {
  username: string;
  contextGraph: ContextGraphSnapshot;
  snapshot?: StoredContextGraphSnapshot | null;
  auditLogId?: string | null;
  warnings?: string[];
  sideEffects?: Record<string, unknown>;
}

export async function buildContextGraph(payload: {
  projectId?: string | null;
  projectName?: string | null;
  projectType?: string | null;
  messages?: Array<Record<string, unknown>> | null;
  documents?: Array<Record<string, unknown>> | null;
  files?: unknown[] | null;
  decisions?: unknown[] | null;
  tasks?: unknown[] | null;
  models?: unknown[] | null;
  tools?: unknown[] | null;
  includeProjectThreads?: boolean;
  storeSnapshot?: boolean;
}): Promise<ContextGraphBuildResult> {
  const response = await authFetch("/api/cognix/context/graph/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<ContextGraphBuildResult>(response);
}

export async function listContextGraphSnapshots(payload?: {
  projectId?: string | null;
}): Promise<StoredContextGraphSnapshot[]> {
  const params = new URLSearchParams();
  if (payload?.projectId) params.set("project_id", payload.projectId);
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await authFetch(`/api/cognix/context/graph/snapshots${query}`);
  const body = await parseJsonOrThrow<{
    snapshots?: StoredContextGraphSnapshot[];
  }>(response);
  return body.snapshots ?? [];
}

export type WorkflowStepType =
  | "user_action"
  | "tool_call"
  | "model_call"
  | "parameters"
  | "output"
  | "export"
  | "approval"
  | string;

export interface WorkflowStepInput {
  stepType: WorkflowStepType;
  label: string;
  toolName?: string | null;
  modelId?: string | null;
  parameters?: Record<string, unknown>;
  outputSummary?: string | null;
  requiresApproval?: boolean;
}

export interface WorkflowStepRecord extends WorkflowStepInput {
  id?: string | null;
  workflowId?: string | null;
  stepIndex: number;
  willExecuteNow?: boolean;
  step?: Record<string, unknown>;
  createdAt?: string | null;
}

export interface WorkflowTemplate {
  id: string;
  workflowType: string;
  label: string;
  steps: WorkflowStepInput[];
}

export interface WorkflowRecord {
  id: string;
  projectId?: string | null;
  title: string;
  objective?: string | null;
  workflowType: string;
  status?: "active" | "disabled" | "archived" | string;
  shareStatus?: "private" | "shared" | string;
  metadata?: Record<string, unknown>;
  steps?: WorkflowStepRecord[];
  stepCount?: number | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface WorkflowRecordingPlan {
  workflowRecorderVersion?: string;
  workflowTemplateManagerVersion?: string;
  mode?: string;
  workflow?: Partial<WorkflowRecord>;
  steps?: WorkflowStepRecord[];
  summary?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface WorkflowRunPlanStep {
  stepId?: string | null;
  stepIndex: number;
  stepType?: WorkflowStepType;
  label?: string | null;
  requiresApproval?: boolean;
  willExecuteNow?: boolean;
  blockedSideEffects?: string[];
}

export interface WorkflowRunPlan {
  workflowRunnerVersion?: string;
  mode?: string;
  workflowId?: string | null;
  runMode?: "dry_run" | "simulation" | string;
  inputs?: Record<string, unknown>;
  orderedSteps?: WorkflowRunPlanStep[];
  summary?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface WorkflowRunRecord {
  id: string;
  workflowId?: string | null;
  status?: string | null;
  runMode?: string | null;
  runPlan?: WorkflowRunPlan;
  logs?: Array<Record<string, unknown>>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface WorkflowExportBundle {
  username?: string;
  workflow: WorkflowRecord;
  runs?: WorkflowRunRecord[];
  exportedAt?: string;
}

export interface WorkflowRecordResult {
  recordingPlan: WorkflowRecordingPlan;
  workflow: WorkflowRecord | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface WorkflowUpdateResult {
  workflow: WorkflowRecord;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface WorkflowRunPlanResult {
  runPlan: WorkflowRunPlan;
  run: WorkflowRunRecord;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asOptionalRecord(
  value: unknown,
): Record<string, unknown> | undefined {
  const record = asRecord(value);
  return Object.keys(record).length > 0 ? record : undefined;
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

function boolValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function parseRecordJson(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value !== "string" || !value.trim()) return undefined;
  try {
    return asOptionalRecord(JSON.parse(value));
  } catch {
    return undefined;
  }
}

function normalizeWorkflowStep(
  value: unknown,
  fallbackIndex = 0,
): WorkflowStepRecord {
  const raw = asRecord(value);
  const nestedStep = asRecord(raw.step);
  return {
    id: maybeString(raw.id),
    workflowId: maybeString(raw.workflowId ?? raw.workflow_id),
    stepIndex: numberValue(
      raw.stepIndex ?? raw.step_index ?? nestedStep.stepIndex,
      fallbackIndex,
    ),
    stepType: stringValue(
      raw.stepType ?? raw.step_type ?? nestedStep.stepType,
      "user_action",
    ),
    label: stringValue(raw.label ?? nestedStep.label, `Step ${fallbackIndex + 1}`),
    toolName: maybeString(raw.toolName ?? raw.tool_name ?? nestedStep.toolName),
    modelId: maybeString(raw.modelId ?? raw.model_id ?? nestedStep.modelId),
    parameters:
      parseRecordJson(raw.parameters ?? raw.parameters_json) ??
      parseRecordJson(nestedStep.parameters) ??
      {},
    outputSummary: maybeString(
      raw.outputSummary ?? raw.output_summary ?? nestedStep.outputSummary,
    ),
    requiresApproval: boolValue(
      raw.requiresApproval ?? nestedStep.requiresApproval,
    ),
    willExecuteNow: boolValue(raw.willExecuteNow ?? nestedStep.willExecuteNow),
    step: asOptionalRecord(raw.step),
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
  };
}

function normalizeWorkflow(value: unknown): WorkflowRecord {
  const raw = asRecord(value);
  const steps = Array.isArray(raw.steps)
    ? raw.steps.map((step, index) => normalizeWorkflowStep(step, index))
    : undefined;
  return {
    id: stringValue(raw.id),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    title: stringValue(raw.title, "Workflow CogniX"),
    objective: maybeString(raw.objective),
    workflowType: stringValue(raw.workflowType ?? raw.workflow_type, "custom"),
    status: stringValue(raw.status, "active"),
    shareStatus: stringValue(raw.shareStatus ?? raw.share_status, "private"),
    metadata:
      parseRecordJson(raw.metadata) ?? parseRecordJson(raw.metadata_json) ?? {},
    steps,
    stepCount: numberValue(raw.stepCount ?? raw.step_count, steps?.length ?? 0),
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeWorkflowRunPlanStep(
  value: unknown,
  fallbackIndex = 0,
): WorkflowRunPlanStep {
  const raw = asRecord(value);
  return {
    stepId: maybeString(raw.stepId ?? raw.step_id),
    stepIndex: numberValue(raw.stepIndex ?? raw.step_index, fallbackIndex),
    stepType: maybeString(raw.stepType ?? raw.step_type) ?? "user_action",
    label: maybeString(raw.label),
    requiresApproval: boolValue(raw.requiresApproval),
    willExecuteNow: boolValue(raw.willExecuteNow),
    blockedSideEffects: Array.isArray(raw.blockedSideEffects)
      ? raw.blockedSideEffects.map((item) => stringValue(item)).filter(Boolean)
      : [],
  };
}

function normalizeWorkflowRunPlan(value: unknown): WorkflowRunPlan {
  const raw = asRecord(value);
  return {
    workflowRunnerVersion: maybeString(raw.workflowRunnerVersion) ?? undefined,
    mode: maybeString(raw.mode) ?? undefined,
    workflowId: maybeString(raw.workflowId ?? raw.workflow_id),
    runMode: maybeString(raw.runMode ?? raw.run_mode) ?? "dry_run",
    inputs: parseRecordJson(raw.inputs) ?? {},
    orderedSteps: Array.isArray(raw.orderedSteps)
      ? raw.orderedSteps.map((step, index) =>
          normalizeWorkflowRunPlanStep(step, index),
        )
      : [],
    summary: parseRecordJson(raw.summary) ?? {},
    sideEffects: parseRecordJson(raw.sideEffects) ?? {},
  };
}

function normalizeWorkflowRun(value: unknown): WorkflowRunRecord {
  const raw = asRecord(value);
  return {
    id: stringValue(raw.id),
    workflowId: maybeString(raw.workflowId ?? raw.workflow_id),
    status: maybeString(raw.status),
    runMode: maybeString(raw.runMode ?? raw.run_mode),
    runPlan: normalizeWorkflowRunPlan(raw.runPlan ?? raw.run_plan_json),
    logs: Array.isArray(raw.logs)
      ? raw.logs.map((log) => asRecord(log))
      : undefined,
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeWorkflowTemplate(value: unknown): WorkflowTemplate {
  const raw = asRecord(value);
  return {
    id: stringValue(raw.id),
    workflowType: stringValue(raw.workflowType ?? raw.workflow_type, "custom"),
    label: stringValue(raw.label, "Workflow"),
    steps: Array.isArray(raw.steps)
      ? raw.steps.map((step, index) => normalizeWorkflowStep(step, index))
      : [],
  };
}

export async function listWorkflowTemplates(): Promise<WorkflowTemplate[]> {
  const response = await authFetch("/api/cognix/workflows/templates");
  const body = await parseJsonOrThrow<{
    templateRegistry?: { templates?: unknown[] };
  }>(response);
  return (body.templateRegistry?.templates ?? []).map(normalizeWorkflowTemplate);
}

export async function listWorkflows(payload?: {
  includeDisabled?: boolean;
}): Promise<WorkflowRecord[]> {
  const query = payload?.includeDisabled ? "?include_disabled=true" : "";
  const response = await authFetch(`/api/cognix/workflows${query}`);
  const body = await parseJsonOrThrow<{ workflows?: unknown[] }>(response);
  return (body.workflows ?? []).map(normalizeWorkflow);
}

export async function getWorkflow(workflowId: string): Promise<WorkflowRecord> {
  const response = await authFetch(
    `/api/cognix/workflows/${encodeURIComponent(workflowId)}`,
  );
  const body = await parseJsonOrThrow<{ workflow?: unknown }>(response);
  return normalizeWorkflow(body.workflow);
}

export async function recordWorkflow(payload: {
  title?: string | null;
  objective?: string | null;
  workflowType?: string | null;
  projectId?: string | null;
  steps?: WorkflowStepInput[];
  metadata?: Record<string, unknown>;
  storeWorkflow?: boolean;
}): Promise<WorkflowRecordResult> {
  const response = await authFetch("/api/cognix/workflows/record", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: payload.title ?? null,
      objective: payload.objective ?? null,
      workflowType: payload.workflowType ?? null,
      projectId: payload.projectId ?? null,
      steps: payload.steps ?? [],
      metadata: payload.metadata ?? {},
      storeWorkflow: payload.storeWorkflow ?? true,
    }),
  });
  const body = await parseJsonOrThrow<{
    recordingPlan?: WorkflowRecordingPlan;
    workflow?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    recordingPlan: body.recordingPlan ?? {},
    workflow: body.workflow ? normalizeWorkflow(body.workflow) : null,
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function updateWorkflow(
  workflowId: string,
  payload: {
    title?: string | null;
    objective?: string | null;
    status?: "active" | "disabled" | "archived" | null;
    shareStatus?: "private" | "shared" | null;
  },
): Promise<WorkflowUpdateResult> {
  const response = await authFetch(
    `/api/cognix/workflows/${encodeURIComponent(workflowId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const body = await parseJsonOrThrow<{
    workflow?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    workflow: normalizeWorkflow(body.workflow),
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  const response = await authFetch(
    `/api/cognix/workflows/${encodeURIComponent(workflowId)}`,
    { method: "DELETE" },
  );
  await parseJsonOrThrow<unknown>(response);
}

export async function exportWorkflowBundle(
  workflowId: string,
): Promise<WorkflowExportBundle> {
  const response = await authFetch(
    `/api/cognix/workflows/${encodeURIComponent(workflowId)}/export`,
  );
  const body = await parseJsonOrThrow<{ workflowExport?: unknown }>(response);
  const bundle = asRecord(body.workflowExport);
  return {
    username: maybeString(bundle.username) ?? undefined,
    workflow: normalizeWorkflow(bundle.workflow),
    runs: Array.isArray(bundle.runs)
      ? bundle.runs.map(normalizeWorkflowRun)
      : [],
    exportedAt: maybeString(bundle.exportedAt) ?? undefined,
  };
}

export async function buildWorkflowRunPlan(payload: {
  workflowId: string;
  runMode?: "dry_run" | "simulation";
  inputs?: Record<string, unknown>;
}): Promise<WorkflowRunPlanResult> {
  const response = await authFetch(
    `/api/cognix/workflows/${encodeURIComponent(payload.workflowId)}/run-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        runMode: payload.runMode ?? "dry_run",
        inputs: payload.inputs ?? {},
      }),
    },
  );
  const body = await parseJsonOrThrow<{
    runPlan?: unknown;
    run?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    runPlan: normalizeWorkflowRunPlan(body.runPlan),
    run: normalizeWorkflowRun(body.run),
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function listWorkflowRuns(
  workflowId: string,
): Promise<WorkflowRunRecord[]> {
  const response = await authFetch(
    `/api/cognix/workflows/${encodeURIComponent(workflowId)}/runs`,
  );
  const body = await parseJsonOrThrow<{ runs?: unknown[] }>(response);
  return (body.runs ?? []).map(normalizeWorkflowRun);
}

export interface CompressionEvaluation {
  originalTokenCount?: number;
  compressedTokenCount?: number;
  reductionRatio?: number;
  retainedKeywordRatio?: number;
  retainedObjectiveRatio?: number;
  lostInfoRisk?: "low" | "medium" | "high" | string;
  qualityGate?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface PromptCompressionSummary {
  originalTokenCount?: number;
  compressedTokenCount?: number;
  targetTokenCount?: number;
  reductionRatio?: number;
  badge?: string | null;
  lostInfoRisk?: "low" | "medium" | "high" | string;
  messageCount?: number;
  summarizedMessageCount?: number;
  retainedRecentMessageCount?: number;
  rawHistoryIncluded?: boolean;
  redactionCount?: number;
}

export interface PromptCompressionPlan {
  promptCompressionVersion?: string;
  contextRankerVersion?: string;
  compressionEvaluatorVersion?: string;
  mode?: string;
  projectId?: string | null;
  objective?: string | null;
  targetTokens?: number;
  contextHash?: string;
  ranking?: Array<Record<string, unknown>>;
  selectedSentenceIndexes?: number[];
  compressedContext?: string;
  evaluation?: CompressionEvaluation;
  summary?: PromptCompressionSummary;
  sideEffects?: Record<string, unknown>;
}

export interface ConversationSummaryPlan extends PromptCompressionPlan {
  conversationSummaryContractVersion?: string;
  recentMessageLimit?: number;
  conversationSummary?: {
    summaryText?: string;
    summaryRequired?: boolean;
    readyForContextInjection?: boolean;
    summarizedMessageCount?: number;
    retainedRecentMessageCount?: number;
    redactionMarkers?: string[];
  };
  recentMessages?: Array<Record<string, unknown>>;
  boundaryContract?: Record<string, unknown>;
  policy?: Record<string, unknown>;
}

export interface CompressedContextRecord {
  id: string;
  projectId?: string | null;
  contextHash?: string | null;
  objectiveExcerpt?: string | null;
  originalTokenCount?: number | null;
  compressedTokenCount?: number | null;
  reductionRatio?: number | null;
  compressedContext?: string;
  ranking?: Array<Record<string, unknown>>;
  evaluation?: CompressionEvaluation;
  status?: "active" | "deleted" | string;
  logs?: Array<Record<string, unknown>>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface PromptCompressionResult {
  compressionPlan: PromptCompressionPlan;
  compressedContext: CompressedContextRecord | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface ConversationSummaryResult {
  conversationSummaryPlan: ConversationSummaryPlan;
  compressedContext: CompressedContextRecord | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

function normalizeCompressionEvaluation(value: unknown): CompressionEvaluation {
  const raw = asRecord(value);
  return {
    originalTokenCount: numberValue(raw.originalTokenCount, 0),
    compressedTokenCount: numberValue(raw.compressedTokenCount, 0),
    reductionRatio: numberValue(raw.reductionRatio, 0),
    retainedKeywordRatio: numberValue(raw.retainedKeywordRatio, 0),
    retainedObjectiveRatio: numberValue(raw.retainedObjectiveRatio, 0),
    lostInfoRisk: maybeString(raw.lostInfoRisk) ?? undefined,
    qualityGate: parseRecordJson(raw.qualityGate) ?? {},
    sideEffects: parseRecordJson(raw.sideEffects) ?? {},
  };
}

function normalizePromptCompressionSummary(
  value: unknown,
): PromptCompressionSummary {
  const raw = asRecord(value);
  return {
    originalTokenCount: numberValue(raw.originalTokenCount, 0),
    compressedTokenCount: numberValue(raw.compressedTokenCount, 0),
    targetTokenCount: numberValue(raw.targetTokenCount, 0),
    reductionRatio: numberValue(raw.reductionRatio, 0),
    badge: maybeString(raw.badge),
    lostInfoRisk: maybeString(raw.lostInfoRisk) ?? undefined,
    messageCount: numberValue(raw.messageCount, 0),
    summarizedMessageCount: numberValue(raw.summarizedMessageCount, 0),
    retainedRecentMessageCount: numberValue(raw.retainedRecentMessageCount, 0),
    rawHistoryIncluded: boolValue(raw.rawHistoryIncluded),
    redactionCount: numberValue(raw.redactionCount, 0),
  };
}

function normalizePromptCompressionPlan(
  value: unknown,
): PromptCompressionPlan {
  const raw = asRecord(value);
  return {
    promptCompressionVersion:
      maybeString(raw.promptCompressionVersion) ?? undefined,
    contextRankerVersion: maybeString(raw.contextRankerVersion) ?? undefined,
    compressionEvaluatorVersion:
      maybeString(raw.compressionEvaluatorVersion) ?? undefined,
    mode: maybeString(raw.mode) ?? undefined,
    projectId: maybeString(raw.projectId ?? raw.project_id),
    objective: maybeString(raw.objective),
    targetTokens: numberValue(raw.targetTokens ?? raw.target_tokens, 0),
    contextHash: maybeString(raw.contextHash ?? raw.context_hash) ?? undefined,
    ranking: Array.isArray(raw.ranking)
      ? raw.ranking.map((item) => asRecord(item))
      : [],
    selectedSentenceIndexes: Array.isArray(raw.selectedSentenceIndexes)
      ? raw.selectedSentenceIndexes
          .map((item) => numberValue(item, -1))
          .filter((item) => item >= 0)
      : [],
    compressedContext:
      maybeString(raw.compressedContext ?? raw.compressed_context) ?? "",
    evaluation: normalizeCompressionEvaluation(raw.evaluation),
    summary: normalizePromptCompressionSummary(raw.summary),
    sideEffects: parseRecordJson(raw.sideEffects) ?? {},
  };
}

function normalizeConversationSummaryPlan(
  value: unknown,
): ConversationSummaryPlan {
  const raw = asRecord(value);
  const base = normalizePromptCompressionPlan(raw);
  const conversationSummary = asRecord(raw.conversationSummary);
  return {
    ...base,
    conversationSummaryContractVersion:
      maybeString(raw.conversationSummaryContractVersion) ?? undefined,
    recentMessageLimit: numberValue(raw.recentMessageLimit, 0),
    conversationSummary: {
      summaryText: maybeString(conversationSummary.summaryText) ?? undefined,
      summaryRequired: boolValue(conversationSummary.summaryRequired),
      readyForContextInjection: boolValue(
        conversationSummary.readyForContextInjection,
      ),
      summarizedMessageCount: numberValue(
        conversationSummary.summarizedMessageCount,
        0,
      ),
      retainedRecentMessageCount: numberValue(
        conversationSummary.retainedRecentMessageCount,
        0,
      ),
      redactionMarkers: Array.isArray(conversationSummary.redactionMarkers)
        ? conversationSummary.redactionMarkers
            .map((item) => stringValue(item))
            .filter(Boolean)
        : [],
    },
    recentMessages: Array.isArray(raw.recentMessages)
      ? raw.recentMessages.map((item) => asRecord(item))
      : [],
    boundaryContract: parseRecordJson(raw.boundaryContract) ?? {},
    policy: parseRecordJson(raw.policy) ?? {},
  };
}

function normalizeCompressedContext(value: unknown): CompressedContextRecord {
  const raw = asRecord(value);
  const logs = Array.isArray(raw.logs)
    ? raw.logs.map((log) => asRecord(log))
    : undefined;
  return {
    id: stringValue(raw.id),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    contextHash: maybeString(raw.contextHash ?? raw.context_hash),
    objectiveExcerpt: maybeString(
      raw.objectiveExcerpt ?? raw.objective_excerpt,
    ),
    originalTokenCount: numberValue(
      raw.originalTokenCount ?? raw.original_token_count,
      0,
    ),
    compressedTokenCount: numberValue(
      raw.compressedTokenCount ?? raw.compressed_token_count,
      0,
    ),
    reductionRatio: numberValue(raw.reductionRatio ?? raw.reduction_ratio, 0),
    compressedContext:
      maybeString(raw.compressedContext ?? raw.compressed_context) ?? "",
    ranking: Array.isArray(raw.ranking)
      ? raw.ranking.map((item) => asRecord(item))
      : [],
    evaluation: normalizeCompressionEvaluation(raw.evaluation),
    status: maybeString(raw.status) ?? "active",
    logs,
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

export async function createPromptCompressionPlan(payload: {
  context: string;
  objective?: string | null;
  projectId?: string | null;
  targetTokens?: number;
  storeContext?: boolean;
}): Promise<PromptCompressionResult> {
  const response = await authFetch("/api/cognix/prompt-compression/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      context: payload.context,
      objective: payload.objective ?? null,
      projectId: payload.projectId ?? null,
      targetTokens: payload.targetTokens ?? 500,
      storeContext: payload.storeContext ?? true,
    }),
  });
  const body = await parseJsonOrThrow<{
    compressionPlan?: unknown;
    compressedContext?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    compressionPlan: normalizePromptCompressionPlan(body.compressionPlan),
    compressedContext: body.compressedContext
      ? normalizeCompressedContext(body.compressedContext)
      : null,
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function createConversationSummaryPlan(payload: {
  messages: Array<Record<string, unknown>>;
  objective?: string | null;
  projectId?: string | null;
  targetTokens?: number;
  recentMessageLimit?: number;
  storeContext?: boolean;
}): Promise<ConversationSummaryResult> {
  const response = await authFetch(
    "/api/cognix/prompt-compression/conversation-summary-plan",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: payload.messages,
        objective: payload.objective ?? null,
        projectId: payload.projectId ?? null,
        targetTokens: payload.targetTokens ?? 420,
        recentMessageLimit: payload.recentMessageLimit ?? 6,
        storeContext: payload.storeContext ?? true,
      }),
    },
  );
  const body = await parseJsonOrThrow<{
    conversationSummaryPlan?: unknown;
    compressedContext?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    conversationSummaryPlan: normalizeConversationSummaryPlan(
      body.conversationSummaryPlan,
    ),
    compressedContext: body.compressedContext
      ? normalizeCompressedContext(body.compressedContext)
      : null,
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function listCompressedContexts(payload?: {
  includeDeleted?: boolean;
  projectId?: string | null;
}): Promise<CompressedContextRecord[]> {
  const params = new URLSearchParams();
  if (payload?.includeDeleted) params.set("include_deleted", "true");
  if (payload?.projectId) params.set("projectId", payload.projectId);
  const query = params.toString();
  const response = await authFetch(
    `/api/cognix/prompt-compression/contexts${query ? `?${query}` : ""}`,
  );
  const body = await parseJsonOrThrow<{ contexts?: unknown[] }>(response);
  return (body.contexts ?? []).map(normalizeCompressedContext);
}

export async function deleteCompressedContext(contextId: string): Promise<void> {
  const response = await authFetch(
    `/api/cognix/prompt-compression/contexts/${encodeURIComponent(contextId)}`,
    { method: "DELETE" },
  );
  await parseJsonOrThrow<unknown>(response);
}

export interface ContextHeatmapEntry {
  id?: string | null;
  projectId?: string | null;
  chunkId: string;
  sourceType?: string | null;
  sourceId?: string | null;
  title?: string | null;
  utilityScore?: number;
  usageCount?: number;
  responseCount?: number;
  citationCount?: number;
  copiedTermCount?: number;
  ageDays?: number;
  bucket?: "very_useful" | "low_usage" | "archive_candidate" | string;
  label?: string | null;
  recommendedAction?: "keep" | "review" | "archive" | "deprioritize" | string;
  themeToken?: string | null;
  matchedObjectiveTerms?: string[];
  signals?: Record<string, unknown>;
  entry?: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ContextUsageStat {
  id?: string | null;
  projectId?: string | null;
  chunkId: string;
  sourceType?: string | null;
  sourceId?: string | null;
  usageCount?: number;
  responseCount?: number;
  citationCount?: number;
  utilityScore?: number;
  metadata?: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ContextHeatmapPlan {
  usageTrackerVersion?: string;
  heatmapGeneratorVersion?: string;
  memoryGarbageCollectorVersion?: string;
  mode?: string;
  projectId?: string | null;
  objective?: string | null;
  entries?: ContextHeatmapEntry[];
  summary?: {
    chunkCount?: number;
    bucketCounts?: Record<string, number>;
    averageUtilityScore?: number;
    archiveCandidateCount?: number;
    automaticArchiveWillRun?: boolean;
  };
  garbageCollectorPlan?: {
    candidateChunkIds?: string[];
    recommendedAction?: string;
    automaticArchiveAllowed?: boolean;
    automaticDeleteAllowed?: boolean;
    requiresHumanConfirmation?: boolean;
  };
  display?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface ContextHeatmapPlanResult {
  contextHeatmapPlan: ContextHeatmapPlan;
  storedHeatmapEntries: ContextHeatmapEntry[];
  storedUsageStats: ContextUsageStat[];
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface ProjectDnaModelRef {
  modelId: string;
  label: string;
}

export interface ProjectDnaToolRef {
  toolId: string;
  label: string;
}

export interface ProjectDnaDecision {
  decisionKey?: string;
  title: string;
  rationale?: string;
  status?: string;
}

export interface ProjectDnaProfile {
  username?: string | null;
  projectId?: string | null;
  projectName?: string | null;
  objective?: string | null;
  context?: string | null;
  responseStyle?: string | null;
  preferredModels: ProjectDnaModelRef[];
  allowedTools: ProjectDnaToolRef[];
  constraints: string[];
  decisions: ProjectDnaDecision[];
  sectionStates: Record<string, string>;
  completion: {
    readySectionCount: number;
    totalSectionCount: number;
    readySectionIds: string[];
    score: number;
  };
  dnaHash?: string | null;
}

export interface ProjectDnaInjectionPlan {
  contextInjectorVersion?: string;
  channelId?: string;
  status?: string;
  includedSectionIds: string[];
  priority?: number;
  maxTokens?: number;
  willInjectNow?: boolean;
  contextManagerCompatible?: boolean;
  rawHistoryAllowed?: boolean;
  reason?: string;
}

export interface ProjectDnaPlan {
  projectDnaServiceVersion?: string;
  profileBuilderVersion?: string;
  contextInjectorVersion?: string;
  mode?: string;
  projectId?: string | null;
  status?: string;
  profile: ProjectDnaProfile;
  contextInjectionPlan: ProjectDnaInjectionPlan;
  sideEffects?: Record<string, unknown>;
}

export interface ProjectDnaRecord {
  id?: string | null;
  projectId?: string | null;
  objective?: string | null;
  context?: string | null;
  responseStyle?: string | null;
  preferredModels: ProjectDnaModelRef[];
  allowedTools: ProjectDnaToolRef[];
  dna: ProjectDnaPlan | null;
  dnaHash?: string | null;
  status?: string | null;
  constraints?: string[];
  decisions?: ProjectDnaDecision[];
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ProjectDnaResult {
  projectDnaPlan: ProjectDnaPlan;
  projectDna?: ProjectDnaRecord | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface ProjectDnaPayload {
  projectId: string;
  objective?: string | null;
  context?: string | null;
  responseStyle?: string | null;
  preferredModels?: Array<string | ProjectDnaModelRef>;
  allowedTools?: Array<string | ProjectDnaToolRef>;
  constraints?: string[];
  decisions?: Array<string | ProjectDnaDecision>;
  storeDna?: boolean;
}

function normalizeStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .map((item) => {
          const record = asRecord(item);
          return stringValue(
            record.label ?? record.title ?? record.value ?? item,
          ).trim();
        })
        .filter(Boolean)
    : [];
}

function normalizeProjectDnaModels(value: unknown): ProjectDnaModelRef[] {
  return Array.isArray(value)
    ? value
        .map((item) => {
          const record = asRecord(item);
          const modelId = stringValue(record.modelId ?? record.id ?? item).trim();
          const label = stringValue(record.label ?? record.name ?? modelId, modelId).trim();
          return modelId ? { modelId, label: label || modelId } : null;
        })
        .filter((item): item is ProjectDnaModelRef => Boolean(item))
    : [];
}

function normalizeProjectDnaTools(value: unknown): ProjectDnaToolRef[] {
  return Array.isArray(value)
    ? value
        .map((item) => {
          const record = asRecord(item);
          const toolId = stringValue(record.toolId ?? record.id ?? item).trim();
          const label = stringValue(record.label ?? record.name ?? toolId, toolId).trim();
          return toolId ? { toolId, label: label || toolId } : null;
        })
        .filter((item): item is ProjectDnaToolRef => Boolean(item))
    : [];
}

function normalizeProjectDnaDecisions(value: unknown): ProjectDnaDecision[] {
  return Array.isArray(value)
    ? value
        .map((item): ProjectDnaDecision | null => {
          const record = asRecord(item);
          const title = stringValue(record.title ?? record.decision ?? item).trim();
          if (!title) return null;
          return {
            decisionKey: maybeString(record.decisionKey ?? record.decision_key) ?? undefined,
            title,
            rationale: maybeString(record.rationale ?? record.reason) ?? undefined,
            status: maybeString(record.status) ?? undefined,
          };
        })
        .filter((item): item is ProjectDnaDecision => Boolean(item))
    : [];
}

function normalizeProjectDnaProfile(value: unknown): ProjectDnaProfile {
  const raw = asRecord(value);
  const completion = asRecord(raw.completion);
  const sectionStates = asRecord(raw.sectionStates);
  return {
    username: maybeString(raw.username),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    projectName: maybeString(raw.projectName ?? raw.project_name),
    objective: maybeString(raw.objective),
    context: maybeString(raw.context),
    responseStyle: maybeString(raw.responseStyle ?? raw.response_style),
    preferredModels: normalizeProjectDnaModels(
      raw.preferredModels ?? raw.preferred_models,
    ),
    allowedTools: normalizeProjectDnaTools(raw.allowedTools ?? raw.allowed_tools),
    constraints: normalizeStringList(raw.constraints),
    decisions: normalizeProjectDnaDecisions(raw.decisions),
    sectionStates: Object.fromEntries(
      Object.entries(sectionStates).map(([key, status]) => [
        key,
        stringValue(status, "missing_optional"),
      ]),
    ),
    completion: {
      readySectionCount: numberValue(completion.readySectionCount, 0),
      totalSectionCount: numberValue(completion.totalSectionCount, 0),
      readySectionIds: normalizeStringList(completion.readySectionIds),
      score: numberValue(completion.score, 0),
    },
    dnaHash: maybeString(raw.dnaHash ?? raw.dna_hash),
  };
}

function normalizeProjectDnaInjectionPlan(value: unknown): ProjectDnaInjectionPlan {
  const raw = asRecord(value);
  return {
    contextInjectorVersion: maybeString(raw.contextInjectorVersion) ?? undefined,
    channelId: maybeString(raw.channelId) ?? undefined,
    status: maybeString(raw.status) ?? undefined,
    includedSectionIds: normalizeStringList(raw.includedSectionIds),
    priority: numberValue(raw.priority, 0),
    maxTokens: numberValue(raw.maxTokens, 0),
    willInjectNow: boolValue(raw.willInjectNow),
    contextManagerCompatible: boolValue(raw.contextManagerCompatible),
    rawHistoryAllowed: boolValue(raw.rawHistoryAllowed),
    reason: maybeString(raw.reason) ?? undefined,
  };
}

function normalizeProjectDnaPlan(value: unknown): ProjectDnaPlan {
  const raw = asRecord(value);
  return {
    projectDnaServiceVersion:
      maybeString(raw.projectDnaServiceVersion) ?? undefined,
    profileBuilderVersion: maybeString(raw.profileBuilderVersion) ?? undefined,
    contextInjectorVersion: maybeString(raw.contextInjectorVersion) ?? undefined,
    mode: maybeString(raw.mode) ?? undefined,
    projectId: maybeString(raw.projectId ?? raw.project_id),
    status: maybeString(raw.status) ?? undefined,
    profile: normalizeProjectDnaProfile(raw.profile),
    contextInjectionPlan: normalizeProjectDnaInjectionPlan(
      raw.contextInjectionPlan,
    ),
    sideEffects: parseRecordJson(raw.sideEffects) ?? {},
  };
}

function normalizeProjectDnaRecord(value: unknown): ProjectDnaRecord {
  const raw = asRecord(value);
  const dna = parseRecordJson(raw.dna ?? raw.dnaJson ?? raw.dna_json);
  const constraints = raw.constraints ?? raw.activeConstraints;
  const decisions = raw.decisions ?? raw.activeDecisions;
  return {
    id: maybeString(raw.id),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    objective: maybeString(raw.objective),
    context: maybeString(raw.context),
    responseStyle: maybeString(raw.responseStyle ?? raw.response_style),
    preferredModels: normalizeProjectDnaModels(
      raw.preferredModels ?? raw.preferred_models,
    ),
    allowedTools: normalizeProjectDnaTools(raw.allowedTools ?? raw.allowed_tools),
    dna: dna ? normalizeProjectDnaPlan(dna) : null,
    dnaHash: maybeString(raw.dnaHash ?? raw.dna_hash),
    status: maybeString(raw.status),
    constraints: normalizeStringList(constraints),
    decisions: normalizeProjectDnaDecisions(decisions),
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeContextHeatmapEntry(value: unknown): ContextHeatmapEntry {
  const raw = asRecord(value);
  const entry = parseRecordJson(raw.entry ?? raw.entryJson) ?? {};
  const merged = { ...entry, ...raw };
  return {
    id: maybeString(raw.id),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    chunkId: stringValue(merged.chunkId ?? merged.chunk_id),
    sourceType: maybeString(merged.sourceType ?? merged.source_type),
    sourceId: maybeString(merged.sourceId ?? merged.source_id),
    title: maybeString(merged.title),
    utilityScore: numberValue(merged.utilityScore ?? merged.utility_score, 0),
    usageCount: numberValue(merged.usageCount ?? merged.usage_count, 0),
    responseCount: numberValue(merged.responseCount ?? merged.response_count, 0),
    citationCount: numberValue(merged.citationCount ?? merged.citation_count, 0),
    copiedTermCount: numberValue(
      merged.copiedTermCount ?? merged.copied_term_count,
      0,
    ),
    ageDays: numberValue(merged.ageDays ?? merged.age_days, 0),
    bucket: maybeString(merged.bucket) ?? "low_usage",
    label: maybeString(merged.label),
    recommendedAction: maybeString(
      merged.recommendedAction ?? merged.recommended_action,
    ) ?? "review",
    themeToken: maybeString(merged.themeToken ?? merged.theme_token),
    matchedObjectiveTerms: Array.isArray(merged.matchedObjectiveTerms)
      ? merged.matchedObjectiveTerms.map((item) => stringValue(item)).filter(Boolean)
      : [],
    signals: parseRecordJson(merged.signals) ?? {},
    entry,
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeContextUsageStat(value: unknown): ContextUsageStat {
  const raw = asRecord(value);
  return {
    id: maybeString(raw.id),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    chunkId: stringValue(raw.chunkId ?? raw.chunk_id),
    sourceType: maybeString(raw.sourceType ?? raw.source_type),
    sourceId: maybeString(raw.sourceId ?? raw.source_id),
    usageCount: numberValue(raw.usageCount ?? raw.usage_count, 0),
    responseCount: numberValue(raw.responseCount ?? raw.response_count, 0),
    citationCount: numberValue(raw.citationCount ?? raw.citation_count, 0),
    utilityScore: numberValue(raw.utilityScore ?? raw.utility_score, 0),
    metadata: parseRecordJson(raw.metadata ?? raw.metadataJson) ?? {},
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeContextHeatmapPlan(value: unknown): ContextHeatmapPlan {
  const raw = asRecord(value);
  const summary = asRecord(raw.summary);
  const bucketCounts = asRecord(summary.bucketCounts);
  const garbageCollectorPlan = asRecord(raw.garbageCollectorPlan);
  return {
    usageTrackerVersion: maybeString(raw.usageTrackerVersion) ?? undefined,
    heatmapGeneratorVersion: maybeString(raw.heatmapGeneratorVersion) ?? undefined,
    memoryGarbageCollectorVersion:
      maybeString(raw.memoryGarbageCollectorVersion) ?? undefined,
    mode: maybeString(raw.mode) ?? undefined,
    projectId: maybeString(raw.projectId ?? raw.project_id),
    objective: maybeString(raw.objective),
    entries: Array.isArray(raw.entries)
      ? raw.entries.map(normalizeContextHeatmapEntry)
      : [],
    summary: {
      chunkCount: numberValue(summary.chunkCount, 0),
      bucketCounts: Object.fromEntries(
        Object.entries(bucketCounts).map(([key, count]) => [
          key,
          numberValue(count, 0),
        ]),
      ),
      averageUtilityScore: numberValue(summary.averageUtilityScore, 0),
      archiveCandidateCount: numberValue(summary.archiveCandidateCount, 0),
      automaticArchiveWillRun: boolValue(summary.automaticArchiveWillRun),
    },
    garbageCollectorPlan: {
      candidateChunkIds: Array.isArray(garbageCollectorPlan.candidateChunkIds)
        ? garbageCollectorPlan.candidateChunkIds
            .map((item) => stringValue(item))
            .filter(Boolean)
        : [],
      recommendedAction:
        maybeString(garbageCollectorPlan.recommendedAction) ?? undefined,
      automaticArchiveAllowed: boolValue(
        garbageCollectorPlan.automaticArchiveAllowed,
      ),
      automaticDeleteAllowed: boolValue(
        garbageCollectorPlan.automaticDeleteAllowed,
      ),
      requiresHumanConfirmation: boolValue(
        garbageCollectorPlan.requiresHumanConfirmation,
      ),
    },
    display: parseRecordJson(raw.display) ?? {},
    sideEffects: parseRecordJson(raw.sideEffects) ?? {},
  };
}

export async function getProjectDna(
  projectId: string,
): Promise<ProjectDnaRecord | null> {
  const response = await authFetch(
    `/api/cognix/projects/${encodeURIComponent(projectId)}/dna`,
  );
  const body = await parseJsonOrThrow<{
    projectDna?: unknown;
  }>(response);
  return body.projectDna ? normalizeProjectDnaRecord(body.projectDna) : null;
}

export async function upsertProjectDna(
  payload: ProjectDnaPayload,
): Promise<ProjectDnaResult> {
  const response = await authFetch(
    `/api/cognix/projects/${encodeURIComponent(payload.projectId)}/dna`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        objective: payload.objective ?? null,
        context: payload.context ?? null,
        responseStyle: payload.responseStyle ?? null,
        preferredModels: payload.preferredModels ?? [],
        allowedTools: payload.allowedTools ?? [],
        constraints: payload.constraints ?? [],
        decisions: payload.decisions ?? [],
        storeDna: payload.storeDna ?? true,
      }),
    },
  );
  const body = await parseJsonOrThrow<{
    projectDnaPlan?: unknown;
    projectDna?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    projectDnaPlan: normalizeProjectDnaPlan(body.projectDnaPlan),
    projectDna: body.projectDna
      ? normalizeProjectDnaRecord(body.projectDna)
      : null,
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function createProjectDnaInjectionPlan(
  payload: ProjectDnaPayload,
): Promise<ProjectDnaResult> {
  const response = await authFetch(
    `/api/cognix/projects/${encodeURIComponent(payload.projectId)}/dna/injection-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        objective: payload.objective ?? null,
        context: payload.context ?? null,
        responseStyle: payload.responseStyle ?? null,
        preferredModels: payload.preferredModels ?? [],
        allowedTools: payload.allowedTools ?? [],
        constraints: payload.constraints ?? [],
        decisions: payload.decisions ?? [],
        storeDna: false,
      }),
    },
  );
  const body = await parseJsonOrThrow<{
    projectDnaPlan?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    projectDnaPlan: normalizeProjectDnaPlan(body.projectDnaPlan),
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function createContextHeatmapPlan(payload: {
  contextChunks: Array<Record<string, unknown>>;
  responseUsage?: Array<Record<string, unknown>>;
  objective?: string | null;
  projectId?: string | null;
  storeHeatmap?: boolean;
}): Promise<ContextHeatmapPlanResult> {
  const response = await authFetch("/api/cognix/context/heatmap/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contextChunks: payload.contextChunks,
      responseUsage: payload.responseUsage ?? [],
      objective: payload.objective ?? null,
      projectId: payload.projectId ?? null,
      storeHeatmap: payload.storeHeatmap ?? true,
    }),
  });
  const body = await parseJsonOrThrow<{
    contextHeatmapPlan?: unknown;
    storedHeatmapEntries?: unknown[];
    storedUsageStats?: unknown[];
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    contextHeatmapPlan: normalizeContextHeatmapPlan(body.contextHeatmapPlan),
    storedHeatmapEntries: (body.storedHeatmapEntries ?? []).map(
      normalizeContextHeatmapEntry,
    ),
    storedUsageStats: (body.storedUsageStats ?? []).map(normalizeContextUsageStat),
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function listContextHeatmapEntries(payload?: {
  projectId?: string | null;
}): Promise<{
  entries: ContextHeatmapEntry[];
  usageStats: ContextUsageStat[];
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}> {
  const params = new URLSearchParams();
  if (payload?.projectId) params.set("project_id", payload.projectId);
  const query = params.toString();
  const response = await authFetch(
    `/api/cognix/context/heatmap/entries${query ? `?${query}` : ""}`,
  );
  const body = await parseJsonOrThrow<{
    entries?: unknown[];
    usageStats?: unknown[];
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    entries: (body.entries ?? []).map(normalizeContextHeatmapEntry),
    usageStats: (body.usageStats ?? []).map(normalizeContextUsageStat),
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function planCogniXExecution(payload: {
  objective: string;
  projectType?: string | null;
  projectId?: string | null;
}): Promise<CogniXExecutionPlan> {
  const response = await authFetch("/api/cognix/orchestrator/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objective: payload.objective,
      project_type: payload.projectType ?? null,
      project_id: payload.projectId ?? null,
    }),
  });
  return parseJsonOrThrow(response);
}

export async function explainCogniXDecision(payload: {
  sourceType?: "orchestrator_log" | "router_log" | "manual";
  sourceId?: string | null;
  projectId?: string | null;
  question?: string | null;
  decision?: Record<string, unknown> | null;
  storeDecision?: boolean;
}): Promise<CogniXDecisionExplainResult> {
  const response = await authFetch("/api/cognix/decisions/explain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sourceType: payload.sourceType ?? "manual",
      sourceId: payload.sourceId ?? null,
      projectId: payload.projectId ?? null,
      question: payload.question ?? null,
      decision: payload.decision ?? null,
      storeDecision: payload.storeDecision ?? true,
    }),
  });
  return parseJsonOrThrow<CogniXDecisionExplainResult>(response);
}

export async function loadModel(
  payload: LoadModelRequest,
): Promise<LoadModelResponse> {
  const response = await authFetch("/api/inference/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      native_path_lease: payload.nativePathLease ?? null,
      nativePathLease: undefined,
    }),
  });
  return parseJsonOrThrow<LoadModelResponse>(response);
}

export async function validateModel(
  payload: LoadModelRequest,
): Promise<ValidateModelResponse> {
  const response = await authFetch("/api/inference/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_path: payload.model_path,
      native_path_lease: payload.nativePathLease ?? null,
      hf_token: payload.hf_token,
      gguf_variant: payload.gguf_variant ?? null,
      // Send the intended load settings so validate's VRAM check matches the
      // follow-up /load and doesn't unload for a load /load would then reject.
      max_seq_length: payload.max_seq_length,
      load_in_4bit: payload.load_in_4bit,
    }),
  });
  return parseJsonOrThrow<ValidateModelResponse>(response);
}

/**
 * Read a GGUF's native context length from its local header (no GPU load, no
 * download). Returns null when the file isn't downloaded yet, the model isn't a
 * GGUF, or it's gated. For a native (drag-drop / picked) file, pass
 * `nativePathToken` so the backend reads the granted local path. Used by the
 * deferred-load staging flow to fill the context slider before the single load.
 */
export async function fetchGgufContextLength(payload: {
  model_path: string;
  gguf_variant?: string | null;
  hf_token?: string | null;
  nativePathToken?: string | null;
}): Promise<number | null> {
  let nativePathLease: string | null = null;
  if (payload.nativePathToken) {
    try {
      nativePathLease = (
        await consumeNativePathToken(payload.nativePathToken, "validate-model")
      ).nativePathLease;
    } catch {
      // Lease expired / revoked: degrade to no context (the load can re-mint).
      return null;
    }
  }
  const response = await authFetch("/api/inference/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_path: payload.model_path,
      gguf_variant: payload.gguf_variant ?? null,
      hf_token: payload.hf_token ?? null,
      native_path_lease: nativePathLease,
      include_context_length: true,
    }),
  });
  const res = await parseJsonOrThrow<ValidateModelResponse>(response);
  return res.context_length ?? null;
}

export async function unloadModel(payload: UnloadModelRequest): Promise<void> {
  const response = await authFetch("/api/inference/unload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await parseJsonOrThrow<unknown>(response);
}

/**
 * Allow or deny a tool call that is paused awaiting user confirmation
 * (when the "Confirm tool calls" toggle is on). The call is identified by
 * the backend ``approvalId`` echoed in the tool_start event; ``sessionId``
 * is a scope check. Resolves to ``true`` only when the backend matched a
 * pending call, so the caller can surface a retry on a stale/failed post.
 */
export async function resolveToolConfirmation(
  sessionId: string,
  approvalId: string,
  decision: "allow" | "deny",
): Promise<boolean> {
  const response = await authFetch("/api/inference/tool-confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      approval_id: approvalId,
      decision,
    }),
  });
  const parsed = await parseJsonOrThrow<{ resolved?: boolean }>(response);
  return parsed.resolved === true;
}

export interface CachedGgufRepo {
  repo_id: string;
  size_bytes: number;
  cache_path: string;
  /** Epoch seconds of the newest downloaded quant; sorts Downloaded
   * newest-first. Optional for older-backend compatibility. */
  last_modified?: number;
  /** True when the repo ships an mmproj adapter (image inputs). Optional for
   * older-backend compatibility. */
  has_vision?: boolean;
}

export async function getGgufDownloadProgress(
  repoId: string,
  variant: string,
  expectedBytes: number,
): Promise<{
  downloaded_bytes: number;
  expected_bytes: number;
  progress: number;
}> {
  const params = new URLSearchParams({
    repo_id: repoId,
    variant,
    expected_bytes: String(expectedBytes),
  });
  const response = await authFetch(
    `/api/models/gguf-download-progress?${params}`,
  );
  return parseJsonOrThrow(response);
}

export interface DownloadProgressResponse {
  downloaded_bytes: number;
  expected_bytes: number;
  progress: number;
  /**
   * On-disk path of the snapshot dir (or cache repo root if no snapshot yet).
   * Null when nothing has been written to the cache for this repo.
   */
  cache_path: string | null;
}

export interface ProjectDefaultModel {
  projectId: string;
  ownerUsername?: string;
  modelId: string;
  label: string;
  providerType?: string | null;
  providerId?: string | null;
  createdAt: number;
  updatedAt: number;
}

export interface ResponseReflectionConfidence {
  score?: number;
  label?: "high" | "medium" | "low" | string;
  verificationRequired?: boolean;
  recommendedAction?: string;
}

export interface ResponseReflectionIssue {
  id?: string;
  severity?: string;
  label?: string;
  detail?: string;
  evidence?: Record<string, unknown>;
}

export interface ResponseReflectionEvaluation {
  reflectionVersion?: string;
  mode?: string;
  taskType?: string;
  modelId?: string | null;
  confidence?: ResponseReflectionConfidence;
  issues?: ResponseReflectionIssue[];
  sideEffects?: Record<string, unknown>;
}

export interface ResponseReflectionResult {
  username: string;
  responseReflection: ResponseReflectionEvaluation;
  record?: Record<string, unknown> | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface ResponseReflectionRecord {
  id: string;
  messageId?: string | null;
  threadId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  confidenceScore?: number | null;
  confidenceLabel?: string | null;
  verificationRequired?: boolean | number | null;
  recommendedAction?: string | null;
  issues?: ResponseReflectionIssue[];
  evaluation?: ResponseReflectionEvaluation;
  createdAt?: string | null;
}

export async function evaluateResponseReflection(payload: {
  prompt: string;
  response: string;
  messageId?: string | null;
  threadId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  taskType?: string | null;
  requiresSources?: boolean;
  responseSources?: Array<Record<string, unknown>>;
}): Promise<ResponseReflectionResult> {
  const response = await authFetch("/api/cognix/reflection/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<ResponseReflectionResult>(response);
}

export async function listResponseReflectionEvaluations(
  messageId?: string | null,
): Promise<ResponseReflectionRecord[]> {
  const query = messageId
    ? `?${new URLSearchParams({ message_id: messageId }).toString()}`
    : "";
  const response = await authFetch(`/api/cognix/reflection/evaluations${query}`);
  const body = await parseJsonOrThrow<{
    evaluations?: ResponseReflectionRecord[];
  }>(response);
  return body.evaluations ?? [];
}

export interface DraftStyleProfile {
  id: string;
  label: string;
  tone?: string;
  targetLength?: string;
  bestFor?: string[];
  instruction?: string;
}

export interface DraftPlanVariant {
  id: string;
  variantType: string;
  label: string;
  status?: string;
  styleProfile?: DraftStyleProfile;
  promptInstruction?: string;
  requiresBackendGeneration?: boolean;
  willGenerateNow?: boolean;
  willStoreVariant?: boolean;
}

export interface DraftGenerationPlan {
  draftGenerationVersion?: string;
  styleProfileRegistryVersion?: string;
  mode?: string;
  messageId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  taskType?: string;
  selectedVariantTypes?: string[];
  variants?: DraftPlanVariant[];
  rankingPlan?: Record<string, unknown>;
  costPlan?: {
    estimatedGenerationCount?: number;
    requiresExplicitUserAction?: boolean;
    defaultSingleDraftStillAllowed?: boolean;
  };
  policies?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface DraftGenerationPlanResult {
  username: string;
  draftGenerationPlan: DraftGenerationPlan;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export interface ResponseVariantRecord {
  id: string;
  messageId?: string | null;
  threadId?: string | null;
  projectId?: string | null;
  variantType?: string | null;
  title?: string | null;
  content?: string | null;
  modelId?: string | null;
  rankingScore?: number | null;
  metadata?: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export async function createDraftGenerationPlan(payload: {
  prompt: string;
  requestedVariants?: string[] | null;
  maxVariants?: number;
  taskType?: string | null;
  includeRanking?: boolean;
  messageId?: string | null;
  threadId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
}): Promise<DraftGenerationPlanResult> {
  const response = await authFetch("/api/cognix/drafts/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<DraftGenerationPlanResult>(response);
}

export async function listResponseVariants(
  messageId?: string | null,
): Promise<ResponseVariantRecord[]> {
  const query = messageId
    ? `?${new URLSearchParams({ message_id: messageId }).toString()}`
    : "";
  const response = await authFetch(`/api/cognix/drafts/variants${query}`);
  const body = await parseJsonOrThrow<{
    variants?: ResponseVariantRecord[];
  }>(response);
  return body.variants ?? [];
}

export interface DebateRoleProfile {
  id: string;
  label: string;
  displayRole?: string;
  purpose?: string;
  visibility?: string;
}

export interface DebatePlanRound {
  id: string;
  roundIndex?: number;
  roleId: string;
  label: string;
  purpose?: string;
  publicPrompt?: string;
  status?: string;
  requiresBackendGeneration?: boolean;
  willGenerateNow?: boolean;
}

export interface DebatePlan {
  debateOrchestratorVersion?: string;
  debateRoleRegistryVersion?: string;
  mode?: string;
  messageId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  taskType?: string;
  objectiveExcerpt?: string;
  roles?: DebateRoleProfile[];
  rounds?: DebatePlanRound[];
  summary?: {
    roleCount?: number;
    plannedRoundCount?: number;
    maxRounds?: number;
    finalRoundId?: string;
  };
  displayContract?: Record<string, unknown>;
  policies?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface DebateSessionRoundRecord extends DebatePlanRound {
  sessionId?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface DebateOutputRecord {
  id: string;
  sessionId?: string | null;
  roundId?: string | null;
  roleId?: string | null;
  outputType?: "argument" | "critique" | "reply" | "synthesis" | "note" | string;
  publicSummary?: string | null;
  content?: string | null;
  modelId?: string | null;
  metadata?: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface DebateSessionRecord {
  id: string;
  messageId?: string | null;
  threadId?: string | null;
  projectId?: string | null;
  prompt?: string | null;
  plan?: DebatePlan | null;
  rounds?: DebateSessionRoundRecord[];
  outputs?: DebateOutputRecord[];
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface DebatePlanResult {
  username: string;
  debatePlan: DebatePlan;
  session?: DebateSessionRecord | null;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
  plannerVersion?: string;
}

export async function createDebatePlan(payload: {
  prompt: string;
  requestedRoles?: string[] | null;
  maxRounds?: number;
  taskType?: string | null;
  messageId?: string | null;
  threadId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  createSession?: boolean;
}): Promise<DebatePlanResult> {
  const response = await authFetch("/api/cognix/debate/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<DebatePlanResult>(response);
}

export async function listDebateSessions(
  messageId?: string | null,
): Promise<DebateSessionRecord[]> {
  const query = messageId
    ? `?${new URLSearchParams({ message_id: messageId }).toString()}`
    : "";
  const response = await authFetch(`/api/cognix/debate/sessions${query}`);
  const body = await parseJsonOrThrow<{
    sessions?: DebateSessionRecord[];
  }>(response);
  return body.sessions ?? [];
}

export interface ToolDiscoveryNeed {
  needId?: string;
  label?: string;
  description?: string;
  confidence?: number;
  toolIds?: string[];
}

export interface ToolDiscoveryRecommendation {
  id?: string;
  toolId?: string;
  toolName?: string;
  category?: string;
  needId?: string;
  needs?: ToolDiscoveryNeed[];
  reason?: string;
  confidence?: number;
  status?: string;
  capabilities?: string[];
  installHint?: string | null;
  connectorBacked?: boolean;
  actions?: {
    primary?: string;
    ignoreAllowed?: boolean;
    automaticInstallAllowed?: boolean;
    requiresHumanConfirmation?: boolean;
  };
  guardrails?: Record<string, unknown>;
}

export interface ToolDiscoveryPlan {
  toolDiscoveryVersion?: string;
  capabilityRegistryVersion?: string;
  mode?: string;
  projectId?: string | null;
  projectType?: string | null;
  projectName?: string | null;
  objectiveExcerpt?: string;
  needs?: ToolDiscoveryNeed[];
  recommendations?: ToolDiscoveryRecommendation[];
  summary?: {
    needCount?: number;
    recommendationCount?: number;
    installedMatchCount?: number;
    connectorDisabledCount?: number;
    automaticInstallAllowed?: boolean;
  };
  policies?: Record<string, unknown>;
  sideEffects?: Record<string, unknown>;
}

export interface StoredToolRecommendationRecord {
  id: string;
  projectId?: string | null;
  needId?: string | null;
  toolId?: string | null;
  toolName?: string | null;
  category?: string | null;
  reason?: string | null;
  status?: string | null;
  confidence?: number | null;
  ignored?: boolean;
  recommendation?: ToolDiscoveryRecommendation;
  recommendationJson?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ToolDiscoveryAnalyzeResult {
  username: string;
  toolDiscoveryPlan: ToolDiscoveryPlan;
  storedRecommendations?: StoredToolRecommendationRecord[];
  installedTools?: Array<Record<string, unknown>>;
  auditLogId?: string | null;
  sideEffects?: Record<string, unknown>;
}

export async function analyzeToolDiscovery(payload: {
  objective?: string | null;
  projectId?: string | null;
  projectType?: string | null;
  projectName?: string | null;
  fileNames?: string[] | null;
  documents?: Array<Record<string, unknown>> | null;
  tags?: string[] | null;
  installedToolIds?: string[] | null;
  storeRecommendations?: boolean;
  recordInstalledSnapshot?: boolean;
}): Promise<ToolDiscoveryAnalyzeResult> {
  const response = await authFetch("/api/cognix/tools/discovery/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<ToolDiscoveryAnalyzeResult>(response);
}

export async function listToolRecommendations(payload?: {
  projectId?: string | null;
  includeIgnored?: boolean;
}): Promise<StoredToolRecommendationRecord[]> {
  const params = new URLSearchParams();
  if (payload?.projectId) params.set("project_id", payload.projectId);
  if (payload?.includeIgnored) params.set("include_ignored", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await authFetch(`/api/cognix/tools/recommendations${query}`);
  const body = await parseJsonOrThrow<{
    recommendations?: StoredToolRecommendationRecord[];
  }>(response);
  return body.recommendations ?? [];
}

export interface ProjectSkillRecord {
  id: string;
  skillId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  displayName?: string | null;
  objective?: string | null;
  effectiveAllowedTools?: string[];
}

export interface ProjectDirectiveRecord {
  id: string;
  directiveId?: string | null;
  projectId?: string | null;
  modelId?: string | null;
  directiveType?: string | null;
  content?: string | null;
  priority?: number | null;
}

export async function createProjectSkill(payload: {
  projectId: string;
  displayName: string;
  objective?: string | null;
  instructions?: string | null;
  modelId?: string | null;
  allowedTools?: string[];
}): Promise<ProjectSkillRecord | null> {
  const response = await authFetch(
    `/api/cognix/projects/${encodeURIComponent(payload.projectId)}/skills`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        displayName: payload.displayName,
        objective: payload.objective ?? null,
        instructions: payload.instructions ?? null,
        modelId: payload.modelId ?? null,
        allowedTools: payload.allowedTools ?? [],
      }),
    },
  );
  const body = await parseJsonOrThrow<{
    projectSkill: ProjectSkillRecord | null;
  }>(response);
  return body.projectSkill;
}

export async function createProjectDirective(payload: {
  projectId: string;
  content: string;
  directiveType?: string | null;
  priority?: number;
  modelId?: string | null;
}): Promise<ProjectDirectiveRecord | null> {
  const response = await authFetch(
    `/api/cognix/projects/${encodeURIComponent(payload.projectId)}/directives`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: payload.content,
        directiveType: payload.directiveType ?? "style",
        priority: payload.priority ?? 50,
        modelId: payload.modelId ?? null,
      }),
    },
  );
  const body = await parseJsonOrThrow<{
    projectDirective: ProjectDirectiveRecord | null;
  }>(response);
  return body.projectDirective;
}

export async function getProjectDefaultModel(
  projectId: string,
): Promise<ProjectDefaultModel | null> {
  const response = await authFetch(
    `/api/cognix/projects/${encodeURIComponent(projectId)}/default-model`,
  );
  const body = await parseJsonOrThrow<{
    defaultModel: ProjectDefaultModel | null;
  }>(response);
  return body.defaultModel;
}

export async function getDownloadProgress(
  repoId: string,
): Promise<DownloadProgressResponse> {
  const params = new URLSearchParams({ repo_id: repoId });
  const response = await authFetch(`/api/models/download-progress?${params}`);
  return parseJsonOrThrow(response);
}

export async function getDatasetDownloadProgress(
  repoId: string,
): Promise<DownloadProgressResponse> {
  const params = new URLSearchParams({ repo_id: repoId });
  const response = await authFetch(`/api/datasets/download-progress?${params}`);
  return parseJsonOrThrow(response);
}

export type ModelLoadPhase = "mmap" | "ready" | null;

export interface LoadProgressResponse {
  /**
   * Load phase: "mmap" while llama-server pages weight shards into RAM,
   * "ready" once healthy, or null when no load is in flight.
   */
  phase: ModelLoadPhase;
  bytes_loaded: number;
  bytes_total: number;
  fraction: number;
}

/**
 * Fetch the active GGUF load's mmap/upload progress. Complements the download
 * progress endpoints for the "download complete" -> "chat ready" window, which
 * for large MoE models can be several minutes of otherwise-opaque spinning.
 */
export async function getLoadProgress(): Promise<LoadProgressResponse> {
  const response = await authFetch(`/api/inference/load-progress`);
  return parseJsonOrThrow(response);
}

export interface LocalModelInfo {
  id: string;
  display_name: string;
  path: string;
  source: "models_dir" | "hf_cache" | "lmstudio" | "custom";
  model_id?: string | null;
  // Backend-detected weights format ("gguf" when known), so the UI can
  // classify scanned folders whose name lacks a -GGUF suffix.
  model_format?: string | null;
  updated_at?: number | null;
}

interface LocalModelListResponse {
  models_dir: string;
  hf_cache_dir?: string | null;
  lmstudio_dirs: string[];
  models: LocalModelInfo[];
}

export async function listLocalModels(): Promise<LocalModelListResponse> {
  const response = await authFetch("/api/models/local");
  return parseJsonOrThrow<LocalModelListResponse>(response);
}

export async function listCachedGguf(): Promise<CachedGgufRepo[]> {
  const response = await authFetch("/api/models/cached-gguf");
  const data = await parseJsonOrThrow<{ cached: CachedGgufRepo[] }>(response);
  return data.cached;
}

export interface CachedModelRepo {
  repo_id: string;
  size_bytes: number;
  /** Epoch seconds of the newest downloaded weight file; sorts Downloaded
   * newest-first. Optional for older-backend compatibility. */
  last_modified?: number;
}

export async function listCachedModels(): Promise<CachedModelRepo[]> {
  const response = await authFetch("/api/models/cached-models");
  const data = await parseJsonOrThrow<{ cached: CachedModelRepo[] }>(response);
  return data.cached;
}

export async function deleteCachedModel(
  repoId: string,
  variant?: string,
): Promise<void> {
  const payload: Record<string, string> = { repo_id: repoId };
  if (variant) payload.variant = variant;
  const response = await authFetch("/api/models/delete-cached", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await parseJsonOrThrow<unknown>(response);
}

export async function deleteFineTunedModel(args: {
  modelPath: string;
  source: "training" | "exported";
  exportType?: "lora" | "merged" | "gguf";
  ggufVariant?: string;
}): Promise<void> {
  const response = await authFetch("/api/models/delete-finetuned", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_path: args.modelPath,
      source: args.source,
      export_type: args.exportType ?? null,
      gguf_variant: args.ggufVariant ?? null,
    }),
  });
  await parseJsonOrThrow<unknown>(response);
}

export interface ScanFolderInfo {
  id: number;
  path: string;
  created_at: string;
}

export async function listScanFolders(): Promise<ScanFolderInfo[]> {
  const response = await authFetch("/api/models/scan-folders");
  const data = await parseJsonOrThrow<{ folders: ScanFolderInfo[] }>(response);
  return data.folders;
}

export async function addScanFolder(path: string): Promise<ScanFolderInfo> {
  const response = await authFetch("/api/models/scan-folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  return parseJsonOrThrow<ScanFolderInfo>(response);
}

export async function removeScanFolder(id: number): Promise<void> {
  const response = await authFetch(`/api/models/scan-folders/${id}`, {
    method: "DELETE",
  });
  await parseJsonOrThrow<unknown>(response);
}

export async function listChatThreads(
  args: {
    modelType?: ModelType;
    pairId?: string;
    projectId?: string | null;
    includeArchived?: boolean;
  } = {},
): Promise<ThreadRecord[]> {
  const params = new URLSearchParams();
  if (args.modelType) params.set("model_type", args.modelType);
  if (args.pairId) params.set("pair_id", args.pairId);
  if (args.projectId) params.set("project_id", args.projectId);
  if (args.includeArchived !== undefined) {
    params.set("include_archived", String(args.includeArchived));
  }
  const qs = params.toString();
  const response = await authFetch(`/api/chat/threads${qs ? `?${qs}` : ""}`);
  const data = await parseJsonOrThrow<{ threads: ThreadRecord[] }>(response);
  // Always hand back an array: an older or misbehaving backend may omit the
  // field or send a non-array, which would crash list consumers.
  return Array.isArray(data.threads) ? data.threads : [];
}

export async function getChatThread(
  threadId: string,
): Promise<ThreadRecord | null> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}`,
  );
  if (response.status === 404) return null;
  return parseJsonOrThrow<ThreadRecord>(response);
}

export async function saveChatThread(
  thread: ThreadRecord,
): Promise<ThreadRecord> {
  const response = await authFetch("/api/chat/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(thread),
  });
  const savedThread = await parseJsonOrThrow<ThreadRecord>(response);
  notifyChatHistoryUpdated();
  return savedThread;
}

export async function updateChatThread(
  threadId: string,
  patch: Partial<ThreadRecord>,
): Promise<ThreadRecord> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  const thread = await parseJsonOrThrow<ThreadRecord>(response);
  notifyChatHistoryUpdated();
  return thread;
}

export interface ForkChatThreadResult {
  thread: ThreadRecord;
  messages: MessageRecord[];
  containerSnapshotWarning: string | null;
}

export async function forkChatThread(
  threadId: string,
  args: { messageId: string; newThreadId: string; createdAt: number },
): Promise<ForkChatThreadResult> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}/fork`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    },
  );
  const data = await parseJsonOrThrow<{
    thread: ThreadRecord;
    messages: MessageRecord[];
    containerSnapshotWarning: string | null;
  }>(response);
  notifyChatHistoryUpdated();
  return data;
}

export async function getForkCount(
  threadId: string,
  messageId: string,
): Promise<number> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}/forks`,
  );
  if (response.status === 404) return 0;
  const data = await parseJsonOrThrow<{ count: number }>(response);
  return data.count;
}

export async function deleteChatThreads(threadIds: string[]): Promise<void> {
  if (threadIds.length === 0) return;
  const response = await authFetch("/api/chat/threads", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: threadIds }),
  });
  await parseJsonOrThrow<unknown>(response);
  notifyChatHistoryUpdated();
}

export async function listChatProjects(
  args: { includeArchived?: boolean } = {},
): Promise<ProjectRecord[]> {
  const params = new URLSearchParams();
  if (args.includeArchived !== undefined) {
    params.set("include_archived", String(args.includeArchived));
  }
  const qs = params.toString();
  const response = await authFetch(`/api/chat/projects${qs ? `?${qs}` : ""}`);
  const data = await parseJsonOrThrow<{ projects: ProjectRecord[] }>(response);
  // Always hand back an array: an older or misbehaving backend may omit the
  // field or send a non-array, which would crash list consumers.
  return Array.isArray(data.projects) ? data.projects : [];
}

export async function getChatProject(
  projectId: string,
): Promise<ProjectRecord | null> {
  const response = await authFetch(
    `/api/chat/projects/${encodeURIComponent(projectId)}`,
  );
  if (response.status === 404) return null;
  return parseJsonOrThrow<ProjectRecord>(response);
}

export async function saveChatProject(
  project: ProjectRecord,
): Promise<ProjectRecord> {
  const response = await authFetch("/api/chat/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
  const saved = await parseJsonOrThrow<ProjectRecord>(response);
  notifyChatHistoryUpdated();
  return saved;
}

export async function updateChatProject(
  projectId: string,
  patch: Partial<ProjectRecord>,
): Promise<ProjectRecord> {
  const response = await authFetch(
    `/api/chat/projects/${encodeURIComponent(projectId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  const project = await parseJsonOrThrow<ProjectRecord>(response);
  notifyChatHistoryUpdated();
  return project;
}

export async function deleteChatProject(
  projectId: string,
  args: { deleteFiles?: boolean } = {},
): Promise<void> {
  const params = new URLSearchParams();
  if (args.deleteFiles) params.set("delete_files", "true");
  const qs = params.toString();
  const response = await authFetch(
    `/api/chat/projects/${encodeURIComponent(projectId)}${qs ? `?${qs}` : ""}`,
    { method: "DELETE" },
  );
  await parseJsonOrThrow<ProjectRecord>(response);
  notifyChatHistoryUpdated();
}

export interface ChatProjectBridgeLink {
  id: string;
  projectId: string;
  threadId: string;
  linkType: "conversation" | "answer_share" | "approval_context";
  source: string;
  status: string;
  metadata?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export interface MessageTaskRecord {
  id: string;
  projectId: string;
  threadId?: string | null;
  messageId?: string | null;
  title: string;
  sourceText: string;
  status: "open" | "in_progress" | "done" | "blocked";
  priority: "low" | "medium" | "high" | "critical";
  approvalRequestId?: string | null;
  metadata?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export interface ChatProjectBridgeResponse {
  links: ChatProjectBridgeLink[];
  tasks: MessageTaskRecord[];
  summary: {
    linkCount: number;
    taskCount: number;
    openTaskCount: number;
  };
}

export async function getChatProjectBridge(
  args: {
    projectId?: string;
    threadId?: string;
  } = {},
): Promise<ChatProjectBridgeResponse> {
  const params = new URLSearchParams();
  if (args.projectId) params.set("project_id", args.projectId);
  if (args.threadId) params.set("thread_id", args.threadId);
  const qs = params.toString();
  const response = await authFetch(
    `/api/cognix/chat-project-bridge${qs ? `?${qs}` : ""}`,
  );
  const data = await parseJsonOrThrow<ChatProjectBridgeResponse>(response);
  return {
    links: Array.isArray(data.links) ? data.links : [],
    tasks: Array.isArray(data.tasks) ? data.tasks : [],
    summary: {
      linkCount: Number(data.summary?.linkCount ?? 0),
      taskCount: Number(data.summary?.taskCount ?? 0),
      openTaskCount: Number(data.summary?.openTaskCount ?? 0),
    },
  };
}

export async function createChatProjectBridgeLink(payload: {
  projectId: string;
  threadId: string;
  linkType?: "conversation" | "answer_share" | "approval_context";
  source?: "chat" | "project" | "manual";
  metadata?: Record<string, unknown>;
}): Promise<ChatProjectBridgeLink> {
  const response = await authFetch("/api/cognix/chat-project-bridge/links", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, storeLink: true }),
  });
  const data = await parseJsonOrThrow<{ link: ChatProjectBridgeLink }>(
    response,
  );
  return data.link;
}

export async function createMessageTask(payload: {
  projectId: string;
  threadId?: string | null;
  messageId?: string | null;
  title?: string | null;
  sourceText: string;
  priority?: "low" | "medium" | "high" | "critical";
  status?: "open" | "in_progress" | "done" | "blocked";
  requireApproval?: boolean;
  metadata?: Record<string, unknown>;
}): Promise<MessageTaskRecord> {
  const response = await authFetch(
    "/api/cognix/chat-project-bridge/message-tasks",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, storeTask: true }),
    },
  );
  const data = await parseJsonOrThrow<{ task: MessageTaskRecord }>(response);
  return data.task;
}

export async function listChatMessages(
  threadId: string,
): Promise<MessageRecord[]> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}/messages`,
  );
  if (response.status === 404) return [];
  const data = await parseJsonOrThrow<{ messages: MessageRecord[] }>(response);
  return data.messages;
}

/**
 * Fetch messages for many threads in one HTTP call. Falls back to
 * per-thread listChatMessages on 404/405 (older servers without the
 * batch route).
 */
export async function batchListChatMessages(
  threadIds: string[],
): Promise<Map<string, MessageRecord[]>> {
  const out = new Map<string, MessageRecord[]>();
  if (threadIds.length === 0) return out;
  const response = await authFetch("/api/chat/messages:batch", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ threadIds }),
  });
  if (response.status === 404 || response.status === 405) {
    // Older server: fall back to per-thread fetches.
    const per = await Promise.all(
      threadIds.map(async (id) => [id, await listChatMessages(id)] as const),
    );
    for (const [id, msgs] of per) out.set(id, msgs);
    return out;
  }
  const data = await parseJsonOrThrow<{
    messagesByThreadId: Record<string, MessageRecord[]>;
  }>(response);
  for (const id of threadIds) {
    out.set(id, data.messagesByThreadId[id] ?? []);
  }
  return out;
}

export async function getChatMessage(
  threadId: string,
  messageId: string,
): Promise<MessageRecord | null> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}`,
  );
  if (response.status === 404) return null;
  return parseJsonOrThrow<MessageRecord>(response);
}

export async function saveChatMessage(
  message: MessageRecord,
): Promise<MessageRecord> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(message.threadId)}/messages/${encodeURIComponent(message.id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message),
    },
  );
  const savedMessage = await parseJsonOrThrow<MessageRecord>(response);
  notifyChatHistoryUpdated();
  return savedMessage;
}

export async function syncChatMessages(
  threadId: string,
  messages: MessageRecord[],
  options: { pruneMissing?: boolean } = {},
): Promise<MessageRecord[]> {
  const response = await authFetch(
    `/api/chat/threads/${encodeURIComponent(threadId)}/messages`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages,
        pruneMissing: options.pruneMissing ?? false,
      }),
    },
  );
  const data = await parseJsonOrThrow<{ messages: MessageRecord[] }>(response);
  notifyChatHistoryUpdated();
  return data.messages;
}

export async function countBackendChats(): Promise<number> {
  const response = await authFetch("/api/chat/count");
  const data = await parseJsonOrThrow<{ count: number }>(response);
  return data.count;
}

export async function clearBackendChats(
  options: { notify?: boolean } = {},
): Promise<void> {
  const response = await authFetch("/api/chat", { method: "DELETE" });
  await parseJsonOrThrow<unknown>(response);
  if (options.notify !== false) {
    notifyChatHistoryUpdated();
  }
}

export async function buildBackendChatExport(): Promise<{
  exportedAt: string;
  version: number;
  threadCount: number;
  projects?: ProjectRecord[];
  threads: ThreadRecord[];
  messages: MessageRecord[];
}> {
  const response = await authFetch("/api/chat/export");
  return parseJsonOrThrow(response);
}

// Legacy-Dexie import ledger: server-side source of truth replacing the
// boolean localStorage sentinel, so a studio.db wipe keeps the import
// recoverable.
export async function listChatImportLedger(): Promise<Set<string>> {
  const response = await authFetch("/api/chat/import-ledger");
  // Backends without this endpoint behave like an empty ledger -- caller
  // re-imports every legacy thread. syncChatMessages UPSERTs prevent
  // duplicates, so this fallback is safe.
  if (response.status === 404 || response.status === 405) return new Set();
  const data = await parseJsonOrThrow<{ threadIds: string[] }>(response);
  return new Set(data.threadIds);
}

export interface RecordChatImportLedgerResult {
  accepted: number;
  inserted: number;
  // false when the backend predates /api/chat/import-ledger (404/405/501) so
  // the caller avoids poisoning the localStorage perf hint; next launch
  // retries the (idempotent) import.
  supported: boolean;
}

export async function recordChatImportLedger(
  threadIds: string[],
): Promise<RecordChatImportLedgerResult> {
  if (threadIds.length === 0) {
    return { accepted: 0, inserted: 0, supported: true };
  }
  const response = await authFetch("/api/chat/import-ledger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threadIds }),
  });
  if (
    response.status === 404 ||
    response.status === 405 ||
    response.status === 501
  ) {
    return { accepted: 0, inserted: 0, supported: false };
  }
  const data = await parseJsonOrThrow<{ accepted: number; inserted: number }>(
    response,
  );
  return {
    accepted: data.accepted,
    inserted: data.inserted,
    supported: true,
  };
}

export interface BrowseEntry {
  name: string;
  has_models: boolean;
  hidden: boolean;
}

export interface BrowseFoldersResponse {
  current: string;
  parent: string | null;
  entries: BrowseEntry[];
  suggestions: string[];
  truncated?: boolean;
  model_files_here?: number;
}

export async function listRecommendedFolders(): Promise<string[]> {
  const response = await authFetch("/api/models/recommended-folders");
  const data = await parseJsonOrThrow<{ folders: string[] }>(response);
  return data.folders;
}

export async function browseFolders(
  path?: string,
  showHidden = false,
  signal?: AbortSignal,
): Promise<BrowseFoldersResponse> {
  const params = new URLSearchParams();
  if (path !== undefined && path !== null) params.set("path", path);
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString();
  // Forward the AbortSignal through authFetch -> fetch so a cancelled
  // FolderBrowser navigation actually cancels the in-flight request
  // server-side, instead of just dropping the response while the backend
  // keeps walking large directory trees.
  const response = await authFetch(
    `/api/models/browse-folders${qs ? `?${qs}` : ""}`,
    signal ? { signal } : undefined,
  );
  return parseJsonOrThrow<BrowseFoldersResponse>(response);
}

export async function listGgufVariants(
  repoId: string,
  hfToken?: string,
): Promise<GgufVariantsResponse> {
  const params = new URLSearchParams({ repo_id: repoId });
  if (hfToken) params.set("hf_token", hfToken);
  const response = await authFetch(`/api/models/gguf-variants?${params}`);
  return parseJsonOrThrow<GgufVariantsResponse>(response);
}

export interface KvCacheEstimate {
  kv_bytes: number | null;
  weights_bytes: number | null;
  native_context: number | null;
}

/** Estimate KV cache + weight bytes for a downloaded quant at a context length,
 * for the load dialog's memory warning. */
export async function estimateKvCache(
  repoId: string,
  quant: string,
  nCtx: number,
  cacheTypeKv?: string | null,
  signal?: AbortSignal,
): Promise<KvCacheEstimate> {
  const params = new URLSearchParams({
    repo_id: repoId,
    quant,
    n_ctx: String(nCtx),
  });
  if (cacheTypeKv) params.set("cache_type_kv", cacheTypeKv);
  const response = await authFetch(
    `/api/models/kv-cache-estimate?${params}`,
    signal ? { signal } : undefined,
  );
  return parseJsonOrThrow<KvCacheEstimate>(response);
}

function parseSseEvent(rawEvent: string): string[] {
  const dataLines: string[] = [];
  for (const line of rawEvent.split(/\r?\n/)) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  return dataLines;
}

export async function* streamChatCompletions(
  payload: OpenAIChatCompletionsRequest,
  signal: AbortSignal,
): AsyncGenerator<OpenAIChatChunk> {
  const response = await authFetch("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(parseErrorText(response.status, body));
  }

  if (!response.body) {
    throw new Error("Stream response missing body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.search(/\r?\n\r?\n/);
    while (separatorIndex >= 0) {
      const rawEvent = buffer.slice(0, separatorIndex);
      const separatorLength = buffer[separatorIndex] === "\r" ? 4 : 2;
      buffer = buffer.slice(separatorIndex + separatorLength);

      const dataLines = parseSseEvent(rawEvent);
      if (dataLines.length === 0) {
        separatorIndex = buffer.search(/\r?\n\r?\n/);
        continue;
      }

      const dataText = dataLines.join("\n");
      if (dataText === "[DONE]") {
        return;
      }

      const parsed = JSON.parse(dataText) as
        | OpenAIChatChunk
        | { type?: string; content?: string; error?: unknown };
      if ("error" in parsed && parsed.error) {
        throw new Error(parseProviderErrorText(parsed) || "Stream error");
      }
      // Tool status events are custom SSE payloads, not OpenAI chunks
      if ("type" in parsed && parsed.type === "tool_status") {
        yield {
          _toolStatus: parsed.content ?? "",
        } as unknown as OpenAIChatChunk;
        separatorIndex = buffer.search(/\r?\n\r?\n/);
        continue;
      }
      // Diffusion frame: a per-step canvas snapshot. Custom SSE payload (not an OpenAI chunk) with
      // no assistant text, surfaced as a transient marker for the in-place renderer, never the transcript.
      if ("type" in parsed && parsed.type === "diffusion_frame") {
        yield {
          _diffusionFrame: parsed,
        } as unknown as OpenAIChatChunk;
        separatorIndex = buffer.search(/\r?\n\r?\n/);
        continue;
      }
      // Tool start/end events carry full input/output for the tool outputs panel
      if (
        "type" in parsed &&
        (parsed.type === "tool_start" || parsed.type === "tool_end")
      ) {
        yield { _toolEvent: parsed } as unknown as OpenAIChatChunk;
        separatorIndex = buffer.search(/\r?\n\r?\n/);
        continue;
      }
      yield parsed as OpenAIChatChunk;
      separatorIndex = buffer.search(/\r?\n\r?\n/);
    }
  }
}

export async function generateAudio(
  payload: OpenAIChatCompletionsRequest,
  signal: AbortSignal,
): Promise<AudioGenerationResponse> {
  const response = await authFetch("/api/inference/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, stream: false }),
    signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(parseErrorText(response.status, body));
  }

  return (await response.json()) as AudioGenerationResponse;
}
