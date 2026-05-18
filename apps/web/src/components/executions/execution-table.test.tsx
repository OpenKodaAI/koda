import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExecutionTable } from "@/components/executions/execution-table";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { ExecutionSummary } from "@/lib/types";

const execution: ExecutionSummary = {
  task_id: 351,
  bot_id: "KODA",
  status: "completed",
  query_text: "Retry the morning digest after connector throttling",
  model: "gpt-5.2",
  session_id: null,
  user_id: 1,
  chat_id: 1,
  created_at: "2026-05-02T08:00:00.000Z",
  started_at: "2026-05-02T08:00:10.000Z",
  completed_at: "2026-05-02T08:00:40.000Z",
  cost_usd: 0.12,
  duration_ms: 30_000,
  attempt: 1,
  max_attempts: 3,
  has_rich_trace: true,
  trace_source: "trace",
  tool_count: 3,
  warning_count: 0,
  stop_reason: "completed",
  error_message: null,
};

describe("ExecutionTable", () => {
  it("keeps the desktop execution status column non-sticky while the table scrolls normally", () => {
    const { container } = render(
      <I18nProvider initialLanguage="en-US">
        <ExecutionTable
          executions={[execution]}
          selectedExecutionId={execution.task_id}
          onExecutionClick={() => {}}
        />
      </I18nProvider>,
    );

    const desktopScroller = container.querySelector(".overflow-x-auto.overscroll-x-contain");
    expect(desktopScroller).toBeInTheDocument();

    const desktopSurface = Array.from(container.querySelectorAll("div")).find((node) =>
      node.className.includes("min-w-[960px]"),
    );
    expect(desktopSurface).toBeInTheDocument();

    expect(container.querySelector(".sticky-table-last")).not.toBeInTheDocument();
    expect(container.querySelector(".sticky-table-last--header")).not.toBeInTheDocument();
    expect(container.querySelector(".sticky-table-row")).not.toBeInTheDocument();
    expect(container.querySelector(".sticky-table-row--selected")).not.toBeInTheDocument();

    const statusHeader = Array.from(container.querySelectorAll('[role="row"] span')).find(
      (node) => node.textContent === "Status",
    );
    expect(statusHeader).toHaveClass("pr-4");
    expect(statusHeader).not.toHaveClass("sticky-table-last");

    const desktopRow = container.querySelector("button.grid");
    expect(desktopRow).toHaveClass("bg-[var(--table-row-selected)]");

    const statusCell = Array.from(desktopRow?.querySelectorAll("span") ?? []).find((node) =>
      node.textContent?.includes("Completed"),
    );
    expect(statusCell).toHaveClass("pr-4");
    expect(statusCell).not.toHaveClass("sticky-table-last");
  });
});
