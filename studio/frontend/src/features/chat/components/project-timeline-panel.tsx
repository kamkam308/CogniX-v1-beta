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
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { useNavigate } from "@tanstack/react-router";
import {
  AlertTriangleIcon,
  BotIcon,
  BriefcaseIcon,
  CpuIcon,
  FileTextIcon,
  GitBranchIcon,
  HistoryIcon,
  LinkIcon,
  MessageSquareIcon,
  RefreshCwIcon,
  SearchIcon,
  ShieldCheckIcon,
  SparklesIcon,
  TimerResetIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createTimelineEvent,
  listTimelineEvents,
  type TimelineEventRecord,
  type TimelineEventType,
  type TimelineEventPlan,
} from "../api/chat-api";
import type { SidebarItem } from "../hooks/use-chat-sidebar-items";

type TimelineFilter = "all" | TimelineEventType;
type TimelineDraftType = "auto" | TimelineEventType;

const TIMELINE_EVENT_OPTIONS: Array<{
  value: TimelineEventType;
  label: string;
  hint: string;
}> = [
  {
    value: "architecture_decision",
    label: "Architecture",
    hint: "Technical decisions and module contracts",
  },
  {
    value: "model_selected",
    label: "Model",
    hint: "Model selection, provider, routing",
  },
  {
    value: "document_added",
    label: "Document",
    hint: "New sources, files, project documents",
  },
  {
    value: "fine_tuning_started",
    label: "Training",
    hint: "Fine-tuning, QLoRA, evaluation starts",
  },
  {
    value: "critical_error",
    label: "Critical error",
    hint: "Blocked flow or important incident",
  },
  {
    value: "business_decision",
    label: "Business",
    hint: "Pricing, client, plan, product direction",
  },
];

