"""Supervisor cluster claim/heartbeat semantics.

The cluster module is the spine of horizontal supervisor scaling. Two
supervisor instances polling the same control-plane DB MUST NOT spawn
duplicate workers for the same agent — these tests pin the SQL the
``ClusterClient`` issues so any future refactor to the claim/heartbeat
flow stays compatible with sibling supervisors built against the same
contract.

We don't exercise live Postgres here; the existing
``koda.control_plane.database.execute`` / ``fetch_all`` shape is well-
covered elsewhere. Instead we capture (sql, params) tuples and assert
the gating contract: cluster disabled → no SQL; cluster enabled but
draining → release path; happy path → SELECT FOR UPDATE SKIP LOCKED
followed by upsert.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from koda.control_plane import cluster as cluster_mod


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.calls.append((sql, params))
        # The SELECT-then-UPSERT path issues two writes (heartbeat +
        # claim upsert); both report 1 affected row in this stub.
        if "UPDATE cp_agent_assignments" in sql or "DELETE FROM cp_agent_assignments" in sql:
            return 1
        return 1

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.calls.append((sql, params))
        if "SELECT draining FROM cp_supervisor_runtimes" in sql:
            return []
        if "SELECT a.agent_id" in sql:
            agents = list(params[0]) if params and isinstance(params[0], list) else []
            return [{"agent_id": a} for a in agents]
        if "SELECT agent_id FROM cp_agent_assignments" in sql:
            return [{"agent_id": "AGENT_A"}]
        return []

    def sql_at(self, idx: int) -> str:
        return self.calls[idx][0]


def _make_client(
    *, enabled: bool = True, draining_initial: bool = False
) -> tuple[cluster_mod.ClusterClient, _Recorder]:
    rec = _Recorder()
    config = cluster_mod.ClusterConfig(
        enabled=enabled,
        supervisor_id="sup_test",
        version="v1",
        host="localhost",
        capacity=10,
        heartbeat_stale_seconds=30,
    )
    client = cluster_mod.ClusterClient(config=config)
    if draining_initial:

        def _fetch_with_draining(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
            if "SELECT draining FROM cp_supervisor_runtimes" in sql:
                return [{"draining": True}]
            return rec.fetch_all(sql, params)

        patcher = patch("koda.control_plane.cluster.fetch_all", side_effect=_fetch_with_draining)
    else:
        patcher = patch("koda.control_plane.cluster.fetch_all", side_effect=rec.fetch_all)
    patcher.start()
    patch("koda.control_plane.cluster.execute", side_effect=rec.execute).start()
    return client, rec


def _stop_patches() -> None:
    patch.stopall()


def test_disabled_cluster_returns_empty_set_and_does_no_sql() -> None:
    client, rec = _make_client(enabled=False)
    try:
        assert client.claim_agents(["AGENT_A", "AGENT_B"]) == set()
        assert client.heartbeat() == 0
        assert client.list_owned_agents() == set()
    finally:
        _stop_patches()
    assert rec.calls == []


def test_register_inserts_supervisor_runtime_row() -> None:
    client, rec = _make_client(enabled=True)
    try:
        assert client.register() is True
    finally:
        _stop_patches()
    assert any("INSERT INTO cp_supervisor_runtimes" in c[0] for c in rec.calls)


def test_claim_agents_runs_select_for_update_skip_locked() -> None:
    client, rec = _make_client(enabled=True)
    try:
        claimed = client.claim_agents(["AGENT_A", "AGENT_B"])
    finally:
        _stop_patches()
    assert claimed == {"AGENT_A", "AGENT_B"}
    # The query was rewritten as a UNION of two CTEs to satisfy PG's rule
    # that FOR UPDATE cannot apply to the nullable side of an outer join.
    # The lock now lives in the ``locked_existing`` CTE (existing rows
    # only); the ``unowned`` CTE picks candidates with no row via NOT
    # EXISTS. Both pieces must be present.
    select_sqls = [c for c in rec.calls if "WITH locked_existing AS" in c[0]]
    assert len(select_sqls) == 1
    sql = select_sqls[0][0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "NOT EXISTS" in sql
    assert any("INSERT INTO cp_agent_assignments" in c[0] for c in rec.calls)


def test_claim_returns_empty_when_draining() -> None:
    """A supervisor that is draining must NOT claim more work — it is
    on its way out and the blue/green protocol expects ownership to fall back to the
    fresh version."""
    client, _rec = _make_client(enabled=True, draining_initial=True)
    try:
        assert client.claim_agents(["AGENT_A"]) == set()
    finally:
        _stop_patches()


def test_heartbeat_returns_zero_when_disabled() -> None:
    client, _ = _make_client(enabled=False)
    try:
        assert client.heartbeat() == 0
    finally:
        _stop_patches()


def test_heartbeat_releases_when_draining() -> None:
    """When draining is true, heartbeat tears down ownership instead of
    refreshing it — that is the blue/green hand-off contract."""
    client, rec = _make_client(enabled=True, draining_initial=True)
    try:
        result = client.heartbeat()
    finally:
        _stop_patches()
    assert result >= 0
    assert any("DELETE FROM cp_agent_assignments WHERE supervisor_id" in c[0] for c in rec.calls)


def test_release_agent_targets_only_own_supervisor_id() -> None:
    client, rec = _make_client(enabled=True)
    try:
        client.release_agent("AGENT_A")
    finally:
        _stop_patches()
    delete = [c for c in rec.calls if "DELETE FROM cp_agent_assignments" in c[0]]
    assert delete
    sql, params = delete[0]
    assert "WHERE agent_id = ? AND supervisor_id = ?" in sql
    assert params == ("AGENT_A", "sup_test")


def test_set_draining_updates_supervisor_runtime_row() -> None:
    client, rec = _make_client(enabled=True)
    try:
        assert client.set_draining(True) is True
    finally:
        _stop_patches()
    update = [c for c in rec.calls if "UPDATE cp_supervisor_runtimes" in c[0]]
    assert update
    sql, params = update[0]
    assert "SET draining = ?" in sql
    assert params[0] is True


def test_list_owned_agents_returns_only_own_rows() -> None:
    client, _ = _make_client(enabled=True)
    try:
        owned = client.list_owned_agents()
    finally:
        _stop_patches()
    assert owned == {"AGENT_A"}


def test_config_from_env_defaults_to_disabled(monkeypatch: Any) -> None:
    monkeypatch.delenv("KODA_CLUSTER_MODE", raising=False)
    cfg = cluster_mod.ClusterConfig.from_env()
    assert cfg.enabled is False


def test_config_from_env_parses_cluster_mode(monkeypatch: Any) -> None:
    monkeypatch.setenv("KODA_CLUSTER_MODE", "cluster")
    monkeypatch.setenv("KODA_SUPERVISOR_ID", "sup_alpha")
    monkeypatch.setenv("KODA_SUPERVISOR_CAPACITY", "25")
    monkeypatch.setenv("KODA_CLUSTER_HEARTBEAT_STALE_SECONDS", "45")
    cfg = cluster_mod.ClusterConfig.from_env()
    assert cfg.enabled is True
    assert cfg.supervisor_id == "sup_alpha"
    assert cfg.capacity == 25
    assert cfg.heartbeat_stale_seconds == 45
