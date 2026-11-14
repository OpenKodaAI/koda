"""Supervisor env-propagation contract.

When the control-plane supervisor spawns an agent worker via
``asyncio.create_subprocess_exec``, the child inherits only an explicitly
whitelisted subset of the parent process env. gRPC sidecar target addresses
(SECURITY/MEMORY/ARTIFACT/RETRIEVAL/RUNTIME_KERNEL) must be in that whitelist
or the child falls back to ``config.py`` defaults that only resolve inside
the supervisor's container — every RPC then fails with ``Connection refused``
and the runtime silently degrades to the minimal-safe-env fallback.

The prior regression: those keys were missing from ``_SYSTEM_ENV_KEYS`` in
``koda/control_plane/supervisor.py``. The fix added all five entries.
"""

from __future__ import annotations

import inspect


def test_supervisor_propagates_grpc_sidecar_targets() -> None:
    """The supervisor's spec-build path must force every gRPC sidecar target
    from the parent env into each worker's spec.environment so the kernel
    spawns workers that can reach the docker-compose-provided sidecars.

    Post runtime-kernel migration the supervisor no longer spawns workers
    itself — it builds an ``AgentWorkerSpec`` and hands it to the kernel
    via ``RuntimeKernelLink.ensure_agent_workers``. The whitelist now lives
    as the module-level ``_SYSTEM_ENV_KEYS`` constant, applied inside
    ``ControlPlaneSupervisor._build_spec``.
    """
    from koda.control_plane import supervisor as supervisor_mod

    system_keys = supervisor_mod._SYSTEM_ENV_KEYS
    build_spec_src = inspect.getsource(supervisor_mod.ControlPlaneSupervisor._build_spec)
    for env_key in (
        "SECURITY_GRPC_TARGET",
        "MEMORY_GRPC_TARGET",
        "ARTIFACT_GRPC_TARGET",
        "RETRIEVAL_GRPC_TARGET",
        "RUNTIME_KERNEL_GRPC_TARGET",
        "PLAYWRIGHT_BROWSERS_PATH",
    ):
        assert env_key in system_keys, (
            f"{env_key} must be in supervisor._SYSTEM_ENV_KEYS so spawned workers "
            "inherit the docker-compose-provided sidecar address. Without it the "
            "child falls back to 127.0.0.1:<port> and every RPC fails."
        )
    # The keys must also actually be applied — guard against a future
    # refactor that drops the parent-env override loop and reduces the
    # constant to a static label.
    assert "_SYSTEM_ENV_KEYS" in build_spec_src
    assert "os.environ.get" in build_spec_src


def test_security_guard_fallback_warning_is_gated_by_target_env(monkeypatch) -> None:
    """In dev where the Rust security sidecar isn't deployed, falling back to
    the minimal-safe-env is the nominal path — don't spam WARNING on every
    LLM turn. Only warn when SECURITY_GRPC_TARGET is explicitly configured
    (operator expected the sidecar to be reachable).
    """
    import logging

    from koda.services import provider_env

    monkeypatch.delenv("SECURITY_GRPC_TARGET", raising=False)

    class _BoomClient:
        def sanitize_environment(self, **_kwargs: object) -> dict[str, str]:
            raise RuntimeError("security_guard unreachable")

    monkeypatch.setattr(provider_env, "get_security_guard_client", lambda: _BoomClient())

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger("koda.services.provider_env")
    logger.addHandler(handler)
    try:
        result = provider_env._sanitize_env(
            {"PATH": "/usr/bin"},
            allowed_provider_keys=frozenset(),
            env_overrides={},
            safe_env_keys=frozenset({"PATH"}),
        )
    finally:
        logger.removeHandler(handler)

    assert result == {"PATH": "/usr/bin"}
    warnings = [record for record in records if record.levelno >= logging.WARNING]
    assert not warnings, (
        "security_guard fallback should log at DEBUG (not WARNING) when the "
        "sidecar is intentionally unconfigured in dev/compose-lite stacks."
    )


