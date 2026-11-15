# Changelog

All notable changes to Koda are recorded here: the `@openkodaai/koda` npm package, the
container images and the release bundle they install. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/). Version numbers match
`pyproject.toml` and the release tag. A release that was not published everywhere says
so in its section.

An entry ends with the plan task or defect it comes from, when there is one (for
example `M1-E1-T3` or `D-004`; see `docs/engineering/MASTER_PLAN.md` and
`docs/engineering/TECHNICAL_DEBT.md`). New entries go under [Unreleased] in the same
change. When `pyproject.toml` is bumped, the release moves those entries under its own
version heading.

The record starts at 1.0.18. Earlier releases are described on the
[GitHub Releases page](https://github.com/OpenKodaAI/koda/releases).

## [Unreleased]

Before you update, read **Security** and **Changed**. Ports are now published on
loopback by default, the bundled nginx template must be replaced, and the control
plane refuses to start when its master key does not match the stored data. This
release adds schema migrations `047_scheduler_events_and_dispatch_columns` and
`048_control_plane_master_key_fingerprint`; see `docs/operations/upgrade.md`.

### Security

- The control-plane API and the dashboard are published on loopback by default. Every
  compose file binds the API to `127.0.0.1:${CONTROL_PLANE_PORT:-8090}` and the
  dashboard to `${WEB_PUBLISH_ADDRESS:-127.0.0.1}:${WEB_PORT:-3000}`. Before, the base
  and release compose files published both on every interface, and the production
  overlay only added loopback mappings. Set `WEB_PUBLISH_ADDRESS` only for a
  TLS-terminating proxy on another host. A remote proxy reaches only the dashboard,
  never the API. (M1-E1-T1)
- Unedited `.env.example` placeholders (`replace-with-…`) no longer authenticate.
  `CONTROL_PLANE_API_TOKEN`, `RUNTIME_LOCAL_UI_TOKEN` and `WEB_OPERATOR_SESSION_SECRET`
  with a placeholder value count as unset. For the two tokens, the control plane logs
  why at startup (`control_plane_api_token_placeholder_ignored`,
  `runtime_local_ui_token_placeholder_ignored`). The dashboard checks its session
  secret before a login or owner registration reaches the control plane, and logs the
  reason (`[web-operator-session]`) on the first attempt, so a misconfiguration cannot
  use up the setup code or lose the one-time recovery codes.
  `scripts/generate_env_secrets.py` writes random values to `.env` with mode 0600.
  (D-007)
- `POSTGRES_PASSWORD` and the `S3_*` keys left at their `.env.example` placeholders are
  reported, not yet refused. The supervisor logs `storage_secret_placeholder_in_use` at
  every start. `scripts/doctor.py` fails its `storage_secrets_not_placeholders` check
  and prints the rotation command. `GET
  /api/control-plane/system-settings/placeholder-secrets` returns the key names, and
  the dashboard shows a banner. The rotation steps are in `docs/install/local.md`.
  (M1-E8-T3)
- Login, recovery, bootstrap-exchange and auth-failure rate limits apply per real
  client. The control plane keys each bucket on the TCP peer and reads
  `X-Forwarded-For` only from `CONTROL_PLANE_TRUSTED_PROXIES`: IPs, CIDRs, hostnames
  or `gateway`. The default is `127.0.0.1,::1`, and the compose files set `web`. The
  dashboard server replaces `X-Forwarded-For` on every request and upgrade with the
  peer, or with the first untrusted hop when the peer is a trusted proxy. Loopback is
  always trusted, `WEB_TRUSTED_PROXIES` adds IPs, CIDRs or `gateway`, and the compose
  files set `gateway`. IPv6 clients share a bucket per /64. A reverse proxy in front of
  the dashboard must append or replace `X-Forwarded-For` (nginx
  `$proxy_add_x_forwarded_for`, HAProxy `option forwardfor`). Per-account lockout is
  unchanged. (M1-E1-T2, D-004)
- Before login, `GET /api/control-plane/onboarding/status` returns only `has_owner`
  and `bootstrap_required`. `GET /api/control-plane/auth/status` returns the bootstrap
  file path and the loopback flag only until an owner exists, and never returns
  `recovery_available`. Agents, owner contact details, the Telegram allowlist and
  provider state need an operator session. `onboarding/readiness` needs a session in
  the dashboard too. A pre-login probe of an unavailable upstream gets a plain 503.
  `koda doctor` and `scripts/doctor.py` read the bootstrap file path from
  `auth/status`. (M1-E1-T3)
- The control-plane API treats a request as public only when the router resolves it
  to a listed public route and method. Before, it matched path prefixes, so a route
  added under or beside a public path skipped authentication.
- A request with a malformed `Host` header or target no longer stops the dashboard
  server. It answers 400 instead. (D-004)
- Outbound fetches refuse more non-public destinations: `0.0.0.0/8`, `::`,
  `100.64.0.0/10`, multicast and reserved ranges, and IPv4-mapped or NAT64 forms of
  any blocked address. Connections are pinned to the addresses that were checked, which
  closes the DNS-rebinding window. The check uses the host aiohttp actually connects
  to, so IDNA-mapped names can no longer reach loopback. Web search re-checks every
  redirect, and yt-dlp only receives a watch URL rebuilt from a validated YouTube,
  Vimeo or Dailymotion ID. The default vendor base URLs of OpenAI-compatible providers
  are pinned and follow no redirects. An unfollowed 3xx is reported as an HTTP error
  instead of an empty answer. Any other `*_API_BASE_URL`, from the control plane or
  `.env`, is an operator override and may reach private hosts. Behaviour change:
  fake-IP DNS (`198.18.0.0/15`) and CGNAT/Tailscale (`100.64.0.0/10`) destinations are
  now non-public. (M1-E3-T1, D-003)
- The MCP HTTP transport, artifact ingestion's yt-dlp step, generated-image
  downloads, provider API-key checks, Ollama and the control plane's runtime calls go
  through the same guard. They ignore `*_proxy` variables and refuse redirects to
  another origin. MCP HTTP servers on CGNAT/Tailscale or other private networks need
  the new `MCP_ALLOWED_PRIVATE_NETWORKS` (empty by default). A tailnet needs both
  `100.64.0.0/10` and `fd7a:115c:a1e0::/48`. The grant never covers loopback,
  link-local, unspecified or multicast addresses, `100.100.100.200` or
  `fd00:ec2::254`. The release compose file passes it from the install's `.env`.
  (M1-E3-T8, D-223)
- The control-plane master key fails closed. Only the control-plane supervisor creates
  a key, and only on a fresh install. Any other process without the key file gets an
  error instead of silently generating a new key. The key's fingerprint (an HMAC under
  the key, never the key itself) is recorded in Postgres. On the first start after the
  upgrade, a present key is recorded only if it decrypts the newest stored secrets, or
  if nothing is stored yet. Startup is refused, with guidance, when the key is missing
  while ciphertext or a fingerprint exists, when it differs from the recorded one
  (unless `CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE` matches, for a rotation), or when it
  is not a Fernet key. To accept a replacement key after losing the original, write its
  fingerprint prefix to `.master.key.accept-undecryptable` next to the key file. A key
  file readable by group or others is tightened to owner-only. If the mount refuses
  that, `control_plane_master_key_permissions_too_open` is logged. See
  `docs/operations/backup-restore.md` and `docs/operations/hardening.md`. (AG-05)
