"""Observability dashboard."""

from __future__ import annotations

from koda.dashboard.aggregator import DashboardAggregator

_aggregator: DashboardAggregator | None = None


def get_aggregator() -> DashboardAggregator:
    global _aggregator  # noqa: PLW0603
    if _aggregator is None:
        _aggregator = DashboardAggregator()
    return _aggregator


__all__ = ["DashboardAggregator", "get_aggregator"]
