"use client";

import Image from "next/image";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  KeyRound,
  Link2,
  Server,
  Unplug,
} from "lucide-react";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { SecretInput } from "@/components/ui/secret-controls";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import type { ProviderLoginSession } from "@/lib/control-plane";
import { normalizeFallbackOrder } from "@/lib/system-settings-model";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function providerLabel(providerId: string) {
  if (providerId === "claude") return "Anthropic";
  if (providerId === "codex") return "OpenAI";
  if (providerId === "gemini") return "Google";
  return providerId;
}

export const PROVIDER_LOGOS: Record<string, string> = {
  claude: "/providers/anthropic.svg",
  codex: "/providers/openai.svg",
  gemini: "/providers/google.svg",
  elevenlabs: "/providers/elevenlabs.svg",
  ollama: "/providers/ollama.svg",
  sora: "/providers/sora.png",
};

export const PROVIDER_ICON_COMPONENTS: Record<string, typeof Server> = {
  kokoro: Server,
};

export const MASKED_LOGO_PROVIDERS = new Set(["gemini"]);

export const MONOCHROME_LOGO_PROVIDERS = new Set(["codex", "elevenlabs", "ollama"]);

export const PROVIDER_ACCENTS: Record<string, string> = {
  claude: "212 120 62",
  codex: "16 163 127",
  gemini: "86 138 248",
  elevenlabs: "250 204 21",
  ollama: "56 189 248",
  sora: "236 72 153",
  kokoro: "129 140 248",
};

export function providerGlyphColor(providerId: string, emphasized = false) {
  if (MONOCHROME_LOGO_PROVIDERS.has(providerId)) {
    return "rgb(255 255 255)";
  }
  if (!emphasized) {
    return "rgb(255 255 255)";
  }
  const accent = PROVIDER_ACCENTS[providerId] || "255 255 255";
  return `rgb(${accent})`;
}

export function providerOrder(category: string) {
  if (category === "general") return 0;
  if (category === "voice") return 1;
  if (category === "media") return 2;
  return 3;
}

export type ProviderOption = ReturnType<typeof useSystemSettings>["providerOptions"][number];

export function providerDescription(providerId: string, category: string) {
  if (providerId === "claude") return "Anthropic via API Key ou Claude Code CLI local.";
  if (providerId === "codex") return "OpenAI via API Key ou login oficial do Codex.";
  if (providerId === "gemini") return "Google via GEMINI_API_KEY ou login oficial do Gemini CLI.";
  if (providerId === "elevenlabs") return "Voz premium com API Key, idioma padrão e seleção de vozes.";
  if (providerId === "sora") return "Provider de mídia com autenticação pela plataforma OpenAI.";
  if (providerId === "ollama") return "Servidor Ollama local ou cloud com API Key, usando o catálogo real de modelos.";
  if (category === "voice") return "Provider multimodal focado em voz e áudio.";
  if (category === "media") return "Provider multimídia disponível para fluxos especializados.";
  return "Provider disponível no catálogo global do sistema.";
}

