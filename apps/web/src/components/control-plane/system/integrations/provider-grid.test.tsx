/* eslint-disable @next/next/no-img-element */

import type { ImgHTMLAttributes } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProviderGrid } from "@/components/control-plane/system/integrations/provider-grid";

vi.mock("next/image", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt || ""} />,
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

const useSystemSettingsMock = vi.fn();

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
    providerOptions: [
      {
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
      },
    ],
    providerConnections: {
      claude: {
        provider_id: "claude",
        title: "Anthropic",
        auth_mode: "api_key",
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
    setProviderConnectionDraft: vi.fn(),
    setField: vi.fn(),
    connectProviderApiKey: vi.fn(),
    startProviderLogin: vi.fn(),
    submitProviderLoginCode: vi.fn(),
    disconnectProviderConnection: vi.fn(),
    connectProviderLocal: vi.fn(),
    elevenlabsVoiceCatalog: {
      items: [],
      available_languages: [],
      selected_language: "",
      cached: false,
      provider_connected: false,
    },
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
    ollamaModelCatalog: {
      items: [],
      cached: false,
      provider_connected: false,
      base_url: "",
      auth_mode: "local",
    },
    ollamaModelsLoading: false,
    loadOllamaModels: vi.fn(),
    isProviderActionPending: vi.fn(() => false),
    providerActionStatus: vi.fn(() => "idle"),
    enabledProviders: [],
  };
}

describe("ProviderGrid", () => {
  beforeEach(() => {
    useSystemSettingsMock.mockReset();
  });

  it("renders the provider detail with inline auth tabs and descriptive highlight copy", async () => {
    useSystemSettingsMock.mockReturnValue(makeBaseSystemSettingsMock());

    render(<ProviderGrid />);

    const providerCard = screen.getByRole("button", { name: /Anthropic/i });
    const providerGlyph = providerCard.querySelector('[data-provider-logo-glyph="claude"]');

    expect(providerGlyph).toHaveStyle({ backgroundColor: "rgb(212, 120, 62)" });

    fireEvent.click(providerCard);

    expect(await screen.findByRole("tab", { name: "API Key" })).toBeInTheDocument();
    const providerHeading = screen.getByRole("heading", { name: "Anthropic" });
    const detailGlyph = providerHeading.parentElement?.parentElement?.querySelector(
      '[data-provider-logo-glyph="claude"]',
    );
    const detailBannerGlyph = document.querySelector('[data-provider-banner-glyph="claude"]');

    expect(detailGlyph).not.toBeNull();
    expect(detailGlyph).toHaveStyle({ backgroundColor: "rgb(212, 120, 62)" });
    expect(detailBannerGlyph).toHaveStyle({ backgroundColor: "rgb(212, 120, 62)" });
    expect(screen.queryByText("Conexão")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Claude Code CLI" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Anthropic para raciocínio profundo, revisão de código e fluxos oficiais do Claude Code.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Analise este código e sugira melhorias de performance"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conectar" })).toBeInTheDocument();
  });

  it("keeps OpenAI glyphs monochrome in the card and detail banner", async () => {
    const settings = makeBaseSystemSettingsMock();
    settings.providerOptions = [
      {
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
      },
    ];
    settings.providerConnections = {
      codex: {
        provider_id: "codex",
        title: "OpenAI",
        auth_mode: "api_key",
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
        connection_status: "not_configured",
      },
    };
    settings.providerConnectionDrafts = {
      codex: {
        auth_mode: "subscription_login",
        api_key: "",
        project_id: "",
        base_url: "",
        login_session: null,
      },
    };
    useSystemSettingsMock.mockReturnValue(settings);

    render(<ProviderGrid />);

    const providerCard = screen.getByRole("button", { name: /OpenAI/i });
    const providerGlyph = providerCard.querySelector('[data-provider-logo-glyph="codex"]');

    expect(providerGlyph).toHaveStyle({ backgroundColor: "rgb(255, 255, 255)" });

    fireEvent.click(providerCard);

    const providerHeading = await screen.findByRole("heading", { name: "OpenAI" });
    const detailGlyph = providerHeading.parentElement?.parentElement?.querySelector(
      '[data-provider-logo-glyph="codex"]',
    );
    const detailBannerGlyph = document.querySelector('[data-provider-banner-glyph="codex"]');

    expect(detailGlyph).toHaveStyle({ backgroundColor: "rgb(255, 255, 255)" });
    expect(detailBannerGlyph).toHaveStyle({ backgroundColor: "rgb(255, 255, 255)" });
  });

  it("shows connection state only through the primary action button in detail view", async () => {
    const settings = makeBaseSystemSettingsMock();
    settings.providerConnections = {
      claude: {
        provider_id: "claude",
        title: "Anthropic",
        auth_mode: "subscription_login",
        configured: true,
        verified: true,
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
        connection_status: "verified",
      },
    };
    settings.providerConnectionDrafts = {
      claude: {
        auth_mode: "subscription_login",
        api_key: "",
        project_id: "",
        base_url: "",
        login_session: null,
      },
    };
    useSystemSettingsMock.mockReturnValue(settings);

    render(<ProviderGrid />);

    const providerCard = screen.getByRole("button", { name: /Anthropic/i });
    expect(providerCard).toHaveClass("integration-card--connected");
    expect(providerCard.getAttribute("style") ?? "").not.toContain("border-left");
    const checkIcon = providerCard.querySelector(".lucide-check");
    expect(checkIcon).not.toBeNull();
    // The check icon inherits success color from its container's CSS class
    const checkContainer = checkIcon!.closest("div");
    expect(checkContainer?.className).toContain("text-[var(--tone-success-text)]");

    fireEvent.click(providerCard);

    expect(await screen.findByRole("button", { name: "Desconectar" })).toBeInTheDocument();
    expect(screen.queryByText("Conectado")).not.toBeInTheDocument();
    expect(screen.queryByText("Pendente")).not.toBeInTheDocument();
  });
});
