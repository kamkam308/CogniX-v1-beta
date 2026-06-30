// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import {
  type ProjectRecord,
  createChatProject,
  deleteChatProject,
  renameChatProject,
  useChatProjects,
  useChatRuntimeStore,
} from "@/features/chat";
import { toast } from "@/lib/toast";
import {
  Delete02Icon,
  Download01Icon,
  Edit03Icon,
  Folder02Icon,
  FolderAddIcon,
  Search01Icon,
  Upload01Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useNavigate } from "@tanstack/react-router";
import {
  BrainCircuitIcon,
  Link2Icon,
  ListChecksIcon,
  MoreHorizontalIcon,
  ScrollTextIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type ChatProjectBridgeResponse,
  createChatProjectBridgeLink,
  createProjectDirective,
  createProjectSkill,
  createMessageTask,
  getChatProjectBridge,
} from "./api/chat-api";
import {
  type ConvExportFormat,
  EXPORT_FORMATS_LIST,
  exportBulkConversationsMerged,
  exportBulkConversationsSeparate,
  exportProjectConversations,
  importConversationsFromFile,
} from "./prompt-storage/prompt-storage-dialog";
import type { ThreadRecord } from "./types";
import { listStoredChatThreads } from "./utils/chat-history-storage";

type SortMode = "activity" | "name";

function formatUpdatedAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (!Number.isFinite(diff) || diff < 0) return "just now";
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} day${d === 1 ? "" : "s"} ago`;
  const mo = Math.floor(d / 30);
  if (mo < 12) return `${mo} month${mo === 1 ? "" : "s"} ago`;
  const y = Math.floor(mo / 12);
  return `${y} year${y === 1 ? "" : "s"} ago`;
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const { projects, hasLoaded } = useChatProjects();

  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("activity");

  const [creating, setCreating] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [renaming, setRenaming] = useState<ProjectRecord | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [deleting, setDeleting] = useState<ProjectRecord | null>(null);
  const [bridge, setBridge] = useState<ChatProjectBridgeResponse>({
    links: [],
    tasks: [],
    summary: { linkCount: 0, taskCount: 0, openTaskCount: 0 },
  });
  const [bridgeLoading, setBridgeLoading] = useState(false);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [taskProject, setTaskProject] = useState<ProjectRecord | null>(null);
  const [taskThreads, setTaskThreads] = useState<ThreadRecord[]>([]);
  const [taskThreadId, setTaskThreadId] = useState("");
  const [taskTitleDraft, setTaskTitleDraft] = useState("");
  const [taskSourceDraft, setTaskSourceDraft] = useState("");
  const [taskPriority, setTaskPriority] = useState<
    "low" | "medium" | "high" | "critical"
  >("medium");
  const [taskRequiresApproval, setTaskRequiresApproval] = useState(false);
  const [bridgeBusy, setBridgeBusy] = useState<string | null>(null);
  const [skillProject, setSkillProject] = useState<ProjectRecord | null>(null);
  const [skillNameDraft, setSkillNameDraft] = useState("");
  const [skillObjectiveDraft, setSkillObjectiveDraft] = useState("");
  const [skillInstructionsDraft, setSkillInstructionsDraft] = useState("");
  const [skillModelDraft, setSkillModelDraft] = useState("");
  const [skillToolsDraft, setSkillToolsDraft] = useState("");
  const [directiveProject, setDirectiveProject] =
    useState<ProjectRecord | null>(null);
  const [directiveContentDraft, setDirectiveContentDraft] = useState("");
  const [directiveType, setDirectiveType] = useState("style");
  const [directivePriority, setDirectivePriority] = useState("60");
  const [directiveModelDraft, setDirectiveModelDraft] = useState("");

  const globalImportRef = useRef<HTMLInputElement>(null);
  const projectImportRefs = useRef<Map<string, HTMLInputElement>>(new Map());
  const [importFile, setImportFile] = useState<File | null>(null);
  // null = Recents
  const [importTargetId, setImportTargetId] = useState<string | null>(null);

  const refreshBridge = useCallback(async () => {
    setBridgeLoading(true);
    setBridgeError(null);
    try {
      setBridge(await getChatProjectBridge());
    } catch (err) {
      setBridgeError(err instanceof Error ? err.message : "Bridge unavailable");
    } finally {
      setBridgeLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshBridge();
  }, [refreshBridge]);

  const bridgeByProject = useMemo(() => {
    const stats = new Map<
      string,
      { links: number; tasks: number; openTasks: number }
    >();
    const ensure = (projectId: string) => {
      const current = stats.get(projectId) ?? {
        links: 0,
        tasks: 0,
        openTasks: 0,
      };
      stats.set(projectId, current);
      return current;
    };
    for (const link of bridge.links) {
      if (link.projectId) ensure(link.projectId).links += 1;
    }
    for (const task of bridge.tasks) {
      if (!task.projectId) continue;
      const current = ensure(task.projectId);
      current.tasks += 1;
      if (
        task.status === "open" ||
        task.status === "in_progress" ||
        task.status === "blocked"
      ) {
        current.openTasks += 1;
      }
    }
    return stats;
  }, [bridge]);

  async function handleImport(file: File, projectId: string | null) {
    try {
      const count = await importConversationsFromFile(file, projectId);
      if (count === 0) {
        toast.info("No conversations found in file.");
      } else {
        const dest = projectId
          ? (projects.find((p) => p.id === projectId)?.name ?? "project")
          : "Recents";
        toast.success(
          `Imported ${count} conversation${count === 1 ? "" : "s"} to ${dest}.`,
        );
      }
    } catch {
      toast.error("Import failed.");
    }
  }

  async function commitImport() {
    if (!importFile) return;
    const file = importFile;
    const target = importTargetId;
    setImportFile(null);
    await handleImport(file, target);
  }

  const visibleProjects = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    const filtered = trimmed
      ? projects.filter((p) => p.name.toLowerCase().includes(trimmed))
      : projects.slice();
    filtered.sort((a, b) =>
      sortMode === "name"
        ? a.name.localeCompare(b.name)
        : b.updatedAt - a.updatedAt,
    );
    return filtered;
  }, [projects, query, sortMode]);

  function openProject(projectId: string) {
    const runtime = useChatRuntimeStore.getState();
    runtime.setActiveThreadId(null);
    runtime.setActiveProjectId(projectId);
    navigate({ to: "/chat", search: { project: projectId } });
  }

  async function commitCreate() {
    const name = nameDraft.trim();
    if (!name) return;
    try {
      const project = await createChatProject(name);
      setCreating(false);
      setNameDraft("");
      openProject(project.id);
    } catch (err) {
      toast.error("Failed to create project", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  async function openTaskDialog(project: ProjectRecord) {
    setTaskProject(project);
    setTaskTitleDraft("");
    setTaskSourceDraft("");
    setTaskPriority("medium");
    setTaskRequiresApproval(false);
    try {
      const threads = await listStoredChatThreads({
        projectId: project.id,
        includeArchived: false,
      });
      setTaskThreads(threads);
      setTaskThreadId(threads[0]?.id ?? "");
    } catch {
      setTaskThreads([]);
      setTaskThreadId("");
    }
  }

  function openSkillDialog(project: ProjectRecord) {
    setSkillProject(project);
    setSkillNameDraft("");
    setSkillObjectiveDraft("");
    setSkillInstructionsDraft("");
    setSkillModelDraft("");
    setSkillToolsDraft("project_context, rag_retrieval");
  }

  function openDirectiveDialog(project: ProjectRecord) {
    setDirectiveProject(project);
    setDirectiveContentDraft("");
    setDirectiveType("style");
    setDirectivePriority("60");
    setDirectiveModelDraft("");
  }

  async function commitProjectSkill() {
    const project = skillProject;
    const displayName = skillNameDraft.trim();
    const objective = skillObjectiveDraft.trim();
    if (!project || !displayName || !objective) return;
    setBridgeBusy(`skill:${project.id}`);
    try {
      const allowedTools = skillToolsDraft
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      await createProjectSkill({
        projectId: project.id,
        displayName,
        objective,
        instructions: skillInstructionsDraft.trim() || null,
        modelId: skillModelDraft.trim() || null,
        allowedTools,
      });
      setSkillProject(null);
      toast.success("Project skill added.");
    } catch (err) {
      toast.error("Skill creation failed", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBridgeBusy(null);
    }
  }

  async function commitProjectDirective() {
    const project = directiveProject;
    const content = directiveContentDraft.trim();
    if (!project || !content) return;
    setBridgeBusy(`directive:${project.id}`);
    try {
      const parsedPriority = Number.parseInt(directivePriority, 10);
      await createProjectDirective({
        projectId: project.id,
        content,
        directiveType,
        priority: Number.isFinite(parsedPriority) ? parsedPriority : 60,
        modelId: directiveModelDraft.trim() || null,
      });
      setDirectiveProject(null);
      toast.success("Project directive added.");
    } catch (err) {
      toast.error("Directive creation failed", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBridgeBusy(null);
    }
  }

  async function handleLinkLatestThread(project: ProjectRecord) {
    const busyKey = `link:${project.id}`;
    setBridgeBusy(busyKey);
    try {
      const threads = await listStoredChatThreads({
        projectId: project.id,
        includeArchived: false,
      });
      const thread = threads[0];
      if (!thread) {
        toast.info("No project chat to link yet.");
        return;
      }
      await createChatProjectBridgeLink({
        projectId: project.id,
        threadId: thread.id,
        linkType: "conversation",
        source: "project",
        metadata: { threadTitle: thread.title },
      });
      toast.success("Chat linked to project.");
      await refreshBridge();
    } catch (err) {
      toast.error("Bridge link failed", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBridgeBusy(null);
    }
  }

  async function commitMessageTask() {
    const project = taskProject;
    const sourceText = taskSourceDraft.trim();
    if (!project || !sourceText) return;
    const busyKey = `task:${project.id}`;
    setBridgeBusy(busyKey);
    try {
      await createMessageTask({
        projectId: project.id,
        threadId: taskThreadId || null,
        title: taskTitleDraft.trim() || null,
        sourceText,
        priority: taskPriority,
        status: "open",
        requireApproval: taskRequiresApproval,
        metadata: { source: "projects_page" },
      });
      setTaskProject(null);
      setTaskSourceDraft("");
      setTaskTitleDraft("");
      toast.success("Task created.");
      await refreshBridge();
    } catch (err) {
      toast.error("Task creation failed", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBridgeBusy(null);
    }
  }

  async function commitRename() {
    const target = renaming;
    const name = renameDraft.trim();
    if (!target || !name || name === target.name) {
      setRenaming(null);
      return;
    }
    setRenaming(null);
    try {
      await renameChatProject(target.id, name);
    } catch (err) {
      toast.error("Failed to rename project", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  async function handleProjectExport(
    project: ProjectRecord,
    fmt: ConvExportFormat,
  ) {
    try {
      const threads = await listStoredChatThreads({
        projectId: project.id,
        includeArchived: false,
      });
      const ids = [...new Set(threads.map((t) => t.id))];
      await exportProjectConversations(ids, fmt, project.name);
    } catch {
      toast.error("Export failed.");
    }
  }

  async function handleBulkProjectExport(
    scope: "projects" | "all",
    fmt: ConvExportFormat,
    merged: boolean,
  ) {
    try {
      let threads;
      if (scope === "projects") {
        threads = (
          await Promise.all(
            projects.map((p) =>
              listStoredChatThreads({
                projectId: p.id,
                includeArchived: false,
              }),
            ),
          )
        ).flat();
      } else {
        threads = await listStoredChatThreads({ includeArchived: false });
      }
      const ids = [...new Set(threads.map((t) => t.id))];
      if (ids.length === 0) {
        toast.info("No conversations to export.");
        return;
      }
      const ts = new Date().toISOString().slice(0, 10);
      const basename = `${scope === "all" ? "all-chats" : "all-projects"}-${ts}`;
      if (merged) {
        await exportBulkConversationsMerged(ids, fmt, basename);
      } else {
        await exportBulkConversationsSeparate(ids, fmt, basename);
      }
    } catch {
      toast.error("Export failed.");
    }
  }

  async function commitDelete() {
    const target = deleting;
    if (!target) return;
    setDeleting(null);
    try {
      await deleteChatProject(target.id);
    } catch (err) {
      toast.error("Failed to delete project", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10 font-heading sm:px-10">
      {/* Global import file input */}
      <input
        ref={globalImportRef}
        type="file"
        accept=".jsonl,.ndjson,.csv"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            setImportTargetId(projects[0]?.id ?? null);
            setImportFile(file);
          }
          e.target.value = "";
        }}
      />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[30px] font-semibold leading-[1.04] tracking-[-0.028em] text-foreground sm:text-[34px]">
          Projects
        </h1>
        <div className="flex items-center gap-3">
          <div className="relative">
            <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground">
              <HugeiconsIcon
                icon={Search01Icon}
                strokeWidth={1.75}
                className="size-4"
              />
            </span>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects"
              className="h-9 w-52 rounded-full border-none bg-muted pl-10 pr-4 shadow-none dark:bg-card sm:w-64"
              aria-label="Search projects"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Sort by</span>
            <Select
              value={sortMode}
              onValueChange={(v) => setSortMode(v as SortMode)}
            >
              <SelectTrigger className="h-9 w-[130px] rounded-full border-none bg-muted shadow-none dark:bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="activity">Activity</SelectItem>
                <SelectItem value="name">Name</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild={true}>
              <Button
                variant="outline"
                size="icon"
                title="Import / Export projects"
                className="rounded-full border-none bg-muted shadow-none dark:bg-card"
              >
                <HugeiconsIcon
                  icon={Download01Icon}
                  strokeWidth={1.75}
                  className="size-icon"
                />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem
                onSelect={() => globalImportRef.current?.click()}
              >
                <HugeiconsIcon
                  icon={Upload01Icon}
                  strokeWidth={1.75}
                  className="size-icon"
                />
                Import chats…
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  Export All Projects
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-52">
                  {EXPORT_FORMATS_LIST.map(({ fmt, label }) => (
                    <DropdownMenuItem
                      key={`ap-m-${fmt}`}
                      onSelect={() =>
                        void handleBulkProjectExport("projects", fmt, true)
                      }
                    >
                      {label} (combined)
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  {EXPORT_FORMATS_LIST.map(({ fmt, label }) => (
                    <DropdownMenuItem
                      key={`ap-s-${fmt}`}
                      onSelect={() =>
                        void handleBulkProjectExport("projects", fmt, false)
                      }
                    >
                      {label} (per chat)
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  Export Projects + Recents
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-52">
                  {EXPORT_FORMATS_LIST.map(({ fmt, label }) => (
                    <DropdownMenuItem
                      key={`all-m-${fmt}`}
                      onSelect={() =>
                        void handleBulkProjectExport("all", fmt, true)
                      }
                    >
                      {label} (combined)
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  {EXPORT_FORMATS_LIST.map(({ fmt, label }) => (
                    <DropdownMenuItem
                      key={`all-s-${fmt}`}
                      onSelect={() =>
                        void handleBulkProjectExport("all", fmt, false)
                      }
                    >
                      {label} (per chat)
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            onClick={() => {
              setNameDraft("");
              setCreating(true);
            }}
          >
            New project
          </Button>
        </div>
      </div>

      <div className="mt-8 grid gap-4 border-y border-border/70 py-4 text-sm sm:grid-cols-3">
        <div className="flex min-h-14 items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70 dark:bg-card">
            <Link2Icon strokeWidth={1.75} className="size-4" />
          </span>
          <div>
            <p className="text-xs text-muted-foreground">Linked chats</p>
            <p className="text-lg font-semibold text-foreground">
              {bridgeLoading ? "…" : bridge.summary.linkCount}
            </p>
          </div>
        </div>
        <div className="flex min-h-14 items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70 dark:bg-card">
            <ListChecksIcon strokeWidth={1.75} className="size-4" />
          </span>
          <div>
            <p className="text-xs text-muted-foreground">Message tasks</p>
            <p className="text-lg font-semibold text-foreground">
              {bridgeLoading ? "…" : bridge.summary.taskCount}
            </p>
          </div>
        </div>
        <div className="flex min-h-14 items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70 dark:bg-card">
            <ListChecksIcon strokeWidth={1.75} className="size-4" />
          </span>
          <div>
            <p className="text-xs text-muted-foreground">Open tasks</p>
            <p className="text-lg font-semibold text-foreground">
              {bridgeLoading ? "…" : bridge.summary.openTaskCount}
            </p>
          </div>
        </div>
        {bridgeError ? (
          <p className="sm:col-span-3 text-xs text-destructive">
            {bridgeError}
          </p>
        ) : null}
      </div>

      {hasLoaded ? (
        visibleProjects.length === 0 ? (
          <div className="mt-16 flex flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <p className="text-sm">
              {projects.length === 0
                ? "No projects yet."
                : "No projects match your search."}
            </p>
            {projects.length === 0 && (
              <Button
                variant="outline"
                className="mt-2 border-none bg-background shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] dark:bg-card dark:shadow-none"
                onClick={() => {
                  setNameDraft("");
                  setCreating(true);
                }}
              >
                <HugeiconsIcon
                  icon={FolderAddIcon}
                  strokeWidth={1.75}
                  className="size-icon"
                />
                Create your first project
              </Button>
            )}
          </div>
        ) : (
          <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {visibleProjects.map((project) => {
              const bridgeStats = bridgeByProject.get(project.id);
              const linkBusy = bridgeBusy === `link:${project.id}`;
              return (
                <div key={`wrap-${project.id}`} className="contents">
                  <input
                    key={`import-${project.id}`}
                    type="file"
                    accept=".jsonl,.ndjson,.csv"
                    className="hidden"
                    ref={(el) => {
                      if (el) projectImportRefs.current.set(project.id, el);
                      else projectImportRefs.current.delete(project.id);
                    }}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void handleImport(file, project.id);
                      e.target.value = "";
                    }}
                  />
                  <div
                    key={project.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => openProject(project.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openProject(project.id);
                      }
                    }}
                    className="group/project-card relative flex min-h-[172px] cursor-pointer flex-col rounded-[26px] bg-card p-6 text-left shadow-[0_2px_12px_-4px_rgba(0,0,0,0.10)] transition-colors duration-150 hover:bg-[#f2f2f2] dark:shadow-none dark:hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-[14px] bg-muted text-foreground/70 transition-colors group-hover/project-card:bg-primary/10 group-hover/project-card:text-primary">
                        <HugeiconsIcon
                          icon={Folder02Icon}
                          strokeWidth={1.75}
                          className="size-5"
                        />
                      </span>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild={true}>
                          <button
                            type="button"
                            onClick={(e) => e.stopPropagation()}
                            aria-label="Project options"
                            className="-mr-1 -mt-1 inline-flex size-7 shrink-0 items-center justify-center rounded-full text-muted-foreground opacity-0 transition-opacity hover:bg-black/5 hover:text-foreground dark:hover:bg-white/10 focus-visible:opacity-100 group-hover/project-card:opacity-100 data-[state=open]:bg-black/5 data-[state=open]:opacity-100 dark:data-[state=open]:bg-white/10"
                          >
                            <MoreHorizontalIcon
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          side="bottom"
                          align="end"
                          sideOffset={0}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                          className="app-user-menu menu-soft-surface menu-flat-destructive ring-0 w-44 py-2 font-heading rounded-[14px] border-0"
                        >
                          <DropdownMenuItem
                            onSelect={() => {
                              setRenameDraft(project.name);
                              setRenaming(project);
                            }}
                          >
                            <HugeiconsIcon
                              icon={Edit03Icon}
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>Rename</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={(e) => {
                              e.stopPropagation();
                              projectImportRefs.current
                                .get(project.id)
                                ?.click();
                            }}
                          >
                            <HugeiconsIcon
                              icon={Upload01Icon}
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>Import chats</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={linkBusy}
                            onSelect={(e) => {
                              e.stopPropagation();
                              void handleLinkLatestThread(project);
                            }}
                          >
                            <Link2Icon
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>Link latest chat</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={(e) => {
                              e.stopPropagation();
                              void openTaskDialog(project);
                            }}
                          >
                            <ListChecksIcon
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>New task</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={(e) => {
                              e.stopPropagation();
                              openSkillDialog(project);
                            }}
                          >
                            <BrainCircuitIcon
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>Add skill</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={(e) => {
                              e.stopPropagation();
                              openDirectiveDialog(project);
                            }}
                          >
                            <ScrollTextIcon
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>Add directive</span>
                          </DropdownMenuItem>
                          <DropdownMenuSub>
                            <DropdownMenuSubTrigger>
                              <HugeiconsIcon
                                icon={Download01Icon}
                                strokeWidth={1.75}
                                className="size-icon mr-1"
                              />
                              <span>Export</span>
                            </DropdownMenuSubTrigger>
                            <DropdownMenuSubContent className="w-52">
                              {EXPORT_FORMATS_LIST.map(({ fmt, label }) => (
                                <DropdownMenuItem
                                  key={fmt}
                                  onSelect={(e) => {
                                    e.stopPropagation();
                                    void handleProjectExport(project, fmt);
                                  }}
                                >
                                  {label}
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuSubContent>
                          </DropdownMenuSub>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            variant="destructive"
                            onSelect={() => setDeleting(project)}
                          >
                            <HugeiconsIcon
                              icon={Delete02Icon}
                              strokeWidth={1.75}
                              className="size-icon"
                            />
                            <span>Delete</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    <h2 className="mt-4 truncate text-[16px] font-semibold text-foreground">
                      {project.name}
                    </h2>
                    {project.instructions ? (
                      <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                        {project.instructions}
                      </p>
                    ) : null}
                    {bridgeStats ? (
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        {bridgeStats.links > 0 ? (
                          <span className="rounded-md bg-muted px-2 py-1 dark:bg-background">
                            {bridgeStats.links} link
                            {bridgeStats.links === 1 ? "" : "s"}
                          </span>
                        ) : null}
                        {bridgeStats.tasks > 0 ? (
                          <span className="rounded-md bg-muted px-2 py-1 dark:bg-background">
                            {bridgeStats.openTasks}/{bridgeStats.tasks} open
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                    <span className="mt-auto pt-4 text-xs text-muted-foreground/80">
                      Updated {formatUpdatedAgo(project.updatedAt)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )
      ) : (
        <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="min-h-[172px] rounded-[26px] bg-card p-6 shadow-[0_2px_12px_-4px_rgba(0,0,0,0.10)] dark:shadow-none"
            >
              <Skeleton className="size-10 rounded-[14px]" />
              <Skeleton className="mt-4 h-5 w-2/3 rounded-[8px]" />
              <Skeleton className="mt-2 h-4 w-4/5 rounded-[8px]" />
              <Skeleton className="mt-8 h-3 w-24 rounded-[8px]" />
            </div>
          ))}
        </div>
      )}

      {/* Create project */}
      <Dialog
        open={creating}
        onOpenChange={(open) => {
          if (!open) setCreating(false);
        }}
      >
        <DialogContent className="corner-squircle dialog-soft-surface sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
          </DialogHeader>
          <Input
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void commitCreate();
              }
            }}
            autoFocus={true}
            maxLength={120}
            placeholder="Project name"
            aria-label="Project name"
            className="focus-visible:border-input focus-visible:ring-0"
          />
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreating(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void commitCreate()}
              disabled={!nameDraft.trim()}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename project */}
      <Dialog
        open={renaming !== null}
        onOpenChange={(open) => {
          if (!open) setRenaming(null);
        }}
      >
        <DialogContent className="corner-squircle dialog-soft-surface sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename project</DialogTitle>
          </DialogHeader>
          <Input
            value={renameDraft}
            onChange={(e) => setRenameDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void commitRename();
              }
            }}
            autoFocus={true}
            maxLength={120}
            placeholder="Project name"
            aria-label="Project name"
            className="focus-visible:border-input focus-visible:ring-0"
          />
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setRenaming(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void commitRename()}
              disabled={
                !renameDraft.trim() || renameDraft.trim() === renaming?.name
              }
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Message task */}
      <Dialog
        open={taskProject !== null}
        onOpenChange={(open) => {
          if (!open) setTaskProject(null);
        }}
      >
        <DialogContent className="corner-squircle dialog-soft-surface sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>New task</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              value={taskTitleDraft}
              onChange={(e) => setTaskTitleDraft(e.target.value)}
              maxLength={180}
              placeholder="Title"
              aria-label="Task title"
              className="focus-visible:border-input focus-visible:ring-0"
            />
            <Textarea
              value={taskSourceDraft}
              onChange={(e) => setTaskSourceDraft(e.target.value)}
              className="min-h-28 resize-none focus-visible:border-input focus-visible:ring-0"
              placeholder="Paste a message or note"
              aria-label="Task source text"
              fieldSizing="fixed"
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                value={taskThreadId || "__none__"}
                onValueChange={(value) =>
                  setTaskThreadId(value === "__none__" ? "" : value)
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Thread" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">No chat link</SelectItem>
                  {taskThreads.map((thread) => (
                    <SelectItem key={thread.id} value={thread.id}>
                      {thread.title || "New Chat"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={taskPriority}
                onValueChange={(value) =>
                  setTaskPriority(value as typeof taskPriority)
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Priority" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox
                checked={taskRequiresApproval}
                onCheckedChange={(checked) =>
                  setTaskRequiresApproval(checked === true)
                }
              />
              Request approval
            </label>
          </div>
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setTaskProject(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void commitMessageTask()}
              disabled={
                !taskSourceDraft.trim() ||
                bridgeBusy === `task:${taskProject?.id ?? ""}`
              }
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Project skill */}
      <Dialog
        open={skillProject !== null}
        onOpenChange={(open) => {
          if (!open) setSkillProject(null);
        }}
      >
        <DialogContent className="corner-squircle dialog-soft-surface sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add skill</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              value={skillNameDraft}
              onChange={(e) => setSkillNameDraft(e.target.value)}
              maxLength={180}
              placeholder="Skill name"
              aria-label="Skill name"
              className="focus-visible:border-input focus-visible:ring-0"
            />
            <Textarea
              value={skillObjectiveDraft}
              onChange={(e) => setSkillObjectiveDraft(e.target.value)}
              className="min-h-20 resize-none focus-visible:border-input focus-visible:ring-0"
              placeholder="Objective"
              aria-label="Skill objective"
              fieldSizing="fixed"
            />
            <Textarea
              value={skillInstructionsDraft}
              onChange={(e) => setSkillInstructionsDraft(e.target.value)}
              className="min-h-24 resize-none focus-visible:border-input focus-visible:ring-0"
              placeholder="Instructions"
              aria-label="Skill instructions"
              fieldSizing="fixed"
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                value={skillModelDraft}
                onChange={(e) => setSkillModelDraft(e.target.value)}
                maxLength={240}
                placeholder="Model ID"
                aria-label="Skill model ID"
                className="focus-visible:border-input focus-visible:ring-0"
              />
              <Input
                value={skillToolsDraft}
                onChange={(e) => setSkillToolsDraft(e.target.value)}
                maxLength={500}
                placeholder="Allowed tools"
                aria-label="Allowed tools"
                className="focus-visible:border-input focus-visible:ring-0"
              />
            </div>
          </div>
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setSkillProject(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void commitProjectSkill()}
              disabled={
                !skillNameDraft.trim() ||
                !skillObjectiveDraft.trim() ||
                bridgeBusy === `skill:${skillProject?.id ?? ""}`
              }
            >
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Project directive */}
      <Dialog
        open={directiveProject !== null}
        onOpenChange={(open) => {
          if (!open) setDirectiveProject(null);
        }}
      >
        <DialogContent className="corner-squircle dialog-soft-surface sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add directive</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Textarea
              value={directiveContentDraft}
              onChange={(e) => setDirectiveContentDraft(e.target.value)}
              className="min-h-28 resize-none focus-visible:border-input focus-visible:ring-0"
              placeholder="Directive"
              aria-label="Directive content"
              fieldSizing="fixed"
            />
            <div className="grid gap-3 sm:grid-cols-3">
              <Select value={directiveType} onValueChange={setDirectiveType}>
                <SelectTrigger>
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="style">Style</SelectItem>
                  <SelectItem value="security">Security</SelectItem>
                  <SelectItem value="privacy">Privacy</SelectItem>
                  <SelectItem value="format">Format</SelectItem>
                  <SelectItem value="tools">Tools</SelectItem>
                  <SelectItem value="model">Model</SelectItem>
                  <SelectItem value="rag">RAG</SelectItem>
                  <SelectItem value="code">Code</SelectItem>
                  <SelectItem value="pedagogy">Pedagogy</SelectItem>
                </SelectContent>
              </Select>
              <Input
                value={directivePriority}
                onChange={(e) => setDirectivePriority(e.target.value)}
                type="number"
                min={0}
                max={100}
                placeholder="Priority"
                aria-label="Directive priority"
                className="focus-visible:border-input focus-visible:ring-0"
              />
              <Input
                value={directiveModelDraft}
                onChange={(e) => setDirectiveModelDraft(e.target.value)}
                maxLength={240}
                placeholder="Model ID"
                aria-label="Directive model ID"
                className="focus-visible:border-input focus-visible:ring-0"
              />
            </div>
          </div>
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDirectiveProject(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void commitProjectDirective()}
              disabled={
                !directiveContentDraft.trim() ||
                bridgeBusy === `directive:${directiveProject?.id ?? ""}`
              }
            >
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import destination picker */}
      <Dialog
        open={importFile !== null}
        onOpenChange={(open) => {
          if (!open) setImportFile(null);
        }}
      >
        <DialogContent className="corner-squircle dialog-soft-surface sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Import chats</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Choose where to import{" "}
            <span className="font-medium text-foreground">
              {importFile?.name}
            </span>
            :
          </p>
          <Select
            value={importTargetId ?? "__recents__"}
            onValueChange={(v) =>
              setImportTargetId(v === "__recents__" ? null : v)
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="Select destination" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__recents__">Recents</SelectItem>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setImportFile(null)}
            >
              Cancel
            </Button>
            <Button type="button" onClick={() => void commitImport()}>
              Import
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete project */}
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
      >
        <DialogContent className="menu-flat-destructive corner-squircle dialog-soft-surface sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete project</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete <em>{deleting?.name}</em>? Chats in
            this project will be moved back to Recents.
          </p>
          <DialogFooter className="flex-wrap gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDeleting(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void commitDelete()}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