- The agent worker and the runtime kernel make themselves non-dumpable and disable
  core dumps before anything else, and refuse to start if either step fails.
  Processes they start can no longer read their environment or memory through
  `/proc`. Attaching py-spy or gdb needs root with `CAP_SYS_PTRACE`. One window
  remains open. During the tens of milliseconds of Python startup before the worker's
  entrypoint runs, a process running as the same user can still read its environment.
  It closes only once provider CLIs, governed shell and git (AG-14), the commands the
  runtime kernel starts (AG-15), and MCP servers and media tools (AG-16) run under
  Landlock. (AG-04)
- Provider CLIs are pinned to Claude Code 2.1.325, Codex 0.169.0 and Gemini CLI 0.68.0,
  and both images install them the same way. A provider whose installed CLI is not the
  pinned version is unavailable (`unavailable:unverified_cli_version`). `CODEX_BIN` and
  `GEMINI_BIN` must each be the path of one executable. A command line such as
  `npx -y @google/gemini-cli` counts as not installed, and Gemini no longer falls back
  to npx. (AG-02)
- A `CONTROL_PLANE_BOOTSTRAP_CODE` seed is never logged. `bootstrap_file_written`
  names the code's source and logs only a generated code. A seed with fewer than 12
  significant characters logs `bootstrap_code_seed_weak`. A seed the `/setup` field
  cannot take (1 to 12 characters from its alphabet) logs
  `bootstrap_code_seed_not_typeable`. (M1-E1-T17)
