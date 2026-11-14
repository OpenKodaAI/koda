# Reference Product Research

UI/UX research input for the consolidation mission ([MISSION.md](MISSION.md)), 2026-11-14.
It summarizes what was found about seven reference products and distills design principles
for Koda, mapped onto the agents, squads, skills, memory, governance and monitoring surfaces
that exist in this repository.

This file is research, not a plan or a spec. Principles in section 6 are proposals. Before any
of them becomes work, check it against the code and against
[`apps/web/AGENTS.md`](../../apps/web/AGENTS.md) and [`apps/web/CLAUDE.md`](../../apps/web/CLAUDE.md).

## 1. Scope and evidence

Inputs:

- A research pass on 2026-11-14 that fetched or searched the product pages listed in section 10.
  This document did not re-fetch those sources.
- Read-only inventory of this repository at commit `7c7b03f` (branch `claude/dreamy-cerf-mhvbwn`)
  for the Koda baseline in section 5.

Evidence labels:

| Label | Applies to | Meaning |
|---|---|---|
| `docs` | Products | Taken from the product's official documentation, fetched directly |
| `secondary` | Products | Taken from third-party articles or press; not confirmed in official docs |
| `snippet` | Products | Known only from a search-result snippet; page not fetched |
| `unverified` | Both | Not independently verified; do not treat as fact |
| `inv` | Koda | Checked in this repository with read-only commands (`ls`, `grep`, file reads) for this document |
| `claimed` | Koda | Stated in README or `docs/`; implementation depth not checked |

Most of these products launched or changed after the model training cutoff (OpenClaw renamed in
Jan 2026, ClawHavoc in Feb 2026, Grok Bot / Team Bots Aug-Nov 2026, OpenAI Dots announced
29 Sep 2026). All product facts below come from the 2026-11-14 research pass, not prior knowledge.

## 2. Products at a glance

| Product | What it is | Verification | Closest Koda analog |
|---|---|---|---|
| OpenClaw (formerly Clawdbot / Moltbot) | Self-hosted MIT gateway linking chat channels to agent runtimes; Web Control UI, CLI, device nodes, ClawHub skills | Verified (`docs`) | Whole product: gateway, channels, multiple agents, skills, approvals, local dashboard |
| Hermes Agent (Nous Research) | Open-source CLI-first agent with a 20+ platform messaging gateway, self-curated memory and skills, delegation, cron | Verified (`docs`) | Memory governance, skills lifecycle, child runs, command approval |
| Grok Bot / Team Bots (xAI, branded SpaceXAI) | Desktop app for persistent named Bots on a shared cloud computer; 2-6 Bot groups; shared Team Bots with roles | Verified for docs.x.ai pages; several items `secondary` | Squad Rooms, approvals, learning curation, roles |
| OpenAI Dots ("GPT Dots") | Persistent always-on agents in ChatGPT with their own cloud computer, cross-channel identity, learned notes | **Unverified** (official page returned 403; all detail secondhand) | Agent profile, approval rules, memory control |
| CrewAI (framework + AMP) | Python multi-agent framework; role/goal/backstory agents; sequential or hierarchical crews | Verified (`docs`) | Squad coordination modes, agent limits |
| LangGraph Studio (LangSmith) | Agent IDE: graph view, threads, assistants, time travel, tracing and evals | Verified (`docs`) | RunGraph, evals, HITL interrupts |
| OpenAI Agents SDK | Python/JS SDK: agents, handoffs, agents-as-tools, guardrails, sessions, tracing, tool approvals | Verified (`docs`) | Squad coordination, approval state, guardrails |

## 3. Product findings

### 3.1 OpenClaw

Verification: `docs` (docs.openclaw.ai). ClawHavoc figures from The Hacker News and the OpenClaw blog.

| Area | Finding |
|---|---|
| Agent scopes | Three separate scopes per agent. **Workspace**: persona/operating files (`AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`), default cwd, not a sandbox. **agentDir**: auth profiles, model registry, per-agent config; docs say "never reuse agentDir across agents". **Session store**: per agent. Operating rules go in `AGENTS.md` so spawned sessions that skip persona files still get them. |
| Routing | Bindings map channel/account/peer/guild to an agent. Most specific match wins, then config order. Unbound messages go to a configured fallback owner (e.g. `systemAgent`) or stay undispatched; never to an arbitrary agent. |
| Groups and sessions | Groups gated by `allowFrom` and `requireMention`. DMs collapse into the agent's main session; each group gets its own session. Cross-agent session access via `tools.agentToAgent` allow-pairs and visibility. |
| Sandbox and tools | Per-agent sandbox (mode off/all; scope agent = one container per agent) and per-agent `tools.allow/deny`. Elevated-access gate exists globally and per agent; the per-agent gate can only restrict. |
| Exec approvals | Modes: deny, allowlist, ask, auto, full. Auto mode reviewer can allow once, deny with reason, or escalate to a human. Ask: off, on-miss, always. `askFallback` defaults to deny when no UI is reachable or on timeout. "Always Allow Here" binds to exact argv and cwd; for automations it mints a revocable job-scoped grant. Allowlist entries are path globs plus `argPattern` regex; every segment of a shell chain must match. |
| Approval delivery | Approvals can be forwarded to chat with reaction shortcuts (allow once / allow always / deny), `/approve` as fallback. Automation approvals go only to approval-capable clients, never to chat channels. |
| Skills | `SKILL.md` (AgentSkills spec), 7-level precedence, highest source wins. `metadata.openclaw` gates eligibility (`requires.bins/anyBins/env/config`, `os`). Per-agent skill allowlists **replace** defaults; `[]` means no skills. Docs: "An allowlist is not a shell authorization boundary." |
| Skill supply chain | `openclaw skills verify` checks the trust envelope; `security.installPolicy` runs a local hook before install; realpath containment on skill roots. After ClawHavoc (341 of 2,857 audited skills malicious), every ClawHub skill is scanned by VirusTotal (benign / suspicious / malicious) with daily rescans. Maintainers state this does not catch prompt injection written as plain prose. |
| Memory | `MEMORY.md`: compact durable facts injected at session start, truncated past the bootstrap budget. `memory/YYYY-MM-DD.md` daily notes: indexed, not injected. Silent "memory flush" turn before compaction. Hybrid vector + keyword search. Background "Dreaming" sweep promotes items to `MEMORY.md` and writes `DREAMS.md` for human review. |
| Sub-agents | Own sessions (`agent:<id>:subagent:<uuid>`), announce results to the requester. No session or message tools by default; docs suggest a cheaper model. Subagents panel in the parent conversation: Running / Finished, transcript, Stop. |
| Control UI | Chat Details panel with a Changes (diff) view. Consecutive tool calls share one expandable log; completed turns collapse to e.g. "Worked for 2m 3s". Processes show status, elapsed time, recent output. Sessions can be grouped, pinned, snoozed, renamed. All-agent views for Automations, Dashboards, Sessions, Usage. Guided "Create new agent" flow; per-agent settings at `/settings/agents/<id>`. Read-only config banner. Per-device token pairing. |

