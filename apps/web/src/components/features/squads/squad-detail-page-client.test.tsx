import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SquadDetailPageClient from "@/components/features/squads/squad-detail-page-client";
import type { SquadThreadSummary, SquadThreadsResponse } from "@/lib/squads";

vi.mock("@/lib/control-plane-dashboard", () => ({
  fetchControlPlaneDashboardJson: vi.fn(),
  buildControlPlaneDashboardPath: (p: string) => `/api/control-plane/dashboard${p}`,
  buildControlPlaneDashboardUrl: (p: string) => `/api/control-plane/dashboard${p}`,
}));

import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import type { SquadActivityResponse } from "@/lib/squads";

function _thread(overrides: Partial<SquadThreadSummary> = {}): SquadThreadSummary {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    workspaceId: "acme",
    squadId: "build",
    title: "Landing page",
    status: "open",
    coordinatorAgentId: "PM",
    currentOwnerAgentId: null,
    telegramChatId: -100,
    telegramMessageThreadId: 7,
    costUsdAccum: "1.50",
    createdAt: "2024-06-15T10:00:00Z",
    updatedAt: "2024-06-15T11:00:00Z",
    completedAt: null,
    ...overrides,
  };
}

function makePayload(overrides: Partial<SquadThreadsResponse> = {}): SquadThreadsResponse {
  return {
    items: [
      _thread(),
      _thread({
        id: "00000000-0000-0000-0000-000000000002",
        title: "Hotfix",
        status: "completed",
        coordinatorAgentId: null,
        costUsdAccum: "0.80",
        updatedAt: "2024-06-14T08:00:00Z",
      }),
    ],
    count: 2,
    available: true,
    ...overrides,
  };
}

function makeActivity(overrides: Partial<SquadActivityResponse> = {}): SquadActivityResponse {
  return {
    items: [],
    count: 0,
    available: true,
    ...overrides,
  };
}

function dispatchMock(
  threadsPayload?: SquadThreadsResponse | Error,
  activityPayload?: SquadActivityResponse | Error,
) {
  vi.mocked(fetchControlPlaneDashboardJson).mockImplementation(((path: string) => {
    if (path.includes("/activity")) {
      const value = activityPayload ?? makeActivity();
      return value instanceof Error ? Promise.reject(value) : Promise.resolve(value);
    }
    const value = threadsPayload ?? makePayload();
    return value instanceof Error ? Promise.reject(value) : Promise.resolve(value);
  }) as unknown as typeof fetchControlPlaneDashboardJson);
}

function renderClient(squadId = "build") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SquadDetailPageClient squadId={squadId} />
    </QueryClientProvider>,
  );
}

describe("SquadDetailPageClient", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows loading state initially", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockImplementation(
      () => new Promise(() => undefined),
    );
    renderClient();
    expect(await screen.findByTestId("squad-detail-route")).toHaveTextContent("Loading squad");
  });

  it("renders thread rows with status badges and links to thread detail", async () => {
    dispatchMock();
    renderClient();

    await waitFor(() => {
      expect(screen.getByText("Landing page")).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId("squad-thread-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Landing page");
    expect(rows[1]).toHaveTextContent("Hotfix");

    // Link points to thread detail
    const firstLink = rows[0].querySelector("a");
    expect(firstLink?.getAttribute("href")).toBe(
      "/squads/threads/00000000-0000-0000-0000-000000000001",
    );

    // Header includes the count
    expect(screen.getByTestId("squad-detail-route")).toHaveTextContent("2 thread(s) in this squad");
  });

  it("renders empty state when there are no threads", async () => {
    dispatchMock(makePayload({ items: [], count: 0 }));
    renderClient();
    await waitFor(() => {
      expect(screen.getByTestId("squad-detail-empty")).toBeInTheDocument();
    });
  });

  it("renders Postgres-unavailable message when backend reports unavailable", async () => {
    dispatchMock(makePayload({ items: [], count: 0, available: false }));
    renderClient();
    await waitFor(() => {
      expect(screen.getByTestId("squad-detail-empty-postgres")).toBeInTheDocument();
    });
  });

  it("renders error state on fetch failure", async () => {
    dispatchMock(new Error("boom"), new Error("boom"));
    renderClient();
    await waitFor(
      () => {
        expect(screen.getByText("Couldn't load squad")).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders activity feed entries with event chip and thread link", async () => {
    dispatchMock(
      makePayload(),
      makeActivity({
        items: [
          {
            timestamp: "2024-06-15T10:00:00Z",
            source: "coordinator",
            eventType: "elected",
            actor: "admin",
            summary: "coordinator elected: (none) -> PM",
            threadId: null,
            payload: { force_replace: false },
          },
          {
            timestamp: "2024-06-15T10:30:00Z",
            source: "system_event",
            eventType: "coordinator_changed",
            actor: "admin",
            summary: "[elected] coordinator changed: (none) -> PM",
            threadId: "00000000-0000-0000-0000-000000000001",
            payload: { kind: "elected" },
          },
        ],
        count: 2,
      }),
    );
    renderClient();
    await waitFor(() => {
      expect(screen.getByTestId("squad-activity-feed")).toBeInTheDocument();
    });
    const rows = screen.getAllByTestId("squad-activity-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("admin");
    expect(rows[0]).toHaveTextContent("elected");
    // Row with threadId should have a link
    const link = rows[1].querySelector("a");
    expect(link?.getAttribute("href")).toBe(
      "/squads/threads/00000000-0000-0000-0000-000000000001",
    );
  });

  it("renders activity empty state when there are no events", async () => {
    dispatchMock(makePayload(), makeActivity({ items: [], count: 0 }));
    renderClient();
    await waitFor(() => {
      expect(screen.getByTestId("squad-activity-empty")).toBeInTheDocument();
    });
  });
});
