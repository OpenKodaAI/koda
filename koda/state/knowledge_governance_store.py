"""Knowledge governance and review state store over the shared primary backend."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from koda.config import AGENT_ID, RUNBOOK_REVALIDATION_STALE_DAYS
from koda.logging_config import get_logger
from koda.state.memory_store import increment_memory_quality_counter
from koda.state_primary import (
    get_primary_state_backend,
    postgres_primary_mode,
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    run_coro_sync,
)

log = get_logger(__name__)


@contextmanager
def _compat_backend_removed_conn() -> Iterator[Any]:
    raise RuntimeError("knowledge_governance_compat_backend_removed")
    yield


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _scope(agent_id: str | None = None) -> str:
    normalized = str(agent_id or AGENT_ID or "default").strip().lower()
    return normalized or "default"


def _primary_enabled(agent_id: str | None = None) -> bool:
    return postgres_primary_mode() and get_primary_state_backend(agent_id=_scope(agent_id)) is not None


def _primary_agent_id(agent_id: str | None = None) -> str:
    return _scope(agent_id)


def _parse_iso_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _runbook_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "agent_id": row.get("agent_id"),
            "runbook_key": row.get("runbook_key") or "",
            "version": int(row.get("version") or 1),
            "title": row.get("title") or "",
            "task_kind": row.get("task_kind") or "",
            "summary": row.get("summary") or "",
            "prerequisites": _json_loads(row.get("prerequisites_json"), []),
            "steps": _json_loads(row.get("steps_json"), []),
            "verification": _json_loads(row.get("verification_json"), []),
            "rollback": row.get("rollback") or "",
            "source_refs": _json_loads(row.get("source_refs_json"), []),
            "project_key": row.get("project_key") or "",
            "environment": row.get("environment") or "",
            "team": row.get("team") or "",
            "owner": row.get("owner") or "",
            "approved_by": row.get("approved_by") or "",
            "approved_at": row.get("approved_at"),
            "last_validated_by": row.get("last_validated_by") or "",
            "last_validated_at": row.get("last_validated_at") or row.get("approved_at"),
            "status": row.get("status") or "approved",
            "lifecycle_status": row.get("lifecycle_status") or "approved",
            "valid_from": row.get("valid_from"),
            "valid_until": row.get("valid_until"),
            "rollout_scope": _json_loads(row.get("rollout_scope_json"), {}),
            "policy_overrides": _json_loads(row.get("policy_overrides_json"), {}),
            "supersedes_runbook_id": row.get("supersedes_runbook_id"),
            "source_candidate_id": row.get("source_candidate_id"),
        }
    return {
        "id": row[0],
        "agent_id": row[1],
        "runbook_key": row[2] or "",
        "version": int(row[3] or 1),
        "title": row[4],
        "task_kind": row[5],
        "summary": row[6] or "",
        "prerequisites": _json_loads(row[7], []),
        "steps": _json_loads(row[8], []),
        "verification": _json_loads(row[9], []),
        "rollback": row[10] or "",
        "source_refs": _json_loads(row[11], []),
        "project_key": row[12] or "",
        "environment": row[13] or "",
        "team": row[14] or "",
        "owner": row[15] or "",
        "approved_by": row[16] or "",
        "approved_at": row[17],
        "last_validated_by": row[18] or "",
        "last_validated_at": row[19] or row[17],
        "status": row[20] or "approved",
        "lifecycle_status": row[21] or "approved",
        "valid_from": row[22],
        "valid_until": row[23],
        "rollout_scope": _json_loads(row[24], {}),
        "policy_overrides": _json_loads(row[25], {}),
        "supersedes_runbook_id": row[26],
        "source_candidate_id": row[27],
    }


def _candidate_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "candidate_key": row.get("candidate_key") or "",
            "merge_key": row.get("merge_key") or "",
            "agent_id": row.get("agent_id"),
            "task_id": row.get("task_id"),
            "task_kind": row.get("task_kind") or "",
            "candidate_type": row.get("candidate_type") or "",
            "summary": row.get("summary") or "",
            "evidence": _json_loads(row.get("evidence_json"), []),
            "source_refs": _json_loads(row.get("source_refs_json"), []),
            "proposed_runbook": _json_loads(row.get("proposed_runbook_json"), {}),
            "confidence_score": float(row.get("confidence_score") or 0.0),
            "review_status": row.get("review_status") or "learning",
            "reviewer": row.get("reviewer") or "",
            "reviewed_at": row.get("reviewed_at"),
            "diff_summary": row.get("diff_summary") or "",
            "review_note": row.get("review_note") or "",
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "project_key": row.get("project_key") or "",
            "environment": row.get("environment") or "",
            "team": row.get("team") or "",
            "support_count": int(row.get("support_count") or 0),
            "success_count": int(row.get("success_count") or 0),
            "failure_count": int(row.get("failure_count") or 0),
            "verification_count": int(row.get("verification_count") or 0),
            "promoted_runbook_id": row.get("promoted_runbook_id"),
            "last_human_feedback_at": row.get("last_human_feedback_at"),
            "last_promoted_version": row.get("last_promoted_version"),
        }
    return {
        "id": row[0],
        "candidate_key": row[1],
        "merge_key": row[2] or "",
        "agent_id": row[3],
        "task_id": row[4],
        "task_kind": row[5],
        "candidate_type": row[6],
        "summary": row[7],
        "evidence": _json_loads(row[8], []),
        "source_refs": _json_loads(row[9], []),
        "proposed_runbook": _json_loads(row[10], {}),
        "confidence_score": float(row[11] or 0.0),
        "review_status": row[12],
        "reviewer": row[13] or "",
        "reviewed_at": row[14],
        "diff_summary": row[15] or "",
        "review_note": row[16] or "",
        "created_at": row[17],
        "updated_at": row[18],
        "project_key": row[19] or "",
        "environment": row[20] or "",
        "team": row[21] or "",
        "support_count": int(row[22] or 0),
        "success_count": int(row[23] or 0),
        "failure_count": int(row[24] or 0),
        "verification_count": int(row[25] or 0),
        "promoted_runbook_id": row[26],
        "last_human_feedback_at": row[27],
        "last_promoted_version": row[28],
    }


def _episode_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "agent_id": row.get("agent_id"),
            "task_id": row.get("task_id"),
            "user_id": row.get("user_id"),
            "task_kind": row.get("task_kind") or "",
            "project_key": row.get("project_key") or "",
            "environment": row.get("environment") or "",
            "team": row.get("team") or "",
            "autonomy_tier": row.get("autonomy_tier") or "",
            "approval_mode": row.get("approval_mode") or "",
            "status": row.get("status") or "",
            "confidence_score": float(row.get("confidence_score") or 0.0),
            "verified_before_finalize": bool(row.get("verified_before_finalize")),
            "stale_sources_present": bool(row.get("stale_sources_present")),
            "ungrounded_operationally": bool(row.get("ungrounded_operationally")),
            "plan": _json_loads(row.get("plan_json"), {}),
            "source_refs": _json_loads(row.get("source_refs_json"), []),
            "tool_trace": _json_loads(row.get("tool_trace_json"), []),
            "feedback_status": row.get("feedback_status") or "pending",
            "retrieval_trace_id": row.get("retrieval_trace_id"),
            "retrieval_strategy": row.get("retrieval_strategy") or "",
            "grounding_score": float(row.get("grounding_score") or 0.0),
            "citation_coverage": float(row.get("citation_coverage") or 0.0),
            "winning_sources": _json_loads(row.get("winning_sources_json"), []),
            "answer_citation_coverage": float(row.get("answer_citation_coverage") or 0.0),
            "answer_gate_status": row.get("answer_gate_status") or "",
            "answer_gate_reasons": _json_loads(row.get("answer_gate_reasons_json"), []),
            "post_write_review_required": bool(row.get("post_write_review_required")),
            "created_at": row.get("created_at"),
        }
    return {
        "id": row[0],
        "agent_id": row[1],
        "task_id": row[2],
        "user_id": row[3],
        "task_kind": row[4],
        "project_key": row[5] or "",
        "environment": row[6] or "",
        "team": row[7] or "",
        "autonomy_tier": row[8] or "",
        "approval_mode": row[9] or "",
        "status": row[10],
        "confidence_score": float(row[11] or 0.0),
        "verified_before_finalize": bool(row[12]),
        "stale_sources_present": bool(row[13]),
        "ungrounded_operationally": bool(row[14]),
        "plan": _json_loads(row[15], {}),
        "source_refs": _json_loads(row[16], []),
        "tool_trace": _json_loads(row[17], []),
        "feedback_status": row[18] or "pending",
        "retrieval_trace_id": row[19],
        "retrieval_strategy": row[20] or "",
        "grounding_score": float(row[21] or 0.0),
        "citation_coverage": float(row[22] or 0.0),
        "winning_sources": _json_loads(row[23], []),
        "answer_citation_coverage": float(row[24] or 0.0),
        "answer_gate_status": row[25] or "",
        "answer_gate_reasons": _json_loads(row[26], []),
        "post_write_review_required": bool(row[27]),
        "created_at": row[28],
    }


def upsert_knowledge_source(
    *,
    source_key: str,
    source_type: str,
    layer: str,
    source_label: str,
    source_path: str,
    updated_at: str,
    agent_id: str | None = None,
    project_key: str | None = None,
    owner: str = "",
    freshness_days: int = 90,
    content_hash: str = "",
    status: str = "active",
    is_canonical: bool = False,
    stale_after: str | None = None,
    invalid_after: str | None = None,
    sla_hours: int = 0,
    sync_mode: str = "local_scan",
    last_success_at: str | None = None,
    last_error: str = "",
    workspace_fingerprint: str = "",
) -> None:
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        run_coro_sync(
            primary_execute(
                """INSERT INTO knowledge_source_registry
                   (source_key, agent_id, project_key, source_type, layer, source_label, source_path,
                    owner, freshness_days, content_hash, status, is_canonical, updated_at, last_synced_at,
                    stale_after, invalid_after, sla_hours, sync_mode, last_success_at, last_error,
                    workspace_fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_key) DO UPDATE SET
                       agent_id = EXCLUDED.agent_id,
                       project_key = EXCLUDED.project_key,
                       source_type = EXCLUDED.source_type,
                       layer = EXCLUDED.layer,
                       source_label = EXCLUDED.source_label,
                       source_path = EXCLUDED.source_path,
                       owner = EXCLUDED.owner,
                       freshness_days = EXCLUDED.freshness_days,
                       content_hash = EXCLUDED.content_hash,
                       status = EXCLUDED.status,
                       is_canonical = EXCLUDED.is_canonical,
                       updated_at = EXCLUDED.updated_at,
                       last_synced_at = EXCLUDED.last_synced_at,
                       stale_after = EXCLUDED.stale_after,
                       invalid_after = EXCLUDED.invalid_after,
                       sla_hours = EXCLUDED.sla_hours,
                       sync_mode = EXCLUDED.sync_mode,
                       last_success_at = EXCLUDED.last_success_at,
                       last_error = EXCLUDED.last_error,
                       workspace_fingerprint = EXCLUDED.workspace_fingerprint""",
                (
                    source_key,
                    scope,
                    project_key,
                    source_type,
                    layer,
                    source_label,
                    source_path,
                    owner,
                    freshness_days,
                    content_hash,
                    status,
                    is_canonical,
                    updated_at,
                    now,
                    stale_after,
                    invalid_after,
                    sla_hours,
                    sync_mode,
                    last_success_at or now,
                    last_error,
                    workspace_fingerprint,
                ),
                agent_id=scope,
            )
        )
        return
    with _compat_backend_removed_conn() as conn:
        conn.execute(
            """INSERT INTO knowledge_source_registry
               (source_key, agent_id, project_key, source_type, layer, source_label, source_path,
                owner, freshness_days, content_hash, status, is_canonical, updated_at, last_synced_at,
                stale_after, invalid_after, sla_hours, sync_mode, last_success_at, last_error,
                workspace_fingerprint)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_key) DO UPDATE SET
                   agent_id = excluded.agent_id,
                   project_key = excluded.project_key,
                   source_type = excluded.source_type,
                   layer = excluded.layer,
                   source_label = excluded.source_label,
                   source_path = excluded.source_path,
                   owner = excluded.owner,
                   freshness_days = excluded.freshness_days,
                   content_hash = excluded.content_hash,
                   status = excluded.status,
                   is_canonical = excluded.is_canonical,
                   updated_at = excluded.updated_at,
                   last_synced_at = excluded.last_synced_at,
                   stale_after = excluded.stale_after,
                   invalid_after = excluded.invalid_after,
                   sla_hours = excluded.sla_hours,
                   sync_mode = excluded.sync_mode,
                   last_success_at = excluded.last_success_at,
                   last_error = excluded.last_error,
                   workspace_fingerprint = excluded.workspace_fingerprint""",
            (
                source_key,
                agent_id,
                project_key,
                source_type,
                layer,
                source_label,
                source_path,
                owner,
                freshness_days,
                content_hash,
                status,
                1 if is_canonical else 0,
                updated_at,
                now,
                stale_after,
                invalid_after,
                sla_hours,
                sync_mode,
                last_success_at or now,
                last_error,
                workspace_fingerprint,
            ),
        )


def list_knowledge_sources(
    *,
    agent_id: str | None = None,
    status: str | None = "active",
    canonical_only: bool = False,
    freshness: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if agent_id:
        conditions.append("(agent_id = ? OR agent_id IS NULL OR agent_id = '')")
        params.append(scope if _primary_enabled(agent_id) else agent_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if canonical_only:
        conditions.append("is_canonical = ?")
        params.append(True if _primary_enabled(agent_id) else 1)
    if freshness == "stale":
        conditions.append("stale_after IS NOT NULL AND stale_after <= ?")
        params.append(now)
    elif freshness == "errors":
        conditions.append("last_error IS NOT NULL AND last_error != ''")
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    columns = (
        "id, source_key, agent_id, project_key, source_type, layer, source_label, source_path, owner, "
        "freshness_days, content_hash, status, is_canonical, updated_at, last_synced_at, stale_after, "
        "invalid_after, sla_hours, sync_mode, last_success_at, last_error, workspace_fingerprint"
    )
    if _primary_enabled(agent_id):
        rows = run_coro_sync(
            primary_fetch_all(
                f"SELECT {columns} FROM knowledge_source_registry{where} "
                "ORDER BY is_canonical DESC, updated_at DESC LIMIT ?",
                tuple(params),
                agent_id=scope,
            )
        )
        return [
            {
                "id": row["id"],
                "source_key": row["source_key"],
                "agent_id": row.get("agent_id"),
                "project_key": row.get("project_key") or "",
                "source_type": row.get("source_type") or "",
                "layer": row.get("layer") or "",
                "source_label": row.get("source_label") or "",
                "source_path": row.get("source_path") or "",
                "owner": row.get("owner") or "",
                "freshness_days": int(row.get("freshness_days") or 0),
                "content_hash": row.get("content_hash") or "",
                "status": row.get("status") or "",
                "is_canonical": bool(row.get("is_canonical")),
                "updated_at": row.get("updated_at"),
                "last_synced_at": row.get("last_synced_at"),
                "stale_after": row.get("stale_after"),
                "invalid_after": row.get("invalid_after"),
                "sla_hours": int(row.get("sla_hours") or 0),
                "sync_mode": row.get("sync_mode") or "",
                "last_success_at": row.get("last_success_at"),
                "last_error": row.get("last_error") or "",
                "workspace_fingerprint": row.get("workspace_fingerprint") or "",
            }
            for row in rows
        ]
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(
            f"SELECT {columns} FROM knowledge_source_registry{where} "
            "ORDER BY is_canonical DESC, updated_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [
        {
            "id": row[0],
            "source_key": row[1],
            "agent_id": row[2],
            "project_key": row[3] or "",
            "source_type": row[4] or "",
            "layer": row[5] or "",
            "source_label": row[6] or "",
            "source_path": row[7] or "",
            "owner": row[8] or "",
            "freshness_days": row[9],
            "content_hash": row[10] or "",
            "status": row[11] or "",
            "is_canonical": bool(row[12]),
            "updated_at": row[13],
            "last_synced_at": row[14],
            "stale_after": row[15],
            "invalid_after": row[16],
            "sla_hours": row[17],
            "sync_mode": row[18] or "",
            "last_success_at": row[19],
            "last_error": row[20] or "",
            "workspace_fingerprint": row[21] or "",
        }
        for row in rows
    ]


def create_approved_runbook(
    *,
    title: str,
    task_kind: str,
    summary: str,
    prerequisites: list[str],
    steps: list[str],
    verification: list[str],
    rollback: str,
    source_refs: list[dict[str, Any]],
    approved_by: str,
    approved_at: str | None = None,
    last_validated_by: str | None = None,
    last_validated_at: str | None = None,
    agent_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    owner: str = "",
    status: str = "approved",
    runbook_key: str = "",
    version: int = 1,
    lifecycle_status: str = "approved",
    valid_from: str | None = None,
    valid_until: str | None = None,
    rollout_scope: dict[str, Any] | None = None,
    policy_overrides: dict[str, Any] | None = None,
    supersedes_runbook_id: int | None = None,
    source_candidate_id: int | None = None,
) -> int:
    approved_at = approved_at or _now_iso()
    last_validated_at = last_validated_at or approved_at
    last_validated_by = last_validated_by or approved_by
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        row_id = run_coro_sync(
            primary_fetch_val(
                """INSERT INTO approved_runbooks
                   (agent_id, runbook_key, version, title, task_kind, summary, prerequisites_json, steps_json,
                    verification_json, rollback, source_refs_json, project_key, environment, team, owner,
                    approved_by, approved_at, last_validated_by, last_validated_at,
                    status, lifecycle_status, valid_from, valid_until,
                    rollout_scope_json, policy_overrides_json, supersedes_runbook_id, source_candidate_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    scope,
                    runbook_key,
                    version,
                    title,
                    task_kind,
                    summary,
                    prerequisites,
                    steps,
                    verification,
                    rollback,
                    source_refs,
                    project_key,
                    environment,
                    team,
                    owner,
                    approved_by,
                    approved_at,
                    last_validated_by,
                    last_validated_at,
                    status,
                    lifecycle_status,
                    valid_from,
                    valid_until,
                    rollout_scope or {},
                    policy_overrides or {},
                    supersedes_runbook_id,
                    source_candidate_id,
                ),
                agent_id=scope,
            )
        )
        if row_id is None:
            raise RuntimeError("failed_to_persist_approved_runbook")
        return int(row_id)
    with _compat_backend_removed_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO approved_runbooks
               (agent_id, runbook_key, version, title, task_kind, summary, prerequisites_json, steps_json,
                verification_json, rollback, source_refs_json, project_key, environment, team, owner,
                approved_by, approved_at, last_validated_by, last_validated_at,
                status, lifecycle_status, valid_from, valid_until,
                rollout_scope_json, policy_overrides_json, supersedes_runbook_id, source_candidate_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                runbook_key,
                version,
                title,
                task_kind,
                summary,
                json.dumps(prerequisites, default=str),
                json.dumps(steps, default=str),
                json.dumps(verification, default=str),
                rollback,
                json.dumps(source_refs, default=str),
                project_key,
                environment,
                team,
                owner,
                approved_by,
                approved_at,
                last_validated_by,
                last_validated_at,
                status,
                lifecycle_status,
                valid_from,
                valid_until,
                json.dumps(rollout_scope or {}, default=str),
                json.dumps(policy_overrides or {}, default=str),
                supersedes_runbook_id,
                source_candidate_id,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("failed_to_persist_approved_runbook")
        return int(cursor.lastrowid)


def list_approved_runbooks(
    *,
    agent_id: str | None = None,
    task_kind: str | None = None,
    project_key: str | None = None,
    environment: str | None = None,
    team: str | None = None,
    status: str | None = "approved",
    enforce_valid_window: bool = True,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if agent_id:
        conditions.append("(agent_id = ? OR agent_id IS NULL OR agent_id = '')")
        params.append(scope if _primary_enabled(agent_id) else agent_id)
    if task_kind:
        conditions.append("(task_kind = ? OR task_kind = 'general')")
        params.append(task_kind)
    if project_key:
        conditions.append("(project_key = ? OR project_key IS NULL OR project_key = '')")
        params.append(project_key)
    if environment:
        conditions.append("(environment = ? OR environment IS NULL OR environment = '')")
        params.append(environment)
    if team:
        conditions.append("(team = ? OR team IS NULL OR team = '')")
        params.append(team)
    if enforce_valid_window:
        conditions.append("(valid_from IS NULL OR valid_from = '' OR valid_from <= ?)")
        params.append(now)
        conditions.append("(valid_until IS NULL OR valid_until = '' OR valid_until >= ?)")
        params.append(now)
    params.append(limit)
    where = " AND ".join(conditions) if conditions else "1 = 1"
    query = (
        "SELECT id, agent_id, runbook_key, version, title, task_kind, summary, prerequisites_json, steps_json, "
        "verification_json, rollback, source_refs_json, project_key, environment, team, owner, approved_by, "
        "approved_at, last_validated_by, last_validated_at, status, lifecycle_status, valid_from, valid_until, "
        "rollout_scope_json, policy_overrides_json, supersedes_runbook_id, source_candidate_id "
        f"FROM approved_runbooks WHERE {where} "
        "ORDER BY COALESCE(last_validated_at, approved_at) DESC, approved_at DESC LIMIT ?"
    )
    if _primary_enabled(agent_id):
        rows = run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=scope))
        return [_runbook_from_row(row) for row in rows]
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_runbook_from_row(row) for row in rows]


