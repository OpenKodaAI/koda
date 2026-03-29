# API Reference

Koda exposes a small number of public HTTP surfaces for setup, control-plane operations, and runtime inspection.

The canonical contract is maintained in:

- [`../openapi/control-plane.json`](../openapi/control-plane.json)

This document is a guide to the public shape of the platform, not a replacement for the OpenAPI file.

## Primary Surfaces

### Setup

- `GET /setup`

Purpose:

- first-boot onboarding UI
- bootstrap token entry
- operator-facing setup flow for control-plane-first installation

### Control Plane

- `GET /api/control-plane/onboarding/status`
- `POST /api/control-plane/onboarding/bootstrap`
- `GET /api/control-plane/system-settings`
- `GET /api/control-plane/agents*`
- `POST /api/control-plane/providers/*`

Purpose:

- inspect setup status
- bootstrap or finalize product configuration
- manage agents, providers, secrets, and system-level settings

### Runtime

- `GET /api/runtime/*`

Purpose:

- inspect runtime state
- access runtime health and supervision surfaces
- expose operational runtime control APIs

## Intended Usage

- infrastructure bootstrap happens through Docker and `.env`
- product bootstrap happens through `/setup`
- ongoing product management happens through the control plane and its HTTP APIs
- runtime operations are exposed through dedicated runtime routes, not mixed into setup endpoints

## Versioning And Stability

- the OpenAPI file is the source of truth for the public control-plane contract
- setup and control-plane routes should stay stable for the future unified frontend
- internal gRPC and service contracts are intentionally separate from this public HTTP layer
