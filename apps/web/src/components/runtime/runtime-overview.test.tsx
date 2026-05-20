import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
import { ToastNotification } from "@/components/ui/toast-notification";
import type { RuntimeOverview } from "@/lib/runtime-types";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/hooks/use-create-agent", () => ({
  useCreateAgent: () => ({ creating: false, createAgent: vi.fn() }),
}));

vi.mock("@/hooks/use-runtime-overview", () => ({
  useRuntimeOverview: vi.fn(),
}));

vi.mock("@/hooks/use-runtime-rooms", () => ({
  useRuntimeRooms: vi.fn(),
}));

function overview(overrides: Partial<RuntimeOverview>): RuntimeOverview {
  return {
    agentId: "ATLAS",
    agentLabel: "ATLAS",
    agentColor: "#6E97D9",
    baseUrl: "http://localhost:8080",
    fetchedAt: "2026-03-19T00:00:00.000Z",
    health: null,
    snapshot: {
      active_environments: 1,
      retained_environments: 0,
      recovery_backlog: 0,
      cleanup_backlog: 0,
    },
    availability: {
      health: "available",
      database: "available",
      runtime: "available",
      browser: "available",
      attach: "available",
      errors: [],
    },
    queues: [
      {
        task_id: 12,
        status: "running",
        query_text: "Revisar onboarding do ambiente",
      },
    ],
    environments: [
      {
        id: 1,
        task_id: 12,
        status: "active",
        current_phase: "running",
        branch_name: "task/12",
        workspace_path: "/tmp/runtime-12",
        updated_at: "2026-03-19T00:05:00.000Z",
      },
    ],
    incidents: [],
    activeTaskIds: [12],
    retainedTaskIds: [],
    ...overrides,
  };
}