def get_runbook_status_counts(*, agent_id: str | None = None) -> dict[str, int]:
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        rows = run_coro_sync(
            primary_fetch_all(
                """SELECT COALESCE(lifecycle_status, status, 'approved') AS lifecycle, COUNT(*) AS total
                   FROM approved_runbooks
                   WHERE COALESCE(agent_id, ?) IN (?, '')
                   GROUP BY COALESCE(lifecycle_status, status, 'approved')""",
                (scope, scope),
                agent_id=scope,
            )
        )
        return {str(row.get("lifecycle") or "approved"): int(row.get("total") or 0) for row in rows}
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(
            """SELECT COALESCE(lifecycle_status, status, 'approved') AS lifecycle, COUNT(*)
               FROM approved_runbooks
               WHERE COALESCE(agent_id, ?) IN (?, '')
               GROUP BY COALESCE(lifecycle_status, status, 'approved')""",
            (scope, scope),
        ).fetchall()
    return {str(row[0] or "approved"): int(row[1] or 0) for row in rows}


def get_knowledge_candidate_counts(*, agent_id: str | None = None) -> dict[str, int]:
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        rows = run_coro_sync(
            primary_fetch_all(
                """SELECT review_status, COUNT(*) AS total
                   FROM knowledge_candidates
                   WHERE COALESCE(agent_id, ?) IN (?, '')
                   GROUP BY review_status""",
                (scope, scope),
                agent_id=scope,
            )
        )
        return {str(row.get("review_status") or "learning"): int(row.get("total") or 0) for row in rows}
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(
            """SELECT review_status, COUNT(*)
               FROM knowledge_candidates
               WHERE COALESCE(agent_id, ?) IN (?, '')
               GROUP BY review_status""",
            (scope, scope),
        ).fetchall()
    return {str(row[0] or "learning"): int(row[1] or 0) for row in rows}


