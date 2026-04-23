"use client";

import { Focus } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { DetailBlock, DetailDatum, DetailGrid } from "@/components/ui/detail-group";
import { Drawer } from "@/components/ui/drawer";
import { StatusDot } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getMemoryTypeLabel, getMemoryTypeMeta } from "@/lib/memory-constants";
import type {
  MemoryGraphEdge,
  MemoryGraphNode,
  MemoryLearningNode,
  MemorySemanticStatus,
} from "@/lib/types";
import { cn, formatDateTime, formatRelativeTime, truncateText } from "@/lib/utils";

export type MemoryInspectorNode = MemoryGraphNode | MemoryLearningNode;

export interface MemoryInspectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  node: MemoryInspectorNode | null;
  relatedNodes: MemoryInspectorNode[];
  relatedEdges: MemoryGraphEdge[];
  semanticStatus: MemorySemanticStatus;
  onFocusNode?: (nodeId: string) => void;
  onRecenter?: () => void;
}

function isMemoryNode(node: MemoryInspectorNode): node is MemoryGraphNode {
  return node.kind === "memory";
}

function TypeBadge({ color, label }: { color: string; label: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-[color:var(--radius-chip)] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.12em]"
      style={{ color }}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

function NeighborRow({
  node,
  relation,
  onSelect,
}: {
  node: MemoryInspectorNode;
  relation: MemoryGraphEdge | undefined;
  onSelect?: () => void;
}) {
  const { t } = useAppI18n();
  const meta = getMemoryTypeMeta(
    isMemoryNode(node) ? node.memory_type : node.dominant_type,
  );
  const subtitle = isMemoryNode(node)
    ? `${getMemoryTypeLabel(node.memory_type, t)} · ${Math.round(node.importance * 100)}%`
    : `${t("memory.inspector.syntheticLearning", { defaultValue: "Aprendizado" })} · ${node.member_count}`;
  const relationLabel = relation
    ? relation.type === "semantic"
      ? t("memory.inspector.semantic", { defaultValue: "Semântico" })
      : relation.type === "session"
        ? t("common.session", { defaultValue: "Sessão" })
        : relation.type === "source"
          ? t("memory.inspector.source", { defaultValue: "Origem" })
          : t("memory.inspector.learning", { defaultValue: "Aprendizado" })
    : null;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center justify-between gap-3 border-t border-[color:var(--divider-hair)] py-2.5 pl-0.5 pr-1 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "first:border-t-0",
        "hover:bg-[color:var(--hover-tint)]",
        !onSelect && "cursor-default hover:bg-transparent",
      )}
      disabled={!onSelect}
    >
      <span className="flex min-w-0 items-center gap-2.5">
        <span
          aria-hidden
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: meta.color }}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.8125rem] text-[color:var(--text-primary)]">
            {truncateText(node.label || node.title, 54)}
          </span>
          <span className="block truncate font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
            {subtitle}
          </span>
        </span>
      </span>
      {relationLabel ? (
        <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
          {relationLabel}
        </span>
      ) : null}
    </button>
  );
}

function DrawerSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="px-5 py-4">
      <h4 className="mb-2.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-[color:var(--text-quaternary)]">
        {title}
      </h4>
      {children}
    </section>
  );
}

