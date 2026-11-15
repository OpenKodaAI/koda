"""Operator auth bootstrap, sessions, recovery and token management.

The service tests run against the real control-plane tables on Postgres
(``@pytest.mark.postgres``), through the same ``koda.control_plane.database``
adapter the control plane uses in production. Tests of pure helpers stay
DB-free and run without Postgres.
"""

from __future__ import annotations

import asyncio
import io
import json
import statistics
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from koda.control_plane import api as control_plane_api
from koda.control_plane import bootstrap_file as bootstrap_file_mod
from koda.control_plane import database as control_plane_db
from koda.control_plane import operator_auth as operator_auth_mod
from koda.control_plane import operator_profile_photos

STRONG_PASSWORD = "CorrectHorseBattery!9"
ANOTHER_STRONG_PASSWORD = "R3volution@Nebula!42"

# Every table OperatorAuthService reads or writes.
_OPERATOR_AUTH_TABLES = (
    "cp_operator_users",
    "cp_operator_sessions",
    "cp_operator_tokens",
    "cp_operator_recovery_codes",
    "cp_bootstrap_codes",
)


@pytest.fixture()
def operator_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Empty operator-auth tables on the migrated test database.

    Only side channels are stubbed: audit events, the break-glass token list
    and the failure timing floor. The bootstrap file helpers are the real ones,
    pointed at a per-test path, which the fixture yields.
    """
    control_plane_db.execute(f"TRUNCATE TABLE {', '.join(_OPERATOR_AUTH_TABLES)}")
    monkeypatch.setattr(operator_auth_mod, "emit_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_API_TOKENS", ["legacy-break-glass"])
    monkeypatch.setattr(operator_auth_mod, "_FAILURE_TIMING_FLOOR_SECONDS", 0.0)
    bootstrap_path = tmp_path / "control_plane" / "bootstrap.txt"
    monkeypatch.setattr(bootstrap_file_mod, "_BOOTSTRAP_FILE_PATH", bootstrap_path)
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "")
    operator_auth_mod._password_hasher.cache_clear()
    yield bootstrap_path
    operator_auth_mod._password_hasher.cache_clear()


def _user_row(user_id: str) -> dict[str, Any]:
    row = control_plane_db.fetch_one("SELECT * FROM cp_operator_users WHERE id = ?", (user_id,))
    assert row is not None, f"operator {user_id} not persisted"
    return dict(row)


def _count(table: str) -> int:
    row = control_plane_db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")
    return int(row["count"]) if row else 0


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


@pytest.mark.postgres
def test_loopback_owner_registration_issues_recovery_codes(operator_db: Path) -> None:
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


@pytest.mark.postgres
def test_bootstrap_via_registration_token_still_works(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    bootstrap = service.issue_bootstrap_code(label="cli")
    exchanged = service.exchange_bootstrap_code(bootstrap["code"])

    payload = service.register_owner(
        registration_token=exchanged["registration_token"],
        email="cli@example.com",
        password=STRONG_PASSWORD,
    )
    assert payload["operator"]["email"] == "cli@example.com"


def _bootstrap_file_code(service: operator_auth_mod.OperatorAuthService) -> str:
    """Let the service write ``bootstrap.txt`` as it does on first boot, then read the code back."""
    service.onboarding_payload()
    code = bootstrap_file_mod.read_bootstrap_file()
    assert code, "the first status request writes the bootstrap file"
    return code


@pytest.mark.postgres
def test_owner_registration_with_bootstrap_file_code(operator_db: Path) -> None:
    """The VPS path: the code from ``bootstrap.txt`` registers the owner from a remote address."""
    service = operator_auth_mod.OperatorAuthService()
    code = _bootstrap_file_code(service)
    assert operator_db.exists()

    payload = service.register_owner(
        bootstrap_code=code,
        email="vps@example.com",
        password=STRONG_PASSWORD,
        remote_ip="203.0.113.7",
    )

    assert payload["operator"]["email"] == "vps@example.com"
    assert service.has_owner() is True
    assert not operator_db.exists(), "the bootstrap file is deleted after registration"
    stored = control_plane_db.fetch_all("SELECT code_hint, consumed_at, exchange_consumed_at FROM cp_bootstrap_codes")
    assert len(stored) == 1
    assert stored[0]["code_hint"] == code[-4:]
    assert stored[0]["consumed_at"] and stored[0]["exchange_consumed_at"]


@pytest.mark.postgres
def test_wrong_setup_code_fails_without_creating_owner(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    code = _bootstrap_file_code(service)
    wrong = code[:-1] + ("A" if code[-1] != "A" else "B")

    with pytest.raises(ValueError, match=r"^Setup code is invalid or expired\.$"):
        service.register_owner(
            bootstrap_code=wrong,
            email="vps@example.com",
            password=STRONG_PASSWORD,
            remote_ip="203.0.113.7",
        )

    assert service.has_owner() is False
    assert _count("cp_operator_users") == 0
    assert _count("cp_bootstrap_codes") == 0
    assert operator_db.exists(), "a failed attempt leaves the real code usable"


@pytest.mark.postgres
def test_setup_code_is_single_use_and_expires(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    used = service.issue_bootstrap_code(label="cli")["code"]
    service.exchange_bootstrap_code(used)
    with pytest.raises(ValueError, match=r"^Setup code is invalid or expired\.$"):
        service.exchange_bootstrap_code(used)

    expired = service.issue_bootstrap_code(label="cli")["code"]
    control_plane_db.execute(
        "UPDATE cp_bootstrap_codes SET expires_at = ? WHERE code_hash = ?",
        ("2000-01-01T00:00:00+00:00", operator_auth_mod._hash_secret(expired)),
    )
    with pytest.raises(ValueError, match=r"^Setup code is invalid or expired\.$"):
        service.exchange_bootstrap_code(expired)
    assert service.has_owner() is False


# Setup codes are issued as ``XXXX-XXXX-XXXX``, like recovery codes, and the
# server canonicalizes what the operator types the same way (D-221).
_TYPED_CODE_VARIANTS = [
    pytest.param(str.lower, id="lowercase"),
    pytest.param(lambda code: code.replace("-", ""), id="no-dashes"),
    pytest.param(lambda code: f"  {code.lower().replace('-', ' ')}\n", id="spaces-and-padding"),
    pytest.param(lambda code: code.replace("-", "_").lower(), id="underscores"),
]


def _setup_code(service: operator_auth_mod.OperatorAuthService, source: str) -> str:
    if source == "cli":
        return str(service.issue_bootstrap_code(label="cli")["code"])
    return _bootstrap_file_code(service)


def _register_with_setup_code(service: operator_auth_mod.OperatorAuthService, code: str) -> dict[str, Any]:
    return service.register_owner(
        bootstrap_code=code,
        email="owner@example.com",
        password=STRONG_PASSWORD,
        remote_ip="203.0.113.7",
    )


def test_setup_code_canonicalizer_is_the_recovery_code_canonicalizer() -> None:
    normalize = operator_auth_mod._normalize_bootstrap_code
    assert normalize("abcd-efgh-jklm") == "ABCD-EFGH-JKLM"
    assert normalize(" abcd efgh\tjklm ") == "ABCD-EFGH-JKLM"
    assert normalize("ABCDEFGHJKLM") == "ABCD-EFGH-JKLM"
    for typed in ("ab-cd--efgh_jk.lm", "abſd-efgh-jklm", "ＡＢＣＤ-efgh-jklm", "----", "", None):
        assert normalize(typed) == operator_auth_mod._normalize_recovery_code(typed)
    # Issued codes are already canonical, so stored hashes keep matching.
    issued = operator_auth_mod._random_code()
    assert normalize(issued) == issued


@pytest.mark.postgres
@pytest.mark.parametrize("source", ["cli", "bootstrap_file"])
@pytest.mark.parametrize("transform", _TYPED_CODE_VARIANTS)
def test_setup_code_accepts_case_and_separator_variants(operator_db: Path, source: str, transform: Any) -> None:
    service = operator_auth_mod.OperatorAuthService()
    code = _setup_code(service, source)
    assert code == operator_auth_mod._normalize_bootstrap_code(code)

    payload = _register_with_setup_code(service, transform(code))

    assert payload["operator"]["email"] == "owner@example.com"
    assert service.has_owner() is True


@pytest.mark.postgres
@pytest.mark.parametrize("source", ["cli", "bootstrap_file"])
def test_setup_code_canonicalization_does_not_accept_other_codes(operator_db: Path, source: str) -> None:
    service = operator_auth_mod.OperatorAuthService()
    code = _setup_code(service, source)
    compact = code.replace("-", "").lower()
    other = "a" if compact[-1] != "a" else "b"
    # A missing, wrong, extra or non-ASCII (look-alike) character still fails
    # with the generic error, never a server error.
    for candidate in (compact[:-1], compact[:-1] + other, compact + "a", code[:-1] + "ſ", code[:-1] + "é", "----"):
        with pytest.raises(ValueError, match=r"^Setup code is invalid or expired\.$"):
            _register_with_setup_code(service, candidate)
    assert service.has_owner() is False


@pytest.mark.postgres
def test_seeded_setup_code_is_canonicalized_on_the_stored_side(
    operator_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CONTROL_PLANE_BOOTSTRAP_CODE`` reaches ``bootstrap.txt`` as configured; matching ignores its spelling."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "cust omse edcd")
    service = operator_auth_mod.OperatorAuthService()
    assert _bootstrap_file_code(service) == "cust omse edcd"

    _register_with_setup_code(service, "CUST-OMSE-EDCD")

    assert service.has_owner() is True


@pytest.mark.postgres
def test_setup_code_without_ascii_letters_or_digits_never_matches(
    operator_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seed that canonicalizes to nothing must not match input that also canonicalizes to nothing."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "ÄÖÜ-ÄÖÜ")
    service = operator_auth_mod.OperatorAuthService()
    _bootstrap_file_code(service)

    for candidate in ("----", "ÄÖÜ-ÄÖÜ", "äöü äöü"):
        with pytest.raises(ValueError, match=r"^Setup code is invalid or expired\.$"):
            _register_with_setup_code(service, candidate)
    assert service.has_owner() is False
    assert _count("cp_bootstrap_codes") == 0


@pytest.mark.postgres
@pytest.mark.parametrize("source", ["cli", "bootstrap_file"])
@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(lambda code: code + "é", id="added-non-ascii"),
        pytest.param(lambda code: code.replace("-", "\u2013"), id="en-dashes"),
        pytest.param(lambda code: code + "\u00a0", id="trailing-nbsp"),
    ],
)
def test_setup_code_ignores_characters_that_are_not_ascii_letters_or_digits(
    operator_db: Path, source: str, transform: Any
) -> None:
    """Only ASCII letters and digits count, so an added non-ASCII character or separator is ignored."""
    service = operator_auth_mod.OperatorAuthService()
    code = _setup_code(service, source)

    _register_with_setup_code(service, transform(code))

    assert service.has_owner() is True


@pytest.mark.parametrize(
    "seed", ["!@#$%^&*()_+1", "!!!!a!!!!", "Tr0ub4dor&3!", "ÄÖÜ-ÄÖÜ", "CUST-OMSE-EDCD", "abſd ＡＢＣＤ efgh"]
)
def test_seed_strength_counts_only_what_setup_code_matching_keeps(seed: str) -> None:
    """The weak-seed warning in ``bootstrap_file`` counts exactly the characters the canonicalizer keeps."""
    canonical = operator_auth_mod._normalize_bootstrap_code(seed)
    assert bootstrap_file_mod._seed_kept_characters(seed) == canonical.replace("-", "")
    assert bootstrap_file_mod._seed_significant_characters(seed) == len(canonical.replace("-", ""))


def test_seed_punctuation_and_non_ascii_add_nothing_to_the_setup_code() -> None:
    normalize = operator_auth_mod._normalize_bootstrap_code
    assert normalize("Tr0ub4dor&3!") == "TR0U-B4DO-R3"
    assert normalize("!!!!a!!!!") == normalize("a") == "A"
    assert normalize("!@#$%^&*()_+1") == "1"


_AUTH_DOC = Path(__file__).resolve().parents[1] / "docs" / "security" / "authentication.md"


def test_auth_doc_states_which_setup_code_characters_count() -> None:
    """The security contract must not overstate what a setup code rejects (D-221 review)."""
    text = _AUTH_DOC.read_text(encoding="utf-8")
    start = text.index("## Account creation")
    section = " ".join(text[start : text.index("\n## ", start)].split())
    # An added non-ASCII character is dropped, not rejected; only a look-alike in place of a character fails.
    assert "non-ASCII character fails" not in section
    assert "any other non-ASCII character, so `ABCD-EFGH-JKLMé` matches too" in section
    assert "or a non-ASCII look-alike typed in place of one (for example `ſ` in place of `S`), fails" in section
    # A seed's punctuation no longer counts, and a short seed is flagged.
    assert "seed: only its ASCII letters and digits count towards its strength" in section
    assert "`bootstrap_code_seed_weak` warning" in section
    # The /setup field takes only part of what the API matches; the doc says which seeds it takes
    # and gives no example it cannot take (M1-E1-T17 review).
    assert (
        "The `/setup` screen's code field takes at most 12 characters, from "
        "`ABCDEFGHJKLMNPQRSTUVWXYZ23456789` only (no `I`, `O`, `0` or `1`)" in section
    )
    assert "`bootstrap_code_seed_not_typeable` warning" in section
    assert "Tr0ub4dor" not in section


@pytest.mark.postgres
def test_loopback_rejected_when_flag_disabled(
    operator_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    monkeypatch.setattr(operator_auth_mod, "ALLOW_LOOPBACK_BOOTSTRAP", False)
    with pytest.raises(ValueError, match="Bootstrap code is invalid"):
        _create_owner(service)


@pytest.mark.postgres
def test_loopback_rejected_when_owner_exists(
    operator_db: Path,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)
    with pytest.raises(ValueError, match="already exists"):
        _create_owner(service, email="second@example.com")


@pytest.mark.postgres
def test_issue_bootstrap_code_tolerates_insert_replay(
    operator_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    bootstrap_id = "boot_" + "1" * 32
    bootstrap_uuid = uuid.UUID(hex="1" * 32)
    recorded_insert = {"done": False}
    original_execute = operator_auth_mod.execute

    def execute_with_replay(query: str, params: tuple[Any, ...] = ()) -> int:
        # The row is really written, but the driver reports 0 affected rows,
        # as a replayed INSERT ... ON CONFLICT DO NOTHING would.
        affected = original_execute(query, params)
        if "INSERT INTO cp_bootstrap_codes" in " ".join(query.split()) and not recorded_insert["done"]:
            recorded_insert["done"] = True
            return 0
        return affected

    monkeypatch.setattr(operator_auth_mod, "execute", execute_with_replay)
    monkeypatch.setattr(operator_auth_mod, "uuid4", lambda: bootstrap_uuid)

    payload = service.issue_bootstrap_code(label="cli")

    assert payload["ok"] is True
    assert payload["code"]
    assert recorded_insert["done"] is True
    stored = control_plane_db.fetch_all("SELECT id, code_hash FROM cp_bootstrap_codes")
    assert [dict(row) for row in stored] == [
        {"id": bootstrap_id, "code_hash": operator_auth_mod._hash_secret(payload["code"])}
    ]


@pytest.mark.postgres
def test_login_lockout_applies_after_repeated_failures(
    operator_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES", 2)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS", 60)

    with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
        service.login(identifier="owner", password="wrong")

    with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
        service.login(identifier="owner", password="wrong")

    # After lockout, even the correct password returns the same generic error,
    # never "temporarily locked" — avoid leaking lock state to the caller.
    with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
        service.login(identifier="owner", password=STRONG_PASSWORD)


@pytest.mark.postgres
def test_login_never_reveals_account_disabled(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    control_plane_db.execute("UPDATE cp_operator_users SET disabled = 1 WHERE id = ?", (payload["operator"]["id"],))
    with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
        service.login(identifier="owner", password=STRONG_PASSWORD)


@pytest.mark.postgres
def test_login_rejects_an_unknown_identifier_like_a_wrong_password(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)

    for identifier, password in (("nobody@example.com", STRONG_PASSWORD), ("owner", "wrong-password-XX")):
        with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
            service.login(identifier=identifier, password=password)


@pytest.mark.parametrize(("identifier", "password"), [("", STRONG_PASSWORD), ("  ", STRONG_PASSWORD), ("owner", "")])
def test_login_without_an_identifier_or_password_is_a_malformed_request(identifier: str, password: str) -> None:
    """A missing field stays a 400, not an auth failure: no credential was checked (D-135)."""
    service = operator_auth_mod.OperatorAuthService()

    with pytest.raises(ValueError, match=r"^Identifier and password are required\.$") as caught:
        service.login(identifier=identifier, password=password)

    assert not isinstance(caught.value, operator_auth_mod.AuthError)


async def test_error_middleware_answers_rejected_credentials_with_401() -> None:
    """D-135: an AuthError is a 401, so the auth-failure rate-limit bucket (401/403) counts it."""

    async def rejected(_request: web.Request) -> web.Response:
        raise operator_auth_mod.AuthError("Invalid credentials.")

    async def malformed(_request: web.Request) -> web.Response:
        raise ValueError("Identifier and password are required.")

    app = web.Application(middlewares=[control_plane_api.control_plane_error_middleware])
    app.router.add_post("/rejected", rejected)
    app.router.add_post("/malformed", malformed)

    async with TestClient(TestServer(app)) as client:
        unauthorized = await client.post("/rejected")
        bad_request = await client.post("/malformed")

        assert unauthorized.status == 401
        assert await unauthorized.json() == {"error": "Invalid credentials."}
        assert bad_request.status == 400
        assert await bad_request.json() == {"error": "Identifier and password are required."}


@pytest.mark.postgres
async def test_failed_logins_answer_401_on_the_supervisor_stack_and_spend_the_auth_failure_bucket(
    operator_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-135 end to end on the :8090 middleware stack, with the real service and Argon2 hashes.

    A wrong password and an unknown identifier answer the same 401, and the stricter
    auth-failure bucket counts both: with a budget of 2, the third failure is a 429.
    """
    from koda.control_plane import rate_limit
    from koda.control_plane.supervisor import ControlPlaneSupervisor

    service = operator_auth_mod.OperatorAuthService()
    _create_owner(service)
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)
    monkeypatch.setattr(rate_limit, "CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT", 2)
    audit: list[dict[str, Any]] = []
    monkeypatch.setattr(rate_limit, "emit_security", lambda event, **fields: audit.append({"event": event, **fields}))
    monkeypatch.setattr("koda.control_plane.supervisor.get_control_plane_manager", lambda: object())
    app = ControlPlaneSupervisor().build_app()
    attempts = [
        {"identifier": "owner", "password": "wrong-password-XX"},
        {"identifier": "nobody@example.com", "password": STRONG_PASSWORD},
        {"identifier": "owner", "password": "wrong-password-XX"},
    ]

    rate_limit.clear_limiters()
    try:
        async with TestClient(TestServer(app)) as client:
            responses = [await client.post("/api/control-plane/auth/login", json=attempt) for attempt in attempts]
            statuses = [response.status for response in responses]
            bodies = [await response.json() for response in responses]
    finally:
        rate_limit.clear_limiters()

    assert statuses == [401, 401, 429]
    assert bodies[:2] == [{"error": "Invalid credentials."}] * 2
    assert int(responses[2].headers["Retry-After"]) >= 1
    failures = [entry for entry in audit if entry["event"] == "security.control_plane_auth_failure"]
    assert [(entry["path"], entry["status"]) for entry in failures] == [("/api/control-plane/auth/login", 401)] * 3


