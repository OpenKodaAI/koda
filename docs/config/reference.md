# Configuration Reference

Koda keeps infrastructure bootstrap and product configuration separate on purpose.

- `.env` is for platform bootstrap and shared infrastructure concerns
- the control plane owns product configuration after first boot

## Bootstrap Infrastructure Variables

### Control Plane

- `CONTROL_PLANE_ENABLED`
- `CONTROL_PLANE_BIND`
- `CONTROL_PLANE_PORT`
- `CONTROL_PLANE_AUTH_MODE`
- `CONTROL_PLANE_API_TOKEN`
- `RUNTIME_LOCAL_UI_TOKEN`
- `WEB_OPERATOR_SESSION_SECRET`
- `CONTROL_PLANE_MASTER_KEY_FILE`

## Security-Sensitive Bootstrap Variables

- `CONTROL_PLANE_AUTH_MODE` defaults to `token`. Use `development` only for the source/dev stack and treat `open` as a deliberate local-development override, not as a production setting.
- `CONTROL_PLANE_API_TOKEN` is the backend break-glass and recovery credential. Normal browser auth should use setup code exchange, local owner login, and HTTP-only sessions instead of exposing this token in the UI.
- `RUNTIME_LOCAL_UI_TOKEN` protects runtime inspection and attach access between the dashboard and the runtime.
- `WEB_OPERATOR_SESSION_SECRET` is required for stable HTTP-only operator sessions in the web dashboard. Without it, operator sessions would be invalidated on web restarts.
- `BROWSER_ALLOW_PRIVATE_NETWORK` should remain disabled unless runtime browser automation explicitly needs internal or localhost destinations.
- `ALLOW_INSECURE_WEB_OPERATOR_SESSION_SECRET` and `ALLOW_INSECURE_COOKIES` are development-only escape hatches and should not be used in production.

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
- core connection defaults, integration verification, and integration health
- allowed Telegram users and product access policy
- agent creation, publication, and defaults
- secrets and connection defaults
- per-agent models and runtime behavior
- prompt layers, templates, skills, and knowledge attachments

Global configuration and per-bot authorization are intentionally different layers:

- the control plane stores system-level provider connections and core connection defaults
- each bot still authorizes integrations through `resource_access_policy.integration_grants` in its agent spec

## Public Setup And Management Surfaces

- `/control-plane/setup`
- `/control-plane`
- `/setup`
- `/api/control-plane/onboarding/status`
- `/api/control-plane/onboarding/bootstrap`
- `/api/control-plane/auth/status`
- `/api/control-plane/auth/bootstrap/exchange`
- `/api/control-plane/auth/register-owner`
- `/api/control-plane/auth/login`
- `/api/control-plane/auth/logout`
- `/api/control-plane/auth/tokens*`
- `/api/control-plane/auth/sessions*`
- `/api/control-plane/web-auth`
- `/api/control-plane/system-settings`
- `/api/control-plane/system-settings/general`
- `/api/control-plane/connections/catalog`
- `/api/control-plane/connections/defaults*`
- `/api/control-plane/providers/{provider_id}/connection*`
- `/api/control-plane/integrations/{integration_id}/system`
- `/api/control-plane/integrations/{integration_id}/health`
- `/api/control-plane/agents*`
- `/api/runtime/*`
- [`../openapi/control-plane.json`](../openapi/control-plane.json)

## Operational Principles

- bootstrap infra should be stable before any product configuration is attempted
- object storage and Postgres are required platform dependencies, not optional local conveniences
- third-party hosting layers should stay thin and infrastructure-focused
- product state should be managed through Koda’s own control plane, not scattered host-level env files
- the web dashboard must authenticate operators with its own sealed session and must not inherit privileged backend tokens
