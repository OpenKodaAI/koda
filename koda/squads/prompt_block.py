"""Squad runtime context block — what an agent's prompt sees when it's working in a thread.

Renders a markdown ``<squad_context>`` envelope that joins thread metadata,
the squad members' capability summaries, the recent transcript, and any open
tasks for the thread. Built once per turn by the queue manager (or on demand
via the ``squad_context`` tool) and prepended to the system prompt before the
LLM call. Token budgets per section keep the block bounded.
"""

from __future__ import annotations

from typing import Any

from koda.squads.capabilities import CapabilitySummary, SquadMemberCapabilityCache, format_capability_block
from koda.squads.tasks import SquadTaskStore, TaskDescriptor
from koda.squads.threads import SquadThreadStore, ThreadDescriptor

_DEFAULT_TRANSCRIPT_LIMIT = 8
_TRANSCRIPT_SNIPPET_CHARS = 200
_ACTIVE_TASK_STATUSES = ("pending", "claimed", "in_progress", "blocked")


def _truncate(text: str, *, cap: int) -> str:
    if not text:
        return ""
    flat = text.replace("\n", " ").strip()
    return flat[:cap] + ("…" if len(flat) > cap else "")


def _render_thread_header(thread: ThreadDescriptor, executing_agent_id: str | None) -> list[str]:
    lines = [
        f"Thread: {thread.title or '(untitled)'} (status={thread.status})",
        f"Squad: {thread.squad_id} (workspace={thread.workspace_id})",
    ]
    if thread.coordinator_agent_id:
        lines.append(f"Coordinator: {thread.coordinator_agent_id}")
    else:
        lines.append("Coordinator: (none — capability-based routing)")
    if executing_agent_id:
        lines.append(f"You are: {executing_agent_id}")
    return lines


def _render_transcript(messages: list[dict[str, Any]]) -> list[str]:
    if not messages:
        return []
    out: list[str] = ["", "Recent thread (last messages first):"]
    for msg in messages:
        sender = msg.get("from") or "?"
        kind = msg.get("type") or "agent_text"
        content = _truncate(str(msg.get("content") or ""), cap=_TRANSCRIPT_SNIPPET_CHARS)
        msg_id = msg.get("id")
        reply_to = msg.get("in_reply_to") or (msg.get("metadata") or {}).get("in_reply_to")
        suffix = f" reply_to={reply_to}" if reply_to else ""
        summary = msg.get("reply_summary") if isinstance(msg.get("reply_summary"), dict) else {}
        open_replies = int(summary.get("open") or 0) if summary else 0
        if open_replies:
            suffix += f" open_reply_obligations={open_replies}"
        out.append(f"- [{msg_id}] [{kind}] {sender}{suffix}: {content}")
    return out


def _render_reply_obligations(messages: list[dict[str, Any]]) -> list[str]:
    open_items: list[str] = []
    for msg in messages:
        obligations = msg.get("reply_obligations")
        if not isinstance(obligations, list):
            continue
        for item in obligations:
            if not isinstance(item, dict) or item.get("status") != "open":
                continue
            target = item.get("targetAgentId") or item.get("target_agent_id") or "?"
            source = item.get("sourceMessageId") or msg.get("id")
            deadline = item.get("requiresResponseBy") or "no deadline"
            open_items.append(f"- obligation={item.get('id')} source=msg-{source} target={target} due={deadline}")
    if not open_items:
        return []
    return ["", "Open reply obligations (answer or follow up explicitly):", *open_items[:10]]


def _render_active_tasks(tasks: list[TaskDescriptor]) -> list[str]:
    if not tasks:
        return []
    out: list[str] = ["", "Active tasks (open):"]
    for task in tasks:
        owner = task.assigned_agent_id or "unassigned"
        prefix = task.id[:8]
        out.append(f"- [{task.status}] {prefix}… '{task.title}' — {owner}")
    return out


def _render_delegation_chain(chain: list[str] | None) -> list[str]:
    if not chain:
        return []
    return ["", "Delegation chain (do not loop): " + " -> ".join(chain)]


async def build_squad_context_block(
    *,
    thread_id: str,
    executing_agent_id: str | None = None,
    thread_store: SquadThreadStore,
    capability_cache: SquadMemberCapabilityCache,
    task_store: SquadTaskStore | None = None,
    transcript_limit: int = _DEFAULT_TRANSCRIPT_LIMIT,
    delegation_chain: list[str] | None = None,
    visible_after: Any | None = None,
) -> str | None:
    """Build the runtime ``<squad_context>`` block for ``thread_id``.

    Returns ``None`` if the thread doesn't exist (caller can fall back to
    the persona-only prompt). Each section is silently skipped when empty.
    """
    thread = await thread_store.get_thread(thread_id)
    if thread is None:
        return None
    summaries: list[CapabilitySummary] = await capability_cache.list_for_squad(squad_id=thread.squad_id)
    history = await thread_store.thread_history(
        thread_id=thread_id,
        limit=max(1, int(transcript_limit)),
        visible_after=visible_after,
    )
    active_tasks: list[TaskDescriptor] = []
    if task_store is not None:
        active_tasks = await task_store.list_tasks(
            thread_id=thread_id,
            status=list(_ACTIVE_TASK_STATUSES),
            limit=20,
        )

    lines: list[str] = ["<squad_context>"]
    lines.extend(_render_thread_header(thread, executing_agent_id))
    if summaries:
        lines.append("")
        lines.append(format_capability_block(summaries, exclude_agent_id=executing_agent_id))
    lines.extend(_render_transcript(history))
    lines.extend(_render_reply_obligations(history))
    lines.extend(_render_active_tasks(active_tasks))
    lines.extend(_render_delegation_chain(delegation_chain))
    lines.append("</squad_context>")
    return "\n".join(lines)


async def build_squad_context_block_default(
    *,
    thread_id: str,
    executing_agent_id: str | None = None,
    transcript_limit: int = _DEFAULT_TRANSCRIPT_LIMIT,
    delegation_chain: list[str] | None = None,
) -> str | None:
    """Convenience wrapper that uses the singleton stores. Returns ``None``
    when any required store is unavailable (e.g., no Postgres DSN)."""
    from koda.squads.capabilities import get_capability_cache
    from koda.squads.tasks import get_squad_task_store
    from koda.squads.threads import get_squad_thread_store

    threads = get_squad_thread_store()
    cache = get_capability_cache()
    if threads is None or cache is None:
        return None
    visible_after = None
    if executing_agent_id:
        try:
            from koda.squads.access import get_squad_access_service

            access = get_squad_access_service()
            if access is not None:
                grant = await access.require_thread_access(thread_id=thread_id, agent_id=executing_agent_id)
                visible_after = None if grant.is_coordinator else grant.joined_at
        except Exception:
            return None
    return await build_squad_context_block(
        thread_id=thread_id,
        executing_agent_id=executing_agent_id,
        thread_store=threads,
        capability_cache=cache,
        task_store=get_squad_task_store(),
        transcript_limit=transcript_limit,
        delegation_chain=delegation_chain,
        visible_after=visible_after,
    )
