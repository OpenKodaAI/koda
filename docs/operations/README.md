# Operations runbooks

Operator-facing runbooks for self-hosting koda. The runtime layer
ships defaults that work for a single operator on one host; this
directory documents what to do when scale, hardening, or
incident-response demands more.

| Runbook | When to read |
|---|---|
| [backup-restore.md](backup-restore.md) | Before going to production, and monthly thereafter |
| [upgrade.md](upgrade.md) | Every release |
| [cluster-mode.md](cluster-mode.md) | When you need >1 supervisor host (medium-large internal teams) |
| [observability.md](observability.md) | Before a stability or capacity issue happens |
| [hardening.md](hardening.md) | Before exposing the control plane to anyone besides yourself |
| [incident-response.md](incident-response.md) | At the moment something is wrong |

These runbooks assume the docker-compose deployment from
[`docs/install/local.md`](../install/local.md) or
[`docs/install/vps.md`](../install/vps.md) and target the
single-tenant, multi-team flavor of koda — not a SaaS multi-tenant
deployment.

## Architecture quick reference

The deployment surface a self-hoster cares about:

```
┌──────────────────────────────────────────────────────────────────┐
│  Edge (TLS)                                                       │
│   ↓                                                               │
│  Web (Next.js, control-plane UI) :3000                            │
│  Control-plane API (Python aiohttp) :8090                         │
│   ↓                                                               │
│  Supervisor processes — spawn agent workers                       │
│   ↓ gRPC (UDS or TCP)                                             │
│  Sidecars (Rust): security :50065 · memory :50063 · artifact      │
│                   :50064 · retrieval :50062 · runtime-kernel      │
│                   :50061 · bot-gateway :50066 (opt-in) ·          │
│                   policy-engine :50067 (opt-in)                   │
│   ↓                                                               │
│  Postgres :5432 · S3-compatible object store :8333                │
└──────────────────────────────────────────────────────────────────┘
```

State lives in:
- `postgres-data` volume → control plane, agent assignments, audit, queue, knowledge_v2
- object-storage volume → artifacts, embeddings, snapshots
- `koda-state` volume → master key, secrets, runtime caches
- `koda-runtime` tmpfs → ephemeral worktrees, browser sessions
