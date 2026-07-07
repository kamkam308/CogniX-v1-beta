// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  BrainCircuitIcon,
  CheckCircle2Icon,
  CircleIcon,
  FileIcon,
  FileTextIcon,
  FolderIcon,
  ListChecksIcon,
  MessageSquareIcon,
  RefreshCwIcon,
  SparklesIcon,
  WrenchIcon,
} from "lucide-react";
import {
  type ComponentType,
  type SVGProps,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  buildContextGraph,
  listContextGraphSnapshots,
  type ContextGraphEdge,
  type ContextGraphNode,
  type ContextGraphSnapshot,
  type StoredContextGraphSnapshot,
} from "../api/chat-api";
import type { SidebarItem } from "../hooks/use-chat-sidebar-items";

type NodeIcon = ComponentType<SVGProps<SVGSVGElement>>;

type PositionedNode = {
  node: ContextGraphNode;
  x: number;
  y: number;
};

const GRAPH_WIDTH = 640;
const GRAPH_HEIGHT = 340;
const GRAPH_CENTER_X = GRAPH_WIDTH / 2;
const GRAPH_CENTER_Y = GRAPH_HEIGHT / 2;
const MAX_RENDERED_NODES = 28;

const NODE_ICONS: Record<string, NodeIcon> = {
  project: FolderIcon,
  document: FileTextIcon,
  chat: MessageSquareIcon,
  concept: SparklesIcon,
  model: BrainCircuitIcon,
  decision: CheckCircle2Icon,
  task: ListChecksIcon,
  file: FileIcon,
  tool: WrenchIcon,
};

const NODE_COLOR_CLASSES: Record<string, string> = {
  project: "bg-primary/10 text-primary ring-primary/20",
  document: "bg-blue-500/10 text-blue-700 ring-blue-500/20 dark:text-blue-300",
  chat: "bg-muted text-muted-foreground ring-border",
  concept:
    "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300",
  model:
    "bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-300",
  decision: "bg-red-500/10 text-red-700 ring-red-500/20 dark:text-red-300",
  task: "bg-primary/10 text-primary ring-primary/20",
  file: "bg-muted text-muted-foreground ring-border",
  tool: "bg-cyan-500/10 text-cyan-700 ring-cyan-500/20 dark:text-cyan-300",
};

const NODE_STROKE_COLORS: Record<string, string> = {
  project: "hsl(var(--primary))",
  document: "rgb(37 99 235)",
  chat: "hsl(var(--muted-foreground))",
  concept: "rgb(5 150 105)",
  model: "rgb(217 119 6)",
  decision: "rgb(220 38 38)",
  task: "hsl(var(--primary))",
  file: "hsl(var(--muted-foreground))",
  tool: "rgb(8 145 178)",
};

const TYPE_LABELS: Record<string, string> = {
  project: "Project",
  document: "Documents",
  chat: "Chats",
  concept: "Concepts",
  model: "Models",
  decision: "Decisions",
  task: "Tasks",
  file: "Files",
  tool: "Tools",
};

function itemMessageSeed(item: SidebarItem): Record<string, unknown> {
  return {
    id: item.id,
    title: item.title,
    content: item.title,
    kind: item.type,
    projectId: item.projectId ?? null,
    createdAt: item.createdAt,
  };
}

function nodeColorClass(type: string | undefined): string {
  return NODE_COLOR_CLASSES[type ?? ""] ?? "bg-muted text-muted-foreground ring-border";
}

function nodeStrokeColor(type: string | undefined): string {
  return NODE_STROKE_COLORS[type ?? ""] ?? "hsl(var(--muted-foreground))";
}

function nodeTypeLabel(type: string | undefined): string {
  return TYPE_LABELS[type ?? ""] ?? (type ? type.replace(/[_-]+/g, " ") : "Node");
}

