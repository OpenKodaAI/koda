# ADR-002 (detailed design): Agent-native tool governance and provider confinement

| Field | Value |
|---|---|
| Status | **Accepted** (Option C, operator, 2026-11-14; Q-4, [DECISIONS.md](../DECISIONS.md) ADR-002). **Revision 3** (2026-11-14) answers the round-2 SEC and REV reviews and waits for their round-3 reviews. The operator questions in §9.1 need MISSION §13 sign-off before the tasks they name go live. |
| Date | 2026-11-14 (revisions 1, 2 and 3) |
| Owner | SEC (ARCH). Review: SEC and REV (MASTER_PLAN M1-E2-T1). |
| Summary entry | [DECISIONS.md ADR-002](../DECISIONS.md#adr-002--agent-native-tool-governance-option-c) |
| Relation to other ADRs | **Implements** ADR-009 for the governed path (§2.9: D-011, D-012). **Amended by** ADR-039, which records AG-06's single fnmatch engine as the amendment of ADR-008 step 1. **Clarifies** ADR-025 (the control plane resolves secret references). **Supersedes** the relocation step of ADR-026 (the key stays where it is; its volume becomes app-only). **Depends on** ADR-010, ADR-011 and ADR-035 (M1-E6-T1). |
| Plan items | MASTER_PLAN M1-E2-T2, T3 and T4 are carried out by the AG items mapped in §7.1. M1-E2-T5 (scoped DB role) is unchanged. M1-E4-T9 is carried by AG-06 and closes with AG-09 (ADR-039). |

**Evidence tags.** `[V]` means read or run during this design, with the citation or the command given. `[I]` means inferred; the task named alongside it supplies the proof. File references are relative to the repository root, at commit dfa596c (this branch changes only documents). Pinned CLI evidence names the package and the command. Claude's help output is the fixture `tests/fixtures/provider_cli/claude-2.1.325-help.txt`; Gemini bundle references are to files in the `bundle/` directory of `@google/gemini-cli@0.68.0`. Every CLI ran with an empty scratch HOME and no credentials, and no model was called. The Landlock probes used a helper that applies `no_new_privs` and a Landlock ruleset (ABI 7) whose only rule allows every filesystem right on `/`, then execs the probe.

---

## Revision 3 log

Each row names what changed and the round-2 finding it answers. Round-2 findings are numbered in review order: `S2-n` for SEC, `R2-n` for REV (`S2-0` and `R2-0` are each review's done-when item 5, which only the round-3 reviews can meet).

| # | Change | Answers |
|---|---|---|
| 1 | Codex compile rule rewritten (§2.3.3). Codex's inner sandboxes cannot start inside any Landlock domain (`[V]`: `bwrap: Failed to make / slave: Operation not permitted`), so an inner sandbox mode is selected only when the probe `IP` passed **inside the same confinement profile the spawn uses**. Under L2 (the defaults `strict` and `filesystem`) Codex therefore has `none` or `workspace_exec` (`danger-full-access`, confined by L2). Option (i) of S2-2, recorded in §1.2, O-8 and OQ-6. | S2-2, R2-5 |
| 2 | Codex `read_only` clamps to `none` in every mode on 0.169.0: under L2 the inner sandbox cannot start, and under `off` its read-only sandbox reads every file the uid can read (`[V]`). Codex at `none` runs `--sandbox read-only --disable shell_tool`, proven offline with `codex debug prompt-input`. The notice, the matrix, the migration banner and the escalation modal say so. | S2-2, R2-5, R2-13, S2-6 |
| 3 | Codex reviewed feature set for 0.169.0 (§2.3.3): 32 default-on features disabled at every level, `agents.enabled=false`, skills off (`skills.include_instructions=false`, `skills.bundled.enabled=false`), HOME set to the Codex provider home. A-K-02 fails on any enabled feature outside the reviewed list; A-K-04 is the offline prompt-input probe. | S2-8, R2-13 |
| 4 | Codex `workspace-write` rows add `exclude_slash_tmp=true`, `exclude_tmpdir_env_var=true` and `writable_roots=[<task tmp>]` (`[V]`: `/tmp`, `$TMPDIR` and `$CODEX_HOME` writes refused, the workspace and the task tmp writable). Asserted in A-X-02 and A-X-03. | S2-5, R2-8 |
| 5 | Gemini no longer uses a system settings file: 0.68.0 skips it unless it and every ancestor are root-owned (`[V]`), and it ignores `admin.*` from any file. Settings go into the Koda-written **user** settings of the rebuilt per-agent home; `security.disableYoloMode` replaces `admin.secureModeEnabled` (`[V]`). A settings warning fails the spawn; an offline load probe proves the file is read (A-K-05). | R2-3, R2-1, R2-2, R2-4 |
| 6 | Gemini runs with cwd set to an empty, read-only, Koda-owned directory inside its provider home, the workspace passed as `--include-directories=<workspace>`, and trust from `GEMINI_CLI_TRUST_WORKSPACE=true` (not `--skip-trust`, which trusts only after the first settings load, `[V]`). Workspace `.gemini/settings.json` and `.gemini/.env` are never read (`[V]`). The env pins the variables a planted `.env` could set (`[V]`: a pinned value is not overridden). New canaries. | S2-3, S2-1, R2-3 |
| 7 | GEMINI.md: 0.68.0 has no switch (`context.fileName` unions with the default; JIT discovery appends GEMINI.md files found on the path of a file a tool reads). With the workspace out of cwd it is not loaded at start, but R-7 applies to Gemini whatever OQ-3(b) decides. OQ-3, the notice and A-G-02 corrected. | S2-1, S2-3, R2-4 |
| 8 | Non-operator publishes (chat toggles, `/provider`, `/model`, supervisor reconcile, bootstrap, snapshot fallback) never publish the draft: they publish the last published snapshot plus their own typed change; a system first publish uses the draft with the secure-default execution and tool policies. §5.1.10 test. | S2-4 |
| 9 | Option (b) of R2-7: the worker reads the model policy only from the published snapshot. `/provider`, `/model` and functional defaults publish their own change as `telegram_user`, refused on escalation (the change waits in the dashboard). S10 becomes an assertion that fires on a CLI bump or a bug. A-P-04 is a publish test; OQ-2 reworded. | R2-7 |
| 10 | The server-side migration moves into AG-21 (per agent, `governance_migration_pending`); AG-30 keeps the banner and UI. Step 2 reads "a version without a governance block". AG-11 re-signs unsigned versions with the same primitive. | R2-6 |
| 11 | One actor shape `{kind, id}` with one enum (`operator`, `system`, `system:migration`, `system:import`, `telegram_user`) in the governance block, the gate and the event. | R2-14 |
| 12 | `/tmp`: internal calls run at `none` on every provider with a fresh, empty per-task work dir and TMPDIR; S10 applies to them; Koda's MCP env files leave the system temp dir; the native `RUNTIME_EPHEMERAL_ROOT` and compose `RUNTIME_KERNEL_ROOT` defaults leave `/tmp`; L2 refuses a shared directory as a workspace grant. A-P-01 asserts each internal call site's work dir and provider. | S2-5 |
| 13 | New residual R-8 (under `off`, class M reads every file the uid can read), in the notice and the red `off` banner. | S2-6, R2-8 |
| 14 | D-012 boundary restated (§2.9.2): the Telegram relay is a resolution the worker asserts; the grant MAC stops direct DSN inserts only once AG-17 and AG-19 put the signing key out of workers' reach (R-4, R-5); the broker token is what keeps a prompt-injected model out (D12-14). Consume becomes `POST /internal/approvals/consume` with an optional request id, and an existing scope grant is consumed before any request or card (D12-13). M3-E3-T2 deps add AG-17 and M1-E6-T3. | S2-7, R2-9, R2-10 |
| 15 | Every git process Koda spawns runs hardened and refuses a repository config key outside an allowlist; governed file tools refuse writes under `.git/` (D11-13, D11-14). | S2-9 |
| 16 | `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` are no longer read but are not cleared; AG-32 deletes them one release later (OQ-7). "All migrations are additive" is now true. | R2-11 |
| 17 | Dependencies: M1-E4-T9 = AG-06 plus AG-09, with AG-09 a close condition, not a start dependency; AG-12 moves to M1-E2-T2, so M1-E2-T4 (and M1-E6-T1 behind it) no longer waits for M1-E4-T13; AG-23 to AG-25 depend on AG-13a. ADR-039's "AG-10" is listed for the orchestrator (§9.3). | R2-12 |
| 18 | The rollback text says that rolling back restores the ungoverned provider modes and the previous volume layout. | S2-10 |
| 19 | Smaller design (MISSION §12): no Gemini system file and no per-task settings path; Gemini `none` is `tools.core=[]` (`[V]` in code), so S7 is `none` on every provider and no internal call needs a shell; the Codex probe is needed only for inner sandbox modes; S9 clamps to the highest class S level instead of refusing the provider. | Task brief |

## Revision 2 log

Kept as history (round-1 findings `SEC-n`, `REV-n`; done-when items `DW-n`). Rows 7, 10, 15 and 24 are superseded by revision 3 rows 1 to 7 and 12.

| # | Change | Answers |
|---|---|---|
| 1 | New §2.3: one row per provider mode. Every Claude permission mode (`acceptEdits`, `auto`, `bypassPermissions`, `default`/`manual`, `dontAsk`, `plan`), every Codex `sandbox_mode` × `approval_policy` pair (16 rows for the 15 pairs, because `workspace-write` splits on network, plus the bypass and auto-review flags), every Gemini approval mode (`default`, `auto_edit`, `yolo`, `plan`, and the `--yolo` alias). Each row names the Koda policy state (S1 to S10, §2.2.4) that selects it and the argv it produces. | DW-1; SEC done-when; REV done-when |
| 2 | §2.2.2: JSON Schema of the per-agent field, the derived governance block written at publish, and the error format. §2.6.1: the `agent.provider_builtin_tools_changed` audit event, written in the publish transaction. | DW-2; REV done-when (no schema, no event name, `record_audit_event` swallows failures) |
| 3 | §2.8.4: the text of the operator migration notice (release note, dashboard banner, escalation modal). | DW-3 |
| 4 | §5.2: a named test plan. Argv tests per provider for AG-22 to AG-25 (which replace M1-E2-T2), and the D-011 and D-012 tests for M3-E3-T1 and M3-E3-T2. | DW-4 |
| 5 | New §2.9: D-011 and D-012 designed. A per-call `ExecutionAuthorization` bound to the exact command and work dir, single use, never ambient; one Postgres request and grant store written only by the control plane, MAC-signed grants, single-use consumption through the control plane, expiry on restart, cross-process resolution by LISTEN/NOTIFY with a poll fallback. | SEC-1 (critical), REV-1 (critical) |
| 6 | M3-E3-T1's go-live order versus confinement becomes operator question OQ-1 (§9.1), with the recommendation to require AG-03, AG-14, AG-15 and AG-19 first. The plan edit is listed for the orchestrator (§9.3). | REV-1 (dependency part) |
| 7 | Codex compile rule: `read_only` always compiles to Codex's own `--sandbox read-only`; `danger-full-access` only at `workspace_exec` under L2; the static `inner_sandbox_ok` field becomes a runtime probe. **Superseded by revision 3 rows 1 and 2.** | SEC-2, REV-2 |
| 8 | §2.2.3: escalation is an increase in effective capability (`read`, `write`, `exec`, `egress`) per provider, not only a level raise. The published snapshot records a capability ceiling; the resolver refuses any provider whose capability exceeds it. | SEC-3 |
| 9 | §2.2.3: the escalation check lives inside `ControlPlaneManager.publish_agent`, which every publish path calls. A publish needs an actor; the route, the six internal callers and the new migration are listed with their behaviour and a test each. Clone and first publish compare with the `read_only` baseline. | SEC-4 |
| 10 | §2.3.5: persistent instructions and extensions. Claude adds `--safe-mode` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`; Codex adds `project_doc_max_bytes=0`, `--ignore-rules`, `--ephemeral`, `--disable hooks`, `--disable plugins`, `--disable apps`; Gemini gets an allowlisted system-settings file. Provider homes are rebuilt before every spawn from a per-provider allowlist. New live canaries. **The Gemini part is superseded by revision 3 rows 5 to 7.** | SEC-5 |
| 11 | §2.4.4: CLI login homes move to an app-only path; the sync-back is an allowlist of named credential files, schema-checked, done by the control plane through the AG-17 broker; config, hooks and instruction files never cross. Operator question OQ-4. | SEC-6 |
| 12 | §2.5.4: the credential residual extends to `read_only` and `workspace_write` until AG-23 and AG-25 prove the file tools' path confinement; live checks named. | SEC-7 |
| 13 | §2.5.3: the snapshot MAC binds `agent_id`, `version`, `published_at` and the snapshot hash; the supervisor refuses a version lower than the highest it has verified for that agent; the remaining rollback path is residual R-5, closed by M1-E2-T5. | SEC-8 |
| 14 | §2.4.2: network claims restated (TCP connect per port only; UDP and pathname UNIX sockets are not covered); Landlock signal and abstract-socket scoping applied at ABI ≥ 6; a UNIX-socket kernel target is refused under `strict`. | SEC-9 |
| 15 | Gemini levels use a `tools.core` allowlist instead of a `tools.exclude` denylist; `admin.secureModeEnabled` blocks `yolo` below `workspace_exec`. **Corrected in revision 3:** the system file carrying them was skipped and `admin.*` keys from any file are ignored; the allowlist and `security.disableYoloMode` now live in the user settings (revision 3 row 5). | SEC-10 |
| 16 | §2.6.2: the spawn event records the resolved L2 profile, the generated settings digest and the effective tool list. | SEC-11 |
| 17 | Gemini argv in the attached `--flag=value` form throughout; option-injection argv tests; `CODEX_BIN` and `GEMINI_BIN` recorded as one executable path inside the L2 read-only exec grant, with their changes audited. | SEC-12, REV-7, REV-8 |
| 18 | C10, C12 and §2.5 describe AG-04 and AG-05 as implemented, with the startup-window residual, the `.master.key.accept-undecryptable` file, the five `ensure_master_key` outcomes and the fingerprint audit event. | SEC-13, REV-10, REV-11 |
| 19 | MASTER_PLAN M1-E2-T2, T3 and T4 rewritten to map to the AG items; no bypass opt-in and no key copy remain. | SEC-14, REV-4 |
| 20 | Gemini system instructions stay on stdin, but user text is escaped so it cannot close the `<user_request>` block; named test. `GEMINI_SYSTEM_MD` was considered and rejected (§3). | SEC-15 |
| 21 | AG-06 is described as ADR-039 records it (one fnmatch engine, replay safeguard at delivery), and M1-E4-T9 is folded into it. | REV-3 |
| 22 | §7 dependencies fixed: AG-23 and AG-25 need AG-14 only for `workspace_exec`; AG-10 split into delivery (AG-10a) and rule activation (AG-10b, the §13 part), and AG-20 needs only AG-10a; AG-19 needs AG-05, AG-08, AG-17 and AG-18; compose hardening moves to AG-19b. | REV-5 |
| 23 | Codex native resume is off until proven (`exec resume` takes no `--sandbox`); Codex declares `supports_native_resume=False`, AG-24 depends on M3-E5-T1, and the bypass-flag sentence is removed. | REV-6 |
| 24 | Internal-call ceiling corrected: Claude `none`, Codex and Gemini `read_only`. **Superseded by revision 3 row 12:** `none` on every provider. | REV-7 |
| 25 | The claim that probes and argv cannot drift now covers flags only. Codex `-c` keys are probed for existence and type; their behaviour stays a live check, and a level that depends on an unproven key is unavailable. | REV-9 |
| 26 | AG-18 no longer moves the approval JSON files; they are retired by M2-E1-T2 and replaced by §2.9. | REV-12 |
| 27 | The grep guard is replaced by assertions on the compiled argv of every profile, plus "no legacy token left in the contract". | REV-13 |
| 28 | One `koda policy audit` (AG-09) with three sections serves the upgrade report, AG-30 and the M3-E3-T1 approval package. | REV-14 |
| 29 | M1-E4-T7 (bubblewrap egress) is proposed for retargeting to AG-16's Landlock TCP rules: operator question OQ-5. | REV-15 |
| 30 | Stale task IDs updated; every code citation re-read at dfa596c; `queue_manager.py` cited by function and line. | REV-16; SEC summary (line drift) |
| 31 | Smaller design (MISSION §12): AG-01 dropped; the `published_by` column dropped; the per-level Gemini denylists, the static `inner_sandbox_ok` field and the Codex L2-only read-only mode removed; no new task for D-011 and D-012. | Task brief (anti-over-engineering) |

---

## 1. Context

### 1.1 Code today

**Provider built-in tools run ungoverned**

- **C1 [V]** Every turn runs with `permission_mode="bypassPermissions"` (`_prepare_query_context`, `koda/services/queue_manager.py:3122`). Supervised mode only sets `max_turns = 1` (`:3123`). `"plan"` is used only for scheduled dry runs (`:3122`), blocking artifact gaps (`:3465-3467`) and child runs (`:3593-3600`). The Claude argv adds `--permission-mode` from it and carries no tool flags (`koda/services/claude_runner.py:376-378, 665-667`); dry runs are forced to plan (`:92-96`).
- **C2 [V]** Codex defaults to `CODEX_SANDBOX=danger-full-access` and `CODEX_APPROVAL_POLICY=never` (`koda/config.py:269-270`). Both are operator system settings (`koda/control_plane/manager.py:608-609`). The startup check accepts a value set (`koda/startup_validator.py:67-72`) of which only `never` exists in Codex 0.169.0, and 0.169.0 refuses `untrusted` at config load (§1.2).
  - The runner discards `permission_mode` (`koda/services/codex_runner.py:629, 899`) and uses `--sandbox read-only` only for dry runs (`:286`).
  - Resume adds `--dangerously-bypass-approvals-and-sandbox` (`:259-260`), is ready only in the dangerous mode (`:312-330`) and refuses dry runs (`:283-284`).
  - So child runs, artifact-gap turns and the squad planner (`koda/squads/coordinator_engine.py:375-385`) run `danger-full-access` on Codex. The memory extractor passes `dry_run=True` (`koda/memory/extractor.py:192-193`), so it runs `--sandbox read-only`, with its shell.
- **C3 [V]** Gemini maps `bypassPermissions` to `yolo` and dry runs, child runs and artifact gaps to `plan` (`koda/services/gemini_runner.py:86-96`). The system instructions and the query go on argv as one `--prompt=` value (`:117`), wrapped in `<system_instructions>`/`<user_request>` tags without escaping (`:73-83`). The workspace is both `--include-directories` (`:116`) and the process cwd (`:363, 394, 541, 551`); no trust flag is passed.
- **C4 [V] AG-02 is implemented** (6d050b5). The CLIs are pinned in `packages/provider-clis` and installed by both images (`Dockerfile:4-11, 30-33`; `Dockerfile.runtime-kernel:3-10`). `koda/services/provider_cli_contract.py` holds the contract table (`:177-335`); `validate_args` refuses any token outside it (`:392-449`); probes fail closed (`:605-704`). `CODEX_BIN` and `GEMINI_BIN` are each one executable path, resolved by `provider_auth.provider_executable()` (`koda/services/provider_auth.py:439-460`); a command line is refused (`provider_cli_contract.py:623-629`); there is no `npx` fallback (`provider_auth.py:463-475`). The Gemini contract requires attached values (`provider_cli_contract.py:140-142, 334`).
- **C5 [V]** Koda governs only `<agent_cmd>` and OpenAI-style `tool_calls`, in `_run_agent_loop` (`queue_manager.py:4494`; policy at `:4884-4893`, execution at `:5115`). Claude's `tool_use` blocks have already run when Koda sees them and are kept as telemetry (`claude_runner.py:585-595, 905-906`). Koda's own shell, git and file tools are outside the secure default and are denied unless the agent's tool policy enables them (`koda/services/execution_policy.py:497-510`; `koda/agent_contract.py:1650-1659`; probed: `is_tool_allowed_by_secure_default` is false for every `shell_*`, `git_*` and `file_*` tool in the catalog).

**The policy layer is broken in ways the opt-in would inherit**

- **C6 [V]** `execution_policy` never reaches the worker. The runtime reads only `AGENT_EXECUTION_POLICY_JSON` (`config.py:1335`; `services/execution_policy.py:201-202`). The control plane emits the tool, autonomy and resource policy keys (`manager.py:3485, 3496, 12773-12774`) and ships the spec as `AGENT_SPEC_JSON` (`manager.py:803`), but never that key. Every dashboard-authored rule is ignored at runtime and the legacy branch runs (`services/execution_policy.py:479-575`).
- **C7 [V]** The two evaluators disagree: the runtime's order is deny > allow_with_preview > require_approval > allow (`services/execution_policy.py:40, 309`), the control plane takes the first match by priority. AG-06 (in progress as M1-E4-T9, ADR-039) makes one engine.
- **C8 [V]** Approvals are broken twice.
  - **D-011.** `run_shell_command` and the CLI runner refuse unless the ambient contextvar `_execution_approved` is true (`koda/utils/approval.py:66-73`; `koda/services/shell_runner.py:27-30`; `koda/services/cli_runner.py:107-115`). The agent loop never sets it, so policy-approved shell and git always fail. `execute_tool`'s supervised-write check uses the same contextvar (`koda/services/tool_dispatcher.py:779-790`). Only human commands (`approval.py:1125-1131, 1179-1341`) and scheduled shell jobs (`koda/services/scheduled_job_runtime.py:299-305`) set it.
  - **D-012.** Pending agent approvals are an in-memory dict with an `asyncio.Event` in the worker (`approval.py:1588, 1625-1730`; the loop waits at `queue_manager.py:4949`). The dashboard broker reads that dict from the supervisor process, where it is empty (`koda/services/approval_broker.py:152-163`). Persistence restores pending operations on start (`approval.py:86-153`; D-163). Scope grants match on the resource-scope fingerprint plus session and chat (`approval.py:1371-1389`), with the scope's TTL and `max_uses` (`:1413-1414`).
- **C9 [V]** `publish_agent` snapshots the **draft** (`manager.py:12573`) and records no actor (`:12579-12613`). It has six callers besides the API route (§2.2.3). Policy writes (`put_section` `:12115`, `put_execution_policy` `:8652`, `put_model_policy` `:8583`) are not audited, and `record_audit_event` swallows failures by design (`koda/control_plane/audit.py:22-35`).
  - The voice toggle publishes the whole draft (`koda/handlers/commands.py:2447` → `koda/services/agent_settings.py:495-508` → `_publish_agent_runtime_update`, `:482-492`); so do the audio functional defaults (`commands.py:2059`; `agent_settings.py:614, 689`).
  - `/provider` and `/model` write only the draft model policy (`commands.py:447, 510` → `agent_settings.py:517-553, 555-578`), and the worker builds its runtime settings from `build_draft_snapshot` (`agent_settings.py:232-236`), so a draft model-policy write takes effect without any publish.

**Secrets and confinement**

- **C10 [V]** `runtime-kernel` mounts `koda-state` read-write (`docker-compose.yml:249`). The master key lives there at `STATE_ROOT_DIR/control_plane/.master.key` (`koda/control_plane/settings.py:52-53`), and so does `bootstrap.txt` (`koda/control_plane/bootstrap_file.py:36`). The supervisor forwards `STATE_ROOT_DIR` to workers (`koda/control_plane/supervisor.py:92`).
  - **AG-05 is implemented** (6d050b5). No process creates a key implicitly (`koda/control_plane/crypto.py:159-168`). Only the supervisor calls `ensure_master_key()` (`supervisor.py:223`), which ends in one of five outcomes: `fresh_install`, `upgrade`, `lost_key_reset`, `verified`, `rotation` (`crypto.py:89, 394-478`). A Postgres fingerprint row binds the key to the database; on upgrade the key must decrypt one of the newest stored values (`crypto.py:354-391`), and the lost-key path needs the operator file `.master.key.accept-undecryptable` naming the new key's fingerprint prefix (`crypto.py:53, 308-330`). Each outcome emits `security.master_key_fingerprint_recorded` (`crypto.py:336-341`). The previous key is read from `CONTROL_PLANE_MASTER_KEY_PREVIOUS` or its file (`crypto.py:171-179`). Disconnecting a provider removes only the CLI login files (`manager.py:1575-1580`; D-230).
  - Workers still decrypt in-process: `koda/services/mcp_connection_broker.py:17, 156` and `koda/services/mcp_oauth.py:732, 827`. AG-17's import-graph test enumerates any other path.
- **C11 [V]** Isolation is cgroups only; workers and CLIs run as the same uid (`botuser`, `Dockerfile.runtime-kernel:59, 88`). Kernel gRPC is unauthenticated on `0.0.0.0:50061` (`docker-compose.yml:245-246`; D-042), and the kernel also binds a UNIX socket when its target is a path (`rust/koda-runtime-kernel/src/server.rs:3223-3231`).
- **C12 [V]** Worker env and children:
  - the worker env holds the Postgres credentials and the S3 secret (`supervisor.py:66-69, 82`) and decrypted granted secrets;
  - CLI and tool child envs are allowlisted (`koda/services/provider_env.py:182-236`), but `HOME`, `USER`, `LOGNAME` and the `XDG_*` directories pass through (`:206-222`), so every CLI reads the shared HOME (C13);
  - MCP stdio servers inherit the whole worker env (`mcp_bootstrap.py:90` → `mcp_manager.py:128` → `mcp_client.py:156-162`), and so do yt-dlp, ffmpeg and ffprobe (`link_analyzer.py:128, 186`; `artifact_ingestion.py:1511, 1568`; `utils/audio.py:123, 170, 291`; `utils/video.py:37`);
  - **AG-04 is implemented** (6d050b5): the worker's first statement makes it non-dumpable with `RLIMIT_CORE=0` and refuses to start otherwise (`koda/__main__.py:9-11`; `koda/process_hygiene.py:52-77`). Python's own startup runs before that, so a same-uid process can read a starting worker's env, and can kill the worker to reopen the window (`process_hygiene.py:24-33`; `docs/security/threat-model.md:96`). Only L2 closes it (§2.5.4, R-2).
- **C13 [V]** `DEFAULT_WORK_DIR` is HOME (`config.py:201`), and in compose HOME and `CLAUDE_CONFIG_DIR` sit on `koda-runtime` (`docker-compose.yml:29-31`), which `runtime-kernel` mounts read-write (`:250`). `SENSITIVE_DIRS` blocks every path under `/var/lib` (`config.py:775`; `tool_dispatcher.py:2389-2402`), which includes the Docker work dirs.
- **C14 [V]** The app also uses the worker's state subpaths: skill locks (`koda/skills/_package.py:1277`), the channel gateway (`koda/channels/gateway.py:133`), room photos (`koda/squads/room_photos.py:56`), TTS assets (`koda/services/kokoro_manager.py:25-33`, `supertonic_manager.py:22-30`). A one-time copy to a worker-only volume would split them.
- **C15 [V] Shared temporary space.**
  - The memory extractor runs with `work_dir="/tmp"` (`koda/memory/extractor.py:187`) on an install-wide provider chain (`:183`; `koda/memory/config.py:9`), not the agent's model policy. The squad planner runs in `DEFAULT_WORK_DIR` (`coordinator_engine.py:380`) on the coordinator's live, unpublished spec (`:419-437`, `get_agent_spec`).
  - Docker MCP env files, secrets included, are written with `tempfile.mkstemp` into the system temp dir and never deleted (`koda/services/mcp_isolation.py:329-330, 392-410`).
  - On native installs `RUNTIME_EPHEMERAL_ROOT` defaults to `<system temp>/koda-runtime/<bid>` (`config.py:207-213`), and so would every provider home under it. Compose sets the kernel root to `/tmp/koda-runtime/default/kernel` by default (`docker-compose.yml:247`).
- **C16 [V] Git.** No Koda git spawn sets `core.fsmonitor`, `core.hooksPath` or `GIT_CONFIG_*` (a search of `koda/` finds none). `git_status`, `git_diff` and `git_log` are read tools (`tool_dispatcher.py:192-194`), so they run without a grant even in supervised mode. Governed git runs through `_run_git` and `run_cli_command_detailed` (`tool_dispatcher.py:2870-2889`).

### 1.2 Pinned CLI facts checked in this revision

| Fact | How checked |
|---|---|
| `claude` 2.1.325, `codex-cli` 0.169.0, `gemini` 0.68.0; Koda's contract check passes for all three. | `--version` of each; `python -m koda.services.provider_cli_contract` with the three on `PATH` → `ok: true` ×3 (revision 2). |
| Claude `--permission-mode` choices: `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`. `manual` is an alias of `default`. `default` prompts for dangerous operations, `acceptEdits` auto-accepts edits, `plan` executes no tools, `dontAsk` denies anything not pre-approved, `auto` lets a model classifier approve. | Help fixture lines 151-154; strings of the pinned binary. |
| `--restricted` removes code-running tools and WebFetch unless `--tools` names them, ignores user, project and local settings, confines the file tools to the working directories, refuses `bypassPermissions`. It does **not** stop CLAUDE.md. `--safe-mode` disables CLAUDE.md, skills, installed plugins, hooks, MCP servers, custom commands and agents; auth, model selection, built-in tools and permissions work normally. | Help fixture lines 195-209, 213-223. |
| The parser accepts the whole every-level argv of §2.3.1. | `claude -p --output-format json --model m --max-turns 1 --restricted --safe-mode --strict-mcp-config --disable-slash-commands --permission-prompts none --permission-mode dontAsk --tools "" --allowedTools "" --append-system-prompt-file <f> --no-session-persistence --koda-unknown-option` reports only the unknown option. |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY` disables auto-memory; `--tools ""` disables all tools; `--permission-prompts none` denies anything that would prompt; `--bare` reads only `ANTHROPIC_API_KEY`. | Strings of the pinned binary; help fixture lines 155-162, 255-259, 41-58. |
| Codex `exec` takes `--sandbox {read-only, workspace-write, danger-full-access}`, `--ephemeral`, `--ignore-rules`, `--ignore-user-config`, `--enable/--disable <feature>`, `--trust`, `--approve-for-me`, `--dangerously-bypass-approvals-and-sandbox`, `--dangerously-bypass-hook-trust`. `exec resume` has **no** `--sandbox`. | `codex exec --help`, `codex exec resume --help`. |
| Codex `approval_policy` parses as `untrusted`, `on-failure`, `on-request`, `granular`, `never`; `untrusted` fails config load. | `codex -c approval_policy="<v>" features list` for each value (revision 2). |
| Codex config keys exist with these types: `sandbox_mode`, `sandbox_workspace_write.network_access` (bool), `sandbox_workspace_write.exclude_slash_tmp` (bool), `sandbox_workspace_write.exclude_tmpdir_env_var` (bool), `sandbox_workspace_write.writable_roots` (sequence), `shell_environment_policy.*`, `mcp_servers`, `web_search`, `project_doc_max_bytes`, `agents.enabled` (bool), `skills.include_instructions` (bool), `skills.bundled.enabled` (bool), `features.<name>` (bool). `include_apply_patch_tool` and `tools.view_image` are unknown and silently ignored. | `codex -c <key>=<wrong type> features list`: each typed key errors naming itself; unknown keys are accepted silently. |
| **Codex's inner sandboxes cannot start inside a Landlock domain.** `codex sandbox -c sandbox_mode="read-only"` and `"workspace-write"` work unconfined and after `no_new_privs` alone, and fail with `bwrap: Failed to make / slave: Operation not permitted` inside an allow-all Landlock ruleset. `--enable use_legacy_landlock` panics (`linux_run_main.rs:391`). `danger-full-access` runs inside the same ruleset. Codex itself (`codex debug prompt-input`) runs inside it. | `codex sandbox -c sandbox_mode=<m> -- /bin/sh -c <probe>` unconfined, after `prctl(PR_SET_NO_NEW_PRIVS)`, and after the Landlock helper; kernel 6.18, ABI 7. |
| Unconfined, `read-only` refuses writes ("Read-only file system") and sockets (EPERM) but **reads every file the uid can read**; the sandboxed shell has its own pid namespace. `workspace-write` writes the cwd, `/tmp`, `$TMPDIR` and anything under them (it wrote `$CODEX_HOME/AGENTS.md` when that home was under `/tmp`). With `exclude_slash_tmp=true`, `exclude_tmpdir_env_var=true` and `writable_roots=["<task tmp>"]` only the cwd and the task tmp are writable; sockets stay EPERM unless `network_access=true`. | `codex sandbox` probes that cat a file outside the cwd, write each path, and create a socket. |
| In Codex 0.169.0, 71 features report `true` by default, among them `browser_use`, `browser_use_external`, `browser_use_full_cdp_access`, `computer_use`, `in_app_browser`, `in_app_local_automation`, `multi_agent`, `image_generation`, `guardian_approval`, `daemon_auto_start`, `remote_plugin`, `skill_mcp_dependency_install`, `workspace_dependencies`, `tool_suggest`, `shell_snapshot`, `view_image`. An unknown feature name is an error. `--disable unified_exec` leaves it reported `true`; `--disable shell_tool` removes the shell tools. Some removed features stay `true` (`item_ids`, `tui_app_server`, `worktrees`). | `codex features list`; `codex --disable <f> features list` per feature. |
| `codex debug prompt-input` renders the model-visible input offline, for models whose catalog entry is `tool_mode: code_mode_only` (the `gpt-6-*` family; `gpt-5.5` renders no tool list). For `gpt-6-sol` the default tools are `exec` (a JavaScript orchestrator with no filesystem or network of its own) nesting `apply_patch`, `exec_command`, `write_stdin`, `view_image`, the MCP resource tools and a clock, plus `wait`, `request_user_input`, `sleep` and six `collaboration.*` sub-agent tools. With the §2.3.3 every-level flags and `--disable shell_tool`, only `apply_patch`, the (empty) MCP resource tools, the clock, `wait`, `request_user_input` (and its async variant) and `sleep` remain; with the shell, `exec_command` and `write_stdin` are added. `-c agents.enabled=false` removes the `collaboration.*` tools; `--disable multi_agent` does not. | `codex debug prompt-input -c model="gpt-6-sol" … hi`, then the tool names in the JSON; `codex debug models` for `tool_mode`. |
| Codex instruction and skill loading: with no switches, skills from the workspace `.agents/skills` and `.codex/skills`, from `$HOME/.agents/skills`, from `$CODEX_HOME/skills` and the bundled system skills enter the prompt, and so do the workspace `AGENTS.md` and `$CODEX_HOME/AGENTS.md`. `project_doc_max_bytes=0` drops only the workspace `AGENTS.md`. `skills.include_instructions=false` with `skills.bundled.enabled=false` drops every skill (and the bundled skills are not installed into `$CODEX_HOME`). Setting HOME to `$CODEX_HOME` drops the shared-HOME source. A workspace `.codex/config.toml` is not loaded without `--trust`. | `codex debug prompt-input` with canary `SKILL.md`, `AGENTS.md` and `config.toml` files planted in each place. |
| Gemini `--approval-mode` choices: `default`, `auto_edit`, `yolo`, `plan`; `-y/--yolo`; `--skip-trust`; `-e/--extensions`; `--include-directories` (comma-separated: a value with a comma becomes two directories, `gemini-Q2FNZWQG.js:8727`); `-p` is appended to stdin input. | `gemini --help`; bundle. |
| **Gemini skips a system settings file** unless the file and every ancestor are owned by root and not writable by group or others; it prints `Security Warning: Skipping system settings file … Parent directory '/tmp' is insecure` and continues (here `YOLO mode is enabled` followed). Workers run as `botuser` (C11), so no file they write can pass. | Run with `GEMINI_CLI_SYSTEM_SETTINGS_PATH` pointing at a file that sets `security.disableYoloMode`; bundle `chunk-VFM6AETN.js:38307-38320`, `chunk-RCB6BI5H.js:368971, 369112`. |
| Gemini rebuilds `admin.*` only from schema defaults and remote Code Assist admin settings, so `admin.*` from any file is ignored. | Bundle `chunk-VFM6AETN.js:37945-37953`. |
| **User settings** (`$HOME/.gemini/settings.json`, or `GEMINI_CLI_HOME`) load with no ownership check: `{"security":{"disableYoloMode":true}}` there makes `--approval-mode=yolo` fail with "YOLO mode is disabled by the "disableYolo" setting" before auth. An invalid value prints `Invalid configuration in …` and the key is dropped. The §2.3.2 settings validate without any warning. | Offline runs; bundle `chunk-VFM6AETN.js:38254-38272, 38327`; `gemini-Q2FNZWQG.js:8906-8928`. |
| Workspace settings load only from `<cwd>/.gemini/settings.json` and only when the cwd is trusted; the merge order is defaults < system defaults < user < workspace < system. With `GEMINI_CLI_TRUST_WORKSPACE=true`, a workspace file that sets `disableYoloMode` refuses `yolo` when it is the cwd, and has no effect when the same directory is passed with `--include-directories` from another cwd. | Offline runs; bundle `chunk-VFM6AETN.js:37860-37871, 38328-38331, 38377-38382`; `chunk-RCB6BI5H.js:253424-253426`. |
| `--skip-trust` sets `GEMINI_CLI_TRUST_WORKSPACE=true` only after `main()` has loaded settings, and settings are cached for 10 s: with `--skip-trust` the same workspace `disableYoloMode` file had no effect, while later `loadSettings` calls after the cache expires see the trust. | Offline runs; `gemini-Q2FNZWQG.js:8765-8767, 18768-18788`; `chunk-VFM6AETN.js:38191-38195`. |
| `.env` loading: when trusted, Gemini walks from the cwd to `/` and loads the first `<dir>/.gemini/.env` or `<dir>/.env`, then the home's; it sets only keys not already in the environment, and a pinned value (empty for ordinary keys) is kept. `advanced.excludedEnvVars` applies only to a plain `.env`; `advanced.ignoreLocalEnv` skips plain `.env` files except in the home. A planted `.gemini/.env` set `GEMINI_SYSTEM_MD`, `GOOGLE_GEMINI_BASE_URL` (which switches auth to a gateway) and `GEMINI_TELEMETRY_*` when unpinned, and none of them when pinned. | Offline runs with a `NODE_OPTIONS` preload that records the child's environment at exit; bundle `chunk-VFM6AETN.js:38086-38117, 38146-38190`; `chunk-RCB6BI5H.js:286010-286025, 313747-313749, 337236-337262`. |
| GEMINI.md cannot be switched off: `context.fileName` is unioned with the current names, which start as `GEMINI.md`; and when a tool reads a file inside a trusted workspace directory, JIT discovery appends the GEMINI.md files on the path from that directory to the workspace root to the tool output. `context.loadMemoryFromIncludeDirectories` (default `false`) keeps include directories out of the startup memory. | Bundle `chunk-RCB6BI5H.js:253526-253549` (`setGeminiMdFilename`), `310192-310203, 311388` (JIT), `365212-365227`; `gemini-Q2FNZWQG.js:8824-8828, 9077`. |
| `tools.core` is an allowlist applied when built-in tools register, and an empty list registers none. `activate_skill` is also registered outside the allowlist when skills are enabled, so `skills.enabled=false` is needed. Hooks follow `hooksConfig.enabled`, sub-agents `experimental.enableAgents`. | Bundle `gemini-Q2FNZWQG.js:9084, 9129, 9136, 9188`; `chunk-RCB6BI5H.js:382636-382644, 384321-384385`; tool names `:280949-280991`. |
| In headless mode an untrusted cwd is fatal (`FatalUntrustedWorkspaceError`) unless trust comes from `--skip-trust` or the env; an untrusted folder forces `default` mode; any "ask user" decision is denied. | Bundle `gemini-Q2FNZWQG.js:8930-8934, 12659-12673`; `chunk-RCB6BI5H.js:366049-366051`. Auth fails first without credentials, so the order is `[I]` (AG-25). |
| The kernel here reports Landlock ABI 7. Deployment hosts and Docker's default seccomp are `[I]`; AG-08 finds out. | The Landlock helper's ABI query. |

---

## 2. Decision

### 2.1 Invariants

1. **Koda policy is the only authority.** A provider built-in tool runs only at a level the agent's signed, published policy pre-authorises, lowered by every ceiling that applies, and only on a provider whose capability the published policy covers. Nothing raises it.
2. **Per-call approval exists only on the governed path.** Built-in tools have no approval state, because the CLIs run headless. Anything that needs a human goes through `<agent_cmd>`, `evaluate_execution_policy` and the approval pipeline (§2.9).
3. **Koda confines model-directed code.** Every process that runs code the model controls, or code it can plant, runs inside Koda's confinement or does not run. A provider's own sandbox is an inner layer, used only where it has been proven to start inside the same confinement.
4. **Never wider than the inner layer allows.** Koda never asks a provider sandbox for more than the effective level, except where Koda's own L2 enforces the level instead. In `RUNTIME_CONFINEMENT=off` the provider's own restriction is the only layer, and no level is weaker than today's behaviour.
5. **The model cannot reach control-plane secrets.** No process the model can reach holds or can read the master key, the bootstrap code, the worker's secrets, another agent's data or an unauthenticated control endpoint. Residuals, including everything `off` gives up (R-8), are listed in §2.5.4.
6. **Fail closed.** An unverified CLI version, a missing flag, an unproven restriction, a settings warning or a missing kernel feature makes the capability unavailable, and the reason is shown. It never silently widens.

### 2.2 Governance model

#### 2.2.1 Field

- `execution_policy.provider_builtin_tools.level` is an ordered enum: `none < read_only < workspace_write < workspace_exec`. It is a typed block compiled at spawn, not a matched rule. There are no per-provider overrides and no free-form tool lists; those break across CLI versions.
- **Default `read_only`.** A missing block or key means `read_only`. It matches the governed path's baseline, where reads by enabled tools are allowed and writes need approval (`services/execution_policy.py:532-575`), and reads stay cheap.
- **One delivery channel.** The published, signed `AGENT_SPEC_JSON` (AG-10a, AG-11) carries the execution policy **and the model policy**. `AGENT_EXECUTION_POLICY_JSON` and its readers are deleted. The worker reads neither drafts (`agent_settings.py:232-236` and the `skills/_runtime.py` draft fallback move to the published snapshot) nor live control-plane rows for governance (the squad planner's `get_agent_spec`, `coordinator_engine.py:423`, included).
- **One resolver**, `koda/services/provider_builtin_tools.py`: `normalize`, `validate`, and `resolve(published, provider, ctx) -> BuiltinToolProfile{requested, effective, clamps[], capability, process_class, refusal}`. The runtime, publish validation, the prompt preview and the simulator import it. The control-plane normalizer delegates this block to it.
- The name avoids "native tools", which means Koda tools sent as function-calling schemas (`docs/architecture/tool-registry-native-tools.md`).

#### 2.2.2 Schema

Authored by the operator, in the draft and the published spec:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "koda:execution_policy.provider_builtin_tools",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "level": { "enum": ["none", "read_only", "workspace_write", "workspace_exec"], "default": "read_only" }
  }
}
```

- Validation errors use the existing execution-policy error shape: `{"path": "execution_policy.provider_builtin_tools.level", "code": "invalid_enum", "message": ...}`, and `code: "unknown_key"` for any other key.
- The block has no version key. It is versioned with the snapshot; an incompatible change would add a new key, never a new meaning for `level`.

**Actor.** One shape everywhere (the gate's parameter, the governance block, the audit event):

```json
{
  "$id": "koda:actor",
  "type": "object",
  "additionalProperties": false,
  "required": ["kind", "id"],
  "properties": {
    "kind": { "enum": ["operator", "system", "system:migration", "system:import", "telegram_user"] },
    "id": { "type": "string", "description": "operator account id, Telegram user id, or the system component (supervisor, bootstrap, runtime_snapshot, AG-21 migration, legacy import)" }
  }
}
```

Derived at publish by `publish_agent` (never authored; a draft that contains it is rejected), inside the signed snapshot:

```json
"governance": {
  "provider_builtin_tools": {
    "level": "workspace_write",
    "capability_ceiling": ["read", "write"],
    "providers": ["claude", "gemini"],
    "published_by": { "kind": "operator", "id": "7" },
    "confirmed": true,
    "published_at": "2026-11-20T10:00:00Z",
    "previous_version": 41
  }
}
```

`providers` is every provider the published model policy lets the agent run: the default provider, the fallbacks and the functional defaults. `capability_ceiling` is the union of `capability(provider, level)` over them (§2.2.3).

#### 2.2.3 Capability, escalation and the publish gate

**Capability.** The contract table records, per pinned CLI version, provider and level, a conservative capability set over `read` (file reads), `write` (workspace writes), `exec` (model-chosen programs) and `egress` (model-chosen network connections), taken as the widest over the confinement modes:

| Provider | `none` | `read_only` | `workspace_write` | `workspace_exec` |
|---|---|---|---|---|
| Claude | `[]` | `[read]` | `[read, write]` | `[read, write, exec, egress]` |
| Codex 0.169.0 | `[]` | `[]` (clamped to `none`, §2.3.3) | `[read, write, exec]` (only under `off`, R-8; clamped to `none` under L2) | `[read, write, exec, egress]` |
| Gemini | `[]` | `[read]` | `[read, write]` | `[read, write, exec, egress]` |

**Escalation** is a publish whose level is higher than the baseline's, or whose `capability_ceiling` is not a subset of the baseline's. Adding Codex to a Claude `workspace_write` agent adds `exec` and is an escalation; raising the level is one; adding Codex to a Claude `read_only` agent is not, because Codex has no tools at `read_only`.

**Runtime check (S10).** A turn on provider P at effective level L runs only if `capability(P, L)` is a subset of the published `capability_ceiling`; otherwise P is refused for the turn with `capability_not_confirmed`, the fallback chain skips it, and an alert is raised. Because the model policy now comes only from the published snapshot, the ceiling covers every provider it names and capability is monotone in the level, so S10 can fail only after a CLI bump changes the capability table or through a bug; it stays as that assertion. Internal calls run at `none`, whose capability is empty, so they pass on any provider.

**Publish gate.** `publish_agent(agent_id, *, actor, confirm_escalation=False, change=None)` takes a required `actor` (§2.2.2). Inside it, before the version insert:

1. **Source.** Only an `operator` publish takes the draft as it is. No other actor can publish the operator's pending policy:
   - `telegram_user` applies only its own `change` to the **last published snapshot**: a field-level patch from a closed list (`voice_policy.mode`; `model_policy.default_provider`, `default_models.<provider>` and `functional_defaults.<function>`). The caller writes the same patch to the draft, so the dashboard shows it.
   - `system` publishes only an agent that has never been published (supervisor reconcile, bootstrap, runtime snapshot fallback; each publishes only when no version exists, `supervisor.py:458-461`, `bootstrap.py:53-55`, `manager.py:12633-12635`). It takes the draft with `execution_policy` and `tool_policy` replaced by the defaults a new agent gets (no rules, level `read_only`, the secure-default tool subset); the dashboard shows the operator's policy as pending until an operator publishes it.
   - `system:migration` publishes the last published snapshot with only the governance block or the signature added (AG-21, AG-11). `system:import` publishes the imported legacy configuration at level `read_only`, which only lowers what those agents ran with.
2. **Baseline.** The last published version's governance block. A version without a governance block counts as unrestricted (it ran with bypass), and only the AG-21 migration publishes over it. An agent never published has the baseline `{level: read_only, capability_ceiling: [read]}`.
3. **Check.** On escalation, refuse unless `actor.kind == operator` and `confirm_escalation`. The error names the new capabilities; for `telegram_user` the reply is "A troca precisa de confirmação no painel: {capacidades}." and the patch stays in the draft.
4. **Write** the version, the governance block (signed with the snapshot, AG-11) and the `agent.provider_builtin_tools_changed` event (§2.6.1) in one transaction; the publish fails if the event cannot be written.
5. **Migration state.** A publish of an agent whose last published version has no governance block is refused with `governance_migration_pending`. The AG-21 migration runs at every control-plane start before the API serves (next to `ensure_master_key`, `supervisor.py:223`), per agent, and retries agents that failed; it never blocks other agents.

Every publish path calls this one function (`manager.py:12568`):

| Caller | Actor | Source | On escalation |
|---|---|---|---|
| Publish route (`koda/control_plane/api.py:3085-3095`) | `operator`; `confirm_escalation` from the body, sent only by the escalation modal | draft | publishes when confirmed |
| Onboarding (`manager.py:5909`) | `operator`; the onboarding step shows the modal when the chosen provider's `read_only` capability exceeds `[read]` (none on the pinned CLIs) | draft | publishes when confirmed |
| Supervisor reconcile, first publish (`supervisor.py:459-461`) | `system` | draft with secure-default execution and tool policies | refused; the agent shows "Aguardando publicação" |
| Runtime snapshot fallback (`manager.py:12634-12636`) | `system` | as above | refused |
| Bootstrap (`koda/control_plane/bootstrap.py:53-56`) | `system` | as above | refused |
| Legacy import (`manager.py:13101`) | `system:import` | imported configuration at `read_only` | other raises refused |
| Voice toggle (`commands.py:2447` → `agent_settings.py:495-508`) | `telegram_user` | last published + `voice_policy.mode` | n/a (no capability change) |
| `/provider`, `/model`, functional defaults (`commands.py:447, 510, 587, 2059` → `agent_settings.py:517-553, 555-578, 581-617, 689`) | `telegram_user` | last published + the model-policy patch (these now publish; today only the voice and audio paths do) | refused, patch kept in the draft |
| AG-21 migration | `system:migration` | last published + governance block at `read_only` | n/a (only lowers) |
| AG-11 re-signing | `system:migration` | last published, unchanged, signed | n/a |

`clone_agent` (`manager.py:9937`) copies the execution policy into a new draft; its first operator publish compares with the never-published baseline, so a cloned `workspace_exec` policy needs confirmation.

#### 2.2.4 Koda policy states and ceilings

The effective level is the minimum of the published level and every applicable ceiling. The matrix in §2.3 names these states.

| State | Signal | Ceiling | Replaces |
|---|---|---|---|
| S1 | Published level (default `read_only`) | — | — |
| S2 | Scheduled dry run | `read_only` | `queue_manager.py:3122`; `claude_runner.py:92-96`; `codex_runner.py:286`; `gemini_runner.py:86-88` |
| S3 | Blocking artifact gap | `read_only` | `queue_manager.py:3465-3467` |
| S4 | Child run, any toolset | `read_only` | `queue_manager.py:3593-3600` |
| S5 | Effective `approval_mode` ∈ {`read_only`, `escalation_required`} | `read_only` | new (never reached the CLI) |
| S6 | `agent_mode == supervised` | `read_only` | `queue_manager.py:3123` |
| S7 | Internal call site: memory extractor, squad planner | `none` on every provider, with a fresh, empty per-task work dir and `TMPDIR` under the task tmp (never `/tmp`, HOME or `DEFAULT_WORK_DIR`). The extractor keeps its install-wide chain; the planner uses the coordinator's published model policy. | `memory/extractor.py:183-193`; `coordinator_engine.py:375-385, 419-437` |
| S8 | Level not faithful on this CLI, host and confinement profile (the contract; the Codex probe `IP` run inside the spawn's own profile; Codex's unconfined reads; a settings warning) | next lower faithful level | — |
| S9 | Class M level while the confinement mode's required layers are missing (from AG-14 on) | the highest class S level; governed class M processes (shell, `shell_bg`, git, `cli_runner`) are refused | — |
| S10 | `capability(P, L)` not covered by the published ceiling (internal calls included) | provider refused for the turn; an assertion (§2.2.3) | — |

- The task-kind default `supervised` approval mode (`knowledge/task_policy_defaults.py`) is deliberately not a ceiling: general tasks default to it, so it would make every opt-in inert, and it is derived from the query text. Ceilings may come from such signals only because they only lower.
- Below the floor (`none` on every provider), the provider is refused for the turn; the level is never raised.
- **Supervised mode means the same on every provider:** built-ins capped at `read_only`; every governed write needs a human grant (§2.9.1); Koda's loop pauses after each governed round with the existing Continue/Stop buttons (`queue_manager.py:6513-6522`). The Claude-only `--max-turns 1` coupling is removed.
- **Governed-loop budget.** `MAX_AGENT_TOOL_ITERATIONS` stays the install-wide ceiling (operator setting `manager.py:650`; default 8, `config.py:1326`), and `max_budget` also stops the loop. The default changes only on M0-E3-T2 eval evidence (AG-27).
- **Evaluator.** AG-06 builds one engine with fnmatch for every rule; precedence is the most restrictive decision first (deny > require_approval > allow_with_preview > allow), then priority, then name; a rule's name is its audit `rule_id`; simulate and preview call it. This is ADR-039, which amends ADR-008 step 1 and moves its replay safeguard to delivery: AG-09 replays every stored policy under the legacy matcher and the engine before AG-10b activates rules. It changes nothing in production while rules are undelivered (C6).

### 2.3 Provider mode matrix

Each runner compiles the profile from the one contract table in `provider_cli_contract.py`, keyed by pinned version. The probes check every flag against `--help` (or the parser probe for hidden flags). Codex config keys are probed for existence and type (A-K-01), Codex features against a reviewed list (A-K-02) and Codex's model-visible tools offline (A-K-04); the Gemini settings file is probed offline for being read (A-K-05). A level whose restriction depends on an unproven key or setting is unavailable (S8) until its live check passes.

#### 2.3.1 Claude Code 2.1.325

**Every level:**

```
claude -p --output-format json|stream-json [--verbose] --model M --max-turns N
  [--max-budget-usd B] [--effort E] [--resume ID]
  --restricted --safe-mode --strict-mcp-config --disable-slash-commands
  --permission-prompts none --permission-mode dontAsk
  --tools <T> --allowedTools <T>
  --append-system-prompt-file <task_tmp>/system.md        (mode 0600, deleted after the run)
  [--add-dir <task_tmp>/images]
cwd: the workspace; for S7 internal calls, a fresh empty per-task dir
env (allowlisted builder, AG-03): CLAUDE_CODE_DISABLE_AUTO_MEMORY=1; HOME, CLAUDE_CONFIG_DIR and XDG_* inside the agent's Claude home; TMPDIR = the task tmp
```

`--strict-mcp-config` is passed with no `--mcp-config`, so no MCP server loads. `--add-dir` covers only the task's image directory.

| Level | `<T>` | Selected by | Class |
|---|---|---|---|
| `none` | `""` | S1 = `none`; S7 | S |
| `read_only` | `Read,Grep,Glob` | S1 = `read_only` (default); S2 to S6 | S once AG-23 proves path confinement, else M |
| `workspace_write` | `Read,Grep,Glob,Edit,Write` | S1 = `workspace_write` with no lowering state; S9 for `workspace_exec` without L2 | S once proven, else M |
| `workspace_exec` | `Read,Grep,Glob,Edit,Write,Bash` | S1 = `workspace_exec` with no lowering state | M (needs AG-14) |

**One row per Claude permission mode:**

| `--permission-mode` | Koda state that selects it | Argv | Why |
|---|---|---|---|
| `dontAsk` | Every state, at every level | the block above | Denies anything not pre-approved; the level is expressed only by `--tools`/`--allowedTools`. |
| `default` (alias `manual`) | None | not emitted; `validate_args` refuses it once AG-23 narrows the choices to `dontAsk` | Prompts, and headless prompts are denied by `--permission-prompts none`, so it adds nothing over `dontAsk` and is less explicit. |
| `acceptEdits` | None | not emitted | Auto-accepts edits as a mode rather than through the explicit list; `workspace_write` already lists Edit and Write. |
| `auto` | None | not emitted | A model classifier approves prompts: an authority other than Koda policy (invariant 1). |
| `plan` | None. Today: S2, S3, S4 and the memory extractor (C1) | not emitted | Replaced by explicit `read_only`/`none` tool lists; one mode keeps one semantics across versions. |
| `bypassPermissions` | None. Today: every other turn (C1) | not emitted; `--restricted` also refuses it | Invariant 1. |

Never emitted at all: `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`, `--mcp-config`, `--setting-sources`, `--settings`, `--plugin-dir`, `--plugin-url`, `--agents`, `--bare` (it reads only `ANTHROPIC_API_KEY`, so subscription logins break) and `--append-system-prompt` (the prompt stays off argv). Floor: `none`.

#### 2.3.2 Gemini CLI 0.68.0

**Every level** (attached values only; `validate_args` refuses separate values, because yargs reads a separate value that starts with `-` as an option, VALIDATION_REPORT WAVE-2B):

```
gemini --model=M --output-format=json|text --extensions=none --approval-mode=<A>
       [--include-directories=<workspace>]        (omitted for S7; a workspace path containing "," is refused)
cwd   = <gemini home>/cwd: empty, mode 0500, recreated before every spawn (§2.3.5)
stdin = <system_instructions>…</system_instructions><user_request>{escaped query}</user_request>
env   : HOME = the agent's Gemini home; GEMINI_CLI_TRUST_WORKSPACE=true; TMPDIR = the task tmp;
        pinned: GEMINI_SYSTEM_MD=false, GEMINI_TELEMETRY_ENABLED=false, GEMINI_TELEMETRY_LOG_PROMPTS=false,
                GEMINI_TELEMETRY_OTLP_ENDPOINT="", OTEL_EXPORTER_OTLP_ENDPOINT="",
                GOOGLE_GEMINI_BASE_URL=<the configured gateway or "">, GOOGLE_VERTEX_BASE_URL="",
                GEMINI_API_KEY, GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION = configured value or ""
settings: <gemini home>/.gemini/settings.json, written by Koda (0600) before every spawn; no system settings file
```

- **Why the workspace is not the cwd.** Gemini reads workspace settings and walks to `.env` files only from the cwd (§1.2). With an empty, Koda-owned cwd, a planted or repository-supplied `.gemini/settings.json`, `.gemini/.env` or `.env` in the workspace is never read, whatever its content (`context.includeDirectories`, hooks, MCP servers, discovery commands, telemetry, a base URL or a system prompt). The cwd's ancestors are the per-agent home (rebuilt) and Koda's runtime root, which L2 grants to no confined process and which is never under `/tmp` (AG-12). The pins are defence in depth: `.env` never overrides a variable that is already set (§1.2).
- **Why trust comes from the env.** Headless Gemini refuses an untrusted cwd. `--skip-trust` trusts only after the first settings load, so trust would change within a run when the 10 s settings cache expires (§1.2). `GEMINI_CLI_TRUST_WORKSPACE=true` makes every load see the same, trusted, empty cwd.
- **Fail closed on settings.** A stderr line `Invalid configuration in` or `Security Warning: Skipping` fails the spawn (A-G-09). At each worker start, per CLI fingerprint, the load probe of A-K-05 must pass, or Gemini is unavailable. No file needs root ownership, so the same design works on native installs.
- The non-streaming runner uses `json` and the streaming runner `text`, as today (`gemini_runner.py:351, 525`).

Koda-written user settings (`security.auth.selectedType` is added from the provider connection when file OAuth is used):

```json
{
  "tools": { "core": ["<per level>"], "discoveryCommand": "", "callCommand": "" },
  "mcpServers": {},
  "hooksConfig": { "enabled": false },
  "skills": { "enabled": false },
  "experimental": { "enableAgents": false, "autoMemory": false },
  "security": { "disableYoloMode": true },
  "telemetry": { "enabled": false, "logPrompts": false },
  "privacy": { "usageStatisticsEnabled": false },
  "context": { "loadMemoryFromIncludeDirectories": false },
  "advanced": { "ignoreLocalEnv": true },
  "general": { "enableAutoUpdate": false }
}
```

`security.disableYoloMode` is `false` only at `workspace_exec`. No `admin.*` key is written, because Gemini ignores it from files.

| Level | `--approval-mode=` | `tools.core` | Selected by | Class |
|---|---|---|---|---|
| `none` | `default` | `[]` (no built-in tool registers, §1.2) | S1 = `none`; S7 | S |
| `read_only` | `default` | `list_directory, read_file, grep_search, glob` | S1 default; S2 to S6 | S once AG-25 proves path confinement, else M |
| `workspace_write` | `auto_edit` | the above plus `replace, write_file` | S1 = `workspace_write`; S9 for `workspace_exec` without L2 | S once proven, else M |
| `workspace_exec` | `yolo` | the above plus `run_shell_command` | S1 = `workspace_exec` | M (needs AG-14) |

**One row per Gemini approval mode:**

| Mode | Koda state that selects it | Argv | Why |
|---|---|---|---|
| `default` | `none` and `read_only` levels: S1, S2 to S7 | `--approval-mode=default` | In headless mode any tool that would ask is denied, so only the allowlisted read tools run. |
| `auto_edit` | `workspace_write` | `--approval-mode=auto_edit` | Edit tools are auto-approved; no shell tool is registered. |
| `yolo` | `workspace_exec` only | `--approval-mode=yolo` | Every registered tool is approved; refused by `security.disableYoloMode` at every other level (verified offline). |
| `plan` | None. Today: S2, S3, S4 (C3) | not emitted | Read-only by mode rather than by registry, adds plan-mode tools and reroutes the `auto` model to Pro. |
| `-y/--yolo` (alias) | None | not emitted | Same as `yolo`; one spelling only. |
| `-s/--sandbox` (Gemini's own container sandbox) | None | not emitted | Needs docker or podman inside the runtime image. |

Never emitted: `--prompt`/`-p` (the prompt goes on stdin), `--skip-trust`, `--allowed-tools`, `--allowed-mcp-server-names`, `--policy`, `--admin-policy`, `--resume`, `--session-file`, `--session-id`, `--raw-output`, `--accept-raw-output-risk`, `--worktree`, `--debug`, `--acp`. Gemini 0.68.0 has native resume, but Koda keeps Gemini stateless with transcript replay (M3-E5-T1). Floor: `none`.

**GEMINI.md.** No 0.68.0 setting turns it off (§1.2). With the workspace out of the cwd and `loadMemoryFromIncludeDirectories=false`, no workspace GEMINI.md enters the startup context, and the home's is removed by the rebuild. But whenever a read tool reads a file inside the workspace, JIT discovery appends the GEMINI.md files on its path to that tool's output. So at `read_only` and above, residual R-7 applies to Gemini whatever OQ-3(b) decides; at `none` nothing reads.

**Prompt channel.** System instructions stay on stdin, because `GEMINI_SYSTEM_MD` replaces the CLI's whole built-in prompt (§3); it is pinned to `false`, the built-in prompt. The query is escaped so that `<` and `>` inside a tag-like sequence that matches either delimiter become `&lt;` and `&gt;`, so user text cannot close `<user_request>` or open `<system_instructions>`.

#### 2.3.3 Codex 0.169.0

**Every level, new turn:**

```
codex exec --json --cd <dir> --model M [--skip-git-repo-check]
  --ephemeral --ignore-rules
  --disable <F>   for every F in the 0.169.0 disable set below
  -c agents.enabled=false -c skills.include_instructions=false -c skills.bundled.enabled=false
  -c approval_policy="never"
  -c shell_environment_policy.inherit="core"
  -c shell_environment_policy.exclude=["*_API_KEY","*TOKEN*","*SECRET*","POSTGRES*","KNOWLEDGE_V2_S3*"]
  -c mcp_servers={} -c web_search="disabled" -c project_doc_max_bytes=0
  <level flags, below>
  [-c model_reasoning_effort=E] [--image P …] -
<dir> = the workspace; for S7 internal calls, a fresh empty per-task dir
env: HOME = CODEX_HOME = the agent's Codex home (XDG_* inside it); TMPDIR = the task tmp;
     developer instructions in its Koda-written config.toml (0600)
```

`web_search="disabled"` replaces `tools.web_search=false`; both keys exist, and the enum key is unambiguous. Developer instructions move off argv (today `-c developer_instructions=…`, `codex_runner.py:171-174`) into the Koda-written `config.toml`; `--ignore-user-config` is therefore not used.

**Reviewed feature set (0.169.0).** Every default-on feature that adds a tool, a browser, a sub-agent, a process, a plugin or skill install, or an approval authority other than Koda is disabled at every level (32): `apps`, `auth_elicitation`, `browser_annotation_api`, `browser_use`, `browser_use_external`, `browser_use_full_cdp_access`, `computer_use`, `daemon_auto_start`, `goals`, `guardian_approval`, `guardian_include_additional_context`, `guardian_reuse_parent_compaction`, `hooks`, `image_generation`, `in_app_browser`, `in_app_chat`, `in_app_dictation`, `in_app_local_automation`, `in_app_updates`, `in_app_voice`, `mcp_oauth_refresh_coordination`, `multi_agent`, `plugin_sharing`, `plugins`, `remote_plugin`, `shell_snapshot`, `skill_mcp_dependency_install`, `skill_search`, `tool_call_mcp_elicitation`, `tool_suggest`, `view_image` (it reads any image path outside the shell's sandbox) and `workspace_dependencies`. Below the shell levels `shell_tool` is disabled too. The features left enabled form the reviewed keep list (38 at `none`, plus `shell_tool` at shell levels): model, protocol, budget and display switches (`api_key_cyber_access_programs`, `api_key_model_discovery`, `bedrock_setup_wizard`, `cli_daybreak`, `compaction_image_budget`, `content_item_kinds`, `deferred_tool_world_state`, `enable_request_compression`, `fast_mode`, `incremental_tools`, `incremental_tools_legacy_gcp`, `mentions_v2`, `prediction_preserve_parent_tools`, `reasoning_effort_override`, `retain_client_tool_outputs`, `system_proxy_fallback`, `ultrafast_mode`, `unbounded_connection_retries`, `unified_image_budget`, `untrusted_as_tool_output`, `write_stdin_approval`); the code-mode host, a JavaScript orchestrator with no filesystem or network of its own (`code_mode_host`, `code_mode_host_grpc`, `code_mode_host_output_truncation`, `code_mode_interrupt`); `sleep_tool`; the shell implementation, which exposes nothing without `shell_tool` (`unified_exec`, which cannot be disabled, and `unified_exec_tty`); and removed features that still report `true` (`collaboration_modes`, `item_ids`, `realtime_conversation`, `resize_all_images`, `sqlite`, `steer`, `terminal_resize_reflow`, `tool_search_always_defer_mcp_tools`, `tui_app_server`, `worktrees`). A-K-02 fails when `features list` shows any other enabled feature, so a version bump that adds a default-on feature stops the build until it is reviewed.

**Compile rule.** `IP(mode)` is the inner-sandbox probe `codex sandbox -c sandbox_mode="<mode>" [the row's workspace-write keys] -- <python> -c <probe>`, run **through the same launcher and confinement profile as the spawn** (`koda-sandbox-exec` with the Codex profile under L2; directly under `off`). It passes when the probe exits 0, a write outside the writable roots fails and a socket fails. It runs at worker start, is cached per CLI fingerprint and profile, and is shown in health and in the spawn event. `L2` means confinement status `enforced` or `filesystem_only` (§2.4). An inner sandbox mode is selected only when its `IP` passed in that profile (A-X-10).

| Effective level | L2 on | L2 off (`off`) |
|---|---|---|
| `none` | `--sandbox read-only --disable shell_tool` | same |
| `read_only` | `IP(read-only)` fails inside L2 on 0.169.0 → not faithful → `none`. A later pin whose `IP` passes there gets `--sandbox read-only` with the shell. | not faithful → `none`: the inner read-only sandbox reads every file the uid can read (§1.2), so it does not confine reads to the workspace |
| `workspace_write` | `IP(workspace-write)` fails inside L2 → `none` | `IP` ok: `--sandbox workspace-write -c sandbox_workspace_write.network_access=false` `-c sandbox_workspace_write.exclude_slash_tmp=true -c sandbox_workspace_write.exclude_tmpdir_env_var=true -c sandbox_workspace_write.writable_roots=["<task tmp>"]`; `IP` failed: `none` |
| `workspace_exec` | `IP(workspace-write)` ok inside L2: the off-mode row with `network_access=true`; failed (0.169.0): `--sandbox danger-full-access`, with L2 enforcing the workspace and the TCP ports | `IP` ok: the `workspace_write` row with `network_access=true`; `IP` failed: `none` |

So on 0.169.0 under the defaults `strict` and `filesystem`, Codex has two working levels: `none` (it answers with no shell and no file reads) and `workspace_exec`. `danger-full-access` is emitted only under L2, so in `off` no Codex level is weaker than today. At `none`, `apply_patch` stays in the tool list (there is no switch for it on 0.169.0); `--sandbox read-only` with `approval_policy="never"` refuses the patch `[I]` (AG-24 live check), and under L2 the workspace is read-only at `none`, so a patch cannot land either way. Codex at `none` is class S; with a shell it is class M.

**Resume.** `exec resume` takes no `--sandbox`, and whether it honours `-c sandbox_mode` is unproven. Native resume is off: Codex declares `supports_native_resume=False`, and follow-ups get transcript replay (M3-E5-T1, Q-13). `--dangerously-bypass-approvals-and-sandbox` is never emitted and leaves the contract. If AG-24's live check later proves `exec resume -c sandbox_mode="<S>"`, the contract adds `sandbox_mode` for the `exec_resume` scope and resume returns.

**One row per Codex sandbox and approval-policy pair:**

| # | `sandbox_mode` | `approval_policy` | Koda state that selects it | Argv |
|---|---|---|---|---|
| 1 | `read-only` (shell disabled) | `never` | Effective `none`: S1 = `none`; S7; `read_only` (S1 default, S2 to S6) clamped by S8 on 0.169.0; `workspace_write` under L2 clamped by S8 | the block above with `--sandbox read-only --disable shell_tool` |
| 2 | `workspace-write` | `never` | Effective `workspace_write` under `off` with `IP` ok | `--sandbox workspace-write` with `network_access=false`, both tmp excludes and `writable_roots=["<task tmp>"]` |
| 3 | `workspace-write` + network | `never` | Effective `workspace_exec` under `off` with `IP` ok; under L2 only when `IP(workspace-write)` passed inside the L2 profile (never on 0.169.0) | row 2 with `network_access=true` |
| 4 | `danger-full-access` | `never` | Effective `workspace_exec` under L2 when `IP` fails inside the profile (always on 0.169.0). Today: every non-dry-run turn (C2) | `--sandbox danger-full-access` |
| 5 | `read-only` | `on-request` | None | not emitted; AG-24 narrows the contract's `approval_policy` choices to `never` |
| 6 | `workspace-write` | `on-request` | None | not emitted |
| 7 | `danger-full-access` | `on-request` | None | not emitted |
| 8 | `read-only` | `on-failure` | None | not emitted |
| 9 | `workspace-write` | `on-failure` | None | not emitted |
| 10 | `danger-full-access` | `on-failure` | None | not emitted |
| 11 | `read-only` | `granular` | None | not emitted |
| 12 | `workspace-write` | `granular` | None | not emitted |
| 13 | `danger-full-access` | `granular` | None | not emitted |
| 14 | `read-only` | `untrusted` | None (0.169.0 refuses it at config load) | not emitted |
| 15 | `workspace-write` | `untrusted` | None (refused by the CLI) | not emitted |
| 16 | `danger-full-access` | `untrusted` | None (refused by the CLI) | not emitted |
| 17 | (no sandbox) | `--dangerously-bypass-approvals-and-sandbox` | None. Today: resume in danger mode (C2) | not emitted; removed from the contract |
| 18 | `workspace-write` (forced by the flag) | `--approve-for-me` (automatic review) | None | not emitted |

`read-only` with the shell enabled (row 1 without `--disable shell_tool`) has no selecting state on 0.169.0; it is today's dry-run argv and the memory extractor's (C2). Rows 2 and 3 differ only in `network_access`. Today an operator could select rows 5 to 16 through `CODEX_APPROVAL_POLICY` (`codex_runner.py:175-176`); AG-24 stops reading that setting.

Why only `never`: `exec` is headless, so any policy that asks has nobody to ask; `on-request` and `granular` hand the decision to the model or to categories Koda does not govern, and `--approve-for-me` routes approvals to an automatic reviewer, which is an authority other than Koda policy (invariant 1). Never emitted either: `--trust` (it would load the workspace's config layer and persist trust) and `--dangerously-bypass-hook-trust`.

#### 2.3.4 HTTP providers

Ollama, llama.cpp, MLX and the OpenAI-compatible providers have no built-in tools; the field does not apply and the UI shows "não se aplica". Their ignored `permission_mode` and `dry_run` parameters are removed. Their `tool_calls` already go through the dispatcher and policy (`_run_agent_loop`). D-147 stays a separate item.

#### 2.3.5 Persistent instructions and extensions

A model with write access, or a shell, can plant files that a later spawn loads automatically. Koda closes the places where that happens:

- **Provider homes** are per agent and rebuilt before every spawn from an allowlist; everything else is removed:

  | Provider | Kept | Removed (examples) |
  |---|---|---|
  | Claude | `.credentials.json` (file OAuth only); `projects/<slug>/*.jsonl` session transcripts (needed for `--resume`) | `CLAUDE.md`, `settings*.json`, `skills/`, `agents/`, `commands/`, `plugins/`, `projects/*/memory/`, `.claude.json` (rewritten minimal) |
  | Codex | `auth.json` (file OAuth only); Koda's `config.toml`, rewritten | `AGENTS.md`, `rules/`, `skills/` (with `.system`), `.agents/`, `hooks.json`, `sessions/`, `shell_snapshots/`, `.env` |
  | Gemini | `.gemini/oauth_creds.json`, `.gemini/google_accounts.json` (file OAuth only); Koda's `.gemini/settings.json`, rewritten; `cwd/`, recreated empty | `GEMINI.md`, `.env`, `.gemini/.env`, `.gemini/extensions/`, `.gemini/skills/`, `.gemini/commands/`, `.gemini/policies/`, `.gemini/trustedFolders.json`, `.gemini/tmp/`, `.agents/` |

- **Workspace customisation** is not loaded:
  - Claude: `--safe-mode` (CLAUDE.md, skills, plugins, hooks, MCP, commands, agents) and `--restricted` (project settings).
  - Codex: `project_doc_max_bytes=0` (workspace AGENTS.md), skills off (workspace `.agents/skills` and `.codex/skills` included), `--ignore-rules`, the reviewed feature set, and no `--trust`, so the workspace `.codex/config.toml` is not loaded (all `[V]` offline, §1.2).
  - Gemini: the workspace is never the cwd, so its `.gemini/settings.json` and `.env` files are never read; extensions off by `--extensions=none`; hooks, skills, sub-agents and MCP off in the user settings; GEMINI.md as described in §2.3.2.

Executable customisation (hooks, MCP servers, plugins, extensions, rules, skills, discovery commands) would run code at `read_only` and must stay off for the levels to mean anything. Instruction files (CLAUDE.md, AGENTS.md, GEMINI.md) only steer the model; turning them off removes a feature users may rely on. Both are operator question OQ-3. If the operator keeps instruction files, Claude omits `--safe-mode`, Codex omits `project_doc_max_bytes=0`, and Gemini sets `context.loadMemoryFromIncludeDirectories=true`; residual R-7 then applies to all three. Executable customisation stays off for Claude without `--safe-mode`: `--restricted` ignores the settings files that define hooks and enable plugins, the home rebuild removes installed plugins, `--disable-slash-commands` turns off skills and commands, `--strict-mcp-config` turns off MCP, and custom agents need the Agent tool, which is never in `--tools` (`[I]`, covered by the live canaries).

Live canaries (§5.3) cover each kept and removed item, in the workspace, in the provider home and, for Gemini, in every ancestor of the cwd.

### 2.4 Confinement

#### 2.4.1 Threat and classes

**Threat.** A prompt-injected model drives built-in tools, governed shell or git, MCP servers and media tools. At risk: the master key, the previous key and `bootstrap.txt`; the worker env (DSN, S3 secret, granted secrets, runtime tokens); other agents' workspaces, homes and sessions; kernel RPC, the sidecars and publish integrity.

| Class | Members | If a required layer is missing |
|---|---|---|
| **M**: runs model-directed code | governed shell, `shell_bg` and git; worker-side git on workspaces; Codex at any level with a shell; Claude and Gemini at `workspace_exec`; any CLI level not proven self-confined; `cli_runner.py` spawns | Provider levels clamp to the highest class S level (S9); governed processes are refused (from AG-14 on), with a reason pointing to `koda doctor` |
| **S**: self-confined CLI level | Claude `none`, `read_only`, `workspace_write`; Gemini levels below `workspace_exec`, once proven; Codex `none` | Runs with the available layers |
| **U**: untrusted input, operator-installed code | MCP stdio servers, yt-dlp, ffmpeg, ffprobe, Playwright chromium | Runs with a minimal env and a health warning |
| **T**: trusted | Login flows in `app`, with an explicit allowlist and reasons | Not confined; HOME is the app-only login home (§2.4.4) |

#### 2.4.2 Layers

- **L0 Placement** (host-independent):
  - `koda-state` is mounted only in `app` (AG-19). The master key, the previous key and `bootstrap.txt` never enter `runtime-kernel`, and the key never moves.
  - Worker data moves to a new `koda-worker-state` volume (`WORKER_STATE_ROOT`), mounted in both `app` and `runtime-kernel`; every C14 consumer resolves through it in both processes. The supervisor forwards `WORKER_STATE_ROOT` instead of `STATE_ROOT_DIR` (`supervisor.py:92`).
  - CLI login homes move off `koda-runtime` to the app-only path (§2.4.4).
  - No Koda state or temporary file lives in a directory other users or agents share: `RUNTIME_EPHEMERAL_ROOT` defaults to `~/.koda-runtime/<bid>` (mode 0700) on native installs instead of the system temp dir, the compose kernel root moves to `/var/lib/koda/runtime/kernel`, and Docker MCP env files are written into a 0700 per-worker directory and deleted once the container has started (AG-03, AG-12).
- **L1 Process hygiene:** AG-04 (implemented) makes the worker and the kernel non-dumpable with no cores. One allowlist builder makes every child env, with no DSN, S3 secret, granted secrets, runtime, kernel or broker token; it sets HOME and the `XDG_*` directories to the child's own home and `TMPDIR` to the task tmp; this covers MCP and media spawns (AG-03). Prompts stay off argv, because `/proc/*/cmdline` stays readable even under Landlock `[I]`.
- **L2 OS confinement.** One Rust primitive, `rust/koda-runtime-kernel/src/confinement.rs`, exposed as the `koda-sandbox-exec` binary in the existing crate (no new service, ADR-001):
  - It applies `no_new_privs`, then a Landlock filesystem ruleset, then at ABI ≥ 4 TCP rules (connect only to `RUNTIME_CONFINEMENT_EGRESS_PORTS`, default `443,53`, plus the port of the provider's configured base URL; no bind), then at ABI ≥ 6 signal and abstract-UNIX-socket scoping, so a confined process cannot kill the worker or the kernel or reach their abstract sockets. Then it execs.
  - Landlock's ptrace restriction stops reads of the unconfined worker's and kernel's `/proc/<pid>/environ` and `mem`, and of sibling domains, on every ABI.
  - It exits 126 if any requested right cannot be enforced. Nesting only narrows. A process inside it cannot change mount topology, which is why Codex's bubblewrap sandboxes cannot start there (§1.2).
  - **What it does not cover:** TCP rules are per port, so the allowed ports reach every host, and an internal service listening on 443, 53 or the provider port is reachable; UDP is not restricted (DNS and other UDP egress stay open); connecting to a pathname UNIX socket is not a Landlock right. So under `strict` the kernel listens on TCP only, and a UNIX-socket kernel target is refused at start (M1-E6-T1 constraint, §9.3).
  - Both spawn paths exec through it: worker-side spawns through `koda/security/process_confinement.py` (AG-14), and kernel `StartTask` and `ExecuteCommand`, whose profile the kernel computes itself (AG-15).
  - A workspace grant is refused when the work dir is, or contains, a shared or Koda-owned directory: `/tmp`, `/var/tmp`, `/dev/shm`, the system temp dir, HOME, a state root, `RUNTIME_EPHEMERAL_ROOT`, `RUNTIME_KERNEL_ROOT`, a provider home or a login home (AG-12 predicate, checked again by AG-14).

  Allowlist (anything else is denied, including worker-state, the artifact root, `/app`, `/workspace`, shared HOME, other agents' workspaces and homes, the login homes, and the `tmp_images` root):

  | Grant | Provider CLI | Governed shell and git | MCP stdio | Media tools | Chromium |
  |---|---|---|---|---|---|
  | read-only: `/usr`, `/lib*`, `/bin`, `/sbin`, `/etc`, `/opt`, `/proc`, required `/dev` nodes; `CODEX_BIN`/`GEMINI_BIN` must resolve inside these | yes | yes | yes | yes | yes |
  | read-write: task tmp | yes | yes | yes | yes | yes |
  | workspace | read-only at `none` and `read_only`, else read-write | read-write | only if the server declares it | no | no |
  | own per-agent provider home, read-write (Gemini's `cwd/` inside it is mode 0500) | yes | no | no | no | no |
  | other | — | — | server package read-only; state dir read-write | input read-only; output dir read-write | browsers path read-only; profile read-write |

- **L3 Provider layer (inner):** Claude `--restricted --safe-mode` and its tool lists; Codex's reviewed feature set and, only where `IP` proved it inside the same profile, its inner sandbox; Gemini's `tools.core` and user settings. Per-agent homes live under `<RUNTIME_EPHEMERAL_ROOT>/provider-homes/<agent>/{claude,codex,gemini}` and are rebuilt per §2.3.5. A work dir is never HOME and never contains a provider home or a state root, checked by path component; this also applies to `agent_set_workdir` (`tool_dispatcher.py:1404-1416`) and to internal calls (S7).
- **L4 RPC:** kernel RPC authentication (M1-E6-T1) is a prerequisite for AG-15, which adds per-worker kernel tokens: the kernel binds each `StartTask` and `ExecuteCommand` to the token's agent and computes the floor itself (that agent's workspace, its provider home and the task tmp); a caller profile can only narrow it; a request without a profile is rejected. The control-plane worker broker (AG-17) has its own per-worker token.

#### 2.4.3 Modes

One setting, `RUNTIME_CONFINEMENT`, in `config.py` and `.env.example`.

| Mode | Required for class M | Use |
|---|---|---|
| `strict` (default) | filesystem + ptrace + TCP (ABI ≥ 4, kernel ≥ 6.7) | Normal |
| `filesystem` | filesystem + ptrace (ABI ≥ 1, kernel ≥ 5.13) | Explicit operator choice; audit event and a persistent health banner. Internal TCP ports stay reachable until M5-E5. |
| `off` | nothing; each provider's own restriction is the only layer (§2.3) | Development, macOS or native installs. Explicit config, a red banner that states R-8, a startup log line and `confinement=off` in every spawn event. The installer never writes it. Every class M process reads every file the uid can read (R-8). |

The status (`enforced | filesystem_only | unavailable`, the ABI and the scoping flags) is computed at worker start and shown in health, `koda doctor` and the spawn event. `koda-sandbox-exec --self-test` settles what a host supports, including Docker's seccomp `[I]`.

**Compose** (`docker-compose.yml`, `packages/cli/release/bundle/docker-compose.release.yml`, `packages/cli/release/CHECKSUMS.txt`): AG-19 removes `koda-state` from `runtime-kernel` and adds `koda-worker-state` to both services. AG-19b adds `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]` and, after the smoke test, `read_only: true` with a tmpfs `/tmp`. No user-namespace or seccomp relaxation, no bwrap, no uid split, no new container.

#### 2.4.4 Provider credentials and login homes

- **Env credentials** where the provider supports a non-rotating token (API keys, Claude's long-lived `setup-token`): delivered in the CLI env by the allowlisted builder; nothing is written to the home.
- **File OAuth** (Claude `.credentials.json`, Codex `auth.json`, Gemini `oauth_creds.json` and `google_accounts.json`; the same names D-230 deletes, `manager.py:1575-1580`):
  - The canonical login homes move from `koda-runtime` (`docker-compose.yml:29-31`, mounted read-write by `runtime-kernel` at `:250`) to `STATE_ROOT_DIR/provider-logins/<provider>` on `koda-state`, which becomes app-only with AG-19. Class T login flows run with that HOME. The move copies and verifies; the old copies go one release later (AG-32). Operator question OQ-4.
  - Before a spawn, the worker checks the credential file out through the AG-17 broker (`POST /internal/provider-credentials/{provider}/checkout`, per-worker token) and writes it into the per-agent home (0600). After the run it checks it in. The control plane accepts only the named files, parses them as JSON against a per-provider schema (known keys, size limit, same account id, expiry not earlier than the canonical copy), and writes them under a per-provider lock. Config, hooks and instruction files never cross, because nothing else is transferred.
  - Whether concurrent refresh-token rotation survives this needs live evidence (O-4). If it does not, file OAuth modes require env credentials under confinement.

### 2.5 Secrets and the master-key boundary

#### 2.5.1 Key handling (AG-05, implemented)

- Only `app` holds the key: the control plane and the supervisor.
- No process creates a key implicitly. `ensure_master_key()` runs at supervisor start (`supervisor.py:223`) and ends in `fresh_install`, `upgrade`, `lost_key_reset`, `verified` or `rotation`; anything else refuses to start with operator guidance (C10). On upgrade, the control plane refuses to start when the key decrypts none of the newest stored values, unless the operator writes the new key's fingerprint prefix to `.master.key.accept-undecryptable` next to the key; that file is removed once used.
- The acknowledgement file and the previous-key file sit next to the key on `koda-state`; with AG-19 they become app-only with it. `CONTROL_PLANE_MASTER_KEY_PREVIOUS` is an `app` env value and never reaches a worker (AG-03).
- The fingerprint outcome audit event is `security.master_key_fingerprint_recorded`.
- ADR-026: the relocation step is superseded; the volume stops being mounted in `runtime-kernel`, the key stays put. Rotation (M5-E6-T11) and backups (M2-E6-T1) are unchanged.

#### 2.5.2 Workers never decrypt (AG-17)

- Static granted secrets are still decrypted by the control plane into the spawn env.
- Dynamic needs go through internal broker routes on the existing control-plane API: MCP connection env, MCP OAuth access tokens (refresh and write-back in the control plane only), the squad admin check (only the result returns), the ElevenLabs key, the image-generation key, CLI credential checkout and check-in (§2.4.4) and approvals (§2.9.2).
- Route auth: a per-worker token, minted by the supervisor at spawn, stored as a hash in Postgres (ADR-011), bound to `agent_id`, rotated on respawn, rate-limited; every resolution is audited by id, never value. The token never enters a child env (AG-03), the worker is non-dumpable (AG-04), and L2 denies ptrace and `/proc/<worker>/environ` and `mem` to every confined process (D12-14).
- ADR-025 clarification: "workers resolve secret references at start" means resolution by the control plane, into the spawn env or through the broker.

#### 2.5.3 Snapshot integrity (AG-11)

- Published snapshots are HMAC-signed with the ADR-025 HKDF signing key (M1-E6-T3). The MAC covers `agent_id`, `version`, `published_at` and the SHA-256 of the canonical snapshot JSON (governance block included).
- The supervisor verifies before building a worker env: the MAC, that `agent_id` and `version` in the MAC match the row and the agent being spawned (so another agent's signed snapshot is refused), and that the version is not lower than the highest version it has verified for that agent since it started (rollback while `app` runs is refused). On a failure it does not spawn and emits `security.snapshot_rejected`.
- Versions published before AG-11 carry no MAC. At control-plane start, AG-11 republishes each agent's unsigned latest version unchanged and signed (actor `system:migration`, the AG-21 primitive), trusting the row as it is at upgrade, as today.
- **What the MAC protects, and from when.** It stops a holder of the owner-role DSN who cannot compute the signing key. Until AG-17 (workers stop loading the master key to decrypt) and AG-19 (`koda-state` leaves `runtime-kernel`) both ship, a worker can read the key material and forge a MAC (R-5).
- A DSN holder can still, across an `app` restart, delete newer version rows or point `desired_version` at an older signed version (`manager.py:12600-12607`; `supervisor.py:459`). That is residual R-5, closed by M1-E2-T5 (the worker role gets no write on `cp_*` tables). A persisted high-water mark was rejected: restoring an older database backup would then refuse every agent.
- Live worker reads of `cp_mcp_tool_policies` (`services/execution_policy.py:127-165`) move into the snapshot (O-5).

#### 2.5.4 Documented residuals

| # | Residual | Closed by |
|---|---|---|
| R-1 | The CLI's own credential is readable by the model: through any shell (Codex `workspace_write` under `off` and `workspace_exec`; Claude and Gemini at `workspace_exec`), and at `read_only` and `workspace_write` through Claude's Read or Gemini's `read_file` (`/proc/self/environ`, the provider-home credential files) until AG-23 and AG-25 prove the file tools' path confinement. Codex at `none` has no read. The UI says so and recommends scoped API keys. | Path confinement live checks (AG-23, AG-25) for the read levels; never for shell levels |
| R-2 | AG-04's startup window: a same-uid process can read a starting worker's env and can kill the worker to reopen it. | L2 for every spawn: AG-14, AG-15, AG-16 together. Never under `off`, nor for class U on hosts without L2. |
| R-3 | The worker process, including in-process plugin code (D-005), holds the DSN. | M1-E2-T5, M1-E4-T4 |
| R-4 | Approvals: a DSN holder can reset `uses` on a real grant (replaying a call a human approved, same fingerprint); any code holding the worker's broker token, such as in-process plugin code, can relay a Telegram decision the control plane cannot verify; until AG-17 and AG-19 ship, a worker can also compute a grant MAC and insert a grant directly. | M1-E2-T5 (no write on approval tables); M1-E4-T4 (plugins); AG-17 + AG-19 (MAC forgery) |
| R-5 | Snapshot rollback across an `app` restart by a DSN holder; until AG-17 and AG-19 ship, a worker can also forge a snapshot MAC. | M1-E2-T5; AG-17 + AG-19 |
| R-6 | UDP egress, the provider base-URL port to any host, and internal services on 443, 53 or that port, are reachable from class M under `strict`. | Not closed by this ADR; documented in `docs/security/threat-model.md` (AG-31) |
| R-7 | Instruction files steer later turns. Gemini 0.68.0 appends the workspace GEMINI.md files on the path of every file a read tool reads (§2.3.2), at `read_only` and above, whatever OQ-3(b) decides. For Claude and Codex, and for Gemini's startup context, only if OQ-3(b) is declined. | A Gemini version with a switch, recorded by the contract |
| R-8 | Under `off`, every class M process (Codex `workspace_write` and `workspace_exec`, Claude and Gemini `workspace_exec`, governed shell and git) can read every file the worker's uid can read: on native installs the master key, `bootstrap.txt` and every agent's home, sessions and workspace. Codex writes stay inside its writable roots; the others can write wherever the uid can. Codex `read_only` is clamped to `none` for this reason. | L2 (`strict` or `filesystem`); never under `off` |

### 2.6 Audit

Events go to the existing sinks (`control_plane/audit.py:22`, `services/audit.py`). Governance events (2.6.1 and the approval events) are written in the transaction of the action they record, and the action fails if they cannot be written (a `required=True` path in `record_audit_event`).

#### 2.6.1 Opt-in change: `agent.provider_builtin_tools_changed`

Emitted by `publish_agent` whenever the level or the capability ceiling differs from the baseline, including the AG-21 migration and the legacy import.

```json
{
  "event_type": "agent.provider_builtin_tools_changed",
  "agent_id": "string",
  "version": 42,
  "previous_version": 41,
  "from_level": "read_only",
  "to_level": "workspace_exec",
  "from_capability": ["read"],
  "to_capability": ["read", "write", "exec", "egress"],
  "providers": ["claude", "codex"],
  "escalation": true,
  "actor": { "kind": "operator", "id": "7" },
  "confirmed": true,
  "snapshot_signature_id": "string",
  "reason": "publish | migration | import"
}
```

`actor` follows the `koda:actor` schema (§2.2.2).

#### 2.6.2 Other events

1. **Configuration changes:** actor plus before/after diff on `put_section`, `put_execution_policy`, `put_autonomy_policy`, `put_model_policy` (`manager.py:12115, 8652, 8597, 8583`) and on system-settings writes, including `CODEX_BIN` and `GEMINI_BIN` (`manager.py:605, 617`).
2. **`provider.process_spawned`**, one per model-reachable process: agent, task, provider, process class; CLI version and contract id; requested and effective level with clamp reasons; capability; confinement mode, ABI and the enforced layers; the resolved L2 profile (workspace ro/rw, provider home, egress ports); for Codex the `IP` result for this profile and the SHA-256 of the `features list` output and of the Koda-written `config.toml`; for Gemini the SHA-256 and effective tool list of the Koda-written user settings and the result of the settings-warning check; the non-secret flag list (never prompt or query text); `CONTROL_PLANE_ACTIVE_VERSION` and the snapshot signature id.
3. **Provider-reported tool use:** built-in `tool_use` the CLIs report (`claude_runner.py:585-595, 905-906`; Codex JSON events) stored with `source=provider_reported`, arguments redacted and truncated.
4. **Secret broker:** one row per resolution.
5. **Approvals:** `approval.requested`, `approval.resolved` (resolver kind and id, decision, scope, fingerprint; never parameter values), `approval.grant_consumed`, `approval.expired`.
6. **Migration, restore and mode changes:** actor `system:migration` or the operator; `security.snapshot_rejected`; and AG-05's `security.master_key_fingerprint_recorded` (implemented, `crypto.py:336-341`).

### 2.7 Operator UX

Follows `apps/web/AGENTS.md` and `apps/web/CLAUDE.md`. Copy is PT-BR; existing PT-BR text is not translated.

- **Recursos tab**, next to the provider and model choice: a segmented control **"Ferramentas nativas do provedor"** with *Nenhuma / Somente leitura (padrão) / Escrita no workspace / Execução no workspace*. It replaces raw-JSON editing of this key.
- **Effective level per provider** from the resolver: "não se aplica" for HTTP providers, each clamp with its reason, the capability, and the confinement status. For Codex: "O Codex não tem modo somente leitura: em Nenhuma e Somente leitura ele responde sem ferramentas (sem shell e sem leitura de arquivos). Com o confinamento ativo, só Execução no workspace dá ferramentas ao Codex; sem confinamento, Escrita no workspace também."
- **Escalation modal** (§2.8.4 text) whenever the publish diff contains an escalation, including a provider added to the model policy. Only after confirmation does the client send `confirm_escalation=true`. The agent list shows a badge for agents above `[read]`.
- **Pending chat changes:** a model-policy change made in the chat and refused for escalation shows in the agent's draft as "Mudança pedida pelo chat, aguardando confirmação".
- **Execution detail** per turn: effective level, clamps, capability, confinement (from the spawn event) and provider-reported tool uses.
- **System health:** the mode, the ABI, the enforced layers, each CLI's pin match, the Codex `IP` results per profile, the Codex feature review and the Gemini settings load probe. Under `off`, a red banner: "Confinamento desligado: comandos e ferramentas de escrita podem ler qualquer arquivo deste usuário do sistema, incluindo a chave mestra e os dados de outros agentes."
- **Rule simulator:** the existing evaluate endpoint, backed by the runtime engine (`apps/web/src/lib/control-plane.ts:1630` has no consumer today).
- **Approvals panel:** lists the agent's pending requests from Postgres (§2.9.2) with the verbs allow once, allow scope, deny with a reason.

### 2.8 Defaults, migration and rollback (MISSION §13)

#### 2.8.1 Defaults and existing agents (AG-21, AG-30)

- New agents get `read_only`.
- `koda policy audit` (AG-09, read-only) runs before the upgrade and is attached to the release. It has three sections: (1) decision diffs once rules are delivered (legacy matcher versus the engine, ADR-039); (2) per agent on a CLI provider, the built-in tool use seen in traces (provider-reported Write, Edit, Bash; Codex commands); (3) newly live governed calls, meaning every agent and rule that would let `shell_execute`, `shell_bg`, `git_*` or supervised writes run once M3-E3-T1 lands. Section 3 is M3-E3-T1's approval package.
- **Migration (AG-21).** At control-plane start, an idempotent migration gives every published agent whose last published version has no governance block a version N+1 built **from that published snapshot** (never `build_draft_snapshot`, `manager.py:12461`), with `level=read_only`, the ceiling of its providers at `read_only`, actor `system:migration`, and one audit event; it is signed once AG-11 is present. The field is added to the draft only if the draft lacks it. It ships with the gate in AG-21, so publishing is never blocked waiting for another task.
- **Banner (AG-30).** The banner (§2.8.4) lists the agents that previously ran unrestricted; for Codex agents it says that Codex now answers without tools until the operator chooses Execução no workspace. "Restaurar execução no workspace" goes through the confirmed publish; it cannot restore bypass, which no longer exists.

#### 2.8.2 Settings

- **No longer read:** `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` (removed from `config.py`, `startup_validator.py` and the system-settings fields). Their stored values are **not cleared**: they are listed in the release note, and AG-32 deletes them one release later (OQ-7). Startup is not refused because of them. `AGENT_EXECUTION_POLICY_JSON` is removed; AG-09 reports any value found.
- **Changed (AG-02, implemented):** `CODEX_BIN` and `GEMINI_BIN` are each one executable path. A command line reports `unavailable:unverified_cli_version`; a missing binary `unavailable:cli_not_installed`.
- **Changed defaults (AG-12):** native `RUNTIME_EPHEMERAL_ROOT` moves from the system temp dir to `~/.koda-runtime/<bid>`; compose `RUNTIME_KERNEL_ROOT` moves from `/tmp/koda-runtime/default/kernel` to `/var/lib/koda/runtime/kernel`. Both hold only ephemeral task files; Claude sessions kept for `--resume` start fresh after the move.
- **New:** `RUNTIME_CONFINEMENT`, `RUNTIME_CONFINEMENT_EGRESS_PORTS`, `WORKER_STATE_ROOT` and `AGENT_WORKSPACE_ROOT`, each in `config.py`, `.env.example` and the docs.

#### 2.8.3 Installs, work dirs and rollback

- **Existing installs (AG-18, AG-19):** the release compose and CHECKSUMS are updated. On first start, `app` copies the worker subpaths from `koda-state` into `koda-worker-state`, verifies checksums and writes a marker (copy, not move); the legacy copies go one release later (AG-32, ADR-018). The key is not touched. The installer preflight runs `koda-sandbox-exec --self-test`; on ABI < 4 it requires the operator to choose `filesystem`, interactively or by flag, and records the choice.
- **Work dirs:** the default becomes `<AGENT_WORKSPACE_ROOT>/<agent_id>`. Files in the old shared HOME stay; the release note says how to reach them.

| Rollback scope | How |
|---|---|
| Per agent | Publish a higher level (confirmed, audited). |
| Per install | `RUNTIME_CONFINEMENT=filesystem`. |
| Per release | The previous images still find `koda-state` with the key, the legacy worker subpaths, the old login homes and the stored `CODEX_*` values. Rolling back **restores the previous ungoverned provider modes** (Claude `bypassPermissions`, Codex `danger-full-access` or the operator's stored value, Gemini `yolo`) **and the previous volume layout**, with the key mounted in `runtime-kernel` again. Changes after the upgrade to skill locks, gateway config, room photos and CLI logins are not carried back (documented). Old code ignores the new field, the governance block, signatures and the approval tables; every migration in this ADR is additive until AG-32. |

#### 2.8.4 Operator migration notice

**Release note and `docs/operations/upgrade.md` section (English):**

> ### Provider built-in tools now follow Koda policy (ADR-002)
>
> Claude Code, Codex and Gemini CLI no longer run with their own approvals turned off. Until this release Claude ran with `bypassPermissions`, Codex with `danger-full-access`, and Gemini in `yolo` mode, so an agent's provider could edit files and run commands without any Koda approval.
>
> **What changes when you upgrade**
>
> - Every agent gets the new setting **Provider built-in tools**, set to **Read only**. On upgrade Koda publishes a new version of each agent from its last published version, so pending drafts are not published. The report `koda policy audit`, which you can run before upgrading, lists the agents that used the provider's own edit or shell tools.
> - At **Read only**, Claude and Gemini can read files in the agent's workspace and do nothing else. **Codex has no read-only mode: at None and Read only it answers without any tools (no shell, no file reads).** With confinement on (the default), Codex gets tools only at **Workspace exec**; with confinement off, also at **Workspace write**.
> - Edits and commands through Koda's own tools (files, shell, git) still ask for approval per call, and work for agents whose policy allows them once M3-E3-T1 is approved.
> - Raising an agent to **Workspace write** or **Workspace exec**, or adding a provider that gains capabilities at the agent's level (for example Codex on an agent at Workspace write), needs a confirmation in the dashboard. Chat commands such as `/provider` and `/model` now publish their change at once; a change that would add capabilities is refused in the chat and waits in the dashboard for confirmation.
> - Chat toggles (voice, `/provider`, `/model`, feature defaults) publish only their own change. They no longer publish other pending dashboard edits.
> - Provider CLIs no longer load hooks, MCP servers, plugins, extensions, skills or rules from the workspace or from their home directory, and no longer load CLAUDE.md or AGENTS.md (subject to operator approval, OQ-3). Gemini no longer loads GEMINI.md at start, but when it reads a file in the workspace it still adds the GEMINI.md files in that file's folders to what it read; Gemini 0.68.0 has no setting to turn this off.
> - Each agent has its own provider home. Logins you made in the dashboard keep working.
> - `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` are no longer read. Their stored values are kept for one release, so that a rollback uses them, and then deleted: {list}. `CODEX_BIN` and `GEMINI_BIN` must each be the path of one executable; a command line such as `npx -y @google/gemini-cli` reports `unavailable:unverified_cli_version`, and a missing binary reports `unavailable:cli_not_installed`.
> - On native installs, Koda's runtime files move from the system temp directory to `~/.koda-runtime`; Claude sessions start fresh once.
> - The control plane refuses to start when the master key does not match this database. If the original key is lost for good, follow `docs/operations/backup-restore.md` (the `.master.key.accept-undecryptable` file).
> - Model-directed processes run under Linux Landlock confinement (`RUNTIME_CONFINEMENT=strict`). On hosts with Landlock ABI below 4 (for example Debian 12 or Ubuntu 22.04 GA kernels) the installer asks you to choose `filesystem`. Below kernel 5.13, governed shell and git are refused and Codex answers without tools.
> - With `RUNTIME_CONFINEMENT=off` (development, macOS, native installs), any command an agent runs, and Codex at Workspace write or Workspace exec, can read every file your operating-system user can read, including the master key and other agents' data.
>
> **How to restore an agent's previous behaviour:** Dashboard → Agents → the agent → Recursos → Ferramentas nativas do provedor → Execução no workspace → confirm → publish. Bypass modes no longer exist.
>
> **Rollback:** the previous images still work with your data. Rolling back restores the previous ungoverned provider modes (bypass, `danger-full-access`, `yolo`) and the previous volume layout, with the master key mounted in `runtime-kernel` again. Changes made after the upgrade to skill locks, gateway config, room photos and CLI logins are not carried back.

**Dashboard banner (PT-BR), shown to operators until dismissed:**

> **As ferramentas nativas dos provedores agora seguem a política do Koda.** Nesta atualização, {n} agentes que usavam Claude, Codex ou Gemini com acesso irrestrito passaram para **Somente leitura**. Edições e comandos feitos pelas ferramentas do próprio provedor ficam bloqueados até você escolher outro nível; o Codex responde sem ferramentas até Execução no workspace. As ferramentas do Koda (arquivos, shell e git) continuam pedindo aprovação por chamada. [Ver agentes afetados] [Revisar política]

Per affected agent: "{agente} · {provedor} · antes: irrestrito · agora: Somente leitura{, sem ferramentas no Codex} · [Restaurar execução no workspace]".

**Escalation modal (PT-BR):**

> **Confirmar elevação para {nível}?** Com esta mudança, sem aprovação por chamada, o modelo poderá: {editar arquivos do workspace} {executar comandos} {acessar a rede por HTTPS} {ler a credencial do provedor usada por esses comandos}. {Com o confinamento desligado, os comandos poderão ler qualquer arquivo deste usuário do sistema, inclusive a chave mestra.} {Com o confinamento ativo, o Codex só tem ferramentas em Execução no workspace; neste nível ele responde sem ferramentas.} A mudança fica registrada com o seu usuário. [Cancelar] [Confirmar e publicar]

Only the capabilities the escalation adds are listed; the `off` sentence appears only under `off`, and the Codex sentence only when Codex is among the agent's providers, the level is below `workspace_exec` and L2 is on.

### 2.9 Governed path: per-call authorisation (D-011) and cross-process approvals (D-012)

M3-E3-T1 and M3-E3-T2 implement this section. The flow is ADR-009's: decision, then request, then a fingerprinted grant, then execute.

#### 2.9.1 D-011: `ExecutionAuthorization`

- **Object.** A frozen dataclass in `koda/utils/approval.py`: `agent_id`, `task_id`, `tool_id`, `command_digest` (SHA-256 of the exact command string, or of the git argument string), `work_dir`, `basis` (`policy_allow | human_grant | operator_command | scheduled_job`), `rule_id`, `grant_id`, `snapshot_version`, `nonce`, `expires_at` (mint time plus the call's timeout).
- **Minted** only by `authorize_call(evaluation, call, ctx, grant=None)`, called in `_execute_tool_traced` after the policy decision (`tool_dispatcher.py:732-770`):
  - `deny` → never;
  - `allow` → `policy_allow`, with the matched `rule_id`;
  - `require_approval` or `allow_with_preview` → only with a grant consumed through the control plane for this call (§2.9.2) → `human_grant`;
  - supervised mode: a write call (`_is_write_tool`) needs `human_grant` even when the rule allows it, which replaces the contextvar check at `tool_dispatcher.py:779-790`;
  - dry run and the S2 to S6 ceilings keep refusing writes (`tool_dispatcher.py:791-799`).
- **Passed explicitly**, never through a contextvar: `_execute_tool_traced` passes it as a keyword to the handler; only the shell, `shell_bg` and git handlers accept it and pass it to `run_shell_command(…, authorization=)`, `bg_process_manager.start(…, authorization=)` and `run_cli_command_detailed(…, authorization=)`.
- **Checked and consumed** by those runners: `agent_id` equals `AGENT_ID`, `tool_id` matches, the digest and the work dir equal the values they are about to run, it has not expired, and its nonce is unused (an in-process set). Anything else returns "Error: command execution not authorised." and logs `execution_authorization_refused`.
- **No ambient state.** `_execution_approved` and `check_execution_approved` are deleted. `asyncio` copies a context into every task it creates, so a contextvar set around `execute_tool` would leak into `shell_bg`'s task and any other task spawned meanwhile. The background task holds nothing it could reuse.
- **Human commands and scheduled jobs** mint their own: `with_approval` and `dispatch_approved_operation` mint `operator_command` for the typed command (`koda/handlers/commands.py:984, 1010`; `koda/handlers/packages.py:36, 62`), and the scheduled shell job mints `scheduled_job` from the published job definition (`scheduled_job_runtime.py:299-305`).
- **Governed git cannot execute repository config (AG-03, AG-12).** `git_status`, `git_diff` and `git_log` are read tools that run without a grant (C16), so a file planted in `.git/` must not turn them into exec:
  - every git process Koda spawns (the governed `git_*` tools through `cli_runner`, worker-side git in `queue_manager.py` and `runtime/controller.py`) runs with `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `-c core.fsmonitor=false -c core.hooksPath=/dev/null -c core.pager=cat`, and `--no-ext-diff --no-textconv` where the subcommand takes them;
  - before it runs, Koda reads the repository's own config with `git config --file <gitdir>/config --no-includes --list` (which runs nothing) and refuses when a key is outside an allowlist (`core.repositoryformatversion`, `core.filemode`, `core.bare`, `core.logallrefupdates`, `core.ignorecase`, `core.precomposeunicode`, `core.autocrlf`, `core.eol`, `remote.*.url`, `remote.*.pushurl`, `remote.*.fetch`, `branch.*.remote`, `branch.*.merge`, `branch.*.rebase`, `user.name`, `user.email`, `init.defaultbranch`, `extensions.objectformat`); the error names the key, so `filter.*`, `diff.*.textconv`, `core.sshCommand`, `include*` and the like are refused;
  - governed file tools refuse writes to any path with a `.git` component; provider built-in writes under `.git/` are a live check below `workspace_exec` (§5.3), and a CLI that allows them stays class M.
- **The per-agent enable is the published execution policy; no new field.** The secure default denies `shell_execute`, `shell_bg` and `git_*` (C5), so governed shell and git stay off until the operator publishes a rule that allows or asks for them. Only an operator publish can carry such a rule (§2.2.3, step 1). M3-E3-T1's choice "enable for the listed agents, or a per-agent enable that defaults to off" therefore means publishing rules for the listed agents (from `koda policy audit` section 3) or not.

#### 2.9.2 D-012: one request and grant store, written only by the control plane

- **Tables** (registry migration, BIGINT ids, agent scope):
  - `approval_requests`: `id`, `agent_id`, `worker_incarnation`, `origin` (`agent_call | operator_command`), `task_id`, `session_id`, `chat_id`, `tool_id`, `call_fingerprint`, `scope_fingerprint`, `description`, `preview_text`, `risk_class`, `status` (`pending | approved_once | approved_scope | denied | expired`), `created_at`, `expires_at`, `resolved_at`, `resolved_by_kind`, `resolved_by_id`, `resolution_reason`.
  - `approval_grants`: `id`, `request_id`, `agent_id`, `session_id`, `chat_id`, `kind` (`once | scope`), `fingerprint`, `max_uses`, `uses`, `expires_at`, `issued_by_kind`, `issued_by_id`, `mac`, `created_at`.
- **One writer.** Only `app` writes either table, through one module, `koda/control_plane/approvals.py`. The worker calls internal routes with its per-worker broker token (AG-17); `agent_id` always comes from the token, never the body:
  - `POST /internal/approvals/consume` with `tool_id`, `call_fingerprint`, `scope_fingerprint`, `session_id`, `chat_id` and an optional `request_id`. In one transaction the control plane looks for a usable grant for the token's agent: a `once` grant for that `request_id` whose fingerprint is the call fingerprint; otherwise a `scope` grant whose fingerprint is the scope fingerprint and whose session and chat match (as today, `approval.py:1371-1389`). It locks it, verifies its MAC, `agent_id`, `uses < max_uses` and `expires_at > now()`, increments `uses`, writes `approval.grant_consumed`, and returns `{grant_id, kind}`; with no usable grant it returns `404 no_grant`. The worker mints `human_grant` only from a success.
  - `POST /internal/approvals` creates a request (`expires_at = now + APPROVAL_TIMEOUT`, 300 s, `approval.py:80`), sends `NOTIFY approval_requested`, and returns its id; the worker then shows the Telegram card.
  - `POST /internal/approvals/{id}/telegram-decision` relays a Telegram button press (Telegram user id, decision, scope).
- **Order for every call that needs a grant:** consume first (an existing scope grant covers the call with no request and no card); only on `no_grant`, create a request and show the card; after the resolution, consume with the request id.
- **Resolution** has one function, `resolve_approval_request(request_id, decision, scope, resolver)`, used by the dashboard route (operator session; it replaces `approval_broker`'s in-memory resolve) and by the Telegram relay. It writes the status, inserts the grant with `mac = HMAC(signing key, canonical(id, request_id, agent_id, session_id, chat_id, kind, fingerprint, max_uses, expires_at, issued_by))` using the ADR-025 signing key (M1-E6-T3), writes `approval.resolved`, and sends `NOTIFY approval_resolved` with the request id.
- **Waiting.** The worker waits on `approval_resolved` through the one reconnecting LISTEN implementation (ADR-011, `koda/agents/listen_notify.py`), with a 5 s poll of the request status as the fallback, until `expires_at`; then it consumes.
- **Single use and expiry.** Allow once is `max_uses = 1`, and the consume transaction makes concurrent uses impossible. Scope grants keep the existing `ApprovalScope` TTL and `max_uses` (`approval.py:1413-1414`).
- **Restart.** At each worker spawn the supervisor marks that agent's `pending` requests from another incarnation `expired` (`approval.expired`, reason `worker_restart`). Nothing is restored, so D-163 disappears. Grants persist until they expire (ADR-009).
- **The boundary, stated exactly.**
  - The Telegram relay is a resolution the **worker asserts**. Telegram updates reach the worker, and a callback query carries nothing the control plane can verify; it checks only that the request belongs to the token's agent and is pending, and that the asserted Telegram user is on that agent's published allowed-user list. Any code that holds the worker's broker token can therefore approve that agent's own requests (R-4).
  - What keeps a prompt-injected model out is that it cannot obtain the broker token: AG-03 keeps it out of every child env, AG-04 makes the worker non-dumpable, and L2 denies ptrace and `/proc/<worker>/environ` and `mem` (D12-14). Before AG-14 and AG-15, a same-uid process during the AG-04 startup window can read it (R-2).
  - The grant MAC stops a grant row inserted directly with the DSN only when the inserter cannot compute the signing key, which holds from AG-17 and AG-19 on; before then a worker can forge it (R-4). That is no weaker than today, where grants live in worker memory and JSON files.
  - Cross-agent use is refused at consume: every row and MAC carries `agent_id`, checked against the token.
- **Retired:** `_PENDING_OPS`, `_PENDING_AGENT_CMD_OPS` and `_APPROVAL_GRANTS` (`approval.py:78-79, 1588`), the restore path (`approval.py:86-153`), and `koda/state/pending_approvals.py` and `koda/state/approval_grants.py` with their JSON fallbacks. Existing file grants are not imported as live grants: they were written by workers and would become MAC-signed grants (§9.3, M2-E1-T2).

---

## 3. Alternatives considered

| Alternative | Why not |
|---|---|
| **Fewest moving parts.** A boolean in `autonomy_policy`, honoured only in `guarded` mode; the key stays mounted; network unconfined; dashboard approvals proxied to the worker. | Contradicts ADR-002(B) and ADR-009 (which rejects the proxy). Inert for general tasks and dependent on a query-text classifier. *Grafted:* confining worker-side git, the AST spawn guard, the work-dir invariant, supervised stepping in Koda's loop. |
| **Key relocation** to an app-only volume (copy, verify, delete). | Surgery on key material, and a downgrade trap (older releases created a new key when the file was missing). Making the existing volume app-only reaches the same boundary. |
| **Default `none`, with `strict` imposed silently.** | Silently removes reads from Claude and Gemini agents and governed shell on kernels older than 6.7. |
| **Codex `read_only` through L2 only** (inner `danger-full-access`, Koda maps the workspace read-only): revision 1, and option (ii) of S2-2. | Under L2 the shell gets TCP 443 and 53 to every host at `read_only` (HTTPS egress), and under `off` nothing confines it. |
| **Codex's own `--sandbox read-only` for `read_only`** (revision 2). | Cannot start inside Landlock, so under the default modes Codex could run no command and read nothing while the UI claimed reads; unconfined it reads every file the uid can read. |
| **A nested `koda-sandbox-exec` around Codex's shell** (a narrower Landlock domain with no TCP, through `$SHELL` or a wrapper). | Unproven that Codex 0.169.0 runs `exec_command` through a configurable shell; recorded as O-9 for a later pin. |
| **Refuse Codex entirely under `off` when the worker can read the key.** | Codex `read_only` already clamps to `none`, and the confirmed levels show R-8 in the modal; refusing would remove the only Codex modes native installs have. |
| **Gemini per-task system settings file** (revision 2). | Gemini 0.68.0 skips it unless it and every ancestor are root-owned, and ignores `admin.*` from any file (§1.2). |
| **Root-owned static Gemini settings in the image** (option B of R2-3). | Works only in the image, not on native installs, and still needs the workspace out of the cwd; one Koda-written user-settings file in the rebuilt home works everywhere. |
| **`--skip-trust`.** | Trust arrives after the first settings load and the 10 s cache, so the workspace layer and `.env` would load only on later reloads. Env trust with an empty cwd is the same on every load. |
| **`GEMINI_RESTRICTED_MODE=true` with folder trust off** (untrusted cwd, so no JIT GEMINI.md and no `.gemini/.env`). | Undocumented variable; forces `default` mode, so only `none` and `read_only` could use it, giving two trust modes per level. Revisit if OQ-3(b) for Gemini matters. |
| **Gate chat toggles by an engine-simulated widening of shell, git and write decisions** (SEC alternative in S2-4). | Needs a probe-call corpus and a simulate diff on every toggle. Publishing the last published snapshot plus the toggle's own change is smaller and also stops unrelated draft content. |
| **Keep the model policy live** (option (a) of R2-7: carve it out of the signed snapshot and keep S10 as the gate). | Two delivery channels for governance, and the chat command would take effect without any publish or audit. |
| **Escalation as a level raise only.** | A provider switch at the same level adds a shell and egress unconfirmed (SEC-3). |
| **Gate in the API route**, revision 1. | Six internal callers publish the draft without the route (SEC-4). |
| **Keep the contextvar and set it around `execute_tool`** (ADR-009's rejected alternative). | It leaks into tasks created during the call, binds nothing to the command, and keeps five gates. |
| **Worker-verified grants** (an HMAC key in the worker). | The worker could then sign its own grants. Asymmetric keys add a key pair for the same result as one consume route. |
| **Wait for M1-E2-T5 and rely on DB grants only.** | M1-E2-T5 is §13-gated behind M2-E2-T2 and M2-E6-T1. The MAC closes direct DSN inserts once AG-17 and AG-19 ship; the role closes the rest later. |
| **A persisted snapshot high-water mark.** | A restore of an older database would refuse every agent. |
| **`GEMINI_SYSTEM_MD` for Gemini's system instructions.** | It replaces the CLI's whole built-in prompt, including its tool-use instructions. Escaping the delimiters is smaller. |
| **Gemini `plan` mode for `read_only`; Gemini `tools.exclude`.** | `plan` is read-only by mode and reroutes models; a denylist misses tools added in a version bump (SEC-10). |
| **Claude `acceptEdits`/`auto`/`plan` per level.** | Several modes with version-dependent semantics, and `auto` delegates approval to a classifier. `dontAsk` plus explicit lists is one rule. |
| **Gemini native resume.** | Adds session state in the provider home; replay (M3-E5-T1) is already planned. Revisit on cost evidence. |
| **A Koda-hosted MCP bridge** exposing governed tools natively. | Deferred: an inbound capability socket inside the sandbox and a second tool protocol. Re-evaluate if the M0-E3-T2 eval at `read_only` exceeds the AG-27 budget. |
| **bwrap or a container per execution; uid split.** | User-namespace and seccomp relaxations; uid split stays a fallback only if AG-08 shows Docker's seccomp blocks Landlock. |
| **Provider sandboxes as the boundary; native approval bridging; status quo.** | Per-provider semantics; a hidden flag and a Koda-hosted server; rejected by ADR-002. |

## 4. Consequences

**Positive**
- One authority, one field, one resolver, one delivery channel (execution and model policy), one publish gate, one approval store.
- Child runs, artifact-gap turns, dry runs and internal calls become restricted on every provider; internal calls run with no tools at all, and Codex never runs `danger-full-access` outside L2. No level is weaker than today in any confinement mode.
- Provider switches cannot add a shell or egress without confirmation, and chat toggles cannot publish operator drafts.
- Workspace content cannot configure, extend or redirect a provider CLI.
- Policy-approved governed shell and git can run, bound per call; dashboard approvals work across processes.
- The key and the bootstrap code leave every model-reachable container, and workers stop decrypting.
- Operators can trace who granted what.

**Negative and costs**
- Coding agents slow down until an operator opts them in; each governed round costs a resume, and Codex and Gemini follow-ups are replayed rather than resumed.
- Under the default confinement Codex has two levels, `none` and `workspace_exec`; a Codex agent at the default level answers without reading the workspace (OQ-6).
- More approvals. Workspace customisation stops loading (OQ-3), except Gemini's JIT GEMINI.md (R-7).
- Codex, governed shell and git need Landlock (kernel ≥ 5.13; ≥ 6.7 for `strict`) for anything beyond `none`.
- One new volume, which backups must include. CLIs must be upgraded deliberately; each bump re-runs the contract test, the feature review, the offline probes and the live checks.

**Deleted**
- `permission_mode` and `dry_run` from `QueryContext` (`queue_manager.py:630` and its uses), `llm_runner` and every runner.
- `claude_runner._effective_permission_mode` (`:92-96`) and the duplicate argv builder; `gemini_runner._effective_approval_mode` (`:86-96`); the Codex dry-run and resume-in-danger branches (`codex_runner.py:259-260, 283-286, 312-330`).
- The reads of `CODEX_SANDBOX`, `CODEX_APPROVAL_POLICY` and their validator (the stored values in AG-32); `AGENT_EXECUTION_POLICY_JSON` and its readers.
- The `_execution_approved` contextvar, the in-memory approval stores and the approval JSON fallbacks.
- The worker-side decrypt paths (C10); the draft reads (`agent_settings.py:232-236`, `skills/_runtime.py`); the `/var/lib` prefix rule and the HOME fallback for work dirs; the `/tmp` work dir of the memory extractor.
- The unused `sandbox_policy` gates (TD-037) and the bwrap backend; the `KODA_AGENT_DEFAULT_*` claims in `docs/operations/hardening.md`; the "plan" mode concept.

---

## 5. Verification and test plan

**G** is the full suite (ruff, ruff format, mypy, pytest with coverage, the pnpm web checks); **G-RS** adds cargo fmt, clippy and test; **G-PG** runs on Postgres; **G-CI** is the docker smoke.

### 5.1 Cross-cutting automated checks

1. Resolver (AG-20): a table test over level × ceiling × provider × confinement × Codex `IP` result per profile, and a monotonicity property test (adding a ceiling never raises the level or the capability).
2. An AST spawn guard over all of `koda/`: `subprocess.*`, `asyncio.create_subprocess_*`, `os.system`, `os.spawn*` and `os.posix_spawn` go through `process_confinement` or appear on the class T allowlist with a reason (AG-14).
3. "No secret reaches any child": CLIs, governed shell, git, MCP stdio, media tools, chromium; HOME, `XDG_*` and `TMPDIR` point at the child's own directories (AG-03).
4. Import graph: the worker entrypoint cannot reach `decrypt_secret` or `encrypt_secret` (AG-17).
5. Evaluator parity vectors through the API and the runtime (AG-06).
6. Snapshot tamper, cross-agent replay and rollback are refused; unsigned versions are re-signed once (AG-11).
7. The key-fingerprint matrix (AG-05, implemented: `tests/integration/test_master_key_fingerprint_postgres.py`, `tests/test_control_plane_master_key.py`).
8. Migrations run twice on G-PG (AG-18, AG-21, AG-11).
9. Linux integration for `koda-sandbox-exec`: reads outside the allowlist denied; TCP connects to 5432, 8090 and 50061 denied (ABI ≥ 4); a UDP send and a connect to an internal listener on 443 recorded as allowed (R-6); `environ` of a sibling or parent denied; a signal to the worker denied (ABI ≥ 6); nesting cannot widen; exit 126 when enforcement is incomplete; a workspace grant of `/tmp`, HOME or a state root refused (AG-08, AG-12).
10. Publish gate (AG-21), `tests/test_control_plane/test_publish_gate.py`: one test per caller in §2.2.3, plus clone and first publish, plus:
    - `test_toggle_with_pending_draft_publishes_only_its_change`: a voice toggle while the draft holds an unpublished rule allowing `shell_execute` publishes the voice change and nothing else; the rule stays in the draft;
    - `test_system_first_publish_uses_secure_policies`: a supervisor first publish of a draft with a shell rule publishes the secure-default execution and tool policies;
    - `test_adding_codex_to_workspace_write_agent_needs_confirmation` and `test_adding_codex_to_read_only_agent_is_not_escalation`;
    - `test_publish_refused_while_agent_migration_pending` (per agent, others publish).

### 5.2 Named tests

**Argv tests that replace M1-E2-T2's "per-runner argv unit tests"** (AG-22 to AG-25). Each runs the builder and `validate_args`; none calls a model.

| Id | Test (file) | Asserts |
|---|---|---|
| A-P-01 | `test_profile_reaches_every_call_site` (`tests/test_services/test_provider_builtin_tools.py`) | The four call sites, resume and verification turns all pass a resolved `BuiltinToolProfile`; S2 to S7 each produce the documented level. Each internal call site (memory extractor, squad planner) runs at `none` with a fresh empty work dir and `TMPDIR` under the task tmp, never `/tmp`, HOME or `DEFAULT_WORK_DIR`; the extractor on its `MEMORY_EXTRACTION_PROVIDER` chain and the planner on the coordinator's **published** model policy; both pass S10. |
| A-P-02 | `test_compiled_argv_never_contains_bypass` (same file) | For every provider × level × confinement × {new, streaming, images} profile: no `--permission-mode` other than `dontAsk`, no `--approval-mode=plan`, no `yolo` below `workspace_exec`, no `danger-full-access` without L2, no Codex shell below the shell levels, no `--dangerously-*`, no `--trust`, no `--skip-trust`. |
| A-P-03 | `test_contract_has_no_legacy_tokens` (`tests/test_services/test_provider_cli_contract.py`) | After AG-23 to AG-25 every `legacy` flag and `legacy_choices` entry is gone; `approval_policy` choices are `("never",)`; `--permission-mode` choices are `("dontAsk",)`. |
| A-P-04 | `test_chat_provider_switch_publishes_or_waits` (`tests/test_services/test_agent_settings.py`) | Claude `workspace_write` agent: `/provider codex` calls `publish_agent` with actor `telegram_user` and a model-policy patch; the publish is refused (adds `exec`), the reply asks for dashboard confirmation, the patch stays in the draft, and the published snapshot is unchanged; after a confirmed operator publish Codex runs. A `/model` change within the provider publishes without confirmation, and the worker reads it from the published snapshot. |
| A-P-05 | `test_capability_assertion_after_cli_bump` (`tests/test_services/test_provider_builtin_tools.py`) | When the capability table for a pinned version gains a capability after publish, S10 refuses the provider for the turn and raises the alert. |
| A-C-01 | `test_claude_argv_per_level` (`tests/test_services/test_claude_runner.py`) | Parametrised over the four levels: the every-level block, then `--tools`/`--allowedTools` as in §2.3.1. |
| A-C-02 | `test_claude_streaming_and_print_share_one_builder` | Streaming and non-streaming argv are equal apart from `--output-format`/`--verbose`. |
| A-C-03 | `test_claude_resume_keeps_level_flags` | `--resume ID` adds nothing else and removes nothing. |
| A-C-04 | `test_claude_images_add_only_task_dir` | `--add-dir` is the task's image dir, never the `tmp_images` root. |
| A-C-05 | `test_claude_system_prompt_in_0600_file` | No `--append-system-prompt` on argv; the file is 0600 and gone after the run. |
| A-C-06 | `test_claude_env_disables_auto_memory` | `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`; HOME, `CLAUDE_CONFIG_DIR` and `XDG_*` in the agent's Claude home; `TMPDIR` the task tmp. |
| A-C-07 | `test_claude_option_like_values_stay_values` | A model id or file path starting with `-` does not change the mode or tools. |
| A-C-08 | `test_claude_workspace_exec_clamps_without_l2` | From AG-14 on, `workspace_exec` under `strict` without L2 clamps to `workspace_write` (S9) with the reason. |
| A-X-01 | `test_codex_none_and_read_only_have_no_shell` (`tests/test_services/test_codex_runner.py`) | Effective `none`, and `read_only` on 0.169.0, give `--sandbox read-only --disable shell_tool` in `strict`, `filesystem` and `off`, whatever the `IP` results. |
| A-X-02 | `test_codex_workspace_write_rows` | Under `off` with `IP(workspace-write)` ok: `--sandbox workspace-write`, `network_access=false`, `exclude_slash_tmp=true`, `exclude_tmpdir_env_var=true`, `writable_roots=["<task tmp>"]`; under L2 (`IP` failed inside the profile) or with `IP` failed: `none`. |
| A-X-03 | `test_codex_workspace_exec_rows` | L2 on and `IP` failed inside the profile → `--sandbox danger-full-access`; L2 on and `IP` ok inside the profile → workspace-write with network and both excludes; L2 off and `IP` ok → workspace-write with `network_access=true`, both excludes and `writable_roots`; L2 off and `IP` failed → `none`. |
| A-X-04 | `test_codex_off_mode_never_danger_full_access` | Under `off`: default level, dry run, child run, artifact gap, squad planner and memory extractor never emit `danger-full-access` (SEC-2). |
| A-X-05 | `test_codex_approval_policy_is_never` | Exactly one `approval_policy`, `never`; no `--approve-for-me`. |
| A-X-06 | `test_codex_resume_is_replay` | `supports_native_resume=False`; no `exec resume`; no bypass flag in any argv. |
| A-X-07 | `test_codex_customisation_disabled` | `--ephemeral --ignore-rules`; one `--disable` per feature of the 0.169.0 disable set; `agents.enabled=false`, `skills.include_instructions=false`, `skills.bundled.enabled=false`, `project_doc_max_bytes=0`, `mcp_servers={}`, `web_search="disabled"`; no `--trust`, no `--dangerously-bypass-hook-trust`, no `developer_instructions` on argv; env HOME equals `CODEX_HOME`, the agent's Codex home; `TMPDIR` the task tmp. |
| A-X-08 | `test_codex_internal_calls_use_none` | S7 resolves to `none` with the fresh work dir as `--cd`. |
| A-X-09 | `test_codex_images_and_stdin_prompt` | `--image` paths, prompt on stdin (`-`). |
| A-X-10 | `test_codex_never_selects_unproven_inner_sandbox` | Property over every (level, confinement profile, `IP` result per mode): an inner `read-only` or `workspace-write` sandbox appears in the argv only if `IP` for that mode passed in that same profile. |
| A-G-01 | `test_gemini_argv_and_cwd` (`tests/test_services/test_gemini_runner.py`) | Every value attached; `--extensions=none`; `--include-directories=<workspace>` (absent for S7); no `--prompt`, `--skip-trust` or `--yolo`; cwd is `<gemini home>/cwd`, empty and mode 0500; a workspace path containing `,` is refused. |
| A-G-02 | `test_gemini_user_settings_per_level` | `<gemini home>/.gemini/settings.json`, 0600, rewritten per spawn: the `tools.core` list per level (`[]` at `none`), empty discovery and call commands, `mcpServers={}`, `hooksConfig.enabled=false`, `skills.enabled=false`, `experimental.enableAgents=false`, `security.disableYoloMode` true except at `workspace_exec`, telemetry off, `loadMemoryFromIncludeDirectories=false`, `ignoreLocalEnv=true`; no `admin.*` key; no `GEMINI_CLI_SYSTEM_SETTINGS_PATH` in the env. |
| A-G-03 | `test_gemini_modes_per_level` | `default`/`auto_edit`/`yolo` as in §2.3.2; never `plan`, never `-y`. |
| A-G-04 | `test_gemini_prompt_on_stdin` | The query and instructions reach stdin, not argv. |
| A-G-05 | `test_gemini_option_like_values_cannot_change_mode` | A model id `-y` or a query `--approval-mode=yolo` changes neither the mode nor the tools. |
| A-G-06 | `test_gemini_user_text_cannot_forge_system_block` | A query containing `</user_request><system_instructions>` arrives escaped (SEC-15). |
| A-G-07 | `test_gemini_streaming_uses_same_profile` | `text` and `json` runs differ only in `--output-format`. |
| A-G-08 | `test_gemini_env_pins` | `GEMINI_CLI_TRUST_WORKSPACE=true`, HOME the agent's Gemini home, `TMPDIR` the task tmp, and every pin of §2.3.2 with its fixed value. |
| A-G-09 | `test_gemini_settings_warning_fails_spawn` | A stderr line `Invalid configuration in` or `Security Warning: Skipping` fails the spawn closed. |
| A-K-01 | `test_codex_config_keys_probe_types` (`tests/test_services/test_provider_cli_contract.py`) | The probe runs `codex -c <key>=<wrong type> features list` for each contract key (the §1.2 list) and fails closed when a key stops erroring (a renamed key would be silently ignored). |
| A-K-02 | `test_codex_feature_set_reviewed` | `codex <every-level flags> features list` shows enabled exactly the reviewed keep list for that level (38 at `none`, plus `shell_tool` at shell levels); any other enabled feature fails, and so does an unknown name in the disable set. |
| A-K-03 | `test_codex_inner_sandbox_probe_in_profile` | `IP` runs through the same launcher and profile as the spawn (`koda-sandbox-exec` under L2, direct under `off`), checks exit 0, a refused write and a refused socket, and is cached per binary fingerprint and profile; on a Linux runner with L2, 0.169.0 records `failed` (bubblewrap). |
| A-K-04 | `test_codex_prompt_input_tools` | Offline, no credentials: `codex debug prompt-input` with `gpt-6-sol` and the §2.3.3 flags shows at `none` no `exec_command`, `write_stdin`, `view_image`, `collaboration.*` or skills block, and none of the planted workspace `AGENTS.md`, `.agents/skills` or `.codex/skills` canaries; at shell levels `exec_command` appears. A model that renders no tool list is covered by the AG-24 live check. |
| A-K-05 | `test_gemini_user_settings_load_probe` | Offline, no credentials: with Koda's `read_only` user settings, `--approval-mode=yolo` exits with the `disableYolo` error before auth (the file is read); with the `workspace_exec` settings and a workspace `.gemini/settings.json` setting `disableYoloMode=true` passed through `--include-directories`, `yolo` is not refused (the workspace file is not read); with a `NODE_OPTIONS` preload that records the CLI's environment, a `.gemini/.env` in the workspace and in each ancestor of the cwd changes no variable. |

**D-011 tests that M3-E3-T1 adds** (`tests/test_services/test_execution_authorization.py`, unless noted):

| Id | Test | Asserts |
|---|---|---|
| D11-01 | `test_policy_allowed_shell_and_git_execute` (`tests/test_services/test_approval_context_regression.py`) | M0-E2-T4's strict xfails now pass: `shell_execute` and `git_status` with an allow rule run through `_run_agent_loop` (fake kernel). |
| D11-02 | `test_denied_and_default_calls_fail_closed` | A deny rule, and the secure default with no rule, never reach the runner. |
| D11-03 | `test_require_approval_without_grant_is_refused` | No grant, no execution. |
| D11-04 | `test_authorization_bound_to_command_workdir_and_tool` | An authorization for command A is refused for command B, for another work dir and for another tool. |
| D11-05 | `test_authorization_is_single_use` | A second use of the same nonce is refused. |
| D11-06 | `test_authorization_expires` | Use after `expires_at` is refused. |
| D11-07 | `test_no_authorization_leaks_to_background_tasks` | A task created during an authorised call, and `shell_bg`'s own task, cannot run a second command; a runner called without an authorization refuses. |
| D11-08 | `test_supervised_write_needs_human_grant` | Supervised mode with an allow rule: the write waits for a grant; reads run. |
| D11-09 | `test_human_commands_and_scheduled_jobs_mint_their_own` | `/shell`, `/git`, `pip`, `npm` and a scheduled shell job run; no `_execution_approved` symbol remains in `koda/`. |
| D11-10 | `test_git_option_injection_on_live_path` | The D-026 probes (M1-E4-T1) pass with git live. |
| D11-11 | `test_cat_env_matches_file_read_env` | M1-E4-T13 parity on the live paths. |
| D11-12 | guardrail suite on live paths (`tests/security/test_guardrail_adversarial_suite.py`) | Passes with `shell_execute`, `shell_bg` and `git_*` executing. |
| D11-13 | `test_planted_git_config_never_executes` | A repository whose `.git/config` sets `core.fsmonitor` to a canary script, a `filter.*` driver and a `diff.*.textconv`, and whose `.git/hooks/pre-commit` is a canary: `git_status`, `git_diff` and `git_commit` run no canary, and the tool refuses naming the key. |
| D11-14 | `test_governed_writes_refuse_dot_git` | `file_write`, `file_edit` and the other governed write tools refuse any path with a `.git` component, through symlinks too. |

**D-012 tests that M3-E3-T2 adds** (`tests/integration/test_approvals_postgres.py` on G-PG, unless noted):

| Id | Test | Asserts |
|---|---|---|
| D12-01 | `test_dashboard_lists_and_approves_a_worker_request` | Two processes: the worker creates a request; the control-plane API lists it; an operator approves; the worker's call executes. |
| D12-02 | `test_worker_routes_cannot_resolve_except_relay` | The internal routes set no status and insert no grant except through the Telegram relay, which accepts only a pending request of the token's agent and an allowed Telegram user; with AG-17 and AG-19 present, a grant row inserted with the DSN and a MAC computed without the signing key is refused at consume. |
| D12-03 | `test_allow_once_is_single_use_under_concurrency` | Two concurrent consumes: exactly one succeeds. |
| D12-04 | `test_replayed_or_mismatched_grant_is_refused` | A consumed grant, or a grant for fingerprint A used for B, is refused. |
| D12-05 | `test_cross_agent_grant_is_refused` | Agent B's token cannot consume agent A's grant. |
| D12-06 | `test_pending_requests_expire_on_restart` | A new worker incarnation expires the old pending rows; the restart does not crash (D-163). |
| D12-07 | `test_grants_survive_restart_until_expiry` | A scope grant still works after a restart, and not after `expires_at`. |
| D12-08 | `test_request_times_out` | No decision within `APPROVAL_TIMEOUT` → `expired`, call not executed. |
| D12-09 | `test_telegram_relay_checks_the_approver` | A decision from a Telegram user not allowed for the agent is refused; `approval.resolved` records the resolver. |
| D12-10 | `test_listen_drop_falls_back_to_poll` | With the LISTEN connection dropped, the poll path still delivers the resolution. |
| D12-11 | `test_approval_events_are_transactional` | A failing audit insert fails the resolution. |
| D12-12 | approvals panel (Vitest, `apps/web`) | Lists, approves once, approves scope, denies with a reason. |
| D12-13 | `test_existing_scope_grant_is_consumed_without_a_request` | A call covered by a scope grant (same scope fingerprint, session and chat) consumes it with no request created and no card shown, `uses` increments, and once `max_uses` or `expires_at` is reached a request is created. |
| D12-14 | `test_broker_token_unreachable_from_class_m` (Linux integration, AG-14) | A class M process spawned the way the worker spawns cannot read the broker token from its env, `/proc/<worker>/environ` or `/proc/<worker>/mem`. |

### 5.3 Live provider checks

Credentials required; gated by `tests/_provider_plugin.py`; mocked tests are never proof (MISSION §7.6). Run as the image's uid (`botuser`). Per provider × level:

- a write at `read_only` leaves no file; `.git/` writes are refused below `workspace_exec`; a symlink out of the workspace is refused;
- the file tools refuse `/proc/self/environ`, `/proc/<ppid>/environ` and the provider-home credential files at every level below `workspace_exec` (R-1);
- canaries are ignored:
  - Claude: `CLAUDE.md`, `.claude/settings.json` with a hook, `.claude/skills`, `.claude/agents`, `.claude/commands`, `.mcp.json`, in the workspace and the home; auto-memory does not persist across turns;
  - Codex: the workspace `AGENTS.md`, `$CODEX_HOME/AGENTS.md` (removed by the rebuild), `.codex/config.toml`, `rules/`, `.agents/skills` in the workspace and in HOME, `.codex/skills`, `$CODEX_HOME/skills`;
  - Gemini: a workspace `.gemini/settings.json` with a hook, an MCP server, a discovery command, `context.includeDirectories` and telemetry; a `.gemini/.env` and a `.env` setting `GEMINI_SYSTEM_MD`, `GOOGLE_GEMINI_BASE_URL` and `GEMINI_TELEMETRY_*` in the workspace, in every ancestor of the cwd and in the home; `.gemini/extensions`; GEMINI.md at the workspace root is not loaded at start, and one beside a file `read_file` reads is recorded as R-7 behaviour;
- a hook or config planted in a per-agent home never reaches `app` through check-in;
- Codex: at `none` an `apply_patch` attempt leaves no file, under `off` and under L2; under `off` `workspace-write` writes only the workspace and the task tmp and blocks network unless enabled; under L2 `workspace_exec` runs and stays inside the L2 profile;
- Gemini: only the `tools.core` tools are offered; `yolo` fails below `workspace_exec`; the prompt is read from stdin; the run produces no settings warning; it runs from its 0500 cwd as `botuser`, and `write_file` into that cwd fails;
- `--append-system-prompt-file` and `--safe-mode` work with subscription auth;
- per-agent OAuth refresh holds over repeated cycles with two agents running at once (O-4).

### 5.4 Docker checks (G-CI docker-smoke; evidence in VALIDATION_REPORT.md)

In the runtime-kernel image, a process spawned the way the worker spawns: does not see `/var/lib/koda/state`; cannot read worker-state, another agent's workspace or home, the login homes or `/app`; cannot read `/proc/<worker|kernel>/environ`; cannot TCP-connect to postgres, app:8090, the kernel or the sidecars in `strict`; cannot call kernel RPC without a token; cannot use agent A's kernel token for agent B's paths. Also: the upgrade copies worker-state and decrypts every secret, and rollback to the previous images works; a `read_only` root on `runtime-kernel` passes the CLI smoke; the installer preflight records the mode; the Codex `IP` results are recorded **through `koda-sandbox-exec` with the Codex profile** and unconfined; the Gemini load probe passes as `botuser`.

**Host matrix:** self-test results on kernel 6.1 (expected `filesystem`), on kernel ≥ 6.8 (expected `strict`) and on Docker Desktop `[I]`.

---

## 6. Release gate

The default ships only when all of these are done:
- every AG item in §7 that is not marked done, and M1-E4-T9 (AG-06 and AG-09);
- M1-E6-T1 (kernel RPC auth), M1-E6-T3 (signing key), M3-E3-T1 (D-011), M3-E3-T2 (D-012), M1-E4-T13 (one path resolver), M3-E5-T1 (replay);
- the M0-E3-T2 eval evidence;
- the §9.1 operator decisions.

Each task may merge earlier if it leaves the system no less restrictive than before.

---

## 7. Implementation backlog

Each task names its files, acceptance criteria, tests, risk and dependencies; a gate is listed only when it has one.

### 7.1 Mapping to MASTER_PLAN M1-E2

| Plan task | AG items |
|---|---|
| M1-E2-T1 · this ADR | — (AG-01 merged with revision 2) |
| M1-E2-T2 · Governed-by-default provider permission modes | AG-02 (done), AG-07, AG-08, AG-10a, AG-10b, AG-11, AG-12, AG-13a, AG-13b, AG-14, AG-15, AG-16, AG-19b, AG-20 to AG-31 |
| M1-E2-T3 · `koda-state` off the runtime-kernel (the key stays put) | AG-05 (done), AG-17, AG-18, AG-19, AG-32 |
| M1-E2-T4 · Environment allowlist for spawned processes | AG-03, AG-04 (done) |
| M1-E2-T5 · Scoped Postgres role | no AG item; unchanged in scope, and it closes residuals R-3 to R-5 (§2.5.4) |
| M1-E4-T9 (ADR-039) | AG-06 (starts it) and AG-09 (closes it; not a start dependency) |

M1-E2-T4 keeps only the environment items, because M1-E6-T1 depends on it for the token-stripping allowlist: AG-12 needs M1-E4-T13's resolver, and leaving it in M1-E2-T4 would make kernel RPC auth wait for a path resolver it does not use. AG-09 belongs to M1-E4-T9, whose done-when it completes (ADR-039); AG-09 depends on AG-06 and nothing depends back.

### 7.2 Done

- **AG-02** pinned CLIs, contract table, fail-closed probes (6d050b5; C4).
- **AG-04** non-dumpable worker and kernel (6d050b5; C12).
- **AG-05** fail-closed master key with a Postgres fingerprint (6d050b5; C10, §2.5.1).

### 7.3 Foundation (no dependencies)

**AG-03 · Allowlisted env for every child process; hardened git** (M1-E2-T4)
- Files: `mcp_bootstrap.py:90`, `mcp_manager.py:128`, `mcp_client.py:156-162`; `mcp_isolation.py:329-330, 392-410`; `link_analyzer.py:128, 186`; `artifact_ingestion.py:1511, 1568`; `utils/audio.py:123, 170, 291`; `utils/video.py:37`; every git spawn (the `git_*` handlers at `tool_dispatcher.py:2870-3027`, through `_run_git` and `cli_runner.py`, worker-side git in `queue_manager.py` and `runtime/controller.py`); `provider_env.py:182-236`.
- Accept: no child gets `env=None` or an inherited env; HOME, `XDG_*` and `TMPDIR` are the child's own; MCP servers get their connection env plus the safe base, and Docker MCP env files live in a 0700 per-worker directory and are deleted once the container has started; every git spawn carries the §2.9.1 hardening and refuses a repository config key outside the allowlist; the CLI env sets `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.
- Tests: §5.1.3; a git-runner unit test with a planted `core.fsmonitor`, hook and filter driver (D11-13 repeats it on the live path). · Risk: med (MCP servers that relied on inherited vars; repositories with custom config) · Deps: —

**AG-06 · One evaluator** (M1-E4-T9, ADR-039; in progress)
- Accept: deny > require_approval > allow_with_preview > allow, then priority, then name; fnmatch for every rule; `name` is the `rule_id`; `match` and `selectors` normalise to one key; a `mcp_*__delete_*` deny is enforced; evaluate equals the runtime for every vector.
- Tests: parity vectors (§5.1.5). · Risk: med (no production effect, C6) · Deps: —

**AG-07 · Audit of configuration changes**
- Files: `manager.py:12115, 8583, 8597, 8652, 12568`; the system-settings writer; `control_plane/audit.py` (`required=True` path).
- Accept: every policy, model-policy and system-settings write records the actor and a before/after diff; governance events are transactional (§2.6).
- Tests: G-PG; route tests. · Risk: low · Deps: —

**AG-08 · Confinement primitive, mode setting and doctor**
- Files: `rust/koda-runtime-kernel/src/confinement.rs`; `src/bin/koda-sandbox-exec.rs`; `Cargo.toml` (`landlock` crate, exact version); `config.py`; `.env.example`; `sandbox_doctor.py`; `docs/operations/sandbox-doctor-runbook.md`.
- Accept: `--self-test` prints the ABI and the enforced layers (filesystem, ptrace, TCP, scoping) as JSON; the profile follows §2.4.2 and DNS works; exit 126 when enforcement is incomplete; `filesystem` and `off` emit an audit event and a banner (the `off` banner states R-8); a UNIX-socket kernel target is refused under `strict`; Docker's default seccomp behaviour is recorded.
- Tests: cargo unit tests; Linux integration (§5.1.9) on an ABI ≥ 6 runner. G-RS. · Risk: high · Deps: —

**AG-10a · Deliver the published spec**
- Files: `config.py:1335` (delete); `services/execution_policy.py:198-203`; `tool_prompt.py`; `scheduled_jobs.py`; `queue_manager.py` (`_prepare_query_context`); `agent_settings.py:232-236`; `manager.py` preview accessor.
- Accept: one accessor reads the signed `AGENT_SPEC_JSON`; the worker takes `provider_builtin_tools` **and the model policy** only from it (no `build_draft_snapshot` in the worker); `execution_policy` rules from it stay inactive until AG-10b; a missing or invalid spec gives secure defaults; `AGENT_EXECUTION_POLICY_JSON` is gone.
- Tests: unit; G-PG publish → env → read; a draft model-policy write does not change the worker's provider. · Risk: med · Deps: —

**AG-12 · Workspace roots, deny roots and the work-dir invariant** (M1-E2-T2; inside M1-E4-T13's resolver)
- Files: `config.py:201, 207-213, 766-780`; `docker-compose.yml:247` and the release compose; `utils/workdir.py`; `tool_dispatcher.py:1404-1416, 2389-2402`; `.env.example` (`AGENT_WORKSPACE_ROOT`).
- Accept: governed file tools work under `/var/lib/koda/runtime/workspaces/<agent>`; deny roots are checked by path component; a work dir equal to or containing HOME, a state root, a provider home, a login home, `RUNTIME_EPHEMERAL_ROOT`, `RUNTIME_KERNEL_ROOT` or a shared temp directory (`/tmp`, `/var/tmp`, `/dev/shm`, the system temp dir) is refused; governed writes under a `.git` component are refused; the native `RUNTIME_EPHEMERAL_ROOT` default is `~/.koda-runtime/<bid>` (0700) and the compose kernel root `/var/lib/koda/runtime/kernel`; the HOME fallback is gone.
- Tests: predicate matrix emulating the compose and native layouts; D11-14. · Risk: med · Deps: M1-E4-T13

**AG-13a · Per-agent provider homes**
- Files: `provider_env.py`; `manager.py` (provider home paths); Codex instructions into the Koda-written `config.toml`; the Gemini user-settings writer.
- Accept: each agent has its own Claude, Codex and Gemini home, rebuilt before each spawn from the §2.3.5 allowlist (Gemini's `cwd/` recreated empty and 0500; Koda's Codex `config.toml` and Gemini `settings.json` rewritten); HOME, `CODEX_HOME`, `CLAUDE_CONFIG_DIR` and `XDG_*` point into it; agent B cannot read agent A's sessions; env credentials work; file OAuth modes keep using the canonical login home until AG-13b.
- Tests: unit (rebuild removes every non-allowlisted file, `.env` and `.gemini/.env` included); G-PG. · Risk: med · Deps: —

**AG-17 · Control-plane worker broker: workers never decrypt** (M1-E2-T3)
- Files: `control_plane/api.py` (internal routes); `supervisor.py` (mint the token, store its hash); a worker client; `mcp_connection_broker.py`, `mcp_oauth.py` and the other paths the import-graph test finds.
- Accept: the import-graph test passes; agent A's token gets 403 on agent B's secrets; a respawn revokes the previous token; OAuth refresh and write-back happen in the control plane only; MCP, OAuth MCP, the squad check, TTS and image generation still work. The same token authenticates the credential and approval routes (§2.4.4, §2.9.2).
- Tests: auth matrix; G-PG two-process test. · Risk: high · Deps: AG-05 (done)

**AG-18 · `WORKER_STATE_ROOT` and the `koda-worker-state` volume** (M1-E2-T3)
- Files: `config.py`; the C14 consumers; `supervisor.py:92`; an app-side copy migration (checksums, marker); both compose files (add the volume; `koda-state` stays for now); CHECKSUMS; `tests/test_installation_assets.py`.
- Accept: both processes resolve the same paths; a test lists every `STATE_ROOT_DIR` consumer and classifies it as control-plane-only, worker-state, or retired (`state/pending_approvals.py`, `state/approval_grants.py`: retired by M2-E1-T2 and §2.9.2, not moved); an upgraded install keeps skill locks, gateway config and room photos.
- Tests: migration run twice; compose render. · Risk: med · Deps: —

### 7.4 Policy delivery and integrity

**AG-09 · `koda policy audit` (read-only, one command)** (M1-E4-T9's close condition)
- Files: `koda/cli/migrate.py` (subcommand); docs.
- Accept: the three sections of §2.8.1 per published agent, plus any `AGENT_EXECUTION_POLICY_JSON` value found; writes nothing; its output is the upgrade report, AG-30's banner list and M3-E3-T1's approval package.
- Tests: G-PG fixture with legacy-compiled rules and recorded traces. · Risk: low · Deps: AG-06

**AG-10b · Activate delivered rules**
- Files: the AG-10a accessor (switch on `execution_policy` rules).
- Accept: a published deny rule is enforced in the worker; the preview equals the live tool set.
- Tests: G-PG publish, build env, enforce. · Risk: high · Deps: AG-06, AG-09, AG-10a · Gate: §13 sign-off if AG-09's diff section is non-empty (ADR-039)

**AG-11 · Signed snapshots**
- Files: `manager.py` publish (sign); supervisor env build (verify); `skills/_runtime.py` (delete the draft fallback); `services/execution_policy.py:127-165` (MCP tool policy from the snapshot); the re-signing migration.
- Accept: §2.5.3: a tampered row, another agent's snapshot and a version below the verified high-water mark stop the spawn with `security.snapshot_rejected`; unsigned latest versions are republished signed once, through the AG-21 primitive; the worker never calls `get_agent_spec`. The integrity claim against a worker holds from AG-17 and AG-19 on (R-5).
- Tests: tamper, cross-agent, rollback and re-sign tests; G-PG. · Risk: med · Deps: AG-10a, M1-E6-T3 · Gate: O-5 (approved)

### 7.5 Provider homes and spawn confinement

**AG-13b · Login homes app-only; credential checkout and check-in**
- Files: the login flows in `app`; AG-17 broker routes; the copy migration.
- Accept: §2.4.4; canonical login homes on `koda-state`, copied and verified; only the named files cross, schema-checked; a planted hook or config never reaches `app`.
- Tests: unit; G-PG; recorded live refresh evidence. · Risk: high (OAuth rotation) · Deps: AG-13a, AG-17 · Gate: OQ-4; O-4 evidence

**AG-14 · Class M and S spawns through the helper (worker side)**
- Files: new `koda/security/process_confinement.py`; the runner spawn sites (`claude_runner.py`, `codex_runner.py`, `gemini_runner.py`); `cli_runner.py`; `shell_tools.py`; the git tool spawns; worker-side git in `queue_manager.py` and `runtime/controller.py`; the Codex `IP` launcher.
- Accept: the AST guard passes; class M clamps or refuses exactly when the mode's required layers are missing (S9); a stub CLI or shell cannot read the §5.4 targets or the broker token; the Codex `IP` runs through the same profile as the spawn; a shared directory is never granted as a workspace.
- Tests: argv-prefix tests; AST guard; Linux integration; D12-14. · Risk: high · Deps: AG-03, AG-08, AG-12; the provider-CLI spawns also AG-13a

**AG-15 · Kernel path: per-worker identity and a floor the kernel computes**
- Files: `rust/koda-runtime-kernel/src/server.rs`, `processes.rs`, `agent_workers.rs`; `proto/runtime/v1/runtime.proto` (required `ConfinementProfile`); `koda/internal_rpc/runtime_kernel.py`.
- Accept: a request without a profile is rejected; agent A's token cannot get agent B's paths; a broader caller profile is narrowed; execution goes through `koda-sandbox-exec`.
- Tests: Rust request validation; Python client test. G-RS. · Risk: high · Deps: M1-E6-T1, AG-08

**AG-16 · Class U spawns through the helper**
- Files: `mcp_isolation.py` (the native and Linux backends become the helper; bwrap removed); the media spawns; `browser_manager.py` (chromium through a wrapper `executable_path`); `sandbox_policy.py` (delete the TD-037 gates).
- Accept: MCP, media and chromium run under their own profiles and report status truthfully; without L2 they run with a warning. M1-E4-T6 coordinates; M1-E4-T7's fail-closed egress applies to the helper's TCP rules if OQ-5 approves.
- Tests: fake-runner unit tests; Linux integration; a real-browser CI test. · Risk: med · Deps: AG-03, AG-08, AG-14

**AG-19b · `runtime-kernel` compose hardening**
- Files: both compose files; CHECKSUMS.
- Accept: `no-new-privileges`, `cap_drop: [ALL]`, and `read_only: true` with tmpfs `/tmp` once the smoke passes; the kernel's worker supervision still works.
- Tests: compose render; G-CI smoke. · Risk: med · Deps: AG-14, AG-15

### 7.6 Secrets and placement

**AG-19 · `runtime-kernel` without `koda-state`** (M1-E2-T3)
- Files: `docker-compose.yml:239-256`; release compose; CHECKSUMS; `packages/cli/bin/koda.mjs` (self-test preflight and mode choice); `docs/operations/backup-restore.md`, `hardening.md`, `upgrade.md`.
- Accept: `/var/lib/koda/state` does not exist in `runtime-kernel`; the preflight records the mode; rollback to the previous images works.
- Tests: compose render; installer test with a fake docker; upgrade and rollback smoke. G-CI. · Risk: high · Deps: AG-05 (done), AG-08, AG-17, AG-18 · Gate: §13 (O-1, approved)

**AG-32 · Delete the legacy subpaths, login homes and stored `CODEX_*` values** (the release after AG-19, AG-13b and AG-24, ADR-018)
- Accept: subpaths and login homes removed only when the marker and checksums match; the stored `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` values deleted; the release note says rollback past this release loses them.
- Tests: migration test. · Risk: low · Deps: AG-19, AG-13b and AG-24 shipped in a prior release · Gate: OQ-4, OQ-7

### 7.7 Governance field and runners

**AG-20 · `provider_builtin_tools` field, capability and resolver**
- Files: new `koda/services/provider_builtin_tools.py`; the execution-policy normalize and validate (delegate); the capability table in `provider_cli_contract.py`; the `agent_spec` summary; OpenAPI.
- Accept: §2.2.1 to §2.2.4; the schemas and error format of §2.2.2; one import serves the runtime, publish, preview and simulator.
- Tests: §5.1.1; A-P-05. · Risk: med · Deps: AG-10a

**AG-21 · Publish gate inside `publish_agent`, and the migration**
- Files: `manager.py:12568` and every caller in §2.2.3; `api.py:3085-3095`; `agent_settings.py:482-617, 689`; `commands.py:447, 510, 587, 2059, 2447`; `supervisor.py:223, 459-461`; `bootstrap.py:53-56`; the migrations module.
- Accept: §2.2.3: the required actor; the source rule per actor (non-operator actors never read the draft); escalation by level or capability; the baseline rules; the transactional event; the per-agent `governance_migration_pending` refusal; §2.8.1's migration at control-plane start, idempotent, from the last published snapshot, signed when AG-11 is present; `/provider`, `/model` and functional defaults publish their own change.
- Tests: §5.1.10; A-P-04; migration run twice on G-PG. · Risk: med · Deps: AG-07, AG-20

**AG-22 · Replace `permission_mode` and `dry_run` with `BuiltinToolProfile`**
- Files: `queue_manager.py` (`QueryContext` at `:630`, `_prepare_query_context`, `_run_streaming`, `_run_fallback`, `_run_agent_loop`); `llm_runner.py`; every runner signature; `memory/extractor.py:183-195`; `coordinator_engine.py:375-385, 419-437`; the `bypassPermissions` fixtures.
- Accept: all call sites pass a resolved profile, and resume and verification turns reuse it; internal calls run at `none` with a fresh per-task work dir and `TMPDIR`, and the planner reads the coordinator's published model policy; the CLI argv is unchanged until AG-23 to AG-25.
- Tests: A-P-01, A-P-02. · Risk: med · Deps: AG-20

**AG-23 · Claude compiler**
- Files: `claude_runner.py` (`:92-96` deleted; `run_claude` `:330` and `_build_cmd` `:640` merged into one builder); the system-prompt file; the task-scoped `--add-dir`; the contract (`--safe-mode`, `--permission-mode` choices narrowed to `dontAsk`).
- Accept: §2.3.1 for every level; the live checks pass; `self_confined` is set from that evidence.
- Tests: A-C-01 to A-C-08; probe tests; CI contract job; gated live tests. · Risk: high · Deps: AG-13a, AG-22; `workspace_exec` also AG-14

**AG-24 · Codex compiler, and the `CODEX_*` settings no longer read**
- Files: `codex_runner.py:171-330, 610-629, 878-899`; `config.py:269-270`; `startup_validator.py:26, 67-72`; `manager.py:608-609`; the contract (`approval_policy` choices `never`, bypass flag removed, `--ephemeral`, `--ignore-rules`, the disable set and keep list, the `-c` keys of §1.2, the probes of A-K-01 to A-K-04); the release note.
- Accept: §2.3.3; `none` and `read_only` compile to `--sandbox read-only --disable shell_tool`; inner sandboxes only where `IP` passed in the same profile; `danger-full-access` only at `workspace_exec` under L2; `supports_native_resume=False`; the stored `CODEX_*` values are left in place; the contract's `verified_against_help` and per-flag `verified` are set from the recorded CI help run.
- Tests: A-X-01 to A-X-10, A-K-01 to A-K-04; `test_codex_runner.py` rewritten as profile contract tests; gated live tests. · Risk: high · Deps: AG-13a, AG-22, M3-E5-T1; the L2 rows also AG-14

**AG-25 · Gemini compiler**
- Files: `gemini_runner.py:73-121, 351, 363, 394, 525, 541, 551`; the contract (`--include-directories` no longer legacy; `plan` and `--prompt` removed); the env builder (pins, trust); the settings check.
- Accept: §2.3.2; the user settings are the only settings Koda writes; the load probe gates availability; a settings warning fails the spawn; a level whose settings the live check cannot prove is unavailable; the contract's `verified_against_help` and per-flag `verified` are set from the recorded CI help run.
- Tests: A-G-01 to A-G-09, A-K-05; contract test; gated live tests. · Risk: med · Deps: AG-13a, AG-22; `workspace_exec` also AG-14

**AG-26 · Prompts and pipelines follow the governed tools**
- Files: `config.py` prompt blocks; `tool_prompt.py`; `memory/procedural.py`; `utils/progress_tracker.py`; `utils/progress.py`; `utils/artifacts.py`.
- Accept: the system prompt no longer claims full filesystem access and does not change by level (Claude's prompt snapshot stays valid on resume); each turn's level is in the runtime context block; writes and commands go to governed tools, batched; procedural memory and progress learn from `shell_execute` and `file_*`; PT-BR content untouched.
- Tests: prompt snapshots; procedural and progress unit tests. · Risk: med · Deps: AG-22

**AG-27 · Governed loop and uniform supervised mode**
- Files: `queue_manager.py` (`_prepare_query_context`, `_run_agent_loop`, the Continue/Stop block at `:6513-6522`); `handlers/callbacks.py`; `utils/command_helpers.py`; evals.
- Accept: supervised pauses after each governed round on every provider; the budget stops the loop; `MAX_AGENT_TOOL_ITERATIONS` stays the ceiling and changes only on eval evidence; the MCP-bridge threshold is recorded.
- Tests: `test_agent_loop.py` per stub provider; an eval run. · Risk: med · Deps: AG-22, M0-E3-T2 · Gate: O-6 (approved)

### 7.8 Audit, UX, migration and release

**AG-28 · Spawn audit and execution detail**
- Files: the runner spawn paths → `services/audit.py`; provider-reported `tool_use` rows; `apps/web` execution detail.
- Accept: one event per spawn with the §2.6.2 fields and no prompt text (L2 fields read `unavailable` until AG-14); the UI shows them per turn.
- Tests: unit and redaction; a web component test. · Risk: low · Deps: AG-22

**AG-29 · Typed operator control and health**
- Files: `apps/web` `tab-recursos.tsx`, `shared/policy-card`, `tool-policy-segment.tsx`, `hooks/use-agent-editor.ts`, `lib/control-plane.ts`, the publish dialog, system health.
- Accept: §2.7 with PT-BR copy, the §2.8.4 modal; the raw JSON editor no longer edits this key; chat changes waiting for confirmation are shown.
- Tests: Vitest; `pnpm lint:web`, `test:web`, `build:web`. · Risk: med · Deps: AG-20, AG-21; health fields also AG-08

**AG-30 · Migration banner**
- Files: the web banner; the release-note list.
- Accept: §2.8.1 and §2.8.4: the banner lists the agents AG-21's migration lowered, from AG-09's report, with the Codex wording; restore goes through the confirmed publish.
- Tests: web banner test. · Risk: low · Deps: AG-09, AG-21, AG-29

**AG-31 · Release documentation and the end-to-end regression**
- Files: `docs/security/threat-model.md` (trust boundary, classes, residuals R-1 to R-8), `guardrail-test-matrix.md`; `docs/operations/hardening.md`, `upgrade.md` (§2.8.4); `docs/architecture/runtime.md`, `tool-registry-native-tools.md` ("provider built-in tools"); `.env.example`; the release note; the Docker regression job.
- Accept: §5.4 passes in CI and the §6 checklist is complete.
- Tests: G, G-RS, G-CI. · Risk: med · Deps: every other AG item

---

## 8. Open questions (evidence or delegated)

| # | Question | Owner | Status |
|---|---|---|---|
| O-4 | File OAuth with per-agent homes: does refresh-token rotation survive checkout and check-in with concurrent agents? | AG-13b evidence, then operator | Evidence-gated; default preference: env credentials |
| O-7 | Pinned versions and their proven flag set. | AG-02 | Done for 2.1.325 / 0.169.0 / 0.68.0; the offline probes (A-K-01 to A-K-05) and the live checks of AG-23 to AG-25 complete the proof |
| O-8 | Does Docker's default seccomp allow `landlock_*`? Does Codex's inner sandbox start in the runtime image without L2 (`off`)? | AG-08, AG-24 | Open. Settled `[V]`: Codex 0.169.0's inner sandboxes cannot start inside any Landlock domain on any host (§1.2), so under L2 Codex has `none` and `workspace_exec` only; this is not a property of Docker. Uid split only on proof. |
| O-9 | Can a later Codex pin run its shell through a Koda-supplied wrapper, so that a nested, narrower `koda-sandbox-exec` (no TCP) confines `workspace_write` and `read_only` under L2? | AG-24 on each CLI bump | Open; nothing depends on it |

## 9. Operator decisions

### 9.1 Questions for MISSION §13 sign-off

| # | Question | Why §13 | Recommendation |
|---|---|---|---|
| OQ-1 | **M3-E3-T1 go-live order.** Policy-approved governed shell, `shell_bg` and git start executing with M3-E3-T1. Should that go live only after AG-03 (no secrets in their env, hardened git), AG-14 (worker-side git confined), AG-15 (kernel `ExecuteCommand` confined) and AG-19 (the key out of `runtime-kernel`)? The alternative is to go live earlier with an accepted interim residual: until then governed shell runs unconfined in a container that mounts the master key. | Permission policy affecting users | **Require the four tasks first.** Otherwise invariants 3 and 4 are broken on the newly live path. |
| OQ-2 | **Provider switches need confirmation.** `/provider`, `/model` and functional-default commands publish their own change; one that would add capabilities (for example Codex on an agent at Workspace write) is refused in the chat and waits in the dashboard for an operator's confirmed publish (§2.2.3). | Externally exposed permission policy; changes a Telegram command's effect | **Approve.** Without it, a chat command gives the model a shell. |
| OQ-3 | **Provider CLIs ignore workspace and home customisation** (§2.3.5). (a) Executable customisation: hooks, MCP servers, plugins, extensions, skills, custom commands and agents, rules, discovery commands. (b) Instruction files: CLAUDE.md, AGENTS.md, GEMINI.md. Koda's own MCP servers and skills are unaffected. Gemini 0.68.0 cannot fully honour (b): it still appends GEMINI.md files on the path of files it reads (R-7). | Removes user-facing functionality | **(a) Approve**: needed for any level below `workspace_exec` to mean what it says, because a planted hook runs code at `read_only`. **(b) Approve** for Claude, Codex and Gemini's startup context, with the operator-authored agent instructions as the replacement, and accept R-7 for Gemini's JIT discovery until a Gemini pin has a switch. |
| OQ-4 | **CLI login homes move to an app-only path** (`STATE_ROOT_DIR/provider-logins`), copied and verified, the old copies deleted one release later (AG-13b, AG-32). | Touches production credentials | **Approve**, together with AG-19. |
| OQ-5 | **Retarget M1-E4-T7** (approval batch 1, fail closed on unsupported MCP egress) from the bubblewrap backend, which AG-16 deletes, to the helper's Landlock TCP rules. | Security policy; some MCP servers stop starting | **Approve** the retarget, so the approval is not spent on deleted code. |
| OQ-6 | **Codex under confinement.** On Codex 0.169.0 the inner sandboxes cannot start inside Landlock, and unconfined they read every file the uid can read. Choose: (i) Codex has no tools at Nenhuma and Somente leitura in every mode, and under `strict`/`filesystem` gets tools only at Execução no workspace (`danger-full-access` confined by L2); (ii) enforce Codex `read_only` with L2 alone, which gives its shell HTTPS egress to every host at the default level; (iii) keep Codex below `workspace_exec` unavailable until a pin proves a nesting sandbox. Today Codex runs `danger-full-access` everywhere. | Removes user-facing functionality (Codex reads at the default level); permission policy | **Approve (i)**: it is never weaker than today, keeps internal calls working on Codex-only installs (`none`), and becomes richer automatically if a pin's `IP` passes inside L2. |
| OQ-7 | **Delete the stored `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` values** one release after AG-24 stops reading them (AG-32). | Destructive settings operation | **Approve**: they are listed in the release note, and keeping them for one release lets a rollback use the operator's choice. |
| — | AG-10b activates delivered rules | Permission policy | Needs sign-off only if AG-09's diff section is non-empty (ADR-039). |

### 9.2 Recorded resolutions (revision 1, 2026-11-14)

The operator delegated these to the recommended long-term option ("siga com aquilo que você achar ser o mais recomendado … solução long-term ideal"). Revisions 2 and 3 do not change them.

| # | Resolution |
|---|---|
| O-1 | Approved: `koda-state` becomes app-only; worker data is copied (not moved) to `koda-worker-state` with verification; the key is not touched. |
| O-2 | Approved: `filesystem` is a documented installer choice on hosts with Landlock ABI < 4; minimum host kernel 5.13. |
| O-3 | Approved: the runtime evaluator becomes authoritative after the M5-E3-T2 diff report (Q-5). |
| O-4 | Evidence-gated (§8). |
| O-5 | Approved: MCP tool-policy edits take effect on publish. |
| O-6 | Approved as part of the Q-4 impact; documented in the release notes. |
| O-7 | Delegated to AG-02. |
| O-8 | Delegated to AG-08 (and AG-24 for Codex's inner sandbox outside L2). |

### 9.3 Plan follow-ups outside M1-E2 (for the orchestrator)

This revision edits only the M1-E2 block of MASTER_PLAN and the ADR-002 entry of DECISIONS. These items elsewhere need the orchestrator:

1. **M3-E3-T1:** deps per OQ-1 (AG-03, AG-14, AG-15, AG-19); approval package = `koda policy audit` section 3 (AG-09); Files add `koda/handlers/commands.py`, `koda/handlers/packages.py`, `koda/services/cli_runner.py`, `koda/services/shell_tools.py`, `koda/services/scheduled_job_runtime.py`; Do follows §2.9.1 (the "set the approval context" option is rejected); Tests add D11-13 and D11-14.
2. **M3-E3-T2:** Files add `koda/control_plane/approvals.py` and the internal routes; deps add AG-17 (its routes and token) and M1-E6-T3 (the MAC key); its done-when states that the MAC resists a worker only from AG-19 on (R-4); Tests add D12-13 and D12-14.
3. **M2-E1-T2:** do not import `approval_grants.json` as live grants (§2.9.2); pending operations are not imported.
4. **M0-E2-T4:** the supervised-write xfail models a human grant, not a policy allow (§2.9.1).
5. **M1-E4-T7:** per OQ-5.
6. **M3-E5-T1:** Files add `codex_runner.py` (Codex has `supports_native_resume=False`).
7. **MASTER_PLAN §5.2** row for M1-E2-T3 ("copy, verify, then move" the key) and the **§7.2** governance chain (R-01): reword to the AG mapping of §7.1; the key is not moved.
8. **M1-E6-T1 / ADR-035:** under `RUNTIME_CONFINEMENT=strict` the kernel listens on TCP, not a UNIX socket (§2.4.2). It still depends on M1-E2-T4, which no longer waits for M1-E4-T13.
9. **M1-E9-T1:** its Deps (M1-E2-T2, M1-E2-T4) now cover more AG items; it may track AG-31 instead.
10. **ADR-009 consequence** "the JSON fallbacks are retired after a one-time import": the import must skip grants (item 3); this is an implementation note, not a change to ADR-009's decision.
11. **M1-E4-T9** (MASTER_PLAN "Deps AG-09"): turn the dependency into a close condition (it starts with AG-06 and closes when AG-06 and AG-09 are done), and **ADR-039** (DECISIONS): say AG-10b where it says AG-10.
12. **REMAINING_RISKS R-01:** "M1-E2-T4 (environment and cwd allowlist)" becomes "M1-E2-T4 (environment allowlist); the work-dir invariant is AG-12 under M1-E2-T2"; add R-8 (`off` mode reads) under R-01's residuals.