export function MemoryInspector({
  open,
  onOpenChange,
  node,
  relatedNodes,
  relatedEdges,
  semanticStatus,
  onFocusNode,
  onRecenter,
}: MemoryInspectorProps) {
  const { t } = useAppI18n();
  const handleClose = () => onOpenChange(false);

  if (!node) {
    return (
      <Drawer
        open={open}
        onOpenChange={onOpenChange}
        width="min(380px, 92vw)"
        title={t("memory.inspector.selectPoint", { defaultValue: "Selecione uma memória" })}
        description={t("memory.inspector.selectPointHint", {
          defaultValue: "Clique em um ponto do grafo para ver seus detalhes aqui.",
        })}
      >
        <div className="px-5 py-6 text-[0.8125rem] leading-6 text-[color:var(--text-tertiary)]">
          {t("memory.inspector.empty", {
            defaultValue: "Nenhum nó selecionado. Explore o mapa para começar.",
          })}
        </div>
      </Drawer>
    );
  }

  const isMemory = isMemoryNode(node);
  const meta = getMemoryTypeMeta(isMemory ? node.memory_type : node.dominant_type);
  const typeLabel = isMemory
    ? getMemoryTypeLabel(node.memory_type, t)
    : t("memory.inspector.learningBadge", { defaultValue: "Aprendizado" });

  const statusTone = isMemory
    ? node.is_active
      ? "success"
      : "danger"
    : "info";
  const statusLabel = isMemory
    ? node.is_active
      ? t("memory.inspector.active", { defaultValue: "Ativa" })
      : t("memory.inspector.inactive", { defaultValue: "Inativa" })
    : semanticStatus === "available"
      ? t("memory.health.semanticAvailable", { defaultValue: "Semântico ativo" })
      : t("memory.health.semanticFallback", { defaultValue: "Fallback contextual" });

  const headerMeta = (
    <div className="flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
      <StatusDot tone={statusTone as "success" | "danger" | "info"} />
      <span>{statusLabel}</span>
    </div>
  );

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      width="min(380px, 92vw)"
      title={
        <div className="flex items-center gap-2">
          <TypeBadge color={meta.color} label={typeLabel} />
          <span className="min-w-0 truncate text-[0.9375rem] font-medium text-[color:var(--text-primary)]">
            {truncateText(node.title || node.label, 38)}
          </span>
        </div>
      }
      description={headerMeta}
      footer={
        <div className="flex items-center justify-between gap-2">
          <Button variant="ghost" size="sm" onClick={handleClose}>
            {t("common.close", { defaultValue: "Fechar" })}
          </Button>
          {onRecenter ? (
            <Button variant="secondary" size="sm" onClick={onRecenter}>
              <Focus className="icon-xs" strokeWidth={1.75} />
              {t("memory.inspector.recenter", { defaultValue: "Centralizar" })}
            </Button>
          ) : null}
        </div>
      }
    >
      <DrawerSection title={t("memory.inspector.content", { defaultValue: "Conteúdo" })}>
        <p className="text-[0.8125rem] leading-6 text-[color:var(--text-primary)]">
          {isMemory ? node.content : node.summary}
        </p>
      </DrawerSection>

      <div className="border-t border-[color:var(--divider-hair)]" />

      <DrawerSection title={t("memory.inspector.details", { defaultValue: "Detalhes" })}>
        {isMemory ? (
          <DetailGrid columns={2}>
            <DetailDatum
              label={t("memory.inspector.importance", { defaultValue: "Importância" })}
              value={`${Math.round(node.importance * 100)}%`}
            />
            <DetailDatum
              label={t("memory.inspector.accesses", { defaultValue: "Acessos" })}
              value={`${node.access_count}`}
            />
            <DetailDatum
              label={t("memory.inspector.lastUsed", { defaultValue: "Último uso" })}
              value={
                node.last_accessed
                  ? formatRelativeTime(node.last_accessed)
                  : t("memory.inspector.notAccessedYet", { defaultValue: "—" })
              }
            />
            <DetailDatum
              label={t("memory.inspector.createdAt", { defaultValue: "Criada" })}
              value={
                node.created_at
                  ? formatDateTime(node.created_at)
                  : t("memory.inspector.noDate", { defaultValue: "—" })
              }
            />
            <DetailDatum
              label={t("memory.inspector.expiresAt", { defaultValue: "Expira" })}
              value={
                node.expires_at
                  ? formatRelativeTime(node.expires_at)
                  : t("memory.inspector.never", { defaultValue: "Sem prazo" })
              }
            />
            <DetailDatum
              label={t("common.session", { defaultValue: "Sessão" })}
              value={node.session_id ? truncateText(node.session_id, 18) : "—"}
            />
          </DetailGrid>
        ) : (
          <DetailGrid columns={2}>
            <DetailDatum
              label={t("memory.inspector.dominantType", { defaultValue: "Tipo dominante" })}
              value={typeLabel}
            />
            <DetailDatum
              label={t("memory.inspector.intensity", { defaultValue: "Intensidade" })}
              value={`${Math.round(node.importance * 100)}%`}
            />
            <DetailDatum
              label={t("memory.inspector.semanticStrength", { defaultValue: "Força semântica" })}
              value={
                node.semantic_strength != null
                  ? `${Math.round(node.semantic_strength * 100)}%`
                  : t("memory.inspector.contextualFallback", { defaultValue: "Contextual" })
              }
            />
            <DetailDatum
              label={t("memory.inspector.members", { defaultValue: "Membros" })}
              value={`${node.member_count}`}
            />
            <DetailDatum
              label={t("memory.inspector.sessions", { defaultValue: "Sessões" })}
              value={`${node.session_ids.length}`}
            />
          </DetailGrid>
        )}
      </DrawerSection>

      {isMemory && node.source_query_text ? (
        <>
          <div className="border-t border-[color:var(--divider-hair)]" />
          <DrawerSection title={t("memory.inspector.origin", { defaultValue: "Origem" })}>
            <DetailBlock monospace>{node.source_query_text}</DetailBlock>
          </DrawerSection>
        </>
      ) : null}

      <div className="border-t border-[color:var(--divider-hair)]" />

      <DrawerSection
        title={t("memory.inspector.relatedConnections", { defaultValue: "Conexões" })}
      >
        {relatedNodes.length === 0 ? (
          <p className="text-[0.8125rem] leading-6 text-[color:var(--text-tertiary)]">
            {t("memory.inspector.noVisibleConnections", {
              defaultValue: "Nenhuma conexão visível nos filtros atuais.",
            })}
          </p>
        ) : (
          <div className="-mx-1 flex flex-col">
            {relatedNodes.slice(0, 8).map((related) => {
              const relation = relatedEdges.find(
                (edge) =>
                  (edge.source === node.id && edge.target === related.id) ||
                  (edge.target === node.id && edge.source === related.id),
              );
              return (
                <NeighborRow
                  key={related.id}
                  node={related}
                  relation={relation}
                  onSelect={onFocusNode ? () => onFocusNode(related.id) : undefined}
                />
              );
            })}
          </div>
        )}
      </DrawerSection>
    </Drawer>
  );
}
