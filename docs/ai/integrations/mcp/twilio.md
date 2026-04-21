# Twilio

- **Integration key**: `twilio`
- **Kind**: mcp
- **Tier**: verticals
- **Category**: cloud
- **Canonical source**: https://github.com/twilio-labs/mcp
- **Transport**: stdio
- **Install command**: `npx -y @twilio-alpha/mcp`

## Descrição

Envie SMS, faça chamadas de voz e gerencie recursos de comunicação do Twilio incluindo messaging, chat e funções serverless.

## Connection profile

**Strategy**: `dual_token`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `TWILIO_ACCOUNT_SID` | sim | text | Account SID |
| `TWILIO_AUTH_TOKEN` | sim | password | Auth Token |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `sendSms` | write | Enviar mensagem SMS |
| `makeCall` | write | Iniciar chamada de voz |
| `listMessages` | read | Listar mensagens enviadas/recebidas |
| `getAccount` | read | Informações da conta Twilio |
| `listPhoneNumbers` | read | Listar números de telefone |
| `createMessagingService` | write | Criar serviço de messaging |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-twilio-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-twilio-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-twilio-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-twilio-gotchas -->
