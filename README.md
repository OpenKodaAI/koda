<p align="center">
  <img src="public/koda-mark-white.svg" alt="Koda mark" width="88" />
</p>

<h1 align="center">Koda</h1>

<p align="center">
  <strong>Open-source harness for orchestrating multi-agent, multi-provider AI systems.</strong>
</p>

<p align="center">
  Bring up the platform stack first. Configure providers, agents, access, secrets, and operations through Koda itself.
</p>

<p align="center">
  <a href="docs/install/local.md"><img alt="Quickstart" src="https://img.shields.io/badge/Quickstart-Docker--first-0F766E?style=for-the-badge" /></a>
  <a href="docs/README.md"><img alt="Documentation" src="https://img.shields.io/badge/Documentation-GitHub--native-162126?style=for-the-badge" /></a>
  <a href="docs/reference/api.md"><img alt="API Reference" src="https://img.shields.io/badge/API-OpenAPI-0B84D8?style=for-the-badge" /></a>
  <a href="docs/architecture/overview.md"><img alt="Architecture" src="https://img.shields.io/badge/Architecture-Control%20Plane%20%2B%20Web%20%2B%20Runtime-5C6B73?style=for-the-badge" /></a>
</p>

<p align="center">
  <a href="docs/install/local.md"><img alt="Postgres" src="https://img.shields.io/badge/Postgres-Durable%20state-336791?style=flat-square" /></a>
  <a href="docs/install/local.md"><img alt="SeaweedFS" src="https://img.shields.io/badge/SeaweedFS-S3--compatible%20storage-0F766E?style=flat-square" /></a>
  <a href="docs/reference/api.md"><img alt="Control Plane" src="https://img.shields.io/badge/Control%20Plane-Public%20HTTP%20surface-111827?style=flat-square" /></a>
  <a href="docs/architecture/runtime.md"><img alt="Runtime" src="https://img.shields.io/badge/Runtime-Inspectable%20execution-374151?style=flat-square" /></a>
</p>

<p align="center">
  <img src="docs/assets/brand/koda-hero.png" alt="Koda illustration" width="20%" />
</p>

<p align="center">
  <a href="docs/install/local.md"><strong>Install locally</strong></a>
  ·
  <a href="docs/install/vps.md"><strong>Deploy on a VPS</strong></a>
  ·
  <a href="docs/config/reference.md"><strong>Configuration reference</strong></a>
  ·
  <a href="docs/openapi/control-plane.json"><strong>OpenAPI</strong></a>
</p>

Koda is a control-plane-first platform for orchestrating AI agents with durable state, object storage, knowledge retrieval, memory recall, runtime inspection, and operator-facing setup flows. It is designed to act as a harness: you bring the providers, prompts, policies, and task shapes that fit your use case, and Koda supplies the operational runtime around them.

This repository is the canonical open-source monorepo for Koda. It combines:

- the Python platform backend at the repository root
- the official Next.js operations UI in `apps/web`
- public docs, OpenAPI, Docker assets, and contributor guidance in one place

The public quickstart brings up the platform stack first. Product configuration such as providers, access policy, secrets, agents, and integrations is completed through the control plane and its API surface.

## Quickstart

1. Clone the repository.
2. Run the installer.
3. Open the dashboard and finish bootstrap in the control plane.

```bash
git clone https://github.com/OpenKodaAI/koda.git /opt/koda
cd /opt/koda
./scripts/install.sh
```

When the installer completes, use the two URLs it prints:

- Dashboard: `http://127.0.0.1:3000`
- Bootstrap: `http://127.0.0.1:8090/setup`

From there you can validate platform health, configure access, connect a provider, and create your first agent without editing per-agent `.env` values.

## What The Stack Starts

- `web` on port `3000` for the operator-facing UI
- `app` on port `8090` for `/setup`, `/health`, `/api/control-plane/*`, and `/api/runtime/*`
- `postgres` for durable state
- `seaweedfs` plus `seaweedfs-init` for bundled S3-compatible object storage

## Control Plane Surface

The operational UI is part of the product itself. The dashboard runs as the official web frontend and proxies control-plane and runtime calls back to the backend:

<p align="center">
  <img src="docs/assets/screenshots/setup.png" alt="Koda control plane interface" width="82%" />
</p>

## What Koda Includes

