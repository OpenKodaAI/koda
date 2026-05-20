# Onboarding Readiness Runbook

Use this runbook for first-install UX/DX, clean-room setup validation, OSS
readiness checks, and Phase 6 closeout.

## Contract

`onboarding_readiness.v1` is a backend-generated checklist. The dashboard
renders the payload and may call provided actions, but it must not reclassify
policy, security, release quality, or channel identity state.

Canonical route:

```bash
curl http://127.0.0.1:8090/api/control-plane/onboarding/readiness
```

First task action:

```bash
curl -X POST http://127.0.0.1:8090/api/control-plane/onboarding/first-task \
  -H 'content-type: application/json' \
  -d '{"agent_id":"ATLAS"}'
```

## Required Checks

| Check | Passed when | Typical action |
|---|---|---|
| `provider` | At least one provider is verified. | Open model/provider settings. |
| `runtime` | Control-plane runtime probe is healthy. | Run doctor and inspect runtime. |
| `storage` | Primary state/storage is available. | Configure Postgres/object storage. |
| `sandbox` | Sandbox doctor has no strict failure. | Fix mounts, secrets, egress, or isolation. |
| `mcp` | MCP grants/risk setup has no blocking issue. | Review MCP catalog and grants. |
| `memory` | Memory setup is configured or explicitly optional. | Configure embeddings/memory if needed. |
| `channel` | Telegram has an approved gateway identity or clear warning. | Pair or approve a sender. |
| `first_task` | At least one safe first task exists or was queued. | Run the first-task action. |
| `first_trace` | A trace/execution detail is available. | Open executions after first task completes. |
| `docs` | Objective docs and runbooks are present. | Open docs index and install guide. |
| `release_quality` | Latest deterministic release-quality payload passes or warns explicitly. | Run eval smoke/release gate. |

## Dashboard Behavior

The setup checklist stays visible until the key readiness path is complete:
provider, agent, Telegram connection, channel identity, first task, and first
trace. The card links to the relevant dashboard surfaces and calls
`POST /api/control-plane/onboarding/first-task` for the first runtime smoke.

The readiness payload may include warnings without blocking local use. Failures
must display the backend error envelope and the action link from the check.

## Validation

Focused checks:

```bash
pytest tests/test_services/test_onboarding_readiness.py tests/test_control_plane_onboarding_api.py
pnpm --filter koda-web exec vitest run \
  src/lib/contracts/onboarding-readiness.test.ts \
  src/components/dashboard/setup-checklist-card.test.tsx
```

Release closeout should also run:

```bash
ruff check .
ruff format --check .
.venv/bin/python -m mypy koda/ --ignore-missing-imports
pytest --cov=koda --cov-report=term-missing
pnpm lint:web
pnpm test:web
pnpm build:web
python scripts/eval_smoke.py --input tests/fixtures/evals/release_quality.v1.pass.json
```

Authenticated Browser E2E remains a hard external blocker unless local
Browser/auth infrastructure is available. When unavailable, record the blocker
in Obsidian and release-quality residual risk.

## Troubleshooting

- If readiness is `pending`, inspect each check. Pending is expected before a
  first task and first trace exist.
- If `channel` is warning, open the Telegram gateway and pair or approve a
  sender.
- If `release_quality` is failed, run the deterministic eval smoke before
  closing any release claim.
- If `first_task` creation fails, verify an agent exists, provider config is
  valid, and the runtime queue is healthy.

## Rollback

Readiness runs are advisory and additive. To roll back, ignore or drop
`onboarding_readiness_runs`. Runtime tasks created through the first-task action
remain normal tasks and should be managed through existing execution tooling.
