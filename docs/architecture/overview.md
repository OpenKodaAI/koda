# Architecture Overview

Koda is a control-plane-first harness for configurable AI agents. The repository ships the backend, the official dashboard, runtime supervision, public docs, Docker assets, and OpenAPI contract together.

## Mental Model

```text
Operator
  uses
Dashboard
  calls
Control Plane
  publishes configuration to
Runtime
  executes through
Provider CLIs + tools
  persists to
Postgres + object storage
```

Infrastructure comes up first. Product configuration happens after setup through the dashboard or `/api/control-plane/*`.

## Components

- **Dashboard:** Next.js app in `apps/web`, served on port `3000`.
- **Control plane:** setup, owner auth, providers, secrets, agents, workspaces, prompts, and runtime policy.
- **Runtime:** queues, worker supervision, task rooms, command execution, browser sessions, artifacts, and health.
- **Knowledge and memory:** retrieval traces, durable memories, curation, and context assembly.
- **Artifacts and storage:** metadata in Postgres, binaries through an S3-compatible object-store contract.
- **Sidecars:** Rust services for security, retrieval, memory, artifact processing, and runtime-kernel process control.

## Default Topology

```text
web :3000
  |
app :8090
  |
  +-- postgres :5432
  +-- seaweedfs :8333
  +-- security :50065
  +-- memory :50063
  +-- artifact :50064
  +-- retrieval :50062
  +-- runtime-kernel :50061
        |
        +-- agent worker processes
```

This topology is used by the local quickstart and the default single-node VPS path.

## State Boundaries

- Postgres is canonical for control-plane, runtime, queue, audit, memory, knowledge, and scheduler state.
- Object storage is canonical for object-backed artifacts and derived evidence.
- Local filesystem paths are scratch, runtime workspaces, or caches unless a document says otherwise.
- Browser sessions, terminals, and process trees are runtime state, not control-plane configuration.

## Public Surfaces

- `/setup`
- `/`
- `/control-plane`
- `/runtime`
- `/api/control-plane/*`
- `/api/runtime/*`
- [`../openapi/control-plane.json`](../openapi/control-plane.json)

For the execution lifecycle, continue with [Runtime Architecture](runtime.md).
For roadmap execution contracts, continue with
[Top-Tier Phase Contracts](top-tier-phase-contracts.md).
For Phase 1 runtime contracts, continue with
[AgentTurn Contract](agent-turn-contract.md) and
[ToolRegistry And Native Tools](tool-registry-native-tools.md).
For local extensibility contracts, continue with
[KodaSkill Plugin SDK](koda-skill-plugin-sdk.md).
For quality gates and deterministic evals, continue with
[Evals, Trajectory Export, And Release Quality](evals-release-quality.md).
For Phase 6 channel identity and first-run readiness, continue with
[Channel Gateway And Onboarding Readiness](channel-gateway-onboarding.md).
For operational replies and multi-agent coordination inside squad rooms,
continue with
[Thread Replies And Agent Coordination](thread-replies-agent-coordination.md).
