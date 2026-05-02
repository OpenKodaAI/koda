# Bitbucket

- **Integration key**: `bitbucket`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: development
- **Canonical source**: https://www.npmjs.com/package/@nexus2520/bitbucket-mcp-server
- **Transport**: stdio
- **Install command**: `npx -y @nexus2520/bitbucket-mcp-server`

## Descrição

Servidor MCP comunitário para Bitbucket Cloud e Server. Lista repositórios, gerencia pull requests, lê arquivos, executa builds. Cloud: Username + App Password. Server: HTTP access token.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `BITBUCKET_USERNAME` | não | text | Username (Cloud) — Para Bitbucket Cloud: seu username Atlassian. |
| `BITBUCKET_APP_PASSWORD` | não | password | App Password (Cloud) — Crie em id.atlassian.com/manage-profile/security/app-passwords com escopos repository, pullrequest, pipeline. |
| `BITBUCKET_TOKEN` | não | password | HTTP Access Token (Server) — Para Bitbucket Server self-hosted, gere em User profile → Personal access tokens. |
| `BITBUCKET_URL` | não | text | Base URL (Server) — Apenas para Bitbucket Server (ex.: https://bitbucket.empresa.com). |
| `BITBUCKET_DEFAULT_WORKSPACE` | não | text | Workspace padrão (Cloud) — Opcional: limita o escopo a um único workspace. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_repositories` | read | Listar repositórios |
| `get_repository` | read | Detalhes do repositório |
| `list_pull_requests` | read | Listar pull requests |
| `create_pull_request` | write | Abrir pull request |
| `merge_pull_request` | write | Fazer merge de PR |
| `get_pull_request` | read | Detalhes de PR |
| `comment_pull_request` | write | Comentar em PR |
| `get_file_content` | read | Ler arquivo do repo |
| `list_branches` | read | Listar branches |
| `list_pipelines` | read | Listar pipelines |
| `get_pipeline` | read | Detalhes de pipeline |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-bitbucket-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-bitbucket-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-bitbucket-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-bitbucket-gotchas -->
