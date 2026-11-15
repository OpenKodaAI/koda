"""Tests for the MCP process isolation layer."""

from __future__ import annotations

import platform
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.mcp_client import McpToolDefinition
from koda.services.mcp_isolation import (
    BwrapIsolation,
    DockerIsolation,
    IsolationConstraints,
    Mount,
    NativeIsolation,
    SandboxExecIsolation,
    isolation_runtime_summary,
    select_isolation_strategy,
)


def test_native_isolation_passes_through():
    strategy = NativeIsolation()
    cmd, env = strategy.wrap(["npx", "-y", "pkg"], {"K": "v"}, IsolationConstraints())
    assert cmd == ["npx", "-y", "pkg"]
    assert env["K"] == "v"


def test_native_strips_blocked_env_only_when_explicitly_set_via_other_strategies():
    # NativeIsolation does not scrub — the env is preserved as-is. The scrub
    # only kicks in for sandboxed strategies. This test pins behaviour so we
    # don't accidentally start scrubbing env in native mode and break devs.
    strategy = NativeIsolation()
    _, env = strategy.wrap(["sh"], {"LD_PRELOAD": "/tmp/x.so"}, IsolationConstraints())
    assert env["LD_PRELOAD"] == "/tmp/x.so"


def test_select_isolation_uses_env_override_when_available():
    # Force Linux platform + bwrap available, then ask for sandbox-exec
    # explicitly via override → must fall back since sandbox-exec doesn't
    # exist on Linux.
    with (
        patch("koda.services.mcp_isolation.platform.system", return_value="Linux"),
        patch("koda.services.mcp_isolation.shutil.which", return_value=None),
    ):
        strategy = select_isolation_strategy(env_override="sandbox-exec")
        assert strategy.kind == "native"


def test_select_isolation_auto_detects_per_platform():
    # On macOS, sandbox-exec is the auto choice.
    with (
        patch("koda.services.mcp_isolation.platform.system", return_value="Darwin"),
        patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/sandbox-exec"),
    ):
        strategy = select_isolation_strategy()
        assert strategy.kind == "sandbox-exec"


def test_bwrap_wrap_emits_unshare_net_for_network_none():
    if platform.system() != "Linux":
        # We mock the platform check below; the unit test should still run on
        # any host so long as we patch the binary lookup.
        pass
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/bwrap"):
        strategy = BwrapIsolation()
        constraints = IsolationConstraints(network_mode="none")
        argv, _ = strategy.wrap(["npx", "pkg"], {"X": "y"}, constraints)
        assert "--unshare-net" in argv
        assert argv[-2:] == ["npx", "pkg"]


def test_bwrap_wrap_handles_mounts():
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/bwrap"):
        strategy = BwrapIsolation()
        constraints = IsolationConstraints(mounts=(Mount(host="/tmp/data", container="/data", read_only=False),))
        argv, _ = strategy.wrap(["bin"], {}, constraints)
        joined = " ".join(argv)
        assert "--bind /tmp/data /data" in joined


def test_sandbox_exec_profile_includes_mounts_and_network_toggle():
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/sandbox-exec"):
        strategy = SandboxExecIsolation()
        constraints = IsolationConstraints(
            network_mode="none",
            mounts=(Mount(host="/opt/test/vault", container="/vault"),),
        )
        argv, _ = strategy.wrap(["bin"], {}, constraints)
        # argv structure: [sandbox-exec, -p, profile, bin]
        assert argv[0] == "/usr/bin/sandbox-exec"
        assert argv[1] == "-p"
        profile = argv[2]
        assert "/opt/test/vault" in profile
        assert "(allow network*)" not in profile  # network=none must NOT enable network
        # cmd is appended at the end
        assert argv[-1] == "bin"


def test_docker_wrap_passes_env_by_name_and_cap_drops(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("DOCKER_CONFIG", "/srv/docker-config")
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/docker"):
        strategy = DockerIsolation()
        argv, env = strategy.wrap(["npx", "pkg"], {"TOKEN": "abc", "LD_PRELOAD": "/tmp/x.so"}, IsolationConstraints())
        joined = " ".join(argv)
        assert "--cap-drop=ALL" in joined
        assert "--read-only" in joined
        assert "--network bridge" in joined
        # Env goes by name only: the value stays out of argv and no env file is written.
        assert "-e TOKEN" in joined
        assert "abc" not in joined
        assert "--env-file" not in argv
        assert "LD_PRELOAD" not in joined
        assert list(tmp_path.iterdir()) == []
        # The docker CLI reads each named value from its own environment, which keeps the inherited one.
        assert env["TOKEN"] == "abc"
        assert env["DOCKER_CONFIG"] == "/srv/docker-config"
        assert "LD_PRELOAD" not in env


@pytest.mark.parametrize("name", ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "HOME", "PATH"])
def test_docker_wrap_refuses_env_names_the_docker_cli_reads(name):
    # ``-e NAME`` reads the value from the docker CLI's own environment, so these
    # names would reconfigure the CLI (daemon, context, config, credential helpers)
    # instead of reaching only the container.
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/docker"):
        strategy = DockerIsolation()
        with pytest.raises(RuntimeError, match=name) as excinfo:
            strategy.wrap(
                ["mcp-docker"],
                {name: "tcp://remote:2375", "TOKEN": "abc"},
                IsolationConstraints(network_mode="none"),
            )
    assert "tcp://remote:2375" not in str(excinfo.value)
    assert "abc" not in str(excinfo.value)


