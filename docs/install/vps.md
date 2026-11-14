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
npm install -g @openkodaai/koda
koda install --headless
```

For source-based administration or contributor workflows you can still use the repository wrapper,
which installs the npm CLI locally and stages the release bundle into `.koda-release/`.

## Reverse Proxy

Koda publishes the dashboard and the control-plane API on the host's loopback interface only
(packaged installs, `docker-compose.yml` and the production overlay alike), so nothing is reachable
from the network until a reverse proxy publishes it. A reverse proxy should:

- publish `/` to the Koda web UI
- publish `/setup`, `/login`, `/forgot-password`, and `/control-plane` to the Koda dashboard
- terminate TLS
- optionally keep `/control-plane/setup` as a compatibility redirect to `/setup`
- publish `/api/control-plane/*`
- publish `/api/runtime/*`
- publish `/openapi/control-plane.json`
- add the address each request came from to `X-Forwarded-For`, appended or replacing the header
  (see the rate-limit notes below)

Recommended model:

- Koda web listens on `127.0.0.1:${WEB_PORT:-3000}`
- Koda listens on `127.0.0.1:${CONTROL_PLANE_PORT:-8090}`
- your reverse proxy handles TLS and public routing
- product configuration remains inside the control plane instead of host env files

The bundled `proxy/nginx.conf` targets `127.0.0.1` (not `localhost`, which may resolve to `::1`
first while Koda publishes on IPv4 loopback only).

The control-plane API is always published on loopback only; the dashboard reaches it over the
Docker network (`http://app:8090`) and a host reverse proxy reaches it on `127.0.0.1`.
`WEB_PUBLISH_ADDRESS` publishes the dashboard on another interface instead of loopback, only for a
TLS-terminating proxy running on another host. Such a proxy can reach the dashboard (browser
sessions) but not the control-plane API, so API-token clients and `/openapi/control-plane.json`
need a proxy on the Koda host. Plain-HTTP access from other machines does not work: production
operator session cookies are `Secure`, so browsers only keep them on HTTPS (or `localhost`).

Login and recovery are rate limited per client address. A proxy on the Koda host reaches the
dashboard from the Docker gateway, whose `X-Forwarded-For` the dashboard believes
(`WEB_TRUSTED_PROXIES=gateway` in Compose), and the API believes the dashboard
(`CONTROL_PLANE_TRUSTED_PROXIES=web`). The proxy must therefore add the address it received each
request from to `X-Forwarded-For`, appended or replacing the header. nginx needs
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` (or `$remote_addr`) in every
`location`, as in the bundled `proxy/nginx.conf`; HAProxy needs `option forwardfor` (without
`if-none`); Caddy and Traefik do it by default. A proxy that passes the client's header through
unchanged, which nginx and HAProxy do otherwise, lets each client name its own rate-limit bucket,
and clients that send no header all share one bucket. If your proxy also forwards
`/api/control-plane/*` straight to the API, as the bundled `proxy/nginx.conf` does, set
`CONTROL_PLANE_TRUSTED_PROXIES=web,gateway`, or all of its clients share one budget. A proxy
on another host needs its address added: `WEB_TRUSTED_PROXIES=gateway,<proxy-ip>`.

A proxy that runs as a container on Koda's Compose network (Traefik or Caddy attached to
`frontend`) connects from its own container address. `WEB_TRUSTED_PROXIES` takes addresses,
not service names, and Docker can give a container a new address when it is recreated, so
pin one in a Compose override and trust that single address
(`WEB_TRUSTED_PROXIES=gateway,172.30.0.10`). Trusting the whole subnet instead would let every
container on it name any client. Until the proxy is trusted, all of its clients share one
budget. A new subnet applies only once the network is recreated (`docker compose down`).

```yaml
networks:
  frontend:
    ipam:
      config:
        - subnet: 172.30.0.0/24
services:
  proxy: # your reverse proxy
    networks:
      frontend:
        ipv4_address: 172.30.0.10
```

If that proxy also forwards `/api/control-plane/*` straight to `app:8090`, add its service name
to `CONTROL_PLANE_TRUSTED_PROXIES` (`web,proxy`), which does accept hostnames.

When `WEB_PUBLISH_ADDRESS` publishes the dashboard beyond loopback, firewall its port so only
your proxy can reach it. A client that connects directly is charged to its own address, but
Docker hides that address behind the gateway when its userland proxy carries the connection
(Docker Desktop, rootless Docker, an IPv6 host address on an IPv4-only network), and the
gateway is trusted to name any client. See
[Authentication](../security/authentication.md#which-address-a-request-is-charged-to).

## Tailscale And External Hosting Layers

Koda is intentionally decoupled from the outer delivery layer. A VPS provider panel, Tailscale deployment, or similar host integration only needs to:

- run the Docker Compose stack
- preserve the persistent volumes
- route HTTPS traffic to the dashboard on the host's loopback (for example
  `tailscale serve --bg --https=443 http://127.0.0.1:3000`; publishing plain HTTP on the tailnet IP
  does not work because session cookies are `Secure`)
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

1. **`KODA_ENV=production`** — this blocks `ALLOW_LOOPBACK_BOOTSTRAP=true` at boot
   (rejected with a hard failure). The control-plane backend always enforces an
   operator-session bearer token at the middleware layer regardless of environment.
2. **`ALLOW_LOOPBACK_BOOTSTRAP=false`** — the first-owner flow then requires the bootstrap
   code. Do NOT enable loopback trust behind a reverse proxy that might forward an arbitrary
   `X-Forwarded-For`.
3. **Bootstrap code via CLI or SSH:** `koda install --headless` prints a setup code. If you need
   to recover it manually, SSH in and read `${STATE_ROOT_DIR}/control_plane/bootstrap.txt`
   (mode `0600`) inside the app container, then paste it into `/setup`. The file is deleted
   after successful registration.
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
10. **`CONTROL_PLANE_API_TOKEN`** is generated by the packaged installer for break-glass CLI
    operations. Do not expose it to browsers or use it as the daily operator login.

## Post-Install Validation

Run:

```bash
python3 scripts/doctor.py --env-file .env --base-url http://127.0.0.1:8090 --dashboard-url http://127.0.0.1:3000
```

Then finish product configuration through `/control-plane` in the dashboard.

## Upgrade Path

- install the new npm CLI release or run `npx @openkodaai/koda@latest update`
- rerun `koda update`
- let the CLI run doctor checks and rollback automatically if the new bundle is unhealthy
- verify control-plane health and setup status

## Existing Bundled Object-Storage Installs

If you are migrating an older quickstart deployment from the previous bundled object-storage backend, follow the explicit migration guide before changing the S3 endpoint:

- [Object storage migration](object-storage-migration.md)
