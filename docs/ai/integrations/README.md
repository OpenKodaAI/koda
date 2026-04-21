# Koda Integrations — Per-Integration Reference

This directory is the canonical per-integration documentation. Each integration has **one** .md file describing how an agent connects to it, what tools it exposes, what runtime constraints apply, and what to watch out for.

## Layout

```
docs/ai/integrations/
├─ README.md         # this file
├─ _template.md      # canonical template all per-integration docs follow
├─ core/             # core integrations (koda/agent_contract.py)
├─ mcp/              # MCP server integrations (cp_mcp_server_catalog)
└─ providers/        # AI model providers (koda/services/provider_auth.py)
```

## How this is kept in sync

Per-integration docs are generated from the contract + catalog by
[`scripts/generate_integration_docs.py`](../../../scripts/generate_integration_docs.py).

Run `python3 scripts/generate_integration_docs.py --check` in CI to detect drift.

Editable sections inside each doc (marked by `<!-- MANUAL:BEGIN -->` / `<!-- MANUAL:END -->` blocks) are preserved across regens.

## Connection strategies

Every integration declares a `ConnectionProfile` with one of these strategies:

| Strategy | When to use | UX shape |
|---|---|---|
| `oauth_only` | Provider requires OAuth (e.g. Slack remote MCP) | Single brand button |
| `oauth_preferred` | Provider supports OAuth and a legacy API key | Brand button + "Configurar manualmente" disclosure |
| `api_key` | One or more API keys / env vars | Flat list of secret fields |
| `connection_string` | One URI plus optional read-only toggle (Postgres, Mongo) | Single URI field + toggle |
| `dual_token` | Two paired credentials (Twilio SID + token) | Two fields side-by-side |
| `local_path` | Server needs a local filesystem path as command arg (Obsidian vault) | Path field with existence validation |
| `local_app` | Relies on a locally-authenticated CLI or desktop app (gh, Granola) | Detection status + instruction |
| `none` | No credential needed (Excalidraw, scheduler) | Single "Ativar" switch |

## Runtime constraints

Constraints are **declarative per integration**. The UI only renders the ones the integration declares in `runtime_constraints`:

| Key | Applies to | Semantics |
|---|---|---|
| `allowed_domains` | `web`, `browser`, MCPs doing external HTTP | Whitelist of hostnames/suffixes |
| `allowed_paths` | `shell`, `git`, `docker`, `fileops`, `obsidian` | Whitelist of filesystem prefixes |
| `allowed_db_envs` | `aws`, `supabase`, `mongodb`, `postgres_mcp` | Whitelist of DB environments (`dev`, `staging`, `prod`, `readonly`) |
| `allow_private_network` | `web`, `browser` | Whether the integration may reach private/internal IPs |
| `read_only_mode` | `mongodb`, `postgres_mcp`, `supabase` | Switches the server into read-only |

Anything outside this set is rejected by `normalize_integration_grants`.

## Where the data lives

- **Contract / profiles**: `koda/agent_contract.py` (`ConnectionProfile`, `CoreIntegrationDefinition.connection_profile`, `CoreIntegrationDefinition.runtime_constraints`)
- **MCP catalog**: `cp_mcp_server_catalog.metadata_json.connection_profile`
- **Frontend types**: `apps/web/src/lib/control-plane.ts` (`ConnectionProfile`, `RuntimeConstraintKey`)
- **Modal router**: `apps/web/src/components/control-plane/editor/tabs/connection/connection-modal-router.tsx`
- **Constraints panel**: `apps/web/src/components/control-plane/editor/tabs/constraints/dynamic-constraints-panel.tsx`
