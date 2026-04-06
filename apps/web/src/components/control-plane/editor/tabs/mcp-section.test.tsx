import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { McpSection } from "./mcp-section";

const { requestJsonMock } = vi.hoisted(() => ({
  requestJsonMock: vi.fn(),
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
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

vi.mock("@/components/control-plane/shared/policy-card", () => ({
  PolicyCard: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("./mcp-connection-modal", () => ({
  McpConnectionModal: () => null,
}));

vi.mock("./mcp-tool-policy-row", () => ({
  McpToolPolicyRow: () => null,
}));

describe("McpSection", () => {
  it("filters reserved catalog rows from the per-agent MCP list", async () => {
    requestJsonMock.mockImplementation(async (path: string) => {
      if (path === "/api/control-plane/mcp/catalog") {
        return [
          {
            server_key: "filesystem",
            display_name: "Filesystem Persisted",
            description: "Reserved legacy row",
            transport_type: "stdio",
            command_json: "[]",
            url: null,
            env_schema_json: "[]",
            documentation_url: null,
            logo_key: null,
            category: "development",
            enabled: true,
            metadata_json: "{}",
            created_at: "",
            updated_at: "",
          },
          {
            server_key: "custom-docs",
            display_name: "Custom Docs",
            description: "Knowledge bridge",
            transport_type: "stdio",
            command_json: "[]",
            url: null,
            env_schema_json: "[]",
            documentation_url: null,
            logo_key: null,
            category: "general",
            enabled: true,
            metadata_json: "{}",
            created_at: "",
            updated_at: "",
          },
        ];
      }

      if (path === "/api/control-plane/agents/ATLAS/mcp/connections") {
        return [];
      }

      throw new Error(`Unhandled request: ${path}`);
    });

    render(<McpSection agentId="ATLAS" />);

    expect(await screen.findByText("Custom Docs")).toBeInTheDocument();
    expect(screen.queryByText("Filesystem Persisted")).not.toBeInTheDocument();
  });
});
