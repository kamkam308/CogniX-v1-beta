# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Pydantic models for authentication tokens."""

from pydantic import BaseModel, Field
from typing import Optional


class Token(BaseModel):
    """Authentication response model for session credentials."""

    access_token: str = Field(
        ..., description = "Session access credential used for authenticated API requests"
    )
    refresh_token: str = Field(
        ...,
        description = "Session refresh credential used to renew an expired access credential",
    )
    token_type: str = Field(
        ..., description = "Credential type for the Authorization header, always 'bearer'"
    )
    must_change_password: bool = Field(
        ..., description = "True when the user must change the seeded default password"
    )
    username: Optional[str] = Field(None, description = "Canonical username for the session")
    email: Optional[str] = Field(None, description = "Email address for the session user")
    display_name: Optional[str] = Field(None, description = "Display name for the session user")
    role: Optional[str] = Field(None, description = "Application role for the session user")
    plan: Optional[str] = Field(None, description = "Billing/access plan for the session user")
