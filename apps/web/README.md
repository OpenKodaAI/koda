## Koda Web

This package contains the official Next.js operator interface for Koda.

### Local development

```bash
cp .env.example .env.local
pnpm install
pnpm dev:web
```

The app expects a reachable Koda control plane, usually at `http://127.0.0.1:8090`.

### Docker

The root `docker-compose.yml` starts this app as the `web` service and publishes it on port `3000`.

### Scripts

- `pnpm dev`
- `pnpm lint`
- `pnpm test`
- `pnpm build`
