# Operations Runbooks

Runbooks for self-hosting Koda after the local or VPS stack is installed.

## Read First

| Runbook | Use it when |
|---|---|
| [Top-tier release train](top-tier-release-train.md) | Before starting or closing any top-tier roadmap phase |
| [Top-tier roadmap assurance](top-tier-roadmap-assurance.md) | Before claiming roadmap coverage, phase completeness, or release-quality maturity |
| [Scaling and resilience](scaling-resilience-runbook.md) | Before changing queue, runtime, provider, MCP, browser, or operations UI behavior |
| [HITL approvals](hitl-approval-runbook.md) | Before changing approval decisions, pending approval storage, or dashboard approval UX |
| [Sandbox doctor](sandbox-doctor-runbook.md) | Before changing sandbox policy, doctor checks, MCP isolation, mounts, env, browser, or egress behavior |
| [Skills and plugins](skills-plugin-runbook.md) | Before scanning, installing, uninstalling, rolling back, or troubleshooting local skill packages |
| [Workspace directory import](workspace-directory-import-runbook.md) | Before importing Codex, Claude, Cursor, MCP, or skill config from a local project folder |
| [Evals and release quality](evals-release-runbook.md) | Before creating evals from runs, exporting trajectories, or closing release-quality gates |
| [Improvement proposals](improvement-proposal-runbook.md) | Before approving, validating, applying, or rolling back self-improvement proposals |
| [Memory governance](memory-governance-runbook.md) | Before changing memory scanners, namespaces, recall explanations, or utility feedback |
| [Channel gateway](channel-gateway-runbook.md) | Before connecting Telegram, approving senders, debugging identity denials, or rotating channel access |
| [Onboarding readiness](onboarding-readiness-runbook.md) | Before claiming clean-install readiness, first-use UX completeness, or OSS setup maturity |
| [Thread replies](thread-replies-runbook.md) | Before enabling reply obligations, agent follow-ups, coordinator synthesis, or room reply troubleshooting |
| [Quality cockpit](quality-cockpit-runbook.md) | Before converting quality failures into proposals or claiming P4/P5 quality dashboard coverage |
| [Backup and restore](backup-restore.md) | Before production and during recovery drills |
| [Upgrade](upgrade.md) | Every release |
| [Hardening](hardening.md) | Before exposing the dashboard beyond yourself |
| [Observability](observability.md) | Before debugging stability or capacity issues |
| [Cluster mode](cluster-mode.md) | When one supervisor host is not enough |
| [Incident response](incident-response.md) | When something is already wrong |

## Operational Topology

```text
Edge / localhost
  |
web :3000
  |
app :8090
  |
runtime-kernel :50061
  |
agent workers

sidecars:
  security :50065
  memory :50063
  artifact :50064
  retrieval :50062

state:
  postgres
  S3-compatible object storage
  koda-state volume
  koda-runtime volume
```

## Daily Checks

```bash
docker compose ps
curl http://127.0.0.1:3000/api/health
curl http://127.0.0.1:8090/health
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

Healthy means:

- web and app containers are reachable
- Postgres and object storage are ready
- sidecars respond to gRPC probes
- active agent workers are alive
- scheduler/background loops are not degraded

## State Locations

- `postgres-data` volume: control plane, runtime, queue, audit, knowledge, memory.
- object-storage volume: object-backed artifacts and evidence.
- `koda-state` volume: master key, encrypted secrets, bootstrap state.
- `koda-runtime` volume: runtime home, provider CLI state, worker scratch roots.

## Demo Screenshots

For docs or product walkthroughs:

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

Clear afterward:

```bash
docker compose exec app python scripts/seed_demo_data.py --clear
```
