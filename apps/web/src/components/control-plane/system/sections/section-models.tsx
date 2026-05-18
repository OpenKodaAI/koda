"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  ExternalLink,
  KeyRound,
  Link2,
  RefreshCcw,
  Server,
  Trash2,
  Unplug,
  Upload,
} from "lucide-react";

/**
 * Official Apple logo silhouette (the bitten-apple mark) rendered as a
 * monochrome glyph that inherits color from the surrounding text via
 * ``currentColor``. Used as the visual anchor for the Metal/Apple Silicon
 * acceleration toggle. Path is the canonical Apple Inc. logo silhouette
 * commonly bundled in icon sets — the lucide ``Apple`` icon is a generic
 * apple shape (with a stem and leaf) and would not communicate the Apple
 * brand context this toggle requires.
 */
function AppleLogo({ size = 18 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M17.543 12.823c-.027-2.726 2.225-4.034 2.327-4.097-1.27-1.857-3.245-2.111-3.945-2.139-1.68-.17-3.281 .988-4.135 .988-.854 0-2.166-.964-3.564-.937-1.832 .027-3.524 1.066-4.464 2.708-1.904 3.301-.485 8.179 1.366 10.853 .908 1.31 1.985 2.78 3.398 2.726 1.367-.054 1.881-.882 3.535-.882 1.654 0 2.117 .882 3.557 .855 1.469-.027 2.4-1.337 3.298-2.65 1.04-1.526 1.469-3.005 1.495-3.082-.033-.014-2.844-1.092-2.868-4.343zM14.79 4.967c.755-.916 1.265-2.187 1.126-3.456-1.087 .045-2.408 .726-3.19 1.642-.7 .811-1.314 2.106-1.149 3.348 1.213 .094 2.46-.616 3.213-1.534z" />
    </svg>
  );
}
import { AsyncActionButton, InlineSpinner } from "@/components/ui/async-feedback";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { SecretInput } from "@/components/ui/secret-controls";
import {
  SELECT_ALL_VALUE,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { AnimatedSwitch } from "@/components/control-plane/system/shared/animated-switch";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { EffortPicker, type EffortCapability } from "@/components/control-plane/shared/effort-picker";
import { ModelSelector } from "@/components/control-plane/shared/model-selector";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import type { ProviderLoginSession } from "@/lib/control-plane";
import { normalizeFallbackOrder } from "@/lib/system-settings-model";
import { findFieldError } from "@/lib/system-settings-schema";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format byte counts into human-readable suffixes (B / KB / MB / GB). */
export function formatAssetBytes(bytes: number | null | undefined): string {
  const value = Number(bytes ?? 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)} GB`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} KB`;
  return `${Math.round(value)} B`;
}

export function providerLabel(providerId: string) {
  if (providerId === "claude") return "Anthropic";
  if (providerId === "codex") return "OpenAI";
  if (providerId === "gemini") return "Google";
  if (providerId === "perplexity") return "Perplexity";
  if (providerId === "mistral") return "Mistral AI";
  if (providerId === "qwen") return "Qwen (Alibaba)";
  if (providerId === "kimi") return "Kimi (Moonshot AI)";
  if (providerId === "groq") return "Groq";
  if (providerId === "deepseek") return "DeepSeek";
  if (providerId === "xai") return "xAI Grok";
  if (providerId === "openrouter") return "OpenRouter";
  if (providerId === "supertonic") return "Supertonic";
  return providerId;
}

// Logos / accents / colors are centralized in `../shared/provider-brand`.
// We import them here for in-file use and re-export so existing consumers
// (`PROVIDER_ACCENTS`, `PROVIDER_LOGOS`, etc.) keep working without churn.
import {
  PROVIDER_LOGOS,
  PROVIDER_ICON_COMPONENTS,
  PROVIDER_ACCENTS,
  MASKED_LOGO_PROVIDERS,
  MONOCHROME_LOGO_PROVIDERS,
  COLORED_BRAND_LOGO_PROVIDERS,
  providerGlyphColor,
} from "../../shared/provider-brand";

export {
  PROVIDER_LOGOS,
  PROVIDER_ICON_COMPONENTS,
  PROVIDER_ACCENTS,
  MASKED_LOGO_PROVIDERS,
  MONOCHROME_LOGO_PROVIDERS,
  COLORED_BRAND_LOGO_PROVIDERS,
  providerGlyphColor,
};

export function providerOrder(category: string) {
  if (category === "general") return 0;
  if (category === "voice") return 1;
  if (category === "transcription") return 2;
  if (category === "media") return 3;
  return 4;
}

function SelectLoadingSpinner({ loading }: { loading: boolean }) {
  if (!loading) return null;
  return <InlineSpinner className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]" />;
}

export type ProviderOption = ReturnType<typeof useSystemSettings>["providerOptions"][number];

export function providerDescription(providerId: string, category: string) {
  if (providerId === "claude") return "Anthropic via API Key, assinatura do Claude Code ou CLI local já autenticado.";
  if (providerId === "codex") return "OpenAI via API Key ou login oficial do Codex.";
  if (providerId === "gemini") return "Google via GEMINI_API_KEY ou login oficial do Gemini CLI.";
  if (providerId === "elevenlabs") return "Voz premium com API Key, idioma padrão e seleção de vozes.";
  if (providerId === "ollama") return "Servidor Ollama local ou cloud com API Key, usando o catálogo real de modelos.";
  if (providerId === "whispercpp") {
    return "Transcrição local via whisper.cpp, com modelos baixados sob demanda.";
  }
  if (providerId === "supertonic") {
    return "Voz local/offline via Supertonic, com modelos ONNX e vozes importadas sob demanda.";
  }
  if (providerId === "perplexity") {
    return "Modelos Sonar com pesquisa em tempo real e citações de fontes via API Key. Acesso programático via console.";
  }
  if (providerId === "mistral") {
    return "Família Mistral (Large, Medium, Small, Codestral, Pixtral) via La Plateforme. Visão via Pixtral, código via Codestral.";
  }
  if (providerId === "qwen") {
    return "Família Qwen via Alibaba DashScope International. Inclui Qwen3-Coder, Qwen-VL e contexto longo de até 1M tokens.";
  }
  if (providerId === "kimi") {
    return "Modelos Kimi K2 e Moonshot v1 com janela de contexto até 128K tokens. Visão via kimi-vision.";
  }
  if (providerId === "groq") {
    return "Inferência ultra-rápida via LPU para Llama 3.3, Mixtral, Gemma2, DeepSeek-R1 distill e Qwen 2.5.";
  }
  if (providerId === "deepseek") {
    return "DeepSeek V3 (chat) e R1 (reasoner) com prompt caching automático e custo significativamente menor.";
  }
  if (providerId === "xai") {
    return "Grok 4, Grok 3 e variantes mini/fast da xAI. Visão via grok-2-vision.";
  }
  if (providerId === "openrouter") {
    return "Roteamento OpenRouter para centenas de modelos via API Key, com catálogo dinâmico e aliases curados.";
  }
  if (category === "voice") return "Provider multimodal focado em voz e áudio.";
  if (category === "media") return "Provider multimídia disponível para fluxos especializados.";
  return "Provider disponível no catálogo global do sistema.";
}

export function providerLoginCopy(providerId: string) {
  if (providerId === "claude") {
    return "Abra o link gerado pelo Claude Code, autorize no navegador e cole o código aqui para conectar sua assinatura Anthropic.";
  }
  if (providerId === "codex") {
    return "Use o login oficial do Codex com sua conta OpenAI/ChatGPT. A cobrança da API continua separada da assinatura.";
  }
  if (providerId === "perplexity") {
    return "Cole sua API key obtida em perplexity.ai/settings/api. Acesso pago via créditos ou assinatura Pro.";
  }
  if (providerId === "mistral") {
    return "Cole sua API key obtida em console.mistral.ai/api-keys.";
  }
  if (providerId === "qwen") {
    return "Cole sua API key obtida em dashscope.console.aliyun.com (versão internacional).";
  }
  if (providerId === "kimi") {
    return "Cole sua API key obtida em platform.moonshot.ai/console/api-keys.";
  }
  if (providerId === "groq") {
    return "Cole sua API key obtida em console.groq.com/keys.";
  }
  if (providerId === "deepseek") {
    return "Cole sua API key obtida em platform.deepseek.com/api_keys.";
  }
  if (providerId === "xai") {
    return "Cole sua API key obtida em console.x.ai.";
  }
  if (providerId === "openrouter") {
    return "Cole sua API key obtida em openrouter.ai/settings/keys.";
  }
  return "Use o login oficial do Gemini CLI com sua conta Google.";
}

export function providerLocalTitle(providerId: string) {
  if (providerId === "claude") return "Claude Code CLI";
  if (providerId === "ollama") return "Servidor Ollama";
  return "Servidor local";
}

export function providerLocalDescription(providerId: string) {
  if (providerId === "claude") {
    return (
      "Opcional: se você já autenticou o Claude Code em outra máquina e montou o CLAUDE_CONFIG_DIR no container, " +
      "basta clicar em Verificar para detectar a sessão. Caso contrário use a opção de assinatura acima."
    );
  }
  if (providerId === "ollama") {
    return "Use um endpoint local ou remoto compatível com a API do Ollama para listar e executar modelos.";
  }
  return "Configure a conexão local para este provider.";
}

export function providerActionCopy(providerId: string) {
  if (providerId === "claude") return "Claude Code";
  if (providerId === "codex") return "Codex";
  if (providerId === "gemini") return "Gemini CLI";
  return "runtime oficial";
}

