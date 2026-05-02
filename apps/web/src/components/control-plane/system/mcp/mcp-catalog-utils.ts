/* ------------------------------------------------------------------ */
/*  MCP catalog – pure utility helpers                                 */
/*                                                                    */
/*  The catalog data itself is fetched from the backend via            */
/*  `useMcpCatalogSuggestions`. This module only exports static        */
/*  utilities (category labels, reserved keys, normalization) plus the */
/*  TypeScript types that mirror the API response shape.               */
/* ------------------------------------------------------------------ */

import type {
  ConnectionProfile,
  McpServerCatalogEntry,
  RuntimeConstraintKey,
} from "@/lib/control-plane";

export type McpCategory = "general" | "development" | "productivity" | "data" | "cloud";

/**
 * Default category labels for SSR / no-i18n contexts. The backend also
 * returns translation keys so consumers should prefer i18n where possible.
 */
export const MCP_CATEGORY_LABELS: Record<McpCategory, string> = {
  general: "Geral",
  development: "Desenvolvimento",
  productivity: "Produtividade",
  data: "Dados",
  cloud: "Cloud",
};

export const MCP_CATEGORY_KEYS: Record<McpCategory, string> = {
  general: "mcp.category.general",
  development: "mcp.category.development",
  productivity: "mcp.category.productivity",
  data: "mcp.category.data",
  cloud: "mcp.category.cloud",
};

export type McpSuggestedEnvField = {
  key: string;
  label: string;
  required: boolean;
};

export type McpExpectedTool = {
  name: string;
  description: string;
  read_only_hint?: boolean | null;
  destructive_hint?: boolean | null;
};

export type McpI18nKeys = {
  display_name?: string | null;
  tagline?: string | null;
  description?: string | null;
  vendor_notes?: string | null;
};

export type McpSuggestedServer = {
  server_key: string;
  display_name: string;
  description: string;
  tagline: string;
  transport_type: "stdio" | "http_sse";
  command_template: string[];
  env_fields: McpSuggestedEnvField[];
  category: McpCategory;
  documentation_url?: string;
  logo_key?: string;
  expected_tools: McpExpectedTool[];
  oauth_supported?: boolean;
  connection_profile?: ConnectionProfile;
  runtime_constraints?: RuntimeConstraintKey[];
  remote_url?: string;
  i18n_keys?: McpI18nKeys;
};

/**
 * Server keys that Koda already supports natively and should never be
 * treated as a custom MCP server. Mirrors the backend reserved set.
 */
export const MCP_RESERVED_SERVER_KEYS = new Set([
  "docker",
  "filesystem",
  "github",
  "gitlab",
  "memory",
  "puppeteer",
]);

export function normalizeMcpServerKey(serverKey: string) {
  return serverKey.trim().toLowerCase();
}

export function isReservedMcpServerKey(serverKey: string) {
  return MCP_RESERVED_SERVER_KEYS.has(normalizeMcpServerKey(serverKey));
}

export function filterAllowedMcpCatalogEntries<T extends { server_key: string }>(
  entries: T[],
) {
  return entries.filter((entry) => !isReservedMcpServerKey(entry.server_key));
}

/**
 * Project a backend catalog row (the shape returned by
 * /api/control-plane/connections/catalog filtered to kind="mcp") into the
 * McpSuggestedServer shape consumed across the UI.
 *
 * Lives next to the types so both the hook and the SSR fallback build go
 * through the exact same projection.
 */
export function projectApiCatalogEntry(item: Record<string, unknown>): McpSuggestedServer {
  const envSchema = (item.env_schema as Array<Record<string, unknown>>) ?? [];
  return {
    server_key: String(item.integration_key ?? item.server_key ?? ""),
    display_name: String(item.display_name ?? ""),
    description: String(item.description ?? ""),
    tagline: String(item.tagline ?? ""),
    transport_type: (item.transport_type as "stdio" | "http_sse") ?? "stdio",
    command_template: (item.command_template as string[]) ?? [],
    env_fields: envSchema.map((field) => ({
      key: String(field.key ?? ""),
      label: String(field.label ?? field.key ?? ""),
      required: Boolean(field.required),
    })),
    category: ((item.category as McpCategory) ?? "general") as McpCategory,
    documentation_url: (item.documentation_url as string) ?? undefined,
    logo_key: (item.logo_key as string) ?? undefined,
    expected_tools: (item.expected_tools as McpExpectedTool[]) ?? [],
    oauth_supported: Boolean(item.oauth_supported),
    connection_profile: (item.connection_profile as ConnectionProfile) ?? undefined,
    runtime_constraints: (item.runtime_constraints as RuntimeConstraintKey[]) ?? undefined,
    remote_url: (item.remote_url as string) ?? undefined,
    i18n_keys: (item.i18n_keys as McpI18nKeys) ?? undefined,
  };
}

/**
 * Build a `McpServerCatalogEntry` from a fetched suggestion so existing
 * consumers that expect the persisted-row shape (e.g. when adding a new
 * server) keep working without changes.
 */
export function buildSuggestedMcpCatalogEntry(
  suggested: McpSuggestedServer,
): McpServerCatalogEntry {
  const metadata: Record<string, unknown> = {};
  if (suggested.connection_profile) {
    metadata.connection_profile = suggested.connection_profile;
  }
  if (suggested.runtime_constraints) {
    metadata.runtime_constraints = suggested.runtime_constraints;
  }
  if (suggested.remote_url) {
    metadata.remote_url = suggested.remote_url;
  }
  return {
    server_key: suggested.server_key,
    display_name: suggested.display_name,
    description: suggested.description,
    transport_type: suggested.transport_type,
    command_json: JSON.stringify(suggested.command_template),
    url: suggested.remote_url ?? null,
    env_schema_json: JSON.stringify(
      suggested.env_fields.map((field) => ({
        key: field.key,
        label: field.label,
        required: field.required,
        input_type: "password",
      })),
    ),
    documentation_url: suggested.documentation_url ?? null,
    logo_key: suggested.logo_key ?? null,
    category: suggested.category,
    enabled: true,
    metadata_json: JSON.stringify(metadata),
    connection_profile: suggested.connection_profile ?? null,
    runtime_constraints: suggested.runtime_constraints ?? undefined,
    created_at: "",
    updated_at: "",
  };
}
