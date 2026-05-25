import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorDetail } from "@/components/dlq/error-detail";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { DLQEntry } from "@/lib/types";

const entry: DLQEntry = {
  id: 16,
  task_id: 351,
  user_id: 1,
  chat_id: 1,
  bot_id: "KODA",
  pod_name: "docs-demo",
  query_text: "Retry the morning digest after connector throttling",
  model: "gpt-5.2",
  error_message: "Connector throttled the final artifact upload.",
  error_class: "TransientProviderError",
  attempt_count: 2,
  original_created_at: "2026-05-02T08:00:00.000Z",
  failed_at: "2026-05-02T08:05:00.000Z",
  retry_eligible: 1,
  retried_at: null,
  metadata_json: JSON.stringify({
    provider: "openai",
    trace_id: "trace-351",
    retryable: true,
  }),
};

describe("ErrorDetail", () => {
  it("renders compact DLQ detail samples and metadata without oversized KPI cards", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ErrorDetail entry={entry} onClose={vi.fn()} />
      </I18nProvider>,
    );

    expect(screen.getByRole("dialog", { name: /DLQ entry details 16/i })).toBeInTheDocument();
    expect(document.querySelector(".app-kpi-card")).not.toBeInTheDocument();

    const querySample = screen.getByText(entry.query_text).closest("pre");
    expect(querySample).toHaveClass("max-h-32", "text-xs");

    const failureSample = screen
      .getAllByText(entry.error_message)
      .find((node) => node.closest("pre"))
      ?.closest("pre");
    expect(failureSample).toHaveClass("max-h-32", "text-xs");

    const metadataSample = screen.getByText(/trace-351/).closest("pre");
    expect(metadataSample).toHaveClass("max-h-[220px]", "text-xs");
  });
});