Gaps in the sources: the Control UI page does not describe dedicated Approvals, Skills, Cron or Logs tabs. Star counts vary by source and date and were not used.

### 3.2 Hermes Agent (Nous Research)

Verification: `docs` (hermes-agent.nousresearch.com), plus one `secondary` guide (Better Stack).

| Area | Finding |
|---|---|
| Bounded memory | `MEMORY.md` (agent notes, 2,200 chars) and `USER.md` (user profile, 1,375 chars) are hard-capped. A write over the cap returns an error; the agent must consolidate or remove in the same turn. Docs advise consolidating above 80%. |
| Frozen snapshot | Memory is injected once at session start and does not change mid-session (preserves prompt cache). Writes hit disk immediately and apply next session; docs recommend `/new` at task boundaries. |
| Memory tool | `add`, `patch` (unique-substring match), `remove`; no blind replace. `session_search` is FTS5 over all sessions in SQLite at zero LLM cost. External providers (Honcho etc.) run alongside the built-in store. |
| Write approval | `memory.write_approval` stages writes for `/memory pending` and `/memory approve`; `skills.write_approval` stages skill writes for `/skills approve` / `/skills reject`. `display.memory_notifications`: off / on / verbose. `/journey` lists, edits, deletes learned nodes. |
| Background review | Runs after turns, may save memories or update skills; token cost can be capped or the review disabled. |
| Skills | Progressive disclosure: L0 `skills_list` (name, description, category, ~3k tokens), L1 `skill_view`, L2 one reference file. `skill_manage`: create, patch (preferred), full rewrite, `write_file` / `remove_file`, delete. Agent saves a skill after a repeatable multi-step workflow, after recovering from errors, or after a user correction. |
| Skills Hub trust | Tiers: builtin, official, trusted, community. Scanner checks exfiltration, prompt injection, destructive commands, supply-chain signals. `--force` overrides non-dangerous findings only, never a dangerous verdict. `lock.json` records source URL, content hash, scanner version, findings. Dangerous project-local skills are quarantined and hidden from the index. |
| Curator | Stale at 14 days unused, archived at 30 days (see caveat). LLM consolidation (merge, patch, archive) is opt-in. Worst outcome is archival, never deletion. Exempt: pinned skills, skills referenced by cron, hub-installed skills. `--dry-run`, per-run `REPORT.md` and `run.json`, tar.gz snapshot before consolidation, `.curator_ledger.jsonl` with per-entry rollback. Counters: `view_count`, `use_count`, `patch_count`, `last_used_at`. Pin blocks archive/delete; lock blocks all agent edits. |
| Delegation | `delegate_task`: fresh child context, only the final summary returns. Flat by default (`max_spawn_depth=1`), 10 concurrent children. Over-limit batch is a tool error, not silent truncation. Children cannot get toolsets the parent lacks and are blocked from memory, `send_message`, `clarify`, `cronjob`. `output_schema` check sets `schema_valid:false` on mismatch. Statuses: completed, failed, timeout, interrupted. Opt-in git worktree isolation and stall monitor. Docs warn depth 3 x concurrency 3 = 27 leaf agents. |
| Command approval | Modes: smart (auxiliary LLM risk-scores commands), manual, off. Choices: once, session, always (persisted to config), deny (default). 300 s timeout denies (fail-closed). Hardline blocklist (`rm -rf /`, fork bombs) applies even in YOLO mode. User `approvals.deny` globs checked before YOLO/off. |
| Gateway auth | Default deny when no allowlists are set. Unknown users get an 8-char DM pairing code (expires 1 h); requests rate-limited; 5 failures cause 1 h lockout. In shared chats an `approvers` list restricts who can answer approvals. `AGENTS.md` / `SOUL.md` scanned for prompt injection before loading. |

Gaps in the sources: curator docs disagree on the archive threshold (30 days in config defaults vs "90d unused -> archived" elsewhere).

### 3.3 Grok Bot / Team Bots (xAI, branded SpaceXAI)

"GrokBot" is the operator's name for the Grok Bot app. Verification: `docs` for the three docs.x.ai
pages in section 10. Items marked `secondary` below are not verified. `x.ai/changelog/bot` returned 403.

