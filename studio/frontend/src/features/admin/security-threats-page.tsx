// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { authFetch } from "@/features/auth";
import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Severity = "critical" | "high" | "medium" | "low";
type StatusFilter = "open" | "active" | "in_review" | "resolved" | "ignored";
type LoadState = "idle" | "loading" | "loaded" | "error";

interface ThreatSummary {
  id?: string;
  category?: string;
  title?: string;
  description?: string;
  impact?: string;
  severity?: Severity | string;
  filesAffected?: string[];
  evidence?: string;
  recommendedSolution?: string;
  status?: StatusFilter | string;
  sourceType?: string;
  sourceId?: string;
  createdAt?: string;
}

interface IncidentCategory {
  id: string;
  label: string;
  description?: string;
  count: number;
  severity?: Severity | string;
  status?: string;
  items?: ThreatSummary[];
}

interface ThreatCenter {
  centerVersion?: string;
  scannerAdapterVersion?: string;
  summary?: {
    status?: string;
    totalSignals?: number;
    critical?: number;
    high?: number;
    medium?: number;
    low?: number;
    resolved?: number;
    ignored?: number;
    open?: number;
    cloudRisks?: number;
    codexIncidents?: number;
    permissionErrors?: number;
    exposedSecrets?: number;
  };
  incidentCategories?: IncidentCategory[];
  codexSummaries?: ThreatSummary[];
  sideEffects?: Record<string, boolean>;
}

interface ThreatResponse {
  securityThreatCenter?: ThreatCenter;
  incidentCategories?: IncidentCategory[];
  codexSummaries?: ThreatSummary[];
  sideEffects?: Record<string, boolean>;
}

const severityFilters = ["all", "critical", "high", "medium", "low"] as const;
const statusFilters = ["all", "open", "active", "in_review", "resolved", "ignored"] as const;

function normalizeSeverity(value: unknown): Severity {
  const normalized = String(value ?? "low").toLowerCase();
  if (normalized === "critical" || normalized === "high" || normalized === "medium") {
    return normalized;
  }
  return "low";
}

function normalizeStatus(value: unknown): StatusFilter {
  const normalized = String(value ?? "open").toLowerCase();
  if (
    normalized === "active" ||
    normalized === "in_review" ||
    normalized === "resolved" ||
    normalized === "ignored"
  ) {
    return normalized;
  }
  return "open";
}

function severityClass(severity: unknown): string {
  switch (normalizeSeverity(severity)) {
    case "critical":
      return "border-red-500/50 bg-red-500/10 text-red-200";
    case "high":
      return "border-orange-500/50 bg-orange-500/10 text-orange-200";
    case "medium":
      return "border-amber-500/50 bg-amber-500/10 text-amber-100";
    default:
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-100";
  }
}

function statusLabel(status: unknown): string {
  switch (normalizeStatus(status)) {
    case "active":
      return "Active";
    case "in_review":
      return "In review";
    case "resolved":
      return "Resolved";
    case "ignored":
      return "Ignored";
    default:
      return "Open";
  }
}

function filterLabel(value: string): string {
  if (value === "all") return "All";
  if (value === "in_review") return "In review";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function MetricTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: string;
}) {
  return (
    <div className="min-h-[74px] rounded-lg border border-border/70 bg-background px-4 py-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tracking-normal ${tone ?? "text-foreground"}`}>
        {value}
      </div>
    </div>
  );
}

function FilterButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-8 rounded-md border px-3 text-xs font-medium transition-colors ${
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border/70 bg-background text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

export function SecurityThreatsPage() {
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [data, setData] = useState<ThreatResponse | null>(null);
  const [severityFilter, setSeverityFilter] =
    useState<(typeof severityFilters)[number]>("all");
  const [statusFilter, setStatusFilter] =
    useState<(typeof statusFilters)[number]>("all");
  const [categoryFilter, setCategoryFilter] = useState("all");

  async function loadThreats() {
    setState("loading");
    setMessage(null);
    try {
      const response = await authFetch("/api/cognix/admin/security-threats");
      if (!response.ok) {
        setState("error");
        setMessage(response.status === 403 ? "Admin access required." : "Security threats unavailable.");
        return;
      }
      setData((await response.json()) as ThreatResponse);
      setState("loaded");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Unable to load security threats.");
    }
  }

  useEffect(() => {
    void loadThreats();
  }, []);

  const center = data?.securityThreatCenter;
  const categories = data?.incidentCategories ?? center?.incidentCategories ?? [];
  const summaries = data?.codexSummaries ?? center?.codexSummaries ?? [];
  const summary = center?.summary ?? {};

  const filteredSummaries = useMemo(() => {
    return summaries.filter((item) => {
      const severityOk =
        severityFilter === "all" || normalizeSeverity(item.severity) === severityFilter;
      const statusOk =
        statusFilter === "all" || normalizeStatus(item.status) === statusFilter;
      const categoryOk = categoryFilter === "all" || item.category === categoryFilter;
      return severityOk && statusOk && categoryOk;
    });
  }, [categoryFilter, severityFilter, statusFilter, summaries]);

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-5 px-5 pb-8 pt-5 md:px-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
            Admin
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-foreground">
            Security Threats
          </h1>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>{center?.centerVersion ?? "cognix_security_threat_center_v1"}</span>
            <span>{center?.scannerAdapterVersion ?? "scanner_adapter"}</span>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void loadThreats()}
          disabled={state === "loading"}
          className="gap-2 self-start"
        >
          <RefreshCw className={`size-4 ${state === "loading" ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </header>

      {state === "error" ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {message}
        </div>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <MetricTile label="Total" value={summary.totalSignals ?? summaries.length} />
        <MetricTile label="Critical" value={summary.critical ?? 0} tone="text-red-300" />
        <MetricTile label="High" value={summary.high ?? 0} tone="text-orange-300" />
        <MetricTile label="Medium" value={summary.medium ?? 0} tone="text-amber-200" />
        <MetricTile label="Resolved" value={summary.resolved ?? 0} tone="text-emerald-300" />
        <MetricTile label="Ignored" value={summary.ignored ?? 0} tone="text-muted-foreground" />
      </section>

      <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-muted/20 p-3">
        <div className="flex flex-wrap gap-2">
          {severityFilters.map((filter) => (
            <FilterButton
              key={filter}
              active={severityFilter === filter}
              onClick={() => setSeverityFilter(filter)}
            >
              {filterLabel(filter)}
            </FilterButton>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {statusFilters.map((filter) => (
            <FilterButton
              key={filter}
              active={statusFilter === filter}
              onClick={() => setStatusFilter(filter)}
            >
              {filterLabel(filter)}
            </FilterButton>
          ))}
        </div>
      </section>

      <section className="grid min-h-0 gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => setCategoryFilter("all")}
            className={`rounded-lg border px-4 py-3 text-left text-sm transition-colors ${
              categoryFilter === "all"
                ? "border-foreground bg-foreground text-background"
                : "border-border/70 bg-background hover:bg-muted/40"
            }`}
          >
            <div className="font-semibold">All categories</div>
            <div className="mt-1 text-xs opacity-80">{summaries.length} signals</div>
          </button>

          {categories.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => setCategoryFilter(category.id)}
              className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                categoryFilter === category.id
                  ? "border-foreground bg-foreground text-background"
                  : "border-border/70 bg-background hover:bg-muted/40"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 truncate text-sm font-semibold">
                  {category.label}
                </div>
                <span className="shrink-0 text-xs font-semibold">{category.count}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className={`rounded-md border px-2 py-0.5 text-[11px] ${severityClass(category.severity)}`}>
                  {filterLabel(normalizeSeverity(category.severity))}
                </span>
                <span className="rounded-md border border-border/70 px-2 py-0.5 text-[11px]">
                  {statusLabel(category.status)}
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          {state === "loading" && filteredSummaries.length === 0 ? (
            <div className="rounded-lg border border-border/70 bg-background px-4 py-8 text-center text-sm text-muted-foreground">
              Loading...
            </div>
          ) : null}

          {state !== "loading" && filteredSummaries.length === 0 ? (
            <div className="rounded-lg border border-border/70 bg-background px-4 py-8 text-center text-sm text-muted-foreground">
              No threats match these filters.
            </div>
          ) : null}

          {filteredSummaries.map((item) => (
            <article
              key={`${item.sourceType ?? "signal"}:${item.sourceId ?? item.id ?? item.title}`}
              className="rounded-lg border border-border/70 bg-background p-4"
            >
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${severityClass(item.severity)}`}>
                      {filterLabel(normalizeSeverity(item.severity))}
                    </span>
                    <span className="rounded-md border border-border/70 px-2 py-1 text-xs text-muted-foreground">
                      {statusLabel(item.status)}
                    </span>
                  </div>
                  <h2 className="mt-3 text-base font-semibold text-foreground">
                    {item.title ?? "Security threat"}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.description ?? "Security signal detected."}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
                  <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Impact
                  </div>
                  <p className="mt-2 text-sm text-foreground">{item.impact ?? "Review required."}</p>
                </div>
                <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
                  <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Solution
                  </div>
                  <p className="mt-2 text-sm text-foreground">
                    {item.recommendedSolution ?? "Track and remediate this finding."}
                  </p>
                </div>
              </div>

              <div className="mt-3 rounded-lg border border-border/60 bg-muted/20 p-3">
                <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Evidence
                </div>
                <p className="mt-2 break-words font-mono text-xs text-foreground">
                  {item.evidence ?? "No evidence captured."}
                </p>
                {item.filesAffected && item.filesAffected.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.filesAffected.map((file) => (
                      <span
                        key={file}
                        className="rounded-md border border-border/70 bg-background px-2 py-1 font-mono text-[11px] text-muted-foreground"
                      >
                        {file}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