- The `plugin_install` tool takes only `path`. It no longer reads `review_accepted`,
  `approved`, `review_note` or `note`, and its error no longer tells the agent to
  retry with them, so the model cannot accept the review of a `review_required`
  package. Only an operator can, in the agent's Skills tab: the control-plane install
  route now also takes the `package_hash` shown in the scan, refuses the install with
  `skill.review_hash_mismatch` (409) when the files changed since, and records the
  reviewer, hash, scanner version and verdict in the lock's `operator_review`.
  (M1-E4-T3, D-031)
- Skill package code loads only while its files still hash to the approved
  `package_hash`. A package changed after approval is not loaded: the runtime logs
  `skill_package_modified_not_loaded`, `plugin_reload` says the package changed, and
  the skills registry and the Skills tab report `integrity.status: modified`. While
  the runtime registers a package's handlers they load from their `.py` sources only,
  never from a bytecode cache, and the package hash no longer covers the cache files
  Python writes into `__pycache__` (`<module>.<tag>.pyc`); every other file there is
  still hashed. A package approved by an earlier release, whose hash covered those
  cache files too, keeps loading while every file still matches. A rollback whose
  files no longer match its revision (an update that overwrote the same directory) is
  refused with `skill.package_modified` (409) and asks for a reinstall.
  (M1-E4-T11, D-037)
- Tool results reach the model inside an `<untrusted_data>` frame, with protocol tags in
  tool output escaped, so a fetched page or file cannot close the frame or issue a tool
  call. Third-party MCP tool names, descriptions and parameters are sanitised and
  capped. (M1-E4-T2, D-025)
- Tools that are not in the catalog and are not skill-package tools count as write tools,
  so dry-run, supervised mode and the confidence gate apply to them. (M1-E4-T5, D-132)
- Plugin handler paths must stay inside the plugin, on register and on reload, and
  loading a handler no longer changes `sys.path`. (M1-E4-T12, D-138)
- A wrong password at sign-in answers 401 instead of 400. Every rejected sign-in and
  password recovery takes at least 300 ms from when its body is read, with the same
  work whether the account exists, is locked or the secret is wrong. (M1-E1-T5,
  M1-E1-T13, D-135, D-136)


### Added

- `CONTROL_PLANE_PUBLIC_PORT` carries a non-default host port to host-facing URLs such
  as the OAuth relay. The container always listens on 8090, and `CONTROL_PLANE_PORT`
  only picks the host port. (M1-E1-T1)
- The routines table offers a Validate action for a routine that is waiting for
  validation, so a stuck routine can be recovered from the dashboard. (D-016)
- A refresh of a scheduled job's policy snapshot is recorded as a
  `job.policy_snapshot_refreshed` event. A half-open circuit breaker is audited as
  `system.circuit_half_open`. (D-001, D-020)
- `GET /ready` on the control plane answers 503 while Postgres or the runtime kernel is
  down; `/health` stays a liveness probe. The compose healthcheck uses `/ready`, every
  sidecar has a healthcheck, and the app waits for them to be healthy. (M7-E1-T1)
- A daily retention report counts the rows past their retention in `audit_events` and
  `query_history`, deletes nothing, and records a `retention.report` audit event once per
  deployment per day. Schema migration `049_audit_events_type_lookup` adds its index.
  (M2-E5-T1)


### Changed

