"""Squad router — periodic sweepers that keep squad state honest.

Wraps ``SquadTaskStore.sweep_expired_claims`` in a long-running coroutine so a
coordinator's claim TTL eventually triggers a revert when a worker goes
silent. When a thread store is available, each reverted claim emits a
``system_event`` so the transcript shows what happened. Each reverted task is
then dispatched again to its planned assignee once, and escalated on a later
expiry (D-097).

Phase 5 will wire this into ``supervisor.start()``. Until then, callers can
start it manually (``squad_router_tick`` sweeps one squad's expired claims).
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
# A handoff whose cycle's tasks changed less than this long ago is left to the task-cycle check
# that runs after its last destination's turn, so the sweep does not queue a second synthesis
# beside it.
_HANDOFF_COMPLETION_GRACE_S = 30.0
# A handoff requested longer ago than this is not swept: the sweep completes a check lost to a
# restart, a cancel or a refused dispatch, not a request nobody answered long ago.
_HANDOFF_COMPLETION_MAX_AGE_S = 24 * 3600.0


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
    open_handoffs_checked: int = 0

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
        # The last open handoff a full batch of the sweep reached; the next sweep starts after it.
        self._open_handoff_cursor = 0

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

    async def _sweep_claims(self, *, squad_id: str | None = None) -> list[ExpiredClaim]:
        # This runtime's queued and running squad turns renew their tasks' claims first, so only a
        # silent worker's claim expires; each runtime's router renews its own turns' claims (D-097).
        from koda.services.queue_manager import active_squad_turn_claims

        if claims := active_squad_turn_claims():
            from koda.config import SQUAD_CLAIM_TTL_S

            try:
                await self._task_store.renew_claims(claims=claims, ttl_seconds=SQUAD_CLAIM_TTL_S)
            except Exception:
                log.exception("squad_router_claim_renewal_failed", squad_id=squad_id)
        try:
            expired = await self._task_store.sweep_expired_claims(batch_size=self._batch_size, squad_id=squad_id)
        except Exception:
            log.exception("squad_router_sweep_failed", squad_id=squad_id)
            expired = []
        if expired and self._thread_store is not None:
            for claim in expired:
                if claim.refused:
                    # A worker refused the turn of a paused, spent or unreadable thread; no worker
                    # went silent, so no claim_expired (a pause is explained by its own event).
                    continue
                try:
                    await self._emit_revert_event(claim)
                except Exception:
                    log.exception(
                        "squad_router_thread_event_failed",
                        thread_id=claim.thread_id,
                        task_id=claim.task_id,
                    )
        if expired:
            from koda.services.queue_manager import redispatch_expired_squad_claim

            for claim in expired:
                try:
                    await redispatch_expired_squad_claim(task_id=claim.task_id)
                except Exception:
                    log.exception(
                        "squad_router_claim_redispatch_failed",
                        thread_id=claim.thread_id,
                        task_id=claim.task_id,
                    )
        return expired

    async def sweep_squad_claims(self, squad_id: str) -> SweepReport:
        """Revert the expired claims of ``squad_id``'s threads, then dispatch or escalate those tasks, and nothing else.

        This is the ``squad_router_tick`` sweep: a coordinator reaches only its own squad. The
        other sweeps (auto-election, timeouts, dead letters, budgets, open handoffs) cover every
        squad, so they run only in the background loop.
        """
        return SweepReport(expired_claims=await self._sweep_claims(squad_id=squad_id))

    async def sweep_once(self) -> SweepReport:
        expired = await self._sweep_claims()
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
        open_handoffs = 0
        try:
            open_handoffs = await self._sweep_open_handoffs()
        except Exception:
            log.exception("squad_router_open_handoff_sweep_failed")
        return SweepReport(
            expired_claims=expired,
            auto_elections=elections,
            timed_out_delegations=timed_out,
            timed_out_reply_obligations=reply_timeouts,
            dead_letters_reported=dead_letters,
            budget_alerts=budget_alerts,
            budget_auto_pauses=budget_pauses,
            open_handoffs_checked=open_handoffs,
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
            "expiry_count": claim.expiry_count,
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
        # Only the rooms the sweep still acts on: those not yet alerted at 80%, and open rooms at
        # their cap. A paused room already alerted is left out, so however many there are, an
        # open room at its cap is always reached.
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT id, status, budget_usd_cap, cost_usd_accum, metadata_json
                      FROM "{schema}"."squad_threads"
                     WHERE budget_usd_cap IS NOT NULL
                       AND budget_usd_cap > 0
                       AND cost_usd_accum >= budget_usd_cap * 0.8
                       AND (
                           (status IN ('open', 'paused')
                            AND COALESCE(metadata_json->>'budget_alert_80_sent', 'false') <> 'true')
                           OR (status = 'open' AND cost_usd_accum >= budget_usd_cap)
                       )
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
            # An open thread at its cap runs no turn, so it is paused, and the room told why, each
            # time it is open there: a room an operator reopened at its cap is paused again. Only
            # the UPDATE that paused it posts the event, so a pause that won the race (the
            # operator's, or another runtime's sweep) is not announced twice.
            if ratio >= 1.0 and row["status"] == "open":
                async with pool.acquire() as conn:
                    paused = await conn.execute(
                        f"""UPDATE "{schema}"."squad_threads"
                               SET status = 'paused',
                                   metadata_json = metadata_json || '{{"budget_auto_paused": true}}'::jsonb,
                                   updated_at = NOW()
                             WHERE id = $1
                               AND status = 'open'""",
                        thread_id,
                    )
                if paused != "UPDATE 1":
                    continue
                await self._emit_system_event(
                    thread_id=thread_id,
                    event_type="budget_exceeded_auto_pause",
                    content=f"[budget_exceeded_auto_pause] thread paused at ${cost:.4f} of ${cap:.4f}",
                    metadata={
                        "event_type": "budget_exceeded_auto_pause",
                        "reason": "budget",
                        "cost_usd": cost,
                        "budget_usd_cap": cap,
                    },
                )
                pauses += 1
        return alerts, pauses

    async def _sweep_open_handoffs(self) -> int:
        """Run the task-cycle check again for each handoff left open after its cycle's tasks ended (D-074).

        A handoff is checked when it was requested less than ``_HANDOFF_COMPLETION_MAX_AGE_S`` ago
        in an open thread, is still ``requested`` or ``accepted``, its cycle has a task, no task of
        its cycle is open (as in the check, open tasks of other cycles do not hold it, D-287), and
        its cycle's tasks have not changed for ``_HANDOFF_COMPLETION_GRACE_S``. The check runs as the
        follow-up of the cycle's most recently changed task that the coordinator does not own.
        Each sweep takes the next batch after the last one, so handoffs the check cannot close do
        not keep it from the others. A runtime checks a handoff only while it holds a transaction
        advisory lock on its id, so two runtimes do not check it at the same time.
        Returns the number of handoffs checked.
        """
        if self._thread_store is None:
            return 0
        pool = await self._thread_store._ensure_pool()  # noqa: SLF001
        schema = self._thread_store._schema  # noqa: SLF001
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT h.id, h.thread_id, h.metadata_json->'payload'->>'handoff_id' AS handoff_id,
                           cycle.task_id
                      FROM "{schema}"."squad_messages" AS h
                      JOIN "{schema}"."squad_threads" AS th ON th.id = h.thread_id
                      CROSS JOIN LATERAL (
                          SELECT t.id AS task_id
                            FROM "{schema}"."squad_tasks" AS t
                           WHERE t.thread_id = h.thread_id
                             AND t.metadata_json->>'handoff_correlation_id' = h.correlation_id
                             AND t.assigned_agent_id IS DISTINCT FROM th.coordinator_agent_id
                        ORDER BY t.updated_at DESC
                           LIMIT 1
                      ) AS cycle
                     WHERE h.created_at > NOW() - make_interval(secs => $1)
                       AND h.id > $4
                       AND h.thread_id IS NOT NULL
                       AND th.status = 'open'
                       AND th.coordinator_agent_id IS NOT NULL
                       AND h.message_type = 'system_event'
                       AND h.metadata_json->>'event_type' = 'handoff_event'
                       AND h.metadata_json->'payload'->>'status' IN ('requested', 'accepted')
                       AND NOT EXISTS (
                           SELECT 1
                             FROM "{schema}"."squad_messages" AS c
                            WHERE c.thread_id = h.thread_id
                              AND c.correlation_id = h.correlation_id
                              AND c.metadata_json->>'event_type' = 'handoff_event'
                              AND c.metadata_json->'payload'->>'handoff_id'
                                  = h.metadata_json->'payload'->>'handoff_id'
                              AND c.metadata_json->'payload'->>'status' NOT IN ('requested', 'accepted')
                       )
                       AND NOT EXISTS (
                           SELECT 1
                             FROM "{schema}"."squad_tasks" AS o
                            WHERE o.thread_id = h.thread_id
                              AND o.metadata_json->>'handoff_correlation_id' = h.correlation_id
                              AND (
                                  o.status IN ('pending', 'claimed', 'in_progress', 'blocked')
                                  OR o.updated_at > NOW() - make_interval(secs => $2)
                              )
                       )
                  ORDER BY h.id ASC
                     LIMIT $3""",
                float(_HANDOFF_COMPLETION_MAX_AGE_S),
                float(_HANDOFF_COMPLETION_GRACE_S),
                self._batch_size,
                self._open_handoff_cursor,
            )
        self._open_handoff_cursor = int(rows[-1]["id"]) if len(rows) >= self._batch_size else 0
        from koda.services.queue_manager import complete_open_squad_handoff

        checked = 0
        for row in rows:
            handoff_id = str(row["handoff_id"] or "")
            if not handoff_id:
                continue
            async with pool.acquire() as conn, conn.transaction():
                claimed = await conn.fetchval(
                    "SELECT pg_try_advisory_xact_lock(hashtext($1))", f"squad_handoff_completion:{handoff_id}"
                )
                if not claimed:
                    # Another runtime is checking this handoff now.
                    continue
                await complete_open_squad_handoff(
                    thread_id=str(row["thread_id"]), squad_task_id=str(row["task_id"]), handoff_id=handoff_id
                )
                checked += 1
        return checked

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
