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
- [Top-tier phase contracts](architecture/top-tier-phase-contracts.md)
- [AgentTurn contract](architecture/agent-turn-contract.md)
- [ToolRegistry and native tools](architecture/tool-registry-native-tools.md)
- [RunGraph and replay contract](architecture/run-graph-replay.md)
- [KodaSkill plugin SDK](architecture/koda-skill-plugin-sdk.md)
- [Workspace directory config import](architecture/workspace-directory-import.md)
- [Evals and release quality](architecture/evals-release-quality.md)
- [Channel gateway and onboarding readiness](architecture/channel-gateway-onboarding.md)
- [Thread replies and agent coordination](architecture/thread-replies-agent-coordination.md)
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
- [Top-tier release train](operations/top-tier-release-train.md)
- [Top-tier roadmap assurance](operations/top-tier-roadmap-assurance.md)
- [Scaling and resilience runbook](operations/scaling-resilience-runbook.md)
- [HITL approval runbook](operations/hitl-approval-runbook.md)
- [Sandbox doctor runbook](operations/sandbox-doctor-runbook.md)
- [Skills and plugins runbook](operations/skills-plugin-runbook.md)
- [Workspace directory import runbook](operations/workspace-directory-import-runbook.md)
- [Evals and release quality runbook](operations/evals-release-runbook.md)
- [Channel gateway runbook](operations/channel-gateway-runbook.md)
- [Onboarding readiness runbook](operations/onboarding-readiness-runbook.md)
- [Thread replies runbook](operations/thread-replies-runbook.md)
- [Backup and restore](operations/backup-restore.md)
- [Upgrade guide](operations/upgrade.md)
- [Hardening](operations/hardening.md)
- [Incident response](operations/incident-response.md)
- [Security readiness](security/README.md)
- [MCP risk taxonomy](security/mcp-risk-taxonomy.md)
- [Skill supply-chain scanner](security/skill-supply-chain-scanner.md)

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