function formatTimelineDate(value: string | null | undefined): string {
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

function sidebarItemTime(value: number | string | null | undefined): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function eventTypeLabel(value: string | null | undefined): string {
  return (
    TIMELINE_EVENT_OPTIONS.find((option) => option.value === value)?.label ??
    "Architecture"
  );
}

function eventTypeHint(value: string | null | undefined): string {
  return (
    TIMELINE_EVENT_OPTIONS.find((option) => option.value === value)?.hint ??
    "Project decision"
  );
}

function eventTypeClass(value: string | null | undefined): string {
  if (value === "critical_error") {
    return "bg-red-500/10 text-red-700 dark:text-red-300";
  }
  if (value === "model_selected") {
    return "bg-sky-500/10 text-sky-700 dark:text-sky-300";
  }
  if (value === "document_added") {
    return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (value === "fine_tuning_started") {
    return "bg-violet-500/10 text-violet-700 dark:text-violet-300";
  }
  if (value === "business_decision") {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-muted text-muted-foreground";
}

function EventTypeIcon({ type }: { type: string | null | undefined }) {
  const className = "size-4";
  const strokeWidth = 1.75;
  if (type === "critical_error") {
    return (
      <AlertTriangleIcon className={className} strokeWidth={strokeWidth} />
    );
  }
  if (type === "model_selected") {
    return <CpuIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "document_added") {
    return <FileTextIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "fine_tuning_started") {
    return <BotIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "business_decision") {
    return <BriefcaseIcon className={className} strokeWidth={strokeWidth} />;
  }
  return <GitBranchIcon className={className} strokeWidth={strokeWidth} />;
}

function sourceLabel(event: TimelineEventRecord): string | null {
  if (!event.sourceId) return null;
  const source = event.sourceType
    ? event.sourceType.replaceAll("_", " ")
    : "source";
  return `${source}: ${event.sourceId}`;
}

function canOpenSource(event: TimelineEventRecord): boolean {
  if (!event.sourceId) return false;
  const source = event.sourceType?.toLowerCase();
  return (
    !source || source === "chat" || source === "thread" || source === "compare"
  );
}

function TimelineEventRow({
  event,
  onOpenSource,
}: {
  event: TimelineEventRecord;
  onOpenSource: (event: TimelineEventRecord) => void;
}) {
  const linked = canOpenSource(event);
  const content = (
    <>
      <span className="absolute top-0 left-[22px] h-full w-px bg-border" />
      <span
        className={cn(
          "relative z-10 mt-1 flex size-11 shrink-0 items-center justify-center rounded-full",
          eventTypeClass(event.eventType),
        )}
      >
        <EventTypeIcon type={event.eventType} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            {event.title || "Timeline event"}
          </span>
          <span
            className={cn(
              "rounded-full px-2 py-1 text-[11px] font-medium",
              eventTypeClass(event.eventType),
            )}
          >
            {eventTypeLabel(event.eventType)}
          </span>
          {event.importance === "high" ? (
            <Badge
              variant="outline"
              className="bg-background text-muted-foreground"
            >
              high signal
            </Badge>
          ) : null}
        </span>
        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
          {event.summary || eventTypeHint(event.eventType)}
        </span>
        <span className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span>{formatTimelineDate(event.createdAt)}</span>
          {sourceLabel(event) ? (
            <>
              <span>·</span>
              <span className="inline-flex min-w-0 max-w-full items-center gap-1 truncate">
                <LinkIcon className="size-3.5 shrink-0" strokeWidth={1.75} />
                <span className="truncate">{sourceLabel(event)}</span>
              </span>
            </>
          ) : null}
        </span>
      </span>
    </>
  );

  const className =
    "relative flex w-full items-start gap-3 rounded-[20px] bg-background/70 px-3 py-3 text-left transition-colors hover:bg-background";

  if (linked) {
    return (
      <button
        type="button"
        onClick={() => onOpenSource(event)}
        className={className}
        aria-label={`Open source for ${event.title || "timeline event"}`}
      >
        {content}
      </button>
    );
  }

  return <div className={className}>{content}</div>;
}

export function ProjectTimelinePanel({
  projectId,
  projectName,
  items,
}: {
  projectId: string;
  projectName: string;
  items: SidebarItem[];
}) {
  const navigate = useNavigate();
  const [events, setEvents] = useState<TimelineEventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<TimelineFilter>("all");
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [draftType, setDraftType] = useState<TimelineDraftType>("auto");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftSummary, setDraftSummary] = useState("");
  const [lastPlan, setLastPlan] = useState<TimelineEventPlan | null>(null);

  const latestChat = useMemo(() => {
    return [...items]
      .filter((item) => item.type === "single")
      .sort((left, right) => {
        return (
          sidebarItemTime(right.createdAt) - sidebarItemTime(left.createdAt)
        );
      })[0];
  }, [items]);

  const highSignalCount = useMemo(
    () => events.filter((event) => event.importance === "high").length,
    [events],
  );
  const linkedCount = useMemo(
    () => events.filter((event) => event.sourceId).length,
    [events],
  );

  const loadTimeline = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const nextEvents = await listTimelineEvents({
          projectId,
          eventType: filter === "all" ? null : filter,
          query: appliedQuery || null,
        });
        setEvents(nextEvents);
        if (showToast) {
          toast.success("Timeline refreshed.");
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to load Timeline.";
        setError(message);
        if (showToast) {
          toast.error(message);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [appliedQuery, filter, projectId],
  );

  useEffect(() => {
    setLoading(true);
    void loadTimeline();
  }, [loadTimeline]);

  const addEventToList = useCallback((event: TimelineEventRecord | null) => {
    if (!event) return;
    setEvents((current) => [
      event,
      ...current.filter((candidate) => candidate.id !== event.id),
    ]);
  }, []);

  const handleRecord = useCallback(async () => {
    const title = draftTitle.trim();
    if (!title) {
      toast.error("Add a title before recording the event.");
      return;
    }
    setSaving(true);
    try {
      const result = await createTimelineEvent({
        projectId,
        eventType: draftType === "auto" ? null : draftType,
        title,
        summary: draftSummary.trim() || null,
        metadata: {
          projectName,
          source: "project_timeline_panel",
          recordedManually: true,
        },
        storeEvent: true,
      });
      addEventToList(result.event);
      setLastPlan(result.timelineEventPlan);
      setDraftTitle("");
      setDraftSummary("");
      setDraftType("auto");
      toast.success("Timeline event recorded.");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to record event.",
      );
    } finally {
      setSaving(false);
    }
  }, [
    addEventToList,
    draftSummary,
    draftTitle,
    draftType,
    projectId,
    projectName,
  ]);

  const handleCaptureLatestChat = useCallback(async () => {
    if (!latestChat) {
      toast.error("No project chat is available to capture yet.");
      return;
    }
    setSaving(true);
    try {
      const result = await createTimelineEvent({
        projectId,
        title: `Chat captured: ${latestChat.title || projectName}`,
        summary: `Important discussion captured from ${projectName}.`,
        sourceType: "chat",
        sourceId: latestChat.id,
        metadata: {
          projectName,
          source: "project_timeline_panel",
          capturedFrom: "latest_project_chat",
          chatTitle: latestChat.title,
        },
        storeEvent: true,
      });
      addEventToList(result.event);
      setLastPlan(result.timelineEventPlan);
      toast.success("Latest chat linked to Timeline.");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to capture chat.",
      );
    } finally {
      setSaving(false);
    }
  }, [addEventToList, latestChat, projectId, projectName]);

  const handleOpenSource = useCallback(
    (event: TimelineEventRecord) => {
      if (!event.sourceId) return;
      const source = event.sourceType?.toLowerCase();
      if (source === "compare") {
        navigate({
          to: "/chat",
          search: { compare: event.sourceId, project: projectId },
        });
        return;
      }
      navigate({
        to: "/chat",
        search: { thread: event.sourceId, project: projectId },
      });
    },
    [navigate, projectId],
  );

  const activeClassifier =
    lastPlan?.classification?.eventType &&
    eventTypeLabel(lastPlan.classification.eventType);

  return (
    <section
      className="mt-8 rounded-[26px] bg-muted/30 px-5 py-5"
      data-testid="project-timeline-panel"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex size-10 items-center justify-center rounded-full bg-background text-foreground">
              <HistoryIcon className="size-5" strokeWidth={1.75} />
            </span>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-foreground">
                Timeline
              </h2>
              <p className="text-xs leading-5 text-muted-foreground">
                Key project decisions, sources, model choices, incidents, and
                training milestones.
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="bg-background">
              {events.length} events
            </Badge>
            <Badge variant="outline" className="bg-background">
              {highSignalCount} high signal
            </Badge>
            <Badge variant="outline" className="bg-background">
              {linkedCount} linked
            </Badge>
            <Badge
              variant="outline"
              className="bg-background text-muted-foreground"
            >
              no generation
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={saving || !latestChat}
            onClick={handleCaptureLatestChat}
            className="gap-2 rounded-full bg-background"
          >
            <MessageSquareIcon className="size-4" strokeWidth={1.75} />
            Capture latest chat
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={refreshing}
            onClick={() => void loadTimeline(true)}
            className="gap-2 rounded-full"
          >
            <RefreshCwIcon
              className={cn("size-4", refreshing && "animate-spin")}
              strokeWidth={1.75}
            />
            Refresh
          </Button>
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="rounded-[22px] bg-background/60 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <SparklesIcon className="size-4" strokeWidth={1.75} />
            Record a milestone
          </div>
          <div className="mt-4 space-y-3">
            <Select
              value={draftType}
              onValueChange={(value) =>
                setDraftType(value as TimelineDraftType)
              }
            >
              <SelectTrigger className="h-10 rounded-full bg-background">
                <SelectValue placeholder="Event type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto classify</SelectItem>
                {TIMELINE_EVENT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              value={draftTitle}
              onChange={(event) => setDraftTitle(event.target.value)}
              placeholder="Architecture backend validated"
              className="h-10 rounded-full bg-background"
            />
            <Textarea
              value={draftSummary}
              onChange={(event) => setDraftSummary(event.target.value)}
              placeholder="Short context, decision, or source link..."
              className="min-h-24 rounded-[18px] bg-background"
            />
            <Button
              type="button"
              disabled={saving}
              onClick={() => void handleRecord()}
              className="w-full gap-2 rounded-full"
            >
              <ShieldCheckIcon className="size-4" strokeWidth={1.75} />
              Record event
            </Button>
          </div>
          {lastPlan ? (
            <div className="mt-4 rounded-[18px] bg-muted/50 px-3 py-3 text-xs leading-5 text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2 text-foreground">
                <TimerResetIcon className="size-4" strokeWidth={1.75} />
                <span className="font-semibold">
                  Classifier: {activeClassifier || "ready"}
                </span>
              </div>
              <p className="mt-1">
                TimelineService stored the event without model loading, tool
                execution, or generation.
              </p>
            </div>
          ) : null}
        </div>

        <div className="rounded-[22px] bg-background/60 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative min-w-0 flex-1">
              <SearchIcon
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.75}
              />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    setAppliedQuery(query.trim());
                  }
                }}
                placeholder="Search decisions, errors, documents..."
                className="h-10 rounded-full bg-background pl-9"
              />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Select
                value={filter}
                onValueChange={(value) => setFilter(value as TimelineFilter)}
              >
                <SelectTrigger className="h-10 w-[150px] rounded-full bg-background">
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  {TIMELINE_EVENT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setAppliedQuery(query.trim())}
                className="rounded-full bg-background"
              >
                Search
              </Button>
            </div>
          </div>

          {error ? (
            <div className="mt-4 rounded-[18px] bg-destructive/10 px-3 py-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <div className="mt-4 space-y-3">
            {loading ? (
              <>
                <Skeleton className="h-24 rounded-[20px]" />
                <Skeleton className="h-24 rounded-[20px]" />
                <Skeleton className="h-24 rounded-[20px]" />
              </>
            ) : events.length > 0 ? (
              events.map((event) => (
                <TimelineEventRow
                  key={event.id}
                  event={event}
                  onOpenSource={handleOpenSource}
                />
              ))
            ) : (
              <div className="rounded-[20px] bg-background/70 px-4 py-8 text-center">
                <HistoryIcon
                  className="mx-auto size-6 text-muted-foreground"
                  strokeWidth={1.75}
                />
                <p className="mt-3 text-sm font-semibold text-foreground">
                  No timeline events yet
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Record a milestone or capture the latest project chat to start
                  the project history.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
