"""Integration tests for koda.control_plane.cluster.ClusterClient against a
real PostgreSQL container.

Pinned guarantees:

  * register() upserts the supervisor row and survives repeated calls.
  * claim_agents() takes ownership of unowned candidates AND idle-claims of
    other supervisors whose heartbeat is stale.
  * heartbeat() refreshes heartbeat_at on every active claim.
  * release_agent() / release_all_for_supervisor() drop ownership.
  * set_draining(True) → next heartbeat releases all claims (Phase 2E
    blue/green protocol).
  * is_draining() reflects the persisted state.
  * Two supervisors race for the same candidate set → SKIP LOCKED partitions
    them; no double-claim.
  * Disabled cluster mode (KODA_CLUSTER_MODE!=cluster) makes every method a
    safe no-op.
"""

from __future__ import annotations

import contextlib
import importlib
import json as _json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest

from koda.control_plane.cluster import ClusterClient, ClusterConfig

pytestmark = [pytest.mark.postgres]


@pytest.fixture
async def cluster_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """Migrated DSN with cp_* tables truncated and primary modules reloaded.

    Same pattern as test_runtime_postgres_isolation: reload knowledge config
    so KNOWLEDGE_V2_POSTGRES_DSN is honored, install JSONB codec for any
    tables that need it (cluster tables don't, but some adjacent ones might
    be touched by the control-plane store), and reset the cp_* tables.
    """
    import koda.knowledge.config as kn_config

    importlib.reload(kn_config)

    from koda.knowledge.v2 import common as common_mod

    if hasattr(common_mod, "_SHARED_BACKENDS"):
        common_mod._SHARED_BACKENDS.clear()  # type: ignore[attr-defined]

    from koda.state import primary as primary_mod

    original_install = primary_mod._install_timestamptz_str_codec

    async def _install_codecs(conn: Any) -> None:
        await original_install(conn)
        with contextlib.suppress(Exception):
            await conn.set_type_codec(
                "jsonb",
                encoder=lambda v: v if isinstance(v, str) else _json.dumps(v, default=str),
                decoder=lambda v: _json.loads(v) if v else None,
                schema="pg_catalog",
                format="text",
            )

    monkeypatch.setattr(primary_mod, "_install_timestamptz_str_codec", _install_codecs)

    conn = await asyncpg.connect(migrated_postgres)
    try:
        for table in ("cp_agent_assignments", "cp_supervisor_runtimes"):
            await conn.execute(f'TRUNCATE TABLE knowledge_v2."{table}" RESTART IDENTITY CASCADE')
    finally:
        await conn.close()

    try:
        yield migrated_postgres
    finally:
        if hasattr(common_mod, "_SHARED_BACKENDS"):
            common_mod._SHARED_BACKENDS.clear()  # type: ignore[attr-defined]


def _make_config(supervisor_id: str, *, capacity: int = 0, stale_seconds: int = 30) -> ClusterConfig:
    return ClusterConfig(
        enabled=True,
        supervisor_id=supervisor_id,
        version="test",
        host="localhost",
        capacity=capacity,
        heartbeat_stale_seconds=stale_seconds,
    )


async def _direct_query(dsn: str, sql: str, *params: Any) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetch(sql, *params)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# ClusterConfig.from_env — pure logic
# ---------------------------------------------------------------------------


def test_config_from_env_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KODA_CLUSTER_MODE", raising=False)
    cfg = ClusterConfig.from_env()
    assert cfg.enabled is False


def test_config_from_env_enabled_when_mode_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    cfg = ClusterConfig.from_env()
    assert cfg.enabled is True


def test_config_from_env_supervisor_id_generated_if_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KODA_SUPERVISOR_ID", raising=False)
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    cfg = ClusterConfig.from_env()
    assert cfg.supervisor_id.startswith("sup_")
    assert len(cfg.supervisor_id) > len("sup_")


def test_config_from_env_explicit_supervisor_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_SUPERVISOR_ID", "supA")
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    cfg = ClusterConfig.from_env()
    assert cfg.supervisor_id == "supA"


