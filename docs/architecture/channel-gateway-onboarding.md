# Channel Gateway And Onboarding Readiness

Phase 6 closes KG-12 and KG-13 with two versioned contracts:
`channel_gateway.v1` for inbound channel identity and `onboarding_readiness.v1`
for first-run UX/DX readiness. Telegram is the production pilot. Slack and
Discord are now contract-gated through the same `ChannelManager` path; live
credentialed E2E remains required before they are called production-ready.

## Goals

- Deny or queue unknown channel senders before task enqueue.
- Keep legacy Telegram `ALLOWED_USER_IDS` compatible while making an empty
  allowlist fail closed.
- Let operators create short-lived pairing codes and approve, block, or revoke
  identities from the dashboard.
- Surface onboarding readiness as backend-owned status: provider, runtime,
  storage, channel, first task, first trace, and release quality.
- Emit audit, metrics, and RunGraph-compatible event names for every public
  state transition.

## `channel_gateway.v1`

Identity scope is `(agent_id, channel_type, channel_id, user_id)`. The stable
`identity_id` is derived from those fields and never from display names.

Core identity record:

```json
{
  "schema_version": "channel_gateway.v1",
  "identity_id": "chgid_...",
  "agent_id": "ATLAS",
  "channel_type": "telegram",
  "channel_id": "-10042",
  "user_id": "12345",
  "display_name": "Operator",
  "is_group": false,
  "status": "pending | paired | allowed | blocked | revoked",
  "scopes": ["message"],
  "source": "channel_gateway | operator_approval | operator_block | operator_revoke | pairing_code | legacy_allowed_user_ids",
  "allowed_by": "operator-id",
  "blocked_by": "",
  "revoked_by": "",
  "created_at": "iso-8601",
  "updated_at": "iso-8601",
  "last_seen_at": "iso-8601",
  "paired_at": "iso-8601",
  "metadata": {}
}
```

Unknown sender queue records include `message_id`, redacted `message_preview`,
`first_seen_at`, and `last_seen_at`. Pairing code records include
`pairing_code_id`, `channel_type`, `code`, `status`, `created_by`,
`created_at`, `expires_at`, and `used_at`.

Decision envelope:

```json
{
  "schema_version": "channel_gateway.v1",
  "decision": "allow | queue_for_pairing | deny | paired",
  "allowed": false,
  "identity_id": "chgid_...",
  "channel_type": "telegram",
  "channel_id": "-10042",
  "user_id": "12345",
  "status": "pending",
  "reason_code": "channel.identity_unknown",
  "error": {
    "code": "channel.identity_unknown",
    "category": "permission",
    "message": "This channel identity has not been approved for the agent.",
    "retryable": true,
    "user_action": "Open the dashboard channel gateway and approve or block the sender.",
    "detail_ref": "docs/operations/channel-gateway-runbook.md"
  }
}
```

Required errors:

- `channel.identity_unknown`: sender is queued for review; no task is enqueued.
- `channel.pairing_required`: channel can receive messages but no approved
  sender exists.
- `channel.policy_denied`: blocked or revoked identity tried to route.
- `channel.pairing_locked`: sender made too many failed pairing attempts and
  is locked out of pairing for a while; it stays queued for review.
- `channel.gateway_unavailable`: the sender's identity could not be read from
  the primary backend; the message is denied and nothing is written.
- `channel.relay_failed`: approval relay or outbound channel response failed.

## API

