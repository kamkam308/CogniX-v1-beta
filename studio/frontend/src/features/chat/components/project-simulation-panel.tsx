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
  BarChart3Icon,
  BriefcaseIcon,
  Clock3Icon,
  DatabaseIcon,
  GaugeIcon,
  RefreshCwIcon,
  SearchIcon,
  ServerIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserIcon,
  UsersIcon,
  WorkflowIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSimulationRun,
  listSimulationRuns,
  type SimulationMetric,
  type SimulationRunRecord,
  type SimulationType,
} from "../api/chat-api";

type SimulationFilter = "all" | SimulationType;

const SIMULATION_TYPES: Array<{
  value: SimulationType;
  label: string;
}> = [
  { value: "business", label: "Business" },
  { value: "user", label: "User" },
  { value: "server", label: "Server" },
  { value: "database", label: "Database" },
  { value: "workflow", label: "Workflow" },
];

const PROJECT_TYPES = [
  { value: "business", label: "Business" },
  { value: "school", label: "School" },
  { value: "developer", label: "Developer" },
  { value: "local", label: "Local" },
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

function simulationLabel(value: string | null | undefined): string {
  return (
    SIMULATION_TYPES.find((item) => item.value === value)?.label ?? "Business"
  );
}

function severityClass(value: string | null | undefined): string {
  if (value === "high") return "bg-red-500/10 text-red-700 dark:text-red-300";
  if (value === "medium") {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function metricValue(metric: SimulationMetric): string {
  if (metric.unit === "ms") return `${Math.round(metric.value)} ms`;
  if (metric.unit === "rpm") return `${Math.round(metric.value)} rpm`;
  if (metric.unit === "percent") return `${Math.round(metric.value)}%`;
  if (metric.unit === "usd") return `$${metric.value.toFixed(4)}`;
  return `${metric.value}`;
}

function metricPercent(metric: SimulationMetric): number {
  if (metric.unit === "percent")
    return Math.max(3, Math.min(100, metric.value));
  if (metric.unit === "ms")
    return Math.max(3, Math.min(100, (metric.value / 1400) * 100));
  if (metric.unit === "rpm")
    return Math.max(3, Math.min(100, (metric.value / 600) * 100));
  if (metric.unit === "usd")
    return Math.max(3, Math.min(100, metric.value * 80));
  return Math.max(3, Math.min(100, metric.value));
}

function splitConstraints(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 20);
}

function SummaryMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof BarChart3Icon;
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

function MetricBar({ metric }: { metric: SimulationMetric }) {
  return (
    <div className="rounded-[18px] bg-background/70 px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-foreground">
          {metric.label}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-1 text-[11px] font-medium",
            severityClass(metric.severity),
          )}
        >
          {metric.severity}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <div className="h-2 min-w-0 flex-1 rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-foreground/80"
            style={{ width: `${metricPercent(metric)}%` }}
          />
        </div>
        <span className="w-20 shrink-0 text-right text-xs text-muted-foreground">
          {metricValue(metric)}
        </span>
      </div>
    </div>
  );
}

