"""First-boot bootstrap code provisioning.

When the control plane starts without an owner account, we need a way for the
operator to authenticate the *first* registration request. Three mechanisms are
supported (in priority order):

1. **Loopback trust** — if `ALLOW_LOOPBACK_BOOTSTRAP=true` and the incoming
   request originates from 127.0.0.1/::1 without `X-Forwarded-For`, the registration
   endpoint accepts requests without a bootstrap code. Default: true in development,
   false in production (enforced in settings.py at boot).
2. **Env var** — `CONTROL_PLANE_BOOTSTRAP_CODE` seeds the code instead of autogen.
3. **Disk file** — `state/control_plane/bootstrap.txt` (mode 0600) written on first
   boot if no owner exists. The operator SSHs in and reads it.

The file is deleted automatically after the owner registers.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path

from koda.logging_config import get_logger

from .settings import (
    CONTROL_PLANE_BOOTSTRAP_CODE_SEED,
    STATE_ROOT_DIR,
)

log = get_logger(__name__)

_BOOTSTRAP_FILE_PATH: Path = STATE_ROOT_DIR / "control_plane" / "bootstrap.txt"
_BOOTSTRAP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def bootstrap_file_path() -> Path:
    return _BOOTSTRAP_FILE_PATH


def _generate_code() -> str:
    chunks = ["".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(chunks)


def ensure_bootstrap_file(*, has_owner: bool) -> str | None:
    """Write a bootstrap code to disk if one is needed and none exists.

    Returns the plaintext code if a *new* one was written (so callers can echo
    it to the log once), or None if nothing was written.

    Does nothing when:
    - The owner account already exists.
    - The file already exists (we never overwrite an existing code).
    - Both the env seed and the file path point to a code — env takes priority
      but we still don't overwrite the file.
    """
    if has_owner:
        if _BOOTSTRAP_FILE_PATH.exists():
            try:
                _BOOTSTRAP_FILE_PATH.unlink()
                log.info("bootstrap_file_removed_owner_exists", path=str(_BOOTSTRAP_FILE_PATH))
            except OSError as exc:
                log.warning("bootstrap_file_unlink_failed", path=str(_BOOTSTRAP_FILE_PATH), error=str(exc))
        return None
    if _BOOTSTRAP_FILE_PATH.exists():
        return None
    _BOOTSTRAP_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    code = CONTROL_PLANE_BOOTSTRAP_CODE_SEED or _generate_code()
    try:
        fd = os.open(
            str(_BOOTSTRAP_FILE_PATH),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return None
    try:
        os.write(fd, f"{code}\n".encode())
    finally:
        os.close(fd)
    with contextlib.suppress(OSError):
        os.chmod(str(_BOOTSTRAP_FILE_PATH), 0o600)
    log.info("bootstrap_file_written", path=str(_BOOTSTRAP_FILE_PATH))
    return code


def read_bootstrap_file() -> str | None:
    """Return the bootstrap code stored on disk, if any."""
    if not _BOOTSTRAP_FILE_PATH.exists():
        return None
    try:
        content = _BOOTSTRAP_FILE_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        log.warning("bootstrap_file_read_failed", path=str(_BOOTSTRAP_FILE_PATH), error=str(exc))
        return None
    return content or None


def consume_bootstrap_file() -> None:
    """Delete the bootstrap file after successful owner registration."""
    if not _BOOTSTRAP_FILE_PATH.exists():
        return
    try:
        _BOOTSTRAP_FILE_PATH.unlink()
        log.info("bootstrap_file_consumed", path=str(_BOOTSTRAP_FILE_PATH))
    except OSError as exc:
        log.warning("bootstrap_file_unlink_failed", path=str(_BOOTSTRAP_FILE_PATH), error=str(exc))


def is_loopback_request(remote_ip: str | None, forwarded_for: str | None) -> bool:
    """True when the request came straight from loopback with no proxy hops.

    The ALLOW_LOOPBACK_BOOTSTRAP flag is checked separately by callers; this
    function only reports whether the transport is trusted, not whether the
    policy allows it.
    """
    if not remote_ip:
        return False
    if str(forwarded_for or "").strip():
        return False
    return remote_ip in {"127.0.0.1", "::1", "localhost"}
