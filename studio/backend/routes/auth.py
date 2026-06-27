# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

import base64
import ipaddress
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from models.auth import (
    ApiKeyListResponse,
    ApiKeyResponse,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthStatusResponse,
    ChangePasswordRequest,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    DesktopLoginRequest,
    RefreshTokenRequest,
    UserListResponse,
    UserProfileResponse,
)
from models.users import Token
from auth import storage, hashing
from auth.authentication import (
    create_access_token,
    create_refresh_token,
    get_current_subject,
    get_current_subject_allow_password_change,
    get_current_jwt_subject,
    get_current_jwt_subject_allow_password_change,
)

router = APIRouter()
_REFRESH_COOKIE_NAME = "cognix_refresh_token"
_REFRESH_COOKIE_PATH = "/api/auth"
_REFRESH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _token_response(
    *,
    username: str,
    access_token: str,
    refresh_token: str,
    must_change_password: bool,
) -> Token:
    profile = storage.get_user_profile(username) or {}
    return Token(
        access_token = access_token,
        refresh_token = refresh_token,
        token_type = "bearer",
        must_change_password = must_change_password,
        username = username,
        email = profile.get("email"),
        display_name = profile.get("displayName") or username,
        role = profile.get("role") or "user",
        plan = profile.get("plan") or storage.DEFAULT_USER_PLAN,
    )


