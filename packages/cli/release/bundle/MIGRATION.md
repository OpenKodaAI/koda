# Koda Release Notes

## Authentication

- Browser auth now starts with a short-lived setup code.
- The first successful setup code exchange creates an owner-registration session.
- Operators then sign in with the local owner account and receive an HTTP-only browser session.
- `CONTROL_PLANE_API_TOKEN` remains break-glass and recovery only.

## Installation

- The official product path is now `npm install -g koda` or `npx koda@latest install`.
- Releases ship only the runtime bundle: compose, manifest, bootstrap env template, migration notes,
  proxy template, and SBOM metadata.
- Developer hot-reload stays in the source repository and is not part of the product bundle.

## Update Behavior

- `koda update` swaps the release manifest, reapplies the stack, runs health checks, and rolls back
  automatically if the updated release does not become healthy.
