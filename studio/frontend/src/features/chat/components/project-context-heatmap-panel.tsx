// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  ArchiveIcon,
  FlameIcon,
  GaugeIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createContextHeatmapPlan,
  listContextHeatmapEntries,
  type ContextHeatmapEntry,
  type ContextHeatmapPlan,
} from "../api/chat-api";
import type { SidebarItem } from "../hooks/use-chat-sidebar-items";
import type { MessageRecord } from "../types";
import { listStoredChatMessages } from "../utils/chat-history-storage";

type HeatmapChunk = {
  chunkId: string;
  sourceType: string;
  sourceId: string;
  title: string;
  text: string;
  ageDays: number;
  usageCount: number;
  responseCount: number;
  citationCount: number;
  copiedTermCount: number;
};

const MAX_HEATMAP_THREADS = 36;
const MAX_MESSAGES_PER_THREAD = 18;

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

function formatPercent(value: number | null | undefined): string {
  const safe = Math.max(0, Math.min(1, Number(value ?? 0)));
  return `${Math.round(safe * 100)}%`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "saved";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return "saved";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(time);
}

function dayAge(createdAt: number): number {
  if (!Number.isFinite(createdAt) || createdAt <= 0) return 0;
  return Math.max(0, Math.floor((Date.now() - createdAt) / 86_400_000));
}

function countMatches(value: string, pattern: RegExp): number {
  return value.match(pattern)?.length ?? 0;
}

function sourceLabel(sourceType: string | null | undefined): string {
  if (sourceType === "project_memory") return "Project memory";
  if (sourceType === "old_message") return "Old chat";
  if (sourceType === "document") return "Document";
  if (sourceType === "chat") return "Chat";
  return "Context";
}

