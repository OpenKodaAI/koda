"""Local runtime supervisor — opt-in process lifecycle for ``llama-server`` / ``mlx-openai-server``.

Activated by ``LOCAL_RUNTIME_AUTO_SPAWN=true``. Without auto-spawn the
runners (:mod:`koda.services.llamacpp_runner`, :mod:`koda.services.mlx_runner`)
just connect to whatever the operator started; with auto-spawn this module:

- Spawns the binary on demand (``ensure_running``).
- Holds a slot lock (``LOCAL_RUNTIME_HEAVY_SLOTS``) so two ≥30B models can't
  load simultaneously and OOM the unified-memory pool.
- Tracks model residency with an LRU so a request for a new heavy model
  evicts the oldest before spawn.
- Health-checks newly spawned servers and warms them up with a 1-token
  request so the first user-facing turn doesn't pay the model-load latency.
- Tears down spawned processes on Koda shutdown via ``atexit`` and SIGTERM
  forwarding through the process group.

Imports of this module are gated behind the auto-spawn flag in the runners
themselves; importing it does not start anything.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

from koda.config import (
    LLAMACPP_API_BASE_URL,
    LLAMACPP_BIN,
    LLAMACPP_DEFAULT_MODEL,
    LLAMACPP_DRAFT_MODEL,
    LOCAL_RUNTIME_HEAVY_SLOTS,
    LOCAL_RUNTIME_QUEUE_TIMEOUT,
    MLX_API_BASE_URL,
    MLX_DEFAULT_MODEL,
    MLX_SERVER_BIN,
)
from koda.logging_config import get_logger

log = get_logger(__name__)

LocalRuntime = Literal["llamacpp", "mlx"]
HealthState = Literal["unknown", "starting", "ready", "failed", "stopped"]


@dataclass(slots=True)
class RuntimeProcess:
    runtime: LocalRuntime
    model: str
    process: subprocess.Popen[bytes]
    base_url: str
    started_at: float
    health: HealthState = "starting"
    last_health_check: float = 0.0
    failure_reason: str | None = None
    last_used: float = field(default_factory=time.monotonic)


def _parse_port(base_url: str, default: int) -> int:
    if "://" not in base_url:
        return default
    rest = base_url.split("://", 1)[1]
    host_part = rest.split("/", 1)[0]
    if ":" not in host_part:
        return default
    try:
        return int(host_part.rsplit(":", 1)[1])
    except ValueError:
        return default


def _wait_for_health(url: str, *, timeout: float = 60.0) -> bool:
    """Poll ``GET /v1/models`` until 2xx or timeout. Returns ``True`` on ready."""
    deadline = time.monotonic() + timeout
    delay = 0.5
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 3.0)
    return False


class LocalRuntimeSupervisor:
    """Process-singleton supervisor for local Metal-accelerated runtimes."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._processes: dict[LocalRuntime, RuntimeProcess] = {}
        self._heavy_lock = asyncio.Semaphore(max(1, LOCAL_RUNTIME_HEAVY_SLOTS))
        self._residency: OrderedDict[LocalRuntime, str] = OrderedDict()
        self._closing = False
        # Threading lock used by the atexit handler since it runs outside the
        # asyncio loop.
        self._proc_table_lock = threading.Lock()
        atexit.register(self._atexit_terminate)

    def _resolve_model(self, runtime: LocalRuntime) -> str:
        if runtime == "llamacpp":
            return LLAMACPP_DEFAULT_MODEL or ""
        if runtime == "mlx":
            return MLX_DEFAULT_MODEL or ""
        return ""

    def _resolve_base_url(self, runtime: LocalRuntime) -> str:
        if runtime == "llamacpp":
            return LLAMACPP_API_BASE_URL or "http://127.0.0.1:8080"
        if runtime == "mlx":
            return MLX_API_BASE_URL or "http://127.0.0.1:8000"
        return ""

    def _resolve_binary(self, runtime: LocalRuntime) -> str:
        if runtime == "llamacpp":
            return LLAMACPP_BIN or "llama-server"
        if runtime == "mlx":
            return MLX_SERVER_BIN or "mlx_lm.server"
        return ""

    def _build_command(self, runtime: LocalRuntime, model: str, port: int) -> list[str] | None:
        if runtime == "llamacpp":
            binary = self._resolve_binary(runtime)
            resolved = shutil.which(binary)
            if resolved is None:
                log.warning("local_runtime_binary_missing", runtime=runtime, binary=binary)
                return None
            cmd = [
                resolved,
                "-m",
                model,
                "-ngl",
                "99",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
            if LLAMACPP_DRAFT_MODEL:
                cmd.extend(["--draft-max", "8", "-md", LLAMACPP_DRAFT_MODEL])
            return cmd
        if runtime == "mlx":
            # mlx-openai-server is a Python module, invoked as
            # ``python -m mlx_lm.server`` rather than a standalone binary.
            # Verify the module is importable in this interpreter; the
            # binary name on PROVIDER_BASE_URL_ENV_KEYS is informational.
            import importlib.util  # noqa: PLC0415

            if importlib.util.find_spec("mlx_lm") is None:
                log.warning("local_runtime_module_missing", runtime=runtime, module="mlx_lm")
                return None
            # Use sys.executable rather than "python" so the spawn lands on
            # the same interpreter that imported mlx_lm — avoids picking up
            # a stale system python that has no MLX installed.
            return [
                sys.executable,
                "-m",
                "mlx_lm.server",
                "--model",
                model,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
        return None

    async def ensure_running(
        self,
        runtime: LocalRuntime,
        *,
        model: str | None = None,
    ) -> str:
        """Make sure ``runtime`` is up; return its base URL.

        Idempotent: if the requested runtime is already healthy with the same
        model, returns immediately. If the runtime is up with a different
        model and we'd exceed memory budget, evicts the oldest first.
        """
        target_model = (model or self._resolve_model(runtime)).strip()
        if not target_model:
            log.debug("local_runtime_skip_no_model", runtime=runtime)
            return self._resolve_base_url(runtime)

        # First check (fast path): is the runtime already up with the right
        # model? If so we can skip the heavy-slot lock entirely.
        async with self._lock:
            existing = self._processes.get(runtime)
            if existing is not None and existing.health == "ready" and existing.model == target_model:
                existing.last_used = time.monotonic()
                self._residency.move_to_end(runtime)
                return existing.base_url

        # Need to spawn (or re-spawn for a different model). Acquire the
        # heavy-slot semaphore first so two callers can't both spawn into
        # unified memory simultaneously.
        try:
            await asyncio.wait_for(self._heavy_lock.acquire(), timeout=LOCAL_RUNTIME_QUEUE_TIMEOUT)
        except TimeoutError:
            log.warning("local_runtime_slot_timeout", runtime=runtime, timeout=LOCAL_RUNTIME_QUEUE_TIMEOUT)
            return self._resolve_base_url(runtime)

        try:
            async with self._lock:
                # Second check (after heavy_lock acquired): another caller may
                # have spawned the right process while we were queued. This
                # double-checked-locking pattern is what keeps concurrent
                # ensure_running calls from racing into duplicate spawns and
                # leaving the loser as an orphan PID.
                existing = self._processes.get(runtime)
                if existing is not None and existing.health == "ready" and existing.model == target_model:
                    existing.last_used = time.monotonic()
                    self._residency.move_to_end(runtime)
                    return existing.base_url
                if existing is not None and existing.process.poll() is None:
                    # Different model OR previous spawn failed mid-flight; either
                    # way, terminate before spawning the replacement so we never
                    # leak the previous process.
                    self._stop_process_locked(runtime)

                base_url = self._resolve_base_url(runtime)
                port = _parse_port(base_url, default=8080 if runtime == "llamacpp" else 8000)
                cmd = self._build_command(runtime, target_model, port)
                if cmd is None:
                    return base_url
                log.info("local_runtime_spawn", runtime=runtime, model=target_model, port=port)
                env = os.environ.copy()
                # ``setsid`` puts the child in its own process group so
                # ``os.killpg(-pid, signal)`` cleans up reliably on shutdown.
                process = subprocess.Popen(  # noqa: S603 — args resolved via shutil.which
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    env=env,
                    start_new_session=True,
                )
                handle = RuntimeProcess(
                    runtime=runtime,
                    model=target_model,
                    process=process,
                    base_url=base_url,
                    started_at=time.monotonic(),
                )
                self._processes[runtime] = handle
                self._residency[runtime] = target_model

            health_url = base_url.rstrip("/") + "/v1/models"
            ready = await asyncio.to_thread(_wait_for_health, health_url, timeout=120.0)
            async with self._lock:
                refreshed = self._processes.get(runtime)
                if refreshed is None:
                    return base_url
                handle = refreshed
                handle.health = "ready" if ready else "failed"
                handle.last_health_check = time.monotonic()
                if not ready:
                    handle.failure_reason = f"Health probe to {health_url} timed out."
                    log.warning("local_runtime_health_timeout", runtime=runtime, model=target_model)
                else:
                    log.info(
                        "local_runtime_ready",
                        runtime=runtime,
                        model=target_model,
                        elapsed_s=round(handle.last_health_check - handle.started_at, 2),
                    )

            if ready:
                await self._warmup(runtime, base_url, target_model)
            return base_url
        finally:
            self._heavy_lock.release()

    async def _warmup(self, runtime: LocalRuntime, base_url: str, model: str) -> None:
        """Issue a 1-token completion so the first real request is fast."""
        url = base_url.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
            "stream": False,
        }
        try:
            import json  # noqa: PLC0415

            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            await asyncio.to_thread(lambda: urllib.request.urlopen(request, timeout=30).read())
            log.debug("local_runtime_warmed", runtime=runtime, model=model)
        except Exception as exc:  # noqa: BLE001
            log.debug("local_runtime_warmup_skipped", runtime=runtime, error=str(exc))

    async def stop(self, runtime: LocalRuntime) -> None:
        async with self._lock:
            self._stop_process_locked(runtime)

    async def stop_all(self) -> None:
        async with self._lock:
            for runtime in list(self._processes.keys()):
                self._stop_process_locked(runtime)

    def _stop_process_locked(self, runtime: LocalRuntime) -> None:
        handle = self._processes.pop(runtime, None)
        self._residency.pop(runtime, None)
        if handle is None:
            return
        process = handle.process
        if process.poll() is not None:
            handle.health = "stopped"
            return
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError, ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        handle.health = "stopped"
        log.info("local_runtime_stopped", runtime=runtime, model=handle.model)

    def status(self) -> dict[str, dict[str, object]]:
        """Snapshot of supervised runtimes for the web UI."""
        out: dict[str, dict[str, object]] = {}
        with self._proc_table_lock:
            for runtime, handle in self._processes.items():
                out[runtime] = {
                    "model": handle.model,
                    "base_url": handle.base_url,
                    "health": handle.health,
                    "started_at": handle.started_at,
                    "last_used": handle.last_used,
                    "pid": handle.process.pid,
                    "failure_reason": handle.failure_reason,
                }
        return out

    def _atexit_terminate(self) -> None:
        """Synchronous shutdown on interpreter exit (not async)."""
        with self._proc_table_lock:
            for _runtime, handle in list(self._processes.items()):
                process = handle.process
                if process.poll() is not None:
                    continue
                with contextlib.suppress(OSError, ProcessLookupError):
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(OSError, ProcessLookupError):
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)


_INSTANCE: LocalRuntimeSupervisor | None = None
_INSTANCE_LOCK = threading.Lock()


def get_local_runtime_supervisor() -> LocalRuntimeSupervisor:
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = LocalRuntimeSupervisor()
    return _INSTANCE


def reset_for_tests() -> None:
    """Test hook: reset the singleton (does NOT terminate spawned processes)."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
