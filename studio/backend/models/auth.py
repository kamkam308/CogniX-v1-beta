# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Pydantic schemas for the Authentication API."""

from typing import Optional

from pydantic import BaseModel, Field


class AuthLoginRequest(BaseModel):
    """Login payload: username-or-email/password to obtain a JWT."""

    username: Optional[str] = Field(None, max_length = 254, description = "Username or email")
    identifier: Optional[str] = Field(None, max_length = 254, description = "Username or email")
    password: str = Field(..., max_length = 128, description = "Password")

    @property
    def login_identifier(self) -> str:
        return (self.identifier or self.username or "").strip()


class AuthRegisterRequest(BaseModel):
    """Create a local CogniX user."""

    username: str = Field(..., min_length = 3, max_length = 32, description = "Username")
    email: Optional[str] = Field(None, max_length = 254, description = "Email address")
    password: str = Field(..., min_length = 8, max_length = 128, description = "Password")
    display_name: Optional[str] = Field(None, max_length = 80, description = "Display name")


class UserProfileResponse(BaseModel):
    """Public user profile returned by auth endpoints."""

    id: int
    username: str
    email: Optional[str] = None
    displayName: str
    role: str
    plan: str
    mustChangePassword: bool = False
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    lastLoginAt: Optional[str] = None
    lastLoginIp: Optional[str] = None
    loginLocked: bool = False
    loginLockoutUntil: Optional[str] = None
    loginLockoutLevel: int = 0
    failedLoginCount: int = 0
    loginPermanentlyLocked: bool = False


class UserListResponse(BaseModel):
    """Admin-only user list."""

    users: list[UserProfileResponse]


class DesktopLoginRequest(BaseModel):
    """Desktop-only local secret exchange payload."""

    secret: str = Field(..., min_length = 1, max_length = 256, description = "Desktop local auth secret")


class RefreshTokenRequest(BaseModel):
    """Refresh token payload to obtain new access + refresh tokens."""

    refresh_token: Optional[str] = Field(
        None,
        min_length = 32,
        max_length = 256,
        description = "Refresh token from a previous login or refresh; browsers may use the HttpOnly cookie instead",
    )


class AuthStatusResponse(BaseModel):
    """Indicate whether the seeded admin auth flow is ready."""

    initialized: bool = Field(..., description = "True if the auth database contains a login user")
    default_username: str = Field(
        "unsloth",
        description = "Default admin username for first-boot UI prefill; empty once auth is initialized.",
    )
    requires_password_change: bool = Field(
        ...,
        description = "True if the seeded admin must still change the default password",
    )


class ChangePasswordRequest(BaseModel):
    """Change the current user's password, typically on first login."""

    current_password: str = Field(
        ..., min_length = 8, max_length = 128, description = "Existing password for the authenticated user"
    )
    new_password: str = Field(
        ..., min_length = 8, max_length = 128, description = "Replacement password (minimum 8 characters)"
    )


# ---------------------------------------------------------------------------
# API key schemas
# ---------------------------------------------------------------------------


class CreateApiKeyRequest(BaseModel):
    """Request body to create a new API key."""

    name: str = Field(..., min_length = 1, max_length = 80, description = "Human-readable label for this key")
    expires_in_days: Optional[int] = Field(
        None,
        ge = 1,
        le = 3650,
        description = "Number of days until the key expires (None = never)",
    )


class ApiKeyResponse(BaseModel):
    """Public representation of an API key (never contains the raw key)."""

    id: int
    name: str
    key_prefix: str = Field(..., description = "First 8 characters after sk-unsloth- for display")
    created_at: str
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    is_active: bool


class CreateApiKeyResponse(BaseModel):
    """Returned once when a key is created -- ``key`` is never shown again."""

    key: str = Field(..., description = "Full API key (shown once)")
    api_key: ApiKeyResponse


class ApiKeyListResponse(BaseModel):
    """List of API keys for the authenticated user."""

    api_keys: list[ApiKeyResponse]
