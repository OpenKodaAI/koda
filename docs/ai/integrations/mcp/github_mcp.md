# GitHub

- **Integration key**: `github_mcp`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://github.com/github/github-mcp-server
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://api.githubcopilot.com/mcp`
- **Remote URL**: https://api.githubcopilot.com/mcp

## Descrição

Servidor MCP oficial do GitHub: lê e edita repos, abre PRs, gerencia issues e consulta Copilot/Actions. OAuth 2.1 via api.githubcopilot.com/mcp ou Personal Access Token classic/fine-grained.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `github` · scopes: `repo read:org read:user`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | não | password | Personal Access Token (fallback) — Use preferencialmente OAuth. Para PAT, gere em github.com/settings/tokens (classic ou fine-grained) com scopes 'repo', 'read:org' e 'read:user'. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_repos` | read | Listar repositórios |
| `get_repo` | read | Detalhes de um repositório |
| `list_issues` | read | Listar issues |
| `create_issue` | write | Criar issue |
| `comment_on_issue` | write | Comentar em issue |
| `list_pull_requests` | read | Listar pull requests |
| `create_pull_request` | write | Abrir pull request |
| `get_file_contents` | read | Ler arquivo do repo |
| `create_or_update_file` | write | Criar/editar arquivo |
| `search_code` | read | Buscar código |
| `list_workflow_runs` | read | Listar runs de Actions |
| `get_workflow_run` | read | Detalhes de run |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-github_mcp-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-github_mcp-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-github_mcp-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-github_mcp-gotchas -->
