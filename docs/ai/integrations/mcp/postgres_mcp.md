# PostgreSQL

- **Integration key**: `postgres_mcp`
- **Kind**: mcp
- **Tier**: verticals
- **Category**: data
- **Canonical source**: https://www.npmjs.com/package/@henkey/postgres-mcp-server
- **Transport**: stdio
- **Install command**: `npx -y @henkey/postgres-mcp-server`

## Descrição

Conecte a qualquer banco PostgreSQL externo para executar queries e inspecionar schema via protocolo MCP.

## Connection profile

**Strategy**: `connection_string`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `DATABASE_URL` | sim | password | PostgreSQL Connection String — Format: postgresql://user:password@host:5432/database |


### Toggle de read-only

`POSTGRES_MCP_READ_ONLY` — Modo somente leitura


## Runtime constraints

- `allowed_db_envs`
- `read_only_mode`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `queryDatabase` | read | Executar queries SQL |
| `inspectSchema` | read | Inspecionar schema do banco |
| `listTables` | read | Listar todas as tabelas |
| `getTableInfo` | read | Column and constraint details |
| `list_schemas` | read | List available schemas |
| `list_objects` | read | Browse tables, views, sequences |
| `get_object_details` | read | Column and constraint details |
| `execute_sql` | read | Execute SQL (respecting read-only mode) |
| `explain_query` | read | Analyze execution plan |
| `get_top_queries` | read | Identify slowest queries |
| `analyze_workload_indexes` | read | Recommend indexes for the workload |
| `analyze_query_indexes` | read | Optimize indexes for a query |
| `analyze_db_health` | read | Check database health |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-postgres_mcp-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-postgres_mcp-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-postgres_mcp-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-postgres_mcp-gotchas -->
