"""Squad coordinator service.

Coordination is a *role* an agent occupies, not a separate agent type. This
module manages elections, demotions, eligibility checks, and the audit trail
in ``squad_coordinator_history``. When a thread store is available, every
elect/demote also emits a typed ``system_event`` row in each open thread of
the squad so the change is visible in the conversation transcript.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_POLICIES = {"manual", "auto_first_active", "weighted"}


def _emit_audit(*, scope: str, event_type: str, details: dict[str, Any]) -> None:
    """Best-effort audit emit. Swallow any failure (the coordinator op already
    succeeded; missing audit is a governance debt, not a correctness issue)."""
    try:
        from koda.control_plane.audit import record_audit_event

        record_audit_event(scope, event_type=event_type, details=details)
    except Exception:
        log.exception("squad_audit_emit_failed", scope=scope, event_type=event_type)


# Tools the coordinator must be allowed to call to perform its role. A spec
# missing any of these is a no-op election: the agent literally cannot
# orchestrate without them.
REQUIRED_COORDINATOR_TOOL_IDS: tuple[str, ...] = (
    "agent_delegate",
    "squad_thread_create",
    "squad_post",
    "squad_task_create",
    "squad_task_claim",
    "squad_task_update",
)


class CoordinatorConflictError(RuntimeError):
    """Squad already has an active coordinator and ``force_replace`` is False."""


class CoordinatorEligibilityError(ValueError):
    """Agent's ``tool_policy.allowed_tool_ids`` is missing required coordinator tools."""


class CoordinatorNotFoundError(LookupError):
    """No active coordinator state row for the squad."""


@dataclass
class CoordinatorState:
    squad_id: str
    coordinator_agent_id: str | None
    election_policy: str
    auto_demote_after_inactive_days: int | None
    elected_at: datetime | None
    elected_by_agent_id: str | None
    last_active_at: datetime | None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass
class CoordinatorHistoryEntry:
    id: int
    squad_id: str
    event_type: str
    coordinator_agent_id: str | None
    previous_coordinator_agent_id: str | None
    triggered_by_agent_id: str | None
    reason: str | None
    metadata: dict[str, Any]
    created_at: datetime | None


def _decode_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def _row_to_state(row: Any) -> CoordinatorState:
    return CoordinatorState(
        squad_id=row["squad_id"],
        coordinator_agent_id=row["coordinator_agent_id"],
        election_policy=row["election_policy"],
        auto_demote_after_inactive_days=row["auto_demote_after_inactive_days"],
        elected_at=row["elected_at"],
        elected_by_agent_id=row["elected_by_agent_id"],
        last_active_at=row["last_active_at"],
        metadata=_decode_metadata(row["metadata_json"]),
        updated_at=row["updated_at"],
    )


