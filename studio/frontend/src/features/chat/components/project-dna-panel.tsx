// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  BrainCircuitIcon,
  DnaIcon,
  RefreshCwIcon,
  SaveIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createProjectDnaInjectionPlan,
  getProjectDna,
  upsertProjectDna,
  type ProjectDnaDecision,
  type ProjectDnaModelRef,
  type ProjectDnaPlan,
  type ProjectDnaRecord,
  type ProjectDnaToolRef,
} from "../api/chat-api";
import type { SidebarItem } from "../hooks/use-chat-sidebar-items";
import type { MessageRecord } from "../types";
import { listStoredChatMessages } from "../utils/chat-history-storage";

type ProjectDnaDraft = {
  objective: string;
  context: string;
  responseStyle: string;
  preferredModelsText: string;
  allowedToolsText: string;
  constraintsText: string;
  decisionsText: string;
};

const MAX_DNA_THREADS = 8;
const MAX_DNA_MESSAGES = 8;

const DEFAULT_TOOLS = ["chat", "projects", "context", "rag", "models", "codex"];

const DEFAULT_CONSTRAINTS = [
  "Integrate changes natively in the CogniX source code.",
  "Keep the current CogniX design language stable.",
  "Do not call models directly from the frontend.",
  "Keep sensitive actions auditable and reversible.",
];

const DEFAULT_DECISIONS = [
  "Preserve CogniX branding and avoid regression to the old base interface.",
  "Route project memory through the Context Manager before generation.",
];

function messageContentText(content: MessageRecord["content"]): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      if (part.type === "text") return part.text;
      if (part.type === "image") return "Image";
      if (part.type === "audio") return "Audio";
      return "";
    })
    .filter(Boolean)
    .join(" ");
}

function uniqueLines(values: string[]): string[] {
  const seen = new Set<string>();
  const lines: string[] = [];
  values.forEach((value) => {
    const normalized = value.trim().replace(/\s+/g, " ");
    const key = normalized.toLowerCase();
    if (!normalized || seen.has(key)) return;
    seen.add(key);
    lines.push(normalized);
  });
  return lines;
}

