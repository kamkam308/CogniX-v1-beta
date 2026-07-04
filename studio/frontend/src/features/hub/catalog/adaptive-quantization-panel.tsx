// SPDX-License-Identifier: AGPL-3.0-only

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  CheckCircle2Icon,
  GaugeIcon,
  HardDriveIcon,
  MemoryStickIcon,
  RefreshCwIcon,
  SaveIcon,
  ShieldCheckIcon,
  SparklesIcon,
  ZapIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createAdaptiveQuantizationPlan,
  listQuantizationProfiles,
  type QuantizationPlan,
  type QuantizationPriority,
  type QuantizationProfile,
  type QuantizationVariant,
} from "../api/adaptive-quantization";

const PRIORITY_OPTIONS: Array<{
  value: QuantizationPriority;
  label: string;
  icon: typeof SparklesIcon;
}> = [
  { value: "balanced", label: "Equilibre", icon: GaugeIcon },
  { value: "quality", label: "Qualite", icon: SparklesIcon },
  { value: "speed", label: "Vitesse", icon: ZapIcon },
  { value: "memory", label: "Memoire", icon: MemoryStickIcon },
];

function priorityLabel(priority: QuantizationPriority): string {
  return (
    PRIORITY_OPTIONS.find((item) => item.value === priority)?.label ??
    "Equilibre"
  );
}

function fitClass(status: string | null | undefined): string {
  if (status === "blocked") return "bg-red-500/10 text-red-700 dark:text-red-300";
  if (status === "tight") {
    return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
}

function gbLabel(value: number | null | undefined): string {
  if (!value) return "0 GB";
  return `${value.toFixed(value >= 10 ? 0 : 1)} GB`;
}

function VariantRow({
  variant,
  selected = false,
}: {
  variant: QuantizationVariant;
  selected?: boolean;
}) {
  return (
    <div
      data-selected={selected}
      className="flex min-w-0 items-center gap-3 rounded-lg border border-border/50 bg-background/70 px-3 py-3 data-[selected=true]:ring-1 data-[selected=true]:ring-border"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <HardDriveIcon className="size-4" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            {variant.quantization}
          </span>
          <span className="truncate text-xs text-muted-foreground">
            {variant.label}
          </span>
          {selected ? (
            <Badge
              className="rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              variant="secondary"
            >
              Recommande
            </Badge>
          ) : null}
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-full bg-muted px-2 py-1">
            RAM {gbLabel(variant.fit.estimatedRamGb)}
          </span>
          <span className="rounded-full bg-muted px-2 py-1">
            Quality {variant.performancePrediction.expectedQuality ?? "medium"}
          </span>
          <span className="rounded-full bg-muted px-2 py-1">
            Speed {variant.performancePrediction.expectedLatency ?? "medium"}
          </span>
        </div>
      </div>
      <span
        className={cn(
          "rounded-full px-2 py-1 text-[11px] font-medium",
          fitClass(variant.fit.status),
        )}
      >
        {variant.fit.status}
      </span>
    </div>
  );
}

function ProfileSummary({ profile }: { profile: QuantizationProfile | null }) {
  if (!profile) {
    return (
      <span className="text-xs text-muted-foreground">
        No saved profile yet
      </span>
    );
  }
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
      <CheckCircle2Icon className="size-3.5 text-emerald-600" strokeWidth={1.75} />
      <span className="truncate">
        Saved {profile.quantization} for {priorityLabel(profile.priority)}
      </span>
    </span>
  );
}

