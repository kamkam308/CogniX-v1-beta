# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX product/admin API routes."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth import storage as auth_storage
from auth.authentication import get_current_jwt_subject
from core.cognix.strategy import build_strategy
from storage import cognix_db
from storage.studio_db import list_chat_messages_for_threads, list_chat_projects, list_chat_threads


router = APIRouter()


class ApprovalCreateRequest(BaseModel):
    reason: str = Field(..., min_length = 3, max_length = 2000)


class ApprovalDecisionRequest(BaseModel):
    status: Literal["pending", "approved", "denied"]
    admin_note: str | None = Field(None, max_length = 2000)


class ReportCreateRequest(BaseModel):
    category: str = Field("general", min_length = 1, max_length = 80)
    title: str = Field(..., min_length = 3, max_length = 160)
    message: str = Field(..., min_length = 3, max_length = 4000)


class ReportStatusRequest(BaseModel):
    status: Literal["open", "in_review", "resolved", "closed"]


class BanStatusRequest(BaseModel):
    status: Literal["pending_admin_review", "active", "cleared", "permanent"]
    admin_decision: str | None = Field(None, max_length = 2000)


class ContextMemoryRequest(BaseModel):
    content: str = Field("", max_length = 120000)


class LibraryItemRequest(BaseModel):
    kind: Literal["file", "image", "video", "document", "dataset", "other"] = "other"
    name: str = Field(..., min_length = 1, max_length = 240)
    source: str = Field("manual", max_length = 80)
    size_bytes: int | None = Field(None, ge = 0)
    uri: str | None = Field(None, max_length = 2000)
    metadata: dict[str, Any] | None = None


class ScheduledTaskCreateRequest(BaseModel):
    title: str = Field(..., min_length = 1, max_length = 160)
    prompt: str = Field(..., min_length = 1, max_length = 4000)
    schedule_text: str = Field(..., min_length = 1, max_length = 160)


class ScheduledTaskStatusRequest(BaseModel):
    status: Literal["active", "paused", "done", "cancelled"]


class AppConnectionRequest(BaseModel):
    app_id: str = Field(..., min_length = 1, max_length = 80)
    app_name: str = Field(..., min_length = 1, max_length = 120)
    status: Literal["connected", "disabled"] = "connected"


class SocialMessageRequest(BaseModel):
    content: str = Field(..., min_length = 1, max_length = 2000)


class SocialAgentRequest(BaseModel):
    prompt: str | None = Field(None, max_length = 1000)


class ModelPinRequest(BaseModel):
    model_id: str = Field(..., min_length = 1, max_length = 240)
    label: str = Field(..., min_length = 1, max_length = 240)


class ProjectShareCreateRequest(BaseModel):
    project_id: str = Field(..., min_length = 1, max_length = 160)
    permission: Literal["view", "edit"] = "view"


class ImageRequest(BaseModel):
    prompt: str = Field(..., min_length = 1, max_length = 4000)
    model: str | None = Field(None, max_length = 160)


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length = 2, max_length = 500)


class AgentRunRequest(BaseModel):
    goal: str = Field(..., min_length = 2, max_length = 2000)
    mode: Literal["agent", "research", "automation"] = "agent"


class NewsRefreshRequest(BaseModel):
    topic: str = Field("intelligence artificielle", min_length = 1, max_length = 120)


class GameCreateRequest(BaseModel):
    game_type: Literal["chess", "quiz", "code_duel"] = "chess"
    opponent_type: Literal["ai", "user"] = "ai"
    opponent_username: str | None = Field(None, max_length = 120)


class GameMoveRequest(BaseModel):
    from_square: str = Field(..., min_length = 2, max_length = 2)
    to_square: str = Field(..., min_length = 2, max_length = 2)


APP_CATALOG = [
    {"id": "canva", "name": "Canva", "category": "Design", "description": "Creer des designs et supports."},
    {"id": "google-drive", "name": "Google Drive", "category": "Files", "description": "Importer et organiser les fichiers."},
    {"id": "github", "name": "GitHub", "category": "Code", "description": "Depots, issues et pull requests."},
    {"id": "hugging-face", "name": "Hugging Face", "category": "AI", "description": "Modeles, datasets et jobs GPU."},
    {"id": "notion", "name": "Notion", "category": "Productivity", "description": "Docs, bases et suivi projet."},
    {"id": "gmail", "name": "Gmail", "category": "Communication", "description": "Lecture et redaction assistee."},
]


NEWS_FEEDS = [
    ("Google News", "https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr"),
    ("Hacker News", "https://hnrss.org/newest?q={query}"),
]


def _require_admin(current_subject: str) -> None:
    if not auth_storage.is_admin(current_subject):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail = "Admin access required",
        )


