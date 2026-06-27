# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""SQLite storage for auth data (user credentials + JWT secret)."""

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from utils.paths import auth_db_path, ensure_dir

DB_PATH = auth_db_path()
DEFAULT_ADMIN_USERNAME = "kamil"
LEGACY_ADMIN_USERNAME = "unsloth"
ADMIN_USERNAMES = frozenset({DEFAULT_ADMIN_USERNAME, LEGACY_ADMIN_USERNAME, "kamil_ebk"})
ADMIN_LOGIN_ALIASES = frozenset({"kamil", "kamil_ebk", "ceo"})
DEFAULT_USER_PLAN = "free"
CEO_PLAN = "CEO"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{2,31}$")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
DISPLAY_NAME_MAX_LENGTH = 80
EMAIL_MAX_LENGTH = 254
LOGIN_FAILURES_BEFORE_LOCK = 10
LOGIN_LOCKOUT_FIRST = timedelta(hours = 1)
LOGIN_LOCKOUT_SECOND = timedelta(hours = 2)

# Plaintext bootstrap password file beside auth.db, deleted on first password
# change so the credential never lingers on disk.
_BOOTSTRAP_PW_PATH = DB_PATH.parent / ".bootstrap_password"

# In-process cache to avoid re-reading the file on every HTML serve.
_bootstrap_password: Optional[str] = None


def generate_bootstrap_password() -> str:
    """Generate a 4-word diceware passphrase and persist it to disk.

    Persisted (the DB stores only the hash) so it survives restarts; later
    calls return the persisted value.
    """
    global _bootstrap_password

    # Cached in this process?
    if _bootstrap_password is not None:
        return _bootstrap_password

    # Persisted from a previous run?
    if _BOOTSTRAP_PW_PATH.is_file():
        _bootstrap_password = _BOOTSTRAP_PW_PATH.read_text().strip()
        if _bootstrap_password:
            return _bootstrap_password

    # First startup: generate a fresh passphrase.
    import diceware

    _bootstrap_password = diceware.get_passphrase(
        options = diceware.handle_options(args = ["-n", "4", "-d", "", "-c"])
    )

    # Persist so the same passphrase survives restarts until password change.
    ensure_dir(_BOOTSTRAP_PW_PATH.parent)
    _BOOTSTRAP_PW_PATH.write_text(_bootstrap_password)
    try:
        os.chmod(_BOOTSTRAP_PW_PATH, 0o600)
    except OSError:
        pass

    return _bootstrap_password


def get_bootstrap_password() -> Optional[str]:
    """Return the cached bootstrap password, or None if not yet generated."""
    return _bootstrap_password


def _load_bootstrap_password() -> Optional[str]:
    """Load an existing bootstrap password without creating one."""
    global _bootstrap_password
    _bootstrap_password = None
    if _BOOTSTRAP_PW_PATH.is_file():
        bootstrap_password = _BOOTSTRAP_PW_PATH.read_text().strip()
        if bootstrap_password:
            _bootstrap_password = bootstrap_password
    return _bootstrap_password


def clear_bootstrap_password() -> None:
    """Delete the persisted bootstrap password file (called after password change)."""
    global _bootstrap_password
    _bootstrap_password = None
    if _BOOTSTRAP_PW_PATH.is_file():
        _BOOTSTRAP_PW_PATH.unlink(missing_ok = True)


