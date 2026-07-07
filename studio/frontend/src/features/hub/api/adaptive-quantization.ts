// SPDX-License-Identifier: AGPL-3.0-only

import { authFetch } from "@/features/auth";
import { formatFastApiDetail } from "@/lib/format-fastapi-error";

export type QuantizationPriority =
  | "quality"
  | "speed"
  | "memory"
  | "balanced";

export interface QuantizationFit {
  status: string;
  fitScore: number;
  reason: string;
  estimatedRamGb: number;
  estimatedVramGb: number;
  gpuFit?: boolean;
  ramFit?: boolean;
}

export interface QuantizationVariant {
  variantId: string;
  variantKey: string;
  modelId: string;
  quantization: string;
  label: string;
  qualityScore: number;
  speedScore: number;
  memoryScore: number;
  priorityScore: number;
  risk?: string;
  fit: QuantizationFit;
  performancePrediction: {
    expectedLatency?: string;
    expectedQuality?: string;
    memoryPressure?: string;
    benchmarkRequiredForConfidence?: boolean;
  };
}

export interface QuantizationPlan {
  advisorVersion?: string;
  variantRegistryVersion?: string;
  performancePredictorVersion?: string;
  mode?: string;
  priority: QuantizationPriority;
  badge: {
    label: string;
    variantKey?: string;
    quantization?: string;
  };
  model: {
    modelId: string;
    label: string;
    providerType?: string;
    format?: string;
    baseQuantization?: string;
    baseEstimatedRamGb?: number;
  };
  hardware: {
    deviceBackend?: string;
    totalRamGb?: number;
    availableRamGb?: number;
    gpuAvailable?: boolean;
    gpuCount?: number;
    maxVramGb?: number;
  };
  selectedVariant: QuantizationVariant;
  alternativeVariants: QuantizationVariant[];
  benchmark: {
    available?: boolean;
    latestRunId?: string | null;
    recommendedBeforeApply?: boolean;
    willRunBenchmark?: boolean;
  };
  applyPlan: {
    willApplyAutomatically?: boolean;
    requiresHumanConfirmation?: boolean;
    requiresModelReload?: boolean;
    modelVariantSelectionOnly?: boolean;
    writesModelFiles?: boolean;
    writesRuntimeConfig?: boolean;
  };
  reason?: string;
  sideEffects?: Record<string, unknown>;
}

