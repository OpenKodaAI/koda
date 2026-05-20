# Skills And Plugin Package Runbook

This runbook covers Phase 4 install, uninstall, rollback, and operations for
`koda_skill.v1` packages.

## Operator Flow

1. Scan a local package path.
2. Review findings, requested permissions, exported skills, and exported tools.
3. Install only when the scan decision is `allow` or an explicit review path is
   accepted by policy.
4. Verify installed package state in the agent Skills tab.
5. Use the Skills tab registry view to inspect provenance, trust summary,
   eval status, rollback availability, and RunGraph lifecycle evidence.
6. Run offline skill evals from the package row when new evidence is needed.
7. Uninstall or rollback from the installed packages list when needed.

Control-plane endpoints:

- `POST /api/control-plane/agents/{agent_id}/skills/packages/scan`
- `POST /api/control-plane/agents/{agent_id}/skills/packages/install`
- `GET /api/control-plane/agents/{agent_id}/skills/packages`
- `GET /api/control-plane/agents/{agent_id}/skills/registry`
- `POST /api/control-plane/agents/{agent_id}/skills/packages/{package_id}/evals/run`
- `DELETE /api/control-plane/agents/{agent_id}/skills/packages/{package_id}`
- `POST /api/control-plane/agents/{agent_id}/skills/packages/{package_id}/rollback`

## Allowlists And Recommendation

P3 is strict by default:

- Add custom/package skill IDs to `skill_policy.enabled_skills`; no allowlist
  means no skill is available.
- Add package IDs to `skill_policy.enabled_skill_packages`; package skills and
  tools stay hidden without it.
- Add package tool IDs to `tool_policy.allowed_tool_ids`; package allowlist does
  not expose tools by itself.
- Direct dynamic handler calls are denied unless both gates match the runtime
  agent spec.

Installed packages remain `unreviewed` until eval evidence exists. Run package
evals with the eval endpoint above or install a package that already declares
offline `eval_case.v1` metadata. Required eval failures keep the package at
`eval_failed` and block `recommended`. `review_required` packages also require
preserved operator review evidence before they can become `recommended`.

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

Install, eval run, and rollback store redacted `runtime_event` RunGraph nodes
in package lock/event payloads. These nodes include package IDs, version,
recommendation status, hashes and rollback refs, but not raw package content.

## Rollback

Rollback should:

- deactivate current package tools and skills
- restore the previous lock payload when present
- emit `skill_package.rollback`
- store rollback RunGraph evidence in the restored lock
- leave custom skills untouched

If no previous lock exists, return `skill.rollback_unavailable` and keep the
current package unchanged.

## Troubleshooting

- Scanner denies dangerous imports, install scripts, path escapes, secrets,
  unknown permissions, high-risk tool classes, and tool id conflicts.
- `PLUGIN_SYSTEM_ENABLED=false` blocks dynamic handler execution even when the
  package is installed.
- If a tool appears installed but unavailable, inspect ToolRegistry metadata,
  package scan findings, `skill_policy.enabled_skill_packages`,
  `tool_policy.allowed_tool_ids`, and runtime feature flags.
