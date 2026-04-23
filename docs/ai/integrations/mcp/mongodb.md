# MongoDB

- **Integration key**: `mongodb`
- **Kind**: mcp
- **Tier**: high_impact
- **Category**: data
- **Canonical source**: https://www.mongodb.com/docs/mcp-server/
- **Transport**: stdio
- **Install command**: `npx -y mongodb-mcp-server`

## Descrição

Execute queries, gerencie coleções e índices no MongoDB. Suporta MongoDB Atlas para provisionamento de clusters.

## Connection profile

**Strategy**: `connection_string`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `MDB_MCP_CONNECTION_STRING` | sim | password | Connection URI — Formato: mongodb+srv://usuário:senha@host/banco |


### Toggle de read-only

`MDB_MCP_READ_ONLY` — Modo somente leitura


## Runtime constraints

- `allowed_db_envs`
- `read_only_mode`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `find` | read | Consultar documentos com filtros |
| `listCollections` | read | Listar coleções disponíveis |
| `insertOne` | write | Inserir documento |
| `updateOne` | write | Atualizar documento |
| `deleteOne` | destructive | Remover documento |
| `createIndex` | write | Criar índice |
| `dropIndex` | destructive | Remover índice |
| `indexes` | read | Listar índices existentes |
| `atlas-list-clusters` | read | Listar clusters Atlas |
| `atlas-list-projects` | read | Listar projetos Atlas |
| `atlas-inspect-cluster` | read | Detalhes do cluster |
| `atlas-create-free-cluster` | destructive | Provisionar cluster gratuito |
| `atlas-list-db-users` | read | Listar usuários do banco |
| `atlas-create-db-user` | write | Criar usuário do banco |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-mongodb-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-mongodb-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-mongodb-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-mongodb-gotchas -->
