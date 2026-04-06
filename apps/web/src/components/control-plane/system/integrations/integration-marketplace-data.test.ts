import { describe, expect, it } from "vitest";
import type { McpServerCatalogEntry } from "@/lib/control-plane";
import { MCP_SUGGESTED_SERVERS } from "@/components/control-plane/system/mcp/mcp-catalog-data";
import {
  buildUnifiedIntegrationEntries,
  filterUnifiedIntegrationEntries,
  groupUnifiedIntegrationEntries,
} from "./integration-marketplace-data";

type CoreDefaultConnection = {
  kind: "core";
  integration_key: string;
  status: string;
};

function makeCatalogServer(
  overrides: Partial<McpServerCatalogEntry> & Pick<McpServerCatalogEntry, "server_key" | "display_name">,
): McpServerCatalogEntry {
  return {
    server_key: overrides.server_key,
    display_name: overrides.display_name,
    description: overrides.description ?? "",
    transport_type: overrides.transport_type ?? "stdio",
    command_json: overrides.command_json ?? '["npx","-y","example-mcp"]',
    url: overrides.url ?? null,
    env_schema_json: overrides.env_schema_json ?? "[]",
    documentation_url: overrides.documentation_url ?? null,
    logo_key: overrides.logo_key ?? null,
    category: overrides.category ?? "general",
    enabled: overrides.enabled ?? true,
    metadata_json: overrides.metadata_json ?? "{}",
    created_at: overrides.created_at ?? "",
    updated_at: overrides.updated_at ?? "",
  };
}

function buildEntries({
  integrations = {},
  coreDefaults = [],
  mcpCatalog = [],
}: {
  integrations?: Record<string, boolean>;
  coreDefaults?: CoreDefaultConnection[];
  mcpCatalog?: McpServerCatalogEntry[];
}) {
  const legacyConnectionMap = Object.fromEntries(
    coreDefaults.map((connection) => [
      connection.integration_key,
      { connection_status: connection.status },
    ]),
  );

  return buildUnifiedIntegrationEntries({
    integrations,
    mcpCatalog,
    integrationConnections: legacyConnectionMap,
  } as Parameters<typeof buildUnifiedIntegrationEntries>[0]);
}

describe("integration marketplace data", () => {
  it("merges curated MCP definitions with persisted catalog state and keeps custom servers generic", () => {
    const slackSuggested = MCP_SUGGESTED_SERVERS.find(
      (server) => server.server_key === "slack",
    );
    expect(slackSuggested).toBeTruthy();

    const entries = buildEntries({
      integrations: { browser_enabled: true },
      mcpCatalog: [
        makeCatalogServer({
          server_key: "slack",
          display_name: "Slack Override",
          description: "Persisted server description",
          documentation_url: "https://internal.example/slack",
          logo_key: null,
          category: "data",
          enabled: false,
        }),
        makeCatalogServer({
          server_key: "custom-docs",
          display_name: "Custom Docs",
          description: "Knowledge bridge",
          transport_type: "http_sse",
          url: "https://docs.example.com/sse",
          command_json: "[]",
          documentation_url: "https://docs.example.com",
          logo_key: null,
          enabled: true,
        }),
      ],
    });

    const slack = entries.find((entry) => entry.id === "mcp:slack");
    const custom = entries.find((entry) => entry.id === "mcp:custom-docs");
    const notion = entries.find((entry) => entry.id === "mcp:notion");

    expect(slack).toMatchObject({
      kind: "mcp",
      label: slackSuggested?.display_name,
      tagline: slackSuggested?.tagline,
      logoKey: slackSuggested?.logo_key,
      status: "pending",
      metadata: {
        documentationUrl: slackSuggested?.documentation_url,
        origin: "curated",
        type: "MCP",
      },
      mcp: {
        origin: "curated",
        isCataloged: true,
        canAdd: false,
        canEdit: true,
        canRemove: false,
      },
    });

    expect(custom).toMatchObject({
      kind: "mcp",
      label: "Custom Docs",
      tagline: "Servidor MCP custom",
      logoKey: "mcp",
      status: "connected",
      metadata: {
        origin: "custom",
        transport: "HTTP / SSE",
        type: "MCP",
      },
      mcp: {
        origin: "custom",
        canEdit: true,
        canRemove: true,
      },
    });

    expect(notion).toMatchObject({
      kind: "mcp",
      status: "disabled",
      mcp: {
        canAdd: true,
        isCataloged: false,
      },
    });
  });

  it("filters reserved MCP server keys and keeps postgres only as curated MCP", () => {
    const entries = buildEntries({
      integrations: {},
      mcpCatalog: [
        makeCatalogServer({
          server_key: "filesystem",
          display_name: "Filesystem",
          enabled: true,
        }),
        makeCatalogServer({
          server_key: "postgres_mcp",
          display_name: "PostgreSQL (MCP)",
          enabled: false,
        }),
        makeCatalogServer({
          server_key: "custom-docs",
          display_name: "Custom Docs",
          enabled: true,
        }),
      ],
    });

    expect(entries.some((entry) => entry.key === "postgres")).toBe(false);
    expect(entries.some((entry) => entry.key === "filesystem")).toBe(false);

    const postgresMcp = entries.find((entry) => entry.key === "postgres_mcp");
    expect(postgresMcp).toBeTruthy();
    expect(postgresMcp).toMatchObject({
      kind: "mcp",
      mcp: {
        origin: "curated",
        canEdit: true,
        canAdd: false,
      },
    });

    expect(entries.some((entry) => entry.key === "custom-docs")).toBe(true);
  });

  it("filters and groups unified entries across core and MCP entries", () => {
    const entries = buildEntries({
      integrations: { browser_enabled: true },
      coreDefaults: [
        {
          kind: "core",
          integration_key: "browser",
          status: "verified",
        },
      ],
      mcpCatalog: [
        makeCatalogServer({
          server_key: "custom-docs",
          display_name: "Custom Docs",
          description: "Knowledge bridge",
          enabled: true,
        }),
      ],
    });

    const filtered = filterUnifiedIntegrationEntries(entries, {
      category: "all",
      search: "custom docs",
    });
    const grouped = groupUnifiedIntegrationEntries(filtered);

    expect(filtered.map((entry) => entry.id)).toEqual(["mcp:custom-docs"]);
    expect(grouped).toHaveLength(1);
    expect(grouped[0]?.category).toBe("general");
    expect(grouped[0]?.entries[0]?.label).toBe("Custom Docs");
    expect(entries.find((entry) => entry.id === "core:browser")?.status).toBe("connected");
  });
});
