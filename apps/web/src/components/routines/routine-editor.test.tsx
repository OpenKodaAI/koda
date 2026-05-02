import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { RoutineEditor } from "@/components/routines/routine-editor";
import type { AgentDisplay } from "@/lib/agent-constants";
import type { CronJob } from "@/lib/types";

const AGENTS: AgentDisplay[] = [
  { id: "alpha", label: "Alpha", color: "#D97757", colorRgb: "217, 119, 87" },
  { id: "beta", label: "Beta", color: "#6E97D9", colorRgb: "110, 151, 217" },
];

function renderEditor(
  overrides: Partial<React.ComponentProps<typeof RoutineEditor>> = {},
) {
  const onSubmit = vi.fn(() => Promise.resolve());
  const onOpenChange = vi.fn();

  const defaults: React.ComponentProps<typeof RoutineEditor> = {
    open: true,
    onOpenChange,
    mode: "create",
    agents: AGENTS,
    onSubmit,
  };

  const utils = render(
    <I18nProvider initialLanguage="en-US">
      <RoutineEditor {...defaults} {...overrides} />
    </I18nProvider>,
  );

  return { ...utils, onSubmit, onOpenChange };
}

describe("RoutineEditor", () => {
  it("renders the create form with empty fields", async () => {
    renderEditor();

    expect(await screen.findByText(/new routine/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Daily code review/i)).toHaveValue("");
    expect(
      screen.getByPlaceholderText(/Describe what the agent should do/i),
    ).toHaveValue("");
  });

  it("blocks submit until name and instructions are filled", async () => {
    const { onSubmit } = renderEditor();

    const submit = await screen.findByRole("button", { name: /create routine/i });
    fireEvent.click(submit);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
  });

  it("emits a normalized payload when create form is filled", async () => {
    const { onSubmit } = renderEditor();

    fireEvent.change(screen.getByPlaceholderText(/Daily code review/i), {
      target: { value: "Daily review" },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/Describe what the agent should do/i),
      { target: { value: "Look for regressions in main." } },
    );

    fireEvent.click(await screen.findByRole("button", { name: /create routine/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));

    const payload = onSubmit.mock.calls[0][0];
    expect(payload.name).toBe("Daily review");
    expect(payload.instructions).toBe("Look for regressions in main.");
    expect(payload.agentId).toBe("alpha");
    expect(payload.triggerKind).toBe("schedule");
    expect(payload.scheduleMode).toBe("recurring");
    expect(payload.triggerType).toBe("cron");
    expect(payload.scheduleExpr).toMatch(/^0 9 \* \* \*$/);
    expect(payload.connectors).toEqual([]);
    expect(payload.notificationMode).toBe("summary_complete");
    expect(payload.verificationMode).toBe("post_write_if_any");
  });

  it("prefills fields in edit mode from an existing job", async () => {
    const job: CronJob = {
      id: 42,
      bot_id: "beta",
      user_id: 1,
      chat_id: null,
      cron_expression: "30 8 * * 1",
      trigger_type: "cron",
      schedule_expr: "30 8 * * 1",
      timezone: "America/Sao_Paulo",
      summary: "Weekly status",
      command: "Generate weekly status report",
      description: "",
      created_at: null,
      enabled: 1,
      status: "active",
      work_dir: "/repo",
      provider_preference: "anthropic",
      model_preference: "claude-opus-4-7",
      payload: { query: "Generate weekly status report" },
      notification_policy: { mode: "failures_only" },
      verification_policy: { mode: "task_success" },
    };

    renderEditor({ mode: "edit", job });

    expect(await screen.findByText(/Edit routine #42/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Daily code review/i)).toHaveValue(
      "Weekly status",
    );
    expect(
      screen.getByPlaceholderText(/Describe what the agent should do/i),
    ).toHaveValue("Generate weekly status report");
    expect(
      screen.getByRole("button", { name: /save changes/i }),
    ).toBeInTheDocument();
  });
});
