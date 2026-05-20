import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { RoomChatPane } from "@/components/sessions/chat/room-chat-pane";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";
import { setAgentCatalog } from "@/lib/agent-constants";
import type { SquadThreadOverviewResponse } from "@/lib/squads";

vi.mock("@/components/ui/agent-glyph", () => ({
  AgentGlyph: ({
    agentId,
    className,
  }: {
    agentId: string;
    className?: string;
  }) => <span data-testid={`agent-glyph-${agentId}`} className={className} />,
}));

const agentCatalog = [
  {
    id: "planner",
    label: "Planner",
    color: "#22C7D8",
    colorRgb: "34, 199, 216",
    initials: "PL",
    status: "active" as const,
    model: "Claude Sonnet 4.6",
  },
];

function makeThreadDetail(
  threadId: string,
  messages: SquadThreadOverviewResponse["recentMessages"],
  page: SquadThreadOverviewResponse["page"],
  threadOverrides: Partial<SquadThreadOverviewResponse["thread"]> = {},
): SquadThreadOverviewResponse {
  return {
    thread: {
      id: threadId,
      workspaceId: "workspace-1",
      squadId: "squad-1",
      title: "Test room",
      status: "active",
      ownerUserId: 1,
      coordinatorAgentId: "planner",
      currentOwnerAgentId: null,
      telegramChatId: null,
      telegramMessageThreadId: null,
      budgetUsdCap: null,
      costUsdAccum: "0",
      createdAt: "2026-03-28T10:00:00.000Z",
      updatedAt: "2026-03-28T10:05:00.000Z",
      ...threadOverrides,
    },
    coordinatorAgentId: "planner",
    participants: [
      {
        agentId: "planner",
        role: "coordinator",
        joinedAt: "2026-03-28T10:00:00.000Z",
        leftAt: null,
      },
    ],
    recentMessages: messages,
    page,
    activeTasks: [],
    artifacts: [],
    openTaskCount: 0,
    doneTaskCount: 0,
  };
}

function makeMessage(
  id: number,
  content: string,
  overrides: Partial<SquadThreadOverviewResponse["recentMessages"][number]> = {},
): SquadThreadOverviewResponse["recentMessages"][number] {
  const minute = String(id).padStart(2, "0");
  return {
    id,
    messageUuid: `message-${id}`,
    from: "planner",
    to: null,
    toAgentIds: [],
    content,
    type: "agent_text",
    metadata: {},
    createdAt: `2026-03-28T10:${minute}:00.000Z`,
    ...overrides,
  };
}

function renderRoomPane(threadId: string, queryClient: QueryClient) {
  return render(roomPaneTree(threadId, queryClient));
}

