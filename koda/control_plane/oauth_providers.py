"""Static OAuth configuration registry for MCP server providers.

Each entry defines the OAuth endpoints, default scopes, token-to-env-var
mapping, and provider-specific behaviour needed by the MCP OAuth flow
service (``koda.services.mcp_oauth``) to perform authorization-code
exchanges and token lifecycle management.

The ``token_env_mapping`` field is the bridge between the OAuth world and
the MCP world: it maps token-response fields (e.g. ``access_token``) to
the environment variable the corresponding MCP server expects at startup
(e.g. ``STRIPE_SECRET_KEY``).  This allows the runtime bootstrap to inject
decrypted tokens into the server process without any provider-specific
wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TokenExchangeAuth = Literal["body", "basic"]


@dataclass(frozen=True, slots=True)
class OAuthProviderConfig:
    """Immutable OAuth configuration for a single MCP server provider.

    Attributes:
        server_key: Stable identifier matching the MCP server catalog key.
        display_name: Human-readable provider name shown in the UI.
        authorization_url: Full URL for the OAuth authorization endpoint.
        token_url: Full URL for the OAuth token exchange endpoint.
        default_scopes: Space-separated default scopes requested during
            authorization.  May be overridden per-connection.
        pkce_required: Whether the provider mandates PKCE (Proof Key for
            Code Exchange).  When ``True`` the flow always generates a
            code verifier and challenge.
        token_env_mapping: Maps token-response field names to the
            environment variable the MCP server expects.
            Example: ``{"access_token": "STRIPE_SECRET_KEY"}``.
        extra_auth_params: Additional query parameters appended to the
            authorization URL (e.g. ``{"response_type": "code"}``).
        supports_refresh: Whether the provider issues refresh tokens that
            can be used to obtain new access tokens automatically.
        revocation_url: Optional endpoint for revoking tokens.  ``None``
            when the provider does not support programmatic revocation.
        token_exchange_auth: How client credentials are sent during the
            token exchange.  ``"body"`` sends ``client_id`` and
            ``client_secret`` as POST body parameters; ``"basic"`` sends
            them via HTTP Basic authentication.
    """

    server_key: str
    display_name: str
    authorization_url: str
    token_url: str
    default_scopes: str = ""
    pkce_required: bool = False
    token_env_mapping: dict[str, str] = field(default_factory=dict)
    extra_auth_params: dict[str, str] = field(default_factory=dict)
    supports_refresh: bool = True
    revocation_url: str | None = None
    token_exchange_auth: TokenExchangeAuth = "body"


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
# Each key matches the ``server_key`` used in the MCP server catalog
# (``apps/web/src/components/control-plane/system/mcp/mcp-catalog-data.ts``)
# and in ``cp_mcp_server_catalog``.
#
# Only providers whose MCP servers are listed in the catalog AND that offer
# a standard OAuth 2.0 authorization-code flow appear here.
# ---------------------------------------------------------------------------

OAUTH_PROVIDER_CONFIGS: dict[str, OAuthProviderConfig] = {
    # ---- Stripe ----
    "stripe": OAuthProviderConfig(
        server_key="stripe",
        display_name="Stripe",
        authorization_url="https://connect.stripe.com/oauth/authorize",
        token_url="https://connect.stripe.com/oauth/token",
        default_scopes="read_write",
        token_env_mapping={"access_token": "STRIPE_SECRET_KEY"},
        extra_auth_params={"response_type": "code"},
        supports_refresh=True,
        revocation_url="https://connect.stripe.com/oauth/deauthorize",
    ),
    # ---- GitHub ----
    "github": OAuthProviderConfig(
        server_key="github",
        display_name="GitHub",
        authorization_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        default_scopes="repo read:org",
        token_env_mapping={"access_token": "GITHUB_PERSONAL_ACCESS_TOKEN"},
        supports_refresh=False,
        token_exchange_auth="body",
    ),
    # ---- Slack ----
    "slack": OAuthProviderConfig(
        server_key="slack",
        display_name="Slack",
        authorization_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        default_scopes="channels:read chat:write",
        token_env_mapping={"access_token": "SLACK_BOT_TOKEN"},
        supports_refresh=True,
        revocation_url="https://slack.com/api/auth.revoke",
        token_exchange_auth="body",
    ),
    # ---- Notion ----
    "notion": OAuthProviderConfig(
        server_key="notion",
        display_name="Notion",
        authorization_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        token_env_mapping={"access_token": "NOTION_TOKEN"},
        supports_refresh=False,
        token_exchange_auth="basic",
    ),
    # ---- Linear ----
    "linear": OAuthProviderConfig(
        server_key="linear",
        display_name="Linear",
        authorization_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
        default_scopes="read write",
        token_env_mapping={"access_token": "LINEAR_API_KEY"},
        supports_refresh=True,
        revocation_url="https://api.linear.app/oauth/revoke",
    ),
    # ---- HubSpot ----
    "hubspot": OAuthProviderConfig(
        server_key="hubspot",
        display_name="HubSpot",
        authorization_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/v1/token",
        default_scopes="crm.objects.contacts.read crm.objects.contacts.write",
        token_env_mapping={"access_token": "PRIVATE_APP_ACCESS_TOKEN"},
        supports_refresh=True,
    ),
    # ---- Figma ----
    "figma": OAuthProviderConfig(
        server_key="figma",
        display_name="Figma",
        authorization_url="https://www.figma.com/oauth",
        token_url="https://api.figma.com/v1/oauth/token",
        default_scopes="files:read",
        token_env_mapping={"access_token": "FIGMA_API_KEY"},
        supports_refresh=True,
    ),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_oauth_config(server_key: str) -> OAuthProviderConfig | None:
    """Return the OAuth configuration for *server_key*, or ``None``."""
    return OAUTH_PROVIDER_CONFIGS.get(server_key)


def is_oauth_supported(server_key: str) -> bool:
    """Check whether *server_key* has a registered OAuth configuration."""
    return server_key in OAUTH_PROVIDER_CONFIGS


def get_all_oauth_server_keys() -> list[str]:
    """Return every server key that has an OAuth configuration."""
    return list(OAUTH_PROVIDER_CONFIGS.keys())