function SimulationTypeIcon({ type }: { type: SimulationType }) {
  const className = "size-4";
  const strokeWidth = 1.75;
  if (type === "user") {
    return <UserIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "server") {
    return <ServerIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "database") {
    return <DatabaseIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (type === "workflow") {
    return <WorkflowIcon className={className} strokeWidth={strokeWidth} />;
  }
  return <BriefcaseIcon className={className} strokeWidth={strokeWidth} />;
}

function RunRow({
  run,
  selected,
  onSelect,
}: {
  run: SimulationRunRecord;
  selected: boolean;
  onSelect: () => void;
}) {
  const severity = run.report.summary.highestMetricSeverity ?? "low";
  return (
    <button
      type="button"
      data-selected={selected}
      onClick={onSelect}
      className="flex w-full items-start gap-3 rounded-[18px] bg-background/70 px-3 py-3 text-left transition-colors hover:bg-background data-[selected=true]:ring-1 data-[selected=true]:ring-border"
    >
      <span className="mt-1 flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <SimulationTypeIcon type={run.simulationType} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-foreground">
            {simulationLabel(run.simulationType)} / {run.userCount} users
          </span>
          <span
            className={cn(
              "rounded-full px-2 py-1 text-[11px] font-medium",
              severityClass(severity),
            )}
          >
            {severity}
          </span>
        </span>
        <span className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
          {run.scenario}
        </span>
        <span className="mt-2 block text-[11px] text-muted-foreground">
          {run.durationMinutes} min / {formatDate(run.createdAt)}
        </span>
      </span>
    </button>
  );
}

export function ProjectSimulationPanel({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const [runs, setRuns] = useState<SimulationRunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<SimulationFilter>("all");
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [simulationType, setSimulationType] =
    useState<SimulationType>("business");
  const [projectType, setProjectType] = useState("business");
  const [userCount, setUserCount] = useState(100);
  const [durationMinutes, setDurationMinutes] = useState(45);
  const [scenario, setScenario] = useState(
    `Simulate 100 users using ${projectName}.`,
  );
  const [constraints, setConstraints] = useState("database\nprivacy");

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId],
  );

  const highRiskCount = useMemo(
    () =>
      runs.filter((run) => run.report.summary.highestMetricSeverity === "high")
        .length,
    [runs],
  );
  const queuedCount = useMemo(
    () => runs.filter((run) => run.report.summary.queueRequired).length,
    [runs],
  );

  const loadRuns = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const nextRuns = await listSimulationRuns({
          projectId,
          simulationType: filter === "all" ? null : filter,
          query: appliedQuery || null,
        });
        setRuns(nextRuns);
        setSelectedRunId((current) =>
          current && nextRuns.some((run) => run.id === current)
            ? current
            : (nextRuns[0]?.id ?? null),
        );
        if (showToast) toast.success("Simulation runs refreshed.");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to load simulations.";
        setError(message);
        if (showToast) toast.error(message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [appliedQuery, filter, projectId],
  );

  useEffect(() => {
    setLoading(true);
    void loadRuns();
  }, [loadRuns]);

  const handlePlanSimulation = useCallback(async () => {
    const cleanScenario = scenario.trim();
    if (!cleanScenario) {
      toast.error("Add a scenario before planning the simulation.");
      return;
    }
    setSaving(true);
    try {
      const result = await createSimulationRun({
        projectId,
        projectType,
        simulationType,
        userCount,
        scenario: cleanScenario,
        durationMinutes,
        constraints: splitConstraints(constraints),
        storeRun: true,
      });
      if (result.run) {
        setRuns((current) => [
          result.run as SimulationRunRecord,
          ...current.filter((run) => run.id !== result.run?.id),
        ]);
        setSelectedRunId(result.run.id);
      }
      toast.success("Simulation report planned.");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to plan simulation.",
      );
    } finally {
      setSaving(false);
    }
  }, [
    constraints,
    durationMinutes,
    projectId,
    projectType,
    scenario,
    simulationType,
    userCount,
  ]);

  const summary = selectedRun?.report.summary;
  const selectedMetrics = selectedRun?.metrics.length
    ? selectedRun.metrics
    : (selectedRun?.plan.metrics ?? []);

  return (
    <section
      className="mt-8 rounded-[26px] bg-muted/30 px-5 py-5"
      data-testid="project-simulation-panel"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex size-10 items-center justify-center rounded-full bg-background text-foreground">
              <BarChart3Icon className="size-5" strokeWidth={1.75} />
            </span>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-foreground">
                Simulation
              </h2>
              <p className="text-xs leading-5 text-muted-foreground">
                Pre-deployment load, workflow, database, user, and business
                estimates.
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="bg-background">
              {runs.length} runs
            </Badge>
            <Badge variant="outline" className="bg-background">
              {highRiskCount} high risk
            </Badge>
            <Badge variant="outline" className="bg-background">
              {queuedCount} queue advised
            </Badge>
            <Badge
              variant="outline"
              className="bg-background text-muted-foreground"
            >
              planner only
            </Badge>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={refreshing}
          onClick={() => void loadRuns(true)}
          className="w-fit gap-2 rounded-full"
        >
          <RefreshCwIcon
            className={cn("size-4", refreshing && "animate-spin")}
            strokeWidth={1.75}
          />
          Refresh
        </Button>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="rounded-[22px] bg-background/60 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <SparklesIcon className="size-4" strokeWidth={1.75} />
            Plan a scenario
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Select
              value={simulationType}
              onValueChange={(value) =>
                setSimulationType(value as SimulationType)
              }
            >
              <SelectTrigger className="h-10 rounded-full bg-background">
                <SelectValue placeholder="Simulation type" />
              </SelectTrigger>
              <SelectContent>
                {SIMULATION_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={projectType} onValueChange={setProjectType}>
              <SelectTrigger className="h-10 rounded-full bg-background">
                <SelectValue placeholder="Project type" />
              </SelectTrigger>
              <SelectContent>
                {PROJECT_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              type="number"
              min={1}
              max={100000}
              value={userCount}
              onChange={(event) =>
                setUserCount(Math.max(1, Number(event.target.value) || 1))
              }
              className="h-10 rounded-full bg-background"
              aria-label="User count"
            />
            <Input
              type="number"
              min={1}
              max={10080}
              value={durationMinutes}
              onChange={(event) =>
                setDurationMinutes(Math.max(1, Number(event.target.value) || 1))
              }
              className="h-10 rounded-full bg-background"
              aria-label="Duration minutes"
            />
          </div>
          <div className="mt-3 space-y-3">
            <Textarea
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
              placeholder={`Simulate 100 users using ${projectName}.`}
              className="min-h-28 rounded-[18px] bg-background"
            />
            <Textarea
              value={constraints}
              onChange={(event) => setConstraints(event.target.value)}
              placeholder="database, privacy, local only"
              className="min-h-20 rounded-[18px] bg-background"
            />
            <Button
              type="button"
              disabled={saving}
              onClick={() => void handlePlanSimulation()}
              className="w-full gap-2 rounded-full"
            >
              <ShieldCheckIcon className="size-4" strokeWidth={1.75} />
              Plan simulation
            </Button>
          </div>
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
                  if (event.key === "Enter") setAppliedQuery(query.trim());
                }}
                placeholder="Search scenarios, reports, risks..."
                className="h-10 rounded-full bg-background pl-9"
              />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Select
                value={filter}
                onValueChange={(value) => setFilter(value as SimulationFilter)}
              >
                <SelectTrigger className="h-10 w-[150px] rounded-full bg-background">
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  {SIMULATION_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
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

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div className="space-y-3">
              {loading ? (
                <>
                  <Skeleton className="h-24 rounded-[18px]" />
                  <Skeleton className="h-24 rounded-[18px]" />
                  <Skeleton className="h-24 rounded-[18px]" />
                </>
              ) : runs.length > 0 ? (
                runs.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    selected={run.id === selectedRun?.id}
                    onSelect={() => setSelectedRunId(run.id)}
                  />
                ))
              ) : (
                <div className="rounded-[20px] bg-background/70 px-4 py-8 text-center">
                  <GaugeIcon
                    className="mx-auto size-6 text-muted-foreground"
                    strokeWidth={1.75}
                  />
                  <p className="mt-3 text-sm font-semibold text-foreground">
                    No simulation runs yet
                  </p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Plan a scenario to create the first dashboard report.
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-3">
              {selectedRun ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <SummaryMetric
                      icon={UsersIcon}
                      label="Users"
                      value={`${selectedRun.userCount}`}
                    />
                    <SummaryMetric
                      icon={Clock3Icon}
                      label="Duration"
                      value={`${selectedRun.durationMinutes} min`}
                    />
                    <SummaryMetric
                      icon={GaugeIcon}
                      label="Latency"
                      value={`${Math.round(summary?.estimatedLatencyMs ?? 0)} ms`}
                    />
                    <SummaryMetric
                      icon={BarChart3Icon}
                      label="Cost"
                      value={`$${(summary?.estimatedCostUsd ?? 0).toFixed(2)}`}
                    />
                  </div>
                  <div className="rounded-[18px] bg-background/70 px-3 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "rounded-full px-2 py-1 text-[11px] font-medium",
                          severityClass(summary?.highestMetricSeverity),
                        )}
                      >
                        {summary?.highestMetricSeverity ?? "low"} severity
                      </span>
                      {summary?.queueRequired ? (
                        <Badge
                          variant="outline"
                          className="bg-background text-muted-foreground"
                        >
                          queue advised
                        </Badge>
                      ) : null}
                      <Badge
                        variant="outline"
                        className="bg-background text-muted-foreground"
                      >
                        no live load
                      </Badge>
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
                      {selectedRun.scenario}
                    </p>
                  </div>
                  <div className="space-y-2">
                    {selectedMetrics.map((metric) => (
                      <MetricBar key={metric.id} metric={metric} />
                    ))}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-[18px] bg-background/70 px-3 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <AlertTriangleIcon
                          className="size-4"
                          strokeWidth={1.75}
                        />
                        Risks
                      </div>
                      <div className="mt-3 space-y-2">
                        {selectedRun.report.risks.map((risk) => (
                          <div
                            key={risk.id}
                            className="rounded-[14px] bg-muted/50 px-3 py-2"
                          >
                            <span
                              className={cn(
                                "rounded-full px-2 py-1 text-[11px] font-medium",
                                severityClass(risk.severity),
                              )}
                            >
                              {risk.severity}
                            </span>
                            <p className="mt-2 text-xs leading-5 text-muted-foreground">
                              {risk.message || risk.label || risk.id}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-[18px] bg-background/70 px-3 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <DatabaseIcon className="size-4" strokeWidth={1.75} />
                        Bottlenecks
                      </div>
                      <div className="mt-3 space-y-2">
                        {selectedRun.report.bottlenecks.length > 0 ? (
                          selectedRun.report.bottlenecks.map((bottleneck) => (
                            <div
                              key={bottleneck.id}
                              className="flex items-center justify-between gap-3 rounded-[14px] bg-muted/50 px-3 py-2"
                            >
                              <span className="text-xs font-medium text-foreground">
                                {bottleneck.label || bottleneck.id}
                              </span>
                              <span
                                className={cn(
                                  "rounded-full px-2 py-1 text-[11px] font-medium",
                                  severityClass(bottleneck.severity),
                                )}
                              >
                                {bottleneck.severity}
                              </span>
                            </div>
                          ))
                        ) : (
                          <p className="text-xs leading-5 text-muted-foreground">
                            No bottleneck above threshold.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              ) : loading ? (
                <Skeleton className="h-72 rounded-[18px]" />
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
