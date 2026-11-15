import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import SchedulesPage from "@/app/routines/schedules/page";
import { setAgentCatalog, type AgentDisplay } from "@/lib/agent-constants";
import { LOCALE_COOKIE_KEY, translateForLanguage } from "@/lib/i18n";
import type { CronJob, ScheduleDetail } from "@/lib/types";

const showToast = vi.fn();

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ showToast }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/routines/schedules",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/agent-switcher", () => ({
  AgentSwitcher: () => <div data-testid="agent-switcher-mock" />,
}));

const AGENTS: AgentDisplay[] = [
  { id: "alpha", label: "Alpha", color: "#D97757", colorRgb: "217, 119, 87" },
];

function routine(overrides: Partial<CronJob> = {}): CronJob {
  return {
    id: 7,
    bot_id: "alpha",
    user_id: 1,
    chat_id: 2,
    job_type: "agent_query",
    trigger_type: "cron",
    schedule_expr: "0 9 * * *",
    cron_expression: "0 9 * * *",
    timezone: "UTC",
    payload: { name: "Nightly audit", query: "Audit the repository." },
    command: "Audit the repository.",
    description: "",
    created_at: null,
    enabled: 1,
    status: "active",
    work_dir: "/repo",
    config_version: 3,
    ...overrides,
  };
}

function detail(job: CronJob = routine()): ScheduleDetail {
  // Runtime responses put the query text in `summary`; the name is in `payload.name`.
  return { job: { ...job, summary: String(job.payload?.query ?? "") }, runs: [], events: [] };
}

const tr = (key: string) => translateForLanguage("en-US", key);

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (url: string, init: RequestInit | undefined) => Response | undefined;

let handlers: Handler[] = [];
const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" ? input : input.toString();
  for (const handler of handlers) {
    const response = handler(url, init);
    if (response) return response;
  }
  if (url.includes("/dashboard/schedules")) {
    const items = [routine()];
    return json({
      items,
      page: { limit: 25, offset: 0, returned: items.length, next_offset: null, has_more: false },
    });
  }
  if (url.includes("/schedules/preview?")) {
    return json({ next_runs: [] });
  }
  if (url.endsWith("/api/runtime/agents/alpha/schedules/7") && (init?.method ?? "GET") === "GET") {
    return json(detail());
  }
  throw new Error(`Unexpected fetch ${init?.method ?? "GET"} ${url}`);
});

function requestsTo(fragment: string, method: string) {
  return fetchMock.mock.calls.filter(
    ([input, init]) => String(input).includes(fragment) && (init?.method ?? "GET") === method,
  );
}

function renderPage(agents: AgentDisplay[] = AGENTS) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={agents}>
          <SchedulesPage />
        </AgentCatalogProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

async function openEditor() {
  const [edit] = await screen.findAllByRole("button", { name: "Edit" });
  fireEvent.click(edit);
  return screen.findByRole("dialog");
}

async function goToLastStep() {
  fireEvent.click(await screen.findByRole("button", { name: /next/i }));
  fireEvent.click(await screen.findByRole("button", { name: /next/i }));
}

