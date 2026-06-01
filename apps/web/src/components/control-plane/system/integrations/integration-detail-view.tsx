"use client";

import { useEffect } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Calendar,
  Check,
  CircleDot,
  ExternalLink,
  FileText,
  FolderOpen,
  GitBranch,
  GitMerge,
  GitPullRequest,
  HardDrive,
  LayoutDashboard,
  Mail,
  Pencil,
  Play,
  Plug,
  Plus,
  ScrollText,
  Search,
  Server,
  Shield,
  Table,
  Trash2,
  Workflow,
  Activity,
  Database,
} from "lucide-react";
import { motion } from "framer-motion";
import { AsyncActionButton, InlineSpinner } from "@/components/ui/async-feedback";
import { cn } from "@/lib/utils";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { renderIntegrationLogo } from "./integration-logos";
import { UNIFIED_CATEGORY_LABELS, type UnifiedIntegrationEntry } from "./integration-marketplace-data";

const CAPABILITY_ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  Search,
  Plus,
  Pencil,
  LayoutDashboard,
  FileText,
  FolderOpen,
  Mail,
  Calendar,
  HardDrive,
  Table,
  Database,
  Activity,
  Server,
  ScrollText,
  Shield,
  GitBranch,
  GitPullRequest,
  CircleDot,
  Play,
  GitMerge,
  Workflow,
};

function CapabilityRow({
  label,
  description,
  iconKey,
  index,
}: {
  label: string;
  description: string;
  iconKey: string;
  index: number;
}) {
  const { t, tl } = useAppI18n();
  const Icon = CAPABILITY_ICONS[iconKey];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay: 0.1 + index * 0.04,
        duration: 0.3,
        ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
      }}
      className={cn(
        "flex items-center gap-3.5 rounded-lg border border-[var(--border-subtle)] px-4 py-3",
        index % 2 === 0 ? "bg-[var(--surface-elevated-soft)]" : "bg-transparent",
      )}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
        {Icon ? (
          <Icon size={16} className="text-[var(--icon-primary)]" />
        ) : (
          <div className="h-4 w-4 rounded bg-[var(--field-bg)]" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-[var(--text-primary)]">{tl(label)}</div>
        <div className="mt-0.5 text-xs text-[var(--text-quaternary)]">{tl(description)}</div>
      </div>
      <span
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]"
        aria-label={`${tl(label)} — ${t("generated.controlPlane.incluido_da69d9db")}`}
      >
        <Check size={12} />
      </span>
    </motion.div>
  );
}

