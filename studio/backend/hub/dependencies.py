# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Shared FastAPI dependencies for Hub routes."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException

from auth import storage as auth_storage
from auth.authentication import get_current_jwt_subject

HUB_HF_TOKEN_HEADER = "X-Unsloth-HF-Token"
HUB_HF_TOKEN_MAX_LENGTH = 512


def get_hf_token(
    hf_token: Optional[str] = Header(
        None,
        alias = HUB_HF_TOKEN_HEADER,
        max_length = HUB_HF_TOKEN_MAX_LENGTH,
    ),
) -> Optional[str]:
    token = (hf_token or "").strip()
    return token or None


def require_admin_subject(current_subject: str = Depends(get_current_jwt_subject)) -> str:
    if not auth_storage.is_admin(current_subject):
        raise HTTPException(status_code = 403, detail = "Admin access required")
    return current_subject
