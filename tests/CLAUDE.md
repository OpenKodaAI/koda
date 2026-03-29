# Test Suite Guide

The test suite mirrors the application structure and is the safety net for behavior changes. The matching [`AGENTS.md`](AGENTS.md) file mirrors the same local rules for `AGENTS.md`-aware tooling.

## Layout

- [`conftest.py`](conftest.py): shared environment defaults and common mocks
- [`test_handlers`](test_handlers): Telegram adapter and command coverage
- [`test_services`](test_services): orchestration, integrations, runtime tools, and safety rules
- [`test_memory`](test_memory): recall, extraction, scheduling, and storage behavior
- [`test_utils`](test_utils): focused unit tests for helper modules

## Rules

- Add tests next to the subsystem you changed. Do not hide service regressions inside unrelated handler tests.
- Keep tests isolated from live services. Mock Telegram, Claude CLI, browser, network, and filesystem side effects unless the test explicitly targets that integration boundary.
- Reuse the fixtures in [`conftest.py`](conftest.py) whenever possible instead of recreating broad mocks.
- When adding new configuration-driven behavior, patch module constants or environment-dependent paths deliberately so tests stay deterministic.

## Documentation Contract

- [`test_ai_docs.py`](test_ai_docs.py) validates the AI-friendly documentation layer.
- [`test_repo_map.py`](test_repo_map.py) validates the deterministic repo-map generator and the committed YAML artifact.
- If you add or rename AI entrypoint docs or repo-local skills, update that contract test in the same change.