function formatSnapshotDate(value: string | null | undefined): string {
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

function nodeTypeCounts(nodes: ContextGraphNode[]): Record<string, number> {
  return nodes.reduce<Record<string, number>>((counts, node) => {
    counts[node.type] = (counts[node.type] ?? 0) + 1;
    return counts;
  }, {});
}

function positionedNodes(nodes: ContextGraphNode[]): PositionedNode[] {
  const projectIndex = nodes.findIndex((node) => node.type === "project");
  const ordered =
    projectIndex >= 0
      ? [
          nodes[projectIndex],
          ...nodes.slice(0, projectIndex),
          ...nodes.slice(projectIndex + 1),
        ]
      : nodes;
  const visible = ordered.slice(0, MAX_RENDERED_NODES);
  const project = visible[0];
  const rest = visible.slice(1);
  const positioned: PositionedNode[] = project
    ? [{ node: project, x: GRAPH_CENTER_X, y: GRAPH_CENTER_Y }]
    : [];

  rest.forEach((node, index) => {
    const isConcept = node.type === "concept";
    const radius = isConcept ? 92 : 138;
    const angle = (Math.PI * 2 * index) / Math.max(rest.length, 1) - Math.PI / 2;
    positioned.push({
      node,
      x: GRAPH_CENTER_X + Math.cos(angle) * radius,
      y: GRAPH_CENTER_Y + Math.sin(angle) * radius,
    });
  });
  return positioned;
}

function latestGraphSnapshot(
  snapshots: StoredContextGraphSnapshot[],
): StoredContextGraphSnapshot | null {
  return snapshots.find((snapshot) => snapshot.graph) ?? snapshots[0] ?? null;
}

function ContextGraphMap({
  nodes,
  edges,
}: {
  nodes: ContextGraphNode[];
  edges: ContextGraphEdge[];
}) {
  const positioned = useMemo(() => positionedNodes(nodes), [nodes]);
  const byId = useMemo(
    () => new Map(positioned.map((item) => [item.node.id, item])),
    [positioned],
  );
  const visibleEdges = edges.filter(
    (edge) => byId.has(edge.source) && byId.has(edge.target),
  );

  return (
    <div className="aspect-[16/9] overflow-hidden rounded-[24px] border border-border/60 bg-background/70">
      <svg
        viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
        role="img"
        aria-label="Project context graph"
        className="h-full w-full"
      >
        <g>
          {visibleEdges.slice(0, 80).map((edge) => {
            const source = byId.get(edge.source);
            const target = byId.get(edge.target);
            if (!source || !target) return null;
            return (
              <line
                key={edge.id}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="rgb(148 163 184 / 0.45)"
                strokeWidth={Math.max(1, (edge.weight ?? 0.5) * 2)}
                strokeLinecap="round"
              />
            );
          })}
        </g>
        <g>
          {positioned.map(({ node, x, y }) => (
            <circle
              key={node.id}
              cx={x}
              cy={y}
              r={node.type === "project" ? 18 : 10 + Math.min(8, (node.weight ?? 0.5) * 8)}
              fill="transparent"
              stroke={nodeStrokeColor(node.type)}
              strokeWidth={node.type === "project" ? 4 : 2.5}
            >
              <title>{`${nodeTypeLabel(node.type)}: ${node.label}`}</title>
            </circle>
          ))}
        </g>
      </svg>
    </div>
  );
}

function ContextGraphNodeList({ nodes }: { nodes: ContextGraphNode[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {nodes.slice(0, 10).map((node) => {
        const Icon = NODE_ICONS[node.type] ?? CircleIcon;
        return (
          <div
            key={node.id}
            className="flex min-w-0 items-center gap-3 rounded-[18px] bg-background/70 px-3 py-2"
          >
            <span
              className={cn(
                "flex size-8 shrink-0 items-center justify-center rounded-full ring-1",
                nodeColorClass(node.type),
              )}
            >
              <Icon strokeWidth={1.75} className="size-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-foreground">
                {node.label}
              </p>
              <p className="text-xs text-muted-foreground">
                {nodeTypeLabel(node.type)}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ProjectContextGraphPanel({
  projectId,
  projectName,
  items,
}: {
  projectId: string;
  projectName: string;
  items: SidebarItem[];
}) {
  const [graph, setGraph] = useState<ContextGraphSnapshot | null>(null);
  const [snapshots, setSnapshots] = useState<StoredContextGraphSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messageSeeds = useMemo(
    () => items.slice(0, 40).map(itemMessageSeed),
    [items],
  );

  const rebuildGraph = useCallback(
    async (showToast = false) => {
      setRefreshing(true);
      setError(null);
      try {
        const result = await buildContextGraph({
          projectId,
          projectName,
          projectType: "project",
          messages: messageSeeds,
          includeProjectThreads: true,
          storeSnapshot: true,
        });
        setGraph(result.contextGraph);
        if (result.snapshot) {
          setSnapshots((current) => [result.snapshot!, ...current]);
        }
        if (showToast) toast.success("Context graph refreshed");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Context graph unavailable";
        setError(message);
        if (showToast) {
          toast.error("Context graph unavailable", { description: message });
        }
      } finally {
        setRefreshing(false);
      }
    },
    [messageSeeds, projectId, projectName],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadGraph() {
      setLoading(true);
      setError(null);
      try {
        const existingSnapshots = await listContextGraphSnapshots({ projectId });
        if (cancelled) return;
        setSnapshots(existingSnapshots);
        const latest = latestGraphSnapshot(existingSnapshots);
        if (latest?.graph) {
          setGraph(latest.graph);
          return;
        }
        const result = await buildContextGraph({
          projectId,
          projectName,
          projectType: "project",
          messages: messageSeeds,
          includeProjectThreads: true,
          storeSnapshot: true,
        });
        if (cancelled) return;
        setGraph(result.contextGraph);
        setSnapshots(result.snapshot ? [result.snapshot] : []);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Context graph unavailable",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadGraph();
    return () => {
      cancelled = true;
    };
  }, [messageSeeds, projectId, projectName]);

  const nodes = useMemo(() => graph?.nodes ?? [], [graph]);
  const edges = useMemo(() => graph?.edges ?? [], [graph]);
  const counts = useMemo(() => nodeTypeCounts(nodes), [nodes]);
  const latestSnapshot = latestGraphSnapshot(snapshots);
  const safeGraph =
    graph?.sideEffects?.generation === false &&
    graph?.sideEffects?.toolExecution === false &&
    graph?.sideEffects?.modelLoad === false;

  if (loading) {
    return (
      <div className="mt-8 rounded-[26px] bg-muted/30 px-6 py-5">
        <Skeleton className="h-[260px] rounded-[24px]" />
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <Skeleton className="h-16 rounded-[18px]" />
          <Skeleton className="h-16 rounded-[18px]" />
          <Skeleton className="h-16 rounded-[18px]" />
        </div>
      </div>
    );
  }

  if (error && !graph) {
    return (
      <div className="mt-8 flex flex-col items-center justify-center gap-3 rounded-[26px] bg-muted/30 px-6 py-14 text-center">
        <p className="text-[15px] font-semibold text-foreground">
          Context graph unavailable
        </p>
        <p className="max-w-sm text-sm text-muted-foreground">{error}</p>
        <Button
          type="button"
          variant="outline"
          className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
          disabled={refreshing}
          onClick={() => void rebuildGraph(true)}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div
      data-testid="project-context-graph-panel"
      className="mt-8 rounded-[26px] bg-muted/30 px-6 py-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="rounded-full bg-background px-2.5 py-1 dark:bg-card">
            {nodes.length} nodes
          </span>
          <span className="rounded-full bg-background px-2.5 py-1 dark:bg-card">
            {edges.length} relations
          </span>
          {safeGraph ? (
            <span className="rounded-full bg-background px-2.5 py-1 dark:bg-card">
              no generation
            </span>
          ) : null}
          <span className="rounded-full bg-background px-2.5 py-1 dark:bg-card">
            {formatSnapshotDate(latestSnapshot?.createdAt)}
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="border-none bg-background text-foreground shadow-[0_2px_8px_-2px_rgba(0,0,0,0.16)] hover:bg-background/80 dark:bg-card dark:shadow-none dark:hover:bg-accent/50"
          disabled={refreshing}
          onClick={() => void rebuildGraph(true)}
        >
          <RefreshCwIcon
            strokeWidth={1.75}
            className={cn("size-4", refreshing && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {nodes.length > 0 ? (
        <>
          <ContextGraphMap nodes={nodes} edges={edges} />
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {(["document", "chat", "concept", "model", "tool", "task"] as const).map(
              (type) => {
                const Icon = NODE_ICONS[type] ?? CircleIcon;
                return (
                  <div
                    key={type}
                    className="flex items-center gap-3 rounded-[18px] bg-background/70 px-3 py-2"
                  >
                    <span
                      className={cn(
                        "flex size-8 shrink-0 items-center justify-center rounded-full ring-1",
                        nodeColorClass(type),
                      )}
                    >
                      <Icon strokeWidth={1.75} className="size-4" />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-foreground">
                        {counts[type] ?? 0}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {nodeTypeLabel(type)}
                      </p>
                    </div>
                  </div>
                );
              },
            )}
          </div>
          <div className="mt-4">
            <ContextGraphNodeList nodes={nodes} />
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center gap-3 rounded-[24px] bg-background/70 px-6 py-14 text-center">
          <p className="text-[15px] font-semibold text-foreground">
            No graph snapshot yet
          </p>
          <Button
            type="button"
            variant="outline"
            className="border-none bg-muted text-foreground hover:bg-muted/80"
            disabled={refreshing}
            onClick={() => void rebuildGraph(true)}
          >
            Build graph
          </Button>
        </div>
      )}
    </div>
  );
}
