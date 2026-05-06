import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { CronTable, type CronTableRow } from "@/components/schedules/cron-table";

const rows: CronTableRow[] = [
  {
    agent: {
      id: "ATLAS",
      label: "Atlas",
      color: "#5b8cff",
      colorRgb: "91, 140, 255",
    },
    job: {
      id: 42,
      bot_id: "ATLAS",
      user_id: 1,
      chat_id: 1,
      command: "Summarize yesterday's operations.",
      summary: "Daily operations summary",
      description: "Summarize yesterday's operations.",
      status: "active",
      enabled: 1,
      schedule_expr: "0 9 * * *",
      cron_expression: "0 9 * * *",
      timezone: "UTC",
      next_run_at: "2026-05-07T09:00:00.000Z",
      work_dir: "/workspace",
      payload: { name: "Daily operations summary" },
      provider_preference: null,
      model_preference: null,
      created_at: "2026-05-06T09:00:00.000Z",
      updated_at: "2026-05-06T09:00:00.000Z",
      last_run_at: null,
      last_success_at: null,
      last_failure_at: null,
      config_version: 1,
    },
  },
];

describe("CronTable", () => {
  it("renders stable rows without entrance animation classes on data refreshes", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <CronTable rows={rows} />
      </I18nProvider>,
    );

    const row = screen.getAllByRole("row")[1];
    expect(row).toBeTruthy();
    expect(row).not.toHaveClass("animate-in");
  });
});
