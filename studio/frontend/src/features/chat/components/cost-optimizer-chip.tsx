// SPDX-License-Identifier: AGPL-3.0-only

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent } from "@/components/ui/tooltip";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  CloudIcon,
  DollarSignIcon,
  LaptopIcon,
  RefreshCwIcon,
  ServerIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  TimerIcon,
} from "lucide-react";
import { Tooltip as TooltipPrimitive } from "radix-ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCostOptimizationPlan,
  type CostCandidate,
  type CostOptimizationPlan,
} from "../api/cost-optimizer";

export interface CostOptimizerContextUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface CostOptimizerChipProps {
  active: boolean;
  checkpoint: string;
  isExternalModel: boolean;
  providerName?: string | null;
  providerType?: string | null;
  projectId?: string | null;
  projectName?: string | null;
  threadTitle?: string | null;
  contextUsage?: CostOptimizerContextUsage | null;
}

function costLabel(value: number | null | undefined): string {
  const cost = typeof value === "number" && Number.isFinite(value) ? value : 0;
  if (cost <= 0) return "Free";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  if (cost < 1) return `$${cost.toFixed(2)}`;
  return `$${cost.toFixed(1)}`;
}

function latencyLabel(value: number | null | undefined): string {
  const ms = typeof value === "number" && Number.isFinite(value) ? value : 0;
  if (ms <= 0) return "unknown";
  if (ms >= 1000) return `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)}s`;
  return `${Math.round(ms)}ms`;
}

function shortCheckpoint(value: string): string {
  const decoded = decodeURIComponent(value);
  const segments = decoded.split(/[/:]/).filter(Boolean);
  return segments.at(-1) ?? decoded;
}

function targetLabel(value: string | null | undefined): string {
  if (value === "cloud_api") return "Cloud";
  if (value === "personal_server") return "Personal server";
  if (value === "enterprise_server") return "Enterprise";
  if (value === "local") return "Local";
  return value ? value.replace(/_/g, " ") : "Target";
}

function TargetIcon({ target }: { target: string | null | undefined }) {
  const className = "size-3.5";
  const strokeWidth = 1.75;
  if (target === "cloud_api") {
    return <CloudIcon className={className} strokeWidth={strokeWidth} />;
  }
  if (target === "enterprise_server" || target === "personal_server") {
    return <ServerIcon className={className} strokeWidth={strokeWidth} />;
  }
  return <LaptopIcon className={className} strokeWidth={strokeWidth} />;
}

function candidateTone(candidate: CostCandidate): string {
  if (candidate.status === "blocked") {
    return "bg-red-500/10 text-red-700 dark:text-red-300";
  }
  if (candidate.costEstimate.billingRequired) {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function shouldDisplayPlan(
  plan: CostOptimizationPlan | null,
  {
    isExternalModel,
    contextUsage,
  }: Pick<CostOptimizerChipProps, "isExternalModel" | "contextUsage">,
): boolean {
  if (!plan) return isExternalModel;
  if (isExternalModel) return true;
  if (plan.policy.cloudBlockedBecauseSensitive) return true;
  if (plan.decision.estimatedCostUsd > 0) return true;
  if (plan.decision.requiresExplicitUserAction) return true;
  if (plan.guardedDecision?.selectedExecutionTargetChanged) return true;
  if (contextUsage && plan.decision.selectedExecutionTarget !== "local") {
    return true;
  }
  return false;
}

function OptionRow({ candidate }: { candidate: CostCandidate }) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-muted/60 px-2 py-2">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-background text-muted-foreground">
        <TargetIcon target={candidate.executionTarget} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-foreground">
          {candidate.displayName}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {costLabel(candidate.costEstimate.estimatedCostUsd)} /{" "}
          {latencyLabel(candidate.latencyEstimate.estimatedLatencyMs)}
        </span>
      </span>
      <Badge
        variant="secondary"
        className={cn("rounded-full text-[10.5px]", candidateTone(candidate))}
      >
        {candidate.status}
      </Badge>
    </div>
  );
}

