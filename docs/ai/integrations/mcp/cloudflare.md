# Cloudflare

- **Integration key**: `cloudflare`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: cloud
- **Canonical source**: https://github.com/cloudflare/mcp-server-cloudflare
- **Transport**: stdio
- **Install command**: `npx -y @cloudflare/mcp-server-cloudflare`

## Descrição

Gerencie zonas DNS, deploy de Workers, configure regras de firewall e monitore a infraestrutura Cloudflare.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `cloudflare` · scopes: `zone:read dns:edit worker:edit`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | não | password | Cloudflare API Token (fallback) — Use preferencialmente OAuth; o token fica como fallback. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `list_zones` | read | List domains/zones |
| `get_zone_details` | read | Zone configuration details |
| `list_dns_records` | read | Listar registros DNS |
| `create_dns_record` | write | Criar registro DNS |
| `update_dns_record` | write | Atualizar registro DNS |
| `delete_dns_record` | destructive | Remover registro DNS |
| `list_workers` | read | Listar Workers |
| `deploy_worker` | destructive | Deploy de Worker |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-cloudflare-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-cloudflare-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-cloudflare-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-cloudflare-gotchas -->
