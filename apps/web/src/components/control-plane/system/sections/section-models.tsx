"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { translate } from "@/lib/i18n";
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
type ProviderCopyTranslator = (key: string, options?: Record<string, unknown>) => string;
const defaultProviderCopyTranslator: ProviderCopyTranslator = (key, options) => translate(key, options);

export function providerDescription(
  providerId: string,
  category: string,
  t: ProviderCopyTranslator = defaultProviderCopyTranslator,
) {
  const knownProviderKey = `controlPlane.providerCopy.descriptions.${providerId}`;
  const knownProviderCopy = t(knownProviderKey);
  if (knownProviderCopy !== knownProviderKey) return knownProviderCopy;
  if (category === "voice") return t("controlPlane.providerCopy.descriptions.voiceFallback");
  if (category === "media") return t("controlPlane.providerCopy.descriptions.mediaFallback");
  return t("controlPlane.providerCopy.descriptions.fallback");
}

export function providerLoginCopy(providerId: string, t: ProviderCopyTranslator = defaultProviderCopyTranslator) {
  const knownProviderKey = `controlPlane.providerCopy.login.${providerId}`;
  const knownProviderCopy = t(knownProviderKey);
  if (knownProviderCopy !== knownProviderKey) return knownProviderCopy;
  return t("controlPlane.providerCopy.login.gemini");
}

export function providerLocalTitle(providerId: string, t: ProviderCopyTranslator = defaultProviderCopyTranslator) {
  const knownProviderKey = `controlPlane.providerCopy.localTitle.${providerId}`;
  const knownProviderCopy = t(knownProviderKey);
  if (knownProviderCopy !== knownProviderKey) return knownProviderCopy;
  return t("controlPlane.providerCopy.localTitle.fallback");
}

export function providerLocalDescription(providerId: string, t: ProviderCopyTranslator = defaultProviderCopyTranslator) {
  const knownProviderKey = `controlPlane.providerCopy.localDescription.${providerId}`;
  const knownProviderCopy = t(knownProviderKey);
  if (knownProviderCopy !== knownProviderKey) return knownProviderCopy;
  return t("controlPlane.providerCopy.localDescription.fallback");
}

export function providerActionCopy(providerId: string, t: ProviderCopyTranslator = defaultProviderCopyTranslator) {
  if (providerId === "claude") return t("controlPlane.providerCopy.action.claudeCode");
  if (providerId === "codex") return t("controlPlane.providerCopy.action.codex");
  if (providerId === "gemini") return t("controlPlane.providerCopy.action.geminiCli");
  return t("controlPlane.providerCopy.action.officialRuntime");
}

