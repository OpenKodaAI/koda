# Demo Data And Screenshots

Use this workflow when README/docs screenshots need a complete local UI with realistic but fake operational data.

## Seed

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
```

What it fills:

- demo workspaces and paused demo agents
- Koda operational history when the local `KODA` agent exists
- tasks, costs, executions, sessions, schedules, DLQ rows, runtime projections, memory records, and knowledge assets

All rows are tagged with `koda-docs-demo` or scoped to managed `DEMO_` agents.

## Capture

```bash
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

The capture script opens authenticated dashboard pages and writes stable PNG names such as:

- `overview.png`
- `costs.png`
- `executions.png`
- `sessions.png`
- `control-plane.png`
- `agent-detail.png`
- `runtime.png`
- `runtime-task.png`

## Clear

```bash
docker compose exec app python scripts/seed_demo_data.py --clear
```

This removes only the demo scope and leaves real local operator data alone.
