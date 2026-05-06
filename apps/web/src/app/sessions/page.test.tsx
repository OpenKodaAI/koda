import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SessionsPage from "@/app/sessions/page";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { setAgentCatalog } from "@/lib/agent-constants";
import type { ExecutionSummary, SessionDetail, SessionSummary } from "@/lib/types";

const replaceMock = vi.fn();

let currentQueryString = "agent=ATLAS";
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
  useMediaQuery: () => true,
}));

const agentCatalog = [
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

const sessionsByAgent: Record<string, SessionSummary[]> = {
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
  NOVA: [
    {
      bot_id: "NOVA",
      session_id: "session-nova",
      name: "Nova review",
      user_id: 101,
      created_at: "2026-03-28T08:00:00.000Z",
      last_used: "2026-03-28T08:15:00.000Z",
      last_activity_at: "2026-03-28T08:15:00.000Z",
      query_count: 2,
      execution_count: 1,
      total_cost_usd: 0.22,
      running_count: 0,
      failed_count: 0,
      latest_status: "completed",
      latest_query_preview: "Need Nova help",
      latest_response_preview: "Nova already reviewed the notes.",
      latest_message_preview: "Nova already reviewed the notes.",
    },
  ],
};

const allSessions: SessionSummary[] = [...sessionsByAgent.ATLAS, ...sessionsByAgent.NOVA];

function executionSummary(overrides: Partial<ExecutionSummary> = {}): ExecutionSummary {
  return {
    task_id: 42,
    bot_id: "ATLAS",
    status: "completed",
    query_text: "Need a quick update",
    model: "claude-opus-4-6",
    session_id: "session-alpha",
    user_id: 101,
    chat_id: 101,
    created_at: "2026-03-28T10:02:00.000Z",
    started_at: "2026-03-28T10:02:01.000Z",
    completed_at: "2026-03-28T10:03:00.000Z",
    cost_usd: 0.42,
    duration_ms: 59_000,
    attempt: 1,
    max_attempts: 1,
    has_rich_trace: true,
    trace_source: "trace",
    tool_count: 0,
    warning_count: 0,
    stop_reason: "completed",
    error_message: null,
    ...overrides,
  };
}

const sessionDetails: Record<string, SessionDetail> = {
  "session-alpha": {
    summary: sessionsByAgent.ATLAS[0],
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
        linked_execution: executionSummary(),
      },
    ],
    orphan_executions: [],
    totals: { messages: 2, executions: 1, tools: 0, cost_usd: 0.42 },
    page: { limit: 2, returned: 1, next_cursor: null, has_more: false },
  },
  "session-beta": {
    summary: sessionsByAgent.ATLAS[1],
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
    totals: { messages: 2, executions: 1, tools: 0, cost_usd: 0.16 },
    page: { limit: 2, returned: 1, next_cursor: null, has_more: false },
  },
  "session-new": {
    summary: {
      ...sessionsByAgent.ATLAS[0],
      session_id: "session-new",
      name: null,
      latest_message_preview: "Hello from web",
      last_activity_at: "2026-03-28T10:20:00.000Z",
    },
    messages: [],
    orphan_executions: [],
    totals: { messages: 0, executions: 0, tools: 0, cost_usd: 0 },
    page: { limit: 0, returned: 0, next_cursor: null, has_more: false },
  },
};

function renderSessionsPage(options?: { agents?: typeof agentCatalog }) {
  const agents = options?.agents ?? agentCatalog;
  setAgentCatalog(agents);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <AppTourProvider
          pathname="/sessions"
          mobileNavOpen={false}
          onMobileNavOpenChange={() => undefined}
        >
          <AgentCatalogProvider initialAgents={agents}>
            <SessionsPage />
          </AgentCatalogProvider>
        </AppTourProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { ...rendered, queryClient };
}