def test_blocked_env_is_scrubbed_in_isolated_strategies():
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/bwrap"):
        strategy = BwrapIsolation()
        _, env = strategy.wrap(["npx"], {"LD_PRELOAD": "/tmp/x.so", "OK": "v"}, IsolationConstraints())
        assert "LD_PRELOAD" not in env
        assert env.get("OK") == "v"


def test_isolation_runtime_summary_returns_strategies():
    summary = isolation_runtime_summary()
    assert "platform" in summary
    assert "active_default" in summary
    kinds = {entry["kind"] for entry in summary["strategies"]}
    assert {"bwrap", "sandbox-exec", "docker", "native"} <= kinds


# Stored isolation settings reach the spawned command (fake process runner)


class _FakeStdioTransport:
    """Records the argv and env the stdio transport would exec."""

    spawned: list[dict[str, Any]] = []

    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        _FakeStdioTransport.spawned.append({"argv": [command, *(args or [])], "env": env})

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _fake_session() -> MagicMock:
    session = MagicMock()
    session.initialize = AsyncMock(return_value={})
    session.list_tools = AsyncMock(return_value=[McpToolDefinition(name="read", description="Read")])
    session.list_resources = AsyncMock(return_value=[])
    session.list_prompts = AsyncMock(return_value=[])
    return session


def _which(name: str) -> str:
    return f"/usr/bin/{name}"


@pytest.mark.asyncio
async def test_bootstrap_spawns_the_stored_isolation_profile_and_constraints(monkeypatch, tmp_path):
    from koda.services import mcp_bootstrap
    from koda.services.mcp_manager import McpServerManager

    monkeypatch.delenv("KODA_MCP_ISOLATION", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    _FakeStdioTransport.spawned = []
    manager = McpServerManager()
    manager._loops_started = True
    catalog = {
        "server_key": "github",
        "transport_type": "stdio",
        "command": ["mcp-github"],
        "isolation_profile": "docker",
        "isolation_constraints": {
            "network_mode": "none",
            "cpu_quota": 1.5,
            "memory_limit_bytes": 512 * 1024 * 1024,
            "docker_image": "example/mcp:1",
            "mounts": [{"host": "/srv/data", "container": "/data"}],
        },
    }
    with (
        patch("koda.config.MCP_ENABLED", True),
        patch("koda.services.mcp_isolation.shutil.which", side_effect=_which),
        patch("koda.services.mcp_isolation.platform.system", return_value="Linux"),
        patch("koda.services.mcp_manager.StdioTransport", _FakeStdioTransport),
        patch("koda.services.mcp_manager.McpSession", return_value=_fake_session()),
        patch("koda.services.mcp_manager.mcp_server_manager", manager),
        patch.object(mcp_bootstrap, "_load_catalog_entry", return_value=catalog),
        patch.object(
            mcp_bootstrap,
            "_load_agent_mcp_connections",
            return_value=[{"server_key": "github", "enabled": True, "env_values": {"API_TOKEN": "secret"}}],
        ),
        patch("koda.services.mcp_bridge.register_mcp_capabilities_for_agent", return_value={"tools": []}),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=MagicMock()),
    ):
        summary = await mcp_bootstrap.bootstrap_mcp_for_agent("agent-1")

    assert summary["errors"] == []
    assert len(_FakeStdioTransport.spawned) == 1
    argv = _FakeStdioTransport.spawned[0]["argv"]
    joined = " ".join(argv)
    assert argv[:2] == ["/usr/bin/docker", "run"]
    assert "--memory 512m" in joined
    assert "--cpus 1.5" in joined
    assert "--network none" in joined
    assert "--mount type=bind,source=/srv/data,target=/data,readonly" in joined
    assert argv[-2:] == ["example/mcp:1", "mcp-github"]
    assert "-e API_TOKEN" in joined
    assert "secret" not in joined
    assert "--env-file" not in argv
    assert _FakeStdioTransport.spawned[0]["env"]["API_TOKEN"] == "secret"
    assert list(tmp_path.iterdir()) == []
    instance = manager.get_instance("github", "agent-1")
    assert instance is not None
    assert instance.isolation_status == {"isolation": "docker", "egress": "none"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("network_mode", "expected_egress", "warned"),
    [("egress_allowlist", "unrestricted", True), ("none", "none", False)],
)
async def test_bwrap_status_reports_the_egress_it_can_enforce(network_mode, expected_egress, warned, monkeypatch):
    from koda.services.mcp_manager import McpServerInstance

    monkeypatch.delenv("KODA_MCP_ISOLATION", raising=False)
    _FakeStdioTransport.spawned = []
    with (
        patch("koda.services.mcp_isolation.shutil.which", side_effect=_which),
        patch("koda.services.mcp_isolation.platform.system", return_value="Linux"),
        patch("koda.services.mcp_manager.StdioTransport", _FakeStdioTransport),
        patch("koda.services.mcp_manager.McpSession", return_value=_fake_session()),
        patch("koda.services.mcp_manager.logger") as manager_logger,
    ):
        instance = McpServerInstance(
            "github",
            "agent-1",
            "stdio",
            command=["mcp-github"],
            isolation_profile="bwrap",
            isolation_constraints=IsolationConstraints(network_mode=network_mode),
        )
        await instance.start()

    argv = _FakeStdioTransport.spawned[0]["argv"]
    assert argv[0] == "/usr/bin/bwrap"
    assert ("--unshare-net" in argv) is (network_mode == "none")
    assert instance.isolation_status == {"isolation": "bwrap", "egress": expected_egress}
    warnings = [call.args[0] for call in manager_logger.warning.call_args_list]
    assert ("mcp_isolation_egress_allowlist_unenforced" in warnings) is warned


