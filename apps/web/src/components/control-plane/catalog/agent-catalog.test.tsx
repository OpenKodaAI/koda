import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
import { AgentCatalog } from "@/components/control-plane/catalog/agent-catalog";
import type {
  ControlPlaneAgentSummary,
  ControlPlaneCoreProviders,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

const refreshMock = vi.fn();
const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: pushMock }),
}));

function makeAgent(
  id: string,
  displayName: string,
  organization: ControlPlaneAgentSummary["organization"],
): ControlPlaneAgentSummary {
  return {
    id,
    display_name: displayName,
    status: id === "ATLAS" ? "active" : "paused",
    appearance: {
      label: displayName,
      color: "#6E97D9",
      color_rgb: "110, 151, 217",
    },
    storage_namespace: id.toLowerCase(),
    runtime_endpoint: {
      health_port: 8080,
      health_url: "http://127.0.0.1:8080/health",
      runtime_base_url: "http://127.0.0.1:8080",
    },
    metadata: {},
    organization,
    default_model_provider_id: "claude",
    default_model_provider_label: "Anthropic",
    default_model_id: "claude-sonnet-4-6",
    default_model_label: "Claude Sonnet 4.6",
    applied_version: 1,
    desired_version: 1,
  };
}

const coreProviders: ControlPlaneCoreProviders = {
  providers: {},
  enabled_providers: ["claude"],
  default_provider: "claude",
  fallback_order: ["claude"],
};

const workspaceTree: ControlPlaneWorkspaceTree = {
  items: [
    {
      id: "workspace-product",
      name: "Produto",
      description: "Workspace de produto",
      color: "#4F7CFF",
      root_path: "/workspace/product",
      agent_count: 2,
      squads: [
        {
          id: "squad-platform",
          workspace_id: "workspace-product",
          name: "Plataforma",
          description: "Squad de plataforma",
          agent_count: 1,
          created_at: "2026-03-23T00:00:00Z",
          updated_at: "2026-03-23T00:00:00Z",
        },
      ],
      virtual_buckets: {
        no_squad: {
          id: null,
          label: "Sem squad",
          agent_count: 1,
        },
      },
      created_at: "2026-03-23T00:00:00Z",
      updated_at: "2026-03-23T00:00:00Z",
    },
    {
      id: "workspace-ops",
      name: "Operacoes",
      description: "Workspace de operacoes",
      color: "#2EAF6D",
      agent_count: 1,
      squads: [],
      virtual_buckets: {
        no_squad: {
          id: null,
          label: "Sem squad",
          agent_count: 1,
        },
      },
      created_at: "2026-03-23T00:00:00Z",
      updated_at: "2026-03-23T00:00:00Z",
    },
  ],
  virtual_buckets: {
    no_workspace: {
      id: null,
      label: "Sem workspace",
      agent_count: 1,
    },
  },
  total_agent_count: 4,
};

const agents: ControlPlaneAgentSummary[] = [
  makeAgent("ATLAS", "ATLAS", {
    workspace_id: "workspace-product",
    workspace_name: "Produto",
    squad_id: "squad-platform",
    squad_name: "Plataforma",
  }),
  makeAgent("NOVA", "NOVA", {
    workspace_id: "workspace-product",
    workspace_name: "Produto",
    squad_id: null,
    squad_name: null,
  }),
  makeAgent("ORBITAL_ONE", "ORBITAL ONE", {
    workspace_id: "workspace-ops",
    workspace_name: "Operacoes",
    squad_id: null,
    squad_name: null,
  }),
  makeAgent("SOLO", "Solo", {
    workspace_id: null,
    workspace_name: null,
    squad_id: null,
    squad_name: null,
  }),
];

function renderCatalog() {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <ToastProvider>
        <AgentCatalog
          agents={agents}
          coreProviders={coreProviders}
          workspaces={workspaceTree}
        />
      </ToastProvider>
    </I18nProvider>,
  );
}

function createDataTransfer() {
  const store = new Map<string, string>();
  return {
    effectAllowed: "move",
    setData: (type: string, value: string) => {
      store.set(type, value);
    },
    getData: (type: string) => store.get(type) ?? "",
  };
}