function splitListText(value: string): string[] {
  return uniqueLines(
    value
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function modelText(models: ProjectDnaModelRef[]): string {
  return models
    .map((model) =>
      model.label && model.label !== model.modelId
        ? `${model.modelId} | ${model.label}`
        : model.modelId,
    )
    .join("\n");
}

function toolText(tools: ProjectDnaToolRef[]): string {
  return tools.map((tool) => tool.toolId).join("\n");
}

function decisionText(decisions: ProjectDnaDecision[]): string {
  return decisions
    .map((decision) =>
      decision.rationale
        ? `${decision.title} | ${decision.rationale}`
        : decision.title,
    )
    .join("\n");
}

function parseModels(value: string): ProjectDnaModelRef[] {
  return splitListText(value).map((line) => {
    const [modelId, label] = line.split("|").map((part) => part.trim());
    return {
      modelId,
      label: label || modelId,
    };
  });
}

function parseTools(value: string): ProjectDnaToolRef[] {
  return splitListText(value).map((toolId) => ({
    toolId,
    label: toolId,
  }));
}

function parseDecisions(value: string): ProjectDnaDecision[] {
  return uniqueLines(value.split("\n")).map((line, index) => {
    const [title, rationale] = line.split("|").map((part) => part.trim());
    return {
      decisionKey: `decision_${index + 1}`,
      title,
      rationale: rationale || undefined,
      status: "active",
    };
  });
}

function percent(value: number | null | undefined): string {
  const safe = Math.max(0, Math.min(1, Number(value ?? 0)));
  return `${Math.round(safe * 100)}%`;
}

function shortSnippet(value: string): string {
  return value.trim().replace(/\s+/g, " ").slice(0, 240);
}

async function collectProjectSeed(
  projectName: string,
  items: SidebarItem[],
): Promise<ProjectDnaDraft> {
  const threadItems = items
    .filter((item) => item.type === "single")
    .slice(0, MAX_DNA_THREADS);
  const threadSummaries = await Promise.all(
    threadItems.map(async (item) => {
      const messages = await listStoredChatMessages(item.id).catch(() => []);
      const recent = messages
        .slice(-MAX_DNA_MESSAGES)
        .map((message) => messageContentText(message.content))
        .map(shortSnippet)
        .filter(Boolean);
      return [item.title, ...recent].filter(Boolean).join(" ");
    }),
  );
  const contextLines = uniqueLines(
    threadSummaries
      .map((summary, index) =>
        summary ? `${index + 1}. ${summary.slice(0, 460)}` : "",
      )
      .filter(Boolean),
  );
  const lowerContext = contextLines.join("\n").toLowerCase();
  const constraints = [...DEFAULT_CONSTRAINTS];
  if (lowerContext.includes("https") || lowerContext.includes("cognix.local")) {
    constraints.push("Keep the local HTTPS access path stable when configured.");
  }
  if (lowerContext.includes("ollama")) {
    constraints.push("Load Ollama models lazily after the first user message.");
  }

  return {
    objective: `Maintain ${projectName} as a native CogniX project with stable memory, tools, and model routing.`,
    context:
      contextLines.length > 0
        ? contextLines.join("\n")
        : `Project ${projectName}. Native CogniX memory, tools, model routing, and product decisions.`,
    responseStyle: "Clear, direct, practical, and aligned with CogniX UI.",
    preferredModelsText: "",
    allowedToolsText: DEFAULT_TOOLS.join("\n"),
    constraintsText: uniqueLines(constraints).join("\n"),
    decisionsText: DEFAULT_DECISIONS.join("\n"),
  };
}

function draftFromRecord(
  record: ProjectDnaRecord | null,
  seed: ProjectDnaDraft,
): ProjectDnaDraft {
  if (!record) return seed;
  const profile = record.dna?.profile;
  return {
    objective: profile?.objective || record.objective || seed.objective,
    context: profile?.context || record.context || seed.context,
    responseStyle:
      profile?.responseStyle || record.responseStyle || seed.responseStyle,
    preferredModelsText: modelText(
      profile?.preferredModels.length
        ? profile.preferredModels
        : record.preferredModels,
    ),
    allowedToolsText: toolText(
      profile?.allowedTools.length ? profile.allowedTools : record.allowedTools,
    ),
    constraintsText:
      (profile?.constraints.length
        ? profile.constraints
        : record.constraints ?? []
      ).join("\n") || seed.constraintsText,
    decisionsText:
      decisionText(
        profile?.decisions.length ? profile.decisions : record.decisions ?? [],
      ) || seed.decisionsText,
  };
}

function payloadFromDraft(projectId: string, draft: ProjectDnaDraft) {
  return {
    projectId,
    objective: draft.objective.trim(),
    context: draft.context.trim(),
    responseStyle: draft.responseStyle.trim(),
    preferredModels: parseModels(draft.preferredModelsText),
    allowedTools: parseTools(draft.allowedToolsText),
    constraints: splitListText(draft.constraintsText),
    decisions: parseDecisions(draft.decisionsText),
  };
}

function DnaStat({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string;
  tone?: "muted" | "ready" | "safe";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 text-xs text-muted-foreground dark:bg-card",
        tone === "ready" && "text-emerald-700 dark:text-emerald-300",
        tone === "safe" && "text-sky-700 dark:text-sky-300",
      )}
    >
      {tone === "ready" ? (
        <DnaIcon className="size-3.5" strokeWidth={1.75} />
      ) : tone === "safe" ? (
        <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
      ) : (
        <BrainCircuitIcon className="size-3.5" strokeWidth={1.75} />
      )}
      <span>{value}</span>
      <span className="text-muted-foreground/70">{label}</span>
    </span>
  );
}

