"""The knowledge corpus check behind the grounding gate, on real Postgres (M6-E1-T5)."""

from __future__ import annotations

import os
from datetime import datetime

import asyncpg
import pytest

from koda.knowledge.types import KnowledgeEntry, KnowledgeLayer, KnowledgeScope
from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

pytestmark = [pytest.mark.postgres]

_AGENTS = ("CORPUS_EMPTY_AGENT", "CORPUS_FILLED_AGENT")


async def test_has_knowledge_chunks_reads_only_the_agents_own_corpus(migrated_postgres: str) -> None:
    schema = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
    conn = await asyncpg.connect(migrated_postgres)
    try:
        for table in ("knowledge_chunks", "knowledge_documents"):
            await conn.execute(f'DELETE FROM "{schema}"."{table}" WHERE agent_id = ANY($1::text[])', list(_AGENTS))
    finally:
        await conn.close()
    empty, filled = (
        KnowledgeV2PostgresBackend(agent_id=agent, dsn=migrated_postgres, schema=schema, embedding_dimension=1024)
        for agent in _AGENTS
    )
    try:
        assert await empty.start() and await filled.start()
        assert await empty.has_knowledge_chunks() is False
        assert await filled.has_knowledge_chunks() is False

        await filled.upsert_documents(
            [
                KnowledgeEntry(
                    id="runbook-1",
                    title="Deploy runbook",
                    content="Run the migration before the deploy.",
                    layer=KnowledgeLayer.APPROVED_RUNBOOK,
                    scope=KnowledgeScope.OPERATIONAL_POLICY,
                    source_label="runbook:deploy",
                    source_path="/tmp/runbook-1.md",
                    updated_at=datetime(2026, 11, 1),
                )
            ],
            object_key="test/runbook-1",
        )

        assert await filled.has_knowledge_chunks() is True
        assert await empty.has_knowledge_chunks() is False
    finally:
        await empty.close()
        await filled.close()
        conn = await asyncpg.connect(migrated_postgres)
        try:
            for table in ("knowledge_chunks", "knowledge_documents"):
                await conn.execute(f'DELETE FROM "{schema}"."{table}" WHERE agent_id = ANY($1::text[])', list(_AGENTS))
        finally:
            await conn.close()
