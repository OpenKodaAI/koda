import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ExecutionDetailContent } from "@/components/executions/execution-detail-content";
import type { ExecutionDetail } from "@/lib/types";

const detail: ExecutionDetail = {
  task_id: 351,
  bot_id: "KODA",
  status: "completed",
  query_text: "Retry the morning digest after connector throttling",
  response_text: null,
  model: "gpt-5.2",
  session_id: null,
  work_dir: null,
  user_id: 1,
  chat_id: 1,
  created_at: "2026-05-02T08:00:00.000Z",
  started_at: "2026-05-02T08:00:10.000Z",
  completed_at: "2026-05-02T08:00:40.000Z",
  cost_usd: 0.12,
  duration_ms: 30_000,
  attempt: 1,
  max_attempts: 3,
  error_message: null,
  stop_reason: "completed",
  warnings: [],
  has_rich_trace: true,
  trace_source: "trace",
  response_source: "missing",
  tools_source: "missing",
  tool_count: 0,
  timeline: [],
  tools: [],
  reasoning_summary: [],
  artifacts: [],
  redactions: null,
};

describe("ExecutionDetailContent", () => {
  function renderDetail(ui: React.ReactNode) {
    return render(<I18nProvider initialLanguage="en-US">{ui}</I18nProvider>);
  }

  it("uses a theme-safe primary CTA for the operational room link", () => {
    renderDetail(<ExecutionDetailContent data={detail} variant="drawer" />);

    const link = screen.getByRole("link", { name: /operational room|sala operacional/i });
    expect(link).toHaveAttribute("href", "/runtime/KODA/tasks/351");
    expect(link).toHaveClass("button-shell", "button-shell--primary", "button-shell--sm");
    expect(link).not.toHaveClass("button-pill", "is-active");
  });

  it("renders granular visuals for metadata, timeline, tools, and artifacts", () => {
    const { container } = renderDetail(
      <ExecutionDetailContent
        data={{
          ...detail,
          tool_count: 2,
          warnings: ["knowledge resolution unavailable"],
          response_source: "trace",
          tools_source: "trace",
          timeline: [
            {
              id: "policy",
              type: "policy_gate",
              title: "Policy gate",
              summary: "Write tool requires approval.",
              status: "warning",
              timestamp: "2026-05-02T08:00:20.000Z",
              details: {},
            },
          ],
          tools: [
            {
              id: "tool-shell",
              tool: "shell_execute",
              category: "shell",
              success: true,
              duration_ms: 250,
              started_at: "2026-05-02T08:00:21.000Z",
              completed_at: "2026-05-02T08:00:22.000Z",
              params: { command: "ls" },
              output: "ok",
              metadata: { binary: "ls", args: "-la" },
              summary: "Listed files.",
              redactions: null,
            },
            {
              id: "tool-file",
              tool: "file_write",
              category: "fileops",
              success: false,
              duration_ms: 120,
              started_at: "2026-05-02T08:00:23.000Z",
              completed_at: "2026-05-02T08:00:24.000Z",
              params: { path: "notes.md" },
              output: null,
              metadata: { path: "notes.md", denied: true },
              summary: "Write was denied.",
              redactions: { count: 1, fields: ["params.path"] },
            },
          ],
          artifacts: [
            {
              id: "artifact-json",
              label: "Replay bundle",
              kind: "json",
              content: { replay_mode: "offline" },
            },
          ],
        }}
        variant="drawer"
      />,
    );

    expect(container.querySelector('[data-metadata-visual="cost"]')).toBeInTheDocument();
    expect(container.querySelector('[data-metadata-visual="trace_source"]')).toBeInTheDocument();
    expect(container.querySelector('[data-timeline-visual="policy_gate"]')).toBeInTheDocument();
    expect(container.querySelector('[data-tool-visual="shell"]')).toBeInTheDocument();
    expect(container.querySelector('[data-tool-visual="file_write"]')).toBeInTheDocument();
    expect(screen.getByText("Trace response")).toHaveClass("max-w-full", "whitespace-normal", "break-words");
    expect(screen.getByText("Structured tools")).toHaveClass("max-w-full", "whitespace-normal", "break-words");
    expect(screen.getByText("knowledge resolution unavailable")).toHaveClass("break-words");
    expect(screen.getByText("Shell command")).toBeInTheDocument();
    expect(screen.getByText("File write")).toBeInTheDocument();
    expect(screen.getByText("JSON artifact")).toBeInTheDocument();
  });
});