export function elevenlabsVoiceOptionLabel(voice: {
  name: string;
  accent: string;
  gender: string;
  category: string;
  api_available?: boolean;
}) {
  const metadata = [
    voice.accent,
    voice.gender,
    voice.category,
    voice.api_available === false ? "requer plano pago/API" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return metadata ? `${voice.name} — ${metadata}` : voice.name;
}

export function isSelectableProvider(
  provider: {
    id: string;
    category: string;
    commandPresent: boolean;
    supportsApiKey: boolean;
    supportsSubscriptionLogin: boolean;
    supportsLocalConnection: boolean;
    connectionManaged: boolean;
  } | undefined,
  connection: ReturnType<typeof useSystemSettings>["providerConnections"][string] | undefined,
  functionId = "general",
) {
  if (!provider) return false;
  if (provider.connectionManaged) {
    if (provider.id === "codex" && ["image", "transcription"].includes(functionId)) {
      return Boolean(connection?.api_key_present && (!connection?.auth_mode || connection.auth_mode === "api_key"));
    }
    return Boolean(connection?.verified);
  }
  if (provider.id === "kokoro") {
    return true;
  }
  return provider.commandPresent;
}

// ---------------------------------------------------------------------------
// ProviderLogo
// ---------------------------------------------------------------------------

export function ProviderLogo({
  providerId,
  title,
  active = false,
  accented = false,
}: {
  providerId: string;
  title: string;
  active?: boolean;
  accented?: boolean;
}) {
  const Icon = PROVIDER_ICON_COMPONENTS[providerId];
  const accent = PROVIDER_ACCENTS[providerId] || "255 255 255";
  const glyphColor = providerGlyphColor(providerId, active || accented);
  const wrapperStyle = active
    ? ({
        borderColor: `rgba(${accent}, 0.42)`,
        backgroundColor: `rgba(${accent}, 0.12)`,
        boxShadow: `0 0 0 1px rgba(${accent}, 0.08) inset`,
      } satisfies CSSProperties)
    : undefined;
  if (Icon) {
    return (
      <div
        className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] transition-colors"
        style={wrapperStyle}
      >
        <Icon
          className="h-5 w-5"
          style={{ color: glyphColor }}
        />
      </div>
    );
  }

  const logo = PROVIDER_LOGOS[providerId];
  if (logo) {
    // Colored brand logos opt out of the mask-tint so their original palette
    // shows through even when the card is active/accented. All other logos
    // keep the existing behavior (tinted silhouette when active/accented or
    // when explicitly opted into MASKED_LOGO_PROVIDERS).
    const preserveBrandColors = COLORED_BRAND_LOGO_PROVIDERS.has(providerId);
    const renderAsMask =
      !preserveBrandColors &&
      (active || accented || MASKED_LOGO_PROVIDERS.has(providerId));
    return (
      <div
        className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] transition-colors"
        style={wrapperStyle}
      >
        {renderAsMask ? (
          <span
            className="block h-6 w-6"
            data-provider-logo-glyph={providerId}
            data-testid={`provider-logo-${providerId}`}
            style={
              {
                backgroundColor: glyphColor,
                WebkitMaskImage: `url(${logo})`,
                maskImage: `url(${logo})`,
                WebkitMaskRepeat: "no-repeat",
                maskRepeat: "no-repeat",
                WebkitMaskPosition: "center",
                maskPosition: "center",
                WebkitMaskSize: "contain",
                maskSize: "contain",
              } satisfies CSSProperties
            }
          />
        ) : (
          <Image src={logo} alt={title} width={24} height={24} className="h-6 w-6 object-contain opacity-95" />
        )}
      </div>
    );
  }

  return (
    <div
      className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] text-sm font-semibold transition-colors"
      style={wrapperStyle}
    >
      <span style={{ color: glyphColor }}>
        {title.slice(0, 1).toUpperCase()}
      </span>
    </div>
  );
}

export function useProviderConnectionUi(provider: ProviderOption, isOpen: boolean) {
  const {
    draft,
    providerConnections,
    providerConnectionDrafts,
    setProviderConnectionDraft,
    setField,
    connectProviderApiKey,
    startProviderLogin,
    submitProviderLoginCode,
    disconnectProviderConnection,
    connectProviderLocal,
    elevenlabsVoiceCatalog,
    elevenlabsVoicesLoading,
    loadElevenLabsVoices,
    kokoroVoiceCatalog,
    kokoroVoicesLoading,
    kokoroModelStatus,
    supertonicVoiceCatalog,
    supertonicVoicesLoading,
    supertonicModelCatalog,
    supertonicModelsLoading,
    whisperCatalog,
    isDownloadingKokoroAsset,
    isDownloadingSupertonicAsset,
    isDownloadingWhisperVariant,
    loadKokoroVoices,
    loadKokoroModelStatus,
    loadSupertonicModels,
    loadSupertonicVoices,
    loadWhisperCatalog,
    downloadKokoroVoice,
    downloadKokoroModel,
    downloadSupertonicModel,
    downloadSupertonicVoice,
    importSupertonicVoice,
    downloadWhisperModel,
    deleteKokoroModelAsset,
    deleteKokoroVoiceAsset,
    deleteSupertonicModelAsset,
    deleteSupertonicVoiceAsset,
    deleteWhisperVariantAsset,
    ollamaModelCatalog,
    ollamaModelsLoading,
    loadOllamaModels,
    isProviderActionPending,
    providerActionStatus,
    enabledProviders,
  } = useSystemSettings();

  const connection = providerConnections[provider.id];
  const connectionDraft = providerConnectionDrafts[provider.id];
  const activeMode = connectionDraft?.auth_mode || connection?.auth_mode || "api_key";
  // Local flag so the persisted-key view can switch back to an editable
  // SecretInput when the operator explicitly asks to replace the stored key.
  const [replacingApiKey, setReplacingApiKey] = useState(false);
  const markReplacingKey = () => setReplacingApiKey(true);
  const unmarkReplacingKey = () => setReplacingApiKey(false);
  // Auto-collapse back to the persisted view after a successful save: the
  // `connectProviderApiKey` flow updates `connection.last_verified_at` (and
  // resets `connectionDraft.api_key` to ""), so using that as the reset
  // signal keeps the edit view open during typing but closes it as soon as
  // the new key is persisted. The setState here is idempotent and runs in
  // response to a prop change, so the cascading-renders lint is safely
  // disabled for this intentional synchronization.
  const lastVerifiedAt = connection?.last_verified_at ?? "";
  useEffect(() => {
    if (lastVerifiedAt) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setReplacingApiKey(false);
    }
  }, [lastVerifiedAt]);
  const supportsAnyAuth = provider.connectionManaged;
  const supportsApiKey = provider.supportedAuthModes.includes("api_key");
  const supportsLocalConnection = provider.supportedAuthModes.includes("local");
  const supportsSubscriptionLogin = provider.supportedAuthModes.includes("subscription_login");
  const connectionState = supportsAnyAuth
    ? connection?.connection_status || "not_configured"
    : "internal";
  const enabled = enabledProviders.includes(provider.id);
  const hasActiveConnection = supportsAnyAuth
    ? connectionState === "verified" ||
      connectionState === "configured" ||
      Boolean(connection?.verified || connection?.configured)
    : enabled;
  const loginSession = connectionDraft?.login_session;
  const elevenlabsLanguage = draft.values.models.elevenlabs_default_language || "";
  const elevenlabsDefaultVoice = draft.values.models.elevenlabs_default_voice || "";
  const elevenlabsDefaultVoiceLabel = draft.values.models.elevenlabs_default_voice_label || "";
  const kokoroLanguage = draft.values.models.kokoro_default_language || "pt-br";
  const kokoroDefaultVoice = draft.values.models.kokoro_default_voice || "pf_dora";
  const kokoroDefaultVoiceLabel = draft.values.models.kokoro_default_voice_label || "";
  const kokoroDownloadActive = isDownloadingKokoroAsset(kokoroDefaultVoice);
  const kokoroModelDownloading = isDownloadingKokoroAsset("model");
  const kokoroSelectedVoice = kokoroVoiceCatalog.items.find(
    (voice) => voice.voice_id === kokoroDefaultVoice,
  );
  const supertonicModel = draft.values.models.supertonic_default_model || "supertonic-3";
  const supertonicLanguage = draft.values.models.supertonic_default_language || "pt";
  const supertonicDefaultVoice = draft.values.models.supertonic_default_voice || "F1";
  const supertonicAssetKey = `${supertonicModel}:${supertonicDefaultVoice}`;
  const supertonicVoiceDownloading = isDownloadingSupertonicAsset(supertonicAssetKey);
  const supertonicModelDownloading = isDownloadingSupertonicAsset(supertonicModel);
  const supertonicSelectedModel = supertonicModelCatalog?.items.find(
    (item) => item.model_id === supertonicModel,
  );
  const supertonicSelectedVoice = supertonicVoiceCatalog.items.find(
    (voice) => voice.voice_id === supertonicDefaultVoice,
  );
  const loginPending = Boolean(
    loginSession && ["pending", "awaiting_browser"].includes(loginSession.status),
  );
  const hasApiKeyDraft = Boolean(connectionDraft?.api_key.trim());
  const configuredForActiveMode =
    connection?.auth_mode === activeMode && Boolean(connection?.configured || connection?.verified);
  const shouldShowDisconnect =
    supportsAnyAuth &&
    configuredForActiveMode &&
    !(activeMode === "api_key" && hasApiKeyDraft) &&
    !loginPending;
  const canConnectApiKey =
    activeMode === "api_key" &&
    (hasApiKeyDraft || (!configuredForActiveMode && Boolean(connection?.api_key_present)));
  const actionLabel = shouldShowDisconnect ? "Desconectar" : "Conectar";
  const actionIcon = shouldShowDisconnect
    ? Unplug
    : activeMode === "api_key"
      ? KeyRound
      : activeMode === "local"
        ? Server
        : Link2;
  const actionVariant: "danger" | "quiet" = shouldShowDisconnect ? "danger" : "quiet";
  const actionLoading = shouldShowDisconnect
    ? isProviderActionPending(provider.id, "disconnect")
    : isProviderActionPending(provider.id, "connect") ||
      (activeMode === "subscription_login" && loginPending);
  const actionStatus = shouldShowDisconnect
    ? providerActionStatus(provider.id, "disconnect")
    : providerActionStatus(provider.id, "connect");
  const actionLoadingLabel = shouldShowDisconnect
    ? "Desconectando"
    : activeMode === "subscription_login" && loginPending
      ? "Aguardando"
      : "Conectando";
  const actionDisabled =
    !supportsAnyAuth ||
    (shouldShowDisconnect
      ? false
      : activeMode === "api_key"
        ? !canConnectApiKey
        : activeMode === "local"
          ? false
          : loginPending || !provider.commandPresent);
  const handleActionClick = () => {
    if (shouldShowDisconnect) {
      void disconnectProviderConnection(provider.id);
      return;
    }
    if (activeMode === "api_key") {
      void connectProviderApiKey(provider.id);
      return;
    }
    if (activeMode === "local") {
      void connectProviderLocal(provider.id);
      return;
    }
    void startProviderLogin(provider.id);
  };

  useEffect(() => {
    if (provider.id !== "kokoro" || !isOpen) {
      return;
    }
    void loadKokoroVoices(kokoroLanguage);
    void loadKokoroModelStatus();
  }, [isOpen, kokoroLanguage, loadKokoroVoices, loadKokoroModelStatus, provider.id]);

  useEffect(() => {
    if (provider.id !== "supertonic" || !isOpen) {
      return;
    }
    void loadSupertonicModels();
    void loadSupertonicVoices(supertonicModel, supertonicLanguage);
  }, [isOpen, loadSupertonicModels, loadSupertonicVoices, provider.id, supertonicLanguage, supertonicModel]);

  useEffect(() => {
    if (provider.id !== "whispercpp" || !isOpen) {
      return;
    }
    void loadWhisperCatalog();
  }, [isOpen, loadWhisperCatalog, provider.id]);

  useEffect(() => {
    if (provider.id !== "elevenlabs" || !isOpen || activeMode !== "api_key") {
      return;
    }
    if (!(connection?.api_key_present || connection?.configured || connection?.verified)) {
      return;
    }
    void loadElevenLabsVoices(elevenlabsLanguage);
  }, [
    activeMode,
    connection?.api_key_present,
    connection?.configured,
    connection?.verified,
    elevenlabsLanguage,
    isOpen,
    loadElevenLabsVoices,
    provider.id,
  ]);

  useEffect(() => {
    if (provider.id !== "ollama" || !isOpen) {
      return;
    }
    if (!(connection?.configured || connection?.verified || connection?.api_key_present)) {
      return;
    }
    void loadOllamaModels();
  }, [
    connection?.api_key_present,
    connection?.configured,
    connection?.verified,
    isOpen,
    loadOllamaModels,
    provider.id,
  ]);

  return {
    draft,
    setField,
    setProviderConnectionDraft,
    connection,
    connectionDraft,
    activeMode,
    supportsAnyAuth,
    supportsApiKey,
    supportsLocalConnection,
    supportsSubscriptionLogin,
    hasActiveConnection,
    loginSession,
    elevenlabsLanguage,
    elevenlabsDefaultVoice,
    elevenlabsDefaultVoiceLabel,
    elevenlabsVoiceCatalog,
    elevenlabsVoicesLoading,
    loadElevenLabsVoices,
    kokoroLanguage,
    kokoroDefaultVoice,
    kokoroDefaultVoiceLabel,
    kokoroVoiceCatalog,
    kokoroVoicesLoading,
    kokoroDownloadActive,
    kokoroModelDownloading,
    kokoroModelStatus,
    kokoroSelectedVoice,
    loadKokoroVoices,
    downloadKokoroVoice,
    downloadKokoroModel,
    deleteKokoroModelAsset,
    deleteKokoroVoiceAsset,
    supertonicModel,
    supertonicLanguage,
    supertonicDefaultVoice,
    supertonicVoiceCatalog,
    supertonicVoicesLoading,
    supertonicModelCatalog,
    supertonicModelsLoading,
    supertonicVoiceDownloading,
    supertonicModelDownloading,
    supertonicSelectedModel,
    supertonicSelectedVoice,
    loadSupertonicVoices,
    downloadSupertonicModel,
    downloadSupertonicVoice,
    importSupertonicVoice,
    deleteSupertonicModelAsset,
    deleteSupertonicVoiceAsset,
    deleteWhisperVariantAsset,
    whisperCatalog,
    isDownloadingWhisperVariant,
    downloadWhisperModel,
    loadWhisperCatalog,
    ollamaModelCatalog,
    ollamaModelsLoading,
    shouldShowDisconnect,
    actionLabel,
    actionIcon,
    actionVariant,
    actionLoading,
    actionStatus,
    actionLoadingLabel,
    actionDisabled,
    handleActionClick,
    submitProviderLoginCode,
    replacingApiKey,
    markReplacingKey,
    unmarkReplacingKey,
  };
}

