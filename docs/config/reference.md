# Configuration Reference

Koda separates platform bootstrap from product configuration.

```text
.env / Docker
  -> infrastructure, secrets-at-rest, service addresses

Control Plane
  -> providers, agents, prompts, tools, integrations, runtime policy
```

## Bootstrap Variables

### Control Plane And Auth

- `CONTROL_PLANE_ENABLED`
- `CONTROL_PLANE_BIND`
- `CONTROL_PLANE_PORT`
- `CONTROL_PLANE_API_TOKEN`
- `WEB_OPERATOR_SESSION_SECRET`
- `CONTROL_PLANE_MASTER_KEY_FILE`
- `CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH`
- `CONTROL_PLANE_RECOVERY_CODES_PER_USER`

Security notes:

- `CONTROL_PLANE_API_TOKEN` is for break-glass and CLI use, not browser login.
- `WEB_OPERATOR_SESSION_SECRET` must be stable or browser sessions are invalidated on restart.
- `ALLOW_INSECURE_WEB_OPERATOR_SESSION_SECRET` and `ALLOW_INSECURE_COOKIES` are development-only escape hatches.

### Runtime And State

- `STATE_BACKEND`
- `STATE_ROOT_DIR`
- `RUNTIME_EPHEMERAL_ROOT`
- `ARTIFACT_STORE_DIR`
- `OBJECT_STORAGE_REQUIRED`
- `RUNTIME_LOCAL_UI_TOKEN`
- `RUNTIME_KERNEL_SOCKET`
- `PLAYWRIGHT_BROWSERS_PATH`

### Postgres

- `KNOWLEDGE_V2_POSTGRES_DSN`
- `KNOWLEDGE_V2_POSTGRES_SCHEMA`
- `KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE`
- `KNOWLEDGE_V2_POSTGRES_POOL_MIN_IDLE`
- `KNOWLEDGE_V2_POSTGRES_ACQUIRE_TIMEOUT_MS`
- `KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS`
- `KODA_RETRIEVAL_POSTGRES_POOL_MAX_SIZE`
- `KODA_MEMORY_POSTGRES_POOL_MAX_SIZE`
- `KODA_ARTIFACT_POSTGRES_POOL_MAX_SIZE`

### Object Storage

- `KNOWLEDGE_V2_STORAGE_MODE`
- `KNOWLEDGE_V2_S3_BUCKET`
- `KNOWLEDGE_V2_S3_PREFIX`
- `KNOWLEDGE_V2_S3_ENDPOINT_URL`
- `KNOWLEDGE_V2_S3_REGION`
- `KNOWLEDGE_V2_S3_ACCESS_KEY_ID`
- `KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY`

The quickstart uses SeaweedFS, but the application contract is generic S3-compatible storage.

### Retrieval Quality

- `KNOWLEDGE_RETRIEVAL_MIN_QUALITY_TIER`
- `KNOWLEDGE_RETRIEVAL_DENSE_WINDOW`
- `KNOWLEDGE_RETRIEVAL_RERANK_TOP_K`
- `KNOWLEDGE_RETRIEVAL_VECTOR_COVERAGE_MIN`

Default production tier: `lexical_graph`. Dense and reranked modes require the matching embedding/reranker support.

## Configure In The Control Plane

Do not put these in per-agent `.env` files:

- provider credentials and verification
- global connection defaults
- integration health and account labels
- agent definitions and publication state
- prompt layers, templates, skills, and knowledge assets
- per-agent model/tool/runtime policy
- allowed users, channel access, and integration grants

Each agent still authorizes integrations through its published contract, even when a system-level connection exists.

### OpenRouter

OpenRouter is managed like the other OpenAI-compatible cloud providers: store
the user's own API key in the control plane, or bootstrap with env vars when
running headless.

- `OPENROUTER_ENABLED`
- `OPENROUTER_API_KEY`
- `OPENROUTER_AUTH_MODE`
- `OPENROUTER_CONNECTION_VERIFIED`
- `OPENROUTER_API_BASE_URL`
- `OPENROUTER_AVAILABLE_MODELS`
- `OPENROUTER_DEFAULT_MODEL`
- `OPENROUTER_MODEL_SMALL`
- `OPENROUTER_MODEL_MEDIUM`
- `OPENROUTER_MODEL_LARGE`
- `OPENROUTER_TIMEOUT`
- `OPENROUTER_FIRST_CHUNK_TIMEOUT`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_TITLE`
- `OPENROUTER_APP_CATEGORIES`

Defaults use `https://openrouter.ai/api/v1`, verify credentials through
`/key`, and discover model IDs through `/models`. Attribution headers are
optional, non-secret, and only sent when configured.

### Supertonic

Supertonic is a local voice provider. The initial model download uses Hugging
Face, then synthesis runs offline from `STATE_ROOT_DIR/providers/supertonic`
or `SUPERTONIC_ASSET_ROOT`. Preset voices `M1`-`M5` and `F1`-`F5` are bundled
with the model snapshot; custom Voice Builder JSON files can be imported
locally. Model assets are OpenRAIL-M; the Python package code is MIT.

- `SUPERTONIC_ENABLED`
- `SUPERTONIC_AVAILABLE_MODELS`
- `SUPERTONIC_DEFAULT_MODEL`
- `SUPERTONIC_DEFAULT_LANGUAGE`
- `SUPERTONIC_DEFAULT_VOICE`
- `SUPERTONIC_ASSET_ROOT`
- `SUPERTONIC_TOTAL_STEPS`
- `SUPERTONIC_SPEED`
- `SUPERTONIC_MAX_CHUNK_LENGTH`
- `SUPERTONIC_SILENCE_DURATION`
- `SUPERTONIC_INTRA_OP_THREADS`
- `SUPERTONIC_INTER_OP_THREADS`
- `SUPERTONIC_ONNX_PROVIDERS`
- `SUPERTONIC_COREML_EXPERIMENTAL`
- `SUPERTONIC_MODEL_REVISION`

CoreML acceleration is experimental and opt-in: set
`SUPERTONIC_COREML_EXPERIMENTAL=true` with `METAL_ENABLED=true` on Apple
Silicon. CPU ONNX remains the official default path.

References: [Supertonic GitHub](https://github.com/supertone-inc/supertonic),
[supertonic-py](https://supertone-inc.github.io/supertonic-py/),
[official voices](https://supertone-inc.github.io/supertonic-py/voices/), and
[Supertone/supertonic-3](https://huggingface.co/Supertone/supertonic-3).

## Public Management Surfaces

- `/setup`
- `/control-plane`
- `/api/control-plane/onboarding/status`
- `/api/control-plane/auth/*`
- `/api/control-plane/system-settings*`
- `/api/control-plane/providers/{provider_id}/connection*`
- `/api/control-plane/providers/supertonic/models*`
- `/api/control-plane/providers/supertonic/voices*`
- `/api/control-plane/integrations/{integration_id}/*`
- `/api/control-plane/agents*`
- `/api/runtime/*`
- [`../openapi/control-plane.json`](../openapi/control-plane.json)

## Examples

Local doctor:

```bash
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

Seed documentation demo data:

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
```
