// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { authFetch } from "@/features/auth";
import { BarChart3, Database, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type LoadState = "idle" | "loading" | "loaded" | "error";

interface UsageSummary {
  eventCount?: number;
  messageCount?: number;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  modelsUsed?: number;
  userCount?: number;
  projectCount?: number;
  estimatedCostUsd?: number;
  averageLatencyMs?: number;
  localTokens?: number;
  cloudTokens?: number;
}

interface UsageRow extends UsageSummary {
  username?: string;
  modelId?: string;
  projectId?: string;
  day?: string;
  scope?: string;
  estimatedCostUsd?: number;
}

interface UsageDashboard {
  usageDashboardVersion?: string;
  mode?: string;
  summary?: UsageSummary;
  byUser?: UsageRow[];
  byModel?: UsageRow[];
  byProject?: UsageRow[];
  byDay?: UsageRow[];
  byProviderScope?: UsageRow[];
  charts?: {
    usageByDay?: UsageRow[];
    usageByModel?: UsageRow[];
    usageByUser?: UsageRow[];
    localVsCloud?: UsageRow[];
    costEstimate?: UsageRow[];
  };
  organization?: {
    organizationId?: string;
    peakDay?: string | null;
    topUsers?: UsageRow[];
    topModels?: UsageRow[];
    localCloudSplit?: UsageRow[];
  };
  rollups?: {
    dailyUserTokenUsage?: unknown[];
    dailyModelUsage?: unknown[];
    organizationUsageSummary?: unknown[];
  };
  sideEffects?: Record<string, boolean>;
}

interface UsageResponse {
  usageDashboard?: UsageDashboard;
}

const numberFormatter = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const compactFormatter = new Intl.NumberFormat("en", {
  maximumFractionDigits: 1,
  notation: "compact",
});
const currencyFormatter = new Intl.NumberFormat("en", {
  currency: "USD",
  maximumFractionDigits: 4,
  style: "currency",
});

function numberValue(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatNumber(value: unknown): string {
  return numberFormatter.format(numberValue(value));
}

function formatCompact(value: unknown): string {
  return compactFormatter.format(numberValue(value));
}

function formatCost(value: unknown): string {
  return currencyFormatter.format(numberValue(value));
}

function MetricTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="min-h-[76px] rounded-lg border border-border/70 bg-background px-4 py-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tracking-normal ${tone ?? "text-foreground"}`}>
        {value}
      </div>
    </div>
  );
}