def _record_runbook_governance_action_on_compat_backend(
    conn: Any,
    *,
    runbook_id: int,
    agent_id: str | None,
    action: str,
    reason: str,
    previous_status: str,
    new_status: str,
    metrics_snapshot: dict[str, object] | None = None,
    reviewer: str = "",
) -> Any:
    return conn.execute(
        """
        INSERT INTO runbook_governance_audit
            (
                runbook_id,
                agent_id,
                action,
                reason,
                previous_status,
                new_status,
                metrics_snapshot_json,
                reviewer,
                created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            runbook_id,
            _scope(agent_id),
            action,
            reason,
            previous_status,
            new_status,
            json.dumps(metrics_snapshot or {}, default=str),
            reviewer,
            _now_iso(),
        ),
    )


def get_latest_runbook_governance_actions(
    runbook_ids: list[int],
    *,
    agent_id: str | None = None,
) -> dict[int, dict[str, object]]:
    if not runbook_ids:
        return {}
    scope = _primary_agent_id(agent_id)
    placeholders = ",".join("?" for _ in runbook_ids)
    query = f"""
        SELECT audit.runbook_id, audit.action, audit.reason, audit.previous_status, audit.new_status,
               audit.metrics_snapshot_json, audit.reviewer, audit.created_at
        FROM runbook_governance_audit audit
        INNER JOIN (
            SELECT runbook_id, MAX(created_at) AS max_created_at
            FROM runbook_governance_audit
            WHERE COALESCE(agent_id, ?) = ? AND runbook_id IN ({placeholders})
            GROUP BY runbook_id
        ) latest
            ON latest.runbook_id = audit.runbook_id AND latest.max_created_at = audit.created_at
        WHERE audit.runbook_id IN ({placeholders})
    """
    params = [scope, scope, *runbook_ids, *runbook_ids]
    if _primary_enabled(agent_id):
        rows = run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=scope))
        return {
            int(row["runbook_id"]): {
                "action": str(row.get("action") or ""),
                "reason": str(row.get("reason") or ""),
                "previous_status": str(row.get("previous_status") or ""),
                "new_status": str(row.get("new_status") or ""),
                "metrics_snapshot": _json_loads(row.get("metrics_snapshot_json"), {}),
                "reviewer": str(row.get("reviewer") or ""),
                "created_at": row.get("created_at"),
            }
            for row in rows
        }
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return {
        int(row[0]): {
            "action": str(row[1] or ""),
            "reason": str(row[2] or ""),
            "previous_status": str(row[3] or ""),
            "new_status": str(row[4] or ""),
            "metrics_snapshot": _json_loads(row[5], {}),
            "reviewer": str(row[6] or ""),
            "created_at": row[7],
        }
        for row in rows
    }


def set_runbook_lifecycle_status(
    runbook_id: int,
    *,
    status: str,
    reviewer: str,
    reason: str,
    metrics_snapshot: dict[str, object] | None = None,
    refresh_validation: bool = False,
    renew_validity_window: bool = False,
) -> bool:
    columns = (
        "agent_id, COALESCE(lifecycle_status, status, 'approved') AS previous_status, approved_at, approved_by, "
        "last_validated_at, last_validated_by, valid_from, valid_until"
    )
    backend_scope = _primary_agent_id(None)
    if _primary_enabled(None):
        row = run_coro_sync(
            primary_fetch_one(
                f"SELECT {columns} FROM approved_runbooks WHERE id = ?",
                (runbook_id,),
                agent_id=backend_scope,
            )
        )
        if not row:
            return False
        agent_id = row.get("agent_id")
        previous_status = str(row.get("previous_status") or "approved")
        if previous_status == status and not reason.startswith("manual_"):
            return True
        now = datetime.now(UTC).replace(tzinfo=None)
        approved_at = row.get("approved_at")
        original_approver = row.get("approved_by")
        previous_validated_at = row.get("last_validated_at")
        previous_validated_by = row.get("last_validated_by")
        valid_from = row.get("valid_from")
        valid_until = row.get("valid_until")
        next_last_validated_at = previous_validated_at
        next_last_validated_by = previous_validated_by
        next_valid_from = valid_from
        next_valid_until = valid_until
        if refresh_validation:
            now_iso = now.isoformat()
            next_last_validated_at = now_iso
            next_last_validated_by = reviewer
            if renew_validity_window:
                parsed_valid_from = _parse_iso_datetime(valid_from)
                parsed_valid_until = _parse_iso_datetime(valid_until)
                parsed_approved_at = _parse_iso_datetime(approved_at)
                duration: timedelta | None = None
                if parsed_valid_from and parsed_valid_until and parsed_valid_until > parsed_valid_from:
                    duration = parsed_valid_until - parsed_valid_from
                elif parsed_approved_at and parsed_valid_until and parsed_valid_until > parsed_approved_at:
                    duration = parsed_valid_until - parsed_approved_at
                elif parsed_valid_until is not None:
                    duration = timedelta(days=RUNBOOK_REVALIDATION_STALE_DAYS)
                if duration is not None:
                    next_valid_from = now_iso
                    next_valid_until = (now + duration).isoformat()
                elif valid_until:
                    next_valid_from = now_iso
                    next_valid_until = (now + timedelta(days=RUNBOOK_REVALIDATION_STALE_DAYS)).isoformat()
        run_coro_sync(
            primary_execute(
                """
                UPDATE approved_runbooks
                SET status = ?,
                    lifecycle_status = ?,
                    approved_by = COALESCE(approved_by, ?),
                    approved_at = COALESCE(approved_at, ?),
                    last_validated_by = ?,
                    last_validated_at = ?,
                    valid_from = ?,
                    valid_until = ?
                WHERE id = ?
                """,
                (
                    status,
                    status,
                    original_approver,
                    approved_at,
                    next_last_validated_by,
                    next_last_validated_at,
                    next_valid_from,
                    next_valid_until,
                    runbook_id,
                ),
                agent_id=backend_scope,
            )
        )
        run_coro_sync(
            primary_execute(
                """
                INSERT INTO runbook_governance_audit
                    (
                        runbook_id,
                        agent_id,
                        action,
                        reason,
                        previous_status,
                        new_status,
                        metrics_snapshot_json,
                        reviewer,
                        created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    runbook_id,
                    _scope(agent_id),
                    status,
                    reason,
                    previous_status,
                    status,
                    metrics_snapshot or {},
                    reviewer,
                    _now_iso(),
                ),
                agent_id=backend_scope,
            )
        )
    else:
        with _compat_backend_removed_conn() as conn:
            row = conn.execute(f"SELECT {columns} FROM approved_runbooks WHERE id = ?", (runbook_id,)).fetchone()
            if not row:
                return False
            agent_id = row[0]
            previous_status = str(row[1] or "approved")
            if previous_status == status and not reason.startswith("manual_"):
                return True
            now = datetime.now(UTC).replace(tzinfo=None)
            approved_at = row[2]
            original_approver = row[3]
            previous_validated_at = row[4]
            previous_validated_by = row[5]
            valid_from = row[6]
            valid_until = row[7]
            next_last_validated_at = previous_validated_at
            next_last_validated_by = previous_validated_by
            next_valid_from = valid_from
            next_valid_until = valid_until
            if refresh_validation:
                now_iso = now.isoformat()
                next_last_validated_at = now_iso
                next_last_validated_by = reviewer
                if renew_validity_window:
                    parsed_valid_from = _parse_iso_datetime(valid_from)
                    parsed_valid_until = _parse_iso_datetime(valid_until)
                    parsed_approved_at = _parse_iso_datetime(approved_at)
                    duration_legacy: timedelta | None = None
                    if parsed_valid_from and parsed_valid_until and parsed_valid_until > parsed_valid_from:
                        duration_legacy = parsed_valid_until - parsed_valid_from
                    elif parsed_approved_at and parsed_valid_until and parsed_valid_until > parsed_approved_at:
                        duration_legacy = parsed_valid_until - parsed_approved_at
                    elif parsed_valid_until is not None:
                        duration_legacy = timedelta(days=RUNBOOK_REVALIDATION_STALE_DAYS)
                    if duration_legacy is not None:
                        next_valid_from = now_iso
                        next_valid_until = (now + duration_legacy).isoformat()
                    elif valid_until:
                        next_valid_from = now_iso
                        next_valid_until = (now + timedelta(days=RUNBOOK_REVALIDATION_STALE_DAYS)).isoformat()
            conn.execute(
                """
                UPDATE approved_runbooks
                SET status = ?,
                    lifecycle_status = ?,
                    approved_by = COALESCE(approved_by, ?),
                    approved_at = COALESCE(approved_at, ?),
                    last_validated_by = ?,
                    last_validated_at = ?,
                    valid_from = ?,
                    valid_until = ?
                WHERE id = ?
                """,
                (
                    status,
                    status,
                    original_approver,
                    approved_at,
                    next_last_validated_by,
                    next_last_validated_at,
                    next_valid_from,
                    next_valid_until,
                    runbook_id,
                ),
            )
            _record_runbook_governance_action_on_compat_backend(
                conn,
                runbook_id=runbook_id,
                agent_id=agent_id,
                action=status,
                reason=reason,
                previous_status=previous_status,
                new_status=status,
                metrics_snapshot=metrics_snapshot,
                reviewer=reviewer,
            )
    increment_memory_quality_counter(_scope(agent_id), f"runbook_governance.{status}", 1)
    with contextlib.suppress(Exception):
        from koda.services import metrics

        metrics.RUNBOOK_GOVERNANCE_ACTIONS.labels(agent_id=_scope(agent_id), action=status).inc()
    return True


