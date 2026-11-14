import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { RoutineEditor } from "@/components/routines/routine-editor";
import type { AgentDisplay } from "@/lib/agent-constants";
import {
  LOCALE_COOKIE_KEY,
  SUPPORTED_LANGUAGES,
  translateForLanguage,
  type AppLanguage,
} from "@/lib/i18n";
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

beforeEach(() => {
  // The i18n provider persists the active language; reset it so each test renders the
  // language it asks for.
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
});

const AGENTS: AgentDisplay[] = [
  { id: "alpha", label: "Alpha", color: "#D97757", colorRgb: "217, 119, 87" },
  { id: "beta", label: "Beta", color: "#6E97D9", colorRgb: "110, 151, 217" },
];

// Copy the Permissions tab shipped before M1-E8-T1. Runs ignore `read_only` and
// `allowed_paths` (D-006), so none of these promises may come back in any locale.
const FORMER_ENFORCEMENT_PROMISES = [
  "Block any writes during the run, even if the agent attempts them.",
  "Empty means no restriction.",
  "Bloqueia qualquer escrita durante a execução, mesmo que o agente tente.",
  "Vazio = sem restrição.",
  "Bloquea cualquier escritura durante la ejecución, aunque el agente lo intente.",
  "Vacío = sin restricción.",
  "Bloque toute écriture pendant l'exécution, même si l'agent essaie.",
  "Vide = sans restriction.",
  "Blockiert alle Schreibvorgänge während der Ausführung, auch wenn der Agent sie versucht.",
  "Leer = keine Einschränkung.",
];

function tr(language: AppLanguage, key: string) {
  return translateForLanguage(language, key);
}

function fillBasics(language: AppLanguage = "en-US") {
  fireEvent.change(screen.getByPlaceholderText(tr(language, "routines.editor.namePlaceholder")), {
    target: { value: "Nightly audit" },
  });
  fireEvent.change(
    screen.getByPlaceholderText(tr(language, "routines.editor.instructionsPlaceholder")),
    { target: { value: "Audit the repository." } },
  );
}

async function openPermissionsTab(language: AppLanguage = "en-US") {
  const next = tr(language, "routines.editor.actions.next");
  fireEvent.click(await screen.findByRole("button", { name: next }));
  fireEvent.click(await screen.findByRole("button", { name: next }));
  fireEvent.click(
    await screen.findByRole("tab", { name: tr(language, "routines.editor.tabs.permissions") }),
  );
}

function permissionControls(language: AppLanguage = "en-US") {
  const readOnlyLabel = tr(language, "routines.editor.permissions.readOnly");
  const allowedPathsLabel = tr(language, "routines.editor.permissions.allowedPaths");
  return {
    readOnly: screen.getByRole("checkbox", {
      name: (accessibleName) => accessibleName.includes(readOnlyLabel),
    }),
    allowedPaths: screen.getByRole("textbox", {
      name: (accessibleName) => accessibleName.includes(allowedPathsLabel),
    }),
  };
}