function roomPaneTree(threadId: string, queryClient: QueryClient) {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <ToastProvider>
          <AgentCatalogProvider initialAgents={agentCatalog}>
            <RoomChatPane threadId={threadId} />
          </AgentCatalogProvider>
          <ToastNotification />
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

describe("RoomChatPane history pagination", () => {
  beforeEach(() => {
    setAgentCatalog(agentCatalog);
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";
      const parsed = new URL(url, "http://localhost");
      const before = parsed.searchParams.get("before");

      if (
        method === "POST" &&
        url.includes("/api/control-plane/dashboard/squads/threads/thread-1/messages")
      ) {
        return new Response(JSON.stringify({ error: "Dispatch service unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/squads/threads/thread-1")) {
        const detail =
          before === "room-before-2"
            ? makeThreadDetail("thread-1", [makeMessage(1, "Older room context")], {
                limit: 32,
                returned: 1,
                nextCursor: null,
                hasMore: false,
              })
            : makeThreadDetail(
                "thread-1",
                [makeMessage(2, "Latest room message"), makeMessage(3, "Room follow up")],
                {
                  limit: 32,
                  returned: 2,
                  nextCursor: "room-before-2",
                  hasMore: true,
                },
              );
        return new Response(JSON.stringify(detail), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/squads/threads/thread-2")) {
        return new Response(
          JSON.stringify(
            makeThreadDetail("thread-2", [makeMessage(10, "Second room latest")], {
              limit: 32,
              returned: 1,
              nextCursor: null,
              hasMore: false,
            }),
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/control-plane/dashboard/squads/threads/thread-rich")) {
        return new Response(
          JSON.stringify(
            makeThreadDetail(
              "thread-rich",
              [
                makeMessage(
                  20,
                  "Intro.**KODA:** `Controle financeiro sem complicação.`\n\n1. `Seu dinheiro no seu comando.`",
                  {
                    metadata: {
                      blocks: [
                        {
                          id: "card-1",
                          version: 1,
                          block_type: "ui_card",
                          payload: {
                            title: "Signal card",
                            body: "Rendered inside the room message.",
                          },
                        },
                      ],
                    },
                  },
                ),
              ],
              {
                limit: 32,
                returned: 1,
                nextCursor: null,
                hasMore: false,
              },
            ),
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/control-plane/dashboard/squads/threads/thread-photo")) {
        return new Response(
          JSON.stringify(
            makeThreadDetail(
              "thread-photo",
              [makeMessage(30, "Room with photo")],
              {
                limit: 32,
                returned: 1,
                nextCursor: null,
                hasMore: false,
              },
              {
                title: "Visual room",
                photoUrl: "/api/control-plane/dashboard/squads/threads/thread-photo/photo",
              },
            ),
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads older room pages near the top and keeps them cached per room", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const rendered = renderRoomPane("thread-1", queryClient);

    let log = await screen.findByRole("log");
    expect(await within(log).findByText("Latest room message")).toBeInTheDocument();
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1600 },
      clientHeight: { configurable: true, value: 520 },
      scrollTop: { configurable: true, value: 260, writable: true },
    });
    fireEvent.scroll(log);

    expect(await within(log).findByText("Older room context")).toBeInTheDocument();
    const olderFetchCount = () =>
      vi.mocked(global.fetch).mock.calls.filter(([input]) => {
        const url = typeof input === "string" ? input : input.toString();
        if (!url.includes("/api/control-plane/dashboard/squads/threads/thread-1")) {
          return false;
        }
        const parsed = new URL(url, "http://localhost");
        return parsed.searchParams.get("before") === "room-before-2";
      }).length;
    expect(olderFetchCount()).toBe(1);

    rendered.rerender(roomPaneTree("thread-2", queryClient));
    expect(
      await within(await screen.findByRole("log")).findByText("Second room latest"),
    ).toBeInTheDocument();

    rendered.rerender(roomPaneTree("thread-1", queryClient));
    log = await screen.findByRole("log");
    expect(await within(log).findByText("Older room context")).toBeInTheDocument();
    await waitFor(() => expect(olderFetchCount()).toBe(1));
  });

  it("renders room messages with the agent orb, markdown, and structured blocks", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderRoomPane("thread-rich", queryClient);

    const log = await screen.findByRole("log");
    expect(await within(log).findByText("KODA:")).toBeInTheDocument();
    expect(within(log).queryByText("**KODA:**")).not.toBeInTheDocument();
    expect(within(log).getByText("Controle financeiro sem complicação.").tagName).toBe("CODE");
    const avatar = within(log).getByRole("img", { name: "Planner" });
    expect(avatar).toHaveClass("h-9", "w-9");
    expect(avatar).not.toHaveClass("border", "bg-[var(--panel-strong)]", "shadow-[var(--shadow-xs)]");
    expect(within(log).getByTestId("agent-glyph-planner")).toHaveClass("h-9", "w-9");
    expect(within(log).getByText("Signal card")).toBeInTheDocument();
  });

  it("uses the room photo in the header and otherwise leaves only the title", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const rendered = renderRoomPane("thread-photo", queryClient);

    expect(await screen.findByText("Visual room")).toHaveClass("font-semibold");
    expect(screen.getByTestId("room-header-photo")).toBeInTheDocument();

    rendered.rerender(roomPaneTree("thread-2", queryClient));

    expect(await screen.findByText("Test room")).toHaveClass("font-semibold");
    expect(screen.queryByTestId("room-header-photo")).not.toBeInTheDocument();
  });

  it("surfaces room post request failures via toast instead of composer text", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderRoomPane("thread-1", queryClient);

    expect(await screen.findByText("Latest room message")).toBeInTheDocument();

    const textbox = screen.getByPlaceholderText(/Send a message to this room/i);
    fireEvent.change(textbox, { target: { value: "Can you retry this?" } });
    const form = textbox.closest("form");
    expect(form).toBeTruthy();
    if (!form) return;

    fireEvent.submit(form);

    expect(await screen.findByText("Dispatch service unavailable")).toBeInTheDocument();
    expect(within(form).queryByText("Dispatch service unavailable")).not.toBeInTheDocument();
  });
});
