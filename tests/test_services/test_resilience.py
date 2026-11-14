"""Tests for circuit breaker resilience module."""

from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pybreaker
import pytest

from koda.services import resilience
from koda.services.resilience import (
    ALL_BREAKERS,
    CircuitOpenError,
    check_breaker,
    get_breaker_states,
    http_external_breaker,
    record_failure,
    record_success,
)


def _close_shared_breakers() -> None:
    for breaker in ALL_BREAKERS.values():
        with suppress(Exception):
            breaker.close()
    # Drop recovery timing too, so fake-clock timings never leak between tests.
    resilience._gates.clear()


@pytest.fixture(autouse=True)
def _reset_shared_breakers():
    _close_shared_breakers()
    yield
    _close_shared_breakers()


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock()
    monkeypatch.setattr(resilience, "_clock", fake)
    return fake


def _tripped_breaker(name: str, *, reset_timeout: float = 60) -> pybreaker.CircuitBreaker:
    # reset_timeout is far beyond the test's wall-clock runtime, so recovery can
    # only come from the controllable clock, never from pybreaker's own timer.
    breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=reset_timeout, name=name)
    record_failure(breaker)
    record_failure(breaker)
    assert breaker.current_state == "open"
    return breaker


class TestCircuitBreakers:
    def test_all_breakers_registered(self):
        expected = {
            "claude_cli",
            "codex_cli",
            "telegram_api",
            "postgres",
            "browser",
            "http_external",
            "memory_vector",
            "elevenlabs",
            "scheduler_dispatcher",
        }
        assert set(ALL_BREAKERS.keys()) == expected

    def test_breakers_start_closed(self):
        states = get_breaker_states()
        for name, state in states.items():
            assert state == "closed", f"{name} should start closed"


class TestCheckBreaker:
    def test_closed_returns_none(self):
        breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10, name="test_closed")
        assert check_breaker(breaker) is None

    def test_open_returns_error_message(self):
        breaker = pybreaker.CircuitBreaker(fail_max=1, reset_timeout=999, name="test_open")
        # Force open by failing
        for _ in range(2):
            with suppress(Exception):
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        if str(breaker.current_state) == "open":
            result = check_breaker(breaker)
            assert result is not None
            assert "circuit breaker open" in result


class TestRecordOutcome:
    def test_record_success_does_not_raise(self):
        breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10, name="test_success")
        record_success(breaker)

    def test_record_failure_does_not_raise(self):
        breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10, name="test_failure")
        record_failure(breaker)


class TestCircuitOpenError:
    def test_error_message(self):
        err = CircuitOpenError("postgres")
        assert err.dependency == "postgres"
        assert "postgres" in str(err)
        assert "circuit breaker" in str(err)


class TestBreakerLifecycle:
    def test_breaker_opens_after_fail_max(self):
        breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=999, name="test_lifecycle_open")
        for _ in range(3):
            record_failure(breaker)
        assert str(breaker.current_state) == "open"
        err = check_breaker(breaker)
        assert err is not None
        assert "circuit breaker open" in err

    def test_record_success_keeps_closed(self):
        breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60, name="test_lifecycle_closed")
        assert str(breaker.current_state) == "closed"
        record_success(breaker)
        assert str(breaker.current_state) == "closed"


class TestGetBreakerStates:
    def test_returns_dict(self):
        states = get_breaker_states()
        assert isinstance(states, dict)
        assert len(states) == len(ALL_BREAKERS)


