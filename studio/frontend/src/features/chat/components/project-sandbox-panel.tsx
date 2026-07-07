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
  AlertTriangleIcon,
  BrainCircuitIcon,
  CheckCircle2Icon,
  CircleDashedIcon,
  Code2Icon,
  FlaskConicalIcon,
  ListChecksIcon,
  LockKeyholeIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SearchIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SparklesIcon,
  TimerIcon,
  WrenchIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSandboxPlan,
  listSandboxRuns,
  type SandboxPipelineStep,
  type SandboxRunRecord,
  type SandboxTargetType,
} from "../api/chat-api";

type SandboxFilter = "all" | SandboxTargetType;

const TARGET_TYPES: Array<{
  value: SandboxTargetType;
  label: string;
}> = [
  { value: "feature", label: "Feature" },
  { value: "model", label: "Model" },
  { value: "tool", label: "Tool" },
  { value: "code_change", label: "Code change" },
  { value: "config_change", label: "Config change" },
];

const PROJECT_TYPES = [
  { value: "developer", label: "Developer" },
  { value: "business", label: "Business" },
  { value: "local", label: "Local" },
  { value: "enterprise", label: "Enterprise" },
  { value: "custom", label: "Custom" },
];

function formatDate(value: string | null | undefined): string {
  if (!value) return "planned";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return "planned";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(time);
}

function targetLabel(value: string | null | undefined): string {
  return TARGET_TYPES.find((item) => item.value === value)?.label ?? "Feature";
}

function riskClass(value: string | null | undefined): string {
  if (value === "high") return "bg-red-500/10 text-red-700 dark:text-red-300";
  if (value === "medium") {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function splitChecks(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 20);
}

function TargetIcon({ type }: { type: SandboxTargetType }) {
  const className = "size-4";
  const strokeWidth = 1.75;
  if (type === "model") {
    return <BrainCircuitIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "tool") {
    return <WrenchIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "code_change") {
    return <Code2Icon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "config_change") {
    return <SettingsIcon className={className} strokeWidth={strokeWidth} />;
  }
  return <SparklesIcon className={className} strokeWidth={strokeWidth} />;
}

function SummaryCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ShieldCheckIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[18px] bg-background/70 px-3 py-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="size-4" strokeWidth={1.75} />
        {label}
      </div>
      <div className="mt-2 break-words text-base font-semibold text-foreground sm:text-lg">
        {value}
      </div>
    </div>
  );
}

function RunRow({
  run,
  selected,
  onSelect,
}: {
  run: SandboxRunRecord;
  selected: boolean;
  onSelect: () => void;
}) {
  const riskLevel =
    run.reportRecord?.riskLevel ?? run.plan.report.riskLevel ?? "low";
  return (
    <button
      type="button"
      data-selected={selected}
      onClick={onSelect}
      className="flex w-full items-start gap-3 rounded-[18px] bg-background/70 px-3 py-3 text-left transition-colors hover:bg-background data-[selected=true]:ring-1 data-[selected=true]:ring-border"
    >
      <span className="mt-1 flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <TargetIcon type={run.targetType} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-foreground">
            {targetLabel(run.targetType)}
          </span>
          <span
            className={cn(
              "rounded-full px-2 py-1 text-[11px] font-medium",
              riskClass(riskLevel),
            )}
          >
            {riskLevel}
          </span>
        </span>
        <span className="mt-1 line-clamp-2 text-xs text-muted-foreground">
          {run.objective}
        </span>
        <span className="mt-2 block text-[11px] text-muted-foreground/80">
          {formatDate(run.createdAt)}
        </span>
      </span>
    </button>
  );
}

