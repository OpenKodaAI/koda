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

### Master key check on start

Before it serves anything, the control plane checks the master key against
the fingerprint Postgres records in `cp_master_key_fingerprint` (migration
`048_control_plane_master_key_fingerprint`). On the first start after an
upgrade from a release without that table, it checks that the key it finds,
or the previous key during a rotation, decrypts at least one of the newest
stored encrypted values. It then records the key's fingerprint (audit event
`security.master_key_fingerprint_recorded`, `reason=upgrade`); it re-encrypts
and deletes nothing. The app refuses to start, logging
`koda control plane refused to start:` with the fix, in three cases: the key
file is missing while encrypted secrets exist; on that first start, the key
decrypts none of them (releases before this check created a new key
whenever the file was missing); or, on later starts, the key differs from
the recorded one. See [backup-restore.md](backup-restore.md#master-key-recovery).

Releases from before this check ignore the table, so rolling back needs no
extra step. Keep the key file in place either way: those releases create a
new key when the file is missing.

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

Then confirm that both images carry the pinned provider CLIs (see
[Provider CLI versions](#provider-cli-versions)):

```bash
docker compose exec -T app python -m koda.services.provider_cli_contract
docker compose exec -T runtime-kernel python -m koda.services.provider_cli_contract
```

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

## Provider CLI versions

The `app` and `runtime-kernel` images install Claude Code, Codex and
Gemini CLI from one lockfile, `packages/provider-clis/package-lock.json`,
at the exact versions listed in `packages/provider-clis/package.json`.
Nothing in a running image can install or update a package: npm and
npx are not in the image, and Gemini no longer falls back to
`npx @google/gemini-cli` when its binary is missing.

Before a provider's first turn, Koda checks the installed binary
against its contract in `koda/services/provider_cli_contract.py`: the
version must equal the pin, every option Koda passes must have its own
entry in `--help` with each value Koda passes listed in that entry,
and options that `--help` hides must be accepted by the parser. Each
runner repeats the check once its cached result is 30 seconds old, so
a binary replaced in place is probed again. If any check fails, the
provider is unavailable for turns and its health entry shows the
reason:

| Reason | Meaning |
|---|---|
| `unavailable:unverified_cli_version` | The installed CLI is not the pinned version, or it does not accept an option Koda passes. |
| `unavailable:cli_not_installed` | The CLI is not on `PATH`. |
| `unavailable:cli_probe_failed` | `--version` or `--help` did not finish, so nothing could be verified. |

Koda never runs a turn on an unverified CLI. Rebuild or pull the
images to get the pinned versions. Native (non-Docker) runs must
install exactly the versions in `packages/provider-clis/package.json`.
The `gemini_bin` system setting (`GEMINI_BIN`) is the path of one
executable, the pinned `gemini` binary. A command line such as
`npx -y @google/gemini-cli` is not a valid value: Koda reads the
whole value as one path, finds no such executable, and treats the
CLI as not installed.

`python -m koda.services.provider_cli_contract` prints the check for
every provider as JSON and exits non-zero on any mismatch. It runs
only `--version`, `--help` and a parser check, with no model call and
no credentials. It starts each CLI the way the runners do: with the
same command and the same allowlisted environment, so database,
object-storage and other container secrets never reach the CLIs.

### Changing a pinned version

1. Change the version in `packages/provider-clis/package.json`, then
   run `npm install --package-lock-only` in that directory.
2. Update `pinned_version` and the option tokens in
   `koda/services/provider_cli_contract.py`, checking each token
   against the new version's real `--help` output. For Claude Code,
   also refresh the recorded outputs in `tests/fixtures/provider_cli/`.
3. Merge only when the `provider-cli-contract` CI job passes. It
   installs the lockfile the way the images do and probes the
   binaries against the contract.

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
