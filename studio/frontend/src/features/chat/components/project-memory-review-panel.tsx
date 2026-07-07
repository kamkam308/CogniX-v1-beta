// SPDX-License-Identifier: AGPL-3.0-only

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  ArchiveIcon,
  CheckCircle2Icon,
  CircleIcon,
  DatabaseIcon,
  GitMergeIcon,
  PencilIcon,
  RefreshCwIcon,
  SaveIcon,
  ShieldCheckIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createLiveMemoryItem,
  createMemoryCleanupPlan,
  disableLiveMemoryItem,
  listLiveMemoryItems,
  listMemoryCleanupSuggestions,
  listMemoryConflicts,
  mergeLiveMemoryItems,
  updateLiveMemoryItem,
  type LiveMemoryCategory,
  type LiveMemoryItem,
  type MemoryCleanupPlan,
  type MemoryCleanupSuggestion,
  type MemoryConflict,
} from "../api/chat-api";

type MemoryDraft = {
  title: string;
  content: string;
  category: LiveMemoryCategory;
  sensitive: boolean;
};

const MEMORY_CATEGORIES: Array<{ value: LiveMemoryCategory; label: string }> = [
  { value: "project", label: "Project" },
  { value: "preference", label: "Preference" },
  { value: "skill", label: "Skill" },
  { value: "organization", label: "Organization" },
  { value: "general", label: "General" },
];

const EMPTY_DRAFT: MemoryDraft = {
  title: "",
  content: "",
  category: "project",
  sensitive: false,
};

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

function ageDays(value: string | null | undefined): number {
  if (!value) return 0;
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return 0;
  return Math.max(0, Math.floor((Date.now() - time) / 86_400_000));
}

function categoryLabel(value: string | null | undefined): string {
  return (
    MEMORY_CATEGORIES.find((category) => category.value === value)?.label ??
    "General"
  );
}

function categoryClass(value: string | null | undefined): string {
  if (value === "preference") {
    return "bg-sky-500/10 text-sky-700 dark:text-sky-300";
  }
  if (value === "skill") {
    return "bg-violet-500/10 text-violet-700 dark:text-violet-300";
  }
  if (value === "organization") {
    return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (value === "project") {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-muted text-muted-foreground";
}

function actionClass(value: string | null | undefined): string {
  if (value === "merge") {
    return "bg-sky-500/10 text-sky-700 dark:text-sky-300";
  }
  if (value === "review_conflict") {
    return "bg-red-500/10 text-red-700 dark:text-red-300";
  }
  if (value === "archive") {
    return "bg-slate-500/10 text-slate-700 dark:text-slate-300";
  }
  return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
}

function cleanupPayload(memory: LiveMemoryItem): Record<string, unknown> {
  return {
    id: memory.id,
    memoryId: memory.id,
    projectId: memory.projectId,
    title: memory.title,
    content: memory.content,
    category: memory.category,
    status: memory.status,
    ageDays: ageDays(memory.updatedAt ?? memory.createdAt),
    preferenceKey: memory.title,
  };
}

function MemoryRow({
  memory,
  selected,
  busy,
  onEdit,
  onDisable,
  onToggleSelected,
}: {
  memory: LiveMemoryItem;
  selected: boolean;
  busy: boolean;
  onEdit: () => void;
  onDisable: () => void;
  onToggleSelected: () => void;
}) {
  return (
    <div className="rounded-[18px] bg-background/70 px-3 py-3">
      <div className="flex items-start gap-3">
        <button
          type="button"
          aria-label={selected ? "Unselect memory" : "Select memory"}
          onClick={onToggleSelected}
          className={cn(
            "mt-1 flex size-7 shrink-0 items-center justify-center rounded-full transition-colors",
            selected
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:text-foreground",
          )}
        >
          {selected ? (
            <CheckCircle2Icon className="size-4" strokeWidth={1.75} />
          ) : (
            <CircleIcon className="size-4" strokeWidth={1.75} />
          )}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-foreground">
              {memory.title || "Memory"}
            </p>
            <span
              className={cn(
                "rounded-full px-2 py-1 text-[11px] font-medium",
                categoryClass(memory.category),
              )}
            >
              {categoryLabel(memory.category)}
            </span>
            {memory.sensitive ? (
              <Badge variant="outline" className="bg-background text-muted-foreground">
                controlled
              </Badge>
            ) : null}
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
            {memory.content}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>v{memory.currentVersion || 1}</span>
            <span>·</span>
            <span>{memory.status}</span>
            <span>·</span>
            <span>{formatDate(memory.updatedAt ?? memory.createdAt)}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="Edit memory"
            onClick={onEdit}
            className="text-muted-foreground hover:text-foreground"
          >
            <PencilIcon className="size-4" strokeWidth={1.75} />
          </Button>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            disabled={busy || memory.status !== "active"}
            aria-label="Disable memory"
            onClick={onDisable}
            className="text-muted-foreground hover:text-destructive"
          >
            <ArchiveIcon className="size-4" strokeWidth={1.75} />
          </Button>
        </div>
      </div>
    </div>
  );
}

function SuggestionRow({
  suggestion,
  busy,
  onPrepare,
}: {
  suggestion: MemoryCleanupSuggestion;
  busy: boolean;
  onPrepare: () => void;
}) {
  return (
    <div className="rounded-[18px] bg-background/70 px-3 py-3">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-1 rounded-full px-2 py-1 text-[11px] font-medium",
            actionClass(suggestion.recommendedAction),
          )}
        >
          {suggestion.recommendedAction.replaceAll("_", " ")}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">
            {suggestion.title || suggestion.memoryId}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{suggestion.reasonCode.replaceAll("_", " ")}</span>
            <span>·</span>
            <span>{formatPercent(suggestion.confidence)}</span>
            <span>·</span>
            <span>review first</span>
          </div>
          {suggestion.detail ? (
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
              {suggestion.detail}
            </p>
          ) : null}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={onPrepare}
          className="shrink-0 border-none bg-muted text-foreground hover:bg-muted/80"
        >
          Review
        </Button>
      </div>
    </div>
  );
}

