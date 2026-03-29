import { describe, expect, it } from "vitest";
import type { ExecutionSummary } from "@/lib/types";
import { buildOperationalSessionDetail } from "@/lib/runtime-dashboard";

describe("buildOperationalSessionDetail", () => {
  it("does not invent assistant replies in degraded runtime sessions", () => {
    const executions: ExecutionSummary[] = [
      {
        task_id: 42,
        bot_id: "ATLAS",
        status: "completed",
        query_text: "Need a deploy status update",
        model: "claude-opus-4-6",
        session_id: "session-1",
        user_id: 101,
        chat_id: 202,
        created_at: "2026-03-28T10:00:00.000Z",
        started_at: "2026-03-28T10:00:05.000Z",
        completed_at: "2026-03-28T10:00:30.000Z",
        cost_usd: 1.25,
        duration_ms: 25000,
        attempt: 1,
        max_attempts: 3,
        has_rich_trace: false,
        trace_source: "missing",
        tool_count: 0,
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
        source_ref_count: 2,
        winning_source_count: 1,
        provenance_source: "episode",
      },
    ];

    const detail = buildOperationalSessionDetail("ATLAS", "session-1", executions);

    expect(detail.messages).toHaveLength(1);
    expect(detail.messages[0].role).toBe("user");
    expect(detail.messages[0].text).toBe("Need a deploy status update");
    expect(detail.messages[0].linked_execution?.feedback_status).toBe("approved");
    expect(detail.orphan_executions).toHaveLength(0);
  });

  it("keeps execution-only rows in orphan_executions", () => {
    const executions: ExecutionSummary[] = [
      {
        task_id: 99,
        bot_id: "ATLAS",
        status: "failed",
        query_text: null,
        model: "claude-sonnet-4-6",
        session_id: "session-2",
        user_id: 101,
        chat_id: 202,
        created_at: "2026-03-28T11:00:00.000Z",
        started_at: null,
        completed_at: null,
        cost_usd: 0.2,
        duration_ms: null,
        attempt: 1,
        max_attempts: 3,
        has_rich_trace: false,
        trace_source: "missing",
        tool_count: 0,
        warning_count: 1,
        stop_reason: "failed",
        error_message: "No assistant response captured",
        feedback_status: "pending",
        retrieval_strategy: null,
        answer_gate_status: null,
        answer_gate_reasons: [],
        post_write_review_required: false,
        stale_sources_present: false,
        ungrounded_operationally: false,
        source_ref_count: 0,
        winning_source_count: 0,
        provenance_source: "missing",
      },
    ];

    const detail = buildOperationalSessionDetail("ATLAS", "session-2", executions);

    expect(detail.messages).toHaveLength(0);
    expect(detail.orphan_executions).toHaveLength(1);
    expect(detail.orphan_executions[0].task_id).toBe(99);
  });
});
