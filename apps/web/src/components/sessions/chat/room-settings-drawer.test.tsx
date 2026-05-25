import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { RoomSettingsPanel } from "@/components/sessions/chat/room-settings-drawer";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";

const agents = [
  {
    id: "ATLAS",
    label: "Atlas",
    color: "#22C7D8",
    colorRgb: "34, 199, 216",
    initials: "AT",
    status: "active" as const,
    model: "Claude Sonnet 4.6",
  },
];

function renderSettingsPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <ToastProvider>
          <AgentCatalogProvider initialAgents={agents}>
            <RoomSettingsPanel threadId="thread-open" variant="rail" />
          </AgentCatalogProvider>
          <ToastNotification />
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("RoomSettingsPanel", () => {
  let threadTitle: string;

  beforeEach(() => {
    threadTitle = "Smoke test room";
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (method === "GET" && url.includes("/api/control-plane/agents")) {
        return new Response(JSON.stringify({ items: [{ id: "ATLAS", status: "active" }] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (
        method === "GET" &&
        url.includes("/api/control-plane/dashboard/squads/threads/thread-open")
      ) {
        return new Response(
          JSON.stringify({
            thread: {
              id: "thread-open",
              workspaceId: "workspace-1",
              squadId: "squad-1",
              title: threadTitle,
              status: "open",
              ownerUserId: 1,
              coordinatorAgentId: "ATLAS",
              currentOwnerAgentId: null,
              telegramChatId: null,
              telegramMessageThreadId: null,
              budgetUsdCap: null,
              costUsdAccum: "0",
              photoUrl: null,
              metadata: {},
              createdAt: "2026-03-28T10:00:00.000Z",
              updatedAt: "2026-03-28T10:05:00.000Z",
            },
            coordinatorAgentId: "ATLAS",
            participants: [
              {
                agentId: "ATLAS",
                role: "coordinator",
                joinedAt: "2026-03-28T10:00:00.000Z",
                leftAt: null,
              },
            ],
            recentMessages: [],
            page: { limit: 32, returned: 0, nextCursor: null, hasMore: false },
            activeTasks: [],
            artifacts: [],
            openTaskCount: 0,
            doneTaskCount: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (
        method === "PATCH" &&
        url.includes("/api/control-plane/dashboard/squads/threads/thread-open")
      ) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { title?: string };
        if (body.title) threadTitle = body.title;
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (
        method === "DELETE" &&
        url.includes("/api/control-plane/dashboard/squads/threads/thread-open")
      ) {
        return new Response(
          JSON.stringify({ error: "illegal transition 'open' -> 'archived'" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows archive request failures via toast", async () => {
    const user = userEvent.setup();
    renderSettingsPanel();

    expect(await screen.findByDisplayValue("Smoke test room")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Archive$/i }));

    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /^Archive$/i }));

    expect(
      await screen.findByText("illegal transition 'open' -> 'archived'"),
    ).toBeInTheDocument();
  });

  it("saves room title inline when the field loses focus", async () => {
    const user = userEvent.setup();
    renderSettingsPanel();

    const titleInput = await screen.findByRole("textbox", { name: /room name/i });
    await user.clear(titleInput);
    await user.type(titleInput, "Launch room");
    await user.tab();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/control-plane/dashboard/squads/threads/thread-open"),
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ title: "Launch room" }),
        }),
      );
    });
  });
});
