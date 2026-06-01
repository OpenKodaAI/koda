import { describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

describe("legacy MCP settings page", () => {
  it("redirects to the integrations page", async () => {
    const pageModule = await import("@/app/control-plane/system/mcp/page");

    pageModule.default();

    expect(redirectMock).toHaveBeenCalledWith("/control-plane/system/integrations");
  });
});
