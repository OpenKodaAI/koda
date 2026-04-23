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

Gerencie issues, projetos e ciclos no Linear. Crie tickets, atualize status, adicione comentários e acompanhe o progresso das equipes.

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
| `get_ticket` | read | Recuperar detalhes de um ticket |
| `get_my_issues` | read | Issues atribuídas ao usuário atual |
| `search_issues` | read | Buscar issues |
| `create_issue` | write | Criar nova issue |
| `update_issue` | write | Atualizar propriedades de issue |
| `add_comment` | write | Adicionar comentário |
| `get_teams` | read | Listar equipes |
| `list_projects` | read | Listar projetos |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-linear-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-linear-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-linear-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-linear-gotchas -->
