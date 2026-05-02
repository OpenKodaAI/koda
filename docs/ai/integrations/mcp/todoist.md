# Todoist

- **Integration key**: `todoist`
- **Kind**: mcp
- **Tier**: high_impact
- **Category**: productivity
- **Canonical source**: https://developer.todoist.com/
- **Transport**: stdio
- **Install command**: `npx -y todoist-mcp-server`

## Descrição

Manage tasks, projects, sections, and labels on Todoist. Create, complete, reopen, and organize tasks.

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
| `updateTask` | write | Update task properties |
| `completeTask` | write | Mark task as completed |
| `reopenTask` | write | Reopen completed task |
| `deleteTask` | destructive | Remove task permanently |
| `listProjects` | read | Listar projetos |
| `createProject` | write | Create new project |
| `listSections` | read | List sections of a project |
| `createSection` | write | Create section in project |
| `createLabel` | write | Create new label |
| `addComment` | write | Add comment a tarefa |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-todoist-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-todoist-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-todoist-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-todoist-gotchas -->