describe("AgentCatalog organization board", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    refreshMock.mockReset();
    pushMock.mockReset();
    globalThis.fetch = vi.fn().mockImplementation((input, init) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (url === "/api/control-plane/workspaces" && method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify(workspaceTree), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url === "/api/control-plane/workspaces" && method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: "workspace-research",
              name: "Pesquisa",
              description: "Workspace novo",
              color: "#7A8799",
              agent_count: 0,
              squads: [],
              virtual_buckets: {
                no_squad: { id: null, label: "Sem squad", agent_count: 0 },
              },
              created_at: "2026-03-23T00:00:00Z",
              updated_at: "2026-03-23T00:00:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (url === "/api/control-plane/workspaces/directory-roots" && method === "GET") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [{ path: "/tmp", label: "tmp" }],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (url === "/api/control-plane/workspaces/list-directory" && method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              path: "/tmp",
              parent: "/",
              items: [
                { path: "/tmp/sample-repo", name: "sample-repo", kind: "directory" },
                { path: "/tmp/AGENTS.md", name: "AGENTS.md", kind: "file" },
              ],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (url === "/api/control-plane/workspaces/scan-directory" && method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              schema_version: "workspace_config_scan.v1",
              root_path: "/tmp/sample-repo",
              root_kind: "local_path",
              scan_hash: "scan123",
              status: "completed",
              summary: {
                total_sources: 4,
                by_kind: { instructions: 2, mcp: 1, hook: 1 },
                by_tool: { codex: 1, claude: 2, cursor: 1 },
                by_risk: { low: 2, review: 1, blocked: 1 },
                importable: 2,
                review_required: 1,
                blocked: 1,
                truncated: false,
              },
              sources: [
                {
                  source_id: "src_agents",
                  tool: "codex",
                  kind: "instructions",
                  relative_path: "AGENTS.md",
                  scope: "workspace",
                  name: "AGENTS.md",
                  description: "Codex instructions",
                  confidence: "high",
                  risk: "low",
                  status: "detected",
                  import_action: "append_workspace_prompt",
                  warnings: [],
                  metadata: {},
                  content_excerpt: "Use tests.",
                },
                {
                  source_id: "src_claude",
                  tool: "claude",
                  kind: "instructions",
                  relative_path: "CLAUDE.md",
                  scope: "workspace",
                  name: "CLAUDE.md",
                  description: "Claude memory",
                  confidence: "high",
                  risk: "low",
                  status: "detected",
                  import_action: "append_workspace_prompt",
                  warnings: [],
                  metadata: {},
                  content_excerpt: "Prefer safe imports.",
                },
                {
                  source_id: "src_mcp",
                  tool: "cursor",
                  kind: "mcp",
                  relative_path: ".cursor/mcp.json",
                  scope: "workspace",
                  name: "mcp",
                  description: "MCP candidate",
                  confidence: "high",
                  risk: "review",
                  status: "detected",
                  import_action: "mcp_review",
                  warnings: [],
                  metadata: {},
                  content_excerpt: "",
                },
                {
                  source_id: "src_hook",
                  tool: "claude",
                  kind: "hook",
                  relative_path: ".claude/settings.json",
                  scope: "workspace",
                  name: "PostToolUse hook",
                  description: "Blocked hook",
                  confidence: "high",
                  risk: "blocked",
                  status: "blocked",
                  import_action: "blocked_hook",
                  warnings: [],
                  metadata: {},
                  content_excerpt: "echo [REDACTED]",
                },
              ],
              warnings: [],
              limits: {
                max_depth: 8,
                max_entries: 2500,
                max_file_bytes: 262144,
                max_total_bytes: 3145728,
              },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (url === "/api/control-plane/workspaces/import" && method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              workspace: {
                id: "sample-repo",
                name: "sample-repo",
                description: "",
                root_path: "/tmp/sample-repo",
              },
              import_result: { applied: [], skipped: [], conflicts: [] },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (
        url.startsWith("/api/control-plane/agents/") &&
        method === "PATCH" &&
        !url.endsWith("/clone")
      ) {
        const body = JSON.parse(String(init?.body || "{}"));
        const agentId = url.split("/").pop() ?? "";
        const baseAgent = agents.find((item) => item.id === agentId) ?? agents[0];
        const workspace =
          workspaceTree.items.find(
            (item) => item.id === body.organization.workspace_id,
          ) ?? null;
        const squad =
          workspace && body.organization.squad_id
            ? workspace.squads.find(
                (item) => item.id === body.organization.squad_id,
              ) ?? null
            : null;

        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...baseAgent,
              organization: {
                workspace_id: body.organization.workspace_id,
                workspace_name: workspace?.name ?? null,
                squad_id: body.organization.squad_id,
                squad_name: squad?.name ?? null,
              },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (url === "/api/control-plane/agents/ATLAS" && method === "DELETE") {
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url === "/api/control-plane/agents/ATLAS/clone" && method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: "ATLAS_COPY",
              status: "ok",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders the organization board and filters only by search", async () => {
    const user = userEvent.setup();
    renderCatalog();

    // Workspace selector trigger is rendered with the active workspace name
    const selectorTrigger = screen.getByRole("button", { name: /Selecionar espa/i });
    expect(selectorTrigger).toBeInTheDocument();
    expect(selectorTrigger).toHaveTextContent(/Produto/i);

    expect(screen.getByRole("heading", { name: "ATLAS" })).toBeInTheDocument();
    expect(screen.getAllByText("Claude Sonnet 4.6").length).toBeGreaterThan(0);

    // Open the workspace selector and verify options
    await user.click(selectorTrigger);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Produto/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /Operacoes/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /Sem espa/i })).toBeInTheDocument();
    });
    // Close the selector by clicking outside
    await user.click(document.body);

    await user.type(
      screen.getByLabelText(/Buscar agentes por nome, ID/i),
      "solo",
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Solo" })).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("heading", { name: "ATLAS" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Ativo$/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Pausado$/i }),
    ).not.toBeInTheDocument();
  });

  it("creates a workspace from the management toolbar", async () => {
    const user = userEvent.setup();
    renderCatalog();

    // Open the + popover and click Workspace ("Espaço de trabalho" in pt-BR)
    const createBtn = screen.getByRole("button", { name: /^Criar$/i });
    await user.click(createBtn);
    await waitFor(() => {
      expect(screen.getByRole("menuitem", { name: /spa.o de trabalho/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("menuitem", { name: /spa.o de trabalho/i }));

    await user.type(screen.getByLabelText(/Nome do espa/i), "Pesquisa");
    await user.type(screen.getByLabelText(/Descri/i), "Workspace novo");
    // The form submit button (not the + popover trigger)
    const submitButtons = screen.getAllByRole("button", { name: /^Criar$/i });
    await user.click(submitButtons[submitButtons.length - 1]);

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/workspaces",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("scans a folder import and keeps review-only sources disabled", async () => {
    const user = userEvent.setup();
    renderCatalog();

    await user.click(screen.getByRole("button", { name: /^Criar$/i }));
    await waitFor(() => {
      expect(screen.getByRole("menuitem", { name: /Import from folder|Importar/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("menuitem", { name: /Import from folder|Importar/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: /Import from folder/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/workspaces/directory-roots",
        expect.objectContaining({ headers: expect.any(Object) }),
      );
    });
    expect(await within(dialog).findByText("tmp")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/Folder path/i), "/tmp/sample-repo");
    await user.click(within(dialog).getByRole("button", { name: /Scan/i }));

    await waitFor(() => {
      expect(within(dialog).getByText("AGENTS.md")).toBeInTheDocument();
      expect(within(dialog).getByText("CLAUDE.md")).toBeInTheDocument();
      expect(within(dialog).getByText(".cursor/mcp.json")).toBeInTheDocument();
      expect(within(dialog).getByText(".claude/settings.json")).toBeInTheDocument();
    });

    const blockedSection = within(dialog).getByText(".claude/settings.json").closest("section");
    expect(blockedSection).not.toBeNull();
    expect(within(blockedSection as HTMLElement).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(dialog).getByText(/koda:workspace-import:start/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/src_agents/i)).toBeInTheDocument();
    expect(within(dialog).getAllByText(/Use tests/i).length).toBeGreaterThan(0);

    await user.click(within(dialog).getByRole("button", { name: /^Import$/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/workspaces/import",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            path: "/tmp/sample-repo",
            selectedSourceIds: ["src_agents", "src_claude"],
          }),
        }),
      );
    });
  });

  it("opens folder import when directory root quick-picks are unavailable", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input, init) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (url === "/api/control-plane/workspaces/directory-roots" && method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify({ error: "405: Method Not Allowed" }), {
            status: 405,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      return Promise.resolve(
        new Response(JSON.stringify({ error: "Unexpected request" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });

    const user = userEvent.setup();
    renderCatalog();

    await user.click(screen.getByRole("button", { name: /^Criar$/i }));
    await user.click(await screen.findByRole("menuitem", { name: /Import from folder|Importar/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: /Import from folder/i })).toBeInTheDocument();
    expect(await within(dialog).findByText("Produto")).toBeInTheDocument();
  });

  it("moves a agent between lanes using drag and drop", async () => {
    const user = userEvent.setup();
    renderCatalog();

    const dataTransfer = createDataTransfer();
    fireEvent.dragStart(screen.getByTestId("agent-card-ATLAS"), { dataTransfer });

    // Switch to Operacoes workspace via the selector dropdown
    await user.click(screen.getByRole("button", { name: /Selecionar espa/i }));
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Operacoes/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("option", { name: /Operacoes/i }));
    await waitFor(() => {
      expect(
        screen.getByTestId("lane-workspace-ops-no-squad"),
      ).toBeInTheDocument();
    });
    fireEvent.dragEnter(screen.getByTestId("lane-workspace-ops-no-squad"), {
      dataTransfer,
    });
    fireEvent.dragOver(screen.getByTestId("lane-workspace-ops-no-squad"), {
      dataTransfer,
    });
    fireEvent.drop(screen.getByTestId("lane-workspace-ops-no-squad"), {
      dataTransfer,
    });

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            organization: {
              workspace_id: "workspace-ops",
              squad_id: null,
            },
          }),
        }),
      );
    });
  });

  it("keeps the no-squad lane as the last column when the workspace already has squads", () => {
    renderCatalog();

    const rail = screen.getByTestId("lane-rail-workspace-product");
    const laneCards = Array.from(
      rail.querySelectorAll<HTMLElement>("[data-lane-card='true']"),
    );

    expect(laneCards.at(-1)).toHaveAttribute(
      "data-testid",
      "lane-workspace-product-no-squad",
    );
  });

  it("allows dragging the squad rail horizontally with the mouse", () => {
    renderCatalog();

    const rail = screen.getByTestId("lane-rail-workspace-product");
    Object.defineProperty(rail, "scrollLeft", {
      value: 48,
      writable: true,
    });

    fireEvent.mouseDown(rail, { button: 0, clientX: 240 });
    fireEvent.mouseMove(window, { clientX: 120 });

    expect((rail as HTMLDivElement).scrollLeft).toBe(168);
    expect(rail.className).toContain("catalog-lane-rail--dragging");

    fireEvent.mouseUp(window);
    expect(rail.className).not.toContain("catalog-lane-rail--dragging");
  });

  it("does not render squad edit or delete actions for the virtual no-squad lane", () => {
    renderCatalog();

    expect(
      screen.queryByRole("button", { name: /Editar squad Sem squad/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Remover squad Sem squad/i }),
    ).not.toBeInTheDocument();
  });

  it("opens agent actions inline and confirms deletion before removing", async () => {
    const user = userEvent.setup();
    renderCatalog();

    await user.click(
      screen.getByRole("button", { name: /Abrir ações do agente ATLAS/i }),
    );
    const deleteAction = within(screen.getByRole("menu")).getAllByRole("menuitem")[2];
    await user.click(deleteAction);

    const dialog = await screen.findByRole("alertdialog", {
      name: /Remover agente/i,
    });
    expect(dialog).toBeInTheDocument();
    await user.click(within(dialog).getAllByRole("button").at(-1)!);

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("duplicates a agent and dispatches clone request", async () => {
    const user = userEvent.setup();
    renderCatalog();

    await user.click(
      screen.getByRole("button", { name: /Abrir ações do agente ATLAS/i }),
    );
    const duplicateAction = within(screen.getByRole("menu")).getAllByRole("menuitem")[1];
    await user.click(duplicateAction);

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/clone",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            id: "ATLAS_COPY",
            display_name: "ATLAS (Cópia)",
          }),
        }),
      );
    });
  });
});