def _request_is_https(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded_proto.lower().split(",", 1)[0].strip() == "https"


def _set_refresh_cookie(response: Response, request: Request, refresh_token: str) -> None:
    response.set_cookie(
        key = _REFRESH_COOKIE_NAME,
        value = refresh_token,
        max_age = _REFRESH_COOKIE_MAX_AGE_SECONDS,
        httponly = True,
        secure = _request_is_https(request),
        samesite = "lax",
        path = _REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key = _REFRESH_COOKIE_NAME,
        path = _REFRESH_COOKIE_PATH,
        httponly = True,
        samesite = "lax",
    )


# Per-(ip, username) bucket + per-IP aggregate. Account bucket stops one user's
# typos from blocking others; the aggregate stops username-rotation spray.
# Single-process only; multi-worker deployments need a shared store.
_LOGIN_BUCKETS: dict[tuple[str, str], deque] = {}
_LOGIN_IP_BUCKETS: dict[str, deque] = {}
_REGISTER_IP_BUCKETS: dict[str, deque] = {}
_LOGIN_BUCKETS_LOCK = threading.Lock()
_LOGIN_WINDOW_SECONDS = 60.0
_LOGIN_MAX_FAILS = 10
_LOGIN_IP_MAX_FAILS = 30
_LOGIN_LOCKOUT_SECONDS = 60
_REGISTER_WINDOW_SECONDS = 300.0
_REGISTER_IP_MAX_ATTEMPTS = 10
# Bucket-dict cap. On overflow, prune stale entries; if still full the failure
# folds into the per-IP aggregate only.
_LOGIN_MAX_BUCKETS = 4096
# Unrepresentable as a real username (leading NUL); folds unknown-user attempts
# into one slot so attacker cardinality can't blow the bucket dict.
_UNKNOWN_LOGIN_USER = "\x00unknown-user"
_INCORRECT_PASSWORD_DETAIL = "Incorrect password. To reset it, contact your administrator."
_ADMIN_INCORRECT_PASSWORD_DETAIL = _INCORRECT_PASSWORD_DETAIL
_ACCOUNT_LOCKED_DETAIL = "Contact your administrator to unlock your account."
_COMMON_PASSWORDS = {
    "12345678",
    "123456789",
    "password",
    "password1",
    "password123",
    "qwerty123",
    "admin123",
    "admin1234",
    "letmein123",
}


def _trust_forwarded_for() -> bool:
    """Honour X-Forwarded-For only when UNSLOTH_STUDIO_TRUST_FORWARDED is set.

    Off by default so a direct caller can't spoof the header.
    """
    return os.environ.get("UNSLOTH_STUDIO_TRUST_FORWARDED", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _normalize_forwarded_addr(value: str) -> str:
    """Parse an XFF / Forwarded `for=` value into a bare IP (port-stripped)."""
    value = (value or "").strip().strip('"')
    if not value or value.lower() == "unknown":
        return ""
    if value.startswith("["):
        # Bracketed IPv6, optionally with port.
        end = value.find("]")
        if end <= 0:
            return ""
        host = value[1:end]
    elif value.count(":") == 1:
        # IPv4:port. Bare IPv6 has multiple colons → else branch.
        head, _, tail = value.rpartition(":")
        host = head if tail.isdigit() and head else value
    else:
        host = value
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return ""


def _forwarded_for_from_element(element: str) -> str:
    """Pick the `for=` token out of a single ``Forwarded`` element."""
    for tok in element.split(";"):
        key, sep, val = tok.strip().partition("=")
        if sep and key.lower() == "for":
            return _normalize_forwarded_addr(val)
    return ""


def _client_ip(request: Request | None) -> str:
    if request is None:
        return "_unknown"
    if _trust_forwarded_for():
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            # First entry is the originating client.
            normalized = _normalize_forwarded_addr(xff.split(",", 1)[0])
            if normalized:
                return normalized
        fwd = request.headers.get("forwarded", "")
        if fwd:
            # First element only; multi-element headers can't fork buckets.
            normalized = _forwarded_for_from_element(fwd.split(",", 1)[0])
            if normalized:
                return normalized
    return (request.client.host if request.client else None) or "_unknown"


def _bucket_key(request: Request | None, username: str) -> tuple[str, str]:
    return (_client_ip(request), (username or "").casefold())


def _unknown_user_key(request: Request | None) -> tuple[str, str]:
    return (_client_ip(request), _UNKNOWN_LOGIN_USER)


def _prune_bucket(bucket: deque, now: float) -> None:
    while bucket and now - bucket[0] > _LOGIN_WINDOW_SECONDS:
        bucket.popleft()


def _prune_bucket_window(bucket: deque, now: float, window_seconds: float) -> None:
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()


def _prune_stale_buckets(now: float) -> None:
    """Drop empty / expired account buckets to bound memory under spray."""
    stale: list[tuple[str, str]] = []
    for key, bucket in _LOGIN_BUCKETS.items():
        _prune_bucket(bucket, now)
        if not bucket:
            stale.append(key)
    for key in stale:
        _LOGIN_BUCKETS.pop(key, None)


def _record_login_failure(key: tuple[str, str]) -> int:
    now = time.monotonic()
    ip, _username = key
    with _LOGIN_BUCKETS_LOCK:
        ip_bucket = _LOGIN_IP_BUCKETS.setdefault(ip, deque())
        _prune_bucket(ip_bucket, now)
        ip_bucket.append(now)

        if key not in _LOGIN_BUCKETS and len(_LOGIN_BUCKETS) >= _LOGIN_MAX_BUCKETS:
            _prune_stale_buckets(now)
        if key in _LOGIN_BUCKETS or len(_LOGIN_BUCKETS) < _LOGIN_MAX_BUCKETS:
            account_bucket = _LOGIN_BUCKETS.setdefault(key, deque())
            _prune_bucket(account_bucket, now)
            account_bucket.append(now)
            return len(account_bucket)
        # Bucket dict at cap; per-IP cap still applies via ip_bucket.
        return len(ip_bucket)


def _blocked_for(bucket: deque | None, now: float, max_fails: int) -> int:
    if not bucket:
        return 0
    _prune_bucket(bucket, now)
    if len(bucket) >= max_fails:
        return max(1, int(_LOGIN_WINDOW_SECONDS - (now - bucket[0])))
    return 0


def _login_blocked(key: tuple[str, str]) -> int:
    """Return seconds until the next attempt is allowed, or 0."""
    now = time.monotonic()
    ip, _username = key
    with _LOGIN_BUCKETS_LOCK:
        return max(
            _blocked_for(_LOGIN_BUCKETS.get(key), now, _LOGIN_MAX_FAILS),
            _blocked_for(_LOGIN_IP_BUCKETS.get(ip), now, _LOGIN_IP_MAX_FAILS),
        )


def _login_ip_blocked(ip: str) -> int:
    now = time.monotonic()
    with _LOGIN_BUCKETS_LOCK:
        return _blocked_for(_LOGIN_IP_BUCKETS.get(ip), now, _LOGIN_IP_MAX_FAILS)


def _clear_login_bucket(key: tuple[str, str]) -> None:
    ip, _username = key
    with _LOGIN_BUCKETS_LOCK:
        _LOGIN_BUCKETS.pop(key, None)
        _LOGIN_IP_BUCKETS.pop(ip, None)


def _clear_account_bucket(key: tuple[str, str]) -> None:
    with _LOGIN_BUCKETS_LOCK:
        _LOGIN_BUCKETS.pop(key, None)


def _raise_timed_lockout(retry_after: int) -> None:
    retry_after = max(1, int(retry_after))
    minutes = max(1, (retry_after + 59) // 60)
    raise HTTPException(
        status_code = status.HTTP_429_TOO_MANY_REQUESTS,
        detail = f"Too many incorrect password attempts. Try again in {minutes} minutes.",
        headers = {"Retry-After": str(retry_after)},
    )


def _raise_account_locked() -> None:
    raise HTTPException(
        status_code = status.HTTP_423_LOCKED,
        detail = _ACCOUNT_LOCKED_DETAIL,
    )


def _enforce_non_admin_lockout(username: str) -> None:
    state = storage.get_login_lockout_state(username)
    if not state:
        return
    if state["loginPermanentlyLocked"]:
        _raise_account_locked()
    if state["retryAfterSeconds"] > 0:
        _raise_timed_lockout(state["retryAfterSeconds"])


def _validate_password_strength(
    password: str,
    *,
    username: str | None = None,
    email: str | None = None,
) -> None:
    """Reject common or user-derived passwords while keeping local setup friendly."""
    value = password or ""
    lowered = value.casefold()
    problems: list[str] = []
    if len(value) < 8:
        problems.append("at least 8 characters")

    families = 0
    families += bool(any(ch.islower() for ch in value))
    families += bool(any(ch.isupper() for ch in value))
    families += bool(any(ch.isdigit() for ch in value))
    families += bool(any(not ch.isalnum() for ch in value))
    if families < 2:
        problems.append("at least two character types")

    if lowered in _COMMON_PASSWORDS:
        problems.append("not a common password")

    identifiers = []
    if username:
        identifiers.append(username)
    if email:
        local_part = email.split("@", 1)[0]
        identifiers.extend([email, local_part])
    for identifier in identifiers:
        normalized = (identifier or "").strip().casefold()
        if len(normalized) >= 3 and normalized in lowered:
            problems.append("not based on your username or email")
            break

    if problems:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = "Password must be " + ", ".join(problems) + ".",
        )


def _register_blocked(request: Request | None) -> int:
    ip = _client_ip(request)
    now = time.monotonic()
    with _LOGIN_BUCKETS_LOCK:
        bucket = _REGISTER_IP_BUCKETS.get(ip)
        if not bucket:
            return 0
        _prune_bucket_window(bucket, now, _REGISTER_WINDOW_SECONDS)
        if len(bucket) >= _REGISTER_IP_MAX_ATTEMPTS:
            return max(1, int(_REGISTER_WINDOW_SECONDS - (now - bucket[0])))
        return 0


def _record_register_attempt(request: Request | None) -> int:
    ip = _client_ip(request)
    now = time.monotonic()
    with _LOGIN_BUCKETS_LOCK:
        bucket = _REGISTER_IP_BUCKETS.setdefault(ip, deque())
        _prune_bucket_window(bucket, now, _REGISTER_WINDOW_SECONDS)
        bucket.append(now)
        return len(bucket)


# Sync def (not async): compute_identity_proof touches SQLite on the first call,
# so FastAPI runs it in the threadpool rather than blocking the event loop.
@router.get("/identity")
def identity(nonce: str, request: Request) -> dict:
    """Challenge-response proof this is the real local Studio: caller sends a nonce,
    gets HMAC(install identity secret, nonce, connection address + port).
    Unauthenticated and side-effect free; a process that can't read the same-user
    secret can't forge a proof, and binding to the address/port the connection
    landed on stops a squatter relaying a proof from the real Studio elsewhere."""
    try:
        raw = base64.urlsafe_b64decode(nonce)
    except Exception:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST, detail = "nonce must be base64url"
        )
    if not 16 <= len(raw) <= 128:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST, detail = "nonce must decode to 16-128 bytes"
        )
    # The address + port the connection actually landed on, from the socket
    # (request.scope is getsockname, so it is the real local address even when
    # bound to 0.0.0.0), never the client-controlled Host header.
    server = request.scope.get("server") or ("", 0)
    host = server[0] or ""
    port = server[1] if server[1] is not None else 0
    return {"proof": storage.compute_identity_proof(raw, host, port)}