export function CostOptimizerChip({
  active,
  checkpoint,
  isExternalModel,
  providerName,
  providerType,
  projectId,
  projectName,
  threadTitle,
  contextUsage,
}: CostOptimizerChipProps) {
  const [plan, setPlan] = useState<CostOptimizationPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shouldPlan = Boolean(
    active && checkpoint && (isExternalModel || contextUsage),
  );
  const objective = useMemo(() => {
    const target = shortCheckpoint(checkpoint);
    const title = threadTitle || projectName || "New chat";
    const provider = providerName || providerType || "local";
    return `${title} with ${target} on ${provider}`;
  }, [checkpoint, projectName, providerName, providerType, threadTitle]);
  const constraints = useMemo(
    () =>
      [
        isExternalModel ? "external_provider_selected" : "local_provider_selected",
        providerType ? `provider_type:${providerType}` : null,
        projectName ? `project:${projectName}` : null,
      ].filter((item): item is string => Boolean(item)),
    [isExternalModel, projectName, providerType],
  );

  const refresh = useCallback(
    async (showToast = false) => {
      if (!shouldPlan) {
        setPlan(null);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const result = await createCostOptimizationPlan({
          objective,
          projectId,
          projectType: projectId ? "project" : null,
          priority: "balanced",
          sensitivityLevel: null,
          constraints,
          expectedInputTokens: contextUsage?.promptTokens ?? null,
          expectedOutputTokens: contextUsage?.completionTokens ?? null,
          messageCount: contextUsage ? 1 : null,
          allowCloudWhenSensitive: false,
          enforceQuotas: true,
          storeLog: false,
        });
        setPlan(result.costOptimizationPlan);
        if (showToast) toast.success("Cost plan refreshed.");
      } catch (caught) {
        const message =
          caught instanceof Error ? caught.message : "Cost optimizer unavailable.";
        setError(message);
        if (showToast) toast.error(message);
      } finally {
        setLoading(false);
      }
    },
    [
      constraints,
      contextUsage,
      objective,
      projectId,
      shouldPlan,
    ],
  );

  useEffect(() => {
    if (!shouldPlan) {
      setPlan(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void createCostOptimizationPlan({
        objective,
        projectId,
        projectType: projectId ? "project" : null,
        priority: "balanced",
        sensitivityLevel: null,
        constraints,
        expectedInputTokens: contextUsage?.promptTokens ?? null,
        expectedOutputTokens: contextUsage?.completionTokens ?? null,
        messageCount: contextUsage ? 1 : null,
        allowCloudWhenSensitive: false,
        enforceQuotas: true,
        storeLog: false,
      })
        .then((result) => {
          if (!cancelled) setPlan(result.costOptimizationPlan);
        })
        .catch((caught) => {
          if (!cancelled) {
            setError(
              caught instanceof Error
                ? caught.message
                : "Cost optimizer unavailable.",
            );
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 240);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [
    constraints,
    contextUsage,
    objective,
    projectId,
    shouldPlan,
  ]);

  if (!shouldDisplayPlan(plan, { isExternalModel, contextUsage })) {
    return null;
  }

  const decision = plan?.guardedDecision ?? plan?.decision ?? null;
  const target = decision?.selectedExecutionTarget ?? null;
  const cost = decision?.estimatedCostUsd ?? plan?.decision.estimatedCostUsd ?? 0;
  const latency =
    decision?.estimatedLatencyMs ?? plan?.decision.estimatedLatencyMs ?? 0;
  const cloudBlocked =
    plan?.policy.cloudBlockedBecauseSensitive ||
    plan?.decision.cloudBlockedBecauseSensitive;
  const quotaBlocked = plan?.budgetGuard?.status === "blocked_by_quota";
  const paid = cost > 0;
  const tone = cloudBlocked || quotaBlocked
    ? "border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300"
    : paid
      ? "border-amber-500/35 bg-amber-500/10 text-amber-700 dark:text-amber-300"
      : "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  const label = cloudBlocked ? "Privacy guard" : costLabel(cost);
  const candidates = plan?.candidates.slice(0, 3) ?? [];

  return (
    <Tooltip>
      <TooltipPrimitive.Trigger asChild={true}>
        <button
          type="button"
          data-testid="cost-optimizer-chip"
          onClick={() => void refresh(true)}
          className={cn(
            "hidden h-[34px] w-auto max-w-[220px] shrink-0 items-center justify-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium transition-colors hover:bg-nav-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex",
            tone,
          )}
          aria-label={`AI Cost Optimizer: ${targetLabel(target)}, ${label}`}
        >
          {cloudBlocked || quotaBlocked ? (
            <ShieldAlertIcon className="size-3.5 shrink-0" strokeWidth={1.75} />
          ) : (
            <DollarSignIcon className="size-3.5 shrink-0" strokeWidth={1.75} />
          )}
          <span className="shrink-0">Cost</span>
          <span className="text-muted-foreground">/</span>
          <span className="min-w-0 truncate">
            {loading && !plan ? "Planning..." : label}
          </span>
        </button>
      </TooltipPrimitive.Trigger>
      <TooltipContent
        side="bottom"
        sideOffset={6}
        variant="rich"
        className="max-w-[380px]"
      >
        <div className="flex flex-col gap-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-medium">AI Cost Optimizer</div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                {targetLabel(target)} / {costLabel(cost)} / {latencyLabel(latency)}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void refresh(true)}
              className="flex size-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Refresh cost plan"
            >
              <RefreshCwIcon
                className={cn("size-3.5", loading && "animate-spin")}
                strokeWidth={1.75}
              />
            </button>
          </div>
          {error ? (
            <div className="rounded-md bg-red-500/10 px-2 py-1.5 text-xs text-red-700 dark:text-red-300">
              {error}
            </div>
          ) : null}
          {plan ? (
            <>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-md bg-muted/60 px-2 py-2">
                  <DollarSignIcon className="mb-1 size-3.5" strokeWidth={1.75} />
                  {costLabel(cost)}
                </div>
                <div className="rounded-md bg-muted/60 px-2 py-2">
                  <TimerIcon className="mb-1 size-3.5" strokeWidth={1.75} />
                  {latencyLabel(latency)}
                </div>
                <div className="rounded-md bg-muted/60 px-2 py-2">
                  <ShieldCheckIcon className="mb-1 size-3.5" strokeWidth={1.75} />
                  {plan.sensitivity.sensitive ? "Sensitive" : "Normal"}
                </div>
              </div>
              {cloudBlocked ? (
                <div className="rounded-md bg-red-500/10 px-2 py-1.5 text-xs text-red-700 dark:text-red-300">
                  Cloud blocked until explicit validation because the task looks
                  sensitive.
                </div>
              ) : null}
              <div className="space-y-1.5">
                {candidates.map((candidate) => (
                  <OptionRow key={candidate.providerId} candidate={candidate} />
                ))}
              </div>
              <div className="text-[11px] leading-4 text-muted-foreground">
                Dry run only: no provider call, billing mutation, generation or
                model load.
              </div>
            </>
          ) : (
            <div className="text-xs text-muted-foreground">
              Building the local cost plan.
            </div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
