import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BotEditorProvider } from "@/hooks/use-bot-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabConhecimento } from "@/components/control-plane/editor/tabs/tab-conhecimento";
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
    id: "ORBITAL_ONE",
    display_name: "Air Compass",
    status: "active",
    appearance: { label: "Air Compass", color: "#A93F0A", color_rgb: "169, 63, 10" },
    storage_namespace: "air_compass",
    runtime_endpoint: {
      health_port: 8081,
      health_url: "http://127.0.0.1:8081/health",
      runtime_base_url: "http://127.0.0.1:8081",
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
    knowledge_assets: [{ id: 1, name: "Runbook" }],
    knowledge_candidates: [],
    templates: [{ id: 2, name: "Resumo executivo" }],
    skills: [{ id: 3, name: "architecture" }],
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
      memory_policy: {
        enabled: true,
        proactive_enabled: true,
        procedural_enabled: true,
        maintenance_enabled: true,
        digest_enabled: false,
        observed_pattern_requires_review: true,
        max_recall: 8,
        recall_threshold: 0.35,
        recall_timeout: 2,
        max_context_tokens: 1600,
        max_extraction_items: 6,
        procedural_max_recall: 4,
        similarity_dedup_threshold: 0.82,
        max_per_user: 400,
        recency_half_life_days: 30,
        minimum_verified_successes: 3,
        extraction_provider: "",
        extraction_model: "",
        risk_posture: "balanced",
        memory_density_target: "focused",
        focus_domains: ["incidentes"],
        preferred_layers: ["procedural"],
        forbidden_layers_for_actions: ["proactive"],
      },
      knowledge_policy: {
        enabled: true,
        require_owner_provenance: true,
        require_freshness_provenance: true,
        allowed_layers: ["canonical_policy", "approved_runbook"],
        max_results: 6,
        recall_threshold: 0.35,
        recall_timeout: 2,
        context_max_tokens: 2200,
        workspace_max_files: 24,
        max_observed_patterns: 3,
        max_source_age_days: 3650,
        promotion_mode: "review_queue",
        source_globs: ["docs/**/*.md"],
        workspace_source_globs: ["README.md"],
      },
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
    providers: {
      claude: { title: "Anthropic", category: "general", enabled: true, available_models: [] },
    },
    enabled_providers: ["claude"],
  } as unknown as ControlPlaneCoreProviders,
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

function renderTab() {
  return render(
    <ToastProvider>
      <BotEditorProvider
        bot={makeBot()}
        core={core}
        workspaces={workspaces}
        systemSettings={systemSettings}
      >
        <TabConhecimento />
      </BotEditorProvider>
    </ToastProvider>,
  );
}

describe("TabConhecimento", () => {
  it("shows a guided knowledge setup and keeps raw JSON hidden by default", async () => {
    const user = userEvent.setup();

    renderTab();

    expect(screen.getByText("Memória e grounding")).toBeInTheDocument();
    expect(screen.getByText(/3 itens publicados/i)).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: /Salvar coleção/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Memória persistente/i }));

    expect(screen.getByText("Memórias por vez")).toBeInTheDocument();
    expect(screen.getByText("Como o agente aprende e o que vale guardar")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Editar ativos em JSON/i }));

    expect(screen.getByRole("button", { name: /Salvar coleção/i })).toBeInTheDocument();
  });
});
