---
name: integration-and-safety-changes
description: Add or modify repository integrations while preserving runtime guardrails. Use when changing external providers, agent tools, approval rules, blocked-command patterns, read-only database behavior, feature flags, or related safety checks.
---

# Integration And Safety Changes

## Workflow

1. Read [`../../repo-map.yaml`](../../repo-map.yaml) first to confirm the owning integration area, guardrails, and tests.
2. Read [`../../llm-compatibility.md`](../../llm-compatibility.md) if you need to keep `AGENTS.md`, `CLAUDE.md`, and provider-neutral docs aligned.
3. Read [`../../configuration-and-prompts.md`](../../configuration-and-prompts.md).
4. Read [`../../../koda/services/AGENTS.md`](../../../koda/services/AGENTS.md) or [`../../../koda/services/CLAUDE.md`](../../../koda/services/CLAUDE.md).
5. Inspect the relevant service module under [`../../../koda/services`](../../../koda/services).
6. If the integration is exposed through an agent tool, inspect both [`../../../koda/services/tool_prompt.py`](../../../koda/services/tool_prompt.py) and [`../../../koda/services/tool_dispatcher.py`](../../../koda/services/tool_dispatcher.py).
7. Inspect the matching service and handler tests under [`../../../tests/test_services`](../../../tests/test_services) and [`../../../tests/test_handlers`](../../../tests/test_handlers).

## Preserve

- Feature flags and timeout controls in [`../../../koda/config.py`](../../../koda/config.py)
- Approval and supervised-mode rules for write operations
- Blocked-pattern enforcement for shell-like inputs
- Read-only guarantees for PostgreSQL access
- Clear disabled-path behavior when an integration is not configured

## Required Checks

- Add configuration in [`../../../koda/config.py`](../../../koda/config.py) instead of scattered environment reads.
- Update [`.env.example`](../../../.env.example) when users need to provide new settings.
- Add tests for enabled, disabled, and blocked paths.
- If the feature is prompt-exposed, keep prompt documentation and dispatcher behavior aligned.

## Repository-Specific Reminders

- [`../../../koda/services/db_manager.py`](../../../koda/services/db_manager.py) enforces read-only SQL behavior and is not a general-purpose database client.
- [`../../../koda/services/tool_dispatcher.py`](../../../koda/services/tool_dispatcher.py) is where read-versus-write classification lives for runtime agent tools.
- Runtime integrations should remain narrow service modules, not grow into handler-heavy logic.