@router.get("/status", response_model = AuthStatusResponse)
async def auth_status() -> AuthStatusResponse:
    """Auth initialization state; ``default_username`` is exposed for first-boot UI prefill only."""
    initialized = storage.is_initialized()
    return AuthStatusResponse(
        initialized = initialized,
        default_username = "" if initialized else storage.DEFAULT_ADMIN_USERNAME,
        requires_password_change = storage.requires_password_change(storage.DEFAULT_ADMIN_USERNAME)
        if initialized
        else True,
    )


@router.post("/login", response_model = Token)
async def login(payload: AuthLoginRequest, request: Request, response: Response) -> Token:
    """Login with username-or-email/password. Per-account + per-IP rate-limited."""
    identifier = payload.login_identifier
    if not identifier:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = "Username or email is required",
        )
    unknown_key = _unknown_user_key(request)
    blocked_for = _login_blocked(unknown_key)
    if blocked_for > 0:
        raise HTTPException(
            status_code = status.HTTP_429_TOO_MANY_REQUESTS,
            # IP not interpolated into the body; behind a proxy/NAT it's
            # misleading or an info leak.
            detail = (f"Too many failed login attempts. " f"Try again in {blocked_for} seconds."),
            headers = {"Retry-After": str(blocked_for)},
        )

    record = storage.get_user_login_record(identifier)
    if record is None:
        # Record under one sentinel key per IP so attacker-controlled username
        # cardinality can't allocate unbounded buckets.
        _record_login_failure(unknown_key)
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = _INCORRECT_PASSWORD_DETAIL,
        )

    username = record["username"]
    key = _bucket_key(request, username)
    ip_blocked_for = _login_ip_blocked(key[0])
    if ip_blocked_for > 0:
        raise HTTPException(
            status_code = status.HTTP_429_TOO_MANY_REQUESTS,
            detail = f"Too many failed login attempts. Try again in {ip_blocked_for} seconds.",
            headers = {"Retry-After": str(ip_blocked_for)},
        )
    is_admin_user = (record.get("role") or "user") == "admin"
    if is_admin_user:
        blocked_for = _login_blocked(key)
        if blocked_for > 0:
            raise HTTPException(
                status_code = status.HTTP_429_TOO_MANY_REQUESTS,
                detail = f"Too many failed login attempts. Try again in {blocked_for} seconds.",
                headers = {"Retry-After": str(blocked_for)},
            )
    else:
        _enforce_non_admin_lockout(username)

    salt = record["password_salt"]
    pwd_hash = record["password_hash"]
    must_change_password = bool(record["must_change_password"])
    if not hashing.verify_password(payload.password, salt, pwd_hash):
        _record_login_failure(key)
        if not is_admin_user:
            state = storage.record_failed_login(username)
            if state and state["loginPermanentlyLocked"]:
                _raise_account_locked()
            if state and state["retryAfterSeconds"] > 0:
                _raise_timed_lockout(state["retryAfterSeconds"])
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = _ADMIN_INCORRECT_PASSWORD_DETAIL if is_admin_user else _INCORRECT_PASSWORD_DETAIL,
        )

    if hashing.needs_rehash(pwd_hash):
        storage.rehash_password(username, payload.password)
    storage.clear_login_failures(username)
    storage.record_login_success(username, _client_ip(request))
    _clear_login_bucket(key)
    _clear_login_bucket(unknown_key)
    access_token = create_access_token(subject = username)
    refresh_token = create_refresh_token(subject = username)
    _set_refresh_cookie(response, request, refresh_token)
    return _token_response(
        username = username,
        access_token = access_token,
        refresh_token = refresh_token,
        must_change_password = must_change_password,
    )


