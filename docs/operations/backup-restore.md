# Backup & restore

This runbook turns "we have backups" into "we have *tested* backups".
A backup that has never been restored is not a backup.

## What needs backing up

| Source | Why | RPO |
|---|---|---|
| Postgres database | Control plane, agents, audit log, queue items, knowledge graph | ≤ 1 h |
| Object store (S3-compatible / SeaweedFS) | Artifacts, embeddings, snapshots | ≤ 24 h |
| `${STATE_ROOT_DIR}/control_plane/.master.key` | Decrypts every secret in `cp_secret_values` | Permanent — losing this loses every stored secret |
| `${STATE_ROOT_DIR}/control_plane/bootstrap.txt` | Operator setup recovery | Permanent — single-use after install |
| `.env` file | Bootstrap configuration (DSNs, ports, ALLOWED_USER_IDS) | Permanent |

The runtime tmpfs (`koda-runtime`) is **not** backed up — it holds
ephemeral worktrees rebuilt by the runtime-kernel on demand.

## Postgres — pg_dump nightly

```bash
# Add to operator crontab on the host running docker compose
0 3 * * * docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" \
    --format=custom --no-owner --no-privileges \
    "$POSTGRES_DB" > /backup/koda-pg-$(date +\%F).dump
```

Retention: keep 7 daily, 4 weekly, 12 monthly. Encrypt at-rest via
the destination filesystem (LUKS / EBS encryption / GCS CMEK).

For larger deployments, switch to **WAL archiving** (RPO ~1 min):
configure `archive_mode=on` + `archive_command` pointing to S3, and
take a base backup with `pg_basebackup` weekly.

## Object store — sync to off-host bucket

```bash
# Daily, after pg_dump completes
docker compose exec -T seaweedfs \
    weed s3 sync s3://koda-objects s3://offsite-backup/$(date +\%F)/koda-objects/
```

If you use AWS S3 / GCS managed buckets, lifecycle rules + cross-
region replication usually replace this.

## State volume — tarball

```bash
docker run --rm -v koda_koda-state:/data:ro \
    -v /backup:/backup \
    alpine tar czf /backup/koda-state-$(date +\%F).tar.gz -C /data .
```

This catches the master key, bootstrap.txt, and any cached runtime
state. Encrypt the tarball before uploading off-host.

## Restore drill — monthly, mandatory

A restore drill once a month is the only way to know the procedure
still works. Schedule it.

```bash
# 1. Spin up an isolated stack (different ports / data volumes)
KODA_RESTORE=1 docker compose -p koda-restore up -d postgres seaweedfs

# 2. Restore Postgres
docker compose -p koda-restore exec -T postgres pg_restore \
    --clean --if-exists --no-owner --no-privileges \
    -d "$POSTGRES_DB" -U "$POSTGRES_USER" < /backup/koda-pg-YYYY-MM-DD.dump

# 3. Restore object store
docker compose -p koda-restore exec -T seaweedfs \
    weed s3 sync s3://offsite-backup/YYYY-MM-DD/koda-objects/ s3://koda-objects/

# 4. Restore state volume
docker run --rm -v koda-restore_koda-state:/data \
    -v /backup:/backup:ro \
    alpine sh -c "cd /data && tar xzf /backup/koda-state-YYYY-MM-DD.tar.gz"

# 5. Boot the rest of the stack
docker compose -p koda-restore up -d

# 6. Run doctor against the restored stack
python3 scripts/doctor.py --base-url http://127.0.0.1:18090

# 7. Verify a representative agent answers a known query
curl -X POST http://127.0.0.1:18090/api/control-plane/agents/.../send \
    -d '{"query":"What is your name?"}'
```

If any step fails, fix the procedure (not the data). Document the
fix in this file.

## Master key recovery

If `${STATE_ROOT_DIR}/control_plane/.master.key` is lost, every row
in `cp_secret_values` is unrecoverable. Mitigations:

- Store the key in an off-host secret manager (Vault, AWS KMS, GCP
  KMS, 1Password, sealed-secrets). The `.env` file or compose
  override mounts it back into the supervisor at boot.
- For rotation, see the [hardening](hardening.md) runbook.

## RTO target

For a single-host deployment with disk image + nightly Postgres
dump: **30 minutes** end-to-end (boot fresh host, restore image,
restore Postgres dump, run doctor, accept first message).

For a cluster deployment with WAL archiving + replicated S3:
**5 minutes** (the DB primary is already live; only stuck workers
need to be replaced).
