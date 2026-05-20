# AgentTurn Contract

Phase 1 introduces the internal `agent_turn.v1` contract as the stable bridge
between the current queue loop and future RunGraph/replay work.

## Scope

`agent_turn.v1` is an internal runtime snapshot contract. It does not replace
`QueryContext`, `RunResult`, leases, retries, DLQ, metrics, or provider
fallback. The current queue loop stays the behavior source; AgentTurn captures
its inputs and outputs in a versioned shape.

## Types

Python types live in `koda/agent_turn.py`:

- `AgentTurnInput`
- `CompiledContextBlock`
- `AgentTurnEvent`
- `AgentTurnOutput`
- `AgentTurnError`

Adapters:

- `from_query_context(ctx)` snapshots a `QueryContext`-shaped object.
- `from_run_result(result)` snapshots a `RunResult`-shaped object.

The contract includes runtime states from the Phase 0 state model:
`queued`, `running`, `retrying`, `stalled`, `degraded`, `failed`,
`cancelled`, and `completed`.

## Error Envelope

`AgentTurnError` follows the Phase 0 error contract:

```json
{
  "code": "runtime.provider_timeout",
  "category": "timeout",
  "message": "Provider timed out.",
  "retryable": true,
  "user_action": "Retry, cancel, or reduce scope.",
  "trace_id": null,
  "run_graph_node_id": null,
  "detail_ref": null
}
```

## Audit

`queue_manager` emits `agent_turn.started` and `agent_turn.completed` audit
events from the adapters. Prompt and result text are not stored verbatim in the
audit payload; they are represented by SHA-256 and character counts.

## Validation

Focused tests:

```bash
.venv/bin/python -m pytest tests/test_agent_turn_contract.py
.venv/bin/python -m pytest tests/test_services/test_queue_helpers.py::TestPhase1NativeToolHelpers
```

## Rollback

Rollback is additive: remove `koda/agent_turn.py`, the helper tests, and the
audit emit calls. Runtime behavior remains XML/tool-loop compatible without
AgentTurn snapshots.
