import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OAuthCallbackPage from "@/app/oauth/callback/page";

const { requestJsonMock } = vi.hoisted(() => ({
  requestJsonMock: vi.fn(),
}));

let currentSearchParams = new URLSearchParams("state=state-1&code=code-1");

vi.mock("next/navigation", () => ({
  useSearchParams: () => currentSearchParams,
}));

vi.mock("@/lib/http-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http-client")>("@/lib/http-client");
  return {
    ...actual,
    requestJson: requestJsonMock,
  };
});

describe("OAuth callback page", () => {
  beforeEach(() => {
    requestJsonMock.mockReset();
    currentSearchParams = new URLSearchParams("state=state-1&code=code-1");
    Object.defineProperty(window, "name", {
      configurable: true,
      writable: true,
      value: "koda-oauth:mcp:linear",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("finishes a successful callback, notifies the opener and closes the popup", async () => {
    const postMessage = vi.fn();
    const closeSpy = vi.spyOn(window, "close").mockImplementation(() => undefined);

    Object.defineProperty(window, "opener", {
      configurable: true,
      value: { postMessage },
    });
    requestJsonMock.mockResolvedValue({
      success: true,
      server_key: "linear",
      agent_id: "ATLAS",
      provider_account_label: "Linear Workspace",
    });

    render(<OAuthCallbackPage />);

    await waitFor(() => {
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/connections/oauth/callback?state=state-1&code=code-1",
      );
    });
    expect(await screen.findByText("Conectado com sucesso Linear Workspace")).toBeInTheDocument();
    expect(postMessage).toHaveBeenCalledWith(
      {
        type: "koda:oauth:callback",
        status: "success",
        serverKey: "linear",
        agentId: "ATLAS",
        error: "",
      },
      window.location.origin,
    );
    await waitFor(() => {
      expect(closeSpy).toHaveBeenCalled();
    }, { timeout: 2500 });
  });

  it("surfaces provider errors without calling the backend callback exchange", async () => {
    const postMessage = vi.fn();
    currentSearchParams = new URLSearchParams("error=access_denied&error_description=Authorization%20denied");

    Object.defineProperty(window, "opener", {
      configurable: true,
      value: { postMessage },
    });

    render(<OAuthCallbackPage />);

    expect((await screen.findAllByText("Authorization denied")).length).toBeGreaterThan(0);
    expect(requestJsonMock).not.toHaveBeenCalled();
    expect(postMessage).toHaveBeenCalledWith(
      {
        type: "koda:oauth:callback",
        status: "error",
        serverKey: "mcp:linear",
        agentId: "",
        error: "Authorization denied",
      },
      window.location.origin,
    );
  });
});