| Area | Finding | Evidence |
|---|---|---|
| Groups | Scoped to one outcome, 2-6 Bots, membership editable. No @mention: Bots decide who responds. `@Bot` assigns a single owner. `@everyone` for group updates, used sparingly. Docs: "Ask for a single owner at each stage" (parallel handoffs create duplicate work). Every Bot reply counts toward usage. | `docs` |
| Bot-to-Bot | Handoff by async message. A personal Bot in a Slack thread cannot message other Bots; a Team Bot can message its acting teammate's Bots. | `docs` |
| Interruption | A user DM takes priority over background work and can redirect it. "Stop now" ends work but does not undo completed actions. | `docs` |
| Outbound drafts | Outbound email and Slack are drafts by default ("Needs approval" card: Send / Discard). Owner can "Disable drafts for Bot" (still subject to Auto Review). Unrequested email from the Bot's own address always stays a draft. Calls need Call / Cancel each time; only the owner can pay. | `docs` |
| Approval cards | Allow once (no rule), Always allow (saves an Allow rule for similar actions), Deny (no retry until next user message). Chat cards wait indefinitely; routine/background cards expire after 30 min. Docs: "An approval controls the proposed action. It does not reverse work already completed." In Slack only the requester can answer "Review an action". | `docs` |
| Auto Review and rules | Auto Review on by default, checks each action, routes some to cards. Custom Rules: "Allow automatically" or "Ask first", max 20 each; "Ask first" wins on conflict. Admins can require Auto Review; team rules always apply; personal rules can only tighten; admins can cap local-computer execution. | `docs` |
| Security boundary | All of a user's Bots share one cloud computer (files, browser sessions, CLI credentials). Docs: "Do not use separate Bots as a security boundary." Team Bot keys and files are visible to all teammates. | `docs` |
| Roles and lifecycle | Owner (chat, edit/share, delete), Manager (chat, edit/share), Collaborator (chat). New Bot is a draft visible only to its creator until Publish. Sharing: team, org, or "People you invite"; owner can set "Only you". | `docs` |
| Review learnings | What teammates teach for the team sits as Suggested until an Owner/Manager approves or rejects each item. Owner/Manager edits in main chat apply immediately. Each person's chat with a Team Bot is private, even from Owners/Managers. | `docs` |
| Skill update approval | A teammate's suggested skill change ("Update the skill") needs approval. | `secondary`, unverified |
| Connectors | Individual accounts, owner's shared account, or a separate Bot account. Shared personal logins need admin "Allow Shared Logins" (off by default). | `docs` |
| Admin | "Manage Bots" lists every shared Bot; Bot sharing Everyone / Admins only; auto-add to sidebars; Slack access. Analytics: messages, hours saved, top users, DAU/WAU (7/30/90 d). | `docs` |
| Account split | Tools and skills at account level, shared across Bots; memory and routines per Bot. | `secondary`, unverified |
| Teach a task | Records a browser demonstration and drafts a skill for review and test. Routines are scheduled or event-triggered. | `secondary`, unverified |
| Grok 4.20 multi-agent API | 4 or 16 agents with a leader that writes the final answer. | `snippet`, unverified |

Not used: pricing ($120/mo) and version numbers conflict across sources; launch dates unverified; one
docs.x.ai page mentions privacy settings in "Cursor account settings", left out as unexplained.

### 3.4 OpenAI Dots ("GPT Dots") — UNVERIFIED

