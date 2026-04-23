---
name: repo-orientation
description: Orient quickly in the Koda repository. Use when a task requires understanding entrypoints, package ownership, runtime flow, prompt layering, test placement, or safe edit boundaries before making code changes.
---

# Repo Orientation

## Workflow

1. Read [`../../repo-map.yaml`](../../repo-map.yaml) first when the task needs ownership, flow, or test targeting.
2. Read [`../../../README.md`](../../../README.md).
3. Read [`../../llm-compatibility.md`](../../llm-compatibility.md).
4. Read the provider entrypoint you are using: [`../../../AGENTS.md`](../../../AGENTS.md) or [`../../../CLAUDE.md`](../../../CLAUDE.md).
5. Read [`../../architecture-overview.md`](../../architecture-overview.md).
6. Read [`../../runtime-flows.md`](../../runtime-flows.md).
7. If the task touches configuration or prompt behavior, read [`../../configuration-and-prompts.md`](../../configuration-and-prompts.md).
8. Open the closest subtree entrypoint. `AGENTS.md` and `CLAUDE.md` mirrors carry the same local rules:
   - [`../../../koda/AGENTS.md`](../../../koda/AGENTS.md) or [`../../../koda/CLAUDE.md`](../../../koda/CLAUDE.md)
   - [`../../../koda/services/AGENTS.md`](../../../koda/services/AGENTS.md) or [`../../../koda/services/CLAUDE.md`](../../../koda/services/CLAUDE.md)
   - [`../../../koda/memory/AGENTS.md`](../../../koda/memory/AGENTS.md) or [`../../../koda/memory/CLAUDE.md`](../../../koda/memory/CLAUDE.md)
   - [`../../../tests/AGENTS.md`](../../../tests/AGENTS.md) or [`../../../tests/CLAUDE.md`](../../../tests/CLAUDE.md)

## Produce Before Editing

- Identify the runtime entrypoint and the owning package.
- Identify the closest module area, runtime flow, and test target in [`../../repo-map.yaml`](../../repo-map.yaml).
- Identify the modules that orchestrate the full flow, not just the first handler you found.
- Identify whether the change belongs to compiled control-plane agent documents, a runtime skill, or repository guidance.
- Identify the tests that prove the change safely.

## Repository-Specific Reminders

- [`../../../koda/services/queue_manager.py`](../../../koda/services/queue_manager.py) is the orchestration spine.
- [`../../../koda/config.py`](../../../koda/config.py) is the source of truth for feature flags, prompt assembly, and namespaced paths.
- Runtime `/skill` templates live in [`../../../koda/skills`](../../../koda/skills).
- Repo-local guidance skills live in [`../`](../).
- Agent-specific prompt behavior is sourced from control-plane documents and the compiled runtime prompt contract.

## Finish Line

- State the call path you traced.
- State the files and tests you need to touch.
- State any prompt or configuration layer affected by the task.
