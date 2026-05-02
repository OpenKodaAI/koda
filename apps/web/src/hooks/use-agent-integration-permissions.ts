"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  ControlPlaneConnectionCapabilities,
  ControlPlaneConnectionCatalogEntry,
  ControlPlaneConnectionTools,
  McpAgentConnection,
  McpCapabilityKind,
  McpCapabilityPolicies,
  McpCapabilityPolicy,
  McpClaudeDesktopImportResult,
  McpCustomServerEntry,
  McpDiscoveredPrompt,
  McpDiscoveredResource,
  McpDiscoveredTool,
  McpOAuthStatus,
  McpResourceTemplate,
  McpServerCatalogEntry,
  McpServerInfo,
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
  status: "connected" | "pending" | "disabled" | "needs_reauth";
  accentFrom: string;
  accentTo: string;
  isCustom?: boolean;
  customScope?: "system" | "agent";
  customSource?: "manual" | "claude_desktop_json" | string;
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
  mcpResources?: McpDiscoveredResource[];
  mcpResourceTemplates?: McpResourceTemplate[];
  mcpResourcePolicies?: Record<string, McpCapabilityPolicy>;
  mcpResourceExposureModes?: Record<string, "context" | "tool" | "auto" | undefined>;
  mcpPrompts?: McpDiscoveredPrompt[];
  mcpPromptPolicies?: Record<string, McpCapabilityPolicy>;
  mcpServerInfo?: McpServerInfo;
  mcpServerCapabilities?: Record<string, unknown>;
  mcpProtocolVersion?: string | null;
  mcpSummary?: ControlPlaneConnectionTools["summary"];
  mcpCapabilitySummary?: ControlPlaneConnectionCapabilities["summary"];
  mcpLastDiscoveredAt?: string | null;
  mcpDiff?: ControlPlaneConnectionTools["diff"];
  mcpDiscoveryError?: string | null;
  oauth_supported?: boolean;
  oauthStatus?: McpOAuthStatus;
  connectionProfile?: ConnectionProfile | null;
  runtimeConstraints?: RuntimeConstraintKey[];
};

export type ImportClaudeDesktopMcpInput = {
  payload: { mcpServers?: Record<string, unknown> } | Record<string, unknown>;
  agentId?: string | null;
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
  oauthStatus?: McpOAuthStatus,
): AgentIntegrationEntry["status"] {
  if (!connection) return "disabled";
  if (connection.connected === false || connection.enabled === false) return "disabled";
  if (oauthStatus && oauthStatus.last_error && oauthStatus.last_error.toLowerCase().includes("auth")) {
    return "needs_reauth";
  }
  if (oauthStatus?.expires_at) {
    const expiresAt = new Date(oauthStatus.expires_at).getTime();
    if (!Number.isNaN(expiresAt) && expiresAt - Date.now() < 0) return "needs_reauth";
  }
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
  customServers: McpCustomServerEntry[] = [],
): AgentIntegrationEntry[] {
  const mcpCatalogItems = catalogItems.filter((item) => item.kind === "mcp");
  const connectionMap = new Map<string, ControlPlaneAgentConnection>();
  for (const conn of connections.filter((item) => item.kind === "mcp")) {
    connectionMap.set(conn.integration_key, conn);
  }
  const catalogByKey = new Map(
    mcpCatalogItems.map((item) => [item.integration_key, item] as const),
  );
  const customByKey = new Map(customServers.map((entry) => [entry.server_key, entry] as const));
  const allKeys = new Set<string>();
  for (const item of mcpCatalogItems) allKeys.add(item.integration_key);
  for (const conn of connections.filter((item) => item.kind === "mcp")) allKeys.add(conn.integration_key);
  for (const custom of customServers) allKeys.add(custom.server_key);

  const entries: AgentIntegrationEntry[] = [];

  for (const serverKey of allKeys) {
    const catalogItem = catalogByKey.get(serverKey) ?? null;
    const customEntry = customByKey.get(serverKey) ?? null;
    const server = catalogItem ? toMcpServerCatalogEntry(catalogItem) : null;
    const connection = connectionMap.get(serverKey) ?? null;
    const legacyConnection = connection ? toMcpAgentConnection(connection) : null;
    const logoKey = customEntry ? "mcp" : (server?.logo_key ?? "mcp");
    const accent = getIntegrationAccent(logoKey);
    const label = customEntry?.display_name ?? catalogItem?.display_name ?? server?.display_name ?? serverKey;
    const tagline = customEntry
      ? customEntry.description || "Servidor MCP customizado"
      : catalogItem?.vendor_notes || server?.description || "Servidor MCP";
    const description = customEntry?.description ?? catalogItem?.description ?? server?.description ?? "";
    const connectionKey = connection?.connection_key ?? `mcp:${serverKey}`;

    const catalogMetadata =
      (catalogItem?.metadata as Record<string, unknown> | undefined) ?? {};
    const isCustomFromCatalog =
      Boolean((catalogMetadata as { is_custom?: unknown }).is_custom) ||
      Boolean((catalogItem as { is_custom?: unknown } | null | undefined)?.is_custom);
    const isCustom = Boolean(customEntry) || isCustomFromCatalog;
    const customScope = customEntry?.scope ?? (isCustomFromCatalog ? "system" : undefined);

    const profileFromCustom: ConnectionProfile | null = customEntry
      ? deriveCustomConnectionProfile(customEntry)
      : null;
    const profileFromCatalog =
      profileFromCustom ??
      (catalogItem?.connection_profile as ConnectionProfile | null | undefined) ??
      (catalogMetadata.connection_profile as ConnectionProfile | undefined) ??
      null;
    const constraintsFromCatalog =
      (customEntry?.runtime_constraints as RuntimeConstraintKey[] | undefined) ??
      (catalogItem?.runtime_constraints as RuntimeConstraintKey[] | undefined) ??
      (catalogMetadata.runtime_constraints as RuntimeConstraintKey[] | undefined);

    entries.push({
      id: `mcp:${serverKey}`,
      key: serverKey,
      connectionKey,
      kind: "mcp",
      category: customEntry ? "custom" : catalogItem?.category ?? "general",
      label,
      tagline,
      description,
      logoKey,
      status: deriveMcpStatus(connection),
      accentFrom: accent.from,
      accentTo: accent.to,
      isCustom,
      customScope,
      customSource: customEntry?.source,
      mcpServer: server ?? undefined,
      mcpConnection: legacyConnection,
      oauth_supported: customEntry
        ? customEntry.auth_strategy === "oauth"
        : resolveMcpOAuthSupport(catalogItem),
      connectionProfile: profileFromCatalog,
      runtimeConstraints: constraintsFromCatalog,
    });
  }

  return entries;
}

