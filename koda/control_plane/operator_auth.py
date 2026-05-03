"""Operator authentication, bootstrap codes, sessions, and personal tokens."""

from __future__ import annotations

import hashlib
import secrets
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
from .password_policy import validate_password
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
_FAILURE_TIMING_FLOOR_SECONDS = 0.0


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


def _normalize_bootstrap_code(value: Any) -> str:
    return str(value or "").strip().upper()


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
        ensure_bootstrap_file(has_owner=has_owner)
        return {
            "has_owner": has_owner,
            "bootstrap_required": not has_owner,
            "auth_mode": "local_account",
            "session_required": has_owner,
            "recovery_available": bool(CONTROL_PLANE_API_TOKENS),
            "loopback_trust_enabled": ALLOW_LOOPBACK_BOOTSTRAP,
            "bootstrap_file_path": str(bootstrap_file_path()),
            "onboarding_complete": has_owner,
        }

    def auth_status(self, context: OperatorAuthContext | None = None) -> dict[str, Any]:
        payload = self.onboarding_payload()
        payload.update(
            {
                "authenticated": context is not None,
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

    def _insert_bootstrap_code(
        self,
        *,
        code: str,
        label: str,
        actor: str | None = None,
        expires_at: datetime | None = None,
    ) -> Any | None:
        now = _utc_now()
        bootstrap_id = f"boot_{uuid4().hex}"
        normalized = _normalize_bootstrap_code(code)
        execute(
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
                _hash_secret(normalized),
                normalized[-4:],
                "owner_setup",
                now.isoformat(),
                (expires_at or now + timedelta(seconds=CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS)).isoformat(),
                _safe_text(actor),
                json_dump({"label": _safe_text(label)}),
            ),
        )
        return fetch_one("SELECT * FROM cp_bootstrap_codes WHERE code_hash = ?", (_hash_secret(normalized),))

    def _bootstrap_file_matches(self, code: str) -> bool:
        file_code = read_bootstrap_file()
        if not file_code:
            return False
        return compare_digest(_normalize_bootstrap_code(file_code), _normalize_bootstrap_code(code))

    def exchange_bootstrap_code(self, code: str) -> dict[str, Any]:
        if self.has_owner():
            raise ValueError("Owner account already exists. Sign in instead.")
        normalized = _normalize_bootstrap_code(code)
        if not normalized:
            raise ValueError("Setup code is required.")
        row = fetch_one("SELECT * FROM cp_bootstrap_codes WHERE code_hash = ?", (_hash_secret(normalized),))
        if row is None and self._bootstrap_file_matches(normalized):
            row = self._insert_bootstrap_code(code=normalized, label="bootstrap_file")
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

    def _validate_operator_password(self, password: str, *, username: str, email: str) -> None:
        validate_password(
            password,
            min_length=CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH,
            username=username,
            email=email,
        )

    def _issue_recovery_codes(self, *, user_id: str, generation: str) -> list[str]:
        count = max(1, int(CONTROL_PLANE_RECOVERY_CODES_PER_USER or 10))
        issued_at = now_iso()
        codes: list[str] = []
        for _ in range(count):
            code = _random_code()
            codes.append(code)
            execute(
                """
                INSERT INTO cp_operator_recovery_codes (
                    id,
                    user_id,
                    code_hash,
                    code_hint,
                    created_at,
                    consumed_at,
                    consumed_reason,
                    generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"rec_{uuid4().hex}",
                    user_id,
                    _hash_secret(code),
                    code[-4:],
                    issued_at,
                    "",
                    "",
                    generation,
                ),
            )
        if len(codes) < count:
            raise RuntimeError("Could not issue recovery codes.")
        return codes

    def _revoke_sessions_for_user(self, user_id: str, *, except_session_id: str | None = None) -> None:
        if except_session_id:
            execute(
                """
                UPDATE cp_operator_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND session_id != ? AND revoked_at = ''
                """,
                (now_iso(), user_id, except_session_id),
            )
            return
        execute(
            """
            UPDATE cp_operator_sessions
            SET revoked_at = ?
            WHERE user_id = ? AND revoked_at = ''
            """,
            (now_iso(), user_id),
        )

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
        registration_token: str = "",
        bootstrap_code: str = "",
        username: str = "",
        email: str = "",
        password: str = "",
        display_name: str = "",
        remote_ip: str | None = None,
        forwarded_for: str | None = None,
    ) -> dict[str, Any]:
        if self.has_owner():
            raise ValueError("Owner account already exists. Sign in instead.")

        normalized_email = _normalize_email(email)
        if "@" not in normalized_email:
            raise ValueError("A valid email is required.")
        normalized_username = _normalize_username(username or normalized_email.split("@", 1)[0])
        if not normalized_username:
            raise ValueError("Username is required.")
        self._validate_operator_password(password, username=normalized_username, email=normalized_email)

        row = None
        trusted_loopback = (
            ALLOW_LOOPBACK_BOOTSTRAP
            and not str(registration_token or "").strip()
            and not str(bootstrap_code or "").strip()
            and is_loopback_request(remote_ip, forwarded_for)
        )
        if str(registration_token or "").strip():
            row = self._registration_row(registration_token)
            if row is None or row.get("exchange_consumed_at") or _is_expired(row.get("exchange_expires_at")):
                raise ValueError("Registration token is invalid or expired.")
        elif str(bootstrap_code or "").strip():
            exchange = self.exchange_bootstrap_code(bootstrap_code)
            registration_token = str(exchange.get("registration_token") or "")
            row = self._registration_row(registration_token)
            if row is None or row.get("exchange_consumed_at") or _is_expired(row.get("exchange_expires_at")):
                raise ValueError("Registration token is invalid or expired.")
        elif not trusted_loopback:
            raise ValueError("Bootstrap code is invalid or expired.")

        if row is not None and bootstrap_code:
            normalized_code = _normalize_bootstrap_code(bootstrap_code)
            if _hash_secret(normalized_code) != str(row.get("code_hash")):
                raise ValueError("Setup code does not match registration token.")

        existing = fetch_one(
            "SELECT id FROM cp_operator_users WHERE lower(username) = lower(?) OR lower(email) = lower(?)",
            (normalized_username, normalized_email),
        )
        if existing is not None:
            raise ValueError("Username or email already exists.")
        password_hash = _password_hasher().hash(password)
        user_id = f"usr_{uuid4().hex}"
        recovery_generation = uuid4().hex
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
                recovery_generation,
            ),
        )
        recovery_codes = self._issue_recovery_codes(user_id=user_id, generation=recovery_generation)
        if row is not None:
            execute(
                "UPDATE cp_bootstrap_codes SET exchange_consumed_at = ? WHERE id = ?",
                (now_iso(), str(row["id"])),
            )
        consume_bootstrap_file()
        session_token, context = self._create_session(
            user_id=user_id,
            subject_type="operator",
            label="web_owner_registration",
            metadata={
                "origin": "register_owner",
                "remote_ip": remote_ip,
                "forwarded_for": forwarded_for,
            },
        )
        emit_security(
            "security.operator_owner_registered",
            user_id=_optional_audit_user_id(user_id),
            username=normalized_username,
            remote_ip=remote_ip,
            forwarded_for=forwarded_for,
        )
        return {
            "ok": True,
            "operator": self._row_to_operator(fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (user_id,))),
            "session_token": session_token,
            "recovery_codes": recovery_codes,
            "auth": self.auth_status(context),
        }

    def reset_password_with_recovery_code(
        self,
        identifier: str,
        recovery_code: str,
        new_password: str,
    ) -> dict[str, Any]:
        normalized_id = identifier.strip().lower()
        row = fetch_one(
            "SELECT * FROM cp_operator_users WHERE lower(username) = lower(?) OR lower(email) = lower(?)",
            (normalized_id, normalized_id),
        )
        if not row:
            # Constant-time-ish side-effect to prevent enumeration
            _password_hasher().hash("dummy")
            raise ValueError("Invalid identifier or recovery code.")

        if row.get("locked_until") and not _is_expired(row["locked_until"]):
            raise ValueError("Invalid identifier or recovery code.")

        generation = str(row.get("recovery_generation") or "")
        active_codes = fetch_all(
            """
            SELECT id, code_hash FROM cp_operator_recovery_codes
            WHERE user_id = ? AND consumed_at = '' AND generation = ?
            """,
            (str(row["id"]), generation),
        )
        code_hash = _hash_secret(recovery_code.strip())
        code_row = next(
            (item for item in active_codes if compare_digest(str(item.get("code_hash") or ""), code_hash)),
            None,
        )
        if not code_row:
            raise ValueError("Invalid identifier or recovery code.")

        self._validate_operator_password(
            new_password,
            username=str(row.get("username") or ""),
            email=str(row.get("email") or ""),
        )

        password_hash = _password_hasher().hash(new_password)
        execute(
            "UPDATE cp_operator_users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, now_iso(), str(row["id"])),
        )
        execute(
            """
            UPDATE cp_operator_recovery_codes
            SET consumed_at = ?, consumed_reason = ?
            WHERE id = ?
            """,
            (now_iso(), "password_reset", str(code_row["id"])),
        )
        execute(
            """
            UPDATE cp_operator_recovery_codes
            SET consumed_at = ?, consumed_reason = ?
            WHERE user_id = ? AND consumed_at = '' AND generation = ?
            """,
            (now_iso(), "password_reset_invalidation", str(row["id"]), generation),
        )
        self._revoke_sessions_for_user(str(row["id"]))

        emit_security(
            "security.operator_password_reset_recovery",
            user_id=_optional_audit_user_id(str(row["id"])),
            username=str(row["username"]),
        )
        return {"ok": True}

    def change_password(
        self,
        context: OperatorAuthContext,
        current_password: str,
        new_password: str,
    ) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (context.user_id,))
        if not row:
            raise ValueError("User not found.")

        try:
            _password_hasher().verify(str(row["password_hash"]), current_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            raise ValueError("Invalid current password.") from None

        self._validate_operator_password(
            new_password,
            username=str(row.get("username") or ""),
            email=str(row.get("email") or ""),
        )

        password_hash = _password_hasher().hash(new_password)
        execute(
            "UPDATE cp_operator_users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, now_iso(), context.user_id),
        )
        self._revoke_sessions_for_user(context.user_id, except_session_id=context.session_id)
        emit_security(
            "security.operator_password_changed",
            user_id=_optional_audit_user_id(context.user_id),
        )
        return {"ok": True}

    def recovery_codes_summary(self, context: OperatorAuthContext) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        row = fetch_one("SELECT recovery_generation FROM cp_operator_users WHERE id = ?", (context.user_id,))
        generation = str(row.get("recovery_generation") or "") if row else ""
        total_row = fetch_one(
            """
            SELECT COUNT(*) AS count FROM cp_operator_recovery_codes
            WHERE user_id = ? AND generation = ?
            """,
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
            ORDER BY created_at ASC LIMIT 1
            """,
            (context.user_id, generation),
        )
        total = int(total_row.get("count") or 0) if total_row else 0
        remaining = int(remaining_row.get("count") or 0) if remaining_row else 0
        return {
            "total": total,
            "remaining": remaining,
            "active_count": remaining,
            "generated_at": str(created_row.get("created_at") or "") if created_row else None,
        }

    def regenerate_recovery_codes(self, context: OperatorAuthContext, current_password: str) -> dict[str, Any]:
        if not context.user_id:
            raise ValueError("Operator session is required.")
        row = fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (context.user_id,))
        if not row:
            raise ValueError("User not found.")

        try:
            _password_hasher().verify(str(row["password_hash"]), current_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            raise ValueError("Invalid current password.") from None

        # Invalidate existing
        current_generation = str(row.get("recovery_generation") or "")
        execute(
            """
            UPDATE cp_operator_recovery_codes
            SET consumed_at = ?, consumed_reason = ?
            WHERE user_id = ? AND consumed_at = '' AND generation = ?
            """,
            (now_iso(), "regenerated", context.user_id, current_generation),
        )

        generation = uuid4().hex
        new_codes = self._issue_recovery_codes(user_id=context.user_id, generation=generation)
        execute(
            "UPDATE cp_operator_users SET recovery_generation = ?, updated_at = ? WHERE id = ?",
            (generation, now_iso(), context.user_id),
        )

        emit_security(
            "security.operator_recovery_codes_regenerated",
            user_id=_optional_audit_user_id(context.user_id),
        )
        return {"recovery_codes": new_codes, "generated_at": now_iso()}

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
        normalized = str(identifier or "").strip()
        if not normalized or not password:
            raise ValueError("Identifier and password are required.")
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
            raise ValueError("Invalid credentials.")
        if row.get("disabled"):
            emit_security("security.operator_login_failed", identifier=normalized, reason="disabled")
            raise ValueError("Invalid credentials.")
        if row.get("locked_until") and not _is_expired(row.get("locked_until")):
            emit_security("security.operator_login_failed", identifier=normalized, reason="locked")
            raise ValueError("Invalid credentials.")
        try:
            _password_hasher().verify(str(row["password_hash"]), password)
        except (VerifyMismatchError, VerificationError, InvalidHashError) as exc:
            self._set_login_failure(row, identifier=normalized)
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
                return self._context_from_user_row(owner, auth_kind="break_glass", subject_type="break_glass")
            return OperatorAuthContext(
                auth_kind="break_glass",
                subject_type="break_glass",
                user_id=None,
                username=None,
                email=None,
                display_name="Break Glass",
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
