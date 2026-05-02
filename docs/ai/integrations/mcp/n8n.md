# n8n

- **Integration key**: `n8n`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: general
- **Canonical source**: https://www.npmjs.com/package/n8n-mcp
- **Transport**: stdio
- **Install command**: `npx -y n8n-mcp@2.50.0`

## Descrição

Servidor MCP comunitário para n8n (cloud ou self-hosted). Lista e executa workflows, consulta histórico de executions, gerencia metadata de credentials.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `N8N_API_KEY` | sim | password | n8n API Key — Crie em Settings → n8n API → Create API Key. |
| `N8N_BASE_URL` | sim | text | Base URL — Padrão cloud: https://app.n8n.cloud. Use sua URL self-hosted se aplicável. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_workflows` | read | Listar workflows |
| `get_workflow` | read | Detalhes de workflow |
| `execute_workflow` | write | Executar workflow |
| `activate_workflow` | write | Ativar workflow |
| `deactivate_workflow` | write | Desativar workflow |
| `list_executions` | read | Listar executions |
| `get_execution` | read | Detalhes de execution |
| `list_credentials` | read | Listar credentials (metadata) |
| `create_workflow` | write | Criar workflow |
| `update_workflow` | write | Atualizar workflow |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-n8n-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-n8n-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-n8n-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-n8n-gotchas -->