- The bundled nginx template (`proxy/nginx.conf`) follows the auth model. Browser
  pages and API calls, the runtime relay WebSocket and the runtime event streams go to
  the dashboard. Only API-token (`Authorization: Bearer`) requests and
  `/openapi/control-plane.json` go to the control-plane API. It passes the browser's
  `Host` with its port, so sign-in works behind a non-default port. A request without
  a `Host`, such as an HTTP/1.0 health check, gets the `server_name`. It keeps idle
  relay and event-stream connections open for an hour. Every request keeps nginx's
  1 MiB body limit except API-token photo uploads, which accept 13 MiB (a 12 MiB photo
  plus its multipart framing). Replace any installed copy, keeping your `server_name`
  and TLS settings, then run `nginx -t` and reload nginx. (M1-E1-T16)
- `POST /api/runtime/schedules` queues a validation run for the new job and returns
  `validation_run_id` and a `message`. An idempotent replay returns the same shape.
  Before, the job stayed waiting for validation and nothing was queued. (D-016)
- `POST /api/runtime/tasks/{id}/cancel` and `/interrupt` answer 409, with an error and
  the `not_running` payload, when nothing is left to stop. The dashboard shows that as
  an error instead of "Cancel execution completed". (D-009)
- The dashboard's runtime stream relays send a single `stream_error` event carrying
  only `{status}` when the runtime rejects the request (400, 404 or 422). Other
  failures get a non-200 JSON error instead of an empty 200 stream. The dashboard
  retries a rejected stream after 60 seconds. (D-022)
- The routine editor labels Read-only mode and Allowed paths "Not enforced yet" and
  no longer lets new routines set them; routine runs have never enforced either
  setting. Values an existing routine already stores are shown and kept. (M1-E8-T1)
- Setup codes are accepted without dashes, with spaces or in lower case, as recovery
  codes are. A wrong code still gets the generic error. (M1-E1-T17)
- Subscription login, logout and verification are offered only for Claude, Codex and
  Gemini. Other providers answer "does not support subscription login". Starting a
  subscription login without the CLI answers 400 "CLI is not installed". Disconnecting
  a provider resets it to its fresh-install mode.
- The OpenAPI document no longer marks four session-protected control-plane routes
  as public: the two OAuth callbacks, the OAuth relay and onboarding readiness.
  (M0-E3-T1)
- The knowledge backend sets its schema once per connection as a startup `search_path`.
  A connection pooler must forward `search_path`: for PgBouncer, list it in
  `track_extra_parameters` (1.20 or later). See `docs/config/reference.md`. (M2-E2-T4)
- The supervisor backs off from 5 s to 60 s while the runtime kernel is unreachable and
  logs one traceback per state change. It refuses to start when the kernel socket path
  is longer than the platform allows. (M7-E1-T2)
- The eight non-Telegram channels show "Not available" and their forms are disabled;
  stored credentials are kept. The video and music model slots read "Not available yet";
  stored defaults are kept. Improvement proposals say "Accept (recorded)": accepting
  records the decision and does not change the agent. (M6-E1-T2, M6-E3-T5, M6-E1-T9)
- Snapshots are stored per explicit scope (`task:<id>` or `user:<id>`), so a task and a
  user with the same id no longer share snapshots. Snapshots saved before this release
  under the old layout are not listed. `snapshot_restore` is described as loading a
  snapshot for inspection. The feature stays off by default (`SNAPSHOT_ENABLED`). (M6-E3-T6)


### Removed

- Onboarding readiness no longer reports the fixed sandbox, MCP, memory and docs
  checks, which never changed. Every remaining check comes from live state. (M1-E1-T3)
- The runtime image no longer contains npm, npx or corepack. (AG-02)
- The repository no longer tracks two third-party JavaScript bundles at its root, or
  another project's `CHANGELOG.md`. Neither was in the npm package or the images.
  (M1-E7-T6, D-128, D-084)
- Agents no longer have the `webhook_register`, `webhook_unregister`, `webhook_list`
  and `event_wait` tools, and the `WEBHOOK_ENABLED`, `WEBHOOK_MAX_REGISTRATIONS` and
  `WEBHOOK_TIMEOUT_MAX` settings are gone. No route ever delivered an event to a
  registered webhook, so `event_wait` always timed out. An agent whose tool policy
  still lists one of these tools fails validation with "unknown core tools" until the
  id is removed from its tool policy JSON. (M4-E1-T10, D-067)
