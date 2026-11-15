import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import SchedulesPage from "@/app/routines/schedules/page";
import type { AgentDisplay } from "@/lib/agent-constants";
import { LOCALE_COOKIE_KEY } from "@/lib/i18n";
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
});
