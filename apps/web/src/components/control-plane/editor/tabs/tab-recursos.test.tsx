import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BotEditorProvider, useBotEditor } from "@/hooks/use-bot-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabRecursos } from "@/components/control-plane/editor/tabs/tab-recursos";
import type {
  ControlPlaneBot,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

const refreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
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
      mission_profile: {},
      interaction_style: {},
      operating_instructions: {},
      hard_rules: {},
      response_policy: {},
      model_policy: {
        allowed_providers: ["claude", "elevenlabs"],
        default_provider: "elevenlabs",
      },
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
  providers: ({
    providers: {
      claude: {
        title: "Anthropic",
        category: "general",
        enabled: true,
        available_models: ["claude-opus-4-6"],
      },
      elevenlabs: {
        title: "ElevenLabs",
        category: "voice",
        enabled: true,
        available_models: ["eleven_v3"],
      },
    },
    enabled_providers: ["claude", "elevenlabs"],
    default_provider: "claude",
    fallback_order: ["claude"],
    model_functions: [],
    functional_model_catalog: {},
  } as unknown) as ControlPlaneCoreProviders,
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
        <TabRecursos />
      </BotEditorProvider>
    </ToastProvider>,
  );
}

describe("TabRecursos", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    refreshMock.mockReset();
    globalThis.fetch = vi.fn().mockImplementation((input, init) => {
      const method = String(init?.method || "GET").toUpperCase();
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : String(input);

      if (url === "/api/control-plane/agents/ATLAS" && method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify(makeBot()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url === "/api/control-plane/agents/ATLAS/agent-spec" && method === "PUT") {
        return Promise.resolve(
          new Response(JSON.stringify(makeBot()), {
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

  it("filters the model envelope to general providers and keeps advanced sections closed by default", async () => {
    const user = userEvent.setup();
    renderTab(makeBot());

    await user.click(screen.getByRole("button", { name: /modelo principal/i }));

    expect(screen.getAllByText("Anthropic").length).toBeGreaterThan(0);
    expect(screen.queryByText(/elevenlabs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/política de modelo \(json\)/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /toggle developer/i }));
    expect(screen.getByRole("button", { name: /json avançado/i })).toBeInTheDocument();
    expect(screen.queryByText(/política de modelo \(json\)/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /json avançado/i }));
    expect(screen.getByText(/política de modelo \(json\)/i)).toBeInTheDocument();
  });
});
