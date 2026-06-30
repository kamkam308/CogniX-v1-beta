// SPDX-License-Identifier: AGPL-3.0-only

import { Badge } from "@/components/ui/badge";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Spinner } from "@/components/ui/spinner";
import { hasAuthToken } from "@/features/auth";
import { clearNewChatDraft, useChatRuntimeStore } from "@/features/chat";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import {
  AppWindow,
  Bot,
  CalendarClock,
  Code2,
  FileSearch,
  Folder,
  LibraryBig,
  type LucideIcon,
  MessageSquarePlus,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  type JsonRecord,
  asArray,
  asRecord,
  cognixJson,
  jsonBody,
  readBoolean,
  readString,
  readStringList,
} from "./api";

type NativeCommand = JsonRecord & {
  id?: string;
  label?: string;
  description?: string;
  category?: string;
  route?: string;
  status?: string;
  available?: boolean;
  riskLevel?: string;
};

type PlannedCommandRun = {
  blockReason: string | null;
  target: string | null;
};

const AUTH_HIDDEN_ROUTES = new Set([
  "/login",
  "/signup",
  "/change-password",
  "/onboarding",
]);

const ROUTE_MAP = new Map<string, string>([
  ["/", "/chat"],
  ["/chat", "/chat"],
  ["/projects", "/projects"],
  ["/projects/new", "/projects"],
  ["/hub", "/hub"],
  ["/pulse", "/pulse"],
  ["/library", "/library"],
  ["/scheduled", "/scheduled"],
  ["/scheduled/new", "/scheduled"],
  ["/apps", "/apps"],
  ["/gpts", "/gpts"],
  ["/images", "/images"],
  ["/codex", "/codex"],
  ["/studio", "/studio"],
  ["/data-recipes", "/data-recipes"],
  ["/export", "/export"],
  ["/admin/usage", "/admin/usage"],
  ["/admin/security-threats", "/admin/security-threats"],
]);

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  admin: ShieldCheck,
  apps: AppWindow,
  automation: CalendarClock,
  chat: MessageSquarePlus,
  codex: Code2,
  gpts: Bot,
  library: LibraryBig,
  models: Zap,
  projects: Folder,
  pulse: Search,
};

function commandId(command: NativeCommand): string {
  return readString(command.id);
}

function commandCategory(command: NativeCommand): string {
  return readString(command.category, "other");
}

