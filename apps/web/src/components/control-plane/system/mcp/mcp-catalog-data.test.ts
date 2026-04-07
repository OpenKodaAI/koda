import { describe, expect, it } from "vitest";
import {
  filterAllowedMcpCatalogEntries,
  MCP_SUGGESTED_SERVERS,
  MCP_RESERVED_SERVER_KEYS,
  MCP_CATEGORY_LABELS,
  buildSuggestedMcpCatalogEntry,
  isReservedMcpServerKey,
  type McpCategory,
} from "./mcp-catalog-data";

const VALID_CATEGORIES = Object.keys(MCP_CATEGORY_LABELS) as McpCategory[];

describe("MCP catalog data", () => {
  it("contains the full curated MCP catalog", () => {
    expect(MCP_SUGGESTED_SERVERS).toHaveLength(19);
  });

  it("has no duplicate server_key values", () => {
    const keys = MCP_SUGGESTED_SERVERS.map((s) => s.server_key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("includes all required server_keys", () => {
    const keys = new Set(MCP_SUGGESTED_SERVERS.map((s) => s.server_key));
    const required = [
      "supabase",
      "stripe",
      "excalidraw",
      "vercel",
      "granola",
      "sentry",
      "linear",
      "brave_search",
      "slack",
      "notion",
      "cloudflare",
      "figma",
      "twilio",
      "postgres_mcp",
    ];
    for (const key of required) {
      expect(keys.has(key), `missing server_key: ${key}`).toBe(true);
    }
  });

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

  it("assigns valid categories to every entry", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      expect(
        VALID_CATEGORIES.includes(server.category),
        `${server.server_key} has invalid category: ${server.category}`,
      ).toBe(true);
    }
  });

  it("uses valid transport_type for every entry", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      expect(["stdio", "http_sse"]).toContain(server.transport_type);
    }
  });

  it("has non-empty expected_tools for every entry", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      expect(
        server.expected_tools.length,
        `${server.server_key} has no expected_tools`,
      ).toBeGreaterThan(0);
    }
  });

  it("has no duplicate tool names within each server", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      const toolNames = server.expected_tools.map((t) => t.name);
      expect(
        new Set(toolNames).size,
        `${server.server_key} has duplicate tool names`,
      ).toBe(toolNames.length);
    }
  });

  it("has non-empty tagline and description for every entry", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      expect(server.tagline.length, `${server.server_key} tagline empty`).toBeGreaterThan(0);
      expect(server.description.length, `${server.server_key} description empty`).toBeGreaterThan(0);
    }
  });

  it("uses valid npm package format in command_template", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      expect(
        server.command_template.length,
        `${server.server_key} has empty command_template`,
      ).toBeGreaterThan(0);
      // npx-based entries should start with npx -y
      if (server.command_template[0] === "npx") {
        expect(server.command_template[1]).toBe("-y");
        expect(
          server.command_template[2],
          `${server.server_key} missing package name`,
        ).toBeTruthy();
      }
    }
  });

  it("does not use floating @latest versions in curated command templates", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      expect(
        server.command_template.join(" "),
        `${server.server_key} should pin its MCP bootstrap dependency`,
      ).not.toContain("@latest");
    }
  });

  it("marks required env_fields correctly", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      for (const field of server.env_fields) {
        expect(field.key.length).toBeGreaterThan(0);
        expect(field.label.length).toBeGreaterThan(0);
        expect(typeof field.required).toBe("boolean");
      }
    }
  });

  it("each expected_tool has at least one hint set", () => {
    for (const server of MCP_SUGGESTED_SERVERS) {
      for (const tool of server.expected_tools) {
        const hasHint =
          tool.read_only_hint !== undefined || tool.destructive_hint !== undefined;
        expect(
          hasHint,
          `${server.server_key}.${tool.name} has no read_only_hint or destructive_hint`,
        ).toBe(true);
      }
    }
  });

  it("preserves curated logo keys when creating a suggested catalog entry", () => {
    const notion = MCP_SUGGESTED_SERVERS.find((server) => server.server_key === "notion");
    expect(notion).toBeTruthy();

    const entry = buildSuggestedMcpCatalogEntry(notion!);

    expect(entry.logo_key).toBe("notion");
  });
});
