# Top-Tier Roadmap Assurance

This assurance report audits the top-tier roadmap against the Koda Gap Backlog,
the Top-Tier Roadmap, the phase contracts, and the Phase 1-6 handoffs.

It is intentionally evidence-based: an epic is only marked implemented when
there is a versioned contract, product code, focused tests, docs/runbook
coverage, and a recorded validation path. Phase 6 closes the previously pending
KG-12 and KG-13 scope with Telegram channel identity and onboarding readiness.

## Assurance Standard

- **Coverage means critical coverage:** every public contract, acceptance
  criterion, deny path, redaction path, edge case, and user-visible flow must
  have meaningful test coverage. Koda does not pursue artificial 100% line or
  branch coverage for low-value implementation details.
- **No product mocks:** production UI must consume backend-shaped contracts.
  Versioned fixtures may exist in tests only.
- **Security is acceptance:** deny, fail-closed, redaction-denied, unknown-risk,
  unsafe-skill, unsafe-toolset, and policy-downgrade paths are first-class pass
  criteria.
- **Adapters over rewrites:** existing queue/runtime behavior stays compatible;
  broad `queue_manager.py` rewrites remain out of scope for assurance work.
- **Residual blockers are explicit:** authenticated browser E2E is still gated
  by local Browser/auth infrastructure and must remain visible in handoffs and
  release-quality payloads.

## Epic Matrix

