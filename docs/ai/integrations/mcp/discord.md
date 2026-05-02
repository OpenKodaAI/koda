# Discord

- **Integration key**: `discord`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: productivity
- **Canonical source**: https://www.npmjs.com/package/discord-mcp
- **Transport**: stdio
- **Install command**: `npx -y discord-mcp@2.4.0`

## Descrição

Servidor MCP comunitário para Discord. Lê e envia mensagens, gerencia threads, lista membros, aplica reações. Auth via Bot Token.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | sim | password | Bot Token — Crie em discord.com/developers/applications → New Application → Bot → Reset Token. Necessita escopos messages, threads, members. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_guilds` | read | Listar servidores |
| `list_channels` | read | Listar canais |
| `read_messages` | read | Ler mensagens de canal |
| `send_message` | write | Enviar mensagem |
| `create_thread` | write | Criar thread |
| `add_reaction` | write | Adicionar reação |
| `list_members` | read | Listar membros |
| `get_user` | read | Detalhes de usuário |
| `delete_message` | destructive | Excluir mensagem |
| `set_status` | write | Definir status do bot |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-discord-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-discord-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-discord-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-discord-gotchas -->
