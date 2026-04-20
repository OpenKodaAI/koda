# PostgreSQL (MCP)

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
| `DATABASE_URL` | sim | password | PostgreSQL Connection String — Formato: postgresql://usuário:senha@host:5432/banco |


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
| `getTableInfo` | read | Detalhes de colunas e constraints |
| `list_schemas` | read | Listar schemas disponíveis |
| `list_objects` | read | Navegar tabelas, views, sequences |
| `get_object_details` | read | Detalhes de colunas e constraints |
| `execute_sql` | read | Executar SQL (respeitando modo read-only) |
| `explain_query` | read | Analisar plano de execução |
| `get_top_queries` | read | Identificar queries mais lentas |
| `analyze_workload_indexes` | read | Recomendar índices para a carga |
| `analyze_query_indexes` | read | Otimizar índices de uma query |
| `analyze_db_health` | read | Checar health do banco |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-postgres_mcp-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-postgres_mcp-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-postgres_mcp-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-postgres_mcp-gotchas -->
