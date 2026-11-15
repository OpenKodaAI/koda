# Upgrade procedure

Self-hosted koda upgrades follow a five-step pipeline that keeps the
operator in the loop. The pipeline is the same for single-host and
multi-supervisor deployments; cluster mode adds a drain step.

## Pre-flight (always)

1. **Read the changelog.** [`CHANGELOG.md`](../../CHANGELOG.md) has a
   section for each version since 1.0.18. Read every section between
   your installed version and the new one: schema migrations, removed
   settings and changed defaults are called out there.
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
- **A path rule also covers a search, grep or move of an ancestor.**
  `file_search`, `file_grep` and `file_move` act on everything below
  their path (a moved directory takes its contents along, and a move can
  create a directory's contents at its destination). For these tools a
  `deny`, `require_approval` or `allow_with_preview` path rule now also
  matches when its path lies below the call's path. So `file_grep` with
  its `path` set to the working directory, or `file_search` from `/`, is
  denied by a deny rule on a directory inside it, as `file_grep` without
  a `path` already was, and moving a directory that holds a gated path,
  or onto one, needs that rule's approval or preview. A rule path with a
  wildcard segment counts when the call's path is at, above or below the
  segments before the wildcard, and one that starts with `*` always
  counts. An `allow` path rule still has to cover the call's path
  itself.
- **A move counts as a directory move.** The rules cannot tell whether a
  move's source is a directory (the simulator has no filesystem, and in
  the worker the answer can change while an approval is pending), so
  both ends of every `file_move` count as directories. A single-file move
  or rename is therefore decided by a restrictive path rule below its
  source or destination, and by one that starts with `*`: with a deny
  rule for `*.pem`, `file_move` of `a.txt` to `b.txt` is denied too.
  Write a restrictive rule for a directory or a fixed path rather than a
  `*`-prefixed one where file moves must keep working.
- **A path rule covers a listing of the directory that holds it.**
  `file_list` and `/ls` show the direct entries of their path, each
  one's name, kind and size, and nothing below them. A `deny`,
  `require_approval` or `allow_with_preview` path rule now also matches
  a listing when its path can be one of those entries: a rule for
  `/srv/work/secrets` or `/srv/work/key.pem` decides a listing of
  `/srv/work`, and a rule for `/srv/work/a/b/secret` does not. A rule
  path with a wildcard segment counts when the listed directory is at or
  below the segments before the wildcard (`/srv/work/*.pem` decides a
  listing of `/srv/work`, `/srv/work/a/*.pem` does not), and one that
  starts with `*` decides every listing, since the rules do not know
  which entries a directory holds.
- **The worker resolves a file tool's relative paths before the rules
  see them.** In the worker, each file tool's `path`, `source` and
  `destination` reaches the rules as the absolute, symlink-resolved path
  it names under the agent's working directory (`~` expanded with the
  worker's `HOME`), and a file listing or search without a `path` is
  checked against the working directory, resolved (M1-E4-T13,
  `koda/services/tool_dispatcher.py::_file_tool_policy_params`). The
  relative paths the agent's own tool prompt teaches
  (`{"path": "src/main.py"}`, `{"path": "output.txt"}`, and `file_list`
  with `{}`) are therefore evaluated where they land. A value that is not
  a non-blank string, or cannot be resolved, reaches the rules as
  written, and the tool then refuses it. An operator file command's path
  is resolved the same way under the operator's work dir.
- **A path that cannot be placed fails closed.** The rule engine does
  not know a working directory or `HOME`, so a path that starts with
  `~`, a relative path such as `notes.txt` or `../secrets/key.pem`, and
  a file listing or search without a `path` count as matching every
  `deny`, `require_approval` and `allow_with_preview` path rule, and no
  `allow` path rule, wherever they reach the engine unresolved: in the
  worker that is only `agent_set_workdir`'s `path`, which is passed as
  written; in the simulator, which evaluates the params as you send
  them, it is every such path. The `fileops` grant's `allowed_paths`
  check sees the same paths, and no `allowed_paths` entry covers a path
  that cannot be placed, so in the simulator a `file_list`, `file_search`
  or `file_grep` without a `path` is outside every path-scoped grant,
  while the worker checks the working directory it reads. So for a
  relative or `~` file-tool path, and for a listing, search or grep
  without a `path`, the simulator can show a stricter decision than the
  worker makes, never a looser one. To see the worker's decision, send
  the absolute path the call resolves to.
