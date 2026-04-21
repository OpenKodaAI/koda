import type { McpServerCatalogEntry } from "@/lib/control-plane";
import {
  CATEGORY_LABELS as CORE_CATEGORY_LABELS,
  INTEGRATION_CATALOG,
  getIntegrationStatus,
  type IntegrationCapability,
  type IntegrationCatalogEntry,
  type IntegrationCategory,
  type IntegrationStatus,
} from "./integration-catalog-data";
import {
  MCP_SUGGESTED_SERVERS,
  filterAllowedMcpCatalogEntries,
  isReservedMcpServerKey,
  type McpExpectedTool,
  type McpSuggestedServer,
} from "@/components/control-plane/system/mcp/mcp-catalog-data";
import { getIntegrationAccent } from "./integration-logos";

export type UnifiedIntegrationCategory = IntegrationCategory | "general";
export type UnifiedIntegrationKind = "core" | "mcp";
export type UnifiedMcpOrigin = "curated" | "custom";

export type UnifiedIntegrationMetadata = {
  developer?: string;
  type: string;
  documentationUrl?: string;
  transport?: string;
  origin?: UnifiedMcpOrigin;
  serverKey?: string;
};

export type UnifiedIntegrationEntry = {
  id: string;
  key: string;
  kind: UnifiedIntegrationKind;
  status: IntegrationStatus;
  label: string;
  tagline: string;
  description: string;
  category: UnifiedIntegrationCategory;
  logoKey: string;
  gradientFrom: string;
  gradientTo: string;
  promptExample: string;
  capabilities: IntegrationCapability[];
  metadata: UnifiedIntegrationMetadata;
  searchText: string;
  core?: {
    entry: IntegrationCatalogEntry;
  };
  mcp?: {
    serverKey: string;
    server: McpServerCatalogEntry | null;
    suggested: McpSuggestedServer | null;
    origin: UnifiedMcpOrigin;
    isCataloged: boolean;
    canAdd: boolean;
    canEdit: boolean;
    canRemove: boolean;
  };
};

export const UNIFIED_CATEGORY_LABELS: Record<UnifiedIntegrationCategory, string> = {
  ...CORE_CATEGORY_LABELS,
  general: "Geral",
};

type IntegrationConnectionLike = {
  connection_status?: string;
  last_error?: string;
  fields?: Array<{ required?: boolean; value?: string; value_present?: boolean }>;
};

function mcpStatus(server: McpServerCatalogEntry | null): IntegrationStatus {
  if (!server) return "disabled";
  return server.enabled ? "connected" : "pending";
}

function normalizeTransportLabel(transportType: string | null | undefined) {
  if (transportType === "http_sse") return "HTTP / SSE";
  if (transportType === "stdio") return "stdio";
  return transportType || "stdio";
}

function mcpToolToCapability(tool: McpExpectedTool, index: number): IntegrationCapability {
  return {
    id: `mcp-tool-${tool.name}-${index}`,
    label: tool.name,
    description: tool.description,
    icon: tool.read_only_hint ? "Search" : tool.destructive_hint ? "Shield" : "Workflow",
  };
}

function buildCoreEntry(
  entry: IntegrationCatalogEntry,
  integrations: Record<string, boolean>,
  connection?: IntegrationConnectionLike | null,
): UnifiedIntegrationEntry {
  const status = getIntegrationStatus(
    entry,
    integrations,
    connection,
  );
  return {
    id: `core:${entry.key}`,
    key: entry.key,
    kind: "core",
    status,
    label: entry.label,
    tagline: entry.tagline,
    description: entry.description,
    category: entry.category,
    logoKey: entry.logoKey,
    gradientFrom: entry.gradientFrom,
    gradientTo: entry.gradientTo,
    promptExample: entry.promptExample,
    capabilities: entry.capabilities,
    metadata: {
      developer: entry.metadata.developer,
      type: entry.metadata.type,
      documentationUrl: entry.metadata.documentationUrl,
    },
    searchText: [
      entry.label,
      entry.tagline,
      entry.description,
      entry.metadata.developer,
      entry.metadata.type,
    ]
      .join(" ")
      .toLowerCase(),
    core: {
      entry,
    },
  };
}

