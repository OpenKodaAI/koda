# AWS

- **Integration key**: `aws`
- **Kind**: core
- **Transport**: cli
- **Risk class**: write
- **Auth modes**: `assume_role`, `access_key`, `local_session`
- **Required env**: `AWS_DEFAULT_REGION`
- **Required secrets**: —

## Descrição

Governed AWS profiles, regions, and CLI-backed runtime access.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | sim | password | Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | sim | password | Secret Access Key |
| `AWS_DEFAULT_REGION` | sim | text | Região padrão |


### Campos de escopo (opcionais)

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `AWS_SESSION_TOKEN` | não | password | Session Token (opcional) |


## Runtime constraints

- `allowed_db_envs`

## Como o agente usa bem

<!-- MANUAL:BEGIN:core-aws-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:core-aws-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:core-aws-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:core-aws-gotchas -->
