# Improvement Proposal Runbook

Use this runbook when reviewing self-improvement proposals from eval failures,
runs, operator corrections, timeouts, tool failures, or manual changes.
Memory quality and knowledge-candidate evidence may appear in `evidence_refs`.

## Operator Flow

1. Open Evaluations and switch to Proposals.
2. Select a proposal and inspect summary, source, risk, diff preview,
   validation plan, rollback plan, and RunGraph references.
3. Reject proposals that are unsafe, duplicate, unclear, or missing evidence.
4. Approve proposals that should proceed to validation.
5. Run validation. The proposal must record a passing `validation_result`.
6. Apply only after post-approval validation passes and rollback effects are
   present.
7. Roll back if the applied effect regresses behavior.

No proposal applies persistent runtime changes at creation time. P1 applies only
safe ledger effects unless a proposal type has a registered, tested executor.

## Common Outcomes

| Status | Meaning | Operator action |
|---|---|---|
| `draft` | Captured but not ready for review. | Add evidence or move to review. |
| `pending_review` | Ready for operator decision. | Approve or reject. |
| `approved` | Human approval recorded. | Validate, then apply if validation passed. |
| `rejected` | Closed without mutation. | No action unless new evidence appears. |
| `validating` | Validation is in progress or awaiting result. | Wait for result. |
| `failed` | Validation or lifecycle guard failed. | Inspect failure and create a new proposal if needed. |
| `applied` | Ledger effect is active; runtime mutation requires a typed executor. | Monitor evals and runtime quality. |
| `rolled_back` | Applied ledger effect was reverted. | Keep evidence for postmortem. |

## Eval Failure Path

When an offline eval case fails, Koda creates a `pending_review`
`improvement_proposal.v1` with:

- source kind `eval`
- eval run, eval case, source task, RunGraph and RunGraph node evidence refs
- failure summary in the redacted diff preview
- offline replay validation plan
- ledger-only rollback effect

Tool or policy regressions create `tool_policy` proposals. Other failures
default to `eval_case` proposals.

## Safety Rules

- Do not approve proposals without source evidence.
- Do not apply proposals without passing validation.
- Do not apply proposals without a structured rollback plan and effect ledger.
- Treat unknown proposal types, unknown sources, and malformed diffs as failed
  or rejected.
- Treat `memory_quality` and `knowledge_candidate` as evidence kinds, not
  proposal source kinds.
- Do not paste secrets, raw prompts, raw compiled context, credentials, or raw
  logs into proposal fields.

## Validation

Focused checks for this surface:

```bash
uv run python -m pytest tests/test_control_plane_improvement_proposals.py
pnpm test:web -- apps/web/src/lib/contracts/improvement-proposals.test.ts
```

Full closeout still requires the repository validation commands from the
release train.
