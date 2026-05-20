# Squads Overview

Squads are durable multi-agent conversations scoped to a workspace and squad.
They use Postgres-backed `SquadThread`, typed `AgentMessage` envelopes,
`SquadTask` ownership, and optional coordinator election.

Runtime safety invariants:

- Agent prompts remain isolated. Cross-agent context comes only from typed
  squad messages and the generated `<squad_context>` block.
- Thread membership is the visibility boundary. Private side-threads are
  visible only to active participants, and late joiners do not receive older
  messages in prompt/history views.
- Tasks have one active owner. Claims are atomic and preassigned tasks can only
  be claimed by the assignee unless the coordinator explicitly overrides.
- Postgres is required for durable squads. The memory bus remains for local
  development and legacy inter-agent tools.

Enable with:

```bash
SQUADS_ENABLED=true
INTER_AGENT_ENABLED=true
INTER_AGENT_BUS_BACKEND=postgres
POSTGRES_URL=postgres://...
```

The Web composer writes `user_input` rows and dispatches routed messages to
the selected agent inboxes. Telegram supergroups map one squad to a forum
enabled chat; each forum topic maps to one `SquadThread`.
