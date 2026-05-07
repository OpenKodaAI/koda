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
import { AsyncActionButton } from "@/components/ui/async-feedback";
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
  const { tl } = useAppI18n();
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
        aria-label={`${tl(label)} — ${tl("Incluído")}`}
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
  const { tl } = useAppI18n();

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
      ? { label: tl("Verificada"), tone: "verified" as const }
      : connection?.connection_status === "degraded"
        ? { label: tl("Degradada"), tone: "warning" as const }
        : connection?.connection_status === "auth_expired"
          ? { label: tl("Auth expirada"), tone: "warning" as const }
          : connection?.connection_status === "configured"
            ? { label: tl("Configurada"), tone: "warning" as const }
            : { label: tl("Nao configurada"), tone: "neutral" as const }
    : entry.status === "connected"
      ? { label: tl("Ativo no catálogo"), tone: "verified" as const }
      : entry.status === "pending"
        ? { label: tl("Desativado no catálogo"), tone: "warning" as const }
        : { label: tl("Ainda não adicionado"), tone: "neutral" as const };

  const availabilityLabel =
    isCoreEntry && entry.key === "browser"
      ? systemEnabled
        ? tl("Gerenciada internamente")
        : tl("Gerenciamento interno desativado")
      : isCoreEntry
        ? systemEnabled
          ? tl("Ativa no sistema")
          : tl("Desativada no sistema")
        : mcpEntry?.origin === "custom"
          ? tl("Servidor custom")
          : tl("Servidor curado");

  const metadataRows: Array<{ id: string; label: string; value: React.ReactNode }> = [
    {
      id: "category",
      label: tl("Categoria"),
      value: tl(UNIFIED_CATEGORY_LABELS[entry.category]),
    },
    {
      id: "type",
      label: tl("Tipo"),
      value: tl(entry.metadata.type),
    },
  ];

  if (isCoreEntry && connection) {
    metadataRows.push({
      id: "auth-method",
      label: tl("Auth mode"),
      value: connection.auth_method || connection.auth_mode || tl("Não definido"),
    });
    metadataRows.push({
      id: "source-origin",
      label: tl("Origem da conexão"),
      value:
        connection.source_origin === "system_default"
          ? tl("Default do sistema")
          : connection.source_origin === "local_session"
            ? tl("Sessão local desta máquina")
            : tl("Binding explícito"),
    });
    metadataRows.push({
      id: "account-label",
      label: tl("Conta conectada"),
      value: connection.account_label || tl("Não identificada"),
    });
    if (connection.expires_at) {
      metadataRows.push({
        id: "expires-at",
        label: tl("Expira em"),
        value: connection.expires_at,
      });
    }
  }

  if (entry.metadata.developer) {
    metadataRows.push({
      id: "developer",
      label: tl("Desenvolvedor"),
      value: entry.metadata.developer,
    });
  }

  if (!isCoreEntry && entry.metadata.transport) {
    metadataRows.push({
      id: "transport",
      label: tl("Transporte"),
      value: entry.metadata.transport,
    });
  }

  if (!isCoreEntry && entry.metadata.origin) {
    metadataRows.push({
      id: "origin",
      label: tl("Origem"),
      value: entry.metadata.origin === "curated" ? tl("Curado") : tl("Custom"),
    });
  }

  if (!isCoreEntry && entry.metadata.serverKey) {
    metadataRows.push({
      id: "server-key",
      label: tl("Chave do servidor"),
      value: <span className="font-mono text-xs">{entry.metadata.serverKey}</span>,
    });
  }

  if (entry.metadata.documentationUrl) {
    metadataRows.push({
      id: "docs",
      label: tl("Documentação"),
      value: (
        <a
          href={entry.metadata.documentationUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--tone-info-dot)] transition-colors hover:text-[var(--tone-info-text)]"
        >
          {tl("Abrir documentação")}
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
          {tl("Integrações")}
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
            <StatusBadge label={tl("Precisa de validacao")} tone="warning" />
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
            ? tl("Conexão de {{integration}}", { integration: entry.label })
            : tl("Catálogo MCP de {{integration}}", { integration: entry.label })
        }
      >
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 flex-1 space-y-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {isCoreEntry ? tl("Conexão") : tl("Catálogo")}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
                {isCoreEntry
                  ? coreEntry?.hasCredentials
                    ? tl("Salvar a conexão grava as credenciais no control plane. A verificação executa o probe real da integração e atualiza o health, o checked_via e o estado operacional.")
                    : tl("Conectar registra esta superfície no control plane. A verificação roda automaticamente ao abrir este detalhe, executa o probe operacional on-demand e reaproveita um cache curto para evitar rechecagens desnecessárias.")
                  : tl("Os servidores MCP aqui representam o catálogo global do sistema. Adicionar ou editar um item atualiza a definição do servidor, transporte, documentação e schema de variáveis, enquanto a conexão por agente continua no editor de bots.")}
              </p>
            </div>

            {isCoreEntry && connection?.last_error ? (
              <div className="rounded-xl border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-4 py-3 text-sm text-[var(--tone-warning-text)]">
                <span className="font-medium">{tl("Último erro")}:</span> {connection.last_error}
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
                    {connection?.configured ? tl("Editar conexão") : tl("Conectar")}
                  </button>
                ) : canManageConnection ? (
                  <AsyncActionButton
                    type="button"
                    variant="primary"
                    size="sm"
                    onClick={() => connectIntegration(entry.key)}
                    loading={isIntegrationActionPending(entry.key, "connect")}
                    status={integrationActionStatus(entry.key, "connect")}
                    loadingLabel={tl("Conectando")}
                    icon={Plug}
                  >
                    {connection?.configured ? tl("Atualizar conexão") : tl("Conectar")}
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
                    loadingLabel={tl("Desconectando")}
                  >
                    {tl("Desconectar")}
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
                    {tl("Adicionar servidor")}
                  </button>
                ) : null}

                {mcpEntry?.canEdit ? (
                  <button
                    type="button"
                    onClick={() => onOpenMcpEditor?.(entry)}
                    className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3.5 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Pencil size={14} />
                    {tl("Editar servidor")}
                  </button>
                ) : null}

                {mcpEntry?.canRemove ? (
                  <button
                    type="button"
                    onClick={() => onRemoveMcpServer?.(entry)}
                    disabled={mcpRemoving}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-medium transition-colors",
                      mcpRemoving
                        ? "cursor-not-allowed border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-quaternary)]"
                        : "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg-strong)]",
                    )}
                  >
                    <Trash2 size={14} />
                    {mcpRemoving ? tl("Removendo") : tl("Remover servidor")}
                  </button>
                ) : null}
              </>
            )}
          </div>
        </div>
      </section>

      <div>
        <span className="eyebrow mb-3 block text-[var(--text-quaternary)]">{tl("Inclui")}</span>
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
            {tl("Este servidor MCP não possui um catálogo curado de ferramentas esperadas.")}
          </div>
        )}
      </div>

      <div>
        <span className="eyebrow mb-3 block text-[var(--text-quaternary)]">{tl("Informações")}</span>
        <InfoTable rows={metadataRows} />
      </div>
    </div>
  );
}
