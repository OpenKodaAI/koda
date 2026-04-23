import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IntegrationMarketplace } from "@/components/control-plane/system/integrations/integration-marketplace";

const { useSystemSettingsMock, requestJsonMock } = vi.hoisted(() => ({
  useSystemSettingsMock: vi.fn(),
  requestJsonMock: vi.fn(),
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
    t: (value: string) => value,
  }),
}));

vi.mock("@/hooks/use-system-settings", () => ({
  useSystemSettings: () => useSystemSettingsMock(),
}));

vi.mock("@/lib/http-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http-client")>(
    "@/lib/http-client",
  );

  return {
    ...actual,
    requestJson: requestJsonMock,
  };
});

vi.mock(
  "@/components/control-plane/system/integrations/provider-grid",
  () => ({
    ProviderGrid: () => <div>Provider Grid</div>,
  }),
);

vi.mock("@/components/control-plane/system/integrations/integration-logos", () => ({
  renderIntegrationLogo: () => null,
  getIntegrationAccent: () => ({ from: "#7C9CFF", to: "#5168D9" }),
}));

function makeCatalogServer(overrides: Record<string, unknown>) {
  return {
    server_key: "custom-docs",
    display_name: "Custom Docs",
    description: "Knowledge bridge",
    transport_type: "stdio",
    command_json: '["npx","-y","example"]',
    url: null,
    env_schema_json: "[]",
    documentation_url: null,
    logo_key: null,
    category: "general",
    enabled: true,
    metadata_json: "{}",
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

function makeSystemSettingsMock() {
  return {
    draft: {
      values: {
        resources: {
          integrations: {
            browser_enabled: true,
          },
        },
      },
    },
    connectionDefaults: [],
    integrationCatalog: [],
    integrationConnections: {},
    ensureIntegrationConnectionFresh: vi.fn().mockResolvedValue(null),
    connectIntegration: vi.fn(),
    disconnectIntegrationConnection: vi.fn(),
    isIntegrationActionPending: vi.fn(() => false),
    integrationActionStatus: vi.fn(() => "idle"),
  };
}

describe("IntegrationMarketplace", () => {
  beforeEach(() => {
    useSystemSettingsMock.mockReset();
    requestJsonMock.mockReset();
    useSystemSettingsMock.mockReturnValue(makeSystemSettingsMock());
    requestJsonMock.mockImplementation(async (path: string) => {
      if (path === "/api/control-plane/connections/defaults") {
        return {
          items: [
            {
              connection_key: "core:browser",
              kind: "core",
              integration_key: "browser",
              status: "verified",
              auth_method: "none",
              connected: true,
              enabled: true,
              metadata: {},
              fields: [],
            },
          ],
        };
      }

      if (path === "/api/control-plane/mcp/catalog") {
        return [
          makeCatalogServer({
            server_key: "filesystem",
            display_name: "Filesystem Persisted",
            category: "development",
            enabled: true,
          }),
          makeCatalogServer({
            server_key: "slack",
            display_name: "Slack Persisted",
            logo_key: "slack",
            category: "productivity",
            enabled: false,
          }),
          makeCatalogServer({
            server_key: "custom-docs",
            display_name: "Custom Docs",
            transport_type: "http_sse",
            url: "https://docs.example.com/sse",
            documentation_url: "https://docs.example.com",
            enabled: true,
          }),
        ];
      }

      throw new Error(`Unhandled request: ${path}`);
    });
  });

  it("renders a unified grid with core integrations, curated MCP entries and custom MCP entries", async () => {
    render(<IntegrationMarketplace />);

    expect(await screen.findByRole("button", { name: /Browser/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Slack/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Custom Docs/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Filesystem Persisted/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Adicionar servidor MCP" }),
    ).toBeInTheDocument();
  });

  it("supports search and shows the correct MCP detail CTAs for curated and custom entries", async () => {
    const user = userEvent.setup();

    render(<IntegrationMarketplace />);

    await screen.findByRole("button", { name: /Browser/i });

    const search = screen.getByLabelText("Buscar integrações e servidores MCP");

    await user.type(search, "custom docs");
    expect(screen.getByRole("button", { name: /Custom Docs/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Browser/i })).not.toBeInTheDocument();

    await user.clear(search);

    await user.click(screen.getByRole("button", { name: /Slack/i }));
    expect(await screen.findByRole("heading", { name: "Slack" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar servidor" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adicionar servidor" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Integrações/i }));
    await screen.findByRole("button", { name: /Notion/i });
    await user.click(screen.getByRole("button", { name: /Notion/i }));
    expect(await screen.findByRole("heading", { name: "Notion" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adicionar servidor" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Integrações/i }));
    await screen.findByRole("button", { name: /Custom Docs/i });
    await user.click(screen.getByRole("button", { name: /Custom Docs/i }));
    expect(await screen.findByRole("heading", { name: "Custom Docs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar servidor" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remover servidor" })).toBeInTheDocument();
  }, 10000);
});
