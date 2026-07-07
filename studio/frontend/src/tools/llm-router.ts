// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { toolsForMode } from "./registry.ts";

export type LLMRouteModel = {
  id: string;
  label?: string;
  provider: "huggingface" | "openrouter" | "openai" | "ollama" | "local" | "custom";
  local?: boolean;
  enabled?: boolean;
};

export type LLMRouterInput = {
  online: boolean;
  selectedModelId?: string | null;
  cloudModels: LLMRouteModel[];
  localModels: LLMRouteModel[];
};

export type LLMRouteDecision = {
  mode: "online" | "offline";
  primaryModel: LLMRouteModel | null;
  fallbackModel: LLMRouteModel | null;
  allowedToolNames: string[];
  reason: string;
};

function enabledModels(models: LLMRouteModel[]): LLMRouteModel[] {
  return models.filter((model) => model.enabled !== false);
}

function findSelected(
  models: LLMRouteModel[],
  selectedModelId?: string | null,
): LLMRouteModel | null {
  if (!selectedModelId) {
    return null;
  }
  return models.find((model) => model.id === selectedModelId) ?? null;
}

export function routeLLM(input: LLMRouterInput): LLMRouteDecision {
  const cloudModels = enabledModels(input.cloudModels);
  const localModels = enabledModels(input.localModels);
  const selectedCloud = findSelected(cloudModels, input.selectedModelId);
  const selectedLocal = findSelected(localModels, input.selectedModelId);
  const onlineTools = toolsForMode(input.online).map((tool) => tool.name);

  if (!input.online) {
    return {
      mode: "offline",
      primaryModel: selectedLocal ?? localModels[0] ?? null,
      fallbackModel: null,
      allowedToolNames: onlineTools,
      reason: "Internet indisponible: CogniX route uniquement vers un modele local.",
    };
  }

  const primaryModel = selectedCloud ?? selectedLocal ?? cloudModels[0] ?? localModels[0] ?? null;
  const fallbackModel = primaryModel?.local ? null : selectedLocal ?? localModels[0] ?? null;
  return {
    mode: "online",
    primaryModel,
    fallbackModel,
    allowedToolNames: onlineTools,
    reason:
      "Internet disponible: CogniX privilegie le modele cloud selectionne et garde un fallback local si possible.",
  };
}
