import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DLQTable } from "@/components/dlq/dlq-table";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { DLQEntry } from "@/lib/types";

const entry: DLQEntry = {
  id: 16,
  task_id: 351,
  user_id: 1,
  chat_id: 1,
  bot_id: "KODA",
  pod_name: null,
  query_text: "Retry the morning digest after connector throttling",
  model: "gpt-5.2",
  error_message: "Connector throttled the final artifact upload.",
  error_class: "TransientProviderError",
  attempt_count: 2,
  original_created_at: "2026-05-02T08:00:00.000Z",
  failed_at: "2026-05-02T08:05:00.000Z",
  retry_eligible: 1,
  retried_at: null,
  metadata_json: "{}",
};

describe("DLQTable", () => {
  it("uses the shared sticky-last table shell without clipping status content", () => {
    const { container } = render(
      <I18nProvider initialLanguage="en-US">
        <DLQTable entries={[entry]} selectedEntryId={entry.id} onEntryClick={() => {}} />
      </I18nProvider>,
    );

    const shell = container.querySelector(".table-shell");
    expect(shell).toBeInTheDocument();
    expect(shell).toHaveStyle("--sticky-last-width: 192px");

    const table = container.querySelector("table");
    expect(table).toHaveClass("glass-table", "glass-table--sticky-last", "min-w-[1340px]");

    const statusHeader = screen.getByText("Status").closest("th");
    expect(statusHeader).toHaveClass("text-right");
    expect(statusHeader).not.toHaveClass("pr-0");

    const statusCell = Array.from(table?.querySelectorAll("td") ?? []).find((cell) =>
      cell.textContent?.includes("Can retry"),
    );
    expect(statusCell).toHaveClass("text-right");
    expect(statusCell).not.toHaveClass("pr-0");
  });
});