function BarList({
  rows,
  labelKey,
  valueKey = "totalTokens",
  emptyLabel = "No data",
}: {
  rows: UsageRow[];
  labelKey: "day" | "modelId" | "username" | "projectId" | "scope";
  valueKey?: "totalTokens" | "estimatedCostUsd";
  emptyLabel?: string;
}) {
  const maxValue = Math.max(1, ...rows.map((row) => numberValue(row[valueKey])));
  if (rows.length === 0) {
    return <div className="py-8 text-center text-sm text-muted-foreground">{emptyLabel}</div>;
  }
  return (
    <div className="flex flex-col gap-3">
      {rows.slice(0, 10).map((row) => {
        const label = String(row[labelKey] ?? "unknown");
        const value = numberValue(row[valueKey]);
        const width = `${Math.max(4, Math.round((value / maxValue) * 100))}%`;
        return (
          <div key={`${label}-${valueKey}`} className="grid grid-cols-[minmax(92px,160px)_1fr_auto] items-center gap-3">
            <div className="truncate text-sm text-muted-foreground" title={label}>
              {label}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-emerald-400" style={{ width }} />
            </div>
            <div className="min-w-[72px] text-right text-sm font-medium text-foreground">
              {valueKey === "estimatedCostUsd" ? formatCost(value) : formatCompact(value)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ChartSection({
  title,
  rows,
  labelKey,
  valueKey,
}: {
  title: string;
  rows: UsageRow[];
  labelKey: "day" | "modelId" | "username" | "projectId" | "scope";
  valueKey?: "totalTokens" | "estimatedCostUsd";
}) {
  return (
    <section className="rounded-lg border border-border/70 bg-card p-4">
      <div className="mb-4 flex items-center gap-2">
        <BarChart3 className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      </div>
      <BarList rows={rows} labelKey={labelKey} valueKey={valueKey} />
    </section>
  );
}

export function AdminUsagePage() {
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<UsageDashboard | null>(null);
  const [aggregating, setAggregating] = useState(false);

  async function loadUsage() {
    setState("loading");
    setMessage(null);
    try {
      const response = await authFetch("/api/cognix/admin/usage");
      if (!response.ok) {
        setState("error");
        setMessage(response.status === 403 ? "Admin access required." : "Usage dashboard unavailable.");
        return;
      }
      const data = (await response.json()) as UsageResponse;
      setDashboard(data.usageDashboard ?? null);
      setState("loaded");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Unable to load usage dashboard.");
    }
  }

  async function aggregateUsage() {
    setAggregating(true);
    setMessage(null);
    try {
      const response = await authFetch("/api/cognix/admin/usage/aggregate", { method: "POST" });
      if (!response.ok) {
        setMessage(response.status === 403 ? "Admin access required." : "Usage aggregation unavailable.");
        return;
      }
      const data = (await response.json()) as UsageResponse;
      setDashboard(data.usageDashboard ?? null);
      setState("loaded");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Unable to aggregate usage.");
    } finally {
      setAggregating(false);
    }
  }

  useEffect(() => {
    void loadUsage();
  }, []);

  const summary = dashboard?.summary ?? {};
  const chartRows = useMemo(() => {
    return {
      day: dashboard?.charts?.usageByDay ?? dashboard?.byDay ?? [],
      model: dashboard?.charts?.usageByModel ?? dashboard?.byModel ?? [],
      user: dashboard?.charts?.usageByUser ?? dashboard?.byUser ?? [],
      localCloud: dashboard?.charts?.localVsCloud ?? dashboard?.byProviderScope ?? [],
      cost: dashboard?.charts?.costEstimate ?? [],
      project: dashboard?.byProject ?? [],
    };
  }, [dashboard]);

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-5 px-5 pb-8 pt-5 md:px-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
            Admin
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-foreground">
            Token Usage
          </h1>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>{dashboard?.usageDashboardVersion ?? "cognix_usage_dashboard_v1"}</span>
            <span>{dashboard?.organization?.organizationId ?? "default"}</span>
            <span>{dashboard?.organization?.peakDay ?? "no_peak_day"}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void aggregateUsage()}
            disabled={aggregating || state === "loading"}
            className="gap-2"
          >
            <Database className={`size-4 ${aggregating ? "animate-pulse" : ""}`} />
            Aggregate
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void loadUsage()}
            disabled={state === "loading"}
            className="gap-2"
          >
            <RefreshCw className={`size-4 ${state === "loading" ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      {state === "error" || message ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {message}
        </div>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <MetricTile label="Tokens" value={formatNumber(summary.totalTokens)} />
        <MetricTile label="Input" value={formatNumber(summary.inputTokens)} />
        <MetricTile label="Output" value={formatNumber(summary.outputTokens)} />
        <MetricTile label="Messages" value={formatNumber(summary.messageCount)} />
        <MetricTile label="Cost" value={formatCost(summary.estimatedCostUsd)} tone="text-emerald-300" />
        <MetricTile label="Latency" value={`${formatNumber(summary.averageLatencyMs)} ms`} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ChartSection title="Usage By Day" rows={chartRows.day} labelKey="day" />
        <ChartSection title="Usage By Model" rows={chartRows.model} labelKey="modelId" />
        <ChartSection title="Usage By User" rows={chartRows.user} labelKey="username" />
        <ChartSection title="Local Vs Cloud" rows={chartRows.localCloud} labelKey="scope" />
        <ChartSection title="Cost Estimate" rows={chartRows.cost} labelKey="day" valueKey="estimatedCostUsd" />
        <ChartSection title="Usage By Project" rows={chartRows.project} labelKey="projectId" />
      </section>
    </main>
  );
}
