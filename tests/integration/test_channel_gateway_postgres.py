"""Channel gateway pairing limits and identity writes against Postgres (M1-E5-T3, D-182).

The gateway keeps identities, unknown senders and pairing codes only in the
primary backend. Message handling writes an identity only when its status
changes, so an approval the control plane writes while the agent handles a
message from the same sender is not overwritten. Pairing guesses are limited
per sender.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from koda.channels import gateway
from koda.channels.types import ChannelIdentity, IncomingMessage
from tests.postgres_fixtures import stop_primary_bridge

pytestmark = [pytest.mark.postgres]

_SCHEMA = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
_AGENT = "CHGWPG"
_TABLES = ("channel_gateway_identities", "channel_unknown_senders", "channel_pairing_codes", "channel_gateway_events")


async def _clear(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        for table in _TABLES:
            await conn.execute(f'DELETE FROM "{_SCHEMA}"."{table}" WHERE agent_id = $1', _AGENT)
    finally:
        await conn.close()


async def _identity_statuses(dsn: str) -> list[str]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            f'SELECT status FROM "{_SCHEMA}"."channel_gateway_identities" WHERE agent_id = $1', _AGENT
        )
    finally:
        await conn.close()
    return [str(row["status"]) for row in rows]


async def _unknown_sender_statuses(dsn: str) -> list[str]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(f'SELECT status FROM "{_SCHEMA}"."channel_unknown_senders" WHERE agent_id = $1', _AGENT)
    finally:
        await conn.close()
    return [str(row["status"]) for row in rows]


@pytest.fixture
async def gateway_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    await _clear(migrated_postgres)
    monkeypatch.setattr("koda.config.STATE_BACKEND", "postgres")
    monkeypatch.setattr(gateway, "_emit_observability", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gateway, "_PAIRING_FAILURES", {}, raising=False)
    monkeypatch.setattr(gateway, "_PAIRING_LOCKED_UNTIL", {}, raising=False)
    yield migrated_postgres
    stop_primary_bridge()
    await _clear(migrated_postgres)


def _message(text: str, *, user_id: str = "42") -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        channel=ChannelIdentity(channel_type="telegram", channel_id="chat-1", user_id=user_id, user_display_name="A"),
        text=text,
        timestamp=1.0,
    )


async def test_control_plane_approval_survives_concurrent_message_handling(
    gateway_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = gateway.evaluate_incoming_message(_AGENT, _message("hello there"), legacy_allowed_user_ids=set())
    original_list = gateway._list_primary_identities
    approved: list[bool] = []

    def stale_read_then_control_plane_approval(agent_id: str) -> Any:
        rows = original_list(agent_id)
        if not approved:
            approved.append(True)
            gateway.approve_identity(_AGENT, first.identity_id, approved_by="owner")
        return rows

    monkeypatch.setattr(gateway, "_list_primary_identities", stale_read_then_control_plane_approval)
    gateway.evaluate_incoming_message(_AGENT, _message("still waiting"), legacy_allowed_user_ids=set())
    monkeypatch.setattr(gateway, "_list_primary_identities", original_list)

    after = gateway.evaluate_incoming_message(_AGENT, _message("real task"), legacy_allowed_user_ids=set())

    assert after.allowed is True
    assert await _identity_statuses(gateway_db) == ["allowed"]
    # The queue entry the control plane resolved is not put back as pending.
    assert await _unknown_sender_statuses(gateway_db) == ["resolved"]


async def test_pairing_guesses_are_limited_per_sender(gateway_db: str) -> None:
    code = str(gateway.create_pairing_code(_AGENT, channel_type="telegram", created_by="owner")["code"])

    for index in range(gateway.PAIRING_MAX_FAILURES):
        gateway.evaluate_incoming_message(_AGENT, _message(f"GUESS{index:03d}"), legacy_allowed_user_ids=set())
    locked = gateway.evaluate_incoming_message(_AGENT, _message(code), legacy_allowed_user_ids=set())
    other = gateway.evaluate_incoming_message(_AGENT, _message(code, user_id="43"), legacy_allowed_user_ids=set())

    assert locked.reason_code == "channel.pairing_locked"
    assert other.reason_code == "channel.pairing_complete"
    assert gateway.list_pairing_codes(_AGENT) == []
