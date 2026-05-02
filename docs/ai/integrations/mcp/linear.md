# Linear

- **Integration key**: `linear`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://linear.app/docs/mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.linear.app/mcp`
- **Remote URL**: https://mcp.linear.app/mcp

## Descrição

Manage issues, projects, and cycles on Linear. Create tickets, update status, add comments, and track team progress.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `linear` · scopes: `read write`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `LINEAR_API_KEY` | não | password | Personal API Key (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `get_ticket` | read | Retrieve ticket details |
| `get_my_issues` | read | Issues assigned to the current user |
| `search_issues` | read | Search issues |
| `create_issue` | write | Create new issue |
| `update_issue` | write | Update issue properties |
| `add_comment` | write | Add comment |
| `get_teams` | read | List teams |
| `list_projects` | read | Listar projetos |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-linear-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-linear-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-linear-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-linear-gotchas -->
