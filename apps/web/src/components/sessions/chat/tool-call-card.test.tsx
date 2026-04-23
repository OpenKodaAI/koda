import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToolCallCard } from "@/components/sessions/chat/tool-call-card";
import type { ExecutionSummary } from "@/lib/types";

function baseExecution(overrides: Partial<ExecutionSummary> = {}): ExecutionSummary {
  return {
    task_id: 1042,
    bot_id: "ATLAS",
    status: "completed",
    query_text: "List files in /tmp",
    model: "claude-opus-4-6",
    session_id: "session-1",
    user_id: 101,
    chat_id: 1,
    created_at: "2026-03-28T10:00:00.000Z",
    started_at: "2026-03-28T10:00:01.000Z",
    completed_at: "2026-03-28T10:00:03.200Z",
    cost_usd: 0.12,
    duration_ms: 3200,
    attempt: 1,
    max_attempts: 3,
    has_rich_trace: true,
    trace_source: "trace",
    tool_count: 2,
    warning_count: 0,
    stop_reason: null,
    error_message: null,
    ...overrides,
  };
}

describe("ToolCallCard", () => {
  it("starts collapsed and exposes status + duration", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ToolCallCard execution={baseExecution()} />
      </I18nProvider>,
    );
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveTextContent(/Completed/i);
  });

  it("expands on click and calls onOpenDetails with task id", async () => {
    const onOpenDetails = vi.fn();
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <ToolCallCard execution={baseExecution()} onOpenDetails={onOpenDetails} />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /#1042/i }));
    const viewExecution = screen.getByRole("button", { name: /View execution/i });
    await user.click(viewExecution);

    expect(onOpenDetails).toHaveBeenCalledWith(1042);
  });

  it("surfaces the error message when the execution failed", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <ToolCallCard
          execution={baseExecution({ status: "failed", error_message: "Permission denied" })}
        />
      </I18nProvider>,
    );
    await user.click(screen.getByRole("button", { name: /#1042/i }));
    expect(screen.getByText("Permission denied")).toBeInTheDocument();
  });
});
