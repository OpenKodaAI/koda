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

P3 adds strict per-agent allowlists:

- `skill_policy.enabled_skills` is the canonical allowlist for custom and
  package skill IDs. If it is absent or empty, no skill is injected into the
  prompt and `/skill` / `request_skill` expose no skills.
- `skill_policy.enabled_skill_packages` is the package allowlist. Package
  skills and tools require this package ID to be present.
- Package tools also require `tool_policy.allowed_tool_ids`; the package
  allowlist alone never exposes a tool to the model.
- Direct dispatcher calls to dynamic package handlers are fail-closed by the
  same two gates, so a tool call cannot bypass prompt/native schema filtering.
- Squad capability summaries include allowed skill IDs/package IDs as metadata
  for routing, without raw skill content.

## Skill Evals And Recommendation

Package manifests may declare eval metadata under top-level `evals` or
`tests.evals`. These entries are normalized into `skill_eval.v1` records using
existing `eval_case.v1` offline evaluation. Evals never call providers.

`skill_lock.v1` now carries additive fields:

- `skill_evals`
- `recommendation_status`: `unreviewed`, `recommended`, `eval_failed`, or
  `blocked`
- `eval_summary`
- `trust_summary`

Install without eval evidence remains `unreviewed`. A package becomes
`recommended` only when scanner state is allow/review-accepted and all required
skill evals pass. Legacy or imported `review_required` locks without preserved
operator review remain `blocked`, even if eval results are passing.

The local registry endpoint returns `skill_registry.v1`:

- `GET /api/control-plane/agents/{agent_id}/skills/registry`
- `POST /api/control-plane/agents/{agent_id}/skills/packages/{package_id}/evals/run`

The Skills UI consumes this registry view for provenance, trust, eval status,
rollback availability, and the latest redacted RunGraph lifecycle node.

## Rollback

Rollback restores the previous lock payload for the package when available.
If the database tables are unavailable, the runtime falls back to a JSON lock
store. Rollback does not mutate legacy `custom_skills`. Install, eval run and
rollback lifecycle actions store a redacted `runtime_event` RunGraph node in
the lock/event payload so operators can inspect evidence without raw package
content.

## Improvement Proposals

Repeated workflow, eval, or manual evidence may create a draft
`improvement_proposal.v1` with `proposal_type="skill"`. The proposal records
evidence, a redacted diff preview, validation plan, and rollback plan, but it
does not install or enable any skill without approval and validation.
