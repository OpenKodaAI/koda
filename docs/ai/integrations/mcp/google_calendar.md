# Google Calendar

- **Integration key**: `google_calendar`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://developers.google.com/calendar/api
- **Transport**: stdio
- **Install command**: `npx -y @cocal/google-calendar-mcp`

## Descrição

Acesse Google Calendar via OAuth: lista calendários, cria/edita eventos, consulta disponibilidade (free/busy) e RSVPs.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `google` · scopes: `https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | não | password | OAuth Client ID (fallback) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | não | password | OAuth Client Secret (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_calendars` | read | Listar calendários |
| `list_events` | read | Listar eventos |
| `get_event` | read | Detalhes de evento |
| `create_event` | write | Criar evento |
| `update_event` | write | Atualizar evento |
| `delete_event` | destructive | Excluir evento |
| `freebusy` | read | Consultar disponibilidade |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-google_calendar-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-google_calendar-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-google_calendar-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-google_calendar-gotchas -->
