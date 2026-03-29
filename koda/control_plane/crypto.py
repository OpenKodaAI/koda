"""Secret encryption helpers for the control plane."""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet

from .settings import CONTROL_PLANE_MASTER_KEY, CONTROL_PLANE_MASTER_KEY_FILE


def _load_master_key() -> bytes:
    if CONTROL_PLANE_MASTER_KEY.strip():
        return CONTROL_PLANE_MASTER_KEY.strip().encode("utf-8")
    if CONTROL_PLANE_MASTER_KEY_FILE.exists():
        try:
            current_mode = CONTROL_PLANE_MASTER_KEY_FILE.stat().st_mode & 0o777
            if current_mode > 0o600:
                CONTROL_PLANE_MASTER_KEY_FILE.chmod(0o600)
        except OSError:
            pass
        return CONTROL_PLANE_MASTER_KEY_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
    old_umask = os.umask(0o177)
    try:
        CONTROL_PLANE_MASTER_KEY_FILE.write_text(Fernet.generate_key().decode("utf-8"), encoding="utf-8")
        CONTROL_PLANE_MASTER_KEY_FILE.chmod(0o600)
    finally:
        os.umask(old_umask)
    return CONTROL_PLANE_MASTER_KEY_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


@lru_cache(maxsize=1)
def get_fernet() -> Fernet:
    return Fernet(_load_master_key())


def encrypt_secret(value: str) -> str:
    return get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"
