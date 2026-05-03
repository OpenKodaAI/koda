# ClickUp

- **Integration key**: `clickup`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://www.npmjs.com/package/clickup-mcp-server
- **Transport**: stdio
- **Install command**: `npx -y clickup-mcp-server@1.12.0`

## Descrição

Servidor MCP comunitário (oficial-aligned) para ClickUp. Tasks, lists, folders, spaces, comments, time tracking. Auth via API Key.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `CLICKUP_API_KEY` | sim | password | API Key — Crie em ClickUp → Settings → Apps → API Token. |
| `CLICKUP_TEAM_ID` | sim | text | Team ID — Disponível na URL do workspace (ex.: app.clickup.com/<TEAM_ID>/...). |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_spaces` | read | Listar spaces |
| `list_folders` | read | Listar folders |
| `list_lists` | read | Listar lists |
| `list_tasks` | read | Listar tasks |
| `get_task` | read | Detalhes de task |
| `create_task` | write | Criar task |
| `update_task` | write | Atualizar task |
| `delete_task` | destructive | Excluir task |
| `add_comment` | write | Adicionar comentário |
| `list_members` | read | Listar membros do team |
| `start_time_tracking` | write | Iniciar tracking de tempo |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-clickup-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-clickup-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-clickup-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-clickup-gotchas -->
