# Notion

- **Integration key**: `notion`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://developers.notion.com/guides/mcp/get-started-with-mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.notion.com/mcp`
- **Remote URL**: https://mcp.notion.com/mcp

## Descrição

Search, create, and edit pages and data sources on Notion. Read content, add blocks, and manage your knowledge base.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `notion` · scopes: `(sem scopes padrão)`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `NOTION_TOKEN` | não | password | Notion Integration Token (fallback) — Use preferencialmente OAuth; o token fica como fallback. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `search_notion` | read | Busca full-text no workspace |
| `query_data_source` | read | Query data source (v2) |
| `get_page` | read | Retrieve page content |
| `create_page` | write | Create new page |
| `update_page` | write | Update page properties |
| `append_block` | write | Append content to page |
| `get_data_source` | read | Schema de um data source |
| `list_pages` | read | List workspace pages |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-notion-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-notion-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-notion-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-notion-gotchas -->
