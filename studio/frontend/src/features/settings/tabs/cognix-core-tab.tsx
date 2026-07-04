// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { authFetch } from "@/features/auth";
import { cn } from "@/lib/utils";
import { useEffect, useMemo, useState } from "react";
import { SettingsRow } from "../components/settings-row";
import { SettingsSection } from "../components/settings-section";

type LoadState = "idle" | "loading" | "loaded" | "error";

type HardwareProfile = {
  deviceBackend?: string | null;
  memory?: {
    totalGb?: number | null;
    availableGb?: number | null;
  };
  gpu?: {
    label?: string | null;
    vramGb?: number | null;
  };
};

type Recommendation = {
  readiness?: string;
  executionMode?: string;
  providerName?: string | null;
  providerType?: string | null;
  modelId?: string | null;
  modelLabel?: string | null;
  reason?: string | null;
  confidence?: number | null;
  warnings?: string[];
  memoryFit?: {
    level?: string;
    estimatedRamGb?: number | null;
    label?: string | null;
  };
};

type StrategyResponse = {
  username?: string;
  phase?: string;
  roadmapPhase?: string;
  hardware?: HardwareProfile;
  recommendation?: Recommendation;
  nextSteps?: string[];
};

type CacheResponse = {
  runtime?: {
    runtimeType?: string;
    activeModel?: string | null;
    loadedModels?: string[];
    loadingModels?: string[];
  };
  cache?: {
    policy?: {
      maxResidentModels?: number;
      keepWarmMinutes?: number;
      reason?: string;
    };
    residentModels?: Array<{
      modelId?: string;
      state?: string;
      lastUsedAt?: string;
    }>;
  };
};

type RouterLog = {
  id?: string;
  username?: string;
  objectiveExcerpt?: string;
  projectType?: string | null;
  selectedDomain?: string;
  modelLabel?: string;
  confidence?: number;
  needsClarification?: boolean;
  routingMode?: string;
  createdAt?: string;
};

type RouterLogsResponse = {
  logs?: RouterLog[];
};

type AdminReadinessState = LoadState | "protected";

type MvpReadiness = {
  summary?: {
    phaseCount?: number;
    readyPhaseCount?: number;
    partialPhaseCount?: number;
    plannedPhaseCount?: number;
    blockedPhaseCount?: number;
    coreMvpBlocked?: boolean;
    coreMvpBlockedPhaseIds?: string[];
    readyForMvpIteration?: boolean;
  };
  phases?: Array<{
    id?: string;
    phase?: number;
    title?: string;
    status?: string;
    missingRequirements?: string[];
  }>;
  sideEffects?: Record<string, boolean>;
};

type AdvancedRoadmapReadiness = {
  summary?: {
    featureCount?: number;
    readyFeatureCount?: number;
    partialFeatureCount?: number;
    plannedFeatureCount?: number;
    missingFeatureCount?: number;
    nativeModuleCoverageReady?: boolean;
    allStorageReady?: boolean;
    readyForAdvancedIteration?: boolean;
  };
  features?: Array<{
    id?: string;
    number?: number;
    title?: string;
    status?: string;
    moduleId?: string;
    moduleDisplayName?: string;
    capabilityCoverage?: {
      missingCapabilities?: string[];
    };
    routeCoverage?: {
      status?: string;
    };
    storageCoverage?: {
      status?: string;
    };
  }>;
  sideEffects?: Record<string, boolean>;
};

type RuntimeMetrics = {
  runtime?: {
    runtimeType?: string | null;
    activeModel?: string | null;
    loadedModelCount?: number | null;
    loadingModelCount?: number | null;
  };
  hardware?: {
    ram?: {
      totalGb?: number | null;
      availableGb?: number | null;
      usedGb?: number | null;
      usedPercent?: number | null;
    };
    cpu?: {
      usagePercent?: number | null;
    };
    gpu?: {
      available?: boolean;
      deviceCount?: number | null;
    };
  };
  inference?: {
    tokensPerSecond?: number | null;
    latencyMs?: number | null;
    loadTimeMs?: number | null;
    estimatedCostUsd?: number | null;
  };
  sideEffects?: Record<string, boolean>;
};

type RuntimeMetricRow = {
  id?: string;
  created_at?: string;
  model_id?: string | null;
  runtime_type?: string | null;
  ram_used_percent?: number | null;
  cpu_used_percent?: number | null;
  gpu_available?: boolean | number | null;
  tokens_per_second?: number | null;
  latency_ms?: number | null;
  load_time_ms?: number | null;
  estimated_cost_usd?: number | null;
  metrics?: RuntimeMetrics;
};

