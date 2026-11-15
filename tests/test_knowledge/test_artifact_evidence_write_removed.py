"""The artifact evidence write path is gone (M4-E1-T14, D-260).

It wrote into ``artifact_evidence_nodes``, a table no migration creates and
no reader selects from, so every live call failed. Artifact evidence that
readers use lives in ``artifact_derivatives``.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

import koda
from koda.knowledge.graph_materializer import KnowledgeGraphMaterializer
from koda.knowledge.manager import KnowledgeManager
from koda.knowledge.repository import KnowledgeRepository
from koda.services import queue_manager

_TABLE = "artifact_evidence_nodes"
_KODA_ROOT = Path(koda.__file__).parent


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        (KnowledgeRepository, "batch_upsert_artifact_evidence"),
        (KnowledgeGraphMaterializer, "materialize_artifacts"),
        (KnowledgeManager, "ingest_artifact_dossiers"),
        (queue_manager, "_persist_artifact_evidence_nodes"),
    ],
)
def test_write_path_and_its_callers_are_gone(owner: object, name: str) -> None:
    assert not hasattr(owner, name)


def test_no_code_references_the_table() -> None:
    referencing = [
        str(path.relative_to(_KODA_ROOT)) for path in _KODA_ROOT.rglob("*.py") if _TABLE in path.read_text("utf-8")
    ]
    assert referencing == []


@pytest.mark.postgres
async def test_no_migration_creates_the_table(migrated_postgres: str) -> None:
    conn = await asyncpg.connect(migrated_postgres)
    try:
        knowledge_tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'artifact_derivatives'"
        )
        evidence_tables = await conn.fetch(
            "SELECT table_schema FROM information_schema.tables WHERE table_name = $1", _TABLE
        )
    finally:
        await conn.close()

    assert knowledge_tables >= 1  # the migrations ran
    assert evidence_tables == []
