# Backup & restore

This runbook turns "we have backups" into "we have *tested* backups".
A backup that has never been restored is not a backup.

## What needs backing up

| Source | Why | RPO |
|---|---|---|
| Postgres database | Control plane, agents, audit log, queue items, knowledge graph | ≤ 1 h |
| Object store (S3-compatible / SeaweedFS) | Artifacts, embeddings, snapshots | ≤ 24 h |
| `${STATE_ROOT_DIR}/control_plane/.master.key` | Decrypts every stored secret (`cp_secret_values`, MCP env values and OAuth tokens). Postgres records its fingerprint, so the control plane refuses to start without it once secrets exist | Permanent — losing this loses every stored secret. Keep it apart from the Postgres dumps |
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

# 5. Boot the rest of the stack. The control plane checks the restored
#    key against the fingerprint in the restored database: if step 4 is
#    skipped or restores a key from another backup set, it refuses to
#    start (see "Master key recovery" below) instead of creating a new key.
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

If `${STATE_ROOT_DIR}/control_plane/.master.key` is lost, every
stored secret is unrecoverable. Mitigations:

- Store the key in an off-host secret manager (Vault, AWS KMS, GCP
  KMS, 1Password, sealed-secrets). The `.env` file or compose
  override mounts it back into the supervisor at boot.
- For rotation, see the [hardening](hardening.md#master-key-rotation) runbook.

### How the control plane guards the key

The control plane creates the key only on a fresh install: when it starts
with no key file, no fingerprint in Postgres and no encrypted data. No other
process creates one; an agent worker or CLI without the key file fails with
`MasterKeyUnavailable`. On every start the control plane compares the key
with the fingerprint recorded in `cp_master_key_fingerprint` (an HMAC of a
fixed label under the key, never the key). On the first start after an
upgrade from a release without that table, it first checks that the key it
finds, or the previous key during a rotation, decrypts at least one of the
newest stored encrypted values. Releases before this check created a new
key whenever the key file was missing, and such a key must not become the
recorded one. It then records the key's fingerprint and changes nothing
else.

A lost or wrong key therefore stops the control plane at startup, with a
log line starting `koda control plane refused to start:`:

| The message says | Cause | Fix |
|---|---|---|
| `master key not found ... this database recorded a master key (fingerprint ...)` | The key file is missing | Restore the key file from backup |
| `master key not found ... the database holds encrypted secrets` | The key file is missing on an install whose fingerprint was never recorded | Restore the key file from backup |
| `... is not the key this database recorded` | Another key: a backup from another set, another volume, or a cluster replica with its own key | Restore the key whose fingerprint matches; when rotating, follow [hardening](hardening.md#master-key-rotation) |
| `... decrypts none of the ... newest encrypted values in this database` | First start after an upgrade, with a key that did not encrypt the stored secrets. Releases before this check created a new key whenever the key file was missing, for example after `koda-state` was lost or not restored | Restore the original key file from backup. To keep the key found as well, put the original in the previous-key slot, as in a [rotation](hardening.md#master-key-rotation). If the original is permanently lost, see [below](#if-the-key-is-permanently-lost) |
| `... is not a valid Fernet key` | The file is damaged or is not a Fernet key | Restore the key file from backup |

To find which backup holds the right key, compare fingerprint prefixes. The
recorded one (adjust the schema if you changed `KNOWLEDGE_V2_POSTGRES_SCHEMA`):

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
    "SELECT left(fingerprint, 12), recorded_reason, updated_at FROM knowledge_v2.cp_master_key_fingerprint"
```

A candidate key file:

```bash
python3 -c 'import hashlib, hmac, sys
key = open(sys.argv[1], "rb").read().strip()
print(hmac.new(key, b"koda.control_plane.master_key.fingerprint.v1", hashlib.sha256).hexdigest()[:12])' candidate.key
```

### If the key is permanently lost

The encrypted secrets cannot be recovered. To run again with a new key,
deliberately and only after a Postgres backup:

1. Write a new key file. The app container keeps restarting while it
   refuses, so use a one-off container:

   ```bash
   docker compose run --rm --no-deps app sh -c 'mkdir -p "$STATE_ROOT_DIR/control_plane" &&
       cd "$STATE_ROOT_DIR/control_plane" && umask 077 &&
       python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .master.key'
   ```

2. If a fingerprint is recorded, delete it:
   `DELETE FROM knowledge_v2.cp_master_key_fingerprint;`. This removes only
   the check; the old ciphertext stays in place.
3. Let the control plane start (`docker compose up -d app`) and read
   `docker compose logs app`. While encrypted secrets are stored, it refuses
   with `... decrypts none of the ... newest encrypted values in this
   database`. The message names the new key's fingerprint prefix and an
   acknowledgement file next to the key file
   (`.master.key.accept-undecryptable`). If it starts instead, nothing stored
   needed the old key; go to step 5.
4. Accept the new key explicitly: write that prefix into the file the
   message names.

   ```bash
   docker compose run --rm --no-deps app sh -c \
       'echo <prefix> > "$STATE_ROOT_DIR/control_plane/.master.key.accept-undecryptable"'
   ```

   On the next start, the control plane records the new key's fingerprint
   (`reason=lost_key_reset`, audit event
   `security.master_key_fingerprint_recorded`) and deletes the file. The file
   counts only for the key whose fingerprint it names, and only while no
   fingerprint is recorded.
5. Re-enter every secret, MCP credential and OAuth connection in the
   dashboard; the old values stay undecryptable until they are overwritten.

## RTO target

For a single-host deployment with disk image + nightly Postgres
dump: **30 minutes** end-to-end (boot fresh host, restore image,
restore Postgres dump, run doctor, accept first message).

For a cluster deployment with WAL archiving + replicated S3:
**5 minutes** (the DB primary is already live; only stuck workers
need to be replaced).
