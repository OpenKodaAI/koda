# Cluster mode

Cluster mode lets a self-hoster run multiple supervisor processes
against the same Postgres + sidecars so a single host's CPU/RAM is
not the cap on agent count. Useful for medium-large internal teams
running 100+ agents.

## When to enable cluster mode

- Single host CPU consistently > 70%
- One worker pod crash-looping takes the whole stack down
- Want to roll deploys without dropping in-flight messages

If none of the above apply, **stay on single-host mode**. Cluster
mode adds operational complexity (multiple supervisor URLs, drain
protocol, heartbeat tuning) that is not free.

## Activating cluster mode

Each supervisor pod sets:

```bash
KODA_CLUSTER_MODE=cluster
KODA_SUPERVISOR_ID=sup_$(hostname)               # must be unique per pod
KODA_SUPERVISOR_CAPACITY=50                      # max agents this pod will host
KODA_CLUSTER_HEARTBEAT_STALE_SECONDS=30          # tune for your network
```

When `KODA_CLUSTER_MODE != "cluster"` (the default), supervisors
behave exactly as in single-host mode — the cluster code is dormant.

## How claims work

The supervisor cluster uses ``cp_agent_assignments`` (migration 024)
as the leader-elected work queue. On every reconcile cycle each
supervisor:

1. Lists active agents from `cp_agent_definitions`.
2. Runs `SELECT … FOR UPDATE SKIP LOCKED` against
   `cp_agent_assignments` to claim agents that are unowned OR whose
   owner's heartbeat is stale (older than
   `KODA_CLUSTER_HEARTBEAT_STALE_SECONDS`).
3. Spawns workers only for claimed agents.

A separate `_heartbeat_loop` task refreshes
`cp_agent_assignments.heartbeat_at` every `stale_seconds / 3`
(default 10s). This is decoupled from reconcile so a slow reconcile
cycle cannot push heartbeat past staleness and cause split-brain.

## Cluster status & drain endpoints

Each supervisor exposes:

| Endpoint | What |
|---|---|
| `GET /cluster/status` | Returns supervisor_id, version, host, capacity, draining flag, owned_agents list, owned_count |
| `POST /cluster/drain` | Sets `draining=true`. Next heartbeat releases all claims. |
| `POST /cluster/undrain` | Reverts the drain flag. |

These are unauthenticated by design: the control-plane port (8090)
is internal-only — put it behind a private network or VPN. They are
NOT exposed publicly under any circumstance.

## Rolling deploy (blue/green)

Already documented in [upgrade.md](upgrade.md#step-2-cluster--bluegreen-drain).
Summary:

1. Bring up new-version supervisors alongside old.
2. POST `/cluster/drain` on each old supervisor.
3. Wait for `owned_count → 0` on old (typically <30s).
4. Stop old.

In-flight messages are preserved by:
- `cp_telegram_pending_updates` — bot-gateway's durable queue
- `runtime_queue_items` — control-plane's pending queue (rolled back
  to "queued" by `pause_agent` if the worker is killed)

## Sidecar pooling

When supervisors run on multiple hosts they need a way to reach the
sidecars. Two options:

**Option A — sidecar pool (recommended).** Run N replicas of each
sidecar; workers configure comma-separated `*_GRPC_TARGET`:

```bash
MEMORY_GRPC_TARGET=memory-1.svc:50063,memory-2.svc:50063,memory-3.svc:50063
```

The Phase 2B service-discovery layer translates this to gRPC's
`ipv4:` resolver and the channel auto-load-balances with `round_robin`.

**Option B — single sidecar per host (DaemonSet pattern).** Each
supervisor host runs its own sidecar set; workers use UDS or
`127.0.0.1` targets. Simpler operationally but no failover within a
single host.

## Resource limits

Setting `KODA_AGENT_DEFAULT_MEMORY_MB` etc. enables per-workspace
cgroup v2 limits (Phase 1E + A.3 wire-up). On Linux, the supervisor
materializes a cgroup directory under `/sys/fs/cgroup/koda/ws_<id>/`
before spawning each worker and moves the worker PID into it. An
OOM kills the offending workspace cgroup, not the host.

```bash
KODA_AGENT_DEFAULT_MEMORY_MB=512        # max RSS per worker
KODA_AGENT_DEFAULT_CPU_FRACTION=0.5     # 50% of one core
KODA_AGENT_DEFAULT_PIDS_MAX=128
```

On macOS / non-Linux hosts these are no-ops. The supervisor still
boots, just without OS-level isolation.

## Observability

The cluster-mode story is incomplete without metrics:

- `koda_supervisor_owned_agents` per supervisor_id
- `koda_supervisor_heartbeat_age_seconds` — alert if > stale_seconds
- `koda_cluster_claim_attempts_total` — split-brain detector

See [observability.md](observability.md) for scrape configs.

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Two supervisors spawn the same agent | Heartbeat couldn't refresh in time | Increase `KODA_CLUSTER_HEARTBEAT_STALE_SECONDS` or fix the slow reconcile cycle |
| `owned_count` stuck at 0 across all pods | Postgres advisory locks held by a crashed connection | Restart Postgres or `pg_terminate_backend(pid)` the dead connection |
| Drain never completes | Worker is in middle of a long LLM call | Wait, or force-stop the worker; the next reconcile will re-claim |
| `cp_agent_assignments` rows for unknown supervisor_id | Old supervisor pod died without graceful shutdown | The next reconcile reaps stale rows; nothing to do |
