# Brave Search

- **Integration key**: `brave_search`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: data
- **Canonical source**: https://brave.com/search/api/
- **Transport**: stdio
- **Install command**: `npx -y @brave/brave-search-mcp-server`

## Descrição

Realize buscas na web, notícias, imagens e vídeos usando a API do Brave Search com foco em privacidade.

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
| `brave_web_search` | read | Busca geral na web |
| `brave_local_search` | read | Busca de negócios locais |
| `brave_news_search` | read | Notícias recentes |
| `brave_image_search` | read | Busca de imagens |
| `brave_video_search` | read | Busca de vídeos |
| `brave_summarizer` | read | Resumo de resultados gerado por IA |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-brave_search-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-brave_search-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-brave_search-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-brave_search-gotchas -->