def deprecate_approved_runbook(runbook_id: int, *, reviewer: str) -> bool:
    return set_runbook_lifecycle_status(
        runbook_id,
        status="deprecated",
        reviewer=reviewer,
        reason="manual_deprecation",
    )


def revalidate_approved_runbook(runbook_id: int, *, reviewer: str) -> bool:
    return set_runbook_lifecycle_status(
        runbook_id,
        status="approved",
        reviewer=reviewer,
        reason="manual_revalidation",
        refresh_validation=True,
        renew_validity_window=True,
    )


def upsert_knowledge_candidate(
    *,
    candidate_key: str,
    merge_key: str | None = None,
    task_kind: str,
    candidate_type: str,
    summary: str,
    evidence: list[dict[str, Any]],
    source_refs: list[dict[str, Any]],
    proposed_runbook: dict[str, Any],
    confidence_score: float,
    agent_id: str | None = None,
    task_id: int | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    success_delta: int = 0,
    failure_delta: int = 0,
    verification_delta: int = 0,
    force_pending: bool = False,
    diff_summary: str = "",
) -> dict[str, Any]:
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        row = run_coro_sync(
            primary_fetch_one(
                "SELECT id, review_status, support_count, success_count, failure_count, verification_count "
                "FROM knowledge_candidates WHERE candidate_key = ?",
                (candidate_key,),
                agent_id=scope,
            )
        )
        if row:
            candidate_id = int(row["id"])
            current_status = str(row.get("review_status") or "learning")
            review_status = "pending" if force_pending and current_status == "learning" else current_status
            run_coro_sync(
                primary_execute(
                    """UPDATE knowledge_candidates
                       SET task_id = COALESCE(?, task_id),
                           merge_key = COALESCE(?, merge_key),
                           task_kind = ?,
                           candidate_type = ?,
                           summary = ?,
                           evidence_json = ?,
                           source_refs_json = ?,
                           proposed_runbook_json = ?,
                           confidence_score = ?,
                           review_status = ?,
                           diff_summary = COALESCE(NULLIF(?, ''), diff_summary),
                           updated_at = ?,
                           project_key = ?,
                           environment = ?,
                           team = ?,
                           support_count = ?,
                           success_count = ?,
                           failure_count = ?,
                           verification_count = ?
                       WHERE id = ?""",
                    (
                        task_id,
                        merge_key,
                        task_kind,
                        candidate_type,
                        summary,
                        evidence,
                        source_refs,
                        proposed_runbook,
                        confidence_score,
                        review_status,
                        diff_summary,
                        now,
                        project_key,
                        environment,
                        team,
                        int(row.get("support_count") or 0) + 1,
                        int(row.get("success_count") or 0) + success_delta,
                        int(row.get("failure_count") or 0) + failure_delta,
                        int(row.get("verification_count") or 0) + verification_delta,
                        candidate_id,
                    ),
                    agent_id=scope,
                )
            )
        else:
            review_status = "pending" if force_pending else "learning"
            candidate_id = int(
                run_coro_sync(
                    primary_fetch_val(
                        """INSERT INTO knowledge_candidates
                           (
                               candidate_key,
                               merge_key,
                               agent_id,
                               task_id,
                               task_kind,
                               candidate_type,
                               summary,
                               evidence_json,
                            source_refs_json, proposed_runbook_json, confidence_score, review_status, diff_summary,
                            created_at, updated_at, project_key, environment, team, support_count, success_count,
                            failure_count, verification_count
                           )
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           RETURNING id""",
                        (
                            candidate_key,
                            merge_key,
                            scope,
                            task_id,
                            task_kind,
                            candidate_type,
                            summary,
                            evidence,
                            source_refs,
                            proposed_runbook,
                            confidence_score,
                            review_status,
                            diff_summary,
                            now,
                            now,
                            project_key,
                            environment,
                            team,
                            1,
                            success_delta,
                            failure_delta,
                            verification_delta,
                        ),
                        agent_id=scope,
                    )
                )
                or 0
            )
        candidate = get_knowledge_candidate(candidate_id)
        if candidate is None:
            raise RuntimeError("candidate_missing_after_upsert")
        return candidate
    with _compat_backend_removed_conn() as conn:
        row = conn.execute(
            "SELECT id, review_status, support_count, success_count, failure_count, verification_count "
            "FROM knowledge_candidates WHERE candidate_key = ?",
            (candidate_key,),
        ).fetchone()
        if row:
            candidate_id = int(row[0])
            current_status = str(row[1])
            review_status = "pending" if force_pending and current_status == "learning" else current_status
            conn.execute(
                """UPDATE knowledge_candidates
                   SET task_id = COALESCE(?, task_id),
                       merge_key = COALESCE(?, merge_key),
                       task_kind = ?,
                       candidate_type = ?,
                       summary = ?,
                       evidence_json = ?,
                       source_refs_json = ?,
                       proposed_runbook_json = ?,
                       confidence_score = ?,
                       review_status = ?,
                       diff_summary = COALESCE(NULLIF(?, ''), diff_summary),
                       updated_at = ?,
                       project_key = ?,
                       environment = ?,
                       team = ?,
                       support_count = ?,
                       success_count = ?,
                       failure_count = ?,
                       verification_count = ?
                   WHERE id = ?""",
                (
                    task_id,
                    merge_key,
                    task_kind,
                    candidate_type,
                    summary,
                    json.dumps(evidence, default=str),
                    json.dumps(source_refs, default=str),
                    json.dumps(proposed_runbook, default=str),
                    confidence_score,
                    review_status,
                    diff_summary,
                    now,
                    project_key,
                    environment,
                    team,
                    int(row[2] or 0) + 1,
                    int(row[3] or 0) + success_delta,
                    int(row[4] or 0) + failure_delta,
                    int(row[5] or 0) + verification_delta,
                    candidate_id,
                ),
            )
        else:
            review_status = "pending" if force_pending else "learning"
            cursor = conn.execute(
                """INSERT INTO knowledge_candidates
                   (candidate_key, merge_key, agent_id, task_id, task_kind, candidate_type, summary, evidence_json,
                    source_refs_json, proposed_runbook_json, confidence_score, review_status, diff_summary,
                    created_at, updated_at, project_key, environment, team, support_count, success_count,
                    failure_count, verification_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate_key,
                    merge_key,
                    agent_id,
                    task_id,
                    task_kind,
                    candidate_type,
                    summary,
                    json.dumps(evidence, default=str),
                    json.dumps(source_refs, default=str),
                    json.dumps(proposed_runbook, default=str),
                    confidence_score,
                    review_status,
                    diff_summary,
                    now,
                    now,
                    project_key,
                    environment,
                    team,
                    1,
                    success_delta,
                    failure_delta,
                    verification_delta,
                ),
            )
            candidate_id = int(cursor.lastrowid or 0)
    candidate = get_knowledge_candidate(candidate_id)
    if candidate is None:
        raise RuntimeError("candidate_missing_after_upsert")
    return candidate


def set_knowledge_candidate_status(
    candidate_id: int,
    *,
    review_status: str,
    reviewer: str | None = None,
    promoted_runbook_id: int | None = None,
    review_note: str | None = None,
) -> bool:
    params = (
        review_status,
        reviewer,
        _now_iso() if reviewer else None,
        promoted_runbook_id,
        review_note,
        _now_iso(),
        candidate_id,
    )
    if _primary_enabled(None):
        updated = run_coro_sync(
            primary_execute(
                "UPDATE knowledge_candidates SET review_status = ?, reviewer = ?, reviewed_at = ?, "
                "promoted_runbook_id = COALESCE(?, promoted_runbook_id), review_note = COALESCE(?, review_note), "
                "updated_at = ? WHERE id = ?",
                params,
                agent_id=_primary_agent_id(None),
            )
        )
        return bool(updated)
    with _compat_backend_removed_conn() as conn:
        cursor = conn.execute(
            "UPDATE knowledge_candidates SET review_status = ?, reviewer = ?, reviewed_at = ?, "
            "promoted_runbook_id = COALESCE(?, promoted_runbook_id), review_note = COALESCE(?, review_note), "
            "updated_at = ? WHERE id = ?",
            params,
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0


def get_knowledge_candidate(candidate_id: int) -> dict[str, Any] | None:
    query = (
        "SELECT id, candidate_key, merge_key, agent_id, task_id, task_kind, candidate_type, summary, evidence_json, "
        "source_refs_json, proposed_runbook_json, confidence_score, review_status, reviewer, reviewed_at, "
        "diff_summary, review_note, created_at, updated_at, project_key, environment, team, support_count, "
        "success_count, failure_count, verification_count, promoted_runbook_id, last_human_feedback_at, "
        "last_promoted_version FROM knowledge_candidates WHERE id = ?"
    )
    if _primary_enabled(None):
        row = run_coro_sync(primary_fetch_one(query, (candidate_id,), agent_id=_primary_agent_id(None)))
        return _candidate_from_row(row) if row else None
    with _compat_backend_removed_conn() as conn:
        row = conn.execute(query, (candidate_id,)).fetchone()
    return _candidate_from_row(row) if row else None


def list_knowledge_candidates(
    *,
    agent_id: str | None = None,
    review_status: str = "pending",
    limit: int = 20,
) -> list[dict[str, Any]]:
    conditions = ["review_status = ?"]
    params: list[Any] = [review_status]
    scope = _primary_agent_id(agent_id)
    if agent_id:
        conditions.append("(agent_id = ? OR agent_id IS NULL OR agent_id = '')")
        params.append(scope if _primary_enabled(agent_id) else agent_id)
    params.append(limit)
    query = (
        "SELECT id, candidate_key, merge_key, agent_id, task_id, task_kind, candidate_type, summary, evidence_json, "
        "source_refs_json, proposed_runbook_json, confidence_score, review_status, reviewer, reviewed_at, "
        "diff_summary, review_note, created_at, updated_at, project_key, environment, team, support_count, "
        "success_count, failure_count, verification_count, promoted_runbook_id, last_human_feedback_at, "
        "last_promoted_version FROM knowledge_candidates WHERE "
        + " AND ".join(conditions)
        + " ORDER BY updated_at DESC LIMIT ?"
    )
    if _primary_enabled(agent_id):
        rows = run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=scope))
        return [_candidate_from_row(row) for row in rows]
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_candidate_from_row(row) for row in rows]


def list_approved_guardrails(
    *,
    agent_id: str | None = None,
    task_kind: str | None = None,
    project_key: str | None = None,
    environment: str | None = None,
    team: str | None = None,
    status: str = "active",
    limit: int = 20,
) -> list[dict[str, Any]]:
    conditions = ["status = ?"]
    params: list[Any] = [status]
    scope = _primary_agent_id(agent_id)
    if agent_id:
        conditions.append("(agent_id = ? OR agent_id IS NULL OR agent_id = '')")
        params.append(scope if _primary_enabled(agent_id) else agent_id)
    if task_kind:
        conditions.append("(task_kind = ? OR task_kind = 'general')")
        params.append(task_kind)
    if project_key:
        conditions.append("(project_key = ? OR project_key IS NULL OR project_key = '')")
        params.append(project_key)
    if environment:
        conditions.append("(environment = ? OR environment IS NULL OR environment = '')")
        params.append(environment)
    if team:
        conditions.append("(team = ? OR team IS NULL OR team = '')")
        params.append(team)
    params.append(limit)
    query = (
        "SELECT id, agent_id, task_kind, title, severity, reason, source_label, source_path, project_key, "
        "environment, team, owner, status, source_candidate_id, created_at, updated_at "
        "FROM approved_guardrails WHERE " + " AND ".join(conditions) + " ORDER BY updated_at DESC LIMIT ?"
    )
    if _primary_enabled(agent_id):
        rows = run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=scope))
        return [
            {
                "id": row["id"],
                "agent_id": row.get("agent_id"),
                "task_kind": row.get("task_kind") or "",
                "title": row.get("title") or "",
                "severity": row.get("severity") or "",
                "reason": row.get("reason") or "",
                "source_label": row.get("source_label") or "",
                "source_path": row.get("source_path") or "",
                "project_key": row.get("project_key") or "",
                "environment": row.get("environment") or "",
                "team": row.get("team") or "",
                "owner": row.get("owner") or "",
                "status": row.get("status") or "",
                "source_candidate_id": row.get("source_candidate_id"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ]
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [
        {
            "id": row[0],
            "agent_id": row[1],
            "task_kind": row[2],
            "title": row[3],
            "severity": row[4],
            "reason": row[5],
            "source_label": row[6],
            "source_path": row[7] or "",
            "project_key": row[8] or "",
            "environment": row[9] or "",
            "team": row[10] or "",
            "owner": row[11] or "",
            "status": row[12],
            "source_candidate_id": row[13],
            "created_at": row[14],
            "updated_at": row[15],
        }
        for row in rows
    ]


def _create_approved_guardrail(
    *,
    task_kind: str,
    title: str,
    reason: str,
    source_label: str,
    reviewer: str,
    agent_id: str | None = None,
    severity: str = "high",
    source_path: str = "",
    project_key: str = "",
    environment: str = "",
    team: str = "",
    source_candidate_id: int | None = None,
) -> int:
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        row_id = run_coro_sync(
            primary_fetch_val(
                """INSERT INTO approved_guardrails
                   (agent_id, task_kind, title, severity, reason, source_label, source_path, project_key,
                    environment, team, owner, status, source_candidate_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                   RETURNING id""",
                (
                    scope,
                    task_kind,
                    title,
                    severity,
                    reason,
                    source_label,
                    source_path,
                    project_key,
                    environment,
                    team,
                    reviewer,
                    source_candidate_id,
                    now,
                    now,
                ),
                agent_id=scope,
            )
        )
        if row_id is None:
            raise RuntimeError("failed_to_persist_approved_guardrail")
        return int(row_id)
    with _compat_backend_removed_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO approved_guardrails
               (agent_id, task_kind, title, severity, reason, source_label, source_path, project_key,
                environment, team, owner, status, source_candidate_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (
                agent_id,
                task_kind,
                title,
                severity,
                reason,
                source_label,
                source_path,
                project_key,
                environment,
                team,
                reviewer,
                source_candidate_id,
                now,
                now,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("failed_to_persist_approved_guardrail")
        return int(cursor.lastrowid)


def create_execution_episode(
    *,
    agent_id: str | None,
    task_id: int | None,
    user_id: int | None,
    task_kind: str,
    project_key: str,
    environment: str,
    team: str,
    autonomy_tier: str,
    approval_mode: str,
    status: str,
    confidence_score: float,
    verified_before_finalize: bool,
    stale_sources_present: bool,
    ungrounded_operationally: bool,
    plan: dict[str, Any] | None,
    source_refs: list[dict[str, Any]],
    tool_trace: list[dict[str, Any]],
    retrieval_trace_id: int | None = None,
    retrieval_strategy: str = "",
    grounding_score: float = 0.0,
    citation_coverage: float = 0.0,
    winning_sources: list[str] | None = None,
    answer_citation_coverage: float = 0.0,
    answer_gate_status: str = "",
    answer_gate_reasons: list[str] | None = None,
    post_write_review_required: bool = False,
) -> int:
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        row_id = run_coro_sync(
            primary_fetch_val(
                """INSERT INTO execution_episodes
                   (agent_id, task_id, user_id, task_kind, project_key, environment, team, autonomy_tier,
                    approval_mode, status, confidence_score, verified_before_finalize, stale_sources_present,
                    ungrounded_operationally, plan_json, source_refs_json, tool_trace_json, feedback_status,
                    retrieval_trace_id, retrieval_strategy, grounding_score, citation_coverage, winning_sources_json,
                    answer_citation_coverage, answer_gate_status, answer_gate_reasons_json, post_write_review_required,
                    created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    scope,
                    task_id,
                    user_id,
                    task_kind,
                    project_key,
                    environment,
                    team,
                    autonomy_tier,
                    approval_mode,
                    status,
                    confidence_score,
                    verified_before_finalize,
                    stale_sources_present,
                    ungrounded_operationally,
                    plan or {},
                    source_refs,
                    tool_trace,
                    retrieval_trace_id,
                    retrieval_strategy,
                    grounding_score,
                    citation_coverage,
                    winning_sources or [],
                    answer_citation_coverage,
                    answer_gate_status,
                    answer_gate_reasons or [],
                    post_write_review_required,
                    now,
                ),
                agent_id=scope,
            )
        )
        if row_id is None:
            raise RuntimeError("failed_to_persist_execution_episode")
        return int(row_id)
    with _compat_backend_removed_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO execution_episodes
               (agent_id, task_id, user_id, task_kind, project_key, environment, team, autonomy_tier,
                approval_mode, status, confidence_score, verified_before_finalize, stale_sources_present,
                ungrounded_operationally, plan_json, source_refs_json, tool_trace_json, feedback_status,
                retrieval_trace_id, retrieval_strategy, grounding_score, citation_coverage, winning_sources_json,
                answer_citation_coverage, answer_gate_status, answer_gate_reasons_json, post_write_review_required,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                task_id,
                user_id,
                task_kind,
                project_key,
                environment,
                team,
                autonomy_tier,
                approval_mode,
                status,
                confidence_score,
                1 if verified_before_finalize else 0,
                1 if stale_sources_present else 0,
                1 if ungrounded_operationally else 0,
                json.dumps(plan or {}, default=str),
                json.dumps(source_refs, default=str),
                json.dumps(tool_trace, default=str),
                retrieval_trace_id,
                retrieval_strategy,
                grounding_score,
                citation_coverage,
                json.dumps(winning_sources or [], default=str),
                answer_citation_coverage,
                answer_gate_status,
                json.dumps(answer_gate_reasons or [], default=str),
                1 if post_write_review_required else 0,
                now,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("failed_to_persist_execution_episode")
        return int(cursor.lastrowid)


def get_latest_execution_episode(task_id: int) -> dict[str, Any] | None:
    query = (
        "SELECT id, agent_id, task_id, user_id, task_kind, project_key, environment, team, autonomy_tier, "
        "approval_mode, status, confidence_score, verified_before_finalize, stale_sources_present, "
        "ungrounded_operationally, plan_json, source_refs_json, tool_trace_json, feedback_status, "
        "retrieval_trace_id, retrieval_strategy, grounding_score, citation_coverage, winning_sources_json, "
        "answer_citation_coverage, answer_gate_status, answer_gate_reasons_json, post_write_review_required, "
        "created_at "
    )
    if _primary_enabled(None):
        row = run_coro_sync(
            primary_fetch_one(
                query + "FROM execution_episodes WHERE agent_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1",
                (_primary_agent_id(None), task_id),
                agent_id=_primary_agent_id(None),
            )
        )
        return _episode_from_row(row) if row else None
    with _compat_backend_removed_conn() as conn:
        row = conn.execute(
            query + "FROM execution_episodes WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    return _episode_from_row(row) if row else None


def list_execution_episodes(
    *,
    agent_id: str | None = None,
    feedback_status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    scope = _primary_agent_id(agent_id)
    if agent_id is not None:
        where.append("agent_id = ?")
        params.append(scope if _primary_enabled(agent_id) else agent_id)
    if feedback_status:
        where.append("feedback_status = ?")
        params.append(feedback_status)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    params.append(max(1, limit))
    query = (
        "SELECT id, agent_id, task_id, user_id, task_kind, project_key, environment, team, autonomy_tier, "
        "approval_mode, status, confidence_score, verified_before_finalize, stale_sources_present, "
        "ungrounded_operationally, plan_json, source_refs_json, tool_trace_json, feedback_status, "
        "retrieval_trace_id, retrieval_strategy, grounding_score, citation_coverage, winning_sources_json, "
        "answer_citation_coverage, answer_gate_status, answer_gate_reasons_json, post_write_review_required, "
        "created_at FROM execution_episodes" + clause + " ORDER BY id DESC LIMIT ?"
    )
    if _primary_enabled(agent_id):
        rows = run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=scope))
        return [_episode_from_row(row) for row in rows]
    with _compat_backend_removed_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_episode_from_row(row) for row in rows]


