# Koda Release Notes

## Authentication

- Browser auth now starts with a short-lived setup code.
- The first successful setup code exchange creates an owner-registration session.
- Operators then sign in with the local owner account and receive an HTTP-only browser session.
- `CONTROL_PLANE_API_TOKEN` remains break-glass and recovery only.

## Installation

- The official product path is now `npm install -g @openkodaai/koda` or `npx @openkodaai/koda@latest install`.
- Releases ship only the runtime bundle: compose, manifest, bootstrap env template, migration notes,
  proxy template, and SBOM metadata.
- The npm package embeds that exact product bundle, while GitHub Releases mirror the same archive and checksums.
- Developer hot-reload stays in the source repository and is not part of the product bundle.

## Network Exposure

- The dashboard (`WEB_PORT`, default 3000) and the control-plane API (`CONTROL_PLANE_PORT`,
  default 8090) are now published on the host's loopback interface only. Earlier bundles published
  both on every interface.
- After `koda update`, anything that reached those ports from another machine (a reverse proxy or
  load balancer on another host, external monitoring of `:8090`) stops working. Put a TLS reverse
  proxy on the Koda host (the bundled `proxy/nginx.conf` targets `127.0.0.1`), or set
  `WEB_PUBLISH_ADDRESS` in `.env` to publish the dashboard on a specific address (served over TLS:
  operator session cookies are `Secure`). The control-plane API is not published beyond loopback.
- `CONTROL_PLANE_PORT` now only selects the published host port; the container always listens on
  8090 internally, so non-default ports work end to end.
- Login, recovery and setup are now rate limited per client address. `X-Forwarded-For` is believed
  only from trusted peers: the API trusts the dashboard (`CONTROL_PLANE_TRUSTED_PROXIES=web`) and
  the dashboard trusts the Docker gateway a proxy on this host connects from
  (`WEB_TRUSTED_PROXIES=gateway`). If your proxy forwards requests straight to the API, as
  `proxy/nginx.conf` does for API-token requests, set `CONTROL_PLANE_TRUSTED_PROXIES=web,gateway`.
  With `WEB_PUBLISH_ADDRESS`, add your proxy's IP to `WEB_TRUSTED_PROXIES` and firewall the
  dashboard port so only the proxy reaches it.
- `proxy/nginx.conf` now follows the auth model. Earlier templates sent `/setup`,
  `/api/control-plane/*` and `/api/runtime/*` straight to the API, so browser sign-in, the runtime
  terminal and browser panels, and per-client login limits failed through them. The template now
  sends pages and every browser API call to the dashboard, passes WebSocket upgrades on
  `/api/runtime/relay/`, and sends only `/api/control-plane/*` requests carrying
  `Authorization: Bearer` (API tokens) and `/openapi/control-plane.json` to the API. It also passes
  the browser's `Host` with its port (`$http_host`), so sign-in works behind a non-default port,
  sends the `server_name` for a request without a `Host` (an HTTP/1.0 health check), keeps idle
  runtime event streams open, and accepts request bodies of up to 13 MiB on the two photo upload
  routes (`/api/control-plane/auth/profile/photo` and
  `/api/control-plane/dashboard/squads/threads/<id>/photo`), where nginx's default of 1 MiB
  refused photo uploads over 1 MiB. Every other route keeps that default.
  `koda update` does not change a copy installed in nginx:
  replace that copy with the new template, keeping your `server_name` and TLS settings, then run
  `nginx -t` and reload nginx.

## MCP Servers On Private Networks

- Remote (HTTP) MCP servers are now reached on public addresses only, and the address check is
  stricter: `100.64.0.0/10` (Tailscale and other carrier-grade NAT ranges) counts as private, and
  an IPv4-mapped or NAT64 IPv6 address is judged by the IPv4 address it carries. Earlier releases
  accepted an MCP server at a `100.64.0.0/10` address.
- After `koda update`, an MCP server on such an address, or on any other private network, is
  refused (`Private/internal IP not allowed`) both when it is registered and when an agent
  connects to it. To keep using it, list its networks in `MCP_ALLOWED_PRIVATE_NETWORKS` in the
  install's `.env`, as comma-separated CIDRs: for a tailnet both
  `100.64.0.0/10,fd7a:115c:a1e0::/48`, or better each server's own `/32` and `/128`. Then run
  `koda up`. The control plane passes the grant on to every agent worker. Loopback, link-local and
  cloud metadata addresses are never granted.

## Update Behavior

- `koda update` swaps the release manifest, reapplies the stack, runs health checks, and rolls back
  automatically if the updated release does not become healthy.
