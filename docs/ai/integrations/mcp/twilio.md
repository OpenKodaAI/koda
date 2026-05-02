# Twilio

- **Integration key**: `twilio`
- **Kind**: mcp
- **Tier**: verticals
- **Category**: cloud
- **Canonical source**: https://github.com/twilio-labs/mcp
- **Transport**: stdio
- **Install command**: `npx -y @twilio-alpha/mcp`

## Descrição

Send SMS, make voice calls, and manage Twilio communication resources including messaging, chat, and serverless functions.

## Connection profile

**Strategy**: `dual_token`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `TWILIO_ACCOUNT_SID` | sim | text | Account SID — Encontre no painel Twilio (formato AC...). |
| `TWILIO_API_KEY` | sim | text | API Key SID — Crie em Console → Account → API keys & tokens (formato SK...). |
| `TWILIO_API_SECRET` | sim | password | API Secret — Mostrado apenas uma vez ao criar a API Key. |


## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `sendSms` | write | Enviar mensagem SMS |
| `makeCall` | write | Iniciar chamada de voz |
| `listMessages` | read | List sent/received messages |
| `getAccount` | read | Twilio account information |
| `listPhoneNumbers` | read | List phone numbers |
| `createMessagingService` | write | Create messaging service |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-twilio-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-twilio-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-twilio-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-twilio-gotchas -->
