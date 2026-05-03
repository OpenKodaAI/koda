"""Pure-logic tests for koda.services.runtime.port_allocator.PortAllocator.

The allocator is the boundary that prevents two runtime tasks from claiming
the same localhost port (e.g. dev servers, NoVNC streams). The contract is:

  * Skip ports already marked allocated in the store.
  * Bind-test the next candidate; on EADDRINUSE skip and try the next.
  * Persist the reservation only after a successful bind.
  * Reservation is per (host, port) within an agent scope.
  * release_ports filters by env_id and purpose; mutates only matching rows.
  * Lock serializes concurrent allocate calls in the same process.

We stub RuntimeStore with an in-memory fake; sockets are bound for real so
the bind-test path is exercised against the OS.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterable
from typing import Any

import pytest

from koda.services.runtime.port_allocator import PortAllocator


class _FakeStore:
    """Minimal in-memory RuntimeStore stand-in for port-allocation tests."""

    def __init__(self) -> None:
        self._next_id = 1
        self.rows: list[dict[str, Any]] = []
        self.add_calls: int = 0

    def is_port_allocated(self, host: str, port: int) -> bool:
        return any(
            r["host"] == host and r["port"] == port and r["status"] in {"allocated", "active"} for r in self.rows
        )

    def add_port_allocation(
        self,
        *,
        task_id: int,
        env_id: int | None,
        purpose: str,
        host: str,
        port: int,
        metadata: dict[str, object] | None = None,
    ) -> int:
        self.add_calls += 1
        row = {
            "id": self._next_id,
            "task_id": task_id,
            "env_id": env_id,
            "purpose": purpose,
            "host": host,
            "port": port,
            "status": "allocated",
            "metadata": dict(metadata or {}),
        }
        self._next_id += 1
        self.rows.append(row)
        return row["id"]

    def list_port_allocations(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows if r["task_id"] == task_id]

    def update_port_allocation(
        self,
        allocation_id: int,
        *,
        status: str | None = None,
        metadata: dict[str, object] | None = None,
        released: bool = False,
    ) -> None:
        for r in self.rows:
            if r["id"] == allocation_id:
                if status is not None:
                    r["status"] = status
                if metadata is not None:
                    r["metadata"] = dict(metadata)
                if released:
                    r["released"] = True
                return


class _FlakyAddStore(_FakeStore):
    """Store whose add_port_allocation raises a configurable number of times.

    Used to verify the allocator catches store errors and tries the next port.
    """

    def __init__(self, fail_first: int) -> None:
        super().__init__()
        self.fail_first = fail_first

    def add_port_allocation(self, **kwargs):  # type: ignore[override]
        if self.add_calls < self.fail_first:
            self.add_calls += 1
            raise RuntimeError("simulated db error")
        return super().add_port_allocation(**kwargs)


@pytest.fixture
def free_port() -> int:
    """Return a port number that is currently free on 127.0.0.1.

    Closes the probe socket immediately, so there's a small TOCTOU window.
    Tests that need a guaranteed-free port use a wider start_port window
    so the allocator can fall through if the OS reassigns.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# Allocate happy path


def test_allocate_uses_first_free_port(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)

    out = allocator.allocate(task_id=1, env_id=10, purpose="vnc", start_port=free_port, window=50)
    assert out["host"] == "127.0.0.1"
    assert isinstance(out["port"], int)
    assert out["port"] >= free_port
    assert out["id"] == 1
    assert len(store.rows) == 1
    assert store.rows[0]["purpose"] == "vnc"
    assert store.rows[0]["env_id"] == 10


def test_allocate_skips_ports_marked_allocated(free_port: int) -> None:
    store = _FakeStore()
    # Pre-mark a few ports as allocated to force the allocator to scan past.
    for offset in range(3):
        store.rows.append(
            {
                "id": 1000 + offset,
                "task_id": 0,
                "env_id": None,
                "purpose": "test",
                "host": "127.0.0.1",
                "port": free_port + offset,
                "status": "allocated",
                "metadata": {},
            }
        )
    allocator = PortAllocator(store)

    out = allocator.allocate(task_id=2, env_id=None, purpose="dev", start_port=free_port, window=50)
    # The allocator must have advanced past the pre-allocated three.
    assert int(out["port"]) >= free_port + 3


def test_allocate_persists_metadata(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)
    allocator.allocate(
        task_id=5,
        env_id=20,
        purpose="novnc",
        start_port=free_port,
        metadata={"display": ":99", "protocol": "vnc"},
    )
    assert store.rows[0]["metadata"] == {"display": ":99", "protocol": "vnc"}


def test_allocate_default_host_is_loopback(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)
    out = allocator.allocate(task_id=1, env_id=None, purpose="any", start_port=free_port)
    assert out["host"] == "127.0.0.1"