def test_security_guard_fallback_warns_when_target_set(monkeypatch) -> None:
    """Conversely, when SECURITY_GRPC_TARGET IS configured, the operator
    expected the sidecar to be reachable — warn loudly on unexpected failure.
    """
    import logging

    from koda.services import provider_env

    monkeypatch.setenv("SECURITY_GRPC_TARGET", "security:50065")

    class _BoomClient:
        def sanitize_environment(self, **_kwargs: object) -> dict[str, str]:
            raise RuntimeError("security_guard unreachable")

    monkeypatch.setattr(provider_env, "get_security_guard_client", lambda: _BoomClient())

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger("koda.services.provider_env")
    logger.addHandler(handler)
    try:
        provider_env._sanitize_env(
            {"PATH": "/usr/bin"},
            allowed_provider_keys=frozenset(),
            env_overrides={},
            safe_env_keys=frozenset({"PATH"}),
        )
    finally:
        logger.removeHandler(handler)

    warnings = [record for record in records if record.levelno >= logging.WARNING]
    assert warnings, "expected WARNING when SECURITY_GRPC_TARGET is set but unreachable"
    assert any("security_guard_rpc_unavailable" in record.getMessage() for record in warnings)


_WORKER_CONFIG_SCRIPT = """
import json, os, sys
os.environ.clear()
os.environ.update(json.loads(sys.argv[1]))
import koda.config as config
print(json.dumps({
    "SECURITY_GRPC_TARGET": config.SECURITY_GRPC_TARGET,
    "POSTGRES_URL": config.POSTGRES_URL,
    "STATE_ROOT_DIR": str(config.STATE_ROOT_DIR),
    "RUNTIME_EPHEMERAL_ROOT": str(config.RUNTIME_EPHEMERAL_ROOT),
    "INTER_AGENT_ENABLED": config.INTER_AGENT_ENABLED,
}))
"""


def test_the_hosts_infrastructure_settings_win_over_a_snapshots_agent_scoped_keys(tmp_path) -> None:
    """A stale snapshot sets an infrastructure key; the worker koda.config must read the host's value.

    The manager scopes every snapshot key as ``KEY`` and ``<AGENT_ID>_KEY``, and koda.config
    reads ``<AGENT_ID>_KEY`` first, so forcing only the plain ``KEY`` from the supervisor's
    environment would leave the snapshot's value in force. The worker env is built by the
    real steps (the manager's scoping and ``ControlPlaneSupervisor._build_spec``) and read
    by koda.config in a fresh process, with the install's ``.env`` left out.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from koda.control_plane import supervisor as supervisor_mod
    from koda.control_plane.manager import ControlPlaneManager, RuntimeSnapshot

    agent_id = "AGENT_A"
    stale = {
        "SECURITY_GRPC_TARGET": "stale-security:50065",
        "POSTGRES_URL": "postgresql://stale@stale-db/koda",
        "STATE_ROOT_DIR": str(tmp_path / "stale-state"),
        "RUNTIME_EPHEMERAL_ROOT": str(tmp_path / "stale-runtime"),
        "INTER_AGENT_ENABLED": "true",
    }
    host = {
        "SECURITY_GRPC_TARGET": "security:50065",
        "POSTGRES_URL": "postgresql://koda@postgres/koda",
        "STATE_ROOT_DIR": str(tmp_path / "state"),
        "RUNTIME_EPHEMERAL_ROOT": str(tmp_path / "runtime"),
        "INTER_AGENT_ENABLED": "false",
    }
    assert set(host) <= supervisor_mod._SYSTEM_ENV_KEYS
    runtime = RuntimeSnapshot(
        agent_id=agent_id,
        version=1,
        runtime_dir=Path(tmp_path),
        process_env=ControlPlaneManager._scoped_env(MagicMock(), agent_id, stale),
        connection_refs=[],
        health_url="http://127.0.0.1:9001/health",
        runtime_base_url="http://127.0.0.1:9001",
        state_backend="postgres",
        db_file_name="",
    )
    supervisor = SimpleNamespace(
        _manager=MagicMock(**{"get_provider_connection.return_value": {}}),
        _link=SimpleNamespace(target="unix:///tmp/koda-test.sock"),
        _workspace_id_for_agent=lambda _agent_id: "default",
    )
    with patch.dict(os.environ, host):
        spec = supervisor_mod.ControlPlaneSupervisor._build_spec(supervisor, agent_id, 1, runtime)
    worker_env = {**spec.environment, "PYTHON_DOTENV_DISABLED": "true", "KODA_SKIP_SECURITY_GUARD_SERVICE": "1"}

    completed = subprocess.run(
        [sys.executable, "-c", _WORKER_CONFIG_SCRIPT, json.dumps(worker_env)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=120,
    )
    worker = json.loads(completed.stdout.strip().splitlines()[-1])

    assert worker == {**host, "INTER_AGENT_ENABLED": False}
