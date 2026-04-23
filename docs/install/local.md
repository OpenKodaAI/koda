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

The local quickstart brings up:

- `app`
- `web`
- `postgres`
- `seaweedfs`
- `seaweedfs-init`

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
