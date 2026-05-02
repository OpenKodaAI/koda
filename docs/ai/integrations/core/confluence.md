# Confluence

- **Integration key**: `confluence`
- **Kind**: core
- **Transport**: api
- **Risk class**: write
- **Auth modes**: `api_token`
- **Required env**: `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`
- **Required secrets**: `CONFLUENCE_API_TOKEN`

## Descrição

Governed Confluence document access and mutations.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `CONFLUENCE_URL` | sim | text | Confluence site URL |
| `CONFLUENCE_USERNAME` | sim | text | Username (email) |
| `CONFLUENCE_API_TOKEN` | sim | password | API Token |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Como o agente usa bem

<!-- MANUAL:BEGIN:core-confluence-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:core-confluence-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:core-confluence-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:core-confluence-gotchas -->
