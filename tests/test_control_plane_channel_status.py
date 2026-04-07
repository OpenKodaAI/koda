"""Tests for channel connection status: get_secret with include_value support."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from koda.control_plane import api as control_plane_api


class _Request:
    def __init__(
        self,
        *,
        query: dict[str, str] | None = None,
        match_info: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.query = query or {}
        self.match_info: dict[str, str] = match_info or {}
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


# ---------------------------------------------------------------------------
#  get_secret without include_value (existing behavior)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_secret_returns_metadata_only_by_default() -> None:
    manager = MagicMock()
    manager.get_secret_asset.return_value = {
        "id": 1,
        "scope": "agent",
        "secret_key": "DISCORD_BOT_TOKEN",
        "preview": "Bot****",
        "updated_at": "2026-04-04T00:00:00Z",
    }

    with patch.object(control_plane_api, "_manager", return_value=manager):
        request = _Request(
            query={"scope": "agent"},
            match_info={"agent_id": "agent-1", "secret_key": "DISCORD_BOT_TOKEN"},
        )
        response = await control_plane_api.get_secret(request)

    body = json.loads(response.text)
    assert body["secret_key"] == "DISCORD_BOT_TOKEN"
    assert body["scope"] == "agent"
    assert "value" not in body
    manager.get_decrypted_secret_value.assert_not_called()


# ---------------------------------------------------------------------------
#  get_secret with include_value=true
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_secret_returns_decrypted_value_when_requested() -> None:
    manager = MagicMock()
    manager.get_secret_asset.return_value = {
        "id": 1,
        "scope": "agent",
        "secret_key": "DISCORD_BOT_TOKEN",
        "preview": "Bot****",
        "updated_at": "2026-04-04T00:00:00Z",
    }
    manager.get_decrypted_secret_value.return_value = "real-discord-token-123"

    with patch.object(control_plane_api, "_manager", return_value=manager):
        request = _Request(
            query={"scope": "agent", "include_value": "true"},
            match_info={"agent_id": "agent-1", "secret_key": "DISCORD_BOT_TOKEN"},
        )
        response = await control_plane_api.get_secret(request)

    body = json.loads(response.text)
    assert body["secret_key"] == "DISCORD_BOT_TOKEN"
    assert body["value"] == "real-discord-token-123"
    manager.get_decrypted_secret_value.assert_called_once_with("agent-1", "DISCORD_BOT_TOKEN")


# ---------------------------------------------------------------------------
#  get_secret with include_value=true but decryption returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_secret_omits_value_when_decryption_returns_none() -> None:
    manager = MagicMock()
    manager.get_secret_asset.return_value = {
        "id": 1,
        "scope": "agent",
        "secret_key": "DISCORD_BOT_TOKEN",
        "preview": "Bot****",
        "updated_at": "2026-04-04T00:00:00Z",
    }
    manager.get_decrypted_secret_value.return_value = None

    with patch.object(control_plane_api, "_manager", return_value=manager):
        request = _Request(
            query={"scope": "agent", "include_value": "true"},
            match_info={"agent_id": "agent-1", "secret_key": "DISCORD_BOT_TOKEN"},
        )
        response = await control_plane_api.get_secret(request)

    body = json.loads(response.text)
    assert body["secret_key"] == "DISCORD_BOT_TOKEN"
    assert "value" not in body


# ---------------------------------------------------------------------------
#  get_secret for non-existent secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_secret_returns_empty_stub_for_missing_secret() -> None:
    manager = MagicMock()
    manager.get_secret_asset.return_value = None

    with patch.object(control_plane_api, "_manager", return_value=manager):
        request = _Request(
            query={"scope": "agent"},
            match_info={"agent_id": "agent-1", "secret_key": "NONEXISTENT_KEY"},
        )
        response = await control_plane_api.get_secret(request)

    body = json.loads(response.text)
    assert body["scope"] == "agent"
    assert body["secret_key"] == "NONEXISTENT_KEY"
    assert body["preview"] == ""
    assert "value" not in body


# ---------------------------------------------------------------------------
#  get_secret with include_value=true for non-existent secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_secret_include_value_on_missing_secret_returns_stub() -> None:
    manager = MagicMock()
    manager.get_secret_asset.return_value = None

    with patch.object(control_plane_api, "_manager", return_value=manager):
        request = _Request(
            query={"scope": "agent", "include_value": "true"},
            match_info={"agent_id": "agent-1", "secret_key": "NONEXISTENT_KEY"},
        )
        response = await control_plane_api.get_secret(request)

    body = json.loads(response.text)
    assert body["scope"] == "agent"
    assert body["secret_key"] == "NONEXISTENT_KEY"
    assert body["preview"] == ""
    assert "value" not in body
    manager.get_decrypted_secret_value.assert_not_called()
