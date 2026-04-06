"""Dashboard data aggregation."""

from __future__ import annotations

import time

from koda.logging_config import get_logger

log = get_logger(__name__)


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


class DashboardAggregator:
    """Collects tool execution metrics for observability."""

    def __init__(self) -> None:
        self._tool_usage: dict[str, int] = {}
        self._error_log: list[dict[str, object]] = []
        self._cost_log: list[dict[str, object]] = []
        self._max_log = 500

    def record_tool_execution(
        self,
        tool: str,
        success: bool,
        duration_ms: float | None = None,
        cost_usd: float | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._tool_usage[tool] = self._tool_usage.get(tool, 0) + 1
        if cost_usd and cost_usd > 0:
            self._cost_log.append(
                {
                    "tool": tool,
                    "cost_usd": cost_usd,
                    "agent_id": agent_id,
                    "timestamp": time.time(),
                }
            )
            if len(self._cost_log) > self._max_log:
                self._cost_log = self._cost_log[-self._max_log :]
        if not success:
            self._error_log.append(
                {
                    "tool": tool,
                    "agent_id": agent_id,
                    "timestamp": time.time(),
                    "duration_ms": duration_ms,
                }
            )
            if len(self._error_log) > self._max_log:
                self._error_log = self._error_log[-self._max_log :]

    def get_tool_stats(self, sort_by: str = "usage", limit: int = 50) -> list[dict[str, object]]:
        stats: list[dict[str, object]] = [{"tool": t, "call_count": c} for t, c in self._tool_usage.items()]
        if sort_by == "usage":
            stats.sort(key=lambda item: int(_coerce_float(item.get("call_count"))), reverse=True)
        return stats[:limit]

    def get_recent_errors(self, limit: int = 20) -> list[dict[str, object]]:
        return self._error_log[-limit:]

    def get_cost_summary(self, period_hours: int = 24, group_by: str = "agent") -> dict[str, object]:
        cutoff = time.time() - (period_hours * 3600)
        recent = [c for c in self._cost_log if _coerce_float(c.get("timestamp")) >= cutoff]
        total = sum(_coerce_float(c.get("cost_usd")) for c in recent)
        groups: dict[str, float] = {}
        for c in recent:
            key = str(c.get(group_by) or c.get("agent_id") or "unknown")
            groups[key] = groups.get(key, 0) + _coerce_float(c.get("cost_usd"))
        return {
            "period_hours": period_hours,
            "total_cost_usd": round(total, 6),
            "event_count": len(recent),
            "by_group": groups,
        }

    def get_overview(self) -> dict[str, int]:
        return {
            "total_tool_calls": sum(self._tool_usage.values()),
            "unique_tools_used": len(self._tool_usage),
            "total_errors": len(self._error_log),
        }

    def health_check(self) -> dict[str, object]:
        return {
            "status": "healthy",
            "total_tool_calls": sum(self._tool_usage.values()),
            "error_count": len(self._error_log),
        }
