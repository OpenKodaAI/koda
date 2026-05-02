# Atlassian

- **Integration key**: `atlassian`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://support.atlassian.com/atlassian-rovo-mcp-server/
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.atlassian.com/v1/mcp`
- **Remote URL**: https://mcp.atlassian.com/v1/mcp

## Descrição

Conecte ao Atlassian Cloud para gerenciar issues do Jira, páginas e spaces do Confluence. Suporta OAuth 2.1 via Rovo MCP server (mcp.atlassian.com) ou autenticação por email + API token quando o admin habilita.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `atlassian` · scopes: `read:jira-work write:jira-work read:confluence-content.all`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `ATLASSIAN_SITE_URL` | não | text | Site URL (fallback) — Ex.: https://yourorg.atlassian.net (apenas para autenticação por API token) |
| `ATLASSIAN_USER_EMAIL` | não | text | Email da conta (fallback) |
| `ATLASSIAN_API_TOKEN` | não | password | API Token (fallback) — Crie em id.atlassian.com/manage-profile/security/api-tokens. Use preferencialmente OAuth — só preencha se o admin desabilitou o flow OAuth. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `get_issue` | read | Recuperar detalhes de um Jira issue |
| `search_issues` | read | Buscar issues com JQL |
| `create_issue` | write | Criar issue no Jira |
| `update_issue` | write | Atualizar campos de issue |
| `add_comment` | write | Adicionar comentário |
| `get_page` | read | Recuperar página do Confluence |
| `search_pages` | read | Buscar páginas do Confluence (CQL) |
| `create_page` | write | Criar página no Confluence |
| `update_page` | write | Atualizar página do Confluence |
| `list_projects` | read | Listar projetos do Jira |
| `list_spaces` | read | Listar spaces do Confluence |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-atlassian-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-atlassian-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-atlassian-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-atlassian-gotchas -->
