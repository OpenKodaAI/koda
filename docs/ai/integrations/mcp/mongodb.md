# MongoDB

- **Integration key**: `mongodb`
- **Kind**: mcp
- **Tier**: high_impact
- **Category**: data
- **Canonical source**: https://www.mongodb.com/docs/mcp-server/
- **Transport**: stdio
- **Install command**: `npx -y mongodb-mcp-server`

## Descrição

Run queries, manage collections and indexes on MongoDB. Supports MongoDB Atlas para provisionamento de clusters.

## Connection profile

**Strategy**: `connection_string`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `MDB_MCP_CONNECTION_STRING` | sim | password | Connection URI — Format: mongodb+srv://user:password@host/database |


### Toggle de read-only

`MDB_MCP_READ_ONLY` — Modo somente leitura


## Runtime constraints

- `allowed_db_envs`
- `read_only_mode`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `find` | read | Query documents with filters |
| `listCollections` | read | List available collections |
| `insertOne` | write | Insert document |
| `updateOne` | write | Atualizar documento |
| `deleteOne` | destructive | Remove document |
| `createIndex` | write | Create index |
| `dropIndex` | destructive | Remove index |
| `indexes` | read | List existing indexes |
| `atlas-list-clusters` | read | List Atlas clusters |
| `atlas-list-projects` | read | Listar projetos Atlas |
| `atlas-inspect-cluster` | read | Detalhes do cluster |
| `atlas-create-free-cluster` | destructive | Provision free cluster |
| `atlas-list-db-users` | read | List database users |
| `atlas-create-db-user` | write | Create database user |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-mongodb-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-mongodb-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-mongodb-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-mongodb-gotchas -->
