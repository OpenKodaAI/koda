# Box

- **Integration key**: `box`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://www.npmjs.com/package/box-mcp-server
- **Transport**: stdio
- **Install command**: `npx -y box-mcp-server@0.3.1`

## Descrição

Servidor MCP comunitário para Box Cloud. Lista, baixa e faz upload de arquivos, cria folders, compartilha links. Auth via OAuth 2.0 do Box (preferencial) ou Developer Token.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `box` · scopes: `root_readwrite`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `BOX_DEVELOPER_TOKEN` | não | password | Developer Token (fallback) — Use preferencialmente OAuth. Token disponível em developer.box.com. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_files` | read | Listar arquivos |
| `get_file` | read | Detalhes de arquivo |
| `download_file` | read | Baixar arquivo |
| `upload_file` | write | Upload de arquivo |
| `create_folder` | write | Criar folder |
| `list_folders` | read | Listar folders |
| `search` | read | Buscar arquivos |
| `share_file` | write | Compartilhar arquivo |
| `move_file` | write | Mover arquivo |
| `delete_file` | destructive | Excluir arquivo |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-box-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-box-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-box-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-box-gotchas -->
