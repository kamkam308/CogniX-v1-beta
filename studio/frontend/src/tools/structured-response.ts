// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import type {
  StructuredAction,
  StructuredCard,
  StructuredResponse,
  StructuredStep,
  StructuredTable,
  ToolImage,
  ToolProposal,
} from "./types.ts";

const MAX_CARDS = 6;
const MAX_IMAGES = 6;
const MAX_STEPS = 12;
const MAX_TABLES = 4;
const MAX_TABLE_COLUMNS = 8;
const MAX_TABLE_ROWS = 20;
const MAX_TEXT = 4000;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function cleanText(value: unknown, maxLength = MAX_TEXT): string {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .trim()
    .slice(0, maxLength);
}

function markdownCell(value: unknown): string {
  return cleanText(value, 500).replace(/\|/g, "\\|").replace(/\n+/g, "<br>");
}

function markdownAlt(value: unknown): string {
  return cleanText(value, 160).replace(/[[\]]/g, "");
}

function markdownLinkLabel(value: unknown): string {
  return cleanText(value, 80).replace(/[[\]]/g, "");
}

function isSafeUrl(value: string): boolean {
  if (!value) {
    return false;
  }
  if (value.startsWith("/") && !value.startsWith("//")) {
    return true;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function parseJsonCandidate(source: string): unknown | null {
  const trimmed = source.trim();
  if (!trimmed) {
    return null;
  }
  const fence = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const candidate = fence?.[1] ?? trimmed;
  if (!candidate.startsWith("{") || !candidate.endsWith("}")) {
    return null;
  }
  try {
    return JSON.parse(candidate);
  } catch {
    return null;
  }
}

function normalizeCards(value: unknown): boolean | StructuredCard[] | undefined {
  if (typeof value === "boolean") {
    return value;
  }
  if (!Array.isArray(value)) {
    return undefined;
  }
  const cards = value
    .map((item): StructuredCard => {
      const record = asRecord(item);
      return {
        title: cleanText(record.title, 120),
        body: cleanText(record.body ?? item, 1000),
      };
    })
    .filter((card) => card.body)
    .slice(0, MAX_CARDS);
  return cards.length > 0 ? cards : undefined;
}

function normalizeImages(value: unknown): ToolImage[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const images = value
    .map((item): ToolImage | null => {
      const record = asRecord(item);
      const src = cleanText(record.src ?? record.url, 2000);
      if (!isSafeUrl(src)) {
        return null;
      }
      return {
        src,
        alt: cleanText(record.alt ?? record.title ?? "image", 160),
        title: cleanText(record.title, 160),
        source: cleanText(record.source, 160),
      };
    })
    .filter((image): image is ToolImage => image !== null)
    .slice(0, MAX_IMAGES);
  return images.length > 0 ? images : undefined;
}

function normalizeSteps(value: unknown): StructuredStep[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const steps = value
    .map((item): StructuredStep => {
      const record = asRecord(item);
      return {
        title: cleanText(record.title, 120),
        body: cleanText(record.body ?? item, 1000),
      };
    })
    .filter((step) => step.body)
    .slice(0, MAX_STEPS);
  return steps.length > 0 ? steps : undefined;
}

function normalizeTables(value: unknown): StructuredTable[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const tables = value
    .map((item): StructuredTable | null => {
      const record = asRecord(item);
      const columns = Array.isArray(record.columns)
        ? record.columns.map((column) => markdownCell(column)).filter(Boolean)
        : [];
      const rows = Array.isArray(record.rows) ? record.rows : [];
      if (columns.length === 0) {
        return null;
      }
      return {
        title: cleanText(record.title, 120),
        columns: columns.slice(0, MAX_TABLE_COLUMNS),
        rows: rows
          .filter(Array.isArray)
          .map((row) =>
            row
              .slice(0, MAX_TABLE_COLUMNS)
              .map((cell: unknown) => markdownCell(cell)),
          )
          .filter((row) => row.length > 0)
          .slice(0, MAX_TABLE_ROWS),
      };
    })
    .filter((table): table is StructuredTable => table !== null)
    .slice(0, MAX_TABLES);
  return tables.length > 0 ? tables : undefined;
}

function normalizeActions(value: unknown): StructuredAction[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const actions = value
    .map((item): StructuredAction | null => {
      const record = asRecord(item);
      const label = cleanText(record.label, 80);
      if (!label) {
        return null;
      }
      const url = cleanText(record.url, 2000);
      return {
        label,
        url: isSafeUrl(url) ? url : undefined,
        action: cleanText(record.action, 120),
      };
    })
    .filter((action): action is StructuredAction => action !== null)
    .slice(0, 6);
  return actions.length > 0 ? actions : undefined;
}

function normalizeToolProposals(value: unknown): ToolProposal[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const proposals = value
    .map((item): ToolProposal | null => {
      const record = asRecord(item);
      const name = cleanText(record.name, 80);
      return name ? { name, input: record.input } : null;
    })
    .filter((proposal): proposal is ToolProposal => proposal !== null)
    .slice(0, 8);
  return proposals.length > 0 ? proposals : undefined;
}

export function parseStructuredResponse(source: string): StructuredResponse | null {
  const parsed = parseJsonCandidate(source);
  const record = asRecord(parsed);
  const ui = asRecord(record.ui);
  const answer = cleanText(record.answer);
  const tools = normalizeToolProposals(record.tools);
  const normalizedUi: StructuredResponse["ui"] = {
    layout:
      ui.layout === "compact" ||
      ui.layout === "compact_visual" ||
      ui.layout === "detailed" ||
      ui.layout === "expert"
        ? ui.layout
        : undefined,
    cards: normalizeCards(ui.cards),
    images: normalizeImages(ui.images),
    tables: normalizeTables(ui.tables),
    steps: normalizeSteps(ui.steps),
    actions: normalizeActions(ui.actions ?? ui.buttons),
  };
  const hasUi = Object.values(normalizedUi).some((value) => value !== undefined);
  if (!answer && !tools && !hasUi) {
    return null;
  }
  return {
    answer: answer || undefined,
    tools,
    ui: hasUi ? normalizedUi : undefined,
  };
}

function renderImages(images: ToolImage[]): string {
  return images
    .map((image) => `![${markdownAlt(image.alt || image.title || "image")}](${image.src})`)
    .join("\n");
}

function renderCards(cards: StructuredCard[]): string {
  return cards
    .map((card) => {
      const title = card.title ? `> **${card.title}**\n` : "";
      const body = card.body
        .split("\n")
        .map((line) => `> ${line}`)
        .join("\n");
      return `${title}${body}`;
    })
    .join("\n\n");
}

function renderSteps(steps: StructuredStep[]): string {
  return steps
    .map((step, index) => {
      const title = step.title ? `**${step.title}** ` : "";
      return `${index + 1}. ${title}${step.body}`;
    })
    .join("\n");
}

function renderTable(table: StructuredTable): string {
  const columns = table.columns.map(markdownCell);
  const divider = columns.map(() => "---");
  const rows = table.rows.map((row) => {
    const cells = columns.map((_, index) => row[index] ?? "");
    return `| ${cells.join(" | ")} |`;
  });
  const title = table.title ? `**${table.title}**\n\n` : "";
  return `${title}| ${columns.join(" | ")} |\n| ${divider.join(" | ")} |\n${rows.join("\n")}`;
}

function renderActions(actions: StructuredAction[]): string {
  return actions
    .map((action) => {
      const label = markdownLinkLabel(action.label);
      if (action.url) {
        return `[${label}](${action.url})`;
      }
      return `**${label}**`;
    })
    .join("  ");
}

export function renderStructuredResponseToMarkdown(response: StructuredResponse): string {
  const sections: string[] = [];
  if (response.answer) {
    sections.push(response.answer);
  }
  const ui = response.ui;
  if (ui?.images?.length) {
    sections.push(renderImages(ui.images));
  }
  if (Array.isArray(ui?.cards) && ui.cards.length > 0) {
    sections.push(renderCards(ui.cards));
  }
  if (ui?.steps?.length) {
    sections.push(renderSteps(ui.steps));
  }
  if (ui?.tables?.length) {
    sections.push(ui.tables.map(renderTable).join("\n\n"));
  }
  if (ui?.actions?.length) {
    sections.push(renderActions(ui.actions));
  }
  return sections.join("\n\n").trim();
}
