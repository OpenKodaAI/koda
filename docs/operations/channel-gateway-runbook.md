# Channel Gateway Runbook

Use this runbook when connecting Telegram, reviewing unknown senders, rotating
allowlists, or debugging channel identity denials.

## Operating Model

Telegram messages are evaluated by the channel gateway before enqueue. Unknown,
blocked, or revoked identities do not create tasks. Approved identities keep
using the existing runtime path.

Slack and Discord adapters follow the same contract through `ChannelManager`.
The adapters normalize platform events; `ChannelManager` evaluates
`channel_gateway.v1` and only then calls the runtime callback. Adapter code must
not duplicate allow/block/revoke policy.

Legacy `ALLOWED_USER_IDS` remains supported, but an empty value is fail-closed.
It does not mean "allow everyone".

## Pair A Telegram Sender

1. Open the agent's Telegram channel card in the dashboard.
2. Confirm the bot token is connected.
3. Click **Pairing code** in the channel gateway panel.
4. Send that code to the bot from the desired Telegram account or chat.
5. Send the real task again after the bot confirms pairing.

The code message is never enqueued as a task. It only approves the identity.

## Review Unknown Senders

Unknown senders appear in the gateway panel with a redacted message preview.

- **Approve:** future messages from that exact channel/user pair may enqueue.
- **Block:** future messages are denied with `channel.policy_denied`.
- **Leave pending:** every message stays denied and updates the queue item.

Approve only when the sender is expected for the agent. For group chats, verify
the chat id and the user id before approving.

## Revoke Access

Use **Revoke** for identities that were previously allowed but should stop
routing. Revoked identities deny before enqueue and override legacy
`ALLOWED_USER_IDS` compatibility.

## Error Codes

| Code | Meaning | Operator action |
|---|---|---|
| `channel.identity_unknown` | Sender was not approved and is queued. | Approve, block, or create a pairing code. |
| `channel.pairing_required` | Channel is connected but has no approved sender. | Pair or approve a sender. |
| `channel.policy_denied` | Sender is blocked or revoked. | Keep blocked or explicitly approve again. |
| `channel.relay_failed` | Gateway could not deliver a channel reply. | Inspect channel token, Telegram API status, and runtime logs. |

## Validation

Focused checks:

```bash
uv run python -m pytest \
  tests/test_channels/test_gateway.py \
  tests/test_channels/test_manager.py \
  tests/test_channels/test_channel_gateway_smoke.py \
  tests/test_control_plane_onboarding_api.py
pnpm --filter koda-web exec vitest run \
  src/lib/contracts/channel-gateway.test.ts \
  src/components/control-plane/editor/channel-gateway-mini-panel.test.tsx
```

Offline operational smoke:

```bash
uv run python scripts/channel_gateway_smoke.py \
  --input tests/fixtures/channels/channel_gateway_smoke.v1.json
```

Manual live Telegram smoke when credentials are available:

1. Clear `ALLOWED_USER_IDS`.
2. Send a Telegram message from an unknown sender.
3. Confirm no task is created and the sender appears in the unknown queue.
4. Approve the sender.
5. Send another message and confirm it follows the normal task path.
6. Revoke the identity and confirm the next message is denied.

Slack/Discord live E2E requires `SLACK_*` or `DISCORD_*` credentials and should
be recorded as blocked when those secrets are absent; the contract tests still
must pass locally.

## Troubleshooting

- If all Telegram users are denied, check whether the gateway has an allowed
  identity or legacy `ALLOWED_USER_IDS` values.
- If an approved sender is still denied, verify the Telegram `channel_id` and
  `user_id`; group chat identity is different from a direct chat.
- If the dashboard cannot load gateway state, inspect Postgres and fallback
  file permissions under `STATE_ROOT_DIR/channel_gateway`.
- If pairing succeeds but the user sees no task, ask them to send the actual
  task again. Pairing text is intentionally discarded.

## Rollback

The migration is additive. To roll back Phase 6 channel state, export any
needed records from `channel_gateway_identities`, `channel_unknown_senders`,
`channel_pairing_codes`, and `channel_gateway_events`, then ignore or drop
those tables. The legacy Telegram bot token and `ALLOWED_USER_IDS` settings
remain available, but empty allowlist continues to deny all senders.
