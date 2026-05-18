# Skills And Plugin Package Runbook

This runbook covers Phase 4 install, uninstall, rollback, and operations for
`koda_skill.v1` packages.

## Operator Flow

1. Scan a local package path.
2. Review findings, requested permissions, exported skills, and exported tools.
3. Install only when the scan decision is `allow` or an explicit review path is
   accepted by policy.
4. Verify installed package state in the agent Skills tab.
5. Uninstall or rollback from the installed packages list when needed.

Control-plane endpoints:

- `POST /api/control-plane/agents/{agent_id}/skills/packages/scan`
- `POST /api/control-plane/agents/{agent_id}/skills/packages/install`
- `GET /api/control-plane/agents/{agent_id}/skills/packages`
- `DELETE /api/control-plane/agents/{agent_id}/skills/packages/{package_id}`
- `POST /api/control-plane/agents/{agent_id}/skills/packages/{package_id}/rollback`

## Error Envelope

Skill package operations use the shared operational envelope. Common codes:

- `skill.validation_failed`
- `skill.scan_denied`
- `skill.policy_denied`
- `skill.tool_conflict`
- `skill.rollback_unavailable`

## Persistence

Phase 4 uses additive tables:

- `skill_packages`: current lock per agent/package.
- `skill_package_events`: scan, install, uninstall, rollback, and deny audit
  trail.

If these tables are unavailable, the fallback JSON lock store preserves local
install state and rollback metadata for self-hosted recovery.

## Rollback

Rollback should:

- deactivate current package tools and skills
- restore the previous lock payload when present
- emit `skill_package.rollback`
- leave custom skills untouched

If no previous lock exists, return `skill.rollback_unavailable` and keep the
current package unchanged.

## Troubleshooting

- Scanner denies dangerous imports, install scripts, path escapes, secrets,
  unknown permissions, high-risk tool classes, and tool id conflicts.
- `PLUGIN_SYSTEM_ENABLED=false` blocks dynamic handler execution even when the
  package is installed.
- If a tool appears installed but unavailable, inspect ToolRegistry metadata,
  package scan findings, and runtime feature flags.
