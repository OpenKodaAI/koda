# Granola

- **Integration key**: `granola`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: productivity
- **Canonical source**: https://github.com/btn0s/granola-mcp
- **Transport**: stdio
- **Install command**: `npx -y granola-mcp-server`

## Descrição

Access meeting notes, transcripts, and calendar events captured by Granola.

## Connection profile

**Strategy**: `local_app`
- App local: **Granola**
  - Install the Granola app and log in. The MCP reads credentials from `~/Library/Application Support/Granola/supabase.json`.

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_meetings` | read | List recent meetings |
| `get_meeting_transcript` | read | Get meeting transcript |
| `query_granola_meetings` | read | Search meetings by criteria |
| `list_meeting_folders` | read | List meeting folders |
| `get_meetings` | read | Get meeting details |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-granola-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-granola-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-granola-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-granola-gotchas -->
