"""Squad task store.

Persists ``squad_tasks`` rows — the unit of work the coordinator decomposes
work into. Enforces a state machine, single-owner-per-task via optimistic
locking on ``version``, and idempotent creation via ``idempotency_key``.
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_STATUSES = {"pending", "claimed", "in_progress", "blocked", "done", "failed", "cancelled", "escalated"}
_TERMINAL_STATUSES = {"done", "failed", "cancelled", "escalated"}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"claimed", "cancelled"},
    "claimed": {"in_progress", "cancelled", "pending"},
    "in_progress": {"blocked", "done", "failed", "escalated", "cancelled"},
    "blocked": {"in_progress", "failed", "escalated", "cancelled"},
    "done": set(),
    "failed": set(),
    "cancelled": set(),
    "escalated": set(),
}


class TaskNotFoundError(KeyError):
    """Task id does not exist."""


class TaskClaimConflictError(RuntimeError):
    """Another agent claimed the task first or it is no longer pending."""


class IllegalTransitionError(ValueError):
    """Status transition not allowed by the state machine."""


class StaleVersionError(RuntimeError):
    """Optimistic lock failed: row was updated by someone else."""


class TaskOwnershipError(PermissionError):
    """Caller is not the assignee for this transition."""


class TaskDependencyError(ValueError):
    """Task dependency graph is invalid."""


@dataclass
class ExpiredClaim:
    task_id: str
    thread_id: str
    previously_assigned_agent_id: str | None
    version_after: int


@dataclass
class TaskDescriptor:
    id: str
    thread_id: str
    parent_task_id: str | None
    depends_on: list[str]
    assigned_agent_id: str | None
    assigner_agent_id: str
    kind: str
    title: str
    description: str
    status: str
    acceptance_criteria: list[str]
    deliverables_spec: list[Any]
    delivered_artifact_ids: list[str]
    claim_token: str | None
    claim_expires_at: datetime | None
    delegation_depth: int
    idempotency_key: str | None
    cost_usd_so_far: Decimal
    runtime_task_id: int | None
    version: int
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result_summary: str | None = None


def _decode_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return value


def _row_to_task(row: Any) -> TaskDescriptor:
    depends = _decode_jsonb(row["depends_on"]) or []
    accept = _decode_jsonb(row["acceptance_criteria"]) or []
    deliv_spec = _decode_jsonb(row["deliverables_spec"]) or []
    delivered = _decode_jsonb(row["delivered_artifact_ids"]) or []
    metadata = _decode_jsonb(row["metadata_json"]) or {}
    return TaskDescriptor(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        parent_task_id=str(row["parent_task_id"]) if row["parent_task_id"] is not None else None,
        depends_on=[str(x) for x in depends if x is not None],
        assigned_agent_id=row["assigned_agent_id"],
        assigner_agent_id=row["assigner_agent_id"],
        kind=row["kind"] or "",
        title=row["title"],
        description=row["description"] or "",
        status=row["status"],
        acceptance_criteria=[str(x) for x in accept if x is not None],
        deliverables_spec=list(deliv_spec) if isinstance(deliv_spec, list) else [],
        delivered_artifact_ids=[str(x) for x in delivered if x is not None],
        claim_token=str(row["claim_token"]) if row["claim_token"] is not None else None,
        claim_expires_at=row["claim_expires_at"],
        delegation_depth=int(row["delegation_depth"] or 0),
        idempotency_key=row["idempotency_key"],
        cost_usd_so_far=row["cost_usd_so_far"] or Decimal(0),
        runtime_task_id=row["runtime_task_id"],
        version=int(row["version"]),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
        result_summary=row["result_summary"],
    )


class SquadTaskStore:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None

    async def create_task(
        self,
        *,
        thread_id: str,
        title: str,
        assigner_agent_id: str,
        description: str = "",
        kind: str = "",
        parent_task_id: str | None = None,
        depends_on: list[str] | None = None,
        assigned_agent_id: str | None = None,
        acceptance_criteria: list[str] | None = None,
        deliverables_spec: list[Any] | None = None,
        delegation_depth: int = 0,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskDescriptor:
        if not thread_id or not title or not assigner_agent_id:
            raise ValueError("thread_id, title, and assigner_agent_id are required")
        task_id = str(uuid.uuid4())
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            if idempotency_key:
                existing = await conn.fetchrow(
                    f'SELECT * FROM "{self._schema}"."squad_tasks" WHERE idempotency_key = $1',
                    idempotency_key,
                )
                if existing is not None:
                    return _row_to_task(existing)
            thread_exists = await conn.fetchval(
                f'SELECT 1 FROM "{self._schema}"."squad_threads" WHERE id = $1',
                thread_id,
            )
            if not thread_exists:
                raise TaskDependencyError(f"thread {thread_id!r} not found")
            if parent_task_id:
                parent_thread = await conn.fetchval(
                    f'SELECT thread_id FROM "{self._schema}"."squad_tasks" WHERE id = $1',
                    parent_task_id,
                )
                if parent_thread is None:
                    raise TaskDependencyError(f"parent task {parent_task_id!r} not found")
                if str(parent_thread) != str(thread_id):
                    raise TaskDependencyError("parent task belongs to a different thread")
            dependency_ids = [str(dep) for dep in depends_on or [] if dep]
            if len(set(dependency_ids)) != len(dependency_ids):
                raise TaskDependencyError("depends_on contains duplicate task ids")
            if dependency_ids:
                rows = await conn.fetch(
                    f'SELECT id, thread_id FROM "{self._schema}"."squad_tasks" WHERE id = ANY($1::uuid[])',
                    dependency_ids,
                )
                found = {str(row["id"]): str(row["thread_id"]) for row in rows}
                missing = sorted(set(dependency_ids) - set(found))
                if missing:
                    raise TaskDependencyError(f"depends_on references missing tasks: {', '.join(missing)}")
                foreign = [dep for dep, dep_thread in found.items() if dep_thread != str(thread_id)]
                if foreign:
                    raise TaskDependencyError("depends_on references tasks from a different thread")
            try:
                row = await conn.fetchrow(
                    f"""INSERT INTO "{self._schema}"."squad_tasks"
                            (id, thread_id, parent_task_id, depends_on, assigned_agent_id,
                             assigner_agent_id, kind, title, description, status,
                             acceptance_criteria, deliverables_spec, delegation_depth,
                             idempotency_key, metadata_json)
                          VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, 'pending',
                                  $10::jsonb, $11::jsonb, $12, $13, $14::jsonb)
                          RETURNING *""",
                    task_id,
                    thread_id,
                    parent_task_id,
                    json.dumps(dependency_ids),
                    assigned_agent_id,
                    assigner_agent_id,
                    kind or "",
                    title,
                    description or "",
                    json.dumps(list(acceptance_criteria or [])),
                    json.dumps(list(deliverables_spec or [])),
                    int(delegation_depth),
                    idempotency_key,
                    json.dumps(metadata or {}),
                )
            except Exception as exc:
                # Race: another caller inserted with same idempotency_key between our
                # check and INSERT. Re-read and return the existing row.
                if idempotency_key and "idempotency_key" in str(exc):
                    existing = await conn.fetchrow(
                        f'SELECT * FROM "{self._schema}"."squad_tasks" WHERE idempotency_key = $1',
                        idempotency_key,
                    )
                    if existing is not None:
                        return _row_to_task(existing)
                raise
        return _row_to_task(row)

    async def get_task(self, task_id: str) -> TaskDescriptor | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_tasks" WHERE id = $1',
                task_id,
            )
        return _row_to_task(row) if row is not None else None

    async def list_tasks(
        self,
        *,
        thread_id: str | None = None,
        assigned_agent_id: str | None = None,
        status: str | list[str] | None = None,
        limit: int = 100,
    ) -> list[TaskDescriptor]:
        clauses: list[str] = []
        params: list[Any] = []
        if thread_id:
            params.append(thread_id)
            clauses.append(f"thread_id = ${len(params)}")
        if assigned_agent_id:
            params.append(assigned_agent_id)
            clauses.append(f"assigned_agent_id = ${len(params)}")
        if status:
            statuses = [status] if isinstance(status, str) else list(status)
            params.append(statuses)
            clauses.append(f"status = ANY(${len(params)}::text[])")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        sql = f'SELECT * FROM "{self._schema}"."squad_tasks" {where} ORDER BY created_at ASC LIMIT ${len(params)}'
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_row_to_task(r) for r in rows]

    async def claim_task(
        self,
        *,
        task_id: str,
        agent_id: str,
        ttl_seconds: int = 300,
        coordinator_override: bool = False,
    ) -> TaskDescriptor:
        if not agent_id:
            raise ValueError("agent_id is required")
        token = str(uuid.uuid4())
        ttl = max(1, int(ttl_seconds))
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""UPDATE "{self._schema}"."squad_tasks"
                       SET status = 'claimed',
                           assigned_agent_id = $2,
                           claim_token = $3,
                           claim_expires_at = NOW() + ($4 || ' seconds')::interval,
                           version = version + 1,
                           updated_at = NOW()
                     WHERE id = $1
                       AND status = 'pending'
                       AND (
                            $5::boolean
                            OR assigned_agent_id IS NULL
                            OR assigned_agent_id = $2
                       )
                     RETURNING *""",
                task_id,
                agent_id,
                token,
                str(ttl),
                bool(coordinator_override),
            )
        if row is None:
            current = await self.get_task(task_id)
            if current is None:
                raise TaskNotFoundError(task_id)
            raise TaskClaimConflictError(
                f"task {task_id!r} not claimable (status={current.status}, assignee={current.assigned_agent_id})"
            )
        return _row_to_task(row)

    async def update_task_status(
        self,
        *,
        task_id: str,
        new_status: str,
        agent_id: str,
        expected_version: int | None = None,
        error_message: str | None = None,
        result_summary: str | None = None,
        deliverables: list[str] | None = None,
        metadata_patch: dict[str, Any] | None = None,
        coordinator_override: bool = False,
    ) -> TaskDescriptor:
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            current_row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_tasks" WHERE id = $1 FOR UPDATE',
                task_id,
            )
            if current_row is None:
                raise TaskNotFoundError(task_id)
            current = _row_to_task(current_row)
            if expected_version is not None and current.version != int(expected_version):
                raise StaleVersionError(
                    f"task {task_id!r} version mismatch: expected {expected_version}, got {current.version}"
                )
            if current.status == new_status:
                return current
            allowed = _ALLOWED_TRANSITIONS.get(current.status, set())
            if new_status not in allowed:
                raise IllegalTransitionError(f"illegal transition {current.status!r} -> {new_status!r}")
            if (
                current.status not in {"pending"}
                and current.assigned_agent_id
                and current.assigned_agent_id != agent_id
                and not coordinator_override
            ):
                raise TaskOwnershipError(f"agent {agent_id!r} is not the assignee of task {task_id!r}")
            if new_status == "in_progress" and current.depends_on and not coordinator_override:
                rows = await conn.fetch(
                    f"""SELECT id, status
                          FROM "{self._schema}"."squad_tasks"
                         WHERE id = ANY($1::uuid[])""",
                    current.depends_on,
                )
                status_by_id = {str(row["id"]): str(row["status"]) for row in rows}
                missing = sorted(set(current.depends_on) - set(status_by_id))
                if missing:
                    raise TaskDependencyError(f"depends_on references missing tasks: {', '.join(missing)}")
                blocked = [dep for dep in current.depends_on if status_by_id.get(dep) != "done"]
                if blocked:
                    raise TaskDependencyError(
                        "task dependencies must be done before in_progress: " + ", ".join(blocked)
                    )
            assignments = ["status = $2", "version = version + 1", "updated_at = NOW()"]
            params: list[Any] = [task_id, new_status]
            if new_status == "in_progress" and current.started_at is None:
                assignments.append("started_at = NOW()")
            if new_status in _TERMINAL_STATUSES:
                assignments.append("completed_at = NOW()")
                assignments.append("claim_token = NULL")
                assignments.append("claim_expires_at = NULL")
            if error_message is not None:
                params.append(error_message)
                assignments.append(f"error_message = ${len(params)}")
            if result_summary is not None:
                params.append(result_summary)
                assignments.append(f"result_summary = ${len(params)}")
            if deliverables is not None:
                params.append(json.dumps(list(deliverables)))
                assignments.append(f"delivered_artifact_ids = ${len(params)}::jsonb")
            if metadata_patch is not None:
                merged = {**current.metadata, **metadata_patch}
                params.append(json.dumps(merged))
                assignments.append(f"metadata_json = ${len(params)}::jsonb")
            sql = f'UPDATE "{self._schema}"."squad_tasks" SET {", ".join(assignments)} WHERE id = $1 RETURNING *'
            row = await conn.fetchrow(sql, *params)
        return _row_to_task(row)

    async def complete_task(
        self,
        *,
        task_id: str,
        agent_id: str,
        result_summary: str | None = None,
        deliverables: list[str] | None = None,
    ) -> TaskDescriptor:
        return await self.update_task_status(
            task_id=task_id,
            new_status="done",
            agent_id=agent_id,
            result_summary=result_summary,
            deliverables=deliverables,
        )

    async def sweep_expired_claims(self, *, batch_size: int = 50) -> list[ExpiredClaim]:
        """Atomically revert tasks past their claim TTL back to ``pending``.

        Returns a record per reverted task so callers can emit thread events
        or notify the prior assignee.
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""WITH expired AS (
                        SELECT id, assigned_agent_id
                          FROM "{self._schema}"."squad_tasks"
                         WHERE status = 'claimed'
                           AND claim_expires_at IS NOT NULL
                           AND claim_expires_at < NOW()
                         ORDER BY claim_expires_at ASC
                         LIMIT $1
                           FOR UPDATE SKIP LOCKED
                    )
                    UPDATE "{self._schema}"."squad_tasks" AS t
                       SET status = 'pending',
                           assigned_agent_id = NULL,
                           claim_token = NULL,
                           claim_expires_at = NULL,
                           version = t.version + 1,
                           updated_at = NOW()
                      FROM expired
                     WHERE t.id = expired.id
                 RETURNING t.id, t.thread_id, t.version,
                           expired.assigned_agent_id AS prior_agent""",
                max(1, min(int(batch_size), 500)),
            )
        return [
            ExpiredClaim(
                task_id=str(r["id"]),
                thread_id=str(r["thread_id"]),
                previously_assigned_agent_id=r["prior_agent"],
                version_after=int(r["version"]),
            )
            for r in rows
        ]

    async def escalate_task(
        self,
        *,
        task_id: str,
        agent_id: str,
        reason: str,
    ) -> TaskDescriptor:
        result = await self.update_task_status(
            task_id=task_id,
            new_status="escalated",
            agent_id=agent_id,
            error_message=reason,
        )
        try:
            from koda.control_plane.audit import record_audit_event

            record_audit_event(
                agent_id,
                event_type="squad.task.escalated",
                details={
                    "task_id": result.id,
                    "thread_id": result.thread_id,
                    "reason": reason,
                    "version": result.version,
                },
            )
        except Exception:
            log.exception("squad_task_audit_emit_failed", task_id=task_id)
        return result


_store: SquadTaskStore | None = None


def _build_store() -> SquadTaskStore | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return SquadTaskStore(dsn=POSTGRES_URL, schema=schema)


def get_squad_task_store() -> SquadTaskStore | None:
    """Return the singleton task store, or None if no Postgres DSN is configured."""
    global _store  # noqa: PLW0603
    if _store is None:
        _store = _build_store()
    return _store
