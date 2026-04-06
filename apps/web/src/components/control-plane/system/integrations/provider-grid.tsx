"use client";

import { useState, useMemo } from "react";
import { Search, ArrowLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { cn } from "@/lib/utils";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  ProviderLogo,
  ProviderAuthPanel,
  providerLabel,
  providerDescription,
  providerGlyphColor,
  providerOrder,
  PROVIDER_ACCENTS,
  PROVIDER_LOGOS,
  useProviderConnectionUi,
  type ProviderOption,
} from "@/components/control-plane/system/sections/section-models";
import {
  IntegrationCardStatusIndicator,
  integrationCardRootClassName,
} from "./integration-card-presentation";

/* ------------------------------------------------------------------ */
/*  Category labels for provider types                                 */
/* ------------------------------------------------------------------ */

const PROVIDER_CATEGORY_LABELS: Record<string, string> = {
  general: "LLM",
  voice: "Voz",
  media: "Mídia",
};

/* ------------------------------------------------------------------ */
/*  Transition variants                                                */
/* ------------------------------------------------------------------ */

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const viewIn = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -20 },
  transition: { duration: 0.28, ease: EASE },
} as const;

const viewOut = {
  initial: { opacity: 0, x: -20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 20 },
  transition: { duration: 0.28, ease: EASE },
} as const;

/* ------------------------------------------------------------------ */
/*  Provider card (matching IntegrationCard layout)                    */
/* ------------------------------------------------------------------ */