def test_allocate_window_is_respected_when_no_free_port(free_port: int) -> None:
    """If the entire window is marked allocated in the store, raise."""
    store = _FakeStore()
    for offset in range(50):
        store.rows.append(
            {
                "id": 1000 + offset,
                "task_id": 0,
                "env_id": None,
                "purpose": "test",
                "host": "127.0.0.1",
                "port": free_port + offset,
                "status": "allocated",
                "metadata": {},
            }
        )
    allocator = PortAllocator(store)
    with pytest.raises(RuntimeError, match="no free port"):
        allocator.allocate(task_id=1, env_id=None, purpose="vnc", start_port=free_port, window=50)


def test_allocate_falls_through_store_errors(free_port: int) -> None:
    """add_port_allocation raises N times, then the allocator tries the next port."""
    store = _FlakyAddStore(fail_first=2)
    allocator = PortAllocator(store)
    out = allocator.allocate(task_id=1, env_id=None, purpose="vnc", start_port=free_port, window=10)
    # 3rd attempt succeeds — port should be at least free_port + 2.
    assert int(out["port"]) >= free_port + 2
    # Exactly 3 add attempts (2 failures + 1 success).
    assert store.add_calls == 3


# Release path


def test_release_task_ports_marks_all_active_as_released(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)
    a = allocator.allocate(task_id=1, env_id=10, purpose="vnc", start_port=free_port, window=50)
    b = allocator.allocate(task_id=1, env_id=10, purpose="dev", start_port=free_port, window=50)
    allocator.release_task_ports(task_id=1)
    by_id = {r["id"]: r for r in store.rows}
    assert by_id[a["id"]]["status"] == "released"
    assert by_id[a["id"]]["released"] is True
    assert by_id[b["id"]]["status"] == "released"


def test_release_filters_by_env_id(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)
    a = allocator.allocate(task_id=1, env_id=10, purpose="vnc", start_port=free_port, window=50)
    b = allocator.allocate(task_id=1, env_id=20, purpose="dev", start_port=free_port, window=50)
    allocator.release_ports(task_id=1, env_id=10)
    by_id = {r["id"]: r for r in store.rows}
    assert by_id[a["id"]]["status"] == "released"
    assert by_id[b["id"]]["status"] == "allocated"  # other env left alone


def test_release_filters_by_purpose(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)
    a = allocator.allocate(task_id=1, env_id=10, purpose="vnc", start_port=free_port, window=50)
    b = allocator.allocate(task_id=1, env_id=10, purpose="dev", start_port=free_port, window=50)
    allocator.release_ports(task_id=1, purposes=["vnc"])
    by_id = {r["id"]: r for r in store.rows}
    assert by_id[a["id"]]["status"] == "released"
    assert by_id[b["id"]]["status"] == "allocated"


def test_release_skips_already_released(free_port: int) -> None:
    store = _FakeStore()
    allocator = PortAllocator(store)
    allocator.allocate(task_id=1, env_id=10, purpose="vnc", start_port=free_port, window=50)
    allocator.release_task_ports(task_id=1)
    # Second release is a no-op (status check inside release_ports).
    allocator.release_task_ports(task_id=1)
    assert all(r["status"] == "released" for r in store.rows)


def test_release_with_purposes_iterable(free_port: int) -> None:
    """release_ports accepts any iterable for purposes (set, tuple, generator)."""
    store = _FakeStore()
    allocator = PortAllocator(store)
    a = allocator.allocate(task_id=1, env_id=10, purpose="vnc", start_port=free_port, window=50)
    b = allocator.allocate(task_id=1, env_id=10, purpose="novnc", start_port=free_port, window=50)
    c = allocator.allocate(task_id=1, env_id=10, purpose="dev", start_port=free_port, window=50)
    purposes: Iterable[str] = (p for p in ("vnc", "novnc"))
    allocator.release_ports(task_id=1, purposes=purposes)
    by_id = {r["id"]: r for r in store.rows}
    assert by_id[a["id"]]["status"] == "released"
    assert by_id[b["id"]]["status"] == "released"
    assert by_id[c["id"]]["status"] == "allocated"


# Concurrency: the threading.Lock serializes allocations in the same allocator


def test_concurrent_allocations_from_same_allocator_serialize(free_port: int) -> None:
    """Run 8 concurrent allocate calls; each should land on a distinct port."""
    store = _FakeStore()
    allocator = PortAllocator(store)
    results: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def one(idx: int) -> None:
        try:
            barrier.wait(timeout=5)
            out = allocator.allocate(task_id=idx, env_id=idx, purpose="dev", start_port=free_port, window=200)
            results.append(int(out["port"]))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"unexpected errors: {errors}"
    assert len(results) == 8
    # All distinct ports.
    assert len(set(results)) == 8
