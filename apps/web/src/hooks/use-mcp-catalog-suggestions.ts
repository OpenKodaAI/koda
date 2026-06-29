"use client";

import { keepPreviousData } from "@tanstack/react-query";

import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { requestJson } from "@/lib/http-client";
import {
  filterAllowedMcpCatalogEntries,
  projectApiCatalogEntry,
  type McpSuggestedServer,
} from "@/components/control-plane/system/mcp/mcp-catalog-utils";

type CatalogResponse = {
  items: Array<Record<string, unknown>>;
};

async function fetchMcpCatalogSuggestions(): Promise<McpSuggestedServer[]> {
  const data = await requestJson<CatalogResponse>(
    "/api/control-plane/connections/catalog",
  );
  const items = data.items ?? [];
  const mcpItems = items.filter((item) => item.kind === "mcp");
  // Reserved keys (filesystem, github native, etc.) are filtered out so they
  // never surface as user-installable MCP servers.
  const allowed = filterAllowedMcpCatalogEntries(
    mcpItems.map((item) => ({
      ...item,
      server_key: String(item.integration_key ?? item.server_key ?? ""),
    })),
  );
  return allowed.map(projectApiCatalogEntry);
}

/**
 * Fetches the suggested MCP catalog from the control-plane API. The data is
 * the SSoT — there is no TS-side mirror anymore. Cached aggressively because
 * the catalog only mutates when an operator adds a custom server.
 *
 * `data` is `undefined` while loading; consumers should branch on `isLoading`
 * to render skeletons.
 */
export function useMcpCatalogSuggestions() {
  const query = useControlPlaneQuery<McpSuggestedServer[]>({
    tier: "catalog",
    queryKey: ["mcp", "catalog", "suggestions"],
    queryFn: fetchMcpCatalogSuggestions,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    staleTime: 60 * 1000,
  });

  return {
    servers: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}
