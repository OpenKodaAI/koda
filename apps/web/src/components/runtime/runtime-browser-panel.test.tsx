import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";

class MockWebSocket {
  static OPEN = 1;

  readyState = MockWebSocket.OPEN;
  addEventListener = vi.fn();
  close = vi.fn();

  constructor(public readonly url: string) {}
}

describe("RuntimeBrowserPanel", () => {
  it("falls back to snapshot mode when the runtime has no noVNC surface", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    const mockFetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ error: "Browser is not available." }), {
          status: 404,
          headers: { "content-type": "application/json" },
        })
      )
    );
    vi.stubGlobal("fetch", mockFetch);

    const mutate = vi.fn();
    const fetchResource = vi.fn();

    const { RuntimeBrowserPanel } = await import("@/components/runtime/runtime-browser-panel");

    render(
      <I18nProvider initialLanguage="pt-BR">
        <RuntimeBrowserPanel
          botId="ATLAS"
          taskId={7}
          browser={{
            status: "running",
            transport: "local_headful",
            display_id: 91,
            novnc_port: null,
          }}
          mutate={mutate}
          fetchResource={fetchResource}
        />
      </I18nProvider>
    );

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/runtime/bots/ATLAS/tasks/7/browser",
        expect.objectContaining({ cache: "no-store" })
      )
    );
    expect(mutate).not.toHaveBeenCalled();
    expect(
      screen.getAllByText(/sess[aã]o visual do browser n[aã]o est[aá] mais ativa/i).length
    ).toBeGreaterThan(0);
    vi.unstubAllGlobals();
  });
});