function buildCuratedMcpEntry(
  suggested: McpSuggestedServer,
  server: McpServerCatalogEntry | null,
): UnifiedIntegrationEntry {
  const accent = getIntegrationAccent(suggested.logo_key || "mcp");
  return {
    id: `mcp:${suggested.server_key}`,
    key: suggested.server_key,
    kind: "mcp",
    status: mcpStatus(server),
    label: suggested.display_name,
    tagline: suggested.tagline,
    description: suggested.description,
    category: suggested.category,
    logoKey: suggested.logo_key || "mcp",
    gradientFrom: accent.from,
    gradientTo: accent.to,
    promptExample: `Gerencie ${suggested.display_name} como servidor MCP no catálogo global do sistema.`,
    capabilities: suggested.expected_tools.map(mcpToolToCapability),
    metadata: {
      type: "MCP",
      documentationUrl: suggested.documentation_url || server?.documentation_url || undefined,
      transport: normalizeTransportLabel(server?.transport_type || suggested.transport_type),
      origin: "curated",
      serverKey: suggested.server_key,
    },
    searchText: [
      suggested.display_name,
      suggested.tagline,
      suggested.description,
      suggested.server_key,
      suggested.logo_key || "mcp",
      "mcp",
      "curated",
    ]
      .join(" ")
      .toLowerCase(),
    mcp: {
      serverKey: suggested.server_key,
      server,
      suggested,
      origin: "curated",
      isCataloged: Boolean(server),
      canAdd: !server,
      canEdit: Boolean(server),
      canRemove: false,
    },
  };
}

function buildCustomMcpEntry(server: McpServerCatalogEntry): UnifiedIntegrationEntry {
  const logoKey = server.logo_key || "mcp";
  const accent = getIntegrationAccent(logoKey);
  return {
    id: `mcp:${server.server_key}`,
    key: server.server_key,
    kind: "mcp",
    status: mcpStatus(server),
    label: server.display_name,
    tagline: "Servidor MCP custom",
    description:
      server.description || "Servidor MCP configurado manualmente no catálogo global do sistema.",
    category: (server.category as UnifiedIntegrationCategory) || "general",
    logoKey,
    gradientFrom: accent.from,
    gradientTo: accent.to,
    promptExample: `Gerencie ${server.display_name} como servidor MCP custom no catálogo global do sistema.`,
    capabilities: [],
    metadata: {
      type: "MCP",
      documentationUrl: server.documentation_url || undefined,
      transport: normalizeTransportLabel(server.transport_type),
      origin: "custom",
      serverKey: server.server_key,
    },
    searchText: [
      server.display_name,
      server.description,
      server.server_key,
      server.category,
      "mcp",
      "custom",
    ]
      .join(" ")
      .toLowerCase(),
    mcp: {
      serverKey: server.server_key,
      server,
      suggested: null,
      origin: "custom",
      isCataloged: true,
      canAdd: false,
      canEdit: true,
      canRemove: true,
    },
  };
}

export function buildUnifiedIntegrationEntries({
  integrations,
  integrationConnections,
  mcpCatalog,
}: {
  integrations: Record<string, boolean>;
  integrationConnections: Record<string, IntegrationConnectionLike>;
  mcpCatalog: McpServerCatalogEntry[];
}): UnifiedIntegrationEntry[] {
  const coreEntries = INTEGRATION_CATALOG.map((entry) =>
    buildCoreEntry(
      entry,
      integrations,
      integrationConnections[entry.key] ?? null,
    ),
  );

  const allowedMcpCatalog = filterAllowedMcpCatalogEntries(mcpCatalog);
  const catalogByKey = new Map(
    allowedMcpCatalog.map((server) => [server.server_key, server] as const),
  );

  const curatedMcpEntries = MCP_SUGGESTED_SERVERS.filter(
    (suggested) => !isReservedMcpServerKey(suggested.server_key),
  ).map((suggested) =>
    buildCuratedMcpEntry(suggested, catalogByKey.get(suggested.server_key) ?? null),
  );

  const curatedKeys = new Set(curatedMcpEntries.map((entry) => entry.key));
  const customMcpEntries = allowedMcpCatalog
    .filter((server) => !curatedKeys.has(server.server_key))
    .map(buildCustomMcpEntry);

  return [...coreEntries, ...curatedMcpEntries, ...customMcpEntries];
}

export function filterUnifiedIntegrationEntries(
  entries: UnifiedIntegrationEntry[],
  {
    category,
    search,
  }: {
    category: UnifiedIntegrationCategory | "all";
    search: string;
  },
) {
  const normalizedQuery = search.trim().toLowerCase();
  return entries.filter((entry) => {
    if (category !== "all" && entry.category !== category) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    return entry.searchText.includes(normalizedQuery);
  });
}

export function groupUnifiedIntegrationEntries(entries: UnifiedIntegrationEntry[]) {
  const grouped = new Map<UnifiedIntegrationCategory, UnifiedIntegrationEntry[]>();
  for (const entry of entries) {
    const bucket = grouped.get(entry.category) ?? [];
    bucket.push(entry);
    grouped.set(entry.category, bucket);
  }
  return Array.from(grouped.entries()).map(([category, categoryEntries]) => ({
    category,
    entries: categoryEntries,
  }));
}
