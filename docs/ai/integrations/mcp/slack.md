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

Envie mensagens, leia histórico de canais, responda em threads e consulte perfis de usuários no Slack do seu workspace.

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
| `slack_list_channels` | read | Listar canais disponíveis |
| `slack_post_message` | write | Enviar mensagem no canal |
| `slack_reply_to_thread` | write | Responder em thread |
| `slack_add_reaction` | write | Adicionar reação com emoji |
| `slack_get_channel_history` | read | Histórico de mensagens |
| `slack_get_thread_replies` | read | Respostas de uma thread |
| `slack_get_users` | read | Listar usuários do workspace |
| `slack_get_user_profile` | read | Perfil de um usuário |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-slack-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-slack-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-slack-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-slack-gotchas -->
