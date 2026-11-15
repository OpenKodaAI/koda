import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { NewRoomDialog } from "@/components/sessions/rail/new-room-dialog";
import { ToastProvider } from "@/hooks/use-toast";

vi.mock("@/components/ui/agent-glyph", () => ({
  AgentGlyph: ({ className }: { className?: string }) => <span className={className} />,
}));

function renderDialog() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ items: [{ id: "ATLAS", status: "paused" }] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <ToastProvider>
          <AgentCatalogProvider
            initialAgents={[{ id: "ATLAS", label: "Atlas", color: "#D97757", colorRgb: "217, 119, 87" }]}
          >
            <NewRoomDialog open onClose={vi.fn()} onCreated={vi.fn()} />
          </AgentCatalogProvider>
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NewRoomDialog agent rows", () => {
  // M8-E5-T3: the paused badge and the agent id sit on the type scale, not
  // under the 12px floor.
  it("sets the paused badge and the agent id on the type scale", async () => {
    renderDialog();
    const badge = (await screen.findByText("Paused agent")).parentElement as HTMLElement;
    for (const element of [badge, screen.getByText("ATLAS")]) {
      expect([...element.classList].filter((name) => /^text-\[[\d.]+(?:px|rem)\]$/.test(name))).toEqual([]);
      expect(element.classList).toContain("text-xs");
    }
  });

  // D-267: an unchecked row paints --hover-tint on hover, and on the light
  // modal glass that takes --text-quaternary to 4.37:1, so the agent id steps
  // up to --text-tertiary while its row is hovered.
  it("steps the agent id up to --text-tertiary while its row is hovered", async () => {
    renderDialog();
    const row = await screen.findByRole("button", { name: /Atlas/ });
    expect(row.className).toContain("hover:bg-[var(--hover-tint)]");
    expect(row.classList).toContain("group");
    const id = screen.getByText("ATLAS");
    expect(id.classList).toContain("group-hover:text-[color:var(--text-tertiary)]");
  });
});
