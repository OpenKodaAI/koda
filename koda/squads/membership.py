"""Squad membership reconciliation and routing hints.

Threads are the visibility boundary, but a thread can outlive changes in the
control-plane squad membership. These helpers keep open threads aligned with
the current squad roster without granting retroactive visibility: new members
are inserted before the next inbound message is posted, so ``joined_at`` still
guards older history.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any, cast

from koda.logging_config import get_logger
from koda.squads.capabilities import CapabilitySummary, build_capability_summary, get_capability_cache
from koda.squads.threads import ParticipantInfo, ThreadDescriptor

log = get_logger(__name__)
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _agent_value(agent: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(agent, dict) and key in agent:
            return agent.get(key)
        if hasattr(agent, key):
            return getattr(agent, key)
    return None


def _agent_id(agent: Any) -> str:
    return str(_agent_value(agent, "id", "agent_id") or "").strip()


def _agent_display_name(agent: Any, agent_id: str) -> str:
    return str(_agent_value(agent, "display_name", "name") or agent_id).strip() or agent_id


async def _list_squad_agents_from_postgres(squad_id: str, *, thread_store: Any | None = None) -> list[dict[str, Any]]:
    schema = ""
    pool = None
    if thread_store is not None and hasattr(thread_store, "_ensure_pool"):
        try:
            schema = str(getattr(thread_store, "_schema", "") or "")
            pool = await thread_store._ensure_pool()  # noqa: SLF001
        except Exception:
            log.exception("squad_agent_roster_thread_store_pool_failed", squad_id=squad_id)
            pool = None
    if pool is None:
        try:
            import asyncpg  # type: ignore[import-not-found]

            from koda.config import POSTGRES_URL
            from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

            if not POSTGRES_URL:
                return []
            schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
            if not _SCHEMA_RE.match(schema):
                return []
            conn = await asyncpg.connect(POSTGRES_URL)
            try:
                rows = await conn.fetch(
                    f"""SELECT id, display_name, status, workspace_id, squad_id, metadata_json
                          FROM "{schema}"."cp_agent_definitions"
                         WHERE squad_id = $1
                      ORDER BY id ASC""",
                    squad_id,
                )
            finally:
                await conn.close()
            return [dict(row) for row in rows]
        except Exception:
            log.exception("squad_agent_roster_postgres_lookup_failed", squad_id=squad_id)
            return []
    if not _SCHEMA_RE.match(schema):
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT id, display_name, status, workspace_id, squad_id, metadata_json
                  FROM "{schema}"."cp_agent_definitions"
                 WHERE squad_id = $1
              ORDER BY id ASC""",
            squad_id,
        )
    return [dict(row) for row in rows]


async def _list_squad_agents(squad_id: str, *, thread_store: Any | None = None) -> list[Any]:
    rows = await _list_squad_agents_from_postgres(squad_id, thread_store=thread_store)
    if rows:
        return rows
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        return [
            agent for agent in manager.list_agents() if str(_agent_value(agent, "squad_id") or "").strip() == squad_id
        ]
    except Exception:
        log.exception("squad_agent_roster_manager_lookup_failed", squad_id=squad_id)
        return []


def _summary_hint(summary: CapabilitySummary) -> str:
    return " ".join(
        part
        for part in [
            summary.agent_id,
            summary.display_name,
            summary.role,
            " ".join(summary.domains),
            " ".join(summary.primary_outcomes),
            " ".join(summary.tool_categories),
            summary.delegate_when,
            summary.do_not_delegate,
        ]
        if part
    )