def _hash_token(token: str) -> str:
    """SHA-256 hash helper for refresh token storage.

    Plain SHA-256 is intentional: refresh tokens are 384-bit random strings, so
    a slow KDF adds no security while costing per-refresh latency. API keys use
    the separate ``_pbkdf2_api_key`` helper, only to satisfy CodeQL's
    ``py/weak-sensitive-data-hashing`` query, not for crypto reasons.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_connection() -> sqlite3.Connection:
    """Get a connection to the auth database, creating tables if needed."""
    ensure_dir(DB_PATH.parent)
    conn = sqlite3.connect(DB_PATH)
    # Keep the auth dir + DB private (they hold the JWT/identity secrets and
    # password hashes); sqlite3.connect would otherwise create the DB 0644 under
    # a 022 umask, letting another OS user read the identity secret and forge proofs.
    for _path, _mode in ((DB_PATH.parent, 0o700), (DB_PATH, 0o600)):
        try:
            os.chmod(_path, _mode)
        except OSError:
            pass
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_user (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            jwt_secret TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY,
            token_hash TEXT NOT NULL,
            username TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_desktop INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            key_hash   TEXT NOT NULL UNIQUE,
            name       TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            expires_at TEXT,
            is_active  INTEGER NOT NULL DEFAULT 1,
            is_internal INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    api_key_columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)")}
    if "is_internal" not in api_key_columns:
        conn.execute("ALTER TABLE api_keys ADD COLUMN is_internal INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_secrets (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(auth_user)")}
    if "must_change_password" not in columns:
        conn.execute(
            "ALTER TABLE auth_user ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
        )
    if "email" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN email TEXT")
    if "display_name" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN display_name TEXT")
    if "role" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "plan" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN created_at TEXT")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN updated_at TEXT")
    if "failed_login_count" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0")
    if "login_lockout_until" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN login_lockout_until TEXT")
    if "login_lockout_level" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN login_lockout_level INTEGER NOT NULL DEFAULT 0")
    if "login_permanently_locked" not in columns:
        conn.execute(
            "ALTER TABLE auth_user ADD COLUMN login_permanently_locked INTEGER NOT NULL DEFAULT 0"
        )
    if "last_login_at" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN last_login_at TEXT")
    if "last_login_ip" not in columns:
        conn.execute("ALTER TABLE auth_user ADD COLUMN last_login_ip TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_email ON auth_user(email) WHERE email IS NOT NULL AND email != ''"
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE auth_user
        SET
            display_name = COALESCE(NULLIF(display_name, ''), CASE WHEN username IN ('unsloth', 'kamil', 'kamil_ebk') THEN 'Kamil' ELSE username END),
            role = CASE WHEN username IN ('unsloth', 'kamil', 'kamil_ebk') THEN 'admin' ELSE COALESCE(NULLIF(role, ''), 'user') END,
            plan = CASE WHEN username IN ('unsloth', 'kamil', 'kamil_ebk') THEN 'CEO' ELSE COALESCE(NULLIF(plan, ''), 'free') END,
            created_at = COALESCE(created_at, ?),
            updated_at = COALESCE(updated_at, ?)
        WHERE display_name IS NULL
           OR display_name = ''
           OR role IS NULL
           OR role = ''
           OR plan IS NULL
           OR plan = ''
           OR created_at IS NULL
           OR updated_at IS NULL
           OR username IN ('unsloth', 'kamil', 'kamil_ebk')
        """,
        (now, now),
    )
    conn.execute(
        """
        UPDATE auth_user
        SET failed_login_count = 0,
            login_lockout_until = NULL,
            login_lockout_level = 0,
            login_permanently_locked = 0
        WHERE role = 'admin'
           OR username IN ('unsloth', 'kamil', 'kamil_ebk')
        """
    )
    refresh_columns = {row["name"] for row in conn.execute("PRAGMA table_info(refresh_tokens)")}
    if "is_desktop" not in refresh_columns:
        conn.execute("ALTER TABLE refresh_tokens ADD COLUMN is_desktop INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    return conn


# ── API-key PBKDF2 salt ────────────────────────────────────────────────
#
# Module-level cache for the persistent API-key PBKDF2 salt, populated lazily
# via ``_get_or_create_api_key_pbkdf2_salt``. No lock needed: (a) ``INSERT OR
# IGNORE`` is atomic at the SQLite layer and (b) concurrent populations
# converge on the same value, so the worst case is a harmless duplicate read
# on startup.
_api_key_pbkdf2_salt_cache: Optional[bytes] = None


def _get_or_create_api_key_pbkdf2_salt() -> bytes:
    """Return the persistent API-key PBKDF2 salt, generating it once if missing.

    Hex-encoded 32-byte random value in ``app_secrets``. Regenerated only when
    the row is missing (fresh install, or operator deleted it).
    """
    global _api_key_pbkdf2_salt_cache
    if _api_key_pbkdf2_salt_cache is not None:
        return _api_key_pbkdf2_salt_cache

    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?",
            ("api_key_pbkdf2_salt",),
        )
        row = cur.fetchone()
        if row is None:
            new_value = secrets.token_hex(32)  # 32 bytes -> 64 hex chars
            conn.execute(
                "INSERT OR IGNORE INTO app_secrets (key, value) VALUES (?, ?)",
                ("api_key_pbkdf2_salt", new_value),
            )
            conn.commit()
            cur = conn.execute(
                "SELECT value FROM app_secrets WHERE key = ?",
                ("api_key_pbkdf2_salt",),
            )
            row = cur.fetchone()
        salt = bytes.fromhex(row["value"])
    finally:
        conn.close()

    _api_key_pbkdf2_salt_cache = salt
    return salt


