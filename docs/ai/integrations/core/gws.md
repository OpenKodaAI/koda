# Google Workspace

- **Integration key**: `gws`
- **Kind**: core
- **Transport**: cli
- **Risk class**: write
- **Auth modes**: `service_account`, `service_account_key`
- **Required env**: —
- **Required secrets**: —

## Descrição

Governed Google Workspace CLI and service-account credentials.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | sim | textarea | Service Account JSON (caminho ou conteúdo) — Cole o JSON do service account ou o caminho absoluto do arquivo. |


## Runtime constraints

- `allowed_domains`
- `allow_private_network`

## Como o agente usa bem

<!-- MANUAL:BEGIN:core-gws-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:core-gws-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:core-gws-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:core-gws-gotchas -->
