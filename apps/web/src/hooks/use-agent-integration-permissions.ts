"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { requestJson } from "@/lib/http-client";
import {
  INTEGRATION_CATALOG,
  type IntegrationCatalogEntry,
} from "@/components/control-plane/system/integrations/integration-catalog-data";
import { getIntegrationAccent } from "@/components/control-plane/system/integrations/integration-logos";
import type {
  ConnectionProfile,
  ControlPlaneCoreIntegration,
  ControlPlaneAgentConnection,
  ControlPlaneConnectionCatalogEntry,
  ControlPlaneConnectionTools,
  McpAgentConnection,
  McpDiscoveredTool,
  McpOAuthStatus,
  McpServerCatalogEntry,
  McpToolPolicy,
  RuntimeConstraintKey,
} from "@/lib/control-plane";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type IntegrationGrantValue = {
  enabled?: boolean;
  approval_mode?: string;
  allow_actions?: string[];
  deny_actions?: string[];
  secret_keys?: string[];
  shared_env_keys?: string[];
  allowed_domains?: string[];
  allowed_paths?: string[];
  allowed_db_envs?: string[];
  allow_private_network?: boolean;
  read_only_mode?: boolean;
};

export type AgentIntegrationEntry = {
  id: string; // "core:{key}" or "mcp:{serverKey}"
  key: string;
  connectionKey: string;
  kind: "core" | "mcp";
  category: string;
  label: string;
  tagline: string;
  description: string;
  logoKey: string;
  status: "connected" | "pending" | "disabled";
  accentFrom: string;
  accentTo: string;
  // Core-specific
  coreIntegration?: ControlPlaneCoreIntegration;
  coreConnection?: ControlPlaneAgentConnection | null;
  coreDefaultConnection?: ControlPlaneAgentConnection | null;
  coreGrant?: IntegrationGrantValue;
  // MCP-specific
  mcpServer?: McpServerCatalogEntry;
  mcpConnection?: McpAgentConnection | null;
  mcpTools?: McpDiscoveredTool[];
  mcpPolicies?: Record<string, McpToolPolicy>;
  mcpSummary?: ControlPlaneConnectionTools["summary"];
  mcpLastDiscoveredAt?: string | null;
  mcpDiff?: ControlPlaneConnectionTools["diff"];
  oauth_supported?: boolean;
  oauthStatus?: McpOAuthStatus;
  connectionProfile?: ConnectionProfile | null;
  runtimeConstraints?: RuntimeConstraintKey[];
};

type UseAgentIntegrationPermissionsParams = {
  agentId: string;
  coreIntegrations: ControlPlaneCoreIntegration[];
  integrationGrants: Record<string, IntegrationGrantValue>;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function deriveCoreStatus(
  integration: ControlPlaneCoreIntegration,
  grant: IntegrationGrantValue | undefined,
  connection: ControlPlaneAgentConnection | null,
): AgentIntegrationEntry["status"] {
  if (!grant?.enabled) return "disabled";
  if (connection) {
    if (connection.connected === false || connection.enabled === false) return "disabled";
    if (connection.status === "verified") return "connected";
    if (connection.status === "error" || connection.status === "configured") return "pending";
    if (connection.last_error) return "pending";
  }
  const connStatus =
    integration.connection_status ??
    integration.connection?.connection_status;
  if (connStatus === "verified") return "connected";
  if (
    connStatus === "configured" ||
    connStatus === "degraded" ||
    connStatus === "auth_expired"
  ) {
    return "pending";
  }
  return "connected";
}

function deriveMcpStatus(
  connection: ControlPlaneAgentConnection | null,
): AgentIntegrationEntry["status"] {
  if (!connection) return "disabled";
  if (connection.connected === false || connection.enabled === false) return "disabled";
  if (connection.status === "verified") return "connected";
  if (connection.status === "error" || connection.status === "configured") return "pending";
  if (connection.last_error) return "pending";
  return "connected";
}

function findCatalogEntry(key: string): IntegrationCatalogEntry | undefined {
  return INTEGRATION_CATALOG.find((e) => e.key === key);
}

function readBooleanFlag(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (value === 1) return true;
    if (value === 0) return false;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(normalized)) return true;
    if (["false", "0", "no", "off"].includes(normalized)) return false;
  }
  return undefined;
}

