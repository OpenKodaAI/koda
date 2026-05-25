# Squads Security

`SquadAccessService` is the enforcement point for squad tools and runtime
context assembly. Handlers must call it before reading or mutating:

- `squad_threads`
- `squad_tasks`
- `squad_messages`
- `squad_artifacts`

Access is denied unless the caller is an active thread participant or the
elected coordinator for that squad. Private side-threads are visible only to
participants plus the elected coordinator; workspace operators see redacted
metadata by default. When a participant joins after messages already exist,
history and prompt context are filtered by `joined_at`.

Operator break-glass access to private content is disabled by default with
`SQUAD_OPERATOR_BREAK_GLASS_ENABLED=false`. When enabled, callers must provide
a reason and the access service emits a governance audit event.

Coordinator election validates the real AgentSpec from the control plane.
Caller-supplied tool lists are ignored.

Artifact updates require ownership and an `If-Match` style version check to
prevent concurrent overwrites.
