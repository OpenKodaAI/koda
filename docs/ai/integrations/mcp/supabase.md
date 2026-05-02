# Supabase

- **Integration key**: `supabase`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: cloud
- **Canonical source**: https://supabase.com/docs/guides/getting-started/mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.supabase.com/mcp`
- **Remote URL**: https://mcp.supabase.com/mcp

## Descrição

Connect to Supabase to run SQL queries, manage tables, list functions, and inspect project configuration directly from the chat.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `supabase` · scopes: `read write`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | não | password | Personal Access Token (fallback) — Use preferencialmente OAuth; o PAT fica como fallback para CI. |


### Campos de escopo (opcionais)

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SUPABASE_PROJECT_REF` | não | text | Project Reference (escopo) — Opcional: restringe acesso a um único projeto Supabase. |


## Runtime constraints

- `allowed_db_envs`
- `read_only_mode`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_tables` | read | Listar todas as tabelas do projeto |
| `get_table_schema` | read | Inspecionar schema de uma tabela |
| `execute_sql` | destructive | Run SQL queries on the database |
| `list_functions` | read | List Postgres functions |
| `get_project_info` | read | Retrieve project configuration |
| `apply_migration` | destructive | Apply a migration on the database |
| `list_extensions` | read | List installed extensions |
| `list_migrations` | read | List applied migrations |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-supabase-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-supabase-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-supabase-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-supabase-gotchas -->
