# Services Guide

The `services` package holds orchestration logic and most cross-cutting runtime behavior. The matching [`AGENTS.md`](AGENTS.md) file mirrors the same local rules for `AGENTS.md`-aware tooling.

## High-Value Modules

- [`queue_manager.py`](queue_manager.py): request queuing, context preparation, provider execution, tool loops, retries, and response delivery
- [`claude_runner.py`](claude_runner.py): Claude CLI process execution, streaming, retry classification, and JSON parsing
- [`tool_dispatcher.py`](tool_dispatcher.py): `<agent_cmd>` parsing, tool execution, read/write classification, and resume payload formatting
- [`tool_prompt.py`](tool_prompt.py): system-prompt exposure of runtime agent tools
- [`templates.py`](templates.py): built-in templates, runtime skill loading from `koda/skills`, and skills-awareness prompt construction
- [`browser_manager.py`](browser_manager.py), [`atlassian_client.py`](atlassian_client.py), [`db_manager.py`](db_manager.py), [`http_client.py`](http_client.py): focused integration wrappers
- [`scheduler.py`](scheduler.py) and [`cron_store.py`](cron_store.py): cron orchestration and persistence

## Editing Rules

- Preserve the split between prompt exposure and runtime execution. When a tool changes, update both [`tool_prompt.py`](tool_prompt.py) and [`tool_dispatcher.py`](tool_dispatcher.py).
- Keep [`queue_manager.py`](queue_manager.py) as the orchestration spine. Avoid moving Telegram parsing, database schema definitions, or integration-specific details into it.
- Keep [`claude_runner.py`](claude_runner.py) thin and CLI-focused. Business rules belong in the caller.
- Keep service wrappers narrow and testable. Prefer explicit helper modules over expanding monolithic handlers.

## Do Not Break

- System prompt assembly order in `queue_manager`: base prompt, user instructions, voice prompt, recalled memory, agent tools prompt, runtime skills awareness
- Supervised-mode protection for write operations in [`tool_dispatcher.py`](tool_dispatcher.py)
- Read-only guarantees for PostgreSQL queries in [`db_manager.py`](db_manager.py)
- The coupling between created artifacts and response delivery in `queue_manager`

## When Adding A New Service

1. Define configuration and feature flags in [`../config.py`](../config.py).
2. Add a focused service module or extend the narrowest existing one.
3. Wire the feature into handlers or queue orchestration only after the service contract is clear.
4. Update prompt exposure if the feature is available through `<agent_cmd>`.
5. Add tests in [`../../tests/test_services`](../../tests/test_services).
