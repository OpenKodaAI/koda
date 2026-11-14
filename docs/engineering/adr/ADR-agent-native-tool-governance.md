# ADR-002 (detailed design): Agent-native tool governance and provider confinement

| Field | Value |
|---|---|
| Status | **Accepted.** The operator approved Option C on 2026-11-14 (Q-4, [DECISIONS.md](../DECISIONS.md) ADR-002). Three steps still need their own MISSION §13 sign-off: AG-10 (only if its audit diff is non-empty), AG-19 (volume layout on existing installs), and the items in §8. |
| Date | 2026-11-14 |
| Owner | SEC (ARCH). Review: SEC and REV (MASTER_PLAN M1-E2-T1). |
| Summary entry | [DECISIONS.md ADR-002](../DECISIONS.md#adr-002--agent-native-tool-governance-option-c) |
| Relation to other ADRs | **Amends** ADR-008 step 1 (adds a precedence fix to M1-E4-T9). **Clarifies** ADR-025 (the control plane resolves secret references). **Supersedes** the relocation step of ADR-026 (the key stays where it is; its volume becomes app-only). **Depends on** ADR-009 (approvals), ADR-010 (one path resolver), ADR-011 (cross-process state). |
| Replaces plan items | M1-E2-T2, M1-E2-T3 and M1-E2-T4 are replaced by AG-01 to AG-32 (§7). M1-E2-T5 (scoped DB role) is unchanged. |

**Evidence tags.** `[V]` means read or run during this design, with the citation given. `[I]` means inferred; the task named alongside it supplies the proof. File references are relative to the repository root.

---

## 1. Context

**Provider built-in tools run ungoverned**

- **C1 [V]** Every turn runs with `permission_mode="bypassPermissions"`. Supervised agents are included; supervised mode only sets `max_turns=1` (`koda/services/queue_manager.py:3101-3103`). The mode is downgraded to `"plan"` only in three cases: dry runs, blocking artifact gaps (`:3443-3449`) and child runs (`:3570-3580`). The Claude argv carries no tool flags (`claude_runner.py:328-360, 598-646`). Dry runs are forced to plan mode in the runner (`:91-95`).
- **C2 [V]** Codex defaults to `CODEX_SANDBOX=danger-full-access` and `CODEX_APPROVAL_POLICY=never` (`koda/config.py:226-227`). Both are also operator system settings (`koda/control_plane/manager.py:606-607`) and are checked at startup (`koda/startup_validator.py:26, 68-70`).
  - Resume adds `--dangerously-bypass-approvals-and-sandbox` (`codex_runner.py:277-278`).
  - The runner discards `permission_mode` (`:689, 959`) and uses a read-only sandbox only for dry runs (`:300-303`).
  - As a result, child runs, artifact-gap turns and the squad planner (`koda/squads/coordinator_engine.py:376-384`) run in danger-full-access on Codex today.
  - Resume is only possible in the dangerous mode (`codex_runner.py:341-353`).
- **C3 [V]** Gemini maps `bypassPermissions` to `yolo` (`gemini_runner.py:85-95`). It has no tool exclusions and puts the system prompt on argv (`:116-119`). When the `gemini` binary is missing, it falls back at runtime to an unpinned `npx -y @google/gemini-cli` (`provider_auth.py:455-459`).
- **C4 [V]** All three CLIs are installed unpinned (`Dockerfile.runtime-kernel:3-6`, `Dockerfile:5-8`). Only Codex probes its flags (`codex_runner.py:155-188`). Claude and Gemini probe only authentication (`claude_runner.py:269-290`).
- **C5 [V]** Koda governs only `<agent_cmd>` and OpenAI-style `tool_calls` (`queue_manager.py:4523-4558, 4770-4930`). Claude's `tool_use` blocks (Bash, Edit, Write) have already run by the time Koda sees them, and are kept only as telemetry (`claude_runner.py:543-553`). Koda's own shell, file and git tools deny by default (`koda/agent_contract.py:1157-1165`), so the ungoverned path is looser than the governed one.

**The policy layer is broken in ways the opt-in would inherit**

- **C6 [V]** `execution_policy` never reaches the worker.
  - The runtime reads only `AGENT_EXECUTION_POLICY_JSON` (`config.py:1291`; `services/execution_policy.py:196-203`).
  - The control plane emits the resource, tool, model and autonomy policy keys, but not that one (`manager.py:12760-12776`).
  - The full spec ships separately as `AGENT_SPEC_JSON` (`manager.py:12916`).
  - So every dashboard-authored rule is ignored at runtime, and the legacy branch always runs (`services/execution_policy.py:736-750`).
- **C7 [V]** The two evaluators disagree.
  - The runtime picks the most permissive of `allow_with_preview` and `require_approval`: its order is deny > allow_with_preview > require_approval > allow (`services/execution_policy.py:40, 300-312`).
  - The control plane takes the first match by priority (`control_plane/execution_policy.py:923-1108`; TD-031, D-024).
- **C8 [V]** Approvals are broken in two ways.
  - The dashboard reads the supervisor's empty in-memory store (`approval_broker.py:150-176`, `utils/approval.py:1588`; D-012).
  - Policy-approved shell and git always fail, because of a contextvar gate (`shell_runner.py:26-32`; D-011).
- **C9 [V]** Publishing snapshots the **draft** and records no actor (`manager.py:12560-12580`). Policy writes (`put_section` `:12108`, `put_execution_policy` `:8645`) are not audited.

**Secrets and confinement**

- **C10 [V]** `runtime-kernel` mounts `koda-state` read-write (`docker-compose.yml:244`; release compose `:188`).
  - The master key lives on that volume at `STATE_ROOT_DIR/control_plane/.master.key` (`koda/control_plane/settings.py:51-55`), and so does `bootstrap.txt` (`bootstrap_file.py:36`).
  - The supervisor forces `STATE_ROOT_DIR` onto workers (`supervisor.py:91`).
  - `_load_master_key` creates a fresh key whenever the file is missing (`crypto.py:18-37`).
  - Workers decrypt in-process in five places: `mcp_connection_broker.py:156`, `mcp_oauth.py:732, 779-780`, `squad_handlers.py:85`, `utils/tts.py:79`, `generation_stubs.py:149-160`.
- **C11 [V]** Isolation is cgroups only. Workers and CLIs run as the same uid, with no namespaces and no Landlock (`rust/koda-runtime-kernel/src/agent_workers.rs:645-708`, `processes.rs:74-100`). Kernel gRPC is unauthenticated on `0.0.0.0:50061` (`docker-compose.yml:240-241`; D-042).
- **C12 [V]** Worker env and child processes:
  - The worker env holds the DSN, the S3 secret and decrypted granted secrets (`supervisor.py:59-124`; `manager.py:12887-12893`).
  - CLI child env is allowlisted (`provider_env.py:182-236`).
  - MCP stdio servers get `env=None`, so they inherit the whole worker env (`mcp_bootstrap.py:86-92` → `mcp_manager.py:125-129` → `mcp_client.py:154-163`).
  - yt-dlp, ffmpeg and ffprobe pass no `env` either (`link_analyzer.py:115, 167`; `artifact_ingestion.py:1511, 1568`; `utils/audio.py:123`; `utils/video.py:37`).
  - Worker-side git runs unconfined in agent-writable dirs (`queue_manager.py:1084-1106`; `runtime/controller.py:722-756`).
  - No process sets `PR_SET_DUMPABLE`. Same-uid reads of `/proc/<pid>/environ` are therefore `[I]`, proven by AG-04.
- **C13 [V]** Work dirs and file tools:
  - `DEFAULT_WORK_DIR` is HOME (`config.py:159`), and in compose HOME holds the CLI credential directories (`docker-compose.yml:29-31`).
  - `SENSITIVE_DIRS` blocks every path that starts with `/var/lib` (`config.py:722-736`; `tool_dispatcher.py:2396-2402`). That includes the Docker work dirs, so governed file tools cannot do work there.
- **C14 [V]** The app also uses the worker's state subpaths: skill locks (`skills/_package.py:1277`), channel gateway (`channels/gateway.py:133`), room photos (`squads/room_photos.py:56`), TTS assets (`kokoro_manager.py:25-33`, `supertonic_manager.py:22-30`) and the knowledge v2 fallback (`knowledge/config.py:57`). A one-time copy to a worker-only volume would therefore split the data.

**Host and CLI facts, from commands run in this session**

- **[V]** The kernel here is 6.18 and reports Landlock ABI 7, from the `landlock_create_ruleset` version probe. **[I]** Deployment hosts and Docker's default seccomp profile are unknown; AG-08 finds out.
- **[V]** `claude` 2.1.325 `--help` lists these options: `--restricted`, `--tools`, `--allowedTools`, `--permission-mode` (including `dontAsk`), `--permission-prompts none`, `--strict-mcp-config`, `--disable-slash-commands` and `--setting-sources`.
  - Per the help text, `--restricted` ignores user, project and local settings, confines the file tools to the working dirs, refuses `bypassPermissions`, and does not let the model write settings, git or tool-config files without an approver.
  - `--append-system-prompt-file` appears **only inside the `--bare` description**, not as a listed option. AG-23 must prove it works.
  - `--system-prompt-snapshot` (on by default) reuses the first turn's system prompt on resume.
- **[I]** Codex and Gemini are not installed here. Every Codex and Gemini flag below is therefore a hypothesis, gated by AG-02, AG-24 and AG-25.

---

## 2. Decision

### 2.1 Invariants

1. **Koda policy is the only authority.** A provider built-in tool runs only at a level that the agent's **signed, published** policy pre-authorizes, lowered by every ceiling that applies. Nothing raises it.
2. **Per-call approval exists only on the governed path.** Built-in tools have no approval state, because the CLIs run headless. Anything that needs a human goes through `<agent_cmd>`, then `evaluate_execution_policy`, then the approval pipeline (ADR-009).
3. **Koda confines model-directed code itself.** Every process that runs code the model controls, or code it can plant, runs inside Koda's confinement or does not run. A provider's own sandbox is an extra inner layer, never the boundary.
4. **The model cannot reach control-plane secrets.** No process the model can reach holds, or can read, the master key, the bootstrap code, the worker's secrets, another agent's data or an unauthenticated control endpoint.
5. **Fail closed.** An unverified CLI version, a missing flag, an unproven restriction or a missing kernel feature makes the capability unavailable, and the reason is shown. It never silently widens.

### 2.2 Governance model

- **Field.** `execution_policy.provider_builtin_tools.level` is an ordered enum: `none < read_only < workspace_write < workspace_exec`.
  - It is a typed block, compiled at spawn. It is **not** a matched rule.
  - There are no per-provider overrides and no free-form provider tool lists. Those break across CLI versions and cannot be validated.
  - The name avoids the existing term "native tools", which means Koda tools sent as function-calling schemas (`docs/architecture/tool-registry-native-tools.md`).
- **Default: `read_only`.** A missing field means `read_only`. Three reasons:
  - It equals Koda's governed secure default, which allows reads and denies writes (`services/execution_policy.py:736-747`).
  - It is Codex's lowest enforceable level.
  - It limits the coding regression, because reads stay cheap.
- **Single delivery channel.** The published, signed `AGENT_SPEC_JSON` (AG-10, AG-11) is the only channel. `AGENT_EXECUTION_POLICY_JSON` and its readers are deleted. The worker never reads draft specs (the `skills/_runtime.py:34-42` fallback is deleted) or live control-plane rows to make governance decisions.
- **Single resolver.** `koda/services/provider_builtin_tools.py` provides `normalize`, `validate` and `resolve(published_level, ctx) -> BuiltinToolProfile{requested, effective, clamps[], process_class}`. The runtime, publish validation, the prompt preview and the simulator all import it. The control-plane normalizer delegates this block to it.

**Ceiling table.** The effective level is the minimum of the published level and every applicable row. Each row replaces an ad hoc site.

| Signal | Ceiling | Replaces |
|---|---|---|
| Scheduled dry run | `read_only` | `queue_manager.py:3102`, `claude_runner.py:91-95`, `codex_runner.py:300-303`, `gemini_runner.py:85-87` |
| Blocking artifact gap | `read_only` | `queue_manager.py:3443-3449` |
| Child run, any toolset | `read_only` | `queue_manager.py:3570-3580` |
| Effective `approval_mode` ∈ {`read_only`, `escalation_required`} | `read_only` | new (today this never reached the CLI) |
| `agent_mode == supervised` | `read_only` | `queue_manager.py:3103` |
| Internal call sites: memory extractor, squad planner | provider minimum (`none`; Codex `read_only`) | `memory/extractor.py:184-197`, `coordinator_engine.py:376-384` |
| Level not faithful on the pinned CLI (contract, §2.3) | next lower faithful level | — |
| Process class M and the required confinement unavailable | turn refused for that provider; fallback skips it | — |

- **The task-kind default `supervised` approval mode is deliberately not a ceiling.**
  - General tasks default to `supervised` (`knowledge/task_policy_defaults.py:170-180`), so using it as a ceiling would make every opt-in silently inert.
  - That mode is also derived from a regex over the query text. Ceilings may come from such signals because they only ever lower the level; nothing a query says can ever raise it.
  - A published level is an explicit pre-authorization, audited and confined to the workspace. Governed tools keep their per-call approval.
- **Below the floor.** If the effective level is below the provider's floor, that provider is refused for the turn. The level is never raised.
- **Supervised mode means the same on every provider.**
  - Built-in tools are capped at `read_only`.
  - Every governed write is approved per call.
  - Koda's loop pauses after each governed round with the existing Continue/Stop buttons (`queue_manager.py:6486-6508`).
  - The Claude-only coupling, where supervised means CLI `--max-turns 1`, is removed. Codex and Gemini already discarded `max_turns` (`codex_runner.py:689`).
- **Governed-loop budget.** `MAX_AGENT_TOOL_ITERATIONS` stays the install-wide ceiling. It is an operator setting (`manager.py:648`), default 8 (`config.py:1281`). The agent's `max_budget` also stops the loop. The default changes only on M0-E3-T2 eval evidence (AG-27).
- **Evaluator.**
  - AG-06 makes the runtime engine pick the most restrictive decision among matched rules: deny > require_approval > allow_with_preview > allow. It also makes the engine fnmatch-only, makes a rule's `name` its audit `rule_id`, and routes simulate and preview to the runtime engine.
  - This is ADR-008 step 1. It changes nothing in production today, because rules are not delivered (C6).
  - Deleting the control-plane engine stays with ADR-008 steps 2–3 (M5-E3-T2, T3; Q-5).

### 2.3 Per-provider mapping

Each runner compiles the effective level from **one table** in `koda/services/provider_cli_contract.py`. The table is keyed by pinned CLI version. For every (provider, level) it records the argv tokens, `self_confined`, the inner-sandbox support and the resume override. Probes check exactly those tokens, so the probe and the argv cannot drift apart. Values not yet proven take the conservative setting: not self-confined, no resume override, floor `read_only`.

**Claude** (contract-proven in AG-23)

- **Every level:**
  ```
  -p --output-format json|stream-json [--verbose] --model M --max-turns N
  [--max-budget-usd B] [--resume ID] [--effort E]
  --restricted --strict-mcp-config --disable-slash-commands
  --permission-prompts none --permission-mode dontAsk
  --append-system-prompt-file <task_tmp>/system.md      (0600, deleted after the run)
  [--add-dir <task_tmp>/images]
  ```
  `--strict-mcp-config` is passed with no `--mcp-config`, so no MCP servers load. `--add-dir` covers only the task's own image directory, never the shared `tmp_images` root.

| Level | Flags | Class |
|---|---|---|
| `none` | `--tools ""` | S |
| `read_only` | `--tools Read,Grep,Glob --allowedTools Read,Grep,Glob` | S (if proven) |
| `workspace_write` | `--tools Read,Grep,Glob,Edit,Write --allowedTools <same>` | S (if proven) |
| `workspace_exec` | `--tools Read,Grep,Glob,Edit,Write,Bash --allowedTools <same>` | M |

- **Never emitted:** `bypassPermissions`, `plan`, `--dangerously-skip-permissions`, `--mcp-config`, `--setting-sources`. `--bare` is also excluded, because per its help text it reads only `ANTHROPIC_API_KEY` and so breaks subscription logins.
- **Floor:** `none`.
- **If `--append-system-prompt-file` is not supported,** AG-02 pins a version that supports it. The prompt does not stay on argv.

**Codex** (every value is `[I]`; AG-02 and AG-24)

- **Every level, new turn:**
  ```
  exec --json --cd <workspace> --model M [--skip-git-repo-check]
  -c approval_policy="never"
  -c shell_environment_policy.inherit="core"
  -c shell_environment_policy.exclude=["*_API_KEY","*TOKEN*","*SECRET*","POSTGRES*","KNOWLEDGE_V2_S3*"]
  -c mcp_servers={} -c tools.web_search=false
  [-c model_reasoning_effort=E] [--image P] -
  ```
  Developer instructions go in the **Koda-written per-agent `config.toml`** (mode 0600), not on argv.
- **`none`:** unsupported (floor `read_only`) until the contract proves a key that removes the shell tool.
- **Other levels.** The choice depends on whether Codex's inner sandbox starts inside the runtime image (contract field `inner_sandbox_ok`).

| Level | `inner_sandbox_ok = true` | `inner_sandbox_ok = false` |
|---|---|---|
| `read_only` | `--sandbox read-only` | `--sandbox danger-full-access`; Koda maps the workspace read-only |
| `workspace_write` | `--sandbox workspace-write -c sandbox_workspace_write.network_access=false` | not faithful; clamps to `read_only` |
| `workspace_exec` | `--sandbox workspace-write -c sandbox_workspace_write.network_access=true` | `--sandbox danger-full-access` |

- **Resume.** `exec resume ... -c sandbox_mode="<same>"` is used only if the contract proves resume honours it. Otherwise native resume is off and the turn becomes a new turn with transcript replay (Q-13, M3-E5-T1). `--dangerously-bypass-approvals-and-sandbox` appears only when the inner mode is `danger-full-access`, which is always inside Koda's helper.
- **Class M at every level,** because the model always has a shell.

**Gemini** (every value is `[I]`; AG-02 and AG-25)

> Implementation note (2026-11-14, AG-02 integration review). gemini-cli parses argv with yargs, which reads a separate value that starts with `-` as an option: the pinned 0.68.0 takes `--prompt -y` as `--yolo`. The contract therefore requires attached values (`--flag=value`), and `validate_args` refuses the separate form. The argv below uses the attached form; the decision is unchanged.

- **Every level:** `gemini --model=M --output-format=json|stream-json --extensions=none`.
  - The env sets `GEMINI_CLI_SYSTEM_SETTINGS_PATH=<task_tmp>/gemini-settings.json`. Koda writes that file with `mcpServers={}`, no `tools.discoveryCommand`, and `tools.exclude` set per level.
  - The prompt and the system instructions go on **stdin**.
  - cwd is the workspace.
- **Level settings:**

| Level | Settings |
|---|---|
| `none` | `tools.core=[]`, only if proven; otherwise the floor is `read_only` |
| `read_only` | `--approval-mode=default`; excludes `write_file`, `replace`, `run_shell_command`, `web_fetch`, `google_web_search`, `save_memory` |
| `workspace_write` | `--approval-mode=auto_edit`; excludes `run_shell_command`, `web_fetch`, `google_web_search`, `save_memory` |
| `workspace_exec` | `--approval-mode=yolo`; excludes `web_fetch`, `google_web_search`, `save_memory` |

- **Class M** until AG-25 proves the workspace boundary of the file tools. `workspace_exec` is always class M.

**Ollama, llama.cpp, MLX and the OpenAI-compatible providers.** These have no built-in tools, so the field does not apply and the UI shows "não se aplica". The ignored `permission_mode` and `dry_run` parameters are removed. Their `tool_calls` already go through the dispatcher and policy (`queue_manager.py:4523-4558`). D-147 (tools sent only on the non-streaming path) stays a separate item.

### 2.4 Confinement model

**Threat.** A prompt-injected model drives built-in tools, governed shell or git, MCP servers and media tools. The assets at risk are:
- the master key, the previous key and `bootstrap.txt`;
- the worker env: DSN, S3 secret, granted secrets and runtime tokens;
- other agents' workspaces, provider homes and sessions;
- kernel RPC, the sidecars and publish integrity.

**Process classes.** The class decides what happens when a required layer is missing.

| Class | Members | If a required layer is missing |
|---|---|---|
| **M**: runs model-directed code | governed shell and git; worker-side git on workspaces; Codex at every level; Claude and Gemini at `workspace_exec`; any CLI level not proven self-confined; `cli_runner.py:121` | Refused, with a reason pointing to `koda doctor` |
| **S**: self-confined CLI level | Claude `none`, `read_only` and `workspace_write`, and Gemini levels, once proven | Runs with the layers that are available |
| **U**: processes untrusted input, operator-installed code | MCP stdio servers, yt-dlp, ffmpeg, ffprobe, Playwright chromium | Runs with a minimal env and a health warning |
| **T**: trusted | login flows in `app`. Explicit allowlist with reasons. | Not confined |

**Layers**

- **L0 Placement** (does not depend on the host):
  - `koda-state` is mounted **only in `app`**. The master key, the previous key and `bootstrap.txt` never enter `runtime-kernel`, and **the key never moves**.
  - Worker data moves to a new `koda-worker-state` volume (setting `WORKER_STATE_ROOT`), mounted in **both** `app` and `runtime-kernel`. All consumers in C14 resolve through it in both processes, which avoids the split-brain a one-time copy would cause.
  - The supervisor forwards `WORKER_STATE_ROOT` instead of `STATE_ROOT_DIR` (`supervisor.py:91`).
- **L1 Process hygiene:**
  - The worker (early in `koda/__main__.py`) and the kernel (`main.rs`) set `PR_SET_DUMPABLE=0` and `RLIMIT_CORE=0`.
  - Every child env comes from one allowlist builder, with no DSN, S3, granted secrets, or runtime, kernel or broker tokens. This covers the MCP and media spawns (C12).
  - Prompts are kept off argv, because `/proc/*/cmdline` stays readable by other processes even under Landlock `[I]`.
- **L2 OS confinement.** One Rust primitive, `rust/koda-runtime-kernel/src/confinement.rs`, is exposed as the `koda-sandbox-exec` binary in the existing crate. It is not a new service (ADR-001).
  - It applies `no_new_privs`, then a Landlock filesystem ruleset, then, at ABI ≥ 4, TCP rules: connect allowed only to `RUNTIME_CONFINEMENT_EGRESS_PORTS` (default `443,53`) plus the port of the provider's configured base URL, and no bind. Then it execs.
  - Landlock's domain ptrace restriction stops reads of the unconfined worker's or kernel's `/proc/<pid>/environ` and `mem`, and of sibling domains, on every ABI.
  - It exits 126 if any requested right cannot be enforced. Nesting can only narrow access.
  - Both spawn paths exec through it:
    - worker-side spawns, through `koda/security/process_confinement.py`;
    - kernel `StartTask` and `ExecuteCommand`. The kernel computes the profile itself (L4).

  Allowlists. Anything not listed is denied, including worker-state, the artifact root, `/app`, `/workspace` (dev overlay), shared HOME, other agents' workspaces and homes, and the `tmp_images` root.

  | Grant | Provider CLI | Governed shell and git | MCP stdio | Media tools | Chromium |
  |---|---|---|---|---|---|
  | read-only: `/usr`, `/lib*`, `/bin`, `/sbin`, `/etc`, `/opt`, `/proc`, the required `/dev` nodes | yes | yes | yes | yes | yes |
  | read-write: task tmp | yes | yes | yes | yes | yes |
  | workspace | read-only at `read_only`, otherwise read-write | read-write | only if the server declares it | no | no |
  | own per-agent provider home, read-write | yes | **no** | no | no | no |
  | other | — | — | server package read-only; server state dir read-write | input file read-only; output dir read-write | browsers path read-only; profile read-write |

- **L3 Provider layer (inner).**
  - The CLI's own restrictions apply inside L2: Claude `--restricted`, Codex's inner sandbox when proven, Gemini's exclusions.
  - Each agent gets its **own provider homes** under `<RUNTIME_EPHEMERAL_ROOT>/provider-homes/<agent>/{claude,codex,gemini}`. Before every spawn, Koda rewrites the files that carry configuration and hooks (Codex `config.toml`, Gemini user settings, Claude settings).
  - This stops one agent injecting configuration into another agent's CLI, and stops it reading another agent's session transcripts.
  - A work dir is never HOME and never contains a provider home or a state root. This is checked by path component, and also applies to `agent_set_workdir` (`tool_dispatcher.py:1404`).
- **L4 RPC.**
  - Kernel RPC authentication (M1-E6-T1) is a hard prerequisite. AG-15 extends it to **per-worker kernel tokens**. The kernel binds each `StartTask` or `ExecuteCommand` call to the token's agent and computes the floor itself: that agent's workspace, its provider home and the task tmp. A profile supplied by the caller can only narrow that floor. A request without a profile is rejected.
  - The control-plane secret broker uses its own per-worker token (§2.5).
  - In strict mode, confined processes cannot connect to any internal port.

**Modes.** One new setting, `RUNTIME_CONFINEMENT`, in `config.py` and `.env.example`.

| Mode | Required for class M | Use |
|---|---|---|
| `strict` (default) | filesystem + ptrace + network (ABI ≥ 4, kernel ≥ 6.7) | Normal |
| `filesystem` | filesystem + ptrace (ABI ≥ 1, kernel ≥ 5.13) | Explicit operator choice. Recorded as an audit event, with a persistent health banner. Unauthenticated sidecars stay reachable until M5-E5. |
| `off` | nothing | Development, macOS or native installs. Requires explicit config, a red banner, a startup log line, and `confinement=off` in every spawn audit event (the M1-E1-T11 pattern). The installer never writes it. |

The confinement status (`enforced | filesystem_only | unavailable`, plus the ABI) is computed at worker start. It is shown in health, `koda doctor` (`sandbox_doctor.py`) and the spawn audit. Whether a host actually supports Landlock, including whether Docker's seccomp profile allows the `landlock_*` syscalls, is settled by `koda-sandbox-exec --self-test` `[I]`.

**Compose.** Applies to `docker-compose.yml` and `packages/cli/release/bundle/docker-compose.release.yml`, plus `packages/cli/release/CHECKSUMS.txt`.
- `runtime-kernel`:
  - remove `koda-state` and add `koda-worker-state`;
  - `security_opt: [no-new-privileges:true]`;
  - `cap_drop: [ALL]`;
  - `read_only: true` with a tmpfs `/tmp`, but only after the smoke test passes.
- `app`: add `koda-worker-state`.

Only long-supported Compose features are used. There is no user-namespace or seccomp relaxation, no bwrap, no uid split and no new container.

### 2.5 Secrets and the master-key boundary

- **Only `app` holds the key:** the control plane and the supervisor.
- **Key loading fails closed (AG-05).**
  - `_load_master_key` never creates a key.
  - `ensure_master_key()` runs only during control-plane bootstrap, and only when no ciphertext and no fingerprint exist.
  - A Postgres fingerprint row (an HMAC under a fixed label, never the key) makes the control plane refuse to start on a mismatch, or when the key is missing while secrets exist.
- **Workers never decrypt or encrypt (AG-17).**
  - Static granted secrets are still decrypted by the control plane into the spawn env (`manager.py:12887-12893`).
  - Dynamic needs go through internal broker routes on the existing control-plane API. They cover MCP connection env, MCP OAuth access tokens (refresh and write-back happen in the control plane only), the squad admin check (run in the control plane; only the result is returned), the ElevenLabs key and the image-generation key.
  - Route auth uses a per-worker token. The supervisor mints it at spawn and stores its hash in Postgres (ADR-011). It is bound to `agent_id`, rotated on respawn, rate-limited, and every resolution is audited (secret id, never the value).
- **ADR-025 clarification.** "Workers resolve secret references at start" means resolution by the control plane, either into the spawn env or through the broker. Workers never hold the key.
- **ADR-026.** The relocation step is superseded: the volume stops being mounted, and the key itself stays put. Rotation (M1-E6-T4) and backups (M7-E2-T1) are unchanged.
- **Snapshot integrity (AG-11).**
  - Published snapshots are HMAC-signed with the ADR-025 HKDF signing key (M1-E6-T3).
  - The supervisor verifies the signature before building a worker env. On a mismatch it does not spawn and emits a security audit event.
  - This closes the path where a holder of the owner-role DSN raises `provider_builtin_tools` by writing `cp_agent_config_versions` directly.
  - Live reads of `cp_mcp_tool_policies` by the worker (`services/execution_policy.py:127-165`) move into the snapshot (O-5).
- **Documented residuals.**
  - In any level that gives the model a shell (every Codex level, and Claude or Gemini `workspace_exec`), code inside that CLI's process tree can read the CLI's own credential. The UI says so, and scoped API keys are recommended.
  - The worker process itself, including in-process plugin code (D-005), still holds the DSN. That is covered by M1-E2-T5 and M1-E4-T4.

### 2.6 Audit

Every event goes to the existing sinks: `control_plane/audit.py:22` (`record_audit_event`) and `services/audit.py:245, 284`.
1. **Configuration changes.** Actor plus before/after diff on `put_section` (`manager.py:12108`), `put_execution_policy` (`:8645`), `put_autonomy_policy` (`:8590`) and publish (`:12560`). `cp_agent_config_versions` gains a `published_by` column.
2. **Spawns.** One `provider.process_spawned` event per model-reachable process. It records:
   - agent, task, provider and process class;
   - CLI version and contract id;
   - requested and effective level, with the clamp reasons;
   - confinement mode, ABI, and which of filesystem, network and ptrace are enforced;
   - the non-secret flag list (**never** prompt or query text);
   - `CONTROL_PLANE_ACTIVE_VERSION` and the snapshot signature id.
3. **Provider-reported tool use.** Built-in `tool_use` reported by the CLIs (`claude_runner.py:543-553`, `codex_runner.py:533-645`) is stored as audit rows with `source=provider_reported`, with arguments redacted and truncated.
4. **Secret broker.** One row per resolution.
5. **Migration, restore and mode changes.** Actor is `system:migration` or the operator.

### 2.7 Operator UX

Follows `apps/web/AGENTS.md` and `apps/web/CLAUDE.md`. Copy is PT-BR; existing PT-BR text is not translated.
- **Recursos tab, next to the provider and model choice:** a typed segmented control, **"Ferramentas nativas do provedor"**, with the options *Nenhuma / Somente leitura (padrão) / Escrita no workspace / Execução no workspace*. It replaces raw-JSON editing of this key.
- **Effective level per provider**, from the resolver through the existing GET execution-policy payload. It shows floors (for example "Codex não suporta Nenhuma"), "não se aplica" for HTTP providers, each clamp with its reason, and the confinement status.
- **Escalation modal.** It lists what becomes reachable: edits without per-call approval, command execution, the provider credential being readable by those commands, and HTTPS egress. Only after confirmation does the client send `confirm_escalation=true`. The publish dialog lists level changes, and the agent list shows a badge on agents above `read_only`.
- **Execution detail** shows, per turn, the effective level, clamps and confinement (from the spawn audit) and the provider-reported tool uses.
- **System health** shows the mode, the ABI, the enforced layers and whether each CLI matches its pin. Filesystem and off modes get a persistent banner.
- **Rule simulator.** The existing evaluate endpoint, backed by the runtime engine, is wired up as the simulator. Today `apps/web/src/lib/control-plane.ts:1607` has no consumers.

### 2.8 Defaults, migration and rollback (MISSION §13)

**Defaults.** New agents get `read_only`.

**Existing agents (AG-30)**
1. A read-only pre-upgrade report (`koda policy audit`) lists:
   - agents on CLI providers;
   - agents whose recent traces show provider-reported Write, Edit or Bash;
   - execution-policy rules whose decisions change once they are delivered.
2. An idempotent migration then runs for each published agent that lacks the field. It creates version N+1 **from the last published snapshot**, not from `build_draft_snapshot` (`manager.py:12566`), so pending drafts are never published. The new version has `level=read_only`, is signed, and has `published_by=system:migration`. One audit row is written per agent. The field is added to the draft only if the draft lacks it.
3. A banner lists the agents that previously ran with unrestricted native access. "Restaurar execução no workspace" goes through the confirmed, audited publish. It cannot restore bypass, which no longer exists.

**Removed settings.**
- `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY`, from `config.py`, `startup_validator.py` and the system-settings fields. Persisted values are cleared by a migration and listed in the release note. Startup is not refused because of them.
- `AGENT_EXECUTION_POLICY_JSON`.

**New settings.** `RUNTIME_CONFINEMENT`, `RUNTIME_CONFINEMENT_EGRESS_PORTS`, `WORKER_STATE_ROOT` and `AGENT_WORKSPACE_ROOT`. Each lives in `config.py` and is added to `.env.example` and the docs.

**Existing installs (AG-18, AG-19)**
- The release compose file and CHECKSUMS are updated.
- On first start, `app` copies the worker subpaths from `koda-state` into `koda-worker-state`, verifies checksums and writes a marker. It copies, it does not move.
- The legacy copies are deleted one release later (AG-32, ADR-018).
- The key is not touched.
- The installer preflight runs `koda-sandbox-exec --self-test` in the runtime image. On ABI < 4 it requires the operator to choose `filesystem`: interactively, or with a flag when non-interactive. The choice is recorded.

**Work dirs.** The default becomes `<AGENT_WORKSPACE_ROOT>/<agent_id>`. Files in the old shared HOME are left untouched, and the release note explains how to reach them.

**Provider homes.** Per-agent homes are seeded from the canonical login location, which the `app` login flows keep writing. Credentials are delivered as env where the provider supports a non-rotating token (API keys, Claude's long-lived `setup-token`). File-based OAuth uses copy-in, then a validated sync-back under a lock. Whether that is safe needs live evidence (O-4).

**Rollback**

| Scope | How |
|---|---|
| Per agent | Publish a higher level (audited). |
| Per install | `RUNTIME_CONFINEMENT=filesystem`. |
| Per release | The previous images still find `koda-state` with the key and the legacy worker subpaths. Changes to skill locks, gateway config or room photos made after the upgrade are not carried back (documented). Old code ignores the new field, signatures, fingerprint row and `published_by`; all migrations are additive. |

**§13 status**

| Item | Status |
|---|---|
| Governed-by-default impact | Approved (Q-4). |
| AG-19: volume layout on existing installs (reframed M1-E2-T3) | Needs sign-off. |
| AG-10: activating dormant rules | Needs sign-off only if the AG-09 diff is non-empty. |
| Supervised-semantics change (AG-27) | Release-note item. Listed in O-6. |
| M1-E2-T5 | Unchanged. |

---

## 3. Alternatives considered

| Alternative | Why not |
|---|---|
| **Fewest moving parts.** A boolean in `autonomy_policy`, honoured only in `guarded` mode; the key stays mounted; network unconfined; dashboard approvals proxied to the worker. | Contradicts ADR-002(B) (the key moves off worker volumes) and ADR-009, which rejects the proxy. The opt-in does nothing for general tasks (`task_policy_defaults.py:170-180`) and depends on a classifier of the query text. The key stays reachable on hosts without Landlock. `execution_policy` stays undelivered. *Grafted:* confining worker-side git plus an AST spawn guard; the work-dir invariant; supervised stepping in Koda's loop. |
| **Key relocation** to an app-only `CONTROL_PLANE_STATE_DIR` volume (copy, verify, delete). | Surgery on key material. It also sets a downgrade trap: older releases create a new key when the file is missing (`crypto.py:29-36`). Making the existing volume app-only reaches the same boundary without moving the key. *Grafted:* the DB fingerprint, the `read_only` default, the level names, `--restricted` at every Claude level, `provider_reported` audit rows, and clearing `CODEX_*` by migration. |
| **Default `none`, with `strict` mode imposed silently.** | The most disruptive option. It conflicts with Codex's floor, breaks internal calls on Codex-only installs, and silently removes governed shell on kernels older than 6.7. |
| **A Koda-hosted MCP bridge** that exposes governed tools natively to the CLIs. | Deferred. It puts an inbound capability socket inside the sandbox and adds a second tool protocol. Re-evaluate if the M0-E3-T2 coding eval at `read_only` exceeds the cost or latency budget recorded in AG-27. |
| **bwrap or a container per execution.** | Needs user-namespace and seccomp relaxations that weaken the container boundary. Not installed in the images. |
| **uid split** (kernel runs with `CAP_SETUID`). | Kept as a fallback only, if AG-08 shows that Docker's default seccomp blocks Landlock on the Docker versions Koda supports. |
| **Provider sandboxes as the boundary.** | One boundary per provider, with semantics that vary by version. The Codex sandbox inside a container is unproven. |
| **Native approval bridging** (`--permission-prompt-tool` or hooks). | The flag is hidden, it needs a server hosted by Koda, and the CLIs run headless. |
| **Status quo plus documentation.** | Rejected by ADR-002. |

## 4. Consequences

**Positive**
- One authority, one field, one resolver and one delivery channel.
- Child runs, artifact-gap turns, dry runs and the squad planner become truly restricted on every provider, which fixes the Codex danger-full-access bug (C2).
- The key and the bootstrap code leave every model-reachable container.
- Workers stop decrypting.
- Operators can trace who granted what.

**Negative and costs**
- Coding agents slow down until an operator opts them in. Each governed round costs a resume, and Gemini resends the full context because it has no resume.
- There are more approvals.
- Codex, governed shell and git need Landlock: kernel ≥ 5.13, and ≥ 6.7 for `strict`.
- One new volume, which must be included in backups.
- The CLIs must be upgraded deliberately. Each version bump re-runs the contract test; without that, providers fail closed.

**Deleted**
- `permission_mode` and `dry_run` from `QueryContext` (`queue_manager.py:640` and its uses), `llm_runner`, and every runner, including the HTTP runners that ignored them.
- `claude_runner._effective_permission_mode` (`:91-95`) and the duplicate argv builder.
- `gemini_runner._effective_approval_mode` (`:85-95`).
- The Codex dry-run branches, the error raised for dry-run on resume, and the dependence of resume on dangerous mode (`codex_runner.py:296-303, 341-353`).
- The `CODEX_SANDBOX` and `CODEX_APPROVAL_POLICY` settings and validator.
- `AGENT_EXECUTION_POLICY_JSON` and its readers.
- The `npx` fallback for Gemini.
- Auto-generation of the master key, and the five worker-side decrypt paths.
- The draft-spec fallback in `skills/_runtime.py`.
- The `'/var/lib'` prefix rule and the HOME fallback for work dirs.
- The unused `sandbox_policy` gates (TD-037) and the bwrap backend.
- The `KODA_AGENT_DEFAULT_*` claims in `docs/operations/hardening.md`, which no code reads.
- The "plan" mode concept.

---

## 5. Verification plan

**Automated (G = full suite: ruff, ruff format, mypy, pytest with coverage, and the pnpm web checks; G-RS adds cargo fmt, clippy and test)**
1. Resolver tests:
   - a table test over every level × ceiling × provider × confinement state;
   - a monotonicity property test (adding a ceiling never raises the level);
   - a test that no `bypassPermissions` or `plan` literal remains outside the Claude compiler.
2. Argv and settings snapshots for each provider × level × {streaming, non-streaming, resume, images}. Contract tests run the pinned binaries' `--help` in CI, without model calls.
3. An AST spawn guard over **all** of `koda/`: `subprocess.*`, `asyncio.create_subprocess_*`, `os.system`, `os.spawn*` and `os.posix_spawn` must go through `process_confinement`, or appear on the class T allowlist with a reason.
4. A "no secret reaches any child" env test covering CLIs, governed shell, git, MCP stdio, media tools and chromium.
5. An import-graph test showing that the worker entrypoint cannot reach `decrypt_secret` or `encrypt_secret`.
6. Evaluator parity vectors run through both the API and the runtime.
7. Snapshot tampering is refused.
8. The key-fingerprint matrix.
9. Migration tests run twice on G-PG.
10. Linux integration tests for `koda-sandbox-exec`: reads outside the allowlist are denied, connects to 5432, 8090 and 50061 are denied (ABI ≥ 4), reading a sibling's or parent's `environ` is denied, nesting cannot widen access, and the helper exits 126 when enforcement is incomplete.

**Runtime checks that need Docker** (G-CI docker-smoke; evidence goes in VALIDATION_REPORT.md). In the runtime-kernel image, a process spawned the way the worker spawns:
1. does not see `/var/lib/koda/state`;
2. cannot read worker-state, another agent's workspace or home, or `/app`;
3. cannot read `/proc/<worker|kernel>/environ`;
4. cannot connect to postgres, app:8090, the kernel or the sidecars in `strict`;
5. cannot call kernel RPC without a token;
6. cannot use agent A's kernel token to get agent B's paths.

Also covered in docker-smoke:
7. The upgrade copies worker-state and decrypts every secret, and rolling back to the previous images works.
8. A `read_only` root on `runtime-kernel` passes the CLI smoke test.
9. The installer preflight reports the mode.

**Live provider checks** (credentials required; gated by `tests/_provider_plugin.py`; mocked tests are never taken as proof, MISSION §7.6). For each provider × level:
- a write at `read_only` leaves no file;
- canary `CLAUDE.md`, `.mcp.json`, hooks, `.gemini/settings.json` and `.codex/config.toml` files in the workspace are ignored;
- a symlink that points outside the workspace is refused;
- writes to `.git/` are refused below `workspace_exec`;
- Codex's inner sandbox starts, and resume keeps its sandbox override;
- Gemini's exclusions hold, and the prompt is read from stdin;
- `--append-system-prompt-file` works;
- per-agent OAuth refresh holds over repeated refresh cycles with two agents running concurrently.

**Host matrix.** Record the self-test result on kernel 6.1 (expected: `filesystem`), on kernel ≥ 6.8 (expected: `strict`) and on Docker Desktop `[I]`.

---

## 6. Release gate

The default ships only when all of the following are done:
- AG-01 to AG-31;
- M1-E6-T1 (kernel RPC auth), M1-E6-T3 (signing key), M3-E3-T1 (D-011), M3-E3-T2 (D-012), M5-E3-T7 (one path resolver);
- the M0-E3-T2 eval evidence;
- the §13 sign-offs in §2.8.

Each task may merge earlier, provided it leaves the system no less restrictive than before.

---

## 7. Implementation backlog

Each task names its files, acceptance criteria, tests, risk and dependencies. A gate is listed only when the task needs one.

### Foundation (no dependencies, can run in parallel)

**AG-01 · Record the decision**
- Files: `docs/engineering/DECISIONS.md` (ADR-002 link, the ADR-025 clarification, ADR-026 relocation step superseded, ADR-008 step-1 amendment); `docs/engineering/MASTER_PLAN.md` (M1-E2-T2..T4 → AG-*; M1-E2-T3 reframed); `docs/security/threat-model.md` (trust boundary, classes, residuals).
- Accept: the log and the plan point to this ADR, and no accepted ADR is edited in substance.
- Tests: docs link check.
- Risk: low · Deps: —

**AG-02 · Pin the CLIs; contract table; probes that fail closed**
- Files: one lockfile `packages/provider-clis/package.json` and its lock, installed by `Dockerfile:5-8` and `Dockerfile.runtime-kernel:3-6`; new `koda/services/provider_cli_contract.py`; the probes at `claude_runner.py:269-290`, `codex_runner.py:155-188, 307-364` and the Gemini probe; `provider_auth.py:455-459` (delete npx); a CI job.
- Accept:
  - both images install identical, exact versions;
  - a version mismatch reports `unavailable:unverified_cli_version`;
  - the builders cannot emit a token that is not in the contract;
  - a missing `gemini` binary means unavailable, never npx.
- Tests: unit tests with fake `--help` and version output; an asset test (no unpinned `npm -g`); a CI contract job against the pinned binaries.
- Risk: med · Deps: —

**AG-03 · Allowlisted env for every child process**
- Files: `mcp_bootstrap.py:86-92`, `mcp_manager.py:125-129`, `mcp_client.py:154-163`; `link_analyzer.py:115, 167`; `artifact_ingestion.py:1511, 1568`; `utils/audio.py:123`; `utils/video.py:37`; `queue_manager.py:1084-1106`; `runtime/controller.py:722-756`; `provider_env.py:226-236`.
- Accept: no child is spawned with `env=None` or with an inherited env. MCP servers get only their connection env plus the safe base. Worker-side git adds `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `-c core.fsmonitor=false -c core.hooksPath=/dev/null`, `--no-ext-diff` and `--no-textconv`.
- Tests: the "no secret reaches any child" test (§5.4).
- Risk: med (MCP servers that relied on inherited vars) · Deps: —

**AG-04 · Non-dumpable worker and kernel**
- Files: `koda/__main__.py` (prctl via ctypes on Linux, first statement); `rust/koda-runtime-kernel/src/main.rs`.
- Accept: a same-uid sibling gets EACCES on `/proc/<worker|kernel>/environ`; core dumps are off; the kernel's worker supervision still works.
- Tests: a Linux pytest integration test; a cargo test. G, G-RS.
- Risk: low · Deps: —

**AG-05 · Fail-closed master key with a DB fingerprint**
- Files: `koda/control_plane/crypto.py:18-37`; control-plane bootstrap; a migration adding the fingerprint row.
- Accept:
  - no code path generates a key implicitly;
  - a fresh install generates the key and fingerprint in `app` only;
  - a mismatch, or a missing key while secrets exist, refuses startup with guidance;
  - a worker gets `MasterKeyUnavailable` and leaves no file behind.
- Tests: unit tests (missing, present, mismatch, permissions); G-PG.
- Risk: med · Deps: —

**AG-06 · Evaluator precedence and parity** (amends M1-E4-T9)
- Files: `services/execution_policy.py:40, 168-312`; `control_plane/execution_policy.py:551-606` (normalize and validate delegate; the simulate route calls the runtime engine); `manager.py:8676`; `tests/fixtures/execution_policy_vectors.json`.
- Accept:
  - deny > require_approval > allow_with_preview > allow;
  - fnmatch only, and validation rejects `^regex`;
  - `name` is the `rule_id`;
  - `match` and `selectors` normalize to one canonical key;
  - a `mcp_*__delete_*` deny is enforced;
  - evaluate equals the runtime result for every vector.
- Tests: parity vectors; normalizer migration tests.
- Risk: med (no production effect, because rules are undelivered, C6) · Deps: —

**AG-07 · Audit of configuration changes, and `published_by`**
- Files: `manager.py:12108, 8590, 8645, 12560-12580`; `control_plane/audit.py`; a migration adding `cp_agent_config_versions.published_by`.
- Accept: every policy write and publish records the actor and a before/after diff, and versions carry `published_by`.
- Tests: G-PG; API route tests.
- Risk: low · Deps: —

**AG-08 · Confinement primitive, mode setting and doctor**
- Files: `rust/koda-runtime-kernel/src/confinement.rs`; `src/bin/koda-sandbox-exec.rs`; `Cargo.toml` (`landlock` crate, exact version); `config.py` (`RUNTIME_CONFINEMENT`, `RUNTIME_CONFINEMENT_EGRESS_PORTS`); `.env.example`; `sandbox_doctor.py`; `docs/operations/sandbox-doctor-runbook.md`.
- Accept:
  - `--self-test` prints the ABI and the enforced layers as JSON;
  - the profile is applied as specified in §2.4, and DNS resolution works;
  - exit 126 when enforcement is incomplete;
  - choosing `filesystem` or `off` emits an audit event and shows a banner;
  - Docker's default-seccomp behaviour is recorded, and the uid-split fallback is triggered only on proof.
- Tests: cargo unit tests; Linux integration tests (§5.10), with CI requiring an ABI ≥ 4 runner. G-RS.
- Risk: high · Deps: —

### Policy delivery and integrity

**AG-09 · `koda policy audit` (read-only)**
- Files: `koda/cli/migrate.py` (subcommand); docs.
- Accept: for each published agent, reports its rules and the decision changes that AG-10 combined with AG-06 would cause, plus the built-in tool usage seen in traces. Writes nothing.
- Tests: G-PG fixture with legacy-compiled rules.
- Risk: low · Deps: AG-06

**AG-10 · Deliver `execution_policy` only through `AGENT_SPEC_JSON`**
- Files: `config.py:1291` (delete); `services/execution_policy.py:196-203`; `tool_prompt.py:217`; `scheduled_jobs.py:50, 560`; `queue_manager.py:3345-3352`; `manager.py:445-449` (the preview uses the same accessor).
- Accept: a published deny rule is enforced in the worker; the preview equals the live tool set; a missing or invalid spec gives secure defaults; the old variable is gone from the tree.
- Tests: unit tests; a G-PG test that publishes, builds the env, then checks enforcement.
- Risk: high · Deps: AG-06, AG-09 · Gate: §13 sign-off if the AG-09 diff is non-empty

**AG-11 · Signed snapshots; governance inputs only from the snapshot**
- Files: `manager.py` publish (sign); supervisor env build (verify); `skills/_runtime.py:34-42` (delete the fallback); `services/execution_policy.py:127-165` (MCP tool policy taken from the snapshot).
- Accept: a tampered `cp_agent_config_versions` row stops the spawn and emits a security event; the worker never calls `get_agent_spec`.
- Tests: tamper test; G-PG.
- Risk: med · Deps: AG-10, M1-E6-T3 · Gate: O-5

### Workspaces and provider homes

**AG-12 · Workspace roots, deny roots and the work-dir invariant** (implemented inside M5-E3-T7's resolver)
- Files: `config.py:159, 722-736`; `utils/workdir.py:27-57`; `tool_dispatcher.py:1404-1430, 2396-2402`; `.env.example` (`AGENT_WORKSPACE_ROOT`).
- Accept:
  - governed file tools work under `/var/lib/koda/runtime/workspaces/<agent>`;
  - explicit deny roots are checked by path component;
  - a work dir equal to or containing HOME, a state root, a provider home or `RUNTIME_KERNEL_ROOT` is refused;
  - the HOME fallback is gone.
- Tests: predicate matrix emulating the compose layout; dispatcher and workdir tests.
- Risk: med · Deps: M5-E3-T7

**AG-13 · Per-agent provider homes**
- Files: `provider_env.py:88-223`; `manager.py:8155-8171`; `queue_manager.py:5680-5695` (Codex `generated` path); Codex instructions moved into the Koda-written `config.toml`.
- Accept:
  - each agent has its own Claude, Codex and Gemini home, with config rewritten before each spawn;
  - agent B cannot read agent A's sessions;
  - logins still work;
  - credential delivery per auth mode matches §2.8, with live refresh evidence.
- Tests: unit tests; G-PG; recorded live checks.
- Risk: high (OAuth rotation) · Deps: AG-02, AG-12 · Gate: O-4

### Spawn confinement

**AG-14 · Class M and S spawns through the helper**
- Files: new `koda/security/process_confinement.py`; `claude_runner.py:161, 430, 735`; `codex_runner.py:157, 173, 786, 1014`; `gemini_runner.py:348, 497`; `cli_runner.py:121`; `shell_tools.py:66-72`; the git tool spawns in `tool_dispatcher`; `queue_manager.py:1084-1106`; `runtime/controller.py:722-756`.
- Accept: the AST guard passes; class M refuses exactly when the mode's required layers are missing; a stub CLI or shell cannot read the denied targets in §5.
- Tests: argv-prefix unit tests; the AST guard; Linux integration tests.
- Risk: high · Deps: AG-03, AG-08, AG-12, AG-13

**AG-15 · Kernel path: per-worker identity and a floor the kernel computes**
- Files: `rust/koda-runtime-kernel/src/server.rs:1062-1130, 1268-1284`; `processes.rs:74-100`; `agent_workers.rs` (mint per-worker tokens); `proto/runtime/v1/runtime.proto` (required `ConfinementProfile`); `koda/internal_rpc/runtime_kernel.py`.
- Accept: a request without a profile is rejected; agent A's token cannot obtain agent B's paths; a broader caller profile is narrowed to the floor; execution goes through `koda-sandbox-exec`.
- Tests: Rust request-validation tests; a Python client test. G-RS.
- Risk: high · Deps: M1-E6-T1, AG-08

**AG-16 · Class U spawns through the helper**
- Files: `mcp_isolation.py:150-225` (the native and Linux backends become the helper; bwrap removed); media spawns (AG-03 list); `browser_manager.py` (chromium through a wrapper `executable_path`); `sandbox_policy.py` (delete the TD-037 gates).
- Accept: MCP, media and chromium run under their own profiles and report status truthfully; without L2 they run with a warning. Coordinated with M1-E4-T6 and M1-E4-T7.
- Tests: unit tests with a fake runner; Linux integration tests; a real-browser CI test.
- Risk: med · Deps: AG-03, AG-08, AG-14

### Secrets and placement

**AG-17 · Control-plane secret broker: workers never decrypt**
- Files: `control_plane/api.py` (internal routes); `supervisor.py:500-551` (mint the token, store its hash); a worker client; `mcp_bootstrap.py:58`; `mcp_connection_broker.py:156`; `mcp_oauth.py:683-827`; `squad_handlers.py:85`; `utils/tts.py:76-82`; `generation_stubs.py:149-160`.
- Accept:
  - the import-graph test passes;
  - an agent-A token gets 403 on agent B's secrets;
  - a respawn revokes the previous token;
  - OAuth refresh and write-back happen only in the control plane;
  - MCP, OAuth MCP, the squad check, TTS and image generation still work.
- Tests: auth matrix; a G-PG two-process test.
- Risk: high · Deps: AG-05

**AG-18 · `WORKER_STATE_ROOT` and the `koda-worker-state` volume, shared by app and worker**
- Files: `config.py`; the consumers in C14 plus `state/pending_approvals.py:30` and `state/approval_grants.py:20`; `supervisor.py:91`; an app-side copy migration (checksums, marker); both compose files (add the volume to `app` and `runtime-kernel`; `koda-state` stays mounted for now); CHECKSUMS; `tests/test_installation_assets.py`.
- Accept:
  - both processes resolve the same paths;
  - a test lists every `STATE_ROOT_DIR` consumer and classifies it as control-plane-only or worker-state;
  - an upgraded install keeps its skill locks, gateway config and room photos.
- Tests: migration test run twice; compose render test.
- Risk: med · Deps: —

**AG-19 · `runtime-kernel` without `koda-state`; compose and installer hardening** (reframed M1-E2-T3)
- Files: `docker-compose.yml:234-256`; release compose `:178-192`; CHECKSUMS; `tests/test_compose_port_exposure.py` pattern; `packages/cli/bin/koda.mjs` (self-test preflight and mode choice); `docs/operations/backup-restore.md`, `hardening.md`, `upgrade.md`.
- Accept:
  - `/var/lib/koda/state` does not exist in `runtime-kernel`;
  - the service has `no-new-privileges` and `cap_drop: [ALL]`, and `read_only` once the smoke test passes;
  - the preflight records the mode;
  - rolling back to the previous images works.
- Tests: compose render; an installer test with a fake docker; an upgrade and rollback smoke. G-CI.
- Risk: high · Deps: AG-05, AG-14, AG-17, AG-18, M1-E6-T1 · Gate: §13 (O-1)

### Governance field and runners

**AG-20 · `provider_builtin_tools` field and resolver**
- Files: new `koda/services/provider_builtin_tools.py`; the execution-policy normalize and validate functions (delegate); the `agent_spec` summary; OpenAPI.
- Accept:
  - missing means `read_only`;
  - an unknown value is a validation error with its path;
  - the ceilings, floors and internal-minimum rules hold as in §2.2;
  - one import serves the runtime, publish, preview and simulator.
- Tests: table test plus monotonicity property test.
- Risk: med · Deps: AG-02, AG-10

**AG-21 · Publish gate**
- Files: `api.py` publish route; `manager.py` `publish_checks`.
- Accept: raising the level without `confirm_escalation` is rejected; a level the agent's providers cannot enforce fails with the floor named; the publish diff lists level changes.
- Tests: G-PG; route tests.
- Risk: low · Deps: AG-07, AG-20

**AG-22 · Replace `permission_mode` and `dry_run` with `BuiltinToolProfile`**
- Files: `queue_manager.py:640, 3101-3103, 3443-3449, 3570-3580, 3707, 3842, 4062, 4610, 5283`; `llm_runner.py:277-353`; every runner signature; `memory/extractor.py:184-197`; `coordinator_engine.py:376-384`; the 16 `bypassPermissions` fixtures (`test_queue_helpers.py:885, 935, 1264`; `test_agent_loop.py:36`).
- Accept:
  - all four call sites pass a resolved profile, and resume and verification turns reuse it;
  - the CLI argv is unchanged until AG-23, AG-24 and AG-25;
  - none of `permission_mode`, `bypassPermissions` or `plan` appears outside the compilers.
- Tests: queue tests per scenario; a grep guard; fixtures rewritten as contract tests.
- Risk: med · Deps: AG-20

**AG-23 · Claude compiler**
- Files: `claude_runner.py:91-95` (delete), `328-360` and `598-646` (merged into one builder); system-prompt file; task-scoped `--add-dir`.
- Accept: argv matches §2.3 for every level and mode; the live checks in §5 pass; `self_confined` is set from that evidence.
- Tests: argv snapshots; probe tests; the CI contract test; gated live tests.
- Risk: high · Deps: AG-02, AG-14, AG-22

**AG-24 · Codex compiler and removal of the `CODEX_*` settings**
- Files: `codex_runner.py:190-364, 443-487, 689, 959`; `config.py:226-227`; `startup_validator.py:26, 68-70`; `manager.py:606-607`; a migration that clears persisted values; the release note.
- Accept:
  - child, artifact-gap and squad-planner runs are never danger-full-access outside Koda's helper;
  - the bypass flag appears only for an inner `danger-full-access` mode under the helper;
  - resume does not depend on dangerous mode;
  - `none` is refused while the floor is `read_only`.
- Tests: `test_codex_runner.py:85-123` rewritten as profile contract tests; argv and probe tests; gated live tests.
- Risk: high · Deps: AG-02, AG-14, AG-22

**AG-25 · Gemini compiler**
- Files: `gemini_runner.py:72-121, 277, 316-348, 450, 486-497`; the settings-file writer.
- Accept: approval mode and settings match each level; the prompt goes on stdin; `yolo` appears only for `workspace_exec`; an exclusion the contract cannot prove makes that level unavailable.
- Tests: argv and settings snapshots; contract test; gated live tests.
- Risk: med · Deps: AG-02, AG-14, AG-22

**AG-26 · Prompts and pipelines follow the governed tools**
- Files: `config.py:1027-1060, 1102-1196`; `tool_prompt.py:300-440`; `memory/procedural.py:47`; `utils/progress_tracker.py:10-11`; `utils/progress.py:16-24`; `utils/artifacts.py:15-27`.
- Accept:
  - the system prompt no longer claims full filesystem access and does not change by level, which keeps Claude's prompt snapshot valid on resume;
  - each turn's effective level is stated in the runtime context block;
  - writes and commands are routed to governed tools, and the model is asked to batch independent calls;
  - procedural memory and progress also learn from `shell_execute` and `file_*`;
  - PT-BR content is untouched.
- Tests: prompt snapshot tests; procedural and progress unit tests.
- Risk: med · Deps: AG-22

**AG-27 · Governed loop and uniform supervised mode**
- Files: `queue_manager.py:3103, 4575, 5351-5382, 6486-6508`; `handlers/callbacks.py:1140`; `utils/command_helpers.py:357`; evals.
- Accept:
  - supervised pauses after each governed round on every provider;
  - the budget stops the loop;
  - `MAX_AGENT_TOOL_ITERATIONS` stays the ceiling, and its default changes only on recorded eval evidence;
  - the MCP-bridge re-evaluation threshold (cost and latency) is recorded.
- Tests: `test_agent_loop.py` per stub provider (pause, budget, cap); an eval run.
- Risk: med · Deps: AG-22, M0-E3-T2 · Gate: O-6

### Audit, UX, migration and release

**AG-28 · Spawn audit and execution detail**
- Files: the runner spawn paths → `services/audit.py`; provider-reported `tool_use` rows; `apps/web` `execution-detail-content.tsx`.
- Accept: exactly one event per spawn with the fields in §2.6 and no prompt text; the UI shows the events for each turn.
- Tests: unit and redaction tests; a web component test.
- Risk: low · Deps: AG-14, AG-22

**AG-29 · Typed operator control and health**
- Files: `apps/web` `tab-recursos.tsx:421-620`, `shared/policy-card`, `tool-policy-segment.tsx`, `hooks/use-agent-editor.ts`, `lib/control-plane.ts:1607`, the publish dialog, system health.
- Accept: the items in §2.7 are delivered, with PT-BR copy, and the raw JSON editor no longer edits this key.
- Tests: Vitest component tests; `pnpm lint:web`, `test:web`, `build:web`.
- Risk: med · Deps: AG-08, AG-20, AG-21

**AG-30 · Migration of existing agents, and the banner**
- Files: the migrations module; a web banner; the `koda policy audit` extension.
- Accept: §2.8 steps 1–3; versions are built from the **last published** snapshot and signed; the migration is idempotent; restore goes through the confirmed publish.
- Tests: G-PG migration run twice; a web banner test.
- Risk: med · Deps: AG-07, AG-11, AG-20, AG-29

**AG-31 · Release documentation and the end-to-end regression**
- Files: `docs/security/threat-model.md`, `guardrail-test-matrix.md`; `docs/operations/hardening.md`, `upgrade.md`; `docs/architecture/runtime.md`, `tool-registry-native-tools.md` (use the term "provider built-in tools"); `.env.example`; the release note (§13 impact, migration, verification, rollback); the Docker regression job.
- Accept: the runtime checks in §5 pass in CI, and the §6 release gate checklist is complete.
- Tests: G, G-RS and G-CI.
- Risk: med · Deps: AG-01..AG-30

**AG-32 · Delete the legacy worker subpaths in `koda-state`** (the release after AG-19, per ADR-018)
- Files: the app-side cleanup migration; release note.
- Accept: the legacy copies are removed only when the marker and checksums match, and the release note says that rollback past this release loses them.
- Tests: migration test.
- Risk: low · Deps: AG-19 shipped in a prior release

---

## 8. Open questions

| # | Question | Owner | Recommendation |
|---|---|---|---|
| O-1 | §13 sign-off for AG-19: change the volume layout on existing installs. `koda-state` becomes app-only and worker data is copied to `koda-worker-state`; the key is not touched. | **Operator** | Approve. It is lower risk than ADR-026's key relocation, which this supersedes. |
| O-2 | Hosts with Landlock ABI < 4 (for example Debian 12 or Ubuntu 22.04 GA, `[I]`): accept `filesystem` as a documented installer choice? And should Koda declare a minimum host kernel of 5.13? Below it, Codex, governed shell and git are refused. | **Operator** | Yes to both. |
| O-3 | Q-5 (ADR-008): which evaluator becomes authoritative, and when the control-plane engine is deleted. | **Operator** (existing) | The runtime engine, after the M5-E3-T2 diff report. |
| O-4 | File-based OAuth (Codex ChatGPT login, Gemini Google login, Claude `.credentials.json`) with per-agent homes. If the live evidence from AG-13 shows refresh-token rotation breaks copy-in and sync-back, should those modes require API keys or Claude's long-lived token under confinement? | Evidence first, then **operator** | Prefer non-rotating env credentials. |
| O-5 | MCP tool-policy edits would take effect on publish instead of immediately (consequence of AG-11). | **Operator** | Accept: publish is the change control. |
| O-6 | Supervised mode changes for Claude users: it pauses per governed round instead of per CLI turn, and built-ins are capped at `read_only`. A release-note item, or an extra §13 sign-off? | **Operator** | Treat it as part of the approved Q-4 impact. |
| O-7 | Pinned versions of claude-code, codex and gemini-cli, and their proven flag set. | AG-02 | Choose the newest versions that pass the contract, including `--append-system-prompt-file`. |
| O-8 | Does Docker's default seccomp allow `landlock_*` on the Docker versions Koda supports? If not, the uid-split fallback applies. | AG-08 | — |

## 9. Operator resolutions (2026-11-14)

The operator delegated these decisions to the recommended long-term option ("siga com aquilo que você
achar ser o mais recomendado … solução long-term ideal"). Recorded resolutions:

| # | Resolution |
|---|---|
| O-1 | Approved: `koda-state` becomes app-only; worker data is **copied** (not moved) to `koda-worker-state` with verification; the master key is not touched. |
| O-2 | Approved: `filesystem` confinement is a documented installer choice on hosts with Landlock ABI < 4; minimum supported host kernel 5.13. |
| O-3 | Approved: the runtime evaluator becomes authoritative after the M5-E3-T2 diff report (Q-5). |
| O-4 | Evidence-gated: decided after AG-13's live refresh-token evidence; default preference is non-rotating env credentials. |
| O-5 | Approved: MCP tool-policy edits take effect on publish (publish is the change control). |
| O-6 | Approved as part of the Q-4 impact; documented in release notes. |
| O-7 | Delegated to AG-02 (newest versions that pass the CLI contract). |
| O-8 | Delegated to AG-08 (uid-split fallback if Docker seccomp blocks Landlock). |
