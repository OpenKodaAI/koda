# Local Install

## Prerequisites

- Docker
- Docker Compose
- a local clone of this repository

## Quickstart

```bash
git clone <your-fork-or-repo-url> ./koda
cd ./koda
./scripts/install.sh
```

The installer will:

1. verify Docker and Docker Compose
2. create a minimal `.env` if one does not exist
3. start the quickstart stack with `docker compose up -d --build`
4. run the doctor checks
5. print both the dashboard URL and the bootstrap URL

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
- `8090` for the control plane and setup surface
- `5432` for Postgres inside the compose network
- `8333` for bundled S3-compatible storage inside the compose network

Persistent volumes are managed by Docker Compose and are intended to survive container restarts.

## First Boot

When the installer finishes, open the bootstrap URL it prints:

- `http://127.0.0.1:3000`
- `http://127.0.0.1:8090/setup?token=<CONTROL_PLANE_API_TOKEN>`

![Koda control plane interface](../assets/screenshots/setup.png)

At that point the infrastructure is already ready for use:

- the dashboard UI is reachable
- Postgres is available
- object storage is available
- bootstrap secrets exist
- the control plane is reachable
- health checks are in place

Use the control plane UI to complete product configuration:

1. review platform health and bootstrap status
2. configure owner and access policy
3. connect and verify a provider
4. create or publish the first agent
5. continue ongoing configuration in the control plane

The quickstart path does not require per-agent env configuration, provider credentials in `.env`, or manual Telegram runtime wiring before first boot.

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
- If `/setup` is not reachable, verify that `docker compose ps` shows `app` healthy.
- If object storage checks fail, verify that `seaweedfs` and `seaweedfs-init` both completed successfully.
- If bootstrap still fails, rerun the doctor command and inspect the reported failing check name.
