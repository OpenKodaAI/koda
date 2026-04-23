# Supabase

- **Integration key**: `supabase`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: cloud
- **Canonical source**: https://supabase.com/docs/guides/getting-started/mcp
- **Transport**: stdio
- **Install command**: `npx -y @supabase/mcp-server-supabase@0.7.0`

## Descrição

Conecte ao Supabase para executar queries SQL, gerenciar tabelas, listar funções e inspecionar a configuração do projeto diretamente pela conversa.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | sim | password | Personal Access Token |


### Campos de escopo (opcionais)

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `SUPABASE_PROJECT_REF` | não | text | Project Reference (escopo) — Opcional: limita o acesso a um único projeto Supabase. |


## Runtime constraints

- `allowed_db_envs`
- `read_only_mode`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_tables` | read | Listar todas as tabelas do projeto |
| `get_table_schema` | read | Inspecionar schema de uma tabela |
| `execute_sql` | destructive | Executar queries SQL no banco |
| `list_functions` | read | Listar funções Postgres |
| `get_project_info` | read | Recuperar configuração do projeto |
| `apply_migration` | destructive | Aplicar migration no banco |
| `list_extensions` | read | Listar extensões instaladas |
| `list_migrations` | read | Listar migrations aplicadas |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-supabase-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-supabase-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-supabase-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-supabase-gotchas -->
