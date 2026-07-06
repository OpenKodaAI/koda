from __future__ import annotations

import inspect

import pytest

from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend
from koda.memory.namespaces import NAMESPACE_KINDS, namespace_allowed, resolve_memory_namespace
from koda.memory.types import Memory, MemoryType


@pytest.mark.parametrize("kind", sorted(NAMESPACE_KINDS))
def test_memory_namespace_resolves_supported_kinds(kind: str) -> None:
    namespace = resolve_memory_namespace(
        user_id=42,
        agent_id="AGENT_A",
        namespace_kind=kind,
        namespace_key=f"{kind}:custom",
        session_id="sess-1",
        squad_thread_id="thread-1",
        workspace_id="workspace-1",
        project_key="project-a",
        team="team-a",
        org_id="org-a",
    )

    assert namespace.kind == kind
    assert namespace.key == f"{kind}:custom"
    assert namespace.scope["agent_id"] == "agent_a"
    assert namespace.to_dict()["scope"]["user_id"] == "42"


def test_memory_namespace_defaults_to_agent_scope_for_legacy_memory() -> None:
    namespace = resolve_memory_namespace(user_id=42, agent_id="AGENT_A")

    assert namespace.kind == "agent"
    assert namespace.key == "agent_a"


def test_namespace_allowed_blocks_cross_namespace_memory() -> None:
    memory = Memory(
        user_id=42,
        agent_id="AGENT_A",
        memory_type=MemoryType.FACT,
        content="Only visible to squad alpha.",
        namespace_kind="squad",
        namespace_key="squad:alpha",
    )

    assert namespace_allowed(memory, namespace_kind="squad", namespace_key="squad:alpha")
    assert not namespace_allowed(memory, namespace_kind="agent", namespace_key="agent_a")
    assert not namespace_allowed(memory, namespace_kind="squad", namespace_key="squad:beta")


def test_memory_namespace_migration_is_additive() -> None:
    src = inspect.getsource(KnowledgeV2PostgresBackend._migrations)

    assert "046_memory_governance_namespaces" in src
    assert "ADD COLUMN IF NOT EXISTS namespace_kind" in src
    assert "ADD COLUMN IF NOT EXISTS namespace_key" in src
    assert "ADD COLUMN IF NOT EXISTS sensitivity" in src
