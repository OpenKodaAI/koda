"""Tests for the custom MCP server registry: validation + Claude Desktop import."""

from __future__ import annotations

import pytest

from koda.integrations.custom_mcp_registry import (
    CustomServerPayload,
    ValidationError,
    _payload_from_claude_desktop,
    compute_validation_signature,
    normalize_server_key,
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


def test_validate_signature_when_secret_provided():
    payload = _payload()
    secret = b"test-secret"
    validate_payload(payload, secret_key=secret)
    assert payload.metadata["validation_signature"]
    assert payload.metadata["validation_signature"] == compute_validation_signature(payload, secret)


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
