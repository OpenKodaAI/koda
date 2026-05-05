import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { CronTable, type CronTableRow } from "@/components/schedules/cron-table";

vi.mock("@/components/control-plane/shared/agent-sigil", () => ({
  AgentSigil: ({ label }: { label?: string | null }) => (
    <span data-testid="agent-sigil">{label}</span>
  ),
}));

const rows: CronTableRow[] = [
  {
    agent: {
      id: "atlas",
      label: "Atlas",
      color: "#D97757",
      colorRgb: "217, 119, 87",
    },
    job: {
      id: 101,
      bot_id: "atlas",
      user_id: 1,
      chat_id: null,
      cron_expression: "0 9 * * MON-FRI",
      trigger_type: "cron",
      schedule_expr: "0 9 * * MON-FRI",
      timezone: "America/Sao_Paulo",
      summary: "Daily operator brief",
      command: "Prepare the daily operator brief.",
      description: "Review incidents, blockers, and handoff notes.",
      created_at: null,
      enabled: 1,
      status: "active",
      work_dir: "/workspace/atlas",
      next_run_at: "2026-05-05T12:00:00Z",
      last_run_at: "2026-05-04T12:00:00Z",
    },
  },
  {
    agent: {
      id: "forge",
      label: "Forge",
      color: "#6E97D9",
      colorRgb: "110, 151, 217",
    },
    job: {
      id: 102,
      bot_id: "forge",
      user_id: 1,
      chat_id: null,
      cron_expression: "0 13 * * 1",
      trigger_type: "cron",
      schedule_expr: "0 13 * * 1",
      timezone: "UTC",
      payload: { name: "Dependency review" },
      command: "Audit dependency updates.",
      description: "",
      created_at: null,
      enabled: 0,
      status: "paused",
      work_dir: "/workspace/forge",
      next_run_at: null,
      last_run_at: null,
    },
  },
];

function renderTable(overrides: Partial<ComponentProps<typeof CronTable>> = {}) {
  return render(
    <I18nProvider initialLanguage="en-US">
      <CronTable rows={rows} {...overrides} />
    </I18nProvider>,
  );
}

describe("CronTable", () => {
  it("renders multiple agents in one unified schedule table", () => {
    renderTable();

    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: /agent/i })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: /execution/i })).not.toBeInTheDocument();
    expect(within(table).getAllByText("Atlas")).toHaveLength(2);
    expect(within(table).getAllByText("Forge")).toHaveLength(2);
    expect(within(table).getByText("Daily operator brief")).toBeInTheDocument();
    expect(within(table).getByText("Dependency review")).toBeInTheDocument();
  });

  it("keeps row actions available from the compact action rail", () => {
    const onExecutions = vi.fn();
    const onRun = vi.fn();
    const onLifecycleAction = vi.fn();
    renderTable({ onExecutions, onRun, onLifecycleAction });

    const table = screen.getByRole("table");
    fireEvent.click(within(table).getAllByRole("button", { name: "Executions" })[0]);
    fireEvent.click(within(table).getAllByRole("button", { name: "Run now" })[0]);
    fireEvent.click(within(table).getAllByRole("button", { name: "Pause" })[0]);

    expect(onExecutions).toHaveBeenCalledWith(rows[0].job);
    expect(onRun).toHaveBeenCalledWith(rows[0].job);
    expect(onLifecycleAction).toHaveBeenCalledWith(rows[0].job, "pause");
  });

  it("shows per-action request states on command buttons", () => {
    renderTable({
      busyJobId: rows[0].job.id,
      actionStates: {
        [rows[0].job.id]: {
          executions: "success",
          run: "pending",
          lifecycle: "error",
        },
      },
    });

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("button", { name: "Executions" })[0]).toHaveAttribute(
      "data-action-state",
      "success",
    );
    expect(within(table).getAllByRole("button", { name: "Run now" })[0]).toHaveAttribute(
      "data-action-state",
      "pending",
    );
    expect(within(table).getAllByRole("button", { name: "Pause" })[0]).toHaveAttribute(
      "data-action-state",
      "error",
    );
  });
});
