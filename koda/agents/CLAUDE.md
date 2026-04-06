# Inter-Agent Communication Guide

Message passing and task delegation between agents.

## Key Files
- `message_bus.py` -- AgentMessageBus (send/receive/delegate/broadcast)
- `models.py` -- AgentMessage, DelegationRequest, DelegationResult

## Patterns
- `agent_send` / `agent_receive` -- async message passing
- `agent_delegate` -- task delegation with depth limits
- `agent_broadcast` -- send to all agents

## Guardrails
- Max delegation depth: `INTER_AGENT_MAX_DELEGATION_DEPTH` (default 3)
- Message timeout: `INTER_AGENT_MESSAGE_TIMEOUT` (default 60s)
- Inbox size: 100 messages per agent
