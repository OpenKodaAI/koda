# Top-Tier Release Train

This document operationalizes Phase 0 of the Koda top-tier roadmap. It is the
delivery map for KG-15 and the release gate for KG-14.

## Ralph Loop

Every phase runs this loop:

1. **Read:** reload AGENTS guides, Obsidian memory, roadmap notes, source files,
   git status, tests, and prior handoff.
2. **Align:** lock phase scope, owners, write sets, contracts, SLOs, risks,
   gates, and expected outputs.
3. **Launch:** implement slices by role with disjoint ownership.
4. **Prove:** run the required checks. A failing gate keeps the phase open.
5. **Handoff:** update docs, Obsidian, validation results, residual risks, and
   next phase kickoff.

## Issue Map

| Epic | Phase | Lead owner | Dependencies | Closeout evidence |
|---|---|---|---|---|
| KG-15 Delivery operations | 0 | Lead / Integrator | Roadmap docs | Owners, write sets, contracts, QA, security, docs, release gates. |
| KG-14 Scale and resilience | 0 | Backend Runtime + Release/Ops | KG-15 | SLOs, load/fault/resource gates, error feedback, scaling runbook. |
| KG-01 AgentTurn | 1 | Backend Runtime | KG-15, KG-14 | ADR, types, adapters, snapshots, no behavior drift. |
| KG-02 ToolRegistry | 1 | Tools / Policy / Security | KG-01 | Schema-first registry, drift tests, XML/native schema generation. |
| KG-03 Native tool calling | 1 | Backend Runtime | KG-02, KG-14 | Provider fake, native read/write tool, XML fallback preserved. |
| KG-04 HITL approvals | 1 | Tools / Policy / Security + Frontend Product | KG-02, KG-14 | Approve/edit/reject/respond, persisted pending op, UI diff. |
| KG-05 RunGraph/replay | 2 | Backend Runtime + Frontend Product | KG-01, KG-02, KG-04, KG-14 | Tree, replay offline, redaction, viewer. |
| KG-06 Sandbox/doctor | 2 | Tools / Policy / Security | KG-01, KG-05, KG-14 | Effective policy, deny before execute, doctor card/CLI. |
| KG-07 MCP risk | 2 | Tools / Policy / Security | KG-02, KG-04, KG-06, KG-14 | Risk taxonomy, grants, fail-closed unknown risk. |
| KG-09 Subagent task | 3 | Backend Runtime + Frontend Product | KG-01, KG-02, KG-05, KG-14 | Child-run lifecycle, cancel/interrupt, parent/child trace. |
| KG-10 Context governance | 3 | Backend Runtime + Tools / Policy / Security | KG-01, KG-04, KG-05, KG-14 | Context blocks, fencing, memory review. |
| KG-08 Skills/plugins | 4 | Tools / Policy / Security + Docs/DX | KG-02, KG-06, KG-07, KG-14 | Manifest, scanner, provenance, install/uninstall/rollback. |
| KG-11 Evals/release quality | 5 | QA / Evals + Release/Ops | KG-05, KG-14, KG-15 | Eval from run, smoke CI, redacted trajectory export. |
| KG-12 Channel gateway | 6 | Backend Runtime + Security | KG-01, KG-04, KG-05, KG-07, KG-14 | Identity, pairing, allowlist, unknown sender deny. |
| KG-13 UX/DX/OSS polish | 6 | Frontend Product + Docs/DX | KG-06, KG-11, KG-14 | First-use wizard, docs by objective, examples and roadmap. |

## Phase 0 Slices

| Slice | Owner | Write set | Acceptance |
|---|---|---|---|
| P0.1 Baseline and issue map | Lead / Integrator | This release train and Obsidian handoff | KG-01 to KG-15 mapped to phases, owners, dependencies, and blocked-before rules. |
| P0.2 Phase contract package | Lead + Backend + Frontend | Architecture phase contracts | APIs, events, schemas, mocks, error envelope, runtime states, and RunGraph requirements declared. |
| P0.3 SLO and resilience budgets | Backend Runtime + Release/Ops | Scaling and observability docs | Local/team/company profiles and current runtime defaults documented. |
| P0.4 QA, load, and fault gates | QA / Evals | Validation matrix and focused tests | Unit, integration, E2E, load, chaos, security, replay, docs, and smoke gates named. |
| P0.5 Error feedback and ops UI | Frontend Product + Security | Runtime state and error contracts | Stalled/degraded/retry/DLQ/breaker states have required UI actions. |
| P0.6 Handoff and release train | Docs/DX + Release/Ops | Obsidian daily/session note | Closeout records validation, residual risk, rollback, and Phase 1 kickoff. |

## Integration Order

1. Commit Phase 0 docs and contract tests.
2. Start Phase 1 with ADR `AgentTurn` and snapshot tests for the current loop.
3. Add `ToolRegistry` contract without changing provider behavior.
4. Add provider fake and native tool-call loop behind capability checks.
5. Add schema-driven HITL and frontend integration only after schemas are
   versioned.
6. Close Phase 1 only after integration, security, docs, load/fault, and
   Obsidian handoff gates pass.

## Release Gate Checklist

Before a phase closes:

