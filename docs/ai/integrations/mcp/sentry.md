# Sentry

- **Integration key**: `sentry`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://docs.sentry.io/product/sentry-mcp/
- **Transport**: stdio
- **Install command**: `npx -y @sentry/mcp-server@0.31.0`

## Descrição

Investigue erros em produção, analise stack traces, busque issues e monitore a saúde dos projetos com integração direta ao Sentry.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SENTRY_ACCESS_TOKEN` | sim | password | Auth Token |


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
| `search_issues` | read | Buscar issues com filtros |
| `list_projects` | read | Listar projetos monitorados |
| `get_project_info` | read | Configuração do projeto |
| `create_issue` | write | Criar nova issue |
| `update_issue` | write | Atualizar status de issue |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-sentry-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-sentry-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-sentry-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-sentry-gotchas -->
