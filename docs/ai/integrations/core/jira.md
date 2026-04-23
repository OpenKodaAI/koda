# Jira

- **Integration key**: `jira`
- **Kind**: core
- **Transport**: api
- **Risk class**: write
- **Auth modes**: `api_token`
- **Required env**: `JIRA_URL`, `JIRA_USERNAME`
- **Required secrets**: `JIRA_API_TOKEN`

## Descrição

Governed Jira operations and deep issue context.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `JIRA_URL` | sim | text | URL do site Jira |
| `JIRA_USERNAME` | sim | text | Usuário (email) |
| `JIRA_API_TOKEN` | sim | password | API Token |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Como o agente usa bem

<!-- MANUAL:BEGIN:core-jira-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:core-jira-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:core-jira-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:core-jira-gotchas -->
