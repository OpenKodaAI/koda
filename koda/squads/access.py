"""Authorization helpers for squad-scoped resources.

Squad membership is the visibility boundary. This service centralizes the
checks that were previously scattered across handlers so every tool/API path
fails closed before reading or mutating a thread, task, or message.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from koda.squads.threads import ThreadDescriptor, _row_to_thread

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _row_id_from_message_id(value: int | str) -> int:
    if isinstance(value, int):
        return value
    raw = str(value or "").strip()
    if raw.isdigit():
        return int(raw)
    match = re.search(r"(\d+)$", raw)
    if match:
        return int(match.group(1))
    raise SquadAccessError(f"invalid message_id {value!r}")


class SquadAccessError(PermissionError):
    """Caller is not allowed to access the requested squad resource."""


class SquadResourceNotFoundError(KeyError):
    """Requested squad resource does not exist."""


PrincipalKind = Literal["agent", "thread_owner", "workspace_operator", "system"]


@dataclass(frozen=True)
class SquadPrincipal:
    """Authenticated actor attempting to access a squad resource.

    ``agent`` keeps the legacy runtime/tool contract. Human operators and
    thread owners are explicit principals so Web/Telegram paths cannot smuggle
    themselves in as an agent id without audit context.
    """

    kind: PrincipalKind
    agent_id: str | None = None
    user_id: int | None = None
    username: str | None = None
    workspace_id: str | None = None
    break_glass_reason: str | None = None

    @classmethod
    def agent(cls, agent_id: str) -> SquadPrincipal:
        return cls(kind="agent", agent_id=agent_id)

    @classmethod
    def thread_owner(cls, user_id: int, *, workspace_id: str | None = None) -> SquadPrincipal:
        return cls(kind="thread_owner", user_id=user_id, workspace_id=workspace_id)

    @classmethod
    def workspace_operator(
        cls,
        username: str,
        *,
        workspace_id: str,
        break_glass_reason: str | None = None,
    ) -> SquadPrincipal:
        return cls(
            kind="workspace_operator",
            username=username,
            workspace_id=workspace_id,
            break_glass_reason=break_glass_reason,
        )

    @classmethod
    def system(cls) -> SquadPrincipal:
        return cls(kind="system")


@dataclass(frozen=True)
class ThreadAccess:
    thread: ThreadDescriptor
    principal: SquadPrincipal
    agent_id: str | None
    role: str
    joined_at: datetime | None
    is_coordinator: bool = False
    redacted: bool = False
    break_glass: bool = False


class SquadAccessService:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None

    async def require_thread_access(
        self,
        *,
        thread_id: str,
        agent_id: str,
        require_write: bool = False,
        message_id: int | str | None = None,
    ) -> ThreadAccess:
        if not thread_id or not agent_id:
            raise SquadAccessError("thread_id and agent_id are required")
        return await self.require_thread_access_for_principal(
            thread_id=thread_id,
            principal=SquadPrincipal.agent(agent_id),
            require_write=require_write,
            message_id=message_id,
        )

    async def require_thread_access_for_principal(
        self,
        *,
        thread_id: str,
        principal: SquadPrincipal,
        require_write: bool = False,
        message_id: int | str | None = None,
    ) -> ThreadAccess:
        if not thread_id:
            raise SquadAccessError("thread_id is required")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_threads" WHERE id = $1',
                str(thread_id),
            )
            if row is None:
                raise SquadResourceNotFoundError(f"thread {thread_id!r} not found")
            thread = _row_to_thread(row)
            if principal.kind == "system":
                return ThreadAccess(
                    thread=thread,
                    principal=principal,
                    agent_id=None,
                    role="system",
                    joined_at=None,
                )
            if require_write and thread.status in {"completed", "archived"}:
                raise SquadAccessError(f"thread {thread_id!r} is {thread.status}")
            if principal.kind == "workspace_operator":
                return await self._require_operator_thread_access(
                    conn=conn,
                    thread=thread,
                    principal=principal,
                    require_write=require_write,
                    message_id=message_id,
                )
            if principal.kind == "thread_owner":
                return await self._require_owner_thread_access(
                    conn=conn,
                    thread=thread,
                    principal=principal,
                    require_write=require_write,
                    message_id=message_id,
                )
            agent_id = principal.agent_id or ""
            if not agent_id:
                raise SquadAccessError("agent principal requires agent_id")
            participant = await conn.fetchrow(
                f"""SELECT role, joined_at, left_at, paused
                      FROM "{self._schema}"."squad_thread_participants"
                     WHERE thread_id = $1
                       AND agent_id = $2
                     LIMIT 1""",
                str(thread_id),
                agent_id,
            )
            coordinator_id = await conn.fetchval(
                f"""SELECT coordinator_agent_id
                      FROM "{self._schema}"."squad_coordinator_state"
                     WHERE squad_id = $1""",
                thread.squad_id,
            )
            is_coordinator = bool(coordinator_id and coordinator_id == agent_id)
            role = "coordinator" if is_coordinator else ""
            joined_at: datetime | None = None
            if participant is not None:
                role = str(participant["role"] or role or "worker")
                joined_at = participant["joined_at"]
                if participant["left_at"] is not None:
                    raise SquadAccessError(f"agent {agent_id!r} is not an active participant")
                if bool(participant["paused"]) and require_write and not is_coordinator:
                    raise SquadAccessError(f"agent {agent_id!r} is paused in thread {thread_id!r}")
            elif not is_coordinator:
                raise SquadAccessError(f"agent {agent_id!r} is not a participant of thread {thread_id!r}")

            if thread.visibility == "private" and participant is None and not is_coordinator:
                raise SquadAccessError(f"private thread {thread_id!r} is visible only to participants")

            if message_id is not None and participant is not None and joined_at is not None:
                await self._assert_message_visible_after(
                    conn=conn,
                    thread_id=str(thread_id),
                    message_id=message_id,
                    joined_at=joined_at,
                    bypass=is_coordinator,
                )

        return ThreadAccess(
            thread=thread,
            principal=principal,
            agent_id=agent_id,
            role=role or "observer",
            joined_at=joined_at,
            is_coordinator=is_coordinator,
        )

    async def _require_operator_thread_access(
        self,
        *,
        conn: Any,
        thread: ThreadDescriptor,
        principal: SquadPrincipal,
        require_write: bool,
        message_id: int | str | None,
    ) -> ThreadAccess:
        if not principal.workspace_id or principal.workspace_id != thread.workspace_id:
            raise SquadAccessError("operator is not scoped to this workspace")
        if thread.visibility == "private":
            reason = (principal.break_glass_reason or "").strip()
            if require_write:
                raise SquadAccessError("operators cannot write to private side-threads")
            if reason:
                from koda.config import SQUAD_OPERATOR_BREAK_GLASS_ENABLED

                if not SQUAD_OPERATOR_BREAK_GLASS_ENABLED:
                    raise SquadAccessError("operator break-glass is disabled")
                await self._audit_break_glass(conn=conn, thread=thread, principal=principal, reason=reason)
                return ThreadAccess(
                    thread=thread,
                    principal=principal,
                    agent_id=None,
                    role="operator",
                    joined_at=None,
                    redacted=False,
                    break_glass=True,
                )
            return ThreadAccess(
                thread=thread,
                principal=principal,
                agent_id=None,
                role="operator",
                joined_at=None,
                redacted=True,
            )
        if message_id is not None:
            await self._assert_message_exists(conn=conn, thread_id=thread.id, message_id=message_id)
        return ThreadAccess(
            thread=thread,
            principal=principal,
            agent_id=None,
            role="operator",
            joined_at=None,
        )

    async def _require_owner_thread_access(
        self,
        *,
        conn: Any,
        thread: ThreadDescriptor,
        principal: SquadPrincipal,
        require_write: bool,
        message_id: int | str | None,
    ) -> ThreadAccess:
        if (
            principal.user_id is None
            or thread.owner_user_id is None
            or int(principal.user_id) != int(thread.owner_user_id)
        ):
            raise SquadAccessError("thread owner mismatch")
        if principal.workspace_id and principal.workspace_id != thread.workspace_id:
            raise SquadAccessError("thread owner is not scoped to this workspace")
        if thread.visibility == "private":
            if require_write:
                raise SquadAccessError("thread owner cannot write to private side-threads")
            return ThreadAccess(
                thread=thread,
                principal=principal,
                agent_id=None,
                role="thread_owner",
                joined_at=None,
                redacted=True,
            )
        if message_id is not None:
            await self._assert_message_exists(conn=conn, thread_id=thread.id, message_id=message_id)
        return ThreadAccess(
            thread=thread,
            principal=principal,
            agent_id=None,
            role="thread_owner",
            joined_at=None,
        )

    async def _assert_message_exists(self, *, conn: Any, thread_id: str, message_id: int | str) -> None:
        msg_row = await conn.fetchrow(
            f"""SELECT 1
                  FROM "{self._schema}"."squad_messages"
                 WHERE id = $1
                   AND thread_id = $2""",
            _row_id_from_message_id(message_id),
            str(thread_id),
        )
        if msg_row is None:
            raise SquadResourceNotFoundError(f"message {message_id!r} not found")

    async def _assert_message_visible_after(
        self,
        *,
        conn: Any,
        thread_id: str,
        message_id: int | str,
        joined_at: datetime,
        bypass: bool,
    ) -> None:
        msg_row = await conn.fetchrow(
            f"""SELECT created_at
                  FROM "{self._schema}"."squad_messages"
                 WHERE id = $1
                   AND thread_id = $2""",
            _row_id_from_message_id(message_id),
            str(thread_id),
        )
        if msg_row is None:
            raise SquadResourceNotFoundError(f"message {message_id!r} not found")
        if msg_row["created_at"] < joined_at and not bypass:
            raise SquadAccessError("participant cannot read messages created before joined_at")

    async def _audit_break_glass(
        self,
        *,
        conn: Any,
        thread: ThreadDescriptor,
        principal: SquadPrincipal,
        reason: str,
    ) -> None:
        with suppress(Exception):
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."audit_events"
                        (agent_id, timestamp, event_type, pod_name, trace_id, details_json)
                    VALUES ($1, NOW(), 'squad.operator.break_glass', '', $2, $3::jsonb)""",
                principal.username or "operator",
                thread.id,
                json.dumps(
                    {
                        "thread_id": thread.id,
                        "workspace_id": thread.workspace_id,
                        "squad_id": thread.squad_id,
                        "reason": reason,
                    }
                ),
            )

    def visible_after_for(self, access: ThreadAccess) -> datetime | None:
        """Return the lower message timestamp bound for timeline reads."""
        if access.redacted or access.is_coordinator or access.principal.kind in {"system", "workspace_operator"}:
            return None
        return access.joined_at

    def redact_messages(self, access: ThreadAccess, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply private-thread/operator redaction to a timeline payload."""
        if not access.redacted:
            return messages
        redacted: list[dict[str, Any]] = []
        for msg in messages:
            item = dict(msg)
            item["content"] = "[redacted]"
            item["payload"] = {"redacted": True}
            metadata = dict(item.get("metadata") or {})
            metadata.pop("payload", None)
            metadata["redacted"] = True
            item["metadata"] = metadata
            redacted.append(item)
        return redacted

    async def require_task_access(
        self,
        *,
        task_id: str,
        agent_id: str,
        require_write: bool = False,
        coordinator_override: bool = False,
    ) -> tuple[ThreadAccess, dict[str, Any]]:
        if not task_id:
            raise SquadAccessError("task_id is required")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            task = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_tasks" WHERE id = $1',
                str(task_id),
            )
        if task is None:
            raise SquadResourceNotFoundError(f"task {task_id!r} not found")
        access = await self.require_thread_access(
            thread_id=str(task["thread_id"]),
            agent_id=agent_id,
            require_write=require_write,
        )
        if (
            require_write
            and task["assigned_agent_id"]
            and task["assigned_agent_id"] != agent_id
            and not (coordinator_override and access.is_coordinator)
        ):
            raise SquadAccessError(f"agent {agent_id!r} cannot mutate task assigned to {task['assigned_agent_id']!r}")
        return access, dict(task)

    async def require_task_access_for_principal(
        self,
        *,
        task_id: str,
        principal: SquadPrincipal,
        require_write: bool = False,
    ) -> tuple[ThreadAccess, dict[str, Any]]:
        if not task_id:
            raise SquadAccessError("task_id is required")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            task = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_tasks" WHERE id = $1',
                str(task_id),
            )
        if task is None:
            raise SquadResourceNotFoundError(f"task {task_id!r} not found")
        access = await self.require_thread_access_for_principal(
            thread_id=str(task["thread_id"]),
            principal=principal,
            require_write=require_write,
        )
        if require_write and principal.kind not in {"agent", "system"} and access.redacted:
            raise SquadAccessError("principal cannot mutate redacted task content")
        return access, dict(task)

    async def require_coordinator(self, *, squad_id: str, agent_id: str) -> None:
        if not squad_id or not agent_id:
            raise SquadAccessError("squad_id and agent_id are required")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            coordinator_id = await conn.fetchval(
                f"""SELECT coordinator_agent_id
                      FROM "{self._schema}"."squad_coordinator_state"
                     WHERE squad_id = $1""",
                squad_id,
            )
        if coordinator_id != agent_id:
            raise SquadAccessError(f"agent {agent_id!r} is not coordinator for squad {squad_id!r}")


_service: SquadAccessService | None = None


def _build_service() -> SquadAccessService | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return SquadAccessService(dsn=POSTGRES_URL, schema=schema)


def get_squad_access_service() -> SquadAccessService | None:
    """Return the singleton access service, or None if Postgres is disabled."""
    global _service  # noqa: PLW0603
    if _service is None:
        _service = _build_service()
    return _service
