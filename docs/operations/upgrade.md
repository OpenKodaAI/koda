# Upgrade procedure

Self-hosted koda upgrades follow a five-step pipeline that keeps the
operator in the loop. The pipeline is the same for single-host and
multi-supervisor deployments; cluster mode adds a drain step.

## Pre-flight (always)

1. **Read the changelog.** Schema migrations and removed env vars
   are called out in `docs/release-notes/<version>.md`.
2. **Take a backup.** See [backup-restore.md](backup-restore.md).
3. **Pull the new image** but do not restart yet.

   ```bash
   docker compose pull
   ```

### Execution-policy rules

Agent execution-policy rules (`execution_policy.rules`) now follow the
worker's rule engine everywhere: in publish validation, in the
control-plane simulator (`POST /api/control-plane/agents/{agent_id}/execution-policy/evaluate`)
and in the worker. Workers do not receive these rules yet, so this
release does not change what agents can run. It does change how
existing rules are validated and simulated:

- **Publish rejects rules the engine cannot evaluate.** A `^regex`
  pattern, an unknown selector key (for example a misspelt `tool_ids`),
  an empty selector value, a mapping value, a value other than true or
  false on a boolean selector (for example `private_network: "ture"`),
  a `path` pattern that is neither absolute nor starts with `*` (for
  example `~/prod` or `srv/prod`) or has `..` after a wildcard segment
  (for example `/srv/*/../prod`), a rule with no selectors or an unknown
  `decision` or legacy `action` (for example `dney`), and two rules with
  the same name are now validation errors. A rule with no selectors or an
  unknown decision used to disappear silently; publish now validates the
  policy as stored and reports it. An agent with any of these cannot be
  published, for any change, until the rule is fixed. Saving a changed
  policy through the agent spec or the execution-policy route is refused
  with the same errors; saving other changes beside an unchanged policy
  still works.
  Each error names the rule and the selector, for example
  `execution_policy.rules[0].match.tool_ids is not a supported selector`.
  Rewrite a regex as an fnmatch pattern: `^mcp_.*__delete_.*$` becomes
  `mcp_*__delete_*`.
- **The most restrictive matching rule wins.** The simulator used to
  take the first match by priority. Now a matching `deny` beats every
  `require_approval`, `allow_with_preview` and `allow` rule, whatever
  their priority.
- **An `effect_tags` list needs every listed tag.** The simulator used to
  match a rule when any listed tag was present. Now, as in the worker,
  every listed tag must be present, so a deny rule that lists several
  tags matches fewer calls. To deny a call that has any of the tags,
  write one rule per tag.
- **A `path` selector covers the path and everything below it.** The
  simulator used to match only that exact path. Path rules are now
  evaluated against these paths, as the tool receives them: a file
  tool's `path`, `source` and `destination` (both ends of a
  `file_move`), the working directory for `file_list`, `file_search`
  and `file_grep` called without a `path`, the `path` of
  `agent_set_workdir`, and the file an operator file command acts on
  (see below). No other param is evaluated, even one that names a
  path: an MCP tool's params, `browser_upload`'s `file_path`,
  `plugin_install`'s `path`, the `path` of `git_diff` and `git_log`,
  and `job_create`'s `work_dir`, nor anything a shell or git command
  touches. A path rule therefore does not keep those tools out of a
  directory (owner: AG-12).
  An absolute path is evaluated once for each of its spellings
  (normalized, with `.`, `..` and repeated `/` resolved, and as written;
  each with and without case), and the most restrictive outcome wins. A
  `deny`, `require_approval` or `allow_with_preview` path rule therefore
  also covers `..`, `//` and other-case spellings of its path, and a
  call such as `/srv/work/link/../other/key` that passes through its
  directory `/srv/work/link` (when that directory is a symlink, the tool
  follows the link before the `..`). An `allow` path rule covers a call
  only when each spelling of each of the call's paths is inside it, with
  case. When two rules with the winning decision match different
  spellings, the higher priority (then the lower name) decides, as for
  any other tie.
- **A path that is not absolute fails closed.** The worker's tools
  expand `~` and resolve a relative path against the agent's working
  directory, which the rule engine does not know. So a path that starts
  with `~`, a relative path such as `notes.txt` or `../secrets/key.pem`,
  and a file listing or search of the working directory without a
  `path` now count as matching every `deny`, `require_approval` and
  `allow_with_preview` path rule, and no `allow` path rule. A call that
  such a rule's other selectors match and that gives a relative or `~`
  path is therefore denied, or needs approval or a preview, even when it
  would land outside that rule's directory. The agent's own tool prompt
  teaches relative paths (`{"path": "src/main.py"}`,
  `{"path": "output.txt"}`, and `file_list` with `{}`), so once rules
  reach workers, one restrictive path rule beside an allow for the file
  tools gates nearly every file call an agent makes, until relative
  paths are resolved under the work dir (M1-E4-T13). Check such a rule
  with the simulator before you rely on it.
- **Rule path patterns are normalized.** `/srv//prod`, `/srv/./prod`,
  `/srv/x/../prod` and `/srv/prod/` now all mean `/srv/prod`, so such a
  rule matches the calls it names instead of none.
