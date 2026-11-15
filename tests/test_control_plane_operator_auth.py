"""Operator auth bootstrap, sessions, recovery and token management.

The service tests run against the real control-plane tables on Postgres
(``@pytest.mark.postgres``), through the same ``koda.control_plane.database``
adapter the control plane uses in production. Tests of pure helpers stay
DB-free and run without Postgres.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import io
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import bootstrap_file as bootstrap_file_mod
from koda.control_plane import database as control_plane_db
from koda.control_plane import operator_auth as operator_auth_mod
from koda.control_plane import operator_profile_photos
from koda.state import primary as primary_state
from tests.postgres_fixtures import injected_fault, stop_primary_bridge

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
def test_owner_registration_fault_leaves_no_owner_without_recovery_codes(operator_db: Path) -> None:
    """D-056: a write failing mid-registration rolls back every write, and the same setup code still works."""
    service = operator_auth_mod.OperatorAuthService()
    owner = {
        "bootstrap_code": _bootstrap_file_code(service),
        "email": "vps@example.com",
        "password": STRONG_PASSWORD,
        "remote_ip": "203.0.113.7",
    }

    with (
        injected_fault("cp_operator_recovery_codes", "INSERT", rows_before=3),
        pytest.raises(Exception, match="injected fault"),
    ):
        service.register_owner(**owner)

    assert service.has_owner() is False
    assert _count("cp_operator_users") == 0
    assert _count("cp_operator_recovery_codes") == 0
    assert _count("cp_operator_sessions") == 0
    assert operator_db.exists(), "the bootstrap file is kept until registration commits"
    payload = service.register_owner(**owner)
    assert payload["operator"]["email"] == "vps@example.com"
    assert _count("cp_operator_recovery_codes") == len(payload["recovery_codes"]) >= 10
    assert not operator_db.exists()


@pytest.mark.postgres
def test_owner_registration_fault_keeps_the_registration_token_not_the_setup_code(operator_db: Path) -> None:
    """D-056: on the registration-token path the exchange consumed the setup code; the token stays usable."""
    service = operator_auth_mod.OperatorAuthService()
    bootstrap = service.issue_bootstrap_code(label="cli")
    exchanged = service.exchange_bootstrap_code(bootstrap["code"])
    owner = {"email": "cli@example.com", "password": STRONG_PASSWORD}

    with (
        injected_fault("cp_operator_recovery_codes", "INSERT", rows_before=3),
        pytest.raises(Exception, match="injected fault"),
    ):
        service.register_owner(registration_token=exchanged["registration_token"], **owner)

    assert service.has_owner() is False
    with pytest.raises(ValueError, match="Setup code is invalid or expired"):
        service.register_owner(bootstrap_code=bootstrap["code"], **owner)
    payload = service.register_owner(registration_token=exchanged["registration_token"], **owner)
    assert payload["operator"]["email"] == "cli@example.com"


@pytest.fixture()
def bridge_loop() -> Iterator[None]:
    """Run the sync service's Postgres calls on the bridge loop, as the control plane does, so threads share it."""
    primary_state._ensure_bridge_loop()
    yield
    stop_primary_bridge()


def _concurrently(
    monkeypatch: pytest.MonkeyPatch,
    service: operator_auth_mod.OperatorAuthService,
    checkpoint: str,
    *attempts: Callable[[], Any],
) -> list[Any]:
    """Run ``attempts`` on their own threads, each waiting after ``service.<checkpoint>`` until all have passed it.

    Every attempt has validated the same code before any of them writes, the
    window two concurrent requests race in. Each outcome is the attempt's
    return value or the exception it raised.
    """
    barrier = threading.Barrier(len(attempts), timeout=20)
    original = getattr(service, checkpoint)

    def _checkpoint(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        barrier.wait()
        return result

    monkeypatch.setattr(service, checkpoint, _checkpoint)

    def _outcome(attempt: Callable[[], Any]) -> Any:
        try:
            return attempt()
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=len(attempts)) as pool:
        return list(pool.map(_outcome, attempts))


def _split(outcomes: list[Any]) -> tuple[list[Any], list[Exception]]:
    return (
        [outcome for outcome in outcomes if not isinstance(outcome, Exception)],
        [outcome for outcome in outcomes if isinstance(outcome, Exception)],
    )


