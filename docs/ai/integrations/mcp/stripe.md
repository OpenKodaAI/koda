# Stripe

- **Integration key**: `stripe`
- **Kind**: mcp
- **Tier**: mandatory
- **Category**: data
- **Canonical source**: https://docs.stripe.com/mcp
- **Transport**: stdio
- **Install command**: `npx -y @stripe/mcp@0.3.3`
- **Remote URL**: https://mcp.stripe.com

## Descrição

Manage customers, charges, subscriptions, and refunds on Stripe. Create payment links, inspect invoices, and query the API documentation.

## Connection profile

**Strategy**: `oauth_preferred`
- OAuth provider: `stripe` · scopes: `read_write`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `STRIPE_SECRET_KEY` | não | password | Secret API Key (fallback) — Use preferencialmente OAuth; a API Key fica apenas como fallback. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `create_customer` | write | Criar novo cliente |
| `list_customers` | read | Listar clientes |
| `create_invoice` | write | Criar fatura |
| `finalize_invoice` | destructive | Finalizar fatura para pagamento |
| `create_payment_link` | write | Create payment link |
| `list_payment_intents` | read | List payment intents |
| `list_subscriptions` | read | List subscriptions |
| `cancel_subscription` | destructive | Cancelar assinatura |
| `create_refund` | destructive | Process refund |
| `search_stripe_documentation` | read | Search the Stripe documentation |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-stripe-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-stripe-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-stripe-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-stripe-gotchas -->
