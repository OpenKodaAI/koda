# GitLab

- **Integration key**: `gitlab_mcp`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://github.com/zereight/gitlab-mcp
- **Transport**: stdio
- **Install command**: `npx -y @zereight/mcp-gitlab`

## Descrição

Servidor MCP comunitário do GitLab: navega projetos, abre merge requests, lê issues e consulta pipelines. Auth via Personal Access Token (scope ``api`` ou ``read_api``).

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GITLAB_PERSONAL_ACCESS_TOKEN` | sim | password | Personal Access Token — Crie em GitLab → User → Preferences → Access tokens com scope 'api' ou 'read_api'. |
| `GITLAB_API_URL` | não | text | API URL (opcional) — Padrão: https://gitlab.com/api/v4. Use sua URL self-hosted se aplicável. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_projects` | read | Listar projetos |
| `get_project` | read | Detalhes do projeto |
| `list_issues` | read | Listar issues |
| `create_issue` | write | Criar issue |
| `list_merge_requests` | read | Listar merge requests |
| `create_merge_request` | write | Abrir merge request |
| `get_file_content` | read | Ler arquivo do repo |
| `create_or_update_file` | write | Criar/editar arquivo |
| `search_blobs` | read | Buscar código |
| `list_pipelines` | read | Listar pipelines CI |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-gitlab_mcp-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-gitlab_mcp-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-gitlab_mcp-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-gitlab_mcp-gotchas -->
