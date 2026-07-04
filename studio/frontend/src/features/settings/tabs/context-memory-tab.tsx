// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  approveSkillMemoryCandidate,
  buildSkillMemoryCandidates,
  buildSkillMemoryInjectionPlan,
  deleteSkillMemory,
  exportSkillMemory,
  listSkillMemories,
  listSkillMemoryCandidates,
  loadContextMemory,
  rejectSkillMemoryCandidate,
  saveContextMemory,
  type SkillMemoryCandidate,
  type SkillMemoryDecision,
  type SkillMemoryInjectionPlanResponse,
  type SkillMemoryRecord,
  type SkillMemoryUpdate,
  type UserPreferenceRecord,
  updateSkillMemory,
} from "../api/skill-memory";
import { SettingsRow } from "../components/settings-row";
import { SettingsSection } from "../components/settings-section";

type LoadState = "idle" | "loading" | "loaded" | "error" | "saving";
type MemoryDraft = Required<
  Pick<SkillMemoryUpdate, "category" | "label" | "value">
> & { status: "active" | "disabled" };

const inputClassName =
  "h-9 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20";

const textareaClassName =
  "min-h-[86px] w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20";

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function formatConfidence(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "unknown";
  return `${Math.round(value * 100)}%`;
}

function candidateType(candidate: SkillMemoryCandidate): string {
  return candidate.candidateType || asText(candidate.candidate?.candidateType) || "memory";
}

function candidateCategory(candidate: SkillMemoryCandidate): string {
  return candidate.category || asText(candidate.candidate?.category) || "general";
}

function candidateLabel(candidate: SkillMemoryCandidate): string {
  return candidate.label || asText(candidate.candidate?.label);
}

function candidateValue(candidate: SkillMemoryCandidate): string {
  return candidate.value || asText(candidate.candidate?.value);
}

function candidateEvidence(candidate: SkillMemoryCandidate): string {
  return (
    candidate.evidenceExcerpt ||
    asText(candidate.candidate?.evidenceExcerpt) ||
    "No evidence excerpt stored."
  );
}

function buildCandidateDraft(candidate: SkillMemoryCandidate): SkillMemoryDecision {
  return {
    category: candidateCategory(candidate),
    label: candidateLabel(candidate),
    value: candidateValue(candidate),
  };
}

function buildMemoryDraft(memory: SkillMemoryRecord): MemoryDraft {
  return {
    category: memory.category ?? "general",
    label: memory.label ?? "",
    value: memory.value ?? "",
    status: memory.status === "disabled" ? "disabled" : "active",
  };
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function EmptyState({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border/70 px-3 py-4 text-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted-foreground">
      {label}
      {children}
    </label>
  );
}

function PreferenceList({
  preferences,
}: {
  preferences: UserPreferenceRecord[];
}) {
  const activePreferences = preferences.filter(
    (preference) => preference.status !== "disabled",
  );
  if (!activePreferences.length) {
    return <EmptyState>No active preference has been approved yet.</EmptyState>;
  }
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:flex-wrap">
      {activePreferences.map((preference) => (
        <span
          key={preference.id}
          className="inline-flex min-w-0 max-w-full items-center overflow-hidden rounded-full border border-border bg-muted/40 px-3 py-1 text-xs text-foreground sm:w-auto"
        >
          <span className="shrink-0 text-muted-foreground">
            {preference.category ?? "general"}
          </span>
          <span className="shrink-0 px-1">·</span>
          <span className="min-w-0 truncate">
            {preference.value ?? preference.preferenceKey ?? "Preference"}
          </span>
        </span>
      ))}
    </div>
  );
}

