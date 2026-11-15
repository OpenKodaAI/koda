"""Operator approval of a review-required skill package, recorded in Postgres (M1-E4-T3, D-031).

An operator accepts the review through the control-plane install route. The
approval is stored in the package lock in ``skill_packages``, bound to the
package hash the operator saw, with the reviewer and the scanner version.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from koda.control_plane import api as control_plane_api
from koda.control_plane.operator_auth import OperatorAuthContext
from tests.postgres_fixtures import stop_primary_bridge

pytestmark = [pytest.mark.postgres]

_SCHEMA = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
_AGENT = "PKGREVIEW"


class _Request:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.match_info = {"agent_id": _AGENT}
        self.query: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = True
        self._payload = payload
        self._state: dict[str, Any] = {
            "operator_auth": OperatorAuthContext(
                auth_kind="session",
                subject_type="operator",
                user_id="user-1",
                username="owner",
                email="owner@example.com",
                display_name="Owner",
            )
        }

    async def json(self) -> dict[str, Any]:
        return self._payload

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)


async def _rows(dsn: str) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetch(
            f'SELECT package_hash, lock_json FROM "{_SCHEMA}"."skill_packages" WHERE agent_id = $1',
            _AGENT,
        )
    finally:
        await conn.close()


async def _clear(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'DELETE FROM "{_SCHEMA}"."skill_packages" WHERE agent_id = $1', _AGENT)
    finally:
        await conn.close()


@pytest.fixture
async def package_db(migrated_postgres: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    from koda.services import tool_registry
    from koda.skills import _package

    await _clear(migrated_postgres)
    monkeypatch.setattr("koda.config.STATE_BACKEND", "postgres")
    monkeypatch.setattr(_package, "STATE_ROOT_DIR", tmp_path / "state")
    tool_registry._DEFAULT_REGISTRY_CACHE.clear()
    yield migrated_postgres
    stop_primary_bridge()
    tool_registry._DEFAULT_REGISTRY_CACHE.clear()
    await _clear(migrated_postgres)


def _write_review_required_package(root: Path) -> Path:
    package_dir = root / "net_pack"
    package_dir.mkdir()
    (package_dir / "koda-skill.yaml").write_text(
        """
schema_version: koda_skill.v1
id: net_pack
name: Net Pack
version: 1.0.0
description: Package that asks for network access.
author: Koda Tests
permissions:
  network: true
skills:
  - id: net_review
    name: Net Review
    instruction: Check the network notes.
    content: Read the network notes before you call anything.
""".strip(),
        encoding="utf-8",
    )
    return package_dir


async def test_operator_approval_is_recorded_in_postgres_bound_to_the_package_hash(
    package_db: str, tmp_path: Path
) -> None:
    from koda.skills._package import get_skill_package_lock, scan_skill_package

    package_dir = _write_review_required_package(tmp_path)
    scan = scan_skill_package(package_dir, agent_id=_AGENT)
    assert scan.decision == "review_required"

    response = await control_plane_api.install_skill_package_route(
        _Request(
            {
                "path": str(package_dir),
                "review_accepted": True,
                "review_note": "Network access is expected for this agent.",
                "package_hash": scan.package_hash,
            }
        )
    )

    assert response.status == 201, response.text
    rows = await _rows(package_db)
    assert len(rows) == 1
    assert rows[0]["package_hash"] == scan.package_hash
    lock = rows[0]["lock_json"]
    lock = json.loads(lock) if isinstance(lock, str) else dict(lock)
    review = lock["operator_review"]
    assert review["accepted"] is True
    assert review["package_hash"] == scan.package_hash
    assert review["scanner_version"] == scan.scanner_version
    assert review["scan_decision"] == "review_required"
    assert review["reviewer"] == "owner"
    assert review["note"] == "Network access is expected for this agent."
    assert lock["trust_summary"]["operator_review_accepted"] is True
    # The runtime reads the approval back from Postgres, not from the file fallback.
    for fallback in (tmp_path / "state").rglob("*.json"):
        fallback.unlink()
    stored = get_skill_package_lock(_AGENT, "net_pack")
    assert stored is not None
    assert stored["operator_review"]["package_hash"] == scan.package_hash
