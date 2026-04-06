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
npm install -g koda
koda install --headless
```

For source-based administration or contributor workflows you can still use the repository wrapper,
which installs the npm CLI locally and stages the release bundle into `.koda-release/`.

## Reverse Proxy

The default production overlay keeps both the dashboard and the control plane bound to localhost. A reverse proxy should:

- publish `/` to the Koda web UI
- publish `/control-plane` to the Koda dashboard setup and operator surface
- terminate TLS
- optionally keep `/setup` only as a compatibility redirect
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

The expected post-bootstrap flow is:

1. connect and verify providers
2. connect and verify integrations
3. inspect `connection_status`, `checked_via`, and recent integration health when something is degraded
4. grant integrations per bot in the agent editor instead of assuming system-level configuration is enough

## Restart And Boot Persistence

Use the provided systemd template:

- [`../../koda.service.example`](../../koda.service.example)

Adjust `WorkingDirectory`, install it as a real unit, and enable it after the compose stack is confirmed healthy.

## Hardening Baseline

- keep the control plane bound to localhost unless deliberately fronted by a proxy
- store `.env` and any bootstrap secret files with root or service-user-only permissions
- avoid exposing internal storage or database ports publicly
- use managed TLS at the reverse-proxy layer
- set and rotate `WEB_OPERATOR_SESSION_SECRET` so dashboard operator sessions remain stable across restarts
- keep Docker volumes persistent across restarts

## Post-Install Validation

Run:

```bash
python3 scripts/doctor.py --env-file .env --base-url http://127.0.0.1:8090 --dashboard-url http://127.0.0.1:3000
```

Then finish product configuration through `/control-plane` in the dashboard.

## Upgrade Path

- install the new npm CLI release or run `npx koda@latest update`
- rerun `koda update`
- let the CLI run doctor checks and rollback automatically if the new bundle is unhealthy
- verify control-plane health and setup status

## Existing Bundled Object-Storage Installs

If you are migrating an older quickstart deployment from the previous bundled object-storage backend, follow the explicit migration guide before changing the S3 endpoint:

- [Object storage migration](object-storage-migration.md)