export function elevenlabsVoiceOptionLabel(voice: {
  name: string;
  accent: string;
  gender: string;
  category: string;
  api_available?: boolean;
}, t: ProviderCopyTranslator = defaultProviderCopyTranslator) {
  const metadata = [
    voice.accent,
    voice.gender,
    voice.category,
    voice.api_available === false ? t("controlPlane.providerCopy.voices.requiresPaidApi") : "",
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
  const { t } = useAppI18n();
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
  const actionLabel = shouldShowDisconnect
    ? t("controlPlane.providerCopy.action.disconnect")
    : t("controlPlane.providerCopy.action.connect");
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
    ? t("controlPlane.providerCopy.action.disconnecting")
    : activeMode === "subscription_login" && loginPending
      ? t("controlPlane.providerCopy.action.waiting")
      : t("controlPlane.providerCopy.action.connecting");
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
  const { t } = useAppI18n();
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
        setFeedback(t("generated.controlPlane.codigo_confirmado_validando_a_conexao_com_a__b4dc964c"));
      } else if (result.status === "error" || result.last_error) {
        // Claude CLI reports invalid codes via ``last_error`` while keeping the
        // session in ``awaiting_browser`` so the operator can retry in the same
        // PTY. Surface that as a red error state so the rejection is obvious.
        setStatus("error");
        setFeedback(result.last_error || t("generated.controlPlane.nao_foi_possivel_validar_o_codigo_enviado_64508fb6"));
      } else {
        setStatus("idle");
        setFeedback(
          result.message || t("generated.controlPlane.codigo_enviado_aguardando_a_confirmacao_fina_12b05453"),
        );
      }
    } catch {
      setStatus("error");
      setFeedback(t("generated.controlPlane.nao_foi_possivel_enviar_o_codigo_agora_tente_21ffd76a"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div key={sessionId} className="space-y-2.5 px-1">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
        {t("generated.controlPlane.authentication_code_28780d65")}
      </div>
      <div className="flex items-center gap-2.5">
        <input
          className="field-shell min-w-0 flex-1 font-mono tracking-[0.08em] text-[var(--text-primary)]"
          type="text"
          inputMode="text"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          placeholder={t("generated.controlPlane.cole_o_codigo_de_autenticacao_787a08f7")}
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
          loadingLabel={t("generated.controlPlane.enviando_0a595e85")}
          icon={Link2}
          disabled={!code.trim()}
          onClick={() => {
            void handleSubmit();
          }}
          className="shrink-0 rounded-full px-3.5"
        >
          {t("generated.controlPlane.enviar_codigo_fa36fc41")}
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
  const { t, tl } = useAppI18n();

  if (!whisperCatalog) {
    return (
      <div className="px-1 text-sm text-[var(--text-tertiary)]">
        {t("generated.controlPlane.carregando_modelos_whisper_cpp_3bde8b2d")}
      </div>
    );
  }

  return (
    <div className="space-y-3 px-1">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
          {t("generated.controlPlane.modelos_whisper_cpp_c793774d")}
        </div>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {t("generated.controlPlane.modelos_locais_para_transcricao_offline_baix_6f80d015")}
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
                      {t("generated.controlPlane.padrao_ecc075df")}
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
                  {t("generated.controlPlane.baixado_fdf556f7")}
                </span>
              ) : null}
              <AsyncActionButton
                type="button"
                variant={variant.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={downloading}
                loadingLabel={t("generated.controlPlane.baixando_741a1547")}
                icon={ArrowDown}
                disabled={Boolean(variant.downloaded) || downloading}
                onClick={() => {
                  void downloadWhisperModel(variant.variant_id);
                }}
                className="rounded-full px-3.5"
              >
                {variant.downloaded ? t("generated.controlPlane.disponivel_099498ec") : t("generated.controlPlane.baixar_1ab3957c")}
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
                  loadingLabel={t("generated.controlPlane.removendo_2b311926")}
                  className="rounded-full px-3.5"
                >
                  {t("generated.controlPlane.remover_5465770e")}
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
  const { t, tl } = useAppI18n();
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
          {t(
            "generated.controlPlane.o_runtime_oficial_deste_provider_nao_esta_di_941ff905",
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
              {t("generated.controlPlane.modelo_base_do_kokoro_6a93f08f")}
            </span>
            {kokoroModelStatus?.downloaded ? (
              <>
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                  <Check className="h-3 w-3" strokeWidth={1.75} />
                  {t("generated.controlPlane.disponivel_099498ec")}
                </span>
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                  {formatAssetBytes(kokoroModelStatus.bytes)}
                </span>
              </>
            ) : (
              <span className="text-xs text-[var(--text-tertiary)]">
                {t("generated.controlPlane.necessario_antes_de_baixar_qualquer_voz_4b78c793")}
              </span>
            )}
            <div className="ml-auto flex items-center gap-2">
              <AsyncActionButton
                type="button"
                variant={kokoroModelStatus?.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={kokoroModelDownloading}
                loadingLabel={t("generated.controlPlane.baixando_741a1547")}
                icon={ArrowDown}
                disabled={Boolean(kokoroModelStatus?.downloaded) || kokoroModelDownloading}
                onClick={() => {
                  void downloadKokoroModel();
                }}
                className="rounded-full px-3.5"
              >
                {kokoroModelStatus?.downloaded
                  ? t("generated.controlPlane.modelo_baixado_c7fe0e67")
                  : t("generated.controlPlane.baixar_modelo_kokoro_7c23b6a5")}
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
                  loadingLabel={t("generated.controlPlane.removendo_2b311926")}
                >
                  {t("generated.controlPlane.remover_5465770e")}
                </AsyncActionButton>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <FieldShell
              label={t("generated.controlPlane.idioma_1bc8a0e5")}
              description={t("generated.controlPlane.define_o_idioma_padrao_e_filtra_a_lista_de_v_e6a4d526")}
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
            label={translate("generated.controlPlane.voz_4f8c6efc")}
            description={
              kokoroVoicesLoading
                ? t("controlPlane.providerCopy.voices.loadingOfficial")
                : t("controlPlane.providerCopy.voices.defaultLocalDescription")
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
                    kokoroVoicesLoading
                      ? t("controlPlane.providerCopy.voices.loading")
                      : t("controlPlane.providerCopy.voices.selectDefault")
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
                    {`${voice.name} — ${tl(voice.language_label)}${voice.downloaded ? ` · ${t("generated.controlPlane.baixada_97a64703")}` : ""}`}
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
              loadingLabel={t("generated.controlPlane.baixando_741a1547")}
              status={kokoroDownloadActive ? "pending" : "idle"}
              icon={ArrowDown}
              disabled={!kokoroDefaultVoice || Boolean(kokoroSelectedVoice?.downloaded)}
              onClick={() => {
                if (!kokoroDefaultVoice) return;
                void downloadKokoroVoice(kokoroDefaultVoice);
              }}
              className="rounded-full px-3.5"
            >
              {kokoroSelectedVoice?.downloaded ? t("generated.controlPlane.voz_baixada_2f40c57e") : t("generated.controlPlane.baixar_voz_dcfca6de")}
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
                loadingLabel={t("generated.controlPlane.removendo_2b311926")}
                className="rounded-full px-3.5"
              >
                {t("generated.controlPlane.remover_5465770e")}
              </AsyncActionButton>
            ) : null}
            <span className="text-sm text-[var(--text-secondary)]">
              {kokoroSelectedVoice
                ? `${tl(kokoroSelectedVoice.language_label)} · ${kokoroSelectedVoice.gender === "female" ? t("generated.controlPlane.feminina_06649a23") : t("generated.controlPlane.masculina_6a75350b")}${
                    kokoroSelectedVoice.downloaded && Number(kokoroSelectedVoice.bytes ?? 0) > 0
                      ? ` · ${formatAssetBytes(kokoroSelectedVoice.bytes)}`
                      : ""
                  }`
                : t("generated.controlPlane.selecione_uma_voz_para_baixar_sob_demanda_e0ff8d20")}
            </span>
          </div>

          </div>
        </>
      ) : provider.id === "supertonic" ? (
        <>
          <div className="flex flex-wrap items-center gap-3 px-1 pb-2 text-sm">
            <span className="text-[var(--text-secondary)]">
              {t("generated.controlPlane.modelo_supertonic_1d003ea1")}
            </span>
            {supertonicSelectedModel?.downloaded ? (
              <>
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                  <Check className="h-3 w-3" strokeWidth={1.75} />
                  {t("generated.controlPlane.disponivel_099498ec")}
                </span>
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                  {formatAssetBytes(supertonicSelectedModel.bytes)}
                </span>
              </>
            ) : (
              <span className="text-xs text-[var(--text-tertiary)]">
                {t("generated.controlPlane.download_inicial_via_hugging_face_f6a44a0a")}
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
                loadingLabel={t("generated.controlPlane.baixando_741a1547")}
                icon={ArrowDown}
                disabled={Boolean(supertonicSelectedModel?.downloaded) || supertonicModelDownloading}
                onClick={() => {
                  void downloadSupertonicModel(supertonicModel);
                }}
                className="rounded-full px-3.5"
              >
                {supertonicSelectedModel?.downloaded ? t("generated.controlPlane.modelo_baixado_c7fe0e67") : t("generated.controlPlane.baixar_modelo_6fe6bec5")}
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
                  loadingLabel={t("generated.controlPlane.removendo_2b311926")}
                >
                  {t("generated.controlPlane.remover_5465770e")}
                </AsyncActionButton>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <FieldShell label={t("generated.controlPlane.modelo_57cfd288")} description={t("generated.controlPlane.seleciona_o_snapshot_local_usado_na_sintese_41119e15")}>
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
                      {`${model.title}${model.downloaded ? ` · ${t("generated.controlPlane.baixado_34cb559b")}` : ""}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>

            <FieldShell label={t("generated.controlPlane.idioma_1bc8a0e5")} description={t("generated.controlPlane.define_o_idioma_padrao_para_a_fala_local_f4fb3e12")}>
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
              label={translate("generated.controlPlane.voz_4f8c6efc")}
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
                  <SelectValue placeholder={t("generated.controlPlane.selecione_a_voz_padrao_e59b227c")} />
                  <SelectLoadingSpinner loading={supertonicVoicesLoading} />
                </SelectTrigger>
                <SelectContent>
                  {supertonicDefaultVoice && !supertonicHasSelectedVoice ? (
                    <SelectItem value={supertonicDefaultVoice}>{supertonicDefaultVoice}</SelectItem>
                  ) : null}
                  {supertonicVoiceCatalog.items.map((voice) => (
                    <SelectItem key={voice.voice_id} value={voice.voice_id}>
                      {`${voice.name} · ${voice.kind === "custom" ? t("generated.controlPlane.custom_d632c043") : t("generated.controlPlane.preset_52adebe8")}${
                        voice.downloaded ? ` · ${t("generated.controlPlane.baixada_97a64703")}` : ""
                      }`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>

            <FieldShell label={t("generated.controlPlane.voz_custom_0d3f178d")} description={t("generated.controlPlane.importa_json_local_do_voice_builder_97970553")}>
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
                {t("generated.controlPlane.importar_json_283a7ae7")}
              </Button>
            </FieldShell>

            <div className="md:col-span-2 flex flex-wrap items-center gap-3 px-1">
              <AsyncActionButton
                type="button"
                variant={supertonicSelectedVoice?.downloaded ? "secondary" : "quiet"}
                size="sm"
                loading={supertonicVoiceDownloading}
                loadingLabel={t("generated.controlPlane.baixando_741a1547")}
                status={supertonicVoiceDownloading ? "pending" : "idle"}
                icon={ArrowDown}
                disabled={!supertonicDefaultVoice || Boolean(supertonicSelectedVoice?.downloaded)}
                onClick={() => {
                  if (!supertonicDefaultVoice) return;
                  void downloadSupertonicVoice(supertonicDefaultVoice, supertonicModel);
                }}
                className="rounded-full px-3.5"
              >
                {supertonicSelectedVoice?.downloaded ? t("generated.controlPlane.voz_baixada_2f40c57e") : t("generated.controlPlane.baixar_voz_dcfca6de")}
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
                  loadingLabel={t("generated.controlPlane.removendo_2b311926")}
                  className="rounded-full px-3.5"
                >
                  {t("generated.controlPlane.remover_5465770e")}
                </AsyncActionButton>
              ) : null}
              <span className="text-sm text-[var(--text-secondary)]">
                {supertonicSelectedVoice
                  ? `${tl(supertonicSelectedVoice.language_label)} · ${
                      supertonicSelectedVoice.gender === "female"
                        ? t("generated.controlPlane.feminina_06649a23")
                        : supertonicSelectedVoice.gender === "male"
                          ? t("generated.controlPlane.masculina_6a75350b")
                          : t("generated.controlPlane.custom_1995fb7d")
                    }${
                      supertonicSelectedVoice.downloaded && Number(supertonicSelectedVoice.bytes ?? 0) > 0
                        ? ` · ${formatAssetBytes(supertonicSelectedVoice.bytes)}`
                        : ""
                    }`
                  : t("generated.controlPlane.selecione_uma_voz_para_ativar_localmente_7efcd4f9")}
              </span>
            </div>
          </div>
        </>
      ) : supportsAnyAuth ? (
        <>
          <div className="space-y-2 px-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              {t("generated.controlPlane.autenticacao_023abe86")}
            </div>
            <div
              className="flex items-center gap-5 border-b border-[var(--border-subtle)]"
              role="tablist"
              aria-label={t("generated.controlPlane.formas_de_autenticacao_de_provider_40e86ee8", { provider: provider.title })}
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
                  {translate("generated.controlPlane.api_key_9245266a")}</button>
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
                  {provider.id === "claude" ? t("generated.controlPlane.claude_code_cli_b86bb2cc") : t("generated.controlPlane.servidor_local_79e4f89a")}
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
                  {t("generated.controlPlane.assinatura_login_c48f1746")}
                </button>
              ) : null}
            </div>
          </div>

          {activeMode === "api_key" ? (
            <div className="grid gap-3 xl:grid-cols-2">
              <div className="space-y-2 px-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    {t("generated.controlPlane.chave_da_api_7c8c1447")}
                  </div>
                  {connection?.api_key_present ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                      <CheckCircle2 className="h-3 w-3" strokeWidth={1.75} />
                      {t("generated.controlPlane.configurada_df5188a8")}
                    </span>
                  ) : null}
                </div>
                {connection?.api_key_present &&
                !connectionDraft?.api_key &&
                !replacingApiKey ? (
                  <div className="space-y-2">
                    <p className="text-xs text-[var(--text-tertiary)]">
                      {t(
                        "generated.controlPlane.a_chave_esta_armazenada_e_criptografada_para_9bd55941",
                      )}
                    </p>
                    <button
                      type="button"
                      onClick={markReplacingKey}
                      className="inline-flex items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-transparent px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                    >
                      <RefreshCcw className="h-3 w-3" strokeWidth={1.75} />
                      {t("generated.controlPlane.substituir_chave_0f8828aa")}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <SecretInput
                      placeholder={
                        provider.id === "gemini"
                          ? "AIza..."
                          : t("generated.controlPlane.cole_a_chave_da_api_074b64f7")
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
                        {t("generated.controlPlane.cancelar_substituicao_77e2d650")}
                      </button>
                    ) : null}
                  </div>
                )}
              </div>

              {provider.id === "elevenlabs" ? (
                <div className="grid gap-3 md:grid-cols-2">
                  <FieldShell
                    label={t("generated.controlPlane.idioma_padrao_3bdf98fe")}
                    description={t("generated.controlPlane.filtra_a_biblioteca_de_vozes_e_define_o_idio_ab2e4134")}
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
                        <SelectItem value={SELECT_ALL_VALUE}>{t("generated.controlPlane.todos_os_idiomas_8b2a5222")}</SelectItem>
                        {elevenlabsVoiceCatalog.available_languages.map((language) => (
                          <SelectItem key={language.code} value={language.code}>
                            {language.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FieldShell>

                  <FieldShell
                    label={t("generated.controlPlane.voz_padrao_2a5f9d79")}
                    description={
                      elevenlabsVoicesLoading
                        ? t("generated.controlPlane.carregando_vozes_disponiveis_9bc787ce")
                        : t("generated.controlPlane.usada_como_voz_default_dos_agentes_quando_tt_e3eecd86")
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
                            ? t("generated.controlPlane.carregando_vozes_a31605ea")
                            : t("generated.controlPlane.selecione_a_voz_padrao_e59b227c")}
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
                            {elevenlabsVoiceOptionLabel(voice, t)}
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
                  {providerLocalTitle(provider.id, t)}
                </div>
                <div className="text-sm leading-6 text-[var(--text-secondary)]">
                  {providerLocalDescription(provider.id, t)}
                </div>
              </div>
              {provider.id === "ollama" ? (
                <div className="space-y-2 px-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    {translate("generated.controlPlane.base_url_91eabd63")}</div>
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
                    {t(
                      "generated.controlPlane.ollama_no_desktop_host_http_host_docker_inte_3968b4fb",
                    )}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2 px-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {t("generated.controlPlane.login_oficial_09256a9c")}
              </div>
              <div className="text-sm leading-6 text-[var(--text-secondary)]">
                {providerLoginCopy(provider.id, t)}
              </div>
            </div>
          )}

          {provider.id === "ollama" ? (
            <div className="space-y-2 px-1">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  {t("generated.controlPlane.modelos_detectados_3f86289b")}
                </div>
                <div
                  className="inline-flex min-h-4 min-w-16 items-center justify-end text-xs text-[var(--text-quaternary)]"
                  role={ollamaModelsLoading ? "status" : undefined}
                  aria-label={ollamaModelsLoading ? t("generated.controlPlane.carregando_62b04e95") : undefined}
                >
                  {ollamaModelsLoading ? (
                    <InlineSpinner className="h-3.5 w-3.5" />
                  ) : ollamaModelCatalog.items.length ? (
                    t("generated.controlPlane.count_modelos_affe71e2", { count: ollamaModelCatalog.items.length })
                  ) : (
                    t("generated.controlPlane.nenhum_modelo_30d8523b")
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
                    ? t("generated.controlPlane.nenhum_modelo_foi_retornado_pelo_endpoint_co_0a0f60f9")
                    : t("generated.controlPlane.conecte_o_ollama_para_carregar_a_lista_real__fa609232")}
                </div>
              )}
            </div>
          ) : null}
        </>
      ) : (
        <div className="space-y-2 px-1">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
            {t("generated.controlPlane.operacao_e27e6db2")}
          </div>
          <div className="text-sm leading-6 text-[var(--text-secondary)]">
            {provider.id === "ollama"
              ? t("generated.controlPlane.o_ollama_depende_apenas_do_runtime_local_con_c2e28849")
              : t("generated.controlPlane.este_provider_nao_exige_autenticacao_manual__826b2975")}
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
              ? loginSession.message || t("generated.controlPlane.iniciando_autenticacao_e684996c")
              : loginSession.status === "awaiting_browser"
                ? loginSession.last_error ||
                  loginSession.message ||
                  t("generated.controlPlane.abra_o_link_abaixo_autorize_no_navegador_e_v_11550f56")
                : loginSession.status === "completed"
                  ? loginSession.message || t("generated.controlPlane.autenticacao_concluida_verificando_conexao_b4284672")
                  : loginSession.last_error ||
                    loginSession.message ||
                    t("generated.controlPlane.conclua_a_autenticacao_no_provider_2b47e2d5", {
                      provider: providerActionCopy(provider.id, t),
                    })}
          </span>
          {loginSession.status === "awaiting_browser" || loginSession.status === "pending" ? (
            <div className="space-y-3">
              {loginSession.user_code ? (
                <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                        {t("generated.controlPlane.codigo_de_autorizacao_54b1b8f9")}
                      </div>
                      <div className="mt-2 font-mono text-lg tracking-[0.28em] text-[var(--text-primary)] sm:text-[1.35rem]">
                        {loginSession.user_code}
                      </div>
                      <div className="mt-2 text-xs leading-5 text-[var(--text-quaternary)]">
                        {t("generated.controlPlane.use_este_codigo_na_pagina_de_autorizacao_abe_98218908")}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        void handleCopyLoginCode();
                      }}
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] text-[var(--text-quaternary)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--panel-soft)] hover:text-[var(--text-secondary)]"
                      aria-label={codeCopied ? t("generated.controlPlane.codigo_copiado_cd656998") : t("generated.controlPlane.copiar_codigo_de_autenticacao_6ecb37b0")}
                      title={codeCopied ? t("generated.controlPlane.codigo_copiado_cd656998") : t("generated.controlPlane.copiar_codigo_de_autenticacao_6ecb37b0")}
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
                    {t("generated.controlPlane.abrir_pagina_de_autorizacao_b9be17a8")}
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
  const { t, tl } = useAppI18n();
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
              {providerDescription(provider.id, provider.category, t)}
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
                ? t("generated.controlPlane.recolher_provider_1fb14d79", { provider: provider.title })
                : t("generated.controlPlane.expandir_provider_d219b1b9", { provider: provider.title })
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
  const { t, tl } = useAppI18n();
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
      title={translate("generated.controlPlane.settings_sections_models_label_80ad4bfc")}
      description={translate("generated.controlPlane.settings_sections_models_description_1224742f")}
    >
      {/* ---- Routing ---- */}
      <SettingsFieldGroup title={t("generated.controlPlane.routing_a8c41b5d")}>
        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={t("generated.controlPlane.provider_padrao_31f40d65")}
            description={t("generated.controlPlane.primeira_escolha_global_entre_os_providers_j_b8e656ce")}
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
                      ? t("generated.controlPlane.nenhum_provider_verificado_c65d5168")
                      : undefined
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {enabledGeneralProviders.length === 0 ? (
                  <SelectItem value={SELECT_ALL_VALUE} disabled>
                    {t("generated.controlPlane.nenhum_provider_verificado_c65d5168")}
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
            label={t("generated.controlPlane.perfil_de_uso_a9c9af3d")}
            description={t("generated.controlPlane.controla_a_preferencia_global_entre_custo_e__7ca08d04")}
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
            label={t("generated.controlPlane.ordem_de_fallback_a3ab2eaf")}
            description={t("generated.controlPlane.so_entram_aqui_providers_ja_verificados_e_pr_77c492a9")}
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
                          {connection?.verified ? t("generated.controlPlane.verificado_2e7257fc") : t("generated.controlPlane.ainda_nao_verificado_3848ed3a")}
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => moveFallback(providerId, "up")}
                          disabled={index === 0}
                          aria-label={t("generated.controlPlane.subir_cb17d495")}
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
                          aria-label={t("generated.controlPlane.descer_0e0b8bbe")}
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
      <SettingsFieldGroup title={t("generated.controlPlane.budgets_73005ecc")}>
        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={t("generated.controlPlane.budget_por_tarefa_891c0d6a")}
            description={t("generated.controlPlane.limite_global_por_execucao_individual_1d5d62fc")}
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
            label={t("generated.controlPlane.budget_acumulado_2aeb1647")}
            description={t("generated.controlPlane.teto_global_para_o_uso_consolidado_fafca014")}
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
      <SettingsFieldGroup title={t("generated.controlPlane.functional_defaults_c0c3361a")}>
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
                emptyLabel={t("generated.controlPlane.selecione_um_modelo_padrao_b60e4c30")}
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
                disabledOptionLabel={t("generated.controlPlane.indisponivel_no_momento_268dcf13")}
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
      <SettingsFieldGroup title={t("generated.controlPlane.aceleracao_de_hardware_b6a4173a")}>
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
                {t("generated.controlPlane.aceleracao_metal_apple_silicon_7591b382")}
              </span>
              <span className="text-xs text-[var(--text-tertiary)]">
                {t("controlPlane.providerCopy.acceleration.metalDescription")}
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
            ariaLabel={t("generated.controlPlane.aceleracao_metal_ca77f591")}
          />
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