def test_config_from_env_capacity_clamps_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    monkeypatch.setenv("KODA_SUPERVISOR_CAPACITY", "-5")
    cfg = ClusterConfig.from_env()
    assert cfg.capacity == 0


def test_config_from_env_capacity_invalid_falls_back_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    monkeypatch.setenv("KODA_SUPERVISOR_CAPACITY", "not-an-int")
    cfg = ClusterConfig.from_env()
    assert cfg.capacity == 0


def test_config_from_env_stale_seconds_clamps_at_5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    monkeypatch.setenv("KODA_CLUSTER_HEARTBEAT_STALE_SECONDS", "1")
    cfg = ClusterConfig.from_env()
    assert cfg.heartbeat_stale_seconds == 5  # min floor


def test_config_from_env_stale_seconds_invalid_default_30(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    monkeypatch.setenv("KODA_CLUSTER_HEARTBEAT_STALE_SECONDS", "not-a-number")
    cfg = ClusterConfig.from_env()
    assert cfg.heartbeat_stale_seconds == 30


# ---------------------------------------------------------------------------
# Disabled-mode is a safe no-op (no DB calls)
# ---------------------------------------------------------------------------


def test_disabled_register_returns_false() -> None:
    client = ClusterClient(config=ClusterConfig(
        enabled=False, supervisor_id="sup", version="", host="h", capacity=0, heartbeat_stale_seconds=30,
    ))
    assert client.register() is False


def test_disabled_claim_returns_empty_set() -> None:
    client = ClusterClient(config=ClusterConfig(
        enabled=False, supervisor_id="sup", version="", host="h", capacity=0, heartbeat_stale_seconds=30,
    ))
    assert client.claim_agents(["a", "b"]) == set()


def test_disabled_heartbeat_returns_zero() -> None:
    client = ClusterClient(config=ClusterConfig(
        enabled=False, supervisor_id="sup", version="", host="h", capacity=0, heartbeat_stale_seconds=30,
    ))
    assert client.heartbeat() == 0


def test_disabled_release_all_returns_zero() -> None:
    client = ClusterClient(config=ClusterConfig(
        enabled=False, supervisor_id="sup", version="", host="h", capacity=0, heartbeat_stale_seconds=30,
    ))
    assert client.release_all_for_supervisor() == 0


def test_disabled_list_owned_agents_returns_empty() -> None:
    client = ClusterClient(config=ClusterConfig(
        enabled=False, supervisor_id="sup", version="", host="h", capacity=0, heartbeat_stale_seconds=30,
    ))
    assert client.list_owned_agents() == set()


def test_disabled_set_draining_returns_false() -> None:
    client = ClusterClient(config=ClusterConfig(
        enabled=False, supervisor_id="sup", version="", host="h", capacity=0, heartbeat_stale_seconds=30,
    ))
    assert client.set_draining(True) is False


# ---------------------------------------------------------------------------
# register() — upsert + repeated calls
# ---------------------------------------------------------------------------


async def test_register_upserts_supervisor_row(cluster_db: str) -> None:
    client = ClusterClient(config=_make_config("supA", capacity=4))
    assert client.register() is True
    rows = await _direct_query(
        cluster_db,
        'SELECT supervisor_id, capacity, draining FROM knowledge_v2.cp_supervisor_runtimes WHERE supervisor_id = $1',
        "supA",
    )
    assert len(rows) == 1
    assert rows[0]["supervisor_id"] == "supA"
    assert rows[0]["capacity"] == 4
    assert rows[0]["draining"] is False


async def test_register_idempotent(cluster_db: str) -> None:
    client = ClusterClient(config=_make_config("supA", capacity=2))
    client.register()
    client.register()
    rows = await _direct_query(
        cluster_db,
        'SELECT count(*)::int AS n FROM knowledge_v2.cp_supervisor_runtimes WHERE supervisor_id = $1',
        "supA",
    )
    assert rows[0]["n"] == 1


async def test_register_resets_draining(cluster_db: str) -> None:
    """Calling register() must clear the draining flag (used during restart)."""
    client = ClusterClient(config=_make_config("supA", capacity=2))
    client.register()
    client.set_draining(True)
    assert client.is_draining() is True
    client.register()
    assert client.is_draining() is False


# ---------------------------------------------------------------------------
# claim_agents() — happy path
#
# Implementation note: the SELECT-side query is split into two CTEs to
# satisfy PostgreSQL's restriction that FOR UPDATE cannot apply to the
# nullable side of an outer join. ``locked_existing`` locks rows that
# already exist (stale or self-owned) with FOR UPDATE SKIP LOCKED;
# ``unowned`` picks candidates that have no row yet via NOT EXISTS
# (no row to lock — the subsequent UPSERT serializes via the agent_id
# PRIMARY KEY).
# ---------------------------------------------------------------------------


async def test_claim_agents_takes_unowned_candidates(cluster_db: str) -> None:
    client = ClusterClient(config=_make_config("supA"))
    client.register()
    claimed = client.claim_agents(["agent_x", "agent_y", "agent_z"])
    assert claimed == {"agent_x", "agent_y", "agent_z"}
    rows = await _direct_query(
        cluster_db,
        'SELECT agent_id, supervisor_id FROM knowledge_v2.cp_agent_assignments ORDER BY agent_id',
    )
    assert sorted(r["agent_id"] for r in rows) == ["agent_x", "agent_y", "agent_z"]
    assert all(r["supervisor_id"] == "supA" for r in rows)


async def test_claim_agents_empty_input_returns_empty(cluster_db: str) -> None:
    client = ClusterClient(config=_make_config("supA"))
    client.register()
    assert client.claim_agents([]) == set()


async def test_claim_agents_respects_capacity_limit(cluster_db: str) -> None:
    """capacity=2 → only 2 of the 5 candidates are claimed."""
    client = ClusterClient(config=_make_config("supA", capacity=2))
    client.register()
    claimed = client.claim_agents(["a", "b", "c", "d", "e"])
    assert len(claimed) == 2
    rows = await _direct_query(
        cluster_db,
        'SELECT count(*)::int AS n FROM knowledge_v2.cp_agent_assignments WHERE supervisor_id = $1',
        "supA",
    )
    assert rows[0]["n"] == 2


async def test_claim_agents_ignores_already_owned_by_other_when_fresh(cluster_db: str) -> None:
    """If supA owns agent_x with a fresh heartbeat, supB cannot claim it."""
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_b = ClusterClient(config=_make_config("supB"))
    sup_a.register()
    sup_b.register()
    sup_a.claim_agents(["agent_x", "agent_y"])

    # supB tries to claim what supA owns. Both are fresh → supA wins.
    claimed_b = sup_b.claim_agents(["agent_x", "agent_y", "agent_z"])
    assert claimed_b == {"agent_z"}
    # Verify ownership untouched.
    rows = await _direct_query(
        cluster_db,
        'SELECT agent_id, supervisor_id FROM knowledge_v2.cp_agent_assignments ORDER BY agent_id',
    )
    owners = {r["agent_id"]: r["supervisor_id"] for r in rows}
    assert owners == {"agent_x": "supA", "agent_y": "supA", "agent_z": "supB"}


async def test_claim_agents_reclaims_stale_heartbeat(cluster_db: str) -> None:
    """A claim with stale heartbeat is reclaimable by a peer."""
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_b = ClusterClient(config=_make_config("supB", stale_seconds=5))
    sup_a.register()
    sup_b.register()
    sup_a.claim_agents(["agent_x"])

    # Manually backdate supA's heartbeat past the stale threshold.
    stale = datetime.now(UTC) - timedelta(seconds=60)
    conn = await asyncpg.connect(cluster_db)
    try:
        await conn.execute(
            'UPDATE knowledge_v2.cp_agent_assignments SET heartbeat_at = $1 WHERE agent_id = $2',
            stale, "agent_x",
        )
    finally:
        await conn.close()

    claimed = sup_b.claim_agents(["agent_x"])
    assert claimed == {"agent_x"}
    rows = await _direct_query(
        cluster_db,
        'SELECT supervisor_id FROM knowledge_v2.cp_agent_assignments WHERE agent_id = $1',
        "agent_x",
    )
    assert rows[0]["supervisor_id"] == "supB"


async def test_claim_agents_reclaims_own_existing_assignment(cluster_db: str) -> None:
    """A supervisor can re-affirm its own claim — the WHERE clause matches own id."""
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_a.register()
    sup_a.claim_agents(["agent_x"])
    # Re-claim is idempotent.
    again = sup_a.claim_agents(["agent_x"])
    assert again == {"agent_x"}


# ---------------------------------------------------------------------------
# heartbeat() — refreshes timestamps
# ---------------------------------------------------------------------------


async def test_heartbeat_refreshes_assignment_timestamp(cluster_db: str) -> None:
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    sup.claim_agents(["agent_x"])

    before = await _direct_query(
        cluster_db,
        'SELECT heartbeat_at FROM knowledge_v2.cp_agent_assignments WHERE agent_id = $1',
        "agent_x",
    )
    initial_ts = before[0]["heartbeat_at"]

    # Backdate the row a bit so the refresh is observable.
    conn = await asyncpg.connect(cluster_db)
    try:
        await conn.execute(
            'UPDATE knowledge_v2.cp_agent_assignments SET heartbeat_at = $1 WHERE agent_id = $2',
            datetime.now(UTC) - timedelta(seconds=10), "agent_x",
        )
    finally:
        await conn.close()

    refreshed = sup.heartbeat()
    assert refreshed >= 1

    after = await _direct_query(
        cluster_db,
        'SELECT heartbeat_at FROM knowledge_v2.cp_agent_assignments WHERE agent_id = $1',
        "agent_x",
    )
    assert after[0]["heartbeat_at"] > initial_ts - timedelta(seconds=15)
    assert after[0]["heartbeat_at"] >= datetime.now(UTC) - timedelta(seconds=2)


async def test_heartbeat_returns_zero_when_no_claims(cluster_db: str) -> None:
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    assert sup.heartbeat() == 0


# ---------------------------------------------------------------------------
# Draining: heartbeat releases all claims
# ---------------------------------------------------------------------------


async def test_draining_heartbeat_releases_all(cluster_db: str) -> None:
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    sup.claim_agents(["a", "b", "c"])
    assert sup.list_owned_agents() == {"a", "b", "c"}

    sup.set_draining(True)
    released = sup.heartbeat()
    assert released == 3
    assert sup.list_owned_agents() == set()


async def test_is_draining_reflects_persisted_state(cluster_db: str) -> None:
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    assert sup.is_draining() is False
    sup.set_draining(True)
    assert sup.is_draining() is True
    sup.set_draining(False)
    assert sup.is_draining() is False


async def test_draining_supervisor_cannot_claim(cluster_db: str) -> None:
    """A draining supervisor returns empty from claim_agents()."""
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    sup.set_draining(True)
    assert sup.claim_agents(["x"]) == set()


# ---------------------------------------------------------------------------
# release_agent / release_all_for_supervisor
# ---------------------------------------------------------------------------


async def test_release_agent_drops_one_claim(cluster_db: str) -> None:
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    sup.claim_agents(["a", "b"])
    assert sup.release_agent("a") is True
    assert sup.list_owned_agents() == {"b"}


async def test_release_agent_returns_false_when_not_owned(cluster_db: str) -> None:
    """release_agent only drops the row when (agent_id, supervisor_id) matches
    the caller; a peer cannot release another supervisor's claim."""
    sup = ClusterClient(config=_make_config("supA"))
    sup.register()
    sup.claim_agents(["a"])
    # supB cannot release supA's claim.
    sup_b = ClusterClient(config=_make_config("supB"))
    sup_b.register()
    assert sup_b.release_agent("a") is False


async def test_release_all_for_supervisor_only_drops_own(cluster_db: str) -> None:
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_b = ClusterClient(config=_make_config("supB"))
    sup_a.register()
    sup_b.register()
    sup_a.claim_agents(["x", "y"])
    sup_b.claim_agents(["z"])
    released = sup_a.release_all_for_supervisor()
    assert released == 2
    rows = await _direct_query(
        cluster_db,
        'SELECT agent_id FROM knowledge_v2.cp_agent_assignments ORDER BY agent_id',
    )
    assert [r["agent_id"] for r in rows] == ["z"]


# ---------------------------------------------------------------------------
# list_owned_agents — agent_id set scoped per supervisor
# ---------------------------------------------------------------------------


async def test_list_owned_agents_scoped_per_supervisor(cluster_db: str) -> None:
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_b = ClusterClient(config=_make_config("supB"))
    sup_a.register()
    sup_b.register()
    sup_a.claim_agents(["a1", "a2"])
    sup_b.claim_agents(["b1"])
    assert sup_a.list_owned_agents() == {"a1", "a2"}
    assert sup_b.list_owned_agents() == {"b1"}


# ---------------------------------------------------------------------------
# Concurrency — race two supervisors over a stale candidate set
# ---------------------------------------------------------------------------


async def test_two_sequential_supervisors_partition_stale_pool(cluster_db: str) -> None:
    """When two supervisors call claim_agents sequentially against the same
    stale pool, the UPSERT side of the second call rebinds the row to the
    later supervisor (last-write-wins). The fix's SKIP LOCKED only matters
    for concurrent transactions; for sequential calls, the second SELECT
    sees the rows as own (because the first call rebound them — wait, no:
    the first call rebound them to supC, so the second call sees them as
    owned-by-supC and not stale, which means the OR clause matches only
    if supD is the owner — it's not. So supD claims nothing. This pins the
    sequential semantic.
    """
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_a.register()
    sup_a.claim_agents(["a", "b", "c", "d"])

    conn = await asyncpg.connect(cluster_db)
    try:
        await conn.execute(
            "UPDATE knowledge_v2.cp_agent_assignments SET heartbeat_at = $1 "
            "WHERE agent_id = ANY($2::text[])",
            datetime.now(UTC) - timedelta(seconds=60),
            ["a", "b", "c", "d"],
        )
    finally:
        await conn.close()

    sup_c = ClusterClient(config=_make_config("supC", stale_seconds=5))
    sup_d = ClusterClient(config=_make_config("supD", stale_seconds=5))
    sup_c.register()
    sup_d.register()

    candidates = ["a", "b", "c", "d"]
    claimed_c = sup_c.claim_agents(list(candidates))
    # supC just refreshed all four rows. supD's claim now sees fresh
    # heartbeats owned by supC — NOT stale, NOT own — so the locked_existing
    # CTE returns nothing and unowned returns nothing. supD claims none.
    claimed_d = sup_d.claim_agents(list(candidates))

    assert claimed_c == set(candidates), f"first supervisor failed to take stale pool: {claimed_c}"
    assert claimed_d == set(), f"second supervisor stole fresh claims: {claimed_d}"

    # Persisted state confirms supC owns everything; nothing stayed with supA.
    rows = await _direct_query(
        cluster_db,
        "SELECT agent_id, supervisor_id FROM knowledge_v2.cp_agent_assignments "
        "WHERE agent_id = ANY($1::text[]) ORDER BY agent_id",
        list(candidates),
    )
    persisted = {r["agent_id"]: r["supervisor_id"] for r in rows}
    assert all(v == "supC" for v in persisted.values()), persisted
    assert "supA" not in persisted.values()


async def test_concurrent_threads_no_double_claim_via_skip_locked(cluster_db: str) -> None:
    """Two threads holding open transactions race for stale rows.

    We open two raw asyncpg connections and run the SELECT FOR UPDATE
    SKIP LOCKED side of the cluster fix concurrently. The first
    transaction acquires the row locks; the second sees them as locked
    and skips. This proves the SKIP LOCKED guarantee at the SQL level
    (independent of cluster.py's higher-level orchestration).
    """
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_a.register()
    sup_a.claim_agents(["x1", "x2", "x3"])

    conn_setup = await asyncpg.connect(cluster_db)
    try:
        await conn_setup.execute(
            "UPDATE knowledge_v2.cp_agent_assignments SET heartbeat_at = $1 "
            "WHERE agent_id = ANY($2::text[])",
            datetime.now(UTC) - timedelta(seconds=60),
            ["x1", "x2", "x3"],
        )
    finally:
        await conn_setup.close()

    # Same SELECT shape the cluster fix issues, run inside an explicit
    # transaction on TWO connections so the locks visibly partition.
    select_sql = """
        SELECT existing.agent_id
        FROM knowledge_v2.cp_agent_assignments existing
        WHERE existing.agent_id = ANY($1::text[])
          AND existing.heartbeat_at < (NOW() - INTERVAL '60 seconds')
        FOR UPDATE SKIP LOCKED
    """

    conn_p = await asyncpg.connect(cluster_db)
    conn_q = await asyncpg.connect(cluster_db)
    try:
        # Open transactions on both connections.
        tx_p = conn_p.transaction()
        await tx_p.start()
        # First grabs the locks for everything.
        rows_p = await conn_p.fetch(select_sql, ["x1", "x2", "x3"])
        # Second runs while first is uncommitted — must see empty due to SKIP LOCKED.
        tx_q = conn_q.transaction()
        await tx_q.start()
        rows_q = await conn_q.fetch(select_sql, ["x1", "x2", "x3"])
        await tx_p.commit()
        await tx_q.commit()
    finally:
        await conn_p.close()
        await conn_q.close()

    set_p = {r["agent_id"] for r in rows_p}
    set_q = {r["agent_id"] for r in rows_q}
    assert set_p == {"x1", "x2", "x3"}, f"first txn missed locks: {set_p}"
    assert set_q == set(), f"SKIP LOCKED leaked: second txn saw {set_q}"


async def test_unowned_and_stale_partition_combine_under_capacity(cluster_db: str) -> None:
    """Mix of unowned + stale candidates with capacity > total — every one is claimed."""
    # 3 unowned + 2 stale that supA used to own
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_a.register()
    sup_a.claim_agents(["s1", "s2"])
    conn = await asyncpg.connect(cluster_db)
    try:
        await conn.execute(
            "UPDATE knowledge_v2.cp_agent_assignments SET heartbeat_at = $1 "
            "WHERE agent_id = ANY($2::text[])",
            datetime.now(UTC) - timedelta(seconds=60),
            ["s1", "s2"],
        )
    finally:
        await conn.close()

    sup_b = ClusterClient(config=_make_config("supB", capacity=10, stale_seconds=5))
    sup_b.register()
    claimed = sup_b.claim_agents(["u1", "u2", "u3", "s1", "s2"])
    assert claimed == {"u1", "u2", "u3", "s1", "s2"}


async def test_unowned_preferred_over_stale_under_capacity_pressure(cluster_db: str) -> None:
    """When capacity caps the result, the unowned candidates win — they are
    preferred (priority=0 in the UNION; matches the original NULLS FIRST
    semantic of the buggy query)."""
    sup_a = ClusterClient(config=_make_config("supA"))
    sup_a.register()
    sup_a.claim_agents(["stale1", "stale2"])
    conn = await asyncpg.connect(cluster_db)
    try:
        await conn.execute(
            "UPDATE knowledge_v2.cp_agent_assignments SET heartbeat_at = $1 "
            "WHERE agent_id = ANY($2::text[])",
            datetime.now(UTC) - timedelta(seconds=60),
            ["stale1", "stale2"],
        )
    finally:
        await conn.close()

    # supB has capacity=2 and 2 unowned + 2 stale candidates → only the
    # 2 unowned should be claimed.
    sup_b = ClusterClient(config=_make_config("supB", capacity=2, stale_seconds=5))
    sup_b.register()
    claimed = sup_b.claim_agents(["unowned1", "unowned2", "stale1", "stale2"])
    assert claimed == {"unowned1", "unowned2"}, f"expected unowned preferred, got {claimed}"
