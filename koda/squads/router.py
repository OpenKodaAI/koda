"""Squad router — periodic sweepers that keep squad state honest.

Wraps ``SquadTaskStore.sweep_expired_claims`` in a long-running coroutine so a
coordinator's claim TTL eventually triggers a revert when a worker goes
silent. When a thread store is available, each reverted claim emits a
``system_event`` so the transcript shows what happened.

Phase 5 will wire this into ``supervisor.start()``. Until then, callers can
start it manually (or trigger a one-off sweep via ``squad_router_tick``).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from koda.logging_config import get_logger
from koda.squads.coordinator import CoordinatorService
from koda.squads.tasks import ExpiredClaim, SquadTaskStore
from koda.squads.threads import SquadThreadStore

log = get_logger(__name__)

_DEFAULT_INTERVAL_S = 30.0
_DEFAULT_BATCH_SIZE = 50


def _decode_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


@dataclass
class AutoElection:
    squad_id: str
    coordinator_agent_id: str


@dataclass
class SweepReport:
    expired_claims: list[ExpiredClaim] = field(default_factory=list)
    auto_elections: list[AutoElection] = field(default_factory=list)
    timed_out_delegations: int = 0
    timed_out_reply_obligations: int = 0
    dead_letters_reported: int = 0
    budget_alerts: int = 0
    budget_auto_pauses: int = 0

    @property
    def reverted_count(self) -> int:
        return len(self.expired_claims)

    @property
    def elected_count(self) -> int:
        return len(self.auto_elections)


class SquadRouter:
    def __init__(
        self,
        *,
        task_store: SquadTaskStore,
        thread_store: SquadThreadStore | None = None,
        coordinator_service: CoordinatorService | None = None,
        sweep_interval_s: float = _DEFAULT_INTERVAL_S,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self._task_store = task_store
        self._thread_store = thread_store
        self._coordinator = coordinator_service
        self._sweep_interval_s = max(0.1, float(sweep_interval_s))
        self._batch_size = max(1, int(batch_size))
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run())

    async def run_forever(self) -> None:
        """Run in a lifecycle-supervised background loop."""
        self._stopping.clear()
        await self._run()

    async def stop(self) -> None:
        self._stopping.set()
        task = self._task
        self._task = None
        if task is None:
            return
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
            with suppress(BaseException):
                await task

    async def sweep_once(self) -> SweepReport:
        try:
            expired = await self._task_store.sweep_expired_claims(batch_size=self._batch_size)
        except Exception:
            log.exception("squad_router_sweep_failed")
            expired = []
        if expired and self._thread_store is not None:
            for claim in expired:
                try:
                    await self._emit_revert_event(claim)
                except Exception:
                    log.exception(
                        "squad_router_thread_event_failed",
                        thread_id=claim.thread_id,
                        task_id=claim.task_id,
                    )
        elections: list[AutoElection] = []
        try:
            elections = await self._sweep_auto_elections()
        except Exception:
            log.exception("squad_router_auto_election_failed")
        timed_out = 0
        reply_timeouts = 0
        dead_letters = 0
        budget_alerts = 0
        budget_pauses = 0
        try:
            timed_out = await self._sweep_delegation_timeouts()
        except Exception:
            log.exception("squad_router_delegation_timeout_failed")
        try:
            reply_timeouts = await self._sweep_reply_obligation_timeouts()
        except Exception:
            log.exception("squad_router_reply_timeout_failed")
        try:
            dead_letters = await self._sweep_dead_letters()
        except Exception:
            log.exception("squad_router_dead_letter_failed")
        try:
            budget_alerts, budget_pauses = await self._sweep_budgets()
        except Exception:
            log.exception("squad_router_budget_sweep_failed")
        return SweepReport(
            expired_claims=expired,
            auto_elections=elections,
            timed_out_delegations=timed_out,
            timed_out_reply_obligations=reply_timeouts,
            dead_letters_reported=dead_letters,
            budget_alerts=budget_alerts,
            budget_auto_pauses=budget_pauses,
        )

    async def _sweep_auto_elections(self) -> list[AutoElection]:
        """Promote a first-active participant for any squad whose policy is
        ``auto_first_active`` and that has no current coordinator."""
        if self._coordinator is None:
            return []
        candidate_squads = await self._coordinator.list_auto_election_candidates()
        elections: list[AutoElection] = []
        for squad_id in candidate_squads:
            agent_id = await self._coordinator.find_first_active_participant(squad_id)
            if not agent_id:
                continue
            try:
                state = await self._coordinator.elect(
                    squad_id=squad_id,
                    agent_id=agent_id,
                    triggered_by="squad_router",
                    reason="auto_first_active",
                    auto=True,
                    thread_store=self._thread_store,
                )
            except Exception:
                log.exception("squad_router_auto_election_elect_failed", squad_id=squad_id)
                continue
            if state.coordinator_agent_id:
                elections.append(AutoElection(squad_id=squad_id, coordinator_agent_id=state.coordinator_agent_id))
        return elections

    async def _emit_revert_event(self, claim: ExpiredClaim) -> None:
        if self._thread_store is None:
            return
        prior = claim.previously_assigned_agent_id or "(unknown)"
        prefix = claim.task_id[:8]
        metadata: dict[str, Any] = {
            "event_type": "claim_expired",
            "task_id": claim.task_id,
            "previously_assigned_agent_id": claim.previously_assigned_agent_id,
            "version_after": claim.version_after,
        }
        try:
            await self._thread_store.post_thread_message(
                thread_id=claim.thread_id,
                from_agent="system",
                content=f"[claim_expired] task {prefix}… reverted to pending (prior assignee: {prior})",
                message_type="system_event",
                metadata=metadata,
            )
        except KeyError:
            # Thread no longer exists (archived/deleted). Stay quiet — the
            # claim was still reverted in the DB; the missing audit message is
            # acceptable rather than crashing the sweeper.
            log.warning("squad_router_thread_missing", thread_id=claim.thread_id, task_id=claim.task_id)

    async def _sweep_delegation_timeouts(self) -> int:
        if self._thread_store is None:
            return 0
        from koda.config import SQUAD_MESSAGE_TIMEOUT_S

        pool = await self._thread_store._ensure_pool()  # noqa: SLF001 - router is the lifecycle owner.
        schema = self._thread_store._schema  # noqa: SLF001
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT m.id, m.thread_id, m.from_agent, m.to_agent, m.kind,
                            m.correlation_id, m.metadata_json
                      FROM "{schema}"."squad_messages" AS m
                     WHERE m.thread_id IS NOT NULL
                       AND m.kind IN ('task_request', 'delegation_request')
                       AND m.created_at < NOW() - ($1 || ' seconds')::interval
                       AND COALESCE(m.metadata_json->>'timeout_reported', 'false') <> 'true'
                       AND NOT EXISTS (
                           SELECT 1
                             FROM "{schema}"."squad_messages" AS r
                            WHERE r.thread_id = m.thread_id
                              AND r.id > m.id
                              AND r.kind IN ('task_result', 'delegation_result')
                              AND (
                                  (m.correlation_id IS NOT NULL AND r.correlation_id = m.correlation_id)
                                  OR (m.metadata_json->>'request_id' IS NOT NULL
                                      AND r.metadata_json->>'request_id' = m.metadata_json->>'request_id')
                              )
                       )
                     ORDER BY m.created_at ASC
                     LIMIT $2""",
                str(max(1, int(SQUAD_MESSAGE_TIMEOUT_S))),
                self._batch_size,
            )
        count = 0
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            request_id = metadata.get("request_id") or row["correlation_id"] or f"msg-{int(row['id'])}"
            await self._emit_system_event(
                thread_id=str(row["thread_id"]),
                event_type="delegation_timeout",
                content=f"[delegation_timeout] request {request_id} timed out",
                metadata={
                    "event_type": "delegation_timeout",
                    "message_id": f"msg-{int(row['id'])}",
                    "request_id": request_id,
                    "from_agent": row["from_agent"],
                    "to_agent": row["to_agent"],
                },
            )
            async with pool.acquire() as conn:
                await conn.execute(
                    f"""UPDATE "{schema}"."squad_messages"
                           SET metadata_json = metadata_json || '{{"timeout_reported": true}}'::jsonb
                         WHERE id = $1""",
                    int(row["id"]),
                )
            count += 1
        return count

    async def _sweep_reply_obligation_timeouts(self) -> int:
        if self._thread_store is None:
            return 0
        from koda.squads.replies import get_thread_reply_service

        service = get_thread_reply_service(self._thread_store)
        if service is None:
            return 0
        timed_out = await service.mark_timeouts(limit=self._batch_size)
        for obligation in timed_out:
            await self._emit_system_event(
                thread_id=obligation.thread_id,
                event_type="reply_obligation_timeout",
                content=(
                    f"[reply_obligation_timeout] {obligation.target_agent_id} did not answer obligation {obligation.id}"
                ),
                metadata={
                    "event_type": "reply_obligation_timeout",
                    "obligation_id": obligation.id,
                    "source_message_id": obligation.source_message_id,
                    "target_agent_id": obligation.target_agent_id,
                },
            )
        return len(timed_out)

    async def _sweep_dead_letters(self) -> int:
        if self._thread_store is None:
            return 0
        pool = await self._thread_store._ensure_pool()  # noqa: SLF001
        schema = self._thread_store._schema  # noqa: SLF001
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT r.message_id, r.to_agent_id, r.delivery_attempts, r.last_error,
                            m.thread_id, m.kind
                      FROM "{schema}"."squad_message_recipients" AS r
                      JOIN "{schema}"."squad_messages" AS m ON m.id = r.message_id
                     WHERE r.delivery_status = 'dead'
                       AND r.dead_reported_at IS NULL
                       AND m.thread_id IS NOT NULL
                     ORDER BY r.message_id ASC
                     LIMIT $1""",
                self._batch_size,
            )
        for row in rows:
            await self._emit_system_event(
                thread_id=str(row["thread_id"]),
                event_type="inbox_dead_letter",
                content=f"[inbox_dead_letter] msg-{int(row['message_id'])} could not be delivered",
                metadata={
                    "event_type": "inbox_dead_letter",
                    "message_id": f"msg-{int(row['message_id'])}",
                    "to_agent_id": row["to_agent_id"],
                    "delivery_attempts": int(row["delivery_attempts"] or 0),
                    "last_error": row["last_error"],
                    "kind": row["kind"],
                },
            )
        if rows:
            async with pool.acquire() as conn:
                for row in rows:
                    await conn.execute(
                        f"""UPDATE "{schema}"."squad_message_recipients"
                               SET dead_reported_at = NOW()
                             WHERE message_id = $1
                               AND to_agent_id = $2""",
                        int(row["message_id"]),
                        str(row["to_agent_id"]),
                    )
        return len(rows)

    async def _sweep_budgets(self) -> tuple[int, int]:
        if self._thread_store is None:
            return 0, 0
        pool = await self._thread_store._ensure_pool()  # noqa: SLF001
        schema = self._thread_store._schema  # noqa: SLF001
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT id, status, budget_usd_cap, cost_usd_accum, metadata_json
                      FROM "{schema}"."squad_threads"
                     WHERE status IN ('open', 'paused')
                       AND budget_usd_cap IS NOT NULL
                       AND budget_usd_cap > 0
                       AND cost_usd_accum >= budget_usd_cap * 0.8
                     ORDER BY updated_at ASC
                     LIMIT $1""",
                self._batch_size,
            )
        alerts = 0
        pauses = 0
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            thread_id = str(row["id"])
            cost = float(row["cost_usd_accum"] or 0)
            cap = float(row["budget_usd_cap"] or 0)
            ratio = cost / cap if cap > 0 else 0.0
            if ratio >= 0.8 and not metadata.get("budget_alert_80_sent"):
                await self._emit_system_event(
                    thread_id=thread_id,
                    event_type="budget_80_percent",
                    content=f"[budget_80_percent] thread spend is ${cost:.4f} of ${cap:.4f}",
                    metadata={"event_type": "budget_80_percent", "cost_usd": cost, "budget_usd_cap": cap},
                )
                async with pool.acquire() as conn:
                    await conn.execute(
                        f"""UPDATE "{schema}"."squad_threads"
                               SET metadata_json = metadata_json || '{{"budget_alert_80_sent": true}}'::jsonb,
                                   updated_at = NOW()
                             WHERE id = $1""",
                        thread_id,
                    )
                alerts += 1
            if ratio >= 1.0 and row["status"] == "open" and not metadata.get("budget_auto_paused"):
                async with pool.acquire() as conn:
                    await conn.execute(
                        f"""UPDATE "{schema}"."squad_threads"
                               SET status = 'paused',
                                   metadata_json = metadata_json || '{{"budget_auto_paused": true}}'::jsonb,
                                   updated_at = NOW()
                             WHERE id = $1
                               AND status = 'open'""",
                        thread_id,
                    )
                await self._emit_system_event(
                    thread_id=thread_id,
                    event_type="budget_exceeded_auto_pause",
                    content=f"[budget_exceeded_auto_pause] thread paused at ${cost:.4f} of ${cap:.4f}",
                    metadata={"event_type": "budget_exceeded_auto_pause", "cost_usd": cost, "budget_usd_cap": cap},
                )
                pauses += 1
        return alerts, pauses

    async def _emit_system_event(
        self,
        *,
        thread_id: str,
        event_type: str,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        if self._thread_store is None:
            return
        try:
            await self._thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent="system",
                content=content,
                message_type="system_event",
                metadata=metadata,
            )
            await self._thread_store.notify_event(
                thread_id=thread_id,
                event_type=event_type,
                data=metadata,
            )
        except KeyError:
            log.warning("squad_router_thread_missing", thread_id=thread_id, event_type=event_type)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            await self.sweep_once()
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._sweep_interval_s)
            except TimeoutError:
                continue


_router: SquadRouter | None = None


def _build_router() -> SquadRouter | None:
    from koda.squads.coordinator import get_coordinator_service
    from koda.squads.tasks import get_squad_task_store
    from koda.squads.threads import get_squad_thread_store

    task_store = get_squad_task_store()
    if task_store is None:
        return None
    return SquadRouter(
        task_store=task_store,
        thread_store=get_squad_thread_store(),
        coordinator_service=get_coordinator_service(),
    )


def get_squad_router() -> SquadRouter | None:
    """Return the singleton router, or None if no Postgres DSN is configured."""
    global _router  # noqa: PLW0603
    if _router is None:
        _router = _build_router()
    return _router
