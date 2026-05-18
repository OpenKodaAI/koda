# Workspace Directory Import Runbook

Use **Import from folder** in the control-plane catalog when an existing project already has Codex, Claude, Cursor, MCP, or skill configuration that should seed a Koda workspace.

## Operator Flow

1. Pick a local project directory.
2. Scan the folder and review the badges by tool and risk.
3. Select only the safe instruction/rule sources you want in the workspace prompt.
4. Import the workspace.
5. Review any paused agent drafts or disabled MCP candidates before enabling them elsewhere.

The scan is non-mutating. Koda reads static files only and does not run hooks, MCP commands, package scripts, or skill code.

## Safety Checks

- Sensitive roots and path escapes are blocked.
- Heavy folders such as `.git`, `node_modules`, `dist`, `target`, caches, and virtualenvs are ignored.
- `.env`, private keys, binary files, and oversized files are skipped or reported as review-only.
- Secret-like values in excerpts and imported prompt text are redacted.
- Hooks/settings/scripts/skills are not installed or activated by the import flow.

## Recovery

- If a root disappears, the workspace remains available as a logical workspace and the UI shows the missing-root state.
- If source files change, use **rescan** before applying a reimport.
- Reimport replaces only the managed prompt block and preserves manual prompt text around it.
- If an imported agent ID already exists, Koda records a conflict in import history and leaves the existing agent untouched.
