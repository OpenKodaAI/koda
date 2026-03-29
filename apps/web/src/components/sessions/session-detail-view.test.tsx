import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { SessionDetailView } from "@/components/sessions/session-detail-view";
import type { SessionDetail } from "@/lib/types";

const detail: SessionDetail = {
  summary: {
    bot_id: "ATLAS",
    session_id: "session-1",
    name: "Deploy review",
    user_id: 101,
    created_at: "2026-03-28T10:00:00.000Z",
    last_used: "2026-03-28T10:01:00.000Z",
    last_activity_at: "2026-03-28T10:01:00.000Z",
    query_count: 1,
    execution_count: 1,
    total_cost_usd: 1.25,
    running_count: 0,
    failed_count: 0,
    latest_status: "completed",
    latest_query_preview: "Deploy release",
    latest_response_preview: "Done",
    latest_message_preview: "Done",
  },
  messages: [
    {
      id: "query-1-user",
      role: "user",
      text: "Deploy release",
      timestamp: "2026-03-28T10:00:00.000Z",
      model: null,
      cost_usd: null,
      query_id: 1,
      session_id: "session-1",
      error: false,
    },
    {
      id: "query-1-assistant",
      role: "assistant",
      text: "Done",
      timestamp: "2026-03-28T10:01:00.000Z",
      model: "claude-opus-4-6",
      cost_usd: 1.25,
      query_id: 1,
      session_id: "session-1",
      error: false,
      linked_execution: {
        task_id: 77,
        bot_id: "ATLAS",
        status: "completed",
        query_text: "Deploy release",
        model: "claude-opus-4-6",
        session_id: "session-1",
        user_id: 101,
        chat_id: 202,
        created_at: "2026-03-28T10:00:00.000Z",
        started_at: "2026-03-28T10:00:05.000Z",
        completed_at: "2026-03-28T10:01:05.000Z",
        cost_usd: 1.25,
        duration_ms: 60000,
        attempt: 1,
        max_attempts: 3,
        has_rich_trace: false,
        trace_source: "missing",
        tool_count: 2,
        warning_count: 0,
        stop_reason: "completed",
        error_message: null,
        feedback_status: "approved",
        retrieval_strategy: "hybrid",
        answer_gate_status: "approved",
        answer_gate_reasons: ["approved"],
        post_write_review_required: false,
        stale_sources_present: false,
        ungrounded_operationally: false,
        source_ref_count: 1,
        winning_source_count: 1,
        provenance_source: "episode",
      },
    },
  ],
  orphan_executions: [],
  totals: {
    messages: 2,
    executions: 1,
    tools: 2,
    cost_usd: 1.25,
  },
};

describe("SessionDetailView", () => {
  it("renders feedback and provenance metadata for linked executions", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <SessionDetailView detail={detail} />
      </I18nProvider>,
    );

    expect(screen.getByText("feedback: approved")).toBeInTheDocument();
    expect(screen.getByText("provenance: hybrid")).toBeInTheDocument();
    expect(screen.getByText("gate: approved")).toBeInTheDocument();
  });
});
