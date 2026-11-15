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
- `CONTROL_PLANE_BIND` — native runs only; Docker Compose binds `0.0.0.0` inside the container
- `CONTROL_PLANE_PORT` — host port the control plane is published on (loopback only); the
  container always listens on 8090
- `CONTROL_PLANE_PUBLIC_PORT` — set by Docker Compose to the published port for host-facing URLs
  (OAuth relay); native runs fall back to `CONTROL_PLANE_PORT`
- `WEB_PUBLISH_ADDRESS` — address the dashboard is published on (default `127.0.0.1`); change it
  only for a TLS-terminating proxy on another host, never for plain-HTTP access. Then add that
  proxy to `WEB_TRUSTED_PROXIES` and firewall the port so only the proxy can reach it: a client
  that reaches the port directly is rate limited by the address Docker shows, which is the
  trusted gateway under Docker Desktop, rootless Docker or Docker's userland proxy
- `CONTROL_PLANE_TRUSTED_PROXIES` — peers whose `X-Forwarded-For` the API rate limiter
  believes: comma-separated IPs, CIDRs, hostnames, or `gateway` (the container's Docker
  gateway, where a proxy on the Docker host connects from). Default `127.0.0.1,::1`; Docker
  Compose sets `web`, the dashboard. Use `web,gateway` only if a proxy on the host forwards
  straight to the API. Unusable entries are logged at startup and ignored; see
  [Authentication](../security/authentication.md#which-address-a-request-is-charged-to)
- `WEB_TRUSTED_PROXIES` — read by the dashboard server (`apps/web/server.mjs`): peers whose
  `X-Forwarded-For` it believes besides loopback, as IPs, CIDRs or `gateway` (no hostnames: a
  proxy container on the Compose network needs a fixed `ipv4_address`, see
  [VPS Install](../install/vps.md#reverse-proxy)). Unset natively;
  Docker Compose sets `gateway` so a reverse proxy on the host keeps per-client limits. Every
  other peer is charged to its own address, whatever header it sends
- `CONTROL_PLANE_API_TOKEN`
- `WEB_OPERATOR_SESSION_SECRET`
- `CONTROL_PLANE_MASTER_KEY_FILE` — the Fernet key that encrypts stored secrets (default
  `${STATE_ROOT_DIR}/control_plane/.master.key`). Only the control plane creates it, on a fresh install; Postgres
  records its fingerprint and the control plane refuses to start without it while secrets exist, or with a different
  key. See [Master key recovery](../operations/backup-restore.md#master-key-recovery)
- `CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE` — the key in use before a rotation (default
  `${STATE_ROOT_DIR}/control_plane/.master-previous.key`, read only when the file exists): secrets still encrypted
  with it keep decrypting, and startup accepts the new key because this one matches the recorded fingerprint. See
  [Master key rotation](../operations/hardening.md#master-key-rotation)
- `CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH`
- `CONTROL_PLANE_RECOVERY_CODES_PER_USER`
- `CONTROL_PLANE_BOOTSTRAP_CODE` — a fixed first-boot setup code in place of the generated one the
  control plane writes to `${STATE_ROOT_DIR}/control_plane/bootstrap.txt` (unset by default, which is
  recommended). Only its ASCII letters and digits count. The `/setup` screen takes at most 12
  characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no `I`, `O`, `0` or `1`), so give it exactly
  12 of those; any other seed works only through `POST /api/control-plane/auth/register-owner`, and
  the control plane logs `bootstrap_code_seed_weak` or `bootstrap_code_seed_not_typeable` for it.
  Read natively and by the repository's Docker Compose; the release bundle's Compose file does not
  pass it, so an npm install uses the generated code `koda install` prints. See
  [Authentication](../security/authentication.md#account-creation-first-boot)

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

### Outbound Network

These outbound requests go through the SSRF guard in `koda/services/http_client.py`: agent
web tools, link previews and artifact downloads, MCP HTTP servers, generated-image
downloads, OpenAI-compatible providers and their key checks, Ollama chat, the local Ollama
connection check and the Ollama model catalog, and the agent runtime API. On each of them
the guard speaks http and https only and does not use the `*_proxy` environment variables.
Unless a private-network grant applies, it reaches public unicast addresses only, and
connects only to the addresses it checked. Endpoints the operator configures
(`OLLAMA_BASE_URL`, a provider base URL other than the vendor's, the runtime API) hold such
a grant and may be on a private network; MCP servers get one only through
`MCP_ALLOWED_PRIVATE_NETWORKS` below. Redirects depend on the path:

- MCP HTTP servers, generated-image downloads, those Ollama calls, the runtime API and the
  key check of an OpenAI-compatible provider follow no redirect to another origin, so a
  configured private endpoint's redirects never leave it.
- Agent web tools, link previews and artifact downloads check every redirect hop again and
  may follow it to another public origin.
- An OpenAI-compatible provider's vendor endpoint follows no redirect; a base URL the
  operator set follows redirects (see the
  [guardrail test matrix](../security/guardrail-test-matrix.md)).

Not covered yet, and still using Python's `urllib` (which honours `*_proxy` and follows
redirects): MCP OAuth discovery, registration and token requests, the local llama.cpp and
MLX runtime supervisor, and requests to fixed vendor hosts such as the API-key checks for
Claude, Codex, Gemini, ElevenLabs and Ollama Cloud.

- `MCP_ALLOWED_PRIVATE_NETWORKS` — private networks remote (HTTP) MCP servers may be
  reached on, as comma-separated CIDRs. A host is refused if any of its DNS answers is
  neither public nor in the list, and a Tailscale tailnet gives every node an IPv4 and an
  IPv6 address, so a tailnet needs both ranges, `100.64.0.0/10,fd7a:115c:a1e0::/48`, or
  better each server's own `/32` and `/128`. Unset, MCP servers must be on public addresses.
  Loopback, link-local, unspecified and multicast addresses and the cloud metadata addresses
  `100.100.100.200` and `fd00:ec2::254` are never granted, whatever the list covers; any
  other address in the list is, so keep it narrow. Entries that are not CIDRs are logged and
  ignored. Set it in the `.env` Docker Compose reads: the install's `.env` for the npm/release
  install (the release Compose file passes it to the control plane; run `koda up` after a
  change), or the checkout's `.env` for a source install. The control plane checks
  registrations against it and passes it on to every agent worker

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

`KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS` (default `30000`) limits each query. The schema
migrations that run at startup and in `koda migrate` have no time limit, because an index
build on a large table can take longer than any query. The control plane applies them before
it starts serving, and waits for them however long they take: the
`PRIMARY_STATE_BRIDGE_TIMEOUT_SECONDS` limit (default `30`) of its other database calls does
not apply. Its database health check does stop waiting after that limit and reports the
database not ready, but the migrations it started keep running to the end.

The Python workers open each Postgres connection with `search_path` set to
`KNOWLEDGE_V2_POSTGRES_SCHEMA` as a startup parameter, followed by the database or role
default `search_path` (where extension types such as `vector` are found), and their state
queries rely on it to find their tables. A connection pooler between the workers and
Postgres must forward that parameter. With PgBouncer, list `search_path` in
`track_extra_parameters` (PgBouncer 1.20 or later; use 1.25.1 or later, which fixes a
vulnerability in that configuration) and never in `ignore_startup_parameters`, which
drops it. PgBouncer releases before 1.26 refuse the connection without that setting.

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
