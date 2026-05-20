"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Search, Server, Zap, Brain, HardDrive, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import { FormField } from "./form-field";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  getModelMeta,
  formatContextWindow,
  formatCost,
  type ModelMeta,
} from "./model-metadata";

/*  Provider visual config                                             */
/* Logos / accents / icon components live in the shared provider-brand
 * module so every UI surface (system settings, agent editor, model
 * picker) renders the same brand treatment for every provider.        */

import {
  PROVIDER_LOGOS,
  PROVIDER_ICON_COMPONENTS,
  PROVIDER_DISPLAY_NAMES as PROVIDER_DISPLAY,
  COLORED_BRAND_LOGO_PROVIDERS,
  providerGlyphColor,
} from "./provider-brand";

/*  Inline provider logo                                               */

function ProviderIcon({
  providerId,
  size = 20,
}: {
  providerId: string;
  size?: number;
}) {
  // Local-runtime providers (Ollama, Kokoro) get a CPU glyph in the
  // theme's primary text color so on-device inference stays visually
  // distinct from cloud providers without parsing model IDs.
  const Icon = PROVIDER_ICON_COMPONENTS[providerId];
  if (Icon) {
    return (
      <Icon
        width={size}
        height={size}
        className="shrink-0 text-[var(--text-secondary)]"
      />
    );
  }

  const logo = PROVIDER_LOGOS[providerId];
  if (!logo) {
    return <Server size={size} className="text-[var(--text-quaternary)]" />;
  }

  // Colored brand logos render as a real image so the original palette
  // is preserved across all states. Monochrome logos are mask-tinted.
  if (COLORED_BRAND_LOGO_PROVIDERS.has(providerId)) {
    return (
      <Image
        src={logo}
        alt={PROVIDER_DISPLAY[providerId] ?? providerId}
        width={size}
        height={size}
        className="shrink-0 object-contain"
      />
    );
  }

  return (
    <span
      className="block shrink-0"
      style={{
        width: size,
        height: size,
        backgroundColor: providerGlyphColor(providerId),
        WebkitMaskImage: `url(${logo})`,
        maskImage: `url(${logo})`,
        WebkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        maskPosition: "center",
        WebkitMaskSize: "contain",
        maskSize: "contain",
      }}
    />
  );
}

/*  Metric bar                                                         */

function MetricBar({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: typeof Zap;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1.5 w-[100px] shrink-0">
        <Icon size={12} className="text-[var(--text-quaternary)]" />
        <span className="text-[11px] text-[var(--text-tertiary)]">{label}</span>
      </div>
      <div className="flex gap-1 flex-1">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-1.5 flex-1 rounded-full transition-colors"
            style={{
              backgroundColor: i <= value
                ? "var(--tone-info-text)"
                : "rgba(255,255,255,0.08)",
            }}
          />
        ))}
      </div>
    </div>
  );
}

/*  Detail card                                                        */