beforeAll(() => {
  if (!window.matchMedia) {
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
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
  handlers = [];
  fetchMock.mockClear();
  showToast.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SchedulesPage", () => {
  // D-063: a rename is sent as `payload.name`, which `update_job` stores.
  it("prefills the stored name and sends a rename as patch.name", async () => {
    handlers.push((url, init) =>
      init?.method === "PATCH" ? json({ ok: true, ...detail() }) : undefined,
    );
    renderPage();
    await openEditor();

    const name = await screen.findByPlaceholderText(/Daily code review/i);
    expect(name).toHaveValue("Nightly audit");
    fireEvent.change(name, { target: { value: "Weekly audit" } });
    await goToLastStep();
    fireEvent.click(await screen.findByRole("button", { name: /save/i }));

    await waitFor(() => expect(requestsTo("/schedules/7", "PATCH")).toHaveLength(1));
    const [[, init]] = requestsTo("/schedules/7", "PATCH");
    const body = JSON.parse(String(init?.body));
    expect(body.patch.name).toBe("Weekly audit");
    expect(body.patch).not.toHaveProperty("summary");
  });

  // D-121: the delete toast follows the result, and a failure stays visible in the editor.
  describe("deleting a routine", () => {
    async function confirmDelete() {
      await openEditor();
      await goToLastStep();
      fireEvent.click(await screen.findByRole("button", { name: tr("routines.editor.actions.delete") }));
      const dialog = await screen.findByRole("alertdialog");
      fireEvent.click(within(dialog).getByRole("button", { name: tr("routines.editor.delete.confirmAction") }));
    }

    it("reports the backend refusal instead of a deleted toast", async () => {
      handlers.push((url) =>
        url.endsWith("/actions/delete")
          ? json({ ok: false, message: "Job already archived." }, 400)
          : undefined,
      );
      renderPage();
      await confirmDelete();

      await waitFor(() => expect(showToast).toHaveBeenCalledWith("Job already archived.", "error"));
      expect(showToast).not.toHaveBeenCalledWith(tr("routines.editor.messages.deleted"), "success");
      const editor = screen.getByRole("dialog");
      expect(within(editor).getByText("Job already archived.")).toBeInTheDocument();
    });

    it("toasts and closes the editor when the delete succeeds", async () => {
      handlers.push((url) =>
        url.endsWith("/actions/delete") ? json({ ok: true, message: "Job archived." }) : undefined,
      );
      renderPage();
      await confirmDelete();

      await waitFor(() =>
        expect(showToast).toHaveBeenCalledWith(tr("routines.editor.messages.deleted"), "success"),
      );
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });
  });

  // D-122: the backend reports refusals as `{ ok: false, message }` and conflicts as 409.
  describe("saving a routine", () => {
    async function save() {
      await openEditor();
      await goToLastStep();
      fireEvent.click(await screen.findByRole("button", { name: /save/i }));
    }

    it("shows the backend message when the update is refused", async () => {
      handlers.push((url, init) =>
        init?.method === "PATCH"
          ? json({ ok: false, message: "Agent jobs require a non-empty query." }, 400)
          : undefined,
      );
      renderPage();
      await save();

      const editor = await screen.findByRole("dialog");
      expect(await within(editor).findByText("Agent jobs require a non-empty query.")).toBeInTheDocument();
    });

    it("reloads the routine and says so on a version conflict", async () => {
      handlers.push((url, init) =>
        init?.method === "PATCH"
          ? json({ ok: false, message: "Job was updated by another actor.", config_version: 4 }, 409)
          : undefined,
      );
      renderPage();
      await save();

      await waitFor(() =>
        expect(showToast).toHaveBeenCalledWith(tr("routines.editor.errors.conflict"), "error"),
      );
      expect(requestsTo("/api/runtime/agents/alpha/schedules/7", "GET")).toHaveLength(2);
      const editor = screen.getByRole("dialog");
      expect(within(editor).getByText(tr("routines.editor.errors.conflict"))).toBeInTheDocument();
    });
  });

  // D-123: row actions report their result without opening the editor.
  it.each([
    ["Run now", "run", { ok: true, message: "Manual execution queued.", run_id: 12 }],
    ["Pause", "pause", { ok: true, message: "Job paused." }],
  ])("%s does not open the editor", async (label, action, response) => {
    handlers.push((url) =>
      url.endsWith(`/actions/${action}`) ? json({ ...response, ...detail() }) : undefined,
    );
    renderPage();
    const [button] = await screen.findAllByRole("button", { name: label });
    fireEvent.click(button);

    expect(await screen.findByText(response.message)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("toasts a row action the backend refuses", async () => {
    handlers.push((url) =>
      url.endsWith("/actions/run")
        ? json({ ok: false, message: "Job must be validated before manual execution.", run_id: null }, 400)
        : undefined,
    );
    renderPage();
    const [button] = await screen.findAllByRole("button", { name: "Run now" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("Job must be validated before manual execution.", "error"),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // D-211: with no agents the schedules query never runs, so the page must not wait for it.
  it("shows an empty state instead of a skeleton when there are no agents", async () => {
    // An empty provider falls back to the module catalog, which earlier renders filled.
    setAgentCatalog([]);
    renderPage([]);

    expect(await screen.findByText(tr("schedules.page.noAgents"))).toBeInTheDocument();
    expect(screen.getByText(tr("schedules.page.noAgentsDescription"))).toBeInTheDocument();
    expect(requestsTo("/dashboard/schedules", "GET")).toHaveLength(0);
  });
});
