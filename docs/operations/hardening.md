# Hardening checklist

Pre-deploy hardening for self-hosted koda. The defaults work for
local development; production deploys expose the control plane to
people other than the operator (other team members, automation,
sometimes the public internet) and require deliberate hardening.

Every item below is verifiable. The matching checks live in
`scripts/doctor.py --strict` so CI / pre-deploy can fail closed.

## Filesystem & secrets

- [ ] `STATE_ROOT_DIR` permissions are `0700` (owner-only).
- [ ] `${STATE_ROOT_DIR}/control_plane/.master.key` is `0600`.
- [ ] The master key is backed up off-host, apart from the Postgres
      dumps it decrypts. Once Postgres has recorded its fingerprint, the
      control plane refuses to start without it or with a different key
      (see [backup-restore.md](backup-restore.md#master-key-recovery)).
- [ ] `.env` file is `0600` and excluded from git via `.gitignore`.
- [ ] `bootstrap.txt` is single-use; delete after first login.
- [ ] Backups (Postgres dumps, state tarballs) are encrypted at-rest
      via filesystem-level encryption (LUKS / EBS / GCS CMEK).

## Auth

- [ ] `CONTROL_PLANE_API_TOKEN` is at least 32 random bytes (use
      `openssl rand -hex 32`).
- [ ] `WEB_OPERATOR_SESSION_SECRET` is at least 32 random bytes.
- [ ] `RUNTIME_LOCAL_UI_TOKEN` is at least 32 random bytes.
- [ ] `ALLOWED_USER_IDS` is set; empty means "reject every message".
- [ ] `ALLOW_LOOPBACK_BOOTSTRAP=false` once the operator account
      exists (default for `KODA_ENV=production`).
- [ ] Recovery codes from initial setup are stored offline (1Password,
      hardware token, printed in a safe).

## Network

- [ ] Control-plane port `:8090` is NOT exposed publicly. Compose publishes
      it on `127.0.0.1` only; keep it that way (no overlay may re-publish it).
- [ ] Web port `:3000` is reverse-proxied behind TLS (Caddy, Traefik,
      nginx, cloud LB). Self-signed certs are acceptable for VPS
      deploys; managed certs (Let's Encrypt) for public deploys.
- [ ] `CONTROL_PLANE_TRUSTED_PROXIES` and `WEB_TRUSTED_PROXIES` list only
      the dashboard and proxies you run (Compose: `web` and `gateway`).
      A trusted peer can claim any client address for rate limiting.
- [ ] If `WEB_PUBLISH_ADDRESS` publishes the dashboard beyond loopback,
      its port is firewalled so only your reverse proxy can reach it.
      Docker can hide a direct client behind the trusted gateway, which
      lets it choose its own rate-limit bucket.
- [ ] Sidecar gRPC ports (`50061`–`50067`) are loopback / private
      network only — never publicly exposed.
- [ ] If running multi-host: `GRPC_TLS_ENABLED=true` for sidecar
      mTLS. Single-host loopback can stay `false`.

## Browser sandbox

- [ ] `BROWSER_ALLOW_PRIVATE_NETWORK=false` unless agents
      deliberately need to reach internal services.
- [ ] Browser tool disabled entirely (`BROWSER_FEATURES_ENABLED=false`)
      unless the deployment uses it.

## Resource isolation (Phase A.3)

When running on Linux (production deploys), set per-workspace cgroup
v2 limits so a noisy workspace cannot starve others:

- [ ] `KODA_AGENT_DEFAULT_MEMORY_MB=512` (or per-workspace
      override).
- [ ] `KODA_AGENT_DEFAULT_CPU_FRACTION=0.5`.
- [ ] `KODA_AGENT_DEFAULT_PIDS_MAX=128`.
- [ ] Cgroup root (`/sys/fs/cgroup/koda`) is writable by the
      supervisor process.

## Audit & retention

- [ ] `AUDIT_RETENTION_DAYS=90` (or higher per compliance
      requirements).
- [ ] `audit_events` rows are reviewed weekly: any
      `control_plane.worker_crash_loop`, `command_blocked`, or
      `policy.hard_stop_crossed` is investigated.

## Workspace policy (Phase 1C, opt-in)

For multi-team deployments, enable the policy engine to enforce
fairness:

- [ ] `POLICY_ENGINE_ENABLED=true`
- [ ] Per-workspace policy set via `UpdatePolicy` gRPC RPC:
  - `max_concurrent_agents` per workspace
  - `max_messages_per_minute` per workspace
  - `monthly_llm_spend_usd_cap` per workspace
- [ ] Hard-stop thresholds reviewed; spend warning crosses are
      surfaced in operator dashboards.

## Master key rotation

The master key (`.master.key`) encrypts every secret the control plane
stores: `cp_secret_values`, MCP connection env values and OAuth tokens,
and provider login sessions. Rotate annually or after a suspected
compromise.

Postgres records a fingerprint of the key in `cp_master_key_fingerprint`
(an HMAC of a fixed label under the key, never the key). At startup the
control plane refuses a key that does not match it, unless the previous
key does: that is a rotation, and the control plane then records the new
key's fingerprint. Replacing the key file without step 2 below therefore
stops the control plane at startup instead of leaving secrets
undecryptable.

```bash
# 1. Back up the current key off-host (see backup-restore.md).

# 2. Keep the current key as the previous key
docker compose exec app sh -c \
    'cd "$STATE_ROOT_DIR/control_plane" && cp -p .master.key .master-previous.key'

# 3. Write the new key in place. It must be a Fernet key (32 url-safe
#    base64-encoded bytes); raw `openssl rand` output is refused at startup.
docker compose exec app sh -c 'cd "$STATE_ROOT_DIR/control_plane" && umask 077 &&
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .master.key.new &&
    mv .master.key.new .master.key'

# 4. Set CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE in .env so the decrypt
#    path can still read pre-rotation rows and startup accepts the new key
echo 'CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE=/var/lib/koda/state/control_plane/.master-previous.key' >> .env

# 5. Recreate the app so it reads .env. Startup records the new key's
#    fingerprint (audit event security.master_key_fingerprint_recorded,
#    reason "rotation"); each secret is re-encrypted on its next write.
docker compose up -d --force-recreate app

# 6. After the next batch update touched every secret, remove the
#    CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE line from .env, then:
docker compose exec app sh -c 'rm "$STATE_ROOT_DIR/control_plane/.master-previous.key"'
docker compose up -d --force-recreate app
```

To undo a rotation before step 6, swap the two files back (old key as
`.master.key`, new key as `.master-previous.key`) and recreate the app.
The new key, now the previous key, matches the recorded fingerprint, so
startup records the old key's fingerprint again, and secrets already
re-encrypted with the new key still decrypt through the fallback.

This is a one-way operation once step 6 is done; back up `.master.key`
before rotation. Rotation that loses both files makes every secret
unrecoverable. In cluster mode every control-plane replica must use the
same key file: a replica with another key refuses to start.

## Provider tokens

Telegram bot tokens, OpenAI / Claude / etc. API keys live in
`cp_secret_values` (encrypted at rest with the master key) but the
operator's own `.env` file may also contain bootstrap values. Best
practice:

- [ ] Keep tokens out of `.env` whenever possible — the control-plane
      UI is the canonical place.
- [ ] If `.env` MUST contain a token (e.g. `AGENT_TOKEN` for the
      first bootstrap), the file is `0600` and excluded from
      backups.
- [ ] For multi-host or managed deploys, integrate a secret store
      (Vault, sealed-secrets, AWS Secrets Manager) and inject env
      vars at boot.

## Verification

```bash
docker compose exec app python3 scripts/doctor.py --strict
```

Strict mode runs every check above. Exit 0 means production-ready.
Any failure must be addressed before exposing the deployment to
real users.
