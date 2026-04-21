import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SystemSettingsProvider, useSystemSettings } from "@/hooks/use-system-settings";
import type {
  ControlPlaneCoreIntegrations,
  ElevenLabsVoiceCatalog,
  GeneralSystemSettings,
  GeneralSystemSettingsCatalogProvider,
  GeneralSystemSettingsProviderConnection,
  OllamaModelCatalog,
  ProviderLoginSession,
} from "@/lib/control-plane";

const showToastMock = vi.fn();

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}));

const originalFetch = globalThis.fetch;
const originalOpen = window.open;

function makeProviderCatalogProvider(
  overrides: Partial<GeneralSystemSettingsCatalogProvider> & Pick<GeneralSystemSettingsCatalogProvider, "id" | "title">,
): GeneralSystemSettingsCatalogProvider {
  return {
    id: overrides.id,
    title: overrides.title,
    vendor: overrides.vendor || overrides.title,
    category: overrides.category || "general",
    enabled_by_default: overrides.enabled_by_default ?? true,
    command_present: overrides.command_present ?? true,
    available_models: overrides.available_models || [],
    default_model: overrides.default_model || "",
    supported_auth_modes: overrides.supported_auth_modes || [],
    supports_api_key: overrides.supports_api_key ?? false,
    supports_subscription_login: overrides.supports_subscription_login ?? false,
    supports_local_connection: overrides.supports_local_connection ?? false,
    login_flow_kind: overrides.login_flow_kind || "",
    requires_project_id: overrides.requires_project_id ?? false,
    connection_managed: overrides.connection_managed ?? false,
    show_in_settings: overrides.show_in_settings ?? true,
    connection_status: overrides.connection_status || "not_configured",
    functional_models: overrides.functional_models || [],
  };
}

function makeProviderConnection(
  overrides: Partial<GeneralSystemSettingsProviderConnection> & Pick<GeneralSystemSettingsProviderConnection, "provider_id" | "title" | "auth_mode">,
): GeneralSystemSettingsProviderConnection {
  return {
    provider_id: overrides.provider_id,
    title: overrides.title,
    auth_mode: overrides.auth_mode,
    configured: overrides.configured ?? false,
    verified: overrides.verified ?? false,
    account_label: overrides.account_label || "",
    plan_label: overrides.plan_label || "",
    last_verified_at: overrides.last_verified_at || "",
    last_error: overrides.last_error || "",
    project_id: overrides.project_id || "",
    command_present: overrides.command_present ?? true,
    supports_api_key: overrides.supports_api_key ?? false,
    supports_subscription_login: overrides.supports_subscription_login ?? false,
    supports_local_connection: overrides.supports_local_connection ?? false,
    supported_auth_modes: overrides.supported_auth_modes || [],
    login_flow_kind: overrides.login_flow_kind || "",
    requires_project_id: overrides.requires_project_id ?? false,
    connection_managed: overrides.connection_managed ?? true,
    show_in_settings: overrides.show_in_settings ?? true,
    api_key_present: overrides.api_key_present ?? false,
    api_key_preview: overrides.api_key_preview || "",
    base_url: overrides.base_url || "",
    connection_status: overrides.connection_status || "not_configured",
  };
}