function resolveMcpOAuthSupport(
  catalogEntry: ControlPlaneConnectionCatalogEntry | null,
): boolean {
  const authCapabilities = catalogEntry?.auth_capabilities;
  if (authCapabilities && typeof authCapabilities === "object" && !Array.isArray(authCapabilities)) {
    const oauth = readBooleanFlag((authCapabilities as Record<string, unknown>).oauth);
    if (typeof oauth === "boolean") return oauth;
  }
  const strategy = String(catalogEntry?.auth_strategy_default || "").toLowerCase();
  const oauthMode = String(catalogEntry?.oauth_mode || "").toLowerCase();
  return strategy.includes("oauth") || oauthMode !== "" && oauthMode !== "none";
}

function toMcpServerCatalogEntry(
  item: ControlPlaneConnectionCatalogEntry,
): McpServerCatalogEntry {
  return {
    server_key: item.integration_key,
    display_name: item.display_name,
    description: item.description,
    transport_type:
      item.transport_kind === "remote" ? "http_sse" : "stdio",
    transport_kind: item.transport_kind ?? undefined,
    command: [],
    remote_url: item.remote_url,
    category: item.category,
    enabled: item.enabled ?? true,
    env_schema: item.env_schema ?? [],
    env_schema_json: JSON.stringify(item.env_schema ?? []),
    headers_schema: item.headers_schema ?? [],
    headers_schema_json: JSON.stringify(item.headers_schema ?? []),
    tool_discovery_mode: "runtime",
    official_support_level: item.official_support_level ?? null,
    auth_strategy: item.auth_strategy_default ?? null,
    oauth_enabled: resolveMcpOAuthSupport(item),
    oauth_mode: item.oauth_mode ?? null,
    vendor_notes: item.vendor_notes ?? null,
    default_policy: item.default_policy ?? null,
    auth_capabilities: item.auth_capabilities ?? null,
    documentation_url: item.documentation_url ?? null,
    logo_key: item.logo_key ?? null,
    metadata: item.metadata ?? undefined,
    metadata_json: JSON.stringify(item.metadata ?? {}),
  };
}

function toMcpAgentConnection(
  connection: ControlPlaneAgentConnection,
): McpAgentConnection {
  return {
    server_key: connection.integration_key,
    agent_id: connection.agent_id,
    enabled: connection.enabled ?? connection.connected,
    transport_override: connection.transport_override ?? null,
    command_override: connection.command_override ?? null,
    command_override_json: connection.command_override_json ?? null,
    url_override: connection.url_override ?? null,
    cached_tools_json: connection.cached_tools_json ?? undefined,
    cached_tools_at: connection.cached_tools_at ?? null,
    last_connected_at: connection.last_verified_at ?? null,
    last_error: connection.last_error ?? "",
    env_values: connection.env_values ?? {},
    auth_method:
      connection.auth_method === "oauth" ? "oauth" : "manual",
    metadata: connection.metadata ?? undefined,
    tool_count: connection.tool_count,
    created_at: connection.created_at,
    updated_at: connection.updated_at,
  };
}