async def sync_thread_participants_from_squad(
    thread_store: Any,
    *,
    thread: ThreadDescriptor,
) -> list[ParticipantInfo]:
    """Ensure an open thread has active participants for current squad agents.

    The function is intentionally additive: it never removes participants and
    does not rewrite ``joined_at`` for already-active members. If the control
    plane cannot be read, callers still get the current thread membership so
    routing can continue best-effort.
    """

    try:
        participants = await thread_store.list_participants(thread_id=thread.id)
    except Exception:
        log.exception("squad_participant_sync_current_lookup_failed", thread_id=thread.id)
        participants = []

    active_ids = {p.agent_id for p in participants if p.left_at is None}
    squad_agents = await _list_squad_agents(thread.squad_id, thread_store=thread_store)

    changed = False
    for agent in squad_agents:
        agent_id = _agent_id(agent)
        if not agent_id or agent_id in active_ids:
            continue
        role = "coordinator" if agent_id == thread.coordinator_agent_id else "worker"
        try:
            await thread_store.add_participant(thread_id=thread.id, agent_id=agent_id, role=role)
            active_ids.add(agent_id)
            changed = True
        except Exception:
            log.exception("squad_participant_sync_add_failed", thread_id=thread.id, agent_id=agent_id)

    if not changed:
        return cast(list[ParticipantInfo], participants)
    try:
        return cast(list[ParticipantInfo], await thread_store.list_participants(thread_id=thread.id))
    except Exception:
        log.exception("squad_participant_sync_refresh_failed", thread_id=thread.id)
        return cast(list[ParticipantInfo], participants)


async def build_squad_capability_summaries(
    *,
    squad_id: str,
    participant_agent_ids: Iterable[str] | None = None,
    coordinator_agent_id: str | None = None,
) -> list[CapabilitySummary]:
    """Return AgentSpec-derived summaries for participants.

    The cache is preferred for speed. When it is empty or missing a participant,
    we derive summaries from the control-plane AgentSpec and opportunistically
    upsert them. Semantic routing intentionally consumes only these summaries
    rather than expanding role labels with local keyword lists.
    """

    participant_order = [str(value).strip() for value in participant_agent_ids or [] if str(value or "").strip()]
    participant_set = set(participant_order)
    summaries: dict[str, CapabilitySummary] = {}
    cache = get_capability_cache()
    if cache is not None:
        try:
            for summary in await cache.list_for_squad(squad_id=squad_id):
                if participant_set and summary.agent_id not in participant_set:
                    continue
                summaries[summary.agent_id] = summary
        except Exception:
            log.exception("squad_capability_hint_cache_lookup_failed", squad_id=squad_id)

    missing = participant_set - set(summaries)
    if participant_set and not missing:
        return [summaries[agent_id] for agent_id in participant_order if agent_id in summaries]

    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        agents = await _list_squad_agents(squad_id)
        for agent in agents:
            agent_id = _agent_id(agent)
            if not agent_id:
                continue
            if participant_set and agent_id not in participant_set:
                continue
            if agent_id in summaries and agent_id not in missing:
                continue
            try:
                spec = manager.get_agent_spec(agent_id)
                summary = build_capability_summary(
                    spec if isinstance(spec, dict) else {},
                    agent_id=agent_id,
                    display_name=_agent_display_name(agent, agent_id),
                    is_coordinator=agent_id == coordinator_agent_id,
                )
            except Exception:
                log.exception("squad_capability_hint_spec_lookup_failed", squad_id=squad_id, agent_id=agent_id)
                metadata = _agent_value(agent, "metadata_json") or {}
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except (json.JSONDecodeError, ValueError):
                        metadata = {}
                summary = CapabilitySummary(
                    agent_id=agent_id,
                    display_name=_agent_display_name(agent, agent_id),
                    role=str(_agent_value(agent, "status") or ""),
                    domains=[str(value) for value in metadata.get("domains", [])] if isinstance(metadata, dict) else [],
                    is_coordinator=agent_id == coordinator_agent_id,
                )
            summaries[agent_id] = summary
            if cache is not None:
                try:
                    await cache.upsert(squad_id=squad_id, summary=summary, ttl_seconds=3600)
                except Exception:
                    log.exception("squad_capability_hint_cache_upsert_failed", squad_id=squad_id, agent_id=agent_id)
    except Exception:
        log.exception("squad_capability_hint_control_plane_failed", squad_id=squad_id)

    if participant_set:
        return [summaries[agent_id] for agent_id in participant_order if agent_id in summaries]
    return list(summaries.values())


async def build_squad_capability_hints(
    *,
    squad_id: str,
    participant_agent_ids: Iterable[str] | None = None,
    coordinator_agent_id: str | None = None,
) -> dict[str, str]:
    """Return prompt/display hints derived from capability summaries."""

    summaries = await build_squad_capability_summaries(
        squad_id=squad_id,
        participant_agent_ids=participant_agent_ids,
        coordinator_agent_id=coordinator_agent_id,
    )
    hints = {summary.agent_id: _summary_hint(summary) for summary in summaries}
    return hints
