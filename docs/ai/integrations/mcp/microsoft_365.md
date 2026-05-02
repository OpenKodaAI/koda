# Microsoft 365

- **Integration key**: `microsoft_365`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://github.com/merill/lokka
- **Transport**: stdio
- **Install command**: `npx -y @merill/lokka@0.3.0`

## Descrição

Servidor MCP comunitário (Lokka) que conecta ao Microsoft Graph: Outlook (mail/calendar), Teams (channels/chat), OneDrive (files). Auth via OAuth 2.1 do Microsoft Identity Platform.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `microsoft` · scopes: `Mail.ReadWrite Calendars.ReadWrite Files.ReadWrite Team.ReadBasic.All Chat.ReadWrite`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `TENANT_ID` | não | text | Tenant ID (fallback) — Apenas para deployments com client credentials. |
| `CLIENT_ID` | não | text | Client ID (fallback) |
| `CLIENT_SECRET` | não | password | Client Secret (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_messages` | read | Listar emails (Outlook) |
| `send_message` | write | Enviar email |
| `get_message` | read | Detalhes de email |
| `list_calendars` | read | Listar calendários |
| `list_events` | read | Listar eventos |
| `create_event` | write | Criar evento |
| `update_event` | write | Atualizar evento |
| `delete_event` | destructive | Excluir evento |
| `list_files` | read | Listar arquivos (OneDrive) |
| `read_file` | read | Ler conteúdo do arquivo |
| `upload_file` | write | Upload de arquivo |
| `list_teams_channels` | read | Listar canais Teams |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-microsoft_365-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-microsoft_365-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-microsoft_365-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-microsoft_365-gotchas -->