function formatSizeBytes(bytes: number): string {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(0)} MB`;
  return `${bytes} B`;
}

function ModelDetailCard({
  meta,
  modelId,
  providerLabel,
  ollamaMeta,
}: {
  meta: ModelMeta | null;
  modelId: string;
  providerLabel: string;
  ollamaMeta?: {
    family?: string;
    parameter_size?: string;
    quantization_level?: string;
    size_bytes?: number;
  };
}) {
  const { t, tl } = useAppI18n();
  const isOllama = providerLabel === "Ollama";
  const hasCost = meta?.inputCostPer1M != null && meta.inputCostPer1M > 0;

  return (
    <div className="flex flex-col gap-3 w-[248px]">
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">
          {meta?.displayName || modelId}
        </div>
        {meta?.description && (
          <div className="mt-0.5 text-xs leading-relaxed text-[var(--text-tertiary)]">
            {meta.description}
          </div>
        )}
      </div>

      {meta && (
        <div className="flex flex-col gap-2">
          <MetricBar label={t("generated.controlPlane.velocidade_27f727af")} value={meta.speed} icon={Zap} />
          <MetricBar label={t("generated.controlPlane.inteligencia_56d3ac6e")} value={meta.intelligence} icon={Brain} />
        </div>
      )}

      <div className="flex flex-col gap-1.5 border-t border-[rgba(255,255,255,0.06)] pt-3">
        <div className="flex justify-between text-[11px]">
          <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.provider_c2d1091b")}</span>
          <span className="text-[var(--text-secondary)]">{providerLabel}</span>
        </div>
        {ollamaMeta?.family && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.familia_f26e5199")}</span>
            <span className="text-[var(--text-secondary)]">{ollamaMeta.family}</span>
          </div>
        )}
        {ollamaMeta?.parameter_size && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.parametros_a223a8f5")}</span>
            <span className="text-[var(--text-secondary)]">{ollamaMeta.parameter_size}</span>
          </div>
        )}
        {ollamaMeta?.quantization_level && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.quantizacao_4265fef5")}</span>
            <span className="font-mono text-[var(--text-secondary)]">{ollamaMeta.quantization_level}</span>
          </div>
        )}
        {ollamaMeta?.size_bytes != null && ollamaMeta.size_bytes > 0 && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.disco_27affb4b")}</span>
            <span className="text-[var(--text-secondary)]">{formatSizeBytes(ollamaMeta.size_bytes)}</span>
          </div>
        )}
        {meta?.contextWindow != null && meta.contextWindow > 0 && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.contexto_e462fa88")}</span>
            <span className="text-[var(--text-secondary)]">{formatContextWindow(meta.contextWindow)}</span>
          </div>
        )}
        {hasCost && (
          <>
            <div className="flex justify-between text-[11px]">
              <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.custo_input_628ae9af")}</span>
              <span className="text-[var(--text-secondary)]">{formatCost(meta!.inputCostPer1M!)} / 1M</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.custo_output_470790a9")}</span>
              <span className="text-[var(--text-secondary)]">{formatCost(meta!.outputCostPer1M!)} / 1M</span>
            </div>
          </>
        )}
        {isOllama && !hasCost && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.custo_e31838b4")}</span>
            <span className="text-[var(--text-secondary)]">{t("generated.controlPlane.gratuito_local_5d539621")}</span>
          </div>
        )}
        <div className="flex justify-between text-[11px]">
          <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.model_id_79808c3c")}</span>
          <span className="font-mono text-[var(--text-quaternary)]">{modelId}</span>
        </div>
      </div>
    </div>
  );
}

/*  Model row — always shows tooltip on hover                          */

function buildMergedMeta(opt: ModelOption): ModelMeta | null {
  const api = opt.apiMeta;
  const fallback = getModelMeta(opt.modelId);
  const hasApi = api && (api.context_window || api.input_cost_per_1m || api.speed_tier);
  if (!hasApi && !fallback) return null;
  return {
    displayName: opt.displayName,
    description: api?.description || fallback?.description || "",
    speed: api?.speed_tier || fallback?.speed || 3,
    intelligence: api?.intelligence_tier || fallback?.intelligence || 3,
    contextWindow: api?.context_window || fallback?.contextWindow || 0,
    inputCostPer1M: api?.input_cost_per_1m ?? fallback?.inputCostPer1M,
    outputCostPer1M: api?.output_cost_per_1m ?? fallback?.outputCostPer1M,
  };
}

function ModelRow({
  opt,
  isSelected,
  onSelect,
}: {
  opt: ModelOption;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const meta = buildMergedMeta(opt);
  const disabled = Boolean(opt.disabled);

  return (
    <Tooltip delayDuration={350}>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => {
            if (!disabled) onSelect();
          }}
          aria-disabled={disabled || undefined}
          className={cn(
            "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
            disabled
              ? "cursor-not-allowed text-[var(--text-quaternary)] opacity-60"
              : isSelected
                ? "bg-[var(--surface-hover)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)]",
          )}
        >
          <ProviderIcon providerId={opt.providerId} size={20} />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-[var(--text-primary)] truncate">
              {opt.displayName}
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-quaternary)] truncate">
              <span className="truncate">{opt.modelId}</span>
              {opt.providerId === "ollama" && opt.apiMeta?.parameter_size && (
                <span className="inline-flex shrink-0 items-center gap-1 rounded border border-[rgba(255,255,255,0.06)] px-1.5 py-0.5 text-[10px]">
                  <HardDrive size={9} />
                  {opt.apiMeta.parameter_size}
                </span>
              )}
            </div>
            {opt.disabledReason && (
              <div className="mt-0.5 truncate text-[11px] text-[var(--text-quaternary)]">
                {opt.disabledReason}
              </div>
            )}
          </div>
          {isSelected && <Check size={14} className="shrink-0 text-[var(--text-primary)]" />}
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="right"
        align="start"
        sideOffset={-4}
        className="!z-[200] !max-w-none !rounded-xl !px-4 !py-4"
      >
        <ModelDetailCard
          meta={meta}
          modelId={opt.modelId}
          providerLabel={opt.providerLabel}
          ollamaMeta={opt.providerId === "ollama" ? {
            family: opt.apiMeta?.family,
            parameter_size: opt.apiMeta?.parameter_size,
            quantization_level: opt.apiMeta?.quantization_level,
            size_bytes: opt.apiMeta?.size_bytes,
          } : undefined}
        />
      </TooltipContent>
    </Tooltip>
  );
}

/*  Helpers                                                            */

function prettifyModelId(modelId: string) {
  if (!modelId) return "";
  return modelId
    .replace(/:latest$/i, "")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase())
    .replace(/\bGpt\b/g, "GPT")
    .replace(/\bLlama\b/g, "Llama")
    .replace(/\bQwen\b/g, "Qwen");
}

/*  Types                                                              */

type ModelOption = {
  providerId: string;
  providerLabel: string;
  modelId: string;
  displayName: string;
  combinedValue: string;
  disabled?: boolean;
  disabledReason?: string;
  apiMeta?: {
    description?: string;
    context_window?: number;
    input_cost_per_1m?: number;
    output_cost_per_1m?: number;
    speed_tier?: number;
    intelligence_tier?: number;
    family?: string;
    parameter_size?: string;
    quantization_level?: string;
    size_bytes?: number;
  };
};

export type ModelSelectorProps = {
  label: string;
  description?: string;
  error?: string;
  value: string;
  onChange: (value: string) => void;
  providers: Record<string, Record<string, unknown>>;
  enabledProviders: string[];
  emptyLabel?: string;
  functionalCatalog?: Record<string, Array<Record<string, unknown>>>;
  functionId?: string;
  isOptionDisabled?: (option: {
    providerId: string;
    modelId: string;
    functionId: string;
  }) => boolean;
  disabledOptionLabel?: string;
};

/*  ModelSelector                                                      */

const PANEL_MAX_H = 368; // search bar (~52) + list (~320)

export function ModelSelector({
  label,
  description,
  error,
  value,
  onChange,
  providers,
  enabledProviders,
  emptyLabel,
  functionalCatalog,
  functionId,
  isOptionDisabled,
  disabledOptionLabel,
}: ModelSelectorProps) {
  const { t, tl } = useAppI18n();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  /* ---- Build options grouped by provider ---- */
  const { grouped, flat } = useMemo(() => {
    const allOptions: ModelOption[] = [];
    const catalogId = functionId ?? "general";
    const catalogEntries = functionalCatalog?.[catalogId];

    if (catalogEntries && catalogEntries.length > 0) {
      for (const entry of catalogEntries) {
        const pId = String(entry.provider_id || "");
        const mId = String(entry.model_id || "");
        if (!pId || !mId) continue;
        if (!enabledProviders.includes(pId)) continue;
        const disabled = Boolean(
          isOptionDisabled?.({ providerId: pId, modelId: mId, functionId: catalogId }),
        );
        const meta = getModelMeta(mId);
        allOptions.push({
          providerId: pId,
          providerLabel: String(entry.provider_title || PROVIDER_DISPLAY[pId] || pId),
          modelId: mId,
          displayName: meta?.displayName || String(entry.title || "") || prettifyModelId(mId),
          combinedValue: `${pId}:${mId}`,
          disabled,
          disabledReason: disabled ? tl(disabledOptionLabel || "indisponível no momento") : undefined,
          apiMeta: {
            description: String(entry.description || ""),
            context_window: Number(entry.context_window) || undefined,
            input_cost_per_1m: Number(entry.input_cost_per_1m) || undefined,
            output_cost_per_1m: Number(entry.output_cost_per_1m) || undefined,
            speed_tier: Number(entry.speed_tier) || undefined,
            intelligence_tier: Number(entry.intelligence_tier) || undefined,
            family: String(entry.family || "") || undefined,
            parameter_size: String(entry.parameter_size || "") || undefined,
            quantization_level: String(entry.quantization_level || "") || undefined,
            size_bytes: Number(entry.size_bytes) || undefined,
          },
        });
      }
    } else {
      for (const pId of enabledProviders) {
        const provider = providers[pId];
        if (!provider) continue;
        if (String(provider.category || "general") !== "general") continue;
        const models = Array.isArray(provider.available_models)
          ? provider.available_models.map(String)
          : [];
        const providerLabel = String(provider.title || PROVIDER_DISPLAY[pId] || pId);
        for (const mId of models) {
          const disabled = Boolean(
            isOptionDisabled?.({ providerId: pId, modelId: mId, functionId: catalogId }),
          );
          const meta = getModelMeta(mId);
          allOptions.push({
            providerId: pId,
            providerLabel,
            modelId: mId,
            displayName: meta?.displayName || prettifyModelId(mId),
            combinedValue: `${pId}:${mId}`,
            disabled,
            disabledReason: disabled ? tl(disabledOptionLabel || "indisponível no momento") : undefined,
          });
        }
      }
    }

    const groups = new Map<string, ModelOption[]>();
    for (const opt of allOptions) {
      const bucket = groups.get(opt.providerId) ?? [];
      bucket.push(opt);
      groups.set(opt.providerId, bucket);
    }

    return {
      grouped: Array.from(groups.entries()).map(([pId, items]) => ({
        providerId: pId,
        label: items[0]?.providerLabel ?? pId,
        items,
      })),
      flat: allOptions,
    };
  }, [
    providers,
    enabledProviders,
    functionalCatalog,
    functionId,
    isOptionDisabled,
    disabledOptionLabel,
    t, tl,
  ]);

  /* ---- Derived display for trigger ---- */
  const selectedOption = flat.find((o) => o.combinedValue === value);
  const triggerLabel = selectedOption
    ? selectedOption.displayName
    : emptyLabel
      ? tl(emptyLabel)
      : t("generated.controlPlane.selecione_um_modelo_38cc28d1");

  /* ---- Filtered by search ---- */
  const filteredGroups = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return grouped;
    return grouped
      .map((g) => ({
        ...g,
        items: g.items.filter(
          (o) =>
            o.displayName.toLowerCase().includes(q) ||
            o.modelId.toLowerCase().includes(q) ||
            o.providerLabel.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.items.length > 0);
  }, [grouped, search]);

  /* ---- Close on outside click ---- */
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (
        triggerRef.current?.contains(e.target as Node) ||
        panelRef.current?.contains(e.target as Node)
      ) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  /* ---- Close on Escape ---- */
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  /* ---- Panel position: auto up/down ---- */
  const [panelLayout, setPanelLayout] = useState<{
    style: React.CSSProperties;
    direction: "down" | "up";
  }>({ style: {}, direction: "down" });

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const vh = window.innerHeight;
    const spaceBelow = vh - rect.bottom;
    const spaceAbove = rect.top;
    const opensUp = spaceBelow < PANEL_MAX_H && spaceAbove > spaceBelow;

    setPanelLayout({
      direction: opensUp ? "up" : "down",
      style: {
        position: "fixed",
        left: rect.left,
        width: rect.width,
        zIndex: 150,
        ...(opensUp
          ? { bottom: vh - rect.top + 4 }
          : { top: rect.bottom + 4 }),
      },
    });
  }, [open]);

  return (
    <FormField label={label} description={description} error={error}>
      <div className="relative">
        {/* Trigger */}
        <button
          ref={triggerRef}
          type="button"
          onClick={() => { setOpen((v) => !v); setSearch(""); }}
          className="field-shell flex min-h-[48px] w-full items-center justify-between gap-3 rounded-[1rem] px-4 py-3 text-sm text-left"
        >
          <span className="flex min-w-0 items-center gap-3">
            {selectedOption && (
              <ProviderIcon providerId={selectedOption.providerId} size={18} />
            )}
            <span className={cn(
              "truncate",
              selectedOption ? "text-[var(--text-primary)]" : "text-[var(--text-quaternary)]",
            )}>
              {triggerLabel}
            </span>
          </span>
          <ChevronDown
            size={16}
            className={cn(
              "shrink-0 text-[var(--text-quaternary)] transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </button>

        {/* Dropdown panel */}
        {open && createPortal(
          <div ref={panelRef} style={panelLayout.style}>
            <div
              className={cn(
                "app-floating-panel rounded-xl overflow-hidden",
                panelLayout.direction === "down"
                  ? "animate-in fade-in-0 slide-in-from-top-1 duration-150"
                  : "animate-in fade-in-0 slide-in-from-bottom-1 duration-150",
              )}
            >
              {/* Search */}
              <div className="border-b border-[var(--divider-hair)] px-2.5 py-2">
                <div className="flex h-8 items-center gap-2 rounded-[var(--radius-input)] px-2.5 text-[var(--text-tertiary)] transition-[background-color,box-shadow] duration-150 focus-within:bg-[var(--panel-soft)] focus-within:shadow-[inset_0_0_0_1px_var(--border-strong)]">
                  <Search size={13} className="shrink-0 text-[var(--text-quaternary)]" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("generated.controlPlane.buscar_modelo_50f4a238")}
                    className="h-full w-full min-w-0 bg-transparent text-[0.8125rem] text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
                    style={{ outline: "none", border: "none", boxShadow: "none" }}
                    autoFocus
                  />
                  {search ? (
                    <button
                      type="button"
                      onClick={() => setSearch("")}
                      aria-label={t("generated.controlPlane.limpar_busca_0bb288dc")}
                      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[var(--radius-chip)] text-[var(--text-quaternary)] transition-colors focus-visible:text-[var(--text-primary)] focus-visible:outline-none"
                    >
                      <X size={12} />
                    </button>
                  ) : null}
                </div>
              </div>

              {/* Model list */}
              <TooltipProvider delayDuration={350}>
                <div className="max-h-[320px] overflow-y-auto p-1.5">
                  {/* Empty option */}
                  {emptyLabel && (
                    <button
                      type="button"
                      onClick={() => { onChange(""); setOpen(false); }}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                        value === ""
                          ? "bg-[var(--surface-hover)] text-[var(--text-primary)]"
                          : "text-[var(--text-secondary)]",
                      )}
                    >
                      {value === "" && <Check size={14} className="shrink-0 text-[var(--text-primary)]" />}
                      <span className={value === "" ? "" : "pl-[26px]"}>{tl(emptyLabel)}</span>
                    </button>
                  )}

                  {filteredGroups.length === 0 && (
                    <div className="px-3 py-4 text-center text-xs text-[var(--text-quaternary)]">
                      {t("generated.controlPlane.nenhum_modelo_encontrado_a79c6a50")}
                    </div>
                  )}

                  {filteredGroups.map((group) => (
                    <div key={group.providerId}>
                      <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                        {group.label}
                      </div>
                      {group.items.map((opt) => (
                        <ModelRow
                          key={opt.combinedValue}
                          opt={opt}
                          isSelected={value === opt.combinedValue}
                          onSelect={() => { onChange(opt.combinedValue); setOpen(false); }}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              </TooltipProvider>
            </div>
          </div>,
          document.body,
        )}
      </div>
    </FormField>
  );
}
