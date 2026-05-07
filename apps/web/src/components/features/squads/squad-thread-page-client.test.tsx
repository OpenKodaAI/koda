import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SquadThreadPageClient from "@/components/features/squads/squad-thread-page-client";
import type { SquadThreadOverviewResponse } from "@/lib/squads";

vi.mock("@/lib/control-plane-dashboard", () => ({
  fetchControlPlaneDashboardJson: vi.fn(),
  mutateControlPlaneDashboardJson: vi.fn(),
  buildControlPlaneDashboardPath: (p: string) => `/api/control-plane/dashboard${p}`,
  buildControlPlaneDashboardUrl: (p: string) => `/api/control-plane/dashboard${p}`,
}));

import {
  fetchControlPlaneDashboardJson,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";

function makePayload(overrides: Partial<SquadThreadOverviewResponse> = {}): SquadThreadOverviewResponse {
  return {
    thread: {
      id: "00000000-0000-0000-0000-000000000001",
      workspaceId: "acme",
      squadId: "build",
      title: "Landing page",
      status: "open",
      ownerUserId: 42,
      coordinatorAgentId: "PM",
      currentOwnerAgentId: null,
      telegramChatId: -100,
      telegramMessageThreadId: 7,
      budgetUsdCap: null,
      costUsdAccum: "1.50",
      createdAt: "2024-06-15T10:00:00Z",
      updatedAt: "2024-06-15T11:00:00Z",
    },
    coordinatorAgentId: "PM",
    participants: [
      { agentId: "PM", role: "coordinator", joinedAt: null, leftAt: null },
      { agentId: "FE", role: "worker", joinedAt: null, leftAt: null },
    ],
    recentMessages: [
      {
        id: 5,
        from: "PM",
        to: null,
        content: "Let's split work",
        type: "agent_text",
        metadata: {},
        createdAt: "2024-06-15T10:55:00Z",
      },
      {
        id: 4,
        from: "user:operator",
        to: null,
        content: "Need a landing page",
        type: "user_input",
        metadata: {},
        createdAt: "2024-06-15T10:30:00Z",
      },
    ],
    activeTasks: [
      {
        id: "00000000-0000-0000-0000-0000000000aa",
        title: "Hero copy",
        status: "claimed",
        assignedAgentId: "FE",
        assignerAgentId: "PM",
        kind: "design",
        version: 2,
      },
    ],
    openTaskCount: 1,
    doneTaskCount: 3,
    ...overrides,
  };
}

function renderClient(threadId = "00000000-0000-0000-0000-000000000001") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SquadThreadPageClient threadId={threadId} />
    </QueryClientProvider>,
  );
}

describe("SquadThreadPageClient", () => {
  // React Query + Testing Library rely on real timers for async waits, so we
  // intentionally do NOT use vi.useFakeTimers here. Relative-timestamp values
  // depend on Date.now() but their exact text is not asserted.

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
    expect(await screen.findByTestId("squad-thread-route")).toHaveTextContent("Loading thread");
  });

  it("renders thread header, participants, messages and tasks", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockResolvedValue(makePayload());
    renderClient();

    await waitFor(() => {
      expect(screen.getByText("Landing page")).toBeInTheDocument();
    });

    // Header bits
    expect(screen.getByText("acme")).toBeInTheDocument();
    expect(screen.getAllByText("PM").length).toBeGreaterThan(0);

    // Participants strip
    const strip = screen.getByTestId("participants-strip");
    expect(strip).toHaveTextContent("Participants (2)");
    expect(strip).toHaveTextContent("PM");
    expect(strip).toHaveTextContent("FE");

    // Message timeline (newest first)
    const rows = screen.getAllByTestId("message-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Let's split work");
    expect(rows[1]).toHaveTextContent("Need a landing page");

    // Active task
    const task = screen.getByTestId("task-row");
    expect(task).toHaveTextContent("Hero copy");
    expect(task).toHaveTextContent("FE");
  });

  it("renders empty states when there are no messages or tasks", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockResolvedValue(
      makePayload({ recentMessages: [], activeTasks: [] }),
    );
    renderClient();
    await waitFor(() => {
      expect(screen.getByText("no messages in this thread yet")).toBeInTheDocument();
    });
    expect(screen.getByText("no active tasks")).toBeInTheDocument();
  });

  it("renders an error state and surfaces the message", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockRejectedValue(new Error("boom"));
    renderClient();
    // The default tier retries once with backoff; allow ample time for the
    // hook to settle into an error state.
    await waitFor(
      () => {
        expect(screen.getByText("Couldn't load thread")).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("posts a message and clears the textarea", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockResolvedValue(makePayload());
    vi.mocked(mutateControlPlaneDashboardJson).mockResolvedValue({ messageId: 99 });
    renderClient();

    await waitFor(() => {
      expect(screen.getByText("Landing page")).toBeInTheDocument();
    });

    const textarea = screen.getByTestId("thread-composer-textarea") as HTMLTextAreaElement;
    const submit = screen.getByTestId("thread-composer-submit");
    expect(submit).toBeDisabled();

    const user = userEvent.setup();
    await user.type(textarea, "noted, on it");
    expect(submit).toBeEnabled();

    await user.click(submit);
    await waitFor(() => {
      expect(mutateControlPlaneDashboardJson).toHaveBeenCalledWith(
        "/squads/threads/00000000-0000-0000-0000-000000000001/messages",
        expect.objectContaining({
          body: { content: "noted, on it", from_agent: "operator" },
        }),
      );
    });
    await waitFor(() => {
      expect(textarea.value).toBe("");
    });
  });

  it("claim button is disabled until acting-as is set", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockResolvedValue(
      makePayload({
        activeTasks: [
          {
            id: "00000000-0000-0000-0000-0000000000aa",
            title: "Hero copy",
            status: "pending",
            assignedAgentId: null,
            assignerAgentId: "PM",
            kind: "design",
            version: 1,
          },
        ],
      }),
    );
    vi.mocked(mutateControlPlaneDashboardJson).mockResolvedValue({ task: {} });
    renderClient();

    await waitFor(() => {
      expect(screen.getByText("Hero copy")).toBeInTheDocument();
    });

    const claim = screen.getByTestId("task-action-claim") as HTMLButtonElement;
    expect(claim).toBeDisabled();

    const user = userEvent.setup();
    const actingAs = screen.getByTestId("thread-acting-as") as HTMLInputElement;
    await user.type(actingAs, "FE");
    expect(claim).toBeEnabled();

    await user.click(claim);
    await waitFor(() => {
      expect(mutateControlPlaneDashboardJson).toHaveBeenCalledWith(
        "/squads/tasks/00000000-0000-0000-0000-0000000000aa/claim",
        expect.objectContaining({ body: { agent_id: "FE" } }),
      );
    });
  });

  it("surfaces task action errors via the inline alert", async () => {
    vi.mocked(fetchControlPlaneDashboardJson).mockResolvedValue(makePayload());
    vi.mocked(mutateControlPlaneDashboardJson).mockRejectedValue(new Error("ownership"));
    renderClient();

    await waitFor(() => {
      expect(screen.getByText("Hero copy")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const actingAs = screen.getByTestId("thread-acting-as") as HTMLInputElement;
    await user.type(actingAs, "BE");
    const complete = screen.getByTestId("task-action-complete") as HTMLButtonElement;
    expect(complete).toBeEnabled();
    await user.click(complete);

    await waitFor(() => {
      expect(screen.getByTestId("thread-action-error")).toHaveTextContent("ownership");
    });
  });
});
