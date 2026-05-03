"""Pure-logic tests for scheduled_jobs and scheduled_job_runtime helpers.

Covers (no DB, no asyncio):

  * _parse_interval_seconds — every supported suffix + invalid inputs
  * _normalize_timezone_name — IANA validation + default fallback
  * compute_next_run — interval, one_shot, cron with timezone & DST edges
  * _scheduler_retry_delay — exponential backoff formula and cap

These functions are the schedule contract surface; if any of them drift,
every dispatch decision will misfire silently. Table-driven cases pin
the behavior so changes are deliberate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from koda.services.scheduled_job_runtime import _scheduler_retry_delay
from koda.services.scheduled_jobs import (
    SCHEDULER_RETRY_BASE_DELAY,
    SCHEDULER_RETRY_MAX_DELAY,
    _normalize_timezone_name,
    _parse_interval_seconds,
    compute_next_run,
)

# ---------------------------------------------------------------------------
# _parse_interval_seconds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr,expected",
    [
        # Plain seconds
        ("0", 0),
        ("1", 1),
        ("60", 60),
        ("3600", 3600),
        # `every` prefix is stripped (lowercase)
        ("every 30", 30),
        ("Every 30", 30),
        ("EVERY 30", 30),
        # Suffixes
        ("30s", 30),
        ("60s", 60),
        ("1m", 60),
        ("5m", 300),
        ("1h", 3600),
        ("2h", 7200),
        ("1d", 86400),
        ("7d", 7 * 86400),
        # Whitespace tolerated
        ("  60  ", 60),
        ("  1h  ", 3600),
        # Mixed-case suffix is accepted via lowercasing
        ("1H", 3600),
        ("5M", 300),
    ],
)
def test_parse_interval_seconds_valid(expr: str, expected: int) -> None:
    assert _parse_interval_seconds(expr) == expected


@pytest.mark.parametrize(
    "expr",
    [
        "",
        "abc",
        "1.5h",  # float not supported
        "1y",  # year not supported
        "every",  # missing value
        "30 seconds",  # spelled-out unit not supported
        "-30",
        "1.0",
    ],
)
def test_parse_interval_seconds_invalid(expr: str) -> None:
    assert _parse_interval_seconds(expr) is None


# ---------------------------------------------------------------------------
# _normalize_timezone_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given",
    ["UTC", "America/Sao_Paulo", "Europe/London", "Asia/Tokyo", "Australia/Sydney"],
)
def test_normalize_timezone_name_passthrough_known(given: str) -> None:
    assert _normalize_timezone_name(given) == given


def test_normalize_timezone_name_default_when_empty() -> None:
    # Empty input falls back to SCHEDULER_DEFAULT_TIMEZONE which is itself a
    # valid IANA name — so the function returns *some* IANA-loadable string.
    out_empty = _normalize_timezone_name("")
    out_none = _normalize_timezone_name(None)
    assert out_empty
    assert out_empty == out_none


@pytest.mark.parametrize("bad", ["NotARealZone", "Mars/Olympus_Mons", "America/NotACity"])
def test_normalize_timezone_name_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError, match="Invalid timezone"):
        _normalize_timezone_name(bad)


# ---------------------------------------------------------------------------
# compute_next_run — interval
# ---------------------------------------------------------------------------


def test_compute_next_run_interval_basic() -> None:
    after = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="interval", schedule_expr="3600", timezone_name="UTC", after=after
    )
    assert nxt == after + timedelta(seconds=3600)


def test_compute_next_run_interval_with_suffix() -> None:
    after = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(trigger_type="interval", schedule_expr="2h", timezone_name="UTC", after=after)
    assert nxt == after + timedelta(hours=2)


def test_compute_next_run_interval_invalid_returns_none() -> None:
    assert (
        compute_next_run(trigger_type="interval", schedule_expr="bogus", timezone_name="UTC")
        is None
    )


def test_compute_next_run_interval_zero_returns_none() -> None:
    assert (
        compute_next_run(trigger_type="interval", schedule_expr="0", timezone_name="UTC")
        is None
    )


# ---------------------------------------------------------------------------
# compute_next_run — one_shot
# ---------------------------------------------------------------------------


def test_compute_next_run_one_shot_future() -> None:
    after = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    target = "2026-05-15T08:30:00+00:00"
    nxt = compute_next_run(
        trigger_type="one_shot", schedule_expr=target, timezone_name="UTC", after=after
    )
    assert nxt is not None
    assert nxt == datetime(2026, 5, 15, 8, 30, 0, tzinfo=UTC)


def test_compute_next_run_one_shot_past_returns_none() -> None:
    after = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="one_shot",
        schedule_expr="2025-01-01T00:00:00+00:00",
        timezone_name="UTC",
        after=after,
    )
    assert nxt is None


# ---------------------------------------------------------------------------
# compute_next_run — cron with timezone & DST edges
# ---------------------------------------------------------------------------


def test_compute_next_run_cron_daily_utc() -> None:
    after = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="cron", schedule_expr="0 2 * * *", timezone_name="UTC", after=after
    )
    assert nxt == datetime(2026, 5, 2, 2, 0, 0, tzinfo=UTC)


def test_compute_next_run_cron_daily_brazil() -> None:
    """02:00 in America/Sao_Paulo — Brazil dropped permanent DST in 2019, so
    UTC offset is fixed at -03:00 year-round."""
    after = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="cron",
        schedule_expr="0 2 * * *",
        timezone_name="America/Sao_Paulo",
        after=after,
    )
    # Next 02:00 BRT after 2026-05-01 00:00 UTC = 2026-05-01 05:00 UTC
    assert nxt == datetime(2026, 5, 1, 5, 0, 0, tzinfo=UTC)


def test_compute_next_run_cron_returns_utc_with_matching_offset() -> None:
    """Crossing into summer-time in Europe/London (BST = UTC+1).

    Cron `0 9 * * *` in Europe/London after 2026-04-15 (BST) yields
    08:00 UTC, not 09:00 UTC.
    """
    after = datetime(2026, 4, 15, 0, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="cron",
        schedule_expr="0 9 * * *",
        timezone_name="Europe/London",
        after=after,
    )
    # 09:00 BST == 08:00 UTC.
    assert nxt is not None
    assert nxt.tzinfo is UTC
    assert nxt == datetime(2026, 4, 15, 8, 0, 0, tzinfo=UTC)


def test_compute_next_run_cron_hourly() -> None:
    after = datetime(2026, 5, 1, 12, 30, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="cron", schedule_expr="0 * * * *", timezone_name="UTC", after=after
    )
    assert nxt == datetime(2026, 5, 1, 13, 0, 0, tzinfo=UTC)


def test_compute_next_run_cron_monthly() -> None:
    after = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    nxt = compute_next_run(
        trigger_type="cron",
        schedule_expr="0 0 1 * *",  # 1st of every month at midnight
        timezone_name="UTC",
        after=after,
    )
    assert nxt == datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# compute_next_run — invalid trigger_type returns None
# ---------------------------------------------------------------------------


def test_compute_next_run_unknown_trigger_returns_none() -> None:
    assert (
        compute_next_run(trigger_type="weekly", schedule_expr="anything", timezone_name="UTC")
        is None
    )


# ---------------------------------------------------------------------------
# _scheduler_retry_delay — exponential backoff formula
# ---------------------------------------------------------------------------


def test_scheduler_retry_delay_attempt_1() -> None:
    """First retry uses base delay (no doubling yet)."""
    assert _scheduler_retry_delay(1) == SCHEDULER_RETRY_BASE_DELAY


def test_scheduler_retry_delay_attempt_2_doubles() -> None:
    expected = min(SCHEDULER_RETRY_BASE_DELAY * 2, SCHEDULER_RETRY_MAX_DELAY)
    assert _scheduler_retry_delay(2) == expected


def test_scheduler_retry_delay_attempt_3_quadruples() -> None:
    expected = min(SCHEDULER_RETRY_BASE_DELAY * 4, SCHEDULER_RETRY_MAX_DELAY)
    assert _scheduler_retry_delay(3) == expected


def test_scheduler_retry_delay_capped_at_max() -> None:
    """Very high attempt counts saturate at SCHEDULER_RETRY_MAX_DELAY."""
    assert _scheduler_retry_delay(20) == SCHEDULER_RETRY_MAX_DELAY
    assert _scheduler_retry_delay(50) == SCHEDULER_RETRY_MAX_DELAY


def test_scheduler_retry_delay_attempt_zero_or_negative_treated_as_first_retry() -> None:
    """attempt=0 and negatives are clamped to behave like attempt=1 (base delay)."""
    assert _scheduler_retry_delay(0) == SCHEDULER_RETRY_BASE_DELAY
    assert _scheduler_retry_delay(-5) == SCHEDULER_RETRY_BASE_DELAY


def test_scheduler_retry_delay_monotonic_until_cap() -> None:
    delays = [_scheduler_retry_delay(i) for i in range(1, 12)]
    # Strictly non-decreasing.
    for a, b in zip(delays, delays[1:], strict=False):
        assert a <= b
    # Eventually hits the cap.
    assert delays[-1] == SCHEDULER_RETRY_MAX_DELAY