@pytest.mark.postgres
@pytest.mark.parametrize("presented", ["bootstrap_code", "registration_token"])
def test_concurrent_registrations_with_one_code_create_one_owner(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
    presented: str,
) -> None:
    """D-283: two registrations racing with the same setup code (or registration token) create one owner."""
    service = operator_auth_mod.OperatorAuthService()
    if presented == "bootstrap_code":
        credential = {"bootstrap_code": _bootstrap_file_code(service)}
        # Both have looked the file code up and found no row before either stores it.
        checkpoint, refusal = "_bootstrap_file_matches", "Setup code is invalid or expired."
    else:
        exchanged = service.exchange_bootstrap_code(service.issue_bootstrap_code(label="cli")["code"])
        credential = {"registration_token": exchanged["registration_token"]}
        checkpoint, refusal = "_registration_row", "Registration token is invalid or expired."

    outcomes = _concurrently(
        monkeypatch,
        service,
        checkpoint,
        *(
            functools.partial(service.register_owner, email=email, password=STRONG_PASSWORD, **credential)
            for email in ("first@example.com", "second@example.com")
        ),
    )

    succeeded, refused = _split(outcomes)
    assert len(succeeded) == 1, outcomes
    assert [type(exc) for exc in refused] == [ValueError] and str(refused[0]) == refusal
    owner = succeeded[0]
    assert [row["id"] for row in control_plane_db.fetch_all("SELECT id FROM cp_operator_users")] == [
        owner["operator"]["id"]
    ]
    assert _count("cp_operator_recovery_codes") == len(owner["recovery_codes"])
    assert _count("cp_operator_sessions") == 1


@pytest.mark.postgres
@pytest.mark.parametrize("presented", ["two_setup_codes", "loopback"])
def test_concurrent_registrations_with_different_credentials_create_one_owner(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
    presented: str,
) -> None:
    """D-294: two registrations racing with two valid setup codes (or two loopback-trusted ones) create one owner.

    The loser changes nothing and gets the answer a registration gets once an owner exists.
    """
    service = operator_auth_mod.OperatorAuthService()
    codes = [_bootstrap_file_code(service), service.issue_bootstrap_code(label="cli")["code"]]
    if presented == "two_setup_codes":
        credentials: list[dict[str, Any]] = [{"bootstrap_code": code, "remote_ip": "203.0.113.7"} for code in codes]
    else:
        credentials = [{"remote_ip": "127.0.0.1"}, {"remote_ip": "127.0.0.1"}]

    # Both have checked that no owner exists, redeemed their credential and
    # recorded their writes before either transaction runs.
    outcomes = _concurrently(
        monkeypatch,
        service,
        "_insert_session",
        *(
            functools.partial(service.register_owner, email=email, password=STRONG_PASSWORD, **credential)
            for email, credential in zip(("first@example.com", "second@example.com"), credentials, strict=True)
        ),
    )

    succeeded, refused = _split(outcomes)
    assert len(succeeded) == 1, outcomes
    assert [type(exc) for exc in refused] == [ValueError], outcomes
    assert str(refused[0]) == "Owner account already exists. Sign in instead."
    owner = succeeded[0]
    assert [row["id"] for row in control_plane_db.fetch_all("SELECT id FROM cp_operator_users")] == [
        owner["operator"]["id"]
    ]
    assert _count("cp_operator_recovery_codes") == len(owner["recovery_codes"])
    assert _count("cp_operator_sessions") == 1
    consumed = {
        str(row["code_hash"]): bool(row["consumed_at"] or row["exchange_consumed_at"])
        for row in control_plane_db.fetch_all("SELECT * FROM cp_bootstrap_codes")
    }
    by_code = [
        consumed.get(operator_auth_mod._hash_secret(operator_auth_mod._normalize_bootstrap_code(code)))
        for code in codes
    ]
    if presented == "two_setup_codes":
        # The winner's code is spent; the loser's is left unused, as after any
        # failed registration, but once an owner exists no setup code registers anyone.
        assert by_code[outcomes.index(owner)] is True
        assert by_code[1 - outcomes.index(owner)] is False
    else:
        assert by_code == [None, False]
    for code in codes:
        with pytest.raises(ValueError, match=r"^Owner account already exists\. Sign in instead\.$"):
            service.register_owner(
                bootstrap_code=code, email="third@example.com", password=STRONG_PASSWORD, remote_ip="203.0.113.7"
            )


