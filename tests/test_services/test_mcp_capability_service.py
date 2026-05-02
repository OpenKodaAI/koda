"""Tests for the MCP capability service — discovery, snapshot caching, TTL."""

from __future__ import annotations

import time
from unittest.mock import patch

from koda.services.mcp_capability_service import (
    CapabilitySnapshot,
    _is_stale,
    _resource_schema_hash,
    _uri_hash,
)


def test_capability_snapshot_to_payload_includes_summary():
    snap = CapabilitySnapshot(
        agent_id="A",
        server_key="supabase",
        tools=[{"name": "execute_sql"}],
        resources=[{"uri": "postgres://x"}],
        prompts=[{"name": "summarize"}],
        captured_at="2026-05-01T10:00:00+00:00",
    )
    payload = snap.to_payload()
    summary = payload["summary"]
    assert summary["tool_count"] == 1
    assert summary["resource_count"] == 1
    assert summary["prompt_count"] == 1


def test_is_stale_returns_true_when_error_present():
    snap = CapabilitySnapshot(
        agent_id="A",
        server_key="x",
        captured_at="2026-05-01T10:00:00+00:00",
        ttl_seconds=3600,
        error="boom",
    )
    assert _is_stale(snap) is True


def test_is_stale_returns_false_for_fresh_snapshot():
    # Build an ISO timestamp within the TTL window.
    fresh = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    snap = CapabilitySnapshot(
        agent_id="A",
        server_key="x",
        captured_at=fresh,
        ttl_seconds=3600,
    )
    assert _is_stale(snap) is False


def test_uri_hash_is_stable():
    a = _uri_hash("postgres://server/db")
    b = _uri_hash("postgres://server/db")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_resource_schema_hash_changes_with_mime_type():
    base = {"name": "config.json", "mime_type": "application/json"}
    other = {"name": "config.json", "mime_type": "text/plain"}
    assert _resource_schema_hash(base) != _resource_schema_hash(other)


def test_capability_snapshot_serializes_protocol_version():
    snap = CapabilitySnapshot(
        agent_id="A",
        server_key="x",
        protocol_version="2025-03-26",
        captured_at="2026-05-01T00:00:00+00:00",
    )
    payload = snap.to_payload()
    assert payload["protocol_version"] == "2025-03-26"


@patch("koda.services.mcp_capability_service._load_snapshot")
@patch("koda.services.mcp_capability_service._resolve_runtime_payload")
def test_verify_capabilities_returns_cached_when_fresh(mock_resolve, mock_load):
    """Cache hit must NOT spawn the server."""
    fresh = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    cached = CapabilitySnapshot(
        agent_id="A",
        server_key="x",
        captured_at=fresh,
        ttl_seconds=3600,
        tools=[{"name": "ok"}],
    )
    mock_load.return_value = cached
    mock_resolve.return_value = {"transport_type": "stdio"}

    from koda.services.mcp_capability_service import verify_capabilities

    result = verify_capabilities("A", "x", force_refresh=False)
    assert result is cached
    # When the cache is hit, runtime resolution is unnecessary.
    assert not mock_resolve.called


@patch("koda.services.mcp_capability_service._load_snapshot")
@patch("koda.services.mcp_capability_service._resolve_runtime_payload")
def test_verify_capabilities_returns_error_snapshot_when_no_connection(mock_resolve, mock_load):
    mock_load.return_value = None
    mock_resolve.return_value = None

    with patch("koda.services.mcp_capability_service._persist_snapshot") as mock_persist:
        from koda.services.mcp_capability_service import verify_capabilities

        snap = verify_capabilities("A", "x")
        assert snap.error == "connection_not_found"
        mock_persist.assert_called_once()
