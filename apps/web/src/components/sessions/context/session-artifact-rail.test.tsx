import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/components/providers/i18n-provider";
import { SessionArtifactRail } from "@/components/sessions/context/session-artifact-rail";
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
  return render(<I18nProvider initialLanguage="en-US">{ui}</I18nProvider>);
}

describe("SessionArtifactRail", () => {
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

  it("renders room context without inventing files", () => {
    const onOpenRoomSettings = vi.fn();
    renderRail(
      <SessionArtifactRail
        detail={null}
        summary={null}
        room={room}
        onOpenRoomSettings={onOpenRoomSettings}
      />,
    );

    expect(screen.getByText("Room")).toBeInTheDocument();
    expect(screen.getByText("Smoke test room")).toBeInTheDocument();
    expect(screen.getByText("3 agents")).toBeInTheDocument();
    expect(screen.queryByText("Files")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /room settings/i }));
    expect(onOpenRoomSettings).toHaveBeenCalledTimes(1);
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