function InfoTable({
  rows,
}: {
  rows: Array<{ id: string; label: string; value: React.ReactNode }>;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
      {rows.map((row, index) => (
        <div
          key={row.id}
          className={cn(
            "flex items-center justify-between gap-6 px-4 py-3 text-sm",
            index !== rows.length - 1 && "border-b border-[var(--border-subtle)]",
            index % 2 === 0 ? "bg-[var(--surface-elevated-soft)]" : "bg-transparent",
          )}
        >
          <span className="text-[var(--text-tertiary)]">{row.label}</span>
          <span className="text-right font-medium text-[var(--text-primary)]">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

function StatusBadge({
  label,
  tone,
}: {
  label: string;
  tone: "verified" | "warning" | "neutral";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        tone === "verified" && "border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
        tone === "warning" && "border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
        tone === "neutral" && "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-secondary)]",
      )}
    >
      {tone === "verified" ? <Check size={11} /> : <AlertTriangle size={11} />}
      {label}
    </span>
  );
}

type IntegrationDetailViewProps = {
  entry: UnifiedIntegrationEntry;
  onBack: () => void;
  onConnect: () => void;
  onOpenMcpEditor?: (entry: UnifiedIntegrationEntry) => void;
  onRemoveMcpServer?: (entry: UnifiedIntegrationEntry) => void | Promise<void>;
  mcpRemoving?: boolean;
};

export function IntegrationDetailView({
  entry,
  onBack,
  onConnect,
  onOpenMcpEditor,
  onRemoveMcpServer,
  mcpRemoving = false,
}: IntegrationDetailViewProps) {
  const {
    draft,
    connectIntegration,
    integrationCatalog,
    integrationConnections,
    ensureIntegrationConnectionFresh,
    disconnectIntegrationConnection,
    isIntegrationActionPending,
    integrationActionStatus,
  } = useSystemSettings();
  const { t, tl } = useAppI18n();

  const logo = renderIntegrationLogo(entry.logoKey, "h-8 w-8 object-contain");
  const bannerLogo = renderIntegrationLogo(entry.logoKey, "h-4 w-4 object-contain");
  const isCoreEntry = entry.kind === "core";
  const coreEntry = entry.core?.entry ?? null;
  const mcpEntry = entry.mcp ?? null;

  const integrationDefinition = isCoreEntry
    ? integrationCatalog.find((item) => item.id === entry.key) || null
    : null;
  const connection = isCoreEntry ? integrationConnections[entry.key] || null : null;
  const systemEnabled = isCoreEntry
    ? Boolean(draft.values.resources.integrations[coreEntry?.toggleKey || ""])
    : false;
  const canManageConnection = Boolean(isCoreEntry && integrationDefinition?.supports_persistence);
  const canDisconnect = Boolean(canManageConnection && connection?.configured);

  useEffect(() => {
    if (!isCoreEntry || !canManageConnection || !connection?.configured) {
      return;
    }
    void ensureIntegrationConnectionFresh(entry.key);
  }, [
    canManageConnection,
    connection?.configured,
    connection?.connection_status,
    connection?.last_verified_at,
    ensureIntegrationConnectionFresh,
    entry.key,
    isCoreEntry,
    systemEnabled,
  ]);

  const connectionBadge = isCoreEntry
    ? connection?.connection_status === "verified"
      ? { label: t("generated.controlPlane.verificada_b357beca"), tone: "verified" as const }
      : connection?.connection_status === "degraded"
        ? { label: t("generated.controlPlane.degradada_142d8ead"), tone: "warning" as const }
        : connection?.connection_status === "auth_expired"
          ? { label: t("generated.controlPlane.auth_expirada_d303d113"), tone: "warning" as const }
          : connection?.connection_status === "configured"
            ? { label: t("generated.controlPlane.configurada_df5188a8"), tone: "warning" as const }
            : { label: t("generated.controlPlane.nao_configurada_50a5db79"), tone: "neutral" as const }
    : entry.status === "connected"
      ? { label: t("generated.controlPlane.ativo_no_catalogo_e7324d60"), tone: "verified" as const }
      : entry.status === "pending"
        ? { label: t("generated.controlPlane.desativado_no_catalogo_cb484f86"), tone: "warning" as const }
        : { label: t("generated.controlPlane.ainda_nao_adicionado_49a891f9"), tone: "neutral" as const };

  const availabilityLabel =
    isCoreEntry && entry.key === "browser"
      ? systemEnabled
        ? t("generated.controlPlane.gerenciada_internamente_80c9f504")
        : t("generated.controlPlane.gerenciamento_interno_desativado_8d02a69d")
      : isCoreEntry
        ? systemEnabled
          ? t("generated.controlPlane.ativa_no_sistema_c3a71821")
          : t("generated.controlPlane.desativada_no_sistema_1ee1b56d")
        : mcpEntry?.origin === "custom"
          ? t("generated.controlPlane.servidor_custom_0aea2e6d")
          : t("generated.controlPlane.servidor_curado_20357cf4");

  const metadataRows: Array<{ id: string; label: string; value: React.ReactNode }> = [
    {
      id: "category",
      label: t("generated.controlPlane.categoria_d4679e28"),
      value: tl(UNIFIED_CATEGORY_LABELS[entry.category]),
    },
    {
      id: "type",
      label: t("generated.controlPlane.tipo_50772377"),
      value: tl(entry.metadata.type),
    },
  ];

  if (isCoreEntry && connection) {
    metadataRows.push({
      id: "auth-method",
      label: t("generated.controlPlane.auth_mode_1eee1b22"),
      value: connection.auth_method || connection.auth_mode || t("generated.controlPlane.nao_definido_6d56afe4"),
    });
    metadataRows.push({
      id: "source-origin",
      label: t("generated.controlPlane.origem_da_conexao_a0f8a86e"),
      value:
        connection.source_origin === "system_default"
          ? t("generated.controlPlane.default_do_sistema_dcf3cdc9")
          : connection.source_origin === "local_session"
            ? t("generated.controlPlane.sessao_local_desta_maquina_b2dc5c38")
            : t("generated.controlPlane.binding_explicito_bc7f6172"),
    });
    metadataRows.push({
      id: "account-label",
      label: t("generated.controlPlane.conta_conectada_cb761484"),
      value: connection.account_label || t("generated.controlPlane.nao_identificada_3eaa7a48"),
    });
    if (connection.expires_at) {
      metadataRows.push({
        id: "expires-at",
        label: t("generated.controlPlane.expira_em_053d8009"),
        value: connection.expires_at,
      });
    }
  }

  if (entry.metadata.developer) {
    metadataRows.push({
      id: "developer",
      label: t("generated.controlPlane.desenvolvedor_430184b8"),
      value: entry.metadata.developer,
    });
  }

  if (!isCoreEntry && entry.metadata.transport) {
    metadataRows.push({
      id: "transport",
      label: t("generated.controlPlane.transporte_a6e18c12"),
      value: entry.metadata.transport,
    });
  }

  if (!isCoreEntry && entry.metadata.origin) {
    metadataRows.push({
      id: "origin",
      label: t("generated.controlPlane.origem_b7c29d8a"),
      value: entry.metadata.origin === "curated" ? t("generated.controlPlane.curado_657db740") : t("generated.controlPlane.custom_1995fb7d"),
    });
  }

  if (!isCoreEntry && entry.metadata.serverKey) {
    metadataRows.push({
      id: "server-key",
      label: t("generated.controlPlane.chave_do_servidor_b0f9c83a"),
      value: <span className="font-mono text-xs">{entry.metadata.serverKey}</span>,
    });
  }

  if (entry.metadata.documentationUrl) {
    metadataRows.push({
      id: "docs",
      label: t("generated.controlPlane.documentacao_9db82914"),
      value: (
        <a
          href={entry.metadata.documentationUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--tone-info-dot)] transition-colors hover:text-[var(--tone-info-text)]"
        >
          {t("generated.controlPlane.abrir_documentacao_f6e366c9")}
          <ExternalLink size={12} />
        </a>
      ),
    });
  }

  return (
    <div className="space-y-6">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-2 text-sm text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)]"
      >
        <ArrowLeft size={14} />
        <span>
          {t("generated.controlPlane.integracoes_012889d2")}
          <span className="mx-1.5 text-[var(--text-quaternary)]">/</span>
          <span className="text-[var(--text-primary)]">{entry.label}</span>
        </span>
      </button>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-4">
          <div
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl"
            style={{
              background: `color-mix(in srgb, ${entry.gradientFrom} 18%, var(--surface-elevated) 82%)`,
            }}
          >
            {logo}
          </div>
          <div>
            <h2 className="text-lg font-bold tracking-[-0.03em] text-[var(--text-primary)]">
              {entry.label}
            </h2>
            <p className="mt-0.5 text-sm text-[var(--text-tertiary)]">{tl(entry.tagline)}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={connectionBadge.label} tone={connectionBadge.tone} />
          <StatusBadge
            label={availabilityLabel}
            tone={isCoreEntry ? (systemEnabled ? "verified" : "neutral") : "neutral"}
          />
          {isCoreEntry &&
          entry.status !== "disabled" &&
          connection?.connection_status !== "verified" ? (
            <StatusBadge label={t("generated.controlPlane.precisa_de_validacao_47d43f6d")} tone="warning" />
          ) : null}
        </div>
      </div>

      <div
        className="integration-detail-banner relative overflow-hidden rounded-xl"
        style={{
          background: `linear-gradient(135deg, color-mix(in srgb, ${entry.gradientFrom} 18%, var(--surface-elevated) 82%), color-mix(in srgb, ${entry.gradientTo} 14%, var(--surface-panel-soft) 86%))`,
        }}
      >
        <div className="integration-detail-banner-grain" />
        <div className="relative z-10 px-6 py-5">
          <div className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-2">
            {bannerLogo}
            <span className="text-sm text-[var(--text-primary)]">{tl(entry.promptExample)}</span>
          </div>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{tl(entry.description)}</p>

      <section
        className="rounded-[26px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-5 py-4"
        aria-label={
          isCoreEntry
            ? t("generated.controlPlane.conexao_de_integration_4aad8d5d", { integration: entry.label })
            : t("generated.controlPlane.catalogo_mcp_de_integration_dfcb6ae8", { integration: entry.label })
        }
      >
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 flex-1 space-y-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {isCoreEntry ? t("generated.controlPlane.conexao_5d0e2f3c") : t("generated.controlPlane.catalogo_200920c4")}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
                {isCoreEntry
                  ? coreEntry?.hasCredentials
                    ? t("generated.controlPlane.salvar_a_conexao_grava_as_credenciais_no_con_520a5e16")
                    : t("generated.controlPlane.conectar_registra_esta_superficie_no_control_34739dbf")
                  : t("generated.controlPlane.os_servidores_mcp_aqui_representam_o_catalog_9f57a3d6")}
              </p>
            </div>

            {isCoreEntry && connection?.last_error ? (
              <div className="rounded-xl border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-4 py-3 text-sm text-[var(--tone-warning-text)]">
                <span className="font-medium">{t("generated.controlPlane.ultimo_erro_9a793b25")}:</span> {connection.last_error}
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-start justify-end gap-2 xl:max-w-[21rem]">
            {isCoreEntry ? (
              <>
                {coreEntry?.hasCredentials ? (
                  <button
                    type="button"
                    onClick={onConnect}
                    className="inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium text-[var(--interactive-active-text)] transition-all"
                    style={{
                      background:
                        "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                      border: "1px solid var(--interactive-active-border)",
                    }}
                  >
                    <Plug size={14} />
                    {connection?.configured ? t("generated.controlPlane.editar_conexao_32fbd125") : t("generated.controlPlane.conectar_a587e076")}
                  </button>
                ) : canManageConnection ? (
                  <AsyncActionButton
                    type="button"
                    variant="primary"
                    size="sm"
                    onClick={() => connectIntegration(entry.key)}
                    loading={isIntegrationActionPending(entry.key, "connect")}
                    status={integrationActionStatus(entry.key, "connect")}
                    loadingLabel={t("generated.controlPlane.conectando_6b3be187")}
                    icon={Plug}
                  >
                    {connection?.configured ? t("generated.controlPlane.atualizar_conexao_5195be6a") : t("generated.controlPlane.conectar_a587e076")}
                  </AsyncActionButton>
                ) : null}

                {canDisconnect ? (
                  <AsyncActionButton
                    type="button"
                    variant="danger"
                    size="sm"
                    onClick={() => disconnectIntegrationConnection(entry.key)}
                    loading={isIntegrationActionPending(entry.key, "disconnect")}
                    status={integrationActionStatus(entry.key, "disconnect")}
                    loadingLabel={t("generated.controlPlane.desconectando_35c02306")}
                  >
                    {t("generated.controlPlane.desconectar_d1a164af")}
                  </AsyncActionButton>
                ) : null}
              </>
            ) : (
              <>
                {mcpEntry?.canAdd ? (
                  <button
                    type="button"
                    onClick={() => onOpenMcpEditor?.(entry)}
                    className="inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium text-[var(--interactive-active-text)] transition-all"
                    style={{
                      background:
                        "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                      border: "1px solid var(--interactive-active-border)",
                    }}
                  >
                    <Plus size={14} />
                    {t("generated.controlPlane.adicionar_servidor_5ad219d2")}
                  </button>
                ) : null}

                {mcpEntry?.canEdit ? (
                  <button
                    type="button"
                    onClick={() => onOpenMcpEditor?.(entry)}
                    className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3.5 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Pencil size={14} />
                    {t("generated.controlPlane.editar_servidor_ab1f64e7")}
                  </button>
                ) : null}

                {mcpEntry?.canRemove ? (
                  <button
                    type="button"
                    onClick={() => onRemoveMcpServer?.(entry)}
                    disabled={mcpRemoving}
                    aria-label={mcpRemoving ? t("generated.controlPlane.removendo_2b311926") : undefined}
                    aria-busy={mcpRemoving || undefined}
                    className={cn(
                      "inline-flex min-w-36 items-center justify-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-medium transition-colors",
                      mcpRemoving
                        ? "cursor-not-allowed border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-quaternary)]"
                        : "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg-strong)]",
                    )}
                  >
                    {mcpRemoving ? (
                      <InlineSpinner className="h-3.5 w-3.5" />
                    ) : (
                      <>
                        <Trash2 size={14} />
                        {t("generated.controlPlane.remover_servidor_f9d6522a")}
                      </>
                    )}
                  </button>
                ) : null}
              </>
            )}
          </div>
        </div>
      </section>

      <div>
        <span className="eyebrow mb-3 block text-[var(--text-quaternary)]">{t("generated.controlPlane.inclui_e11ae750")}</span>
        {entry.capabilities.length > 0 ? (
          <div className="space-y-2">
            {entry.capabilities.map((capability, index) => (
              <CapabilityRow
                key={capability.id}
                label={tl(capability.label)}
                description={tl(capability.description)}
                iconKey={capability.icon}
                index={index}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-5 text-sm text-[var(--text-quaternary)]">
            {t("generated.controlPlane.este_servidor_mcp_nao_possui_um_catalogo_cur_862373be")}
          </div>
        )}
      </div>

      <div>
        <span className="eyebrow mb-3 block text-[var(--text-quaternary)]">{t("generated.controlPlane.informacoes_62821400")}</span>
        <InfoTable rows={metadataRows} />
      </div>
    </div>
  );
}
