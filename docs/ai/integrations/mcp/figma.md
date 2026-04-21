# Figma

- **Integration key**: `figma`
- **Kind**: mcp
- **Tier**: verticals
- **Category**: development
- **Canonical source**: https://developers.figma.com/docs/figma-mcp-server/
- **Transport**: stdio
- **Install command**: `npx -y figma-developer-mcp --stdio`

## Descrição

Acesse arquivos de design, inspecione componentes, extraia design tokens e exporte assets do Figma.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `figma` · scopes: `files:read`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `FIGMA_API_KEY` | não | password | Personal Access Token (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `getFileNodes` | read | Recuperar estrutura do arquivo de design |
| `getComponentInfo` | read | Detalhes e propriedades de componentes |
| `downloadImages` | read | Exportar assets de design |
| `getVariables` | read | Extrair design tokens |
| `getStyles` | read | Recuperar estilos do design system |
| `analyzeComponents` | read | Análise de componentes para code generation |
| `extractAssets` | read | Exportar todos os assets do arquivo |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-figma-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-figma-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-figma-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-figma-gotchas -->
