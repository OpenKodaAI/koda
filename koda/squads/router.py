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


@dataclass
class AutoElection:
    squad_id: str
    coordinator_agent_id: str


@dataclass
class SweepReport:
    expired_claims: list[ExpiredClaim] = field(default_factory=list)
    auto_elections: list[AutoElection] = field(default_factory=list)

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
        return SweepReport(expired_claims=expired, auto_elections=elections)

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
