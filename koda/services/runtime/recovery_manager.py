"""Recovery sweeps for stale runtime environments."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from koda.config import RUNTIME_STALE_AFTER_SECONDS
from koda.services.runtime.postgres_store import PostgresRuntimeStore


class RecoveryManager:
    """List the stale environments the recovery sweep recovers."""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        self.store = store

    def recover_stale(self) -> list[dict[str, object]]:
        """Return one entry per stale environment.

        ``orphan`` is true when no recorded process is alive and the task has no
        checkpoint; the controller counts those separately.
        """
        stale_before = (datetime.now(UTC) - timedelta(seconds=RUNTIME_STALE_AFTER_SECONDS)).isoformat()
        recovered: list[dict[str, object]] = []
        for env in self.store.list_stale_environments(stale_before=stale_before):
            env_id = int(env["id"])
            task_id = int(env["task_id"])
            checkpoint = self.store.get_latest_checkpoint(task_id)
            recorded_processes = self.store.list_processes(task_id, env_id=env_id)
            alive = any(str(process_row.get("status") or "") != "exited" for process_row in recorded_processes)
            recovered.append({"env_id": env_id, "task_id": task_id, "orphan": not alive and checkpoint is None})
        return recovered
