import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentEditorProvider, useAgentEditor } from "@/hooks/use-agent-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabInstrucoes } from "@/components/control-plane/editor/tabs/tab-instrucoes";
import type {
  ControlPlaneAgent,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
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
      mission_profile: {
        responsibility_limits: ["never approve production deploys"],
      },
      interaction_style: {
        tone: "profissional",
        persona: "trusted operator",
        escalation_style: "escalar com contexto",
        values: ["honestidade"],
        collaboration_style: "colaborativo",
        writing_style: "claro e direto",
      },
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
    enabled_providers: ["claude"],
    default_provider: "claude",
    fallback_order: ["claude"],
  } satisfies ControlPlaneCoreProviders,
  policies: {} as ControlPlaneCorePolicies,
  capabilities: { providers: [] } satisfies ControlPlaneCoreCapabilities,
};

const workspaces: ControlPlaneWorkspaceTree = {
  items: [],
  virtual_buckets: {
    no_workspace: {
      id: null,
      label: "Sem workspace",
      agent_count: 0,
    },
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

function DeveloperHarness() {
  const { developerMode, setDeveloperMode } = useAgentEditor();
  return (
    <button type="button" onClick={() => setDeveloperMode(!developerMode)}>
      toggle developer
    </button>
  );
}

function renderTab(agent: ControlPlaneAgent) {
  return render(
    <ToastProvider>
      <AgentEditorProvider
        agent={agent}
        core={core}
        workspaces={workspaces}
        systemSettings={systemSettings}
      >
        <DeveloperHarness />
        <TabInstrucoes />
      </AgentEditorProvider>
    </ToastProvider>,
  );
}

describe("TabInstrucoes", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("keeps legacy style and responsibility fields hidden outside developer mode", async () => {
    const user = userEvent.setup();
    renderTab(makeAgent());

    // Default sub-tab is "Prompts"; switch to "Politicas" to reach response + autonomy
    await user.click(screen.getByRole("tab", { name: /pol.ticas/i }));
    expect(screen.getByText(/formato de resposta/i)).toBeInTheDocument();
    expect(screen.getByText(/autonomia e aprova/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/execution policy json/i)).not.toBeInTheDocument();

    // Legacy personality/mission/hard-rules list fields are hidden outside dev mode
    expect(screen.queryByLabelText(/persona/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/responsibility limits|limites de responsabilidade/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/modo de colabora..o|collaboration/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/regras inviolaveis/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/acoes proibidas/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/regras de seguranca/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /toggle developer/i }));
    await user.click(screen.getByRole("button", { name: /campos avan[cç]ados/i }));
    await user.click(screen.getByRole("button", { name: /substitui[cç][oõ]es avan[cç]adas de prompt e autonomia|overrides avan[cç]ados de prompt e autonomia|derived prompts/i }));

    expect(screen.getByLabelText(/persona/i)).toBeInTheDocument();
    expect(screen.getByText(/responsibility limits|limites de responsabilidade/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/execution policy json|pol.tica de execu..o json/i)).toBeInTheDocument();
    // Legacy mission/interaction fields now live inside developer mode
    expect(screen.getByLabelText(/modo de colabora..o|collaboration/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/papel profissional|fun..o profissional|professional role|legacy role/i)).toBeInTheDocument();
    // Legacy hard_rules list editors also move into developer mode
    expect(screen.getByText(/regras n.o negoci.veis \(legado\)|non-negotiable rules/i)).toBeInTheDocument();
    expect(screen.getByText(/a..es proibidas \(legado\)|forbidden actions/i)).toBeInTheDocument();
    expect(screen.getByText(/regras de seguran.a \(herdadas\)|security rules/i)).toBeInTheDocument();
  }, 10000);
});