export function AdaptiveQuantizationPanel({
  activeModelId,
  activeGgufVariant,
  hidden = false,
}: {
  activeModelId: string | null;
  activeGgufVariant: string | null;
  hidden?: boolean;
}) {
  const [priority, setPriority] = useState<QuantizationPriority>("balanced");
  const [plan, setPlan] = useState<QuantizationPlan | null>(null);
  const [latestProfile, setLatestProfile] = useState<QuantizationProfile | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modelMetadata = useMemo(
    () =>
      activeModelId
        ? {
            modelId: activeModelId,
            modelLabel: activeModelId,
            providerType: "local_gguf",
            format: "gguf",
            quantization: activeGgufVariant ?? undefined,
          }
        : null,
    [activeGgufVariant, activeModelId],
  );

  const loadPlan = useCallback(
    async (nextPriority: QuantizationPriority, showToast = false) => {
      try {
        setLoading(true);
        setError(null);
        const [planResponse, profiles] = await Promise.all([
          createAdaptiveQuantizationPlan({
            priority: nextPriority,
            modelId: activeModelId,
            modelMetadata,
            storeProfile: false,
          }),
          listQuantizationProfiles().catch(() => []),
        ]);
        setPlan(planResponse.quantizationPlan);
        setLatestProfile(profiles[0] ?? null);
        if (showToast) toast.success("Quantization recommendation refreshed.");
      } catch (caught) {
        const message =
          caught instanceof Error
            ? caught.message
            : "Unable to load quantization recommendation.";
        setError(message);
        toast.error(message);
      } finally {
        setLoading(false);
      }
    },
    [activeModelId, modelMetadata],
  );

  useEffect(() => {
    if (!hidden) {
      void loadPlan(priority);
    }
  }, [hidden, loadPlan, priority]);

  const saveProfile = useCallback(async () => {
    try {
      setSaving(true);
      setError(null);
      const response = await createAdaptiveQuantizationPlan({
        priority,
        modelId: activeModelId,
        modelMetadata,
        storeProfile: true,
      });
      setPlan(response.quantizationPlan);
      setLatestProfile(response.profile);
      toast.success("Quantization profile saved.");
    } catch (caught) {
      const message =
        caught instanceof Error
          ? caught.message
          : "Unable to save quantization profile.";
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }, [activeModelId, modelMetadata, priority]);

  if (hidden) return null;

  const selected = plan?.selectedVariant ?? null;
  const alternatives = plan?.alternativeVariants.slice(0, 2) ?? [];

  return (
    <section
      data-testid="adaptive-quantization-panel"
      className="mx-auto w-full max-w-[1100px] px-4 pb-3 sm:px-5"
    >
      <div className="border-y border-border/70 bg-muted/30 p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant="secondary"
                className="rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              >
                <ShieldCheckIcon className="mr-1 size-3.5" strokeWidth={1.75} />
                {plan?.badge.label ?? "Recommande pour ton PC"}
              </Badge>
              <Badge variant="outline" className="rounded-full">
                Dry run
              </Badge>
              {selected ? (
                <Badge variant="outline" className="rounded-full">
                  {selected.quantization}
                </Badge>
              ) : null}
            </div>
            <h2 className="mt-3 text-lg font-semibold tracking-normal text-foreground">
              Adaptive quantization
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
              CogniX chooses the best quantization from your RAM, GPU and
              priority before any model file or runtime setting changes.
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Select
              value={priority}
              onValueChange={(value) => setPriority(value as QuantizationPriority)}
            >
              <SelectTrigger
                aria-label="Quantization priority"
                className="h-10 w-full rounded-full bg-background sm:w-44"
              >
                <SelectValue placeholder="Priority" />
              </SelectTrigger>
              <SelectContent>
                {PRIORITY_OPTIONS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => void loadPlan(priority, true)}
              disabled={loading}
              aria-label="Refresh quantization recommendation"
            >
              <RefreshCwIcon className="size-4" strokeWidth={1.75} />
            </Button>
            <Button
              type="button"
              className="h-10 rounded-full px-4"
              onClick={() => void saveProfile()}
              disabled={saving || !plan}
            >
              <SaveIcon className="mr-2 size-4" strokeWidth={1.75} />
              {saving ? "Saving..." : "Save profile"}
            </Button>
          </div>
        </div>

        {error ? (
          <div className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        ) : null}

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
          <div className="space-y-2">
            {loading && !selected ? (
              <>
                <Skeleton className="h-20 rounded-lg" />
                <Skeleton className="h-20 rounded-lg" />
              </>
            ) : selected ? (
              <>
                <VariantRow variant={selected} selected />
                {alternatives.map((variant) => (
                  <VariantRow key={variant.variantKey} variant={variant} />
                ))}
              </>
            ) : (
              <div className="rounded-lg border border-border/50 bg-background/70 px-3 py-6 text-center text-sm text-muted-foreground">
                Refresh to build a recommendation.
              </div>
            )}
          </div>

          <div className="rounded-lg border border-border/50 bg-background/70 px-3 py-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-[11px] text-muted-foreground">
                  Available RAM
                </div>
                <div className="mt-1 text-base font-semibold text-foreground">
                  {gbLabel(plan?.hardware.availableRamGb)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">
                  Max VRAM
                </div>
                <div className="mt-1 text-base font-semibold text-foreground">
                  {gbLabel(plan?.hardware.maxVramGb)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">
                  Priority
                </div>
                <div className="mt-1 text-base font-semibold text-foreground">
                  {priorityLabel(priority)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">
                  Apply mode
                </div>
                <div className="mt-1 text-base font-semibold text-foreground">
                  Confirm
                </div>
              </div>
            </div>
            <div className="mt-3 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
              {plan?.reason ??
                "No model load, conversion, download or runtime write happens here."}
            </div>
            <div className="mt-3">
              <ProfileSummary profile={latestProfile} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
