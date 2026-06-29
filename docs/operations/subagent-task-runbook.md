# Subagent Task Runbook

Use this runbook when a parent execution delegates work through the `task`
tool.

## Inspect

1. Open the parent execution detail.
2. Check `child_runs[]` for `child_run_id`, `child_task_id`, `status`, deadline,
   warnings, and error envelope.
3. Open each child execution from the dashboard or runtime API.
4. Review RunGraph `child_run` and `context_block` nodes.
5. Confirm the child used only approved context metadata and the expected
   toolset.

Runtime APIs:

- `GET /api/runtime/tasks/{parent_task_id}`
- `GET /api/runtime/tasks/{child_task_id}`
- `POST /api/runtime/tasks/{child_task_id}/cancel`
- `POST /api/runtime/tasks/{child_task_id}/interrupt`

## Common Errors

| Code | Meaning | Operator action |
|---|---|---|
| `subagent.fanout_limit_exceeded` | Parent exceeded child-run cap. | Reduce `tasks[]` or wait for a new parent run. |
| `subagent.policy_denied` | Requested toolset is not allowed. | Use `read_only`, `analysis`, or `research`; escalate only through future approval path. |
| `subagent.timeout` | Child exceeded declared timeout. | Open child execution, inspect trace, retry with smaller scope if safe. |
| `subagent.runtime_unavailable` | Runtime application context is missing. | Check runtime readiness and dashboard/app startup. |
| `subagent.child_failed` | Child task reached terminal failure. | Inspect child execution error envelope and RunGraph. |

## Safety Checks

- Nested child-runs are disabled.
- Child-runs are silent to user chat; results return to the parent tool call.
- Child-runs use task leases and runtime finalization.
- Parent retries reuse idempotency keys to avoid duplicate child tasks.
- Sensitive context is metadata-only, dropped, or marked review-required.

## Rollback

1. Remove `task` from the agent's allowed tool policy or disable inter-agent
   tools.
2. Leave `tasks.source_task_id/source_action` intact.
3. Ignore or export/drop `child_runs` if required.
4. Keep Squad Room tools unchanged.
