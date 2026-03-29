import { render, screen, waitFor } from "@testing-library/react";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SessionsPage from "@/app/sessions/page";
import { BotCatalogProvider } from "@/components/providers/bot-catalog-provider";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { SessionDetail, SessionSummary } from "@/lib/types";

const replaceMock = vi.fn();

let currentQueryString = "bot=ATLAS";
let currentSearchParams = new URLSearchParams(currentQueryString);

vi.mock("next/navigation", () => ({
  usePathname: () => "/sessions",
  useRouter: () => ({
    replace: (nextUrl: string) => {
      replaceMock(nextUrl);
      const [, query = ""] = nextUrl.split("?");
      currentQueryString = query;
      currentSearchParams = new URLSearchParams(currentQueryString);
    },
  }),
  useSearchParams: () => currentSearchParams,
}));

vi.mock("@/hooks/use-animated-presence", () => ({
  useAnimatedPresence: (isOpen: boolean) => ({
    shouldRender: isOpen,
    isVisible: isOpen,
    renderedValue: null,
  }),
  useBodyScrollLock: () => undefined,
  useEscapeToClose: () => undefined,
  useMediaQuery: (query: string) => query.includes("1080") || query.includes("1380"),
}));

const botCatalog = [
  {
    id: "ATLAS",
    label: "ATLAS",
    color: "#ff5a5a",
    colorRgb: "255, 90, 90",
    initials: "MA",
    status: "active" as const,
    model: "Claude Opus 4.6",
  },
  {
    id: "NOVA",
    label: "Nova",
    color: "#5b8cff",
    colorRgb: "91, 140, 255",
    initials: "LU",
    status: "active" as const,
    model: "Claude Sonnet 4.6",
  },
];

const sessionsByBot: Record<string, SessionSummary[]> = {
  ATLAS: [
    {
      bot_id: "ATLAS",
      session_id: "session-alpha",
      name: "Alpha conversation",
      user_id: 101,
      created_at: "2026-03-28T10:00:00.000Z",
      last_used: "2026-03-28T10:05:00.000Z",
      last_activity_at: "2026-03-28T10:05:00.000Z",
      query_count: 4,
      execution_count: 2,
      total_cost_usd: 1.42,
      running_count: 0,
      failed_count: 0,
      latest_status: "completed",
      latest_query_preview: "Need a quick update",
      latest_response_preview: "Everything shipped correctly.",
      latest_message_preview: "Everything shipped correctly.",
    },
    {
      bot_id: "ATLAS",
      session_id: "session-beta",
      name: "Beta sync",
      user_id: 101,
      created_at: "2026-03-28T09:00:00.000Z",
      last_used: "2026-03-28T09:12:00.000Z",
      last_activity_at: "2026-03-28T09:12:00.000Z",
      query_count: 3,
      execution_count: 1,
      total_cost_usd: 0.58,
      running_count: 0,
      failed_count: 0,
      latest_status: "completed",
      latest_query_preview: "Can you summarize beta?",
      latest_response_preview: "Here is the beta summary.",
      latest_message_preview: "Here is the beta summary.",
    },
  ],
};