export interface QuantizationProfile {
  id: string;
  projectId?: string | null;
  priority: QuantizationPriority;
  modelId: string;
  selectedVariantId?: string | null;
  quantization: string;
  status?: string | null;
  plan: QuantizationPlan;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface QuantizationPlanResponse {
  quantizationPlan: QuantizationPlan;
  profile: QuantizationProfile | null;
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

function boolValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function normalizePriority(value: unknown): QuantizationPriority {
  const priority = maybeString(value)?.toLowerCase();
  if (
    priority === "quality" ||
    priority === "speed" ||
    priority === "memory" ||
    priority === "balanced"
  ) {
    return priority;
  }
  return "balanced";
}

function normalizeVariant(value: unknown): QuantizationVariant {
  const raw = asRecord(value);
  const fit = asRecord(raw.fit);
  const prediction = asRecord(raw.performancePrediction);
  return {
    variantId: stringValue(raw.variantId, "variant"),
    variantKey: stringValue(raw.variantKey, stringValue(raw.variantId)),
    modelId: stringValue(raw.modelId, "selected_model"),
    quantization: stringValue(raw.quantization, "Q4"),
    label: stringValue(raw.label, "Recommended quantization"),
    qualityScore: numberValue(raw.qualityScore, 0),
    speedScore: numberValue(raw.speedScore, 0),
    memoryScore: numberValue(raw.memoryScore, 0),
    priorityScore: numberValue(raw.priorityScore, 0),
    risk: maybeString(raw.risk) ?? undefined,
    fit: {
      status: stringValue(fit.status, "recommended"),
      fitScore: numberValue(fit.fitScore, 0),
      reason: stringValue(fit.reason, "Compatible with current hardware."),
      estimatedRamGb: numberValue(fit.estimatedRamGb, 0),
      estimatedVramGb: numberValue(fit.estimatedVramGb, 0),
      gpuFit: boolValue(fit.gpuFit),
      ramFit: boolValue(fit.ramFit),
    },
    performancePrediction: {
      expectedLatency: maybeString(prediction.expectedLatency) ?? undefined,
      expectedQuality: maybeString(prediction.expectedQuality) ?? undefined,
      memoryPressure: maybeString(prediction.memoryPressure) ?? undefined,
      benchmarkRequiredForConfidence: boolValue(
        prediction.benchmarkRequiredForConfidence,
      ),
    },
  };
}

function normalizePlan(value: unknown): QuantizationPlan {
  const raw = asRecord(value);
  const badge = asRecord(raw.badge);
  const model = asRecord(raw.model);
  const hardware = asRecord(raw.hardware);
  const benchmark = asRecord(raw.benchmark);
  const applyPlan = asRecord(raw.applyPlan);
  return {
    advisorVersion: maybeString(raw.advisorVersion) ?? undefined,
    variantRegistryVersion: maybeString(raw.variantRegistryVersion) ?? undefined,
    performancePredictorVersion:
      maybeString(raw.performancePredictorVersion) ?? undefined,
    mode: maybeString(raw.mode) ?? undefined,
    priority: normalizePriority(raw.priority),
    badge: {
      label: stringValue(badge.label, "Recommande pour ton PC"),
      variantKey: maybeString(badge.variantKey) ?? undefined,
      quantization: maybeString(badge.quantization) ?? undefined,
    },
    model: {
      modelId: stringValue(model.modelId, "selected_model"),
      label: stringValue(model.label, stringValue(model.modelId, "Model")),
      providerType: maybeString(model.providerType) ?? undefined,
      format: maybeString(model.format) ?? undefined,
      baseQuantization: maybeString(model.baseQuantization) ?? undefined,
      baseEstimatedRamGb: numberValue(model.baseEstimatedRamGb, 0),
    },
    hardware: {
      deviceBackend: maybeString(hardware.deviceBackend) ?? undefined,
      totalRamGb: numberValue(hardware.totalRamGb, 0),
      availableRamGb: numberValue(hardware.availableRamGb, 0),
      gpuAvailable: boolValue(hardware.gpuAvailable),
      gpuCount: numberValue(hardware.gpuCount, 0),
      maxVramGb: numberValue(hardware.maxVramGb, 0),
    },
    selectedVariant: normalizeVariant(raw.selectedVariant),
    alternativeVariants: Array.isArray(raw.alternativeVariants)
      ? raw.alternativeVariants.map(normalizeVariant)
      : [],
    benchmark: {
      available: boolValue(benchmark.available),
      latestRunId: maybeString(benchmark.latestRunId),
      recommendedBeforeApply: boolValue(benchmark.recommendedBeforeApply),
      willRunBenchmark: boolValue(benchmark.willRunBenchmark),
    },
    applyPlan: {
      willApplyAutomatically: boolValue(applyPlan.willApplyAutomatically),
      requiresHumanConfirmation: boolValue(applyPlan.requiresHumanConfirmation),
      requiresModelReload: boolValue(applyPlan.requiresModelReload),
      modelVariantSelectionOnly: boolValue(applyPlan.modelVariantSelectionOnly),
      writesModelFiles: boolValue(applyPlan.writesModelFiles),
      writesRuntimeConfig: boolValue(applyPlan.writesRuntimeConfig),
    },
    reason: maybeString(raw.reason) ?? undefined,
    sideEffects: asRecord(raw.sideEffects),
  };
}

function normalizeProfile(value: unknown): QuantizationProfile {
  const raw = asRecord(value);
  const plan = normalizePlan(raw.plan);
  return {
    id: stringValue(raw.id),
    projectId: maybeString(raw.projectId ?? raw.project_id),
    priority: normalizePriority(raw.priority ?? plan.priority),
    modelId: stringValue(raw.modelId ?? raw.model_id, plan.model.modelId),
    selectedVariantId: maybeString(
      raw.selectedVariantId ?? raw.selected_variant_id,
    ),
    quantization: stringValue(raw.quantization, plan.selectedVariant.quantization),
    status: maybeString(raw.status),
    plan,
    createdAt: maybeString(raw.createdAt ?? raw.created_at),
    updatedAt: maybeString(raw.updatedAt ?? raw.updated_at),
  };
}

export async function createAdaptiveQuantizationPlan(payload: {
  priority: QuantizationPriority;
  modelId?: string | null;
  modelMetadata?: Record<string, unknown> | null;
  projectId?: string | null;
  projectType?: string | null;
  storeProfile?: boolean;
}): Promise<QuantizationPlanResponse> {
  const response = await authFetch("/api/cognix/quantization/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      priority: payload.priority,
      modelId: payload.modelId ?? null,
      modelMetadata: payload.modelMetadata ?? null,
      projectId: payload.projectId ?? null,
      projectType: payload.projectType ?? null,
      storeProfile: payload.storeProfile ?? false,
    }),
  });
  const body = await parseJsonOrThrow<{
    quantizationPlan?: unknown;
    profile?: unknown;
    auditLogId?: string | null;
    sideEffects?: Record<string, unknown>;
    plannerVersion?: string;
  }>(response);
  return {
    quantizationPlan: normalizePlan(body.quantizationPlan),
    profile: body.profile ? normalizeProfile(body.profile) : null,
    auditLogId: body.auditLogId,
    sideEffects: body.sideEffects,
    plannerVersion: body.plannerVersion,
  };
}

export async function listQuantizationProfiles(payload?: {
  projectId?: string | null;
}): Promise<QuantizationProfile[]> {
  const params = new URLSearchParams();
  if (payload?.projectId) params.set("project_id", payload.projectId);
  const query = params.toString();
  const response = await authFetch(
    `/api/cognix/quantization/profiles${query ? `?${query}` : ""}`,
  );
  const body = await parseJsonOrThrow<{ profiles?: unknown[] }>(response);
  return (body.profiles ?? []).map(normalizeProfile);
}
