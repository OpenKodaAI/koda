# Todoist

- **Integration key**: `todoist`
- **Kind**: mcp
- **Tier**: high_impact
- **Category**: productivity
- **Canonical source**: https://developer.todoist.com/
- **Transport**: stdio
- **Install command**: `npx -y todoist-mcp-server`

## Descrição

Gerencie tarefas, projetos, seções e labels no Todoist. Crie, complete, reabra e organize tarefas.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `TODOIST_API_TOKEN` | sim | password | Todoist API Token |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `listTasks` | read | Listar tarefas com filtros |
| `createTask` | write | Criar nova tarefa |
| `updateTask` | write | Atualizar propriedades da tarefa |
| `completeTask` | write | Marcar tarefa como concluída |
| `reopenTask` | write | Reabrir tarefa concluída |
| `deleteTask` | destructive | Remover tarefa permanentemente |
| `listProjects` | read | Listar projetos |
| `createProject` | write | Criar novo projeto |
| `listSections` | read | Listar seções de um projeto |
| `createSection` | write | Criar seção em projeto |
| `createLabel` | write | Criar nova label |
| `addComment` | write | Adicionar comentário a tarefa |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-todoist-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-todoist-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-todoist-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-todoist-gotchas -->