# D-300: a stdio server never inherits Koda's environment


_BASIC_ENV_NAMES = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ")


async def _spawn_env(profile: str, system: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    from koda.services.mcp_manager import McpServerInstance

    _FakeStdioTransport.spawned = []
    with (
        patch("koda.services.mcp_isolation.shutil.which", side_effect=_which),
        patch("koda.services.mcp_isolation.platform.system", return_value=system),
        patch("koda.services.mcp_manager.StdioTransport", _FakeStdioTransport),
        patch("koda.services.mcp_manager.McpSession", return_value=_fake_session()),
    ):
        instance = McpServerInstance(
            "third-party", "agent-1", "stdio", command=["mcp-third-party"], env=env, isolation_profile=profile
        )
        await instance.start()
    assert instance.isolation_status["isolation"] == profile
    assert len(_FakeStdioTransport.spawned) == 1
    return _FakeStdioTransport.spawned[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "system"),
    [("native", "Linux"), ("bwrap", "Linux"), ("sandbox-exec", "Darwin"), ("docker", "Linux")],
)
async def test_server_without_env_does_not_see_koda_secrets(profile, system, monkeypatch):
    monkeypatch.delenv("KODA_MCP_ISOLATION", raising=False)
    monkeypatch.setenv("CONTROL_PLANE_API_TOKEN", "planted-control-plane-token")
    monkeypatch.setenv("KODA_DATABASE_URL", "postgresql://koda:planted-password@db/koda")
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("HOME", "/srv/koda-home")
    monkeypatch.setenv("LANG", "C.UTF-8")

    spawned = await _spawn_env(profile, system)

    joined = " ".join(spawned["argv"])
    assert "planted" not in joined
    if profile == "docker":
        # Regression guard, not part of D-300: docker already gave the container only
        # the names passed with ``-e``, so this case passes before the fix too.
        assert "-e" not in spawned["argv"]
        return
    env = spawned["env"]
    assert env is not None, "env=None makes the server inherit Koda's whole environment"
    assert "CONTROL_PLANE_API_TOKEN" not in env
    assert "KODA_DATABASE_URL" not in env
    assert not any("planted" in value for value in env.values())
    assert set(env) <= set(_BASIC_ENV_NAMES)
    assert (env["PATH"], env["HOME"], env["LANG"]) == ("/usr/local/bin:/usr/bin", "/srv/koda-home", "C.UTF-8")


@pytest.mark.asyncio
@pytest.mark.parametrize(("profile", "system"), [("native", "Linux"), ("bwrap", "Linux"), ("sandbox-exec", "Darwin")])
async def test_server_env_is_the_basics_plus_its_own_env(profile, system, monkeypatch):
    monkeypatch.delenv("KODA_MCP_ISOLATION", raising=False)
    for name in _BASIC_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONTROL_PLANE_API_TOKEN", "planted-control-plane-token")
    monkeypatch.setenv("HOME", "/srv/koda-home")

    with_env = await _spawn_env(profile, system, env={"API_TOKEN": "server-token"})
    without_env = await _spawn_env(profile, system)

    assert with_env["env"] == {"HOME": "/srv/koda-home", "API_TOKEN": "server-token"}
    assert without_env["env"] == {"HOME": "/srv/koda-home"}


