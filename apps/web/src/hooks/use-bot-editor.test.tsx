import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { BotEditorProvider, useBotEditor } from "@/hooks/use-bot-editor";
import { prettyJson } from "@/lib/control-plane-editor";
import type {
  ControlPlaneBot,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneExecutionPolicyPayload,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

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

function StateProbe() {
  const { state } = useBotEditor();
  return (
    <>
      <div data-testid="display-name">{state.displayName}</div>
      <div data-testid="compiled-prompt">{state.compiledPrompt}</div>
      <pre data-testid="execution-policy-json">{state.executionPolicyJson}</pre>
      <pre data-testid="knowledge-json">{state.knowledgeJson}</pre>
    </>
  );
}

function PersistDraftProbe() {
  const { state, updateCollectionJson, persistDraft } = useBotEditor();

  return (
    <>
      <button
        type="button"
        onClick={() =>
          updateCollectionJson(
            "knowledge",
            prettyJson([
              {
                name: "Playbook canônico",
                content_md: "Use sempre a política mais recente.",
              },
            ]),
          )
        }
      >
        editar knowledge
      </button>
      <button
        type="button"
        onClick={() =>
          void persistDraft({
            includeMeta: false,
            includeAgentSpec: false,
            includeCollections: true,
          })
        }
      >
        salvar collections
      </button>
      <button type="button" onClick={() => void persistDraft()}>
        salvar draft
      </button>
      <pre data-testid="knowledge-json">{state.knowledgeJson}</pre>
    </>
  );
}

describe("useBotEditor", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("rehydrates editor state when the server bot payload changes", async () => {
    function Harness({
      bot,
      compiledPromptPayload,
      executionPolicyPayload,
    }: {
      bot: ControlPlaneBot;
      compiledPromptPayload?: ControlPlaneCompiledPrompt | null;
      executionPolicyPayload?: ControlPlaneExecutionPolicyPayload | null;
    }) {
      return (
        <BotEditorProvider
          bot={bot}
          compiledPromptPayload={compiledPromptPayload}
          executionPolicyPayload={executionPolicyPayload}
          core={core}
          workspaces={workspaces}
          systemSettings={systemSettings}
        >
          <StateProbe />
        </BotEditorProvider>
      );
    }

    const { rerender } = render(
      <Harness
        bot={makeBot({
          agent_spec: {
            ...makeBot().agent_spec,
            execution_policy: {
              version: 99,
              source: "legacy",
              defaults: { stale: true },
            },
          },
        })}
        compiledPromptPayload={{
          bot_id: "ATLAS",
          compiled_prompt: "compiled canonical",
          documents: {},
        }}
        executionPolicyPayload={{
          agent_id: "ATLAS",
          source: "compiled_legacy",
          policy: {
            version: 1,
            source: "compiled_legacy",
            defaults: { preview: true },
            rules: [
              {
                name: "allow_read",
                priority: 10,
                match: { tool_id: "notes.read" },
                decision: "allow",
              },
            ],
          },
          catalog: {
            version: 1,
            decision_values: ["allow", "allow_with_preview", "require_approval", "deny"],
            effect_tags: [],
            selector_keys: ["tool_id"],
            core_tools: [],
            core_integrations: [],
          },
          legacy: {
            tool_policy: {},
            autonomy_policy: {},
            resource_access_policy: {},
          },
        }}
      />,
    );
    expect(screen.getByTestId("display-name")).toHaveTextContent("ATLAS");
    expect(screen.getByTestId("compiled-prompt")).toHaveTextContent("compiled canonical");
    expect(screen.getByTestId("execution-policy-json")).toHaveTextContent(
      '"source": "compiled_legacy"',
    );

    rerender(
      <Harness
        bot={makeBot({ display_name: "ATLAS Atualizado" })}
        compiledPromptPayload={{
          bot_id: "ATLAS",
          compiled_prompt: "compiled atualizado",
          documents: {},
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("display-name")).toHaveTextContent(
        "ATLAS Atualizado",
      );
      expect(screen.getByTestId("compiled-prompt")).toHaveTextContent(
        "compiled atualizado",
      );
    });
  });

  it("refreshes collection state after persisting new assets so later saves do not duplicate drafts", async () => {
    const user = userEvent.setup();
    const refreshedBot = makeBot({
      knowledge_assets: [
        {
          id: 101,
          name: "Playbook canônico",
          content_md: "Use sempre a política mais recente.",
        },
      ],
    });

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 101,
            name: "Playbook canônico",
            content_md: "Use sempre a política mais recente.",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(refreshedBot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    globalThis.fetch = fetchMock;

    render(
      <BotEditorProvider bot={makeBot()} core={core} workspaces={workspaces} systemSettings={systemSettings}>
        <PersistDraftProbe />
      </BotEditorProvider>,
    );

    await user.click(screen.getByRole("button", { name: "editar knowledge" }));
    await user.click(screen.getByRole("button", { name: "salvar collections" }));

    await waitFor(() => {
      expect(screen.getByTestId("knowledge-json")).toHaveTextContent('"id": 101');
    });

    await user.click(screen.getByRole("button", { name: "salvar draft" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/control-plane/agents/ATLAS/knowledge-assets",
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "/api/control-plane/agents/ATLAS",
    );
  });
});
