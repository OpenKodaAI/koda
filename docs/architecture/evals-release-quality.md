# Evals, Trajectory Export, And Release Quality

Phase 5 introduces the KG-11 quality loop: operators can create deterministic
evals from real executions, export redacted trajectories, and block release
quality claims unless replay and smoke gates pass.

The contracts in this document are additive. Existing knowledge evaluation
helpers, execution episodes, RunGraph/replay payloads, and legacy
`evaluation-cases` / `knowledge-evals/runs` endpoints remain compatibility
sources.

## Scope

Phase 5 covers:

- `eval_case.v1`: an operator-reviewable case created from a real run or a
  curated fixture.
- `eval_run.v1`: a deterministic offline execution of one case or a suite.
- `trajectory_export.v1`: redacted JSONL evidence for replay, debugging, and
  release handoff.
- `release_quality.v1`: a release gate summary that combines smoke status,
  eval status, redaction status, RunGraph completeness, and regression groups.

Phase 5 does not add channel gateway behavior, onboarding flows, marketplace
publishing, or real-provider evals. The default eval path is offline replay or
provider fake; it must not call a live provider, MCP server, browser, shell, or
external network dependency.

## eval_case.v1

`eval_case.v1` is the durable source of truth for an expected behavior.

Required fields:

- `schema_version`: `eval_case.v1`
- `case_id`, `agent_id`, `title`, `status`
- `source`: `manual`, `run`, `seed`, or `import`
- `source_refs`: `task_id?`, `run_graph_id?`, `replay_ref?`, `episode_id?`,
  `artifact_refs`, and `created_from_export_id?`
- `input`: redacted user goal, prompt preview, prompt hash, context summaries,
  model/provider hints, and runtime state snapshot
- `expected`: final output summary or structured output, required tool ids,
  forbidden tool ids, expected policy decisions, expected approvals, required
  RunGraph node types, and allowed error envelopes
- `assertions`: named checks with type, threshold, severity, and user-facing
  failure text
- `redactions`: applied redaction rules and omitted fields
- `metadata`: tags, owner, suite ids, priority, created/updated timestamps

Allowed `status` values are `draft`, `active`, `quarantined`, and `archived`.
Only `active` cases may block release. `draft` cases created from a run require
operator review before they enter a release suite.

The case must never store raw provider prompts, raw compiled context, secrets,
environment values, mount paths with sensitive data, raw credentials, or
unredacted logs. Store hashes, summaries, and artifact refs instead.

## eval_run.v1

`eval_run.v1` records deterministic evaluation output.

Required fields:

- `schema_version`: `eval_run.v1`
- `run_id`, `agent_id`, `suite_id?`, `case_ids`
- `mode`: `offline_replay` or `provider_fake`
- `status`: `queued`, `running`, `passed`, `failed`, `error`, or `cancelled`
- `started_at`, `completed_at?`, `duration_ms?`
- `case_results`: result per case with assertion results, observed output
  summary, observed tool/policy/approval sequence, RunGraph node coverage,
  divergences, and error envelope when applicable
- `summary`: pass/fail counts, score, threshold, release-blocking failures,
  flaky/quarantined counts, and residual warnings
- `metrics`: tool, model, policy, retry, breaker, DLQ, cost, duration, and
  redaction counters
- `refs`: source case refs, replay bundle refs, trajectory export refs, and
  audit/RunGraph ids

An eval run passes only when all release-blocking assertions pass and no
forbidden tool, policy downgrade, redaction failure, or unexpected live
dependency call is observed.

## trajectory_export.v1

`trajectory_export.v1` is a JSONL export intended for debugging, handoff, and
release evidence. It is generated offline from stored execution episodes,
RunGraph/replay payloads, audit events, approvals, and artifact metadata.

Header fields:

- `schema_version`: `trajectory_export.v1`
- `export_id`, `agent_id`, `task_id?`, `case_id?`, `eval_run_id?`
- `replay_mode`: `offline`
- `format`: `jsonl`
- `redaction_version`, `created_at`, `created_by`
- `source_refs`, `package_hash?`, `file_hash?`, `line_count`

Allowed JSONL entry types:

