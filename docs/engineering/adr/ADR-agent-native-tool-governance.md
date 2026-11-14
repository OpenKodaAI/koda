# ADR-002 (detailed design): Agent-native tool governance and provider confinement

| Field | Value |
|---|---|
| Status | **Accepted** (Option C, operator, 2026-11-14; Q-4, [DECISIONS.md](../DECISIONS.md) ADR-002). **Revision 2** (2026-11-14) answers the round-1 SEC and REV reviews and waits for their round-2 reviews. The operator questions in §9.1 need MISSION §13 sign-off before the tasks they name go live. |
| Date | 2026-11-14 (revision 1); 2026-11-14 (revision 2) |
| Owner | SEC (ARCH). Review: SEC and REV (MASTER_PLAN M1-E2-T1). |
| Summary entry | [DECISIONS.md ADR-002](../DECISIONS.md#adr-002--agent-native-tool-governance-option-c) |
| Relation to other ADRs | **Implements** ADR-009 for the governed path (§2.9: D-011, D-012). **Amended by** ADR-039, which records AG-06's single fnmatch engine as the amendment of ADR-008 step 1. **Clarifies** ADR-025 (the control plane resolves secret references). **Supersedes** the relocation step of ADR-026 (the key stays where it is; its volume becomes app-only). **Depends on** ADR-010, ADR-011 and ADR-035 (M1-E6-T1). |
| Plan items | MASTER_PLAN M1-E2-T2, T3 and T4 are carried out by the AG items mapped in §7.1. M1-E2-T5 (scoped DB role) is unchanged. AG-06 is carried by M1-E4-T9 (ADR-039). |

**Evidence tags.** `[V]` means read or run during this design, with the citation or the command given. `[I]` means inferred; the task named alongside it supplies the proof. File references are relative to the repository root and to the worktree at commit dfa596c. Pinned CLI evidence names the pinned package and the command; Claude's help output is the fixture `tests/fixtures/provider_cli/claude-2.1.325-help.txt`. Every CLI was run with an empty scratch HOME and no credentials, and no model was called.

---

## Revision 2 log

Each row names what changed and the round-1 finding it answers (VALIDATION_REPORT "M1-E2-T1 reviews"; `SEC-n` and `REV-n` are the findings in review order, `DW-n` the M1-E2-T1 done-when items).

| # | Change | Answers |
|---|---|---|
| 1 | New §2.3: one row per provider mode. Every Claude permission mode (`acceptEdits`, `auto`, `bypassPermissions`, `default`/`manual`, `dontAsk`, `plan`), every Codex `sandbox_mode` × `approval_policy` pair (16 rows for the 15 pairs, because `workspace-write` splits on network, plus the bypass and auto-review flags), every Gemini approval mode (`default`, `auto_edit`, `yolo`, `plan`, and the `--yolo` alias). Each row names the Koda policy state (S1 to S10, §2.2.4) that selects it and the argv it produces. | DW-1; SEC done-when; REV done-when |
| 2 | §2.2.2: JSON Schema of the per-agent field, the derived governance block written at publish, and the error format. §2.6.1: the `agent.provider_builtin_tools_changed` audit event, written in the publish transaction. | DW-2; REV done-when (no schema, no event name, `record_audit_event` swallows failures) |
| 3 | §2.8.4: the text of the operator migration notice (release note, dashboard banner, escalation modal). | DW-3 |
| 4 | §5.2: a named test plan. Argv tests per provider for AG-22 to AG-25 (which replace M1-E2-T2), and the D-011 and D-012 tests for M3-E3-T1 and M3-E3-T2. | DW-4 |
| 5 | New §2.9: D-011 and D-012 designed. A per-call `ExecutionAuthorization` bound to the exact command and work dir, single use, never ambient; one Postgres request and grant store written only by the control plane, MAC-signed grants, single-use consumption through the control plane, expiry on restart, cross-process resolution by LISTEN/NOTIFY with a poll fallback. | SEC-1 (critical), REV-1 (critical) |
| 6 | M3-E3-T1's go-live order versus confinement becomes operator question OQ-1 (§9.1), with the recommendation to require AG-03, AG-14, AG-15 and AG-19 first. The plan edit is listed for the orchestrator (§9.3). | REV-1 (dependency part) |
| 7 | Codex compile rule (§2.3.3): `read_only` always compiles to Codex's own `--sandbox read-only`, on every host and in every confinement mode, which is today's dry-run argv. `danger-full-access` is emitted only at `workspace_exec` and only while L2 is enforced. No level is weaker than today. The static `inner_sandbox_ok` field becomes a runtime probe (`codex sandbox`, verified here). | SEC-2, REV-2 |
| 8 | §2.2.3: escalation is an increase in effective capability (`read`, `write`, `exec`, `egress`) per provider, not only a level raise. The published snapshot records a capability ceiling; the resolver refuses any provider whose capability exceeds it, which covers `/provider`, fallbacks and live model-policy writes. | SEC-3 |
| 9 | §2.2.3: the escalation check lives inside `ControlPlaneManager.publish_agent`, which every publish path calls. A publish needs an actor; the route, the six internal callers and the new migration are listed with their behaviour and a test each. Clone and first publish compare with the `read_only` baseline. | SEC-4 |
| 10 | §2.3.5: persistent instructions and extensions. Claude adds `--safe-mode` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`; Codex adds `project_doc_max_bytes=0`, `--ignore-rules`, `--ephemeral`, `--disable hooks`, `--disable plugins`, `--disable apps`; Gemini gets an allowlisted system-settings file (admin switches off, `hooksConfig.enabled=false`, `context.fileName=[]`). Provider homes are rebuilt before every spawn from a per-provider allowlist. New live canaries. The loss of workspace customisation is operator question OQ-3. | SEC-5 |
| 11 | §2.4.4: CLI login homes move to an app-only path; the sync-back is an allowlist of named credential files, schema-checked, done by the control plane through the AG-17 broker; config, hooks and instruction files never cross. Operator question OQ-4. | SEC-6 |
| 12 | §2.5.4: the credential residual extends to `read_only` and `workspace_write` until AG-23 and AG-25 prove the file tools' path confinement; live checks named. | SEC-7 |
| 13 | §2.5.3: the snapshot MAC binds `agent_id`, `version`, `published_at` and the snapshot hash; the supervisor refuses a version lower than the highest it has verified for that agent; the remaining rollback path is residual R-5, closed by M1-E2-T5. | SEC-8 |
| 14 | §2.4.2: network claims restated (TCP connect per port only; UDP and pathname UNIX sockets are not covered); Landlock signal and abstract-socket scoping applied at ABI ≥ 6; a UNIX-socket kernel target is refused under `strict`. | SEC-9 |
| 15 | Gemini levels use a `tools.core` allowlist instead of a `tools.exclude` denylist; `admin.secureModeEnabled` blocks `yolo` below `workspace_exec`. | SEC-10 |
| 16 | §2.6.2: the spawn event records the resolved L2 profile, the generated settings digest and the effective tool list. | SEC-11 |
| 17 | Gemini argv in the attached `--flag=value` form throughout; option-injection argv tests; `CODEX_BIN` and `GEMINI_BIN` recorded as one executable path inside the L2 read-only exec grant, with their changes audited. | SEC-12, REV-7, REV-8 |
| 18 | C10, C12 and §2.5 describe AG-04 and AG-05 as implemented, with the startup-window residual, the `.master.key.accept-undecryptable` file, the five `ensure_master_key` outcomes and the fingerprint audit event. | SEC-13, REV-10, REV-11 |
| 19 | MASTER_PLAN M1-E2-T2, T3 and T4 rewritten in this commit to map to the AG items; no bypass opt-in and no key copy remain. | SEC-14, REV-4 |
| 20 | Gemini system instructions stay on stdin, but user text is escaped so it cannot close the `<user_request>` block; named test. `GEMINI_SYSTEM_MD` was considered and rejected (§3). | SEC-15 |
| 21 | AG-06 is described as ADR-039 records it (one fnmatch engine, replay safeguard at delivery), and M1-E4-T9 is folded into it. | REV-3 |
| 22 | §7 dependencies fixed: AG-23 and AG-25 need AG-14 only for `workspace_exec`; AG-10 split into delivery (AG-10a) and rule activation (AG-10b, the §13 part), and AG-20 needs only AG-10a; AG-19 needs AG-05, AG-08, AG-17 and AG-18; compose hardening moves to AG-19b. | REV-5 |
| 23 | Codex native resume is off until proven (`exec resume` takes no `--sandbox`); Codex declares `supports_native_resume=False`, AG-24 depends on M3-E5-T1, and the bypass-flag sentence is removed. | REV-6 |
| 24 | Internal-call ceiling corrected: Claude `none`, Codex and Gemini `read_only`. | REV-7 |
| 25 | The claim that probes and argv cannot drift now covers flags only. Codex `-c` keys are now probed for existence and type (`codex -c <key>=<wrong type> features list`, verified); their behaviour stays a live check, and a level that depends on an unproven key is unavailable. | REV-9 |
| 26 | AG-18 no longer moves the approval JSON files; they are retired by M2-E1-T2 and replaced by §2.9. | REV-12 |
| 27 | The grep guard is replaced by assertions on the compiled argv of every profile, plus "no legacy token left in the contract". | REV-13 |
| 28 | One `koda policy audit` (AG-09) with three sections serves the upgrade report, AG-30 and the M3-E3-T1 approval package. | REV-14 |
| 29 | M1-E4-T7 (bubblewrap egress) is proposed for retargeting to AG-16's Landlock TCP rules: operator question OQ-5. | REV-15 |
| 30 | Stale task IDs updated (M5-E3-T7 → M1-E4-T13, M1-E6-T4 → M5-E6-T11, M7-E2-T1 → M2-E6-T1); every code citation re-read at dfa596c; `queue_manager.py` cited by function and line. | REV-16; SEC summary (line drift) |
| 31 | Smaller design (MISSION §12): AG-01 dropped (done by this commit and ADR-039); the `published_by` column dropped (the actor goes into the signed governance block and the audit event); the per-level Gemini denylists, the static `inner_sandbox_ok` field and the Codex L2-only read-only mode removed; no new task for D-011 and D-012 (M3-E3-T1 and T2 own them). | Task brief (anti-over-engineering) |

---

## 1. Context

### 1.1 Code today

**Provider built-in tools run ungoverned**

- **C1 [V]** Every turn runs with `permission_mode="bypassPermissions"` (`_prepare_query_context`, `koda/services/queue_manager.py:3122`). Supervised mode only sets `max_turns = 1` (`:3123`). `"plan"` is used only for scheduled dry runs (`:3122`), blocking artifact gaps (`:3465-3467`) and child runs (`:3593-3600`). The Claude argv adds `--permission-mode` from it and carries no tool flags (`koda/services/claude_runner.py:376-378, 665-667`); dry runs are forced to plan (`:92-96`).
- **C2 [V]** Codex defaults to `CODEX_SANDBOX=danger-full-access` and `CODEX_APPROVAL_POLICY=never` (`koda/config.py:269-270`). Both are operator system settings (`koda/control_plane/manager.py:608-609`). The startup check accepts a value set (`koda/startup_validator.py:67-72`) of which only `never` exists in Codex 0.169.0, and 0.169.0 refuses `untrusted` at config load (§1.2).
  - The runner discards `permission_mode` (`koda/services/codex_runner.py:629, 899`) and uses `--sandbox read-only` only for dry runs (`:286`).
  - Resume adds `--dangerously-bypass-approvals-and-sandbox` (`:259-260`), is ready only in the dangerous mode (`:312-330`) and refuses dry runs (`:283-284`).
  - So child runs, artifact-gap turns and the squad planner (`koda/squads/coordinator_engine.py:375-385`) run `danger-full-access` on Codex. The memory extractor passes `dry_run=True` (`koda/memory/extractor.py:192-193`), so it already runs `--sandbox read-only`.
- **C3 [V]** Gemini maps `bypassPermissions` to `yolo` and dry runs, child runs and artifact gaps to `plan` (`koda/services/gemini_runner.py:86-96`). The system instructions and the query go on argv as one `--prompt=` value (`:117`), wrapped in `<system_instructions>`/`<user_request>` tags without escaping (`:73-83`). The workspace is passed as `--include-directories` (`:116`).
- **C4 [V] AG-02 is implemented** (6d050b5). The CLIs are pinned in `packages/provider-clis` and installed by both images (`Dockerfile:4-11, 30-33`; `Dockerfile.runtime-kernel:3-10`). `koda/services/provider_cli_contract.py` holds the contract table (`:177-335`); `validate_args` refuses any token outside it (`:392-449`); probes fail closed (`:605-704`). `CODEX_BIN` and `GEMINI_BIN` are each one executable path, resolved by `provider_auth.provider_executable()` (`koda/services/provider_auth.py:439-460`); a command line is refused (`provider_cli_contract.py:623-629`); there is no `npx` fallback (`provider_auth.py:463-475`). The Gemini contract requires attached values (`provider_cli_contract.py:140-142, 334`).
- **C5 [V]** Koda governs only `<agent_cmd>` and OpenAI-style `tool_calls`, in `_run_agent_loop` (`queue_manager.py:4494`; policy at `:4884-4893`, execution at `:5115`). Claude's `tool_use` blocks have already run when Koda sees them and are kept as telemetry (`claude_runner.py:585-595, 905-906`). Koda's own shell, git and file tools are outside the secure default and are denied unless the agent's tool policy enables them (`koda/services/execution_policy.py:497-510`; `koda/agent_contract.py:1650-1659`; probed: `is_tool_allowed_by_secure_default` is false for every `shell_*`, `git_*` and `file_*` tool in the catalog).

**The policy layer is broken in ways the opt-in would inherit**

- **C6 [V]** `execution_policy` never reaches the worker. The runtime reads only `AGENT_EXECUTION_POLICY_JSON` (`config.py:1335`; `services/execution_policy.py:201-202`). The control plane emits the tool, autonomy and resource policy keys (`manager.py:3485, 3496, 12773-12774`) and ships the spec as `AGENT_SPEC_JSON` (`manager.py:803`), but never that key. Every dashboard-authored rule is ignored at runtime and the legacy branch runs (`services/execution_policy.py:479-575`).
- **C7 [V]** The two evaluators disagree: the runtime's order is deny > allow_with_preview > require_approval > allow (`services/execution_policy.py:40, 309`), the control plane takes the first match by priority. AG-06 (in progress as M1-E4-T9, ADR-039) makes one engine.
- **C8 [V]** Approvals are broken twice.
  - **D-011.** `run_shell_command` and the CLI runner refuse unless the ambient contextvar `_execution_approved` is true (`koda/utils/approval.py:66-73`; `koda/services/shell_runner.py:27-30`; `koda/services/cli_runner.py:107-115`). The agent loop never sets it, so policy-approved shell and git always fail. `execute_tool`'s supervised-write check uses the same contextvar (`koda/services/tool_dispatcher.py:779-790`). Only human commands (`approval.py:1125-1131, 1179-1341`) and scheduled shell jobs (`koda/services/scheduled_job_runtime.py:299-305`) set it.
  - **D-012.** Pending agent approvals are an in-memory dict with an `asyncio.Event` in the worker (`approval.py:1588, 1625-1730`; the loop waits at `queue_manager.py:4949`). The dashboard broker reads that dict from the supervisor process, where it is empty (`koda/services/approval_broker.py:152-163`). Persistence restores pending operations on start (`approval.py:86-153`; D-163).
- **C9 [V]** `publish_agent` snapshots the **draft** (`manager.py:12573`) and records no actor (`:12579-12613`). It has six callers besides the API route (§2.2.3). Policy writes (`put_section` `:12115`, `put_execution_policy` `:8652`, `put_model_policy` `:8583`) are not audited, and `record_audit_event` swallows failures by design (`koda/control_plane/audit.py:22-35`).

**Secrets and confinement**

- **C10 [V]** `runtime-kernel` mounts `koda-state` read-write (`docker-compose.yml:249`). The master key lives there at `STATE_ROOT_DIR/control_plane/.master.key` (`koda/control_plane/settings.py:52-53`), and so does `bootstrap.txt` (`koda/control_plane/bootstrap_file.py:36`). The supervisor forwards `STATE_ROOT_DIR` to workers (`koda/control_plane/supervisor.py:92`).
  - **AG-05 is implemented** (6d050b5). No process creates a key implicitly (`koda/control_plane/crypto.py:159-168`). Only the supervisor calls `ensure_master_key()` (`supervisor.py:223`), which ends in one of five outcomes: `fresh_install`, `upgrade`, `lost_key_reset`, `verified`, `rotation` (`crypto.py:89, 394-478`). A Postgres fingerprint row binds the key to the database; on upgrade the key must decrypt one of the newest stored values (`crypto.py:354-391`), and the lost-key path needs the operator file `.master.key.accept-undecryptable` naming the new key's fingerprint prefix (`crypto.py:53, 308-330`). Each outcome emits `security.master_key_fingerprint_recorded` (`crypto.py:336-341`). The previous key is read from `CONTROL_PLANE_MASTER_KEY_PREVIOUS` or its file (`crypto.py:171-179`).
  - Workers still decrypt in-process: `koda/services/mcp_connection_broker.py:17, 156` and `koda/services/mcp_oauth.py:732, 827`. AG-17's import-graph test enumerates any other path.
- **C11 [V]** Isolation is cgroups only; workers and CLIs run as the same uid. Kernel gRPC is unauthenticated on `0.0.0.0:50061` (`docker-compose.yml:245-246`; D-042), and the kernel also binds a UNIX socket when its target is a path (`rust/koda-runtime-kernel/src/server.rs:3223-3231`).
- **C12 [V]** Worker env and children:
  - the worker env holds the Postgres credentials and the S3 secret (`supervisor.py:66-69, 82`) and decrypted granted secrets;
  - CLI and tool child envs are allowlisted (`koda/services/provider_env.py:182-236`);
  - MCP stdio servers inherit the whole worker env (`mcp_bootstrap.py:90` → `mcp_manager.py:128` → `mcp_client.py:156-162`), and so do yt-dlp, ffmpeg and ffprobe (`link_analyzer.py:128, 186`; `artifact_ingestion.py:1511, 1568`; `utils/audio.py:123, 170, 291`; `utils/video.py:37`);
  - **AG-04 is implemented** (6d050b5): the worker's first statement makes it non-dumpable with `RLIMIT_CORE=0` and refuses to start otherwise (`koda/__main__.py:9-11`; `koda/process_hygiene.py:52-77`). Python's own startup runs before that, so a same-uid process can read a starting worker's env, and can kill the worker to reopen the window (`process_hygiene.py:24-33`; `docs/security/threat-model.md:96`). Only L2 closes it (§2.5.4, R-2).
- **C13 [V]** `DEFAULT_WORK_DIR` is HOME (`config.py:201`), and in compose HOME and `CLAUDE_CONFIG_DIR` sit on `koda-runtime` (`docker-compose.yml:29-31`), which `runtime-kernel` mounts read-write (`:250`). `SENSITIVE_DIRS` blocks every path under `/var/lib` (`config.py:775`; `tool_dispatcher.py:2389-2402`), which includes the Docker work dirs.
- **C14 [V]** The app also uses the worker's state subpaths: skill locks (`koda/skills/_package.py:1277`), the channel gateway (`koda/channels/gateway.py:133`), room photos (`koda/squads/room_photos.py:56`), TTS assets (`koda/services/kokoro_manager.py:25-33`, `supertonic_manager.py:22-30`). A one-time copy to a worker-only volume would split them.

### 1.2 Pinned CLI facts checked in this revision

| Fact | How checked |
|---|---|
| `claude` 2.1.325, `codex-cli` 0.169.0, `gemini` 0.68.0; Koda's contract check passes for all three. | `--version` of each; `python -m koda.services.provider_cli_contract` with the three on `PATH` → `ok: true` ×3. |
| Claude `--permission-mode` choices: `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`. `manual` is an alias of `default`. Per the CLI's own schema text: `default` prompts for dangerous operations, `acceptEdits` auto-accepts edits, `plan` executes no tools, `dontAsk` denies anything not pre-approved, `auto` lets a model classifier approve. | Help fixture lines 151-154; strings of the pinned binary (the SDK schema text and the `manual`→`default` mapping). |
| `--restricted` removes code-running tools and WebFetch unless `--tools` names them, ignores user, project and local settings, confines the file tools to the working directories, refuses `bypassPermissions`. It does **not** stop CLAUDE.md. | Help fixture lines 195-209. |
| `--safe-mode` disables CLAUDE.md, skills, installed plugins, hooks, MCP servers, custom commands and agents; auth, model selection, built-in tools and permissions work normally. The parser accepts it with `-p`. | Help fixture lines 213-223; parser probe `claude -p --safe-mode --restricted <unknown option>` reports only the unknown option. |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY` disables auto-memory. | Strings of the pinned binary (the memdir-disabled event reads that variable). |
| `--append-system-prompt-file`, `--max-turns` and `--no-session-persistence` are accepted by the parser. `--tools ""` disables all tools; `--permission-prompts none` denies anything that would prompt. `--bare` reads only `ANTHROPIC_API_KEY`. | Parser probe as above; help fixture lines 255-259, 155-162, 41-58. |
| Codex `exec` takes `--sandbox {read-only, workspace-write, danger-full-access}`, `--ephemeral`, `--ignore-rules`, `--ignore-user-config`, `--disable <feature>`, `--approve-for-me`, `--dangerously-bypass-approvals-and-sandbox`. `exec resume` has **no** `--sandbox`. The root `--ask-for-approval` lists only `on-request` and `never`. | `codex exec --help`, `codex exec resume --help`, `codex --help`. |
| Codex `approval_policy` parses as `untrusted`, `on-failure`, `on-request`, `granular`, `never`; `untrusted` fails config load ("no longer supported"). | `codex -c approval_policy="<v>" features list` for each value and a bogus one. |
| Codex config keys exist with these types: `sandbox_mode` (enum), `sandbox_workspace_write.network_access` (bool), `shell_environment_policy.inherit` (`core`/`all`/`none`), `shell_environment_policy.exclude` (sequence), `mcp_servers` (map), `web_search` (`disabled`/`cached`/`indexed`/`live`), `tools.web_search`, `project_doc_max_bytes` (usize; "applies only to project files"), `developer_instructions` (string), `hooks`. An unknown key is silently ignored. | `codex -c <key>=<wrong type> features list` (each typed key errors naming itself; `bogus_key_xyz=1` is accepted). |
| `--disable hooks`, `--disable plugins`, `--disable apps` turn those features off; an unknown feature name is an error. | `codex --disable <f> features list`. |
| Codex's inner sandbox works on this host (kernel 6.18): `read-only` refuses a write ("Read-only file system") and socket creation (EPERM); `workspace-write` allows writes in cwd and blocks sockets unless `sandbox_workspace_write.network_access=true`. The sandboxed shell can read the sandbox parent's environment. | `codex sandbox -c sandbox_mode=... -- <probe>`, with a canary variable in the parent env. Docker behaviour is `[I]` (AG-24). |
| Gemini `--approval-mode` choices: `default` (prompt), `auto_edit`, `yolo`, `plan` (read-only mode); `-y/--yolo`; `--skip-trust`; `-e/--extensions`; `-r/--resume`; `-p` is appended to stdin input. | `gemini --help`. |
| Gemini merges settings in the order defaults < system defaults < user < workspace (only if trusted) < **system**; `tools.exclude` merges by union, `mcpServers` by shallow merge, `hooks` by concat, `admin.*` by replace, other values are replaced. `tools.core` is an allowlist applied when built-in tools register. `--extensions=none` disables every extension. | `@google/gemini-cli@0.68.0` bundle: `chunk-VFM6AETN.js:37860-37871` (merge order), `:33969, 35429-35439, 36229-36301, 36562-36676` (strategies), `chunk-RCB6BI5H.js:384328-384339` (core allowlist), `chunk-ASDLQWJU.js:38762` (`none`). |
| In headless mode Gemini turns any "ask user" decision into deny, refuses to run in an untrusted workspace unless `--skip-trust` or `GEMINI_CLI_TRUST_WORKSPACE=true`, and forces `default` mode in an untrusted folder. Stdin is the prompt when stdin is not a TTY. `admin.secureModeEnabled` refuses `yolo`. `plan` mode routes the `auto` model to Pro. | Bundle `chunk-RCB6BI5H.js:366049-366051, 363628-363636`; `gemini-Q2FNZWQG.js:8765-8767, 8906-8935, 12665-12673, 19080-19087`. Auth fails before the trust check without credentials, so the order is `[I]` (AG-25). |
| Gemini 0.68.0 built-in tools include `invoke_agent`, `activate_skill`, `web_fetch`, `google_web_search`, `write_todos`, tracker tools and MCP resource tools; `save_memory` no longer exists. A denylist therefore misses new tools. | Bundle `chunk-RCB6BI5H.js` tool-name constants and `createToolRegistry` (`:384321-384385`). |
| The kernel here reports Landlock ABI 7 (revision 1 probe). Deployment hosts and Docker's default seccomp are `[I]`; AG-08 finds out. | — |

---

## 2. Decision

### 2.1 Invariants

1. **Koda policy is the only authority.** A provider built-in tool runs only at a level the agent's signed, published policy pre-authorises, lowered by every ceiling that applies, and only on a provider whose capability the published policy covers. Nothing raises it.
2. **Per-call approval exists only on the governed path.** Built-in tools have no approval state, because the CLIs run headless. Anything that needs a human goes through `<agent_cmd>`, `evaluate_execution_policy` and the approval pipeline (§2.9).
3. **Koda confines model-directed code.** Every process that runs code the model controls, or code it can plant, runs inside Koda's confinement or does not run. A provider's own sandbox is an inner layer.
4. **Never wider than the inner layer allows.** Koda never asks a provider sandbox for more than the effective level, except where Koda's own L2 enforces the level instead. In `RUNTIME_CONFINEMENT=off` the provider's own restriction is the only layer, and no level is weaker than today's behaviour.
5. **The model cannot reach control-plane secrets.** No process the model can reach holds or can read the master key, the bootstrap code, the worker's secrets, another agent's data or an unauthenticated control endpoint. Residuals are listed in §2.5.4.
6. **Fail closed.** An unverified CLI version, a missing flag, an unproven restriction or a missing kernel feature makes the capability unavailable, and the reason is shown. It never silently widens.

### 2.2 Governance model

#### 2.2.1 Field

- `execution_policy.provider_builtin_tools.level` is an ordered enum: `none < read_only < workspace_write < workspace_exec`. It is a typed block compiled at spawn, not a matched rule. There are no per-provider overrides and no free-form tool lists; those break across CLI versions.
- **Default `read_only`.** A missing block or key means `read_only`. It matches the governed path's baseline, where reads by enabled tools are allowed and writes need approval (`services/execution_policy.py:532-575`); it is Codex's lowest level; and reads stay cheap.
- **One delivery channel.** The published, signed `AGENT_SPEC_JSON` (AG-10a, AG-11). `AGENT_EXECUTION_POLICY_JSON` and its readers are deleted. The worker reads neither drafts (the `skills/_runtime.py` draft fallback is deleted) nor live control-plane rows for governance.
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

Derived at publish by `publish_agent` (never authored; a draft that contains it is rejected), inside the signed snapshot:

```json
"governance": {
  "provider_builtin_tools": {
    "level": "workspace_write",
    "capability_ceiling": ["read", "write"],
    "providers": ["claude", "gemini"],
    "published_by": "operator:7",
    "confirmed": true,
    "published_at": "2026-11-20T10:00:00Z",
    "previous_version": 41
  }
}
```

`providers` is every provider the draft's model policy lets the agent run: the default provider, the fallbacks and the functional defaults. `capability_ceiling` is the union of `capability(provider, level)` over them (§2.2.3).

#### 2.2.3 Capability, escalation and the publish gate

**Capability.** The contract table records, per provider and level, a conservative capability set over `read` (file reads), `write` (workspace writes), `exec` (model-chosen programs) and `egress` (model-chosen network connections):

| Provider | `none` | `read_only` | `workspace_write` | `workspace_exec` |
|---|---|---|---|---|
| Claude | `[]` | `[read]` | `[read, write]` | `[read, write, exec, egress]` |
| Codex | unsupported | `[read, exec]` (inner sandbox: no write, no network) | `[read, write, exec]` | `[read, write, exec, egress]` |
| Gemini | `[]` once proven, else unsupported | `[read]` | `[read, write]` | `[read, write, exec, egress]` |

**Escalation** is a publish whose level is higher than the baseline's, or whose `capability_ceiling` is not a subset of the baseline's. Adding Codex to a Claude `read_only` agent adds `exec` and is an escalation; so is raising the level.

**Runtime check (the resolver).** A turn on provider P at effective level L runs only if `capability(P, L)` is a subset of the published `capability_ceiling`. Otherwise P is refused for the turn with `capability_not_confirmed`, and the fallback chain skips it. This one check covers every way a provider can change without a publish: the Telegram `/provider` command (`koda/handlers/commands.py:433-447` → `koda/services/agent_settings.py:517-553`, a live `put_model_policy` write), `/model`, functional defaults and fallbacks.

**Publish gate.** `publish_agent(agent_id, *, actor)` takes a required keyword `actor = {kind: operator | system | telegram_user, id, confirm_escalation: bool}`. Inside it, before the version insert:

1. Compute the draft's governance block.
2. Baseline: the last published version's block. A version published before AG-20 counts as unrestricted (it ran with bypass). An agent never published has the baseline `{level: read_only, capability_ceiling: [read]}`.
3. On escalation, refuse unless `actor.kind == operator` and `actor.confirm_escalation`. The error names the new capabilities.
4. Write the version, the governance block (signed with the snapshot, AG-11) and the `agent.provider_builtin_tools_changed` event (§2.6.1) in one transaction; the publish fails if the event cannot be written.
5. Publishing is refused while any published agent still lacks the block (the AG-30 migration runs at control-plane start, before the API serves, next to `ensure_master_key` at `supervisor.py:223`).

Every publish path calls this one function (`manager.py:12568`):

| Caller | Actor | On escalation |
|---|---|---|
| Publish route (`koda/control_plane/api.py:3085-3095`) | operator session; `confirm_escalation` from the body, sent only by the escalation modal | publishes when confirmed |
| Onboarding (`manager.py:5909`) | operator; the onboarding step shows the modal when the chosen provider's `read_only` capability exceeds `[read]` (Codex) | publishes when confirmed |
| Supervisor reconcile, first publish (`supervisor.py:459-461`) | `system` | refused; the agent shows "Aguardando confirmação" |
| Runtime snapshot fallback (`manager.py:12634-12636`) | `system` | refused |
| Bootstrap (`koda/control_plane/bootstrap.py:53-56`) | `system` | refused |
| Legacy import (`manager.py:13101`) | `system:import`; like the migration, it may publish `read_only` with the imported providers' ceiling, which only lowers what those agents ran with | other raises refused |
| Chat toggles: voice and functional defaults (`agent_settings.py:482-492`, used at `:508, 614`) | `telegram_user` | refused with "Há uma elevação pendente no rascunho; publique pelo painel." |
| AG-30 migration | `system:migration`, may set `read_only` | n/a (only lowers) |

`clone_agent` (`manager.py:9937`) copies the execution policy into a new draft; its first publish compares with the never-published baseline, so a cloned `workspace_exec` policy needs confirmation. The chat toggles still publish unrelated pending draft changes, as today; that is not a capability change and stays out of scope.

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
| S7 | Internal call site: memory extractor, squad planner | provider floor: Claude `none`; Codex and Gemini `read_only` | `memory/extractor.py:192-193`; `coordinator_engine.py:375-385` |
| S8 | Level not faithful on this CLI and host (contract, Codex inner-sandbox probe, L2 status) | next lower faithful level | — |
| S9 | Process class M and the confinement mode's required layers missing (from AG-14 on) | provider refused for the turn | — |
| S10 | `capability(P, L)` not covered by the published ceiling | provider refused for the turn | — |

- The task-kind default `supervised` approval mode (`knowledge/task_policy_defaults.py`) is deliberately not a ceiling: general tasks default to it, so it would make every opt-in inert, and it is derived from the query text. Ceilings may come from such signals only because they only lower.
- Below the floor, the provider is refused for the turn; the level is never raised.
- **Supervised mode means the same on every provider:** built-ins capped at `read_only`; every governed write needs a human grant (§2.9.1); Koda's loop pauses after each governed round with the existing Continue/Stop buttons (`queue_manager.py:6513-6522`). The Claude-only `--max-turns 1` coupling is removed.
- **Governed-loop budget.** `MAX_AGENT_TOOL_ITERATIONS` stays the install-wide ceiling (operator setting `manager.py:650`; default 8, `config.py:1326`), and `max_budget` also stops the loop. The default changes only on M0-E3-T2 eval evidence (AG-27).
- **Evaluator.** AG-06 builds one engine with fnmatch for every rule; precedence is the most restrictive decision first (deny > require_approval > allow_with_preview > allow), then priority, then name; a rule's name is its audit `rule_id`; simulate and preview call it. This is ADR-039, which amends ADR-008 step 1 and moves its replay safeguard to delivery: AG-09 replays every stored policy under the legacy matcher and the engine before AG-10b activates rules. It changes nothing in production while rules are undelivered (C6).

### 2.3 Provider mode matrix

Each runner compiles the profile from the one contract table in `provider_cli_contract.py`, keyed by pinned version. The probes check every flag against `--help` (or the parser probe for hidden flags). Config and settings keys cannot be seen in `--help`: Codex keys are probed for existence and type (`codex -c <key>=<wrong type> features list`), Gemini settings keys only by the live checks. A level whose restriction depends on an unproven key or setting is unavailable (S8) until the live check passes.

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
env (allowlisted builder, AG-03): CLAUDE_CODE_DISABLE_AUTO_MEMORY=1, HOME and CLAUDE_CONFIG_DIR = the agent's provider home
```

`--strict-mcp-config` is passed with no `--mcp-config`, so no MCP server loads. `--add-dir` covers only the task's image directory.

| Level | `<T>` | Selected by | Class |
|---|---|---|---|
| `none` | `""` | S1 = `none`; S7 (Claude internal calls) | S |
| `read_only` | `Read,Grep,Glob` | S1 = `read_only` (default); S2 to S6 | S once AG-23 proves path confinement, else M |
| `workspace_write` | `Read,Grep,Glob,Edit,Write` | S1 = `workspace_write` with no lowering state | S once proven, else M |
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
gemini --model=M --output-format=json|text --extensions=none --skip-trust --approval-mode=<A>
cwd   = the workspace (no --include-directories)
stdin = <system_instructions>…</system_instructions><user_request>{escaped query}</user_request>
env   : GEMINI_CLI_SYSTEM_SETTINGS_PATH=<task_tmp>/gemini-system-settings.json (0600), HOME = the agent's provider home
```

The non-streaming runner uses `json` and the streaming runner `text`, as today (`gemini_runner.py:351, 525`). `--skip-trust` is required: headless Gemini refuses an untrusted workspace. Trusting it loads `.gemini/settings.json` from the workspace, under the system settings, so the system file pins every security-relevant key with a merge that the workspace cannot widen:

```json
{
  "tools": { "core": ["<per level>"], "discoveryCommand": "", "callCommand": "" },
  "mcpServers": {},
  "admin": {
    "secureModeEnabled": true,
    "mcp": { "enabled": false },
    "extensions": { "enabled": false },
    "skills": { "enabled": false }
  },
  "hooksConfig": { "enabled": false },
  "skills": { "enabled": false },
  "experimental": { "autoMemory": false, "enableAgents": false },
  "context": { "fileName": [] }
}
```

`admin.secureModeEnabled` is `false` only at `workspace_exec`. `mcpServers={}` alone is not enough, because `mcpServers` merges shallowly; `admin.mcp.enabled=false` (replace) is the switch.

| Level | `--approval-mode=` | `tools.core` | Selected by | Class |
|---|---|---|---|---|
| `none` | `default` | `[]` | S1 = `none`, once AG-25 proves it; until then unsupported and the floor is `read_only` | S |
| `read_only` | `default` | `list_directory, read_file, grep_search, glob` | S1 default; S2 to S7 | S once AG-25 proves path confinement, else M |
| `workspace_write` | `auto_edit` | the above plus `replace, write_file` | S1 = `workspace_write` | S once proven, else M |
| `workspace_exec` | `yolo` | the above plus `run_shell_command` | S1 = `workspace_exec` | M (needs AG-14) |

**One row per Gemini approval mode:**

| Mode | Koda state that selects it | Argv | Why |
|---|---|---|---|
| `default` | `none` and `read_only` levels: S1 default, S2 to S7 | `--approval-mode=default` | In headless mode any tool that would ask is denied, so only the allowlisted read tools run. |
| `auto_edit` | `workspace_write` | `--approval-mode=auto_edit` | Edit tools are auto-approved; no shell tool is registered. |
| `yolo` | `workspace_exec` only | `--approval-mode=yolo` | Every registered tool is approved; refused by `admin.secureModeEnabled` at any other level. |
| `plan` | None. Today: S2, S3, S4 (C3) | not emitted | Read-only by mode rather than by registry, adds plan-mode tools and reroutes the `auto` model to Pro. |
| `-y/--yolo` (alias) | None | not emitted | Same as `yolo`; one spelling only. |
| `-s/--sandbox` (Gemini's own container sandbox) | None | not emitted | Needs docker or podman inside the runtime image. |

Never emitted: `--prompt`/`-p` (the prompt goes on stdin), `--include-directories`, `--allowed-tools`, `--allowed-mcp-server-names`, `--policy`, `--admin-policy`, `--resume`, `--session-file`, `--raw-output`. Gemini 0.68.0 has native resume, but Koda keeps Gemini stateless with transcript replay (M3-E5-T1); adopting resume later is an optimisation, not part of this ADR. Floor: `read_only` until `none` is proven.

**Prompt channel.** System instructions stay on stdin, because `GEMINI_SYSTEM_MD` replaces the CLI's whole built-in prompt (§3). The query is escaped so that `<` and `>` inside a tag-like sequence that matches either delimiter become `&lt;` and `&gt;`, so user text cannot close `<user_request>` or open `<system_instructions>`.

#### 2.3.3 Codex 0.169.0

**Every level, new turn:**

```
codex exec --json --cd <workspace> --model M [--skip-git-repo-check]
  --ephemeral --ignore-rules --disable hooks --disable plugins --disable apps
  -c approval_policy="never"
  -c shell_environment_policy.inherit="core"
  -c shell_environment_policy.exclude=["*_API_KEY","*TOKEN*","*SECRET*","POSTGRES*","KNOWLEDGE_V2_S3*"]
  -c mcp_servers={} -c web_search="disabled" -c project_doc_max_bytes=0
  --sandbox <S> [-c sandbox_workspace_write.network_access=<bool>]
  [-c model_reasoning_effort=E] [--image P …] -
env: CODEX_HOME = the agent's provider home; developer instructions in its Koda-written config.toml (0600)
```

`web_search="disabled"` replaces `tools.web_search=false`; both keys exist, and the enum key is unambiguous. Developer instructions move off argv (today `-c developer_instructions=…`, `codex_runner.py:171-174`) into the Koda-written `config.toml`; `--ignore-user-config` is therefore not used.

**Compile rule.** `IP` is the inner-sandbox probe (`codex sandbox -c sandbox_mode="read-only" -- <python> -c <probe>` at worker start: the probe exits 0, a write to a temp file fails and a socket fails; cached per CLI fingerprint, shown in health and in the spawn event). `L2` means confinement status `enforced` or `filesystem_only` (§2.4).

| Effective level | `IP` ok | `IP` failed, L2 on | `IP` failed, L2 off |
|---|---|---|---|
| `none` | unsupported: the provider is refused; S7 uses `read_only` | same | same |
| `read_only` | `--sandbox read-only` | `--sandbox read-only` | `--sandbox read-only` |
| `workspace_write` | `--sandbox workspace-write -c sandbox_workspace_write.network_access=false` | same | same |
| `workspace_exec` | `--sandbox workspace-write -c sandbox_workspace_write.network_access=true` | `--sandbox danger-full-access` (L2 enforces the workspace and TCP ports) | not faithful: clamps to `workspace_write` |

When `IP` failed, Codex's own commands fail inside its sandbox at `read_only` and `workspace_write`. That is exactly today's dry-run behaviour (`codex_runner.py:286`); the model still answers, and the health page says why its commands fail. `danger-full-access` is emitted only at `workspace_exec` under L2, so in `off` mode no Codex level is weaker than today. Codex is class M at every level (it always has a shell); from AG-14 on, `strict` and `filesystem` refuse it when L2 is missing (S9).

**Resume.** `exec resume` takes no `--sandbox`, and whether it honours `-c sandbox_mode` is unproven. Native resume is off: Codex declares `supports_native_resume=False`, and follow-ups get transcript replay (M3-E5-T1, Q-13). `--dangerously-bypass-approvals-and-sandbox` is never emitted and leaves the contract. If AG-24's live check later proves `exec resume -c sandbox_mode="<S>"`, the contract adds `sandbox_mode` for the `exec_resume` scope and resume returns.

**One row per Codex sandbox and approval-policy pair:**

| # | `sandbox_mode` | `approval_policy` | Koda state that selects it | Argv |
|---|---|---|---|---|
| 1 | `read-only` | `never` | Effective `read_only`: S1 default, S2 to S7 (every host, every mode) | the block above with `--sandbox read-only` |
| 2 | `workspace-write` | `never` | Effective `workspace_write` (S1), and `workspace_exec` with `IP` failed and L2 off (clamped, S8) | `--sandbox workspace-write -c sandbox_workspace_write.network_access=false` |
| 3 | `workspace-write` + network | `never` | Effective `workspace_exec` with `IP` ok | `--sandbox workspace-write -c sandbox_workspace_write.network_access=true` |
| 4 | `danger-full-access` | `never` | Effective `workspace_exec`, `IP` failed, L2 on. Today: every non-dry-run turn (C2) | `--sandbox danger-full-access` |
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

Rows 2 and 3 differ only in `sandbox_workspace_write.network_access`. Today an operator could select rows 5 to 16 through `CODEX_APPROVAL_POLICY` (`codex_runner.py:175-176`); AG-24 removes that setting.

Why only `never`: `exec` is headless, so any policy that asks has nobody to ask; `on-request` and `granular` hand the decision to the model or to categories Koda does not govern, and `--approve-for-me` routes approvals to an automatic reviewer, which is an authority other than Koda policy (invariant 1). The `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` settings go (AG-24).

#### 2.3.4 HTTP providers

Ollama, llama.cpp, MLX and the OpenAI-compatible providers have no built-in tools; the field does not apply and the UI shows "não se aplica". Their ignored `permission_mode` and `dry_run` parameters are removed. Their `tool_calls` already go through the dispatcher and policy (`_run_agent_loop`). D-147 stays a separate item.

#### 2.3.5 Persistent instructions and extensions

A model with write access, or Codex's shell at any level, can plant files that a later spawn loads automatically. Koda closes the two places where that happens:

- **Provider homes** are per agent and are rebuilt before every spawn from an allowlist; everything else is removed:

  | Provider | Kept | Removed (examples) |
  |---|---|---|
  | Claude | `.credentials.json` (file OAuth only); `projects/<slug>/*.jsonl` session transcripts (needed for `--resume`) | `CLAUDE.md`, `settings*.json`, `skills/`, `agents/`, `commands/`, `plugins/`, `projects/*/memory/`, `.claude.json` (rewritten minimal) |
  | Codex | `auth.json` (file OAuth only); Koda's `config.toml`, rewritten | `AGENTS.md`, `rules/`, `skills/`, `hooks.json`, `sessions/` (`--ephemeral`) |
  | Gemini | `oauth_creds.json`, `google_accounts.json` (file OAuth only) | `settings.json`, `GEMINI.md`, `extensions/`, `skills/`, `commands/`, `tmp/` |

- **Workspace customisation** is not loaded: Claude `--safe-mode` (CLAUDE.md, skills, plugins, hooks, MCP, commands, agents) plus `--restricted` (project settings); Codex `project_doc_max_bytes=0` (AGENTS.md), `--ignore-rules`, `--disable hooks|plugins|apps`, and no `--trust` (so no project config layer, `[I]`, live canary); Gemini's system settings above (`context.fileName=[]`, hooks, skills, MCP and extensions off, discovery commands empty).

Executable customisation (hooks, MCP servers, plugins, extensions, rules, discovery commands) would run code at `read_only` and must stay off for the levels to mean anything. Instruction files (CLAUDE.md, AGENTS.md, GEMINI.md) only steer the model; turning them off removes a feature users may rely on. Both are operator question OQ-3. If the operator keeps instruction files, Claude omits `--safe-mode`, Codex omits `project_doc_max_bytes=0` and Gemini omits `context.fileName=[]`, and residual R-7 applies. Executable customisation stays off for Claude without `--safe-mode`: `--restricted` ignores the settings files that define hooks and enable plugins, the home rebuild removes installed plugins, `--disable-slash-commands` turns off skills and commands, `--strict-mcp-config` turns off MCP, and custom agents need the Agent tool, which is never in `--tools` (`[I]`, covered by the live canaries).

Live canaries (§5.3) cover each kept and removed item, in the workspace and in the provider home.

### 2.4 Confinement

#### 2.4.1 Threat and classes

**Threat.** A prompt-injected model drives built-in tools, governed shell or git, MCP servers and media tools. At risk: the master key, the previous key and `bootstrap.txt`; the worker env (DSN, S3 secret, granted secrets, runtime tokens); other agents' workspaces, homes and sessions; kernel RPC, the sidecars and publish integrity.

| Class | Members | If a required layer is missing |
|---|---|---|
| **M**: runs model-directed code | governed shell, `shell_bg` and git; worker-side git on workspaces; Codex at every level; Claude and Gemini at `workspace_exec`; any CLI level not proven self-confined; `cli_runner.py` spawns | Refused (from AG-14 on), with a reason pointing to `koda doctor` |
| **S**: self-confined CLI level | Claude `none`, `read_only`, `workspace_write` and Gemini levels below `workspace_exec`, once proven | Runs with the available layers |
| **U**: untrusted input, operator-installed code | MCP stdio servers, yt-dlp, ffmpeg, ffprobe, Playwright chromium | Runs with a minimal env and a health warning |
| **T**: trusted | Login flows in `app`, with an explicit allowlist and reasons | Not confined; HOME is the app-only login home (§2.4.4) |

#### 2.4.2 Layers

- **L0 Placement** (host-independent):
  - `koda-state` is mounted only in `app` (AG-19). The master key, the previous key and `bootstrap.txt` never enter `runtime-kernel`, and the key never moves.
  - Worker data moves to a new `koda-worker-state` volume (`WORKER_STATE_ROOT`), mounted in both `app` and `runtime-kernel`; every C14 consumer resolves through it in both processes. The supervisor forwards `WORKER_STATE_ROOT` instead of `STATE_ROOT_DIR` (`supervisor.py:92`).
  - CLI login homes move off `koda-runtime` to the app-only path (§2.4.4).
- **L1 Process hygiene:** AG-04 (implemented) makes the worker and the kernel non-dumpable with no cores. One allowlist builder makes every child env, with no DSN, S3 secret, granted secrets, runtime, kernel or broker token; this covers MCP and media spawns (AG-03). Prompts stay off argv, because `/proc/*/cmdline` stays readable even under Landlock `[I]`.
- **L2 OS confinement.** One Rust primitive, `rust/koda-runtime-kernel/src/confinement.rs`, exposed as the `koda-sandbox-exec` binary in the existing crate (no new service, ADR-001):
  - It applies `no_new_privs`, then a Landlock filesystem ruleset, then at ABI ≥ 4 TCP rules (connect only to `RUNTIME_CONFINEMENT_EGRESS_PORTS`, default `443,53`, plus the port of the provider's configured base URL; no bind), then at ABI ≥ 6 signal and abstract-UNIX-socket scoping, so a confined process cannot kill the worker or the kernel or reach their abstract sockets. Then it execs.
  - Landlock's ptrace restriction stops reads of the unconfined worker's and kernel's `/proc/<pid>/environ` and `mem`, and of sibling domains, on every ABI.
  - It exits 126 if any requested right cannot be enforced. Nesting only narrows.
  - **What it does not cover:** TCP rules are per port, so the allowed ports reach every host, and an internal service listening on 443, 53 or the provider port is reachable; UDP is not restricted (DNS and other UDP egress stay open); connecting to a pathname UNIX socket is not a Landlock right. So under `strict` the kernel listens on TCP only, and a UNIX-socket kernel target is refused at start (M1-E6-T1 constraint, §9.3).
  - Both spawn paths exec through it: worker-side spawns through `koda/security/process_confinement.py` (AG-14), and kernel `StartTask` and `ExecuteCommand`, whose profile the kernel computes itself (AG-15).

  Allowlist (anything else is denied, including worker-state, the artifact root, `/app`, `/workspace`, shared HOME, other agents' workspaces and homes, the login homes, and the `tmp_images` root):

  | Grant | Provider CLI | Governed shell and git | MCP stdio | Media tools | Chromium |
  |---|---|---|---|---|---|
  | read-only: `/usr`, `/lib*`, `/bin`, `/sbin`, `/etc`, `/opt`, `/proc`, required `/dev` nodes; `CODEX_BIN`/`GEMINI_BIN` must resolve inside these | yes | yes | yes | yes | yes |
  | read-write: task tmp | yes | yes | yes | yes | yes |
  | workspace | read-only at `read_only`, else read-write | read-write | only if the server declares it | no | no |
  | own per-agent provider home, read-write | yes | no | no | no | no |
  | other | — | — | server package read-only; state dir read-write | input read-only; output dir read-write | browsers path read-only; profile read-write |

- **L3 Provider layer (inner):** Claude `--restricted --safe-mode` and its tool lists; Codex's inner sandbox; Gemini's `tools.core` and settings. Per-agent homes live under `<RUNTIME_EPHEMERAL_ROOT>/provider-homes/<agent>/{claude,codex,gemini}` and are rebuilt per §2.3.5. A work dir is never HOME and never contains a provider home or a state root, checked by path component; this also applies to `agent_set_workdir` (`tool_dispatcher.py:1404-1416`).
- **L4 RPC:** kernel RPC authentication (M1-E6-T1) is a prerequisite for AG-15, which adds per-worker kernel tokens: the kernel binds each `StartTask` and `ExecuteCommand` to the token's agent and computes the floor itself (that agent's workspace, its provider home and the task tmp); a caller profile can only narrow it; a request without a profile is rejected. The control-plane worker broker (AG-17) has its own per-worker token.

#### 2.4.3 Modes

One setting, `RUNTIME_CONFINEMENT`, in `config.py` and `.env.example`.

| Mode | Required for class M | Use |
|---|---|---|
| `strict` (default) | filesystem + ptrace + TCP (ABI ≥ 4, kernel ≥ 6.7) | Normal |
| `filesystem` | filesystem + ptrace (ABI ≥ 1, kernel ≥ 5.13) | Explicit operator choice; audit event and a persistent health banner. Internal TCP ports stay reachable until M5-E5. |
| `off` | nothing; each provider's own restriction is the only layer (§2.3) | Development, macOS or native installs. Explicit config, a red banner, a startup log line and `confinement=off` in every spawn event. The installer never writes it. |

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
- Dynamic needs go through internal broker routes on the existing control-plane API: MCP connection env, MCP OAuth access tokens (refresh and write-back in the control plane only), the squad admin check (only the result returns), the ElevenLabs key, the image-generation key, CLI credential checkout and check-in (§2.4.4) and approval consumption (§2.9.2).
- Route auth: a per-worker token, minted by the supervisor at spawn, stored as a hash in Postgres (ADR-011), bound to `agent_id`, rotated on respawn, rate-limited; every resolution is audited by id, never value.
- ADR-025 clarification: "workers resolve secret references at start" means resolution by the control plane, into the spawn env or through the broker.

#### 2.5.3 Snapshot integrity (AG-11)

- Published snapshots are HMAC-signed with the ADR-025 HKDF signing key (M1-E6-T3). The MAC covers `agent_id`, `version`, `published_at` and the SHA-256 of the canonical snapshot JSON (governance block included).
- The supervisor verifies before building a worker env: the MAC, that `agent_id` and `version` in the MAC match the row and the agent being spawned (so another agent's signed snapshot is refused), and that the version is not lower than the highest version it has verified for that agent since it started (rollback while `app` runs is refused). On a failure it does not spawn and emits `security.snapshot_rejected`.
- A holder of the owner-role DSN can still, across an `app` restart, delete newer version rows or point `desired_version` at an older signed version (`manager.py:12600-12607`; `supervisor.py:459`). That is residual R-5, closed by M1-E2-T5 (the worker role gets no write on `cp_*` tables). A persisted high-water mark was rejected: restoring an older database backup would then refuse every agent.
- Live worker reads of `cp_mcp_tool_policies` (`services/execution_policy.py:127-165`) move into the snapshot (O-5).

#### 2.5.4 Documented residuals

| # | Residual | Closed by |
|---|---|---|
| R-1 | The CLI's own credential is readable by the model: at every Codex level and at `workspace_exec` through the shell (verified: Codex's sandboxed shell reads its parent's environment), and at `read_only` and `workspace_write` through Claude's Read or Gemini's `read_file` (`/proc/self/environ`, the provider-home credential files) until AG-23 and AG-25 prove the file tools' path confinement. The UI says so and recommends scoped API keys. | Path confinement live checks (AG-23, AG-25) for the read levels; never for shell levels |
| R-2 | AG-04's startup window: a same-uid process can read a starting worker's env and can kill the worker to reopen it. | L2 for every spawn: AG-14, AG-15, AG-16 together. Never under `off`, nor for class U on hosts without L2. |
| R-3 | The worker process, including in-process plugin code (D-005), holds the DSN. | M1-E2-T5, M1-E4-T4 |
| R-4 | Approval tables: a DSN holder can reset `uses` on a real grant (replaying a call a human approved, same exact fingerprint); in-process plugin code can forge a Telegram decision relay. | M1-E2-T5 (no write on approval tables); M1-E4-T4 |
| R-5 | Snapshot rollback across an `app` restart by a DSN holder. | M1-E2-T5 |
| R-6 | UDP egress, the provider base-URL port to any host, and internal services on 443, 53 or that port, are reachable from class M under `strict`. | Not closed by this ADR; documented in `docs/security/threat-model.md` (AG-31) |
| R-7 | Only if OQ-3(b) is declined: workspace instruction files persist instructions into later turns at write levels. | — |

### 2.6 Audit

Events go to the existing sinks (`control_plane/audit.py:22`, `services/audit.py`). Governance events (2.6.1 and the approval events) are written in the transaction of the action they record, and the action fails if they cannot be written (a `required=True` path in `record_audit_event`).

#### 2.6.1 Opt-in change: `agent.provider_builtin_tools_changed`

Emitted by `publish_agent` whenever the level or the capability ceiling differs from the baseline, including the AG-30 migration and the legacy import.

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
  "actor_kind": "operator | system | system:migration | system:import | telegram_user",
  "actor_id": "string",
  "confirmed": true,
  "snapshot_signature_id": "string",
  "reason": "publish | migration | import"
}
```

#### 2.6.2 Other events

1. **Configuration changes:** actor plus before/after diff on `put_section`, `put_execution_policy`, `put_autonomy_policy`, `put_model_policy` (`manager.py:12115, 8652, 8597, 8583`) and on system-settings writes, including `CODEX_BIN` and `GEMINI_BIN` (`manager.py:605, 617`).
2. **`provider.process_spawned`**, one per model-reachable process: agent, task, provider, process class; CLI version and contract id; requested and effective level with clamp reasons; capability; confinement mode, ABI and the enforced layers; the resolved L2 profile (workspace ro/rw, provider home, egress ports); the Codex `IP` result; the SHA-256 and effective tool list of the generated Gemini settings or Codex `config.toml`; the non-secret flag list (never prompt or query text); `CONTROL_PLANE_ACTIVE_VERSION` and the snapshot signature id.
3. **Provider-reported tool use:** built-in `tool_use` the CLIs report (`claude_runner.py:585-595, 905-906`; Codex JSON events) stored with `source=provider_reported`, arguments redacted and truncated.
4. **Secret broker:** one row per resolution.
5. **Approvals:** `approval.requested`, `approval.resolved` (resolver kind and id, decision, scope, fingerprint; never parameter values), `approval.grant_consumed`, `approval.expired`.
6. **Migration, restore and mode changes:** actor `system:migration` or the operator; `security.snapshot_rejected`; and AG-05's `security.master_key_fingerprint_recorded` (implemented, `crypto.py:336-341`).

### 2.7 Operator UX

Follows `apps/web/AGENTS.md` and `apps/web/CLAUDE.md`. Copy is PT-BR; existing PT-BR text is not translated.

- **Recursos tab**, next to the provider and model choice: a segmented control **"Ferramentas nativas do provedor"** with *Nenhuma / Somente leitura (padrão) / Escrita no workspace / Execução no workspace*. It replaces raw-JSON editing of this key.
- **Effective level per provider** from the resolver: floors ("Codex não suporta Nenhuma"), "não se aplica" for HTTP providers, each clamp with its reason, the capability, and the confinement status. Codex shows "Codex executa comandos em qualquer nível (em Somente leitura, sem escrita e sem rede)".
- **Escalation modal** (§2.8.4 text) whenever the publish diff contains an escalation, including a provider added to the model policy. Only after confirmation does the client send `confirm_escalation=true`. The agent list shows a badge for agents above `[read]`.
- **Execution detail** per turn: effective level, clamps, capability, confinement (from the spawn event) and provider-reported tool uses.
- **System health:** the mode, the ABI, the enforced layers, each CLI's pin match and the Codex inner-sandbox probe.
- **Rule simulator:** the existing evaluate endpoint, backed by the runtime engine (`apps/web/src/lib/control-plane.ts:1630` has no consumer today).
- **Approvals panel:** lists the agent's pending requests from Postgres (§2.9.2) with the verbs allow once, allow scope, deny with a reason.

### 2.8 Defaults, migration and rollback (MISSION §13)

#### 2.8.1 Defaults and existing agents (AG-30)

- New agents get `read_only`.
- `koda policy audit` (AG-09, read-only) runs before the upgrade and is attached to the release. It has three sections: (1) decision diffs once rules are delivered (legacy matcher versus the engine, ADR-039); (2) per agent on a CLI provider, the built-in tool use seen in traces (provider-reported Write, Edit, Bash; Codex commands); (3) newly live governed calls, meaning every agent and rule that would let `shell_execute`, `shell_bg`, `git_*` or supervised writes run once M3-E3-T1 lands. Section 3 is M3-E3-T1's approval package.
- At control-plane start, an idempotent migration gives every published agent that lacks the governance block a version N+1 built **from the last published snapshot** (never `build_draft_snapshot`, `manager.py:12461`), with `level=read_only`, the ceiling of its providers at `read_only`, signed, actor `system:migration`, and one audit event. The field is added to the draft only if the draft lacks it.
- The banner (§2.8.4) lists the agents that previously ran unrestricted. "Restaurar execução no workspace" goes through the confirmed publish; it cannot restore bypass, which no longer exists.

#### 2.8.2 Settings

- **Removed:** `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` (from `config.py`, `startup_validator.py` and the system-settings fields; persisted values cleared by a migration and listed in the release note; startup is not refused because of them); `AGENT_EXECUTION_POLICY_JSON`.
- **Changed (AG-02, implemented):** `CODEX_BIN` and `GEMINI_BIN` are each one executable path. A command line reports `unavailable:unverified_cli_version`; a missing binary `unavailable:cli_not_installed`.
- **New:** `RUNTIME_CONFINEMENT`, `RUNTIME_CONFINEMENT_EGRESS_PORTS`, `WORKER_STATE_ROOT` and `AGENT_WORKSPACE_ROOT`, each in `config.py`, `.env.example` and the docs.

#### 2.8.3 Installs, work dirs and rollback

- **Existing installs (AG-18, AG-19):** the release compose and CHECKSUMS are updated. On first start, `app` copies the worker subpaths from `koda-state` into `koda-worker-state`, verifies checksums and writes a marker (copy, not move); the legacy copies go one release later (AG-32, ADR-018). The key is not touched. The installer preflight runs `koda-sandbox-exec --self-test`; on ABI < 4 it requires the operator to choose `filesystem`, interactively or by flag, and records the choice.
- **Work dirs:** the default becomes `<AGENT_WORKSPACE_ROOT>/<agent_id>`. Files in the old shared HOME stay; the release note says how to reach them.

| Rollback scope | How |
|---|---|
| Per agent | Publish a higher level (confirmed, audited). |
| Per install | `RUNTIME_CONFINEMENT=filesystem`. |
| Per release | The previous images still find `koda-state` with the key, the legacy worker subpaths and the old login homes. Changes after the upgrade to skill locks, gateway config, room photos and CLI logins are not carried back (documented). Old code ignores the new field, the governance block, signatures and the approval tables; all migrations are additive. |

#### 2.8.4 Operator migration notice

**Release note and `docs/operations/upgrade.md` section (English):**

> ### Provider built-in tools now follow Koda policy (ADR-002)
>
> Claude Code, Codex and Gemini CLI no longer run with their own approvals turned off. Until this release Claude ran with `bypassPermissions`, Codex with `danger-full-access`, and Gemini in `yolo` mode, so an agent's provider could edit files and run commands without any Koda approval.
>
> **What changes when you upgrade**
>
> - Every agent gets the new setting **Provider built-in tools**, set to **Read only**. On upgrade Koda publishes a new version of each agent from its last published version, so pending drafts are not published. The report `koda policy audit`, which you can run before upgrading, lists the agents that used the provider's own edit or shell tools.
> - At **Read only**, Claude and Gemini can read files and do nothing else. Codex keeps its shell, inside its own read-only sandbox with no network. If Codex's sandbox cannot start on your host, its commands fail and the health page says why.
> - Edits and commands through Koda's own tools (files, shell, git) still ask for approval per call, and now work for agents whose policy allows them once M3-E3-T1 is approved.
> - Raising an agent to **Workspace write** or **Workspace exec**, or adding Codex to an agent, needs a confirmation in the dashboard. A chat command such as `/provider codex` cannot do it: the turn is refused with a link to the dashboard.
> - Provider CLIs no longer load hooks, MCP servers, plugins, extensions, skills or rules from the workspace or from their home directory, and no longer load CLAUDE.md, AGENTS.md or GEMINI.md (subject to operator approval, OQ-3).
> - Each agent has its own provider home. Logins you made in the dashboard keep working.
> - Removed settings: `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` (their stored values are cleared: {list}). `CODEX_BIN` and `GEMINI_BIN` must each be the path of one executable; a command line such as `npx -y @google/gemini-cli` reports `unavailable:unverified_cli_version`, and a missing binary reports `unavailable:cli_not_installed`.
> - The control plane refuses to start when the master key does not match this database. If the original key is lost for good, follow `docs/operations/backup-restore.md` (the `.master.key.accept-undecryptable` file).
> - Model-directed processes run under Linux Landlock confinement (`RUNTIME_CONFINEMENT=strict`). On hosts with Landlock ABI below 4 (for example Debian 12 or Ubuntu 22.04 GA kernels) the installer asks you to choose `filesystem`. Below kernel 5.13, Codex, governed shell and git are refused.
>
> **How to restore an agent's previous behaviour:** Dashboard → Agents → the agent → Recursos → Ferramentas nativas do provedor → Execução no workspace → confirm → publish. Bypass modes no longer exist.
>
> **Rollback:** the previous images still work with your data; changes made after the upgrade to skill locks, gateway config, room photos and CLI logins are not carried back.

**Dashboard banner (PT-BR), shown to operators until dismissed:**

> **As ferramentas nativas dos provedores agora seguem a política do Koda.** Nesta atualização, {n} agentes que usavam Claude, Codex ou Gemini com acesso irrestrito passaram para **Somente leitura**. Edições e comandos feitos pelas ferramentas do próprio provedor ficam bloqueados até você escolher outro nível. As ferramentas do Koda (arquivos, shell e git) continuam pedindo aprovação por chamada. [Ver agentes afetados] [Revisar política]

Per affected agent: "{agente} · {provedor} · antes: irrestrito · agora: Somente leitura · [Restaurar execução no workspace]".

**Escalation modal (PT-BR):**

> **Confirmar elevação para {nível}?** Com esta mudança, sem aprovação por chamada, o modelo poderá: {editar arquivos do workspace} {executar comandos} {acessar a rede por HTTPS} {ler a credencial do provedor usada por esses comandos}. {Codex executa comandos em qualquer nível.} A mudança fica registrada com o seu usuário. [Cancelar] [Confirmar e publicar]

Only the capabilities the escalation adds are listed.

### 2.9 Governed path: per-call authorisation (D-011) and cross-process approvals (D-012)

M3-E3-T1 and M3-E3-T2 implement this section. The flow is ADR-009's: decision, then request, then a fingerprinted grant, then execute.

#### 2.9.1 D-011: `ExecutionAuthorization`

- **Object.** A frozen dataclass in `koda/utils/approval.py`: `agent_id`, `task_id`, `tool_id`, `command_digest` (SHA-256 of the exact command string, or of the git argument string), `work_dir`, `basis` (`policy_allow | human_grant | operator_command | scheduled_job`), `rule_id`, `grant_id`, `snapshot_version`, `nonce`, `expires_at` (mint time plus the call's timeout).
- **Minted** only by `authorize_call(evaluation, call, ctx, grant=None)`, called in `_execute_tool_traced` after the policy decision (`tool_dispatcher.py:732-770`):
  - `deny` → never;
  - `allow` → `policy_allow`, with the matched `rule_id`;
  - `require_approval` or `allow_with_preview` → only with a grant consumed through the control plane for this call's fingerprint (2.9.2) → `human_grant`;
  - supervised mode: a write call (`_is_write_tool`) needs `human_grant` even when the rule allows it, which replaces the contextvar check at `tool_dispatcher.py:779-790`;
  - dry run and the S2 to S6 ceilings keep refusing writes (`tool_dispatcher.py:791-799`).
- **Passed explicitly**, never through a contextvar: `_execute_tool_traced` passes it as a keyword to the handler; only the shell, `shell_bg` and git handlers accept it and pass it to `run_shell_command(…, authorization=)`, `bg_process_manager.start(…, authorization=)` and `run_cli_command_detailed(…, authorization=)`.
- **Checked and consumed** by those runners: `agent_id` equals `AGENT_ID`, `tool_id` matches, the digest and the work dir equal the values they are about to run, it has not expired, and its nonce is unused (an in-process set). Anything else returns "Error: command execution not authorised." and logs `execution_authorization_refused`.
- **No ambient state.** `_execution_approved` and `check_execution_approved` are deleted. `asyncio` copies a context into every task it creates, so a contextvar set around `execute_tool` would leak into `shell_bg`'s task and any other task spawned meanwhile. The background task holds nothing it could reuse.
- **Human commands and scheduled jobs** mint their own: `with_approval` and `dispatch_approved_operation` mint `operator_command` for the typed command (`koda/handlers/commands.py:984, 1010`; `koda/handlers/packages.py:36, 62`), and the scheduled shell job mints `scheduled_job` from the published job definition (`scheduled_job_runtime.py:299-305`).
- **The per-agent enable is the published execution policy; no new field.** The secure default denies `shell_execute`, `shell_bg` and `git_*` (C5), so governed shell and git stay off until the operator publishes a rule that allows or asks for them. M3-E3-T1's choice "enable for the listed agents, or a per-agent enable that defaults to off" therefore means publishing rules for the listed agents (from `koda policy audit` section 3) or not.

#### 2.9.2 D-012: one request and grant store, written only by the control plane

- **Tables** (registry migration, BIGINT ids, agent scope):
  - `approval_requests`: `id`, `agent_id`, `worker_incarnation`, `origin` (`agent_call | operator_command`), `task_id`, `session_id`, `chat_id`, `tool_id`, `call_fingerprint`, `scope_fingerprint`, `description`, `preview_text`, `risk_class`, `status` (`pending | approved_once | approved_scope | denied | expired`), `created_at`, `expires_at`, `resolved_at`, `resolved_by_kind`, `resolved_by_id`, `resolution_reason`.
  - `approval_grants`: `id`, `request_id`, `agent_id`, `kind` (`once | scope`), `fingerprint`, `max_uses`, `uses`, `expires_at`, `issued_by_kind`, `issued_by_id`, `mac`, `created_at`.
- **One writer.** Only `app` writes either table, through one module, `koda/control_plane/approvals.py`. The worker calls internal routes with its per-worker broker token (AG-17); `agent_id` always comes from the token, never the body:
  - `POST /internal/approvals` creates a request (`expires_at = now + APPROVAL_TIMEOUT`, 300 s, `approval.py:80`), sends `NOTIFY approval_requested`, and returns its id; the worker then shows the Telegram card;
  - `POST /internal/approvals/{id}/telegram-decision` relays a Telegram button press (Telegram user id, decision, scope); the control plane accepts it only for the token's agent, only for a pending request, and only from a Telegram user on that agent's published allowed-user list;
  - `POST /internal/approvals/{id}/consume` with the call fingerprint: in one transaction the control plane locks the matching grant (`once`: exact fingerprint; `scope`: scope fingerprint), verifies its MAC, `agent_id`, `uses < max_uses` and `expires_at > now()`, increments `uses`, writes `approval.grant_consumed`, and returns `{grant_id, kind}`. The worker mints `human_grant` from that answer.
- **Resolution** has one function, `resolve_approval_request(request_id, decision, scope, resolver)`, used by the dashboard route (operator session; it replaces `approval_broker`'s in-memory resolve) and by the Telegram relay. It writes the status, inserts the grant with `mac = HMAC(signing key, canonical(id, request_id, agent_id, kind, fingerprint, max_uses, expires_at, issued_by))` using the ADR-025 signing key (M1-E6-T3, app-only after AG-19), writes `approval.resolved`, and sends `NOTIFY approval_resolved` with the request id.
- **Waiting.** The worker waits on `approval_resolved` through the one reconnecting LISTEN implementation (ADR-011, `koda/agents/listen_notify.py`), with a 5 s poll of the request status as the fallback, until `expires_at`; then it consumes.
- **Single use and expiry.** Allow once is `max_uses = 1`, and the consume transaction makes concurrent uses impossible. Scope grants keep the existing `ApprovalScope` TTL and `max_uses` (`approval.py:1413-1414`).
- **Restart.** At each worker spawn the supervisor marks that agent's `pending` requests from another incarnation `expired` (`approval.expired`, reason `worker_restart`). Nothing is restored, so D-163 disappears. Grants persist until they expire (ADR-009).
- **Cross-agent and self-approval.** Every row and MAC carries `agent_id`, and consume checks it against the token. The worker has no route that sets a status or inserts a grant; a grant row inserted directly with the worker's DSN has no valid MAC and is refused at consume. What a DSN holder can still do is residual R-4.
- **Retired:** `_PENDING_OPS`, `_PENDING_AGENT_CMD_OPS` and `_APPROVAL_GRANTS` (`approval.py:78-79, 1588`), the restore path (`approval.py:86-153`), and `koda/state/pending_approvals.py` and `koda/state/approval_grants.py` with their JSON fallbacks. Existing file grants are not imported as live grants: they were written by workers and would become MAC-signed grants (§9.3, M2-E1-T2).

---

## 3. Alternatives considered

| Alternative | Why not |
|---|---|
| **Fewest moving parts.** A boolean in `autonomy_policy`, honoured only in `guarded` mode; the key stays mounted; network unconfined; dashboard approvals proxied to the worker. | Contradicts ADR-002(B) and ADR-009 (which rejects the proxy). Inert for general tasks and dependent on a query-text classifier. *Grafted:* confining worker-side git, the AST spawn guard, the work-dir invariant, supervised stepping in Koda's loop. |
| **Key relocation** to an app-only volume (copy, verify, delete). | Surgery on key material, and a downgrade trap (older releases created a new key when the file was missing). Making the existing volume app-only reaches the same boundary. |
| **Default `none`, with `strict` imposed silently.** | Conflicts with Codex's floor, breaks internal calls on Codex-only installs, silently removes governed shell on kernels older than 6.7. |
| **Codex `read_only` through L2 only** (inner `danger-full-access`, Koda maps the workspace read-only), revision 1. | Under `off` it is weaker than today's dry run, and under L2 it adds HTTPS egress at `read_only`. Codex's own `--sandbox read-only` costs nothing and fails closed (SEC-2). |
| **Treat Codex as `workspace_exec` only** (no Codex below it). | Breaks Codex-only installs (memory extractor, squad planner) and the default level. |
| **Escalation as a level raise only.** | A provider switch at the same level adds a shell and egress unconfirmed (SEC-3). |
| **Gate in the API route**, revision 1. | Six internal callers publish the draft without the route (SEC-4). |
| **Keep the contextvar and set it around `execute_tool`** (ADR-009's rejected alternative). | It leaks into tasks created during the call, binds nothing to the command, and keeps five gates. |
| **Worker-verified grants** (an HMAC key in the worker). | The worker could then sign its own grants. Asymmetric keys add a key pair for the same result as one consume route. |
| **Wait for M1-E2-T5 and rely on DB grants only.** | M1-E2-T5 is §13-gated behind M2-E2-T2 and M2-E6-T1; the MAC closes self-approval now and the role closes the rest later. |
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
- One authority, one field, one resolver, one delivery channel, one publish gate, one approval store.
- Child runs, artifact-gap turns, dry runs and the squad planner become restricted on every provider, and on Codex never `danger-full-access` (C2). No level is weaker than today in any confinement mode.
- Provider switches cannot add a shell or egress without confirmation.
- Policy-approved governed shell and git can run, bound per call; dashboard approvals work across processes.
- The key and the bootstrap code leave every model-reachable container, and workers stop decrypting.
- Operators can trace who granted what.

**Negative and costs**
- Coding agents slow down until an operator opts them in; each governed round costs a resume, and Codex and Gemini follow-ups are replayed rather than resumed.
- More approvals. Workspace customisation stops loading (OQ-3).
- On hosts where Codex's sandbox cannot start, Codex commands fail below `workspace_exec`, and `workspace_exec` needs L2.
- Codex, governed shell and git need Landlock (kernel ≥ 5.13; ≥ 6.7 for `strict`).
- One new volume, which backups must include. CLIs must be upgraded deliberately; each bump re-runs the contract test and the live checks.

**Deleted**
- `permission_mode` and `dry_run` from `QueryContext` (`queue_manager.py:630` and its uses), `llm_runner` and every runner.
- `claude_runner._effective_permission_mode` (`:92-96`) and the duplicate argv builder; `gemini_runner._effective_approval_mode` (`:86-96`); the Codex dry-run and resume-in-danger branches (`codex_runner.py:259-260, 283-286, 312-330`).
- `CODEX_SANDBOX`, `CODEX_APPROVAL_POLICY` and their validator; `AGENT_EXECUTION_POLICY_JSON` and its readers.
- The `_execution_approved` contextvar, the in-memory approval stores and the approval JSON fallbacks.
- The worker-side decrypt paths (C10); the draft-spec fallback in `skills/_runtime.py`; the `/var/lib` prefix rule and the HOME fallback for work dirs.
- The unused `sandbox_policy` gates (TD-037) and the bwrap backend; the `KODA_AGENT_DEFAULT_*` claims in `docs/operations/hardening.md`; the "plan" mode concept.

---

## 5. Verification and test plan

**G** is the full suite (ruff, ruff format, mypy, pytest with coverage, the pnpm web checks); **G-RS** adds cargo fmt, clippy and test; **G-PG** runs on Postgres; **G-CI** is the docker smoke.

### 5.1 Cross-cutting automated checks

1. Resolver (AG-20): a table test over level × ceiling × provider × confinement × `IP`, and a monotonicity property test (adding a ceiling never raises the level or the capability).
2. An AST spawn guard over all of `koda/`: `subprocess.*`, `asyncio.create_subprocess_*`, `os.system`, `os.spawn*` and `os.posix_spawn` go through `process_confinement` or appear on the class T allowlist with a reason (AG-14).
3. "No secret reaches any child": CLIs, governed shell, git, MCP stdio, media tools, chromium (AG-03).
4. Import graph: the worker entrypoint cannot reach `decrypt_secret` or `encrypt_secret` (AG-17).
5. Evaluator parity vectors through the API and the runtime (AG-06).
6. Snapshot tamper, cross-agent replay and rollback are refused (AG-11).
7. The key-fingerprint matrix (AG-05, implemented: `tests/integration/test_master_key_fingerprint_postgres.py`, `tests/test_control_plane_master_key.py`).
8. Migrations run twice on G-PG (AG-18, AG-30).
9. Linux integration for `koda-sandbox-exec`: reads outside the allowlist denied; TCP connects to 5432, 8090 and 50061 denied (ABI ≥ 4); a UDP send and a connect to an internal listener on 443 recorded as allowed (R-6); `environ` of a sibling or parent denied; a signal to the worker denied (ABI ≥ 6); nesting cannot widen; exit 126 when enforcement is incomplete (AG-08).
10. Publish gate: one test per caller in §2.2.3, plus clone, first publish, and a publish that adds Codex to a Claude agent at the same level (AG-21).

### 5.2 Named tests

**Argv tests that replace M1-E2-T2's "per-runner argv unit tests"** (AG-22 to AG-25). Each runs the builder and `validate_args`; none calls a model.

| Id | Test (file) | Asserts |
|---|---|---|
| A-P-01 | `test_profile_reaches_every_call_site` (`tests/test_services/test_provider_builtin_tools.py`) | The four call sites, resume and verification turns all pass a resolved `BuiltinToolProfile`; S2 to S7 each produce the documented level. |
| A-P-02 | `test_compiled_argv_never_contains_bypass` (same file) | For every provider × level × {new, streaming, images} profile: no `--permission-mode` other than `dontAsk`, no `--approval-mode=plan`, no `yolo` below `workspace_exec`, no `danger-full-access` without L2, no `--dangerously-*`. |
| A-P-03 | `test_contract_has_no_legacy_tokens` (`tests/test_services/test_provider_cli_contract.py`) | After AG-23 to AG-25 every `legacy` flag and `legacy_choices` entry is gone; `approval_policy` choices are `("never",)`; `--permission-mode` choices are `("dontAsk",)`. |
| A-P-04 | `test_provider_switch_needs_confirmed_capability` (`tests/test_services/test_provider_builtin_tools.py`) | Claude `read_only` agent: a `/provider codex` turn is refused with `capability_not_confirmed`; the fallback skips Codex; after a confirmed publish it runs. |
| A-C-01 | `test_claude_argv_per_level` (`tests/test_services/test_claude_runner.py`) | Parametrised over the four levels: the every-level block, then `--tools`/`--allowedTools` as in §2.3.1. |
| A-C-02 | `test_claude_streaming_and_print_share_one_builder` | Streaming and non-streaming argv are equal apart from `--output-format`/`--verbose`. |
| A-C-03 | `test_claude_resume_keeps_level_flags` | `--resume ID` adds nothing else and removes nothing. |
| A-C-04 | `test_claude_images_add_only_task_dir` | `--add-dir` is the task's image dir, never the `tmp_images` root. |
| A-C-05 | `test_claude_system_prompt_in_0600_file` | No `--append-system-prompt` on argv; the file is 0600 and gone after the run. |
| A-C-06 | `test_claude_env_disables_auto_memory` | `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` and the per-agent HOME. |
| A-C-07 | `test_claude_option_like_values_stay_values` | A model id or file path starting with `-` does not change the mode or tools. |
| A-C-08 | `test_claude_workspace_exec_refused_without_l2` | From AG-14 on, `workspace_exec` under `strict` without L2 is refused (S9). |
| A-X-01 | `test_codex_read_only_uses_inner_read_only` (`tests/test_services/test_codex_runner.py`) | Effective `read_only` gives `--sandbox read-only` whatever `IP` and L2 are. |
| A-X-02 | `test_codex_workspace_write_no_network` | `--sandbox workspace-write -c sandbox_workspace_write.network_access=false`. |
| A-X-03 | `test_codex_workspace_exec_by_probe_and_l2` | `IP` ok → workspace-write with network; `IP` failed and L2 on → `danger-full-access`; `IP` failed and L2 off → clamped to `workspace_write`. |
| A-X-04 | `test_codex_off_mode_never_danger_full_access` | Under `off`: default level, dry run, child run, artifact gap, squad planner and memory extractor never emit `danger-full-access` (SEC-2). |
| A-X-05 | `test_codex_approval_policy_is_never` | Exactly one `approval_policy`, `never`; no `--approve-for-me`. |
| A-X-06 | `test_codex_resume_is_replay` | `supports_native_resume=False`; no `exec resume`; no bypass flag in any argv. |
| A-X-07 | `test_codex_customisation_disabled` | `--ephemeral --ignore-rules --disable hooks --disable plugins --disable apps`, `project_doc_max_bytes=0`, `mcp_servers={}`, `web_search="disabled"`, no `--trust`, no `developer_instructions` on argv. |
| A-X-08 | `test_codex_none_refused` | `none` refuses the provider; S7 resolves to `read_only`. |
| A-X-09 | `test_codex_images_and_stdin_prompt` | `--image` paths, prompt on stdin (`-`). |
| A-G-01 | `test_gemini_argv_attached_values` (`tests/test_services/test_gemini_runner.py`) | Every value attached; `--extensions=none --skip-trust`; no `--prompt`, no `--include-directories`. |
| A-G-02 | `test_gemini_settings_per_level` | The system-settings file per level: `tools.core` lists, admin switches, `hooksConfig`, `context.fileName=[]`, `secureModeEnabled` false only at `workspace_exec`; file 0600. |
| A-G-03 | `test_gemini_modes_per_level` | `default`/`auto_edit`/`yolo` as in §2.3.2; never `plan`, never `-y`. |
| A-G-04 | `test_gemini_prompt_on_stdin` | The query and instructions reach stdin, not argv. |
| A-G-05 | `test_gemini_option_like_values_cannot_change_mode` | A model id `-y` or a query `--approval-mode=yolo` changes neither the mode nor the tools. |
| A-G-06 | `test_gemini_user_text_cannot_forge_system_block` | A query containing `</user_request><system_instructions>` arrives escaped (SEC-15). |
| A-G-07 | `test_gemini_streaming_uses_same_profile` | `text` and `json` runs differ only in `--output-format`. |
| A-K-01 | `test_codex_config_keys_probe_types` (`tests/test_services/test_provider_cli_contract.py`) | The probe runs `codex -c <key>=<wrong type> features list` for each contract key and fails closed when a key stops erroring (a renamed key would be silently ignored). |
| A-K-02 | `test_codex_feature_disables_probe` | `codex --disable hooks --disable plugins --disable apps features list` shows all three false. |
| A-K-03 | `test_codex_inner_sandbox_probe` | `IP` from `codex sandbox`: ok, write refused, socket refused; cached per binary fingerprint. |

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

**D-012 tests that M3-E3-T2 adds** (`tests/integration/test_approvals_postgres.py` on G-PG, unless noted):

| Id | Test | Asserts |
|---|---|---|
| D12-01 | `test_dashboard_lists_and_approves_a_worker_request` | Two processes: the worker creates a request; the control-plane API lists it; an operator approves; the worker's call executes. |
| D12-02 | `test_worker_cannot_self_approve` | No internal route resolves; a grant row inserted with the worker's DSN is refused at consume (bad MAC); the worker token on the resolve route gets 403. |
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

### 5.3 Live provider checks

Credentials required; gated by `tests/_provider_plugin.py`; mocked tests are never proof (MISSION §7.6). Per provider × level:

- a write at `read_only` leaves no file; `.git/` writes are refused below `workspace_exec`; a symlink out of the workspace is refused;
- the file tools refuse `/proc/self/environ`, `/proc/<ppid>/environ` and the provider-home credential files at every level below `workspace_exec` (R-1);
- canaries planted in the workspace and in the provider home are ignored: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.claude/settings.json` with a hook, `.claude/skills`, `.claude/agents`, `.claude/commands`, `.mcp.json`, `.codex/config.toml`, Codex `rules/`, `.gemini/settings.json` with a hook, an MCP server and a discovery command, `.gemini/extensions`; auto-memory does not persist across turns;
- a hook or config planted in a per-agent home never reaches `app` through check-in;
- Codex: `--sandbox read-only` blocks writes and network; `workspace-write` blocks network unless enabled; Gemini: only the `tools.core` tools are offered, `yolo` fails below `workspace_exec`, the prompt is read from stdin, `--skip-trust` runs headless;
- `--append-system-prompt-file` and `--safe-mode` work with subscription auth;
- per-agent OAuth refresh holds over repeated cycles with two agents running at once (O-4).

### 5.4 Docker checks (G-CI docker-smoke; evidence in VALIDATION_REPORT.md)

In the runtime-kernel image, a process spawned the way the worker spawns: does not see `/var/lib/koda/state`; cannot read worker-state, another agent's workspace or home, the login homes or `/app`; cannot read `/proc/<worker|kernel>/environ`; cannot TCP-connect to postgres, app:8090, the kernel or the sidecars in `strict`; cannot call kernel RPC without a token; cannot use agent A's kernel token for agent B's paths. Also: the upgrade copies worker-state and decrypts every secret, and rollback to the previous images works; a `read_only` root on `runtime-kernel` passes the CLI smoke; the installer preflight records the mode; the Codex `IP` result in the image is recorded.

**Host matrix:** self-test results on kernel 6.1 (expected `filesystem`), on kernel ≥ 6.8 (expected `strict`) and on Docker Desktop `[I]`.

---

## 6. Release gate

The default ships only when all of these are done:
- every AG item in §7 that is not marked done, and AG-06 (M1-E4-T9);
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
| M1-E2-T1 · this ADR | — (AG-01 merged: the plan, DECISIONS and ADR-039 edits are done; the threat-model edit moves to AG-31) |
| M1-E2-T2 · Governed-by-default provider permission modes | AG-02 (done), AG-07, AG-08, AG-09, AG-10a, AG-10b, AG-11, AG-13a, AG-13b, AG-14, AG-15, AG-16, AG-19b, AG-20 to AG-31 |
| M1-E2-T3 · `koda-state` off the runtime-kernel (the key stays put) | AG-05 (done), AG-17, AG-18, AG-19, AG-32 |
| M1-E2-T4 · Environment and working-directory allowlist | AG-03, AG-04 (done), AG-12 (so the task also depends on M1-E4-T13) |
| M1-E2-T5 · Scoped Postgres role | no AG item; unchanged in scope, and it closes residuals R-3 to R-5 (§2.5.4) |
| M1-E4-T9 (ADR-039) | AG-06 |

M1-E2-T4 keeps only the environment and work-dir items because M1-E6-T1 depends on it for the token-stripping allowlist; putting confinement there would block kernel RPC auth on Landlock work it does not need.

### 7.2 Done

- **AG-02** pinned CLIs, contract table, fail-closed probes (6d050b5; C4).
- **AG-04** non-dumpable worker and kernel (6d050b5; C12).
- **AG-05** fail-closed master key with a Postgres fingerprint (6d050b5; C10, §2.5.1).

### 7.3 Foundation (no dependencies)

**AG-03 · Allowlisted env for every child process** (M1-E2-T4)
- Files: `mcp_bootstrap.py:90`, `mcp_manager.py:128`, `mcp_client.py:156-162`; `link_analyzer.py:128, 186`; `artifact_ingestion.py:1511, 1568`; `utils/audio.py:123, 170, 291`; `utils/video.py:37`; worker-side git (`queue_manager.py`, `runtime/controller.py`); `provider_env.py:182-236`.
- Accept: no child gets `env=None` or an inherited env; MCP servers get their connection env plus the safe base; worker-side git adds `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `-c core.fsmonitor=false -c core.hooksPath=/dev/null`, `--no-ext-diff`, `--no-textconv`; the CLI env sets `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.
- Tests: §5.1.3. · Risk: med (MCP servers that relied on inherited vars) · Deps: —

**AG-06 · One evaluator** (M1-E4-T9, ADR-039; in progress)
- Accept: deny > require_approval > allow_with_preview > allow, then priority, then name; fnmatch for every rule; `name` is the `rule_id`; `match` and `selectors` normalise to one key; a `mcp_*__delete_*` deny is enforced; evaluate equals the runtime for every vector.
- Tests: parity vectors (§5.1.5). · Risk: med (no production effect, C6) · Deps: —

**AG-07 · Audit of configuration changes**
- Files: `manager.py:12115, 8583, 8597, 8652, 12568`; the system-settings writer; `control_plane/audit.py` (`required=True` path).
- Accept: every policy, model-policy and system-settings write records the actor and a before/after diff; governance events are transactional (§2.6).
- Tests: G-PG; route tests. · Risk: low · Deps: —

**AG-08 · Confinement primitive, mode setting and doctor**
- Files: `rust/koda-runtime-kernel/src/confinement.rs`; `src/bin/koda-sandbox-exec.rs`; `Cargo.toml` (`landlock` crate, exact version); `config.py`; `.env.example`; `sandbox_doctor.py`; `docs/operations/sandbox-doctor-runbook.md`.
- Accept: `--self-test` prints the ABI and the enforced layers (filesystem, ptrace, TCP, scoping) as JSON; the profile follows §2.4.2 and DNS works; exit 126 when enforcement is incomplete; `filesystem` and `off` emit an audit event and a banner; a UNIX-socket kernel target is refused under `strict`; Docker's default seccomp behaviour is recorded.
- Tests: cargo unit tests; Linux integration (§5.1.9) on an ABI ≥ 6 runner. G-RS. · Risk: high · Deps: —

**AG-10a · Deliver the published spec**
- Files: `config.py:1335` (delete); `services/execution_policy.py:198-203`; `tool_prompt.py`; `scheduled_jobs.py`; `queue_manager.py` (`_prepare_query_context`); `manager.py` preview accessor.
- Accept: one accessor reads the signed `AGENT_SPEC_JSON`; the worker takes `provider_builtin_tools` and the model policy from it; `execution_policy` rules from it stay inactive until AG-10b; a missing or invalid spec gives secure defaults; `AGENT_EXECUTION_POLICY_JSON` is gone.
- Tests: unit; G-PG publish → env → read. · Risk: med · Deps: —

**AG-12 · Workspace roots, deny roots and the work-dir invariant** (M1-E2-T4; inside M1-E4-T13's resolver)
- Files: `config.py:201, 766-780`; `utils/workdir.py`; `tool_dispatcher.py:1404-1416, 2389-2402`; `.env.example` (`AGENT_WORKSPACE_ROOT`).
- Accept: governed file tools work under `/var/lib/koda/runtime/workspaces/<agent>`; deny roots are checked by path component; a work dir equal to or containing HOME, a state root, a provider home, a login home or `RUNTIME_KERNEL_ROOT` is refused; the HOME fallback is gone.
- Tests: predicate matrix emulating the compose layout. · Risk: med · Deps: M1-E4-T13

**AG-17 · Control-plane worker broker: workers never decrypt** (M1-E2-T3)
- Files: `control_plane/api.py` (internal routes); `supervisor.py` (mint the token, store its hash); a worker client; `mcp_connection_broker.py`, `mcp_oauth.py` and the other paths the import-graph test finds.
- Accept: the import-graph test passes; agent A's token gets 403 on agent B's secrets; a respawn revokes the previous token; OAuth refresh and write-back happen in the control plane only; MCP, OAuth MCP, the squad check, TTS and image generation still work. The same token authenticates the credential and approval routes (§2.4.4, §2.9.2).
- Tests: auth matrix; G-PG two-process test. · Risk: high · Deps: AG-05 (done)

**AG-18 · `WORKER_STATE_ROOT` and the `koda-worker-state` volume** (M1-E2-T3)
- Files: `config.py`; the C14 consumers; `supervisor.py:92`; an app-side copy migration (checksums, marker); both compose files (add the volume; `koda-state` stays for now); CHECKSUMS; `tests/test_installation_assets.py`.
- Accept: both processes resolve the same paths; a test lists every `STATE_ROOT_DIR` consumer and classifies it as control-plane-only, worker-state, or retired (`state/pending_approvals.py`, `state/approval_grants.py`: retired by M2-E1-T2 and §2.9.2, not moved); an upgraded install keeps skill locks, gateway config and room photos.
- Tests: migration run twice; compose render. · Risk: med · Deps: —

### 7.4 Policy delivery and integrity

**AG-09 · `koda policy audit` (read-only, one command)**
- Files: `koda/cli/migrate.py` (subcommand); docs.
- Accept: the three sections of §2.8.1 per published agent; writes nothing; its output is the upgrade report, AG-30's banner list and M3-E3-T1's approval package.
- Tests: G-PG fixture with legacy-compiled rules and recorded traces. · Risk: low · Deps: AG-06

**AG-10b · Activate delivered rules**
- Files: the AG-10a accessor (switch on `execution_policy` rules).
- Accept: a published deny rule is enforced in the worker; the preview equals the live tool set.
- Tests: G-PG publish, build env, enforce. · Risk: high · Deps: AG-06, AG-09, AG-10a · Gate: §13 sign-off if AG-09's diff section is non-empty (ADR-039)

**AG-11 · Signed snapshots**
- Files: `manager.py` publish (sign); supervisor env build (verify); `skills/_runtime.py` (delete the draft fallback); `services/execution_policy.py:127-165` (MCP tool policy from the snapshot).
- Accept: §2.5.3: a tampered row, another agent's snapshot and a version below the verified high-water mark stop the spawn with `security.snapshot_rejected`; the worker never calls `get_agent_spec`.
- Tests: tamper, cross-agent and rollback tests; G-PG. · Risk: med · Deps: AG-10a, M1-E6-T3 · Gate: O-5 (approved)

### 7.5 Provider homes and spawn confinement

**AG-13a · Per-agent provider homes**
- Files: `provider_env.py`; `manager.py` (provider home paths); Codex instructions into the Koda-written `config.toml`.
- Accept: each agent has its own Claude, Codex and Gemini home, rebuilt before each spawn from the §2.3.5 allowlist; agent B cannot read agent A's sessions; env credentials work; file OAuth modes keep using the canonical login home until AG-13b.
- Tests: unit (rebuild removes every non-allowlisted file); G-PG. · Risk: med · Deps: —

**AG-13b · Login homes app-only; credential checkout and check-in**
- Files: the login flows in `app`; AG-17 broker routes; the copy migration.
- Accept: §2.4.4; canonical login homes on `koda-state`, copied and verified; only the named files cross, schema-checked; a planted hook or config never reaches `app`.
- Tests: unit; G-PG; recorded live refresh evidence. · Risk: high (OAuth rotation) · Deps: AG-13a, AG-17 · Gate: OQ-4; O-4 evidence

**AG-14 · Class M and S spawns through the helper (worker side)**
- Files: new `koda/security/process_confinement.py`; the runner spawn sites (`claude_runner.py`, `codex_runner.py`, `gemini_runner.py`); `cli_runner.py`; `shell_tools.py`; the git tool spawns; worker-side git in `queue_manager.py` and `runtime/controller.py`.
- Accept: the AST guard passes; class M refuses exactly when the mode's required layers are missing (S9); a stub CLI or shell cannot read the §5.4 targets.
- Tests: argv-prefix tests; AST guard; Linux integration. · Risk: high · Deps: AG-03, AG-08, AG-12; the provider-CLI spawns also AG-13a

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

**AG-32 · Delete the legacy subpaths and login homes** (the release after AG-19 and AG-13b, ADR-018)
- Accept: removed only when the marker and checksums match; the release note says rollback past this release loses them.
- Tests: migration test. · Risk: low · Deps: AG-19 and AG-13b shipped in a prior release

### 7.7 Governance field and runners

**AG-20 · `provider_builtin_tools` field, capability and resolver**
- Files: new `koda/services/provider_builtin_tools.py`; the execution-policy normalize and validate (delegate); the capability table in `provider_cli_contract.py`; the `agent_spec` summary; OpenAPI.
- Accept: §2.2.1 to §2.2.4; the schema and error format of §2.2.2; one import serves the runtime, publish, preview and simulator.
- Tests: §5.1.1; A-P-04. · Risk: med · Deps: AG-10a

**AG-21 · Publish gate inside `publish_agent`**
- Files: `manager.py:12568` and every caller in §2.2.3; `api.py:3085-3095`; `agent_settings.py:482-492`.
- Accept: §2.2.3: the required actor; escalation by level or capability; the baseline rules; the transactional event; refusal while the migration is pending.
- Tests: one per caller, clone and first publish (§5.1.10); G-PG. · Risk: med · Deps: AG-07, AG-20

**AG-22 · Replace `permission_mode` and `dry_run` with `BuiltinToolProfile`**
- Files: `queue_manager.py` (`QueryContext` at `:630`, `_prepare_query_context`, `_run_streaming`, `_run_fallback`, `_run_agent_loop`); `llm_runner.py`; every runner signature; `memory/extractor.py:192-193`; `coordinator_engine.py:375-385`; the `bypassPermissions` fixtures.
- Accept: all call sites pass a resolved profile, and resume and verification turns reuse it; the CLI argv is unchanged until AG-23 to AG-25.
- Tests: A-P-01, A-P-02. · Risk: med · Deps: AG-20

**AG-23 · Claude compiler**
- Files: `claude_runner.py` (`:92-96` deleted; `run_claude` `:330` and `_build_cmd` `:640` merged into one builder); the system-prompt file; the task-scoped `--add-dir`; the contract (`--safe-mode`, `--permission-mode` choices narrowed to `dontAsk`).
- Accept: §2.3.1 for every level; the live checks pass; `self_confined` is set from that evidence.
- Tests: A-C-01 to A-C-08; probe tests; CI contract job; gated live tests. · Risk: high · Deps: AG-22; `workspace_exec` also AG-14

**AG-24 · Codex compiler and removal of the `CODEX_*` settings**
- Files: `codex_runner.py:171-330, 610-629, 878-899`; `config.py:269-270`; `startup_validator.py:26, 67-72`; `manager.py:608-609`; the contract (`approval_policy` choices `never`, bypass flag removed, `--ephemeral`, `--ignore-rules`, `--disable`, the probes of A-K-01 to A-K-03); a migration clearing persisted values; the release note.
- Accept: §2.3.3; child, artifact-gap, squad-planner and extractor runs compile to `--sandbox read-only`; `danger-full-access` only at `workspace_exec` under L2; `supports_native_resume=False`; the contract's `verified_against_help` and per-flag `verified` are set from the recorded CI help run.
- Tests: A-X-01 to A-X-09, A-K-01 to A-K-03; `test_codex_runner.py` rewritten as profile contract tests; gated live tests. · Risk: high · Deps: AG-22, M3-E5-T1; the `IP`-failed `workspace_exec` row also AG-14

**AG-25 · Gemini compiler**
- Files: `gemini_runner.py:73-121, 351, 525` and the streaming path; the settings-file writer; the contract (`--skip-trust`; `plan` and `--prompt` removed).
- Accept: §2.3.2; a level whose settings the live check cannot prove is unavailable; the contract's `verified_against_help` and per-flag `verified` are set from the recorded CI help run.
- Tests: A-G-01 to A-G-07; contract test; gated live tests. · Risk: med · Deps: AG-22; `workspace_exec` also AG-14

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
- Accept: §2.7 with PT-BR copy, the §2.8.4 modal and banner; the raw JSON editor no longer edits this key.
- Tests: Vitest; `pnpm lint:web`, `test:web`, `build:web`. · Risk: med · Deps: AG-20, AG-21; health fields also AG-08

**AG-30 · Migration of existing agents, and the banner**
- Files: the migrations module; the web banner.
- Accept: §2.8.1; versions from the last published snapshot, signed, idempotent; restore goes through the confirmed publish.
- Tests: G-PG migration run twice; web banner test. · Risk: med · Deps: AG-07, AG-09, AG-11, AG-20, AG-21, AG-29

**AG-31 · Release documentation and the end-to-end regression**
- Files: `docs/security/threat-model.md` (trust boundary, classes, residuals R-1 to R-7), `guardrail-test-matrix.md`; `docs/operations/hardening.md`, `upgrade.md` (§2.8.4); `docs/architecture/runtime.md`, `tool-registry-native-tools.md` ("provider built-in tools"); `.env.example`; the release note; the Docker regression job.
- Accept: §5.4 passes in CI and the §6 checklist is complete.
- Tests: G, G-RS, G-CI. · Risk: med · Deps: every other AG item

---

## 8. Open questions (evidence or delegated)

| # | Question | Owner | Status |
|---|---|---|---|
| O-4 | File OAuth with per-agent homes: does refresh-token rotation survive checkout and check-in with concurrent agents? | AG-13b evidence, then operator | Evidence-gated; default preference: env credentials |
| O-7 | Pinned versions and their proven flag set. | AG-02 | Done for 2.1.325 / 0.169.0 / 0.68.0; the live checks of AG-23 to AG-25 complete the proof |
| O-8 | Does Docker's default seccomp allow `landlock_*`, and does Codex's inner sandbox start in the runtime image? | AG-08, AG-24 | Open; uid split only on proof |

## 9. Operator decisions

### 9.1 Questions for MISSION §13 sign-off

| # | Question | Why §13 | Recommendation |
|---|---|---|---|
| OQ-1 | **M3-E3-T1 go-live order.** Policy-approved governed shell, `shell_bg` and git start executing with M3-E3-T1. Should that go live only after AG-03 (no secrets in their env), AG-14 (worker-side git confined), AG-15 (kernel `ExecuteCommand` confined) and AG-19 (the key out of `runtime-kernel`)? The alternative is to go live earlier with an accepted interim residual: until then governed shell runs unconfined in a container that mounts the master key. | Permission policy affecting users | **Require the four tasks first.** Otherwise invariants 3 and 4 are broken on the newly live path. |
| OQ-2 | **Provider switches need confirmation.** `/provider`, `/model`, fallbacks and functional defaults can no longer run a provider whose capability exceeds the published ceiling; such a turn is refused with a link to the dashboard (§2.2.3). | Externally exposed permission policy; changes a Telegram command's effect | **Approve.** Without it, a chat command gives the model a shell. |
| OQ-3 | **Provider CLIs ignore workspace and home customisation** (§2.3.5). (a) Executable customisation: hooks, MCP servers, plugins, extensions, skills, custom commands and agents, rules, discovery commands. (b) Instruction files: CLAUDE.md, AGENTS.md, GEMINI.md. Koda's own MCP servers and skills are unaffected. | Removes user-facing functionality | **(a) Approve**: needed for any level below `workspace_exec` to mean what it says, because a planted hook runs code at `read_only`. **(b) Approve**, with the operator-authored agent instructions as the replacement; if declined, residual R-7 applies. |
| OQ-4 | **CLI login homes move to an app-only path** (`STATE_ROOT_DIR/provider-logins`), copied and verified, the old copies deleted one release later (AG-13b, AG-32). | Touches production credentials | **Approve**, together with AG-19. |
| OQ-5 | **Retarget M1-E4-T7** (approval batch 1, fail closed on unsupported MCP egress) from the bubblewrap backend, which AG-16 deletes, to the helper's Landlock TCP rules. | Security policy; some MCP servers stop starting | **Approve** the retarget, so the approval is not spent on deleted code. |
| — | AG-10b activates delivered rules | Permission policy | Needs sign-off only if AG-09's diff section is non-empty (ADR-039). |

### 9.2 Recorded resolutions (revision 1, 2026-11-14)

The operator delegated these to the recommended long-term option ("siga com aquilo que você achar ser o mais recomendado … solução long-term ideal"). Revision 2 does not change them.

| # | Resolution |
|---|---|
| O-1 | Approved: `koda-state` becomes app-only; worker data is copied (not moved) to `koda-worker-state` with verification; the key is not touched. |
| O-2 | Approved: `filesystem` is a documented installer choice on hosts with Landlock ABI < 4; minimum host kernel 5.13. |
| O-3 | Approved: the runtime evaluator becomes authoritative after the M5-E3-T2 diff report (Q-5). |
| O-4 | Evidence-gated (§8). |
| O-5 | Approved: MCP tool-policy edits take effect on publish. |
| O-6 | Approved as part of the Q-4 impact; documented in the release notes. |
| O-7 | Delegated to AG-02. |
| O-8 | Delegated to AG-08 (and AG-24 for Codex's inner sandbox). |

### 9.3 Plan follow-ups outside M1-E2 (for the orchestrator)

This revision edits only the M1-E2 block of MASTER_PLAN and the ADR-002 entry of DECISIONS. These items elsewhere need the orchestrator:

1. **M3-E3-T1:** deps per OQ-1 (AG-03, AG-14, AG-15, AG-19); approval package = `koda policy audit` section 3 (AG-09); Files add `koda/handlers/commands.py`, `koda/handlers/packages.py`, `koda/services/cli_runner.py`, `koda/services/shell_tools.py`, `koda/services/scheduled_job_runtime.py`; Do follows §2.9.1 (the "set the approval context" option is rejected).
2. **M3-E3-T2:** Files add `koda/control_plane/approvals.py` and the internal routes; deps add AG-17 and M1-E6-T3.
3. **M2-E1-T2:** do not import `approval_grants.json` as live grants (§2.9.2); pending operations are not imported.
4. **M0-E2-T4:** the supervised-write xfail models a human grant, not a policy allow (§2.9.1).
5. **M1-E4-T7:** per OQ-5.
6. **M3-E5-T1:** Files add `codex_runner.py` (Codex has `supports_native_resume=False`).
7. **MASTER_PLAN §5.2** row for M1-E2-T3 ("copy, verify, then move" the key) and the **§7.2** governance chain (R-01): reword to the AG mapping of §7.1; the key is not moved.
8. **M1-E6-T1 / ADR-035:** under `RUNTIME_CONFINEMENT=strict` the kernel listens on TCP, not a UNIX socket (§2.4.2).
9. **M1-E9-T1:** its Deps (M1-E2-T2, M1-E2-T4) now cover more AG items; it may track AG-31 instead.
10. **ADR-009 consequence** "the JSON fallbacks are retired after a one-time import": the import must skip grants (item 3); this is an implementation note, not a change to ADR-009's decision.