function buildCoreEntries(
  integrations: ControlPlaneCoreIntegration[],
  grants: Record<string, IntegrationGrantValue>,
  connections: ControlPlaneAgentConnection[],
  defaults: ControlPlaneAgentConnection[],
): AgentIntegrationEntry[] {
  const connectionMap = new Map<string, ControlPlaneAgentConnection>();
  for (const connection of connections.filter((item) => item.kind === "core")) {
    connectionMap.set(connection.integration_key, connection);
  }
  const defaultConnectionMap = new Map<string, ControlPlaneAgentConnection>();
  for (const connection of defaults.filter((item) => item.kind === "core")) {
    defaultConnectionMap.set(connection.integration_key, connection);
  }
  return integrations.map((integration) => {
    const catalogEntry = findCatalogEntry(integration.id);
    const grant = grants[integration.id];
    const connection = connectionMap.get(integration.id) ?? null;
    const defaultConnection = defaultConnectionMap.get(integration.id) ?? null;
    const logoKey = catalogEntry?.logoKey ?? integration.id;
    const accent = getIntegrationAccent(logoKey);
    const baseConnection = integration.connection ?? {
      integration_id: integration.id,
      title: integration.title,
      description: integration.description,
      transport: integration.transport,
      auth_modes: integration.auth_modes,
      auth_mode: integration.auth_mode,
      configured: false,
      verified: false,
      fields: [],
      connection_status: integration.connection_status,
    };
    const mergedConnection = connection
      ? {
          ...baseConnection,
          integration_id: baseConnection.integration_id || integration.id,
          title: baseConnection.title || integration.title,
          description: baseConnection.description ?? integration.description,
          transport: baseConnection.transport ?? integration.transport,
          auth_modes: baseConnection.auth_modes ?? integration.auth_modes,
          auth_mode: connection.auth_method ?? baseConnection.auth_mode ?? integration.auth_mode,
          configured: connection.connected ?? baseConnection.configured ?? false,
          verified: connection.status === "verified",
          account_label: connection.account_label ?? baseConnection.account_label,
          last_verified_at: connection.last_verified_at ?? baseConnection.last_verified_at,
          last_error: connection.last_error ?? baseConnection.last_error,
          checked_via:
            typeof connection.metadata?.checked_via === "string"
              ? connection.metadata.checked_via
              : baseConnection.checked_via,
          auth_expired:
            typeof connection.metadata?.auth_expired === "boolean"
              ? connection.metadata.auth_expired
              : baseConnection.auth_expired,
          metadata: {
            ...(baseConnection.metadata ?? {}),
            ...(connection.metadata ?? {}),
          },
          fields:
            connection.fields ??
            (Array.isArray(baseConnection.fields) ? baseConnection.fields : []),
          health_probe:
            baseConnection.health_probe ??
            (typeof connection.metadata?.health_probe === "string"
              ? connection.metadata.health_probe
              : undefined),
          supports_persistence:
            baseConnection.supports_persistence ?? integration.supports_persistence,
          connection_status: connection.status || baseConnection.connection_status,
        }
      : baseConnection;
    const mergedIntegration = connection
      ? {
          ...integration,
          auth_mode: connection.auth_method ?? integration.auth_mode,
          connection_status: connection.status || integration.connection_status,
          connection: mergedConnection,
        }
      : integration;

    return {
      id: `core:${integration.id}`,
      key: integration.id,
      connectionKey: `core:${integration.id}`,
      kind: "core",
      category: String((catalogEntry as { category?: string } | undefined)?.category || "general"),
      label: catalogEntry?.label ?? integration.title,
      tagline: catalogEntry?.tagline ?? (integration.description || ""),
      description: catalogEntry?.description ?? (integration.description || ""),
      logoKey,
      status: deriveCoreStatus(integration, grant, connection),
      accentFrom: catalogEntry?.gradientFrom ?? accent.from,
      accentTo: catalogEntry?.gradientTo ?? accent.to,
      coreIntegration: mergedIntegration,
      coreConnection: connection,
      coreDefaultConnection: defaultConnection,
      coreGrant: grant,
      connectionProfile: (integration.connection_profile as ConnectionProfile | undefined) ?? null,
      runtimeConstraints: (integration.runtime_constraints as RuntimeConstraintKey[] | undefined) ?? undefined,
    };
  });
}

