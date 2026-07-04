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
  ArchiveRestoreIcon,
  GaugeIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  SparklesIcon,
  Trash2Icon,
  ZapIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createConversationSummaryPlan,
  createPromptCompressionPlan,
  deleteCompressedContext,
  listCompressedContexts,
  type CompressedContextRecord,
  type ConversationSummaryPlan,
  type PromptCompressionPlan,
} from "../api/chat-api";
import type { SidebarItem } from "../hooks/use-chat-sidebar-items";
import type { MessageRecord } from "../types";
import { listStoredChatMessages } from "../utils/chat-history-storage";

type CompressionMessage = {
  role: string;
  content: string;
  threadId?: string;
  title?: string;
  createdAt: number;
};

type LastPlan = {
  mode: string;
  plan: PromptCompressionPlan | ConversationSummaryPlan;
};

const DEFAULT_TARGET_TOKENS = 420;
const MAX_THREADS_FOR_CONTEXT = 32;
const MAX_MESSAGES_FOR_CONTEXT = 80;

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

function safeObjective(projectName: string): string {
  return `${projectName} context`;
}

function redactClientSide(value: string): string {
  return value
    .replace(/\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})\b/g, "[redacted_secret]")
    .replace(
      /\b(password|mot de passe|api[_ -]?key|token|secret)\s*[:=]\s*\S+/gi,
      "$1=[redacted_secret]",
    );
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

function formatPercent(value: number | null | undefined): string {
  const safe = Math.max(0, Math.min(1, Number(value ?? 0)));
  return `${Math.round(safe * 100)}%`;
}

function formatTokens(value: number | null | undefined): string {
  const safe = Math.max(0, Number(value ?? 0));
  if (safe >= 1000) return `${(safe / 1000).toFixed(1)}k`;
  return String(safe);
}

function contextRiskClass(risk: string | null | undefined): string {
  if (risk === "high") return "bg-red-500/10 text-red-700 dark:text-red-300";
  if (risk === "medium") {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function renderContextSource(messages: CompressionMessage[]): string {
  return messages
    .map((message, index) => {
      const prefix = `${index + 1}. ${message.role}`;
      const title = message.title ? ` (${message.title})` : "";
      return `${prefix}${title}: ${redactClientSide(message.content)}`;
    })
    .join("\n");
}

function newestProjectContext(
  contexts: CompressedContextRecord[],
): CompressedContextRecord | null {
  return contexts[0] ?? null;
}

async function collectProjectMessages(
  items: SidebarItem[],
): Promise<CompressionMessage[]> {
  const threadItems = items
    .filter((item) => item.type === "single")
    .slice(0, MAX_THREADS_FOR_CONTEXT);
  const batches = await Promise.all(
    threadItems.map(async (item) => {
      const messages = await listStoredChatMessages(item.id).catch(() => []);
      return messages.map((message) => ({
        role: String(message.role ?? "user"),
        content: messageContentText(message.content),
        threadId: item.id,
        title: item.title,
        createdAt: message.createdAt,
      }));
    }),
  );
  const flattened = batches
    .flat()
    .filter((message) => message.content.trim().length > 0)
    .sort((a, b) => a.createdAt - b.createdAt);
  if (flattened.length > 0) {
    return flattened.slice(-MAX_MESSAGES_FOR_CONTEXT);
  }
  return items.slice(0, MAX_MESSAGES_FOR_CONTEXT).map((item, index) => ({
    role: "user",
    content: item.title,
    threadId: item.id,
    title: item.title,
    createdAt: item.createdAt + index,
  }));
}

function ContextRecordRow({
  context,
  deleting,
  onDelete,
}: {
  context: CompressedContextRecord;
  deleting: boolean;
  onDelete: () => void;
}) {
  const risk = context.evaluation?.lostInfoRisk;
  return (
    <div className="rounded-[18px] bg-background/70 px-3 py-3">
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <ArchiveRestoreIcon className="size-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-foreground">
              {context.objectiveExcerpt || "Compressed context"}
            </p>
            <Badge variant="outline" className="bg-background text-muted-foreground">
              Context optimized
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{formatTokens(context.originalTokenCount)} tokens</span>
            <span>{"->"}</span>
            <span>{formatTokens(context.compressedTokenCount)}</span>
            <span>·</span>
            <span>{formatPercent(context.reductionRatio)} reduction</span>
            <span>·</span>
            <span>{formatDate(context.updatedAt ?? context.createdAt)}</span>
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-1 text-[11px] font-medium",
            contextRiskClass(risk),
          )}
        >
          {risk ?? "low"}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
          {context.compressedContext}
        </p>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          disabled={deleting}
          aria-label="Delete compressed context"
          onClick={onDelete}
          className="shrink-0 text-muted-foreground hover:text-destructive"
        >
          <Trash2Icon className="size-4" strokeWidth={1.75} />
        </Button>
      </div>
    </div>
  );
}

