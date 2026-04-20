"""Canonical Python-side registries for per-integration metadata.

This package is the single source of truth for:

- Per-MCP-server connection profiles and tool inventories
  (`mcp_catalog.MCP_CATALOG`).
- Runtime constraints declared per integration.

Both the control-plane seeder and the documentation generator consume this
package. The frontend fetches the same data via
`/api/control-plane/connections/catalog`; `apps/web/src/components/.../mcp-catalog-data.ts`
acts only as a client-side fallback for the suggested-servers marketplace.
"""

from koda.integrations.mcp_catalog import (
    MCP_CATALOG,
    McpServerSpec,
    McpTool,
)

__all__ = [
    "MCP_CATALOG",
    "McpServerSpec",
    "McpTool",
]
