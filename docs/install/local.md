# Local Install

## Prerequisites

- Docker
- Docker Compose
- Node.js with npm if you want the packaged CLI path
- a local clone of this repository only when contributing from source

## Quickstart

```bash
npm install -g koda
koda install
```

If you are working from the repository itself, the source wrapper installs the same npm CLI and
then stages the product bundle into a separate `.koda-release/` directory:

```bash
git clone <your-fork-or-repo-url> ./koda
cd ./koda
./scripts/install.sh
```

The installer will:

1. verify Docker and the Koda npm CLI prerequisites
2. stage the release bundle in its own product directory
3. create a minimal `.env` if one does not exist
4. start the quickstart stack with the release compose file
5. run the doctor checks
6. print the dashboard setup URL plus a short-lived setup code

## What Starts

The local quickstart brings up only what every Koda deployment needs:

- `app` — control plane + worker host (Python)
- `web` — dashboard UI (Next.js)
- `postgres` — single source of truth for control plane, agents, audit, queue
- `seaweedfs` + `seaweedfs-init` — bundled S3-compatible object store
- `security` / `memory` / `artifact` / `retrieval` / `runtime-kernel` — Rust sidecars used on every agent turn

That's it. No observability stack, no Telegram fan-in pool, no quota engine, no
multi-supervisor cluster. Each of those is an opt-in profile or overlay file you
turn on when you actually need it (see [`docs/operations/`](../operations/README.md)):

| Feature | How to enable | When it's worth it |
|---|---|---|
| Telegram fan-in (`bot-gateway`) | `docker compose --profile bot-gateway up -d` + `BOT_GATEWAY_ENABLED=true` | You run >5 agents on the same host |
| Workspace quotas (`policy-engine`) | `docker compose --profile policy-engine up -d` + `POLICY_ENGINE_ENABLED=true` | You have multiple internal teams sharing one deployment |
| Multi-supervisor cluster | `docker compose -f docker-compose.yml -f docker-compose-cluster.yml up -d` | You need >100 agents or zero-downtime deploys |
| Observability (Prometheus + Grafana + Tempo) | `docker compose -f docker-compose.yml -f docker-compose-observability.yml up -d` | You want metrics dashboards / distributed tracing |

This is the same platform topology used by the default VPS path.

## Ports And Volumes

Default local ports:

- `3000` for the Koda dashboard UI
- `8090` for the control plane API, health surface, and `/setup` compatibility bridge
- `5432` for Postgres inside the compose network
- `8333` for bundled S3-compatible storage inside the compose network

Persistent volumes are managed by Docker Compose and are intended to survive container restarts.

## First Boot

When the installer finishes, open the dashboard:

- `http://127.0.0.1:3000/setup`

The flow is deliberately minimal — two screens, no provider or GitHub or Telegram required
up-front. Everything else is configured from the dashboard after first login.

### 1. Create the owner account (`/setup`)

Fill in:

- email
- password (minimum 12 characters, 3 of 4 classes: upper / lower / digit / symbol)
- confirm password

The `username` is derived from the email local-part and can be renamed later.

By default, `ALLOW_LOOPBACK_BOOTSTRAP=true` in development, which means no setup code is
required when the request originates from `127.0.0.1` with no proxy hop. If loopback trust is
disabled, the page shows an additional **setup code** field; read the value from
`${STATE_ROOT_DIR}/control_plane/bootstrap.txt` (the file is created on first boot with mode
`0600` and is echoed to the control-plane log once). The file is deleted automatically after
the owner is registered.

### 2. Save your recovery codes

After registration, the dashboard shows **ten** one-time recovery codes. Copy, download, or
print them — they are never shown again. Tick the confirmation checkbox and continue to the
dashboard.

Recovery codes let you reset the password without SMTP:

- visit `/forgot-password`
- enter your email + any unused recovery code + a new password
- all existing sessions are revoked, and **every remaining recovery code is invalidated** (you
  must regenerate a new batch from Settings › Security)

### 3. Optional configuration in the dashboard

A `SetupChecklistCard` on the dashboard home points to three opt-in steps:

- connect an AI provider
- create your first agent
- connect Telegram (or any other channel)

Each item opens a Drawer with its dedicated wizard. None of them block normal operation, and
the card dismisses itself once all three are complete.

`CONTROL_PLANE_API_TOKEN` stays blank by default and is only used as a break-glass CLI
credential. It is no longer part of the default setup flow.

The quickstart path does not require per-agent env configuration, provider credentials in
`.env`, or manual Telegram runtime wiring before first boot.

## Doctor

Run the built-in diagnostic command at any time:

```bash
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

The doctor validates bootstrap configuration, storage connectivity, secrets, dashboard reachability, and control-plane reachability.

## Manual Startup

If you prefer to bootstrap without the installer:

```bash
cp .env.example .env
docker compose up -d --build
python3 scripts/doctor.py --env-file .env --base-url http://127.0.0.1:8090 --dashboard-url http://127.0.0.1:3000
```

## Troubleshooting

- If the dashboard is not reachable, verify that `docker compose ps` shows `web` healthy.
- If `http://127.0.0.1:3000/control-plane` is not reachable, verify that `docker compose ps` shows `web` healthy.
- If `http://127.0.0.1:8090/health` is not reachable, verify that `docker compose ps` shows `app` healthy.
- If object storage checks fail, verify that `seaweedfs` and `seaweedfs-init` both completed successfully.
- If bootstrap still fails, rerun the doctor command and inspect the reported failing check name.

### Local-native bring-up: PID-file invariant

The Docker-free path uses `~/.koda-local/scripts/dev-up.sh` (Postgres,
the object-store backend, the 5 Rust sidecars, control plane, web).
Each long-running process writes its PID to
`~/.koda-local/var/run/<service>.pid`. The script's idempotency relies
on this invariant:

- A PID file present **and** the listed PID still alive means the service
  is up; the script must skip starting it.
- A PID file present but the PID is dead means the previous run crashed.
  The PID file must be removed before starting a fresh process — otherwise
  the second `dev-up.sh` invocation thinks the service is healthy and
  refuses to start it, leaving the stack half-up.

Some services (notably the object-store backend) additionally hold an
on-disk lock under their data directory that survives process death; if
the service was SIGKILL'd during debugging, the next `dev-up.sh` will
report `Another instance is already running` and bail.

Use `scripts/dev/dev-restart.sh` (a thin wrapper around `dev-down.sh` →
`dev-up.sh`) to safely cycle the stack: it removes stale PID files, lets
data-directory locks release, then re-runs the bring-up.

```bash
~/.koda-local/scripts/dev-down.sh
scripts/dev/dev-restart.sh
```