export function ProjectMemoryReviewPanel({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const [memories, setMemories] = useState<LiveMemoryItem[]>([]);
  const [suggestions, setSuggestions] = useState<MemoryCleanupSuggestion[]>([]);
  const [conflicts, setConflicts] = useState<MemoryConflict[]>([]);
  const [draft, setDraft] = useState<MemoryDraft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [mergeTitle, setMergeTitle] = useState("");
  const [mergeCategory, setMergeCategory] =
    useState<LiveMemoryCategory>("project");
  const [lastCleanupPlan, setLastCleanupPlan] =
    useState<MemoryCleanupPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [merging, setMerging] = useState(false);
  const [busyMemoryId, setBusyMemoryId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeMemories = useMemo(
    () => memories.filter((memory) => memory.status === "active"),
    [memories],
  );
  const disabledCount = useMemo(
    () => memories.filter((memory) => memory.status === "disabled").length,
    [memories],
  );
  const selectedMemories = useMemo(
    () => memories.filter((memory) => selectedIds.includes(memory.id)),
    [memories, selectedIds],
  );

  const loadMemory = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const [nextMemories, nextSuggestions, nextConflicts] =
          await Promise.all([
            listLiveMemoryItems({ projectId, includeDisabled: true }),
            listMemoryCleanupSuggestions({ projectId, limit: 50 }),
            listMemoryConflicts({ projectId, limit: 50 }),
          ]);
        setMemories(nextMemories.filter((memory) => memory.status !== "deleted"));
        setSuggestions(nextSuggestions);
        setConflicts(nextConflicts);
        if (showToast) toast.success("Memory refreshed");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Project memory unavailable";
        setError(message);
        if (showToast) {
          toast.error("Project memory unavailable", { description: message });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    setDraft({
      ...EMPTY_DRAFT,
      title: `${projectName} memory`,
    });
    setEditingId(null);
    setSelectedIds([]);
    setMergeTitle("");
    setLastCleanupPlan(null);
    setLoading(true);
    void loadMemory(false);
  }, [loadMemory, projectName]);

  const updateMemoryInState = (memory: LiveMemoryItem) => {
    setMemories((current) => [
      memory,
      ...current.filter((item) => item.id !== memory.id),
    ]);
  };

  const handleSave = async () => {
    const title = draft.title.trim();
    const content = draft.content.trim();
    if (!title || !content) {
      toast.error("Memory needs a title and content");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = editingId
        ? await updateLiveMemoryItem(editingId, {
            title,
            content,
            category: draft.category,
            reason: "project_memory_review_edit",
          })
        : await createLiveMemoryItem({
            title,
            content,
            category: draft.category,
            projectId,
            sensitive: draft.sensitive,
            confirmedSensitiveControl: draft.sensitive,
            metadata: { source: "project_memory_review_panel" },
          });
      if (result.memory) updateMemoryInState(result.memory);
      setDraft({ ...EMPTY_DRAFT, title: `${projectName} memory` });
      setEditingId(null);
      toast.success(editingId ? "Memory updated" : "Memory saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Memory save failed";
      setError(message);
      toast.error("Memory save failed", { description: message });
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (memory: LiveMemoryItem) => {
    setEditingId(memory.id);
    setDraft({
      title: memory.title,
      content: memory.content,
      category: memory.category,
      sensitive: memory.sensitive,
    });
  };

  const handleDisable = async (memoryId: string, reason = "manual_review") => {
    setBusyMemoryId(memoryId);
    try {
      const result = await disableLiveMemoryItem(memoryId, reason);
      if (result.memory) updateMemoryInState(result.memory);
      setSelectedIds((current) => current.filter((item) => item !== memoryId));
      toast.success("Memory disabled");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Memory disable failed";
      toast.error("Memory disable failed", { description: message });
    } finally {
      setBusyMemoryId(null);
    }
  };

  const handleCleanup = async () => {
    if (activeMemories.length === 0) {
      toast.error("No active memory to review");
      return;
    }
    setCleaning(true);
    setError(null);
    try {
      const result = await createMemoryCleanupPlan({
        projectId,
        memories: activeMemories.map(cleanupPayload),
        storeSuggestions: true,
      });
      setLastCleanupPlan(result.memoryCleanupPlan);
      setSuggestions(
        result.storedSuggestions.length > 0
          ? result.storedSuggestions
          : result.memoryCleanupPlan.suggestions,
      );
      setConflicts(
        result.storedConflicts.length > 0
          ? result.storedConflicts
          : result.memoryCleanupPlan.conflicts,
      );
      toast.success("Cleanup review prepared");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Cleanup review failed";
      setError(message);
      toast.error("Cleanup review failed", { description: message });
    } finally {
      setCleaning(false);
    }
  };

  const handlePrepareSuggestion = (suggestion: MemoryCleanupSuggestion) => {
    if (suggestion.recommendedAction === "merge" && suggestion.duplicateOf) {
      const nextIds = [suggestion.memoryId, suggestion.duplicateOf].filter(
        (id, index, values) => id && values.indexOf(id) === index,
      );
      setSelectedIds(nextIds);
      setMergeTitle(suggestion.title || "Merged memory");
      setMergeCategory(suggestion.category || "project");
      toast.success("Merge selection prepared");
      return;
    }
    if (
      suggestion.recommendedAction === "archive" ||
      suggestion.recommendedAction === "deprioritize"
    ) {
      void handleDisable(suggestion.memoryId, suggestion.reasonCode);
      return;
    }
    setSelectedIds((current) =>
      current.includes(suggestion.memoryId)
        ? current
        : [...current, suggestion.memoryId],
    );
    toast.success("Memory selected for review");
  };

  const toggleSelected = (memoryId: string) => {
    setSelectedIds((current) => {
      if (current.includes(memoryId)) {
        return current.filter((item) => item !== memoryId);
      }
      return [...current, memoryId].slice(0, 12);
    });
  };

  const handleMerge = async () => {
    if (selectedIds.length < 2) {
      toast.error("Select at least two memories");
      return;
    }
    setMerging(true);
    setError(null);
    try {
      const result = await mergeLiveMemoryItems({
        sourceIds: selectedIds,
        title: mergeTitle.trim() || `${projectName} merged memory`,
        category: mergeCategory,
        disableSources: true,
        metadata: { source: "project_memory_review_panel" },
      });
      if (result.memory) updateMemoryInState(result.memory);
      setSelectedIds([]);
      setMergeTitle("");
      await loadMemory(false);
      toast.success("Memories merged");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Memory merge failed";
      setError(message);
      toast.error("Memory merge failed", { description: message });
    } finally {
      setMerging(false);
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
      data-testid="project-memory-review-panel"
      className="mt-4 rounded-[26px] bg-muted/30 px-6 py-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <DatabaseIcon className="size-3.5" strokeWidth={1.75} />
            {activeMemories.length} active
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ArchiveIcon className="size-3.5" strokeWidth={1.75} />
            {disabledCount} disabled
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <SparklesIcon className="size-3.5" strokeWidth={1.75} />
            {suggestions.length} reviews
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
            <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
            rollback ready
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={refreshing}
          onClick={() => void loadMemory(true)}
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
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
            <Input
              value={draft.title}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
              placeholder="Memory title"
              className="h-10 rounded-2xl bg-background/70 text-sm"
            />
            <Select
              value={draft.category}
              onValueChange={(value) =>
                setDraft((current) => ({
                  ...current,
                  category: value,
                }))
              }
            >
              <SelectTrigger className="h-10 w-full rounded-2xl bg-background/70">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MEMORY_CATEGORIES.map((category) => (
                  <SelectItem key={category.value} value={category.value}>
                    {category.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Textarea
            value={draft.content}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                content: event.target.value,
              }))
            }
            placeholder="Native project memory"
            className="min-h-20 rounded-[18px] bg-background/70 text-sm"
          />
        </div>
        <div className="grid content-start gap-2">
          <label className="flex h-10 items-center justify-between rounded-2xl bg-background/70 px-3 text-sm text-muted-foreground">
            Sensitive
            <Switch
              size="sm"
              checked={draft.sensitive}
              onCheckedChange={(checked) =>
                setDraft((current) => ({
                  ...current,
                  sensitive: Boolean(checked),
                }))
              }
            />
          </label>
          <Button
            type="button"
            disabled={saving}
            onClick={() => void handleSave()}
            className="h-10 rounded-full"
          >
            <SaveIcon className="size-4" strokeWidth={1.75} />
            {editingId ? "Update" : "Save"}
          </Button>
          {editingId ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEditingId(null);
                setDraft({ ...EMPTY_DRAFT, title: `${projectName} memory` });
              }}
              className="h-10 rounded-full text-muted-foreground"
            >
              <XIcon className="size-4" strokeWidth={1.75} />
              Cancel
            </Button>
          ) : null}
        </div>
      </div>

      {selectedMemories.length > 0 ? (
        <div className="mt-3 grid gap-3 rounded-[22px] bg-background/70 p-3 lg:grid-cols-[minmax(0,1fr)_180px_150px]">
          <Input
            value={mergeTitle}
            onChange={(event) => setMergeTitle(event.target.value)}
            placeholder={`${selectedMemories.length} selected memories`}
            className="h-10 rounded-2xl bg-input/40 text-sm"
          />
          <Select
            value={mergeCategory}
            onValueChange={(value) => setMergeCategory(value)}
          >
            <SelectTrigger className="h-10 w-full rounded-2xl bg-input/40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MEMORY_CATEGORIES.map((category) => (
                <SelectItem key={category.value} value={category.value}>
                  {category.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            disabled={merging || selectedIds.length < 2}
            onClick={() => void handleMerge()}
            className="h-10 rounded-full"
          >
            <GitMergeIcon className="size-4" strokeWidth={1.75} />
            Merge
          </Button>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={cleaning || activeMemories.length === 0}
          onClick={() => void handleCleanup()}
          className="h-9 rounded-full border-none bg-background text-foreground hover:bg-background/80 dark:bg-card"
        >
          <SparklesIcon className="size-4" strokeWidth={1.75} />
          Review cleanup
        </Button>
        {lastCleanupPlan ? (
          <span className="text-xs text-muted-foreground">
            {lastCleanupPlan.summary?.suggestionCount ?? 0} suggestions ·{" "}
            {lastCleanupPlan.summary?.conflictCount ?? 0} conflicts
          </span>
        ) : null}
      </div>

      {error ? (
        <p className="mt-3 rounded-[18px] bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="mt-4 grid gap-2">
        {memories.length > 0 ? (
          memories.slice(0, 8).map((memory) => (
            <MemoryRow
              key={memory.id}
              memory={memory}
              selected={selectedIds.includes(memory.id)}
              busy={busyMemoryId === memory.id}
              onEdit={() => handleEdit(memory)}
              onDisable={() => void handleDisable(memory.id)}
              onToggleSelected={() => toggleSelected(memory.id)}
            />
          ))
        ) : (
          <div className="rounded-[22px] bg-background/70 px-4 py-8 text-center">
            <p className="text-sm font-medium text-foreground">
              No project memory
            </p>
          </div>
        )}
      </div>

      {suggestions.length > 0 || conflicts.length > 0 ? (
        <div className="mt-4 grid gap-2">
          {conflicts.slice(0, 3).map((conflict) => (
            <div
              key={conflict.id ?? conflict.conflictId ?? conflict.summary}
              className="rounded-[18px] bg-red-500/10 px-3 py-3 text-sm text-red-700 dark:text-red-300"
            >
              <div className="font-semibold">
                {conflict.conflictType?.replaceAll("_", " ") ?? "Conflict"}
              </div>
              <p className="mt-1 text-xs leading-5">
                {conflict.summary ?? "Conflicting memories need review."}
              </p>
            </div>
          ))}
          {suggestions.slice(0, 5).map((suggestion) => (
            <SuggestionRow
              key={
                suggestion.id ??
                `${suggestion.memoryId}:${suggestion.reasonCode}`
              }
              suggestion={suggestion}
              busy={busyMemoryId === suggestion.memoryId}
              onPrepare={() => handlePrepareSuggestion(suggestion)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
