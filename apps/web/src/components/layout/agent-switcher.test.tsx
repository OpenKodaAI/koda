import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { AgentDisplay } from "@/lib/agent-constants";

vi.mock("@/hooks/use-create-agent", () => ({
  useCreateAgent: () => ({
    creating: false,
    createAgent: vi.fn(),
  }),
}));

vi.mock("@/components/ui/agent-glyph", () => ({
  MAX_AGENT_ORB_COLORS: 5,
  AgentGlyph: ({ agentId }: { agentId: string }) => (
    <span data-testid={`agent-glyph-${agentId}`} />
  ),
}));

function makeAgent(index: number): AgentDisplay {
  return {
    id: `AGENT_${index.toString().padStart(2, "0")}`,
    label: `Agent ${index.toString().padStart(2, "0")}`,
    color: index % 2 === 0 ? "#D97757" : "#6E97D9",
    colorRgb: index % 2 === 0 ? "217, 119, 87" : "110, 151, 217",
  };
}

function installAgentFetch(agents: AgentDisplay[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const limit = Number(url.searchParams.get("limit") ?? agents.length);
    const offset = Number(url.searchParams.get("offset") ?? "0");
    const query = (url.searchParams.get("q") ?? "").toLowerCase();
    const filtered = query
      ? agents.filter((agent) =>
          `${agent.label} ${agent.id}`.toLowerCase().includes(query),
        )
      : agents;
    const items = filtered.slice(offset, offset + limit).map((agent) => ({
      id: agent.id,
      display_name: agent.label,
      appearance: {
        label: agent.label,
        color: agent.color,
        color_rgb: agent.colorRgb,
      },
    }));

    return new Response(
      JSON.stringify({
        items,
        total: filtered.length,
        limit,
        offset,
        has_more: offset + items.length < filtered.length,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderSwitcher(agents: AgentDisplay[]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={agents}>
          <AgentSwitcher
            multiple
            selectedBotIds={[]}
            onSelectionChange={vi.fn()}
            showCreate={false}
          />
        </AgentCatalogProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AgentSwitcher", () => {
  it("renders agents in five-item pages and fetches the next page on dropdown scroll", async () => {
    const agents = Array.from({ length: 12 }, (_, index) => makeAgent(index));
    const fetchMock = installAgentFetch(agents);
    renderSwitcher(agents);

    fireEvent.click(screen.getByRole("button", { name: /select agents/i }));

    expect(await screen.findByText("Agent 00")).toBeInTheDocument();
    expect(screen.getByText("Agent 04")).toBeInTheDocument();
    expect(screen.queryByText("Agent 05")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/agents?limit=5&offset=0",
      expect.any(Object),
    );

    const listbox = screen.getByRole("listbox", { hidden: true });
    const scroller = listbox.querySelector("[aria-busy]") as HTMLDivElement;
    await waitFor(() => {
      expect(scroller).toHaveAttribute("aria-busy", "false");
    });
    Object.defineProperty(scroller, "scrollHeight", {
      value: 100,
      configurable: true,
    });
    Object.defineProperty(scroller, "clientHeight", {
      value: 80,
      configurable: true,
    });
    Object.defineProperty(scroller, "scrollTop", {
      value: 30,
      configurable: true,
      writable: true,
    });
    scroller.scrollTop = 30;
    fireEvent.scroll(scroller, { target: { scrollTop: 30 } });

    await screen.findByText("Agent 05");
    expect(screen.getByText("Agent 09")).toBeInTheDocument();
    expect(screen.queryByText("Agent 10")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/control-plane/agents?limit=5&offset=5",
        expect.any(Object),
      );
    });
  });
});
