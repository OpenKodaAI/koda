# Web E2E Notes

The web app has an authenticated Playwright suite for the disposable Docker dev
stack. It exercises setup/login, dashboard navigation, runtime execution detail,
RunGraph/replay, approvals deny paths, skills packages, evals/release quality,
Telegram channel gateway, onboarding readiness, sessions and squad-adjacent
surfaces.

## Local Authenticated E2E

From the repository root:

```bash
cat > .env.e2e.local <<'EOF'
AGENT_ID=KODA
AGENT_TOKEN=e2e-telegram-token
ALLOWED_USER_IDS=
CONTROL_PLANE_API_TOKEN=e2e-control-plane-token-local-only-32chars
WEB_OPERATOR_SESSION_SECRET=e2e-web-session-secret-local-only-32chars
POSTGRES_USER=koda
POSTGRES_PASSWORD=koda_e2e_password
POSTGRES_DB=koda
S3_ACCESS_KEY_ID=koda_e2e_access
S3_SECRET_ACCESS_KEY=koda_e2e_secret_key_local_only
WEB_PORT=3000
CONTROL_PLANE_PORT=8090
KODA_E2E=1
KODA_TEST=1
EOF

docker compose -p koda-e2e --env-file .env.e2e.local -f docker-compose.yml -f docker-compose.dev.yml down -v
docker compose -p koda-e2e --env-file .env.e2e.local -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -p koda-e2e --env-file .env.e2e.local -f docker-compose.yml -f docker-compose.dev.yml exec -T app python scripts/seed_demo_data.py --apply
docker compose -p koda-e2e --env-file .env.e2e.local -f docker-compose.yml -f docker-compose.dev.yml exec -T app python scripts/seed_e2e_data.py --apply

pnpm install --frozen-lockfile
pnpm --filter koda-web exec playwright install chromium
PLAYWRIGHT_SKIP_WEB_SERVER=1 KODA_WEB_BASE_URL=http://127.0.0.1:3000 pnpm --filter koda-web test:e2e
```

Artifacts are written under `apps/web/test-results/` and
`apps/web/playwright-report/`; both are ignored by git. The auth storage state
is local-only under `apps/web/tests/e2e/.auth/`.

The console guard treats `pageerror` and console `error` events as failures.
Specs that intentionally exercise a browser-visible 4xx deny path must declare
that specific status in their local guard allowlist; 5xx responses are never
allowlisted.

## Documentation Screenshots

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

The screenshot helper uses Python Playwright and the existing web operator
session cookie format.