function PipelineStepRow({ step }: { step: SandboxPipelineStep }) {
  const blocked = step.willExecuteNow === false;
  return (
    <div className="flex gap-3 rounded-[18px] bg-background/70 px-3 py-3">
      <span
        className={cn(
          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
          blocked
            ? "bg-muted text-muted-foreground"
            : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        )}
      >
        {blocked ? (
          <CircleDashedIcon className="size-4" strokeWidth={1.75} />
        ) : (
          <CheckCircle2Icon className="size-4" strokeWidth={1.75} />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            {step.service}
          </span>
          <span className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">
            {step.status}
          </span>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {step.detail}
        </p>
      </div>
    </div>
  );
}

export function ProjectSandboxPanel({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const [runs, setRuns] = useState<SandboxRunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [planning, setPlanning] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SandboxFilter>("all");
  const [targetType, setTargetType] =
    useState<SandboxTargetType>("code_change");
  const [projectType, setProjectType] = useState("developer");
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [objective, setObjective] = useState(
    `Tester une modification CogniX pour ${projectName} sans toucher la production.`,
  );
  const [changeSummary, setChangeSummary] = useState(
    "Patch a valider dans un environnement isole avec rollback automatique si un check echoue.",
  );
  const [checks, setChecks] = useState("smoke test\nsecurity scan\nrollback");

  const loadRuns = useCallback(
    async (showToast = false) => {
      try {
        setLoading(true);
        const nextRuns = await listSandboxRuns({
          projectId,
          targetType: filter === "all" ? null : filter,
          query: search,
        });
        setRuns(nextRuns);
        setSelectedRunId((current) => {
          if (current && nextRuns.some((run) => run.id === current)) {
            return current;
          }
          return nextRuns[0]?.id ?? null;
        });
        if (showToast) toast.success("Sandbox runs refreshed.");
      } catch (error) {
        toast.error(
          error instanceof Error
            ? error.message
            : "Unable to load sandbox runs.",
        );
      } finally {
        setLoading(false);
      }
    },
    [filter, projectId, search],
  );

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId],
  );

  const handleCreate = useCallback(async () => {
    const trimmedObjective = objective.trim();
    const trimmedChange = changeSummary.trim();
    if (!trimmedObjective || !trimmedChange) {
      toast.error("Objective and change summary are required.");
      return;
    }
    try {
      setPlanning(true);
      const result = await createSandboxPlan({
        projectId,
        projectType,
        targetType,
        objective: trimmedObjective,
        changeSummary: trimmedChange,
        durationMinutes,
        requestedChecks: splitChecks(checks),
        storeRun: true,
      });
      if (result.run) {
        setRuns((current) => [
          result.run as SandboxRunRecord,
          ...current.filter((run) => run.id !== result.run?.id),
        ]);
        setSelectedRunId(result.run.id);
      }
      toast.success("Sandbox plan prepared.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Unable to prepare sandbox.",
      );
    } finally {
      setPlanning(false);
    }
  }, [
    changeSummary,
    checks,
    durationMinutes,
    objective,
    projectId,
    projectType,
    targetType,
  ]);

  const activeReport = selectedRun?.reportRecord?.report ?? selectedRun?.plan.report;
  const activePlan = selectedRun?.plan ?? null;
  const riskLevel = activeReport?.riskLevel ?? "low";
  const approvalText = activeReport?.summary.requiresHumanApproval
    ? "Review required"
    : "Ready to queue";

  return (
    <section
      data-testid="project-sandbox-panel"
      className="mt-8 w-[min(calc(100vw-2.5rem),72rem)] self-center rounded-[24px] border border-border/70 bg-muted/35 p-4 shadow-sm sm:p-5"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="secondary"
              className="rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            >
              <FlaskConicalIcon className="mr-1 size-3.5" strokeWidth={1.75} />
              Mode sandbox actif
            </Badge>
            <Badge variant="outline" className="rounded-full">
              No prod secrets
            </Badge>
          </div>
          <h2 className="mt-3 text-xl font-semibold tracking-normal text-foreground">
            AI Sandbox
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            Prepare isolated experiments for risky changes, models and tools
            before anything touches the real CogniX runtime.
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => void loadRuns(true)}
          aria-label="Refresh sandbox runs"
        >
          <RefreshCwIcon className="size-4" strokeWidth={1.75} />
        </Button>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.2fr)]">
        <div className="space-y-4">
          <div className="rounded-[20px] border border-border/70 bg-background/55 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <FlaskConicalIcon className="size-4" strokeWidth={1.75} />
              Tester en sandbox
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
                Target
                <Select
                  value={targetType}
                  onValueChange={(value) =>
                    setTargetType(value as SandboxTargetType)
                  }
                >
                  <SelectTrigger className="h-10 rounded-full bg-background">
                    <SelectValue placeholder="Target type" />
                  </SelectTrigger>
                  <SelectContent>
                    {TARGET_TYPES.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
                Project type
                <Select value={projectType} onValueChange={setProjectType}>
                  <SelectTrigger className="h-10 rounded-full bg-background">
                    <SelectValue placeholder="Project type" />
                  </SelectTrigger>
                  <SelectContent>
                    {PROJECT_TYPES.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
            </div>
            <label className="mt-3 block space-y-1.5 text-xs font-medium text-muted-foreground">
              Objective
              <Textarea
                value={objective}
                onChange={(event) => setObjective(event.target.value)}
                className="min-h-24 resize-none rounded-[18px] bg-background"
                maxLength={4000}
              />
            </label>
            <label className="mt-3 block space-y-1.5 text-xs font-medium text-muted-foreground">
              Change summary
              <Textarea
                value={changeSummary}
                onChange={(event) => setChangeSummary(event.target.value)}
                className="min-h-24 resize-none rounded-[18px] bg-background"
                maxLength={4000}
              />
            </label>
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_120px]">
              <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
                Requested checks
                <Textarea
                  value={checks}
                  onChange={(event) => setChecks(event.target.value)}
                  className="min-h-20 resize-none rounded-[18px] bg-background"
                  maxLength={1200}
                />
              </label>
              <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
                Minutes
                <Input
                  type="number"
                  min={1}
                  max={1440}
                  value={durationMinutes}
                  onChange={(event) =>
                    setDurationMinutes(Number(event.target.value) || 30)
                  }
                  className="h-10 rounded-full bg-background"
                />
              </label>
            </div>
            <Button
              type="button"
              onClick={() => void handleCreate()}
              disabled={planning}
              className="mt-4 h-10 rounded-full px-5"
            >
              {planning ? "Preparing..." : "Tester en sandbox"}
            </Button>
          </div>

          <div className="rounded-[20px] border border-border/70 bg-background/55 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative min-w-0 flex-1">
                <SearchIcon
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  strokeWidth={1.75}
                />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search sandbox runs"
                  className="h-10 rounded-full bg-background pl-9"
                />
              </div>
              <Select
                value={filter}
                onValueChange={(value) => setFilter(value as SandboxFilter)}
              >
                <SelectTrigger className="h-10 w-full rounded-full bg-background sm:w-44">
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All targets</SelectItem>
                  {TARGET_TYPES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="mt-4 space-y-2">
              {loading ? (
                <>
                  <Skeleton className="h-20 rounded-[18px]" />
                  <Skeleton className="h-20 rounded-[18px]" />
                </>
              ) : runs.length ? (
                runs.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    selected={run.id === selectedRun?.id}
                    onSelect={() => setSelectedRunId(run.id)}
                  />
                ))
              ) : (
                <div className="rounded-[18px] bg-background/70 px-3 py-6 text-center text-sm text-muted-foreground">
                  No sandbox run yet.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-[20px] border border-border/70 bg-background/55 p-4">
          {selectedRun && activePlan && activeReport ? (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      className={cn(
                        "rounded-full px-2.5 py-1",
                        riskClass(riskLevel),
                      )}
                    >
                      {riskLevel} risk
                    </Badge>
                    <Badge variant="outline" className="rounded-full">
                      {approvalText}
                    </Badge>
                  </div>
                  <h3 className="mt-3 text-lg font-semibold text-foreground">
                    {activeReport.title ?? "Sandbox report"}
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {selectedRun.changeSummary}
                  </p>
                </div>
                <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                  {selectedRun.status ?? "planned"}
                </span>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <SummaryCard
                  icon={ListChecksIcon}
                  label="Checks"
                  value={`${activeReport.summary.checkCount ?? activePlan.checks.length}`}
                />
                <SummaryCard
                  icon={TimerIcon}
                  label="Duration"
                  value={`${activePlan.target.durationMinutes} min`}
                />
                <SummaryCard
                  icon={LockKeyholeIcon}
                  label="Prod secrets"
                  value={
                    activePlan.isolation.productionSecretsAccessible
                      ? "Allowed"
                      : "Blocked"
                  }
                />
                <SummaryCard
                  icon={RotateCcwIcon}
                  label="Failure"
                  value={
                    activePlan.rollbackPlan.deleteSandboxOnFailure
                      ? "Delete"
                      : "Review"
                  }
                />
              </div>

              <div className="mt-5 grid gap-4 xl:grid-cols-2">
                <div>
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                    <ShieldCheckIcon className="size-4" strokeWidth={1.75} />
                    Security guardrails
                  </div>
                  <div className="space-y-2">
                    {activeReport.risks.map((risk) => (
                      <div
                        key={risk.id}
                        className="flex items-center justify-between gap-3 rounded-[18px] bg-background/70 px-3 py-3"
                      >
                        <span className="min-w-0 truncate text-sm text-foreground">
                          {risk.id.replaceAll("_", " ")}
                        </span>
                        <span
                          className={cn(
                            "rounded-full px-2 py-1 text-[11px] font-medium",
                            riskClass(risk.severity),
                          )}
                        >
                          {risk.severity}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                    <ListChecksIcon className="size-4" strokeWidth={1.75} />
                    Checks
                  </div>
                  <div className="space-y-2">
                    {activePlan.checks.slice(0, 6).map((check) => (
                      <div
                        key={check.id}
                        className="flex items-center justify-between gap-3 rounded-[18px] bg-background/70 px-3 py-3"
                      >
                        <span className="min-w-0 truncate text-sm text-foreground">
                          {check.label}
                        </span>
                        <span className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">
                          {check.required ? "required" : "optional"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                  <FlaskConicalIcon className="size-4" strokeWidth={1.75} />
                  Planned pipeline
                </div>
                <div className="space-y-2">
                  {selectedRun.pipeline.map((step) => (
                    <PipelineStepRow key={step.id} step={step} />
                  ))}
                </div>
              </div>

              <div className="mt-5 rounded-[18px] bg-background/70 px-3 py-3">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                  <AlertTriangleIcon className="size-4" strokeWidth={1.75} />
                  Recommendations
                </div>
                <ul className="space-y-2 text-sm leading-6 text-muted-foreground">
                  {activeReport.recommendations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </>
          ) : (
            <div className="flex min-h-80 flex-col items-center justify-center rounded-[18px] bg-background/70 px-6 text-center">
              <FlaskConicalIcon
                className="size-8 text-muted-foreground"
                strokeWidth={1.75}
              />
              <p className="mt-3 text-sm font-semibold text-foreground">
                Prepare a sandbox plan
              </p>
              <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
                The report will show isolation rules, blocked production access,
                checks and rollback behavior.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
