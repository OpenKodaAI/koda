# Granola

- **Integration key**: `granola`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: productivity
- **Canonical source**: https://github.com/btn0s/granola-mcp
- **Transport**: stdio
- **Install command**: `npx -y granola-mcp-server`

## Descrição

Acesse notas de reuniões, transcrições e eventos de calendário capturados pelo Granola.

## Connection profile

**Strategy**: `local_app`
- App local: **Granola**
  - Instale o app Granola e faça login. O MCP lê as credenciais de `~/Library/Application Support/Granola/supabase.json`.

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_meetings` | read | Listar reuniões recentes |
| `get_meeting_transcript` | read | Obter transcrição de reunião |
| `query_granola_meetings` | read | Buscar reuniões por critérios |
| `list_meeting_folders` | read | Listar pastas de reuniões |
| `get_meetings` | read | Obter detalhes de reuniões |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-granola-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-granola-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-granola-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-granola-gotchas -->
