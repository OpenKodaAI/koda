# Sentry

- **Integration key**: `sentry`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://docs.sentry.io/product/sentry-mcp/
- **Transport**: stdio
- **Install command**: `npx -y @sentry/mcp-server@0.31.0`

## Descrição

Investigate production errors, analyze stack traces, search issues, and monitor project health with direct Sentry integration.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `sentry` · scopes: `org:read project:read event:read`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SENTRY_ACCESS_TOKEN` | não | password | Auth Token (fallback) — Use preferencialmente OAuth; o token fica como fallback. |


### Campos de escopo (opcionais)

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SENTRY_HOST` | não | text | Host self-hosted (opcional) — Deixe em branco para usar sentry.io. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `get_issues` | read | Recuperar issues de erro |
| `get_issue_details` | read | Detalhes completos de uma issue |
| `search_issues` | read | Search issues com filtros |
| `list_projects` | read | List monitored projects |
| `get_project_info` | read | Project configuration |
| `create_issue` | write | Create new issue |
| `update_issue` | write | Atualizar status de issue |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-sentry-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-sentry-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-sentry-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-sentry-gotchas -->
