# Obsidian

- **Integration key**: `obsidian`
- **Kind**: mcp
- **Tier**: high_impact
- **Category**: productivity
- **Canonical source**: https://www.npmjs.com/package/@mauricio.wolff/mcp-obsidian
- **Transport**: stdio
- **Install command**: `npx -y @mauricio.wolff/mcp-obsidian`

## Descrição

Access, search, and edit notes in your Obsidian vault. Read frontmatter, list tags, and search content across the vault.

## Connection profile

**Strategy**: `local_path`
- Argumento de caminho: `VAULT_PATH` — Caminho do vault Obsidian

## Runtime constraints

- `allowed_paths`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `readFile` | read | Read note content |
| `writeFile` | write | Create or update note |
| `deleteFile` | destructive | Remover nota do vault |
| `listVault` | read | Navegar estrutura do vault |
| `searchVault` | read | Busca full-text no vault |
| `readFrontmatter` | read | Ler metadados YAML da nota |
| `listTags` | read | Listar todas as tags do vault |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-obsidian-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-obsidian-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-obsidian-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-obsidian-gotchas -->