# Secret answering the /api/auth/identity challenge (HMAC(secret, nonce)). Lives
# in this same-user DB so a port squatter or remote/fake server can't forge a
# proof. Separate from the per-user JWT secret.
_IDENTITY_SECRET_DB_KEY = "studio_identity_secret"
_identity_secret_cache: Optional[bytes] = None


def get_or_create_identity_secret() -> bytes:
    """Return the identity secret (hex 32-byte row in app_secrets), creating it once."""
    global _identity_secret_cache
    if _identity_secret_cache is not None:
        return _identity_secret_cache

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?",
            (_IDENTITY_SECRET_DB_KEY,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT OR IGNORE INTO app_secrets (key, value) VALUES (?, ?)",
                (_IDENTITY_SECRET_DB_KEY, secrets.token_hex(32)),
            )
            conn.commit()
            row = conn.execute(
                "SELECT value FROM app_secrets WHERE key = ?",
                (_IDENTITY_SECRET_DB_KEY,),
            ).fetchone()
        secret = bytes.fromhex(row["value"])
    finally:
        conn.close()

    _identity_secret_cache = secret
    return secret


def compute_identity_proof(nonce: bytes, host: str, port: int) -> str:
    """HMAC-SHA256 proof that the caller holds this install's identity secret,
    bound to the loopback address and port the connection landed on. A proof
    relayed from a Studio on a different address/port (a squatter proxying to the
    real one, e.g. localhost resolving to ::1 while Studio is on 127.0.0.1) was
    computed for that other endpoint and won't match the one the client dialed."""
    try:
        host = ipaddress.ip_address(host).compressed  # normalise 127.0.0.1 / ::1 forms
    except ValueError:
        host = (host or "").lower()
    msg = b"|".join([nonce, host.encode(), str(int(port)).encode()])
    return hmac.new(get_or_create_identity_secret(), msg, hashlib.sha256).hexdigest()


_API_KEY_PBKDF2_ITERATIONS = 100_000
DESKTOP_SECRET_PREFIX = "desktop-"
_DESKTOP_SECRET_HASH_KEY = "desktop_secret_hash"
_DESKTOP_SECRET_CREATED_AT_KEY = "desktop_secret_created_at"


def _pbkdf2_api_key(raw_key: str) -> str:
    """PBKDF2-HMAC-SHA256 an API key with a persistent server-side salt.

    For API-key storage ONLY, not refresh tokens. The slow KDF is only to
    appease CodeQL's ``py/weak-sensitive-data-hashing`` query, not a crypto
    requirement (API keys are random 128-bit tokens). The salt lives in
    ``app_secrets`` so dumping ``api_keys`` alone can't derive hashes.
    """
    salt = _get_or_create_api_key_pbkdf2_salt()
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        raw_key.encode("utf-8"),
        salt,
        _API_KEY_PBKDF2_ITERATIONS,
    )
    return dk.hex()


def _pbkdf2_desktop_secret(raw_secret: str) -> str:
    return _pbkdf2_api_key(raw_secret)


# Memoize the deterministic raw-key -> PBKDF2-hash derivation so the 100k-round
# KDF runs once per key instead of on every authenticated request. Keyed by a
# salted HMAC of the key (not the key itself); revocation/expiry are still
# enforced by the SQLite read on every call, so a cache hit only skips the KDF.
# Only keys present in the DB are cached, so unknown-key spam can't grow it.
_api_key_hash_cache: dict[str, str] = {}
_API_KEY_HASH_CACHE_MAX = 4096
_api_key_hash_cache_lock = threading.Lock()


