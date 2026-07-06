"""Persistent port allocation helpers for isolated runtime environments."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterable

from koda.services.runtime.store import RuntimeStore


class PortAllocator:
    """Reserve localhost ports and persist the reservation in the runtime store."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store
        self._lock = threading.Lock()

    def allocate(
        self,
        *,
        task_id: int,
        env_id: int | None,
        purpose: str,
        start_port: int,
        host: str = "127.0.0.1",
        metadata: dict[str, object] | None = None,
        window: int = 500,
    ) -> dict[str, int | str]:
        with self._lock:
            for port in range(start_port, start_port + window):
                if self.store.is_port_allocated(host, port):
                    continue
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        sock.bind((host, port))
                    except OSError:
                        continue
                    try:
                        allocation_id = self.store.add_port_allocation(
                            task_id=task_id,
                            env_id=env_id,
                            purpose=purpose,
                            host=host,
                            port=port,
                            metadata=metadata,
                        )
                    except Exception:
                        continue
                return {"id": allocation_id, "host": host, "port": port}
        raise RuntimeError(f"no free port available for purpose={purpose}")

    def release_task_ports(self, task_id: int) -> None:
        """Release all active port allocations for one task."""
        self.release_ports(task_id=task_id)

    def release_ports(
        self,
        *,
        task_id: int,
        env_id: int | None = None,
        purposes: Iterable[str] | None = None,
    ) -> None:
        purpose_set = {str(purpose) for purpose in purposes or ()}
        with self._lock:
            for allocation in self.store.list_port_allocations(task_id):
                if env_id is not None and int(allocation.get("env_id") or 0) != env_id:
                    continue
                if purpose_set and str(allocation.get("purpose") or "") not in purpose_set:
                    continue
                if str(allocation.get("status")) in {"released", "closed"}:
                    continue
                self.store.update_port_allocation(int(allocation["id"]), status="released", released=True)
