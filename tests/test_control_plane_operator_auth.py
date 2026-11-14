"""Focused tests for operator auth bootstrap, sessions, and token management."""

from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import operator_auth as operator_auth_mod
from koda.control_plane import operator_profile_photos

STRONG_PASSWORD = "CorrectHorseBattery!9"
ANOTHER_STRONG_PASSWORD = "R3volution@Nebula!42"


class FakeOperatorAuthDb:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, dict[str, Any]] = {}
        self.bootstrap_codes: dict[str, dict[str, Any]] = {}
        self.recovery_codes: dict[str, dict[str, Any]] = {}

    # ---------------------------- fetch_one ---------------------------------

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        normalized = " ".join(query.split())

        if "FROM cp_operator_users ORDER BY created_at ASC LIMIT 1" in normalized:
            if not self.users:
                return None
            return sorted(self.users.values(), key=lambda row: str(row["created_at"]))[0]

        if "SELECT * FROM cp_operator_users WHERE id = ?" in normalized:
            return self.users.get(str(params[0]))

        if "SELECT recovery_generation FROM cp_operator_users WHERE id = ?" in normalized:
            row = self.users.get(str(params[0]))
            if row is None:
                return None
            return {"recovery_generation": str(row.get("recovery_generation") or "")}

        if "SELECT id FROM cp_operator_users WHERE lower(username) = lower(?) OR lower(email) = lower(?)" in normalized:
            username = str(params[0]).lower()
            email = str(params[1]).lower()
            for row in self.users.values():
                if str(row["username"]).lower() == username or str(row["email"]).lower() == email:
                    return {"id": row["id"]}
            return None

        if "SELECT * FROM cp_operator_users WHERE lower(username) = lower(?) OR lower(email) = lower(?)" in normalized:
            username = str(params[0]).lower()
            email = str(params[1]).lower()
            matches = [
                row
                for row in self.users.values()
                if str(row["username"]).lower() == username or str(row["email"]).lower() == email
            ]
            if not matches:
                return None
            return sorted(matches, key=lambda row: str(row["created_at"]))[0]

        if "SELECT * FROM cp_bootstrap_codes WHERE code_hash = ?" in normalized:
            code_hash = str(params[0])
            for row in self.bootstrap_codes.values():
                if str(row.get("code_hash")) == code_hash:
                    return row
            return None

        if "SELECT * FROM cp_bootstrap_codes WHERE exchange_token_hash = ?" in normalized:
            token_hash = str(params[0])
            for row in self.bootstrap_codes.values():
                if str(row.get("exchange_token_hash") or "") == token_hash:
                    return row
            return None

        if "SELECT * FROM cp_bootstrap_codes WHERE id = ?" in normalized:
            return self.bootstrap_codes.get(str(params[0]))

        if "SELECT * FROM cp_operator_sessions WHERE token_hash = ?" in normalized:
            token_hash = str(params[0])
            matches = [row for row in self.sessions.values() if str(row.get("token_hash")) == token_hash]
            if not matches:
                return None
            return sorted(matches, key=lambda row: str(row["created_at"]), reverse=True)[0]

        if "SELECT * FROM cp_operator_tokens WHERE token_hash = ?" in normalized:
            token_hash = str(params[0])
            matches = [row for row in self.tokens.values() if str(row.get("token_hash")) == token_hash]
            if not matches:
                return None
            return sorted(matches, key=lambda row: str(row["created_at"]), reverse=True)[0]

        if (
            "SELECT COUNT(*) AS count FROM cp_operator_recovery_codes WHERE user_id = ? AND generation = ?"
            in normalized
        ):
            user_id = str(params[0])
            generation = str(params[1])
            count = sum(
                1
                for row in self.recovery_codes.values()
                if str(row.get("user_id")) == user_id and str(row.get("generation")) == generation
            )
            return {"count": count}

        if (
            "SELECT COUNT(*) AS count FROM cp_operator_recovery_codes "
            "WHERE user_id = ? AND consumed_at = '' AND generation = ?"
        ) in normalized:
            user_id = str(params[0])
            generation = str(params[1])
            count = sum(
                1
                for row in self.recovery_codes.values()
                if str(row.get("user_id")) == user_id
                and str(row.get("consumed_at") or "") == ""
                and str(row.get("generation")) == generation
            )
            return {"count": count}

        if (
            "SELECT created_at FROM cp_operator_recovery_codes WHERE user_id = ? AND generation = ? "
            "ORDER BY created_at ASC LIMIT 1"
        ) in normalized:
            user_id = str(params[0])
            generation = str(params[1])
            matches = [
                row
                for row in self.recovery_codes.values()
                if str(row.get("user_id")) == user_id and str(row.get("generation")) == generation
            ]
            if not matches:
                return None
            earliest = sorted(matches, key=lambda row: str(row["created_at"]))[0]
            return {"created_at": earliest["created_at"]}

        raise AssertionError(f"Unexpected fetch_one query: {query}")

    # ---------------------------- fetch_all ---------------------------------

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        normalized = " ".join(query.split())

        if "SELECT * FROM cp_operator_tokens WHERE user_id = ?" in normalized:
            user_id = str(params[0])
            return sorted(
                [row for row in self.tokens.values() if str(row.get("user_id")) == user_id],
                key=lambda row: str(row["created_at"]),
                reverse=True,
            )

        if "SELECT * FROM cp_operator_sessions WHERE user_id = ?" in normalized:
            user_id = str(params[0])
            return sorted(
                [row for row in self.sessions.values() if str(row.get("user_id")) == user_id],
                key=lambda row: str(row["created_at"]),
                reverse=True,
            )

        if (
            "SELECT id, code_hash FROM cp_operator_recovery_codes "
            "WHERE user_id = ? AND consumed_at = '' AND generation = ?"
        ) in normalized:
            user_id = str(params[0])
            generation = str(params[1])
            matches = [
                {"id": row["id"], "code_hash": row["code_hash"]}
                for row in self.recovery_codes.values()
                if str(row.get("user_id")) == user_id
                and str(row.get("consumed_at") or "") == ""
                and str(row.get("generation")) == generation
            ]
            return sorted(matches, key=lambda row: str(row["id"]))

        raise AssertionError(f"Unexpected fetch_all query: {query}")

    # ---------------------------- execute -----------------------------------

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(query.split())

        if "INSERT INTO cp_bootstrap_codes" in normalized:
            (
                row_id,
                code_hash,
                code_hint,
                purpose,
                created_at,
                expires_at,
                issued_by,
                metadata_json,
            ) = params
            self.bootstrap_codes[str(row_id)] = {
                "id": str(row_id),
                "code_hash": str(code_hash),
                "code_hint": str(code_hint),
                "purpose": str(purpose),
                "created_at": str(created_at),
                "expires_at": str(expires_at),
                "issued_by": str(issued_by),
                "metadata_json": str(metadata_json),
                "consumed_at": "",
                "exchange_token_hash": "",
                "exchange_issued_at": "",
                "exchange_expires_at": "",
                "exchange_consumed_at": "",
            }
            return

        if "UPDATE cp_bootstrap_codes SET consumed_at = ?" in normalized:
            consumed_at, exchange_token_hash, exchange_issued_at, exchange_expires_at, row_id = params
            row = self.bootstrap_codes[str(row_id)]
            row["consumed_at"] = str(consumed_at)
            row["exchange_token_hash"] = str(exchange_token_hash)
            row["exchange_issued_at"] = str(exchange_issued_at)
            row["exchange_expires_at"] = str(exchange_expires_at)
            return

        if "UPDATE cp_bootstrap_codes SET exchange_consumed_at = ?" in normalized:
            exchange_consumed_at, row_id = params
            self.bootstrap_codes[str(row_id)]["exchange_consumed_at"] = str(exchange_consumed_at)
            return

        if "INSERT INTO cp_operator_users" in normalized:
            (
                user_id,
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
                recovery_generation,
            ) = params
            self.users[str(user_id)] = {
                "id": str(user_id),
                "username": str(username),
                "email": str(email),
                "display_name": str(display_name),
                "password_hash": str(password_hash),
                "role": str(role),
                "created_at": str(created_at),
                "updated_at": str(updated_at),
                "last_login_at": str(last_login_at),
                "failed_login_attempts": int(failed_login_attempts),
                "locked_until": str(locked_until),
                "disabled": int(disabled),
                "totp_secret": str(totp_secret),
                "recovery_generation": str(recovery_generation),
                "profile_photo_hash": "",
                "profile_photo_updated_at": "",
            }
            return

        if "INSERT INTO cp_operator_sessions" in normalized:
            (
                session_id,
                user_id,
                token_hash,
                subject_type,
                label,
                created_at,
                last_used_at,
                expires_at,
                revoked_at,
                metadata_json,
            ) = params
            self.sessions[str(session_id)] = {
                "session_id": str(session_id),
                "user_id": str(user_id) if user_id else "",
                "token_hash": str(token_hash),
                "subject_type": str(subject_type),
                "label": str(label),
                "created_at": str(created_at),
                "last_used_at": str(last_used_at),
                "expires_at": str(expires_at),
                "revoked_at": str(revoked_at),
                "metadata_json": str(metadata_json),
            }
            return

        if "INSERT INTO cp_operator_recovery_codes" in normalized:
            # Supports both the batched multi-row INSERT used in production and
            # the legacy single-row form (8 params).
            assert len(params) % 8 == 0, f"unexpected recovery insert: {params}"
            for offset in range(0, len(params), 8):
                row_id, user_id, code_hash, code_hint, created_at, consumed_at, consumed_reason, generation = (
                    params[offset + 0],
                    params[offset + 1],
                    params[offset + 2],
                    params[offset + 3],
                    params[offset + 4],
                    params[offset + 5],
                    params[offset + 6],
                    params[offset + 7],
                )
                self.recovery_codes[str(row_id)] = {
                    "id": str(row_id),
                    "user_id": str(user_id),
                    "code_hash": str(code_hash),
                    "code_hint": str(code_hint),
                    "created_at": str(created_at),
                    "consumed_at": str(consumed_at),
                    "consumed_reason": str(consumed_reason),
                    "generation": str(generation),
                }
            return

        if "UPDATE cp_operator_recovery_codes SET consumed_at = ?, consumed_reason = ? WHERE id = ?" in normalized:
            consumed_at, reason, row_id = params
            row = self.recovery_codes.get(str(row_id))
            if row:
                row["consumed_at"] = str(consumed_at)
                row["consumed_reason"] = str(reason)
            return

        if (
            "UPDATE cp_operator_recovery_codes SET consumed_at = ?, consumed_reason = ? "
            "WHERE user_id = ? AND consumed_at = '' AND generation = ?"
        ) in normalized:
            consumed_at, reason, user_id, generation = params
            for row in self.recovery_codes.values():
                if (
                    str(row.get("user_id")) == str(user_id)
                    and str(row.get("consumed_at") or "") == ""
                    and str(row.get("generation")) == str(generation)
                ):
                    row["consumed_at"] = str(consumed_at)
                    row["consumed_reason"] = str(reason)
            return

        if (
            "UPDATE cp_operator_recovery_codes SET consumed_at = ?, consumed_reason = ? "
            "WHERE user_id = ? AND consumed_at = ''"
            in normalized
            and "generation" not in normalized
        ):
            consumed_at, reason, user_id = params
            for row in self.recovery_codes.values():
                if str(row.get("user_id")) == str(user_id) and str(row.get("consumed_at") or "") == "":
                    row["consumed_at"] = str(consumed_at)
                    row["consumed_reason"] = str(reason)
            return

        if "UPDATE cp_operator_users SET failed_login_attempts = ?, locked_until = ?, updated_at = ?" in normalized:
            attempts, locked_until, updated_at, user_id = params
            row = self.users[str(user_id)]
            row["failed_login_attempts"] = int(attempts)
            row["locked_until"] = str(locked_until)
            row["updated_at"] = str(updated_at)
            return

        if (
            "UPDATE cp_operator_users SET failed_login_attempts = 0, locked_until = '', "
            "last_login_at = ?, updated_at = ?" in normalized
        ):
            last_login_at, updated_at, user_id = params
            row = self.users[str(user_id)]
            row["failed_login_attempts"] = 0
            row["locked_until"] = ""
            row["last_login_at"] = str(last_login_at)
            row["updated_at"] = str(updated_at)
            return

        if "UPDATE cp_operator_users SET password_hash = ?, updated_at = ? WHERE id = ?" in normalized:
            password_hash, updated_at, user_id = params
            row = self.users[str(user_id)]
            row["password_hash"] = str(password_hash)
            row["updated_at"] = str(updated_at)
            return

        if "UPDATE cp_operator_users SET display_name = ?, updated_at = ? WHERE id = ?" in normalized:
            display_name, updated_at, user_id = params
            row = self.users[str(user_id)]
            row["display_name"] = str(display_name)
            row["updated_at"] = str(updated_at)
            return

        if (
            "UPDATE cp_operator_users SET profile_photo_hash = ?, profile_photo_updated_at = ?, "
            "updated_at = ? WHERE id = ?"
        ) in normalized:
            photo_hash, photo_updated_at, updated_at, user_id = params
            row = self.users[str(user_id)]
            row["profile_photo_hash"] = str(photo_hash)
            row["profile_photo_updated_at"] = str(photo_updated_at)
            row["updated_at"] = str(updated_at)
            return

        if (
            "UPDATE cp_operator_users SET profile_photo_hash = '', profile_photo_updated_at = '', "
            "updated_at = ? WHERE id = ?"
        ) in normalized:
            updated_at, user_id = params
            row = self.users[str(user_id)]
            row["profile_photo_hash"] = ""
            row["profile_photo_updated_at"] = ""
            row["updated_at"] = str(updated_at)
            return

        if "UPDATE cp_operator_users SET recovery_generation = ?, updated_at = ? WHERE id = ?" in normalized:
            generation, updated_at, user_id = params
            row = self.users[str(user_id)]
            row["recovery_generation"] = str(generation)
            row["updated_at"] = str(updated_at)
            return

        if "UPDATE cp_operator_sessions SET revoked_at = ?, last_used_at = ? WHERE token_hash = ?" in normalized:
            revoked_at, last_used_at, token_hash = params
            for row in self.sessions.values():
                if str(row.get("token_hash")) == str(token_hash):
                    row["revoked_at"] = str(revoked_at)
                    row["last_used_at"] = str(last_used_at)
            return

        if "UPDATE cp_operator_sessions SET last_used_at = ? WHERE session_id = ?" in normalized:
            last_used_at, session_id = params
            self.sessions[str(session_id)]["last_used_at"] = str(last_used_at)
            return

        if (
            "UPDATE cp_operator_sessions SET revoked_at = ? WHERE user_id = ? "
            "AND session_id != ? AND revoked_at = ''" in normalized
        ):
            revoked_at, user_id, current_session_id = params
            for row in self.sessions.values():
                if (
                    str(row.get("user_id")) == str(user_id)
                    and str(row.get("session_id")) != str(current_session_id)
                    and str(row.get("revoked_at") or "") == ""
                ):
                    row["revoked_at"] = str(revoked_at)
            return

        if "UPDATE cp_operator_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = ''" in normalized:
            revoked_at, user_id = params
            for row in self.sessions.values():
                if str(row.get("user_id")) == str(user_id) and str(row.get("revoked_at") or "") == "":
                    row["revoked_at"] = str(revoked_at)
            return

        if "INSERT INTO cp_operator_tokens" in normalized:
            (
                token_id,
                user_id,
                token_name,
                token_hash,
                token_prefix,
                scopes_json,
                created_at,
                last_used_at,
                expires_at,
                revoked_at,
                metadata_json,
            ) = params
            self.tokens[str(token_id)] = {
                "id": str(token_id),
                "user_id": str(user_id),
                "token_name": str(token_name),
                "token_hash": str(token_hash),
                "token_prefix": str(token_prefix),
                "scopes_json": str(scopes_json),
                "created_at": str(created_at),
                "last_used_at": str(last_used_at),
                "expires_at": str(expires_at),
                "revoked_at": str(revoked_at),
                "metadata_json": str(metadata_json),
            }
            return

        if "UPDATE cp_operator_tokens SET last_used_at = ? WHERE id = ?" in normalized:
            last_used_at, token_id = params
            self.tokens[str(token_id)]["last_used_at"] = str(last_used_at)
            return

        if "UPDATE cp_operator_tokens SET revoked_at = ? WHERE id = ? AND user_id = ?" in normalized:
            revoked_at, token_id, user_id = params
            row = self.tokens.get(str(token_id))
            if row and str(row.get("user_id")) == str(user_id):
                row["revoked_at"] = str(revoked_at)
            return

        if "UPDATE cp_operator_sessions SET revoked_at = ? WHERE session_id = ? AND user_id = ?" in normalized:
            revoked_at, session_id, user_id = params
            row = self.sessions.get(str(session_id))
            if row and str(row.get("user_id")) == str(user_id):
                row["revoked_at"] = str(revoked_at)
            return

        raise AssertionError(f"Unexpected execute query: {query}")


