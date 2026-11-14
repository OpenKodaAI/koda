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
  (`WEB_TRUSTED_PROXIES=gateway`). If your proxy forwards `/api/control-plane/*` straight to the
  API, as `proxy/nginx.conf` does, set `CONTROL_PLANE_TRUSTED_PROXIES=web,gateway`. With
  `WEB_PUBLISH_ADDRESS`, add your proxy's IP to `WEB_TRUSTED_PROXIES` and firewall the dashboard
  port so only the proxy reaches it.

## Update Behavior

- `koda update` swaps the release manifest, reapplies the stack, runs health checks, and rolls back
  automatically if the updated release does not become healthy.