@pytest.mark.postgres
def test_concurrent_setup_code_exchanges_issue_one_registration_token(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-283: two exchanges racing with the same setup code issue one registration token, and it works."""
    service = operator_auth_mod.OperatorAuthService()
    code = service.issue_bootstrap_code(label="cli")["code"]

    outcomes = _concurrently(
        monkeypatch,
        service,
        "_redeemable_bootstrap_code",
        *(functools.partial(service.exchange_bootstrap_code, code) for _ in range(2)),
    )

    succeeded, refused = _split(outcomes)
    assert len(succeeded) == 1, outcomes
    assert [type(exc) for exc in refused] == [ValueError] and str(refused[0]) == "Setup code is invalid or expired."
    payload = operator_auth_mod.OperatorAuthService().register_owner(
        registration_token=succeeded[0]["registration_token"],
        email="cli@example.com",
        password=STRONG_PASSWORD,
    )
    assert payload["operator"]["email"] == "cli@example.com"


@pytest.mark.postgres
def test_concurrent_resets_with_one_recovery_code_apply_one_password(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-283: two password resets racing with the same recovery code: one applies, the other changes nothing."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    passwords = (ANOTHER_STRONG_PASSWORD, "Quantum#Lighthouse!77")

    outcomes = _concurrently(
        monkeypatch,
        service,
        "_validate_operator_password",
        *(
            functools.partial(
                service.reset_password_with_recovery_code, "owner", payload["recovery_codes"][0], password
            )
            for password in passwords
        ),
    )

    succeeded, refused = _split(outcomes)
    assert succeeded == [{"ok": True}], outcomes
    assert [type(exc) for exc in refused] == [ValueError] and str(refused[0]) == "Invalid identifier or recovery code."
    winner = outcomes.index({"ok": True})
    fresh = operator_auth_mod.OperatorAuthService()
    assert fresh.login(identifier="owner", password=passwords[winner])["operator"]["username"] == "owner"
    with pytest.raises(ValueError):
        fresh.login(identifier="owner", password=passwords[1 - winner])
    reasons = [row["consumed_reason"] for row in control_plane_db.fetch_all("SELECT * FROM cp_operator_recovery_codes")]
    assert reasons.count("password_reset") == 1
    assert reasons.count("password_reset_invalidation") == len(payload["recovery_codes"]) - 1


def _interleaved(monkeypatch: pytest.MonkeyPatch, first: Callable[[], Any], second: Callable[[], Any]) -> list[Any]:
    """Run ``first`` and ``second`` on their own threads, their transactions interleaved after their first statement.

    ``second`` starts once ``first``'s transaction has run its first
    statement. Each transaction then waits, up to 2 s, until the other has run
    its first statement too, as two control-plane processes can. Each outcome
    is the attempt's return value or the exception it raised.
    """
    from koda.state import control_plane_store

    started = threading.Event()
    barrier = threading.Barrier(2, timeout=2)
    original = control_plane_store.Transaction.execute

    async def _execute(self: Any, query: str, params: tuple[Any, ...] = ()) -> int:
        count = await original(self, query, params)
        if not getattr(self, "_koda_test_interleaved", False):
            self._koda_test_interleaved = True
            started.set()
            # A broken barrier: the other transaction waits on a lock this one holds.
            with contextlib.suppress(threading.BrokenBarrierError):
                await asyncio.to_thread(barrier.wait)
        return count

    monkeypatch.setattr(control_plane_store.Transaction, "execute", _execute)

    def _outcome(attempt: Callable[[], Any]) -> Any:
        try:
            return attempt()
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_outcome = pool.submit(_outcome, first)
        assert started.wait(timeout=20)
        second_outcome = pool.submit(_outcome, second)
        return [first_outcome.result(), second_outcome.result()]


@pytest.mark.postgres
def test_concurrent_resets_with_two_codes_of_one_account_do_not_deadlock(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two resets of one account with two valid codes: one applies, the other fails like any invalid code."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    passwords = (ANOTHER_STRONG_PASSWORD, "Quantum#Lighthouse!77")

    outcomes = _interleaved(
        monkeypatch,
        *(
            functools.partial(service.reset_password_with_recovery_code, "owner", code, password)
            for code, password in zip(payload["recovery_codes"][:2], passwords, strict=True)
        ),
    )

    assert outcomes[0] == {"ok": True}, outcomes
    assert type(outcomes[1]) is ValueError and str(outcomes[1]) == "Invalid identifier or recovery code.", outcomes
    fresh = operator_auth_mod.OperatorAuthService()
    assert fresh.login(identifier="owner", password=passwords[0])["operator"]["username"] == "owner"


@pytest.mark.postgres
def test_a_reset_and_a_regeneration_of_one_account_do_not_deadlock(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reset and a recovery-code regeneration of one account, interleaved: both complete."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    outcomes = _interleaved(
        monkeypatch,
        functools.partial(
            service.reset_password_with_recovery_code, "owner", payload["recovery_codes"][-1], ANOTHER_STRONG_PASSWORD
        ),
        functools.partial(service.regenerate_recovery_codes, context, current_password=STRONG_PASSWORD),
    )

    assert outcomes[0] == {"ok": True}, outcomes
    assert isinstance(outcomes[1], dict), outcomes
    assert len(outcomes[1]["recovery_codes"]) == len(payload["recovery_codes"])
    assert service.reset_password_with_recovery_code("owner", outcomes[1]["recovery_codes"][0], STRONG_PASSWORD) == {
        "ok": True
    }


@pytest.mark.postgres
@pytest.mark.parametrize("presented", ["bootstrap_code", "registration_token"])
def test_an_invalid_setup_credential_hashes_the_password_like_a_registration_that_loses_the_race(
    operator_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    presented: str,
) -> None:
    """A wrong code costs the password hash a registration that passed the code check and lost the race pays."""
    service = operator_auth_mod.OperatorAuthService()
    _bootstrap_file_code(service)
    hashes: list[str] = []
    real_hasher = operator_auth_mod._password_hasher()

    class _CountingHasher:
        def hash(self, password: str | bytes, **kwargs: Any) -> str:
            hashes.append(str(password))
            return real_hasher.hash(password, **kwargs)

        def __getattr__(self, name: str) -> Any:
            return getattr(real_hasher, name)

    monkeypatch.setattr(operator_auth_mod, "_password_hasher", functools.lru_cache(maxsize=1)(_CountingHasher))

    with pytest.raises(ValueError, match="is invalid or expired"):
        service.register_owner(
            email="vps@example.com",
            password=STRONG_PASSWORD,
            remote_ip="203.0.113.7",
            **{presented: "WRONG-WRONG-WRONG"},
        )

    assert len(hashes) == 1
    assert _count("cp_operator_users") == 0


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
def test_an_expired_bootstrap_file_no_longer_locks_setup(operator_db: Path) -> None:
    """D-195: past its TTL, the file is replaced at the next status request, and the new code works."""
    service = operator_auth_mod.OperatorAuthService()
    expired = _bootstrap_file_code(service)
    lines = operator_db.read_text(encoding="utf-8").splitlines()
    operator_db.write_text(
        "\n".join("expires_at=2000-01-01T00:00:00+00:00" if line.startswith("expires_at=") else line for line in lines),
        encoding="utf-8",
    )
    owner = {"email": "vps@example.com", "password": STRONG_PASSWORD, "remote_ip": "203.0.113.7"}
    with pytest.raises(ValueError, match=r"^Setup code is invalid or expired\.$"):
        service.register_owner(bootstrap_code=expired, **owner)

    fresh = _bootstrap_file_code(service)

    assert fresh != expired
    assert service.register_owner(bootstrap_code=fresh, **owner)["operator"]["email"] == "vps@example.com"
    assert not operator_db.exists()
    service.onboarding_payload()
    assert not operator_db.exists(), "an install with an owner never writes a setup code"


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

    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password="wrong")

    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password="wrong")

    # After lockout, even the correct password returns the same generic error,
    # never "temporarily locked" — avoid leaking lock state to the caller.
    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password=STRONG_PASSWORD)


@pytest.mark.postgres
def test_login_never_reveals_account_disabled(operator_db: Path) -> None:
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    control_plane_db.execute("UPDATE cp_operator_users SET disabled = 1 WHERE id = ?", (payload["operator"]["id"],))
    with pytest.raises(ValueError, match="Invalid credentials"):
        service.login(identifier="owner", password=STRONG_PASSWORD)


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
    with pytest.raises(ValueError, match="Invalid credentials"):
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
        assert stale.status == 400
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
def test_password_reset_fault_changes_nothing(operator_db: Path) -> None:
    """D-056: when revoking sessions fails, the password, the recovery codes and the sessions stay as they were."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    reset = {
        "identifier": "owner",
        "recovery_code": payload["recovery_codes"][0],
        "new_password": ANOTHER_STRONG_PASSWORD,
    }

    with injected_fault("cp_operator_sessions", "UPDATE"), pytest.raises(Exception, match="injected fault"):
        service.reset_password_with_recovery_code(**reset)

    unused = control_plane_db.fetch_one(
        "SELECT COUNT(*) AS count FROM cp_operator_recovery_codes WHERE consumed_at = ''",
    )
    assert unused is not None and int(unused["count"]) == len(payload["recovery_codes"])
    assert service.resolve_bearer_token(payload["session_token"]) is not None
    assert service.login(identifier="owner", password=STRONG_PASSWORD)["operator"]["username"] == "owner"
    assert service.reset_password_with_recovery_code(**reset) == {"ok": True}
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
def test_change_password_fault_changes_nothing(operator_db: Path) -> None:
    """D-284: when revoking the other sessions fails, the password and the sessions stay as they were."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None
    other_login = service.login(identifier="owner", password=STRONG_PASSWORD)
    password_hash = _user_row(payload["operator"]["id"])["password_hash"]

    with injected_fault("cp_operator_sessions", "UPDATE"), pytest.raises(Exception, match="injected fault"):
        service.change_password(context, current_password=STRONG_PASSWORD, new_password=ANOTHER_STRONG_PASSWORD)

    assert _user_row(payload["operator"]["id"])["password_hash"] == password_hash
    assert service.resolve_bearer_token(other_login["session_token"]) is not None
    service.change_password(context, current_password=STRONG_PASSWORD, new_password=ANOTHER_STRONG_PASSWORD)
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
def test_regenerate_recovery_codes_fault_keeps_the_current_codes(operator_db: Path) -> None:
    """D-284: when storing the new batch fails partway, the current codes stay usable and no new code is kept."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None
    generation = _user_row(payload["operator"]["id"])["recovery_generation"]
    second_new_code = len(payload["recovery_codes"]) + 1

    with (
        injected_fault("cp_operator_recovery_codes", "INSERT", rows_before=second_new_code),
        pytest.raises(Exception, match="injected fault"),
    ):
        service.regenerate_recovery_codes(context, current_password=STRONG_PASSWORD)

    assert _user_row(payload["operator"]["id"])["recovery_generation"] == generation
    assert _count("cp_operator_recovery_codes") == len(payload["recovery_codes"])
    summary = service.recovery_codes_summary(context)
    assert summary["remaining"] == summary["total"] == len(payload["recovery_codes"])
    assert service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=payload["recovery_codes"][0],
        new_password=ANOTHER_STRONG_PASSWORD,
    ) == {"ok": True}