function bucketClass(bucket: string | null | undefined): string {
  if (bucket === "very_useful") {
    return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (bucket === "archive_candidate") {
    return "bg-slate-500/10 text-slate-700 dark:text-slate-300";
  }
  return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
}

function actionLabel(action: string | null | undefined): string {
  if (action === "keep") return "keep";
  if (action === "archive") return "review archive";
  if (action === "deprioritize") return "deprioritize";
  return "review";
}

function newestTimestamp(messages: MessageRecord[], item: SidebarItem): number {
  return messages.reduce(
    (latest, message) => Math.max(latest, message.createdAt || 0),
    item.createdAt || 0,
  );
}

async function collectHeatmapChunks(
  projectName: string,
  items: SidebarItem[],
): Promise<HeatmapChunk[]> {
  const chunks: HeatmapChunk[] = [
    {
      chunkId: "project-memory",
      sourceType: "project_memory",
      sourceId: "project",
      title: projectName,
      text: `Project memory for ${projectName}. Native CogniX context, decisions, tasks, sources, and project direction.`,
      ageDays: 0,
      usageCount: Math.max(1, Math.min(5, items.length)),
      responseCount: Math.max(1, Math.min(4, Math.ceil(items.length / 2))),
      citationCount: 0,
      copiedTermCount: 2,
    },
  ];

  const threadItems = items
    .filter((item) => item.type === "single")
    .slice(0, MAX_HEATMAP_THREADS);
  const threadChunks = await Promise.all(
    threadItems.map(async (item) => {
      const messages = await listStoredChatMessages(item.id).catch(() => []);
      const relevantMessages = messages
        .slice(-MAX_MESSAGES_PER_THREAD)
        .map((message) => ({
          role: String(message.role ?? "user"),
          text: messageContentText(message.content),
        }))
        .filter((message) => message.text.trim().length > 0);
      const combinedText =
        relevantMessages.length > 0
          ? relevantMessages
              .map((message) => `${message.role}: ${message.text}`)
              .join("\n")
          : item.title;
      const latest = newestTimestamp(messages, item);
      const ageDays = dayAge(latest);
      const assistantCount = relevantMessages.filter(
        (message) => message.role === "assistant",
      ).length;
      const citationCount = countMatches(
        combinedText,
        /\b(rag|pdf|citation|source|document|dataset|library)\b/gi,
      );
      return {
        chunkId: `thread:${item.id}`,
        sourceType: ageDays >= 45 ? "old_message" : "chat",
        sourceId: item.id,
        title: item.title,
        text: combinedText,
        ageDays,
        usageCount: Math.min(8, relevantMessages.length),
        responseCount: Math.min(6, assistantCount),
        citationCount: Math.min(6, citationCount),
        copiedTermCount: countMatches(
          combinedText,
          /\b(cognix|project|context|memory|model|rag|security|native)\b/gi,
        ),
      };
    }),
  );

  chunks.push(...threadChunks.filter((chunk) => chunk.text.trim().length > 0));
  return chunks;
}

function HeatmapEntryRow({ entry }: { entry: ContextHeatmapEntry }) {
  const bucket = entry.bucket ?? "low_usage";
  return (
    <div className="rounded-[18px] bg-background/70 px-3 py-3">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-full",
            bucketClass(bucket),
          )}
        >
          {bucket === "very_useful" ? (
            <FlameIcon className="size-4" strokeWidth={1.75} />
          ) : bucket === "archive_candidate" ? (
            <ArchiveIcon className="size-4" strokeWidth={1.75} />
          ) : (
            <GaugeIcon className="size-4" strokeWidth={1.75} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-foreground">
              {entry.title || entry.chunkId}
            </p>
            <Badge variant="outline" className="bg-background text-muted-foreground">
              {sourceLabel(entry.sourceType)}
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{formatPercent(entry.utilityScore)}</span>
            <span>·</span>
            <span>{entry.usageCount ?? 0} uses</span>
            <span>·</span>
            <span>{entry.responseCount ?? 0} responses</span>
            <span>·</span>
            <span>{formatDate(entry.updatedAt ?? entry.createdAt)}</span>
          </div>
        </div>
        <span
          className={cn("rounded-full px-2 py-1 text-[11px] font-medium", bucketClass(bucket))}
        >
          {actionLabel(entry.recommendedAction)}
        </span>
      </div>
      {entry.matchedObjectiveTerms && entry.matchedObjectiveTerms.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {entry.matchedObjectiveTerms.slice(0, 8).map((term) => (
            <span
              key={term}
              className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground"
            >
              {term}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ProjectContextHeatmapPanel({
  projectId,
  projectName,
  items,
}: {
  projectId: string;
  projectName: string;
  items: SidebarItem[];
}) {
  const [entries, setEntries] = useState<ContextHeatmapEntry[]>([]);
  const [objective, setObjective] = useState(
    () => `${projectName} useful context`,
  );
  const [lastPlan, setLastPlan] = useState<ContextHeatmapPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [chunkCount, setChunkCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const bucketCounts = useMemo(
    () => ({
      veryUseful: entries.filter((entry) => entry.bucket === "very_useful").length,
      lowUsage: entries.filter((entry) => entry.bucket === "low_usage").length,
      archive: entries.filter((entry) => entry.bucket === "archive_candidate").length,
    }),
    [entries],
  );

  const loadHeatmap = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const result = await listContextHeatmapEntries({ projectId });
        setEntries(result.entries);
        if (showToast) toast.success("Context heatmap refreshed");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Context heatmap unavailable";
        setError(message);
        if (showToast) {
          toast.error("Context heatmap unavailable", { description: message });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    setObjective(`${projectName} useful context`);
    setLastPlan(null);
    setChunkCount(0);
    setLoading(true);
    void loadHeatmap(false);
  }, [loadHeatmap, projectName]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      const chunks = await collectHeatmapChunks(projectName, items);
      setChunkCount(chunks.length);
      if (chunks.length === 0) {
        toast.error("No project context available");
        return;
      }
      const result = await createContextHeatmapPlan({
        contextChunks: chunks,
        responseUsage: chunks.map((chunk) => ({
          chunkId: chunk.chunkId,
          usageCount: chunk.usageCount,
          responseCount: chunk.responseCount,
          citationCount: chunk.citationCount,
          copiedTermCount: chunk.copiedTermCount,
        })),
        objective: objective.trim() || `${projectName} useful context`,
        projectId,
        storeHeatmap: true,
      });
      setEntries(
        result.storedHeatmapEntries.length > 0
          ? result.storedHeatmapEntries
          : result.contextHeatmapPlan.entries ?? [],
      );
      setLastPlan(result.contextHeatmapPlan);
      toast.success("Context heatmap updated");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Context heatmap failed";
      setError(message);
      toast.error("Context heatmap failed", { description: message });
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) {
    return (
      <div className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5">
        <Skeleton className="h-12 rounded-[22px]" />
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Skeleton className="h-24 rounded-[18px]" />
          <Skeleton className="h-24 rounded-[18px]" />
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="project-context-heatmap-panel"
      className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <FlameIcon className="size-3.5" strokeWidth={1.75} />
            {bucketCounts.veryUseful} useful
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <GaugeIcon className="size-3.5" strokeWidth={1.75} />
            {bucketCounts.lowUsage} review
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ArchiveIcon className="size-3.5" strokeWidth={1.75} />
            {bucketCounts.archive} archive review
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
            no deletion
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={refreshing}
          onClick={() => void loadHeatmap(true)}
          className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
        >
          <RefreshCwIcon
            strokeWidth={1.75}
            className={cn("size-4", refreshing && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px]">
        <Input
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          placeholder="Objective"
          className="h-10 rounded-2xl bg-background/70 text-sm"
        />
        <Button
          type="button"
          disabled={analyzing}
          onClick={() => void handleAnalyze()}
          className="h-10 rounded-full"
        >
          <SparklesIcon className="size-4" strokeWidth={1.75} />
          Analyze
        </Button>
      </div>

      {error ? (
        <p className="mt-3 rounded-[18px] bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {lastPlan ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="bg-background text-muted-foreground">
            Context heatmap
          </Badge>
          <span>{chunkCount} chunks</span>
          <span>·</span>
          <span>
            {formatPercent(lastPlan.summary?.averageUtilityScore)} average
          </span>
          <span>·</span>
          <span>
            {lastPlan.garbageCollectorPlan?.requiresHumanConfirmation
              ? "review required"
              : "no cleanup needed"}
          </span>
        </div>
      ) : null}

      <div className="mt-4 grid gap-2">
        {entries.length > 0 ? (
          entries
            .slice(0, 8)
            .map((entry) => (
              <HeatmapEntryRow
                key={`${entry.chunkId}:${entry.updatedAt ?? entry.id ?? ""}`}
                entry={entry}
              />
            ))
        ) : (
          <div className="rounded-[22px] bg-background/70 px-4 py-8 text-center">
            <p className="text-sm font-medium text-foreground">
              No context heatmap
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
