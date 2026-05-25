# Upgrade procedure

Self-hosted koda upgrades follow a five-step pipeline that keeps the
operator in the loop. The pipeline is the same for single-host and
multi-supervisor deployments; cluster mode adds a drain step.

## Pre-flight (always)

1. **Read the changelog.** Schema migrations and removed env vars
   are called out in `docs/release-notes/<version>.md`.
2. **Take a backup.** See [backup-restore.md](backup-restore.md).
3. **Pull the new image** but do not restart yet.

   ```bash
   docker compose pull
   ```

## Step 1 — schema migration gate

```bash
docker compose run --rm app python -m koda migrate --check
```

Exit codes:
- `0` — DB is in sync with the new code's migrations. Safe to upgrade.
- `3` — pending migrations. Apply them BEFORE rolling new code.
- `1` — infra error (DSN unreachable, asyncpg missing). Fix and retry.

If exit `3`, apply migrations first:

```bash
docker compose run --rm app python -m koda migrate
docker compose run --rm app python -m koda migrate --check  # must now exit 0
```

The `migrate --check` step is also enforced in CI via
`.github/workflows/migrations-gate.yml` so a PR that adds a migration
without bumping the schema_migrations expectation cannot merge.

## Step 2 — single-host restart

For a single-host docker-compose deployment:

```bash
docker compose up -d --no-deps app web    # rolls services with the new image
docker compose restart supervisor          # if you run the supervisor separately
```

Wait for `/health` to report `healthy`:

```bash
curl -fs http://127.0.0.1:8090/health | jq .status
```

## Step 2 (cluster) — blue/green drain

For a multi-supervisor deployment (`KODA_CLUSTER_MODE=cluster`):

```bash
# 1. Bring up the new version's supervisor pods alongside the old.
docker compose up -d --scale supervisor=4 supervisor   # 2 old + 2 new

# 2. Drain the old supervisors. Each releases its claims; the new
#    supervisors pick them up via the SELECT FOR UPDATE SKIP LOCKED
#    path. In-flight messages are preserved by the bot-gateway's
#    durable queue.
for old_pod in supervisor-old-1 supervisor-old-2; do
    curl -fs -X POST http://${old_pod}:8090/cluster/drain
done

# 3. Wait for owned_count → 0 on the old pods.
watch -n 2 'curl -fs http://supervisor-old-1:8090/cluster/status | jq .owned_count'

# 4. Stop the old pods.
docker compose stop supervisor-old-1 supervisor-old-2
```

The drain HTTP endpoints are documented in
[cluster-mode.md](cluster-mode.md).

## Step 3 — doctor verification

```bash
docker compose exec app python3 scripts/doctor.py --strict
```

Strict mode adds the [hardening](hardening.md) checklist to the
default doctor checks. Any failure aborts the upgrade.

## Step 4 — smoke a representative request

Send a known query through your usual interface (Telegram bot,
control-plane UI, API) and verify the response shape. If you have
synthetic users wired into the [observability](observability.md)
stack, the smoke test is just a prometheus alert read: query
processing rate at baseline within 60s.

## Step 5 — rollback (only if 1-4 fails)

```bash
# 1. Stop the new image
docker compose stop app web

# 2. Restore Postgres from pre-upgrade dump
#    (see backup-restore.md)
docker compose exec -T postgres pg_restore --clean ... < pre-upgrade.dump

# 3. Pin the previous image tag in docker-compose.yml or the env file
echo "KODA_IMAGE_TAG=v1.0.10" >> .env

# 4. Bring the old version back up
docker compose up -d
```

**Important:** rolling back a migration is a one-way door for any
new column / table the new code wrote rows into. Forward-only
migration design (additive ALTERs, never DROP COLUMN in the same
release that introduces the column) keeps rollback safe. If a
release notes called out a destructive migration, follow the
release-specific rollback in `docs/release-notes/<version>.md`.

## Tracking upgrade history

Every successful upgrade should leave an audit row:

```bash
docker compose exec app python3 -c "
from koda.control_plane.audit import record_audit_event
record_audit_event('global', event_type='operator.upgrade_completed', \
    details={'from': 'v1.0.10', 'to': 'v1.0.11'})
"
```

Future-you running an incident review will be glad you did.
