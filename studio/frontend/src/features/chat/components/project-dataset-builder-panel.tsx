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
  DatabaseIcon,
  FileTextIcon,
  GaugeIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  type DatasetBuilderExample,
  type DatasetBuilderPlan,
  type DatasetBuilderSource,
  type GeneratedDatasetRecord,
  createDatasetBuilderPlan,
  listGeneratedDatasets,
} from "../api/chat-api";
import type { SidebarItem } from "../hooks/use-chat-sidebar-items";
import type { MessageRecord } from "../types";
import { listStoredChatMessages } from "../utils/chat-history-storage";

type DatasetDocument = {
  id: string;
  sourceId: string;
  sourceType: string;
  title: string;
  text: string;
  metadata: Record<string, unknown>;
};

type DatasetFormat = "jsonl" | "alpaca_json" | "chatml_jsonl";

const DATASET_FORMATS: Array<{ id: DatasetFormat; label: string }> = [
  { id: "jsonl", label: "JSONL" },
  { id: "alpaca_json", label: "Alpaca" },
  { id: "chatml_jsonl", label: "ChatML" },
];

const MAX_DATASET_THREADS = 24;
const MAX_MESSAGES_PER_THREAD = 16;
const MAX_DOCUMENT_CHARS = 7000;

function messageContentText(content: MessageRecord["content"]): string {
  if (typeof content === "string") {
    return content;
  }
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .map((part) => {
      if (part.type === "text") {
        return part.text;
      }
      if (part.type === "image") {
        return "Image";
      }
      if (part.type === "audio") {
        return "Audio";
      }
      return "";
    })
    .filter(Boolean)
    .join(" ");
}

function redactDatasetText(value: string): string {
  return value
    .replace(
      /\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})\b/g,
      "[redacted_secret]",
    )
    .replace(
      /\b(password|mot de passe|api[_ -]?key|token|secret)\s*[:=]\s*\S+/gi,
      "$1=[redacted_secret]",
    );
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "saved";
  }
  const time = Date.parse(value);
  if (!Number.isFinite(time)) {
    return "saved";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(time);
}

function formatPercent(value: number | null | undefined): string {
  const safe = Math.max(0, Math.min(1, Number(value ?? 0)));
  return `${Math.round(safe * 100)}%`;
}

function qualityClass(
  score: number | null | undefined,
  status?: string | null,
): string {
  if (status === "filtered" || Number(score ?? 0) < 0.48) {
    return "bg-slate-500/10 text-slate-700 dark:text-slate-300";
  }
  if (status === "review" || Number(score ?? 0) < 0.72) {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function sourceTypeLabel(value: string | null | undefined): string {
  if (value === "chat_thread") {
    return "Chat";
  }
  if (value === "project_seed") {
    return "Project";
  }
  if (value === "document") {
    return "Document";
  }
  return "Source";
}

function isDatasetDocument(
  source: DatasetBuilderSource | DatasetDocument,
): source is DatasetDocument {
  return "text" in source;
}

function sourceTokenCount(
  source: DatasetBuilderSource | DatasetDocument,
): number {
  if (isDatasetDocument(source)) {
    return Math.max(1, Math.round(source.text.length / 5));
  }
  return Math.max(1, Number(source.tokenCount ?? 0));
}

function sourceIdentity(
  source: DatasetBuilderSource | DatasetDocument,
): string {
  return source.sourceId || (isDatasetDocument(source) ? source.id : "source");
}

function sourceTitle(source: DatasetBuilderSource | DatasetDocument): string {
  if ("title" in source && source.title) {
    return source.title;
  }
  return sourceIdentity(source);
}

function safeObjective(projectName: string): string {
  return `${projectName} training dataset`;
}

function examplePreviewText(value: string): string {
  return value.trim().replace(/\s+/g, " ").slice(0, 220);
}

async function collectDatasetDocuments(
  projectName: string,
  items: SidebarItem[],
): Promise<DatasetDocument[]> {
  const threadItems = items
    .filter((item) => item.type === "single")
    .slice(0, MAX_DATASET_THREADS);
  const documents = await Promise.all(
    threadItems.map(async (item): Promise<DatasetDocument | null> => {
      const messages = await listStoredChatMessages(item.id).catch(() => []);
      const transcript = messages
        .slice(-MAX_MESSAGES_PER_THREAD)
        .map((message) => ({
          role: String(message.role ?? "user"),
          text: messageContentText(message.content),
        }))
        .filter((message) => message.text.trim().length > 0)
        .map((message) => `${message.role}: ${message.text}`)
        .join("\n");
      const text = redactDatasetText(transcript || item.title).slice(
        0,
        MAX_DOCUMENT_CHARS,
      );
      if (!text.trim()) {
        return null;
      }
      return {
        id: item.id,
        sourceId: item.id,
        sourceType: "chat_thread",
        title: item.title,
        text,
        metadata: {
          projectName,
          createdAt: item.createdAt,
          messageCount: messages.length,
        },
      };
    }),
  );
  const filtered = documents.filter((item): item is DatasetDocument =>
    Boolean(item),
  );
  if (filtered.length > 0) {
    return filtered;
  }
  return [
    {
      id: "project-seed",
      sourceId: "project-seed",
      sourceType: "project_seed",
      title: projectName,
      text: redactDatasetText(
        `Project ${projectName}. CogniX native project context, decisions, chats, tools, models, and training objectives.`,
      ),
      metadata: { projectName },
    },
  ];
}

function SourcePill({
  source,
}: { source: DatasetBuilderSource | DatasetDocument }) {
  const type = "sourceType" in source ? source.sourceType : "document";
  const sensitiveCount =
    "sensitiveTermCount" in source ? Number(source.sensitiveTermCount ?? 0) : 0;
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-background px-2.5 py-1 text-xs text-muted-foreground dark:bg-card">
      <FileTextIcon className="size-3.5 shrink-0" strokeWidth={1.75} />
      <span className="truncate">{sourceTitle(source)}</span>
      <span className="text-muted-foreground/70">
        {sourceTypeLabel(type)} · {sourceTokenCount(source)}
      </span>
      {sensitiveCount > 0 ? (
        <span className="text-amber-700 dark:text-amber-300">review</span>
      ) : null}
    </span>
  );
}

function ExampleRow({ example }: { example: DatasetBuilderExample }) {
  return (
    <div className="rounded-lg bg-background/70 px-3 py-3">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-full",
            qualityClass(example.qualityScore, example.status),
          )}
        >
          <GaugeIcon className="size-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-foreground">
              {example.metadata.sourceTitle || example.id}
            </p>
            <Badge
              variant="outline"
              className="bg-background text-muted-foreground"
            >
              {example.metadata.format || "jsonl"}
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{formatPercent(example.qualityScore)}</span>
            <span>·</span>
            <span>{example.tokenCount ?? 0} tokens</span>
            <span>·</span>
            <span>{example.status ?? "review"}</span>
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-1 text-[11px] font-medium",
            qualityClass(example.qualityScore, example.status),
          )}
        >
          {example.metadata.requiresHumanReview ? "review" : "ready"}
        </span>
      </div>
      <div className="mt-3 grid gap-2 text-xs leading-5 text-muted-foreground">
        <p className="line-clamp-2">
          <span className="font-medium text-foreground/80">Instruction: </span>
          {example.instruction}
        </p>
        <p className="line-clamp-2">
          <span className="font-medium text-foreground/80">Input: </span>
          {examplePreviewText(example.input)}
        </p>
        <p className="line-clamp-2">
          <span className="font-medium text-foreground/80">Output: </span>
          {examplePreviewText(example.output)}
        </p>
      </div>
    </div>
  );
}

