import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { SessionRail } from "@/components/sessions/rail/session-rail";
import type { RoomEntry } from "@/hooks/use-rooms";
import type { AgentDisplay } from "@/lib/agent-constants";

vi.mock("@/components/ui/agent-glyph", () => ({
  AgentGlyph: ({ agentId, className }: { agentId: string; className?: string }) => (
    <span data-testid={`agent-glyph-${agentId}`} className={className} />
  ),
}));

function makeAgent(index: number, label = `Agent ${index.toString().padStart(2, "0")}`): AgentDisplay {
  return {
    id: `AGENT_${index.toString().padStart(2, "0")}`,
    label,
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

function renderRail({
  agents,
  onNewChat = vi.fn(),
  rooms = [],
  search = "",
  onSearchChange = vi.fn(),
}: {
  agents: AgentDisplay[];
  onNewChat?: (agentId?: string) => void;
  rooms?: RoomEntry[];
  search?: string;
  onSearchChange?: (value: string) => void;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={[]}>
          <SessionRail
            sessions={[]}
            rooms={rooms}
            selectedSessionId={null}
            selectedRoomId={null}
            onSelectSession={vi.fn()}
            onSelectRoom={vi.fn()}
            onNewChat={onNewChat}
            search={search}
            onSearchChange={onSearchChange}
          />
        </AgentCatalogProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { ...rendered, queryClient, agents, onNewChat };
}

function makeRoom(title: string, squadId: string, coordinatorAgentId: string): RoomEntry {
  return {
    sortKey: "2026-03-28T10:00:00.000Z",
    squad: {
      squadId,
      workspaceId: "workspace-1",
      coordinatorAgentId,
      threadCounts: { open: 1, paused: 0, completed: 0, archived: 0 },
      taskCounts: {
        pending: 0,
        claimed: 0,
        in_progress: 0,
        blocked: 0,
        done: 0,
        failed: 0,
        cancelled: 0,
        escalated: 0,
      },
      memberCount: 2,
      lastActiveAt: "2026-03-28T10:00:00.000Z",
      totalCostUsd: "0",
    },
    thread: {
      id: `${squadId}-thread`,
      workspaceId: "workspace-1",
      squadId,
      title,
      status: "open",
      coordinatorAgentId,
      currentOwnerAgentId: null,
      telegramChatId: null,
      telegramMessageThreadId: null,
      costUsdAccum: "0",
      photoUrl: null,
      createdAt: "2026-03-28T10:00:00.000Z",
      updatedAt: "2026-03-28T10:00:00.000Z",
      completedAt: null,
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SessionRail new conversation agent picker", () => {
  it("filters rooms with the same rail search used for conversations", () => {
    renderRail({
      agents: [makeAgent(0, "Atlas")],
      rooms: [
        makeRoom("Smoke test room", "DEMO_SMOKE", "ATLAS"),
        makeRoom("Research room", "DEMO_RESEARCH", "HARBOR"),
      ],
      search: "research",
    });

    expect(screen.getByRole("button", { name: /Research room/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Smoke test room/i }),
    ).not.toBeInTheDocument();
  });

  it("loads agents from the backend in compact infinite-scroll pages", async () => {
    const agents = Array.from({ length: 10 }, (_, index) => makeAgent(index));
    const fetchMock = installAgentFetch(agents);
    const onNewChat = vi.fn();
    renderRail({ agents, onNewChat });

    await userEvent.click(screen.getByRole("button", { name: /new conversation/i }));

    expect(await screen.findByText("Agent 00")).toBeInTheDocument();
    expect(screen.getByText("Agent 07")).toBeInTheDocument();
    expect(screen.queryByText("Agent 08")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/agents?limit=8&offset=0",
      expect.any(Object),
    );

    const agentButton = screen.getByRole("button", { name: /agent 00/i });
    expect(agentButton).toHaveClass("min-h-9");
    expect(screen.getByTestId("agent-glyph-AGENT_00")).toHaveClass("h-6", "w-6");

    const scroller = document.querySelector("[aria-busy]") as HTMLDivElement;
    await waitFor(() => expect(scroller).toHaveAttribute("aria-busy", "false"));
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
    fireEvent.scroll(scroller, { target: { scrollTop: 30 } });

    expect(await screen.findByText("Agent 08")).toBeInTheDocument();
    expect(screen.getByText("Agent 09")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/control-plane/agents?limit=8&offset=8",
        expect.any(Object),
      );
    });

    await userEvent.click(screen.getByRole("button", { name: /agent 08/i }));
    expect(onNewChat).toHaveBeenCalledWith("AGENT_08");
  });

  it("searches agents through the backend query", async () => {
    const agents = [
      makeAgent(0, "Atlas"),
      makeAgent(1, "Forge"),
      makeAgent(2, "Harbor"),
    ];
    const fetchMock = installAgentFetch(agents);
    renderRail({ agents });

    await userEvent.click(screen.getByRole("button", { name: /new conversation/i }));
    await screen.findByText("Atlas");
    fireEvent.change(screen.getByPlaceholderText("Search agents"), {
      target: { value: "harbor" },
    });

    expect(await screen.findByText("Harbor")).toBeInTheDocument();
    expect(screen.queryByText("Atlas")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/control-plane/agents?limit=8&offset=0&q=harbor",
        expect.any(Object),
      );
    });
  });
});
