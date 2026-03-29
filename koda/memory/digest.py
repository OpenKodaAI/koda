"""Daily digest: build formatted summary of memory activity."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from koda.memory.napkin import (
    get_expiring_soon,
    get_memories_by_types,
    get_recent_memories,
    get_stats,
)
from koda.state.agent_scope import normalize_agent_scope
from koda.state_primary import require_primary_state_backend, run_coro_sync


def _primary_backend(agent_id: str | None = None) -> Any:
    return require_primary_state_backend(
        agent_id=normalize_agent_scope(agent_id),
        error="memory digest requires the primary state backend",
    )


def _get_query_count_24h(user_id: int, *, agent_id: str | None = None) -> int:
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    backend = _primary_backend(agent_id)
    return int(cast(int, run_coro_sync(backend.count_recent_queries(user_id=user_id, since=since)) or 0))


def _format_digest(sections: dict[str, str]) -> str:
    parts = ["<b>📋 Daily Digest</b>\n"]
    for title, body in sections.items():
        parts.append(f"\n<b>{title}</b>\n{body}")
    return "\n".join(parts)


def build_digest(user_id: int, *, agent_id: str | None = None) -> str | None:
    sections: dict[str, str] = {}

    since = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = get_recent_memories(user_id, since, limit=10, agent_id=agent_id)
    if recent:
        lines = [f"  • [{m.created_at.strftime('%H:%M')}] {m.content}" for m in recent]
        sections["📝 Memórias Recentes"] = "\n".join(lines)

    tasks = get_memories_by_types(user_id, ["task"], limit=10, agent_id=agent_id)
    if tasks:
        sections["✅ Tarefas Ativas"] = "\n".join(f"  • {m.content}" for m in tasks)

    events = get_memories_by_types(user_id, ["event"], limit=10, agent_id=agent_id)
    if events:
        sections["📅 Eventos"] = "\n".join(f"  • {m.content}" for m in events)

    query_count = _get_query_count_24h(user_id, agent_id=agent_id)
    if query_count > 0:
        sections["📊 Atividade"] = f"  {query_count} consultas nas últimas 24h"

    expiring = get_expiring_soon(user_id, within_days=7, agent_id=agent_id)
    if expiring:
        lines = [f"  • [{m.expires_at.strftime('%Y-%m-%d') if m.expires_at else '?'}] {m.content}" for m in expiring]
        sections["⏳ Expirando em Breve"] = "\n".join(lines)

    stats = get_stats(user_id, agent_id=agent_id)
    if stats["active"] > 0:
        type_parts = [f"{t}: {c}" for t, c in sorted(stats["by_type"].items())]
        n = stats["active"]
        label = "memória ativa" if n == 1 else "memórias ativas"
        sections["🧠 Stats"] = f"  {n} {label} ({', '.join(type_parts)})"

    if not sections:
        return None
    return _format_digest(sections)
