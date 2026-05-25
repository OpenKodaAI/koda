"""Tests for the MCP process isolation layer."""

from __future__ import annotations

import platform
from unittest.mock import patch

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
    assert env == {"K": "v"}


def test_native_strips_blocked_env_only_when_explicitly_set_via_other_strategies():
    # NativeIsolation does not scrub — the env is preserved as-is. The scrub
    # only kicks in for sandboxed strategies. This test pins behaviour so we
    # don't accidentally start scrubbing env in native mode and break devs.
    strategy = NativeIsolation()
    _, env = strategy.wrap(["sh"], {"LD_PRELOAD": "/tmp/x.so"}, IsolationConstraints())
    assert env == {"LD_PRELOAD": "/tmp/x.so"}


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


def test_docker_wrap_uses_env_file_and_cap_drops():
    with patch("koda.services.mcp_isolation.shutil.which", return_value="/usr/bin/docker"):
        strategy = DockerIsolation()
        argv, env = strategy.wrap(["npx", "pkg"], {"TOKEN": "abc"}, IsolationConstraints())
        joined = " ".join(argv)
        assert "--cap-drop=ALL" in joined
        assert "--read-only" in joined
        assert "--network bridge" in joined
        # Env is NOT passed via argv; it goes through --env-file.
        assert env == {}
        assert "--env-file" in argv


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