@router.post("/register", response_model = Token)
async def register(payload: AuthRegisterRequest, request: Request, response: Response) -> Token:
    """Create a normal local CogniX account and start a session."""
    blocked_for = _register_blocked(request)
    if blocked_for > 0:
        raise HTTPException(
            status_code = status.HTTP_429_TOO_MANY_REQUESTS,
            detail = f"Too many account creation attempts. Try again in {blocked_for} seconds.",
            headers = {"Retry-After": str(blocked_for)},
        )
    _record_register_attempt(request)
    _validate_password_strength(
        payload.password,
        username = payload.username,
        email = payload.email,
    )

    try:
        profile = storage.create_user(
            username = payload.username,
            email = payload.email,
            password = payload.password,
            display_name = payload.display_name,
            role = "user",
            plan = storage.DEFAULT_USER_PLAN,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = str(exc),
        ) from exc

    username = profile["username"]
    storage.record_login_success(username, _client_ip(request))
    _clear_login_bucket(_bucket_key(request, username))
    access_token = create_access_token(subject = username)
    refresh_token = create_refresh_token(subject = username)
    _set_refresh_cookie(response, request, refresh_token)
    return _token_response(
        username = username,
        access_token = access_token,
        refresh_token = refresh_token,
        must_change_password = False,
    )


