# Brave Search

- **Integration key**: `brave_search`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: data
- **Canonical source**: https://brave.com/search/api/
- **Transport**: stdio
- **Install command**: `npx -y @brave/brave-search-mcp-server`

## Descrição

Search the web, news, images, and videos using the Brave Search API with a privacy-first focus.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `BRAVE_API_KEY` | sim | password | Brave Search API Key |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `brave_web_search` | read | General web search |
| `brave_local_search` | read | Local business search |
| `brave_news_search` | read | Recent news |
| `brave_image_search` | read | Image search |
| `brave_video_search` | read | Video search |
| `brave_summarizer` | read | AI-generated results summary |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-brave_search-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-brave_search-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-brave_search-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-brave_search-gotchas -->