def update_execution_reliability_stats(
    *,
    agent_id: str | None,
    task_kind: str,
    project_key: str,
    environment: str,
    successful: bool,
    verified: bool,
    count_execution: bool = True,
    human_override_delta: int = 0,
    correction_delta: int = 0,
    rollback_delta: int = 0,
) -> None:
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    query = """
        INSERT INTO execution_reliability_stats
           (agent_id, task_kind, project_key, environment, total_runs, successful_runs, verified_runs,
            human_override_count, correction_count, rollback_count, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(agent_id, task_kind, project_key, environment) DO UPDATE SET
               total_runs = execution_reliability_stats.total_runs + EXCLUDED.total_runs,
               successful_runs = execution_reliability_stats.successful_runs + EXCLUDED.successful_runs,
               verified_runs = execution_reliability_stats.verified_runs + EXCLUDED.verified_runs,
               human_override_count = execution_reliability_stats.human_override_count + EXCLUDED.human_override_count,
               correction_count = execution_reliability_stats.correction_count + EXCLUDED.correction_count,
               rollback_count = execution_reliability_stats.rollback_count + EXCLUDED.rollback_count,
               updated_at = EXCLUDED.updated_at
    """
    params = (
        scope if _primary_enabled(agent_id) else agent_id,
        task_kind,
        project_key,
        environment,
        1 if count_execution else 0,
        1 if count_execution and successful else 0,
        1 if count_execution and verified else 0,
        human_override_delta,
        correction_delta,
        rollback_delta,
        now,
    )
    if _primary_enabled(agent_id):
        run_coro_sync(primary_execute(query, params, agent_id=scope))
        return
    with _compat_backend_removed_conn() as conn:
        conn.execute(query.replace("EXCLUDED", "excluded"), params)