- Twenty configuration keys that nothing read are gone. Setting one never had an effect,
  and it is now ignored without a warning: `INTER_AGENT_MESSAGE_TIMEOUT`,
  `WORKFLOW_MAX_PARALLEL`, `RUNTIME_PTY_ENABLED`, `RUNTIME_BUNDLE_RETENTION_DAYS`,
  `RUNTIME_LOCAL_UI_BIND`, `RUNTIME_ATTACH_IDLE_TIMEOUT_SECONDS`,
  `RUNTIME_BROWSER_DISPLAY_BASE`, `RUNTIME_PTY_CHUNK_BYTES`, `RUNTIME_PTY_BACKPRESSURE_KB`,
  `RUNTIME_LOOP_MAX_CYCLES`, `RUNTIME_LOOP_MAX_RETRIES_PER_PHASE`,
  `RUNTIME_LOOP_NO_CHANGE_LIMIT`, `RUNTIME_CHECKPOINT_MAX_UNTRACKED_BYTES`,
  `SNAPSHOT_MAX_SIZE_MB`, `PLUGIN_DIRS`, `PLUGIN_MAX_EXECUTION_TIMEOUT`,
  `MEMORY_LEXICAL_CANDIDATES`, and `KNOWLEDGE_V2_NEO4J_URI`, `_USER` and `_PASSWORD`.
  The control-plane system settings no longer offer four of them in their `runtime`
  section (`runtime_pty_enabled`, `runtime_local_ui_bind`,
  `runtime_attach_idle_timeout_seconds`, `runtime_browser_display_base`); a value saved
  there before now shows under `additional_env_vars`. `PLUGIN_SANDBOX_ENABLED` stays
  until M1-E4-T4. (M4-E1-T2, TD-003, D-194)
- `DASHBOARD_ENABLED` is gone with the in-process stats aggregator it switched on, which
  recorded tool runs that nothing read; the dashboard reads its data from Postgres.
  Three Prometheus metrics that were never exported are gone. `scripts/ops_benchmark.py`
  recorded `koda_ops_benchmark_runs_total` and `koda_ops_benchmark_duration_seconds`
  only inside its own process, which serves no `/metrics` and pushes nowhere; it no
  longer records them, and its output and exit codes are unchanged. Nothing set
  `koda_runtime_worktree_disk_bytes`. The `KodaOpsBenchmarkFailed` alert in
  `docs/operations/alerts.yml` and the "Ops benchmark" panel of the bundled Grafana
  dashboard, which could never show data, are gone with them. `/health` reports the
  same fields and breakers. (M4-E1-T3, TD-057, TD-058)
- `POST /api/control-plane/onboarding/bootstrap` is gone: it has answered `410
  onboarding_bootstrap_removed` since the setup wizard stopped using it, and now answers
  `404`. Create the owner with `POST /api/control-plane/auth/register-owner`. The control
  plane (`:8090`) no longer serves the HTML page at `/setup` that pointed to the
  dashboard, or the `/` redirect to it; the setup screen is the dashboard's `/setup`.
  `scripts/doctor.py` drops `legacy_setup_url` from its payload and `koda doctor` its
  "Bridge" line. (M4-E1-T8, TD-071)
- `CONTROL_PLANE_AUTO_IMPORT` is gone with the import it switched on, which read agents
  from a root `.env` and a sibling `koda-dashboard` checkout and was off by default.
  (M4-E1-T8, TD-070)
- Custom MCP servers no longer carry `validation_signature`: the HMAC was stored and
  returned but never checked. New and updated servers store no signature. The custom
  server list and the MCP catalog no longer return it, neither as a field nor inside
  `metadata`, where servers saved before this change still hold a copy until they are
  next updated. (M4-E1-T8, TD-038)
- The `artifact_evidence_nodes` write path is gone: no schema ever created that table, so
  every write failed. (M4-E1-T14, D-260)


### Fixed

- Automatic and web-created scheduled jobs run. Every reminder, interval and cron run
  used to be blocked as "policy snapshot is missing". Migration 047 adds the scheduler
  events table and the dispatch and validation columns that a real Postgres database
  lacked. (D-001, D-016)
