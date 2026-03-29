# VPS Install

## Target Environment

The official VPS target is Linux with Docker Compose.

The recommended bundled storage path uses:

- Postgres for durable state
- SeaweedFS for bundled S3-compatible object storage
- the web dashboard on port `3000`
- the control plane for product configuration

## Recommended Flow

```bash
git clone <your-fork-or-repo-url> /opt/koda
cd /opt/koda
./scripts/install.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Reverse Proxy

The default production overlay keeps both the dashboard and the control plane bound to localhost. A reverse proxy should:

- publish `/` to the Koda web UI
- terminate TLS
- publish `/setup`
- publish `/api/control-plane/*`
- publish `/api/runtime/*`
- publish `/openapi/control-plane.json`

Recommended model:

- Koda web listens on `127.0.0.1:${WEB_PORT:-3000}`
- Koda listens on `127.0.0.1:${CONTROL_PLANE_PORT:-8090}`
- your reverse proxy handles TLS and public routing
- product configuration remains inside the control plane instead of host env files

## Tailscale And External Hosting Layers

Koda is intentionally decoupled from the outer delivery layer. A VPS provider panel, Tailscale deployment, or similar host integration only needs to:

- run the Docker Compose stack
- preserve the persistent volumes
- route traffic to the control-plane HTTP surface
- keep bootstrap secrets available to the containers

Providers, agents, secrets, and integrations remain part of the Koda product layer, not the hosting layer.
Product configuration stays inside the control-plane UI and API.

## Restart And Boot Persistence

Use the provided systemd template:

- [`../../koda.service.example`](../../koda.service.example)

Adjust `WorkingDirectory`, install it as a real unit, and enable it after the compose stack is confirmed healthy.

## Hardening Baseline

- keep the control plane bound to localhost unless deliberately fronted by a proxy
- store `.env` and any bootstrap secret files with root or service-user-only permissions
- avoid exposing internal storage or database ports publicly
- use managed TLS at the reverse-proxy layer
- keep Docker volumes persistent across restarts

## Post-Install Validation

Run:

```bash
python3 scripts/doctor.py --env-file .env --base-url http://127.0.0.1:8090 --dashboard-url http://127.0.0.1:3000
```

Then finish product configuration through `/setup`.

## Upgrade Path

- pull the new version of the repository
- review updated docs and config notes
- rebuild and restart the stack with Docker Compose
- rerun the doctor command
- verify control-plane health and setup status

## Existing Bundled Object-Storage Installs

If you are migrating an older quickstart deployment from the previous bundled object-storage backend, follow the explicit migration guide before changing the S3 endpoint:

- [Object storage migration](object-storage-migration.md)
