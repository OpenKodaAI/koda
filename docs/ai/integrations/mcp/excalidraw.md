# Excalidraw

- **Integration key**: `excalidraw`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: productivity
- **Canonical source**: https://github.com/excalidraw/excalidraw-mcp
- **Transport**: stdio
- **Install command**: `npx -y excalidraw-mcp`

## Descrição

Crie e edite diagramas, fluxogramas e wireframes no Excalidraw. Exporte como imagem, manipule elementos e gerencie cenas.

## Connection profile

**Strategy**: `none`

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `create_diagram` | write | Criar novo diagrama |
| `export_to_image` | read | Exportar diagrama como PNG/SVG |
| `export_scene` | read | Exportar cena completa |
| `import_scene` | write | Importar cena de arquivo |
| `describe_scene` | read | Descrever elementos do diagrama |
| `clear_canvas` | destructive | Limpar canvas |
| `snapshot_scene` | read | Criar snapshot do diagrama |
| `set_viewport` | write | Ajustar área de visualização |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-excalidraw-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-excalidraw-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-excalidraw-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-excalidraw-gotchas -->