function ProviderCard({
  provider,
  connection,
  onClick,
}: {
  provider: { id: string; title: string; category: string };
  connection: { connection_status: string; verified: boolean; configured: boolean } | undefined;
  onClick: () => void;
}) {
  const { tl } = useAppI18n();
  const label = providerLabel(provider.id);
  const description = providerDescription(provider.id, provider.category);

  const isVerified = connection?.verified ?? false;
  const isConfigured = connection?.configured ?? false;

  let status: "connected" | "pending" | "disconnected" = "disconnected";
  if (isVerified) status = "connected";
  else if (isConfigured) status = "pending";

  return (
    <button
      type="button"
      onClick={onClick}
      className={integrationCardRootClassName(status)}
      aria-label={`${label} — ${status === "connected" ? tl("Conectado") : status === "pending" ? tl("Pendente") : tl("Desconectado")}`}
    >
      <ProviderLogo providerId={provider.id} title={label} active={isVerified} accented />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-[var(--text-primary)]">{label}</div>
        <div className="mt-0.5 truncate text-xs text-[var(--text-quaternary)]">{tl(description)}</div>
      </div>
      <div className="flex shrink-0 items-center">
        <IntegrationCardStatusIndicator status={status} />
      </div>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Provider detail view (matches integration detail layout)           */
/* ------------------------------------------------------------------ */

const PROVIDER_CATEGORY_DISPLAY: Record<string, string> = {
  general: "LLM",
  voice: "Voz",
  media: "Mídia",
};

const PROVIDER_HIGHLIGHT_COPY: Record<string, string> = {
  claude: "Anthropic para raciocínio profundo, revisão de código e fluxos oficiais do Claude Code.",
  codex: "OpenAI para tarefas agentic, execução assistida e modelos GPT com API key ou login oficial.",
  gemini: "Google Gemini para geração multimodal, AI Studio e autenticação oficial via Gemini CLI.",
  elevenlabs: "ElevenLabs para síntese de voz premium com catálogo gerenciado e idioma padrão por bot.",
  ollama: "Ollama para modelos locais ou remotos com descoberta real do catálogo no endpoint configurado.",
  sora: "Sora amplia os fluxos de mídia da OpenAI para geração visual e vídeo quando disponível.",
  kokoro: "Kokoro entrega TTS local com vozes sob demanda e operação otimizada para ambientes self-hosted.",
  whispercpp: "Whisper.cpp mantém transcrição local com runtime leve para ambientes controlados.",
};

function ProviderDetailView({
  provider,
  onBack,
}: {
  provider: ProviderOption;
  onBack: () => void;
}) {
  const { tl } = useAppI18n();
  const ui = useProviderConnectionUi(provider, true);

  const label = providerLabel(provider.id);
  const description = providerDescription(provider.id, provider.category);
  const accentRaw = PROVIDER_ACCENTS[provider.id] || "255 255 255";
  const highlightDescription = PROVIDER_HIGHLIGHT_COPY[provider.id] || description;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-2 text-sm text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)]"
      >
        <ArrowLeft size={14} />
        <span>
          {tl("Provedores AI")}
          <span className="mx-1.5 text-[var(--text-quaternary)]">/</span>
          <span className="text-[var(--text-primary)]">{label}</span>
        </span>
      </button>

      {/* Header: logo + name + actions */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-4">
          <ProviderLogo
            providerId={provider.id}
            title={label}
            active={ui.hasActiveConnection}
            accented
          />
          <div>
            <h2 className="text-lg font-bold tracking-[-0.03em] text-[var(--text-primary)]">
              {label}
            </h2>
            <p className="mt-0.5 text-sm text-[var(--text-tertiary)]">{tl(description)}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {ui.supportsAnyAuth ? (
            <AsyncActionButton
              type="button"
              variant={ui.shouldShowDisconnect ? "danger" : "primary"}
              size="sm"
              loading={ui.actionLoading}
              status={ui.actionStatus}
              loadingLabel={tl(ui.actionLoadingLabel)}
              onClick={ui.handleActionClick}
              disabled={ui.actionDisabled}
              icon={ui.actionIcon}
              className={cn(
                "rounded-lg px-3.5",
                ui.shouldShowDisconnect && "text-[var(--text-secondary)]",
              )}
            >
              {tl(ui.actionLabel)}
            </AsyncActionButton>
          ) : null}
        </div>
      </div>

      {/* Hero banner with provider accent gradient */}
      <div
        className="integration-detail-banner relative overflow-hidden rounded-xl"
        style={{
          background: `linear-gradient(135deg, color-mix(in srgb, rgb(${accentRaw}) 20%, var(--surface-elevated) 80%) 0%, color-mix(in srgb, rgb(${accentRaw}) 12%, var(--surface-panel-soft) 88%) 100%)`,
        }}
      >
        <div className="integration-detail-banner-grain" />
        <div className="relative z-10 px-6 py-5">
          <div className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-2">
            {PROVIDER_LOGOS[provider.id] ? (
              <span
                className="inline-block h-4 w-4 shrink-0"
                data-provider-banner-glyph={provider.id}
                style={{
                  backgroundColor: providerGlyphColor(provider.id, true),
                  WebkitMaskImage: `url(${PROVIDER_LOGOS[provider.id]})`,
                  maskImage: `url(${PROVIDER_LOGOS[provider.id]})`,
                  WebkitMaskRepeat: "no-repeat",
                  maskRepeat: "no-repeat",
                  WebkitMaskPosition: "center",
                  maskPosition: "center",
                  WebkitMaskSize: "contain",
                  maskSize: "contain",
                }}
              />
            ) : (
              <span className="text-sm font-semibold text-[var(--icon-primary)]">{label.slice(0, 1)}</span>
            )}
            <span className="text-sm text-[var(--text-primary)]">
              {tl(highlightDescription)}
            </span>
          </div>
        </div>
      </div>

      <section
        className="rounded-[26px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-5 py-4"
        aria-label={tl("Autenticação de {{provider}}", { provider: label })}
      >
        <ProviderAuthPanel
          provider={provider}
          ui={ui}
        />
      </section>

      {/* Info table */}
      <div>
        <span className="eyebrow mb-2 block text-[var(--text-quaternary)]">
          {tl("Informações")}
        </span>
        <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
          {[
            { id: "category", label: tl("Categoria"), value: tl(PROVIDER_CATEGORY_DISPLAY[provider.category] ?? provider.category) },
            { id: "vendor", label: tl("Desenvolvedor"), value: provider.vendor || label },
            { id: "type", label: tl("Tipo"), value: tl("Provedor de IA") },
          ].map((row, i, arr) => (
            <div
              key={row.id}
              className={cn(
                "flex items-center justify-between px-4 py-3 text-sm",
                i !== arr.length - 1 && "border-b border-[var(--border-subtle)]",
                i % 2 === 0 ? "bg-[var(--surface-elevated-soft)]" : "bg-transparent",
              )}
            >
              <span className="text-[var(--text-tertiary)]">{row.label}</span>
              <span className="font-medium text-[var(--text-primary)]">{row.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Provider grid (list view)                                          */
/* ------------------------------------------------------------------ */

function ProviderListView({
  onSelect,
}: {
  onSelect: (providerId: string) => void;
}) {
  const { providerOptions, providerConnections } = useSystemSettings();
  const { tl } = useAppI18n();
  const [search, setSearch] = useState("");

  const visibleProviders = useMemo(() => {
    let providers = providerOptions.filter((p) => p.category !== "infra");
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      providers = providers.filter(
        (p) =>
          providerLabel(p.id).toLowerCase().includes(q) ||
          p.title.toLowerCase().includes(q) ||
          p.vendor.toLowerCase().includes(q),
      );
    }
    return providers.sort(
      (a, b) => providerOrder(a.category) - providerOrder(b.category),
    );
  }, [providerOptions, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, typeof visibleProviders>();
    for (const provider of visibleProviders) {
      const list = map.get(provider.category) ?? [];
      list.push(provider);
      map.set(provider.category, list);
    }
    return Array.from(map.entries()).map(([category, entries]) => ({
      category,
      entries,
    }));
  }, [visibleProviders]);

  let cardIndex = 0;

  return (
    <motion.div {...viewOut}>
      <div className="integration-marketplace-hero">
        <h1 className="text-xl font-bold tracking-[-0.04em] text-[var(--text-primary)] sm:text-2xl">
          {tl("Conecte seus provedores")}
        </h1>
        <p className="mt-1.5 text-sm text-[var(--text-tertiary)]">
          {tl("Configure os provedores de IA para modelos de linguagem, voz e mídia.")}
        </p>
        <div className="mt-4">
          <div className="relative w-full max-w-sm">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-quaternary)]"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={tl("Buscar provedores...")}
              className="field-shell w-full py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
              aria-label={tl("Buscar provedores")}
            />
          </div>
        </div>
      </div>

      {grouped.length === 0 ? (
        <div className="py-12 text-center text-sm text-[var(--text-quaternary)]">
          {tl("Nenhum provedor encontrado.")}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {grouped.map(({ category, entries }) => (
            <div key={category}>
              <span className="eyebrow mb-2 block text-[var(--text-quaternary)]">
                {tl(PROVIDER_CATEGORY_LABELS[category] ?? category)}
              </span>
              <div className="grid grid-cols-2 gap-2">
                {entries.map((provider) => {
                  const idx = cardIndex++;
                  return (
                    <motion.div
                      key={provider.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.03, duration: 0.3, ease: EASE }}
                    >
                      <ProviderCard
                        provider={provider}
                        connection={providerConnections[provider.id]}
                        onClick={() => onSelect(provider.id)}
                      />
                    </motion.div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main export: manages list ↔ detail switching                       */
/* ------------------------------------------------------------------ */

export function ProviderGrid() {
  const { providerOptions } = useSystemSettings();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectedProvider = selectedId
    ? providerOptions.find((p) => p.id === selectedId)
    : null;

  return (
    <AnimatePresence mode="wait">
      {selectedProvider ? (
        <motion.div key="provider-detail" {...viewIn}>
          <ProviderDetailView
            provider={selectedProvider}
            onBack={() => setSelectedId(null)}
          />
        </motion.div>
      ) : (
        <ProviderListView
          key="provider-list"
          onSelect={setSelectedId}
        />
      )}
    </AnimatePresence>
  );
}
