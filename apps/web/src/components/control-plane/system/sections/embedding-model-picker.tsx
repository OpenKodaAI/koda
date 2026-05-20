"use client";

import { useCallback, useState } from "react";
import { translate } from "@/lib/i18n";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Download,
  Loader2,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";
import { useDownloadJob } from "@/hooks/use-download-job";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAppMutation, useControlPlaneQuery } from "@/hooks/use-app-query";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type EmbeddingModel = {
  id: string;
  repo_id: string;
  title: string;
  description: string;
  size_mb: number;
  dimension: number;
  languages: string[];
  quality: number;
  speed: number;
  hardware_hint: string;
  multilingual: boolean;
  is_default_install: boolean;
  installed: boolean;
  disk_bytes: number;
  active_job?: {
    id: string;
    status: "pending" | "running" | "completed" | "error" | "cancelled";
    progress_percent: number;
  } | null;
};

type CatalogPayload = {
  items: EmbeddingModel[];
  active: string;
  default: string;
};

const HARDWARE_LABEL: Record<string, string> = {
  cpu: "CPU",
  "cpu/mps": "CPU / Apple Silicon",
  mps_recommended: "Apple Silicon recomendado",
  gpu_recommended: "GPU dedicada recomendada",
};

// Single shared cache key — anywhere in the UI that reads or invalidates the
// catalog uses this exact tuple so TanStack Query can deduplicate.
export const EMBEDDING_CATALOG_QUERY_KEY = ["control-plane", "embedding-catalog"] as const;

function Stars({ score, max = 5 }: { score: number; max?: number }) {
  return (
    <span className="text-[11px] tracking-tight text-[var(--text-tertiary)]">
      {Array.from({ length: max })
        .map((_, i) => (i < score ? "●" : "○"))
        .join("")}
    </span>
  );
}

function formatSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

async function fetchEmbeddingCatalog(): Promise<CatalogPayload> {
  const res = await fetch("/api/control-plane/providers/embedding/models", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const text = await res.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    // raw HTML or non-JSON body — usually a stale Next route or proxy error
  }
  if (!res.ok) {
    const errorText =
      (parsed && typeof parsed === "object" && "error" in (parsed as Record<string, unknown>)
        ? String((parsed as Record<string, unknown>).error || "")
        : "") || text.slice(0, 200);
    throw new Error(errorText || `HTTP ${res.status}`);
  }
  if (
    !parsed ||
    typeof parsed !== "object" ||
    !Array.isArray((parsed as Record<string, unknown>).items)
  ) {
    throw new Error("embedding.catalog.malformed");
  }
  return parsed as CatalogPayload;
}

