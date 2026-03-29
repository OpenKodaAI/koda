"""Scheduler persistence store over the shared primary backend."""

from __future__ import annotations

from typing import Any, cast

import koda.config as config_module
from koda.state_primary import (
    get_primary_state_backend,
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    run_coro_sync,
)


class SchedulerStore:
    """Persistence adapter for scheduled jobs and runs."""

    def primary_enabled(self) -> bool:
        return (
            config_module.STATE_BACKEND == "postgres"
            and get_primary_state_backend(agent_id=config_module.AGENT_ID) is not None
        )

    def _require_primary_backend(self) -> None:
        if config_module.STATE_BACKEND != "postgres":
            raise RuntimeError("scheduled_jobs_primary_mode_required")
        if get_primary_state_backend(agent_id=config_module.AGENT_ID) is None:
            raise RuntimeError("scheduled_jobs_primary_backend_unavailable")

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        self._require_primary_backend()
        return cast(
            dict[str, Any] | None,
            run_coro_sync(primary_fetch_one(query, params, agent_id=config_module.AGENT_ID)),
        )

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self._require_primary_backend()
        rows = run_coro_sync(primary_fetch_all(query, params, agent_id=config_module.AGENT_ID)) or []
        return [cast(dict[str, Any], row) for row in rows]

    def fetch_val(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        self._require_primary_backend()
        return run_coro_sync(primary_fetch_val(query, params, agent_id=config_module.AGENT_ID))

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        self._require_primary_backend()
        return int(run_coro_sync(primary_execute(query, params, agent_id=config_module.AGENT_ID)) or 0)

    def insert_returning_id(self, query: str, params: tuple[Any, ...] = ()) -> int:
        self._require_primary_backend()
        inserted = run_coro_sync(
            primary_fetch_val(f"{query.rstrip().rstrip(';')} RETURNING id", params, agent_id=config_module.AGENT_ID)
        )
        return int(inserted or 0)


_STORE = SchedulerStore()


def get_scheduler_store() -> SchedulerStore:
    return _STORE
