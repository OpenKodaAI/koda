# KodaSkill And Plugin SDK

Phase 4 introduces `koda_skill.v1`, the local-first package contract for
skills and plugin tools. It extends the current agent-scoped custom skills
without replacing them.

## Manifest

Packages use `koda-skill.yaml` as the primary manifest. `plugin.yaml` remains a
legacy compatibility input and is normalized into the same contract before
scan or install.

Required fields:

- `schema_version`: `koda_skill.v1`
- `id`, `name`, `version`, `description`, `author`
- `skills`: prompt skills to merge into the agent runtime registry
- `tools`: optional plugin tools exported into ToolRegistry
- `permissions`: requested filesystem, network, secrets, shell, MCP, and
  package permissions
- `docs`: optional README, changelog, and support references

Skill entries map to the runtime `SkillDefinition` shape:

- `id`, `name`, `instruction`, `content_path`
- `aliases`, `tags`, `triggers`, `requires`, `conflicts`
- `output_format_enforcement`, `max_token_budget`

Tool entries map to `tool-definition.v1`:

- `id`, `title`, `category`, `description`, `args_schema`, `handler`
- `access_level`, `effect_tags`, `idempotency`, `risk_class`
- `approval_default`, `timeout_seconds`

## Scan And Lock Contracts

`skill_scan.v1` is produced before install and is safe to show in UI:

- `decision`: `allow`, `review_required`, or `deny`
- `severity`: `info`, `warning`, `error`, or `critical`
- `findings`, `permissions_requested`, `risk_classes`, `redactions`
- `package_hash`, `file_hashes`, `scanner_version`

`skill_lock.v1` records the installed state:

- package id, version, source, path, hash, installed agent
- installed skills and tools
- scan summary, installed timestamp
- previous revision and rollback reference when available

## Runtime Integration

Installed package skills are merged with existing `custom_skills` at runtime.
Custom JSON remains the first compatibility layer and is not rewritten by
package install. Package tools enter the ToolRegistry with `source` set to
`skill_package` and continue through dispatcher, ExecutionPolicy, approvals,
audit, and RunGraph paths.

Dynamic Python handlers remain opt-in. If `PLUGIN_SYSTEM_ENABLED=false`, plugin
tools are visible as installed metadata but cannot execute.

## Rollback

Rollback restores the previous lock payload for the package when available.
If the database tables are unavailable, the runtime falls back to a JSON lock
store. Rollback does not mutate legacy `custom_skills`.
