import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { BotEditorProvider, useBotEditor } from "@/hooks/use-bot-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabEscopo } from "@/components/control-plane/editor/tabs/tab-escopo";
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

function makeSystemSettings(): ControlPlaneSystemSettings {
  return {
    version: 1,
    general: {},
    providers: {},
    tools: {},
    integrations: {},
    memory: {},
    knowledge: {},
    runtime: {},
    scheduler: {},
    shared_variables: [
      { key: "TEAM_NAME", value: "Platform" },
      { key: "WORKSPACE_HINT", value: "/workspace/masp" },
    ],
    additional_env_vars: [],
    global_secrets: [
      {
        scope: "global",
        secret_key: "OPENAI_API_KEY",
        preview: "sk-****",
        grantable_to_agents: true,
      },
      {
        scope: "global",
        secret_key: "RUNTIME_LOCAL_UI_TOKEN",
        preview: "cp-****",
        grantable_to_bots: false,
      },
    ],
  };
}

function renderTab(bot: ControlPlaneBot) {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <ToastProvider>
        <BotEditorProvider bot={bot} core={core} workspaces={workspaces} systemSettings={makeSystemSettings()}>
          <PersistDraftHarness />
          <TabEscopo />
        </BotEditorProvider>
      </ToastProvider>
    </I18nProvider>,
  );
}

function PersistDraftHarness() {
  const { persistDraft } = useBotEditor();
  return (
    <button type="button" onClick={() => void persistDraft({ includeAgentSpec: true })}>
      persist draft
    </button>
  );
}

describe("TabEscopo", () => {
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

  it("persists global grants and local variables through the agent spec save flow", async () => {
    const user = userEvent.setup();
    renderTab(makeBot());

    await user.click(screen.getByRole("button", { name: /escopo de acesso do agente/i }));
    await user.click(screen.getByRole("button", { name: /variáveis locais do agente/i }));
    await user.click(screen.getAllByRole("button", { name: /Conceder acesso/i })[0]);
    await user.type(screen.getByPlaceholderText("TEAM_CONTEXT"), "TEAM_CONTEXT");
    await user.type(
      screen.getByPlaceholderText(/Ex\.: (squad-platform|plataforma-esquadrão)/i),
      "squad-platform",
    );
    await user.click(screen.getByRole("button", { name: "Adicionar" }));

    await user.click(screen.getByRole("button", { name: /persist draft/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/agent-spec",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    const fetchMock = vi.mocked(globalThis.fetch);
    const payload = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(payload.resource_access_policy.allowed_shared_env_keys).toEqual(["TEAM_NAME"]);
    expect(payload.resource_access_policy.local_env).toEqual({
      TEAM_CONTEXT: "squad-platform",
    });
  }, 10000);

  it("updates a local secret through the dedicated bot secret endpoint", async () => {
    const user = userEvent.setup();
    renderTab(
      makeBot({
        secrets: [
          {
            scope: "bot",
            secret_key: "JIRA_API_TOKEN",
            preview: "ji-****",
          },
        ],
      }),
    );

    await user.click(screen.getByRole("button", { name: /segredos locais do agente/i }));
    expect(screen.getByText("ji-****")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Editar$/i }));
    const secretInput = screen.getByPlaceholderText("Digite um novo valor para substituir") as HTMLInputElement;
    expect(secretInput.type).toBe("password");
    await user.type(secretInput, "new-secret-value");
    await user.click(screen.getByRole("button", { name: /Visualizar valor|Valor de exibição/i }));
    expect(secretInput.type).toBe("text");
    await user.click(screen.getByRole("button", { name: /^Atualizar$/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/secrets/JIRA_API_TOKEN?scope=bot",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    expect(refreshMock).toHaveBeenCalled();
  }, 10000);
});
