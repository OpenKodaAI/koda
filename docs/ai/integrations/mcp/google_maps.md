# Google Maps

- **Integration key**: `google_maps`
- **Kind**: mcp
- **Tier**: high_impact
- **Category**: cloud
- **Canonical source**: https://developers.google.com/maps/ai/mcp
- **Transport**: stdio
- **Install command**: `npx -y @googlemaps/code-assist-mcp`

## Descrição

Consulte a documentação do Google Maps Platform e gere código integrado com Maps, Places, Directions e Geocoding.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GOOGLE_MAPS_API_KEY` | sim | password | Google Maps API Key |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `retrieve-google-maps-platform-docs` | read | Consultar documentação oficial |
| `retrieve-instructions` | read | Guia de instruções para o agente |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-google_maps-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-google_maps-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-google_maps-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-google_maps-gotchas -->