@pytest.fixture()
def fake_operator_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> FakeOperatorAuthDb:
    db = FakeOperatorAuthDb()
    monkeypatch.setattr(operator_auth_mod, "fetch_one", db.fetch_one)
    monkeypatch.setattr(operator_auth_mod, "fetch_all", db.fetch_all)
    monkeypatch.setattr(operator_auth_mod, "execute", db.execute)
    monkeypatch.setattr(operator_auth_mod, "emit_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_API_TOKENS", ["legacy-break-glass"])
    monkeypatch.setattr(operator_auth_mod, "_FAILURE_TIMING_FLOOR_SECONDS", 0.0)
    # Ensure bootstrap file helpers don't touch the real filesystem during tests.
    monkeypatch.setattr(operator_auth_mod, "ensure_bootstrap_file", lambda **_: None)
    monkeypatch.setattr(operator_auth_mod, "consume_bootstrap_file", lambda: None)
    monkeypatch.setattr(operator_auth_mod, "read_bootstrap_file", lambda: None)
    monkeypatch.setattr(operator_auth_mod, "bootstrap_file_path", lambda: tmp_path / "bootstrap.txt")
    operator_auth_mod._password_hasher.cache_clear()
    yield db
    operator_auth_mod._password_hasher.cache_clear()


def _create_owner(
    service: operator_auth_mod.OperatorAuthService,
    *,
    password: str = STRONG_PASSWORD,
    loopback: bool = True,
    email: str = "owner@example.com",
) -> dict[str, Any]:
    """Create the owner via a loopback-trusted request."""
    return service.register_owner(
        email=email,
        password=password,
        remote_ip="127.0.0.1" if loopback else None,
        forwarded_for=None,
    )


