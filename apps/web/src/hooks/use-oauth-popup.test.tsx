import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useOAuthPopup } from "@/hooks/use-oauth-popup";

const { requestJsonMock } = vi.hoisted(() => ({
  requestJsonMock: vi.fn(),
}));

vi.mock("@/lib/http-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http-client")>("@/lib/http-client");
  return {
    ...actual,
    requestJson: requestJsonMock,
  };
});

describe("useOAuthPopup", () => {
  beforeEach(() => {
    requestJsonMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts the OAuth popup and resolves on callback success", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const popup = { closed: false, close: vi.fn() } as unknown as Window;

    requestJsonMock.mockResolvedValue({
      session_id: "sess-1",
      authorization_url: "https://linear.example.com/oauth/authorize",
    });

    const openSpy = vi.spyOn(window, "open").mockReturnValue(popup);
    const { result } = renderHook(() =>
      useOAuthPopup({
        agentId: "ATLAS",
        onSuccess,
        onError,
      }),
    );

    await act(async () => {
      await result.current.startOAuth("mcp:linear");
    });

    expect(requestJsonMock).toHaveBeenCalledWith(
      "/api/control-plane/agents/ATLAS/connections/mcp%3Alinear/oauth/start",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          frontend_callback_uri: "http://localhost:3000/oauth/callback",
          redirect_uri: "http://localhost:3000/oauth/callback",
        }),
      }),
    );
    expect(openSpy).toHaveBeenCalledWith(
      "https://linear.example.com/oauth/authorize",
      "koda-oauth:mcp:linear",
      expect.stringContaining("width=600"),
    );
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isPopupOpen).toBe(true);

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          origin: window.location.origin,
          data: {
            type: "koda:oauth:callback",
            status: "success",
          },
        }),
      );
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
    expect(onError).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isPopupOpen).toBe(false);
  });

  it("reports a blocked popup without leaving loading state behind", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();

    requestJsonMock.mockResolvedValue({
      session_id: "sess-1",
      authorization_url: "https://linear.example.com/oauth/authorize",
    });

    vi.spyOn(window, "open").mockReturnValue(null);
    const { result } = renderHook(() =>
      useOAuthPopup({
        agentId: "ATLAS",
        onSuccess,
        onError,
      }),
    );

    await act(async () => {
      await result.current.startOAuth("mcp:linear");
    });

    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith("Popup blocked. Please allow popups for this site.");
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isPopupOpen).toBe(false);
  });
});