class TestHalfOpenRecovery:
    """Drive the check -> record pattern every call site uses through a real outage."""

    def test_single_probe_after_reset_timeout_closes_on_success(self, clock):
        breaker = _tripped_breaker("test_probe_success", reset_timeout=3600)

        assert check_breaker(breaker) is not None
        clock.advance(3599.9)
        assert check_breaker(breaker) is not None
        assert breaker.current_state == "open"

        clock.advance(0.1)
        assert check_breaker(breaker) is None  # this caller is the probe
        assert breaker.current_state == "half-open"
        assert check_breaker(breaker) is not None  # concurrent caller rejected while probing

        record_success(breaker)
        assert breaker.current_state == "closed"
        assert check_breaker(breaker) is None
        assert check_breaker(breaker) is None

    def test_failed_probe_reopens_for_another_full_timeout(self, clock):
        breaker = _tripped_breaker("test_probe_failure")

        clock.advance(60)
        assert check_breaker(breaker) is None
        record_failure(breaker)
        assert breaker.current_state == "open"

        clock.advance(59)
        assert check_breaker(breaker) is not None
        clock.advance(1)
        assert check_breaker(breaker) is None
        record_success(breaker)
        assert breaker.current_state == "closed"

    def test_probe_without_outcome_frees_slot_after_reset_timeout(self, clock):
        breaker = _tripped_breaker("test_probe_lost")

        clock.advance(60)
        assert check_breaker(breaker) is None  # probe admitted, never reports back
        clock.advance(59)
        assert check_breaker(breaker) is not None
        clock.advance(1)
        assert check_breaker(breaker) is None  # replacement probe
        record_success(breaker)
        assert breaker.current_state == "closed"

    def test_stragglers_while_open_neither_close_nor_extend_window(self, clock):
        breaker = _tripped_breaker("test_stragglers")

        clock.advance(30)
        record_success(breaker)  # call admitted before the trip finishing late
        assert breaker.current_state == "open"
        record_failure(breaker)
        assert breaker.current_state == "open"

        clock.advance(30)
        assert check_breaker(breaker) is None
        assert breaker.current_state == "half-open"

    def test_directly_opened_breaker_recovers(self, clock):
        breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60, name="test_direct_open")
        breaker.open()

        assert check_breaker(breaker) is not None
        clock.advance(60)
        assert check_breaker(breaker) is None
        record_success(breaker)
        assert breaker.current_state == "closed"

    def test_reopened_breaker_gets_a_fresh_timeout(self, clock):
        breaker = _tripped_breaker("test_reopen_direct")

        clock.advance(60)
        # Closed and re-opened directly with no check in between: the earlier
        # episode's timing must not let the new episode probe immediately.
        breaker.close()
        breaker.open()
        assert check_breaker(breaker) is not None
        assert breaker.current_state == "open"

        clock.advance(59)
        assert check_breaker(breaker) is not None
        clock.advance(1)
        assert check_breaker(breaker) is None
        assert breaker.current_state == "half-open"

    def test_reopened_after_probe_rejects_until_new_timeout(self, clock):
        breaker = _tripped_breaker("test_reopen_after_probe")

        clock.advance(60)
        assert check_breaker(breaker) is None  # probe admitted
        breaker.close()
        breaker.open()  # tripped again without record_failure
        assert check_breaker(breaker) is not None
        clock.advance(60)
        assert check_breaker(breaker) is None


class TestStateChangeAudit:
    def test_each_transition_emits_its_own_event(self, clock):
        breaker = pybreaker.CircuitBreaker(
            fail_max=1, reset_timeout=60, name="test_audit_events", listeners=[resilience._listener]
        )
        with patch("koda.services.audit.emit_task_lifecycle") as emit:
            record_failure(breaker)  # closed -> open
            clock.advance(60)
            assert check_breaker(breaker) is None  # open -> half-open
            record_failure(breaker)  # half-open -> open
            clock.advance(60)
            assert check_breaker(breaker) is None  # open -> half-open
            record_success(breaker)  # half-open -> closed

        events = [(c.args[0], c.kwargs["old_state"], c.kwargs["new_state"]) for c in emit.call_args_list]
        assert events == [
            ("system.circuit_opened", "closed", "open"),
            ("system.circuit_half_open", "open", "half-open"),
            ("system.circuit_opened", "half-open", "open"),
            ("system.circuit_half_open", "open", "half-open"),
            ("system.circuit_closed", "half-open", "closed"),
        ]


class TestCallSiteRecovery:
    async def test_web_search_resumes_after_transient_outage(self, clock):
        from koda.services.tool_dispatcher import ToolContext, _handle_web_search

        ctx = ToolContext(user_id=1, chat_id=1, work_dir="/tmp", user_data={}, agent=None, agent_mode="normal")
        search = AsyncMock(return_value="Error: upstream down")
        with patch("koda.services.http_client.search_web", search):
            for _ in range(http_external_breaker.fail_max):
                result = await _handle_web_search({"query": "koda"}, ctx)
                assert not result.success
            assert http_external_breaker.current_state == "open"

            calls_before = search.await_count
            rejected = await _handle_web_search({"query": "koda"}, ctx)
            assert "circuit breaker open" in rejected.output
            assert search.await_count == calls_before

            search.return_value = "1. Koda - result"
            clock.advance(http_external_breaker.reset_timeout)
            probe = await _handle_web_search({"query": "koda"}, ctx)
            assert probe.success
            assert search.await_count == calls_before + 1
            assert http_external_breaker.current_state == "closed"

            follow_up = await _handle_web_search({"query": "koda"}, ctx)
            assert follow_up.success