def test_loopback_owner_registration_issues_recovery_codes(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()

    assert service.auth_status()["authenticated"] is False
    assert service.auth_status()["bootstrap_required"] is True

    payload = _create_owner(service)

    assert service.has_owner() is True
    assert payload["operator"]["username"] == "owner"
    assert payload["operator"]["email"] == "owner@example.com"
    assert payload["auth"]["authenticated"] is True
    assert payload["auth"]["onboarding_complete"] is True
    assert isinstance(payload["recovery_codes"], list)
    assert len(payload["recovery_codes"]) >= 10
    for code in payload["recovery_codes"]:
        assert len(code) == 14  # xxxx-xxxx-xxxx

    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None
    assert context.user_id == payload["operator"]["id"]


def test_bootstrap_via_registration_token_still_works(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    bootstrap = service.issue_bootstrap_code(label="cli")
    exchanged = service.exchange_bootstrap_code(bootstrap["code"])

    payload = service.register_owner(
        registration_token=exchanged["registration_token"],
        email="cli@example.com",
        password=STRONG_PASSWORD,
    )
    assert payload["operator"]["email"] == "cli@example.com"


def test_loopback_rejected_when_flag_disabled(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    monkeypatch.setattr(operator_auth_mod, "ALLOW_LOOPBACK_BOOTSTRAP", False)
    with pytest.raises(ValueError, match="Bootstrap code is invalid"):
        _create_owner(service)


def test_loopback_rejected_when_owner_exists(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)
    with pytest.raises(ValueError, match="already exists"):
        _create_owner(service, email="second@example.com")


def test_issue_bootstrap_code_tolerates_insert_replay(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    bootstrap_id = "boot_" + "1" * 32
    bootstrap_uuid = uuid.UUID(hex="1" * 32)
    recorded_insert = {"done": False}
    original_execute = fake_operator_db.execute

    def execute_with_replay(query: str, params: tuple[Any, ...] = ()) -> int:
        normalized = " ".join(query.split())
        if "INSERT INTO cp_bootstrap_codes" not in normalized:
            original_execute(query, params)
            return 1
        original_execute(query, params)
        if not recorded_insert["done"]:
            recorded_insert["done"] = True
            return 0
        return 1

    monkeypatch.setattr(operator_auth_mod, "execute", execute_with_replay)
    monkeypatch.setattr(operator_auth_mod, "uuid4", lambda: bootstrap_uuid)

    payload = service.issue_bootstrap_code(label="cli")

    assert payload["ok"] is True
    assert payload["code"]
    assert bootstrap_id in fake_operator_db.bootstrap_codes
    assert fake_operator_db.bootstrap_codes[bootstrap_id]["code_hash"] == operator_auth_mod._hash_secret(
        payload["code"]
    )


def test_login_lockout_applies_after_repeated_failures(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES", 2)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS", 60)

    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password="wrong")

    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password="wrong")

    # After lockout, even the correct password returns the same generic error,
    # never "temporarily locked" — avoid leaking lock state to the caller.
    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password=STRONG_PASSWORD)


def test_login_never_reveals_account_disabled(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    fake_operator_db.users[payload["operator"]["id"]]["disabled"] = 1
    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password=STRONG_PASSWORD)


def test_register_owner_rejects_weak_password(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    with pytest.raises(ValueError, match="at least"):
        _create_owner(service, password="short")


def test_register_owner_rejects_common_password(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    # Long enough and has 3 classes, but exists in the common-password list.
    with pytest.raises(ValueError, match="too common"):
        _create_owner(service, password="Welcome2025!")


def test_register_owner_rejects_password_containing_email_local_part(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    with pytest.raises(ValueError, match="must not contain"):
        _create_owner(service, password="Owner!OwnerOwner1", email="owner@example.com")


def test_recovery_code_resets_password_and_invalidates_all(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    codes = payload["recovery_codes"]
    assert len(codes) >= 10

    # Consume one to reset password — every other code is invalidated too.
    service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=codes[0],
        new_password=ANOTHER_STRONG_PASSWORD,
    )
    # Second code can no longer reset, because the first reset invalidated all of them.
    with pytest.raises(ValueError, match="Invalid"):
        service.reset_password_with_recovery_code(
            identifier="owner",
            recovery_code=codes[1],
            new_password=STRONG_PASSWORD,
        )
    # Old password no longer works.
    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password=STRONG_PASSWORD)
    # New password does.
    logged_in = service.login(identifier="owner", password=ANOTHER_STRONG_PASSWORD)
    assert logged_in["operator"]["username"] == "owner"


@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(str.lower, id="lowercase"),
        pytest.param(lambda code: code.replace("-", ""), id="no-separators"),
        pytest.param(lambda code: f"  {code.lower().replace('-', ' ')}\n", id="spaces-and-padding"),
        pytest.param(lambda code: code.replace("-", "_").lower(), id="underscores"),
    ],
)
def test_recovery_code_accepts_case_and_separator_variants(
    fake_operator_db: FakeOperatorAuthDb,
    transform: Any,
) -> None:
    """Codes are issued as ``XXXX-XXXX-XXXX``; the server canonicalizes what the user types."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    issued = payload["recovery_codes"][0]
    assert issued == issued.upper()

    service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=transform(issued),
        new_password=ANOTHER_STRONG_PASSWORD,
    )
    logged_in = service.login(identifier="owner", password=ANOTHER_STRONG_PASSWORD)
    assert logged_in["operator"]["username"] == "owner"


def test_recovery_code_normalization_does_not_accept_other_codes(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    issued = payload["recovery_codes"][0]
    # Dropping or swapping a character must still fail after canonicalization.
    for candidate in (issued[:-1], issued[:-1] + ("A" if issued[-1] != "A" else "B"), "", "----"):
        with pytest.raises(ValueError, match="Invalid identifier or recovery code"):
            service.reset_password_with_recovery_code(
                identifier="owner",
                recovery_code=candidate,
                new_password=ANOTHER_STRONG_PASSWORD,
            )
    assert service.login(identifier="owner", password=STRONG_PASSWORD)["operator"]["username"] == "owner"


def test_normalize_recovery_code_is_canonical_issued_format() -> None:
    normalize = operator_auth_mod._normalize_recovery_code
    assert normalize("abcd-efgh-jklm") == "ABCD-EFGH-JKLM"
    assert normalize(" abcd efgh\tjklm ") == "ABCD-EFGH-JKLM"
    assert normalize("ABCDEFGHJKLM") == "ABCD-EFGH-JKLM"
    assert normalize("ab-cd--efgh_jk.lm") == "ABCD-EFGH-JKLM"
    assert normalize("ABCD-EFGH-JKLM") == "ABCD-EFGH-JKLM"
    assert normalize(None) == ""
    # Non-ASCII characters are dropped, never case-folded into ASCII look-alikes
    # (U+017F long s upper-cases to "S", "ß" to "SS", the "ﬆ" ligature to "ST").
    assert normalize("abſd-efgh-jklm") == "ABDE-FGHJ-KLM"
    assert normalize("aßcd-efgh-jklm") == "ACDE-FGHJ-KLM"
    assert normalize("ﬆcd-efgh-jklm") == "CDEF-GHJK-LM"
    assert normalize("ＡＢＣＤ-efgh-jklm") == "EFGH-JKLM"
    # Issued codes are already canonical, so hashes stored before this
    # normalization existed keep matching.
    issued = operator_auth_mod._random_code()
    assert normalize(issued) == issued


async def test_password_recover_route_accepts_lowercase_compact_code(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the aiohttp handler and the control-plane middlewares."""
    service = operator_auth_mod.OperatorAuthService()
    issued = _create_owner(service)["recovery_codes"][0]
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)

    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_post("/api/control-plane/auth/password/recover", control_plane_api.auth_password_recover)
    app.router.add_post("/api/control-plane/auth/login", control_plane_api.auth_login)

    async with TestClient(TestServer(app)) as client:
        recovered = await client.post(
            "/api/control-plane/auth/password/recover",
            json={
                "identifier": "owner",
                "recovery_code": issued.lower().replace("-", ""),
                "new_password": ANOTHER_STRONG_PASSWORD,
            },
        )
        assert recovered.status == 200, await recovered.text()
        assert await recovered.json() == {"ok": True}

        stale = await client.post(
            "/api/control-plane/auth/login",
            json={"identifier": "owner", "password": STRONG_PASSWORD},
        )
        assert stale.status == 400
        fresh = await client.post(
            "/api/control-plane/auth/login",
            json={"identifier": "owner", "password": ANOTHER_STRONG_PASSWORD},
        )
        assert fresh.status == 200, await fresh.text()
        assert (await fresh.json())["operator"]["username"] == "owner"