| Epic | Status | Contract / expected outcome | Implementation evidence | Test evidence | Gap / residual risk | Next action |
|---|---|---|---|---|---|---|
| KG-01 AgentTurn | Implemented | `agent_turn.v1` adapts the existing queue turn without behavior drift. | `koda/agent_turn.py`, `docs/architecture/agent-turn-contract.md`, queue audit adapters. | `tests/test_agent_turn_contract.py`. | Full runtime behavior still depends on the orchestration spine. | Keep snapshots green before any queue extraction. |
| KG-02 ToolRegistry | Implemented | `tool-definition.v1` is the schema-first source for core tools, XML prompt, native schemas, UI/docs metadata, risk, and handlers. | `koda/services/tool_registry.py`, `docs/architecture/tool-registry-native-tools.md`, dispatcher/prompt adapters. | `tests/test_services/test_tool_registry.py`, native runner tests. | Dynamic tools must continue to use the same registry path. | Add drift tests when new tool sources appear. |
| KG-03 Native Tool Calling | Implemented | Provider capability matrix gates native tool calls while XML fallback remains mandatory. | `koda/services/openai_compatible_runner.py`, provider runtime capability adapters, queue native schema path. | `tests/test_services/test_openai_compatible_runner.py`, ToolRegistry tests. | Real provider support varies by capability profile. | Keep provider fake as the release gate for deterministic validation. |
| KG-04 HITL Approvals | Implemented | Schema-driven approve/edit/reject/respond with persisted pending approvals and legacy aliases. | `koda/services/approval_broker.py`, `koda/state/pending_approvals.py`, dashboard approval components. | `tests/test_services/test_approval_broker.py`, `tests/test_utils/test_pending_approvals.py`, approval UI tests. | Browser-authenticated E2E remains external. | Preserve original/edited params, rationale, and RunGraph ids in all new approval flows. |
| KG-05 RunGraph / Replay | Implemented | `run_graph.v1` and replay reconstruct model/tool/policy/approval/runtime evidence with redaction. | `koda/services/run_graph.py`, `koda/services/run_graph_store.py`, migration `036_run_graph_v1`, runtime/detail UI panels. | `tests/test_services/test_run_graph.py`, web runtime contract tests. | Reconstructed traces can be partial when historical data lacks nodes. | Keep missing-data warnings visible instead of silently claiming completeness. |
| KG-06 Sandbox / Doctor | Implemented | `sandbox_policy.v1` denies unsafe mounts, secrets, egress, custom MCP, and invalid isolation before execution; doctor reports actionable status. | `koda/services/sandbox_policy.py`, `koda/services/sandbox_doctor.py`, `scripts/doctor.py`, sandbox doctor panel. | `tests/test_services/test_sandbox_policy.py`, `tests/test_services/test_sandbox_doctor.py`. | Platform-specific kernel/cgroup support can be degraded. | Keep doctor strict checks and degradation messaging current. |
| KG-07 MCP Risk | Implemented | `mcp_risk.v1` normalizes read/write/network/destructive/secret/code/unknown risk and fails closed for unknown/high-risk classes. | `koda/services/mcp_risk.py`, `koda/services/mcp_capability_service.py`, MCP badges/UI. | `tests/test_services/test_mcp_risk.py`, `apps/web/src/lib/contracts/phase2-runtime.test.ts`. | New MCP annotations may introduce aliases. | Extend taxonomy aliases only with fail-closed tests. |
| KG-08 Skills / Plugin SDK | Implemented | `koda_skill.v1`, `skill_scan.v1`, and `skill_lock.v1` support local install/uninstall/rollback with scanner/provenance. | `koda/skills/_package.py`, safe example package, docs/runbooks/security scanner doc, Skills UI package panel. | `tests/test_skills/test_skill_packages.py`, web skill-package contract tests. | No public marketplace yet by design. | Any marketplace work must reuse scanner, lock, rollback, and policy paths. |
| KG-09 Subagent Task | Implemented | `child_run.v1` supports ephemeral Delegate Task child-runs, fan-out limits, idempotency, cancel/interrupt, and parent/child trace. | `koda/services/child_runs.py`, child-run queue adapters, migration `037_child_runs_v1`, execution detail child panels. | `tests/test_services/test_child_runs.py`, `apps/web/src/lib/contracts/phase3-runtime.test.ts`. | Write/network/destructive child toolsets remain approval-first/fail-closed. | Keep Delegate Task distinct from persistent Squad Room. |
| KG-10 Context Governance | Implemented | `context_governance.v1` publishes metadata-only context blocks with fencing, redaction, risk, and include/drop reasons. | `koda/services/context_governance.py`, queue context governance events, context panel. | `tests/test_services/test_context_governance.py`, web Phase 3 contract tests. | Raw compiled prompts must never become governance payloads. | Add leak regressions when new context block sources are introduced. |
| KG-11 Evals / Release Quality | Implemented | `eval_case.v1`, `eval_run.v1`, `trajectory_export.v1`, and `release_quality.v1` provide deterministic evals, redacted JSONL, and release gates. | `koda/services/evals.py`, canonical `/evals/*` APIs, migration `039_evals_release_quality_v1`, `/evaluations` UI, `scripts/eval_smoke.py`. | `tests/test_services/test_evals_release_quality.py`, `tests/test_control_plane_evals_api.py`, `tests/test_release_quality_smoke.py`, web eval contract/component tests. | Authenticated browser E2E remains a blocked residual gate. | Keep offline/provider-fake evals free from live provider, MCP, browser, shell, or network calls. |
| KG-12 Channel Gateway | Implemented | `channel_gateway.v1` covers identity, pairing, allowlist, unknown-sender deny, channel approvals, and Telegram pilot gateway. | `koda/channels/gateway.py`, `koda/auth.py`, migration `040_channel_gateway_onboarding_v1`, gateway APIs, Telegram channel gateway UI, docs/runbook. | `tests/test_channels/test_gateway.py`, `tests/test_control_plane_onboarding_api.py`, `apps/web/src/lib/contracts/channel-gateway.test.ts`, gateway panel test. | Slack/Discord remain contract-ready only; authenticated Browser E2E is still external. | Reuse the gateway contract before enabling additional production channels. |
| KG-13 UX / DX / OSS Polish | Implemented | `onboarding_readiness.v1` reports first-use readiness and dashboard checklist guides provider, runtime, channel, first task, first trace, docs, and release quality. | `koda/services/onboarding_readiness.py`, onboarding readiness APIs, setup checklist card, OpenAPI/docs indexes/runbooks. | `tests/test_services/test_onboarding_readiness.py`, `tests/test_control_plane_onboarding_api.py`, `apps/web/src/lib/contracts/onboarding-readiness.test.ts`, setup checklist test. | Full authenticated Browser E2E remains blocked by local Browser/auth infrastructure when unavailable. | Keep readiness checks backend-owned and add checks when new first-run dependencies appear. |
| KG-14 Scale / Resilience / Error Feedback | Implemented baseline, ongoing gate | SLO profiles, runtime states, error envelope, load/fault/resource gates, backpressure and operations UI requirements. | `docs/operations/scaling-resilience-runbook.md`, metrics, leases, breakers, runtime state contracts. | Queue/runtime/resilience tests, `tests/test_phase0_contract_docs.py`, focused phase suites. | Some load/fault gates remain scenario-specific and opt-in (`bench`, `chaos`). | Require affected phases to run the relevant load/fault gate before closeout. |
| KG-15 Delivery Operations | Implemented baseline, ongoing gate | Owners, write sets, contracts, QA/security/docs/release gates, Ralph Loop handoff format. | `docs/architecture/top-tier-phase-contracts.md`, `docs/operations/top-tier-release-train.md`, Obsidian handoffs. | `tests/test_phase0_contract_docs.py`, this assurance test suite. | Parallel work increases conflict risk in dirty worktrees. | Keep single owner for shared orchestration files and record residual risks. |

