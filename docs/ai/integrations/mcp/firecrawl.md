# Firecrawl

- **Integration key**: `firecrawl`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: general
- **Canonical source**: https://docs.firecrawl.dev/mcp
- **Transport**: stdio
- **Install command**: `npx -y firecrawl-mcp@3.14.1`

## Descrição

Servidor MCP oficial da Firecrawl: scrape de URLs únicas, crawl de sites inteiros, busca web e extração estruturada via LLM. Complementa Brave Search para fluxos de research.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `FIRECRAWL_API_KEY` | sim | password | API Key — Crie em firecrawl.dev/app/api-keys. |


## Runtime constraints

- `allowed_domains`
- `allow_private_network`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `scrape_url` | read | Scrape de uma URL |
| `crawl_site` | read | Crawl recursivo de site |
| `search` | read | Busca web com Firecrawl |
| `extract` | read | Extração estruturada via LLM |
| `map_site` | read | Mapear URLs de um site |
| `batch_scrape` | read | Scrape de múltiplas URLs |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-firecrawl-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-firecrawl-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-firecrawl-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-firecrawl-gotchas -->