function makeSettings(overrides?: {
  providers?: GeneralSystemSettingsCatalogProvider[];
  providerConnections?: Record<string, GeneralSystemSettingsProviderConnection>;
}): GeneralSystemSettings {
  return {
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
        providers_enabled: [],
        default_provider: "",
        fallback_order: [],
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
      provider_connections: overrides?.providerConnections || {},
    },
    source_badges: {},
    catalogs: {
      providers: overrides?.providers || [],
      model_functions: [],
      functional_model_catalog: {},
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
}

function renderUseSystemSettings(
  settings: GeneralSystemSettings,
  coreIntegrations: ControlPlaneCoreIntegrations = makeCoreIntegrations(),
) {
  return renderHook(() => useSystemSettings(), {
    wrapper: ({ children }) => (
      <SystemSettingsProvider settings={settings} coreIntegrations={coreIntegrations}>
        {children}
      </SystemSettingsProvider>
    ),
  });
}

function makeCoreIntegrations(
  overrides?: Partial<ControlPlaneCoreIntegrations>,
): ControlPlaneCoreIntegrations {
  return {
    items: overrides?.items || [],
    governance: overrides?.governance || {},
  };
}

describe("useSystemSettings", () => {
  beforeEach(() => {
    showToastMock.mockReset();
    window.open = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.open = originalOpen;
  });

  it("filters hidden providers and preserves ollama local support from the backend catalog", () => {
    const settings = makeSettings({
      providers: [
        makeProviderCatalogProvider({
          id: "ollama",
          title: "Ollama",
          supported_auth_modes: ["local", "api_key"],
          supports_api_key: true,
          supports_local_connection: true,
          connection_managed: true,
        }),
        makeProviderCatalogProvider({
          id: "sora",
          title: "Sora",
          category: "media",
          supported_auth_modes: ["api_key"],
          supports_api_key: true,
          connection_managed: false,
          show_in_settings: false,
        }),
      ],
    });

    const { result } = renderUseSystemSettings(settings);

    expect(result.current.providerOptions.map((provider) => provider.id)).toEqual(["ollama"]);
    expect(result.current.providerOptions[0].supportsLocalConnection).toBe(true);
    expect(result.current.providerOptions[0].connectionManaged).toBe(true);
  });

  it("polls completed login sessions and auto-verifies the provider connection", async () => {
    const codexProvider = makeProviderCatalogProvider({
      id: "codex",
      title: "OpenAI",
      supported_auth_modes: ["api_key", "subscription_login"],
      supports_api_key: true,
      supports_subscription_login: true,
      connection_managed: true,
      login_flow_kind: "device_auth",
    });
    const codexConnection = makeProviderConnection({
      provider_id: "codex",
      title: "OpenAI",
      auth_mode: "subscription_login",
      configured: false,
      verified: false,
      supports_api_key: true,
      supports_subscription_login: true,
      supported_auth_modes: ["api_key", "subscription_login"],
      connection_status: "not_configured",
    });
    const settings = makeSettings({
      providers: [codexProvider],
      providerConnections: { codex: codexConnection },
    });

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/providers/codex/connection/login/start") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...codexConnection,
              configured: true,
              connection_status: "configured",
            },
            login_session: {
              session_id: "sess-1",
              provider_id: "codex",
              auth_mode: "subscription_login",
              status: "awaiting_browser",
              command: "codex login --device-auth",
              auth_url: "https://example.com/auth",
              user_code: "ABCD-EFGH",
              message: "Abra o navegador",
              instructions: "",
              output_preview: "",
              last_error: "",
            } satisfies ProviderLoginSession,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/codex/connection/login/sess-1") && method === "GET") {
        return new Response(
          JSON.stringify({
            session_id: "sess-1",
            provider_id: "codex",
            auth_mode: "subscription_login",
            status: "completed",
            command: "codex login --device-auth",
            auth_url: "https://example.com/auth",
            user_code: "ABCD-EFGH",
            message: "Autenticado",
            instructions: "",
            output_preview: "",
            last_error: "",
          } satisfies ProviderLoginSession),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/codex/connection/verify") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...codexConnection,
              configured: true,
              verified: true,
              connection_status: "verified",
              account_label: "ChatGPT Plus",
            },
            verification: {
              verified: true,
              account_label: "ChatGPT Plus",
              plan_label: "",
              checked_via: "login_status",
              last_error: "",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    await act(async () => {
      await result.current.startProviderLogin("codex");
    });

    await waitFor(() => {
      expect(result.current.providerConnections.codex.verified).toBe(true);
    });
    expect(result.current.providerConnectionDrafts.codex.login_session).toBeNull();
    expect(window.open).toHaveBeenCalledWith(
      "https://example.com/auth",
      "_blank",
      "noopener,noreferrer",
    );
    expect(window.open).toHaveBeenCalledTimes(1);
  });

  it("clears ElevenLabs voices and Ollama models after disconnecting", async () => {
    const elevenlabsConnection = makeProviderConnection({
      provider_id: "elevenlabs",
      title: "ElevenLabs",
      auth_mode: "api_key",
      configured: true,
      verified: true,
      supports_api_key: true,
      supported_auth_modes: ["api_key"],
      api_key_present: true,
      connection_status: "verified",
    });
    const ollamaConnection = makeProviderConnection({
      provider_id: "ollama",
      title: "Ollama",
      auth_mode: "local",
      configured: true,
      verified: true,
      supports_api_key: true,
      supports_local_connection: true,
      supported_auth_modes: ["local", "api_key"],
      connection_status: "verified",
      base_url: "http://127.0.0.1:11434",
    });
    const settings = makeSettings({
      providers: [
        makeProviderCatalogProvider({
          id: "elevenlabs",
          title: "ElevenLabs",
          category: "voice",
          supported_auth_modes: ["api_key"],
          supports_api_key: true,
          connection_managed: true,
        }),
        makeProviderCatalogProvider({
          id: "ollama",
          title: "Ollama",
          supported_auth_modes: ["local", "api_key"],
          supports_api_key: true,
          supports_local_connection: true,
          connection_managed: true,
        }),
      ],
      providerConnections: {
        elevenlabs: elevenlabsConnection,
        ollama: ollamaConnection,
      },
    });

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.startsWith("/api/elevenlabs/voices") && method === "GET") {
        return new Response(
          JSON.stringify({
            items: [{ voice_id: "voice-1", name: "Ana", gender: "", accent: "", category: "", preview_url: "", languages: [] }],
            available_languages: [{ code: "pt", label: "Português" }],
            selected_language: "pt",
            cached: false,
            provider_connected: true,
          } satisfies ElevenLabsVoiceCatalog),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/ollama/models") && method === "GET") {
        return new Response(
          JSON.stringify({
            items: [{ model_id: "llama3", name: "llama3", family: "llama", parameter_size: "", quantization_level: "", format: "", modified_at: "", size: 0 }],
            cached: false,
            provider_connected: true,
            base_url: "http://127.0.0.1:11434",
            auth_mode: "local",
          } satisfies OllamaModelCatalog),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/elevenlabs/connection/disconnect") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...elevenlabsConnection,
              configured: false,
              verified: false,
              api_key_present: false,
              connection_status: "not_configured",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/ollama/connection/disconnect") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...ollamaConnection,
              configured: false,
              verified: false,
              api_key_present: false,
              connection_status: "not_configured",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    await act(async () => {
      await result.current.loadElevenLabsVoices("pt");
      await result.current.loadOllamaModels();
    });

    await waitFor(() => {
      expect(result.current.elevenlabsVoiceCatalog.items).toHaveLength(1);
      expect(result.current.ollamaModelCatalog.items).toHaveLength(1);
    });

    await act(async () => {
      await result.current.disconnectProviderConnection("elevenlabs");
      await result.current.disconnectProviderConnection("ollama");
    });

    expect(result.current.elevenlabsVoiceCatalog.items).toHaveLength(0);
    expect(result.current.elevenlabsVoiceCatalog.provider_connected).toBe(false);
    expect(result.current.ollamaModelCatalog.items).toHaveLength(0);
    expect(result.current.ollamaModelCatalog.provider_connected).toBe(false);
    expect(result.current.providerConnectionDrafts.ollama.auth_mode).toBe("local");
  });

  it("auto-verifies Anthropic after submitting the browser authentication code", async () => {
    const claudeProvider = makeProviderCatalogProvider({
      id: "claude",
      title: "Anthropic",
      supported_auth_modes: ["api_key", "subscription_login"],
      supports_api_key: true,
      supports_subscription_login: true,
      connection_managed: true,
      login_flow_kind: "browser",
    });
    const claudeConnection = makeProviderConnection({
      provider_id: "claude",
      title: "Anthropic",
      auth_mode: "subscription_login",
      configured: true,
      verified: false,
      supports_api_key: true,
      supports_subscription_login: true,
      supported_auth_modes: ["api_key", "subscription_login"],
      connection_status: "configured",
    });
    const settings = makeSettings({
      providers: [claudeProvider],
      providerConnections: { claude: claudeConnection },
    });

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (
        path.endsWith("/api/control-plane/providers/claude/connection/login/sess-claude/code") &&
        method === "POST"
      ) {
        expect(JSON.parse(String(init?.body || "{}"))).toEqual({ code: "AUTH-CODE-123" });
        return new Response(
          JSON.stringify({
            session_id: "sess-claude",
            provider_id: "claude",
            auth_mode: "subscription_login",
            status: "completed",
            command: "claude auth login --claudeai",
            auth_url: "https://claude.com/cai/oauth/authorize?code=true",
            user_code: "",
            message: "Authenticated",
            instructions: "",
            output_preview: "",
            last_error: "",
          } satisfies ProviderLoginSession),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/claude/connection/verify") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...claudeConnection,
              configured: true,
              verified: true,
              connection_status: "verified",
              account_label: "Claude",
            },
            verification: {
              verified: true,
              account_label: "Claude",
              plan_label: "",
              checked_via: "auth_status",
              last_error: "",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    act(() => {
      result.current.setProviderConnectionDraft("claude", {
        auth_mode: "subscription_login",
        api_key: "",
        project_id: "",
        base_url: "",
        login_session: {
          session_id: "sess-claude",
          provider_id: "claude",
          auth_mode: "subscription_login",
          status: "awaiting_browser",
          command: "claude auth login --claudeai",
          auth_url: "https://claude.com/cai/oauth/authorize?code=true",
          user_code: "",
          message: "",
          instructions: "",
          output_preview: "",
          last_error: "",
        },
      });
    });

    await act(async () => {
      await result.current.submitProviderLoginCode("claude", "sess-claude", "AUTH-CODE-123");
    });

    await waitFor(() => {
      expect(result.current.providerConnections.claude.verified).toBe(true);
    });
    expect(result.current.providerConnectionDrafts.claude.login_session).toBeNull();
  });

  it("reuses a single popup for Anthropic browser login and does not restart polling on each refresh", async () => {
    const claudeProvider = makeProviderCatalogProvider({
      id: "claude",
      title: "Anthropic",
      supported_auth_modes: ["api_key", "subscription_login"],
      supports_api_key: true,
      supports_subscription_login: true,
      connection_managed: true,
      login_flow_kind: "browser",
    });
    const claudeConnection = makeProviderConnection({
      provider_id: "claude",
      title: "Anthropic",
      auth_mode: "subscription_login",
      configured: false,
      verified: false,
      supports_api_key: true,
      supports_subscription_login: true,
      supported_auth_modes: ["api_key", "subscription_login"],
      connection_status: "not_configured",
    });
    const settings = makeSettings({
      providers: [claudeProvider],
      providerConnections: { claude: claudeConnection },
    });

    let pollCount = 0;
    const popupLocationReplace = vi.fn();
    const popupWindow = {
      closed: false,
      close: vi.fn(),
      opener: {},
      location: {
        replace: popupLocationReplace,
      },
      document: {
        title: "",
        body: {
          innerHTML: "",
        },
      },
    } as unknown as Window;
    window.open = vi.fn(() => popupWindow);

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/providers/claude/connection/login/start") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...claudeConnection,
              configured: true,
              connection_status: "configured",
            },
            login_session: {
              session_id: "sess-claude",
              provider_id: "claude",
              auth_mode: "subscription_login",
              status: "pending",
              command: "claude auth login --claudeai",
              auth_url: "",
              user_code: "",
              message: "Inicializando login oficial",
              instructions: "",
              output_preview: "",
              last_error: "",
            } satisfies ProviderLoginSession,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/claude/connection/login/sess-claude") && method === "GET") {
        pollCount += 1;
        return new Response(
          JSON.stringify({
            session_id: "sess-claude",
            provider_id: "claude",
            auth_mode: "subscription_login",
            status: "awaiting_browser",
            command: "claude auth login --claudeai",
            auth_url: "https://claude.ai/oauth/authorize?state=abc123",
            user_code: "",
            message: "Abra o navegador",
            instructions: "",
            output_preview: "",
            last_error: "",
          } satisfies ProviderLoginSession),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    await act(async () => {
      await result.current.startProviderLogin("claude");
    });

    await waitFor(() => {
      expect(popupLocationReplace).toHaveBeenCalledWith(
        "https://claude.ai/oauth/authorize?state=abc123",
      );
    });

    expect(window.open).toHaveBeenCalledTimes(1);
    expect(window.open).toHaveBeenCalledWith("", "_blank", "popup=yes,width=960,height=800");
    expect(pollCount).toBe(1);
  });

  it("keeps the Anthropic login session pending when the submitted code is still being processed", async () => {
    const claudeProvider = makeProviderCatalogProvider({
      id: "claude",
      title: "Anthropic",
      supported_auth_modes: ["api_key", "subscription_login"],
      supports_api_key: true,
      supports_subscription_login: true,
      connection_managed: true,
      login_flow_kind: "browser",
    });
    const claudeConnection = makeProviderConnection({
      provider_id: "claude",
      title: "Anthropic",
      auth_mode: "subscription_login",
      configured: true,
      verified: false,
      supports_api_key: true,
      supports_subscription_login: true,
      supported_auth_modes: ["api_key", "subscription_login"],
      connection_status: "configured",
    });
    const settings = makeSettings({
      providers: [claudeProvider],
      providerConnections: { claude: claudeConnection },
    });

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (
        path.endsWith("/api/control-plane/providers/claude/connection/login/sess-claude/code") &&
        method === "POST"
      ) {
        return new Response(
          JSON.stringify({
            session_id: "sess-claude",
            provider_id: "claude",
            auth_mode: "subscription_login",
            status: "awaiting_browser",
            command: "claude auth login --claudeai",
            auth_url: "https://claude.com/cai/oauth/authorize?code=true",
            user_code: "",
            message: "Código enviado. Aguardando a confirmação final do Claude Code.",
            instructions: "",
            output_preview: "",
            last_error: "",
          } satisfies ProviderLoginSession),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    act(() => {
      result.current.setProviderConnectionDraft("claude", {
        auth_mode: "subscription_login",
        api_key: "",
        project_id: "",
        base_url: "",
        login_session: {
          session_id: "sess-claude",
          provider_id: "claude",
          auth_mode: "subscription_login",
          status: "awaiting_browser",
          command: "claude auth login --claudeai",
          auth_url: "https://claude.com/cai/oauth/authorize?code=true",
          user_code: "",
          message: "",
          instructions: "",
          output_preview: "",
          last_error: "",
        },
      });
    });

    await act(async () => {
      const session = await result.current.submitProviderLoginCode(
        "claude",
        "sess-claude",
        "AUTH-CODE-123",
      );
      expect(session.status).toBe("awaiting_browser");
    });

    expect(result.current.providerConnections.claude.verified).toBe(false);
    expect(result.current.providerConnectionDrafts.claude.login_session?.status).toBe("awaiting_browser");
  });

  it("preserves the Anthropic login session when backend verification still fails after CLI completion", async () => {
    const claudeProvider = makeProviderCatalogProvider({
      id: "claude",
      title: "Anthropic",
      supported_auth_modes: ["api_key", "subscription_login"],
      supports_api_key: true,
      supports_subscription_login: true,
      connection_managed: true,
      login_flow_kind: "browser",
    });
    const claudeConnection = makeProviderConnection({
      provider_id: "claude",
      title: "Anthropic",
      auth_mode: "subscription_login",
      configured: true,
      verified: false,
      supports_api_key: true,
      supports_subscription_login: true,
      supported_auth_modes: ["api_key", "subscription_login"],
      connection_status: "configured",
    });
    const settings = makeSettings({
      providers: [claudeProvider],
      providerConnections: { claude: claudeConnection },
    });

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (
        path.endsWith("/api/control-plane/providers/claude/connection/login/sess-claude/code") &&
        method === "POST"
      ) {
        return new Response(
          JSON.stringify({
            session_id: "sess-claude",
            provider_id: "claude",
            auth_mode: "subscription_login",
            status: "completed",
            command: "claude auth login --claudeai",
            auth_url: "https://claude.com/cai/oauth/authorize?code=true",
            user_code: "",
            message: "Authentication complete",
            instructions: "",
            output_preview: "",
            last_error: "",
          } satisfies ProviderLoginSession),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (path.endsWith("/api/control-plane/providers/claude/connection/verify") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              ...claudeConnection,
              configured: true,
              verified: false,
              connection_status: "configured",
              last_error:
                "Claude CLI ainda nao autenticado. Conclua a autorizacao no navegador e envie o Authentication Code se solicitado.",
            },
            verification: {
              verified: false,
              account_label: "",
              plan_label: "",
              checked_via: "auth_status",
              last_error:
                "Claude CLI ainda nao autenticado. Conclua a autorizacao no navegador e envie o Authentication Code se solicitado.",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    act(() => {
      result.current.setProviderConnectionDraft("claude", {
        auth_mode: "subscription_login",
        api_key: "",
        project_id: "",
        base_url: "",
        login_session: {
          session_id: "sess-claude",
          provider_id: "claude",
          auth_mode: "subscription_login",
          status: "awaiting_browser",
          command: "claude auth login --claudeai",
          auth_url: "https://claude.com/cai/oauth/authorize?code=true",
          user_code: "",
          message: "",
          instructions: "",
          output_preview: "",
          last_error: "",
        },
      });
    });

    await act(async () => {
      const session = await result.current.submitProviderLoginCode(
        "claude",
        "sess-claude",
        "AUTH-CODE-123",
      );
      expect(session.status).toBe("completed");
    });

    expect(result.current.providerConnections.claude.verified).toBe(false);
    expect(result.current.providerConnectionDrafts.claude.login_session?.session_id).toBe("sess-claude");
    expect(result.current.providerConnections.claude.last_error).toContain("Claude CLI ainda nao autenticado");
  });

  it("saves general settings without serializing legacy integration credentials", async () => {
    const settings = makeSettings();
    const removedCredentialsKey = ["integration", "credentials"].join("_");
    const fetchMock = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/system-settings/general") && method === "PUT") {
        return new Response(JSON.stringify(makeSettings()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    });

    globalThis.fetch = fetchMock as typeof fetch;

    const { result } = renderUseSystemSettings(settings);

    await act(async () => {
      await result.current.handleSave();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, requestInit] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(requestInit?.body ?? "{}")) as Record<string, unknown>;

    expect(payload).not.toHaveProperty(removedCredentialsKey);
    expect(payload).toHaveProperty("resources");
    expect(payload).toHaveProperty("variables");
  });

  it("saves core integration defaults through the canonical connections endpoint", async () => {
    const settings = makeSettings();
    const coreIntegrations = makeCoreIntegrations({
      items: [
        {
          id: "jira",
          title: "Jira",
          description: "Atlassian issue tracking",
          transport: "integration",
          auth_modes: ["api_token"],
          auth_mode: "api_token",
          supports_persistence: true,
          actions: [],
          connection: {
            integration_id: "jira",
            title: "Jira",
            description: "Atlassian issue tracking",
            transport: "integration",
            auth_modes: ["api_token"],
            auth_mode: "api_token",
            configured: false,
            verified: false,
            account_label: "",
            last_verified_at: "",
            last_error: "",
            checked_via: "",
            auth_expired: false,
            metadata: {},
            fields: [
              { key: "JIRA_URL", value: "https://example.atlassian.net" },
              { key: "JIRA_USERNAME", value: "ada@example.com" },
              { key: "JIRA_API_TOKEN", value: "jira-token" },
            ],
            supports_persistence: true,
            connection_status: "not_configured",
          },
        },
      ],
    });

    const fetchMock = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/connections/defaults/core%3Ajira") && method === "PUT") {
        return new Response(
          JSON.stringify({
            connection_key: "core:jira",
            kind: "core",
            integration_key: "jira",
            auth_method: "api_token",
            auth_strategy: "api_token",
            source_origin: "system_default",
            connected: true,
            enabled: true,
            status: "configured",
            last_error: "",
            last_verified_at: "",
            metadata: {
              configured: true,
              verified: false,
              supports_persistence: true,
            },
            fields: [
              { key: "JIRA_URL", value: "https://example.atlassian.net" },
              { key: "JIRA_USERNAME", value: "ada@example.com" },
              { key: "JIRA_API_TOKEN", value: "" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    });

    globalThis.fetch = fetchMock as typeof fetch;

    const { result } = renderUseSystemSettings(settings, coreIntegrations);

    await act(async () => {
      await result.current.connectIntegration("jira");
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, requestInit] = fetchMock.mock.calls[0] ?? [];
    expect(String(path)).toContain("/api/control-plane/connections/defaults/core%3Ajira");
    const payload = JSON.parse(String(requestInit?.body ?? "{}")) as {
      auth_method: string;
      fields: Array<{ key: string; value: string }>;
    };
    expect(payload.auth_method).toBe("api_token");
    expect(payload.fields.map((field) => field.key)).toEqual([
      "JIRA_URL",
      "JIRA_USERNAME",
      "JIRA_API_TOKEN",
    ]);
    expect(result.current.integrationConnections.jira.connection_status).toBe("configured");
    expect(result.current.integrationConnections.jira.configured).toBe(true);
    expect(result.current.integrationConnections.jira.source_origin).toBe("system_default");
  });

  it("verifies core integration defaults through the canonical verify endpoint", async () => {
    const settings = makeSettings();
    const coreIntegrations = makeCoreIntegrations({
      items: [
        {
          id: "browser",
          title: "Browser",
          description: "Governed browser automation",
          transport: "browser",
          auth_modes: [],
          auth_mode: "none",
          supports_persistence: true,
          actions: [],
          connection: {
            integration_id: "browser",
            title: "Browser",
            description: "Governed browser automation",
            transport: "browser",
            auth_modes: [],
            auth_mode: "none",
            configured: true,
            verified: false,
            account_label: "",
            last_verified_at: "",
            last_error: "",
            checked_via: "",
            auth_expired: false,
            metadata: {},
            fields: [],
            supports_persistence: true,
            connection_status: "configured",
          },
        },
      ],
    });

    const fetchMock = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/connections/defaults/core%3Abrowser/verify") && method === "POST") {
        return new Response(
          JSON.stringify({
            connection: {
              connection_key: "core:browser",
              kind: "core",
              integration_key: "browser",
              auth_method: "none",
              auth_strategy: "none",
              source_origin: "system_default",
              connected: true,
              enabled: true,
              status: "verified",
              account_label: "",
              last_verified_at: "2026-04-05T15:30:00Z",
              last_error: "",
              metadata: {
                configured: true,
                verified: true,
                supports_persistence: true,
              },
              fields: [],
            },
            verification: {
              verified: true,
              checked_via: "agent_binding",
              last_error: "",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    });

    globalThis.fetch = fetchMock as typeof fetch;

    const { result } = renderUseSystemSettings(settings, coreIntegrations);

    let verifiedConnection = null;
    await act(async () => {
      verifiedConnection = await result.current.ensureIntegrationConnectionFresh("browser", { force: true });
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/api/control-plane/connections/defaults/core%3Abrowser/verify",
    );
    expect(verifiedConnection?.verified).toBe(true);
    expect(result.current.integrationConnections.browser.connection_status).toBe("verified");
    expect(result.current.integrationConnections.browser.last_verified_at).toBe("2026-04-05T15:30:00Z");
  });

  it("disconnects core integration defaults through the canonical delete endpoint", async () => {
    const settings = makeSettings();
    const coreIntegrations = makeCoreIntegrations({
      items: [
        {
          id: "browser",
          title: "Browser",
          description: "Governed browser automation",
          transport: "browser",
          auth_modes: [],
          auth_mode: "none",
          supports_persistence: true,
          actions: [],
          connection: {
            integration_id: "browser",
            title: "Browser",
            description: "Governed browser automation",
            transport: "browser",
            auth_modes: [],
            auth_mode: "none",
            configured: true,
            verified: true,
            account_label: "",
            last_verified_at: "2026-04-05T15:30:00Z",
            last_error: "",
            checked_via: "agent_binding",
            auth_expired: false,
            metadata: {},
            fields: [],
            supports_persistence: true,
            connection_status: "verified",
          },
        },
      ],
    });

    const fetchMock = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/connections/defaults/core%3Abrowser") && method === "DELETE") {
        return new Response(
          JSON.stringify({
            connection: {
              connection_key: "core:browser",
              kind: "core",
              integration_key: "browser",
              auth_method: "none",
              auth_strategy: "none",
              source_origin: "system_default",
              connected: false,
              enabled: false,
              status: "not_configured",
              account_label: null,
              last_verified_at: "",
              last_error: "",
              metadata: {
                configured: false,
                verified: false,
                supports_persistence: true,
              },
              fields: [],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    });

    globalThis.fetch = fetchMock as typeof fetch;

    const { result } = renderUseSystemSettings(settings, coreIntegrations);

    await act(async () => {
      await result.current.disconnectIntegrationConnection("browser");
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/api/control-plane/connections/defaults/core%3Abrowser",
    );
    expect(result.current.integrationConnections.browser.connection_status).toBe("not_configured");
    expect(result.current.integrationConnections.browser.configured).toBe(false);
    expect(result.current.integrationConnections.browser.verified).toBe(false);
  });

  it("updates browser system availability and connection state without touching provider settings", async () => {
    const settings = makeSettings();
    const coreIntegrations = makeCoreIntegrations({
      items: [
        {
          id: "browser",
          title: "Browser",
          description: "Governed browser automation",
          transport: "browser",
          auth_modes: [],
          auth_mode: "none",
          supports_persistence: true,
          actions: [],
          connection: {
            integration_id: "browser",
            title: "Browser",
            description: "Governed browser automation",
            transport: "browser",
            auth_modes: [],
            auth_mode: "none",
            configured: false,
            verified: false,
            account_label: "",
            last_verified_at: "",
            last_error: "",
            checked_via: "",
            auth_expired: false,
            metadata: {},
            fields: [],
            supports_persistence: true,
            connection_status: "not_configured",
          },
        },
      ],
    });

    globalThis.fetch = vi.fn(async (input, init) => {
      const path = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (path.endsWith("/api/control-plane/integrations/browser/system") && method === "POST") {
        return new Response(
          JSON.stringify({
            integration_id: "browser",
            enabled: true,
            connection: {
              integration_id: "browser",
              title: "Browser",
              description: "Governed browser automation",
              transport: "browser",
              auth_modes: [],
              auth_mode: "none",
              configured: false,
              verified: false,
              account_label: "",
              last_verified_at: "",
              last_error: "",
              checked_via: "",
              auth_expired: false,
              metadata: {},
              fields: [],
              supports_persistence: true,
              connection_status: "not_configured",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${path}`);
    }) as typeof fetch;

    const { result } = renderUseSystemSettings(settings, coreIntegrations);

    await act(async () => {
      await result.current.setIntegrationSystemEnabled("browser", true);
    });

    expect(result.current.draft.values.resources.integrations.browser_enabled).toBe(true);
    expect(result.current.sectionDirty.integrations).toBe(false);
  });
});
