# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX strategy helpers."""

from __future__ import annotations

from typing import Any

from core.cognix import hardware as cognix_hardware
from core.cognix import recommender as cognix_recommender


def build_strategy(current_subject: str) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    model_recommendation = cognix_recommender.build_model_recommendation(hardware)

    return {
        "username": current_subject,
        "phase": "mvp_core_local",
        "roadmapPhase": "Phase 1 - Core local solide",
        "hardware": hardware,
        "providers": model_recommendation["providers"],
        "recommendation": model_recommendation["recommendation"],
        "nextSteps": [
            "brancher cette strategie au futur Model Router",
            "ajouter un Hardware Profiler visible",
            "journaliser les decisions de routage",
            "preparer le Model Cache Manager sans changer le chat actuel",
        ],
    }