@router.get("/me", response_model = UserProfileResponse)
async def me(current_subject: str = Depends(get_current_jwt_subject)) -> UserProfileResponse:
    profile = storage.get_user_profile(current_subject)
    if profile is None:
        raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED, detail = "Invalid session")
    return UserProfileResponse(**profile)


@router.get("/admin/users", response_model = UserListResponse)
async def admin_users(current_subject: str = Depends(get_current_jwt_subject)) -> UserListResponse:
    if not storage.is_admin(current_subject):
        raise HTTPException(status_code = status.HTTP_403_FORBIDDEN, detail = "Admin access required")
    return UserListResponse(
        users = [UserProfileResponse(**profile) for profile in storage.list_user_profiles()]
    )


@router.post("/admin/users/{username}/unlock", response_model = UserProfileResponse)
async def admin_unlock_user(
    username: str, current_subject: str = Depends(get_current_jwt_subject)
) -> UserProfileResponse:
    if not storage.is_admin(current_subject):
        raise HTTPException(status_code = status.HTTP_403_FORBIDDEN, detail = "Admin access required")
    profile = storage.unlock_user_login(username)
    if profile is None:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "User not found")
    return UserProfileResponse(**profile)


@router.post("/logout", status_code = status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, current_subject: str = Depends(get_current_jwt_subject_allow_password_change)
) -> Response:
    """Revoke refresh tokens for the subject; the access token is stateless and expires on its own."""
    try:
        storage.revoke_user_refresh_tokens(current_subject)
    except Exception:
        pass
    try:
        request.app.state.bootstrap_password = None
    except AttributeError:
        pass
    response = Response(status_code = status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.post("/desktop-login", response_model = Token)
async def desktop_login(payload: DesktopLoginRequest, request: Request, response: Response) -> Token:
    """Exchange a local desktop secret for normal admin-subject tokens."""
    username = storage.validate_desktop_secret(payload.secret)
    if username is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Desktop authentication failed",
        )

    refresh_token = create_refresh_token(subject = username, desktop = True)
    _set_refresh_cookie(response, request, refresh_token)
    return _token_response(
        username = username,
        access_token = create_access_token(subject = username, desktop = True),
        refresh_token = refresh_token,
        must_change_password = False,
    )


