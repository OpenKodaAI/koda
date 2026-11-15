import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentEditorProvider } from "@/hooks/use-agent-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { ToastNotification } from "@/components/ui/toast-notification";
import { TabPublicacao } from "@/components/control-plane/editor/tabs/tab-publicacao";
import type {
  ControlPlaneAgent,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: pushMock }),
}));

vi.mock("@/hooks/use-app-i18n", async () => {
  const { translateForLanguage } = await vi.importActual<typeof import("@/lib/i18n")>("@/lib/i18n");
  const t = (key: string, options?: Record<string, unknown>) => translateForLanguage("pt-BR", key, options);

  return {
    useAppI18n: () => ({
      t,
      tl: (value: string) => value,
      i18n: { t },
      language: "pt-BR",
      setLanguage: vi.fn(),
      options: [],
    }),
  };
});

function makeAgent(overrides: Partial<ControlPlaneAgent> = {}): ControlPlaneAgent {
  return {
    id: "ATLAS",
    display_name: "ATLAS",
    status: "active",
    appearance: { label: "ATLAS", color: "#6E97D9", color_rgb: "110, 151, 217" },
    storage_namespace: "masp",
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
    applied_version: 3,
    desired_version: 3,
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
    versions: [
      {
        id: 3,
        version: 3,
        status: "published",
        created_at: "2026-03-24T10:00:00Z",
      },
    ],
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
    compiled_prompt: "prompt final compilado",
    validation: {
      ok: true,
      errors: [],
      warnings: [],
      compiled_prompt: "prompt final compilado",
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
    no_workspace: { id: null, label: "Sem workspace", agent_count: 0 },
  },
  total_agent_count: 0,
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

function makeCompiledPromptPayload(
  overrides: Partial<ControlPlaneCompiledPrompt> = {},
): ControlPlaneCompiledPrompt {
  return {
    bot_id: "ATLAS",
    compiled_prompt: "prompt final compilado",
    documents: {},
    document_lengths: { identity_md: 120, system_prompt_md: 240 },
    prompt_preview: {
      preview_scope: "runtime_modeled_static",
      provider: "claude",
      model: "claude-sonnet",
      compiled_tokens: 512,
      segment_order: ["immutable_base_policy", "tool_contracts"],
      final_segment_order: ["immutable_base_policy", "tool_contracts"],
      budget: {
        within_budget: true,
        compiled_tokens: 512,
        overflow_tokens: 0,
      },
    },
    agent_contract_prompt_preview: {
      preview_scope: "bot_contract_only",
      segment_order: ["identity_md", "system_prompt_md"],
    },
    runtime_prompt_preview: {
      preview_scope: "runtime_modeled_static",
      provider: "claude",
      model: "claude-sonnet",
      compiled_tokens: 512,
      segment_order: ["immutable_base_policy", "tool_contracts"],
      final_segment_order: ["immutable_base_policy", "tool_contracts"],
      budget: {
        within_budget: true,
        compiled_tokens: 512,
        overflow_tokens: 0,
      },
    },
    ...overrides,
  };
}

function renderTab(
  agent = makeAgent(),
  compiledPromptPayload: ControlPlaneCompiledPrompt | null = makeCompiledPromptPayload(),
  withToasts = false,
) {
  return render(
    <ToastProvider>
      {withToasts ? <ToastNotification /> : null}
      <AgentEditorProvider
        agent={agent}
        compiledPromptPayload={compiledPromptPayload}
        core={core}
        workspaces={workspaces}
        systemSettings={systemSettings}
      >
        <TabPublicacao />
      </AgentEditorProvider>
    </ToastProvider>,
  );
}

describe("TabPublicacao", () => {
  it("renders the lifecycle status and publication metadata", () => {
    renderTab();

    expect(screen.getByText("Status do agente")).toBeInTheDocument();
    expect(screen.getByText("Versão aplicada")).toBeInTheDocument();
    expect(screen.getByText("Versão desejada")).toBeInTheDocument();
    // applied_version=3, desired_version=3, status=active → "Ativo"
    expect(screen.getByText("Ativo")).toBeInTheDocument();
  });

  it("renders clone and delete sections", () => {
    renderTab();

    expect(screen.getByText("Clonar agente")).toBeInTheDocument();
    expect(screen.getByText("Remover agente")).toBeInTheDocument();
  });

  it("renders the delete confirmation trigger", () => {
    renderTab();

    expect(screen.getByRole("button", { name: "Remover agente" })).toBeInTheDocument();
  });

  describe("clone", () => {
    const originalFetch = globalThis.fetch;

    afterEach(() => {
      globalThis.fetch = originalFetch;
      pushMock.mockReset();
    });

    function answerClone(body: unknown, status: number) {
      const fetchMock = vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify(body), {
            status,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      );
      globalThis.fetch = fetchMock as unknown as typeof fetch;
      return fetchMock;
    }

    async function cloneAs(name: string) {
      const user = userEvent.setup();
      renderTab(makeAgent(), makeCompiledPromptPayload(), true);
      await user.click(screen.getByRole("button", { name: /Clonar agente/ }));
      await user.type(await screen.findByLabelText("Nome do clone"), name);
      await user.click(screen.getByRole("button", { name: "Clonar" }));
    }

    it("sends only the name and opens the id the server generated", async () => {
      const fetchMock = answerClone({ id: "ATLAS_BETA" }, 201);

      await cloneAs("Atlas Beta");

      await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/control-plane/agents/ATLAS_BETA"));
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/clone",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ display_name: "Atlas Beta" }),
        }),
      );
    });

    it("shows the id conflict when the server answers 409", async () => {
      answerClone({ error: "agent id ATLAS_BETA already exists" }, 409);

      await cloneAs("Atlas Beta");

      expect(await screen.findByText("Já existe um agente com este ID.")).toBeInTheDocument();
      expect(pushMock).not.toHaveBeenCalled();
    });
  });

  it("shows the active lifecycle label when no pending changes exist", () => {
    renderTab();

    expect(screen.getByText("Ativo")).toBeInTheDocument();
    expect(
      screen.queryByText("Alterações não publicadas"),
    ).not.toBeInTheDocument();
  });
});
