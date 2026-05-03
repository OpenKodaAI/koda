# Zapier

- **Integration key**: `zapier`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: general
- **Canonical source**: https://zapier.com/mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.zapier.com/api/mcp/sse`
- **Remote URL**: https://mcp.zapier.com/api/mcp/sse

## Descrição

Servidor MCP remoto oficial da Zapier. Execute Zaps e acesse as ações de qualquer app conectado na sua conta Zapier. URL única por usuário (com token embutido) — gere em mcp.zapier.com.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `ZAPIER_MCP_URL` | sim | password | MCP URL (with embedded token) — Gere a URL personalizada em mcp.zapier.com — formato: https://mcp.zapier.com/api/mcp/<token>/sse |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_actions` | read | Listar ações disponíveis |
| `execute_action` | write | Executar Zap/ação |
| `search_apps` | read | Buscar apps conectados |
| `get_action_schema` | read | Schema de uma ação |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-zapier-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-zapier-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-zapier-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-zapier-gotchas -->
