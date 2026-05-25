# Safe Readonly KodaSkill Example

This package demonstrates the Phase 4 local-first extension contract:

- `koda-skill.yaml` is the primary manifest.
- `skills/safe-review.md` provides prompt-skill content.
- `handlers.py` exposes one read-only tool.
- The package requests no secrets, shell, install scripts, or network access.

Scan before install:

```bash
curl -X POST http://127.0.0.1:8090/api/control-plane/agents/KODA/skills/packages/scan \
  -H 'Content-Type: application/json' \
  -d '{"path":"examples/skills/safe-readonly"}'
```

Install after an `allow` scan:

```bash
curl -X POST http://127.0.0.1:8090/api/control-plane/agents/KODA/skills/packages/install \
  -H 'Content-Type: application/json' \
  -d '{"path":"examples/skills/safe-readonly"}'
```
