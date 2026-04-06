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

When the installer finishes, open the dashboard setup URL it prints:

- `http://127.0.0.1:3000/control-plane`
- `http://127.0.0.1:3000`

At that point the infrastructure is already ready for use:

- the dashboard UI is reachable
- Postgres is available
- object storage is available
- bootstrap secrets exist
- the control plane is reachable
- health checks are in place

Use the dashboard control plane to complete product configuration:

1. review platform health and bootstrap status
2. configure owner and access policy
3. connect and verify the providers you want to use
4. connect and verify the integrations you want to expose globally
5. optionally connect the first Telegram agent
6. continue ongoing configuration in the control plane

After provider and integration setup, each bot still needs its own grants. In practice the operator flow is:

- configure the provider or integration in the control plane
- run `verify` and inspect the resulting `connection_status` / `checked_via`
- open the bot editor and grant only the required tools and `resource_access_policy.integration_grants`

The quickstart now provisions `WEB_OPERATOR_SESSION_SECRET` automatically so operator sessions
survive web restarts instead of depending on ephemeral in-memory state.
Daily operator access should start from the printed setup code, local owner account, and HTTP-only
browser session. `CONTROL_PLANE_API_TOKEN` remains recovery-only.

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
- If `http://127.0.0.1:3000/control-plane` is not reachable, verify that `docker compose ps` shows `web` healthy.
- If `http://127.0.0.1:8090/health` is not reachable, verify that `docker compose ps` shows `app` healthy.
- If object storage checks fail, verify that `seaweedfs` and `seaweedfs-init` both completed successfully.
- If bootstrap still fails, rerun the doctor command and inspect the reported failing check name.
