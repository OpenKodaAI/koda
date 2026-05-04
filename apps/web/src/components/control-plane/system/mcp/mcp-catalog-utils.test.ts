import { describe, expect, it } from "vitest";
import {
  buildSuggestedMcpCatalogEntry,
  filterAllowedMcpCatalogEntries,
  isReservedMcpServerKey,
  MCP_CATEGORY_KEYS,
  MCP_CATEGORY_LABELS,
  MCP_RESERVED_SERVER_KEYS,
  normalizeMcpServerKey,
  projectApiCatalogEntry,
  type McpSuggestedServer,
} from "./mcp-catalog-utils";

describe("MCP catalog utilities", () => {
  it("marks redundant native-duplicate server keys as reserved", () => {
    for (const key of MCP_RESERVED_SERVER_KEYS) {
      expect(isReservedMcpServerKey(key)).toBe(true);
      expect(isReservedMcpServerKey(` ${key.toUpperCase()} `)).toBe(true);
    }
  });

  it("filters reserved server keys from persisted MCP catalog rows", () => {
    const filtered = filterAllowedMcpCatalogEntries([
      { server_key: "filesystem" },
      { server_key: "custom-docs" },
      { server_key: "memory" },
      { server_key: "postgres_mcp" },
    ]);

    expect(filtered.map((entry) => entry.server_key)).toEqual([
      "custom-docs",
      "postgres_mcp",
    ]);
  });

  it("normalizes server keys with whitespace and case", () => {
    expect(normalizeMcpServerKey("  Custom-Docs ")).toBe("custom-docs");
    expect(normalizeMcpServerKey("FILESYSTEM")).toBe("filesystem");
  });

  it("exposes a translation key for every category label", () => {
    for (const category of Object.keys(MCP_CATEGORY_LABELS)) {
      expect(MCP_CATEGORY_KEYS[category as keyof typeof MCP_CATEGORY_KEYS]).toMatch(
        /^mcp\.category\./,
      );
    }
  });

  it("projects API catalog rows into the suggested-server shape", () => {
    const apiRow = {
      kind: "mcp",
      integration_key: "supabase",
      display_name: "Supabase",
      tagline: "Banco, auth e edge functions",
      description: "Supabase MCP",
      transport_type: "http_sse",
      command_template: ["npx", "-y", "mcp-remote@0.1.38", "https://mcp.supabase.com/mcp"],
      env_schema: [
        { key: "SUPABASE_ACCESS_TOKEN", label: "PAT", required: false, input_type: "password" },
      ],
      category: "cloud",
      logo_key: "supabase",
      documentation_url: "https://supabase.com/docs",
      oauth_supported: true,
      connection_profile: { strategy: "oauth_preferred", fields: [] },
      runtime_constraints: ["read_only_mode"],
      remote_url: "https://mcp.supabase.com/mcp",
      expected_tools: [
        { name: "list_tables", description: "List tables", read_only_hint: true },
      ],
      i18n_keys: {
        display_name: "mcp.supabase.display_name",
        tagline: "mcp.supabase.tagline",
        description: "mcp.supabase.description",
      },
    };

    const projected = projectApiCatalogEntry(apiRow);

    expect(projected).toMatchObject({
      server_key: "supabase",
      display_name: "Supabase",
      tagline: "Banco, auth e edge functions",
      transport_type: "http_sse",
      category: "cloud",
      oauth_supported: true,
      logo_key: "supabase",
      remote_url: "https://mcp.supabase.com/mcp",
    });
    expect(projected.command_template).toEqual([
      "npx",
      "-y",
      "mcp-remote@0.1.38",
      "https://mcp.supabase.com/mcp",
    ]);
    expect(projected.env_fields).toEqual([
      { key: "SUPABASE_ACCESS_TOKEN", label: "PAT", required: false },
    ]);
    expect(projected.expected_tools).toHaveLength(1);
    expect(projected.runtime_constraints).toEqual(["read_only_mode"]);
    expect(projected.i18n_keys?.display_name).toBe("mcp.supabase.display_name");
  });

  it("preserves curated logo keys when creating a suggested catalog entry", () => {
    const suggested: McpSuggestedServer = {
      server_key: "notion",
      display_name: "Notion",
      tagline: "Páginas, databases e blocks",
      description: "Notion fixture.",
      transport_type: "stdio",
      command_template: ["npx", "-y", "@modelcontextprotocol/server-notion"],
      env_fields: [],
      category: "productivity",
      logo_key: "notion",
      expected_tools: [
        { name: "list_pages", description: "Listar páginas", read_only_hint: true },
      ],
    };

    const entry = buildSuggestedMcpCatalogEntry(suggested);

    expect(entry.logo_key).toBe("notion");
    expect(entry.transport_type).toBe("stdio");
    expect(entry.enabled).toBe(true);
  });
});
