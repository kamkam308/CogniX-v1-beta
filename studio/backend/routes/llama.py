# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""llama.cpp prebuilt update endpoints.

GET  /api/llama/update-status  -> is a newer prebuilt available + job state
POST /api/llama/update         -> download + atomically swap to the latest

Detection reuses utils.llama_cpp_freshness; the swap reuses
install_llama_prebuilt.py via utils.llama_cpp_update. Both fail open so the UI
never blocks on a missing marker / offline GitHub.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import storage as auth_storage
from auth.authentication import get_current_jwt_subject
from utils.llama_cpp_update import get_update_status, start_update

router = APIRouter()


def _require_admin(current_subject: str) -> None:
    if not auth_storage.is_admin(current_subject):
        raise HTTPException(status_code = 403, detail = "Admin access required")


class LlamaUpdateJob(BaseModel):
    state: str = Field("idle", description = "idle | running | success | error")
    message: str = ""
    from_tag: Optional[str] = None
    to_tag: Optional[str] = None
    reload_required: Optional[bool] = None
    error: Optional[str] = None
    progress: Optional[float] = Field(None, description = "0..1 while running, 1 on success.")
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class LlamaUpdateStatusResponse(BaseModel):
    supported: bool = Field(
        False,
        description = "True when the install came from an Unsloth prebuilt (has a marker).",
    )
    update_available: bool = Field(
        False, description = "True when the latest release is genuinely newer than the install."
    )
    stale: bool = Field(
        False, description = "Update available AND install older than the staleness threshold."
    )
    installed_tag: Optional[str] = None
    latest_tag: Optional[str] = None
    published_repo: Optional[str] = None
    installed_at_utc: Optional[str] = None
    age_days: Optional[int] = None
    source_build: bool = Field(
        False, description = "True when there is no marker (source build) but a prebuilt is offered."
    )
    update_size_bytes: Optional[int] = Field(
        None, description = "Download size of the prebuilt Update would fetch, in bytes."
    )
    job: LlamaUpdateJob = Field(default_factory = LlamaUpdateJob)


class LlamaUpdateActionResponse(BaseModel):
    started: bool
    reason: Optional[str] = None
    message: Optional[str] = None
    job: LlamaUpdateJob = Field(default_factory = LlamaUpdateJob)


@router.get("/update-status", response_model = LlamaUpdateStatusResponse)
async def llama_update_status(
    force_refresh: bool = Query(
        False, description = "Bypass the 24h release cache for an explicit check."
    ),
    current_subject: str = Depends(get_current_jwt_subject),
) -> LlamaUpdateStatusResponse:
    _require_admin(current_subject)
    # Off the event loop: detection may probe the host and read GitHub.
    status = await asyncio.to_thread(get_update_status, force_refresh = force_refresh)
    show_banner = os.environ.get("COGNIX_SHOW_LLAMA_UPDATE_BANNER", "").lower() in {
        "1",
        "true",
        "yes",
    }
    job_state = (status.get("job") or {}).get("state")
    if not force_refresh and not show_banner and job_state == "idle":
        status["update_available"] = False
        status["stale"] = False
        status["update_size_bytes"] = None
    return LlamaUpdateStatusResponse(**status)


@router.post("/update", response_model = LlamaUpdateActionResponse)
async def llama_update(
    current_subject: str = Depends(get_current_jwt_subject),
) -> LlamaUpdateActionResponse:
    _require_admin(current_subject)
    action = await asyncio.to_thread(start_update)
    return LlamaUpdateActionResponse(**action)