def get_execution_reliability_stats(
    *,
    agent_id: str | None,
    task_kind: str,
    project_key: str,
    environment: str,
) -> dict[str, Any]:
    scope = _primary_agent_id(agent_id)
    query = (
        "SELECT total_runs, successful_runs, verified_runs, human_override_count, correction_count, "
        "rollback_count, updated_at FROM execution_reliability_stats "
        "WHERE agent_id = ? AND task_kind = ? AND project_key = ? AND environment = ?"
    )
    if _primary_enabled(agent_id):
        row = run_coro_sync(primary_fetch_one(query, (scope, task_kind, project_key, environment), agent_id=scope))
        if row is None:
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "verified_runs": 0,
                "human_override_count": 0,
                "correction_count": 0,
                "rollback_count": 0,
                "updated_at": None,
            }
        return {
            "total_runs": int(row.get("total_runs") or 0),
            "successful_runs": int(row.get("successful_runs") or 0),
            "verified_runs": int(row.get("verified_runs") or 0),
            "human_override_count": int(row.get("human_override_count") or 0),
            "correction_count": int(row.get("correction_count") or 0),
            "rollback_count": int(row.get("rollback_count") or 0),
            "updated_at": row.get("updated_at"),
        }
    with _compat_backend_removed_conn() as conn:
        row = conn.execute(
            query.replace("agent_id = ?", "agent_id IS ?"),
            (agent_id, task_kind, project_key, environment),
        ).fetchone()
    if not row:
        return {
            "total_runs": 0,
            "successful_runs": 0,
            "verified_runs": 0,
            "human_override_count": 0,
            "correction_count": 0,
            "rollback_count": 0,
            "updated_at": None,
        }
    return {
        "total_runs": int(row[0] or 0),
        "successful_runs": int(row[1] or 0),
        "verified_runs": int(row[2] or 0),
        "human_override_count": int(row[3] or 0),
        "correction_count": int(row[4] or 0),
        "rollback_count": int(row[5] or 0),
        "updated_at": row[6],
    }


