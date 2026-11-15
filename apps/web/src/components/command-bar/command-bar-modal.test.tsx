import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandBarModal } from "./command-bar-modal";

const fetchDashboardJson = vi.fn();

vi.mock("@/lib/control-plane-dashboard", () => ({
  fetchControlPlaneDashboardJson: (...args: unknown[]) => fetchDashboardJson(...args),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/hooks/use-app-i18n", () => ({ useAppI18n: () => ({ t: (key: string) => key }) }));
vi.mock("@/components/providers/agent-catalog-provider", () => ({
  useAgentCatalog: () => ({ agents: [{ id: "ATLAS", label: "Atlas" }] }),
}));
vi.mock("@/hooks/use-command-catalog", () => ({
  useSkillsCatalog: () => [],
  useToolsCatalog: () => [],
  usePendingApprovalsCatalog: () => [],
}));
vi.mock("./command-bar", () => ({ CommandBar: () => null }));

function statsRequests() {
  return fetchDashboardJson.mock.calls.filter(([path]) => path === "/agents/summary").length;
}

describe("CommandBarModal", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchDashboardJson.mockReset();
    fetchDashboardJson.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("asks for agent stats only while the palette is open", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CommandBarModal />
      </QueryClientProvider>,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(65_000);
    });
    expect(statsRequests()).toBe(0);

    fireEvent.keyDown(document.body, { key: "k", metaKey: true });
    await waitFor(() => expect(statsRequests()).toBe(1));

    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    const afterClose = statsRequests();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(65_000);
    });
    expect(statsRequests()).toBe(afterClose);
    client.clear();
  });
});
