# Configuration And Prompts

Configuration and prompt behavior is centralized, layered, and heavily environment-driven.

Use [`repo-map.yaml`](repo-map.yaml) for the quick index of configuration surfaces, owning paths, and related tests. Use [`llm-compatibility.md`](llm-compatibility.md) for provider entrypoints and compatibility rules. Use this document for the narrative rules and layering details.

## Configuration Source Of Truth

[`../../koda/config.py`](../../koda/config.py) is the source of truth for:

- feature flags
- provider enablement, model catalogs, fallback order, and CLI execution defaults
- shared and per-agent environment variables
- path namespacing
- blocked-command patterns
- prompt building
- defaults for budgets, timeouts, tools, memory, browser, TTS, and integrations

[`../../koda/control_plane/settings.py`](../../koda/control_plane/settings.py) owns control-plane settings (auth mode, rate limits, session TTL, master-key files). It also hosts first-run auth policy: `KODA_ENV`, `ALLOW_LOOPBACK_BOOTSTRAP`, `CONTROL_PLANE_BOOTSTRAP_CODE`, `CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH` (default 12), and `CONTROL_PLANE_RECOVERY_CODES_PER_USER` (default 10). `KODA_ENV=production` hard-fails when `CONTROL_PLANE_AUTH_MODE ∈ {development, open}` or `ALLOW_LOOPBACK_BOOTSTRAP=true`.

Avoid adding direct `os.environ` reads outside these files unless there is a clear reason.

[`../../koda/memory/config.py`](../../koda/memory/config.py) is the source of truth for memory-specific provider/model selection, including which provider performs post-response extraction.

## Multi-Agent Lookup Model

The helper functions `_env` and `_env_required` implement a two-step lookup:

1. if `AGENT_ID` is set, look for `{AGENT_ID}_{KEY}`
2. otherwise, fall back to the shared key

This pattern is used for core runtime settings and many integrations.

The same lookup rules now apply to provider-aware settings such as `DEFAULT_PROVIDER`, provider model catalogs, Codex CLI execution settings, and fallback ordering.

## Namespaced Runtime Paths

When `AGENT_ID` is present, these paths become agent-specific:

- temporary image directory
- runtime scratch roots and control-plane materialization directories

The stateless/Postgres-first rollout also moves these defaults outside the repository root. Runtime workspaces, temp image directories, artifact caches, and control-plane snapshots should be ephemeral or state-root scoped rather than persisted inside the git checkout.

## Provider-Aware Execution Config

The runtime is now provider-neutral at the orchestration level.

