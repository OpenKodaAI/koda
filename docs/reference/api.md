# API Reference

Koda exposes a small number of public HTTP surfaces for dashboard setup, control-plane operations, and runtime inspection.

The canonical contract is maintained in:

- [`../openapi/control-plane.json`](../openapi/control-plane.json)

This document is a guide to the public shape of the platform, not a replacement for the OpenAPI file.

## Primary Surfaces

### Dashboard Setup

- `GET /control-plane/setup` on the Next.js web app
- `GET /control-plane` on the Next.js web app

Purpose:

- canonical first-boot configuration flow on `/control-plane/setup`
- control-plane home and catalog on `/control-plane` after auth/setup is complete
- operator session entry and ongoing product configuration inside the dashboard

### Compatibility Setup Bridge
- `GET /setup`

Purpose:

- compatibility page that points operators to `/control-plane/setup`
- bridge for older quickstart links and published reverse-proxy routes

### Control Plane

- `GET /api/control-plane/onboarding/status`
- `POST /api/control-plane/onboarding/bootstrap`
- `GET /api/control-plane/system-settings`
- `GET|PUT /api/control-plane/system-settings/general`
- `GET /api/control-plane/connections/catalog`
- `GET /api/control-plane/connections/defaults`
- `GET|PUT|DELETE /api/control-plane/connections/defaults/{connection_key}`
- `POST /api/control-plane/connections/defaults/{connection_key}/verify`
- `GET /api/control-plane/integrations/{integration_id}/health`
- `GET /api/control-plane/agents*`
- `POST /api/control-plane/providers/*`

Purpose:

- inspect setup status
- bootstrap or finalize product configuration
- manage agents, providers, integrations, secrets, and system-level settings

### Core Integration Defaults

The control plane now separates two different concerns for integrations:

- system-level connection defaults:
  - catalog and canonical connection state live under `/api/control-plane/connections/catalog` and `/api/control-plane/connections/defaults/{connection_key}`
  - health history for a given core integration remains available under `/api/control-plane/integrations/{integration_id}/health`
- bot-level authorization:
  - each bot still needs explicit grants in `resource_access_policy.integration_grants` inside its agent spec

Operationally, the expected lifecycle is:

1. inspect the unified connection catalog and pick the default connection key for the core integration, such as `core:jira` or `core:aws`
2. configure or update the connection default in the control plane
3. run `verify` so Koda records `status`, `checked_via`, `auth_expired`, and probe metadata
4. inspect `health` if the integration is degraded or if runtime authentication starts failing
5. grant the integration per bot through the agent editor or agent-spec API

Canonical core connection payloads are keyed by `connection_key`. Typical keys include:

- `core:browser`
- `core:jira`
- `core:confluence`
- `core:gws`
- `core:aws`
- `core:gh`
- `core:glab`

`status` is the canonical top-level state exposed by default connections. Typical values include:

- `not_configured`
- `configured`
- `verified`
- `error`

### Runtime

- `GET /api/runtime/*`

Purpose:

- inspect runtime state
- access runtime health and supervision surfaces
- expose operational runtime control APIs

## Intended Usage

- infrastructure bootstrap happens through Docker and `.env`
- product bootstrap happens through `/control-plane/setup` in the dashboard
- ongoing product management happens through the control plane and its HTTP APIs
- runtime operations are exposed through dedicated runtime routes, not mixed into setup endpoints

## Versioning And Stability

- the OpenAPI file is the source of truth for the public control-plane contract
- setup bridge and control-plane routes should stay stable for the unified frontend
- internal gRPC and service contracts are intentionally separate from this public HTTP layer