class _SpyHasher:
    """Stands in for the Argon2 hasher: records the hashes it makes and checks, and rejects every password."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.checked: list[str] = []

    def hash(self, password: str) -> str:
        self.created.append(f"spy-hash-{len(self.created)}")
        return self.created[-1]

    def verify(self, password_hash: str, password: str) -> bool:
        self.checked.append(password_hash)
        raise VerifyMismatchError


@pytest.fixture()
def spy_hasher(monkeypatch: pytest.MonkeyPatch) -> Iterator[_SpyHasher]:
    spy = _SpyHasher()
    monkeypatch.setattr(operator_auth_mod, "_password_hasher", lambda: spy)
    operator_auth_mod._dummy_password_hash.cache_clear()
    yield spy
    operator_auth_mod._dummy_password_hash.cache_clear()


@pytest.mark.parametrize(
    ("row", "stored_hash_checked"),
    [
        pytest.param(None, False, id="unknown-identifier"),
        pytest.param({"id": "7", "password_hash": "stored-hash", "disabled": 1}, False, id="disabled"),
        pytest.param(
            {"id": "7", "password_hash": "stored-hash", "locked_until": "2999-01-01T00:00:00+00:00"},
            False,
            id="locked",
        ),
        pytest.param({"id": "7", "password_hash": "stored-hash"}, True, id="wrong-password"),
    ],
)
def test_every_rejected_login_checks_one_password_hash(
    monkeypatch: pytest.MonkeyPatch,
    spy_hasher: _SpyHasher,
    row: dict[str, Any] | None,
    stored_hash_checked: bool,
) -> None:
    """D-136: a rejection that never reaches the stored hash checks a dummy one instead.

    Every rejected sign-in therefore does the same Argon2 work, whether or not the account exists.
    """
    monkeypatch.setattr(operator_auth_mod, "fetch_one", lambda query, params=(): row)
    monkeypatch.setattr(operator_auth_mod, "execute", lambda query, params=(): 1)
    monkeypatch.setattr(operator_auth_mod, "emit_security", lambda *args, **kwargs: None)

    with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
        operator_auth_mod.OperatorAuthService().login(identifier="owner", password="wrong-password-XX")

    assert spy_hasher.checked == (["stored-hash"] if stored_hash_checked else spy_hasher.created)
    assert len(spy_hasher.checked) == 1
    # The dummy hash is made on the first sign-in whichever path it takes, so the first unknown
    # identifier after a restart does not pay for it alone.
    assert len(spy_hasher.created) == 1


class _StubLoginService:
    """Accepts `owner`, treats an empty password as malformed and rejects everyone else."""

    def login(self, *, identifier: str, password: str) -> dict[str, Any]:
        if not password:
            raise ValueError("Identifier and password are required.")
        if identifier != "owner":
            raise operator_auth_mod.AuthError("Invalid credentials.")
        return {"ok": True, "session_token": "stub-session"}


def _login_app() -> web.Application:
    """The login route behind the error and auth middlewares, without the rate limiter."""
    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_post("/api/control-plane/auth/login", control_plane_api.auth_login)
    return app


async def _timed_login(client: TestClient, identifier: str, password: str) -> tuple[int, float]:
    started = time.perf_counter()
    response = await client.post("/api/control-plane/auth/login", json={"identifier": identifier, "password": password})
    await response.read()
    return response.status, time.perf_counter() - started


async def test_the_login_route_pads_only_rejected_sign_ins_to_the_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-136: a rejected sign-in answers no sooner than the floor; other answers are not held back."""
    monkeypatch.setattr(control_plane_api, "_auth_service", _StubLoginService)
    floor = operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS

    async with TestClient(TestServer(_login_app())) as client:
        rejected = await _timed_login(client, "nobody@example.com", "wrong-password-XX")
        accepted = await _timed_login(client, "owner", "wrong-password-XX")
        malformed = await _timed_login(client, "owner", "")

    assert rejected[0] == 401
    assert rejected[1] >= floor
    assert accepted[0] == 200
    assert accepted[1] < floor
    assert malformed[0] == 400
    assert malformed[1] < floor


