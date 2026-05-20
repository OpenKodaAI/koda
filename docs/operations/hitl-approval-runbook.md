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

Pending approvals are Postgres-primary when the primary state backend is
enabled. The JSON file at `{STATE_ROOT_DIR}/pending_approvals.json` remains the
fallback and rollback path.

The Postgres table is additive and created with `CREATE TABLE IF NOT EXISTS`:

```sql
CREATE TABLE IF NOT EXISTS pending_approvals (
  op_id TEXT PRIMARY KEY,
  op_type TEXT NOT NULL,
  user_id INTEGER,
  agent_id TEXT,
  session_id TEXT,
  chat_id INTEGER,
  description TEXT,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  payload_json TEXT NOT NULL
);
```

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

Rollback is compatible: keep the JSON pending-approval fallback, stop sending
`edit`/`respond` from the dashboard, and continue accepting legacy
`approved`, `denied`, and `approved_scope` decisions.
