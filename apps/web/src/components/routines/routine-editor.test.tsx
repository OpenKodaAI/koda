import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { RoutineEditor } from "@/components/routines/routine-editor";
import type { AgentDisplay } from "@/lib/agent-constants";
import type { CronJob } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/routines/schedules",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/agent-switcher", () => ({
  AgentSwitcher: ({
    activeBotId,
    onAgentChange,
    disabled,
  }: {
    activeBotId?: string;
    onAgentChange?: (id: string | undefined) => void;
    disabled?: boolean;
  }) => (
    <select
      aria-label="Agent"
      data-testid="agent-switcher-mock"
      value={activeBotId ?? ""}
      disabled={disabled}
      onChange={(event) => onAgentChange?.(event.target.value || undefined)}
    >
      <option value="alpha">Alpha</option>
      <option value="beta">Beta</option>
    </select>
  ),
}));

beforeAll(() => {
  if (typeof window !== "undefined" && !window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

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
      <AgentCatalogProvider initialAgents={AGENTS}>
        <RoutineEditor {...defaults} {...overrides} />
      </AgentCatalogProvider>
    </I18nProvider>,
  );

  return { ...utils, onSubmit, onOpenChange };
}

describe("RoutineEditor", () => {
  it("opens at the Basics step with empty fields", async () => {
    renderEditor();

    expect(await screen.findByText(/new routine/i)).toBeInTheDocument();
    expect(screen.getByText(/basics/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Daily code review/i)).toHaveValue("");
    expect(
      screen.getByPlaceholderText(/Describe what the agent should do/i),
    ).toHaveValue("");
  });

  it("blocks Next until name and instructions are filled", async () => {
    renderEditor();

    const next = await screen.findByRole("button", { name: /next/i });
    fireEvent.click(next);

    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    // Still on Basics step.
    expect(screen.getByPlaceholderText(/Daily code review/i)).toBeInTheDocument();
  });

  it("walks through all three steps and submits a normalized payload", async () => {
    const { onSubmit } = renderEditor();

    // Step 1: Basics
    fireEvent.change(screen.getByPlaceholderText(/Daily code review/i), {
      target: { value: "Daily review" },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/Describe what the agent should do/i),
      { target: { value: "Look for regressions in main." } },
    );
    fireEvent.click(await screen.findByRole("button", { name: /next/i }));

    // Step 2: Schedule (defaults: recurring + daily 09:00)
    expect(await screen.findByText(/schedule/i)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /next/i }));

    // Step 3: Refine — submit with default behavior/permissions.
    expect(await screen.findByRole("button", { name: /create routine/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /create routine/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));

    const payload = onSubmit.mock.calls[0][0];
    expect(payload.name).toBe("Daily review");
    expect(payload.instructions).toBe("Look for regressions in main.");
    expect(payload.agentId).toBe("alpha");
    expect(payload.scheduleMode).toBe("recurring");
    expect(payload.triggerType).toBe("cron");
    expect(payload.scheduleExpr).toMatch(/^0 9 \* \* \*$/);
    expect(payload.connectors).toEqual([]);
    expect(payload.notificationMode).toBe("summary_complete");
    expect(payload.verificationMode).toBe("post_write_if_any");
  });

  it("prefills Basics step in edit mode from an existing job", async () => {
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
  });

  it("uses defaultTimezone when provided", async () => {
    const { onSubmit } = renderEditor({ defaultTimezone: "America/Sao_Paulo" });

    fireEvent.change(screen.getByPlaceholderText(/Daily code review/i), {
      target: { value: "Tz check" },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/Describe what the agent should do/i),
      { target: { value: "Verify timezone wiring" } },
    );
    fireEvent.click(await screen.findByRole("button", { name: /next/i }));
    fireEvent.click(await screen.findByRole("button", { name: /next/i }));
    fireEvent.click(await screen.findByRole("button", { name: /create routine/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].timezone).toBe("America/Sao_Paulo");
  });
});