function buildMcpEntries(
  catalogItems: ControlPlaneConnectionCatalogEntry[],
  connections: ControlPlaneAgentConnection[],
): AgentIntegrationEntry[] {
  const mcpCatalogItems = catalogItems.filter((item) => item.kind === "mcp");
  const connectionMap = new Map<string, ControlPlaneAgentConnection>();
  for (const conn of connections.filter((item) => item.kind === "mcp")) {
    connectionMap.set(conn.integration_key, conn);
  }
  const catalogByKey = new Map(
    mcpCatalogItems.map((item) => [item.integration_key, item] as const),
  );
  const allKeys = new Set<string>();
  for (const item of mcpCatalogItems) allKeys.add(item.integration_key);
  for (const conn of connections.filter((item) => item.kind === "mcp")) allKeys.add(conn.integration_key);

  const entries: AgentIntegrationEntry[] = [];

  for (const serverKey of allKeys) {
    const catalogItem = catalogByKey.get(serverKey) ?? null;
    const server = catalogItem ? toMcpServerCatalogEntry(catalogItem) : null;
    const connection = connectionMap.get(serverKey) ?? null;
    const legacyConnection = connection ? toMcpAgentConnection(connection) : null;
    const logoKey = server?.logo_key ?? "mcp";
    const accent = getIntegrationAccent(logoKey);
    const label = catalogItem?.display_name ?? server?.display_name ?? serverKey;
    const tagline = catalogItem?.vendor_notes || server?.description || "Servidor MCP";
    const description = catalogItem?.description ?? server?.description ?? "";
    const connectionKey = connection?.connection_key ?? `mcp:${serverKey}`;

    const catalogMetadata =
      (catalogItem?.metadata as Record<string, unknown> | undefined) ?? {};
    const profileFromCatalog =
      (catalogItem?.connection_profile as ConnectionProfile | null | undefined) ??
      (catalogMetadata.connection_profile as ConnectionProfile | undefined) ??
      null;
    const constraintsFromCatalog =
      (catalogItem?.runtime_constraints as RuntimeConstraintKey[] | undefined) ??
      (catalogMetadata.runtime_constraints as RuntimeConstraintKey[] | undefined);

    entries.push({
      id: `mcp:${serverKey}`,
      key: serverKey,
      connectionKey,
      kind: "mcp",
      category: catalogItem?.category ?? "general",
      label,
      tagline,
      description,
      logoKey,
      status: deriveMcpStatus(connection),
      accentFrom: accent.from,
      accentTo: accent.to,
      mcpServer: server ?? undefined,
      mcpConnection: legacyConnection,
      oauth_supported: resolveMcpOAuthSupport(catalogItem),
      connectionProfile: profileFromCatalog,
      runtimeConstraints: constraintsFromCatalog,
    });
  }

  return entries;
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

export function useAgentIntegrationPermissions({
  agentId,
  coreIntegrations,
  integrationGrants,
}: UseAgentIntegrationPermissionsParams) {
  const [entries, setEntries] = useState<AgentIntegrationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);

  /* ---- Build entries on mount / when dependencies change ---------- */

  const fetchMcpData = useCallback(async () => {
    setLoading(true);
    try {
      const [catalog, connections, defaults] = await Promise.all([
        requestJson<{ items: ControlPlaneConnectionCatalogEntry[] }>(
          "/api/control-plane/connections/catalog",
        ),
        requestJson<{ items: ControlPlaneAgentConnection[] }>(
          `/api/control-plane/agents/${agentId}/connections`,
        ),
        requestJson<{ items: ControlPlaneAgentConnection[] }>(
          "/api/control-plane/connections/defaults",
        ),
      ]);

      const coreEntries = buildCoreEntries(
        coreIntegrations,
        integrationGrants,
        connections.items ?? [],
        defaults.items ?? [],
      );
      const mcpEntries = buildMcpEntries(catalog.items ?? [], connections.items ?? []);

      setEntries([...coreEntries, ...mcpEntries]);
    } catch {
      // On error, still show core entries
      const coreEntries = buildCoreEntries(
        coreIntegrations,
        integrationGrants,
        [],
        [],
      );
      setEntries(coreEntries);
    } finally {
      setLoading(false);
    }
  }, [agentId, coreIntegrations, integrationGrants]);

  useEffect(() => {
    fetchMcpData();
  }, [fetchMcpData]);

  // Keep core entries in sync when grants change without re-fetching MCP
  useEffect(() => {
    setEntries((prev) =>
      prev.map((entry) => {
        if (entry.kind !== "core") return entry;
        const grant = integrationGrants[entry.key];
        const integration = coreIntegrations.find(
          (i) => i.id === entry.key,
        );
        if (!integration) return entry;
        return {
          ...entry,
          coreGrant: grant,
          status: deriveCoreStatus(integration, grant, entry.coreConnection ?? null),
        };
      }),
    );
  }, [integrationGrants, coreIntegrations]);

  /* ---- Selected entry --------------------------------------------- */

  const selectedEntry = useMemo(
    () => entries.find((e) => e.id === selectedId) ?? null,
    [entries, selectedId],
  );

  /* ---- Lazy tool loading on detail open --------------------------- */

  const selectEntry = useCallback(
    async (id: string | null) => {
      setSelectedId(id);

      if (!id) return;

      const entry = entries.find((e) => e.id === id);
      if (!entry || entry.kind !== "mcp") return;
      if (entry.mcpTools) return;

      // Fetch OAuth status for connected MCP servers
      let oauthStatus: McpOAuthStatus | undefined;
      if (entry.mcpConnection) {
        try {
          oauthStatus = await requestJson<McpOAuthStatus>(
            `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/oauth/status`,
          );
        } catch {
          /* OAuth status is optional */
        }
      }

      let toolsPayload: ControlPlaneConnectionTools | null = null;
      try {
        toolsPayload = await requestJson<ControlPlaneConnectionTools>(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/tools`,
        );
      } catch {
        toolsPayload = null;
      }

      setEntries((prev) =>
        prev.map((e) =>
          e.id === id
            ? {
                ...e,
                mcpTools: toolsPayload?.tools ?? [],
                mcpPolicies: toolsPayload?.policies ?? {},
                mcpSummary: toolsPayload?.summary,
                mcpLastDiscoveredAt: toolsPayload?.last_discovered_at ?? null,
                mcpDiff: toolsPayload?.diff,
                oauthStatus,
              }
            : e,
        ),
      );
    },
    [agentId, entries],
  );

  /* ---- MCP actions ------------------------------------------------ */

  const discoverTools = useCallback(
    async (serverKey: string) => {
      setIsDiscovering(true);
      try {
        const entry = entries.find((item) => item.kind === "mcp" && item.key === serverKey);
        if (!entry) return;
        const result = await requestJson<ControlPlaneConnectionTools & { success?: boolean }>(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/discover-tools`,
          { method: "POST" },
        );
        setEntries((prev) =>
          prev.map((e) =>
            e.key === serverKey && e.kind === "mcp"
              ? {
                  ...e,
                  mcpTools: result.tools ?? [],
                  mcpPolicies: result.policies ?? e.mcpPolicies,
                  mcpSummary: result.summary ?? e.mcpSummary,
                  mcpLastDiscoveredAt: result.last_discovered_at ?? null,
                  mcpDiff: result.diff ?? e.mcpDiff,
                }
              : e,
          ),
        );
      } finally {
        setIsDiscovering(false);
      }
    },
    [agentId, entries],
  );

  const disconnectMcp = useCallback(
    async (serverKey: string) => {
      const entry = entries.find((item) => item.kind === "mcp" && item.key === serverKey);
      if (!entry) return;
      await requestJson(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}`,
        { method: "DELETE" },
      );
      // Refresh all data
      await fetchMcpData();
      setSelectedId(null);
    },
    [agentId, entries, fetchMcpData],
  );

  const updateMcpToolPolicy = useCallback(
    async (
      serverKey: string,
      toolName: string,
      policy: McpToolPolicy,
    ) => {
      const entry = entries.find((item) => item.kind === "mcp" && item.key === serverKey);
      if (!entry) return;
      // Capture previous state for rollback
      const prevEntries = entries;

      // Optimistic update
      setEntries((prev) =>
        prev.map((e) =>
          e.key === serverKey && e.kind === "mcp"
            ? {
                ...e,
                mcpPolicies: {
                  ...e.mcpPolicies,
                  [toolName]: policy,
                },
              }
            : e,
        ),
      );

      try {
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/policies/${encodeURIComponent(toolName)}`,
          { method: "PUT", body: JSON.stringify({ policy }) },
        );
      } catch {
        // Revert on error
        setEntries(prevEntries);
      }
    },
    [agentId, entries],
  );

  /* ---- Core action (callback, delegates to parent) ---------------- */

  const toggleCoreIntegration: (integrationId: string, enabled: boolean) => void = useCallback(
    () => {
      // This is a no-op here. The parent (tab-escopo) handles this via
      // its own handleIntegrationToggle that updates the draft state.
      // This stub exists to satisfy the hook interface; the detail view
      // should call the parent handler directly through onToggleEnabled.
    },
    [],
  );

  return {
    entries,
    loading,
    selectedEntry,
    selectEntry,
    discoverTools,
    disconnectMcp,
    updateMcpToolPolicy,
    isDiscovering,
    toggleCoreIntegration,
    refreshData: fetchMcpData,
  };
}
