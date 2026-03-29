# Configuration Reference

Koda keeps infrastructure bootstrap and product configuration separate on purpose.

- `.env` is for platform bootstrap and shared infrastructure concerns
- the control plane owns product configuration after first boot

## Bootstrap Infrastructure Variables

### Control Plane

- `CONTROL_PLANE_ENABLED`
- `CONTROL_PLANE_BIND`
- `CONTROL_PLANE_PORT`
- `CONTROL_PLANE_API_TOKEN`
- `RUNTIME_LOCAL_UI_TOKEN`
- `CONTROL_PLANE_MASTER_KEY`
- `CONTROL_PLANE_MASTER_KEY_FILE`

### Runtime And State

- `STATE_BACKEND`
- `STATE_ROOT_DIR`
- `RUNTIME_EPHEMERAL_ROOT`
- `ARTIFACT_STORE_DIR`
- `OBJECT_STORAGE_REQUIRED`

### Postgres

- `KNOWLEDGE_V2_POSTGRES_DSN`
- `KNOWLEDGE_V2_POSTGRES_SCHEMA`
- any platform-level Postgres connectivity overrides you intentionally manage outside the default quickstart

### Object Storage

- `KNOWLEDGE_V2_STORAGE_MODE`
- `KNOWLEDGE_V2_S3_BUCKET`
- `KNOWLEDGE_V2_S3_PREFIX`
- `KNOWLEDGE_V2_S3_ENDPOINT_URL`
- `KNOWLEDGE_V2_S3_REGION`
- `KNOWLEDGE_V2_S3_ACCESS_KEY_ID`
- `KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY`

The official quickstart uses SeaweedFS as the bundled storage backend, but the application contract remains generic S3-compatible storage.

## Configure Through The Control Plane

These settings belong in the control plane, not in `.env`:

- provider credentials and provider verification
- allowed Telegram users and product access policy
- agent creation, publication, and defaults
- secrets and integration credentials
- per-agent models and runtime behavior
- prompt layers, templates, skills, and knowledge attachments

## Public Setup And Management Surfaces

- `/setup`
- `/api/control-plane/onboarding/status`
- `/api/control-plane/onboarding/bootstrap`
- `/api/control-plane/system-settings`
- `/api/control-plane/providers/{provider_id}/connection*`
- `/api/control-plane/agents*`
- `/api/runtime/*`
- [`../openapi/control-plane.json`](../openapi/control-plane.json)

## Operational Principles

- bootstrap infra should be stable before any product configuration is attempted
- object storage and Postgres are required platform dependencies, not optional local conveniences
- third-party hosting layers should stay thin and infrastructure-focused
- product state should be managed through Koda’s own control plane, not scattered host-level env files
