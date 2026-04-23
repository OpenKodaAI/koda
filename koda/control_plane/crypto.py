"""Secret encryption helpers for the control plane."""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .settings import (
    CONTROL_PLANE_MASTER_KEY,
    CONTROL_PLANE_MASTER_KEY_FILE,
    CONTROL_PLANE_MASTER_KEY_PREVIOUS,
    CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE,
)


def _load_master_key() -> bytes:
    if CONTROL_PLANE_MASTER_KEY.strip():
        raise RuntimeError("CONTROL_PLANE_MASTER_KEY is deprecated; use CONTROL_PLANE_MASTER_KEY_FILE instead")
    if CONTROL_PLANE_MASTER_KEY_FILE.exists():
        try:
            current_mode = CONTROL_PLANE_MASTER_KEY_FILE.stat().st_mode & 0o777
            if current_mode > 0o600:
                CONTROL_PLANE_MASTER_KEY_FILE.chmod(0o600)
        except OSError:
            pass
        return CONTROL_PLANE_MASTER_KEY_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
    CONTROL_PLANE_MASTER_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o177)
    try:
        CONTROL_PLANE_MASTER_KEY_FILE.write_text(Fernet.generate_key().decode("utf-8"), encoding="utf-8")
        CONTROL_PLANE_MASTER_KEY_FILE.chmod(0o600)
    finally:
        os.umask(old_umask)
    return CONTROL_PLANE_MASTER_KEY_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


def _load_previous_master_key() -> bytes | None:
    """Load the previous master key for backward-compatible decryption during rotation."""
    if CONTROL_PLANE_MASTER_KEY_PREVIOUS.strip():
        return CONTROL_PLANE_MASTER_KEY_PREVIOUS.strip().encode("utf-8")
    if CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE.exists():
        raw = CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE.read_text(encoding="utf-8").strip()
        if raw:
            return raw.encode("utf-8")
    return None


@lru_cache(maxsize=1)
def get_fernet() -> Fernet:
    return Fernet(_load_master_key())


@lru_cache(maxsize=1)
def get_previous_fernet() -> Fernet | None:
    key = _load_previous_master_key()
    if key is None:
        return None
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    """Encrypt a secret value. Always uses the current master key."""
    return str(get_fernet().encrypt(value.encode("utf-8")).decode("utf-8"))


def decrypt_secret(value: str) -> str:
    """Decrypt a secret value.

    Tries the current master key first; if that fails and a previous key is
    configured, falls back to the previous key for backward compatibility
    during key rotation.
    """
    data = value.encode("utf-8")
    try:
        return str(get_fernet().decrypt(data).decode("utf-8"))
    except InvalidToken:
        previous = get_previous_fernet()
        if previous is None:
            raise
        return str(previous.decrypt(data).decode("utf-8"))


def rotate_master_key(encrypted_values: list[str]) -> list[str]:
    """Re-encrypt a list of ciphertext values with the current master key.

    Each value is decrypted (using current or previous key) and re-encrypted
    with the current key.  Returns the list of newly encrypted values in the
    same order.

    After calling this, the caller should persist the updated ciphertexts and
    remove the previous key from the environment.
    """
    results: list[str] = []
    for ct in encrypted_values:
        plaintext = decrypt_secret(ct)
        results.append(encrypt_secret(plaintext))
    return results


def clear_fernet_cache() -> None:
    """Clear cached Fernet instances, e.g. after key rotation."""
    get_fernet.cache_clear()
    get_previous_fernet.cache_clear()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) < 8:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"
