# Evals And Release Quality Runbook

Use this runbook when creating evals from real executions, running deterministic
eval suites, exporting trajectories, or closing a release-quality gate.

Phase 5 covers KG-11. It depends on RunGraph/replay, scale/resilience gates,
and delivery operations. It does not require live provider calls during eval
execution.

## Operator Flow

1. Open an execution with enough RunGraph/replay and execution episode evidence.
2. Create a draft eval case from the run.
3. Review and edit the expected output, required tools, policy decisions,
   approval expectations, and release-blocking assertions.
4. Move the case from `draft` to `active`.
5. Add the case to a release suite.
6. Run the suite in `offline_replay` or `provider_fake` mode.
7. Inspect failure groups, top failing tools/providers/policies, and
   trajectory divergences.
8. Generate a redacted trajectory export for release handoff or debugging.
9. Close the release gate only when smoke, eval, export redaction, security
   deny, docs, and residual blocker records are complete.

Control-plane endpoints:

- `POST /api/control-plane/agents/{agent_id}/evals/cases/from-run`
- `GET /api/control-plane/agents/{agent_id}/evals/cases`
- `PATCH /api/control-plane/agents/{agent_id}/evals/cases/{case_id}`
- `POST /api/control-plane/agents/{agent_id}/evals/runs`
- `GET /api/control-plane/agents/{agent_id}/evals/runs/{run_id}`
- `POST /api/control-plane/agents/{agent_id}/evals/trajectory-exports`
- `GET /api/control-plane/agents/{agent_id}/evals/release-quality/latest`
- `GET /api/control-plane/dashboard/quality/overview`
- `GET /api/control-plane/dashboard/quality/agents/{agent_id}`
- `POST /api/control-plane/dashboard/quality/failures/{failure_id}/proposal`

Legacy `evaluation-cases` and `knowledge-evals/runs` endpoints remain
compatibility surfaces, but new release gates should use `/evals/*`.

## Release Gate

A Phase 5 release-quality gate passes only when:

- the release suite uses deterministic `offline_replay` or `provider_fake`
  mode
- no eval case calls live providers, MCP servers, browser sessions, shell, or
  network dependencies
- every release-blocking assertion passes
- no forbidden tool or policy downgrade appears in observed trajectory
- RunGraph completeness gate passes, including scenario-specific squad nodes,
  valid causal edges, and synthesis evidence
- squad golden quality proves the squad beats the single-agent baseline with
  evidence-backed quality claims and zero provider calls
- trajectory export redaction passes
- security deny/fail-closed paths pass
- smoke eval script exits zero
- docs and handoff identify validation, residual risks, and rollback

The gate is failed when a release-blocking assertion fails. It is blocked, not
passed, when authenticated browser E2E is unavailable. A blocked E2E gate must
name the exact unavailable infrastructure and can close only with mocked
Playwright/API smoke coverage plus documented residual risk.

## Error Envelope

Eval operations use the shared operational envelope:

```json
{
  "code": "eval.redaction_failed",
  "category": "validation",
  "message": "Trajectory export could not be redacted safely.",
  "retryable": false,
  "user_action": "Remove or redact the sensitive source and generate the export again.",
  "trace_id": "optional-trace-id",
  "run_graph_node_id": "optional-node-id",
  "detail_ref": "docs/architecture/evals-release-quality.md"
}
```

Common Phase 5 codes:

| Code | Meaning | Operator action |
|---|---|---|
| `eval.case_not_found` | Requested case is missing or not visible. | Refresh the case list and confirm agent scope. |
| `eval.source_run_unavailable` | Source execution lacks required episode, graph, or replay data. | Open execution detail and inspect RunGraph/replay availability. |
| `eval.redaction_failed` | Export or case creation would expose sensitive data. | Remove the unsafe source or improve redaction before retry. |
| `eval.live_dependency_blocked` | Eval attempted a live dependency call. | Run offline replay/provider fake only. |
| `eval.assertion_failed` | A release-blocking assertion failed. | Inspect failure drilldown and decide fix, quarantine, or expected-output update. |
| `eval.suite_failed` | Suite finished below threshold. | Inspect grouped failures and rerun after fixes. |
| `trajectory.export_denied` | Export is unsafe or lacks authorized source data. | Resolve redaction/source issue before exporting. |
| `release_quality.gate_failed` | Release quality status is failed. | Fix failing smoke/eval/security/docs gate. |
| `release_quality.e2e_blocked` | Full authenticated E2E is unavailable. | Record blocker and keep mocked smoke coverage current. |

Eval failures may also create `improvement_proposal.v1` rows. Review them in
the proposal queue; creation alone does not apply any change.

Quality cockpit failures use the same proposal queue. The cockpit action
creates `improvement_proposal.v1` evidence and never validates, applies, or
rolls back by itself.

## Redaction Rules

Trajectory exports, eval cases, run summaries, and release-quality artifacts
must not include:

- raw provider prompts or raw compiled context
- secrets, tokens, credentials, private keys, cookies, or `.env` values
- raw browser/session data
- sensitive mount paths or filesystem listings
- unredacted customer data
- raw logs that contain secret-shaped strings

Store redacted previews, hashes, summary text, artifact refs, and RunGraph ids
instead. If safe redaction is not possible, return `eval.redaction_failed` or
`trajectory.export_denied` and do not write the export.

## Persistence And Rollback

Phase 5 uses additive persistence for suites, run batches, trajectory exports,
and release-quality summaries. Existing evaluation cases and knowledge eval
runs remain readable during migration.

Rollback path:

1. Stop creating new `/evals/*` cases or runs.
2. Export Phase 5 tables if the release-quality history is needed.
3. Ignore or drop only Phase 5 additive tables.
4. Continue using existing execution episodes, RunGraph/replay, and legacy
   knowledge evaluation helpers.

Runtime task execution, ToolRegistry, approvals, sandbox policy, skills, and
child-runs must continue if eval persistence is unavailable.

## Validation Commands

Docs/DX closeout should at least run:

```bash
obsidian vault=Koda unresolved verbose format=tsv
obsidian vault=Koda orphans
```

Full Phase 5 closeout should also run the implementation checks defined by the
QA/Evals and Release/Ops slices:

```bash
ruff check .
ruff format --check .
.venv/bin/python -m mypy koda/ --ignore-missing-imports
pytest tests/test_knowledge* tests/test_control_plane* tests/test_services/test_run_graph.py
pnpm lint:web
pnpm test:web
pnpm build:web
python scripts/eval_smoke.py --input tests/fixtures/evals/release_quality.v1.pass.json
python scripts/squad_smoke.py --input tests/fixtures/evals/squad_smoke.v1.json
```

The exact focused pytest paths may change with the implementation, but the gate
must include eval contracts, eval-from-run, deterministic runner, trajectory
redaction, release smoke, RunGraph completeness, squad golden quality,
frontend contracts, and dashboard smoke coverage.

## Troubleshooting

- If create-from-run fails, inspect execution detail, execution episode,
  RunGraph, replay bundle, and redaction errors.
- If a suite fails unexpectedly, compare observed tool/policy/approval sequence
  with the case expectations before changing expected output.
- If export is denied, keep the denial as acceptance evidence for redaction and
  remove unsafe raw data from the source.
- If release health is `unknown`, verify the latest eval run, release smoke
  artifact, and trajectory export refs.
- If E2E is blocked, record the Browser MCP/authenticated dashboard blocker in
  the handoff and keep mocked API/component coverage green.