@pytest.mark.postgres
def test_concurrent_regenerations_store_one_batch(
    operator_db: Path,
    bridge_loop: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-295: a double-submitted regeneration stores one batch, the one returned; the other request changes nothing."""
    service = operator_auth_mod.OperatorAuthService()
    payload = _create_owner(service)
    context = service.resolve_bearer_token(payload["session_token"])
    assert context is not None

    # Both have read the current generation and recorded their writes before either transaction runs.
    outcomes = _concurrently(
        monkeypatch,
        service,
        "_issue_recovery_codes",
        *(
            functools.partial(service.regenerate_recovery_codes, context, current_password=STRONG_PASSWORD)
            for _ in range(2)
        ),
    )

    succeeded, refused = _split(outcomes)
    assert len(succeeded) == 1, outcomes
    assert [type(exc) for exc in refused] == [ValueError], outcomes
    assert str(refused[0]) == "Recovery codes were regenerated by another request. Try again."
    new_codes = succeeded[0]["recovery_codes"]
    assert _count("cp_operator_recovery_codes") == len(payload["recovery_codes"]) + len(new_codes)
    summary = service.recovery_codes_summary(context)
    assert summary["remaining"] == summary["total"] == len(new_codes)
    assert service.reset_password_with_recovery_code(
        identifier="owner",
        recovery_code=new_codes[0],
        new_password=ANOTHER_STRONG_PASSWORD,
    ) == {"ok": True}


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
        _REPO_ROOT / "docs" / "security" / "authentication.md",
        _REPO_ROOT / "apps" / "web" / "CLAUDE.md",
        _REPO_ROOT / "docs" / "install" / "vps.md",
    ],
    ids=lambda path: f"{path.parent.name}/{path.name}",
)
def test_docs_mark_the_login_timing_floor_as_pending(path: Path) -> None:
    """D-136: nothing pads failed logins to a time floor yet, so no doc may say they take equal time.

    An unknown identifier or a locked account fails before any password hash is checked, so it
    answers faster than a wrong password. M1-E1-T13 adds the floor, then updates these docs and
    this test.
    """
    assert operator_auth_mod._FAILURE_TIMING_FLOOR_SECONDS == 0.0
    text = " ".join(path.read_text(encoding="utf-8").split())

    assert "timing floor pending M1-E1-T13" in text
    assert "All auth-failure paths pad" not in text
    assert "neutralize timing" not in text
    assert "deliberately slowed" not in text
