import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BotEditorProvider, useBotEditor } from "@/hooks/use-bot-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabInstrucoes } from "@/components/control-plane/editor/tabs/tab-instrucoes";
import type {
  ControlPlaneBot,
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

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.defaultValue === "string" ? options.defaultValue : key,
    tl: (value: string) => value,
    i18n: { t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.defaultValue === "string" ? options.defaultValue : key },
    language: "en-US",
    setLanguage: vi.fn(),
    options: [],
  }),
}));

function makeBot(overrides: Partial<ControlPlaneBot> = {}): ControlPlaneBot {
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
      workspace_color: null,
      squad_id: null,
      squad_name: null,
      squad_color: null,
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
      bot_count: 0,
    },
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

function DeveloperHarness() {
  const { developerMode, setDeveloperMode } = useBotEditor();
  return (
    <button type="button" onClick={() => setDeveloperMode(!developerMode)}>
      toggle developer
    </button>
  );
}

function renderTab(bot: ControlPlaneBot) {
  return render(
    <ToastProvider>
      <BotEditorProvider bot={bot} core={core} workspaces={workspaces} systemSettings={systemSettings}>
        <DeveloperHarness />
        <TabInstrucoes />
      </BotEditorProvider>
    </ToastProvider>,
  );
}

describe("TabInstrucoes", () => {
  it("keeps legacy style and responsibility fields hidden outside developer mode", async () => {
    const user = userEvent.setup();
    renderTab(makeBot());

    await user.click(screen.getByRole("button", { name: /missao e governanca/i }));
    expect(screen.queryByLabelText(/persona/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/responsibility limits/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/modo de colaboracao|collaboration/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /toggle developer/i }));
    await user.click(screen.getByRole("button", { name: /derived prompts and advanced overrides|prompts derivados/i }));

    expect(screen.getByLabelText(/persona/i)).toBeInTheDocument();
    expect(screen.getByText(/responsibility limits/i)).toBeInTheDocument();
  });
});
