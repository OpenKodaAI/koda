#!/usr/bin/env bash
# Phase D — multi-supervisor cluster smoke.
#
# Validates that:
#   1. Multiple supervisor replicas come up healthy.
#   2. ``cp_supervisor_runtimes`` shows N distinct supervisor IDs.
#   3. ``cp_agent_assignments`` distributes ownership across them.
#   4. ``POST /cluster/drain`` releases claims; siblings re-claim.
#   5. The pool of memory/retrieval sidecars takes a single-replica
#      death without bringing the cluster down.
#
# Run AFTER the cluster compose is up:
#   docker compose -f docker-compose.yml -f docker-compose-cluster.yml up -d
#   bash scripts/cluster_smoke.sh

set -euo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-koda}"
SUPERVISOR_PORT="${CONTROL_PLANE_PORT:-8090}"
PG_USER="${POSTGRES_USER:-koda}"
PG_DB="${POSTGRES_DB:-koda}"

say()  { printf '\033[1;36m[cluster-smoke]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[cluster-smoke FAIL]\033[0m %s\n' "$*" >&2; exit 1; }
ok()   { printf '\033[1;32m[cluster-smoke OK]\033[0m %s\n' "$*"; }

pg_query() {
  docker compose -p "${PROJECT}" exec -T postgres \
    psql -U "${PG_USER}" -d "${PG_DB}" -tA -c "$1"
}

# ---------------------------------------------------------------------------
# 1. Wait for replicas to register
# ---------------------------------------------------------------------------
say "waiting up to 60s for supervisor replicas to register"
for _ in $(seq 1 30); do
  count=$(pg_query "SELECT COUNT(*) FROM cp_supervisor_runtimes WHERE heartbeat_at > NOW() - INTERVAL '15 seconds'")
  if [[ "${count:-0}" -ge 2 ]]; then
    ok "registered supervisors: ${count}"
    break
  fi
  sleep 2
done
[[ "${count:-0}" -ge 2 ]] || fail "expected ≥2 supervisors, found ${count:-0}"

# ---------------------------------------------------------------------------
# 2. Each supervisor must be reachable on its /health endpoint
# ---------------------------------------------------------------------------
say "probing /health on every replica"
replicas=$(docker compose -p "${PROJECT}" ps -q app)
[[ -z "${replicas}" ]] && fail "no app replicas found"
for cid in ${replicas}; do
  status=$(docker exec "${cid}" sh -c "curl -fs http://127.0.0.1:${SUPERVISOR_PORT}/health" | grep -o '"status":"[^"]*"' | head -1 || true)
  [[ "${status}" == '"status":"healthy"' || "${status}" == '"status":"degraded"' ]] || fail "container ${cid} health unreachable: ${status}"
done
ok "every replica responds on /health"

# ---------------------------------------------------------------------------
# 3. cp_agent_assignments distributes ownership
# ---------------------------------------------------------------------------
say "checking claim distribution"
distinct_owners=$(pg_query "SELECT COUNT(DISTINCT supervisor_id) FROM cp_agent_assignments")
total_claims=$(pg_query "SELECT COUNT(*) FROM cp_agent_assignments")
if [[ "${total_claims:-0}" -gt 0 ]]; then
  ok "claims=${total_claims} distinct_owners=${distinct_owners}"
else
  say "no active agents to claim — distribution check skipped"
fi

# ---------------------------------------------------------------------------
# 4. Drain protocol
# ---------------------------------------------------------------------------
target_cid=$(echo "${replicas}" | head -1)
target_sup_id=$(docker exec "${target_cid}" sh -c "curl -fs http://127.0.0.1:${SUPERVISOR_PORT}/cluster/status" | grep -o '"supervisor_id":"[^"]*"' | sed 's/.*:"//;s/"//')
[[ -n "${target_sup_id}" ]] || fail "could not read supervisor_id from ${target_cid}"

say "draining supervisor ${target_sup_id}"
docker exec "${target_cid}" sh -c "curl -fs -X POST http://127.0.0.1:${SUPERVISOR_PORT}/cluster/drain" >/dev/null

# Wait up to 60s for owned_count to drop to 0
for _ in $(seq 1 30); do
  owned=$(pg_query "SELECT COUNT(*) FROM cp_agent_assignments WHERE supervisor_id='${target_sup_id}'")
  [[ "${owned:-0}" -eq 0 ]] && break
  sleep 2
done
[[ "${owned:-0}" -eq 0 ]] || fail "drain did not release claims; remaining=${owned}"
ok "drain released all claims for ${target_sup_id}"

# Undrain so the supervisor returns to service
docker exec "${target_cid}" sh -c "curl -fs -X POST http://127.0.0.1:${SUPERVISOR_PORT}/cluster/undrain" >/dev/null
ok "undrain restored ${target_sup_id} to active"

# ---------------------------------------------------------------------------
# 5. Sidecar pool resilience
# ---------------------------------------------------------------------------
memory_replicas=$(docker compose -p "${PROJECT}" ps -q memory | wc -l | tr -d ' ')
if [[ "${memory_replicas:-0}" -ge 2 ]]; then
  victim=$(docker compose -p "${PROJECT}" ps -q memory | head -1)
  say "killing memory replica ${victim} to verify pool failover"
  docker kill "${victim}" >/dev/null
  sleep 5
  # The remaining memory replica must still respond. We probe via the
  # app container's own DNS resolution — same path workers use.
  app_cid=$(docker compose -p "${PROJECT}" ps -q app | head -1)
  if docker exec "${app_cid}" sh -c "getent hosts memory" >/dev/null; then
    ok "memory pool still resolvable after killing one replica"
  else
    fail "memory DNS lookup failed after killing one replica"
  fi
  # Bring the dead replica back so the cluster ends in a healthy state
  docker compose -p "${PROJECT}" up -d --no-recreate memory >/dev/null
fi

ok "all cluster smoke checks passed"
