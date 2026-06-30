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
import {
  Activity,
  AppWindow,
  Bot,
  CalendarClock,
  CheckCircle2,
  Code2,
  FilePlus2,
  ImageIcon,
  LibraryBig,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Wand2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  asArray,
  asRecord,
  cognixJson,
  jsonBody,
  readBoolean,
  readNumber,
  readString,
  readStringList,
  type JsonRecord,
} from "./api";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "ghost" | "link";

const LIBRARY_KINDS = [
  "document",
  "dataset",
  "model",
  "lora_adapter",
  "image",
  "prompt",
  "persona",
  "workflow",
  "report",
  "app",
  "plugin",
  "skill",
  "directive",
  "file",
  "video",
  "other",
] as const;

const IMAGE_MODES = ["generate", "edit", "analyze", "variants"] as const;
const PRIVACY_LEVELS = ["private", "project", "organization"] as const;
const SHARE_SCOPES = ["private", "project", "organization", "public_readonly"] as const;
const CODEX_RUN_MODES = ["guided", "night"] as const;

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function useCognixResource(path: string) {
  const [data, setData] = useState<JsonRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void cognixJson(path)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, reloadTick]);

  const reload = useCallback(() => setReloadTick((value) => value + 1), []);
  return { data, error, loading, reload };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected CogniX error";
}

function notifyError(title: string, error: unknown) {
  toast.error(title, { description: errorMessage(error) });
}

function labelize(value: unknown): string {
  const text = readString(value, "unknown").replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatDate(value: unknown): string {
  const text = readString(value);
  if (!text) return "No date";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return dateFormatter.format(date);
}

function formatBytes(value: unknown): string {
  const bytes = readNumber(value);
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function recordId(record: JsonRecord, fallback: string): string {
  return readString(record.id) || readString(record.gptId) || readString(record.appId) || fallback;
}

function getCreatedAt(record: JsonRecord): unknown {
  return (
    record.created_at ??
    record.createdAt ??
    record.updated_at ??
    record.updatedAt ??
    record.finished_at ??
    record.finishedAt
  );
}

function riskVariant(value: unknown): BadgeVariant {
  const risk = readString(value).toLowerCase();
  if (risk === "critical" || risk === "high") return "destructive";
  if (risk === "medium") return "secondary";
  return "outline";
}

function statusVariant(value: unknown): BadgeVariant {
  const status = readString(value).toLowerCase();
  if (["failed", "error", "blocked", "missing_permissions", "cancelled"].includes(status)) {
    return "destructive";
  }
  if (["connected", "active", "ready", "complete", "available"].includes(status)) {
    return "default";
  }
  return "outline";
}

function ModuleShell({
  title,
  icon: Icon,
  actions,
  children,
}: {
  title: string;
  icon: LucideIcon;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-5 py-8 font-heading sm:px-8 lg:px-10">
      <header className="flex flex-col gap-5 border-b border-border/70 pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-foreground shadow-sm">
            <Icon className="size-5" strokeWidth={1.8} />
          </span>
          <div className="min-w-0">
            <h1 className="text-[28px] font-semibold leading-tight tracking-normal text-foreground sm:text-[32px]">
              {title}
            </h1>
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </main>
  );
}

function StatGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{children}</div>;
}

function Stat({
  label,
  value,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  icon: LucideIcon;
  tone?: "neutral" | "green" | "blue" | "amber";
}) {
  const toneClass = {
    neutral: "bg-muted text-muted-foreground",
    green: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    blue: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
    amber: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  }[tone];
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
        <span className={cn("flex size-8 items-center justify-center rounded-md", toneClass)}>
          <Icon className="size-4" strokeWidth={1.8} />
        </span>
      </div>
      <div className="mt-3 text-2xl font-semibold leading-none text-foreground">{value}</div>
    </div>
  );
}

function Panel({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-card", className)}>
      <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function LoadingPanels() {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="rounded-lg border border-border bg-card p-4">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="mt-4 h-4 w-full" />
          <Skeleton className="mt-2 h-4 w-3/4" />
          <Skeleton className="mt-6 h-8 w-24 rounded-md" />
        </div>
      ))}
    </div>
  );
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
      <span className="min-w-0 break-words">{message}</span>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="size-4" />
        Retry
      </Button>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex min-h-32 items-center justify-center rounded-lg border border-dashed border-border bg-background/40 p-6 text-center text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function FieldLabel({ children }: { children: ReactNode }) {
  return <label className="text-xs font-medium text-muted-foreground">{children}</label>;
}

function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1 min-w-0 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function JsonDetails({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="rounded-lg border border-border bg-background/40">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">{title}</summary>
      <pre className="max-h-80 overflow-auto border-t border-border/70 p-3 text-xs leading-5 text-muted-foreground">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </details>
  );
}

