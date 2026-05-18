# Koda Repository Guide

Operational guide for any coding agent working in this repository.

This repository is inside the root Obsidian Vault named `Koda`. Before asking
the user to repeat context, read the root workspace memory:

```bash
obsidian vault=Koda read path="00_Index/Koda Workspace.md"
obsidian vault=Koda read path="60_Memory/Agent Operating Memory.md"
obsidian vault=Koda read path="60_Memory/User Preferences.md"
obsidian vault=Koda read path="60_Memory/Project Memory.md"
obsidian vault=Koda search query="<topic>" limit=10
```

If `obsidian read` is unavailable in this agent session, use the workspace
fallback reader instead:

```bash
../bin/koda-vault-read "60_Memory/User Preferences.md"
```

Persist durable preferences, project facts, and handoffs in `60_Memory/`.

## Read Order

Before non-trivial changes, read in this order:

1. Root Obsidian memory listed above.
2. [`README.md`](README.md) — product overview, install paths, public surface
3. The closest module the change touches (handler, service, memory, etc.)
4. [`apps/web/AGENTS.md`](apps/web/AGENTS.md) and [`apps/web/CLAUDE.md`](apps/web/CLAUDE.md) — UI design system & principles (mandatory for any `apps/web/` change)

Public product and contributor documentation lives in [`docs/`](docs/README.md).

## Core Invariants

- [`koda/__main__.py`](koda/__main__.py) is the runtime entrypoint and registers Telegram handlers.
- [`koda/config.py`](koda/config.py) is the central source for environment-driven behavior, prompt composition, and namespaced paths.
- [`koda/services/queue_manager.py`](koda/services/queue_manager.py) is the orchestration spine from queued work through provider execution to response delivery.
- Runtime prompt templates exposed to end users via `/skill` live in `koda/skills`.
- Per-agent runtime prompt behavior is derived from control-plane documents and the compiled runtime prompt contract, not repository prompt files.
- Setup / login / recovery contract is documented in [`docs/security/authentication.md`](docs/security/authentication.md). Changes to [`koda/control_plane/operator_auth.py`](koda/control_plane/operator_auth.py), [`koda/control_plane/password_policy.py`](koda/control_plane/password_policy.py), [`koda/control_plane/bootstrap_file.py`](koda/control_plane/bootstrap_file.py), or the web auth routes must update that document and the matching tests in the same change.

## Safe Editing Rules

- Trace the full request path before editing behavior. For most features that means handlers, queue orchestration, provider execution, response delivery, and tests.
- Keep configuration changes centralized in [`koda/config.py`](koda/config.py). If you add a new setting, also update `.env.example` and the relevant docs.
- Treat security guardrails as first-class behavior. Command blocking, approval flow, safe path handling, and read-only database rules are not optional.
- Do not translate existing PT-BR agent-facing prompt content unless the task explicitly requires it.

## Common Decision Points

- New Telegram command: update the owning handler module, register it in [`koda/__main__.py`](koda/__main__.py), adjust help text if needed, and add tests.
- New agent tool: keep [`koda/services/tool_prompt.py`](koda/services/tool_prompt.py) and [`koda/services/tool_dispatcher.py`](koda/services/tool_dispatcher.py) aligned.
- New memory behavior: keep [`koda/memory/config.py`](koda/memory/config.py), the relevant pipeline modules, and memory tests in sync.
- New OpenAI-compatible provider: add a builder + entry to `_PROFILE_BUILDERS` in [`koda/services/openai_compatible_runner.py`](koda/services/openai_compatible_runner.py); no new module file required.

## Required Validation

Run after every code change before considering the task complete:

- `ruff check .`
- `ruff format --check .`
- `mypy koda/ --ignore-missing-imports`
- `pytest --cov=koda --cov-report=term-missing`
- `pnpm lint:web`
- `pnpm test:web`
- `pnpm build:web`

When the change touches the Rust workspace, also run:

- `cargo fmt --check --manifest-path rust/Cargo.toml`
- `cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml --workspace`
