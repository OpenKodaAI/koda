# Workspace Directory Config Import

Koda workspaces can optionally point at a physical source root. The root is used as read-only source context for workspace configuration imports and as the default `base_work_dir` for linked agent tasks. Mutable task execution still happens in the runtime workspace, worktree, or copy selected by the runtime provisioner.

## Contract

- A logical workspace remains valid with `root_path: null`.
- A rooted workspace stores `root_path`, `root_kind`, `scan_status`, `last_scanned_at`, `scan_hash`, `config_sources_json`, and `import_history_json` on `cp_workspaces`.
- Scans emit `workspace_config_scan.v1`.
- The scanner validates the root with `realpath`, blocks sensitive directories, ignores heavy folders, skips `.env` and key material, avoids symlink escapes, caps depth/entries/bytes, redacts secret-like values, and never executes commands.
- Imports require explicit `selectedSourceIds`.
- Prompt imports are written into a replaceable block delimited by:

```html
<!-- koda:workspace-import:start ... -->
<!-- koda:workspace-import:end -->
```

Manual prompt text outside the block is preserved on reimport.

## Source Handling

Low-risk instruction and rule files can be appended to the workspace prompt block. Claude/Codex subagents become paused draft agents with `metadata.imported_from`. MCP files become disabled review-required catalog candidates when they have a safe static shape. Hooks, scripts, skills, settings with execution behavior, local memory, and identity/personality files are findings only until an operator reviews them through their owning feature.

Detected source records include `source_id`, `tool`, `kind`, `relative_path`, `scope`, `name`, `description`, `confidence`, `risk`, `status`, `import_action`, `warnings`, `metadata`, and `content_excerpt`.

## Runtime Semantics

When a linked agent starts work, the queue manager resolves the source directory in this order: existing runtime workdir, explicit schedule/child-run/retry workdir, workspace root, session/user workdir, then `DEFAULT_WORK_DIR`.

Runtime responses expose:

- `source_root_path`: the safe source root alias for `base_work_dir`.
- `workspace_path`: the effective task workspace where mutable execution happens.

The `agent_set_workdir` tool is additionally constrained to the active runtime workspace and source workspace root. A path outside those roots is blocked even if generic workdir validation would accept it.
