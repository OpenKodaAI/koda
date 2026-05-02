# Incident response playbooks

Pre-written procedures for the incidents most likely to interrupt a
self-hosted koda. Skim these before they happen.

Each playbook is structured: **symptom → likely cause → diagnostic
commands → fix → audit trail**.

## 1. Worker is crash-looping

**Symptom**: `/health` reports `degraded` with one or more
`workers_unhealthy > 0`.

**Likely cause**: handler raised on every restart (typo in deploy,
missing migration, exhausted provider quota).

**Diagnose**:
```bash
# Audit log shows the crash-loop event automatically (Phase P1-4)
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT timestamp, event_type, details_json::text FROM audit_events \
        WHERE event_type = 'control_plane.worker_crash_loop' \
        ORDER BY timestamp DESC LIMIT 10;"

# Worker logs around the crash
docker compose logs app --since 10m | grep -E "worker.*crash|FATAL|ERROR"
```

**Fix**:
```bash
# Pause the agent so the supervisor stops re-spawning
curl -X POST http://127.0.0.1:8090/api/control-plane/agents/<AGENT_ID>/pause \
    -H "Authorization: Bearer $CONTROL_PLANE_API_TOKEN"

# Once root cause is resolved
curl -X POST http://127.0.0.1:8090/api/control-plane/agents/<AGENT_ID>/activate \
    -H "Authorization: Bearer $CONTROL_PLANE_API_TOKEN"
```

**Audit**: `control_plane.agent_paused` and `control_plane.agent_activated`
events are emitted automatically.

## 2. Provider key compromised / leaked

**Symptom**: GitHub bot pings you that an API key is on a public
gist; or Stripe alerts unusual provider spend.

**Diagnose**:
```bash
# Find which agents use the key
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT scope_id FROM cp_secret_values \
        WHERE secret_key LIKE '%API_KEY%' AND updated_at > NOW() - INTERVAL '30 days';"
```

**Fix**:
1. Rotate the key at the provider (e.g. revoke + reissue at OpenAI).
2. Update the secret in the control-plane UI (System → Connections).
3. Restart affected agents to pick up the new value.

**Audit**: each secret rotation logs `audit_events` row with
`event_type='secret.rotated'`.

## 3. Postgres connection pool exhausted

**Symptom**: Workers timeout at startup. Logs show
`asyncpg.exceptions.ConnectionDoesNotExistError` or
`pool exhausted`.

**Diagnose**:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT pid, state, wait_event_type, query \
        FROM pg_stat_activity WHERE state != 'idle' ORDER BY backend_start;"
```

**Fix**:
- If a long query is hung, `SELECT pg_terminate_backend(pid)` it.
- If the count of active connections is at `max_connections`, either:
  - Lower `KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE` per worker, OR
  - Raise Postgres `max_connections` and restart, OR
  - Add pgbouncer in front (recommended at >50 workers).

**Prevention**: with `KODA_CLUSTER_MODE=cluster`, set
`KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE=ceil(MAX_CONCURRENCY/4)` so N
workers × pool_size doesn't exceed `max_connections`.

## 4. Sidecar (memory / artifact / retrieval / runtime-kernel) hung

**Symptom**: Workers feel slow. `/health` shows
`sidecars_unhealthy > 0`. Phase A.2 circuit breaker is OPEN for the
hung sidecar (visible in worker logs as
`circuit_breaker_opened name=memory_engine`).

**Diagnose**:
```bash
# Which sidecar?
curl -fs http://127.0.0.1:8090/health | jq '.sidecars[] | select(.ok == false)'

# Container state
docker compose ps memory artifact retrieval runtime-kernel
```

**Fix**:
```bash
# Restart the offending sidecar; the breaker will close on next probe
docker compose restart memory      # for example
```

The breaker fail-fast (Phase A.2) means worker calls return in
microseconds during the outage instead of waiting on the gRPC
deadline. Users see degraded service for the affected feature
(memory recall, artifact upload) but the bot stays responsive.

## 5. Telegram bot stops receiving messages

**Symptom**: Users say they sent messages, no reply. Worker logs
show no incoming updates.

**Diagnose**:
```bash
# Check the worker is up
curl -fs http://127.0.0.1:8090/health | jq '.workers[] | select(.agent_id == "<AGENT_ID>")'

# Check the bot-gateway (if BOT_GATEWAY_ENABLED=true)
docker compose logs bot-gateway --since 5m | grep -E "telegram_api|poll"

# Check Telegram-side
curl -fs "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

**Fix**:
- If a webhook is set on the bot (Telegram returns `url != ""`), it's
  hijacking polling. Delete it: `curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook"`.
- If polling itself is failing, restart the worker (or the
  bot-gateway). Phase 1B durable queue means in-flight updates are
  preserved.

## 6. Master key rotation

See [hardening.md](hardening.md#master-key-rotation).

## 7. Quick "stop everything" — kill switch

```bash
# Stop all workers (keeps the control plane up so you can recover)
for agent_id in $(docker compose exec -T postgres psql -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" -t -c "SELECT id FROM cp_agent_definitions WHERE status='active'"); do
    curl -X POST http://127.0.0.1:8090/api/control-plane/agents/${agent_id}/pause \
        -H "Authorization: Bearer $CONTROL_PLANE_API_TOKEN"
done

# Or, full-stop:
docker compose stop
```

The control plane retains the queue, audit, and assignments. After
the incident is resolved, `activate` agents one at a time to
verify the system is healthy.