> **Status: unverified.** Existence and core shape are corroborated by several independent outlets
> (Zapier, Tom's Guide, PCWorld, DataCamp, Flavio Copes). The official announcement
> (`openai.com/index/introducing-dots/`) returned 403, so every detail below is secondhand.
> Treat each row as a press or author claim.

"GPT Dots" refers to OpenAI's Dots, announced at DevDay on 29 Sep 2026: persistent always-on agents in
ChatGPT, each with its own cloud computer, using ChatGPT plugins/connectors, working across ChatGPT, voice,
Slack and Microsoft Teams. "Specialist dots" take company roles with their own identity, credentials and
system access, with enterprise governance via Microsoft Agent 365. One dot per user at launch; teams of
dots in testing.

| Area | Reported pattern |
|---|---|
| Identity | Name plus customizable avatar (shape, color, eyes, accessories); name sets a handle such as `@name-dot`. One dot across channels; each channel keeps its own history, learning is shared; switching channels does not create a new dot. |
| Onboarding | Conversational: the dot reviews ChatGPT memory and connected apps, introduces itself, proposes where it can help. A "responsibility" is given in conversation (what should stay true, sources to read, what needs attention, what not to do yet) rather than an instructions form. |
| Rules | Four levels: act without asking, act when you say so, ask first, hand off to you. Rules cannot override safety checks, Auto-review or proactive-research limits; admins can disable Custom Rules. Password changes and money transfers always go to the user; purchases need approval. Auto-review checks actions such as outgoing email and runs, asks, or leaves them to the user. |
| Plugin permissions | Granular per action (e.g. read email without send). |
| Profile | Activity (progress, files, results, background work, tasks waiting on decision / sign-in / connection / approval, answered in place), Scheduled (disable or delete), Computers. Take over / Return control on the cloud computer. Pause stops the main task but not delegated tasks, which must be stopped individually. |
| Anti-pattern | Individual learned notes cannot be viewed, corrected or deleted; deleting the dot is the only full reset. Disconnecting a plugin stops new access but does not erase what was learned. (`secondary` only) |

Ignored: model names (GPT-6 Astra / GPT-6.1 Terra) and an unverified report of a halted GPT-6.1 Astra release.

### 3.5 CrewAI (framework + CrewAI AMP)

Verification: `docs` (docs.crewai.com agents and processes pages).

| Area | Finding |
|---|---|
| Agent definition | Role, goal, backstory, plus `llm`, a separate `function_calling_llm`, and tools. Limits: `max_iter` (default 20, then best answer), `max_retry_limit`, `max_rpm`, `max_execution_time`. |
| Delegation | `allow_delegation` defaults to False; opt in per agent. |
| Processes | Sequential: each output feeds the next; `Task.context` passes specific outputs. Hierarchical: requires `manager_llm` or `manager_agent`; tasks are not pre-assigned, the manager allocates by capability and validates outputs. |
| Config as files | `agents/<name>.jsonc` and `crew.jsonc`, or YAML with `@CrewBase`; values under `settings` take precedence. |
| Loop guard | Same tool call returning the same result 5 times stops the task with `ToolExecutionFailedError`. Large tool results can be deferred to temp files and read in sections. |
| AMP | Visual Agent Builder: form-based configuration, real-time testing, template library. |

Gaps in the sources: the agents page does not describe distinct memory types or human-input mechanics.

### 3.6 LangGraph Studio (LangSmith)

Verification: `docs` (docs.langchain.com Studio and interrupts pages).

| Area | Finding |
|---|---|
| Two views | Graph mode: traversed nodes, intermediate state, LangSmith actions (send to dataset, open playground). Chat mode: simpler UI for business users; requires `MessagesState`. |
| Assistants | Versioned configurations of one graph, managed separately from threads. |
| Time travel | Inspect and debug state at past checkpoints. Forking is referenced by linked docs; the Studio page does not detail forking or state editing. |
| HITL | `interrupt(payload)` pauses a node; `Command(resume=value)` resumes on the same `thread_id`; requires a durable checkpointer. Patterns: approve/reject routing, review-and-edit (edit written back to state). On resume the node restarts from its beginning, so pre-interrupt side effects must be idempotent. |
| Trace to eval | Direct path from a trace to a dataset and an experiment. |
| No-code drafting | LangSmith Cloud only: describe the agent, chat drafts the config, user reviews and saves. |

### 3.7 OpenAI Agents SDK

Verification: `docs` (openai.github.io/openai-agents-python).

| Area | Finding |
|---|---|
| Orchestration patterns | Manager (`Agent.as_tool`): one agent keeps the conversation, calls specialists, synthesizes; shared guardrails enforced in one place. Handoff: a triage agent transfers the turn and the specialist becomes active. Combinable. |
| LLM vs code orchestration | LLM-driven is open-ended; code-driven (structured-output routing, chaining, evaluator loops, parallel runs) is more deterministic for speed, cost and performance. |
| Tool approval | `needs_approval` is a bool or per-call async callable. Pending approvals surface as `RunResult.interruptions` (`ToolApprovalItem` with tool name and arguments). Pause via `to_state()`, resolve with approve/reject (optional `rejection_message`), resume with `Runner.run(agent, state)`. Partial resolution allowed. |
| Sticky decisions | `always_approve` / `always_reject` are sticky per tool identity; per-call approvals scoped to the call ID. Function-tool sticky decisions are scoped to the requesting agent; for shell and `apply_patch` they can carry across handoffs. |
| State security | `RunState` serializes via `to_json` / `from_json`. Docs warn deserializing does not authenticate the snapshot or the submitter; store server-side. |
| Guardrails and tracing | Guardrails run in parallel with execution and fail fast; tool guardrails are separate. Built-in tracing feeds evals and fine-tuning. |

## 4. Cross-product comparison

Dots column is unverified throughout.

| Concern | OpenClaw | Hermes | Grok Bot | Dots (unverified) | Frameworks (CrewAI, LangGraph, Agents SDK) |
|---|---|---|---|---|---|
| Agent config split | Workspace / agentDir / session store | Context files + config | Role, memory, routines per Bot; skills account-level (`secondary`) | Identity + responsibility in conversation | Role/goal/backstory (CrewAI); assistants as versioned config (LangGraph) |
| Unrouted input | Fallback owner or undispatched | Default deny, pairing code | Bots decide without @mention | One dot across channels | n/a |
| Delegation bounds | Own session, no session/message tools | Depth 1, 10 concurrent, over-cap is error, capability subset | Single owner per stage | Pause does not cascade | `allow_delegation=False` default (CrewAI) |
| Approval verbs | Allow once / always / deny | Once / session / always / deny | Allow once / always / deny | Four rule levels | approve / reject / always_* (Agents SDK) |
| Approval timeout | `askFallback` deny | 300 s deny | Chat waits; background 30 min | n/a | Durable paused state |
| Policy layering | Per-agent gate only restricts | Hardline blocklist over YOLO | Team rules always apply; personal only tighten; Ask first wins | Rules cannot override safety | Guardrails fail fast |
| Skill install trust | VirusTotal verdict, daily rescan, install policy hook | Trust tiers, no `--force` on dangerous, lock.json | Teach a task -> review (`secondary`) | n/a | n/a |
| Skill lifecycle | Precedence, eligibility gates | Stale/archive, pin/lock, ledger rollback | n/a | n/a | n/a |
| Memory core | `MEMORY.md` with bootstrap budget | 2,200 / 1,375 char hard caps, frozen snapshot | Per Bot | Learned notes, not inspectable | n/a |
| Learning curation | `DREAMS.md` review | write_approval queues, `/journey` | Review learnings (Suggested -> approve) | None reported | Review-and-edit interrupts (LangGraph) |
| Monitoring | Subagents panel, collapsed tool bursts, Changes view | Status per child, stall monitor | Admin analytics | Activity / Scheduled / Computers | Graph vs chat view, time travel, trace -> dataset |

## 5. Koda baseline used for mapping

Only items checked for this document are listed. Implementation depth beyond what is named was not verified.

| Area | What exists | Location | Evidence |
|---|---|---|---|
| Agents | Agent catalog with `draft_snapshot` / `published_snapshot` and a publish action | `koda/control_plane/manager.py`; web `/control-plane/agents` | `inv` |
| Operator roles | Operator rows carry a `role` field defaulting to `owner`; no Owner/Manager/Collaborator split for agent editing found | `koda/control_plane/operator_auth.py` | `inv` (grep only) |
| Channels | `channel_gateway.v1`; gateway statuses `pending`, `paired`, `allowed`, `blocked`, `revoked`; decisions `allow`, `queue_for_pairing`, `deny`, `paired`; pairing codes | `koda/channels/gateway.py` | `inv` |
| Channel scope | Telegram live; Slack/Discord adapters validated locally against the same contract | README | `claimed` |
| Squads | Mentions, reply obligations, triage, semantic router, synthesis gate, coordinator; coordinator decisions `answer_self`, `delegate`, `handoff` recorded as `coordination_mode` metadata | `koda/squads/` | `inv` |
| Squad UI | Room rail, room chat pane, room settings drawer, squad spec editor; no coordination-mode field found in the squad spec editor | `apps/web/src/components/sessions/`, `apps/web/src/components/control-plane/catalog/squad-spec-editor.tsx` | `inv` (grep) |
| Child runs | `MAX_CHILD_RUNS_PER_CALL = 4`, `MAX_CONCURRENT_CHILD_RUNS_PER_PARENT = 2`, `MAX_CHILD_RUN_TIMEOUT_SECONDS = 600`; over-cap request returns an error; statuses include `queued`, `running`, `retrying`, `stalled`, `degraded`, `failed`, `cancelled`, `completed`, `needs_review` | `koda/services/child_runs.py` | `inv` |
| Child-run memory | No parent/shared memory recall or writes unless `child_context_policy.include_memory` / `allow_memory_writes` | `docs/architecture/memory-governance.md` | `claimed` |
| Child-run UI | Child runs referenced in RunGraph panels, runtime task room, execution detail | `apps/web/src/components/runtime/`, `apps/web/src/components/executions/` | `inv` |
| Approvals | `APPROVAL_TIMEOUT = 300` s; pending ops older than that are removed; Telegram inline keyboard "Aprovar uma vez" / "Aprovar escopo" / "Negar"; scoped grants with `expires_at` and `remaining_uses`; broker decisions `approve`, `approve_scope`, `deny` with optional `reasons` | `koda/utils/approval.py`, `koda/services/approval_broker.py` | `inv` |
| Skills | Local packages, registry, selector, telemetry (`emit_skill_selection`, `emit_skill_invocation`, `emit_skill_reload`, `emit_skill_compliance`) | `koda/skills/` | `inv` |
| Skill scanner | `skill_scan.v1`: `decision` allow / review_required / deny, findings, `package_hash`, `file_hashes`, `scanner_version` | `docs/security/skill-supply-chain-scanner.md` | `claimed` |
| Skill lifecycle | No `stale` / `archived` / `pinned` / `locked` states found | `koda/skills/` | `inv` (grep) |
| Memory | Safety scanner; namespaces `user`, `agent`, `squad`, `workspace`, `project`, `org`; `MemoryResolution` with explicit drop reasons; utility feedback `useful` / `noise` / `misleading`; review route | `koda/memory/`, web `/memory`, `/memory/review` | `inv` + `claimed` |
| Memory budget | No character/token budget setting found in memory config | `koda/memory/config.py` | `inv` (grep); recall limits not checked |
| Self-improvement | `improvement_proposal.v1` statuses `draft`, `pending_review`, `approved`, `rejected`, `validating`, `applied`, `rolled_back`, `failed`; apply only after validation; rollback via effect ledger | `koda/services/improvement_proposals.py`, `docs/architecture/improvement-proposal.md` | `inv` + `claimed` |
| Monitoring | RunGraph service and store; RunGraph panels; quality cockpit; audit components; routes `/runtime`, `/runtime/[agentId]`, `/executions`, `/tasks`, `/sessions`, `/routines`, `/costs`, `/evaluations` | `koda/services/run_graph.py`, `koda/services/quality_cockpit.py`, `apps/web/src/app/` | `inv` |
| Global inbox | No "Needs you" inbox found in the web app | `apps/web/src/` | `inv` (grep) |

## 6. Design principles for Koda

Each principle lists its basis, what Koda has today (from section 5), and the gap. Gaps are proposals
and have not been scoped or accepted.

### 6.1 Agents (identity and configuration)

**P1. Three edited layers per agent.** Identity (name, @handle, avatar, voice), Operating contract
(rules compiled into the runtime prompt contract), Access (provider/model, tools, secrets, skills,
sandbox). Child runs inherit the operating contract even when they skip the persona. Two agents never
share credential or session state.
- Basis: OpenClaw workspace / agentDir / session split and "never reuse agentDir" (`docs`); Grok Bot roles and memory per Bot (`docs`).
- Koda today: control-plane agent documents compile into the runtime prompt contract (`claimed`, CLAUDE.md core invariant); draft and published snapshots exist (`inv`).
- Gap: whether the agent editor separates these three layers, and whether child runs carry the operating contract, was not checked.

**P2. Show the effective config and its origin.** Every resolved value shows where it came from
(workspace default, squad, agent override). Lists state explicitly whether they replace or merge with
defaults, and what an empty list means.
- Basis: OpenClaw per-agent skill allowlist replaces defaults; `[]` means none (`docs`).
- Koda today: not checked.
- Gap: add a resolved-config view with provenance per value and replace/merge labels on list fields.

**P3. Draft -> publish lifecycle with diff and roles.** Draft agents are visible only to their creator;
publishing shows a diff and makes the agent routable from channels and squads. Editing is role-gated
(Owner / Manager / Collaborator).
- Basis: Grok Team Bots draft-until-Publish and roles (`docs`); LangGraph versioned assistants (`docs`).
- Koda today: `draft_snapshot` / `published_snapshot` and a publish action exist; operator role defaults to `owner` with no finer split found (`inv`).
- Gap: pre-publish diff and draft visibility rules not checked; Manager / Collaborator roles do not exist.

### 6.2 Channels and routing

**P4. One @handle, explicit bindings, explicit fallback.** Each agent has one @handle across dashboard,
Telegram and Slack/Discord. The agent page shows channel bindings, resolved most-specific-first.
Unbound or ambiguous messages go to a named fallback owner or stay undispatched. Groups require a
mention. Access defaults to deny, with expiring pairing codes and lockout after repeated failures.
- Basis: OpenClaw bindings and fallback (`docs`); Hermes default deny, 1 h pairing codes, 5-failure lockout (`docs`); Dots cross-channel handle (`unverified`).
- Koda today: gateway pairing, allow, block, revoke (`inv`); group mention routes into squad delivery (`claimed`).
- Gap: pairing-code expiry, failure lockout and fallback-owner behavior were not checked.

### 6.3 Squads

**P5. Small, outcome-scoped squads with one owner per stage.** In the Squad Room composer, `@agent`
sets an owner chip; `@everyone` is the exception. The current owner and open reply obligations are
always visible. A live cost hint shows that every agent reply costs tokens.
- Basis: Grok Bot 2-6 Bot groups and "ask for a single owner at each stage" (`docs`).
- Koda today: mentions, reply obligations and Squad Room transcript exist (`inv`).
- Gap: owner chip, persistent obligation display and cost hint not checked.

**P6. Coordination mode is an explicit squad setting.** Options: Lead synthesizes (agents-as-tools;
one agent keeps the conversation and the synthesis gate), Handoff (specialist takes the turn),
Sequential pipeline, Manager allocates. Every transcript turn carries a route explanation.
- Basis: OpenAI Agents SDK manager vs handoff (`docs`); CrewAI sequential vs hierarchical (`docs`).
- Koda today: coordinator decides per message among `answer_self`, `delegate`, `handoff` and records `coordination_mode` metadata; synthesis gate exists (`inv`).
- Gap: mode is a per-message decision, not an operator setting; no mode field found in the squad spec editor (`inv`, grep).

### 6.4 Delegation and child runs

**P7. Child runs are bounded and fail loudly.** Each child starts from an explicit goal and context,
returns a summary, a status and an optional schema-validity flag. Flat by default with a concurrency
cap; an over-cap batch is a hard error. A child never gets capabilities its parent lacks and is blocked
by default from memory writes, outbound messaging and scheduling. Raising limits shows a
depth x concurrency cost preview.
- Basis: Hermes `delegate_task` (`docs`); CrewAI `allow_delegation=False` default (`docs`).
- Koda today: 4 per call, 2 concurrent per parent, 600 s timeout, over-cap error (`inv`); memory recall/writes off by default for child runs (`claimed`).
- Gap: capability-subset enforcement, outbound-messaging and scheduling blocks, schema-validity flag and cost preview not checked.

**P8. Child runs panel with stated cascade behavior.** Each task room shows Running and Finished child
runs with model, cost, depth, status, transcript link and Stop. Pause and Stop say whether they cascade
to child runs.
- Basis: OpenClaw Subagents panel (`docs`); Dots Pause not cascading (`unverified`).
- Koda today: child runs appear in RunGraph panels, runtime task room and execution detail (`inv`).
- Gap: Running/Finished split, per-row Stop and cascade wording not checked.

### 6.5 Skills

**P9. The supply-chain check is the install UI.** The install sheet shows source, content hash, trust
tier, scanner version, verdict and findings, required bins/env/config, eval evidence, and which agents
will see the skill. A deny verdict is a hard block with no override. Periodic rescans with a freshness
badge. Scanning is paired with sandboxed evals because scanners miss prose prompt injection.
- Basis: Hermes trust tiers, no `--force` on dangerous, `lock.json` (`docs`); OpenClaw VirusTotal daily rescans and ClawHavoc lesson (`docs`).
- Koda today: `skill_scan.v1` with allow / review_required / deny, package and file hashes, scanner version (`claimed`); README claims a trust registry and eval-backed recommendation (`claimed`).
- Gap: install-sheet presentation, rescan cadence and override rules not checked.

**P10. Visibility and authority are separate panels.** "Skills this agent can see" and "Tools and
permissions this agent can execute" are shown apart; the effective capability is their intersection.
A skill never implies credentials or tools.
- Basis: OpenClaw "an allowlist is not a shell authorization boundary" (`docs`); Grok "do not use separate Bots as a security boundary" (`docs`).
- Koda today: strict skill allowlists and tool policy both exist per README (`claimed`).
- Gap: whether the UI shows both and their intersection was not checked.

**P11. Skill lifecycle with telemetry, Pin and Lock.** Per-skill views, uses, patches, last used.
States active / stale / archived. Curator or consolidation output enters as `improvement_proposal.v1`
items with dry-run diff, snapshot and per-entry rollback, never silent mutation. Archive instead of
delete; exempt hub-installed skills and skills referenced by routines.
- Basis: Hermes curator (`docs`).
- Koda today: skill telemetry events exist (`inv`); proposal lifecycle with rollback ledger exists (`inv` + `claimed`); no stale/archived/pinned/locked states found (`inv`, grep).
- Gap: lifecycle states, Pin/Lock and per-skill usage counters in the UI.

### 6.6 Memory and learning

**P12. Budgeted core above a searchable recall store.** A small always-on core with a capacity meter,
above a large searchable store. A full core requires consolidation, not silent truncation. Operators
are told when memory changes take effect.
- Basis: Hermes hard caps and frozen per-session snapshot (`docs`); OpenClaw `MEMORY.md` bootstrap budget (`docs`).
- Koda today: namespaced memory with recall explanations (`inv` + `claimed`); no budget setting found in `koda/memory/config.py` (`inv`, grep).
- Gap: core/recall split, capacity meter and effect-timing notice.

**P13. One Learning inbox for every proposed durable change.** Memory promotions, skill patches,
prompt or policy edits, and teammate-taught facts share one queue. Each item shows scope (personal /
agent / squad / workspace), evidence, diff and Approve / Reject. Owner and manager edits may apply
directly; everyone else's are suggestions. Personal learning stays private to that person and agent.
- Basis: Grok Review learnings (`docs`); Hermes `write_approval` (`docs`); OpenClaw `DREAMS.md` (`docs`).
- Koda today: `improvement_proposal.v1` queue (`inv`); `/memory/review` route (`inv`).
- Gap: whether memory review and proposals share one queue was not checked; manager role does not exist (P3).

**P14. Every learned item is inspectable, editable and deletable.** Each item shows provenance (source
run, channel, connector), last-recalled time and utility. Revoking a connector or identity offers to
purge what was derived from it.
- Basis: avoids the reported Dots anti-pattern (`unverified`).
- Koda today: provenance, drop reasons and utility feedback exist (`claimed`).
- Gap: per-item edit/delete and purge-on-revoke not checked.

### 6.7 Governance and approvals

**P15. Standard approval verbs everywhere, narrow "Always", fail closed.** Dashboard and Telegram use
the same verbs: Allow once / Allow for this session / Always allow (visible, revocable rule) / Deny with
reason. "Always" binds to a scope the card displays (exact argv and cwd, or tool and argument pattern).
Timeout or no reachable UI means deny. Background approvals expire. In groups only the requester or
listed approvers can answer.
- Basis: OpenClaw argv/cwd binding and `askFallback` deny (`docs`); Hermes 300 s deny and approvers list (`docs`); Grok 30 min background expiry and requester-only answers (`docs`).
- Koda today: approve once / approve scope / deny; 300 s timeout removes pending ops; scoped grants with expiry and use count; optional `reasons` on broker decisions (`inv`).
- Gap: no session-scoped verb; whether the card shows the grant scope, and who may answer in groups, was not checked.

**P16. Policy resolves toward strictness.** Workspace rules always apply; agent and personal rules can
only tighten; "Ask first" beats "Allow automatically". A hardline blocklist no mode can override.
Outbound communication defaults to draft-for-review. An optional AI-reviewer tier can allow, deny with
reason, or escalate; every decision goes to audit and RunGraph.
- Basis: Grok layered rules and Auto Review (`docs`); Hermes hardline blocklist and smart mode (`docs`); OpenClaw auto mode (`docs`).
- Koda today: tool policy, command blocking and audit exist (`claimed`; CLAUDE.md safe editing rules).
- Gap: rule-layering semantics, draft-by-default outbound and AI-reviewer tier not checked.

**P17. Say that approving or stopping does not undo work.** Stop and Cancel dialogs list side effects
already executed (from RunGraph) and state whether child runs and scheduled routines are affected.
- Basis: Grok "does not reverse work already completed" (`docs`).
- Koda today: RunGraph records lifecycle evidence (`inv`).
- Gap: dialog content not checked.

### 6.8 Monitoring

**P18. Agent profile organized around activity.** Order: Needs you (blocked on approval, credential,
decision, pairing), Running, Scheduled, Recent results and files. Transcripts collapse tool bursts into
one expandable line and keep a Changes view for diffs. A task toggles between a Transcript view and a
RunGraph view with per-node state, replay and fork from a checkpoint.
- Basis: Dots profile (`unverified`); OpenClaw collapsed turns and Changes view (`docs`); LangGraph graph vs chat mode and time travel (`docs`).
- Koda today: `/runtime/[agentId]`, RunGraph panels, run-graph replay doc (`inv`).
- Gap: Needs-you ordering, tool-burst collapse and fork-from-checkpoint not checked.

### 6.9 Information architecture and density

**P19. Three cross-linked planes and a global Needs-you count.** Work (sessions, Squad Rooms, channels),
Configuration (control plane), Evidence (runtime, RunGraph, evals, audit). Every evidence row links to
the config version and rule that produced it. A sidebar count combines approvals, pending learnings,
pairing requests and quarantined skills. List pages (sessions, routines, usage, approvals) support
all-agents and single-agent scope.
- Basis: OpenClaw all-agent views (`docs`); Grok Manage Bots analytics (`docs`).
- Koda today: routes for each plane exist (`inv`); no Needs-you inbox found (`inv`, grep).
- Gap: global inbox, evidence-to-config links, scope toggle on list pages.

**P20. Row-first, low-density presentation.** Row lists with hair dividers, status dots (pulse when
running), compact timestamps (4m, 2h); no card per agent or skill. State, budgets and counts inline
(memory meter, skill trust tier and last used, approval scope and expiry). Detail on demand through
progressive disclosure and drawers rather than modals in full-bleed routes.
- Basis: Hermes L0/L1/L2 skill disclosure (`docs`).
- Koda today: `apps/web/CLAUDE.md` already requires low density, no nested cards and no decorative noise (`inv`, headings and UX sections skimmed).
- Gap: none in principle; apply when building P2, P9, P11, P12, P15 surfaces.

## 7. Principle-to-surface map

| Principle | Feature area | Backend touchpoints | Web touchpoints |
|---|---|---|---|
| P1-P3 | Agents | `koda/control_plane/manager.py`, `koda/control_plane/operator_auth.py`, runtime prompt contract | `/control-plane/agents`, `components/control-plane/editor` |
| P4 | Channels | `koda/channels/gateway.py` | Channel gateway UI |
| P5-P6 | Squads | `koda/squads/coordinator_engine.py`, `mentions.py`, `replies.py`, `synthesis_gate.py` | `components/sessions/`, `squad-spec-editor.tsx` |
| P7-P8 | Delegation | `koda/services/child_runs.py`, `koda/services/queue_manager.py` | `components/runtime/`, `components/executions/` |
| P9-P11 | Skills | `koda/skills/`, `koda/services/improvement_proposals.py` | Control-plane catalog |
| P12-P14 | Memory | `koda/memory/`, `koda/control_plane/dashboard_memory.py` | `/memory`, `/memory/review` |
| P15-P17 | Governance | `koda/utils/approval.py`, `koda/services/approval_broker.py`, `koda/control_plane/audit.py` | Approval cards, audit components |
| P18 | Monitoring | `koda/services/run_graph.py`, `koda/services/quality_cockpit.py` | `/runtime`, `/executions`, `/tasks` |
| P19-P20 | IA and density | n/a | App shell, sidebar, list pages |

## 8. Anti-patterns to avoid

| Anti-pattern | Seen in | Evidence |
|---|---|---|
| Learned notes not individually viewable or deletable; only full reset | Dots | `unverified` (`secondary`) |
| Disconnecting a connector leaves derived learning in place | Dots | `unverified` (`secondary`) |
| Pause that silently does not stop delegated work | Dots | `unverified` |
| Treating a skill allowlist as an execution boundary | OpenClaw docs warn against it | `docs` |
| Treating separate agents on shared compute as a security boundary | Grok docs warn against it | `docs` |
| Parallel handoffs to several agents for one stage (duplicate work) | Grok docs warn against it | `docs` |
| Silent truncation of an over-cap delegation batch or memory core | Hermes and OpenClaw avoid it via errors and consolidation | `docs` |
| Force-override of a dangerous scan verdict | Hermes forbids it | `docs` |
| List fields whose replace-vs-merge semantics are invisible | OpenClaw skill allowlists | `docs` |
| Trusting deserialized run state without server-side storage | Agents SDK docs warn against it | `docs` |

## 9. Caveats and open questions

1. Product facts are from a single research pass on 2026-11-14 and were not re-fetched for this document.
2. OpenAI Dots is unverified as a whole. Grok Bot items marked `secondary` or `snippet` are unverified.
3. Hermes curator archive threshold is inconsistent in its own docs (30 vs 90 days).
4. The OpenClaw Control UI page does not describe Approvals, Skills, Cron or Logs tabs; LangGraph Studio does not detail forking or state editing; CrewAI agents docs do not cover memory types or human input.
5. Koda baseline rows marked `claimed` restate README and `docs/` text. Rows marked `inv (grep)` record that a term was not found, which does not prove a feature is absent.
6. The root Obsidian vault memory was not read for this document.
7. Open questions for owners:
   - Should coordination mode (P6) be an operator setting, a per-message decision as today, or both?
   - Is a Manager / Collaborator role split (P3, P13) in scope for a self-hosted single-owner product?
   - Should "Allow for this session" (P15) be added alongside the existing once / scope grants?
   - Where should memory review and improvement proposals converge (P13)?

## 10. Sources

OpenClaw:

- https://docs.openclaw.ai
- https://docs.openclaw.ai/concepts/multi-agent
- https://docs.openclaw.ai/tools/exec-approvals
- https://docs.openclaw.ai/tools/skills
- https://docs.openclaw.ai/concepts/memory
- https://docs.openclaw.ai/tools/subagents
- https://docs.openclaw.ai/web/control-ui
- https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html
- https://www.openclaw.ai/blog/virustotal-partnership
- https://clawdocs.org/getting-started/introduction

Hermes Agent:

- https://hermes-agent.nousresearch.com/docs
- https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- https://hermes-agent.nousresearch.com/docs/user-guide/features/curator
- https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- https://hermes-agent.nousresearch.com/docs/user-guide/security
- https://betterstack.com/community/guides/ai/hermes-agent/ (secondary)

Grok Bot / Team Bots:

- https://docs.x.ai/grok-bot/chat-and-collaboration
- https://docs.x.ai/grok-bot/team-bots
- https://docs.x.ai/grok-bot/approvals-security-and-privacy
- https://flaviocopes.com/grok-bot-1-0/ (secondary)
- https://composio.dev/content/guide-to-frok-bot (secondary)
- https://alphasignal.ai/news/xai-s-grok-team-bots-give-entire-teams-one-shared-ai-agent (secondary)
- https://docs.x.ai/developers/model-capabilities/text/multi-agent (snippet only, not fetched)

OpenAI Dots (all unverified):

- https://openai.com/index/introducing-dots/ (returned 403)
- https://flaviocopes.com/openai-dots/
- https://zapier.com/blog/chatgpt-dots/
- https://www.tomsguide.com/ai/openai-gave-chatgpt-a-virtual-computer-to-run-errands-for-you
- https://www.pcworld.com/article/3246780/
- https://www.datacamp.com/nl/blog/openai-dots

CrewAI:

- https://docs.crewai.com/en/concepts/agents
- https://docs.crewai.com/en/concepts/processes

LangGraph Studio:

- https://docs.langchain.com/langgraph-platform/langgraph-studio
- https://docs.langchain.com/oss/python/langgraph/interrupts

OpenAI Agents SDK:

- https://openai.github.io/openai-agents-python/
- https://openai.github.io/openai-agents-python/multi_agent/
- https://openai.github.io/openai-agents-python/human_in_the_loop/