async def test_the_floor_counts_from_when_the_sign_in_has_been_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-136: a client that holds its body back does not use up the floor before its sign-in is checked.

    The headers and the start of the body go out at once, the rest 400 ms later. The rejection
    still waits the whole floor after the body has arrived, so the answer never shows the raw
    time the rejection took, which differs between rejection paths.
    """
    monkeypatch.setattr(control_plane_api, "_auth_service", _StubLoginService)
    floor = operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS
    held_back = 0.4
    body = json.dumps({"identifier": "nobody@example.com", "password": "wrong-password-XX"}).encode()

    async def slow_body() -> AsyncIterator[bytes]:
        yield body[:10]
        await asyncio.sleep(held_back)
        yield body[10:]

    async with TestClient(TestServer(_login_app())) as client:
        started = time.perf_counter()
        response = await client.post(
            "/api/control-plane/auth/login", data=slow_body(), headers={"Content-Type": "application/json"}
        )
        await response.read()
        elapsed = time.perf_counter() - started

    assert response.status == 401
    assert elapsed >= held_back + floor, f"{elapsed * 1000:.1f} ms"


class _SlowHasher:
    """Stands in for the Argon2 hasher on a host so busy that one check outlasts the floor."""

    def __init__(self, check_seconds: float) -> None:
        self.check_seconds = check_seconds

    def hash(self, password: str) -> str:
        return "slow-hash"

    def verify(self, password_hash: str, password: str) -> bool:
        time.sleep(self.check_seconds)
        raise VerifyMismatchError


def _stand_in_operator_table(monkeypatch: pytest.MonkeyPatch, owner: dict[str, Any], write_seconds: float) -> list[Any]:
    """Serve `owner` from a stand-in for cp_operator_users; every write blocks for `write_seconds`.

    The owner's row never changes, so every wrong password for it takes the same path: check the
    stored hash, then write the failure count. Returns the parameters of each write.
    """
    writes: list[Any] = []

    def fetch_one(query: str, params: Any = ()) -> dict[str, Any] | None:
        return owner if owner["username"] in params else None

    def execute(query: str, params: Any = ()) -> int:
        time.sleep(write_seconds)
        writes.append(params)
        return 1

    monkeypatch.setattr(operator_auth_mod, "fetch_one", fetch_one)
    monkeypatch.setattr(operator_auth_mod, "execute", execute)
    monkeypatch.setattr(operator_auth_mod, "emit_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(control_plane_api, "_auth_service", operator_auth_mod.OperatorAuthService)
    return writes


@pytest.mark.parametrize(
    "check_seconds",
    [
        pytest.param(0.17, id="write-pushes-past-the-floor"),
        pytest.param(0.25, id="check-outlasts-the-floor"),
    ],
)
async def test_a_rejection_that_outlasts_the_floor_answers_when_its_work_ends(
    monkeypatch: pytest.MonkeyPatch,
    check_seconds: float,
) -> None:
    """D-136: the floor is fixed, so what work past it can show is the failure-count write, never a whole floor.

    Each Argon2 check takes `check_seconds` against a 200 ms floor, and the failure-count write
    that only a wrong password for an existing account does takes 40 ms. An unknown identifier
    answers at the floor or when its check ends, whichever is later; the owner answers at most
    the write's 40 ms after it (170 ms: 200 against 210 ms; 250 ms: 250 against 290 ms). Waiting
    to the next multiple of the floor instead would turn that write into a whole extra floor
    whenever it pushes the owner's answer past a multiple (200 against 400 ms).
    """
    floor = 0.2
    write_seconds = 0.04
    monkeypatch.setattr(operator_auth_mod, "_FAILURE_TIMING_FLOOR_SECONDS", floor)
    monkeypatch.setattr(operator_auth_mod, "_password_hasher", lambda: _SlowHasher(check_seconds=check_seconds))
    operator_auth_mod._dummy_password_hash.cache_clear()
    owner = {"id": "7", "username": "owner", "password_hash": "slow-hash"}
    writes = _stand_in_operator_table(monkeypatch, owner, write_seconds=write_seconds)
    durations: dict[str, list[float]] = {"owner": [], "nobody@example.com": []}

    try:
        async with TestClient(TestServer(_login_app())) as client:
            for _ in range(3):
                for identifier, measured in durations.items():
                    status, elapsed = await _timed_login(client, identifier, "wrong-password-XX")
                    assert status == 401
                    measured.append(elapsed)
    finally:
        operator_auth_mod._dummy_password_hash.cache_clear()

    assert len(writes) == 3
    for identifier, measured in durations.items():
        assert min(measured) >= floor, f"{identifier}: {[round(value * 1000) for value in measured]} ms"
    known, unknown = (statistics.median(measured) for measured in durations.values())
    assert unknown < max(floor, check_seconds) + 0.03, f"median unknown {unknown * 1000:.1f} ms"
    assert known - unknown < write_seconds + 0.015, (
        f"median owner {known * 1000:.1f} ms, unknown {unknown * 1000:.1f} ms"
    )


@pytest.mark.slow
async def test_failed_logins_take_the_floor_whether_or_not_the_identifier_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-136, measured over HTTP: 1,000 failed sign-ins each for the owner and an unknown identifier.

    Every attempt takes at least the 300 ms floor, and the two medians differ by less than 10 ms.
    The service and its Argon2 hashes are real; only cp_operator_users is stood in for, so the
    test needs no Postgres and runs in the plain `pytest` gate. Every owner attempt is a wrong
    password: it checks the stored hash and writes the failure count, a write the stand-in makes
    take 15 ms, more than the medians may differ by. An unknown identifier checks the dummy hash
    and writes nothing.

    Argon2 runs with cheap parameters so that the work stays inside the floor and the test
    measures the floor itself: with the defaults one check on a loaded host takes longer than
    300 ms (450 ms to 1.4 s on 4 cores at a load of 10). That case is
    `test_a_rejection_that_outlasts_the_floor_answers_when_its_work_ends`, and that every
    rejection checks one hash, the dummy one included, is
    `test_every_rejected_login_checks_one_password_hash`.
    """
    floor = operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS
    cheap_hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    monkeypatch.setattr(operator_auth_mod, "_password_hasher", lambda: cheap_hasher)
    operator_auth_mod._dummy_password_hash.cache_clear()
    owner = {"id": "7", "username": "owner", "password_hash": cheap_hasher.hash(STRONG_PASSWORD)}
    writes = _stand_in_operator_table(monkeypatch, owner, write_seconds=0.015)
    durations: dict[str, list[float]] = {"owner": [], "nobody@example.com": []}

    try:
        async with TestClient(TestServer(_login_app())) as client:
            for _ in range(1000):
                for identifier, measured in durations.items():
                    status, elapsed = await _timed_login(client, identifier, "wrong-password-XX")
                    assert status == 401
                    assert elapsed >= floor, f"{identifier}: {elapsed * 1000:.1f} ms"
                    measured.append(elapsed)
    finally:
        operator_auth_mod._dummy_password_hash.cache_clear()

    assert len(writes) == 1000
    known, unknown = (statistics.median(measured) for measured in durations.values())
    assert abs(known - unknown) < 0.010, f"median owner {known * 1000:.1f} ms, unknown {unknown * 1000:.1f} ms"