function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative min-w-0">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-9 rounded-lg pl-9"
      />
    </div>
  );
}

export function PulsePage() {
  const { data, error, loading, reload } = useCognixResource("/api/cognix/pulse");
  const [hours, setHours] = useState("24");
  const [previewPlan, setPreviewPlan] = useState<JsonRecord | null>(null);
  const [busy, setBusy] = useState<"preview" | "generate" | null>(null);
  const reports = asArray(data?.reports);
  const blueprint = asRecord(data?.blueprint);
  const sources = asArray(blueprint.sources);
  const latestReport = reports[0] ?? null;
  const previewEvents = asArray(previewPlan?.events);
  const previewSummary = asRecord(previewPlan?.summary);

  async function previewPulse() {
    setBusy("preview");
    try {
      const payload = await cognixJson(`/api/cognix/pulse/preview?hours=${encodeURIComponent(hours)}`);
      setPreviewPlan(asRecord(payload.pulsePlan));
      toast.success("Pulse preview ready");
    } catch (err) {
      notifyError("Pulse preview failed", err);
    } finally {
      setBusy(null);
    }
  }

  async function generatePulse() {
    setBusy("generate");
    try {
      const payload = await cognixJson(`/api/cognix/pulse/generate?hours=${encodeURIComponent(hours)}`, {
        method: "POST",
      });
      setPreviewPlan(asRecord(payload.pulsePlan));
      toast.success("Pulse report generated");
      reload();
    } catch (err) {
      notifyError("Pulse generation failed", err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <ModuleShell
      title="Pulse"
      icon={Activity}
      actions={
        <>
          <Input
            value={hours}
            onChange={(event) => setHours(event.target.value.replace(/[^\d]/g, "").slice(0, 3))}
            className="h-9 w-20 rounded-lg"
            aria-label="Pulse hours"
          />
          <Button variant="outline" onClick={() => void previewPulse()} disabled={busy !== null}>
            {busy === "preview" ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
            Preview
          </Button>
          <Button onClick={() => void generatePulse()} disabled={busy !== null}>
            {busy === "generate" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            Generate
          </Button>
        </>
      }
    >
      {loading ? <LoadingPanels /> : error ? <ErrorPanel message={error} onRetry={reload} /> : (
        <>
          <StatGrid>
            <Stat label="Reports" value={reports.length} icon={Activity} tone="blue" />
            <Stat label="Sources" value={sources.length} icon={LibraryBig} />
            <Stat label="Preview events" value={previewEvents.length || readNumber(previewSummary.eventCount)} icon={Search} tone="green" />
            <Stat label="Critical" value={readNumber(previewSummary.criticalCount)} icon={ShieldCheck} tone="amber" />
          </StatGrid>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <Panel title="Timeline">
              {previewEvents.length > 0 ? (
                <div className="space-y-3">
                  {previewEvents.map((event, index) => (
                    <div key={recordId(event, String(index))} className="rounded-lg border border-border bg-background p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={statusVariant(event.priority)}>{labelize(event.priority)}</Badge>
                        <Badge variant="outline">{labelize(event.sourceType)}</Badge>
                        <span className="text-xs text-muted-foreground">{formatDate(event.createdAt)}</span>
                      </div>
                      <h3 className="mt-3 text-sm font-semibold text-foreground">{readString(event.title, "Activity")}</h3>
                      <p className="mt-1 line-clamp-3 text-sm leading-6 text-muted-foreground">{readString(event.summary)}</p>
                    </div>
                  ))}
                </div>
              ) : reports.length > 0 ? (
                <div className="space-y-3">
                  {reports.map((report, index) => (
                    <div key={recordId(report, String(index))} className="rounded-lg border border-border bg-background p-3">
                      <h3 className="text-sm font-semibold text-foreground">{readString(report.title, "Pulse report")}</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">{readString(report.summary)}</p>
                      <p className="mt-3 text-xs text-muted-foreground">{formatDate(getCreatedAt(report))}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState label="No Pulse activity yet." />
              )}
            </Panel>
            <Panel title="Latest report">
              {latestReport ? (
                <div className="space-y-4">
                  <KeyValue label="Title" value={readString(latestReport.title, "Pulse report")} />
                  <KeyValue label="Summary" value={readString(latestReport.summary)} />
                  <KeyValue label="Topics" value={readStringList(latestReport.topics).join(", ") || "None"} />
                  <JsonDetails title="Blueprint" value={blueprint} />
                </div>
              ) : (
                <JsonDetails title="Blueprint" value={blueprint} />
              )}
            </Panel>
          </div>
        </>
      )}
    </ModuleShell>
  );
}

export function LibraryPage() {
  const { data, error, loading, reload } = useCognixResource("/api/cognix/library");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<string>("all");
  const [form, setForm] = useState({
    kind: "document",
    name: "",
    source: "manual",
    uri: "",
  });
  const [creating, setCreating] = useState(false);
  const items = asArray(data?.items);
  const summary = asRecord(data?.summary);

  const visibleItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      const itemKind = readString(item.kind, "other");
      if (kind !== "all" && itemKind !== kind) return false;
      if (!needle) return true;
      return [item.name, item.source, item.uri, itemKind]
        .map((value) => readString(value).toLowerCase())
        .some((value) => value.includes(needle));
    });
  }, [items, kind, query]);

  async function createItem(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) return;
    setCreating(true);
    try {
      await cognixJson("/api/cognix/library", {
        method: "POST",
        body: jsonBody({
          kind: form.kind,
          name,
          source: form.source.trim() || "manual",
          uri: form.uri.trim() || null,
        }),
      });
      setForm((current) => ({ ...current, name: "", uri: "" }));
      toast.success("Library asset added");
      reload();
    } catch (err) {
      notifyError("Library write failed", err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <ModuleShell title="Library" icon={LibraryBig}>
      {loading ? <LoadingPanels /> : error ? <ErrorPanel message={error} onRetry={reload} /> : (
        <>
          <StatGrid>
            <Stat label="Assets" value={items.length} icon={LibraryBig} tone="blue" />
            <Stat label="Visible" value={visibleItems.length} icon={Search} />
            <Stat label="RAG eligible" value={readNumber(summary.ragEligibleCount)} icon={ShieldCheck} tone="green" />
            <Stat label="Model assets" value={readNumber(summary.modelAssetCount)} icon={Bot} tone="amber" />
          </StatGrid>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.75fr_1.25fr]">
            <Panel title="Add asset">
              <form className="space-y-4" onSubmit={(event) => void createItem(event)}>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <FieldLabel>Kind</FieldLabel>
                    <Select value={form.kind} onValueChange={(value) => setForm((current) => ({ ...current, kind: value }))}>
                      <SelectTrigger className="w-full rounded-lg">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {LIBRARY_KINDS.map((item) => (
                          <SelectItem key={item} value={item}>{labelize(item)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <FieldLabel>Source</FieldLabel>
                    <Input value={form.source} onChange={(event) => setForm((current) => ({ ...current, source: event.target.value }))} className="rounded-lg" />
                  </div>
                </div>
                <div className="space-y-2">
                  <FieldLabel>Name</FieldLabel>
                  <Input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="rounded-lg" required />
                </div>
                <div className="space-y-2">
                  <FieldLabel>URI</FieldLabel>
                  <Input value={form.uri} onChange={(event) => setForm((current) => ({ ...current, uri: event.target.value }))} className="rounded-lg" />
                </div>
                <Button type="submit" disabled={creating}>
                  {creating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                  Add
                </Button>
              </form>
            </Panel>
            <Panel
              title="Assets"
              action={
                <div className="flex flex-wrap items-center gap-2">
                  <SearchInput value={query} onChange={setQuery} placeholder="Search" />
                  <Select value={kind} onValueChange={setKind}>
                    <SelectTrigger className="w-40 rounded-lg">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All kinds</SelectItem>
                      {LIBRARY_KINDS.map((item) => (
                        <SelectItem key={item} value={item}>{labelize(item)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              }
            >
              {visibleItems.length > 0 ? (
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {visibleItems.map((item, index) => (
                    <div key={recordId(item, String(index))} className="rounded-lg border border-border bg-background p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{labelize(item.kind)}</Badge>
                        <Badge variant="secondary">{readString(item.source, "manual")}</Badge>
                      </div>
                      <h3 className="mt-3 line-clamp-2 text-sm font-semibold text-foreground">{readString(item.name, "Untitled")}</h3>
                      <p className="mt-2 truncate text-xs text-muted-foreground">{readString(item.uri, "No URI")}</p>
                      <div className="mt-4 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>{formatBytes(item.size_bytes ?? item.sizeBytes)}</span>
                        <span>{formatDate(getCreatedAt(item))}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState label="No Library assets match this view." />
              )}
            </Panel>
          </div>
        </>
      )}
    </ModuleShell>
  );
}

export function ScheduledPage() {
  const { data, error, loading, reload } = useCognixResource("/api/cognix/scheduled-tasks");
  const [form, setForm] = useState({
    title: "",
    prompt: "",
    scheduleText: "daily 09:00",
  });
  const [busy, setBusy] = useState<string | null>(null);
  const tasks = asArray(data?.tasks);
  const runs = asArray(data?.runs);
  const activeCount = tasks.filter((task) => readString(task.status, "active") === "active").length;

  async function createTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.title.trim() || !form.prompt.trim() || !form.scheduleText.trim()) return;
    setBusy("create");
    try {
      await cognixJson("/api/cognix/scheduled-tasks", {
        method: "POST",
        body: jsonBody({
          title: form.title.trim(),
          prompt: form.prompt.trim(),
          schedule_text: form.scheduleText.trim(),
        }),
      });
      setForm({ title: "", prompt: "", scheduleText: "daily 09:00" });
      toast.success("Scheduled task created");
      reload();
    } catch (err) {
      notifyError("Scheduled task failed", err);
    } finally {
      setBusy(null);
    }
  }

  async function updateStatus(taskId: string, status: string) {
    setBusy(`${taskId}:${status}`);
    try {
      await cognixJson(`/api/cognix/scheduled-tasks/${encodeURIComponent(taskId)}`, {
        method: "PATCH",
        body: jsonBody({ status }),
      });
      toast.success("Task updated");
      reload();
    } catch (err) {
      notifyError("Task update failed", err);
    } finally {
      setBusy(null);
    }
  }

  async function runTask(taskId: string) {
    setBusy(`${taskId}:run`);
    try {
      await cognixJson(`/api/cognix/scheduled-tasks/${encodeURIComponent(taskId)}/run`, {
        method: "POST",
      });
      toast.success("Task run recorded");
      reload();
    } catch (err) {
      notifyError("Task run failed", err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <ModuleShell title="Scheduled" icon={CalendarClock}>
      {loading ? <LoadingPanels /> : error ? <ErrorPanel message={error} onRetry={reload} /> : (
        <>
          <StatGrid>
            <Stat label="Tasks" value={tasks.length} icon={CalendarClock} tone="blue" />
            <Stat label="Active" value={activeCount} icon={Play} tone="green" />
            <Stat label="Runs" value={runs.length} icon={Activity} />
            <Stat label="Failed runs" value={runs.filter((run) => readString(run.status) === "failed").length} icon={XCircle} tone="amber" />
          </StatGrid>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.75fr_1.25fr]">
            <Panel title="New task">
              <form className="space-y-4" onSubmit={(event) => void createTask(event)}>
                <div className="space-y-2">
                  <FieldLabel>Title</FieldLabel>
                  <Input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} className="rounded-lg" required />
                </div>
                <div className="space-y-2">
                  <FieldLabel>Schedule</FieldLabel>
                  <Input value={form.scheduleText} onChange={(event) => setForm((current) => ({ ...current, scheduleText: event.target.value }))} className="rounded-lg" required />
                </div>
                <div className="space-y-2">
                  <FieldLabel>Prompt</FieldLabel>
                  <Textarea value={form.prompt} onChange={(event) => setForm((current) => ({ ...current, prompt: event.target.value }))} className="min-h-28 rounded-lg" fieldSizing="fixed" required />
                </div>
                <Button type="submit" disabled={busy === "create"}>
                  {busy === "create" ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                  Create
                </Button>
              </form>
            </Panel>
            <Panel title="Tasks">
              {tasks.length > 0 ? (
                <div className="space-y-3">
                  {tasks.map((task, index) => {
                    const taskId = recordId(task, String(index));
                    const status = readString(task.status, "active");
                    const actionBusy = busy?.startsWith(`${taskId}:`) ?? false;
                    return (
                      <div key={taskId} className="rounded-lg border border-border bg-background p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant={statusVariant(status)}>{labelize(status)}</Badge>
                              <Badge variant="outline">{readString(task.schedule_text ?? task.scheduleText, "custom")}</Badge>
                            </div>
                            <h3 className="mt-3 line-clamp-2 text-sm font-semibold text-foreground">{readString(task.title, "Scheduled task")}</h3>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button size="icon" variant="outline" title="Run" disabled={actionBusy} onClick={() => void runTask(taskId)}>
                              {busy === `${taskId}:run` ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                            </Button>
                            {status === "active" ? (
                              <Button size="icon" variant="outline" title="Pause" disabled={actionBusy} onClick={() => void updateStatus(taskId, "paused")}>
                                {busy === `${taskId}:paused` ? <Loader2 className="size-4 animate-spin" /> : <Pause className="size-4" />}
                              </Button>
                            ) : (
                              <Button size="icon" variant="outline" title="Activate" disabled={actionBusy} onClick={() => void updateStatus(taskId, "active")}>
                                {busy === `${taskId}:active` ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                              </Button>
                            )}
                          </div>
                        </div>
                        <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">{readString(task.prompt)}</p>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyState label="No scheduled tasks yet." />
              )}
            </Panel>
          </div>
        </>
      )}
    </ModuleShell>
  );
}

export function AppsPage() {
  const { data, error, loading, reload } = useCognixResource("/api/cognix/apps");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const registry = asRecord(data?.appRegistry);
  const apps = asArray(registry.apps);
  const summary = asRecord(registry.summary);
  const visibleApps = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return apps;
    return apps.filter((app) =>
      [app.name, app.category, app.description, app.id]
        .map((value) => readString(value).toLowerCase())
        .some((value) => value.includes(needle)),
    );
  }, [apps, query]);

  async function setConnection(app: JsonRecord, status: "connected" | "disabled") {
    const appId = readString(app.id);
    if (!appId) return;
    setBusy(appId);
    try {
      await cognixJson("/api/cognix/apps/connections", {
        method: "POST",
        body: jsonBody({
          app_id: appId,
          app_name: readString(app.name, appId),
          status,
        }),
      });
      toast.success(status === "connected" ? "App connected" : "App disabled");
      reload();
    } catch (err) {
      notifyError("App update failed", err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <ModuleShell
      title="Apps"
      icon={AppWindow}
      actions={<SearchInput value={query} onChange={setQuery} placeholder="Search apps" />}
    >
      {loading ? <LoadingPanels /> : error ? <ErrorPanel message={error} onRetry={reload} /> : (
        <>
          <StatGrid>
            <Stat label="Apps" value={readNumber(summary.appCount, apps.length)} icon={AppWindow} tone="blue" />
            <Stat label="Connected" value={readNumber(summary.connectedCount)} icon={CheckCircle2} tone="green" />
            <Stat label="Visible" value={visibleApps.length} icon={Search} />
            <Stat label="High risk" value={readNumber(asRecord(summary.byRisk).high) + readNumber(asRecord(summary.byRisk).critical)} icon={ShieldCheck} tone="amber" />
          </StatGrid>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {visibleApps.map((app, index) => {
              const appId = recordId(app, String(index));
              const connection = asRecord(app.connection);
              const connected = readBoolean(connection.connected);
              const permissions = asArray(app.requestedPermissions);
              return (
                <div key={appId} className="flex min-h-52 flex-col rounded-lg border border-border bg-card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={statusVariant(connection.status)}>{connected ? "Connected" : labelize(connection.status || "available")}</Badge>
                        <Badge variant={riskVariant(app.riskLevel)}>{labelize(app.riskLevel)} risk</Badge>
                      </div>
                      <h3 className="mt-3 truncate text-sm font-semibold text-foreground">{readString(app.name, appId)}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">{readString(app.category, "Integration")}</p>
                    </div>
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      <AppWindow className="size-4" />
                    </span>
                  </div>
                  <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">{readString(app.description)}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {permissions.slice(0, 4).map((permission, permissionIndex) => (
                      <Badge key={`${appId}-${permissionIndex}`} variant={riskVariant(permission.riskLevel)}>
                        {readString(permission.permission, "permission")}
                      </Badge>
                    ))}
                  </div>
                  <div className="mt-auto pt-5">
                    <Button
                      variant={connected ? "outline" : "default"}
                      className="w-full"
                      disabled={busy === appId}
                      onClick={() => void setConnection(app, connected ? "disabled" : "connected")}
                    >
                      {busy === appId ? <Loader2 className="size-4 animate-spin" /> : connected ? <Pause className="size-4" /> : <CheckCircle2 className="size-4" />}
                      {connected ? "Disable" : "Connect"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
          {visibleApps.length === 0 ? <EmptyState label="No apps match this search." /> : null}
        </>
      )}
    </ModuleShell>
  );
}

export function GPTsPage() {
  const { data, error, loading, reload } = useCognixResource("/api/cognix/gpts");
  const [form, setForm] = useState({
    name: "",
    description: "",
    instructions: "",
    preferredModel: "",
    allowedTools: "project_context, memory_read, rag_retrieval",
    privacyLevel: "private",
    shareScope: "private",
  });
  const [creating, setCreating] = useState(false);
  const gpts = asArray(data?.gpts);

  async function createGpt(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.name.trim()) return;
    setCreating(true);
    try {
      await cognixJson("/api/cognix/gpts/plan", {
        method: "POST",
        body: jsonBody({
          name: form.name.trim(),
          description: form.description.trim() || null,
          instructions: form.instructions.trim() || null,
          preferredModel: form.preferredModel.trim() || null,
          allowedTools: splitCsv(form.allowedTools),
          privacyLevel: form.privacyLevel,
          shareScope: form.shareScope,
          storeGpt: true,
        }),
      });
      setForm((current) => ({ ...current, name: "", description: "", instructions: "" }));
      toast.success("GPT saved");
      reload();
    } catch (err) {
      notifyError("GPT save failed", err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <ModuleShell title="GPTs" icon={Bot}>
      {loading ? <LoadingPanels /> : error ? <ErrorPanel message={error} onRetry={reload} /> : (
        <>
          <StatGrid>
            <Stat label="GPTs" value={gpts.length} icon={Bot} tone="blue" />
            <Stat label="Private" value={gpts.filter((gpt) => readString(asRecord(gpt.config).privacyLevel ?? gpt.privacy_level) === "private").length} icon={ShieldCheck} tone="green" />
            <Stat label="Project scoped" value={gpts.filter((gpt) => Boolean(readString(asRecord(gpt.config).projectId ?? gpt.project_id))).length} icon={LibraryBig} />
            <Stat label="With tools" value={gpts.filter((gpt) => readStringList(asRecord(gpt.config).allowedTools).length > 0).length} icon={Wand2} tone="amber" />
          </StatGrid>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.8fr_1.2fr]">
            <Panel title="New GPT">
              <form className="space-y-4" onSubmit={(event) => void createGpt(event)}>
                <div className="space-y-2">
                  <FieldLabel>Name</FieldLabel>
                  <Input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="rounded-lg" required />
                </div>
                <div className="space-y-2">
                  <FieldLabel>Description</FieldLabel>
                  <Input value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} className="rounded-lg" />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <FieldLabel>Privacy</FieldLabel>
                    <Select value={form.privacyLevel} onValueChange={(value) => setForm((current) => ({ ...current, privacyLevel: value }))}>
                      <SelectTrigger className="w-full rounded-lg"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {PRIVACY_LEVELS.map((item) => <SelectItem key={item} value={item}>{labelize(item)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <FieldLabel>Share</FieldLabel>
                    <Select value={form.shareScope} onValueChange={(value) => setForm((current) => ({ ...current, shareScope: value }))}>
                      <SelectTrigger className="w-full rounded-lg"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {SHARE_SCOPES.map((item) => <SelectItem key={item} value={item}>{labelize(item)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-2">
                  <FieldLabel>Preferred model</FieldLabel>
                  <Input value={form.preferredModel} onChange={(event) => setForm((current) => ({ ...current, preferredModel: event.target.value }))} className="rounded-lg" />
                </div>
                <div className="space-y-2">
                  <FieldLabel>Allowed tools</FieldLabel>
                  <Input value={form.allowedTools} onChange={(event) => setForm((current) => ({ ...current, allowedTools: event.target.value }))} className="rounded-lg" />
                </div>
                <div className="space-y-2">
                  <FieldLabel>Instructions</FieldLabel>
                  <Textarea value={form.instructions} onChange={(event) => setForm((current) => ({ ...current, instructions: event.target.value }))} className="min-h-32 rounded-lg" fieldSizing="fixed" />
                </div>
                <Button type="submit" disabled={creating}>
                  {creating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                  Save
                </Button>
              </form>
            </Panel>
            <Panel title="Saved GPTs">
              {gpts.length > 0 ? (
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {gpts.map((gpt, index) => {
                    const config = asRecord(gpt.config);
                    const name = readString(config.name ?? gpt.name, "CogniX GPT");
                    const allowedTools = readStringList(config.allowedTools ?? gpt.allowed_tools);
                    return (
                      <div key={recordId(gpt, String(index))} className="rounded-lg border border-border bg-background p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="default">{labelize(config.privacyLevel ?? gpt.privacy_level ?? "private")}</Badge>
                          <Badge variant="outline">{labelize(config.shareScope ?? gpt.share_scope ?? "private")}</Badge>
                        </div>
                        <h3 className="mt-3 truncate text-sm font-semibold text-foreground">{name}</h3>
                        <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">{readString(config.description ?? gpt.description)}</p>
                        <div className="mt-4 flex flex-wrap gap-2">
                          {allowedTools.slice(0, 5).map((tool) => (
                            <Badge key={tool} variant="secondary">{tool}</Badge>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyState label="No GPTs saved yet." />
              )}
            </Panel>
          </div>
        </>
      )}
    </ModuleShell>
  );
}

export function ImagesPage() {
  const { data, error, loading, reload } = useCognixResource("/api/cognix/images");
  const [form, setForm] = useState({
    prompt: "",
    model: "",
    mode: "generate",
    variantCount: "1",
  });
  const [creating, setCreating] = useState(false);
  const images = asArray(data?.images);
  const summary = asRecord(data?.summary);
  const blueprint = asRecord(data?.blueprint);
  const runtimePolicy = asRecord(blueprint.runtimePolicy);

  async function createImageRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.prompt.trim()) return;
    setCreating(true);
    try {
      await cognixJson("/api/cognix/images", {
        method: "POST",
        body: jsonBody({
          prompt: form.prompt.trim(),
          model: form.model.trim() || null,
          mode: form.mode,
          variantCount: Math.max(1, Math.min(Number.parseInt(form.variantCount, 10) || 1, 8)),
        }),
      });
      setForm((current) => ({ ...current, prompt: "" }));
      toast.success("Image request recorded");
      reload();
    } catch (err) {
      notifyError("Image request failed", err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <ModuleShell title="Images" icon={ImageIcon}>
      {loading ? <LoadingPanels /> : error ? <ErrorPanel message={error} onRetry={reload} /> : (
        <>
          <StatGrid>
            <Stat label="Requests" value={images.length} icon={ImageIcon} tone="blue" />
            <Stat label="Generated" value={readNumber(summary.generatedCount)} icon={Sparkles} tone="green" />
            <Stat label="Needs review" value={readNumber(summary.needsReviewCount)} icon={ShieldCheck} tone="amber" />
            <Stat label="Runtime" value={readBoolean(runtimePolicy.actualGenerationEnabled) ? "live" : "planned"} icon={Wand2} />
          </StatGrid>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.8fr_1.2fr]">
            <Panel title="New image request">
              <form className="space-y-4" onSubmit={(event) => void createImageRequest(event)}>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="space-y-2">
                    <FieldLabel>Mode</FieldLabel>
                    <Select value={form.mode} onValueChange={(value) => setForm((current) => ({ ...current, mode: value }))}>
                      <SelectTrigger className="w-full rounded-lg"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {IMAGE_MODES.map((item) => <SelectItem key={item} value={item}>{labelize(item)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <FieldLabel>Variants</FieldLabel>
                    <Input value={form.variantCount} onChange={(event) => setForm((current) => ({ ...current, variantCount: event.target.value.replace(/[^\d]/g, "").slice(0, 1) }))} className="rounded-lg" />
                  </div>
                  <div className="space-y-2">
                    <FieldLabel>Model</FieldLabel>
                    <Input value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} className="rounded-lg" />
                  </div>
                </div>
                <div className="space-y-2">
                  <FieldLabel>Prompt</FieldLabel>
                  <Textarea value={form.prompt} onChange={(event) => setForm((current) => ({ ...current, prompt: event.target.value }))} className="min-h-36 rounded-lg" fieldSizing="fixed" required />
                </div>
                <Button type="submit" disabled={creating}>
                  {creating ? <Loader2 className="size-4 animate-spin" /> : <FilePlus2 className="size-4" />}
                  Record
                </Button>
              </form>
            </Panel>
            <Panel title="History">
              {images.length > 0 ? (
                <div className="space-y-3">
                  {images.map((image, index) => (
                    <div key={recordId(image, String(index))} className="rounded-lg border border-border bg-background p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={statusVariant(image.status ?? "planned")}>{labelize(image.status ?? "planned")}</Badge>
                        <Badge variant="outline">{readString(image.model, "default")}</Badge>
                      </div>
                      <p className="mt-3 line-clamp-3 text-sm leading-6 text-foreground">{readString(image.prompt)}</p>
                      <p className="mt-3 text-xs text-muted-foreground">{formatDate(getCreatedAt(image))}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState label="No image requests yet." />
              )}
            </Panel>
          </div>
        </>
      )}
    </ModuleShell>
  );
}

export function CodexPage() {
  const [objective, setObjective] = useState("");
  const [runMode, setRunMode] = useState("guided");
  const [pipeline, setPipeline] = useState<JsonRecord | null>(null);
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [commands, setCommands] = useState<JsonRecord[]>([]);
  const [commandQuery, setCommandQuery] = useState("");
  const [busy, setBusy] = useState<"pipeline" | "preview" | "commands" | null>(null);
  const qualityGates = asRecord(pipeline?.qualityGates);
  const branch = asRecord(pipeline?.branch);
  const blockedActions = asArray(pipeline?.blockedActions);

  async function planPipeline(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!objective.trim()) return;
    setBusy("pipeline");
    try {
      const payload = await cognixJson("/api/cognix/codex/pipeline-plan", {
        method: "POST",
        body: jsonBody({
          objective: objective.trim(),
          runMode,
          nightMode: runMode === "night",
        }),
      });
      setPipeline(asRecord(payload.codexPipelinePlan));
      setPreview(null);
      toast.success("Codex plan ready");
    } catch (err) {
      notifyError("Codex plan failed", err);
    } finally {
      setBusy(null);
    }
  }

  async function buildPreview() {
    if (!objective.trim()) return;
    setBusy("preview");
    try {
      const payload = await cognixJson("/api/cognix/codex/preview-contract", {
        method: "POST",
        body: jsonBody({
          objective: objective.trim(),
          branchName: readString(branch.recommendedName),
          featureRequest: { objective: objective.trim(), source: "cognix_ui" },
          previewTarget: "local",
        }),
      });
      setPreview(asRecord(payload.codexPreviewContract));
      toast.success("Preview contract ready");
    } catch (err) {
      notifyError("Preview contract failed", err);
    } finally {
      setBusy(null);
    }
  }

  async function searchCommands() {
    setBusy("commands");
    try {
      const payload = await cognixJson("/api/cognix/command-palette/search", {
        method: "POST",
        body: jsonBody({
          query: commandQuery.trim() || null,
          limit: 24,
          includeDisabled: true,
        }),
      });
      setCommands(asArray(asRecord(payload.commandPalette).commands));
    } catch (err) {
      notifyError("Command search failed", err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <ModuleShell title="Codex" icon={Code2}>
      <StatGrid>
        <Stat label="Applicable" value={readBoolean(pipeline?.applicable) ? "yes" : "no"} icon={Code2} tone={readBoolean(pipeline?.applicable) ? "amber" : "green"} />
        <Stat label="Run mode" value={labelize(runMode)} icon={Activity} />
        <Stat label="Blocked actions" value={blockedActions.length} icon={ShieldCheck} tone="amber" />
        <Stat label="Commands" value={commands.length} icon={Search} tone="blue" />
      </StatGrid>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Panel title="Pipeline plan">
          <form className="space-y-4" onSubmit={(event) => void planPipeline(event)}>
            <div className="space-y-2">
              <FieldLabel>Run mode</FieldLabel>
              <Select value={runMode} onValueChange={setRunMode}>
                <SelectTrigger className="w-full rounded-lg"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CODEX_RUN_MODES.map((item) => <SelectItem key={item} value={item}>{labelize(item)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <FieldLabel>Objective</FieldLabel>
              <Textarea value={objective} onChange={(event) => setObjective(event.target.value)} className="min-h-36 rounded-lg" fieldSizing="fixed" required />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy === "pipeline"}>
                {busy === "pipeline" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                Plan
              </Button>
              <Button type="button" variant="outline" disabled={!pipeline || busy === "preview"} onClick={() => void buildPreview()}>
                {busy === "preview" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                Preview
              </Button>
            </div>
          </form>
        </Panel>
        <Panel title="Contract">
          {pipeline ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <KeyValue label="Path" value={readString(pipeline.recommendedPath, "not_needed")} />
                <KeyValue label="Branch" value={readString(branch.recommendedName, "none")} />
                <KeyValue label="Quality gates" value={Object.keys(qualityGates).length} />
                <KeyValue label="Preview status" value={readString(preview?.status, "not built")} />
              </div>
              {blockedActions.length > 0 ? (
                <div className="space-y-2">
                  {blockedActions.map((action, index) => (
                    <div key={recordId(action, String(index))} className="rounded-lg border border-border bg-background p-3">
                      <Badge variant="destructive">{readString(action.id, "blocked")}</Badge>
                      <p className="mt-2 text-sm text-muted-foreground">{readString(action.reason)}</p>
                    </div>
                  ))}
                </div>
              ) : null}
              <JsonDetails title="Pipeline" value={pipeline} />
              {preview ? <JsonDetails title="Preview" value={preview} /> : null}
            </div>
          ) : (
            <EmptyState label="No Codex plan yet." />
          )}
        </Panel>
      </div>
      <Panel
        title="Command palette"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={commandQuery} onChange={setCommandQuery} placeholder="Search commands" />
            <Button variant="outline" onClick={() => void searchCommands()} disabled={busy === "commands"}>
              {busy === "commands" ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              Search
            </Button>
          </div>
        }
      >
        {commands.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {commands.map((command, index) => {
              const route = readString(command.route);
              return (
                <button
                  key={recordId(command, String(index))}
                  type="button"
                  className="rounded-lg border border-border bg-background p-4 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => {
                    if (route) window.location.assign(route);
                  }}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={statusVariant(command.status)}>{labelize(command.status)}</Badge>
                    <Badge variant={riskVariant(command.riskLevel)}>{labelize(command.riskLevel)}</Badge>
                  </div>
                  <h3 className="mt-3 text-sm font-semibold text-foreground">{readString(command.label, "Command")}</h3>
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{readString(command.description)}</p>
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState label="No commands loaded." />
        )}
      </Panel>
    </ModuleShell>
  );
}