- `case_header`
- `runtime_event`
- `model_call`
- `tool_request`
- `tool_result`
- `policy_gate`
- `approval_request`
- `approval_decision`
- `context_block_summary`
- `child_run`
- `artifact_ref`
- `cost`
- `final_output`
- `user_facing_error`
- `divergence`

Each entry includes `ordinal`, `timestamp?`, `task_id?`, `run_graph_node_id?`,
`trace_id?`, `summary`, `payload`, `redactions`, and `refs`.

The export must contain enough sequence information to compare trajectories
without re-running live work. It must not contain raw prompts, raw model output
when marked sensitive, raw tool results with secrets, environment values,
secret-shaped strings, unredacted filesystem mounts, browser cookies, access
tokens, private keys, or customer data.

## release_quality.v1

`release_quality.v1` is the operator-facing release gate payload.

Required fields:

- `schema_version`: `release_quality.v1`
- `release_quality_id`, `generated_at`, `version?`, `commit_sha?`
- `status`: `passed`, `failed`, `blocked`, or `unknown`
- `gates`: smoke, eval suite, trajectory export redaction, RunGraph
  completeness, security deny, docs, and residual E2E blocker status
- `latest_eval_run`: run id, suite id, score, threshold, failures, warnings
- `failure_groups`: top failing tools, providers, policies, assertions, and
  runtime states
- `artifacts`: trajectory export refs, logs refs, dashboard refs, and CI refs
- `error?`: shared operational error envelope

The release gate is `blocked` when authenticated browser E2E or Browser MCP
infrastructure is unavailable. A blocked E2E gate may be accepted only as a
documented residual blocker when the mocked Playwright/API smoke, eval suite,
redaction tests, and release smoke script pass.

`run_graph_completeness` fails when a required `run_graph.v1` node family is
missing. Squad flows must show the request, reply obligation, child run or task
result, coordinator synthesis, and timeout/dependency evidence when applicable.
The gate also checks dangling edge endpoints, disconnected required nodes, and
a causal path from completed evidence or timeout into synthesis. Historical
partial traces may be accepted only with explicit missing-data warnings.

`squad_golden_quality` compares `single_agent` and `squad` variants from the
same `eval_case.v1`. A passing squad golden case must beat the single-agent
baseline by the configured delta, resolve every quality claim to RunGraph or
delivery evidence, keep provider calls at zero, and report cost/time deltas
when those values are available.

Failed eval cases may create `improvement_proposal.v1` records. Those records
are review-only at creation time and do not activate any memory, skill, prompt,
routing, tool policy, eval, or docs change.

## Control-Plane API

Canonical Phase 5 APIs require authenticated control-plane operator access for
the target agent. Mutating calls require the same operator capability used for
agent configuration or release operations; export calls also require permission
to read the source execution evidence.

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| `POST` | `/api/control-plane/agents/{agent_id}/evals/cases/from-run` | `task_id`, optional `title`, `suite_id`, `expected`, `assertions`, `tags` | `eval_case.v1` with `status=draft` and source refs | `201`, `400`, `403`, `404`, `409`, `422` |
| `GET` | `/api/control-plane/agents/{agent_id}/evals/cases` | query `status?`, `suite_id?`, `limit?`, `cursor?` | list page of `eval_case.v1` summaries | `200`, `403` |
| `PATCH` | `/api/control-plane/agents/{agent_id}/evals/cases/{case_id}` | partial title, expected output, assertions, tags, suite ids, status | updated `eval_case.v1` | `200`, `400`, `403`, `404`, `409`, `422` |
| `POST` | `/api/control-plane/agents/{agent_id}/evals/runs` | `case_id?`, `suite_id?`, `mode`, `threshold?`, `release_blocking?` | `eval_run.v1` summary and artifact refs | `202`, `400`, `403`, `404`, `409`, `422` |
| `GET` | `/api/control-plane/agents/{agent_id}/evals/runs/{run_id}` | none | full `eval_run.v1` with per-case results | `200`, `403`, `404` |
| `POST` | `/api/control-plane/agents/{agent_id}/evals/trajectory-exports` | one of `task_id`, `case_id`, or `eval_run_id`; optional `include_artifact_refs` | `trajectory_export.v1` header and artifact/download ref | `201`, `400`, `403`, `404`, `409`, `422` |
| `GET` | `/api/control-plane/agents/{agent_id}/evals/release-quality/latest` | query `suite_id?`, `version?`, `commit_sha?` | latest `release_quality.v1` payload | `200`, `403`, `404` |