def _row_to_history(row: Any) -> CoordinatorHistoryEntry:
    return CoordinatorHistoryEntry(
        id=int(row["id"]),
        squad_id=row["squad_id"],
        event_type=row["event_type"],
        coordinator_agent_id=row["coordinator_agent_id"],
        previous_coordinator_agent_id=row["previous_coordinator_agent_id"],
        triggered_by_agent_id=row["triggered_by_agent_id"],
        reason=row["reason"],
        metadata=_decode_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def validate_eligibility(agent_spec: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Return (is_eligible, missing_tool_ids). When ``agent_spec`` is None the
    check is skipped — the caller has already trusted the agent."""
    if agent_spec is None:
        return True, []
    tool_policy = agent_spec.get("tool_policy") or {}
    if not isinstance(tool_policy, dict):
        return False, list(REQUIRED_COORDINATOR_TOOL_IDS)
    allowed = tool_policy.get("allowed_tool_ids") or []
    if not isinstance(allowed, (list, tuple, set)):
        return False, list(REQUIRED_COORDINATOR_TOOL_IDS)
    allowed_set = {str(x) for x in allowed if isinstance(x, str)}
    missing = [t for t in REQUIRED_COORDINATOR_TOOL_IDS if t not in allowed_set]
    return (not missing), missing


class CoordinatorService:
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

    async def current_coordinator(self, squad_id: str) -> CoordinatorState | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_coordinator_state" WHERE squad_id = $1',
                squad_id,
            )
        return _row_to_state(row) if row is not None else None

    async def list_auto_election_candidates(self) -> list[str]:
        """Squads with ``election_policy = 'auto_first_active'`` and no active
        coordinator yet. Returned in stable squad_id order."""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT squad_id FROM "{self._schema}"."squad_coordinator_state"
                     WHERE election_policy = 'auto_first_active'
                       AND coordinator_agent_id IS NULL
                     ORDER BY squad_id ASC"""
            )
        return [row["squad_id"] for row in rows]

    async def find_first_active_participant(self, squad_id: str) -> str | None:
        """Pick the agent_id of the participant in any open thread of the squad
        with the earliest ``joined_at``. ``None`` if no active participant."""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT p.agent_id
                       FROM "{self._schema}"."squad_thread_participants" AS p
                       JOIN "{self._schema}"."squad_threads" AS t ON t.id = p.thread_id
                      WHERE t.squad_id = $1
                        AND p.left_at IS NULL
                        AND t.status = 'open'
                      ORDER BY p.joined_at ASC
                      LIMIT 1""",
                squad_id,
            )
        return row["agent_id"] if row is not None else None

    async def list_history(
        self,
        *,
        squad_id: str,
        limit: int = 20,
    ) -> list[CoordinatorHistoryEntry]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT * FROM "{self._schema}"."squad_coordinator_history"
                     WHERE squad_id = $1
                  ORDER BY created_at DESC
                     LIMIT $2""",
                squad_id,
                max(1, min(int(limit), 500)),
            )
        return [_row_to_history(r) for r in rows]

    async def set_election_policy(
        self,
        *,
        squad_id: str,
        policy: str,
        triggered_by: str | None = None,
        reason: str | None = None,
        auto_demote_after_inactive_days: int | None = None,
    ) -> CoordinatorState:
        if policy not in _VALID_POLICIES:
            raise ValueError(f"election_policy must be one of {sorted(_VALID_POLICIES)}")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO "{self._schema}"."squad_coordinator_state"
                        (squad_id, election_policy, auto_demote_after_inactive_days)
                      VALUES ($1, $2, $3)
                      ON CONFLICT (squad_id) DO UPDATE SET
                          election_policy = EXCLUDED.election_policy,
                          auto_demote_after_inactive_days = EXCLUDED.auto_demote_after_inactive_days,
                          updated_at = NOW()
                      RETURNING *""",
                squad_id,
                policy,
                auto_demote_after_inactive_days,
            )
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."squad_coordinator_history"
                        (squad_id, event_type, triggered_by_agent_id, reason, metadata_json)
                      VALUES ($1, 'policy_changed', $2, $3, $4::jsonb)""",
                squad_id,
                triggered_by,
                reason,
                json.dumps({"policy": policy, "auto_demote_after_inactive_days": auto_demote_after_inactive_days}),
            )
        return _row_to_state(row)

    async def elect(
        self,
        *,
        squad_id: str,
        agent_id: str,
        triggered_by: str | None = None,
        reason: str | None = None,
        force_replace: bool = False,
        agent_spec: dict[str, Any] | None = None,
        auto: bool = False,
        thread_store: Any | None = None,
    ) -> CoordinatorState:
        if not squad_id or not agent_id:
            raise ValueError("squad_id and agent_id are required")
        eligible, missing = validate_eligibility(agent_spec)
        if not eligible:
            raise CoordinatorEligibilityError(f"agent {agent_id!r} cannot be coordinator: missing tools {missing}")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            current = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_coordinator_state" WHERE squad_id = $1 FOR UPDATE',
                squad_id,
            )
            previous = current["coordinator_agent_id"] if current is not None else None
            if previous and previous != agent_id and not force_replace:
                raise CoordinatorConflictError(
                    f"squad {squad_id!r} already has coordinator {previous!r}; pass force_replace=True"
                )
            row = await conn.fetchrow(
                f"""INSERT INTO "{self._schema}"."squad_coordinator_state"
                        (squad_id, coordinator_agent_id, elected_at, elected_by_agent_id, last_active_at)
                      VALUES ($1, $2, NOW(), $3, NOW())
                      ON CONFLICT (squad_id) DO UPDATE SET
                          coordinator_agent_id = EXCLUDED.coordinator_agent_id,
                          elected_at = EXCLUDED.elected_at,
                          elected_by_agent_id = EXCLUDED.elected_by_agent_id,
                          last_active_at = EXCLUDED.last_active_at,
                          updated_at = NOW()
                      RETURNING *""",
                squad_id,
                agent_id,
                triggered_by,
            )
            event_type = "auto_elected" if auto else ("replaced" if previous else "elected")
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."squad_coordinator_history"
                        (squad_id, event_type, coordinator_agent_id,
                         previous_coordinator_agent_id, triggered_by_agent_id, reason, metadata_json)
                      VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)""",
                squad_id,
                event_type,
                agent_id,
                previous,
                triggered_by,
                reason,
                json.dumps({"force_replace": force_replace, "auto": auto}),
            )
        await self._emit_thread_system_event(
            thread_store=thread_store,
            squad_id=squad_id,
            event_type="coordinator_changed",
            payload={
                "kind": event_type,
                "new_coordinator": agent_id,
                "previous_coordinator": previous,
                "triggered_by": triggered_by,
                "reason": reason,
            },
        )
        _emit_audit(
            scope=triggered_by or agent_id,
            event_type=f"squad.coordinator.{event_type}",
            details={
                "squad_id": squad_id,
                "new_coordinator": agent_id,
                "previous_coordinator": previous,
                "triggered_by": triggered_by,
                "reason": reason,
            },
        )
        return _row_to_state(row)

    async def demote(
        self,
        *,
        squad_id: str,
        triggered_by: str | None = None,
        reason: str | None = None,
        auto: bool = False,
        thread_store: Any | None = None,
    ) -> CoordinatorState:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            current = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_coordinator_state" WHERE squad_id = $1 FOR UPDATE',
                squad_id,
            )
            if current is None or current["coordinator_agent_id"] is None:
                raise CoordinatorNotFoundError(f"squad {squad_id!r} has no active coordinator")
            previous = current["coordinator_agent_id"]
            row = await conn.fetchrow(
                f"""UPDATE "{self._schema}"."squad_coordinator_state"
                       SET coordinator_agent_id = NULL,
                           elected_at = NULL,
                           elected_by_agent_id = NULL,
                           updated_at = NOW()
                     WHERE squad_id = $1
                     RETURNING *""",
                squad_id,
            )
            event_type = "auto_demoted" if auto else "demoted"
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."squad_coordinator_history"
                        (squad_id, event_type, coordinator_agent_id,
                         previous_coordinator_agent_id, triggered_by_agent_id, reason, metadata_json)
                      VALUES ($1, $2, NULL, $3, $4, $5, $6::jsonb)""",
                squad_id,
                event_type,
                previous,
                triggered_by,
                reason,
                json.dumps({"auto": auto}),
            )
        await self._emit_thread_system_event(
            thread_store=thread_store,
            squad_id=squad_id,
            event_type="coordinator_changed",
            payload={
                "kind": event_type,
                "new_coordinator": None,
                "previous_coordinator": previous,
                "triggered_by": triggered_by,
                "reason": reason,
            },
        )
        _emit_audit(
            scope=triggered_by or previous or "system",
            event_type=f"squad.coordinator.{event_type}",
            details={
                "squad_id": squad_id,
                "previous_coordinator": previous,
                "triggered_by": triggered_by,
                "reason": reason,
            },
        )
        return _row_to_state(row)

    async def _emit_thread_system_event(
        self,
        *,
        thread_store: Any | None,
        squad_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if thread_store is None:
            return
        try:
            threads = await thread_store.list_threads(squad_id=squad_id, status="open")
        except Exception:
            log.exception("coordinator_thread_lookup_failed", squad_id=squad_id)
            return
        from_agent = payload.get("triggered_by") or "system"
        for thread in threads:
            try:
                await thread_store.post_thread_message(
                    thread_id=thread.id,
                    from_agent=from_agent,
                    content=self._format_event_summary(event_type, payload),
                    message_type="system_event",
                    metadata={"event_type": event_type, **payload},
                )
            except Exception:
                log.exception(
                    "coordinator_thread_event_emit_failed",
                    thread_id=thread.id,
                    squad_id=squad_id,
                )

    @staticmethod
    def _format_event_summary(event_type: str, payload: dict[str, Any]) -> str:
        kind = payload.get("kind") or event_type
        prev = payload.get("previous_coordinator") or "(none)"
        new = payload.get("new_coordinator") or "(none)"
        triggered = payload.get("triggered_by") or "system"
        reason = payload.get("reason")
        suffix = f" — {reason}" if reason else ""
        return f"[{kind}] coordinator changed: {prev} -> {new} (by {triggered}){suffix}"


_service: CoordinatorService | None = None


def _build_service() -> CoordinatorService | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return CoordinatorService(dsn=POSTGRES_URL, schema=schema)


def get_coordinator_service() -> CoordinatorService | None:
    """Return the singleton coordinator service, or None if no Postgres DSN is configured."""
    global _service  # noqa: PLW0603
    if _service is None:
        _service = _build_service()
    return _service
