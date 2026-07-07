// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { providerSupportsBuiltinWebSearch } from "../src/features/chat/provider-capabilities.ts";
import { routeLLM } from "../src/tools/llm-router.ts";
import { TOOL_REGISTRY, toolsForMode } from "../src/tools/registry.ts";
import {
  parseStructuredResponse,
  renderStructuredResponseToMarkdown,
} from "../src/tools/structured-response.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

const eggResponse = JSON.stringify({
  answer: "Oui. Le jaune d'oeuf peut etre orange selon l'alimentation.",
  tools: [
    {
      name: "image_search_online",
      input: { query: "orange egg yolk", count: 3 },
    },
  ],
  ui: {
    layout: "compact_visual",
    images: [
      {
        src: "https://example.com/egg.jpg",
        alt: "jaune d'oeuf orange",
      },
    ],
    cards: [
      {
        title: "Pourquoi ?",
        body: "Les pigments naturels influencent la couleur.",
      },
    ],
    steps: [
      { body: "Verifier la fraicheur." },
      { body: "Observer la couleur du jaune." },
    ],
    tables: [
      {
        columns: ["Cas", "Explication"],
        rows: [["Jaune orange", "$\\beta$-carotene alimentaire"]],
      },
    ],
  },
});

const parsed = parseStructuredResponse(eggResponse);
assert(parsed, "Structured response should parse.");
const rendered = renderStructuredResponseToMarkdown(parsed);
assert(rendered.includes("jaune d'oeuf"), "Answer text should be preserved.");
assert(
  rendered.includes("![jaune d'oeuf orange]"),
  "Images should render as Markdown.",
);
assert(
  rendered.includes("| Cas | Explication |"),
  "Tables should render as Markdown.",
);
assert(
  rendered.includes("$\\beta$-carotene"),
  "LaTeX content inside tables should survive.",
);

const onlineTools = toolsForMode(true).map((tool) => tool.name);
const offlineTools = toolsForMode(false).map((tool) => tool.name);
assert(
  onlineTools.includes("image_search_online"),
  "Online image search should be online-only.",
);
assert(
  !offlineTools.includes("image_search_online"),
  "Offline mode must not expose online search.",
);
assert(
  offlineTools.includes("image_local_search"),
  "Offline mode should expose local image search.",
);
assert(
  TOOL_REGISTRY.every((tool) => typeof tool.execute === "function"),
  "Every registered tool needs an execute function.",
);

const offlineRoute = routeLLM({
  online: false,
  selectedModelId: "cloud",
  cloudModels: [{ id: "cloud", provider: "huggingface" }],
  localModels: [{ id: "qwen-local", provider: "ollama", local: true }],
});
assert(
  offlineRoute.primaryModel?.id === "qwen-local",
  "Offline route should use local model.",
);
assert(
  !offlineRoute.allowedToolNames.includes("web_search"),
  "Offline route must not expose web search.",
);

const onlineRoute = routeLLM({
  online: true,
  selectedModelId: "cloud",
  cloudModels: [{ id: "cloud", provider: "huggingface" }],
  localModels: [{ id: "qwen-local", provider: "ollama", local: true }],
});
assert(
  onlineRoute.primaryModel?.id === "cloud",
  "Online route should prefer selected cloud model.",
);
assert(
  onlineRoute.fallbackModel?.id === "qwen-local",
  "Online route should keep local fallback.",
);
assert(
  providerSupportsBuiltinWebSearch("huggingface", "openai/gpt-oss-120b"),
  "Hugging Face models should expose CogniX-managed web search.",
);
assert(
  providerSupportsBuiltinWebSearch("ollama", "qwen-local"),
  "Ollama models should expose CogniX-managed web search.",
);
assert(
  providerSupportsBuiltinWebSearch("openai", "gpt-5.5"),
  "OpenAI models should keep provider-native web search.",
);

process.stdout.write("CogniX tool orchestration check passed.\n");
