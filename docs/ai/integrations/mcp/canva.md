# Canva

- **Integration key**: `canva`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://www.canva.dev/docs/connect/mcp/
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.canva.com/mcp`
- **Remote URL**: https://mcp.canva.com/mcp

## Descrição

Servidor MCP remoto oficial em mcp.canva.com via OAuth. Lista e cria designs, aplica brand templates, exporta como PDF/PNG, faz upload de assets.

## Connection profile

**Strategy**: `oauth_only`
- OAuth provider: `canva` · scopes: `design:read design:write asset:read asset:write`

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_designs` | read | Listar designs |
| `get_design` | read | Detalhes de design |
| `create_design` | write | Criar design |
| `export_design` | read | Exportar design (PDF/PNG) |
| `list_brand_templates` | read | Listar brand templates |
| `apply_brand_template` | write | Aplicar brand template |
| `upload_asset` | write | Upload de asset |
| `list_folders` | read | Listar folders |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-canva-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-canva-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-canva-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-canva-gotchas -->
