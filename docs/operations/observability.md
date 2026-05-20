# Observability

Koda emits Prometheus metrics, structured logs, and OpenTelemetry
traces. None of those are useful without a place to send them. This
runbook documents the minimum stack a self-hoster should run
alongside koda.

## What Koda Emits Today

| Signal | Source | How to consume |
|---|---|---|
| Prometheus metrics | `koda/services/metrics.py` — runtime, queue, cost, tools, memory, RunGraph, proposals, skills, channels, quality cockpit, ops benchmark | Scrape `:8090/metrics` |
| Structured logs | `structlog` → stdout / `~/.koda-local/var/log/` | Tail with `docker compose logs -f` or ship to Loki |
| Audit events | `audit_events` table | Query via `koda` UI or directly in Postgres |
| OpenTelemetry traces | Workers/supervisor when `OTEL_EXPORTER_OTLP_ENDPOINT` is set | Send to Tempo, Jaeger, Honeycomb, Datadog |
| Health probes | `:8090/health` (granular: per-worker + per-sidecar) | Liveness/readiness for any monitoring tool |

Prometheus labels must stay low-cardinality. Do not add raw prompt text, user
ids, chat ids, task ids, run ids, proposal ids, file paths, or message content
as labels. Use bounded labels such as `agent_id`, `status`, `reason`,
`category`, `provider`, `model`, `scenario`, `gate_id`, and `severity`.

## Top-Tier Metric Families

| Family | Example metrics | Purpose |
|---|---|---|
| Runtime and queue | `koda_active_tasks`, `koda_queue_depth`, `koda_runtime_phase_total`, `koda_runtime_cleanup_blocked_total` | Detect backpressure, stuck work, recovery, cleanup and websocket/session pressure. |
| Provider and cost | `koda_request_duration_seconds`, `koda_cost_total_usd`, `koda_provider_compatibility_state`, `koda_provider_adapter_contract_errors_total` | Track latency, spend, resume degradation and provider contract drift. |
| Memory and knowledge | `koda_memory_recall_seconds`, `koda_memory_safety_blocks_total`, `koda_memory_embedding_repairs_total`, `koda_knowledge_grounding_score` | Prove recall quality, safety blocks, embedding repair and grounded-answer quality. |
| Squads and RunGraph | `koda_squad_handoff_events_total`, `koda_squad_synthesis_gate_total`, `koda_route_outcomes_total`, `koda_run_graph_completeness_gates_total` | Prove routing, handoffs, synthesis gates and causal graph completeness. |
| Self-improvement and skills | `koda_improvement_proposal_events_total`, `koda_skill_package_events_total` | Track proposal lifecycle and local-first skill scanner/eval/install/rollback state. |
| Channels and release quality | `koda_channel_gateway_events_total`, `koda_release_quality_gates_total`, `koda_release_blockers`, `koda_trajectory_exports_total` | Prove fail-closed channel policy, release gates, blockers and redacted exports. |
| Ops benchmark | `koda_ops_benchmark_runs_total`, `koda_ops_benchmark_duration_seconds` | Track deterministic queue/runtime/channel fault benchmark runs. |

## Minimum stack for self-hosters

A single docker-compose overlay adds Prometheus + Grafana + Tempo
without disturbing the koda services. Place this file next to your
existing `docker-compose.yml`:

```yaml
# docker-compose-observability.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./docs/operations/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    ports:
      - "127.0.0.1:9090:9090"
    networks:
      - backend

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_PASSWORD:?Set GRAFANA_PASSWORD in .env}"
    volumes:
      - grafana-data:/var/lib/grafana
    ports:
      - "127.0.0.1:3001:3000"
    networks:
      - backend

  tempo:
    image: grafana/tempo:latest
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./docs/operations/tempo.yaml:/etc/tempo.yaml:ro
      - tempo-data:/var/tempo
    ports:
      - "127.0.0.1:4317:4317"   # OTLP gRPC
    networks:
      - backend

volumes:
  prometheus-data:
  grafana-data:
  tempo-data:

networks:
  backend:
    external: true
    name: koda_backend
```