class _StubRecoveryService:
    """Accepts the recovery code `GOOD-CODE` and rejects every other one."""

    def reset_password_with_recovery_code(self, *, identifier: str, recovery_code: str, new_password: str) -> Any:
        if recovery_code != "GOOD-CODE":
            raise ValueError("Invalid identifier or recovery code.")
        return {"ok": True}


def _recover_app() -> web.Application:
    """The password-recovery route behind the error and auth middlewares, without the rate limiter."""
    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_post("/api/control-plane/auth/password/recover", control_plane_api.auth_password_recover)
    return app


async def _timed_recovery(client: TestClient, identifier: str, recovery_code: str) -> tuple[int, float]:
    started = time.perf_counter()
    response = await client.post(
        "/api/control-plane/auth/password/recover",
        json={"identifier": identifier, "recovery_code": recovery_code, "new_password": ANOTHER_STRONG_PASSWORD},
    )
    await response.read()
    return response.status, time.perf_counter() - started


async def test_the_recovery_route_pads_only_rejected_recoveries_to_the_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-136: a rejected password recovery answers no sooner than the floor; a recovery that works is not held back."""
    monkeypatch.setattr(control_plane_api, "_auth_service", _StubRecoveryService)
    floor = operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS

    async with TestClient(TestServer(_recover_app())) as client:
        rejected = await _timed_recovery(client, "owner", "WRONG-CODE")
        accepted = await _timed_recovery(client, "owner", "GOOD-CODE")

    assert rejected[0] == 400
    assert rejected[1] >= floor
    assert accepted[0] == 200
    assert accepted[1] < floor


_RECOVERY_OWNER = {"id": "7", "username": "owner", "email": "owner@example.com", "recovery_generation": "g1"}


def _stand_in_recovery_tables(monkeypatch: pytest.MonkeyPatch, row: dict[str, Any] | None) -> list[Any]:
    """Serve `row` from a stand-in for cp_operator_users, with one active recovery code `REAL-CODE` for it.

    Returns the parameters of each look-up of active recovery codes.
    """
    code_lookups: list[Any] = []
    real_code = {"id": "c1", "code_hash": operator_auth_mod._hash_secret("REAL-CODE")}

    def fetch_all(query: str, params: Any = ()) -> list[dict[str, Any]]:
        code_lookups.append(params)
        return [real_code] if row is not None and params == (row["id"], row["recovery_generation"]) else []

    monkeypatch.setattr(operator_auth_mod, "fetch_one", lambda query, params=(): row)
    monkeypatch.setattr(operator_auth_mod, "fetch_all", fetch_all)
    monkeypatch.setattr(operator_auth_mod, "execute", lambda query, params=(): 1)
    monkeypatch.setattr(operator_auth_mod, "emit_security", lambda *args, **kwargs: None)
    return code_lookups


_REJECTED_RECOVERIES = [
    pytest.param(None, "REAL-CODE", id="unknown-identifier"),
    pytest.param({**_RECOVERY_OWNER, "locked_until": "2999-01-01T00:00:00+00:00"}, "REAL-CODE", id="locked"),
    pytest.param(_RECOVERY_OWNER, "WRONG-CODE", id="wrong-code"),
]


@pytest.mark.parametrize(("row", "recovery_code"), _REJECTED_RECOVERIES)
def test_every_rejected_recovery_does_the_same_work(
    monkeypatch: pytest.MonkeyPatch,
    spy_hasher: _SpyHasher,
    row: dict[str, Any] | None,
    recovery_code: str,
) -> None:
    """D-136: an unknown identifier and a locked account look up and compare recovery codes like a wrong code does.

    None of them makes or checks an Argon2 hash, so none answers slower than the others.
    """
    code_lookups = _stand_in_recovery_tables(monkeypatch, row)

    with pytest.raises(ValueError, match=r"^Invalid identifier or recovery code\.$"):
        operator_auth_mod.OperatorAuthService().reset_password_with_recovery_code(
            identifier="owner",
            recovery_code=recovery_code,
            new_password=ANOTHER_STRONG_PASSWORD,
        )

    assert len(code_lookups) == 1
    assert spy_hasher.created == []
    assert spy_hasher.checked == []


async def test_rejected_recoveries_take_the_floor_whichever_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-136, measured over HTTP: an unknown identifier, a locked account and a wrong code answer alike.

    The service and its hasher are real; only the operator tables are stood in for. Every attempt
    takes at least the 300 ms floor, and the three medians differ by less than 10 ms.
    """
    floor = operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS
    monkeypatch.setattr(control_plane_api, "_auth_service", operator_auth_mod.OperatorAuthService)
    durations: dict[str, list[float]] = {}

    async with TestClient(TestServer(_recover_app())) as client:
        for case in _REJECTED_RECOVERIES:
            row, recovery_code = case.values
            _stand_in_recovery_tables(monkeypatch, row)
            measured = durations.setdefault(str(case.id), [])
            for _ in range(5):
                status, elapsed = await _timed_recovery(client, "owner", recovery_code)
                assert status == 400
                assert elapsed >= floor, f"{case.id}: {elapsed * 1000:.1f} ms"
                measured.append(elapsed)

    medians = {case: statistics.median(measured) for case, measured in durations.items()}
    assert max(medians.values()) - min(medians.values()) < 0.010, {
        case: round(median * 1000, 1) for case, median in medians.items()
    }


