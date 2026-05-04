"""Per-agent Telegram polling offset.

Replaces ``drop_pending_updates=True`` with the Telegram server-side
offset. To make crashes diagnosable and to support the centralized
bot-gateway, the supervisor records the last seen ``update_id`` per
agent in ``cp_telegram_offsets``.

The DB row is observability + recovery aid, not a hard ack: Telegram is
still the source of truth for what the bot has consumed. The
centralized bot gateway uses this table as the offset map that drives
its dispatcher.
"""

from __future__ import annotations

from koda.control_plane.database import execute, fetch_one, now_iso
from koda.logging_config import get_logger

log = get_logger(__name__)


def get_last_offset(agent_id: str) -> int:
    """Return the last-recorded update_id for ``agent_id`` (0 if never set).

    Failure (table missing in legacy deploys, transient DB error) returns
    0 with a log line so the bot still polls fresh; we never want offset
    plumbing to block message delivery.
    """
    scope = str(agent_id or "").strip()
    if not scope:
        return 0
    try:
        row = fetch_one(
            "SELECT last_update_id FROM cp_telegram_offsets WHERE agent_id = ?",
            (scope,),
        )
    except Exception:
        log.exception("telegram_offset_read_failed", agent_id=scope)
        return 0
    if not row:
        return 0
    raw = row.get("last_update_id") if isinstance(row, dict) else None
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def record_offset(agent_id: str, update_id: int) -> None:
    """Upsert the latest update_id for ``agent_id`` after it was processed."""
    scope = str(agent_id or "").strip()
    if not scope or not isinstance(update_id, int) or update_id <= 0:
        return
    try:
        execute(
            """
            INSERT INTO cp_telegram_offsets (agent_id, last_update_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (agent_id) DO UPDATE
            SET last_update_id = GREATEST(cp_telegram_offsets.last_update_id, excluded.last_update_id),
                updated_at = excluded.updated_at
            """,
            (scope, update_id, now_iso()),
        )
    except Exception:
        log.exception("telegram_offset_write_failed", agent_id=scope, update_id=update_id)
