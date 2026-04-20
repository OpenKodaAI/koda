# {{display_name}}

- **Integration key**: `{{integration_key}}`
- **Kind**: {{core | mcp | provider}}
- **Canonical source**: {{url}}
- **Transport**: {{stdio | remote_http | sse | internal | cli | api | browser | filesystem | mcp}}
- **Install command**: `{{exact command}}`
- **Connection profile**: {{strategy}}

## Credentials

<!-- GENERATED:CREDENTIALS:BEGIN -->
| Field | Required | Purpose |
|---|---|---|
| `FIELD_KEY` | yes | ... |
<!-- GENERATED:CREDENTIALS:END -->

## OAuth (when applicable)

- **Provider**: ...
- **Scopes**: ...
- **Refresh supported**: ...
- **Revocation URL**: ...

## Runtime constraints

<!-- GENERATED:CONSTRAINTS:BEGIN -->
- `allowed_domains`: ...
- `allow_private_network`: ...
<!-- GENERATED:CONSTRAINTS:END -->

## Tools exposed

<!-- GENERATED:TOOLS:BEGIN -->
| Tool | Classification | Description |
|---|---|---|
| `tool_name` | read / write / destructive | ... |
<!-- GENERATED:TOOLS:END -->

## How the agent uses this well

<!-- MANUAL:BEGIN:patterns -->
- Padrão recomendado 1 ...
- Padrão recomendado 2 ...
<!-- MANUAL:END:patterns -->

## Gotchas

<!-- MANUAL:BEGIN:gotchas -->
- ...
<!-- MANUAL:END:gotchas -->

## References

- Canonical docs: ...
- Related code: ...