- **A restrictive rule written through a symlinked directory applies to
  the resolved path.** The worker gives the rules a file tool's path
  symlink-resolved, so a rule for `/srv/app/config/secrets`, where
  `/srv/app` links to `/srv/releases/v42`, never saw the agent's calls
  under `/srv/releases/v42/config/secrets` and did not apply. A `deny`,
  `require_approval` or `allow_with_preview` rule's path is now also
  compared with its fixed part (the segments before the first wildcard)
  symlink-resolved. An `allow` rule's path is still compared as written,
  so an `allow` rule written through a symlink does not cover the
  resolved paths: write it with the resolved directory.
- **Rule path patterns are normalized.** `/srv//prod`, `/srv/./prod`,
  `/srv/x/../prod` and `/srv/prod/` now all mean `/srv/prod`, so such a
  rule matches the calls it names instead of none.
- **The simulator uses the agent's feature flags.** For an agent with no
  rules, the simulator filters its tool policy with the feature flags of
  the agent's worker, not with the control-plane process's own. It
  computes them as the worker does: from the environment the supervisor
  gives it, that is the agent's environment (for example the
  `shell_enabled` and `browser_enabled` settings), where an agent-scoped
  `<AGENT_ID>_<KEY>` entry comes first; then from the install's `.env`
  file, which fills only the settings that environment lacks. So a flag
  set in `.env` after the first bootstrap applies in the simulator as it
  does in the worker. The supervisor's own `INTER_AGENT_ENABLED`, when it
  sets one, wins over the agent's and the file's.
- **The supervisor's infrastructure settings win in every worker.** The
  supervisor copies its own infrastructure settings (database and object
  storage addresses, the sidecar gRPC targets, `STATE_ROOT_DIR`,
  `RUNTIME_EPHEMERAL_ROOT`, `INTER_AGENT_ENABLED` and the other keys in
  `koda/control_plane/supervisor.py::_SYSTEM_ENV_KEYS`) onto each worker
  as `<KEY>` and as `<AGENT_ID>_<KEY>`. It used to set only `<KEY>`, so an
  agent environment that still carried one of these settings, for
  example from an older install's `.env` imported at the first
  bootstrap, kept it in that worker, because the worker reads
  `<AGENT_ID>_<KEY>` first. A value the supervisor's environment does
  not set still comes from the agent's environment.

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
  `/cat it's.txt`, no longer fails before the check. Path rules now also
  see the path of `/file` and `/ls` (the work dir for `/ls` alone), which
  they used to skip, so a deny path rule keeps `/file` from sending a file
  it covers, as it keeps `/cat` from showing it, and `/ls` of a directory
  with a gated path among its direct entries is decided by that rule
  (see "A path rule covers a listing of the directory that holds it"
  above; a gated path deeper down does not decide `/ls`).
- **An `approve scope` grant covers only calls on the same paths.** A
  grant now records every path that path rules evaluate, both ends of a
  `file_move` included, so it no longer covers a move from the same
  source to another destination. Scope grants issued before the upgrade
  no longer match, and their calls ask for approval again.
- **Approval grants belong to one agent.** Migration `050_approval_tables`
  creates `pending_approvals` and `approval_grants` with BIGINT user and
  chat ids and DOUBLE PRECISION times; earlier releases created them on
  first use with INTEGER ids and REAL times, which it widens.
  A stored grant with a blank `agent_id` gets the agent that the approval
  request that issued it, its session or its chat names, when exactly one
  agent is named. A session naming `KODA` counts as naming none, because
  migration 027 set `KODA` on every session older than it. Every other such
  grant expires, with one
  `approval.grant_expired` audit event (scope `global`) each, and its call
  asks for approval again. No grant without an agent applies to any agent.
  A grant approved for a request that names no agent now belongs to the
  worker that issued it instead of agent `default`.
