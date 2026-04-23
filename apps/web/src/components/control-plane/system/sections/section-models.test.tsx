/* eslint-disable @next/next/no-img-element */

import type { ImgHTMLAttributes } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { ProviderAccordionItem, ProviderLogo } from "@/components/control-plane/system/sections/section-models";

vi.mock("next/image", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt || ""} />,
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

const useSystemSettingsMock = vi.fn();
const clipboardWriteTextMock = vi.fn();

vi.mock("@/hooks/use-system-settings", () => ({
  useSystemSettings: () => useSystemSettingsMock(),
}));

function makeBaseSystemSettingsMock() {
  return {
    draft: {
      values: {
        models: {
          elevenlabs_default_language: "pt",
          elevenlabs_default_voice: "",
          elevenlabs_default_voice_label: "",
          kokoro_default_language: "pt-br",
          kokoro_default_voice: "pf_dora",
          kokoro_default_voice_label: "",
        },
      },
    },
    providerConnections: {},
    providerConnectionDrafts: {},
    setProviderConnectionDraft: vi.fn(),
    setField: vi.fn(),
    connectProviderApiKey: vi.fn(),
    startProviderLogin: vi.fn(),
    submitProviderLoginCode: vi.fn(),
    disconnectProviderConnection: vi.fn(),
    connectProviderLocal: vi.fn(),
    elevenlabsVoiceCatalog: { items: [], available_languages: [], selected_language: "", cached: false, provider_connected: false },
    elevenlabsVoicesLoading: false,
    loadElevenLabsVoices: vi.fn(),
    kokoroVoiceCatalog: {
      items: [],
      available_languages: [],
      selected_language: "pt-br",
      default_language: "pt-br",
      default_voice: "pf_dora",
      default_voice_label: "",
      downloaded_voice_ids: [],
      provider_connected: true,
    },
    kokoroVoicesLoading: false,
    kokoroDownloadJobForVoice: vi.fn(() => null),
    loadKokoroVoices: vi.fn(),
    downloadKokoroVoice: vi.fn(),
    ollamaModelCatalog: { items: [], cached: false, provider_connected: false, base_url: "", auth_mode: "local" },
    ollamaModelsLoading: false,
    loadOllamaModels: vi.fn(),
    isProviderActionPending: vi.fn(() => false),
    providerActionStatus: vi.fn(() => "idle"),
    enabledProviders: [],
  };
}

