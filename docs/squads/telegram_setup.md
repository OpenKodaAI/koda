# Telegram Squad Setup

1. Create a Telegram supergroup.
2. Enable forum topics for the supergroup.
3. Add the squad agent bots as admins.
4. In the supergroup, bind the squad:

```text
/squad_bind <workspace_id> <squad_id>
```

The bind command verifies the chat is a supergroup, forum topics are enabled,
and the current bot is an admin. It stores `workspace_id` in binding metadata
so `/squad_thread_new <title>` can create a `SquadThread` and matching forum
topic without extra setup.

Inbound topic messages are persisted as `user_input` and routed by:

1. explicit `@agent-id`
2. reply continuation
3. elected coordinator
4. capability fallback

The local target agent is enqueued directly; remote targets receive a durable
Postgres bus message.