function DatasetRecordRow({ dataset }: { dataset: GeneratedDatasetRecord }) {
  return (
    <div className="rounded-lg bg-background/60 px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">
            {dataset.objectiveExcerpt || dataset.id}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{dataset.exampleCount} examples</span>
            <span>·</span>
            <span>{dataset.readyExampleCount} ready</span>
            <span>·</span>
            <span>{formatDate(dataset.updatedAt ?? dataset.createdAt)}</span>
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-1 text-[11px] font-medium",
            qualityClass(
              dataset.qualitySummary.averageQualityScore,
              dataset.status,
            ),
          )}
        >
          {dataset.status ?? "review"}
        </span>
      </div>
    </div>
  );
}

// biome-ignore lint/complexity/noExcessiveCognitiveComplexity: this panel keeps the dataset draft controls, source disclosure, and review preview together.
export function ProjectDatasetBuilderPanel({
  projectId,
  projectName,
  items,
}: {
  projectId: string;
  projectName: string;
  items: SidebarItem[];
}) {
  const [datasets, setDatasets] = useState<GeneratedDatasetRecord[]>([]);
  const [objective, setObjective] = useState(() => safeObjective(projectName));
  const [outputFormat, setOutputFormat] = useState<DatasetFormat>("jsonl");
  const [maxExamples, setMaxExamples] = useState(30);
  const [lastPlan, setLastPlan] = useState<DatasetBuilderPlan | null>(null);
  const [lastSources, setLastSources] = useState<DatasetDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latestDataset = datasets[0] ?? null;
  const planSources = lastPlan?.dataSources;
  const planExamples = lastPlan?.examples;
  const sourceCount =
    planSources && planSources.length > 0
      ? planSources.length
      : lastSources.length;
  const quality = lastPlan?.qualitySummary;
  const sourceChips =
    planSources && planSources.length > 0 ? planSources : lastSources;

  const loadDatasets = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const result = await listGeneratedDatasets({ projectId });
        setDatasets(result.datasets);
        if (showToast) {
          toast.success("Datasets refreshed");
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Dataset builder unavailable";
        setError(message);
        if (showToast) {
          toast.error("Dataset builder unavailable", { description: message });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    setObjective(safeObjective(projectName));
    setLastPlan(null);
    setLastSources([]);
    setLoading(true);
    loadDatasets(false).catch(() => undefined);
  }, [loadDatasets, projectName]);

  const handleBuild = async () => {
    setBuilding(true);
    setError(null);
    try {
      const documents = await collectDatasetDocuments(projectName, items);
      setLastSources(documents);
      if (documents.length === 0) {
        toast.error("No project sources available");
        return;
      }
      const result = await createDatasetBuilderPlan({
        documents,
        objective: objective.trim() || safeObjective(projectName),
        outputFormat,
        maxExamples,
        projectId,
        storeDataset: true,
      });
      setLastPlan(result.datasetBuilderPlan);
      const generatedDataset = result.generatedDataset;
      if (generatedDataset) {
        setDatasets((current) => [
          generatedDataset,
          ...current.filter((item) => item.id !== generatedDataset.id),
        ]);
      }
      toast.success("Dataset draft created");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Dataset build failed";
      setError(message);
      toast.error("Dataset build failed", { description: message });
    } finally {
      setBuilding(false);
    }
  };

  if (loading) {
    return (
      <div className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5">
        <Skeleton className="h-16 rounded-[22px]" />
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="project-dataset-builder-panel"
      className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <DatabaseIcon className="size-3.5" strokeWidth={1.75} />
            {datasets.length} drafts
          </span>
          {latestDataset ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
              <GaugeIcon className="size-3.5" strokeWidth={1.75} />
              {formatPercent(latestDataset.qualitySummary.averageQualityScore)}
            </span>
          ) : null}
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
            no training
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={refreshing}
          onClick={() => {
            loadDatasets(true).catch(() => undefined);
          }}
          className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
        >
          <RefreshCwIcon
            strokeWidth={1.75}
            className={cn("size-4", refreshing && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_190px]">
        <Textarea
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          placeholder="Objective"
          className="min-h-20 rounded-[18px] bg-background/70 text-sm"
        />
        <div className="grid gap-2">
          <div className="grid grid-cols-3 gap-1 rounded-full bg-background/70 p-1 dark:bg-card">
            {DATASET_FORMATS.map((format) => (
              <button
                key={format.id}
                type="button"
                onClick={() => setOutputFormat(format.id)}
                data-active={outputFormat === format.id}
                className="h-8 rounded-full px-2 text-xs font-semibold text-muted-foreground transition-colors data-[active=true]:bg-foreground data-[active=true]:text-background"
              >
                {format.label}
              </button>
            ))}
          </div>
          <Input
            type="number"
            min={1}
            max={500}
            value={maxExamples}
            onChange={(event) =>
              setMaxExamples(
                Math.min(500, Math.max(1, Number(event.target.value) || 1)),
              )
            }
            className="h-10 rounded-2xl bg-background/70 text-sm"
          />
          <Button
            type="button"
            disabled={building}
            onClick={() => {
              handleBuild().catch(() => undefined);
            }}
            className="h-10 rounded-full"
          >
            <SparklesIcon className="size-4" strokeWidth={1.75} />
            Build
          </Button>
        </div>
      </div>

      {error ? (
        <p className="mt-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {sourceChips.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {sourceChips.slice(0, 8).map((source) => (
            <SourcePill key={sourceIdentity(source)} source={source} />
          ))}
        </div>
      ) : null}

      {lastPlan ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge
            variant="outline"
            className="bg-background text-muted-foreground"
          >
            Dataset draft
          </Badge>
          <span>{sourceCount} sources</span>
          <span>·</span>
          <span>{lastPlan.dataset.exampleCount} examples</span>
          <span>·</span>
          <span>{formatPercent(quality?.averageQualityScore)} average</span>
          <span>·</span>
          <span>
            {lastPlan.exportPlan.requiresHumanReview
              ? "review required"
              : "ready"}
          </span>
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]">
        <div className="grid gap-2">
          {planExamples && planExamples.length > 0 ? (
            planExamples
              .slice(0, 6)
              .map((example) => (
                <ExampleRow key={example.id} example={example} />
              ))
          ) : (
            <div className="rounded-lg bg-background/70 px-4 py-8 text-center">
              <p className="text-sm font-medium text-foreground">
                No dataset draft
              </p>
            </div>
          )}
        </div>
        <div className="grid gap-2">
          {lastPlan?.exportPlan.previewJsonl ? (
            <div className="rounded-lg bg-background/70 px-3 py-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-foreground">
                  Export preview
                </p>
                <Badge
                  variant="outline"
                  className="bg-background text-muted-foreground"
                >
                  {lastPlan.exportPlan.format || outputFormat}
                </Badge>
              </div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-muted/60 p-3 text-[11px] leading-5 text-muted-foreground">
                {lastPlan.exportPlan.previewJsonl}
              </pre>
            </div>
          ) : null}
          {datasets.length > 0 ? (
            datasets
              .slice(0, 4)
              .map((dataset) => (
                <DatasetRecordRow key={dataset.id} dataset={dataset} />
              ))
          ) : (
            <div className="rounded-lg bg-background/60 px-4 py-6 text-center">
              <p className="text-sm font-medium text-foreground">
                No saved drafts
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
