# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX strategy helpers."""

from __future__ import annotations

from typing import Any

from core.cognix import hardware as cognix_hardware
from core.cognix import recommender as cognix_recommender
from storage import cognix_db


def build_strategy(current_subject: str) -> dict[str, Any]:
    hardware = cognix_hardware.get_hardware_profile()
    latest_benchmark = cognix_db.get_latest_benchmark_run(current_subject)
    model_recommendation = cognix_recommender.build_model_recommendation(
        hardware,
        latest_benchmark_run = latest_benchmark,
    )

    return {
        "username": current_subject,
        "phase": "mvp_core_local",
        "roadmapPhase": "Phase 1 - Core local solide",
        "hardware": hardware,
        "latestBenchmark": latest_benchmark,
        "providers": model_recommendation["providers"],
        "recommendation": model_recommendation["recommendation"],
        "nextSteps": [
            "utiliser le benchmark pour calibrer les recommandations",
            "brancher les modeles specialises au router",
            "preparer le prechargement selon projet et RAM",
            "connecter RAG et fine-tuning guide au decision engine",
        ],
    }
