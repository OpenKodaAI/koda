---
name: runtime-flow-changes
description: Change message-to-provider execution flows in this repository. Use when modifying queueing, prompt assembly, streaming, tool loops, response delivery, task tracking, or other request-path orchestration behavior.
---

# Runtime Flow Changes

## Workflow

1. Read [`../../repo-map.yaml`](../../repo-map.yaml) first to confirm the owning flow, files, and tests.
2. Read [`../../llm-compatibility.md`](../../llm-compatibility.md) if you need to keep `AGENTS.md`, `CLAUDE.md`, and provider-neutral docs aligned.
3. Read [`../../runtime-flows.md`](../../runtime-flows.md).
4. Read [`../../../koda/services/AGENTS.md`](../../../koda/services/AGENTS.md) or [`../../../koda/services/CLAUDE.md`](../../../koda/services/CLAUDE.md).
5. Inspect the exact orchestration path in [`../../../koda/services/queue_manager.py`](../../../koda/services/queue_manager.py).
6. Inspect the Claude CLI wrapper in [`../../../koda/services/claude_runner.py`](../../../koda/services/claude_runner.py).
7. If runtime agent tools are involved, inspect both [`../../../koda/services/tool_prompt.py`](../../../koda/services/tool_prompt.py) and [`../../../koda/services/tool_dispatcher.py`](../../../koda/services/tool_dispatcher.py).

## Preserve

- System prompt assembly order
- Supervised-mode write protection
- Retry behavior only for transient failures
- Artifact delivery and response formatting
- Session, task, and cost bookkeeping

## Required Checks

- Trace the request from handler entry to final Telegram response.
- Decide whether the change affects prompt assembly, queueing, streaming, tool looping, persistence, or response formatting.
- Update the narrowest handler or service tests that demonstrate the behavior change.
- Run the full validation suite after the change because runtime-flow edits have wide blast radius.

## Repository-Specific Reminders

- `queue_manager` is allowed to orchestrate; it should not become a dumping ground for provider-specific logic.
- `claude_runner` should stay CLI-focused and return execution data, not product decisions.
- If you add a new runtime agent tool, keep prompt exposure and dispatcher behavior aligned.