const sessionDetails: Record<string, SessionDetail> = {
  "session-alpha": {
    summary: sessionsByBot.ATLAS[0],
    messages: [
      {
        id: "alpha-1",
        role: "user",
        text: "Need a quick update",
        timestamp: "2026-03-28T10:02:00.000Z",
        model: null,
        cost_usd: null,
        query_id: 1,
        session_id: "session-alpha",
        error: false,
      },
      {
        id: "alpha-2",
        role: "assistant",
        text: "Everything shipped correctly.",
        timestamp: "2026-03-28T10:03:00.000Z",
        model: "claude-opus-4-6",
        cost_usd: 0.42,
        query_id: 2,
        session_id: "session-alpha",
        error: false,
      },
    ],
    orphan_executions: [],
    totals: {
      messages: 2,
      executions: 1,
      tools: 0,
      cost_usd: 0.42,
    },
  },
  "session-beta": {
    summary: sessionsByBot.ATLAS[1],
    messages: [
      {
        id: "beta-1",
        role: "user",
        text: "Can you summarize beta?",
        timestamp: "2026-03-28T09:10:00.000Z",
        model: null,
        cost_usd: null,
        query_id: 3,
        session_id: "session-beta",
        error: false,
      },
      {
        id: "beta-2",
        role: "assistant",
        text: "Here is the beta summary.",
        timestamp: "2026-03-28T09:11:00.000Z",
        model: "claude-opus-4-6",
        cost_usd: 0.16,
        query_id: 4,
        session_id: "session-beta",
        error: false,
      },
    ],
    orphan_executions: [],
    totals: {
      messages: 2,
      executions: 1,
      tools: 0,
      cost_usd: 0.16,
    },
  },
  "session-new": {
    summary: {
      ...sessionsByBot.ATLAS[0],
      session_id: "session-new",
      name: null,
      latest_message_preview: "Hello from web",
      last_activity_at: "2026-03-28T10:20:00.000Z",
    },
    messages: [],
    orphan_executions: [],
    totals: {
      messages: 0,
      executions: 0,
      tools: 0,
      cost_usd: 0,
    },
  },
};

function renderSessionsPage() {
  return render(
    <I18nProvider initialLanguage="en-US">
      <AppTourProvider
        pathname="/sessions"
        mobileNavOpen={false}
        onMobileNavOpenChange={() => undefined}
      >
        <BotCatalogProvider initialBots={botCatalog}>
          <SessionsPage />
        </BotCatalogProvider>
      </AppTourProvider>
    </I18nProvider>,
  );
}

describe("SessionsPage", () => {
  beforeEach(() => {
    currentQueryString = "bot=ATLAS";
    currentSearchParams = new URLSearchParams(currentQueryString);
    replaceMock.mockReset();
    vi.restoreAllMocks();

    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (method === "POST" && url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/messages")) {
        return new Response(
          JSON.stringify({
            accepted: true,
            session_id: "session-new",
            task_id: 42,
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/session-alpha")) {
        return new Response(JSON.stringify(sessionDetails["session-alpha"]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/session-beta")) {
        return new Response(JSON.stringify(sessionDetails["session-beta"]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/session-new")) {
        return new Response(JSON.stringify(sessionDetails["session-new"]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions")) {
        return new Response(JSON.stringify(sessionsByBot.ATLAS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/sessions")) {
        return new Response(JSON.stringify(sessionsByBot.ATLAS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("auto-selects the first session, switches conversations and supports optimistic new chat sending", async () => {
    const user = userEvent.setup();
    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Beta sync/i }));
    expect((await screen.findAllByText("Here is the beta summary.")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /New chat/i }));
    const composer = await screen.findByPlaceholderText(/Write your message/i);
    await user.type(composer, "Hello from web");
    await user.click(screen.getByRole("button", { name: /Send/i }));

    expect(await screen.findByText("Hello from web")).toBeInTheDocument();

    await waitFor(() => {
      const postCall = vi.mocked(global.fetch).mock.calls.find(([url, init]) => {
        if (typeof url !== "string" || !url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/messages")) {
          return false;
        }
        if (init?.method !== "POST" || typeof init.body !== "string") {
          return false;
        }
        const payload = JSON.parse(init.body as string) as { text?: string; session_id?: string | null };
        return payload.text === "Hello from web" && payload.session_id === null;
      });

      expect(postCall).toBeTruthy();
    });
  }, 10_000);

  it("keeps the composer disabled when browsing with all bots selected", async () => {
    currentQueryString = "";
    currentSearchParams = new URLSearchParams(currentQueryString);
    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Select a specific bot here to start a chat.")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Select a bot to chat" })).toBeInTheDocument();
  });

  it("allows selecting a bot from the composer switcher when browsing all bots", async () => {
    currentQueryString = "";
    currentSearchParams = new URLSearchParams(currentQueryString);
    const user = userEvent.setup();

    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Select a bot to chat" }));

    const menu = await screen.findByRole("dialog", { name: "Select bot" });
    await user.click(within(menu).getByRole("button", { name: /ATLAS/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Write your message/i)).not.toBeDisabled();
    });
  });
});
