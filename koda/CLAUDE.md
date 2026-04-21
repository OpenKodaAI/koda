# koda Package Guide

This package contains the application runtime. Read this guide before editing anything under `koda`. The matching [`AGENTS.md`](AGENTS.md) file mirrors the same local rules for `AGENTS.md`-aware tooling.

## Responsibilities By Area

- [`__main__.py`](__main__.py): process startup, handler registration, health server lifecycle, and graceful shutdown
- [`config.py`](config.py): environment loading, feature flags, path selection, prompt assembly, and guardrail constants
- [`state`](state): typed Postgres-first stores for history, runtime, scheduler, control-plane assets, cache, memory, and governance
- [`handlers`](handlers): Telegram-facing adapters
- [`services`](services): orchestration, external integrations, schedulers, runtime tools, and provider CLI wrappers
- [`memory`](memory): memory recall, extraction, storage, digests, and maintenance
- [`utils`](utils): narrow helpers shared across handlers and services
- [`skills`](skills): runtime expert-skill prompt templates surfaced to end users

## Boundary Rules

- Keep handlers thin. They should validate Telegram input, build or route requests, and hand work to services.
- Keep orchestration in services. Do not spread queue management, provider execution, or approval logic across handlers.
- Keep environment lookups in [`config.py`](config.py) or modules built on top of it. Avoid ad hoc `os.environ` reads elsewhere.
- Keep persistence rules in dedicated storage modules under [`state`](state), runtime stores, or knowledge repositories. Do not embed direct SQL into unrelated handlers.
- Keep runtime skill templates in [`skills`](skills) aligned with how [`koda/services/templates.py`](services/templates.py) loads them.

## Extension Patterns

- Add a new Telegram command by editing the relevant handler module and registering the command in [`__main__.py`](__main__.py).
- Add a new integration by introducing a focused service module, feature flags in [`config.py`](config.py), and tests for both happy-path and blocked-path behavior.
- Add a new user-visible instruction layer only after confirming whether it belongs in compiled control-plane agent documents, a runtime skill, or repository guidance.

## Do Not Break

- Multi-agent namespacing for prompts, logical state scope, and scratch directories
- The runtime distinction between runtime skills in [`skills`](skills) and repo-local guidance skills in [`../docs/ai/skills`](../docs/ai/skills)
- The assumption that agent-specific prompt behavior comes from control-plane documents and the compiled runtime prompt contract
