"""Orphan-worker cleanup contract for the control-plane supervisor.

When the supervisor exits ungracefully (SIGKILL, host crash, OOM), the agent
workers it spawned via ``asyncio.create_subprocess_exec`` keep running. They
are re-parented to PID 1 (init/launchd) and continue holding their per-agent
health ports.

The next supervisor start used to spawn a brand-new worker for the same
agent; that worker then crashed on ``OSError: [Errno 48] address already in
use``. The reconcile loop kept retrying — each retry pulled the asyncio
event loop into sync DB writes (audit + ``mark_apply_*``), starving the
HTTP request handlers and making ``/health`` appear hung.

These tests pin the resolution policy:

  * ``_extract_health_port`` parses the runtime URL.
  * ``_port_in_use``     is a non-disruptive bind probe.
  * ``_is_koda_agent_worker`` matches ONLY the exact ``-m koda
    --agent-id <X>`` shape — never the supervisor itself, never an
    unrelated process.
  * ``_kill_orphan_worker`` escalates SIGTERM → SIGKILL.
  * ``_ensure_health_port_free`` raises ``OrphanResolutionError`` when
    the port is held by something we refuse to kill, so the operator
    sees a clear log instead of an opaque crash loop.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from koda.control_plane.supervisor import (
    OrphanResolutionError,
    _ensure_health_port_free,
    _extract_health_port,
    _is_koda_agent_worker,
    _kill_orphan_worker,
    _port_in_use,
)


# ---------- _extract_health_port ----------------------------------------- #

class TestExtractHealthPort:
    def test_returns_port_from_explicit_url(self) -> None:
        assert _extract_health_port("http://127.0.0.1:8080/health") == 8080

    def test_returns_port_when_host_is_named(self) -> None:
        assert _extract_health_port("http://localhost:9123/health") == 9123

    def test_returns_none_when_port_is_implicit(self) -> None:
        assert _extract_health_port("https://example.com/health") is None

    def test_returns_none_for_garbage_input(self) -> None:
        assert _extract_health_port("not a url") is None
        assert _extract_health_port("") is None


# ---------- _port_in_use ------------------------------------------------- #

class TestPortInUse:
    def test_returns_true_when_port_is_held(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            assert _port_in_use("127.0.0.1", port) is True
        finally:
            sock.close()

    def test_returns_false_for_free_port(self) -> None:
        # Pick a free port by binding to :0 and immediately closing — there's
        # an inherent TOCTOU window but the kernel's ephemeral allocator
        # makes a same-test collision vanishingly unlikely.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        assert _port_in_use("127.0.0.1", port) is False


# ---------- _is_koda_agent_worker --------------------------------------- #

class TestIsKodaAgentWorker:
    @pytest.fixture
    def patched_ps(self):
        """Stub the ``ps`` subprocess used by ``_is_koda_agent_worker``."""

        def _make(stdout: str, returncode: int = 0):
            return SimpleNamespace(stdout=stdout, returncode=returncode)

        with patch(
            "koda.control_plane.supervisor.subprocess.run"
        ) as mock_run:
            mock_run.return_value = _make("")
            yield mock_run

    def test_matches_python_worker_with_correct_agent_id(self, patched_ps) -> None:
        patched_ps.return_value = SimpleNamespace(
            stdout="/usr/bin/python -m koda --agent-id KODA",
            returncode=0,
        )
        assert _is_koda_agent_worker(12345, "KODA") is True

    def test_rejects_supervisor_process(self, patched_ps) -> None:
        patched_ps.return_value = SimpleNamespace(
            stdout="/usr/bin/python -m koda.control_plane",
            returncode=0,
        )
        assert _is_koda_agent_worker(12345, "KODA") is False

    def test_rejects_different_agent_id(self, patched_ps) -> None:
        patched_ps.return_value = SimpleNamespace(
            stdout="/usr/bin/python -m koda --agent-id ATLAS",
            returncode=0,
        )
        assert _is_koda_agent_worker(12345, "KODA") is False

    def test_rejects_unrelated_process(self, patched_ps) -> None:
        patched_ps.return_value = SimpleNamespace(
            stdout="/usr/sbin/sshd -D",
            returncode=0,
        )
        assert _is_koda_agent_worker(12345, "KODA") is False

    def test_refuses_self_pid(self) -> None:
        import os

        # ``os.getpid`` is excluded BEFORE ``ps`` is consulted.
        assert _is_koda_agent_worker(os.getpid(), "KODA") is False

    def test_refuses_nonpositive_pid(self) -> None:
        assert _is_koda_agent_worker(0, "KODA") is False
        assert _is_koda_agent_worker(-1, "KODA") is False


# ---------- _kill_orphan_worker ----------------------------------------- #

class TestKillOrphanWorker:
    @pytest.mark.asyncio
    async def test_terminates_on_sigterm(self) -> None:
        """When the target dies on SIGTERM, no escalation."""
        kill_calls: list[tuple[int, int]] = []
        check_calls = {"count": 0}

        def fake_kill(pid: int, sig: int) -> None:
            kill_calls.append((pid, sig))
            if sig == 0:
                check_calls["count"] += 1
                # First check: still alive. Second check: gone.
                if check_calls["count"] >= 2:
                    raise ProcessLookupError

        with patch("koda.control_plane.supervisor.os.kill", side_effect=fake_kill):
            with patch("koda.control_plane.supervisor.asyncio.sleep", new_callable=AsyncMock):
                result = await _kill_orphan_worker(99999, reason="test")

        assert result is True
        # SIGTERM was sent, SIGKILL was NOT.
        signals = [sig for _, sig in kill_calls if sig != 0]
        import signal as _signal
        assert _signal.SIGTERM in signals
        assert _signal.SIGKILL not in signals

    @pytest.mark.asyncio
    async def test_escalates_to_sigkill_when_sigterm_ignored(self) -> None:
        kill_calls: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            kill_calls.append((pid, sig))
            # Probe always says "alive" so the helper escalates to SIGKILL.
            if sig == 0:
                return
            # Both SIGTERM and SIGKILL succeed silently.

        with patch("koda.control_plane.supervisor.os.kill", side_effect=fake_kill):
            with patch("koda.control_plane.supervisor.asyncio.sleep", new_callable=AsyncMock):
                result = await _kill_orphan_worker(99999, reason="test")

        # We escalated (SIGTERM then SIGKILL) but the process never died.
        signals = [sig for _, sig in kill_calls if sig != 0]
        import signal as _signal
        assert _signal.SIGTERM in signals
        assert _signal.SIGKILL in signals
        assert result is False  # final probe still found it alive

    @pytest.mark.asyncio
    async def test_returns_true_when_pid_already_gone(self) -> None:
        with patch(
            "koda.control_plane.supervisor.os.kill",
            side_effect=ProcessLookupError,
        ):
            result = await _kill_orphan_worker(99999, reason="test")
        assert result is True


# ---------- _ensure_health_port_free ------------------------------------ #

class TestEnsureHealthPortFree:
    @pytest.mark.asyncio
    async def test_no_op_when_port_already_free(self) -> None:
        with patch(
            "koda.control_plane.supervisor._port_in_use",
            return_value=False,
        ):
            with patch(
                "koda.control_plane.supervisor._pids_listening_on"
            ) as mock_pids:
                await _ensure_health_port_free("127.0.0.1", 8080, "KODA")
                mock_pids.assert_not_called()

    @pytest.mark.asyncio
    async def test_kills_recognised_orphan_then_returns(self) -> None:
        # Sequence: port is in use → orphan worker → kill → port becomes free.
        port_states = iter([True, False])
        with patch(
            "koda.control_plane.supervisor._port_in_use",
            side_effect=lambda host, port: next(port_states),
        ):
            with patch(
                "koda.control_plane.supervisor._pids_listening_on",
                return_value=[42],
            ):
                with patch(
                    "koda.control_plane.supervisor._is_koda_agent_worker",
                    return_value=True,
                ):
                    with patch(
                        "koda.control_plane.supervisor._kill_orphan_worker",
                        new_callable=AsyncMock,
                        return_value=True,
                    ) as mock_kill:
                        await _ensure_health_port_free(
                            "127.0.0.1", 8080, "KODA"
                        )
                        mock_kill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_port_holder_is_not_recognised(self) -> None:
        with patch(
            "koda.control_plane.supervisor._port_in_use",
            return_value=True,
        ):
            with patch(
                "koda.control_plane.supervisor._pids_listening_on",
                return_value=[42],
            ):
                with patch(
                    "koda.control_plane.supervisor._is_koda_agent_worker",
                    return_value=False,
                ):
                    with pytest.raises(OrphanResolutionError):
                        await _ensure_health_port_free(
                            "127.0.0.1", 8080, "KODA"
                        )

    @pytest.mark.asyncio
    async def test_raises_when_lsof_cannot_identify_holder(self) -> None:
        with patch(
            "koda.control_plane.supervisor._port_in_use",
            return_value=True,
        ):
            with patch(
                "koda.control_plane.supervisor._pids_listening_on",
                return_value=[],
            ):
                with pytest.raises(OrphanResolutionError):
                    await _ensure_health_port_free(
                        "127.0.0.1", 8080, "KODA"
                    )

    @pytest.mark.asyncio
    async def test_raises_when_kill_fails(self) -> None:
        with patch(
            "koda.control_plane.supervisor._port_in_use",
            return_value=True,
        ):
            with patch(
                "koda.control_plane.supervisor._pids_listening_on",
                return_value=[42],
            ):
                with patch(
                    "koda.control_plane.supervisor._is_koda_agent_worker",
                    return_value=True,
                ):
                    with patch(
                        "koda.control_plane.supervisor._kill_orphan_worker",
                        new_callable=AsyncMock,
                        return_value=False,
                    ):
                        with pytest.raises(OrphanResolutionError):
                            await _ensure_health_port_free(
                                "127.0.0.1", 8080, "KODA"
                            )

    @pytest.mark.asyncio
    async def test_raises_when_port_still_in_use_after_kill(self) -> None:
        # Edge case: kill claims success but the port is somehow still bound
        # (e.g. another orphan grabbed it in the same instant). We refuse to
        # spawn rather than return prematurely and hit a crash loop.
        with patch(
            "koda.control_plane.supervisor._port_in_use",
            return_value=True,
        ):
            with patch(
                "koda.control_plane.supervisor._pids_listening_on",
                return_value=[42],
            ):
                with patch(
                    "koda.control_plane.supervisor._is_koda_agent_worker",
                    return_value=True,
                ):
                    with patch(
                        "koda.control_plane.supervisor._kill_orphan_worker",
                        new_callable=AsyncMock,
                        return_value=True,
                    ):
                        with pytest.raises(OrphanResolutionError):
                            await _ensure_health_port_free(
                                "127.0.0.1", 8080, "KODA"
                            )