def _row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a frontend-friendly copy while keeping raw fields available."""

    out = dict(row)
    alias_map = {
        "request_type": "requestType",
        "admin_note": "adminNote",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
        "decided_at": "decidedAt",
        "decided_by": "decidedBy",
        "temporary_until": "temporaryUntil",
        "admin_decision": "adminDecision",
        "client_key": "clientKey",
        "pattern_label": "patternLabel",
        "ban_id": "banId",
        "updated_by": "updatedBy",
        "size_bytes": "sizeBytes",
        "metadata_json": "metadataJson",
        "schedule_text": "scheduleText",
        "display_name": "displayName",
        "app_id": "appId",
        "app_name": "appName",
        "model_id": "modelId",
        "project_id": "projectId",
        "owner_username": "ownerUsername",
        "collaborator_username": "collaboratorUsername",
        "share_id": "shareId",
        "revoked_at": "revokedAt",
        "topics_json": "topicsJson",
        "source_thread_ids_json": "sourceThreadIdsJson",
        "artifact_uri": "artifactUri",
        "task_id": "taskId",
        "action_type": "actionType",
        "artifact_type": "artifactType",
        "artifact_id": "artifactId",
        "finished_at": "finishedAt",
        "sources_json": "sourcesJson",
        "plan_json": "planJson",
        "published_at": "publishedAt",
        "game_type": "gameType",
        "opponent_type": "opponentType",
        "opponent_username": "opponentUsername",
        "state_json": "stateJson",
    }
    for source, target in alias_map.items():
        if source in out:
            out[target] = out[source]
    return out


def _rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_row(row) for row in rows]


def _dashboard_password_status(user: dict[str, Any]) -> dict[str, Any]:
    locked = bool(user.get("loginLocked"))
    permanent = bool(user.get("loginPermanentlyLocked"))
    must_change = bool(user.get("mustChangePassword"))
    failed = int(user.get("failedLoginCount") or 0)
    if permanent:
        label = "Compte verrouille"
    elif locked:
        label = "Verrouillage temporaire"
    elif must_change:
        label = "Changement requis"
    elif failed:
        label = f"{failed} echec(s) recent(s)"
    else:
        label = "Configure"
    return {
        "configured": True,
        "label": label,
        "mustChangePassword": must_change,
        "locked": locked,
        "permanentlyLocked": permanent,
        "failedAttempts": failed,
        "lockoutLevel": int(user.get("loginLockoutLevel") or 0),
        "lockoutUntil": user.get("loginLockoutUntil"),
        "secretExposed": False,
    }


def _dashboard_quota(plan: str, used_tokens: int) -> dict[str, Any]:
    normalized_plan = (plan or "free").strip() or "free"
    is_unlimited = normalized_plan.casefold() == "ceo"
    return {
        "plan": normalized_plan,
        "usedTokens": int(used_tokens or 0),
        "limitTokens": None,
        "remainingTokens": None,
        "unlimited": is_unlimited,
        "label": "Illimite" if is_unlimited else "Quota non configure",
    }


def _dashboard_model_name(thread: dict[str, Any]) -> str:
    return str(thread.get("modelId") or thread.get("modelType") or "Modele inconnu")


def _build_dashboard_user_details(
    users: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    usage: list[dict[str, Any]],
    security_events: list[dict[str, Any]],
    bans: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    collaborators: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    threads_by_user: dict[str, list[dict[str, Any]]] = {}
    projects_by_user: dict[str, list[dict[str, Any]]] = {}
    usage_by_user: dict[str, list[dict[str, Any]]] = {}
    collaborators_by_owner: dict[str, list[dict[str, Any]]] = {}
    collaborators_by_user: dict[str, list[dict[str, Any]]] = {}
    security_by_user: dict[str, list[dict[str, Any]]] = {}
    bans_by_user: dict[str, list[dict[str, Any]]] = {}
    reports_by_user: dict[str, list[dict[str, Any]]] = {}

    for thread in threads:
        owner = str(thread.get("ownerUsername") or "unknown")
        threads_by_user.setdefault(owner, []).append(thread)
    for project in projects:
        owner = str(project.get("ownerUsername") or "unknown")
        projects_by_user.setdefault(owner, []).append(project)
    for item in usage:
        owner = str(item.get("username") or item.get("ownerUsername") or "unknown")
        usage_by_user.setdefault(owner, []).append(item)
    for item in collaborators:
        owner = str(item.get("owner_username") or item.get("ownerUsername") or "unknown")
        collaborator = str(item.get("collaborator_username") or item.get("collaboratorUsername") or "unknown")
        collaborators_by_owner.setdefault(owner, []).append(item)
        collaborators_by_user.setdefault(collaborator, []).append(item)
    for item in security_events:
        owner = str(item.get("username") or "unknown")
        security_by_user.setdefault(owner, []).append(item)
    for item in bans:
        owner = str(item.get("username") or "unknown")
        bans_by_user.setdefault(owner, []).append(item)
    for item in reports:
        owner = str(item.get("username") or "unknown")
        reports_by_user.setdefault(owner, []).append(item)

    details: dict[str, dict[str, Any]] = {}
    for user in users:
        username = str(user.get("username") or "unknown")
        user_threads = threads_by_user.get(username, [])
        user_projects = projects_by_user.get(username, [])
        user_usage = usage_by_user.get(username, [])
        used_tokens = sum(int(item.get("approxTokens") or item.get("estimatedTokens") or 0) for item in user_usage)
        model_usage = sorted(
            user_usage,
            key = lambda item: int(item.get("approxTokens") or item.get("estimatedTokens") or 0),
            reverse = True,
        )
        recent_chats = [
            {
                "id": thread.get("id"),
                "title": thread.get("title") or "Conversation",
                "modelId": _dashboard_model_name(thread),
                "createdAt": thread.get("createdAt"),
                "projectId": thread.get("projectId"),
            }
            for thread in user_threads[:8]
        ]
        project_collaborator_counts: dict[str, int] = {}
        for collab in collaborators_by_owner.get(username, []):
            project_id = str(collab.get("project_id") or collab.get("projectId") or "")
            if project_id:
                project_collaborator_counts[project_id] = project_collaborator_counts.get(project_id, 0) + 1
        project_items = [
            {
                "id": project.get("id"),
                "name": project.get("name") or "Projet",
                "archived": bool(project.get("archived")),
                "updatedAt": project.get("updatedAt"),
                "collaborators": project_collaborator_counts.get(str(project.get("id") or ""), 0),
            }
            for project in user_projects
        ]
        details[username] = {
            "username": username,
            "displayName": user.get("displayName") or username,
            "plan": user.get("plan") or "free",
            "role": user.get("role") or "user",
            "chatCount": len(user_threads),
            "projectCount": len(user_projects),
            "models": model_usage,
            "quota": _dashboard_quota(str(user.get("plan") or "free"), used_tokens),
            "passwordStatus": _dashboard_password_status(user),
            "network": {
                "lastLoginIp": user.get("lastLoginIp"),
                "lastLoginAt": user.get("lastLoginAt"),
            },
            "recentChats": recent_chats,
            "projects": project_items,
            "collaborations": collaborators_by_user.get(username, []),
            "securityEvents": len(security_by_user.get(username, [])),
            "activeBans": sum(
                1
                for item in bans_by_user.get(username, [])
                if item.get("status") in {"pending_admin_review", "active", "permanent"}
            ),
            "openReports": sum(
                1
                for item in reports_by_user.get(username, [])
                if item.get("status") in {"open", "in_review"}
            ),
        }
    return details


def _strip_html(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _short_summary(*parts: str, limit: int = 360) -> str:
    text = _strip_html(" ".join(part for part in parts if part))
    if not text:
        return "Resume indisponible pour le moment."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentences[:2]).strip()
    if len(summary) > limit:
        summary = summary[: limit - 1].rstrip() + "..."
    return summary


def _xml_text(node: ET.Element | None, tag: str) -> str:
    if node is None:
        return ""
    child = node.find(tag)
    if child is None:
        child = node.find(f"{{*}}{tag}")
    return _strip_html(child.text if child is not None else "")


def _xml_link(node: ET.Element | None) -> str:
    if node is None:
        return ""
    link = _xml_text(node, "link")
    if link:
        return link
    for child in node.findall("{*}link"):
        href = child.attrib.get("href")
        if href:
            return href
    return ""


def _parse_published(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return value[:80]


def _fetch_feed_items(topic: str, limit: int = 10) -> list[dict[str, Any]]:
    query = urllib.parse.quote_plus(topic or "intelligence artificielle")
    items: list[dict[str, Any]] = []
    for source, template in NEWS_FEEDS:
        if len(items) >= limit:
            break
        url = template.format(query = query)
        request = urllib.request.Request(
            url,
            headers = {"User-Agent": "CogniX/0.9 (+local studio)"},
        )
        try:
            with urllib.request.urlopen(request, timeout = 5) as response:
                raw = response.read(750_000)
            root = ET.fromstring(raw)
        except Exception:
            continue

        feed_items = root.findall(".//item") or root.findall(".//{*}entry")
        for item in feed_items:
            title = _xml_text(item, "title")
            item_url = _xml_link(item)
            description = _xml_text(item, "description") or _xml_text(item, "summary")
            published = (
                _xml_text(item, "pubDate")
                or _xml_text(item, "published")
                or _xml_text(item, "updated")
            )
            if not title or not item_url:
                continue
            items.append(
                {
                    "topic": topic,
                    "title": title[:240],
                    "summary": _short_summary(title, description),
                    "url": item_url,
                    "source": source,
                    "published_at": _parse_published(published),
                }
            )
            if len(items) >= limit:
                break
    return items


def _research_summary(query: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return (
            "CogniX a cree une fiche de recherche pour ce sujet. "
            "Aucune source externe n'a repondu assez vite; relancez la recherche plus tard ou precisez le sujet."
        )
    titles = [str(source.get("title") or "").strip() for source in sources[:5] if source.get("title")]
    return (
        f"Recherche approfondie sur '{query}'. "
        "Les sources recentes convergent autour de: "
        + "; ".join(titles)
        + ". CogniX garde ces sources pour produire un rapport plus long ensuite."
    )


def _agent_plan(goal: str, mode: str) -> list[str]:
    base = [
        "Clarifier l'objectif et les criteres de reussite.",
        "Identifier les donnees, outils et permissions necessaires.",
        "Executer les etapes a faible risque en premier.",
        "Verifier le resultat et preparer un compte rendu.",
    ]
    if mode == "research":
        base.insert(1, "Collecter des sources et distinguer faits, hypotheses et inconnues.")
    elif mode == "automation":
        base.insert(2, "Planifier les actions dans le temps avec points de controle.")
    return base


def _scheduled_action_type(prompt: str) -> str:
    text = prompt.lower()
    if any(word in text for word in ("news", "actualite", "actualité", "veille", "surveille")):
        return "news"
    if any(word in text for word in ("recherche", "research", "analyse", "rapport", "source")):
        return "research"
    if any(word in text for word in ("agent", "action", "automatisation", "execute", "exécute")):
        return "agent"
    return "report"


def _execute_scheduled_task(username: str, task: dict[str, Any]) -> dict[str, Any]:
    prompt = str(task.get("prompt") or task.get("title") or "").strip()
    action_type = _scheduled_action_type(prompt)
    artifact_type = None
    artifact_id = None

    if action_type == "news":
        topic = prompt or "intelligence artificielle"
        items = _fetch_feed_items(topic, limit = 8)
        for item in items:
            cognix_db.create_news_item(
                username,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
        result = f"Veille terminee: {len(items)} actualites ajoutees pour '{topic[:80]}'."
        artifact_type = "news"
    elif action_type == "research":
        query = prompt or "Recherche CogniX"
        sources = _fetch_feed_items(query, limit = 6)
        report = cognix_db.create_research_report(
            username,
            query,
            "Recherche planifiee: " + query[:90],
            _research_summary(query, sources),
            [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "publishedAt": item.get("published_at"),
                }
                for item in sources
            ],
        )
        artifact_type = "research"
        artifact_id = str(report.get("id") or "")
        result = f"Recherche planifiee terminee avec {len(sources)} sources."
    elif action_type == "agent":
        plan = _agent_plan(prompt or "Action planifiee", "automation")
        run = cognix_db.create_agent_run(
            username,
            prompt or "Action planifiee",
            "automation",
            plan,
            "Run cree depuis une tache planifiee.",
        )
        artifact_type = "agent_run"
        artifact_id = str(run.get("id") or "")
        result = f"Agent planifie avec {len(plan)} etapes."
    else:
        item = cognix_db.create_library_item(
            username,
            kind = "document",
            name = "Compte rendu planifie: " + (task.get("title") or "Tache")[:80],
            source = "scheduled_task",
            metadata = {"taskId": task.get("id"), "prompt": prompt},
        )
        artifact_type = "library_item"
        artifact_id = str(item.get("id") or "")
        result = "Compte rendu de tache cree dans la bibliotheque."

    return cognix_db.create_scheduled_task_run(
        username,
        str(task.get("id")),
        action_type,
        result,
        artifact_type = artifact_type,
        artifact_id = artifact_id,
    )


def _game_initial_state(game_type: str) -> dict[str, Any]:
    if game_type == "chess":
        return {"board": _chess_initial_board(), "turn": "white", "moves": [], "winner": None, "message": "A vous de jouer."}
    if game_type == "quiz":
        return {"round": 1, "score": {"user": 0, "opponent": 0}, "topic": "general"}
    return {"round": 1, "challenge": "En attente", "score": {"user": 0, "opponent": 0}}


def _chess_initial_board() -> dict[str, str]:
    board: dict[str, str] = {}
    order = ["R", "N", "B", "Q", "K", "B", "N", "R"]
    for index, piece in enumerate(order):
        file_name = chr(ord("a") + index)
        board[f"{file_name}1"] = "w" + piece
        board[f"{file_name}2"] = "wP"
        board[f"{file_name}7"] = "bP"
        board[f"{file_name}8"] = "b" + piece
    return board


def _normalize_chess_state(state: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(state or {})
    board = normalized.get("board")
    if not isinstance(board, dict):
        board = _chess_initial_board()
    normalized["board"] = dict(board)
    normalized["turn"] = normalized.get("turn") if normalized.get("turn") in {"white", "black"} else "white"
    normalized["moves"] = normalized.get("moves") if isinstance(normalized.get("moves"), list) else []
    normalized["winner"] = normalized.get("winner")
    normalized["message"] = normalized.get("message") or "A vous de jouer."
    return normalized


def _square_xy(square: str) -> tuple[int, int]:
    if not re.fullmatch(r"[a-h][1-8]", square or ""):
        raise ValueError("Square invalide")
    return ord(square[0]) - ord("a"), int(square[1]) - 1


def _xy_square(x: int, y: int) -> str:
    return f"{chr(ord('a') + x)}{y + 1}"


def _piece_color(piece: str | None) -> str | None:
    if not piece:
        return None
    return "white" if piece[0] == "w" else "black"


def _path_clear(board: dict[str, str], from_square: str, to_square: str) -> bool:
    fx, fy = _square_xy(from_square)
    tx, ty = _square_xy(to_square)
    step_x = 0 if tx == fx else (1 if tx > fx else -1)
    step_y = 0 if ty == fy else (1 if ty > fy else -1)
    x = fx + step_x
    y = fy + step_y
    while (x, y) != (tx, ty):
        if board.get(_xy_square(x, y)):
            return False
        x += step_x
        y += step_y
    return True


def _is_chess_move_legal(board: dict[str, str], from_square: str, to_square: str, turn: str) -> tuple[bool, str]:
    if from_square == to_square:
        return False, "Choisissez deux cases differentes."
    try:
        fx, fy = _square_xy(from_square)
        tx, ty = _square_xy(to_square)
    except ValueError as exc:
        return False, str(exc)

    piece = board.get(from_square)
    if not piece:
        return False, "Aucune piece sur cette case."
    if _piece_color(piece) != turn:
        return False, "Ce n'est pas le tour de cette couleur."
    target = board.get(to_square)
    if target and _piece_color(target) == turn:
        return False, "Une piece alliee occupe deja cette case."

    dx = tx - fx
    dy = ty - fy
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    kind = piece[1]
    direction = 1 if turn == "white" else -1
    start_rank = 1 if turn == "white" else 6

    if kind == "P":
        if dx == 0 and dy == direction and not target:
            return True, ""
        if dx == 0 and dy == 2 * direction and fy == start_rank and not target and not board.get(_xy_square(fx, fy + direction)):
            return True, ""
        if abs_dx == 1 and dy == direction and target and _piece_color(target) != turn:
            return True, ""
        return False, "Deplacement de pion invalide."
    if kind == "N":
        return ((abs_dx, abs_dy) in {(1, 2), (2, 1)}, "Deplacement de cavalier invalide.")
    if kind == "B":
        return (abs_dx == abs_dy and _path_clear(board, from_square, to_square), "Diagonale bloquee ou invalide.")
    if kind == "R":
        return ((dx == 0 or dy == 0) and _path_clear(board, from_square, to_square), "Ligne bloquee ou invalide.")
    if kind == "Q":
        return (((dx == 0 or dy == 0) or abs_dx == abs_dy) and _path_clear(board, from_square, to_square), "Deplacement de dame invalide.")
    if kind == "K":
        return (max(abs_dx, abs_dy) == 1, "Deplacement de roi invalide.")
    return False, "Piece inconnue."


def _apply_chess_move(state: dict[str, Any], from_square: str, to_square: str, actor: str) -> dict[str, Any]:
    board = dict(state["board"])
    turn = state["turn"]
    legal, reason = _is_chess_move_legal(board, from_square, to_square, turn)
    if not legal:
        raise ValueError(reason)

    piece = board.pop(from_square)
    captured = board.get(to_square)
    if piece[1] == "P" and to_square[1] in {"1", "8"}:
        piece = piece[0] + "Q"
    board[to_square] = piece
    winner = "white" if captured == "bK" else "black" if captured == "wK" else None
    next_turn = "black" if turn == "white" else "white"
    move = {
        "from": from_square,
        "to": to_square,
        "piece": piece,
        "captured": captured,
        "actor": actor,
        "turn": turn,
    }
    moves = list(state.get("moves") or [])
    moves.append(move)
    state.update(
        {
            "board": board,
            "turn": next_turn,
            "moves": moves,
            "winner": winner,
            "message": "Partie terminee." if winner else ("Tour des noirs." if next_turn == "black" else "A vous de jouer."),
        }
    )
    return state


def _legal_chess_moves(board: dict[str, str], turn: str) -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    for from_square, piece in board.items():
        if _piece_color(piece) != turn:
            continue
        for x in range(8):
            for y in range(8):
                to_square = _xy_square(x, y)
                legal, _ = _is_chess_move_legal(board, from_square, to_square, turn)
                if legal:
                    moves.append((from_square, to_square))
    return moves


def _apply_ai_chess_reply(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("winner") or state.get("turn") != "black":
        return state
    board = dict(state["board"])
    moves = _legal_chess_moves(board, "black")
    if not moves:
        state["winner"] = "white"
        state["message"] = "Les noirs n'ont plus de coup disponible."
        return state
    captures = [move for move in moves if board.get(move[1])]
    from_square, to_square = (captures or moves)[0]
    return _apply_chess_move(state, from_square, to_square, "cognix-ai")


@router.get("/strategy")
async def my_strategy(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return build_strategy(current_subject)


@router.get("/permissions/me")
async def my_permissions(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    profile = auth_storage.get_user_profile(current_subject)
    is_admin = bool(profile and profile.get("role") == "admin")
    return {
        "username": current_subject,
        "developerMode": is_admin
        or cognix_db.user_has_permission(current_subject, cognix_db.DEVELOPER_MODE_PERMISSION),
        "admin": is_admin,
    }


@router.post("/approvals/developer-mode")
async def request_developer_mode(
    payload: ApprovalCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if auth_storage.is_admin(current_subject):
        return {
            "request": _row(
                {
                    "id": "admin-self-approved",
                    "username": current_subject,
                    "request_type": cognix_db.DEVELOPER_MODE_PERMISSION,
                    "reason": "Admin account",
                    "status": "approved",
                }
            )
        }
    if cognix_db.user_has_permission(current_subject, cognix_db.DEVELOPER_MODE_PERMISSION):
        return {
            "request": _row(
                {
                    "id": "already-approved",
                    "username": current_subject,
                    "request_type": cognix_db.DEVELOPER_MODE_PERMISSION,
                    "reason": "Developer mode permission already granted",
                    "status": "approved",
                }
            )
        }
    request = cognix_db.create_approval_request(
        current_subject,
        cognix_db.DEVELOPER_MODE_PERMISSION,
        payload.reason,
    )
    return {"request": _row(request)}


@router.get("/approvals/me")
async def my_approval_requests(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"requests": _rows(cognix_db.list_approval_requests(username = current_subject))}


@router.post("/reports")
async def create_report(
    payload: ReportCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    report = cognix_db.create_report(
        current_subject,
        payload.category,
        payload.title,
        payload.message,
    )
    return {"report": _row(report)}


@router.get("/reports/me")
async def my_reports(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"reports": _rows(cognix_db.list_reports(username = current_subject))}


@router.get("/context-memory")
async def get_my_context_memory(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"memory": _row(cognix_db.get_context_memory(current_subject))}


@router.put("/context-memory")
async def update_my_context_memory(
    payload: ContextMemoryRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    memory = cognix_db.update_context_memory(current_subject, payload.content, current_subject)
    return {"memory": _row(memory)}


@router.get("/library")
async def my_library(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"items": _rows(cognix_db.list_library_items(current_subject))}


@router.post("/library")
async def create_library_item(
    payload: LibraryItemRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    item = cognix_db.create_library_item(
        current_subject,
        kind = payload.kind,
        name = payload.name,
        source = payload.source,
        size_bytes = payload.size_bytes,
        uri = payload.uri,
        metadata = payload.metadata,
    )
    return {"item": _row(item)}


@router.get("/scheduled-tasks")
async def my_scheduled_tasks(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "tasks": _rows(cognix_db.list_scheduled_tasks(current_subject)),
        "runs": _rows(cognix_db.list_scheduled_task_runs(current_subject)),
    }


@router.post("/scheduled-tasks")
async def create_scheduled_task(
    payload: ScheduledTaskCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    task = cognix_db.create_scheduled_task(
        current_subject,
        payload.title,
        payload.prompt,
        payload.schedule_text,
    )
    return {"task": _row(task)}


@router.patch("/scheduled-tasks/{task_id}")
async def update_scheduled_task(
    task_id: str,
    payload: ScheduledTaskStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        task = cognix_db.update_scheduled_task_status(current_subject, task_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if task is None:
        raise HTTPException(status_code = 404, detail = "Scheduled task not found")
    return {"task": _row(task)}


@router.post("/scheduled-tasks/{task_id}/run")
async def run_scheduled_task(
    task_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    task = cognix_db.get_scheduled_task(current_subject, task_id)
    if not task:
        raise HTTPException(status_code = 404, detail = "Scheduled task not found")
    if task.get("status") not in {"active", "paused"}:
        raise HTTPException(status_code = 400, detail = "Scheduled task cannot run in this state")
    try:
        run = _execute_scheduled_task(current_subject, task)
    except Exception as exc:
        run = cognix_db.create_scheduled_task_run(
            current_subject,
            task_id,
            "error",
            str(exc),
            status = "failed",
        )
    return {"run": _row(run)}


@router.get("/apps")
async def my_apps(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {
        "catalog": APP_CATALOG,
        "connections": _rows(cognix_db.list_app_connections(current_subject)),
    }


@router.post("/apps/connections")
async def set_app_connection(
    payload: AppConnectionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        connection = cognix_db.set_app_connection(
            current_subject,
            payload.app_id,
            payload.app_name,
            payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    return {"connection": _row(connection)}


@router.get("/social/messages")
async def social_messages(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"messages": _rows(cognix_db.list_social_messages())}


@router.post("/social/messages")
async def create_social_message(
    payload: SocialMessageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    profile = auth_storage.get_user_profile(current_subject) or {}
    message = cognix_db.create_social_message(
        current_subject,
        profile.get("displayName") or current_subject,
        profile.get("role") or "user",
        payload.content,
    )
    return {"message": _row(message)}


@router.post("/social/agent-reply")
async def create_social_agent_reply(
    payload: SocialAgentRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    recent_messages = cognix_db.list_social_messages(limit = 12)
    visible = [
        f"{item.get('display_name') or item.get('username')}: {item.get('content')}"
        for item in recent_messages[-6:]
        if item.get("content")
    ]
    prompt = _strip_html(payload.prompt or "")
    if prompt:
        content = f"CogniX Orchestrateur: je prends en compte la demande '{prompt}'. "
    else:
        content = "CogniX Orchestrateur: je rejoins le salon. "
    if visible:
        content += "Derniers sujets detectes: " + "; ".join(visible[-3:])
    else:
        content += "Aucun sujet actif pour le moment."
    message = cognix_db.create_social_message(
        "cognix-orchestrateur",
        "CogniX Orchestrateur",
        "ai",
        content[:2000],
    )
    return {"message": _row(message)}


@router.get("/model-pins")
async def my_model_pins(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"pins": _rows(cognix_db.list_model_pins(current_subject))}


@router.post("/model-pins")
async def pin_model(
    payload: ModelPinRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    return {
        "pin": _row(
            cognix_db.set_model_pin(
                current_subject,
                payload.model_id,
                payload.label,
            )
        )
    }


@router.delete("/model-pins/{model_id}")
async def unpin_model(
    model_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    cognix_db.delete_model_pin(current_subject, model_id)
    return {"ok": True}


@router.get("/project-shares")
async def my_project_shares(
    project_id: str | None = None,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    shares = _rows(cognix_db.list_project_shares(current_subject, project_id))
    for share in shares:
        share["shareUrl"] = f"/share/project/{share.get('token')}"
    return {
        "shares": shares,
        "collaborators": _rows(cognix_db.list_project_collaborators(owner_username = current_subject)),
        "accepted": _rows(cognix_db.list_project_collaborators(collaborator_username = current_subject)),
    }


@router.get("/project-shares/public/{token}")
async def public_project_share(token: str) -> dict[str, Any]:
    share = cognix_db.get_project_share_by_token(token)
    if not share or share.get("revoked_at"):
        raise HTTPException(status_code = 404, detail = "Project share not found")
    return {
        "share": _row(
            {
                "id": share.get("id"),
                "project_id": share.get("project_id"),
                "owner_username": share.get("owner_username"),
                "permission": share.get("permission"),
                "created_at": share.get("created_at"),
                "revoked_at": share.get("revoked_at"),
            }
        )
    }


@router.post("/project-shares")
async def create_project_share(
    payload: ProjectShareCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        share = _row(
            cognix_db.create_project_share(
                current_subject,
                payload.project_id,
                payload.permission,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    share["shareUrl"] = f"/share/project/{share.get('token')}"
    return {"share": share}


@router.post("/project-shares/public/{token}/accept")
async def accept_public_project_share(
    token: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    collaborator = cognix_db.accept_project_share(token, current_subject)
    if not collaborator:
        raise HTTPException(status_code = 404, detail = "Project share not found")
    return {"collaborator": _row(collaborator)}


@router.delete("/project-shares/{share_id}")
async def revoke_project_share(
    share_id: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    share = cognix_db.revoke_project_share(current_subject, share_id)
    if share is None:
        raise HTTPException(status_code = 404, detail = "Share not found")
    return {"share": _row(share)}


def _thread_created_at_ms(thread: dict[str, Any]) -> int:
    value = thread.get("createdAt") or thread.get("created_at") or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@router.get("/news")
async def my_news(
    topic: str = "intelligence artificielle",
    refresh: bool = False,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    if refresh:
        for item in _fetch_feed_items(topic, limit = 12):
            cognix_db.create_news_item(
                current_subject,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
    items = cognix_db.list_news_items(current_subject, topic)
    if not items and not refresh:
        for item in _fetch_feed_items(topic, limit = 8):
            cognix_db.create_news_item(
                current_subject,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
        items = cognix_db.list_news_items(current_subject, topic)
    return {"items": _rows(items), "topic": topic}


@router.post("/news/refresh")
async def refresh_news(
    payload: NewsRefreshRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    topic = payload.topic.strip() or "intelligence artificielle"
    created = []
    for item in _fetch_feed_items(topic, limit = 12):
        created.append(
            cognix_db.create_news_item(
                current_subject,
                item["topic"],
                item["title"],
                item["summary"],
                item["url"],
                item["source"],
                item.get("published_at"),
            )
        )
    return {"items": _rows(cognix_db.list_news_items(current_subject, topic)), "created": len(created)}


@router.get("/research")
async def my_research(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"reports": _rows(cognix_db.list_research_reports(current_subject))}


@router.post("/research")
async def create_research(
    payload: ResearchRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    query = payload.query.strip()
    sources = _fetch_feed_items(query, limit = 6)
    report = cognix_db.create_research_report(
        current_subject,
        query,
        "Recherche approfondie: " + query[:90],
        _research_summary(query, sources),
        [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "source": item.get("source"),
                "publishedAt": item.get("published_at"),
            }
            for item in sources
        ],
    )
    cognix_db.create_library_item(
        current_subject,
        kind = "document",
        name = report.get("title") or ("Recherche " + query[:60]),
        source = "deep_research",
        metadata = {"researchReportId": report.get("id"), "query": query},
    )
    return {"report": _row(report)}


@router.get("/agent-runs")
async def my_agent_runs(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"runs": _rows(cognix_db.list_agent_runs(current_subject))}


@router.post("/agent-runs")
async def create_agent_run(
    payload: AgentRunRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    goal = payload.goal.strip()
    plan = _agent_plan(goal, payload.mode)
    result = (
        "Plan prepare. CogniX Orchestrateur peut maintenant suivre les etapes, "
        "demander les permissions necessaires et produire un compte rendu."
    )
    run = cognix_db.create_agent_run(current_subject, goal, payload.mode, plan, result)
    return {"run": _row(run)}


@router.get("/games")
async def my_games(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"games": _rows(cognix_db.list_game_sessions(current_subject))}


@router.post("/games")
async def create_game(
    payload: GameCreateRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    try:
        game = cognix_db.create_game_session(
            current_subject,
            payload.game_type,
            payload.opponent_type,
            payload.opponent_username,
            _game_initial_state(payload.game_type),
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    return {"game": _row(game)}


@router.post("/games/{game_id}/move")
async def play_game_move(
    game_id: str,
    payload: GameMoveRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    game = cognix_db.get_game_session(current_subject, game_id)
    if not game:
        raise HTTPException(status_code = 404, detail = "Game not found")
    if game.get("game_type") != "chess":
        raise HTTPException(status_code = 400, detail = "Only chess moves are supported for now")
    if game.get("status") not in {"active", "pending"}:
        raise HTTPException(status_code = 400, detail = "Game is not active")

    state = _normalize_chess_state(game.get("state"))
    try:
        state = _apply_chess_move(state, payload.from_square.lower(), payload.to_square.lower(), "user")
        if game.get("opponent_type") == "ai" and not state.get("winner"):
            state = _apply_ai_chess_reply(state)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc

    status_value = "complete" if state.get("winner") else "active"
    updated = cognix_db.update_game_session(
        current_subject,
        game_id,
        status = status_value,
        state = state,
    )
    return {"game": _row(updated or {})}


@router.get("/pulse")
async def my_pulse(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"reports": _rows(cognix_db.list_pulse_reports(current_subject))}


@router.post("/pulse/generate")
async def generate_pulse(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    threads = list_chat_threads(
        include_archived = True,
        owner_username = current_subject,
    )
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(hours = 24)).timestamp() * 1000)
    recent_threads = [
        thread
        for thread in threads
        if _thread_created_at_ms(thread) >= cutoff_ms
    ]
    source_threads = recent_threads[:12] if recent_threads else threads[:6]
    topics = [
        str(thread.get("title") or "Conversation").strip()[:80]
        for thread in source_threads
        if str(thread.get("title") or "").strip()
    ]
    if not topics:
        topics = ["Activite CogniX", "Suivi personnel", "Idees a reprendre"]
    summary = (
        "Pulse a rassemble les conversations recentes et prepare une base de recherche "
        "sur les sujets suivants: "
        + ", ".join(topics[:6])
        + "."
    )
    report = cognix_db.create_pulse_report(
        current_subject,
        "Pulse des dernieres 24h",
        summary,
        topics[:12],
        [str(thread.get("id")) for thread in source_threads if thread.get("id")],
    )
    return {"report": _row(report)}


@router.get("/images")
async def my_images(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    return {"images": _rows(cognix_db.list_image_history(current_subject))}


@router.post("/images")
async def create_image(
    payload: ImageRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    image = cognix_db.create_image_request(current_subject, payload.prompt, payload.model)
    cognix_db.create_library_item(
        current_subject,
        kind = "image",
        name = payload.prompt[:80] or "Image CogniX",
        source = "image_generation",
        metadata = {"imageRequestId": image.get("id"), "status": image.get("status")},
    )
    return {"image": _row(image)}


@router.get("/admin/dashboard")
async def admin_dashboard(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    users = auth_storage.list_user_profiles()
    threads = list_chat_threads(
        include_archived = True,
        owner_username = current_subject,
        include_all = True,
    )
    projects = list_chat_projects(
        include_archived = True,
        owner_username = current_subject,
        include_all = True,
    )
    messages = list_chat_messages_for_threads([thread["id"] for thread in threads])
    usage = cognix_db.summarize_compute_usage(threads, messages)
    approvals = cognix_db.list_approval_requests()
    bans = cognix_db.list_bans()
    threats = cognix_db.list_security_events(limit = 200)
    reports = cognix_db.list_reports()
    collaborators = cognix_db.list_project_collaborators()
    user_details = _build_dashboard_user_details(
        users = users,
        threads = threads,
        projects = projects,
        usage = usage,
        security_events = threats,
        bans = bans,
        reports = reports,
        collaborators = collaborators,
    )
    return {
        "summary": {
            "users": len(users),
            "conversations": len(threads),
            "projects": len(projects),
            "approvalsPending": sum(1 for item in approvals if item.get("status") == "pending"),
            "activeBans": sum(
                1
                for item in bans
                if item.get("status") in {"pending_admin_review", "active", "permanent"}
            ),
            "securityThreats": len(threats),
            "reportsOpen": sum(1 for item in reports if item.get("status") in {"open", "in_review"}),
        },
        "users": [dict(user, dashboard = user_details.get(str(user.get("username") or ""), {})) for user in users],
        "dashboardUsers": user_details,
        "threads": threads,
        "projects": projects,
        "projectCollaborators": _rows(collaborators),
        "computeUsage": usage,
        "approvals": _rows(approvals),
        "bans": _rows(bans),
        "securityThreats": _rows(threats),
        "reports": _rows(reports),
        "knownAttacks": [
            {
                "id": item["id"],
                "label": item["label"],
                "severity": item["severity"],
            }
            for item in cognix_db.KNOWN_ATTACK_SIGNATURES
        ],
    }


@router.get("/admin/approvals")
async def admin_approvals(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"requests": _rows(cognix_db.list_approval_requests())}


@router.patch("/admin/approvals/{request_id}")
async def admin_decide_approval(
    request_id: str,
    payload: ApprovalDecisionRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        request = cognix_db.set_approval_status(
            request_id,
            payload.status,
            decided_by = current_subject,
            admin_note = payload.admin_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if request is None:
        raise HTTPException(status_code = 404, detail = "Approval request not found")
    return {"request": _row(request)}


@router.get("/admin/bans")
async def admin_bans(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"bans": _rows(cognix_db.list_bans())}


@router.patch("/admin/bans/{ban_id}")
async def admin_update_ban(
    ban_id: str,
    payload: BanStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        ban = cognix_db.update_ban_status(
            ban_id,
            payload.status,
            decided_by = current_subject,
            admin_decision = payload.admin_decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if ban is None:
        raise HTTPException(status_code = 404, detail = "Ban not found")
    return {"ban": _row(ban)}


@router.get("/admin/security-threats")
async def admin_security_threats(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {
        "threats": _rows(cognix_db.list_security_events(limit = 500)),
        "knownAttacks": [
            {
                "id": item["id"],
                "label": item["label"],
                "severity": item["severity"],
            }
            for item in cognix_db.KNOWN_ATTACK_SIGNATURES
        ],
    }


@router.get("/admin/reports")
async def admin_reports(current_subject: str = Depends(get_current_jwt_subject)) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"reports": _rows(cognix_db.list_reports())}


@router.patch("/admin/reports/{report_id}")
async def admin_update_report(
    report_id: str,
    payload: ReportStatusRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    try:
        report = cognix_db.update_report_status(report_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc
    if report is None:
        raise HTTPException(status_code = 404, detail = "Report not found")
    return {"report": _row(report)}


@router.get("/admin/context-memory/{username}")
async def admin_get_context_memory(
    username: str,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    return {"memory": _row(cognix_db.get_context_memory(username))}


@router.put("/admin/context-memory/{username}")
async def admin_update_context_memory(
    username: str,
    payload: ContextMemoryRequest,
    current_subject: str = Depends(get_current_jwt_subject),
) -> dict[str, Any]:
    _require_admin(current_subject)
    memory = cognix_db.update_context_memory(username, payload.content, current_subject)
    return {"memory": _row(memory)}
