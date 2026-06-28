# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX dynamic UI profile planning.

Profiles are declarative hints for the existing design system. This module does
not mutate the frontend, navigation, theme, typography, or route tree.
"""

from __future__ import annotations

from typing import Any


COGNIX_DYNAMIC_UI_VERSION = "cognix_dynamic_ui_v1"
COGNIX_UI_LAYOUT_PROFILE_VERSION = "cognix_ui_layout_profile_v1"

PROJECT_UI_PROFILES: dict[str, dict[str, Any]] = {
    "code": {
        "label": "Code",
        "panels": ["files", "editor", "terminal", "tests"],
        "tools": ["repo-search", "run-tests", "diff-viewer"],
    },
    "maths": {
        "label": "Maths",
        "panels": ["latex-renderer", "formula-table", "scratchpad", "steps"],
        "tools": ["latex-preview", "symbol-table", "calculator"],
    },
    "physics": {
        "label": "Physique",
        "panels": ["latex-renderer", "units", "diagram-notes", "calculations"],
        "tools": ["unit-converter", "formula-table", "plot-preview"],
    },
    "business": {
        "label": "Business",
        "panels": ["dashboard", "documents", "tasks", "metrics"],
        "tools": ["table-view", "report-export", "task-list"],
    },
    "general": {
        "label": "General",
        "panels": ["chat", "notes", "documents"],
        "tools": ["search", "export"],
    },
}


def _profile_key(project_type: str | None) -> str:
    normalized = str(project_type or "general").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "math": "maths",
        "mathematiques": "maths",
        "physique": "physics",
        "biz": "business",
        "dev": "code",
        "coding": "code",
    }
    key = aliases.get(normalized, normalized)
    return key if key in PROJECT_UI_PROFILES else "general"


def _viewport(value: str | None) -> str:
    return "mobile" if str(value or "").lower() == "mobile" else "desktop"


def _theme(value: str | None) -> str:
    return "light" if str(value or "").lower() == "light" else "dark"


def build_dynamic_ui_blueprint() -> dict[str, Any]:
    return {
        "dynamicUiVersion": COGNIX_DYNAMIC_UI_VERSION,
        "layoutProfileVersion": COGNIX_UI_LAYOUT_PROFILE_VERSION,
        "mode": "declarative_layout_profiles",
        "services": ["UILayoutProfileManager", "ProjectLayoutRenderer", "AdaptivePanels"],
        "designContract": {
            "sameDesignSystem": True,
            "sameTypography": True,
            "sameNavigationLogic": True,
            "noVisualRupture": True,
            "themeAware": True,
            "mobileDesktopAware": True,
        },
        "availableProfiles": [
            {"projectType": key, "panels": value["panels"], "tools": value["tools"]}
            for key, value in PROJECT_UI_PROFILES.items()
        ],
        "sideEffects": {
            "profileWrite": False,
            "uiMutation": False,
            "routeMutation": False,
            "themeMutation": False,
            "toolExecution": False,
            "modelLoad": False,
            "generation": False,
        },
    }


def build_project_ui_profile(
    *,
    username: str,
    project_type: str | None = None,
    project_id: str | None = None,
    viewport: str | None = "desktop",
    theme: str | None = "dark",
) -> dict[str, Any]:
    key = _profile_key(project_type)
    profile = PROJECT_UI_PROFILES[key]
    viewport_mode = _viewport(viewport)
    theme_mode = _theme(theme)
    panels = list(profile["panels"])
    if viewport_mode == "mobile":
        panels = panels[:2] + ["overflow-menu"]
    return {
        "dynamicUiVersion": COGNIX_DYNAMIC_UI_VERSION,
        "layoutProfileVersion": COGNIX_UI_LAYOUT_PROFILE_VERSION,
        "mode": "layout_profile_plan",
        "username": username,
        "projectId": project_id,
        "projectType": key,
        "profileKey": key,
        "viewport": viewport_mode,
        "theme": theme_mode,
        "activePanels": panels,
        "availableTools": list(profile["tools"]),
        "suggestion": {
            "visible": False,
            "reason": "Dynamic UI remains subtle; no extra suggestion is shown by default.",
        },
        "layoutHints": {
            "density": "compact" if viewport_mode == "mobile" else "standard",
            "preserveSidebarBehavior": True,
            "preserveChatSurface": True,
            "useExistingTokensOnly": True,
        },
        "designContract": build_dynamic_ui_blueprint()["designContract"],
        "summary": {
            "panelCount": len(panels),
            "toolCount": len(profile["tools"]),
            "mobileOptimized": viewport_mode == "mobile",
            "darkModeCompatible": theme_mode == "dark",
        },
        "sideEffects": build_dynamic_ui_blueprint()["sideEffects"],
    }
