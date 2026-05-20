# Quality Cockpit Runbook

Use this runbook when inspecting quality regressions, converting failures into
governed proposals, or checking whether P4/P5 quality signals are healthy.

## Surfaces

Control-plane endpoints:

- `GET /api/control-plane/dashboard/quality/overview`
- `GET /api/control-plane/dashboard/quality/agents/{agent_id}`
- `POST /api/control-plane/dashboard/quality/failures/{failure_id}/proposal`

Payloads use `quality_cockpit.v1`. The cockpit aggregates existing evidence
from evals, execution summaries, metrics, proposals, and RunGraph references.
It does not replace `release_quality.v1`.

## Operator Flow

1. Open the quality overview.
2. Inspect `top_failures`, `cost_vs_quality`, `eval_trends`, and timeout groups.
3. Drill into an agent-specific cockpit when the failure is scoped to one agent.
4. For a confirmed failure, call the failure-to-proposal action.
5. Review the created `improvement_proposal.v1` in the proposal queue.
6. Approve, validate, apply, or rollback only through the proposal lifecycle.

Failure-to-proposal is intentionally non-mutating. It creates proposal evidence
and never applies runtime changes.

## Required Evidence

Each actionable failure should include stable ids and as much redacted evidence
as is available:

- eval suite/run/case refs
- task or squad thread refs
- RunGraph graph/node refs
- model, tool, skill, or squad group
- risk class and failure summary
- proposed validation and rollback plan

If evidence is insufficient, keep the failure as an investigation item instead
of creating a misleading proposal.

## Validation

Focused P4/P5 validation:

```bash
uv run python -m pytest tests/test_squads tests/test_services/test_run_graph.py tests/test_services/test_queue_helpers.py tests/test_services/test_metrics.py tests/test_services/test_quality_cockpit.py tests/test_control_plane_evals_api.py --maxfail=1
pnpm test:web
pnpm build:web
```

Full closeout still follows the repository validation gate in `AGENTS.md`.

## Residual Risks

The cockpit API and contracts are implemented, but the dedicated full dashboard
page and authenticated browser E2E are still future work. Keep P5 cockpit status
as Partial until those surfaces pass.
