# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""
Password hashing utilities using PBKDF2.
"""

import hashlib
import hmac
import secrets
from typing import Tuple

HASH_ALGORITHM = "pbkdf2_sha256"
LEGACY_PBKDF2_ITERATIONS = 100_000
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, salt: str | None = None) -> Tuple[str, str]:
    """
    Hash a password using PBKDF2-HMAC-SHA256.

    Returns (salt, hex_hash) tuple.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return salt, f"{HASH_ALGORITHM}${PBKDF2_ITERATIONS}${dk.hex()}"


def _parse_password_hash(hashed: str) -> tuple[int, str]:
    parts = (hashed or "").split("$", 2)
    if len(parts) != 3 or parts[0] != HASH_ALGORITHM:
        return LEGACY_PBKDF2_ITERATIONS, hashed
    try:
        iterations = int(parts[1])
    except ValueError:
        return LEGACY_PBKDF2_ITERATIONS, hashed
    return iterations, parts[2]


def verify_password(password: str, salt: str, hashed: str) -> bool:
    """
    Verify a password against a stored salt and hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    iterations, expected = _parse_password_hash(hashed)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(dk.hex(), expected)


def needs_rehash(hashed: str) -> bool:
    """Return True when a stored password hash should be upgraded."""
    iterations, expected = _parse_password_hash(hashed)
    return not hashed.startswith(f"{HASH_ALGORITHM}$") or iterations < PBKDF2_ITERATIONS or not expected
