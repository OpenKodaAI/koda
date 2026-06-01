# Memory Governance

Koda memory governance is additive over the existing memory contracts:
`MemoryStore`, `MemoryResolution`, `memory_recall_audit`,
`memory_quality_counters`, `context_governance.v1`, `run_graph.v1`, and
`improvement_proposal.v1`.

## Contracts

- `koda/memory/safety.py` scans durable memory, proposal, and knowledge-candidate text before persistence.
- `koda/memory/namespaces.py` resolves `user`, `agent`, `squad`, `workspace`, `project`, and `org` namespaces.
- `napkin_log` adds `namespace_kind`, `namespace_key`, `namespace_scope_json`, and `sensitivity` without backfilling old rows beyond safe defaults.
- `MemoryResolution` serializes selected, dropped, stale/status, conflict, namespace, sensitivity, source, and trust metadata.
- `context_governance.v1` and `run_graph.v1` receive metadata-only memory blocks. Raw memory text is not serialized into governance or RunGraph payloads.

## Safety

The scanner blocks prompt injection, exfiltration instructions, secret path/read attempts, credential leakage, and invisible/control unicode. `MemoryStore.add()` and `add_batch()` scan before dedupe or persistence; a blocked item fails the whole batch.

The scanner is reused by extraction parsing, improvement proposal creation, and knowledge candidate upserts. Blocked proposal API requests return an operational error envelope with `code`, `category`, `message`, `retryable`, and `user_action`.

## Recall Policy

Recall defaults remain backward-compatible: legacy rows resolve as `namespace_kind="agent"` and `namespace_key=agent_id`. Explicit namespace filters prevent cross-agent/squad/user leakage, and sensitive memories are excluded unless the caller explicitly permits them.

Stale, superseded, invalidated, rejected, conflict-loser, and sensitive-not-allowed memories are dropped with explicit reasons. They are not silently treated as authoritative.

## Child Runs

Child runs do not recall parent/shared memory unless `child_context_policy.include_memory` is set. They do not write shared memory unless `child_context_policy.allow_memory_writes` is set.

## Utility Feedback

Human utility feedback continues to increment `memory_quality_counters.utility.*`. When a feedback event is tied to a task with recall audit evidence, selected memories receive bounded quality-score adjustments:

- `useful`: small positive adjustment
- `noise`: small negative adjustment
- `misleading`: larger negative adjustment plus review-signal counters

Structural memory changes still go through governed proposals; feedback does not auto-edit sensitive memory.

## Evidence

P2 validation on 2026-05-19:

```bash
uv run python -m pytest \
  tests/test_memory \
  tests/test_knowledge \
  tests/test_services/test_context_governance.py \
  tests/test_handlers/test_commands_extended.py
# 238 passed
```

Web/runtime validation:

```bash
pnpm lint:web
pnpm test:web
pnpm build:web
# lint passed; test:web 151 files / 671 tests passed; build passed
```

Residual risks before `Robust`: restart/fault tests for namespace migrations and memory-engine protobuf parity, authenticated browser E2E for memory panels, and broader production recall telemetry.
