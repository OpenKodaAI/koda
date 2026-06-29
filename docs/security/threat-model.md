# Threat Model

Date: `2026-04-05`

## Trust Boundaries

Koda has five important trust boundaries:

1. Operator browser to web dashboard
The browser is partially trusted only after the operator authenticates. It must never inherit backend service credentials implicitly.

2. Web dashboard to control plane
The web tier is a proxy and UI surface, not the policy authority. It should hold only the minimum material required to relay authenticated operator intent.

3. Control plane to runtime
The control plane is trusted to issue scoped runtime access, but runtime sessions, attach flows, and live operations still need independent expiry, redaction, and least privilege.

4. Runtime to tools/integrations/MCP
This is the highest-risk boundary. The LLM can influence outbound requests, local execution, browser automation, and third-party systems through tool calls.

5. Platform to external infrastructure
Databases, object storage, reverse proxies, webhook senders, OAuth providers, and MCP servers are outside the repository trust boundary and must be treated as partially trusted dependencies.

## Protected Assets

- control-plane API tokens and bootstrap secrets
- operator session material and browser cookies
- runtime attach credentials, websocket relays, and live browser sessions
- provider API keys, OAuth tokens, and integration secrets
- audit history, runtime events, and sensitive artifacts
- Postgres-backed durable state
- object-storage contents and derived evidence
- agent policies, tool policies, and integration grants

## Threat Actors

- anonymous internet users probing public web routes
- authenticated operators making mistakes or over-granting agent capabilities
- end users attempting prompt injection through tasks, documents, web pages, or integrations
- malicious MCP or integration providers
- attackers with network footholds attempting SSRF, token theft, or lateral movement
- insiders with repository or deployment access

## Primary Abuse Paths

### Operator Boundary Abuse

- replay or theft of operator sessions
- cross-site request forgery against cookie-authenticated dashboard routes
- privilege confusion where browser requests inherit server-side tokens

### Runtime Attach Abuse

- theft of raw attach tokens from browser payloads, URLs, logs, or traces
- reuse of attach sessions beyond their intended TTL
- terminal/browser relay abuse after task completion or privilege downgrade

### Tool And Agent Abuse

- prompt injection that convinces the model to use write-capable tools
- shell or file-system access to read secrets or modify code without authorization
- browser-write abuse against internal admin surfaces
- git or plugin abuse to fetch or execute untrusted code

### Integration And MCP Abuse

- SSRF through custom MCP endpoints or remote tool transports
- exfiltration through permissive integration grants
- destructive third-party actions triggered without explicit grant or approval
- malicious MCP tool metadata that understates destructive behavior

### Data-Layer Abuse

- database MITM when TLS is present but not validated
- SSH MITM when host keys are not checked
- plaintext persistence of sensitive runtime credentials
- sensitive artifacts or traces leaking through audit, logs, or screenshots

## Mitigation Themes

- fail closed by default
- separate operator identity from backend service identity
- keep bearer material out of URLs and browser-visible payloads
- prefer scoped, expiring grants instead of ambient access
- validate both literal IPs and resolved hostnames for outbound transports
- pin supply-chain entrypoints or route them through controlled upgrade processes
- redact secrets before persistence, relay, and display

## Residual High-Risk Areas For Ongoing Review

- prompt-injection resistance in real multi-turn agent workflows
- approval-mode drift or silent policy broadening over time
- MCP safety classification accuracy for newly added servers
- browser automation against internal-only apps when private-network access is intentionally enabled
- incident detection for suspicious attach, relay, or integration usage
