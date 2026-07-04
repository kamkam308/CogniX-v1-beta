// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

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
  ArchiveIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  CopyPlusIcon,
  DownloadIcon,
  FileJsonIcon,
  GitBranchIcon,
  PencilIcon,
  PlayIcon,
  PlusIcon,
  RefreshCwIcon,
  SaveIcon,
  Share2Icon,
  ShieldCheckIcon,
  Trash2Icon,
  WorkflowIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  buildWorkflowRunPlan,
  deleteWorkflow,
  exportWorkflowBundle,
  getWorkflow,
  listWorkflowRuns,
  listWorkflows,
  listWorkflowTemplates,
  recordWorkflow,
  updateWorkflow,
  type WorkflowRecord,
  type WorkflowRunPlan,
  type WorkflowRunRecord,
  type WorkflowStepInput,
  type WorkflowStepType,
  type WorkflowTemplate,
} from "../api/chat-api";

type DraftStep = {
  id: string;
  stepType: WorkflowStepType;
  label: string;
  toolName: string;
  modelId: string;
  outputSummary: string;
  parametersText: string;
  requiresApproval: boolean;
};

type WorkflowDraft = {
  title: string;
  objective: string;
  workflowType: string;
  steps: DraftStep[];
};

type SelectedWorkflowEdit = {
  title: string;
  objective: string;
  status: "active" | "disabled" | "archived";
  shareStatus: "private" | "shared";
};

const STEP_TYPE_OPTIONS: Array<{ value: WorkflowStepType; label: string }> = [
  { value: "user_action", label: "User action" },
  { value: "tool_call", label: "Tool call" },
  { value: "model_call", label: "Model call" },
  { value: "parameters", label: "Parameters" },
  { value: "output", label: "Output" },
  { value: "export", label: "Export" },
  { value: "approval", label: "Approval" },
];

const WORKFLOW_TYPES = [
  { value: "rag", label: "RAG" },
  { value: "fine_tuning", label: "Fine-tuning" },
  { value: "code", label: "Code" },
  { value: "document", label: "Document" },
  { value: "custom", label: "Custom" },
];

function newDraftStepId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `step_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function emptyDraftStep(index: number): DraftStep {
  return {
    id: newDraftStepId(),
    stepType: "user_action",
    label: `Step ${index + 1}`,
    toolName: "",
    modelId: "",
    outputSummary: "",
    parametersText: "",
    requiresApproval: false,
  };
}

function draftStepFromInput(
  step: WorkflowStepInput,
  index: number,
): DraftStep {
  const parameters = step.parameters ?? {};
  return {
    id: newDraftStepId(),
    stepType: step.stepType || "user_action",
    label: step.label || `Step ${index + 1}`,
    toolName: step.toolName ?? "",
    modelId: step.modelId ?? "",
    outputSummary: step.outputSummary ?? "",
    parametersText:
      Object.keys(parameters).length > 0 ? JSON.stringify(parameters, null, 2) : "",
    requiresApproval:
      step.requiresApproval ??
      ["tool_call", "model_call", "export"].includes(step.stepType),
  };
}

function createDraft(
  projectName: string,
  template?: WorkflowTemplate | null,
): WorkflowDraft {
  const templateSteps = template?.steps ?? [];
  const steps =
    templateSteps.length > 0
      ? templateSteps.map(draftStepFromInput)
      : [
          {
            stepType: "user_action",
            label: "Receive user request",
            requiresApproval: false,
          },
          {
            stepType: "model_call",
            label: "Build response plan",
            requiresApproval: true,
          },
          {
            stepType: "output",
            label: "Return final output",
            requiresApproval: false,
          },
        ].map(draftStepFromInput);
  return {
    title: template?.label ?? `${projectName} workflow`,
    objective: "",
    workflowType: template?.workflowType ?? "custom",
    steps,
  };
}

function draftFromWorkflow(workflow: WorkflowRecord): WorkflowDraft {
  return {
    title: workflow.title,
    objective: workflow.objective ?? "",
    workflowType: workflow.workflowType || "custom",
    steps:
      workflow.steps && workflow.steps.length > 0
        ? workflow.steps.map(draftStepFromInput)
        : [emptyDraftStep(0)],
  };
}

function selectedEditFromWorkflow(
  workflow: WorkflowRecord | null,
): SelectedWorkflowEdit {
  return {
    title: workflow?.title ?? "",
    objective: workflow?.objective ?? "",
    status:
      workflow?.status === "disabled" || workflow?.status === "archived"
        ? workflow.status
        : "active",
    shareStatus: workflow?.shareStatus === "shared" ? "shared" : "private",
  };
}

function workflowTypeLabel(type: string | undefined): string {
  return (
    WORKFLOW_TYPES.find((item) => item.value === type)?.label ??
    (type ? type.replace(/[_-]+/g, " ") : "Custom")
  );
}

function stepTypeLabel(type: string | undefined): string {
  return (
    STEP_TYPE_OPTIONS.find((item) => item.value === type)?.label ??
    (type ? type.replace(/[_-]+/g, " ") : "Step")
  );
}

function formatWorkflowDate(value: string | null | undefined): string {
  if (!value) return "not saved";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return "saved";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(time);
}

function parseStepParameters(step: DraftStep, index: number): Record<string, unknown> {
  if (!step.parametersText.trim()) return {};
  const parsed = JSON.parse(step.parametersText) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`Step ${index + 1} parameters must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function serializeDraftSteps(steps: DraftStep[]): WorkflowStepInput[] {
  return steps.map((step, index) => ({
    stepType: step.stepType,
    label: step.label.trim() || `Step ${index + 1}`,
    toolName: step.toolName.trim() || null,
    modelId: step.modelId.trim() || null,
    outputSummary: step.outputSummary.trim() || null,
    parameters: parseStepParameters(step, index),
    requiresApproval: step.requiresApproval,
  }));
}