- Recovery codes typed in lower case, without dashes or with spaces reset the password
  from `/forgot-password`. Before, no code typed in the form could match. Non-ASCII
  look-alikes are still rejected. (D-018)
- Open circuit breakers recover through a half-open probe after their reset timeout.
  Before, the Claude and Codex runners, web search and fetch, ElevenLabs and the
  scheduler dispatcher stayed disabled until restart after a transient outage.
  (D-020)
- `/cancel` stops a running light task: its provider process is terminated and no
  answer is delivered. A finished task is reported as not running. (D-009)
- `/cancel` and the runtime cancel API no longer let a task with a runtime
  environment start a fallback provider run or a retry when its provider exits while
  it is being stopped. A fallback result is no longer dropped when its progress
  indicator is cancelled before it starts. (M3-E2-T6, D-222)
- Runtime event streams resume after event id 1000. `after_seq` takes any
  non-negative 64-bit id. An invalid `after_seq`, `task_id` or `env_id` answers 400
  before the stream opens, instead of a 500 or an empty stream. (M3-E8-T1, D-022)
- `koda uninstall` keeps the data volumes and `.env` unless `--purge` is given, and
  refuses to act on a directory that is not a Koda install. (D-008)
- Disconnecting a provider removes only the pinned CLI's credential files, not the
  whole CLI configuration folder, which on a native install is the operator's own CLI
  setup. A provider with no CLI logout to run (an HTTP provider, ElevenLabs, or Gemini
  without its CLI) still has its stored credentials removed. (D-230)
- A non-default `CONTROL_PLANE_PORT` no longer breaks the stack. (M1-E1-T1)
- `scripts/doctor.py` reads `.env` keys written with a leading `export`, as Docker
  Compose does. (M1-E8-T3)
- A setup code with a non-ASCII character gets the generic error instead of a 500 from
  owner registration. (M1-E1-T17)
- Knowledge: with `KNOWLEDGE_V2_STORAGE_MODE=off`, the agent no longer queries the
  never-created `artifact_evidence_nodes` table, so asset references come back in
  that mode. (M4-E1-T6)
- Buffered squad replies to Telegram are no longer dropped when one send fails: replies
  are grouped by parse mode in order, a transient network error is retried once, and a
  failed send is logged. (M7-E1-T4)
- `scripts/install.sh` stops with a clear message on Node older than 20, installs Node
  from NodeSource when it is missing, and picks the Docker apt repository from
  `/etc/os-release` (Debian, Ubuntu and derivatives). (M7-E2-T4)


## [1.0.18] - 2026-05-20

Publishing 1.0.18 did not finish. The container images are on GHCR under the `1.0.18`
tag, but the npm publish failed: npm's newest version is 1.0.17, so
`npx @openkodaai/koda@1.0.18` finds no such version. The GitHub release for v1.0.18,
which carries the release bundle, is still a draft.

This tag also added two third-party JavaScript bundles and another project's
`CHANGELOG.md` to the repository root by mistake. Neither was part of the npm package
or the images. Both are removed under [Unreleased].

### Added

- Multi-agent squads: agents in one workspace collaborate in tracked threads, with
  tasks, a coordinator and delegation. The dashboard's Sessions page gains rooms, with
  agent mentions, a room photo and room settings. Telegram gains `/squad_bind`,
  `/squad_unbind`, `/squad_status`, `/squad_thread_new` and `/squad_thread_close`.
  Five squad agent templates ship as seeds. Squads are off by default: they need
  `SQUADS_ENABLED=true`, `INTER_AGENT_ENABLED=true` and
  `INTER_AGENT_BUS_BACKEND=postgres`. See `docs/squads/`.
- OpenRouter as an OpenAI-compatible provider, and Supertonic local text-to-speech.
- Workspace directory import in the control plane.
- An Evaluations page in the dashboard, and operator profile photos.
- Schema migrations 028 to 046.

### Changed

- The npm CLI explains how to start Docker when the Docker daemon is not running.
- Dashboard JavaScript, Python, Rust and Docker base image dependencies are updated.

[Unreleased]: https://github.com/OpenKodaAI/koda/compare/v1.0.18...HEAD
[1.0.18]: https://github.com/OpenKodaAI/koda/compare/v1.0.17...v1.0.18
