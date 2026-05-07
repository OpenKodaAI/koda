# Web E2E Notes

The web app currently relies on Vitest plus backend/API tests for most automated coverage. Browser automation in this repository is used mainly for local smoke checks and documentation screenshots.

## Documentation Screenshots

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

The screenshot helper uses Python Playwright and the existing web operator session cookie format. It does not require `@playwright/test`.

## Smoke Direction

Future Playwright specs should cover:

- setup/login routing
- dashboard home
- control-plane agent catalog and detail
- runtime overview and task room
- costs, executions, sessions, routines, and memory review

Until a full browser suite exists, keep feature behavior covered by backend tests and colocated web unit tests.
