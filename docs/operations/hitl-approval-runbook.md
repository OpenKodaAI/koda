# HITL Approval Runbook

Phase 1 expands human-in-the-loop approvals from approve/deny into a
schema-driven decision flow.

## Decisions

Dashboard and Telegram-compatible decisions:

- `approve` / `approved`
- `scope` / `approve_scope` / `approved_scope`
- `edit` / `edited`
- `reject` / `deny` / `denied`
- `respond` / `response` / `responded`

The dashboard POST body is:

```json
{
  "decision": "edit",
  "edited_params": {"path": "README.md", "content": "updated"},
  "response_text": null,
  "rationale": "Operator narrowed the write."
}
```

## Pending Payload

A pending approval should include:

- `tool_id`
- `original_params`
- `args_schema`
- `risk_class`
- `approval_scope`
- `preview_text`
- `trace_id`
- `run_graph_node_id`

`approval_broker` validates `edited_params` against the provided object-schema
subset before resolving the approval.

## Persistence

Pending approvals and approval grants are stored in Postgres only, in the
`pending_approvals` and `approval_grants` tables that migration
`050_approval_tables` creates. A failed write is logged and nothing falls back
to a file.

A pending approval lasts as long as the worker process that asked for it: its
command, or the agent turn waiting on it, cannot be restored. On start, each
worker deletes the pending approvals of its agent that its previous process
left, with one `approval.pending_expired` audit event (reason `restart`) each,
and a button pressed on one of them answers that the request expired and must
be asked again. Approval grants survive a restart. Each worker loads only its
own agent's grants.

## Operator Guidance

- Use **Approve** only when the original parameters are acceptable.
- Use **Edit** when the tool is acceptable but arguments need narrowing.
- Use **Respond** when the human should provide a synthetic tool result instead
  of executing the tool.
- Use **Reject** when the operation should stop and following write steps should
  not proceed.

## Validation

Focused tests:

```bash
.venv/bin/python -m pytest tests/test_services/test_approval_broker.py
.venv/bin/python -m pytest tests/test_utils/test_pending_approvals.py
.venv/bin/python -m pytest tests/test_utils/test_approval.py::TestAgentCmdApproval
pnpm --filter koda-web exec vitest run src/components/sessions/chat/approval-prompt.test.tsx
```

## Rollback

Rollback is compatible: stop sending `edit`/`respond` from the dashboard, and
continue accepting legacy
`approved`, `denied`, and `approved_scope` decisions.