Bring it up alongside the main stack:

```bash
docker compose -f docker-compose.yml -f docker-compose-observability.yml up -d
```

## Prometheus Scrape Config

The repository ships `docs/operations/prometheus.yml`. It scrapes the Koda
control plane at `app:8090` and Postgres exporter. Rust sidecars do not expose
Prometheus endpoints yet; watch their container health and Koda `/health`
instead.

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: koda-control-plane
    static_configs:
      - targets: ["app:8090"]

  - job_name: postgres
    static_configs:
      - targets: ["postgres-exporter:9187"]
```

## Recommended alerts

Eight alerts that catch most incidents:

| Alert | Condition | Severity |
|---|---|---|
| `worker_crash_loop` | `audit_events.event_type='control_plane.worker_crash_loop'` in last 5m | high |
| `provider_circuit_open` | `koda_circuit_breaker_state == 2` for 60s | high |
| `queue_depth_high` | `koda_queue_depth > 50` for 5m | medium |
| `postgres_pool_exhausted` | `pg_stat_activity{state="active"} >= max_connections * 0.9` | high |
| `run_graph_completeness_failed` | `increase(koda_run_graph_completeness_gates_total{status="failed"}[10m]) > 0` | high |
| `critical_release_blockers` | `sum(koda_release_blockers{severity=~"critical\\|high"}) > 0` | high |
| `channel_gateway_deny_spike` | `increase(koda_channel_gateway_events_total{event="policy_denied"}[15m]) > 10` | medium |
| `ops_benchmark_failed` | `increase(koda_ops_benchmark_runs_total{status!="passed"}[30m]) > 0` | medium |

## Top-Tier Roadmap Gate

The top-tier roadmap treats observability as a release gate, not an optional
afterthought. See [Scaling and Resilience](scaling-resilience-runbook.md) for
the KG-14 budgets and [Top-Tier Release Train](top-tier-release-train.md) for
the KG-15 phase closeout checklist.

Every roadmap phase must declare audit, metric, and future RunGraph coverage
for queue wait, lease acquire/loss/reap, dependency calls, breaker open, retry,
DLQ, cancellation, cleanup, and user-facing errors before the phase closes.

## Tracing (Phase 2D)

Workers and supervisors emit OTel spans automatically when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set. The hierarchy is:

```
queue_manager.process_message
  └─ tool_dispatcher.execute_tool
      └─ internal_rpc client RPC (memory, artifact, runtime-kernel, ...)
          └─ sidecar handler (Rust)
```

Set in `.env`:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
OTEL_SERVICE_NAME=koda-worker     # auto-set by koda; override per-pod if needed
```

When the env var is unset, all tracing helpers degrade to no-op
context managers — sub-µs overhead per call (verified by
`tests/benchmarks/test_bench_tracing.py`).

## Log shipping

If you want logs in Loki (queryable from the same Grafana that
shows traces and metrics), add a Promtail sidecar to compose. The
compose-observability template above doesn't include it because
many self-hosters prefer their own log pipeline (CloudWatch, GCP
Logging, Datadog, ELK).

## Granular `/health` (Phase P1-3)

The `/health` endpoint exposes:

```json
{
  "status": "healthy" | "degraded",
  "workers": [
    {"agent_id": "AGENT_A", "alive": true, "probe": {"ok": true, "latency_ms": 4, "active_tasks": 0}}
  ],
  "sidecars": [
    {"name": "memory", "ok": true, "latency_ms": 2}
  ],
  "summary": {"workers_total": 5, "workers_alive": 5, "workers_unhealthy": 0,
              "sidecars_total": 5, "sidecars_unhealthy": 0}
}
```

Ideal as the readinessProbe in Kubernetes / `healthcheck.test` in
docker-compose. The shape is stable across versions — see
`tests/test_control_plane_supervisor_health.py` for the contract.