- **The simulator uses the agent's feature flags.** For an agent with no
  rules, the simulator filters its tool policy with the feature flags of
  the agent's worker, not with the control-plane process's own. It
  computes them as the worker does: from the environment the supervisor
  gives it, that is the agent's environment (for example the
  `shell_enabled` and `browser_enabled` settings), where an agent-scoped
  `<AGENT_ID>_<KEY>` entry comes first, and the supervisor's own
  `INTER_AGENT_ENABLED` only when the agent's environment does not set
  it; then from the install's `.env` file, which fills only the settings
  that environment lacks. So a flag set in `.env` after the first
  bootstrap applies in the simulator as it does in the worker.

After the upgrade, send the calls you care about to the simulator to see
what each agent's rules now decide.

### Operator file commands and approval grants

These changes apply with or without rules:

- **A file command is checked against the file it acts on.** `/rm`,
  `/mkdir` and `/cat` act on their whole argument, spaces included, and
  `/write` and `/edit` on their first argument. The execution policy and
  the `fileops` grant's `allowed_paths` now see that path, resolved
  under the work dir as the command resolves it. They used to see the
  first shell word, so `/rm x /../secrets/key` was checked as `x` while
  it deleted `secrets/key`. A path with a quote in it, such as
  `/cat it's.txt`, no longer fails before the check.
- **An `approve scope` grant covers only calls on the same paths.** A
  grant now records every path that path rules evaluate, both ends of a
  `file_move` included, so it no longer covers a move from the same
  source to another destination. Scope grants issued before the upgrade
  no longer match, and their calls ask for approval again.

## Step 1 — schema migration gate

```bash
docker compose run --rm app python -m koda migrate --check
```

Exit codes:
- `0` — DB is in sync with the new code's migrations. Safe to upgrade.
- `3` — pending migrations. Apply them BEFORE rolling new code.
- `1` — infra error (DSN unreachable, asyncpg missing). Fix and retry.

If exit `3`, apply migrations first:

```bash
docker compose run --rm app python -m koda migrate
docker compose run --rm app python -m koda migrate --check  # must now exit 0
```

The `migrate --check` step is also enforced in CI via
`.github/workflows/migrations-gate.yml` so a PR that adds a migration
without bumping the schema_migrations expectation cannot merge.

## Step 2 — single-host restart

For a single-host docker-compose deployment:

```bash
docker compose up -d --no-deps app web    # rolls services with the new image
docker compose restart supervisor          # if you run the supervisor separately
```

Wait for `/health` to report `healthy`:

```bash
curl -fs http://127.0.0.1:8090/health | jq .status
```

## Step 2 (cluster) — blue/green drain

For a multi-supervisor deployment (`KODA_CLUSTER_MODE=cluster`):

```bash
# 1. Bring up the new version's supervisor pods alongside the old.
docker compose up -d --scale supervisor=4 supervisor   # 2 old + 2 new

# 2. Drain the old supervisors. Each releases its claims; the new
#    supervisors pick them up via the SELECT FOR UPDATE SKIP LOCKED
#    path. In-flight messages are preserved by the bot-gateway's
#    durable queue.
for old_pod in supervisor-old-1 supervisor-old-2; do
    curl -fs -X POST http://${old_pod}:8090/cluster/drain
done

# 3. Wait for owned_count → 0 on the old pods.
watch -n 2 'curl -fs http://supervisor-old-1:8090/cluster/status | jq .owned_count'

# 4. Stop the old pods.
docker compose stop supervisor-old-1 supervisor-old-2
```

The drain HTTP endpoints are documented in
[cluster-mode.md](cluster-mode.md).

## Step 3 — doctor verification

```bash
docker compose exec app python3 scripts/doctor.py --strict
```

Strict mode adds the [hardening](hardening.md) checklist to the
default doctor checks. Any failure aborts the upgrade.

## Step 4 — smoke a representative request

Send a known query through your usual interface (Telegram bot,
control-plane UI, API) and verify the response shape. If you have
synthetic users wired into the [observability](observability.md)
stack, the smoke test is just a prometheus alert read: query
processing rate at baseline within 60s.

## Step 5 — rollback (only if 1-4 fails)

```bash
# 1. Stop the new image
docker compose stop app web

# 2. Restore Postgres from pre-upgrade dump
#    (see backup-restore.md)
docker compose exec -T postgres pg_restore --clean ... < pre-upgrade.dump

# 3. Pin the previous image tag in docker-compose.yml or the env file
echo "KODA_IMAGE_TAG=v1.0.10" >> .env

# 4. Bring the old version back up
docker compose up -d
```

**Important:** rolling back a migration is a one-way door for any
new column / table the new code wrote rows into. Forward-only
migration design (additive ALTERs, never DROP COLUMN in the same
release that introduces the column) keeps rollback safe. If a
release notes called out a destructive migration, follow the
release-specific rollback in `docs/release-notes/<version>.md`.

## Tracking upgrade history

Every successful upgrade should leave an audit row:

```bash
docker compose exec app python3 -c "
from koda.control_plane.audit import record_audit_event
record_audit_event('global', event_type='operator.upgrade_completed', \
    details={'from': 'v1.0.10', 'to': 'v1.0.11'})
"
```

Future-you running an incident review will be glad you did.