function renderEditor(
  overrides: Partial<React.ComponentProps<typeof RoutineEditor>> = {},
  language: AppLanguage = "en-US",
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
    <I18nProvider initialLanguage={language}>
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

  // D-006 interim mitigation (M1-E8-T1): runs ignore read-only and allowed paths, so the
  // Permissions tab must say so and must not let new routines set them.
  describe("Permissions tab while read-only and allowed paths are not enforced", () => {
    function existingJob(payload: Record<string, unknown>): CronJob {
      return {
        id: 7,
        bot_id: "alpha",
        user_id: 1,
        chat_id: null,
        cron_expression: "0 9 * * *",
        trigger_type: "cron",
        schedule_expr: "0 9 * * *",
        timezone: "UTC",
        summary: "Docs sweep",
        command: "Sweep the docs",
        description: "",
        created_at: null,
        enabled: 1,
        status: "active",
        work_dir: "/repo",
        payload: { query: "Sweep the docs", ...payload },
      };
    }

    it("labels both controls as not enforced and keeps them off for a new routine", async () => {
      const { onSubmit } = renderEditor();
      fillBasics();
      await openPermissionsTab();

      expect(screen.getByText("Runs ignore these settings for now.", { exact: false })).toBeInTheDocument();
      const { readOnly, allowedPaths } = permissionControls();
      expect(readOnly).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
      expect(allowedPaths).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
      expect(readOnly).toBeDisabled();
      expect(readOnly).not.toBeChecked();
      expect(allowedPaths).toBeDisabled();
      expect(allowedPaths).toHaveValue("");

      fireEvent.click(screen.getByRole("button", { name: /create routine/i }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].readOnly).toBe(false);
      expect(onSubmit.mock.calls[0][0].allowedPaths).toEqual([]);
    });

    it("shows the values an existing routine stores, without letting them change", async () => {
      renderEditor({
        mode: "edit",
        job: existingJob({ read_only: true, allowed_paths: ["/repo/src", "/repo/docs"] }),
      });
      await openPermissionsTab();

      const { readOnly, allowedPaths } = permissionControls();
      expect(readOnly).toBeChecked();
      expect(readOnly).toBeDisabled();
      expect(allowedPaths).toHaveValue("/repo/src\n/repo/docs");
      expect(allowedPaths).toBeDisabled();
      expect(readOnly).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
      expect(allowedPaths).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
    });

    // Routines created before the Permissions tab existed store neither key, and some have no
    // payload at all. They must open as off and empty, still disabled and labelled.
    it.each([
      ["stores no permission keys", existingJob({})],
      ["has no payload", { ...existingJob({}), payload: undefined }],
    ])("shows an existing routine that %s as off and empty", async (_case, job) => {
      renderEditor({ mode: "edit", job });
      await openPermissionsTab();

      const { readOnly, allowedPaths } = permissionControls();
      expect(readOnly).not.toBeChecked();
      expect(readOnly).toBeDisabled();
      expect(allowedPaths).toHaveValue("");
      expect(allowedPaths).toBeDisabled();
      expect(readOnly).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
      expect(allowedPaths).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
    });

    // The create API stores the payload as given, so `allowed_paths` may not be a list of
    // strings. Only string entries of an actual array are shown; anything else shows nothing.
    it.each([
      ["a string", "/repo", ""],
      ["an object", { path: "/repo" }, ""],
      ["null", null, ""],
      ["a list with non-string entries", ["/a", 3, null, { path: "/b" }, true, "/c"], "/a\n/c"],
    ])(
      "shows only the string paths when an existing routine stores allowed_paths as %s",
      async (_case, storedPaths, shownPaths) => {
        renderEditor({
          mode: "edit",
          job: existingJob({ read_only: true, allowed_paths: storedPaths }),
        });
        await openPermissionsTab();

        const { readOnly, allowedPaths } = permissionControls();
        expect(allowedPaths).toHaveValue(shownPaths);
        expect(allowedPaths).toBeDisabled();
        expect(allowedPaths).toHaveAccessibleName(expect.stringContaining("Not enforced yet"));
        expect(readOnly).toBeChecked();
        expect(readOnly).toBeDisabled();
      },
    );

    it.each(SUPPORTED_LANGUAGES)(
      "never promises blocked writes or restricted paths in %s",
      async (language) => {
        const notEnforced = tr(language, "routines.editor.permissions.notEnforced");
        expect(notEnforced).not.toBe("routines.editor.permissions.notEnforced");

        renderEditor({}, language);
        fillBasics(language);
        await openPermissionsTab(language);

        const { readOnly, allowedPaths } = permissionControls(language);
        expect(readOnly).toHaveAccessibleName(expect.stringContaining(notEnforced));
        expect(allowedPaths).toHaveAccessibleName(expect.stringContaining(notEnforced));
        expect(readOnly).toBeDisabled();
        expect(allowedPaths).toBeDisabled();
        expect(
          screen.getByText(tr(language, "routines.editor.permissions.notEnforcedDescription")),
        ).toBeInTheDocument();

        const rendered = document.body.textContent ?? "";
        for (const promise of FORMER_ENFORCEMENT_PROMISES) {
          expect(rendered, language).not.toContain(promise);
        }
      },
    );
  });
});