- **A grant's use is recorded before its action runs.** When Postgres does
  not record the use, the call or command does not run and asks for
  approval again. A use counts when the action starts, so an action that
  fails has used its approval. An approval's grants are stored before the
  approval completes: when Postgres does not store them, the approver gets
  a Telegram reply or an HTTP 503 from the dashboard, and the request stays
  open to approve again.
- **Approvals are kept in Postgres only.** Earlier releases wrote
  `approval_grants.json` and `pending_approvals.json` in `STATE_ROOT_DIR`
  when a Postgres write failed, and never read them back. On its first
  start, before it recovers tasks, each worker imports the files it finds
  there, once. The old release left a grant in the file after its last use
  or its revocation, so every imported grant is stored expired, with one
  `approval.grant_expired` audit event (reason
  `imported_from_retired_json`) each, and its calls ask for approval
  again. A grant keeps its `agent_id`, and one without an agent follows
  the rule above. Each file is then renamed `<name>.migrated` and kept,
  and the worker logs `approval_json_import_complete` with the rows it
  imported. A file that fails to import stays in place: the worker
  reports `approval_json_import_error` and tries again on its next start.
  A failed approval write is now logged (`approval_grants_write_failed`,
  `pending_approvals_write_failed`) and no file is written.
- **A pending approval ends when its worker restarts.** Its command, or the
  agent turn waiting on it, cannot be restored. On start, each worker deletes
  the pending approvals of its agent that its previous process left, with one
  `approval.pending_expired` audit event (reason `restart`) each. Pressing a
  button on one of them runs nothing and answers that the request expired and
  must be asked again; before, approving one failed with an error. Approval
  grants keep working across the restart. A worker loads only its own agent's
  grants, and leaves the rows of other agents, and rows with no agent, alone.

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

`migrate --check` looks at your database. CI does not: its migrations
gate (`.github/workflows/migrations-gate.yml`) checks the migrations
themselves, on pull requests that change them. It applies the previous
release's migrations and then this commit's to one schema, as an upgrade
does, installs this commit's migrations on an empty schema, and fails
when the two schemas differ. A change to the DDL of a migration that was
already released, instead of a new migration, therefore fails the gate:
upgraded installs would never run it. The gate also fails a migration
added since the previous release, or a statement in the DDL that startup
runs after the migrations on every install, that builds a plain index on
a table it lists as large (`scripts/migrations_gate.py`): a `CREATE INDEX`
without `CONCURRENTLY`, or an `ALTER TABLE` adding a `UNIQUE`, `PRIMARY
KEY` or `EXCLUDE` constraint, because the build would block writes to
that table during your upgrade. Such an index is built with `CREATE
INDEX CONCURRENTLY`, and a constraint then takes it over with `USING
INDEX`.

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

### Master key check on start

