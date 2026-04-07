import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
import { BotCreateWizard } from "./bot-create-wizard";
import type {
  ControlPlaneCoreProviders,
  ControlPlaneWorkspaceTree,
  GeneralSystemSettings,
} from "@/lib/control-plane";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
  }),
}));

if (!HTMLElement.prototype.hasPointerCapture) {
  HTMLElement.prototype.hasPointerCapture = () => false;
}

if (!HTMLElement.prototype.setPointerCapture) {
  HTMLElement.prototype.setPointerCapture = () => {};
}

if (!HTMLElement.prototype.releasePointerCapture) {
  HTMLElement.prototype.releasePointerCapture = () => {};
}

const coreProviders: ControlPlaneCoreProviders = {
  providers: {
    codex: {
      title: "OpenAI",
      category: "general",
      available_models: ["gpt-5.4", "gpt-5.4-mini"],
      default_model: "gpt-5.4",
    },
    claude: {
      title: "Anthropic",
      category: "general",
      available_models: ["claude-sonnet-4-6"],
      default_model: "claude-sonnet-4-6",
    },
    gemini: {
      title: "Google",
      category: "general",
      available_models: ["gemini-2.5-pro"],
      default_model: "gemini-2.5-pro",
    },
    kokoro: {
      title: "Kokoro",
      category: "media",
      available_models: ["kokoro-tts"],
      default_model: "kokoro-tts",
    },
  },
  enabled_providers: ["codex", "claude", "gemini", "kokoro"],
  default_provider: "codex",
  fallback_order: ["codex", "claude"],
};

const workspaces: ControlPlaneWorkspaceTree = {
  items: [
    {
      id: "workspace-product",
      name: "Produto",
      description: "Workspace principal",
      color: "#4F7CFF",
      bot_count: 0,
      squads: [
        {
          id: "squad-platform",
          workspace_id: "workspace-product",
          name: "Plataforma",
          description: "Squad de plataforma",
          color: "#4F7CFF",
          bot_count: 0,
          created_at: "2026-04-05T00:00:00Z",
          updated_at: "2026-04-05T00:00:00Z",
        },
      ],
      virtual_buckets: {
        no_squad: {
          id: null,
          label: "Sem squad",
          bot_count: 0,
        },
      },
      created_at: "2026-04-05T00:00:00Z",
      updated_at: "2026-04-05T00:00:00Z",
    },
  ],
  virtual_buckets: {
    no_workspace: {
      id: null,
      label: "Sem workspace",
      bot_count: 0,
    },
  },
  total_bot_count: 0,
};

