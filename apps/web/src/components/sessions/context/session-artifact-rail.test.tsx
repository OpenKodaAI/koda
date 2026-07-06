import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { SessionArtifactRail } from "@/components/sessions/context/session-artifact-rail";
import { ToastProvider } from "@/hooks/use-toast";
import type { RoomEntry } from "@/hooks/use-rooms";
import type { SessionDetail, SessionSummary } from "@/lib/types";

const summary: SessionSummary = {
  bot_id: "ATLAS",
  session_id: "session-alpha",
  name: "Alpha conversation",
  user_id: 1,
  created_at: "2026-03-28T10:00:00.000Z",
  last_used: "2026-03-28T10:05:00.000Z",
  last_activity_at: "2026-03-28T10:05:00.000Z",
  query_count: 1,
  execution_count: 1,
  total_cost_usd: 0.1,
  running_count: 0,
  failed_count: 0,
  latest_status: "completed",
  latest_query_preview: "Create a file",
  latest_response_preview: "Done",
  latest_message_preview: "Done",
};

function detailWithArtifacts(): SessionDetail {
  return {
    summary,
    messages: [
      {
        id: "message-1",
        role: "assistant",
        text: "Done",
        timestamp: "2026-03-28T10:05:00.000Z",
        model: "gpt-5.4",
        cost_usd: 0.1,
        query_id: 1,
        session_id: "session-alpha",
        error: false,
        artifacts: [
          {
            id: "artifact-1",
            label: "Digest",
            kind: "text",
            content: null,
            description: "Digest",
            summary: "Digest",
            url: null,
            path: "/runtime/tasks/1/artifacts/digest.md",
            mime_type: "text/markdown",
            size_bytes: 42,
            source_type: "runtime_artifact",
            status: "complete",
            text_content: null,
            metadata: {},
          },
        ],
      },
    ],
    orphan_executions: [],
    totals: { messages: 1, executions: 1, tools: 0, cost_usd: 0.1 },
    page: { limit: 1, returned: 1, next_cursor: null, has_more: false },
  };
}

const room: RoomEntry = {
  sortKey: "2026-03-28T10:05:00.000Z",
  squad: {
    squadId: "DEMO_SQUAD",
    workspaceId: "workspace-1",
    coordinatorAgentId: "ATLAS",
    threadCounts: { open: 1, paused: 0, completed: 0, archived: 0 },
    taskCounts: {
      pending: 0,
      claimed: 0,
      in_progress: 0,
      blocked: 0,
      done: 0,
      failed: 0,
      cancelled: 0,
      escalated: 0,
    },
    memberCount: 3,
    lastActiveAt: "2026-03-28T10:05:00.000Z",
    totalCostUsd: "0",
  },
  thread: {
    id: "room-1",
    workspaceId: "workspace-1",
    squadId: "DEMO_SQUAD",
    title: "Smoke test room",
    status: "open",
    coordinatorAgentId: "ATLAS",
    currentOwnerAgentId: null,
    telegramChatId: null,
    telegramMessageThreadId: null,
    costUsdAccum: "0",
    photoUrl: null,
    createdAt: "2026-03-28T10:00:00.000Z",
    updatedAt: "2026-03-28T10:05:00.000Z",
    completedAt: null,
  },
};

function renderRail(ui: ReactNode) {
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
                color: "#ff5a5a",
                colorRgb: "255, 90, 90",
                initials: "AT",
                status: "active",
                model: "Claude Sonnet",
              },
              {
                id: "SAGE",
                label: "Sage",
                color: "#5b8cff",
                colorRgb: "91, 140, 255",
                initials: "SA",
                status: "active",
                model: "Claude Sonnet",
              },
              {
                id: "NOVA",
                label: "Nova",
                color: "#56c271",
                colorRgb: "86, 194, 113",
                initials: "NO",
                status: "active",
                model: "Claude Sonnet",
              },
            ]}
          >
            {ui}
          </AgentCatalogProvider>
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("SessionArtifactRail", () => {
  beforeEach(() => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/control-plane/dashboard/squads/threads/room-1")) {
        return new Response(
          JSON.stringify({
            thread: {
              id: "room-1",
              workspaceId: "workspace-1",
              squadId: "DEMO_SQUAD",
              title: "Smoke test room",
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
              {
                agentId: "SAGE",
                role: "worker",
                joinedAt: "2026-03-28T10:00:00.000Z",
                leftAt: null,
              },
              {
                agentId: "NOVA",
                role: "worker",
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
      if (url.includes("/api/control-plane/agents")) {
        return new Response(
          JSON.stringify({
            items: [
              { id: "ATLAS", status: "active" },
              { id: "SAGE", status: "active" },
              { id: "NOVA", status: "active" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`Unhandled fetch: ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not render a conversation panel when there are no files", () => {
    renderRail(
      <SessionArtifactRail
        detail={{ ...detailWithArtifacts(), messages: [] }}
        summary={summary}
      />,
    );

    expect(screen.queryByLabelText("Session details")).not.toBeInTheDocument();
  });

  it("renders real conversation files and can be collapsed", () => {
    const onOpenChange = vi.fn();
    renderRail(
      <SessionArtifactRail
        detail={detailWithArtifacts()}
        summary={summary}
        open
        onOpenChange={onOpenChange}
      />,
    );

    expect(screen.getByText("Files")).toBeInTheDocument();
    expect(screen.getByText("digest.md")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /collapse panel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders full room details inline without a settings drawer button", async () => {
    renderRail(
      <SessionArtifactRail
        detail={null}
        summary={null}
        room={room}
      />,
    );

    expect(await screen.findByDisplayValue("Smoke test room")).toBeInTheDocument();
    expect(screen.getByText("3 members")).toBeInTheDocument();
    expect(screen.queryByText("Thread ID")).not.toBeInTheDocument();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.queryByText("Files")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /room settings/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /collapse panel/i })).not.toBeInTheDocument();
  });

  it("renders room reply obligations from backend-shaped thread messages", () => {
    renderRail(
      <SessionArtifactRail
        detail={null}
        summary={null}
        room={room}
        roomThreadMessages={[
          {
            id: 11,
            messageUuid: "msg-11",
            from: "ATLAS",
            to: null,
            toAgentIds: ["SAGE"],
            content: "Sage, please verify the source list.",
            type: "agent_request",
            payload: {},
            metadata: {},
            causationId: null,
            correlationId: "corr-1",
            inReplyTo: "msg-10",
            requiresResponseBy: "2026-03-28T10:15:00.000Z",
            idempotencyKey: null,
            replyObligations: [
              {
                id: 1,
                obligationKey: "reply:room-1:11:SAGE",
                threadId: "room-1",
                sourceMessageId: 11,
                targetAgentId: "SAGE",
                status: "open",
                requiresResponseBy: "2026-03-28T10:15:00.000Z",
                resolvedByMessageId: null,
                followupCount: 0,
                lastFollowupAt: null,
                metadata: {},
              },
            ],
            replySummary: { open: 1, answered: 0 },
            createdAt: "2026-03-28T10:05:00.000Z",
          },
        ]}
      />,
    );

    expect(screen.getByText("Thread")).toBeInTheDocument();
    expect(screen.getByText("Waiting")).toBeInTheDocument();
    expect(screen.getByText("SAGE")).toBeInTheDocument();
    expect(screen.getByText("Sage, please verify the source list.")).toBeInTheDocument();
  });
});
