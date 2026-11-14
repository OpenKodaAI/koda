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

- terminate TLS
- send browser traffic to the Koda dashboard: `/`, `/setup`, `/login`, `/forgot-password`,
  `/control-plane`, and the browser-facing `/api/control-plane/*` and `/api/runtime/*` routes.
  Only the dashboard turns the HTTP-only session cookie into the API's bearer token, so browser
  requests sent straight to the API fail
- pass WebSocket upgrades on `/api/runtime/relay/*` (the runtime terminal and browser panels) to
  the dashboard, and keep those connections and the runtime event streams
  (`/api/runtime/agents/*/stream`) open while idle: neither sends a heartbeat
- pass the `Host` header the browser sent, port included, and the scheme in `X-Forwarded-Proto`:
  the dashboard accepts a sign-in or any other change only when its `Origin` matches them. Give a
  request that arrives without a `Host` (an HTTP/1.0 health check) your domain instead: the
  dashboard refuses an HTTP/1.1 request without one
- send to the control-plane API only the `/api/control-plane/*` requests that carry
  `Authorization: Bearer` (API-token clients), and `/openapi/control-plane.json`
- keep request bodies the dashboard gets to 1 MiB, nginx's default `client_max_body_size`: the
  dashboard buffers a request body (up to 10 MiB) before it checks the session, so a larger limit
  lets clients without a session make it hold large bodies. The dashboard's own photo uploads fit,
  as its photo editors send a cropped 512-pixel JPEG
- accept request bodies of up to 13 MiB on the two photo upload routes,
  `/api/control-plane/auth/profile/photo` and
  `/api/control-plane/dashboard/squads/threads/<id>/photo`, only when they carry
  `Authorization: Bearer` and go to the API: an API-token client may upload a profile or room
  photo of up to 12 MiB, sent as a multipart form, and the API checks the token before it reads
  the body. nginx checks a declared `Content-Length` against the location it selects, before an
  `if` inside that location runs, so the bundled `proxy/nginx.conf` checks the token in the
  `server` block: a rewrite sends those requests to an internal location with
  `client_max_body_size 13m;` (where nginx also checks a chunked body), and every other request
  keeps the default
- optionally keep `/control-plane/setup` as a compatibility redirect to `/setup`
- add the address each request came from to `X-Forwarded-For`, appended or replacing the header
  (see the rate-limit notes below)

Recommended model:

- Koda web listens on `127.0.0.1:${WEB_PORT:-3000}`
- Koda listens on `127.0.0.1:${CONTROL_PLANE_PORT:-8090}`
- your reverse proxy handles TLS and public routing
- product configuration remains inside the control plane instead of host env files

The bundled `proxy/nginx.conf` routes this way: browser requests go to `127.0.0.1:3000`, and
`/api/control-plane/*` requests with an `Authorization: Bearer` header, plus
`/openapi/control-plane.json`, go to `127.0.0.1:8090`. Only bearer tokens select the API, so HTTP
Basic auth added in front of Koda still sends browsers to the dashboard. It targets `127.0.0.1`
(not `localhost`, which may resolve to `::1` first while Koda publishes on IPv4 loopback only).
Include it in nginx's `http` context (for example `/etc/nginx/conf.d/koda.conf`), set
`server_name` to your domain, and add your TLS settings (`listen 443 ssl;` with `ssl_certificate`
and `ssl_certificate_key`). Then run `nginx -t` and reload nginx. The template ships with
`server_name _`, which matches no domain, so nginx sends your domain's requests to the default
server of the port. Where the distribution's stock site is enabled, that is the stock site: Debian
and Ubuntu ship `sites-enabled/default` with `listen 80 default_server`, and `nginx -t` then only
warns about a conflicting server name `_`. Keep your domain in `server_name`, or disable the stock
site.

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
and clients that send no header all share one bucket. Browser requests reach the API through
the dashboard, so the defaults charge each browser to its own address. Requests a proxy forwards
straight to the API, such as the API-token requests in the bundled `proxy/nginx.conf`, arrive
from the Docker gateway: set `CONTROL_PLANE_TRUSTED_PROXIES=web,gateway`, or all of them share
one budget. A proxy on another host needs its address added:
`WEB_TRUSTED_PROXIES=gateway,<proxy-ip>`.

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

If that proxy also forwards API-token requests (`/api/control-plane/*` with `Authorization: Bearer`)
straight to `app:8090`, add its service name to `CONTROL_PLANE_TRUSTED_PROXIES` (`web,proxy`), which
does accept hostnames. Browser requests must still go to the dashboard (`web:3000`), as above.

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
  does not work because session cookies are `Secure`, and the dashboard shows "HTTPS required"
  there instead of a sign-in form)
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
8. **Account lockout + rate limits** are already enforced — per client address (IPv6 per /64),
   for example 10 login attempts per 5 minutes, 10 password resets per hour and 10 recovery-code
   regenerations per hour, plus a per-account lockout after repeated failed logins. The full
   budget table and how the client address is determined behind a proxy are in
   [`../security/authentication.md`](../security/authentication.md#rate-limits-bucket-budgets).
   "Account does not exist", "wrong password", "locked account" and "invalid recovery code" all
   get the same generic error. A failed sign-in also takes the same time whichever the reason:
   every one does the same Argon2 work and answers no sooner than 300 ms. Password recovery is
   not padded that way yet, so rely on its per-client rate limit above to slow down a caller who
   probes identifiers through it.
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
