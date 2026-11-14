"""Secret encryption helpers for the control plane.

The master key fails closed (ADR-002 §2.5, AG-05). Loading it never creates
one: a process without the key file gets :class:`MasterKeyUnavailable`.
Only :func:`ensure_master_key`, which the control-plane supervisor runs once
at startup in the ``app`` process, may generate a key, and only on a fresh
install. It also binds the key to the database through a fingerprint row (an
HMAC of a fixed label under the key, never the key itself), so the control
plane refuses to start with a different key, or without the key while
encrypted data exists.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

from koda.logging_config import get_logger

from .audit import record_audit_event
from .database import execute, fetch_one, now_iso
from .settings import (
    CONTROL_PLANE_MASTER_KEY,
    CONTROL_PLANE_MASTER_KEY_FILE,
    CONTROL_PLANE_MASTER_KEY_PREVIOUS,
    CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE,
)

log = get_logger(__name__)

MASTER_KEY_FINGERPRINT_LABEL = b"koda.control_plane.master_key.fingerprint.v1"
_FINGERPRINT_KEY_NAME = "control_plane_master_key"
_FINGERPRINT_PREFIX_LENGTH = 12
_RECOVERY_DOC = "docs/operations/backup-restore.md#master-key-recovery"
_ROTATION_DOC = "docs/operations/hardening.md#master-key-rotation"

# Each probe returns a row when its table holds data encrypted with the master
# key. A key is generated only when none of them does.
_CIPHERTEXT_PROBES = (
    "SELECT 1 AS present FROM cp_secret_values LIMIT 1",
    """SELECT 1 AS present FROM cp_mcp_oauth_tokens
        WHERE COALESCE(access_token_encrypted, '') <> '' OR COALESCE(refresh_token_encrypted, '') <> ''
        LIMIT 1""",
    "SELECT 1 AS present FROM cp_mcp_agent_connections WHERE env_values_json NOT IN ('', '{}') LIMIT 1",
    """SELECT 1 AS present FROM cp_provider_login_sessions WHERE details_json LIKE '%"encrypted_details"%' LIMIT 1""",
    """SELECT 1 AS present FROM cp_agent_config_versions WHERE snapshot_json LIKE '%"encrypted_value"%' LIMIT 1""",
)

EnsureOutcome = Literal["verified", "fresh_install", "upgrade", "rotation"]


class MasterKeyError(RuntimeError):
    """The control-plane master key cannot be used safely."""


class MasterKeyUnavailable(MasterKeyError):
    """This process has no usable master key. Raised instead of creating one."""


class MasterKeyMismatch(MasterKeyError):
    """The master key differs from the one whose fingerprint the database recorded."""


def _tighten_permissions(path: Path) -> None:
    try:
        if path.stat().st_mode & 0o777 > 0o600:
            path.chmod(0o600)
    except OSError:
        pass


def _read_current_key() -> bytes | None:
    """Return the current key, or ``None`` when the key file does not exist."""
    if CONTROL_PLANE_MASTER_KEY.strip():
        raise RuntimeError("CONTROL_PLANE_MASTER_KEY is deprecated; use CONTROL_PLANE_MASTER_KEY_FILE instead")
    path = CONTROL_PLANE_MASTER_KEY_FILE
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MasterKeyUnavailable(
            f"cannot read the control-plane master key at {path}: {exc.strerror or exc}"
        ) from exc
    key = raw.strip()
    if not key:
        raise MasterKeyUnavailable(f"the control-plane master key file at {path} is empty")
    _tighten_permissions(path)
    return key


def _load_master_key() -> bytes:
    """Return the current master key. Never creates one."""
    key = _read_current_key()
    if key is None:
        raise MasterKeyUnavailable(
            f"control-plane master key not found at {CONTROL_PLANE_MASTER_KEY_FILE}. This process does not create "
            "keys: the control plane creates one when it starts on a fresh install. Start the control plane "
            f"first, or restore the key file from backup ({_RECOVERY_DOC})."
        )
    return key


def _load_previous_master_key() -> bytes | None:
    """Load the previous master key for backward-compatible decryption during rotation."""
    if CONTROL_PLANE_MASTER_KEY_PREVIOUS.strip():
        return CONTROL_PLANE_MASTER_KEY_PREVIOUS.strip().encode("utf-8")
    if CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE.exists():
        raw = CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE.read_text(encoding="utf-8").strip()
        if raw:
            return raw.encode("utf-8")
    return None


def master_key_fingerprint(key: bytes) -> str:
    """Identify ``key`` without revealing it: HMAC-SHA256 of a fixed label under the key."""
    return hmac.new(key, MASTER_KEY_FINGERPRINT_LABEL, hashlib.sha256).hexdigest()


def _create_key_file(path: Path) -> None:
    """Write a new key to ``path`` (mode 0600) atomically, never replacing an existing file."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(Fernet.generate_key())
            handle.flush()
            os.fsync(handle.fileno())
        # FileExistsError: another app process created the key first; the
        # caller reads and verifies that one.
        with contextlib.suppress(FileExistsError):
            os.link(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _recorded_fingerprint() -> str | None:
    row = fetch_one(
        "SELECT fingerprint FROM cp_master_key_fingerprint WHERE key_name = ?",
        (_FINGERPRINT_KEY_NAME,),
    )
    return str(row["fingerprint"]) if row is not None else None


def _insert_fingerprint(fingerprint: str, *, reason: str) -> None:
    """Record the fingerprint unless another process already recorded one (first writer wins)."""
    now = now_iso()
    execute(
        """
        INSERT INTO cp_master_key_fingerprint (key_name, fingerprint, recorded_reason, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (key_name) DO NOTHING
        RETURNING key_name
        """,
        (_FINGERPRINT_KEY_NAME, fingerprint, reason, now, now),
    )


def _replace_fingerprint(*, expected: str, fingerprint: str, reason: str) -> bool:
    """Compare-and-set the fingerprint; ``False`` when it no longer equals ``expected``."""
    updated = execute(
        """
        UPDATE cp_master_key_fingerprint
           SET fingerprint = ?, recorded_reason = ?, updated_at = ?
         WHERE key_name = ? AND fingerprint = ?
        """,
        (fingerprint, reason, now_iso(), _FINGERPRINT_KEY_NAME, expected),
    )
    return updated > 0


def _ciphertext_exists() -> bool:
    return any(fetch_one(probe) is not None for probe in _CIPHERTEXT_PROBES)


def _short(fingerprint: str) -> str:
    return fingerprint[:_FINGERPRINT_PREFIX_LENGTH]


def _record_fingerprint_event(reason: str, fingerprint: str, *, previous: str | None = None) -> None:
    details = {"reason": reason, "fingerprint_prefix": _short(fingerprint)}
    if previous is not None:
        details["previous_fingerprint_prefix"] = _short(previous)
    log.info("control_plane_master_key_fingerprint_recorded", **details)
    record_audit_event("global", event_type="security.master_key_fingerprint_recorded", details=details)


def _mismatch(recorded: str, fingerprint: str) -> MasterKeyMismatch:
    return MasterKeyMismatch(
        f"the control-plane master key at {CONTROL_PLANE_MASTER_KEY_FILE} (fingerprint {_short(fingerprint)}) is "
        f"not the key this database recorded (fingerprint {_short(recorded)}). Refusing to start: secrets "
        "encrypted with the recorded key would not decrypt. Restore the matching key file from backup "
        f"({_RECOVERY_DOC}). When rotating keys, put the old key in CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE "
        f"({_ROTATION_DOC})."
    )


def ensure_master_key() -> EnsureOutcome:
    """Bind the master key to this database at control-plane startup, failing closed.

    Only the control-plane supervisor calls this, in the ``app`` process, before
    it seeds state, serves the API or spawns workers. Outcomes:

    * ``fresh_install``: no key file, no recorded fingerprint and no ciphertext,
      so a key is created (mode 0600) and its fingerprint recorded;
    * ``upgrade``: a key but no recorded fingerprint (an install from before
      AG-05), so the fingerprint is recorded from the present key; nothing is
      re-encrypted or deleted;
    * ``verified``: the key matches the recorded fingerprint;
    * ``rotation``: the key differs, but the previous key matches the recorded
      fingerprint, so the new key's fingerprint is recorded.

    Anything else raises :class:`MasterKeyError` with operator guidance and
    leaves the key file and the database untouched.
    """
    path = CONTROL_PLANE_MASTER_KEY_FILE
    recorded = _recorded_fingerprint()
    key = _read_current_key()
    created = False
    if key is None:
        if recorded is not None:
            raise MasterKeyUnavailable(
                f"control-plane master key not found at {path}, but this database recorded a master key "
                f"(fingerprint {_short(recorded)}). Refusing to start rather than create a new key that cannot "
                f"decrypt existing data. Restore the key file from backup ({_RECOVERY_DOC})."
            )
        if _ciphertext_exists():
            raise MasterKeyUnavailable(
                f"control-plane master key not found at {path}, but the database holds encrypted secrets. "
                "Refusing to start rather than create a new key that cannot decrypt them. Restore the key file "
                f"from backup ({_RECOVERY_DOC})."
            )
        try:
            _create_key_file(path)
        except OSError as exc:
            raise MasterKeyUnavailable(f"cannot create the control-plane master key at {path}: {exc}") from exc
        key = _load_master_key()
        created = True
    try:
        Fernet(key)
    except ValueError:
        raise MasterKeyUnavailable(
            f"the control-plane master key at {path} is not a valid Fernet key (32 url-safe base64-encoded "
            f"bytes). Restore the key file from backup ({_RECOVERY_DOC})."
        ) from None
    fingerprint = master_key_fingerprint(key)

    if recorded is None:
        reason: EnsureOutcome = "fresh_install" if created else "upgrade"
        _insert_fingerprint(fingerprint, reason=reason)
        recorded = _recorded_fingerprint()
        if recorded is None:
            raise MasterKeyError("the control-plane master key fingerprint could not be recorded")
        if not hmac.compare_digest(recorded, fingerprint):
            # Another app process recorded a different key first.
            raise _mismatch(recorded, fingerprint)
        _record_fingerprint_event(reason, fingerprint)
        clear_fernet_cache()
        return reason

    if hmac.compare_digest(recorded, fingerprint):
        log.info("control_plane_master_key_verified", fingerprint_prefix=_short(fingerprint))
        clear_fernet_cache()
        return "verified"

    previous = _load_previous_master_key()
    if previous is None or not hmac.compare_digest(master_key_fingerprint(previous), recorded):
        raise _mismatch(recorded, fingerprint)
    if not _replace_fingerprint(expected=recorded, fingerprint=fingerprint, reason="rotation"):
        current = _recorded_fingerprint()
        if current is None or not hmac.compare_digest(current, fingerprint):
            raise _mismatch(current or recorded, fingerprint)
    _record_fingerprint_event("rotation", fingerprint, previous=recorded)
    clear_fernet_cache()
    return "rotation"


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


def get_signing_key() -> bytes:
    """Return the master key bytes for HMAC-style signing operations.

    Callers MUST treat the value as opaque and never log or expose it.
    """
    return _load_master_key()
