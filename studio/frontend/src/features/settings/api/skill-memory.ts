// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { authFetch } from "@/features/auth";
import { readFastApiError } from "@/lib/format-fastapi-error";

type JsonObject = Record<string, unknown>;

export type SkillMemoryStatus = "active" | "disabled";

export type ContextMemoryResponse = {
  memory?: {
    content?: string;
  };
};

export type SkillMemoryCandidate = {
  id: string;
  candidateKey?: string;
  candidateType?: string;
  category?: string;
  label?: string;
  value?: string;
  evidenceExcerpt?: string;
  confidence?: number;
  status?: string;
  projectId?: string | null;
  createdAt?: string;
  updatedAt?: string;
  decidedAt?: string | null;
  candidate?: JsonObject;
};

export type SkillMemoryRecord = {
  id: string;
  category?: string;
  label?: string;
  value?: string;
  confidence?: number;
  status?: SkillMemoryStatus | string;
  sourceCandidateId?: string | null;
  metadata?: JsonObject;
  createdAt?: string;
  updatedAt?: string;
};

export type UserPreferenceRecord = {
  id: string;
  preferenceKey?: string;
  category?: string;
  value?: string;
  status?: SkillMemoryStatus | string;
  sourceCandidateId?: string | null;
  metadata?: JsonObject;
  createdAt?: string;
  updatedAt?: string;
};

export type SkillMemoryListResponse = {
  username?: string;
  skillMemories?: SkillMemoryRecord[];
  preferences?: UserPreferenceRecord[];
  sideEffects?: JsonObject;
};

export type SkillMemoryCandidateListResponse = {
  username?: string;
  candidates?: SkillMemoryCandidate[];
  sideEffects?: JsonObject;
};

export type SkillMemoryCandidatePlanResponse = {
  username?: string;
  candidateMemoryPlan?: {
    summary?: {
      candidateCount?: number;
      requiresUserApprovalCount?: number;
    };
    candidates?: SkillMemoryCandidate[];
  };
  storedCandidates?: SkillMemoryCandidate[];
  sideEffects?: JsonObject;
};

export type SkillMemoryDecision = {
  label?: string;
  value?: string;
  category?: string;
};

export type SkillMemoryUpdate = SkillMemoryDecision & {
  status?: SkillMemoryStatus;
};

export type SkillMemoryInjectionPlanResponse = {
  injectionPlan?: {
    selectedMemoryIds?: string[];
    selectedMemories?: Array<{
      id?: string;
      category?: string;
      label?: string;
      value?: string;
    }>;
    summary?: {
      availableMemoryCount?: number;
      selectedMemoryCount?: number;
      willInjectNow?: boolean;
    };
  };
  sideEffects?: JsonObject;
};

export type SkillMemoryExportResponse = {
  memoryExport?: {
    username?: string;
    skillMemories?: SkillMemoryRecord[];
    preferences?: UserPreferenceRecord[];
    candidates?: SkillMemoryCandidate[];
    exportedAt?: string;
  };
};

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await readFastApiError(response, fallback));
  }
  return (await response.json()) as T;
}

export async function loadContextMemory(): Promise<ContextMemoryResponse> {
  const response = await authFetch("/api/cognix/context-memory");
  return readJson<ContextMemoryResponse>(
    response,
    "Failed to load context memory",
  );
}

export async function saveContextMemory(content: string): Promise<void> {
  const response = await authFetch("/api/cognix/context-memory", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  await readJson(response, "Failed to save context memory");
}

export async function listSkillMemories(
  includeDisabled = true,
): Promise<SkillMemoryListResponse> {
  const response = await authFetch(
    `/api/cognix/memory/skills?include_disabled=${String(includeDisabled)}`,
  );
  return readJson<SkillMemoryListResponse>(
    response,
    "Failed to load skill memories",
  );
}

export async function listSkillMemoryCandidates(
  includeDecided = true,
): Promise<SkillMemoryCandidateListResponse> {
  const response = await authFetch(
    `/api/cognix/memory/skills/candidates?include_decided=${String(includeDecided)}`,
  );
  return readJson<SkillMemoryCandidateListResponse>(
    response,
    "Failed to load memory candidates",
  );
}

export async function buildSkillMemoryCandidates(
  observation: string,
): Promise<SkillMemoryCandidatePlanResponse> {
  const response = await authFetch("/api/cognix/memory/skills/candidates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      observations: [{ text: observation }],
      storeCandidates: true,
    }),
  });
  return readJson<SkillMemoryCandidatePlanResponse>(
    response,
    "Failed to propose memory candidates",
  );
}

export async function approveSkillMemoryCandidate(
  candidateId: string,
  decision: SkillMemoryDecision,
): Promise<void> {
  const response = await authFetch(
    `/api/cognix/memory/skills/candidates/${encodeURIComponent(candidateId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    },
  );
  await readJson(response, "Failed to approve memory candidate");
}

export async function rejectSkillMemoryCandidate(
  candidateId: string,
): Promise<void> {
  const response = await authFetch(
    `/api/cognix/memory/skills/candidates/${encodeURIComponent(candidateId)}/reject`,
    { method: "POST" },
  );
  await readJson(response, "Failed to reject memory candidate");
}

export async function updateSkillMemory(
  memoryId: string,
  update: SkillMemoryUpdate,
): Promise<void> {
  const response = await authFetch(
    `/api/cognix/memory/skills/${encodeURIComponent(memoryId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    },
  );
  await readJson(response, "Failed to update skill memory");
}

export async function deleteSkillMemory(memoryId: string): Promise<void> {
  const response = await authFetch(
    `/api/cognix/memory/skills/${encodeURIComponent(memoryId)}`,
    { method: "DELETE" },
  );
  await readJson(response, "Failed to delete skill memory");
}

export async function buildSkillMemoryInjectionPlan(
  objective: string,
): Promise<SkillMemoryInjectionPlanResponse> {
  const response = await authFetch("/api/cognix/memory/skills/injection-plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objective,
      maxMemories: 5,
    }),
  });
  return readJson<SkillMemoryInjectionPlanResponse>(
    response,
    "Failed to build memory injection plan",
  );
}

export async function exportSkillMemory(): Promise<SkillMemoryExportResponse> {
  const response = await authFetch("/api/cognix/memory/skills/export");
  return readJson<SkillMemoryExportResponse>(
    response,
    "Failed to export skill memory",
  );
}
