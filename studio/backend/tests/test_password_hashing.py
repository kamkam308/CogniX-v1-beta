import hashlib

from auth import hashing


def test_password_hash_uses_versioned_strong_pbkdf2_format():
    salt, stored = hashing.hash_password("correct-password-123")

    assert len(salt) >= 32
    assert stored.startswith(f"{hashing.HASH_ALGORITHM}${hashing.PBKDF2_ITERATIONS}$")
    assert hashing.verify_password("correct-password-123", salt, stored) is True
    assert hashing.verify_password("wrong-password", salt, stored) is False
    assert hashing.needs_rehash(stored) is False


def test_legacy_pbkdf2_hash_still_verifies_and_requires_rehash():
    legacy_salt = "legacy-salt"
    legacy_digest = hashlib.pbkdf2_hmac(
        "sha256",
        b"correct-password-123",
        legacy_salt.encode("utf-8"),
        hashing.LEGACY_PBKDF2_ITERATIONS,
    ).hex()

    assert hashing.verify_password("correct-password-123", legacy_salt, legacy_digest) is True
    assert hashing.needs_rehash(legacy_digest) is True
