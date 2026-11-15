"""Tests for the custom MCP server registry: validation + Claude Desktop import."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from koda.integrations.custom_mcp_registry import (
    CustomServerPayload,
    ValidationError,
    _payload_from_claude_desktop,
    normalize_server_key,
    upsert_custom_server,
    validate_payload,
)


def _payload(**overrides) -> CustomServerPayload:
    base = {
        "server_key": "custom_test",
        "display_name": "Test Server",
        "transport_type": "stdio",
        "command": ["npx", "-y", "@org/mcp"],
    }
    base.update(overrides)
    return CustomServerPayload(**base)


def test_normalize_server_key_prefixes():
    assert normalize_server_key("my-server") == "custom_my-server"
    assert normalize_server_key("custom_already") == "custom_already"
    assert normalize_server_key("UPPER Case") == "custom_upper-case"


def test_normalize_server_key_rejects_empty():
    with pytest.raises(ValidationError):
        normalize_server_key("")


def test_validate_accepts_valid_stdio_payload():
    validate_payload(_payload())


def test_validate_rejects_command_outside_allowlist():
    with pytest.raises(ValidationError) as excinfo:
        validate_payload(_payload(command=["rm", "-rf", "/"]))
    assert "allowlist" in str(excinfo.value)


def test_validate_rejects_non_string_command_arg():
    with pytest.raises(ValidationError) as excinfo:
        validate_payload(_payload(command=["npx", {"bad": "shape"}]))
    assert "command[1] must be a string" in str(excinfo.value)


def test_validate_rejects_filesystem_path_command():
    with pytest.raises(ValidationError):
        validate_payload(_payload(command=["/usr/bin/sh"]))


def test_validate_rejects_long_args():
    with pytest.raises(ValidationError):
        validate_payload(_payload(command=["npx", "x" * 600]))


def test_validate_rejects_null_byte_in_args():
    with pytest.raises(ValidationError):
        validate_payload(_payload(command=["npx", "ok\x00bad"]))


def test_validate_rejects_forbidden_env_name():
    payload = _payload(env_schema=[{"key": "LD_PRELOAD", "label": "preload", "required": False}])
    with pytest.raises(ValidationError) as excinfo:
        validate_payload(payload)
    assert "forbidden" in str(excinfo.value).lower()


def test_validate_rejects_koda_reserved_env_name():
    payload = _payload(env_schema=[{"key": "KODA_INTERNAL", "label": "x", "required": False}])
    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_validate_rejects_non_https_url():
    payload = _payload(
        transport_type="http_sse",
        command=[],
        url="http://example.com/sse",
    )
    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_validate_accepts_localhost_http():
    payload = _payload(
        transport_type="http_sse",
        command=[],
        url="http://localhost:3000/sse",
    )
    validate_payload(payload)


def test_validate_rejects_header_outside_allowlist():
    payload = _payload(
        transport_type="http_sse",
        command=[],
        url="https://mcp.example.com/sse",
        headers_schema=[{"key": "Cookie"}],
    )
    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_claude_desktop_parser_handles_stdio_entry():
    payload = _payload_from_claude_desktop(
        "my-mcp",
        {
            "command": "npx",
            "args": ["-y", "@my-org/mcp"],
            "env": {"MY_TOKEN": "", "OTHER": ""},
        },
    )
    assert payload.server_key == "custom_my-mcp"
    assert payload.transport_type == "stdio"
    assert payload.command[:2] == ["npx", "-y"]
    env_keys = [field["key"] for field in payload.env_schema]
    assert "MY_TOKEN" in env_keys
    assert "OTHER" in env_keys


def test_claude_desktop_parser_handles_http_entry():
    payload = _payload_from_claude_desktop(
        "linear",
        {"url": "https://mcp.linear.app/mcp", "transport": "http_sse"},
    )
    assert payload.transport_type == "http_sse"
    assert payload.url == "https://mcp.linear.app/mcp"
    assert payload.command == []


def test_claude_desktop_parser_infers_http_from_url():
    payload = _payload_from_claude_desktop(
        "remote",
        {"url": "https://mcp.example.com/sse"},
    )
    # No transport key → fallback inference picks http_sse for url-only specs.
    assert payload.transport_type == "http_sse"


# D-301: stored isolation constraints are validated on upsert


@pytest.fixture
def koda_secret_paths(tmp_path, monkeypatch):
    import koda.config as config
    import koda.control_plane.settings as settings

    paths = {
        "state": tmp_path / "state",
        "key": tmp_path / "keys" / ".master.key",
        "previous_key": tmp_path / "keys" / ".master-previous.key",
    }
    monkeypatch.setattr(config, "STATE_ROOT_DIR", paths["state"])
    monkeypatch.setattr(settings, "CONTROL_PLANE_MASTER_KEY_FILE", paths["key"])
    monkeypatch.setattr(settings, "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE", paths["previous_key"])
    # No agent's published settings name a state root of their own.
    monkeypatch.setattr(
        "koda.control_plane.manager.get_control_plane_manager",
        lambda: SimpleNamespace(published_state_roots=lambda: ()),
    )
    return paths


def _mount_payload(host: str, *, read_only: bool) -> CustomServerPayload:
    return _payload(isolation_constraints={"mounts": [{"host": host, "container": "/data", "read_only": read_only}]})


@pytest.mark.parametrize(
    ("host", "read_only"),
    [
        ("{state}", False),
        ("{state}", True),
        ("{state}/control_plane", False),
        ("{tmp}", False),  # a parent of the state directory exposes it too
        ("{key}", False),
        ("{key}", True),
        ("{previous_key}", False),
        ("/etc", False),
        ("/etc/ssl", False),
        ("/var/run/docker.sock", False),
        ("/run", False),  # a parent of the Docker socket
        ("~/.ssh", False),
        # The kernel, bwrap and docker read a doubled leading slash as one.
        ("//etc", False),
        ("//var/run/docker.sock", False),
        ("/{state}", False),
    ],
)
def test_upsert_refuses_mounts_of_sensitive_host_paths(host, read_only, koda_secret_paths, tmp_path):
    host = host.format(
        state=koda_secret_paths["state"],
        key=koda_secret_paths["key"],
        previous_key=koda_secret_paths["previous_key"],
        tmp=tmp_path,
    )
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="mount") as excinfo,
    ):
        upsert_custom_server(_mount_payload(host, read_only=read_only))
    assert host in str(excinfo.value)
    execute.assert_not_called()


@pytest.mark.parametrize("target", ["/etc", "/var/run/docker.sock", "{state}", "{key}"])
def test_upsert_refuses_symlinks_to_sensitive_host_paths(target, koda_secret_paths, tmp_path):
    target = target.format(state=koda_secret_paths["state"], key=koda_secret_paths["key"])
    link = tmp_path / "innocent"
    link.symlink_to(target)
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="mount"),
    ):
        upsert_custom_server(_mount_payload(str(link), read_only=False))
    execute.assert_not_called()


@pytest.mark.parametrize("read_only", [True, False])
def test_upsert_accepts_mounts_of_ordinary_host_paths(read_only, koda_secret_paths, tmp_path):
    validate_payload(_mount_payload(str(tmp_path / "data"), read_only=read_only))


@pytest.mark.parametrize("network_mode", ["bridge", "host", "off"])
def test_upsert_refuses_unknown_network_mode(network_mode):
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="network_mode"),
    ):
        upsert_custom_server(_payload(isolation_constraints={"network_mode": network_mode}))
    execute.assert_not_called()


@pytest.mark.parametrize("network_mode", ["none", "egress_allowlist", "any"])
def test_upsert_accepts_known_network_modes(network_mode):
    validate_payload(_payload(isolation_constraints={"network_mode": network_mode}))


# D-317: the control plane and the worker resolve a relative path differently


@pytest.mark.parametrize("host", ["data", "./data", "../srv/data", "srv//data", "~nosuchuser-d317/data"])
def test_upsert_refuses_relative_mount_hosts(host, koda_secret_paths):
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="absolute") as excinfo,
    ):
        upsert_custom_server(_mount_payload(host, read_only=True))
    assert host in str(excinfo.value)
    execute.assert_not_called()


def test_upsert_accepts_a_home_relative_mount_host(koda_secret_paths, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    validate_payload(_mount_payload("~/data", read_only=True))


# D-318: a worker's per-agent state root is protected too


@pytest.mark.parametrize("suffix", ["", "/control_plane"])
def test_upsert_refuses_mounts_of_a_per_agent_state_root(suffix, koda_secret_paths, monkeypatch, tmp_path):
    agent_state = tmp_path / "agent-a-state"
    monkeypatch.setenv("AGENT_A_STATE_ROOT_DIR", str(agent_state))
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="mount"),
    ):
        upsert_custom_server(_mount_payload(f"{agent_state}{suffix}", read_only=True))
    execute.assert_not_called()


# D-318: the state root an agent's stored settings give its worker is protected too


def _agents_publish(monkeypatch, snapshots: list[dict]) -> None:
    """The real manager lookup, over these published snapshots."""
    import koda.control_plane.manager as manager_mod

    rows = [{"snapshot_json": json.dumps(snapshot)} for snapshot in snapshots]
    monkeypatch.setattr(manager_mod, "fetch_all", lambda query, params=(): rows)
    manager = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    monkeypatch.setattr(manager_mod, "get_control_plane_manager", lambda: manager)


@pytest.mark.parametrize("key", ["STATE_ROOT_DIR", "AGENT_A_STATE_ROOT_DIR"])
@pytest.mark.parametrize("suffix", ["", "/control_plane"])
def test_upsert_refuses_mounts_of_a_state_root_from_an_agents_settings(
    key, suffix, koda_secret_paths, monkeypatch, tmp_path
):
    """The control plane's environment names no STATE_ROOT_DIR; agent A's stored settings give its worker one."""
    monkeypatch.delenv("STATE_ROOT_DIR", raising=False)
    agent_state = tmp_path / "agent-a-state"
    env = {key: str(agent_state), "LOG_LEVEL": "INFO"}
    _agents_publish(monkeypatch, [{"env": env, "process_env": env}, {"env": {"LOG_LEVEL": "DEBUG"}}])
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="sensitive host path"),
    ):
        upsert_custom_server(_mount_payload(f"{agent_state}{suffix}", read_only=True))
    execute.assert_not_called()
    validate_payload(_mount_payload(str(tmp_path / "data"), read_only=True))


def test_upsert_refuses_mounts_when_the_agents_state_roots_cannot_be_read(koda_secret_paths, monkeypatch, tmp_path):
    def unreadable() -> tuple[str, ...]:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "koda.control_plane.manager.get_control_plane_manager",
        lambda: SimpleNamespace(published_state_roots=unreadable),
    )
    with (
        patch("koda.integrations.custom_mcp_registry.execute") as execute,
        pytest.raises(ValidationError, match="state roots.*database unavailable"),
    ):
        upsert_custom_server(_mount_payload(str(tmp_path / "data"), read_only=True))
    execute.assert_not_called()
