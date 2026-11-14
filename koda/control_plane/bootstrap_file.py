"""First-boot bootstrap code provisioning.

When the control plane starts without an owner account, we need a way for the
operator to authenticate the *first* registration request. Three mechanisms are
supported (in priority order):

1. **Loopback trust** — if `ALLOW_LOOPBACK_BOOTSTRAP=true` and the incoming
   request originates from 127.0.0.1/::1 without `X-Forwarded-For`, the registration
   endpoint accepts requests without a bootstrap code. Default: true in development,
   false in production (enforced in settings.py at boot).
2. **Env var** — `CONTROL_PLANE_BOOTSTRAP_CODE` seeds the code instead of autogen.
   The file keeps the seed as configured; `operator_auth` canonicalizes both the
   stored and the typed code, so only its ASCII letters and digits count. A seed
   with fewer than 12 of them (a generated code has 12) is still used, but logs a
   `bootstrap_code_seed_weak` warning when the file is written. The /setup
   screen's code field takes at most 12 characters from `_BOOTSTRAP_ALPHABET`, so
   a seed with more, or with any other letter or digit (0, 1, I, O), can only be
   sent to the API; it logs a `bootstrap_code_seed_not_typeable` warning. The
   seed itself is never logged: the operator chose it.
3. **Disk file** — `state/control_plane/bootstrap.txt` (mode 0600) written on first
   boot if no owner exists. The operator SSHs in and reads it. A generated code is
   also shown once, in a banner on stderr; the structured log (`bootstrap_file_written`)
   never carries it. The code expires `CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS` after
   the file is written; while no owner exists, the next status request replaces an
   expired file with a new code.

The file is deleted automatically after the owner registers.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from koda.logging_config import get_logger

from .settings import (
    CONTROL_PLANE_BOOTSTRAP_CODE_SEED,
    CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS,
    STATE_ROOT_DIR,
)

log = get_logger(__name__)

_BOOTSTRAP_FILE_PATH: Path = STATE_ROOT_DIR / "control_plane" / "bootstrap.txt"
_BOOTSTRAP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# The /setup screen's code field (apps/web/src/components/setup/bootstrap-code-input.tsx)
# keeps at most this many characters, from _BOOTSTRAP_ALPHABET only, dropping any other.
_SETUP_FIELD_CHARACTERS = 12
# A generated code has 12 letters and digits; a seed with fewer is weaker than the default.
_SEED_MIN_SIGNIFICANT_CHARACTERS = 12
_SEED_ADVICE = (
    f"Give CONTROL_PLANE_BOOTSTRAP_CODE exactly {_SETUP_FIELD_CHARACTERS} characters from {_BOOTSTRAP_ALPHABET} "
    "(separators are ignored), or unset it to get a generated code."
)


def bootstrap_file_path() -> Path:
    return _BOOTSTRAP_FILE_PATH


def _generate_code() -> str:
    chunks = ["".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(chunks)


def _seed_kept_characters(seed: str) -> str:
    """Return the characters of a seed that setup-code matching keeps, upper-cased.

    ``operator_auth._normalize_bootstrap_code`` keeps only ASCII letters and
    digits, on the stored and on the typed side, so separators, punctuation and
    non-ASCII characters add nothing to a seed's secrecy.
    """
    return "".join(ch for ch in seed if ch.isascii() and ch.isalnum()).upper()


def _seed_significant_characters(seed: str) -> int:
    """Count the characters of a seed that setup-code matching keeps."""
    return len(_seed_kept_characters(seed))


def _seed_fits_setup_field(seed: str) -> bool:
    """True when the /setup code field can take the seed: it keeps only characters
    from ``_BOOTSTRAP_ALPHABET``, at most ``_SETUP_FIELD_CHARACTERS`` of them."""
    kept = _seed_kept_characters(seed)
    return 0 < len(kept) <= _SETUP_FIELD_CHARACTERS and all(ch in _BOOTSTRAP_ALPHABET for ch in kept)


def _parse_expires_at(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _render_bootstrap_file(code: str, expires_at: datetime) -> str:
    instruction = "Paste the first line into the Koda setup screen. This file is removed after owner registration."
    return "\n".join(
        (
            code,
            f"expires_at={expires_at.isoformat()}",
            "setup_url=/setup",
            f"instruction={instruction}",
            "",
        )
    )


def _show_setup_code_banner(code: str, expires_at: datetime) -> None:
    """Show a generated setup code once, on stderr, outside the structured log on stdout."""
    rule = "=" * 72
    sys.stderr.write(
        "\n".join(
            (
                rule,
                f"Koda setup code: {code}",
                f"Paste it into /setup before {expires_at.isoformat()}. It is also in {_BOOTSTRAP_FILE_PATH}.",
                "This code is shown once and is not written to the structured log.",
                rule,
                "",
            )
        )
    )
    sys.stderr.flush()


def _read_file_fields() -> tuple[str, datetime | None] | None:
    """Return the code and ``expires_at`` stored on disk; None when there is no readable code file."""
    if not _BOOTSTRAP_FILE_PATH.exists():
        return None
    try:
        content = _BOOTSTRAP_FILE_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        log.warning("bootstrap_file_read_failed", path=str(_BOOTSTRAP_FILE_PATH), error=str(exc))
        return None
    if not content:
        return None
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    code = ""
    expires_at: datetime | None = None
    for line in lines:
        if line.startswith("expires_at="):
            expires_at = _parse_expires_at(line.split("=", 1)[1])
        elif not code and "=" not in line:
            code = line
    return code, expires_at


def ensure_bootstrap_file(*, has_owner: bool, now: datetime | None = None) -> str | None:
    """Write a bootstrap code to disk if one is needed and no valid one exists.

    Returns the plaintext code if a *new* one was written, or None if nothing was
    written. A new generated code is shown once, in a banner on stderr; the
    structured log never carries it. The code expires
    ``CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS`` after the file is written
    (``now``, the current time unless a test injects one).

    Does nothing when:
    - The owner account already exists (and removes a file left over).
    - The file already exists and has not expired (we never overwrite a valid code).
      An expired file is replaced by a new code (D-195); with an env seed the new
      file holds the same seed with a fresh expiry.
    """
    if has_owner:
        if _BOOTSTRAP_FILE_PATH.exists():
            try:
                _BOOTSTRAP_FILE_PATH.unlink()
                log.info("bootstrap_file_removed_owner_exists", path=str(_BOOTSTRAP_FILE_PATH))
            except OSError as exc:
                log.warning("bootstrap_file_unlink_failed", path=str(_BOOTSTRAP_FILE_PATH), error=str(exc))
        return None
    now = now or datetime.now(UTC)
    if _BOOTSTRAP_FILE_PATH.exists():
        fields = _read_file_fields()
        expired_at = fields[1] if fields is not None else None
        if expired_at is None or expired_at > now:
            return None
        try:
            _BOOTSTRAP_FILE_PATH.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("bootstrap_file_unlink_failed", path=str(_BOOTSTRAP_FILE_PATH), error=str(exc))
            return None
        log.info("bootstrap_file_expired_replaced", path=str(_BOOTSTRAP_FILE_PATH), expired_at=expired_at.isoformat())
    _BOOTSTRAP_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    code = CONTROL_PLANE_BOOTSTRAP_CODE_SEED or _generate_code()
    expires_at = now + timedelta(seconds=CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS)
    try:
        fd = os.open(
            str(_BOOTSTRAP_FILE_PATH),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return None
    try:
        os.write(fd, _render_bootstrap_file(code, expires_at).encode())
    finally:
        os.close(fd)
    with contextlib.suppress(OSError):
        os.chmod(str(_BOOTSTRAP_FILE_PATH), 0o600)
    if CONTROL_PLANE_BOOTSTRAP_CODE_SEED:
        # The operator chose the seed and knows it: say where the code came from, never the code.
        log.info(
            "bootstrap_file_written",
            path=str(_BOOTSTRAP_FILE_PATH),
            code_source="CONTROL_PLANE_BOOTSTRAP_CODE",
            expires_at=expires_at.isoformat(),
        )
    else:
        log.info(
            "bootstrap_file_written",
            path=str(_BOOTSTRAP_FILE_PATH),
            code_source="generated",
            expires_at=expires_at.isoformat(),
        )
        _show_setup_code_banner(code, expires_at)
    if CONTROL_PLANE_BOOTSTRAP_CODE_SEED:
        significant = _seed_significant_characters(CONTROL_PLANE_BOOTSTRAP_CODE_SEED)
        if significant < _SEED_MIN_SIGNIFICANT_CHARACTERS:
            log.warning(
                "bootstrap_code_seed_weak",
                significant_characters=significant,
                minimum=_SEED_MIN_SIGNIFICANT_CHARACTERS,
                hint=f"Setup codes match on ASCII letters and digits only. {_SEED_ADVICE}",
            )
        if not _seed_fits_setup_field(CONTROL_PLANE_BOOTSTRAP_CODE_SEED):
            log.warning(
                "bootstrap_code_seed_not_typeable",
                significant_characters=significant,
                setup_field_characters=_SETUP_FIELD_CHARACTERS,
                hint=(
                    f"The /setup code field keeps at most {_SETUP_FIELD_CHARACTERS} characters from "
                    f"{_BOOTSTRAP_ALPHABET} and drops any other, so this seed works only through the API "
                    f"(POST /api/control-plane/auth/register-owner). {_SEED_ADVICE}"
                ),
            )
    return code


def read_bootstrap_file(*, now: datetime | None = None) -> str | None:
    """Return the bootstrap code stored on disk, if any and not expired by ``now``."""
    fields = _read_file_fields()
    if fields is None:
        return None
    code, expires_at = fields
    if expires_at is not None and expires_at <= (now or datetime.now(UTC)):
        log.info("bootstrap_file_expired", path=str(_BOOTSTRAP_FILE_PATH), expires_at=expires_at.isoformat())
        return None
    return code or None


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
