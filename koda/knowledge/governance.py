"""Periodic runbook governance for lifecycle revalidation and audit."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from koda.config import (
    AGENT_ID,
    RUNBOOK_REVALIDATION_CORRECTION_THRESHOLD,
    RUNBOOK_REVALIDATION_MIN_SUCCESS_RATE,
    RUNBOOK_REVALIDATION_MIN_VERIFIED_RUNS,
    RUNBOOK_REVALIDATION_ROLLBACK_THRESHOLD,
    RUNBOOK_REVALIDATION_STALE_DAYS,
)
from koda.logging_config import get_logger
from koda.state.knowledge_governance_store import (
    get_execution_reliability_stats,
    list_approved_runbooks,
    set_runbook_lifecycle_status,
)

log = get_logger(__name__)


def _scope(agent_id: str | None = None) -> str:
    normalized = (agent_id or AGENT_ID or "default").strip().lower()
    return normalized or "default"


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _reliability_snapshot(runbook: dict[str, Any]) -> dict[str, Any]:
    stats = get_execution_reliability_stats(
        agent_id=str(runbook.get("agent_id") or "") or None,
        task_kind=str(runbook.get("task_kind") or "general"),
        project_key=str(runbook.get("project_key") or ""),
        environment=str(runbook.get("environment") or ""),
    )
    total_runs = int(stats.get("total_runs", 0) or 0)
    successful_runs = int(stats.get("successful_runs", 0) or 0)
    success_rate = (successful_runs / total_runs) if total_runs else 0.0
    last_validated_at = _parse_iso(runbook.get("last_validated_at")) or _parse_iso(runbook.get("approved_at"))
    age_days = (datetime.now() - last_validated_at).days if last_validated_at else None
    return {
        **stats,
        "success_rate": round(success_rate, 4),
        "age_days": age_days,
        "valid_until": runbook.get("valid_until"),
        "last_validated_at": runbook.get("last_validated_at") or runbook.get("approved_at"),
        "current_status": str(runbook.get("lifecycle_status") or runbook.get("status") or "approved"),
    }


def _review_reasons(runbook: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    age_days = snapshot.get("age_days")
    if isinstance(age_days, int) and age_days >= RUNBOOK_REVALIDATION_STALE_DAYS:
        reasons.append("source_aged")
    validated_at = _parse_iso(snapshot.get("last_validated_at"))
    within_grace_window = bool(validated_at and (datetime.now() - validated_at).days < RUNBOOK_REVALIDATION_STALE_DAYS)
    if not within_grace_window and int(snapshot.get("verified_runs", 0) or 0) < RUNBOOK_REVALIDATION_MIN_VERIFIED_RUNS:
        reasons.append("insufficient_verified_runs")
    if int(snapshot.get("total_runs", 0) or 0) > 0 and float(snapshot.get("success_rate", 0.0) or 0.0) < (
        RUNBOOK_REVALIDATION_MIN_SUCCESS_RATE
    ):
        reasons.append("low_success_rate")
    if int(snapshot.get("correction_count", 0) or 0) >= RUNBOOK_REVALIDATION_CORRECTION_THRESHOLD:
        reasons.append("correction_threshold_exceeded")
    if int(snapshot.get("rollback_count", 0) or 0) >= RUNBOOK_REVALIDATION_ROLLBACK_THRESHOLD:
        reasons.append("rollback_threshold_exceeded")
    return reasons


async def run_runbook_governance(agent_id: str | None = None) -> dict[str, int]:
    """Evaluate approved runbooks and downgrade stale or risky lifecycle states."""
    scope = _scope(agent_id)
    started = time.monotonic()
    runbooks = list_approved_runbooks(agent_id=scope, status=None, enforce_valid_window=False, limit=500)
    superseded_ids = {int(item["supersedes_runbook_id"]) for item in runbooks if item.get("supersedes_runbook_id")}
    summary = {
        "scanned": 0,
        "expired": 0,
        "needs_review": 0,
        "deprecated": 0,
    }

    for runbook in runbooks:
        runbook_id = int(runbook["id"])
        current_status = str(runbook.get("lifecycle_status") or runbook.get("status") or "approved")
        summary["scanned"] += 1
        if current_status == "deprecated":
            continue
        snapshot = _reliability_snapshot(runbook)
        valid_until = _parse_iso(runbook.get("valid_until"))

        if runbook_id in superseded_ids and current_status != "deprecated":
            if set_runbook_lifecycle_status(
                runbook_id,
                status="deprecated",
                reviewer="system:runbook_governance",
                reason="superseded_by_newer_runbook",
                metrics_snapshot=snapshot,
            ):
                summary["deprecated"] += 1
            continue

        if valid_until is not None and valid_until < datetime.now() and current_status != "expired":
            if set_runbook_lifecycle_status(
                runbook_id,
                status="expired",
                reviewer="system:runbook_governance",
                reason="valid_until_elapsed",
                metrics_snapshot=snapshot,
            ):
                summary["expired"] += 1
            continue

        reasons = _review_reasons(runbook, snapshot)
        if (
            reasons
            and current_status == "approved"
            and set_runbook_lifecycle_status(
                runbook_id,
                status="needs_review",
                reviewer="system:runbook_governance",
                reason=",".join(reasons),
                metrics_snapshot=snapshot,
            )
        ):
            summary["needs_review"] += 1

    elapsed = time.monotonic() - started
    try:
        from koda.services import metrics

        metrics.RUNBOOK_GOVERNANCE_LATENCY.labels(agent_id=scope).observe(elapsed)
    except Exception:
        log.debug("runbook_governance_latency_metric_error", exc_info=True)
    log.info("runbook_governance_complete", agent_id=scope, elapsed_seconds=round(elapsed, 3), **summary)
    return summary
