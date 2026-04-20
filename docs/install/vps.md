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
4. grant integrations per agent in the agent editor instead of assuming system-level configuration is enough

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

## Public Deployment Checklist

For any deploy reachable from the public internet:

1. **`KODA_ENV=production`** — this blocks `CONTROL_PLANE_AUTH_MODE=development|open` and
   `ALLOW_LOOPBACK_BOOTSTRAP=true` at boot. Both are rejected with a hard failure.
2. **`ALLOW_LOOPBACK_BOOTSTRAP=false`** — the first-owner flow then requires the bootstrap
   code. Do NOT enable loopback trust behind a reverse proxy that might forward an arbitrary
   `X-Forwarded-For`.
3. **Bootstrap code via SSH:** on first boot the control plane writes
   `${STATE_ROOT_DIR}/control_plane/bootstrap.txt` (mode `0600`) and echoes it once to the
   container log. SSH in, `cat` the file, paste it into `/setup`. The file is deleted after
   successful registration.
4. **HTTPS everywhere.** The session cookie is named `koda_operator_session` and is sent
   with `Secure; HttpOnly; SameSite=Strict`. Without TLS at the reverse proxy, the `Secure`
   flag means the browser never sends the cookie back.
5. **Strict CSP on auth screens.** `/login`, `/setup`, and `/forgot-password` enforce a
   strict Content-Security-Policy that disallows cross-origin scripts and iframing. Do not
   patch in `'unsafe-inline'`.
6. **Password policy.** Minimum 12 characters, 3-of-4 character classes, a top-500
   common-passwords deny list, and substring-of-identifier rejection. Override with
   `CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH` only upward.
7. **Recovery codes are single-use.** After any password reset, every remaining code is
   invalidated. The owner must regenerate a fresh batch from Settings › Security (requires
   current password).
8. **Account lockout + rate limits** are already enforced — 5 failed logins per 5 minutes
   per IP, 5 password resets per hour per IP, 3 regenerations per hour per user. Responses
   are deliberately slowed to a ~300 ms floor so the caller cannot distinguish between
   "account does not exist", "wrong password", and "invalid recovery code".
9. **Audit.** Every auth event writes a structured `security.*` event through
   `emit_security()`. Ensure your logging backend persists these.
10. **`CONTROL_PLANE_API_TOKEN`** is optional and should be left blank unless you need a
    break-glass CLI credential; the standard flow no longer uses it.

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
