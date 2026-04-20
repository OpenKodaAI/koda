import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentEditorShell } from "@/components/control-plane/editor/agent-editor-shell";
import { ToastProvider } from "@/hooks/use-toast";
import type {
  ControlPlaneAgent,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

const refreshMock = vi.fn();
const originalFetch = globalThis.fetch;

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: refreshMock,
    replace: vi.fn(),
    push: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-tab-navigation", async () => {
  const React = await import("react");
  return {
    useTabNavigation: (tabs: string[], defaultTab?: string) => {
      const [activeTab, setActiveTab] = React.useState(defaultTab ?? tabs[0] ?? "");
      return { activeTab, setActiveTab };
    },
  };
});

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.defaultValue === "string" ? options.defaultValue : key,
    tl: (value: string) => value,
    i18n: {
      t: (key: string, options?: Record<string, unknown>) =>
        typeof options?.defaultValue === "string" ? options.defaultValue : key,
    },
    language: "en-US",
    setLanguage: vi.fn(),
    options: [],
  }),
}));

function makeAgent(overrides: Partial<ControlPlaneAgent> = {}): ControlPlaneAgent {
  return {
    id: "ORBITAL_ONE",
    display_name: "Sr. Frontend Developer",
    status: "active",
    appearance: {
      label: "ORBITAL_ONE",
      color: "#6E97D9",
      color_rgb: "110, 151, 217",
    },
    storage_namespace: "air_compass",
    runtime_endpoint: {
      health_port: 8080,
      health_url: "http://127.0.0.1:8080/health",
      runtime_base_url: "http://127.0.0.1:8080",
    },
    metadata: {},
    organization: {
      workspace_id: null,
      workspace_name: null,
      squad_id: null,
      squad_name: null,
    },
    applied_version: 1,
    desired_version: 1,
    sections: {},
    documents: {},
    knowledge_assets: [],
    knowledge_candidates: [],
    templates: [],
    skills: [],
    runbooks: [],
    secrets: [],
    draft_snapshot: {},
    published_snapshot: null,
    versions: [],
    agent_spec: {
      mission_profile: {},
      interaction_style: {},
      operating_instructions: {},
      hard_rules: {},
      response_policy: {},
      model_policy: {},
      tool_policy: {},
      memory_policy: {},
      knowledge_policy: {},
      autonomy_policy: {},
      resource_access_policy: {},
      voice_policy: {},
      image_analysis_policy: {},
      memory_extraction_schema: {},
    },
    compiled_prompt: "compiled",
    validation: {
      ok: true,
      errors: [],
      warnings: [],
      compiled_prompt: "compiled",
      documents: {},
    },
    ...overrides,
  };
}

const core = {
  tools: { items: [], governance: {} } satisfies ControlPlaneCoreTools,
  providers: {
    providers: {},
    enabled_providers: [],
    default_provider: "claude",
    fallback_order: ["claude"],
  } satisfies ControlPlaneCoreProviders,
  policies: {} as ControlPlaneCorePolicies,
  capabilities: { providers: [] } satisfies ControlPlaneCoreCapabilities,
};

const workspaces: ControlPlaneWorkspaceTree = {
  items: [],
  virtual_buckets: {
    no_workspace: { id: null, label: "Sem workspace", bot_count: 0 },
  },
  total_bot_count: 0,
};

const systemSettings: ControlPlaneSystemSettings = {
  version: 1,
  general: {},
  providers: {},
  tools: {},
  integrations: {},
  memory: {},
  knowledge: {},
  runtime: {},
  scheduler: {},
  shared_variables: [],
  additional_env_vars: [],
  global_secrets: [],
};

describe("AgentEditorShell", () => {
  beforeEach(() => {
    refreshMock.mockReset();
    globalThis.fetch = vi.fn().mockImplementation((input, init) => {
      const method = String(init?.method || "GET").toUpperCase();
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.toString() : String(input);

      if (url === "/api/control-plane/agents/ORBITAL_ONE" && method === "PATCH") {
        return Promise.resolve(
          new Response(JSON.stringify(makeAgent()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url === "/api/control-plane/agents/ORBITAL_ONE" && method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify(makeAgent()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url === "/api/control-plane/agents/ORBITAL_ONE/agent-spec" && method === "PUT") {
        return Promise.resolve(
          new Response(JSON.stringify(makeAgent()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url === "/api/control-plane/agents/ORBITAL_ONE/publish" && method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
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

  it("renders the fullscreen wizard and navigates between steps", async () => {
    const user = userEvent.setup();

    render(
      <ToastProvider>
        <AgentEditorShell
          agent={makeAgent()}
          core={core}
          workspaces={workspaces}
          systemSettings={systemSettings}
        />
      </ToastProvider>,
    );

    expect(screen.getByText("Fluxo")).toBeInTheDocument();
    expect(screen.queryByText("Etapa 1/6")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Sr. Frontend Developer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Avançar" })).toBeInTheDocument();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();

    const identidadeStep = screen.getByRole("button", { name: /Identidade/i });
    expect(identidadeStep).toHaveAttribute("data-state", "active");

    await user.click(screen.getByRole("button", { name: "Avançar" }));

    expect(screen.getByRole("button", { name: /Comportamento/i })).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(screen.getByRole("button", { name: "Voltar" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Identidade/i })).toHaveAttribute(
      "data-state",
      "completed",
    );
  });

  it("shows save and discard actions only when the editor is dirty and persists through the footer", async () => {
    const user = userEvent.setup();

    render(
      <ToastProvider>
        <AgentEditorShell
          agent={makeAgent()}
          core={core}
          workspaces={workspaces}
          systemSettings={systemSettings}
        />
      </ToastProvider>,
    );

    expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();

    const nameInput = screen.getByDisplayValue("Sr. Frontend Developer");
    await user.clear(nameInput);
    await user.type(nameInput, "Sr. Frontend Developer v2");

    const discardButton = await screen.findByRole("button", { name: "Descartar" });
    const saveButton = await screen.findByRole("button", { name: "Salvar" });
    expect(discardButton).toBeInTheDocument();
    expect(saveButton).toBeInTheDocument();

    await user.click(saveButton);

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/agents/ORBITAL_ONE",
        expect.objectContaining({ method: "PATCH" }),
      );
    });

    const fetchMock = vi.mocked(globalThis.fetch);
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/control-plane/agents/ORBITAL_ONE" && init?.method === "PATCH",
    );
    expect(patchCall).toBeTruthy();
    expect(JSON.parse(String(patchCall?.[1]?.body)).display_name).toBe("Sr. Frontend Developer v2");
  });

  it("discards unsaved changes from the footer", async () => {
    const user = userEvent.setup();

    render(
      <ToastProvider>
        <AgentEditorShell
          agent={makeAgent()}
          core={core}
          workspaces={workspaces}
          systemSettings={systemSettings}
        />
      </ToastProvider>,
    );

    const nameInput = screen.getByDisplayValue("Sr. Frontend Developer");
    await user.clear(nameInput);
    await user.type(nameInput, "Nome temporário");

    await user.click(await screen.findByRole("button", { name: "Descartar" }));

    expect(screen.getByDisplayValue("Sr. Frontend Developer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();
  });
});
