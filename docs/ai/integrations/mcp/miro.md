# Miro

- **Integration key**: `miro`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://developers.miro.com/docs/miro-mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.miro.com/`
- **Remote URL**: https://mcp.miro.com/

## Descrição

Servidor MCP remoto oficial da Miro em mcp.miro.com. Cria e gerencia boards, gera diagramas a partir de código/texto e gera código a partir de conteúdo do board. OAuth 2.1 com DCR.

## Connection profile

**Strategy**: `oauth_only`
- OAuth provider: `miro` · scopes: `boards:read boards:write`

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_boards` | read | Listar boards |
| `get_board` | read | Detalhes de board |
| `create_board` | write | Criar board |
| `list_items` | read | Listar itens de um board |
| `create_item` | write | Criar item (sticky/shape/text) |
| `update_item` | write | Atualizar item |
| `delete_item` | destructive | Excluir item |
| `generate_diagram` | write | Gerar diagrama a partir de código/texto |
| `generate_code_from_board` | read | Gerar código a partir do board |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-miro-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-miro-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-miro-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-miro-gotchas -->
