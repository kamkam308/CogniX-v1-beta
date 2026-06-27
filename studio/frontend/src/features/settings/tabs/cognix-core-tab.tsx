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

function formatGb(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(value >= 10 ? 0 : 1)} GB`
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

function statusTone(readiness: string | undefined): string {
  if (readiness === "ready") return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  if (readiness === "ready_with_caution") return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  return "bg-destructive/10 text-destructive";
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
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function loadCore() {
    setState("loading");
    setMessage(null);
    try {
      const [strategyRes, cacheRes] = await Promise.all([
        authFetch("/api/cognix/strategy"),
        authFetch("/api/cognix/models/cache"),
      ]);
      if (!strategyRes.ok || !cacheRes.ok) {
        throw new Error("CogniX Core endpoints unavailable.");
      }
      setStrategy((await strategyRes.json()) as StrategyResponse);
      setCache((await cacheRes.json()) as CacheResponse);
      setState("loaded");
    } catch {
      setState("error");
      setMessage("Impossible de charger CogniX Core.");
    }
  }

  useEffect(() => {
    void loadCore();
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
