# Memory Governance Runbook

Use this runbook before changing durable memory writes, recall policy, memory UI, or utility feedback.

## Preflight

```bash
git status --short
uv run python -m pytest tests/test_memory tests/test_services/test_context_governance.py
```

Confirm the change does not bypass these canonical surfaces:

- `MemoryStore.add()` and `add_batch()` for durable writes
- `build_memory_resolution()` for recall explanations
- `context_governance.v1` for metadata-only context evidence
- `run_graph.v1` for operator-visible execution evidence
- `improvement_proposal.v1` for governed memory changes

## Safety Blocks

If a memory/proposal/candidate write is rejected with `memory_safety.policy_denied`:

1. Read the envelope `user_action`.
2. Remove prompt-injection, exfiltration, secret-path, invisible-character, or credential material.
3. Retry with redacted or metadata-only evidence.
4. Do not paste the blocked raw text into logs, fixtures, docs, or Obsidian.

Expected counters:

- `memory_safety.blocked.prompt_injection`
- `memory_safety.blocked.exfiltration`
- `memory_safety.blocked.secret_path`
- `memory_safety.blocked.credential_leakage`
- `memory_safety.blocked.invisible_unicode`

## Namespace Checks

For leakage reports, verify:

- requested `namespace_kind` and `namespace_key`
- `agent_id` scope
- `sensitivity`
- recall audit dropped reasons
- context governance memory block status

Legacy rows should resolve as agent-scoped memory, not shared workspace memory.

## Child Runs

Default child-run policy fences shared memory:

- no recall unless `include_memory=true`
- no writes unless `allow_memory_writes=true`
- context governance should show dropped or metadata-only memory blocks

Do not grant shared memory to child runs as a workaround for missing task context. Prefer scoped task input or a reviewed handoff/proposal.

## Validation

Run after memory governance changes:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy koda/ --ignore-missing-imports
uv run python -m pytest tests/test_memory tests/test_knowledge tests/test_services/test_context_governance.py tests/test_handlers/test_commands_extended.py
pnpm test:web
```

Vault hygiene after docs/Obsidian changes:

```bash
obsidian vault=Koda unresolved verbose format=tsv
obsidian vault=Koda orphans
```
