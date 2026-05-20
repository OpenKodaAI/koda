"""Namespace helpers for governed memory recall and writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from koda.state.agent_scope import normalize_agent_scope

NAMESPACE_KINDS = frozenset({"user", "agent", "squad", "workspace", "project", "org"})
SENSITIVITY_LEVELS = frozenset({"normal", "sensitive"})


@dataclass(frozen=True, slots=True)
class MemoryNamespace:
    kind: str
    key: str
    scope: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "key": self.key, "scope": dict(self.scope)}


def normalize_namespace_kind(value: Any, *, fallback: str = "agent") -> str:
    text = str(value or "").strip().lower()
    return text if text in NAMESPACE_KINDS else fallback


def normalize_sensitivity(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SENSITIVITY_LEVELS else "normal"


def resolve_memory_namespace(
    *,
    user_id: int | str | None = None,
    agent_id: str | None = None,
    namespace_kind: str | None = None,
    namespace_key: str | None = None,
    session_id: str | None = None,
    squad_thread_id: str | None = None,
    workspace_id: str | None = None,
    project_key: str = "",
    team: str = "",
    org_id: str | None = None,
) -> MemoryNamespace:
    """Resolve an additive namespace without changing legacy agent scoping."""

    agent_scope = normalize_agent_scope(agent_id)
    kind = normalize_namespace_kind(namespace_kind)
    key = str(namespace_key or "").strip()
    if not key:
        if kind == "user" and user_id is not None:
            key = f"user:{user_id}"
        elif kind == "squad" and squad_thread_id:
            key = f"squad:{squad_thread_id}"
        elif kind == "workspace" and workspace_id:
            key = f"workspace:{workspace_id}"
        elif kind == "project" and project_key:
            key = f"project:{project_key}"
        elif kind == "org" and (org_id or team):
            key = f"org:{org_id or team}"
        else:
            kind = "agent"
            key = agent_scope
    scope = {
        "user_id": str(user_id or ""),
        "agent_id": agent_scope,
        "session_id": str(session_id or ""),
        "squad_thread_id": str(squad_thread_id or ""),
        "workspace_id": str(workspace_id or ""),
        "project_key": str(project_key or ""),
        "team": str(team or ""),
        "org_id": str(org_id or ""),
    }
    return MemoryNamespace(kind=kind, key=key, scope={k: v for k, v in scope.items() if v})


def namespace_for_memory(memory: Any, *, fallback_agent_id: str | None = None) -> MemoryNamespace:
    metadata = getattr(memory, "metadata", {}) if hasattr(memory, "metadata") else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    return resolve_memory_namespace(
        user_id=getattr(memory, "user_id", None),
        agent_id=getattr(memory, "agent_id", None) or fallback_agent_id,
        namespace_kind=getattr(memory, "namespace_kind", "") or metadata.get("namespace_kind"),
        namespace_key=getattr(memory, "namespace_key", "") or metadata.get("namespace_key"),
        session_id=getattr(memory, "session_id", None),
        squad_thread_id=str(metadata.get("squad_thread_id") or ""),
        workspace_id=str(metadata.get("workspace_id") or ""),
        project_key=str(getattr(memory, "project_key", "") or metadata.get("project_key") or ""),
        team=str(getattr(memory, "team", "") or metadata.get("team") or ""),
        org_id=str(metadata.get("org_id") or ""),
    )


def namespace_allowed(
    memory: Any,
    *,
    namespace_kind: str | None = None,
    namespace_key: str | None = None,
) -> bool:
    if not namespace_kind and not namespace_key:
        return True
    memory_kind = normalize_namespace_kind(getattr(memory, "namespace_kind", "agent"))
    memory_key = str(getattr(memory, "namespace_key", "") or "").strip()
    if namespace_kind and memory_kind != normalize_namespace_kind(namespace_kind):
        return False
    return not namespace_key or memory_key == str(namespace_key).strip()