_OPERATOR_ONBOARDING_STATUS: dict[str, Any] = {
    "control_plane": {"ready": True},
    "storage": {"database": {"ready": True}, "object_storage": {"ready": True}},
    "providers": [{"provider_id": "claude", "verified": True, "connection_status": {"account_label": "team"}}],
    "agents": [{"id": "ATLAS", "display_name": "Atlas", "status": "active"}],
    "system": {"owner_email": "owner@example.com", "allowed_user_ids": [123456789]},
    "steps": {"onboarding_complete": True},
}


def _serve_onboarding_status(monkeypatch: pytest.MonkeyPatch, service: Any) -> tuple[TestServer, MagicMock]:
    """The onboarding status route behind the real control-plane middlewares."""
    manager = MagicMock()
    manager.get_onboarding_status.return_value = dict(_OPERATOR_ONBOARDING_STATUS)
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)
    monkeypatch.setattr(control_plane_api, "_manager", lambda: manager)
    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_get("/api/control-plane/onboarding/status", control_plane_api.onboarding_status)
    return TestServer(app), manager


@pytest.mark.parametrize("owner_exists", [False, True], ids=["before-setup", "after-setup"])
async def test_onboarding_status_without_a_session_returns_only_the_setup_flags(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
    owner_exists: bool,
) -> None:
    """Before login the route says whether setup is needed and nothing else (D-050)."""
    service = operator_auth_mod.OperatorAuthService()
    if owner_exists:
        _create_owner(service)
    ensured: list[dict[str, Any]] = []
    monkeypatch.setattr(operator_auth_mod, "ensure_bootstrap_file", lambda **kwargs: ensured.append(kwargs))
    server, manager = _serve_onboarding_status(monkeypatch, service)

    async with TestClient(server) as client:
        anonymous = await client.get("/api/control-plane/onboarding/status")
        unknown_token = await client.get(
            "/api/control-plane/onboarding/status",
            headers={"Authorization": "Bearer kodas_not-a-live-session"},
        )

        for response in (anonymous, unknown_token):
            assert response.status == 200, await response.text()
            assert await response.json() == {"has_owner": owner_exists, "bootstrap_required": not owner_exists}

    manager.get_onboarding_status.assert_not_called()
    # `koda auth issue-code` polls this route so the control plane writes the setup-code file.
    assert ensured == [{"has_owner": owner_exists}, {"has_owner": owner_exists}]


