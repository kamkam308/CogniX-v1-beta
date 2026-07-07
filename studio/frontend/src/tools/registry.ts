// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import type {
  StructuredStep,
  ToolDefinition,
  ToolExecutionContext,
  ToolImage,
  ToolMode,
  ToolResult,
} from "./types.ts";

const TEXT_SCHEMA = {
  type: "string",
  minLength: 1,
  maxLength: 2000,
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function cleanText(value: unknown, maxLength = 2000): string {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function cleanTextList(value: unknown, maxItems: number, maxLength = 200): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => cleanText(item, maxLength))
    .filter(Boolean)
    .slice(0, maxItems);
}

function createDeferred(reason: string): ToolResult {
  return {
    type: "deferred",
    reason,
  };
}

function createCard(input: unknown): ToolResult {
  const record = asRecord(input);
  return {
    type: "card",
    title: cleanText(record.title, 120) || "CogniX",
    body: cleanText(record.body, 2000),
  };
}

function createSteps(input: unknown): ToolResult {
  const record = asRecord(input);
  const steps = Array.isArray(record.steps) ? record.steps : [];
  return {
    type: "steps",
    steps: steps
      .map((step): StructuredStep => {
        const item = asRecord(step);
        return {
          title: cleanText(item.title, 120),
          body: cleanText(item.body ?? step, 600),
        };
      })
      .filter((step) => step.body)
      .slice(0, 12),
  };
}

function createTable(input: unknown): ToolResult {
  const record = asRecord(input);
  const columns = cleanTextList(record.columns, 8, 80);
  const rows = Array.isArray(record.rows) ? record.rows : [];
  return {
    type: "table",
    columns,
    rows: rows
      .filter(Array.isArray)
      .map((row) => cleanTextList(row, columns.length || 8, 240))
      .filter((row) => row.length > 0)
      .slice(0, 20),
  };
}

function searchLocalImages(input: unknown, context: ToolExecutionContext): ToolResult {
  const record = asRecord(input);
  const query = cleanText(record.query, 120).toLowerCase();
  const count = Math.min(Math.max(Number(record.count) || 4, 1), 8);
  const images = (context.localImages ?? [])
    .filter((image) => {
      const haystack = `${image.alt} ${image.title ?? ""} ${image.source ?? ""}`.toLowerCase();
      return !query || haystack.includes(query);
    })
    .slice(0, count);
  return { type: "images", images };
}

export const TOOL_REGISTRY: ToolDefinition[] = [
  {
    name: "image_search_online",
    description:
      "Recherche d'images web. Doit etre executee cote backend pour proteger les cles et respecter le mode online.",
    mode: "online",
    input_schema: {
      type: "object",
      required: ["query"],
      additionalProperties: false,
      properties: {
        query: TEXT_SCHEMA,
        count: { type: "number", minimum: 1, maximum: 8 },
      },
    },
    execute: () =>
      createDeferred("image_search_online doit etre execute cote backend avec une cle serveur."),
  },
  {
    name: "image_local_search",
    description: "Recherche d'images locales deja indexees, disponible hors ligne.",
    mode: "offline",
    input_schema: {
      type: "object",
      required: ["query"],
      additionalProperties: false,
      properties: {
        query: TEXT_SCHEMA,
        count: { type: "number", minimum: 1, maximum: 8 },
      },
    },
    execute: searchLocalImages,
  },
  {
    name: "create_table",
    description: "Transforme des donnees structurees en tableau Markdown compact.",
    mode: "both",
    input_schema: {
      type: "object",
      required: ["columns", "rows"],
      additionalProperties: false,
      properties: {
        columns: {
          type: "array",
          minItems: 1,
          maxItems: 8,
          items: TEXT_SCHEMA,
        },
        rows: {
          type: "array",
          maxItems: 20,
          items: {
            type: "array",
            maxItems: 8,
            items: TEXT_SCHEMA,
          },
        },
      },
    },
    execute: createTable,
  },
  {
    name: "create_card",
    description: "Cree une carte UI compacte sans effet de bord.",
    mode: "both",
    input_schema: {
      type: "object",
      required: ["body"],
      additionalProperties: false,
      properties: {
        title: TEXT_SCHEMA,
        body: TEXT_SCHEMA,
      },
    },
    execute: createCard,
  },
  {
    name: "create_steps",
    description: "Cree une reponse courte en etapes.",
    mode: "both",
    input_schema: {
      type: "object",
      required: ["steps"],
      additionalProperties: false,
      properties: {
        steps: {
          type: "array",
          minItems: 1,
          maxItems: 12,
          items: {
            type: "object",
            required: ["body"],
            additionalProperties: false,
            properties: {
              title: TEXT_SCHEMA,
              body: TEXT_SCHEMA,
            },
          },
        },
      },
    },
    execute: createSteps,
  },
  {
    name: "web_search",
    description:
      "Recherche web. Proposition seulement cote frontend; execution serveur requise.",
    mode: "online",
    input_schema: {
      type: "object",
      required: ["query"],
      additionalProperties: false,
      properties: {
        query: TEXT_SCHEMA,
        count: { type: "number", minimum: 1, maximum: 10 },
      },
    },
    execute: () => createDeferred("web_search doit etre execute cote backend."),
  },
  {
    name: "file_reader",
    description:
      "Lecture de fichier utilisateur. Necessite un fichier explicitement fourni et une validation backend.",
    mode: "both",
    input_schema: {
      type: "object",
      required: ["fileId"],
      additionalProperties: false,
      properties: {
        fileId: TEXT_SCHEMA,
      },
    },
    execute: () => createDeferred("file_reader attend un fichier utilisateur valide cote backend."),
  },
  {
    name: "app_action",
    description: "Action applicative whitelistée; confirmation requise pour toute action sensible.",
    mode: "both",
    input_schema: {
      type: "object",
      required: ["action"],
      additionalProperties: false,
      properties: {
        action: TEXT_SCHEMA,
        payload: { type: "object", additionalProperties: true },
      },
    },
    execute: () => createDeferred("app_action doit passer par une whitelist et une confirmation."),
  },
];

export function toolsForMode(online: boolean): ToolDefinition[] {
  return TOOL_REGISTRY.filter((tool) => tool.mode === "both" || tool.mode === (online ? "online" : "offline"));
}

export function getToolDefinition(name: string): ToolDefinition | undefined {
  return TOOL_REGISTRY.find((tool) => tool.name === name);
}

export function canUseToolMode(tool: ToolDefinition, mode: ToolMode): boolean {
  return tool.mode === "both" || tool.mode === mode;
}

export type { ToolImage };
