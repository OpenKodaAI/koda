"""Tests for the custom MCP server registry: validation + Claude Desktop import."""

from __future__ import annotations

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
