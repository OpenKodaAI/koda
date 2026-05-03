# Postman

- **Integration key**: `postman`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://www.npmjs.com/package/postman-mcp-server
- **Transport**: stdio
- **Install command**: `npx -y postman-mcp-server@1.2.0`

## Descrição

Servidor MCP para Postman API: gerenciar workspaces, collections, requests, environments, folders e mock servers. Auth via API Key.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `POSTMAN_API_KEY` | sim | password | API Key — Crie em postman.com → Profile → Settings → API Keys. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_workspaces` | read | Listar workspaces |
| `get_workspace` | read | Detalhes de workspace |
| `list_collections` | read | Listar collections |
| `get_collection` | read | Detalhes de collection |
| `create_collection` | write | Criar collection |
| `update_collection` | write | Atualizar collection |
| `list_environments` | read | Listar environments |
| `create_environment` | write | Criar environment |
| `list_mocks` | read | Listar mock servers |
| `create_mock` | write | Criar mock server |
| `get_request` | read | Detalhes de request |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-postman-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-postman-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-postman-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-postman-gotchas -->