const generalSettings = {
  version: 1,
  values: {
    account: {
      owner_name: "",
      owner_email: "",
      owner_github: "",
      default_work_dir: "",
      project_dirs: [],
      scheduler_default_timezone: "America/Sao_Paulo",
    },
    models: {
      providers_enabled: ["codex", "claude"],
      default_provider: "codex",
      fallback_order: ["codex", "claude"],
      usage_profile: "balanced",
      max_budget_usd: null,
      max_total_budget_usd: null,
      elevenlabs_default_language: "pt",
      elevenlabs_default_voice: "",
      elevenlabs_default_voice_label: "",
      kokoro_default_language: "pt-br",
      kokoro_default_voice: "pf_dora",
      kokoro_default_voice_label: "",
      functional_defaults: {},
    },
    resources: {
      global_tools: [],
      integrations: {},
    },
    memory_and_knowledge: {
      memory_enabled: false,
      memory_profile: "balanced",
      procedural_enabled: false,
      proactive_enabled: false,
      knowledge_enabled: false,
      knowledge_profile: "curated_workspace",
      provenance_policy: "standard",
      promotion_mode: "review_queue",
      memory_policy: {},
      knowledge_policy: {},
      autonomy_policy: {},
    },
    variables: [],
    provider_connections: {
      codex: {
        provider_id: "codex",
        title: "OpenAI",
        auth_mode: "api_key",
        configured: true,
        verified: true,
        account_label: "",
        plan_label: "",
        last_verified_at: "",
        last_error: "",
        project_id: "",
        command_present: true,
        supports_api_key: true,
        supports_subscription_login: false,
        supports_local_connection: false,
        supported_auth_modes: ["api_key"],
        login_flow_kind: "",
        requires_project_id: false,
        api_key_present: true,
        api_key_preview: "",
        base_url: "",
        connection_status: "verified",
        connection_managed: true,
        show_in_settings: true,
      },
      claude: {
        provider_id: "claude",
        title: "Anthropic",
        auth_mode: "api_key",
        configured: true,
        verified: true,
        account_label: "",
        plan_label: "",
        last_verified_at: "",
        last_error: "",
        project_id: "",
        command_present: true,
        supports_api_key: true,
        supports_subscription_login: false,
        supports_local_connection: false,
        supported_auth_modes: ["api_key"],
        login_flow_kind: "",
        requires_project_id: false,
        api_key_present: true,
        api_key_preview: "",
        base_url: "",
        connection_status: "verified",
        connection_managed: true,
        show_in_settings: true,
      },
      gemini: {
        provider_id: "gemini",
        title: "Google",
        auth_mode: "api_key",
        configured: true,
        verified: false,
        account_label: "",
        plan_label: "",
        last_verified_at: "",
        last_error: "",
        project_id: "",
        command_present: true,
        supports_api_key: true,
        supports_subscription_login: false,
        supports_local_connection: false,
        supported_auth_modes: ["api_key"],
        login_flow_kind: "",
        requires_project_id: false,
        api_key_present: true,
        api_key_preview: "",
        base_url: "",
        connection_status: "configured",
        connection_managed: true,
        show_in_settings: true,
      },
      kokoro: {
        provider_id: "kokoro",
        title: "Kokoro",
        auth_mode: "local",
        configured: true,
        verified: true,
        account_label: "",
        plan_label: "",
        last_verified_at: "",
        last_error: "",
        project_id: "",
        command_present: true,
        supports_api_key: false,
        supports_subscription_login: false,
        supports_local_connection: true,
        supported_auth_modes: ["local"],
        login_flow_kind: "",
        requires_project_id: false,
        api_key_present: false,
        api_key_preview: "",
        base_url: "",
        connection_status: "verified",
        connection_managed: true,
        show_in_settings: true,
      },
    },
  },
  source_badges: {},
  catalogs: {
    providers: [
      {
        id: "codex",
        title: "OpenAI",
        vendor: "OpenAI",
        category: "general",
        command_present: true,
        connection_managed: true,
        supported_auth_modes: ["api_key"],
        supports_api_key: true,
      },
      {
        id: "claude",
        title: "Anthropic",
        vendor: "Anthropic",
        category: "general",
        command_present: true,
        connection_managed: true,
        supported_auth_modes: ["api_key"],
        supports_api_key: true,
      },
      {
        id: "gemini",
        title: "Google",
        vendor: "Google",
        category: "general",
        command_present: true,
        connection_managed: true,
        supported_auth_modes: ["api_key"],
        supports_api_key: true,
      },
      {
        id: "kokoro",
        title: "Kokoro",
        vendor: "Kokoro",
        category: "media",
        command_present: true,
        connection_managed: true,
        supported_auth_modes: ["local"],
        supports_local_connection: true,
      },
    ],
    model_functions: [],
    functional_model_catalog: {
      general: [
        {
          provider_id: "codex",
          provider_title: "OpenAI",
          model_id: "gpt-5.4",
          title: "GPT-5.4",
        },
        {
          provider_id: "claude",
          provider_title: "Anthropic",
          model_id: "claude-sonnet-4-6",
          title: "Claude Sonnet 4.6",
        },
        {
          provider_id: "gemini",
          provider_title: "Google",
          model_id: "gemini-2.5-pro",
          title: "Gemini 2.5 Pro",
        },
      ],
    },
    global_tools: [],
    usage_profiles: [],
    memory_profiles: [],
    knowledge_profiles: [],
    provenance_policies: [],
    knowledge_layers: [],
    approval_modes: [],
    autonomy_tiers: [],
  },
  review: {
    warnings: [],
    hidden_sections: [],
  },
} as GeneralSystemSettings;

function renderWizard() {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <ToastProvider>
        <BotCreateWizard
          open
          onClose={() => {}}
          coreProviders={coreProviders}
          generalSettings={generalSettings}
          workspaces={workspaces}
          suggestedHealthPort={8091}
        />
      </ToastProvider>
    </I18nProvider>,
  );
}

describe("BotCreateWizard", () => {
  it("shows only connected generative providers in the provider selector", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(
      screen.getByPlaceholderText("Ex: Assistente de Vendas"),
      "Atlas",
    );
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(screen.getByRole("button", { name: "Pular" }));

    await screen.findByText("Resumo operacional");
    await user.click(screen.getByRole("combobox"));

    expect(screen.getAllByText("OpenAI").length).toBeGreaterThan(0);
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.queryByText("Google")).not.toBeInTheDocument();
    expect(screen.queryByText("Kokoro")).not.toBeInTheDocument();
  });
});
