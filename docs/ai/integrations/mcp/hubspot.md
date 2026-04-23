# HubSpot

- **Integration key**: `hubspot`
- **Kind**: mcp
- **Tier**: verticals
- **Category**: cloud
- **Canonical source**: https://developers.hubspot.com/mcp
- **Transport**: stdio
- **Install command**: `npx -y @hubspot/mcp-server`

## Descrição

Acesse e gerencie contatos, empresas, deals, tickets e faturas no HubSpot.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `hubspot` · scopes: `crm.objects.contacts.read crm.objects.contacts.write`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `PRIVATE_APP_ACCESS_TOKEN` | não | password | Private App Access Token (fallback) |


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
| `getInvoice` | read | Detalhes de fatura |
| `getProduct` | read | Informações de produto |
| `getLineItem` | read | Detalhes de item |
| `getQuote` | read | Detalhes de cotação |
| `getOrder` | read | Detalhes de pedido |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-hubspot-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-hubspot-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-hubspot-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-hubspot-gotchas -->