export function ProjectPromptCompressionPanel({
  projectId,
  projectName,
  items,
}: {
  projectId: string;
  projectName: string;
  items: SidebarItem[];
}) {
  const [contexts, setContexts] = useState<CompressedContextRecord[]>([]);
  const [objective, setObjective] = useState(() => safeObjective(projectName));
  const [targetTokens, setTargetTokens] = useState(DEFAULT_TARGET_TOKENS);
  const [lastPlan, setLastPlan] = useState<LastPlan | null>(null);
  const [messageCount, setMessageCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [deletingContextId, setDeletingContextId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const projectContexts = useMemo(
    () => contexts.filter((context) => context.projectId === projectId),
    [contexts, projectId],
  );
  const latestContext = newestProjectContext(projectContexts);

  const loadContexts = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const next = await listCompressedContexts({ projectId });
        setContexts(next);
        if (showToast) toast.success("Optimized contexts refreshed");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Context optimization unavailable";
        setError(message);
        if (showToast) {
          toast.error("Context optimization unavailable", {
            description: message,
          });
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
    setMessageCount(0);
    setLoading(true);
    void loadContexts(false);
  }, [loadContexts, projectName, projectId]);

  const handleOptimize = async () => {
    setOptimizing(true);
    setError(null);
    try {
      const messages = await collectProjectMessages(items);
      setMessageCount(messages.length);
      if (messages.length === 0) {
        toast.error("No project context available");
        return;
      }

      const payloadMessages = messages.map((message) => ({
        role: message.role,
        content: redactClientSide(message.content),
        threadId: message.threadId,
      }));
      let storedContext: CompressedContextRecord | null = null;
      let savedPlan: LastPlan | null = null;

      if (payloadMessages.length > 6) {
        const summaryResult = await createConversationSummaryPlan({
          messages: payloadMessages,
          objective: objective.trim() || safeObjective(projectName),
          projectId,
          targetTokens,
          recentMessageLimit: 6,
          storeContext: true,
        });
        storedContext = summaryResult.compressedContext;
        savedPlan = {
          mode: "conversation",
          plan: summaryResult.conversationSummaryPlan,
        };
      }

      if (!storedContext) {
        const compressionResult = await createPromptCompressionPlan({
          context: renderContextSource(messages),
          objective: objective.trim() || safeObjective(projectName),
          projectId,
          targetTokens,
          storeContext: true,
        });
        storedContext = compressionResult.compressedContext;
        savedPlan = {
          mode: "compression",
          plan: compressionResult.compressionPlan,
        };
      }

      if (storedContext) {
        setContexts((current) => [
          storedContext!,
          ...current.filter((item) => item.id !== storedContext!.id),
        ]);
      }
      setLastPlan(savedPlan);
      toast.success("Context optimized");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Context optimization failed";
      setError(message);
      toast.error("Context optimization failed", { description: message });
    } finally {
      setOptimizing(false);
    }
  };

  const handleDelete = async (contextId: string) => {
    setDeletingContextId(contextId);
    try {
      await deleteCompressedContext(contextId);
      setContexts((current) => current.filter((item) => item.id !== contextId));
      toast.success("Optimized context deleted");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Delete failed";
      toast.error("Delete failed", { description: message });
    } finally {
      setDeletingContextId(null);
    }
  };

  if (loading) {
    return (
      <div className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5">
        <Skeleton className="h-16 rounded-[22px]" />
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Skeleton className="h-24 rounded-[18px]" />
          <Skeleton className="h-24 rounded-[18px]" />
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="project-prompt-compression-panel"
      className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ZapIcon className="size-3.5" strokeWidth={1.75} />
            {projectContexts.length} optimized
          </span>
          {latestContext ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
              <GaugeIcon className="size-3.5" strokeWidth={1.75} />
              {formatPercent(latestContext.reductionRatio)}
            </span>
          ) : null}
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
            no generation
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={refreshing}
          onClick={() => void loadContexts(true)}
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
        <Textarea
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          placeholder="Objective"
          className="min-h-20 rounded-[18px] bg-background/70 text-sm"
        />
        <div className="grid gap-2">
          <Input
            type="number"
            min={64}
            max={8000}
            value={targetTokens}
            onChange={(event) =>
              setTargetTokens(
                Math.min(8000, Math.max(64, Number(event.target.value) || 64)),
              )
            }
            className="h-10 rounded-2xl bg-background/70 text-sm"
          />
          <Button
            type="button"
            disabled={optimizing || items.length === 0}
            onClick={() => void handleOptimize()}
            className="h-10 rounded-full"
          >
            <SparklesIcon className="size-4" strokeWidth={1.75} />
            Optimize
          </Button>
        </div>
      </div>

      {error ? (
        <p className="mt-3 rounded-[18px] bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {lastPlan ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="bg-background text-muted-foreground">
            Context optimized
          </Badge>
          <span>{lastPlan.mode}</span>
          <span>·</span>
          <span>{messageCount} messages</span>
          <span>·</span>
          <span>
            {formatTokens(lastPlan.plan.summary?.originalTokenCount)}
            {" -> "}
            {formatTokens(lastPlan.plan.summary?.compressedTokenCount)}
          </span>
          <span>·</span>
          <span>{lastPlan.plan.summary?.lostInfoRisk ?? "low"} risk</span>
        </div>
      ) : null}

      <div className="mt-4 grid gap-2">
        {projectContexts.length > 0 ? (
          projectContexts.slice(0, 6).map((context) => (
            <ContextRecordRow
              key={context.id}
              context={context}
              deleting={deletingContextId === context.id}
              onDelete={() => void handleDelete(context.id)}
            />
          ))
        ) : (
          <div className="rounded-[22px] bg-background/70 px-4 py-8 text-center">
            <p className="text-sm font-medium text-foreground">
              No optimized context
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
