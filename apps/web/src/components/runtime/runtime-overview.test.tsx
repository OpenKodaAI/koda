import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
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
    expect(screen.getByText("Agentes")).toBeInTheDocument();
    expect(screen.getByText("Runtime status")).toBeInTheDocument();
    expect(screen.getByText("1 active execution")).toBeInTheDocument();
    expect(screen.getByText("Runtime layers healthy")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-live-list")).toBeInTheDocument();
    expect(screen.getByText(/Revisar onboarding do ambiente/i)).toBeInTheDocument();
    expect(screen.getAllByText("ATLAS").length).toBeGreaterThan(0);
  });
});