function isPlanSafe(runPlan: WorkflowRunPlan | null): boolean {
  if (!runPlan) return true;
  const sideEffects = runPlan.sideEffects ?? {};
  return (
    runPlan.summary?.willExecuteNow === false &&
    sideEffects.generation === false &&
    sideEffects.toolExecution === false &&
    sideEffects.modelLoad === false &&
    sideEffects.networkCall === false
  );
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function WorkflowStepsEditor({
  steps,
  disabled,
  onChange,
}: {
  steps: DraftStep[];
  disabled: boolean;
  onChange: (steps: DraftStep[]) => void;
}) {
  const updateStep = (index: number, patch: Partial<DraftStep>) => {
    onChange(
      steps.map((step, currentIndex) =>
        currentIndex === index ? { ...step, ...patch } : step,
      ),
    );
  };

  const moveStep = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= steps.length) return;
    const next = [...steps];
    const [step] = next.splice(index, 1);
    next.splice(nextIndex, 0, step);
    onChange(next);
  };

  return (
    <div className="space-y-3">
      {steps.map((step, index) => (
        <div key={step.id} className="relative pl-9">
          <span className="absolute left-3 top-10 h-[calc(100%-2.5rem)] w-px bg-border/70 last:hidden" />
          <span className="absolute left-0 top-3 flex size-7 items-center justify-center rounded-full bg-background text-xs font-semibold text-muted-foreground ring-1 ring-border">
            {index + 1}
          </span>
          <div className="rounded-[18px] bg-background/70 p-3">
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_160px]">
              <Input
                value={step.label}
                disabled={disabled}
                onChange={(event) =>
                  updateStep(index, { label: event.target.value })
                }
                placeholder="Step label"
                className="h-10 rounded-2xl bg-input/40 text-sm"
              />
              <Select
                value={step.stepType}
                disabled={disabled}
                onValueChange={(value) =>
                  updateStep(index, {
                    stepType: value,
                    requiresApproval: ["tool_call", "model_call", "export"].includes(
                      value,
                    ),
                  })
                }
              >
                <SelectTrigger className="h-10 w-full rounded-2xl bg-input/40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STEP_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <details className="group mt-2">
              <summary className="cursor-pointer list-none text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
                Details
              </summary>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <Input
                  value={step.toolName}
                  disabled={disabled}
                  onChange={(event) =>
                    updateStep(index, { toolName: event.target.value })
                  }
                  placeholder="Tool"
                  className="h-9 rounded-2xl bg-input/40 text-sm"
                />
                <Input
                  value={step.modelId}
                  disabled={disabled}
                  onChange={(event) =>
                    updateStep(index, { modelId: event.target.value })
                  }
                  placeholder="Model"
                  className="h-9 rounded-2xl bg-input/40 text-sm"
                />
                <Textarea
                  value={step.outputSummary}
                  disabled={disabled}
                  onChange={(event) =>
                    updateStep(index, { outputSummary: event.target.value })
                  }
                  placeholder="Output summary"
                  className="min-h-18 rounded-[18px] bg-input/40 text-sm sm:col-span-2"
                />
                <Textarea
                  value={step.parametersText}
                  disabled={disabled}
                  onChange={(event) =>
                    updateStep(index, { parametersText: event.target.value })
                  }
                  placeholder='{"key":"value"}'
                  className="min-h-18 rounded-[18px] bg-input/40 font-mono text-xs sm:col-span-2"
                />
              </div>
            </details>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={step.requiresApproval}
                  disabled={disabled}
                  onChange={(event) =>
                    updateStep(index, {
                      requiresApproval: event.target.checked,
                    })
                  }
                  className="size-4 accent-primary"
                />
                Approval
              </label>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  disabled={disabled || index === 0}
                  aria-label="Move step up"
                  onClick={() => moveStep(index, -1)}
                  className="size-8 rounded-full"
                >
                  <ArrowUpIcon className="size-4" strokeWidth={1.75} />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  disabled={disabled || index === steps.length - 1}
                  aria-label="Move step down"
                  onClick={() => moveStep(index, 1)}
                  className="size-8 rounded-full"
                >
                  <ArrowDownIcon className="size-4" strokeWidth={1.75} />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  disabled={disabled || steps.length === 1}
                  aria-label="Remove step"
                  onClick={() =>
                    onChange(steps.filter((_, currentIndex) => currentIndex !== index))
                  }
                  className="size-8 rounded-full text-muted-foreground hover:text-destructive"
                >
                  <Trash2Icon className="size-4" strokeWidth={1.75} />
                </Button>
              </div>
            </div>
          </div>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        disabled={disabled}
        onClick={() => onChange([...steps, emptyDraftStep(steps.length)])}
        className="ml-9 border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
      >
        <PlusIcon className="size-4" strokeWidth={1.75} />
        Add step
      </Button>
    </div>
  );
}

function WorkflowRunPlanPreview({
  runPlan,
  runs,
}: {
  runPlan: WorkflowRunPlan | null;
  runs: WorkflowRunRecord[];
}) {
  if (!runPlan && runs.length === 0) return null;
  const steps = runPlan?.orderedSteps ?? [];
  return (
    <div className="rounded-[22px] bg-background/70 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
          <ShieldCheckIcon className="size-3.5" strokeWidth={1.75} />
          {isPlanSafe(runPlan) ? "dry-run only" : "review needed"}
        </span>
        {runPlan?.runMode ? (
          <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
            {runPlan.runMode}
          </span>
        ) : null}
        {runs[0]?.createdAt ? (
          <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
            {formatWorkflowDate(runs[0].createdAt)}
          </span>
        ) : null}
      </div>
      {steps.length > 0 ? (
        <div className="space-y-2">
          {steps.map((step, index) => (
            <div
              key={step.stepId ?? `${step.stepIndex}:${index}`}
              className="flex items-center gap-3 rounded-[16px] bg-muted/40 px-3 py-2"
            >
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-background text-xs font-semibold text-muted-foreground">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {step.label ?? `Step ${index + 1}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  {stepTypeLabel(step.stepType)}
                </p>
              </div>
              <span className="rounded-full bg-background px-2 py-1 text-[11px] text-muted-foreground">
                blocked
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {runs.length} planned run{runs.length === 1 ? "" : "s"}
        </p>
      )}
    </div>
  );
}

export function ProjectWorkflowRecorderPanel({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowRecord[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] =
    useState<WorkflowRecord | null>(null);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(
    null,
  );
  const [selectedEdit, setSelectedEdit] = useState<SelectedWorkflowEdit>(
    selectedEditFromWorkflow(null),
  );
  const [draft, setDraft] = useState<WorkflowDraft>(() =>
    createDraft(projectName),
  );
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRunRecord[]>([]);
  const [runPlan, setRunPlan] = useState<WorkflowRunPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [selectingWorkflowId, setSelectingWorkflowId] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const projectWorkflows = useMemo(
    () =>
      workflows.filter(
        (workflow) =>
          workflow.projectId === projectId || workflow.metadata?.projectId === projectId,
      ),
    [projectId, workflows],
  );

  const selectWorkflow = useCallback(async (workflowId: string) => {
    setSelectingWorkflowId(workflowId);
    setRunPlan(null);
    try {
      const [workflow, runs] = await Promise.all([
        getWorkflow(workflowId),
        listWorkflowRuns(workflowId).catch(() => []),
      ]);
      setSelectedWorkflow(workflow);
      setSelectedWorkflowId(workflow.id);
      setSelectedEdit(selectedEditFromWorkflow(workflow));
      setWorkflowRuns(runs);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Workflow unavailable";
      toast.error("Workflow unavailable", { description: message });
    } finally {
      setSelectingWorkflowId(null);
    }
  }, []);

  const loadWorkflows = useCallback(
    async (preferredWorkflowId?: string | null, showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const [templateRecords, workflowRecords] = await Promise.all([
          listWorkflowTemplates(),
          listWorkflows({ includeDisabled: true }),
        ]);
        setTemplates(templateRecords);
        setWorkflows(workflowRecords);

        const projectRecords = workflowRecords.filter(
          (workflow) =>
            workflow.projectId === projectId ||
            workflow.metadata?.projectId === projectId,
        );
        const nextWorkflowId =
          (preferredWorkflowId &&
            projectRecords.some((workflow) => workflow.id === preferredWorkflowId)
            ? preferredWorkflowId
            : projectRecords[0]?.id) ?? null;

        if (nextWorkflowId) {
          const [workflow, runs] = await Promise.all([
            getWorkflow(nextWorkflowId),
            listWorkflowRuns(nextWorkflowId).catch(() => []),
          ]);
          setSelectedWorkflow(workflow);
          setSelectedWorkflowId(workflow.id);
          setSelectedEdit(selectedEditFromWorkflow(workflow));
          setWorkflowRuns(runs);
        } else {
          setSelectedWorkflow(null);
          setSelectedWorkflowId(null);
          setSelectedEdit(selectedEditFromWorkflow(null));
          setWorkflowRuns([]);
          setRunPlan(null);
        }

        if (showToast) toast.success("Workflows refreshed");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Workflow recorder unavailable";
        setError(message);
        if (showToast) {
          toast.error("Workflow recorder unavailable", { description: message });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    setDraft(createDraft(projectName));
    setSelectedWorkflow(null);
    setSelectedWorkflowId(null);
    setRunPlan(null);
    setWorkflowRuns([]);
    setLoading(true);
    void loadWorkflows(null);
  }, [loadWorkflows, projectName]);

  const handleTemplateSelect = (template: WorkflowTemplate) => {
    setDraft(createDraft(projectName, template));
    toast.success(`${template.label} loaded`);
  };

  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      const steps = serializeDraftSteps(draft.steps);
      const result = await recordWorkflow({
        title: draft.title.trim() || null,
        objective: draft.objective.trim() || null,
        workflowType: draft.workflowType,
        projectId,
        steps,
        metadata: {
          projectId,
          projectName,
          source: "project_workflow_recorder",
        },
        storeWorkflow: true,
      });
      if (result.workflow) {
        setWorkflows((current) => [
          result.workflow!,
          ...current.filter((workflow) => workflow.id !== result.workflow!.id),
        ]);
        setSelectedWorkflow(result.workflow);
        setSelectedWorkflowId(result.workflow.id);
        setSelectedEdit(selectedEditFromWorkflow(result.workflow));
        setRunPlan(null);
        setWorkflowRuns([]);
      }
      toast.success("Workflow recorded");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Workflow not saved";
      toast.error("Workflow not saved", { description: message });
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateSelected = async (
    patch?: Partial<SelectedWorkflowEdit>,
  ) => {
    if (!selectedWorkflow) return;
    const nextEdit = { ...selectedEdit, ...patch };
    setUpdating(true);
    try {
      const result = await updateWorkflow(selectedWorkflow.id, {
        title: nextEdit.title.trim() || selectedWorkflow.title,
        objective: nextEdit.objective.trim() || null,
        status: nextEdit.status,
        shareStatus: nextEdit.shareStatus,
      });
      setSelectedWorkflow(result.workflow);
      setSelectedWorkflowId(result.workflow.id);
      setSelectedEdit(selectedEditFromWorkflow(result.workflow));
      setWorkflows((current) =>
        current.map((workflow) =>
          workflow.id === result.workflow.id ? result.workflow : workflow,
        ),
      );
      toast.success("Workflow updated");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Workflow update failed";
      toast.error("Workflow update failed", { description: message });
    } finally {
      setUpdating(false);
    }
  };

  const handleRunPlan = async () => {
    if (!selectedWorkflow) return;
    setRunning(true);
    try {
      const result = await buildWorkflowRunPlan({
        workflowId: selectedWorkflow.id,
        runMode: "dry_run",
        inputs: { projectId, projectName },
      });
      setRunPlan(result.runPlan);
      setWorkflowRuns((current) => [result.run, ...current]);
      toast.success("Replay plan ready");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Replay plan unavailable";
      toast.error("Replay plan unavailable", { description: message });
    } finally {
      setRunning(false);
    }
  };

  const handleExport = async () => {
    if (!selectedWorkflow) return;
    setExporting(true);
    try {
      const bundle = await exportWorkflowBundle(selectedWorkflow.id);
      const filename = `${selectedWorkflow.title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "") || "cognix-workflow"}.json`;
      downloadJson(filename, bundle);
      toast.success("Workflow exported");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Workflow export failed";
      toast.error("Workflow export failed", { description: message });
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedWorkflow) return;
    setUpdating(true);
    try {
      await deleteWorkflow(selectedWorkflow.id);
      setWorkflows((current) =>
        current.filter((workflow) => workflow.id !== selectedWorkflow.id),
      );
      setSelectedWorkflow(null);
      setSelectedWorkflowId(null);
      setSelectedEdit(selectedEditFromWorkflow(null));
      setRunPlan(null);
      setWorkflowRuns([]);
      toast.success("Workflow deleted");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Workflow delete failed";
      toast.error("Workflow delete failed", { description: message });
    } finally {
      setUpdating(false);
    }
  };

  if (loading) {
    return (
      <div className="mt-8 rounded-[26px] bg-muted/30 px-6 py-5">
        <Skeleton className="h-20 rounded-[22px]" />
        <div className="mt-4 space-y-3">
          <Skeleton className="h-16 rounded-[18px]" />
          <Skeleton className="h-16 rounded-[18px]" />
          <Skeleton className="h-16 rounded-[18px]" />
        </div>
      </div>
    );
  }

  if (error && workflows.length === 0) {
    return (
      <div
        data-testid="project-workflow-recorder-panel"
        className="mt-8 flex flex-col items-center justify-center gap-3 rounded-[26px] bg-muted/30 px-6 py-14 text-center"
      >
        <p className="text-[15px] font-semibold text-foreground">
          Workflow recorder unavailable
        </p>
        <p className="max-w-sm text-sm text-muted-foreground">{error}</p>
        <Button
          type="button"
          variant="outline"
          disabled={refreshing}
          onClick={() => void loadWorkflows(selectedWorkflowId, true)}
          className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
        >
          <RefreshCwIcon
            strokeWidth={1.75}
            className={cn("size-4", refreshing && "animate-spin")}
          />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div
      data-testid="project-workflow-recorder-panel"
      className="mt-8 space-y-4"
    >
      <div className="rounded-[26px] bg-muted/30 px-6 py-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-background px-2.5 py-1 dark:bg-card">
              <WorkflowIcon className="size-3.5" strokeWidth={1.75} />
              {projectWorkflows.length} workflows
            </span>
            <span className="rounded-full bg-background px-2.5 py-1 dark:bg-card">
              {templates.length} templates
            </span>
            <span className="rounded-full bg-background px-2.5 py-1 dark:bg-card">
              no generation
            </span>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={refreshing}
            onClick={() => void loadWorkflows(selectedWorkflowId, true)}
            className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
          >
            <RefreshCwIcon
              strokeWidth={1.75}
              className={cn("size-4", refreshing && "animate-spin")}
            />
            Refresh
          </Button>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              onClick={() => handleTemplateSelect(template)}
              className="flex min-h-[54px] items-center gap-3 rounded-[18px] bg-background/70 px-3 py-2 text-left transition-colors hover:bg-background dark:hover:bg-card"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <GitBranchIcon className="size-4" strokeWidth={1.75} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-foreground">
                  {template.label}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {template.steps.length} steps
                </span>
              </span>
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
          <Input
            value={draft.title}
            onChange={(event) =>
              setDraft((current) => ({ ...current, title: event.target.value }))
            }
            placeholder="Workflow title"
            className="h-11 rounded-2xl bg-background/70 text-sm"
          />
          <Select
            value={draft.workflowType}
            onValueChange={(value) =>
              setDraft((current) => ({ ...current, workflowType: value }))
            }
          >
            <SelectTrigger className="h-11 w-full rounded-2xl bg-background/70">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WORKFLOW_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Textarea
          value={draft.objective}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              objective: event.target.value,
            }))
          }
          placeholder="Objective"
          className="mt-3 min-h-20 rounded-[18px] bg-background/70 text-sm"
        />

        <div className="mt-4">
          <WorkflowStepsEditor
            steps={draft.steps}
            disabled={saving}
            onChange={(steps) => setDraft((current) => ({ ...current, steps }))}
          />
        </div>

        <div className="mt-4 flex justify-end">
          <Button
            type="button"
            disabled={saving || draft.steps.length === 0}
            onClick={() => void handleSaveDraft()}
            className="rounded-full"
          >
            <SaveIcon className="size-4" strokeWidth={1.75} />
            Record workflow
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="rounded-[26px] bg-muted/30 px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-2 px-1">
            <p className="text-sm font-semibold text-foreground">Saved</p>
            <span className="text-xs text-muted-foreground">
              {projectWorkflows.length}
            </span>
          </div>
          {projectWorkflows.length === 0 ? (
            <div className="rounded-[22px] bg-background/70 px-4 py-10 text-center">
              <p className="text-sm font-medium text-foreground">
                No workflow yet
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {projectWorkflows.map((workflow) => (
                <button
                  key={workflow.id}
                  type="button"
                  onClick={() => void selectWorkflow(workflow.id)}
                  data-active={selectedWorkflowId === workflow.id}
                  disabled={selectingWorkflowId === workflow.id}
                  className="flex min-h-[66px] w-full items-center gap-3 rounded-[18px] bg-background/70 px-3 py-2 text-left transition-colors hover:bg-background data-[active=true]:bg-background data-[active=true]:ring-1 data-[active=true]:ring-border dark:hover:bg-card dark:data-[active=true]:bg-card"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <FileJsonIcon className="size-4" strokeWidth={1.75} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-foreground">
                      {workflow.title}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {workflowTypeLabel(workflow.workflowType)} ·{" "}
                      {workflow.stepCount ?? workflow.steps?.length ?? 0} steps
                    </span>
                  </span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-1 text-[11px]",
                      workflow.status === "active"
                        ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {workflow.status}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-[26px] bg-muted/30 px-4 py-4">
          {selectedWorkflow ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-[15px] font-semibold text-foreground">
                    {selectedWorkflow.title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {workflowTypeLabel(selectedWorkflow.workflowType)} ·{" "}
                    {formatWorkflowDate(selectedWorkflow.updatedAt)}
                  </p>
                </div>
                <span
                  className={cn(
                    "rounded-full px-2.5 py-1 text-xs font-medium",
                    selectedWorkflow.shareStatus === "shared"
                      ? "bg-primary/10 text-primary"
                      : "bg-background text-muted-foreground dark:bg-card",
                  )}
                >
                  {selectedWorkflow.shareStatus}
                </span>
              </div>

              <div className="grid gap-2">
                <Input
                  value={selectedEdit.title}
                  disabled={updating}
                  onChange={(event) =>
                    setSelectedEdit((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                  className="h-10 rounded-2xl bg-background/70 text-sm"
                />
                <Textarea
                  value={selectedEdit.objective}
                  disabled={updating}
                  onChange={(event) =>
                    setSelectedEdit((current) => ({
                      ...current,
                      objective: event.target.value,
                    }))
                  }
                  placeholder="Objective"
                  className="min-h-20 rounded-[18px] bg-background/70 text-sm"
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  <Select
                    value={selectedEdit.status}
                    disabled={updating}
                    onValueChange={(status) =>
                      setSelectedEdit((current) => ({
                        ...current,
                        status: status as SelectedWorkflowEdit["status"],
                      }))
                    }
                  >
                    <SelectTrigger className="h-10 w-full rounded-2xl bg-background/70">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="disabled">Disabled</SelectItem>
                      <SelectItem value="archived">Archived</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select
                    value={selectedEdit.shareStatus}
                    disabled={updating}
                    onValueChange={(shareStatus) =>
                      setSelectedEdit((current) => ({
                        ...current,
                        shareStatus:
                          shareStatus as SelectedWorkflowEdit["shareStatus"],
                      }))
                    }
                  >
                    <SelectTrigger className="h-10 w-full rounded-2xl bg-background/70">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="private">Private</SelectItem>
                      <SelectItem value="shared">Shared</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={updating}
                  onClick={() => void handleUpdateSelected()}
                  className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
                >
                  <PencilIcon className="size-4" strokeWidth={1.75} />
                  Save changes
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={running}
                  onClick={() => void handleRunPlan()}
                  className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
                >
                  <PlayIcon className="size-4" strokeWidth={1.75} />
                  Replay
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={updating}
                  onClick={() =>
                    void handleUpdateSelected({
                      shareStatus:
                        selectedEdit.shareStatus === "shared"
                          ? "private"
                          : "shared",
                    })
                  }
                  className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
                >
                  <Share2Icon className="size-4" strokeWidth={1.75} />
                  Share
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={exporting}
                  onClick={() => void handleExport()}
                  className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
                >
                  <DownloadIcon className="size-4" strokeWidth={1.75} />
                  Export
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setDraft(draftFromWorkflow(selectedWorkflow));
                    toast.success("Workflow loaded as draft");
                  }}
                  className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
                >
                  <CopyPlusIcon className="size-4" strokeWidth={1.75} />
                  Duplicate
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={updating}
                  onClick={() =>
                    void handleUpdateSelected({
                      status:
                        selectedEdit.status === "archived" ? "active" : "archived",
                    })
                  }
                  className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
                >
                  <ArchiveIcon className="size-4" strokeWidth={1.75} />
                  Archive
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={updating}
                  onClick={() => void handleDelete()}
                  className="text-muted-foreground hover:text-destructive"
                >
                  <Trash2Icon className="size-4" strokeWidth={1.75} />
                  Delete
                </Button>
              </div>

              <div className="space-y-2">
                {(selectedWorkflow.steps ?? []).map((step, index) => (
                  <div
                    key={step.id ?? `${step.stepIndex}:${index}`}
                    className="flex items-center gap-3 rounded-[18px] bg-background/70 px-3 py-2"
                  >
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {step.label}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {stepTypeLabel(step.stepType)}
                      </p>
                    </div>
                    {step.requiresApproval ? (
                      <span className="rounded-full bg-amber-500/10 px-2 py-1 text-[11px] text-amber-700 dark:text-amber-300">
                        approval
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>

              <WorkflowRunPlanPreview runPlan={runPlan} runs={workflowRuns} />
            </div>
          ) : (
            <div className="rounded-[22px] bg-background/70 px-4 py-12 text-center">
              <p className="text-sm font-medium text-foreground">
                Select or record a workflow
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
