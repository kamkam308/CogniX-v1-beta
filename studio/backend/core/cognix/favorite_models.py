# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX native favorite models and quick switcher contracts."""

from __future__ import annotations

from typing import Any


COGNIX_FAVORITE_MODEL_SERVICE_VERSION = "cognix_favorite_model_service_v1"
COGNIX_MODEL_QUICK_SWITCHER_VERSION = "cognix_model_quick_switcher_v1"
COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION = "cognix_user_model_preference_service_v1"

FAVORITE_MODEL_SERVICES = [
    "FavoriteModelService",
    "ModelQuickSwitcher",
    "UserModelPreferenceService",
]

FAVORITE_MODEL_TABLES = [
    "favorite_models",
    "user_model_defaults",
    "project_model_defaults",
]


def _text(value: Any, limit: int = 240, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).replace("\r\n", "\n").strip()
    return " ".join(text.split())[:limit].strip()


def _key(value: Any, fallback: str = "local") -> str:
    text = _text(value, 180, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return cleaned.strip("-")[:160] or fallback


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalized_model(
    *,
    model_id: str,
    label: str | None = None,
    provider_type: str | None = None,
    provider_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    normalized_model_id = _text(model_id, 240)
    return {
        "modelId": normalized_model_id,
        "label": _text(label, 240) or normalized_model_id,
        "providerType": _key(provider_type, "local"),
        "providerId": _text(provider_id, 160) or None,
        "source": _key(source, "user"),
    }


def build_favorite_models_blueprint() -> dict[str, Any]:
    return {
        "favoriteModelServiceVersion": COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
        "modelQuickSwitcherVersion": COGNIX_MODEL_QUICK_SWITCHER_VERSION,
        "userModelPreferenceServiceVersion": COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION,
        "mode": "native_favorite_models_contract",
        "services": FAVORITE_MODEL_SERVICES,
        "tables": FAVORITE_MODEL_TABLES,
        "capabilities": [
            "pin_model",
            "unpin_model",
            "set_user_default_model",
            "set_project_default_model",
            "quick_switcher_snapshot",
            "project_model_binding",
        ],
        "uiContract": {
            "modelHubPinAction": True,
            "chatQuickSwitcher": True,
            "projectDefaultModel": True,
            "iconOnlyPinPreferred": True,
            "designSystemOnly": True,
        },
        "sideEffects": {
            "favoriteWrite": False,
            "favoriteDelete": False,
            "userDefaultWrite": False,
            "projectDefaultWrite": False,
            "quickSwitcherWrite": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
            "secretRead": False,
            "frontendDirectModelCall": False,
        },
    }


def build_favorite_model_plan(
    *,
    username: str,
    model_id: str,
    label: str | None = None,
    provider_type: str | None = None,
    provider_id: str | None = None,
    source: str | None = None,
    project_ids: list[Any] | None = None,
    quick_switcher: bool = True,
    sort_order: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = _normalized_model(
        model_id = model_id,
        label = label,
        provider_type = provider_type,
        provider_id = provider_id,
        source = source,
    )
    projects = [_text(item, 160) for item in _as_list(project_ids) if _text(item, 160)]
    return {
        "favoriteModelServiceVersion": COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
        "modelQuickSwitcherVersion": COGNIX_MODEL_QUICK_SWITCHER_VERSION,
        "mode": "native_favorite_model_plan",
        "service": "FavoriteModelService",
        "username": _text(username, 160),
        "valid": bool(model["modelId"]),
        "model": model,
        "favorite": {
            "quickSwitcher": _as_bool(quick_switcher, True),
            "sortOrder": int(sort_order) if isinstance(sort_order, int) else 0,
            "projectIds": projects,
            "status": "active",
        },
        "metadata": _as_dict(metadata),
        "sideEffects": build_favorite_models_blueprint()["sideEffects"],
    }


def build_user_default_model_plan(
    *,
    username: str,
    model_id: str,
    label: str | None = None,
    provider_type: str | None = None,
    provider_id: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = _normalized_model(
        model_id = model_id,
        label = label,
        provider_type = provider_type,
        provider_id = provider_id,
        source = source,
    )
    return {
        "favoriteModelServiceVersion": COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
        "userModelPreferenceServiceVersion": COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION,
        "mode": "native_user_default_model_plan",
        "service": "UserModelPreferenceService",
        "username": _text(username, 160),
        "valid": bool(model["modelId"]),
        "defaultModel": {
            **model,
            "scope": "user",
            "status": "active",
        },
        "metadata": _as_dict(metadata),
        "sideEffects": build_favorite_models_blueprint()["sideEffects"],
    }


def build_project_default_model_plan(
    *,
    username: str,
    project_id: str,
    model_id: str,
    label: str | None = None,
    provider_type: str | None = None,
    provider_id: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = _normalized_model(
        model_id = model_id,
        label = label,
        provider_type = provider_type,
        provider_id = provider_id,
        source = source,
    )
    return {
        "favoriteModelServiceVersion": COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
        "userModelPreferenceServiceVersion": COGNIX_USER_MODEL_PREFERENCE_SERVICE_VERSION,
        "mode": "native_project_default_model_plan",
        "service": "UserModelPreferenceService",
        "username": _text(username, 160),
        "projectId": _text(project_id, 160),
        "valid": bool(model["modelId"] and _text(project_id, 160)),
        "defaultModel": {
            **model,
            "scope": "project",
            "status": "active",
        },
        "metadata": _as_dict(metadata),
        "sideEffects": build_favorite_models_blueprint()["sideEffects"],
    }


def build_quick_switcher_snapshot(
    *,
    username: str,
    favorites: list[dict[str, Any]],
    user_default: dict[str, Any] | None = None,
    project_defaults: list[dict[str, Any]] | None = None,
    active_project_id: str | None = None,
) -> dict[str, Any]:
    active_project = _text(active_project_id, 160) or None
    favorite_items = []
    for row in favorites:
        payload = _as_dict(row.get("payload"))
        model = _as_dict(payload.get("model"))
        favorite = _as_dict(payload.get("favorite"))
        if not model.get("modelId"):
            model = {
                "modelId": row.get("model_id") or row.get("modelId") or row.get("scope_id") or row.get("scopeId"),
                "label": row.get("label") or row.get("model_id") or row.get("modelId") or row.get("scope_id"),
                "providerType": row.get("provider_type") or row.get("providerType") or "local",
                "providerId": row.get("provider_id") or row.get("providerId"),
            }
        favorite_items.append(
            {
                "model": model,
                "quickSwitcher": _as_bool(favorite.get("quickSwitcher"), True),
                "sortOrder": int(favorite.get("sortOrder") or row.get("sort_order") or 0),
                "projectIds": _as_list(favorite.get("projectIds")),
                "updatedAt": row.get("updated_at") or row.get("updatedAt") or row.get("created_at") or row.get("createdAt"),
            }
        )
    favorite_items.sort(key = lambda item: (item["sortOrder"], str(item["updatedAt"] or "")), reverse = True)
    quick_models = [item["model"] for item in favorite_items if item["quickSwitcher"]]
    user_default_model = _as_dict((_as_dict((user_default or {}).get("payload"))).get("defaultModel"))
    project_default_match = None
    for item in project_defaults or []:
        project_id = item.get("project_id") or item.get("projectId")
        if active_project and project_id == active_project:
            project_default_match = {
                "projectId": project_id,
                "modelId": item.get("model_id") or item.get("modelId"),
                "label": item.get("label") or item.get("model_id") or item.get("modelId"),
                "providerType": item.get("provider_type") or item.get("providerType") or "local",
                "providerId": item.get("provider_id") or item.get("providerId"),
                "scope": "project",
            }
            break
    selected_default = project_default_match or user_default_model or (quick_models[0] if quick_models else None)
    return {
        "favoriteModelServiceVersion": COGNIX_FAVORITE_MODEL_SERVICE_VERSION,
        "modelQuickSwitcherVersion": COGNIX_MODEL_QUICK_SWITCHER_VERSION,
        "mode": "native_model_quick_switcher_snapshot",
        "service": "ModelQuickSwitcher",
        "username": _text(username, 160),
        "activeProjectId": active_project,
        "favoriteModels": favorite_items,
        "quickSwitcherModels": quick_models,
        "userDefaultModel": user_default_model or None,
        "projectDefaultModel": project_default_match,
        "selectedDefaultModel": selected_default,
        "summary": {
            "favoriteCount": len(favorite_items),
            "quickSwitcherCount": len(quick_models),
            "hasUserDefault": bool(user_default_model),
            "hasProjectDefault": bool(project_default_match),
        },
        "sideEffects": build_favorite_models_blueprint()["sideEffects"],
    }
