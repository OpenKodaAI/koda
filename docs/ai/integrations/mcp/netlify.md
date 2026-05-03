# Netlify

- **Integration key**: `netlify`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://docs.netlify.com/welcome/build-with-ai/netlify-mcp-server/
- **Transport**: stdio
- **Install command**: `npx -y @netlify/mcp@1.15.1`

## Descrição

Servidor MCP oficial da Netlify. Gerencie sites, deploys, environment variables, edge functions, formulários e domínios.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `NETLIFY_PERSONAL_ACCESS_TOKEN` | sim | password | Personal Access Token — Crie em app.netlify.com → User settings → Applications → Personal access tokens. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_sites` | read | Listar sites |
| `get_site` | read | Detalhes de site |
| `deploy_site` | write | Disparar deploy |
| `list_deploys` | read | Listar deploys |
| `get_deploy` | read | Detalhes de deploy |
| `list_env_vars` | read | Listar variáveis de ambiente |
| `set_env_var` | write | Definir variável de ambiente |
| `delete_env_var` | destructive | Remover variável de ambiente |
| `list_forms` | read | Listar formulários |
| `list_functions` | read | Listar edge functions |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-netlify-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-netlify-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-netlify-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-netlify-gotchas -->
