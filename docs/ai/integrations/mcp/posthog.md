# PostHog

- **Integration key**: `posthog`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: data
- **Canonical source**: https://posthog.com/docs/model-context-protocol
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.posthog.com/mcp`
- **Remote URL**: https://mcp.posthog.com/mcp

## Descrição

Servidor MCP remoto oficial em mcp.posthog.com. Consulta eventos, funnels, dashboards, feature flags e personas. Complementa Sentry (que cobre erros) com analytics de produto.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `POSTHOG_API_KEY` | sim | password | Personal API Key — Crie em app.posthog.com/settings/user-api-keys. |
| `POSTHOG_HOST` | não | text | Host (opcional, self-hosted) — Padrão: https://app.posthog.com. Use sua URL self-hosted se aplicável. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `query_events` | read | Consultar eventos |
| `query_funnel` | read | Consultar funnel |
| `get_insight` | read | Detalhes de insight |
| `list_dashboards` | read | Listar dashboards |
| `get_feature_flag` | read | Detalhes de feature flag |
| `update_feature_flag` | write | Atualizar feature flag |
| `list_persons` | read | Listar personas/users |
| `query_hogql` | read | Executar query HogQL |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-posthog-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-posthog-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-posthog-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-posthog-gotchas -->
