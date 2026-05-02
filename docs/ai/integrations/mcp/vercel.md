# Vercel

- **Integration key**: `vercel`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: development
- **Canonical source**: https://vercel.com/docs/mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.vercel.com`
- **Remote URL**: https://mcp.vercel.com

## Descrição

Manage deployments, inspect build and runtime logs, check domains, and monitor project status on Vercel.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `vercel` · scopes: `read write`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `VERCEL_TOKEN` | não | password | Vercel API Token (fallback) — Use preferencialmente OAuth; o token fica como fallback. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_projects` | read | Listar projetos |
| `get_project` | read | Detalhes de um projeto |
| `list_deployments` | read | Listar deployments |
| `get_deployment` | read | Detalhes de um deployment |
| `get_deployment_build_logs` | read | Logs de build |
| `get_runtime_logs` | read | Logs de runtime |
| `deploy_to_vercel` | write | Create new deployment |
| `check_domain_availability_and_price` | read | Check domain availability |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-vercel-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-vercel-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-vercel-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-vercel-gotchas -->
