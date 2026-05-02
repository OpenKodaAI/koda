# Gmail

- **Integration key**: `gmail`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://developers.google.com/gmail/api
- **Transport**: stdio
- **Install command**: `npx -y @gongrzhe/server-gmail-autoauth-mcp`

## Descrição

Acesse e gerencie sua caixa do Gmail via OAuth do Google. Lista threads, lê mensagens, cria drafts, aplica/remove labels.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `google` · scopes: `https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GMAIL_OAUTH_CLIENT_ID` | não | password | OAuth Client ID (fallback) |
| `GMAIL_OAUTH_CLIENT_SECRET` | não | password | OAuth Client Secret (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_threads` | read | Listar threads |
| `read_message` | read | Ler mensagem |
| `search_messages` | read | Buscar mensagens (Gmail query) |
| `send_message` | write | Enviar mensagem |
| `create_draft` | write | Criar rascunho |
| `modify_labels` | write | Aplicar/remover labels |
| `delete_message` | destructive | Excluir mensagem |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-gmail-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-gmail-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-gmail-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-gmail-gotchas -->
