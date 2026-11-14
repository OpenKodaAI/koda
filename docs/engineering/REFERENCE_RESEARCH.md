# Reference Product Research

UI/UX research input for the consolidation mission ([MISSION.md](MISSION.md)), 2026-11-14.
It summarizes what was found about eight reference products and distills design principles
for Koda, mapped onto the agents, squads, skills, memory, governance and monitoring surfaces
that exist in this repository. The eighth, OpenBot (section 3.8), was named by the operator as a
reference for design, user experience, chat and agents; it also supplies the experience and visual
direction in section 6.10.

This file is research, not a plan or a spec. Principles in section 6 are proposals. Before any
of them becomes work, check it against the code and against
[`apps/web/AGENTS.md`](../../apps/web/AGENTS.md) and [`apps/web/CLAUDE.md`](../../apps/web/CLAUDE.md).

## 1. Scope and evidence

Inputs:

- A research pass on 2026-11-14 that fetched or searched the product pages listed in section 10.
  This document did not re-fetch those sources.
- Read-only inventory of this repository at commit `7c7b03f` (branch `claude/dreamy-cerf-mhvbwn`)
  for the Koda baseline in section 5.
- A second pass on 2026-11-14 for OpenBot (section 3.8). It fetched the openbot.run pages, the
  changelog and the GitHub README listed in section 10. It also drove the site with Playwright:
  8 marketing pages at 1440x900 and 390x844 under both colour-scheme settings, the interactive app
  preview at `/app-preview` in 39 states at 1440x900, keyboard focus, reduced motion, and the computed
  styles of the home page and the preview. The screenshots stay in the research scratch space and are
  not committed (licence and size). The Koda rows it added to section 5 were checked at commit
  `eca031f`.

Evidence labels:

| Label | Applies to | Meaning |
|---|---|---|
| `docs` | Products | Taken from the product's official documentation, fetched directly |
| `observed` | Products | Seen in a screenshot or in the live page during the 2026-11-14 capture; the page and screen state are named |
| `secondary` | Products | Taken from third-party articles or press; not confirmed in official docs |
| `snippet` | Products | Known only from a search-result snippet; page not fetched |
| `unverified` | Both | Not independently verified; do not treat as fact |
| `inv` | Koda | Checked in this repository with read-only commands (`ls`, `grep`, file reads) for this document |
| `claimed` | Koda | Stated in README or `docs/`; implementation depth not checked |

Most of these products launched or changed after the model training cutoff (OpenClaw renamed in
Jan 2026, ClawHavoc in Feb 2026, Grok Bot / Team Bots Aug-Nov 2026, OpenAI Dots announced
29 Sep 2026, OpenBot 0.1.0 to 0.71.0 between 13 Aug and 14 Nov 2026). All product facts below come
from the 2026-11-14 research passes, not prior knowledge.

**Licence rule for OpenBot.** OpenBot's source is published under the PolyForm Noncommercial 1.0.0
licence. This document records its patterns and principles only. No OpenBot code, text, brand, logo or
visual identity is copied into Koda, and nothing here proposes recreating its look. Koda keeps its own
design system ([`apps/web/CLAUDE.md`](../../apps/web/CLAUDE.md)).

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
| OpenBot (openbot.run, Nightly Labs) | Source-available, local-first desktop workspace for persistent agents that drive the provider CLIs the user already has; channels with one task owner; backup models | Verified (`docs`, `observed`); only the scripted app preview was used, not the signed-in app | Sessions and Squad Rooms UI, approval presentation, provider fallback, RunGraph, the web design system |

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

### 3.8 OpenBot (openbot.run, Nightly Labs)

Many products are called "OpenBot". Only the one at openbot.run is in scope: its header menu and FAQ
link to `github.com/nightly-labs/openbot`. The README and the site footer name Synthetify Labs (a Polish
limited company, sp. z o.o.) as the copyright holder; how that company relates to the `nightly-labs`
organisation was not checked. Licence: PolyForm Noncommercial 1.0.0, with commercial use under a
separate licence; versions up to 0.1.11 were Apache-2.0 (README, site FAQ). Section 1 sets the
patterns-only rule.

Verification: `docs` for the openbot.run pages, the changelog and the GitHub README in section 10.
`observed` for the 2026-11-14 capture (section 1). Every `observed` item in the app comes from
`/app-preview`, a scripted demo with sample data. The signed-in app, the desktop builds and the phone apps
were not used.

What it is: an Electron desktop app with a SolidJS renderer and a local SQLite event log. Persistent
agents drive the provider CLIs the user already pays for: Codex, Claude Code, Gemini through Antigravity,
Grok, OpenCode, Cursor, Cline, Pi, Muse Code, ACP agents, and OpenAI-compatible or local models. The
changelog lists 125 releases (0.1.0 to 0.71.0) between 13 Aug and 14 Nov 2026. About 2,152 of its
4,080 items are fixes; the research pass did this count. The fixes cluster on provider reliability,
the browser, routines, mobile, channels and remote servers.

**Product model**