describe("RuntimeOverviewScreen", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/runtime");
  });

  it("renders a compact pulse board with live executions and agents", async () => {
    const { useRuntimeOverview } = await import("@/hooks/use-runtime-overview");
    const { useRuntimeRooms } = await import("@/hooks/use-runtime-rooms");
    vi.mocked(useRuntimeOverview).mockReturnValue({
      overviews: {
        ATLAS: overview({}),
      },
      loading: false,
      refreshing: false,
      connected: { ATLAS: true },
      error: null,
      refreshAgent: vi.fn(),
      lastUpdated: Date.now(),
    });
    vi.mocked(useRuntimeRooms).mockReturnValue({
      data: {
        pages: [
          {
            items: [
              {
                agentId: "ATLAS",
                taskId: 12,
                queryText: "Revisar onboarding do ambiente",
                source: "environment",
                status: "active",
                phase: "running",
                updatedAt: "2026-03-19T00:05:00.000Z",
                environment: overview({}).environments[0] ?? null,
                queue: overview({}).queues[0] ?? null,
              },
            ],
            page: {
              limit: 25,
              offset: 0,
              returned: 1,
              next_offset: null,
              has_more: false,
              total: null,
            },
          },
        ],
        pageParams: [0],
      },
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
      refreshFirstPage: vi.fn(),
    } as never);

    const { RuntimeOverviewScreen } = await import("@/components/runtime/runtime-overview");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider initialLanguage="pt-BR">
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
              <RuntimeOverviewScreen />
            </AgentCatalogProvider>
          </ToastProvider>
        </I18nProvider>
      </QueryClientProvider>
    );

    expect(screen.getByTestId("runtime-overview-screen")).toBeInTheDocument();
    expect(screen.getByText("Execuções ao vivo")).toBeInTheDocument();
    expect(screen.queryByText("Agentes")).not.toBeInTheDocument();
    expect(screen.queryByText("Runtime status")).not.toBeInTheDocument();
    expect(screen.queryByText("Runtime layers healthy")).not.toBeInTheDocument();
    expect(screen.getByTestId("runtime-live-list")).toBeInTheDocument();
    expect(screen.getByText(/Revisar onboarding do ambiente/i)).toBeInTheDocument();
    expect(screen.getAllByText("ATLAS").length).toBeGreaterThan(0);
  });

  it("logs runtime availability notices without showing a toast when no runtime is active", async () => {
    const consoleInfoSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    const { useRuntimeOverview } = await import("@/hooks/use-runtime-overview");
    const { useRuntimeRooms } = await import("@/hooks/use-runtime-rooms");
    vi.mocked(useRuntimeOverview).mockReturnValue({
      overviews: {
        ATLAS: overview({
          snapshot: {
            active_environments: 0,
            retained_environments: 0,
            recovery_backlog: 0,
            cleanup_backlog: 0,
          },
          availability: {
            health: "offline",
            database: "unknown",
            runtime: "unavailable",
            browser: "unavailable",
            attach: "unavailable",
            errors: ["Unable to reach runtime endpoint"],
          },
          queues: [],
          environments: [],
          incidents: ["Runtime indisponível"],
          activeTaskIds: [],
          retainedTaskIds: [],
        }),
      },
      loading: false,
      refreshing: false,
      connected: { ATLAS: false },
      error: null,
      refreshAgent: vi.fn(),
      lastUpdated: Date.now(),
    });
    vi.mocked(useRuntimeRooms).mockReturnValue({
      data: {
        pages: [
          {
            items: [],
            page: {
              limit: 25,
              offset: 0,
              returned: 0,
              next_offset: null,
              has_more: false,
              total: null,
            },
          },
        ],
        pageParams: [0],
      },
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
      refreshFirstPage: vi.fn(),
    } as never);

    const { RuntimeOverviewScreen } = await import("@/components/runtime/runtime-overview");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider initialLanguage="pt-BR">
          <ToastProvider>
            <ToastNotification />
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
              <RuntimeOverviewScreen />
            </AgentCatalogProvider>
          </ToastProvider>
        </I18nProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(consoleInfoSpy).toHaveBeenCalledWith(
        "runtime_overview_silent_notice",
        expect.objectContaining({
          kind: "incident",
          agentId: "ATLAS",
          message: "Runtime indisponível",
        }),
      );
    });
    expect(screen.queryByText(/ATLAS · Runtime indisponível/i)).not.toBeInTheDocument();

    consoleInfoSpy.mockRestore();
  });

  it("keeps live rows visible while search is pending and exposes footer pagination", async () => {
    const { useRuntimeOverview } = await import("@/hooks/use-runtime-overview");
    const { useRuntimeRooms } = await import("@/hooks/use-runtime-rooms");
    const fetchNextPage = vi.fn();

    vi.mocked(useRuntimeOverview).mockReturnValue({
      overviews: {
        ATLAS: overview({}),
      },
      loading: false,
      refreshing: false,
      connected: { ATLAS: true },
      error: null,
      refreshAgent: vi.fn(),
      lastUpdated: Date.now(),
    });
    vi.mocked(useRuntimeRooms).mockReturnValue({
      data: {
        pages: [
          {
            items: [
              {
                agentId: "ATLAS",
                taskId: 12,
                queryText: "Revisar onboarding do ambiente",
                source: "environment",
                status: "active",
                phase: "running",
                updatedAt: "2026-03-19T00:05:00.000Z",
                environment: overview({}).environments[0] ?? null,
                queue: overview({}).queues[0] ?? null,
              },
            ],
            page: {
              limit: 25,
              offset: 0,
              returned: 1,
              next_offset: 25,
              has_more: true,
              total: null,
            },
          },
        ],
        pageParams: [0],
      },
      hasNextPage: true,
      isFetching: true,
      isFetchingNextPage: false,
      fetchNextPage,
      refreshFirstPage: vi.fn(),
    } as never);

    const { RuntimeOverviewScreen } = await import("@/components/runtime/runtime-overview");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider initialLanguage="pt-BR">
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
              <RuntimeOverviewScreen />
            </AgentCatalogProvider>
          </ToastProvider>
        </I18nProvider>
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "onboarding" },
    });

    expect(screen.getByText(/Revisar onboarding do ambiente/i)).toBeInTheDocument();
    expect(screen.getByRole("status", { name: /runtime/i })).toBeInTheDocument();

    const loadMoreButton = screen.getByRole("button", {
      name: /Load more|Carregar mais/i,
    });
    const callsBeforeClick = fetchNextPage.mock.calls.length;
    fireEvent.click(loadMoreButton);
    expect(fetchNextPage.mock.calls.length).toBeGreaterThan(callsBeforeClick);
  });
});
