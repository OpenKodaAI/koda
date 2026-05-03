# Superhuman

- **Integration key**: `superhuman`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://help.superhuman.com/hc/en-us/articles/49810745762067-Superhuman-Mail-MCP-Server
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.mail.superhuman.com/mcp`
- **Remote URL**: https://mcp.mail.superhuman.com/mcp

## Descrição

Servidor MCP remoto oficial da Superhuman Mail. Pesquisa, responde, agenda e resume emails e eventos do calendário usando seu tom de voz. Auth via OAuth.

## Connection profile

**Strategy**: `oauth_only`
- OAuth provider: `superhuman` · scopes: `(sem scopes padrão)`

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `query_email_and_calendar` | read | Busca semântica em email/calendário |
| `list_threads` | read | Listar threads com filtros estruturados |
| `get_thread` | read | Detalhes de thread |
| `get_message` | read | Detalhes de mensagem |
| `get_attachment` | read | Baixar anexo |
| `list_labels` | read | Listar labels |
| `list_splits` | read | Listar Split Inboxes |
| `get_read_statuses` | read | Status de leitura (quem abriu) |
| `get_availability` | read | Buscar horários disponíveis |
| `create_or_update_draft` | write | Criar/editar draft |
| `discard_draft` | destructive | Descartar draft |
| `send_draft` | write | Enviar email (Smart/Scheduled Send) |
| `undo_send` | write | Desfazer envio |
| `create_or_update_event` | write | Criar/atualizar evento |
| `update_thread` | write | Label/Star/Trash/Read em threads |
| `trash_thread` | destructive | Mover thread para Trash |
| `unsubscribe` | write | Desinscrever de mailing list |
| `update_personalization` | write | Atualizar tom/preferências |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-superhuman-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-superhuman-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-superhuman-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-superhuman-gotchas -->
