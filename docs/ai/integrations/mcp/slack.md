# Slack

- **Integration key**: `slack`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://docs.slack.dev/ai/slack-mcp-server/
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.slack.com/mcp`
- **Remote URL**: https://mcp.slack.com/mcp

## Descrição

Send messages, read channel history, reply in threads, and look up user profiles in your Slack workspace.

## Connection profile

**Strategy**: `oauth_only`
- OAuth provider: `slack` · scopes: `channels:read chat:write users:read`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | não | password | Bot Token (fallback legado) |
| `SLACK_TEAM_ID` | não | text | Team ID (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `slack_list_channels` | read | List available channels |
| `slack_post_message` | write | Send message to channel |
| `slack_reply_to_thread` | write | Reply in thread |
| `slack_add_reaction` | write | Add emoji reaction |
| `slack_get_channel_history` | read | Message history |
| `slack_get_thread_replies` | read | Replies of a thread |
| `slack_get_users` | read | List workspace users |
| `slack_get_user_profile` | read | User profile |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-slack-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-slack-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-slack-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-slack-gotchas -->
