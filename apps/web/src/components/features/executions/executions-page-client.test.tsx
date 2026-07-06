import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
import ExecutionsPage from "@/components/features/executions/executions-page-client";
import type { ExecutionSummary } from "@/lib/types";

vi.mock("@/hooks/use-create-agent", () => ({
  useCreateAgent: () => ({ creating: false, createAgent: vi.fn() }),
}));

vi.mock("@/components/ui/agent-glyph", () => ({
  AgentGlyph: ({ agentId, className }: { agentId: string; className?: string }) => (
    <span data-testid={`agent-glyph-${agentId}`} className={className} />
  ),
}));

vi.mock("@/components/ui/agent-glyph-group", () => ({
  AgentGlyphGroup: ({
    agents,
    className,
  }: {
    agents: Array<{ id: string }>;
    className?: string;
  }) => (
    <span data-testid="agent-glyph-group" className={className}>
      {agents.map((agent) => agent.id).join(",")}
    </span>
  ),
}));

function execution(overrides: Partial<ExecutionSummary> = {}): ExecutionSummary {
  return {
    task_id: 42,
    bot_id: "ATLAS",
    status: "completed",
    query_text: "Initial audit execution",
    model: "claude-sonnet-4-6",
    session_id: "session-1",
    user_id: 1,
    chat_id: 1,
    created_at: "2026-03-19T00:05:00.000Z",
    started_at: "2026-03-19T00:05:01.000Z",
    completed_at: "2026-03-19T00:05:10.000Z",
    cost_usd: 0.02,
    duration_ms: 9000,
    attempt: 1,
    max_attempts: 1,
    has_rich_trace: false,
    trace_source: "trace",
    tool_count: 2,
    warning_count: 0,
    stop_reason: null,
    error_message: null,
    ...overrides,
  };
}

function page(items: ExecutionSummary[], hasMore = false) {
  return {
    items,
    page: {
      limit: 25,
      offset: 0,
      returned: items.length,
      next_offset: hasMore ? 25 : null,
      has_more: hasMore,
      total: null,
    },
  };
}

function renderExecutionsPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <ToastProvider>
          <AgentCatalogProvider
            initialAgents={[
              {
                id: "ATLAS",
                label: "ATLAS",
                color: "#6E97D9",
                colorRgb: "110, 151, 217",
              },
            ]}
          >
            <ExecutionsPage />
          </AgentCatalogProvider>
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ExecutionsPage search", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/executions");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps existing rows visible while a confirmed search request is fetching", async () => {
    let resolveSearch: ((response: Response) => void) | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/control-plane/dashboard/executions")) {
        if (url.includes("search=beta")) {
          return new Promise<Response>((resolve) => {
            resolveSearch = resolve;
          });
        }
        return Promise.resolve(
          new Response(JSON.stringify(page([execution()])), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderExecutionsPage();

    expect(await screen.findAllByText("Initial audit execution")).not.toHaveLength(0);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "beta" },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("search=beta"),
        expect.any(Object),
      );
    });

    expect(screen.getAllByText("Initial audit execution")).not.toHaveLength(0);
    expect(
      screen.getByRole("status", { name: /executions/i }),
    ).toBeInTheDocument();

    resolveSearch?.(
      new Response(
        JSON.stringify(
          page([
            execution({
              task_id: 43,
              query_text: "Beta search execution",
            }),
          ]),
        ),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
  });
});
