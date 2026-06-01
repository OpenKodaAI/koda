"""Recovery sweeps for stale runtime environments."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from koda.config import RUNTIME_STALE_AFTER_SECONDS
from koda.services.runtime.store import RuntimeStore


class RecoveryManager:
    """Plan stale-environment recovery actions."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def recover_stale(self) -> list[dict[str, object]]:
        """Plan one stale-environment recovery sweep."""
        stale_before = (datetime.now(UTC) - timedelta(seconds=RUNTIME_STALE_AFTER_SECONDS)).isoformat()
        recovered: list[dict[str, object]] = []
        for env in self.store.list_stale_environments(stale_before=stale_before):
            env_id = int(env["id"])
            task_id = int(env["task_id"])
            checkpoint = self.store.get_latest_checkpoint(task_id)
            recorded_processes = self.store.list_processes(task_id, env_id=env_id)
            alive_processes = [
                process_row for process_row in recorded_processes if str(process_row.get("status") or "") != "exited"
            ]
            if alive_processes:
                recovered.append(
                    {
                        "env_id": env_id,
                        "task_id": task_id,
                        "action": "reattach",
                        "alive_process_count": len(alive_processes),
                    }
                )
                continue
            if checkpoint is not None:
                recovered.append(
                    {
                        "env_id": env_id,
                        "task_id": task_id,
                        "action": "reconstruct",
                        "checkpoint_id": int(checkpoint["id"]),
                    }
                )
                continue
            recovered.append(
                {
                    "env_id": env_id,
                    "task_id": task_id,
                    "action": "mark_recoverable_failed",
                }
            )
        return recovered