type ProviderConnectionUi = ReturnType<typeof useProviderConnectionUi>;

function ClaudeCodeEntry({
  sessionId,
  onSubmit,
  tl,
}: {
  sessionId: string;
  onSubmit: (code: string) => Promise<ProviderLoginSession>;
  tl: (value: string, options?: Record<string, string | number>) => string;
}) {
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState("");

  const handleSubmit = async () => {
    const nextCode = code.trim();
    if (!nextCode) return;
    setSubmitting(true);
    setStatus("idle");
    setFeedback("");
    try {
      const result = await onSubmit(nextCode);
      if (result.status === "completed") {
        setCode("");
        setStatus("success");
        setFeedback(tl("Código confirmado. Validando a conexão com a Anthropic..."));
      } else if (result.status === "error" || result.last_error) {
        // Claude CLI reports invalid codes via ``last_error`` while keeping the
        // session in ``awaiting_browser`` so the operator can retry in the same
        // PTY. Surface that as a red error state so the rejection is obvious.
        setStatus("error");
        setFeedback(result.last_error || tl("Não foi possível validar o código enviado."));
      } else {
        setStatus("idle");
        setFeedback(
          result.message || tl("Código enviado. Aguardando a confirmação final do Claude Code."),
        );
      }
    } catch {
      setStatus("error");
      setFeedback(tl("Não foi possível enviar o código agora. Tente novamente."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div key={sessionId} className="space-y-2.5 px-1">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
        {tl("Authentication Code")}
      </div>
      <div className="flex items-center gap-2.5">
        <input
          className="field-shell min-w-0 flex-1 font-mono tracking-[0.08em] text-[var(--text-primary)]"
          type="text"
          inputMode="text"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          placeholder={tl("Cole o código de autenticação")}
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
            if (status !== "idle") setStatus("idle");
          }}
        />
        <AsyncActionButton
          type="button"
          variant="secondary"
          size="sm"
          loading={submitting}
          status={status}
          loadingLabel={tl("Enviando")}
          icon={Link2}
          disabled={!code.trim()}
          onClick={() => {
            void handleSubmit();
          }}
          className="shrink-0 rounded-full px-3.5"
        >
          {tl("Enviar código")}
        </AsyncActionButton>
      </div>
      {feedback ? (
        <div
          className={cn(
            "text-xs leading-5",
            status === "error" ? "text-rose-300" : "text-[var(--text-secondary)]",
          )}
        >
          {feedback}
        </div>
      ) : null}
    </div>
  );
}

function WhisperCppModelList({
  whisperCatalog,
  isDownloadingWhisperVariant,
  downloadWhisperModel,
  deleteWhisperVariantAsset,
}: {
  whisperCatalog: ProviderConnectionUi["whisperCatalog"];
  isDownloadingWhisperVariant: ProviderConnectionUi["isDownloadingWhisperVariant"];
  downloadWhisperModel: ProviderConnectionUi["downloadWhisperModel"];
  deleteWhisperVariantAsset: ProviderConnectionUi["deleteWhisperVariantAsset"];
}) {
  const { tl } = useAppI18n();

  if (!whisperCatalog) {
    return (
      <div className="px-1 text-sm text-[var(--text-tertiary)]">
        {tl("Carregando modelos Whisper.cpp...")}
      </div>
    );
  }

  return (
    <div className="space-y-3 px-1">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
          {tl("Modelos Whisper.cpp")}
        </div>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {tl("Modelos locais para transcrição offline. Baixe apenas os que deseja usar.")}
        </p>
      </div>

      <div className="space-y-2">
        {whisperCatalog.items.map((variant) => {
          const downloading = isDownloadingWhisperVariant(variant.variant_id);
          const isDefault = whisperCatalog.default_variant === variant.variant_id;
          return (
            <div
              key={variant.variant_id}
              className="flex flex-wrap items-center gap-3 text-sm"
            >
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="font-medium text-[var(--text-primary)]">
                  {variant.label}
                  {isDefault ? (
                    <span className="ml-2 rounded-full border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">
                      {tl("Padrão")}
                    </span>
                  ) : null}
                </span>
                <span className="text-xs text-[var(--text-tertiary)]">
                  {variant.description}
                  {variant.downloaded && Number(variant.bytes ?? 0) > 0
                    ? ` · ${formatAssetBytes(variant.bytes)}`
                    : variant.approx_size_bytes
                      ? ` · ~${formatAssetBytes(variant.approx_size_bytes)}`
                      : ""}
                </span>
              </div>
              {variant.downloaded ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                  <Check className="h-3 w-3" strokeWidth={1.75} />
                  {tl("Baixado")}
                </span>
              ) : null}
              <AsyncActionButton
                type="button"
                variant={variant.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={downloading}
                loadingLabel={tl("Baixando")}
                icon={ArrowDown}
                disabled={Boolean(variant.downloaded) || downloading}
                onClick={() => {
                  void downloadWhisperModel(variant.variant_id);
                }}
                className="rounded-full px-3.5"
              >
                {variant.downloaded ? tl("Disponível") : tl("Baixar")}
              </AsyncActionButton>
              {variant.downloaded ? (
                <AsyncActionButton
                  type="button"
                  variant="danger"
                  size="sm"
                  icon={Trash2}
                  disabled={downloading}
                  onClick={() => {
                    void deleteWhisperVariantAsset(variant.variant_id);
                  }}
                  loadingLabel={tl("Removendo")}
                  className="rounded-full px-3.5"
                >
                  {tl("Remover")}
                </AsyncActionButton>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

async function copyProviderLoginCode(value: string) {
  if (!value) return false;
  try {
    await navigator.clipboard?.writeText(value);
    return true;
  } catch {
    return false;
  }
}

export function ProviderAuthPanel({
  provider,
  ui,
  className,
}: {
  provider: ProviderOption;
  ui: ProviderConnectionUi;
  className?: string;
}) {
  const { tl } = useAppI18n();
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const {
    draft,
    setField,
    setProviderConnectionDraft,
    connection,
    connectionDraft,
    activeMode,
    supportsAnyAuth,
    supportsApiKey,
    supportsLocalConnection,
    supportsSubscriptionLogin,
    loginSession,
    elevenlabsLanguage,
    elevenlabsDefaultVoice,
    elevenlabsDefaultVoiceLabel,
    elevenlabsVoiceCatalog,
    elevenlabsVoicesLoading,
    loadElevenLabsVoices,
    kokoroLanguage,
    kokoroDefaultVoice,
    kokoroDefaultVoiceLabel,
    kokoroVoiceCatalog,
    kokoroVoicesLoading,
    kokoroDownloadActive,
    kokoroModelDownloading,
    kokoroModelStatus,
    kokoroSelectedVoice,
    loadKokoroVoices,
    downloadKokoroVoice,
    downloadKokoroModel,
    deleteKokoroModelAsset,
    deleteKokoroVoiceAsset,
    supertonicModel,
    supertonicLanguage,
    supertonicDefaultVoice,
    supertonicVoiceCatalog,
    supertonicVoicesLoading,
    supertonicModelCatalog,
    supertonicModelsLoading,
    supertonicVoiceDownloading,
    supertonicModelDownloading,
    supertonicSelectedModel,
    supertonicSelectedVoice,
    loadSupertonicVoices,
    downloadSupertonicModel,
    downloadSupertonicVoice,
    importSupertonicVoice,
    deleteSupertonicModelAsset,
    deleteSupertonicVoiceAsset,
    deleteWhisperVariantAsset,
    whisperCatalog,
    isDownloadingWhisperVariant,
    downloadWhisperModel,
    ollamaModelCatalog,
    ollamaModelsLoading,
    submitProviderLoginCode,
    replacingApiKey,
    markReplacingKey,
    unmarkReplacingKey,
  } = ui;
  const loginCode = loginSession?.user_code?.trim() || "";
  const codeCopied = Boolean(loginCode) && copiedCode === loginCode;
  const supertonicImportInputRef = useRef<HTMLInputElement | null>(null);
  const supertonicAccelerationLabel =
    supertonicVoiceCatalog.acceleration?.label || supertonicModelCatalog?.acceleration?.label || "CPU ONNX oficial";
  const kokoroLanguageOptions =
    kokoroVoiceCatalog.available_languages.length > 0
      ? kokoroVoiceCatalog.available_languages
      : [{ id: kokoroLanguage || "pt-br", label: kokoroLanguage || "pt-br" }];
  const kokoroHasSelectedVoice = kokoroVoiceCatalog.items.some(
    (voice) => voice.voice_id === kokoroDefaultVoice,
  );
  const supertonicModelOptions = supertonicModelCatalog?.items || [];
  const supertonicHasSelectedModel = supertonicModelOptions.some(
    (model) => model.model_id === supertonicModel,
  );
  const supertonicLanguageOptions =
    supertonicVoiceCatalog.available_languages.length > 0
      ? supertonicVoiceCatalog.available_languages
      : [{ id: supertonicLanguage || "pt", label: supertonicLanguage || "pt" }];
  const supertonicHasSelectedVoice = supertonicVoiceCatalog.items.some(
    (voice) => voice.voice_id === supertonicDefaultVoice,
  );
  const shouldShowClaudeCodeInput =
    provider.id === "claude" &&
    Boolean(loginSession?.session_id) &&
    Boolean(loginSession?.auth_url) &&
    ["pending", "awaiting_browser"].includes(String(loginSession?.status || ""));

  useEffect(() => {
    if (!copiedCode) return;
    const timeoutId = window.setTimeout(() => setCopiedCode(null), 1800);
    return () => window.clearTimeout(timeoutId);
  }, [copiedCode]);

  const handleCopyLoginCode = async () => {
    if (!loginCode) return;
    const copied = await copyProviderLoginCode(loginCode);
    if (copied) {
      setCopiedCode(loginCode);
    }
  };

  return (
    <div className={cn("space-y-3", className)}>
      {supportsSubscriptionLogin && !provider.commandPresent ? (
        <InlineAlert tone="warning">
          {tl(
            "O runtime oficial deste provider não está disponível neste ambiente. Instale o CLI correspondente antes de concluir a conexão.",
          )}
        </InlineAlert>
      ) : null}

      {provider.id === "whispercpp" ? (
        <WhisperCppModelList
          whisperCatalog={whisperCatalog}
          isDownloadingWhisperVariant={isDownloadingWhisperVariant}
          downloadWhisperModel={downloadWhisperModel}
          deleteWhisperVariantAsset={deleteWhisperVariantAsset}
        />
      ) : provider.id === "kokoro" ? (
        <>
          {/* Modelo base: precisa estar baixado antes que qualquer voz funcione.
              O download é independente do download de vozes. Mostra tamanho
              em disco quando presente e oferece botão de remoção. */}
          <div className="flex flex-wrap items-center gap-3 px-1 pb-2 text-sm">
            <span className="text-[var(--text-secondary)]">
              {tl("Modelo base do Kokoro")}
            </span>
            {kokoroModelStatus?.downloaded ? (
              <>
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                  <Check className="h-3 w-3" strokeWidth={1.75} />
                  {tl("Disponível")}
                </span>
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                  {formatAssetBytes(kokoroModelStatus.bytes)}
                </span>
              </>
            ) : (
              <span className="text-xs text-[var(--text-tertiary)]">
                {tl("Necessário antes de baixar qualquer voz.")}
              </span>
            )}
            <div className="ml-auto flex items-center gap-2">
              <AsyncActionButton
                type="button"
                variant={kokoroModelStatus?.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={kokoroModelDownloading}
                loadingLabel={tl("Baixando")}
                icon={ArrowDown}
                disabled={Boolean(kokoroModelStatus?.downloaded) || kokoroModelDownloading}
                onClick={() => {
                  void downloadKokoroModel();
                }}
                className="rounded-full px-3.5"
              >
                {kokoroModelStatus?.downloaded
                  ? tl("Modelo baixado")
                  : tl("Baixar modelo Kokoro")}
              </AsyncActionButton>
              {kokoroModelStatus?.downloaded ? (
                <AsyncActionButton
                  type="button"
                  variant="danger"
                  size="sm"
                  icon={Trash2}
                  disabled={kokoroModelDownloading}
                  onClick={() => {
                    void deleteKokoroModelAsset();
                  }}
                  className="rounded-full px-3.5"
                  loadingLabel={tl("Removendo")}
                >
                  {tl("Remover")}
                </AsyncActionButton>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <FieldShell
              label={tl("Idioma")}
              description={tl("Define o idioma padrão e filtra a lista de vozes.")}
            >
              <Select
                value={kokoroLanguage}
                onValueChange={(nextLanguage) => {
                  setField("models", {
                    ...draft.values.models,
                    kokoro_default_language: nextLanguage,
                  });
                  void loadKokoroVoices(nextLanguage, { force: true });
                }}
              >
                <SelectTrigger aria-busy={kokoroVoicesLoading || undefined}>
                  <SelectValue />
                  <SelectLoadingSpinner loading={kokoroVoicesLoading} />
                </SelectTrigger>
                <SelectContent>
                  {kokoroLanguageOptions.map((language) => (
                    <SelectItem key={language.id} value={language.id}>
                      {tl(language.label)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>

          <FieldShell
            label="Voz"
            description={
              kokoroVoicesLoading
                ? "Carregando vozes oficiais..."
                : "Escolha a voz padrão local usada pelos agents."
            }
          >
            <Select
              value={kokoroDefaultVoice || "pf_dora"}
              disabled={kokoroVoicesLoading}
              onValueChange={(value) => {
                const nextVoiceId = value === SELECT_ALL_VALUE ? "" : value;
                const selectedVoice = kokoroVoiceCatalog.items.find(
                  (voice) => voice.voice_id === nextVoiceId,
                );
                setField("models", {
                  ...draft.values.models,
                  kokoro_default_voice: nextVoiceId,
                  kokoro_default_voice_label: selectedVoice?.name || "",
                });
              }}
            >
              <SelectTrigger aria-busy={kokoroVoicesLoading || undefined}>
                <SelectValue
                  placeholder={
                    kokoroVoicesLoading ? "Carregando vozes..." : "Selecione a voz padrão"
                  }
                />
                <SelectLoadingSpinner loading={kokoroVoicesLoading} />
              </SelectTrigger>
              <SelectContent>
                {kokoroDefaultVoice && !kokoroHasSelectedVoice ? (
                  <SelectItem value={kokoroDefaultVoice}>
                    {kokoroDefaultVoiceLabel || kokoroDefaultVoice}
                  </SelectItem>
                ) : null}
                {kokoroVoiceCatalog.items.map((voice) => (
                  <SelectItem key={voice.voice_id} value={voice.voice_id}>
                    {`${voice.name} — ${tl(voice.language_label)}${voice.downloaded ? ` · ${tl("baixada")}` : ""}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldShell>

          <div className="md:col-span-2 flex flex-wrap items-center gap-3 px-1">
            <AsyncActionButton
              type="button"
              variant={kokoroSelectedVoice?.downloaded ? "secondary" : "quiet"}
              size="sm"
              loading={kokoroDownloadActive}
              loadingLabel={tl("Baixando")}
              status={kokoroDownloadActive ? "pending" : "idle"}
              icon={ArrowDown}
              disabled={!kokoroDefaultVoice || Boolean(kokoroSelectedVoice?.downloaded)}
              onClick={() => {
                if (!kokoroDefaultVoice) return;
                void downloadKokoroVoice(kokoroDefaultVoice);
              }}
              className="rounded-full px-3.5"
            >
              {kokoroSelectedVoice?.downloaded ? tl("Voz baixada") : tl("Baixar voz")}
            </AsyncActionButton>
            {kokoroSelectedVoice?.downloaded ? (
              <AsyncActionButton
                type="button"
                variant="danger"
                size="sm"
                icon={Trash2}
                disabled={!kokoroDefaultVoice || kokoroDownloadActive}
                onClick={() => {
                  if (!kokoroDefaultVoice) return;
                  void deleteKokoroVoiceAsset(kokoroDefaultVoice);
                }}
                loadingLabel={tl("Removendo")}
                className="rounded-full px-3.5"
              >
                {tl("Remover")}
              </AsyncActionButton>
            ) : null}
            <span className="text-sm text-[var(--text-secondary)]">
              {kokoroSelectedVoice
                ? `${tl(kokoroSelectedVoice.language_label)} · ${kokoroSelectedVoice.gender === "female" ? tl("Feminina") : tl("Masculina")}${
                    kokoroSelectedVoice.downloaded && Number(kokoroSelectedVoice.bytes ?? 0) > 0
                      ? ` · ${formatAssetBytes(kokoroSelectedVoice.bytes)}`
                      : ""
                  }`
                : tl("Selecione uma voz para baixar sob demanda.")}
            </span>
          </div>

          </div>
        </>
      ) : provider.id === "supertonic" ? (
        <>
          <div className="flex flex-wrap items-center gap-3 px-1 pb-2 text-sm">
            <span className="text-[var(--text-secondary)]">
              {tl("Modelo Supertonic")}
            </span>
            {supertonicSelectedModel?.downloaded ? (
              <>
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                  <Check className="h-3 w-3" strokeWidth={1.75} />
                  {tl("Disponível")}
                </span>
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                  {formatAssetBytes(supertonicSelectedModel.bytes)}
                </span>
              </>
            ) : (
              <span className="text-xs text-[var(--text-tertiary)]">
                {tl("Download inicial via Hugging Face.")}
              </span>
            )}
            <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-tertiary)]">
              {tl(supertonicAccelerationLabel)}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <AsyncActionButton
                type="button"
                variant={supertonicSelectedModel?.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={supertonicModelDownloading}
                loadingLabel={tl("Baixando")}
                icon={ArrowDown}
                disabled={Boolean(supertonicSelectedModel?.downloaded) || supertonicModelDownloading}
                onClick={() => {
                  void downloadSupertonicModel(supertonicModel);
                }}
                className="rounded-full px-3.5"
              >
                {supertonicSelectedModel?.downloaded ? tl("Modelo baixado") : tl("Baixar modelo")}
              </AsyncActionButton>
              {supertonicSelectedModel?.downloaded ? (
                <AsyncActionButton
                  type="button"
                  variant="danger"
                  size="sm"
                  icon={Trash2}
                  disabled={supertonicModelDownloading}
                  onClick={() => {
                    void deleteSupertonicModelAsset(supertonicModel);
                  }}
                  className="rounded-full px-3.5"
                  loadingLabel={tl("Removendo")}
                >
                  {tl("Remover")}
                </AsyncActionButton>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <FieldShell label={tl("Modelo")} description={tl("Seleciona o snapshot local usado na síntese.")}>
              <Select
                value={supertonicModel}
                disabled={supertonicModelsLoading}
                onValueChange={(nextModel) => {
                  setField("models", {
                    ...draft.values.models,
                    supertonic_default_model: nextModel,
                    supertonic_default_voice: "F1",
                  });
                  void loadSupertonicVoices(nextModel, supertonicLanguage, { force: true });
                }}
              >
                <SelectTrigger aria-busy={supertonicModelsLoading || undefined}>
                  <SelectValue />
                  <SelectLoadingSpinner loading={supertonicModelsLoading} />
                </SelectTrigger>
                <SelectContent>
                  {!supertonicHasSelectedModel ? (
                    <SelectItem value={supertonicModel}>{supertonicModel}</SelectItem>
                  ) : null}
                  {supertonicModelOptions.map((model) => (
                    <SelectItem key={model.model_id} value={model.model_id}>
                      {`${model.title}${model.downloaded ? ` · ${tl("baixado")}` : ""}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>

            <FieldShell label={tl("Idioma")} description={tl("Define o idioma padrão para a fala local.")}>
              <Select
                value={supertonicLanguage}
                onValueChange={(nextLanguage) => {
                  setField("models", {
                    ...draft.values.models,
                    supertonic_default_language: nextLanguage,
                  });
                  void loadSupertonicVoices(supertonicModel, nextLanguage, { force: true });
                }}
              >
                <SelectTrigger aria-busy={supertonicVoicesLoading || undefined}>
                  <SelectValue />
                  <SelectLoadingSpinner loading={supertonicVoicesLoading} />
                </SelectTrigger>
                <SelectContent>
                  {supertonicLanguageOptions.map((language) => (
                    <SelectItem key={language.id} value={language.id}>
                      {tl(language.label)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>

            <FieldShell
              label="Voz"
              description={
                supertonicVoicesLoading
                  ? "Carregando vozes Supertonic..."
                  : "Escolha presets oficiais ou vozes importadas do Voice Builder."
              }
            >
              <Select
                value={supertonicDefaultVoice || "F1"}
                disabled={supertonicVoicesLoading}
                onValueChange={(nextVoiceId) => {
                  const selectedVoice = supertonicVoiceCatalog.items.find(
                    (voice) => voice.voice_id === nextVoiceId,
                  );
                  setField("models", {
                    ...draft.values.models,
                    supertonic_default_voice: nextVoiceId,
                    supertonic_default_voice_label: selectedVoice?.name || nextVoiceId,
                  });
                }}
              >
                <SelectTrigger aria-busy={supertonicVoicesLoading || undefined}>
                  <SelectValue placeholder={tl("Selecione a voz padrão")} />
                  <SelectLoadingSpinner loading={supertonicVoicesLoading} />
                </SelectTrigger>
                <SelectContent>
                  {supertonicDefaultVoice && !supertonicHasSelectedVoice ? (
                    <SelectItem value={supertonicDefaultVoice}>{supertonicDefaultVoice}</SelectItem>
                  ) : null}
                  {supertonicVoiceCatalog.items.map((voice) => (
                    <SelectItem key={voice.voice_id} value={voice.voice_id}>
                      {`${voice.name} · ${voice.kind === "custom" ? tl("custom") : tl("preset")}${
                        voice.downloaded ? ` · ${tl("baixada")}` : ""
                      }`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>

            <FieldShell label={tl("Voz custom")} description={tl("Importa JSON local do Voice Builder.")}>
              <input
                ref={supertonicImportInputRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.currentTarget.value = "";
                  if (!file) return;
                  void importSupertonicVoice(file, { modelId: supertonicModel });
                }}
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => supertonicImportInputRef.current?.click()}
                className="gap-2 rounded-full px-3.5"
              >
                <Upload className="h-3.5 w-3.5" strokeWidth={1.75} />
                {tl("Importar JSON")}
              </Button>
            </FieldShell>

            <div className="md:col-span-2 flex flex-wrap items-center gap-3 px-1">
              <AsyncActionButton
                type="button"
                variant={supertonicSelectedVoice?.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={supertonicVoiceDownloading}
                loadingLabel={tl("Baixando")}
                status={supertonicVoiceDownloading ? "pending" : "idle"}
                icon={ArrowDown}
                disabled={!supertonicDefaultVoice || Boolean(supertonicSelectedVoice?.downloaded)}
                onClick={() => {
                  if (!supertonicDefaultVoice) return;
                  void downloadSupertonicVoice(supertonicDefaultVoice, supertonicModel);
                }}
                className="rounded-full px-3.5"
              >
                {supertonicSelectedVoice?.downloaded ? tl("Voz baixada") : tl("Baixar voz")}
              </AsyncActionButton>
              {supertonicSelectedVoice?.downloaded ? (
                <AsyncActionButton
                  type="button"
                  variant="danger"
                  size="sm"
                  icon={Trash2}
                  disabled={!supertonicDefaultVoice || supertonicVoiceDownloading}
                  onClick={() => {
                    if (!supertonicDefaultVoice) return;
                    void deleteSupertonicVoiceAsset(supertonicDefaultVoice, supertonicModel);
                  }}
                  loadingLabel={tl("Removendo")}
                  className="rounded-full px-3.5"
                >
                  {tl("Remover")}
                </AsyncActionButton>
              ) : null}
              <span className="text-sm text-[var(--text-secondary)]">
                {supertonicSelectedVoice
                  ? `${tl(supertonicSelectedVoice.language_label)} · ${
                      supertonicSelectedVoice.gender === "female"
                        ? tl("Feminina")
                        : supertonicSelectedVoice.gender === "male"
                          ? tl("Masculina")
                          : tl("Custom")
                    }${
                      supertonicSelectedVoice.downloaded && Number(supertonicSelectedVoice.bytes ?? 0) > 0
                        ? ` · ${formatAssetBytes(supertonicSelectedVoice.bytes)}`
                        : ""
                    }`
                  : tl("Selecione uma voz para ativar localmente.")}
              </span>
            </div>
          </div>
        </>
      ) : supportsAnyAuth ? (
        <>
          <div className="space-y-2 px-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              {tl("Autenticação")}
            </div>
            <div
              className="flex items-center gap-5 border-b border-[var(--border-subtle)]"
              role="tablist"
              aria-label={tl("Formas de autenticação de {{provider}}", { provider: provider.title })}
            >
              {supportsApiKey ? (
                <button
                  type="button"
                  onClick={() => setProviderConnectionDraft(provider.id, { auth_mode: "api_key" })}
                  role="tab"
                  aria-selected={activeMode === "api_key"}
                  className={cn(
                    "relative -mb-px border-b-2 px-0 pb-2.5 text-sm transition-colors",
                    activeMode === "api_key"
                      ? "border-[var(--text-primary)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  API Key
                </button>
              ) : null}
              {supportsLocalConnection ? (
                <button
                  type="button"
                  onClick={() => setProviderConnectionDraft(provider.id, { auth_mode: "local" })}
                  role="tab"
                  aria-selected={activeMode === "local"}
                  className={cn(
                    "relative -mb-px border-b-2 px-0 pb-2.5 text-sm transition-colors",
                    activeMode === "local"
                      ? "border-[var(--text-primary)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {provider.id === "claude" ? tl("Claude Code CLI") : tl("Servidor local")}
                </button>
              ) : null}
              {supportsSubscriptionLogin ? (
                <button
                  type="button"
                  onClick={() =>
                    setProviderConnectionDraft(provider.id, {
                      auth_mode: "subscription_login",
                    })
                  }
                  role="tab"
                  aria-selected={activeMode === "subscription_login"}
                  className={cn(
                    "relative -mb-px border-b-2 px-0 pb-2.5 text-sm transition-colors",
                    activeMode === "subscription_login"
                      ? "border-[var(--text-primary)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {tl("Assinatura / login")}
                </button>
              ) : null}
            </div>
          </div>

          {activeMode === "api_key" ? (
            <div className="grid gap-3 xl:grid-cols-2">
              <div className="space-y-2 px-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    {tl("Chave da API")}
                  </div>
                  {connection?.api_key_present ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                      <CheckCircle2 className="h-3 w-3" strokeWidth={1.75} />
                      {tl("Configurada")}
                    </span>
                  ) : null}
                </div>
                {connection?.api_key_present &&
                !connectionDraft?.api_key &&
                !replacingApiKey ? (
                  <div className="space-y-2">
                    <p className="text-xs text-[var(--text-tertiary)]">
                      {tl(
                        "A chave está armazenada e criptografada. Para trocar, clique em Substituir; o valor atual nunca é exibido.",
                      )}
                    </p>
                    <button
                      type="button"
                      onClick={markReplacingKey}
                      className="inline-flex items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-transparent px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                    >
                      <RefreshCcw className="h-3 w-3" strokeWidth={1.75} />
                      {tl("Substituir chave")}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <SecretInput
                      placeholder={
                        provider.id === "gemini"
                          ? "AIza..."
                          : tl("Cole a chave da API")
                      }
                      value={connectionDraft?.api_key || ""}
                      onChange={(event) =>
                        setProviderConnectionDraft(provider.id, { api_key: event.target.value })
                      }
                    />
                    {connection?.api_key_present && replacingApiKey ? (
                      <button
                        type="button"
                        onClick={() => {
                          unmarkReplacingKey();
                          setProviderConnectionDraft(provider.id, { api_key: "" });
                        }}
                        className="text-[11px] text-[var(--text-tertiary)] underline-offset-2 transition-colors hover:text-[var(--text-primary)] hover:underline"
                      >
                        {tl("Cancelar substituição")}
                      </button>
                    ) : null}
                  </div>
                )}
              </div>

              {provider.id === "elevenlabs" ? (
                <div className="grid gap-3 md:grid-cols-2">
                  <FieldShell
                    label={tl("Idioma padrão")}
                    description={tl("Filtra a biblioteca de vozes e define o idioma padrão dos agentes.")}
                  >
                    <Select
                      value={elevenlabsLanguage === "" ? SELECT_ALL_VALUE : elevenlabsLanguage}
                      onValueChange={(value) => {
                        const nextLanguage = value === SELECT_ALL_VALUE ? "" : value;
                        setField("models", {
                          ...draft.values.models,
                          elevenlabs_default_language: nextLanguage,
                          elevenlabs_default_voice: "",
                          elevenlabs_default_voice_label: "",
                        });
                        void loadElevenLabsVoices(nextLanguage, { force: true });
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={SELECT_ALL_VALUE}>{tl("Todos os idiomas")}</SelectItem>
                        {elevenlabsVoiceCatalog.available_languages.map((language) => (
                          <SelectItem key={language.code} value={language.code}>
                            {language.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FieldShell>

                  <FieldShell
                    label={tl("Voz padrão")}
                    description={
                      elevenlabsVoicesLoading
                        ? tl("Carregando vozes disponíveis…")
                        : tl("Usada como voz default dos agentes quando TTS estiver ativo.")
                    }
                  >
                    <Select
                      value={elevenlabsDefaultVoice === "" ? SELECT_ALL_VALUE : elevenlabsDefaultVoice}
                      disabled={
                        elevenlabsVoicesLoading ||
                        !(connection?.verified || connection?.configured || connection?.api_key_present)
                      }
                      onValueChange={(value) => {
                        const nextVoiceId = value === SELECT_ALL_VALUE ? "" : value;
                        const selectedVoice = elevenlabsVoiceCatalog.items.find(
                          (voice) => voice.voice_id === nextVoiceId,
                        );
                        setField("models", {
                          ...draft.values.models,
                          elevenlabs_default_voice: nextVoiceId,
                          elevenlabs_default_voice_label: selectedVoice?.name || "",
                        });
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={SELECT_ALL_VALUE}>
                          {elevenlabsVoicesLoading
                            ? tl("Carregando vozes...")
                            : tl("Selecione a voz padrão")}
                        </SelectItem>
                        {elevenlabsDefaultVoice &&
                        !elevenlabsVoiceCatalog.items.some((voice) => voice.voice_id === elevenlabsDefaultVoice) ? (
                          <SelectItem value={elevenlabsDefaultVoice}>
                            {elevenlabsDefaultVoiceLabel || elevenlabsDefaultVoice}
                          </SelectItem>
                        ) : null}
                        {elevenlabsVoiceCatalog.items.map((voice) => (
                          <SelectItem
                            key={voice.voice_id}
                            value={voice.voice_id}
                            disabled={voice.api_available === false}
                          >
                            {elevenlabsVoiceOptionLabel(voice)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FieldShell>
                </div>
              ) : null}
            </div>
          ) : activeMode === "local" ? (
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,240px)]">
              <div className="space-y-2 px-1">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  {tl(providerLocalTitle(provider.id))}
                </div>
                <div className="text-sm leading-6 text-[var(--text-secondary)]">
                  {tl(providerLocalDescription(provider.id))}
                </div>
              </div>
              {provider.id === "ollama" ? (
                <div className="space-y-2 px-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    Base URL
                  </div>
                  <input
                    className="field-shell text-[var(--text-primary)]"
                    type="text"
                    placeholder="http://host.docker.internal:11434"
                    value={connectionDraft?.base_url || ""}
                    onChange={(event) =>
                      setProviderConnectionDraft(provider.id, { base_url: event.target.value })
                    }
                  />
                  <p className="text-[11px] leading-5 text-[var(--text-tertiary)]">
                    {tl(
                      "Ollama no desktop (host): http://host.docker.internal:11434. Em outro container da mesma rede: http://<serviço>:11434. Executando o Koda fora do Docker: http://localhost:11434.",
                    )}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2 px-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {tl("Login oficial")}
              </div>
              <div className="text-sm leading-6 text-[var(--text-secondary)]">
                {tl(providerLoginCopy(provider.id))}
              </div>
            </div>
          )}

          {provider.id === "ollama" ? (
            <div className="space-y-2 px-1">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  {tl("Modelos detectados")}
                </div>
                <div
                  className="inline-flex min-h-4 min-w-16 items-center justify-end text-xs text-[var(--text-quaternary)]"
                  role={ollamaModelsLoading ? "status" : undefined}
                  aria-label={ollamaModelsLoading ? tl("Carregando...") : undefined}
                >
                  {ollamaModelsLoading ? (
                    <InlineSpinner className="h-3.5 w-3.5" />
                  ) : ollamaModelCatalog.items.length ? (
                    tl("{{count}} modelos", { count: ollamaModelCatalog.items.length })
                  ) : (
                    tl("Nenhum modelo")
                  )}
                </div>
              </div>
              {ollamaModelCatalog.items.length ? (
                <div className="max-h-48 overflow-y-auto rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)]">
                  <div className="divide-y divide-[var(--divider-hair)]">
                    {ollamaModelCatalog.items.map((item) => {
                      const metadata = [
                        item.family,
                        item.parameter_size,
                        item.quantization_level,
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      return (
                        <div key={item.model_id} className="px-3 py-2.5">
                          <div className="text-sm font-medium text-[var(--text-primary)]">{item.name}</div>
                          {metadata ? (
                            <div className="mt-0.5 text-xs text-[var(--text-quaternary)]">{metadata}</div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-[var(--text-secondary)]">
                  {connection?.configured || connection?.verified || connection?.api_key_present
                    ? tl("Nenhum modelo foi retornado pelo endpoint configurado.")
                    : tl("Conecte o Ollama para carregar a lista real de modelos.")}
                </div>
              )}
            </div>
          ) : null}
        </>
      ) : (
        <div className="space-y-2 px-1">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
            {tl("Operação")}
          </div>
          <div className="text-sm leading-6 text-[var(--text-secondary)]">
            {provider.id === "ollama"
              ? tl("O Ollama depende apenas do runtime local configurado na máquina.")
              : tl("Este provider não exige autenticação manual nesta tela.")}
          </div>
        </div>
      )}

      {connection?.last_error && !loginSession ? (
        <div className="text-sm leading-6 text-rose-300">{connection.last_error}</div>
      ) : null}

      {loginSession ? (
        <div className="space-y-5 px-1 text-sm text-[var(--text-secondary)]">
          <span>
            {loginSession.status === "pending"
              ? loginSession.message || tl("Iniciando autenticação...")
              : loginSession.status === "awaiting_browser"
                ? loginSession.last_error ||
                  loginSession.message ||
                  tl("Abra o link abaixo, autorize no navegador e volte para esta página. A conexão será verificada automaticamente.")
                : loginSession.status === "completed"
                  ? loginSession.message || tl("Autenticação concluída. Verificando conexão...")
                  : loginSession.last_error ||
                    loginSession.message ||
                    tl("Conclua a autenticação no {{provider}}.", {
                      provider: tl(providerActionCopy(provider.id)),
                    })}
          </span>
          {loginSession.status === "awaiting_browser" || loginSession.status === "pending" ? (
            <div className="space-y-3">
              {loginSession.user_code ? (
                <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                        {tl("Código de autorização")}
                      </div>
                      <div className="mt-2 font-mono text-lg tracking-[0.28em] text-[var(--text-primary)] sm:text-[1.35rem]">
                        {loginSession.user_code}
                      </div>
                      <div className="mt-2 text-xs leading-5 text-[var(--text-quaternary)]">
                        {tl("Use este código na página de autorização aberta pelo login oficial.")}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        void handleCopyLoginCode();
                      }}
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] text-[var(--text-quaternary)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--panel-soft)] hover:text-[var(--text-secondary)]"
                      aria-label={codeCopied ? tl("Código copiado") : tl("Copiar código de autenticação")}
                      title={codeCopied ? tl("Código copiado") : tl("Copiar código de autenticação")}
                    >
                      {codeCopied ? (
                        <Check className="h-3.5 w-3.5" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                </div>
              ) : null}
              {shouldShowClaudeCodeInput ? (
                <div className="pt-4 sm:pt-5">
                  <ClaudeCodeEntry
                    key={loginSession.session_id}
                    sessionId={loginSession.session_id}
                    tl={tl}
                    onSubmit={(code) =>
                      submitProviderLoginCode(provider.id, loginSession.session_id, code)
                    }
                  />
                </div>
              ) : null}
              <div className="flex flex-wrap items-center gap-4">
                {loginSession.auth_url ? (
                  <a
                    href={loginSession.auth_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-emerald-300 transition-opacity hover:opacity-85"
                  >
                    {tl("Abrir página de autorização")}
                    <ExternalLink className="h-4 w-4" />
                  </a>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProviderAccordionItem
// ---------------------------------------------------------------------------

export function ProviderAccordionItem({
  provider,
  isOpen,
  onToggle,
}: {
  provider: ProviderOption;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const { tl } = useAppI18n();
  const ui = useProviderConnectionUi(provider, isOpen);

  return (
    <section
      className="overflow-hidden rounded-[var(--radius-shell)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] transition-colors"
    >
      <div
        className={cn(
          "group flex items-center gap-3 px-5 py-4 transition-colors",
          "hover:bg-[var(--hover-tint)]",
          isOpen ? "rounded-t-[var(--radius-shell)]" : "rounded-[var(--radius-shell)]",
        )}
      >
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-4 rounded-[var(--radius-panel)] text-left",
          )}
          aria-expanded={isOpen}
        >
          <ProviderLogo providerId={provider.id} title={provider.title} active={ui.hasActiveConnection} />
          <div className="min-w-0 flex-1">
            <div className="text-base font-semibold text-[var(--text-primary)]">{provider.title}</div>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {tl(providerDescription(provider.id, provider.category))}
            </p>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-2">
          {ui.supportsAnyAuth ? (
            <AsyncActionButton
              type="button"
              variant={ui.actionVariant}
              size="sm"
              loading={ui.actionLoading}
              status={ui.actionStatus}
              loadingLabel={tl(ui.actionLoadingLabel)}
              onClick={ui.handleActionClick}
              disabled={ui.actionDisabled}
              icon={ui.actionIcon}
              className="rounded-full px-3.5"
            >
              {tl(ui.actionLabel)}
            </AsyncActionButton>
          ) : null}
          <button
            type="button"
            onClick={onToggle}
            className={cn(
              "inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--panel)] text-[var(--text-quaternary)] transition-colors",
              "group-hover:bg-[var(--panel-soft)]",
            )}
            aria-label={
              isOpen
                ? tl("Recolher {{provider}}", { provider: provider.title })
                : tl("Expandir {{provider}}", { provider: provider.title })
            }
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 transition-transform duration-200 ease-out",
                isOpen && "rotate-180",
              )}
            />
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {isOpen ? (
          <motion.div
            key="provider-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <ProviderAuthPanel
              provider={provider}
              ui={ui}
              className="border-t border-[var(--border-subtle)] px-5 py-4"
            />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}

// ---------------------------------------------------------------------------
// SectionModels (main export)
// ---------------------------------------------------------------------------

export function SectionModels() {
  const { tl, t } = useAppI18n();
  const { draft, setField, providerOptions, enabledProviders, moveFallback, providerConnections, sectionErrors } =
    useSystemSettings();
  const modelsErrors = sectionErrors.models;

  const generalProviders = useMemo(
    () => providerOptions.filter((provider) => provider.category === "general"),
    [providerOptions],
  );

  const enabledGeneralProviders = enabledProviders.filter((providerId) =>
    generalProviders.some((provider) => provider.id === providerId),
  );
  const generalProviderIds = useMemo(
    () => generalProviders.map((provider) => provider.id),
    [generalProviders],
  );
  const modelFunctions = draft.catalogs.model_functions || [];
  const functionalCatalog = useMemo(
    () => draft.catalogs.functional_model_catalog || {},
    [draft.catalogs.functional_model_catalog],
  );
  const functionalProviderIds = useMemo(() => {
    const ids = new Set(generalProviderIds);
    for (const items of Object.values(functionalCatalog)) {
      for (const item of items || []) {
        const providerId = String(item.provider_id || "").trim();
        if (providerId) ids.add(providerId);
      }
    }
    return Array.from(ids);
  }, [functionalCatalog, generalProviderIds]);
  const providerOptionById = useMemo(
    () => new Map(providerOptions.map((provider) => [provider.id, provider])),
    [providerOptions],
  );

  const selectedGeneralEffortModel = useMemo(() => {
    const selected = draft.values.models.functional_defaults?.general;
    const generalOptions = functionalCatalog.general || [];
    const providerId =
      selected?.provider_id ||
      draft.values.models.default_provider ||
      enabledGeneralProviders[0] ||
      "";
    const providerDefaultModel = String(
      draft.catalogs.providers.find((provider) => provider.id === providerId)?.default_model || "",
    );
    const selectedModelId = selected?.model_id || providerDefaultModel;
    const item =
      generalOptions.find(
        (option) => option.provider_id === providerId && option.model_id === selectedModelId,
      ) ||
      generalOptions.find((option) => option.provider_id === providerId) ||
      generalOptions[0];
    if (!item?.provider_id || !item?.model_id || !item.effort_kind) return null;
    let capability: EffortCapability;
    if (item.effort_kind === "enum") {
      capability = {
        kind: "enum",
        values: Array.isArray(item.effort_enum_values) ? item.effort_enum_values.map(String) : [],
        defaultValue: typeof item.effort_default === "string" ? item.effort_default : undefined,
      };
    } else {
      capability = {
        kind: "tokens",
        min: Number(item.effort_token_min ?? 0),
        max: Number(item.effort_token_max ?? 0),
        defaultValue: typeof item.effort_default === "number" ? item.effort_default : undefined,
      };
    }
    return {
      providerId: item.provider_id,
      modelId: item.model_id,
      providerTitle: item.provider_title || item.provider_id,
      modelTitle: item.title,
      capability,
    };
  }, [
    draft.values.models.default_provider,
    draft.values.models.functional_defaults,
    draft.catalogs.providers,
    enabledGeneralProviders,
    functionalCatalog,
  ]);

  function updateEffortDefault(next: string | number | null) {
    const selected = selectedGeneralEffortModel;
    setField("models", {
      ...draft.values.models,
      effort_default:
        next === null || !selected
          ? null
          : {
              provider_id: selected.providerId,
              model_id: selected.modelId,
              value: next,
            },
    });
  }

  function updateFunctionalDefault(functionId: string, compositeValue: string) {
    const nextDefaults = { ...(draft.values.models.functional_defaults || {}) };
    if (!compositeValue) {
      delete nextDefaults[functionId];
    } else {
      const [providerId, ...modelParts] = compositeValue.split(":");
      const modelId = modelParts.join(":");
      const option = (functionalCatalog[functionId] || []).find(
        (item) => item.provider_id === providerId && item.model_id === modelId,
      );
      if (!option) {
        return;
      }
      nextDefaults[functionId] = {
        provider_id: providerId,
        model_id: modelId,
        provider_title: option.provider_title,
        model_label: option.title,
      };
    }

    const nextModels = {
      ...draft.values.models,
      functional_defaults: nextDefaults,
    };
    if (functionId === "general") {
      nextModels.effort_default = null;
    }
    const generalSelection = nextDefaults.general;
    if (generalSelection?.provider_id && enabledGeneralProviders.includes(generalSelection.provider_id)) {
      nextModels.default_provider = generalSelection.provider_id;
      nextModels.fallback_order = normalizeFallbackOrder(
        enabledGeneralProviders,
        draft.values.models.fallback_order,
        generalSelection.provider_id,
      );
    }
    setField("models", nextModels);
  }

  return (
    <SettingsSectionShell
      sectionId="models"
      title="settings.sections.models.label"
      description="settings.sections.models.description"
    >
      {/* ---- Routing ---- */}
      <SettingsFieldGroup title={tl("Routing")}>
        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={tl("Provider padrão")}
            description={tl("Primeira escolha global entre os providers já verificados.")}
            error={findFieldError(modelsErrors, "models.default_provider")?.message}
          >
            <Select
              value={
                draft.values.models.default_provider === ""
                  ? SELECT_ALL_VALUE
                  : draft.values.models.default_provider
              }
              onValueChange={(value) => {
                const next = value === SELECT_ALL_VALUE ? "" : value;
                setField("models", {
                  ...draft.values.models,
                  default_provider: next,
                  effort_default: null,
                  fallback_order: normalizeFallbackOrder(
                    enabledGeneralProviders,
                    draft.values.models.fallback_order,
                    next,
                  ),
                });
              }}
              disabled={enabledGeneralProviders.length === 0}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    enabledGeneralProviders.length === 0
                      ? tl("Nenhum provider verificado")
                      : undefined
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {enabledGeneralProviders.length === 0 ? (
                  <SelectItem value={SELECT_ALL_VALUE} disabled>
                    {tl("Nenhum provider verificado")}
                  </SelectItem>
                ) : null}
                {enabledGeneralProviders.map((id) => (
                  <SelectItem key={id} value={id}>
                    {providerLabel(id)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldShell>

          <FieldShell
            label={tl("Perfil de uso")}
            description={tl("Controla a preferência global entre custo e qualidade.")}
          >
            <Select
              value={draft.values.models.usage_profile}
              onValueChange={(value) =>
                setField("models", {
                  ...draft.values.models,
                  usage_profile: value,
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {draft.catalogs.usage_profiles.map((profile) => (
                  <SelectItem key={String(profile.id)} value={String(profile.id)}>
                    {tl(String(profile.label))}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldShell>
        </div>

        {enabledGeneralProviders.length > 1 ? (
          <FieldShell
            label={tl("Ordem de fallback")}
            description={tl("Só entram aqui providers já verificados e prontos para uso.")}
          >
            <div className="space-y-2">
              {draft.values.models.fallback_order
                .filter((id) => enabledGeneralProviders.includes(id))
                .map((providerId, index) => {
                  const connection = providerConnections[providerId];
                  return (
                    <div
                      key={providerId}
                      className="flex items-center gap-3 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-3"
                    >
                      <span className="w-5 shrink-0 text-center text-[11px] font-medium text-[var(--text-quaternary)]">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-[var(--text-primary)]">
                          {providerLabel(providerId)}
                        </div>
                        <div className="mt-0.5 text-xs text-[var(--text-quaternary)]">
                          {connection?.verified ? tl("Verificado") : tl("Ainda não verificado")}
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => moveFallback(providerId, "up")}
                          disabled={index === 0}
                          aria-label={tl("Subir")}
                          className="px-2"
                        >
                          <ArrowUp className="h-4 w-4" strokeWidth={1.75} />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => moveFallback(providerId, "down")}
                          disabled={index === enabledGeneralProviders.length - 1}
                          aria-label={tl("Descer")}
                          className="px-2"
                        >
                          <ArrowDown className="h-4 w-4" strokeWidth={1.75} />
                        </Button>
                      </div>
                    </div>
                  );
                })}
            </div>
          </FieldShell>
        ) : null}
      </SettingsFieldGroup>

      {/* ---- Budgets ---- */}
      <SettingsFieldGroup title={tl("Budgets")}>
        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={tl("Budget por tarefa")}
            description={tl("Limite global por execução individual.")}
            error={findFieldError(modelsErrors, "models.max_budget_usd")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={0}
              step={0.01}
              value={draft.values.models.max_budget_usd ?? ""}
              placeholder="2.50"
              onChange={(event) =>
                setField("models", {
                  ...draft.values.models,
                  max_budget_usd: event.target.value === "" ? null : Number(event.target.value),
                })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Budget acumulado")}
            description={tl("Teto global para o uso consolidado.")}
            error={findFieldError(modelsErrors, "models.max_total_budget_usd")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={0}
              step={0.01}
              value={draft.values.models.max_total_budget_usd ?? ""}
              placeholder="100.00"
              onChange={(event) =>
                setField("models", {
                  ...draft.values.models,
                  max_total_budget_usd: event.target.value === "" ? null : Number(event.target.value),
                })
              }
            />
          </FieldShell>
        </div>
      </SettingsFieldGroup>

      {/* ---- Functional Defaults ---- */}
      <SettingsFieldGroup title={tl("Functional Defaults")}>
        <div className="grid gap-4 xl:grid-cols-2">
          {modelFunctions.map((functionItem) => {
            const selected = draft.values.models.functional_defaults?.[functionItem.id];
            const selectedValue =
              selected?.provider_id && selected?.model_id
                ? `${selected.provider_id}:${selected.model_id}`
                : "";
            const error =
              findFieldError(
                modelsErrors,
                `models.functional_defaults.${functionItem.id}.provider_id`,
              )?.message ??
              findFieldError(
                modelsErrors,
                `models.functional_defaults.${functionItem.id}`,
              )?.message;

            return (
              <ModelSelector
                key={functionItem.id}
                label={tl(functionItem.title)}
                description={tl(functionItem.description)}
                error={error}
                value={selectedValue}
                onChange={(value) => updateFunctionalDefault(functionItem.id, value)}
                providers={{}}
                enabledProviders={functionalProviderIds}
                functionalCatalog={functionalCatalog}
                functionId={functionItem.id}
                emptyLabel={tl("Selecione um modelo padrão")}
                isOptionDisabled={({ providerId }) => {
                  const provider = providerOptionById.get(providerId);
                  return (
                    !provider ||
                    !isSelectableProvider(
                      provider,
                      providerConnections[provider.id],
                      functionItem.id,
                    )
                  );
                }}
                disabledOptionLabel={tl("indisponível no momento")}
              />
            );
          })}
        </div>
      </SettingsFieldGroup>

      {selectedGeneralEffortModel && (
        <SettingsFieldGroup title={t("modelEffort.sectionTitle")}>
          <p className="-mt-2 text-xs text-[var(--text-tertiary)] leading-relaxed">
            {t("modelEffort.sectionDescription")}
          </p>
          <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:gap-6">
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {selectedGeneralEffortModel.modelTitle}
              </span>
              <span className="text-xs text-[var(--text-tertiary)]">
                {selectedGeneralEffortModel.providerTitle}
              </span>
            </div>
            <div className="sm:w-[360px]">
              <EffortPicker
                capability={selectedGeneralEffortModel.capability}
                value={
                  draft.values.models.effort_default?.provider_id === selectedGeneralEffortModel.providerId &&
                  draft.values.models.effort_default?.model_id === selectedGeneralEffortModel.modelId
                    ? draft.values.models.effort_default.value
                    : selectedGeneralEffortModel.capability.defaultValue ?? null
                }
                onChange={updateEffortDefault}
                context="global"
                readOnly={
                  selectedGeneralEffortModel.capability.kind === "enum" &&
                  selectedGeneralEffortModel.capability.values.length <= 1
                }
              />
            </div>
          </div>
        </SettingsFieldGroup>
      )}

      {/* ---- Aceleração de hardware ---- */}
      <SettingsFieldGroup title={tl("Aceleração de hardware")}>
        <div className="flex items-center justify-between gap-4 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-strong)] text-[var(--text-primary)]"
              aria-hidden="true"
            >
              <AppleLogo size={18} />
            </span>
            <div className="flex min-w-0 flex-col">
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {tl("Aceleração Metal (Apple Silicon)")}
              </span>
              <span className="text-xs text-[var(--text-tertiary)]">
                {tl(
                  "Habilita o caminho Metal/MPS em runtimes locais (llama.cpp, MLX) quando o host é Apple Silicon. " +
                    "Em hosts Intel ou Linux a configuração não tem efeito.",
                )}
              </span>
            </div>
          </div>
          <AnimatedSwitch
            checked={Boolean(draft.values.models.metal_enabled)}
            onChange={() =>
              setField("models", {
                ...draft.values.models,
                metal_enabled: !draft.values.models.metal_enabled,
              })
            }
            ariaLabel={tl("Aceleração Metal")}
          />
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