- [ ] Epic and KT IDs are listed in the PR or handoff.
- [ ] Owners and write sets are explicit.
- [ ] API/event/schema changes are versioned.
- [ ] Unit and integration tests for changed logic pass.
- [ ] E2E covers the user-facing path and at least one relevant error path.
- [ ] Load/concurrency gate runs when queue/runtime/subagents/channels are touched.
- [ ] Fault-injection gate runs when providers, MCP, browser, Postgres, runtime,
      or channels are touched.
- [ ] Security deny/fail-closed paths pass.
- [ ] RunGraph/audit/metrics requirements are implemented or explicitly
      declared for the next RunGraph migration.
- [ ] Docs, troubleshooting, migration, rollback, and examples are updated.
- [ ] Obsidian handoff records validation, residual risks, and next phase.

## Phase 1 Kickoff

The first implementation phase starts with KG-01 and KG-02:

- Lead creates ADR shells for AgentTurn and ToolRegistry.
- Backend snapshots the current queue/runtime loop before extraction.
- Security defines tool risk/effect metadata and approval defaults.
- Frontend consumes read-only schemas and versioned fixtures only.
- QA adds drift tests and provider fake scaffolding.
- Docs records compatibility rules for XML fallback and no broad
  `queue_manager.py` rewrite.

## Phase 3 Closeout Gate

KG-09 and KG-10 close only when:

- `task` is present in ToolRegistry, XML prompt, native schemas, dispatcher,
  policy, audit, and RunGraph paths.
- Child-runs persist via `tasks.source_task_id/source_action` and
  `child_runs` without changing Squad Room semantics.
- Parent retries do not duplicate child tasks for the same tool-call
  signature.
- Context governance publishes metadata-only `context_governance.v1` blocks
  and never stores compiled prompt text.
- Dashboard execution detail shows child-run links, cancel/interrupt actions,
  context included/dropped/review-required summaries, and parent/child graph
  nodes from backend payloads.
- Validation covers serialization, registry drift, fan-out limits,
  policy-denied toolsets, timeout/cancel behavior, RunGraph child/context
  nodes, web contracts, and docs handoff.

## Phase 4 Closeout Gate

KG-08 closes only when:

- `koda_skill.v1`, `skill_scan.v1`, and `skill_lock.v1` are documented,
  versioned, and covered by backend and frontend contract tests.
- A safe local package installs without rewriting legacy `custom_skills`; an
  unsafe package is denied before prompt/tool registration.
- Installed package tools enter ToolRegistry with `source=skill_package` and
  still pass through dispatcher, ExecutionPolicy, approval, audit, and
  RunGraph paths.
- Uninstall removes package skills/tools from the effective runtime registry,
  and rollback restores the previous lock when available.
- Scanner covers path escape, symlink escape, secrets, dangerous imports,
  invalid schemas, unknown permissions, high-risk classes, and tool id
  conflicts.
- Dashboard Skills UI shows scan findings, requested permissions, install,
  uninstall, and rollback states from backend payloads.
- Validation covers skills, plugins, ToolRegistry drift, ExecutionPolicy,
  scanner deny paths, web contracts/UI, docs, and Obsidian handoff.

## Phase 5 Closeout Gate

KG-11 closes only when:

- `eval_case.v1`, `eval_run.v1`, `trajectory_export.v1`, and
  `release_quality.v1` are documented, versioned, and covered by backend and
  frontend contract tests.
- Operators can create a draft eval from a real execution using execution
  episodes, RunGraph/replay evidence, and redacted source refs.
- Eval suites run in deterministic `offline_replay` or `provider_fake` mode and
  never call live providers, MCP servers, browser sessions, shell, or network
  dependencies.
- Trajectory exports are JSONL, offline, redacted by default, and denied rather
  than written when safe redaction cannot be proven.
- Release quality fails on release-blocking eval regressions, forbidden tool
  use, policy downgrade, redaction failure, or smoke gate failure.
- Dashboard shows eval cases, run history, failure drilldown, trajectory export
  state, and release health from backend payloads.
- Validation covers eval-from-run, deterministic runner, regression comparison,
  redaction, release smoke script, web contracts/UI, mocked Playwright smoke,
  docs, and Obsidian handoff.
- Authenticated browser E2E remains an explicit residual blocker unless the
  Browser MCP/authenticated dashboard infrastructure is available and tested.

## Phase 6 Closeout Gate

KG-12 and KG-13 close only when:

- `channel_gateway.v1` is documented, versioned, exposed in OpenAPI, and
  covered by backend and frontend contract tests.
- Telegram messages from unknown senders fail closed before enqueue and create
  review queue entries; approved senders use the existing task path.
- Empty `ALLOWED_USER_IDS` denies all legacy senders, while configured legacy
  ids still work and blocked/revoked gateway records override them.
- Pairing code, approve, block, revoke, unknown-sender queue, and error
  envelope flows are covered by unit/API/UI tests.
- `onboarding_readiness.v1` reports provider, runtime, storage, sandbox, MCP,
  memory, channel, first task, first trace, docs, and release quality.
- Dashboard setup and Telegram channel UI consume backend payloads and do not
  duplicate policy/risk classification.
- Docs-by-objective include channel operation, onboarding readiness, migration,
  rollback, validation, and authenticated Browser E2E residual risk.
