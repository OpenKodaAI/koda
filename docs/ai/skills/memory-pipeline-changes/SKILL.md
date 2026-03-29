---
name: memory-pipeline-changes
description: Modify the repository memory pipeline safely. Use when changing recall, extraction, storage, retention, digest scheduling, memory configuration, or other behavior under koda/memory.
---

# Memory Pipeline Changes

## Workflow

1. Read [`../../repo-map.yaml`](../../repo-map.yaml) first to confirm the memory module area and matching tests.
2. Read [`../../llm-compatibility.md`](../../llm-compatibility.md) if you need to keep `AGENTS.md`, `CLAUDE.md`, and provider-neutral docs aligned.
3. Read [`../../runtime-flows.md`](../../runtime-flows.md) for the memory lifecycle.
4. Read [`../../../koda/memory/AGENTS.md`](../../../koda/memory/AGENTS.md) or [`../../../koda/memory/CLAUDE.md`](../../../koda/memory/CLAUDE.md).
5. Read [`../../configuration-and-prompts.md`](../../configuration-and-prompts.md) if the task changes memory settings.
6. Inspect the relevant modules under [`../../../koda/memory`](../../../koda/memory).
7. Inspect the matching tests under [`../../../tests/test_memory`](../../../tests/test_memory).

## Preserve

- Best-effort behavior for recall and extraction
- Memory timeouts and graceful degradation
- Separation between recall, extraction, and persistence
- Namespaced storage behavior derived from `AGENT_ID`
- Cache invalidation after successful writes

## Required Checks

- Decide whether the change belongs in configuration, recall, extraction, storage, or scheduling.
- Update the focused tests in [`../../../tests/test_memory`](../../../tests/test_memory).
- If a setting changes, update [`.env.example`](../../../.env.example) and the docs.
- Confirm the main runtime still works even if memory is disabled, slow, or unavailable.

## Repository-Specific Reminders

- [`../../../koda/memory/manager.py`](../../../koda/memory/manager.py) owns the pre-query and post-query orchestration contract.
- [`../../../koda/services/queue_manager.py`](../../../koda/services/queue_manager.py) expects memory failures to degrade gracefully.
- Schedulers for digests and maintenance are part of the subsystem and need coverage when behavior changes.
