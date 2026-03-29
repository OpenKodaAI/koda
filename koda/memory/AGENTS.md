# Memory Subsystem Guide

The `memory` package is a best-effort enrichment layer. It should improve responses without becoming a hard dependency for normal agent execution. The matching [`CLAUDE.md`](CLAUDE.md) file mirrors the same local rules for Claude Code.

## Responsibilities By Module

- [`manager.py`](manager.py): public orchestration for pre-query recall and post-query extraction
- [`recall.py`](recall.py): memory lookup, ranking, caching, and proactive context assembly
- [`extractor.py`](extractor.py): extract candidate memories from a completed interaction
- [`store.py`](store.py): persistence and vector-backed storage operations
- [`digest.py`](digest.py) and [`digest_scheduler.py`](digest_scheduler.py): digest generation and scheduling
- [`maintenance.py`](maintenance.py) and [`maintenance_scheduler.py`](maintenance_scheduler.py): retention and cleanup workflows
- [`config.py`](config.py): all memory tuning knobs
- [`types.py`](types.py): memory schema objects

## Editing Rules

- Keep pre-query recall non-fatal. If memory fails or times out, the main agent flow must still complete.
- Keep post-query extraction non-fatal and best-effort.
- Keep thresholds, recall limits, and feature switches centralized in [`config.py`](config.py).
- Preserve the separation between extraction logic, recall logic, and persistence logic.

## Do Not Break

- Memory enablement gates and timeout behavior
- Namespaced storage behavior derived from `AGENT_ID`
- Cache invalidation after successful writes
- Scheduler behavior for digests and maintenance jobs

## Testing Expectations

- Add or update tests in [`../../tests/test_memory`](../../tests/test_memory) for any change in ranking, extraction, storage, scheduling, or configuration behavior.
- Prefer deterministic fixtures and mocks over live model, filesystem, or network dependencies.
