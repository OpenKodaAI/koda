"""Secret encryption helpers for the control plane.

The master key fails closed (ADR-002 §2.5, AG-05). Loading it never creates
one: a process without the key file gets :class:`MasterKeyUnavailable`.
Only :func:`ensure_master_key`, which the control-plane supervisor runs once
at startup in the ``app`` process, may generate a key, and only on a fresh
install. It also binds the key to the database through a fingerprint row (an
HMAC of a fixed label under the key, never the key itself), so the control
plane refuses to start with a different key, or without the key while
encrypted data exists. On the first start after an upgrade, before any
fingerprint exists, the key is recorded only if it decrypts stored data.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken

from koda.logging_config import get_logger

from .audit import record_audit_event
from .database import execute, fetch_all, fetch_one, now_iso
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
_LOST_KEY_DOC = "docs/operations/backup-restore.md#if-the-key-is-permanently-lost"
_ROTATION_DOC = "docs/operations/hardening.md#master-key-rotation"
# The operator writes this file next to the key file, holding the key's
# fingerprint prefix, to accept a key that decrypts none of the stored data
# because the original key is lost for good. It is read only while no
# fingerprint is recorded, and removed once used.
_LOST_KEY_ACKNOWLEDGEMENT_SUFFIX = ".accept-undecryptable"

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

# The same stores, read back on the first start after an upgrade: the newest
# rows of each, which the install wrote with the key it was last using. Each
# value is a Fernet token, or JSON whose strings include Fernet tokens.
_CIPHERTEXT_SAMPLE_ROWS = 5
_CIPHERTEXT_SAMPLES = (
    f"SELECT encrypted_value AS value FROM cp_secret_values ORDER BY updated_at DESC LIMIT {_CIPHERTEXT_SAMPLE_ROWS}",
    f"""SELECT access_token_encrypted AS value FROM cp_mcp_oauth_tokens
        WHERE COALESCE(access_token_encrypted, '') <> '' ORDER BY updated_at DESC LIMIT {_CIPHERTEXT_SAMPLE_ROWS}""",
    f"""SELECT refresh_token_encrypted AS value FROM cp_mcp_oauth_tokens
        WHERE COALESCE(refresh_token_encrypted, '') <> '' ORDER BY updated_at DESC LIMIT {_CIPHERTEXT_SAMPLE_ROWS}""",
    f"""SELECT env_values_json AS value FROM cp_mcp_agent_connections
        WHERE env_values_json NOT IN ('', '{{}}') ORDER BY updated_at DESC LIMIT {_CIPHERTEXT_SAMPLE_ROWS}""",
    f"""SELECT details_json AS value FROM cp_provider_login_sessions
        WHERE details_json LIKE '%"encrypted_details"%' ORDER BY updated_at DESC LIMIT {_CIPHERTEXT_SAMPLE_ROWS}""",
    f"""SELECT snapshot_json AS value FROM cp_agent_config_versions
        WHERE snapshot_json LIKE '%"encrypted_value"%' ORDER BY id DESC LIMIT {_CIPHERTEXT_SAMPLE_ROWS}""",
)
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+={0,2}")
# Version byte, timestamp, IV, at least one AES block, HMAC.
_FERNET_MIN_TOKEN_BYTES = 1 + 8 + 16 + 16 + 32
_FERNET_VERSION = 0x80

EnsureOutcome = Literal["verified", "fresh_install", "upgrade", "rotation", "lost_key_reset"]


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


def _is_fernet_token(text: str) -> bool:
    """Whether ``text`` is shaped like a Fernet token, whatever key made it."""
    if not _BASE64URL.fullmatch(text):
        return False
    try:
        data = base64.urlsafe_b64decode(text)
    except ValueError:
        return False
    return (
        len(data) >= _FERNET_MIN_TOKEN_BYTES
        and data[0] == _FERNET_VERSION
        and (len(data) - _FERNET_MIN_TOKEN_BYTES) % 16 == 0
    )


def _fernet_tokens(value: object) -> list[str]:
    """The Fernet tokens a stored value holds: the value itself, or the strings inside its JSON."""
    if not isinstance(value, str):
        return []
    text = value.strip()
    if _is_fernet_token(text):
        return [text]
    try:
        pending: list[Any] = [json.loads(text)]
    except (ValueError, RecursionError):
        return []
    tokens: list[str] = []
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and _is_fernet_token(item.strip()):
            tokens.append(item.strip())
    return tokens


def _ciphertext_samples() -> list[str]:
    """Fernet tokens from the newest rows of every store that holds master-key ciphertext."""
    samples: list[str] = []
    for query in _CIPHERTEXT_SAMPLES:
        for row in fetch_all(query):
            samples.extend(_fernet_tokens(row["value"]))
    return samples


def _decrypts_any(samples: list[str], keys: list[bytes]) -> bool:
    fernets: list[Fernet] = []
    for candidate in keys:
        try:
            fernets.append(Fernet(candidate))
        except ValueError:
            continue  # not a Fernet key (only the previous key can be), so it decrypts nothing
    for token in samples:
        for fernet in fernets:
            try:
                fernet.decrypt(token)
            except InvalidToken:
                continue
            return True
    return False


def _lost_key_acknowledgement_path() -> Path:
    path = CONTROL_PLANE_MASTER_KEY_FILE
    return path.with_name(path.name + _LOST_KEY_ACKNOWLEDGEMENT_SUFFIX)


def _read_lost_key_acknowledgement() -> str | None:
    """The fingerprint prefix the acknowledgement file names, or ``None`` when there is no file."""
    try:
        raw = _lost_key_acknowledgement_path().read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return ""
    return raw.decode("utf-8", "replace").strip().lower()


def _remove_lost_key_acknowledgement() -> None:
    path = _lost_key_acknowledgement_path()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("control_plane_master_key_acknowledgement_not_removed", path=str(path), error=str(exc))


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


def _upgrade_outcome(key: bytes, fingerprint: str) -> EnsureOutcome:
    """Decide whether the key found on the first start after an upgrade may be recorded.

    Releases before AG-05 created a new key whenever the key file was missing,
    so the key present now may not be the one that encrypted the stored data.
    Recording such a key would make the control plane refuse the original key
    once the operator restores it. The key, or the previous key during a
    rotation, must therefore decrypt at least one of the newest stored values,
    unless the operator acknowledged, for this key, that the original is lost.
    """
    samples = _ciphertext_samples()
    previous = _load_previous_master_key()
    keys = [key] if previous is None else [key, previous]
    if not samples or _decrypts_any(samples, keys):
        return "upgrade"
    acknowledgement = _lost_key_acknowledgement_path()
    acknowledged = _read_lost_key_acknowledgement()
    if acknowledged and len(acknowledged) >= _FINGERPRINT_PREFIX_LENGTH and fingerprint.startswith(acknowledged):
        log.warning(
            "control_plane_master_key_accepted_without_decrypting_stored_data",
            fingerprint_prefix=_short(fingerprint),
            undecryptable_samples=len(samples),
        )
        return "lost_key_reset"
    note = (
        f" {acknowledgement} exists but does not name this key's fingerprint prefix, so it does not apply."
        if acknowledged is not None
        else ""
    )
    raise MasterKeyMismatch(
        f"the control-plane master key at {CONTROL_PLANE_MASTER_KEY_FILE} (fingerprint {_short(fingerprint)}) "
        f"decrypts none of the {len(samples)} newest encrypted values in this database, and no master key "
        "fingerprint is recorded yet. Refusing to record it as this database's key: a release before this check "
        "may have created it after the original key was lost. Restore the original key file from backup "
        f"({_RECOVERY_DOC}).{note} If the original key is permanently lost, write {_short(fingerprint)} to "
        f"{acknowledgement} to accept this key; the stored secrets stay undecryptable until they are re-entered "
        f"({_LOST_KEY_DOC})."
    )


def ensure_master_key() -> EnsureOutcome:
    """Bind the master key to this database at control-plane startup, failing closed.

    Only the control-plane supervisor calls this, in the ``app`` process, before
    it seeds state, serves the API or spawns workers. Outcomes:

    * ``fresh_install``: no key file, no recorded fingerprint and no ciphertext,
      so a key is created (mode 0600) and its fingerprint recorded;
    * ``upgrade``: a key but no recorded fingerprint (an install from before
      AG-05), and the key, or the previous key, decrypts at least one of the
      newest stored values (or nothing is stored), so the fingerprint is
      recorded from the present key; nothing is re-encrypted or deleted;
    * ``lost_key_reset``: as ``upgrade``, but the key decrypts none of the
      stored values and the operator acknowledged this key as the replacement
      for a key that is lost for good (the acknowledgement file next to the
      key file names its fingerprint prefix; it is removed once used);
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
        reason: EnsureOutcome = "fresh_install" if created else _upgrade_outcome(key, fingerprint)
        _insert_fingerprint(fingerprint, reason=reason)
        recorded = _recorded_fingerprint()
        if recorded is None:
            raise MasterKeyError("the control-plane master key fingerprint could not be recorded")
        if not hmac.compare_digest(recorded, fingerprint):
            # Another app process recorded a different key first.
            raise _mismatch(recorded, fingerprint)
        _record_fingerprint_event(reason, fingerprint)
        if reason == "lost_key_reset":
            _remove_lost_key_acknowledgement()
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
