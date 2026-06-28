# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX live context graph planning.

The graph builder converts project context into deterministic nodes and edges.
It does not call models, retrieve external data, execute tools, or mutate UI.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


COGNIX_CONTEXT_GRAPH_VERSION = "cognix_context_graph_v1"
COGNIX_ENTITY_EXTRACTOR_VERSION = "cognix_entity_extractor_v1"
COGNIX_RELATION_BUILDER_VERSION = "cognix_relation_builder_v1"

MAX_CONCEPTS = 18
MAX_NODES = 180
MAX_EDGES = 360

STOPWORDS = {
    "avec",
    "dans",
    "des",
    "les",
    "pour",
    "une",
    "the",
    "and",
    "that",
    "this",
    "from",
    "project",
    "projet",
    "cognix",
    "user",
    "assistant",
    "message",
    "document",
    "fichier",
    "faire",
    "mode",
    "sur",
    "sans",
    "plus",
    "comme",
    "source",
    "sources",
}

VISUAL_TOKENS = {
    "project": {"colorToken": "accent", "icon": "folder"},
    "document": {"colorToken": "info", "icon": "file-text"},
    "chat": {"colorToken": "neutral", "icon": "message-square"},
    "concept": {"colorToken": "success", "icon": "sparkles"},
    "model": {"colorToken": "warning", "icon": "brain"},
    "decision": {"colorToken": "danger", "icon": "check-circle"},
    "task": {"colorToken": "accent-muted", "icon": "list-checks"},
    "file": {"colorToken": "neutral-muted", "icon": "file"},
    "tool": {"colorToken": "info-muted", "icon": "wrench"},
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _slug(value: Any, *, fallback: str = "item") -> str:
    text = _normalize(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or fallback)[:80]


def _clip(value: Any, limit: int = 260) -> str:
    text = _normalize(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_from_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    parts = []
    for key in ("title", "name", "label", "summary", "content", "text", "message", "objective", "description"):
        if item.get(key):
            parts.append(str(item.get(key)))
    return " ".join(parts)


def _display_label(node_type: str, item: Any, index: int, fallback_text: str) -> str:
    if isinstance(item, dict):
        if node_type == "chat":
            role = item.get("role") or item.get("author") or "message"
            return f"{str(role).title()} message {index + 1}"
        for key in ("title", "name", "label", "id"):
            if item.get(key):
                return str(item.get(key))
    if node_type == "chat":
        return f"Chat message {index + 1}"
    if node_type in {"file", "tool", "model"}:
        return str(item)
    return fallback_text.split(".")[0] if fallback_text else f"{node_type.title()} {index + 1}"


def _node(
    *,
    node_id: str,
    node_type: str,
    label: str,
    source: str,
    weight: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "label": _clip(label, 120),
        "source": source,
        "weight": round(float(weight), 3),
        "visual": VISUAL_TOKENS.get(node_type, {"colorToken": "neutral", "icon": "circle"}),
        "metadata": metadata or {},
    }


def _edge(
    *,
    source: str,
    target: str,
    edge_type: str,
    label: str,
    weight: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"edge_{_slug(source)}_{_slug(edge_type)}_{_slug(target)}"[:180],
        "source": source,
        "target": target,
        "type": edge_type,
        "label": label,
        "weight": round(float(weight), 3),
        "metadata": metadata or {},
    }


def _add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    existing = nodes.get(node["id"])
    if existing is None:
        nodes[node["id"]] = node
        return
    existing["weight"] = round(max(float(existing.get("weight") or 0), float(node.get("weight") or 0)), 3)


def _add_edge(edges: dict[str, dict[str, Any]], edge: dict[str, Any]) -> None:
    existing = edges.get(edge["id"])
    if existing is None:
        edges[edge["id"]] = edge
        return
    existing["weight"] = round(max(float(existing.get("weight") or 0), float(edge.get("weight") or 0)), 3)


def _concept_terms(items: list[Any], *, project_type: str | None = None) -> list[dict[str, Any]]:
    text = " ".join(_text_from_item(item) for item in items)
    words = [
        word.lower()
        for word in re.findall(r"[^\W\d_][\w+#.-]{2,}", text)
        if word.lower() not in STOPWORDS
    ]
    counter = Counter(words)
    if project_type:
        counter[_slug(project_type)] += 3
    concepts: list[dict[str, Any]] = []
    for term, count in counter.most_common(MAX_CONCEPTS):
        if len(term) < 3:
            continue
        concepts.append(
            {
                "id": f"concept_{_slug(term)}",
                "term": term,
                "label": term.replace("_", " ").title(),
                "score": round(min(1.0, 0.25 + (count * 0.08)), 3),
                "mentions": count,
            }
        )
    return concepts


def _item_id(prefix: str, item: Any, index: int) -> str:
    if isinstance(item, dict):
        raw = item.get("id") or item.get("threadId") or item.get("messageId") or item.get("name") or item.get("title")
    else:
        raw = item
    return f"{prefix}_{_slug(raw, fallback = str(index))}"


def build_context_graph_blueprint() -> dict[str, Any]:
    return {
        "contextGraphVersion": COGNIX_CONTEXT_GRAPH_VERSION,
        "entityExtractorVersion": COGNIX_ENTITY_EXTRACTOR_VERSION,
        "relationBuilderVersion": COGNIX_RELATION_BUILDER_VERSION,
        "mode": "declarative_graph_contract",
        "nodeTypes": [
            {"id": "project", "label": "Projet", **VISUAL_TOKENS["project"]},
            {"id": "document", "label": "Document", **VISUAL_TOKENS["document"]},
            {"id": "chat", "label": "Chat", **VISUAL_TOKENS["chat"]},
            {"id": "concept", "label": "Concept", **VISUAL_TOKENS["concept"]},
            {"id": "model", "label": "Modele", **VISUAL_TOKENS["model"]},
            {"id": "decision", "label": "Decision", **VISUAL_TOKENS["decision"]},
            {"id": "task", "label": "Tache", **VISUAL_TOKENS["task"]},
            {"id": "file", "label": "Fichier", **VISUAL_TOKENS["file"]},
            {"id": "tool", "label": "Outil", **VISUAL_TOKENS["tool"]},
        ],
        "edgeTypes": [
            "contains",
            "mentions",
            "derived_from",
            "uses_model",
            "uses_tool",
            "decides",
            "tracks_task",
            "references_file",
            "related_to",
        ],
        "displayContract": {
            "projectTabCompatible": True,
            "usesExistingCardsPanelsBadges": True,
            "themeAwareTokensOnly": True,
            "customVisualizationLibraryRequired": False,
            "rawConversationContentVisibleByDefault": False,
        },
        "policies": {
            "projectScoped": True,
            "userIsolationRequired": True,
            "rawMessageContentStoredInGraph": False,
            "externalRetrievalAllowed": False,
            "modelGenerationAllowed": False,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "externalRetrieval": False,
            "toolExecution": False,
            "snapshotWrite": False,
            "uiMutation": False,
        },
    }


def build_context_graph_snapshot(
    *,
    username: str,
    project_id: str | None = None,
    project_name: str | None = None,
    project_type: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    documents: list[dict[str, Any]] | None = None,
    files: list[Any] | None = None,
    decisions: list[Any] | None = None,
    tasks: list[Any] | None = None,
    models: list[Any] | None = None,
    tools: list[Any] | None = None,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    project_node_id = f"project_{_slug(project_id or project_name or username, fallback = 'current')}"

    _add_node(
        nodes,
        _node(
            node_id = project_node_id,
            node_type = "project",
            label = project_name or project_id or "Projet CogniX",
            source = "chat_project",
            weight = 1.0,
            metadata = {"projectId": project_id, "projectType": project_type},
        ),
    )

    all_items: list[Any] = []
    collections = {
        "document": _as_list(documents),
        "chat": _as_list(messages),
        "file": _as_list(files),
        "decision": _as_list(decisions),
        "task": _as_list(tasks),
        "model": _as_list(models),
        "tool": _as_list(tools),
    }
    for items in collections.values():
        all_items.extend(items)

    concepts = _concept_terms(all_items, project_type = project_type)
    for concept in concepts:
        concept_node = _node(
            node_id = concept["id"],
            node_type = "concept",
            label = concept["label"],
            source = "entity_extractor",
            weight = concept["score"],
            metadata = {"mentions": concept["mentions"], "term": concept["term"]},
        )
        _add_node(nodes, concept_node)
        _add_edge(
            edges,
            _edge(
                source = project_node_id,
                target = concept["id"],
                edge_type = "mentions",
                label = "Concept du projet",
                weight = concept["score"],
            ),
        )

    concept_terms = [(concept["term"], concept["id"]) for concept in concepts]
    for node_type, items in collections.items():
        for index, item in enumerate(items[:60]):
            text = _text_from_item(item)
            if not text and not isinstance(item, str):
                continue
            node_id = _item_id(node_type, item, index)
            label = _display_label(node_type, item, index, text)
            metadata = {"index": index}
            if isinstance(item, dict):
                metadata.update(
                    {
                        key: item.get(key)
                        for key in ("id", "threadId", "messageId", "kind", "source", "modelId", "status")
                        if item.get(key) is not None
                    }
                )
            _add_node(
                nodes,
                _node(
                    node_id = node_id,
                    node_type = node_type,
                    label = label,
                    source = f"input_{node_type}",
                    weight = 0.75,
                    metadata = metadata,
                ),
            )
            relation_type = {
                "document": "contains",
                "chat": "derived_from",
                "file": "references_file",
                "decision": "decides",
                "task": "tracks_task",
                "model": "uses_model",
                "tool": "uses_tool",
            }.get(node_type, "contains")
            _add_edge(
                edges,
                _edge(
                    source = project_node_id,
                    target = node_id,
                    edge_type = relation_type,
                    label = relation_type.replace("_", " "),
                    weight = 0.72,
                ),
            )
            lowered_text = text.lower()
            for term, concept_id in concept_terms[:MAX_CONCEPTS]:
                if term and term in lowered_text:
                    _add_edge(
                        edges,
                        _edge(
                            source = node_id,
                            target = concept_id,
                            edge_type = "mentions",
                            label = "Mentionne",
                            weight = 0.5,
                        ),
                    )

    node_list = list(nodes.values())[:MAX_NODES]
    valid_ids = {node["id"] for node in node_list}
    edge_list = [
        edge for edge in edges.values()
        if edge["source"] in valid_ids and edge["target"] in valid_ids
    ][:MAX_EDGES]
    type_counts = Counter(str(node.get("type")) for node in node_list)
    return {
        "contextGraphVersion": COGNIX_CONTEXT_GRAPH_VERSION,
        "entityExtractorVersion": COGNIX_ENTITY_EXTRACTOR_VERSION,
        "relationBuilderVersion": COGNIX_RELATION_BUILDER_VERSION,
        "mode": "snapshot_dry_run",
        "username": username,
        "projectId": project_id,
        "projectName": project_name,
        "projectType": project_type,
        "nodes": node_list,
        "edges": edge_list,
        "summary": {
            "nodeCount": len(node_list),
            "edgeCount": len(edge_list),
            "conceptCount": type_counts.get("concept", 0),
            "documentCount": type_counts.get("document", 0),
            "chatCount": type_counts.get("chat", 0),
            "fileCount": type_counts.get("file", 0),
            "modelCount": type_counts.get("model", 0),
            "toolCount": type_counts.get("tool", 0),
        },
        "displayContract": {
            "projectTabCompatible": True,
            "themeAwareTokensOnly": True,
            "rawConversationContentVisibleByDefault": False,
            "nodeLabelsAreSummaries": True,
            "layout": "force_or_cluster",
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "externalRetrieval": False,
            "toolExecution": False,
            "snapshotWrite": False,
            "uiMutation": False,
        },
    }
