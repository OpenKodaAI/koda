<p align="center">
  <img src="assets/brand/koda-banner.png" alt="Koda banner" width="100%" />
</p>

# Koda Documentation

Koda is documented as an operator product first: install it, configure it from the dashboard, run agents, inspect the runtime, and keep the deployment safe.

![Koda overview](assets/screenshots/overview.png)

## Use Koda

- [Local install](install/local.md) — run Koda on your machine.
- [VPS install](install/vps.md) — single-node self-hosting path.
- [Configuration reference](config/reference.md) — what belongs in `.env` vs the control plane.
- [API reference](reference/api.md) — operator-facing HTTP surface.

## Understand The Platform

- [Architecture overview](architecture/overview.md)
- [Runtime architecture](architecture/runtime.md)
- [Object storage migration](install/object-storage-migration.md)
- [Demo data and screenshots](demo-data.md)
- [`openapi/control-plane.json`](openapi/control-plane.json)

```text
Dashboard
   -> Control Plane API
      -> Postgres + object storage
      -> Rust sidecars
      -> agent workers + provider CLIs
```

## Operate Safely

- [Operations runbooks](operations/README.md)
- [Backup and restore](operations/backup-restore.md)
- [Upgrade guide](operations/upgrade.md)
- [Hardening](operations/hardening.md)
- [Incident response](operations/incident-response.md)
- [Security readiness](security/README.md)

## Refresh Demo Screenshots

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

The seeded dataset is local-only and tagged with `koda-docs-demo`, so it can be cleared without touching real operator records:

```bash
docker compose exec app python scripts/seed_demo_data.py --clear
```

## Contributor Notes

- Python backend: repository root.
- Web dashboard: `apps/web/`.
- Web design guide: `apps/web/CLAUDE.md` until `apps/web/AGENTS.md` exists.
- Public screenshots and diagrams: `docs/assets`.
- Contributor guide: [CONTRIBUTING.md](../CONTRIBUTING.md).