Compatibility aliases may continue to expose existing evaluation cases and
knowledge eval runs. New UI and release gates should prefer the canonical
`/evals/*` APIs.

All failures use the shared operational envelope. Phase 5 error codes include:

- `eval.case_not_found`
- `eval.source_run_unavailable`
- `eval.redaction_failed`
- `eval.live_dependency_blocked`
- `eval.assertion_failed`
- `eval.suite_failed`
- `trajectory.export_denied`
- `release_quality.gate_failed`
- `release_quality.e2e_blocked`

## Persistence And Rollback

Phase 5 persistence is additive. Implementations may reuse existing
`evaluation_cases` and `evaluation_runs` tables, but any new tables must use
`CREATE TABLE IF NOT EXISTS` and avoid destructive migrations.

Expected additive tables:

- `eval_suites`: suite metadata, release-blocking flag, thresholds, status.
- `eval_suite_cases`: suite membership and per-case severity.
- `eval_run_batches`: run summary, mode, status, metrics, and artifact refs.
- `trajectory_exports`: export metadata, redaction version, hashes, refs.
- `release_quality_runs`: latest release gate payload and CI/dashboard refs.

Rollback is to ignore the new canonical tables and continue using existing
knowledge evaluation helpers and execution episodes. If data must be removed,
export rows first, then drop only Phase 5 tables. Runtime execution must not
depend on eval tables being writable.

## RunGraph, Audit, And Metrics

Phase 5 emits or reconstructs these event concepts:

| Event | Severity | Required correlation | Retention |
|---|---|---|---|
| `eval_case.created` | info | agent, case, source task/export | audit table and case row |
| `eval_case.updated` | info | agent, case, operator | audit table and case row |
| `eval_run.started` | info | agent, run, suite/cases | audit table and run row |
| `eval_run.case_passed` | info | agent, run, case | run result payload |
| `eval_run.case_failed` | warning | agent, run, case, assertion | run result payload and metrics |
| `eval_run.completed` | info or warning | agent, run, suite, status | audit table and run row |
| `trajectory_export.created` | info | agent, export, source refs | export row and artifact ref |
| `trajectory_export.denied` | warning | agent, requested source, redaction rule | audit table and metrics |
| `release_quality.generated` | info | agent, release quality id, suite/version | release-quality row |
| `release_quality.failed` | warning | agent, gate, failure group | release-quality row and metrics |
| `improvement_proposal.created_from_eval_failure` | warning | agent, eval run, case, proposal | proposal row, audit table and metrics |

RunGraph links are references, not new runtime dependencies. Eval case creation
links to source graph nodes; eval runs may produce `runtime_event` or
`artifact` nodes for export evidence when a task context exists.

Metrics must include eval run count, case pass/fail count, failure category,
top failing tool/provider/policy, trajectory export count, redaction deny count,
and release gate status.

## Frontend Contract

Dashboard UI consumes backend-shaped payloads only:

- Execution detail exposes a "Create eval case from run" action.
- The Evals surface lists cases, suites, run history, failure groups, and
  release health.
- Trajectory export actions show generation status, redaction failures, and
  artifact refs.
- Risk, policy, and failure categories are rendered from backend payloads; the
  UI must not reclassify policy risk.

Versioned frontend fixtures may exist only in contract or component tests.
Production UI must not depend on unversioned mocks.

## Validation

Required validation for Phase 5 closeout:

- Contract tests for `eval_case.v1`, `eval_run.v1`, `trajectory_export.v1`, and
  `release_quality.v1`.
- Unit tests for eval-from-run construction, deterministic runner behavior,
  assertion scoring, JSONL export, redaction, and legacy endpoint
  compatibility.
- Integration tests for creating a case from a fake run, running a suite,
  persisting results, exporting a redacted trajectory, and failing the release
  smoke script on a known regression.
- Frontend tests for Zod contracts, create-from-run flow, dashboard failure
  drilldown, release health cards, and trajectory export states.
- Playwright smoke with mocked dashboard APIs for create eval from run, run
  suite, and release status.
- Full authenticated browser E2E remains a residual external blocker until the
  Browser MCP/authenticated dashboard infrastructure is available.