describe("ProviderAccordionItem", () => {
  beforeEach(() => {
    useSystemSettingsMock.mockReset();
    clipboardWriteTextMock.mockReset();
    Object.defineProperty(globalThis.navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: clipboardWriteTextMock.mockResolvedValue(undefined),
      },
    });
  });

  it("renders only the auth tabs supported by Ollama", () => {
    useSystemSettingsMock.mockReturnValue({
      ...makeBaseSystemSettingsMock(),
      providerConnections: {
        ollama: {
          provider_id: "ollama",
          title: "Ollama",
          auth_mode: "local",
          configured: false,
          verified: false,
          account_label: "",
          plan_label: "",
          last_verified_at: "",
          last_error: "",
          project_id: "",
          command_present: true,
          supports_api_key: true,
          supports_subscription_login: false,
          supports_local_connection: true,
          supported_auth_modes: ["local", "api_key"],
          login_flow_kind: "",
          requires_project_id: false,
          api_key_present: false,
          api_key_preview: "",
          base_url: "",
          connection_status: "not_configured",
        },
      },
      providerConnectionDrafts: {
        ollama: {
          auth_mode: "local",
          api_key: "",
          project_id: "",
          base_url: "",
          login_session: null,
        },
      },
    });

    render(
      <ProviderAccordionItem
        provider={{
          id: "ollama",
          title: "Ollama",
          vendor: "Ollama",
          category: "general",
          commandPresent: true,
          supportsApiKey: true,
          supportsSubscriptionLogin: false,
          supportsLocalConnection: true,
          supportedAuthModes: ["local", "api_key"],
          loginFlowKind: "",
          requiresProjectId: false,
          connectionManaged: true,
          showInSettings: true,
        }}
        isOpen
        onToggle={() => {}}
      />,
    );

    expect(screen.getByRole("tab", { name: "API Key" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Servidor local" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Assinatura / login" })).not.toBeInTheDocument();
  });

  it("renders Claude Code CLI content when Claude local mode is active", () => {
    useSystemSettingsMock.mockReturnValue({
      ...makeBaseSystemSettingsMock(),
      providerConnections: {
        claude: {
          provider_id: "claude",
          title: "Anthropic",
          auth_mode: "local",
          configured: false,
          verified: false,
          account_label: "",
          plan_label: "",
          last_verified_at: "",
          last_error: "",
          project_id: "",
          command_present: true,
          supports_api_key: true,
          supports_subscription_login: false,
          supports_local_connection: true,
          supported_auth_modes: ["api_key", "local"],
          login_flow_kind: null,
          requires_project_id: false,
          api_key_present: false,
          api_key_preview: "",
          base_url: "",
          connection_status: "not_configured",
        },
      },
      providerConnectionDrafts: {
        claude: {
          auth_mode: "local",
          api_key: "",
          project_id: "",
          base_url: "",
          login_session: null,
        },
      },
    });

    render(
      <ProviderAccordionItem
        provider={{
          id: "claude",
          title: "Anthropic",
          vendor: "Anthropic",
          category: "general",
          commandPresent: true,
          supportsApiKey: true,
          supportsSubscriptionLogin: false,
          supportsLocalConnection: true,
          supportedAuthModes: ["api_key", "local"],
          loginFlowKind: null,
          requiresProjectId: false,
          connectionManaged: true,
          showInSettings: true,
        }}
        isOpen
        onToggle={() => {}}
      />,
    );

    expect(screen.getByRole("tab", { name: "Claude Code CLI" })).toBeInTheDocument();
    expect(screen.getAllByText("Claude Code CLI").length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText(
        "Opcional: se você já autenticou o Claude Code em outra máquina e montou o CLAUDE_CONFIG_DIR no container, basta clicar em Verificar para detectar a sessão. Caso contrário use a opção de assinatura acima.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Servidor Ollama")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("http://localhost:11434")).not.toBeInTheDocument();
  });

  it("shows the missing CLI warning and disables subscription login connect when the command is unavailable", () => {
    useSystemSettingsMock.mockReturnValue({
      ...makeBaseSystemSettingsMock(),
      providerConnections: {
        gemini: {
          provider_id: "gemini",
          title: "Google",
          auth_mode: "subscription_login",
          configured: false,
          verified: false,
          account_label: "",
          plan_label: "",
          last_verified_at: "",
          last_error: "",
          project_id: "",
          command_present: false,
          supports_api_key: true,
          supports_subscription_login: true,
          supports_local_connection: false,
          supported_auth_modes: ["api_key", "subscription_login"],
          login_flow_kind: "browser",
          requires_project_id: false,
          api_key_present: false,
          api_key_preview: "",
          base_url: "",
          connection_status: "not_configured",
        },
      },
      providerConnectionDrafts: {
        gemini: {
          auth_mode: "subscription_login",
          api_key: "",
          project_id: "",
          base_url: "",
          login_session: null,
        },
      },
    });

    render(
      <ProviderAccordionItem
        provider={{
          id: "gemini",
          title: "Google",
          vendor: "Google",
          category: "general",
          commandPresent: false,
          supportsApiKey: true,
          supportsSubscriptionLogin: true,
          supportsLocalConnection: false,
          supportedAuthModes: ["api_key", "subscription_login"],
          loginFlowKind: "browser",
          requiresProjectId: false,
          connectionManaged: true,
          showInSettings: true,
        }}
        isOpen
        onToggle={() => {}}
      />,
    );

    expect(
      screen.getByText(/O runtime oficial deste provider não está disponível neste ambiente/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "API Key" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Assinatura / login" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conectar" })).toBeDisabled();
  });

  it("renders colored glyphs for different providers when accented", () => {
    render(
      <div>
        <ProviderLogo providerId="codex" title="OpenAI" accented />
        <ProviderLogo providerId="elevenlabs" title="ElevenLabs" accented />
        <ProviderLogo providerId="gemini" title="Google" accented />
        <ProviderLogo providerId="ollama" title="Ollama" accented />
      </div>,
    );

    expect(screen.getByTestId("provider-logo-codex")).toHaveStyle({
      backgroundColor: "rgb(255, 255, 255)",
    });
    expect(screen.getByTestId("provider-logo-elevenlabs")).toHaveStyle({
      backgroundColor: "rgb(255, 255, 255)",
    });
    expect(screen.getByTestId("provider-logo-gemini")).toHaveStyle({
      backgroundColor: "rgb(86, 138, 248)",
    });
    expect(screen.getByTestId("provider-logo-ollama")).toHaveStyle({
      backgroundColor: "rgb(255, 255, 255)",
    });
  });

  it("highlights the device code and lets the user copy it during official login", async () => {
    useSystemSettingsMock.mockReturnValue({
      ...makeBaseSystemSettingsMock(),
      providerConnections: {
        codex: {
          provider_id: "codex",
          title: "OpenAI",
          auth_mode: "subscription_login",
          configured: false,
          verified: false,
          account_label: "",
          plan_label: "",
          last_verified_at: "",
          last_error: "",
          project_id: "",
          command_present: true,
          supports_api_key: true,
          supports_subscription_login: true,
          supports_local_connection: false,
          supported_auth_modes: ["api_key", "subscription_login"],
          login_flow_kind: "browser",
          requires_project_id: false,
          api_key_present: false,
          api_key_preview: "",
          base_url: "",
          connection_status: "auth_in_progress",
        },
      },
      providerConnectionDrafts: {
        codex: {
          auth_mode: "subscription_login",
          api_key: "",
          project_id: "",
          base_url: "",
          login_session: {
            session_id: "sess_123",
            provider_id: "codex",
            auth_mode: "subscription_login",
            status: "awaiting_browser",
            command: "codex login",
            auth_url: "https://example.com/device",
            user_code: "OPEN-AI42",
            message: "",
            instructions: "",
            output_preview: "",
            last_error: "",
          },
        },
      },
    });

    render(
      <ProviderAccordionItem
        provider={{
          id: "codex",
          title: "OpenAI",
          vendor: "OpenAI",
          category: "general",
          commandPresent: true,
          supportsApiKey: true,
          supportsSubscriptionLogin: true,
          supportsLocalConnection: false,
          supportedAuthModes: ["api_key", "subscription_login"],
          loginFlowKind: "browser",
          requiresProjectId: false,
          connectionManaged: true,
          showInSettings: true,
        }}
        isOpen
        onToggle={() => {}}
      />,
    );

    expect(screen.getByText("Código de autorização")).toBeInTheDocument();
    expect(screen.getByText("OPEN-AI42")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copiar código de autenticação" }));

    await waitFor(() => {
      expect(clipboardWriteTextMock).toHaveBeenCalledWith("OPEN-AI42");
    });
  });

  it("renders the Claude browser auth flow without the legacy code entry", async () => {
    const submitProviderLoginCode = vi.fn().mockResolvedValue({
      session_id: "sess_claude",
      provider_id: "claude",
      auth_mode: "subscription_login",
      status: "awaiting_browser",
      command: "claude auth login --claudeai",
      auth_url: "https://claude.com/cai/oauth/authorize?code=true&state=test",
      user_code: "",
      message: "Abrindo a página oficial de login da Anthropic.",
      instructions: "",
      output_preview: "",
      last_error: "",
    });
    useSystemSettingsMock.mockReturnValue({
      ...makeBaseSystemSettingsMock(),
      submitProviderLoginCode,
      providerConnections: {
        claude: {
          provider_id: "claude",
          title: "Anthropic",
          auth_mode: "subscription_login",
          configured: true,
          verified: false,
          account_label: "",
          plan_label: "",
          last_verified_at: "",
          last_error: "",
          project_id: "",
          command_present: true,
          supports_api_key: true,
          supports_subscription_login: true,
          supports_local_connection: false,
          supported_auth_modes: ["api_key", "subscription_login"],
          login_flow_kind: "browser",
          requires_project_id: false,
          api_key_present: false,
          api_key_preview: "",
          base_url: "",
          connection_status: "configured",
        },
      },
      providerConnectionDrafts: {
        claude: {
          auth_mode: "subscription_login",
          api_key: "",
          project_id: "",
          base_url: "",
          login_session: {
            session_id: "sess_claude",
            provider_id: "claude",
            auth_mode: "subscription_login",
            status: "awaiting_browser",
            command: "claude auth login --claudeai",
            auth_url: "https://claude.com/cai/oauth/authorize?code=true&state=test",
            user_code: "",
            message: "Abrindo a página oficial de login da Anthropic.",
            instructions: "Abra o link do Claude Code e conclua o login no navegador.",
            output_preview: "",
            last_error: "",
          },
        },
      },
    });

    render(
      <ProviderAccordionItem
        provider={{
          id: "claude",
          title: "Anthropic",
          vendor: "Anthropic",
          category: "general",
          commandPresent: true,
          supportsApiKey: true,
          supportsSubscriptionLogin: true,
          supportsLocalConnection: false,
          supportedAuthModes: ["api_key", "subscription_login"],
          loginFlowKind: "browser",
          requiresProjectId: false,
          connectionManaged: true,
          showInSettings: true,
        }}
        isOpen
        onToggle={() => {}}
      />,
    );

    expect(screen.getByText("Authentication Code")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Cole o código de autenticação")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir página de autorização" })).toHaveAttribute(
      "href",
      "https://claude.com/cai/oauth/authorize?code=true&state=test",
    );
  });

  it("prefers the Anthropic login-session error over a stale connection error while the browser auth is pending", () => {
    useSystemSettingsMock.mockReturnValue({
      ...makeBaseSystemSettingsMock(),
      providerConnections: {
        claude: {
          provider_id: "claude",
          title: "Anthropic",
          auth_mode: "subscription_login",
          configured: true,
          verified: false,
          account_label: "",
          plan_label: "",
          last_verified_at: "",
          last_error: "}",
          project_id: "",
          command_present: true,
          supports_api_key: true,
          supports_subscription_login: true,
          supports_local_connection: false,
          supported_auth_modes: ["api_key", "subscription_login"],
          login_flow_kind: "browser",
          requires_project_id: false,
          api_key_present: false,
          api_key_preview: "",
          base_url: "",
          connection_status: "configured",
        },
      },
      providerConnectionDrafts: {
        claude: {
          auth_mode: "subscription_login",
          api_key: "",
          project_id: "",
          base_url: "",
          login_session: {
            session_id: "sess_claude",
            provider_id: "claude",
            auth_mode: "subscription_login",
            status: "awaiting_browser",
            command: "claude auth login --claudeai",
            auth_url: "https://claude.com/cai/oauth/authorize?code=true&state=test",
            user_code: "",
            message: "Abrindo a página oficial de login da Anthropic.",
            instructions: "Abra o link do Claude Code e conclua o login no navegador.",
            output_preview: "",
            last_error:
              "Falha ao concluir o login da Anthropic no navegador. Tente novamente.",
          },
        },
      },
    });

    render(
      <ProviderAccordionItem
        provider={{
          id: "claude",
          title: "Anthropic",
          vendor: "Anthropic",
          category: "general",
          commandPresent: true,
          supportsApiKey: true,
          supportsSubscriptionLogin: true,
          supportsLocalConnection: false,
          supportedAuthModes: ["api_key", "subscription_login"],
          loginFlowKind: "browser",
          requiresProjectId: false,
          connectionManaged: true,
          showInSettings: true,
        }}
        isOpen
        onToggle={() => {}}
      />,
    );

    expect(screen.getByText("Falha ao concluir o login da Anthropic no navegador. Tente novamente.")).toBeInTheDocument();
    expect(screen.queryByText("}")).not.toBeInTheDocument();
  });
});
