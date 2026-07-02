// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { ShimmerButton } from "@/components/ui/shimmer-button";
import { Spinner } from "@/components/ui/spinner";
import {
  COGNIX_PLAN_OPTIONS,
  RECOMMENDED_COGNIX_PLAN_ID,
  saveCogniXPlanConfig,
  type CogniXPlanId,
} from "@/features/cognix-plan";
import type { BackendStatus } from "@/hooks/use-tauri-backend";
import type { CopySupportDiagnosticsResult } from "@/lib/tauri-diagnostics";
import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

interface StartupScreenProps {
  status: BackendStatus;
  logs: string[];
  error: string | null;
  currentStepIndex: number;
  progressDetail: string | null;
  elevationPackages: string[];
  onInstall: () => void;
  onRetry: () => void;
  onRetryInstall: () => void;
  onApproveElevation: () => void;
  onStartServer: () => void;
  onCopyDiagnostics: () => Promise<CopySupportDiagnosticsResult>;
}

function DiagnosticsCopyActions({
  onCopyDiagnostics,
  children,
}: {
  onCopyDiagnostics: () => Promise<CopySupportDiagnosticsResult>;
  children: React.ReactNode;
}) {
  const [copying, setCopying] = useState(false);
  const [manualReport, setManualReport] = useState<string | null>(null);
  const [manualMessage, setManualMessage] = useState<string | null>(null);

  async function handleCopyDiagnostics() {
    setCopying(true);
    try {
      const result = await onCopyDiagnostics();
      if (result.ok) {
        setManualReport(null);
        setManualMessage(null);
      } else {
        setManualReport(result.report);
        setManualMessage(result.error ?? "Clipboard copy failed. Select and copy the diagnostics below.");
      }
    } catch (error) {
      setManualReport(null);
      setManualMessage(`Diagnostics copy failed: ${String(error)}`);
    } finally {
      setCopying(false);
    }
  }

  return (
    <div className="mt-4 flex w-full flex-col items-center gap-3">
      <div className="flex gap-3">
        <ActionButton
          variant="secondary"
          onClick={() => void handleCopyDiagnostics()}
        >
          {copying ? "Copying..." : "Copy Diagnostics"}
        </ActionButton>
        {children}
      </div>
      {manualMessage && (
        <p className="max-w-md text-center text-xs text-destructive">{manualMessage}</p>
      )}
      {manualReport && (
        <textarea
          readOnly
          value={manualReport}
          onFocus={(event) => event.currentTarget.select()}
          className="h-32 w-full max-w-md resize-none rounded-lg border border-border/50 bg-muted/30 p-2 font-mono text-[10px] text-muted-foreground"
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const INSTALL_STEPS = [
  "Detecting your system",
  "Checking dependencies",
  "Setting up package manager",
  "Creating Python environment",
  "Installing ML framework",
  "Installing CogniX",
  "Finalizing setup",
] as const;

const EASE_OUT_QUART: [number, number, number, number] = [0.165, 0.84, 0.44, 1];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Logo() {
  return (
    <div className="flex flex-col items-center gap-3">
      <img
        src="/cognix-logo-512.png"
        alt="CogniX"
        className="cognix-logo-mark h-[82px] w-[82px] object-contain"
      />
      <div className="flex flex-col items-center gap-1">
        <span className="font-heading text-[32px] font-semibold leading-none text-foreground">
          CogniX
        </span>
        <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Desktop
        </span>
      </div>
    </div>
  );
}

function ActionButton({
  onClick,
  variant = "primary",
  children,
}: {
  onClick: () => void;
  variant?: "primary" | "secondary";
  children: React.ReactNode;
}) {
  const base = "rounded-lg px-5 py-2.5 text-sm font-medium cursor-pointer transition-colors";
  const styles =
    variant === "primary"
      ? `${base} bg-primary text-primary-foreground hover:bg-primary/80`
      : `${base} bg-muted text-foreground hover:bg-muted/80`;
  return (
    <button type="button" className={styles} onClick={onClick}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Per-status renderers
// ---------------------------------------------------------------------------

function CheckingContent() {
  return (
    <div className="flex h-full flex-col items-center">
      <div className="flex flex-1 items-center">
        <Logo />
      </div>
      <div className="mb-10 flex flex-col items-center gap-2">
        <Spinner className="size-6 text-primary" />
        <p className="text-sm text-muted-foreground">Checking...</p>
      </div>
    </div>
  );
}

function NotInstalledContent({ onInstall }: { onInstall: () => void }) {
  const [selectedPlanId, setSelectedPlanId] = useState<CogniXPlanId>(
    RECOMMENDED_COGNIX_PLAN_ID,
  );
  const selectedPlan =
    COGNIX_PLAN_OPTIONS.find((plan) => plan.id === selectedPlanId) ??
    COGNIX_PLAN_OPTIONS[0];

  function handleInstall() {
    saveCogniXPlanConfig(selectedPlanId);
    onInstall();
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col items-center overflow-y-auto px-1 py-5">
      <div className="flex shrink-0 flex-col items-center">
        <Logo />
        <p className="mt-4 max-w-xl text-center text-sm font-semibold text-foreground">
          Configure ton espace CogniX avant l'installation.
        </p>
        <p className="mt-1 max-w-xl text-center text-xs text-muted-foreground">
          Le profil choisi définit les outils affichés par défaut dans cette installation.
        </p>
      </div>

      <div className="mt-5 grid w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {COGNIX_PLAN_OPTIONS.map((plan) => {
          const selected = plan.id === selectedPlanId;
          return (
            <button
              key={plan.id}
              type="button"
              onClick={() => setSelectedPlanId(plan.id)}
              className={cn(
                "rounded-lg border px-3 py-3 text-left transition-all",
                "bg-card/60 hover:border-primary/50 hover:bg-card",
                selected
                  ? "border-primary shadow-sm ring-1 ring-primary/35"
                  : "border-border/60",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {plan.label}
                  </p>
                  <p className="mt-0.5 text-[11px] font-medium text-primary">
                    {plan.audience}
                  </p>
                </div>
                {plan.id === RECOMMENDED_COGNIX_PLAN_ID && (
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                    conseillé
                  </span>
                )}
              </div>
              <p className="mt-2 min-h-[32px] text-xs leading-4 text-muted-foreground">
                {plan.summary}
              </p>
              <ul className="mt-2 space-y-1">
                {plan.highlights.slice(0, 3).map((highlight) => (
                  <li
                    key={highlight}
                    className="flex gap-1.5 text-[11px] leading-4 text-muted-foreground"
                  >
                    <span className="mt-[6px] size-1 shrink-0 rounded-full bg-primary/70" />
                    <span>{highlight}</span>
                  </li>
                ))}
              </ul>
            </button>
          );
        })}
      </div>

      <motion.div
        key={selectedPlan.id}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: EASE_OUT_QUART }}
        className="mt-3 w-full rounded-lg border border-border/60 bg-muted/25 px-4 py-3 text-left"
      >
        <p className="text-xs font-semibold text-foreground">
          Pourquoi choisir {selectedPlan.label}
        </p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {selectedPlan.guidance}
        </p>
      </motion.div>

      <div className="mt-4 shrink-0 pb-2">
        <ShimmerButton
          onClick={handleInstall}
          shimmerColor="#a7f3d0"
          background="oklch(0.696 0.17 162.48)"
          className="text-sm font-medium"
        >
          Installer avec {selectedPlan.label}
        </ShimmerButton>
      </div>
    </div>
  );
}

function InstallingContent({
  currentStepIndex,
  progressDetail,
}: {
  currentStepIndex: number;
  progressDetail: string | null;
}) {
  const stepNum = Math.max(0, currentStepIndex) + 1;
  const stepLabel = INSTALL_STEPS[Math.min(currentStepIndex, INSTALL_STEPS.length - 1)];

  return (
    <div className="flex h-full flex-col items-center">
      <div className="flex flex-1 items-center">
        <Logo />
      </div>
      <div className="mb-10 flex flex-col items-center gap-2">
        <Spinner className="size-6 text-primary" />
        <p className="text-sm font-bold text-foreground">Installing...</p>
        <p className="text-sm font-bold text-muted-foreground">
          Please wait a few mins, then you can start training.
        </p>
        {currentStepIndex >= 0 && (
          <p className="mt-1 text-xs font-bold text-muted-foreground">
            Step {stepNum} of {INSTALL_STEPS.length}: {stepLabel}
          </p>
        )}
        {progressDetail && (
          <p className="text-xs text-muted-foreground/70">{progressDetail}</p>
        )}
      </div>
    </div>
  );
}

function RepairingContent({
  logs,
  progressDetail,
}: {
  logs: string[];
  progressDetail: string | null;
}) {
  const latest = progressDetail ?? logs.at(-1);

  return (
    <div className="flex h-full flex-col items-center">
      <div className="flex flex-1 items-center">
        <Logo />
      </div>
      <div className="mb-10 flex flex-col items-center gap-2">
        <Spinner className="size-6 text-primary" />
        <p className="text-sm font-bold text-foreground">Updating existing CogniX install...</p>
        {latest && (
          <p className="max-w-xs text-center text-xs text-muted-foreground">{latest}</p>
        )}
      </div>
    </div>
  );
}

function InstallErrorContent({
  error,
  onRetryInstall,
  onCopyDiagnostics,
}: {
  error: string | null;
  onRetryInstall: () => void;
  onCopyDiagnostics: () => Promise<CopySupportDiagnosticsResult>;
}) {
  return (
    <>
      <Logo />
      <div className="mt-8 flex flex-col items-center gap-2">
        <p className="text-sm font-medium text-destructive">Setup ran into a problem</p>
        {error && (
          <p className="max-w-xs text-center text-xs text-muted-foreground">{error}</p>
        )}
        <DiagnosticsCopyActions onCopyDiagnostics={onCopyDiagnostics}>
          <ActionButton onClick={onRetryInstall}>Try Again</ActionButton>
        </DiagnosticsCopyActions>
      </div>
    </>
  );
}

function RepairErrorContent({
  error,
  onRetry,
  onCopyDiagnostics,
}: {
  error: string | null;
  onRetry: () => void;
  onCopyDiagnostics: () => Promise<CopySupportDiagnosticsResult>;
}) {
  return (
    <>
      <Logo />
      <div className="mt-8 flex flex-col items-center gap-2">
        <p className="text-sm font-medium text-destructive">Update failed</p>
        {error && (
          <p className="max-w-md text-center text-xs text-muted-foreground">{error}</p>
        )}
        <DiagnosticsCopyActions onCopyDiagnostics={onCopyDiagnostics}>
          <ActionButton onClick={onRetry}>Retry</ActionButton>
        </DiagnosticsCopyActions>
      </div>
    </>
  );
}

function NeedsElevationContent({
  elevationPackages,
  onApproveElevation,
  onRetryInstall,
}: {
  elevationPackages: string[];
  onApproveElevation: () => void;
  onRetryInstall: () => void;
}) {
  return (
    <>
      <Logo />
      <div className="mt-8 flex flex-col items-center gap-2">
        <p className="text-sm font-medium text-foreground">Permission needed</p>
        <p className="text-xs text-muted-foreground">
          The following system packages need to be installed:
        </p>
        <div className="mt-2 w-full max-w-xs rounded-lg bg-muted p-3 font-mono text-xs">
          {elevationPackages.map((pkg) => (
            <div key={pkg}>{pkg}</div>
          ))}
        </div>
        <div className="mt-4 flex gap-3">
          <ActionButton variant="secondary" onClick={onRetryInstall}>Cancel</ActionButton>
          <ActionButton onClick={onApproveElevation}>Allow</ActionButton>
        </div>
      </div>
    </>
  );
}

function StartingContent() {
  return (
    <div className="flex h-full flex-col items-center">
      <div className="flex flex-1 items-center">
        <Logo />
      </div>
      <div className="mb-10 flex flex-col items-center gap-2">
        <Spinner className="size-6 text-primary" />
        <p className="text-sm text-muted-foreground">Starting server...</p>
      </div>
    </div>
  );
}

function StoppedContent({ onStartServer }: { onStartServer: () => void }) {
  return (
    <>
      <Logo />
      <div className="mt-8 flex flex-col items-center gap-2">
        <p className="text-sm font-medium text-foreground">Server stopped</p>
        <div className="mt-4">
          <ActionButton onClick={onStartServer}>Start Server</ActionButton>
        </div>
      </div>
    </>
  );
}

function ErrorContent({
  error,
  onRetry,
  onCopyDiagnostics,
}: {
  error: string | null;
  onRetry: () => void;
  onCopyDiagnostics: () => Promise<CopySupportDiagnosticsResult>;
}) {
  return (
    <>
      <Logo />
      <div className="mt-8 flex flex-col items-center gap-2">
        <p className="text-sm font-medium text-destructive">Something went wrong</p>
        {error && (
          <p className="max-w-md text-center text-xs text-muted-foreground">{error}</p>
        )}
        <DiagnosticsCopyActions onCopyDiagnostics={onCopyDiagnostics}>
          <ActionButton onClick={onRetry}>Retry</ActionButton>
        </DiagnosticsCopyActions>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function StartupScreen({
  status,
  logs,
  error,
  currentStepIndex,
  progressDetail,
  elevationPackages,
  onInstall,
  onRetry,
  onRetryInstall,
  onApproveElevation,
  onStartServer,
  onCopyDiagnostics,
}: StartupScreenProps) {
  function renderContent() {
    switch (status) {
      case "checking":
        return <CheckingContent />;
      case "not-installed":
        return <NotInstalledContent onInstall={onInstall} />;
      case "installing":
        return <InstallingContent currentStepIndex={currentStepIndex} progressDetail={progressDetail} />;
      case "install-error":
        return (
          <InstallErrorContent
            error={error}
            onRetryInstall={onRetryInstall}
            onCopyDiagnostics={onCopyDiagnostics}
          />
        );
      case "repairing":
        return <RepairingContent logs={logs} progressDetail={progressDetail} />;
      case "repair-error":
        return (
          <RepairErrorContent
            error={error}
            onRetry={onRetry}
            onCopyDiagnostics={onCopyDiagnostics}
          />
        );
      case "needs-elevation":
        return (
          <NeedsElevationContent
            elevationPackages={elevationPackages}
            onApproveElevation={onApproveElevation}
            onRetryInstall={onRetryInstall}
          />
        );
      case "starting":
        return <StartingContent />;
      case "running":
        return null;
      case "stopped":
        return <StoppedContent onStartServer={onStartServer} />;
      case "error":
        return (
          <ErrorContent
            error={error}
            onRetry={onRetry}
            onCopyDiagnostics={onCopyDiagnostics}
          />
        );
    }
  }

  return (
    <div className="flex h-full w-full flex-col items-center bg-background">
      <div className="flex flex-1 min-h-0 w-full max-w-[940px] items-center justify-center px-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={status}
            className="flex h-full w-full flex-col items-center text-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE_OUT_QUART }}
          >
            {renderContent()}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
