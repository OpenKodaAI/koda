# Google Drive

- **Integration key**: `google_drive`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://developers.google.com/drive/api
- **Transport**: stdio
- **Install command**: `npx -y @isaacphi/mcp-gdrive`

## Descrição

Navegue e gerencie arquivos no Google Drive via OAuth: listar, buscar, ler conteúdo, criar pastas e fazer upload de novos itens.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `google` · scopes: `https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/drive.file`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GDRIVE_OAUTH_CLIENT_ID` | não | password | OAuth Client ID (fallback) |
| `GDRIVE_OAUTH_CLIENT_SECRET` | não | password | OAuth Client Secret (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_files` | read | Listar arquivos |
| `search_files` | read | Buscar arquivos (Drive query) |
| `read_file` | read | Ler conteúdo do arquivo |
| `create_folder` | write | Criar pasta |
| `upload_file` | write | Upload de arquivo |
| `update_file` | write | Atualizar arquivo |
| `delete_file` | destructive | Excluir arquivo |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-google_drive-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-google_drive-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-google_drive-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-google_drive-gotchas -->
