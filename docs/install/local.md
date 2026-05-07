# Local Install

Use this path when you want Koda running on your machine with the same core topology used by the VPS deployment.

## Prerequisites

- Docker and Docker Compose
- Node.js with npm for the packaged CLI path
- A repository clone only if you are contributing from source

## Quickstart

```bash
npm install -g @openkodaai/koda
koda install
```

Without a global install:

```bash
npx @openkodaai/koda@latest install
```

From a source clone on apt-based Linux hosts:

```bash
git clone <your-fork-or-repo-url> ./koda
cd ./koda
./scripts/install.sh
```

The installer verifies prerequisites, stages the product bundle, creates `.env` if needed, starts Docker Compose, runs doctor checks, and prints the setup URL plus a short-lived setup code.

## What Starts

```text
web :3000
app :8090
postgres
seaweedfs + seaweedfs-init
security + memory + artifact + retrieval + runtime-kernel
```

Optional overlays:

| Need | Enable |
|---|---|
| Telegram fan-in for many agents | `docker compose --profile bot-gateway up -d` |
| Workspace quotas | `docker compose --profile policy-engine up -d` |
| Multi-supervisor cluster | `docker compose -f docker-compose.yml -f docker-compose-cluster.yml up -d` |
| Prometheus/Grafana/Tempo | `docker compose -f docker-compose.yml -f docker-compose-observability.yml up -d` |

## First Boot

Open:

```text
http://127.0.0.1:3000/setup
```

Then:

1. Paste the setup code printed by the installer.
2. Create the owner account.
3. Save the ten one-time recovery codes.
4. Sign in to the dashboard.

The setup code is stored inside the app container at `${STATE_ROOT_DIR}/control_plane/bootstrap.txt`, mode `0600`, and is deleted after the owner is registered. If it expires, run:

```bash
koda auth issue-code
```

## Configure From The Dashboard

After login, use the dashboard to:

- connect providers
- create agents
- attach integrations and secrets
- publish runtime configuration
- inspect health, activity, costs, executions, sessions, memory, and routines

The quickstart path does not require per-agent env configuration. Product configuration lives in the control-plane UI and API after the platform boots.

`CONTROL_PLANE_API_TOKEN` is a break-glass and CLI credential. Browser auth uses owner login and HTTP-only sessions.

## Demo Data For Screenshots

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

Clear only demo data:

```bash
docker compose exec app python scripts/seed_demo_data.py --clear
```

## Doctor

```bash
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

The doctor validates bootstrap files, secrets, storage, control-plane reachability, and dashboard reachability.

## Manual Startup

```bash
cp .env.example .env
docker compose up -d --build
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

## Troubleshooting

- Dashboard unavailable: check `docker compose ps web`.
- API unavailable: check `docker compose ps app`.
- Degraded `/health`: inspect worker and sidecar status in the JSON payload.
- Object storage errors: check `seaweedfs` and `seaweedfs-init`.
- Browser login loops: verify `WEB_OPERATOR_SESSION_SECRET` is stable in `.env`.
- Runtime worker spawn failures: rebuild `runtime-kernel`; it must contain the Python runtime and shared Koda volumes.
- `koda install` aborts with `Detected pre-existing Docker volumes ... but no .env`: a
  previous install left its volumes behind (typical after `koda uninstall` without
  `--purge`, or after deleting `~/.koda` by hand). The auto-generated random
  Postgres password will not match the volume on disk. Either restore the matching
  `.env` into the install dir, or run `koda install --reset-volumes` to wipe the
  managed volumes and start clean.
- `koda install` fails after `up -d` with `Postgres rejected the credentials`: same
  root cause as above, surfaced after the stack started. Use the same recovery
  steps.

## Local-Native PID Files

The Docker-free development path writes PID files to `~/.koda-local/var/run/<service>.pid`.

```text
PID file + live process  -> service is running
PID file + dead process  -> remove stale file before restart
```

Use the restart helper to clear stale PID files and data-directory locks:

```bash
~/.koda-local/scripts/dev-down.sh
scripts/dev/dev-restart.sh
```
