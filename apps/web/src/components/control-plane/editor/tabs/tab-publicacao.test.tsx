import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BotEditorProvider } from "@/hooks/use-bot-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabPublicacao } from "@/components/control-plane/editor/tabs/tab-publicacao";
import type {
  ControlPlaneBot,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.defaultValue === "string" ? options.defaultValue : key,
    tl: (value: string) => value,
    i18n: {
      t: (key: string, options?: Record<string, unknown>) =>
        typeof options?.defaultValue === "string" ? options.defaultValue : key,
    },
    language: "pt-BR",
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
  bot = makeBot(),
  compiledPromptPayload: ControlPlaneCompiledPrompt | null = makeCompiledPromptPayload(),
) {
  return render(
    <ToastProvider>
      <BotEditorProvider
        bot={bot}
        compiledPromptPayload={compiledPromptPayload}
        core={core}
        workspaces={workspaces}
        systemSettings={systemSettings}
      >
        <TabPublicacao />
      </BotEditorProvider>
    </ToastProvider>,
  );
}

describe("TabPublicacao", () => {
  it("renders the publishing summary in PT-BR and keeps collapsible diagnostics closed", async () => {
    const user = userEvent.setup();
    renderTab();

    expect(screen.getByText("Resumo final")).toBeInTheDocument();
    expect(screen.getByText("Versão publicada")).toBeInTheDocument();
    expect(screen.getByText("Próxima publicação")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prompt compilado" })).toBeInTheDocument();
    expect(screen.queryByDisplayValue("prompt final compilado")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Prompt compilado" }));
    expect(screen.getByDisplayValue("prompt final compilado")).toBeInTheDocument();
  });

  it("renders the modeled runtime prompt preview from the canonical compiled-prompt payload", async () => {
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Spec efetivo" }));

    expect(screen.getByText("Prompt efetivo modelado")).toBeInTheDocument();
    expect(screen.getByText("budget ok")).toBeInTheDocument();
    expect(screen.getByText("runtime_modeled_static")).toBeInTheDocument();
    expect(screen.getByText("immutable_base_policy")).toBeInTheDocument();
    expect(screen.getByText("tool_contracts")).toBeInTheDocument();
  });
});