function buildToolPolicyMap(rows?: McpCapabilityPolicies["tools"]): Record<string, McpToolPolicy> {
  const result: Record<string, McpToolPolicy> = {};
  for (const row of rows ?? []) {
    result[row.capability_name] = row.policy as McpToolPolicy;
  }
  return result;
}

function buildPolicyMap(rows?: McpCapabilityPolicies["resources"] | McpCapabilityPolicies["prompts"]): Record<string, McpCapabilityPolicy> {
  const result: Record<string, McpCapabilityPolicy> = {};
  for (const row of rows ?? []) {
    result[row.capability_name] = row.policy;
  }
  return result;
}

function buildExposureModeMap(
  rows?: McpCapabilityPolicies["resources"],
): Record<string, "context" | "tool" | "auto" | undefined> {
  const result: Record<string, "context" | "tool" | "auto" | undefined> = {};
  for (const row of rows ?? []) {
    if (row.exposure_mode) result[row.capability_name] = row.exposure_mode;
  }
  return result;
}

function toAgentConnectionShape(entry: AgentIntegrationEntry): ControlPlaneAgentConnection | null {
  if (!entry.mcpConnection) return null;
  return {
    connection_key: entry.connectionKey,
    kind: "mcp",
    integration_key: entry.key,
    status: entry.status === "connected" ? "verified" : entry.status,
    transport_kind: entry.mcpConnection.transport_override ?? null,
    auth_method: entry.mcpConnection.auth_method ?? null,
    last_error: entry.mcpConnection.last_error ?? null,
    last_verified_at: entry.mcpConnection.last_connected_at ?? null,
    connected: entry.mcpConnection.enabled,
    enabled: entry.mcpConnection.enabled,
    server_key: entry.key,
  };
}