Before it serves anything, the control plane checks the master key against
the fingerprint Postgres records in `cp_master_key_fingerprint` (migration
`048_control_plane_master_key_fingerprint`). On the first start after an
upgrade from a release without that table, it checks that the key it finds,
or the previous key during a rotation, decrypts at least one of the newest
stored encrypted values. It then records the key's fingerprint (audit event
`security.master_key_fingerprint_recorded`, `reason=upgrade`); it re-encrypts
and deletes nothing. The app refuses to start, logging
`koda control plane refused to start:` with the fix, in three cases: the key
file is missing while encrypted secrets exist; on that first start, the key
decrypts none of them (releases before this check created a new key
whenever the file was missing); or, on later starts, the key differs from
the recorded one. See [backup-restore.md](backup-restore.md#master-key-recovery).

Releases from before this check ignore the table, so rolling back needs no
extra step. Keep the key file in place either way: those releases create a
new key when the file is missing.

### Scheduled jobs without an agent

Each agent worker materializes, claims, recovers and dispatches only its
own agent's scheduled jobs, through its own bot and under its own policy.
Its `/jobs` command, job tools and runtime API actions also act only on
that agent's jobs. The scheduler entry of its `/health` payload and its
`koda_scheduled_*` metrics count only that agent's jobs and runs.

A job created by a worker started without `--agent-id` (no `AGENT_ID`)
has no agent: its `scheduled_jobs.agent_id` is NULL, and only a worker
started the same way runs it. The supervisor always starts workers with
`--agent-id`. After a move from a standalone worker to supervised agents,
no worker runs these jobs and the dashboard lists them under no agent.
Each agent worker logs `scheduler_unowned_jobs_skipped` with their ids
when its dispatcher starts, and its `/health` scheduler entry reports
their number as `unowned_jobs`.

No migration assigns them, because nothing records which agent created
them. Assign each job to the agent that should run it, with `psql`
against the Koda database (for example
`docker compose exec postgres psql -U <user> -d <database>`), while no
worker without `--agent-id` runs.

First close the job's open runs (`queued`, `retrying` or `running`,
validation runs included). Each one carries the policy snapshot of the
worker that created it, and an agent blocks a run whose snapshot is not
its own. Left open, the first such run the agent claims ends `blocked`
("Scheduled run blocked because the job policy changed after
validation."), the job moves to `validation_pending` with no next run,
its other queued and retrying runs end `blocked`, and the agent's bot
tells the user the run was blocked. Close the runs, then assign the jobs,
in one transaction. The first statement closes each run as the scheduler
does when it cancels one: it sets the run's completion and update times,
and records a `run.cancelled` event that names its earlier status and the
reason, so the run history shows why the run ended.

```sql
BEGIN;
WITH open_runs AS (
    SELECT id, status FROM knowledge_v2.scheduled_job_runs
    WHERE scheduled_job_id IN (12, 15)
      AND status IN ('queued', 'retrying', 'running')
    FOR UPDATE
), stamp AS (
    SELECT to_char(now() AT TIME ZONE 'UTC',
                   'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"') AS at
), closed AS (
    UPDATE knowledge_v2.scheduled_job_runs AS run
    SET status = 'cancelled', lease_owner = NULL, lease_expires_at = NULL,
        next_attempt_at = NULL,
        completed_at = COALESCE(run.completed_at, stamp.at),
        updated_at = stamp.at,
        error_message = 'Closed before assigning the job to an agent.'
    FROM open_runs, stamp
    WHERE run.id = open_runs.id
    RETURNING run.id, run.scheduled_job_id, run.trace_id,
              open_runs.status AS status_from, stamp.at
)
INSERT INTO knowledge_v2.scheduled_job_events (
    scheduled_job_id, scheduled_run_id, trace_id, event_type, actor_type,
    source, status_from, status_to, reason, created_at
)
SELECT scheduled_job_id, id, trace_id, 'run.cancelled', 'operator',
       'upgrade', status_from, 'cancelled',
       'Closed before assigning the job to an agent.', at
FROM closed;
UPDATE knowledge_v2.scheduled_jobs
SET agent_id = 'AGENT_A'
WHERE agent_id IS NULL AND id IN (12, 15);
COMMIT;
```

Use your schema name if you changed `KNOWLEDGE_V2_POSTGRES_SCHEMA`. That
agent's next dispatch cycle runs each active job under its own policy, as
after an outage: from the job's next run time, it runs the occurrences
still inside the catch-up window. The occurrences of the closed runs do
not run. A job that was waiting for its validation stays
`validation_pending`. Validate it from that agent's bot with
`/jobs validate <id>`, then `/jobs activate <id>` once the validation
passes. Do the same for a job that you assigned with its runs still open
and that the agent moved to `validation_pending`.

## Step 2 (cluster) — blue/green drain

For a multi-supervisor deployment (`KODA_CLUSTER_MODE=cluster`):

```bash
# 1. Bring up the new version's supervisor pods alongside the old.
docker compose up -d --scale supervisor=4 supervisor   # 2 old + 2 new

# 2. Drain the old supervisors. Each releases its claims; the new
#    supervisors pick them up via the SELECT FOR UPDATE SKIP LOCKED
#    path. In-flight messages are preserved by the bot-gateway's
#    durable queue. Drain needs an operator bearer token, such as the
#    first CONTROL_PLANE_API_TOKEN of the list that the control plane
#    accepts (placeholders and empty items skipped). curl reads the
#    header on stdin, so the token stays out of ps and the history.
token=$(printf '%s\n' "$CONTROL_PLANE_API_TOKEN" | tr ',' '\n' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | grep -iv -e '^$' -e '^replace-with-' | head -n 1)
for old_pod in supervisor-old-1 supervisor-old-2; do
    printf 'Authorization: Bearer %s\n' "$token" \
        | curl -fs -X POST -H @- http://${old_pod}:8090/cluster/drain
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

Then confirm that both images carry the pinned provider CLIs (see
[Provider CLI versions](#provider-cli-versions)):

```bash
docker compose exec -T app python -m koda.services.provider_cli_contract
docker compose exec -T runtime-kernel python -m koda.services.provider_cli_contract
```

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
release that introduces the column) keeps rollback safe. If the
release's section in [`CHANGELOG.md`](../../CHANGELOG.md) calls out a
destructive migration, follow the rollback steps it gives.

## Provider CLI versions

The `app` and `runtime-kernel` images install Claude Code, Codex and
Gemini CLI from one lockfile, `packages/provider-clis/package-lock.json`,
at the exact versions listed in `packages/provider-clis/package.json`.
Nothing in a running image can install or update a package: npm and
npx are not in the image, and Gemini no longer falls back to
`npx @google/gemini-cli` when its binary is missing.

Before a provider's first turn, Koda checks the installed binary
against its contract in `koda/services/provider_cli_contract.py`: the
version must equal the pin, every option Koda passes must have its own
entry in `--help` with each value Koda passes listed in that entry,
and options that `--help` hides must be accepted by the parser. Each
runner repeats the check once its cached result is 30 seconds old, so
a binary replaced in place is probed again. If any check fails, the
provider is unavailable for turns and its health entry shows the
reason:

| Reason | Meaning |
|---|---|
| `unavailable:unverified_cli_version` | The installed CLI is not the pinned version, or it does not accept an option Koda passes. |
| `unavailable:cli_not_installed` | The CLI is not on `PATH`. |
| `unavailable:cli_probe_failed` | `--version` or `--help` did not finish, so nothing could be verified. |

Koda never runs a turn on an unverified CLI. Rebuild or pull the
images to get the pinned versions. Native (non-Docker) runs must
install exactly the versions in `packages/provider-clis/package.json`.
The `codex_bin` and `gemini_bin` system settings (`CODEX_BIN`,
`GEMINI_BIN`) are each the path of one executable, the pinned `codex`
or `gemini` binary. A command line such as `npx -y @google/gemini-cli`
or `codex --model o3` is not a valid value: Koda reads the whole value
as one path, finds no such executable, and treats the CLI as not
installed.

`python -m koda.services.provider_cli_contract` prints the check for
every provider as JSON and exits non-zero on any mismatch. It runs
only `--version`, `--help` and a parser check, with no model call and
no credentials. It starts each CLI the way the runners do: with the
same command and the same allowlisted environment, so database,
object-storage and other container secrets never reach the CLIs.

### Changing a pinned version

1. Change the version in `packages/provider-clis/package.json`, then
   run `npm install --package-lock-only` in that directory.
2. Update `pinned_version` and the option tokens in
   `koda/services/provider_cli_contract.py`, checking each token
   against the new version's real `--help` output. For Claude Code,
   also refresh the recorded outputs in `tests/fixtures/provider_cli/`.
3. Merge only when the `provider-cli-contract` CI job passes. It
   installs the lockfile the way the images do and probes the
   binaries against the contract.

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
