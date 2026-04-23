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
    """The _SYSTEM_ENV_KEYS whitelist must include every gRPC target."""
    from koda.control_plane import supervisor as supervisor_mod

    src = inspect.getsource(supervisor_mod.ControlPlaneSupervisor._start_worker)
    # The whitelist is a local set literal inside _start_worker; assert
    # textually so this test stays stable even if the set is refactored
    # into a module-level constant.
    for env_key in (
        "SECURITY_GRPC_TARGET",
        "MEMORY_GRPC_TARGET",
        "ARTIFACT_GRPC_TARGET",
        "RETRIEVAL_GRPC_TARGET",
        "RUNTIME_KERNEL_GRPC_TARGET",
        "PLAYWRIGHT_BROWSERS_PATH",
    ):
        assert env_key in src, (
            f"{env_key} must be in supervisor._SYSTEM_ENV_KEYS so spawned workers "
            "inherit the docker-compose-provided sidecar address. Without it the "
            "child falls back to 127.0.0.1:<port> and every RPC fails."
        )


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