@pytest.mark.asyncio
async def test_server_env_stays_explicit_when_koda_has_no_basic_variables(monkeypatch):
    monkeypatch.delenv("KODA_MCP_ISOLATION", raising=False)
    for name in _BASIC_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONTROL_PLANE_API_TOKEN", "planted-control-plane-token")

    spawned = await _spawn_env("native", "Linux")

    # An empty mapping, not None: None would inherit the planted token.
    assert spawned["env"] == {}


# D-301: unknown network modes are refused, not treated as shared network


@pytest.mark.parametrize("network_mode", ["bridge", "host", "off", "None"])
def test_constraints_from_dict_rejects_unknown_network_mode(network_mode):
    with pytest.raises(ValueError, match=f"unknown isolation network_mode '{network_mode}'"):
        IsolationConstraints.from_dict({"network_mode": network_mode})


@pytest.mark.parametrize("network_mode", ["none", "egress_allowlist", "any"])
def test_constraints_from_dict_accepts_known_network_modes(network_mode):
    assert IsolationConstraints.from_dict({"network_mode": network_mode}).network_mode == network_mode


def test_constraints_from_dict_defaults_an_unset_network_mode():
    assert IsolationConstraints.from_dict({"cpu_quota": 1}).network_mode == "egress_allowlist"
    assert IsolationConstraints.from_dict({"network_mode": None}).network_mode == "egress_allowlist"


# D-316: stored constraints saved before validation existed are refused at start


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host", "reason"),
    [
        ("{state}", "sensitive host path"),  # the worker's own state root
        ("{state}/control_plane", "sensitive host path"),
        ("{agent_state}", "sensitive host path"),  # D-318: a per-agent override
        ("relative/data", "absolute"),  # D-317
        ("/etc", "sensitive host path"),
    ],
)
async def test_bootstrap_refuses_a_stored_mount_the_save_check_would_refuse(host, reason, monkeypatch, tmp_path):
    import koda.config as config
    from koda.services import mcp_bootstrap
    from koda.services.mcp_manager import McpServerManager

    monkeypatch.delenv("KODA_MCP_ISOLATION", raising=False)
    monkeypatch.setattr(config, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setenv("AGENT_1_STATE_ROOT_DIR", str(tmp_path / "agent-1-state"))
    host = host.format(state=tmp_path / "state", agent_state=tmp_path / "agent-1-state")
    _FakeStdioTransport.spawned = []
    manager = McpServerManager()
    manager._loops_started = True
    control_plane = MagicMock()
    catalog = {
        "server_key": "legacy",
        "transport_type": "stdio",
        "command": ["mcp-legacy"],
        "isolation_profile": "bwrap",
        "isolation_constraints": {"mounts": [{"host": host, "container": "/data", "read_only": True}]},
    }
    with (
        patch("koda.config.MCP_ENABLED", True),
        patch("koda.services.mcp_isolation.shutil.which", side_effect=_which),
        patch("koda.services.mcp_isolation.platform.system", return_value="Linux"),
        patch("koda.services.mcp_manager.StdioTransport", _FakeStdioTransport),
        patch("koda.services.mcp_manager.McpSession", return_value=_fake_session()),
        patch("koda.services.mcp_manager.mcp_server_manager", manager),
        patch.object(mcp_bootstrap, "_load_catalog_entry", return_value=catalog),
        patch.object(
            mcp_bootstrap,
            "_load_agent_mcp_connections",
            return_value=[{"server_key": "legacy", "enabled": True}],
        ),
        patch("koda.services.mcp_bridge.register_mcp_capabilities_for_agent", return_value={"tools": []}),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=control_plane),
        patch.object(mcp_bootstrap, "log") as bootstrap_log,
    ):
        summary = await mcp_bootstrap.bootstrap_mcp_for_agent("agent-1")

    assert _FakeStdioTransport.spawned == []
    assert manager.get_instance("legacy", "agent-1") is None
    assert summary["started_servers"] == 0
    [error] = summary["errors"]
    assert error.startswith("legacy: refused to start")
    assert reason in error
    refusals = [call for call in bootstrap_log.warning.call_args_list if call.args[0] == "mcp_server_start_refused"]
    assert len(refusals) == 1
    assert refusals[0].kwargs["server_key"] == "legacy"
    assert reason in refusals[0].kwargs["reason"]
    control_plane._record_mcp_runtime_state.assert_called_once()
    status = control_plane._record_mcp_runtime_state.call_args
    assert status.args == ("agent-1", "legacy")
    assert status.kwargs["success"] is False
    assert status.kwargs["error"].startswith("refused to start")
    assert reason in status.kwargs["error"]
