# Playwright E2E specs

This directory hosts Playwright specs that exercise the 6 product surfaces
covered by the test plan in
`/Users/larissamiyoshi/.claude/plans/algumas-funcionalidades-do-koda-valiant-melody.md`:

| Spec file              | Feature   | Coverage                                                         |
| ---------------------- | --------- | ---------------------------------------------------------------- |
| `dql.spec.ts`          | DQL       | Saved query → table → CSV export; write rejected; signed URLs    |
| `routines.spec.ts`     | Routines  | 3-step wizard, pause/resume, run history, DLQ requeue            |
| `memory-review.spec.ts`| Memory    | Browse/curate memories, cluster merge, undo                       |
| `artifacts-upload.spec.ts` | Artifacts | Upload PDF, see extraction, download via signed URL              |
| `tools.spec.ts`        | Tools     | Tool card render, approval banner for writes, cancellation        |
| `voice.spec.ts`        | Voice     | `/voice` settings UI, voice picker, test playback                 |

## Bootstrap (one-time)

```bash
pnpm --filter web add -D @playwright/test
pnpm --filter web exec playwright install chromium
```

## Run

```bash
# All specs (requires Next dev server + Python backend in test mode)
pnpm --filter web test:e2e

# Smoke subset (no backend required — uses mock fixtures)
pnpm --filter web test:e2e -- --grep @smoke
```

## Notes

* Bootstrap is intentionally deferred until the suite has fixtures for
  authenticated state (`globalSetup.ts` writes `tests/e2e/.auth/storage.json`)
  and the Python backend exposes a `KODA_TEST=1` flag that bypasses real
  Telegram auth.
* Until then, the feature surfaces are covered by:
  - Backend integration tests (`tests/integration/` — 27 PG + 4 chaos for DQL alone).
  - Sanitization adversarial dataset (194 cases).
  - Pure-logic unit tests (300+ cases across memory, scheduling, artifacts, tools).
* Vitest specs colocated with components (`*.test.tsx`) cover unit-level
  rendering and prop handling without a browser.
