# Repository Agent Guide

Use this file as the operational starting point for Claude Code working in this repository. The matching [`AGENTS.md`](AGENTS.md) file mirrors the same repository guidance for Codex and other `AGENTS.md`-aware tooling.

## Read Order

Follow this order before making non-trivial changes:

1. [`README.md`](README.md)
2. [`docs/ai/repo-map.yaml`](docs/ai/repo-map.yaml)
3. [`docs/ai/llm-compatibility.md`](docs/ai/llm-compatibility.md)
4. [`docs/ai/architecture-overview.md`](docs/ai/architecture-overview.md)
5. [`docs/ai/runtime-flows.md`](docs/ai/runtime-flows.md)
6. [`docs/ai/configuration-and-prompts.md`](docs/ai/configuration-and-prompts.md)
7. the closest subtree guide:
   - [`koda/CLAUDE.md`](koda/CLAUDE.md)
   - [`koda/services/CLAUDE.md`](koda/services/CLAUDE.md)
   - [`koda/memory/CLAUDE.md`](koda/memory/CLAUDE.md)
   - [`tests/CLAUDE.md`](tests/CLAUDE.md)
   - [`apps/web/CLAUDE.md`](apps/web/CLAUDE.md) — **UI design system & principles** (mandatory for any `apps/web/` change)

If another tool expects `AGENTS.md`, the guidance is mirrored there. The provider-neutral content still lives in [`docs/ai`](docs/ai), [`docs/ai/repo-map.yaml`](docs/ai/repo-map.yaml), and each repo-local [`SKILL.md`](docs/ai/skills/repo-orientation/SKILL.md).

Public product and contributor documentation lives in [`docs/README.md`](docs/README.md), [`docs/install`](docs/install), [`docs/architecture`](docs/architecture), and [`docs/reference`](docs/reference). Keep that layer distinct from the AI-oriented repository guidance in [`docs/ai`](docs/ai).

## Core Invariants

- [`koda/__main__.py`](koda/__main__.py) is the runtime entrypoint and registers Telegram handlers.
- [`koda/config.py`](koda/config.py) is the central source for environment-driven behavior, prompt composition, and namespaced paths.
- [`koda/services/queue_manager.py`](koda/services/queue_manager.py) is the orchestration spine from queued work to provider execution and final response delivery.
- Runtime prompt templates exposed to end users through `/skill` live in [`koda/skills`](koda/skills).
- Repo-local guidance skills for working on this repository live in [`docs/ai/skills`](docs/ai/skills).
- Each repo-local [`SKILL.md`](docs/ai/skills/repo-orientation/SKILL.md) is the canonical provider-neutral instruction file. [`docs/ai/skills/repo-orientation/agents/openai.yaml`](docs/ai/skills/repo-orientation/agents/openai.yaml) and its siblings add optional Codex metadata only.
- [`AGENTS.md`](AGENTS.md) and the matching subtree `AGENTS.md` files mirror this guidance for `AGENTS.md`-aware tooling.
- The canonical machine-readable repo index lives at [`docs/ai/repo-map.yaml`](docs/ai/repo-map.yaml) and must match [`scripts/generate_repo_map.py`](scripts/generate_repo_map.py).
- Per-agent runtime prompt behavior is derived from control-plane documents and the compiled runtime prompt contract, not repository prompt files.

## Safe Editing Rules

- Trace the full request path before editing behavior. For most features that means handlers, queue orchestration, provider execution, response sending, and tests.
- Keep configuration changes centralized in [`koda/config.py`](koda/config.py). If you add a new setting, also update [`.env.example`](.env.example) and the relevant docs.
- Treat security guardrails as first-class behavior. Command blocking, approval flow, safe path handling, and read-only database rules are not optional.
- Keep runtime and repository-guidance layers separate. Do not move repository guidance into runtime skills or control-plane agent documents unless explicitly asked.
- When you change repository guidance, keep the matching `CLAUDE.md` and `AGENTS.md` entrypoints aligned.
- Do not translate existing PT-BR agent-facing prompt content unless the task explicitly requires it.

## Required Validation

Run these checks after code changes and before considering the task complete:

- `ruff check .`
- `ruff format --check .`
- `mypy koda/ --ignore-missing-imports`
- `pytest --cov=koda --cov-report=term-missing`
- `pnpm lint:web`
- `pnpm test:web`
- `pnpm build:web`

When the task only changes the AI-friendly documentation layer, also run:

- `python3 scripts/generate_repo_map.py --check`
- `pytest -q tests/test_ai_docs.py tests/test_repo_map.py tests/test_open_source_hygiene.py`

When the task touches the Rust workspace, also run:

- `cargo fmt --check --manifest-path rust/Cargo.toml`
- `cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml --workspace`

## Common Decision Points

- New Telegram command: update the owning handler module, register it in [`koda/__main__.py`](koda/__main__.py), adjust help text if needed, and add tests.
- New agent tool: keep [`koda/services/tool_prompt.py`](koda/services/tool_prompt.py) and [`koda/services/tool_dispatcher.py`](koda/services/tool_dispatcher.py) aligned.
- New memory behavior: keep [`koda/memory/config.py`](koda/memory/config.py), the relevant pipeline modules, and memory tests in sync.
- New repository guidance: place it under [`docs/ai`](docs/ai) or [`docs/ai/skills`](docs/ai/skills), not under agent-facing runtime assets or control-plane agent documents.
- Changes to the AI-guidance layer should also update [`docs/ai/repo-map.yaml`](docs/ai/repo-map.yaml) through [`scripts/generate_repo_map.py`](scripts/generate_repo_map.py).