export function providerLoginCopy(providerId: string) {
  if (providerId === "claude") {
    return "Use o login oficial do Claude Code para conectar sua assinatura Anthropic.";
  }
  if (providerId === "codex") {
    return "Use o login oficial do Codex com sua conta OpenAI/ChatGPT. A cobrança da API continua separada da assinatura.";
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
    return "A autenticação da Anthropic é gerenciada pelo Claude Code CLI instalado nesta máquina. Configure o CLI com `claude auth login` antes de conectar.";
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
}) {
  const metadata = [voice.accent, voice.gender, voice.category].filter(Boolean).join(" · ");
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
    if (provider.id === "codex" && functionId === "transcription") {
      return Boolean(connection?.verified && connection?.auth_mode === "api_key" && connection?.api_key_present);
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
        className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] transition-colors"
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
    const renderAsMask = active || accented || MASKED_LOGO_PROVIDERS.has(providerId);
    return (
      <div
        className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] transition-colors"
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
      className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-sm font-semibold transition-colors"
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
    kokoroDownloadJobForVoice,
    loadKokoroVoices,
    downloadKokoroVoice,
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
  const kokoroDownloadJob = kokoroDownloadJobForVoice(kokoroDefaultVoice);
  const kokoroSelectedVoice = kokoroVoiceCatalog.items.find(
    (voice) => voice.voice_id === kokoroDefaultVoice,
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
  }, [isOpen, kokoroLanguage, loadKokoroVoices, provider.id]);

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
    kokoroDownloadJob,
    kokoroSelectedVoice,
    loadKokoroVoices,
    downloadKokoroVoice,
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
      } else if (result.status === "error") {
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
          className="field-shell min-w-0 flex-1 px-4 py-2.5 font-mono text-sm tracking-[0.08em] text-[var(--text-primary)]"
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
    kokoroDownloadJob,
    kokoroSelectedVoice,
    loadKokoroVoices,
    downloadKokoroVoice,
    ollamaModelCatalog,
    ollamaModelsLoading,
    submitProviderLoginCode,
  } = ui;
  const loginCode = loginSession?.user_code?.trim() || "";
  const codeCopied = Boolean(loginCode) && copiedCode === loginCode;
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
        <div className="flex items-start gap-3 rounded-2xl border border-[rgba(255,180,76,0.18)] bg-[rgba(255,180,76,0.08)] px-3 py-2.5 text-sm text-[var(--text-secondary)]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          <div>
            {tl(
              "O runtime oficial deste provider não está disponível neste ambiente. Instale o CLI correspondente antes de concluir a conexão.",
            )}
          </div>
        </div>
      ) : null}

      {provider.id === "kokoro" ? (
        <div className="grid gap-3 md:grid-cols-2">
          <FieldShell
            label="Idioma"
            description="Define o idioma padrão e filtra a lista de vozes."
          >
            <select
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={kokoroLanguage}
              onChange={(event) => {
                const nextLanguage = event.target.value;
                setField("models", {
                  ...draft.values.models,
                  kokoro_default_language: nextLanguage,
                  kokoro_default_voice: "",
                  kokoro_default_voice_label: "",
                });
                void loadKokoroVoices(nextLanguage, { force: true });
              }}
            >
              {kokoroVoiceCatalog.available_languages.map((language) => (
                <option key={language.id} value={language.id}>
                  {tl(language.label)}
                </option>
              ))}
            </select>
          </FieldShell>

          <FieldShell
            label="Voz"
            description={
              kokoroVoicesLoading
                ? "Carregando vozes oficiais..."
                : "Escolha a voz padrão local usada pelos bots."
            }
          >
            <select
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={kokoroDefaultVoice}
              disabled={kokoroVoicesLoading}
              onChange={(event) => {
                const nextVoiceId = event.target.value;
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
              <option value="">
                {kokoroVoicesLoading ? "Carregando vozes..." : "Selecione a voz padrão"}
              </option>
              {kokoroDefaultVoice &&
              !kokoroVoiceCatalog.items.some((voice) => voice.voice_id === kokoroDefaultVoice) ? (
                <option value={kokoroDefaultVoice}>
                  {kokoroDefaultVoiceLabel || kokoroDefaultVoice}
                </option>
              ) : null}
              {kokoroVoiceCatalog.items.map((voice) => (
                <option key={voice.voice_id} value={voice.voice_id}>
                  {`${voice.name} — ${tl(voice.language_label)}${voice.downloaded ? ` · ${tl("baixada")}` : ""}`}
                </option>
              ))}
            </select>
          </FieldShell>

          <div className="md:col-span-2 flex flex-wrap items-center gap-3 px-1">
            <AsyncActionButton
              type="button"
              variant={kokoroSelectedVoice?.downloaded ? "secondary" : "quiet"}
              size="sm"
              loading={Boolean(
                kokoroDownloadJob &&
                  ["pending", "running"].includes(String(kokoroDownloadJob.status)),
              )}
              loadingLabel={tl("Baixando")}
              status={
                kokoroDownloadJob?.status === "error"
                  ? "error"
                  : kokoroDownloadJob?.status === "completed"
                    ? "success"
                    : "idle"
              }
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
            <span className="text-sm text-[var(--text-secondary)]">
              {kokoroSelectedVoice
                ? `${tl(kokoroSelectedVoice.language_label)} · ${kokoroSelectedVoice.gender === "female" ? tl("Feminina") : tl("Masculina")}`
                : tl("Selecione uma voz para baixar sob demanda.")}
            </span>
          </div>

          {kokoroDownloadJob ? (
            <div className="md:col-span-2 space-y-2 px-1">
              <div className="flex items-center justify-between gap-3 text-xs text-[var(--text-secondary)]">
                <span>{kokoroDownloadJob.message || tl("Download da voz em andamento.")}</span>
                <span>{Math.round(kokoroDownloadJob.progress_percent || 0)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--text-primary)_8%,transparent)]">
                <div
                  className="h-full rounded-full bg-[var(--text-primary)] transition-[width] duration-300 ease-out"
                  style={{ width: `${Math.max(6, Math.min(100, kokoroDownloadJob.progress_percent || 0))}%` }}
                />
              </div>
            </div>
          ) : null}
        </div>
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
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  {tl("Chave da API")}
                </div>
                <SecretInput
                  placeholder={
                    connection?.api_key_present
                      ? (connection.api_key_preview || tl("Chave configurada"))
                      : provider.id === "gemini"
                        ? "AIza..."
                        : tl("Cole a chave da API")
                  }
                  value={connectionDraft?.api_key || ""}
                  onChange={(event) =>
                    setProviderConnectionDraft(provider.id, { api_key: event.target.value })
                  }
                />
              </div>

              {provider.id === "gemini" ? (
                <div className="space-y-2 px-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    {tl("Projeto Google")}
                  </div>
                  <input
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type="text"
                    placeholder={tl("meu-projeto-google")}
                    value={connectionDraft?.project_id || ""}
                    onChange={(event) =>
                      setProviderConnectionDraft(provider.id, { project_id: event.target.value })
                    }
                  />
                </div>
              ) : provider.id === "ollama" ? (
                <div className="space-y-2 px-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    {tl("Base URL")}
                  </div>
                  <input
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type="text"
                    placeholder="https://ollama.com"
                    value={connectionDraft?.base_url || ""}
                    onChange={(event) =>
                      setProviderConnectionDraft(provider.id, { base_url: event.target.value })
                    }
                  />
                </div>
              ) : provider.id === "elevenlabs" ? (
                <div className="grid gap-3 md:grid-cols-2">
                  <FieldShell
                    label="Idioma padrão"
                    description="Filtra a biblioteca de vozes e define o idioma padrão dos bots."
                  >
                    <select
                      className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                      value={elevenlabsLanguage}
                      onChange={(event) => {
                        const nextLanguage = event.target.value;
                        setField("models", {
                          ...draft.values.models,
                          elevenlabs_default_language: nextLanguage,
                          elevenlabs_default_voice: "",
                          elevenlabs_default_voice_label: "",
                        });
                        void loadElevenLabsVoices(nextLanguage, { force: true });
                      }}
                    >
                      <option value="">{tl("Todos os idiomas")}</option>
                      {elevenlabsVoiceCatalog.available_languages.map((language) => (
                        <option key={language.code} value={language.code}>
                          {language.label}
                        </option>
                      ))}
                    </select>
                  </FieldShell>

                  <FieldShell
                    label="Voz padrão"
                    description={
                      elevenlabsVoicesLoading
                        ? "Carregando vozes disponíveis..."
                        : "Usada como voz default dos bots quando TTS estiver ativo."
                    }
                  >
                    <select
                      className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                      value={elevenlabsDefaultVoice}
                      disabled={
                        elevenlabsVoicesLoading ||
                        !(connection?.verified || connection?.configured || connection?.api_key_present)
                      }
                      onChange={(event) => {
                        const nextVoiceId = event.target.value;
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
                      <option value="">
                        {elevenlabsVoicesLoading
                          ? tl("Carregando vozes...")
                          : tl("Selecione a voz padrão")}
                      </option>
                      {elevenlabsDefaultVoice &&
                      !elevenlabsVoiceCatalog.items.some((voice) => voice.voice_id === elevenlabsDefaultVoice) ? (
                        <option value={elevenlabsDefaultVoice}>
                          {elevenlabsDefaultVoiceLabel || elevenlabsDefaultVoice}
                        </option>
                      ) : null}
                      {elevenlabsVoiceCatalog.items.map((voice) => (
                        <option key={voice.voice_id} value={voice.voice_id}>
                          {elevenlabsVoiceOptionLabel(voice)}
                        </option>
                      ))}
                    </select>
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
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type="text"
                    placeholder="http://localhost:11434"
                    value={connectionDraft?.base_url || ""}
                    onChange={(event) =>
                      setProviderConnectionDraft(provider.id, { base_url: event.target.value })
                    }
                  />
                </div>
              ) : null}
            </div>
          ) : (
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,260px)]">
              <div className="space-y-2 px-1">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  {tl("Login oficial")}
                </div>
                <div className="text-sm leading-6 text-[var(--text-secondary)]">
                  {tl(providerLoginCopy(provider.id))}
                </div>
              </div>

              {provider.id === "gemini" ? (
                <div className="space-y-2 px-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    {tl("Projeto Google")}
                  </div>
                  <input
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type="text"
                    placeholder={tl("meu-projeto-google")}
                    value={connectionDraft?.project_id || ""}
                    onChange={(event) =>
                      setProviderConnectionDraft(provider.id, { project_id: event.target.value })
                    }
                  />
                </div>
              ) : null}
            </div>
          )}

          {provider.id === "ollama" ? (
            <div className="space-y-2 px-1">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  {tl("Modelos detectados")}
                </div>
                <div className="text-xs text-[var(--text-quaternary)]">
                  {ollamaModelsLoading
                    ? tl("Carregando...")
                    : ollamaModelCatalog.items.length
                      ? tl("{{count}} modelos", { count: ollamaModelCatalog.items.length })
                      : tl("Nenhum modelo")}
                </div>
              </div>
              {ollamaModelCatalog.items.length ? (
                <div className="max-h-48 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
                  <div className="divide-y divide-[var(--border-subtle)]">
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
                <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3.5">
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
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-quaternary)] shadow-[inset_0_1px_0_color-mix(in_srgb,var(--text-primary)_4%,transparent)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--surface-panel-soft)] hover:text-[var(--text-secondary)]"
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
      className="overflow-hidden rounded-[26px] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] transition-colors"
    >
      <div
        className={cn(
          "group flex items-center gap-3 px-5 py-4 transition-colors",
          "hover:bg-[color-mix(in_srgb,var(--text-primary)_3%,transparent)]",
          isOpen ? "rounded-t-[26px]" : "rounded-[26px]",
        )}
      >
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-4 rounded-[22px] text-left",
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
              "inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-quaternary)] transition-colors",
              "group-hover:bg-[var(--surface-panel-soft)]",
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
  const { tl } = useAppI18n();
  const { draft, setField, providerOptions, enabledProviders, moveFallback, providerConnections } =
    useSystemSettings();

  const generalProviders = useMemo(
    () => providerOptions.filter((provider) => provider.category === "general"),
    [providerOptions],
  );

  const enabledGeneralProviders = enabledProviders.filter((providerId) =>
    generalProviders.some((provider) => provider.id === providerId),
  );
  const modelFunctions = draft.catalogs.model_functions || [];
  const functionalCatalog = draft.catalogs.functional_model_catalog || {};

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
            label="Provider padrão"
            description="Primeira escolha global entre os providers já verificados."
          >
            <select
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={draft.values.models.default_provider}
              onChange={(event) =>
                setField("models", {
                  ...draft.values.models,
                  default_provider: event.target.value,
                  fallback_order: normalizeFallbackOrder(
                    enabledGeneralProviders,
                    draft.values.models.fallback_order,
                    event.target.value,
                  ),
                })
              }
            >
              {enabledGeneralProviders.length === 0 ? (
                <option value="">{tl("Nenhum provider verificado")}</option>
              ) : null}
              {enabledGeneralProviders.map((id) => (
                <option key={id} value={id}>
                  {providerLabel(id)}
                </option>
              ))}
            </select>
          </FieldShell>

          <FieldShell
            label="Perfil de uso"
            description="Controla a preferência global entre custo e qualidade."
          >
            <select
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={draft.values.models.usage_profile}
              onChange={(event) =>
                setField("models", {
                  ...draft.values.models,
                  usage_profile: event.target.value,
                })
              }
            >
              {draft.catalogs.usage_profiles.map((profile) => (
                <option key={String(profile.id)} value={String(profile.id)}>
                  {tl(String(profile.label))}
                </option>
              ))}
            </select>
          </FieldShell>
        </div>

        {enabledGeneralProviders.length > 1 ? (
          <FieldShell
            label="Ordem de fallback"
            description="Só entram aqui providers já verificados e prontos para uso."
          >
            <div className="space-y-2">
              {draft.values.models.fallback_order
                .filter((id) => enabledGeneralProviders.includes(id))
                .map((providerId, index) => {
                  const connection = providerConnections[providerId];
                  return (
                    <div
                      key={providerId}
                      className="flex items-center gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3 py-3"
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
                        <button
                          type="button"
                          onClick={() => moveFallback(providerId, "up")}
                          disabled={index === 0}
                          className="rounded-xl border border-[var(--border-subtle)] px-2 py-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-elevated)] disabled:opacity-30"
                        >
                          <ArrowUp className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => moveFallback(providerId, "down")}
                          disabled={index === enabledGeneralProviders.length - 1}
                          className="rounded-xl border border-[var(--border-subtle)] px-2 py-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-elevated)] disabled:opacity-30"
                        >
                          <ArrowDown className="h-4 w-4" />
                        </button>
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
          <FieldShell label="Budget por tarefa" description="Limite global por execução individual.">
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
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

          <FieldShell label="Budget acumulado" description="Teto global para o uso consolidado.">
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
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
            const options = functionalCatalog[functionItem.id] || [];
            const selected = draft.values.models.functional_defaults?.[functionItem.id];
            const selectedValue =
              selected?.provider_id && selected?.model_id
                ? `${selected.provider_id}:${selected.model_id}`
                : "";
            const groupedOptions = providerOptions
              .map((provider) => ({
                provider,
                items: options.filter((item) => item.provider_id === provider.id),
              }))
              .filter((group) => group.items.length > 0);

            return (
              <FieldShell
                key={functionItem.id}
                label={tl(functionItem.title)}
                description={tl(functionItem.description)}
              >
                <select
                  className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                  value={selectedValue}
                  onChange={(event) => updateFunctionalDefault(functionItem.id, event.target.value)}
                >
                  <option value="">{tl("Selecione um modelo padrão")}</option>
                  {groupedOptions.map(({ provider, items }) => {
                    const selectable = isSelectableProvider(
                      provider,
                      providerConnections[provider.id],
                      functionItem.id,
                    );
                    return (
                      <optgroup key={provider.id} label={provider.title}>
                        {items.map((item) => (
                          <option
                            key={`${item.provider_id}:${item.model_id}`}
                            value={`${item.provider_id}:${item.model_id}`}
                            disabled={!selectable}
                          >
                            {item.title}
                            {!selectable ? ` — ${tl("indisponível no momento")}` : ""}
                          </option>
                        ))}
                      </optgroup>
                    );
                  })}
                </select>
              </FieldShell>
            );
          })}
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
