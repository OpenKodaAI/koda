"""Focused tests for operator auth bootstrap, sessions, and token management."""

from __future__ import annotations

from typing import Any

import pytest

from koda.control_plane import operator_auth as operator_auth_mod


class FakeOperatorAuthDb:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, dict[str, Any]] = {}
        self.bootstrap_codes: dict[str, dict[str, Any]] = {}

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        normalized = " ".join(query.split())

        if "FROM cp_operator_users ORDER BY created_at ASC LIMIT 1" in normalized:
            if not self.users:
                return None
            return sorted(self.users.values(), key=lambda row: str(row["created_at"]))[0]

        if "SELECT * FROM cp_operator_users WHERE id = ?" in normalized:
            return self.users.get(str(params[0]))

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

        raise AssertionError(f"Unexpected fetch_one query: {query}")

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

        raise AssertionError(f"Unexpected fetch_all query: {query}")

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
def fake_operator_db(monkeypatch: pytest.MonkeyPatch) -> FakeOperatorAuthDb:
    db = FakeOperatorAuthDb()
    monkeypatch.setattr(operator_auth_mod, "fetch_one", db.fetch_one)
    monkeypatch.setattr(operator_auth_mod, "fetch_all", db.fetch_all)
    monkeypatch.setattr(operator_auth_mod, "execute", db.execute)
    monkeypatch.setattr(operator_auth_mod, "emit_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_API_TOKENS", ["legacy-break-glass"])
    operator_auth_mod._password_hasher.cache_clear()
    yield db
    operator_auth_mod._password_hasher.cache_clear()


def _create_owner(service: operator_auth_mod.OperatorAuthService) -> dict[str, Any]:
    bootstrap = service.issue_bootstrap_code(label="cli")
    exchanged = service.exchange_bootstrap_code(bootstrap["code"])
    return service.register_owner(
        registration_token=exchanged["registration_token"],
        username="owner",
        email="owner@example.com",
        password="supersecret",
        display_name="Owner",
    )


def test_bootstrap_code_owner_registration_and_session_resolution(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()

    assert service.auth_status()["authenticated"] is False
    assert service.auth_status()["bootstrap_required"] is True

    payload = _create_owner(service)

    assert service.has_owner() is True
    assert payload["operator"]["username"] == "owner"
    assert payload["auth"]["authenticated"] is True
    assert payload["auth"]["operator"]["email"] == "owner@example.com"

    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None
    assert context.user_id == payload["operator"]["id"]
    assert context.subject_type == "operator"


def test_login_lockout_applies_after_repeated_failures(
    fake_operator_db: FakeOperatorAuthDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES", 2)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS", 60)

    with pytest.raises(ValueError, match="Invalid credentials."):
        service.login(identifier="owner", password="wrong")

    with pytest.raises(ValueError, match="Invalid credentials."):
        service.login(identifier="owner", password="wrong")

    with pytest.raises(ValueError, match="temporarily locked"):
        service.login(identifier="owner", password="supersecret")


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


def test_legacy_break_glass_exchange_remains_available(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()

    payload = service.exchange_legacy_token("legacy-break-glass")
    context = service.resolve_bearer_token(payload["session_token"])

    assert payload["auth"]["authenticated"] is True
    assert payload["auth"]["session_subject"] == "break_glass"
    assert payload["auth"]["operator"] is None
    assert context is not None
    assert context.subject_type == "break_glass"