## Architecture Review

- The implemented phases generally follow the intended layering: contracts and
  docs first, adapters around existing runtime behavior, backend-shaped Zod
  contracts in the dashboard, additive migrations, and fail-closed security
  paths.
- Shared orchestration remains concentrated in the existing queue/runtime spine.
  This is acceptable for the roadmap assurance phase because the backlog
  explicitly requires adapters before broad extraction.
- The main architectural guardrail for future work is contract drift: new tools,
  providers, channels, skills, context sources, or eval artifacts must update
  both backend contracts and web contract tests in the same change.

## Assurance Gates

Full assurance closeout should run:

```bash
ruff check .
ruff format --check .
.venv/bin/python -m mypy koda/ --ignore-missing-imports
pytest --cov=koda --cov-report=term-missing
pnpm lint:web
pnpm test:web
pnpm build:web
```

Focused phase gates:

```bash
pytest tests/test_agent_turn_contract.py tests/test_services/test_tool_registry.py tests/test_services/test_openai_compatible_runner.py tests/test_services/test_approval_broker.py
pytest tests/test_services/test_run_graph.py tests/test_services/test_sandbox_policy.py tests/test_services/test_sandbox_doctor.py tests/test_services/test_mcp_risk.py
pytest tests/test_services/test_child_runs.py tests/test_services/test_context_governance.py
pytest tests/test_skills/test_skill_packages.py
pytest tests/test_services/test_evals_release_quality.py tests/test_control_plane_evals_api.py tests/test_release_quality_smoke.py
pytest tests/test_channels/test_gateway.py tests/test_services/test_onboarding_readiness.py tests/test_control_plane_onboarding_api.py
pnpm --filter koda-web exec vitest run src/lib/contracts/phase2-runtime.test.ts src/lib/contracts/phase3-runtime.test.ts src/lib/contracts/skill-package.test.ts src/lib/contracts/evals.test.ts src/lib/contracts/channel-gateway.test.ts src/lib/contracts/onboarding-readiness.test.ts
pnpm --filter koda-web exec vitest run src/components/control-plane/editor/channel-gateway-mini-panel.test.tsx src/components/dashboard/setup-checklist-card.test.tsx
python scripts/eval_smoke.py --input tests/fixtures/evals/release_quality.v1.pass.json
```

## Phase 6 Closeout

Phase 6 closes only when the contract package and implementation remain aligned:

- `channel_gateway.v1` with identity, pairing, unknown sender queue, allowlist,
  approval relay, event tracing, and policy-denied behavior. Telegram is the
  pilot channel; Slack and Discord are contract-ready but not production
  dependencies.
- `onboarding_readiness.v1` with provider, runtime, sandbox, MCP, memory,
  channel, first task, and first trace checks.
- Mocked dashboard/API smoke for channel pairing and first-use wizard, plus an
  authenticated Browser E2E gate when local Browser/auth infrastructure is
  available.
- Empty Telegram allowlist is fail-closed, legacy configured senders remain
  compatible, and blocked/revoked identities override legacy allow.