function labelize(value: unknown): string {
  const text = readString(value, "Other").replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function riskClass(value: unknown): string {
  const risk = readString(value).toLowerCase();
  if (risk === "critical" || risk === "high") {
    return "border-destructive/30 bg-destructive/10 text-destructive";
  }
  if (risk === "medium") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "border-border bg-muted/60 text-muted-foreground";
}

function normalizeRoute(route: unknown): string | null {
  const raw = readString(route);
  if (!raw) {
    return null;
  }
  const path = raw.split("?")[0] || raw;
  return ROUTE_MAP.get(path) ?? null;
}

function commandIcon(command: NativeCommand): LucideIcon {
  const id = commandId(command);
  if (id === "search_documents") {
    return FileSearch;
  }
  return CATEGORY_ICONS[commandCategory(command)] ?? Zap;
}

function commandUnavailableReason(command: NativeCommand): string | null {
  if (readBoolean(command.available, false)) {
    return null;
  }
  return (
    readStringList(command.missingPermissions).join(", ") ||
    "Missing required permissions."
  );
}

async function fetchCommandPlan(
  commandIdValue: string,
  query: string,
  projectId: string | null,
): Promise<JsonRecord> {
  const payload = await cognixJson("/api/cognix/command-palette/plan", {
    method: "POST",
    body: jsonBody({
      commandId: commandIdValue,
      query: query.trim() || null,
      projectId,
      logUsage: true,
    }),
  });
  return asRecord(payload.commandPlan);
}

function commandPlanBlockReason(plan: JsonRecord): string | null {
  if (readBoolean(plan.allowedToRun, false)) {
    return null;
  }
  const blocked = asArray(plan.blockedActions)
    .map((item) => readString(item.reason))
    .filter(Boolean)
    .join(" ");
  return blocked || "Permission gate did not pass.";
}

function resetChatRuntimeForNewChat(): void {
  clearNewChatDraft();
  const runtime = useChatRuntimeStore.getState();
  runtime.setActiveThreadId(null);
  runtime.setActiveProjectId(null);
  runtime.setIncognito(false);
}

function commandPlanTarget(
  plan: JsonRecord,
  command: NativeCommand,
): string | null {
  const executionPlan = asRecord(plan.executionPlan);
  return normalizeRoute(executionPlan.route ?? command.route);
}

async function planCommandRun(
  command: NativeCommand,
  commandIdValue: string,
  query: string,
  projectId: string | null,
): Promise<PlannedCommandRun> {
  const plan = await fetchCommandPlan(commandIdValue, query, projectId);
  const blockReason = commandPlanBlockReason(plan);
  return {
    blockReason,
    target: blockReason ? null : commandPlanTarget(plan, command),
  };
}

export function CogniXCommandPalette() {
  const navigate = useNavigate();
  const { pathname, search } = useRouterState({
    select: (state) => ({
      pathname: state.location.pathname,
      search: state.location.search as Record<string, unknown>,
    }),
  });
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [commands, setCommands] = useState<NativeCommand[]>([]);
  const [loading, setLoading] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const disabledHere = AUTH_HIDDEN_ROUTES.has(pathname) || !hasAuthToken();
  const projectId = typeof search.project === "string" ? search.project : null;

  useEffect(() => {
    if (disabledHere && open) {
      setOpen(false);
    }
  }, [disabledHere, open]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.defaultPrevented || disabledHere) {
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [disabledHere]);

  useEffect(() => {
    if (!open || disabledHere) {
      return;
    }
    let cancelled = false;
    const loadCommands = () => {
      setLoading(true);
      cognixJson("/api/cognix/command-palette/search", {
        method: "POST",
        body: jsonBody({
          query: query.trim() || null,
          projectId,
          limit: 28,
          includeDisabled: true,
        }),
      })
        .then((payload) => {
          if (cancelled) {
            return;
          }
          setCommands(
            asArray(
              asRecord(payload.commandPalette).commands,
            ) as NativeCommand[],
          );
        })
        .catch((error: unknown) => {
          if (cancelled) {
            return;
          }
          toast.error("Command search failed", {
            description: error instanceof Error ? error.message : undefined,
          });
          setCommands([]);
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    };
    const timeout = window.setTimeout(loadCommands, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [disabledHere, open, projectId, query]);

  const groupedCommands = useMemo(() => {
    const groups = new Map<string, NativeCommand[]>();
    for (const command of commands) {
      const category = commandCategory(command);
      const list = groups.get(category) ?? [];
      list.push(command);
      groups.set(category, list);
    }
    return [...groups.entries()];
  }, [commands]);

  async function navigateToCommandTarget(id: string, target: string) {
    setOpen(false);
    setQuery("");
    if (id === "new_chat") {
      resetChatRuntimeForNewChat();
      await navigate({
        to: "/chat",
        search: { new: crypto.randomUUID() },
      });
      return;
    }
    await navigate({ to: target as "/chat" });
  }

  async function runCommand(command: NativeCommand) {
    const id = commandId(command);
    if (!id || runningId) {
      return;
    }
    const unavailableReason = commandUnavailableReason(command);
    if (unavailableReason) {
      toast.error("Command blocked", {
        description: unavailableReason,
      });
      return;
    }
    setRunningId(id);
    try {
      const planned = await planCommandRun(command, id, query, projectId);
      if (planned.blockReason) {
        toast.error("Command blocked", {
          description: planned.blockReason,
        });
        return;
      }
      if (!planned.target) {
        toast.info("Command planned", {
          description: readString(command.label, id),
        });
        return;
      }
      await navigateToCommandTarget(id, planned.target);
    } catch (error) {
      toast.error("Command failed", {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setRunningId(null);
    }
  }

  if (disabledHere) {
    return null;
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Command Palette"
      description="Search native CogniX commands"
      className="max-w-2xl border-border bg-popover shadow-2xl"
    >
      <Command shouldFilter={false} className="bg-transparent">
        <CommandInput
          value={query}
          onValueChange={setQuery}
          placeholder="Search CogniX"
          autoFocus={true}
        />
        <CommandList className="max-h-[420px] px-1 pb-1">
          {loading ? (
            <div className="flex h-24 items-center justify-center text-muted-foreground">
              <Spinner className="size-4" />
            </div>
          ) : null}
          {!loading && groupedCommands.length === 0 ? (
            <CommandEmpty className="text-muted-foreground">
              No commands found.
            </CommandEmpty>
          ) : null}
          {loading
            ? null
            : groupedCommands.map(([category, items], index) => (
                <CommandGroup key={category} heading={labelize(category)}>
                  {items.map((command) => {
                    const Icon = commandIcon(command);
                    const available = readBoolean(command.available, false);
                    const id = commandId(command);
                    return (
                      <CommandItem
                        key={id}
                        value={`${readString(command.label)} ${readString(command.description)} ${id}`}
                        className={cn(!available && "opacity-65")}
                        onSelect={() => {
                          runCommand(command).catch((error: unknown) => {
                            toast.error("Command failed", {
                              description:
                                error instanceof Error
                                  ? error.message
                                  : undefined,
                            });
                          });
                        }}
                      >
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                          {runningId === id ? (
                            <Spinner className="size-4" />
                          ) : (
                            <Icon className="size-4" strokeWidth={1.8} />
                          )}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">
                            {readString(command.label, id)}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {readString(command.description)}
                          </span>
                        </span>
                        <span className="ml-auto flex shrink-0 items-center gap-1.5">
                          <span
                            className={cn(
                              "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                              riskClass(command.riskLevel),
                            )}
                          >
                            {labelize(command.riskLevel)}
                          </span>
                          {available ? null : (
                            <Badge variant="destructive" className="h-5">
                              blocked
                            </Badge>
                          )}
                        </span>
                      </CommandItem>
                    );
                  })}
                  {index < groupedCommands.length - 1 ? (
                    <CommandSeparator />
                  ) : null}
                </CommandGroup>
              ))}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