export function EmbeddingModelPicker({ memoryEnabled = false }: { memoryEnabled?: boolean }) {
  const { t, tl } = useAppI18n();
  const { showToast } = useToast();
  const { start, isActive } = useDownloadJob();
  const queryClient = useQueryClient();

  // Cached catalog fetch. Tier "catalog" gives us:
  //   staleTime: 60s  → no refetch within a minute
  //   gcTime:    10m  → kept warm even if the user leaves and returns
  // The catalog rarely changes outside of operator actions (download / select
  // / delete), and each of those mutations writes the fresh payload back via
  // setQueryData — so most of the time we never hit the network at all.
  const {
    data: catalog,
    error: catalogError,
    isLoading: catalogLoading,
    refetch,
  } = useControlPlaneQuery<CatalogPayload>({
    tier: "catalog",
    queryKey: EMBEDDING_CATALOG_QUERY_KEY,
    queryFn: fetchEmbeddingCatalog,
    // Backend may have just restarted; tolerate a few quick retries.
    retry: 3,
    retryDelay: (attempt) => Math.min(2500, 600 * 2 ** attempt),
  });

  const setCatalog = useCallback(
    (next: CatalogPayload) => {
      queryClient.setQueryData(EMBEDDING_CATALOG_QUERY_KEY, next);
    },
    [queryClient],
  );

  const [busyId, setBusyId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const handleDownload = useCallback(
    async (model: EmbeddingModel) => {
      await start({
        providerId: "embedding",
        assetKey: model.id,
        startEndpoint: `/api/control-plane/providers/embedding/models/${model.id}/download`,
        toastTitle: `${t("generated.controlPlane.baixando_741a1547")} ${model.title}`,
        successMessage: t("generated.controlPlane.modelo_baixado_e_pronto_para_uso_2f07b6f7"),
        onComplete: async () => {
          await queryClient.invalidateQueries({ queryKey: EMBEDDING_CATALOG_QUERY_KEY });
        },
      });
    },
    [queryClient, start, t, tl],
  );

  const selectMutation = useAppMutation<CatalogPayload, EmbeddingModel>({
    mutationFn: async (model) => {
      const res = await fetch(
        `/api/control-plane/providers/embedding/models/${model.id}/select`,
        { method: "POST", credentials: "same-origin" },
      );
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error || t("generated.controlPlane.falha_ao_selecionar_modelo_dc211fc9"));
      }
      return (await res.json()) as CatalogPayload;
    },
    onSuccess: (json, model) => {
      setCatalog(json);
      showToast(`${t("generated.controlPlane.modelo_ativo_61c3d51b")}: ${model.title}`, "success");
    },
    onError: (err) => {
      showToast(err.message || t("generated.controlPlane.falha_ao_selecionar_modelo_dc211fc9"), "error");
    },
    onSettled: () => setBusyId(null),
  });

  const deleteMutation = useAppMutation<CatalogPayload, EmbeddingModel>({
    mutationFn: async (model) => {
      const res = await fetch(
        `/api/control-plane/providers/embedding/models/${model.id}`,
        { method: "DELETE", credentials: "same-origin" },
      );
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error || t("generated.controlPlane.falha_ao_apagar_modelo_4ca369e2"));
      }
      return (await res.json()) as CatalogPayload;
    },
    onSuccess: (json, model) => {
      setCatalog(json);
      showToast(`${t("generated.controlPlane.modelo_apagado_281c09ee")}: ${model.title}`, "success");
    },
    onError: (err) => {
      showToast(err.message || t("generated.controlPlane.falha_ao_apagar_modelo_4ca369e2"), "error");
    },
    onSettled: () => setBusyId(null),
  });

  const handleSelect = useCallback(
    (model: EmbeddingModel) => {
      if (!model.installed) return;
      setBusyId(model.id);
      selectMutation.mutate(model);
    },
    [selectMutation],
  );

  const handleDelete = useCallback(
    (model: EmbeddingModel) => {
      // First click arms confirmation; second click within ~5s actually deletes.
      if (pendingDeleteId !== model.id) {
        setPendingDeleteId(model.id);
        setTimeout(() => {
          setPendingDeleteId((cur) => (cur === model.id ? null : cur));
        }, 5000);
        return;
      }
      setPendingDeleteId(null);
      setBusyId(model.id);
      deleteMutation.mutate(model);
    },
    [deleteMutation, pendingDeleteId],
  );

  if (catalogError && !catalog) {
    const message =
      catalogError.message === "embedding.catalog.malformed"
        ? t("generated.controlPlane.resposta_inesperada_do_catalogo_1b4e7c37")
        : catalogError.message || t("generated.controlPlane.falha_ao_carregar_catalogo_a8ca4b8a");
    return (
      <div className="rounded-xl border border-[color:var(--tone-warning-border)] bg-[color:var(--tone-warning-bg)] p-4 text-sm text-[color:var(--tone-warning-text)]">
        <div className="font-medium mb-1">{t("generated.controlPlane.nao_foi_possivel_carregar_o_catalogo_5d80e428")}</div>
        <div className="text-[12px] text-[color:var(--text-secondary)]">{message}</div>
        <button
          type="button"
          className="mt-2 text-[12px] underline"
          onClick={() => {
            void refetch();
          }}
        >
          {t("generated.controlPlane.tentar_novamente_14dc7f3f")}
        </button>
      </div>
    );
  }

  if (!catalog || catalogLoading) {
    return (
      <div className="rounded-xl border border-[color:var(--divider-hair)] p-4 text-sm text-[var(--text-tertiary)]">
        {t("generated.controlPlane.carregando_catalogo_de_modelos_6c45df79")}
      </div>
    );
  }

  const anyInstalled = catalog.items.some((m) => m.installed);
  const showMissingModelAlert = memoryEnabled && !anyInstalled;

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] leading-relaxed text-[var(--text-tertiary)]">
        {tl(
          "Escolha o modelo usado para memória, knowledge base e cache semântico. " +
            "Nenhum vem pré-instalado: baixe sob demanda quando precisar.",
        )}
      </p>
      {showMissingModelAlert ? (
        <div
          className="flex items-start gap-2 rounded-lg border border-[color:var(--tone-warning-border)] bg-[color:var(--tone-warning-bg)] px-3 py-2 text-[12px] text-[color:var(--tone-warning-text)]"
          data-testid="embedding-missing-model-alert"
        >
          <AlertTriangle size={14} strokeWidth={1.75} className="mt-[2px] shrink-0" />
          <div className="flex flex-col gap-0.5">
            <span className="font-medium">
              {t("generated.controlPlane.memoria_ativada_sem_modelo_de_embedding_inst_ee8a3751")}
            </span>
            <span className="leading-snug text-[var(--text-secondary)]">
              {tl(
                "Extremamente recomendado escolher e baixar um modelo abaixo. " +
                  "Sem ele a recuperação semântica cai para um match por palavras-chave (qualidade degradada).",
              )}
            </span>
          </div>
        </div>
      ) : null}
      <div className="flex flex-col gap-1.5">
        {catalog.items.map((model) => {
          const isActiveModel = catalog.active === model.id;
          const downloading = isActive("embedding", model.id);
          const inFlightFromBackend =
            model.active_job?.status === "running" || model.active_job?.status === "pending";
          const showDownloading = downloading || inFlightFromBackend;
          // Operators can delete any installed model — even the active one.
          // The backend auto-switches to another installed model (or clears
          // the selection if none is on disk) so retrieval keeps working.
          const canDelete = model.installed;
          const armed = pendingDeleteId === model.id;
          return (
            <article
              key={model.id}
              className={cn(
                "flex flex-col gap-1.5 rounded-lg border px-3 py-2 transition-colors",
                isActiveModel
                  ? "border-[color:var(--accent)] bg-[color:var(--accent-muted)]/30"
                  : "border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]",
              )}
              data-testid={`embedding-model-card-${model.id}`}
            >
              <header className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <h4 className="truncate text-[13px] font-medium text-[var(--text-primary)]">
                    {model.title}
                  </h4>
                  {isActiveModel ? (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-pill bg-[color:var(--accent)]/15 px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--accent)]">
                      <CheckCircle2 size={10} />
                      {t("generated.controlPlane.ativo_70b78dfa")}
                    </span>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {!model.installed && !showDownloading ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleDownload(model)}
                      data-testid={`embedding-download-${model.id}`}
                    >
                      <Download size={13} />
                      {formatSize(model.size_mb)}
                    </Button>
                  ) : null}
                  {showDownloading ? (
                    <span
                      className="inline-flex h-5 min-w-7 items-center justify-center rounded-pill bg-[color:var(--panel-strong)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
                      role="status"
                      aria-label={t("generated.controlPlane.baixando_732b403f")}
                    >
                      <Loader2 size={11} className="animate-spin" />
                    </span>
                  ) : null}
                  {model.installed ? (
                    <Button
                      size="sm"
                      variant={isActiveModel ? "secondary" : "primary"}
                      disabled={isActiveModel || busyId === model.id}
                      onClick={() => handleSelect(model)}
                      data-testid={`embedding-select-${model.id}`}
                    >
                      {isActiveModel ? t("generated.controlPlane.em_uso_18b967aa") : t("generated.controlPlane.usar_este_b7a8b8ca")}
                    </Button>
                  ) : null}
                  {canDelete ? (
                    <Button
                      size="sm"
                      variant={armed ? "destructive" : "ghost"}
                      disabled={busyId === model.id}
                      onClick={() => handleDelete(model)}
                      data-testid={`embedding-delete-${model.id}`}
                      title={
                        armed ? t("generated.controlPlane.confirmar_clique_novamente_para_apagar_6fb78678") : t("generated.controlPlane.apagar_modelo_c94d0bbe")
                      }
                      aria-label={t("generated.controlPlane.apagar_modelo_c94d0bbe")}
                    >
                      <Trash2 size={13} />
                      {armed ? t("generated.controlPlane.confirmar_5aa769d9") : null}
                    </Button>
                  ) : null}
                </div>
              </header>
              <p className="line-clamp-2 text-[11px] leading-snug text-[var(--text-secondary)]">
                {tl(model.description)}
              </p>
              <footer className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-[var(--text-tertiary)]">
                <span className="inline-flex items-center gap-1">
                  <Sparkles size={10} strokeWidth={1.75} />
                  <Stars score={model.quality} />
                </span>
                <span className="inline-flex items-center gap-1">
                  <Zap size={10} strokeWidth={1.75} />
                  <Stars score={model.speed} />
                </span>
                <span className="inline-flex items-center gap-1">
                  <Cpu size={10} strokeWidth={1.75} />
                  {tl(HARDWARE_LABEL[model.hardware_hint] ?? model.hardware_hint)}
                </span>
                <span>
                  {formatSize(model.size_mb)} · {model.dimension}{translate("generated.controlPlane.d_ca9b7af8")}{" "}
                  {model.multilingual ? t("generated.controlPlane.multi_177b02bb") : t("generated.controlPlane.en_57756381")}
                </span>
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}
