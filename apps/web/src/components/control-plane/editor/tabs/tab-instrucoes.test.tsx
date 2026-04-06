import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BotEditorProvider, useBotEditor } from "@/hooks/use-bot-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabInstrucoes } from "@/components/control-plane/editor/tabs/tab-instrucoes";
import type {
  ControlPlaneBot,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneExecutionPolicyPayload,
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
  const executionPolicyPayload: ControlPlaneExecutionPolicyPayload = {
    agent_id: bot.id,
    source: "compiled_legacy",
    policy: {
      version: 1,
      source: "compiled_legacy",
      defaults: {},
      rules: [
        {
          name: "allow_read",
          priority: 10,
          match: { tool_id: "notes.read" },
          decision: "allow",
          reason: "safe_read_default",
        },
      ],
    },
    catalog: {
      version: 1,
      decision_values: ["allow", "allow_with_preview", "require_approval", "deny"],
      effect_tags: ["external_communication"],
      selector_keys: ["tool_id", "action_id", "integration_id"],
      actions: [
        {
          action_id: "gmail.users.messages.send",
          tool_id: "gmail.send",
          integration_id: "gmail",
          title: "Send message",
          description: "Enviar um email pelo Gmail",
          transport: "http",
          access_level: "write",
          risk_class: "high",
          effect_tags: ["external_communication"],
          default_decision: "allow_with_preview",
          default_reason_code: "preview_required_default",
          preview_required_default: true,
          approval_scope_default: "tool_call",
        },
      ],
      core_tools: [],
      core_integrations: [],
    },
    legacy: {
      tool_policy: {},
      autonomy_policy: {},
      resource_access_policy: {},
    },
  };

  return render(
    <ToastProvider>
      <BotEditorProvider
        bot={bot}
        core={core}
        workspaces={workspaces}
        systemSettings={systemSettings}
        executionPolicyPayload={executionPolicyPayload}
      >
        <DeveloperHarness />
        <TabInstrucoes />
      </BotEditorProvider>
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
    renderTab(makeBot());

    expect(screen.getByText(/policy center/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/execution policy json/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /personalidade e missao/i }));
    expect(screen.queryByLabelText(/persona/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/responsibility limits/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/modo de colaboracao|collaboration/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /toggle developer/i }));
    await user.click(screen.getByRole("button", { name: /prompts derivados e overrides avancados|derived prompts/i }));

    expect(screen.getByLabelText(/persona/i)).toBeInTheDocument();
    expect(screen.getByText(/responsibility limits/i)).toBeInTheDocument();
    expect(screen.getByText(/execution policy json/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /migrar para policy explícita/i })).toBeInTheDocument();
  }, 10000);

  it("runs the policy simulator and renders the evaluate response", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          agent_id: "ATLAS",
          policy: {
            version: 1,
            source: "compiled_legacy",
            defaults: { preview: true },
            rules: [],
          },
          catalog: {
            version: 1,
            decision_values: ["allow", "allow_with_preview", "require_approval", "deny"],
            effect_tags: ["external_communication"],
            selector_keys: ["tool_id", "action_id", "integration_id"],
            actions: [],
            core_tools: [],
            core_integrations: [],
          },
          action: {
            tool_id: "gmail.send",
            action_id: "gmail.users.messages.send",
            integration_id: "gmail",
          },
          evaluation: {
            decision: "allow_with_preview",
            reason_code: "preview_required_default",
            matched_selector: { action_id: "gmail.users.messages.send" },
            approval_scope: { kind: "tool_call", ttl_seconds: 300 },
            preview_text: "Preview do envio",
            audit_payload: { policy_source: "compiled_legacy" },
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    globalThis.fetch = fetchMock;

    renderTab(makeBot());

    await user.click(screen.getByRole("button", { name: /avaliar policy/i }));

    expect(screen.getAllByText("allow_with_preview").length).toBeGreaterThan(0);
    expect(screen.getByText("preview_required_default")).toBeInTheDocument();
    expect(screen.getAllByText(/gmail\.users\.messages\.send/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/preview do envio/i)).toBeInTheDocument();
  });
});
