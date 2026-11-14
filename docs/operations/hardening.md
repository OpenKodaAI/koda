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
- [ ] `.env` file is `0600` and excluded from git via `.gitignore`.
- [ ] `bootstrap.txt` is single-use; delete after first login.
- [ ] Backups (Postgres dumps, state tarballs) are encrypted at-rest
      via filesystem-level encryption (LUKS / EBS / GCS CMEK).

## Process hygiene (built in)

Nothing to configure. On Linux, each agent worker (`python -m koda`) and
the runtime kernel (`koda-runtime-kernel`) make themselves non-dumpable
(`PR_SET_DUMPABLE=0`) and set the core-file limit to 0. The kernel does
this first thing in `main`. The worker does it in the first statement of
`koda/__main__.py`, which runs only after Python itself has started (see
the startup window below). If either step fails, the process refuses to
start.

- The processes a worker or the kernel starts (provider CLIs, MCP servers,
  governed shell commands) run as the same user. Once the worker or the
  kernel has hardened itself, they get `Permission denied` on
  `/proc/<pid>/environ`, `mem` and `fd` of that process, and cannot attach
  a debugger to it, so they cannot read the secrets in its environment or
  memory. Root with `CAP_SYS_PTRACE` still can, so do not add that
  capability to the `runtime-kernel` container.
- **Residual: the worker's startup window.** From the moment the kernel
  starts a worker until `koda/__main__.py` runs, the worker is still
  dumpable while Python starts up (the interpreter, `site` and `.pth`
  processing, `koda/__init__.py`). That takes tens of milliseconds. A
  same-uid process that keeps polling `/proc/*/environ` reliably reads a
  starting worker's whole environment in that window: the Postgres DSN, the
  S3 secret, granted secrets and runtime tokens. It does not have to wait
  for a restart either. Being non-dumpable does not stop signals, so a
  same-uid process can kill a worker, and the kernel starts it again on the
  supervisor's next reconcile (every 5 seconds by default). Workers also
  restart when a new version is published and after a crash. Nothing stops
  this until ADR-002's L2 confinement (AG-14) runs provider CLIs, MCP
  servers and governed shell under Landlock: a Landlock-confined process
  cannot read `/proc/<pid>/environ` of a process outside its domain,
  whether that process is dumpable or not. Keeping secrets out of the exec
  environment altogether is a follow-up: the kernel would pass only
  non-secret variables and hand the rest to the worker through an inherited
  file descriptor that the worker reads after it has hardened. The kernel
  itself has no such window in practice: it is the first process in its
  container and hardens itself before any worker or command exists.
- The processes the worker and the kernel start inherit the zero core-file
  limit and cannot raise it. They are not non-dumpable themselves: once a process runs its
  own program it is dumpable again, so it is protected only by what is
  kept out of its environment.
- Debugging tools such as `py-spy`, `gdb -p` or `cat /proc/<pid>/environ`
  need root with `CAP_SYS_PTRACE` against these processes, for example
  `docker compose exec --privileged -u root runtime-kernel ...`.
- To check a running process: `grep 'core file' /proc/<pid>/limits` shows
  `0 0`, and `stat -c %U /proc/<pid>/environ` shows `root` even though the
  process runs as `botuser`.

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

The master key (`.master.key`) encrypts every secret in
`cp_secret_values`. Rotate annually or after a suspected compromise.

```bash
# 1. Generate new key
openssl rand 32 > /tmp/new-master.key

# 2. Move the OLD key to the previous-key slot
docker compose exec app cp \
    "${STATE_ROOT_DIR}/control_plane/.master.key" \
    "${STATE_ROOT_DIR}/control_plane/.master-previous.key"

# 3. Place the new key
docker compose exec app cp /tmp/new-master.key \
    "${STATE_ROOT_DIR}/control_plane/.master.key"

# 4. Set CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE in .env so the
#    decrypt path can still read pre-rotation rows
echo 'CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE=/var/lib/koda/state/control_plane/.master-previous.key' >> .env

# 5. Restart and re-encrypt every secret on next write
docker compose restart app

# 6. After the next batch update touched every secret, remove the
#    previous-key reference and the file
unset CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE  # remove from .env
docker compose exec app rm "${STATE_ROOT_DIR}/control_plane/.master-previous.key"
docker compose restart app
```

This is a one-way operation; back up `.master.key` before rotation.
Rotation that loses both files makes every secret unrecoverable.

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
