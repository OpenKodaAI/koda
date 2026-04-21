"""Operator authentication, bootstrap codes, sessions, and personal tokens."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hmac import compare_digest
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from koda.services.audit import emit_security

from .bootstrap_file import (
    bootstrap_file_path,
    consume_bootstrap_file,
    ensure_bootstrap_file,
    is_loopback_request,
    read_bootstrap_file,
)
from .database import execute, fetch_all, fetch_one, json_dump, json_load, now_iso
from .password_policy import PasswordPolicyError, validate_password
from .settings import (
    ALLOW_LOOPBACK_BOOTSTRAP,
    CONTROL_PLANE_API_TOKENS,
    CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS,
    CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS,
    CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES,
    CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH,
    CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS,
    CONTROL_PLANE_OPERATOR_TOKEN_TTL_DAYS,
    CONTROL_PLANE_RECOVERY_CODES_PER_USER,
    CONTROL_PLANE_REGISTRATION_TOKEN_TTL_SECONDS,
)

_BOOTSTRAP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_BOOTSTRAP_INSERT_ATTEMPTS = 5
_PASSWORD_MIN_LENGTH = CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH
_FAILURE_TIMING_FLOOR_SECONDS = 0.3


@dataclass(slots=True)
class OperatorAuthContext:
    auth_kind: str
    subject_type: str
    user_id: str | None
    username: str | None
    email: str | None
    display_name: str | None
    session_id: str | None = None
    token_id: str | None = None
    scopes: tuple[str, ...] = ()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _is_expired(value: Any) -> bool:
    dt = _parse_iso(value)
    if dt is None:
        return False
    return dt <= _utc_now()


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _random_secret(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _random_code() -> str:
    chunks = [
        "".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)),
        "".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)),
        "".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)),
    ]
    return "-".join(chunks)


def _random_recovery_code() -> str:
    chunks = [
        "".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)),
        "".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)),
        "".join(secrets.choice(_BOOTSTRAP_ALPHABET) for _ in range(4)),
    ]
    return "-".join(chunks).lower()


def _pad_failure_timing(started_at: float) -> None:
    """Sleep until at least `_FAILURE_TIMING_FLOOR_SECONDS` have elapsed.

    Neutralizes timing side-channels between "user not found", "wrong password"
    and "recovery code invalid" code paths.
    """
    elapsed = time.monotonic() - started_at
    remaining = _FAILURE_TIMING_FLOOR_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)


@lru_cache(maxsize=1)
def _password_hasher() -> PasswordHasher:
    return PasswordHasher()


def _normalize_username(value: Any) -> str:
    normalized = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"_", ".", "-"})
    return normalized[:64]


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()[:254]


def _safe_text(value: Any, *, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _optional_audit_user_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class OperatorAuthService:
    """Stateful operator auth service backed by control-plane tables."""

    def has_owner(self) -> bool:
        return fetch_one("SELECT id FROM cp_operator_users ORDER BY created_at ASC LIMIT 1") is not None

    def _owner_row(self) -> Any | None:
        return fetch_one("SELECT * FROM cp_operator_users ORDER BY created_at ASC LIMIT 1")

    def _row_to_operator(self, row: Any | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "username": str(row["username"]),
            "email": str(row["email"]),
            "display_name": str(row.get("display_name") or row["username"]),
            "role": str(row.get("role") or "owner"),
            "last_login_at": str(row.get("last_login_at") or "") or None,
        }

    def onboarding_payload(self) -> dict[str, Any]:
        has_owner = self.has_owner()
        generated_code = ensure_bootstrap_file(has_owner=has_owner)
        if generated_code:
            emit_security("security.operator_bootstrap_file_written", path=str(bootstrap_file_path()))
        return {
            "has_owner": has_owner,
            "bootstrap_required": not has_owner,
            "auth_mode": "local_account",
            "session_required": has_owner,
            "recovery_available": has_owner,
            "bootstrap_file_path": str(bootstrap_file_path()) if not has_owner else "",
            "loopback_trust_enabled": ALLOW_LOOPBACK_BOOTSTRAP and not has_owner,
        }

    def auth_status(self, context: OperatorAuthContext | None = None) -> dict[str, Any]:
        payload = self.onboarding_payload()
        authenticated = context is not None
        has_owner = bool(payload.get("has_owner"))
        payload.update(
            {
                "authenticated": authenticated,
                "onboarding_complete": has_owner and authenticated,
                "session_subject": context.subject_type if context else None,
                "operator": (
                    {
                        "id": context.user_id,
                        "username": context.username,
                        "email": context.email,
                        "display_name": context.display_name or context.username or "Operator",
                    }
                    if context and context.user_id
                    else None
                ),
            }
        )
        return payload

    def issue_bootstrap_code(self, *, label: str = "cli", actor: str | None = None) -> dict[str, Any]:
        now = _utc_now()
        expires_at = now + timedelta(seconds=CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS)
        code = ""
        last_error: Exception | None = None
        for _ in range(_BOOTSTRAP_INSERT_ATTEMPTS):
            code = _random_code()
            bootstrap_id = f"boot_{uuid4().hex}"
            code_hash = _hash_secret(code)
            issued_at = now_iso()
            try:
                inserted = execute(
                    """
                    INSERT INTO cp_bootstrap_codes (
                        id,
                        code_hash,
                        code_hint,
                        purpose,
                        created_at,
                        expires_at,
                        issued_by,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        bootstrap_id,
                        code_hash,
                        code[-4:],
                        "owner_setup",
                        issued_at,
                        expires_at.isoformat(),
                        _safe_text(actor),
                        json_dump({"label": _safe_text(label)}),
                    ),
                )
            except Exception as exc:
                message = str(exc).lower()
                if "code_hash" in message and "unique" in message:
                    last_error = exc
                    continue
                raise

            if inserted:
                break

            existing = fetch_one("SELECT * FROM cp_bootstrap_codes WHERE id = ?", (bootstrap_id,))
            if existing is not None and str(existing.get("code_hash") or "") == code_hash:
                break
        else:
            raise RuntimeError("Could not issue a setup code. Please retry.") from last_error

        emit_security("security.operator_bootstrap_code_issued", actor=actor, label=label)
        return {
            "ok": True,
            "code": code,
            "expires_at": expires_at.isoformat(),
            "label": _safe_text(label),
        }

    def exchange_bootstrap_code(self, code: str) -> dict[str, Any]:
        if self.has_owner():
            raise ValueError("Owner account already exists. Sign in instead.")
        normalized = str(code or "").strip().upper()
        if not normalized:
            raise ValueError("Setup code is required.")
        row = fetch_one("SELECT * FROM cp_bootstrap_codes WHERE code_hash = ?", (_hash_secret(normalized),))
        if row is None or _is_expired(row.get("expires_at")) or row.get("consumed_at"):
            emit_security("security.operator_bootstrap_exchange_failed", reason="invalid_or_expired_code")
            raise ValueError("Setup code is invalid or expired.")
        registration_token = _random_secret("kodar")
        exchange_expires_at = (_utc_now() + timedelta(seconds=CONTROL_PLANE_REGISTRATION_TOKEN_TTL_SECONDS)).isoformat()
        execute(
            """
            UPDATE cp_bootstrap_codes
            SET consumed_at = ?, exchange_token_hash = ?, exchange_issued_at = ?, exchange_expires_at = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                _hash_secret(registration_token),
                now_iso(),
                exchange_expires_at,
                str(row["id"]),
            ),
        )
        emit_security("security.operator_bootstrap_exchanged", code_hint=str(row.get("code_hint") or ""))
        return {
            "ok": True,
            "registration_token": registration_token,
            "expires_at": exchange_expires_at,
        }

    def _registration_row(self, registration_token: str) -> Any | None:
        token_hash = _hash_secret(str(registration_token or "").strip())
        if not token_hash:
            return None
        return fetch_one("SELECT * FROM cp_bootstrap_codes WHERE exchange_token_hash = ?", (token_hash,))

    def _create_session(
        self,
        *,
        user_id: str | None,
        subject_type: str,
        label: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, OperatorAuthContext]:
        session_token = _random_secret("kodas")
        session_id = f"sess_{uuid4().hex}"
        now = _utc_now()
        expires_at = now + timedelta(seconds=CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS)
        execute(
            """
            INSERT INTO cp_operator_sessions (
                session_id,
                user_id,
                token_hash,
                subject_type,
                label,
                created_at,
                last_used_at,
                expires_at,
                revoked_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_id,
                _hash_secret(session_token),
                subject_type,
                _safe_text(label),
                now.isoformat(),
                now.isoformat(),
                expires_at.isoformat(),
                "",
                json_dump(metadata or {}),
            ),
        )
        row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (user_id,)) if user_id else None
        return session_token, OperatorAuthContext(
            auth_kind="session",
            subject_type=subject_type,
            user_id=str(row["id"]) if row else None,
            username=str(row["username"]) if row else None,
            email=str(row["email"]) if row else None,
            display_name=str(row.get("display_name") or row["username"]) if row else "Break Glass",
            session_id=session_id,
        )

    def register_owner(
        self,
        *,
        email: str,
        password: str,
        username: str = "",
        display_name: str = "",
        bootstrap_code: str = "",
        registration_token: str = "",
        remote_ip: str | None = None,
        forwarded_for: str | None = None,
    ) -> dict[str, Any]:
        """Create the first owner account.

        Accepts any ONE of three authentication mechanisms, checked in priority:
        - a valid `registration_token` previously obtained via `exchange_bootstrap_code`
          (legacy flow, still supported);
        - a `bootstrap_code` matching either the env seed or the on-disk bootstrap file;
        - a trusted loopback request (when `ALLOW_LOOPBACK_BOOTSTRAP=true` and the
          request comes from 127.0.0.1/::1 without a proxy hop).

        On success, generates N one-time recovery codes and returns them in plaintext
        as part of the response. They are never retrievable again.
        """
        started_at = time.monotonic()
        if self.has_owner():
            _pad_failure_timing(started_at)
            raise ValueError("Owner account already exists. Sign in instead.")

        authentication_mode = self._authenticate_registration(
            bootstrap_code=bootstrap_code,
            registration_token=registration_token,
            remote_ip=remote_ip,
            forwarded_for=forwarded_for,
        )
        if authentication_mode is None:
            _pad_failure_timing(started_at)
            emit_security("security.operator_owner_register_rejected", reason="no_valid_bootstrap")
            raise ValueError("Bootstrap code is invalid or expired.")

        normalized_email = _normalize_email(email)
        if "@" not in normalized_email:
            raise ValueError("A valid email is required.")
        derived_username = username.strip() if username and username.strip() else normalized_email.split("@", 1)[0]
        normalized_username = _normalize_username(derived_username)
        if not normalized_username:
            raise ValueError("Username is required.")
        try:
            validate_password(
                password,
                min_length=_PASSWORD_MIN_LENGTH,
                username=normalized_username,
                email=normalized_email,
            )
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc

        existing = fetch_one(
            "SELECT id FROM cp_operator_users WHERE lower(username) = lower(?) OR lower(email) = lower(?)",
            (normalized_username, normalized_email),
        )
        if existing is not None:
            raise ValueError("Username or email already exists.")
        password_hash = _password_hasher().hash(password)
        user_id = f"usr_{uuid4().hex}"
        generation = uuid4().hex
        try:
            execute(
                """
                INSERT INTO cp_operator_users (
                    id,
                    username,
                    email,
                    display_name,
                    password_hash,
                    role,
                    created_at,
                    updated_at,
                    last_login_at,
                    failed_login_attempts,
                    locked_until,
                    disabled,
                    totp_secret,
                    recovery_generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    normalized_username,
                    normalized_email,
                    _safe_text(display_name or normalized_username),
                    password_hash,
                    "owner",
                    now_iso(),
                    now_iso(),
                    now_iso(),
                    0,
                    "",
                    0,
                    "",
                    generation,
                ),
            )
        except Exception as exc:
            # Two scenarios collapse into the same message so we don't leak
            # whether the collision was on id, username, or email: a concurrent
            # register_owner (double-submit), or stale state left by a prior
            # half-finished attempt. Either way the operator should sign in.
            message = str(exc).lower()
            if "duplicate" in message or "unique" in message or "unique_violation" in message:
                raise ValueError("Owner account already exists. Sign in instead.") from exc
            raise
        try:
            plaintext_codes = self._issue_recovery_codes(user_id=user_id, generation=generation)
        except Exception:
            # Recovery-code insertion failed AFTER the user row was committed —
            # roll it back so the operator can retry from a clean slate instead
            # of being locked out by a half-provisioned account.
            execute("DELETE FROM cp_operator_users WHERE id = ?", (user_id,))
            raise
        if authentication_mode == "registration_token" and registration_token:
            row = self._registration_row(registration_token)
            if row is not None:
                execute(
                    "UPDATE cp_bootstrap_codes SET exchange_consumed_at = ? WHERE id = ?",
                    (now_iso(), str(row["id"])),
                )
        if authentication_mode == "bootstrap_file":
            consume_bootstrap_file()
        session_token, context = self._create_session(
            user_id=user_id,
            subject_type="operator",
            label="web_owner_registration",
            metadata={"origin": "register_owner", "bootstrap_mode": authentication_mode},
        )
        emit_security(
            "security.operator_owner_registered",
            user_id=_optional_audit_user_id(user_id),
            username=normalized_username,
            bootstrap_mode=authentication_mode,
        )
        return {
            "ok": True,
            "operator": self._row_to_operator(fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (user_id,))),
            "session_token": session_token,
            "recovery_codes": plaintext_codes,
            "auth": self.auth_status(context),
        }

    def _authenticate_registration(
        self,
        *,
        bootstrap_code: str,
        registration_token: str,
        remote_ip: str | None,
        forwarded_for: str | None,
    ) -> str | None:
        """Return the authentication mode used, or None if none are valid."""
        trimmed_token = str(registration_token or "").strip()
        if trimmed_token:
            row = self._registration_row(trimmed_token)
            if (
                row is not None
                and not row.get("exchange_consumed_at")
                and not _is_expired(row.get("exchange_expires_at"))
            ):
                return "registration_token"
        trimmed_code = str(bootstrap_code or "").strip().upper()
        if trimmed_code:
            file_code = read_bootstrap_file()
            if file_code and compare_digest(trimmed_code, file_code.strip().upper()):
                return "bootstrap_file"
        if ALLOW_LOOPBACK_BOOTSTRAP and is_loopback_request(remote_ip, forwarded_for):
            emit_security("security.operator_bootstrap_loopback_trust_used", remote_ip=str(remote_ip or ""))
            return "loopback_trust"
        return None

    def _issue_recovery_codes(self, *, user_id: str, generation: str) -> list[str]:
        """Generate N fresh recovery codes, persist their Argon2 hashes, return plaintext."""
        import time as _time_mod

        hasher = _password_hasher()
        plaintext_codes: list[str] = []
        timestamp = now_iso()
        count = max(1, CONTROL_PLANE_RECOVERY_CODES_PER_USER)
        rows: list[tuple[Any, ...]] = []
        for _ in range(count):
            code = _random_recovery_code()
            plaintext_codes.append(code)
            rows.append(
                (
                    f"rec_{uuid4().hex}",
                    user_id,
                    hasher.hash(code),
                    code[-4:],
                    timestamp,
                    "",
                    "",
                    generation,
                )
            )
        # Batch into a single multi-values INSERT so the async bridge makes one
        # trip to Postgres instead of N. That avoids connection-reset races in
        # the pool when code generation runs back-to-back on the request path.
        values_sql = ", ".join(["(?, ?, ?, ?, ?, ?, ?, ?)"] * count)
        flat_params: tuple[Any, ...] = tuple(value for row in rows for value in row)
        query = f"""
            INSERT INTO cp_operator_recovery_codes (
                id, user_id, code_hash, code_hint, created_at,
                consumed_at, consumed_reason, generation
            ) VALUES {values_sql}
        """
        # Retry on transient asyncpg connection races. The first INSERT often
        # loses to the concurrent audit/pool release path; subsequent attempts
        # get a fresh connection and succeed.
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                execute(query, flat_params)
                return plaintext_codes
            except Exception as exc:  # noqa: BLE001 — asyncpg errors are unstable across versions
                last_error = exc
                message = str(exc).lower()
                if (
                    "another operation is in progress" in message
                    or "connection was closed" in message
                    or "connection is closed" in message
                    or "different loop" in message
                ):
                    _time_mod.sleep(0.1 * (attempt + 1))
                    continue
                raise
        if last_error is not None:
            raise last_error
        return plaintext_codes

    def _set_login_failure(self, row: Any | None, *, identifier: str) -> None:
        if row is None:
            emit_security("security.operator_login_failed", identifier=identifier, reason="user_not_found")
            return
        attempts = int(row.get("failed_login_attempts") or 0) + 1
        locked_until = ""
        if attempts >= CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES:
            attempts = 0
            locked_until = (_utc_now() + timedelta(seconds=CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS)).isoformat()
        execute(
            "UPDATE cp_operator_users SET failed_login_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?",
            (attempts, locked_until, now_iso(), str(row["id"])),
        )
        emit_security(
            "security.operator_login_failed",
            identifier=identifier,
            user_id=_optional_audit_user_id(row["id"]),
        )

    def login(self, *, identifier: str, password: str) -> dict[str, Any]:
        started_at = time.monotonic()
        normalized = str(identifier or "").strip()
        if not normalized or not password:
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.")
        row = fetch_one(
            """
            SELECT * FROM cp_operator_users
            WHERE lower(username) = lower(?) OR lower(email) = lower(?)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (normalized, normalized),
        )
        if row is None:
            self._set_login_failure(None, identifier=normalized)
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.")
        if row.get("disabled"):
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.")
        if row.get("locked_until") and not _is_expired(row.get("locked_until")):
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.")
        try:
            _password_hasher().verify(str(row["password_hash"]), password)
        except (VerifyMismatchError, VerificationError, InvalidHashError) as exc:
            self._set_login_failure(row, identifier=normalized)
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.") from exc
        execute(
            """
            UPDATE cp_operator_users
            SET failed_login_attempts = 0, locked_until = '', last_login_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), now_iso(), str(row["id"])),
        )
        session_token, context = self._create_session(
            user_id=str(row["id"]),
            subject_type="operator",
            label="web_login",
            metadata={"origin": "login"},
        )
        emit_security("security.operator_login_succeeded", user_id=_optional_audit_user_id(row["id"]))
        return {
            "ok": True,
            "operator": self._row_to_operator(
                fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (str(row["id"]),))
            ),
            "session_token": session_token,
            "auth": self.auth_status(context),
        }

    def change_password(
        self,
        context: OperatorAuthContext,
        *,
        current_password: str,
        new_password: str,
    ) -> dict[str, Any]:
        """Change the authenticated user's password.

        Revokes every OTHER session (keeping the current one) and leaves existing
        recovery codes intact — the operator still has their printed sheet.
        """
        if not context.user_id:
            raise ValueError("Operator session is required.")
        started_at = time.monotonic()
        row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (context.user_id,))
        if row is None:
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.")
        try:
            _password_hasher().verify(str(row["password_hash"]), current_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError) as exc:
            _pad_failure_timing(started_at)
            emit_security(
                "security.operator_password_change_failed",
                user_id=_optional_audit_user_id(context.user_id),
            )
            raise ValueError("Invalid credentials.") from exc
        try:
            validate_password(
                new_password,
                min_length=_PASSWORD_MIN_LENGTH,
                username=str(row.get("username") or ""),
                email=str(row.get("email") or ""),
            )
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc
        new_hash = _password_hasher().hash(new_password)
        execute(
            "UPDATE cp_operator_users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, now_iso(), context.user_id),
        )
        if context.session_id:
            execute(
                """
                UPDATE cp_operator_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND session_id != ? AND revoked_at = ''
                """,
                (now_iso(), context.user_id, context.session_id),
            )
        else:
            execute(
                "UPDATE cp_operator_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = ''",
                (now_iso(), context.user_id),
            )
        emit_security(
            "security.operator_password_changed",
            user_id=_optional_audit_user_id(context.user_id),
        )
        return {"ok": True}

    def reset_password_with_recovery_code(
        self,
        *,
        identifier: str,
        recovery_code: str,
        new_password: str,
    ) -> dict[str, Any]:
        """Reset a password using a one-time recovery code.

        Revokes ALL existing sessions and invalidates ALL remaining recovery
        codes for the user (Google/GitHub style). User must regenerate a fresh
        set from the dashboard afterwards.

        Returns the same generic success payload regardless of which lookup
        failed, to avoid leaking user existence.
        """
        started_at = time.monotonic()
        normalized_identifier = str(identifier or "").strip()
        trimmed_code = str(recovery_code or "").strip().lower()
        if not normalized_identifier or not trimmed_code or not new_password:
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials or recovery code.")
        row = fetch_one(
            """
            SELECT * FROM cp_operator_users
            WHERE lower(username) = lower(?) OR lower(email) = lower(?)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (normalized_identifier, normalized_identifier),
        )
        if row is None:
            _pad_failure_timing(started_at)
            emit_security(
                "security.operator_password_reset_failed",
                reason="identifier_not_found",
            )
            raise ValueError("Invalid credentials or recovery code.")
        user_id = str(row["id"])
        generation = str(row.get("recovery_generation") or "")
        codes = fetch_all(
            """
            SELECT id, code_hash FROM cp_operator_recovery_codes
            WHERE user_id = ? AND consumed_at = '' AND generation = ?
            ORDER BY created_at ASC
            """,
            (user_id, generation),
        )
        hasher = _password_hasher()
        matched_id: str | None = None
        for entry in codes:
            try:
                if hasher.verify(str(entry["code_hash"]), trimmed_code):
                    matched_id = str(entry["id"])
                    break
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                continue
        if matched_id is None:
            _pad_failure_timing(started_at)
            emit_security(
                "security.operator_password_reset_failed",
                user_id=_optional_audit_user_id(user_id),
                reason="recovery_code_invalid",
            )
            raise ValueError("Invalid credentials or recovery code.")
        try:
            validate_password(
                new_password,
                min_length=_PASSWORD_MIN_LENGTH,
                username=str(row.get("username") or ""),
                email=str(row.get("email") or ""),
            )
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc
        new_hash = hasher.hash(new_password)
        timestamp = now_iso()
        execute(
            "UPDATE cp_operator_users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, timestamp, user_id),
        )
        execute(
            "UPDATE cp_operator_recovery_codes SET consumed_at = ?, consumed_reason = ? WHERE id = ?",
            (timestamp, "password_reset", matched_id),
        )
        execute(
            """
            UPDATE cp_operator_recovery_codes
            SET consumed_at = ?, consumed_reason = ?
            WHERE user_id = ? AND consumed_at = '' AND generation = ?
            """,
            (timestamp, "password_reset_invalidation", user_id, generation),
        )
        execute(
            """
            UPDATE cp_operator_sessions
            SET revoked_at = ?
            WHERE user_id = ? AND revoked_at = ''
            """,
            (timestamp, user_id),
        )
        emit_security(
            "security.operator_password_reset",
            user_id=_optional_audit_user_id(user_id),
        )
        return {"ok": True}

    def regenerate_recovery_codes(
        self,
        context: OperatorAuthContext,
        *,
        current_password: str,
    ) -> dict[str, Any]:
        """Issue a fresh batch of recovery codes; invalidates any previous codes."""
        if not context.user_id:
            raise ValueError("Operator session is required.")
        started_at = time.monotonic()
        row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (context.user_id,))
        if row is None:
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.")
        try:
            _password_hasher().verify(str(row["password_hash"]), current_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError) as exc:
            _pad_failure_timing(started_at)
            raise ValueError("Invalid credentials.") from exc
        timestamp = now_iso()
        execute(
            """
            UPDATE cp_operator_recovery_codes
            SET consumed_at = ?, consumed_reason = ?
            WHERE user_id = ? AND consumed_at = ''
            """,
            (timestamp, "regenerated", context.user_id),
        )
        new_generation = uuid4().hex
        execute(
            "UPDATE cp_operator_users SET recovery_generation = ?, updated_at = ? WHERE id = ?",
            (new_generation, timestamp, context.user_id),
        )
        plaintext = self._issue_recovery_codes(user_id=context.user_id, generation=new_generation)
        emit_security(
            "security.operator_recovery_codes_regenerated",
            user_id=_optional_audit_user_id(context.user_id),
        )
        return {"ok": True, "recovery_codes": plaintext, "generated_at": timestamp}

    def recovery_codes_summary(self, context: OperatorAuthContext) -> dict[str, Any]:
        """Summary without revealing the codes themselves."""
        if not context.user_id:
            raise ValueError("Operator session is required.")
        row = fetch_one(
            """
            SELECT recovery_generation FROM cp_operator_users WHERE id = ?
            """,
            (context.user_id,),
        )
        generation = str(row.get("recovery_generation") or "") if row else ""
        total_row = fetch_one(
            "SELECT COUNT(*) AS count FROM cp_operator_recovery_codes WHERE user_id = ? AND generation = ?",
            (context.user_id, generation),
        )
        remaining_row = fetch_one(
            """
            SELECT COUNT(*) AS count FROM cp_operator_recovery_codes
            WHERE user_id = ? AND consumed_at = '' AND generation = ?
            """,
            (context.user_id, generation),
        )
        created_row = fetch_one(
            """
            SELECT created_at FROM cp_operator_recovery_codes
            WHERE user_id = ? AND generation = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (context.user_id, generation),
        )
        return {
            "total": int((total_row or {}).get("count") or 0),
            "remaining": int((remaining_row or {}).get("count") or 0),
            "generated_at": str((created_row or {}).get("created_at") or "") or None,
        }

    def logout(self, bearer_token: str) -> dict[str, Any]:
        token_hash = _hash_secret(str(bearer_token or "").strip())
        execute(
            "UPDATE cp_operator_sessions SET revoked_at = ?, last_used_at = ? WHERE token_hash = ?",
            (now_iso(), now_iso(), token_hash),
        )
        emit_security("security.operator_logout")
        return {"ok": True}

    def _context_from_user_row(
        self,
        row: Any,
        *,
        auth_kind: str,
        subject_type: str,
        session_id: str | None = None,
        token_id: str | None = None,
    ) -> OperatorAuthContext:
        return OperatorAuthContext(
            auth_kind=auth_kind,
            subject_type=subject_type,
            user_id=str(row["id"]),
            username=str(row["username"]),
            email=str(row["email"]),
            display_name=str(row.get("display_name") or row["username"]),
            session_id=session_id,
            token_id=token_id,
        )

    def resolve_bearer_token(self, token: str, *, touch: bool = True) -> OperatorAuthContext | None:
        provided = str(token or "").strip()
        if not provided:
            return None
        if any(compare_digest(provided, configured) for configured in CONTROL_PLANE_API_TOKENS):
            owner = self._owner_row()
            if owner is not None:
                return self._context_from_user_row(owner, auth_kind="cli_bootstrap", subject_type="cli_bootstrap")
            return OperatorAuthContext(
                auth_kind="cli_bootstrap",
                subject_type="cli_bootstrap",
                user_id=None,
                username=None,
                email=None,
                display_name="CLI Bootstrap",
            )
        token_hash = _hash_secret(provided)
        session_row = fetch_one(
            """
            SELECT * FROM cp_operator_sessions
            WHERE token_hash = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (token_hash,),
        )
        if (
            session_row is not None
            and not session_row.get("revoked_at")
            and not _is_expired(session_row.get("expires_at"))
        ):
            user_id = str(session_row.get("user_id") or "") or None
            if touch:
                execute(
                    "UPDATE cp_operator_sessions SET last_used_at = ? WHERE session_id = ?",
                    (now_iso(), str(session_row["session_id"])),
                )
            if user_id:
                row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (user_id,))
                if row is not None:
                    return self._context_from_user_row(
                        row,
                        auth_kind="session",
                        subject_type=str(session_row.get("subject_type") or "operator"),
                        session_id=str(session_row["session_id"]),
                    )
            return OperatorAuthContext(
                auth_kind="session",
                subject_type=str(session_row.get("subject_type") or "break_glass"),
                user_id=None,
                username=None,
                email=None,
                display_name="Break Glass",
                session_id=str(session_row["session_id"]),
            )
        token_row = fetch_one(
            """
            SELECT * FROM cp_operator_tokens
            WHERE token_hash = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (token_hash,),
        )
        if token_row is None or token_row.get("revoked_at") or _is_expired(token_row.get("expires_at")):
            return None
        if touch:
            execute(
                "UPDATE cp_operator_tokens SET last_used_at = ? WHERE id = ?",
                (now_iso(), str(token_row["id"])),
            )
        user_row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (str(token_row["user_id"]),))
        if user_row is None:
            return None
        return self._context_from_user_row(
            user_row,
            auth_kind="api_token",
            subject_type="api_token",
            token_id=str(token_row["id"]),
        )

    def issue_personal_token(
        self,
        context: OperatorAuthContext,
        *,
        token_name: str,
        expires_in_days: int | None = None,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        raw_token = _random_secret("kpat")
        token_id = f"tok_{uuid4().hex}"
        expires_at = None
        if expires_in_days is None:
            expires_in_days = CONTROL_PLANE_OPERATOR_TOKEN_TTL_DAYS
        if expires_in_days > 0:
            expires_at = (_utc_now() + timedelta(days=expires_in_days)).isoformat()
        execute(
            """
            INSERT INTO cp_operator_tokens (
                id,
                user_id,
                token_name,
                token_hash,
                token_prefix,
                scopes_json,
                created_at,
                last_used_at,
                expires_at,
                revoked_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_id,
                context.user_id,
                _safe_text(token_name or "CLI token"),
                _hash_secret(raw_token),
                raw_token[:16],
                json_dump(scopes or ["control_plane"]),
                now_iso(),
                "",
                expires_at or "",
                "",
                json_dump({}),
            ),
        )
        emit_security(
            "security.operator_token_created",
            user_id=_optional_audit_user_id(context.user_id),
            token_id=token_id,
        )
        return {
            "id": token_id,
            "token_name": _safe_text(token_name or "CLI token"),
            "token": raw_token,
            "token_prefix": raw_token[:16],
            "expires_at": expires_at,
            "scopes": scopes or ["control_plane"],
        }

    def list_personal_tokens(self, context: OperatorAuthContext) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        rows = fetch_all(
            "SELECT * FROM cp_operator_tokens WHERE user_id = ? ORDER BY created_at DESC",
            (context.user_id,),
        )
        return {
            "items": [
                {
                    "id": str(row["id"]),
                    "token_name": str(row.get("token_name") or "CLI token"),
                    "token_prefix": str(row.get("token_prefix") or ""),
                    "scopes": json_load(row.get("scopes_json"), []),
                    "created_at": str(row.get("created_at") or ""),
                    "last_used_at": str(row.get("last_used_at") or "") or None,
                    "expires_at": str(row.get("expires_at") or "") or None,
                    "revoked_at": str(row.get("revoked_at") or "") or None,
                }
                for row in rows
            ]
        }

    def revoke_personal_token(self, context: OperatorAuthContext, token_id: str) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        execute(
            "UPDATE cp_operator_tokens SET revoked_at = ? WHERE id = ? AND user_id = ?",
            (now_iso(), _safe_text(token_id), context.user_id),
        )
        emit_security(
            "security.operator_token_revoked",
            user_id=_optional_audit_user_id(context.user_id),
            token_id=token_id,
        )
        return {"ok": True}

    def list_sessions(self, context: OperatorAuthContext) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        rows = fetch_all(
            "SELECT * FROM cp_operator_sessions WHERE user_id = ? ORDER BY created_at DESC",
            (context.user_id,),
        )
        return {
            "items": [
                {
                    "session_id": str(row["session_id"]),
                    "subject_type": str(row.get("subject_type") or "operator"),
                    "label": str(row.get("label") or ""),
                    "created_at": str(row.get("created_at") or ""),
                    "last_used_at": str(row.get("last_used_at") or "") or None,
                    "expires_at": str(row.get("expires_at") or "") or None,
                    "revoked_at": str(row.get("revoked_at") or "") or None,
                    "is_current": str(row["session_id"]) == str(context.session_id or ""),
                }
                for row in rows
            ]
        }

    def revoke_session(self, context: OperatorAuthContext, session_id: str) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        execute(
            "UPDATE cp_operator_sessions SET revoked_at = ? WHERE session_id = ? AND user_id = ?",
            (now_iso(), _safe_text(session_id), context.user_id),
        )
        emit_security(
            "security.operator_session_revoked",
            user_id=_optional_audit_user_id(context.user_id),
            session_id=session_id,
        )
        return {"ok": True}


@lru_cache(maxsize=1)
def get_operator_auth_service() -> OperatorAuthService:
    return OperatorAuthService()
