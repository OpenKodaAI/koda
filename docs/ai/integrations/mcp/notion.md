# Notion

- **Integration key**: `notion`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://github.com/makenotion/notion-mcp-server
- **Transport**: stdio
- **Install command**: `npx -y @notionhq/notion-mcp-server`

## Descrição

Busque, crie e edite páginas e data sources no Notion. Consulte conteúdo, adicione blocos e gerencie sua base de conhecimento.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `notion` · scopes: `(sem scopes padrão)`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `NOTION_TOKEN` | não | password | Notion Integration Token (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `search_notion` | read | Busca full-text no workspace |
| `query_data_source` | read | Consultar data source (v2) |
| `get_page` | read | Recuperar conteúdo de página |
| `create_page` | write | Criar nova página |
| `update_page` | write | Atualizar propriedades de página |
| `append_block` | write | Adicionar conteúdo a página |
| `get_data_source` | read | Schema de um data source |
| `list_pages` | read | Listar páginas do workspace |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-notion-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-notion-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-notion-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-notion-gotchas -->
