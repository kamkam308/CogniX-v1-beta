// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

export type ToolMode = "online" | "offline" | "both";

export type JsonSchema = {
  type: string;
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  required?: string[];
  enum?: string[];
  description?: string;
  additionalProperties?: boolean;
  minItems?: number;
  maxItems?: number;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
};

export type ToolExecutionContext = {
  online: boolean;
  localImages?: ToolImage[];
};

export type ToolImage = {
  src: string;
  alt: string;
  title?: string;
  source?: string;
};

export type ToolResult =
  | {
      type: "card";
      title: string;
      body: string;
    }
  | {
      type: "steps";
      steps: StructuredStep[];
    }
  | {
      type: "table";
      columns: string[];
      rows: string[][];
    }
  | {
      type: "images";
      images: ToolImage[];
    }
  | {
      type: "deferred";
      reason: string;
    };

export type ToolDefinition<Input = unknown, Output = ToolResult> = {
  name: string;
  description: string;
  input_schema: JsonSchema;
  mode: ToolMode;
  execute: (input: Input, context: ToolExecutionContext) => Output | Promise<Output>;
};

export type ToolProposal = {
  name: string;
  input?: unknown;
};

export type StructuredCard = {
  title?: string;
  body: string;
};

export type StructuredStep = {
  title?: string;
  body: string;
};

export type StructuredTable = {
  title?: string;
  columns: string[];
  rows: string[][];
};

export type StructuredAction = {
  label: string;
  url?: string;
  action?: string;
};

export type StructuredResponse = {
  answer?: string;
  tools?: ToolProposal[];
  ui?: {
    layout?: "compact" | "compact_visual" | "detailed" | "expert";
    cards?: boolean | StructuredCard[];
    images?: ToolImage[];
    tables?: StructuredTable[];
    steps?: StructuredStep[];
    actions?: StructuredAction[];
  };
};

export type ResponseStyle = "compact" | "detailed" | "expert" | "visual";
