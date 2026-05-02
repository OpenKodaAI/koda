# HubSpot

- **Integration key**: `hubspot`
- **Kind**: mcp
- **Tier**: verticals
- **Category**: cloud
- **Canonical source**: https://developers.hubspot.com/mcp
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://mcp.hubspot.com`
- **Remote URL**: https://mcp.hubspot.com

## Descrição

Acesse e gerencie contatos, empresas, deals, tickets e faturas no HubSpot.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `hubspot` · scopes: `crm.objects.contacts.read crm.objects.contacts.write`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `PRIVATE_APP_ACCESS_TOKEN` | não | password | Private App Access Token (fallback) — Use preferencialmente OAuth; o private app token fica como fallback. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `getContact` | read | Recuperar contato por ID |
| `searchContacts` | read | Buscar contatos |
| `createContact` | write | Criar novo contato |
| `updateContact` | write | Atualizar contato |
| `getCompany` | read | Recuperar empresa |
| `searchCompanies` | read | Buscar empresas |
| `getDeal` | read | Detalhes de um deal |
| `searchDeals` | read | Buscar deals |
| `getTicket` | read | Recuperar ticket de suporte |
| `searchTickets` | read | Buscar tickets |
| `getInvoice` | read | Invoice details |
| `getProduct` | read | Product information |
| `getLineItem` | read | Line item details |
| `getQuote` | read | Quote details |
| `getOrder` | read | Order details |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-hubspot-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-hubspot-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-hubspot-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-hubspot-gotchas -->