async def test_onboarding_status_with_an_operator_credential_returns_the_full_payload(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    session_token = _create_owner(service)["session_token"]
    server, manager = _serve_onboarding_status(monkeypatch, service)

    async with TestClient(server) as client:
        for token in (session_token, "legacy-break-glass"):
            response = await client.get(
                "/api/control-plane/onboarding/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status == 200, await response.text()
            payload = await response.json()
            assert payload["agents"] == _OPERATOR_ONBOARDING_STATUS["agents"]
            assert payload["providers"] == _OPERATOR_ONBOARDING_STATUS["providers"]
            assert payload["system"] == _OPERATOR_ONBOARDING_STATUS["system"]
            assert payload["has_owner"] is True
            assert payload["bootstrap_required"] is False
            assert payload["session_required"] is True

    assert manager.get_onboarding_status.call_count == 2


def _serve_auth_status(monkeypatch: pytest.MonkeyPatch, service: Any) -> TestServer:
    """The auth status route behind the real control-plane middlewares."""
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)
    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_get("/api/control-plane/auth/status", control_plane_api.auth_status)
    return TestServer(app)


_ANONYMOUS_AUTH_STATUS_KEYS = {
    "has_owner",
    "bootstrap_required",
    "auth_mode",
    "session_required",
    "onboarding_complete",
    "authenticated",
    "session_subject",
    "operator",
}


@pytest.mark.parametrize("owner_exists", [False, True], ids=["before-setup", "after-setup"])
async def test_auth_status_without_a_session_names_the_bootstrap_file_only_before_setup(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    owner_exists: bool,
) -> None:
    """The setup screen gets the bootstrap file path; once an owner exists nobody anonymous does (D-050, R-36)."""
    monkeypatch.setattr(operator_auth_mod, "ALLOW_LOOPBACK_BOOTSTRAP", True)
    service = operator_auth_mod.OperatorAuthService()
    if owner_exists:
        _create_owner(service)
    server = _serve_auth_status(monkeypatch, service)

    async with TestClient(server) as client:
        anonymous = await client.get("/api/control-plane/auth/status")
        unknown_token = await client.get(
            "/api/control-plane/auth/status",
            headers={"Authorization": "Bearer kodas_not-a-live-session"},
        )

        for response in (anonymous, unknown_token):
            assert response.status == 200, await response.text()
            payload = await response.json()
            assert payload["authenticated"] is False
            assert payload["operator"] is None
            assert payload["has_owner"] is owner_exists
            assert payload["bootstrap_required"] is not owner_exists
            if owner_exists:
                assert set(payload) == _ANONYMOUS_AUTH_STATUS_KEYS
            else:
                assert set(payload) == _ANONYMOUS_AUTH_STATUS_KEYS | {"bootstrap_file_path", "loopback_trust_enabled"}
                assert payload["bootstrap_file_path"] == str(tmp_path / "bootstrap.txt")
                assert payload["loopback_trust_enabled"] is True


async def test_auth_status_with_an_operator_credential_keeps_the_server_flags(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setattr(operator_auth_mod, "ALLOW_LOOPBACK_BOOTSTRAP", True)
    service = operator_auth_mod.OperatorAuthService()
    session_token = _create_owner(service)["session_token"]
    server = _serve_auth_status(monkeypatch, service)

    async with TestClient(server) as client:
        for token in (session_token, "legacy-break-glass"):
            response = await client.get(
                "/api/control-plane/auth/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status == 200, await response.text()
            payload = await response.json()
            assert payload["authenticated"] is True
            assert payload["has_owner"] is True
            assert payload["recovery_available"] is True
            assert payload["loopback_trust_enabled"] is True
            assert payload["bootstrap_file_path"] == str(tmp_path / "bootstrap.txt")


def test_password_reset_revokes_all_existing_sessions(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    # Initial session should resolve.
    assert service.resolve_bearer_token(payload["session_token"]) is not None

    service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=payload["recovery_codes"][0],
        new_password=ANOTHER_STRONG_PASSWORD,
    )
    # All sessions revoked.
    assert service.resolve_bearer_token(payload["session_token"]) is None


def test_change_password_revokes_other_sessions_but_keeps_current(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    # A second login (e.g. from a different device) creates a second session.
    other_login = service.login(identifier="owner", password=STRONG_PASSWORD)

    service.change_password(
        context,
        current_password=STRONG_PASSWORD,
        new_password=ANOTHER_STRONG_PASSWORD,
    )
    # The session that initiated the change still works.
    assert service.resolve_bearer_token(payload["session_token"]) is not None
    # The other session is revoked.
    assert service.resolve_bearer_token(other_login["session_token"]) is None


def test_change_password_rejects_wrong_current_password(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None
    with pytest.raises(ValueError, match="Invalid"):
        service.change_password(
            context,
            current_password="definitely-wrong-password-XYZ",
            new_password=ANOTHER_STRONG_PASSWORD,
        )


def test_update_profile_normalizes_and_persists_display_name(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    updated = service.update_profile(context, display_name="  Avery   Stone  ")

    assert updated["operator"]["display_name"] == "Avery Stone"
    assert fake_operator_db.users[payload["operator"]["id"]]["display_name"] == "Avery Stone"
    refreshed = service.resolve_bearer_token(payload["session_token"])
    assert refreshed is not None
    assert service.auth_status(refreshed)["operator"]["display_name"] == "Avery Stone"


def test_update_profile_rejects_invalid_display_name(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    with pytest.raises(ValueError, match="required"):
        service.update_profile(context, display_name="   ")
    with pytest.raises(ValueError, match="control"):
        service.update_profile(context, display_name="Bad\nName")
    with pytest.raises(ValueError, match="80"):
        service.update_profile(context, display_name="A" * 81)


def test_profile_photo_upload_read_and_delete(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    monkeypatch.setattr(
        operator_auth_mod,
        "save_operator_profile_photo",
        lambda user_id, raw: SimpleNamespace(content_hash="abc123", byte_size=len(raw)),
    )
    monkeypatch.setattr(operator_auth_mod, "read_operator_profile_photo", lambda user_id: b"jpeg-bytes")
    removed: list[str] = []
    monkeypatch.setattr(
        operator_auth_mod,
        "delete_operator_profile_photo",
        lambda user_id: not removed.append(user_id),
    )

    uploaded = service.set_profile_photo(context, raw=b"raw-image")

    assert uploaded["photoHash"] == "abc123"
    assert uploaded["photoUrl"] == "/api/control-plane/auth/profile/photo?v=abc123"
    assert uploaded["operator"]["profile_photo_hash"] == "abc123"
    assert uploaded["operator"]["profile_photo_url"] == "/api/control-plane/auth/profile/photo?v=abc123"

    data, photo_hash = service.get_profile_photo(context, requested_hash="abc123")
    assert data == b"jpeg-bytes"
    assert photo_hash == "abc123"
    with pytest.raises(FileNotFoundError):
        service.get_profile_photo(context, requested_hash="old-hash")

    deleted = service.delete_profile_photo(context)

    assert deleted["removed"] is True
    assert deleted["operator"]["profile_photo_hash"] is None
    assert deleted["operator"]["profile_photo_url"] is None
    assert removed == [payload["operator"]["id"]]


def test_operator_profile_photo_storage_processes_image(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Image = pytest.importorskip("PIL.Image")
    monkeypatch.setattr(operator_profile_photos, "STATE_ROOT_DIR", tmp_path)

    source = Image.new("RGB", (80, 40), color=(217, 119, 87))
    raw = io.BytesIO()
    source.save(raw, format="PNG")

    stored = operator_profile_photos.save_operator_profile_photo("usr_test", raw.getvalue())

    assert stored.path.exists()
    assert stored.content_hash
    processed = operator_profile_photos.read_operator_profile_photo("usr_test")
    assert processed is not None
    with Image.open(io.BytesIO(processed)) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 40)
    assert operator_profile_photos.delete_operator_profile_photo("usr_test") is True
    assert operator_profile_photos.read_operator_profile_photo("usr_test") is None


def test_operator_profile_photo_storage_rejects_unsafe_or_large_payload(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operator_profile_photos, "STATE_ROOT_DIR", tmp_path)

    with pytest.raises(ValueError, match="unsafe"):
        operator_profile_photos.profile_photo_path_for("../bad")
    with pytest.raises(operator_profile_photos.ProfilePhotoTooLargeError):
        operator_profile_photos.save_operator_profile_photo(
            "usr_test",
            b"x" * (operator_profile_photos.MAX_INPUT_BYTES + 1),
        )


def test_regenerate_recovery_codes_invalidates_old(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    regen = service.regenerate_recovery_codes(context, current_password=STRONG_PASSWORD)
    new_codes = regen["recovery_codes"]
    assert len(new_codes) >= 10

    # Old codes are invalidated — they can't be used to reset.
    with pytest.raises(ValueError, match="Invalid"):
        service.reset_password_with_recovery_code(
            identifier="owner",
            recovery_code=payload["recovery_codes"][0],
            new_password=ANOTHER_STRONG_PASSWORD,
        )
    # New codes do work.
    service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=new_codes[0],
        new_password=ANOTHER_STRONG_PASSWORD,
    )


def test_recovery_codes_summary_counts_remaining(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    summary = service.recovery_codes_summary(context)
    assert summary["total"] >= 10
    assert summary["remaining"] == summary["total"]

    # Consume one → remaining drops by 1 (but summary returns 0 because the reset
    # invalidates all of them — that is the intended behavior).
    service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=payload["recovery_codes"][0],
        new_password=ANOTHER_STRONG_PASSWORD,
    )
    # Re-authenticate with new password.
    login_payload = service.login(identifier="owner", password=ANOTHER_STRONG_PASSWORD)
    new_context = service.resolve_bearer_token(login_payload["session_token"])
    assert new_context is not None
    summary_after = service.recovery_codes_summary(new_context)
    # All recovery codes under the original generation are consumed; nothing under
    # the new (unchanged) generation string yet.
    assert summary_after["remaining"] == 0


def test_personal_tokens_and_sessions_can_be_listed_and_revoked(
    fake_operator_db: FakeOperatorAuthDb,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    token_payload = service.issue_personal_token(context, token_name="CLI token")
    listed_tokens = service.list_personal_tokens(context)["items"]
    listed_sessions = service.list_sessions(context)["items"]

    assert len(listed_tokens) == 1
    assert listed_tokens[0]["token_name"] == "CLI token"
    assert len(listed_sessions) == 1
    assert listed_sessions[0]["is_current"] is True

    token_context = service.resolve_bearer_token(token_payload["token"])
    assert token_context is not None
    assert token_context.auth_kind == "api_token"

    service.revoke_personal_token(context, token_payload["id"])
    assert service.resolve_bearer_token(token_payload["token"]) is None

    service.revoke_session(context, context.session_id or "")
    assert service.resolve_bearer_token(payload["session_token"]) is None


def test_legacy_exchange_method_is_removed() -> None:
    service = operator_auth_mod.OperatorAuthService()

    assert not hasattr(service, "exchange_legacy_token")


def test_break_glass_accepts_configured_token(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()

    context = service.resolve_bearer_token("legacy-break-glass")

    assert context is not None
    assert context.auth_kind == "break_glass"


def test_break_glass_never_accepts_env_example_placeholder(
    fake_operator_db: FakeOperatorAuthDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.control_plane.settings import parse_api_tokens

    # A deployment that copied .env.example without editing it.
    tokens, ignored = parse_api_tokens("replace-with-a-random-token")
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_API_TOKENS", tokens)
    service = operator_auth_mod.OperatorAuthService()

    assert ignored == 1
    assert service.resolve_bearer_token("replace-with-a-random-token") is None