- `DEFAULT_PROVIDER` selects the initial provider preference for a user or agent.
- `CLAUDE_ENABLED` and `CODEX_ENABLED` gate provider availability.
- `CLAUDE_AVAILABLE_MODELS`, `CODEX_AVAILABLE_MODELS`, `GEMINI_AVAILABLE_MODELS`, `OLLAMA_AVAILABLE_MODELS`, and the corresponding small/medium/large tier env vars define the router catalog per provider.
- `CLAUDE_DEFAULT_MODEL`, `CODEX_DEFAULT_MODEL`, `GEMINI_DEFAULT_MODEL`, and `OLLAMA_DEFAULT_MODEL` define the default explicit model within each provider. `DEFAULT_MODEL` remains as a legacy fallback for provider-specific setups.
- `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, and `OLLAMA_TIMEOUT` define whether the Ollama runtime should connect to a local/server endpoint or an API-key-backed cloud endpoint.
- `MODEL_FUNCTION_DEFAULTS_JSON` maps global defaults by capability or media function (for example `general`, `image`, `video`, `audio`, `transcription`, `music`). This is the system-wide source of truth used by the dashboard “model defaults by functionality” section.
- `PROVIDER_FALLBACK_ORDER` defines the order used when the active provider cannot start or continue a task.
- `TRANSCRIPT_REPLAY_LIMIT` caps how much canonical transcript is replayed when the runtime has to bootstrap a different provider mid-session.
- `CODEX_BIN`, `CODEX_TIMEOUT`, `CODEX_FIRST_CHUNK_TIMEOUT`, `CODEX_SANDBOX`, `CODEX_APPROVAL_POLICY`, and `CODEX_SKIP_GIT_REPO_CHECK` control the Codex CLI adapter.
- `RUNTIME_BROWSER_TRANSPORT` selects the live browser transport. Use `novnc` for Linux/Xvfb-backed remote viewing and `local_headful` for local desktop testing without the Linux sidecars.
- `MODEL_PRICING_USD` optionally maps model names to per-million-token pricing so usage-only providers can still participate in cost reporting.
- `MEMORY_EXTRACTION_PROVIDER` and `MEMORY_EXTRACTION_MODEL` decouple memory extraction from the main interactive provider.
- `SCHEDULER_ENABLED`, `SCHEDULER_POLL_INTERVAL_SECONDS`, `SCHEDULER_LEASE_SECONDS`, `SCHEDULER_MAX_CATCHUP_PER_CYCLE`, `SCHEDULER_MAX_DISPATCH_PER_CYCLE`, `SCHEDULER_CATCHUP_WINDOW_HOURS`, `SCHEDULER_RUN_MAX_ATTEMPTS`, `SCHEDULER_RETRY_BASE_DELAY`, `SCHEDULER_RETRY_MAX_DELAY`, `SCHEDULER_NOTIFICATION_MODE`, and `SCHEDULER_DEFAULT_TIMEZONE` control the unified scheduler dispatcher, retry policy, catch-up window, and notifications.
- `MAX_QUEUED_TASKS_PER_USER` and `QUEUE_MAX_RECOVERY_ATTEMPTS` control queue admission pressure for one user plus how many startup recoveries a persisted queue item can attempt before it is escalated to the DLQ instead of looping indefinitely.
- `JIRA_DEEP_CONTEXT_ENABLED` and `JIRA_DEEP_CONTEXT_MAX_ISSUES` control proactive Jira dossier construction during queue preparation.
- `ARTIFACT_EXTRACTION_TIMEOUT` and `ARTIFACT_EXTRACTION_VERSION` control artifact extraction time-bounds and cache invalidation for PDFs, DOCX, spreadsheets, OCR, audio, and video analysis.
- `KNOWLEDGE_GRAPH_ENABLED` and `KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED` control whether graph-aware retrieval with multimodal evidence persistence is enabled.
- `KNOWLEDGE_SOURCE_GLOBS` and `KNOWLEDGE_WORKSPACE_SOURCE_GLOBS` control which documentation-style files are scanned into grounded knowledge. Agent prompt contracts come from control-plane documents and are not part of the workspace knowledge source of truth.
- `KNOWLEDGE_V2_ENABLED`, `KNOWLEDGE_V2_MAX_GRAPH_HOPS`, `KNOWLEDGE_V2_CROSS_ENCODER_MODEL`, and `KNOWLEDGE_V2_STORAGE_MODE` enable the graph-native retrieval v2 path, its hop budget, the optional cross-encoder reranker used for top-k refinement, and the storage mode (`off` or `primary`).
- `KNOWLEDGE_PACK_TOML` remains a local compatibility seed only. It is ignored once external or primary knowledge storage is enabled and is not part of the Postgres-first source of truth.
- `KNOWLEDGE_V2_OBJECT_STORE_ROOT`, `KNOWLEDGE_V2_POSTGRES_DSN`, `KNOWLEDGE_V2_POSTGRES_SCHEMA`, `KNOWLEDGE_V2_POSTGRES_POOL_MIN_SIZE`, `KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE`, `KNOWLEDGE_V2_POSTGRES_START_RETRIES`, `KNOWLEDGE_V2_POSTGRES_RETRY_BASE_SECONDS`, and `KNOWLEDGE_V2_EMBEDDING_DIMENSION` control the primary storage path for local manifests, PostgreSQL/pgvector persistence, backend pool sizing, startup retry behavior, and the configured embedding dimension used for vector columns.
- `KNOWLEDGE_V2_S3_BUCKET`, `KNOWLEDGE_V2_S3_PREFIX`, `KNOWLEDGE_V2_S3_ENDPOINT_URL`, `KNOWLEDGE_V2_S3_REGION`, `KNOWLEDGE_V2_S3_ACCESS_KEY_ID`, and `KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY` configure optional S3-compatible object-storage mirroring in a cloud-agnostic way.
- `KNOWLEDGE_V2_OTEL_ENABLED`, `KNOWLEDGE_V2_INGEST_WORKER_ENABLED`, `KNOWLEDGE_V2_INGEST_POLL_SECONDS`, `KNOWLEDGE_V2_INGEST_LEASE_SECONDS`, and `KNOWLEDGE_V2_INGEST_BATCH_LIMIT` enable OpenTelemetry spans plus the async knowledge ingest worker, its polling cadence, lease duration, and per-cycle batch size; `KNOWLEDGE_V2_NEO4J_URI`, `KNOWLEDGE_V2_NEO4J_USER`, and `KNOWLEDGE_V2_NEO4J_PASSWORD` remain legacy/experimental graph-projection knobs and are not required for the current Postgres-first rollout.
- `KNOWLEDGE_SEMANTIC_JUDGE_ENABLED` and `KNOWLEDGE_SEMANTIC_JUDGE_SUPPORT_THRESHOLD` control the heuristic semantic judge that augments deterministic runtime validation before answer promotion and write confirmation.
- `KNOWLEDGE_ALLOWED_SOURCE_LABELS` and `KNOWLEDGE_ALLOWED_WORKSPACE_ROOTS` constrain retrieval to approved source labels and workspace roots when an agent must stay inside a narrower knowledge boundary.
- `KNOWLEDGE_TRACE_SAMPLING_RATE` and `KNOWLEDGE_CITATION_POLICY` control explainability persistence and whether grounded answers must cite their winning sources. Evaluation replay is no longer an operational configuration surface for the Rust-authoritative retrieval path.

## Dynamic Control Plane

The dynamic control plane is the versioned source of truth for agent definitions, compiled prompt documents, memory profiles, knowledge packs, runtime documents, secrets, and publication/apply state.

- `launcher.py` now starts the control-plane supervisor instead of a hardcoded agent list.
- Workers still run through [`../../koda/__main__.py`](../../koda/__main__.py), but their effective runtime configuration is injected from the published control-plane snapshot before the normal runtime imports occur.
- `CONTROL_PLANE_RUNTIME_DIR`, `CONTROL_PLANE_BIND`, `CONTROL_PLANE_PORT`, `CONTROL_PLANE_POLL_INTERVAL_SECONDS`, `CONTROL_PLANE_RESTART_GRACE_SECONDS`, and `CONTROL_PLANE_STARTUP_GRACE_SECONDS` configure the supervisor and its snapshot/bootstrap behavior.
- `CONTROL_PLANE_API_TOKEN` is the break-glass/bootstrap credential. The preferred browser path is setup-code exchange, local owner login, and an HTTP-only session; `/api/control-plane/web-auth` remains a temporary compatibility bridge for legacy token-based installs.
- Secrets stay encrypted at rest and are masked in list-style API responses. If a raw secret is needed for server-to-server runtime access, resolve it through the applied control-plane snapshot rather than rediscovering it from `.env`.
- Agent identity and instruction layers are first-class control-plane documents: `identity_md`, `soul_md`, `system_prompt_md`, `instructions_md`, `rules_md`, `voice_prompt_md`, `image_prompt_md`, and `memory_extraction_prompt_md`.
- The operational runtime contract is the compiled prompt generated from those documents and exposed through `/api/control-plane/agents/{agent_id}/compiled-prompt`. Repository prompt files are not part of the live source of truth for agent behavior.
- Canonical RAG content is stored as control-plane knowledge assets plus the `knowledge` section. Use per-asset metadata for entry-level provenance (`scope`, `criticality`, `owner`, `freshness_days`, `project_key`, `environment`, `team`, `tags`) and `knowledge.pack_metadata` for pack-level defaults such as `owner`, `freshness_days`, and environment scoping.
- Prompt layers, skills, templates, and related runtime documents are injected as inline environment payloads. The operational runtime path no longer depends on a materialized prompt directory or per-agent prompt files under the repository.

## Prompt Layers

### Base Runtime Prompt

`DEFAULT_SYSTEM_PROMPT` is assembled in [`../../koda/config.py`](../../koda/config.py). It includes:

- environment context
- response-format rules
- artifact creation rules
- voice-mode guidance
- authorship rules
- engineering and validation expectations
- integration-specific sections when enabled

The base prompt is shared across providers. Provider-specific CLI flags and resume semantics live in the runner layer, not in the prompt assets.

### Per-Agent Compiled Prompt

The materialized agent prompt is composed from the published control-plane document layers in this order:

1. `identity_md`
2. `soul_md`
3. `system_prompt_md`
4. `instructions_md`
5. `rules_md`

The composed agent prompt is wrapped in structured tags before being prepended to the shared platform prompt. This keeps agent identity, style, instructions, and hard rules editable without changing code while preserving later platform/runtime safety rules as the authoritative layer on conflict.

Repository prompt files are not part of the operational prompt contract.

### Global Defaults Versus Per-Agent Overrides

Global system settings can now define a default provider/model per functionality through `MODEL_FUNCTION_DEFAULTS_JSON`. Examples include:

- `general` for the main conversational or agentic runtime model
- `image` for image generation/editing
- `video` for video generation
- `audio` for TTS or generative audio
- `transcription` for speech-to-text
- `music` for music and soundtrack generation

Each agent can still override those defaults through `model_policy.functional_defaults` inside `AGENT_MODEL_POLICY_JSON` or the control-plane AgentSpec editor. Agent-local overrides must remain isolated from the global system settings; if an agent sets its own `functional_defaults`, those values win only inside that agent's materialized runtime.

Per-agent tool scope still uses `AGENT_TOOL_POLICY_JSON` and `AGENT_ALLOWED_TOOLS` for coarse tool selection, while granular integration scope is materialized through `AGENT_RESOURCE_ACCESS_POLICY_JSON`. The runtime must treat `resource_access_policy.integration_grants` as the source of truth for per-integration actions, domains, database environments, shared env keys, and secret grants.

### Per-Query Prompt Assembly

Inside [`../../koda/services/queue_manager.py`](../../koda/services/queue_manager.py), the effective runtime prompt is built in this order:

1. `DEFAULT_SYSTEM_PROMPT`
2. optional user-specific `/system` addition
3. optional voice-active prompt
4. optional recalled memory context
5. agent tool prompt from [`../../koda/services/tool_prompt.py`](../../koda/services/tool_prompt.py)
6. runtime skills-awareness prompt from [`../../koda/services/templates.py`](../../koda/services/templates.py)

If you change one layer, make sure the order still makes sense.

When Jira deep context is enabled, `_prepare_query_context` also appends one or more `<artifact_context>` blocks built from proactive issue dossiers and typed Telegram artifact bundles. These blocks are explicitly untrusted context and can force the task into read-only mode when critical extraction gaps remain.

After prompt assembly, execution is routed through [`../../koda/services/llm_runner.py`](../../koda/services/llm_runner.py), which selects the provider adapter, preserves the canonical agent session, and applies transparent fallback if the active provider fails during startup or resume.

For scheduled agent jobs, the same prompt assembly path is reused through [`../../koda/services/queue_manager.py`](../../koda/services/queue_manager.py). Validation runs append explicit dry-run instructions and block write-capable tools that do not support safe simulation.

## Runtime Skills Versus Developer-Agent Skills

There are two different “skill” systems in this repository.

### Runtime Skills

- Stored in [`../../koda/skills`](../../koda/skills)
- Loaded by [`../../koda/services/templates.py`](../../koda/services/templates.py)
- Exposed to end users through `/skill`
- Written as prompt templates for the selected provider running inside the agent

### Repository Guidance Skills

- Stored in [`skills`](skills)
- Intended for modern LLM tooling working on this repository
- Refer to the repository docs under [`../`](../)
- Use `SKILL.md` as the canonical provider-neutral instruction file
- Use `agents/openai.yaml` only as optional Codex metadata
- Must not change the runtime `/skill` behavior

## Config Change Checklist

When adding or changing configuration:

1. update [`../../koda/config.py`](../../koda/config.py)
2. update [`.env.example`](../../.env.example) if the setting is user-configurable
3. update the relevant docs in [`../`](../)
4. add or update tests for the new branch or safety rule

## Prompt Change Checklist

When changing prompts:

1. decide whether the change belongs in compiled control-plane documents, runtime skills, or repository guidance docs
2. keep operational prompt language aligned with product needs
3. keep repository guidance docs in English
4. update tests if the prompt content is reflected in asserted behavior
