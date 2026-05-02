# Grafana

- **Integration key**: `grafana`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: cloud
- **Canonical source**: https://github.com/grafana/mcp-grafana
- **Transport**: stdio
- **Install command**: `uvx mcp-grafana==0.13.1`

## Descrição

Servidor MCP oficial da Grafana Labs (Python via uvx). Lista e consulta dashboards, executa queries Prometheus/Loki, gerencia alertas. Auth via Service Account Token.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GRAFANA_URL` | sim | text | Grafana URL — Ex.: https://yourorg.grafana.net ou https://grafana.empresa.com. |
| `GRAFANA_API_KEY` | sim | password | Service Account Token — Crie em Administration → Service accounts → Add token. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_dashboards` | read | Listar dashboards |
| `get_dashboard` | read | Detalhes de dashboard |
| `query_prometheus` | read | Query PromQL |
| `query_loki` | read | Query LogQL |
| `list_datasources` | read | Listar datasources |
| `list_alerts` | read | Listar alertas |
| `silence_alert` | write | Silenciar alerta |
| `get_panel_data` | read | Dados de painel |
| `search_dashboards` | read | Buscar dashboards |
| `list_folders` | read | Listar folders |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-grafana-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-grafana-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-grafana-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-grafana-gotchas -->