- A control plane for setup, provider configuration, agent management, secrets, and operational settings
- A dedicated web dashboard for operations, onboarding, runtime inspection, and control-plane workflows
- A runtime API for inspection, orchestration, command execution, and runtime supervision
- Postgres-backed durable state for runtime, control-plane, knowledge, memory, and audit records
- SeaweedFS-backed bundled object storage for the quickstart path through a generic S3-compatible contract
- Retrieval, memory, and artifact services aligned behind typed internal contracts
- Docker-first deployment for local environments and single-node VPS installs
- A purpose-agnostic harness that can back research, operations, automation, support, engineering, or domain-specific agent workflows

## Core Capabilities

- Control-plane-first bootstrap with web onboarding instead of hand-maintained per-agent env files
- Multi-agent orchestration with isolated runtime state, prompt contracts, and operational settings
- Multi-provider execution so each agent can be configured for the models and tools that fit its role
- Harness-style architecture that lets operators define agents for any niche, workflow, or task class
- Durable artifact processing for documents, media, screenshots, and derived evidence
- Knowledge retrieval and memory recall to ground agent execution with relevant context
- Runtime visibility through health, setup, dashboard, control-plane, and OpenAPI-backed public surfaces
- Provider-agnostic architecture with explicit setup and verification flows
- Production-friendly quickstart with Postgres, SeaweedFS, health checks, and doctor tooling

## How The Platform Is Structured

Koda is organized around a few stable layers:

- **Web UI:** Next.js operator interface in `apps/web`
- **Control plane:** setup, policy, secrets, provider connections, agent definitions, and public onboarding routes
- **Runtime:** execution supervision, queue orchestration, runtime APIs, and agent tool dispatch
- **Knowledge and memory:** retrieval, recall, curation, and context assembly
- **Artifacts and storage:** durable metadata, object-backed binaries, and evidence generation
- **Infrastructure:** Docker, Postgres, bundled S3-compatible storage, health checks, and operator tooling

For a public architecture walkthrough, start with [Documentation Index](docs/README.md), [Architecture Overview](docs/architecture/overview.md), and [Runtime Architecture](docs/architecture/runtime.md).

## Installation Paths

- [Local install](docs/install/local.md)
- [VPS install](docs/install/vps.md)
- [Object storage migration](docs/install/object-storage-migration.md)
- [Configuration reference](docs/config/reference.md)

## Public Interfaces

- `/` for the main operations dashboard served by `apps/web`
- `/setup` for first-boot configuration
- `/api/control-plane/agents/*` for canonical agent-management operations
- `/api/control-plane/dashboard/agents/*` for canonical operational dashboard data
- `/api/runtime/*` for runtime inspection and control
- [`docs/openapi/control-plane.json`](docs/openapi/control-plane.json) as the maintained public API contract
- [API reference](docs/reference/api.md) for an operator-facing summary of the HTTP surface

## Development

Backend development:

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy koda/ --ignore-missing-imports
pytest --cov=koda --cov-report=term-missing
```

Web development:

```bash
pnpm install
cp apps/web/.env.example apps/web/.env.local
pnpm dev:web
```

## Documentation

- [Documentation index](docs/README.md)
- [Architecture overview](docs/architecture/overview.md)
- [Runtime architecture](docs/architecture/runtime.md)
- [API reference](docs/reference/api.md)
- [Local install](docs/install/local.md)
- [VPS install](docs/install/vps.md)
- [Configuration reference](docs/config/reference.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)

## Contributing, Security, And Licensing

Contributors should start with [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, validation, and documentation expectations. Security-sensitive reporting guidance lives in [SECURITY.md](SECURITY.md), and community participation expectations live in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Koda is published under the Apache-2.0 license.

## Developer And AI-Friendly Entry Points

- [AGENTS.md](AGENTS.md)
- [CLAUDE.md](CLAUDE.md)
- [docs/ai/repo-map.yaml](docs/ai/repo-map.yaml)
- [docs/ai/llm-compatibility.md](docs/ai/llm-compatibility.md)
- [docs/ai/architecture-overview.md](docs/ai/architecture-overview.md)
- [docs/ai/runtime-flows.md](docs/ai/runtime-flows.md)
- [docs/ai/configuration-and-prompts.md](docs/ai/configuration-and-prompts.md)

## Validation

```bash
ruff check .
ruff format --check .
mypy koda/ --ignore-missing-imports
pytest --cov=koda --cov-report=term-missing
pnpm lint:web
pnpm test:web
pnpm build:web
python3 scripts/generate_repo_map.py --check
```
