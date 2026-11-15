# Squads Security

`SquadAccessService` is the enforcement point for squad tools and runtime
context assembly. Handlers must call it before reading or mutating:

- `squad_threads`
- `squad_tasks`
- `squad_messages`
- `squad_artifacts`

Access is denied unless the caller is an active thread participant. The
elected coordinator is no exception: its role adds coordination actions (writing
while paused, reading history from before it joined, overriding task
assignments) only on threads it takes part in, and it never opens a thread it is
not party to. Private side-threads are visible only to their participants;
workspace operators see redacted metadata by default. When a participant joins
after messages already exist, history and prompt context are filtered by
`joined_at`.

Operator break-glass access to private content is disabled by default with
`SQUAD_OPERATOR_BREAK_GLASS_ENABLED=false`. When enabled, callers must provide
a reason and the access service writes a governance audit event first. If that
write fails, the break-glass access is refused with an error.

Coordinator election validates the real AgentSpec from the control plane.
Caller-supplied tool lists are ignored.

Squad administration is its own `squad_admin` tool category, so granting the
messaging tools (`agent_comm`) never grants it. Electing or demoting the
coordinator, binding or unbinding Telegram and router ticks need either a
workspace operator, through
`PUT`/`DELETE /api/control-plane/workspaces/{workspace_id}/squads/{squad_id}/coordinator`
for election, or the squad's current coordinator, through the agent tools. The
agent tools take no `force_replace` or `force`: a coordinator can only hand its
own seat over, and `squad_telegram_bind` runs the `/squad_bind` supergroup,
forum and admin checks against Telegram instead of trusting the caller.
Election and the coordinator's own demotion re-check, under the coordinator row
lock, that the caller still holds the seat, so a coordinator demoted or replaced
after its check changes nothing. The elected agent must belong to the squad, or
be an agent of the squad's workspace that is in no squad. `squad_router_tick`
reverts only the expired claims of the coordinator's own squad; the other router
sweeps cover every squad and run only in the background loop.

Artifact updates require ownership and an `If-Match` style version check to
prevent concurrent overwrites.
