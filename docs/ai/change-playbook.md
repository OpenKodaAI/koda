# Change Playbook

Use this playbook to make common changes without fighting the repository structure.

Before following any recipe, check [`repo-map.yaml`](repo-map.yaml) to confirm the owning files, matching tests, and nearest repo-local skills for the area you are touching. Check [`llm-compatibility.md`](llm-compatibility.md) when you need to keep Codex, Claude Code, and provider-neutral artifacts aligned.

## Add Or Change A Telegram Command

1. Find the owning handler module under [`../../koda/handlers`](../../koda/handlers).
2. Implement the command or extend the closest existing command family.
3. Register the command in [`../../koda/__main__.py`](../../koda/__main__.py).
4. Update help text if the command is user-visible through `/help` or `/start`.
5. Add tests in [`../../tests/test_handlers`](../../tests/test_handlers).

Use this pattern for command aliases too. Registration and help text are easy to forget.

## Add Or Change A Runtime Agent Tool

1. Define the prompt-facing description in [`../../koda/services/tool_prompt.py`](../../koda/services/tool_prompt.py).
2. Add execution behavior in [`../../koda/services/tool_dispatcher.py`](../../koda/services/tool_dispatcher.py).
3. Decide whether the tool is read-only or write-capable.
4. If the tool writes state, make sure supervised mode still blocks it correctly.
5. Add tests in [`../../tests/test_services/test_tool_dispatcher.py`](../../tests/test_services/test_tool_dispatcher.py), [`../../tests/test_services/test_tool_prompt.py`](../../tests/test_services/test_tool_prompt.py), or a more specific service test module.

Do not update only one side. The prompt and dispatcher must stay aligned.

## Add Or Change An External Integration

1. Add feature flags, timeouts, blocked-pattern settings, or connection settings in [`../../koda/config.py`](../../koda/config.py).
2. Create or extend a focused service in [`../../koda/services`](../../koda/services).
3. Expose the integration through handlers or tool dispatch only after the service contract is clear.
4. Update [`.env.example`](../../.env.example) when the user must supply new configuration.
5. Add tests for success paths, disabled paths, and blocked paths.

Keep integrations narrow. Prefer one focused module per provider or capability.

## Change The Queue Or Provider Execution Flow

1. Read [`runtime-flows.md`](runtime-flows.md).
2. Inspect [`../../koda/services/queue_manager.py`](../../koda/services/queue_manager.py) and [`../../koda/services/claude_runner.py`](../../koda/services/claude_runner.py) together.
3. Identify whether the change affects prompt assembly, queueing, retries, tool loops, response formatting, or persistence.
4. Update the narrowest tests that prove the behavior change.
5. Re-run the full validation suite because queue changes have wide blast radius.

## Change The Memory Pipeline

1. Read [`../../koda/memory/AGENTS.md`](../../koda/memory/AGENTS.md).
2. Decide whether the change belongs in recall, extraction, storage, scheduling, or configuration.
3. Preserve best-effort semantics. Memory should enrich the runtime, not become a hard blocker.
4. Add or update tests in [`../../tests/test_memory`](../../tests/test_memory).
5. If configuration changes, update [`.env.example`](../../.env.example) and [`configuration-and-prompts.md`](configuration-and-prompts.md).

## Change Prompts Or Skills

1. Runtime agent prompt changes belong in the control-plane document layers and compiled prompt contract under [`../../koda/control_plane`](../../koda/control_plane).
2. Runtime `/skill` prompt-template changes belong in [`../../koda/skills`](../../koda/skills).
3. Repository guidance and repo-local skills belong in [`../`](../) and [`skills`](skills).
4. Keep matching `AGENTS.md` and `CLAUDE.md` entrypoints aligned when local repository guidance changes.

Do not merge these layers accidentally.

## Validation Checklist

Run at least these commands after code changes:

- `ruff check .`
- `ruff format --check .`
- `mypy koda/ --ignore-missing-imports`
- `pytest --cov=koda --cov-report=term-missing`
- `pnpm lint:web`
- `pnpm test:web`
- `pnpm build:web`

Run this extra check after AI-doc changes:

- `python3 ../../scripts/generate_repo_map.py --check`
- `pytest -q ../../tests/test_ai_docs.py ../../tests/test_repo_map.py ../../tests/test_open_source_hygiene.py`

Run these extra checks when the change touches the Rust workspace:

- `cargo fmt --check --manifest-path ../../rust/Cargo.toml`
- `cargo clippy --manifest-path ../../rust/Cargo.toml --workspace --all-targets -- -D warnings`
- `cargo test --manifest-path ../../rust/Cargo.toml --workspace`

## Change The Repo Map

1. Update the relevant AI docs, `AGENTS.md` and `CLAUDE.md` entrypoints, repo-local skills, or tests.
2. Regenerate the canonical map with `python3 ../../scripts/generate_repo_map.py --write`.
3. Re-run `python3 ../../scripts/generate_repo_map.py --check`.
4. Re-run [`../../tests/test_ai_docs.py`](../../tests/test_ai_docs.py), [`../../tests/test_repo_map.py`](../../tests/test_repo_map.py), and [`../../tests/test_open_source_hygiene.py`](../../tests/test_open_source_hygiene.py).
