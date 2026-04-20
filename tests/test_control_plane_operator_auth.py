"""Focused tests for operator auth bootstrap, sessions, and token management."""

from __future__ import annotations

from typing import Any

import pytest

from koda.control_plane import operator_auth as operator_auth_mod

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


def test_legacy_break_glass_exchange_remains_available(fake_operator_db: FakeOperatorAuthDb) -> None:
    service = operator_auth_mod.OperatorAuthService()

    payload = service.exchange_legacy_token("legacy-break-glass")
    context = service.resolve_bearer_token(payload["session_token"])

    assert payload["auth"]["authenticated"] is True
    assert payload["auth"]["session_subject"] == "break_glass"
    assert payload["auth"]["operator"] is None
    assert context is not None
    assert context.subject_type == "break_glass"