type PerformanceBlueprint = {
  services?: string[];
  metrics?: string[];
  displayModes?: string[];
  sideEffects?: Record<string, boolean>;
};

type MetricsStreamPlan = {
  intervalMs?: number | null;
  displayMode?: string | null;
  transport?: string | null;
  willOpenStreamNow?: boolean;
  sideEffects?: Record<string, boolean>;
};

function formatGb(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(value >= 10 ? 0 : 1)} GB`
    : "unknown";
}

function formatConfidence(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value * 100)}%`
    : "unknown";
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatCount(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}%` : "unknown";
}

function formatMs(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value)} ms`
    : "unknown";
}

function formatRate(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(value >= 10 ? 1 : 2)}/s`
    : "unknown";
}

function readinessLabel(value: string | undefined): string {
  switch (value) {
    case "ready":
      return "Ready";
    case "ready_with_caution":
      return "Ready with caution";
    case "model_missing":
      return "Model missing";
    case "service_unreachable":
      return "Service unreachable";
    case "setup_required":
      return "Setup required";
    case "hardware_blocked":
      return "Hardware blocked";
    default:
      return value || "Unknown";
  }
}

function roadmapStatusLabel(value: string | undefined): string {
  switch (value) {
    case "ready":
      return "Ready";
    case "partial":
      return "Partial";
    case "planned":
      return "Planned";
    case "blocked":
      return "Blocked";
    case "missing":
      return "Missing";
    default:
      return value || "Unknown";
  }
}

function statusTone(readiness: string | undefined): string {
  if (readiness === "ready") return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  if (readiness === "ready_with_caution") return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  return "bg-destructive/10 text-destructive";
}

function readinessTone(isReady: boolean | undefined): string {
  if (isReady) return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
}

function blockedTone(count: number): string {
  return count > 0
    ? "bg-destructive/10 text-destructive"
    : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function summarizeRoadmapItems(
  items: Array<{ title?: string; status?: string; missingRequirements?: string[] }>,
): string {
  if (!items.length) return "Tous les contrats suivis sont prets.";
  return items
    .slice(0, 3)
    .map((item) => {
      const missing = item.missingRequirements?.length
        ? ` (${item.missingRequirements.length} manque)`
        : "";
      return `${item.title ?? "Item"}: ${roadmapStatusLabel(item.status)}${missing}`;
    })
    .join(" / ");
}

function InfoPill({
  label,
  tone,
}: {
  label: string;
  tone?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center rounded-full px-3 text-xs font-medium",
        tone ?? "bg-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}

export function CogniXCoreTab() {
  const [strategy, setStrategy] = useState<StrategyResponse | null>(null);
  const [cache, setCache] = useState<CacheResponse | null>(null);
  const [routerLogs, setRouterLogs] = useState<RouterLog[] | null>(null);
  const [mvpReadiness, setMvpReadiness] = useState<MvpReadiness | null>(null);
  const [advancedReadiness, setAdvancedReadiness] = useState<AdvancedRoadmapReadiness | null>(null);
  const [readinessState, setReadinessState] = useState<AdminReadinessState>("idle");
  const [performanceBlueprint, setPerformanceBlueprint] = useState<PerformanceBlueprint | null>(null);
  const [metricsStreamPlan, setMetricsStreamPlan] = useState<MetricsStreamPlan | null>(null);
  const [runtimeMetrics, setRuntimeMetrics] = useState<RuntimeMetrics | null>(null);
  const [performanceMetrics, setPerformanceMetrics] = useState<RuntimeMetricRow[]>([]);
  const [performanceState, setPerformanceState] = useState<LoadState>("idle");
  const [performanceMessage, setPerformanceMessage] = useState<string | null>(null);
  const [recordingPerformance, setRecordingPerformance] = useState(false);
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function loadCore() {
    setState("loading");
    setReadinessState("loading");
    setPerformanceState("loading");
    setMessage(null);
    setPerformanceMessage(null);
    try {
      const [
        strategyRes,
        cacheRes,
        logsRes,
        mvpRes,
        advancedRes,
        performanceBlueprintRes,
        metricsStreamPlanRes,
        performanceMetricsRes,
      ] = await Promise.all([
        authFetch("/api/cognix/strategy"),
        authFetch("/api/cognix/models/cache"),
        authFetch("/api/cognix/admin/router-logs").catch(() => null),
        authFetch("/api/cognix/admin/mvp-readiness").catch(() => null),
        authFetch("/api/cognix/admin/advanced-roadmap-readiness").catch(() => null),
        authFetch("/api/cognix/performance/blueprint").catch(() => null),
        authFetch("/api/cognix/performance/stream-plan").catch(() => null),
        authFetch("/api/cognix/performance/metrics?limit=8").catch(() => null),
      ]);
      if (!strategyRes.ok || !cacheRes.ok) {
        throw new Error("CogniX Core endpoints unavailable.");
      }
      setStrategy((await strategyRes.json()) as StrategyResponse);
      setCache((await cacheRes.json()) as CacheResponse);
      if (logsRes?.ok) {
        const body = (await logsRes.json()) as RouterLogsResponse;
        setRouterLogs((body.logs ?? []).slice(0, 5));
      } else {
        setRouterLogs(null);
      }

      let nextMvp: MvpReadiness | null = null;
      let nextAdvanced: AdvancedRoadmapReadiness | null = null;
      let protectedReadiness = false;

      if (mvpRes?.ok) {
        const body = (await mvpRes.json()) as { mvpReadiness?: MvpReadiness };
        nextMvp = body.mvpReadiness ?? null;
      } else if (mvpRes?.status === 403) {
        protectedReadiness = true;
      }

      if (advancedRes?.ok) {
        const body = (await advancedRes.json()) as { advancedRoadmapReadiness?: AdvancedRoadmapReadiness };
        nextAdvanced = body.advancedRoadmapReadiness ?? null;
      } else if (advancedRes?.status === 403) {
        protectedReadiness = true;
      }

      setMvpReadiness(nextMvp);
      setAdvancedReadiness(nextAdvanced);
      setReadinessState(nextMvp || nextAdvanced ? "loaded" : protectedReadiness ? "protected" : "error");

      if (performanceBlueprintRes?.ok) {
        const body = (await performanceBlueprintRes.json()) as { performanceBlueprint?: PerformanceBlueprint };
        setPerformanceBlueprint(body.performanceBlueprint ?? null);
      } else {
        setPerformanceBlueprint(null);
      }

      if (metricsStreamPlanRes?.ok) {
        const body = (await metricsStreamPlanRes.json()) as { metricsStreamPlan?: MetricsStreamPlan };
        setMetricsStreamPlan(body.metricsStreamPlan ?? null);
      } else {
        setMetricsStreamPlan(null);
      }

      if (performanceMetricsRes?.ok) {
        const body = (await performanceMetricsRes.json()) as { metrics?: RuntimeMetricRow[] };
        setPerformanceMetrics((body.metrics ?? []).slice(0, 8));
      } else {
        setPerformanceMetrics([]);
      }
      setRuntimeMetrics(null);
      setPerformanceState(
        performanceBlueprintRes?.ok || metricsStreamPlanRes?.ok || performanceMetricsRes?.ok ? "loaded" : "error",
      );
      setState("loaded");
    } catch {
      setState("error");
      setReadinessState("error");
      setPerformanceState("error");
      setMvpReadiness(null);
      setAdvancedReadiness(null);
      setPerformanceBlueprint(null);
      setMetricsStreamPlan(null);
      setRuntimeMetrics(null);
      setPerformanceMetrics([]);
      setMessage("Impossible de charger CogniX Core.");
    }
  }

  async function recordPerformanceSnapshot() {
    setRecordingPerformance(true);
    setPerformanceMessage(null);
    try {
      const runtimeSnapshot = {
        runtimeType: runtime?.runtimeType ?? "unknown",
        activeModel: runtime?.activeModel ?? null,
        loadedModels: runtime?.loadedModels ?? [],
        loadingModels: runtime?.loadingModels ?? [],
      };
      const response = await authFetch("/api/cognix/performance/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runtimeSnapshot,
          modelId: runtime?.activeModel ?? null,
          storeMetric: true,
        }),
      });
      if (!response.ok) {
        throw new Error("Performance snapshot unavailable.");
      }
      const body = (await response.json()) as {
        runtimeMetrics?: RuntimeMetrics;
        storedMetric?: RuntimeMetricRow | null;
      };
      setRuntimeMetrics(body.runtimeMetrics ?? null);
      if (body.storedMetric) {
        setPerformanceMetrics((current) => [body.storedMetric as RuntimeMetricRow, ...current].slice(0, 8));
      }
      setPerformanceState("loaded");
      setPerformanceMessage("Snapshot enregistre.");
    } catch {
      setPerformanceState("error");
      setPerformanceMessage("Impossible d'enregistrer le snapshot.");
    } finally {
      setRecordingPerformance(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCore(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const recommendation = strategy?.recommendation;
  const hardware = strategy?.hardware;
  const runtime = cache?.runtime;
  const cachePolicy = cache?.cache?.policy;
  const residentModels = cache?.cache?.residentModels ?? [];
  const warnings = recommendation?.warnings ?? [];
  const nextSteps = useMemo(
    () => (strategy?.nextSteps ?? []).slice(0, 4),
    [strategy?.nextSteps],
  );
  const mvpSummary = mvpReadiness?.summary;
  const advancedSummary = advancedReadiness?.summary;
  const nonReadyMvpPhases = useMemo(
    () => (mvpReadiness?.phases ?? []).filter((phase) => phase.status !== "ready"),
    [mvpReadiness?.phases],
  );
  const nonReadyAdvancedFeatures = useMemo(
    () => (advancedReadiness?.features ?? []).filter((feature) => feature.status !== "ready"),
    [advancedReadiness?.features],
  );
  const readOnlySideEffects = useMemo(() => {
    const effects = {
      ...(mvpReadiness?.sideEffects ?? {}),
      ...(advancedReadiness?.sideEffects ?? {}),
    };
    return Object.values(effects).every((value) => value === false);
  }, [advancedReadiness?.sideEffects, mvpReadiness?.sideEffects]);
  const latestPerformanceMetric = performanceMetrics[0] ?? null;
  const displayedRuntimeMetrics = runtimeMetrics ?? latestPerformanceMetric?.metrics ?? null;
  const displayedRamPercent =
    displayedRuntimeMetrics?.hardware?.ram?.usedPercent ?? latestPerformanceMetric?.ram_used_percent;
  const displayedCpuPercent =
    displayedRuntimeMetrics?.hardware?.cpu?.usagePercent ?? latestPerformanceMetric?.cpu_used_percent;
  const displayedTokensPerSecond =
    displayedRuntimeMetrics?.inference?.tokensPerSecond ?? latestPerformanceMetric?.tokens_per_second;
  const displayedLatencyMs =
    displayedRuntimeMetrics?.inference?.latencyMs ?? latestPerformanceMetric?.latency_ms;
  const streamIntervalSeconds = Math.max(1, Math.round((metricsStreamPlan?.intervalMs ?? 3000) / 1000));
  const performanceNoExecution = useMemo(() => {
    const effects = {
      ...(performanceBlueprint?.sideEffects ?? {}),
      ...(metricsStreamPlan?.sideEffects ?? {}),
      ...(displayedRuntimeMetrics?.sideEffects ?? {}),
    };
    return ["modelLoad", "generation", "benchmarkRun", "gpuStressTest", "networkCall"].every(
      (key) => effects[key] === false || effects[key] === undefined,
    );
  }, [displayedRuntimeMetrics?.sideEffects, metricsStreamPlan?.sideEffects, performanceBlueprint?.sideEffects]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-heading text-xl font-semibold">CogniX Core</h1>
            <p className="text-xs text-muted-foreground">
              Strategie locale, recommandation modele et cache runtime.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void loadCore()}
            disabled={state === "loading"}
          >
            {state === "loading" ? "Refresh..." : "Refresh"}
          </Button>
        </div>
        {message ? (
          <p className="text-xs text-destructive" role="alert">
            {message}
          </p>
        ) : null}
      </header>

      <SettingsSection
        title="Decision layer"
        description="Etat MVP du cerveau local qui doit choisir la bonne strategie IA."
      >
        <SettingsRow
          label="Phase"
          description={strategy?.roadmapPhase ?? "Chargement de la strategie..."}
        >
          <InfoPill label={strategy?.phase ?? state} />
        </SettingsRow>
        <SettingsRow
          label="Recommendation"
          description={recommendation?.reason ?? "CogniX prepare la recommendation locale."}
          alignTop
        >
          <div className="flex max-w-[250px] flex-wrap justify-end gap-2">
            <InfoPill
              label={readinessLabel(recommendation?.readiness)}
              tone={statusTone(recommendation?.readiness)}
            />
            {typeof recommendation?.confidence === "number" ? (
              <InfoPill label={`${Math.round(recommendation.confidence * 100)}% confidence`} />
            ) : null}
          </div>
        </SettingsRow>
        <SettingsRow
          label={recommendation?.modelLabel ?? "Model"}
          description={recommendation?.modelId ?? "Aucun modele recommande pour le moment."}
        >
          <InfoPill label={recommendation?.providerName ?? recommendation?.providerType ?? "Provider"} />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Recent routing"
        description="Dernieres decisions CogniX Auto journalisees par le backend."
      >
        {routerLogs === null ? (
          <SettingsRow
            label="Decision logs"
            description="Connecte en admin pour voir les decisions du routeur."
          >
            <InfoPill label="protected" />
          </SettingsRow>
        ) : routerLogs.length ? (
          routerLogs.map((log) => (
            <SettingsRow
              key={log.id ?? `${log.createdAt}:${log.objectiveExcerpt}`}
              label={log.selectedDomain ?? "general"}
              description={
                <span className="flex flex-col gap-1">
                  <span className="line-clamp-2">
                    {log.objectiveExcerpt ?? "Aucun extrait disponible."}
                  </span>
                  <span>
                    {log.modelLabel ?? "CogniX General 3B"} /{" "}
                    {log.routingMode ?? "unknown"} /{" "}
                    {formatTimestamp(log.createdAt)}
                  </span>
                </span>
              }
              alignTop
            >
              <div className="flex flex-col items-end gap-1">
                <InfoPill label={formatConfidence(log.confidence)} />
                {log.needsClarification ? (
                  <InfoPill
                    label="clarify"
                    tone="bg-amber-500/10 text-amber-700 dark:text-amber-300"
                  />
                ) : null}
              </div>
            </SettingsRow>
          ))
        ) : (
          <SettingsRow
            label="No decisions yet"
            description="Envoie un message sans modele selectionne pour creer une decision CogniX Auto."
          >
            <InfoPill label="empty" />
          </SettingsRow>
        )}
      </SettingsSection>

      <SettingsSection
        title="Hardware profile"
        description="Base locale utilisee par le futur orchestrateur pour eviter les choix trop lourds."
      >
        <SettingsRow
          label="Backend"
          description="Runtime detecte pour les decisions locales."
        >
          <InfoPill label={hardware?.deviceBackend ?? "unknown"} />
        </SettingsRow>
        <SettingsRow
          label="Memory"
          description={`Available ${formatGb(hardware?.memory?.availableGb)} / total ${formatGb(hardware?.memory?.totalGb)}`}
        >
          <InfoPill label={recommendation?.memoryFit?.label ?? "Fit unknown"} />
        </SettingsRow>
        <SettingsRow
          label="GPU"
          description={hardware?.gpu?.label ?? "Aucun GPU visible ou GPU non detecte."}
        >
          <InfoPill label={formatGb(hardware?.gpu?.vramGb)} />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Model cache"
        description="Premiere couche du futur cache LRU, sans chargement automatique de modele."
      >
        <SettingsRow
          label="Runtime"
          description={runtime?.activeModel ? `Active: ${runtime.activeModel}` : "Aucun modele actif."}
        >
          <InfoPill label={runtime?.runtimeType ?? "unknown"} />
        </SettingsRow>
        <SettingsRow
          label="Policy"
          description={cachePolicy?.reason ?? "Politique cache non disponible."}
        >
          <InfoPill
            label={`${cachePolicy?.maxResidentModels ?? 0} resident / ${cachePolicy?.keepWarmMinutes ?? 0} min`}
          />
        </SettingsRow>
        <SettingsRow
          label="Resident models"
          description={
            residentModels.length
              ? residentModels.map((model) => model.modelId ?? "unknown").join(", ")
              : "Aucun modele resident."
          }
        >
          <InfoPill label={`${residentModels.length}`} />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Performance monitor"
        description="Suivi natif des ressources runtime, snapshots persistants et garde anti-execution."
      >
        <SettingsRow
          label="Collector"
          description={`${performanceBlueprint?.services?.length ?? 0} services / ${performanceBlueprint?.metrics?.length ?? 0} metrics / ${streamIntervalSeconds}s`}
        >
          <InfoPill
            label={performanceState === "loading" ? "loading" : performanceState}
            tone={performanceState === "error" ? "bg-destructive/10 text-destructive" : undefined}
          />
        </SettingsRow>
        <SettingsRow
          label="Host load"
          description={`RAM ${formatPercent(displayedRamPercent)} / CPU ${formatPercent(displayedCpuPercent)}`}
        >
          <InfoPill
            label={displayedRuntimeMetrics?.hardware?.gpu?.available || latestPerformanceMetric?.gpu_available ? "GPU visible" : "CPU only"}
          />
        </SettingsRow>
        <SettingsRow
          label="Inference"
          description={
            <span className="flex flex-col gap-1">
              <span>
                {formatRate(displayedTokensPerSecond)} tokens / latency {formatMs(displayedLatencyMs)}
              </span>
              <span>
                {performanceMetrics.length} snapshots
                {latestPerformanceMetric?.created_at ? ` / latest ${formatTimestamp(latestPerformanceMetric.created_at)}` : ""}
                {performanceMessage ? ` / ${performanceMessage}` : ""}
              </span>
            </span>
          }
          alignTop
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void recordPerformanceSnapshot()}
            disabled={recordingPerformance || state === "loading"}
          >
            {recordingPerformance ? "Recording..." : "Snapshot"}
          </Button>
        </SettingsRow>
        <SettingsRow
          label="Execution guard"
          description={`Stream plan: ${metricsStreamPlan?.displayMode ?? "discreet_panel"} / ${metricsStreamPlan?.transport ?? "polling"}`}
        >
          <InfoPill
            label={performanceNoExecution ? "safe" : "review"}
            tone={performanceNoExecution ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-amber-500/10 text-amber-700 dark:text-amber-300"}
          />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Roadmap readiness"
        description="Contrats backend natifs pour suivre les phases MVP et les 30 fonctions avancees."
      >
        {readinessState === "loading" || readinessState === "idle" ? (
          <SettingsRow
            label="Admin contracts"
            description="Chargement des contrats internes."
          >
            <InfoPill label="loading" />
          </SettingsRow>
        ) : readinessState === "protected" ? (
          <SettingsRow
            label="Admin contracts"
            description="Connecte en compte CEO/admin pour voir les contrats internes."
          >
            <InfoPill label="protected" />
          </SettingsRow>
        ) : readinessState === "error" && !mvpReadiness && !advancedReadiness ? (
          <SettingsRow
            label="Admin contracts"
            description="Les contrats internes ne sont pas disponibles sur ce backend."
          >
            <InfoPill label="unavailable" tone="bg-destructive/10 text-destructive" />
          </SettingsRow>
        ) : (
          <>
            <SettingsRow
              label="MVP phases"
              description={summarizeRoadmapItems(nonReadyMvpPhases)}
              alignTop
            >
              <div className="flex flex-wrap justify-end gap-2">
                <InfoPill
                  label={`${formatCount(mvpSummary?.readyPhaseCount)}/${formatCount(mvpSummary?.phaseCount)} ready`}
                  tone={readinessTone(mvpSummary?.readyForMvpIteration)}
                />
                <InfoPill
                  label={`${formatCount(mvpSummary?.blockedPhaseCount)} blocked`}
                  tone={blockedTone(formatCount(mvpSummary?.blockedPhaseCount))}
                />
              </div>
            </SettingsRow>
            <SettingsRow
              label="Advanced native"
              description={summarizeRoadmapItems(nonReadyAdvancedFeatures)}
              alignTop
            >
              <div className="flex flex-wrap justify-end gap-2">
                <InfoPill
                  label={`${formatCount(advancedSummary?.readyFeatureCount)}/${formatCount(advancedSummary?.featureCount)} ready`}
                  tone={readinessTone(advancedSummary?.readyForAdvancedIteration)}
                />
                <InfoPill
                  label={`${formatCount(advancedSummary?.missingFeatureCount)} missing`}
                  tone={blockedTone(formatCount(advancedSummary?.missingFeatureCount))}
                />
              </div>
            </SettingsRow>
            <SettingsRow
              label="Read-only guard"
              description="Aucune migration, activation, execution d'outil ou chargement de modele depuis cette vue."
            >
              <InfoPill
                label={readOnlySideEffects ? "clean" : "review"}
                tone={readOnlySideEffects ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-amber-500/10 text-amber-700 dark:text-amber-300"}
              />
            </SettingsRow>
          </>
        )}
      </SettingsSection>

      {warnings.length || nextSteps.length ? (
        <SettingsSection title="Next" description="Signaux utiles pour la suite du MVP.">
          {warnings.length ? (
            <SettingsRow
              label="Warnings"
              description={warnings.join(" ")}
              alignTop
            />
          ) : null}
          {nextSteps.length ? (
            <SettingsRow
              label="Roadmap"
              description={nextSteps.join(" ")}
              alignTop
            />
          ) : null}
        </SettingsSection>
      ) : null}
    </div>
  );
}
