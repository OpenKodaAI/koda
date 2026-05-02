"""Phase 2A — supervisor cluster: leader-elected agent placement.

Today's supervisor (``koda/control_plane/supervisor.py``) is host-local.
A second instance on a sibling host would spawn a duplicate worker for
every active agent — a hard scaling block once the cluster grows past
one supervisor (P2-1).

The cluster module replaces the implicit "I own everything" with an
explicit claim recorded in ``cp_agent_assignments`` (migration 024):

- ``register_supervisor(supervisor_id, version, host, capacity)``
  inserts a row in ``cp_supervisor_runtimes`` so peers can see this
  process exists.
- ``claim_agents(supervisor_id, candidates, capacity)`` runs a single
  ``SELECT … FOR UPDATE SKIP LOCKED`` to claim agents that have no
  current owner OR whose owner's heartbeat is stale. Returns the
  agent_ids the caller is now responsible for.
- ``heartbeat(supervisor_id)`` refreshes ``heartbeat_at`` on every
  active claim. Concurrent supervisors that fail to heartbeat lose
  their claims to the next ``claim_agents`` call.
- ``release_agent(...)`` and ``release_all_for_supervisor(...)``
  explicitly drop ownership, used by the blue/green drain protocol
  (Phase 2E) and clean shutdown.
- ``set_draining(supervisor_id, draining)`` flips the supervisor into
  drain mode so it releases on next heartbeat instead of refreshing.

The reconcile loop in ``ControlPlaneSupervisor`` only touches agents
present in the claim set when ``KODA_CLUSTER_MODE=cluster`` — the
single-host default behavior is preserved when the flag is unset.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass, field

from koda.control_plane.database import execute, fetch_all, now_iso
from koda.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ClusterConfig:
    enabled: bool
    supervisor_id: str
    version: str
    host: str
    capacity: int
    heartbeat_stale_seconds: int

    @staticmethod
    def from_env() -> ClusterConfig:
        mode = (os.environ.get("KODA_CLUSTER_MODE") or "single").strip().lower()
        enabled = mode == "cluster"
        sup_id = (os.environ.get("KODA_SUPERVISOR_ID") or "").strip() or f"sup_{uuid.uuid4().hex[:12]}"
        version = (os.environ.get("KODA_BUILD_VERSION") or "").strip()
        host = (os.environ.get("HOSTNAME") or "").strip() or socket.gethostname()
        try:
            capacity = max(0, int(os.environ.get("KODA_SUPERVISOR_CAPACITY") or 0))
        except ValueError:
            capacity = 0
        try:
            stale = max(5, int(os.environ.get("KODA_CLUSTER_HEARTBEAT_STALE_SECONDS") or 30))
        except ValueError:
            stale = 30
        return ClusterConfig(
            enabled=enabled,
            supervisor_id=sup_id,
            version=version,
            host=host,
            capacity=capacity,
            heartbeat_stale_seconds=stale,
        )


@dataclass(slots=True)
class ClusterClient:
    """Thin wrapper around the cluster SQL surface.

    All methods are best-effort and never raise — a transient DB
    failure should make the supervisor degrade gracefully (skip claim
    this round) rather than crash the whole process.
    """

    config: ClusterConfig
    _registered: bool = field(default=False, init=False)

    def register(self) -> bool:
        if not self.config.enabled:
            return False
        try:
            execute(
                """
                INSERT INTO cp_supervisor_runtimes
                    (supervisor_id, version, host, started_at, heartbeat_at, draining, capacity)
                VALUES (?, ?, ?, ?, ?, FALSE, ?)
                ON CONFLICT (supervisor_id) DO UPDATE
                SET version = excluded.version,
                    host = excluded.host,
                    started_at = excluded.started_at,
                    heartbeat_at = excluded.heartbeat_at,
                    draining = FALSE,
                    capacity = excluded.capacity
                """,
                (
                    self.config.supervisor_id,
                    self.config.version,
                    self.config.host,
                    now_iso(),
                    now_iso(),
                    int(self.config.capacity),
                ),
            )
            self._registered = True
            return True
        except Exception:
            log.exception("cluster_register_failed", supervisor_id=self.config.supervisor_id)
            return False

    def is_draining(self) -> bool:
        if not self.config.enabled:
            return False
        try:
            rows = fetch_all(
                "SELECT draining FROM cp_supervisor_runtimes WHERE supervisor_id = ?",
                (self.config.supervisor_id,),
            )
        except Exception:
            log.exception("cluster_is_draining_failed")
            return False
        if not rows:
            return False
        row = rows[0]
        value = row.get("draining") if isinstance(row, dict) else None
        return bool(value)

    def claim_agents(self, candidates: list[str]) -> set[str]:
        """Atomically claim ownership of agents this supervisor wants.

        ``candidates`` is the active agent set the supervisor would
        like to host (from ``manager.list_agents``). Returns the
        subset whose ``cp_agent_assignments`` row this supervisor now
        owns.

        The query is two-step: a SELECT FOR UPDATE SKIP LOCKED to
        identify rows that are unowned or whose owner is stale, then a
        single UPSERT batch claiming those rows. We deliberately do
        NOT lock the entire candidate set — sibling supervisors race
        for unowned/stale rows in parallel without blocking each other
        on already-owned agents.
        """
        if not self.config.enabled or not candidates:
            return set()
        if self.is_draining():
            return set()
        cap = self.config.capacity
        # Build candidate list as ``ANY($1)`` so the IN clause stays
        # stable across batch sizes.
        candidates = list(candidates)
        try:
            rows = fetch_all(
                f"""
                SELECT a.agent_id
                FROM unnest(?::text[]) AS a(agent_id)
                LEFT JOIN cp_agent_assignments existing
                    ON existing.agent_id = a.agent_id
                WHERE existing.agent_id IS NULL
                   OR existing.heartbeat_at < (NOW() - INTERVAL '1 second' * ?)
                   OR existing.supervisor_id = ?
                ORDER BY existing.heartbeat_at NULLS FIRST, a.agent_id
                {f"LIMIT {int(cap)}" if cap > 0 else ""}
                FOR UPDATE OF existing SKIP LOCKED
                """,
                (candidates, int(self.config.heartbeat_stale_seconds), self.config.supervisor_id),
            )
        except Exception:
            log.exception("cluster_claim_select_failed")
            return set()
        target = [str(row.get("agent_id")) for row in rows if isinstance(row, dict) and row.get("agent_id")]
        if not target:
            return set()
        try:
            execute(
                """
                INSERT INTO cp_agent_assignments
                    (agent_id, supervisor_id, claimed_at, heartbeat_at, version, draining)
                SELECT a, ?, ?, ?, 0, FALSE FROM unnest(?::text[]) AS a
                ON CONFLICT (agent_id) DO UPDATE
                SET supervisor_id = excluded.supervisor_id,
                    claimed_at = excluded.claimed_at,
                    heartbeat_at = excluded.heartbeat_at,
                    draining = FALSE
                """,
                (self.config.supervisor_id, now_iso(), now_iso(), target),
            )
        except Exception:
            log.exception("cluster_claim_upsert_failed")
            return set()
        return set(target)

    def heartbeat(self) -> int:
        """Refresh ``heartbeat_at`` on every active claim AND on the
        supervisor row. Returns the number of assignment rows touched.

        Draining supervisors release instead of refreshing — the
        Phase 2E blue/green protocol relies on this to hand work over
        to the new version without losing in-flight messages.
        """
        if not self.config.enabled:
            return 0
        if self.is_draining():
            return self.release_all_for_supervisor()
        try:
            execute(
                "UPDATE cp_supervisor_runtimes SET heartbeat_at = ? WHERE supervisor_id = ?",
                (now_iso(), self.config.supervisor_id),
            )
            return int(
                execute(
                    """
                    UPDATE cp_agent_assignments
                    SET heartbeat_at = ?
                    WHERE supervisor_id = ?
                    """,
                    (now_iso(), self.config.supervisor_id),
                )
                or 0
            )
        except Exception:
            log.exception("cluster_heartbeat_failed")
            return 0

    def release_agent(self, agent_id: str) -> bool:
        if not self.config.enabled:
            return False
        try:
            return bool(
                execute(
                    "DELETE FROM cp_agent_assignments WHERE agent_id = ? AND supervisor_id = ?",
                    (agent_id, self.config.supervisor_id),
                )
            )
        except Exception:
            log.exception("cluster_release_agent_failed", agent_id=agent_id)
            return False

    def release_all_for_supervisor(self) -> int:
        if not self.config.enabled:
            return 0
        try:
            return int(
                execute(
                    "DELETE FROM cp_agent_assignments WHERE supervisor_id = ?",
                    (self.config.supervisor_id,),
                )
                or 0
            )
        except Exception:
            log.exception("cluster_release_all_failed")
            return 0

    def set_draining(self, draining: bool) -> bool:
        if not self.config.enabled:
            return False
        try:
            execute(
                "UPDATE cp_supervisor_runtimes SET draining = ?, heartbeat_at = ? WHERE supervisor_id = ?",
                (bool(draining), now_iso(), self.config.supervisor_id),
            )
            return True
        except Exception:
            log.exception("cluster_set_draining_failed")
            return False

    def list_owned_agents(self) -> set[str]:
        if not self.config.enabled:
            return set()
        try:
            rows = fetch_all(
                "SELECT agent_id FROM cp_agent_assignments WHERE supervisor_id = ?",
                (self.config.supervisor_id,),
            )
        except Exception:
            log.exception("cluster_list_owned_failed")
            return set()
        return {str(row.get("agent_id")) for row in rows if isinstance(row, dict) and row.get("agent_id")}