export function ProjectDnaPanel({
  projectId,
  projectName,
  items,
}: {
  projectId: string;
  projectName: string;
  items: SidebarItem[];
}) {
  const [draft, setDraft] = useState<ProjectDnaDraft | null>(null);
  const [storedDna, setStoredDna] = useState<ProjectDnaRecord | null>(null);
  const [plan, setPlan] = useState<ProjectDnaPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const readySections = useMemo(
    () => plan?.profile.completion.readySectionIds ?? [],
    [plan],
  );
  const completionScore = plan?.profile.completion.score ?? 0;
  const includedSections = useMemo(
    () => plan?.contextInjectionPlan.includedSectionIds ?? [],
    [plan],
  );

  const loadDna = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const [seed, record] = await Promise.all([
          collectProjectSeed(projectName, items),
          getProjectDna(projectId),
        ]);
        setStoredDna(record);
        setPlan(record?.dna ?? null);
        setDraft(draftFromRecord(record, seed));
        if (showToast) toast.success("Project DNA refreshed");
      } catch (err) {
        const message = err instanceof Error ? err.message : "Project DNA unavailable";
        setError(message);
        if (showToast) {
          toast.error("Project DNA unavailable", { description: message });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [items, projectId, projectName],
  );

  useEffect(() => {
    setLoading(true);
    void loadDna(false);
  }, [loadDna]);

  const updateDraft = <K extends keyof ProjectDnaDraft>(
    key: K,
    value: ProjectDnaDraft[K],
  ) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  };

  const handlePreview = async () => {
    if (!draft) return;
    setPlanning(true);
    setError(null);
    try {
      const result = await createProjectDnaInjectionPlan(
        payloadFromDraft(projectId, draft),
      );
      setPlan(result.projectDnaPlan);
      toast.success("Project DNA injection planned");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Project DNA preview failed";
      setError(message);
      toast.error("Project DNA preview failed", { description: message });
    } finally {
      setPlanning(false);
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const result = await upsertProjectDna({
        ...payloadFromDraft(projectId, draft),
        storeDna: true,
      });
      setStoredDna(result.projectDna ?? null);
      setPlan(result.projectDnaPlan);
      toast.success("Project DNA saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Project DNA save failed";
      setError(message);
      toast.error("Project DNA save failed", { description: message });
    } finally {
      setSaving(false);
    }
  };

  const sectionText = useMemo(
    () =>
      readySections.length > 0
        ? readySections.map((item) => item.replaceAll("_", " ")).join(" · ")
        : "draft",
    [readySections],
  );

  if (loading || !draft) {
    return (
      <div className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5">
        <Skeleton className="h-10 rounded-[20px]" />
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-32 rounded-[18px]" />
          <Skeleton className="h-32 rounded-[18px]" />
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="project-dna-panel"
      className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <DnaStat
            tone={completionScore > 0 ? "ready" : "muted"}
            value={percent(completionScore)}
            label="DNA"
          />
          <DnaStat value={`${readySections.length}`} label="sections" />
          <DnaStat
            tone="safe"
            value={plan?.contextInjectionPlan.willInjectNow ? "queued" : "preview"}
            label="context"
          />
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 text-xs text-muted-foreground dark:bg-card">
            <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
            no model call
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={refreshing}
            onClick={() => void loadDna(true)}
            className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
          >
            <RefreshCwIcon
              strokeWidth={1.75}
              className={cn("size-4", refreshing && "animate-spin")}
            />
            Refresh
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={planning}
            onClick={() => void handlePreview()}
            className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
          >
            <SparklesIcon className="size-4" strokeWidth={1.75} />
            Preview
          </Button>
          <Button type="button" size="sm" disabled={saving} onClick={() => void handleSave()}>
            <SaveIcon className="size-4" strokeWidth={1.75} />
            Save DNA
          </Button>
        </div>
      </div>

      {error ? (
        <p className="mb-3 rounded-[18px] bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="grid gap-3">
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Objective</span>
            <Input
              value={draft.objective}
              onChange={(event) => updateDraft("objective", event.target.value)}
              className="h-10 rounded-2xl bg-background/70 text-sm"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Context</span>
            <Textarea
              value={draft.context}
              onChange={(event) => updateDraft("context", event.target.value)}
              className="min-h-32 rounded-[18px] bg-background/70 text-sm"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Response style</span>
            <Textarea
              value={draft.responseStyle}
              onChange={(event) => updateDraft("responseStyle", event.target.value)}
              className="min-h-20 rounded-[18px] bg-background/70 text-sm"
            />
          </label>
        </div>

        <div className="grid gap-3">
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Preferred models</span>
            <Textarea
              value={draft.preferredModelsText}
              onChange={(event) =>
                updateDraft("preferredModelsText", event.target.value)
              }
              placeholder="model-id | Model label"
              className="min-h-20 rounded-[18px] bg-background/70 text-sm"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Allowed tools</span>
            <Textarea
              value={draft.allowedToolsText}
              onChange={(event) => updateDraft("allowedToolsText", event.target.value)}
              className="min-h-20 rounded-[18px] bg-background/70 text-sm"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Constraints</span>
            <Textarea
              value={draft.constraintsText}
              onChange={(event) => updateDraft("constraintsText", event.target.value)}
              className="min-h-24 rounded-[18px] bg-background/70 text-sm"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Decisions</span>
            <Textarea
              value={draft.decisionsText}
              onChange={(event) => updateDraft("decisionsText", event.target.value)}
              className="min-h-24 rounded-[18px] bg-background/70 text-sm"
            />
          </label>
        </div>
      </div>

      <div className="mt-4 rounded-[22px] bg-background/70 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="bg-background text-muted-foreground">
            Project DNA
          </Badge>
          <span>{storedDna?.status ?? plan?.status ?? "draft"}</span>
          <span>·</span>
          <span>{sectionText}</span>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Channel</p>
            <p className="mt-1 truncate text-sm font-medium text-foreground">
              {plan?.contextInjectionPlan.channelId ?? "project_dna"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Max tokens</p>
            <p className="mt-1 text-sm font-medium text-foreground">
              {plan?.contextInjectionPlan.maxTokens ?? 700}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Included</p>
            <p className="mt-1 truncate text-sm font-medium text-foreground">
              {includedSections.length > 0 ? includedSections.length : 0} sections
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