describe("SessionsPage chat redesign", () => {
  beforeEach(() => {
    currentQueryString = "agent=ATLAS";
    currentSearchParams = new URLSearchParams(currentQueryString);
    replaceMock.mockReset();
    vi.restoreAllMocks();

    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (
        method === "POST" &&
        url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/messages")
      ) {
        const payload = JSON.parse(String(init?.body ?? "{}")) as {
          session_id?: string | null;
        };
        const sessionId = payload.session_id ?? "session-new";
        return new Response(
          JSON.stringify({ accepted: true, session_id: sessionId, task_id: 42 }),
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

      const atlasSessionDetailMatch = url.match(
        /\/api\/control-plane\/dashboard\/agents\/ATLAS\/sessions\/(session-[^/?]+)/,
      );
      if (atlasSessionDetailMatch) {
        const sessionId = atlasSessionDetailMatch[1];
        return new Response(JSON.stringify({
          ...sessionDetails["session-new"],
          summary: {
            ...sessionDetails["session-new"].summary,
            session_id: sessionId,
          },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions")) {
        return new Response(JSON.stringify(sessionsByAgent.ATLAS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/sessions")) {
        return new Response(JSON.stringify(allSessions), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/control-plane/dashboard/agents/ATLAS/executions")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows sessions grouped by agent and loads the selected thread", async () => {
    renderSessionsPage();

    expect(
      await screen.findByRole("button", { name: /Alpha conversation/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();
  }, 10_000);

  it("loads conversations even when the agent catalog is not hydrated yet", async () => {
    renderSessionsPage({ agents: [] });

    expect(
      await screen.findByRole("button", { name: /Alpha conversation/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();
  }, 10_000);

  it("does not rewrite the URL on mount when the query is already normalized", async () => {
    currentQueryString = "agent=ATLAS&session=session-alpha";
    currentSearchParams = new URLSearchParams(currentQueryString);
    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  }, 10_000);

  it("switches conversations when clicking a rail row", async () => {
    const user = userEvent.setup();
    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Beta sync/i }));

    expect(await screen.findByText("Here is the beta summary.")).toBeInTheDocument();
  }, 10_000);

  it("starts a new conversation and sends a message via the composer", async () => {
    const user = userEvent.setup();
    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();

    const railNewButton = screen.getAllByRole("button", { name: /New conversation/i })[0];
    await user.click(railNewButton);
    await user.click(await screen.findByRole("button", { name: /^ATLAS$/i }));

    const composer = await screen.findByPlaceholderText(/Send a message/i);
    await user.type(composer, "Hello from web");

    await user.click(screen.getByRole("button", { name: /^Send$/i }));

    let firstSessionId = "";
    await waitFor(() => {
      const postCall = vi.mocked(global.fetch).mock.calls.find(([url, init]) => {
        if (
          typeof url !== "string" ||
          !url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/messages")
        ) {
          return false;
        }
        if (init?.method !== "POST" || typeof init.body !== "string") {
          return false;
        }
        const payload = JSON.parse(init.body as string) as {
          text?: string;
          session_id?: string | null;
        };
        if (payload.text !== "Hello from web" || typeof payload.session_id !== "string") {
          return false;
        }
        firstSessionId = payload.session_id;
        return payload.session_id.startsWith("session-");
      });
      expect(postCall).toBeTruthy();
    });

    await user.type(composer, "Second from web");
    await user.click(screen.getByRole("button", { name: /^Send$/i }));

    await waitFor(() => {
      const secondPostCall = vi.mocked(global.fetch).mock.calls.find(([url, init]) => {
        if (
          typeof url !== "string" ||
          !url.includes("/api/control-plane/dashboard/agents/ATLAS/sessions/messages")
        ) {
          return false;
        }
        if (init?.method !== "POST" || typeof init.body !== "string") {
          return false;
        }
        const payload = JSON.parse(init.body as string) as {
          text?: string;
          session_id?: string | null;
        };
        return payload.text === "Second from web" && payload.session_id === firstSessionId;
      });
      expect(secondPostCall).toBeTruthy();
    });
  }, 10_000);

  it("filters conversations via the rail search input", async () => {
    const user = userEvent.setup();
    renderSessionsPage();

    expect(
      await screen.findByRole("button", { name: /Alpha conversation/i }),
    ).toBeInTheDocument();

    const search = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(search, "Beta");

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /Alpha conversation/i }),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Beta sync/i })).toBeInTheDocument();
  }, 10_000);

  it("debounces search URL updates to avoid remount flicker while typing", async () => {
    const user = userEvent.setup();
    renderSessionsPage();

    expect(
      await screen.findByRole("button", { name: /Alpha conversation/i }),
    ).toBeInTheDocument();
    replaceMock.mockClear();

    const search = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(search, "Beta");

    expect(
      replaceMock.mock.calls.some(([url]) => String(url).includes("search=Beta")),
    ).toBe(false);

    await waitFor(() => {
      expect(
        replaceMock.mock.calls.some(([url]) => String(url).includes("search=Beta")),
      ).toBe(true);
    });
  }, 10_000);

  it("renders the composer model and agent indicator once a session is loaded", async () => {
    renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("claude-opus-4-6")).toBeInTheDocument();
    });

    const composerForm = screen.getByPlaceholderText(/Send a message/i).closest("form");
    expect(composerForm).toBeTruthy();
    if (composerForm) {
      expect(within(composerForm).getByText(/ATLAS/)).toBeInTheDocument();
    }
  }, 10_000);

  it("patches the active thread when an artifact_ready stream event arrives", async () => {
    const sources: Array<{
      url: string;
      onopen: (() => void) | null;
      onmessage: ((event: MessageEvent) => void) | null;
      onerror: (() => void) | null;
      close: ReturnType<typeof vi.fn>;
      emit: (data: unknown) => void;
    }> = [];

    class MockEventSource {
      public onopen: (() => void) | null = null;
      public onmessage: ((event: MessageEvent) => void) | null = null;
      public onerror: (() => void) | null = null;
      public close = vi.fn();

      constructor(public url: string) {
        sources.push(this);
      }

      emit(data: unknown) {
        this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
      }
    }

    vi.stubGlobal("EventSource", MockEventSource);
    const { queryClient } = renderSessionsPage();

    expect(await screen.findByText("Everything shipped correctly.")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        sources.some((source) => source.url.includes("/sessions/session-alpha/stream") && source.onmessage),
      ).toBe(true);
    });
    const source = sources.find((item) => item.url.includes("/sessions/session-alpha/stream"));
    expect(source).toBeTruthy();
    if (!source) return;
    const streamedArtifact = {
      id: "88",
      label: "voice-response-42.ogg",
      kind: "audio" as const,
      content: null,
      url: null,
      path: "/runtime/tasks/42/artifacts/voice-response-42.ogg",
      mime_type: "audio/ogg",
      size_bytes: 20,
      source_type: "voice_response",
      status: "complete",
      text_content: null,
      metadata: { runtime_artifact_id: "88", source_execution_id: "42" },
    };
    sessionDetails["session-alpha"] = {
      ...sessionDetails["session-alpha"],
      messages: sessionDetails["session-alpha"].messages.map((message) =>
        message.id === "alpha-2"
          ? { ...message, artifacts: [...(message.artifacts ?? []), streamedArtifact] }
          : message,
      ),
    };

    act(() => {
      source.onopen?.();
      source.emit({
        seq: 1,
        type: "artifact_ready",
        task_id: 42,
        payload: {
          artifact: {
            id: "88",
            kind: "audio",
            label: "voice-response-42.ogg",
            mime_type: "audio/ogg",
            size_bytes: 20,
            created_at: "2026-03-28T10:03:01.000Z",
            source_session_id: "session-alpha",
            source_execution_id: "42",
            download_url: "/api/runtime/artifacts/88/download",
            preview_state: "available",
            path: "/runtime/tasks/42/artifacts/voice-response-42.ogg",
          },
        },
      });
    });

    await waitFor(() => {
      const entries = queryClient.getQueriesData<SessionDetail>({
        queryKey: ["dashboard", "sessions", "ATLAS", "session-alpha"],
      });
      expect(
        entries.some(([, detail]) =>
          detail?.messages.some((message) =>
            message.artifacts?.some((artifact) => artifact.metadata?.runtime_artifact_id === "88"),
          ),
        ),
      ).toBe(true);
    });
    expect(await screen.findByRole("button", { name: /Play audio/i })).toBeInTheDocument();
    expect(document.querySelector("audio")?.getAttribute("src")).toBe(
      "/api/runtime/artifacts/88/download?agent=ATLAS",
    );
  }, 10_000);

  it("keeps an artifact_ready event when it arrives before the assistant message is cached", async () => {
    const sources: Array<{
      url: string;
      onopen: (() => void) | null;
      onmessage: ((event: MessageEvent) => void) | null;
      onerror: (() => void) | null;
      close: ReturnType<typeof vi.fn>;
      emit: (data: unknown) => void;
    }> = [];

    class MockEventSource {
      public onopen: (() => void) | null = null;
      public onmessage: ((event: MessageEvent) => void) | null = null;
      public onerror: (() => void) | null = null;
      public close = vi.fn();

      constructor(public url: string) {
        sources.push(this);
      }

      emit(data: unknown) {
        this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
      }
    }

    vi.stubGlobal("EventSource", MockEventSource);
    const execution = executionSummary({ task_id: 42 });
    sessionDetails["session-alpha"] = {
      ...sessionDetails["session-alpha"],
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
      ],
      orphan_executions: [execution],
    };

    const { queryClient } = renderSessionsPage();

    expect(await screen.findByText("Need a quick update")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        sources.some((source) => source.url.includes("/sessions/session-alpha/stream") && source.onmessage),
      ).toBe(true);
    });
    const source = sources.find((item) => item.url.includes("/sessions/session-alpha/stream"));
    expect(source).toBeTruthy();
    if (!source) return;

    const streamedArtifact = {
      id: "99",
      label: "generated-panel.png",
      kind: "image" as const,
      content: null,
      url: null,
      path: "/runtime/tasks/42/artifacts/generated-panel.png",
      mime_type: "image/png",
      size_bytes: 20,
      source_type: "runtime_artifact",
      status: "complete",
      text_content: null,
      metadata: { runtime_artifact_id: "99", source_execution_id: "42" },
    };
    sessionDetails["session-alpha"] = {
      ...sessionDetails["session-alpha"],
      messages: [
        sessionDetails["session-alpha"].messages[0],
        {
          id: "alpha-2",
          role: "assistant",
          text: "",
          timestamp: "2026-03-28T10:03:00.000Z",
          model: "claude-opus-4-6",
          cost_usd: 0.42,
          query_id: 2,
          session_id: "session-alpha",
          error: false,
          linked_execution: execution,
          artifacts: [streamedArtifact],
        },
      ],
      orphan_executions: [],
    };

    act(() => {
      source.onopen?.();
      source.emit({
        seq: 2,
        type: "artifact_ready",
        task_id: 42,
        payload: {
          artifact: {
            id: "99",
            kind: "image",
            label: "generated-panel.png",
            mime_type: "image/png",
            size_bytes: 20,
            created_at: "2026-03-28T10:03:01.000Z",
            source_session_id: "session-alpha",
            source_execution_id: "42",
            download_url: "/api/runtime/artifacts/99/download",
            preview_state: "available",
            path: "/runtime/tasks/42/artifacts/generated-panel.png",
          },
        },
      });
    });

    const optimisticEntries = queryClient.getQueriesData<SessionDetail>({
      queryKey: ["dashboard", "sessions", "ATLAS", "session-alpha"],
    });
    expect(
      optimisticEntries.some(([, detail]) =>
        detail?.messages.some((message) =>
          message.artifacts?.some((artifact) => artifact.metadata?.runtime_artifact_id === "99"),
        ),
      ),
    ).toBe(true);
    const preview = await screen.findByRole("img", { name: /generated-panel/i });
    expect(preview).toHaveAttribute("src", "/api/runtime/artifacts/99/download?agent=ATLAS");
  }, 10_000);
});
