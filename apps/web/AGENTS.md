# Koda Web Agent Guide

This app lives inside the root Obsidian Vault named `Koda`.

Before non-trivial work under `apps/web/`:

1. Read the root workspace context and persistent memory:
   - `obsidian vault=Koda read path="00_Index/Koda Workspace.md"`
   - `obsidian vault=Koda read path="60_Memory/Agent Operating Memory.md"`
   - `obsidian vault=Koda read path="60_Memory/User Preferences.md"`
   - `obsidian vault=Koda read path="60_Memory/Project Memory.md"`
2. Read `koda/AGENTS.md` from the main repository root.
3. Read `apps/web/CLAUDE.md`; it is the canonical UI design and implementation guide.
4. Search Obsidian for task-specific context before asking the user to repeat it.
5. Inspect the relevant component, route, hook, API, and tests before editing.

## Validation

From `koda/`:

```bash
pnpm lint:web
pnpm test:web
pnpm build:web
```

Run narrower tests during implementation when possible.

## Memory

Persist reusable context in the root Vault under `60_Memory/`. Record task
handoffs in the daily note or a session note. Do not store secrets or raw
environment values.

If `obsidian read` is unavailable in this agent session, use the workspace
fallback reader:

```bash
../../../bin/koda-vault-read "60_Memory/User Preferences.md"
```
