// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import type { UpdateStatus } from "@/hooks/use-tauri-update";
import type { CopySupportDiagnosticsResult } from "@/lib/tauri-diagnostics";
import { AnimatePresence, motion } from "motion/react";
import { Spinner } from "@/components/ui/spinner";
import { useEffect, useRef, useState } from "react";

interface UpdateScreenProps {
  status: UpdateStatus;
  logs: string[];
  progress: number;
  error: string | null;
  onRetry: () => void;
  onSkipRestart: () => void;
  onCopyDiagnostics: () => Promise<CopySupportDiagnosticsResult>;
}

const EASE_OUT_QUART: [number, number, number, number] = [0.165, 0.84, 0.44, 1];

function Logo() {
  return (
    <div className="flex flex-col items-center gap-3">
      <img
        src="/cognix-logo-512.png"
        alt="CogniX"
        className="cognix-logo-mark h-[92px] w-[92px] object-contain"
      />
      <div className="flex flex-col items-center gap-1">
        <span className="font-heading text-[34px] font-semibold leading-none text-foreground">
          CogniX
        </span>
        <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Desktop
        </span>
      </div>
    </div>
  );
}

function statusLabel(status: UpdateStatus): string {
  switch (status) {
    case "updating-backend":
      return "Mise a jour du backend...";
    case "downloading":
      return "Telechargement de la mise a jour...";
    case "installing":
      return "Installation de la mise a jour...";
    case "error":
      return "Mise a jour echouee";
    default:
      return "Mise a jour...";
  }
}

function statusSubtext(status: UpdateStatus, progress: number): string {
  switch (status) {
    case "updating-backend":
      return "Cette etape peut prendre quelques minutes. Garde CogniX ouvert.";
    case "downloading":
      return `${progress}% telecharges`;
    case "installing":
      return "CogniX va redemarrer dans un instant.";
    case "error":
      return "Un probleme est survenu pendant la mise a jour.";
    default:
      return "";
  }
}

function LogViewer({ logs }: { logs: string[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  if (logs.length === 0) return null;

  return (
    <div
      ref={scrollRef}
      className="mt-4 h-[180px] w-full max-w-xl overflow-y-auto rounded-lg border border-border/40 bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground"
    >
      {logs.map((line, i) => (
        <div key={i} className="whitespace-pre-wrap break-all">
          {line}
        </div>
      ))}
    </div>
  );
}

export function UpdateScreen({
  status,
  logs,
  progress,
  error,
  onRetry,
  onSkipRestart,
  onCopyDiagnostics,
}: UpdateScreenProps) {
  const isError = status === "error";
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
        setManualMessage(
          result.error ?? "Impossible de copier le diagnostic. Selectionne puis copie le rapport ci-dessous.",
        );
      }
    } catch (copyError) {
      setManualReport(null);
      setManualMessage(`Copie du diagnostic impossible : ${String(copyError)}`);
    } finally {
      setCopying(false);
    }
  }

  return (
    <div className="flex h-full w-full items-center justify-center bg-background">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE_OUT_QUART }}
        className="flex w-full max-w-xl flex-col items-center px-6"
      >
        <Logo />

        <div className="mt-8 flex flex-col items-center gap-2">
          {!isError && <Spinner className="size-6 text-primary" />}
          <p className="text-sm font-semibold text-foreground">
            {statusLabel(status)}
          </p>
          <p className="text-xs text-muted-foreground">
            {statusSubtext(status, progress)}
          </p>
        </div>

        {/* Download progress bar */}
        {status === "downloading" && (
          <div className="mt-4 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-muted">
            <motion.div
              className="h-full rounded-full bg-primary"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        )}

        {/* Error display */}
        <AnimatePresence>
          {isError && error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 w-full max-w-xl rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3"
            >
              <p className="text-xs text-destructive">{error}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error actions */}
        {isError && (
          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg bg-muted px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/80"
              onClick={() => void handleCopyDiagnostics()}
            >
              {copying ? "Copie..." : "Copier le diagnostic"}
            </button>
            <button
              type="button"
              className="rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
              onClick={onRetry}
            >
              Reessayer
            </button>
            <button
              type="button"
              className="rounded-lg bg-muted px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/80"
              onClick={onSkipRestart}
            >
              Ignorer et redemarrer
            </button>
          </div>
        )}

        {manualMessage && (
          <p className="mt-3 max-w-xl text-center text-xs text-destructive">{manualMessage}</p>
        )}
        {manualReport && (
          <textarea
            readOnly
            value={manualReport}
            onFocus={(event) => event.currentTarget.select()}
            className="mt-2 h-32 w-full max-w-xl resize-none rounded-lg border border-border/50 bg-muted/30 p-2 font-mono text-[10px] text-muted-foreground"
          />
        )}

        {/* Log viewer */}
        <LogViewer logs={logs} />
      </motion.div>
    </div>
  );
}