| Area | Finding | Evidence |
|---|---|---|
| Agent identity | Name, avatar, title and a short description, plus standing rules in an `AGENTS.md` instructions file. Since 0.57.0 the description is "a short summary that teammates read to choose who does a task". Name and title repeat in the tab, the header, the list row and search. When the agent edits its own instructions, the chat shows "Updated its instructions" with View and Undo. | `docs` (changelog 0.57.0); `observed` (`/app-preview` header and list) |
| What an agent owns | A workspace folder, one durable thread, its identity, and a private provider session kept apart from the thread, so that "a model is just a setting". | `docs` (guides/openbot-101, news/one-agent-many-providers) |
| Agent creation | The user describes the agent in one prompt, reviews the generated instructions, then saves. Agents can create and configure other agents. Only the user can grant Full access, turn on Computer Use, change auto-approve or change MCP servers (0.24.0). Only the user's own message can make an agent change, delete or run a workflow (0.61.0). | `docs` (home FAQ; changelog 0.23.0, 0.24.0, 0.61.0) |
| Channels | A channel is a shared thread added on top of each agent's private thread, not a merged agent. One agent owns the task at a time and hands it on in a message ("you can read who took the work and why"). Controls: Stop, Resume, Reassign, Archive, Restore, and Cancel task. Greetings and unclear messages go to the lead (0.66.0). A fan-out collapses into one row such as "Assigned to Chief, Builder and Launch". A member may ask another member at most 2 short questions per request (0.62.0). A waiting request says why it waits, for example "the channel already runs 2 tasks" (0.71.0). | `docs` (guides/openbot-101; news/channels-put-agents-in-one-room; changelog) |
| Agent-to-agent messages | Ask or tell, with "no reply due" messages that open no turn (0.13.0). A "Waiting for replies" block shows each teammate as asked, working, replied or failed, and the agent reads all replies in one turn (0.23.0). An agent can stop only turns that its own messages started. | `docs` (changelog 0.13.0, 0.23.0, 0.71.0) |
| Busy agents | Each agent has a queue that shows why a message waits; queued messages can be edited, reordered, sent now or run in a new thread (0.10.0, 0.11.0). Since 0.69.0 a message steers into the running turn by default. A provider that cannot steer falls back to the queue with a "Not steered" reason. The home FAQ still says that messages wait in a queue. | `docs` (changelog; home FAQ) |
| Provider failover | Backup models: an ordered list, with "Ask before switching" on by default. A note in the chat marks each switch, and since 0.70.0 names the model that failed and the fix. The agent returns to its main model when the limit ends, or 10 minutes after a provider error. "A turn that already used a tool still does not run again, so a tool does not run two times" (0.68.0, #6594). Completed tool results carry over (0.51.0). After a switch the new model gets "selected parts" of the history, not a full replay. | `docs` (changelog 0.40.0, 0.48.2, 0.51.0, 0.68.0, 0.70.0; guides/ai-workspace-vs-chat); `observed` (`/app-preview` Backup models screen) |
| Permissions | After a one-time consent, agents run with `danger-full-access` and `approvalPolicy: never`. The README calls this "an explicit current product decision, not a security boundary", and the FAQ says agents act "without asking each time". A per-agent level offers Workspace only, Ask first or Full access (0.43.0). "Always allow" on an approval card moves the agent to Full access. Workspace only limits writes, but not reads or network. The preview's agent shows Full access and All files. | `docs` (README; guides/openbot-101; changelog 0.43.0); `observed` (`/app-preview` agent settings) |
| Always-ask carve-outs | Some actions ask even with broad access: a draft is shown before the agent sends a message for the user, and the item, price and total are read back before a payment (0.38.2); each screen capture is approved (0.39.1), and in a channel it always asks (0.48.0); the first saved-card fill on each site needs approval (0.50.0). | `docs` (changelog) |
| Waiting-for-you cards | One card design covers approval, browser takeover, code or password, usage limit, task answer and sign-in. Each shows "Waiting for you", with Skip or Cancel instead of X (0.66.0). Plain questions later moved into a question prompt, and button cards stayed for approvals only (0.68.0). Waits reach desktop notifications, a macOS overlay and the phone apps. | `docs` (changelog 0.4.0, 0.38.1, 0.66.0, 0.68.0) |
| Onboarding | Install and consent. Then connect a provider: OpenBot reuses the CLI's existing login ("If codex or claude works in your terminal, it works here"). Then fill in the first-agent form and run a first task that is "small, specific and checkable". The guide adds: read "the activity under the answer, not only the answer". | `docs` (guides/openbot-101) |
| Other surfaces | Not mapped to Koda: a workflow canvas with approval steps (0.50.0), a CDP-driven browser with take-over, a phone companion over WebRTC, a Marketplace of agents, skills and apps, team hosts with roles, and paid hosted servers. | `docs` (changelog; guides; pricing) |

**Chat and agent experience** (app preview at 1440x900)

| Area | Finding | Evidence |
|---|---|---|
| Shell | An icon rail, a resizable list that mixes agents and channels in user folders, the conversation, and an optional side panel (files, agent settings) opened as tabs. The window has back/forward history and conversation tabs. | `observed` (`/app-preview` chat and side panel) |
| Attention | A "Needs you" group at the top of the list carries a count while an agent waits; the row preview becomes the question. An "Unread" group follows, with counts on the avatars. Typing dots show while an agent works. Wait kinds are Answer, Review and Take over (0.25.0). | `observed` (`/app-preview` scenario); `docs` (changelog 0.25.0) |
| Turn summary | A coordinator turn collapses into one-line rows: a live status line; a plan card "3/5" that opens to a checklist; "Ran 2 subagents · 2 done · 3s", which opens to one result card per child (task, one-line outcome, duration); "4 messages with 3 agents"; and a footer "3 steps · Memory: 1 saved · 43s". A setting opens the steps by default; it is off by default. | `observed` (`/app-preview` expanded disclosures; settings) |
| Trace | The footer opens a Trace view. It has a metric strip (duration, LLM calls, tool calls, errors) and a waterfall on a time axis: one row per step, colour per agent, hatched waiting, a dotted handoff marker and a "Slowest" chip. It adds step search and replay. | `observed` (`/app-preview` trace) |
| Question card | Lettered options, each with a one-line rationale, a free-text "Something else", and Skip / Done. The thread shows "Waiting for your answer" and the header shows "Input required". The composer placeholder becomes "Type your answer". After the answer the card collapses to "Answers sent" with the chosen letters. A "NEW" divider and a jump-to-bottom button mark unseen content. | `observed` (`/app-preview` scenario) |
| Composer and header | The composer is a pill whose placeholder names the recipient ("Message Atlas"), with a "+" menu (attach, skill, side question, voice), a context meter and a stop button while the agent works. The header shows a model chip with the provider and the effort; the picker names the CLI and its version. | `observed` (`/app-preview` composer, model picker); `docs` (guides/openbot-101) |
| Context meter | "Context 21% full · 41.2K of 200K tokens", with a breakdown into system prompt, memory files, tools, skills, tool results, messages and free space. It adds "Context compacts automatically at 90%", Compact now and New chat. | `observed` (`/app-preview` context meter) |
| Agent settings | A side panel opened from the header: avatar, Name, Title, Description, then groups Brain (model, backup models, chat colour), Knows (instructions, memories, skills, files, tables), Does (routines, usage, publish) and Rules (permissions, folders). Each row shows its current value. | `observed` (`/app-preview` agent settings) |
| Message actions | A hover toolbar has React, Reply and More. More holds Reply, Copy, Send to channel, Pin, Branch from here, Mark unread, and Delete (separated, in red). Branching does not roll back workspace files (0.57.0). | `observed` (`/app-preview` message menu); `docs` (changelog 0.57.0) |
| System lines | Handoffs and provider switches are muted centred lines ("Ada gave the task to Linus", "Ada now uses Claude Code"). Agents accept work with a scope and a time. These are marketing illustrations, not the live app. | `observed` (home page cards) |
| Deliverables | A final answer has a title, a one-line status, a table, a diagram block with Preview and Code, an explicit "Open item" naming what the user must approve, and file chips. | `observed` (`/app-preview` scenario end) |
| Search, usage, settings | The palette has scope chips (agents, channels, messages, files, routines), grouped results and a key legend. Usage leads with a cost total, then gives per-provider, per-day and per-agent breakdowns and plan-limit gauges. Each setting carries one sentence on its effect and scope ("This choice is only for you and applies on all your devices."). | `observed` (`/app-preview` search, usage, settings) |
| Copy and empty states | The copy is short, concrete and second person, with no exclamation marks; it prefers numbers to adjectives. FAQ answers start with Yes or No and state limits ("Give them only tasks you trust, and keep backups."). Guides include a section on what the product does not fix. Empty states teach the next action ("Start with a trigger"; "Right-click a message and select Pin to keep it here"). | `observed`; `docs` (home FAQ; guides/ai-workspace-vs-chat) |

**Visual system** (computed styles of the home page and the preview)

| Area | Finding | Evidence |
|---|---|---|
| Theme | Dark only on the web. The page declares `color-scheme: dark`, and the body stays `#1a1a1a` under both emulated schemes. The app's Appearance settings were not opened. | `observed` |
| Tokens | About 294 role-named custom properties (930 on the app page): a neutral surface ladder from `#0d0d0d` to `#2a2a2a`, four text levels (muted 5.96:1, dim 3.22:1), near-invisible borders (`#ffffff09`), one blue accent, and semantic tones with soft, text, border and focus variants. Component layers sit on top (message, composer, sidebar, trace, toast). Nested radii are computed, for example `calc(22px - 12px - 1px)`. | `observed` |
| Type | One variable sans with a metric-matched fallback. Weights are 400, 500 and 600, with a single 800. Monospace appears only in eyebrows and code labels. Sizes are role-named: 12 to 18 px for UI, 24 and 32 px for display. | `observed` |
| Shape and depth | A radius scale from 4 px up to a pill; a 4 px spacing base, with app gaps mostly 4 to 8 px. Elevation comes from 1 px inset hairlines and lighter surfaces. Shadows appear only on overlays, which also get a backdrop blur. | `observed` |
| Density | The chrome is compact (52 px rail, rows of about 66 px, 12 to 14 px UI text) and the conversation is airy. Grouping comes from tone and spacing, and the app has almost no card inside a card. | `observed` |
| Motion | Durations of 0.1 to 0.24 s (toasts 0.34 s in, 0.22 s out), a 0 s hover, and one ease-out curve; disclosures animate their grid rows. Reduced motion is designed per component: the app CSS has 133 reduced-motion blocks, reveals are forced visible, marquees become static rows and spinners slow down. Under `reduce`, 0 animations run (6 without it). | `observed` |
| Focus and keyboard | In the app, one focus token (a 1 px `#979797` ring through `:focus-visible`, 5.96:1). On the marketing site, a 34 % blue ring at about 1.52:1, below the 3:1 target. There is no skip link. List rows carry descriptive accessible names, and the sidebar resize handle is a focusable separator with value attributes. | `observed` |
| Decoration | The home page draws two WebGL canvases continuously, plus shader thumbnails; headless capture stalled until `requestAnimationFrame` was frozen. Pastel cards appear only on marketing pages. Agents add emoji reactions in the app. | `observed` |
| Cue attributes | Nearly every control carries `data-cuelume-*` intent attributes (tap, open, navigate). What they trigger was not checked. | `unverified` |

Gaps in the sources: the signed-in app, first-run flow, errors and real approval prompts were not seen.
The preview was used at 1440x900 only, and at 390x844 only inside the home page capture. Screen-reader
output and focus trapping in dialogs were not tested. The individual "Message from …" rows of the
agent-to-agent log were not opened.

## 4. Cross-product comparison

Dots column is unverified throughout. OpenBot column is `docs` unless marked `observed`. A dash (—)
means the research pass did not cover that concern for that product; it does not mean the product lacks it.

| Concern | OpenClaw | Hermes | Grok Bot | Dots (unverified) | Frameworks (CrewAI, LangGraph, Agents SDK) | OpenBot |
|---|---|---|---|---|---|---|
| Agent config split | Workspace / agentDir / session store | Context files + config | Role, memory, routines per Bot; skills account-level (`secondary`) | Identity + responsibility in conversation | Role/goal/backstory (CrewAI); assistants as versioned config (LangGraph) | Identity + `AGENTS.md` + workspace + private provider session; settings grouped Brain / Knows / Does / Rules (`observed`) |
| Unrouted input | Fallback owner or undispatched | Default deny, pairing code | Bots decide without @mention | One dot across channels | n/a | In a channel, greetings and unclear messages go to the lead |
| Delegation bounds | Own session, no session/message tools | Depth 1, 10 concurrent, over-cap is error, capability subset | Single owner per stage | Pause does not cascade | `allow_delegation=False` default (CrewAI) | One task owner; at most 2 member-to-member questions per request; a waiting request says why it waits |
| Approval verbs | Allow once / always / deny | Once / session / always / deny | Allow once / always / deny | Four rule levels | approve / reject / always_* (Agents SDK) | Allow / Deny; "Always allow" moves the whole agent to Full access |
| Approval timeout | `askFallback` deny | 300 s deny | Chat waits; background 30 min | n/a | Durable paused state | — |
| Policy layering | Per-agent gate only restricts | Hardline blocklist over YOLO | Team rules always apply; personal only tighten; Ask first wins | Rules cannot override safety | Guardrails fail fast | One level per agent, Full access the stated default; always-ask carve-outs for sending, paying and screen capture |
| Skill install trust | VirusTotal verdict, daily rescan, install policy hook | Trust tiers, no `--force` on dangerous, lock.json | Teach a task -> review (`secondary`) | n/a | n/a | Marketplace review with Verified and Public views; GitHub skills pinned to the commit read |
| Skill lifecycle | Precedence, eligibility gates | Stale/archive, pin/lock, ledger rollback | n/a | n/a | n/a | Revisions keep versions; installed copies do not auto-update |
| Memory core | `MEMORY.md` with bootstrap budget | 2,200 / 1,375 char hard caps, frozen snapshot | Per Bot | Learned notes, not inspectable | n/a | Per agent and per channel; context meter by category (`observed`) |
| Learning curation | `DREAMS.md` review | write_approval queues, `/journey` | Review learnings (Suggested -> approve) | None reported | Review-and-edit interrupts (LangGraph) | Agent edits its own instructions at once, with View and Undo |
| Monitoring | Subagents panel, collapsed tool bursts, Changes view | Status per child, stall monitor | Admin analytics | Activity / Scheduled / Computers | Graph vs chat view, time travel, trace -> dataset | Tasks page (Needs you / Working / Waiting); trace waterfall from the turn footer (`observed`) |
| Turn shown in the chat | Completed turns collapse ("Worked for 2m 3s"); tool calls share one log | — | — | — (Activity sits on the profile) | Chat mode vs graph mode (LangGraph) | One-line rows for plan, child runs, agent messages, and a footer with steps, memory writes and duration (`observed`) |
| What waits for the user | Approvals forwarded to chat with reaction shortcuts | — | "Needs approval" cards for outbound drafts | Activity lists tasks waiting on a decision, sign-in, connection or approval | `RunResult.interruptions` (Agents SDK) | "Needs you" group at the top of the list; one card design for every wait |
| Provider failover | — | — | — | — | — | Ordered backup models, ask first by default, a note in the chat at each switch, no re-run after a tool |

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

Checked at commit `eca031f` for the OpenBot mapping (section 3.8):

| Area | What exists | Location | Evidence |
|---|---|---|---|
| Sessions rail | Two fixed sections, Rooms and Conversations, sorted by recency. Session rows show a generic chat icon, not the agent. Rows have `aria-current` but no summary label. | `apps/web/src/components/sessions/rail/session-rail.tsx`, `session-row.tsx` | `inv` |
| Composer | Generic placeholder "Send a message…". The toolbar's model label comes from the last message that names a model, not from the agent's configuration. | `apps/web/src/components/sessions/chat/composer/chat-composer.tsx`, `apps/web/src/components/features/sessions/sessions-page-client.tsx` (`modelLabel`) | `inv` |
| Turn in the chat | `ToolCallCard` shows status and duration, and expands to task, tools, cost, model and attempts. `ReasoningBlock` collapses with its duration. Child runs and warnings reach execution detail only, not the chat's `linked_execution` summary. | `apps/web/src/components/sessions/chat/tool-call-card.tsx`, `assistant-message.tsx`; `koda/control_plane/dashboard_service.py` | `inv` |
| Approvals in the chat | `ApprovalPrompt` renders inline with approve, edit, respond and reject. The broker accepts a `respond` decision, which requires response text. A resolved prompt disappears from the thread and leaves no receipt. | `apps/web/src/components/sessions/chat/approval-prompt.tsx`, `assistant-message.tsx`; `koda/services/approval_broker.py` | `inv` |
| Pending approvals | Listed per agent at `/agents/{agent_id}/approvals`; each item carries `agent_id` and `session_id`. The command palette asks only for the first agent in the catalog. | `apps/web/src/hooks/use-command-catalog.ts`, `apps/web/src/components/command-bar/command-bar-modal.tsx` | `inv` |
| Provider fallback | The chain is the primary provider, then the configured `PROVIDER_FALLBACK_ORDER` (empty unless set), filtered by eligibility. A switch is recorded only as the execution warning `provider fallback: <a> -> <b>`. | `koda/services/llm_runner.py` (`get_provider_fallback_chain`), `koda/services/queue_manager.py` | `inv` |
| Room system events | Routing and handoff events are posted as `system_event` messages whose content is a raw tag (`[routing_decision] …`, `[handoff_event] …`); the room shows them muted. | `koda/squads/dispatch.py`, `apps/web/src/components/sessions/chat/room-chat-pane.tsx` | `inv` |
| Context accounting | Context governance estimates included, dropped and review-required tokens per turn. The composer shows none of it. | `koda/services/context_governance.py` | `inv` |
| Memory-write counts | The queue counts memory writes as a quality counter only for denied child-run writes; no per-turn count reaches the chat. | `koda/services/queue_manager.py` (`record_memory_quality_counter`) | `inv` (grep) |

## 6. Design principles for Koda

Each principle lists its basis, what Koda has today (from section 5), and the gap. Gaps are proposals
and have not been scoped or accepted.

P21 to P28 were added from the OpenBot pass. Each sits in the section of its area, so the numbers are
not in page order. Where OpenBot only sharpens an older principle, that principle gained an OpenBot
item in its Basis line.

### 6.1 Agents (identity and configuration)

**P1. Three edited layers per agent.** Identity (name, @handle, avatar, voice), Operating contract
(rules compiled into the runtime prompt contract), Access (provider/model, tools, secrets, skills,
sandbox). Child runs inherit the operating contract even when they skip the persona. Two agents never
share credential or session state.
The agent's name and role appear wherever the agent does (list rows, chat header, search), and its
settings open from the chat header, grouped by what the operator is deciding: who it is, what it
knows, what it can do, and its rules.
- Basis: OpenClaw workspace / agentDir / session split and "never reuse agentDir" (`docs`); Grok Bot roles and memory per Bot (`docs`); OpenBot identity (name, title, description that teammates read to route work) shown in every list row and header, and settings grouped Brain / Knows / Does / Rules in a side panel opened from the header (`docs`, `observed`).
- Koda today: control-plane agent documents compile into the runtime prompt contract (`claimed`, CLAUDE.md core invariant); draft and published snapshots exist (`inv`); squad routing reads each agent's mission profile (`koda/squads/capabilities.py`, `inv`); session rows show a generic icon (`inv`), and no link to the agent's settings was found in the chat header (`inv`, grep).
- Gap: whether the agent editor separates these three layers, and whether child runs carry the operating contract, was not checked. The agent's identity is missing from session rows and the chat header.

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
A handoff is a readable message that says who took the work and why. While the owner waits on
teammates, a waiting block lists each one as asked, working, replied or failed, and a request that
cannot start says what it waits for (a limit, a busy agent, a paused thread).
- Basis: Grok Bot 2-6 Bot groups and "ask for a single owner at each stage" (`docs`); OpenBot one task owner per channel, handover as a message, "Waiting for replies" block, and stated waiting reasons (`docs`).
- Koda today: mentions, reply obligations and Squad Room transcript exist (`inv`); handoff and routing events reach the room as raw tags (`inv`, section 5).
- Gap: owner chip, persistent obligation display and cost hint not checked; readable handoff lines and waiting reasons.

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
to child runs. In the chat, the parent's turn carries one collapsed row ("2 child runs · 2 done · 3s")
that opens to one line per child (goal, outcome, duration) and links to the panel.
- Basis: OpenClaw Subagents panel (`docs`); Dots Pause not cascading (`unverified`); OpenBot "Ran 2 subagents · 2 done · 3s" row with one result card per child (`observed`) and "Waiting for sub-tasks" rows with Stop, then Continue, Reassign or Cancel (`docs`).
- Koda today: child runs appear in RunGraph panels, runtime task room and execution detail (`inv`), not in the chat thread (`inv`, section 5).
- Gap: Running/Finished split, per-row Stop and cascade wording not checked; the in-chat child-run row.

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
are told when memory changes take effect. The composer shows how full the turn's context is, by
category (instructions, memory, tools, tool results, messages), with the compact and new-thread
actions next to it.
- Basis: Hermes hard caps and frozen per-session snapshot (`docs`); OpenClaw `MEMORY.md` bootstrap budget (`docs`); OpenBot context meter with a per-category breakdown, automatic compaction at 90 %, Compact now and New chat (`observed`).
- Koda today: namespaced memory with recall explanations (`inv` + `claimed`); no budget setting found in `koda/memory/config.py` (`inv`, grep); context governance already estimates tokens per turn, and `/summarize` and `/clear-thread` exist, but the composer shows neither (`inv`, section 5).
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
purge what was derived from it. A turn that wrote memory says so in the chat ("Memory: 1 saved") and
links to the item, so a wrong memory can be corrected while the context is fresh.
- Basis: avoids the reported Dots anti-pattern (`unverified`); OpenBot per-turn "Memory: 1 saved" in the turn footer (`observed`).
- Koda today: provenance, drop reasons and utility feedback exist (`claimed`); no per-turn memory-write count reaches the chat (`inv`, section 5).
- Gap: per-item edit/delete and purge-on-revoke not checked; a per-turn write record is needed before a receipt can be shown.

### 6.7 Governance and approvals

**P15. Standard approval verbs everywhere, narrow "Always", fail closed.** Dashboard and Telegram use
the same verbs: Allow once / Allow for this session / Always allow (visible, revocable rule) / Deny with
reason. "Always" binds to a scope the card displays (exact argv and cwd, or tool and argument pattern),
and never widens to a whole agent or permission level. Timeout or no reachable UI means deny.
Background approvals expire. In groups only the requester or listed approvers can answer.
- Basis: OpenClaw argv/cwd binding and `askFallback` deny (`docs`); Hermes 300 s deny and approvers list (`docs`); Grok 30 min background expiry and requester-only answers (`docs`); OpenBot as the counterexample, where "Always allow" moves the whole agent to Full access (`docs`, changelog 0.43.0).
- Koda today: approve once / approve scope / deny; 300 s timeout removes pending ops; scoped grants with expiry and use count; optional `reasons` on broker decisions (`inv`).
- Gap: no session-scoped verb; whether the card shows the grant scope, and who may answer in groups, was not checked.

**P16. Policy resolves toward strictness.** Workspace rules always apply; agent and personal rules can
only tighten; "Ask first" beats "Allow automatically". A hardline blocklist no mode can override.
Outbound communication defaults to draft-for-review. An optional AI-reviewer tier can allow, deny with
reason, or escalate; every decision goes to audit and RunGraph.
- Basis: Grok layered rules and Auto Review (`docs`); Hermes hardline blocklist and smart mode (`docs`); OpenClaw auto mode (`docs`); OpenBot always-ask carve-outs that hold even under full access (draft before sending, read-back before paying, each screen capture) (`docs`), while its default posture is the opposite of this principle (section 8).
- Koda today: tool policy, command blocking and audit exist (`claimed`; CLAUDE.md safe editing rules).
- Gap: rule-layering semantics, draft-by-default outbound and AI-reviewer tier not checked.

**P17. Say that approving or stopping does not undo work.** Stop and Cancel dialogs list side effects
already executed (from RunGraph) and state whether child runs and scheduled routines are affected.
- Basis: Grok "does not reverse work already completed" (`docs`); OpenBot "Branch from here" states that workspace files are not rolled back (`docs`, changelog 0.57.0).
- Koda today: RunGraph records lifecycle evidence (`inv`).
- Gap: dialog content not checked.

**P21. Questions and approvals share one waiting state, not one card.** An agent's question to the
operator (choose options, write an answer, or skip) and an approval of an action are different cards
with different verbs. Both show that the agent is waiting for the operator, both put the session in the
Needs-you group (P19), and both collapse to a one-line receipt once answered: what was chosen or
decided, by whom and when. Approval cards keep the P15 verbs and scope. A question never grants a
permission.
- Basis: OpenBot one card design for every wait (changelog 0.66.0), plain questions moved out of approval button cards (0.68.0) (`docs`), and the question card that collapses to "Answers sent" (`observed`).
- Koda today: `ApprovalPrompt` offers approve, edit, respond and reject; the broker's `respond` needs response text; a resolved prompt leaves no receipt in the thread (`inv`, section 5). The generative `ui_choice` block has no backend producer (FEATURE_MATRIX F-CNV-07).
- Gap: receipts after a decision. A structured question card has no requirement yet; if one comes, it is built on the broker's `respond` path, not on `ui_choice`.

**P22. Provider failover is visible and never repeats side effects.** When a turn moves to another
provider, the thread shows one muted line naming both providers and the reason class, and the
execution record says the same. A turn that already ran a write tool is never re-run on the next
provider: it continues from its tool results or fails visibly. Each agent's order is explicit. Whether
a switch asks the operator first is an operator decision (section 9).
- Basis: OpenBot backup models with "Ask before switching" on by default, a note in the chat that names the model that failed, return to the main model, and no re-run of a turn that used a tool (`docs`, changelog 0.40.0, 0.48.2, 0.68.0, 0.70.0; `observed`, Backup models screen).
- Koda today: the fallback chain comes from the primary provider and the configured order, and a switch is recorded only as an execution warning (`inv`, section 5); tool replay on retry is a known defect (D-051).
- Gap: the thread note; the ask-first option.

### 6.8 Monitoring

**P18. Agent profile organized around activity.** Order: Needs you (blocked on approval, credential,
decision, pairing), Running, Scheduled, Recent results and files. Transcripts collapse tool bursts into
one expandable line and keep a Changes view for diffs. A task toggles between a Transcript view and a
RunGraph view with per-node state, replay and fork from a checkpoint.
- Basis: Dots profile (`unverified`); OpenClaw collapsed turns and Changes view (`docs`); LangGraph graph vs chat mode and time travel (`docs`); OpenBot Tasks page grouped into Needs you, Working, Waiting and Archived (`docs`, changelog 0.55.0).
- Koda today: `/runtime/[agentId]`, RunGraph panels, run-graph replay doc (`inv`).
- Gap: Needs-you ordering, tool-burst collapse and fork-from-checkpoint not checked.

**P23. Every turn leaves a receipt in the thread.** A finished agent turn collapses to one-line rows
that open in place: tool steps with status and duration, child runs with a done count (P8),
agent-to-agent messages, memory writes (P14), and a provider switch (P22). The last row gives total
duration and cost and opens the turn's RunGraph on a time axis, with the slowest step marked. Rows stay
collapsed by default.
- Basis: OpenBot turn rows ("Ran 2 subagents · 2 done · 3s", "3 steps · Memory: 1 saved · 43s") and the trace waterfall opened from the footer (`observed`); OpenClaw "Worked for 2m 3s" (`docs`).
- Koda today: the `ToolCallCard` row (status, duration; expands to cost, model and attempts) and `ReasoningBlock` (`inv`); `RunGraphViewer` is a depth-indented tree with durations and no time axis (`apps/web/src/components/runtime/run-graph-panels.tsx`, `inv`).
- Gap: child-run, memory and provider-switch rows in the chat; a time-axis view of RunGraph data.

### 6.9 Information architecture and density

**P19. Three cross-linked planes and a global Needs-you count.** Work (sessions, Squad Rooms, channels),
Configuration (control plane), Evidence (runtime, RunGraph, evals, audit). Every evidence row links to
the config version and rule that produced it. A sidebar count combines approvals, pending learnings,
pairing requests and quarantined skills. List pages (sessions, routines, usage, approvals) support
all-agents and single-agent scope. In the conversation list, the same sources form a "Needs you" group
at the top: each row says what it waits for (approval, answer, reply) and previews the question, and the
group empties itself when nothing waits.
- Basis: OpenClaw all-agent views (`docs`); Grok Manage Bots analytics (`docs`); OpenBot "Needs you" group with a count, the wait kind and the question as the row preview (`docs`, changelog 0.25.0; `observed`).
- Koda today: routes for each plane exist (`inv`); no Needs-you inbox found (`inv`, grep); pending approvals carry `agent_id` and `session_id`, but the palette asks for the first agent only, and the rail has only Rooms and Conversations (`inv`, section 5).
- Gap: global inbox, evidence-to-config links, scope toggle on list pages.

**P20. Row-first, low-density presentation.** Row lists with hair dividers, status dots (pulse when
running), compact timestamps (4m, 2h); no card per agent or skill. State, budgets and counts inline
(memory meter, skill trust tier and last used, approval scope and expiry). Detail on demand through
progressive disclosure and drawers rather than modals in full-bleed routes.
- Basis: Hermes L0/L1/L2 skill disclosure (`docs`); OpenBot compact chrome around an airy conversation, grouping by surface tone, and almost no card inside a card (`observed`).
- Koda today: `apps/web/CLAUDE.md` already requires low density, no nested cards and no decorative noise (`inv`, headings and UX sections skimmed).
- Gap: none in principle; apply when building P2, P9, P11, P12, P15 surfaces.

### 6.10 Experience and visual direction

This direction comes from the OpenBot visual study (section 3.8) and is expressed only through Koda's
own design system ([`apps/web/CLAUDE.md`](../../apps/web/CLAUDE.md)): dark-first with light and System
themes, the warm `--accent`, Koda's radius, motion and glass-overlay rules, and Lucide icons. Each
principle says what to do, never how OpenBot looks. Nothing here adopts OpenBot's colours, fonts,
shapes, avatars, wording or proportions.

**P24. The conversation says who, which model and what state.** The composer names its recipient (the
agent, or the room). The chat shows the agent's configured provider, model and effort, read from its
published configuration rather than from the last reply. When the agent is working, waiting for the
operator or paused, the composer says so and offers the matching action: stop, go to the waiting card,
or activate. A message that waits behind a running turn stays visible with the reason it waits.
- Basis: OpenBot composer placeholder that names the recipient, header model chip with effort, and composer states (`observed`); the queue that shows why a message waits (`docs`, changelog 0.10.0).
- Koda today: generic placeholder; the model label comes from the last message; a send to a paused agent returns 400 (D-206); pending messages show optimistically with retry, but the backend queue is not shown (`inv`, section 5).
- Gap: recipient naming and the configured-model label (small); the waiting reason for queued messages.

**P25. System events read as sentences.** Handoffs, routing decisions, provider switches, and paused
or limited threads appear as short muted lines. Each line is built from the event's metadata and
translated, for example "Ada handed the task to Linus: needs a code review". Raw tags and ids never
appear. A line that reports a limit names it: depth, hop count or budget.
- Basis: OpenBot handoff and provider-switch lines (`observed`, home page illustrations) and stated waiting reasons (`docs`, changelog 0.71.0).
- Koda today: rooms show raw `[routing_decision]` and `[handoff_event]` text, muted (`inv`, section 5).
- Gap: render from metadata with i18n keys; the stored message content can stay as it is.

**P26. Calm surfaces in Koda's own tokens.**
- Group by surface tone and spacing, with hair dividers instead of borders and no card inside a card (already Koda's rule).
- One accent, used for the single call to action and for focus; state uses the tone tokens. The operator's own messages sit on a neutral raised surface, never on the accent (Koda's `UserMessage` already uses `--panel-soft`).
- Three font weights: 400, 500 and 600, with display text at 500. Monospace only for eyebrows, timestamps, code and tabular numbers.
- Compact chrome (rail, list rows, 12 to 14 px UI text) around an airy conversation column whose bubbles size to their content.
- Role-named tokens. A nested radius is derived from its container (outer radius minus the inset) instead of hard-coded.
- Overlays keep Koda's four glass classes; elsewhere, elevation comes from tone and hairlines rather than shadows.
- Basis: OpenBot neutral surface ladder, near-invisible borders, three-weight type, computed nested radii, and the density split between chrome and conversation (`observed`).
- Koda today: palette, radius, glass and density rules exist in `apps/web/CLAUDE.md`; undefined tokens, raw values and arbitrary font sizes remain (TD-133; M8-E5-T3, M8-E5-T10) (`inv`).
- Gap: token hygiene and a weight scale; no new token layer.

**P27. Motion and focus are designed per component.** Koda keeps its short fixed durations (120, 200
and 320 ms) and one ease-out curve (`--ease-out-quart`). Each animated component has a designed
reduced-motion state: a status pulse becomes a static dot, typing dots stop, overlays fade without
moving, and nothing stays hidden behind an unfinished reveal. One focus-ring token is applied through
`:focus-visible`, with at least 3:1 contrast on every surface it can sit on. List rows have an
accessible name that summarises them (agent, state, last activity). The palette shows its key legend.
- Basis: OpenBot reduced motion handled per component, with 0 running animations under `reduce`; its app focus token at 5.96:1, against a marketing-site ring at about 1.52:1; descriptive row labels; the palette key legend (`observed`).
- Koda today: 9 reduced-motion blocks in `globals.css`, the global rule among them; global resets remove focus rings (D-114, M8-E1-T1); rows have `aria-current` but no summary label (`inv`).
- Gap: per-component fallbacks and a browser check that proves them; row names.

**P28. Copy states the effect, the scope and the next step.** Every setting has one sentence that says
what it changes and for whom. An empty state teaches the next action in one sentence (Koda: never a
card). Messages are short and concrete, prefer numbers to adjectives, use no exclamation marks, and
state limits plainly ("Not available yet"; "Stopping does not undo work already done"). This principle
covers interface copy only. Agent-facing PT-BR prompt text is not translated or rewritten (CLAUDE.md).
- Basis: OpenBot settings descriptions, empty states that teach, and an FAQ that states limits (`observed`, `docs`).
- Koda today: approval modes and system settings carry one-line descriptions; raw i18n keys and PT-BR strings leak into other locales (D-127, J-09); "Not available yet" labels are planned in M6 (`inv`, `claimed`).
- Gap: covered by M8-E3-T2 and the M6 labelling tasks; apply when writing new surfaces.

**Not adopted from OpenBot.** Each item conflicts with Koda's identity, governance or MISSION §12.

| Pattern | Why Koda does not adopt it |
|---|---|
| Dark-only theme | Koda is dark-first and keeps light and System (`apps/web/CLAUDE.md`; M8-E2-T3). |
| Blue accent, saturated user bubble, pastel category cards, generated plush avatars | Koda's accent and identity are its own. The agent glyph follows M4-E3-T3. |
| Emoji reactions from agents; decorative WebGL canvases | The design guide forbids emoji-heavy UI and decorative illustration; Koda is removing its own WebGL orb (M4-E3-T3). |
| Pill-shaped controls everywhere; instant (0 s) hover | A matter of taste, not a gap. Koda keeps its radius tokens and 120 ms colour transitions. |
| Intent cue attributes (`data-cuelume-*`) | Their purpose is unverified, and no requirement asks for them. |
| "What's new" tips in a menu | The design guide forbids tip cards and promo callouts; `CHANGELOG.md` covers releases. |
| Window tabs, back/forward history, chat folders | No requirement for a single-owner console; M8-E2-T5 records keep or drop. |
| Full access by default; "Always allow" that promotes an agent | See section 8. Koda is governed by default (ADR-002). |

## 7. Principle-to-surface map

| Principle | Feature area | Backend touchpoints | Web touchpoints |
|---|---|---|---|
| P1-P3 | Agents | `koda/control_plane/manager.py`, `koda/control_plane/operator_auth.py`, runtime prompt contract | `/control-plane/agents`, `components/control-plane/editor`, `components/sessions/chat/chat-header.tsx`, `components/sessions/rail/session-row.tsx` |
| P4 | Channels | `koda/channels/gateway.py` | Channel gateway UI |
| P5-P6 | Squads | `koda/squads/coordinator_engine.py`, `mentions.py`, `replies.py`, `synthesis_gate.py` | `components/sessions/`, `squad-spec-editor.tsx` |
| P7-P8 | Delegation | `koda/services/child_runs.py`, `koda/services/queue_manager.py`, `koda/control_plane/dashboard_service.py` (execution summary) | `components/runtime/`, `components/executions/`, `components/sessions/chat/assistant-message.tsx` |
| P9-P11 | Skills | `koda/skills/`, `koda/services/improvement_proposals.py` | Control-plane catalog |
| P12-P14 | Memory | `koda/memory/`, `koda/control_plane/dashboard_memory.py`, `koda/services/context_governance.py` | `/memory`, `/memory/review`, the composer |
| P15-P17 | Governance | `koda/utils/approval.py`, `koda/services/approval_broker.py`, `koda/control_plane/audit.py` | Approval cards, audit components |
| P18 | Monitoring | `koda/services/run_graph.py`, `koda/services/quality_cockpit.py` | `/runtime`, `/executions`, `/tasks` |
| P19-P20 | IA and density | Pending approvals (`/agents/{agent_id}/approvals`), reply obligations | App shell, sidebar, list pages, `components/sessions/rail/session-rail.tsx` |
| P21 | Questions and approvals | `koda/services/approval_broker.py` (`respond`), audit | `components/sessions/chat/approval-prompt.tsx`, `assistant-message.tsx` |
| P22 | Provider failover | `koda/services/llm_runner.py` (`get_provider_fallback_chain`), `koda/services/queue_manager.py` (fallback loop), the execution summary | `assistant-message.tsx`; the agent editor's resources tab |
| P23 | Turn receipts | `koda/control_plane/dashboard_service.py`, `koda/state/dashboard_store.py` (`linked_execution`), `koda/services/run_graph.py` | `components/sessions/chat/tool-call-card.tsx`, `assistant-message.tsx`, `components/runtime/run-graph-panels.tsx` |
| P24 | Composer and header | The agent's published snapshot (provider, model, effort) | `components/sessions/chat/composer/`, `chat-header.tsx`, `components/features/sessions/sessions-page-client.tsx` |
| P25 | System lines | `koda/squads/dispatch.py` (event metadata) | `components/sessions/chat/room-chat-pane.tsx`, i18n resources |
| P26-P28 | Visual system, motion, focus, copy | n/a | `apps/web/src/app/globals.css`, `components/ui/`, `apps/web/CLAUDE.md`, i18n resources |

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
| Agents that act without asking by default after one consent ("a product decision, not a security boundary"). This is wrong for Koda: one self-hosted install serves several agents, squads and channel users, and its approvals are the boundary the operator relies on (ADR-002, governed by default) | OpenBot README, guide and FAQ | `docs` |
| "Always allow" on one approval card that raises the whole agent to full access, instead of saving a narrow, visible rule (P15) | OpenBot changelog 0.43.0 | `docs` |
| A permission level whose name suggests confinement it does not enforce: "Workspace only" limits writes but not reads or network, and only a guide says so | OpenBot | `docs` |
| Self-edits to an agent's standing instructions applied at once, with Undo afterwards, instead of reviewed before they apply (Koda keeps review first, Q-16) | OpenBot changelog 0.57.0 | `docs` |
| Product copy that lags behaviour: the FAQ still says busy agents queue messages, but steering is the default since 0.69.0 | OpenBot | `docs` |
| A focus ring below 3:1 contrast | OpenBot marketing site (about 1.52:1) | `observed` |
| Continuously animated decorative canvases, and emoji reactions from agents in work threads | OpenBot home page and app preview | `observed` |

## 9. Caveats and open questions

1. Product facts are from a single research pass on 2026-11-14 and were not re-fetched for this document.
2. OpenAI Dots is unverified as a whole. Grok Bot items marked `secondary` or `snippet` are unverified.
3. Hermes curator archive threshold is inconsistent in its own docs (30 vs 90 days).
4. The OpenClaw Control UI page does not describe Approvals, Skills, Cron or Logs tabs; LangGraph Studio does not detail forking or state editing; CrewAI agents docs do not cover memory types or human input.
5. Koda baseline rows marked `claimed` restate README and `docs/` text. Rows marked `inv (grep)` record that a term was not found, which does not prove a feature is absent.
6. The root Obsidian vault memory was not read for this document.
7. OpenBot (section 3.8):
   - Every `observed` app item comes from the scripted `/app-preview` with sample data, explored at 1440x900 only. The signed-in app, its first-run flow, its errors and its real approval prompts were not seen.
   - The site is dark-only, so its light captures nearly duplicate the dark ones. The app's own Appearance settings were not opened.
   - Some home-page cards (handoff and provider-switch lines) are marketing illustrations, not the live app.
   - The relation between Synthetify Labs and the `nightly-labs` organisation, and the purpose of the `data-cuelume-*` attributes, were not checked.
   - The release and fix counts come from the research pass's own count of the changelog page.
   - Accessibility checks covered computed focus styles, Tab order, contrast arithmetic and reduced-motion rules only.
8. Open questions for owners:
   - Should coordination mode (P6) be an operator setting, a per-message decision as today, or both?
   - Is a Manager / Collaborator role split (P3, P13) in scope for a self-hosted single-owner product?
   - Should "Allow for this session" (P15) be added alongside the existing once / scope grants?
   - Where should memory review and improvement proposals converge (P13)?
   - Should provider failover ask the operator before switching (P22)? Today a configured fallback order switches automatically, and the turn's context goes to the next provider. Asking first would change an existing behaviour that users rely on (MISSION §13).
   - Should agents be able to ask the operator structured questions with options (P21)? No requirement exists yet.

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

OpenBot (fetched and, where marked, captured with Playwright on 2026-11-14):

- https://openbot.run/ (home and FAQ; captured)
- https://openbot.run/app-preview (interactive app preview with sample data; captured in 39 states)
- https://openbot.run/teams (captured)
- https://openbot.run/pricing (captured)
- https://openbot.run/providers (captured), plus `/providers/claude-code`, `/providers/codex`, `/providers/custom-agents`, `/providers/local-models`
- https://openbot.run/download (captured), plus `/download/ios`, `/download/android`
- https://openbot.run/compare/grok-bot (captured)
- https://openbot.run/news/channels-put-agents-in-one-room (captured)
- https://openbot.run/guides/ai-workspace-vs-chat (captured)
- https://openbot.run/guides/openbot-101
- https://openbot.run/guides/openbot-marketplace
- https://openbot.run/guides/openbot-hosted-servers
- https://openbot.run/guides/install-openbot-vps
- https://openbot.run/news/introducing-openbot
- https://openbot.run/news/one-agent-many-providers
- https://openbot.run/news/every-agent-gets-a-workspace
- https://openbot.run/news/your-work-stays-on-your-computer
- https://openbot.run/news/what-gets-redacted-before-it-leaves
- https://openbot.run/news/run-the-team-server-yourself
- https://openbot.run/marketplace/apps
- https://openbot.run/changelog (0.1.0 to 0.71.0)
- https://github.com/nightly-labs/openbot (README: architecture, security warning, licence)