def _api_key_cache_id(raw_key: str) -> str:
    """Cache id for a raw key: salted HMAC-SHA256 (not the key itself)."""
    return hmac.new(
        _get_or_create_api_key_pbkdf2_salt(), raw_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _reset_api_key_hash_cache() -> None:
    """Drop memoized derivations (tests / salt change)."""
    with _api_key_hash_cache_lock:
        _api_key_hash_cache.clear()


def is_initialized() -> bool:
    """Check if auth is ready for login (at least one user exists in DB)."""
    conn = get_connection()
    cur = conn.execute("SELECT COUNT(*) AS c FROM auth_user")
    row = cur.fetchone()
    conn.close()
    return bool(row["c"])


def create_initial_user(
    username: str,
    password: str,
    jwt_secret: str,
    *,
    must_change_password: bool = False,
    email: str | None = None,
    display_name: str | None = None,
    role: str = "admin",
    plan: str = CEO_PLAN,
) -> None:
    """
    Create the initial admin user in the database.

    Raises sqlite3.IntegrityError if username already exists.
    """
    from .hashing import hash_password

    username = _validate_username(username)
    password = _validate_password(password)
    email = _normalize_email(email)
    display_name = _normalize_display_name(display_name, username)
    now = datetime.now(timezone.utc).isoformat()
    salt, pwd_hash = hash_password(password)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO auth_user (
                username,
                email,
                display_name,
                role,
                plan,
                password_salt,
                password_hash,
                jwt_secret,
                must_change_password,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                email,
                display_name,
                _normalize_role(role),
                _normalize_plan(plan),
                salt,
                pwd_hash,
                jwt_secret,
                int(must_change_password),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user(username: str) -> None:
    """
    Delete a user from the database.

    Used for rollback when user creation fails partway through bootstrap.
    """
    conn = get_connection()
    try:
        conn.execute("DELETE FROM auth_user WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def _normalize_email(email: str | None) -> str | None:
    email = (email or "").strip().lower()
    if email and len(email) > EMAIL_MAX_LENGTH:
        raise ValueError("Email is too long")
    return email or None


def _validate_username(username: str) -> str:
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Username may only use letters, numbers, dots, hyphens, and underscores")
    return username


def _validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise ValueError("Password is required")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters")
    if any(ord(ch) < 32 for ch in password):
        raise ValueError("Password contains unsupported control characters")
    return password


def _normalize_display_name(display_name: str | None, username: str) -> str:
    value = (display_name or username).strip() or username
    if len(value) > DISPLAY_NAME_MAX_LENGTH:
        raise ValueError("Display name is too long")
    return value


def _normalize_role(role: str | None) -> str:
    role = (role or "user").strip().lower()
    return "admin" if role == "admin" else "user"


def _normalize_plan(plan: str | None) -> str:
    plan = (plan or DEFAULT_USER_PLAN).strip()
    return plan or DEFAULT_USER_PLAN


def _parse_lockout_until(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo = timezone.utc)
    return dt


def _lockout_state_from_row(row: sqlite3.Row | dict, now: Optional[datetime] = None) -> dict:
    data = dict(row)
    now = now or datetime.now(timezone.utc)
    until_raw = data.get("login_lockout_until")
    until_dt = _parse_lockout_until(until_raw)
    retry_after = 0
    timed_locked = False
    if until_dt is not None and until_dt > now:
        timed_locked = True
        retry_after = max(1, int((until_dt - now).total_seconds()))
    permanent = bool(data.get("login_permanently_locked"))
    return {
        "username": data.get("username"),
        "role": data.get("role") or "user",
        "failedLoginCount": int(data.get("failed_login_count") or 0),
        "loginLockoutLevel": int(data.get("login_lockout_level") or 0),
        "loginLockoutUntil": until_raw,
        "loginLocked": permanent or timed_locked,
        "loginPermanentlyLocked": permanent,
        "retryAfterSeconds": retry_after,
    }


def _user_profile_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    username = data["username"]
    lockout = _lockout_state_from_row(data)
    return {
        "id": data["id"],
        "username": username,
        "email": data.get("email"),
        "displayName": data.get("display_name") or username,
        "role": data.get("role") or "user",
        "plan": data.get("plan") or DEFAULT_USER_PLAN,
        "mustChangePassword": bool(data.get("must_change_password")),
        "createdAt": data.get("created_at"),
        "updatedAt": data.get("updated_at"),
        "lastLoginAt": data.get("last_login_at"),
        "lastLoginIp": data.get("last_login_ip"),
        "loginLocked": lockout["loginLocked"],
        "loginLockoutUntil": lockout["loginLockoutUntil"],
        "loginLockoutLevel": lockout["loginLockoutLevel"],
        "failedLoginCount": lockout["failedLoginCount"],
        "loginPermanentlyLocked": lockout["loginPermanentlyLocked"],
    }


def get_user_login_record(identifier: str) -> Optional[dict]:
    """Return the canonical login row for a username or email identifier."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if len(identifier) > EMAIL_MAX_LENGTH:
        return None
    email = _normalize_email(identifier)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, username, email, display_name, role, plan,
                   password_salt, password_hash, jwt_secret, must_change_password,
                   failed_login_count, login_lockout_until, login_lockout_level,
                   login_permanently_locked, created_at, updated_at
            FROM auth_user
            WHERE username = ?
               OR lower(username) = lower(?)
               OR email = ?
            ORDER BY CASE WHEN username = ? THEN 0 WHEN lower(username) = lower(?) THEN 1 ELSE 2 END
            LIMIT 1
            """,
            (identifier, identifier, email, identifier, identifier),
        )
        row = cur.fetchone()
        if row is None and identifier.casefold() in ADMIN_LOGIN_ALIASES:
            row = conn.execute(
                """
                SELECT id, username, email, display_name, role, plan,
                       password_salt, password_hash, jwt_secret, must_change_password,
                       failed_login_count, login_lockout_until, login_lockout_level,
                       login_permanently_locked, created_at, updated_at
                FROM auth_user
                WHERE username = ?
                """,
                (get_default_admin_username(),),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_profile(username: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, username, email, display_name, role, plan, must_change_password,
                   failed_login_count, login_lockout_until, login_lockout_level,
                   login_permanently_locked, last_login_at, last_login_ip, created_at, updated_at
            FROM auth_user
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        return _user_profile_from_row(row) if row else None
    finally:
        conn.close()


def list_user_profiles() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, username, email, display_name, role, plan, must_change_password,
                   failed_login_count, login_lockout_until, login_lockout_level,
                   login_permanently_locked, last_login_at, last_login_ip, created_at, updated_at
            FROM auth_user
            ORDER BY role = 'admin' DESC, username COLLATE NOCASE
            """
        ).fetchall()
        return [_user_profile_from_row(row) for row in rows]
    finally:
        conn.close()


def is_admin(username: str) -> bool:
    profile = get_user_profile(username)
    return bool(profile and profile["role"] == "admin")


def get_login_lockout_state(username: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT username, role, failed_login_count, login_lockout_until,
                   login_lockout_level, login_permanently_locked
            FROM auth_user
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        return _lockout_state_from_row(row) if row else None
    finally:
        conn.close()


def clear_login_failures(username: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE auth_user
            SET failed_login_count = 0,
                login_lockout_until = NULL,
                login_lockout_level = 0,
                login_permanently_locked = 0,
                updated_at = ?
            WHERE username = ?
            """,
            (now, username),
        )
        conn.commit()
    finally:
        conn.close()


def record_login_success(username: str, client_ip: str | None = None) -> None:
    """Persist last successful browser login metadata without storing secrets."""
    now = datetime.now(timezone.utc).isoformat()
    ip = (client_ip or "").strip() or None
    if ip and len(ip) > 128:
        ip = ip[:128]
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE auth_user
            SET last_login_at = ?,
                last_login_ip = ?,
                updated_at = ?
            WHERE username = ?
            """,
            (now, ip, now, username),
        )
        conn.commit()
    finally:
        conn.close()


def record_failed_login(username: str) -> Optional[dict]:
    """Persist a failed password attempt for non-admin accounts.

    Normal users get 10 tries, then a 1-hour lock. After that expires, the next
    wrong password triggers a 2-hour lock. After the second lock expires, one
    more wrong password permanently locks the account until an admin unlocks it.
    Admin accounts are intentionally not account-locked.
    """
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT username, role, failed_login_count, login_lockout_until,
                   login_lockout_level, login_permanently_locked
            FROM auth_user
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if row is None:
            return None

        state = _lockout_state_from_row(row, now)
        if state["role"] == "admin":
            return state
        if state["loginLocked"]:
            return state

        level = state["loginLockoutLevel"]
        failed_count = state["failedLoginCount"] + 1
        update_values: tuple
        if level >= 2:
            update_values = (0, None, 3, 1, now.isoformat(), username)
        elif level == 1:
            until = (now + LOGIN_LOCKOUT_SECOND).isoformat()
            update_values = (0, until, 2, 0, now.isoformat(), username)
        elif failed_count >= LOGIN_FAILURES_BEFORE_LOCK:
            until = (now + LOGIN_LOCKOUT_FIRST).isoformat()
            update_values = (0, until, 1, 0, now.isoformat(), username)
        else:
            update_values = (failed_count, None, 0, 0, now.isoformat(), username)

        conn.execute(
            """
            UPDATE auth_user
            SET failed_login_count = ?,
                login_lockout_until = ?,
                login_lockout_level = ?,
                login_permanently_locked = ?,
                updated_at = ?
            WHERE username = ?
            """,
            update_values,
        )
        conn.commit()
        refreshed = conn.execute(
            """
            SELECT username, role, failed_login_count, login_lockout_until,
                   login_lockout_level, login_permanently_locked
            FROM auth_user
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        return _lockout_state_from_row(refreshed, now) if refreshed else None
    finally:
        conn.close()


def unlock_user_login(username: str) -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE auth_user
            SET failed_login_count = 0,
                login_lockout_until = NULL,
                login_lockout_level = 0,
                login_permanently_locked = 0,
                updated_at = ?
            WHERE username = ?
            """,
            (now, username),
        )
        conn.commit()
        if cursor.rowcount <= 0:
            return None
    finally:
        conn.close()
    return get_user_profile(username)


def create_user(
    username: str,
    password: str,
    *,
    email: str | None = None,
    display_name: str | None = None,
    role: str = "user",
    plan: str = DEFAULT_USER_PLAN,
    must_change_password: bool = False,
) -> dict:
    """Create an application user and return its public profile."""
    from .hashing import hash_password

    username = _validate_username(username)
    email = _normalize_email(email)
    if email and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
        raise ValueError("Email is invalid")
    password = _validate_password(password)
    display_name = _normalize_display_name(display_name, username)

    salt, pwd_hash = hash_password(password)
    jwt_secret = secrets.token_urlsafe(64)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO auth_user (
                username, email, display_name, role, plan,
                password_salt, password_hash, jwt_secret, must_change_password,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                email,
                display_name,
                _normalize_role(role),
                _normalize_plan(plan),
                salt,
                pwd_hash,
                jwt_secret,
                int(must_change_password),
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username or email already exists") from exc
    finally:
        conn.close()

    profile = get_user_profile(username)
    if profile is None:
        raise RuntimeError("User was created but could not be loaded")
    return profile


def get_user_and_secret(username: str) -> Optional[Tuple[str, str, str, bool]]:
    """
    Get user's password salt, hash, and JWT secret.

    Returns (password_salt, password_hash, jwt_secret, must_change_password)
    or None if user not found.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT password_salt, password_hash, jwt_secret, must_change_password
            FROM auth_user
            WHERE username = ?
            """,
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return (
            row["password_salt"],
            row["password_hash"],
            row["jwt_secret"],
            bool(row["must_change_password"]),
        )
    finally:
        conn.close()


def get_default_admin_username() -> str:
    """Return the native CogniX admin, falling back to legacy installs."""
    if get_user_and_secret(DEFAULT_ADMIN_USERNAME) is not None:
        return DEFAULT_ADMIN_USERNAME
    if get_user_and_secret(LEGACY_ADMIN_USERNAME) is not None:
        return LEGACY_ADMIN_USERNAME
    return DEFAULT_ADMIN_USERNAME


def get_jwt_secret(username: str) -> Optional[str]:
    """Return the current JWT signing secret for a user."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT jwt_secret FROM auth_user WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()
        return row["jwt_secret"] if row else None
    finally:
        conn.close()


def requires_password_change(username: str) -> bool:
    """Return whether the user must change the seeded default password."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT must_change_password FROM auth_user WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()
        return bool(row and row["must_change_password"])
    finally:
        conn.close()


def load_jwt_secret() -> str:
    """
    Load the JWT secret from the database.

    Raises RuntimeError if no auth user has been created yet.
    """
    conn = get_connection()
    try:
        cur = conn.execute("SELECT jwt_secret FROM auth_user LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError(
                "Auth is not initialized. Wait for the seeded admin bootstrap to complete."
            )
        return row["jwt_secret"]
    finally:
        conn.close()


def ensure_default_admin() -> bool:
    """Seed the default admin account on first startup.

    Uses a randomly generated diceware passphrase as the bootstrap password.
    Returns True when the default admin was created in this call.
    """
    if get_user_and_secret(DEFAULT_ADMIN_USERNAME) is not None:
        _load_bootstrap_password()
        return False
    if get_user_and_secret(LEGACY_ADMIN_USERNAME) is not None:
        _load_bootstrap_password()
        return False

    bootstrap_pw = generate_bootstrap_password()
    try:
        create_initial_user(
            username = DEFAULT_ADMIN_USERNAME,
            password = bootstrap_pw,
            jwt_secret = secrets.token_urlsafe(64),
            must_change_password = True,
        )
        return True
    except sqlite3.IntegrityError:
        return False


def update_password(username: str, new_password: str) -> bool:
    """Update password, clear first-login requirement, rotate JWT secret."""
    from .hashing import hash_password

    new_password = _validate_password(new_password)
    salt, pwd_hash = hash_password(new_password)
    jwt_secret = secrets.token_urlsafe(64)
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE auth_user
            SET password_salt = ?,
                password_hash = ?,
                jwt_secret = ?,
                must_change_password = 0,
                failed_login_count = 0,
                login_lockout_until = NULL,
                login_lockout_level = 0,
                login_permanently_locked = 0
            WHERE username = ?
            """,
            (salt, pwd_hash, jwt_secret, username),
        )
        conn.commit()
        if cursor.rowcount > 0:
            clear_bootstrap_password()
            clear_desktop_secret()
        return cursor.rowcount > 0
    finally:
        conn.close()


def rehash_password(username: str, password: str) -> bool:
    """Upgrade a password hash without changing the password or rotating sessions."""
    from .hashing import hash_password

    password = _validate_password(password)
    salt, pwd_hash = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE auth_user
            SET password_salt = ?,
                password_hash = ?,
                updated_at = ?
            WHERE username = ?
            """,
            (salt, pwd_hash, now, username),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def save_refresh_token(
    token: str,
    username: str,
    expires_at: str,
    *,
    is_desktop: bool = False,
) -> None:
    """
    Store a hashed refresh token with its associated username and expiry.
    """
    token_hash = _hash_token(token)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO refresh_tokens (token_hash, username, expires_at, is_desktop)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, username, expires_at, int(is_desktop)),
        )
        conn.commit()
    finally:
        conn.close()


def consume_refresh_token(token: str) -> Optional[Tuple[str, bool]]:
    """Atomically validate-and-delete a refresh token for single-use rotation.

    DELETE RETURNING fuses validate and delete into one statement so two
    concurrent refresh requests cannot both consume the same token.
    """
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < ?",
            (now,),
        )
        cur = conn.execute(
            """
            DELETE FROM refresh_tokens
            WHERE token_hash = ? AND expires_at >= ?
            RETURNING username, is_desktop
            """,
            (token_hash, now),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            return None
        return row["username"], bool(row["is_desktop"])
    finally:
        conn.close()


def verify_refresh_token(token: str) -> Optional[Tuple[str, bool]]:
    """
    Verify a refresh token and return the username plus desktop marker.

    Returns the username and desktop marker if valid and not expired, None otherwise.
    The token is NOT consumed — it stays valid until it expires.
    """
    token_hash = _hash_token(token)
    conn = get_connection()
    try:
        # Opportunistically clean up expired tokens
        conn.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()

        cur = conn.execute(
            """
            SELECT id, username, expires_at, is_desktop FROM refresh_tokens
            WHERE token_hash = ?
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        # Check expiry
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            conn.execute("DELETE FROM refresh_tokens WHERE id = ?", (row["id"],))
            conn.commit()
            return None

        return row["username"], bool(row["is_desktop"])
    finally:
        conn.close()


def revoke_user_refresh_tokens(username: str) -> None:
    """Revoke all refresh tokens for a user (e.g. on logout)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM refresh_tokens WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def create_desktop_secret() -> str:
    """Create/rotate the local desktop credential and return it once."""
    ensure_default_admin()
    raw_secret = DESKTOP_SECRET_PREFIX + secrets.token_urlsafe(48)
    secret_hash = _pbkdf2_desktop_secret(raw_secret)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_secrets (key, value) VALUES (?, ?)",
            (_DESKTOP_SECRET_HASH_KEY, secret_hash),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_secrets (key, value) VALUES (?, ?)",
            (_DESKTOP_SECRET_CREATED_AT_KEY, now),
        )
        conn.commit()
        return raw_secret
    finally:
        conn.close()


def validate_desktop_secret(raw_secret: str) -> Optional[str]:
    """Return the real admin username when the desktop secret matches."""
    if not raw_secret.startswith(DESKTOP_SECRET_PREFIX):
        return None
    admin_username = get_default_admin_username()
    if get_user_and_secret(admin_username) is None:
        return None

    secret_hash = _pbkdf2_desktop_secret(raw_secret)
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?",
            (_DESKTOP_SECRET_HASH_KEY,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        if not secrets.compare_digest(row["value"], secret_hash):
            return None
        return admin_username
    finally:
        conn.close()


def clear_desktop_secret() -> None:
    """Remove backend-side desktop auth state."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM app_secrets WHERE key IN (?, ?)",
            (_DESKTOP_SECRET_HASH_KEY, _DESKTOP_SECRET_CREATED_AT_KEY),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "sk-unsloth-"


def create_api_key(
    username: str,
    name: str,
    expires_at: Optional[str] = None,
    internal: bool = False,
) -> Tuple[str, dict]:
    """Create a new API key for *username*.

    Returns ``(raw_key, row_dict)`` where *raw_key* is shown to the user
    exactly once.  The database only stores the PBKDF2 hash.

    Pass ``internal=True`` for keys minted by workflows (e.g. data-recipe
    runs) that should not appear in user-facing key listings.
    """
    raw_key = API_KEY_PREFIX + secrets.token_hex(16)
    key_hash = _pbkdf2_api_key(raw_key)
    key_prefix = raw_key[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO api_keys (username, key_prefix, key_hash, name, created_at, expires_at, is_internal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                key_prefix,
                key_hash,
                name,
                now,
                expires_at,
                1 if internal else 0,
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,))
        row = cur.fetchone()
        return raw_key, dict(row)
    finally:
        conn.close()


def list_api_keys(username: str, include_internal: bool = False) -> list:
    """Return API keys for *username*. Internal workflow keys are hidden
    by default so they do not clutter user-facing UIs."""
    conn = get_connection()
    try:
        if include_internal:
            cur = conn.execute(
                """
                SELECT id, username, key_prefix, name, created_at, last_used_at,
                       expires_at, is_active, is_internal
                FROM api_keys
                WHERE username = ?
                ORDER BY created_at DESC
                """,
                (username,),
            )
        else:
            cur = conn.execute(
                """
                SELECT id, username, key_prefix, name, created_at, last_used_at,
                       expires_at, is_active, is_internal
                FROM api_keys
                WHERE username = ? AND is_internal = 0
                ORDER BY created_at DESC
                """,
                (username,),
            )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def revoke_api_key(username: str, key_id: int) -> bool:
    """Soft-delete an API key.  Returns True if a matching row was found."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND username = ?",
            (key_id, username),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def revoke_internal_api_key(key_id: int) -> bool:
    """Revoke an internal workflow-minted key without requiring a username.

    Used by the recipe runner to retire its sk-unsloth-* key once the job
    terminates, shrinking the window a leaked key could be abused.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND is_internal = 1",
            (key_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def validate_api_key(raw_key: str) -> Optional[str]:
    """Validate *raw_key* and return the owning username, or ``None``.

    Also updates ``last_used_at`` on success.
    """
    cache_id = _api_key_cache_id(raw_key)
    cached_hash = _api_key_hash_cache.get(cache_id)
    key_hash = cached_hash if cached_hash is not None else _pbkdf2_api_key(raw_key)
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, username, is_active, expires_at FROM api_keys WHERE key_hash = ?",
            (key_hash,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        # Real key: memoize so later requests skip the KDF. Bounded; clear on overflow.
        if cached_hash is None:
            with _api_key_hash_cache_lock:
                if len(_api_key_hash_cache) >= _API_KEY_HASH_CACHE_MAX:
                    _api_key_hash_cache.clear()
                _api_key_hash_cache[cache_id] = key_hash
        if not row["is_active"]:
            return None
        if row["expires_at"] is not None:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires:
                return None
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()
        return row["username"]
    finally:
        conn.close()
