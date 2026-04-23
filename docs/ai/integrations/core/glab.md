# GitLab CLI

- **Integration key**: `glab`
- **Kind**: core
- **Transport**: cli
- **Risk class**: write
- **Auth modes**: `local_session`, `token`
- **Required env**: —
- **Required secrets**: —

## Descrição

Governed GitLab CLI execution.

## Connection profile

**Strategy**: `local_app`
- App local: **GitLab CLI (glab)**
  - Execute `glab auth login` no terminal para autenticar.

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GITLAB_PERSONAL_ACCESS_TOKEN` | não | password | Personal Access Token (fallback) |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Como o agente usa bem

<!-- MANUAL:BEGIN:core-glab-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:core-glab-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:core-glab-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:core-glab-gotchas -->
