# Hugging Face

- **Integration key**: `huggingface`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: data
- **Canonical source**: https://huggingface.co/docs/hub/mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://huggingface.co/mcp`
- **Remote URL**: https://huggingface.co/mcp

## Descrição

Servidor MCP remoto oficial em huggingface.co/mcp. Acesso a models, datasets, Spaces e inference API. Auth via Hugging Face User Access Token.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `HF_TOKEN` | sim | password | User Access Token — Crie em huggingface.co/settings/tokens com escopo read. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `search_models` | read | Buscar models |
| `get_model` | read | Detalhes de model |
| `search_datasets` | read | Buscar datasets |
| `get_dataset` | read | Detalhes de dataset |
| `search_spaces` | read | Buscar Spaces |
| `run_inference` | write | Executar inference |
| `list_organizations` | read | Listar organizações |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-huggingface-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-huggingface-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-huggingface-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-huggingface-gotchas -->