@pytest.mark.postgres
def test_register_owner_rejects_weak_password(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    with pytest.raises(ValueError, match="at least"):
        _create_owner(service, password="short")


@pytest.mark.postgres
def test_register_owner_rejects_common_password(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    # Long enough and has 3 classes, but exists in the common-password list.
    with pytest.raises(ValueError, match="too common"):
        _create_owner(service, password="Welcome2025!")


@pytest.mark.postgres
def test_register_owner_rejects_password_containing_email_local_part(
    operator_db: Path,
) -> None:
    service = operator_auth_mod.OperatorAuthService()
    with pytest.raises(ValueError, match="must not contain"):
        _create_owner(service, password="Owner!OwnerOwner1", email="owner@example.com")


@pytest.mark.postgres
def test_recovery_code_resets_password_and_invalidates_all(
    operator_db: Path,
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
    with pytest.raises(operator_auth_mod.AuthError, match=r"^Invalid credentials\.$"):
        service.login(identifier="owner", password=STRONG_PASSWORD)
    # New password does.
    logged_in = service.login(identifier="owner", password=ANOTHER_STRONG_PASSWORD)
    assert logged_in["operator"]["username"] == "owner"


@pytest.mark.postgres
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
    operator_db: Path,
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


@pytest.mark.postgres
def test_recovery_code_normalization_does_not_accept_other_codes(
    operator_db: Path,
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


@pytest.mark.postgres
async def test_password_recover_route_accepts_lowercase_compact_code(
    operator_db: Path,
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
        assert stale.status == 401
        assert await stale.json() == {"error": "Invalid credentials."}
        fresh = await client.post(
            "/api/control-plane/auth/login",
            json={"identifier": "owner", "password": ANOTHER_STRONG_PASSWORD},
        )
        assert fresh.status == 200, await fresh.text()
        assert (await fresh.json())["operator"]["username"] == "owner"


@pytest.mark.postgres
async def test_register_owner_route_accepts_lowercase_compact_setup_code(
    operator_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the aiohttp handler and the control-plane middlewares."""
    service = operator_auth_mod.OperatorAuthService()
    code = _bootstrap_file_code(service)
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)

    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_post("/api/control-plane/auth/register-owner", control_plane_api.auth_register_owner)
    account = {"email": "owner@example.com", "password": STRONG_PASSWORD}
    compact = code.lower().replace("-", "")

    async with TestClient(TestServer(app)) as client:
        wrong = await client.post(
            "/api/control-plane/auth/register-owner",
            json={**account, "bootstrap_code": compact[:-1] + ("a" if compact[-1] != "a" else "b")},
        )
        assert wrong.status == 400
        assert await wrong.json() == {"error": "Setup code is invalid or expired."}

        created = await client.post(
            "/api/control-plane/auth/register-owner",
            json={**account, "bootstrap_code": compact},
        )
        assert created.status == 201, await created.text()
        body = await created.json()
        assert body["operator"]["email"] == "owner@example.com"
        assert len(body["recovery_codes"]) >= 10

    assert service.has_owner() is True
    assert not operator_db.exists()


@pytest.mark.postgres
def test_password_reset_revokes_all_existing_sessions(operator_db: Path) -> None:
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


@pytest.mark.postgres
def test_change_password_revokes_other_sessions_but_keeps_current(
    operator_db: Path,
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


@pytest.mark.postgres
def test_change_password_rejects_wrong_current_password(
    operator_db: Path,
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


@pytest.mark.postgres
def test_update_profile_normalizes_and_persists_display_name(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    updated = service.update_profile(context, display_name="  Avery   Stone  ")

    assert updated["operator"]["display_name"] == "Avery Stone"
    assert _user_row(payload["operator"]["id"])["display_name"] == "Avery Stone"
    refreshed = service.resolve_bearer_token(payload["session_token"])
    assert refreshed is not None
    assert service.auth_status(refreshed)["operator"]["display_name"] == "Avery Stone"


@pytest.mark.postgres
def test_update_profile_rejects_invalid_display_name(operator_db: Path) -> None:
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


@pytest.mark.postgres
def test_profile_photo_upload_read_and_delete(
    operator_db: Path,
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


@pytest.mark.postgres
def test_regenerate_recovery_codes_invalidates_old(
    operator_db: Path,
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


@pytest.mark.postgres
def test_recovery_codes_summary_counts_remaining(
    operator_db: Path,
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


@pytest.mark.postgres
def test_personal_tokens_and_sessions_can_be_listed_and_revoked(
    operator_db: Path,
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


@pytest.mark.postgres
def test_login_then_logout_revokes_only_that_session(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    registration = _create_owner(service)
    login = service.login(identifier="owner@example.com", password=STRONG_PASSWORD)
    assert service.resolve_bearer_token(login["session_token"]) is not None
    assert _user_row(login["operator"]["id"])["last_login_at"]

    assert service.logout(login["session_token"]) == {"ok": True}

    assert service.resolve_bearer_token(login["session_token"]) is None
    assert service.resolve_bearer_token(registration["session_token"]) is not None


def test_legacy_exchange_method_is_removed() -> None:
    service = operator_auth_mod.OperatorAuthService()

    assert not hasattr(service, "exchange_legacy_token")


@pytest.mark.postgres
def test_break_glass_accepts_configured_token(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()

    context = service.resolve_bearer_token("legacy-break-glass")

    assert context is not None
    assert context.auth_kind == "break_glass"


@pytest.mark.postgres
def test_break_glass_never_accepts_env_example_placeholder(operator_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane.settings import parse_api_tokens

    # A deployment that copied .env.example without editing it.
    tokens, ignored = parse_api_tokens("replace-with-a-random-token")
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_API_TOKENS", tokens)
    service = operator_auth_mod.OperatorAuthService()

    assert ignored == 1
    assert service.resolve_bearer_token("replace-with-a-random-token") is None


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


@pytest.mark.postgres
@pytest.mark.parametrize("owner_exists", [False, True], ids=["before-setup", "after-setup"])
async def test_onboarding_status_without_a_session_returns_only_the_setup_flags(
    operator_db: Path,
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


@pytest.mark.postgres
async def test_onboarding_status_with_an_operator_credential_returns_the_full_payload(
    operator_db: Path,
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


@pytest.mark.postgres
@pytest.mark.parametrize("owner_exists", [False, True], ids=["before-setup", "after-setup"])
async def test_auth_status_without_a_session_names_the_bootstrap_file_only_before_setup(
    operator_db: Path,
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
                assert payload["bootstrap_file_path"] == str(operator_db)
                assert payload["loopback_trust_enabled"] is True


@pytest.mark.postgres
async def test_auth_status_with_an_operator_credential_keeps_the_server_flags(
    operator_db: Path,
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
            assert payload["bootstrap_file_path"] == str(operator_db)


_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(_REPO_ROOT / "docs" / "security" / "authentication.md", id="security/authentication.md"),
        pytest.param(_REPO_ROOT / "apps" / "web" / "CLAUDE.md", id="web/CLAUDE.md"),
        pytest.param(_REPO_ROOT / "docs" / "install" / "vps.md", id="install/vps.md"),
    ],
)
def test_docs_state_the_login_timing_floor(path: Path) -> None:
    """D-136: failed logins and recoveries are padded to a fixed 300 ms floor, and no doc still calls it pending.

    Only the login and password-recovery routes are padded, so no doc may claim that every auth
    failure takes equal time. The mandatory web guide is checked too.
    """
    assert operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS == 0.3
    text = " ".join(path.read_text(encoding="utf-8").split())

    assert "300 ms" in text
    assert "timing floor pending M1-E1-T13" not in text
    assert "All auth-failure paths pad" not in text
    assert "neutralize timing" not in text
    assert "deliberately slowed" not in text
    assert "recovery is not padded" not in text
    assert "next multiple" not in text