def record_correction_event(
    *,
    agent_id: str | None,
    task_id: int,
    feedback_type: str,
    user_id: int,
    note: str = "",
) -> int | None:
    episode = get_latest_execution_episode(task_id)
    if episode is None:
        return None
    now = _now_iso()
    scope = _primary_agent_id(agent_id)
    if _primary_enabled(agent_id):
        event_id = run_coro_sync(
            primary_fetch_val(
                """INSERT INTO correction_events
                   (agent_id, task_id, episode_id, task_kind, feedback_type, note, user_id, project_key,
                    environment, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    scope,
                    task_id,
                    episode["id"],
                    episode["task_kind"],
                    feedback_type,
                    note,
                    user_id,
                    episode["project_key"],
                    episode["environment"],
                    now,
                ),
                agent_id=scope,
            )
        )
        run_coro_sync(
            primary_execute(
                "UPDATE execution_episodes SET feedback_status = ? WHERE agent_id = ? AND id = ?",
                (feedback_type, scope, episode["id"]),
                agent_id=scope,
            )
        )
        return int(event_id) if event_id is not None else None
    with _compat_backend_removed_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO correction_events
               (agent_id, task_id, episode_id, task_kind, feedback_type, note, user_id, project_key,
                environment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                task_id,
                episode["id"],
                episode["task_kind"],
                feedback_type,
                note,
                user_id,
                episode["project_key"],
                episode["environment"],
                now,
            ),
        )
        conn.execute("UPDATE execution_episodes SET feedback_status = ? WHERE id = ?", (feedback_type, episode["id"]))
        return int(cursor.lastrowid) if cursor.lastrowid is not None else None


def _default_runbook_key(candidate: dict[str, Any]) -> str:
    project = str(candidate.get("project_key") or "")
    environment = str(candidate.get("environment") or "")
    team = str(candidate.get("team") or "")
    merge_key = str(candidate.get("merge_key") or "")
    if merge_key:
        return merge_key
    summary = str(candidate.get("summary") or candidate.get("task_kind") or "runbook").lower()
    normalized = "-".join(part for part in summary.replace("/", " ").replace("_", " ").split()[:8] if part)
    parts = [str(candidate.get("task_kind") or "general"), project, environment, team, normalized]
    return ":".join(part for part in parts if part)


def approve_knowledge_candidate(candidate_id: int, *, reviewer: str) -> int | None:
    candidate = get_knowledge_candidate(candidate_id)
    if not candidate or candidate["review_status"] not in {"pending", "learning"}:
        return None
    proposed = candidate["proposed_runbook"] or {}
    if candidate["candidate_type"] == "risk_pattern":
        guardrail_id = _create_approved_guardrail(
            agent_id=candidate["agent_id"],
            task_kind=str(candidate["task_kind"]),
            title=str(proposed.get("title") or candidate["summary"]),
            reason=str(candidate.get("diff_summary") or candidate["summary"]),
            source_label=str(proposed.get("title") or candidate["summary"]),
            reviewer=reviewer,
            project_key=str(candidate["project_key"]),
            environment=str(candidate["environment"]),
            team=str(candidate["team"]),
            source_candidate_id=candidate_id,
        )
        set_knowledge_candidate_status(
            candidate_id,
            review_status="approved",
            reviewer=reviewer,
            review_note="promoted_to_guardrail",
        )
        return guardrail_id

    runbook_key = _default_runbook_key(candidate)
    existing_versions = [
        runbook
        for runbook in list_approved_runbooks(
            agent_id=candidate["agent_id"],
            task_kind=str(candidate["task_kind"]),
            project_key=str(candidate["project_key"]) or None,
            environment=str(candidate["environment"]) or None,
            status=None,
            limit=50,
        )
        if runbook.get("runbook_key") == runbook_key
    ]
    latest = max(existing_versions, key=lambda runbook: int(runbook.get("version") or 1), default=None)
    next_version = int(latest["version"]) + 1 if latest else 1
    supersedes_runbook_id = int(latest["id"]) if latest else None
    if supersedes_runbook_id is not None:
        deprecate_approved_runbook(supersedes_runbook_id, reviewer=reviewer)

    from koda.knowledge.policy import sanitize_policy_overrides

    try:
        policy_overrides = sanitize_policy_overrides(dict(proposed.get("policy_overrides") or {}))
    except (TypeError, ValueError) as exc:
        set_knowledge_candidate_status(
            candidate_id,
            review_status=str(candidate["review_status"]),
            review_note=f"invalid_policy_overrides: {exc}",
        )
        return None

    runbook_id = create_approved_runbook(
        agent_id=candidate["agent_id"],
        runbook_key=runbook_key,
        version=next_version,
        title=str(proposed.get("title") or candidate["summary"]),
        task_kind=str(candidate["task_kind"]),
        summary=str(proposed.get("summary") or candidate["summary"]),
        prerequisites=[str(item) for item in proposed.get("prerequisites", [])],
        steps=[str(item) for item in proposed.get("steps", [])],
        verification=[str(item) for item in proposed.get("verification", [])],
        rollback=str(proposed.get("rollback") or ""),
        source_refs=list(candidate["source_refs"]),
        project_key=str(candidate["project_key"]),
        environment=str(candidate["environment"]),
        team=str(candidate["team"]),
        owner=str(proposed.get("owner") or ""),
        approved_by=reviewer,
        policy_overrides=policy_overrides,
        supersedes_runbook_id=supersedes_runbook_id,
        source_candidate_id=candidate_id,
    )
    set_knowledge_candidate_status(
        candidate_id,
        review_status="approved",
        reviewer=reviewer,
        promoted_runbook_id=runbook_id,
        review_note="promoted_to_runbook",
    )
    upsert_knowledge_source(
        source_key=f"approved_runbook:{runbook_id}",
        agent_id=candidate["agent_id"],
        project_key=str(candidate["project_key"]),
        source_type="approved_runbook",
        layer="approved_runbook",
        source_label=str(proposed.get("title") or candidate["summary"]),
        source_path=f"approved_runbook:{runbook_id}",
        owner=reviewer,
        freshness_days=180,
        content_hash=str(runbook_id),
        status="active",
        is_canonical=False,
        updated_at=_now_iso(),
        last_success_at=_now_iso(),
    )
    update_query = "UPDATE knowledge_candidates SET last_promoted_version = ?, updated_at = ? WHERE id = ?"
    if _primary_enabled(candidate.get("agent_id")):
        run_coro_sync(
            primary_execute(
                update_query,
                (next_version, _now_iso(), candidate_id),
                agent_id=_primary_agent_id(candidate.get("agent_id")),
            )
        )
    else:
        with _compat_backend_removed_conn() as conn:
            conn.execute(update_query, (next_version, _now_iso(), candidate_id))
    return runbook_id


def reject_knowledge_candidate(candidate_id: int, *, reviewer: str) -> bool:
    return set_knowledge_candidate_status(candidate_id, review_status="rejected", reviewer=reviewer)