All mutating routes require an operator session.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/control-plane/agents/{agent_id}/channels/gateway` | Current gateway state, identities, pending senders, pairing codes, and summary. |
| `POST` | `/api/control-plane/agents/{agent_id}/channels/gateway/pairing-codes` | Create a short-lived code for Telegram pairing. |
| `GET` | `/api/control-plane/agents/{agent_id}/channels/gateway/unknown-senders` | List senders denied before enqueue. |
| `POST` | `/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}/approve` | Allow future messages from this identity. |
| `POST` | `/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}/block` | Deny future messages from this identity. |
| `DELETE` | `/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}` | Revoke an existing identity. |

## Routing Rules

- Channel gateway evaluation happens before Telegram messages reach the queue.
- Empty `ALLOWED_USER_IDS` means no legacy sender is allowed.
- If `ALLOWED_USER_IDS` contains a Telegram user id, that sender is still
  allowed for backward compatibility and is mirrored into the gateway as source
  `legacy_allowed_user_ids`.
- Blocked or revoked records override legacy allowlist compatibility.
- A pairing code message allows the identity but does not enqueue that code
  text as a task. The user must send the task again after pairing.
- A code is 8 letters and digits. A pairing attempt is a message that is
  exactly one token of that shape, or `/start CODE`; one message tries one
  code, and other messages are not attempts. Codes expire after 15 minutes and
  work once. A sender (agent, channel type and user id, so one budget across
  all its chats) gets 5 failed attempts per 15 minutes; the fifth locks it out
  of pairing for 15 minutes (`channel.pairing_locked`, event
  `pairing_locked_out`). The counters live in the agent process.
- Unknown senders create a pending identity and create or update an
  unknown-sender queue item, then return a deny response. Message handling
  writes an identity only when its status changes, so it never overwrites an
  approval, block or revoke written by the control plane. It re-reads the
  identity before updating the queue item and skips it once the sender is no
  longer pending, so a queue item the control plane resolved stays resolved.
- If the identity read fails, the message is denied with
  `channel.gateway_unavailable` (event `identity_read_failed`) and nothing is
  written: a failed read is never treated as an unknown sender.
- Slack and Discord adapters must only normalize `IncomingMessage` payloads.
  The central `ChannelManager` calls `channel_gateway.v1` and invokes the
  runtime callback only when the decision is allowed.
- Gateway errors fail closed and do not call the adapter callback.

## Persistence

Migration `040_channel_gateway_onboarding_v1` adds:

- `channel_gateway_identities`
- `channel_unknown_senders`
- `channel_pairing_codes`
- `channel_gateway_events`
- `onboarding_readiness_runs`

These tables are the only gateway store; there is no file fallback. Without
Postgres nothing is stored: legacy `ALLOWED_USER_IDS` senders are still
allowed, and every other sender is denied.

Rollback is additive: export records if needed, then ignore or drop these
tables. Existing Telegram config, legacy allowlist values, and tasks continue
to work, with the fail-closed empty allowlist semantics preserved.

## Observability

Gateway event names:

- `message_received`
- `unknown_sender_queued`
- `pairing_created`
- `identity_paired`
- `pairing_locked_out`
- `identity_allowed`
- `identity_blocked`
- `identity_revoked`
- `policy_denied`
- `approval_relay`
- `relay_failed`

Events are emitted through audit as `channel_gateway.<event>` and metrics as
`koda_channel_gateway_events_total{agent_id,event,status}`. These event names
are RunGraph-compatible runtime events until a dedicated channel node type is
introduced.

## Release Smoke

`channel_gateway_smoke.v1` is the offline release gate for KAT-060:

```bash
uv run python scripts/channel_gateway_smoke.py \
  --input tests/fixtures/channels/channel_gateway_smoke.v1.json
```

The smoke proves unknown sender deny-before-route, pairing-code discard,
operator approve, block, revoke, group mention routing, ignored unmentioned
group traffic, room/squad metadata and reply-channel `reply_to_id` preservation.
Slack and Discord contract tests live in `tests/test_channels/test_manager.py`
and use SDK-free fake adapters so they cannot bypass the gateway.

## `onboarding_readiness.v1`

Readiness checks are backend-owned. The dashboard renders them but does not
invent policy or risk decisions.

```json
{
  "schema_version": "onboarding_readiness.v1",
  "status": "passed | warning | failed | pending",
  "primary_agent_id": "ATLAS",
  "generated_at": "iso-8601",
  "checks": [
    {
      "key": "provider",
      "title": "Provider",
      "status": "passed",
      "summary": "A verified provider is configured.",
      "action_label": "",
      "action_href": "",
      "metadata": {}
    }
  ],
  "summary": {
    "passed": 1,
    "warning": 0,
    "failed": 0,
    "pending": 0
  },
  "actions": []
}
```

Required check keys:

- `provider`
- `runtime`
- `storage`
- `channel`
- `first_task`
- `first_trace`
- `release_quality`

Each check is derived from live state; there are no fixed-status checks, so the
rollup can reach `passed`.

API (operator session or token required):

- `GET /api/control-plane/onboarding/readiness`
- `POST /api/control-plane/onboarding/first-task`

The first-task action sends a safe dashboard message through the normal agent
runtime path. It does not bypass queue, policy, audit, RunGraph, or release
quality gates.