export function ContextMemoryTab() {
  const [contextMemory, setContextMemory] = useState("");
  const [contextState, setContextState] = useState<LoadState>("idle");
  const [skillState, setSkillState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [observation, setObservation] = useState("");
  const [candidates, setCandidates] = useState<SkillMemoryCandidate[]>([]);
  const [memories, setMemories] = useState<SkillMemoryRecord[]>([]);
  const [preferences, setPreferences] = useState<UserPreferenceRecord[]>([]);
  const [editingCandidateId, setEditingCandidateId] = useState<string | null>(
    null,
  );
  const [candidateDrafts, setCandidateDrafts] = useState<
    Record<string, SkillMemoryDecision>
  >({});
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [memoryDrafts, setMemoryDrafts] = useState<Record<string, MemoryDraft>>(
    {},
  );
  const [objective, setObjective] = useState("");
  const [injectionPlan, setInjectionPlan] =
    useState<SkillMemoryInjectionPlanResponse["injectionPlan"]>(undefined);

  const pendingCandidates = useMemo(
    () =>
      candidates.filter(
        (candidate) =>
          (candidate.status ?? "pending_validation") === "pending_validation",
      ),
    [candidates],
  );

  const activeMemories = useMemo(
    () => memories.filter((memory) => memory.status !== "disabled"),
    [memories],
  );

  const disabledMemories = useMemo(
    () => memories.filter((memory) => memory.status === "disabled"),
    [memories],
  );

  const loadSharedContext = useCallback(async () => {
    setContextState("loading");
    try {
      const data = await loadContextMemory();
      setContextMemory(data.memory?.content ?? "");
      setContextState("loaded");
    } catch (currentError) {
      setContextState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to load CogniX memory.",
      );
    }
  }, []);

  const refreshSkillMemory = useCallback(async () => {
    setSkillState("loading");
    try {
      const [memoryData, candidateData] = await Promise.all([
        listSkillMemories(true),
        listSkillMemoryCandidates(true),
      ]);
      setMemories(memoryData.skillMemories ?? []);
      setPreferences(memoryData.preferences ?? []);
      setCandidates(candidateData.candidates ?? []);
      setSkillState("loaded");
      setError(null);
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to load skill memory.",
      );
    }
  }, []);

  useEffect(() => {
    void loadSharedContext();
    void refreshSkillMemory();
  }, [loadSharedContext, refreshSkillMemory]);

  async function saveSharedContext() {
    setContextState("saving");
    setMessage(null);
    setError(null);
    try {
      await saveContextMemory(contextMemory);
      setContextState("loaded");
      setMessage("Shared memory saved.");
    } catch (currentError) {
      setContextState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to save shared memory.",
      );
    }
  }

  async function proposeCandidates() {
    const trimmedObservation = observation.trim();
    if (!trimmedObservation) {
      setMessage("Write an observation before asking CogniX to remember it.");
      return;
    }
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      const result = await buildSkillMemoryCandidates(trimmedObservation);
      await refreshSkillMemory();
      const count =
        result.storedCandidates?.length ??
        result.candidateMemoryPlan?.summary?.candidateCount ??
        0;
      setObservation("");
      setMessage(
        count > 0
          ? `${count} candidate memory${count > 1 ? "ies" : "y"} ready for approval.`
          : "No new candidate was found from this observation.",
      );
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to propose candidate memories.",
      );
    }
  }

  function updateCandidateDraft(
    candidate: SkillMemoryCandidate,
    patch: SkillMemoryDecision,
  ) {
    setCandidateDrafts((current) => ({
      ...current,
      [candidate.id]: {
        ...buildCandidateDraft(candidate),
        ...current[candidate.id],
        ...patch,
      },
    }));
  }

  async function approveCandidate(candidate: SkillMemoryCandidate) {
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      await approveSkillMemoryCandidate(
        candidate.id,
        candidateDrafts[candidate.id] ?? buildCandidateDraft(candidate),
      );
      setEditingCandidateId(null);
      await refreshSkillMemory();
      setMessage("Memory approved and activated.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to approve this memory.",
      );
    }
  }

  async function rejectCandidate(candidateId: string) {
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      await rejectSkillMemoryCandidate(candidateId);
      await refreshSkillMemory();
      setMessage("Candidate dismissed.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to reject this candidate.",
      );
    }
  }

  function editMemory(memory: SkillMemoryRecord) {
    setMemoryDrafts((current) => ({
      ...current,
      [memory.id]: current[memory.id] ?? buildMemoryDraft(memory),
    }));
    setEditingMemoryId(memory.id);
  }

  function updateMemoryDraft(memory: SkillMemoryRecord, patch: SkillMemoryUpdate) {
    setMemoryDrafts((current) => ({
      ...current,
      [memory.id]: {
        ...buildMemoryDraft(memory),
        ...current[memory.id],
        ...patch,
      },
    }));
  }

  async function saveMemory(memory: SkillMemoryRecord) {
    const draft = memoryDrafts[memory.id] ?? buildMemoryDraft(memory);
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      await updateSkillMemory(memory.id, draft);
      setEditingMemoryId(null);
      await refreshSkillMemory();
      setMessage("Memory updated.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to update this memory.",
      );
    }
  }

  async function setMemoryStatus(
    memory: SkillMemoryRecord,
    status: "active" | "disabled",
  ) {
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      await updateSkillMemory(memory.id, { status });
      await refreshSkillMemory();
      setMessage(status === "active" ? "Memory enabled." : "Memory disabled.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to change memory status.",
      );
    }
  }

  async function removeMemory(memoryId: string) {
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      await deleteSkillMemory(memoryId);
      await refreshSkillMemory();
      setMessage("Memory deleted.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to delete this memory.",
      );
    }
  }

  async function previewInjectionPlan() {
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      const result = await buildSkillMemoryInjectionPlan(objective);
      setInjectionPlan(result.injectionPlan);
      setSkillState("loaded");
      setMessage("Injection plan refreshed.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to preview memory injection.",
      );
    }
  }

  async function downloadExport() {
    setSkillState("saving");
    setMessage(null);
    setError(null);
    try {
      const payload = await exportSkillMemory();
      downloadJson("cognix-skill-memory.json", payload.memoryExport ?? payload);
      setSkillState("loaded");
      setMessage("Memory export prepared.");
    } catch (currentError) {
      setSkillState("error");
      setError(
        currentError instanceof Error
          ? currentError.message
          : "Unable to export skill memory.",
      );
    }
  }

  const busy = contextState === "saving" || skillState === "saving";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1 pr-8">
        <h1 className="font-heading text-xl font-semibold">Memory</h1>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Manage what CogniX can remember, approve, edit, disable, delete, and
          export.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      ) : null}
      {message ? (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">
          {message}
        </div>
      ) : null}

      <SettingsSection
        title="Skill memory"
        description="CogniX proposes memories from observations. Nothing becomes active before approval."
      >
        <div className="flex flex-col gap-3 py-3">
          <textarea
            value={observation}
            onChange={(event) => setObservation(event.target.value)}
            className={textareaClassName}
            placeholder="Example: Kamil prefers Python for prototypes and local tools when possible."
            disabled={busy}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              Pending approval: {pendingCandidates.length} · Active memories:{" "}
              {activeMemories.length}
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void refreshSkillMemory()}
                disabled={busy}
              >
                Refresh
              </Button>
              <Button
                type="button"
                variant="dark"
                size="sm"
                onClick={() => void proposeCandidates()}
                disabled={busy}
              >
                Propose
              </Button>
            </div>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Approval queue"
        description="Validate, adjust, or reject candidate memories before they are used."
      >
        <div className="flex flex-col gap-2 py-3">
          {pendingCandidates.length ? (
            pendingCandidates.map((candidate) => {
              const editing = editingCandidateId === candidate.id;
              const draft =
                candidateDrafts[candidate.id] ?? buildCandidateDraft(candidate);
              return (
                <article
                  key={candidate.id}
                  className="flex flex-col gap-3 rounded-lg border border-border bg-muted/20 p-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-foreground">
                          {candidateLabel(candidate) || "Candidate memory"}
                        </h3>
                        <span className="rounded-full bg-background px-2 py-0.5 text-[11px] text-muted-foreground">
                          {candidateType(candidate)}
                        </span>
                        <span className="rounded-full bg-background px-2 py-0.5 text-[11px] text-muted-foreground">
                          {formatConfidence(candidate.confidence)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        {candidateEvidence(candidate)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        onClick={() =>
                          setEditingCandidateId(editing ? null : candidate.id)
                        }
                        disabled={busy}
                      >
                        {editing ? "Close" : "Edit"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        onClick={() => void rejectCandidate(candidate.id)}
                        disabled={busy}
                      >
                        Reject
                      </Button>
                      <Button
                        type="button"
                        variant="dark"
                        size="xs"
                        onClick={() => void approveCandidate(candidate)}
                        disabled={busy}
                      >
                        Approve
                      </Button>
                    </div>
                  </div>
                  {editing ? (
                    <div className="grid gap-2 md:grid-cols-[1fr_140px]">
                      <Field label="Label">
                        <input
                          value={draft.label ?? ""}
                          onChange={(event) =>
                            updateCandidateDraft(candidate, {
                              label: event.target.value,
                            })
                          }
                          className={inputClassName}
                          disabled={busy}
                        />
                      </Field>
                      <Field label="Category">
                        <input
                          value={draft.category ?? ""}
                          onChange={(event) =>
                            updateCandidateDraft(candidate, {
                              category: event.target.value,
                            })
                          }
                          className={inputClassName}
                          disabled={busy}
                        />
                      </Field>
                      <Field label="Memory">
                        <textarea
                          value={draft.value ?? ""}
                          onChange={(event) =>
                            updateCandidateDraft(candidate, {
                              value: event.target.value,
                            })
                          }
                          className={cn(textareaClassName, "md:col-span-2")}
                          disabled={busy}
                        />
                      </Field>
                    </div>
                  ) : (
                    <p className="text-sm leading-relaxed text-foreground">
                      {candidateValue(candidate)}
                    </p>
                  )}
                </article>
              );
            })
          ) : (
            <EmptyState>No candidate is waiting for approval.</EmptyState>
          )}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Active memories"
        description="Only active memories can be considered by the context injector."
      >
        <div className="flex flex-col gap-2 py-3">
          {memories.length ? (
            memories.map((memory) => {
              const editing = editingMemoryId === memory.id;
              const draft = memoryDrafts[memory.id] ?? buildMemoryDraft(memory);
              return (
                <article
                  key={memory.id}
                  className={cn(
                    "flex flex-col gap-3 rounded-lg border border-border p-3",
                    memory.status === "disabled"
                      ? "bg-muted/10 opacity-75"
                      : "bg-muted/20",
                  )}
                >
                  {editing ? (
                    <div className="grid gap-2 md:grid-cols-[1fr_140px]">
                      <Field label="Label">
                        <input
                          value={draft.label}
                          onChange={(event) =>
                            updateMemoryDraft(memory, {
                              label: event.target.value,
                            })
                          }
                          className={inputClassName}
                          disabled={busy}
                        />
                      </Field>
                      <Field label="Category">
                        <input
                          value={draft.category}
                          onChange={(event) =>
                            updateMemoryDraft(memory, {
                              category: event.target.value,
                            })
                          }
                          className={inputClassName}
                          disabled={busy}
                        />
                      </Field>
                      <Field label="Memory">
                        <textarea
                          value={draft.value}
                          onChange={(event) =>
                            updateMemoryDraft(memory, {
                              value: event.target.value,
                            })
                          }
                          className={cn(textareaClassName, "md:col-span-2")}
                          disabled={busy}
                        />
                      </Field>
                    </div>
                  ) : (
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-foreground">
                          {memory.label || "Memory"}
                        </h3>
                        <span className="rounded-full bg-background px-2 py-0.5 text-[11px] text-muted-foreground">
                          {memory.category ?? "general"}
                        </span>
                        <span className="rounded-full bg-background px-2 py-0.5 text-[11px] text-muted-foreground">
                          {memory.status ?? "active"}
                        </span>
                      </div>
                      <p className="mt-1 text-sm leading-relaxed text-foreground">
                        {memory.value}
                      </p>
                    </div>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs text-muted-foreground">
                      Confidence {formatConfidence(memory.confidence)}
                    </span>
                    <div className="flex items-center gap-2">
                      {editing ? (
                        <>
                          <Button
                            type="button"
                            variant="ghost"
                            size="xs"
                            onClick={() => setEditingMemoryId(null)}
                            disabled={busy}
                          >
                            Cancel
                          </Button>
                          <Button
                            type="button"
                            variant="dark"
                            size="xs"
                            onClick={() => void saveMemory(memory)}
                            disabled={busy}
                          >
                            Save
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button
                            type="button"
                            variant="ghost"
                            size="xs"
                            onClick={() => editMemory(memory)}
                            disabled={busy}
                          >
                            Edit
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="xs"
                            onClick={() =>
                              void setMemoryStatus(
                                memory,
                                memory.status === "disabled"
                                  ? "active"
                                  : "disabled",
                              )
                            }
                            disabled={busy}
                          >
                            {memory.status === "disabled" ? "Enable" : "Disable"}
                          </Button>
                          <Button
                            type="button"
                            variant="destructive"
                            size="xs"
                            onClick={() => void removeMemory(memory.id)}
                            disabled={busy}
                          >
                            Delete
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </article>
              );
            })
          ) : (
            <EmptyState>No approved memory yet.</EmptyState>
          )}
          {disabledMemories.length ? (
            <p className="text-xs text-muted-foreground">
              Disabled memories stay visible here so they can be restored.
            </p>
          ) : null}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Preferences"
        description="Approved preference memories are mirrored here for native personalization."
      >
        <PreferenceList preferences={preferences} />
      </SettingsSection>

      <SettingsSection
        title="Context injection preview"
        description="Preview which active memories would be selected. This does not inject anything by itself."
      >
        <div className="flex flex-col gap-3 py-3">
          <div className="flex flex-col gap-2 md:flex-row">
            <input
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              className={inputClassName}
              placeholder="Objective, project, or next chat request"
              disabled={busy}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start text-foreground md:self-auto"
              onClick={() => void previewInjectionPlan()}
              disabled={busy}
            >
              Preview
            </Button>
          </div>
          {injectionPlan ? (
            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>
                  Available:{" "}
                  {injectionPlan.summary?.availableMemoryCount ??
                    activeMemories.length}
                </span>
                <span>
                  Selected:{" "}
                  {injectionPlan.summary?.selectedMemoryCount ??
                    injectionPlan.selectedMemories?.length ??
                    0}
                </span>
                <span>Inject now: no</span>
              </div>
              <div className="mt-3 flex flex-col gap-2">
                {injectionPlan.selectedMemories?.length ? (
                  injectionPlan.selectedMemories.map((memory) => (
                    <div
                      key={memory.id ?? memory.label}
                      className="rounded-lg bg-background px-3 py-2 text-sm text-foreground"
                    >
                      <span className="font-medium">
                        {memory.label ?? "Memory"}
                      </span>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        {memory.value}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No memory matched this objective.
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Shared memory"
        description="Stable instructions kept in CogniX context across sessions."
      >
        <div className="py-3">
          <textarea
            value={contextMemory}
            onChange={(event) => {
              setContextMemory(event.target.value);
              setMessage(null);
            }}
            rows={6}
            className="min-h-[132px] w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20"
            placeholder="Stable CogniX directives..."
            disabled={contextState === "loading" || contextState === "saving"}
          />
        </div>
        <SettingsRow
          label="Shared directives"
          description={
            contextState === "loading"
              ? "Loading..."
              : "Stored in the native CogniX local database."
          }
        >
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setContextMemory("")}
              disabled={contextState === "loading" || contextState === "saving"}
            >
              Clear
            </Button>
            <Button
              type="button"
              variant="dark"
              size="sm"
              onClick={() => void saveSharedContext()}
              disabled={contextState === "loading" || contextState === "saving"}
            >
              {contextState === "saving" ? "Saving..." : "Save"}
            </Button>
          </div>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Export"
        description="Download the skill memory bundle with candidates and preferences."
      >
        <SettingsRow
          label="Portable memory bundle"
          description="Useful before large refactors or moving CogniX to another machine."
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void downloadExport()}
            disabled={busy}
          >
            Export
          </Button>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
