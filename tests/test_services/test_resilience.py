"""Tests for circuit breaker resilience module."""

from contextlib import suppress

import pybreaker

from koda.services.resilience import (
    ALL_BREAKERS,
    CircuitOpenError,
    check_breaker,
    get_breaker_states,
    record_failure,
    record_success,
)


class TestCircuitBreakers:
    def test_all_breakers_registered(self):
        expected = {
            "claude_cli",
            "codex_cli",
            "telegram_api",
            "jira",
            "confluence",
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
        err = CircuitOpenError("jira")
        assert err.dependency == "jira"
        assert "jira" in str(err)
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

    def test_breaker_recovers_after_reset_timeout(self):
        breaker = pybreaker.CircuitBreaker(fail_max=1, reset_timeout=0, name="test_lifecycle_recover")
        record_failure(breaker)
        # With reset_timeout=0, the breaker should immediately transition to half-open
        # and allow a success to close it
        record_success(breaker)
        assert str(breaker.current_state) == "closed"

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