function deriveCustomConnectionProfile(entry: McpCustomServerEntry): ConnectionProfile {
  if (entry.transport_type === "http_sse") {
    return {
      strategy: entry.auth_strategy === "oauth" ? "oauth_preferred" : "custom_http",
      oauth_provider: entry.oauth_config?.oauth_provider ?? null,
      oauth_scopes: entry.oauth_config?.scopes ?? [],
      fields: entry.env_schema.map((field) => ({
        key: field.key,
        label: field.label,
        required: field.required,
        input_type: (field.input_type as ConnectionProfile["fields"] extends Array<infer F>
          ? F extends { input_type?: infer T }
            ? T
            : "text"
          : "text") ?? "password",
      })),
    };
  }
  return {
    strategy: entry.auth_strategy === "oauth" ? "oauth_preferred" : "custom_stdio",
    oauth_provider: entry.oauth_config?.oauth_provider ?? null,
    oauth_scopes: entry.oauth_config?.scopes ?? [],
    fields: entry.env_schema.map((field) => ({
      key: field.key,
      label: field.label,
      required: field.required,
      input_type: "password",
    })),
  };
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
  const [customServers, setCustomServers] = useState<McpCustomServerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);

  /* ---- Build entries on mount / when dependencies change ----------
   *
   * Callers commonly pass `coreIntegrations`/`integrationGrants` as new
   * references on every render (e.g. `core.integrations?.items ?? []`,
   * `policy.integration_grants ?? {}`). If those went into the useCallback
   * deps the fetch effect would re-fire on every parent render, calling
   * setLoading(true) → re-render → repeat — visible to the user as the
   * MCP screen "flickering". We mirror them into refs that are read at
   * fetch time, and gate the effect on `agentId` only.
   */
  const coreIntegrationsRef = useRef(coreIntegrations);
  const integrationGrantsRef = useRef(integrationGrants);
  useEffect(() => {
    coreIntegrationsRef.current = coreIntegrations;
  }, [coreIntegrations]);
  useEffect(() => {
    integrationGrantsRef.current = integrationGrants;
  }, [integrationGrants]);

  const fetchMcpData = useCallback(async () => {
    setLoading(true);
    try {
      const [catalog, connections, defaults, customResp] = await Promise.all([
        requestJson<{ items: ControlPlaneConnectionCatalogEntry[] }>(
          "/api/control-plane/connections/catalog",
        ),
        requestJson<{ items: ControlPlaneAgentConnection[] }>(
          `/api/control-plane/agents/${agentId}/connections`,
        ),
        requestJson<{ items: ControlPlaneAgentConnection[] }>(
          "/api/control-plane/connections/defaults",
        ),
        requestJson<{ servers: McpCustomServerEntry[] }>(
          `/api/control-plane/mcp/servers?agent_id=${encodeURIComponent(agentId)}`,
        ).catch(() => ({ servers: [] as McpCustomServerEntry[] })),
      ]);

      setCustomServers(customResp.servers ?? []);
      const coreEntries = buildCoreEntries(
        coreIntegrationsRef.current,
        integrationGrantsRef.current,
        connections.items ?? [],
        defaults.items ?? [],
      );
      const mcpEntries = buildMcpEntries(
        catalog.items ?? [],
        connections.items ?? [],
        customResp.servers ?? [],
      );

      setEntries([...coreEntries, ...mcpEntries]);
    } catch {
      // On error, still show core entries
      const coreEntries = buildCoreEntries(
        coreIntegrationsRef.current,
        integrationGrantsRef.current,
        [],
        [],
      );
      setEntries(coreEntries);
    } finally {
      setLoading(false);
    }
  }, [agentId]);

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

  /* ---- Lazy capability loading on detail open --------------------- */

  const selectEntry = useCallback(
    async (id: string | null) => {
      setSelectedId(id);

      if (!id) return;

      const entry = entries.find((e) => e.id === id);
      if (!entry || entry.kind !== "mcp") return;
      if (entry.mcpTools && entry.mcpResources && entry.mcpPrompts) return;

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

      // Try unified capabilities endpoint first; fall back to legacy tools
      // path for connections that have not been discovered yet.
      let capabilities: ControlPlaneConnectionCapabilities | null = null;
      try {
        capabilities = await requestJson<ControlPlaneConnectionCapabilities>(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/capabilities`,
        );
      } catch {
        capabilities = null;
      }

      let toolsPayload: ControlPlaneConnectionTools | null = null;
      if (capabilities === null) {
        try {
          toolsPayload = await requestJson<ControlPlaneConnectionTools>(
            `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/tools`,
          );
        } catch {
          toolsPayload = null;
        }
      }

      const policies = capabilities?.policies;
      const resourcePolicyMap = buildPolicyMap(policies?.resources);
      const exposureModeMap = buildExposureModeMap(policies?.resources);
      const promptPolicyMap = buildPolicyMap(policies?.prompts);

      setEntries((prev) =>
        prev.map((e) => {
          if (e.id !== id) return e;
          if (capabilities) {
            return {
              ...e,
              mcpTools: capabilities.tools ?? [],
              mcpPolicies: buildToolPolicyMap(policies?.tools),
              mcpResources: capabilities.resources ?? [],
              mcpResourceTemplates: capabilities.resource_templates ?? [],
              mcpResourcePolicies: resourcePolicyMap,
              mcpResourceExposureModes: exposureModeMap,
              mcpPrompts: capabilities.prompts ?? [],
              mcpPromptPolicies: promptPolicyMap,
              mcpServerInfo: capabilities.server_info,
              mcpServerCapabilities: capabilities.server_capabilities,
              mcpProtocolVersion: capabilities.protocol_version ?? null,
              mcpCapabilitySummary: capabilities.summary,
              mcpLastDiscoveredAt: capabilities.captured_at ?? null,
              mcpDiscoveryError: capabilities.error ?? null,
              oauthStatus,
              status: deriveMcpStatus(e.mcpConnection ? toAgentConnectionShape(e) : null, oauthStatus),
            };
          }
          return {
            ...e,
            mcpTools: toolsPayload?.tools ?? [],
            mcpPolicies: toolsPayload?.policies ?? {},
            mcpSummary: toolsPayload?.summary,
            mcpLastDiscoveredAt: toolsPayload?.last_discovered_at ?? null,
            mcpDiff: toolsPayload?.diff,
            oauthStatus,
            status: deriveMcpStatus(e.mcpConnection ? toAgentConnectionShape(e) : null, oauthStatus),
          };
        }),
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
        // Prefer the unified /capabilities/discover endpoint; fall back to
        // legacy /discover-tools for older deployments.
        let capabilities: ControlPlaneConnectionCapabilities | null = null;
        try {
          capabilities = await requestJson<ControlPlaneConnectionCapabilities>(
            `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/capabilities/discover`,
            { method: "POST" },
          );
        } catch {
          capabilities = null;
        }
        if (capabilities) {
          const policies = capabilities.policies;
          setEntries((prev) =>
            prev.map((e) =>
              e.key === serverKey && e.kind === "mcp"
                ? {
                    ...e,
                    mcpTools: capabilities!.tools ?? [],
                    mcpPolicies: buildToolPolicyMap(policies?.tools) || e.mcpPolicies,
                    mcpResources: capabilities!.resources ?? [],
                    mcpResourceTemplates: capabilities!.resource_templates ?? [],
                    mcpResourcePolicies: buildPolicyMap(policies?.resources),
                    mcpResourceExposureModes: buildExposureModeMap(policies?.resources),
                    mcpPrompts: capabilities!.prompts ?? [],
                    mcpPromptPolicies: buildPolicyMap(policies?.prompts),
                    mcpServerInfo: capabilities!.server_info,
                    mcpServerCapabilities: capabilities!.server_capabilities,
                    mcpProtocolVersion: capabilities!.protocol_version ?? null,
                    mcpCapabilitySummary: capabilities!.summary,
                    mcpLastDiscoveredAt: capabilities!.captured_at ?? null,
                    mcpDiscoveryError: capabilities!.error ?? null,
                  }
                : e,
            ),
          );
          return;
        }
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

  const discoverCapabilities = discoverTools;

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
        // Try the unified capability-policies endpoint first (Phase 1+).
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/capability-policies/tool/${encodeURIComponent(toolName)}`,
          { method: "PUT", body: JSON.stringify({ policy }) },
        );
      } catch {
        try {
          // Fallback: legacy tool-policies endpoint.
          await requestJson(
            `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/policies/${encodeURIComponent(toolName)}`,
            { method: "PUT", body: JSON.stringify({ policy }) },
          );
        } catch {
          // Revert on error
          setEntries(prevEntries);
        }
      }
    },
    [agentId, entries],
  );

  const updateMcpCapabilityPolicy = useCallback(
    async (
      serverKey: string,
      capabilityKind: McpCapabilityKind,
      capabilityName: string,
      policy: McpCapabilityPolicy,
      options?: { exposureMode?: "context" | "tool" | "auto" },
    ) => {
      const entry = entries.find((item) => item.kind === "mcp" && item.key === serverKey);
      if (!entry) return;
      const prevEntries = entries;
      setEntries((prev) =>
        prev.map((e) => {
          if (!(e.key === serverKey && e.kind === "mcp")) return e;
          if (capabilityKind === "tool") {
            return {
              ...e,
              mcpPolicies: { ...e.mcpPolicies, [capabilityName]: policy as McpToolPolicy },
            };
          }
          if (capabilityKind === "resource") {
            return {
              ...e,
              mcpResourcePolicies: { ...(e.mcpResourcePolicies ?? {}), [capabilityName]: policy },
              mcpResourceExposureModes: options?.exposureMode
                ? { ...(e.mcpResourceExposureModes ?? {}), [capabilityName]: options.exposureMode }
                : e.mcpResourceExposureModes,
            };
          }
          return {
            ...e,
            mcpPromptPolicies: { ...(e.mcpPromptPolicies ?? {}), [capabilityName]: policy },
          };
        }),
      );
      try {
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/capability-policies/${capabilityKind}/${encodeURIComponent(capabilityName)}`,
          {
            method: "PUT",
            body: JSON.stringify({
              policy,
              ...(options?.exposureMode ? { exposure_mode: options.exposureMode } : {}),
            }),
          },
        );
      } catch {
        setEntries(prevEntries);
      }
    },
    [agentId, entries],
  );

  /* ---- Custom MCP server CRUD ------------------------------------- */

  const addCustomMcpServer = useCallback(
    async (
      payload: Record<string, unknown>,
      options?: { agentScoped?: boolean },
    ) => {
      const body = {
        server: payload,
        agent_id: options?.agentScoped ? agentId : null,
      };
      const result = await requestJson<McpCustomServerEntry>(
        "/api/control-plane/mcp/servers",
        { method: "POST", body: JSON.stringify(body) },
      );
      await fetchMcpData();
      return result;
    },
    [agentId, fetchMcpData],
  );

  const importClaudeDesktopMcp = useCallback(
    async (
      raw: { mcpServers?: Record<string, unknown> } | Record<string, unknown>,
      options?: { agentScoped?: boolean },
    ) => {
      const body = {
        payload: raw,
        agent_id: options?.agentScoped ? agentId : null,
      };
      const result = await requestJson<McpClaudeDesktopImportResult>(
        "/api/control-plane/mcp/servers/import",
        { method: "POST", body: JSON.stringify(body) },
      );
      await fetchMcpData();
      return result;
    },
    [agentId, fetchMcpData],
  );

  const removeCustomMcpServer = useCallback(
    async (serverKey: string, options?: { agentScoped?: boolean }) => {
      const url = options?.agentScoped
        ? `/api/control-plane/mcp/servers/${encodeURIComponent(serverKey)}?agent_id=${encodeURIComponent(agentId)}`
        : `/api/control-plane/mcp/servers/${encodeURIComponent(serverKey)}`;
      await requestJson(url, { method: "DELETE" });
      await fetchMcpData();
    },
    [agentId, fetchMcpData],
  );

  const readMcpResource = useCallback(
    async (serverKey: string, uri: string) => {
      const entry = entries.find((item) => item.kind === "mcp" && item.key === serverKey);
      if (!entry) return null;
      return requestJson<{ success: boolean; uri: string; contents?: unknown[]; error?: string }>(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/resources/read`,
        { method: "POST", body: JSON.stringify({ uri }) },
      );
    },
    [agentId, entries],
  );

  const renderMcpPrompt = useCallback(
    async (serverKey: string, promptName: string, args?: Record<string, unknown>) => {
      const entry = entries.find((item) => item.kind === "mcp" && item.key === serverKey);
      if (!entry) return null;
      return requestJson<{
        success: boolean;
        prompt: string;
        description?: string;
        messages?: unknown[];
        error?: string;
      }>(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/prompts/${encodeURIComponent(promptName)}/render`,
        { method: "POST", body: JSON.stringify({ arguments: args ?? {} }) },
      );
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
    customServers,
    loading,
    selectedEntry,
    selectEntry,
    discoverTools,
    discoverCapabilities,
    disconnectMcp,
    updateMcpToolPolicy,
    updateMcpCapabilityPolicy,
    addCustomMcpServer,
    importClaudeDesktopMcp,
    removeCustomMcpServer,
    readMcpResource,
    renderMcpPrompt,
    isDiscovering,
    toggleCoreIntegration,
    refreshData: fetchMcpData,
  };
}
