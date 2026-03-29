import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BotCatalogProvider } from "@/components/providers/bot-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { RuntimeOverview } from "@/lib/runtime-types";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/hooks/use-runtime-overview", () => ({
  useRuntimeOverview: vi.fn(),
}));

function overview(overrides: Partial<RuntimeOverview>): RuntimeOverview {
  return {
    botId: "ATLAS",
    botLabel: "ATLAS",
    botColor: "#6E97D9",
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
  it("renders a compact pulse board with live executions and bots", async () => {
    const { useRuntimeOverview } = await import("@/hooks/use-runtime-overview");
    vi.mocked(useRuntimeOverview).mockReturnValue({
      overviews: {
        ATLAS: overview({}),
      },
      loading: false,
      refreshing: false,
      connected: { ATLAS: true },
      error: null,
      refreshBot: vi.fn(),
      lastUpdated: Date.now(),
    });

    const { RuntimeOverviewScreen } = await import("@/components/runtime/runtime-overview");

    render(
      <I18nProvider initialLanguage="pt-BR">
        <BotCatalogProvider
          initialBots={[
            {
              id: "ATLAS",
              label: "ATLAS",
              color: "#6E97D9",
              colorRgb: "110, 151, 217",
            },
          ]}
        >
          <RuntimeOverviewScreen />
        </BotCatalogProvider>
      </I18nProvider>
    );

    expect(screen.getByTestId("runtime-overview-screen")).toBeInTheDocument();
    expect(screen.getByText("Execuções ao vivo")).toBeInTheDocument();
    expect(screen.getByText("Bots")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-live-list")).toBeInTheDocument();
    expect(screen.getByText(/Revisar onboarding do ambiente/i)).toBeInTheDocument();
    expect(screen.getAllByText("ATLAS").length).toBeGreaterThan(0);
  });
});
