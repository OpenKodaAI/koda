"""Tests for squad capability summaries (builder + cache)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest

from koda.squads.capabilities import (
    CapabilitySummary,
    SquadMemberCapabilityCache,
    build_capability_summary,
    format_capability_block,
)


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


# --- builder unit tests (no PG) ---


def test_build_summary_minimal() -> None:
    summary = build_capability_summary({"agent_id": "fe"})
    assert summary.agent_id == "FE"
    assert summary.display_name == "FE"
    assert summary.role == ""
    assert summary.domains == []
    assert summary.tool_categories == []


def test_build_summary_full() -> None:
    summary = build_capability_summary(
        {
            "agent_id": "frontend",
            "mission_profile": {
                "role": "Frontend Engineer",
                "domains": ["frontend", "react", "tailwind", "design"],
                "primary_outcomes": ["polished UI", "accessibility", "perf", "extra-outcome"],
                "delegate_when": "ui work, design polish",
                "do_not_delegate": "backend APIs",
            },
            "tool_policy": {
                "allowed_tool_ids": [
                    "file_read",
                    "file_write",
                    "browser_navigate",
                    "git_commit",
                    "agent_send",
                    "squad_post",
                ],
            },
        },
        display_name="Frontend Dev",
        is_coordinator=False,
    )
    assert summary.agent_id == "FRONTEND"
    assert summary.display_name == "Frontend Dev"
    assert summary.role == "Frontend Engineer"
    assert summary.domains == ["frontend", "react", "tailwind", "design"]
    # primary_outcomes is capped at 3
    assert summary.primary_outcomes == ["polished UI", "accessibility", "perf"]
    assert "fileops" in summary.tool_categories
    assert "browser" in summary.tool_categories
    assert "git" in summary.tool_categories
    assert "agent_comm" in summary.tool_categories
    # tool_categories are deduped + capped (max 6)
    assert len(summary.tool_categories) <= 6


def test_build_summary_truncates_long_text() -> None:
    long = "x" * 1000
    summary = build_capability_summary(
        {
            "agent_id": "fe",
            "mission_profile": {"delegate_when": long, "do_not_delegate": long},
        }
    )
    assert len(summary.delegate_when) == 300
    assert len(summary.do_not_delegate) == 300


def test_build_summary_string_to_list_coercion() -> None:
    summary = build_capability_summary(
        {
            "agent_id": "fe",
            "mission_profile": {"domains": "react"},
        }
    )
    assert summary.domains == ["react"]


def test_format_block_excludes_self() -> None:
    summaries = [
        CapabilitySummary(agent_id="FE", display_name="Frontend", role="FE Eng"),
        CapabilitySummary(agent_id="BE", display_name="Backend", role="BE Eng"),
    ]
    block = format_capability_block(summaries, exclude_agent_id="FE")
    assert "Backend [BE]" in block
    assert "Frontend [FE]" not in block


def test_format_block_marks_coordinator() -> None:
    summaries = [
        CapabilitySummary(agent_id="PM", display_name="PM", role="Product Manager", is_coordinator=True),
        CapabilitySummary(agent_id="FE", display_name="FE", role="FE Eng"),
    ]
    block = format_capability_block(summaries)
    assert "PM [PM] (coordinator)" in block
    assert "FE [FE]\n" in block or "FE [FE]" in block


def test_format_block_includes_capability_fields() -> None:
    summary = CapabilitySummary(
        agent_id="FE",
        display_name="FE",
        role="Frontend Engineer",
        domains=["react", "tailwind"],
        delegate_when="ui work",
        do_not_delegate="backend",
        tool_categories=["fileops", "browser"],
    )
    block = format_capability_block([summary])
    assert "domains: react, tailwind" in block
    assert "delegate_when: ui work" in block
    assert "do_not_delegate: backend" in block
    assert "tools: fileops, browser" in block


# --- cache schema validation ---


def test_cache_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        SquadMemberCapabilityCache(dsn="postgresql://x/y", schema="bad-schema!")


# --- PG-marked cache tests ---


@pytest.fixture
async def clean_capabilities(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_member_capabilities"')
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def cache(clean_capabilities: str) -> AsyncIterator[SquadMemberCapabilityCache]:
    c = SquadMemberCapabilityCache(dsn=clean_capabilities, schema=_schema())
    try:
        yield c
    finally:
        with suppress(Exception):
            await c.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_upsert_and_get(cache: SquadMemberCapabilityCache) -> None:
    summary = CapabilitySummary(
        agent_id="FE",
        display_name="Frontend",
        role="FE Eng",
        domains=["react"],
        delegate_when="ui",
        is_coordinator=False,
    )
    await cache.upsert(squad_id="build", summary=summary)
    got = await cache.get(squad_id="build", agent_id="FE")
    assert got is not None
    assert got.agent_id == "FE"
    assert got.display_name == "Frontend"
    assert got.role == "FE Eng"
    assert got.domains == ["react"]
    assert got.delegate_when == "ui"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_upsert_overwrites(cache: SquadMemberCapabilityCache) -> None:
    s1 = CapabilitySummary(agent_id="FE", display_name="A", role="r1")
    s2 = CapabilitySummary(agent_id="FE", display_name="B", role="r2")
    await cache.upsert(squad_id="build", summary=s1)
    await cache.upsert(squad_id="build", summary=s2)
    got = await cache.get(squad_id="build", agent_id="FE")
    assert got is not None
    assert got.display_name == "B"
    assert got.role == "r2"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_for_squad_orders_coordinator_first(cache: SquadMemberCapabilityCache) -> None:
    await cache.upsert(
        squad_id="build",
        summary=CapabilitySummary(agent_id="FE", display_name="Frontend", role="r"),
    )
    await cache.upsert(
        squad_id="build",
        summary=CapabilitySummary(agent_id="PM", display_name="PM", role="r", is_coordinator=True),
    )
    summaries = await cache.list_for_squad(squad_id="build")
    assert len(summaries) == 2
    assert summaries[0].agent_id == "PM"
    assert summaries[0].is_coordinator is True


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_invalidate_specific_agent(cache: SquadMemberCapabilityCache) -> None:
    await cache.upsert(squad_id="build", summary=CapabilitySummary(agent_id="FE", display_name="x", role="r"))
    await cache.upsert(squad_id="build", summary=CapabilitySummary(agent_id="BE", display_name="y", role="r"))
    deleted = await cache.invalidate(squad_id="build", agent_id="FE")
    assert deleted == 1
    remaining = await cache.list_for_squad(squad_id="build")
    assert {s.agent_id for s in remaining} == {"BE"}


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_invalidate_whole_squad(cache: SquadMemberCapabilityCache) -> None:
    await cache.upsert(squad_id="build", summary=CapabilitySummary(agent_id="FE", display_name="x", role="r"))
    await cache.upsert(squad_id="build", summary=CapabilitySummary(agent_id="BE", display_name="y", role="r"))
    deleted = await cache.invalidate(squad_id="build")
    assert deleted == 2
    assert await cache.list_for_squad(squad_id="build") == []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_expired_rows_excluded(cache: SquadMemberCapabilityCache) -> None:
    await cache.upsert(
        squad_id="build",
        summary=CapabilitySummary(agent_id="FE", display_name="x", role="r"),
        ttl_seconds=1,
    )
    await asyncio.sleep(1.5)
    fresh = await cache.list_for_squad(squad_id="build")
    assert fresh == []
    stale = await cache.list_for_squad(squad_id="build", include_expired=True)
    assert len(stale) == 1
