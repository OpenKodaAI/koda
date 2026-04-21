# GitHub CLI

- **Integration key**: `gh`
- **Kind**: core
- **Transport**: cli
- **Risk class**: write
- **Auth modes**: `local_session`, `token`
- **Required env**: —
- **Required secrets**: —

## Descrição

Governed GitHub CLI execution.

## Connection profile

**Strategy**: `local_app`
- App local: **GitHub CLI (gh)**
  - Execute `gh auth login` no terminal para autenticar.

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | não | password | Personal Access Token (fallback) — Opcional: use apenas quando `gh auth login` não for viável. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Como o agente usa bem

<!-- MANUAL:BEGIN:core-gh-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:core-gh-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:core-gh-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:core-gh-gotchas -->