@router.post("/refresh", response_model = Token)
async def refresh(payload: RefreshTokenRequest, request: Request, response: Response) -> Token:
    """Exchange a refresh token for a new access+refresh pair (single-use)."""
    refresh_token = payload.refresh_token or request.cookies.get(_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Invalid or expired refresh token",
        )
    consumed = storage.consume_refresh_token(refresh_token)
    if consumed is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Invalid or expired refresh token",
        )
    username, is_desktop = consumed
    new_access_token = create_access_token(subject = username, desktop = is_desktop)
    new_refresh_token = create_refresh_token(subject = username, desktop = is_desktop)
    _set_refresh_cookie(response, request, new_refresh_token)

    return _token_response(
        username = username,
        access_token = new_access_token,
        refresh_token = new_refresh_token,
        must_change_password = False if is_desktop else storage.requires_password_change(username),
    )


@router.post("/change-password", response_model = Token)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_subject: str = Depends(get_current_jwt_subject_allow_password_change),
) -> Token:
    """Allow the authenticated user to replace the default password."""
    record = storage.get_user_and_secret(current_subject)
    if record is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "User session is invalid",
        )

    salt, pwd_hash, _jwt_secret, _must_change_password = record
    change_key = _bucket_key(request, f"change-password:{current_subject}")
    blocked_for = _login_blocked(change_key)
    if blocked_for > 0:
        raise HTTPException(
            status_code = status.HTTP_429_TOO_MANY_REQUESTS,
            detail = f"Too many failed password change attempts. Try again in {blocked_for} seconds.",
            headers = {"Retry-After": str(blocked_for)},
        )
    if not hashing.verify_password(payload.current_password, salt, pwd_hash):
        _record_login_failure(change_key)
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Current password is incorrect",
        )
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = "New password must be different from the current password",
        )
    profile = storage.get_user_profile(current_subject) or {}
    _validate_password_strength(
        payload.new_password,
        username = current_subject,
        email = profile.get("email"),
    )

    storage.update_password(current_subject, payload.new_password)
    storage.revoke_user_refresh_tokens(current_subject)
    _clear_account_bucket(change_key)
    try:
        request.app.state.bootstrap_password = None
    except AttributeError:
        pass
    access_token = create_access_token(subject = current_subject)
    refresh_token = create_refresh_token(subject = current_subject)
    _set_refresh_cookie(response, request, refresh_token)
    return _token_response(
        username = current_subject,
        access_token = access_token,
        refresh_token = refresh_token,
        must_change_password = False,
    )


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


def _row_to_api_key_response(row: dict) -> ApiKeyResponse:
    return ApiKeyResponse(
        id = row["id"],
        name = row["name"],
        key_prefix = row["key_prefix"],
        created_at = row["created_at"],
        last_used_at = row.get("last_used_at"),
        expires_at = row.get("expires_at"),
        is_active = bool(row["is_active"]),
    )


@router.post("/api-keys", response_model = CreateApiKeyResponse)
async def create_api_key(
    payload: CreateApiKeyRequest, current_subject: str = Depends(get_current_jwt_subject)
) -> CreateApiKeyResponse:
    """Create a new API key. The raw key is returned once and cannot be retrieved later."""
    expires_at = None
    if payload.expires_in_days is not None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days = payload.expires_in_days)
        ).isoformat()

    raw_key, row = storage.create_api_key(
        username = current_subject,
        name = payload.name,
        expires_at = expires_at,
    )
    return CreateApiKeyResponse(
        key = raw_key,
        api_key = _row_to_api_key_response(row),
    )


@router.get("/api-keys", response_model = ApiKeyListResponse)
async def list_api_keys(current_subject: str = Depends(get_current_jwt_subject)) -> ApiKeyListResponse:
    """List all API keys for the authenticated user (raw keys are never exposed)."""
    rows = storage.list_api_keys(current_subject)
    return ApiKeyListResponse(
        api_keys = [_row_to_api_key_response(r) for r in rows],
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: int, current_subject: str = Depends(get_current_jwt_subject)) -> dict:
    """Revoke (soft-delete) an API key."""
    if not storage.revoke_api_key(current_subject, key_id):
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = "API key not found",
        )
    return {"detail": "API key revoked"}
